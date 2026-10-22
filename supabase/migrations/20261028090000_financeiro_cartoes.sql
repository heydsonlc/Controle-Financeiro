-- FIN-CARTOES-1 — cartoes, compras (a vista e parceladas) e faturas, por perfil. SEM pagamento.
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261028090000).
-- Validada em cluster local descartavel, com comparacao contra o Flask
-- (tests/test_supabase_cartoes.py). Diagnostico e decisoes: docs/FIN_CARTOES_1.md.
--
-- Reutiliza o modelo do Flask, sem estrutura paralela:
-- - cartao = public.item_despesa (tipo 'Agregador') + public.config_agregador;
-- - compra/parcela = public.lancamento_agregado (compra_id agrupa as parcelas);
-- - fatura = public.conta (is_fatura_cartao), unica por cartao+competencia (FIN-FATURA-UNICA-1).
-- Regras (validadas aqui, nunca so no navegador):
-- - parcelas como CartaoService.adicionar_lancamento: parcela n na fatura (mes da 1a + n-1), data da
--   compra + (n-1) meses, centavos distribuidos nas primeiras parcelas (soma exata);
-- - fatura paga (status_pagamento 'Pago' ou status_fatura 'PAGA') nunca recebe compra nova: a parcela
--   vai para a proxima fatura nao paga e as seguintes andam junto, uma por fatura (no Flask o desvio
--   testa um status que ninguem grava);
-- - a fatura do mes e garantida pelo mesmo INSERT do FIN-RECORRENCIA-1 (ON CONFLICT no indice unico)
--   e recalculada como CartaoService.recalcular_fatura (so se nao paga);
-- - editar/excluir so parcelas em fatura aberta (nem paga nem fechada) e que nao sejam de
--   recorrencia; parcelas em fatura paga/fechada ficam (historico); nada fica orfao;
-- - so quem tem gestao explicita (pode_gerir) escreve; versao (md5) + FOR UPDATE; idempotencia por chave;
-- - nunca expoe numero completo nem CVV; nenhum pagamento, estorno, movimento ou saldo.

create table financeiro.operacao_cartao (
    chave                uuid        primary key,
    user_id              uuid        not null references auth.users (id) on delete cascade,
    perfil_financeiro_id integer     not null,
    operacao             text        not null,
    resultado            jsonb       not null,
    criado_em            timestamptz not null default now()
);
comment on table financeiro.operacao_cartao is
    'FIN-CARTOES-1: resultado de cada cadastro (compra/cartao) por chave do cliente.';
alter table financeiro.operacao_cartao enable row level security;
alter table financeiro.operacao_cartao force row level security;
revoke all on financeiro.operacao_cartao from public, anon, authenticated;

-- Fatura paga: o pagamento do Flask grava status_pagamento; status_fatura 'PAGA' tambem conta. Interna.
create function financeiro.fatura_esta_paga(p_conta_id integer)
    returns boolean
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select exists (select 1 from public.conta c
                    where c.id = p_conta_id and (c.status_pagamento = 'Pago' or c.status_fatura = 'PAGA'))
$$;

create function financeiro.fatura_do_mes(p_cartao_id integer, p_competencia date)
    returns integer
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select c.id from public.conta c
     where c.item_despesa_id = p_cartao_id and c.is_fatura_cartao and c.cartao_competencia = p_competencia
     order by c.id limit 1
$$;

-- Planejado como CartaoService.calcular_planejado (limites ativos do perfil; senao orcamento legado). Interna.
create function financeiro.planejado_fatura(p_perfil_id integer, p_cartao_id integer, p_competencia date)
    returns numeric
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_qtd   integer;
    v_total numeric;
begin
    select count(*), coalesce(sum(lim.limite_mensal), 0) into v_qtd, v_total
      from public.cartao_categoria_limite lim
     where lim.cartao_id = p_cartao_id and lim.perfil_financeiro_id = p_perfil_id and lim.ativo;
    if v_qtd = 0 then
        select coalesce(sum(o.valor_teto), 0) into v_total
          from public.item_agregado ia
          cross join lateral (
              select oa.valor_teto from public.orcamento_agregado oa
               where oa.item_agregado_id = ia.id and oa.ativo and oa.vigencia_inicio <= p_competencia
                 and (oa.vigencia_fim is null or oa.vigencia_fim >= p_competencia)
               order by oa.id limit 1) o
         where ia.item_despesa_id = p_cartao_id;
    end if;
    return v_total;
end
$$;

-- Garante a fatura (mesmo INSERT do FIN-RECORRENCIA-1; o indice unico decide). Interna.
create function financeiro.garantir_fatura(p_perfil_id integer, p_cartao_id integer, p_competencia date)
    returns integer
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_id      integer;
    v_cartao  public.item_despesa;
    v_dia     integer;
    v_plan    numeric;
begin
    v_id := financeiro.fatura_do_mes(p_cartao_id, p_competencia);
    if v_id is not null then
        return v_id;
    end if;
    select * into v_cartao from public.item_despesa where id = p_cartao_id;
    select cfg.dia_vencimento into v_dia from public.config_agregador cfg where cfg.item_despesa_id = p_cartao_id;
    if v_dia is null or v_dia not between 1 and 31 then
        raise exception 'Cartao sem dia de vencimento configurado' using errcode = '22023';
    end if;
    v_plan := financeiro.planejado_fatura(p_perfil_id, p_cartao_id, p_competencia);
    insert into public.conta (perfil_financeiro_id, item_despesa_id, mes_referencia, descricao, valor, valor_planejado,
                              valor_executado, data_vencimento, status_pagamento, is_fatura_cartao, cartao_competencia,
                              estouro_orcamento, debito_automatico, status_fatura, criado_em)
    values (v_cartao.perfil_financeiro_id, p_cartao_id, p_competencia,
            'Fatura ' || v_cartao.nome || ' - ' || to_char(p_competencia, 'MM/YYYY'), v_plan, v_plan, 0,
            financeiro.dia_contratual(p_competencia, v_dia), 'Pendente', true, p_competencia, false, false, 'ABERTA',
            now() at time zone 'utc')
    on conflict (item_despesa_id, cartao_competencia) where is_fatura_cartao do nothing
    returning id into v_id;
    return coalesce(v_id, financeiro.fatura_do_mes(p_cartao_id, p_competencia));
end
$$;

-- Como CartaoService.recalcular_fatura: so fatura nao paga; planejado, executado, estouro, valor. Interna.
create function financeiro.recalcular_fatura(p_perfil_id integer, p_cartao_id integer, p_competencia date)
    returns void
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_id       integer;
    v_pessoal  boolean;
    v_plan     numeric;
    v_exec     numeric;
begin
    v_id := financeiro.fatura_do_mes(p_cartao_id, p_competencia);
    if v_id is null or financeiro.fatura_esta_paga(v_id) then
        return;
    end if;
    v_pessoal := exists (select 1 from public.perfil_financeiro p where p.id = p_perfil_id and p.nome = 'Pessoal');
    v_plan := financeiro.planejado_fatura(p_perfil_id, p_cartao_id, p_competencia);
    select coalesce(sum(l.valor), 0) into v_exec from public.lancamento_agregado l
     where l.cartao_id = p_cartao_id and l.mes_fatura = p_competencia
       and (l.perfil_financeiro_id = p_perfil_id or (l.perfil_financeiro_id is null and v_pessoal));
    update public.conta set valor_planejado = v_plan, valor_executado = v_exec, estouro_orcamento = v_exec > v_plan,
                            valor = v_plan
     where id = v_id;
end
$$;

-- Categoria do cartao como resolver_categoria_cartao_para_lancamento (mapa + vinculo ao cartao). Interna.
create function financeiro.resolver_categoria_cartao(p_perfil_id integer, p_cartao_id integer, p_categoria_id integer)
    returns integer
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_ccs integer[];
begin
    select array_agg(v.categoria_cartao_id order by v.id) into v_ccs
      from public.categoria_cartao_despesa v join public.categoria_cartao cc on cc.id = v.categoria_cartao_id
     where v.categoria_id = p_categoria_id and v.ativo and cc.ativo
       and financeiro.pertence_ao_perfil(v.perfil_financeiro_id, p_perfil_id)
       and financeiro.pertence_ao_perfil(cc.perfil_financeiro_id, p_perfil_id);
    if cardinality(v_ccs) > 1 then
        raise exception 'Categoria de despesa com mais de uma categoria do cartao ativa' using errcode = '22023';
    end if;
    if cardinality(v_ccs) = 1 and exists (
        select 1 from public.cartao_categoria_limite lim join public.categoria_cartao cc on cc.id = lim.categoria_cartao_id
         where lim.cartao_id = p_cartao_id and lim.categoria_cartao_id = v_ccs[1] and lim.ativo and cc.ativo
           and financeiro.pertence_ao_perfil(lim.perfil_financeiro_id, p_perfil_id)
           and financeiro.pertence_ao_perfil(cc.perfil_financeiro_id, p_perfil_id)) then
        return v_ccs[1];
    end if;
    return null;
end
$$;

-- Cartao do perfil (ativo, com configuracao) ou erro. Interna.
create function financeiro.cartao_do_perfil(p_perfil_id integer, p_cartao_id integer, p_exigir_ativo boolean)
    returns public.item_despesa
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_cartao public.item_despesa;
begin
    select * into v_cartao from public.item_despesa i
     where i.id = p_cartao_id and i.tipo = 'Agregador' and financeiro.pertence_ao_perfil(i.perfil_financeiro_id, p_perfil_id);
    if not found then
        raise exception 'Cartao nao encontrado neste perfil' using errcode = '42501';
    end if;
    if p_exigir_ativo and not coalesce(v_cartao.ativo, true) then
        raise exception 'Cartao inativo' using errcode = '22023';
    end if;
    return v_cartao;
end
$$;

-- Plano de uma compra (somente leitura): parcelas, valores exatos e fatura de cada uma. Interna.
create function financeiro.plano_compra(p_perfil_id integer, p_dados jsonb)
    returns table (numero integer, total integer, mes_fatura date, data_compra date, valor numeric,
                   redirecionada boolean, fatura_id integer, categoria_id integer, categoria_cartao_id integer,
                   cartao_id integer, descricao text, observacoes text)
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_cartao  public.item_despesa;
    v_valor   numeric;
    v_n       integer;
    v_data    date;
    v_mes     date;
    v_cat     integer;
    v_cc      integer;
    v_desc    text;
    v_cent    bigint;
    v_base    bigint;
    v_resto   bigint;
    v_alvo    date;
    v_fat     integer;
    v_desvio  boolean;
    v_passos  integer;
    v_ant     date;
begin
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' then
        raise exception 'Dados da compra invalidos' using errcode = '22023';
    end if;
    begin
        v_cartao := financeiro.cartao_do_perfil(p_perfil_id, (p_dados ->> 'cartao_id')::integer, true);
    exception when invalid_text_representation then
        raise exception 'Cartao invalido' using errcode = '22023';
    end;
    if not exists (select 1 from public.config_agregador cfg where cfg.item_despesa_id = v_cartao.id
                    and cfg.dia_vencimento between 1 and 31) then
        raise exception 'Cartao sem dia de vencimento configurado' using errcode = '22023';
    end if;
    v_desc := btrim(coalesce(p_dados ->> 'descricao', ''));
    if v_desc = '' or length(v_desc) > 200 then
        raise exception 'Descricao obrigatoria (ate 200 caracteres)' using errcode = '22023';
    end if;
    begin
        v_valor := (p_dados ->> 'valor')::numeric;
        v_n := coalesce((p_dados ->> 'total_parcelas')::integer, 1);
        v_data := (p_dados ->> 'data_compra')::date;
        v_mes := date_trunc('month', (p_dados ->> 'mes_fatura')::date::timestamp)::date;
        v_cat := (p_dados ->> 'categoria_id')::integer;
    exception when others then
        raise exception 'Valor, parcelas, data da compra, mes da fatura ou categoria invalidos' using errcode = '22023';
    end;
    if v_valor is null or v_valor <= 0 or v_valor >= 100000000 or v_valor <> round(v_valor, 2) then
        raise exception 'Valor deve ser positivo, com ate 2 casas decimais' using errcode = '22023';
    end if;
    if v_n is null or v_n not between 1 and 60 or round(v_valor * 100) < v_n then
        raise exception 'Parcelas devem ficar entre 1 e 60 (no minimo R$ 0,01 cada)' using errcode = '22023';
    end if;
    if v_data is null or v_mes is null then
        raise exception 'Data da compra e mes da fatura obrigatorios' using errcode = '22023';
    end if;
    if v_mes < (date_trunc('month', v_data::timestamp) - interval '12 months')::date
       or v_mes > (date_trunc('month', v_data::timestamp) + interval '12 months')::date then
        raise exception 'Mes da fatura deve ficar a ate 12 meses da data da compra' using errcode = '22023';
    end if;
    if v_cat is null or not exists (select 1 from public.categoria c where c.id = v_cat and coalesce(c.ativo, true)) then
        raise exception 'Categoria inexistente ou inativa' using errcode = '22023';
    end if;
    v_cc := financeiro.resolver_categoria_cartao(p_perfil_id, v_cartao.id, v_cat);

    v_cent := round(v_valor * 100)::bigint;
    v_base := v_cent / v_n;
    v_resto := v_cent % v_n;
    for i in 1..v_n loop
        v_alvo := (v_mes + make_interval(months => i - 1))::date;
        if v_ant is not null and v_alvo <= v_ant then  -- desvio desloca as parcelas seguintes (uma por fatura)
            v_alvo := (v_ant + interval '1 month')::date;
        end if;
        v_desvio := v_alvo <> (v_mes + make_interval(months => i - 1))::date;
        v_passos := 0;
        loop  -- fatura paga nao recebe compra nova: proxima nao paga
            v_fat := financeiro.fatura_do_mes(v_cartao.id, v_alvo);
            exit when v_fat is null or not financeiro.fatura_esta_paga(v_fat);
            v_alvo := (v_alvo + interval '1 month')::date;
            v_desvio := true;
            v_passos := v_passos + 1;
            if v_passos > 24 then
                raise exception 'Nao ha fatura aberta nos proximos 24 meses' using errcode = '22023';
            end if;
        end loop;
        v_ant := v_alvo;
        numero := i;
        total := v_n;
        mes_fatura := v_alvo;
        data_compra := (v_data + make_interval(months => i - 1))::date;
        valor := (v_base + case when i <= v_resto then 1 else 0 end)::numeric / 100;
        redirecionada := v_desvio;
        fatura_id := v_fat;
        categoria_id := v_cat;
        categoria_cartao_id := v_cc;
        cartao_id := v_cartao.id;
        descricao := v_desc;
        observacoes := coalesce(p_dados ->> 'observacoes', '');
        return next;
    end loop;
end
$$;

create function financeiro.previa_compra(p_perfil_id integer, p_dados jsonb)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    return (select jsonb_build_object(
                'parcelas', jsonb_agg(jsonb_build_object('numero', p.numero, 'total', p.total, 'mes_fatura', p.mes_fatura,
                                                         'data_compra', p.data_compra, 'valor', p.valor,
                                                         'redirecionada', p.redirecionada) order by p.numero),
                'soma', sum(p.valor))
              from financeiro.plano_compra(p_perfil_id, p_dados) p);
end
$$;

-- Cadastro da compra: todas as parcelas, faturas e recalculos numa transacao; idempotente pela chave.
create function financeiro.criar_compra(p_perfil_id integer, p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_anterior  financeiro.operacao_cartao;
    v_linha     record;
    v_compra    text := gen_random_uuid()::text;
    v_ids       integer[] := '{}';
    v_meses     date[] := '{}';
    v_fatura    integer;
    v_id        integer;
    v_cartao    integer;
    v_resultado jsonb;
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if p_chave is null then
        raise exception 'Chave da operacao obrigatoria' using errcode = '22023';
    end if;
    perform pg_advisory_xact_lock(hashtextextended(p_chave::text, 20261028));
    select * into v_anterior from financeiro.operacao_cartao o where o.chave = p_chave;
    if found then
        if v_anterior.user_id is distinct from (select auth.uid()) or v_anterior.perfil_financeiro_id <> p_perfil_id then
            raise exception 'Chave da operacao ja usada' using errcode = '22023';
        end if;
        return v_anterior.resultado || jsonb_build_object('repetida', true);
    end if;
    perform pg_advisory_xact_lock(20261023, p_perfil_id);  -- mesma trava da geracao (recorrencias do cartao)

    for v_linha in select * from financeiro.plano_compra(p_perfil_id, p_dados) order by numero loop
        v_cartao := v_linha.cartao_id;
        v_fatura := financeiro.garantir_fatura(p_perfil_id, v_linha.cartao_id, v_linha.mes_fatura);
        perform 1 from public.conta where id = v_fatura for update;  -- o pagamento (se vier) espera
        if financeiro.fatura_esta_paga(v_fatura) then
            raise exception 'A fatura de % foi paga durante o cadastro. Revise e tente de novo.',
                to_char(v_linha.mes_fatura, 'MM/YYYY') using errcode = 'P0001';
        end if;
        insert into public.lancamento_agregado (perfil_financeiro_id, cartao_id, item_agregado_id, categoria_cartao_id,
                                                categoria_id, descricao, valor, data_compra, mes_fatura, numero_parcela,
                                                total_parcelas, observacoes, is_recorrente, compra_id, is_importado,
                                                criado_em)
        values (coalesce((select c.perfil_financeiro_id from public.conta c where c.id = v_fatura), p_perfil_id),
                v_linha.cartao_id, null, v_linha.categoria_cartao_id, v_linha.categoria_id, v_linha.descricao,
                v_linha.valor, v_linha.data_compra, v_linha.mes_fatura, v_linha.numero, v_linha.total,
                v_linha.observacoes, false, v_compra, false, now() at time zone 'utc')
        returning id into v_id;
        v_ids := v_ids || v_id;
        if not v_linha.mes_fatura = any(v_meses) then
            v_meses := v_meses || v_linha.mes_fatura;
        end if;
    end loop;
    for i in 1..cardinality(v_meses) loop
        perform financeiro.recalcular_fatura(p_perfil_id, v_cartao, v_meses[i]);
    end loop;
    v_resultado := jsonb_build_object('compra_id', v_compra, 'lancamentos', to_jsonb(v_ids), 'faturas', to_jsonb(v_meses));
    insert into financeiro.operacao_cartao (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'criar_compra', v_resultado);
    return v_resultado;
end
$$;

-- Parcelas da mesma compra (compra_id; sem ele, so a propria). Interna.
create function financeiro.parcelas_da_compra(p_lancamento_id integer)
    returns setof public.lancamento_agregado
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select l2.* from public.lancamento_agregado l
      join public.lancamento_agregado l2
        on l2.id = l.id
        or (l.compra_id is not null and l2.compra_id = l.compra_id and l2.cartao_id = l.cartao_id
            and l2.total_parcelas = l.total_parcelas)
     where l.id = p_lancamento_id
     order by l2.numero_parcela, l2.mes_fatura, l2.id
$$;

create function financeiro.bloqueio_da_parcela(p_lancamento_id integer)
    returns text
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_l   public.lancamento_agregado;
    v_fat integer;
begin
    select * into v_l from public.lancamento_agregado where id = p_lancamento_id;
    if coalesce(v_l.is_recorrente, false) then
        return 'Gerada por recorrencia: edite a recorrencia';
    end if;
    v_fat := financeiro.fatura_do_mes(v_l.cartao_id, v_l.mes_fatura);
    if v_fat is not null and financeiro.fatura_esta_paga(v_fat) then
        return 'Fatura paga: correcao so por estorno';
    end if;
    if v_fat is not null and exists (select 1 from public.conta c where c.id = v_fat and c.status_fatura = 'FECHADA') then
        return 'Fatura fechada (consolidada)';
    end if;
    return null;
end
$$;

create function financeiro.versao_compra(p_lancamento_id integer)
    returns text
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select md5(string_agg(p::text, '|' order by p.id)) from financeiro.parcelas_da_compra(p_lancamento_id) p
$$;

-- Cartoes do perfil: so dados de operacao (dias, limite, final do numero). Nunca numero completo nem CVV.
create function financeiro.cartoes_do_perfil(p_perfil_id integer)
    returns table (id integer, nome text, ativo boolean, dia_fechamento integer, dia_vencimento integer,
                   limite_credito numeric, final_numero text, observacoes text, versao text)
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    return query
        select i.id, i.nome::text, coalesce(i.ativo, true), cfg.dia_fechamento, cfg.dia_vencimento, cfg.limite_credito,
               nullif(right(regexp_replace(coalesce(cfg.numero_cartao, ''), '[^0-9]', '', 'g'), 4), '')::text,
               cfg.observacoes::text, md5(i::text || '|' || coalesce(cfg::text, ''))
          from public.item_despesa i
          left join public.config_agregador cfg on cfg.item_despesa_id = i.id
         where i.tipo = 'Agregador' and financeiro.pertence_ao_perfil(i.perfil_financeiro_id, p_perfil_id)
         order by coalesce(i.ativo, true) desc, i.nome;
end
$$;

-- Faturas do mes por cartao ativo: situacao, executado (compras) e previsto (complemento dos limites,
-- como contas_do_mes). Cartao sem fatura no mes aparece como SEM_FATURA.
create function financeiro.faturas_do_mes(p_perfil_id integer, p_mes date)
    returns table (cartao_id integer, cartao_nome text, fatura_id integer, competencia date, data_vencimento date,
                   situacao text, valor_executado numeric, valor_previsto numeric, compras integer, pode_gerir boolean)
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_mes     date;
    v_pessoal boolean;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    v_mes := date_trunc('month', p_mes::timestamp)::date;
    v_pessoal := exists (select 1 from public.perfil_financeiro p where p.id = p_perfil_id and p.nome = 'Pessoal');
    return query
    with cartoes as (
        select i.id, i.nome from public.item_despesa i
         where i.tipo = 'Agregador' and coalesce(i.ativo, true) and financeiro.pertence_ao_perfil(i.perfil_financeiro_id, p_perfil_id)
    ),
    gastos as (
        select l.cartao_id, l.categoria_cartao_id, sum(l.valor) as gasto, count(*) as qtd
          from public.lancamento_agregado l
         where l.mes_fatura = v_mes and (l.perfil_financeiro_id = p_perfil_id or (l.perfil_financeiro_id is null and v_pessoal))
         group by 1, 2
    )
    select c.id, c.nome::text, f.id, v_mes, f.data_vencimento,
           case when f.id is null then 'SEM_FATURA'
                when f.status_pagamento = 'Pago' or f.status_fatura = 'PAGA' then 'PAGA'
                when f.status_fatura = 'FECHADA' then 'FECHADA' else 'ABERTA' end,
           coalesce((select sum(g.gasto) from gastos g where g.cartao_id = c.id), 0),
           case when f.status_pagamento = 'Pago' then coalesce((select sum(g.gasto) from gastos g where g.cartao_id = c.id), 0)
                else coalesce((select sum(g.gasto) from gastos g where g.cartao_id = c.id), 0)
                     + coalesce((select sum(greatest(lim.limite_mensal - coalesce(g.gasto, 0), 0))
                                   from public.cartao_categoria_limite lim
                                   left join gastos g on g.cartao_id = c.id and g.categoria_cartao_id = lim.categoria_cartao_id
                                  where lim.cartao_id = c.id and lim.ativo), 0) end,
           coalesce((select sum(g.qtd) from gastos g where g.cartao_id = c.id), 0)::integer,
           financeiro.pode_gerir_perfil(p_perfil_id)
      from cartoes c
      left join public.conta f on f.id = financeiro.fatura_do_mes(c.id, v_mes)
     order by c.nome;
end
$$;

-- Compras de um cartao numa competencia, com parcela e permissao de cada uma.
create function financeiro.compras_da_fatura(p_perfil_id integer, p_cartao_id integer, p_mes date)
    returns table (id integer, descricao text, valor numeric, data_compra date, numero_parcela integer,
                   total_parcelas integer, categoria_nome text, recorrente boolean, bloqueio text, pode_editar boolean)
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_pessoal boolean;
    v_gerir   boolean;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    perform financeiro.cartao_do_perfil(p_perfil_id, p_cartao_id, false);
    v_pessoal := exists (select 1 from public.perfil_financeiro p where p.id = p_perfil_id and p.nome = 'Pessoal');
    v_gerir := financeiro.pode_gerir_perfil(p_perfil_id);
    return query
        select l.id, coalesce(nullif(l.descricao_exibida, ''), l.descricao)::text, l.valor, l.data_compra,
               l.numero_parcela, l.total_parcelas, cat.nome::text, coalesce(l.is_recorrente, false),
               financeiro.bloqueio_da_parcela(l.id), v_gerir and financeiro.bloqueio_da_parcela(l.id) is null
          from public.lancamento_agregado l
          left join public.categoria cat on cat.id = l.categoria_id
         where l.cartao_id = p_cartao_id and l.mes_fatura = date_trunc('month', p_mes::timestamp)::date
           and (l.perfil_financeiro_id = p_perfil_id or (l.perfil_financeiro_id is null and v_pessoal))
         order by l.data_compra, l.id;
end
$$;

-- Parcelas de uma compra, permissoes e versao (para editar/excluir).
create function financeiro.compra_para_edicao(p_perfil_id integer, p_lancamento_id integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_l public.lancamento_agregado;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    select * into v_l from public.lancamento_agregado where id = p_lancamento_id;
    if not found or not financeiro.pertence_ao_perfil(v_l.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Compra nao encontrada neste perfil' using errcode = '42501';
    end if;
    return jsonb_build_object(
        'compra', jsonb_build_object('lancamento_id', v_l.id, 'cartao_id', v_l.cartao_id, 'descricao', v_l.descricao,
                                     'categoria_id', v_l.categoria_id, 'observacoes', v_l.observacoes,
                                     'valor', v_l.valor, 'data_compra', v_l.data_compra, 'mes_fatura', v_l.mes_fatura,
                                     'total_parcelas', v_l.total_parcelas, 'recorrente', coalesce(v_l.is_recorrente, false)),
        'parcelas', (select jsonb_agg(jsonb_build_object('id', p.id, 'numero', p.numero_parcela, 'total', p.total_parcelas,
                                                         'mes_fatura', p.mes_fatura, 'valor', p.valor,
                                                         'bloqueio', financeiro.bloqueio_da_parcela(p.id)) order by p.numero_parcela)
                       from financeiro.parcelas_da_compra(p_lancamento_id) p),
        'abertas', (select count(*) from financeiro.parcelas_da_compra(p_lancamento_id) p
                     where financeiro.bloqueio_da_parcela(p.id) is null),
        'pode_gerir', financeiro.pode_gerir_perfil(p_perfil_id),
        'versao', financeiro.versao_compra(p_lancamento_id));
end
$$;

-- Trava faturas e parcelas da compra e confere perfil e versao; devolve as parcelas abertas. Interna.
create function financeiro.travar_compra(p_perfil_id integer, p_lancamento_id integer, p_versao text)
    returns integer[]
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_l      public.lancamento_agregado;
    v_abertas integer[];
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    select * into v_l from public.lancamento_agregado where id = p_lancamento_id;
    if not found or not financeiro.pertence_ao_perfil(v_l.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Compra nao encontrada neste perfil' using errcode = '42501';
    end if;
    perform pg_advisory_xact_lock(20261023, p_perfil_id);  -- mesma trava da geracao (recorrencias do cartao)
    -- Faturas das parcelas primeiro (um pagamento simultaneo espera), depois as parcelas.
    perform 1 from public.conta c
     where c.is_fatura_cartao and c.item_despesa_id = v_l.cartao_id
       and c.cartao_competencia in (select p.mes_fatura from financeiro.parcelas_da_compra(p_lancamento_id) p)
     order by c.id for update;
    perform 1 from public.lancamento_agregado l
     where l.id in (select p.id from financeiro.parcelas_da_compra(p_lancamento_id) p) order by l.id for update;
    if p_versao is null or p_versao is distinct from financeiro.versao_compra(p_lancamento_id) then
        raise exception 'A compra foi alterada por outra operacao. Recarregue e tente de novo.'
            using errcode = 'P0001', hint = 'VERSAO';
    end if;
    select coalesce(array_agg(p.id order by p.numero_parcela), '{}') into v_abertas
      from financeiro.parcelas_da_compra(p_lancamento_id) p where financeiro.bloqueio_da_parcela(p.id) is null;
    if cardinality(v_abertas) = 0 then
        raise exception 'Operacao bloqueada: %', financeiro.bloqueio_da_parcela(p_lancamento_id)
            using errcode = 'P0001', hint = 'BLOQUEIO';
    end if;
    return v_abertas;
end
$$;

-- Edicao: descricao, categoria e observacoes das parcelas em fatura aberta. A vista (1 parcela),
-- tambem valor, data da compra e mes da fatura. Parcelas em fatura paga/fechada ficam como estao.
create function financeiro.editar_compra(p_perfil_id integer, p_lancamento_id integer, p_versao text, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_abertas integer[];
    v_l       public.lancamento_agregado;
    v_desc    text;
    v_cat     integer;
    v_cc      integer;
    v_valor   numeric;
    v_data    date;
    v_mes     date;
    v_meses   date[];
    v_fatura  integer;
begin
    v_abertas := financeiro.travar_compra(p_perfil_id, p_lancamento_id, p_versao);
    select * into v_l from public.lancamento_agregado where id = p_lancamento_id;
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' then
        raise exception 'Dados da compra invalidos' using errcode = '22023';
    end if;
    if p_dados ? 'descricao' then
        v_desc := btrim(coalesce(p_dados ->> 'descricao', ''));
        if v_desc = '' or length(v_desc) > 200 then
            raise exception 'Descricao obrigatoria (ate 200 caracteres)' using errcode = '22023';
        end if;
    end if;
    if p_dados ? 'categoria_id' then
        v_cat := (p_dados ->> 'categoria_id')::integer;
        if not exists (select 1 from public.categoria c where c.id = v_cat and coalesce(c.ativo, true)) then
            raise exception 'Categoria inexistente ou inativa' using errcode = '22023';
        end if;
        v_cc := financeiro.resolver_categoria_cartao(p_perfil_id, v_l.cartao_id, v_cat);
    end if;
    if p_dados ?| array['valor', 'data_compra', 'mes_fatura'] then
        if coalesce(v_l.total_parcelas, 1) > 1 then
            raise exception 'Compra parcelada: valor e datas nao mudam aqui (exclua as parcelas abertas e lance de novo)'
                using errcode = '22023';
        end if;
        v_valor := coalesce((p_dados ->> 'valor')::numeric, v_l.valor);
        if v_valor <= 0 or v_valor >= 100000000 or v_valor <> round(v_valor, 2) then
            raise exception 'Valor deve ser positivo, com ate 2 casas decimais' using errcode = '22023';
        end if;
        v_data := coalesce((p_dados ->> 'data_compra')::date, v_l.data_compra);
        v_mes := coalesce(date_trunc('month', (p_dados ->> 'mes_fatura')::date::timestamp)::date, v_l.mes_fatura);
        if v_mes <> v_l.mes_fatura then
            v_fatura := financeiro.garantir_fatura(p_perfil_id, v_l.cartao_id, v_mes);
            perform 1 from public.conta where id = v_fatura for update;
            if financeiro.fatura_esta_paga(v_fatura) then
                raise exception 'A fatura de destino ja esta paga' using errcode = '22023';
            end if;
        end if;
    end if;
    select array_agg(distinct l.mes_fatura) into v_meses from public.lancamento_agregado l where l.id = any(v_abertas);
    update public.lancamento_agregado l
       set descricao = coalesce(v_desc, l.descricao),
           categoria_id = coalesce(v_cat, l.categoria_id),
           categoria_cartao_id = case when p_dados ? 'categoria_id' then v_cc else l.categoria_cartao_id end,
           observacoes = case when p_dados ? 'observacoes' then coalesce(p_dados ->> 'observacoes', '') else l.observacoes end,
           valor = coalesce(v_valor, l.valor),
           data_compra = coalesce(v_data, l.data_compra),
           mes_fatura = coalesce(v_mes, l.mes_fatura)
     where l.id = any(v_abertas);
    if v_mes is not null and not v_mes = any(v_meses) then
        v_meses := v_meses || v_mes;
    end if;
    for i in 1..cardinality(v_meses) loop
        perform financeiro.recalcular_fatura(p_perfil_id, v_l.cartao_id, v_meses[i]);
    end loop;
    return jsonb_build_object('lancamentos', to_jsonb(v_abertas), 'versao', financeiro.versao_compra(p_lancamento_id));
end
$$;

-- Exclusao: remove as parcelas em fatura aberta (a compra inteira, se todas estiverem abertas).
-- Parcelas em fatura paga/fechada ficam (historico) com o mesmo compra_id: nada fica orfao.
create function financeiro.excluir_compra(p_perfil_id integer, p_lancamento_id integer, p_versao text)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_abertas integer[];
    v_l       public.lancamento_agregado;
    v_meses   date[];
    v_total   integer;
begin
    v_abertas := financeiro.travar_compra(p_perfil_id, p_lancamento_id, p_versao);
    select * into v_l from public.lancamento_agregado where id = p_lancamento_id;
    select count(*) into v_total from financeiro.parcelas_da_compra(p_lancamento_id);
    select array_agg(distinct l.mes_fatura) into v_meses from public.lancamento_agregado l where l.id = any(v_abertas);
    delete from public.lancamento_agregado where id = any(v_abertas);
    for i in 1..cardinality(v_meses) loop
        perform financeiro.recalcular_fatura(p_perfil_id, v_l.cartao_id, v_meses[i]);
    end loop;
    return jsonb_build_object('excluidas', cardinality(v_abertas), 'preservadas', v_total - cardinality(v_abertas));
end
$$;

-- Cartoes: cadastro (como POST /api/cartoes, sem numero/CVV), edicao e inativacao (o "excluir" do Flask).
create function financeiro.ler_dados_cartao(p_dados jsonb, p_parcial boolean)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_saida jsonb := '{}'::jsonb;
    v_texto text;
    v_int   integer;
    v_valor numeric;
begin
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' then
        raise exception 'Dados do cartao invalidos' using errcode = '22023';
    end if;
    if p_dados ?| array['numero_cartao', 'codigo_seguranca', 'data_validade'] then
        raise exception 'Numero, validade e codigo de seguranca nao sao tratados no novo aplicativo' using errcode = '22023';
    end if;
    if p_dados ? 'nome' or not p_parcial then
        v_texto := btrim(coalesce(p_dados ->> 'nome', ''));
        if v_texto = '' or length(v_texto) > 100 then
            raise exception 'Nome do cartao obrigatorio (ate 100 caracteres)' using errcode = '22023';
        end if;
        v_saida := v_saida || jsonb_build_object('nome', v_texto);
    end if;
    foreach v_texto in array array['dia_fechamento', 'dia_vencimento'] loop
        if p_dados ? v_texto or not p_parcial then
            begin
                v_int := (p_dados ->> v_texto)::integer;
            exception when others then
                v_int := null;
            end;
            if v_int is null or v_int not between 1 and 31 then
                raise exception 'Dias de fechamento e vencimento devem ficar entre 1 e 31' using errcode = '22023';
            end if;
            v_saida := v_saida || jsonb_build_object(v_texto, v_int);
        end if;
    end loop;
    if p_dados ? 'limite_credito' then
        if nullif(p_dados ->> 'limite_credito', '') is null then
            v_saida := v_saida || jsonb_build_object('limite_credito', null);
        else
            begin
                v_valor := (p_dados ->> 'limite_credito')::numeric;
            exception when others then
                v_valor := null;
            end;
            if v_valor is null or v_valor < 0 or v_valor >= 100000000 or v_valor <> round(v_valor, 2) then
                raise exception 'Limite de credito invalido' using errcode = '22023';
            end if;
            v_saida := v_saida || jsonb_build_object('limite_credito', v_valor);
        end if;
    end if;
    if p_dados ? 'observacoes' then
        v_saida := v_saida || jsonb_build_object('observacoes', left(coalesce(p_dados ->> 'observacoes', ''), 1000));
    end if;
    return v_saida;
end
$$;

create function financeiro.criar_cartao(p_perfil_id integer, p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_anterior financeiro.operacao_cartao;
    v_d        jsonb;
    v_cat      integer;
    v_id       integer;
    v_res      jsonb;
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if p_chave is null then
        raise exception 'Chave da operacao obrigatoria' using errcode = '22023';
    end if;
    perform pg_advisory_xact_lock(hashtextextended(p_chave::text, 20261028));
    select * into v_anterior from financeiro.operacao_cartao o where o.chave = p_chave;
    if found then
        if v_anterior.user_id is distinct from (select auth.uid()) or v_anterior.perfil_financeiro_id <> p_perfil_id then
            raise exception 'Chave da operacao ja usada' using errcode = '22023';
        end if;
        return v_anterior.resultado || jsonb_build_object('repetida', true);
    end if;
    v_d := financeiro.ler_dados_cartao(p_dados, false);
    select c.id into v_cat from public.categoria c where c.nome = 'Cartoes de Credito' order by c.id limit 1;  -- como o Flask
    insert into public.item_despesa (perfil_financeiro_id, categoria_id, nome, tipo, descricao, ativo, recorrente,
                                     tipo_recorrencia, pago, criado_em)
    values (p_perfil_id, v_cat, v_d ->> 'nome', 'Agregador', '', true, true, 'mensal', false, now() at time zone 'utc')
    returning id into v_id;
    insert into public.config_agregador (item_despesa_id, dia_fechamento, dia_vencimento, limite_credito, tem_codigo,
                                         observacoes, criado_em)
    values (v_id, (v_d ->> 'dia_fechamento')::integer, (v_d ->> 'dia_vencimento')::integer,
            (v_d ->> 'limite_credito')::numeric, true, coalesce(v_d ->> 'observacoes', ''), now() at time zone 'utc');
    v_res := jsonb_build_object('cartao_id', v_id);
    insert into financeiro.operacao_cartao (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'criar_cartao', v_res);
    return v_res;
end
$$;

create function financeiro.editar_cartao(p_perfil_id integer, p_cartao_id integer, p_versao text, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_d jsonb;
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    perform financeiro.cartao_do_perfil(p_perfil_id, p_cartao_id, false);
    perform 1 from public.item_despesa where id = p_cartao_id for update;
    perform 1 from public.config_agregador where item_despesa_id = p_cartao_id for update;
    if p_versao is distinct from (select c.versao from financeiro.cartoes_do_perfil(p_perfil_id) c where c.id = p_cartao_id) then
        raise exception 'O cartao foi alterado por outra operacao. Recarregue e tente de novo.' using errcode = 'P0001';
    end if;
    v_d := financeiro.ler_dados_cartao(p_dados, true);
    update public.item_despesa set nome = coalesce(v_d ->> 'nome', nome) where id = p_cartao_id;
    -- Faturas ja criadas mantem o vencimento gravado; o novo dia vale para as proximas.
    update public.config_agregador cfg
       set dia_fechamento = coalesce((v_d ->> 'dia_fechamento')::integer, cfg.dia_fechamento),
           dia_vencimento = coalesce((v_d ->> 'dia_vencimento')::integer, cfg.dia_vencimento),
           limite_credito = case when v_d ? 'limite_credito' then (v_d ->> 'limite_credito')::numeric else cfg.limite_credito end,
           observacoes = case when v_d ? 'observacoes' then v_d ->> 'observacoes' else cfg.observacoes end
     where cfg.item_despesa_id = p_cartao_id;
    return jsonb_build_object('cartao_id', p_cartao_id);
end
$$;

create function financeiro.inativar_cartao(p_perfil_id integer, p_cartao_id integer, p_versao text)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    perform financeiro.cartao_do_perfil(p_perfil_id, p_cartao_id, false);
    perform 1 from public.item_despesa where id = p_cartao_id for update;
    if p_versao is distinct from (select c.versao from financeiro.cartoes_do_perfil(p_perfil_id) c where c.id = p_cartao_id) then
        raise exception 'O cartao foi alterado por outra operacao. Recarregue e tente de novo.' using errcode = 'P0001';
    end if;
    update public.item_despesa set ativo = false where id = p_cartao_id;  -- nunca exclusao fisica
    return jsonb_build_object('cartao_id', p_cartao_id, 'ativo', false);
end
$$;

revoke execute on function financeiro.fatura_esta_paga(integer) from public, anon, authenticated;
revoke execute on function financeiro.fatura_do_mes(integer, date) from public, anon, authenticated;
revoke execute on function financeiro.planejado_fatura(integer, integer, date) from public, anon, authenticated;
revoke execute on function financeiro.garantir_fatura(integer, integer, date) from public, anon, authenticated;
revoke execute on function financeiro.recalcular_fatura(integer, integer, date) from public, anon, authenticated;
revoke execute on function financeiro.resolver_categoria_cartao(integer, integer, integer) from public, anon, authenticated;
revoke execute on function financeiro.cartao_do_perfil(integer, integer, boolean) from public, anon, authenticated;
revoke execute on function financeiro.plano_compra(integer, jsonb) from public, anon, authenticated;
revoke execute on function financeiro.parcelas_da_compra(integer) from public, anon, authenticated;
revoke execute on function financeiro.bloqueio_da_parcela(integer) from public, anon, authenticated;
revoke execute on function financeiro.versao_compra(integer) from public, anon, authenticated;
revoke execute on function financeiro.travar_compra(integer, integer, text) from public, anon, authenticated;
revoke execute on function financeiro.ler_dados_cartao(jsonb, boolean) from public, anon, authenticated;
revoke execute on function financeiro.cartoes_do_perfil(integer) from public, anon;
revoke execute on function financeiro.faturas_do_mes(integer, date) from public, anon;
revoke execute on function financeiro.compras_da_fatura(integer, integer, date) from public, anon;
revoke execute on function financeiro.compra_para_edicao(integer, integer) from public, anon;
revoke execute on function financeiro.previa_compra(integer, jsonb) from public, anon;
revoke execute on function financeiro.criar_compra(integer, jsonb, uuid) from public, anon;
revoke execute on function financeiro.editar_compra(integer, integer, text, jsonb) from public, anon;
revoke execute on function financeiro.excluir_compra(integer, integer, text) from public, anon;
revoke execute on function financeiro.criar_cartao(integer, jsonb, uuid) from public, anon;
revoke execute on function financeiro.editar_cartao(integer, integer, text, jsonb) from public, anon;
revoke execute on function financeiro.inativar_cartao(integer, integer, text) from public, anon;
grant execute on function financeiro.cartoes_do_perfil(integer) to authenticated;
grant execute on function financeiro.faturas_do_mes(integer, date) to authenticated;
grant execute on function financeiro.compras_da_fatura(integer, integer, date) to authenticated;
grant execute on function financeiro.compra_para_edicao(integer, integer) to authenticated;
grant execute on function financeiro.previa_compra(integer, jsonb) to authenticated;
grant execute on function financeiro.criar_compra(integer, jsonb, uuid) to authenticated;
grant execute on function financeiro.editar_compra(integer, integer, text, jsonb) to authenticated;
grant execute on function financeiro.excluir_compra(integer, integer, text) to authenticated;
grant execute on function financeiro.criar_cartao(integer, jsonb, uuid) to authenticated;
grant execute on function financeiro.editar_cartao(integer, integer, text, jsonb) to authenticated;
grant execute on function financeiro.inativar_cartao(integer, integer, text) to authenticated;
