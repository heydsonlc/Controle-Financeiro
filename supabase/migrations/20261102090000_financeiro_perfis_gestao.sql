-- FIN-MIGRACAO-FIDELIDADE-FASE-1 — gestao de perfis financeiros pelo novo aplicativo (Configuracoes).
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica. Validada em cluster PostgreSQL local
-- descartavel (tests/test_supabase_perfis_gestao.py).
--
-- Sem tabela nova: `public.perfil_financeiro` (Flask) continua sendo a unica fonte de perfis e
-- `financeiro.perfil_acesso` a unica autorizacao. Regras do Flask preservadas
-- (backend/services/perfil_financeiro_service.py):
-- - nome obrigatorio e unico; tipo PESSOAL/EMPRESA/OUTRO (outro valor vira OUTRO); apelido (avatar)
--   derivado do nome quando vazio; cor padrao #2563eb; documento ate 32 e logo ate 255 caracteres;
-- - nao inativar o unico perfil ativo; ao inativar o padrao, outro perfil ativo vira padrao;
-- - ao reativar sem nenhum padrao ativo, o reativado vira padrao; um unico padrao.
-- Adaptacoes ao uso por varios usuarios (o Flask e de um usuario so):
-- - so quem tem gestao explicita do perfil (perfil_acesso.pode_gerir) altera; LEITOR so le;
-- - quem cria um perfil recebe o vinculo TITULAR com gestao SO desse perfil novo (nunca de um
--   existente);
-- - FIN-MIGRACAO-FIDELIDADE-FASE-1-REAL: o perfil criado pelo novo aplicativo ja nasce com o gerador de
--   recorrencias NOVO (escritor unico, FIN-RECORRENCIA-T1), na MESMA transacao da criacao e pela funcao
--   de administrador definir_gerador_recorrencia (auditada). Se a atribuicao falhar, o perfil nao e
--   criado. Perfis existentes nao sao alterados (o gerador deles continua como esta);
-- - "padrao" e uma coluna unica do Flask: so muda quando o usuario gere tambem o padrao atual
--   (nunca altera perfil de outro titular); "unico perfil ativo" conta os perfis do proprio usuario;
-- - "perfil em uso" e escolha do navegador: a regra "selecione outro antes de inativar o perfil
--   ativo" fica na tela.
-- Defeitos do Flask corrigidos (nao perpetuar):
-- - registros sem perfil (perfil_financeiro_id NULL) pertencem ao perfil de NOME "Pessoal"
--   (condicao_perfil). Renomear o "Pessoal", ou dar esse nome a outro perfil, mudaria quem ve
--   esses registros: o nome "Pessoal" fica reservado e o perfil "Pessoal" nao e renomeado;
-- - cor so em hexadecimal #RRGGBB (o Flask aceitava qualquer texto de 7 caracteres com #).

-- Gestao independente de o perfil estar ativo (pode_gerir_perfil exige ativo; reativar nao poderia).
create function financeiro.gere_perfil(p_perfil_id integer)
    returns boolean
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select exists (
        select 1
          from financeiro.perfil_acesso a
         where a.user_id = (select auth.uid())
           and a.perfil_financeiro_id = p_perfil_id
           and a.pode_gerir
    )
$$;

create function financeiro.perfil_em_json(p_perfil_id integer)
    returns jsonb
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select jsonb_build_object('id', p.id, 'nome', p.nome, 'tipo', p.tipo, 'documento', p.documento,
                              'avatar', p.avatar, 'logo_url', p.logo_url, 'cor', p.cor,
                              'ativo', p.ativo, 'padrao', p.padrao)
      from public.perfil_financeiro p
     where p.id = p_perfil_id
$$;

-- Normaliza os campos editaveis como o Flask (_normalizar_tipo, _texto_opcional, _avatar, _cor).
-- So as chaves presentes em p_dados entram no resultado (atualizacao parcial, como o PUT do Flask).
create function financeiro.normalizar_dados_perfil(p_dados jsonb, p_nome_atual text)
    returns jsonb
    language plpgsql
    immutable
    set search_path = ''
as $$
declare
    v jsonb := '{}'::jsonb;
    v_nome text;
    v_texto text;
    v_partes text[];
begin
    if p_dados ? 'nome' then
        v_nome := btrim(coalesce(p_dados ->> 'nome', ''));
        if v_nome = '' then
            raise exception 'Nome do perfil financeiro e obrigatorio' using errcode = '22023';
        end if;
        if char_length(v_nome) > 120 then
            raise exception 'Nome do perfil financeiro deve ter ate 120 caracteres' using errcode = '22023';
        end if;
        v := v || jsonb_build_object('nome', v_nome);
    end if;
    if p_dados ? 'tipo' then
        v_texto := upper(btrim(coalesce(p_dados ->> 'tipo', '')));
        v := v || jsonb_build_object('tipo', case when v_texto in ('PESSOAL', 'EMPRESA', 'OUTRO') then v_texto else 'OUTRO' end);
    end if;
    if p_dados ? 'documento' then
        v := v || jsonb_build_object('documento', left(nullif(btrim(coalesce(p_dados ->> 'documento', '')), ''), 32));
    end if;
    if p_dados ? 'logo_url' then
        v := v || jsonb_build_object('logo_url', left(nullif(btrim(coalesce(p_dados ->> 'logo_url', '')), ''), 255));
    end if;
    if p_dados ? 'avatar' then
        v_texto := upper(btrim(coalesce(nullif(btrim(coalesce(p_dados ->> 'avatar', '')), ''),
                                        coalesce(v ->> 'nome', p_nome_atual), '')));
        v_partes := regexp_split_to_array(v_texto, '\s+');
        v := v || jsonb_build_object('avatar', case
            when v_texto = '' then 'PF'
            when array_length(v_partes, 1) >= 2 then left(left(v_partes[1], 1) || left(v_partes[2], 1), 3)
            else left(v_texto, 3) end);
    end if;
    if p_dados ? 'cor' then
        v_texto := btrim(coalesce(p_dados ->> 'cor', ''));
        if v_texto <> '' and left(v_texto, 1) <> '#' then
            v_texto := '#' || v_texto;
        end if;
        v := v || jsonb_build_object('cor', case when v_texto ~ '^#[0-9A-Fa-f]{6}$' then v_texto else '#2563eb' end);
    end if;
    return v;
end
$$;

-- Torna p_perfil_id o unico padrao. Exige gestao do perfil e do padrao atual (se houver outro).
create function financeiro.aplicar_perfil_padrao(p_perfil_id integer)
    returns void
    language plpgsql
    security definer
    set search_path = ''
as $$
begin
    if exists (select 1 from public.perfil_financeiro p
                where p.padrao and p.id <> p_perfil_id and not financeiro.gere_perfil(p.id)) then
        raise exception 'O perfil padrao atual e gerido por outro titular' using errcode = '42501';
    end if;
    update public.perfil_financeiro
       set padrao = false, updated_at = (now() at time zone 'utc')
     where padrao and id <> p_perfil_id;
    update public.perfil_financeiro
       set padrao = true, updated_at = (now() at time zone 'utc')
     where id = p_perfil_id and not padrao;
end
$$;

-- Lista da tela Configuracoes: todos os perfis vinculados ao usuario, inclusive inativos
-- (Flask listar_perfis_config: ativos primeiro, depois por nome). So leitura.
create function financeiro.perfis_para_configuracao()
    returns table (id integer, nome text, tipo text, documento text, avatar text, logo_url text, cor text,
                   ativo boolean, padrao boolean, papel text, pode_gerir boolean)
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select p.id, p.nome::text, p.tipo::text, p.documento::text, p.avatar::text, p.logo_url::text, p.cor::text,
           p.ativo, p.padrao, a.papel, a.pode_gerir
      from financeiro.perfil_acesso a
      join public.perfil_financeiro p on p.id = a.perfil_financeiro_id
     where a.user_id = (select auth.uid())
     order by p.ativo desc, p.nome
$$;

create function financeiro.criar_perfil(p_dados jsonb)
    returns jsonb
    language plpgsql
    security definer
    set search_path = ''
as $$
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
    -- Todas as chaves editaveis, com os padroes do Flask para as ausentes.
    v := financeiro.normalizar_dados_perfil(
        jsonb_build_object('nome', p_dados -> 'nome', 'tipo', p_dados -> 'tipo', 'documento', p_dados -> 'documento',
                           'logo_url', p_dados -> 'logo_url', 'avatar', p_dados -> 'avatar', 'cor', p_dados -> 'cor'),
        null);
    v_ativo := coalesce((p_dados ->> 'ativo')::boolean, true);

    perform pg_advisory_xact_lock(hashtext('financeiro.perfil_financeiro.gestao'));
    if v ->> 'nome' = 'Pessoal' then
        raise exception 'O nome Pessoal e reservado ao perfil que guarda os registros sem perfil' using errcode = '22023';
    end if;
    if exists (select 1 from public.perfil_financeiro p where p.nome = v ->> 'nome') then
        raise exception 'Ja existe perfil financeiro com este nome' using errcode = '23505';
    end if;

    insert into public.perfil_financeiro (nome, tipo, documento, avatar, logo_url, cor, ativo, padrao, created_at, updated_at)
    values (v ->> 'nome', v ->> 'tipo', v ->> 'documento', v ->> 'avatar', v ->> 'logo_url', v ->> 'cor', v_ativo, false,
            (now() at time zone 'utc'), (now() at time zone 'utc'))
    returning id into v_id;
    insert into financeiro.perfil_acesso (user_id, perfil_financeiro_id, papel, pode_gerir)
    values (v_usuario, v_id, 'TITULAR', true);
    -- Escritor unico: o perfil novo e do novo aplicativo desde a criacao (nunca existe sem atribuicao).
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
$$;

-- Nome, tipo, documento, apelido, logo e cor (so as chaves enviadas). Ativo e padrao tem funcoes proprias.
create function financeiro.atualizar_perfil(p_perfil_id integer, p_dados jsonb)
    returns jsonb
    language plpgsql
    security definer
    set search_path = ''
as $$
declare
    v_perfil public.perfil_financeiro%rowtype;
    v jsonb;
begin
    if not financeiro.gere_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' then
        raise exception 'Dados do perfil invalidos' using errcode = '22023';
    end if;
    perform pg_advisory_xact_lock(hashtext('financeiro.perfil_financeiro.gestao'));
    select * into v_perfil from public.perfil_financeiro p where p.id = p_perfil_id for update;
    v := financeiro.normalizar_dados_perfil(p_dados - 'ativo' - 'padrao' - 'id', v_perfil.nome);

    if v ? 'nome' and v ->> 'nome' <> v_perfil.nome then
        if v_perfil.nome = 'Pessoal' then
            raise exception 'O perfil Pessoal nao pode ser renomeado: ele guarda os registros sem perfil' using errcode = '22023';
        end if;
        if v ->> 'nome' = 'Pessoal' then
            raise exception 'O nome Pessoal e reservado ao perfil que guarda os registros sem perfil' using errcode = '22023';
        end if;
        if exists (select 1 from public.perfil_financeiro p where p.nome = v ->> 'nome' and p.id <> p_perfil_id) then
            raise exception 'Ja existe perfil financeiro com este nome' using errcode = '23505';
        end if;
    end if;

    update public.perfil_financeiro p
       set nome = coalesce(v ->> 'nome', p.nome),
           tipo = coalesce(v ->> 'tipo', p.tipo),
           documento = case when v ? 'documento' then v ->> 'documento' else p.documento end,
           logo_url = case when v ? 'logo_url' then v ->> 'logo_url' else p.logo_url end,
           avatar = coalesce(v ->> 'avatar', p.avatar),
           cor = coalesce(v ->> 'cor', p.cor),
           updated_at = (now() at time zone 'utc')
     where p.id = p_perfil_id;
    return financeiro.perfil_em_json(p_perfil_id);
exception
    when unique_violation then
        raise exception 'Ja existe perfil financeiro com este nome' using errcode = '23505';
end
$$;

create function financeiro.inativar_perfil(p_perfil_id integer)
    returns jsonb
    language plpgsql
    security definer
    set search_path = ''
as $$
declare
    v_perfil public.perfil_financeiro%rowtype;
    v_novo_padrao integer;
begin
    if not financeiro.gere_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    perform pg_advisory_xact_lock(hashtext('financeiro.perfil_financeiro.gestao'));
    select * into v_perfil from public.perfil_financeiro p where p.id = p_perfil_id for update;
    if not v_perfil.ativo then
        return financeiro.perfil_em_json(p_perfil_id);
    end if;
    if (select count(*) from financeiro.perfil_acesso a
          join public.perfil_financeiro p on p.id = a.perfil_financeiro_id
         where a.user_id = (select auth.uid()) and p.ativo) <= 1 then
        raise exception 'Nao e possivel inativar o unico perfil ativo' using errcode = '22023';
    end if;
    if v_perfil.padrao then
        select p.id into v_novo_padrao
          from public.perfil_financeiro p
         where p.ativo and p.id <> p_perfil_id and financeiro.gere_perfil(p.id)
         order by p.id
         limit 1;
        if v_novo_padrao is null then
            raise exception 'Defina outro perfil padrao antes de inativar este' using errcode = '22023';
        end if;
    end if;

    update public.perfil_financeiro
       set ativo = false, padrao = false, updated_at = (now() at time zone 'utc')
     where id = p_perfil_id;
    if v_novo_padrao is not null then
        perform financeiro.aplicar_perfil_padrao(v_novo_padrao);
    end if;
    return financeiro.perfil_em_json(p_perfil_id);
end
$$;

create function financeiro.reativar_perfil(p_perfil_id integer)
    returns jsonb
    language plpgsql
    security definer
    set search_path = ''
as $$
begin
    if not financeiro.gere_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    perform pg_advisory_xact_lock(hashtext('financeiro.perfil_financeiro.gestao'));
    update public.perfil_financeiro
       set ativo = true, updated_at = (now() at time zone 'utc')
     where id = p_perfil_id and not ativo;
    if not exists (select 1 from public.perfil_financeiro p where p.padrao and p.ativo) then
        perform financeiro.aplicar_perfil_padrao(p_perfil_id);
    end if;
    return financeiro.perfil_em_json(p_perfil_id);
end
$$;

create function financeiro.definir_perfil_padrao(p_perfil_id integer)
    returns jsonb
    language plpgsql
    security definer
    set search_path = ''
as $$
begin
    if not financeiro.gere_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    perform pg_advisory_xact_lock(hashtext('financeiro.perfil_financeiro.gestao'));
    perform 1 from public.perfil_financeiro p where p.id = p_perfil_id and p.ativo for update;
    if not found then
        raise exception 'Perfil financeiro ativo nao encontrado' using errcode = '22023';
    end if;
    perform financeiro.aplicar_perfil_padrao(p_perfil_id);
    return financeiro.perfil_em_json(p_perfil_id);
end
$$;

-- Funcoes nascem com EXECUTE para PUBLIC. Internas: so as funcoes acima as chamam.
revoke execute on function financeiro.gere_perfil(integer) from public, anon, authenticated;
revoke execute on function financeiro.perfil_em_json(integer) from public, anon, authenticated;
revoke execute on function financeiro.normalizar_dados_perfil(jsonb, text) from public, anon, authenticated;
revoke execute on function financeiro.aplicar_perfil_padrao(integer) from public, anon, authenticated;
revoke execute on function financeiro.perfis_para_configuracao() from public, anon;
revoke execute on function financeiro.criar_perfil(jsonb) from public, anon;
revoke execute on function financeiro.atualizar_perfil(integer, jsonb) from public, anon;
revoke execute on function financeiro.inativar_perfil(integer) from public, anon;
revoke execute on function financeiro.reativar_perfil(integer) from public, anon;
revoke execute on function financeiro.definir_perfil_padrao(integer) from public, anon;
grant execute on function financeiro.perfis_para_configuracao() to authenticated;
grant execute on function financeiro.criar_perfil(jsonb) to authenticated;
grant execute on function financeiro.atualizar_perfil(integer, jsonb) to authenticated;
grant execute on function financeiro.inativar_perfil(integer) to authenticated;
grant execute on function financeiro.reativar_perfil(integer) to authenticated;
grant execute on function financeiro.definir_perfil_padrao(integer) to authenticated;
