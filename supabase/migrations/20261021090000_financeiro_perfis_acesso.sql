-- PERFIS-1 — identidade (Supabase Auth) <-> perfil financeiro <-> dados.
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica. Validada apenas em
-- cluster PostgreSQL local descartavel (tests/test_supabase_perfis.py).
--
-- Menor adaptacao segura, sem duplicar conceitos:
-- - `public.perfil_financeiro` (Flask) continua sendo a UNICA fonte de perfis;
-- - `financeiro.perfil_acesso` registra quais usuarios do Auth podem usar quais
--   perfis (um usuario pode ter varios; nada e vinculado automaticamente);
-- - o navegador nunca le as tabelas legadas: so funcoes de leitura que validam,
--   no banco, se o perfil pedido pertence ao usuario (auth.uid()).
-- Regras preservadas do Flask (PerfilFinanceiroService):
-- - perfil inativo nao e utilizavel;
-- - linhas com perfil_financeiro_id NULL pertencem ao perfil "Pessoal".
-- Categorias de despesa sao GLOBAIS no Flask (sem perfil); por isso nao entram aqui.

create table financeiro.perfil_acesso (
    user_id              uuid        not null references auth.users (id) on delete cascade,
    perfil_financeiro_id integer     not null references public.perfil_financeiro (id) on delete cascade,
    papel                text        not null default 'TITULAR' check (papel in ('TITULAR', 'LEITOR')),
    criado_em            timestamptz not null default now(),
    primary key (user_id, perfil_financeiro_id)
);

comment on table financeiro.perfil_acesso is
    'Autorizacao explicita usuario do Auth -> perfil financeiro (PERFIS-1). Criada por administrador; o navegador so le os proprios vinculos.';

create index perfil_acesso_perfil_idx on financeiro.perfil_acesso (perfil_financeiro_id);

alter table financeiro.perfil_acesso enable row level security;
alter table financeiro.perfil_acesso force row level security;

revoke all on financeiro.perfil_acesso from public, anon, authenticated;
grant select on financeiro.perfil_acesso to authenticated;

create policy perfil_acesso_select_proprio
    on financeiro.perfil_acesso
    for select
    to authenticated
    using (user_id = (select auth.uid()));

-- Unica porta de autorizacao por perfil: toda funcao que receber um perfil vindo do
-- navegador deve passar por aqui. Exige vinculo do proprio usuario e perfil ativo.
create function financeiro.pode_acessar_perfil(p_perfil_id integer)
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
    )
$$;

create function financeiro.meus_perfis()
    returns table (id integer, nome text, tipo text, avatar text, cor text, padrao boolean, papel text)
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select p.id, p.nome::text, p.tipo::text, p.avatar::text, p.cor::text, p.padrao, a.papel
      from financeiro.perfil_acesso a
      join public.perfil_financeiro p on p.id = a.perfil_financeiro_id
     where a.user_id = (select auth.uid())
       and p.ativo
     order by p.padrao desc, p.nome
$$;

-- Fachada somente leitura do primeiro dado por perfil (base do MOBILE-CONTAS-1).
-- Sem agencia, numero de conta nem saldo: so o necessario para identificar a conta.
create function financeiro.contas_bancarias_do_perfil(p_perfil_id integer)
    returns table (id integer, nome text, instituicao text, tipo text, cor text, status text)
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;

    return query
        select c.id, c.nome::text, c.instituicao::text, c.tipo::text, c.cor_display::text, c.status::text
          from public.conta_bancaria c
         where c.perfil_financeiro_id = p_perfil_id
            or (c.perfil_financeiro_id is null
                and exists (select 1 from public.perfil_financeiro p
                             where p.id = p_perfil_id and p.nome = 'Pessoal'))
         order by c.nome;
end
$$;

-- Funcoes nascem com EXECUTE para PUBLIC: revogar e conceder so a authenticated.
revoke execute on function financeiro.pode_acessar_perfil(integer) from public, anon;
revoke execute on function financeiro.meus_perfis() from public, anon;
revoke execute on function financeiro.contas_bancarias_do_perfil(integer) from public, anon;
grant execute on function financeiro.pode_acessar_perfil(integer) to authenticated;
grant execute on function financeiro.meus_perfis() to authenticated;
grant execute on function financeiro.contas_bancarias_do_perfil(integer) to authenticated;
