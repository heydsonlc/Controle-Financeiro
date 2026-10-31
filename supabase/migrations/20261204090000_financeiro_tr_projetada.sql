-- FIN-AJUSTE-FINANCIAMENTO-REAL-01 (Opcao B, decidida pelo titular em 30/10/2026): TR projetada no motor SAC/TR.
--
-- Antes: o motor (como o Flask) exigia TR cadastrada para CADA competencia de parcela recalculada ou gerada, inclusive
-- as futuras (ate 2059); sem a TR futura, ajuste de saldo, amortizacao e cadastro de contrato SAC/TR eram recusados.
-- Agora (fin_tr_info):
-- - TR publicada (public.indice_tr_mensal) sempre prevalece;
-- - competencia DEPOIS da ultima publicada: TR projetada = a ultima publicada, so em memoria durante o calculo, NUNCA
--   gravada em Indexadores; competencia sem TR ENTRE publicadas continua recusada (TR_AUSENTE: dado real faltando);
-- - a parcela calculada com TR projetada fica marcada em financeiro.parcela_tr_projetada, com o saldo e a quota de
--   entrada da cadeia SAC/TR; a tela a mostra como projetada;
-- - ao cadastrar (ou importar) a TR real de uma competencia, as parcelas projetadas dela em diante sao recalculadas pela
--   mesma cadeia (fin_reprojetar_tr): so pendentes sem execucao, so em perfil com escritor NOVO.
-- Parcela paga, historica ou com movimento nunca e recalculada (regras R1-R4 do motor). Nenhum dado existente e alterado.
-- Reversao: supabase/reversao/20261204090000_tr_projetada_anterior.sql.

-- 1. Marca da parcela projetada -----------------------------------------------------------------------------------------

create table financeiro.parcela_tr_projetada (
    parcela_id         integer     primary key references public.financiamento_parcela (id) on delete cascade,
    financiamento_id   integer     not null references public.financiamento (id) on delete cascade,
    competencia        text        not null,
    tr_projetada       numeric     not null,
    competencia_origem text        not null,
    saldo_inicial      numeric     not null,
    quota_anterior     numeric     not null,
    registrado_em      timestamptz not null default now()
);

create index parcela_tr_projetada_financiamento on financeiro.parcela_tr_projetada (financiamento_id, competencia);

comment on table financeiro.parcela_tr_projetada is
    'FIN-AJUSTE-FINANCIAMENTO-REAL-01: parcela SAC/TR calculada com TR projetada (competencia ainda sem TR publicada). Guarda o saldo e a quota de entrada para recalcular quando a TR real chegar.';

alter table financeiro.parcela_tr_projetada enable row level security;
alter table financeiro.parcela_tr_projetada force row level security;
revoke all on financeiro.parcela_tr_projetada from public, anon, authenticated;

-- 2. TR publicada ou projetada ------------------------------------------------------------------------------------------

-- {valor, projetada, origem}: TR publicada da competencia; depois da ultima publicada, a ultima (projetada); sem TR
-- entre publicadas (ou sem TR nenhuma), recusado como antes. Interna.
create function financeiro.fin_tr_info(p_data date)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_competencia text := to_char(p_data, 'YYYY-MM');
    v_valor       numeric;
    v_ultima      public.indice_tr_mensal;
begin
    select i.valor_decimal into v_valor from public.indice_tr_mensal i where i.competencia = v_competencia;
    if found then
        return jsonb_build_object('valor', v_valor, 'projetada', false, 'origem', v_competencia);
    end if;
    select * into v_ultima from public.indice_tr_mensal i order by i.competencia desc limit 1;
    if v_ultima.id is null or v_competencia <= v_ultima.competencia then
        raise exception 'Nao ha TR cadastrada para a competencia %. Cadastre o indice em Indexadores > TR para financiamentos SAC/TR.',
            v_competencia using errcode = '22023', hint = 'TR_AUSENTE';
    end if;
    return jsonb_build_object('valor', v_ultima.valor_decimal, 'projetada', true, 'origem', v_ultima.competencia);
end
$$;

-- Marca (ou desmarca) a parcela conforme a TR usada no calculo, com o estado de entrada da cadeia SAC/TR. Interna.
create function financeiro.fin_marcar_tr(p_parcela_id integer, p_financiamento_id integer, p_data date, p_info jsonb,
                                         p_saldo numeric, p_quota numeric)
    returns void
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
begin
    if coalesce((p_info ->> 'projetada')::boolean, false) then
        insert into financeiro.parcela_tr_projetada (parcela_id, financiamento_id, competencia, tr_projetada, competencia_origem,
                                                     saldo_inicial, quota_anterior)
        values (p_parcela_id, p_financiamento_id, to_char(p_data, 'YYYY-MM'), (p_info ->> 'valor')::numeric, p_info ->> 'origem',
                p_saldo, p_quota)
        on conflict (parcela_id) do update
           set competencia = excluded.competencia, tr_projetada = excluded.tr_projetada,
               competencia_origem = excluded.competencia_origem, saldo_inicial = excluded.saldo_inicial,
               quota_anterior = excluded.quota_anterior, registrado_em = now();
    else
        delete from financeiro.parcela_tr_projetada t where t.parcela_id = p_parcela_id;
    end if;
end
$$;

-- TR real cadastrada para uma competencia: recalcula, em cada contrato com parcela projetada dela em diante, as parcelas
-- pendentes a partir da primeira projetada elegivel, retomando a cadeia SAC/TR do saldo e da quota guardados. So perfil
-- com escritor NOVO (o Flask escreve os demais) e so sem parcela protegida na faixa (senao, fica projetada, como
-- estava). Devolve quantos contratos recalculou. Interna.
create function financeiro.fin_reprojetar_tr(p_competencia text)
    returns integer
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_fin    public.financiamento;
    v_inicio public.financiamento_parcela;
    v_t      financeiro.parcela_tr_projetada;
    v_ids    integer[];
    v_n      integer := 0;
begin
    for v_fin in select f.* from public.financiamento f
                  where exists (select 1 from financeiro.parcela_tr_projetada t
                                 where t.financiamento_id = f.id and t.competencia >= p_competencia)
                    and exists (select 1 from financeiro.gerador_recorrencia g
                                 where g.perfil_financeiro_id = f.perfil_financeiro_id and g.gerador = 'NOVO')
                  order by f.id loop
        perform pg_advisory_xact_lock(20261123, v_fin.perfil_financeiro_id);
        select * into v_fin from public.financiamento f where f.id = v_fin.id for update;
        select p.* into v_inicio from public.financiamento_parcela p
          join financeiro.parcela_tr_projetada t on t.parcela_id = p.id
         where p.financiamento_id = v_fin.id and t.competencia >= p_competencia and financeiro.fin_parcela_elegivel(p.id)
         order by p.numero_parcela limit 1;
        continue when v_inicio.id is null;
        select * into v_t from financeiro.parcela_tr_projetada t where t.parcela_id = v_inicio.id;
        select coalesce(array_agg(p.id order by p.numero_parcela), '{}') into v_ids from public.financiamento_parcela p
         where p.financiamento_id = v_fin.id and p.numero_parcela >= v_inicio.numero_parcela and p.status = 'pendente';
        -- Como o ajuste de saldo: parcela dali em diante paga, historica ou com movimento impede o recalculo.
        continue when exists (select 1 from public.financiamento_parcela p
                               where p.financiamento_id = v_fin.id and p.numero_parcela >= v_inicio.numero_parcela
                                 and not financeiro.fin_parcela_elegivel(p.id));
        perform financeiro.fin_atualizar_sac_tr(v_fin, v_ids, v_t.saldo_inicial, v_t.quota_anterior);
        if v_inicio.numero_parcela = coalesce(v_fin.numero_parcela_base, 0) + 1 then
            update public.financiamento
               set amortizacao_mensal_atual = (select p.valor_amortizacao from public.financiamento_parcela p where p.id = v_ids[1])
             where id = v_fin.id;
        end if;
        v_n := v_n + 1;
    end loop;
    return v_n;
end
$$;

-- 3. Funcoes que passam a usar e marcar a TR projetada (texto anterior + as linhas marcadas) ---------------------------

create or replace function financeiro.fin_tr(p_data date)
    returns numeric
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
begin
    -- FIN-AJUSTE-FINANCIAMENTO-REAL-01: TR publicada ou, depois da ultima publicada, a projetada (fin_tr_info).
    return (financeiro.fin_tr_info(p_data) ->> 'valor')::numeric;
end
$$;

create or replace function financeiro.fin_gerar_sac_tr(p_fin public.financiamento, p_cfg jsonb)
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
    v_tr_info    jsonb;
    v_quota_ini  numeric;
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
        v_tr_info := financeiro.fin_tr_info(v_venc);
        v_tr := (v_tr_info ->> 'valor')::numeric;
        v_quota_ini := v_quota;
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
        perform financeiro.fin_marcar_tr(v_id, p_fin.id, v_venc, v_tr_info, v_saldo, v_quota_ini);
        perform financeiro.fin_gravar_despesa(p_fin, v_id);
        v_geradas := v_geradas + 1;
        v_saldo := v_final;
        v_venc := (v_venc + interval '1 month')::date;  -- relativedelta acumulado
    end loop;
    return v_geradas;
end
$$;

create or replace function financeiro.fin_atualizar_sac_tr(p_fin public.financiamento, p_ids integer[], p_saldo numeric, p_quota numeric)
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
    v_tr_info    jsonb;
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
            delete from financeiro.parcela_tr_projetada t where t.parcela_id = v_id;
            v_quitadas := v_quitadas || v_id;
            continue;
        end if;
        v_tr_info := financeiro.fin_tr_info(v_p.data_vencimento);
        v_tr := (v_tr_info ->> 'valor')::numeric;
        perform financeiro.fin_marcar_tr(v_id, p_fin.id, v_p.data_vencimento, v_tr_info, v_saldo, v_quota);
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

create or replace function financeiro.simular_quitacao(p_perfil_id integer, p_id integer, p_dados jsonb)
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
    v_tr_info  jsonb;
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
        v_tr_info := financeiro.fin_tr_info(v_data);
        v_tr := (v_tr_info ->> 'valor')::numeric;
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
        v_obs := v_obs || jsonb_build_array('TR da competência ' || to_char(v_data, 'YYYY-MM') || ' aplicada: ' || round(v_tr * 100, 4)::text || '%'
            || case when (v_tr_info ->> 'projetada')::boolean
                    then ' (projetada: TR de ' || (v_tr_info ->> 'origem') || ', a última publicada)' else '' end || '.');
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

create or replace function financeiro.financiamento_tela(p_perfil_id integer, p_financiamento_id integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_fin public.financiamento;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    select * into v_fin from public.financiamento f where f.id = p_financiamento_id;
    if not found or not financeiro.pertence_ao_perfil(v_fin.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Financiamento nao encontrado neste perfil' using errcode = '22023';
    end if;
    return financeiro.financiamento_flask(v_fin) || jsonb_build_object(
        -- FinanciamentoParcela.to_dict: saldo apos o pagamento zero vira null ('float(x) if x else None').
        'parcelas', coalesce((select jsonb_agg(to_jsonb(p) || jsonb_build_object('saldo_devedor_apos_pagamento',
                                                                                 nullif(p.saldo_devedor_apos_pagamento, 0))
                                               -- FIN-AJUSTE-FINANCIAMENTO-REAL-01: so na parcela calculada com TR projetada.
                                               || case when exists (select 1 from financeiro.parcela_tr_projetada t
                                                                     where t.parcela_id = p.id)
                                                       then jsonb_build_object('tr_projetada', true) else '{}'::jsonb end
                                               order by p.numero_parcela, p.id) from public.financiamento_parcela p
                               where p.financiamento_id = v_fin.id), '[]'::jsonb),
        'vigencia_seguro_info', financeiro.vigencia_seguro_info(v_fin.id));
end
$$;

create or replace function financeiro.criar_tr(p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_rep   jsonb;
    v_comp  text;
    v_valor numeric;
    v_fonte text := coalesce(nullif(p_dados ->> 'fonte', ''), 'BACEN');
    v_i     public.indice_tr_mensal;
    v_agora timestamp := (now() at time zone 'utc')::timestamp;
begin
    perform financeiro.idx_exigir_acesso(true);
    v_rep := financeiro.idx_repeticao(p_chave, 'CRIAR_TR');
    if v_rep is not null then
        return v_rep;
    end if;
    perform financeiro.idx_travar();
    v_comp := financeiro.idx_competencia(p_dados ->> 'competencia');
    if exists (select 1 from public.indice_tr_mensal i where i.competencia = v_comp) then
        raise exception 'TR da competência % já cadastrada', v_comp using errcode = '22023';
    end if;
    v_valor := financeiro.idx_decimal(p_dados ->> 'valor_percentual');
    insert into public.indice_tr_mensal (ano, mes, competencia, valor_decimal, fonte, criado_em, atualizado_em)
    values (substr(v_comp, 1, 4)::integer, substr(v_comp, 6, 2)::integer, v_comp, v_valor, v_fonte, v_agora, v_agora)
    returning * into v_i;
    perform financeiro.idx_auditar(v_comp, 'CADASTRO', null, v_valor, null, v_fonte);
    perform financeiro.fin_reprojetar_tr(v_comp);  -- FIN-AJUSTE-FINANCIAMENTO-REAL-01
    insert into financeiro.operacao_indexador (chave, user_id, operacao, resultado)
    values (p_chave, (select auth.uid()), 'CRIAR_TR', jsonb_build_object('data', financeiro.idx_tr_json(v_i)));
    return jsonb_build_object('data', financeiro.idx_tr_json(v_i));
end
$$;

create or replace function financeiro.importar_tr(p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_rep       jsonb;
    v_texto     text := p_dados ->> 'texto';
    v_fonte     text := coalesce(nullif(p_dados ->> 'fonte', ''), 'BACEN');
    v_sobre     boolean := coalesce((p_dados ->> 'sobrescrever')::boolean, false);
    v_linha     record;
    v_conteudo  text;
    v_partes    text[];
    v_comp      text;
    v_valor     numeric;
    v_i         public.indice_tr_mensal;
    v_criados   integer := 0;
    v_atual     integer := 0;
    v_ignorados integer := 0;
    v_erros     jsonb := '[]'::jsonb;
    v_agora     timestamp := (now() at time zone 'utc')::timestamp;
    v_resultado jsonb;
    v_primeira  text;
begin
    perform financeiro.idx_exigir_acesso(true);
    v_rep := financeiro.idx_repeticao(p_chave, 'IMPORTAR_TR');
    if v_rep is not null then
        return v_rep;
    end if;
    if v_texto is null or btrim(v_texto) = '' then
        raise exception 'texto é obrigatório' using errcode = '22023';
    end if;
    perform financeiro.idx_travar();
    for v_linha in select t.conteudo, t.numero
                     from regexp_split_to_table(v_texto, E'\r\n|\n|\r') with ordinality as t(conteudo, numero) loop
        v_conteudo := btrim(v_linha.conteudo, E' \t\f\v');
        continue when v_conteudo = '' or lower(v_conteudo) like 'competencia%';
        v_partes := regexp_match(v_conteudo, '^(\d{4}-\d{2})\s*[;,]\s*(.+)$');
        if v_partes is null then
            v_erros := v_erros || jsonb_build_object('linha', v_linha.numero, 'conteudo', v_conteudo,
                                                     'erro', 'Linha deve estar no formato YYYY-MM;valor_percentual');
            continue;
        end if;
        begin
            v_comp := financeiro.idx_competencia(v_partes[1]);
            v_valor := financeiro.idx_decimal(btrim(v_partes[2]));
            select * into v_i from public.indice_tr_mensal i where i.competencia = v_comp for update;
            if found then
                if not v_sobre then
                    v_ignorados := v_ignorados + 1;
                    continue;
                end if;
                if financeiro.idx_tr_usada(v_comp) then
                    raise exception 'Esta TR já é usada em parcelas de financiamento SAC/TR. Para alterar, será necessário revisar ou recalcular os cronogramas afetados em uma etapa própria.'
                        using errcode = '22023';
                end if;
                update public.indice_tr_mensal i set valor_decimal = v_valor, fonte = v_fonte, atualizado_em = v_agora
                 where i.id = v_i.id;
                perform financeiro.idx_auditar(v_comp, 'IMPORTACAO', v_i.valor_decimal, v_valor, v_i.fonte, v_fonte);
                v_primeira := least(coalesce(v_primeira, v_comp), v_comp);
                v_atual := v_atual + 1;
                continue;
            end if;
            insert into public.indice_tr_mensal (ano, mes, competencia, valor_decimal, fonte, criado_em, atualizado_em)
            values (substr(v_comp, 1, 4)::integer, substr(v_comp, 6, 2)::integer, v_comp, v_valor, v_fonte, v_agora, v_agora);
            perform financeiro.idx_auditar(v_comp, 'IMPORTACAO', null, v_valor, null, v_fonte);
            v_primeira := least(coalesce(v_primeira, v_comp), v_comp);
            v_criados := v_criados + 1;
        exception when sqlstate '22023' then
            v_erros := v_erros || jsonb_build_object('linha', v_linha.numero, 'conteudo', v_conteudo, 'erro', sqlerrm);
        end;
    end loop;
    if v_primeira is not null then
        perform financeiro.fin_reprojetar_tr(v_primeira);  -- FIN-AJUSTE-FINANCIAMENTO-REAL-01
    end if;
    v_resultado := jsonb_build_object('criados', v_criados, 'atualizados', v_atual, 'ignorados', v_ignorados, 'erros', v_erros);
    insert into financeiro.operacao_indexador (chave, user_id, operacao, resultado)
    values (p_chave, (select auth.uid()), 'IMPORTAR_TR', v_resultado);
    return v_resultado;
end
$$;

revoke execute on function financeiro.fin_tr_info(date) from public, anon, authenticated;
revoke execute on function financeiro.fin_marcar_tr(integer, integer, date, jsonb, numeric, numeric) from public, anon, authenticated;
revoke execute on function financeiro.fin_reprojetar_tr(text) from public, anon, authenticated;
