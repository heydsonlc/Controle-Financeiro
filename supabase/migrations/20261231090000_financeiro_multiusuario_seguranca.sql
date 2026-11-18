-- FIN-MULTIUSUARIO-SEGURANCA-01 — propriedade dos perfis, isolamento entre usuarios e referencias globais protegidas.
--
-- GERADA por scripts/gerar_migration_multiusuario_seguranca.py: nao editar a mao.
--
-- O que muda (nenhum registro financeiro e alterado por esta migration):
--   1. Cada perfil financeiro passa a ter DONO (public.perfil_financeiro.user_id -> auth.users). Preenchido pelo titular
--      que ja administra o perfil. Quem administra um perfil e sempre o dono dele.
--   2. Nome de perfil unico POR DONO (sem diferenca de maiusculas ou de espacos), nao mais no aplicativo inteiro.
--      "Pessoal" deixa de ser nome reservado.
--   3. Perfil padrao POR USUARIO: no maximo um por dono.
--   4. Registros antigos sem perfil: a posse deixa de ser decidida pelo NOME do perfil. Passa a existir uma guarda
--      explicita (financeiro.guarda_sem_perfil), que aponta o perfil que os guarda. Nesta migration ela recebe o perfil
--      que hoje cumpre esse papel (o unico chamado "Pessoal", se houver exatamente um): o comportamento nao muda.
--      Depois de regularizados os registros (scripts/regularizar_itens_sem_perfil.py), a guarda pode ser retirada.
--   5. Indices de TR: leitura para quem usa o aplicativo; manutencao so do administrador da plataforma
--      (financeiro.administrador_plataforma), que NAO ganha, por isso, acesso a dados financeiros de ninguem.
--   6. Tres funcoes passam a conferir a autorizacao antes de validar os dados.
-- A autorizacao continua em financeiro.perfil_acesso (leitura) e passa a exigir tambem a posse para administrar.

-- =====================================================================================================================
-- 1. Dono do perfil
-- =====================================================================================================================
alter table public.perfil_financeiro add column user_id uuid references auth.users (id) on delete restrict;
comment on column public.perfil_financeiro.user_id is
    'FIN-MULTIUSUARIO-SEGURANCA-01: dono do perfil (usuario do Supabase Auth). Nunca derivado de nome ou e-mail.';

do $$
begin
    if exists (select 1 from financeiro.perfil_acesso a where a.pode_gerir group by a.perfil_financeiro_id having count(*) > 1) then
        raise exception 'Ha perfil administrado por mais de um usuario: defina o dono antes de aplicar esta migration.';
    end if;
end
$$;
update public.perfil_financeiro p
   set user_id = a.user_id
  from financeiro.perfil_acesso a
 where a.perfil_financeiro_id = p.id and a.pode_gerir;
create index perfil_financeiro_dono_idx on public.perfil_financeiro (user_id);

-- Nome comparavel: sem espacos nas pontas, espacos internos unificados, sem diferenca de maiusculas.
create function financeiro.nome_de_perfil_normalizado(p_nome text)
    returns text
    language sql
    immutable
    set search_path = ''
as $$
    select lower(regexp_replace(btrim(coalesce(p_nome, '')), '\s+', ' ', 'g'))
$$;
revoke execute on function financeiro.nome_de_perfil_normalizado(text) from public, anon, authenticated;

do $$
declare
    r record;
begin
    -- a unicidade global do nome (restricao ou indice herdado do Flask), qualquer que seja o nome dela
    for r in select c.conname from pg_constraint c
              where c.conrelid = 'public.perfil_financeiro'::regclass and c.contype = 'u'
                and (select array_agg(a.attname::text) from pg_attribute a where a.attrelid = c.conrelid and a.attnum = any(c.conkey)) = array['nome'] loop
        execute format('alter table public.perfil_financeiro drop constraint %I', r.conname);
    end loop;
    for r in select i.indexrelid::regclass::text nome from pg_index i
              where i.indrelid = 'public.perfil_financeiro'::regclass and i.indisunique and not i.indisprimary and i.indnatts = 1
                and (select a.attname from pg_attribute a where a.attrelid = i.indrelid and a.attnum = i.indkey[0]) = 'nome' loop
        execute format('drop index %s', r.nome);
    end loop;
end
$$;
create unique index perfil_financeiro_dono_nome_uq
    on public.perfil_financeiro (user_id, financeiro.nome_de_perfil_normalizado(nome)) where user_id is not null;
create unique index perfil_financeiro_padrao_por_dono_uq
    on public.perfil_financeiro (user_id) where padrao and user_id is not null;

-- O dono nao muda depois de definido (transferencia de perfil nao existe).
create function financeiro.proteger_dono_do_perfil()
    returns trigger
    language plpgsql
    set search_path = ''
as $$
begin
    if old.user_id is not null and new.user_id is distinct from old.user_id then
        raise exception 'O dono do perfil financeiro nao pode ser alterado' using errcode = '42501';
    end if;
    return new;
end
$$;
revoke execute on function financeiro.proteger_dono_do_perfil() from public, anon, authenticated;
create trigger perfil_financeiro_dono_fixo before update of user_id on public.perfil_financeiro
    for each row execute function financeiro.proteger_dono_do_perfil();

-- Quem administra o perfil e o dono: o primeiro vinculo de administracao define o dono de um perfil que ainda nao o
-- tem (cargas e cenarios que gravam o perfil e depois o vinculo); um segundo administrador e recusado.
create function financeiro.conferir_dono_no_vinculo()
    returns trigger
    language plpgsql
    security definer
    set search_path = ''
as $$
declare
    v_dono uuid;
begin
    if not new.pode_gerir then
        return new;
    end if;
    select p.user_id into v_dono from public.perfil_financeiro p where p.id = new.perfil_financeiro_id for update;
    if v_dono is null then
        update public.perfil_financeiro set user_id = new.user_id where id = new.perfil_financeiro_id;
    elsif v_dono <> new.user_id then
        raise exception 'Somente o dono do perfil financeiro pode administra-lo' using errcode = '42501';
    end if;
    return new;
end
$$;
revoke execute on function financeiro.conferir_dono_no_vinculo() from public, anon, authenticated;
create trigger perfil_acesso_dono before insert or update of pode_gerir, user_id, perfil_financeiro_id on financeiro.perfil_acesso
    for each row execute function financeiro.conferir_dono_no_vinculo();

-- Administrar = ter o vinculo de administracao E ser o dono (texto de 20261020/20261124 + a posse).
create or replace function financeiro.pode_gerir_perfil(p_perfil_id integer)
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
           and p.user_id = a.user_id
    )
$$;

create or replace function financeiro.gere_perfil(p_perfil_id integer)
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
           and a.pode_gerir
           and p.user_id = a.user_id
    )
$$;

-- =====================================================================================================================
-- 2. Registros sem perfil: guarda explicita no lugar do nome "Pessoal"
-- =====================================================================================================================
create table financeiro.guarda_sem_perfil (
    id                   boolean     primary key default true check (id),
    perfil_financeiro_id integer     references public.perfil_financeiro (id) on delete restrict,
    definido_em          timestamptz not null default now(),
    definido_por         text        not null,
    motivo               text        not null
);
alter table financeiro.guarda_sem_perfil enable row level security;
revoke all on table financeiro.guarda_sem_perfil from public, anon, authenticated;
comment on table financeiro.guarda_sem_perfil is
    'FIN-MULTIUSUARIO-SEGURANCA-01: o unico perfil que guarda os registros antigos sem perfil (ou nenhum). Linha unica.';

insert into financeiro.guarda_sem_perfil (perfil_financeiro_id, definido_por, motivo)
select (select min(p.id) from public.perfil_financeiro p where p.nome = 'Pessoal' having count(*) = 1),
       'migration 20261231090000', 'Perfil que cumpria esse papel pela regra anterior (nome Pessoal), transcrito uma unica vez';

create function financeiro.perfil_guarda_legado()
    returns integer
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select g.perfil_financeiro_id from financeiro.guarda_sem_perfil g
$$;

create function financeiro.guarda_legado(p_perfil_id integer)
    returns boolean
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select coalesce(p_perfil_id = (select g.perfil_financeiro_id from financeiro.guarda_sem_perfil g), false)
$$;

-- Administrativa (dono do banco): troca ou retira (nulo) a guarda. Nao executavel por usuarios.
create function financeiro.definir_guarda_sem_perfil(p_perfil_id integer, p_por text, p_motivo text)
    returns integer
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
begin
    if btrim(coalesce(p_por, '')) = '' or btrim(coalesce(p_motivo, '')) = '' then
        raise exception 'Informe quem define e o motivo' using errcode = '22023';
    end if;
    if p_perfil_id is not null and not exists (select 1 from public.perfil_financeiro p where p.id = p_perfil_id) then
        raise exception 'Perfil financeiro inexistente' using errcode = '22023';
    end if;
    insert into financeiro.guarda_sem_perfil (id, perfil_financeiro_id, definido_por, motivo)
    values (true, p_perfil_id, btrim(p_por), btrim(p_motivo))
    on conflict (id) do update set perfil_financeiro_id = excluded.perfil_financeiro_id, definido_em = now(),
                                   definido_por = excluded.definido_por, motivo = excluded.motivo;
    return p_perfil_id;
end
$$;
revoke execute on function financeiro.perfil_guarda_legado() from public, anon, authenticated;
revoke execute on function financeiro.guarda_legado(integer) from public, anon, authenticated;
revoke execute on function financeiro.definir_guarda_sem_perfil(integer, text, text) from public, anon, authenticated;

create or replace function financeiro.pertence_ao_perfil(p_registro_perfil integer, p_perfil_id integer)
    returns boolean
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select p_registro_perfil = p_perfil_id
        or (p_registro_perfil is null and financeiro.guarda_legado(p_perfil_id))
$$;

-- Regularizacao dos registros sem perfil (scripts/regularizar_itens_sem_perfil.py): o que foi atribuido, para desfazer.
create table financeiro.regularizacao_perfil (
    chave          uuid        primary key,
    executada_em   timestamptz not null default now(),
    executada_por  text        not null,
    impressao      text        not null,
    perfil_destino integer     not null references public.perfil_financeiro (id) on delete restrict,
    registros      jsonb       not null,
    revertida_em   timestamptz
);
alter table financeiro.regularizacao_perfil enable row level security;
revoke all on table financeiro.regularizacao_perfil from public, anon, authenticated;

-- =====================================================================================================================
-- 3. Perfis: criacao, edicao e perfil padrao por dono
-- =====================================================================================================================
create or replace function financeiro.criar_perfil(p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
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
$$;

create or replace function financeiro.atualizar_perfil(p_perfil_id integer, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_perfil public.perfil_financeiro%rowtype;
    v jsonb;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id, true);
    if not financeiro.gere_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' then
        raise exception 'Dados do perfil invalidos' using errcode = '22023';
    end if;
    select * into v_perfil from public.perfil_financeiro p where p.id = p_perfil_id for update;
    perform pg_advisory_xact_lock(hashtextextended('financeiro.perfil_financeiro.gestao:' || v_perfil.user_id::text, 20261231));
    v := financeiro.normalizar_dados_perfil(p_dados - 'ativo' - 'padrao' - 'id', v_perfil.nome);

    if v ? 'nome' and v ->> 'nome' <> v_perfil.nome
       and exists (select 1 from public.perfil_financeiro p
                    where p.user_id = v_perfil.user_id and p.id <> p_perfil_id
                      and financeiro.nome_de_perfil_normalizado(p.nome) = financeiro.nome_de_perfil_normalizado(v ->> 'nome')) then
        raise exception 'Ja existe perfil financeiro com este nome' using errcode = '23505';
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

-- O padrao e do dono: escolher um perfil como padrao so desmarca os outros perfis DO MESMO DONO.
create or replace function financeiro.aplicar_perfil_padrao(p_perfil_id integer)
    returns void
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_dono uuid;
begin
    select p.user_id into v_dono from public.perfil_financeiro p where p.id = p_perfil_id for update;
    if v_dono is null then
        raise exception 'Perfil financeiro sem dono definido' using errcode = '42501';
    end if;
    update public.perfil_financeiro
       set padrao = false, updated_at = (now() at time zone 'utc')
     where padrao and id <> p_perfil_id and user_id = v_dono;
    update public.perfil_financeiro
       set padrao = true, updated_at = (now() at time zone 'utc')
     where id = p_perfil_id and not padrao;
end
$$;

create or replace function financeiro.definir_perfil_padrao(p_perfil_id integer)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
begin
    if not financeiro.gere_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    perform 1 from public.perfil_financeiro p where p.id = p_perfil_id and p.ativo for update;
    if not found then
        raise exception 'Perfil financeiro ativo nao encontrado' using errcode = '22023';
    end if;
    perform financeiro.aplicar_perfil_padrao(p_perfil_id);
    return financeiro.perfil_em_json(p_perfil_id);
end
$$;

create or replace function financeiro.reativar_perfil(p_perfil_id integer)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id, true);
    if not financeiro.gere_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    update public.perfil_financeiro
       set ativo = true, updated_at = (now() at time zone 'utc')
     where id = p_perfil_id and not ativo;
    -- sem padrao ativo ENTRE OS PERFIS DO DONO: este passa a ser
    if not exists (select 1 from public.perfil_financeiro p
                    where p.padrao and p.ativo
                      and p.user_id = (select q.user_id from public.perfil_financeiro q where q.id = p_perfil_id)) then
        perform financeiro.aplicar_perfil_padrao(p_perfil_id);
    end if;
    return financeiro.perfil_em_json(p_perfil_id);
end
$$;

-- Consorcio antigo sem perfil: o perfil que guarda os registros sem perfil (nao mais "o padrao" nem "o Pessoal").
create or replace function financeiro.perfil_do_consorcio(p_c public.contrato_consorcio)
    returns integer
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select coalesce((p_c).perfil_financeiro_id, financeiro.perfil_guarda_legado())
$$;

-- =====================================================================================================================
-- 4. Administrador da plataforma e indices de TR
-- =====================================================================================================================
create table financeiro.administrador_plataforma (
    user_id       uuid        primary key references auth.users (id) on delete cascade,
    concedido_em  timestamptz not null default now(),
    concedido_por text        not null,
    motivo        text        not null
);
alter table financeiro.administrador_plataforma enable row level security;
revoke all on table financeiro.administrador_plataforma from public, anon, authenticated;
comment on table financeiro.administrador_plataforma is
    'FIN-MULTIUSUARIO-SEGURANCA-01: quem mantem as referencias globais (indices de TR). Nao da acesso a dado financeiro de usuario.';

-- Quem ja administrava o catalogo compartilhado e o administrador inicial.
insert into financeiro.administrador_plataforma (user_id, concedido_por, motivo)
select g.user_id, 'migration 20261231090000', 'Conta que ja administrava o catalogo de categorias'
  from financeiro.gestor_catalogo g;

create function financeiro.definir_administrador_plataforma(p_user_id uuid, p_ativo boolean, p_por text, p_motivo text)
    returns boolean
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
begin
    if p_user_id is null or btrim(coalesce(p_por, '')) = '' or btrim(coalesce(p_motivo, '')) = '' then
        raise exception 'Informe o usuario, quem concede e o motivo' using errcode = '22023';
    end if;
    if p_ativo then
        insert into financeiro.administrador_plataforma (user_id, concedido_por, motivo)
        values (p_user_id, btrim(p_por), btrim(p_motivo))
        on conflict (user_id) do nothing;
    else
        delete from financeiro.administrador_plataforma where user_id = p_user_id;
    end if;
    return p_ativo;
end
$$;
revoke execute on function financeiro.definir_administrador_plataforma(uuid, boolean, text, text) from public, anon, authenticated;

-- Para a tela: mostrar ou nao as acoes de manutencao (o banco recusa de qualquer forma).
create function financeiro.sou_administrador_plataforma()
    returns boolean
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select exists (select 1 from financeiro.administrador_plataforma a where a.user_id = (select auth.uid()))
$$;
revoke execute on function financeiro.sou_administrador_plataforma() from public, anon;
grant execute on function financeiro.sou_administrador_plataforma() to authenticated;

-- Leitura: quem usa o aplicativo (algum perfil). Gravacao: so o administrador da plataforma (texto de 20261122 + a regra).
create or replace function financeiro.idx_exigir_acesso(p_gravar boolean)
    returns void
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
begin
    if (select auth.uid()) is null then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if p_gravar then
        if not exists (select 1 from financeiro.administrador_plataforma a where a.user_id = (select auth.uid())) then
            raise exception 'A manutencao dos indices oficiais e restrita ao administrador da plataforma. Nada foi gravado.'
                using errcode = '42501', hint = 'SO_ADMINISTRADOR';
        end if;
        return;
    end if;
    if not exists (select 1 from financeiro.perfil_acesso a join public.perfil_financeiro p on p.id = a.perfil_financeiro_id
                    where a.user_id = (select auth.uid())) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
end
$$;

-- =====================================================================================================================
-- 5. Cadastro com pagamento imediato: autorizacao antes da validacao (texto de 20261230090000 + a primeira conferencia)
-- =====================================================================================================================
CREATE OR REPLACE FUNCTION financeiro.criar_despesa_paga(p_perfil_id integer, p_dados jsonb, p_pagamento jsonb, p_chave uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_criada  jsonb;
    v_paga    jsonb;
    v_chave   uuid;
    v_valor   numeric;
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then  -- antes de qualquer validacao dos dados
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if p_chave is null then
        raise exception 'Chave da operacao obrigatoria' using errcode = '22023';
    end if;
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' then
        raise exception 'Dados da despesa invalidos' using errcode = '22023';
    end if;
    if coalesce(p_dados ->> 'recorrente', 'false') not in ('false', 'f') then
        raise exception 'Pagamento no cadastro: so para despesa direta (as ocorrencias da recorrencia sao pagas uma a uma)'
            using errcode = '22023';
    end if;
    if p_pagamento is null or jsonb_typeof(p_pagamento) <> 'object' then
        raise exception 'Dados do pagamento invalidos' using errcode = '22023';
    end if;
    if nullif(btrim(coalesce(p_pagamento ->> 'conta_bancaria_id', '')), '') is null then
        raise exception 'Informe a conta bancaria do pagamento' using errcode = '22023';
    end if;
    if nullif(btrim(coalesce(p_pagamento ->> 'data_pagamento', '')), '') is null then
        raise exception 'Informe a data do pagamento' using errcode = '22023';
    end if;
    v_chave := extensions.uuid_generate_v5(p_chave, 'pagar');

    -- 1. Cadastro oficial (permissao, escritor, validacoes, competencia e idempotencia sao os dele).
    v_criada := financeiro.criar_despesa(p_perfil_id, p_dados, p_chave);
    if coalesce((v_criada ->> 'repetida')::boolean, false)
       and not exists (select 1 from financeiro.operacao_despesa o where o.chave = v_chave and o.operacao = 'pagar_despesa') then
        -- a chave ja foi usada por um cadastro SEM pagamento: nao se paga uma despesa que esta chamada nao criou
        raise exception 'Chave da operacao ja usada' using errcode = '22023';
    end if;
    if (v_criada ->> 'conta_id') is null then
        raise exception 'Pagamento no cadastro: so para despesa direta' using errcode = '22023';
    end if;

    -- 2. Pagamento oficial, integral, pelo valor que acabou de ser gravado (sem ajuste, juros ou desconto).
    select c.valor into v_valor from public.conta c where c.id = (v_criada ->> 'conta_id')::integer;
    v_paga := financeiro.pagar_despesa(p_perfil_id, (v_criada ->> 'conta_id')::integer,
        jsonb_build_object('conta_bancaria_id', p_pagamento -> 'conta_bancaria_id', 'data_pagamento', p_pagamento -> 'data_pagamento',
                           'valor_pago', v_valor, 'valor_devido', v_valor),
        v_chave);
    return (v_criada - 'repetida') || jsonb_build_object('paga', true, 'pagamento', v_paga - 'repetida',
                                                         'repetida', coalesce((v_criada ->> 'repetida')::boolean, false));
end
$function$;

-- =====================================================================================================================
-- 6. Funcoes que decidiam a posse pelo nome do perfil: agora pela guarda explicita (nenhuma regra financeira muda)
-- =====================================================================================================================
-- compras_da_fatura: texto de 20261230090000 (definicao vigente) com a posse dos registros sem perfil pela guarda explicita (1 trecho(s)).
CREATE OR REPLACE FUNCTION financeiro.compras_da_fatura(p_perfil_id integer, p_cartao_id integer, p_mes date)
 RETURNS TABLE(id integer, descricao text, valor numeric, data_compra date, numero_parcela integer, total_parcelas integer, categoria_nome text, recorrente boolean, bloqueio text, pode_editar boolean, categoria_cartao_id integer, valor_previsto numeric, natureza text, situacao_ocorrencia text, valor_executado numeric)
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_pessoal boolean;
    v_gerir   boolean;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    perform financeiro.cartao_do_perfil(p_perfil_id, p_cartao_id, false);
    v_pessoal := financeiro.guarda_legado(p_perfil_id);
    v_gerir := financeiro.pode_gerir_perfil(p_perfil_id);
    return query
        select l.id, coalesce(nullif(l.descricao_exibida, ''), l.descricao)::text, l.valor, l.data_compra,
               l.numero_parcela, l.total_parcelas, cat.nome::text, coalesce(l.is_recorrente, false),
               financeiro.bloqueio_da_parcela(l.id), v_gerir and financeiro.bloqueio_da_parcela(l.id) is null,
               l.categoria_cartao_id,
               -- FIN-CARTAO-DESPESAS-FIXAS-01: previsto da ocorrencia (o valor antes da cobranca real; sem cobranca, o proprio valor)
               case when nat.n = 'FIXA' then coalesce(o.valor_previsto, l.valor) when nat.n = 'PARCELADA' then l.valor end,
               nat.n,
               sit.s,  -- FIN-CARTAO-PREVISTO-EXECUTADO-01
               financeiro.valor_executado_compra(l.valor, sit.s)
          from public.lancamento_agregado l
          left join public.categoria cat on cat.id = l.categoria_id
          left join financeiro.ocorrencia_recorrencia_cartao o on o.lancamento_id = l.id and o.revertida_em is null
         cross join lateral (select financeiro.natureza_da_compra(l.total_parcelas, l.is_recorrente, l.item_despesa_id, l.categoria_cartao_id) as n) nat
         cross join lateral (select financeiro.situacao_previsao(l.id, nat.n, l.is_importado, l.cartao_id, l.mes_fatura) as s) sit
         where l.cartao_id = p_cartao_id and l.mes_fatura = date_trunc('month', p_mes::timestamp)::date
           and (l.perfil_financeiro_id = p_perfil_id or (l.perfil_financeiro_id is null and v_pessoal))
         order by l.data_compra, l.id;
end
$function$;

-- contas_bancarias_do_perfil: texto de 20261230090000 (definicao vigente) com a posse dos registros sem perfil pela guarda explicita (1 trecho(s)).
CREATE OR REPLACE FUNCTION financeiro.contas_bancarias_do_perfil(p_perfil_id integer)
 RETURNS TABLE(id integer, nome text, instituicao text, tipo text, cor text, status text)
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;

    return query
        select c.id, c.nome::text, c.instituicao::text, c.tipo::text, c.cor_display::text, c.status::text
          from public.conta_bancaria c
         where c.perfil_financeiro_id = p_perfil_id
            or (c.perfil_financeiro_id is null
                and financeiro.guarda_legado(p_perfil_id))
         order by c.nome;
end
$function$;

-- contas_do_mes: texto de 20261230090000 (definicao vigente) com a posse dos registros sem perfil pela guarda explicita (1 trecho(s)).
CREATE OR REPLACE FUNCTION financeiro.contas_do_mes(p_perfil_id integer, p_mes date)
 RETURNS TABLE(id integer, grupo text, nome text, valor numeric, valor_previsto numeric, valor_executado numeric, data_vencimento date, data_pagamento date, situacao text, status_pagamento text, categoria_nome text, categoria_cor text, cartao_id integer, cartao_nome text, numero_parcela integer, total_parcelas integer, debito_automatico boolean)
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_mes date;
    v_hoje date := (now() at time zone 'America/Sao_Paulo')::date;
    v_pessoal boolean;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if p_mes is null then
        raise exception 'Mes de competencia obrigatorio' using errcode = '22023';
    end if;
    v_mes := date_trunc('month', p_mes)::date;
    v_pessoal := financeiro.guarda_legado(p_perfil_id);

    return query
    with contas as (
        select c.*
          from public.conta c
         where (c.perfil_financeiro_id = p_perfil_id or (c.perfil_financeiro_id is null and v_pessoal))
           and c.status_pagamento is distinct from 'Substituida' and c.status_pagamento is distinct from 'Dispensada'  -- FIN-MVP-MOB-01: preservada, fora das despesas do mes
           and (
                (coalesce(c.is_fatura_cartao, false) = false and date_trunc('month', c.mes_referencia) = v_mes)
             or (c.is_fatura_cartao = true and date_trunc('month', c.cartao_competencia) = v_mes)
           )
    ),
    gastos as (
        -- gasto do mes por cartao e categoria de cartao, no perfil (mes_fatura = 1o dia, como no Flask)
        -- FIN-CARTOES-EXECUTADO-01: total = executado (a previsao fixa sem cobranca ja entra pelo valor previsto)
        select l.cartao_id, l.categoria_cartao_id, sum(financeiro.valor_executado_compra(l.valor, sit.s)) as total,
               sum(l.valor) filter (where sit.s = 'PREVISTA') as pendente,
               -- FIN-CARTAO-DESPESAS-FIXAS-01: parceladas e fixas nao consomem o limite da Categoria do Cartao
               sum(l.valor) filter (where financeiro.natureza_da_compra(l.total_parcelas, l.is_recorrente, l.item_despesa_id, l.categoria_cartao_id) = 'CATEGORIA') as total_categoria
          from public.lancamento_agregado l
         cross join lateral (select financeiro.situacao_previsao(l.id, financeiro.natureza_da_compra(l.total_parcelas, l.is_recorrente, l.item_despesa_id, l.categoria_cartao_id), l.is_importado, l.cartao_id, l.mes_fatura) as s) sit
         where (l.perfil_financeiro_id = p_perfil_id or (l.perfil_financeiro_id is null and v_pessoal))
           and l.mes_fatura = v_mes
         group by l.cartao_id, l.categoria_cartao_id
    ),
    faturas as (
        select c.id,
               -- FIN-CARTAO-NUBANK-CREDITOS-01: executado das compras menos os creditos da fatura (valor a pagar)
               coalesce((select sum(g.total) from gastos g where g.cartao_id = c.item_despesa_id), 0)
                   - financeiro.creditos_fatura(c.id) as executado,
               coalesce((select sum(g.pendente) from gastos g where g.cartao_id = c.item_despesa_id), 0) as pendente,
               coalesce((select sum(greatest(lim.limite_mensal - coalesce(g.total_categoria, 0), 0))
                           from public.cartao_categoria_limite lim
                           left join gastos g
                             on g.cartao_id = lim.cartao_id and g.categoria_cartao_id = lim.categoria_cartao_id
                          where lim.cartao_id = c.item_despesa_id and lim.ativo), 0) as complemento
          from contas c
         where c.is_fatura_cartao = true
    )
    select c.id,
           case when c.is_fatura_cartao then 'FATURA' else 'DESPESA' end,
           c.descricao::text,
           case
               when not coalesce(c.is_fatura_cartao, false) then c.valor
               when c.status_pagamento = 'Pago' then f.executado
               else f.executado + f.complemento
           end,
           case when c.is_fatura_cartao then f.executado + f.complemento end,
           case when c.is_fatura_cartao then f.executado end,
           c.data_vencimento,
           c.data_pagamento,
           case
               when c.status_pagamento = 'Pago' then 'PAGA'
               when c.status_pagamento = 'Atrasado' or c.data_vencimento < v_hoje then 'VENCIDA'
               else 'PENDENTE'
           end,
           coalesce(c.status_pagamento, 'Pendente')::text,
           cat.nome::text,
           cat.cor::text,
           case when c.is_fatura_cartao then c.item_despesa_id end,
           case when c.is_fatura_cartao then item.nome::text end,
           c.numero_parcela,
           c.total_parcelas,
           coalesce(c.debito_automatico, false)
      from contas c
      left join faturas f on f.id = c.id
      left join public.item_despesa item on item.id = c.item_despesa_id
      left join public.categoria cat on cat.id = item.categoria_id
     order by 2, c.data_vencimento, c.descricao, c.id;
end
$function$;

-- estornar_pagamento_fatura: texto de 20261230090000 (definicao vigente) com a posse dos registros sem perfil pela guarda explicita (1 trecho(s)).
CREATE OR REPLACE FUNCTION financeiro.estornar_pagamento_fatura(p_perfil_id integer, p_fatura_id integer, p_movimento_id integer, p_dados jsonb, p_chave uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_anterior  financeiro.operacao_cartao;
    v_fatura    public.conta;
    v_original  public.movimento_financeiro;
    v_motivo    text;
    v_data      date;
    v_estorno   integer;
    v_saldo     numeric;
    v_perfil    integer;
    v_resultado jsonb;
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if p_chave is null then
        raise exception 'Chave da operacao obrigatoria' using errcode = '22023';
    end if;
    perform pg_advisory_xact_lock(hashtextextended(p_chave::text, 20261031));
    select * into v_anterior from financeiro.operacao_cartao o where o.chave = p_chave;
    if found then
        if v_anterior.user_id is distinct from (select auth.uid()) or v_anterior.perfil_financeiro_id <> p_perfil_id
           or v_anterior.operacao <> 'estornar_pagamento_fatura' then
            raise exception 'Chave da operacao ja usada' using errcode = '22023';
        end if;
        return v_anterior.resultado || jsonb_build_object('repetida', true);
    end if;
    v_motivo := btrim(coalesce(p_dados ->> 'motivo', ''));
    if v_motivo = '' or length(v_motivo) > 500 then
        raise exception 'Informe o motivo do estorno (ate 500 caracteres)' using errcode = '22023';
    end if;
    begin
        v_data := (p_dados ->> 'data_estorno')::date;
    exception when invalid_datetime_format or datetime_field_overflow then
        raise exception 'Data do estorno invalida' using errcode = '22023';
    end;
    if v_data is null then
        raise exception 'Informe a data do estorno' using errcode = '22023';
    end if;
    if p_movimento_id is null then
        raise exception 'Pagamento a estornar nao identificado' using errcode = '22023';
    end if;

    perform financeiro.exigir_pagamento_novo(p_perfil_id);
    v_fatura := financeiro.travar_fatura_do_perfil(p_perfil_id, p_fatura_id);
    if v_fatura.status_pagamento is distinct from 'Pago' then
        raise exception 'Esta fatura nao esta paga: nada a estornar' using errcode = '22023', hint = 'NAO_PAGA';
    end if;
    select * into v_original from public.movimento_financeiro m where m.id = p_movimento_id;
    if not found or v_original.tipo <> 'DEBITO' or v_original.origem <> 'FATURA'
       or not (v_original.conta_id = v_fatura.id or v_original.fatura_id = v_fatura.id) then
        raise exception 'Pagamento nao encontrado nesta fatura' using errcode = '22023';
    end if;
    -- Ordem global: conta bancaria antes do movimento.
    perform 1 from public.conta_bancaria cb where cb.id = v_original.conta_bancaria_id for update;
    perform 1 from public.movimento_financeiro m where m.id = v_original.id for update;
    if p_movimento_id is distinct from financeiro.pagamento_vigente(v_fatura.id) then
        raise exception 'Este pagamento ja foi estornado ou nao e o pagamento atual da fatura'
            using errcode = '22023', hint = 'JA_ESTORNADO';
    end if;

    insert into public.movimento_financeiro (perfil_financeiro_id, conta_bancaria_id, tipo, valor, descricao, data_movimento,
                                             fatura_id, conta_id, origem, ajustavel, movimento_original_id, criado_em)
    values (coalesce(v_original.perfil_financeiro_id, p_perfil_id), v_original.conta_bancaria_id, 'CREDITO',
            v_original.valor, left('Estorno de pagamento da fatura: ' || coalesce(v_fatura.descricao, v_fatura.id::text), 200),
            v_data, v_fatura.id, v_fatura.id, 'ESTORNO_FATURA', false, v_original.id, now() at time zone 'utc')
    returning id into v_estorno;
    v_saldo := financeiro.atualizar_saldo_conta(v_original.conta_bancaria_id);
    update public.conta
       set status_pagamento = 'Pendente', data_pagamento = null,
           observacoes = concat_ws(E'\n', nullif(observacoes, ''), '[ESTORNO] ' || v_data::text || ' — ' || v_motivo)
     where id = v_fatura.id;
    -- Volta a aberta com os valores atuais das compras (planejado/executado), como qualquer fatura nao paga.
    v_perfil := coalesce(v_fatura.perfil_financeiro_id,
                         financeiro.perfil_guarda_legado());
    perform financeiro.recalcular_fatura(v_perfil, v_fatura.item_despesa_id, v_fatura.cartao_competencia);
    update financeiro.pagamento_fatura
       set estorno_movimento_id = v_estorno, estorno_motivo = v_motivo, estorno_user_id = (select auth.uid()),
           estornado_em = now()
     where movimento_id = v_original.id;
    if not found then  -- pagamento feito pelo Flask: registra so o estorno
        insert into financeiro.pagamento_fatura (fatura_id, perfil_financeiro_id, movimento_id, origem, estorno_movimento_id,
                                                estorno_motivo, estorno_user_id, estornado_em)
        values (v_fatura.id, p_perfil_id, v_original.id, 'FLASK', v_estorno, v_motivo, (select auth.uid()), now());
    end if;
    v_resultado := jsonb_build_object('fatura_id', v_fatura.id, 'movimento_estorno_id', v_estorno,
                                      'movimento_original_id', v_original.id, 'valor_estornado', v_original.valor,
                                      'data_estorno', v_data, 'conta_bancaria_id', v_original.conta_bancaria_id,
                                      'saldo_conta', v_saldo);
    insert into financeiro.operacao_cartao (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'estornar_pagamento_fatura', v_resultado);
    return v_resultado;
end
$function$;

-- executado_fatura: texto de 20261230090000 (definicao vigente) com a posse dos registros sem perfil pela guarda explicita (1 trecho(s)).
CREATE OR REPLACE FUNCTION financeiro.executado_fatura(p_fatura_id integer)
 RETURNS numeric
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
    -- FIN-CARTOES-EXECUTADO-01: previsao de recorrencia sem cobranca entra pelo valor previsto; a nao cobrada fica fora
    -- FIN-CARTAO-NUBANK-CREDITOS-01: menos os creditos da fatura (estorno, IOF devolvido, ajuste): o valor a pagar
    select coalesce(sum(financeiro.valor_executado_compra(l.valor, financeiro.situacao_previsao(l.id, financeiro.natureza_da_compra(l.total_parcelas, l.is_recorrente, l.item_despesa_id, l.categoria_cartao_id), l.is_importado, l.cartao_id, l.mes_fatura))), 0)
           - financeiro.creditos_fatura(p_fatura_id)
      from public.conta c
      join public.lancamento_agregado l on l.cartao_id = c.item_despesa_id and l.mes_fatura = c.cartao_competencia
     where c.id = p_fatura_id
       and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, coalesce(c.perfil_financeiro_id,
               financeiro.perfil_guarda_legado()))
$function$;

-- faturas_do_mes: texto de 20261230090000 (definicao vigente) com a posse dos registros sem perfil pela guarda explicita (1 trecho(s)).
CREATE OR REPLACE FUNCTION financeiro.faturas_do_mes(p_perfil_id integer, p_mes date)
 RETURNS TABLE(cartao_id integer, cartao_nome text, fatura_id integer, competencia date, data_vencimento date, situacao text, valor_executado numeric, valor_previsto numeric, compras integer, pode_gerir boolean)
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_mes     date;
    v_pessoal boolean;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    v_mes := date_trunc('month', p_mes::timestamp)::date;
    v_pessoal := financeiro.guarda_legado(p_perfil_id);
    return query
    with cartoes as (
        select i.id, i.nome from public.item_despesa i
         where i.tipo = 'Agregador' and coalesce(i.ativo, true) and financeiro.pertence_ao_perfil(i.perfil_financeiro_id, p_perfil_id)
    ),
    gastos as (
        -- FIN-CARTOES-EXECUTADO-01: gasto = executado (a previsao fixa sem cobranca ja entra pelo valor previsto)
        select l.cartao_id, l.categoria_cartao_id, sum(financeiro.valor_executado_compra(l.valor, sit.s)) as gasto,
               count(*) as qtd, sum(l.valor) filter (where sit.s = 'PREVISTA') as pendente,
               -- FIN-CARTAO-DESPESAS-FIXAS-01: parceladas e fixas nao consomem o limite da Categoria do Cartao
               sum(l.valor) filter (where financeiro.natureza_da_compra(l.total_parcelas, l.is_recorrente, l.item_despesa_id, l.categoria_cartao_id) = 'CATEGORIA') as gasto_categoria
          from public.lancamento_agregado l
         cross join lateral (select financeiro.situacao_previsao(l.id, financeiro.natureza_da_compra(l.total_parcelas, l.is_recorrente, l.item_despesa_id, l.categoria_cartao_id), l.is_importado, l.cartao_id, l.mes_fatura) as s) sit
         where l.mes_fatura = v_mes and (l.perfil_financeiro_id = p_perfil_id or (l.perfil_financeiro_id is null and v_pessoal))
         group by 1, 2
    )
    -- FIN-CARTAO-NUBANK-CREDITOS-01: executado e previsto ja descontam os creditos da fatura
    select c.id, c.nome::text, f.id, v_mes, f.data_vencimento,
           case when f.id is null then 'SEM_FATURA'
                when f.status_pagamento = 'Pago' or f.status_fatura = 'PAGA' then 'PAGA'
                when f.status_fatura = 'FECHADA' then 'FECHADA' else 'ABERTA' end,
           (coalesce((select sum(g.gasto) from gastos g where g.cartao_id = c.id), 0) - financeiro.creditos_fatura(f.id)),
           case when f.status_pagamento = 'Pago' then (coalesce((select sum(g.gasto) from gastos g where g.cartao_id = c.id), 0) - financeiro.creditos_fatura(f.id))
                else (coalesce((select sum(g.gasto) from gastos g where g.cartao_id = c.id), 0) - financeiro.creditos_fatura(f.id))
                     + coalesce((select sum(greatest(lim.limite_mensal - coalesce(g.gasto_categoria, 0), 0))
                                   from public.cartao_categoria_limite lim
                                   left join gastos g on g.cartao_id = c.id and g.categoria_cartao_id = lim.categoria_cartao_id
                                  where lim.cartao_id = c.id and lim.ativo), 0) end,
           coalesce((select sum(g.qtd) from gastos g where g.cartao_id = c.id), 0)::integer,
           financeiro.pode_gerir_perfil(p_perfil_id)
      from cartoes c
      left join public.conta f on f.id = financeiro.fatura_do_mes(c.id, v_mes)
     order by c.nome;
end
$function$;

-- fontes_de_receita: texto de 20261230090000 (definicao vigente) com a posse dos registros sem perfil pela guarda explicita (1 trecho(s)).
CREATE OR REPLACE FUNCTION financeiro.fontes_de_receita(p_perfil_id integer)
 RETURNS TABLE(id integer, nome text, tipo text, recorrente boolean, ativo boolean, dia_previsto integer, conta_bancaria_id integer, valor_base_mensal numeric, de_outro_modulo boolean)
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_pessoal boolean;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    v_pessoal := financeiro.guarda_legado(p_perfil_id);
    return query
        select i.id, i.nome::text, i.tipo::text, coalesce(i.recorrente, true), coalesce(i.ativo, true),
               i.dia_previsto_pagamento, i.conta_bancaria_id, i.valor_base_mensal, financeiro.fonte_de_outro_modulo(i.id)
          from public.item_receita i
         where i.perfil_financeiro_id = p_perfil_id or (i.perfil_financeiro_id is null and v_pessoal)
         order by i.nome;
end
$function$;

-- lancamentos_da_fatura: texto de 20261230090000 (definicao vigente) com a posse dos registros sem perfil pela guarda explicita (1 trecho(s)).
CREATE OR REPLACE FUNCTION financeiro.lancamentos_da_fatura(p_perfil_id integer, p_conta_id integer)
 RETURNS TABLE(id integer, descricao text, valor numeric, data_compra date, numero_parcela integer, total_parcelas integer, categoria_cartao text)
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_pessoal boolean;
    v_cartao integer;
    v_competencia date;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    v_pessoal := financeiro.guarda_legado(p_perfil_id);

    select c.item_despesa_id, date_trunc('month', c.cartao_competencia)::date
      into v_cartao, v_competencia
      from public.conta c
     where c.id = p_conta_id
       and c.is_fatura_cartao = true
       and (c.perfil_financeiro_id = p_perfil_id or (c.perfil_financeiro_id is null and v_pessoal));
    if v_cartao is null then
        -- Mesmo erro para "nao existe" e "de outro perfil": nao revela ids alheios.
        raise exception 'Fatura nao encontrada no perfil' using errcode = '42501';
    end if;

    return query
        select l.id, coalesce(nullif(l.descricao_exibida, ''), l.descricao)::text, l.valor, l.data_compra,
               l.numero_parcela, l.total_parcelas, cc.nome::text
          from public.lancamento_agregado l
          left join public.categoria_cartao cc on cc.id = l.categoria_cartao_id
         where l.cartao_id = v_cartao
           and l.mes_fatura = v_competencia
           and (l.perfil_financeiro_id = p_perfil_id or (l.perfil_financeiro_id is null and v_pessoal))
         order by l.data_compra, l.id;
end
$function$;

-- limpar_importacoes_cartao: texto de 20261230090000 (definicao vigente) com a posse dos registros sem perfil pela guarda explicita (1 trecho(s)).
CREATE OR REPLACE FUNCTION financeiro.limpar_importacoes_cartao(p_perfil_id integer, p_cartao_id integer, p_competencia date, p_hash text, p_chave uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_anterior financeiro.operacao_cartao;
    v_previa   jsonb;
    v_compras  integer[];
    v_creditos bigint[];
    v_fotos_c  jsonb;
    v_fotos_k  jsonb;
    v_meses    record;
    v_res      jsonb;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if not financeiro.guarda_legado(p_perfil_id) then
        raise exception 'A limpeza das importacoes e so do perfil Pessoal' using errcode = '42501';
    end if;
    if p_chave is null then
        raise exception 'Chave da operacao obrigatoria' using errcode = '22023';
    end if;
    perform pg_advisory_xact_lock(hashtextextended(p_chave::text, 20261213));
    select * into v_anterior from financeiro.operacao_cartao o where o.chave = p_chave;
    if found then
        if v_anterior.user_id is distinct from (select auth.uid()) or v_anterior.perfil_financeiro_id <> p_perfil_id then
            raise exception 'Chave da operacao ja usada' using errcode = '22023';
        end if;
        return (v_anterior.resultado - 'fotos') || jsonb_build_object('repetida', true);
    end if;
    perform pg_advisory_xact_lock(20261023, p_perfil_id);  -- mesma trava das compras e da importacao do perfil
    perform 1 from public.item_despesa i where i.tipo = 'Agregador' and (p_cartao_id is null or i.id = p_cartao_id)
                                           and financeiro.pertence_ao_perfil(i.perfil_financeiro_id, p_perfil_id) for update;
    v_previa := financeiro.previa_limpeza_importacoes(p_perfil_id, p_cartao_id, p_competencia);
    if p_hash is distinct from v_previa ->> 'hash' then
        raise exception 'A previa da limpeza mudou desde a conferencia: confira de novo' using errcode = '40001';
    end if;
    if jsonb_array_length(v_previa -> 'protegidos') > 0 then
        raise exception 'Limpeza interrompida: % registro(s) importado(s) protegido(s) (fatura paga ou consolidada, ocorrencia de recorrencia, credito vinculado). Nada foi removido.',
            jsonb_array_length(v_previa -> 'protegidos') using errcode = 'P0001';
    end if;
    select coalesce(array_agg((x ->> 'id')::integer), '{}') into v_compras from jsonb_array_elements(v_previa -> 'compras_elegiveis') x;
    select coalesce(array_agg((x ->> 'id')::bigint), '{}') into v_creditos from jsonb_array_elements(v_previa -> 'creditos_elegiveis') x;
    if cardinality(v_compras) + cardinality(v_creditos) = 0 then
        raise exception 'Nada a limpar nesta selecao' using errcode = '22023';
    end if;
    select coalesce(jsonb_agg(to_jsonb(l) order by l.id), '[]'::jsonb) into v_fotos_c from public.lancamento_agregado l where l.id = any(v_compras);
    select coalesce(jsonb_agg(to_jsonb(cf) order by cf.id), '[]'::jsonb) into v_fotos_k from financeiro.credito_fatura cf where cf.id = any(v_creditos);
    delete from financeiro.credito_fatura where id = any(v_creditos);
    delete from public.lancamento_agregado where id = any(v_compras);
    for v_meses in
        select distinct (x ->> 'cartao_id')::integer as cartao, (x ->> 'mes_fatura')::date as mes
          from (select jsonb_array_elements(v_fotos_c) x union all select jsonb_array_elements(v_fotos_k)) y
    loop
        perform financeiro.recalcular_fatura(p_perfil_id, v_meses.cartao, v_meses.mes);
    end loop;
    v_res := jsonb_build_object('compras_removidas', cardinality(v_compras), 'creditos_removidos', cardinality(v_creditos),
                                'valor_compras', v_previa -> 'totais' -> 'valor_compras',
                                'valor_creditos', v_previa -> 'totais' -> 'valor_creditos',
                                'por_fatura', v_previa -> 'por_fatura', 'filtro', v_previa -> 'filtro', 'hash', p_hash);
    insert into financeiro.operacao_cartao (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'limpar_importacoes',
            v_res || jsonb_build_object('fotos', jsonb_build_object('compras', v_fotos_c, 'creditos', v_fotos_k)));
    return v_res;
end
$function$;

-- mes_pode_estar_incompleto: texto de 20261230090000 (definicao vigente) com a posse dos registros sem perfil pela guarda explicita (1 trecho(s)).
CREATE OR REPLACE FUNCTION financeiro.mes_pode_estar_incompleto(p_perfil_id integer, p_mes date)
 RETURNS boolean
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_mes date;
    v_pessoal boolean;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if p_mes is null then
        raise exception 'Mes de competencia obrigatorio' using errcode = '22023';
    end if;
    v_mes := date_trunc('month', p_mes)::date;
    v_pessoal := financeiro.guarda_legado(p_perfil_id);

    return exists (
        select 1
          from public.item_despesa i
         where (i.perfil_financeiro_id = p_perfil_id or (i.perfil_financeiro_id is null and v_pessoal))
           and coalesce(i.ativo, true)
           and coalesce(i.recorrente, false)
           and coalesce(i.tipo_recorrencia, 'mensal') = 'mensal'
           and i.tipo <> 'Agregador'
           and i.data_vencimento is not null
           and date_trunc('month', i.data_vencimento) <= v_mes
           and not exists (select 1 from public.conta c
                            where c.item_despesa_id = i.id and date_trunc('month', c.mes_referencia) = v_mes)
    ) or exists (
        select 1
          from public.item_despesa cartao
         where (cartao.perfil_financeiro_id = p_perfil_id or (cartao.perfil_financeiro_id is null and v_pessoal))
           and cartao.tipo = 'Agregador'
           and coalesce(cartao.ativo, true)
           and not exists (select 1 from public.conta c
                            where c.item_despesa_id = cartao.id and c.is_fatura_cartao = true
                              and date_trunc('month', c.cartao_competencia) = v_mes)
    );
end
$function$;

-- plano_recorrencia: texto de 20261230090000 (definicao vigente) com a posse dos registros sem perfil pela guarda explicita (1 trecho(s)).
CREATE OR REPLACE FUNCTION financeiro.plano_recorrencia(p_perfil_id integer, p_mes date)
 RETURNS SETOF financeiro.linha_plano
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_mes     date := date_trunc('month', p_mes::timestamp)::date;
    v_limite  date := (date_trunc('month', p_mes::timestamp) + interval '1 month')::date;
    v_ns      constant uuid := '7f3a1b2c-4d5e-6f7a-8b9c-0d1e2f3a4b5c';  -- namespace do Flask
    v_pessoal boolean;
    v_consolidada date;  -- FIN-CARTOES-D6-INTEGRIDADE-1
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
    v_pessoal := financeiro.guarda_legado(p_perfil_id);

    -- 1) Recorrencias: conta (boleto, debito, pix...) ou compra no cartao.
    for v_item in
        select i.*
          from public.item_despesa i
         where (i.perfil_financeiro_id = p_perfil_id or (i.perfil_financeiro_id is null and v_pessoal))
           and coalesce(i.recorrente, false)
           -- FIN-FIDELIDADE-CARTOES-2 (R4): o proprio cartao (Agregador) e gravado como recorrente (como no Flask), mas a
           -- fatura dele e gerada pela parte de cartoes; ele nao e uma recorrencia que produz despesa.
           and i.tipo is distinct from 'Agregador'
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
        elsif coalesce(v_item.tipo_recorrencia, 'mensal') not in ('mensal', 'anual')
              and financeiro.semanas_da_recorrencia(v_item.tipo_recorrencia) is null then  -- FIN-CATEGORIAS-RECORRENCIAS-2
            v_motivo := 'Tipo de recorrencia fora do escopo: ' || v_item.tipo_recorrencia;
        elsif v_linha.natureza = 'LANCAMENTO_CARTAO'
              and financeiro.semanas_da_recorrencia(v_item.tipo_recorrencia) is not null then  -- FIN-CATEGORIAS-RECORRENCIAS-2
            v_motivo := 'Recorrencia semanal no cartao: o sistema original tambem nao a lanca (so mensal e anual)';
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

        -- FIN-CATEGORIAS-RECORRENCIAS-2 (R1): semanal e a cada 2 semanas, uma linha por ocorrencia.
        if financeiro.semanas_da_recorrencia(v_item.tipo_recorrencia) is not null then
            return query select * from financeiro.ocorrencias_semanais(v_linha, v_item.tipo_recorrencia,
                                                                       v_item.data_vencimento, v_limite);
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
                        -- FIN-FATURA-INTEGRIDADE-1: pelo mes so os antigos, sem compra_id (uma compra de outra
                        -- competencia desviada para este mes por fatura paga nao e a deste mes).
                        or (l.item_despesa_id = v_item.id and l.mes_fatura = v_comp and l.is_recorrente
                            and l.compra_id is null)
                     order by l.id
                     limit 1;
                end if;
                v_linha.situacao := case when v_id is null then 'A_GERAR' else 'EXISTENTE' end;
                -- FIN-CARTOES-D6-INTEGRIDADE-1: a geracao automatica nao e confirmacao do usuario (D6) e nao muda a
                -- competencia (D5): compra recorrente cujo destino e fatura consolidada nao e gerada (nem em silencio,
                -- nem em outro mes). Fica REJEITADA, com o motivo na previa, ate o usuario lancar pela compra, com a
                -- confirmacao. Nada e gravado; a proxima previa reavalia (idempotente).
                if v_linha.natureza = 'LANCAMENTO_CARTAO' and v_linha.situacao = 'A_GERAR' then
                    v_consolidada := financeiro.fatura_consolidada_no_destino(v_linha.cartao_id, v_comp);
                    if v_consolidada is not null then
                        v_linha.situacao := 'REJEITADA';
                        v_linha.motivo := 'Fatura de ' || to_char(v_consolidada, 'MM/YYYY')
                            || ' consolidada: a compra recorrente nao entra sem confirmacao (lance-a pela compra no cartao)';
                    end if;
                end if;
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
$function$;

-- previa_reclassificacao_categorias: texto de 20261230090000 (definicao vigente) com a posse dos registros sem perfil pela guarda explicita (1 trecho(s)).
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

-- previsto_fatura: texto de 20261230090000 (definicao vigente) com a posse dos registros sem perfil pela guarda explicita (1 trecho(s)).
CREATE OR REPLACE FUNCTION financeiro.previsto_fatura(p_fatura_id integer)
 RETURNS numeric
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
    select case when c.status_pagamento = 'Pago' then financeiro.executado_fatura(c.id)
                else financeiro.executado_fatura(c.id)
                     + coalesce((select sum(greatest(lim.limite_mensal - coalesce((
                                    select sum(l.valor) from public.lancamento_agregado l
                                     where l.cartao_id = c.item_despesa_id and l.mes_fatura = c.cartao_competencia
                                       and l.categoria_cartao_id = lim.categoria_cartao_id
                                       and financeiro.natureza_da_compra(l.total_parcelas, l.is_recorrente, l.item_despesa_id, l.categoria_cartao_id) = 'CATEGORIA'
                                       and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, coalesce(c.perfil_financeiro_id,
                                               financeiro.perfil_guarda_legado()))), 0), 0))
                                   from public.cartao_categoria_limite lim
                                  where lim.cartao_id = c.item_despesa_id and lim.ativo), 0) end
      from public.conta c
     where c.id = p_fatura_id and c.is_fatura_cartao
$function$;

-- reativar_competencia_interno: texto de 20261230090000 (definicao vigente) com a posse dos registros sem perfil pela guarda explicita (1 trecho(s)).
CREATE OR REPLACE FUNCTION financeiro.reativar_competencia_interno(p_perfil_id integer, p_natureza text, p_item_id integer, p_competencia date)
 RETURNS boolean
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_pessoal boolean;
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    v_pessoal := financeiro.guarda_legado(p_perfil_id);
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
$function$;

-- recalcular_fatura: texto de 20261230090000 (definicao vigente) com a posse dos registros sem perfil pela guarda explicita (1 trecho(s)).
CREATE OR REPLACE FUNCTION financeiro.recalcular_fatura(p_perfil_id integer, p_cartao_id integer, p_competencia date)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
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
    v_pessoal := financeiro.guarda_legado(p_perfil_id);
    v_plan := financeiro.planejado_fatura(p_perfil_id, p_cartao_id, p_competencia);
    -- FIN-CARTOES-EXECUTADO-01: previsao de recorrencia sem cobranca entra pelo valor previsto; a nao cobrada fica fora
    select coalesce(sum(financeiro.valor_executado_compra(l.valor, financeiro.situacao_previsao(l.id, financeiro.natureza_da_compra(l.total_parcelas, l.is_recorrente, l.item_despesa_id, l.categoria_cartao_id), l.is_importado, l.cartao_id, l.mes_fatura))), 0)
      into v_exec from public.lancamento_agregado l
     where l.cartao_id = p_cartao_id and l.mes_fatura = p_competencia
       and (l.perfil_financeiro_id = p_perfil_id or (l.perfil_financeiro_id is null and v_pessoal));
    -- FIN-CARTAO-NUBANK-CREDITOS-01: creditos da fatura abatem o executado e o planejado (valor a pagar)
    v_exec := v_exec - financeiro.creditos_fatura(v_id);
    v_plan := v_plan - financeiro.creditos_fatura(v_id);
    update public.conta set valor_planejado = v_plan, valor_executado = v_exec, estouro_orcamento = v_exec > v_plan,
                            valor = v_plan
     where id = v_id;
end
$function$;

-- recebido_da_previsao: texto de 20261230090000 (definicao vigente) com a posse dos registros sem perfil pela guarda explicita (1 trecho(s)).
CREATE OR REPLACE FUNCTION financeiro.recebido_da_previsao(p_orcamento_id integer)
 RETURNS numeric
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
    select coalesce(sum(r.valor_recebido), 0)
      from public.receita_orcamento o
      join public.receita_realizada r on r.item_receita_id = o.item_receita_id
       and date_trunc('month', r.mes_referencia::timestamp) = date_trunc('month', o.mes_referencia::timestamp)
     where o.id = p_orcamento_id
       and financeiro.pertence_ao_perfil(r.perfil_financeiro_id, coalesce(o.perfil_financeiro_id,
               financeiro.perfil_guarda_legado()))
       and not financeiro.receita_estornada(r.id)
       and not (coalesce(r.observacoes, '') ~ 'consorcio_id=[0-9]+' and r.conta_bancaria_id is null)
$function$;

-- receitas_do_mes: texto de 20261230090000 (definicao vigente) com a posse dos registros sem perfil pela guarda explicita (1 trecho(s)).
CREATE OR REPLACE FUNCTION financeiro.receitas_do_mes(p_perfil_id integer, p_mes date)
 RETURNS TABLE(origem text, id integer, item_receita_id integer, nome text, tipo text, competencia date, data_prevista date, valor_previsto numeric, valor_recebido numeric, situacao text, conta_bancaria_nome text, recorrente boolean, fonte_ativa boolean, observacoes text, data_prevista_explicita boolean)
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_mes     date;
    v_pessoal boolean;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if p_mes is null then
        raise exception 'Mes de competencia obrigatorio' using errcode = '22023';
    end if;
    v_mes := date_trunc('month', p_mes::timestamp)::date;
    v_pessoal := financeiro.guarda_legado(p_perfil_id);

    return query
    with realizadas as (
        select r.*, financeiro.receita_estornada(r.id) as estornada,
               (coalesce(r.observacoes, '') ~ 'consorcio_id=[0-9]+' and r.conta_bancaria_id is null) as consorcio
          from public.receita_realizada r
         where (r.perfil_financeiro_id = p_perfil_id or (r.perfil_financeiro_id is null and v_pessoal))
           and date_trunc('month', r.mes_referencia::timestamp)::date = v_mes
    ),
    previsoes as (
        select o.id, o.item_receita_id, i.nome, i.tipo, o.mes_referencia, o.valor_esperado, o.observacoes,
               o.data_prevista as data_explicita,
               i.dia_previsto_pagamento, i.conta_bancaria_id, coalesce(i.recorrente, true) as recorrente,
               coalesce(i.ativo, true) as ativo,
               coalesce((select sum(r.valor_recebido) from realizadas r
                          where r.item_receita_id = o.item_receita_id and not r.estornada and not r.consorcio), 0) as recebido
          from public.receita_orcamento o
          join public.item_receita i on i.id = o.item_receita_id
         where (o.perfil_financeiro_id = p_perfil_id or (o.perfil_financeiro_id is null and v_pessoal))
           and date_trunc('month', o.mes_referencia::timestamp)::date = v_mes
    ),
    linhas as (
    select 'PREVISAO'::text as origem, p.id, p.item_receita_id, p.nome::text as nome, p.tipo::text as tipo,
           v_mes as competencia,
           coalesce(p.data_explicita,
                    case when p.dia_previsto_pagamento between 1 and 31
                         then financeiro.dia_contratual(v_mes, p.dia_previsto_pagamento) end) as data_prevista,
           p.valor_esperado as valor_previsto, p.recebido as valor_recebido,
           case when p.valor_esperado = 0 and coalesce(p.observacoes, '') ilike 'Removid%' then 'REMOVIDA'
                when p.recebido > 0 and (p.valor_esperado <= 0 or p.recebido >= p.valor_esperado) then 'RECEBIDA'
                when p.recebido > 0 then 'PARCIAL'
                when not p.ativo then 'INATIVA'
                else 'PREVISTA' end as situacao,
           (select b.nome::text from public.conta_bancaria b where b.id = p.conta_bancaria_id) as conta_bancaria_nome,
           p.recorrente, p.ativo as fonte_ativa, p.observacoes, p.data_explicita is not null as data_prevista_explicita
      from previsoes p
    union all
    -- Recebimentos sem previsao na competencia, estornos e previsoes de consorcio: linhas proprias.
    select 'RECEBIMENTO'::text, r.id, r.item_receita_id, coalesce(i.nome, r.descricao, 'Receita')::text,
           coalesce(i.tipo, 'PONTUAL')::text, v_mes, r.data_recebimento,
           case when r.consorcio then r.valor_recebido end,
           case when r.consorcio then 0 else r.valor_recebido end,
           case when r.estornada then 'ESTORNADA' when r.consorcio then 'PREVISTA_CONSORCIO' else 'RECEBIDA' end,
           (select b.nome::text from public.conta_bancaria b where b.id = r.conta_bancaria_id),
           coalesce(i.recorrente, false), coalesce(i.ativo, true), r.observacoes, false
      from realizadas r
      left join public.item_receita i on i.id = r.item_receita_id
     where r.estornada or r.consorcio
        or not exists (select 1 from previsoes p where p.item_receita_id = r.item_receita_id)
    )
    -- Mesma ordem da tela de receitas do Flask: prevista, parcial, recebida; depois as demais.
    select l.origem, l.id, l.item_receita_id, l.nome, l.tipo, l.competencia, l.data_prevista, l.valor_previsto,
           l.valor_recebido, l.situacao, l.conta_bancaria_nome, l.recorrente, l.fonte_ativa, l.observacoes,
           l.data_prevista_explicita
      from linhas l
     order by case l.situacao when 'PREVISTA' then 0 when 'PREVISTA_CONSORCIO' then 0 when 'PARCIAL' then 1
                               when 'RECEBIDA' then 2 else 3 end,
              l.data_prevista nulls last, l.nome;
end
$function$;

-- recorrencias_do_perfil: texto de 20261230090000 (definicao vigente) com a posse dos registros sem perfil pela guarda explicita (1 trecho(s)).
CREATE OR REPLACE FUNCTION financeiro.recorrencias_do_perfil(p_perfil_id integer)
 RETURNS TABLE(id integer, nome text, descricao text, valor numeric, categoria_id integer, categoria_nome text, categoria_cor text, tipo_recorrencia text, data_vencimento date, proximo_vencimento date, meio_pagamento text, cartao_id integer, cartao_nome text, conta_bancaria_id integer, conta_bancaria_nome text, ativo boolean, gerenciavel boolean, versao text)
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_pessoal boolean;
    v_hoje date := (now() at time zone 'America/Sao_Paulo')::date;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    v_pessoal := financeiro.guarda_legado(p_perfil_id);
    return query
        select i.id, i.nome::text, i.descricao::text, i.valor, i.categoria_id, cat.nome::text, cat.cor::text,
               coalesce(i.tipo_recorrencia, 'mensal')::text, i.data_vencimento,
               -- Mesmo calculo do Flask (_proximo_vencimento) para mensal e anual, sem deslizar o dia contratual
               -- (soma a partir da data original, como o gerador). Outras frequencias: so a data se ainda vier.
               case
                   when i.data_vencimento is null then null
                   -- FIN-CATEGORIAS-RECORRENCIAS-2: semanal como _proximo_vencimento do Flask (vencimento levado ao dia da semana).
                   when financeiro.semanas_da_recorrencia(i.tipo_recorrencia) is not null
                       then financeiro.proxima_ocorrencia_semanal(i.tipo_recorrencia, i.data_vencimento, v_hoje)
                   when i.data_vencimento >= v_hoje then i.data_vencimento
                   when coalesce(i.tipo_recorrencia, 'mensal') in ('mensal', 'anual') then (
                       select min(d)::date
                         from generate_series(0, 1200) k,
                              lateral (select case when coalesce(i.tipo_recorrencia, 'mensal') = 'anual'
                                                   then i.data_vencimento + make_interval(years => k)
                                                   else i.data_vencimento + make_interval(months => k) end as d) x
                        where x.d >= v_hoje)
               end,
               i.meio_pagamento::text, i.cartao_id, cartao.nome::text, i.conta_bancaria_id, cb.nome::text,
               coalesce(i.ativo, true),
               i.tipo = 'Simples' and i.origem_tipo is null and coalesce(i.meio_pagamento, '') <> 'cartao',
               financeiro.versao_recorrencia(i.id)
          from public.item_despesa i
          left join public.categoria cat on cat.id = i.categoria_id
          left join public.item_despesa cartao on cartao.id = i.cartao_id
          left join public.conta_bancaria cb on cb.id = i.conta_bancaria_id
         where (i.perfil_financeiro_id = p_perfil_id or (i.perfil_financeiro_id is null and v_pessoal))
           and coalesce(i.recorrente, false)
           and i.tipo is distinct from 'Consorcio'
           and i.tipo is distinct from 'Agregador'
         order by i.nome, i.id;
end
$function$;

-- referencias_categoria: texto de 20261230090000 (definicao vigente) com a posse dos registros sem perfil pela guarda explicita (1 trecho(s)).
CREATE OR REPLACE FUNCTION financeiro.referencias_categoria(p_categoria_id integer)
 RETURNS TABLE(tabela text, coluna text, registros bigint, valor numeric, perfis integer[])
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_fk      record;
    v_pessoal integer := financeiro.perfil_guarda_legado();
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
$function$;

-- reverter_reclassificacao_categorias: texto de 20261230090000 (definicao vigente) com a posse dos registros sem perfil pela guarda explicita (1 trecho(s)).
CREATE OR REPLACE FUNCTION financeiro.reverter_reclassificacao_categorias(p_chave_origem uuid, p_chave uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_anterior financeiro.operacao_catalogo;
    v_origem   financeiro.operacao_catalogo;
    v_f        jsonb;
    v_perfil   integer;
    v_n        bigint;
    v_total    integer := 0;
    v_pessoal  integer := financeiro.perfil_guarda_legado();
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
$function$;

-- anular_abastecimento: texto de 20261230090000 (definicao vigente); o motivo so e validado depois de conferidos o perfil e o abastecimento.
CREATE OR REPLACE FUNCTION financeiro.anular_abastecimento(p_perfil_id integer, p_id integer, p_dados jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    a        financeiro.abastecimento;
    n        financeiro.abastecimento;
    v_motivo text;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    a := financeiro.mob_abastecimento(p_perfil_id, p_id);
    v_motivo := financeiro.mob_exigir_motivo(p_dados);  -- so depois da autorizacao
    if a.anulado_em is not null then
        raise exception 'Abastecimento já anulado' using errcode = '22023';
    end if;
    if a.lancamento_id is not null or a.conta_id is not null then
        raise exception 'Desvincule a despesa antes de anular. Nada foi gravado.' using errcode = '22023', hint = 'ABASTECIMENTO_VINCULADO';
    end if;
    update financeiro.abastecimento x set anulado_em = now(), anulado_por = (select auth.uid()), atualizado_em = now()
     where x.id = a.id
    returning * into n;
    insert into financeiro.abastecimento_historico (abastecimento_id, acao, motivo, antes, depois, user_id)
    values (a.id, 'ANULACAO', v_motivo, to_jsonb(a), to_jsonb(n), (select auth.uid()));
    return jsonb_build_object('abastecimento', financeiro.mob_abastecimento_flask(n));
end
$function$;

-- corrigir_abastecimento: texto de 20261230090000 (definicao vigente); o motivo so e validado depois de conferidos o perfil e o abastecimento.
CREATE OR REPLACE FUNCTION financeiro.corrigir_abastecimento(p_perfil_id integer, p_id integer, p_dados jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    a        financeiro.abastecimento;
    n        financeiro.abastecimento;
    v_motivo text;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    a := financeiro.mob_abastecimento(p_perfil_id, p_id);
    v_motivo := financeiro.mob_exigir_motivo(p_dados);  -- so depois da autorizacao
    if a.anulado_em is not null then
        raise exception 'Abastecimento anulado não pode ser corrigido' using errcode = '22023';
    end if;
    n := financeiro.mob_dados_abastecimento(p_perfil_id, to_jsonb(a) || (coalesce(p_dados, '{}'::jsonb) - 'id') || jsonb_build_object('id', a.id));
    if (a.lancamento_id is not null or a.conta_id is not null)
       and (n.veiculo_id <> a.veiculo_id or n.valor_total <> a.valor_total) then
        raise exception 'Desvincule a despesa antes de corrigir o veículo ou o valor. Nada foi gravado.' using errcode = '22023', hint = 'ABASTECIMENTO_VINCULADO';
    end if;
    update financeiro.abastecimento x
       set veiculo_id = n.veiculo_id, perfil_financeiro_id = n.perfil_financeiro_id, data_abastecimento = n.data_abastecimento,
           hodometro_km = n.hodometro_km, combustivel = n.combustivel, preco_litro = n.preco_litro, valor_total = n.valor_total,
           meio_pagamento = n.meio_pagamento, cartao_id = n.cartao_id, cartao_vinculado_id = n.cartao_vinculado_id,
           estabelecimento = n.estabelecimento, observacoes = n.observacoes, atualizado_em = now()
     where x.id = a.id
    returning * into n;
    insert into financeiro.abastecimento_historico (abastecimento_id, acao, motivo, antes, depois, user_id)
    values (a.id, 'CORRECAO', v_motivo, to_jsonb(a), to_jsonb(n), (select auth.uid()));
    return jsonb_build_object('abastecimento', financeiro.mob_abastecimento_flask(n));
end
$function$;
