"""corrige receita de contemplacao de consorcio por perfil

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-05-07 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'd5e6f7a8b9c0'
down_revision = 'c4d5e6f7a8b9'
branch_labels = None
depends_on = None


NOME_FONTE = 'Contemplação de Consórcio'
NOME_FONTE_MOJIBAKE = 'ContemplaÃ§Ã£o de ConsÃ³rcio'
DESCRICAO_FONTE = 'Receita pontual gerada automaticamente por consórcio contemplado.'


def _insp():
    return sa.inspect(op.get_bind())


def _table_exists(table_name):
    return table_name in _insp().get_table_names()


def _columns(table_name):
    if not _table_exists(table_name):
        return set()
    return {column['name'] for column in _insp().get_columns(table_name)}


def _column_exists(table_name, column_name):
    return column_name in _columns(table_name)


def _index_exists(table_name, index_name):
    if not _table_exists(table_name):
        return False
    return index_name in {index['name'] for index in _insp().get_indexes(table_name)}


def _fk_exists(table_name, fk_name):
    if not _table_exists(table_name):
        return False
    return fk_name in {fk['name'] for fk in _insp().get_foreign_keys(table_name)}


def _ensure_pessoal_id(bind):
    pessoal_id = bind.execute(
        sa.text("SELECT id FROM perfil_financeiro WHERE nome = 'Pessoal' ORDER BY id LIMIT 1")
    ).scalar()
    if pessoal_id:
        return pessoal_id

    cols = _columns('perfil_financeiro')
    payload = {
        'nome': 'Pessoal',
        'tipo': 'PESSOAL',
        'avatar': 'PE',
        'cor': '#2563eb',
        'ativo': True,
    }
    if 'padrao' in cols:
        payload['padrao'] = True
    if 'created_at' in cols:
        payload['created_at'] = sa.func.current_timestamp()
    if 'updated_at' in cols:
        payload['updated_at'] = sa.func.current_timestamp()

    perfil = sa.table('perfil_financeiro', *[sa.column(col) for col in payload])
    bind.execute(perfil.insert().values(**payload))
    return bind.execute(
        sa.text("SELECT id FROM perfil_financeiro WHERE nome = 'Pessoal' ORDER BY id LIMIT 1")
    ).scalar()


def _primeiro_dia(valor):
    if hasattr(valor, 'replace') and not isinstance(valor, str):
        return valor.replace(day=1)
    texto = str(valor)[:10]
    return f'{texto[:8]}01'


def _ensure_item_receita(bind, perfil_id):
    item_id = bind.execute(
        sa.text("""
            SELECT id
            FROM item_receita
            WHERE perfil_financeiro_id = :perfil_id
              AND nome = :nome
            ORDER BY ativo DESC, id
            LIMIT 1
        """),
        {'perfil_id': perfil_id, 'nome': NOME_FONTE},
    ).scalar()
    if item_id:
        return item_id

    item_id = bind.execute(
        sa.text("""
            SELECT id
            FROM item_receita
            WHERE perfil_financeiro_id = :perfil_id
              AND nome = :nome_mojibake
            ORDER BY ativo DESC, id
            LIMIT 1
        """),
        {'perfil_id': perfil_id, 'nome_mojibake': NOME_FONTE_MOJIBAKE},
    ).scalar()
    if item_id:
        bind.execute(
            sa.text("""
                UPDATE item_receita
                SET nome = :nome,
                    tipo = 'OUTROS',
                    descricao = COALESCE(descricao, :descricao),
                    ativo = :ativo,
                    recorrente = :recorrente
                WHERE id = :id
            """),
            {
                'id': item_id,
                'nome': NOME_FONTE,
                'descricao': DESCRICAO_FONTE,
                'ativo': True,
                'recorrente': False,
            },
        )
        return item_id

    bind.execute(
        sa.text("""
            INSERT INTO item_receita (
                perfil_financeiro_id, nome, tipo, descricao, ativo, recorrente, criado_em
            )
            VALUES (
                :perfil_id, :nome, 'OUTROS', :descricao, :ativo, :recorrente, CURRENT_TIMESTAMP
            )
        """),
        {
            'perfil_id': perfil_id,
            'nome': NOME_FONTE,
            'descricao': DESCRICAO_FONTE,
            'ativo': True,
            'recorrente': False,
        },
    )
    return bind.execute(
        sa.text("""
            SELECT id
            FROM item_receita
            WHERE perfil_financeiro_id = :perfil_id
              AND nome = :nome
            ORDER BY id DESC
            LIMIT 1
        """),
        {'perfil_id': perfil_id, 'nome': NOME_FONTE},
    ).scalar()


def _consorcio_id(observacoes):
    match = None
    if observacoes:
        import re
        match = re.search(r'\bconsorcio_id=(\d+)\b', observacoes)
    return int(match.group(1)) if match else None


def _perfil_do_consorcio(bind, consorcio_id, pessoal_id):
    if not consorcio_id or not _table_exists('contrato_consorcio'):
        return pessoal_id
    perfil_id = bind.execute(
        sa.text("SELECT perfil_financeiro_id FROM contrato_consorcio WHERE id = :id"),
        {'id': consorcio_id},
    ).scalar()
    return perfil_id or pessoal_id


def _migrar_receitas_por_fonte(bind, pessoal_id):
    if not _table_exists('receita_realizada') or not _table_exists('item_receita'):
        return

    receitas = bind.execute(
        sa.text("""
            SELECT rr.id, rr.perfil_financeiro_id, rr.item_receita_id, rr.observacoes
            FROM receita_realizada rr
            JOIN item_receita ir ON ir.id = rr.item_receita_id
            WHERE ir.nome IN (:nome, :nome_mojibake)
        """),
        {'nome': NOME_FONTE, 'nome_mojibake': NOME_FONTE_MOJIBAKE},
    ).mappings().all()

    for receita in receitas:
        perfil_id = receita['perfil_financeiro_id']
        if not perfil_id:
            perfil_id = _perfil_do_consorcio(bind, _consorcio_id(receita['observacoes']), pessoal_id)
        item_id = _ensure_item_receita(bind, perfil_id)
        bind.execute(
            sa.text("""
                UPDATE receita_realizada
                SET perfil_financeiro_id = :perfil_id,
                    item_receita_id = :item_id
                WHERE id = :id
            """),
            {'id': receita['id'], 'perfil_id': perfil_id, 'item_id': item_id},
        )


def _receita_tem_movimento(bind, receita_id):
    if not _table_exists('movimento_financeiro') or not _column_exists('movimento_financeiro', 'receita_realizada_id'):
        return False
    return bool(bind.execute(
        sa.text("SELECT 1 FROM movimento_financeiro WHERE receita_realizada_id = :id LIMIT 1"),
        {'id': receita_id},
    ).fetchone())


def _deduplicar_receitas_consorcio(bind):
    if not _table_exists('contrato_consorcio') or not _table_exists('receita_realizada'):
        return

    consorcios = bind.execute(sa.text("""
        SELECT id, nome, perfil_financeiro_id, mes_contemplacao, valor_premio
        FROM contrato_consorcio
        WHERE mes_contemplacao IS NOT NULL
          AND valor_premio IS NOT NULL
    """)).mappings().all()

    for consorcio in consorcios:
        marcador = f'consorcio_id={consorcio["id"]}'
        receitas = bind.execute(
            sa.text("""
                SELECT id, perfil_financeiro_id, item_receita_id
                FROM receita_realizada
                WHERE observacoes LIKE :marcador
                ORDER BY id
            """),
            {'marcador': f'%{marcador}%'},
        ).mappings().all()
        if not receitas:
            continue

        perfil_id = consorcio['perfil_financeiro_id']
        item_id = _ensure_item_receita(bind, perfil_id)
        canonica = sorted(
            receitas,
            key=lambda receita: (
                0 if receita['perfil_financeiro_id'] == perfil_id else 1,
                0 if receita['item_receita_id'] == item_id else 1,
                0 if receita['perfil_financeiro_id'] is not None else 1,
                receita['id'],
            ),
        )[0]

        bind.execute(
            sa.text("""
                UPDATE receita_realizada
                SET perfil_financeiro_id = :perfil_id,
                    item_receita_id = :item_id,
                    data_recebimento = :data_recebimento,
                    valor_recebido = :valor_recebido,
                    mes_referencia = :mes_referencia,
                    descricao = :descricao,
                    orcamento_id = NULL
                WHERE id = :id
            """),
            {
                'id': canonica['id'],
                'perfil_id': perfil_id,
                'item_id': item_id,
                'data_recebimento': consorcio['mes_contemplacao'],
                'valor_recebido': consorcio['valor_premio'],
                'mes_referencia': _primeiro_dia(consorcio['mes_contemplacao']),
                'descricao': f'Consórcio {consorcio["nome"]} - contemplação (ID {consorcio["id"]})',
            },
        )

        for receita in receitas:
            if receita['id'] == canonica['id']:
                continue
            if not _receita_tem_movimento(bind, receita['id']):
                bind.execute(sa.text("DELETE FROM receita_realizada WHERE id = :id"), {'id': receita['id']})


def _limpar_fontes_duplicadas(bind, pessoal_id):
    if not _table_exists('item_receita'):
        return

    if _table_exists('receita_orcamento'):
        item_pessoal = _ensure_item_receita(bind, pessoal_id)
        bind.execute(
            sa.text("""
                UPDATE receita_orcamento
                SET perfil_financeiro_id = COALESCE(perfil_financeiro_id, :perfil_id),
                    item_receita_id = :item_id
                WHERE item_receita_id IN (
                    SELECT id FROM item_receita
                    WHERE perfil_financeiro_id IS NULL
                      AND nome IN (:nome, :nome_mojibake)
                )
            """),
            {'perfil_id': pessoal_id, 'item_id': item_pessoal, 'nome': NOME_FONTE, 'nome_mojibake': NOME_FONTE_MOJIBAKE},
        )

    itens = bind.execute(
        sa.text("""
            SELECT id, perfil_financeiro_id, nome
            FROM item_receita
            WHERE nome IN (:nome, :nome_mojibake)
            ORDER BY perfil_financeiro_id IS NOT NULL, perfil_financeiro_id, id
        """),
        {'nome': NOME_FONTE, 'nome_mojibake': NOME_FONTE_MOJIBAKE},
    ).mappings().all()

    for item in itens:
        perfil_id = item['perfil_financeiro_id'] or pessoal_id
        item_canonico_id = _ensure_item_receita(bind, perfil_id)
        if item['id'] != item_canonico_id:
            if _table_exists('receita_realizada'):
                bind.execute(
                    sa.text("""
                        UPDATE receita_realizada
                        SET perfil_financeiro_id = :perfil_id,
                            item_receita_id = :item_canonico_id
                        WHERE item_receita_id = :item_id
                    """),
                    {
                        'perfil_id': perfil_id,
                        'item_canonico_id': item_canonico_id,
                        'item_id': item['id'],
                    },
                )
            if _table_exists('receita_orcamento'):
                bind.execute(
                    sa.text("""
                        UPDATE receita_orcamento
                        SET perfil_financeiro_id = :perfil_id,
                            item_receita_id = :item_canonico_id
                        WHERE item_receita_id = :item_id
                    """),
                    {
                        'perfil_id': perfil_id,
                        'item_canonico_id': item_canonico_id,
                        'item_id': item['id'],
                    },
                )

        refs_realizadas = 0
        refs_orcamento = 0
        if _table_exists('receita_realizada'):
            refs_realizadas = bind.execute(
                sa.text("SELECT COUNT(*) FROM receita_realizada WHERE item_receita_id = :id"),
                {'id': item['id']},
            ).scalar() or 0
        if _table_exists('receita_orcamento'):
            refs_orcamento = bind.execute(
                sa.text("SELECT COUNT(*) FROM receita_orcamento WHERE item_receita_id = :id"),
                {'id': item['id']},
            ).scalar() or 0

        if refs_realizadas or refs_orcamento:
            if item['nome'] == NOME_FONTE_MOJIBAKE:
                bind.execute(
                    sa.text("UPDATE item_receita SET nome = :nome WHERE id = :id"),
                    {'id': item['id'], 'nome': NOME_FONTE},
                )
            continue

        bind.execute(
            sa.text("""
                UPDATE item_receita
                SET nome = :nome,
                    ativo = :ativo
                WHERE id = :id
            """),
            {'id': item['id'], 'nome': f'{NOME_FONTE} (legado #{item["id"]})', 'ativo': False},
        )


def upgrade():
    bind = op.get_bind()
    if not _table_exists('contrato_consorcio'):
        return

    if not _column_exists('contrato_consorcio', 'perfil_financeiro_id'):
        with op.batch_alter_table('contrato_consorcio') as batch_op:
            batch_op.add_column(sa.Column('perfil_financeiro_id', sa.Integer(), nullable=True))

    if _table_exists('perfil_financeiro') and not _fk_exists(
        'contrato_consorcio',
        'fk_contrato_consorcio_perfil_financeiro',
    ):
        with op.batch_alter_table('contrato_consorcio') as batch_op:
            batch_op.create_foreign_key(
                'fk_contrato_consorcio_perfil_financeiro',
                'perfil_financeiro',
                ['perfil_financeiro_id'],
                ['id'],
            )

    if not _index_exists('contrato_consorcio', 'ix_contrato_consorcio_perfil_financeiro_id'):
        op.create_index(
            'ix_contrato_consorcio_perfil_financeiro_id',
            'contrato_consorcio',
            ['perfil_financeiro_id'],
            unique=False,
        )

    pessoal_id = _ensure_pessoal_id(bind)
    bind.execute(
        sa.text("""
            UPDATE contrato_consorcio
            SET perfil_financeiro_id = :perfil_id
            WHERE perfil_financeiro_id IS NULL
        """),
        {'perfil_id': pessoal_id},
    )

    _migrar_receitas_por_fonte(bind, pessoal_id)
    _deduplicar_receitas_consorcio(bind)
    _limpar_fontes_duplicadas(bind, pessoal_id)


def downgrade():
    if not _table_exists('contrato_consorcio'):
        return

    if _index_exists('contrato_consorcio', 'ix_contrato_consorcio_perfil_financeiro_id'):
        op.drop_index('ix_contrato_consorcio_perfil_financeiro_id', table_name='contrato_consorcio')

    if _fk_exists('contrato_consorcio', 'fk_contrato_consorcio_perfil_financeiro'):
        with op.batch_alter_table('contrato_consorcio') as batch_op:
            batch_op.drop_constraint('fk_contrato_consorcio_perfil_financeiro', type_='foreignkey')

    if _column_exists('contrato_consorcio', 'perfil_financeiro_id'):
        with op.batch_alter_table('contrato_consorcio') as batch_op:
            batch_op.drop_column('perfil_financeiro_id')
