-- FIN-CADASTROS-PADRAO-01 — catalogo padrao do aplicativo e personalizacao por usuario.
--
-- GERADA por scripts/gerar_migration_cadastros_padrao.py (parte fixa em scripts/cadastros_padrao_estrutura.sql): nao editar
-- o arquivo da migration a mao.
--
-- Nenhum registro financeiro e alterado por esta migration, nenhuma categoria muda de identificador e nada e copiado.
--   1. Categoria de despesa com DONO: public.categoria.user_id nulo = categoria PADRAO do aplicativo (todas as atuais);
--      preenchido = categoria PARTICULAR daquele usuario, invisivel aos demais. O banco recusa gravar, em qualquer tabela,
--      uma categoria particular num registro de perfil de outro dono.
--   2. Padrao protegido: so quem administra o catalogo cria, edita, exclui ou muda a natureza de uma categoria padrao. O
--      usuario faz isso nas suas particulares. Com registros vinculados, a categoria e inativada, nunca excluida.
--   3. Palavras-chave em duas camadas: as padrao (tabela atual) + os ajustes de cada usuario (nova, desligada,
--      reassociada). Ninguem recebe copia: a regra efetiva e calculada. Ajuste de um usuario nao alcanca outro; mudanca
--      do administrador alcanca quem nao ajustou aquela palavra. Palavra-chave so influencia SUGESTAO: nenhuma despesa
--      ou compra ja classificada muda.
--   4. Categorias de cartao: modelo do aplicativo (financeiro.categoria_cartao_padrao) copiado para cada perfil, com
--      marca de origem. A copia nao duplica (repetir nao cria nada) e so acrescenta. Nome e situacao da categoria padrao
--      ficam protegidos; categorias adicionais do perfil continuam livres.
--   5. A tela fiscal deixa de ler o catalogo pela guarda dos registros sem perfil (FIN-MULTIUSUARIO-SEGURANCA-01).

-- =====================================================================================================================
-- 1. Apoio
-- =====================================================================================================================
alter table public.categoria add column user_id uuid references auth.users (id) on delete restrict;
comment on column public.categoria.user_id is
    'FIN-CADASTROS-PADRAO-01: nulo = categoria padrao do aplicativo; preenchido = categoria particular desse usuario.';
create index categoria_dono_idx on public.categoria (user_id);

create function financeiro.dono_do_perfil(p_perfil_id integer)
    returns uuid
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select p.user_id from public.perfil_financeiro p where p.id = p_perfil_id
$$;

-- A categoria (pelo dono dela) aparece para o perfil: padrao, ou particular do dono do perfil.
create function financeiro.categoria_visivel(p_categoria_user uuid, p_perfil_id integer)
    returns boolean
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select p_categoria_user is null or p_categoria_user = financeiro.dono_do_perfil(p_perfil_id)
$$;

-- A categoria existe para este usuario (padrao ou dele).
create function financeiro.categoria_do_usuario(p_categoria_id integer, p_user_id uuid)
    returns boolean
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select exists (select 1 from public.categoria c where c.id = p_categoria_id and (c.user_id is null or c.user_id = p_user_id))
$$;

create function financeiro.e_administrador_plataforma()
    returns boolean
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select exists (select 1 from financeiro.administrador_plataforma a where a.user_id = (select auth.uid()))
$$;
revoke execute on function financeiro.dono_do_perfil(integer) from public, anon, authenticated;
revoke execute on function financeiro.categoria_visivel(uuid, integer) from public, anon, authenticated;
revoke execute on function financeiro.categoria_do_usuario(integer, uuid) from public, anon, authenticated;
revoke execute on function financeiro.e_administrador_plataforma() from public, anon, authenticated;

-- Enquanto o catalogo de categorias for administrado pelo sistema anterior, NADA do catalogo e gravado pelo novo aplicativo:
-- nem o padrao (exigir_escrita_catalogo) nem o que e do usuario (categoria particular, ajuste de palavra-chave) nem o modelo
-- de categorias de cartao. O sistema anterior nao conhece o dono da categoria e mostraria a particular a todos.
create function financeiro.exigir_catalogo_no_novo()
    returns void
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_escritor text;
begin
    perform pg_advisory_xact_lock_shared(20261125, 0);
    select c.escritor into v_escritor from financeiro.catalogo_categorias c;
    if v_escritor is distinct from 'NOVO' then
        raise exception 'O catalogo de categorias ainda e administrado pelo sistema atual (Flask). Nada foi gravado.'
            using errcode = 'P0001', hint = 'CATALOGO_FLASK';
    end if;
end
$$;
revoke execute on function financeiro.exigir_catalogo_no_novo() from public, anon, authenticated;

-- =====================================================================================================================
-- 2. Categoria de despesa com dono
-- =====================================================================================================================
-- (a coluna do dono e criada no inicio da migration: as funcoes de apoio ja a usam)

do $$
declare
    r record;
begin
    -- a unicidade global do nome (restricao ou indice herdado do Flask), qualquer que seja o nome dela
    for r in select c.conname from pg_constraint c
              where c.conrelid = 'public.categoria'::regclass and c.contype = 'u'
                and (select array_agg(a.attname::text) from pg_attribute a where a.attrelid = c.conrelid and a.attnum = any(c.conkey)) = array['nome'] loop
        execute format('alter table public.categoria drop constraint %I', r.conname);
    end loop;
    for r in select i.indexrelid::regclass::text nome from pg_index i
              where i.indrelid = 'public.categoria'::regclass and i.indisunique and not i.indisprimary and i.indnatts = 1
                and (select a.attname from pg_attribute a where a.attrelid = i.indrelid and a.attnum = i.indkey[0]) = 'nome' loop
        execute format('drop index %s', r.nome);
    end loop;
end
$$;
create unique index categoria_padrao_nome_uq on public.categoria (lower(btrim(nome))) where user_id is null;
create unique index categoria_particular_nome_uq on public.categoria (user_id, lower(btrim(nome))) where user_id is not null;

-- Rede de protecao nos DADOS: uma categoria particular so entra em registro de perfil do proprio dono dela. Vale para
-- toda tabela que aponta para a categoria, qualquer que seja a funcao que grave (as 16 colunas de hoje e as futuras que
-- esta migration encontrar). As palavras-chave PADRAO so apontam para categoria padrao.
create function financeiro.conferir_categoria_do_dono()
    returns trigger
    language plpgsql
    security definer
    set search_path = ''
as $$
declare
    v_linha  jsonb := to_jsonb(new);
    v_cat    integer := (v_linha ->> tg_argv[0])::integer;
    v_dono   uuid;
    v_perfil integer;
begin
    if v_cat is null then
        return new;
    end if;
    if tg_op = 'UPDATE' and (to_jsonb(old) ->> tg_argv[0])::integer is not distinct from v_cat
       and (tg_argv[1] in ('PADRAO', 'USUARIO') or (to_jsonb(old) ->> tg_argv[1]) is not distinct from (v_linha ->> tg_argv[1])) then
        return new;  -- nem a categoria nem o perfil mudaram
    end if;
    select c.user_id into v_dono from public.categoria c where c.id = v_cat;
    if v_dono is null then
        return new;  -- categoria padrao (ou inexistente: a chave estrangeira responde)
    end if;
    if tg_argv[1] = 'PADRAO' then
        raise exception 'Categoria de Despesa nao encontrada' using errcode = '22023', hint = 'CATEGORIA_PARTICULAR';
    end if;
    if tg_argv[1] = 'USUARIO' then  -- registro do proprio usuario (coluna user_id): so categoria padrao ou dele
        if (v_linha ->> 'user_id')::uuid is distinct from v_dono then
            raise exception 'Categoria de Despesa nao encontrada' using errcode = '22023', hint = 'CATEGORIA_DE_OUTRO_USUARIO';
        end if;
        return new;
    end if;
    v_perfil := (v_linha ->> tg_argv[1])::integer;
    if v_perfil is null or financeiro.dono_do_perfil(v_perfil) is distinct from v_dono then
        raise exception 'Categoria de Despesa nao encontrada' using errcode = '22023', hint = 'CATEGORIA_DE_OUTRO_USUARIO';
    end if;
    return new;
end
$$;
revoke execute on function financeiro.conferir_categoria_do_dono() from public, anon, authenticated;

do $$
declare
    r record;
    v_perfil text;
begin
    for r in select t.oid::regclass::text tabela, t.relname, a.attname coluna, t.oid
               from pg_constraint k join pg_class t on t.oid = k.conrelid join pg_namespace n on n.oid = t.relnamespace
               join pg_attribute a on a.attrelid = k.conrelid and a.attnum = k.conkey[1]
              where k.contype = 'f' and k.confrelid = 'public.categoria'::regclass and cardinality(k.conkey) = 1
                and n.nspname in ('public', 'financeiro') order by 1, 3 loop
        if r.relname = 'categoria_palavra_chave' then
            v_perfil := 'PADRAO';
        elsif exists (select 1 from pg_attribute a where a.attrelid = r.oid and a.attname = 'perfil_financeiro_id' and not a.attisdropped) then
            v_perfil := 'perfil_financeiro_id';
        else
            raise exception 'Tabela % aponta para a categoria e nao tem perfil: defina a regra antes de aplicar esta migration.', r.tabela;
        end if;
        execute format('create trigger %I before insert or update on %s for each row execute function financeiro.conferir_categoria_do_dono(%L, %L)',
                       'categoria_do_dono_' || r.coluna, r.tabela, r.coluna, v_perfil);
    end loop;
end
$$;

-- Nome: unico entre as categorias padrao; a particular nao repete nome de padrao nem de outra particular do mesmo dono.
-- (p_user nulo = categoria padrao.) Substitui a assinatura anterior (nome, id).
create or replace function financeiro.validar_nome_categoria(p_nome text, p_id integer)
    returns void
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_codigo text;
    v_user   uuid := (select c.user_id from public.categoria c where c.id = p_id);
begin
    if p_id is null then
        v_user := nullif(current_setting('financeiro.categoria_dono', true), '')::uuid;  -- definido por criar_categoria
    end if;
    if exists (select 1 from public.categoria c
                where lower(btrim(c.nome)) = lower(btrim(p_nome)) and c.id is distinct from p_id
                  and (c.user_id is null or c.user_id = v_user)) then
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
$$;

-- Leituras: o catalogo padrao + as particulares de quem pede (ou do dono do perfil).
create or replace function financeiro.categorias_de_despesa()
    returns table (id integer, nome text, cor text)
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select c.id, c.nome::text, c.cor::text
      from public.categoria c
     where coalesce(c.ativo, true)
       and (c.user_id is null or c.user_id = (select auth.uid()))
       and exists (select 1 from financeiro.perfil_acesso a where a.user_id = (select auth.uid()))
     order by c.nome
$$;

create or replace function financeiro.categorias_tela(p_perfil_id integer, p_ativo boolean)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_dono uuid;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    v_dono := financeiro.dono_do_perfil(p_perfil_id);
    return coalesce((
        select jsonb_agg(financeiro.categoria_flask(c)
                         || jsonb_build_object('padrao', c.user_id is null,
                                               'natureza', financeiro.natureza_da_categoria(c.id),
                                               'palavras_chave_count', (select count(*) from financeiro.palavras_efetivas(v_dono) p where p.categoria_id = c.id))
                         order by c.id)
          from public.categoria c
         where (c.user_id is null or c.user_id = v_dono)
           and (p_ativo is null or c.ativo is not distinct from p_ativo)), '[]'::jsonb);
end
$$;

create or replace function financeiro.mobilidade_categorias_tela(p_perfil_id integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_dono uuid;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    v_dono := financeiro.dono_do_perfil(p_perfil_id);
    return coalesce((select jsonb_agg(financeiro.categoria_flask(c) || jsonb_build_object(
                                          'palavras_chave_count', (select count(*) from financeiro.palavras_efetivas(v_dono) k where k.categoria_id = c.id))
                                      order by c.id)
                       from public.categoria c
                      where c.user_id is null or c.user_id = v_dono), '[]'::jsonb);
end
$$;

create or replace function financeiro.naturezas_das_categorias()
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
                       'categoria_id', c.id, 'nome', c.nome, 'ativo', coalesce(c.ativo, true), 'padrao', c.user_id is null,
                       'natureza', financeiro.natureza_da_categoria(c.id),
                       'definida', exists (select 1 from financeiro.categoria_natureza n where n.categoria_id = c.id))
                   order by c.nome, c.id), '[]'::jsonb)
              from public.categoria c
             where c.user_id is null or c.user_id = (select auth.uid()));
end
$$;

-- Criar: particular por padrao (de quem pede). Categoria padrao so com p_dados.padrao = true e por quem administra o catalogo.
create or replace function financeiro.criar_categoria(p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
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
$$;

-- Quem pode alterar esta categoria: a padrao, quem administra o catalogo; a particular, o dono. A de outro usuario nao
-- "existe" para quem pede (mesma resposta de uma categoria inexistente).
create function financeiro.exigir_alteracao_da_categoria(p_categoria_id integer)
    returns public.categoria
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_usuario uuid := (select auth.uid());
    v_cat     public.categoria;
begin
    if v_usuario is null then
        raise exception 'Sessao obrigatoria' using errcode = '42501';
    end if;
    perform financeiro.exigir_catalogo_no_novo();
    select * into v_cat from public.categoria c where c.id = p_categoria_id for update;
    if not found or (v_cat.user_id is not null and v_cat.user_id <> v_usuario) then
        raise exception 'Categoria nao encontrada' using errcode = 'P0001', hint = 'NAO_ENCONTRADA';
    end if;
    if v_cat.user_id is null then
        perform financeiro.exigir_escrita_catalogo();
    end if;
    return v_cat;
end
$$;
revoke execute on function financeiro.exigir_alteracao_da_categoria(integer) from public, anon, authenticated;

create or replace function financeiro.editar_categoria(p_categoria_id integer, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
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
$$;

create or replace function financeiro.excluir_categoria(p_categoria_id integer)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
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
$$;

-- Natureza gerencial: da categoria padrao, quem administra o catalogo; da particular, o dono. So muda a classificacao
-- gerencial (Consumo, Aportes, Outras saidas): nenhum valor, saldo ou pagamento e tocado.
create or replace function financeiro.definir_natureza_categoria(p_categoria_id integer, p_natureza text, p_chave uuid)
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
$$;

-- =====================================================================================================================
-- 3. Palavras-chave: padrao + ajustes do usuario
-- =====================================================================================================================
-- tipo NOVA: palavra do usuario em categoria_id. DESLIGADA: a palavra padrao de categoria_padrao_id nao vale para ele.
-- REASSOCIADA: a palavra padrao de categoria_padrao_id vale, para ele, em categoria_id.
-- O ajuste se refere ao par (categoria padrao, palavra), nao a linha: continua valendo se o administrador desativar e
-- reativar a regra, e nao alcanca a mesma palavra em outra categoria padrao.
create table financeiro.palavra_chave_usuario (
    id                  bigint      generated always as identity primary key,
    user_id             uuid        not null references auth.users (id) on delete cascade,
    tipo                text        not null check (tipo in ('NOVA', 'DESLIGADA', 'REASSOCIADA')),
    palavra             text        not null check (palavra = lower(btrim(palavra)) and length(palavra) between 1 and 120),
    categoria_id        integer     references public.categoria (id) on delete restrict,
    categoria_padrao_id integer     references public.categoria (id) on delete restrict,
    criado_em           timestamptz not null default now(),
    atualizado_em       timestamptz not null default now(),
    check ((tipo = 'NOVA' and categoria_id is not null and categoria_padrao_id is null)
           or (tipo = 'DESLIGADA' and categoria_id is null and categoria_padrao_id is not null)
           or (tipo = 'REASSOCIADA' and categoria_id is not null and categoria_padrao_id is not null and categoria_id <> categoria_padrao_id))
);
create unique index palavra_chave_usuario_nova_uq on financeiro.palavra_chave_usuario (user_id, categoria_id, palavra) where tipo = 'NOVA';
create unique index palavra_chave_usuario_ajuste_uq on financeiro.palavra_chave_usuario (user_id, categoria_padrao_id, palavra) where tipo <> 'NOVA';
alter table financeiro.palavra_chave_usuario enable row level security;
revoke all on table financeiro.palavra_chave_usuario from public, anon, authenticated;
-- A mesma rede de protecao das outras tabelas: o destino do ajuste e categoria padrao ou do proprio usuario; a origem
-- (a regra padrao ajustada) e sempre categoria padrao.
create trigger categoria_do_dono_categoria_id before insert or update on financeiro.palavra_chave_usuario
    for each row execute function financeiro.conferir_categoria_do_dono('categoria_id', 'USUARIO');
create trigger categoria_do_dono_categoria_padrao_id before insert or update on financeiro.palavra_chave_usuario
    for each row execute function financeiro.conferir_categoria_do_dono('categoria_padrao_id', 'PADRAO');
comment on table financeiro.palavra_chave_usuario is
    'FIN-CADASTROS-PADRAO-01: ajustes de palavras-chave de cada usuario sobre o catalogo padrao (nenhuma copia do padrao).';

-- A regra efetiva de um usuario. ordem: a da palavra padrao (o id dela) ou, nas do usuario, depois de todas as padrao.
create function financeiro.palavras_efetivas(p_user_id uuid)
    returns table (categoria_id integer, palavra text, origem text, ordem bigint, padrao_id integer, ajuste_id bigint)
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select p.categoria_id, lower(btrim(p.palavra))::text, 'PADRAO'::text, p.id::bigint, p.id, null::bigint
      from public.categoria_palavra_chave p
     where p.ativo
       and not exists (select 1 from financeiro.palavra_chave_usuario u
                        where u.user_id = p_user_id and u.tipo <> 'NOVA' and u.categoria_padrao_id = p.categoria_id
                          and u.palavra = lower(btrim(p.palavra)))
    union all
    select u.categoria_id, u.palavra, case u.tipo when 'NOVA' then 'PROPRIA' else 'REASSOCIADA' end, 1000000000 + u.id, null::integer, u.id
      from financeiro.palavra_chave_usuario u
      join public.categoria c on c.id = u.categoria_id and (c.user_id is null or c.user_id = p_user_id)
     where u.user_id = p_user_id and u.tipo in ('NOVA', 'REASSOCIADA')
       -- a reassociacao so vale enquanto a regra padrao de origem existir e estiver ativa
       and (u.tipo = 'NOVA' or exists (select 1 from public.categoria_palavra_chave p
                                        where p.categoria_id = u.categoria_padrao_id and p.ativo and lower(btrim(p.palavra)) = u.palavra))
$$;
revoke execute on function financeiro.palavras_efetivas(uuid) from public, anon, authenticated;

-- Tela: por categoria, as palavras efetivas do dono do perfil e, marcadas como inativas, as padrao que ele desligou
-- (para restaurar). id > 0: palavra padrao (o id dela). id < 0: ajuste do usuario (o id do ajuste, negativo).
create or replace function financeiro.palavras_chave_tela(p_perfil_id integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_dono uuid;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    v_dono := financeiro.dono_do_perfil(p_perfil_id);
    return coalesce((
        select jsonb_object_agg(x.categoria_id::text, x.palavras)
          from (select y.categoria_id,
                       jsonb_agg(jsonb_build_object('id', y.id, 'categoria_id', y.categoria_id, 'palavra', y.palavra, 'ativo', y.ativo,
                                                    'origem', y.origem,
                                                    -- as datas da palavra padrao (como sempre); do ajuste, as dele
                                                    'created_at', case when y.id > 0 then (select financeiro.iso_python(p.created_at) from public.categoria_palavra_chave p where p.id = y.id)
                                                                       else (select financeiro.iso_python((u.criado_em at time zone 'utc')::timestamp) from financeiro.palavra_chave_usuario u where u.id = -y.id) end,
                                                    'updated_at', case when y.id > 0 then (select financeiro.iso_python(p.updated_at) from public.categoria_palavra_chave p where p.id = y.id)
                                                                       else (select financeiro.iso_python((u.atualizado_em at time zone 'utc')::timestamp) from financeiro.palavra_chave_usuario u where u.id = -y.id) end)
                                 -- FIN-MULTIUSUARIO-AJUSTES-FINAIS-01: so quando ha reassociacao (as demais linhas ficam como eram)
                                 || case when y.categoria_padrao_id is not null then jsonb_build_object('categoria_padrao_id', y.categoria_padrao_id) else '{}'::jsonb end
                                 || case when y.categoria_destino_id is not null then jsonb_build_object('categoria_destino_id', y.categoria_destino_id) else '{}'::jsonb end
                                 order by y.palavra, y.id) palavras
                  from (select e.categoria_id, coalesce(e.padrao_id::bigint, -e.ajuste_id) id, e.palavra, true ativo, e.origem,
                               case when e.origem = 'REASSOCIADA' then (select u.categoria_padrao_id from financeiro.palavra_chave_usuario u where u.id = e.ajuste_id) end categoria_padrao_id,
                               null::integer categoria_destino_id
                          from financeiro.palavras_efetivas(v_dono) e
                        union all
                        select u.categoria_padrao_id, -u.id, u.palavra, false, case u.tipo when 'DESLIGADA' then 'DESLIGADA' else 'MOVIDA' end, null::integer,
                               case when u.tipo = 'REASSOCIADA' then u.categoria_id end
                          from financeiro.palavra_chave_usuario u
                         where u.user_id = v_dono and u.tipo in ('DESLIGADA', 'REASSOCIADA')
                           and exists (select 1 from public.categoria_palavra_chave p
                                        where p.categoria_id = u.categoria_padrao_id and p.ativo and lower(btrim(p.palavra)) = u.palavra)) y
                 group by y.categoria_id) x), '{}'::jsonb);
end
$$;

-- Palavra-chave PADRAO (quem administra o catalogo): so em categoria padrao. Texto anterior + essa conferencia.
create or replace function financeiro.criar_palavra_chave(p_categoria_id integer, p_palavra text)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
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
$$;

-- Ajustes do proprio usuario (sempre sobre auth.uid(); nenhum toca o catalogo padrao nem os ajustes de outro usuario).
create function financeiro.criar_minha_palavra_chave(p_categoria_id integer, p_palavra text)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
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
$$;

create function financeiro.desligar_palavra_chave_padrao(p_palavra_id integer)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
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
$$;

create function financeiro.reassociar_palavra_chave_padrao(p_palavra_id integer, p_categoria_id integer)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
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
$$;

-- Remove um ajuste do proprio usuario: a palavra propria deixa de existir; a desligada ou reassociada volta ao padrao.
create function financeiro.remover_minha_palavra_chave(p_ajuste_id bigint)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
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
$$;

-- Restaura uma palavra padrao que o usuario tinha desligado ou reassociado (pelo id da palavra padrao).
create function financeiro.restaurar_palavra_chave_padrao(p_palavra_id integer)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
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
$$;
-- FIN-MULTIUSUARIO-AJUSTES-FINAIS-01 — acao "Alterar categoria" da tela. Vale so para a conta de quem pede: palavra padrao ->
-- ajuste REASSOCIADA do usuario (o catalogo padrao nao muda); palavra propria -> muda a categoria dela; voltar a categoria de
-- origem restaura o padrao. Repetir a mesma alteracao nao duplica nem falha. Na tela (palavras_chave_tela) a reassociada
-- informa a categoria padrao de origem, e a categoria de origem mostra a palavra que saiu dela (inativa, origem MOVIDA).
-- p_id > 0: palavra PADRAO (o id dela). p_id < 0: ajuste do usuario (o id que palavras_chave_tela devolve, negativo).
create function financeiro.alterar_categoria_da_palavra_chave(p_id bigint, p_categoria_id integer)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_usuario uuid := (select auth.uid());
    v_p       public.categoria_palavra_chave;
    v_u       financeiro.palavra_chave_usuario;
    v_palavra text;
    v_origem  integer;   -- categoria padrao de origem (nula na palavra propria)
    v_atual   integer;   -- categoria em que a palavra vale hoje para o usuario
begin
    perform financeiro.exigir_catalogo_no_novo();
    if v_usuario is null then
        raise exception 'Sessao obrigatoria' using errcode = '42501';
    end if;
    if p_id is null or p_id = 0 then
        raise exception 'Palavra-chave nao encontrada' using errcode = 'P0001', hint = 'NAO_ENCONTRADA';
    end if;
    perform pg_advisory_xact_lock(hashtextextended('palavra_chave_usuario:' || v_usuario::text, 20270101));
    if p_id > 0 then
        select * into v_p from public.categoria_palavra_chave p where p.id = p_id and p.ativo;
        if not found then
            raise exception 'Palavra-chave nao encontrada' using errcode = 'P0001', hint = 'NAO_ENCONTRADA';
        end if;
        v_palavra := lower(btrim(v_p.palavra));
        v_origem := v_p.categoria_id;
        select * into v_u from financeiro.palavra_chave_usuario u
         where u.user_id = v_usuario and u.tipo <> 'NOVA' and u.categoria_padrao_id = v_origem and u.palavra = v_palavra for update;
        v_atual := case when v_u.id is null then v_origem when v_u.tipo = 'REASSOCIADA' then v_u.categoria_id end;
    else
        -- o ajuste de outro usuario responde como inexistente
        select * into v_u from financeiro.palavra_chave_usuario u where u.id = -p_id and u.user_id = v_usuario for update;
        if not found then
            raise exception 'Palavra-chave nao encontrada' using errcode = 'P0001', hint = 'NAO_ENCONTRADA';
        end if;
        v_palavra := v_u.palavra;
        v_origem := v_u.categoria_padrao_id;
        v_atual := v_u.categoria_id;
    end if;
    -- destino: categoria ativa, padrao ou do proprio usuario (a particular de outro responde como inexistente)
    if p_categoria_id is null or not exists (select 1 from public.categoria c where c.id = p_categoria_id and coalesce(c.ativo, true)
                                                and (c.user_id is null or c.user_id = v_usuario)) then
        raise exception 'Categoria de Despesa nao encontrada' using errcode = 'P0001', hint = 'NAO_ENCONTRADA';
    end if;
    if v_atual is not distinct from p_categoria_id then  -- repeticao: ja esta la
        return jsonb_build_object('id', case when v_u.id is null then p_id else -v_u.id end, 'categoria_id', p_categoria_id, 'palavra', v_palavra,
                                  'origem', case when v_u.id is null then 'PADRAO' when v_u.tipo = 'NOVA' then 'PROPRIA' else 'REASSOCIADA' end,
                                  'alterada', false);
    end if;
    if v_origem is not null and p_categoria_id = v_origem then
        -- de volta a categoria padrao: o ajuste deixa de existir (restaura a regra do aplicativo)
        delete from financeiro.palavra_chave_usuario u where u.id = v_u.id;
        return jsonb_build_object('id', (select p.id from public.categoria_palavra_chave p
                                          where p.categoria_id = v_origem and p.ativo and lower(btrim(p.palavra)) = v_palavra order by p.id limit 1),
                                  'categoria_id', v_origem, 'palavra', v_palavra, 'origem', 'PADRAO', 'alterada', true, 'restaurada', true);
    end if;
    -- sem duas regras iguais na mesma categoria para o usuario
    if exists (select 1 from financeiro.palavras_efetivas(v_usuario) e where e.categoria_id = p_categoria_id and e.palavra = v_palavra) then
        raise exception 'Palavra-chave ja cadastrada para esta categoria' using errcode = '22023', hint = 'JA_EXISTE';
    end if;
    if v_u.id is null then
        insert into financeiro.palavra_chave_usuario (user_id, tipo, palavra, categoria_id, categoria_padrao_id)
        values (v_usuario, 'REASSOCIADA', v_palavra, p_categoria_id, v_origem)
        returning * into v_u;
    elsif v_u.tipo = 'NOVA' then
        update financeiro.palavra_chave_usuario u set categoria_id = p_categoria_id, atualizado_em = now() where u.id = v_u.id returning * into v_u;
    else  -- DESLIGADA ou REASSOCIADA: passa a valer na categoria escolhida
        update financeiro.palavra_chave_usuario u set tipo = 'REASSOCIADA', categoria_id = p_categoria_id, atualizado_em = now()
         where u.id = v_u.id returning * into v_u;
    end if;
    return jsonb_build_object('id', -v_u.id, 'categoria_id', v_u.categoria_id, 'categoria_padrao_id', v_u.categoria_padrao_id, 'palavra', v_palavra,
                              'origem', case when v_u.tipo = 'NOVA' then 'PROPRIA' else 'REASSOCIADA' end, 'alterada', true);
end
$$;
revoke execute on function financeiro.criar_minha_palavra_chave(integer, text) from public, anon;
revoke execute on function financeiro.desligar_palavra_chave_padrao(integer) from public, anon;
revoke execute on function financeiro.reassociar_palavra_chave_padrao(integer, integer) from public, anon;
revoke execute on function financeiro.remover_minha_palavra_chave(bigint) from public, anon;
revoke execute on function financeiro.restaurar_palavra_chave_padrao(integer) from public, anon;
grant execute on function financeiro.criar_minha_palavra_chave(integer, text) to authenticated;
revoke execute on function financeiro.alterar_categoria_da_palavra_chave(bigint, integer) from public, anon;
grant execute on function financeiro.alterar_categoria_da_palavra_chave(bigint, integer) to authenticated;
grant execute on function financeiro.desligar_palavra_chave_padrao(integer) to authenticated;
grant execute on function financeiro.reassociar_palavra_chave_padrao(integer, integer) to authenticated;
grant execute on function financeiro.remover_minha_palavra_chave(bigint) to authenticated;
grant execute on function financeiro.restaurar_palavra_chave_padrao(integer) to authenticated;

-- =====================================================================================================================
-- 4. Categorias de cartao: modelo do aplicativo, copiado para cada perfil
-- =====================================================================================================================
create table financeiro.categoria_cartao_padrao (
    id        integer     generated by default as identity primary key,
    nome      text        not null check (length(btrim(nome)) between 1 and 100),
    descricao text,
    cor       text        not null default '#6c757d' check (cor ~ '^#[0-9A-Fa-f]{6}$'),
    icone     text,
    ativo     boolean     not null default true,
    ordem     integer     not null default 0,
    criado_em timestamptz not null default now()
);
create unique index categoria_cartao_padrao_nome_uq on financeiro.categoria_cartao_padrao (lower(btrim(nome)));
-- Vinculo padrao: a categoria de despesa (padrao) que cada categoria de cartao recebe ao ser copiada.
create table financeiro.categoria_cartao_padrao_despesa (
    id           integer generated always as identity primary key,  -- a incorporacao de categorias reaponta as referencias pelo id da linha
    padrao_id    integer not null references financeiro.categoria_cartao_padrao (id) on delete cascade,
    categoria_id integer not null references public.categoria (id) on delete restrict,
    unique (padrao_id, categoria_id)
);
create trigger categoria_do_dono_categoria_id before insert or update on financeiro.categoria_cartao_padrao_despesa
    for each row execute function financeiro.conferir_categoria_do_dono('categoria_id', 'PADRAO');
alter table financeiro.categoria_cartao_padrao enable row level security;
alter table financeiro.categoria_cartao_padrao_despesa enable row level security;
revoke all on table financeiro.categoria_cartao_padrao from public, anon, authenticated;
revoke all on table financeiro.categoria_cartao_padrao_despesa from public, anon, authenticated;

alter table public.categoria_cartao add column padrao_id integer references financeiro.categoria_cartao_padrao (id) on delete restrict;
comment on column public.categoria_cartao.padrao_id is
    'FIN-CADASTROS-PADRAO-01: categoria copiada do modelo do aplicativo (nome e situacao protegidos). Nulo = adicional do perfil.';
create unique index categoria_cartao_padrao_por_perfil_uq on public.categoria_cartao (perfil_financeiro_id, padrao_id) where padrao_id is not null;

-- Copia o modelo para o perfil. So acrescenta, nunca duplica: categoria ja copiada e pulada; categoria do perfil com o
-- mesmo nome e ADOTADA (ganha a marca de origem, nada mais muda); vinculo que ja existe, ou categoria de despesa ja
-- vinculada a outra categoria de cartao ativa do perfil, e pulado. Repetir a chamada nao muda nada.
create function financeiro.inicializar_categorias_cartao(p_perfil_id integer)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    t        financeiro.categoria_cartao_padrao;
    v_id     integer;
    v_criou  integer := 0;
    v_adotou integer := 0;
    v_vinc   integer := 0;
    v_n      integer;
begin
    perform pg_advisory_xact_lock(20270101, p_perfil_id);
    if not exists (select 1 from public.perfil_financeiro p where p.id = p_perfil_id) then
        raise exception 'Perfil financeiro inexistente' using errcode = '22023';
    end if;
    for t in select * from financeiro.categoria_cartao_padrao where ativo order by ordem, id loop
        select cc.id into v_id from public.categoria_cartao cc where cc.perfil_financeiro_id = p_perfil_id and cc.padrao_id = t.id;
        if v_id is null then
            select cc.id into v_id from public.categoria_cartao cc
             where cc.perfil_financeiro_id = p_perfil_id and cc.padrao_id is null and lower(btrim(cc.nome)) = lower(btrim(t.nome));
            if v_id is not null then
                update public.categoria_cartao set padrao_id = t.id where id = v_id;
                v_adotou := v_adotou + 1;
            else
                insert into public.categoria_cartao (perfil_financeiro_id, nome, descricao, cor, icone, ativo, padrao_id, created_at, updated_at)
                values (p_perfil_id, t.nome, t.descricao, t.cor, t.icone, true, t.id, now() at time zone 'utc', now() at time zone 'utc')
                returning id into v_id;
                v_criou := v_criou + 1;
            end if;
        end if;
        insert into public.categoria_cartao_despesa (perfil_financeiro_id, categoria_cartao_id, categoria_id, ativo, created_at, updated_at)
        select p_perfil_id, v_id, d.categoria_id, true, now() at time zone 'utc', now() at time zone 'utc'
          from financeiro.categoria_cartao_padrao_despesa d
         where d.padrao_id = t.id
           and not exists (select 1 from public.categoria_cartao_despesa v
                            where v.perfil_financeiro_id = p_perfil_id and v.categoria_id = d.categoria_id
                              and (v.categoria_cartao_id = v_id or v.ativo));
        get diagnostics v_n = row_count;
        v_vinc := v_vinc + v_n;
    end loop;
    return jsonb_build_object('perfil_id', p_perfil_id, 'criadas', v_criou, 'adotadas', v_adotou, 'vinculos', v_vinc);
end
$$;
revoke execute on function financeiro.inicializar_categorias_cartao(integer) from public, anon, authenticated;

-- Para o dono de um perfil que ja existia: recebe as categorias de cartao padrao que ainda nao tem.
create function financeiro.inicializar_categorias_cartao_do_perfil(p_perfil_id integer)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
begin
    perform financeiro.exigir_escrita_categoria_cartao(p_perfil_id);
    return financeiro.inicializar_categorias_cartao(p_perfil_id);
end
$$;
revoke execute on function financeiro.inicializar_categorias_cartao_do_perfil(integer) from public, anon;
grant execute on function financeiro.inicializar_categorias_cartao_do_perfil(integer) to authenticated;

-- Administracao do modelo (so o administrador da plataforma).
create function financeiro.categorias_cartao_padrao_tela()
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
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
$$;

-- p_dados: id (edicao) ou sem id (criacao); nome, descricao, cor, icone, ativo, ordem, despesas [ids de categorias padrao].
-- Renomear o modelo NAO renomeia as copias ja feitas (cada perfil guarda a sua); desativar o modelo so deixa de copiar.
create function financeiro.manter_categoria_cartao_padrao(p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
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
$$;

-- Leva o modelo atual a TODOS os perfis (so acrescenta o que falta em cada um).
create function financeiro.propagar_categorias_cartao_padrao()
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
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
$$;
revoke execute on function financeiro.categorias_cartao_padrao_tela() from public, anon;
revoke execute on function financeiro.manter_categoria_cartao_padrao(jsonb) from public, anon;
revoke execute on function financeiro.propagar_categorias_cartao_padrao() from public, anon;
grant execute on function financeiro.categorias_cartao_padrao_tela() to authenticated;
grant execute on function financeiro.manter_categoria_cartao_padrao(jsonb) to authenticated;
grant execute on function financeiro.propagar_categorias_cartao_padrao() to authenticated;

-- Tela: as categorias de cartao do perfil, com a marca de padrao (texto de 20261119090000 + a marca).
create or replace function financeiro.categorias_cartao_tela(p_perfil_id integer, p_ativo boolean)
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
    return coalesce((
        select jsonb_agg(financeiro.categoria_cartao_flask(cc) || jsonb_build_object('padrao', cc.padrao_id is not null) order by cc.nome, cc.id)
          from public.categoria_cartao cc
         where financeiro.pertence_ao_perfil(cc.perfil_financeiro_id, p_perfil_id)
           and (p_ativo is null or coalesce(cc.ativo, false) = p_ativo)), '[]'::jsonb);
end
$$;

