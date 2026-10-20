"""Protege as tabelas legadas do schema public no Supabase

Revision ID: c4f7a2d91b3e
Revises: 5c91e95eb05d
Create Date: 2026-10-20 12:00:00

SEC-SUPABASE-PUBLIC-1: no Supabase, as tabelas criadas pelo Flask no schema
`public` nasceram com RLS desligada e com todos os privilegios para os papeis
da Data API (`anon`, `authenticated`), por causa dos default privileges da
plataforma. Esta migration:

- habilita RLS (sem FORCE) nas tabelas do `public` cujo dono e o papel que
  executa a migration — o mesmo papel com que o Flask conecta. O dono nao e
  afetado por RLS sem FORCE (e, no Supabase, o papel `postgres` ainda tem
  BYPASSRLS), entao o Flask continua lendo e gravando normalmente;
- revoga de `anon` e `authenticated` todos os privilegios em tabelas,
  sequencias e funcoes do `public`;
- revoga os default privileges desse papel no `public`, para que tabelas
  criadas por migrations futuras nao nascam expostas.

Nenhuma policy e criada: sem policy, a RLS nega tudo a quem nao e dono. Nao
altera dados, colunas nem regras financeiras.

E no-op fora do Supabase (SQLite, ou PostgreSQL sem os papeis anon/authenticated),
como o banco local de desenvolvimento.

Limite conhecido: os default privileges do papel de plataforma `supabase_admin`
nao podem ser alterados por esta migration (objetos criados pela plataforma no
`public` ainda receberiam grants). A revogacao em massa desta migration nao
cobre objetos criados depois dela por esse papel.
"""
import logging

from alembic import op


revision = 'c4f7a2d91b3e'
down_revision = '5c91e95eb05d'
branch_labels = None
depends_on = None

logger = logging.getLogger('alembic.runtime.migration')

PAPEIS_DATA_API = ('anon', 'authenticated')


def _ident(conn, nome):
    return conn.exec_driver_sql('select quote_ident(%(n)s)', {'n': nome}).scalar()


def aplicar_protecao(conn):
    """Aplica a protecao e devolve um resumo. Idempotente."""
    if conn.dialect.name != 'postgresql':
        return {'aplicado': False, 'motivo': f'dialeto {conn.dialect.name}'}

    papeis = [p for (p,) in conn.exec_driver_sql(
        "select rolname from pg_roles where rolname in ('anon', 'authenticated') order by 1"
    ).fetchall()]
    if not papeis:
        return {'aplicado': False, 'motivo': 'sem papeis da Data API (nao e Supabase)'}

    atual = conn.exec_driver_sql('select current_user').scalar()
    alvos = ', '.join(_ident(conn, p) for p in papeis)

    tabelas = conn.exec_driver_sql(
        """
        select c.relname, pg_get_userbyid(c.relowner) as dono, c.relrowsecurity
          from pg_class c
          join pg_namespace n on n.oid = c.relnamespace
         where n.nspname = 'public' and c.relkind in ('r', 'p')
         order by c.relname
        """
    ).fetchall()

    habilitadas, ja_tinham, ignoradas = [], [], []
    for nome, dono, rls in tabelas:
        if dono != atual:
            # Nunca ligar RLS em tabela de outro dono: o papel do Flask poderia
            # perder acesso (sem policy, RLS nega tudo a quem nao e dono).
            ignoradas.append(nome)
            continue
        if rls:
            ja_tinham.append(nome)
            continue
        conn.exec_driver_sql(f'alter table public.{_ident(conn, nome)} enable row level security')
        habilitadas.append(nome)

    # Objeto a objeto, so no que pertence ao papel atual: `REVOKE ... ON ALL TABLES
    # IN SCHEMA` aborta a migration inteira se existir no public um objeto de outro
    # dono sobre o qual este papel nao tem privilegio (ex.: objetos da plataforma).
    objetos = conn.exec_driver_sql(
        """
        select case when c.relkind = 'S' then 'sequence' else 'table' end, c.relname
          from pg_class c
          join pg_namespace n on n.oid = c.relnamespace
         where n.nspname = 'public' and c.relkind in ('r', 'p', 'v', 'm', 'f', 'S')
           and pg_get_userbyid(c.relowner) = current_user
         order by 1, 2
        """
    ).fetchall()
    for tipo, nome in objetos:
        conn.exec_driver_sql(f'revoke all on {tipo} public.{_ident(conn, nome)} from {alvos}')

    funcoes = conn.exec_driver_sql(
        """
        select p.oid::regprocedure::text
          from pg_proc p
          join pg_namespace n on n.oid = p.pronamespace
         where n.nspname = 'public' and pg_get_userbyid(p.proowner) = current_user
        """
    ).fetchall()
    for (assinatura,) in funcoes:
        conn.exec_driver_sql(f'revoke all on function {assinatura} from {alvos}')

    dono_atual = _ident(conn, atual)
    for tipo in ('tables', 'sequences', 'functions'):
        conn.exec_driver_sql(
            f'alter default privileges for role {dono_atual} in schema public revoke all on {tipo} from {alvos}'
        )

    if ignoradas:
        logger.warning('SEC-SUPABASE-PUBLIC-1: RLS nao habilitada (dono diferente de %s): %s', atual, ', '.join(ignoradas))
    logger.info('SEC-SUPABASE-PUBLIC-1: RLS habilitada em %d tabela(s); %d ja tinham; privilegios de %s revogados.',
                len(habilitadas), len(ja_tinham), ', '.join(papeis))
    return {'aplicado': True, 'papel': atual, 'papeis_revogados': papeis, 'habilitadas': habilitadas,
            'ja_tinham': ja_tinham, 'ignoradas': ignoradas}


def upgrade():
    aplicar_protecao(op.get_bind())


def downgrade():
    # Intencionalmente vazio: desfazer reabriria as tabelas do Flask para a
    # Data API (anon com leitura e escrita). Se for realmente necessario,
    # reconceder privilegios deve ser uma decisao explicita e revisada.
    logger.warning('SEC-SUPABASE-PUBLIC-1: downgrade nao reabre o acesso de anon/authenticated (no-op).')
