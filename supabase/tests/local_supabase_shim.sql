-- Reproducao minima, para testes locais, dos objetos que o Supabase ja fornece
-- (roles da Data API, schema auth, auth.uid()). Usado SOMENTE no cluster
-- PostgreSQL descartavel dos testes. Nunca aplicar em um projeto Supabase: la
-- esses objetos ja existem e sao gerenciados pela plataforma.
--
-- Semantica espelhada do Supabase:
-- - PostgREST conecta como `authenticator` e troca para `anon` ou `authenticated`
--   conforme o claim `role` do JWT;
-- - os claims ficam em `request.jwt.claims`; auth.uid() le o `sub`.
-- - o Supabase concede ALL em tabelas novas do schema public para anon e
--   authenticated (default privileges). Reproduzido aqui de proposito, para que
--   os testes provem que o schema `financeiro` nao herda esse comportamento.

create role anon nologin noinherit;
create role authenticated nologin noinherit;
create role service_role nologin noinherit bypassrls;
create role authenticator login noinherit;
grant anon, authenticated, service_role to authenticator;

create schema auth;
grant usage on schema auth to anon, authenticated, service_role;

create table auth.users (
    id    uuid primary key,
    email text unique not null
);

create function auth.uid() returns uuid
    language sql stable
as $$
    select nullif(
        coalesce(
            current_setting('request.jwt.claim.sub', true),
            current_setting('request.jwt.claims', true)::jsonb ->> 'sub'
        ),
        ''
    )::uuid
$$;

create function auth.role() returns text
    language sql stable
as $$
    select coalesce(
        current_setting('request.jwt.claim.role', true),
        current_setting('request.jwt.claims', true)::jsonb ->> 'role'
    )
$$;

grant execute on function auth.uid() to anon, authenticated, service_role;
grant execute on function auth.role() to anon, authenticated, service_role;

grant usage on schema public to anon, authenticated, service_role;
alter default privileges in schema public grant all on tables to anon, authenticated, service_role;
