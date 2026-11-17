-- FIN-CATEGORIAS-REORGANIZACAO-01 — reclassificacao controlada de categorias, natureza gerencial e sugestao da importacao.
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261229090000). Aplicar depois de 20261228090000.
-- Validada em cluster local descartavel (tests/test_supabase_categorias_reorganizacao.py) e ensaiada numa copia fiel da
-- producao (scripts/reorganizar_categorias.py). Doc: docs/FIN_CATEGORIAS_REORGANIZACAO_01.md.
-- Reversao: supabase/reversao/20261229090000_categorias_reorganizacao_anterior.sql.
--
-- NENHUM DADO e alterado por esta migration: ela so cria uma tabela vazia e funcoes. As categorias novas, a incorporacao,
-- as reclassificacoes, as naturezas e as palavras-chave sao aplicadas depois, com autorizacao, pelo roteiro
-- scripts/reorganizar_categorias.py (previa conferida pelo hash, uma transacao, auditoria e inversa).
--
-- 1. Natureza gerencial da categoria (CONSUMO, APORTE, AJUSTE_TECNICO, TRANSFERENCIA_INTERNA, NAO_DEFINIDO), em tabela
--    propria do schema financeiro (o public.categoria, do Flask, nao muda). Sem linha = CONSUMO, como hoje. Nunca pelo nome.
-- 2. Reclassificacao: troca SO a coluna categoria_id de itens de despesa e de compras de cartao indicados num manifesto
--    (as contas herdam a categoria do item: nenhuma linha de conta, valor, vencimento, pagamento, fatura ou movimento e
--    tocada). Previa com hash, execucao transacional e idempotente, auditoria em operacao_catalogo e funcao inversa.
-- 3. Importacao: a categoria do historico so vale como sugestao quando nao e de natureza NAO_DEFINIDO (ex.: Outros); a
--    escolha do usuario e as compras antigas nao mudam.
-- 4. Leituras gerenciais: indicadores do mes por natureza (o mesmo conjunto que o Dashboard soma, sem dupla contagem) e a
--    posicao dos consorcios classificados como aporte (aportes, resgate, retorno de capital e ganho).
--
-- Funcao existente substituida pelo texto vigente com o trecho marcado "FIN-CATEGORIAS-REORGANIZACAO-01":
-- sugestao_categoria_importacao (texto de 20261105090000).

-- =====================================================================================================================
-- 1. Natureza gerencial
-- =====================================================================================================================
-- Sem chave estrangeira para public.categoria de proposito: a incorporacao de categorias reaponta toda tabela que a
-- referencia, e a natureza e da propria categoria (a linha de uma categoria excluida fica orfa e e ignorada nas leituras).
create table financeiro.categoria_natureza (
    categoria_id   integer     primary key,
    natureza       text        not null check (natureza in ('CONSUMO', 'APORTE', 'AJUSTE_TECNICO', 'TRANSFERENCIA_INTERNA', 'NAO_DEFINIDO')),
    atualizado_em  timestamptz not null default now(),
    atualizado_por uuid        references auth.users (id) on delete set null
);

alter table financeiro.categoria_natureza enable row level security;
revoke all on table financeiro.categoria_natureza from public, anon, authenticated;

comment on table financeiro.categoria_natureza is
    'FIN-CATEGORIAS-REORGANIZACAO-01: natureza gerencial da Categoria de Despesa. Sem linha = CONSUMO. So pelas funcoes.';

-- Natureza de uma categoria. Sem categoria = NAO_DEFINIDO; categoria sem linha = CONSUMO. Interna.
create function financeiro.natureza_da_categoria(p_categoria_id integer)
    returns text
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select case when p_categoria_id is null then 'NAO_DEFINIDO'
                else coalesce((select n.natureza from financeiro.categoria_natureza n where n.categoria_id = p_categoria_id), 'CONSUMO') end
$$;

-- Leitura para as telas: a natureza de cada categoria do catalogo.
create function financeiro.naturezas_das_categorias()
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
begin
    if (select auth.uid()) is null then
        raise exception 'Sessao obrigatoria' using errcode = '42501';
    end if;
    return (select coalesce(jsonb_agg(jsonb_build_object(
                       'categoria_id', c.id, 'nome', c.nome, 'ativo', coalesce(c.ativo, true),
                       'natureza', financeiro.natureza_da_categoria(c.id),
                       'definida', exists (select 1 from financeiro.categoria_natureza n where n.categoria_id = c.id))
                   order by c.nome, c.id), '[]'::jsonb)
              from public.categoria c);
end
$$;

-- Define a natureza (so quem administra o catalogo); p_natureza nula retira a linha (volta ao padrao, CONSUMO).
-- Idempotente pela chave; auditoria com o valor anterior.
create function financeiro.definir_natureza_categoria(p_categoria_id integer, p_natureza text, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_anterior financeiro.operacao_catalogo;
    v_antes    text;
    v_tinha    boolean;
    v_res      jsonb;
begin
    perform financeiro.exigir_escrita_catalogo();
    if p_chave is null then
        raise exception 'Chave da operacao obrigatoria' using errcode = '22023';
    end if;
    select * into v_anterior from financeiro.operacao_catalogo o where o.chave = p_chave;
    if found then
        if v_anterior.user_id is distinct from (select auth.uid()) or v_anterior.operacao <> 'definir_natureza_categoria' then
            raise exception 'Chave da operacao ja usada' using errcode = '22023';
        end if;
        return v_anterior.resultado || jsonb_build_object('repetida', true);
    end if;
    if p_natureza is not null and p_natureza not in ('CONSUMO', 'APORTE', 'AJUSTE_TECNICO', 'TRANSFERENCIA_INTERNA', 'NAO_DEFINIDO') then
        raise exception 'Natureza gerencial invalida' using errcode = '22023';
    end if;
    perform 1 from public.categoria c where c.id = p_categoria_id for update;
    if not found then
        raise exception 'Categoria de Despesa nao encontrada' using errcode = 'P0001', hint = 'NAO_ENCONTRADA';
    end if;
    select n.natureza into v_antes from financeiro.categoria_natureza n where n.categoria_id = p_categoria_id for update;
    v_tinha := found;
    if p_natureza is null then
        delete from financeiro.categoria_natureza n where n.categoria_id = p_categoria_id;
    else
        insert into financeiro.categoria_natureza (categoria_id, natureza, atualizado_em, atualizado_por)
        values (p_categoria_id, p_natureza, now(), (select auth.uid()))
        on conflict (categoria_id) do update set natureza = excluded.natureza, atualizado_em = excluded.atualizado_em,
                                                  atualizado_por = excluded.atualizado_por;
    end if;
    v_res := jsonb_build_object('categoria_id', p_categoria_id, 'natureza', p_natureza, 'natureza_anterior', v_antes,
                                'tinha_linha', v_tinha);
    insert into financeiro.operacao_catalogo (chave, user_id, operacao, resultado)
    values (p_chave, (select auth.uid()), 'definir_natureza_categoria', v_res);
    return v_res;
end
$$;

-- =====================================================================================================================
-- 2. Reclassificacao por manifesto (so a coluna da categoria)
-- =====================================================================================================================
-- Manifesto: {"itens": [{"id": 463, "de": null, "para": 89}], "compras": [{"id": 616, "de": 107, "para": 102}]}.
-- "de" e a categoria que o registro TEM de ter agora (null = sem categoria); diferente disso, a execucao recusa.
-- Previa (nada e alterado), so para quem administra o catalogo: cada registro, as contas que herdam a categoria do item
-- (quantidade, soma, pagas), os bloqueios e o hash do que sera decidido.
create function financeiro.previa_reclassificacao_categorias(p_manifesto jsonb)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_e      jsonb;
    v_id     integer;
    v_de     integer;
    v_para   integer;
    v_item   public.item_despesa;
    v_compra public.lancamento_agregado;
    v_n      bigint;
    v_soma   numeric;
    v_pagas  bigint;
    v_itens  jsonb := '[]'::jsonb;
    v_comp   jsonb := '[]'::jsonb;
    v_bloq   jsonb := '[]'::jsonb;
    v_vistos integer[] := '{}';
    v_pessoal integer := (select p.id from public.perfil_financeiro p where p.nome = 'Pessoal' order by p.id limit 1);
begin
    if (select auth.uid()) is null
       or not exists (select 1 from financeiro.gestor_catalogo g where g.user_id = (select auth.uid())) then
        raise exception 'Esta conta nao administra o catalogo de categorias' using errcode = '42501';
    end if;
    if p_manifesto is null or jsonb_typeof(p_manifesto) <> 'object'
       or jsonb_typeof(coalesce(p_manifesto -> 'itens', '[]'::jsonb)) <> 'array'
       or jsonb_typeof(coalesce(p_manifesto -> 'compras', '[]'::jsonb)) <> 'array' then
        raise exception 'Manifesto invalido' using errcode = '22023';
    end if;
    if jsonb_array_length(coalesce(p_manifesto -> 'itens', '[]'::jsonb))
       + jsonb_array_length(coalesce(p_manifesto -> 'compras', '[]'::jsonb)) not between 1 and 500 then
        raise exception 'Manifesto vazio ou com mais de 500 registros' using errcode = '22023';
    end if;

    for v_e in select e from jsonb_array_elements(coalesce(p_manifesto -> 'itens', '[]'::jsonb)) e order by (e ->> 'id')::integer loop
        begin
            v_id := (v_e ->> 'id')::integer;
            v_de := nullif(v_e ->> 'de', '')::integer;
            v_para := (v_e ->> 'para')::integer;
        exception when others then
            raise exception 'Manifesto invalido: item %', v_e using errcode = '22023';
        end;
        if v_id is null or v_para is null then
            raise exception 'Manifesto invalido: item %', v_e using errcode = '22023';
        end if;
        if v_id = any (v_vistos) then
            raise exception 'Manifesto invalido: item % repetido', v_id using errcode = '22023';
        end if;
        v_vistos := v_vistos || v_id;
        select * into v_item from public.item_despesa i where i.id = v_id;
        if not found then
            v_bloq := v_bloq || jsonb_build_object('codigo', 'NAO_ENCONTRADO', 'tabela', 'item_despesa', 'id', v_id,
                                                   'motivo', 'item de despesa ' || v_id || ' nao encontrado');
            continue;
        end if;
        if v_item.tipo = 'Agregador' then
            v_bloq := v_bloq || jsonb_build_object('codigo', 'CARTAO', 'tabela', 'item_despesa', 'id', v_id,
                                                   'motivo', 'o item ' || v_id || ' e um cartao: nao tem categoria de despesa');
        end if;
        if v_item.categoria_id is distinct from v_de then
            v_bloq := v_bloq || jsonb_build_object('codigo', 'CATEGORIA_MUDOU', 'tabela', 'item_despesa', 'id', v_id,
                                                   'motivo', 'o item ' || v_id || ' nao esta mais na categoria esperada');
        end if;
        if v_para is not distinct from v_de then
            v_bloq := v_bloq || jsonb_build_object('codigo', 'SEM_MUDANCA', 'tabela', 'item_despesa', 'id', v_id,
                                                   'motivo', 'o item ' || v_id || ' ja esta na categoria de destino');
        end if;
        if not exists (select 1 from public.categoria c where c.id = v_para and coalesce(c.ativo, true)) then
            v_bloq := v_bloq || jsonb_build_object('codigo', 'DESTINO_INVALIDO', 'tabela', 'item_despesa', 'id', v_id,
                                                   'motivo', 'categoria de destino ' || v_para || ' inexistente ou inativa');
        end if;
        select count(*), coalesce(sum(c.valor), 0), count(*) filter (where c.status_pagamento = 'Pago')
          into v_n, v_soma, v_pagas
          from public.conta c where c.item_despesa_id = v_id;
        v_itens := v_itens || jsonb_build_object(
            'id', v_id, 'nome', v_item.nome, 'tipo', v_item.tipo, 'perfil_id', coalesce(v_item.perfil_financeiro_id, v_pessoal),
            'de', v_de, 'para', v_para, 'atual', v_item.categoria_id, 'valor', v_item.valor,
            'contas', v_n, 'contas_valor', v_soma, 'contas_pagas', v_pagas);
    end loop;

    v_vistos := '{}';
    for v_e in select e from jsonb_array_elements(coalesce(p_manifesto -> 'compras', '[]'::jsonb)) e order by (e ->> 'id')::integer loop
        begin
            v_id := (v_e ->> 'id')::integer;
            v_de := nullif(v_e ->> 'de', '')::integer;
            v_para := (v_e ->> 'para')::integer;
        exception when others then
            raise exception 'Manifesto invalido: compra %', v_e using errcode = '22023';
        end;
        if v_id is null or v_para is null then
            raise exception 'Manifesto invalido: compra %', v_e using errcode = '22023';
        end if;
        if v_id = any (v_vistos) then
            raise exception 'Manifesto invalido: compra % repetida', v_id using errcode = '22023';
        end if;
        v_vistos := v_vistos || v_id;
        select * into v_compra from public.lancamento_agregado l where l.id = v_id;
        if not found then
            v_bloq := v_bloq || jsonb_build_object('codigo', 'NAO_ENCONTRADO', 'tabela', 'lancamento_agregado', 'id', v_id,
                                                   'motivo', 'compra ' || v_id || ' nao encontrada');
            continue;
        end if;
        if v_compra.categoria_id is distinct from v_de then
            v_bloq := v_bloq || jsonb_build_object('codigo', 'CATEGORIA_MUDOU', 'tabela', 'lancamento_agregado', 'id', v_id,
                                                   'motivo', 'a compra ' || v_id || ' nao esta mais na categoria esperada');
        end if;
        if v_para is not distinct from v_de then
            v_bloq := v_bloq || jsonb_build_object('codigo', 'SEM_MUDANCA', 'tabela', 'lancamento_agregado', 'id', v_id,
                                                   'motivo', 'a compra ' || v_id || ' ja esta na categoria de destino');
        end if;
        if not exists (select 1 from public.categoria c where c.id = v_para and coalesce(c.ativo, true)) then
            v_bloq := v_bloq || jsonb_build_object('codigo', 'DESTINO_INVALIDO', 'tabela', 'lancamento_agregado', 'id', v_id,
                                                   'motivo', 'categoria de destino ' || v_para || ' inexistente ou inativa');
        end if;
        v_comp := v_comp || jsonb_build_object(
            'id', v_id, 'descricao', v_compra.descricao, 'perfil_id', coalesce(v_compra.perfil_financeiro_id, v_pessoal),
            'de', v_de, 'para', v_para, 'atual', v_compra.categoria_id, 'valor', v_compra.valor,
            'mes_fatura', v_compra.mes_fatura, 'cartao_id', v_compra.cartao_id);
    end loop;

    return jsonb_build_object(
        'itens', v_itens, 'compras', v_comp, 'bloqueios', v_bloq,
        'totais', jsonb_build_object(
            'itens', jsonb_array_length(v_itens), 'compras', jsonb_array_length(v_comp),
            'contas_por_heranca', (select coalesce(sum((i ->> 'contas')::bigint), 0) from jsonb_array_elements(v_itens) i),
            'valor_das_contas', (select coalesce(sum((i ->> 'contas_valor')::numeric), 0) from jsonb_array_elements(v_itens) i),
            'valor_das_compras', (select coalesce(sum((c ->> 'valor')::numeric), 0) from jsonb_array_elements(v_comp) c)),
        -- o hash cobre a decisao: cada registro, a categoria que tem, a de destino e o que ele carrega (valor e contas)
        'hash', md5((select coalesce(string_agg(concat_ws('|', 'I', i ->> 'id', coalesce(i ->> 'atual', '-'), i ->> 'para', i ->> 'valor',
                                                          i ->> 'contas', i ->> 'contas_valor', i ->> 'contas_pagas'), ';'
                                                order by (i ->> 'id')::integer), '') from jsonb_array_elements(v_itens) i)
                    || '#'
                    || (select coalesce(string_agg(concat_ws('|', 'C', c ->> 'id', coalesce(c ->> 'atual', '-'), c ->> 'para', c ->> 'valor',
                                                             c ->> 'mes_fatura'), ';' order by (c ->> 'id')::integer), '')
                          from jsonb_array_elements(v_comp) c)));
end
$$;

-- Execucao, so por quem administra o catalogo e com a escrita de cada perfil dos registros: refaz a previa sob as travas,
-- confere o hash e recusa com bloqueio. Numa transacao, troca SO categoria_id dos itens e das compras do manifesto.
-- Auditoria em operacao_catalogo (categoria anterior de cada registro). Idempotente pela chave. Qualquer falha desfaz tudo.
create function financeiro.reclassificar_categorias(p_manifesto jsonb, p_hash text, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_anterior financeiro.operacao_catalogo;
    v_previa   jsonb;
    v_perfil   integer;
    v_r        jsonb;
    v_n        bigint;
    v_fotos    jsonb := '[]'::jsonb;
    v_res      jsonb;
begin
    perform financeiro.exigir_escrita_catalogo();
    if p_chave is null then
        raise exception 'Chave da operacao obrigatoria' using errcode = '22023';
    end if;
    select * into v_anterior from financeiro.operacao_catalogo o where o.chave = p_chave;
    if found then
        if v_anterior.user_id is distinct from (select auth.uid()) or v_anterior.operacao <> 'reclassificar_categorias' then
            raise exception 'Chave da operacao ja usada' using errcode = '22023';
        end if;
        return (v_anterior.resultado - 'fotos') || jsonb_build_object('repetida', true);
    end if;
    v_previa := financeiro.previa_reclassificacao_categorias(p_manifesto);
    -- travas: cada perfil com registros (a mesma trava das compras, da importacao e das despesas), depois as linhas
    for v_perfil in select distinct (x ->> 'perfil_id')::integer
                      from jsonb_array_elements((v_previa -> 'itens') || (v_previa -> 'compras')) x order by 1 loop
        perform financeiro.exigir_escrita_novo(v_perfil);
    end loop;
    perform 1 from public.item_despesa i
      where i.id in (select (x ->> 'id')::integer from jsonb_array_elements(v_previa -> 'itens') x) order by i.id for update;
    perform 1 from public.lancamento_agregado l
      where l.id in (select (x ->> 'id')::integer from jsonb_array_elements(v_previa -> 'compras') x) order by l.id for update;
    v_previa := financeiro.previa_reclassificacao_categorias(p_manifesto);
    if p_hash is distinct from v_previa ->> 'hash' then
        raise exception 'A previa da reclassificacao mudou desde a conferencia: confira de novo' using errcode = '40001';
    end if;
    if jsonb_array_length(v_previa -> 'bloqueios') > 0 then
        raise exception 'Reclassificacao recusada: %. Nada foi alterado.',
            (select string_agg(b ->> 'motivo', '; ') from jsonb_array_elements(v_previa -> 'bloqueios') b)
            using errcode = 'P0001', hint = v_previa -> 'bloqueios' -> 0 ->> 'codigo';
    end if;

    for v_r in select x from jsonb_array_elements(v_previa -> 'itens') x loop
        update public.item_despesa i set categoria_id = (v_r ->> 'para')::integer
         where i.id = (v_r ->> 'id')::integer and i.categoria_id is not distinct from nullif(v_r ->> 'de', '')::integer;
        get diagnostics v_n = row_count;
        if v_n <> 1 then
            raise exception 'Reclassificacao recusada: o item % mudou durante a operacao. Nada foi alterado.', v_r ->> 'id'
                using errcode = '40001';
        end if;
        v_fotos := v_fotos || jsonb_build_object('tabela', 'item_despesa', 'id', (v_r ->> 'id')::integer, 'de', v_r -> 'de',
                                                 'para', v_r -> 'para', 'contas', v_r -> 'contas');
    end loop;
    for v_r in select x from jsonb_array_elements(v_previa -> 'compras') x loop
        update public.lancamento_agregado l set categoria_id = (v_r ->> 'para')::integer
         where l.id = (v_r ->> 'id')::integer and l.categoria_id is not distinct from nullif(v_r ->> 'de', '')::integer;
        get diagnostics v_n = row_count;
        if v_n <> 1 then
            raise exception 'Reclassificacao recusada: a compra % mudou durante a operacao. Nada foi alterado.', v_r ->> 'id'
                using errcode = '40001';
        end if;
        v_fotos := v_fotos || jsonb_build_object('tabela', 'lancamento_agregado', 'id', (v_r ->> 'id')::integer, 'de', v_r -> 'de',
                                                 'para', v_r -> 'para');
    end loop;

    v_res := jsonb_build_object('hash', p_hash, 'totais', v_previa -> 'totais', 'fotos', v_fotos);
    insert into financeiro.operacao_catalogo (chave, user_id, operacao, resultado)
    values (p_chave, (select auth.uid()), 'reclassificar_categorias', v_res);
    return v_res - 'fotos';
end
$$;

-- Inversa: devolve a categoria anterior de cada registro de uma reclassificacao feita. So desfaz o que continua como a
-- reclassificacao deixou (registro mudado depois = recusa, sem alterar nada). Idempotente pela chave; auditada.
create function financeiro.reverter_reclassificacao_categorias(p_chave_origem uuid, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_anterior financeiro.operacao_catalogo;
    v_origem   financeiro.operacao_catalogo;
    v_f        jsonb;
    v_perfil   integer;
    v_n        bigint;
    v_total    integer := 0;
    v_pessoal  integer := (select p.id from public.perfil_financeiro p where p.nome = 'Pessoal' order by p.id limit 1);
    v_res      jsonb;
begin
    perform financeiro.exigir_escrita_catalogo();
    if p_chave is null or p_chave_origem is null then
        raise exception 'Chave da operacao obrigatoria' using errcode = '22023';
    end if;
    select * into v_anterior from financeiro.operacao_catalogo o where o.chave = p_chave;
    if found then
        if v_anterior.user_id is distinct from (select auth.uid()) or v_anterior.operacao <> 'reverter_reclassificacao_categorias' then
            raise exception 'Chave da operacao ja usada' using errcode = '22023';
        end if;
        return v_anterior.resultado || jsonb_build_object('repetida', true);
    end if;
    select * into v_origem from financeiro.operacao_catalogo o
     where o.chave = p_chave_origem and o.operacao = 'reclassificar_categorias';
    if not found then
        raise exception 'Reclassificacao nao encontrada' using errcode = 'P0001', hint = 'NAO_ENCONTRADA';
    end if;
    if exists (select 1 from financeiro.operacao_catalogo o
                where o.operacao = 'reverter_reclassificacao_categorias' and o.resultado ->> 'origem' = p_chave_origem::text) then
        raise exception 'Esta reclassificacao ja foi revertida. Nada foi alterado.' using errcode = 'P0001', hint = 'JA_REVERTIDA';
    end if;
    for v_perfil in
        select distinct coalesce(i.perfil_financeiro_id, v_pessoal) from public.item_despesa i
         where i.id in (select (f ->> 'id')::integer from jsonb_array_elements(v_origem.resultado -> 'fotos') f where f ->> 'tabela' = 'item_despesa')
        union
        select distinct coalesce(l.perfil_financeiro_id, v_pessoal) from public.lancamento_agregado l
         where l.id in (select (f ->> 'id')::integer from jsonb_array_elements(v_origem.resultado -> 'fotos') f where f ->> 'tabela' = 'lancamento_agregado')
        order by 1 loop
        perform financeiro.exigir_escrita_novo(v_perfil);
    end loop;
    for v_f in select f from jsonb_array_elements(v_origem.resultado -> 'fotos') f order by f ->> 'tabela', (f ->> 'id')::integer loop
        if v_f ->> 'tabela' = 'item_despesa' then
            update public.item_despesa i set categoria_id = nullif(v_f ->> 'de', '')::integer
             where i.id = (v_f ->> 'id')::integer and i.categoria_id is not distinct from (v_f ->> 'para')::integer;
        else
            update public.lancamento_agregado l set categoria_id = nullif(v_f ->> 'de', '')::integer
             where l.id = (v_f ->> 'id')::integer and l.categoria_id is not distinct from (v_f ->> 'para')::integer;
        end if;
        get diagnostics v_n = row_count;
        if v_n <> 1 then
            raise exception 'Reversao recusada: % % foi alterado depois da reclassificacao. Nada foi alterado.',
                v_f ->> 'tabela', v_f ->> 'id' using errcode = 'P0001', hint = 'MUDOU_DEPOIS';
        end if;
        v_total := v_total + 1;
    end loop;
    v_res := jsonb_build_object('origem', p_chave_origem, 'registros_restaurados', v_total);
    insert into financeiro.operacao_catalogo (chave, user_id, operacao, resultado)
    values (p_chave, (select auth.uid()), 'reverter_reclassificacao_categorias', v_res);
    return v_res;
end
$$;

-- =====================================================================================================================
-- 3. Importacao: historico em categoria de natureza NAO_DEFINIDO nao vale como sugestao
-- =====================================================================================================================
-- sugestao_categoria_importacao: texto de 20261105090000 + o trecho marcado.
create or replace function financeiro.sugestao_categoria_importacao(p_perfil_id integer, p_classificacao text, p_normalizada text,
                                                                    p_fallback integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_desc   text := btrim(coalesce(p_classificacao, ''));
    v_tokens text[] := regexp_split_to_array(btrim(coalesce(p_classificacao, '')), '\s+');
    v_cands  jsonb;
    v_n      integer;
    v_hist   integer;
begin
    if v_desc <> '' then
        select coalesce(jsonb_agg(jsonb_build_object('categoria_id', m.categoria_id, 'categoria_nome', m.nome,
                                                     'palavras_encontradas', m.palavras, 'score', m.score)
                                  order by m.score desc, m.categoria_id), '[]'::jsonb), count(*)
          into v_cands, v_n
          from (select pk.categoria_id, c.nome, to_jsonb(array_agg(lower(btrim(pk.palavra)) order by pk.id)) as palavras,
                       count(*) as score
                  from public.categoria_palavra_chave pk
                  join public.categoria c on c.id = pk.categoria_id and coalesce(c.ativo, true)
                 where pk.ativo and btrim(pk.palavra) <> ''
                   and case when position(' ' in btrim(pk.palavra)) > 0 then position(lower(btrim(pk.palavra)) in v_desc) > 0
                            else lower(btrim(pk.palavra)) = any(v_tokens) end
                 group by pk.categoria_id, c.nome) m;
        if v_n = 1 or (v_n > 1 and (v_cands -> 0 ->> 'score')::integer > (v_cands -> 1 ->> 'score')::integer) then
            return jsonb_build_object(
                'categoria_id', (v_cands -> 0 ->> 'categoria_id')::integer, 'origem', 'palavra_chave',
                'confianca', case when v_n = 1 or (v_cands -> 0 ->> 'score')::integer >= 2 then 'alta' else 'media' end,
                'ambigua', false, 'palavras_chave_encontradas', v_cands -> 0 -> 'palavras_encontradas',
                'categorias_candidatas', v_cands,
                'aviso', 'Categoria sugerida por palavra-chave. Palavras encontradas: '
                         || (select string_agg(p, ', ') from jsonb_array_elements_text(v_cands -> 0 -> 'palavras_encontradas') p) || '.');
        elsif v_n > 1 then
            return jsonb_build_object(
                'categoria_id', null, 'origem', 'ambigua', 'confianca', 'baixa', 'ambigua', true,
                'palavras_chave_encontradas', (select coalesce(jsonb_agg(distinct p), '[]'::jsonb)
                                                 from jsonb_array_elements(v_cands) c, jsonb_array_elements_text(c -> 'palavras_encontradas') p),
                'categorias_candidatas', v_cands,
                'aviso', 'Mais de uma categoria possivel. Revise antes de importar. Candidatas: '
                         || (select string_agg(c ->> 'categoria_nome', ', ') from (select c from jsonb_array_elements(v_cands) c limit 3) x) || '.');
        end if;
    end if;
    if btrim(coalesce(p_normalizada, '')) <> '' then
        select l.categoria_id into v_hist from public.lancamento_agregado l
         where lower(coalesce(l.descricao_original_normalizada, l.descricao)) = lower(btrim(p_normalizada))
           and l.categoria_id is not null and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id)
           -- FIN-CATEGORIAS-REORGANIZACAO-01: a categoria residual (natureza NAO_DEFINIDO, ex.: Outros) nao se propaga pelo
           -- historico; vale a classificacao especifica mais recente da mesma descricao, se houver
           and financeiro.natureza_da_categoria(l.categoria_id) <> 'NAO_DEFINIDO'
         order by l.id desc limit 1;
        if v_hist is not null then
            return jsonb_build_object('categoria_id', v_hist, 'origem', 'historico', 'confianca', 'alta', 'ambigua', false,
                                      'palavras_chave_encontradas', '[]'::jsonb, 'categorias_candidatas', '[]'::jsonb,
                                      'aviso', null);
        end if;
    end if;
    return jsonb_build_object('categoria_id', p_fallback, 'origem', case when p_fallback is null then 'sem_sugestao' else 'fallback' end,
                              'confianca', case when p_fallback is null then 'baixa' else 'media' end, 'ambigua', false,
                              'palavras_chave_encontradas', '[]'::jsonb, 'categorias_candidatas', '[]'::jsonb, 'aviso', null);
end
$$;

-- =====================================================================================================================
-- 4. Leituras gerenciais (nada e gravado)
-- =====================================================================================================================
-- Indicadores do mes por natureza gerencial. "obrigacoes" e "previsoes" sao exatamente o conjunto que o Dashboard soma em
-- despesas previstas (contas que nao sao fatura, fora as substituidas e as dispensadas, + previsoes financeiras; texto de
-- 20261226090000), so repartido por natureza: o total nao muda e
-- nenhuma saida some do fluxo. "cartao" reparte as compras das faturas do mes (informativo: as faturas ja sao obrigacoes
-- do Dashboard a parte e nao se somam de novo).
create function financeiro.indicadores_gerenciais(p_perfil_id integer, p_mes text)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_valor  text := btrim(coalesce(p_mes, ''));
    v_inicio date;
    v_obr    jsonb;
    v_prev   jsonb;
    v_cart   jsonb;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if length(v_valor) = 7 then
        v_valor := v_valor || '-01';
    end if;
    if v_valor !~ '^\d{4}-\d{2}-\d{2}$' then
        raise exception 'Mes invalido' using errcode = '22023';
    end if;
    v_inicio := date_trunc('month', v_valor::date)::date;

    select coalesce(jsonb_object_agg(t.natureza, jsonb_build_object('quantidade', t.qtd, 'previsto', t.previsto, 'pago', t.pago)), '{}'::jsonb)
      into v_obr
      from (select financeiro.natureza_da_categoria(i.categoria_id) natureza, count(*) qtd, round(sum(c.valor), 2) previsto,
                   round(coalesce(sum(c.valor) filter (where c.status_pagamento = 'Pago'), 0), 2) pago
              from public.conta c
              left join public.item_despesa i on i.id = c.item_despesa_id
             where financeiro.pertence_ao_perfil(c.perfil_financeiro_id, p_perfil_id)
               and date_trunc('month', c.mes_referencia) = v_inicio and c.is_fatura_cartao is not true
               and c.status_pagamento is distinct from 'Substituida' and c.status_pagamento is distinct from 'Dispensada'
             group by 1) t;
    select coalesce(jsonb_object_agg(t.natureza, jsonb_build_object('quantidade', t.qtd, 'previsto', t.previsto, 'pago', 0)), '{}'::jsonb)
      into v_prev
      from (select financeiro.natureza_da_categoria(d.categoria_id) natureza, count(*) qtd, round(sum(d.valor_previsto), 2) previsto
              from public.despesa_prevista d
             where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id)
               and date_trunc('month', d.data_atual_prevista) = v_inicio and d.status in ('PREVISTA', 'ADIADA')
               and financeiro.prevista_financeira(d.origem_tipo, d.origem_id)
             group by 1) t;
    select coalesce(jsonb_object_agg(t.natureza, jsonb_build_object('quantidade', t.qtd, 'valor', t.valor)), '{}'::jsonb)
      into v_cart
      from (select financeiro.natureza_da_categoria(l.categoria_id) natureza, count(*) qtd, round(sum(l.valor), 2) valor
              from public.lancamento_agregado l
             where financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id)
               and date_trunc('month', l.mes_fatura) = v_inicio
             group by 1) t;

    return jsonb_build_object(
        'mes', to_char(v_inicio, 'YYYY-MM'),
        'obrigacoes', v_obr, 'previsoes', v_prev, 'cartao', v_cart,
        'fluxo_total', (select coalesce(sum((e.value ->> 'previsto')::numeric), 0) from jsonb_each(v_obr) e)
                       + (select coalesce(sum((e.value ->> 'previsto')::numeric), 0) from jsonb_each(v_prev) e),
        'aportes', coalesce((v_obr -> 'APORTE' ->> 'previsto')::numeric, 0) + coalesce((v_prev -> 'APORTE' ->> 'previsto')::numeric, 0),
        'ajustes_tecnicos', coalesce((v_obr -> 'AJUSTE_TECNICO' ->> 'previsto')::numeric, 0)
                            + coalesce((v_prev -> 'AJUSTE_TECNICO' ->> 'previsto')::numeric, 0),
        'transferencias_internas', coalesce((v_obr -> 'TRANSFERENCIA_INTERNA' ->> 'previsto')::numeric, 0)
                                   + coalesce((v_prev -> 'TRANSFERENCIA_INTERNA' ->> 'previsto')::numeric, 0),
        -- consumo = o fluxo menos o que foi expressamente classificado como aporte, ajuste tecnico ou transferencia interna
        -- (o que ainda nao tem natureza definida continua contado, a vista, em "nao_definido")
        'consumo', coalesce((v_obr -> 'CONSUMO' ->> 'previsto')::numeric, 0) + coalesce((v_prev -> 'CONSUMO' ->> 'previsto')::numeric, 0),
        'nao_definido', coalesce((v_obr -> 'NAO_DEFINIDO' ->> 'previsto')::numeric, 0)
                        + coalesce((v_prev -> 'NAO_DEFINIDO' ->> 'previsto')::numeric, 0));
end
$$;

-- Posicao dos consorcios cujas parcelas estao em categoria de natureza APORTE: aportes (previsto, pago, a pagar) e
-- resgate (previsto, recebido). O resgate nao e ganho: retorno de capital = ate o total dos aportes; ganho = o que passar.
-- Nada de saldo de investimento nem de patrimonio: so o aportado, o recebido e a diferenca.
create function financeiro.poupanca_programada_tela(p_perfil_id integer)
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
    return (
        select coalesce(jsonb_agg(jsonb_build_object(
                   'contrato_id', k.id, 'nome', k.nome, 'ativo', coalesce(k.ativo, true), 'parcelas', k.parcelas,
                   'aporte_previsto', k.previsto, 'aporte_pago', k.pago, 'aporte_a_pagar', k.previsto - k.pago,
                   'mes_contemplacao', k.mes_contemplacao, 'resgate_previsto', k.premio, 'resgate_recebido', k.recebido,
                   'retorno_de_capital_previsto', least(k.premio, k.previsto),
                   'ganho_previsto', greatest(k.premio - k.previsto, 0),
                   'perda_prevista', greatest(k.previsto - k.premio, 0),
                   'retorno_de_capital_recebido', least(k.recebido, k.previsto),
                   'ganho_recebido', greatest(k.recebido - k.previsto, 0),
                   'posicao', k.pago - k.recebido)  -- aportado e ainda nao recebido (negativa = recebeu antes de terminar de aportar)
               order by k.nome, k.id), '[]'::jsonb)
          from (select cc.id, cc.nome, cc.ativo, cc.mes_contemplacao, coalesce(cc.valor_premio, 0) premio,
                       count(c.id) parcelas, coalesce(sum(c.valor), 0) previsto,
                       coalesce(sum(c.valor) filter (where c.status_pagamento = 'Pago'), 0) pago,
                       coalesce((select sum(r.valor_recebido) from public.receita_realizada r
                                  where r.observacoes ~ ('consorcio_id=' || cc.id || '([^0-9]|$)')  -- o marcador da receita de contemplacao
                                    and exists (select 1 from public.movimento_financeiro m where m.receita_realizada_id = r.id)), 0) recebido
                  from public.contrato_consorcio cc
                  join public.item_despesa i on i.tipo = 'Consorcio'
                       and financeiro.pertence_ao_perfil(i.perfil_financeiro_id, p_perfil_id)
                       and financeiro.posicao_parcela_consorcio(i.nome, array[cc.nome]) is not null
                       and financeiro.natureza_da_categoria(i.categoria_id) = 'APORTE'
                  join public.conta c on c.item_despesa_id = i.id
                 where financeiro.pertence_ao_perfil(cc.perfil_financeiro_id, p_perfil_id)
                 group by cc.id, cc.nome, cc.ativo, cc.mes_contemplacao, cc.valor_premio) k);
end
$$;

revoke execute on function financeiro.natureza_da_categoria(integer) from public, anon, authenticated;
revoke execute on function financeiro.naturezas_das_categorias() from public, anon;
revoke execute on function financeiro.definir_natureza_categoria(integer, text, uuid) from public, anon;
revoke execute on function financeiro.previa_reclassificacao_categorias(jsonb) from public, anon;
revoke execute on function financeiro.reclassificar_categorias(jsonb, text, uuid) from public, anon;
revoke execute on function financeiro.reverter_reclassificacao_categorias(uuid, uuid) from public, anon;
revoke execute on function financeiro.indicadores_gerenciais(integer, text) from public, anon;
revoke execute on function financeiro.poupanca_programada_tela(integer) from public, anon;
grant execute on function financeiro.naturezas_das_categorias() to authenticated;
grant execute on function financeiro.definir_natureza_categoria(integer, text, uuid) to authenticated;
grant execute on function financeiro.previa_reclassificacao_categorias(jsonb) to authenticated;
grant execute on function financeiro.reclassificar_categorias(jsonb, text, uuid) to authenticated;
grant execute on function financeiro.reverter_reclassificacao_categorias(uuid, uuid) to authenticated;
grant execute on function financeiro.indicadores_gerenciais(integer, text) to authenticated;
grant execute on function financeiro.poupanca_programada_tela(integer) to authenticated;
