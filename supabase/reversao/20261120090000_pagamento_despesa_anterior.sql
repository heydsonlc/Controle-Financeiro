-- REVERSAO da migration 20261120090000 (FIN-CONTRATOS-2): devolve bloqueio_do_pagamento, pagar_despesa e
-- estornar_pagamento_despesa as definicoes de 20261101090000 (parcelas de consorcio e de financiamento voltam a ser
-- recusadas) e remove as 4 funcoes internas. Mesmas assinaturas e privilegios. Nenhum dado e alterado.
-- Nao e migration (fora de supabase/migrations). Aplicar so com autorizacao, numa transacao.

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
    if v_item.tipo = 'Consorcio' then
        return 'Parcela de consorcio: paga no modulo de consorcios do sistema atual';
    end if;
    if v_item.tipo = 'Financiamento' or v_conta.financiamento_parcela_id is not null
       or exists (select 1 from public.financiamento_parcela fp where fp.conta_id = v_conta.id) then
        return 'Parcela de financiamento: paga no modulo de financiamentos do sistema atual';
    end if;
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

drop function if exists financeiro.reabrir_parcela_estornada(integer);
drop function if exists financeiro.sincronizar_parcela_paga(integer, numeric);
drop function if exists financeiro.saldo_devedor_pelas_parcelas(integer);
drop function if exists financeiro.parcela_da_despesa(integer);
