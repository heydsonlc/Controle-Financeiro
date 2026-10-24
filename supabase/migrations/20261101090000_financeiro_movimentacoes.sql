-- FIN-MOVIMENTACOES-1 — pagamento de despesas comuns, recebimento de receitas, estornos e movimentos do mes.
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261101090000).
-- Validada em cluster local descartavel (tests/test_movimentacoes.py). Docs: docs/FIN_MOVIMENTACOES_1.md.
--
-- Um motor so (o do FIN-CARTOES-PAGAMENTO-1): movimentos em public.movimento_financeiro, saldo pelos movimentos
-- (financeiro.atualizar_saldo_conta), escritor unico por perfil (financeiro.exigir_pagamento_novo), chave de
-- idempotencia (operacao_despesa / operacao_receita), ordem de travas chave -> perfil -> registro -> conta bancaria
-- -> movimento. Nenhuma tabela nova.
-- Regras do Flask reaproveitadas (despesas.marcar_como_pago / estornar_pagamento, receitas.criar_realizada /
-- estornar_realizada), nas mesmas tabelas e origens (DESPESA, ESTORNO_DESPESA, RECEITA, ESTORNO_RECEITA):
-- - despesa: debito na conta, conta 'Pago' com valor = pago; estorno = credito ligado ao debito, conta 'Pendente';
-- - receita: cada recebimento e um registro (receita_realizada) com credito; varios se acumulam na previsao
--   (PARCIAL ate o previsto: semantica mantida por decisao do titular); estorno = debito ligado ao credito.
-- Correcoes em relacao ao Flask: recebimento e credito na MESMA transacao (o Flask grava o recebimento antes do
-- movimento); a identidade do estorno e o movimento original (pagar, estornar, pagar e estornar de novo funciona);
-- o estorno da despesa devolve o valor devido original (o Flask deixa o valor pago); valor de despesa diferente do
-- devido so classificado e justificado; recebimento acima do que falta so justificado.
-- Fora daqui (continuam no Flask): parcelas de consorcio e de financiamento, faturas (tela de cartoes), receitas
-- pontuais sem previsao. financeiro.pagamento_fatura passa a guardar tambem os detalhes do pagamento de despesa
-- comum (fatura_id = public.conta.id; valor_executado = valor devido no pagamento).
-- Nenhum dado existente e alterado.

comment on table financeiro.pagamento_fatura is
    'FIN-CARTOES-PAGAMENTO-1 / FIN-MOVIMENTACOES-1: valor devido no pagamento, ajuste justificado, responsavel e '
    'estorno de cada pagamento de conta (fatura de cartao ou despesa comum; fatura_id = public.conta.id; identidade = '
    'movimento de debito). Origem FLASK: pagamento do Flask estornado pelo novo aplicativo.';

-- 1. Internas ------------------------------------------------------------------------------------------------------

-- Debito vigente de uma conta (despesa): o mais recente da origem, sem credito que o referencie.
create function financeiro.debito_vigente(p_conta_id integer, p_origem text)
    returns integer
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select m.id from public.movimento_financeiro m
     where m.conta_id = p_conta_id and m.tipo = 'DEBITO' and m.origem = p_origem
       and not exists (select 1 from public.movimento_financeiro e
                        where e.movimento_original_id = m.id and e.tipo = 'CREDITO')
     order by m.id desc limit 1
$$;
revoke execute on function financeiro.debito_vigente(integer, text) from public, anon, authenticated;

-- Por que a despesa nao e paga aqui (NULL = pode). Faturas tem tela propria; consorcio e financiamento sincronizam
-- os seus modulos no Flask.
create function financeiro.bloqueio_do_pagamento(p_conta_id integer)
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
revoke execute on function financeiro.bloqueio_do_pagamento(integer) from public, anon, authenticated;

-- Recebido da previsao como receitas_do_mes: mesma fonte e competencia, sem estornos nem previsao de consorcio.
create function financeiro.recebido_da_previsao(p_orcamento_id integer)
    returns numeric
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select coalesce(sum(r.valor_recebido), 0)
      from public.receita_orcamento o
      join public.receita_realizada r on r.item_receita_id = o.item_receita_id
       and date_trunc('month', r.mes_referencia::timestamp) = date_trunc('month', o.mes_referencia::timestamp)
     where o.id = p_orcamento_id
       and financeiro.pertence_ao_perfil(r.perfil_financeiro_id, coalesce(o.perfil_financeiro_id,
               (select p.id from public.perfil_financeiro p where p.nome = 'Pessoal' order by p.id limit 1)))
       and not financeiro.receita_estornada(r.id)
       and not (coalesce(r.observacoes, '') ~ 'consorcio_id=[0-9]+' and r.conta_bancaria_id is null)
$$;
revoke execute on function financeiro.recebido_da_previsao(integer) from public, anon, authenticated;

-- Contas bancarias ativas do perfil com saldo pelos movimentos (para os formularios). Interna.
create function financeiro.contas_ativas_com_saldo(p_perfil_id integer)
    returns jsonb
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select coalesce(jsonb_agg(jsonb_build_object('id', cb.id, 'nome', cb.nome, 'instituicao', cb.instituicao,
                                                 'saldo', financeiro.saldo_da_conta(cb.id)) order by cb.nome, cb.id), '[]'::jsonb)
      from public.conta_bancaria cb
     where cb.status = 'ATIVO' and financeiro.pertence_ao_perfil(cb.perfil_financeiro_id, p_perfil_id)
$$;
revoke execute on function financeiro.contas_ativas_com_saldo(integer) from public, anon, authenticated;

-- Conta bancaria do perfil e ativa, travada (ordem global: depois do registro, antes do movimento). Interna.
create function financeiro.travar_conta_bancaria(p_perfil_id integer, p_conta_bancaria_id integer)
    returns public.conta_bancaria
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_conta public.conta_bancaria;
begin
    if p_conta_bancaria_id is null then
        raise exception 'Selecione a conta bancaria' using errcode = '22023';
    end if;
    select * into v_conta from public.conta_bancaria cb where cb.id = p_conta_bancaria_id for update;
    if not found or not financeiro.pertence_ao_perfil(v_conta.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Conta bancaria nao encontrada neste perfil' using errcode = '22023';
    end if;
    if v_conta.status is distinct from 'ATIVO' then
        raise exception 'Conta bancaria inativa' using errcode = '22023';
    end if;
    return v_conta;
end
$$;
revoke execute on function financeiro.travar_conta_bancaria(integer, integer) from public, anon, authenticated;

-- 2. Despesa comum -------------------------------------------------------------------------------------------------

create function financeiro.dados_pagamento_despesa(p_perfil_id integer, p_conta_id integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_conta    public.conta;
    v_paga     boolean;
    v_bloqueio text;
    v_gerir    boolean;
    v_novo     boolean;
    v_vigente  integer;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    select * into v_conta from public.conta c where c.id = p_conta_id;
    if not found or not financeiro.pertence_ao_perfil(v_conta.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Despesa nao encontrada neste perfil' using errcode = '42501';
    end if;
    v_paga := v_conta.status_pagamento = 'Pago';
    v_bloqueio := financeiro.bloqueio_do_pagamento(v_conta.id);
    v_gerir := financeiro.pode_gerir_perfil(p_perfil_id);
    v_novo := financeiro.gerador_do_perfil(p_perfil_id) = 'NOVO';
    v_vigente := financeiro.debito_vigente(v_conta.id, 'DESPESA');
    return jsonb_build_object(
        'despesa', jsonb_build_object('id', v_conta.id, 'descricao', v_conta.descricao, 'valor', v_conta.valor,
                                      'data_vencimento', v_conta.data_vencimento, 'paga', v_paga,
                                      'data_pagamento', v_conta.data_pagamento, 'bloqueio', v_bloqueio),
        'contas', financeiro.contas_ativas_com_saldo(p_perfil_id),
        'pagamentos', coalesce((
            select jsonb_agg(jsonb_build_object(
                       'movimento_id', m.id, 'data_pagamento', m.data_movimento, 'valor_pago', m.valor,
                       'conta_bancaria_id', m.conta_bancaria_id, 'conta_nome', cb.nome, 'valor_devido', p.valor_executado,
                       'tipo_ajuste', p.tipo_ajuste, 'justificativa', p.justificativa, 'origem', coalesce(p.origem, 'FLASK'),
                       'vigente', coalesce(m.id = v_vigente, false) and v_paga,
                       'estorno', case when e.id is null then null else jsonb_build_object(
                           'movimento_id', e.id, 'data', e.data_movimento, 'valor', e.valor, 'motivo', p.estorno_motivo) end)
                   order by m.id)
              from public.movimento_financeiro m
              left join public.conta_bancaria cb on cb.id = m.conta_bancaria_id
              left join financeiro.pagamento_fatura p on p.movimento_id = m.id
              left join lateral (select x.id, x.data_movimento, x.valor from public.movimento_financeiro x
                                  where x.movimento_original_id = m.id and x.tipo = 'CREDITO' order by x.id limit 1) e on true
             where m.conta_id = v_conta.id and m.tipo = 'DEBITO' and m.origem = 'DESPESA'), '[]'::jsonb),
        'sistema', case when v_novo then 'NOVO' else 'FLASK' end,
        'pode_pagar', v_gerir and v_novo and v_bloqueio is null and not v_paga and coalesce(v_conta.valor, 0) > 0,
        'pode_estornar', v_gerir and v_novo and v_bloqueio is null and v_paga and v_vigente is not null);
end
$$;

-- Pagamento integral. p_dados: conta_bancaria_id, data_pagamento, valor_pago, valor_devido (o que o usuario viu) e,
-- se diferente, tipo_ajuste (JUROS se maior, DESCONTO se menor, AJUSTE) com justificativa.
create function financeiro.pagar_despesa(p_perfil_id integer, p_conta_id integer, p_dados jsonb, p_chave uuid)
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

-- Estorno do pagamento vigente (p_movimento_id: o debito). Credito ligado a ele; a despesa volta a 'Pendente' com o
-- valor devido original (quando o pagamento foi registrado aqui).
create function financeiro.estornar_pagamento_despesa(p_perfil_id integer, p_conta_id integer, p_movimento_id integer,
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

-- 3. Receita -------------------------------------------------------------------------------------------------------

-- Previsao do perfil e o que permite (bloqueio NULL = pode receber). Interna.
create function financeiro.bloqueio_do_recebimento(p_orcamento_id integer)
    returns text
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select case when o.id is null then 'Previsao inexistente'
                when financeiro.fonte_de_outro_modulo(o.item_receita_id) then 'Fonte do modulo de consorcios: fica no sistema atual'
                when o.valor_esperado = 0 and coalesce(o.observacoes, '') ilike 'Removid%' then 'Previsao removida' end
      from (select 1) x left join public.receita_orcamento o on o.id = p_orcamento_id
$$;
revoke execute on function financeiro.bloqueio_do_recebimento(integer) from public, anon, authenticated;

create function financeiro.dados_recebimento_receita(p_perfil_id integer, p_orcamento_id integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_prev     public.receita_orcamento;
    v_recebido numeric;
    v_bloqueio text;
    v_gerir    boolean;
    v_novo     boolean;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    select * into v_prev from public.receita_orcamento o where o.id = p_orcamento_id;
    if not found or not financeiro.pertence_ao_perfil(v_prev.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Receita nao encontrada neste perfil' using errcode = '42501';
    end if;
    v_recebido := financeiro.recebido_da_previsao(v_prev.id);
    v_bloqueio := financeiro.bloqueio_do_recebimento(v_prev.id);
    v_gerir := financeiro.pode_gerir_perfil(p_perfil_id);
    v_novo := financeiro.gerador_do_perfil(p_perfil_id) = 'NOVO';
    return jsonb_build_object(
        'receita', jsonb_build_object('id', v_prev.id, 'item_receita_id', v_prev.item_receita_id,
                                      'nome', (select i.nome from public.item_receita i where i.id = v_prev.item_receita_id),
                                      'competencia', v_prev.mes_referencia, 'valor_previsto', v_prev.valor_esperado,
                                      'valor_recebido', v_recebido, 'falta', greatest(v_prev.valor_esperado - v_recebido, 0),
                                      'bloqueio', v_bloqueio,
                                      'conta_padrao', (select i.conta_bancaria_id from public.item_receita i
                                                        where i.id = v_prev.item_receita_id)),
        'contas', financeiro.contas_ativas_com_saldo(p_perfil_id),
        'recebimentos', coalesce((
            select jsonb_agg(jsonb_build_object(
                       'id', r.id, 'data_recebimento', r.data_recebimento, 'valor', r.valor_recebido,
                       'conta_nome', cb.nome, 'observacoes', r.observacoes,
                       'estornado', financeiro.receita_estornada(r.id),
                       'pode_estornar', v_gerir and v_novo and not financeiro.receita_estornada(r.id)
                                        and exists (select 1 from public.movimento_financeiro m
                                                     where m.receita_realizada_id = r.id and m.tipo = 'CREDITO'
                                                       and m.origem = 'RECEITA')) order by r.data_recebimento, r.id)
              from public.receita_realizada r
              left join public.conta_bancaria cb on cb.id = r.conta_bancaria_id
             where r.item_receita_id = v_prev.item_receita_id
               and date_trunc('month', r.mes_referencia::timestamp) = date_trunc('month', v_prev.mes_referencia::timestamp)
               and financeiro.pertence_ao_perfil(r.perfil_financeiro_id, p_perfil_id)), '[]'::jsonb),
        'sistema', case when v_novo then 'NOVO' else 'FLASK' end,
        'pode_receber', v_gerir and v_novo and v_bloqueio is null);
end
$$;

-- Recebimento. p_dados: conta_bancaria_id, data_recebimento, valor_recebido, falta (o que o usuario viu faltar) e,
-- acima do que falta, justificativa. Abaixo do que falta e recebimento parcial (a previsao fica PARCIAL).
create function financeiro.receber_receita(p_perfil_id integer, p_orcamento_id integer, p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_anterior  financeiro.operacao_receita;
    v_prev      public.receita_orcamento;
    v_banco     public.conta_bancaria;
    v_bloqueio  text;
    v_data      date;
    v_valor     numeric;
    v_visto     numeric;
    v_falta     numeric;
    v_just      text;
    v_nome      text;
    v_real      integer;
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
    select * into v_anterior from financeiro.operacao_receita o where o.chave = p_chave;
    if found then
        if v_anterior.user_id is distinct from (select auth.uid()) or v_anterior.perfil_financeiro_id <> p_perfil_id
           or v_anterior.operacao <> 'receber_receita' then
            raise exception 'Chave da operacao ja usada' using errcode = '22023';
        end if;
        return v_anterior.resultado || jsonb_build_object('repetida', true);
    end if;
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' then
        raise exception 'Dados do recebimento invalidos' using errcode = '22023';
    end if;
    begin
        v_data := (p_dados ->> 'data_recebimento')::date;
        v_valor := (p_dados ->> 'valor_recebido')::numeric;
        v_visto := (p_dados ->> 'falta')::numeric;
    exception when invalid_text_representation or datetime_field_overflow or invalid_datetime_format
                   or numeric_value_out_of_range then
        raise exception 'Dados do recebimento invalidos' using errcode = '22023';
    end;
    if v_data is null then
        raise exception 'Informe a data do recebimento' using errcode = '22023';
    end if;
    if v_valor is null or v_valor <= 0 or v_valor <> round(v_valor, 2) then
        raise exception 'Valor recebido deve ser positivo, com ate 2 casas decimais' using errcode = '22023';
    end if;

    perform financeiro.exigir_pagamento_novo(p_perfil_id);
    -- Mesma ordem de travar_previsao (editar/excluir previsao): tabela de recebimentos, depois a previsao. Um
    -- recebimento simultaneo pelo Flask nesta fonte e mes espera (ou e visto).
    lock table public.receita_realizada in share row exclusive mode;
    select * into v_prev from public.receita_orcamento o where o.id = p_orcamento_id for update;
    if not found or not financeiro.pertence_ao_perfil(v_prev.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Receita nao encontrada neste perfil' using errcode = '42501';
    end if;
    v_bloqueio := financeiro.bloqueio_do_recebimento(v_prev.id);
    if v_bloqueio is not null then
        raise exception 'Operacao bloqueada: %', v_bloqueio using errcode = '22023', hint = 'BLOQUEADA';
    end if;
    v_falta := greatest(v_prev.valor_esperado - financeiro.recebido_da_previsao(v_prev.id), 0);
    if v_visto is distinct from v_falta then
        raise exception 'O valor a receber mudou para R$ %. Confira e confirme de novo.',
            replace(to_char(v_falta, 'FM999999990.00'), '.', ',') using errcode = '22023', hint = 'VALOR_MUDOU';
    end if;
    v_just := btrim(coalesce(p_dados ->> 'justificativa', ''));
    if v_valor > v_falta and (v_just = '' or length(v_just) > 500) then
        raise exception 'Valor acima do que falta receber: a justificativa e obrigatoria (ate 500 caracteres)'
            using errcode = '22023', hint = 'JUSTIFICATIVA_OBRIGATORIA';
    end if;
    v_banco := financeiro.travar_conta_bancaria(p_perfil_id, (p_dados ->> 'conta_bancaria_id')::integer);
    select i.nome into v_nome from public.item_receita i where i.id = v_prev.item_receita_id;

    insert into public.receita_realizada (perfil_financeiro_id, item_receita_id, data_recebimento, valor_recebido,
                                         mes_referencia, conta_bancaria_id, descricao, orcamento_id, observacoes,
                                         criado_em, atualizado_em)
    values (coalesce(v_prev.perfil_financeiro_id, p_perfil_id), v_prev.item_receita_id, v_data, v_valor,
            date_trunc('month', v_prev.mes_referencia::timestamp)::date, v_banco.id,
            left(coalesce(v_nome, 'Receita') || ' ' || to_char(v_prev.mes_referencia, 'MM/YYYY'), 200), v_prev.id,
            case when v_valor > v_falta then '[ACIMA DO PREVISTO] ' || v_just else '' end,
            now() at time zone 'utc', now() at time zone 'utc')
    returning id into v_real;
    insert into public.movimento_financeiro (perfil_financeiro_id, conta_bancaria_id, tipo, valor, descricao, data_movimento,
                                             receita_realizada_id, origem, ajustavel, criado_em)
    values (p_perfil_id, v_banco.id, 'CREDITO', v_valor,
            left('Receita - ' || coalesce(v_nome, 'Receita') || ' ' || to_char(v_prev.mes_referencia, 'MM/YYYY'), 200), v_data,
            v_real, 'RECEITA', false, now() at time zone 'utc')
    returning id into v_mov;
    v_saldo := financeiro.atualizar_saldo_conta(v_banco.id);
    v_resultado := jsonb_build_object('orcamento_id', v_prev.id, 'receita_realizada_id', v_real, 'movimento_id', v_mov,
                                      'valor_recebido', v_valor, 'falta_antes', v_falta,
                                      'falta_depois', greatest(v_falta - v_valor, 0), 'data_recebimento', v_data,
                                      'conta_bancaria_id', v_banco.id, 'conta_nome', v_banco.nome, 'saldo_conta', v_saldo);
    insert into financeiro.operacao_receita (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'receber_receita', v_resultado);
    return v_resultado;
end
$$;

-- Estorno de um recebimento (cada recebimento e estornavel sozinho; o registro e o credito originais ficam).
create function financeiro.estornar_recebimento(p_perfil_id integer, p_realizada_id integer, p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_anterior  financeiro.operacao_receita;
    v_real      public.receita_realizada;
    v_original  public.movimento_financeiro;
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
    select * into v_anterior from financeiro.operacao_receita o where o.chave = p_chave;
    if found then
        if v_anterior.user_id is distinct from (select auth.uid()) or v_anterior.perfil_financeiro_id <> p_perfil_id
           or v_anterior.operacao <> 'estornar_recebimento' then
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

    perform financeiro.exigir_pagamento_novo(p_perfil_id);
    select * into v_real from public.receita_realizada r where r.id = p_realizada_id for update;
    if not found or not financeiro.pertence_ao_perfil(v_real.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Recebimento nao encontrado neste perfil' using errcode = '42501';
    end if;
    select * into v_original from public.movimento_financeiro m
     where m.receita_realizada_id = v_real.id and m.tipo = 'CREDITO' and m.origem = 'RECEITA' order by m.id desc limit 1;
    if not found then
        raise exception 'Recebimento sem movimento de credito: nada a estornar' using errcode = '22023';
    end if;
    perform 1 from public.conta_bancaria cb where cb.id = v_original.conta_bancaria_id for update;
    perform 1 from public.movimento_financeiro m where m.id = v_original.id for update;
    if financeiro.receita_estornada(v_real.id) then
        raise exception 'Este recebimento ja foi estornado' using errcode = '22023', hint = 'JA_ESTORNADO';
    end if;

    insert into public.movimento_financeiro (perfil_financeiro_id, conta_bancaria_id, tipo, valor, descricao, data_movimento,
                                             receita_realizada_id, origem, ajustavel, movimento_original_id, criado_em)
    values (coalesce(v_original.perfil_financeiro_id, p_perfil_id), v_original.conta_bancaria_id, 'DEBITO', v_original.valor,
            left('Estorno de recebimento da receita: ' || coalesce(v_real.descricao, v_real.id::text), 200), v_data,
            v_real.id, 'ESTORNO_RECEITA', false, v_original.id, now() at time zone 'utc')
    returning id into v_estorno;
    v_saldo := financeiro.atualizar_saldo_conta(v_original.conta_bancaria_id);
    update public.receita_realizada
       set observacoes = concat_ws(E'\n', nullif(observacoes, ''), '[ESTORNO] ' || v_data::text || ' — ' || v_motivo),
           atualizado_em = now() at time zone 'utc'
     where id = v_real.id;
    v_resultado := jsonb_build_object('receita_realizada_id', v_real.id, 'movimento_estorno_id', v_estorno,
                                      'movimento_original_id', v_original.id, 'valor_estornado', v_original.valor,
                                      'data_estorno', v_data, 'conta_bancaria_id', v_original.conta_bancaria_id,
                                      'saldo_conta', v_saldo);
    insert into financeiro.operacao_receita (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'estornar_recebimento', v_resultado);
    return v_resultado;
end
$$;

-- 4. Movimentos do mes (extrato simples): contas do perfil com saldo e os movimentos do mes, com a origem ligada.
create function financeiro.movimentos_do_mes(p_perfil_id integer, p_mes date)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_mes date;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if p_mes is null then
        raise exception 'Mes obrigatorio' using errcode = '22023';
    end if;
    v_mes := date_trunc('month', p_mes::timestamp)::date;
    return jsonb_build_object(
        'contas', coalesce((select jsonb_agg(jsonb_build_object('id', cb.id, 'nome', cb.nome, 'status', cb.status,
                                                                'saldo', financeiro.saldo_da_conta(cb.id)) order by cb.nome, cb.id)
                              from public.conta_bancaria cb
                             where financeiro.pertence_ao_perfil(cb.perfil_financeiro_id, p_perfil_id)), '[]'::jsonb),
        'movimentos', coalesce((
            select jsonb_agg(jsonb_build_object(
                       'id', m.id, 'data', m.data_movimento, 'descricao', m.descricao, 'tipo', m.tipo,
                       'origem', coalesce(m.origem, 'MANUAL'), 'valor', m.valor, 'conta_bancaria_id', m.conta_bancaria_id,
                       'conta_nome', cb.nome, 'estorno_de', m.movimento_original_id,
                       'referencia', coalesce(c.descricao, i.nome, rr.descricao)) order by m.data_movimento, m.id)
              from public.movimento_financeiro m
              join public.conta_bancaria cb on cb.id = m.conta_bancaria_id
              left join public.conta c on c.id = coalesce(m.conta_id, m.fatura_id)
              left join public.receita_realizada rr on rr.id = m.receita_realizada_id
              left join public.item_receita i on i.id = rr.item_receita_id
             where financeiro.pertence_ao_perfil(cb.perfil_financeiro_id, p_perfil_id)
               and m.data_movimento >= v_mes and m.data_movimento < (v_mes + interval '1 month')::date), '[]'::jsonb));
end
$$;

revoke execute on function financeiro.dados_pagamento_despesa(integer, integer) from public, anon;
revoke execute on function financeiro.pagar_despesa(integer, integer, jsonb, uuid) from public, anon;
revoke execute on function financeiro.estornar_pagamento_despesa(integer, integer, integer, jsonb, uuid) from public, anon;
revoke execute on function financeiro.dados_recebimento_receita(integer, integer) from public, anon;
revoke execute on function financeiro.receber_receita(integer, integer, jsonb, uuid) from public, anon;
revoke execute on function financeiro.estornar_recebimento(integer, integer, jsonb, uuid) from public, anon;
revoke execute on function financeiro.movimentos_do_mes(integer, date) from public, anon;
grant execute on function financeiro.dados_pagamento_despesa(integer, integer) to authenticated;
grant execute on function financeiro.pagar_despesa(integer, integer, jsonb, uuid) to authenticated;
grant execute on function financeiro.estornar_pagamento_despesa(integer, integer, integer, jsonb, uuid) to authenticated;
grant execute on function financeiro.dados_recebimento_receita(integer, integer) to authenticated;
grant execute on function financeiro.receber_receita(integer, integer, jsonb, uuid) to authenticated;
grant execute on function financeiro.estornar_recebimento(integer, integer, jsonb, uuid) to authenticated;
grant execute on function financeiro.movimentos_do_mes(integer, date) to authenticated;
