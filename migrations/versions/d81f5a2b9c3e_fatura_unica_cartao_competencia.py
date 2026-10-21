"""Uma unica fatura por cartao e competencia (indice unico parcial)

Revision ID: d81f5a2b9c3e
Revises: c4f7a2d91b3e
Create Date: 2026-10-21 18:00:00

FIN-FATURA-UNICA-1: o Flask (CartaoService.get_or_create_fatura) e o novo aplicativo
(financeiro.gerar_mes) consultam a fatura antes de cria-la; com acessos simultaneos,
os dois podiam inserir a mesma fatura. Esta migration cria o indice unico parcial
`ux_conta_fatura_cartao_competencia` em conta (item_despesa_id, cartao_competencia)
WHERE is_fatura_cartao — a mesma garantia da migration do Supabase
20261025090000_financeiro_fatura_unica (as duas usam IF NOT EXISTS; a que rodar
primeiro cria, a outra nao faz nada).

Antes de criar, verifica se ja existem faturas duplicadas. Se houver, ABORTA sem
alterar nada (nao exclui nem consolida): rode scripts/diagnostico_faturas_duplicadas.py
e decida o tratamento. Nao altera dados, valores, pagamentos nem compras.

Regra unica: se o indice ja existir (criado pela migration do Supabase ou pelo create_all),
a definicao e conferida com DEFINICAO; diferente, aborta sem alterar nada.
"""
from alembic import op
from sqlalchemy import text


revision = 'd81f5a2b9c3e'
down_revision = 'c4f7a2d91b3e'
branch_labels = None
depends_on = None

INDICE = 'ux_conta_fatura_cartao_competencia'
PREDICADO = {'postgresql': 'is_fatura_cartao', 'sqlite': 'is_fatura_cartao = 1'}
# Definicao unica da regra, igual a da migration do Supabase e a do model (Conta.__table_args__).
# IF NOT EXISTS so compara o nome: se ja existir um indice com este nome e outra definicao, aborta.
DEFINICAO = {
    'postgresql': ('select indexdef from pg_indexes where schemaname = current_schema() and indexname = %(nome)s',
                   f'CREATE UNIQUE INDEX {INDICE} ON public.conta USING btree (item_despesa_id, cartao_competencia) '
                   'WHERE is_fatura_cartao'),
    'sqlite': ("select sql from sqlite_master where type = 'index' and name = :nome",
               f'CREATE UNIQUE INDEX {INDICE} ON conta (item_despesa_id, cartao_competencia) WHERE is_fatura_cartao = 1'),
}


def _normalizar(definicao):
    return ''.join(definicao.lower().replace('"', '').split()).replace('public.conta', 'conta').replace('usingbtree', '')


def definicao_existente(conn):
    consulta, _ = DEFINICAO[conn.dialect.name]
    if conn.dialect.name == 'postgresql':
        return conn.exec_driver_sql(consulta, {'nome': INDICE}).scalar()
    return conn.execute(text(consulta), {'nome': INDICE}).scalar()


def definicao_confere(definicao, dialeto):
    return _normalizar(definicao) == _normalizar(DEFINICAO[dialeto][1])


def upgrade():
    conn = op.get_bind()
    dialeto = conn.dialect.name
    if dialeto not in PREDICADO:
        raise RuntimeError(f'FIN-FATURA-UNICA-1: dialeto nao suportado ({dialeto})')
    duplicados = conn.exec_driver_sql(
        f"select count(*) from (select 1 from conta where {PREDICADO[dialeto]} and cartao_competencia is not null "
        "group by item_despesa_id, cartao_competencia having count(*) > 1) d"
    ).scalar()
    existente = definicao_existente(conn)
    if existente is not None:
        if not definicao_confere(existente, dialeto):
            raise RuntimeError(f'FIN-FATURA-UNICA-1: ja existe {INDICE} com outra definicao ({existente}). Nada foi alterado.')
        return  # mesma regra ja criada (pela migration do Supabase ou pelo create_all): nada a fazer
    if duplicados:
        raise RuntimeError(
            f'FIN-FATURA-UNICA-1: {duplicados} fatura(s) duplicada(s) (cartao + competencia). Nada foi alterado. '
            'Rode scripts/diagnostico_faturas_duplicadas.py e decida o tratamento antes de aplicar.'
        )
    conn.exec_driver_sql(
        f'create unique index if not exists {INDICE} on conta (item_despesa_id, cartao_competencia) '
        f'where {PREDICADO[dialeto]}'
    )


def downgrade():
    op.get_bind().exec_driver_sql(f'drop index if exists {INDICE}')
