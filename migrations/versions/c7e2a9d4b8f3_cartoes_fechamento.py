"""Fechamento do cartao: regra do dia, confirmacao, competencia sugerida e auditoria de fatura consolidada

Revision ID: c7e2a9d4b8f3
Revises: f1c4d8e2a7b9
Create Date: 2026-10-23 15:00:00

FIN-CARTOES-FECHAMENTO-1:
- config_agregador.compra_no_fechamento (VARCHAR(10), 'PROXIMO' padrao | 'ATUAL') e
  config_agregador.fechamento_confirmado (BOOLEAN, false): nenhum cartao existente e marcado como confirmado;
- lancamento_agregado.mes_fatura_sugerido (DATE, nula): competencia que o fechamento sugeria no cadastro;
- fatura_consolidada_inclusao: auditoria das inclusoes confirmadas em fatura consolidada (D6);
- recorrencia_rejeicao (FIN-CARTOES-RECORRENCIA-PENDENCIA-1): compra recorrente nao lancada porque a fatura de destino
  estava consolidada; uma linha por recorrencia + competencia, com o aviso ao usuario e a dispensa auditavel.
Nada e preenchido retroativamente; nenhuma compra, fatura ou pagamento existente e alterado.
Os mesmos objetos sao criados pela migration do Supabase 20261030090000_financeiro_cartoes_fechamento
(IF NOT EXISTS: a que rodar primeiro cria). Os models mapeiam as colunas como deferred e o servico so as usa
quando existem: o Flask continua funcionando num banco que ainda nao rodou esta migration (sem sugestao de
competencia e sem inclusao em fatura consolidada, que exige a auditoria).
No Supabase (papeis anon/authenticated presentes), a tabela nova fica com RLS e sem privilegios para a Data API,
como as demais do public (SEC-SUPABASE-PUBLIC-1).
"""
from alembic import op


revision = 'c7e2a9d4b8f3'
down_revision = 'f1c4d8e2a7b9'
branch_labels = None
depends_on = None

TABELA = 'fatura_consolidada_inclusao'
REJEICAO = 'recorrencia_rejeicao'
COLUNAS_REJEICAO = """
            item_despesa_id             integer       not null references item_despesa (id) on delete cascade,
            competencia                 date          not null,
            perfil_financeiro_id        integer,
            cartao_id                   integer       not null,
            fatura_id                   integer       references conta (id) on delete set null,
            valor                       numeric(12,2),
            motivo                      text          not null,
            situacao                    varchar(20)   not null default 'PENDENTE',
            origem                      varchar(20)   not null,
            tentativas                  integer       not null default 1,
            aviso_dispensado_user_id    varchar(36),
            aviso_dispensado_usuario_id integer,"""
RESTRICOES_REJEICAO = """,
            constraint ux_recorrencia_rejeicao_competencia unique (item_despesa_id, competencia),
            constraint ck_recorrencia_rejeicao_situacao check (situacao in ('PENDENTE', 'REGULARIZADA')),
            constraint ck_recorrencia_rejeicao_origem check (origem in ('FLASK', 'NOVO_APP'))"""
DDL_REJEICAO = {
    'postgresql': f"""
        create table if not exists {REJEICAO} (
            id                          serial        primary key,{COLUNAS_REJEICAO}
            primeira_tentativa_em       timestamp     not null default (now() at time zone 'utc'),
            ultima_tentativa_em         timestamp     not null default (now() at time zone 'utc'),
            aviso_dispensado_em         timestamp{RESTRICOES_REJEICAO}
        )""",
    'sqlite': f"""
        create table if not exists {REJEICAO} (
            id                          integer       primary key autoincrement,{COLUNAS_REJEICAO}
            primeira_tentativa_em       datetime      not null default current_timestamp,
            ultima_tentativa_em         datetime      not null default current_timestamp,
            aviso_dispensado_em         datetime{RESTRICOES_REJEICAO}
        )""",
}

DDL = {
    'postgresql': f"""
        create table if not exists {TABELA} (
            id                         serial primary key,
            fatura_id                  integer       not null references conta (id) on delete cascade,
            cartao_id                  integer       not null,
            perfil_financeiro_id       integer,
            competencia                date          not null,
            compra_id                  varchar(36),
            lancamento_id              integer       references lancamento_agregado (id) on delete set null,
            valor_incluido             numeric(12,2) not null,
            total_consolidado_anterior numeric(12,2) not null,
            total_consolidado_novo     numeric(12,2) not null,
            operacao                   varchar(20)   not null,
            origem                     varchar(20)   not null,
            user_id                    varchar(36),
            usuario_id                 integer,
            criado_em                  timestamp     not null default (now() at time zone 'utc')
        )""",
    'sqlite': f"""
        create table if not exists {TABELA} (
            id                         integer primary key autoincrement,
            fatura_id                  integer       not null references conta (id) on delete cascade,
            cartao_id                  integer       not null,
            perfil_financeiro_id       integer,
            competencia                date          not null,
            compra_id                  varchar(36),
            lancamento_id              integer       references lancamento_agregado (id) on delete set null,
            valor_incluido             numeric(12,2) not null,
            total_consolidado_anterior numeric(12,2) not null,
            total_consolidado_novo     numeric(12,2) not null,
            operacao                   varchar(20)   not null,
            origem                     varchar(20)   not null,
            user_id                    varchar(36),
            usuario_id                 integer,
            criado_em                  datetime      not null default current_timestamp
        )""",
}


def _colunas(conn, tabela):
    if conn.dialect.name == 'sqlite':
        return {r[1] for r in conn.exec_driver_sql(f"PRAGMA table_info('{tabela}')")}
    return {r[0] for r in conn.exec_driver_sql(
        "select column_name from information_schema.columns where table_schema = current_schema() "
        f"and table_name = '{tabela}'")}


def _papeis_data_api(conn):
    return [p for (p,) in conn.exec_driver_sql(
        "select rolname from pg_roles where rolname in ('anon', 'authenticated') order by 1").fetchall()]


def upgrade():
    conn = op.get_bind()
    dialeto = conn.dialect.name
    if dialeto not in DDL:
        raise RuntimeError(f'FIN-CARTOES-FECHAMENTO-1: dialeto nao suportado ({dialeto})')

    config = _colunas(conn, 'config_agregador')
    if 'compra_no_fechamento' not in config:
        conn.exec_driver_sql("alter table config_agregador add column compra_no_fechamento varchar(10) not null "
                             "default 'PROXIMO'")
    if dialeto == 'postgresql' and not conn.exec_driver_sql(
            "select count(*) from pg_constraint where conname = 'ck_config_agregador_compra_no_fechamento'").scalar():
        conn.exec_driver_sql("alter table config_agregador add constraint ck_config_agregador_compra_no_fechamento "
                             "check (compra_no_fechamento in ('ATUAL', 'PROXIMO'))")
    if 'fechamento_confirmado' not in config:
        padrao = 'false' if dialeto == 'postgresql' else '0'
        conn.exec_driver_sql(f'alter table config_agregador add column fechamento_confirmado boolean not null '
                             f'default {padrao}')
    if 'mes_fatura_sugerido' not in _colunas(conn, 'lancamento_agregado'):
        conn.exec_driver_sql('alter table lancamento_agregado add column mes_fatura_sugerido date')

    conn.exec_driver_sql(DDL[dialeto])
    conn.exec_driver_sql(DDL_REJEICAO[dialeto])
    if dialeto == 'postgresql':
        papeis = _papeis_data_api(conn)
        if papeis:  # Supabase: fora da Data API, como as demais tabelas do public
            alvos = ', '.join(papeis)
            for tabela in (TABELA, REJEICAO):
                conn.exec_driver_sql(f'alter table {tabela} enable row level security')
                conn.exec_driver_sql(f'revoke all on table {tabela} from {alvos}')
                conn.exec_driver_sql(f'revoke all on sequence {tabela}_id_seq from {alvos}')


def downgrade():
    conn = op.get_bind()
    conn.exec_driver_sql(f'drop table if exists {REJEICAO}')
    conn.exec_driver_sql(f'drop table if exists {TABELA}')
    if 'mes_fatura_sugerido' in _colunas(conn, 'lancamento_agregado'):
        conn.exec_driver_sql('alter table lancamento_agregado drop column mes_fatura_sugerido')
    config = _colunas(conn, 'config_agregador')
    if conn.dialect.name == 'postgresql':
        conn.exec_driver_sql('alter table config_agregador drop constraint if exists ck_config_agregador_compra_no_fechamento')
    for coluna in ('fechamento_confirmado', 'compra_no_fechamento'):
        if coluna in config:
            conn.exec_driver_sql(f'alter table config_agregador drop column {coluna}')
