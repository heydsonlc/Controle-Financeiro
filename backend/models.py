"""
Modelos do banco de dados - Sistema de Controle Financeiro

14 Tabelas organizadas em 3 módulos:
- Módulo 1: Orçamento (Receitas e Despesas) - 11 tabelas
- Módulo 2: Automação (Consórcios) - 1 tabela
- Módulo 3: Patrimônio (Caixinhas) - 2 tabelas
"""
from datetime import datetime
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

    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    # Relacionamentos
    categoria = db.relationship('Categoria', back_populates='itens_despesa')
    config_agregador = db.relationship('ConfigAgregador', back_populates='item_despesa', uselist=False)
    orcamentos = db.relationship('Orcamento', back_populates='item_despesa', lazy='dynamic')
    contas = db.relationship('Conta', back_populates='item_despesa', lazy='dynamic')
    itens_agregados = db.relationship('ItemAgregado', back_populates='item_despesa_pai', lazy='dynamic')

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
            'mes_competencia': self.mes_competencia
        }

        # Adicionar categoria apenas se existir
        if self.categoria:
            result['categoria'] = {
                'id': self.categoria.id,
                'nome': self.categoria.nome
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
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    # Relacionamentos
    item_despesa = db.relationship('ItemDespesa', back_populates='contas')

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
            'mes_referencia': self.mes_referencia.strftime('%Y-%m-%d'),
            'descricao': self.descricao,
            'valor': float(self.valor),
            'data_vencimento': self.data_vencimento.strftime('%Y-%m-%d'),
            'data_pagamento': self.data_pagamento.strftime('%Y-%m-%d') if self.data_pagamento else None,
            'status_pagamento': self.status_pagamento,
            'debito_automatico': self.debito_automatico,
            'numero_parcela': self.numero_parcela,
            'total_parcelas': self.total_parcelas,
            'observacoes': self.observacoes
        }


class ItemAgregado(db.Model):
    """
    Sub-itens de um item 'Agregador' (ex: Supermercado, Farmácia dentro do Cartão VISA)
    """
    __tablename__ = 'item_agregado'

    id = db.Column(db.Integer, primary_key=True)
    item_despesa_id = db.Column(db.Integer, db.ForeignKey('item_despesa.id'), nullable=False)
    nome = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.Text)
    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    # Relacionamentos
    item_despesa_pai = db.relationship('ItemDespesa', back_populates='itens_agregados')
    orcamentos_agregados = db.relationship('OrcamentoAgregado', back_populates='item_agregado', lazy='dynamic')
    lancamentos_agregados = db.relationship('LancamentoAgregado', back_populates='item_agregado', lazy='dynamic')

    def __repr__(self):
        return f'<ItemAgregado {self.nome}>'

    def to_dict(self):
        return {
            'id': self.id,
            'item_despesa_id': self.item_despesa_id,
            'nome': self.nome,
            'descricao': self.descricao,
            'ativo': self.ativo
        }


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
            'observacoes': self.observacoes
        }


class LancamentoAgregado(db.Model):
    """
    Gasto real no cartão de crédito
    """
    __tablename__ = 'lancamento_agregado'

    id = db.Column(db.Integer, primary_key=True)
    item_agregado_id = db.Column(db.Integer, db.ForeignKey('item_agregado.id'), nullable=False)
    descricao = db.Column(db.String(200), nullable=False)
    valor = db.Column(db.Numeric(10, 2), nullable=False)
    data_compra = db.Column(db.Date, nullable=False)
    mes_fatura = db.Column(db.Date, nullable=False)  # Mês que a fatura fecha
    numero_parcela = db.Column(db.Integer, default=1)
    total_parcelas = db.Column(db.Integer, default=1)
    observacoes = db.Column(db.Text)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    # Relacionamentos
    item_agregado = db.relationship('ItemAgregado', back_populates='lancamentos_agregados')

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
            'observacoes': self.observacoes
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
            'conta_origem_id': self.conta_origem_id
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
    ano_mes = db.Column(db.Date, nullable=False)  # Primeiro dia do mês (YYYY-MM-01)
    valor_previsto = db.Column(db.Numeric(10, 2), nullable=False)

    # Periodicidade da receita
    periodicidade = db.Column(db.String(20), default='MENSAL_FIXA')
    # Valores: MENSAL_FIXA, EVENTUAL, UNICA

    observacoes = db.Column(db.Text)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    # Relacionamentos
    item_receita = db.relationship('ItemReceita', back_populates='receitas_orcamento')

    # Índice composto
    __table_args__ = (
        db.Index('idx_rec_orc_item_mes', 'item_receita_id', 'ano_mes'),
    )

    def __repr__(self):
        return f'<ReceitaOrcamento Item:{self.item_receita_id} Mês:{self.ano_mes} R${self.valor_previsto}>'

    def to_dict(self):
        return {
            'id': self.id,
            'item_receita_id': self.item_receita_id,
            'ano_mes': self.ano_mes.strftime('%Y-%m-%d'),
            'valor_previsto': float(self.valor_previsto),
            'periodicidade': self.periodicidade,
            'observacoes': self.observacoes
        }


class ReceitaRealizada(db.Model):
    """
    Receita efetivamente recebida (baixa da receita)

    Registra cada recebimento real, permitindo comparar com o orçamento
    """
    __tablename__ = 'receita_realizada'

    id = db.Column(db.Integer, primary_key=True)
    item_receita_id = db.Column(db.Integer, db.ForeignKey('item_receita.id'), nullable=False)

    # Data efetiva do recebimento
    data_recebimento = db.Column(db.Date, nullable=False)

    # Valor recebido
    valor_recebido = db.Column(db.Numeric(10, 2), nullable=False)

    # Competência (mês de referência - ex: salário de Maio/2025 mesmo que pago em 06/06)
    competencia = db.Column(db.Date, nullable=False)  # YYYY-MM-01

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
        db.Index('idx_rec_real_competencia', 'competencia'),
        db.Index('idx_rec_real_item_comp', 'item_receita_id', 'competencia'),
    )

    def __repr__(self):
        return f'<ReceitaRealizada {self.descricao} R${self.valor_recebido} Receb:{self.data_recebimento}>'

    def to_dict(self):
        result = {
            'id': self.id,
            'item_receita_id': self.item_receita_id,
            'data_recebimento': self.data_recebimento.strftime('%Y-%m-%d'),
            'valor_recebido': float(self.valor_recebido),
            'competencia': self.competencia.strftime('%Y-%m-%d'),
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

    def __repr__(self):
        return f'<Financiamento {self.nome} - {self.sistema_amortizacao}>'

    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'produto': self.produto,
            'sistema_amortizacao': self.sistema_amortizacao,
            'valor_financiado': float(self.valor_financiado),
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
