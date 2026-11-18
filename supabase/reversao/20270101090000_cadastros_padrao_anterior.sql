-- FIN-CADASTROS-PADRAO-01 — reversao da migration 20270101090000.
--
-- GERADA por scripts/gerar_migration_cadastros_padrao.py: nao editar a mao.
-- NAO aplicar no Supabase remoto sem autorizacao especifica. Antes: volte o frontend ao deploy anterior e desfaca os dados
-- pelo roteiro (scripts/cadastros_padrao.py reverter). Recusada enquanto existir personalizacao de usuario que a regra
-- anterior nao sabe representar (categoria particular, palavra-chave do usuario, modelo de categorias de cartao em uso).

do $$
begin
    if exists (select 1 from public.categoria where user_id is not null) then
        raise exception 'Reversao recusada: ha categorias particulares de usuarios. A regra anterior as mostraria a todos.';
    end if;
    if exists (select 1 from financeiro.palavra_chave_usuario) then
        raise exception 'Reversao recusada: ha palavras-chave personalizadas por usuarios. Reverta os dados antes.';
    end if;
    if exists (select 1 from public.categoria_cartao where padrao_id is not null) or exists (select 1 from financeiro.categoria_cartao_padrao) then
        raise exception 'Reversao recusada: o modelo de categorias de cartao esta em uso. Reverta os dados antes.';
    end if;
    if exists (select 1 from public.categoria group by lower(nome) having count(*) > 1) then
        raise exception 'Reversao recusada: ha categorias com o mesmo nome. A regra anterior exige nome unico.';
    end if;
end
$$;

CREATE OR REPLACE FUNCTION financeiro.categorias_de_despesa()
 RETURNS TABLE(id integer, nome text, cor text)
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
    select c.id, c.nome::text, c.cor::text
      from public.categoria c
     where coalesce(c.ativo, true)
       and exists (select 1 from financeiro.perfil_acesso a where a.user_id = (select auth.uid()))
     order by c.nome
$function$;

CREATE OR REPLACE FUNCTION financeiro.categorias_tela(p_perfil_id integer, p_ativo boolean)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    return coalesce((
        select jsonb_agg(financeiro.categoria_flask(c)
                         || jsonb_build_object('palavras_chave_count',
                                               (select count(*) from public.categoria_palavra_chave p
                                                 where p.categoria_id = c.id and p.ativo))
                         order by c.id)
          from public.categoria c
         where p_ativo is null or c.ativo is not distinct from p_ativo), '[]'::jsonb);
end
$function$;

CREATE OR REPLACE FUNCTION financeiro.mobilidade_categorias_tela(p_perfil_id integer)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    return coalesce((select jsonb_agg(financeiro.categoria_flask(c) || jsonb_build_object(
                                          'palavras_chave_count', (select count(*) from public.categoria_palavra_chave k
                                                                    where k.categoria_id = c.id and k.ativo))
                                      order by c.id)
                       from public.categoria c), '[]'::jsonb);
end
$function$;

CREATE OR REPLACE FUNCTION financeiro.naturezas_das_categorias()
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
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
$function$;

CREATE OR REPLACE FUNCTION financeiro.validar_nome_categoria(p_nome text, p_id integer)
 RETURNS void
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_codigo text;
begin
    if exists (select 1 from public.categoria c
                where lower(c.nome) = lower(p_nome) and c.id is distinct from p_id) then
        raise exception '%', case when p_id is null then 'Ja existe uma categoria com este nome'
                                  else 'Ja existe outra categoria com este nome' end using errcode = '22023';
    end if;
    select s.codigo into v_codigo from financeiro.categorias_sistemicas_mobilidade() s
     where lower(s.nome) = lower(btrim(p_nome));
    if v_codigo is not null then
        raise exception 'Nome reservado para a categoria sistemica de Mobilidade (%)', v_codigo
            using errcode = '22023', hint = 'NOME_SISTEMICO';
    end if;
end
$function$;

CREATE OR REPLACE FUNCTION financeiro.criar_categoria(p_dados jsonb, p_chave uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_anterior financeiro.operacao_catalogo;
    v_d        jsonb;
    v_cat      public.categoria;
    v_resultado jsonb;
begin
    perform financeiro.exigir_escrita_catalogo();
    if p_chave is null then
        raise exception 'Chave da operacao obrigatoria' using errcode = '22023';
    end if;
    select * into v_anterior from financeiro.operacao_catalogo o where o.chave = p_chave;
    if found then
        if v_anterior.user_id is distinct from (select auth.uid()) or v_anterior.operacao <> 'criar_categoria' then
            raise exception 'Chave da operacao ja usada' using errcode = '22023';
        end if;
        return v_anterior.resultado || jsonb_build_object('repetida', true);
    end if;
    v_d := financeiro.ler_dados_categoria(p_dados, false);
    perform financeiro.validar_nome_categoria(v_d ->> 'nome', null);
    insert into public.categoria (perfil_financeiro_id, nome, descricao, cor, icone, ativo, sistemica, bloquear_edicao,
                                  bloquear_exclusao, criado_em)
    values (null, v_d ->> 'nome', v_d ->> 'descricao', coalesce(v_d ->> 'cor', '#6c757d'), v_d ->> 'icone',
            coalesce((v_d ->> 'ativo')::boolean, true), false, false, false, now() at time zone 'utc')
    returning * into v_cat;
    v_resultado := jsonb_build_object('categoria_id', v_cat.id, 'nome', v_cat.nome);
    insert into financeiro.operacao_catalogo (chave, user_id, operacao, resultado)
    values (p_chave, (select auth.uid()), 'criar_categoria', v_resultado);
    return v_resultado;
end
$function$;

CREATE OR REPLACE FUNCTION financeiro.editar_categoria(p_categoria_id integer, p_dados jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_cat public.categoria;
    v_d   jsonb;
begin
    perform financeiro.exigir_escrita_catalogo();
    select * into v_cat from public.categoria c where c.id = p_categoria_id for update;
    if not found then
        raise exception 'Categoria nao encontrada' using errcode = 'P0001', hint = 'NAO_ENCONTRADA';
    end if;
    v_d := financeiro.ler_dados_categoria(p_dados, true);
    if coalesce(v_cat.sistemica, false) or coalesce(v_cat.bloquear_edicao, false) then
        raise exception 'Esta categoria e sistemica e nao pode ser editada.' using errcode = 'P0001', hint = 'SISTEMICA';
    end if;
    if v_d ? 'nome' then
        perform financeiro.validar_nome_categoria(v_d ->> 'nome', p_categoria_id);
    end if;
    update public.categoria c
       set nome = coalesce(v_d ->> 'nome', c.nome),
           descricao = case when v_d ? 'descricao' then v_d ->> 'descricao' else c.descricao end,
           cor = coalesce(v_d ->> 'cor', c.cor),
           icone = case when v_d ? 'icone' then v_d ->> 'icone' else c.icone end,
           ativo = coalesce((v_d ->> 'ativo')::boolean, c.ativo)
     where c.id = p_categoria_id
    returning * into v_cat;
    return jsonb_build_object('categoria_id', v_cat.id, 'nome', v_cat.nome, 'ativo', v_cat.ativo);
end
$function$;

CREATE OR REPLACE FUNCTION financeiro.excluir_categoria(p_categoria_id integer)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_cat     public.categoria;
    v_vinculo text;
begin
    perform financeiro.exigir_escrita_catalogo();
    select * into v_cat from public.categoria c where c.id = p_categoria_id for update;
    if not found then
        raise exception 'Categoria nao encontrada' using errcode = 'P0001', hint = 'NAO_ENCONTRADA';
    end if;
    if coalesce(v_cat.sistemica, false) or coalesce(v_cat.bloquear_exclusao, false) then
        raise exception 'Esta categoria e sistemica e nao pode ser excluida.' using errcode = 'P0001', hint = 'SISTEMICA';
    end if;
    v_vinculo := financeiro.vinculos_da_categoria(p_categoria_id);
    if v_vinculo is not null then
        raise exception 'Nao e possivel excluir categoria com registros vinculados (%). Inative-a.', v_vinculo
            using errcode = 'P0001', hint = 'COM_VINCULOS';
    end if;
    begin
        delete from public.categoria_palavra_chave p where p.categoria_id = p_categoria_id;
        delete from public.categoria c where c.id = p_categoria_id;
    exception when foreign_key_violation then
        raise exception 'Nao e possivel excluir categoria com registros vinculados. Inative-a.'
            using errcode = 'P0001', hint = 'COM_VINCULOS';
    end;
    return jsonb_build_object('categoria_id', p_categoria_id, 'excluida', true);
end
$function$;

CREATE OR REPLACE FUNCTION financeiro.definir_natureza_categoria(p_categoria_id integer, p_natureza text, p_chave uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
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
$function$;

CREATE OR REPLACE FUNCTION financeiro.criar_palavra_chave(p_categoria_id integer, p_palavra text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_palavra text := regexp_replace(btrim(lower(coalesce(p_palavra, ''))), '\s+', ' ', 'g');
    v_reg     public.categoria_palavra_chave;
begin
    perform financeiro.exigir_escrita_catalogo();
    perform 1 from public.categoria c where c.id = p_categoria_id for update;
    if not found then
        raise exception 'Categoria de Despesa nao encontrada' using errcode = 'P0001', hint = 'NAO_ENCONTRADA';
    end if;
    if v_palavra = '' then
        raise exception 'Palavra-chave e obrigatoria' using errcode = '22023';
    end if;
    if length(v_palavra) > 120 then
        raise exception 'Palavra-chave ate 120 caracteres' using errcode = '22023';
    end if;
    select * into v_reg from public.categoria_palavra_chave p
     where p.categoria_id = p_categoria_id and p.palavra = v_palavra for update;
    if found and v_reg.ativo then
        raise exception 'Palavra-chave ja cadastrada para esta categoria' using errcode = '22023';
    end if;
    if found then
        update public.categoria_palavra_chave set ativo = true, updated_at = now() at time zone 'utc'
         where id = v_reg.id returning * into v_reg;
        return jsonb_build_object('id', v_reg.id, 'categoria_id', p_categoria_id, 'palavra', v_palavra, 'ativo', true,
                                  'created', false);
    end if;
    insert into public.categoria_palavra_chave (categoria_id, palavra, ativo, created_at, updated_at)
    values (p_categoria_id, v_palavra, true, now() at time zone 'utc', now() at time zone 'utc')
    returning * into v_reg;
    return jsonb_build_object('id', v_reg.id, 'categoria_id', p_categoria_id, 'palavra', v_palavra, 'ativo', true,
                              'created', true);
end
$function$;

CREATE OR REPLACE FUNCTION financeiro.palavras_chave_tela(p_perfil_id integer)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    return coalesce((
        select jsonb_object_agg(x.categoria_id::text, x.palavras)
          from (select p.categoria_id,
                       jsonb_agg(jsonb_build_object('id', p.id, 'categoria_id', p.categoria_id, 'palavra', p.palavra,
                                                    'ativo', coalesce(p.ativo, false),
                                                    'created_at', financeiro.iso_python(p.created_at),
                                                    'updated_at', financeiro.iso_python(p.updated_at))
                                 order by p.palavra, p.id) palavras
                  from public.categoria_palavra_chave p
                 where p.ativo
                 group by p.categoria_id) x), '{}'::jsonb);
end
$function$;

CREATE OR REPLACE FUNCTION financeiro.sugestao_categoria_importacao(p_perfil_id integer, p_classificacao text, p_normalizada text, p_fallback integer)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
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
$function$;

CREATE OR REPLACE FUNCTION financeiro.ir_categorias_despesa_tela(p_perfil_id integer, p_disponiveis boolean)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
begin
    perform financeiro.tipo_perfil_ir(p_perfil_id);
    if not p_disponiveis then
        return coalesce((
            select jsonb_agg(jsonb_build_object(
                       'id', v.id, 'perfil_financeiro_id', v.perfil_financeiro_id, 'categoria_ir_id', v.categoria_ir_id,
                       'categoria_ir_nome', (select ic.nome from public.ir_categoria ic where ic.id = v.categoria_ir_id),
                       'categoria_id', v.categoria_id,
                       'categoria_nome', (select c.nome from public.categoria c where c.id = v.categoria_id),
                       'ativo', coalesce(v.ativo, false),
                       'created_at', financeiro.iso_python(v.created_at), 'updated_at', financeiro.iso_python(v.updated_at))
                   order by v.id)
              from public.ir_categoria_despesa v
             where financeiro.pertence_ao_perfil(v.perfil_financeiro_id, p_perfil_id)), '[]'::jsonb);
    end if;
    return coalesce((
        select jsonb_agg(jsonb_build_object(
                   'id', c.id, 'perfil_financeiro_id', c.perfil_financeiro_id, 'nome', c.nome, 'descricao', c.descricao,
                   'cor', c.cor, 'icone', c.icone, 'logo_arquivo', c.logo_arquivo, 'logo_mime', c.logo_mime,
                   'logo_tamanho', c.logo_tamanho, 'logo_original_nome', c.logo_original_nome,
                   'logo_criado_em', financeiro.iso_python(c.logo_criado_em),
                   'logo_url', case when nullif(c.logo_arquivo, '') is not null then '/api/categorias/' || c.id || '/logo' end,
                   'ativo', c.ativo, 'sistemica', coalesce(c.sistemica, false), 'codigo_sistema', c.codigo_sistema,
                   'modulo_origem', c.modulo_origem, 'bloquear_edicao', coalesce(c.bloquear_edicao, false),
                   'bloquear_exclusao', coalesce(c.bloquear_exclusao, false), 'criado_em', financeiro.iso_python(c.criado_em),
                   'categoria_ir_id', v.categoria_ir_id,
                   'categoria_ir_nome', (select ic.nome from public.ir_categoria ic where ic.id = v.categoria_ir_id))
               order by c.nome, c.id)
          from public.categoria c
          left join lateral (select x.categoria_ir_id from public.ir_categoria_despesa x
                              where x.categoria_id = c.id and x.ativo
                                and financeiro.pertence_ao_perfil(x.perfil_financeiro_id, p_perfil_id)
                              order by x.id limit 1) v on true
         where c.ativo and financeiro.pertence_ao_perfil(c.perfil_financeiro_id, p_perfil_id)), '[]'::jsonb);
end
$function$;

CREATE OR REPLACE FUNCTION financeiro.criar_perfil(p_dados jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_usuario uuid := (select auth.uid());
    v jsonb;
    v_ativo boolean;
    v_id integer;
begin
    if v_usuario is null then
        raise exception 'Usuario nao autenticado' using errcode = '42501';
    end if;
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' then
        raise exception 'Dados do perfil invalidos' using errcode = '22023';
    end if;
    v := financeiro.normalizar_dados_perfil(
        jsonb_build_object('nome', p_dados -> 'nome', 'tipo', p_dados -> 'tipo', 'documento', p_dados -> 'documento',
                           'logo_url', p_dados -> 'logo_url', 'avatar', p_dados -> 'avatar', 'cor', p_dados -> 'cor'),
        null);
    v_ativo := coalesce((p_dados ->> 'ativo')::boolean, true);

    -- o nome e unico entre os perfis do proprio usuario (os de outros usuarios nao entram na conta nem na resposta)
    perform pg_advisory_xact_lock(hashtextextended('financeiro.perfil_financeiro.gestao:' || v_usuario::text, 20261231));
    if exists (select 1 from public.perfil_financeiro p
                where p.user_id = v_usuario
                  and financeiro.nome_de_perfil_normalizado(p.nome) = financeiro.nome_de_perfil_normalizado(v ->> 'nome')) then
        raise exception 'Ja existe perfil financeiro com este nome' using errcode = '23505';
    end if;

    insert into public.perfil_financeiro (nome, tipo, documento, avatar, logo_url, cor, ativo, padrao, user_id, created_at, updated_at)
    values (v ->> 'nome', v ->> 'tipo', v ->> 'documento', v ->> 'avatar', v ->> 'logo_url', v ->> 'cor', v_ativo, false, v_usuario,
            (now() at time zone 'utc'), (now() at time zone 'utc'))
    returning id into v_id;
    insert into financeiro.perfil_acesso (user_id, perfil_financeiro_id, papel, pode_gerir)
    values (v_usuario, v_id, 'TITULAR', true);
    perform financeiro.definir_gerador_recorrencia(v_id, 'NOVO', 'criar_perfil (usuario ' || v_usuario::text || ')',
                                                   'Perfil criado pelo novo aplicativo');

    if coalesce((p_dados ->> 'padrao')::boolean, false) and v_ativo then
        perform financeiro.aplicar_perfil_padrao(v_id);
    end if;
    return financeiro.perfil_em_json(v_id);
exception
    when unique_violation then
        raise exception 'Ja existe perfil financeiro com este nome' using errcode = '23505';
end
$function$;

CREATE OR REPLACE FUNCTION financeiro.editar_categoria_cartao(p_perfil_id integer, p_id integer, p_dados jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_d jsonb;
    v_c public.categoria_cartao;
begin
    perform financeiro.exigir_escrita_categoria_cartao(p_perfil_id);
    v_c := financeiro.travar_categoria_cartao(p_perfil_id, p_id);
    v_d := financeiro.ler_dados_categoria_cartao(p_perfil_id, p_dados, true, v_c.id);
    update public.categoria_cartao cc set
        nome = coalesce(v_d ->> 'nome', cc.nome),
        descricao = case when v_d ? 'descricao' then v_d ->> 'descricao' else cc.descricao end,
        cor = coalesce(v_d ->> 'cor', cc.cor),
        icone = case when v_d ? 'icone' then v_d ->> 'icone' else cc.icone end,
        ativo = coalesce((v_d ->> 'ativo')::boolean, cc.ativo),
        updated_at = now() at time zone 'utc'
     where cc.id = v_c.id
    returning * into v_c;
    return financeiro.categoria_cartao_flask(v_c);
end
$function$;

CREATE OR REPLACE FUNCTION financeiro.desativar_categoria_cartao(p_perfil_id integer, p_id integer)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_c public.categoria_cartao;
begin
    perform financeiro.exigir_escrita_categoria_cartao(p_perfil_id);
    v_c := financeiro.travar_categoria_cartao(p_perfil_id, p_id);
    update public.categoria_cartao cc set ativo = false, updated_at = now() at time zone 'utc'
     where cc.id = v_c.id
    returning * into v_c;
    return financeiro.categoria_cartao_flask(v_c);
end
$function$;

CREATE OR REPLACE FUNCTION financeiro.categorias_cartao_tela(p_perfil_id integer, p_ativo boolean)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    return coalesce((
        select jsonb_agg(financeiro.categoria_cartao_flask(cc) order by cc.nome, cc.id)
          from public.categoria_cartao cc
         where financeiro.pertence_ao_perfil(cc.perfil_financeiro_id, p_perfil_id)
           and (p_ativo is null or coalesce(cc.ativo, false) = p_ativo)), '[]'::jsonb);
end
$function$;

CREATE OR REPLACE FUNCTION financeiro.vincular_despesa_categoria_cartao(p_perfil_id integer, p_categoria_cartao_id integer, p_categoria_id integer, p_ativo boolean)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_c      public.categoria_cartao;
    v_ativo  boolean := coalesce(p_ativo, true);
    v_v      public.categoria_cartao_despesa;
    v_criado boolean := false;
begin
    perform financeiro.exigir_escrita_categoria_cartao(p_perfil_id);
    v_c := financeiro.travar_categoria_cartao(p_perfil_id, p_categoria_cartao_id);
    if p_categoria_id is null or not exists (select 1 from public.categoria c where c.id = p_categoria_id) then
        raise exception 'Categoria de despesa nao encontrada' using errcode = '22023';
    end if;
    if v_ativo and exists (select 1 from public.categoria_cartao_despesa v
                            where v.categoria_id = p_categoria_id and v.ativo and v.categoria_cartao_id <> v_c.id
                              and financeiro.pertence_ao_perfil(v.perfil_financeiro_id, p_perfil_id)) then
        raise exception 'Categoria de despesa ja vinculada a outra Categoria do Cartao ativa' using errcode = '22023';
    end if;
    select * into v_v from public.categoria_cartao_despesa v
     where v.categoria_cartao_id = v_c.id and v.categoria_id = p_categoria_id and v.perfil_financeiro_id = p_perfil_id
       for update;
    if found then
        update public.categoria_cartao_despesa v set ativo = v_ativo, updated_at = now() at time zone 'utc'
         where v.id = v_v.id
        returning * into v_v;
    else
        insert into public.categoria_cartao_despesa (perfil_financeiro_id, categoria_cartao_id, categoria_id, ativo,
                                                     created_at, updated_at)
        values (p_perfil_id, v_c.id, p_categoria_id, v_ativo, now() at time zone 'utc', now() at time zone 'utc')
        returning * into v_v;
        v_criado := true;
    end if;
    return financeiro.categoria_cartao_despesa_flask(v_v) || jsonb_build_object('created', v_criado);
end
$function$;

do $$
declare
    r record;
begin
    for r in select t.tgname, c.oid::regclass::text tabela from pg_trigger t join pg_class c on c.oid = t.tgrelid
              where t.tgname like 'categoria_do_dono_%' and not t.tgisinternal loop
        execute format('drop trigger %I on %s', r.tgname, r.tabela);
    end loop;
end
$$;
drop function financeiro.conferir_categoria_do_dono();
drop function financeiro.propagar_categorias_cartao_padrao();
drop function financeiro.manter_categoria_cartao_padrao(jsonb);
drop function financeiro.categorias_cartao_padrao_tela();
drop function financeiro.inicializar_categorias_cartao_do_perfil(integer);
drop function financeiro.inicializar_categorias_cartao(integer);
drop index public.categoria_cartao_padrao_por_perfil_uq;
alter table public.categoria_cartao drop column padrao_id;
drop table financeiro.categoria_cartao_padrao_despesa;
drop table financeiro.categoria_cartao_padrao;
drop function financeiro.alterar_categoria_da_palavra_chave(bigint, integer);
drop function financeiro.restaurar_palavra_chave_padrao(integer);
drop function financeiro.remover_minha_palavra_chave(bigint);
drop function financeiro.reassociar_palavra_chave_padrao(integer, integer);
drop function financeiro.desligar_palavra_chave_padrao(integer);
drop function financeiro.criar_minha_palavra_chave(integer, text);
drop function financeiro.palavras_efetivas(uuid);
drop table financeiro.palavra_chave_usuario;
drop function financeiro.exigir_alteracao_da_categoria(integer);
drop function financeiro.categoria_do_usuario(integer, uuid);
drop function financeiro.categoria_visivel(uuid, integer);
drop function financeiro.dono_do_perfil(integer);
drop function financeiro.exigir_catalogo_no_novo();
drop function financeiro.e_administrador_plataforma();
drop index public.categoria_particular_nome_uq;
drop index public.categoria_padrao_nome_uq;
drop index public.categoria_dono_idx;
alter table public.categoria drop column user_id;
alter table public.categoria add constraint ux_categoria_nome_global UNIQUE (nome);
