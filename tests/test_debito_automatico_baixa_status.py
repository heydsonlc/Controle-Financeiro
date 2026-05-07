"""
DA-AUTO-STATUS-1 — Testes de baixa automática de despesas em Débito Automático.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from backend.app import create_app
from backend.models import (
    Conta,
    ContaBancaria,
    ItemDespesa,
    MovimentoFinanceiro,
    PerfilFinanceiro,
    db,
)
from backend.services.debito_automatico_service import executar_baixa_debito_automatico
from backend.services.perfil_financeiro_service import PerfilFinanceiroService


HOJE = date.today()
ONTEM = HOJE - timedelta(days=1)
AMANHA = HOJE + timedelta(days=1)


@pytest.fixture()
def app_context():
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        PerfilFinanceiroService.obter_ou_criar_perfis_iniciais()
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


def _perfil(nome='Pessoal'):
    return PerfilFinanceiro.query.filter_by(nome=nome).first()


def _conta_bancaria(perfil, saldo=Decimal('1000.00'), nome='CB Teste'):
    cb = ContaBancaria(
        perfil_financeiro_id=perfil.id,
        nome=nome,
        instituicao='Banco Teste',
        tipo='Conta Corrente',
        saldo_inicial=saldo,
        saldo_atual=saldo,
        status='ATIVO',
    )
    db.session.add(cb)
    db.session.flush()
    return cb


def _item_despesa(perfil, conta_bancaria=None, meio='debito_automatico'):
    item = ItemDespesa(
        perfil_financeiro_id=perfil.id,
        nome='Despesa Teste',
        tipo='Simples',
        valor=Decimal('200.00'),
        data_vencimento=HOJE,
        recorrente=False,
        tipo_recorrencia='mensal',
        meio_pagamento=meio,
        conta_bancaria_id=conta_bancaria.id if conta_bancaria else None,
        ativo=True,
        pago=False,
    )
    db.session.add(item)
    db.session.flush()
    return item


def _conta(item, conta_bancaria=None, vencimento=None, status='Pendente', valor=None):
    cb_id = conta_bancaria.id if conta_bancaria else item.conta_bancaria_id
    conta = Conta(
        perfil_financeiro_id=item.perfil_financeiro_id,
        item_despesa_id=item.id,
        mes_referencia=(vencimento or HOJE).replace(day=1),
        descricao=item.nome,
        valor=valor or item.valor,
        data_vencimento=vencimento or HOJE,
        data_pagamento=None,
        status_pagamento=status,
        debito_automatico=(item.meio_pagamento == 'debito_automatico'),
        conta_bancaria_id=cb_id,
        numero_parcela=1,
        total_parcelas=1,
        is_fatura_cartao=False,
    )
    db.session.add(conta)
    db.session.flush()
    return conta


# ---------------------------------------------------------------------------
# 1. Despesa pendente DA, vencida, conta vinculada, saldo suficiente → vira Paga
# ---------------------------------------------------------------------------
def test_despesa_da_vencida_saldo_suficiente_vira_paga(app_context):
    perfil = _perfil()
    cb = _conta_bancaria(perfil, saldo=Decimal('500.00'))
    item = _item_despesa(perfil, cb)
    conta = _conta(item, cb, vencimento=ONTEM)
    db.session.commit()

    baixadas = executar_baixa_debito_automatico(perfil.id)

    assert conta.id in baixadas
    assert conta.status_pagamento == 'Pago'
    assert conta.data_pagamento == ONTEM  # data_vencimento


# ---------------------------------------------------------------------------
# 2. Saldo insuficiente → permanece pendente
# ---------------------------------------------------------------------------
def test_saldo_insuficiente_permanece_pendente(app_context):
    perfil = _perfil()
    cb = _conta_bancaria(perfil, saldo=Decimal('50.00'))
    item = _item_despesa(perfil, cb)
    conta = _conta(item, cb, vencimento=ONTEM, valor=Decimal('200.00'))
    db.session.commit()

    baixadas = executar_baixa_debito_automatico(perfil.id)

    assert conta.id not in baixadas
    assert conta.status_pagamento == 'Pendente'


# ---------------------------------------------------------------------------
# 3. Despesa futura não é baixada antes do vencimento
# ---------------------------------------------------------------------------
def test_despesa_futura_nao_e_baixada(app_context):
    perfil = _perfil()
    cb = _conta_bancaria(perfil, saldo=Decimal('1000.00'))
    item = _item_despesa(perfil, cb)
    conta = _conta(item, cb, vencimento=AMANHA)
    db.session.commit()

    baixadas = executar_baixa_debito_automatico(perfil.id)

    assert conta.id not in baixadas
    assert conta.status_pagamento == 'Pendente'


# ---------------------------------------------------------------------------
# 4. Despesa sem conta bancária não é baixada
# ---------------------------------------------------------------------------
def test_sem_conta_bancaria_nao_e_baixada(app_context):
    perfil = _perfil()
    item = _item_despesa(perfil, conta_bancaria=None)
    conta = Conta(
        perfil_financeiro_id=perfil.id,
        item_despesa_id=item.id,
        mes_referencia=HOJE.replace(day=1),
        descricao=item.nome,
        valor=Decimal('200.00'),
        data_vencimento=ONTEM,
        status_pagamento='Pendente',
        debito_automatico=True,
        conta_bancaria_id=None,
        numero_parcela=1,
        total_parcelas=1,
        is_fatura_cartao=False,
    )
    db.session.add(conta)
    db.session.commit()

    baixadas = executar_baixa_debito_automatico(perfil.id)

    assert conta.id not in baixadas
    assert conta.status_pagamento == 'Pendente'


# ---------------------------------------------------------------------------
# 5. Meio de pagamento diferente de debito_automatico não é baixado
# ---------------------------------------------------------------------------
def test_meio_pagamento_diferente_nao_e_baixado(app_context):
    perfil = _perfil()
    cb = _conta_bancaria(perfil, saldo=Decimal('1000.00'))
    item = _item_despesa(perfil, cb, meio='pix')
    # debito_automatico=False explícito
    conta = Conta(
        perfil_financeiro_id=perfil.id,
        item_despesa_id=item.id,
        mes_referencia=HOJE.replace(day=1),
        descricao='Despesa Pix',
        valor=Decimal('200.00'),
        data_vencimento=ONTEM,
        status_pagamento='Pendente',
        debito_automatico=False,
        conta_bancaria_id=cb.id,
        numero_parcela=1,
        total_parcelas=1,
        is_fatura_cartao=False,
    )
    db.session.add(conta)
    db.session.commit()

    baixadas = executar_baixa_debito_automatico(perfil.id)

    assert conta.id not in baixadas
    assert conta.status_pagamento == 'Pendente'


# ---------------------------------------------------------------------------
# 6. Despesa já paga não é reprocessada
# ---------------------------------------------------------------------------
def test_despesa_ja_paga_nao_e_reprocessada(app_context):
    perfil = _perfil()
    cb = _conta_bancaria(perfil, saldo=Decimal('1000.00'))
    item = _item_despesa(perfil, cb)
    conta = _conta(item, cb, vencimento=ONTEM, status='Pago')
    conta.data_pagamento = ONTEM
    db.session.commit()

    # Registrar movimento existente para garantir que não duplica
    mov = MovimentoFinanceiro(
        perfil_financeiro_id=perfil.id,
        conta_bancaria_id=cb.id,
        tipo='DEBITO',
        valor=Decimal('200.00'),
        descricao='Pago manualmente',
        data_movimento=ONTEM,
        conta_id=conta.id,
        origem='DESPESA',
        ajustavel=False,
    )
    db.session.add(mov)
    db.session.commit()

    movimentos_antes = MovimentoFinanceiro.query.filter_by(conta_id=conta.id).count()
    baixadas = executar_baixa_debito_automatico(perfil.id)

    assert conta.id not in baixadas
    movimentos_depois = MovimentoFinanceiro.query.filter_by(conta_id=conta.id).count()
    assert movimentos_depois == movimentos_antes  # sem duplicata


# ---------------------------------------------------------------------------
# 7. Idempotência — chamar duas vezes não duplica movimento nem status
# ---------------------------------------------------------------------------
def test_baixa_automatica_e_idempotente(app_context):
    perfil = _perfil()
    cb = _conta_bancaria(perfil, saldo=Decimal('1000.00'))
    item = _item_despesa(perfil, cb)
    conta = _conta(item, cb, vencimento=ONTEM)
    db.session.commit()

    executar_baixa_debito_automatico(perfil.id)
    movimentos_1a = MovimentoFinanceiro.query.filter_by(conta_id=conta.id).count()
    status_1a = conta.status_pagamento

    executar_baixa_debito_automatico(perfil.id)
    movimentos_2a = MovimentoFinanceiro.query.filter_by(conta_id=conta.id).count()
    status_2a = conta.status_pagamento

    assert status_1a == 'Pago'
    assert status_2a == 'Pago'
    assert movimentos_1a == 1
    assert movimentos_2a == 1  # não duplicou


# ---------------------------------------------------------------------------
# 8. Conta de outro perfil não é usada
# ---------------------------------------------------------------------------
def test_conta_de_outro_perfil_nao_e_usada(app_context):
    perfil_pessoal = _perfil('Pessoal')
    perfil_empresa = _perfil('Empresa')

    # Conta bancária pertence ao perfil Empresa
    cb_empresa = ContaBancaria(
        perfil_financeiro_id=perfil_empresa.id,
        nome='CB Empresa',
        instituicao='Banco',
        tipo='Conta Corrente',
        saldo_inicial=Decimal('5000.00'),
        saldo_atual=Decimal('5000.00'),
        status='ATIVO',
    )
    db.session.add(cb_empresa)
    db.session.flush()

    # ItemDespesa pertence ao perfil Pessoal mas aponta para conta do Empresa
    item = ItemDespesa(
        perfil_financeiro_id=perfil_pessoal.id,
        nome='Despesa Cruzada',
        tipo='Simples',
        valor=Decimal('200.00'),
        data_vencimento=HOJE,
        recorrente=False,
        tipo_recorrencia='mensal',
        meio_pagamento='debito_automatico',
        conta_bancaria_id=cb_empresa.id,
        ativo=True,
        pago=False,
    )
    db.session.add(item)
    db.session.flush()

    conta = Conta(
        perfil_financeiro_id=perfil_pessoal.id,
        item_despesa_id=item.id,
        mes_referencia=HOJE.replace(day=1),
        descricao='Despesa Cruzada',
        valor=Decimal('200.00'),
        data_vencimento=ONTEM,
        status_pagamento='Pendente',
        debito_automatico=True,
        conta_bancaria_id=cb_empresa.id,  # conta de outro perfil
        numero_parcela=1,
        total_parcelas=1,
        is_fatura_cartao=False,
    )
    db.session.add(conta)
    db.session.commit()

    # Roda para o perfil Pessoal — a conta bancária não pertence a ele
    baixadas = executar_baixa_debito_automatico(perfil_pessoal.id)

    assert conta.id not in baixadas
    assert conta.status_pagamento == 'Pendente'


# ---------------------------------------------------------------------------
# 9. Movimento financeiro é criado e não duplicado na baixa
# ---------------------------------------------------------------------------
def test_movimento_financeiro_criado_e_nao_duplicado(app_context):
    perfil = _perfil()
    cb = _conta_bancaria(perfil, saldo=Decimal('1000.00'))
    item = _item_despesa(perfil, cb)
    conta = _conta(item, cb, vencimento=ONTEM)
    db.session.commit()

    assert MovimentoFinanceiro.query.filter_by(conta_id=conta.id).count() == 0

    executar_baixa_debito_automatico(perfil.id)

    movimentos = MovimentoFinanceiro.query.filter_by(conta_id=conta.id).all()
    assert len(movimentos) == 1
    assert movimentos[0].tipo == 'DEBITO'
    assert movimentos[0].origem == 'DESPESA'
    assert movimentos[0].valor == Decimal('200.00')

    # Segunda chamada — não cria novo movimento
    executar_baixa_debito_automatico(perfil.id)
    assert MovimentoFinanceiro.query.filter_by(conta_id=conta.id).count() == 1


# ---------------------------------------------------------------------------
# 10. Listagem de despesas (GET /api/despesas) dispara avaliação
# ---------------------------------------------------------------------------
def test_listagem_de_despesas_dispara_baixa_automatica(app_context):
    perfil = _perfil()

    with app_context.test_client() as client:
        with client.session_transaction() as sess:
            sess['perfil_financeiro_id'] = perfil.id

        cb = _conta_bancaria(perfil, saldo=Decimal('500.00'))
        item = _item_despesa(perfil, cb)
        conta = _conta(item, cb, vencimento=ONTEM)
        db.session.commit()

        assert conta.status_pagamento == 'Pendente'

        r = client.get('/api/despesas/')

    assert r.status_code == 200
    # Após listagem, a despesa deve ter sido baixada
    db.session.refresh(conta)
    assert conta.status_pagamento == 'Pago'
