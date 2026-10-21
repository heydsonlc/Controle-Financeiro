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
"""
from alembic import op


revision = 'd81f5a2b9c3e'
down_revision = 'c4f7a2d91b3e'
branch_labels = None
depends_on = None

INDICE = 'ux_conta_fatura_cartao_competencia'
PREDICADO = {'postgresql': 'is_fatura_cartao', 'sqlite': 'is_fatura_cartao = 1'}


def upgrade():
    conn = op.get_bind()
    dialeto = conn.dialect.name
    if dialeto not in PREDICADO:
        raise RuntimeError(f'FIN-FATURA-UNICA-1: dialeto nao suportado ({dialeto})')
    duplicados = conn.exec_driver_sql(
        f"select count(*) from (select 1 from conta where {PREDICADO[dialeto]} and cartao_competencia is not null "
        "group by item_despesa_id, cartao_competencia having count(*) > 1) d"
    ).scalar()
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
