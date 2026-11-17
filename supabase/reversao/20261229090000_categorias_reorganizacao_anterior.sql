-- FIN-CATEGORIAS-REORGANIZACAO-01 — reversao da migration 20261229090000.
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica. Recusada enquanto houver reclassificacao nao revertida ou
-- natureza gerencial gravada: desfaca antes os dados pelo roteiro (scripts/reorganizar_categorias.py reverter), para nada
-- ficar classificado sem a funcao que o explica. Devolve sugestao_categoria_importacao ao texto de 20261105090000.

do $$
begin
    if exists (select 1 from financeiro.categoria_natureza) then
        raise exception 'Reversao recusada: ha naturezas gerenciais gravadas. Reverta os dados antes.';
    end if;
    if exists (select 1 from financeiro.operacao_catalogo o
                where o.operacao = 'reclassificar_categorias'
                  and not exists (select 1 from financeiro.operacao_catalogo r
                                   where r.operacao = 'reverter_reclassificacao_categorias' and r.resultado ->> 'origem' = o.chave::text)) then
        raise exception 'Reversao recusada: ha reclassificacao de categorias nao revertida. Reverta os dados antes.';
    end if;
end
$$;

drop function financeiro.poupanca_programada_tela(integer);
drop function financeiro.indicadores_gerenciais(integer, text);
drop function financeiro.reverter_reclassificacao_categorias(uuid, uuid);
drop function financeiro.reclassificar_categorias(jsonb, text, uuid);
drop function financeiro.previa_reclassificacao_categorias(jsonb);
drop function financeiro.definir_natureza_categoria(integer, text, uuid);
drop function financeiro.naturezas_das_categorias();

-- sugestao_categoria_importacao: texto de 20261105090000 (sem o filtro da natureza).
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

drop function financeiro.natureza_da_categoria(integer);
drop table financeiro.categoria_natureza;
