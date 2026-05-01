"""baseline_inicial_schema_completo

Revision ID: dd1a552aec6a
Revises: 
Create Date: 2026-05-01 08:54:58.117339

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'dd1a552aec6a'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Baseline completo gerado via autogenerate contra banco temporário local vazio.
    # Ciclos de FK quebrados manualmente com op.create_foreign_key após criação das tabelas:
    #   - conta.financiamento_parcela_id -> financiamento_parcela (ciclo conta <-> financiamento_parcela)
    #   - item_despesa.item_agregado_id  -> item_agregado         (ciclo item_despesa <-> item_agregado)

    # --- Tabelas raiz (sem dependências) ---
    op.create_table('categoria',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nome', sa.String(length=100), nullable=False),
    sa.Column('descricao', sa.Text(), nullable=True),
    sa.Column('cor', sa.String(length=7), nullable=True),
    sa.Column('ativo', sa.Boolean(), nullable=True),
    sa.Column('criado_em', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('nome')
    )
    op.create_table('conta_bancaria',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nome', sa.String(length=100), nullable=False),
    sa.Column('instituicao', sa.String(length=100), nullable=False),
    sa.Column('tipo', sa.String(length=50), nullable=False),
    sa.Column('agencia', sa.String(length=20), nullable=True),
    sa.Column('numero_conta', sa.String(length=50), nullable=True),
    sa.Column('digito_conta', sa.String(length=10), nullable=True),
    sa.Column('saldo_inicial', sa.Numeric(precision=15, scale=2), nullable=True),
    sa.Column('saldo_atual', sa.Numeric(precision=15, scale=2), nullable=True),
    sa.Column('cor_display', sa.String(length=7), nullable=True),
    sa.Column('icone', sa.String(length=50), nullable=True),
    sa.Column('data_criacao', sa.DateTime(), nullable=True),
    sa.Column('data_atualizacao', sa.DateTime(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('conta_patrimonio',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nome', sa.String(length=100), nullable=False),
    sa.Column('tipo', sa.String(length=50), nullable=True),
    sa.Column('saldo_inicial', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('saldo_atual', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('meta', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('cor', sa.String(length=7), nullable=True),
    sa.Column('ativo', sa.Boolean(), nullable=True),
    sa.Column('observacoes', sa.Text(), nullable=True),
    sa.Column('criado_em', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('nome')
    )
    op.create_table('grupo_agregador',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nome', sa.String(length=100), nullable=False),
    sa.Column('descricao', sa.Text(), nullable=True),
    sa.Column('ativo', sa.Boolean(), nullable=True),
    sa.Column('criado_em', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('nome')
    )
    op.create_table('indexador_mensal',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nome', sa.String(length=20), nullable=False),
    sa.Column('data_referencia', sa.Date(), nullable=False),
    sa.Column('valor', sa.Numeric(precision=10, scale=6), nullable=False),
    sa.Column('criado_em', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('indexador_mensal', schema=None) as batch_op:
        batch_op.create_index('idx_indexador_nome_data', ['nome', 'data_referencia'], unique=True)

    op.create_table('preferencia',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nome_usuario', sa.String(length=100), nullable=True),
    sa.Column('renda_principal', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('mes_inicio_planejamento', sa.Integer(), nullable=True),
    sa.Column('dia_fechamento_mes', sa.Integer(), nullable=True),
    sa.Column('ajustar_competencia_automatico', sa.Boolean(), nullable=True),
    sa.Column('exibir_aviso_despesa_vencida', sa.Boolean(), nullable=True),
    sa.Column('solicitar_confirmacao_exclusao', sa.Boolean(), nullable=True),
    sa.Column('vincular_pagamento_cartao_auto', sa.Boolean(), nullable=True),
    sa.Column('graficos_visiveis', sa.String(length=200), nullable=True),
    sa.Column('insights_inteligentes_ativo', sa.Boolean(), nullable=True),
    sa.Column('mostrar_saldo_consolidado', sa.Boolean(), nullable=True),
    sa.Column('mostrar_evolucao_historica', sa.Boolean(), nullable=True),
    sa.Column('dia_inicio_fatura', sa.Integer(), nullable=True),
    sa.Column('dia_corte_fatura', sa.Integer(), nullable=True),
    sa.Column('lancamentos_agrupados', sa.Boolean(), nullable=True),
    sa.Column('orcamento_por_categoria', sa.Boolean(), nullable=True),
    sa.Column('tema_sistema', sa.String(length=20), nullable=True),
    sa.Column('cor_principal', sa.String(length=7), nullable=True),
    sa.Column('mostrar_icones_coloridos', sa.Boolean(), nullable=True),
    sa.Column('abreviar_valores', sa.Boolean(), nullable=True),
    sa.Column('ultimo_backup', sa.DateTime(), nullable=True),
    sa.Column('backup_automatico', sa.Boolean(), nullable=True),
    sa.Column('modo_inteligente_ativo', sa.Boolean(), nullable=True),
    sa.Column('sugestoes_economia', sa.Boolean(), nullable=True),
    sa.Column('classificacao_automatica', sa.Boolean(), nullable=True),
    sa.Column('correcao_categorias', sa.Boolean(), nullable=True),
    sa.Column('parcelas_recorrentes_auto', sa.Boolean(), nullable=True),
    sa.Column('data_criacao', sa.DateTime(), nullable=True),
    sa.Column('data_atualizacao', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )

    # --- item_despesa sem FK circular (item_agregado_id adicionada depois) ---
    op.create_table('item_despesa',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('categoria_id', sa.Integer(), nullable=True),
    sa.Column('nome', sa.String(length=100), nullable=False),
    sa.Column('tipo', sa.String(length=20), nullable=False),
    sa.Column('descricao', sa.Text(), nullable=True),
    sa.Column('ativo', sa.Boolean(), nullable=True),
    sa.Column('valor', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('valor_pago', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('data_vencimento', sa.Date(), nullable=True),
    sa.Column('data_pagamento', sa.Date(), nullable=True),
    sa.Column('pago', sa.Boolean(), nullable=True),
    sa.Column('recorrente', sa.Boolean(), nullable=True),
    sa.Column('tipo_recorrencia', sa.String(length=20), nullable=True),
    sa.Column('mes_competencia', sa.String(length=7), nullable=True),
    sa.Column('meio_pagamento', sa.String(length=20), nullable=True),
    sa.Column('cartao_id', sa.Integer(), nullable=True),
    sa.Column('item_agregado_id', sa.Integer(), nullable=True),
    sa.Column('criado_em', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['cartao_id'], ['item_despesa.id'], ),
    sa.ForeignKeyConstraint(['categoria_id'], ['categoria.id'], ),
    sa.PrimaryKeyConstraint('id')
    )

    # --- item_agregado depende de item_despesa e grupo_agregador ---
    op.create_table('item_agregado',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('item_despesa_id', sa.Integer(), nullable=False),
    sa.Column('nome', sa.String(length=100), nullable=False),
    sa.Column('descricao', sa.Text(), nullable=True),
    sa.Column('ativo', sa.Boolean(), nullable=True),
    sa.Column('grupo_agregador_id', sa.Integer(), nullable=True),
    sa.Column('criado_em', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['grupo_agregador_id'], ['grupo_agregador.id'], ),
    sa.ForeignKeyConstraint(['item_despesa_id'], ['item_despesa.id'], ),
    sa.PrimaryKeyConstraint('id')
    )

    # Fechar ciclo item_despesa <-> item_agregado
    op.create_foreign_key('fk_item_despesa_item_agregado', 'item_despesa', 'item_agregado', ['item_agregado_id'], ['id'])
    op.create_table('config_agregador',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('item_despesa_id', sa.Integer(), nullable=False),
    sa.Column('dia_fechamento', sa.Integer(), nullable=False),
    sa.Column('dia_vencimento', sa.Integer(), nullable=False),
    sa.Column('limite_credito', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('numero_cartao', sa.String(length=19), nullable=True),
    sa.Column('data_validade', sa.String(length=7), nullable=True),
    sa.Column('codigo_seguranca', sa.String(length=4), nullable=True),
    sa.Column('tem_codigo', sa.Boolean(), nullable=True),
    sa.Column('observacoes', sa.Text(), nullable=True),
    sa.Column('criado_em', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['item_despesa_id'], ['item_despesa.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('item_despesa_id')
    )
    op.create_table('despesa_prevista',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('origem_tipo', sa.String(length=20), nullable=False),
    sa.Column('origem_id', sa.Integer(), nullable=False),
    sa.Column('categoria_id', sa.Integer(), nullable=False),
    sa.Column('data_prevista', sa.Date(), nullable=False),
    sa.Column('data_original_prevista', sa.Date(), nullable=False),
    sa.Column('data_atual_prevista', sa.Date(), nullable=False),
    sa.Column('valor_previsto', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('metadata', sa.Text(), nullable=True),
    sa.Column('criado_em', sa.DateTime(), nullable=True),
    sa.Column('atualizado_em', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['categoria_id'], ['categoria.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('despesa_prevista', schema=None) as batch_op:
        batch_op.create_index('idx_desp_prev_origem_data', ['origem_tipo', 'origem_id', 'data_prevista'], unique=False)

    op.create_table('financiamento',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nome', sa.String(length=200), nullable=False),
    sa.Column('produto', sa.String(length=100), nullable=True),
    sa.Column('sistema_amortizacao', sa.String(length=20), nullable=False),
    sa.Column('valor_financiado', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('prazo_total_meses', sa.Integer(), nullable=False),
    sa.Column('prazo_remanescente_meses', sa.Integer(), nullable=False),
    sa.Column('taxa_juros_nominal_anual', sa.Numeric(precision=8, scale=4), nullable=False),
    sa.Column('taxa_juros_efetiva_anual', sa.Numeric(precision=8, scale=4), nullable=True),
    sa.Column('taxa_juros_efetiva_relacionamento_anual', sa.Numeric(precision=8, scale=4), nullable=True),
    sa.Column('taxa_juros_mensal', sa.Numeric(precision=8, scale=6), nullable=False),
    sa.Column('indexador_saldo', sa.String(length=20), nullable=True),
    sa.Column('data_contrato', sa.Date(), nullable=False),
    sa.Column('data_primeira_parcela', sa.Date(), nullable=False),
    sa.Column('item_despesa_id', sa.Integer(), nullable=True),
    sa.Column('seguro_tipo', sa.String(length=20), nullable=True),
    sa.Column('seguro_percentual', sa.Numeric(precision=8, scale=6), nullable=True),
    sa.Column('valor_seguro_mensal', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('taxa_administracao_fixa', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('saldo_devedor_atual', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('numero_parcela_base', sa.Integer(), nullable=True),
    sa.Column('data_base', sa.Date(), nullable=True),
    sa.Column('amortizacao_mensal_atual', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('regime_pos_amortizacao', sa.String(length=20), nullable=True),
    sa.Column('ativo', sa.Boolean(), nullable=True),
    sa.Column('criado_em', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['item_despesa_id'], ['item_despesa.id'], ),
    sa.PrimaryKeyConstraint('id')
    )

    # --- financiamento_parcela sem FK circular para conta (adicionada depois) ---
    op.create_table('financiamento_parcela',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('financiamento_id', sa.Integer(), nullable=False),
    sa.Column('numero_parcela', sa.Integer(), nullable=False),
    sa.Column('data_vencimento', sa.Date(), nullable=False),
    sa.Column('valor_amortizacao', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('valor_juros', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('valor_seguro', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('valor_taxa_adm', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('valor_subsidio', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('valor_fgts_utilizado', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('valor_juros_mora', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('valor_multa', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('valor_atualizacao_monetaria', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('valor_iof_complementar', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('valor_previsto_total', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('valor_pago', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('dif_apurada', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('saldo_devedor_apos_pagamento', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('conta_id', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('criado_em', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['financiamento_id'], ['financiamento.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('financiamento_parcela', schema=None) as batch_op:
        batch_op.create_index('idx_fin_parc_financ', ['financiamento_id'], unique=False)
        batch_op.create_index('idx_fin_parc_status', ['status'], unique=False)
        batch_op.create_index('idx_fin_parc_venc', ['data_vencimento'], unique=False)

    # --- conta sem FK circular para financiamento_parcela (adicionada depois) ---
    op.create_table('conta',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('item_despesa_id', sa.Integer(), nullable=False),
    sa.Column('financiamento_parcela_id', sa.Integer(), nullable=True),
    sa.Column('mes_referencia', sa.Date(), nullable=False),
    sa.Column('descricao', sa.String(length=200), nullable=False),
    sa.Column('valor', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('data_vencimento', sa.Date(), nullable=False),
    sa.Column('data_pagamento', sa.Date(), nullable=True),
    sa.Column('status_pagamento', sa.String(length=20), nullable=True),
    sa.Column('debito_automatico', sa.Boolean(), nullable=True),
    sa.Column('conta_bancaria_id', sa.Integer(), nullable=True),
    sa.Column('numero_parcela', sa.Integer(), nullable=True),
    sa.Column('total_parcelas', sa.Integer(), nullable=True),
    sa.Column('observacoes', sa.Text(), nullable=True),
    sa.Column('is_fatura_cartao', sa.Boolean(), nullable=True),
    sa.Column('valor_planejado', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('valor_executado', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('estouro_orcamento', sa.Boolean(), nullable=True),
    sa.Column('cartao_competencia', sa.Date(), nullable=True),
    sa.Column('status_fatura', sa.String(length=10), nullable=True),
    sa.Column('data_consolidacao', sa.DateTime(), nullable=True),
    sa.Column('valor_consolidado', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('criado_em', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['conta_bancaria_id'], ['conta_bancaria.id'], ),
    sa.ForeignKeyConstraint(['item_despesa_id'], ['item_despesa.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('conta', schema=None) as batch_op:
        batch_op.create_index('idx_conta_item_mes', ['item_despesa_id', 'mes_referencia'], unique=False)
        batch_op.create_index('idx_conta_status', ['status_pagamento'], unique=False)
        batch_op.create_index('idx_conta_vencimento', ['data_vencimento'], unique=False)

    # Fechar ciclo conta <-> financiamento_parcela
    op.create_foreign_key('fk_conta_financiamento_parcela', 'conta', 'financiamento_parcela', ['financiamento_parcela_id'], ['id'])
    op.create_foreign_key('fk_financiamento_parcela_conta', 'financiamento_parcela', 'conta', ['conta_id'], ['id'])

    op.create_table('item_receita',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nome', sa.String(length=100), nullable=False),
    sa.Column('tipo', sa.String(length=30), nullable=False),
    sa.Column('descricao', sa.Text(), nullable=True),
    sa.Column('ativo', sa.Boolean(), nullable=True),
    sa.Column('valor_base_mensal', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('dia_previsto_pagamento', sa.Integer(), nullable=True),
    sa.Column('conta_origem_id', sa.Integer(), nullable=True),
    sa.Column('conta_bancaria_id', sa.Integer(), nullable=True),
    sa.Column('recorrente', sa.Boolean(), nullable=True),
    sa.Column('criado_em', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['conta_bancaria_id'], ['conta_bancaria.id'], ),
    sa.ForeignKeyConstraint(['conta_origem_id'], ['conta_patrimonio.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('nome')
    )
    op.create_table('lancamento_agregado',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('item_agregado_id', sa.Integer(), nullable=True),
    sa.Column('cartao_id', sa.Integer(), nullable=False),
    sa.Column('categoria_id', sa.Integer(), nullable=False),
    sa.Column('descricao', sa.String(length=200), nullable=False),
    sa.Column('valor', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('data_compra', sa.Date(), nullable=False),
    sa.Column('mes_fatura', sa.Date(), nullable=False),
    sa.Column('numero_parcela', sa.Integer(), nullable=True),
    sa.Column('total_parcelas', sa.Integer(), nullable=True),
    sa.Column('observacoes', sa.Text(), nullable=True),
    sa.Column('is_recorrente', sa.Boolean(), nullable=True),
    sa.Column('item_despesa_id', sa.Integer(), nullable=True),
    sa.Column('compra_id', sa.String(length=36), nullable=True),
    sa.Column('descricao_original', sa.Text(), nullable=True),
    sa.Column('descricao_original_normalizada', sa.Text(), nullable=True),
    sa.Column('descricao_exibida', sa.Text(), nullable=True),
    sa.Column('is_importado', sa.Boolean(), nullable=True),
    sa.Column('origem_importacao', sa.String(length=20), nullable=True),
    sa.Column('criado_em', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['cartao_id'], ['item_despesa.id'], ),
    sa.ForeignKeyConstraint(['categoria_id'], ['categoria.id'], ),
    sa.ForeignKeyConstraint(['item_agregado_id'], ['item_agregado.id'], ),
    sa.ForeignKeyConstraint(['item_despesa_id'], ['item_despesa.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('lancamento_agregado', schema=None) as batch_op:
        batch_op.create_index('idx_lanc_agregado_data', ['data_compra'], unique=False)
        batch_op.create_index('idx_lanc_agregado_fatura', ['mes_fatura'], unique=False)
        batch_op.create_index('idx_lanc_agregado_item_fatura', ['item_agregado_id', 'mes_fatura'], unique=False)
        batch_op.create_index(batch_op.f('ix_lancamento_agregado_compra_id'), ['compra_id'], unique=False)

    op.create_table('orcamento',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('item_despesa_id', sa.Integer(), nullable=False),
    sa.Column('mes_referencia', sa.Date(), nullable=False),
    sa.Column('valor_planejado', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('observacoes', sa.Text(), nullable=True),
    sa.Column('criado_em', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['item_despesa_id'], ['item_despesa.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('orcamento', schema=None) as batch_op:
        batch_op.create_index('idx_orcamento_item_mes', ['item_despesa_id', 'mes_referencia'], unique=False)

    op.create_table('orcamento_agregado',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('item_agregado_id', sa.Integer(), nullable=False),
    sa.Column('mes_referencia', sa.Date(), nullable=False),
    sa.Column('valor_teto', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('observacoes', sa.Text(), nullable=True),
    sa.Column('vigencia_inicio', sa.Date(), nullable=False),
    sa.Column('vigencia_fim', sa.Date(), nullable=True),
    sa.Column('ativo', sa.Boolean(), nullable=True),
    sa.Column('criado_em', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['item_agregado_id'], ['item_agregado.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('orcamento_agregado', schema=None) as batch_op:
        batch_op.create_index('idx_orc_agregado_item_mes', ['item_agregado_id', 'mes_referencia'], unique=False)

    op.create_table('transferencia',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('conta_origem_id', sa.Integer(), nullable=False),
    sa.Column('conta_destino_id', sa.Integer(), nullable=False),
    sa.Column('valor', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('data_transferencia', sa.Date(), nullable=False),
    sa.Column('descricao', sa.String(length=200), nullable=True),
    sa.Column('observacoes', sa.Text(), nullable=True),
    sa.Column('criado_em', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['conta_destino_id'], ['conta_patrimonio.id'], ),
    sa.ForeignKeyConstraint(['conta_origem_id'], ['conta_patrimonio.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('transferencia', schema=None) as batch_op:
        batch_op.create_index('idx_transf_data', ['data_transferencia'], unique=False)
        batch_op.create_index('idx_transf_destino', ['conta_destino_id'], unique=False)
        batch_op.create_index('idx_transf_origem', ['conta_origem_id'], unique=False)

    op.create_table('veiculo',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nome', sa.String(length=100), nullable=False),
    sa.Column('tipo', sa.String(length=20), nullable=False),
    sa.Column('combustivel', sa.String(length=20), nullable=False),
    sa.Column('autonomia_km_l', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('data_inicio', sa.Date(), nullable=True),
    sa.Column('categoria_combustivel_id', sa.Integer(), nullable=True),
    sa.Column('combustivel_valor_mensal', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('ipva_categoria_id', sa.Integer(), nullable=True),
    sa.Column('ipva_mes', sa.Integer(), nullable=True),
    sa.Column('ipva_valor', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('seguro_categoria_id', sa.Integer(), nullable=True),
    sa.Column('seguro_mes', sa.Integer(), nullable=True),
    sa.Column('seguro_valor', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('licenciamento_categoria_id', sa.Integer(), nullable=True),
    sa.Column('licenciamento_mes', sa.Integer(), nullable=True),
    sa.Column('licenciamento_valor', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('preco_medio_combustivel', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('km_estimado_acumulado', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('km_estimado_ultimo_calculo_em', sa.DateTime(), nullable=True),
    sa.Column('km_estimado_ultimo_despesa_prevista_id', sa.Integer(), nullable=True),
    sa.Column('criado_em', sa.DateTime(), nullable=True),
    sa.Column('atualizado_em', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['categoria_combustivel_id'], ['categoria.id'], ),
    sa.ForeignKeyConstraint(['ipva_categoria_id'], ['categoria.id'], ),
    sa.ForeignKeyConstraint(['licenciamento_categoria_id'], ['categoria.id'], ),
    sa.ForeignKeyConstraint(['seguro_categoria_id'], ['categoria.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('contrato_consorcio',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nome', sa.String(length=100), nullable=False),
    sa.Column('valor_inicial', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('taxa_correcao', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('tipo_reajuste', sa.String(length=20), nullable=True),
    sa.Column('valor_reajuste', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('numero_parcelas', sa.Integer(), nullable=False),
    sa.Column('mes_inicio', sa.Date(), nullable=False),
    sa.Column('mes_contemplacao', sa.Date(), nullable=True),
    sa.Column('valor_premio', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('item_despesa_id', sa.Integer(), nullable=True),
    sa.Column('item_receita_id', sa.Integer(), nullable=True),
    sa.Column('ativo', sa.Boolean(), nullable=True),
    sa.Column('observacoes', sa.Text(), nullable=True),
    sa.Column('criado_em', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['item_despesa_id'], ['item_despesa.id'], ),
    sa.ForeignKeyConstraint(['item_receita_id'], ['item_receita.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('despesa_prevista_acao_log',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('despesa_prevista_id', sa.Integer(), nullable=False),
    sa.Column('acao', sa.String(length=30), nullable=False),
    sa.Column('ajustar_ciclo', sa.Boolean(), nullable=True),
    sa.Column('despesa_prevista_criada_id', sa.Integer(), nullable=True),
    sa.Column('criado_em', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['despesa_prevista_criada_id'], ['despesa_prevista.id'], ),
    sa.ForeignKeyConstraint(['despesa_prevista_id'], ['despesa_prevista.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('financiamento_amortizacao_extra',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('financiamento_id', sa.Integer(), nullable=False),
    sa.Column('data', sa.Date(), nullable=False),
    sa.Column('valor', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('tipo', sa.String(length=20), nullable=False),
    sa.Column('observacoes', sa.Text(), nullable=True),
    sa.Column('criado_em', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['financiamento_id'], ['financiamento.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('financiamento_amortizacao_extra', schema=None) as batch_op:
        batch_op.create_index('idx_amort_data', ['data'], unique=False)
        batch_op.create_index('idx_amort_financ', ['financiamento_id'], unique=False)

    op.create_table('financiamento_seguro_vigencia',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('financiamento_id', sa.Integer(), nullable=False),
    sa.Column('competencia_inicio', sa.Date(), nullable=False),
    sa.Column('valor_mensal', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('saldo_devedor_vigencia', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('taxa_percentual', sa.Numeric(precision=8, scale=6), nullable=True),
    sa.Column('data_nascimento_segurado', sa.Date(), nullable=True),
    sa.Column('observacoes', sa.Text(), nullable=True),
    sa.Column('vigencia_ativa', sa.Boolean(), nullable=True),
    sa.Column('data_encerramento', sa.Date(), nullable=True),
    sa.Column('criado_em', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['financiamento_id'], ['financiamento.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('financiamento_seguro_vigencia', schema=None) as batch_op:
        batch_op.create_index('idx_seguro_vig_ativa', ['vigencia_ativa'], unique=False)
        batch_op.create_index('idx_seguro_vig_comp', ['competencia_inicio'], unique=False)
        batch_op.create_index('idx_seguro_vig_financ', ['financiamento_id'], unique=False)

    op.create_table('receita_orcamento',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('item_receita_id', sa.Integer(), nullable=False),
    sa.Column('mes_referencia', sa.Date(), nullable=False),
    sa.Column('valor_esperado', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('periodicidade', sa.String(length=20), nullable=True),
    sa.Column('observacoes', sa.Text(), nullable=True),
    sa.Column('criado_em', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['item_receita_id'], ['item_receita.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('receita_orcamento', schema=None) as batch_op:
        batch_op.create_index('idx_rec_orc_item_mes', ['item_receita_id', 'mes_referencia'], unique=False)

    op.create_table('veiculo_financiamento',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('veiculo_id', sa.Integer(), nullable=False),
    sa.Column('valor_bem', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('entrada', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('valor_financiado', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('numero_parcelas', sa.Integer(), nullable=False),
    sa.Column('taxa_juros_mensal', sa.Numeric(precision=6, scale=3), nullable=False),
    sa.Column('indexador_tipo', sa.String(length=20), nullable=True),
    sa.Column('iof_percentual', sa.Numeric(precision=6, scale=3), nullable=False),
    sa.Column('iof_valor', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('categoria_id', sa.Integer(), nullable=True),
    sa.Column('custo_total_financiamento', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('criado_em', sa.DateTime(), nullable=True),
    sa.Column('atualizado_em', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['categoria_id'], ['categoria.id'], ),
    sa.ForeignKeyConstraint(['veiculo_id'], ['veiculo.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('veiculo_id')
    )
    op.create_table('veiculo_regra_manutencao_km',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('veiculo_id', sa.Integer(), nullable=False),
    sa.Column('tipo_evento', sa.String(length=50), nullable=False),
    sa.Column('intervalo_km', sa.Integer(), nullable=False),
    sa.Column('meses_intervalo', sa.Integer(), nullable=True),
    sa.Column('custo_estimado', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('categoria_id', sa.Integer(), nullable=False),
    sa.Column('ativo', sa.Boolean(), nullable=True),
    sa.Column('criado_em', sa.DateTime(), nullable=True),
    sa.Column('atualizado_em', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['categoria_id'], ['categoria.id'], ),
    sa.ForeignKeyConstraint(['veiculo_id'], ['veiculo.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('veiculo_regra_manutencao_km', schema=None) as batch_op:
        batch_op.create_index('idx_regra_km_veiculo_tipo', ['veiculo_id', 'tipo_evento'], unique=False)

    op.create_table('receita_realizada',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('item_receita_id', sa.Integer(), nullable=True),
    sa.Column('data_recebimento', sa.Date(), nullable=False),
    sa.Column('valor_recebido', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('mes_referencia', sa.Date(), nullable=False),
    sa.Column('conta_origem_id', sa.Integer(), nullable=True),
    sa.Column('conta_bancaria_id', sa.Integer(), nullable=True),
    sa.Column('descricao', sa.String(length=200), nullable=True),
    sa.Column('orcamento_id', sa.Integer(), nullable=True),
    sa.Column('observacoes', sa.Text(), nullable=True),
    sa.Column('criado_em', sa.DateTime(), nullable=True),
    sa.Column('atualizado_em', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['conta_bancaria_id'], ['conta_bancaria.id'], ),
    sa.ForeignKeyConstraint(['conta_origem_id'], ['conta_patrimonio.id'], ),
    sa.ForeignKeyConstraint(['item_receita_id'], ['item_receita.id'], ),
    sa.ForeignKeyConstraint(['orcamento_id'], ['receita_orcamento.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('receita_realizada', schema=None) as batch_op:
        batch_op.create_index('idx_rec_real_competencia', ['mes_referencia'], unique=False)
        batch_op.create_index('idx_rec_real_data', ['data_recebimento'], unique=False)
        batch_op.create_index('idx_rec_real_item_comp', ['item_receita_id', 'mes_referencia'], unique=False)

    op.create_table('veiculo_ciclo_manutencao',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('veiculo_id', sa.Integer(), nullable=False),
    sa.Column('tipo_evento', sa.String(length=50), nullable=False),
    sa.Column('regra_id', sa.Integer(), nullable=False),
    sa.Column('intervalo_km', sa.Integer(), nullable=False),
    sa.Column('criado_em', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['regra_id'], ['veiculo_regra_manutencao_km.id'], ),
    sa.ForeignKeyConstraint(['veiculo_id'], ['veiculo.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('veiculo_ciclo_manutencao', schema=None) as batch_op:
        batch_op.create_index('idx_ciclo_veiculo_tipo', ['veiculo_id', 'tipo_evento'], unique=False)

    op.create_table('movimento_financeiro',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('conta_bancaria_id', sa.Integer(), nullable=False),
    sa.Column('tipo', sa.String(length=20), nullable=False),
    sa.Column('valor', sa.Numeric(precision=15, scale=2), nullable=False),
    sa.Column('descricao', sa.String(length=200), nullable=False),
    sa.Column('data_movimento', sa.Date(), nullable=False),
    sa.Column('fatura_id', sa.Integer(), nullable=True),
    sa.Column('conta_id', sa.Integer(), nullable=True),
    sa.Column('receita_realizada_id', sa.Integer(), nullable=True),
    sa.Column('transferencia_id', sa.String(length=36), nullable=True),
    sa.Column('origem', sa.String(length=20), nullable=True),
    sa.Column('ajustavel', sa.Boolean(), nullable=True),
    sa.Column('criado_em', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['conta_bancaria_id'], ['conta_bancaria.id'], ),
    sa.ForeignKeyConstraint(['conta_id'], ['conta.id'], ),
    sa.ForeignKeyConstraint(['fatura_id'], ['conta.id'], ),
    sa.ForeignKeyConstraint(['receita_realizada_id'], ['receita_realizada.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('movimento_financeiro', schema=None) as batch_op:
        batch_op.create_index('idx_movimento_conta', ['conta_bancaria_id'], unique=False)
        batch_op.create_index('idx_movimento_data', ['data_movimento'], unique=False)
        batch_op.create_index('idx_movimento_fatura', ['fatura_id'], unique=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('movimento_financeiro', schema=None) as batch_op:
        batch_op.drop_index('idx_movimento_fatura')
        batch_op.drop_index('idx_movimento_data')
        batch_op.drop_index('idx_movimento_conta')

    op.drop_table('movimento_financeiro')
    with op.batch_alter_table('veiculo_ciclo_manutencao', schema=None) as batch_op:
        batch_op.drop_index('idx_ciclo_veiculo_tipo')

    op.drop_table('veiculo_ciclo_manutencao')
    with op.batch_alter_table('receita_realizada', schema=None) as batch_op:
        batch_op.drop_index('idx_rec_real_item_comp')
        batch_op.drop_index('idx_rec_real_data')
        batch_op.drop_index('idx_rec_real_competencia')

    op.drop_table('receita_realizada')
    with op.batch_alter_table('veiculo_regra_manutencao_km', schema=None) as batch_op:
        batch_op.drop_index('idx_regra_km_veiculo_tipo')

    op.drop_table('veiculo_regra_manutencao_km')
    op.drop_table('veiculo_financiamento')
    with op.batch_alter_table('receita_orcamento', schema=None) as batch_op:
        batch_op.drop_index('idx_rec_orc_item_mes')

    op.drop_table('receita_orcamento')
    with op.batch_alter_table('financiamento_seguro_vigencia', schema=None) as batch_op:
        batch_op.drop_index('idx_seguro_vig_financ')
        batch_op.drop_index('idx_seguro_vig_comp')
        batch_op.drop_index('idx_seguro_vig_ativa')

    op.drop_table('financiamento_seguro_vigencia')
    with op.batch_alter_table('financiamento_amortizacao_extra', schema=None) as batch_op:
        batch_op.drop_index('idx_amort_financ')
        batch_op.drop_index('idx_amort_data')

    op.drop_table('financiamento_amortizacao_extra')
    op.drop_table('despesa_prevista_acao_log')
    op.drop_table('contrato_consorcio')
    op.drop_table('veiculo')
    with op.batch_alter_table('transferencia', schema=None) as batch_op:
        batch_op.drop_index('idx_transf_origem')
        batch_op.drop_index('idx_transf_destino')
        batch_op.drop_index('idx_transf_data')

    op.drop_table('transferencia')
    with op.batch_alter_table('orcamento_agregado', schema=None) as batch_op:
        batch_op.drop_index('idx_orc_agregado_item_mes')

    op.drop_table('orcamento_agregado')
    with op.batch_alter_table('orcamento', schema=None) as batch_op:
        batch_op.drop_index('idx_orcamento_item_mes')

    op.drop_table('orcamento')
    with op.batch_alter_table('lancamento_agregado', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_lancamento_agregado_compra_id'))
        batch_op.drop_index('idx_lanc_agregado_item_fatura')
        batch_op.drop_index('idx_lanc_agregado_fatura')
        batch_op.drop_index('idx_lanc_agregado_data')

    op.drop_table('lancamento_agregado')
    op.drop_table('item_receita')
    op.drop_table('financiamento')
    with op.batch_alter_table('despesa_prevista', schema=None) as batch_op:
        batch_op.drop_index('idx_desp_prev_origem_data')

    op.drop_table('despesa_prevista')
    op.drop_table('config_agregador')
    op.drop_table('preferencia')
    op.drop_table('item_despesa')
    op.drop_table('item_agregado')
    with op.batch_alter_table('indexador_mensal', schema=None) as batch_op:
        batch_op.drop_index('idx_indexador_nome_data')

    op.drop_table('indexador_mensal')
    op.drop_table('grupo_agregador')
    with op.batch_alter_table('financiamento_parcela', schema=None) as batch_op:
        batch_op.drop_index('idx_fin_parc_venc')
        batch_op.drop_index('idx_fin_parc_status')
        batch_op.drop_index('idx_fin_parc_financ')

    op.drop_table('financiamento_parcela')
    op.drop_table('conta_patrimonio')
    op.drop_table('conta_bancaria')
    with op.batch_alter_table('conta', schema=None) as batch_op:
        batch_op.drop_index('idx_conta_vencimento')
        batch_op.drop_index('idx_conta_status')
        batch_op.drop_index('idx_conta_item_mes')

    op.drop_table('conta')
    op.drop_table('categoria')
    # ### end Alembic commands ###
