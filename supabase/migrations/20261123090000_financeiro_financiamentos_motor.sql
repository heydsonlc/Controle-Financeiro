-- FIN-FINANCIAMENTOS-MOTOR-1 — motor de Financiamentos SAC/TR da Caixa no novo aplicativo (escritor unico do perfil):
-- cadastro com geracao das parcelas e despesas, regeneracao sem execucao financeira, amortizacao extraordinaria
-- (reduzir parcela / reduzir prazo) e registro explicito de parcelas historicas (quitadas antes do sistema).
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261123090000).
-- Validada em cluster local descartavel, comparada com o PROPRIO Flask (tests/test_supabase_financiamentos_motor.py).
-- Docs: docs/FIN_FINANCIAMENTOS_MOTOR_1.md.
--
-- Referencia: services/financiamento_service.py (criar_financiamento, _gerar_parcelas_caixa_sac_tr,
-- _atualizar_parcelas_caixa_sac_tr, calcular_seguro_habitacional, registrar_amortizacao_extra,
-- _recalcular_apos_amortizacao, _criar_conta_da_parcela, _remover_cronograma_sem_execucao). As contas seguem o Flask
-- (Decimal em memoria, gravado em numeric(10,2)/(12,2)); aqui os intermediarios ficam com 30 casas (financeiro.fin_r).
--
-- Regras de integridade (docs/FIN_CONTRATOS_3.md §9), que prevalecem sobre o Flask:
-- 1. despesa paga ou com qualquer movimento (inclusive estornado) nunca e alterada pelo motor (R1);
-- 2. o status da despesa nunca e copiado da parcela (R2): so pagamento e estorno (FIN-CONTRATOS-2) mudam os dois;
-- 3. parcela historica e registrada explicitamente (financeiro.parcela_historica), sem movimento bancario (R3);
-- 4. recalculo, reducao de prazo e regeneracao so mexem em parcela pendente cuja despesa nao tem movimento (R4).
-- Tabelas: financeiro.parcela_historica (nova) e dois indices unicos (parcela por numero; despesa por parcela).
-- Substitui financeiro.saldo_devedor_pelas_parcelas (20261120090000). Nenhum dado existente e alterado. Reversao: supabase/reversao/20261123090000_remover_motor_financiamentos.sql.
-- Tambem: edicao (estrutural so sem execucao), vigencias de seguro com recalculo so do seguro e exclusao segura. Correcoes em relacao ao Flask, classificadas em
-- docs/FIN_FINANCIAMENTOS_MOTOR_1.md §5: continuidade do saldo na amortizacao, parcelas so de taxa no reduzir prazo,
-- movimento (inclusive estornado) como execucao, valor acima do saldo.

-- 0. Unicidade e registro historico ---------------------------------------------------------------------------------

create unique index financiamento_parcela_numero_unico on public.financiamento_parcela (financiamento_id, numero_parcela);
create unique index conta_financiamento_parcela_unica on public.conta (financiamento_parcela_id)
    where financiamento_parcela_id is not null;

create table financeiro.parcela_historica (
    parcela_id           integer     primary key references public.financiamento_parcela (id),
    financiamento_id     integer     not null references public.financiamento (id),
    perfil_financeiro_id integer     not null,
    conta_id             integer     references public.conta (id),
    registrado_por       uuid        not null,
    registrado_em        timestamptz not null default now()
);

comment on table financeiro.parcela_historica is
    'FIN-FINANCIAMENTOS-MOTOR-1: parcela quitada antes do uso do sistema, registrada sem movimento bancario. Nunca reaberta pelo motor.';

alter table financeiro.parcela_historica enable row level security;
alter table financeiro.parcela_historica force row level security;
revoke all on financeiro.parcela_historica from public, anon, authenticated;

-- Registro coerente e permanente, garantido no banco (nao so pela funcao que o grava): a parcela e do financiamento, o
-- financiamento e do perfil, a parcela esta paga e a despesa (se houver) e a da parcela. Depois de gravado, nao muda nem
-- sai (UPDATE, DELETE e TRUNCATE recusados); so a reversao, com a tabela vazia, a remove.
create function financeiro.proteger_parcela_historica()
    returns trigger
    language plpgsql
    set search_path = ''
as $$
begin
    if tg_op <> 'INSERT' then
        raise exception 'Registro de parcela historica e permanente' using errcode = 'P0001', hint = 'HISTORICO_PERMANENTE';
    end if;
    if not exists (select 1 from public.financiamento_parcela p
                     join public.financiamento f on f.id = p.financiamento_id
                    where p.id = new.parcela_id and p.financiamento_id = new.financiamento_id
                      and lower(coalesce(p.status, '')) = 'pago'
                      and financeiro.pertence_ao_perfil(f.perfil_financeiro_id, new.perfil_financeiro_id))
       or (new.conta_id is not null and new.conta_id is distinct from financeiro.fin_conta_da_parcela(new.parcela_id)) then
        raise exception 'Registro de parcela historica incoerente' using errcode = '23514', hint = 'HISTORICO_INCOERENTE';
    end if;
    return new;
end
$$;
revoke execute on function financeiro.proteger_parcela_historica() from public, anon, authenticated;

create trigger parcela_historica_protegida
    before insert or update or delete on financeiro.parcela_historica
    for each row execute function financeiro.proteger_parcela_historica();
create trigger parcela_historica_sem_truncate
    before truncate on financeiro.parcela_historica
    for each statement execute function financeiro.proteger_parcela_historica();

-- Saldo devedor pela cadeia (substitui a de 20261120090000, mesma assinatura e privilegios): o da parcela paga de maior
-- numero MENOS as amortizacoes extraordinarias registradas depois do vencimento dela (sem paga: financiado menos todas).
-- Pagando em ordem, igual ao Flask; corrige o pagamento ou registro de parcela anterior a uma amortizacao ja feita, que
-- devolvia o saldo de antes da amortizacao. Interna.
create or replace function financeiro.saldo_devedor_pelas_parcelas(p_financiamento_id integer)
    returns numeric
    language sql
    stable
    security definer
    set search_path = ''
as $$
    with paga as (select p.saldo_devedor_apos_pagamento, p.data_vencimento from public.financiamento_parcela p
                   where p.financiamento_id = p_financiamento_id and p.status = 'pago'
                   order by p.numero_parcela desc, p.id desc limit 1)
    select coalesce((select saldo_devedor_apos_pagamento from paga),
                    (select f.valor_financiado from public.financiamento f where f.id = p_financiamento_id))
         - coalesce((select sum(a.valor) from public.financiamento_amortizacao_extra a
                      where a.financiamento_id = p_financiamento_id
                        and (not exists (select 1 from paga) or a.data > (select data_vencimento from paga))), 0)
$$;

-- 1. Calculo ---------------------------------------------------------------------------------------------------------

-- Intermediario como o Decimal do Flask: 28 digitos significativos, arredondamento bancario (ROUND_HALF_EVEN), a
-- cada operacao. Necessario para empatar ao centavo nos casos de meio centavo exato. Interna.
create function financeiro.fin_r(p numeric)
    returns numeric
    language plpgsql
    immutable
    set search_path = ''
as $$
declare
    v_casas integer;
    v_trunc numeric;
    v_resto numeric;
    v_unid  numeric;
begin
    if p is null or p = 0 then
        return p;
    end if;
    v_casas := 27 - floor(log(10::numeric, abs(p)))::integer;
    v_trunc := trunc(p, v_casas);
    v_resto := abs(p - v_trunc);
    if v_resto = 0 then
        return v_trunc;
    end if;
    v_unid := power(10::numeric, -v_casas);
    if v_resto * 2 > v_unid
       or (v_resto * 2 = v_unid and mod(abs(trunc(v_trunc * power(10::numeric, v_casas))), 2) = 1) then
        return v_trunc + sign(p) * v_unid;
    end if;
    return v_trunc;
end
$$;

-- Divisao como o Decimal do Flask (o numeric do PostgreSQL divide com menos casas). Interna.
create function financeiro.fin_div(p_a numeric, p_b numeric)
    returns numeric
    language sql
    immutable
    set search_path = ''
as $$
    select financeiro.fin_r(round(p_a, 60) / p_b)
$$;

-- SAC com TR (ou o modo tecnico antigo caixa_sac_tr): motor Caixa (_config_usa_sac_tr). Interna.
create function financeiro.fin_usa_sac_tr(p_sistema text, p_indexador text, p_modo text)
    returns boolean
    language sql
    immutable
    set search_path = ''
as $$
    select (upper(btrim(coalesce(p_sistema, ''))) = 'SAC' and upper(btrim(coalesce(p_indexador, ''))) = 'TR')
        or coalesce(p_modo, '') = 'caixa_sac_tr'
$$;

-- TR mensal (fator decimal) da competencia do vencimento; sem indice, erro como o Flask. Interna.
create function financeiro.fin_tr(p_data date)
    returns numeric
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_competencia text := to_char(p_data, 'YYYY-MM');
    v_valor       numeric;
begin
    select i.valor_decimal into v_valor from public.indice_tr_mensal i where i.competencia = v_competencia;
    if not found then
        raise exception 'Nao ha TR cadastrada para a competencia %. Cadastre o indice em Indexadores > TR para financiamentos SAC/TR.',
            v_competencia using errcode = '22023', hint = 'TR_AUSENTE';
    end if;
    return v_valor;
end
$$;

-- Configuracao de calculo a partir do contrato gravado (as operacoes depois do cadastro leem do banco, como o Flask).
-- No cadastro, criar_financiamento monta a mesma configuracao com os valores do pedido (o Flask gera com os valores
-- ainda em memoria). Interna.
create function financeiro.fin_config(p_fin public.financiamento)
    returns jsonb
    language sql
    stable
    set search_path = ''
as $$
    select jsonb_build_object(
        'id', p_fin.id, 'valor_financiado', p_fin.valor_financiado, 'prazo', p_fin.prazo_total_meses,
        'taxa_anual', p_fin.taxa_juros_nominal_anual, 'primeira', p_fin.data_primeira_parcela,
        'taxa_adm', coalesce(p_fin.taxa_administracao_fixa, 0), 'seguro_modo', coalesce(p_fin.seguro_modo, 'fixo'),
        'fator_dfi', p_fin.seguro_fator_dfi, 'dfi_base', p_fin.seguro_dfi_base,
        'nascimento', p_fin.seguro_data_nascimento_titular, 'mes_reajuste', p_fin.seguro_mes_reajuste_idade,
        'taxa_mensal', p_fin.taxa_juros_mensal,
        'sac_tr', financeiro.fin_usa_sac_tr(p_fin.sistema_amortizacao, p_fin.indexador_saldo, p_fin.modo_calculo_financiamento))
$$;

-- Seguro habitacional (calcular_seguro_habitacional): fixo = vigencia do vencimento; estimado = DFI + MIP por faixa. Interna.
create function financeiro.fin_seguro(p_cfg jsonb, p_data date, p_amortizacao numeric, p_juros numeric)
    returns numeric
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_fin        integer := (p_cfg ->> 'id')::integer;
    v_valor      numeric;
    v_nasc       date;
    v_mes        integer;
    v_dia        integer;
    v_reajuste   date;
    v_idade      integer;
    v_fator_mip  numeric;
    v_base       numeric;
begin
    if p_cfg ->> 'seguro_modo' = 'estimado_dfi_mip' then
        if p_cfg ->> 'fator_dfi' is null then
            raise exception 'seguro_fator_dfi é obrigatório no modo estimado DFI + MIP' using errcode = '22023';
        end if;
        v_nasc := (p_cfg ->> 'nascimento')::date;
        if v_nasc is null then
            raise exception 'Data de nascimento do titular é obrigatória para seguro estimado' using errcode = '22023';
        end if;
        -- _calcular_idade_seguro
        v_mes := coalesce((p_cfg ->> 'mes_reajuste')::integer, extract(month from v_nasc)::integer);
        if v_mes < 1 or v_mes > 12 then
            raise exception 'seguro_mes_reajuste_idade deve estar entre 1 e 12' using errcode = '22023';
        end if;
        v_dia := case when p_cfg ->> 'mes_reajuste' is not null then 1 else extract(day from v_nasc)::integer end;
        begin
            v_reajuste := make_date(extract(year from p_data)::integer, v_mes, v_dia);
        exception when others then
            v_reajuste := make_date(extract(year from p_data)::integer, v_mes, 1);
        end;
        v_idade := extract(year from p_data)::integer - extract(year from v_nasc)::integer;
        if p_data < v_reajuste then
            v_idade := v_idade - 1;
        end if;
        v_idade := greatest(v_idade, 0);
        -- _obter_faixa_mip (ordem do PostgreSQL: vigencia_inicio desc com nulos primeiro, depois idade_inicio)
        select fx.fator_mip into v_fator_mip from public.financiamento_seguro_faixa_mip fx
         where fx.financiamento_id = v_fin and fx.ativo = true and fx.idade_inicio <= v_idade and fx.idade_fim >= v_idade
           and (fx.vigencia_inicio is null or fx.vigencia_inicio <= p_data) and (fx.vigencia_fim is null or fx.vigencia_fim >= p_data)
         order by fx.vigencia_inicio desc, fx.idade_inicio limit 1;
        if not found then
            raise exception 'Nenhuma faixa MIP encontrada para idade % na data %.', v_idade, to_char(p_data, 'YYYY-MM-DD')
                using errcode = '22023';
        end if;
        -- _base_dfi_seguro
        if (p_cfg ->> 'sac_tr')::boolean then
            v_base := coalesce((p_cfg ->> 'dfi_base')::numeric,
                               case when (p_cfg ->> 'valor_financiado')::numeric <> 0 and (p_cfg ->> 'prazo')::integer <> 0
                                    then financeiro.fin_div((p_cfg ->> 'valor_financiado')::numeric, (p_cfg ->> 'prazo')::integer) end,
                               coalesce(p_amortizacao, 0));
        else
            v_base := coalesce(p_amortizacao, 0);
        end if;
        return round(financeiro.fin_r(financeiro.fin_r(v_base * (p_cfg ->> 'fator_dfi')::numeric)
                                      + financeiro.fin_r(coalesce(p_juros, 0) * v_fator_mip)), 2);
    end if;
    if p_cfg ->> 'seguro_modo' <> 'fixo' then
        raise exception 'seguro_modo deve ser "fixo" ou "estimado_dfi_mip"' using errcode = '22023';
    end if;
    -- obter_seguro_por_data (empate de competencia: a vigencia cadastrada primeiro, como no gastos.db)
    select v.valor_mensal into v_valor from public.financiamento_seguro_vigencia v
     where v.financiamento_id = v_fin and v.competencia_inicio <= p_data
       and (v.data_encerramento is null or v.data_encerramento >= p_data)
     order by v.competencia_inicio desc, v.id limit 1;
    if not found then
        raise exception 'Seguro não configurado para a data %. Cadastre uma vigência de seguro antes de gerar as parcelas.',
            to_char(p_data, 'DD/MM/YYYY') using errcode = '22023', hint = 'SEGURO_SEM_VIGENCIA';
    end if;
    return v_valor;
end
$$;

-- 2. Despesas das parcelas --------------------------------------------------------------------------------------------

-- Despesa da parcela (as duas ligacoes do Flask) ou nada. Interna.
create function financeiro.fin_conta_da_parcela(p_parcela_id integer)
    returns integer
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select coalesce((select c.id from public.conta c where c.financiamento_parcela_id = p_parcela_id order by c.id limit 1),
                    (select p.conta_id from public.financiamento_parcela p where p.id = p_parcela_id))
$$;

-- Parcela que o motor pode recalcular, substituir ou remover: pendente, nao historica, e a despesa (se houver) nao
-- esta paga nem tem movimento algum (financeiro.despesa_efetivada, inclusive estornado). Interna.
create function financeiro.fin_parcela_elegivel(p_parcela_id integer)
    returns boolean
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select exists (select 1 from public.financiamento_parcela p
                    where p.id = p_parcela_id and lower(coalesce(p.status, '')) = 'pendente')
       and not exists (select 1 from financeiro.parcela_historica h where h.parcela_id = p_parcela_id)
       and not coalesce(financeiro.despesa_efetivada(financeiro.fin_conta_da_parcela(p_parcela_id)), false)
       and not exists (select 1 from public.conta c
                        where c.id = financeiro.fin_conta_da_parcela(p_parcela_id) and c.data_pagamento is not null)
       and not exists (select 1 from public.movimento_financeiro m where m.financiamento_parcela_id = p_parcela_id)
$$;

-- Cria ou atualiza a despesa da parcela (_criar_conta_da_parcela) SEM tocar no status (R2) e SEM tocar em despesa
-- efetivada (R1). Interna.
create function financeiro.fin_gravar_despesa(p_fin public.financiamento, p_parcela_id integer)
    returns void
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_p     public.financiamento_parcela;
    v_conta integer;
begin
    if p_fin.item_despesa_id is null then
        return;
    end if;
    select * into v_p from public.financiamento_parcela p where p.id = p_parcela_id;
    v_conta := financeiro.fin_conta_da_parcela(p_parcela_id);
    if v_conta is null then
        insert into public.conta (perfil_financeiro_id, item_despesa_id, financiamento_parcela_id, mes_referencia, descricao, valor,
                                  data_vencimento, data_pagamento, status_pagamento, numero_parcela, total_parcelas, observacoes,
                                  debito_automatico, is_fatura_cartao, estouro_orcamento, status_fatura, criado_em)
        values (p_fin.perfil_financeiro_id, p_fin.item_despesa_id, v_p.id, date_trunc('month', v_p.data_vencimento)::date,
                p_fin.nome || ' - Parcela ' || v_p.numero_parcela || '/' || p_fin.prazo_total_meses, v_p.valor_previsto_total,
                v_p.data_vencimento, null, 'Pendente', v_p.numero_parcela, p_fin.prazo_total_meses,
                'Financiamento ' || p_fin.sistema_amortizacao, false, false, false, 'ABERTA', now() at time zone 'utc')
        returning id into v_conta;
    elsif financeiro.despesa_efetivada(v_conta)
          or exists (select 1 from public.conta c where c.id = v_conta and c.data_pagamento is not null) then
        return;  -- R1: despesa efetivada e historico
    else
        update public.conta
           set item_despesa_id = p_fin.item_despesa_id, valor = v_p.valor_previsto_total, data_vencimento = v_p.data_vencimento,
               mes_referencia = date_trunc('month', v_p.data_vencimento)::date, numero_parcela = v_p.numero_parcela,
               total_parcelas = p_fin.prazo_total_meses, financiamento_parcela_id = v_p.id
         where id = v_conta;
    end if;
    update public.financiamento_parcela set conta_id = v_conta where id = v_p.id;
end
$$;

-- 3. Motor SAC/TR ---------------------------------------------------------------------------------------------------

-- Gera o cronograma completo (_gerar_parcelas_caixa_sac_tr) de um contrato sem parcelas. Devolve quantas gerou. Interna.
create function financeiro.fin_gerar_sac_tr(p_fin public.financiamento, p_cfg jsonb)
    returns integer
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_prazo      integer := (p_cfg ->> 'prazo')::integer;
    v_taxa       numeric := financeiro.fin_div(financeiro.fin_div((p_cfg ->> 'taxa_anual')::numeric, 100), 12);
    v_quota      numeric := financeiro.fin_div((p_cfg ->> 'valor_financiado')::numeric, v_prazo);
    v_saldo      numeric := (p_cfg ->> 'valor_financiado')::numeric;
    v_venc       date := (p_cfg ->> 'primeira')::date;
    v_taxa_adm   numeric := coalesce((p_cfg ->> 'taxa_adm')::numeric, 0);
    v_tr         numeric;
    v_corrigido  numeric;
    v_juros      numeric;
    v_amort      numeric;
    v_seguro     numeric;
    v_final      numeric;
    v_id         integer;
    v_n          integer;
    v_geradas    integer := 0;
begin
    if exists (select 1 from public.financiamento_parcela p where p.financiamento_id = p_fin.id) then
        raise exception 'O contrato ja tem parcelas' using errcode = '22023';
    end if;
    for v_n in 1 .. v_prazo loop
        exit when v_saldo <= 0.01;
        v_tr := financeiro.fin_tr(v_venc);
        v_quota := financeiro.fin_r(v_quota * (1 + v_tr));
        v_corrigido := financeiro.fin_r(v_saldo * (1 + v_tr));
        v_juros := financeiro.fin_r(v_corrigido * v_taxa);
        v_amort := least(v_quota, v_corrigido);
        v_seguro := financeiro.fin_seguro(p_cfg, v_venc, v_amort, v_juros);
        v_final := financeiro.fin_r(v_corrigido - v_amort);
        insert into public.financiamento_parcela (perfil_financeiro_id, financiamento_id, numero_parcela, data_vencimento,
                                                  valor_amortizacao, valor_juros, valor_seguro, valor_taxa_adm,
                                                  valor_subsidio, valor_fgts_utilizado, valor_juros_mora, valor_multa,
                                                  valor_atualizacao_monetaria, valor_iof_complementar, valor_previsto_total,
                                                  valor_pago, dif_apurada, saldo_devedor_apos_pagamento, status, criado_em)
        values (p_fin.perfil_financeiro_id, p_fin.id, v_n, v_venc, v_amort, v_juros, v_seguro, v_taxa_adm, 0, 0, 0, 0,
                financeiro.fin_r(v_corrigido - v_saldo), 0,
                financeiro.fin_r(financeiro.fin_r(financeiro.fin_r(v_amort + v_juros) + v_seguro) + v_taxa_adm), 0, 0,
                case when v_final > 0.01 then v_final else 0 end, 'pendente', now() at time zone 'utc')
        returning id into v_id;
        perform financeiro.fin_gravar_despesa(p_fin, v_id);
        v_geradas := v_geradas + 1;
        v_saldo := v_final;
        v_venc := (v_venc + interval '1 month')::date;  -- relativedelta acumulado
    end loop;
    return v_geradas;
end
$$;

-- Recalcula, na ordem, parcelas pendentes elegiveis a partir de um saldo e de uma quota base
-- (_atualizar_parcelas_caixa_sac_tr). Devolve as parcelas que ficaram sem saldo (saldo inicial <= 0,01). Interna.
create function financeiro.fin_atualizar_sac_tr(p_fin public.financiamento, p_ids integer[], p_saldo numeric, p_quota numeric)
    returns integer[]
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_cfg        jsonb := financeiro.fin_config(p_fin);
    v_taxa       numeric := financeiro.fin_div(financeiro.fin_div(p_fin.taxa_juros_nominal_anual, 100), 12);
    v_saldo      numeric := p_saldo;
    v_quota      numeric := coalesce(p_quota, financeiro.fin_div(p_saldo, greatest(cardinality(p_ids), 1)));
    v_p          public.financiamento_parcela;
    v_id         integer;
    v_tr         numeric;
    v_corrigido  numeric;
    v_juros      numeric;
    v_amort      numeric;
    v_seguro     numeric;
    v_taxa_adm   numeric;
    v_final      numeric;
    v_quitadas   integer[] := '{}';
begin
    foreach v_id in array coalesce(p_ids, '{}') loop
        select * into v_p from public.financiamento_parcela p where p.id = v_id for update;
        if not financeiro.fin_parcela_elegivel(v_id) then
            raise exception 'Parcela % nao pode ser recalculada (paga, historica ou com movimento)', v_p.numero_parcela
                using errcode = '22023', hint = 'PARCELA_PROTEGIDA';
        end if;
        v_taxa_adm := coalesce(nullif(v_p.valor_taxa_adm, 0), p_fin.taxa_administracao_fixa, 0);
        if v_saldo <= 0.01 then
            update public.financiamento_parcela
               set valor_amortizacao = 0, valor_juros = 0, valor_seguro = 0, valor_taxa_adm = v_taxa_adm,
                   valor_previsto_total = v_taxa_adm, saldo_devedor_apos_pagamento = 0
             where id = v_id;
            v_quitadas := v_quitadas || v_id;
            continue;
        end if;
        v_tr := financeiro.fin_tr(v_p.data_vencimento);
        v_quota := financeiro.fin_r(v_quota * (1 + v_tr));
        v_corrigido := financeiro.fin_r(v_saldo * (1 + v_tr));
        v_juros := financeiro.fin_r(v_corrigido * v_taxa);
        v_amort := least(v_quota, v_corrigido);
        v_seguro := financeiro.fin_seguro(v_cfg, v_p.data_vencimento, v_amort, v_juros);
        v_final := financeiro.fin_r(v_corrigido - v_amort);
        update public.financiamento_parcela
           set valor_amortizacao = v_amort, valor_juros = v_juros, valor_seguro = v_seguro, valor_taxa_adm = v_taxa_adm,
               valor_atualizacao_monetaria = financeiro.fin_r(v_corrigido - v_saldo),
               valor_previsto_total = financeiro.fin_r(financeiro.fin_r(financeiro.fin_r(v_amort + v_juros) + v_seguro) + v_taxa_adm),
               saldo_devedor_apos_pagamento = case when v_final > 0.01 then v_final else 0 end
         where id = v_id;
        perform financeiro.fin_gravar_despesa(p_fin, v_id);
        v_saldo := v_final;
    end loop;
    return v_quitadas;
end
$$;

-- 3b. SAC (sem TR, com ou sem outro indexador), PRICE e SIMPLES ------------------------------------------------------

-- Potencia inteira como o Decimal do Flask (calculo exato com folga, arredondado uma vez a 28 digitos). Interna.
create function financeiro.fin_pow_int(p_base numeric, p_n integer)
    returns numeric
    language plpgsql
    immutable
    set search_path = ''
as $$
declare
    v_r numeric := 1;
    v_b numeric := round(p_base, 80);
    v_n integer := p_n;
begin
    while v_n > 0 loop
        if v_n % 2 = 1 then
            v_r := round(v_r * v_b, 80);
        end if;
        v_b := round(v_b * v_b, 80);
        v_n := v_n / 2;
    end loop;
    return financeiro.fin_r(v_r);
end
$$;

-- Taxa mensal (_calcular_taxa_mensal_por_modo): nominal/12 ou efetiva equivalente (1 + anual)^(1/12) - 1. Interna.
create function financeiro.fin_taxa_mensal(p_anual numeric, p_modo text)
    returns numeric
    language sql
    immutable
    set search_path = ''
as $$
    select case when p_modo = 'nominal_dividida_12' then financeiro.fin_div(financeiro.fin_div(p_anual, 100), 12)
                else financeiro.fin_r(financeiro.fin_r(power(round(1 + financeiro.fin_div(p_anual, 100), 60),
                                                             round(financeiro.fin_div(1, 12), 60))) - 1) end
$$;

-- Indexador do mes (_obter_indexador: indexador_mensal pelo nome e mes; sem registro, zero). Interna.
create function financeiro.fin_indexador(p_nome text, p_data date)
    returns numeric
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select coalesce((select i.valor from public.indexador_mensal i
                      where i.nome = p_nome and i.data_referencia = date_trunc('month', p_data)::date limit 1), 0)
$$;

-- Cronograma completo de SAC (_gerar_parcelas_sac), PRICE (_gerar_parcelas_price) ou SIMPLES (_gerar_parcelas_simples)
-- num contrato sem parcelas. Devolve quantas gerou. Interna.
create function financeiro.fin_gerar_padrao(p_fin public.financiamento, p_cfg jsonb)
    returns integer
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_sistema   text := p_fin.sistema_amortizacao;
    v_valor     numeric := (p_cfg ->> 'valor_financiado')::numeric;
    v_prazo     integer := (p_cfg ->> 'prazo')::integer;
    v_taxa      numeric := (p_cfg ->> 'taxa_mensal')::numeric;
    v_taxa_adm  numeric := (p_cfg ->> 'taxa_adm')::numeric;
    v_saldo     numeric := v_valor;
    v_venc      date := (p_cfg ->> 'primeira')::date;
    v_fixa      numeric;
    v_pmt       numeric;
    v_fator     numeric;
    v_idx       numeric;
    v_corrigido numeric;
    v_juros     numeric;
    v_amort     numeric;
    v_seguro    numeric;
    v_total     numeric;
    v_final     numeric;
    v_id        integer;
    v_n         integer;
    v_geradas   integer := 0;
begin
    if exists (select 1 from public.financiamento_parcela p where p.financiamento_id = p_fin.id) then
        raise exception 'O contrato ja tem parcelas' using errcode = '22023';
    end if;
    if v_sistema = 'PRICE' then
        if v_taxa = 0 then
            v_pmt := financeiro.fin_div(v_valor, v_prazo);
        else
            v_fator := financeiro.fin_pow_int(1 + v_taxa, v_prazo);
            v_pmt := financeiro.fin_div(financeiro.fin_r(financeiro.fin_r(v_valor * v_taxa) * v_fator), financeiro.fin_r(v_fator - 1));
        end if;
    elsif v_sistema = 'SIMPLES' then
        v_juros := financeiro.fin_r(v_valor * v_taxa);
        v_fixa := financeiro.fin_div(v_valor, v_prazo);
    else
        v_fixa := financeiro.fin_div(v_valor, v_prazo);
    end if;
    for v_n in 1 .. v_prazo loop
        if v_sistema = 'SAC' then
            exit when v_saldo <= 0.01;
            v_idx := case when nullif(p_fin.indexador_saldo, '') is not null
                          then financeiro.fin_indexador(p_fin.indexador_saldo, v_venc) else 0 end;
            v_corrigido := financeiro.fin_r(v_saldo * financeiro.fin_r(1 + financeiro.fin_div(v_idx, 100)));
            v_juros := financeiro.fin_r(v_corrigido * v_taxa);
            v_amort := least(v_fixa, v_corrigido);
            v_seguro := financeiro.fin_seguro(p_cfg, v_venc, v_amort, v_juros);
            v_total := financeiro.fin_r(financeiro.fin_r(financeiro.fin_r(v_amort + v_juros) + v_seguro) + v_taxa_adm);
            v_final := financeiro.fin_r(v_corrigido - v_amort);
        elsif v_sistema = 'PRICE' then
            v_juros := financeiro.fin_r(v_saldo * v_taxa);
            v_amort := financeiro.fin_r(v_pmt - v_juros);
            v_seguro := financeiro.fin_seguro(p_cfg, v_venc, v_amort, v_juros);
            v_total := financeiro.fin_r(financeiro.fin_r(v_pmt + v_seguro) + v_taxa_adm);
            v_final := financeiro.fin_r(v_saldo - v_amort);
        else
            v_amort := v_fixa;
            v_seguro := financeiro.fin_seguro(p_cfg, v_venc, v_amort, v_juros);
            v_total := financeiro.fin_r(financeiro.fin_r(financeiro.fin_r(v_amort + v_juros) + v_seguro) + v_taxa_adm);
            v_final := financeiro.fin_r(v_saldo - v_amort);
        end if;
        insert into public.financiamento_parcela (perfil_financeiro_id, financiamento_id, numero_parcela, data_vencimento,
                                                  valor_amortizacao, valor_juros, valor_seguro, valor_taxa_adm,
                                                  valor_subsidio, valor_fgts_utilizado, valor_juros_mora, valor_multa,
                                                  valor_atualizacao_monetaria, valor_iof_complementar, valor_previsto_total,
                                                  valor_pago, dif_apurada, saldo_devedor_apos_pagamento, status, criado_em)
        values (p_fin.perfil_financeiro_id, p_fin.id, v_n, v_venc, v_amort, v_juros, v_seguro, v_taxa_adm, 0, 0, 0, 0, 0, 0,
                v_total, 0, 0, case when v_final > 0.01 then v_final else 0 end, 'pendente', now() at time zone 'utc')
        returning id into v_id;
        perform financeiro.fin_gravar_despesa(p_fin, v_id);
        v_geradas := v_geradas + 1;
        v_saldo := v_final;
        v_venc := (v_venc + interval '1 month')::date;
    end loop;
    return v_geradas;
end
$$;

-- Gerador do contrato (gerar_parcelas): motor Caixa SAC/TR ou o do sistema de amortizacao. Interna.
create function financeiro.fin_gerar(p_fin public.financiamento, p_cfg jsonb)
    returns integer
    language sql
    volatile
    security definer
    set search_path = ''
as $$
    select case when (p_cfg ->> 'sac_tr')::boolean then financeiro.fin_gerar_sac_tr(p_fin, p_cfg)
                else financeiro.fin_gerar_padrao(p_fin, p_cfg) end
$$;

-- Recalculo depois de amortizacao em SAC, PRICE e SIMPLES (_recalcular_reduzir_parcela / _recalcular_reduzir_prazo):
-- taxa mensal SEMPRE efetiva equivalente da nominal gravada (como o Flask), sem indexador. Reduzir prazo mantem a
-- amortizacao da 1a pendente e devolve as parcelas que sobram (o chamador as remove). Interna.
create function financeiro.fin_amortizar_padrao(p_fin public.financiamento, p_ids integer[], p_saldo numeric, p_tipo text)
    returns integer[]
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_cfg      jsonb := financeiro.fin_config(p_fin);
    v_taxa     numeric := financeiro.fin_taxa_mensal(p_fin.taxa_juros_nominal_anual, 'efetiva_equivalente');
    v_saldo    numeric := p_saldo;
    v_ref      numeric;
    v_p        public.financiamento_parcela;
    v_i        integer;
    v_n        integer := cardinality(p_ids);
    v_juros    numeric;
    v_amort    numeric;
    v_pmt      numeric;
    v_pot      numeric;
    v_seguro   numeric;
    v_taxa_adm numeric;
begin
    select p.valor_amortizacao into v_ref from public.financiamento_parcela p where p.id = p_ids[1];
    for v_i in 1 .. v_n loop
        select * into v_p from public.financiamento_parcela p where p.id = p_ids[v_i] for update;
        if not financeiro.fin_parcela_elegivel(v_p.id) then
            raise exception 'Parcela % nao pode ser recalculada (paga, historica ou com movimento)', v_p.numero_parcela
                using errcode = '22023', hint = 'PARCELA_PROTEGIDA';
        end if;
        v_juros := financeiro.fin_r(v_saldo * v_taxa);
        if p_tipo = 'reduzir_prazo' then
            v_amort := v_ref;
            if v_saldo <= v_amort then
                v_amort := v_saldo;
            end if;
        elsif p_fin.sistema_amortizacao = 'PRICE' then
            if v_taxa > 0 then
                v_pot := financeiro.fin_pow_int(financeiro.fin_r(1 + v_taxa), v_n - v_i + 1);
                v_pmt := financeiro.fin_div(financeiro.fin_r(v_saldo * financeiro.fin_r(v_taxa * v_pot)), financeiro.fin_r(v_pot - 1));
            else
                v_pmt := financeiro.fin_div(v_saldo, v_n - v_i + 1);
            end if;
            v_amort := financeiro.fin_r(v_pmt - v_juros);
        else
            v_amort := financeiro.fin_div(v_saldo, v_n - v_i + 1);
        end if;
        v_seguro := financeiro.fin_seguro(v_cfg, v_p.data_vencimento, v_amort, v_juros);
        v_taxa_adm := coalesce(nullif(v_p.valor_taxa_adm, 0), 0);
        update public.financiamento_parcela
           set valor_amortizacao = v_amort, valor_juros = v_juros, valor_seguro = v_seguro, valor_taxa_adm = v_taxa_adm,
               valor_previsto_total = financeiro.fin_r(financeiro.fin_r(financeiro.fin_r(v_amort + v_juros) + v_seguro) + v_taxa_adm),
               saldo_devedor_apos_pagamento = financeiro.fin_r(v_saldo - v_amort)
         where id = v_p.id;
        perform financeiro.fin_gravar_despesa(p_fin, v_p.id);
        v_saldo := financeiro.fin_r(v_saldo - v_amort);
        if p_tipo = 'reduzir_prazo' and v_saldo <= 0.01 then
            return p_ids[v_i + 1:];
        end if;
    end loop;
    return '{}';
end
$$;

-- Recalculo do ajuste de saldo em SAC, PRICE e SIMPLES (ramo nao Caixa de ajustar_saldo_devedor_real): taxa mensal
-- gravada; PRICE com a prestacao refeita a cada parcela; SAC e SIMPLES com saldo / restantes. Interna.
create function financeiro.fin_ajustar_padrao(p_fin public.financiamento, p_ids integer[], p_saldo numeric)
    returns void
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_cfg      jsonb := financeiro.fin_config(p_fin);
    v_taxa     numeric := p_fin.taxa_juros_mensal;
    v_saldo    numeric := p_saldo;
    v_p        public.financiamento_parcela;
    v_i        integer;
    v_rest     integer;
    v_juros    numeric;
    v_amort    numeric;
    v_prest    numeric;
    v_fator    numeric;
    v_seguro   numeric;
    v_taxa_adm numeric;
    v_final    numeric;
begin
    for v_i in 1 .. cardinality(p_ids) loop
        select * into v_p from public.financiamento_parcela p where p.id = p_ids[v_i] for update;
        if not financeiro.fin_parcela_elegivel(v_p.id) then
            raise exception 'Parcela % nao pode ser recalculada (paga, historica ou com movimento)', v_p.numero_parcela
                using errcode = '22023', hint = 'PARCELA_PROTEGIDA';
        end if;
        v_rest := cardinality(p_ids) - v_i + 1;
        v_juros := financeiro.fin_r(v_saldo * v_taxa);
        if p_fin.sistema_amortizacao = 'PRICE' then
            if v_taxa > 0 then
                v_fator := financeiro.fin_pow_int(financeiro.fin_r(1 + v_taxa), v_rest);
                v_prest := financeiro.fin_div(financeiro.fin_r(financeiro.fin_r(v_saldo * v_taxa) * v_fator), financeiro.fin_r(v_fator - 1));
            else
                v_prest := financeiro.fin_div(v_saldo, v_rest);
            end if;
            v_amort := financeiro.fin_r(v_prest - v_juros);
        else
            v_amort := financeiro.fin_div(v_saldo, v_rest);
            v_prest := financeiro.fin_r(v_amort + v_juros);
        end if;
        if v_amort > v_saldo then
            v_amort := v_saldo;
            v_prest := financeiro.fin_r(v_amort + v_juros);
        end if;
        v_seguro := financeiro.fin_seguro(v_cfg, v_p.data_vencimento, v_amort, v_juros);
        v_taxa_adm := coalesce(nullif(v_p.valor_taxa_adm, 0), nullif(p_fin.taxa_administracao_fixa, 0), 0);
        v_final := financeiro.fin_r(v_saldo - v_amort);
        update public.financiamento_parcela
           set valor_amortizacao = v_amort, valor_juros = v_juros, valor_seguro = v_seguro, valor_taxa_adm = v_taxa_adm,
               valor_previsto_total = financeiro.fin_r(financeiro.fin_r(v_prest + v_seguro) + v_taxa_adm),
               saldo_devedor_apos_pagamento = case when v_final > 0.01 then v_final else 0 end
         where id = v_p.id;
        perform financeiro.fin_gravar_despesa(p_fin, v_p.id);
        v_saldo := v_final;
    end loop;
end
$$;

-- 4. Guardas ----------------------------------------------------------------------------------------------------------

-- Escrita de financiamento: quem gere o perfil, perfil no novo aplicativo (escritor unico), uma operacao por vez. Interna.
create function financeiro.exigir_escrita_financiamento(p_perfil_id integer)
    returns void
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    perform financeiro.exigir_pagamento_novo(p_perfil_id);
    perform pg_advisory_xact_lock(20261123, p_perfil_id);
end
$$;

-- Contrato do perfil, travado. Interna.
create function financeiro.travar_financiamento(p_perfil_id integer, p_id integer)
    returns public.financiamento
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_f public.financiamento;
begin
    select * into v_f from public.financiamento f where f.id = p_id for update;
    if not found or not financeiro.pertence_ao_perfil(v_f.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Financiamento não encontrado' using errcode = '22023', hint = 'NAO_ENCONTRADO';
    end if;
    return v_f;
end
$$;

-- Execucao financeira (financiamento_possui_execucao_financeira): parcela paga, despesa paga, amortizacao, ajuste de
-- saldo ou movimento (inclusive estornado) em despesa de parcela. Interna.
create function financeiro.fin_possui_execucao(p_id integer)
    returns boolean
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select exists (select 1 from public.financiamento_parcela p where p.financiamento_id = p_id
                      and lower(coalesce(p.status, '')) in ('pago', 'paga', 'baixado', 'baixada', 'realizado', 'realizada',
                                                             'conciliado', 'conciliada', 'amortizado', 'amortizada',
                                                             'efetivado', 'efetivada'))
        or exists (select 1 from public.conta c join public.financiamento_parcela p on p.id = c.financiamento_parcela_id
                    where p.financiamento_id = p_id
                      and (lower(coalesce(c.status_pagamento, '')) in ('pago', 'paga', 'baixado', 'baixada', 'realizado',
                                                                        'realizada', 'conciliado', 'conciliada', 'efetivado',
                                                                        'efetivada') or c.data_pagamento is not null))
        or exists (select 1 from public.financiamento_amortizacao_extra a where a.financiamento_id = p_id)
        or exists (select 1 from public.financiamento_ajuste_saldo a where a.financiamento_id = p_id)
        or exists (select 1 from public.movimento_financeiro m
                     join public.conta c on c.id = m.conta_id
                     join public.financiamento_parcela p on p.id = c.financiamento_parcela_id
                    where p.financiamento_id = p_id)
        or exists (select 1 from public.movimento_financeiro m
                     join public.financiamento_parcela p on p.id = m.financiamento_parcela_id
                    where p.financiamento_id = p_id)
        or exists (select 1 from financeiro.parcela_historica h where h.financiamento_id = p_id)
$$;

-- Competencia de vigencia de seguro: YYYY-MM, YYYY-MM-DD, MM/YYYY ou DD/MM/YYYY, sempre no dia 1. Interna.
create function financeiro.fin_competencia(p_valor text)
    returns date
    language plpgsql
    immutable
    set search_path = ''
as $$
declare
    v text := btrim(coalesce(p_valor, ''));
begin
    if v ~ '^\d{4}-\d{2}(-\d{2})?$' then
        return make_date(substr(v, 1, 4)::integer, substr(v, 6, 2)::integer, 1);
    elsif v ~ '^\d{1,2}/\d{4}$' then
        return make_date(split_part(v, '/', 2)::integer, split_part(v, '/', 1)::integer, 1);
    elsif v ~ '^\d{1,2}/\d{1,2}/\d{4}$' then
        return make_date(split_part(v, '/', 3)::integer, split_part(v, '/', 2)::integer, 1);
    end if;
    raise exception 'Formato de data inválido para competencia_inicio: %. Use YYYY-MM, MM/YYYY, YYYY-MM-DD ou DD/MM/YYYY', p_valor
        using errcode = '22023';
exception when datetime_field_overflow or invalid_datetime_format or numeric_value_out_of_range then
    raise exception 'Formato de data inválido para competencia_inicio: %. Use YYYY-MM, MM/YYYY, YYYY-MM-DD ou DD/MM/YYYY', p_valor
        using errcode = '22023';
end
$$;

-- Numero do pedido (aceita virgula decimal) ou nulo. Interna.
create function financeiro.fin_numero(p_valor text, p_campo text)
    returns numeric
    language plpgsql
    immutable
    set search_path = ''
as $$
begin
    if p_valor is null or btrim(p_valor) = '' then
        return null;
    end if;
    return replace(btrim(p_valor), ',', '.')::numeric;
exception when invalid_text_representation then
    raise exception '% deve ser numérico', p_campo using errcode = '22023';
end
$$;

-- Data YYYY-MM-DD do pedido. Interna.
create function financeiro.fin_data(p_valor text, p_campo text)
    returns date
    language plpgsql
    immutable
    set search_path = ''
as $$
begin
    if p_valor is null or btrim(p_valor) = '' then
        raise exception '% é obrigatório', p_campo using errcode = '22023';
    end if;
    if btrim(p_valor) !~ '^\d{4}-\d{2}-\d{2}$' then
        raise exception '% deve estar no formato YYYY-MM-DD', p_campo using errcode = '22023';
    end if;
    return btrim(p_valor)::date;
exception when datetime_field_overflow or invalid_datetime_format then
    raise exception '% deve estar no formato YYYY-MM-DD', p_campo using errcode = '22023';
end
$$;

-- 5. Operacoes ---------------------------------------------------------------------------------------------------------

-- POST /api/financiamentos (criar_financiamento + validacoes da rota): contrato, vigencias de seguro (ou faixas MIP),
-- item de despesa automatico, parcelas e despesas (motor Caixa SAC/TR, SAC, PRICE ou SIMPLES). Idempotente pela chave.
create function financeiro.criar_financiamento(p_perfil_id integer, p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_repetida   jsonb;
    v_modo       text;
    v_modo_taxa  text;
    v_sistema    text;
    v_indexador  text;
    v_seguro     text;
    v_valor      numeric;
    v_prazo      integer;
    v_taxa       numeric;
    v_contrato   date;
    v_primeira   date;
    v_fator_dfi  numeric;
    v_nasc       date;
    v_mes_idade  integer;
    v_dfi_base   numeric;
    v_taxa_adm   numeric;
    v_item       integer;
    v_item_auto  boolean := false;
    v_f          public.financiamento;
    v_vig        jsonb;
    v_vigencias  jsonb;
    v_idx        integer := 0;
    v_comp       date;
    v_faixa      jsonb;
    v_cfg        jsonb;
    v_geradas    integer;
    v_resultado  jsonb;
begin
    perform financeiro.exigir_escrita_financiamento(p_perfil_id);
    v_repetida := financeiro.operacao_repetida(p_perfil_id, p_chave, 'criar_financiamento');
    if v_repetida is not null then
        return v_repetida;
    end if;
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' or p_dados = '{}'::jsonb then
        raise exception 'Dados não fornecidos' using errcode = '22023';
    end if;
    -- Validacoes da rota
    v_seguro := coalesce(nullif(p_dados ->> 'seguro_modo', ''), 'fixo');
    if v_seguro not in ('fixo', 'estimado_dfi_mip') then
        raise exception 'seguro_modo deve ser "fixo" ou "estimado_dfi_mip"' using errcode = '22023';
    end if;
    if v_seguro = 'estimado_dfi_mip' and nullif(p_dados ->> 'seguro_data_nascimento_titular', '') is null then
        raise exception 'seguro_data_nascimento_titular é obrigatória no modo estimado DFI + MIP' using errcode = '22023';
    end if;
    v_vigencias := coalesce(p_dados -> 'vigencias_seguro', '[]'::jsonb);
    if jsonb_typeof(v_vigencias) <> 'array' then
        raise exception 'vigencias_seguro deve ser uma lista' using errcode = '22023';
    end if;
    if v_seguro = 'fixo' and jsonb_array_length(v_vigencias) = 0 then
        raise exception 'É obrigatório informar pelo menos uma vigência de seguro' using errcode = '22023';
    end if;
    for v_vig in select value from jsonb_array_elements(v_vigencias) loop
        v_idx := v_idx + 1;
        if not v_vig ? 'competencia_inicio' then
            raise exception 'Vigência %: competencia_inicio é obrigatório', v_idx using errcode = '22023';
        end if;
        if coalesce(financeiro.fin_numero(v_vig ->> 'valor_mensal', 'valor_mensal'), 0) <= 0 then
            raise exception 'Vigência %: valor_mensal deve ser maior que zero', v_idx using errcode = '22023';
        end if;
        if v_vig ? 'saldo_devedor_vigencia' and coalesce(financeiro.fin_numero(v_vig ->> 'saldo_devedor_vigencia', 'saldo'), 0) <= 0 then
            raise exception 'Vigência %: saldo_devedor_vigencia, se fornecido, deve ser maior que zero', v_idx using errcode = '22023';
        end if;
    end loop;
    -- Validacoes do servico
    if nullif(btrim(coalesce(p_dados ->> 'nome', '')), '') is null then
        raise exception 'Nome é obrigatório' using errcode = '22023';
    end if;
    v_sistema := p_dados ->> 'sistema_amortizacao';
    if v_sistema is null or v_sistema not in ('SAC', 'PRICE', 'SIMPLES') then
        raise exception 'Sistema de amortização deve ser SAC, PRICE ou SIMPLES' using errcode = '22023';
    end if;
    v_modo := coalesce(nullif(p_dados ->> 'modo_calculo_financiamento', ''), 'padrao');
    if v_modo not in ('padrao', 'caixa_sac_tr') then
        raise exception 'modo_calculo_financiamento deve ser "padrao" ou "caixa_sac_tr"' using errcode = '22023';
    end if;
    v_indexador := nullif(p_dados ->> 'indexador_saldo', '');
    if v_modo = 'caixa_sac_tr' then
        v_sistema := 'SAC';
        v_indexador := 'TR';
    end if;
    v_modo_taxa := case when financeiro.fin_usa_sac_tr(v_sistema, v_indexador, v_modo) then 'nominal_dividida_12'
                        else coalesce(nullif(p_dados ->> 'modo_taxa_mensal', ''), 'efetiva_equivalente') end;
    if v_modo_taxa not in ('efetiva_equivalente', 'nominal_dividida_12') then
        raise exception 'modo_taxa_mensal deve ser "efetiva_equivalente" ou "nominal_dividida_12"' using errcode = '22023';
    end if;
    v_valor := financeiro.fin_numero(p_dados ->> 'valor_financiado', 'valor_financiado');
    if v_valor is null or v_valor <= 0 then
        raise exception 'Valor financiado deve ser maior que zero' using errcode = '22023';
    end if;
    v_prazo := financeiro.fin_numero(p_dados ->> 'prazo_total_meses', 'prazo_total_meses')::integer;
    if v_prazo is null or v_prazo <= 0 then
        raise exception 'Prazo total deve ser maior que zero' using errcode = '22023';
    end if;
    v_taxa := financeiro.fin_numero(p_dados ->> 'taxa_juros_nominal_anual', 'taxa_juros_nominal_anual');
    if v_taxa is null or v_taxa <= 0 then  -- o Flask recusa tambem zero ("not dados.get(...)")
        raise exception 'Taxa de juros não pode ser negativa' using errcode = '22023';
    end if;
    v_contrato := financeiro.fin_data(p_dados ->> 'data_contrato', 'data_contrato');
    v_primeira := financeiro.fin_data(p_dados ->> 'data_primeira_parcela', 'data_primeira_parcela');
    v_fator_dfi := financeiro.fin_numero(p_dados ->> 'seguro_fator_dfi', 'seguro_fator_dfi');
    if v_fator_dfi is null and v_seguro = 'estimado_dfi_mip' then
        v_fator_dfi := 0.0489;
    end if;
    if v_fator_dfi is not null and v_fator_dfi < 0 then
        raise exception 'seguro_fator_dfi não pode ser negativo' using errcode = '22023';
    end if;
    if nullif(p_dados ->> 'seguro_data_nascimento_titular', '') is not null then
        v_nasc := financeiro.fin_data(p_dados ->> 'seguro_data_nascimento_titular', 'seguro_data_nascimento_titular');
    end if;
    v_mes_idade := coalesce(financeiro.fin_numero(coalesce(p_dados ->> 'seguro_mes_reajuste_idade', '2'), 'seguro_mes_reajuste_idade')::integer, 2);
    if v_mes_idade = 0 then
        v_mes_idade := 2;
    end if;
    if v_mes_idade < 1 or v_mes_idade > 12 then
        raise exception 'seguro_mes_reajuste_idade deve estar entre 1 e 12' using errcode = '22023';
    end if;
    v_dfi_base := financeiro.fin_numero(p_dados ->> 'seguro_dfi_base', 'seguro_dfi_base');
    if v_dfi_base is not null and v_dfi_base < 0 then
        raise exception 'seguro_dfi_base nao pode ser negativo' using errcode = '22023';
    end if;
    if v_dfi_base is null and v_seguro = 'estimado_dfi_mip' and financeiro.fin_usa_sac_tr(v_sistema, v_indexador, v_modo) then
        v_dfi_base := financeiro.fin_div(v_valor, v_prazo);
    end if;
    v_taxa_adm := coalesce(financeiro.fin_numero(p_dados ->> 'taxa_administracao_fixa', 'taxa_administracao_fixa'), 0);
    -- Item de despesa: o informado (do perfil) ou um automatico com a origem do contrato.
    if nullif(p_dados ->> 'item_despesa_id', '') is not null then
        select d.id into v_item from public.item_despesa d
         where d.id = financeiro.fin_numero(p_dados ->> 'item_despesa_id', 'item_despesa_id')::integer
           and financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id);
        if v_item is null then
            raise exception 'Item de despesa invalido ou nao pertence ao contexto financeiro atual.' using errcode = '22023';
        end if;
    else
        insert into public.item_despesa (perfil_financeiro_id, nome, tipo, ativo, valor, recorrente, pago, tipo_recorrencia, criado_em)
        values (p_perfil_id, p_dados ->> 'nome', 'Financiamento', true, 0, false, false, 'mensal', now() at time zone 'utc')
        returning id into v_item;
        v_item_auto := true;
    end if;
    insert into public.financiamento (perfil_financeiro_id, nome, produto, sistema_amortizacao, valor_financiado, prazo_total_meses,
                                      prazo_remanescente_meses, taxa_juros_nominal_anual, taxa_juros_efetiva_anual,
                                      taxa_juros_efetiva_relacionamento_anual, taxa_juros_mensal, modo_calculo_financiamento,
                                      modo_taxa_mensal, indexador_saldo, data_contrato, data_primeira_parcela, item_despesa_id,
                                      seguro_tipo, seguro_percentual, valor_seguro_mensal, seguro_modo, seguro_fator_dfi,
                                      seguro_data_nascimento_titular, seguro_mes_reajuste_idade, seguro_dfi_base,
                                      taxa_administracao_fixa, ativo, saldo_devedor_atual, numero_parcela_base, data_base,
                                      amortizacao_mensal_atual, regime_pos_amortizacao, criado_em)
    values (p_perfil_id, p_dados ->> 'nome', coalesce(p_dados ->> 'produto', ''), v_sistema, v_valor, v_prazo, v_prazo, v_taxa,
            nullif(financeiro.fin_numero(p_dados ->> 'taxa_juros_efetiva_anual', 'taxa_juros_efetiva_anual'), 0),
            nullif(financeiro.fin_numero(p_dados ->> 'taxa_juros_efetiva_relacionamento_anual', 'taxa_juros_efetiva_relacionamento_anual'), 0),
            financeiro.fin_taxa_mensal(v_taxa, v_modo_taxa), v_modo, v_modo_taxa, v_indexador, v_contrato, v_primeira, v_item,
            'fixo', coalesce(financeiro.fin_numero(p_dados ->> 'seguro_percentual', 'seguro_percentual'), 0.0006),
            coalesce(financeiro.fin_numero(p_dados ->> 'valor_seguro_mensal', 'valor_seguro_mensal'), 0), v_seguro, v_fator_dfi,
            v_nasc, v_mes_idade, v_dfi_base, v_taxa_adm, true, v_valor, 0, v_primeira,
            case when v_sistema = 'SAC' then financeiro.fin_div(v_valor, v_prazo) end, null, now() at time zone 'utc')
    returning * into v_f;
    if v_item_auto then
        update public.item_despesa set origem_tipo = 'FINANCIAMENTO', origem_id = v_f.id, origem_contexto = 'cronograma'
         where id = v_item;
    end if;
    -- Vigencias de seguro em ordem de competencia; cada nova encerra a ativa anterior.
    for v_vig in select value from jsonb_array_elements(v_vigencias) order by financeiro.fin_competencia(value ->> 'competencia_inicio') loop
        v_comp := financeiro.fin_competencia(v_vig ->> 'competencia_inicio');
        update public.financiamento_seguro_vigencia
           set vigencia_ativa = false, data_encerramento = v_comp - 1
         where id = (select v.id from public.financiamento_seguro_vigencia v
                      where v.financiamento_id = v_f.id and v.vigencia_ativa order by v.id limit 1);
        insert into public.financiamento_seguro_vigencia (perfil_financeiro_id, financiamento_id, competencia_inicio, valor_mensal,
                                                          saldo_devedor_vigencia, taxa_percentual, data_nascimento_segurado,
                                                          observacoes, vigencia_ativa, data_encerramento, criado_em)
        values (p_perfil_id, v_f.id, v_comp, financeiro.fin_numero(v_vig ->> 'valor_mensal', 'valor_mensal'), v_valor, null, null,
                v_vig ->> 'observacoes', true, null, now() at time zone 'utc');
    end loop;
    if v_seguro = 'estimado_dfi_mip' then
        if jsonb_typeof(coalesce(p_dados -> 'faixas_mip', 'null'::jsonb)) not in ('array', 'null') then
            raise exception 'faixas_mip deve ser uma lista' using errcode = '22023';
        end if;
        v_idx := 0;
        for v_faixa in select value from jsonb_array_elements(coalesce(p_dados -> 'faixas_mip', '[]'::jsonb)) loop
            v_idx := v_idx + 1;
            if (v_faixa ->> 'idade_inicio')::integer < 0 or (v_faixa ->> 'idade_fim')::integer < (v_faixa ->> 'idade_inicio')::integer then
                raise exception 'Faixa MIP % possui intervalo de idade inválido', v_idx using errcode = '22023';
            end if;
            if financeiro.fin_numero(v_faixa ->> 'fator_mip', 'fator_mip') < 0 then
                raise exception 'Faixa MIP % possui fator_mip negativo', v_idx using errcode = '22023';
            end if;
            insert into public.financiamento_seguro_faixa_mip (perfil_financeiro_id, financiamento_id, idade_inicio, idade_fim,
                                                                fator_mip, vigencia_inicio, vigencia_fim, ativo, criado_em, atualizado_em)
            values (v_f.perfil_financeiro_id, v_f.id, (v_faixa ->> 'idade_inicio')::integer, (v_faixa ->> 'idade_fim')::integer,
                    financeiro.fin_numero(v_faixa ->> 'fator_mip', 'fator_mip'),
                    case when nullif(v_faixa ->> 'vigencia_inicio', '') is not null then financeiro.fin_data(v_faixa ->> 'vigencia_inicio', 'vigencia_inicio') end,
                    case when nullif(v_faixa ->> 'vigencia_fim', '') is not null then financeiro.fin_data(v_faixa ->> 'vigencia_fim', 'vigencia_fim') end,
                    coalesce((v_faixa ->> 'ativo')::boolean, true), now() at time zone 'utc', now() at time zone 'utc');
        end loop;
        if v_idx = 0 then  -- _garantir_faixas_mip_padrao
            insert into public.financiamento_seguro_faixa_mip (perfil_financeiro_id, financiamento_id, idade_inicio, idade_fim,
                                                                fator_mip, vigencia_inicio, vigencia_fim, ativo, criado_em, atualizado_em)
            select v_f.perfil_financeiro_id, v_f.id, x.i, x.f, x.m, null, null, true, now() at time zone 'utc', now() at time zone 'utc'
              from (values (0, 45, 0.03187), (46, 50, 0.04899), (51, 55, 0.08593), (56, 60, 0.16077), (61, 65, 0.31887),
                           (66, 70, 0.34932), (71, 75, 0.49795), (76, 80, 0.57099)) as x(i, f, m);
        end if;
    end if;
    -- Geracao com os valores do pedido (o Flask gera antes de gravar: valores em memoria, sem o arredondamento das colunas).
    v_cfg := financeiro.fin_config(v_f) || jsonb_build_object('valor_financiado', v_valor, 'taxa_anual', v_taxa,
                                                              'taxa_adm', v_taxa_adm, 'fator_dfi', v_fator_dfi, 'dfi_base', v_dfi_base,
                                                              'taxa_mensal', financeiro.fin_taxa_mensal(v_taxa, v_modo_taxa));
    v_geradas := financeiro.fin_gerar(v_f, v_cfg);
    select * into v_f from public.financiamento f where f.id = v_f.id;
    v_resultado := jsonb_build_object('success', true, 'message', 'Financiamento criado e parcelas geradas com sucesso',
                                      'data', financeiro.financiamento_flask(v_f), 'parcelas_geradas', v_geradas);
    insert into financeiro.operacao_despesa (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'criar_financiamento', v_resultado);
    return v_resultado;
end
$$;

-- POST /api/financiamentos/<id>/regenerar-parcelas: como o Flask, so sem execucao financeira (nada pago, nenhuma
-- amortizacao, ajuste, parcela historica ou movimento); remove o cronograma e as despesas e gera de novo.
create function financeiro.regenerar_parcelas_financiamento(p_perfil_id integer, p_id integer)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_f       public.financiamento;
    v_ids     integer[];
    v_geradas integer;
begin
    perform financeiro.exigir_escrita_financiamento(p_perfil_id);
    v_f := financeiro.travar_financiamento(p_perfil_id, p_id);
    if financeiro.fin_possui_execucao(v_f.id) then
        raise exception 'Não é possível alterar dados estruturais do financiamento porque já existem parcelas pagas ou vinculadas a pagamentos.'
            using errcode = '22023', hint = 'COM_EXECUCAO';
    end if;
    select coalesce(array_agg(p.id), '{}') into v_ids from public.financiamento_parcela p where p.financiamento_id = v_f.id;
    update public.financiamento_parcela set conta_id = null where id = any (v_ids);
    delete from public.conta c where c.financiamento_parcela_id = any (v_ids);
    delete from public.financiamento_parcela p where p.id = any (v_ids);
    v_geradas := financeiro.fin_gerar(v_f, financeiro.fin_config(v_f));
    return jsonb_build_object('success', true, 'message', 'Parcelas regeneradas com sucesso', 'parcelas_geradas', v_geradas);
end
$$;

-- Parcelas quitadas antes do uso do sistema (Regra 3): da primeira pendente ate 'ate_parcela', ja vencidas, sem
-- despesa efetivada. Parcela 'pago' com valor pago = previsto; despesa 'Pago' na data do vencimento, valor intacto;
-- NENHUM movimento bancario; registro em financeiro.parcela_historica. Idempotente pela chave.
create function financeiro.registrar_parcelas_historicas(p_perfil_id integer, p_id integer, p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_repetida  jsonb;
    v_f         public.financiamento;
    v_ate       integer;
    v_p         public.financiamento_parcela;
    v_conta     integer;
    v_n         integer := 0;
    v_resultado jsonb;
begin
    perform financeiro.exigir_escrita_financiamento(p_perfil_id);
    v_repetida := financeiro.operacao_repetida(p_perfil_id, p_chave, 'registrar_parcelas_historicas');
    if v_repetida is not null then
        return v_repetida;
    end if;
    v_f := financeiro.travar_financiamento(p_perfil_id, p_id);
    v_ate := financeiro.fin_numero(p_dados ->> 'ate_parcela', 'ate_parcela')::integer;
    if v_ate is null or v_ate < 1 then
        raise exception 'Informe até qual parcela o pagamento é anterior ao sistema' using errcode = '22023';
    end if;
    if not exists (select 1 from public.financiamento_parcela p where p.financiamento_id = v_f.id and p.numero_parcela = v_ate) then
        raise exception 'Parcela % não existe neste financiamento', v_ate using errcode = '22023';
    end if;
    if (select p.data_vencimento from public.financiamento_parcela p where p.financiamento_id = v_f.id and p.numero_parcela = v_ate)
       > financeiro.hoje_brasilia() then
        raise exception 'Parcela histórica precisa estar vencida; para pagar uma parcela futura use Despesas' using errcode = '22023',
            hint = 'PARCELA_FUTURA';
    end if;
    for v_p in select * from public.financiamento_parcela p where p.financiamento_id = v_f.id and p.numero_parcela <= v_ate
                order by p.numero_parcela for update loop
        if lower(coalesce(v_p.status, '')) = 'pago' then
            continue;  -- ja quitada (historica ou paga em Despesas): intacta
        end if;
        if not financeiro.fin_parcela_elegivel(v_p.id) then
            raise exception 'Parcela % tem despesa paga ou com movimento: use Despesas (pagamento e estorno)', v_p.numero_parcela
                using errcode = '22023', hint = 'PARCELA_PROTEGIDA';
        end if;
        v_conta := financeiro.fin_conta_da_parcela(v_p.id);
        update public.financiamento_parcela
           set status = 'pago', valor_pago = valor_previsto_total, dif_apurada = 0
         where id = v_p.id;
        if v_conta is not null then
            update public.conta set status_pagamento = 'Pago', data_pagamento = v_p.data_vencimento where id = v_conta;
        end if;
        insert into financeiro.parcela_historica (parcela_id, financiamento_id, perfil_financeiro_id, conta_id, registrado_por)
        values (v_p.id, v_f.id, p_perfil_id, v_conta, (select auth.uid()));
        v_n := v_n + 1;
    end loop;
    if v_n > 0 then
        update public.financiamento set saldo_devedor_atual = financeiro.saldo_devedor_pelas_parcelas(v_f.id) where id = v_f.id;
    end if;
    select * into v_f from public.financiamento f where f.id = v_f.id;
    v_resultado := jsonb_build_object('success', true, 'registradas', v_n, 'ate_parcela', v_ate,
                                      'saldo_devedor_atual', v_f.saldo_devedor_atual);
    insert into financeiro.operacao_despesa (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'registrar_parcelas_historicas', v_resultado);
    return v_resultado;
end
$$;

-- POST /api/financiamentos/<id>/amortizacao-extra (registrar_amortizacao_extra + _recalcular_apos_amortizacao, SAC/TR):
-- reduz o saldo devedor atual e recalcula SO as parcelas pendentes elegiveis a partir da data. Correcoes em relacao ao
-- Flask: (a) parcela futura com movimento (inclusive estornado) tambem bloqueia (o Flask so olha pago/data de pagamento);
-- (b) valor acima do saldo devedor e recusado (o Flask deixa o saldo negativo; quitacao e operacao propria);
-- (c) reduzir prazo remove as parcelas pendentes que ficaram sem saldo (o Flask as mantem cobrando so a taxa
-- administrativa, despesa sem obrigacao). Idempotente pela chave.
create function financeiro.registrar_amortizacao_extra(p_perfil_id integer, p_id integer, p_dados jsonb, p_chave uuid)
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

-- DELETE /api/financiamentos/<id> (excluir_financiamento): so sem execucao financeira; remove despesas, parcelas,
-- vigencias e faixas MIP e o contrato. O item de despesa fica (como no Flask). Contrato com documento ou conferencia
-- da Caixa e recusado (os arquivos ainda sao do Flask: FIN-DOCUMENTOS-2).
create function financeiro.excluir_financiamento(p_perfil_id integer, p_id integer)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_f   public.financiamento;
    v_ids integer[];
begin
    perform financeiro.exigir_escrita_financiamento(p_perfil_id);
    v_f := financeiro.travar_financiamento(p_perfil_id, p_id);
    if financeiro.fin_possui_execucao(v_f.id) then
        raise exception 'Nao e possivel excluir este financiamento porque ja existem parcelas pagas, ajustes, amortizacoes ou movimentacoes financeiras vinculadas.'
            using errcode = '22023', hint = 'COM_EXECUCAO';
    end if;
    if exists (select 1 from public.financiamento_documento d where d.financiamento_id = v_f.id)
       or exists (select 1 from public.financiamento_conferencia_caixa x where x.financiamento_id = v_f.id) then
        raise exception 'Este financiamento tem documentos ou conferências da Caixa; a exclusão continua no sistema atual. Nada foi gravado.'
            using errcode = '22023', hint = 'COM_DOCUMENTOS';
    end if;
    select coalesce(array_agg(p.id), '{}') into v_ids from public.financiamento_parcela p where p.financiamento_id = v_f.id;
    update public.financiamento_parcela set conta_id = null where id = any (v_ids);
    delete from public.conta c where c.financiamento_parcela_id = any (v_ids);
    delete from public.financiamento_parcela p where p.id = any (v_ids);
    delete from public.financiamento_seguro_vigencia v where v.financiamento_id = v_f.id;
    delete from public.financiamento_seguro_faixa_mip x where x.financiamento_id = v_f.id;
    delete from public.financiamento f where f.id = v_f.id;
    return jsonb_build_object('success', true, 'message', 'Financiamento excluido com sucesso.', 'parcelas_removidas', cardinality(v_ids));
end
$$;

-- 5b. Edicao, vigencias de seguro e recalculo so do seguro ------------------------------------------------------------

-- Campo estrutural alterado (_valor_estrutural_alterado): numero compara pelo valor (nulo = 0); demais pelo texto. Interna.
create function financeiro.fin_campo_alterado(p_campo text, p_atual jsonb, p_novo jsonb)
    returns boolean
    language sql
    immutable
    set search_path = ''
as $$
    select case
        when p_novo is null or jsonb_typeof(p_novo) = 'null' then coalesce(jsonb_typeof(p_atual), 'null') <> 'null'
        when p_campo in ('valor_financiado', 'taxa_juros_nominal_anual', 'seguro_percentual', 'valor_seguro_mensal',
                         'seguro_fator_dfi', 'seguro_dfi_base', 'taxa_administracao_fixa')
            then coalesce((p_atual #>> '{}')::numeric, 0) <> (p_novo #>> '{}')::numeric
        else (p_atual #>> '{}') is distinct from (p_novo #>> '{}')
    end
$$;

-- Recalculo SO do seguro (recalcular_seguro_parcelas_futuras) nas parcelas pendentes a partir da data: amortizacao,
-- juros e saldo intactos. Correcao: a despesa pendente sem movimento acompanha o novo total (o Flask so muda a parcela:
-- origem da diferenca de R$ 1,00 do contrato real); parcela com despesa paga ou com movimento fica intacta. Interna.
create function financeiro.fin_recalcular_seguro(p_fin_id integer, p_a_partir_de date)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_f        public.financiamento;
    v_cfg      jsonb;
    v_p        public.financiamento_parcela;
    v_seguro   numeric;
    v_n        integer := 0;
    v_mantidas integer := 0;
begin
    select * into v_f from public.financiamento f where f.id = p_fin_id;
    v_cfg := financeiro.fin_config(v_f);
    for v_p in select * from public.financiamento_parcela p
                where p.financiamento_id = p_fin_id and p.status = 'pendente'
                  and (p_a_partir_de is null or p.data_vencimento >= p_a_partir_de)
                order by p.numero_parcela for update loop
        if not financeiro.fin_parcela_elegivel(v_p.id) then
            v_mantidas := v_mantidas + 1;
            continue;
        end if;
        v_seguro := financeiro.fin_seguro(v_cfg, v_p.data_vencimento, v_p.valor_amortizacao, v_p.valor_juros);
        update public.financiamento_parcela
           set valor_seguro = v_seguro,
               valor_previsto_total = v_p.valor_amortizacao + v_p.valor_juros + v_seguro + coalesce(v_p.valor_taxa_adm, 0)
         where id = v_p.id;
        perform financeiro.fin_gravar_despesa(v_f, v_p.id);
        v_n := v_n + 1;
    end loop;
    return jsonb_build_object('atualizadas', v_n, 'preservadas', v_mantidas);
end
$$;

-- Vigencia de seguro nova (SeguroVigenciaService.criar_vigencia): sem encerrar as anteriores, como o Flask. Interna.
create function financeiro.fin_criar_vigencia(p_fin public.financiamento, p_competencia date, p_valor numeric, p_obs text)
    returns public.financiamento_seguro_vigencia
    language sql
    volatile
    security definer
    set search_path = ''
as $$
    insert into public.financiamento_seguro_vigencia (perfil_financeiro_id, financiamento_id, competencia_inicio, valor_mensal,
                                                      saldo_devedor_vigencia, taxa_percentual, data_nascimento_segurado,
                                                      observacoes, vigencia_ativa, data_encerramento, criado_em)
    values (p_fin.perfil_financeiro_id, p_fin.id, p_competencia, p_valor, p_fin.saldo_devedor_atual, null, null, p_obs, true, null,
            now() at time zone 'utc')
    returning *
$$;

-- POST /api/financiamentos/<id>/vigencias-seguro (adicionar_vigencia_seguro): vigencia nova com o saldo devedor atual e
-- recalculo so do seguro a partir da competencia. Qualquer modalidade (nao mexe em saldo nem amortizacao). Idempotente.
create function financeiro.adicionar_vigencia_seguro(p_perfil_id integer, p_id integer, p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_repetida  jsonb;
    v_f         public.financiamento;
    v_comp      date;
    v_vig       public.financiamento_seguro_vigencia;
    v_rec       jsonb;
    v_resultado jsonb;
begin
    perform financeiro.exigir_escrita_financiamento(p_perfil_id);
    v_repetida := financeiro.operacao_repetida(p_perfil_id, p_chave, 'adicionar_vigencia_seguro');
    if v_repetida is not null then
        return v_repetida;
    end if;
    v_f := financeiro.travar_financiamento(p_perfil_id, p_id);
    if nullif(btrim(coalesce(p_dados ->> 'competencia_inicio', '')), '') is null then
        raise exception 'competencia_inicio é obrigatório' using errcode = '22023';
    end if;
    if coalesce(financeiro.fin_numero(p_dados ->> 'valor_mensal', 'valor_mensal'), 0) = 0 then
        raise exception 'valor_mensal é obrigatório' using errcode = '22023';
    end if;
    v_comp := financeiro.fin_competencia(p_dados ->> 'competencia_inicio');
    v_vig := financeiro.fin_criar_vigencia(v_f, v_comp, financeiro.fin_numero(p_dados ->> 'valor_mensal', 'valor_mensal'),
                                           coalesce(p_dados ->> 'observacoes', ''));
    v_rec := financeiro.fin_recalcular_seguro(v_f.id, v_comp);
    v_resultado := jsonb_build_object(
        'success', true,
        'message', 'Vigência criada com sucesso. ' || (v_rec ->> 'atualizadas') || ' parcelas atualizadas.',
        'data', jsonb_build_object(
            'vigencia', jsonb_build_object('id', v_vig.id, 'perfil_financeiro_id', v_vig.perfil_financeiro_id,
                                           'financiamento_id', v_vig.financiamento_id,
                                           'competencia_inicio', to_char(v_vig.competencia_inicio, 'YYYY-MM-DD'),
                                           'valor_mensal', v_vig.valor_mensal, 'saldo_devedor_vigencia', v_vig.saldo_devedor_vigencia,
                                           'taxa_percentual', v_vig.taxa_percentual, 'data_nascimento_segurado', null,
                                           'observacoes', v_vig.observacoes, 'vigencia_ativa', v_vig.vigencia_ativa,
                                           'data_encerramento', null),
            'parcelas_atualizadas', (v_rec ->> 'atualizadas')::integer,
            'parcelas_preservadas', (v_rec ->> 'preservadas')::integer,
            'saldo_devedor_atual', v_f.saldo_devedor_atual));
    insert into financeiro.operacao_despesa (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'adicionar_vigencia_seguro', v_resultado);
    return v_resultado;
end
$$;

-- PUT /api/financiamentos/<id> (atualizar_financiamento + validacoes da rota). Campos estruturais so sem execucao
-- financeira (e entao o cronograma e regenerado); nome, produto, situacao e item de despesa
-- sempre (item: so sem execucao, como o Flask). Correcao: renomear muda a descricao das despesas pendentes sem
-- movimento (as efetivadas guardam o historico), como em consorcios. Idempotente pela chave.
create function financeiro.atualizar_financiamento(p_perfil_id integer, p_id integer, p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_repetida   jsonb;
    v_f          public.financiamento;
    v_e          jsonb := '{}'::jsonb;
    v_d          jsonb := p_dados;
    v_campo      text;
    v_valor      numeric;
    v_modo       text;
    v_sistema    text;
    v_indexador  text;
    v_modo_calc  text;
    v_sac_tr     boolean;
    v_modo_taxa  text;
    v_taxa_base  numeric;
    v_seguro     text;
    v_faixas     jsonb;
    v_faixa      jsonb;
    v_idx        integer;
    v_item       integer;
    v_troca_item boolean := false;
    v_alterados  text[] := '{}';
    v_estrutural boolean;
    v_regenerar  boolean;
    v_nome_ant   text;
    v_vig        jsonb;
    v_ids        integer[];
    v_cfg        jsonb;
    v_rec        jsonb;
    v_a_partir   date;
    v_resultado  jsonb;
begin
    perform financeiro.exigir_escrita_financiamento(p_perfil_id);
    v_repetida := financeiro.operacao_repetida(p_perfil_id, p_chave, 'atualizar_financiamento');
    if v_repetida is not null then
        return v_repetida;
    end if;
    if v_d is null or jsonb_typeof(v_d) <> 'object' or v_d = '{}'::jsonb then
        raise exception 'Dados não fornecidos' using errcode = '22023';
    end if;
    v_f := financeiro.travar_financiamento(p_perfil_id, p_id);
    v_nome_ant := v_f.nome;
    -- Validacoes da rota
    if v_d ? 'seguro_modo' then
        v_seguro := coalesce(nullif(v_d ->> 'seguro_modo', ''), 'fixo');
        if v_seguro not in ('fixo', 'estimado_dfi_mip') then
            raise exception 'seguro_modo deve ser "fixo" ou "estimado_dfi_mip"' using errcode = '22023';
        end if;
        if v_seguro = 'estimado_dfi_mip' and nullif(v_d ->> 'seguro_data_nascimento_titular', '') is null then
            raise exception 'seguro_data_nascimento_titular é obrigatória no modo estimado DFI + MIP' using errcode = '22023';
        end if;
    end if;
    if v_d ? 'seguro_tipo' and coalesce(v_d ->> 'seguro_tipo', '') not in ('fixo', 'percentual_saldo') then
        raise exception 'seguro_tipo deve ser "fixo" ou "percentual_saldo"' using errcode = '22023';
    end if;
    -- Valores estruturais pedidos
    if v_d ? 'sistema_amortizacao' then
        if coalesce(v_d ->> 'sistema_amortizacao', '') not in ('SAC', 'PRICE', 'SIMPLES') then
            raise exception 'Sistema de amortização deve ser SAC, PRICE ou SIMPLES' using errcode = '22023';
        end if;
        v_e := v_e || jsonb_build_object('sistema_amortizacao', v_d ->> 'sistema_amortizacao');
    end if;
    if v_d ? 'modo_calculo_financiamento' then
        v_modo := coalesce(nullif(v_d ->> 'modo_calculo_financiamento', ''), 'padrao');
        if v_modo not in ('padrao', 'caixa_sac_tr') then
            raise exception 'modo_calculo_financiamento deve ser "padrao" ou "caixa_sac_tr"' using errcode = '22023';
        end if;
        v_e := v_e || jsonb_build_object('modo_calculo_financiamento', v_modo);
        if v_modo = 'caixa_sac_tr' then
            v_e := v_e || jsonb_build_object('sistema_amortizacao', 'SAC', 'indexador_saldo', 'TR', 'modo_taxa_mensal', 'nominal_dividida_12');
        end if;
    end if;
    if v_d ? 'modo_taxa_mensal' then
        v_modo := coalesce(nullif(v_d ->> 'modo_taxa_mensal', ''), 'efetiva_equivalente');
        if v_modo not in ('efetiva_equivalente', 'nominal_dividida_12') then
            raise exception 'modo_taxa_mensal deve ser "efetiva_equivalente" ou "nominal_dividida_12"' using errcode = '22023';
        end if;
        v_e := v_e || jsonb_build_object('modo_taxa_mensal', v_modo);
    end if;
    if v_d ? 'valor_financiado' then
        v_valor := financeiro.fin_numero(v_d ->> 'valor_financiado', 'valor_financiado');
        if v_valor is null or v_valor <= 0 then
            raise exception 'Valor financiado deve ser maior que zero' using errcode = '22023';
        end if;
        v_e := v_e || jsonb_build_object('valor_financiado', v_valor);
    end if;
    if v_d ? 'prazo_total_meses' then
        v_valor := financeiro.fin_numero(v_d ->> 'prazo_total_meses', 'prazo_total_meses');
        if v_valor is null or v_valor <= 0 then
            raise exception 'Prazo total deve ser maior que zero' using errcode = '22023';
        end if;
        v_e := v_e || jsonb_build_object('prazo_total_meses', v_valor::integer);
    end if;
    if v_d ? 'taxa_juros_nominal_anual' then
        v_valor := financeiro.fin_numero(v_d ->> 'taxa_juros_nominal_anual', 'taxa_juros_nominal_anual');
        if v_valor is null or v_valor < 0 then
            raise exception 'Taxa de juros não pode ser negativa' using errcode = '22023';
        end if;
        v_e := v_e || jsonb_build_object('taxa_juros_nominal_anual', v_valor);
    end if;
    if v_d ? 'indexador_saldo' then
        v_e := v_e || jsonb_build_object('indexador_saldo', nullif(v_d ->> 'indexador_saldo', ''));
    end if;
    if v_d ? 'data_contrato' then
        v_e := v_e || jsonb_build_object('data_contrato', financeiro.fin_data(v_d ->> 'data_contrato', 'data_contrato'));
    end if;
    if v_d ? 'data_primeira_parcela' then
        v_e := v_e || jsonb_build_object('data_primeira_parcela', financeiro.fin_data(v_d ->> 'data_primeira_parcela', 'data_primeira_parcela'));
    end if;
    if v_d ? 'seguro_tipo' then
        v_e := v_e || jsonb_build_object('seguro_tipo', v_d ->> 'seguro_tipo');
        if not v_d ? 'seguro_modo' then
            v_e := v_e || jsonb_build_object('seguro_modo', 'fixo');
        end if;
    end if;
    if v_d ? 'seguro_percentual' and jsonb_typeof(v_d -> 'seguro_percentual') <> 'null' then
        v_valor := financeiro.fin_numero(v_d ->> 'seguro_percentual', 'seguro_percentual');
        if v_valor < 0 then
            raise exception 'seguro_percentual não pode ser negativo' using errcode = '22023';
        end if;
        v_e := v_e || jsonb_build_object('seguro_percentual', v_valor);
    end if;
    if v_d ? 'valor_seguro_mensal' then
        v_valor := coalesce(financeiro.fin_numero(v_d ->> 'valor_seguro_mensal', 'valor_seguro_mensal'), 0);
        if v_valor < 0 then
            raise exception 'valor_seguro_mensal não pode ser negativo' using errcode = '22023';
        end if;
        v_e := v_e || jsonb_build_object('valor_seguro_mensal', v_valor);
    end if;
    if v_d ? 'seguro_modo' then
        v_e := v_e || jsonb_build_object('seguro_modo', v_seguro);
    end if;
    foreach v_campo in array array['seguro_fator_dfi', 'seguro_dfi_base'] loop
        if v_d ? v_campo then
            v_valor := financeiro.fin_numero(v_d ->> v_campo, v_campo);
            if v_valor is not null and v_valor < 0 then
                raise exception '% nao pode ser negativo', v_campo using errcode = '22023';
            end if;
            v_e := v_e || jsonb_build_object(v_campo, v_valor);
        end if;
    end loop;
    if v_d ? 'seguro_data_nascimento_titular' then
        v_e := v_e || jsonb_build_object('seguro_data_nascimento_titular',
            case when nullif(v_d ->> 'seguro_data_nascimento_titular', '') is not null
                 then financeiro.fin_data(v_d ->> 'seguro_data_nascimento_titular', 'seguro_data_nascimento_titular') end);
    end if;
    if v_d ? 'seguro_mes_reajuste_idade' then
        v_valor := coalesce(nullif(financeiro.fin_numero(v_d ->> 'seguro_mes_reajuste_idade', 'seguro_mes_reajuste_idade'), 0), 2);
        if v_valor < 1 or v_valor > 12 then
            raise exception 'seguro_mes_reajuste_idade deve estar entre 1 e 12' using errcode = '22023';
        end if;
        v_e := v_e || jsonb_build_object('seguro_mes_reajuste_idade', v_valor::integer);
    end if;
    if v_d ? 'taxa_administracao_fixa' then
        v_valor := coalesce(financeiro.fin_numero(v_d ->> 'taxa_administracao_fixa', 'taxa_administracao_fixa'), 0);
        if v_valor < 0 then
            raise exception 'taxa_administracao_fixa não pode ser negativa' using errcode = '22023';
        end if;
        v_e := v_e || jsonb_build_object('taxa_administracao_fixa', v_valor);
    end if;
    if (v_e ? 'sistema_amortizacao' or v_e ? 'indexador_saldo') and not v_e ? 'modo_calculo_financiamento' then
        v_e := v_e || jsonb_build_object('modo_calculo_financiamento', 'padrao');
    end if;
    -- Resultantes
    v_sistema := coalesce(v_e ->> 'sistema_amortizacao', v_f.sistema_amortizacao);
    v_indexador := case when v_e ? 'indexador_saldo' then v_e ->> 'indexador_saldo' else v_f.indexador_saldo end;
    v_modo_calc := coalesce(v_e ->> 'modo_calculo_financiamento', v_f.modo_calculo_financiamento, 'padrao');
    v_sac_tr := financeiro.fin_usa_sac_tr(v_sistema, v_indexador, v_modo_calc);
    v_modo_taxa := case when v_sac_tr then 'nominal_dividida_12'
                        else coalesce(nullif(coalesce(v_e ->> 'modo_taxa_mensal', v_f.modo_taxa_mensal), ''), 'efetiva_equivalente') end;
    if v_modo_taxa not in ('efetiva_equivalente', 'nominal_dividida_12') then
        raise exception 'modo_taxa_mensal deve ser "efetiva_equivalente" ou "nominal_dividida_12"' using errcode = '22023';
    end if;
    if v_e ?| array['taxa_juros_nominal_anual', 'modo_taxa_mensal', 'modo_calculo_financiamento', 'sistema_amortizacao', 'indexador_saldo'] then
        v_taxa_base := coalesce((v_e ->> 'taxa_juros_nominal_anual')::numeric, v_f.taxa_juros_nominal_anual);
        v_e := v_e || jsonb_build_object('modo_taxa_mensal', v_modo_taxa, 'taxa_juros_mensal',
            financeiro.fin_taxa_mensal(v_taxa_base, v_modo_taxa));
    end if;
    if v_d ? 'faixas_mip' then
        v_faixas := coalesce(nullif(v_d -> 'faixas_mip', 'null'::jsonb), '[]'::jsonb);
        if jsonb_typeof(v_faixas) <> 'array' then
            raise exception 'faixas_mip deve ser uma lista' using errcode = '22023';
        end if;
    end if;
    if coalesce(v_e ->> 'seguro_modo', v_f.seguro_modo, 'fixo') = 'estimado_dfi_mip' then
        if not v_e ? 'seguro_fator_dfi' and v_f.seguro_fator_dfi is null then
            v_e := v_e || jsonb_build_object('seguro_fator_dfi', 0.0489);
        end if;
        if (case when v_e ? 'seguro_data_nascimento_titular' then v_e ->> 'seguro_data_nascimento_titular'
                 else v_f.seguro_data_nascimento_titular::text end) is null then
            raise exception 'seguro_data_nascimento_titular e obrigatoria no modo estimado DFI + MIP' using errcode = '22023';
        end if;
        if v_sac_tr and not v_e ? 'seguro_dfi_base' and v_f.seguro_dfi_base is null then
            v_e := v_e || jsonb_build_object('seguro_dfi_base', financeiro.fin_div(
                coalesce((v_e ->> 'valor_financiado')::numeric, v_f.valor_financiado),
                coalesce((v_e ->> 'prazo_total_meses')::integer, v_f.prazo_total_meses)));
        end if;
    end if;
    if v_d ? 'item_despesa_id' then
        select d.id into v_item from public.item_despesa d
         where d.id = financeiro.fin_numero(v_d ->> 'item_despesa_id', 'item_despesa_id')::integer
           and financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id);
        if v_item is null then
            raise exception 'Item de despesa invalido ou nao pertence ao contexto financeiro atual.' using errcode = '22023';
        end if;
        v_troca_item := v_f.item_despesa_id is distinct from v_item;
        if v_troca_item and financeiro.fin_possui_execucao(v_f.id) then
            raise exception 'Nao e possivel alterar o item de despesa deste financiamento porque ja existem parcelas pagas, ajustes, amortizacoes ou movimentacoes financeiras vinculadas.'
                using errcode = '22023', hint = 'COM_EXECUCAO';
        end if;
    end if;
    select coalesce(array_agg(k), '{}') into v_alterados from jsonb_object_keys(v_e) k
     where k <> 'taxa_juros_mensal' and financeiro.fin_campo_alterado(k, to_jsonb(v_f) -> k, v_e -> k);
    v_estrutural := cardinality(v_alterados) > 0 or v_faixas is not null;
    if v_estrutural and financeiro.fin_possui_execucao(v_f.id) then
        raise exception 'Não é possível alterar dados estruturais do financiamento porque já existem parcelas pagas ou vinculadas a pagamentos.'
            using errcode = '22023', hint = 'COM_EXECUCAO';
    end if;
    v_regenerar := v_estrutural and (coalesce((v_d ->> 'regenerar_cronograma')::boolean, true)
                                     or exists (select 1 from public.financiamento_parcela p where p.financiamento_id = v_f.id));
    -- Gravacao
    update public.financiamento f set
        nome = case when v_d ? 'nome' then v_d ->> 'nome' else f.nome end,
        produto = case when v_d ? 'produto' then v_d ->> 'produto' else f.produto end,
        ativo = case when v_d ? 'ativo' then (v_d ->> 'ativo')::boolean else f.ativo end,
        item_despesa_id = coalesce(v_item, f.item_despesa_id),
        sistema_amortizacao = coalesce(v_e ->> 'sistema_amortizacao', f.sistema_amortizacao),
        modo_calculo_financiamento = case when v_e ? 'modo_calculo_financiamento' then v_e ->> 'modo_calculo_financiamento' else f.modo_calculo_financiamento end,
        modo_taxa_mensal = case when v_e ? 'modo_taxa_mensal' then v_e ->> 'modo_taxa_mensal' else f.modo_taxa_mensal end,
        taxa_juros_mensal = case when v_e ? 'taxa_juros_mensal' then (v_e ->> 'taxa_juros_mensal')::numeric else f.taxa_juros_mensal end,
        valor_financiado = coalesce((v_e ->> 'valor_financiado')::numeric, f.valor_financiado),
        prazo_total_meses = coalesce((v_e ->> 'prazo_total_meses')::integer, f.prazo_total_meses),
        taxa_juros_nominal_anual = coalesce((v_e ->> 'taxa_juros_nominal_anual')::numeric, f.taxa_juros_nominal_anual),
        indexador_saldo = case when v_e ? 'indexador_saldo' then v_e ->> 'indexador_saldo' else f.indexador_saldo end,
        data_contrato = coalesce((v_e ->> 'data_contrato')::date, f.data_contrato),
        data_primeira_parcela = coalesce((v_e ->> 'data_primeira_parcela')::date, f.data_primeira_parcela),
        seguro_tipo = coalesce(v_e ->> 'seguro_tipo', f.seguro_tipo),
        seguro_percentual = coalesce((v_e ->> 'seguro_percentual')::numeric, f.seguro_percentual),
        valor_seguro_mensal = coalesce((v_e ->> 'valor_seguro_mensal')::numeric, f.valor_seguro_mensal),
        seguro_modo = coalesce(v_e ->> 'seguro_modo', f.seguro_modo),
        seguro_fator_dfi = case when v_e ? 'seguro_fator_dfi' then (v_e ->> 'seguro_fator_dfi')::numeric else f.seguro_fator_dfi end,
        seguro_dfi_base = case when v_e ? 'seguro_dfi_base' then (v_e ->> 'seguro_dfi_base')::numeric else f.seguro_dfi_base end,
        seguro_data_nascimento_titular = case when v_e ? 'seguro_data_nascimento_titular' then (v_e ->> 'seguro_data_nascimento_titular')::date
                                              else f.seguro_data_nascimento_titular end,
        seguro_mes_reajuste_idade = coalesce((v_e ->> 'seguro_mes_reajuste_idade')::integer, f.seguro_mes_reajuste_idade),
        taxa_administracao_fixa = coalesce((v_e ->> 'taxa_administracao_fixa')::numeric, f.taxa_administracao_fixa)
     where f.id = v_f.id;
    select * into v_f from public.financiamento f where f.id = v_f.id;
    if v_faixas is not null then
        delete from public.financiamento_seguro_faixa_mip x where x.financiamento_id = v_f.id;
        v_idx := 0;
        for v_faixa in select value from jsonb_array_elements(v_faixas) loop
            v_idx := v_idx + 1;
            if (v_faixa ->> 'idade_inicio')::integer < 0 or (v_faixa ->> 'idade_fim')::integer < (v_faixa ->> 'idade_inicio')::integer then
                raise exception 'Faixa MIP % possui intervalo de idade inválido', v_idx using errcode = '22023';
            end if;
            if financeiro.fin_numero(v_faixa ->> 'fator_mip', 'fator_mip') < 0 then
                raise exception 'Faixa MIP % possui fator_mip negativo', v_idx using errcode = '22023';
            end if;
            insert into public.financiamento_seguro_faixa_mip (perfil_financeiro_id, financiamento_id, idade_inicio, idade_fim, fator_mip,
                                                                vigencia_inicio, vigencia_fim, ativo, criado_em, atualizado_em)
            values (v_f.perfil_financeiro_id, v_f.id, (v_faixa ->> 'idade_inicio')::integer, (v_faixa ->> 'idade_fim')::integer,
                    financeiro.fin_numero(v_faixa ->> 'fator_mip', 'fator_mip'),
                    case when nullif(v_faixa ->> 'vigencia_inicio', '') is not null then financeiro.fin_data(v_faixa ->> 'vigencia_inicio', 'vigencia_inicio') end,
                    case when nullif(v_faixa ->> 'vigencia_fim', '') is not null then financeiro.fin_data(v_faixa ->> 'vigencia_fim', 'vigencia_fim') end,
                    coalesce((v_faixa ->> 'ativo')::boolean, true), now() at time zone 'utc', now() at time zone 'utc');
        end loop;
    elsif v_f.seguro_modo = 'estimado_dfi_mip'
          and not exists (select 1 from public.financiamento_seguro_faixa_mip x where x.financiamento_id = v_f.id) then
        insert into public.financiamento_seguro_faixa_mip (perfil_financeiro_id, financiamento_id, idade_inicio, idade_fim, fator_mip,
                                                            vigencia_inicio, vigencia_fim, ativo, criado_em, atualizado_em)
        select v_f.perfil_financeiro_id, v_f.id, x.i, x.f, x.m, null, null, true, now() at time zone 'utc', now() at time zone 'utc'
          from (values (0, 45, 0.03187), (46, 50, 0.04899), (51, 55, 0.08593), (56, 60, 0.16077), (61, 65, 0.31887),
                       (66, 70, 0.34932), (71, 75, 0.49795), (76, 80, 0.57099)) as x(i, f, m);
    end if;
    if v_estrutural then  -- estado soberano reiniciado
        update public.financiamento f
           set prazo_remanescente_meses = f.prazo_total_meses, saldo_devedor_atual = f.valor_financiado, numero_parcela_base = 0,
               data_base = f.data_primeira_parcela, regime_pos_amortizacao = null,
               amortizacao_mensal_atual = case when f.sistema_amortizacao = 'SAC'
                                               then financeiro.fin_div(coalesce((v_e ->> 'valor_financiado')::numeric, f.valor_financiado),
                                                                       f.prazo_total_meses) end
         where f.id = v_f.id;
        select * into v_f from public.financiamento f where f.id = v_f.id;
    end if;
    -- Vigencias pedidas (sempre novas, sem editar as existentes)
    for v_vig in select value from jsonb_array_elements(coalesce(nullif(v_d -> 'vigencias_seguro', 'null'::jsonb), '[]'::jsonb)) loop
        perform financeiro.fin_criar_vigencia(v_f, financeiro.fin_competencia(v_vig ->> 'competencia_inicio'),
                                              financeiro.fin_numero(v_vig ->> 'valor_mensal', 'valor_mensal'), v_vig ->> 'observacoes');
    end loop;
    if v_troca_item and not v_regenerar then  -- _sincronizar_item_despesa_contas_pendentes (so as nao efetivadas)
        update public.conta c set item_despesa_id = v_f.item_despesa_id
          from public.financiamento_parcela p
         where c.financiamento_parcela_id = p.id and p.financiamento_id = v_f.id and financeiro.fin_parcela_elegivel(p.id);
    end if;
    if v_regenerar then
        if v_f.seguro_modo is distinct from 'estimado_dfi_mip' then  -- _reconfigurar_vigencia_inicial_sem_execucao
            delete from public.financiamento_seguro_vigencia v where v.financiamento_id = v_f.id;
            perform financeiro.fin_criar_vigencia(v_f, date_trunc('month', v_f.data_primeira_parcela)::date,
                                                  coalesce(v_f.valor_seguro_mensal, 0),
                                                  'Vigência inicial regenerada na edição do financiamento sem parcelas pagas.');
        end if;
        select coalesce(array_agg(p.id), '{}') into v_ids from public.financiamento_parcela p where p.financiamento_id = v_f.id;
        update public.financiamento_parcela set conta_id = null where id = any (v_ids);
        delete from public.conta c where c.financiamento_parcela_id = any (v_ids);
        delete from public.financiamento_parcela p where p.id = any (v_ids);
        -- O Flask gera com os valores do pedido ainda em memoria (sem o arredondamento das colunas).
        v_cfg := financeiro.fin_config(v_f);
        if v_e ? 'valor_financiado' then v_cfg := v_cfg || jsonb_build_object('valor_financiado', v_e -> 'valor_financiado'); end if;
        if v_e ? 'taxa_juros_nominal_anual' then v_cfg := v_cfg || jsonb_build_object('taxa_anual', v_e -> 'taxa_juros_nominal_anual'); end if;
        if v_e ? 'taxa_administracao_fixa' then v_cfg := v_cfg || jsonb_build_object('taxa_adm', v_e -> 'taxa_administracao_fixa'); end if;
        if v_e ? 'seguro_fator_dfi' then v_cfg := v_cfg || jsonb_build_object('fator_dfi', v_e -> 'seguro_fator_dfi'); end if;
        if v_e ? 'seguro_dfi_base' then v_cfg := v_cfg || jsonb_build_object('dfi_base', v_e -> 'seguro_dfi_base'); end if;
        if v_e ? 'taxa_juros_mensal' then v_cfg := v_cfg || jsonb_build_object('taxa_mensal', v_e -> 'taxa_juros_mensal'); end if;
        perform financeiro.fin_gerar(v_f, v_cfg);
    elsif jsonb_array_length(coalesce(nullif(v_d -> 'vigencias_seguro', 'null'::jsonb), '[]'::jsonb)) > 0 then
        v_a_partir := case when length(v_d -> 'vigencias_seguro' -> 0 ->> 'competencia_inicio') = 7
                           then (v_d -> 'vigencias_seguro' -> 0 ->> 'competencia_inicio' || '-01')::date
                           else financeiro.fin_data(v_d -> 'vigencias_seguro' -> 0 ->> 'competencia_inicio', 'competencia_inicio') end;
        v_rec := financeiro.fin_recalcular_seguro(v_f.id, v_a_partir);
    end if;
    if v_d ? 'nome' and v_f.nome is distinct from v_nome_ant and not v_regenerar then
        update public.conta c
           set descricao = v_f.nome || substr(c.descricao, length(v_nome_ant) + 1)
          from public.financiamento_parcela p
         where c.financiamento_parcela_id = p.id and p.financiamento_id = v_f.id and financeiro.fin_parcela_elegivel(p.id)
           and left(c.descricao, length(v_nome_ant) + 11) = v_nome_ant || ' - Parcela ';
    end if;
    select * into v_f from public.financiamento f where f.id = v_f.id;
    v_resultado := jsonb_build_object('success', true, 'message', 'Financiamento atualizado com sucesso',
                                      'data', financeiro.financiamento_flask(v_f));
    insert into financeiro.operacao_despesa (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'atualizar_financiamento', v_resultado);
    return v_resultado;
end
$$;

-- POST /api/financiamentos/<id>/ajustar-saldo (ajustar_saldo_devedor_real): registro auditavel do saldo devedor real
-- (financiamento_ajuste_saldo) e recalculo das parcelas pendentes a partir da referencia. Parcela de referencia paga,
-- historica ou com movimento: comeca na seguinte. Qualquer parcela protegida na faixa: recusado (como o Flask, mais
-- movimento). Idempotente pela chave.
create function financeiro.ajustar_saldo_devedor(p_perfil_id integer, p_id integer, p_dados jsonb, p_chave uuid)
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

-- POST /api/financiamentos/<id>/simular-quitacao (simular_quitacao): SO LEITURA, como no Flask (rota fora da guarda de
-- escritor unico): saldo devedor atual (corrigido pela TR da competencia em SAC/TR), juros, seguros e taxas das parcelas
-- depois da data, desconto hipotetico sobre os juros e avisos. Quem le o perfil pode simular. Nada e gravado.
create function financeiro.simular_quitacao(p_perfil_id integer, p_id integer, p_dados jsonb)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_f        public.financiamento;
    v_data     date;
    v_desc     numeric;
    v_saldo    numeric;
    v_sac_tr   boolean;
    v_tr       numeric;
    v_estimado numeric;
    v_juros    numeric;
    v_seguros  numeric;
    v_taxas    numeric;
    v_total    integer;
    v_futuras  integer;
    v_vencidas integer;
    v_desconto numeric;
    v_obs      jsonb;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' or p_dados = '{}'::jsonb then
        raise exception 'Dados não fornecidos' using errcode = '22023';
    end if;
    if nullif(p_dados ->> 'data_quitacao', '') is null then
        raise exception 'data_quitacao é obrigatória' using errcode = '22023';
    end if;
    begin
        v_desc := coalesce(nullif(p_dados ->> 'desconto_banco_percentual', ''), '0')::double precision::text::numeric;
    exception when others then
        raise exception 'desconto_banco_percentual deve ser um número' using errcode = '22023';
    end;
    select * into v_f from public.financiamento f where f.id = p_id;
    if not found or not financeiro.pertence_ao_perfil(v_f.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Financiamento não encontrado' using errcode = '22023', hint = 'NAO_ENCONTRADO';
    end if;
    if btrim(p_dados ->> 'data_quitacao') !~ '^\d{4}-\d{2}-\d{2}$' then
        raise exception 'data_quitacao deve estar no formato YYYY-MM-DD' using errcode = '22023';
    end if;
    begin
        v_data := btrim(p_dados ->> 'data_quitacao')::date;
    exception when others then
        raise exception 'data_quitacao deve estar no formato YYYY-MM-DD' using errcode = '22023';
    end;
    if v_desc < 0 or v_desc > 100 then
        raise exception 'desconto_banco_percentual deve estar entre 0 e 100' using errcode = '22023';
    end if;
    v_saldo := coalesce(v_f.saldo_devedor_atual, v_f.valor_financiado);
    if v_saldo <= 0 then
        raise exception 'O financiamento não possui saldo devedor em aberto.' using errcode = '22023';
    end if;
    select count(*), count(*) filter (where p.data_vencimento > v_data), count(*) filter (where p.data_vencimento < financeiro.hoje_brasilia()),
           coalesce(sum(p.valor_juros) filter (where p.data_vencimento > v_data), 0),
           coalesce(sum(p.valor_seguro) filter (where p.data_vencimento > v_data), 0),
           coalesce(sum(p.valor_taxa_adm) filter (where p.data_vencimento > v_data), 0)
      into v_total, v_futuras, v_vencidas, v_juros, v_seguros, v_taxas
      from public.financiamento_parcela p
     where p.financiamento_id = v_f.id
       and p.status not in ('pago', 'paga', 'baixado', 'baixada', 'realizado', 'realizada', 'conciliado', 'conciliada',
                            'amortizado', 'amortizada', 'efetivado', 'efetivada');
    v_sac_tr := financeiro.fin_usa_sac_tr(v_f.sistema_amortizacao, v_f.indexador_saldo, v_f.modo_calculo_financiamento);
    if v_sac_tr then
        v_tr := financeiro.fin_tr(v_data);
        v_estimado := financeiro.fin_r(v_saldo * (1 + v_tr));
    else
        v_estimado := v_saldo;
    end if;
    v_desconto := financeiro.fin_r(v_juros * financeiro.fin_div(v_desc, 100));
    v_obs := jsonb_build_array('Esta é uma simulação estimada. O valor oficial de quitação deve ser confirmado com o banco.',
                               'Juros pro rata diário não incluído nesta simulação.');
    if v_desc > 0 then
        v_obs := v_obs || jsonb_build_array('O desconto informado é apenas uma hipótese para simulação. O percentual real depende da política do banco.');
    end if;
    if v_vencidas > 0 then
        v_obs := v_obs || jsonb_build_array('Há ' || v_vencidas || ' parcela(s) vencida(s) em aberto. O valor oficial pode incluir encargos não considerados nesta simulação.');
    end if;
    if v_sac_tr then
        v_obs := v_obs || jsonb_build_array('TR da competência ' || to_char(v_data, 'YYYY-MM') || ' aplicada: ' || round(v_tr * 100, 4)::text || '%.');
    end if;
    return jsonb_build_object('success', true, 'data', jsonb_build_object(
        'financiamento_id', v_f.id, 'financiamento_nome', v_f.nome, 'data_quitacao', to_char(v_data, 'YYYY-MM-DD'),
        'saldo_devedor_base', v_saldo, 'saldo_devedor_estimado', v_estimado, 'parcelas_restantes_total', v_total,
        'parcelas_futuras_consideradas', v_futuras, 'juros_futuros_estimados', v_juros, 'seguros_futuros_estimados', v_seguros,
        'taxas_futuras_estimadas', v_taxas, 'desconto_estimado', v_desconto,
        'economia_estimada', financeiro.fin_r(v_juros + v_seguros + v_taxas + v_desconto),
        'valor_quitacao_estimado', financeiro.fin_r(v_estimado - v_desconto),
        'modo_calculo', case when v_sac_tr then 'SAC+TR' else v_f.sistema_amortizacao end,
        'competencia_tr', case when v_sac_tr then to_char(v_data, 'YYYY-MM') end, 'tr_aplicada', v_tr, 'observacoes', v_obs));
end
$$;

-- 6. Privilegios -------------------------------------------------------------------------------------------------------

revoke execute on function financeiro.fin_r(numeric) from public, anon, authenticated;
revoke execute on function financeiro.fin_div(numeric, numeric) from public, anon, authenticated;
revoke execute on function financeiro.fin_usa_sac_tr(text, text, text) from public, anon, authenticated;
revoke execute on function financeiro.fin_tr(date) from public, anon, authenticated;
revoke execute on function financeiro.fin_config(public.financiamento) from public, anon, authenticated;
revoke execute on function financeiro.fin_seguro(jsonb, date, numeric, numeric) from public, anon, authenticated;
revoke execute on function financeiro.fin_conta_da_parcela(integer) from public, anon, authenticated;
revoke execute on function financeiro.fin_parcela_elegivel(integer) from public, anon, authenticated;
revoke execute on function financeiro.fin_gravar_despesa(public.financiamento, integer) from public, anon, authenticated;
revoke execute on function financeiro.fin_gerar_sac_tr(public.financiamento, jsonb) from public, anon, authenticated;
revoke execute on function financeiro.fin_pow_int(numeric, integer) from public, anon, authenticated;
revoke execute on function financeiro.fin_taxa_mensal(numeric, text) from public, anon, authenticated;
revoke execute on function financeiro.fin_indexador(text, date) from public, anon, authenticated;
revoke execute on function financeiro.fin_gerar_padrao(public.financiamento, jsonb) from public, anon, authenticated;
revoke execute on function financeiro.fin_gerar(public.financiamento, jsonb) from public, anon, authenticated;
revoke execute on function financeiro.fin_amortizar_padrao(public.financiamento, integer[], numeric, text) from public, anon, authenticated;
revoke execute on function financeiro.fin_ajustar_padrao(public.financiamento, integer[], numeric) from public, anon, authenticated;
revoke execute on function financeiro.fin_atualizar_sac_tr(public.financiamento, integer[], numeric, numeric) from public, anon, authenticated;
revoke execute on function financeiro.exigir_escrita_financiamento(integer) from public, anon, authenticated;
revoke execute on function financeiro.travar_financiamento(integer, integer) from public, anon, authenticated;
revoke execute on function financeiro.fin_possui_execucao(integer) from public, anon, authenticated;
revoke execute on function financeiro.fin_competencia(text) from public, anon, authenticated;
revoke execute on function financeiro.fin_numero(text, text) from public, anon, authenticated;
revoke execute on function financeiro.fin_data(text, text) from public, anon, authenticated;
revoke execute on function financeiro.criar_financiamento(integer, jsonb, uuid) from public, anon;
revoke execute on function financeiro.regenerar_parcelas_financiamento(integer, integer) from public, anon;
revoke execute on function financeiro.registrar_parcelas_historicas(integer, integer, jsonb, uuid) from public, anon;
revoke execute on function financeiro.registrar_amortizacao_extra(integer, integer, jsonb, uuid) from public, anon;
revoke execute on function financeiro.excluir_financiamento(integer, integer) from public, anon;
revoke execute on function financeiro.fin_campo_alterado(text, jsonb, jsonb) from public, anon, authenticated;
revoke execute on function financeiro.fin_recalcular_seguro(integer, date) from public, anon, authenticated;
revoke execute on function financeiro.fin_criar_vigencia(public.financiamento, date, numeric, text) from public, anon, authenticated;
revoke execute on function financeiro.adicionar_vigencia_seguro(integer, integer, jsonb, uuid) from public, anon;
revoke execute on function financeiro.atualizar_financiamento(integer, integer, jsonb, uuid) from public, anon;
grant execute on function financeiro.adicionar_vigencia_seguro(integer, integer, jsonb, uuid) to authenticated;
grant execute on function financeiro.atualizar_financiamento(integer, integer, jsonb, uuid) to authenticated;
revoke execute on function financeiro.ajustar_saldo_devedor(integer, integer, jsonb, uuid) from public, anon;
grant execute on function financeiro.ajustar_saldo_devedor(integer, integer, jsonb, uuid) to authenticated;
revoke execute on function financeiro.simular_quitacao(integer, integer, jsonb) from public, anon;
grant execute on function financeiro.simular_quitacao(integer, integer, jsonb) to authenticated;
grant execute on function financeiro.excluir_financiamento(integer, integer) to authenticated;
grant execute on function financeiro.criar_financiamento(integer, jsonb, uuid) to authenticated;
grant execute on function financeiro.regenerar_parcelas_financiamento(integer, integer) to authenticated;
grant execute on function financeiro.registrar_parcelas_historicas(integer, integer, jsonb, uuid) to authenticated;
grant execute on function financeiro.registrar_amortizacao_extra(integer, integer, jsonb, uuid) to authenticated;
