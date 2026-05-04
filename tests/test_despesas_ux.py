"""
DESPESAS-UX-1: testes de integracao para a tela de Despesas reformulada.
Verifica estrutura HTML, endpoints da API e integridade das regras de negocio.
"""
from pathlib import Path
from datetime import date, timedelta

import pytest
from flask import Flask, render_template

from backend.models import db, ItemDespesa, Categoria, Conta
from backend.routes.despesas import despesas_bp


# ---------------------------------------------------------------------------
# Fixture central: app Flask in-memory
# ---------------------------------------------------------------------------

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
    app.register_blueprint(despesas_bp, url_prefix='/api/despesas')

    @app.route('/despesas')
    def despesas_page():
        return render_template(
            'despesas.html',
            active_page='despesas',
            page_title='Gerenciamento de Despesas',
        )

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app_context):
    return app_context.test_client()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _criar_categoria(nome='Moradia', cor='#007aff'):
    cat = Categoria(nome=nome, cor=cor, ativo=True)
    db.session.add(cat)
    db.session.flush()
    return cat


def _criar_item_despesa(nome='Aluguel', valor=1500.0, recorrente=False, categoria=None, tipo='Simples'):
    item = ItemDespesa(
        nome=nome,
        valor=valor,
        recorrente=recorrente,
        tipo=tipo,
        ativo=True,
        categoria_id=categoria.id if categoria else None,
    )
    db.session.add(item)
    db.session.flush()
    return item


def _criar_conta(item, vencimento=None, status='Pendente'):
    hoje = date.today()
    venc = vencimento or hoje
    conta = Conta(
        item_despesa_id=item.id,
        mes_referencia=venc.replace(day=1),
        descricao=item.nome,
        valor=item.valor,
        data_vencimento=venc,
        status_pagamento=status,
        is_fatura_cartao=False,
    )
    if status == 'Pago':
        conta.data_pagamento = hoje
    db.session.add(conta)
    db.session.commit()
    return conta


# ---------------------------------------------------------------------------
# TESTE 1: Rota principal renderiza com status 200
# ---------------------------------------------------------------------------

def test_rota_principal_renderiza_200(client):
    resp = client.get('/despesas')
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# TESTE 2: Banco vazio nao causa crash
# ---------------------------------------------------------------------------

def test_banco_vazio_nao_crasha(client):
    resp = client.get('/api/despesas/')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    assert body['data'] == []


# ---------------------------------------------------------------------------
# TESTE 3: Filtro mes_referencia e aceito sem erro
# ---------------------------------------------------------------------------

def test_filtro_mes_referencia_aceito(client, app_context):
    resp = client.get('/api/despesas/?mes_referencia=2026-05')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True


# ---------------------------------------------------------------------------
# TESTE 4: Cards de resumo — totais presentes no campo sidebar
# ---------------------------------------------------------------------------

def test_sidebar_totais_presentes(client, app_context):
    with app_context.app_context():
        cat = _criar_categoria('Moradia')
        item = _criar_item_despesa('Aluguel', 1500.0, categoria=cat)
        _criar_conta(item, status='Pendente')

    resp = client.get('/api/despesas/')
    body = resp.get_json()
    assert body['success'] is True
    sidebar = body.get('sidebar')
    assert sidebar is not None
    assert 'total_mes' in sidebar
    assert 'total_pendentes' in sidebar
    assert 'total_pagas' in sidebar
    assert sidebar['total_mes'] > 0
    assert sidebar['total_pendentes'] > 0


# ---------------------------------------------------------------------------
# TESTE 5: Campos de vencendo_7d, recorrentes e cartoes existem no sidebar
# ---------------------------------------------------------------------------

def test_sidebar_novos_cards_sem_crash(client, app_context):
    resp = client.get('/api/despesas/')
    body = resp.get_json()
    sidebar = body.get('sidebar', {})
    assert 'vencendo_7d_count' in sidebar
    assert 'vencendo_7d_valor' in sidebar
    assert 'recorrentes_count' in sidebar
    assert 'recorrentes_valor' in sidebar
    assert 'cartoes_count' in sidebar
    assert 'cartoes_valor' in sidebar


# ---------------------------------------------------------------------------
# TESTE 6: Lista preserva agrupamentos no template HTML
# ---------------------------------------------------------------------------

def test_template_contem_agrupamentos(client):
    resp = client.get('/despesas')
    html = resp.get_data(as_text=True)
    # A lista e renderizada pelo JS, mas os elementos de marcacao devem existir
    assert 'despesas-lista' in html
    assert 'despesas-page-layout' in html
    assert 'despesas-main' in html
    assert 'despesas-sidebar' in html


# ---------------------------------------------------------------------------
# TESTE 7: Template contem colunas essenciais (via IDs e textos esperados)
# ---------------------------------------------------------------------------

def test_template_contem_colunas_essenciais(client):
    resp = client.get('/despesas')
    html = resp.get_data(as_text=True)
    # Cards de resumo
    assert 'total-geral' in html
    assert 'total-pendentes' in html
    assert 'total-pagas' in html
    # Novos cards
    assert 'total-vencendo-7d' in html
    assert 'total-recorrentes' in html
    assert 'total-cartoes' in html


# ---------------------------------------------------------------------------
# TESTE 8: Sidebar renderiza sem dados (banco vazio)
# ---------------------------------------------------------------------------

def test_sidebar_renderiza_sem_dados(client):
    resp = client.get('/despesas')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'sidebar-composicao' in html
    assert 'sidebar-por-categoria' in html
    assert 'sidebar-indicadores' not in html
    assert 'sidebar-proximos' in html


# ---------------------------------------------------------------------------
# TESTE 9: Botoes de acao essenciais presentes no template
# ---------------------------------------------------------------------------

def test_template_contem_botoes_acao(client):
    resp = client.get('/despesas')
    html = resp.get_data(as_text=True)
    assert 'abrirModal' in html
    assert 'modal-despesa' in html
    assert 'modal-pagar' in html
    assert 'confirmarPagamento' in html
    assert 'form-pagar' in html


# ---------------------------------------------------------------------------
# TESTE 10: Nenhuma logica de pagamento alterada (verificacao estrutural)
# ---------------------------------------------------------------------------

def test_logica_pagamento_nao_alterada(client, app_context):
    """
    Cria uma conta pendente e paga via /api/despesas/<id>/pagar
    Verifica que o endpoint ainda exige conta_bancaria_id (logica preservada).
    """
    with app_context.app_context():
        cat = _criar_categoria('Alimentacao')
        item = _criar_item_despesa('Supermercado', 300.0, categoria=cat)
        conta = _criar_conta(item, status='Pendente')
        conta_id = conta.id

    # Tentar pagar sem conta_bancaria_id deve retornar erro 400
    resp = client.post(
        f'/api/despesas/{conta_id}/pagar',
        json={'data_pagamento': date.today().isoformat()},
    )
    body = resp.get_json()
    # Regra: conta_bancaria_id e obrigatoria — logica de pagamento preservada
    assert resp.status_code == 400
    assert body['success'] is False


# ---------------------------------------------------------------------------
# TESTE 11: composicao_categoria no sidebar e uma lista
# ---------------------------------------------------------------------------

def test_sidebar_composicao_categoria_e_lista(client, app_context):
    with app_context.app_context():
        cat = _criar_categoria('Transporte', '#34c759')
        item = _criar_item_despesa('Combustivel', 400.0, categoria=cat)
        _criar_conta(item)

    resp = client.get('/api/despesas/')
    body = resp.get_json()
    sidebar = body.get('sidebar', {})
    assert 'composicao_categoria' in sidebar
    assert isinstance(sidebar['composicao_categoria'], list)


# ---------------------------------------------------------------------------
# TESTE 12: proximos_vencimentos no sidebar e uma lista
# ---------------------------------------------------------------------------

def test_sidebar_proximos_vencimentos_e_lista(client, app_context):
    with app_context.app_context():
        cat = _criar_categoria('Saude')
        item = _criar_item_despesa('Plano de Saude', 800.0, categoria=cat)
        venc = date.today() + timedelta(days=3)
        _criar_conta(item, vencimento=venc, status='Pendente')

    resp = client.get('/api/despesas/')
    body = resp.get_json()
    sidebar = body.get('sidebar', {})
    assert 'proximos_vencimentos' in sidebar
    assert isinstance(sidebar['proximos_vencimentos'], list)
    # Deve aparecer nos proximos vencimentos
    assert len(sidebar['proximos_vencimentos']) >= 1
