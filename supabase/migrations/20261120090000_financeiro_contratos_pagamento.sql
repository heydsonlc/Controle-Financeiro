-- FIN-CONTRATOS-2 — pagamento e estorno das parcelas de financiamento e de consorcio pelas despesas, no novo
-- aplicativo (escritor unico do perfil).
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261120090000).
-- Validada em cluster local descartavel, comparada com o PROPRIO Flask (tests/test_supabase_contratos_pagamento.py).
-- Docs: docs/FIN_CONTRATOS_2.md. Reversao: supabase/reversao/20261120090000_pagamento_despesa_anterior.sql.
--
-- O caminho real do Flask: cada parcela de financiamento tem a sua despesa (public.conta, financiamento_parcela_id) e e
-- paga em Despesas (marcar_como_pago + FinanciamentoService.registrar_pagamento_parcela); a parcela de consorcio e a
-- despesa do item 'Consorcio' (sem estado proprio a sincronizar). Esta migration:
-- - libera essas despesas em bloqueio_do_pagamento (fatura de cartao continua na tela de cartoes);
-- - pagar_despesa sincroniza a parcela na MESMA transacao (status 'pago', valor_pago, dif_apurada = previsto - pago,
--   saldo devedor do contrato), como registrar_pagamento_parcela;
-- - estornar_pagamento_despesa reabre a parcela (Defeito A: o Flask devolve a despesa a 'Pendente' e deixa a parcela
--   'pago', com o saldo devedor reduzido), so a partir da parcela paga mais recente (regra do estorno direto do Flask,
--   que preserva a cadeia do saldo devedor);
-- - a identidade do estorno ja e o debito original (Defeito B: pagar, estornar, pagar e estornar de novo funciona; o
--   Flask procura estorno anterior pela despesa/parcela e bloqueia o segundo para sempre).
-- Correcao em relacao ao Flask: o saldo devedor do contrato e sempre o da parcela paga de MAIOR numero (o Flask grava o
-- da ultima parcela paga, mesmo fora de ordem); sem parcela paga, o valor financiado. Parcela ligada pela despesa
-- (conta.financiamento_parcela_id) ou pela parcela (financiamento_parcela.conta_id): as duas formas do Flask.
-- O texto de bloqueio_do_pagamento, pagar_despesa e estornar_pagamento_despesa e o de 20261101090000 com as linhas
-- marcadas FIN-CONTRATOS-2 (mesma assinatura e privilegios). Nenhuma tabela nova; nenhum dado existente e alterado.

-- Parcela de financiamento da despesa (ou nada), pelas duas ligacoes do Flask. Interna.
create function financeiro.parcela_da_despesa(p_conta_id integer)
    returns integer
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select coalesce((select c.financiamento_parcela_id from public.conta c where c.id = p_conta_id),
                    (select fp.id from public.financiamento_parcela fp where fp.conta_id = p_conta_id order by fp.id limit 1))
$$;

-- Saldo devedor do contrato pela cadeia das parcelas: o da paga de maior numero; sem paga, o valor financiado. Interna.
create function financeiro.saldo_devedor_pelas_parcelas(p_financiamento_id integer)
    returns numeric
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select coalesce((select p.saldo_devedor_apos_pagamento from public.financiamento_parcela p
                      where p.financiamento_id = p_financiamento_id and p.status = 'pago'
                      order by p.numero_parcela desc, p.id desc limit 1),
                    (select f.valor_financiado from public.financiamento f where f.id = p_financiamento_id))
$$;

-- Pagamento da despesa de uma parcela (chamada por pagar_despesa, ja com a despesa travada): parcela 'pago' com o valor
-- pago e a diferenca para o previsto, e o saldo devedor do contrato. Despesa sem parcela: nada. Interna.
create function financeiro.sincronizar_parcela_paga(p_conta_id integer, p_valor numeric)
    returns void
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_id      integer := financeiro.parcela_da_despesa(p_conta_id);
    v_parcela public.financiamento_parcela;
begin
    if v_id is null then
        return;
    end if;
    select * into v_parcela from public.financiamento_parcela p where p.id = v_id;
    perform 1 from public.financiamento f where f.id = v_parcela.financiamento_id for update;  -- financiamento -> parcela
    select * into v_parcela from public.financiamento_parcela p where p.id = v_id for update;
    if v_parcela.status = 'pago' then
        raise exception 'Esta parcela ja foi paga' using errcode = '22023', hint = 'PARCELA_PAGA';
    end if;
    update public.financiamento_parcela
       set valor_pago = p_valor, dif_apurada = coalesce(valor_previsto_total, 0) - p_valor, status = 'pago'
     where id = v_parcela.id;
    update public.financiamento
       set saldo_devedor_atual = financeiro.saldo_devedor_pelas_parcelas(v_parcela.financiamento_id)
     where id = v_parcela.financiamento_id;
end
$$;

-- Estorno da despesa de uma parcela (chamada por estornar_pagamento_despesa antes de gravar): so a parcela paga mais
-- recente; ela volta a 'pendente' (valor pago e diferenca zerados) e o saldo devedor volta a cadeia. Interna.
create function financeiro.reabrir_parcela_estornada(p_conta_id integer)
    returns void
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_id      integer := financeiro.parcela_da_despesa(p_conta_id);
    v_parcela public.financiamento_parcela;
    v_depois  integer;
begin
    if v_id is null then
        return;
    end if;
    select * into v_parcela from public.financiamento_parcela p where p.id = v_id;
    perform 1 from public.financiamento f where f.id = v_parcela.financiamento_id for update;
    select * into v_parcela from public.financiamento_parcela p where p.id = v_id for update;
    select max(p.numero_parcela) into v_depois from public.financiamento_parcela p
     where p.financiamento_id = v_parcela.financiamento_id and p.status = 'pago' and p.numero_parcela > v_parcela.numero_parcela;
    if v_depois is not null then
        raise exception 'Existe uma parcela paga mais recente (numero %). Estorne a partir da parcela mais recente para preservar a cadeia de saldo devedor.',
            v_depois using errcode = '22023', hint = 'PARCELA_POSTERIOR_PAGA';
    end if;
    update public.financiamento_parcela set status = 'pendente', valor_pago = 0, dif_apurada = 0 where id = v_parcela.id;
    update public.financiamento
       set saldo_devedor_atual = financeiro.saldo_devedor_pelas_parcelas(v_parcela.financiamento_id)
     where id = v_parcela.financiamento_id;
end
$$;

revoke execute on function financeiro.parcela_da_despesa(integer) from public, anon, authenticated;
revoke execute on function financeiro.saldo_devedor_pelas_parcelas(integer) from public, anon, authenticated;
revoke execute on function financeiro.sincronizar_parcela_paga(integer, numeric) from public, anon, authenticated;
revoke execute on function financeiro.reabrir_parcela_estornada(integer) from public, anon, authenticated;

-- Funcoes de 20261101090000 com as linhas FIN-CONTRATOS-2 ---------------------------------------------------

create or replace function financeiro.bloqueio_do_pagamento(p_conta_id integer)
    returns text
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_conta public.conta;
    v_item  public.item_despesa;
begin
    select * into v_conta from public.conta where id = p_conta_id;
    if not found then
        return 'Despesa inexistente';
    end if;
    select * into v_item from public.item_despesa where id = v_conta.item_despesa_id;
    if coalesce(v_conta.is_fatura_cartao, false) then
        return 'Fatura de cartao: pague na tela de cartoes';
    end if;
    -- FIN-CONTRATOS-2: parcelas de consorcio (despesa comum do item 'Consorcio') e de financiamento (sincronizada pela
    -- financeiro.sincronizar_parcela_paga) sao pagas aqui, pelo escritor unico do perfil.
    return null;
end
$$;

create or replace function financeiro.pagar_despesa(p_perfil_id integer, p_conta_id integer, p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_anterior  financeiro.operacao_despesa;
    v_conta     public.conta;
    v_banco     public.conta_bancaria;
    v_bloqueio  text;
    v_data      date;
    v_valor     numeric;
    v_visto     numeric;
    v_devido    numeric;
    v_tipo      text;
    v_just      text;
    v_mov       integer;
    v_saldo     numeric;
    v_resultado jsonb;
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if p_chave is null then
        raise exception 'Chave da operacao obrigatoria' using errcode = '22023';
    end if;
    perform pg_advisory_xact_lock(hashtextextended(p_chave::text, 20261101));
    select * into v_anterior from financeiro.operacao_despesa o where o.chave = p_chave;
    if found then
        if v_anterior.user_id is distinct from (select auth.uid()) or v_anterior.perfil_financeiro_id <> p_perfil_id
           or v_anterior.operacao <> 'pagar_despesa' then
            raise exception 'Chave da operacao ja usada' using errcode = '22023';
        end if;
        return v_anterior.resultado || jsonb_build_object('repetida', true);
    end if;
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' then
        raise exception 'Dados do pagamento invalidos' using errcode = '22023';
    end if;
    begin
        v_data := (p_dados ->> 'data_pagamento')::date;
        v_valor := (p_dados ->> 'valor_pago')::numeric;
        v_visto := (p_dados ->> 'valor_devido')::numeric;
    exception when invalid_text_representation or datetime_field_overflow or invalid_datetime_format
                   or numeric_value_out_of_range then
        raise exception 'Dados do pagamento invalidos' using errcode = '22023';
    end;
    if v_data is null then
        raise exception 'Informe a data do pagamento' using errcode = '22023';
    end if;
    if v_valor is null or v_valor <= 0 or v_valor <> round(v_valor, 2) then
        raise exception 'Valor pago deve ser positivo, com ate 2 casas decimais' using errcode = '22023';
    end if;

    perform financeiro.exigir_pagamento_novo(p_perfil_id);
    select * into v_conta from public.conta c where c.id = p_conta_id for update;
    if not found or not financeiro.pertence_ao_perfil(v_conta.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Despesa nao encontrada neste perfil' using errcode = '42501';
    end if;
    v_bloqueio := financeiro.bloqueio_do_pagamento(v_conta.id);
    if v_bloqueio is not null then
        raise exception 'Operacao bloqueada: %', v_bloqueio using errcode = '22023', hint = 'BLOQUEADA';
    end if;
    if v_conta.status_pagamento = 'Pago' then
        raise exception 'Esta despesa ja foi paga' using errcode = '22023', hint = 'DESPESA_PAGA';
    end if;
    v_devido := coalesce(v_conta.valor, 0);
    if v_devido <= 0 then
        raise exception 'Despesa sem valor a pagar' using errcode = '22023';
    end if;
    if v_visto is distinct from v_devido then
        raise exception 'O valor da despesa mudou para R$ %. Confira e confirme de novo.',
            replace(to_char(v_devido, 'FM999999990.00'), '.', ',') using errcode = '22023', hint = 'VALOR_MUDOU';
    end if;
    if v_valor <> v_devido then
        v_tipo := upper(btrim(coalesce(p_dados ->> 'tipo_ajuste', '')));
        v_just := btrim(coalesce(p_dados ->> 'justificativa', ''));
        if v_tipo not in ('JUROS', 'DESCONTO', 'AJUSTE') or (v_tipo = 'JUROS' and v_valor < v_devido)
           or (v_tipo = 'DESCONTO' and v_valor > v_devido) then
            raise exception 'Valor diferente do devido: classifique a diferenca (juros, desconto ou ajuste de quitacao integral)'
                using errcode = '22023', hint = 'AJUSTE_OBRIGATORIO';
        end if;
        if v_just = '' or length(v_just) > 500 then
            raise exception 'Valor diferente do devido: a justificativa e obrigatoria (ate 500 caracteres)'
                using errcode = '22023', hint = 'AJUSTE_OBRIGATORIO';
        end if;
    end if;
    v_banco := financeiro.travar_conta_bancaria(p_perfil_id, (p_dados ->> 'conta_bancaria_id')::integer);

    insert into public.movimento_financeiro (perfil_financeiro_id, conta_bancaria_id, tipo, valor, descricao, data_movimento,
                                             conta_id, origem, ajustavel, criado_em)
    values (p_perfil_id, v_banco.id, 'DEBITO', v_valor, left('Pagamento despesa - ' || coalesce(v_conta.descricao, ''), 200),
            v_data, v_conta.id, 'DESPESA', false, now() at time zone 'utc')
    returning id into v_mov;
    v_saldo := financeiro.atualizar_saldo_conta(v_banco.id);
    update public.conta set valor = v_valor, status_pagamento = 'Pago', data_pagamento = v_data, conta_bancaria_id = v_banco.id
     where id = v_conta.id;
    perform financeiro.sincronizar_parcela_paga(v_conta.id, v_valor);  -- FIN-CONTRATOS-2: mesma transacao
    insert into financeiro.pagamento_fatura (fatura_id, perfil_financeiro_id, movimento_id, origem, valor_executado,
                                            tipo_ajuste, justificativa, user_id)
    values (v_conta.id, p_perfil_id, v_mov, 'NOVO_APP', v_devido, v_tipo, nullif(v_just, ''), (select auth.uid()));
    v_resultado := jsonb_build_object('conta_id', v_conta.id, 'movimento_id', v_mov, 'valor_pago', v_valor,
                                      'valor_devido', v_devido, 'tipo_ajuste', v_tipo, 'data_pagamento', v_data,
                                      'conta_bancaria_id', v_banco.id, 'conta_nome', v_banco.nome, 'saldo_conta', v_saldo);
    insert into financeiro.operacao_despesa (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'pagar_despesa', v_resultado);
    return v_resultado;
end
$$;

create or replace function financeiro.estornar_pagamento_despesa(p_perfil_id integer, p_conta_id integer, p_movimento_id integer,
                                                      p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_anterior  financeiro.operacao_despesa;
    v_conta     public.conta;
    v_original  public.movimento_financeiro;
    v_pag       financeiro.pagamento_fatura;
    v_motivo    text;
    v_data      date;
    v_estorno   integer;
    v_saldo     numeric;
    v_resultado jsonb;
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if p_chave is null then
        raise exception 'Chave da operacao obrigatoria' using errcode = '22023';
    end if;
    perform pg_advisory_xact_lock(hashtextextended(p_chave::text, 20261101));
    select * into v_anterior from financeiro.operacao_despesa o where o.chave = p_chave;
    if found then
        if v_anterior.user_id is distinct from (select auth.uid()) or v_anterior.perfil_financeiro_id <> p_perfil_id
           or v_anterior.operacao <> 'estornar_pagamento_despesa' then
            raise exception 'Chave da operacao ja usada' using errcode = '22023';
        end if;
        return v_anterior.resultado || jsonb_build_object('repetida', true);
    end if;
    v_motivo := btrim(coalesce(p_dados ->> 'motivo', ''));
    if v_motivo = '' or length(v_motivo) > 500 then
        raise exception 'Informe o motivo do estorno (ate 500 caracteres)' using errcode = '22023';
    end if;
    begin
        v_data := (p_dados ->> 'data_estorno')::date;
    exception when invalid_datetime_format or datetime_field_overflow then
        raise exception 'Data do estorno invalida' using errcode = '22023';
    end;
    if v_data is null then
        raise exception 'Informe a data do estorno' using errcode = '22023';
    end if;
    if p_movimento_id is null then
        raise exception 'Pagamento a estornar nao identificado' using errcode = '22023';
    end if;

    perform financeiro.exigir_pagamento_novo(p_perfil_id);
    select * into v_conta from public.conta c where c.id = p_conta_id for update;
    if not found or not financeiro.pertence_ao_perfil(v_conta.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Despesa nao encontrada neste perfil' using errcode = '42501';
    end if;
    if financeiro.bloqueio_do_pagamento(v_conta.id) is not null then
        raise exception 'Operacao bloqueada: %', financeiro.bloqueio_do_pagamento(v_conta.id)
            using errcode = '22023', hint = 'BLOQUEADA';
    end if;
    if v_conta.status_pagamento is distinct from 'Pago' then
        raise exception 'Esta despesa nao esta paga: nada a estornar' using errcode = '22023', hint = 'NAO_PAGA';
    end if;
    select * into v_original from public.movimento_financeiro m where m.id = p_movimento_id;
    if not found or v_original.tipo <> 'DEBITO' or v_original.origem <> 'DESPESA' or v_original.conta_id <> v_conta.id then
        raise exception 'Pagamento nao encontrado nesta despesa' using errcode = '22023';
    end if;
    perform 1 from public.conta_bancaria cb where cb.id = v_original.conta_bancaria_id for update;
    perform 1 from public.movimento_financeiro m where m.id = v_original.id for update;
    if p_movimento_id is distinct from financeiro.debito_vigente(v_conta.id, 'DESPESA') then
        raise exception 'Este pagamento ja foi estornado ou nao e o pagamento atual da despesa'
            using errcode = '22023', hint = 'JA_ESTORNADO';
    end if;
    perform financeiro.reabrir_parcela_estornada(v_conta.id);  -- FIN-CONTRATOS-2 (Defeito A): antes de qualquer gravacao

    insert into public.movimento_financeiro (perfil_financeiro_id, conta_bancaria_id, tipo, valor, descricao, data_movimento,
                                             conta_id, origem, ajustavel, movimento_original_id, criado_em)
    values (coalesce(v_original.perfil_financeiro_id, p_perfil_id), v_original.conta_bancaria_id, 'CREDITO', v_original.valor,
            left('Estorno de pagamento da despesa: ' || coalesce(v_conta.descricao, v_conta.id::text), 200), v_data,
            v_conta.id, 'ESTORNO_DESPESA', false, v_original.id, now() at time zone 'utc')
    returning id into v_estorno;
    v_saldo := financeiro.atualizar_saldo_conta(v_original.conta_bancaria_id);
    select * into v_pag from financeiro.pagamento_fatura p where p.movimento_id = v_original.id;
    update public.conta
       set status_pagamento = 'Pendente', data_pagamento = null,
           valor = coalesce(v_pag.valor_executado, valor),
           observacoes = concat_ws(E'\n', nullif(observacoes, ''), '[ESTORNO] ' || v_data::text || ' — ' || v_motivo)
     where id = v_conta.id;
    if v_pag.id is not null then
        update financeiro.pagamento_fatura
           set estorno_movimento_id = v_estorno, estorno_motivo = v_motivo, estorno_user_id = (select auth.uid()),
               estornado_em = now()
         where id = v_pag.id;
    else  -- pagamento feito pelo Flask (ou debito automatico): registra so o estorno
        insert into financeiro.pagamento_fatura (fatura_id, perfil_financeiro_id, movimento_id, origem, estorno_movimento_id,
                                                estorno_motivo, estorno_user_id, estornado_em)
        values (v_conta.id, p_perfil_id, v_original.id, 'FLASK', v_estorno, v_motivo, (select auth.uid()), now());
    end if;
    v_resultado := jsonb_build_object('conta_id', v_conta.id, 'movimento_estorno_id', v_estorno,
                                      'movimento_original_id', v_original.id, 'valor_estornado', v_original.valor,
                                      'data_estorno', v_data, 'conta_bancaria_id', v_original.conta_bancaria_id,
                                      'saldo_conta', v_saldo);
    insert into financeiro.operacao_despesa (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'estornar_pagamento_despesa', v_resultado);
    return v_resultado;
end
$$;
