"""
VEIC-2B: Testes de integração — transporte por app como recorrência,
assinatura de mobilidade, supressão de DespesaPrevista redundante.

Usa SQLite in-memory (mesmo padrão VEIC-2).
"""
import json
from datetime import date
from decimal import Decimal

import pytest
from flask import Flask

from backend.models import (
    db,
    Categoria,
    CategoriaCartao,
    CategoriaCartaoDespesa,
    CartaoCategoriaLimite,
    ConfigAgregador,
    DespesaPrevista,
    ItemDespesa,
    MobilidadeAssinatura,
    MobilidadeCenarioAtivo,
    Veiculo,
)
from backend.services.mobilidade_service import (
    ativar_modalidade,
    criar_assinatura,
    criar_recorrencia_assinatura,
    criar_recorrencia_transporte_app,
    listar_assinaturas,
    obter_modalidade_ativa,
    suprimir_despesas_previstas_por_recorrencia,
)
from backend.routes.veiculos import veiculos_bp


@pytest.fixture()
def app_context():
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    app.register_blueprint(veiculos_bp, url_prefix='/api/veiculos')

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app_context):
    return app_context.test_client()


# ---------------------------------------------------------------------------
# Fixtures helpers
# ---------------------------------------------------------------------------

def _categoria():
    cat = Categoria(nome='Mobilidade', cor='#1e40af', ativo=True)
    db.session.add(cat)
    db.session.flush()
    return cat


def _assinatura(cat_id=None, nome='Carro por Assinatura', valor=1200.0):
    ass = MobilidadeAssinatura(
        nome=nome,
        valor_mensal=Decimal(str(valor)),
        categoria_id=cat_id,
        status='ATIVO',
    )
    db.session.add(ass)
    db.session.flush()
    return ass


def _get_or_create_cat():
    cat = Categoria.query.filter_by(nome='Mobilidade').first()
    if not cat:
        cat = Categoria(nome='Mobilidade', cor='#1e40af', ativo=True)
        db.session.add(cat)
        db.session.flush()
    return cat


def _despesa_prevista_app(origem_id, data_prevista, valor=300.0, status='PREVISTA', tipo_evento='TRANSPORTE_APP'):
    cat = _get_or_create_cat()
    md = json.dumps({'tipo_evento': tipo_evento, 'caminho': {'nome': 'Casa-Trabalho'}})
    d = DespesaPrevista(
        origem_tipo='TRANSPORTE_APP',
        origem_id=origem_id,
        categoria_id=cat.id,
        data_prevista=data_prevista,
        data_original_prevista=data_prevista,
        data_atual_prevista=data_prevista,
        valor_previsto=Decimal(str(valor)),
        status=status,
        metadata_json=md,
    )
    db.session.add(d)
    db.session.flush()
    return d


# ---------------------------------------------------------------------------
# CRUD de MobilidadeAssinatura
# ---------------------------------------------------------------------------

def test_criar_assinatura_valida(app_context):
    cat = _categoria()
    ass = criar_assinatura({'nome': 'Carro Kwid', 'valor_mensal': '899.90', 'categoria_id': cat.id})
    db.session.commit()
    assert ass.id is not None
    assert ass.status == 'ATIVO'
    assert float(ass.valor_mensal) == pytest.approx(899.90)


def test_criar_assinatura_sem_nome_falha(app_context):
    with pytest.raises(ValueError, match='nome'):
        criar_assinatura({'nome': '', 'valor_mensal': '500'})


def test_criar_assinatura_valor_zero_falha(app_context):
    with pytest.raises(ValueError, match='valor_mensal'):
        criar_assinatura({'nome': 'X', 'valor_mensal': '0'})


def test_listar_assinaturas_apenas_ativas(app_context):
    _assinatura(nome='A1')
    ass2 = _assinatura(nome='A2')
    ass2.status = 'INATIVO'
    db.session.commit()
    ativas = listar_assinaturas(apenas_ativas=True)
    nomes = [a['nome'] for a in ativas]
    assert 'A1' in nomes
    assert 'A2' not in nomes


# ---------------------------------------------------------------------------
# criar_recorrencia_transporte_app
# ---------------------------------------------------------------------------

def test_criar_recorrencia_app_nova(app_context):
    cat = _categoria()
    rec, avisos = criar_recorrencia_transporte_app(
        caminho_id=1,
        nome='Casa-Trabalho',
        valor_mensal=Decimal('320.00'),
        meio_pagamento='pix',
        cartao_id=None,
        categoria_id=cat.id,
        categoria_cartao_id=None,
        data_inicio=date(2026, 5, 1),
    )
    db.session.flush()
    assert rec.origem_tipo == 'TRANSPORTE_APP'
    assert rec.origem_id == 1
    assert rec.origem_contexto == 'transporte_app_mensal'
    assert rec.recorrente is True
    assert float(rec.valor) == pytest.approx(320.0)
    assert rec.nome == 'Transporte por app - Casa-Trabalho'


def test_criar_recorrencia_app_nao_duplica(app_context):
    cat = _categoria()
    criar_recorrencia_transporte_app(
        caminho_id=1, nome='Rota', valor_mensal=Decimal('200'), meio_pagamento='pix',
        cartao_id=None, categoria_id=cat.id, categoria_cartao_id=None,
    )
    db.session.flush()
    rec2, _ = criar_recorrencia_transporte_app(
        caminho_id=1, nome='Rota', valor_mensal=Decimal('250'), meio_pagamento='debito',
        cartao_id=None, categoria_id=cat.id, categoria_cartao_id=None,
    )
    db.session.flush()
    total = ItemDespesa.query.filter_by(origem_tipo='TRANSPORTE_APP', origem_id=1, recorrente=True, ativo=True).count()
    assert total == 1
    assert float(rec2.valor) == pytest.approx(250.0)


# ---------------------------------------------------------------------------
# criar_recorrencia_assinatura
# ---------------------------------------------------------------------------

def test_criar_recorrencia_assinatura(app_context):
    cat = _categoria()
    ass = _assinatura(cat_id=cat.id, valor=1100.0)
    rec, avisos = criar_recorrencia_assinatura(
        assinatura=ass,
        meio_pagamento='debito',
        cartao_id=None,
        categoria_cartao_id=None,
        data_inicio=date(2026, 5, 1),
    )
    db.session.flush()
    assert rec.origem_tipo == 'ASSINATURA'
    assert rec.origem_id == ass.id
    assert rec.origem_contexto == 'assinatura_mensal'
    assert float(rec.valor) == pytest.approx(1100.0)
    assert 'Assinatura - Carro por Assinatura' in rec.nome


def test_criar_recorrencia_assinatura_sem_valor_falha(app_context):
    ass = MobilidadeAssinatura(nome='X', valor_mensal=Decimal('0'), status='ATIVO')
    db.session.add(ass)
    db.session.flush()
    with pytest.raises(ValueError, match='valor_mensal'):
        criar_recorrencia_assinatura(ass, 'pix', None, None)


# ---------------------------------------------------------------------------
# suprimir_despesas_previstas_por_recorrencia
# ---------------------------------------------------------------------------

def test_suprimir_despesas_previstas_futuras(app_context):
    hoje = date.today().replace(day=1)
    d1 = _despesa_prevista_app(origem_id=5, data_prevista=hoje, status='PREVISTA')
    d2 = _despesa_prevista_app(origem_id=5, data_prevista=date(2026, 8, 1), status='PREVISTA')
    db.session.commit()
    n = suprimir_despesas_previstas_por_recorrencia('TRANSPORTE_APP', 5, 'TRANSPORTE_APP')
    db.session.commit()
    assert n == 2
    assert DespesaPrevista.query.get(d1.id).status == 'SUPRIMIDA'
    assert DespesaPrevista.query.get(d2.id).status == 'SUPRIMIDA'


def test_suprimir_nao_toca_confirmada_ou_adiada(app_context):
    hoje = date.today().replace(day=1)
    _despesa_prevista_app(origem_id=7, data_prevista=hoje, status='CONFIRMADA')
    _despesa_prevista_app(origem_id=7, data_prevista=hoje, status='ADIADA')
    db.session.commit()
    n = suprimir_despesas_previstas_por_recorrencia('TRANSPORTE_APP', 7, 'TRANSPORTE_APP')
    db.session.commit()
    assert n == 0


def test_suprimir_nao_toca_tipo_evento_diferente(app_context):
    hoje = date.today().replace(day=1)
    _despesa_prevista_app(origem_id=9, data_prevista=hoje, status='PREVISTA', tipo_evento='COMBUSTIVEL')
    db.session.commit()
    n = suprimir_despesas_previstas_por_recorrencia('TRANSPORTE_APP', 9, 'TRANSPORTE_APP')
    assert n == 0


# ---------------------------------------------------------------------------
# ativar_modalidade — ASSINATURA
# ---------------------------------------------------------------------------

def test_ativar_modalidade_assinatura(app_context):
    cat = _categoria()
    ass = _assinatura(cat_id=cat.id, valor=950.0)
    db.session.commit()

    resultado = ativar_modalidade({
        'tipo_modalidade': 'ASSINATURA',
        'origem_id': ass.id,
        'meio_pagamento': 'debito',
        'criar_recorrencia': True,
    })
    db.session.commit()

    assert resultado['cenario']['tipo_modalidade'] == 'ASSINATURA'
    assert resultado['recorrencia'] is not None
    assert float(resultado['recorrencia']['valor']) == pytest.approx(950.0)


def test_ativar_assinatura_inexistente_falha(app_context):
    with pytest.raises(ValueError, match='MobilidadeAssinatura'):
        ativar_modalidade({'tipo_modalidade': 'ASSINATURA', 'origem_id': 9999, 'meio_pagamento': 'pix'})


# ---------------------------------------------------------------------------
# Endpoints REST de assinaturas
# ---------------------------------------------------------------------------

def test_endpoint_get_assinaturas(client, app_context):
    _assinatura(nome='Sub A')
    db.session.commit()
    r = client.get('/api/veiculos/mobilidade/assinaturas')
    assert r.status_code == 200
    data = r.get_json()
    assert data['success'] is True
    assert any(a['nome'] == 'Sub A' for a in data['data'])


def test_endpoint_post_assinatura(client, app_context):
    cat = _categoria()
    db.session.commit()
    r = client.post(
        '/api/veiculos/mobilidade/assinaturas',
        json={'nome': 'Nova Sub', 'valor_mensal': 750, 'categoria_id': cat.id},
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data['data']['nome'] == 'Nova Sub'


def test_endpoint_post_assinatura_sem_nome_400(client, app_context):
    r = client.post('/api/veiculos/mobilidade/assinaturas', json={'valor_mensal': 500})
    assert r.status_code == 400


def test_endpoint_put_assinatura(client, app_context):
    ass = _assinatura(valor=600)
    db.session.commit()
    r = client.put(
        f'/api/veiculos/mobilidade/assinaturas/{ass.id}',
        json={'valor_mensal': 700, 'status': 'INATIVO'},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert float(data['data']['valor_mensal']) == pytest.approx(700.0)
    assert data['data']['status'] == 'INATIVO'


def test_endpoint_mobilidade_ativo_assinatura(client, app_context):
    cat = _categoria()
    ass = _assinatura(cat_id=cat.id, valor=800)
    db.session.commit()
    ativar_modalidade({
        'tipo_modalidade': 'ASSINATURA',
        'origem_id': ass.id,
        'meio_pagamento': 'pix',
    })
    db.session.commit()
    r = client.get('/api/veiculos/mobilidade/ativo')
    assert r.status_code == 200
    d = r.get_json()
    assert d['data']['tipo_modalidade'] == 'ASSINATURA'
    assert d['data']['nome_origem'] == ass.nome
