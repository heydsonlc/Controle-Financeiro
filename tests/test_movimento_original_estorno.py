"""
Testes MOV-REF-1 — Referência explícita ao movimento original nos estornos.

MovimentoFinanceiro.movimento_original_id aponta diretamente do movimento de
estorno para o movimento financeiro original que ele compensa. Campo nullable:
estornos anteriores a esta coluna continuam válidos e bloqueados por
duplicidade via a lógica indireta legada (origem + conta_id/receita_realizada_id/
financiamento_parcela_id).

Cobre os quatro módulos: despesa, receita, fatura, financiamento.
"""
from datetime import date
from decimal import Decimal

import pytest
from flask import Flask

from backend.models import (
    Conta,
    ContaBancaria,
    Financiamento,
    FinanciamentoParcela,
    ItemDespesa,
    ItemReceita,
    MovimentoFinanceiro,
    ReceitaRealizada,
    db,
)
from backend.routes.despesas import despesas_bp
from backend.routes.receitas import receitas_bp
from backend.routes.financiamentos import financiamentos_bp
from backend.routes.contas_bancarias import contas_bancarias_bp


@pytest.fixture()
def client():
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    app.register_blueprint(despesas_bp, url_prefix='/api/despesas')
    app.register_blueprint(receitas_bp, url_prefix='/api/receitas')
    app.register_blueprint(financiamentos_bp, url_prefix='/api/financiamentos')
    app.register_blueprint(contas_bancarias_bp, url_prefix='/api/contas')

    with app.app_context():
        db.create_all()
        with app.test_client() as c:
            yield c
        db.session.remove()
        db.drop_all()


def _conta_bancaria(saldo=Decimal('10000.00')):
    cb = ContaBancaria(
        nome='Conta Teste', instituicao='Banco', tipo='Conta Corrente',
        saldo_inicial=saldo, saldo_atual=saldo, status='ATIVO',
    )
    db.session.add(cb)
    db.session.commit()
    return cb.id


# ---------------------------------------------------------------------------
# 1. Despesa: estorno grava movimento_original_id
# ---------------------------------------------------------------------------

def test_estorno_despesa_grava_movimento_original_id(client):
    cb_id = _conta_bancaria()
    item = ItemDespesa(nome='Item Teste', tipo='Simples', ativo=True)
    db.session.add(item)
    db.session.commit()
    conta = Conta(
        item_despesa_id=item.id, mes_referencia=date(2026, 5, 1),
        descricao='Despesa Teste', valor=Decimal('100.00'),
        data_vencimento=date(2026, 5, 1), status_pagamento='Pendente',
    )
    db.session.add(conta)
    db.session.commit()

    client.post(f'/api/despesas/{conta.id}/pagar', json={
        'conta_bancaria_id': cb_id, 'data_pagamento': '2026-05-10',
    })
    mov_original = MovimentoFinanceiro.query.filter_by(conta_id=conta.id, tipo='DEBITO').first()
    assert mov_original is not None

    resp = client.post(f'/api/despesas/{conta.id}/estornar-pagamento', json={
        'data_estorno': '2026-05-11', 'motivo': 'Engano',
    })
    assert resp.status_code == 200

    mov_estorno = MovimentoFinanceiro.query.filter_by(conta_id=conta.id, origem='ESTORNO_DESPESA').first()
    assert mov_estorno is not None
    assert mov_estorno.movimento_original_id == mov_original.id


# ---------------------------------------------------------------------------
# 2. Receita: estorno grava movimento_original_id
# ---------------------------------------------------------------------------

def test_estorno_receita_grava_movimento_original_id(client):
    cb_id = _conta_bancaria()
    item = ItemReceita(nome='Fonte Teste', tipo='OUTROS', ativo=True, recorrente=False)
    db.session.add(item)
    db.session.commit()

    resp_receber = client.post('/api/receitas/realizadas', json={
        'item_receita_id': item.id, 'data_recebimento': '2026-05-05',
        'valor_recebido': 1000.0, 'competencia': '2026-05-01', 'conta_bancaria_id': cb_id,
    })
    receita_id = resp_receber.get_json()['data']['id']
    mov_original = MovimentoFinanceiro.query.filter_by(receita_realizada_id=receita_id, origem='RECEITA').first()
    assert mov_original is not None

    resp = client.post(f'/api/receitas/realizadas/{receita_id}/estornar', json={
        'data_estorno': '2026-05-11', 'motivo': 'Engano',
    })
    assert resp.status_code == 200

    mov_estorno = MovimentoFinanceiro.query.filter_by(receita_realizada_id=receita_id, origem='ESTORNO_RECEITA').first()
    assert mov_estorno is not None
    assert mov_estorno.movimento_original_id == mov_original.id


# ---------------------------------------------------------------------------
# 3. Fatura: estorno grava movimento_original_id
# ---------------------------------------------------------------------------

def test_estorno_fatura_grava_movimento_original_id(client):
    from backend.services.conta_bancaria_service import ContaBancariaService

    cb_id = _conta_bancaria()
    cartao = ItemDespesa(nome='Cartao Teste', tipo='Agregador', ativo=True)
    db.session.add(cartao)
    db.session.commit()
    fatura = Conta(
        item_despesa_id=cartao.id, mes_referencia=date(2026, 5, 1),
        descricao='Fatura Teste', valor=Decimal('3000.00'),
        data_vencimento=date(2026, 5, 10), status_pagamento='Pendente',
        is_fatura_cartao=True, valor_executado=Decimal('3000.00'),
        cartao_competencia=date(2026, 5, 1), status_fatura='ABERTA',
    )
    db.session.add(fatura)
    db.session.commit()

    mov_original = ContaBancariaService.criar_movimento(
        cb_id, tipo='DEBITO', valor=Decimal('3000.00'),
        descricao='Pagamento fatura', data_movimento=date(2026, 5, 10),
        origem='FATURA', fatura_id=fatura.id, conta_id=fatura.id,
    )
    fatura.conta_bancaria_id = cb_id
    fatura.status_pagamento = 'Pago'
    fatura.data_pagamento = date(2026, 5, 10)
    db.session.commit()
    mov_original_id = mov_original.id

    resp = client.post(f'/api/despesas/{fatura.id}/estornar-pagamento', json={
        'data_estorno': '2026-05-11', 'motivo': 'Engano',
    })
    assert resp.status_code == 200

    mov_estorno = MovimentoFinanceiro.query.filter_by(conta_id=fatura.id, origem='ESTORNO_FATURA').first()
    assert mov_estorno is not None
    assert mov_estorno.movimento_original_id == mov_original_id


# ---------------------------------------------------------------------------
# 4. Financiamento: estorno grava movimento_original_id
# ---------------------------------------------------------------------------

def test_estorno_financiamento_grava_movimento_original_id(client):
    cb_id = _conta_bancaria()
    fin = Financiamento(
        nome='Financiamento Teste', sistema_amortizacao='SAC',
        valor_financiado=Decimal('100000.00'), prazo_total_meses=360,
        prazo_remanescente_meses=360, taxa_juros_nominal_anual=Decimal('8.0000'),
        taxa_juros_mensal=Decimal('0.006434'), data_contrato=date(2025, 1, 1),
        data_primeira_parcela=date(2025, 2, 1), saldo_devedor_atual=Decimal('100000.00'),
    )
    db.session.add(fin)
    db.session.flush()
    parcela = FinanciamentoParcela(
        financiamento_id=fin.id, numero_parcela=1, data_vencimento=date(2026, 5, 1),
        valor_amortizacao=Decimal('800.00'), valor_juros=Decimal('500.00'),
        valor_previsto_total=Decimal('1300.00'), status='pendente',
        saldo_devedor_apos_pagamento=Decimal('99200.00'),
    )
    db.session.add(parcela)
    db.session.commit()

    client.post(f'/api/financiamentos/parcelas/{parcela.id}/pagar', json={
        'conta_bancaria_id': cb_id, 'data_pagamento': '2026-05-10',
    })
    mov_original = MovimentoFinanceiro.query.filter_by(
        financiamento_parcela_id=parcela.id, origem='FINANCIAMENTO',
    ).first()
    assert mov_original is not None

    resp = client.post(f'/api/financiamentos/parcelas/{parcela.id}/estornar-pagamento', json={
        'data_estorno': '2026-05-11', 'motivo': 'Engano',
    })
    assert resp.status_code == 200

    mov_estorno = MovimentoFinanceiro.query.filter_by(
        financiamento_parcela_id=parcela.id, origem='ESTORNO_FINANCIAMENTO',
    ).first()
    assert mov_estorno is not None
    assert mov_estorno.movimento_original_id == mov_original.id


# ---------------------------------------------------------------------------
# 5. Duplicidade bloqueada por movimento_original_id
# ---------------------------------------------------------------------------

def test_duplicidade_bloqueada_via_movimento_original_id(client):
    """Injeta um estorno com movimento_original_id preenchido mas SEM o vinculo
    legado (conta_id), para provar que a checagem preferencial funciona sozinha."""
    cb_id = _conta_bancaria()
    item = ItemDespesa(nome='Item Teste', tipo='Simples', ativo=True)
    db.session.add(item)
    db.session.commit()
    conta = Conta(
        item_despesa_id=item.id, mes_referencia=date(2026, 5, 1),
        descricao='Despesa Teste', valor=Decimal('100.00'),
        data_vencimento=date(2026, 5, 1), status_pagamento='Pendente',
    )
    db.session.add(conta)
    db.session.commit()

    client.post(f'/api/despesas/{conta.id}/pagar', json={
        'conta_bancaria_id': cb_id, 'data_pagamento': '2026-05-10',
    })
    mov_original = MovimentoFinanceiro.query.filter_by(conta_id=conta.id, tipo='DEBITO').first()

    # Estorno "preferencial": tem movimento_original_id mas NAO tem conta_id
    # (simula um cenario onde so o vinculo novo existe)
    estorno_manual = MovimentoFinanceiro(
        conta_bancaria_id=cb_id, tipo='CREDITO', valor=Decimal('100.00'),
        descricao='Estorno manual', data_movimento=date(2026, 5, 11),
        origem='ESTORNO_DESPESA', movimento_original_id=mov_original.id,
        conta_id=None,
    )
    db.session.add(estorno_manual)
    db.session.commit()

    resp = client.post(f'/api/despesas/{conta.id}/estornar-pagamento', json={
        'data_estorno': '2026-05-12', 'motivo': 'Segunda tentativa',
    })
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# 6. Fallback legado: duplicidade bloqueada mesmo sem movimento_original_id
# ---------------------------------------------------------------------------

def test_fallback_legado_bloqueia_duplicidade_sem_movimento_original_id(client):
    """Simula um estorno 'antigo' (criado antes desta coluna existir): sem
    movimento_original_id, mas com o vinculo indireto (conta_id + origem).
    A nova tentativa de estorno deve ser bloqueada pelo fallback."""
    cb_id = _conta_bancaria()
    item = ItemDespesa(nome='Item Teste', tipo='Simples', ativo=True)
    db.session.add(item)
    db.session.commit()
    conta = Conta(
        item_despesa_id=item.id, mes_referencia=date(2026, 5, 1),
        descricao='Despesa Teste', valor=Decimal('100.00'),
        data_vencimento=date(2026, 5, 1), status_pagamento='Pago',
        data_pagamento=date(2026, 5, 10), conta_bancaria_id=cb_id,
    )
    db.session.add(conta)
    db.session.commit()

    # Movimento original "antigo" preservado sem alteracao
    mov_original = MovimentoFinanceiro(
        conta_bancaria_id=cb_id, tipo='DEBITO', valor=Decimal('100.00'),
        descricao='Pagamento despesa (legado)', data_movimento=date(2026, 5, 10),
        origem='DESPESA', conta_id=conta.id,
    )
    db.session.add(mov_original)
    db.session.flush()

    # Estorno "legado" sem movimento_original_id
    estorno_legado = MovimentoFinanceiro(
        conta_bancaria_id=cb_id, tipo='CREDITO', valor=Decimal('100.00'),
        descricao='Estorno legado', data_movimento=date(2026, 5, 11),
        origem='ESTORNO_DESPESA', conta_id=conta.id, movimento_original_id=None,
    )
    db.session.add(estorno_legado)
    db.session.commit()

    resp = client.post(f'/api/despesas/{conta.id}/estornar-pagamento', json={
        'data_estorno': '2026-05-12', 'motivo': 'Segunda tentativa',
    })
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# 7. Movimento original permanece inalterado apos o estorno
# ---------------------------------------------------------------------------

def test_movimento_original_permanece_inalterado_apos_estorno(client):
    cb_id = _conta_bancaria()
    item = ItemDespesa(nome='Item Teste', tipo='Simples', ativo=True)
    db.session.add(item)
    db.session.commit()
    conta = Conta(
        item_despesa_id=item.id, mes_referencia=date(2026, 5, 1),
        descricao='Despesa Teste', valor=Decimal('100.00'),
        data_vencimento=date(2026, 5, 1), status_pagamento='Pendente',
    )
    db.session.add(conta)
    db.session.commit()

    client.post(f'/api/despesas/{conta.id}/pagar', json={
        'conta_bancaria_id': cb_id, 'data_pagamento': '2026-05-10',
    })
    mov_original = MovimentoFinanceiro.query.filter_by(conta_id=conta.id, tipo='DEBITO').first()
    valor_antes = mov_original.valor
    tipo_antes = mov_original.tipo
    origem_antes = mov_original.origem
    data_antes = mov_original.data_movimento

    client.post(f'/api/despesas/{conta.id}/estornar-pagamento', json={
        'data_estorno': '2026-05-11', 'motivo': 'Engano',
    })

    mov_original_depois = MovimentoFinanceiro.query.get(mov_original.id)
    assert mov_original_depois.valor == valor_antes
    assert mov_original_depois.tipo == tipo_antes
    assert mov_original_depois.origem == origem_antes
    assert mov_original_depois.data_movimento == data_antes
    assert mov_original_depois.movimento_original_id is None


# ---------------------------------------------------------------------------
# 8. Saldo continua correto com a nova coluna
# ---------------------------------------------------------------------------

def test_saldo_continua_correto_apos_estorno_com_movimento_original_id(client):
    cb_id = _conta_bancaria(Decimal('1000.00'))
    item = ItemDespesa(nome='Item Teste', tipo='Simples', ativo=True)
    db.session.add(item)
    db.session.commit()
    conta = Conta(
        item_despesa_id=item.id, mes_referencia=date(2026, 5, 1),
        descricao='Despesa Teste', valor=Decimal('100.00'),
        data_vencimento=date(2026, 5, 1), status_pagamento='Pendente',
    )
    db.session.add(conta)
    db.session.commit()

    client.post(f'/api/despesas/{conta.id}/pagar', json={
        'conta_bancaria_id': cb_id, 'data_pagamento': '2026-05-10',
    })
    client.post(f'/api/despesas/{conta.id}/estornar-pagamento', json={
        'data_estorno': '2026-05-11', 'motivo': 'Engano',
    })

    resp = client.get(f'/api/contas/{cb_id}/conferir-saldo')
    r = resp.get_json()['data']
    assert r['consistente'] is True
    assert r['saldo_calculado'] == 1000.0
