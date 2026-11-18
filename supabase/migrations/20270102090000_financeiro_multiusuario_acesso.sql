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

-- =====================================================================================================================
-- 6. Funcoes sem perfil (22) e a guarda do catalogo padrao: definicao vigente + a exigencia de conta ativa como primeira instrucao (nenhuma outra
--    linha muda). As funcoes COM perfil ja passam pelas funcoes centrais de acesso, que exigem a conta ativa (secao 1).
-- =====================================================================================================================
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
    perform financeiro.exigir_conta_ativa();  -- FIN-MULTIUSUARIO-ACESSO-01
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
    perform financeiro.exigir_conta_ativa();  -- FIN-MULTIUSUARIO-ACESSO-01
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
    perform financeiro.exigir_conta_ativa();  -- FIN-MULTIUSUARIO-ACESSO-01
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
    perform financeiro.exigir_conta_ativa();  -- FIN-MULTIUSUARIO-ACESSO-01
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
    perform financeiro.exigir_conta_ativa();  -- FIN-MULTIUSUARIO-ACESSO-01
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
    perform financeiro.exigir_conta_ativa();  -- FIN-MULTIUSUARIO-ACESSO-01
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
    perform financeiro.exigir_conta_ativa();  -- FIN-MULTIUSUARIO-ACESSO-01
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
    perform financeiro.exigir_conta_ativa();  -- FIN-MULTIUSUARIO-ACESSO-01
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
    perform financeiro.exigir_conta_ativa();  -- FIN-MULTIUSUARIO-ACESSO-01
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
    perform financeiro.exigir_conta_ativa();  -- FIN-MULTIUSUARIO-ACESSO-01
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
    perform financeiro.exigir_conta_ativa();  -- FIN-MULTIUSUARIO-ACESSO-01
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
    perform financeiro.exigir_conta_ativa();  -- FIN-MULTIUSUARIO-ACESSO-01
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
    perform financeiro.exigir_conta_ativa();  -- FIN-MULTIUSUARIO-ACESSO-01
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
    perform financeiro.exigir_conta_ativa();  -- FIN-MULTIUSUARIO-ACESSO-01
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
    perform financeiro.exigir_conta_ativa();  -- FIN-MULTIUSUARIO-ACESSO-01
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
    perform financeiro.exigir_conta_ativa();  -- FIN-MULTIUSUARIO-ACESSO-01
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
    perform financeiro.exigir_conta_ativa();  -- FIN-MULTIUSUARIO-ACESSO-01
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
    perform financeiro.exigir_conta_ativa();  -- FIN-MULTIUSUARIO-ACESSO-01
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
    perform financeiro.exigir_conta_ativa();  -- FIN-MULTIUSUARIO-ACESSO-01
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
    perform financeiro.exigir_conta_ativa();  -- FIN-MULTIUSUARIO-ACESSO-01
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
    perform financeiro.exigir_conta_ativa();  -- FIN-MULTIUSUARIO-ACESSO-01
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
    perform financeiro.exigir_conta_ativa();  -- FIN-MULTIUSUARIO-ACESSO-01
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
    perform financeiro.exigir_conta_ativa();  -- FIN-MULTIUSUARIO-ACESSO-01
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
