-- FIN-REGULARIZACAO-HISTORICO-01 (opcao 1, decidida pelo titular em 30/10/2026): pagamento historico SEM movimento.
--
-- Encerra o historico operacional de um perfil ate uma competencia ja passada: despesas, faturas de cartao e parcelas de
-- financiamento PENDENTES ate o corte passam a pagas, com a data de pagamento = vencimento, sem movimento bancario, sem
-- alterar saldo de conta e sem alterar o saldo devedor do financiamento (o historico estimado nao e fonte do saldo; o
-- saldo real vem do ajuste de saldo). Para o sistema, despesa e fatura pagas sao status_pagamento = 'Pago'
-- (financeiro.despesa_efetivada, financeiro.fatura_esta_paga); a parcela, status = 'pago'.
-- Elegivel: pendente, sem data de pagamento, sem movimento algum, competencia <= corte. Fora: o que ja esta pago, de
-- outubro em diante, de outro perfil, e a despesa de item pago por cartao que ja tem compra na fatura da mesma
-- competencia (o gasto e a fatura; pagar as duas contaria duas vezes).
-- Auditoria por item (financeiro.regularizacao_historica, com o estado anterior) e reversao do lote, so se nada mudou.
-- Nenhum dado existente e alterado por esta migration. Reversao: supabase/reversao/20261205090000_regularizacao_historica_anterior.sql.

create table financeiro.regularizacao_historica (
    id                       bigserial   primary key,
    lote                     uuid        not null,
    perfil_financeiro_id     integer     not null,
    conta_id                 integer     not null,
    tipo                     text        not null check (tipo in ('DESPESA', 'FATURA', 'PARCELA')),
    financiamento_parcela_id integer,
    competencia              date        not null,
    descricao                text,
    valor                    numeric(12, 2),
    data_pagamento           date        not null,
    anterior                 jsonb       not null,
    registrado_por           uuid        not null,
    registrado_em            timestamptz not null default now(),
    revertido_em             timestamptz,
    revertido_por            uuid
);

create unique index regularizacao_historica_conta_vigente on financeiro.regularizacao_historica (conta_id)
    where revertido_em is null;
create index regularizacao_historica_lote on financeiro.regularizacao_historica (lote);

comment on table financeiro.regularizacao_historica is
    'FIN-REGULARIZACAO-HISTORICO-01: despesa, fatura ou parcela dada como paga por regularizacao historica (sem movimento bancario), com o estado anterior para a reversao.';

alter table financeiro.regularizacao_historica enable row level security;
alter table financeiro.regularizacao_historica force row level security;
revoke all on financeiro.regularizacao_historica from public, anon, authenticated;

-- Plano: os itens elegiveis (em ordem cronologica) e os que ficam fora por estarem representados pela fatura. Interna.
create function financeiro.plano_regularizacao_historica(p_perfil_id integer, p_ate date)
    returns jsonb
    language sql
    stable
    security definer
    set search_path = ''
as $$
    with base as (
        select c.*, case when coalesce(c.is_fatura_cartao, false) then 'FATURA'
                         when c.financiamento_parcela_id is not null then 'PARCELA' else 'DESPESA' end as tipo,
               coalesce(lower(d.meio_pagamento), '') = 'cartao'
               and exists (select 1 from public.lancamento_agregado l
                            where l.item_despesa_id = c.item_despesa_id and l.perfil_financeiro_id = c.perfil_financeiro_id
                              and date_trunc('month', l.mes_fatura) = date_trunc('month', c.mes_referencia)) as na_fatura
          from public.conta c
          left join public.item_despesa d on d.id = c.item_despesa_id
         where c.perfil_financeiro_id = p_perfil_id and c.mes_referencia <= p_ate
           and c.status_pagamento = 'Pendente' and c.data_pagamento is null
           and coalesce(c.status_fatura, '') <> 'PAGA'
           and not exists (select 1 from public.movimento_financeiro m where m.conta_id = c.id)
           and not exists (select 1 from financeiro.regularizacao_historica r where r.conta_id = c.id and r.revertido_em is null)
           and (c.financiamento_parcela_id is null
                or exists (select 1 from public.financiamento_parcela p
                            where p.id = c.financiamento_parcela_id and lower(coalesce(p.status, '')) = 'pendente'
                              and not exists (select 1 from financeiro.parcela_historica h where h.parcela_id = p.id)
                              and not exists (select 1 from public.movimento_financeiro m where m.financiamento_parcela_id = p.id)))
    )
    select jsonb_build_object(
        'itens', coalesce((select jsonb_agg(jsonb_build_object(
                     'conta_id', b.id, 'tipo', b.tipo, 'competencia', to_char(b.mes_referencia, 'YYYY-MM'),
                     'descricao', b.descricao, 'valor', coalesce(b.valor, 0),
                     'data_pagamento', coalesce(b.data_vencimento, b.mes_referencia), 'financiamento_parcela_id', b.financiamento_parcela_id)
                     order by b.mes_referencia, coalesce(b.data_vencimento, b.mes_referencia), b.id)
                    from base b where not b.na_fatura), '[]'::jsonb),
        'representadas_na_fatura', coalesce((select jsonb_agg(jsonb_build_object(
                     'conta_id', b.id, 'competencia', to_char(b.mes_referencia, 'YYYY-MM'), 'descricao', b.descricao,
                     'valor', coalesce(b.valor, 0)) order by b.mes_referencia, b.id)
                    from base b where b.na_fatura), '[]'::jsonb))
$$;

-- POST (sem tela): regularizacao historica do perfil ate a competencia informada ('YYYY-MM', anterior ao mes corrente).
-- Sem 'confirmar': so o plano (nada e gravado). Com 'confirmar': exige 'esperado' {quantidade, valor} igual ao plano
-- (o que foi conferido e o que e gravado) e grava em ordem cronologica, item a item, numa transacao. Idempotente pela
-- chave. So quem gere o perfil e com o escritor NOVO.
create function financeiro.regularizar_historico(p_perfil_id integer, p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_repetida  jsonb;
    v_comp      text := btrim(coalesce(p_dados ->> 'ate_competencia', ''));
    v_ate       date;
    v_plano     jsonb;
    v_itens     jsonb;
    v_item      jsonb;
    v_qtd       integer;
    v_total     numeric;
    v_lote      uuid := gen_random_uuid();
    v_conta     public.conta;
    v_parcela   public.financiamento_parcela;
    v_resumo    jsonb;
    v_resultado jsonb;
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if v_comp !~ '^\d{4}-(0[1-9]|1[0-2])$' then
        raise exception 'Informe ate_competencia no formato AAAA-MM' using errcode = '22023';
    end if;
    v_ate := to_date(v_comp || '-01', 'YYYY-MM-DD');
    if v_ate >= date_trunc('month', financeiro.hoje_brasilia())::date then
        raise exception 'A regularizacao historica so vale para competencias ja encerradas (anteriores a %)',
            to_char(financeiro.hoje_brasilia(), 'MM/YYYY') using errcode = '22023', hint = 'COMPETENCIA_ABERTA';
    end if;
    perform financeiro.exigir_pagamento_novo(p_perfil_id);
    perform pg_advisory_xact_lock(20261123, p_perfil_id);
    v_plano := financeiro.plano_regularizacao_historica(p_perfil_id, v_ate);
    v_itens := v_plano -> 'itens';
    v_qtd := jsonb_array_length(v_itens);
    select coalesce(sum((x ->> 'valor')::numeric), 0) into v_total from jsonb_array_elements(v_itens) x;
    select jsonb_build_object(
               'por_tipo', coalesce((select jsonb_object_agg(t, jsonb_build_object('quantidade', n, 'valor', s))
                                       from (select x ->> 'tipo' t, count(*) n, sum((x ->> 'valor')::numeric) s
                                               from jsonb_array_elements(v_itens) x group by 1) a), '{}'::jsonb),
               'por_competencia', coalesce((select jsonb_object_agg(m, jsonb_build_object('quantidade', n, 'valor', s) order by m)
                                              from (select x ->> 'competencia' m, count(*) n, sum((x ->> 'valor')::numeric) s
                                                      from jsonb_array_elements(v_itens) x group by 1) a), '{}'::jsonb))
      into v_resumo;
    if not coalesce((p_dados ->> 'confirmar')::boolean, false) then
        return jsonb_build_object('confirmado', false, 'ate_competencia', v_comp, 'quantidade', v_qtd, 'valor', v_total,
                                  'resumo', v_resumo, 'itens', v_itens,
                                  'representadas_na_fatura', v_plano -> 'representadas_na_fatura');
    end if;

    if p_chave is null then
        raise exception 'Chave da operacao obrigatoria' using errcode = '22023';
    end if;
    v_repetida := financeiro.operacao_repetida(p_perfil_id, p_chave, 'regularizar_historico');
    if v_repetida is not null then
        return v_repetida;
    end if;
    if (p_dados -> 'esperado' ->> 'quantidade')::integer is distinct from v_qtd
       or (p_dados -> 'esperado' ->> 'valor')::numeric is distinct from v_total then
        raise exception 'O plano mudou (agora % itens, R$ %): confira de novo antes de confirmar', v_qtd, v_total
            using errcode = '22023', hint = 'PLANO_MUDOU';
    end if;
    for v_item in select x from jsonb_array_elements(v_itens) x loop
        select * into v_conta from public.conta c where c.id = (v_item ->> 'conta_id')::integer for update;
        if v_conta.status_pagamento <> 'Pendente' or v_conta.data_pagamento is not null
           or exists (select 1 from public.movimento_financeiro m where m.conta_id = v_conta.id) then
            raise exception 'Despesa % (%) mudou durante a regularizacao', v_conta.id, v_conta.descricao
                using errcode = '22023', hint = 'PLANO_MUDOU';
        end if;
        v_parcela := null;
        if v_conta.financiamento_parcela_id is not null then
            select * into v_parcela from public.financiamento_parcela p where p.id = v_conta.financiamento_parcela_id for update;
        end if;
        insert into financeiro.regularizacao_historica (lote, perfil_financeiro_id, conta_id, tipo, financiamento_parcela_id,
                                                        competencia, descricao, valor, data_pagamento, anterior, registrado_por)
        values (v_lote, p_perfil_id, v_conta.id, v_item ->> 'tipo', v_parcela.id, v_conta.mes_referencia, v_conta.descricao,
                v_conta.valor, (v_item ->> 'data_pagamento')::date,
                jsonb_build_object('status_pagamento', v_conta.status_pagamento, 'data_pagamento', v_conta.data_pagamento,
                                   'parcela', case when v_parcela.id is null then null else jsonb_build_object(
                                       'status', v_parcela.status, 'valor_pago', v_parcela.valor_pago,
                                       'dif_apurada', v_parcela.dif_apurada) end),
                (select auth.uid()));
        update public.conta set status_pagamento = 'Pago', data_pagamento = (v_item ->> 'data_pagamento')::date
         where id = v_conta.id;
        if v_parcela.id is not null then
            -- Parcela quitada no historico pelo valor previsto (estimado); o saldo devedor NAO e recalculado.
            update public.financiamento_parcela set status = 'pago', valor_pago = valor_previsto_total, dif_apurada = 0
             where id = v_parcela.id;
        end if;
    end loop;
    v_resultado := jsonb_build_object('confirmado', true, 'lote', v_lote, 'ate_competencia', v_comp, 'quantidade', v_qtd,
                                      'valor', v_total, 'resumo', v_resumo,
                                      'representadas_na_fatura', v_plano -> 'representadas_na_fatura');
    insert into financeiro.operacao_despesa (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'regularizar_historico', v_resultado);
    return v_resultado;
end
$$;

-- Reversao de um lote: so se cada item continua exatamente como a regularizacao o deixou (pago na data registrada, sem
-- movimento; parcela paga pelo valor previsto). Tudo ou nada. Idempotente pela chave.
create function financeiro.reverter_regularizacao_historica(p_perfil_id integer, p_lote uuid, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_repetida  jsonb;
    v_r         financeiro.regularizacao_historica;
    v_conta     public.conta;
    v_parcela   public.financiamento_parcela;
    v_n         integer := 0;
    v_resultado jsonb;
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if p_chave is null then
        raise exception 'Chave da operacao obrigatoria' using errcode = '22023';
    end if;
    perform financeiro.exigir_pagamento_novo(p_perfil_id);
    perform pg_advisory_xact_lock(20261123, p_perfil_id);
    v_repetida := financeiro.operacao_repetida(p_perfil_id, p_chave, 'reverter_regularizacao_historica');
    if v_repetida is not null then
        return v_repetida;
    end if;
    for v_r in select * from financeiro.regularizacao_historica r
                where r.lote = p_lote and r.perfil_financeiro_id = p_perfil_id and r.revertido_em is null
                order by r.id desc for update loop
        select * into v_conta from public.conta c where c.id = v_r.conta_id for update;
        if not found or v_conta.status_pagamento <> 'Pago' or v_conta.data_pagamento is distinct from v_r.data_pagamento
           or exists (select 1 from public.movimento_financeiro m where m.conta_id = v_conta.id) then
            raise exception 'Despesa % mudou depois da regularizacao: reversao recusada', v_r.conta_id
                using errcode = '22023', hint = 'ITEM_ALTERADO';
        end if;
        update public.conta set status_pagamento = v_r.anterior ->> 'status_pagamento',
                                data_pagamento = (v_r.anterior ->> 'data_pagamento')::date
         where id = v_conta.id;
        if v_r.financiamento_parcela_id is not null then
            select * into v_parcela from public.financiamento_parcela p where p.id = v_r.financiamento_parcela_id for update;
            if v_parcela.status <> 'pago' or v_parcela.valor_pago is distinct from v_parcela.valor_previsto_total
               or exists (select 1 from public.movimento_financeiro m where m.financiamento_parcela_id = v_parcela.id) then
                raise exception 'Parcela % mudou depois da regularizacao: reversao recusada', v_parcela.numero_parcela
                    using errcode = '22023', hint = 'ITEM_ALTERADO';
            end if;
            update public.financiamento_parcela
               set status = v_r.anterior -> 'parcela' ->> 'status',
                   valor_pago = (v_r.anterior -> 'parcela' ->> 'valor_pago')::numeric,
                   dif_apurada = (v_r.anterior -> 'parcela' ->> 'dif_apurada')::numeric
             where id = v_parcela.id;
        end if;
        update financeiro.regularizacao_historica set revertido_em = now(), revertido_por = (select auth.uid()) where id = v_r.id;
        v_n := v_n + 1;
    end loop;
    if v_n = 0 then
        raise exception 'Lote de regularizacao nao encontrado (ou ja revertido) neste perfil' using errcode = '22023';
    end if;
    v_resultado := jsonb_build_object('lote', p_lote, 'revertidos', v_n);
    insert into financeiro.operacao_despesa (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'reverter_regularizacao_historica', v_resultado);
    return v_resultado;
end
$$;

revoke execute on function financeiro.plano_regularizacao_historica(integer, date) from public, anon, authenticated;
revoke execute on function financeiro.regularizar_historico(integer, jsonb, uuid) from public, anon;
revoke execute on function financeiro.reverter_regularizacao_historica(integer, uuid, uuid) from public, anon;
grant execute on function financeiro.regularizar_historico(integer, jsonb, uuid) to authenticated;
grant execute on function financeiro.reverter_regularizacao_historica(integer, uuid, uuid) to authenticated;
