"""
Modelos do banco de dados - Sistema de Controle Financeiro

15 Tabelas organizadas em 3 módulos:
- Módulo 1: Orçamento (Receitas e Despesas) - 12 tabelas (incluindo GrupoAgregador)
- Módulo 2: Automação (Consórcios) - 1 tabela
- Módulo 3: Patrimônio (Caixinhas) - 2 tabelas
"""
from datetime import datetime, date
import json
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


# ============================================================================
# MÓDULO 1: ORÇAMENTO (RECEITAS E DESPESAS)
# ============================================================================

class Categoria(db.Model):
    """
    Agrupador de despesas (ex: Moradia, Transporte, Alimentação)
    """
    __tablename__ = 'categoria'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False, unique=True)
    descricao = db.Column(db.Text)
    cor = db.Column(db.String(7), default='#6c757d')  # Código hexadecimal
    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    # Relacionamentos
    itens_despesa = db.relationship('ItemDespesa', back_populates='categoria', lazy='dynamic')

    def __repr__(self):
        return f'<Categoria {self.nome}>'

    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'descricao': self.descricao,
            'cor': self.cor,
            'ativo': self.ativo
        }


class ItemDespesa(db.Model):
    """
    Item de gasto - pode ser 'Simples' (boleto) ou 'Agregador' (cartão)
    """
    __tablename__ = 'item_despesa'

    id = db.Column(db.Integer, primary_key=True)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categoria.id'), nullable=True)  # Opcional para cartões
    nome = db.Column(db.String(100), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)  # 'Simples' ou 'Agregador'
    descricao = db.Column(db.Text)
    ativo = db.Column(db.Boolean, default=True)

    # Campos para despesas
    valor = db.Column(db.Numeric(10, 2))  # Valor previsto/orçado
    valor_pago = db.Column(db.Numeric(10, 2))  # Valor realmente pago (pode ser diferente)
    data_vencimento = db.Column(db.Date)
    data_pagamento = db.Column(db.Date)
    pago = db.Column(db.Boolean, default=False)
    recorrente = db.Column(db.Boolean, default=False)
    tipo_recorrencia = db.Column(db.String(20), default='mensal')  # 'semanal', 'a_cada_2_semanas', 'mensal' ou 'anual'
    mes_competencia = db.Column(db.String(7))  # Formato: YYYY-MM (mês do salário que paga)

    # Campos para recorrência paga via cartão
    meio_pagamento = db.Column(db.String(20))  # 'boleto', 'debito', 'cartao', 'pix', etc. (None = não especificado)
    cartao_id = db.Column(db.Integer, db.ForeignKey('item_despesa.id'), nullable=True)  # Obrigatório quando meio_pagamento='cartao'
    item_agregado_id = db.Column(db.Integer, db.ForeignKey('item_agregado.id'), nullable=True)  # Categoria do cartão (opcional)

    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    # Relacionamentos
    categoria = db.relationship('Categoria', back_populates='itens_despesa')
    config_agregador = db.relationship('ConfigAgregador', back_populates='item_despesa', uselist=False)
    orcamentos = db.relationship('Orcamento', back_populates='item_despesa', lazy='dynamic')
    contas = db.relationship('Conta', back_populates='item_despesa', lazy='dynamic')
    itens_agregados = db.relationship('ItemAgregado', back_populates='item_despesa_pai', lazy='dynamic', foreign_keys='ItemAgregado.item_despesa_id')

    # Relacionamentos para recorrência paga via cartão
    cartao = db.relationship(
        'ItemDespesa',
        remote_side=[id],
        foreign_keys=[cartao_id],
        post_update=True,
        uselist=False
    )
    item_agregado = db.relationship(
        'ItemAgregado',
        foreign_keys=[item_agregado_id],
        post_update=True,
        uselist=False
    )

    def __repr__(self):
        return f'<ItemDespesa {self.nome} ({self.tipo})>'

    def to_dict(self):
        result = {
            'id': self.id,
            'categoria_id': self.categoria_id,
            'nome': self.nome,
            'tipo': self.tipo,
            'descricao': self.descricao,
            'ativo': self.ativo,
            'valor': float(self.valor) if self.valor else None,
            'valor_pago': float(self.valor_pago) if self.valor_pago else None,
            'data_vencimento': self.data_vencimento.isoformat() if self.data_vencimento else None,
            'data_pagamento': self.data_pagamento.isoformat() if self.data_pagamento else None,
            'pago': self.pago,
            'recorrente': self.recorrente,
            'tipo_recorrencia': self.tipo_recorrencia,
            'mes_competencia': self.mes_competencia,
            'meio_pagamento': self.meio_pagamento,
            'cartao_id': self.cartao_id,
            'item_agregado_id': self.item_agregado_id
        }

        # Adicionar categoria apenas se existir
        if self.categoria:
            result['categoria'] = {
                'id': self.categoria.id,
                'nome': self.categoria.nome
            }

        # Adicionar dados do cartão se for recorrência paga via cartão
        if self.cartao:
            result['cartao'] = {
                'id': self.cartao.id,
                'nome': self.cartao.nome
            }

        # Adicionar dados da categoria do cartão se especificado
        if self.item_agregado:
            result['item_agregado'] = {
                'id': self.item_agregado.id,
                'nome': self.item_agregado.nome
            }

        return result


class ConfigAgregador(db.Model):
    """
    Configuração específica para itens do tipo 'Agregador' (Cartão de Crédito)
    """
    __tablename__ = 'config_agregador'

    id = db.Column(db.Integer, primary_key=True)
    item_despesa_id = db.Column(db.Integer, db.ForeignKey('item_despesa.id'), nullable=False, unique=True)
    dia_fechamento = db.Column(db.Integer, nullable=False)  # 1-31
    dia_vencimento = db.Column(db.Integer, nullable=False)  # 1-31
    limite_credito = db.Column(db.Numeric(10, 2))
    numero_cartao = db.Column(db.String(19))  # Formato: 1234 5678 9012 3456
    data_validade = db.Column(db.String(7))  # Formato: MM/AAAA
    codigo_seguranca = db.Column(db.String(4))  # CVV/CVC (armazenado de forma segura)
    tem_codigo = db.Column(db.Boolean, default=True)  # Se o cartão possui código de segurança
    observacoes = db.Column(db.Text)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    # Relacionamentos
    item_despesa = db.relationship('ItemDespesa', back_populates='config_agregador')

    def __repr__(self):
        return f'<ConfigAgregador Item:{self.item_despesa_id} Fecha:{self.dia_fechamento} Vence:{self.dia_vencimento}>'

    def to_dict(self):
        return {
            'id': self.id,
            'item_despesa_id': self.item_despesa_id,
            'dia_fechamento': self.dia_fechamento,
            'dia_vencimento': self.dia_vencimento,
            'limite_credito': float(self.limite_credito) if self.limite_credito else None,
            'numero_cartao': self.numero_cartao,  # Número completo
            'data_validade': self.data_validade,  # MM/AAAA
            'tem_codigo': self.tem_codigo if self.tem_codigo is not None else True,  # Se o cartão possui código de segurança
            'observacoes': self.observacoes
        }


class Orcamento(db.Model):
    """
    Plano mensal de gastos para itens 'Simples' (ex: Aluguel, Internet)
    """
    __tablename__ = 'orcamento'

    id = db.Column(db.Integer, primary_key=True)
    item_despesa_id = db.Column(db.Integer, db.ForeignKey('item_despesa.id'), nullable=False)
    mes_referencia = db.Column(db.Date, nullable=False)  # Primeiro dia do mês (YYYY-MM-01)
    valor_planejado = db.Column(db.Numeric(10, 2), nullable=False)
    observacoes = db.Column(db.Text)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    # Relacionamentos
    item_despesa = db.relationship('ItemDespesa', back_populates='orcamentos')

    # Índice composto para busca rápida
    __table_args__ = (
        db.Index('idx_orcamento_item_mes', 'item_despesa_id', 'mes_referencia'),
    )

    def __repr__(self):
        return f'<Orcamento Item:{self.item_despesa_id} Mês:{self.mes_referencia} R${self.valor_planejado}>'

    def to_dict(self):
        return {
            'id': self.id,
            'item_despesa_id': self.item_despesa_id,
            'mes_referencia': self.mes_referencia.strftime('%Y-%m-%d'),
            'valor_planejado': float(self.valor_planejado),
            'observacoes': self.observacoes
        }


class Conta(db.Model):
    """
    Contas a pagar - boletos, faturas e compromissos financeiros
    """
    __tablename__ = 'conta'

    id = db.Column(db.Integer, primary_key=True)
    item_despesa_id = db.Column(db.Integer, db.ForeignKey('item_despesa.id'), nullable=False)
    financiamento_parcela_id = db.Column(db.Integer, db.ForeignKey('financiamento_parcela.id'))
    mes_referencia = db.Column(db.Date, nullable=False)
    descricao = db.Column(db.String(200), nullable=False)
    valor = db.Column(db.Numeric(10, 2), nullable=False)
    data_vencimento = db.Column(db.Date, nullable=False)
    data_pagamento = db.Column(db.Date)
    status_pagamento = db.Column(db.String(20), default='Pendente')  # 'Pendente', 'Pago', 'Atrasado'
    debito_automatico = db.Column(db.Boolean, default=False)
    numero_parcela = db.Column(db.Integer)  # Ex: parcela 2 de 12
    total_parcelas = db.Column(db.Integer)
    observacoes = db.Column(db.Text)

    # Campos para fatura de cartão (planejado vs executado)
    is_fatura_cartao = db.Column(db.Boolean, default=False)  # Identifica se é fatura de cartão
    valor_planejado = db.Column(db.Numeric(10, 2))  # Orçamento total do cartão (soma das categorias)
    valor_executado = db.Column(db.Numeric(10, 2))  # Valor real gasto (soma dos lançamentos)
    estouro_orcamento = db.Column(db.Boolean, default=False)  # Flag de alerta
    cartao_competencia = db.Column(db.Date)  # Mês de competência (YYYY-MM-01)

    # Campos para fechamento de fatura
    status_fatura = db.Column(db.String(10), default='ABERTA')  # 'ABERTA', 'FECHADA', 'PAGA'
    data_consolidacao = db.Column(db.DateTime, nullable=True)  # Data em que a fatura foi fechada
    valor_consolidado = db.Column(db.Numeric(12, 2), nullable=True)  # Valor executado no momento do fechamento

    # ==========================================================
    # FUTURO (FASE 3): Pagamento parcial de fatura
    # Campos planejados (NÃO IMPLEMENTADOS):
    # - valor_pago: Decimal(12,2) - Valor efetivamente pago
    # - saldo_devedor: Decimal(12,2) - Diferença entre total e pago
    # - taxa_juros: Decimal(8,6) - Taxa de juros mensal do rotativo
    # - iof: Decimal(8,6) - Alíquota de IOF sobre rotativo
    #
    # ATUALMENTE: pagamento é sempre integral
    # Fatura só vai para status='PAGA' após pagamento total
    # ==========================================================

    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    # Relacionamentos
    item_despesa = db.relationship('ItemDespesa', back_populates='contas')
    financiamento_parcela = db.relationship('FinanciamentoParcela', foreign_keys=[financiamento_parcela_id])

    # Índices
    __table_args__ = (
        db.Index('idx_conta_vencimento', 'data_vencimento'),
        db.Index('idx_conta_status', 'status_pagamento'),
        db.Index('idx_conta_item_mes', 'item_despesa_id', 'mes_referencia'),
    )

    def __repr__(self):
        return f'<Conta {self.descricao} R${self.valor} Venc:{self.data_vencimento}>'

    def to_dict(self):
        return {
            'id': self.id,
            'item_despesa_id': self.item_despesa_id,
            'financiamento_parcela_id': self.financiamento_parcela_id,
            'mes_referencia': self.mes_referencia.strftime('%Y-%m-%d'),
            'descricao': self.descricao,
            'valor': float(self.valor),
            'data_vencimento': self.data_vencimento.strftime('%Y-%m-%d'),
            'data_pagamento': self.data_pagamento.strftime('%Y-%m-%d') if self.data_pagamento else None,
            'status_pagamento': self.status_pagamento,
            'debito_automatico': self.debito_automatico,
            'numero_parcela': self.numero_parcela,
            'total_parcelas': self.total_parcelas,
            'observacoes': self.observacoes,
            # Campos de fatura de cartão
            'is_fatura_cartao': self.is_fatura_cartao,
            'valor_planejado': float(self.valor_planejado) if self.valor_planejado else None,
            'valor_executado': float(self.valor_executado) if self.valor_executado else None,
            'estouro_orcamento': self.estouro_orcamento,
            'cartao_competencia': self.cartao_competencia.strftime('%Y-%m-%d') if self.cartao_competencia else None,
            # Campos de fechamento de fatura
            'status_fatura': self.status_fatura,
            'data_consolidacao': self.data_consolidacao.strftime('%Y-%m-%d %H:%M:%S') if self.data_consolidacao else None,
            'valor_consolidado': float(self.valor_consolidado) if self.valor_consolidado else None
        }


class GrupoAgregador(db.Model):
    """
    Grupo opcional para consolidação de categorias entre múltiplos cartões

    Permite agrupar categorias com o mesmo nome de diferentes cartões para:
    - Análise consolidada (ex: Farmácia do Cartão A + Farmácia do Cartão B)
    - Alertas de limite total entre cartões
    - Planejamento familiar/compartilhado

    IMPORTANTE: Grupos NÃO possuem orçamento próprio, NÃO bloqueiam lançamentos.
    São apenas para consolidação e análise.
    """
    __tablename__ = 'grupo_agregador'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False, unique=True)
    descricao = db.Column(db.Text)  # Ex: "Farmácia compartilhada - Cartão João + Maria"
    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    # Relacionamentos
    categorias = db.relationship('ItemAgregado', back_populates='grupo', lazy='dynamic')

    def __repr__(self):
        return f'<GrupoAgregador {self.nome}>'

    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'descricao': self.descricao,
            'ativo': self.ativo
        }


class ItemAgregado(db.Model):
    """
    Sub-itens de um item 'Agregador' (ex: Supermercado, Farmácia dentro do Cartão VISA)

    Também conhecido como: Categoria Agregadora de Cartão
    Representa uma categoria de gastos dentro de um cartão específico

    Pode opcionalmente pertencer a um GrupoAgregador para consolidação entre cartões
    """
    __tablename__ = 'item_agregado'

    id = db.Column(db.Integer, primary_key=True)
    item_despesa_id = db.Column(db.Integer, db.ForeignKey('item_despesa.id'), nullable=False)
    nome = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.Text)
    ativo = db.Column(db.Boolean, default=True)

    # Grupo opcional para consolidação entre cartões
    grupo_agregador_id = db.Column(db.Integer, db.ForeignKey('grupo_agregador.id'), nullable=True)

    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    # Relacionamentos
    item_despesa_pai = db.relationship('ItemDespesa', back_populates='itens_agregados', foreign_keys=[item_despesa_id])
    orcamentos_agregados = db.relationship('OrcamentoAgregado', back_populates='item_agregado', lazy='dynamic')
    lancamentos_agregados = db.relationship('LancamentoAgregado', back_populates='item_agregado', lazy='dynamic')
    grupo = db.relationship('GrupoAgregador', back_populates='categorias')

    def __repr__(self):
        return f'<ItemAgregado {self.nome}>'

    def to_dict(self):
        result = {
            'id': self.id,
            'item_despesa_id': self.item_despesa_id,
            'nome': self.nome,
            'descricao': self.descricao,
            'ativo': self.ativo,
            'grupo_agregador_id': self.grupo_agregador_id
        }

        # Incluir dados do grupo se existir
        if self.grupo:
            result['grupo'] = {
                'id': self.grupo.id,
                'nome': self.grupo.nome
            }

        return result


class OrcamentoAgregado(db.Model):
    """
    Teto de gastos mensal para sub-itens do cartão
    """
    __tablename__ = 'orcamento_agregado'

    id = db.Column(db.Integer, primary_key=True)
    item_agregado_id = db.Column(db.Integer, db.ForeignKey('item_agregado.id'), nullable=False)
    mes_referencia = db.Column(db.Date, nullable=False)
    valor_teto = db.Column(db.Numeric(10, 2), nullable=False)
    observacoes = db.Column(db.Text)

    # Histórico de vigência do orçamento
    vigencia_inicio = db.Column(db.Date, nullable=False, default=lambda: date.today().replace(day=1))  # Primeiro dia do mês
    vigencia_fim = db.Column(db.Date)  # null = vigência atual/futura
    ativo = db.Column(db.Boolean, default=True)  # Flag de ativo

    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    # Relacionamentos
    item_agregado = db.relationship('ItemAgregado', back_populates='orcamentos_agregados')

    # Índice composto
    __table_args__ = (
        db.Index('idx_orc_agregado_item_mes', 'item_agregado_id', 'mes_referencia'),
    )

    def __repr__(self):
        return f'<OrcamentoAgregado Item:{self.item_agregado_id} Mês:{self.mes_referencia} Teto:R${self.valor_teto}>'

    def to_dict(self):
        return {
            'id': self.id,
            'item_agregado_id': self.item_agregado_id,
            'mes_referencia': self.mes_referencia.strftime('%Y-%m-%d'),
            'valor_teto': float(self.valor_teto),
            'observacoes': self.observacoes,
            # Histórico de vigência
            'vigencia_inicio': self.vigencia_inicio.strftime('%Y-%m-%d') if self.vigencia_inicio else None,
            'vigencia_fim': self.vigencia_fim.strftime('%Y-%m-%d') if self.vigencia_fim else None,
            'ativo': self.ativo
        }


class LancamentoAgregado(db.Model):
    """
    Gasto real no cartão de crédito

    IMPORTANTE: item_agregado_id é OPCIONAL
    - Lançamentos COM categoria: consomem limite orçamentário
    - Lançamentos SEM categoria: vão apenas para a fatura, sem controle de limite
    """
    __tablename__ = 'lancamento_agregado'

    id = db.Column(db.Integer, primary_key=True)
    item_agregado_id = db.Column(db.Integer, db.ForeignKey('item_agregado.id'), nullable=True)
    cartao_id = db.Column(db.Integer, db.ForeignKey('item_despesa.id'), nullable=False)  # Referência direta ao cartão
    categoria_id = db.Column(db.Integer, db.ForeignKey('categoria.id'), nullable=False)  # Categoria da DESPESA (analítica)
    descricao = db.Column(db.String(200), nullable=False)
    valor = db.Column(db.Numeric(10, 2), nullable=False)
    data_compra = db.Column(db.Date, nullable=False)
    mes_fatura = db.Column(db.Date, nullable=False)  # Mês que a fatura fecha
    numero_parcela = db.Column(db.Integer, default=1)
    total_parcelas = db.Column(db.Integer, default=1)
    observacoes = db.Column(db.Text)

    # Campos para lançamentos recorrentes (Despesas Fixas)
    is_recorrente = db.Column(db.Boolean, default=False)  # Se foi gerado por despesa recorrente
    item_despesa_id = db.Column(db.Integer, db.ForeignKey('item_despesa.id'), nullable=True)  # Referência à despesa recorrente que gerou este lançamento

    # Identificador único da compra (para parcelamento)
    # Permite identificar que parcelas pertencem à mesma compra original
    # FASE 2: Idempotência robusta - todas as parcelas de uma compra compartilham o mesmo UUID
    compra_id = db.Column(db.String(36), nullable=True, index=True)  # UUID v4

    # Campos para importação CSV (FASE 6.2)
    descricao_original = db.Column(db.Text, nullable=True)  # Texto bruto do CSV (imutável)
    descricao_original_normalizada = db.Column(db.Text, nullable=True)  # Sem parcelamento explícito (imutável)
    descricao_exibida = db.Column(db.Text, nullable=True)  # Editável pelo usuário
    is_importado = db.Column(db.Boolean, default=False)  # Flag de origem
    origem_importacao = db.Column(db.String(20), nullable=True)  # "csv", "manual", etc.

    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    # Relacionamentos
    item_agregado = db.relationship('ItemAgregado', back_populates='lancamentos_agregados')
    categoria = db.relationship('Categoria')
    item_despesa_recorrente = db.relationship(
        'ItemDespesa',
        foreign_keys=[item_despesa_id],
        post_update=True,
        uselist=False
    )

    # Índices
    __table_args__ = (
        db.Index('idx_lanc_agregado_data', 'data_compra'),
        db.Index('idx_lanc_agregado_fatura', 'mes_fatura'),
        db.Index('idx_lanc_agregado_item_fatura', 'item_agregado_id', 'mes_fatura'),
    )

    def __repr__(self):
        return f'<LancamentoAgregado {self.descricao} R${self.valor} Fatura:{self.mes_fatura}>'

    def to_dict(self):
        return {
            'id': self.id,
            'item_agregado_id': self.item_agregado_id,
            'descricao': self.descricao,
            'valor': float(self.valor),
            'data_compra': self.data_compra.strftime('%Y-%m-%d'),
            'mes_fatura': self.mes_fatura.strftime('%Y-%m-%d'),
            'numero_parcela': self.numero_parcela,
            'total_parcelas': self.total_parcelas,
            'observacoes': self.observacoes,
            'is_recorrente': self.is_recorrente,
            'item_despesa_id': self.item_despesa_id
        }


class ItemReceita(db.Model):
    """
    Fonte de receita com tipos bem definidos

    Tipos:
    - SALARIO_FIXO: Salário mensal fixo
    - GRATIFICACAO: Gratificações, cargos em comissão, funções
    - RENDA_EXTRA: Cálculos judiciais, consultorias, aulas
    - ALUGUEL: Rendimentos de aluguéis
    - RENDIMENTO_FINANCEIRO: Investimentos, dividendos
    - OUTROS: Outras fontes de receita
    """
    __tablename__ = 'item_receita'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False, unique=True)

    # Tipo expandido conforme especificação
    tipo = db.Column(db.String(30), nullable=False)
    # Valores: SALARIO_FIXO, GRATIFICACAO, RENDA_EXTRA, ALUGUEL, RENDIMENTO_FINANCEIRO, OUTROS

    descricao = db.Column(db.Text)
    ativo = db.Column(db.Boolean, default=True)

    # Campos de configuração para receitas fixas
    valor_base_mensal = db.Column(db.Numeric(10, 2))  # Valor fixo mensal (para salários)
    dia_previsto_pagamento = db.Column(db.Integer)  # Dia do mês (1-31)
    conta_origem_id = db.Column(db.Integer, db.ForeignKey('conta_patrimonio.id'))  # Conta onde entra
    recorrente = db.Column(db.Boolean, default=True)  # Se gera orçamentos automaticamente

    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    # Relacionamentos
    receitas_orcamento = db.relationship('ReceitaOrcamento', back_populates='item_receita', lazy='dynamic')
    receitas_realizadas = db.relationship('ReceitaRealizada', back_populates='item_receita', lazy='dynamic')
    conta_origem = db.relationship('ContaPatrimonio', foreign_keys=[conta_origem_id])

    def __repr__(self):
        return f'<ItemReceita {self.nome} ({self.tipo})>'

    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'tipo': self.tipo,
            'descricao': self.descricao,
            'ativo': self.ativo,
            'valor_base_mensal': float(self.valor_base_mensal) if self.valor_base_mensal else None,
            'dia_previsto_pagamento': self.dia_previsto_pagamento,
            'conta_origem_id': self.conta_origem_id,
            'recorrente': self.recorrente
        }


class ReceitaOrcamento(db.Model):
    """
    Plano mensal de receitas esperadas (projeção)

    Periodicidade:
    - MENSAL_FIXA: Receita fixa todo mês (ex: salário)
    - EVENTUAL: Receita esporádica
    - UNICA: Receita de uma única vez
    """
    __tablename__ = 'receita_orcamento'

    id = db.Column(db.Integer, primary_key=True)
    item_receita_id = db.Column(db.Integer, db.ForeignKey('item_receita.id'), nullable=False)
    mes_referencia = db.Column(db.Date, nullable=False)  # Primeiro dia do mês (YYYY-MM-01)
    valor_esperado = db.Column(db.Numeric(10, 2), nullable=False)

    # Periodicidade da receita
    periodicidade = db.Column(db.String(20), default='MENSAL_FIXA')
    # Valores: MENSAL_FIXA, EVENTUAL, UNICA

    observacoes = db.Column(db.Text)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    # Relacionamentos
    item_receita = db.relationship('ItemReceita', back_populates='receitas_orcamento')

    # Índice composto
    __table_args__ = (
        db.Index('idx_rec_orc_item_mes', 'item_receita_id', 'mes_referencia'),
    )

    def __repr__(self):
        return f'<ReceitaOrcamento Item:{self.item_receita_id} Mês:{self.mes_referencia} R${self.valor_esperado}>'

    def to_dict(self):
        return {
            'id': self.id,
            'item_receita_id': self.item_receita_id,
            'mes_referencia': self.mes_referencia.strftime('%Y-%m-%d'),
            'valor_esperado': float(self.valor_esperado),
            'periodicidade': self.periodicidade,
            'observacoes': self.observacoes
        }


class ReceitaRealizada(db.Model):
    """
    Receita efetivamente recebida (baixa da receita)

    Registra cada recebimento real, permitindo comparar com o orçamento
    Permite receitas pontuais sem vínculo com fonte fixa (item_receita_id = NULL)
    """
    __tablename__ = 'receita_realizada'

    id = db.Column(db.Integer, primary_key=True)
    item_receita_id = db.Column(db.Integer, db.ForeignKey('item_receita.id'), nullable=True)  # Permitir NULL para receitas pontuais

    # Data efetiva do recebimento
    data_recebimento = db.Column(db.Date, nullable=False)

    # Valor recebido
    valor_recebido = db.Column(db.Numeric(10, 2), nullable=False)

    # Competência (mês de referência - ex: salário de Maio/2025 mesmo que pago em 06/06)
    mes_referencia = db.Column(db.Date, nullable=False)  # YYYY-MM-01

    # Conta onde entrou o dinheiro
    conta_origem_id = db.Column(db.Integer, db.ForeignKey('conta_patrimonio.id'))

    # Descrição detalhada
    descricao = db.Column(db.String(200))  # Ex: "Salário Maio/2025", "Cálculo judicial processo XXXXX"

    # Vinculação com orçamento (opcional)
    orcamento_id = db.Column(db.Integer, db.ForeignKey('receita_orcamento.id'))

    observacoes = db.Column(db.Text)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    item_receita = db.relationship('ItemReceita', back_populates='receitas_realizadas')
    conta_origem = db.relationship('ContaPatrimonio', foreign_keys=[conta_origem_id])
    orcamento = db.relationship('ReceitaOrcamento', foreign_keys=[orcamento_id])

    # Índices
    __table_args__ = (
        db.Index('idx_rec_real_data', 'data_recebimento'),
        db.Index('idx_rec_real_competencia', 'mes_referencia'),
        db.Index('idx_rec_real_item_comp', 'item_receita_id', 'mes_referencia'),
    )

    def __repr__(self):
        return f'<ReceitaRealizada {self.descricao} R${self.valor_recebido} Receb:{self.data_recebimento}>'

    def to_dict(self):
        result = {
            'id': self.id,
            'item_receita_id': self.item_receita_id,
            'data_recebimento': self.data_recebimento.strftime('%Y-%m-%d'),
            'valor_recebido': float(self.valor_recebido),
            'mes_referencia': self.mes_referencia.strftime('%Y-%m-%d'),
            'competencia': self.mes_referencia.strftime('%Y-%m-%d'),  # Alias para compatibilidade
            'conta_origem_id': self.conta_origem_id,
            'descricao': self.descricao,
            'orcamento_id': self.orcamento_id,
            'observacoes': self.observacoes
        }

        # Adicionar item_receita se carregado
        if self.item_receita:
            result['item_receita'] = {
                'id': self.item_receita.id,
                'nome': self.item_receita.nome,
                'tipo': self.item_receita.tipo
            }

        return result


# ============================================================================
# MÓDULO 2: AUTOMAÇÃO (CONSÓRCIOS)
# ============================================================================

class ContratoConsorcio(db.Model):
    """
    Contrato de consórcio que gera automaticamente contas e receitas
    """
    __tablename__ = 'contrato_consorcio'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    valor_inicial = db.Column(db.Numeric(10, 2), nullable=False)
    taxa_correcao = db.Column(db.Numeric(5, 2), default=0)  # Percentual - deprecated, usar tipo_reajuste
    tipo_reajuste = db.Column(db.String(20), default='nenhum')  # 'nenhum', 'percentual', 'fixo'
    valor_reajuste = db.Column(db.Numeric(10, 2), default=0)  # Valor fixo ou percentual do reajuste
    numero_parcelas = db.Column(db.Integer, nullable=False)
    mes_inicio = db.Column(db.Date, nullable=False)
    mes_contemplacao = db.Column(db.Date)  # Quando recebe o prêmio
    valor_premio = db.Column(db.Numeric(10, 2))
    item_despesa_id = db.Column(db.Integer, db.ForeignKey('item_despesa.id'))  # Item para lançar as parcelas
    item_receita_id = db.Column(db.Integer, db.ForeignKey('item_receita.id'))  # Item para lançar o prêmio
    ativo = db.Column(db.Boolean, default=True)
    observacoes = db.Column(db.Text)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<ContratoConsorcio {self.nome} {self.numero_parcelas}x>'

    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'valor_inicial': float(self.valor_inicial),
            'taxa_correcao': float(self.taxa_correcao) if self.taxa_correcao else 0,
            'tipo_reajuste': self.tipo_reajuste,
            'valor_reajuste': float(self.valor_reajuste) if self.valor_reajuste else 0,
            'numero_parcelas': self.numero_parcelas,
            'mes_inicio': self.mes_inicio.strftime('%Y-%m-%d'),
            'mes_contemplacao': self.mes_contemplacao.strftime('%Y-%m-%d') if self.mes_contemplacao else None,
            'valor_premio': float(self.valor_premio) if self.valor_premio else None,
            'item_despesa_id': self.item_despesa_id,
            'item_receita_id': self.item_receita_id,
            'ativo': self.ativo,
            'observacoes': self.observacoes
        }


# ============================================================================
# MÓDULO 3: PATRIMÔNIO (CAIXINHAS)
# ============================================================================

class ContaPatrimonio(db.Model):
    """
    Caixinhas onde o saldo é alocado (Conta Corrente, Reserva, Investimentos)
    """
    __tablename__ = 'conta_patrimonio'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False, unique=True)
    tipo = db.Column(db.String(50))  # 'Corrente', 'Poupança', 'Investimento', 'Reserva'
    saldo_inicial = db.Column(db.Numeric(10, 2), default=0)
    saldo_atual = db.Column(db.Numeric(10, 2), default=0)
    meta = db.Column(db.Numeric(10, 2))  # Meta de valor (opcional)
    cor = db.Column(db.String(7), default='#28a745')
    ativo = db.Column(db.Boolean, default=True)
    observacoes = db.Column(db.Text)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    # Relacionamentos
    transferencias_origem = db.relationship('Transferencia',
                                           foreign_keys='Transferencia.conta_origem_id',
                                           back_populates='conta_origem',
                                           lazy='dynamic')
    transferencias_destino = db.relationship('Transferencia',
                                            foreign_keys='Transferencia.conta_destino_id',
                                            back_populates='conta_destino',
                                            lazy='dynamic')

    def __repr__(self):
        return f'<ContaPatrimonio {self.nome} R${self.saldo_atual}>'

    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'tipo': self.tipo,
            'saldo_inicial': float(self.saldo_inicial),
            'saldo_atual': float(self.saldo_atual),
            'meta': float(self.meta) if self.meta else None,
            'cor': self.cor,
            'ativo': self.ativo,
            'observacoes': self.observacoes
        }


class Transferencia(db.Model):
    """
    Movimentação de dinheiro entre contas de patrimônio
    """
    __tablename__ = 'transferencia'

    id = db.Column(db.Integer, primary_key=True)
    conta_origem_id = db.Column(db.Integer, db.ForeignKey('conta_patrimonio.id'), nullable=False)
    conta_destino_id = db.Column(db.Integer, db.ForeignKey('conta_patrimonio.id'), nullable=False)
    valor = db.Column(db.Numeric(10, 2), nullable=False)
    data_transferencia = db.Column(db.Date, nullable=False)
    descricao = db.Column(db.String(200))
    observacoes = db.Column(db.Text)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    # Relacionamentos
    conta_origem = db.relationship('ContaPatrimonio',
                                  foreign_keys=[conta_origem_id],
                                  back_populates='transferencias_origem')
    conta_destino = db.relationship('ContaPatrimonio',
                                   foreign_keys=[conta_destino_id],
                                   back_populates='transferencias_destino')

    # Índices
    __table_args__ = (
        db.Index('idx_transf_data', 'data_transferencia'),
        db.Index('idx_transf_origem', 'conta_origem_id'),
        db.Index('idx_transf_destino', 'conta_destino_id'),
    )

    def __repr__(self):
        return f'<Transferencia R${self.valor} {self.conta_origem_id}->{self.conta_destino_id}>'

    def to_dict(self):
        return {
            'id': self.id,
            'conta_origem_id': self.conta_origem_id,
            'conta_destino_id': self.conta_destino_id,
            'valor': float(self.valor),
            'data_transferencia': self.data_transferencia.strftime('%Y-%m-%d'),
            'descricao': self.descricao,
            'observacoes': self.observacoes
        }


# ============================================================================
# MÓDULO 4: FINANCIAMENTOS
# ============================================================================

class Financiamento(db.Model):
    """
    Contrato de financiamento (imobiliário, veículo, empréstimo)

    Suporta sistemas de amortização: SAC, PRICE, SIMPLES
    Integrado com parcelas, amortizações extras e indexadores (TR)
    """
    __tablename__ = 'financiamento'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), nullable=False)
    produto = db.Column(db.String(100))  # Ex: SFH, Veículo, Pessoal
    sistema_amortizacao = db.Column(db.String(20), nullable=False)  # SAC, PRICE, SIMPLES

    # Valores do contrato
    valor_financiado = db.Column(db.Numeric(12, 2), nullable=False)
    prazo_total_meses = db.Column(db.Integer, nullable=False)
    prazo_remanescente_meses = db.Column(db.Integer, nullable=False)

    # Taxas de juros
    taxa_juros_nominal_anual = db.Column(db.Numeric(8, 4), nullable=False)
    taxa_juros_efetiva_anual = db.Column(db.Numeric(8, 4))
    taxa_juros_efetiva_relacionamento_anual = db.Column(db.Numeric(8, 4))
    taxa_juros_mensal = db.Column(db.Numeric(8, 6), nullable=False)

    # Indexador
    indexador_saldo = db.Column(db.String(20))  # TR, IPCA, etc

    # Datas
    data_contrato = db.Column(db.Date, nullable=False)
    data_primeira_parcela = db.Column(db.Date, nullable=False)

    # Integração
    item_despesa_id = db.Column(db.Integer, db.ForeignKey('item_despesa.id'))

    # Configuração de Seguro
    seguro_tipo = db.Column(db.String(20), default='fixo')  # 'fixo' ou 'percentual_saldo'
    seguro_percentual = db.Column(db.Numeric(8, 6), default=0.0006)  # 0,06% em decimal
    valor_seguro_mensal = db.Column(db.Numeric(10, 2), default=0)  # Para tipo 'fixo'

    # Taxa de Administração
    taxa_administracao_fixa = db.Column(db.Numeric(10, 2), default=0)  # Valor fixo mensal

    # ========================================================================
    # ESTADO SOBERANO (fonte de verdade após eventos)
    # ========================================================================
    # Saldo devedor ATUAL - atualizado após cada pagamento/amortização
    saldo_devedor_atual = db.Column(db.Numeric(12, 2), nullable=True)

    # Última parcela consolidada (paga ou marco após evento)
    numero_parcela_base = db.Column(db.Integer, default=0)

    # Data base do saldo atual (vencimento da última parcela consolidada)
    data_base = db.Column(db.Date, nullable=True)

    # Amortização mensal ATUAL (após amortizações extraordinárias)
    amortizacao_mensal_atual = db.Column(db.Numeric(12, 2), nullable=True)

    # Regime após amortização extraordinária
    regime_pos_amortizacao = db.Column(db.String(20), nullable=True)  # 'REDUZIR_PARCELA' ou 'REDUZIR_PRAZO'

    # Controle
    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    # Relacionamentos
    item_despesa = db.relationship('ItemDespesa', foreign_keys=[item_despesa_id])
    parcelas = db.relationship('FinanciamentoParcela', back_populates='financiamento',
                               lazy='dynamic', cascade='all, delete-orphan')
    amortizacoes_extra = db.relationship('FinanciamentoAmortizacaoExtra',
                                        back_populates='financiamento',
                                        lazy='dynamic', cascade='all, delete-orphan')
    seguros_vigencia = db.relationship('FinanciamentoSeguroVigencia',
                                      back_populates='financiamento',
                                      lazy='dynamic', cascade='all, delete-orphan',
                                      order_by='FinanciamentoSeguroVigencia.competencia_inicio')

    def __repr__(self):
        return f'<Financiamento {self.nome} - {self.sistema_amortizacao}>'

    def obter_seguro_por_data(self, data_referencia):
        """
        Retorna a vigência de seguro válida para uma data específica

        Parâmetros:
        - data_referencia: Data da parcela (date)

        Retorna:
        - FinanciamentoSeguroVigencia ou None

        Lança ValueError se não houver vigência cadastrada
        """
        from sqlalchemy import and_

        vigencia = FinanciamentoSeguroVigencia.query.filter(
            and_(
                FinanciamentoSeguroVigencia.financiamento_id == self.id,
                FinanciamentoSeguroVigencia.competencia_inicio <= data_referencia,
                db.or_(
                    FinanciamentoSeguroVigencia.data_encerramento == None,
                    FinanciamentoSeguroVigencia.data_encerramento >= data_referencia
                )
            )
        ).order_by(
            FinanciamentoSeguroVigencia.competencia_inicio.desc()
        ).first()

        return vigencia

    def to_dict(self):
        # ========================================================================
        # Usar ESTADO SOBERANO para saldo devedor atual
        # ========================================================================
        # Se estado soberano foi inicializado, usar ele
        if self.saldo_devedor_atual is not None:
            saldo_devedor_atual = float(self.saldo_devedor_atual)
        else:
            # Fallback para financiamentos antigos (sem estado soberano)
            # Buscar primeira parcela pendente
            primeira_pendente = FinanciamentoParcela.query.filter_by(
                financiamento_id=self.id,
                status='pendente'
            ).order_by(FinanciamentoParcela.numero_parcela).first()

            if primeira_pendente and primeira_pendente.numero_parcela > 1:
                parcela_anterior = FinanciamentoParcela.query.filter_by(
                    financiamento_id=self.id,
                    numero_parcela=primeira_pendente.numero_parcela - 1
                ).first()
                saldo_devedor_atual = float(parcela_anterior.saldo_devedor_apos_pagamento) if parcela_anterior else float(self.valor_financiado)
            else:
                saldo_devedor_atual = float(self.valor_financiado)

        return {
            'id': self.id,
            'nome': self.nome,
            'produto': self.produto,
            'sistema_amortizacao': self.sistema_amortizacao,
            'valor_financiado': float(self.valor_financiado),
            'saldo_devedor_atual': saldo_devedor_atual,  # ✅ NOVO CAMPO
            'prazo_total_meses': self.prazo_total_meses,
            'prazo_remanescente_meses': self.prazo_remanescente_meses,
            'taxa_juros_nominal_anual': float(self.taxa_juros_nominal_anual),
            'taxa_juros_efetiva_anual': float(self.taxa_juros_efetiva_anual) if self.taxa_juros_efetiva_anual else None,
            'taxa_juros_efetiva_relacionamento_anual': float(self.taxa_juros_efetiva_relacionamento_anual) if self.taxa_juros_efetiva_relacionamento_anual else None,
            'taxa_juros_mensal': float(self.taxa_juros_mensal),
            'indexador_saldo': self.indexador_saldo,
            'data_contrato': self.data_contrato.strftime('%Y-%m-%d'),
            'data_primeira_parcela': self.data_primeira_parcela.strftime('%Y-%m-%d'),
            'item_despesa_id': self.item_despesa_id,
            'seguro_tipo': self.seguro_tipo,
            'seguro_percentual': float(self.seguro_percentual) if self.seguro_percentual else 0.0006,
            'valor_seguro_mensal': float(self.valor_seguro_mensal) if self.valor_seguro_mensal else 0,
            'taxa_administracao_fixa': float(self.taxa_administracao_fixa) if self.taxa_administracao_fixa else 0,
            'ativo': self.ativo
        }


class FinanciamentoParcela(db.Model):
    """
    Parcela individual do financiamento com todos os componentes detalhados

    Estrutura baseada nos demonstrativos da CAIXA:
    - A) Componentes do Encargo Mensal
    - B) Descontos/Subsídios
    - C) Encargos por atraso
    - D) Valor total e DIF
    """
    __tablename__ = 'financiamento_parcela'

    id = db.Column(db.Integer, primary_key=True)
    financiamento_id = db.Column(db.Integer, db.ForeignKey('financiamento.id'), nullable=False)
    numero_parcela = db.Column(db.Integer, nullable=False)
    data_vencimento = db.Column(db.Date, nullable=False)

    # A - Componentes do Encargo Mensal
    valor_amortizacao = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    valor_juros = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    valor_seguro = db.Column(db.Numeric(10, 2), default=0)
    valor_taxa_adm = db.Column(db.Numeric(10, 2), default=0)

    # B - Descontos/Abatimentos
    valor_subsidio = db.Column(db.Numeric(10, 2), default=0)
    valor_fgts_utilizado = db.Column(db.Numeric(10, 2), default=0)

    # C - Encargos por atraso
    valor_juros_mora = db.Column(db.Numeric(10, 2), default=0)
    valor_multa = db.Column(db.Numeric(10, 2), default=0)
    valor_atualizacao_monetaria = db.Column(db.Numeric(10, 2), default=0)
    valor_iof_complementar = db.Column(db.Numeric(10, 2), default=0)

    # D - Valores consolidados
    valor_previsto_total = db.Column(db.Numeric(10, 2), nullable=False)
    valor_pago = db.Column(db.Numeric(10, 2), default=0)
    dif_apurada = db.Column(db.Numeric(10, 2), default=0)  # Diferença previsto - pago

    # Saldo devedor
    saldo_devedor_apos_pagamento = db.Column(db.Numeric(12, 2))

    # Status e vínculos
    conta_id = db.Column(db.Integer, db.ForeignKey('conta.id'))  # Integração com contas a pagar
    status = db.Column(db.String(20), default='pendente')  # pendente, pago, atrasado

    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    # Relacionamentos
    financiamento = db.relationship('Financiamento', back_populates='parcelas')
    conta = db.relationship('Conta', foreign_keys=[conta_id])

    # Índices
    __table_args__ = (
        db.Index('idx_fin_parc_financ', 'financiamento_id'),
        db.Index('idx_fin_parc_venc', 'data_vencimento'),
        db.Index('idx_fin_parc_status', 'status'),
    )

    def __repr__(self):
        return f'<FinanciamentoParcela {self.numero_parcela}/{self.financiamento_id} R${self.valor_previsto_total}>'

    def to_dict(self):
        return {
            'id': self.id,
            'financiamento_id': self.financiamento_id,
            'numero_parcela': self.numero_parcela,
            'data_vencimento': self.data_vencimento.strftime('%Y-%m-%d'),
            'valor_amortizacao': float(self.valor_amortizacao),
            'valor_juros': float(self.valor_juros),
            'valor_seguro': float(self.valor_seguro),
            'valor_taxa_adm': float(self.valor_taxa_adm),
            'valor_subsidio': float(self.valor_subsidio),
            'valor_fgts_utilizado': float(self.valor_fgts_utilizado),
            'valor_juros_mora': float(self.valor_juros_mora),
            'valor_multa': float(self.valor_multa),
            'valor_atualizacao_monetaria': float(self.valor_atualizacao_monetaria),
            'valor_iof_complementar': float(self.valor_iof_complementar),
            'valor_previsto_total': float(self.valor_previsto_total),
            'valor_pago': float(self.valor_pago),
            'dif_apurada': float(self.dif_apurada),
            'saldo_devedor_apos_pagamento': float(self.saldo_devedor_apos_pagamento) if self.saldo_devedor_apos_pagamento else None,
            'status': self.status
        }


class FinanciamentoAmortizacaoExtra(db.Model):
    """
    Registro de amortizações extraordinárias

    Permite dois tipos:
    - reduzir_parcela: Mantém prazo, reduz valor das parcelas
    - reduzir_prazo: Mantém valor, diminui quantidade de meses
    """
    __tablename__ = 'financiamento_amortizacao_extra'

    id = db.Column(db.Integer, primary_key=True)
    financiamento_id = db.Column(db.Integer, db.ForeignKey('financiamento.id'), nullable=False)
    data = db.Column(db.Date, nullable=False)
    valor = db.Column(db.Numeric(10, 2), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)  # reduzir_parcela, reduzir_prazo
    observacoes = db.Column(db.Text)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    # Relacionamentos
    financiamento = db.relationship('Financiamento', back_populates='amortizacoes_extra')

    # Índices
    __table_args__ = (
        db.Index('idx_amort_financ', 'financiamento_id'),
        db.Index('idx_amort_data', 'data'),
    )

    def __repr__(self):
        return f'<AmortizacaoExtra {self.financiamento_id} R${self.valor} {self.tipo}>'

    def to_dict(self):
        return {
            'id': self.id,
            'financiamento_id': self.financiamento_id,
            'data': self.data.strftime('%Y-%m-%d'),
            'valor': float(self.valor),
            'tipo': self.tipo,
            'observacoes': self.observacoes
        }


class FinanciamentoSeguroVigencia(db.Model):
    """
    Vigências do seguro habitacional com valores 100% MANUAIS

    Cada registro representa um período onde o seguro tem um valor específico
    informado diretamente pelo usuário (ex: valor da apólice/cobrança da seguradora).

    MODELO ATUAL (manual):
    - Vigência 1: 02/2025 -> R$ 188,00 (usuário informou)
    - Vigência 2: 02/2026 -> R$ 199,00 (usuário informou)

    REGRAS:
    - Usuário informa VALOR absoluto mensal (não percentual, não taxa)
    - Sistema NÃO calcula nada automaticamente
    - Vigência pode ser editada (UPDATE) se não houver parcelas pagas no período
    - Campos taxa_percentual e saldo_devedor_vigencia são LEGACY (não usados)
    """
    __tablename__ = 'financiamento_seguro_vigencia'

    id = db.Column(db.Integer, primary_key=True)
    financiamento_id = db.Column(db.Integer, db.ForeignKey('financiamento.id'), nullable=False)

    # Competência de início (primeiro mês desta vigência)
    competencia_inicio = db.Column(db.Date, nullable=False)  # Ex: 2025-02-01

    # Valor mensal do seguro informado pelo usuário (fonte da verdade)
    valor_mensal = db.Column(db.Numeric(10, 2), nullable=False)  # Ex: 188.00

    # CAMPOS LEGACY (não usados no modelo atual, mantidos por compatibilidade)
    saldo_devedor_vigencia = db.Column(db.Numeric(12, 2), nullable=True)  # Legacy
    taxa_percentual = db.Column(db.Numeric(8, 6), nullable=True)  # Legacy

    # Data de nascimento do segurado (para alertas de mudança de faixa etária)
    data_nascimento_segurado = db.Column(db.Date)

    # Observações (ex: "Mudança por idade 51 anos", "Tabela Caixa 2025-2030")
    observacoes = db.Column(db.Text)

    # Controle de vigência
    vigencia_ativa = db.Column(db.Boolean, default=True)  # False quando substituída
    data_encerramento = db.Column(db.Date)  # Preenchido ao criar nova vigência

    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    # Relacionamentos
    financiamento = db.relationship('Financiamento', back_populates='seguros_vigencia')

    # Índices
    __table_args__ = (
        db.Index('idx_seguro_vig_financ', 'financiamento_id'),
        db.Index('idx_seguro_vig_comp', 'competencia_inicio'),
        db.Index('idx_seguro_vig_ativa', 'vigencia_ativa'),
    )

    def __repr__(self):
        return f'<SeguroVigencia {self.competencia_inicio.strftime("%Y-%m")} R${self.valor_mensal}>'

    def to_dict(self):
        return {
            'id': self.id,
            'financiamento_id': self.financiamento_id,
            'competencia_inicio': self.competencia_inicio.strftime('%Y-%m-%d'),
            'valor_mensal': float(self.valor_mensal),
            'saldo_devedor_vigencia': float(self.saldo_devedor_vigencia),
            'taxa_percentual': float(self.taxa_percentual),
            'data_nascimento_segurado': self.data_nascimento_segurado.strftime('%Y-%m-%d') if self.data_nascimento_segurado else None,
            'observacoes': self.observacoes,
            'vigencia_ativa': self.vigencia_ativa,
            'data_encerramento': self.data_encerramento.strftime('%Y-%m-%d') if self.data_encerramento else None
        }


class IndexadorMensal(db.Model):
    """
    Valores mensais de indexadores (TR, IPCA, etc.)

    Usado para atualizar saldo devedor dos financiamentos
    """
    __tablename__ = 'indexador_mensal'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(20), nullable=False)  # TR, IPCA, IGPM, etc
    data_referencia = db.Column(db.Date, nullable=False)  # Primeiro dia do mês
    valor = db.Column(db.Numeric(10, 6), nullable=False)  # Percentual (ex: 0.0015 = 0,15%)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    # Índice único
    __table_args__ = (
        db.Index('idx_indexador_nome_data', 'nome', 'data_referencia', unique=True),
    )

    def __repr__(self):
        return f'<IndexadorMensal {self.nome} {self.data_referencia.strftime("%Y-%m")} {self.valor}%>'

    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'data_referencia': self.data_referencia.strftime('%Y-%m-%d'),
            'valor': float(self.valor)
        }


class ContaBancaria(db.Model):
    """
    Contas bancárias do usuário (Conta Corrente, Poupança, Carteira Digital)
    """
    __tablename__ = 'conta_bancaria'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    instituicao = db.Column(db.String(100), nullable=False)
    tipo = db.Column(db.String(50), nullable=False)  # Conta Corrente, Poupança, Carteira Digital
    agencia = db.Column(db.String(20))
    numero_conta = db.Column(db.String(50))
    digito_conta = db.Column(db.String(10))
    saldo_inicial = db.Column(db.Numeric(15, 2), default=0)
    saldo_atual = db.Column(db.Numeric(15, 2), default=0)
    cor_display = db.Column(db.String(7), default='#3b82f6')  # Código hexadecimal
    icone = db.Column(db.String(50))  # Nome do ícone (opcional)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    data_atualizacao = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    status = db.Column(db.String(20), default='ATIVO')  # ATIVO ou INATIVO

    def __repr__(self):
        return f'<ContaBancaria {self.nome} - {self.instituicao}>'

    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'instituicao': self.instituicao,
            'tipo': self.tipo,
            'agencia': self.agencia,
            'numero_conta': self.numero_conta,
            'digito_conta': self.digito_conta,
            'saldo_inicial': float(self.saldo_inicial) if self.saldo_inicial else 0,
            'saldo_atual': float(self.saldo_atual) if self.saldo_atual else 0,
            'cor_display': self.cor_display,
            'icone': self.icone,
            'data_criacao': self.data_criacao.strftime('%Y-%m-%d %H:%M:%S') if self.data_criacao else None,
            'data_atualizacao': self.data_atualizacao.strftime('%Y-%m-%d %H:%M:%S') if self.data_atualizacao else None,
            'status': self.status
        }


class MovimentoFinanceiro(db.Model):
    """
    Movimentações financeiras em contas bancárias

    Registra débitos e créditos que impactam o saldo_atual das contas
    """
    __tablename__ = 'movimento_financeiro'

    id = db.Column(db.Integer, primary_key=True)
    conta_bancaria_id = db.Column(db.Integer, db.ForeignKey('conta_bancaria.id'), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)  # DEBITO ou CREDITO
    valor = db.Column(db.Numeric(15, 2), nullable=False)
    descricao = db.Column(db.String(200), nullable=False)
    data_movimento = db.Column(db.Date, nullable=False)
    fatura_id = db.Column(db.Integer, db.ForeignKey('conta.id'))  # Nullable - link para fatura de cartão
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    # Relacionamentos
    conta_bancaria = db.relationship('ContaBancaria', backref='movimentos')
    fatura = db.relationship('Conta', foreign_keys=[fatura_id])

    # Índices
    __table_args__ = (
        db.Index('idx_movimento_conta', 'conta_bancaria_id'),
        db.Index('idx_movimento_data', 'data_movimento'),
        db.Index('idx_movimento_fatura', 'fatura_id'),
    )

    def __repr__(self):
        return f'<MovimentoFinanceiro {self.tipo} R${self.valor} {self.descricao}>'

    def to_dict(self):
        return {
            'id': self.id,
            'conta_bancaria_id': self.conta_bancaria_id,
            'tipo': self.tipo,
            'valor': float(self.valor),
            'descricao': self.descricao,
            'data_movimento': self.data_movimento.strftime('%Y-%m-%d'),
            'fatura_id': self.fatura_id,
            'criado_em': self.criado_em.strftime('%Y-%m-%d %H:%M:%S') if self.criado_em else None
        }


# ============================================================================
# MÓDULO 4: PREFERÊNCIAS E CONFIGURAÇÕES GERAIS
# ============================================================================

class Preferencia(db.Model):
    """
    Armazena preferências e configurações gerais do sistema
    Singleton - apenas um registro por usuário
    """
    __tablename__ = 'preferencia'

    id = db.Column(db.Integer, primary_key=True)

    # ========== ABA 1: DADOS PESSOAIS ==========
    nome_usuario = db.Column(db.String(100))
    renda_principal = db.Column(db.Numeric(10, 2))  # Apenas exibição
    mes_inicio_planejamento = db.Column(db.Integer, default=1)  # 1-12
    dia_fechamento_mes = db.Column(db.Integer, default=1)  # 1-31

    # ========== ABA 2: COMPORTAMENTO DO SISTEMA ==========
    # Lançamentos e Pagamentos
    ajustar_competencia_automatico = db.Column(db.Boolean, default=True)
    exibir_aviso_despesa_vencida = db.Column(db.Boolean, default=True)
    solicitar_confirmacao_exclusao = db.Column(db.Boolean, default=True)
    vincular_pagamento_cartao_auto = db.Column(db.Boolean, default=True)

    # Dashboard
    graficos_visiveis = db.Column(db.String(200), default='categorias,evolucao,saldo')  # CSV
    insights_inteligentes_ativo = db.Column(db.Boolean, default=True)
    mostrar_saldo_consolidado = db.Column(db.Boolean, default=True)
    mostrar_evolucao_historica = db.Column(db.Boolean, default=True)

    # Cartões
    dia_inicio_fatura = db.Column(db.Integer, default=1)  # 1-31
    dia_corte_fatura = db.Column(db.Integer, default=1)  # 1-31
    lancamentos_agrupados = db.Column(db.Boolean, default=False)  # False = linha a linha
    orcamento_por_categoria = db.Column(db.Boolean, default=True)

    # ========== ABA 3: APARÊNCIA ==========
    tema_sistema = db.Column(db.String(20), default='escuro')  # 'claro', 'escuro', 'auto'
    cor_principal = db.Column(db.String(7), default='#3b82f6')  # Hex color
    mostrar_icones_coloridos = db.Column(db.Boolean, default=True)
    abreviar_valores = db.Column(db.Boolean, default=False)  # R$ 1,2k

    # ========== ABA 4: BACKUP E IMPORTAÇÃO ==========
    ultimo_backup = db.Column(db.DateTime)
    backup_automatico = db.Column(db.Boolean, default=False)

    # ========== ABA 5: IA E AUTOMAÇÃO ==========
    modo_inteligente_ativo = db.Column(db.Boolean, default=False)
    sugestoes_economia = db.Column(db.Boolean, default=False)
    classificacao_automatica = db.Column(db.Boolean, default=False)
    correcao_categorias = db.Column(db.Boolean, default=False)
    parcelas_recorrentes_auto = db.Column(db.Boolean, default=False)

    # Metadata
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    data_atualizacao = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<Preferencia ID:{self.id} Usuario:{self.nome_usuario}>'

    def to_dict(self):
        return {
            'id': self.id,
            # Dados Pessoais
            'nome_usuario': self.nome_usuario,
            'renda_principal': float(self.renda_principal) if self.renda_principal else 0,
            'mes_inicio_planejamento': self.mes_inicio_planejamento,
            'dia_fechamento_mes': self.dia_fechamento_mes,
            # Comportamento - Lançamentos
            'ajustar_competencia_automatico': self.ajustar_competencia_automatico,
            'exibir_aviso_despesa_vencida': self.exibir_aviso_despesa_vencida,
            'solicitar_confirmacao_exclusao': self.solicitar_confirmacao_exclusao,
            'vincular_pagamento_cartao_auto': self.vincular_pagamento_cartao_auto,
            # Comportamento - Dashboard
            'graficos_visiveis': self.graficos_visiveis,
            'insights_inteligentes_ativo': self.insights_inteligentes_ativo,
            'mostrar_saldo_consolidado': self.mostrar_saldo_consolidado,
            'mostrar_evolucao_historica': self.mostrar_evolucao_historica,
            # Comportamento - Cartões
            'dia_inicio_fatura': self.dia_inicio_fatura,
            'dia_corte_fatura': self.dia_corte_fatura,
            'lancamentos_agrupados': self.lancamentos_agrupados,
            'orcamento_por_categoria': self.orcamento_por_categoria,
            # Aparência
            'tema_sistema': self.tema_sistema,
            'cor_principal': self.cor_principal,
            'mostrar_icones_coloridos': self.mostrar_icones_coloridos,
            'abreviar_valores': self.abreviar_valores,
            # Backup
            'ultimo_backup': self.ultimo_backup.strftime('%Y-%m-%d %H:%M:%S') if self.ultimo_backup else None,
            'backup_automatico': self.backup_automatico,
            # IA e Automação
            'modo_inteligente_ativo': self.modo_inteligente_ativo,
            'sugestoes_economia': self.sugestoes_economia,
            'classificacao_automatica': self.classificacao_automatica,
            'correcao_categorias': self.correcao_categorias,
            'parcelas_recorrentes_auto': self.parcelas_recorrentes_auto
        }


# ============================================================================
# MÓDULO 4: VEÍCULOS (FASE 1 - PROJETIVO, SEM LANÇAMENTOS AUTOMÁTICOS)
# ============================================================================


class Veiculo(db.Model):
    """
    Veículo é origem de despesas previstas (projeções), nunca uma categoria.
    """
    __tablename__ = 'veiculo'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)  # 'carro', 'moto', 'outro'
    combustivel = db.Column(db.String(20), nullable=False)  # 'gasolina', 'etanol', etc.
    autonomia_km_l = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.String(10), nullable=False, default='SIMULADO')  # SIMULADO | ATIVO
    data_inicio = db.Column(db.Date, nullable=True)  # obrigatório quando ATIVO

    # Configurações mínimas para projeção MVP (todas opcionais e configuráveis por veículo)
    categoria_combustivel_id = db.Column(db.Integer, db.ForeignKey('categoria.id'), nullable=True)
    combustivel_valor_mensal = db.Column(db.Numeric(10, 2), nullable=True)

    ipva_categoria_id = db.Column(db.Integer, db.ForeignKey('categoria.id'), nullable=True)
    ipva_mes = db.Column(db.Integer, nullable=True)  # 1-12
    ipva_valor = db.Column(db.Numeric(10, 2), nullable=True)

    seguro_categoria_id = db.Column(db.Integer, db.ForeignKey('categoria.id'), nullable=True)
    seguro_mes = db.Column(db.Integer, nullable=True)  # 1-12
    seguro_valor = db.Column(db.Numeric(10, 2), nullable=True)

    licenciamento_categoria_id = db.Column(db.Integer, db.ForeignKey('categoria.id'), nullable=True)
    licenciamento_mes = db.Column(db.Integer, nullable=True)  # 1-12
    licenciamento_valor = db.Column(db.Numeric(10, 2), nullable=True)

    # FASE 3: sensor passivo de uso (inferência via combustível)
    preco_medio_combustivel = db.Column(db.Numeric(10, 2), nullable=True)  # R$/L (opcional)
    km_estimado_acumulado = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    km_estimado_ultimo_calculo_em = db.Column(db.DateTime, nullable=True)
    km_estimado_ultimo_despesa_prevista_id = db.Column(db.Integer, nullable=True)

    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos (opcionais; as despesas previstas referenciam categoria)
    categoria_combustivel = db.relationship('Categoria', foreign_keys=[categoria_combustivel_id])
    categoria_ipva = db.relationship('Categoria', foreign_keys=[ipva_categoria_id])
    categoria_seguro = db.relationship('Categoria', foreign_keys=[seguro_categoria_id])
    categoria_licenciamento = db.relationship('Categoria', foreign_keys=[licenciamento_categoria_id])

    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'tipo': self.tipo,
            'combustivel': self.combustivel,
            'autonomia_km_l': float(self.autonomia_km_l) if self.autonomia_km_l is not None else None,
            'status': self.status,
            'data_inicio': self.data_inicio.isoformat() if self.data_inicio else None,
            'projecao_combustivel': {
                'categoria_id': self.categoria_combustivel_id,
                'valor_mensal': float(self.combustivel_valor_mensal) if self.combustivel_valor_mensal else None
            },
            'preco_medio_combustivel': float(self.preco_medio_combustivel) if self.preco_medio_combustivel else None,
            'uso_estimado': {
                'km_estimado_acumulado': float(self.km_estimado_acumulado) if self.km_estimado_acumulado is not None else 0,
                'km_estimado_ultimo_calculo_em': self.km_estimado_ultimo_calculo_em.isoformat() if self.km_estimado_ultimo_calculo_em else None
            },
            'ipva': {
                'categoria_id': self.ipva_categoria_id,
                'mes': self.ipva_mes,
                'valor': float(self.ipva_valor) if self.ipva_valor else None
            },
            'seguro': {
                'categoria_id': self.seguro_categoria_id,
                'mes': self.seguro_mes,
                'valor': float(self.seguro_valor) if self.seguro_valor else None
            },
            'licenciamento': {
                'categoria_id': self.licenciamento_categoria_id,
                'mes': self.licenciamento_mes,
                'valor': float(self.licenciamento_valor) if self.licenciamento_valor else None
            },
            'criado_em': self.criado_em.isoformat() if self.criado_em else None,
            'atualizado_em': self.atualizado_em.isoformat() if self.atualizado_em else None
        }


class VeiculoRegraManutencaoKm(db.Model):
    """
    Regra de manutenção condicionada por km estimado (FASE 4).
    Ex: TROCA_OLEO a cada 10.000 km.
    """
    __tablename__ = 'veiculo_regra_manutencao_km'

    id = db.Column(db.Integer, primary_key=True)
    veiculo_id = db.Column(db.Integer, db.ForeignKey('veiculo.id'), nullable=False)
    tipo_evento = db.Column(db.String(50), nullable=False)  # ex: 'TROCA_OLEO'
    intervalo_km = db.Column(db.Integer, nullable=False)
    # FASE 7: fallback temporal (quando nÇœo houver uso real/projetado suficiente para km/mÇ¦s)
    meses_intervalo = db.Column(db.Integer, nullable=True)  # ex: 8 = a cada 8 meses
    custo_estimado = db.Column(db.Numeric(10, 2), nullable=False)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categoria.id'), nullable=False)
    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    veiculo = db.relationship('Veiculo')
    categoria = db.relationship('Categoria')

    __table_args__ = (
        db.Index('idx_regra_km_veiculo_tipo', 'veiculo_id', 'tipo_evento'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'veiculo_id': self.veiculo_id,
            'tipo_evento': self.tipo_evento,
            'intervalo_km': self.intervalo_km,
            'meses_intervalo': int(self.meses_intervalo) if self.meses_intervalo is not None else None,
            'custo_estimado': float(self.custo_estimado) if self.custo_estimado is not None else None,
            'categoria_id': self.categoria_id,
            'categoria': self.categoria.to_dict() if self.categoria else None,
            'ativo': bool(self.ativo),
            'criado_em': self.criado_em.isoformat() if self.criado_em else None,
            'atualizado_em': self.atualizado_em.isoformat() if self.atualizado_em else None,
        }


class VeiculoCicloManutencao(db.Model):
    """
    Ciclo auditável por veículo + tipo_evento (FASE 5).
    Não guarda agenda futura; serve para amarração e auditoria.
    """
    __tablename__ = 'veiculo_ciclo_manutencao'

    id = db.Column(db.Integer, primary_key=True)
    veiculo_id = db.Column(db.Integer, db.ForeignKey('veiculo.id'), nullable=False)
    tipo_evento = db.Column(db.String(50), nullable=False)
    regra_id = db.Column(db.Integer, db.ForeignKey('veiculo_regra_manutencao_km.id'), nullable=False)
    intervalo_km = db.Column(db.Integer, nullable=False)  # snapshot do intervalo no momento da criação
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    veiculo = db.relationship('Veiculo')
    regra = db.relationship('VeiculoRegraManutencaoKm')

    __table_args__ = (
        db.Index('idx_ciclo_veiculo_tipo', 'veiculo_id', 'tipo_evento'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'veiculo_id': self.veiculo_id,
            'tipo_evento': self.tipo_evento,
            'regra_id': self.regra_id,
            'intervalo_km': self.intervalo_km,
            'criado_em': self.criado_em.isoformat() if self.criado_em else None
        }


class DespesaPrevistaAcaoLog(db.Model):
    """
    Registro mínimo auditável de ações humanas e efeitos (FASE 5).
    """
    __tablename__ = 'despesa_prevista_acao_log'

    id = db.Column(db.Integer, primary_key=True)
    despesa_prevista_id = db.Column(db.Integer, db.ForeignKey('despesa_prevista.id'), nullable=False)
    acao = db.Column(db.String(30), nullable=False)  # ex: 'ADIAR'
    ajustar_ciclo = db.Column(db.Boolean, default=False)
    despesa_prevista_criada_id = db.Column(db.Integer, db.ForeignKey('despesa_prevista.id'), nullable=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    despesa = db.relationship('DespesaPrevista', foreign_keys=[despesa_prevista_id])
    despesa_criada = db.relationship('DespesaPrevista', foreign_keys=[despesa_prevista_criada_id])

    def to_dict(self):
        return {
            'id': self.id,
            'despesa_prevista_id': self.despesa_prevista_id,
            'acao': self.acao,
            'ajustar_ciclo': bool(self.ajustar_ciclo),
            'despesa_prevista_criada_id': self.despesa_prevista_criada_id,
            'criado_em': self.criado_em.isoformat() if self.criado_em else None
        }


class VeiculoFinanciamento(db.Model):
    """
    FASE 6: Financiamento projetivo do veículo (simulação).
    Não implementa SAC/PRICE; é um modelo simples de amortização + juros + indexador.
    """
    __tablename__ = 'veiculo_financiamento'

    id = db.Column(db.Integer, primary_key=True)
    veiculo_id = db.Column(db.Integer, db.ForeignKey('veiculo.id'), nullable=False, unique=True)

    valor_bem = db.Column(db.Numeric(12, 2), nullable=False)
    entrada = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    valor_financiado = db.Column(db.Numeric(12, 2), nullable=False)
    numero_parcelas = db.Column(db.Integer, nullable=False)

    taxa_juros_mensal = db.Column(db.Numeric(6, 3), nullable=False)  # percentual (ex: 2.020 = 2,02% a.m.)
    indexador_tipo = db.Column(db.String(20), nullable=True)  # TR, IPCA, etc.

    iof_percentual = db.Column(db.Numeric(6, 3), nullable=False, default=0)  # percentual
    iof_valor = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    categoria_id = db.Column(db.Integer, db.ForeignKey('categoria.id'), nullable=True)

    custo_total_financiamento = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    veiculo = db.relationship('Veiculo')
    categoria = db.relationship('Categoria')

    def to_dict(self):
        return {
            'id': self.id,
            'veiculo_id': self.veiculo_id,
            'valor_bem': float(self.valor_bem) if self.valor_bem is not None else None,
            'entrada': float(self.entrada) if self.entrada is not None else 0,
            'valor_financiado': float(self.valor_financiado) if self.valor_financiado is not None else None,
            'numero_parcelas': int(self.numero_parcelas) if self.numero_parcelas is not None else None,
            'taxa_juros_mensal': float(self.taxa_juros_mensal) if self.taxa_juros_mensal is not None else None,
            'indexador_tipo': self.indexador_tipo,
            'iof_percentual': float(self.iof_percentual) if self.iof_percentual is not None else 0,
            'iof_valor': float(self.iof_valor) if self.iof_valor is not None else 0,
            'categoria_id': self.categoria_id,
            'custo_total_financiamento': float(self.custo_total_financiamento) if self.custo_total_financiamento is not None else 0,
            'criado_em': self.criado_em.isoformat() if self.criado_em else None,
            'atualizado_em': self.atualizado_em.isoformat() if self.atualizado_em else None,
        }


class DespesaPrevista(db.Model):
    """
    Despesa prevista (projeção). Nunca vira lançamento real automaticamente.
    """
    __tablename__ = 'despesa_prevista'

    id = db.Column(db.Integer, primary_key=True)
    origem_tipo = db.Column(db.String(20), nullable=False)  # ex: 'VEICULO'
    origem_id = db.Column(db.Integer, nullable=False)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categoria.id'), nullable=False)
    # Mantido por compatibilidade (usado em queries atuais): espelha data_atual_prevista
    data_prevista = db.Column(db.Date, nullable=False)  # YYYY-MM-01
    # FASE 2: histórico imutável + data atual ajustável
    data_original_prevista = db.Column(db.Date, nullable=False)
    data_atual_prevista = db.Column(db.Date, nullable=False)
    valor_previsto = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='PREVISTA')  # PREVISTA|CONFIRMADA|ADIADA|IGNORADA
    metadata_json = db.Column('metadata', db.Text, nullable=True)  # JSON string (ex: {"tipo_evento":"IPVA"})
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    categoria = db.relationship('Categoria')

    __table_args__ = (
        db.Index('idx_desp_prev_origem_data', 'origem_tipo', 'origem_id', 'data_prevista'),
    )

    def _metadata_dict(self):
        if not self.metadata_json:
            return {}
        try:
            return json.loads(self.metadata_json)
        except Exception:
            return {}

    def to_dict(self):
        md = self._metadata_dict()
        if 'ciclo_id' not in md:
            md['ciclo_id'] = None
        if 'ordem_no_ciclo' not in md:
            md['ordem_no_ciclo'] = None
        return {
            'id': self.id,
            'origem_tipo': self.origem_tipo,
            'origem_id': self.origem_id,
            'categoria_id': self.categoria_id,
            'categoria': self.categoria.to_dict() if self.categoria else None,
            'data_original_prevista': self.data_original_prevista.isoformat() if self.data_original_prevista else None,
            'data_atual_prevista': self.data_atual_prevista.isoformat() if self.data_atual_prevista else None,
            'data_prevista': self.data_prevista.isoformat() if self.data_prevista else None,
            'valor_previsto': float(self.valor_previsto) if self.valor_previsto is not None else None,
            'status': self.status,
            'metadata': md,
            'tipo_evento': md.get('tipo_evento')
        }
