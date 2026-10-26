-- FIN-FIDELIDADE-CONTRATOS-1 (fase 2) — pagamento e estorno de parcela de financiamento pela tela de Financiamentos.
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261111090000).
-- Depende de 20261109090000 (financeiro.operacao_repetida) e 20261110090000 (financeiro.financiamento_tela).
-- Validada em cluster local descartavel (tests/test_supabase_financiamentos_pagamento.py, comparada com o Flask).
-- Docs: docs/FIN_FIDELIDADE_CONTRATOS_1.md.
--
-- Regras do Flask (routes/financiamentos.py pagar_parcela / estornar_pagamento_parcela, CORE-SALDO-1C e
-- CORE-ESTORNO-4), nas mesmas tabelas e origens:
-- - pagamento: DEBITO na conta bancaria (origem FINANCIAMENTO, financiamento_parcela_id) pelo valor previsto total;
--   parcela 'pago' com valor_pago = previsto e dif_apurada = 0; saldo devedor atual = saldo apos esta parcela;
-- - estorno: so a parcela paga de maior numero; CREDITO ligado ao debito (origem ESTORNO_FINANCIAMENTO,
--   movimento_original_id) na mesma conta e valor; parcela 'pendente', valor_pago 0, dif_apurada 0; saldo devedor
--   atual = saldo apos a parcela anterior (ou o valor financiado na 1a).
-- Motor de movimentos do MVP 2: escritor unico por perfil (financeiro.exigir_pagamento_novo), chave de idempotencia
-- (financeiro.operacao_despesa), travas chave -> perfil -> financiamento -> parcela -> conta bancaria, saldo pelos
-- movimentos (financeiro.atualizar_saldo_conta).
-- Correcoes em relacao ao Flask (docs §6):
-- - a identidade do estorno e o debito original: pagar, estornar, pagar e estornar de novo funciona (o Flask procura
--   estorno pela parcela e bloqueia para sempre o segundo estorno); estornos antigos sem movimento_original_id contam
--   pela parcela, como no Flask;
-- - descricao do movimento com o nome do financiamento (o Flask le um atributo 'descricao' que o modelo nao tem e
--   grava sempre 'Financiamento #id');
-- - o motivo do estorno fica registrado no resultado da operacao (o Flask monta a observacao e a descarta).
-- Fora daqui (continuam no sistema atual): parcela com despesa vinculada (Conta.financiamento_parcela_id) ou de
-- financiamento ligado a item de despesa — o Flask sincroniza essas despesas (sincronizar_contas) e o estorno pelo
-- fluxo de Despesas nao reabre a parcela; amortizacao, ajuste de saldo e o motor de calculo (fase 3).
-- Nenhuma tabela nova. Nenhum dado existente e alterado pela migration.

-- Por que a parcela nao e paga/estornada por aqui (NULL = pode). Interna.
create function financeiro.bloqueio_da_parcela(p_parcela public.financiamento_parcela, p_fin public.financiamento)
    returns text
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select case
        when p_fin.item_despesa_id is not null
             or exists (select 1 from public.conta c where c.financiamento_parcela_id = p_parcela.id)
             or p_parcela.conta_id is not null
            then 'Parcela com despesa vinculada: o pagamento e o estorno continuam no sistema atual nesta fase. Nada foi gravado.'
    end
$$;

-- Parcela do perfil, travada com o financiamento (ordem: financiamento -> parcela). Interna.
create function financeiro.travar_parcela_financiamento(p_perfil_id integer, p_parcela_id integer)
    returns public.financiamento_parcela
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_parcela public.financiamento_parcela;
begin
    select * into v_parcela from public.financiamento_parcela p where p.id = p_parcela_id;
    if not found then
        raise exception 'Parcela nao encontrada' using errcode = '22023', hint = 'NAO_ENCONTRADA';
    end if;
    perform 1 from public.financiamento f where f.id = v_parcela.financiamento_id for update;
    select * into v_parcela from public.financiamento_parcela p where p.id = p_parcela_id for update;
    if not financeiro.pertence_ao_perfil(v_parcela.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Parcela nao encontrada' using errcode = '22023', hint = 'NAO_ENCONTRADA';
    end if;
    return v_parcela;
end
$$;

-- POST /api/financiamentos/parcelas/<id>/pagar. p_dados: conta_bancaria_id, data_pagamento (YYYY-MM-DD).
create function financeiro.pagar_parcela_financiamento(p_perfil_id integer, p_parcela_id integer, p_dados jsonb,
                                                       p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_repetida  jsonb;
    v_parcela   public.financiamento_parcela;
    v_fin       public.financiamento;
    v_banco     public.conta_bancaria;
    v_bloqueio  text;
    v_conta_id  integer;
    v_data      date;
    v_mov       integer;
    v_saldo     numeric;
    v_resultado jsonb;
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    v_repetida := financeiro.operacao_repetida(p_perfil_id, p_chave, 'pagar_parcela_financiamento');
    if v_repetida is not null then
        return v_repetida;
    end if;
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' then
        raise exception 'Dados do pagamento invalidos' using errcode = '22023';
    end if;
    if nullif(btrim(coalesce(p_dados ->> 'conta_bancaria_id', '')), '') is null then
        raise exception 'Informe a conta bancaria para registrar o pagamento da parcela.' using errcode = '22023';
    end if;
    begin
        v_conta_id := (p_dados ->> 'conta_bancaria_id')::integer;
    exception when invalid_text_representation or numeric_value_out_of_range then
        raise exception 'conta_bancaria_id invalido' using errcode = '22023';
    end;
    if nullif(btrim(coalesce(p_dados ->> 'data_pagamento', '')), '') is null then
        raise exception 'data_pagamento e obrigatorio' using errcode = '22023';
    end if;
    if (p_dados ->> 'data_pagamento') !~ '^\d{4}-\d{2}-\d{2}$' then
        raise exception 'Formato de data_pagamento invalido. Use YYYY-MM-DD' using errcode = '22023';
    end if;
    begin
        v_data := (p_dados ->> 'data_pagamento')::date;
    exception when invalid_datetime_format or datetime_field_overflow then
        raise exception 'Formato de data_pagamento invalido. Use YYYY-MM-DD' using errcode = '22023';
    end;

    perform financeiro.exigir_pagamento_novo(p_perfil_id);
    v_parcela := financeiro.travar_parcela_financiamento(p_perfil_id, p_parcela_id);
    if v_parcela.status = 'pago' then
        raise exception 'Esta parcela ja foi paga.' using errcode = '22023', hint = 'PARCELA_PAGA';
    end if;
    select * into v_fin from public.financiamento f where f.id = v_parcela.financiamento_id;
    v_bloqueio := financeiro.bloqueio_da_parcela(v_parcela, v_fin);
    if v_bloqueio is not null then
        raise exception '%', v_bloqueio using errcode = '22023', hint = 'BLOQUEADA';
    end if;
    if coalesce(v_parcela.valor_previsto_total, 0) <= 0 then
        raise exception 'Valor do movimento deve ser maior que zero' using errcode = '22023';
    end if;
    select * into v_banco from public.conta_bancaria cb where cb.id = v_conta_id for update;
    if not found or not financeiro.pertence_ao_perfil(v_banco.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Conta bancaria nao encontrada' using errcode = '22023', hint = 'NAO_ENCONTRADA';
    end if;
    if v_banco.status is distinct from 'ATIVO' then
        raise exception 'Conta bancaria esta inativa' using errcode = '22023';
    end if;

    update public.financiamento_parcela
       set valor_pago = valor_previsto_total, dif_apurada = 0, status = 'pago'
     where id = v_parcela.id;
    update public.financiamento set saldo_devedor_atual = v_parcela.saldo_devedor_apos_pagamento where id = v_fin.id;
    insert into public.movimento_financeiro (perfil_financeiro_id, conta_bancaria_id, tipo, valor, descricao, data_movimento,
                                             financiamento_parcela_id, origem, ajustavel, criado_em)
    values (p_perfil_id, v_banco.id, 'DEBITO', v_parcela.valor_previsto_total,
            left('Pagamento parcela ' || v_parcela.numero_parcela || ' - '
                 || coalesce(nullif(btrim(v_fin.nome), ''), 'Financiamento #' || v_fin.id), 200),
            v_data, v_parcela.id, 'FINANCIAMENTO', false, now() at time zone 'utc')
    returning id into v_mov;
    v_saldo := financeiro.atualizar_saldo_conta(v_banco.id);

    v_resultado := jsonb_build_object(
        'parcela', (select to_jsonb(p) || jsonb_build_object('saldo_devedor_apos_pagamento', nullif(p.saldo_devedor_apos_pagamento, 0))
                      from public.financiamento_parcela p where p.id = v_parcela.id),
        'movimento_id', v_mov, 'conta_bancaria_id', v_banco.id, 'conta_nome', v_banco.nome, 'saldo_conta', v_saldo,
        'saldo_devedor_atual', v_parcela.saldo_devedor_apos_pagamento);
    insert into financeiro.operacao_despesa (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'pagar_parcela_financiamento', v_resultado);
    return v_resultado;
end
$$;

-- POST /api/financiamentos/parcelas/<id>/estornar-pagamento. p_dados: data_estorno (YYYY-MM-DD), motivo.
create function financeiro.estornar_parcela_financiamento(p_perfil_id integer, p_parcela_id integer, p_dados jsonb,
                                                          p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_repetida  jsonb;
    v_parcela   public.financiamento_parcela;
    v_fin       public.financiamento;
    v_bloqueio  text;
    v_ultima    integer;
    v_original  public.movimento_financeiro;
    v_motivo    text;
    v_data      date;
    v_saldo_dev numeric;
    v_estorno   integer;
    v_saldo     numeric;
    v_resultado jsonb;
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    v_repetida := financeiro.operacao_repetida(p_perfil_id, p_chave, 'estornar_parcela_financiamento');
    if v_repetida is not null then
        return v_repetida;
    end if;

    perform financeiro.exigir_pagamento_novo(p_perfil_id);
    v_parcela := financeiro.travar_parcela_financiamento(p_perfil_id, p_parcela_id);
    if v_parcela.status is distinct from 'pago' then
        raise exception 'Apenas parcelas pagas podem ser estornadas.' using errcode = '22023', hint = 'NAO_PAGA';
    end if;
    select * into v_fin from public.financiamento f where f.id = v_parcela.financiamento_id;
    v_bloqueio := financeiro.bloqueio_da_parcela(v_parcela, v_fin);
    if v_bloqueio is not null then
        raise exception '%', v_bloqueio using errcode = '22023', hint = 'BLOQUEADA';
    end if;
    select max(p.numero_parcela) into v_ultima from public.financiamento_parcela p
     where p.financiamento_id = v_parcela.financiamento_id and p.status = 'pago'
       and financeiro.pertence_ao_perfil(p.perfil_financeiro_id, p_perfil_id);
    if v_ultima > v_parcela.numero_parcela then
        raise exception 'Existe uma parcela paga mais recente (numero %). Estorne a partir da parcela mais recente para preservar a cadeia de saldo devedor.',
            v_ultima using errcode = '22023', hint = 'NAO_E_A_ULTIMA';
    end if;
    select * into v_original from public.movimento_financeiro m
     where m.financiamento_parcela_id = v_parcela.id and m.origem = 'FINANCIAMENTO' and m.tipo = 'DEBITO'
     order by m.id desc limit 1;
    if not found then
        raise exception 'Nao foi possivel estornar porque o movimento financeiro original nao foi encontrado.'
            using errcode = '22023', hint = 'SEM_MOVIMENTO';
    end if;
    if exists (select 1 from public.movimento_financeiro e
                where e.origem = 'ESTORNO_FINANCIAMENTO'
                  and (e.movimento_original_id = v_original.id
                       or (e.movimento_original_id is null and e.financiamento_parcela_id = v_parcela.id))) then
        raise exception 'Este pagamento/recebimento ja foi estornado.' using errcode = '22023', hint = 'JA_ESTORNADO';
    end if;
    if v_original.conta_bancaria_id is null then
        raise exception 'Movimento original nao possui conta bancaria vinculada.' using errcode = '22023', hint = 'SEM_MOVIMENTO';
    end if;
    if coalesce(v_original.valor, 0) <= 0 then
        raise exception 'Valor do movimento original invalido para estorno.' using errcode = '22023', hint = 'SEM_MOVIMENTO';
    end if;
    v_motivo := btrim(coalesce(p_dados ->> 'motivo', ''));
    if v_motivo = '' then
        raise exception 'Motivo do estorno e obrigatorio.' using errcode = '22023';
    end if;
    if length(v_motivo) > 500 then
        raise exception 'Motivo do estorno: ate 500 caracteres.' using errcode = '22023';
    end if;
    if btrim(coalesce(p_dados ->> 'data_estorno', '')) = '' then
        raise exception 'Data do estorno e obrigatoria.' using errcode = '22023';
    end if;
    if btrim(p_dados ->> 'data_estorno') !~ '^\d{4}-\d{2}-\d{2}$' then
        raise exception 'Formato de data_estorno invalido. Use YYYY-MM-DD.' using errcode = '22023';
    end if;
    begin
        v_data := btrim(p_dados ->> 'data_estorno')::date;
    exception when invalid_datetime_format or datetime_field_overflow then
        raise exception 'Formato de data_estorno invalido. Use YYYY-MM-DD.' using errcode = '22023';
    end;
    perform 1 from public.conta_bancaria cb where cb.id = v_original.conta_bancaria_id for update;

    insert into public.movimento_financeiro (perfil_financeiro_id, conta_bancaria_id, tipo, valor, descricao, data_movimento,
                                             financiamento_parcela_id, origem, ajustavel, movimento_original_id, criado_em)
    values (coalesce(v_original.perfil_financeiro_id, p_perfil_id), v_original.conta_bancaria_id, 'CREDITO', v_original.valor,
            left('Estorno de pagamento da parcela ' || v_parcela.numero_parcela || ' - '
                 || coalesce(nullif(btrim(v_fin.nome), ''), 'Financiamento #' || v_fin.id), 200),
            v_data, v_parcela.id, 'ESTORNO_FINANCIAMENTO', false, v_original.id, now() at time zone 'utc')
    returning id into v_estorno;
    v_saldo := financeiro.atualizar_saldo_conta(v_original.conta_bancaria_id);
    if v_parcela.numero_parcela > 1 then
        select p.saldo_devedor_apos_pagamento into v_saldo_dev from public.financiamento_parcela p
         where p.financiamento_id = v_fin.id and p.numero_parcela = v_parcela.numero_parcela - 1
         order by p.id limit 1;
    end if;
    v_saldo_dev := coalesce(v_saldo_dev, v_fin.valor_financiado);
    update public.financiamento set saldo_devedor_atual = v_saldo_dev where id = v_fin.id;
    update public.financiamento_parcela set status = 'pendente', valor_pago = 0, dif_apurada = 0 where id = v_parcela.id;

    v_resultado := jsonb_build_object('parcela_id', v_parcela.id, 'movimento_estorno_id', v_estorno, 'status', 'pendente',
                                      'valor_estornado', v_original.valor, 'saldo_devedor_atual', v_saldo_dev,
                                      'movimento_original_id', v_original.id, 'data_estorno', v_data, 'motivo', v_motivo,
                                      'conta_bancaria_id', v_original.conta_bancaria_id, 'saldo_conta', v_saldo);
    insert into financeiro.operacao_despesa (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'estornar_parcela_financiamento', v_resultado);
    return v_resultado;
end
$$;

revoke execute on function financeiro.bloqueio_da_parcela(public.financiamento_parcela, public.financiamento)
    from public, anon, authenticated;
revoke execute on function financeiro.travar_parcela_financiamento(integer, integer) from public, anon, authenticated;
revoke execute on function financeiro.pagar_parcela_financiamento(integer, integer, jsonb, uuid) from public, anon;
revoke execute on function financeiro.estornar_parcela_financiamento(integer, integer, jsonb, uuid) from public, anon;
grant execute on function financeiro.pagar_parcela_financiamento(integer, integer, jsonb, uuid) to authenticated;
grant execute on function financeiro.estornar_parcela_financiamento(integer, integer, jsonb, uuid) to authenticated;
