-- FIN-SALDO-PRECEDENCIA-AJUSTE-01 — precedencia do ajuste de saldo real sobre a evolucao estimada das parcelas.
--
-- Defeito: pagar (ou estornar, ou registrar como historica) uma parcela grava no contrato o saldo da paga de maior numero
-- (saldo_devedor_pelas_parcelas). Com um ajuste de saldo real ancorado nessa parcela ou depois dela, o saldo real era
-- trocado pelo saldo estimado antigo da parcela (que o ajuste nao recalcula: ele recalcula so as seguintes). Caso real:
-- ajuste de 05/10/2026 (R$ 269.524,62, parcela-base 30); pagar a parcela 30 gravaria R$ 464.285,71. A amortizacao
-- extraordinaria tinha a mesma falha na base do recalculo (saldo estimado da parcela anterior a primeira recalculada).
--
-- Regra (dado real nao e sobrescrito por evolucao estimada anterior):
-- - parcela-base do ajuste = a ultima parcela coberta pelo saldo real (a anterior a primeira recalculada), registrada em
--   financeiro.ajuste_saldo_base; o ajuste vigente e o mais recente do contrato (ele recalcula tudo depois da base);
-- - saldo do contrato: paga de maior numero <= parcela-base (ou nenhuma paga) => saldo real do ajuste; paga posterior a
--   parcela-base => cadeia das parcelas, que ja parte do saldo real (evolucao normal); amortizacoes depois da ancora;
-- - amortizacao: ancorada na parcela-base, parte do saldo real; anterior a ela, recusada (AJUSTE_POSTERIOR).
-- O pagamento continua igual (parcela paga, valor, diferenca, despesa, movimento). Sem ajuste, tudo como antes.
-- Dados: so a tabela nova, com a parcela-base de cada ajuste ja existente (deduzida; nao identificavel = a migration para).
-- Reversao: supabase/reversao/20261206090000_precedencia_ajuste_saldo_anterior.sql.

-- 1. Parcela-base de cada ajuste ----------------------------------------------------------------------------------------

create table financeiro.ajuste_saldo_base (
    ajuste_id           integer     primary key references public.financiamento_ajuste_saldo (id) on delete cascade,
    financiamento_id    integer     not null references public.financiamento (id) on delete cascade,
    numero_parcela_base integer     not null check (numero_parcela_base >= 0),
    registrado_em       timestamptz not null default now()
);

comment on table financeiro.ajuste_saldo_base is
    'FIN-SALDO-PRECEDENCIA-AJUSTE-01: parcela-base do ajuste de saldo real (a ultima parcela coberta pelo saldo real).';

alter table financeiro.ajuste_saldo_base enable row level security;
alter table financeiro.ajuste_saldo_base force row level security;
revoke all on financeiro.ajuste_saldo_base from public, anon, authenticated;

-- Ajustes ja existentes: ajustar_saldo_devedor gravou numero_parcela_base = (primeira recalculada - 1) no contrato e
-- recalculou todas as parcelas dali ao fim (pendentes, ou seria recusado). Duas deducoes independentes, que precisam
-- concordar: o contrato (so no ajuste mais recente, com data e saldo ainda os dele) e a contagem das recalculadas. A base
-- e a referencia ou a anterior a ela. Qualquer ajuste sem deducao segura: a migration para, nada e gravado.
do $$
declare
    v          record;
    v_contrato integer;
    v_contagem integer;
    v_base     integer;
begin
    for v in select a.id, a.financiamento_id, a.numero_parcela, a.data_referencia, a.saldo_devedor_real, a.parcelas_recalculadas,
                    f.numero_parcela_base, f.data_base, f.saldo_devedor_atual,
                    a.id = (select max(b.id) from public.financiamento_ajuste_saldo b where b.financiamento_id = a.financiamento_id) as ultimo,
                    (select max(p.numero_parcela) from public.financiamento_parcela p where p.financiamento_id = a.financiamento_id) as maximo
               from public.financiamento_ajuste_saldo a
               join public.financiamento f on f.id = a.financiamento_id
              order by a.id loop
        v_contrato := case when v.ultimo and v.data_base = v.data_referencia and v.saldo_devedor_atual = v.saldo_devedor_real
                           then v.numero_parcela_base end;
        v_contagem := case when coalesce(v.parcelas_recalculadas, 0) > 0 then v.maximo - v.parcelas_recalculadas end;
        v_base := coalesce(v_contrato, v_contagem);
        if v_base is null or v_base not in (v.numero_parcela - 1, v.numero_parcela)
           or (v_contrato is not null and v_contagem is not null and v_contrato <> v_contagem) then
            raise exception 'Parcela-base do ajuste de saldo % (financiamento %) nao identificavel', v.id, v.financiamento_id
                using errcode = 'P0001', hint = 'AJUSTE_SEM_BASE';
        end if;
        insert into financeiro.ajuste_saldo_base (ajuste_id, financiamento_id, numero_parcela_base, registrado_em)
        values (v.id, v.financiamento_id, v_base, now());
    end loop;
end
$$;

-- 2. Ajuste vigente -------------------------------------------------------------------------------------------------------

-- Ajuste de saldo real vigente do contrato (o mais recente): parcela-base, saldo real e data. Nenhum: zero linhas. Interna.
create function financeiro.fin_ajuste_vigente(p_financiamento_id integer)
    returns table (ajuste_id integer, numero_parcela_base integer, saldo numeric, data date)
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select a.id, b.numero_parcela_base, a.saldo_devedor_real, a.data_referencia
      from public.financiamento_ajuste_saldo a
      join financeiro.ajuste_saldo_base b on b.ajuste_id = a.id
     where a.financiamento_id = p_financiamento_id
     order by a.id desc
     limit 1
$$;
revoke execute on function financeiro.fin_ajuste_vigente(integer) from public, anon, authenticated;

-- 3. Funcoes que passam a respeitar o ajuste (texto anterior + as linhas marcadas) ---------------------------------------

create or replace function financeiro.saldo_devedor_pelas_parcelas(p_financiamento_id integer)
    returns numeric
    language sql
    stable
    security definer
    set search_path = ''
as $$
    -- FIN-SALDO-PRECEDENCIA-AJUSTE-01: a ancora e o ajuste de saldo real vigente quando a parcela-base dele e igual ou
    -- posterior a paga de maior numero (ou nao ha paga); senao, a paga. Amortizacoes depois da data da ancora.
    with paga as (select p.numero_parcela, p.saldo_devedor_apos_pagamento, p.data_vencimento from public.financiamento_parcela p
                   where p.financiamento_id = p_financiamento_id and p.status = 'pago'
                   order by p.numero_parcela desc, p.id desc limit 1),
         ajuste as (select j.saldo, j.data from financeiro.fin_ajuste_vigente(p_financiamento_id) j
                     where j.numero_parcela_base >= coalesce((select numero_parcela from paga), 0)),
         ancora as (select j.saldo, j.data from ajuste j
                    union all
                    select p.saldo_devedor_apos_pagamento, p.data_vencimento from paga p where not exists (select 1 from ajuste))
    select coalesce((select saldo from ancora),
                    (select f.valor_financiado from public.financiamento f where f.id = p_financiamento_id))
         - coalesce((select sum(a.valor) from public.financiamento_amortizacao_extra a
                      where a.financiamento_id = p_financiamento_id
                        and (not exists (select 1 from ancora) or a.data > (select data from ancora))), 0)
$$;

create or replace function financeiro.ajustar_saldo_devedor(p_perfil_id integer, p_id integer, p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_repetida   jsonb;
    v_f          public.financiamento;
    v_ref        public.financiamento_parcela;
    v_real       numeric;
    v_data       date;
    v_inicio     integer;
    v_anterior   numeric;
    v_ids        integer[];
    v_recalcular boolean := coalesce(jsonb_typeof(p_dados -> 'recalcular_parcelas_futuras') <> 'boolean'
                                     or (p_dados ->> 'recalcular_parcelas_futuras')::boolean, true);
    v_a          public.financiamento_ajuste_saldo;
    v_n          integer := 0;
    v_resultado  jsonb;
begin
    perform financeiro.exigir_escrita_financiamento(p_perfil_id);
    v_repetida := financeiro.operacao_repetida(p_perfil_id, p_chave, 'ajustar_saldo_devedor');
    if v_repetida is not null then
        return v_repetida;
    end if;
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' or p_dados = '{}'::jsonb then
        raise exception 'Dados não fornecidos' using errcode = '22023';
    end if;
    if coalesce(nullif(p_dados ->> 'parcela_referencia_id', ''), nullif(p_dados ->> 'numero_parcela', '')) is null
       or coalesce(p_dados ->> 'parcela_referencia_id', '') = '0' and coalesce(p_dados ->> 'numero_parcela', '0') = '0' then
        raise exception 'Informe parcela_referencia_id ou numero_parcela' using errcode = '22023';
    end if;
    if jsonb_typeof(coalesce(p_dados -> 'saldo_devedor_real', 'null'::jsonb)) = 'null' then
        raise exception 'saldo_devedor_real é obrigatório' using errcode = '22023';
    end if;
    v_f := financeiro.travar_financiamento(p_perfil_id, p_id);
    if nullif(p_dados ->> 'parcela_referencia_id', '') is not null and p_dados ->> 'parcela_referencia_id' <> '0' then
        select * into v_ref from public.financiamento_parcela p
         where p.id = financeiro.fin_numero(p_dados ->> 'parcela_referencia_id', 'parcela_referencia_id')::integer
           and p.financiamento_id = v_f.id;
    else
        select * into v_ref from public.financiamento_parcela p
         where p.financiamento_id = v_f.id
           and p.numero_parcela = financeiro.fin_numero(p_dados ->> 'numero_parcela', 'numero_parcela')::integer;
    end if;
    if v_ref.id is null then
        raise exception 'Parcela de referencia nao encontrada para este financiamento' using errcode = '22023';
    end if;
    v_real := financeiro.fin_numero(p_dados ->> 'saldo_devedor_real', 'saldo_devedor_real');
    if v_real <= 0 then
        raise exception 'saldo_devedor_real deve ser maior que zero' using errcode = '22023';
    end if;
    v_data := case when nullif(p_dados ->> 'data_referencia', '') is not null
                   then financeiro.fin_data(p_dados ->> 'data_referencia', 'data_referencia') else v_ref.data_vencimento end;
    if not financeiro.fin_parcela_elegivel(v_ref.id) then
        v_inicio := v_ref.numero_parcela + 1;
        v_anterior := coalesce(nullif(v_ref.saldo_devedor_apos_pagamento, 0), v_real);
    else
        v_inicio := v_ref.numero_parcela;
        v_anterior := case when v_ref.numero_parcela <= 1 then v_f.valor_financiado
                           else coalesce((select a.saldo_devedor_apos_pagamento from public.financiamento_parcela a
                                           where a.financiamento_id = v_f.id and a.numero_parcela = v_ref.numero_parcela - 1),
                                         v_f.valor_financiado) end;
    end if;
    select coalesce(array_agg(p.id order by p.numero_parcela), '{}') into v_ids from public.financiamento_parcela p
     where p.financiamento_id = v_f.id and p.numero_parcela >= v_inicio and p.status = 'pendente';
    if cardinality(v_ids) = 0 then
        raise exception 'Nao ha parcelas futuras pendentes para recalcular a partir da referencia informada' using errcode = '22023';
    end if;
    if exists (select 1 from public.financiamento_parcela p
                where p.financiamento_id = v_f.id and p.numero_parcela >= v_inicio and not financeiro.fin_parcela_elegivel(p.id)) then
        raise exception 'Existem parcelas futuras vinculadas a contas ja efetivadas. O ajuste de saldo nao pode ser aplicado automaticamente.'
            using errcode = '22023', hint = 'PARCELA_PROTEGIDA';
    end if;
    insert into public.financiamento_ajuste_saldo (perfil_financeiro_id, financiamento_id, parcela_referencia_id, numero_parcela,
                                                   data_referencia, saldo_devedor_anterior, saldo_devedor_real, diferenca,
                                                   tipo_ajuste, observacao, parcelas_recalculadas, criado_em, atualizado_em)
    values (v_f.perfil_financeiro_id, v_f.id, v_ref.id, v_ref.numero_parcela, v_data, v_anterior, v_real,
            v_real - coalesce(v_anterior, 0), coalesce(nullif(p_dados ->> 'tipo_ajuste', ''), 'ajuste_saldo_real'),
            coalesce(nullif(p_dados ->> 'observacao', ''), nullif(p_dados ->> 'observacoes', '')), 0,
            now() at time zone 'utc', now() at time zone 'utc')
    returning * into v_a;
    -- FIN-SALDO-PRECEDENCIA-AJUSTE-01: a parcela-base (a ultima coberta pelo saldo real) fica registrada com o ajuste.
    insert into financeiro.ajuste_saldo_base (ajuste_id, financiamento_id, numero_parcela_base)
    values (v_a.id, v_f.id, v_inicio - 1);
    if v_recalcular then
        if financeiro.fin_usa_sac_tr(v_f.sistema_amortizacao, v_f.indexador_saldo, v_f.modo_calculo_financiamento) then
            perform financeiro.fin_atualizar_sac_tr(v_f, v_ids, v_real, financeiro.fin_div(v_real, cardinality(v_ids)));
        else
            perform financeiro.fin_ajustar_padrao(v_f, v_ids, v_real);
        end if;
        v_n := cardinality(v_ids);
        update public.financiamento
           set prazo_remanescente_meses = v_n,
               amortizacao_mensal_atual = (select p.valor_amortizacao from public.financiamento_parcela p where p.id = v_ids[1])
         where id = v_f.id;
        update public.financiamento_ajuste_saldo set parcelas_recalculadas = v_n where id = v_a.id returning * into v_a;
    end if;
    update public.financiamento set saldo_devedor_atual = v_real, data_base = v_data, numero_parcela_base = v_inicio - 1
     where id = v_f.id;
    v_resultado := jsonb_build_object('success', true, 'message', 'Saldo devedor ajustado e parcelas futuras recalculadas.',
                                      'ajuste_id', v_a.id, 'parcelas_recalculadas', v_n, 'data', to_jsonb(v_a));
    insert into financeiro.operacao_despesa (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'ajustar_saldo_devedor', v_resultado);
    return v_resultado;
end
$$;

create or replace function financeiro.registrar_amortizacao_extra(p_perfil_id integer, p_id integer, p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_repetida  jsonb;
    v_f         public.financiamento;
    v_data      date;
    v_valor     numeric;
    v_tipo      text;
    v_campo     text;
    v_bloqueio  integer;
    v_saldo     numeric;
    v_ids       integer[];
    v_quota     numeric;
    v_primeira  public.financiamento_parcela;
    v_base      public.financiamento_parcela;
    v_ajuste    record;
    v_quitadas  integer[];
    v_removidas integer := 0;
    v_a         public.financiamento_amortizacao_extra;
    v_resultado jsonb;
begin
    perform financeiro.exigir_escrita_financiamento(p_perfil_id);
    v_repetida := financeiro.operacao_repetida(p_perfil_id, p_chave, 'registrar_amortizacao_extra');
    if v_repetida is not null then
        return v_repetida;
    end if;
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' or p_dados = '{}'::jsonb then
        raise exception 'Dados não fornecidos' using errcode = '22023';
    end if;
    foreach v_campo in array array['data', 'valor', 'tipo'] loop
        if not p_dados ? v_campo then
            raise exception '% é obrigatório', v_campo using errcode = '22023';
        end if;
    end loop;
    v_tipo := p_dados ->> 'tipo';
    if v_tipo is null or v_tipo not in ('reduzir_parcela', 'reduzir_prazo') then
        raise exception 'tipo deve ser "reduzir_parcela" ou "reduzir_prazo"' using errcode = '22023';
    end if;
    v_f := financeiro.travar_financiamento(p_perfil_id, p_id);
    v_data := financeiro.fin_data(p_dados ->> 'data', 'data');
    v_valor := financeiro.fin_numero(p_dados ->> 'valor', 'valor');
    if v_valor is null or v_valor <= 0 then
        raise exception 'Valor da amortizacao deve ser maior que zero' using errcode = '22023';
    end if;
    -- Parcelas a partir da data: nenhuma pode estar executada (Flask) nem ter despesa com movimento (Regra 1).
    select p.numero_parcela into v_bloqueio from public.financiamento_parcela p
     where p.financiamento_id = v_f.id and p.data_vencimento >= v_data and not financeiro.fin_parcela_elegivel(p.id)
     order by p.numero_parcela limit 1;
    if v_bloqueio is not null then
        raise exception 'Existem parcelas futuras vinculadas a contas ja efetivadas. A amortizacao nao pode ser aplicada automaticamente. (parcela %)',
            v_bloqueio using errcode = '22023', hint = 'PARCELA_PROTEGIDA';
    end if;
    select coalesce(array_agg(p.id order by p.numero_parcela), '{}') into v_ids from public.financiamento_parcela p
     where p.financiamento_id = v_f.id and p.data_vencimento >= v_data and p.status = 'pendente';
    -- Amortizacao fora de ordem reescreveria o efeito da posterior ja registrada: recusada.
    if exists (select 1 from public.financiamento_amortizacao_extra a where a.financiamento_id = v_f.id and a.data > v_data) then
        raise exception 'Já existe amortização extraordinária registrada com data posterior a %. Registre as amortizações em ordem cronológica.',
            to_char(v_data, 'DD/MM/YYYY') using errcode = '22023', hint = 'AMORTIZACAO_POSTERIOR';
    end if;
    -- Continuidade do saldo: a base do recalculo e o saldo apos a parcela imediatamente anterior a primeira recalculada,
    -- menos as amortizacoes ja registradas depois do vencimento dela (o Flask usa o saldo atual = saldo apos a ultima
    -- PAGA menos as amortizacoes: com parcelas pendentes antes da data, a amortizacao ordinaria delas seria descontada
    -- duas vezes). Tudo pago antes da data: igual ao Flask.
    if cardinality(v_ids) > 0 then
        select * into v_base from public.financiamento_parcela a
         where a.financiamento_id = v_f.id
           and a.numero_parcela < (select p.numero_parcela from public.financiamento_parcela p where p.id = v_ids[1])
         order by a.numero_parcela desc limit 1;
        v_saldo := coalesce(v_base.saldo_devedor_apos_pagamento, v_f.valor_financiado)
                   - coalesce((select sum(a.valor) from public.financiamento_amortizacao_extra a
                                where a.financiamento_id = v_f.id
                                  and (v_base.id is null or a.data > v_base.data_vencimento)), 0);
        -- FIN-SALDO-PRECEDENCIA-AJUSTE-01: com ajuste de saldo real vigente, a cadeia estimada nao e a base. Ancorada na
        -- parcela-base: o saldo real (menos as amortizacoes depois da data dele). Antes dela: o saldo real ja contem a
        -- amortizacao; recalcular dali reescreveria o ajuste. Recusado.
        select * into v_ajuste from financeiro.fin_ajuste_vigente(v_f.id);
        if v_ajuste.numero_parcela_base > coalesce(v_base.numero_parcela, 0) then
            raise exception 'Amortização anterior à referência do ajuste de saldo real (parcela-base %, %): o saldo real já a contém.',
                v_ajuste.numero_parcela_base, to_char(v_ajuste.data, 'DD/MM/YYYY') using errcode = '22023', hint = 'AJUSTE_POSTERIOR';
        elsif v_ajuste.numero_parcela_base = coalesce(v_base.numero_parcela, 0) then
            v_saldo := v_ajuste.saldo - coalesce((select sum(a.valor) from public.financiamento_amortizacao_extra a
                                                   where a.financiamento_id = v_f.id and a.data > v_ajuste.data), 0);
        end if;
    else
        v_saldo := coalesce(v_f.saldo_devedor_atual, financeiro.saldo_devedor_pelas_parcelas(v_f.id));
    end if;
    if v_valor > v_saldo then
        raise exception 'Valor da amortização (%) maior que o saldo devedor (%). Para quitar, use a simulação de quitação.',
            v_valor, v_saldo using errcode = '22023', hint = 'VALOR_ACIMA_DO_SALDO';
    end if;
    insert into public.financiamento_amortizacao_extra (perfil_financeiro_id, financiamento_id, data, valor, tipo, observacoes, criado_em)
    values (v_f.perfil_financeiro_id, v_f.id, v_data, v_valor, v_tipo, coalesce(p_dados ->> 'observacoes', ''), now() at time zone 'utc')
    returning * into v_a;
    -- Estado soberano (como o Flask: saldo devedor atual menos o valor)
    update public.financiamento
       set saldo_devedor_atual = coalesce(saldo_devedor_atual, financeiro.saldo_devedor_pelas_parcelas(id)) - v_valor,
           regime_pos_amortizacao = upper(v_tipo),
           amortizacao_mensal_atual = case when v_tipo = 'reduzir_parcela'
                                           then financeiro.fin_r((coalesce(saldo_devedor_atual, financeiro.saldo_devedor_pelas_parcelas(id)) - v_valor)
                                                                 / nullif(prazo_remanescente_meses, 0))
                                           else amortizacao_mensal_atual end,
           prazo_remanescente_meses = case when v_tipo = 'reduzir_prazo' and coalesce(amortizacao_mensal_atual, 0) > 0
                                           then ceil((coalesce(saldo_devedor_atual, financeiro.saldo_devedor_pelas_parcelas(id)) - v_valor)
                                                     / amortizacao_mensal_atual)::integer
                                           else prazo_remanescente_meses end
     where id = v_f.id;
    v_saldo := v_saldo - v_valor;
    select * into v_base from public.financiamento_parcela p
     where p.financiamento_id = v_f.id and p.status = 'pago' order by p.numero_parcela desc limit 1;
    if found then
        update public.financiamento set numero_parcela_base = v_base.numero_parcela, data_base = v_base.data_vencimento where id = v_f.id;
    end if;
    select * into v_f from public.financiamento f where f.id = v_f.id;
    if cardinality(v_ids) > 0 and not financeiro.fin_usa_sac_tr(v_f.sistema_amortizacao, v_f.indexador_saldo, v_f.modo_calculo_financiamento) then
        v_quitadas := financeiro.fin_amortizar_padrao(v_f, v_ids, v_saldo, v_tipo);
        if v_tipo = 'reduzir_prazo' then
            if cardinality(v_quitadas) > 0 then
                update public.financiamento_parcela set conta_id = null where id = any (v_quitadas);
                delete from public.conta c where c.financiamento_parcela_id = any (v_quitadas) and not financeiro.despesa_efetivada(c.id);
                delete from public.financiamento_parcela p where p.id = any (v_quitadas);
                get diagnostics v_removidas = row_count;
            end if;
            update public.financiamento set prazo_remanescente_meses = cardinality(v_ids) - v_removidas where id = v_f.id;
        end if;
    elsif cardinality(v_ids) > 0 then
        if v_tipo = 'reduzir_parcela' then
            v_quota := financeiro.fin_div(v_saldo, cardinality(v_ids));
        else
            select * into v_primeira from public.financiamento_parcela p where p.id = v_ids[1];
            v_quota := case when coalesce(v_primeira.valor_amortizacao, 0) <> 0
                            then financeiro.fin_div(v_primeira.valor_amortizacao, 1 + financeiro.fin_tr(v_primeira.data_vencimento))
                            else financeiro.fin_div(v_saldo, cardinality(v_ids)) end;
        end if;
        v_quitadas := financeiro.fin_atualizar_sac_tr(v_f, v_ids, v_saldo, v_quota);
        update public.financiamento
           set amortizacao_mensal_atual = (select p.valor_amortizacao from public.financiamento_parcela p where p.id = v_ids[1])
         where id = v_f.id;
        if v_tipo = 'reduzir_prazo' and cardinality(v_quitadas) > 0 then
            update public.financiamento_parcela set conta_id = null where id = any (v_quitadas);
            delete from public.conta c where c.financiamento_parcela_id = any (v_quitadas) and not financeiro.despesa_efetivada(c.id);
            delete from public.financiamento_parcela p where p.id = any (v_quitadas);
            get diagnostics v_removidas = row_count;
        end if;
    end if;
    v_resultado := jsonb_build_object('success', true, 'message', 'Amortização extraordinária registrada com sucesso',
                                      'data', to_jsonb(v_a), 'parcelas_recalculadas', cardinality(v_ids) - v_removidas,
                                      'parcelas_removidas', v_removidas);
    insert into financeiro.operacao_despesa (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'registrar_amortizacao_extra', v_resultado);
    return v_resultado;
end
$$;
