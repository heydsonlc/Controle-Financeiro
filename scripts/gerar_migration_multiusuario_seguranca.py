"""Gera a migration 20261231090000 (FIN-MULTIUSUARIO-SEGURANCA-01) a partir do texto VIGENTE de cada funcao.

A parte estrutural (dono do perfil, nome unico por dono, perfil padrao por usuario, guarda dos registros sem perfil,
administrador da plataforma) e escrita aqui a mao. As funcoes que decidiam a posse pelo NOME do perfil ("Pessoal") sao
reescritas por substituicoes conferidas sobre a definicao vigente (lida de um PostgreSQL local descartavel com as
migrations anteriores aplicadas): nenhuma regra financeira e tocada, so a forma de reconhecer o perfil que guarda registros sem
perfil. Nenhum dado real, conexao remota ou credencial.

    python scripts/gerar_migration_multiusuario_seguranca.py              # grava a migration
    python scripts/gerar_migration_multiusuario_seguranca.py --verificar  # so compara com o arquivo versionado
"""
import argparse
import re
import sys
from pathlib import Path

_args = argparse.ArgumentParser(description=__doc__.splitlines()[0])
_args.add_argument('--verificar', action='store_true', help='nao grava: falha se a saida difere do arquivo versionado')
ARGS = _args.parse_args()
RAIZ = Path(__file__).resolve().parents[1]
MIG = RAIZ / 'supabase' / 'migrations'
VERSAO = '20261231090000'
SAIDA = MIG / f'{VERSAO}_financeiro_multiusuario_seguranca.sql'
ANTERIORES = sorted(p for p in MIG.glob('*.sql') if p.name < VERSAO)


def carregar_vigentes():
    """Definicao VIGENTE de cada funcao do esquema financeiro: um PostgreSQL local descartavel com todas as migrations
    anteriores aplicadas (ha funcoes renomeadas e redefinidas ao longo das migrations: o texto dos arquivos nao basta)."""
    import tempfile
    sys.path.insert(0, str(RAIZ))
    from tests.supabase_local import ClusterLocal, encontrar_pg_bin
    pg = encontrar_pg_bin()
    assert pg, 'binarios do PostgreSQL nao encontrados'
    with tempfile.TemporaryDirectory(prefix='cf-gerador-', ignore_cleanup_errors=True) as tmp, ClusterLocal(pg, Path(tmp)) as c:
        c.aplicar_shim()
        c.criar_tabelas_legadas()
        conn = c.conectar()
        try:
            with conn.cursor() as cur:
                for migration in ANTERIORES:
                    cur.execute(migration.read_text(encoding='utf-8'))
                cur.execute("""select p.proname, pg_get_functiondef(p.oid) from pg_proc p join pg_namespace n on n.oid = p.pronamespace
                                where n.nspname = 'financeiro' and p.prokind = 'f' order by 1""")
                linhas = cur.fetchall()
                cur.execute("""select 'alter table public.perfil_financeiro add constraint ' || quote_ident(c.conname) || ' ' || pg_get_constraintdef(c.oid) || ';'
                                 from pg_constraint c where c.conrelid = 'public.perfil_financeiro'::regclass and c.contype = 'u'
                                  and (select array_agg(a.attname::text) from pg_attribute a where a.attrelid = c.conrelid and a.attnum = any(c.conkey)) = array['nome']
                               union all
                               select pg_get_indexdef(i.indexrelid) || ';' from pg_index i
                                where i.indrelid = 'public.perfil_financeiro'::regclass and i.indisunique and not i.indisprimary and i.indnatts = 1
                                  and (select a.attname from pg_attribute a where a.attrelid = i.indrelid and a.attnum = i.indkey[0]) = 'nome'
                                  and not exists (select 1 from pg_constraint c where c.conindid = i.indexrelid)""")
                unicidade = [r[0] for r in cur.fetchall()]
        finally:
            conn.close()
    defs = {}
    for nome, texto in linhas:
        defs.setdefault(nome, []).append(texto.replace('\r\n', '\n').rstrip() + ';')
    return defs, unicidade


VIGENTES, UNICIDADE_DO_NOME = carregar_vigentes()
REVERSAO = RAIZ / 'supabase' / 'reversao' / f'{VERSAO}_multiusuario_seguranca_anterior.sql'


def vigente(nome):
    assert len(VIGENTES.get(nome, [])) == 1, f'{nome}: {len(VIGENTES.get(nome, []))} definicoes'
    return f'{ANTERIORES[-1].name[:14]} (definicao vigente)', VIGENTES[nome][0]


def como_replace(b):
    return re.sub(r'^create function', 'create or replace function', b)


# ---------------------------------------------------------------------------------------------------------------------
# Substituicoes: o perfil que guarda os registros sem perfil deixa de ser "o que se chama Pessoal"
# ---------------------------------------------------------------------------------------------------------------------
E_GUARDA = re.compile(r"exists\s*\(\s*select 1 from public\.perfil_financeiro p\s+where p\.id = (\w+) and p\.nome = 'Pessoal'\)")
ID_GUARDA = re.compile(r"\(select p\.id from public\.perfil_financeiro p where p\.nome = 'Pessoal'(?: and p\.ativo)? order by p\.id limit 1\)")
POR_NOME = [  # funcoes reescritas so pelas duas substituicoes acima
    'compras_da_fatura', 'contas_bancarias_do_perfil', 'contas_do_mes', 'estornar_pagamento_fatura', 'executado_fatura', 'faturas_do_mes',
    'fontes_de_receita', 'lancamentos_da_fatura', 'limpar_importacoes_cartao', 'mes_pode_estar_incompleto', 'plano_recorrencia',
    'previa_reclassificacao_categorias', 'previsto_fatura', 'reativar_competencia_interno', 'recalcular_fatura', 'recebido_da_previsao',
    'receitas_do_mes', 'recorrencias_do_perfil', 'referencias_categoria', 'reverter_reclassificacao_categorias',
]
gerado, relatorio = [], []
for nome in POR_NOME:
    origem, texto = vigente(nome)
    novo, n1 = E_GUARDA.subn(lambda m: f'financeiro.guarda_legado({m.group(1)})', texto)
    novo, n2 = ID_GUARDA.subn('financeiro.perfil_guarda_legado()', novo)
    assert n1 + n2 >= 1, f'{nome}: nenhuma substituicao'
    assert "'Pessoal'" not in re.sub(r'--[^\n]*', '', novo), f'{nome}: ainda cita o nome Pessoal no codigo'
    gerado.append(f'-- {nome}: texto de {origem} com a posse dos registros sem perfil pela guarda explicita ({n1 + n2} trecho(s)).\n' + como_replace(novo))
    relatorio.append((nome, origem, n1 + n2))

# Ordem das recusas: autorizacao (perfil e registro) antes da validacao dos dados.
for nome in ('anular_abastecimento', 'corrigir_abastecimento'):
    origem, texto = vigente(nome)
    a = '    v_motivo text := financeiro.mob_exigir_motivo(p_dados);\n'
    b = '    a := financeiro.mob_abastecimento(p_perfil_id, p_id);\n'
    assert texto.count(a) == 1 and texto.count(b) == 1, nome
    novo = texto.replace(a, '    v_motivo text;\n').replace(b, b + '    v_motivo := financeiro.mob_exigir_motivo(p_dados);  -- so depois da autorizacao\n')
    gerado.append(f'-- {nome}: texto de {origem}; o motivo so e validado depois de conferidos o perfil e o abastecimento.\n' + como_replace(novo))
    relatorio.append((nome, origem, 1))

ESTRUTURA = r"""-- FIN-MULTIUSUARIO-SEGURANCA-01 — propriedade dos perfis, isolamento entre usuarios e referencias globais protegidas.
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
"""

origem_paga, paga = vigente('criar_despesa_paga')
a = "begin\n    if p_chave is null then\n        raise exception 'Chave da operacao obrigatoria' using errcode = '22023';\n"
assert paga.count(a) == 1
paga = paga.replace(a, "begin\n    if not financeiro.pode_gerir_perfil(p_perfil_id) then  -- antes de qualquer validacao dos dados\n"
                       "        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';\n    end if;\n" + a[len('begin\n'):])

FUNCOES = ("""
-- =====================================================================================================================
-- 6. Funcoes que decidiam a posse pelo nome do perfil: agora pela guarda explicita (nenhuma regra financeira muda)
-- =====================================================================================================================
""" + '\n\n'.join(gerado) + '\n')

texto = ESTRUTURA + como_replace(paga) + '\n' + FUNCOES

# ---------------------------------------------------------------------------------------------------------------------
# Reversao: as funcoes voltam a definicao anterior (texto exato) e a estrutura nova e retirada
# ---------------------------------------------------------------------------------------------------------------------
SUBSTITUIDAS = sorted(set(POR_NOME) | {'anular_abastecimento', 'corrigir_abastecimento', 'criar_despesa_paga', 'pode_gerir_perfil', 'gere_perfil',
                                       'pertence_ao_perfil', 'criar_perfil', 'atualizar_perfil', 'aplicar_perfil_padrao', 'definir_perfil_padrao',
                                       'reativar_perfil', 'perfil_do_consorcio', 'idx_exigir_acesso'})
assert UNICIDADE_DO_NOME, 'unicidade global do nome nao encontrada no estado anterior'
reversao = f"""-- FIN-MULTIUSUARIO-SEGURANCA-01 — reversao da migration {VERSAO}.
--
-- GERADA por scripts/gerar_migration_multiusuario_seguranca.py: nao editar a mao.
-- NAO aplicar no Supabase remoto sem autorizacao especifica. Antes: volte o frontend ao deploy anterior e desfaca a
-- regularizacao dos itens sem perfil (scripts/regularizar_itens_sem_perfil.py reverter). Nenhum registro financeiro e
-- alterado: voltam as {len(SUBSTITUIDAS)} funcoes ao texto anterior e saem a coluna de dono, os indices, os gatilhos, a guarda e o
-- administrador da plataforma. Recusada quando a volta nao e segura (a regra antiga decidia a posse pelo nome do perfil).

do $$
begin
    if exists (select 1 from financeiro.regularizacao_perfil r where r.revertida_em is null) then
        raise exception 'Reversao recusada: ha regularizacao de itens sem perfil nao revertida. Reverta os dados antes.';
    end if;
    if exists (select 1 from public.perfil_financeiro group by nome having count(*) > 1) then
        raise exception 'Reversao recusada: ha perfis com o mesmo nome (de donos diferentes). A regra anterior exige nome unico no aplicativo.';
    end if;
    if (select count(*) from public.perfil_financeiro where padrao) > 1 then
        raise exception 'Reversao recusada: ha mais de um perfil padrao (um por dono). A regra anterior admite um so.';
    end if;
    if (select g.perfil_financeiro_id from financeiro.guarda_sem_perfil g)
       is distinct from (select min(p.id) from public.perfil_financeiro p where p.nome = 'Pessoal' having count(*) = 1) then
        raise exception 'Reversao recusada: a guarda dos registros sem perfil nao e o perfil chamado Pessoal. A regra anterior mudaria a posse desses registros.';
    end if;
end
$$;

""" + '\n\n'.join(VIGENTES[n][0] for n in SUBSTITUIDAS) + """

drop function financeiro.sou_administrador_plataforma();
drop function financeiro.definir_administrador_plataforma(uuid, boolean, text, text);
drop table financeiro.administrador_plataforma;
drop table financeiro.regularizacao_perfil;
drop function financeiro.definir_guarda_sem_perfil(integer, text, text);
drop function financeiro.guarda_legado(integer);
drop function financeiro.perfil_guarda_legado();
drop table financeiro.guarda_sem_perfil;
drop trigger perfil_acesso_dono on financeiro.perfil_acesso;
drop function financeiro.conferir_dono_no_vinculo();
drop trigger perfil_financeiro_dono_fixo on public.perfil_financeiro;
drop function financeiro.proteger_dono_do_perfil();
drop index public.perfil_financeiro_padrao_por_dono_uq;
drop index public.perfil_financeiro_dono_nome_uq;
drop function financeiro.nome_de_perfil_normalizado(text);
drop index public.perfil_financeiro_dono_idx;
alter table public.perfil_financeiro drop column user_id;
""" + '\n'.join(UNICIDADE_DO_NOME) + '\n'
if ARGS.verificar:
    atual = SAIDA.read_text(encoding='utf-8') if SAIDA.exists() else ''
    atual_rev = REVERSAO.read_text(encoding='utf-8') if REVERSAO.exists() else ''
    if atual != texto or atual_rev != reversao:
        print('DIFERENTE do arquivo versionado: rode o gerador sem --verificar.')
        sys.exit(1)
    print('igual ao arquivo versionado')
else:
    SAIDA.write_text(texto, encoding='utf-8', newline='\n')
    REVERSAO.write_text(reversao, encoding='utf-8', newline='\n')
    print(f'{REVERSAO.name}: {len(reversao.splitlines())} linhas; {len(SUBSTITUIDAS)} funcoes devolvidas ao texto anterior')
    print(f'{SAIDA.name}: {len(texto.splitlines())} linhas; {len(relatorio)} funcoes reescritas por substituicao')
    for nome, origem, n in relatorio:
        print(f'  {nome:42} {n} trecho(s)  <- {origem}')
