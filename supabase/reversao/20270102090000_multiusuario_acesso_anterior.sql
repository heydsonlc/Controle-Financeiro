-- FIN-MULTIUSUARIO-ACESSO-01 — reversao da migration 20270102090000.
--
-- GERADA por scripts/gerar_migration_acesso.py: nao editar a mao.
-- NAO aplicar no Supabase remoto sem autorizacao especifica. Antes: volte o frontend ao deploy anterior.
-- Recusada enquanto houver conta SUSPENSA (a regra anterior nao conhece a suspensao: a conta voltaria a ter acesso) ou
-- convite PENDENTE. O historico de convites e a auditoria de acesso sao apagados: exporte-os antes, se precisar.

do $$
begin
    if exists (select 1 from financeiro.usuario_plataforma where situacao <> 'ATIVA') then
        raise exception 'Reversao recusada: ha conta suspensa. A regra anterior devolveria o acesso a ela.';
    end if;
    if exists (select 1 from financeiro.convite where situacao = 'PENDENTE') then
        raise exception 'Reversao recusada: ha convite pendente. Revogue-o antes.';
    end if;
end
$$;

CREATE OR REPLACE FUNCTION financeiro.pode_acessar_perfil(p_perfil_id integer)
 RETURNS boolean
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
    select exists (
        select 1
          from financeiro.perfil_acesso a
          join public.perfil_financeiro p on p.id = a.perfil_financeiro_id
         where a.user_id = (select auth.uid())
           and a.perfil_financeiro_id = p_perfil_id
           and p.ativo
    )
$function$;

CREATE OR REPLACE FUNCTION financeiro.pode_gerir_perfil(p_perfil_id integer)
 RETURNS boolean
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
    select exists (
        select 1
          from financeiro.perfil_acesso a
          join public.perfil_financeiro p on p.id = a.perfil_financeiro_id
         where a.user_id = (select auth.uid())
           and a.perfil_financeiro_id = p_perfil_id
           and p.ativo
           and a.pode_gerir
           and p.user_id = a.user_id
    )
$function$;

CREATE OR REPLACE FUNCTION financeiro.gere_perfil(p_perfil_id integer)
 RETURNS boolean
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
    select exists (
        select 1
          from financeiro.perfil_acesso a
          join public.perfil_financeiro p on p.id = a.perfil_financeiro_id
         where a.user_id = (select auth.uid())
           and a.perfil_financeiro_id = p_perfil_id
           and a.pode_gerir
           and p.user_id = a.user_id
    )
$function$;

CREATE OR REPLACE FUNCTION financeiro.meus_perfis()
 RETURNS TABLE(id integer, nome text, tipo text, avatar text, cor text, padrao boolean, papel text)
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
    select p.id, p.nome::text, p.tipo::text, p.avatar::text, p.cor::text, p.padrao, a.papel
      from financeiro.perfil_acesso a
      join public.perfil_financeiro p on p.id = a.perfil_financeiro_id
     where a.user_id = (select auth.uid())
       and p.ativo
     order by p.padrao desc, p.nome
$function$;

CREATE OR REPLACE FUNCTION financeiro.perfis_para_configuracao()
 RETURNS TABLE(id integer, nome text, tipo text, documento text, avatar text, logo_url text, cor text, ativo boolean, padrao boolean, papel text, pode_gerir boolean)
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
    select p.id, p.nome::text, p.tipo::text, p.documento::text, p.avatar::text, p.logo_url::text, p.cor::text,
           p.ativo, p.padrao, a.papel, a.pode_gerir
      from financeiro.perfil_acesso a
      join public.perfil_financeiro p on p.id = a.perfil_financeiro_id
     where a.user_id = (select auth.uid())
     order by p.ativo desc, p.nome
$function$;

CREATE OR REPLACE FUNCTION financeiro.categorias_de_despesa()
 RETURNS TABLE(id integer, nome text, cor text)
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
    select c.id, c.nome::text, c.cor::text
      from public.categoria c
     where coalesce(c.ativo, true)
       and (c.user_id is null or c.user_id = (select auth.uid()))
       and exists (select 1 from financeiro.perfil_acesso a where a.user_id = (select auth.uid()))
     order by c.nome
$function$;

CREATE OR REPLACE FUNCTION financeiro.situacao_catalogo_categorias()
 RETURNS jsonb
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
    select jsonb_build_object(
        'escritor', coalesce((select c.escritor from financeiro.catalogo_categorias c), 'FLASK'),
        'gestor', exists (select 1 from financeiro.gestor_catalogo g where g.user_id = (select auth.uid())))
$function$;

CREATE OR REPLACE FUNCTION financeiro.sou_administrador_plataforma()
 RETURNS boolean
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
    select exists (select 1 from financeiro.administrador_plataforma a where a.user_id = (select auth.uid()))
$function$;

CREATE OR REPLACE FUNCTION financeiro.e_administrador_plataforma()
 RETURNS boolean
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
    select exists (select 1 from financeiro.administrador_plataforma a where a.user_id = (select auth.uid()))
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
    perform financeiro.inicializar_categorias_cartao(v_id);  -- FIN-CADASTROS-PADRAO-01

    if coalesce((p_dados ->> 'padrao')::boolean, false) and v_ativo then
        perform financeiro.aplicar_perfil_padrao(v_id);
    end if;
    return financeiro.perfil_em_json(v_id);
exception
    when unique_violation then
        raise exception 'Ja existe perfil financeiro com este nome' using errcode = '23505';
end
$function$;

CREATE OR REPLACE FUNCTION financeiro.criar_categoria(p_dados jsonb, p_chave uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_usuario   uuid := (select auth.uid());
    v_padrao    boolean := coalesce((p_dados ->> 'padrao')::boolean, false);
    v_anterior  financeiro.operacao_catalogo;
    v_d         jsonb;
    v_cat       public.categoria;
    v_resultado jsonb;
begin
    if v_usuario is null then
        raise exception 'Sessao obrigatoria' using errcode = '42501';
    end if;
    if v_padrao then
        perform financeiro.exigir_escrita_catalogo();
    else
        perform financeiro.exigir_catalogo_no_novo();
        if not exists (select 1 from financeiro.perfil_acesso a join public.perfil_financeiro p on p.id = a.perfil_financeiro_id
                        where a.user_id = v_usuario and a.pode_gerir and p.user_id = v_usuario and p.ativo) then
            raise exception 'Crie um perfil financeiro antes de cadastrar categorias' using errcode = '42501';
        end if;
    end if;
    if p_chave is null then
        raise exception 'Chave da operacao obrigatoria' using errcode = '22023';
    end if;
    perform pg_advisory_xact_lock(hashtextextended(p_chave::text, 20270101));
    select * into v_anterior from financeiro.operacao_catalogo o where o.chave = p_chave;
    if found then
        if v_anterior.user_id is distinct from v_usuario or v_anterior.operacao <> 'criar_categoria' then
            raise exception 'Chave da operacao ja usada' using errcode = '22023';
        end if;
        return v_anterior.resultado || jsonb_build_object('repetida', true);
    end if;
    v_d := financeiro.ler_dados_categoria(p_dados - 'padrao' - 'natureza', false);
    perform set_config('financeiro.categoria_dono', case when v_padrao then '' else v_usuario::text end, true);
    perform financeiro.validar_nome_categoria(v_d ->> 'nome', null);
    insert into public.categoria (perfil_financeiro_id, user_id, nome, descricao, cor, icone, ativo, sistemica, bloquear_edicao,
                                  bloquear_exclusao, criado_em)
    values (null, case when v_padrao then null else v_usuario end, v_d ->> 'nome', v_d ->> 'descricao', coalesce(v_d ->> 'cor', '#6c757d'),
            v_d ->> 'icone', coalesce((v_d ->> 'ativo')::boolean, true), false, false, false, now() at time zone 'utc')
    returning * into v_cat;
    if nullif(p_dados ->> 'natureza', '') is not null then
        if p_dados ->> 'natureza' not in ('CONSUMO', 'APORTE', 'AJUSTE_TECNICO', 'TRANSFERENCIA_INTERNA', 'NAO_DEFINIDO') then
            raise exception 'Natureza gerencial invalida' using errcode = '22023';
        end if;
        insert into financeiro.categoria_natureza (categoria_id, natureza, atualizado_em, atualizado_por)
        values (v_cat.id, p_dados ->> 'natureza', now(), v_usuario);
    end if;
    v_resultado := jsonb_build_object('categoria_id', v_cat.id, 'nome', v_cat.nome, 'padrao', v_padrao);
    insert into financeiro.operacao_catalogo (chave, user_id, operacao, resultado)
    values (p_chave, v_usuario, 'criar_categoria', v_resultado);
    return v_resultado;
exception
    when unique_violation then
        raise exception 'Ja existe uma categoria com este nome' using errcode = '22023';
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
    v_cat := financeiro.exigir_alteracao_da_categoria(p_categoria_id);
    v_d := financeiro.ler_dados_categoria(p_dados - 'padrao' - 'natureza', true);
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
    return jsonb_build_object('categoria_id', v_cat.id, 'nome', v_cat.nome, 'ativo', v_cat.ativo, 'padrao', v_cat.user_id is null);
exception
    when unique_violation then
        raise exception 'Ja existe outra categoria com este nome' using errcode = '22023';
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
    v_cat := financeiro.exigir_alteracao_da_categoria(p_categoria_id);
    if coalesce(v_cat.sistemica, false) or coalesce(v_cat.bloquear_exclusao, false) then
        raise exception 'Esta categoria e sistemica e nao pode ser excluida.' using errcode = 'P0001', hint = 'SISTEMICA';
    end if;
    v_vinculo := financeiro.vinculos_da_categoria(p_categoria_id);
    if v_vinculo is null and exists (select 1 from financeiro.palavra_chave_usuario u
                                      where u.categoria_id = p_categoria_id or u.categoria_padrao_id = p_categoria_id) then
        v_vinculo := 'palavras-chave de usuarios';
    end if;
    if v_vinculo is not null then
        raise exception 'Nao e possivel excluir categoria com registros vinculados (%). Inative-a.', v_vinculo
            using errcode = 'P0001', hint = 'COM_VINCULOS';
    end if;
    begin
        delete from public.categoria_palavra_chave p where p.categoria_id = p_categoria_id;
        delete from financeiro.categoria_natureza n where n.categoria_id = p_categoria_id;
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
    perform financeiro.exigir_alteracao_da_categoria(p_categoria_id);
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
                       'categoria_id', c.id, 'nome', c.nome, 'ativo', coalesce(c.ativo, true), 'padrao', c.user_id is null,
                       'natureza', financeiro.natureza_da_categoria(c.id),
                       'definida', exists (select 1 from financeiro.categoria_natureza n where n.categoria_id = c.id))
                   order by c.nome, c.id), '[]'::jsonb)
              from public.categoria c
             where c.user_id is null or c.user_id = (select auth.uid()));
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
    perform 1 from public.categoria c where c.id = p_categoria_id and c.user_id is null for update;
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
    return jsonb_build_object('id', v_reg.id, 'categoria_id', p_categoria_id, 'palavra', v_palavra, 'ativo', true, 'created', true);
end
$function$;

CREATE OR REPLACE FUNCTION financeiro.remover_palavra_chave(p_categoria_id integer, p_palavra_id integer)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_reg public.categoria_palavra_chave;
begin
    perform financeiro.exigir_escrita_catalogo();
    update public.categoria_palavra_chave p set ativo = false, updated_at = now() at time zone 'utc'
     where p.id = p_palavra_id and p.categoria_id = p_categoria_id
    returning * into v_reg;
    if not found then
        raise exception 'Palavra-chave nao encontrada' using errcode = 'P0001', hint = 'NAO_ENCONTRADA';
    end if;
    return jsonb_build_object('id', v_reg.id, 'categoria_id', p_categoria_id, 'palavra', v_reg.palavra, 'ativo', false);
end
$function$;

CREATE OR REPLACE FUNCTION financeiro.criar_minha_palavra_chave(p_categoria_id integer, p_palavra text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_usuario uuid := (select auth.uid());
    v_palavra text := regexp_replace(btrim(lower(coalesce(p_palavra, ''))), '\s+', ' ', 'g');
    v_id      bigint;
begin
    perform financeiro.exigir_catalogo_no_novo();
    if v_usuario is null then
        raise exception 'Sessao obrigatoria' using errcode = '42501';
    end if;
    if not exists (select 1 from public.categoria c where c.id = p_categoria_id and coalesce(c.ativo, true)
                      and (c.user_id is null or c.user_id = v_usuario)) then
        raise exception 'Categoria de Despesa nao encontrada' using errcode = 'P0001', hint = 'NAO_ENCONTRADA';
    end if;
    if v_palavra = '' then
        raise exception 'Palavra-chave e obrigatoria' using errcode = '22023';
    end if;
    if length(v_palavra) > 120 then
        raise exception 'Palavra-chave ate 120 caracteres' using errcode = '22023';
    end if;
    perform pg_advisory_xact_lock(hashtextextended('palavra_chave_usuario:' || v_usuario::text, 20270101));
    -- a mesma palavra padrao, nesta categoria, que ele tinha desligado ou reassociado: volta a valer (restaura)
    delete from financeiro.palavra_chave_usuario u
     where u.user_id = v_usuario and u.tipo <> 'NOVA' and u.categoria_padrao_id = p_categoria_id and u.palavra = v_palavra
    returning u.id into v_id;
    if v_id is not null then
        return jsonb_build_object('categoria_id', p_categoria_id, 'palavra', v_palavra, 'ativo', true, 'origem', 'PADRAO', 'restaurada', true);
    end if;
    if exists (select 1 from financeiro.palavras_efetivas(v_usuario) e where e.categoria_id = p_categoria_id and e.palavra = v_palavra) then
        raise exception 'Palavra-chave ja cadastrada para esta categoria' using errcode = '22023';
    end if;
    insert into financeiro.palavra_chave_usuario (user_id, tipo, palavra, categoria_id)
    values (v_usuario, 'NOVA', v_palavra, p_categoria_id)
    returning id into v_id;
    return jsonb_build_object('id', -v_id, 'categoria_id', p_categoria_id, 'palavra', v_palavra, 'ativo', true, 'origem', 'PROPRIA', 'created', true);
end
$function$;

CREATE OR REPLACE FUNCTION financeiro.desligar_palavra_chave_padrao(p_palavra_id integer)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_usuario uuid := (select auth.uid());
    v_p       public.categoria_palavra_chave;
    v_id      bigint;
begin
    perform financeiro.exigir_catalogo_no_novo();
    if v_usuario is null then
        raise exception 'Sessao obrigatoria' using errcode = '42501';
    end if;
    select * into v_p from public.categoria_palavra_chave p where p.id = p_palavra_id and p.ativo;
    if not found then
        raise exception 'Palavra-chave nao encontrada' using errcode = 'P0001', hint = 'NAO_ENCONTRADA';
    end if;
    insert into financeiro.palavra_chave_usuario (user_id, tipo, palavra, categoria_padrao_id)
    values (v_usuario, 'DESLIGADA', lower(btrim(v_p.palavra)), v_p.categoria_id)
    on conflict (user_id, categoria_padrao_id, palavra) where tipo <> 'NOVA'
    do update set tipo = 'DESLIGADA', categoria_id = null, atualizado_em = now()
    returning id into v_id;
    return jsonb_build_object('id', -v_id, 'categoria_id', v_p.categoria_id, 'palavra', lower(btrim(v_p.palavra)), 'ativo', false, 'origem', 'DESLIGADA');
end
$function$;

CREATE OR REPLACE FUNCTION financeiro.reassociar_palavra_chave_padrao(p_palavra_id integer, p_categoria_id integer)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_usuario uuid := (select auth.uid());
    v_p       public.categoria_palavra_chave;
    v_id      bigint;
begin
    perform financeiro.exigir_catalogo_no_novo();
    if v_usuario is null then
        raise exception 'Sessao obrigatoria' using errcode = '42501';
    end if;
    select * into v_p from public.categoria_palavra_chave p where p.id = p_palavra_id and p.ativo;
    if not found then
        raise exception 'Palavra-chave nao encontrada' using errcode = 'P0001', hint = 'NAO_ENCONTRADA';
    end if;
    if not exists (select 1 from public.categoria c where c.id = p_categoria_id and coalesce(c.ativo, true)
                      and (c.user_id is null or c.user_id = v_usuario)) then
        raise exception 'Categoria de Despesa nao encontrada' using errcode = 'P0001', hint = 'NAO_ENCONTRADA';
    end if;
    if p_categoria_id = v_p.categoria_id then
        raise exception 'A palavra-chave ja pertence a esta categoria' using errcode = '22023';
    end if;
    insert into financeiro.palavra_chave_usuario (user_id, tipo, palavra, categoria_id, categoria_padrao_id)
    values (v_usuario, 'REASSOCIADA', lower(btrim(v_p.palavra)), p_categoria_id, v_p.categoria_id)
    on conflict (user_id, categoria_padrao_id, palavra) where tipo <> 'NOVA'
    do update set tipo = 'REASSOCIADA', categoria_id = excluded.categoria_id, atualizado_em = now()
    returning id into v_id;
    return jsonb_build_object('id', -v_id, 'categoria_id', p_categoria_id, 'categoria_padrao_id', v_p.categoria_id,
                              'palavra', lower(btrim(v_p.palavra)), 'ativo', true, 'origem', 'REASSOCIADA');
end
$function$;

CREATE OR REPLACE FUNCTION financeiro.remover_minha_palavra_chave(p_ajuste_id bigint)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_u financeiro.palavra_chave_usuario;
begin
    perform financeiro.exigir_catalogo_no_novo();
    delete from financeiro.palavra_chave_usuario u where u.id = p_ajuste_id and u.user_id = (select auth.uid()) returning * into v_u;
    if not found then
        raise exception 'Palavra-chave nao encontrada' using errcode = 'P0001', hint = 'NAO_ENCONTRADA';
    end if;
    return jsonb_build_object('id', -v_u.id, 'palavra', v_u.palavra, 'tipo', v_u.tipo, 'removida', true,
                              'volta_ao_padrao', v_u.tipo <> 'NOVA');
end
$function$;

CREATE OR REPLACE FUNCTION financeiro.restaurar_palavra_chave_padrao(p_palavra_id integer)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_p public.categoria_palavra_chave;
    v_n integer;
begin
    perform financeiro.exigir_catalogo_no_novo();
    select * into v_p from public.categoria_palavra_chave p where p.id = p_palavra_id;
    if not found then
        raise exception 'Palavra-chave nao encontrada' using errcode = 'P0001', hint = 'NAO_ENCONTRADA';
    end if;
    delete from financeiro.palavra_chave_usuario u
     where u.user_id = (select auth.uid()) and u.tipo <> 'NOVA' and u.categoria_padrao_id = v_p.categoria_id and u.palavra = lower(btrim(v_p.palavra));
    get diagnostics v_n = row_count;
    return jsonb_build_object('id', v_p.id, 'categoria_id', v_p.categoria_id, 'palavra', lower(btrim(v_p.palavra)), 'restaurada', v_n > 0);
end
$function$;

CREATE OR REPLACE FUNCTION financeiro.categorias_cartao_padrao_tela()
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
begin
    if not financeiro.e_administrador_plataforma() then
        raise exception 'Restrito ao administrador da plataforma' using errcode = '42501', hint = 'SO_ADMINISTRADOR';
    end if;
    return coalesce((select jsonb_agg(jsonb_build_object('id', t.id, 'nome', t.nome, 'descricao', t.descricao, 'cor', t.cor, 'icone', t.icone,
                                                         'ativo', t.ativo, 'ordem', t.ordem,
                                                         'despesas', coalesce((select jsonb_agg(d.categoria_id order by d.categoria_id)
                                                                                 from financeiro.categoria_cartao_padrao_despesa d where d.padrao_id = t.id), '[]'::jsonb),
                                                         'perfis', (select count(*) from public.categoria_cartao cc where cc.padrao_id = t.id))
                                      order by t.ordem, t.id) from financeiro.categoria_cartao_padrao t), '[]'::jsonb);
end
$function$;

CREATE OR REPLACE FUNCTION financeiro.manter_categoria_cartao_padrao(p_dados jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_t  financeiro.categoria_cartao_padrao;
    v_id integer := (p_dados ->> 'id')::integer;
begin
    if not financeiro.e_administrador_plataforma() then
        raise exception 'Restrito ao administrador da plataforma' using errcode = '42501', hint = 'SO_ADMINISTRADOR';
    end if;
    perform financeiro.exigir_catalogo_no_novo();
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' then
        raise exception 'Dados invalidos' using errcode = '22023';
    end if;
    if v_id is null then
        insert into financeiro.categoria_cartao_padrao (nome, descricao, cor, icone, ativo, ordem)
        values (btrim(coalesce(p_dados ->> 'nome', '')), nullif(btrim(coalesce(p_dados ->> 'descricao', '')), ''),
                coalesce(nullif(p_dados ->> 'cor', ''), '#6c757d'), nullif(left(btrim(coalesce(p_dados ->> 'icone', '')), 50), ''),
                coalesce((p_dados ->> 'ativo')::boolean, true), coalesce((p_dados ->> 'ordem')::integer, 0))
        returning * into v_t;
    else
        update financeiro.categoria_cartao_padrao t
           set nome = coalesce(nullif(btrim(p_dados ->> 'nome'), ''), t.nome),
               descricao = case when p_dados ? 'descricao' then nullif(btrim(coalesce(p_dados ->> 'descricao', '')), '') else t.descricao end,
               cor = coalesce(nullif(p_dados ->> 'cor', ''), t.cor),
               icone = case when p_dados ? 'icone' then nullif(left(btrim(coalesce(p_dados ->> 'icone', '')), 50), '') else t.icone end,
               ativo = coalesce((p_dados ->> 'ativo')::boolean, t.ativo),
               ordem = coalesce((p_dados ->> 'ordem')::integer, t.ordem)
         where t.id = v_id
        returning * into v_t;
        if not found then
            raise exception 'Categoria de cartao padrao nao encontrada' using errcode = '22023';
        end if;
    end if;
    if p_dados ? 'despesas' then
        if exists (select 1 from jsonb_array_elements_text(p_dados -> 'despesas') x
                    where not exists (select 1 from public.categoria c where c.id = x::integer and c.user_id is null)) then
            raise exception 'O vinculo padrao so aceita categoria de despesa padrao' using errcode = '22023';
        end if;
        delete from financeiro.categoria_cartao_padrao_despesa d where d.padrao_id = v_t.id;
        insert into financeiro.categoria_cartao_padrao_despesa (padrao_id, categoria_id)
        select distinct v_t.id, x::integer from jsonb_array_elements_text(p_dados -> 'despesas') x;
    end if;
    return jsonb_build_object('id', v_t.id, 'nome', v_t.nome, 'ativo', v_t.ativo);
exception
    when unique_violation then
        raise exception 'Ja existe uma categoria de cartao padrao com este nome' using errcode = '22023';
    when check_violation or invalid_text_representation then
        raise exception 'Dados invalidos' using errcode = '22023';
end
$function$;

CREATE OR REPLACE FUNCTION financeiro.propagar_categorias_cartao_padrao()
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    p record;
    r jsonb;
    v_perfis integer := 0;
    v_criadas integer := 0;
    v_adotadas integer := 0;
begin
    if not financeiro.e_administrador_plataforma() then
        raise exception 'Restrito ao administrador da plataforma' using errcode = '42501', hint = 'SO_ADMINISTRADOR';
    end if;
    perform financeiro.exigir_catalogo_no_novo();
    -- so os perfis cujas gravacoes ja sao do novo aplicativo (os demais recebem quando passarem a ser)
    for p in select f.id from public.perfil_financeiro f
              where exists (select 1 from financeiro.gerador_recorrencia g where g.perfil_financeiro_id = f.id and g.gerador = 'NOVO')
              order by f.id loop
        r := financeiro.inicializar_categorias_cartao(p.id);
        v_perfis := v_perfis + 1;
        v_criadas := v_criadas + (r ->> 'criadas')::integer;
        v_adotadas := v_adotadas + (r ->> 'adotadas')::integer;
    end loop;
    return jsonb_build_object('perfis', v_perfis, 'criadas', v_criadas, 'adotadas', v_adotadas);
end
$function$;

CREATE OR REPLACE FUNCTION financeiro.previa_reclassificacao_categorias(p_manifesto jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
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
    v_pessoal integer := financeiro.perfil_guarda_legado();
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
$function$;

CREATE OR REPLACE FUNCTION financeiro.criar_tr(p_dados jsonb, p_chave uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
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
$function$;

CREATE OR REPLACE FUNCTION financeiro.editar_tr(p_competencia text, p_dados jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_comp  text;
    v_i     public.indice_tr_mensal;
    v_valor numeric;
    v_fonte text;
begin
    perform financeiro.idx_exigir_acesso(true);
    perform financeiro.idx_travar();
    v_comp := financeiro.idx_competencia(p_competencia);
    select * into v_i from public.indice_tr_mensal i where i.competencia = v_comp for update;
    if not found then
        raise exception 'TR da competência % não encontrada', v_comp using errcode = '22023';
    end if;
    if financeiro.idx_tr_usada(v_comp) then
        raise exception 'Esta TR já é usada em parcelas de financiamento SAC/TR. Para alterar, será necessário revisar ou recalcular os cronogramas afetados em uma etapa própria.'
            using errcode = '22023';
    end if;
    v_valor := financeiro.idx_decimal(p_dados ->> 'valor_percentual');
    v_fonte := case when p_dados ? 'fonte' and p_dados -> 'fonte' <> 'null'::jsonb
                    then coalesce(nullif(p_dados ->> 'fonte', ''), 'BACEN') else v_i.fonte end;
    perform financeiro.idx_auditar(v_comp, 'EDICAO', v_i.valor_decimal, v_valor, v_i.fonte, v_fonte);
    update public.indice_tr_mensal i
       set valor_decimal = v_valor, fonte = v_fonte, atualizado_em = (now() at time zone 'utc')::timestamp
     where i.id = v_i.id
    returning * into strict v_i;
    return jsonb_build_object('data', financeiro.idx_tr_json(v_i));
end
$function$;

CREATE OR REPLACE FUNCTION financeiro.importar_tr(p_dados jsonb, p_chave uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
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
$function$;

CREATE OR REPLACE FUNCTION financeiro.tr_faltantes(p_inicio text, p_fim text)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_inicio text := financeiro.idx_competencia(p_inicio);
    v_fim    text := financeiro.idx_competencia(p_fim);
begin
    perform financeiro.idx_exigir_acesso(false);
    if v_inicio > v_fim then
        raise exception 'Competência inicial deve ser menor ou igual à final' using errcode = '22023';
    end if;
    return coalesce((
        select jsonb_agg(to_char(m, 'YYYY-MM') order by m)
          from generate_series(to_date(v_inicio || '-01', 'YYYY-MM-DD'), to_date(v_fim || '-01', 'YYYY-MM-DD'),
                               interval '1 month') m
         where not exists (select 1 from public.indice_tr_mensal i where i.competencia = to_char(m, 'YYYY-MM'))), '[]'::jsonb);
end
$function$;

CREATE OR REPLACE FUNCTION financeiro.tr_oficial_tela(p_ano integer DEFAULT NULL::integer, p_inicio text DEFAULT NULL::text, p_fim text DEFAULT NULL::text)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_inicio text := case when coalesce(p_inicio, '') <> '' then financeiro.idx_competencia(p_inicio) end;
    v_fim    text := case when coalesce(p_fim, '') <> '' then financeiro.idx_competencia(p_fim) end;
begin
    perform financeiro.idx_exigir_acesso(false);
    return coalesce((
        select jsonb_agg(financeiro.idx_tr_json(i) order by i.competencia desc)
          from public.indice_tr_mensal i
         where (p_ano is null or i.ano = p_ano)
           and (v_inicio is null or i.competencia >= v_inicio)
           and (v_fim is null or i.competencia <= v_fim)), '[]'::jsonb);
end
$function$;

CREATE OR REPLACE FUNCTION financeiro.exigir_escrita_catalogo()
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_escritor text;
begin
    if (select auth.uid()) is null then
        raise exception 'Esta conta nao administra o catalogo de categorias' using errcode = '42501';
    end if;
    perform pg_advisory_xact_lock(20261125, 0);
    select c.escritor into v_escritor from financeiro.catalogo_categorias c for share;
    if v_escritor is distinct from 'NOVO' then
        raise exception 'O catalogo de categorias ainda e administrado pelo sistema atual (Flask). Nada foi gravado.'
            using errcode = 'P0001', hint = 'CATALOGO_FLASK';
    end if;
    if not exists (select 1 from financeiro.gestor_catalogo g where g.user_id = (select auth.uid())) then
        raise exception 'Esta conta nao administra o catalogo de categorias' using errcode = '42501';
    end if;
end
$function$;

drop trigger perfil_acesso_conta on financeiro.perfil_acesso;
drop function financeiro.conta_no_vinculo();
drop function financeiro.auditoria_acesso_tela(integer);
drop function financeiro.reativar_usuario(uuid);
drop function financeiro.suspender_usuario(uuid, text);
drop function financeiro.usuarios_tela();
drop function financeiro.ativar_minha_conta(jsonb);
drop function financeiro.situacao_da_minha_conta();
drop function financeiro.convites_tela();
drop function financeiro.registrar_reenvio_convite(uuid, integer);
drop function financeiro.revogar_convite(uuid);
drop function financeiro.criar_convite(jsonb);
drop function financeiro.convite_em_json(financeiro.convite);
drop function financeiro.definir_conta_plataforma(uuid, text, text, text);
drop function financeiro.exigir_administrador();
drop function financeiro.auditar_acesso(text, text, jsonb);
drop function financeiro.exigir_conta_ativa();
drop function financeiro.conta_ativa();
drop table financeiro.usuario_plataforma;
drop table financeiro.convite;
drop table financeiro.auditoria_acesso;
