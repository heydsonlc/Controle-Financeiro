from datetime import date

import pytest

from backend.app import create_app
from backend.models import Categoria, ContratoConsorcio, ItemReceita, ReceitaRealizada, db
from backend.routes.consorcios import gerar_receita_contemplacao
from backend.routes.receitas import _backfill_receitas_contemplacao_consorcios
from backend.services.consorcio_receita_service import (
    NOME_FONTE_CONSORCIO,
    NOME_FONTE_CONSORCIO_MOJIBAKE,
    marcador_consorcio,
)
from backend.services.perfil_financeiro_service import PerfilFinanceiroService
from tests.conftest import autenticar_cliente_teste


@pytest.fixture()
def app():
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        PerfilFinanceiroService.obter_ou_criar_perfis_iniciais()
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return autenticar_cliente_teste(app.test_client(), app)


def _perfis(client):
    return client.get('/api/perfis-financeiros').get_json()['perfis']


def _perfil(client, nome):
    return next(perfil for perfil in _perfis(client) if perfil['nome'] == nome)


def _trocar_perfil(client, nome):
    perfil = _perfil(client, nome)
    response = client.post('/api/perfis-financeiros/ativo', json={'perfil_id': perfil['id']})
    assert response.status_code == 200
    return perfil


def _categoria():
    categoria = Categoria(nome='Consorcio Perfil Teste', ativo=True)
    db.session.add(categoria)
    db.session.commit()
    return categoria


def _payload(categoria_id, **overrides):
    payload = {
        'nome': 'Consorcio Perfil Teste',
        'valor_inicial': 500,
        'categoria_id': categoria_id,
        'numero_parcelas': 10,
        'mes_inicio': '2026-01-01',
        'tipo_reajuste': 'fixo',
        'valor_reajuste': 20,
        'mes_contemplacao': '2026-03-01',
        'observacoes': 'teste de perfil',
    }
    payload.update(overrides)
    return payload


def _criar_consorcio(perfil_id, **overrides):
    dados = {
        'perfil_financeiro_id': perfil_id,
        'nome': 'Consorcio Legado Perfil',
        'valor_inicial': 500,
        'tipo_reajuste': 'fixo',
        'valor_reajuste': 20,
        'numero_parcelas': 10,
        'mes_inicio': date(2026, 1, 1),
        'mes_contemplacao': date(2026, 3, 1),
        'valor_premio': 5400,
        'ativo': True,
    }
    dados.update(overrides)
    consorcio = ContratoConsorcio(**dados)
    db.session.add(consorcio)
    db.session.flush()
    return consorcio


def _criar_item(nome=NOME_FONTE_CONSORCIO, perfil_id=None):
    item = ItemReceita(
        perfil_financeiro_id=perfil_id,
        nome=nome,
        tipo='OUTROS',
        descricao='Fonte de teste',
        ativo=True,
        recorrente=False,
    )
    db.session.add(item)
    db.session.flush()
    return item


def _criar_receita(consorcio, item, perfil_id=None, valor=5400):
    receita = ReceitaRealizada(
        perfil_financeiro_id=perfil_id,
        item_receita_id=item.id if item else None,
        data_recebimento=consorcio.mes_contemplacao,
        valor_recebido=valor,
        mes_referencia=consorcio.mes_contemplacao.replace(day=1),
        descricao='Receita legado',
        observacoes=marcador_consorcio(consorcio.id),
    )
    db.session.add(receita)
    db.session.flush()
    return receita


def _receitas_do_consorcio(consorcio):
    return ReceitaRealizada.query.filter(
        ReceitaRealizada.observacoes.ilike(f'%{marcador_consorcio(consorcio.id)}%')
    ).order_by(ReceitaRealizada.id).all()


def test_novo_consorcio_recebe_perfil_financeiro_id(client):
    categoria = _categoria()
    pessoal = _perfil(client, 'Pessoal')

    response = client.post('/api/consorcios/', json=_payload(categoria.id))
    data = response.get_json()

    assert response.status_code == 201
    assert data['data']['perfil_financeiro_id'] == pessoal['id']
    assert ContratoConsorcio.query.one().perfil_financeiro_id == pessoal['id']


def test_receita_contemplacao_recebe_mesmo_perfil_do_consorcio(client):
    categoria = _categoria()
    empresa = _trocar_perfil(client, 'Empresa')

    response = client.post('/api/consorcios/', json=_payload(categoria.id))

    assert response.status_code == 201
    receita = ReceitaRealizada.query.one()
    consorcio = ContratoConsorcio.query.one()
    assert consorcio.perfil_financeiro_id == empresa['id']
    assert receita.perfil_financeiro_id == empresa['id']
    assert receita.item_receita.perfil_financeiro_id == empresa['id']


def test_fonte_contemplacao_e_criada_por_perfil(client):
    categoria = _categoria()

    client.post('/api/consorcios/', json=_payload(categoria.id, nome='Consorcio Pessoal Fonte'))
    empresa = _trocar_perfil(client, 'Empresa')
    client.post('/api/consorcios/', json=_payload(categoria.id, nome='Consorcio Empresa Fonte'))

    fontes = ItemReceita.query.filter_by(nome=NOME_FONTE_CONSORCIO, ativo=True).all()
    assert {fonte.perfil_financeiro_id for fonte in fontes} == {_perfil(client, 'Pessoal')['id'], empresa['id']}


def test_backfill_nao_cria_receita_duplicada(client):
    pessoal_id = _perfil(client, 'Pessoal')['id']
    consorcio = _criar_consorcio(pessoal_id)
    db.session.commit()

    _backfill_receitas_contemplacao_consorcios()
    _backfill_receitas_contemplacao_consorcios()

    receitas = _receitas_do_consorcio(consorcio)
    assert len(receitas) == 1
    assert receitas[0].perfil_financeiro_id == pessoal_id


def test_receita_global_null_e_migrada_para_perfil_do_consorcio(client):
    pessoal_id = _perfil(client, 'Pessoal')['id']
    consorcio = _criar_consorcio(pessoal_id)
    item_global = _criar_item(perfil_id=None)
    _criar_receita(consorcio, item_global, perfil_id=None)
    db.session.commit()

    _backfill_receitas_contemplacao_consorcios()

    receitas = _receitas_do_consorcio(consorcio)
    assert len(receitas) == 1
    assert receitas[0].perfil_financeiro_id == pessoal_id
    assert receitas[0].item_receita.nome == NOME_FONTE_CONSORCIO
    assert receitas[0].item_receita.perfil_financeiro_id == pessoal_id


def test_fonte_com_mojibake_e_corrigida(client):
    pessoal_id = _perfil(client, 'Pessoal')['id']
    item = _criar_item(nome=NOME_FONTE_CONSORCIO_MOJIBAKE, perfil_id=pessoal_id)
    consorcio = _criar_consorcio(pessoal_id)

    gerar_receita_contemplacao(consorcio)
    db.session.commit()

    assert ItemReceita.query.get(item.id).nome == NOME_FONTE_CONSORCIO


def test_receita_duplicada_por_consorcio_id_e_deduplicada(client):
    pessoal_id = _perfil(client, 'Pessoal')['id']
    consorcio = _criar_consorcio(pessoal_id)
    item_global = _criar_item(perfil_id=None)
    item_perfil = _criar_item(perfil_id=pessoal_id)
    _criar_receita(consorcio, item_global, perfil_id=None)
    _criar_receita(consorcio, item_perfil, perfil_id=pessoal_id)
    db.session.commit()

    _backfill_receitas_contemplacao_consorcios()

    receitas = _receitas_do_consorcio(consorcio)
    assert len(receitas) == 1
    assert receitas[0].perfil_financeiro_id == pessoal_id
    assert receitas[0].item_receita_id == item_perfil.id


def test_consorcio_inativo_nao_gera_nova_receita(client):
    pessoal_id = _perfil(client, 'Pessoal')['id']
    _criar_consorcio(pessoal_id, ativo=False)
    db.session.commit()

    _backfill_receitas_contemplacao_consorcios()

    assert ReceitaRealizada.query.count() == 0


def test_receita_historica_de_consorcio_inativo_e_preservada(client):
    pessoal_id = _perfil(client, 'Pessoal')['id']
    consorcio = _criar_consorcio(pessoal_id, ativo=False)
    item = _criar_item(perfil_id=pessoal_id)
    _criar_receita(consorcio, item, perfil_id=pessoal_id)
    db.session.commit()

    gerar_receita_contemplacao(consorcio)
    db.session.commit()

    receitas = _receitas_do_consorcio(consorcio)
    assert len(receitas) == 1
    assert receitas[0].perfil_financeiro_id == pessoal_id


def test_perfil_empresa_nao_enxerga_receita_de_consorcio_pessoal(client):
    categoria = _categoria()
    response = client.post('/api/consorcios/', json=_payload(categoria.id))
    assert response.status_code == 201

    _trocar_perfil(client, 'Empresa')
    receitas = client.get('/api/receitas/realizadas?ano_mes=2026-03').get_json()
    consorcios = client.get('/api/consorcios/').get_json()

    assert receitas['total'] == 0
    assert consorcios['data'] == []


def test_salvar_consorcio_duas_vezes_nao_duplica_receita(client):
    categoria = _categoria()
    criado = client.post('/api/consorcios/', json=_payload(categoria.id)).get_json()

    response = client.put(
        f"/api/consorcios/{criado['data']['id']}",
        json={'observacoes': 'salvo novamente'},
    )

    assert response.status_code == 200
    consorcio = ContratoConsorcio.query.one()
    assert len(_receitas_do_consorcio(consorcio)) == 1


def test_alterar_valor_do_premio_atualiza_receita_existente(client):
    categoria = _categoria()
    criado = client.post('/api/consorcios/', json=_payload(categoria.id)).get_json()

    response = client.put(
        f"/api/consorcios/{criado['data']['id']}",
        json={'valor_inicial': 600},
    )

    assert response.status_code == 200
    consorcio = ContratoConsorcio.query.one()
    receitas = _receitas_do_consorcio(consorcio)
    assert len(receitas) == 1
    assert float(receitas[0].valor_recebido) == 6400.0
