"""
Testes TX-ATOMIC-1: PerfilFinanceiroService.obter_ou_criar_perfis_iniciais() nao pode
finalizar (commit) a transacao de quem a chama.

Cenario original do bug: ContaBancariaService.criar_movimento() chama, por baixo,
PerfilFinanceiroService.obter_perfil_ativo_id(). Se os perfis financeiros padrao ainda
nao existiam, o service fazia um db.session.commit() proprio no meio da chamada — o que
finalizava prematuramente qualquer transacao maior em andamento (ex.: duas operacoes
que deveriam ser atomicas, uma delas envolvendo criar_movimento()). Um erro na segunda
operacao rodava rollback(), mas a primeira ja tinha sido commitada de verdade.

A correcao: o service usa apenas flush(); a persistencia da criacao idempotente dos
perfis fica a cargo do hook global `commit_pending_session` (backend/app.py,
teardown_request), que comita apenas ao fim da requisicao HTTP inteira.
"""
from decimal import Decimal

import pytest

from backend.app import create_app
from backend.models import (
    ContaBancaria,
    ItemReceita,
    MovimentoFinanceiro,
    PerfilFinanceiro,
    ReceitaRealizada,
    db,
)
from tests.conftest import autenticar_cliente_teste


@pytest.fixture()
def app():
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return autenticar_cliente_teste(app.test_client(), app)


def test_banco_novo_sem_perfis_ainda_nao_tem_nenhum(app):
    with app.app_context():
        assert PerfilFinanceiro.query.count() == 0


def test_get_perfis_financeiros_cria_perfis_padrao_persistidos(client, app):
    resp = client.get('/api/perfis-financeiros')
    assert resp.status_code == 200

    with app.app_context():
        nomes = {p.nome for p in PerfilFinanceiro.query.all()}
        assert {'Pessoal', 'Empresa'}.issubset(nomes)


def test_criar_movimento_em_banco_sem_perfis_nao_finaliza_transacao_prematuramente(app):
    """
    Reproduz o cenario original do bug com precisao: uma mutacao de atributo fica
    PENDENTE (nao commitada) na sessao, e so DEPOIS disso o codigo chama
    ContaBancariaService.criar_movimento() — que aciona, por baixo,
    PerfilFinanceiroService.obter_perfil_ativo_id(). Antes da correcao, como o banco
    ainda nao tinha perfis, esse acionamento fazia um db.session.commit() escondido,
    que finalizava a transacao E JUNTO commitava a mutacao pendente anterior. Uma falha
    logo em seguida disparava rollback(), mas so revertia o que ainda estava pendente
    apos aquele commit acidental — ou seja, nada; a mutacao ja tinha sido persistida de
    verdade. Depois da correcao (service so usa flush()), o rollback reverte tudo.
    """
    with app.app_context():
        from backend.services.conta_bancaria_service import ContaBancariaService

        assert PerfilFinanceiro.query.count() == 0

        conta = ContaBancaria(
            nome='Conta', instituicao='Banco', tipo='Corrente',
            saldo_inicial=Decimal('100'), saldo_atual=Decimal('100'), status='ATIVO',
        )
        item = ItemReceita(nome='Fonte', tipo='OUTROS', ativo=True, recorrente=False)
        db.session.add_all([conta, item])
        db.session.commit()
        conta_id, item_id = conta.id, item.id

        receita = ReceitaRealizada(
            item_receita_id=item_id, data_recebimento=__import__('datetime').date(2026, 5, 5),
            valor_recebido=Decimal('500'), mes_referencia=__import__('datetime').date(2026, 5, 1),
            descricao='Receita historica',
        )
        db.session.add(receita)
        db.session.commit()
        receita_id = receita.id

        try:
            receita = ReceitaRealizada.query.get(receita_id)
            receita.conta_bancaria_id = conta_id  # mutacao PENDENTE, ainda sem commit

            ContaBancariaService.criar_movimento(
                conta_id, tipo='CREDITO', valor=Decimal('500'),
                descricao='primeiro', data_movimento=__import__('datetime').date(2026, 5, 5),
                origem='RECEITA', receita_realizada_id=receita.id,
            )
            raise RuntimeError('Falha simulada apos criar o movimento')
        except RuntimeError:
            db.session.rollback()

        assert MovimentoFinanceiro.query.count() == 0
        db.session.refresh(conta)
        assert conta.saldo_atual == Decimal('100.00')
        receita_fresh = ReceitaRealizada.query.get(receita_id)
        assert receita_fresh.conta_bancaria_id is None


def test_hook_nao_interfere_em_rollback_de_erro_de_negocio(client, app):
    """POST com payload invalido (sem conta bancaria) deve retornar 400 e nao persistir nada,
    mesmo com o hook de commit automatico registrado."""
    with app.app_context():
        item = ItemReceita(nome='Fonte', tipo='OUTROS', ativo=True, recorrente=False)
        db.session.add(item)
        db.session.commit()
        item_id = item.id

    resp = client.post('/api/receitas/realizadas', json={
        'item_receita_id': item_id,
        'data_recebimento': '2026-05-05',
        'valor_recebido': 100.0,
    })
    assert resp.status_code == 400

    with app.app_context():
        assert ReceitaRealizada.query.count() == 0


def test_hook_persiste_escrita_normal_de_rota(client, app):
    with app.app_context():
        conta = ContaBancaria(
            nome='Conta', instituicao='Banco', tipo='Corrente',
            saldo_inicial=Decimal('0'), saldo_atual=Decimal('0'), status='ATIVO',
        )
        item = ItemReceita(nome='Fonte', tipo='OUTROS', ativo=True, recorrente=False)
        db.session.add_all([conta, item])
        db.session.commit()
        conta_id, item_id = conta.id, item.id

    resp = client.post('/api/receitas/realizadas', json={
        'item_receita_id': item_id,
        'data_recebimento': '2026-05-05',
        'valor_recebido': 500.0,
        'conta_bancaria_id': conta_id,
    })
    assert resp.status_code == 201

    with app.app_context():
        assert ReceitaRealizada.query.count() == 1
        assert MovimentoFinanceiro.query.count() == 1
