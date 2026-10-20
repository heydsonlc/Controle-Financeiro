-- CF-SUPABASE-REFACTOR-1 — primeiro modulo da nova arquitetura: categorias (somente leitura).
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica. Validada apenas em
-- cluster PostgreSQL local descartavel (tests/test_supabase_mvp_rls.py).
--
-- Decisoes:
-- - Schema proprio `financeiro`, separado do `public` (onde vivem as tabelas do
--   Flask). Precisa ser exposto explicitamente na Data API do Supabase.
-- - Cada linha pertence a um usuario do Supabase Auth (`user_id`).
-- - RLS habilitada E forcada antes de qualquer acesso pelo navegador.
-- - Navegador so le: `authenticated` recebe apenas SELECT; `anon` nao recebe nada.
--   Escrita vira depois por RPC transacional, nunca por INSERT/UPDATE direto.

create schema if not exists financeiro;

revoke all on schema financeiro from public;
revoke all on schema financeiro from anon;
grant usage on schema financeiro to authenticated;

-- Tabelas futuras do schema nascem sem privilegios para anon/authenticated.
-- (Para funcoes nao ha efeito equivalente: default privileges por schema so
-- ACRESCENTAM aos globais, e EXECUTE para PUBLIC e global. Toda RPC futura deve
-- fazer `revoke execute ... from public, anon` explicitamente.)
alter default privileges in schema financeiro revoke all on tables from public, anon, authenticated;

create table financeiro.categorias (
    id          bigint generated always as identity primary key,
    user_id     uuid        not null default auth.uid() references auth.users (id) on delete cascade,
    nome        text        not null check (char_length(btrim(nome)) between 1 and 100),
    descricao   text,
    cor         text        not null default '#6c757d' check (cor ~ '^#[0-9A-Fa-f]{6}$'),
    icone       text        check (icone is null or char_length(icone) <= 50),
    ativo       boolean     not null default true,
    criado_em   timestamptz not null default now()
);

comment on table financeiro.categorias is
    'Agrupador de despesas por usuario (CF-SUPABASE-REFACTOR-1). Leitura via RLS; escrita futura so por RPC.';

create unique index categorias_user_nome_uk on financeiro.categorias (user_id, lower(btrim(nome)));
create index categorias_user_ativo_idx on financeiro.categorias (user_id, ativo);

alter table financeiro.categorias enable row level security;
alter table financeiro.categorias force row level security;

revoke all on financeiro.categorias from public, anon, authenticated;
grant select on financeiro.categorias to authenticated;

create policy categorias_select_proprias
    on financeiro.categorias
    for select
    to authenticated
    using (user_id = (select auth.uid()));
