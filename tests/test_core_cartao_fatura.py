"""
Testes CORE-CARTAO-FATURA-1:
- CORE-CARTAO-1: idempotência de lançamentos recorrentes via compra_id UUID5
- CORE-FATURA-1: pagamento seguro de fatura (recalcula, bloqueia duplicata, usa service)
- Integração: ciclo completo criar → gerar → re-gerar → pagar → verificar
"""
import uuid
from datetime import date
from decimal import Decimal

import pytest
from flask import Flask

from backend.models import (
    Categoria,
    ConfigAgregador,
    ContaBancaria,
    Conta,
    ItemDespesa,
    LancamentoAgregado,
    MovimentoFinanceiro,
    db,
)
from backend.routes.cartoes import cartoes_bp
from backend.routes.despesas import despesas_bp, gerar_lancamentos_cartao_recorrente
from backend.services.cartao_service import CartaoService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def app_context():
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    app.register_blueprint(cartoes_bp, url_prefix='/api/cartoes')
    app.register_blueprint(despesas_bp, url_prefix='/api/despesas')

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def _cartao():
    cartao = ItemDespesa(nome='Cartao Visa', tipo='Agregador', ativo=True, recorrente=True)
    db.session.add(cartao)
    db.session.flush()
    db.session.add(ConfigAgregador(
        item_despesa_id=cartao.id,
        dia_fechamento=25,
        dia_vencimento=5,
    ))
    db.session.commit()
    return cartao


def _categoria():
    cat = Categoria(nome='Assinatura', ativo=True)
    db.session.add(cat)
    db.session.commit()
    return cat


def _item_recorrente_cartao(cartao, categoria, valor=99.90):
    item = ItemDespesa(
        nome='Netflix',
        tipo='Simples',
        ativo=True,
        recorrente=True,
        meio_pagamento='cartao',
        cartao_id=cartao.id,
        categoria_id=categoria.id,
        valor=Decimal(str(valor)),
        data_vencimento=date(2026, 5, 1),
    )
    db.session.add(item)
    db.session.commit()
    return item


def _conta_bancaria(saldo=1000.0):
    cb = ContaBancaria(
        nome='Conta Corrente',
        instituicao='Banco Teste',
        tipo='Conta Corrente',
        saldo_inicial=Decimal(str(saldo)),
        saldo_atual=Decimal(str(saldo)),
        status='ATIVO',
    )
    db.session.add(cb)
    db.session.commit()
    return cb


def _fatura(cartao, competencia=date(2026, 5, 1), valor_planejado=99.90):
    fatura = Conta(
        item_despesa_id=cartao.id,
        mes_referencia=competencia,
        descricao=f'Fatura {cartao.nome} {competencia.strftime("%m/%Y")}',
        valor=Decimal(str(valor_planejado)),
        data_vencimento=date(2026, 5, 5),
        status_pagamento='Pendente',
        is_fatura_cartao=True,
        cartao_competencia=competencia,
        valor_planejado=Decimal(str(valor_planejado)),
        valor_executado=Decimal('0.00'),
    )
    db.session.add(fatura)
    db.session.commit()
    return fatura


def _lancamento_manual(cartao, categoria, competencia=date(2026, 5, 1), valor=150.00):
    lanc = LancamentoAgregado(
        cartao_id=cartao.id,
        categoria_id=categoria.id,
        descricao='Compra manual',
        valor=Decimal(str(valor)),
        data_compra=competencia,
        mes_fatura=competencia,
        numero_parcela=1,
        total_parcelas=1,
    )
    db.session.add(lanc)
    db.session.commit()
    return lanc


# ---------------------------------------------------------------------------
# CORE-CARTAO-1: Idempotência de lançamentos recorrentes
# ---------------------------------------------------------------------------

def test_gerar_recorrente_cria_um_lancamento(app_context):
    cartao = _cartao()
    cat = _categoria()
    item = _item_recorrente_cartao(cartao, cat)

    gerar_lancamentos_cartao_recorrente(item.id, meses_futuros=1, mes_referencia=date(2026, 5, 1))
    db.session.commit()

    lancamentos = LancamentoAgregado.query.filter_by(item_despesa_id=item.id).all()
    assert len(lancamentos) == 1
    assert lancamentos[0].is_recorrente is True
    assert lancamentos[0].compra_id is not None


def test_gerar_recorrente_segunda_vez_nao_duplica(app_context):
    cartao = _cartao()
    cat = _categoria()
    item = _item_recorrente_cartao(cartao, cat)

    gerar_lancamentos_cartao_recorrente(item.id, meses_futuros=1, mes_referencia=date(2026, 5, 1))
    db.session.commit()

    gerar_lancamentos_cartao_recorrente(item.id, meses_futuros=1, mes_referencia=date(2026, 5, 1))
    db.session.commit()

    assert LancamentoAgregado.query.filter_by(item_despesa_id=item.id).count() == 1


def test_gerar_recorrente_competencia_diferente_cria_outro_lancamento(app_context):
    cartao = _cartao()
    cat = _categoria()
    item = _item_recorrente_cartao(cartao, cat)

    gerar_lancamentos_cartao_recorrente(item.id, meses_futuros=1, mes_referencia=date(2026, 5, 1))
    db.session.commit()

    gerar_lancamentos_cartao_recorrente(item.id, meses_futuros=1, mes_referencia=date(2026, 6, 1))
    db.session.commit()

    meses = {
        l.mes_fatura
        for l in LancamentoAgregado.query.filter_by(item_despesa_id=item.id).all()
    }
    assert date(2026, 5, 1) in meses
    assert date(2026, 6, 1) in meses


def test_compra_id_deterministico_mesmo_em_chamadas_separadas(app_context):
    cartao = _cartao()
    cat = _categoria()
    item = _item_recorrente_cartao(cartao, cat)

    gerar_lancamentos_cartao_recorrente(item.id, meses_futuros=1, mes_referencia=date(2026, 5, 1))
    db.session.commit()

    lancamento = LancamentoAgregado.query.filter_by(item_despesa_id=item.id).one()
    compra_id_primeira_geracao = lancamento.compra_id

    gerar_lancamentos_cartao_recorrente(item.id, meses_futuros=1, mes_referencia=date(2026, 5, 1))
    db.session.commit()

    # Ainda deve ser o mesmo registro, nao foi recriado
    assert LancamentoAgregado.query.filter_by(item_despesa_id=item.id).count() == 1
    lancamento_reload = LancamentoAgregado.query.filter_by(item_despesa_id=item.id).one()
    assert lancamento_reload.compra_id == compra_id_primeira_geracao


def test_fallback_preenche_compra_id_em_lancamento_legado(app_context):
    """Lançamento antigo (sem compra_id) recebe compra_id retroativamente."""
    cartao = _cartao()
    cat = _categoria()
    item = _item_recorrente_cartao(cartao, cat)

    # Simular lancamento legado: criado manualmente sem compra_id
    legado = LancamentoAgregado(
        cartao_id=cartao.id,
        categoria_id=cat.id,
        descricao=item.nome,
        valor=item.valor,
        data_compra=date(2026, 5, 1),
        mes_fatura=date(2026, 5, 1),
        numero_parcela=1,
        total_parcelas=1,
        is_recorrente=True,
        item_despesa_id=item.id,
        compra_id=None,  # legado: sem compra_id
    )
    db.session.add(legado)
    db.session.commit()
    assert legado.compra_id is None

    # Gerar novamente — deve preencher o compra_id no legado, não criar duplicata
    gerar_lancamentos_cartao_recorrente(item.id, meses_futuros=1, mes_referencia=date(2026, 5, 1))
    db.session.commit()

    assert LancamentoAgregado.query.filter_by(item_despesa_id=item.id).count() == 1
    db.session.refresh(legado)
    assert legado.compra_id is not None


def test_lancamento_recorrente_mantem_vinculo_item_despesa(app_context):
    cartao = _cartao()
    cat = _categoria()
    item = _item_recorrente_cartao(cartao, cat)

    gerar_lancamentos_cartao_recorrente(item.id, meses_futuros=1, mes_referencia=date(2026, 5, 1))
    db.session.commit()

    lancamento = LancamentoAgregado.query.filter_by(item_despesa_id=item.id).one()
    assert lancamento.item_despesa_id == item.id
    assert lancamento.cartao_id == cartao.id
    assert lancamento.is_recorrente is True


# ---------------------------------------------------------------------------
# CORE-FATURA-1: Pagamento seguro de fatura
# ---------------------------------------------------------------------------

def test_pagar_fatura_recalcula_valor_executado(app_context):
    """O valor executado deve ser recalculado a partir dos lançamentos, não usar cache."""
    cartao = _cartao()
    cat = _categoria()
    cb = _conta_bancaria()
    fatura = _fatura(cartao, valor_planejado=99.90)

    # Lançamento real difere do planejado (cache seria errado)
    _lancamento_manual(cartao, cat, valor=150.00)

    CartaoService.pagar_fatura(
        fatura_id=fatura.id,
        data_pagamento=date(2026, 5, 5),
        conta_bancaria_id=cb.id,
    )
    db.session.commit()

    db.session.refresh(fatura)
    assert fatura.valor_executado == Decimal('150.00')
    assert fatura.valor == Decimal('150.00')
    assert fatura.status_pagamento == 'Pago'


def test_pagar_fatura_valor_pago_usa_recalculo_se_nao_informado(app_context):
    cartao = _cartao()
    cat = _categoria()
    cb = _conta_bancaria()
    fatura = _fatura(cartao, valor_planejado=99.90)
    _lancamento_manual(cartao, cat, valor=200.00)

    CartaoService.pagar_fatura(
        fatura_id=fatura.id,
        data_pagamento=date(2026, 5, 5),
        conta_bancaria_id=cb.id,
    )
    db.session.commit()

    db.session.refresh(fatura)
    assert fatura.valor == Decimal('200.00')


def test_pagar_fatura_valor_pago_customizado_sobrepoe_recalculo(app_context):
    cartao = _cartao()
    cat = _categoria()
    cb = _conta_bancaria()
    fatura = _fatura(cartao)
    _lancamento_manual(cartao, cat, valor=200.00)

    CartaoService.pagar_fatura(
        fatura_id=fatura.id,
        data_pagamento=date(2026, 5, 5),
        valor_pago=180.00,
        conta_bancaria_id=cb.id,
    )
    db.session.commit()

    db.session.refresh(fatura)
    # valor_executado = recalculado (200), valor = customizado (180)
    assert fatura.valor_executado == Decimal('200.00')
    assert fatura.valor == Decimal('180.00')


def test_pagar_fatura_ja_paga_bloqueia_com_valueerror(app_context):
    cartao = _cartao()
    cat = _categoria()
    cb = _conta_bancaria(saldo=2000.0)
    fatura = _fatura(cartao)
    _lancamento_manual(cartao, cat, valor=100.00)

    CartaoService.pagar_fatura(
        fatura_id=fatura.id,
        data_pagamento=date(2026, 5, 5),
        conta_bancaria_id=cb.id,
    )
    db.session.commit()

    with pytest.raises(ValueError, match='ja foi paga'):
        CartaoService.pagar_fatura(
            fatura_id=fatura.id,
            data_pagamento=date(2026, 5, 5),
            conta_bancaria_id=cb.id,
        )


def test_pagar_fatura_cria_movimento_debito(app_context):
    cartao = _cartao()
    cat = _categoria()
    cb = _conta_bancaria()
    fatura = _fatura(cartao)
    _lancamento_manual(cartao, cat, valor=150.00)

    CartaoService.pagar_fatura(
        fatura_id=fatura.id,
        data_pagamento=date(2026, 5, 5),
        conta_bancaria_id=cb.id,
    )
    db.session.commit()

    movimentos = MovimentoFinanceiro.query.filter_by(conta_bancaria_id=cb.id).all()
    assert len(movimentos) == 1
    mov = movimentos[0]
    assert mov.tipo == 'DEBITO'
    assert mov.valor == Decimal('150.00')
    assert mov.origem == 'FATURA'
    assert mov.conta_bancaria_id == cb.id


def test_pagar_fatura_debita_saldo_uma_unica_vez(app_context):
    cartao = _cartao()
    cat = _categoria()
    cb = _conta_bancaria(saldo=1000.0)
    fatura = _fatura(cartao)
    _lancamento_manual(cartao, cat, valor=150.00)

    CartaoService.pagar_fatura(
        fatura_id=fatura.id,
        data_pagamento=date(2026, 5, 5),
        conta_bancaria_id=cb.id,
    )
    db.session.commit()

    db.session.refresh(cb)
    assert cb.saldo_atual == Decimal('850.00')  # 1000 - 150


def test_pagar_fatura_duplicada_nao_cria_segundo_movimento(app_context):
    cartao = _cartao()
    cat = _categoria()
    cb = _conta_bancaria(saldo=2000.0)
    fatura = _fatura(cartao)
    _lancamento_manual(cartao, cat, valor=100.00)

    CartaoService.pagar_fatura(
        fatura_id=fatura.id,
        data_pagamento=date(2026, 5, 5),
        conta_bancaria_id=cb.id,
    )
    db.session.commit()

    with pytest.raises(ValueError):
        CartaoService.pagar_fatura(
            fatura_id=fatura.id,
            data_pagamento=date(2026, 5, 5),
            conta_bancaria_id=cb.id,
        )

    assert MovimentoFinanceiro.query.filter_by(conta_bancaria_id=cb.id).count() == 1


def test_pagar_fatura_duplicada_nao_debita_saldo_duas_vezes(app_context):
    cartao = _cartao()
    cat = _categoria()
    cb = _conta_bancaria(saldo=2000.0)
    fatura = _fatura(cartao)
    _lancamento_manual(cartao, cat, valor=100.00)

    CartaoService.pagar_fatura(
        fatura_id=fatura.id,
        data_pagamento=date(2026, 5, 5),
        conta_bancaria_id=cb.id,
    )
    db.session.commit()

    with pytest.raises(ValueError):
        CartaoService.pagar_fatura(
            fatura_id=fatura.id,
            data_pagamento=date(2026, 5, 5),
            conta_bancaria_id=cb.id,
        )

    db.session.refresh(cb)
    assert cb.saldo_atual == Decimal('1900.00')  # 2000 - 100 (uma única vez)


def test_pagar_fatura_conta_bancaria_inexistente_levanta_valueerror(app_context):
    cartao = _cartao()
    cat = _categoria()
    fatura = _fatura(cartao)
    _lancamento_manual(cartao, cat, valor=100.00)

    with pytest.raises(ValueError, match='nao encontrada'):
        CartaoService.pagar_fatura(
            fatura_id=fatura.id,
            data_pagamento=date(2026, 5, 5),
            conta_bancaria_id=99999,
        )


def test_pagar_fatura_conta_bancaria_inativa_levanta_valueerror(app_context):
    cartao = _cartao()
    cat = _categoria()
    cb = _conta_bancaria()
    cb.status = 'INATIVO'
    db.session.commit()
    fatura = _fatura(cartao)
    _lancamento_manual(cartao, cat, valor=100.00)

    with pytest.raises(ValueError, match='inativa'):
        CartaoService.pagar_fatura(
            fatura_id=fatura.id,
            data_pagamento=date(2026, 5, 5),
            conta_bancaria_id=cb.id,
        )


def test_pagar_fatura_sem_conta_bancaria_nao_cria_movimento(app_context):
    """Pagamento sem conta bancária deve ser permitido mas não cria movimento."""
    cartao = _cartao()
    cat = _categoria()
    fatura = _fatura(cartao)
    _lancamento_manual(cartao, cat, valor=100.00)

    CartaoService.pagar_fatura(
        fatura_id=fatura.id,
        data_pagamento=date(2026, 5, 5),
        conta_bancaria_id=None,
    )
    db.session.commit()

    assert MovimentoFinanceiro.query.count() == 0
    db.session.refresh(fatura)
    assert fatura.status_pagamento == 'Pago'


def test_pagar_fatura_lancamento_apos_cache_entra_no_recalculo(app_context):
    """Lançamento adicionado depois do planejamento deve entrar no recálculo."""
    cartao = _cartao()
    cat = _categoria()
    cb = _conta_bancaria(saldo=2000.0)
    fatura = _fatura(cartao, valor_planejado=99.90)

    # Dois lançamentos: planejado era 99.90, mas o real é a soma
    _lancamento_manual(cartao, cat, valor=100.00)
    _lancamento_manual(cartao, cat, valor=50.00)

    CartaoService.pagar_fatura(
        fatura_id=fatura.id,
        data_pagamento=date(2026, 5, 5),
        conta_bancaria_id=cb.id,
    )
    db.session.commit()

    db.session.refresh(fatura)
    assert fatura.valor_executado == Decimal('150.00')
    assert fatura.valor == Decimal('150.00')

    db.session.refresh(cb)
    assert cb.saldo_atual == Decimal('1850.00')  # 2000 - 150


# ---------------------------------------------------------------------------
# Integração: ciclo completo
# ---------------------------------------------------------------------------

def test_ciclo_completo_criar_gerar_pagar(app_context):
    """
    Ciclo completo: criar cartão → criar recorrência → gerar → re-gerar (sem dup)
    → criar fatura → pagar → verificar valor e saldo.
    """
    # Setup
    cartao = _cartao()
    cat = _categoria()
    cb = _conta_bancaria(saldo=500.0)
    item = _item_recorrente_cartao(cartao, cat, valor=99.90)

    # Gerar lançamentos recorrentes
    gerar_lancamentos_cartao_recorrente(item.id, meses_futuros=1, mes_referencia=date(2026, 5, 1))
    db.session.commit()
    assert LancamentoAgregado.query.filter_by(item_despesa_id=item.id).count() == 1

    # Re-gerar: sem duplicata
    gerar_lancamentos_cartao_recorrente(item.id, meses_futuros=1, mes_referencia=date(2026, 5, 1))
    db.session.commit()
    assert LancamentoAgregado.query.filter_by(item_despesa_id=item.id).count() == 1

    # Verificar compra_id presente
    lanc = LancamentoAgregado.query.filter_by(item_despesa_id=item.id).one()
    assert lanc.compra_id is not None

    # Criar fatura (valor planejado ainda é estimativa)
    fatura = _fatura(cartao, valor_planejado=90.00)

    # Recalcular fatura via pagar (valor real = 99.90, diferente do planejado 90.00)
    CartaoService.pagar_fatura(
        fatura_id=fatura.id,
        data_pagamento=date(2026, 5, 5),
        conta_bancaria_id=cb.id,
    )
    db.session.commit()

    # Verificar fatura
    db.session.refresh(fatura)
    assert fatura.status_pagamento == 'Pago'
    assert fatura.valor_executado == Decimal('99.90')
    assert fatura.valor == Decimal('99.90')
    assert fatura.conta_bancaria_id == cb.id

    # Verificar saldo debitado uma vez
    db.session.refresh(cb)
    assert cb.saldo_atual == Decimal('400.10')  # 500 - 99.90

    # Verificar movimento criado
    mov = MovimentoFinanceiro.query.filter_by(conta_bancaria_id=cb.id).one()
    assert mov.tipo == 'DEBITO'
    assert mov.valor == Decimal('99.90')
    assert mov.origem == 'FATURA'

    # Segunda tentativa de pagamento deve falhar
    with pytest.raises(ValueError, match='ja foi paga'):
        CartaoService.pagar_fatura(
            fatura_id=fatura.id,
            data_pagamento=date(2026, 5, 5),
            conta_bancaria_id=cb.id,
        )

    # Saldo não muda após segunda tentativa bloqueada
    db.session.refresh(cb)
    assert cb.saldo_atual == Decimal('400.10')
