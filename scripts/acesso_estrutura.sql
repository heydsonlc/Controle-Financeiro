-- FIN-MULTIUSUARIO-ACESSO-01 — entrada por convite, situacao das contas e administracao da plataforma.
--
-- GERADA por scripts/gerar_migration_acesso.py (parte fixa em scripts/acesso_estrutura.sql): nao editar o arquivo da migration
-- a mao.
--
-- Nenhum registro financeiro e alterado. O cadastro publico continua desligado no Supabase Auth; esta migration nao cria
-- usuario, nao guarda senha nem token: a identidade e a senha sao do Supabase Auth (convite e recuperacao por e-mail dele).
--   1. CONTA DA PLATAFORMA (financeiro.usuario_plataforma): ATIVA ou SUSPENSA. Sem conta ativa, nenhuma funcao do
--      aplicativo responde: a conferencia fica nas tres funcoes centrais de acesso ao perfil e nas funcoes sem perfil.
--      As contas que ja possuem perfil ficam ATIVAS nesta migration (a conta atual nao muda em nada).
--   2. CONVITE (financeiro.convite): autorizacao, registrada pelo administrador, para UM e-mail ativar a conta, com
--      validade, uso unico, revogacao e reenvio controlado. O convite nao e credencial: quem prova a identidade e o login
--      do Supabase Auth com o e-mail confirmado.
--   3. ATIVACAO (ativar_minha_conta): uma transacao, repetivel sem efeito. Confere o convite do e-mail da propria sessao,
--      ativa a conta, cria o primeiro perfil (com as categorias de cartao padrao) e o marca como padrao. Nada de outro
--      usuario e copiado; nenhuma conta bancaria ou lancamento e criado.
--   4. ADMINISTRACAO: convites, situacao das contas, suspensao e auditoria, so para o administrador da plataforma, que
--      NAO ganha acesso a dado financeiro de ninguem (nenhuma destas funcoes le tabela financeira).

-- =====================================================================================================================
-- 1. Conta da plataforma
-- =====================================================================================================================
create table financeiro.usuario_plataforma (
    user_id       uuid        primary key references auth.users (id) on delete cascade,
    situacao      text        not null default 'ATIVA' check (situacao in ('ATIVA', 'SUSPENSA')),
    origem        text        not null check (origem in ('EXISTENTE', 'CONVITE', 'ADMINISTRATIVO')),
    ativada_em    timestamptz not null default now(),
    convite_id    uuid,
    suspensa_em   timestamptz,
    suspensa_por  uuid        references auth.users (id) on delete set null,
    motivo        text,
    check ((situacao = 'SUSPENSA') = (suspensa_em is not null))
);
alter table financeiro.usuario_plataforma enable row level security;
revoke all on table financeiro.usuario_plataforma from public, anon, authenticated;
comment on table financeiro.usuario_plataforma is
    'FIN-MULTIUSUARIO-ACESSO-01: situacao da conta no aplicativo. Sem linha ATIVA, nenhuma funcao responde ao usuario.';

-- As contas que ja tem perfil (hoje, a do titular) ficam ativas: nada muda para elas.
insert into financeiro.usuario_plataforma (user_id, origem)
select distinct a.user_id, 'EXISTENTE' from financeiro.perfil_acesso a
on conflict (user_id) do nothing;
insert into financeiro.usuario_plataforma (user_id, origem)
select a.user_id, 'EXISTENTE' from financeiro.administrador_plataforma a
on conflict (user_id) do nothing;

create function financeiro.conta_ativa()
    returns boolean
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select exists (select 1 from financeiro.usuario_plataforma u where u.user_id = (select auth.uid()) and u.situacao = 'ATIVA')
$$;

-- Para as funcoes que nao recebem perfil: recusa unica, que nao diz se a conta nunca foi ativada ou esta suspensa.
create function financeiro.exigir_conta_ativa()
    returns void
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
begin
    if not financeiro.conta_ativa() then
        raise exception 'Conta sem acesso liberado' using errcode = '42501', hint = 'CONTA_INATIVA';
    end if;
end
$$;
revoke execute on function financeiro.conta_ativa() from public, anon, authenticated;
revoke execute on function financeiro.exigir_conta_ativa() from public, anon, authenticated;

-- Vinculo gravado administrativamente (carga, cenarios, vinculo do titular): a conta passa a existir como ativa. O
-- cadastro pelo aplicativo (criar_perfil) so chega aqui com a conta ja ativa, e uma conta SUSPENSA nunca e reativada por aqui.
create function financeiro.conta_no_vinculo()
    returns trigger
    language plpgsql
    security definer
    set search_path = ''
as $$
begin
    insert into financeiro.usuario_plataforma (user_id, origem) values (new.user_id, 'ADMINISTRATIVO') on conflict (user_id) do nothing;
    return new;
end
$$;
revoke execute on function financeiro.conta_no_vinculo() from public, anon, authenticated;
create trigger perfil_acesso_conta after insert on financeiro.perfil_acesso
    for each row execute function financeiro.conta_no_vinculo();

-- As tres funcoes centrais de acesso ao perfil passam a exigir a conta ativa (texto de 20261231090000 + a conferencia).
create or replace function financeiro.pode_acessar_perfil(p_perfil_id integer)
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
    ) and financeiro.conta_ativa()
$$;

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
    ) and financeiro.conta_ativa()
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
    ) and financeiro.conta_ativa()
$$;

create or replace function financeiro.meus_perfis()
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
       and financeiro.conta_ativa()
     order by p.padrao desc, p.nome
$$;

-- Funcoes sem perfil escritas em SQL (as em plpgsql recebem a conferencia na secao gerada, no fim): texto vigente + conta ativa.
create or replace function financeiro.perfis_para_configuracao()
    returns table (id integer, nome text, tipo text, documento text, avatar text, logo_url text, cor text, ativo boolean, padrao boolean, papel text, pode_gerir boolean)
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
       and financeiro.conta_ativa()
     order by p.ativo desc, p.nome
$$;

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
       and financeiro.conta_ativa()
     order by c.nome
$$;

create or replace function financeiro.situacao_catalogo_categorias()
    returns jsonb
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select jsonb_build_object(
        'escritor', coalesce((select c.escritor from financeiro.catalogo_categorias c), 'FLASK'),
        'gestor', financeiro.conta_ativa() and exists (select 1 from financeiro.gestor_catalogo g where g.user_id = (select auth.uid())))
$$;

create or replace function financeiro.sou_administrador_plataforma()
    returns boolean
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select financeiro.conta_ativa() and exists (select 1 from financeiro.administrador_plataforma a where a.user_id = (select auth.uid()))
$$;

create or replace function financeiro.e_administrador_plataforma()
    returns boolean
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select financeiro.conta_ativa() and exists (select 1 from financeiro.administrador_plataforma a where a.user_id = (select auth.uid()))
$$;

-- Operacao administrativa (operador, pelo banco; nunca pelo navegador): define a situacao de uma conta. E o caminho de
-- recuperacao se o unico administrador perder o acesso, e o usado pelos cenarios de teste.
create function financeiro.definir_conta_plataforma(p_user_id uuid, p_situacao text, p_por text, p_motivo text)
    returns text
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
begin
    if btrim(coalesce(p_por, '')) = '' or btrim(coalesce(p_motivo, '')) = '' then
        raise exception 'Responsavel e motivo sao obrigatorios' using errcode = '22023';
    end if;
    if p_situacao not in ('ATIVA', 'SUSPENSA') then
        raise exception 'Situacao invalida' using errcode = '22023';
    end if;
    if not exists (select 1 from auth.users u where u.id = p_user_id) then
        raise exception 'Usuario nao encontrado' using errcode = '22023';
    end if;
    insert into financeiro.usuario_plataforma (user_id, origem, situacao, suspensa_em, motivo)
    values (p_user_id, 'ADMINISTRATIVO', p_situacao, case when p_situacao = 'SUSPENSA' then now() end, case when p_situacao = 'SUSPENSA' then left(p_motivo, 200) end)
    on conflict (user_id) do update
       set situacao = excluded.situacao, suspensa_em = excluded.suspensa_em, suspensa_por = null, motivo = excluded.motivo;
    insert into financeiro.auditoria_acesso (ator, acao, alvo, detalhe)
    values (null, 'CONTA_DEFINIDA_PELO_OPERADOR', p_user_id::text, jsonb_build_object('situacao', p_situacao, 'por', p_por, 'motivo', p_motivo));
    return p_user_id::text || ': ' || p_situacao;
end
$$;
revoke execute on function financeiro.definir_conta_plataforma(uuid, text, text, text) from public, anon, authenticated;

-- =====================================================================================================================
-- 2. Auditoria de acesso (sem dado financeiro)
-- =====================================================================================================================
create table financeiro.auditoria_acesso (
    id      bigint      generated always as identity primary key,
    quando  timestamptz not null default now(),
    ator    uuid        references auth.users (id) on delete set null,
    acao    text        not null,
    alvo    text,
    detalhe jsonb       not null default '{}'::jsonb
);
create index auditoria_acesso_quando_idx on financeiro.auditoria_acesso (quando desc);
alter table financeiro.auditoria_acesso enable row level security;
revoke all on table financeiro.auditoria_acesso from public, anon, authenticated;

create function financeiro.auditar_acesso(p_acao text, p_alvo text, p_detalhe jsonb)
    returns void
    language sql
    volatile
    security definer
    set search_path = ''
as $$
    insert into financeiro.auditoria_acesso (ator, acao, alvo, detalhe) values ((select auth.uid()), p_acao, p_alvo, coalesce(p_detalhe, '{}'::jsonb))
$$;
revoke execute on function financeiro.auditar_acesso(text, text, jsonb) from public, anon, authenticated;

create function financeiro.exigir_administrador()
    returns void
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
begin
    if not financeiro.conta_ativa() or not exists (select 1 from financeiro.administrador_plataforma a where a.user_id = (select auth.uid())) then
        raise exception 'Restrito ao administrador da plataforma' using errcode = '42501', hint = 'SO_ADMINISTRADOR';
    end if;
end
$$;
revoke execute on function financeiro.exigir_administrador() from public, anon, authenticated;

-- =====================================================================================================================
-- 3. Convites
-- =====================================================================================================================
create table financeiro.convite (
    id              uuid        primary key default gen_random_uuid(),
    email           text        not null check (email = lower(btrim(email)) and email ~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$' and length(email) <= 254),
    situacao        text        not null default 'PENDENTE' check (situacao in ('PENDENTE', 'USADO', 'REVOGADO')),
    criado_em       timestamptz not null default now(),
    criado_por      uuid        references auth.users (id) on delete set null,
    expira_em       timestamptz not null,
    envios          integer     not null default 1 check (envios between 1 and 5),
    ultimo_envio_em timestamptz not null default now(),
    usado_em        timestamptz,
    usado_por       uuid        references auth.users (id) on delete set null,
    revogado_em     timestamptz,
    revogado_por    uuid        references auth.users (id) on delete set null,
    observacao      text        check (observacao is null or length(observacao) <= 200),
    check ((situacao = 'USADO') = (usado_em is not null)),
    check ((situacao = 'REVOGADO') = (revogado_em is not null))
);
-- um convite pendente por e-mail
create unique index convite_pendente_por_email_uq on financeiro.convite (email) where situacao = 'PENDENTE';
alter table financeiro.convite enable row level security;
revoke all on table financeiro.convite from public, anon, authenticated;
alter table financeiro.usuario_plataforma add constraint usuario_plataforma_convite_fk foreign key (convite_id) references financeiro.convite (id) on delete set null;
comment on table financeiro.convite is
    'FIN-MULTIUSUARIO-ACESSO-01: autorizacao para um e-mail ativar a conta (uso unico, com validade). Nao e credencial nem guarda token.';

create function financeiro.convite_em_json(c financeiro.convite)
    returns jsonb
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select jsonb_build_object('id', c.id, 'email', c.email,
                              'situacao', case when c.situacao = 'PENDENTE' and c.expira_em <= now() then 'EXPIRADO' else c.situacao end,
                              'criado_em', c.criado_em, 'expira_em', c.expira_em, 'envios', c.envios, 'ultimo_envio_em', c.ultimo_envio_em,
                              'usado_em', c.usado_em, 'revogado_em', c.revogado_em, 'observacao', c.observacao,
                              'conta_no_auth', exists (select 1 from auth.users u where lower(u.email) = c.email))
$$;
revoke execute on function financeiro.convite_em_json(financeiro.convite) from public, anon, authenticated;

-- p_dados: email, validade_dias (1 a 30; padrao 7), observacao.
create function financeiro.criar_convite(p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_email text := lower(btrim(coalesce(p_dados ->> 'email', '')));
    v_dias  integer;
    v_c     financeiro.convite;
begin
    perform financeiro.exigir_administrador();
    begin
        v_dias := coalesce((p_dados ->> 'validade_dias')::integer, 7);
    exception when others then
        raise exception 'Validade invalida' using errcode = '22023';
    end;
    if v_email !~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$' or length(v_email) > 254 then
        raise exception 'E-mail invalido' using errcode = '22023';
    end if;
    if v_dias not between 1 and 30 then
        raise exception 'A validade do convite e de 1 a 30 dias' using errcode = '22023';
    end if;
    -- conta que ja usa o aplicativo nao recebe convite (o administrador ve isto; o usuario comum nunca)
    if exists (select 1 from financeiro.usuario_plataforma u join auth.users a on a.id = u.user_id where lower(a.email) = v_email) then
        raise exception 'Este e-mail ja tem conta no aplicativo' using errcode = '22023', hint = 'CONTA_EXISTENTE';
    end if;
    perform pg_advisory_xact_lock(hashtextextended('financeiro.convite:' || v_email, 20270102));
    -- o pendente ja vencido deixa de valer; um pendente ainda valido impede outro
    update financeiro.convite set situacao = 'REVOGADO', revogado_em = now(), revogado_por = (select auth.uid())
     where email = v_email and situacao = 'PENDENTE' and expira_em <= now();
    if exists (select 1 from financeiro.convite c where c.email = v_email and c.situacao = 'PENDENTE') then
        raise exception 'Ja existe convite pendente para este e-mail' using errcode = '22023', hint = 'CONVITE_PENDENTE';
    end if;
    insert into financeiro.convite (email, criado_por, expira_em, observacao)
    values (v_email, (select auth.uid()), now() + make_interval(days => v_dias), nullif(left(btrim(coalesce(p_dados ->> 'observacao', '')), 200), ''))
    returning * into v_c;
    perform financeiro.auditar_acesso('CONVITE_CRIADO', v_c.id::text, jsonb_build_object('validade_dias', v_dias));
    return financeiro.convite_em_json(v_c);
end
$$;

create function financeiro.revogar_convite(p_convite_id uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_c financeiro.convite;
begin
    perform financeiro.exigir_administrador();
    update financeiro.convite set situacao = 'REVOGADO', revogado_em = now(), revogado_por = (select auth.uid())
     where id = p_convite_id and situacao = 'PENDENTE'
    returning * into v_c;
    if not found then
        raise exception 'Convite nao encontrado ou ja encerrado' using errcode = '22023';
    end if;
    perform financeiro.auditar_acesso('CONVITE_REVOGADO', v_c.id::text, '{}'::jsonb);
    return financeiro.convite_em_json(v_c);
end
$$;

-- Reenvio controlado: no maximo 5 envios por convite e um a cada 10 minutos; renova a validade (p_validade_dias, 1 a 30).
-- O e-mail em si e enviado pelo Supabase Auth; aqui fica o registro e a nova validade.
create function financeiro.registrar_reenvio_convite(p_convite_id uuid, p_validade_dias integer)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_c    financeiro.convite;
    v_dias integer := coalesce(p_validade_dias, 7);
begin
    perform financeiro.exigir_administrador();
    if v_dias not between 1 and 30 then
        raise exception 'A validade do convite e de 1 a 30 dias' using errcode = '22023';
    end if;
    select * into v_c from financeiro.convite c where c.id = p_convite_id for update;
    if not found or v_c.situacao <> 'PENDENTE' then
        raise exception 'Convite nao encontrado ou ja encerrado' using errcode = '22023';
    end if;
    if v_c.envios >= 5 then
        raise exception 'Limite de envios deste convite atingido: revogue-o e crie outro' using errcode = '22023', hint = 'LIMITE_DE_ENVIOS';
    end if;
    if v_c.ultimo_envio_em > now() - interval '10 minutes' then
        raise exception 'Aguarde 10 minutos entre um envio e outro' using errcode = '22023', hint = 'ENVIO_RECENTE';
    end if;
    update financeiro.convite set envios = envios + 1, ultimo_envio_em = now(), expira_em = now() + make_interval(days => v_dias)
     where id = p_convite_id returning * into v_c;
    perform financeiro.auditar_acesso('CONVITE_REENVIADO', v_c.id::text, jsonb_build_object('envios', v_c.envios, 'validade_dias', v_dias));
    return financeiro.convite_em_json(v_c);
end
$$;

create function financeiro.convites_tela()
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
begin
    perform financeiro.exigir_administrador();
    return coalesce((select jsonb_agg(financeiro.convite_em_json(c) order by c.criado_em desc) from financeiro.convite c), '[]'::jsonb);
end
$$;

-- =====================================================================================================================
-- 4. Situacao da propria conta e ativacao
-- =====================================================================================================================
-- O que a tela precisa para decidir: entrar no aplicativo, primeiro acesso, ou aviso. So fala da conta de quem pergunta.
create function financeiro.situacao_da_minha_conta()
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_usuario uuid := (select auth.uid());
    v_u       financeiro.usuario_plataforma;
    v_email   text;
    v_conf    boolean;
    v_c       financeiro.convite;
begin
    if v_usuario is null then
        raise exception 'Sessao obrigatoria' using errcode = '42501';
    end if;
    select * into v_u from financeiro.usuario_plataforma u where u.user_id = v_usuario;
    if found then
        return jsonb_build_object(
            'situacao', v_u.situacao,
            'administrador', v_u.situacao = 'ATIVA' and exists (select 1 from financeiro.administrador_plataforma a where a.user_id = v_usuario),
            'perfis', case when v_u.situacao = 'ATIVA' then (select count(*) from financeiro.perfil_acesso a join public.perfil_financeiro p on p.id = a.perfil_financeiro_id
                                                              where a.user_id = v_usuario and p.ativo) else 0 end);
    end if;
    select lower(a.email), a.email_confirmed_at is not null into v_email, v_conf from auth.users a where a.id = v_usuario;
    select * into v_c from financeiro.convite c where c.email = v_email and c.situacao = 'PENDENTE' order by c.criado_em desc limit 1;
    return jsonb_build_object('situacao', case when not found then 'SEM_CONVITE' when v_c.expira_em <= now() then 'CONVITE_EXPIRADO'
                                               when not coalesce(v_conf, false) then 'EMAIL_NAO_CONFIRMADO' else 'CONVIDADA' end,
                              'administrador', false, 'perfis', 0,
                              'convite_expira_em', case when found then v_c.expira_em end);
end
$$;

-- Ativacao da propria conta: uma transacao, repetivel sem efeito. p_dados: nome (do primeiro perfil), tipo (PESSOAL|EMPRESA|OUTRO).
-- A identidade e a da sessao (auth.uid()) e o e-mail e o que o Supabase Auth tem para ela, ja confirmado: nada do que o
-- usuario envia decide quem ele e nem qual convite vale.
create function financeiro.ativar_minha_conta(p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_usuario uuid := (select auth.uid());
    v_u       financeiro.usuario_plataforma;
    v_email   text;
    v_conf    boolean;
    v_c       financeiro.convite;
    v_perfil  jsonb;
begin
    if v_usuario is null then
        raise exception 'Sessao obrigatoria' using errcode = '42501';
    end if;
    perform pg_advisory_xact_lock(hashtextextended('financeiro.ativacao:' || v_usuario::text, 20270102));
    select * into v_u from financeiro.usuario_plataforma u where u.user_id = v_usuario;
    if found then
        if v_u.situacao <> 'ATIVA' then
            raise exception 'Conta sem acesso liberado' using errcode = '42501', hint = 'CONTA_INATIVA';
        end if;
        -- ja ativada (repeticao, segundo toque, retomada): devolve o estado, sem criar nada
        return jsonb_build_object('ativada', true, 'repetida', true,
                                  'perfis', (select count(*) from financeiro.perfil_acesso a where a.user_id = v_usuario));
    end if;
    select lower(a.email), a.email_confirmed_at is not null into v_email, v_conf from auth.users a where a.id = v_usuario;
    if not coalesce(v_conf, false) then
        raise exception 'Confirme o seu e-mail pelo link recebido antes de ativar a conta' using errcode = '42501', hint = 'EMAIL_NAO_CONFIRMADO';
    end if;
    select * into v_c from financeiro.convite c where c.email = v_email and c.situacao = 'PENDENTE' order by c.criado_em desc limit 1 for update;
    if not found then
        raise exception 'Conta sem acesso liberado' using errcode = '42501', hint = 'SEM_CONVITE';
    end if;
    if v_c.expira_em <= now() then
        raise exception 'O convite expirou. Peca um novo ao administrador.' using errcode = '42501', hint = 'CONVITE_EXPIRADO';
    end if;
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' or btrim(coalesce(p_dados ->> 'nome', '')) = '' then
        raise exception 'Informe o nome do seu primeiro perfil financeiro' using errcode = '22023';
    end if;

    insert into financeiro.usuario_plataforma (user_id, origem, convite_id) values (v_usuario, 'CONVITE', v_c.id);
    update financeiro.convite set situacao = 'USADO', usado_em = now(), usado_por = v_usuario where id = v_c.id;
    -- primeiro perfil (dono = o proprio usuario; ja com as categorias de cartao padrao) e padrao dele
    v_perfil := financeiro.criar_perfil(jsonb_build_object('nome', p_dados ->> 'nome', 'tipo', coalesce(p_dados ->> 'tipo', 'PESSOAL'), 'padrao', true));
    insert into financeiro.preferencia_usuario (user_id) values (v_usuario) on conflict (user_id) do nothing;
    perform financeiro.auditar_acesso('CONTA_ATIVADA', v_usuario::text, jsonb_build_object('convite', v_c.id, 'perfil', v_perfil -> 'id'));
    return jsonb_build_object('ativada', true, 'repetida', false, 'perfil', v_perfil, 'perfis', 1);
end
$$;

-- =====================================================================================================================
-- 5. Administracao das contas
-- =====================================================================================================================
-- Situacao de ativacao: e-mail, situacao, datas e quantidade de perfis. Nenhum dado financeiro.
create function financeiro.usuarios_tela()
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
begin
    perform financeiro.exigir_administrador();
    return coalesce((
        select jsonb_agg(jsonb_build_object(
                   'user_id', u.user_id, 'email', a.email, 'situacao', u.situacao, 'origem', u.origem, 'ativada_em', u.ativada_em,
                   'suspensa_em', u.suspensa_em, 'motivo', u.motivo,
                   'administrador', exists (select 1 from financeiro.administrador_plataforma x where x.user_id = u.user_id),
                   'perfis', (select count(*) from public.perfil_financeiro p where p.user_id = u.user_id),
                   'eu', u.user_id = (select auth.uid()))
               order by a.email)
          from financeiro.usuario_plataforma u join auth.users a on a.id = u.user_id), '[]'::jsonb);
end
$$;

create function financeiro.suspender_usuario(p_user_id uuid, p_motivo text)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_motivo text := btrim(coalesce(p_motivo, ''));
begin
    perform financeiro.exigir_administrador();
    if p_user_id = (select auth.uid()) then
        raise exception 'O administrador nao suspende a propria conta' using errcode = '22023';
    end if;
    if exists (select 1 from financeiro.administrador_plataforma a where a.user_id = p_user_id) then
        raise exception 'Retire antes a administracao desta conta' using errcode = '22023';
    end if;
    if v_motivo = '' or length(v_motivo) > 200 then
        raise exception 'Informe o motivo da suspensao (ate 200 caracteres)' using errcode = '22023';
    end if;
    update financeiro.usuario_plataforma set situacao = 'SUSPENSA', suspensa_em = now(), suspensa_por = (select auth.uid()), motivo = v_motivo
     where user_id = p_user_id and situacao = 'ATIVA';
    if not found then
        raise exception 'Conta nao encontrada ou ja suspensa' using errcode = '22023';
    end if;
    perform financeiro.auditar_acesso('CONTA_SUSPENSA', p_user_id::text, jsonb_build_object('motivo', v_motivo));
    return jsonb_build_object('user_id', p_user_id, 'situacao', 'SUSPENSA');
end
$$;

create function financeiro.reativar_usuario(p_user_id uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
begin
    perform financeiro.exigir_administrador();
    update financeiro.usuario_plataforma set situacao = 'ATIVA', suspensa_em = null, suspensa_por = null, motivo = null
     where user_id = p_user_id and situacao = 'SUSPENSA';
    if not found then
        raise exception 'Conta nao encontrada ou nao suspensa' using errcode = '22023';
    end if;
    perform financeiro.auditar_acesso('CONTA_REATIVADA', p_user_id::text, '{}'::jsonb);
    return jsonb_build_object('user_id', p_user_id, 'situacao', 'ATIVA');
end
$$;

create function financeiro.auditoria_acesso_tela(p_limite integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
begin
    perform financeiro.exigir_administrador();
    return coalesce((
        select jsonb_agg(to_jsonb(x) order by x.quando desc)
          from (select l.quando, l.acao, l.alvo, l.detalhe, (select a.email from auth.users a where a.id = l.ator) ator
                  from financeiro.auditoria_acesso l order by l.quando desc limit least(greatest(coalesce(p_limite, 50), 1), 200)) x), '[]'::jsonb);
end
$$;

revoke execute on function financeiro.criar_convite(jsonb) from public, anon;
revoke execute on function financeiro.revogar_convite(uuid) from public, anon;
revoke execute on function financeiro.registrar_reenvio_convite(uuid, integer) from public, anon;
revoke execute on function financeiro.convites_tela() from public, anon;
revoke execute on function financeiro.situacao_da_minha_conta() from public, anon;
revoke execute on function financeiro.ativar_minha_conta(jsonb) from public, anon;
revoke execute on function financeiro.usuarios_tela() from public, anon;
revoke execute on function financeiro.suspender_usuario(uuid, text) from public, anon;
revoke execute on function financeiro.reativar_usuario(uuid) from public, anon;
revoke execute on function financeiro.auditoria_acesso_tela(integer) from public, anon;
grant execute on function financeiro.criar_convite(jsonb) to authenticated;
grant execute on function financeiro.revogar_convite(uuid) to authenticated;
grant execute on function financeiro.registrar_reenvio_convite(uuid, integer) to authenticated;
grant execute on function financeiro.convites_tela() to authenticated;
grant execute on function financeiro.situacao_da_minha_conta() to authenticated;
grant execute on function financeiro.ativar_minha_conta(jsonb) to authenticated;
grant execute on function financeiro.usuarios_tela() to authenticated;
grant execute on function financeiro.suspender_usuario(uuid, text) to authenticated;
grant execute on function financeiro.reativar_usuario(uuid) to authenticated;
grant execute on function financeiro.auditoria_acesso_tela(integer) to authenticated;
