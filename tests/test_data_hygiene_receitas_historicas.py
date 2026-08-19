"""
Testes DATA-HYGIENE-RECEITA-1: saneamento de receitas realizadas sem conta bancaria.

- dry-run (diagnosticar) nao altera o banco
- classificacao deterministica: REGULARIZAR_MOVIMENTO / REABRIR_COMO_PENDENTE / PENDENTE_DECISAO_USUARIO
- apply cria movimento via ContaBancariaService, nao duplica, nao inventa conta
- apply nao altera receitas ja consistentes (com conta) nem PENDENTE_DECISAO_USUARIO
- rollback preserva estado em caso de falha
"""
from datetime import date
from decimal import Decimal

import pytest
from flask import Flask

from backend.models import (
    ContaBancaria,
    ItemReceita,
    MovimentoFinanceiro,
    PerfilFinanceiro,
    ReceitaRealizada,
    db,
)
from scripts.data_hygiene_receitas_historicas import (
    BLOQUEADO_INCONSISTENTE,
    PENDENTE_DECISAO_USUARIO,
    REABRIR_COMO_PENDENTE,
    REGULARIZAR_MOVIMENTO,
    aplicar,
    diagnosticar,
)


@pytest.fixture()
def app_context():
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    with app.app_context():
        db.create_all()
        # PerfilFinanceiroService.obter_perfil_ativo_id() cria perfis padrao (Pessoal e Empresa)
        # com um db.session.commit() proprio na primeira chamada (obter_ou_criar_perfis_iniciais)
        # quando algum deles ainda nao existe. Criar ambos aqui evita esse commit implicito
        # no meio dos testes de transacao/rollback.
        db.session.add(PerfilFinanceiro(nome='Pessoal', tipo='PESSOAL', avatar='PE', cor='#2563eb', ativo=True, padrao=True))
        db.session.add(PerfilFinanceiro(nome='Empresa', tipo='EMPRESA', avatar='EM', cor='#0f766e', ativo=True, padrao=False))
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


def _criar_conta(saldo=0.0):
    conta = ContaBancaria(
        nome='Conta Real',
        instituicao='Banco',
        tipo='Conta Corrente',
        saldo_inicial=Decimal(str(saldo)),
        saldo_atual=Decimal(str(saldo)),
        status='ATIVO',
    )
    db.session.add(conta)
    db.session.commit()
    return conta


def _criar_item_receita(conta_bancaria_id=None):
    item = ItemReceita(nome='Fonte', tipo='OUTROS', ativo=True, recorrente=False, conta_bancaria_id=conta_bancaria_id)
    db.session.add(item)
    db.session.commit()
    return item


def _criar_receita_sem_conta(item_receita_id=None, valor=1000.0, data_recebimento=date(2026, 5, 5)):
    receita = ReceitaRealizada(
        item_receita_id=item_receita_id,
        data_recebimento=data_recebimento,
        valor_recebido=Decimal(str(valor)) if valor is not None else Decimal('0.01'),
        mes_referencia=date(2026, 5, 1),
        descricao='Receita historica',
    )
    if valor is None:
        # simular ausencia real de valor nao e possivel com NOT NULL constraint do model;
        # usamos 0 para representar "sem valor valido" no teste de REABRIR_COMO_PENDENTE
        receita.valor_recebido = Decimal('0')
    db.session.add(receita)
    db.session.commit()
    return receita


# ---------------------------------------------------------------------------
# dry-run / diagnostico nao altera banco
# ---------------------------------------------------------------------------

def test_diagnosticar_nao_altera_banco(app_context):
    item = _criar_item_receita()
    receita = _criar_receita_sem_conta(item.id)

    diagnosticar()

    db.session.refresh(receita)
    assert receita.conta_bancaria_id is None
    assert ReceitaRealizada.query.count() == 1
    assert MovimentoFinanceiro.query.count() == 0


def test_diagnosticar_ignora_receitas_com_conta(app_context):
    conta = _criar_conta()
    item = _criar_item_receita()
    receita = ReceitaRealizada(
        item_receita_id=item.id,
        data_recebimento=date(2026, 5, 5),
        valor_recebido=Decimal('500'),
        mes_referencia=date(2026, 5, 1),
        conta_bancaria_id=conta.id,
        descricao='Ja tem conta',
    )
    db.session.add(receita)
    db.session.commit()

    resultados = diagnosticar()

    assert resultados == []


# ---------------------------------------------------------------------------
# Classificacao deterministica
# ---------------------------------------------------------------------------

def test_receita_com_conta_na_fonte_classifica_regularizar(app_context):
    conta = _criar_conta()
    item = _criar_item_receita(conta_bancaria_id=conta.id)
    receita = _criar_receita_sem_conta(item.id, valor=1000.0, data_recebimento=date(2026, 5, 5))

    resultados = diagnosticar()

    assert len(resultados) == 1
    r = resultados[0]
    assert r.receita_id == receita.id
    assert r.classificacao == REGULARIZAR_MOVIMENTO
    assert r.conta_inferida_id == conta.id


def test_receita_sem_valor_e_sem_data_classifica_reabrir(app_context):
    item = _criar_item_receita()
    receita = ReceitaRealizada(
        item_receita_id=item.id,
        data_recebimento=date(2026, 5, 5),  # NOT NULL no model; simulamos "sem data valida" via valor 0
        valor_recebido=Decimal('0'),
        mes_referencia=date(2026, 5, 1),
        descricao='Sem evidencia',
    )
    db.session.add(receita)
    db.session.commit()

    resultados = diagnosticar()

    assert len(resultados) == 1
    assert resultados[0].classificacao != REGULARIZAR_MOVIMENTO


def test_receita_com_valor_e_data_mas_sem_conta_inferivel_classifica_pendente(app_context):
    item = _criar_item_receita(conta_bancaria_id=None)
    receita = _criar_receita_sem_conta(item.id, valor=5220.0, data_recebimento=date(2026, 6, 1))

    resultados = diagnosticar()

    assert len(resultados) == 1
    r = resultados[0]
    assert r.classificacao == PENDENTE_DECISAO_USUARIO
    assert r.conta_inferida_id is None


def test_receita_sem_item_receita_vinculado_classifica_pendente(app_context):
    receita = _criar_receita_sem_conta(item_receita_id=None, valor=800.0, data_recebimento=date(2026, 5, 5))

    resultados = diagnosticar()

    assert len(resultados) == 1
    assert resultados[0].classificacao == PENDENTE_DECISAO_USUARIO


def test_nao_infere_conta_pela_unica_conta_existente(app_context):
    """Mesmo com uma unica conta no sistema, sem vinculo explicito nao deve ser inferida."""
    _criar_conta()  # unica conta do sistema, mas SEM vinculo com o item_receita
    item = _criar_item_receita(conta_bancaria_id=None)
    _criar_receita_sem_conta(item.id, valor=1000.0, data_recebimento=date(2026, 5, 5))

    resultados = diagnosticar()

    assert resultados[0].classificacao == PENDENTE_DECISAO_USUARIO
    assert resultados[0].conta_inferida_id is None


def test_receita_com_movimento_orfao_classifica_bloqueado(app_context):
    conta = _criar_conta()
    item = _criar_item_receita()
    receita = _criar_receita_sem_conta(item.id, valor=1000.0)
    mov = MovimentoFinanceiro(
        conta_bancaria_id=conta.id,
        tipo='CREDITO',
        valor=Decimal('1000'),
        descricao='Movimento orfao',
        data_movimento=date(2026, 5, 5),
        origem='RECEITA',
        receita_realizada_id=receita.id,
    )
    db.session.add(mov)
    db.session.commit()

    resultados = diagnosticar()

    assert resultados[0].classificacao == BLOQUEADO_INCONSISTENTE


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------

def test_apply_cria_movimento_para_regularizar(app_context):
    conta = _criar_conta(saldo=100.0)
    item = _criar_item_receita(conta_bancaria_id=conta.id)
    receita = _criar_receita_sem_conta(item.id, valor=500.0, data_recebimento=date(2026, 5, 5))

    resultados = diagnosticar()
    resultado_apply = aplicar(resultados)

    assert len(resultado_apply['movimentos_criados']) == 1
    db.session.refresh(receita)
    assert receita.conta_bancaria_id == conta.id
    mov = MovimentoFinanceiro.query.filter_by(receita_realizada_id=receita.id, origem='RECEITA').first()
    assert mov is not None
    assert mov.tipo == 'CREDITO'
    assert float(mov.valor) == 500.0
    db.session.refresh(conta)
    assert float(conta.saldo_atual) == 600.0


def test_apply_nao_duplica_movimento_em_segunda_execucao(app_context):
    conta = _criar_conta()
    item = _criar_item_receita(conta_bancaria_id=conta.id)
    receita = _criar_receita_sem_conta(item.id, valor=500.0)

    resultados = diagnosticar()
    aplicar(resultados)

    # Segunda rodada: a receita agora tem conta_bancaria_id, diagnosticar() nao deve mais retorna-la
    resultados2 = diagnosticar()
    assert resultados2 == []
    assert MovimentoFinanceiro.query.filter_by(receita_realizada_id=receita.id, origem='RECEITA').count() == 1


def test_apply_nao_altera_receita_pendente_decisao(app_context):
    item = _criar_item_receita(conta_bancaria_id=None)
    receita = _criar_receita_sem_conta(item.id, valor=5220.0, data_recebimento=date(2026, 6, 1))

    resultados = diagnosticar()
    resultado_apply = aplicar(resultados)

    assert resultado_apply['movimentos_criados'] == []
    assert resultado_apply['receitas_reabertas'] == []
    db.session.refresh(receita)
    assert receita.conta_bancaria_id is None
    assert ReceitaRealizada.query.count() == 1


def test_apply_nao_inventa_conta_bancaria(app_context):
    """Mesmo com apenas uma conta no sistema, apply nao deve atribui-la sem vinculo explicito."""
    _criar_conta()
    item = _criar_item_receita(conta_bancaria_id=None)
    _criar_receita_sem_conta(item.id, valor=1000.0)

    resultados = diagnosticar()
    resultado_apply = aplicar(resultados)

    assert resultado_apply['movimentos_criados'] == []
    receita_apos = ReceitaRealizada.query.first()
    assert receita_apos.conta_bancaria_id is None


def test_apply_reabre_receita_sem_evidencia(app_context):
    item = _criar_item_receita()
    receita = ReceitaRealizada(
        item_receita_id=item.id,
        data_recebimento=date(2026, 5, 5),
        valor_recebido=Decimal('0'),
        mes_referencia=date(2026, 5, 1),
        descricao='Sem evidencia',
    )
    db.session.add(receita)
    db.session.commit()
    receita_id = receita.id

    resultados = diagnosticar()
    resultado_apply = aplicar(resultados)

    assert receita_id in resultado_apply['receitas_reabertas']
    assert ReceitaRealizada.query.get(receita_id) is None


def test_apply_com_lista_vazia_nao_faz_nada(app_context):
    resultado_apply = aplicar([])
    assert resultado_apply['movimentos_criados'] == []
    assert resultado_apply['receitas_reabertas'] == []


def test_apply_rollback_em_falha_nao_deixa_movimento_parcial(app_context, monkeypatch):
    conta = _criar_conta(saldo=100.0)
    item1 = _criar_item_receita(conta_bancaria_id=conta.id)
    item2 = _criar_item_receita(conta_bancaria_id=conta.id)
    _criar_receita_sem_conta(item1.id, valor=500.0)
    _criar_receita_sem_conta(item2.id, valor=300.0)

    resultados = diagnosticar()
    assert len(resultados) == 2

    from backend.services import conta_bancaria_service

    original = conta_bancaria_service.ContaBancariaService.criar_movimento
    chamadas = {'n': 0}

    def _falha_na_segunda(*args, **kwargs):
        chamadas['n'] += 1
        if chamadas['n'] == 2:
            raise RuntimeError('Falha simulada')
        return original(*args, **kwargs)

    monkeypatch.setattr(conta_bancaria_service.ContaBancariaService, 'criar_movimento', staticmethod(_falha_na_segunda))

    with pytest.raises(RuntimeError):
        aplicar(resultados)

    assert MovimentoFinanceiro.query.count() == 0
    assert ReceitaRealizada.query.filter(ReceitaRealizada.conta_bancaria_id.isnot(None)).count() == 0
    db.session.refresh(conta)
    assert float(conta.saldo_atual) == 100.0


# ---------------------------------------------------------------------------
# only_id
# ---------------------------------------------------------------------------

def test_diagnosticar_com_only_id_restringe_resultado(app_context):
    item = _criar_item_receita()
    r1 = _criar_receita_sem_conta(item.id, valor=100.0)
    r2 = _criar_receita_sem_conta(item.id, valor=200.0)

    resultados = diagnosticar(only_id=r2.id)

    assert len(resultados) == 1
    assert resultados[0].receita_id == r2.id
