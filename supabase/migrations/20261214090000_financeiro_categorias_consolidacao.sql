-- FIN-CATEGORIAS-CONSOLIDACAO-01 — incorporacao de Categorias de Despesa redundantes e Mobilidade sem MOB_REVISAO.
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261214090000). Aplicar depois de 20261213090000.
-- Validada em cluster local descartavel (tests/test_supabase_categorias_consolidacao.py) e ensaiada numa copia fiel da
-- producao. Doc: docs/FIN_CATEGORIAS_CONSOLIDACAO_01.md. Gerada por scripts/gerar_migration_categorias_consolidacao.py.
-- Reversao: supabase/reversao/20261214090000_categorias_consolidacao_anterior.sql (recusada depois de uma incorporacao).
--
-- 1. Mobilidade: os eventos REVISAO, REVISAO_GERAL e REVISAO_PROGRAMADA usam MOB_MANUTENCAO (Manutencao Veicular); a
--    lista das categorias sistemicas obrigatorias (troca do escritor do catalogo, nomes reservados) passa a ter 9.
-- 2. financeiro.previa_incorporacao_categoria e financeiro.incorporar_categoria: previa por tabela com hash e execucao
--    transacional (trava do catalogo, auditoria em operacao_catalogo, idempotente). Nenhum dado e alterado pela migration:
--    as incorporacoes sao feitas depois, uma a uma, com autorizacao (scripts/consolidar_categorias.py).
--
-- Funcoes existentes substituidas pelo texto vigente com os trechos marcados "FIN-CATEGORIAS-CONSOLIDACAO-01": categorias_sistemicas_mobilidade
-- (texto de 20261125090000) e mob_categoria_evento (texto de 20261127090000).

-- =====================================================================================================================
-- 1. Mobilidade: texto vigente + os trechos marcados
-- =====================================================================================================================

-- categorias_sistemicas_mobilidade: texto de 20261125090000 + os trechos marcados.
create or replace function financeiro.categorias_sistemicas_mobilidade()
    returns table (codigo text, nome text)
    language sql
    immutable
    set search_path = ''
as $$
    -- FIN-CATEGORIAS-CONSOLIDACAO-01: sem MOB_REVISAO (as revisoes do veiculo sao Manutencao Veicular, MOB_MANUTENCAO)
    values ('MOB_COMBUSTIVEL', 'Combustível'), ('MOB_SEGURO_VEICULAR', 'Seguro Veicular'),
           ('MOB_TRIBUTOS_VEICULARES', 'Tributos Veiculares'),
           ('MOB_MANUTENCAO', 'Manutenção Veicular'), ('MOB_PNEUS', 'Pneus'), ('MOB_USO_VEICULO', 'Uso do Veículo'),
           ('MOB_APP', 'Transporte por Aplicativo'), ('MOB_ASSINATURA', 'Assinatura Veicular'),
           ('MOB_LAVAGEM', 'Lavagem Veicular')
$$;

-- mob_categoria_evento: texto de 20261127090000 + os trechos marcados.
create or replace function financeiro.mob_categoria_evento(p_tipo text)
    returns integer
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select financeiro.mob_categoria(case upper(btrim(coalesce(p_tipo, '')))
        when 'COMBUSTIVEL' then 'MOB_COMBUSTIVEL' when 'ABASTECIMENTO' then 'MOB_COMBUSTIVEL'
        when 'SEGURO' then 'MOB_SEGURO_VEICULAR' when 'SEGURO_VEICULAR' then 'MOB_SEGURO_VEICULAR'
        when 'IPVA' then 'MOB_TRIBUTOS_VEICULARES' when 'LICENCIAMENTO' then 'MOB_TRIBUTOS_VEICULARES'
        when 'TRIBUTO' then 'MOB_TRIBUTOS_VEICULARES' when 'TRIBUTOS' then 'MOB_TRIBUTOS_VEICULARES'
        when 'TAXA_OBRIGATORIA' then 'MOB_TRIBUTOS_VEICULARES'
        -- FIN-CATEGORIAS-CONSOLIDACAO-01: revisao e manutencao (o tipo do evento continua no metadata da prevista)
        when 'REVISAO' then 'MOB_MANUTENCAO' when 'REVISAO_GERAL' then 'MOB_MANUTENCAO'
        when 'REVISAO_PROGRAMADA' then 'MOB_MANUTENCAO'
        when 'TROCA_PNEUS' then 'MOB_PNEUS' when 'PNEUS' then 'MOB_PNEUS' when 'ALINHAMENTO_BALANCEAMENTO' then 'MOB_PNEUS'
        when 'ESTACIONAMENTO' then 'MOB_USO_VEICULO' when 'PEDAGIO' then 'MOB_USO_VEICULO' when 'USO_VEICULO' then 'MOB_USO_VEICULO'
        when 'TRANSPORTE_APP' then 'MOB_APP' when 'APP' then 'MOB_APP' when 'TAXI' then 'MOB_APP' when 'UBER' then 'MOB_APP'
        when 'ASSINATURA' then 'MOB_ASSINATURA' when 'ASSINATURA_VEICULAR' then 'MOB_ASSINATURA'
        when 'LAVAGEM' then 'MOB_LAVAGEM' when 'LAVA_JATO' then 'MOB_LAVAGEM' when 'HIGIENIZACAO' then 'MOB_LAVAGEM'
        else 'MOB_MANUTENCAO' end)
$$;

-- =====================================================================================================================
-- 2. Incorporacao de uma Categoria de Despesa em outra (previa conferida pelo hash e execucao transacional)
-- =====================================================================================================================
-- Referencias da categoria em cada tabela que a aponta (chaves estrangeiras para public.categoria, descobertas no
-- catalogo do banco): registros, soma de "valor" (quando a tabela tem) e perfis (registro sem perfil = Pessoal). Interna.
create function financeiro.referencias_categoria(p_categoria_id integer)
    returns table (tabela text, coluna text, registros bigint, valor numeric, perfis integer[])
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_fk      record;
    v_pessoal integer := (select p.id from public.perfil_financeiro p where p.nome = 'Pessoal' order by p.id limit 1);
begin
    for v_fk in
        select n.nspname as esquema, t.relname as tab, a.attname as col,
               exists (select 1 from pg_attribute x where x.attrelid = t.oid and x.attname = 'valor' and not x.attisdropped
                          and x.atttypid = 'numeric'::regtype) as tem_valor,
               exists (select 1 from pg_attribute x where x.attrelid = t.oid and x.attname = 'perfil_financeiro_id'
                          and not x.attisdropped) as tem_perfil
          from pg_constraint k
          join pg_class t on t.oid = k.conrelid
          join pg_namespace n on n.oid = t.relnamespace
          join pg_attribute a on a.attrelid = k.conrelid and a.attnum = k.conkey[1]
         where k.contype = 'f' and k.confrelid = 'public.categoria'::regclass and cardinality(k.conkey) = 1
         order by 2, 3
    loop
        tabela := v_fk.tab;
        coluna := v_fk.col;
        execute format('select count(*), %s, %s from %I.%I where %I = $1',
                       case when v_fk.tem_valor then 'sum(valor)' else 'null::numeric' end,
                       case when v_fk.tem_perfil
                            then 'array_agg(distinct coalesce(perfil_financeiro_id, $2) order by coalesce(perfil_financeiro_id, $2))'
                            else 'null::integer[]' end,
                       v_fk.esquema, v_fk.tab, v_fk.col)
           into registros, valor, perfis using p_categoria_id, v_pessoal;
        return next;
    end loop;
end
$$;

-- Previa (nada e alterado), so para quem administra o catalogo. p_opcoes: {"renomear_destino": "Nome", "palavras":
-- {"pneu": 6}}: cada palavra-chave da origem vai para o destino, salvo as indicadas em "palavras" (para outra categoria).
-- Mostra, por tabela, o que sera reapontado; o destino de cada palavra-chave (ja existente no destino = unida, sem
-- duplicar); os vinculos com a Categoria do Cartao (movidos ao destino e estendidos as categorias que recebem palavras-
-- chave, para a classificacao automatica continuar no mesmo agrupamento da fatura); os lancamentos por fatura (paga ou
-- nao) e as recorrencias. Bloqueios (a execucao recusa): categoria sistemica ainda obrigatoria, destino inativo ou de outro
-- perfil, nome do destino em uso, vinculo conflitante (a categoria ficaria com duas Categorias do Cartao), perfil com
-- registros sem acesso ou ainda no Flask, palavra-chave ou destino invalido e compra de uma limpeza seletiva de cartao
-- ainda nao reimportada (proibido consolidar entre a limpeza e a reimportacao). O hash cobre a decisao, nao o que a
-- previa so informa (outras categorias com a mesma palavra-chave, vinculos atuais do destino).
create function financeiro.previa_incorporacao_categoria(p_origem integer, p_destino integer, p_opcoes jsonb)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_o      public.categoria;
    v_d      public.categoria;
    v_op     jsonb := coalesce(p_opcoes, '{}'::jsonb);
    v_mapa   jsonb;
    v_nome   text;
    v_bloq   jsonb := '[]'::jsonb;
    v_refs   jsonb;
    v_pal    jsonb;
    v_vinc   jsonb;
    v_vinc_p jsonb;
    v_ir     jsonb;
    v_lanc   jsonb;
    v_rec    jsonb;
    v_pend   jsonb;
    v_perfil integer;
    v_chave  text;
    v_valor  jsonb;
    v_alvo   public.categoria;
    v_decisao jsonb;
begin
    if (select auth.uid()) is null
       or not exists (select 1 from financeiro.gestor_catalogo g where g.user_id = (select auth.uid())) then
        raise exception 'Esta conta nao administra o catalogo de categorias' using errcode = '42501';
    end if;
    if jsonb_typeof(v_op) <> 'object' then
        raise exception 'Opcoes da incorporacao invalidas' using errcode = '22023';
    end if;
    v_mapa := coalesce(v_op -> 'palavras', '{}'::jsonb);
    if jsonb_typeof(v_mapa) <> 'object' then
        raise exception 'Destino das palavras-chave invalido: use {"palavra": categoria_id}' using errcode = '22023';
    end if;
    if v_op ? 'renomear_destino' and jsonb_typeof(v_op -> 'renomear_destino') not in ('string', 'null') then
        raise exception 'Novo nome do destino invalido' using errcode = '22023';
    end if;
    v_nome := nullif(btrim(v_op ->> 'renomear_destino'), '');
    if p_origem is null or p_destino is null or p_origem = p_destino then
        raise exception 'Informe categorias de origem e de destino diferentes' using errcode = '22023';
    end if;
    select * into v_o from public.categoria c where c.id = p_origem;
    if not found then
        raise exception 'Categoria de origem nao encontrada' using errcode = 'P0001', hint = 'NAO_ENCONTRADA';
    end if;
    select * into v_d from public.categoria c where c.id = p_destino;
    if not found then
        raise exception 'Categoria de destino nao encontrada' using errcode = 'P0001', hint = 'NAO_ENCONTRADA';
    end if;

    -- as categorias
    if v_o.codigo_sistema is not null
       and exists (select 1 from financeiro.categorias_sistemicas_mobilidade() s where s.codigo = v_o.codigo_sistema) then
        v_bloq := v_bloq || jsonb_build_object('codigo', 'SISTEMICA_OBRIGATORIA', 'motivo',
            format('A categoria %s e sistemica e obrigatoria (%s): nao pode ser incorporada', v_o.nome, v_o.codigo_sistema));
    end if;
    if not coalesce(v_d.ativo, true) then
        v_bloq := v_bloq || jsonb_build_object('codigo', 'DESTINO_INATIVO', 'motivo',
            format('A categoria de destino %s esta inativa', v_d.nome));
    end if;
    if v_d.perfil_financeiro_id is not null and v_o.perfil_financeiro_id is distinct from v_d.perfil_financeiro_id then
        v_bloq := v_bloq || jsonb_build_object('codigo', 'OUTRO_PERFIL', 'motivo',
            'A categoria de destino e de um perfil e a de origem nao: os registros de outros perfis passariam a ela');
    end if;
    if v_nome is not null then
        if coalesce(v_d.sistemica, false) or coalesce(v_d.bloquear_edicao, false) then
            v_bloq := v_bloq || jsonb_build_object('codigo', 'DESTINO_SISTEMICO', 'motivo',
                format('A categoria de destino %s e sistemica: o nome nao muda', v_d.nome));
        elsif length(v_nome) > 120 then
            v_bloq := v_bloq || jsonb_build_object('codigo', 'NOME_INVALIDO', 'motivo', 'Nome do destino com mais de 120 caracteres');
        elsif exists (select 1 from public.categoria c where lower(c.nome) = lower(v_nome) and c.id not in (p_origem, p_destino)) then
            v_bloq := v_bloq || jsonb_build_object('codigo', 'NOME_EM_USO', 'motivo',
                format('Ja existe outra categoria com o nome %s', v_nome));
        elsif exists (select 1 from financeiro.categorias_sistemicas_mobilidade() s where lower(s.nome) = lower(v_nome)) then
            v_bloq := v_bloq || jsonb_build_object('codigo', 'NOME_SISTEMICO', 'motivo',
                format('O nome %s e reservado a uma categoria sistemica de Mobilidade', v_nome));
        end if;
    end if;

    -- destino de cada palavra-chave indicada em "palavras"
    for v_chave, v_valor in select e.key, e.value from jsonb_each(v_mapa) e order by e.key loop
        if not exists (select 1 from public.categoria_palavra_chave k where k.categoria_id = p_origem and k.palavra = v_chave) then
            v_bloq := v_bloq || jsonb_build_object('codigo', 'PALAVRA_INVALIDA', 'motivo',
                format('A palavra-chave "%s" nao e da categoria de origem', v_chave));
            continue;
        end if;
        if jsonb_typeof(v_valor) <> 'number' or (v_valor #>> '{}')::numeric <> trunc((v_valor #>> '{}')::numeric) then
            v_bloq := v_bloq || jsonb_build_object('codigo', 'PALAVRA_INVALIDA', 'motivo',
                format('Destino da palavra-chave "%s" invalido', v_chave));
            continue;
        end if;
        select * into v_alvo from public.categoria c where c.id = (v_valor #>> '{}')::integer;
        if not found or v_alvo.id = p_origem or not coalesce(v_alvo.ativo, true)
           or (v_alvo.perfil_financeiro_id is not null and v_alvo.perfil_financeiro_id is distinct from v_o.perfil_financeiro_id) then
            v_bloq := v_bloq || jsonb_build_object('codigo', 'PALAVRA_INVALIDA', 'motivo',
                format('Destino da palavra-chave "%s" inexistente, inativo, de outro perfil ou a propria origem', v_chave));
        end if;
    end loop;

    -- referencias por tabela
    select coalesce(jsonb_agg(jsonb_build_object('tabela', r.tabela, 'coluna', r.coluna, 'registros', r.registros,
                                                 'valor', r.valor, 'perfis', to_jsonb(r.perfis),
                                                 'tratamento', case r.tabela when 'categoria_palavra_chave' then 'PALAVRAS'
                                                                             when 'categoria_cartao_despesa' then 'VINCULOS'
                                                                             when 'ir_categoria_despesa' then 'UNIR'
                                                                             else 'REAPONTAR' end)
                              order by r.tabela, r.coluna), '[]'::jsonb)
      into v_refs from financeiro.referencias_categoria(p_origem) r where r.registros > 0;
    for v_perfil in select distinct p from financeiro.referencias_categoria(p_origem) r, unnest(r.perfis) p order by p loop
        if not financeiro.pode_gerir_perfil(v_perfil) then
            v_bloq := v_bloq || jsonb_build_object('codigo', 'PERFIL_SEM_ACESSO', 'motivo',
                format('O perfil %s tem registros nesta categoria e esta conta nao o administra', v_perfil));
        elsif (select g.gerador from financeiro.gerador_recorrencia g where g.perfil_financeiro_id = v_perfil) is distinct from 'NOVO' then
            v_bloq := v_bloq || jsonb_build_object('codigo', 'PERFIL_NO_FLASK', 'motivo',
                format('O perfil %s tem registros nesta categoria e ainda e administrado pelo sistema atual (Flask)', v_perfil));
        end if;
    end loop;

    -- palavras-chave da origem
    select coalesce(jsonb_agg(jsonb_build_object(
               'palavra', k.palavra, 'ativo', k.ativo, 'destino_id', x.dest, 'destino', c.nome,
               'situacao', case when exists (select 1 from public.categoria_palavra_chave k2
                                              where k2.categoria_id = x.dest and k2.palavra = k.palavra)
                                then 'JA_NO_DESTINO' else 'MOVER' end,
               'tambem_em', (select coalesce(jsonb_agg(c3.nome order by c3.id), '[]'::jsonb)
                               from public.categoria_palavra_chave k3 join public.categoria c3 on c3.id = k3.categoria_id
                              where k3.palavra = k.palavra and k3.categoria_id not in (p_origem, x.dest)))
               order by k.palavra), '[]'::jsonb)
      into v_pal
      from public.categoria_palavra_chave k
     cross join lateral (select case when jsonb_typeof(v_mapa -> k.palavra) = 'number'
                                     then (v_mapa ->> k.palavra)::numeric::integer else p_destino end as dest) x
      left join public.categoria c on c.id = x.dest
     where k.categoria_id = p_origem;

    -- vinculos da origem com a Categoria do Cartao: vao para o destino
    select coalesce(jsonb_agg(jsonb_build_object(
               'id', v.id, 'perfil_financeiro_id', v.perfil_financeiro_id, 'categoria_cartao_id', v.categoria_cartao_id,
               'categoria_cartao', cc.nome, 'ativo', v.ativo,
               'situacao', case
                   when exists (select 1 from public.categoria_cartao_despesa w
                                 where w.categoria_id = p_destino and w.categoria_cartao_id = v.categoria_cartao_id)
                       then 'JA_NO_DESTINO'
                   when v.ativo and exists (
                       select 1 from public.categoria_cartao_despesa w join public.categoria_cartao c2 on c2.id = w.categoria_cartao_id
                        where w.categoria_id = p_destino and w.ativo and c2.ativo and w.categoria_cartao_id <> v.categoria_cartao_id
                          and (w.perfil_financeiro_id is null or v.perfil_financeiro_id is null
                               or w.perfil_financeiro_id = v.perfil_financeiro_id))
                       then 'CONFLITO'
                   else 'MOVER' end) order by v.id), '[]'::jsonb)
      into v_vinc
      from public.categoria_cartao_despesa v join public.categoria_cartao cc on cc.id = v.categoria_cartao_id
     where v.categoria_id = p_origem;

    -- e sao estendidos as categorias que recebem palavras-chave (o termo continua no mesmo agrupamento da fatura)
    select coalesce(jsonb_agg(jsonb_build_object(
               'categoria_id', a.alvo, 'categoria', c.nome, 'perfil_financeiro_id', v.perfil_financeiro_id,
               'categoria_cartao_id', v.categoria_cartao_id, 'categoria_cartao', cc.nome,
               'situacao', case
                   when exists (select 1 from public.categoria_cartao_despesa w
                                 where w.categoria_id = a.alvo and w.categoria_cartao_id = v.categoria_cartao_id and w.ativo)
                       then 'JA_EXISTE'
                   when exists (
                       select 1 from public.categoria_cartao_despesa w join public.categoria_cartao c2 on c2.id = w.categoria_cartao_id
                        where w.categoria_id = a.alvo and w.ativo and c2.ativo and w.categoria_cartao_id <> v.categoria_cartao_id
                          and (w.perfil_financeiro_id is null or v.perfil_financeiro_id is null
                               or w.perfil_financeiro_id = v.perfil_financeiro_id))
                       then 'CONFLITO'
                   when exists (select 1 from public.categoria_cartao_despesa w
                                 where w.categoria_id = a.alvo and w.categoria_cartao_id = v.categoria_cartao_id)
                       then 'REATIVAR'
                   else 'CRIAR' end) order by a.alvo, v.id), '[]'::jsonb)
      into v_vinc_p
      from (select distinct (e.value #>> '{}')::numeric::integer as alvo from jsonb_each(v_mapa) e
             where jsonb_typeof(e.value) = 'number' and (e.value #>> '{}')::numeric::integer <> p_destino
               and exists (select 1 from public.categoria x where x.id = (e.value #>> '{}')::numeric::integer)
               and exists (select 1 from public.categoria_palavra_chave k where k.categoria_id = p_origem and k.palavra = e.key)) a
      join public.categoria c on c.id = a.alvo
     cross join public.categoria_cartao_despesa v
      join public.categoria_cartao cc on cc.id = v.categoria_cartao_id
     where v.categoria_id = p_origem and v.ativo and cc.ativo;

    if exists (select 1 from jsonb_array_elements(v_vinc || v_vinc_p) x where x ->> 'situacao' = 'CONFLITO') then
        v_bloq := v_bloq || jsonb_build_object('codigo', 'VINCULO_CONFLITANTE', 'motivo',
            'Uma categoria ficaria com duas Categorias do Cartao ativas no mesmo perfil');
    end if;

    -- mapeamento do Imposto de Renda (unico por perfil e categoria do IR)
    select coalesce(jsonb_agg(jsonb_build_object('id', x.id, 'perfil_financeiro_id', x.perfil_financeiro_id,
               'categoria_ir_id', x.categoria_ir_id,
               'situacao', case when exists (select 1 from public.ir_categoria_despesa y
                                              where y.perfil_financeiro_id is not distinct from x.perfil_financeiro_id
                                                and y.categoria_ir_id = x.categoria_ir_id and y.categoria_id = p_destino)
                                then 'JA_NO_DESTINO' else 'MOVER' end) order by x.id), '[]'::jsonb)
      into v_ir from public.ir_categoria_despesa x where x.categoria_id = p_origem;

    -- lancamentos por fatura (paga ou nao) e recorrencias: o valor, as datas e a situacao nao mudam
    select coalesce(jsonb_agg(jsonb_build_object('perfil_financeiro_id', z.perfil, 'cartao_id', z.cartao_id, 'mes_fatura', z.mes,
               'registros', z.n, 'valor', z.total, 'recorrentes', z.rec, 'importados', z.imp, 'fatura_paga', z.paga)
               order by z.perfil, z.cartao_id, z.mes), '[]'::jsonb)
      into v_lanc
      from (select l.perfil_financeiro_id as perfil, l.cartao_id, l.mes_fatura as mes, count(*) as n, sum(l.valor) as total,
                   count(*) filter (where coalesce(l.is_recorrente, false)) as rec,
                   count(*) filter (where coalesce(l.is_importado, false)) as imp,
                   coalesce(financeiro.fatura_esta_paga(financeiro.fatura_do_mes(l.cartao_id, l.mes_fatura)), false) as paga
              from public.lancamento_agregado l where l.categoria_id = p_origem
             group by 1, 2, 3) z;
    select coalesce(jsonb_agg(jsonb_build_object('id', i.id, 'nome', i.nome, 'perfil_financeiro_id', i.perfil_financeiro_id,
               'tipo', i.tipo, 'recorrente', i.recorrente, 'ativo', i.ativo, 'valor', i.valor, 'cartao_id', i.cartao_id)
               order by i.id), '[]'::jsonb)
      into v_rec from public.item_despesa i where i.categoria_id = p_origem;

    -- compras de uma limpeza seletiva de cartao ainda nao reimportadas com a categoria de origem na foto
    select coalesce(jsonb_agg(distinct jsonb_build_object('operacao', o.chave, 'perfil_financeiro_id', o.perfil_financeiro_id,
               'cartao_id', (f ->> 'cartao_id')::integer,
               'competencia', to_char(coalesce((f ->> 'mes_fatura_original')::date, (f ->> 'mes_fatura')::date), 'YYYY-MM'))),
               '[]'::jsonb)
      into v_pend
      from financeiro.operacao_cartao o
     cross join lateral jsonb_array_elements(case when jsonb_typeof(o.resultado -> 'fotos' -> 'compras') = 'array'
                                                  then o.resultado -> 'fotos' -> 'compras' else '[]'::jsonb end) f
     where o.operacao = 'limpar_importacoes' and (f ->> 'categoria_id')::integer = p_origem
       and not exists (
           select 1 from financeiro.operacao_cartao i
            where i.operacao = 'importar_fatura' and i.perfil_financeiro_id = o.perfil_financeiro_id
              and i.criado_em > o.criado_em and (i.resultado ->> 'cartao_id')::integer = (f ->> 'cartao_id')::integer
              and i.resultado ->> 'competencia'
                  = to_char(coalesce((f ->> 'mes_fatura_original')::date, (f ->> 'mes_fatura')::date), 'YYYY-MM'));
    if jsonb_array_length(v_pend) > 0 then
        v_bloq := v_bloq || jsonb_build_object('codigo', 'RECONSTRUCAO_PENDENTE', 'motivo',
            'Ha fatura de cartao limpa e ainda nao reimportada com compras desta categoria: reimporte antes de consolidar');
    end if;

    v_decisao := jsonb_build_object(
        'origem', jsonb_build_object('id', v_o.id, 'nome', v_o.nome, 'codigo_sistema', v_o.codigo_sistema,
                                     'sistemica', coalesce(v_o.sistemica, false), 'perfil_financeiro_id', v_o.perfil_financeiro_id),
        'destino', jsonb_build_object('id', v_d.id, 'codigo_sistema', v_d.codigo_sistema, 'perfil_financeiro_id', v_d.perfil_financeiro_id),
        'renomear_destino', v_nome,
        'referencias', v_refs,
        'palavras', (select coalesce(jsonb_agg(p - 'tambem_em' - 'destino'), '[]'::jsonb) from jsonb_array_elements(v_pal) p),
        'vinculos', v_vinc, 'vinculos_palavras', v_vinc_p, 'ir', v_ir, 'lancamentos', v_lanc, 'recorrencias', v_rec,
        'reconstrucao_pendente', v_pend, 'bloqueios', v_bloq);
    return v_decisao || jsonb_build_object(
        'destino', (v_decisao -> 'destino') || jsonb_build_object('nome', v_d.nome, 'sistemica', coalesce(v_d.sistemica, false)),
        'palavras', v_pal,
        'vinculos_destino', (select coalesce(jsonb_agg(jsonb_build_object('perfil_financeiro_id', w.perfil_financeiro_id,
                                    'categoria_cartao_id', w.categoria_cartao_id, 'categoria_cartao', cc.nome, 'ativo', w.ativo)
                                    order by w.id), '[]'::jsonb)
                               from public.categoria_cartao_despesa w join public.categoria_cartao cc on cc.id = w.categoria_cartao_id
                              where w.categoria_id = p_destino),
        'executavel', jsonb_array_length(v_bloq) = 0,
        'hash', md5(v_decisao::text));
end
$$;

-- Execucao, so por quem administra o catalogo (escritor NOVO, trava oficial do catalogo) e com a escrita de cada perfil
-- com registros (trava das compras e da importacao do perfil): refaz a previa sob as travas, confere o hash e recusa com
-- bloqueio. Numa transacao: palavras-chave (movidas ou unidas sem duplicar), vinculos com a Categoria do Cartao (movidos,
-- unidos e estendidos as categorias que recebem palavras-chave), mapeamento do IR (unido) e as demais referencias
-- reapontadas (so a coluna da categoria: valores, datas, situacao, pagamentos, recorrencias e previsoes ficam como estao).
-- Sem referencia restante, exclui a origem (nunca em cascata) e, se pedido, renomeia o destino. Auditoria em
-- operacao_catalogo (com a linha da origem e os ids reapontados). Idempotente pela chave; repetida com outra chave depois
-- de feita, devolve o resultado anterior. Qualquer falha desfaz tudo.
create function financeiro.incorporar_categoria(p_origem integer, p_destino integer, p_opcoes jsonb, p_hash text, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_anterior financeiro.operacao_catalogo;
    v_previa   jsonb;
    v_o        public.categoria;
    v_mapa     jsonb := coalesce(p_opcoes -> 'palavras', '{}'::jsonb);
    v_nome     text := nullif(btrim(p_opcoes ->> 'renomear_destino'), '');
    v_perfil   integer;
    v_k        public.categoria_palavra_chave;
    v_v        public.categoria_cartao_despesa;
    v_i        record;
    v_alvo     integer;
    v_fk       record;
    v_n        bigint;
    v_ids      jsonb;
    v_resto    text;
    v_pal      jsonb := '[]'::jsonb;
    v_vinc     jsonb := '[]'::jsonb;
    v_ir       jsonb := '[]'::jsonb;
    v_reap     jsonb := '[]'::jsonb;
    v_fotos    jsonb := '[]'::jsonb;
    v_res      jsonb;
begin
    perform financeiro.exigir_escrita_catalogo();
    if p_chave is null then
        raise exception 'Chave da operacao obrigatoria' using errcode = '22023';
    end if;
    select * into v_anterior from financeiro.operacao_catalogo o where o.chave = p_chave;
    if found then
        if v_anterior.user_id is distinct from (select auth.uid()) or v_anterior.operacao <> 'incorporar_categoria' then
            raise exception 'Chave da operacao ja usada' using errcode = '22023';
        end if;
        return (v_anterior.resultado - 'fotos') || jsonb_build_object('repetida', true);
    end if;
    if not exists (select 1 from public.categoria c where c.id = p_origem) then
        select * into v_anterior from financeiro.operacao_catalogo o
         where o.operacao = 'incorporar_categoria' and (o.resultado ->> 'origem_id')::integer = p_origem
         order by o.criado_em desc limit 1;
        if found then
            if (v_anterior.resultado ->> 'destino_id')::integer is distinct from p_destino then
                raise exception 'A categoria % ja foi incorporada em outra (%). Nada foi alterado.', p_origem,
                    v_anterior.resultado ->> 'destino_id' using errcode = 'P0001', hint = 'JA_INCORPORADA';
            end if;
            return (v_anterior.resultado - 'fotos') || jsonb_build_object('repetida', true);
        end if;
    end if;
    -- travas: as duas categorias e cada perfil com registros, em ordem (sem deadlock com as compras e a importacao)
    perform 1 from public.categoria c where c.id in (p_origem, p_destino) order by c.id for update;
    for v_perfil in select distinct p from financeiro.referencias_categoria(p_origem) r, unnest(r.perfis) p order by p loop
        perform financeiro.exigir_escrita_novo(v_perfil);
    end loop;
    v_previa := financeiro.previa_incorporacao_categoria(p_origem, p_destino, p_opcoes);
    if p_hash is distinct from v_previa ->> 'hash' then
        raise exception 'A previa da incorporacao mudou desde a conferencia: confira de novo' using errcode = '40001';
    end if;
    if jsonb_array_length(v_previa -> 'bloqueios') > 0 then
        raise exception 'Incorporacao recusada: %. Nada foi alterado.',
            (select string_agg(b ->> 'motivo', '; ') from jsonb_array_elements(v_previa -> 'bloqueios') b)
            using errcode = 'P0001', hint = v_previa -> 'bloqueios' -> 0 ->> 'codigo';
    end if;
    select * into v_o from public.categoria c where c.id = p_origem;

    -- 1. vinculos com a Categoria do Cartao estendidos as categorias que recebem palavras-chave
    for v_v in select v.* from public.categoria_cartao_despesa v join public.categoria_cartao cc on cc.id = v.categoria_cartao_id
                where v.categoria_id = p_origem and v.ativo and cc.ativo order by v.id loop
        for v_alvo in select distinct (e.value #>> '{}')::numeric::integer from jsonb_each(v_mapa) e
                       where (e.value #>> '{}')::numeric::integer <> p_destino order by 1 loop
            if exists (select 1 from public.categoria_cartao_despesa w
                        where w.categoria_id = v_alvo and w.categoria_cartao_id = v_v.categoria_cartao_id and w.ativo) then
                continue;
            elsif exists (select 1 from public.categoria_cartao_despesa w
                           where w.categoria_id = v_alvo and w.categoria_cartao_id = v_v.categoria_cartao_id) then
                update public.categoria_cartao_despesa w set ativo = true, updated_at = now() at time zone 'utc'
                 where w.categoria_id = v_alvo and w.categoria_cartao_id = v_v.categoria_cartao_id;
                v_vinc := v_vinc || jsonb_build_object('categoria_id', v_alvo, 'categoria_cartao_id', v_v.categoria_cartao_id,
                                                       'acao', 'REATIVADO');
            else
                insert into public.categoria_cartao_despesa (perfil_financeiro_id, categoria_cartao_id, categoria_id, ativo,
                                                             created_at, updated_at)
                values (v_v.perfil_financeiro_id, v_v.categoria_cartao_id, v_alvo, true, now() at time zone 'utc',
                        now() at time zone 'utc');
                v_vinc := v_vinc || jsonb_build_object('categoria_id', v_alvo, 'categoria_cartao_id', v_v.categoria_cartao_id,
                                                       'acao', 'CRIADO');
            end if;
        end loop;
    end loop;
    -- 2. palavras-chave: para o destino (ou a categoria indicada); a que ja existe la e unida, sem duplicar
    for v_k in select k.* from public.categoria_palavra_chave k where k.categoria_id = p_origem order by k.id loop
        v_alvo := case when jsonb_typeof(v_mapa -> v_k.palavra) = 'number' then (v_mapa ->> v_k.palavra)::numeric::integer
                       else p_destino end;
        if exists (select 1 from public.categoria_palavra_chave k2 where k2.categoria_id = v_alvo and k2.palavra = v_k.palavra) then
            update public.categoria_palavra_chave k2 set ativo = k2.ativo or v_k.ativo
             where k2.categoria_id = v_alvo and k2.palavra = v_k.palavra;
            delete from public.categoria_palavra_chave k where k.id = v_k.id;
            v_pal := v_pal || jsonb_build_object('palavra', v_k.palavra, 'categoria_id', v_alvo, 'acao', 'UNIDA');
        else
            update public.categoria_palavra_chave k set categoria_id = v_alvo where k.id = v_k.id;
            v_pal := v_pal || jsonb_build_object('palavra', v_k.palavra, 'categoria_id', v_alvo, 'acao', 'MOVIDA');
        end if;
    end loop;
    -- 3. vinculos da origem com a Categoria do Cartao: para o destino (o mesmo vinculo la e unido)
    for v_v in select v.* from public.categoria_cartao_despesa v where v.categoria_id = p_origem order by v.id loop
        if exists (select 1 from public.categoria_cartao_despesa w
                    where w.categoria_id = p_destino and w.categoria_cartao_id = v_v.categoria_cartao_id) then
            update public.categoria_cartao_despesa w set ativo = true, updated_at = now() at time zone 'utc'
             where w.categoria_id = p_destino and w.categoria_cartao_id = v_v.categoria_cartao_id and v_v.ativo and not w.ativo;
            delete from public.categoria_cartao_despesa v where v.id = v_v.id;
            v_vinc := v_vinc || jsonb_build_object('id', v_v.id, 'categoria_cartao_id', v_v.categoria_cartao_id, 'acao', 'UNIDO');
        else
            update public.categoria_cartao_despesa v set categoria_id = p_destino where v.id = v_v.id;
            v_vinc := v_vinc || jsonb_build_object('id', v_v.id, 'categoria_cartao_id', v_v.categoria_cartao_id, 'acao', 'MOVIDO');
        end if;
    end loop;
    -- 4. mapeamento do IR: o mesmo par (perfil, categoria do IR) no destino e unido
    for v_i in select x.id, x.perfil_financeiro_id, x.categoria_ir_id from public.ir_categoria_despesa x
                where x.categoria_id = p_origem order by x.id loop
        if exists (select 1 from public.ir_categoria_despesa y
                    where y.perfil_financeiro_id is not distinct from v_i.perfil_financeiro_id
                      and y.categoria_ir_id = v_i.categoria_ir_id and y.categoria_id = p_destino) then
            delete from public.ir_categoria_despesa x where x.id = v_i.id;
            v_ir := v_ir || jsonb_build_object('id', v_i.id, 'acao', 'UNIDO');
        else
            update public.ir_categoria_despesa x set categoria_id = p_destino where x.id = v_i.id;
            v_ir := v_ir || jsonb_build_object('id', v_i.id, 'acao', 'MOVIDO');
        end if;
    end loop;
    -- 5. as demais referencias: so a coluna da categoria muda
    for v_fk in
        select n.nspname as esquema, t.relname as tab, a.attname as col
          from pg_constraint k
          join pg_class t on t.oid = k.conrelid
          join pg_namespace n on n.oid = t.relnamespace
          join pg_attribute a on a.attrelid = k.conrelid and a.attnum = k.conkey[1]
         where k.contype = 'f' and k.confrelid = 'public.categoria'::regclass and cardinality(k.conkey) = 1
           and k.conrelid not in ('public.categoria_palavra_chave'::regclass, 'public.categoria_cartao_despesa'::regclass,
                                  'public.ir_categoria_despesa'::regclass)
         order by 2, 3
    loop
        execute format('with u as (update %I.%I set %I = $1 where %I = $2 returning id) '
                       'select count(*), coalesce(jsonb_agg(id order by id), ''[]''::jsonb) from u',
                       v_fk.esquema, v_fk.tab, v_fk.col, v_fk.col)
           into v_n, v_ids using p_destino, p_origem;
        if v_n > 0 then
            v_reap := v_reap || jsonb_build_object('tabela', v_fk.tab, 'coluna', v_fk.col, 'registros', v_n);
            v_fotos := v_fotos || jsonb_build_object('tabela', v_fk.tab, 'coluna', v_fk.col, 'ids', v_ids);
        end if;
    end loop;
    v_resto := financeiro.vinculos_da_categoria(p_origem);
    if v_resto is not null or exists (select 1 from public.categoria_palavra_chave k where k.categoria_id = p_origem) then
        raise exception 'Restaram referencias a categoria de origem (%). Nada foi alterado.', coalesce(v_resto, 'palavras-chave')
            using errcode = 'P0001';
    end if;
    delete from public.categoria c where c.id = p_origem;
    if v_nome is not null then
        perform financeiro.validar_nome_categoria(v_nome, p_destino);
        update public.categoria c set nome = v_nome where c.id = p_destino;
    end if;
    v_res := jsonb_build_object('origem_id', p_origem, 'origem', v_o.nome, 'destino_id', p_destino,
                                'destino', (select c.nome from public.categoria c where c.id = p_destino),
                                'renomeado', v_nome is not null, 'reapontados', v_reap, 'palavras', v_pal,
                                'vinculos', v_vinc, 'ir', v_ir, 'hash', p_hash);
    insert into financeiro.operacao_catalogo (chave, user_id, operacao, resultado)
    values (p_chave, (select auth.uid()), 'incorporar_categoria',
            v_res || jsonb_build_object('fotos', jsonb_build_object('origem', to_jsonb(v_o), 'reapontados', v_fotos,
                                                                    'previa', v_previa)));
    return v_res;
end
$$;

revoke execute on function financeiro.referencias_categoria(integer) from public, anon, authenticated;
revoke execute on function financeiro.previa_incorporacao_categoria(integer, integer, jsonb) from public, anon;
revoke execute on function financeiro.incorporar_categoria(integer, integer, jsonb, text, uuid) from public, anon;
grant execute on function financeiro.previa_incorporacao_categoria(integer, integer, jsonb) to authenticated;
grant execute on function financeiro.incorporar_categoria(integer, integer, jsonb, text, uuid) to authenticated;
