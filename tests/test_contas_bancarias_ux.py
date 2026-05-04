from pathlib import Path

import pytest
from flask import Flask, render_template

from backend.models import ContaBancaria, db
from backend.routes.contas_bancarias import contas_bancarias_bp


@pytest.fixture()
def app_context():
    base_dir = Path(__file__).resolve().parents[1]
    app = Flask(
        __name__,
        template_folder=str(base_dir / 'frontend' / 'templates'),
        static_folder=str(base_dir / 'frontend' / 'static'),
    )
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    app.register_blueprint(contas_bancarias_bp, url_prefix='/api/contas')

    @app.route('/contas-bancarias')
    def contas_bancarias_page():
        return render_template(
            'contas_bancarias.html',
            active_page='contas_bancarias',
            page_title='Contas Bancárias',
        )

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app_context):
    return app_context.test_client()


def _payload_conta(nome='Conta UX', saldo=1000.0, instituicao='Banco Demo', cor='#3b82f6'):
    return {
        'nome': nome,
        'instituicao': instituicao,
        'tipo': 'Conta Corrente',
        'agencia': '1234',
        'numero_conta': '56789',
        'digito_conta': '0',
        'saldo_inicial': saldo,
        'cor_display': cor,
    }


def _criar_conta(client, nome='Conta UX', saldo=1000.0, instituicao='Banco Demo', cor='#3b82f6'):
    response = client.post('/api/contas', json=_payload_conta(nome, saldo, instituicao, cor))
    assert response.status_code == 201
    body = response.get_json()
    assert body['success'] is True
    return body['data']


def test_rota_principal_renderiza_layout_ux(client):
    response = client.get('/contas-bancarias')

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Contas Bancárias' in html
    assert 'module-actionbar' in html
    assert 'Saldo total em contas' in html
    assert 'Contas bancárias' in html
    assert 'Nova Conta Bancária' in html
    assert 'Prévia da conta' in html
    assert 'contas-busca' in html


def test_api_listagem_banco_vazio_nao_quebra(client):
    response = client.get('/api/contas?status=ATIVO')

    assert response.status_code == 200
    body = response.get_json()
    assert body['success'] is True
    assert body['data'] == []
    assert body['total'] == 0


def test_cadastro_aceita_payload_minimo_valido(client):
    conta = _criar_conta(client, saldo=2500.75, cor='#14b8a6')

    assert conta['nome'] == 'Conta UX'
    assert conta['instituicao'] == 'Banco Demo'
    assert conta['tipo'] == 'Conta Corrente'
    assert conta['saldo_inicial'] == 2500.75
    assert conta['saldo_atual'] == 2500.75
    assert conta['cor_display'] == '#14b8a6'
    assert conta['status'] == 'ATIVO'


def test_edicao_preserva_campos_sem_movimentos(client):
    conta = _criar_conta(client)

    response = client.put(f'/api/contas/{conta["id"]}', json={
        'nome': 'Conta UX Editada',
        'instituicao': 'CAIXA',
        'tipo': 'Conta Poupança',
        'agencia': '0001',
        'numero_conta': '99999',
        'digito_conta': '1',
        'saldo_inicial': 1500.0,
        'cor_display': '#ef4444',
    })

    assert response.status_code == 200
    body = response.get_json()
    assert body['success'] is True
    editada = body['data']
    assert editada['nome'] == 'Conta UX Editada'
    assert editada['tipo'] == 'Conta Poupança'
    assert editada['saldo_inicial'] == 1500.0
    assert editada['saldo_atual'] == 1500.0
    assert editada['cor_display'] == '#ef4444'


def test_inativacao_muda_status_sem_apagar(client):
    conta = _criar_conta(client)

    response = client.delete(f'/api/contas/{conta["id"]}')

    assert response.status_code == 200
    body = response.get_json()
    assert body['success'] is True
    assert ContaBancaria.query.get(conta['id']).status == 'INATIVO'

    inativas = client.get('/api/contas?status=INATIVO').get_json()['data']
    assert len(inativas) == 1
    assert inativas[0]['id'] == conta['id']


def test_cards_resumo_podem_calcular_total_ativas_maior_saldo(client):
    conta_ativa = _criar_conta(client, nome='Conta Principal', saldo=5000.0, cor='#22c55e')
    conta_inativa = _criar_conta(client, nome='Conta Antiga', saldo=1200.0, cor='#6b7280')
    client.delete(f'/api/contas/{conta_inativa["id"]}')

    contas_ativas = client.get('/api/contas?status=ATIVO').get_json()['data']
    saldo_total = sum(conta['saldo_atual'] for conta in contas_ativas)
    maior_conta = max(contas_ativas, key=lambda conta: conta['saldo_atual'])

    assert len(contas_ativas) == 1
    assert contas_ativas[0]['id'] == conta_ativa['id']
    assert saldo_total == 5000.0
    assert maior_conta['nome'] == 'Conta Principal'


def test_transferencia_existente_preserva_regra_de_saldo(client):
    origem = _criar_conta(client, nome='Origem', saldo=1000.0)
    destino = _criar_conta(client, nome='Destino', saldo=200.0)

    response = client.post('/api/contas/transferir', json={
        'conta_origem_id': origem['id'],
        'conta_destino_id': destino['id'],
        'valor': 150.0,
        'data_movimento': '2026-05-03',
        'descricao': 'Transferência teste UX',
    })

    assert response.status_code == 201
    body = response.get_json()
    assert body['success'] is True

    origem_atualizada = client.get(f'/api/contas/{origem["id"]}').get_json()['data']
    destino_atualizado = client.get(f'/api/contas/{destino["id"]}').get_json()['data']
    assert origem_atualizada['saldo_atual'] == 850.0
    assert destino_atualizado['saldo_atual'] == 350.0


def test_extrato_retorna_movimentos_com_saldo_apos(client):
    origem = _criar_conta(client, nome='Origem', saldo=1000.0)
    destino = _criar_conta(client, nome='Destino', saldo=200.0)
    client.post('/api/contas/transferir', json={
        'conta_origem_id': origem['id'],
        'conta_destino_id': destino['id'],
        'valor': 150.0,
        'data_movimento': '2026-05-03',
        'descricao': 'Transferência teste UX',
    })

    response = client.get(f'/api/contas/{origem["id"]}/movimentos?incluir_saldo=1')

    assert response.status_code == 200
    body = response.get_json()
    assert body['success'] is True
    assert len(body['data']) == 1
    assert body['data'][0]['tipo'] == 'DEBITO'
    assert body['data'][0]['saldo_apos_movimento'] == 850.0


def test_template_contem_campos_modal_e_acoes_essenciais(client):
    response = client.get('/contas-bancarias')
    html = response.get_data(as_text=True)

    campos = [
        'conta-nome',
        'conta-instituicao',
        'conta-tipo',
        'conta-agencia',
        'conta-numero',
        'conta-digito',
        'conta-saldo-inicial',
        'conta-cor-paleta',
    ]
    for campo in campos:
        assert campo in html

    assert 'Visualizar' in html
    assert 'Editar' in html
    assert 'Transferir' in html
    assert 'Extrato' in html
    assert 'Inativar' in html


def test_nao_altera_saldo_inicial_com_movimentos(client):
    conta = _criar_conta(client, saldo=1000.0)
    ajuste = client.post(f'/api/contas/{conta["id"]}/ajuste-saldo', json={
        'valor_final_desejado': 1100.0,
        'descricao': 'Ajuste teste UX',
        'data_movimento': '2026-05-03',
    })
    assert ajuste.status_code == 201

    response = client.put(f'/api/contas/{conta["id"]}', json={'saldo_inicial': 500.0})

    assert response.status_code == 400
    body = response.get_json()
    assert body['success'] is False
    assert 'saldo inicial' in body['error'].lower()
