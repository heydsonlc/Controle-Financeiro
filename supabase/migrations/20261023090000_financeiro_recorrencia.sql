-- FIN-RECORRENCIA-1 — geracao explicita de contas recorrentes, lancamentos
-- recorrentes de cartao e faturas do mes, por perfil financeiro.
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261023090000).
-- Validada em cluster PostgreSQL local descartavel, com comparacao contra o Flask
-- (tests/test_supabase_recorrencia.py). Contrato: docs/FIN_RECORRENCIA_1_CONTRATO.md.
--
-- Regras (decisoes D1-D9 aprovadas):
-- - consulta nunca grava: previa_geracao e STABLE; so gerar_mes (acao explicita e
--   confirmada pelo usuario) grava, numa unica transacao;
-- - periodo: do inicio de cada recorrencia ate o mes pedido + 1 (preenche lacunas);
--   faturas do mes e do seguinte; a confirmacao informa competencias e registros;
-- - so mensal e anual (semanais ficam fora e sao informadas como rejeitadas);
-- - recorrencia inativa nao gera nada (historico preservado);
-- - dia contratual preservado: 31/01 -> 28/02 (29 em ano bissexto) -> 31/03; o
--   mesmo vale para o vencimento das faturas (dias 29-31);
-- - identidade estavel por (recorrencia, natureza, competencia), e nao pela data:
--   conta reconhecida por item + mes_referencia (ou mes do vencimento), compra de
--   cartao pelo compra_id deterministico do Flask (uuid5) ou pelo legado
--   (item, mes_fatura, is_recorrente), fatura por cartao + competencia;
-- - competencia dispensada fica registrada e nao e recriada; registro gerado e
--   depois removido tambem nao e recriado (reativar_competencia desfaz);
-- - item invalido e rejeitado com motivo, sem impedir os validos;
-- - so quem tem permissao EXPLICITA de gestao do perfil gera (pode_gerir);
-- - nenhum pagamento, baixa ou movimento bancario.
--
-- Escreve apenas em public.conta e public.lancamento_agregado (linhas novas) e nas
-- tabelas novas deste schema. Nenhuma estrutura legada e alterada (sem FK para
-- tabelas legadas, para nao criar gatilhos de integridade nelas).

-- uuid5 identico ao do Flask (ja instalada no Supabase, schema extensions).
create extension if not exists "uuid-ossp" with schema extensions;

-- D8: o papel TITULAR e o valor padrao do vinculo e nao comprova gestao; a
-- permissao de gerar e explicita, concedida por administrador.
alter table financeiro.perfil_acesso
    add column pode_gerir boolean not null default false,
    add constraint perfil_acesso_leitor_nao_gere check (not (papel = 'LEITOR' and pode_gerir));

comment on column financeiro.perfil_acesso.pode_gerir is
    'Permissao explicita de gestao (gerar recorrencias e, futuramente, outras escritas). Concedida so por administrador.';

create function financeiro.pode_gerir_perfil(p_perfil_id integer)
    returns boolean
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select exists (
        select 1
          from financeiro.perfil_acesso a
          join public.perfil_financeiro p on p.id = a.perfil_financeiro_id
         where a.user_id = (select auth.uid())
           and a.perfil_financeiro_id = p_perfil_id
           and p.ativo
           and a.pode_gerir
    )
$$;

-- Relatorio verificavel de cada geracao.
create table financeiro.geracao_execucao (
    id                   bigint      generated always as identity primary key,
    perfil_financeiro_id integer     not null,
    mes                  date        not null,
    user_id              uuid        references auth.users (id) on delete set null,
    executado_em         timestamptz not null default now(),
    resumo               jsonb       not null
);

-- Identidade estavel do que o novo motor gerou ou o usuario dispensou.
create table financeiro.recorrencia_competencia (
    item_despesa_id integer     not null,
    natureza        text        not null check (natureza in ('CONTA', 'LANCAMENTO_CARTAO')),
    competencia     date        not null check (extract(day from competencia) = 1),
    situacao        text        not null check (situacao in ('GERADA', 'DISPENSADA')),
    conta_id        integer,
    lancamento_id   integer,
    execucao_id     bigint      references financeiro.geracao_execucao (id),
    motivo          text,
    user_id         uuid        references auth.users (id) on delete set null,
    registrado_em   timestamptz not null default now(),
    primary key (item_despesa_id, natureza, competencia),
    check (situacao <> 'GERADA' or (conta_id is not null) <> (lancamento_id is not null))
);

comment on table financeiro.recorrencia_competencia is
    'FIN-RECORRENCIA-1: competencias geradas pelo novo motor ou dispensadas pelo usuario. Nunca recriadas.';

alter table financeiro.geracao_execucao enable row level security;
alter table financeiro.geracao_execucao force row level security;
alter table financeiro.recorrencia_competencia enable row level security;
alter table financeiro.recorrencia_competencia force row level security;
revoke all on financeiro.geracao_execucao from public, anon, authenticated;
revoke all on financeiro.recorrencia_competencia from public, anon, authenticated;

-- Dia contratual na competencia: o dia original, ou o ultimo do mes se ele nao existir.
create function financeiro.dia_contratual(p_competencia date, p_dia integer)
    returns date
    language sql
    immutable
    set search_path = ''
as $$
    select make_date(
        extract(year from p_competencia)::integer,
        extract(month from p_competencia)::integer,
        least(p_dia, extract(day from (date_trunc('month', p_competencia::timestamp) + interval '1 month - 1 day'))::integer)
    )
$$;

create type financeiro.linha_plano as (
    natureza            text,     -- CONTA | LANCAMENTO_CARTAO | FATURA
    item_despesa_id     integer,  -- recorrencia (ou cartao, na fatura)
    nome                text,
    competencia         date,     -- null quando a rejeicao e do item inteiro
    data_vencimento     date,     -- vencimento (conta/fatura) ou data da compra (cartao)
    valor               numeric,
    situacao            text,     -- A_GERAR | EXISTENTE | DISPENSADA | REJEITADA | INATIVA
    motivo              text,
    registro_id         integer,  -- conta/lancamento ja existente
    perfil_destino      integer,  -- perfil gravado na linha nova (o do item; NULL = legado do Pessoal)
    cartao_id           integer,
    categoria_id        integer,
    categoria_cartao_id integer,
    compra_id           text,
    conta_bancaria_id   integer,
    debito_automatico   boolean,
    observacoes         text
);

-- Plano (somente leitura) da geracao ate p_mes + 1. Interna: sem EXECUTE para o
-- navegador; usada por previa_geracao e gerar_mes, que autorizam antes.
create function financeiro.plano_recorrencia(p_perfil_id integer, p_mes date)
    returns setof financeiro.linha_plano
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_mes     date := date_trunc('month', p_mes::timestamp)::date;
    v_limite  date := (date_trunc('month', p_mes::timestamp) + interval '1 month')::date;
    v_ns      constant uuid := '7f3a1b2c-4d5e-6f7a-8b9c-0d1e2f3a4b5c';  -- namespace do Flask
    v_pessoal boolean;
    v_item    record;
    v_cartao  record;
    v_reg     record;
    v_linha   financeiro.linha_plano;
    v_comp    date;
    v_passo   interval;
    v_dia     integer;
    v_motivo  text;
    v_ccs     integer[];
    v_qtd     integer;
    v_id      integer;
begin
    v_pessoal := exists (select 1 from public.perfil_financeiro p where p.id = p_perfil_id and p.nome = 'Pessoal');

    -- 1) Recorrencias: conta (boleto, debito, pix...) ou compra no cartao.
    for v_item in
        select i.*
          from public.item_despesa i
         where (i.perfil_financeiro_id = p_perfil_id or (i.perfil_financeiro_id is null and v_pessoal))
           and coalesce(i.recorrente, false)
         order by i.id
    loop
        v_linha := null;
        v_linha.natureza := case when v_item.meio_pagamento = 'cartao' then 'LANCAMENTO_CARTAO' else 'CONTA' end;
        v_linha.item_despesa_id := v_item.id;
        v_linha.nome := v_item.nome;
        v_linha.valor := v_item.valor;
        v_linha.perfil_destino := v_item.perfil_financeiro_id;
        v_linha.observacoes := coalesce(v_item.descricao, '');
        v_motivo := null;

        if not coalesce(v_item.ativo, true) then
            v_linha.situacao := 'INATIVA';
            v_linha.motivo := 'Recorrencia inativa: nao gera novos lancamentos';
            return next v_linha;
            continue;
        end if;

        if v_item.tipo = 'Agregador' then
            v_motivo := 'Cartao marcado como recorrencia';
        elsif v_item.data_vencimento is null then
            v_motivo := 'Sem data de vencimento';
        elsif coalesce(v_item.tipo_recorrencia, 'mensal') not in ('mensal', 'anual') then
            v_motivo := 'Tipo de recorrencia fora do escopo: ' || v_item.tipo_recorrencia;
        elsif v_item.valor is null or v_item.valor < 0 then
            v_motivo := 'Sem valor valido';
        elsif v_linha.natureza = 'LANCAMENTO_CARTAO' then
            if v_item.cartao_id is null then
                v_motivo := 'Sem cartao';
            elsif v_item.categoria_id is null then
                v_motivo := 'Sem categoria';
            else
                select c.* into v_cartao
                  from public.item_despesa c
                 where c.id = v_item.cartao_id
                   and c.tipo = 'Agregador'
                   and coalesce(c.ativo, true)
                   and (c.perfil_financeiro_id = p_perfil_id or (c.perfil_financeiro_id is null and v_pessoal));
                if not found then
                    v_motivo := 'Cartao inexistente, inativo ou de outro perfil';
                end if;
            end if;

            -- Categoria do cartao como CategoriaCartaoService.resolver_categoria_cartao_para_lancamento.
            if v_motivo is null then
                v_linha.cartao_id := v_item.cartao_id;
                v_linha.categoria_id := v_item.categoria_id;
                if v_item.categoria_cartao_id is not null then
                    if exists (select 1 from public.categoria_cartao cc
                                where cc.id = v_item.categoria_cartao_id
                                  and (cc.perfil_financeiro_id = p_perfil_id or (cc.perfil_financeiro_id is null and v_pessoal))) then
                        v_linha.categoria_cartao_id := v_item.categoria_cartao_id;
                    else
                        v_motivo := 'Categoria do cartao nao encontrada';
                    end if;
                else
                    select array_agg(v.categoria_cartao_id order by v.id) into v_ccs
                      from public.categoria_cartao_despesa v
                      join public.categoria_cartao cc on cc.id = v.categoria_cartao_id
                     where v.categoria_id = v_item.categoria_id
                       and v.ativo and cc.ativo
                       and (v.perfil_financeiro_id = p_perfil_id or (v.perfil_financeiro_id is null and v_pessoal))
                       and (cc.perfil_financeiro_id = p_perfil_id or (cc.perfil_financeiro_id is null and v_pessoal));
                    if cardinality(v_ccs) > 1 then
                        v_motivo := 'Categoria de despesa com mais de uma categoria do cartao ativa';
                    elsif cardinality(v_ccs) = 1 and exists (
                        select 1 from public.cartao_categoria_limite lim
                          join public.categoria_cartao cc on cc.id = lim.categoria_cartao_id
                         where lim.cartao_id = v_item.cartao_id
                           and lim.categoria_cartao_id = v_ccs[1]
                           and lim.ativo and cc.ativo
                           and (lim.perfil_financeiro_id = p_perfil_id or (lim.perfil_financeiro_id is null and v_pessoal))
                           and (cc.perfil_financeiro_id = p_perfil_id or (cc.perfil_financeiro_id is null and v_pessoal))) then
                        v_linha.categoria_cartao_id := v_ccs[1];
                    end if;
                end if;
            end if;
        else
            v_linha.conta_bancaria_id := v_item.conta_bancaria_id;
            v_linha.debito_automatico := coalesce(v_item.meio_pagamento = 'debito_automatico', false);
        end if;

        if v_motivo is not null then
            v_linha.situacao := 'REJEITADA';
            v_linha.motivo := v_motivo;
            v_linha.cartao_id := null;
            v_linha.categoria_id := null;
            v_linha.categoria_cartao_id := null;
            return next v_linha;
            continue;
        end if;

        v_dia := extract(day from v_item.data_vencimento)::integer;
        v_passo := case when coalesce(v_item.tipo_recorrencia, 'mensal') = 'anual' then interval '1 year' else interval '1 month' end;
        v_comp := date_trunc('month', v_item.data_vencimento::timestamp)::date;
        while v_comp <= v_limite loop
            v_linha.competencia := v_comp;
            v_linha.data_vencimento := financeiro.dia_contratual(v_comp, v_dia);
            v_linha.registro_id := null;
            v_linha.motivo := null;
            v_linha.compra_id := case when v_linha.natureza = 'LANCAMENTO_CARTAO' then
                extensions.uuid_generate_v5(v_ns, format('%s-%s', v_item.id, to_char(v_comp, 'YYYY-MM-DD')))::text end;

            select r.* into v_reg
              from financeiro.recorrencia_competencia r
             where r.item_despesa_id = v_item.id and r.natureza = v_linha.natureza and r.competencia = v_comp;
            if found then
                if v_reg.situacao = 'GERADA' and (
                       exists (select 1 from public.conta c where c.id = v_reg.conta_id)
                    or exists (select 1 from public.lancamento_agregado l where l.id = v_reg.lancamento_id)) then
                    v_linha.situacao := 'EXISTENTE';
                    v_linha.registro_id := coalesce(v_reg.conta_id, v_reg.lancamento_id);
                else
                    v_linha.situacao := 'DISPENSADA';
                    v_linha.motivo := case when v_reg.situacao = 'DISPENSADA'
                                           then coalesce(v_reg.motivo, 'Competencia dispensada')
                                           else 'Registro gerado foi removido; nao sera recriado' end;
                end if;
            else
                -- Reconhece o que o Flask (ou outro caminho) ja gravou, sem depender da data.
                if v_linha.natureza = 'CONTA' then
                    select c.id into v_id
                      from public.conta c
                     where c.item_despesa_id = v_item.id
                       and coalesce(c.is_fatura_cartao, false) = false
                       and (date_trunc('month', c.mes_referencia) = v_comp or date_trunc('month', c.data_vencimento) = v_comp)
                     order by c.id
                     limit 1;
                else
                    select l.id into v_id
                      from public.lancamento_agregado l
                     where l.compra_id = v_linha.compra_id
                        or (l.item_despesa_id = v_item.id and l.mes_fatura = v_comp and l.is_recorrente)
                     order by l.id
                     limit 1;
                end if;
                v_linha.situacao := case when v_id is null then 'A_GERAR' else 'EXISTENTE' end;
                v_linha.registro_id := v_id;
            end if;
            return next v_linha;
            v_comp := (v_comp + v_passo)::date;
        end loop;
    end loop;

    -- 2) Faturas do mes e do seguinte para cada cartao ativo do perfil.
    for v_cartao in
        select c.id, c.nome, c.perfil_financeiro_id, cfg.dia_vencimento
          from public.item_despesa c
          left join public.config_agregador cfg on cfg.item_despesa_id = c.id
         where (c.perfil_financeiro_id = p_perfil_id or (c.perfil_financeiro_id is null and v_pessoal))
           and c.tipo = 'Agregador'
           and coalesce(c.ativo, true)
         order by c.id
    loop
        foreach v_comp in array array[v_mes, v_limite] loop
            v_linha := null;
            v_linha.natureza := 'FATURA';
            v_linha.item_despesa_id := v_cartao.id;
            v_linha.nome := v_cartao.nome;
            v_linha.competencia := v_comp;
            v_linha.perfil_destino := v_cartao.perfil_financeiro_id;
            v_linha.cartao_id := v_cartao.id;

            select c.id into v_id
              from public.conta c
             where c.item_despesa_id = v_cartao.id
               and c.is_fatura_cartao
               and date_trunc('month', c.cartao_competencia) = v_comp
             order by c.id
             limit 1;
            if v_id is not null then
                v_linha.situacao := 'EXISTENTE';
                v_linha.registro_id := v_id;
            elsif v_cartao.dia_vencimento is null or v_cartao.dia_vencimento not between 1 and 31 then
                v_linha.situacao := 'REJEITADA';
                v_linha.motivo := 'Cartao sem dia de vencimento configurado';
            else
                -- Planejado como CartaoService.calcular_planejado: limites ativos do cartao
                -- no perfil; sem limites, orcamento legado vigente por item agregado.
                select count(*), coalesce(sum(lim.limite_mensal), 0) into v_qtd, v_linha.valor
                  from public.cartao_categoria_limite lim
                 where lim.cartao_id = v_cartao.id and lim.perfil_financeiro_id = p_perfil_id and lim.ativo;
                if v_qtd = 0 then
                    select coalesce(sum(o.valor_teto), 0) into v_linha.valor
                      from public.item_agregado ia
                      cross join lateral (
                          select oa.valor_teto
                            from public.orcamento_agregado oa
                           where oa.item_agregado_id = ia.id
                             and oa.ativo
                             and oa.vigencia_inicio <= v_comp
                             and (oa.vigencia_fim is null or oa.vigencia_fim >= v_comp)
                           order by oa.id
                           limit 1
                      ) o
                     where ia.item_despesa_id = v_cartao.id;
                end if;
                v_linha.situacao := 'A_GERAR';
                v_linha.data_vencimento := financeiro.dia_contratual(v_comp, v_cartao.dia_vencimento);
            end if;
            return next v_linha;
        end loop;
    end loop;
end
$$;

-- Previa (somente leitura): o que a geracao faria, para o aviso e a confirmacao.
create function financeiro.previa_geracao(p_perfil_id integer, p_mes date)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_mes date;
    v_resultado jsonb;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if p_mes is null then
        raise exception 'Mes de competencia obrigatorio' using errcode = '22023';
    end if;
    v_mes := date_trunc('month', p_mes::timestamp)::date;

    select jsonb_build_object(
        'mes', v_mes,
        'pode_gerar', financeiro.pode_gerir_perfil(p_perfil_id),
        'limite', 500,
        'a_gerar', count(*) filter (where p.situacao = 'A_GERAR'),
        'existentes', count(*) filter (where p.situacao = 'EXISTENTE'),
        'dispensadas', count(*) filter (where p.situacao = 'DISPENSADA'),
        'rejeitadas', count(*) filter (where p.situacao = 'REJEITADA'),
        'inativas', count(*) filter (where p.situacao = 'INATIVA'),
        'competencias', coalesce(jsonb_agg(distinct p.competencia order by p.competencia) filter (where p.situacao = 'A_GERAR'), '[]'::jsonb),
        'retroativo', coalesce(bool_or(p.competencia < v_mes) filter (where p.situacao = 'A_GERAR'), false),
        'itens', coalesce(jsonb_agg(jsonb_build_object(
                    'natureza', p.natureza, 'item_id', p.item_despesa_id, 'nome', p.nome,
                    'competencia', p.competencia, 'data_vencimento', p.data_vencimento, 'valor', p.valor)
                    order by p.competencia, p.natureza, p.nome, p.item_despesa_id)
                    filter (where p.situacao = 'A_GERAR'), '[]'::jsonb),
        'dispensados', coalesce(jsonb_agg(jsonb_build_object(
                    'natureza', p.natureza, 'item_id', p.item_despesa_id, 'nome', p.nome,
                    'competencia', p.competencia, 'motivo', p.motivo)
                    order by p.competencia, p.nome) filter (where p.situacao = 'DISPENSADA'), '[]'::jsonb),
        'rejeitados', coalesce(jsonb_agg(jsonb_build_object(
                    'natureza', p.natureza, 'item_id', p.item_despesa_id, 'nome', p.nome,
                    'competencia', p.competencia, 'motivo', p.motivo)
                    order by p.nome, p.competencia) filter (where p.situacao = 'REJEITADA'), '[]'::jsonb)
    )
      into v_resultado
      from financeiro.plano_recorrencia(p_perfil_id, v_mes) p;
    -- Extensa: mais competencias que o mes e o seguinte, ou lacunas anteriores ao mes.
    return v_resultado || jsonb_build_object('extenso',
        jsonb_array_length(v_resultado -> 'competencias') > 2 or (v_resultado ->> 'retroativo')::boolean);
end
$$;

-- Geracao (acao explicita, ja confirmada). p_total_previsto e o a_gerar da previa
-- que o usuario confirmou: se o plano mudou, nada e gravado. p_dispensar lista
-- {natureza, item_id, competencia, motivo?} da previa que o usuario desmarcou.
create function financeiro.gerar_mes(p_perfil_id integer, p_mes date, p_total_previsto integer,
                                     p_dispensar jsonb default '[]'::jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_mes        date;
    v_linhas     financeiro.linha_plano[];
    v_linha      financeiro.linha_plano;
    v_disp       record;
    v_a_gerar    integer;
    v_exec       bigint;
    v_id         integer;
    v_contas     integer := 0;
    v_lancs      integer := 0;
    v_faturas    integer := 0;
    v_dispensas  integer := 0;
    v_registros  jsonb := '[]'::jsonb;
    v_resumo     jsonb;
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if p_mes is null or p_total_previsto is null or p_total_previsto < 0 then
        raise exception 'Mes e total previsto sao obrigatorios' using errcode = '22023';
    end if;
    p_dispensar := coalesce(p_dispensar, '[]'::jsonb);
    if jsonb_typeof(p_dispensar) <> 'array' then
        raise exception 'Dispensas devem ser uma lista' using errcode = '22023';
    end if;
    v_mes := date_trunc('month', p_mes::timestamp)::date;

    -- Uma geracao por perfil de cada vez (abas ou cliques concorrentes).
    perform pg_advisory_xact_lock(20261023, p_perfil_id);

    select coalesce(array_agg(p order by p.competencia, p.natureza, p.item_despesa_id), '{}')
      into v_linhas
      from financeiro.plano_recorrencia(p_perfil_id, v_mes) p;
    select count(*) into v_a_gerar from unnest(v_linhas) l where l.situacao = 'A_GERAR';

    if v_a_gerar = 0 and jsonb_array_length(p_dispensar) = 0 then
        return jsonb_build_object('execucao_id', null, 'mes', v_mes,
            'criadas', jsonb_build_object('contas', 0, 'lancamentos', 0, 'faturas', 0, 'total', 0),
            'existentes', (select count(*) from unnest(v_linhas) l where l.situacao = 'EXISTENTE'),
            'dispensadas', (select count(*) from unnest(v_linhas) l where l.situacao = 'DISPENSADA'),
            'dispensadas_agora', 0,
            'rejeitadas', (select count(*) from unnest(v_linhas) l where l.situacao = 'REJEITADA'),
            'registros', '[]'::jsonb);
    end if;
    if v_a_gerar <> p_total_previsto then
        raise exception 'A previa mudou desde a confirmacao (previstos %, agora %). Revise e confirme de novo.',
            p_total_previsto, v_a_gerar;
    end if;
    if v_a_gerar > 500 then
        raise exception 'Geracao excede o limite de 500 registros (%).', v_a_gerar;
    end if;

    insert into financeiro.geracao_execucao (perfil_financeiro_id, mes, user_id, resumo)
    values (p_perfil_id, v_mes, (select auth.uid()), '{}'::jsonb)
    returning id into v_exec;

    for v_disp in
        select d.natureza, d.item_id, date_trunc('month', d.competencia::timestamp)::date as competencia, d.motivo
          from jsonb_to_recordset(p_dispensar) as d(natureza text, item_id integer, competencia date, motivo text)
    loop
        if not exists (select 1 from unnest(v_linhas) l
                        where l.situacao = 'A_GERAR' and l.natureza in ('CONTA', 'LANCAMENTO_CARTAO')
                          and l.natureza = v_disp.natureza and l.item_despesa_id = v_disp.item_id
                          and l.competencia = v_disp.competencia) then
            raise exception 'Dispensa invalida: so competencias a gerar de recorrencias podem ser dispensadas'
                using errcode = '22023';
        end if;
        insert into financeiro.recorrencia_competencia
            (item_despesa_id, natureza, competencia, situacao, execucao_id, motivo, user_id)
        values (v_disp.item_id, v_disp.natureza, v_disp.competencia, 'DISPENSADA', v_exec,
                coalesce(left(nullif(btrim(v_disp.motivo), ''), 200), 'Dispensada pelo usuario'), (select auth.uid()));
        v_dispensas := v_dispensas + 1;
    end loop;

    foreach v_linha in array v_linhas loop
        continue when v_linha.situacao <> 'A_GERAR';
        continue when exists (select 1 from financeiro.recorrencia_competencia r
                               where r.item_despesa_id = v_linha.item_despesa_id and r.natureza = v_linha.natureza
                                 and r.competencia = v_linha.competencia and r.situacao = 'DISPENSADA');
        if v_linha.natureza = 'CONTA' then
            insert into public.conta (perfil_financeiro_id, item_despesa_id, mes_referencia, descricao, valor,
                                      data_vencimento, status_pagamento, debito_automatico, conta_bancaria_id,
                                      observacoes, is_fatura_cartao, estouro_orcamento, status_fatura, criado_em)
            values (v_linha.perfil_destino, v_linha.item_despesa_id, v_linha.competencia, v_linha.nome, v_linha.valor,
                    v_linha.data_vencimento, 'Pendente', v_linha.debito_automatico, v_linha.conta_bancaria_id,
                    v_linha.observacoes, false, false, 'ABERTA', now() at time zone 'utc')
            returning id into v_id;
            insert into financeiro.recorrencia_competencia
                (item_despesa_id, natureza, competencia, situacao, conta_id, execucao_id, user_id)
            values (v_linha.item_despesa_id, 'CONTA', v_linha.competencia, 'GERADA', v_id, v_exec, (select auth.uid()));
            v_contas := v_contas + 1;
        elsif v_linha.natureza = 'LANCAMENTO_CARTAO' then
            insert into public.lancamento_agregado (perfil_financeiro_id, cartao_id, item_agregado_id, categoria_cartao_id,
                                                    categoria_id, descricao, valor, data_compra, mes_fatura,
                                                    numero_parcela, total_parcelas, observacoes, is_recorrente,
                                                    item_despesa_id, compra_id, is_importado, criado_em)
            values (v_linha.perfil_destino, v_linha.cartao_id, null, v_linha.categoria_cartao_id,
                    v_linha.categoria_id, v_linha.nome, v_linha.valor, v_linha.data_vencimento, v_linha.competencia,
                    1, 1, v_linha.observacoes, true,
                    v_linha.item_despesa_id, v_linha.compra_id, false, now() at time zone 'utc')
            returning id into v_id;
            insert into financeiro.recorrencia_competencia
                (item_despesa_id, natureza, competencia, situacao, lancamento_id, execucao_id, user_id)
            values (v_linha.item_despesa_id, 'LANCAMENTO_CARTAO', v_linha.competencia, 'GERADA', v_id, v_exec,
                    (select auth.uid()));
            v_lancs := v_lancs + 1;
        else
            insert into public.conta (perfil_financeiro_id, item_despesa_id, mes_referencia, descricao, valor,
                                      valor_planejado, valor_executado, data_vencimento, status_pagamento,
                                      is_fatura_cartao, cartao_competencia, estouro_orcamento, debito_automatico,
                                      status_fatura, criado_em)
            values (v_linha.perfil_destino, v_linha.item_despesa_id, v_linha.competencia,
                    'Fatura ' || v_linha.nome || ' - ' || to_char(v_linha.competencia, 'MM/YYYY'),
                    v_linha.valor, v_linha.valor, 0, v_linha.data_vencimento, 'Pendente',
                    true, v_linha.competencia, false, false, 'ABERTA', now() at time zone 'utc')
            returning id into v_id;
            v_faturas := v_faturas + 1;
        end if;
        v_registros := v_registros || jsonb_build_object('natureza', v_linha.natureza, 'item_id', v_linha.item_despesa_id,
                                                         'competencia', v_linha.competencia, 'registro_id', v_id);
    end loop;

    v_resumo := jsonb_build_object(
        'execucao_id', v_exec,
        'mes', v_mes,
        'criadas', jsonb_build_object('contas', v_contas, 'lancamentos', v_lancs, 'faturas', v_faturas,
                                      'total', v_contas + v_lancs + v_faturas),
        'existentes', (select count(*) from unnest(v_linhas) l where l.situacao = 'EXISTENTE'),
        'dispensadas', (select count(*) from unnest(v_linhas) l where l.situacao = 'DISPENSADA') + v_dispensas,
        'dispensadas_agora', v_dispensas,
        'rejeitadas', (select count(*) from unnest(v_linhas) l where l.situacao = 'REJEITADA'),
        'rejeicoes', coalesce((select jsonb_agg(jsonb_build_object('item_id', l.item_despesa_id, 'nome', l.nome,
                                                                    'natureza', l.natureza, 'competencia', l.competencia,
                                                                    'motivo', l.motivo))
                                 from unnest(v_linhas) l where l.situacao = 'REJEITADA'), '[]'::jsonb),
        'registros', v_registros);
    update financeiro.geracao_execucao set resumo = v_resumo where id = v_exec;
    return v_resumo;
end
$$;

-- Desfaz uma dispensa (ou a remocao de um registro gerado): a competencia volta a
-- ser gerada na proxima geracao confirmada.
create function financeiro.reativar_competencia(p_perfil_id integer, p_natureza text, p_item_id integer,
                                                p_competencia date)
    returns boolean
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_pessoal boolean;
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    v_pessoal := exists (select 1 from public.perfil_financeiro p where p.id = p_perfil_id and p.nome = 'Pessoal');
    if not exists (select 1 from public.item_despesa i
                    where i.id = p_item_id
                      and (i.perfil_financeiro_id = p_perfil_id or (i.perfil_financeiro_id is null and v_pessoal))) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    perform pg_advisory_xact_lock(20261023, p_perfil_id);

    delete from financeiro.recorrencia_competencia r
     where r.item_despesa_id = p_item_id
       and r.natureza = p_natureza
       and r.competencia = date_trunc('month', p_competencia::timestamp)::date
       and (r.situacao = 'DISPENSADA'
            or (not exists (select 1 from public.conta c where c.id = r.conta_id)
                and not exists (select 1 from public.lancamento_agregado l where l.id = r.lancamento_id)));
    return found;
end
$$;

-- Funcoes nascem com EXECUTE para PUBLIC: revogar; so as de uso do app vao para authenticated.
revoke execute on function financeiro.pode_gerir_perfil(integer) from public, anon;
revoke execute on function financeiro.dia_contratual(date, integer) from public, anon, authenticated;
revoke execute on function financeiro.plano_recorrencia(integer, date) from public, anon, authenticated;
revoke execute on function financeiro.previa_geracao(integer, date) from public, anon;
revoke execute on function financeiro.gerar_mes(integer, date, integer, jsonb) from public, anon;
revoke execute on function financeiro.reativar_competencia(integer, text, integer, date) from public, anon;
grant execute on function financeiro.pode_gerir_perfil(integer) to authenticated;
grant execute on function financeiro.previa_geracao(integer, date) to authenticated;
grant execute on function financeiro.gerar_mes(integer, date, integer, jsonb) to authenticated;
grant execute on function financeiro.reativar_competencia(integer, text, integer, date) to authenticated;
