from datetime import date
from pathlib import Path

import pytest
from flask import Flask, render_template

from backend.models import (
    ContaBancaria,
    ItemReceita,
    MovimentoFinanceiro,
    ReceitaOrcamento,
    ReceitaRealizada,
    db,
)
from backend.routes.receitas import receitas_bp


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
    app.register_blueprint(receitas_bp, url_prefix='/api/receitas')

    @app.route('/receitas')
    def receitas_page():
        return render_template(
            'receitas.html',
            active_page='receitas',
            page_title='Gerenciamento de Receitas',
        )

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app_context):
    return app_context.test_client()


def _criar_conta(nome='Banco Demo', saldo=100.0):
    conta = ContaBancaria(
        nome=nome,
        instituicao='Banco do Brasil',
        tipo='Conta Corrente',
        agencia='1234',
        numero_conta='98765',
        digito_conta='4',
        saldo_inicial=saldo,
        saldo_atual=saldo,
        cor_display='#2563eb',
        status='ATIVO',
    )
    db.session.add(conta)
    db.session.commit()
    return conta


def _payload_fonte(nome='Fonte UX', valor=3000.0, conta_id=None):
    return {
        'nome': nome,
        'tipo': 'SALARIO_FIXO',
        'descricao': 'Receita de teste UX',
        'valor_base_mensal': valor,
        'dia_previsto_pagamento': 5,
        'conta_bancaria_id': conta_id,
        'recorrente': True,
        'ativo': True,
    }


def _criar_fonte(client, nome='Fonte UX', valor=3000.0, conta_id=None):
    response = client.post('/api/receitas/itens', json=_payload_fonte(nome, valor, conta_id))
    assert response.status_code == 201
    body = response.get_json()
    assert body['success'] is True
    return body['data']


def test_rota_principal_renderiza_layout_ux(client):
    response = client.get('/receitas')

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Gerenciamento de Receitas' in html
    assert 'Acompanhe, gerencie e projete todas as suas receitas em um só lugar.' in html
    assert 'receitas-busca' in html
    assert 'Previsto no mês' in html
    assert 'Receitas do mês' in html
    assert 'Fontes de receita' in html
    assert 'Próximos recebimentos' in html
    assert 'Nova Fonte de Receita' in html
    assert 'Pré-visualização' in html


def test_api_listagem_banco_vazio_nao_quebra(client):
    endpoints = [
        '/api/receitas/itens',
        '/api/receitas/orcamento?ano=2026',
        '/api/receitas/realizadas?ano_mes=2026-05-01',
    ]

    for endpoint in endpoints:
        response = client.get(endpoint)
        assert response.status_code == 200
        body = response.get_json()
        assert body['success'] is True
        assert body['data'] == []


def test_cadastro_aceita_payload_minimo_valido(client):
    fonte = _criar_fonte(client, valor=2500.75)

    assert fonte['nome'] == 'Fonte UX'
    assert fonte['tipo'] == 'SALARIO_FIXO'
    assert fonte['valor_base_mensal'] == 2500.75
    assert fonte['dia_previsto_pagamento'] == 5
    assert fonte['ativo'] is True
    assert fonte['recorrente'] is True


def test_edicao_preserva_campos(client):
    fonte = _criar_fonte(client)

    response = client.put(f'/api/receitas/itens/{fonte["id"]}', json={
        'nome': 'Fonte UX Editada',
        'tipo': 'GRATIFICACAO',
        'descricao': 'Descrição editada',
        'valor_base_mensal': 4200.0,
        'dia_previsto_pagamento': 10,
        'recorrente': False,
        'ativo': True,
    })

    assert response.status_code == 200
    body = response.get_json()
    assert body['success'] is True
    editada = body['data']
    assert editada['nome'] == 'Fonte UX Editada'
    assert editada['tipo'] == 'GRATIFICACAO'
    assert editada['valor_base_mensal'] == 4200.0
    assert editada['dia_previsto_pagamento'] == 10
    assert editada['recorrente'] is False


def test_inativacao_muda_status(client):
    fonte = _criar_fonte(client)

    response = client.delete(f'/api/receitas/itens/{fonte["id"]}')

    assert response.status_code == 200
    body = response.get_json()
    assert body['success'] is True
    assert ItemReceita.query.get(fonte['id']).ativo is False


def test_cards_resumo_calculam_previsto_realizado_diferenca_confiabilidade(client):
    fonte = _criar_fonte(client, valor=3000.0)
    client.post('/api/receitas/realizadas', json={
        'item_receita_id': fonte['id'],
        'data_recebimento': '2026-05-05',
        'valor_recebido': 1500.0,
        'competencia': '2026-05-01',
        'descricao': 'Receita parcial',
    })

    response = client.get('/api/receitas/resumo-mensal?ano=2026')

    assert response.status_code == 200
    body = response.get_json()
    assert body['success'] is True
    maio = body['data']['5'] if '5' in body['data'] else body['data'][5]
    assert maio['total_previsto'] == 3000.0
    assert maio['total_realizado'] == 1500.0
    confiabilidade = (maio['total_realizado'] / maio['total_previsto']) * 100
    assert confiabilidade == 50.0


def test_receita_recorrente_mantem_geracao_atual(client):
    fonte = _criar_fonte(client, nome='Fonte Recorrente', valor=1200.0)

    orcamentos = ReceitaOrcamento.query.filter_by(item_receita_id=fonte['id']).all()

    assert len(orcamentos) >= 1
    assert all(float(orcamento.valor_esperado) == 1200.0 for orcamento in orcamentos)


def test_receita_nao_recorrente_nao_gera_orcamento_automatico(client):
    response = client.post('/api/receitas/itens', json={
        'nome': 'Fonte Pontual UX',
        'tipo': 'OUTROS',
        'descricao': 'Receita sem recorrência',
        'valor_base_mensal': 900.0,
        'dia_previsto_pagamento': None,
        'recorrente': False,
        'ativo': True,
    })

    assert response.status_code == 201
    body = response.get_json()
    assert body['success'] is True
    assert body['data']['recorrente'] is False

    orcamentos = ReceitaOrcamento.query.filter_by(item_receita_id=body['data']['id']).all()
    assert orcamentos == []


def test_consolidacao_em_conta_bancaria_preserva_saldo(client):
    conta = _criar_conta(saldo=100.0)
    fonte = _criar_fonte(client, conta_id=conta.id, valor=800.0)

    response = client.post('/api/receitas/realizadas', json={
        'item_receita_id': fonte['id'],
        'data_recebimento': '2026-05-05',
        'valor_recebido': 800.0,
        'competencia': '2026-05-01',
        'conta_bancaria_id': conta.id,
        'descricao': 'Receita consolidada',
    })

    assert response.status_code == 201
    body = response.get_json()
    assert body['success'] is True

    movimento = MovimentoFinanceiro.query.filter_by(
        receita_realizada_id=body['data']['id'],
        origem='RECEITA',
    ).first()
    assert movimento is not None
    assert movimento.tipo == 'CREDITO'
    assert float(movimento.valor) == 800.0
    assert float(ContaBancaria.query.get(conta.id).saldo_atual) == 900.0


def test_template_contem_campos_essenciais_modal(client):
    html = client.get('/receitas').get_data(as_text=True)

    campos = [
        'fonte-nome',
        'fonte-tipo',
        'fonte-descricao',
        'fonte-valor-base',
        'fonte-recorrente',
        'fonte-dia-pagamento',
        'fonte-conta-bancaria',
        'fonte-observacoes',
        'fonte-ativo',
    ]
    for campo in campos:
        assert campo in html

    assert 'preview-fonte-nome' in html
    assert 'preview-fonte-valor' in html
    assert 'Cancelar' in html
    assert 'Salvar' in html


def test_tipo_invalido_continua_rejeitado(client):
    response = client.post('/api/receitas/itens', json={
        'nome': 'Fonte inválida',
        'tipo': 'TIPO_NOVO',
    })

    assert response.status_code == 400
    body = response.get_json()
    assert body['success'] is False
    assert 'Tipo' in body['error']


def test_listagem_realizadas_retorna_receita_do_periodo(client):
    fonte = _criar_fonte(client)
    receita = ReceitaRealizada(
        item_receita_id=fonte['id'],
        data_recebimento=date(2026, 5, 5),
        valor_recebido=500.0,
        mes_referencia=date(2026, 5, 1),
        descricao='Receita realizada',
    )
    db.session.add(receita)
    db.session.commit()

    response = client.get('/api/receitas/realizadas?ano_mes=2026-05-01')

    assert response.status_code == 200
    body = response.get_json()
    assert body['success'] is True
    assert len(body['data']) == 1
    assert body['data'][0]['valor_recebido'] == 500.0
