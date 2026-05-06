from datetime import date, timedelta
from pathlib import Path

import pytest
from flask import Flask, render_template

from backend.models import (
    db,
    CartaoCategoriaLimite,
    Categoria,
    CategoriaCartao,
    ConfigAgregador,
    Conta,
    ContaBancaria,
    ItemDespesa,
    DocumentoEmpresarialMetadata,
    IrComprovante,
    LancamentoAgregado,
    MobilidadeCenarioAtivo,
    PerfilFinanceiro,
)
from backend.routes.dashboard import dashboard_bp


@pytest.fixture()
def app_context():
    root = Path(__file__).resolve().parents[1]
    app = Flask(
        __name__,
        template_folder=str(root / 'frontend' / 'templates'),
        static_folder=str(root / 'frontend' / 'static'),
    )
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    app.register_blueprint(dashboard_bp, url_prefix='/api/dashboard')

    @app.route('/')
    def index():
        return render_template('index.html', active_page='dashboard', page_title='Dashboard Financeiro')

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def _periodo_atual():
    hoje = date.today()
    return date(hoje.year, hoje.month, 1)


def _base_cartao():
    categoria = Categoria(nome='Combustivel', ativo=True)
    categoria_cartao = CategoriaCartao(nome='Mobilidade', cor='#2563eb', ativo=True)
    cartao = ItemDespesa(nome='Nubank', tipo='Agregador', ativo=True, recorrente=True)
    db.session.add_all([categoria, categoria_cartao, cartao])
    db.session.flush()

    db.session.add(ConfigAgregador(
        item_despesa_id=cartao.id,
        dia_fechamento=25,
        dia_vencimento=10,
        numero_cartao='1234 5678 9012 4321',
    ))
    db.session.add(CartaoCategoriaLimite(
        cartao_id=cartao.id,
        categoria_cartao_id=categoria_cartao.id,
        limite_mensal=1000,
        ativo=True,
    ))
    db.session.commit()
    return categoria, categoria_cartao, cartao


def _lancamento(cartao, categoria, categoria_cartao, valor=850):
    lancamento = LancamentoAgregado(
        cartao_id=cartao.id,
        categoria_id=categoria.id,
        categoria_cartao_id=categoria_cartao.id if categoria_cartao else None,
        descricao='Posto Teste',
        valor=valor,
        data_compra=date.today(),
        mes_fatura=_periodo_atual(),
    )
    db.session.add(lancamento)
    db.session.commit()
    return lancamento


def test_endpoint_resumo_responde_200_com_banco_vazio(app_context):
    with app_context.test_client() as client:
        response = client.get('/api/dashboard/resumo')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['success'] is True
    data = payload['data']
    assert data['kpis']['saldo_consolidado']['valor'] == 0.0
    assert data['categorias_cartao'] == []
    assert data['cartoes_limites']['itens'] == []


def test_endpoint_aceita_mes_referencia(app_context):
    with app_context.test_client() as client:
        response = client.get('/api/dashboard/resumo?mes_referencia=2026-05')

    assert response.status_code == 200
    assert response.get_json()['data']['periodo']['mes_referencia'] == '2026-05'


def test_dashboard_com_cartao_e_limite_retorna_consumo_categoria_cartao(app_context):
    categoria, categoria_cartao, cartao = _base_cartao()
    _lancamento(cartao, categoria, categoria_cartao, valor=850)

    with app_context.test_client() as client:
        response = client.get('/api/dashboard/resumo')

    data = response.get_json()['data']
    consumo = data['categorias_cartao'][0]
    assert consumo['nome'] == 'Mobilidade'
    assert consumo['limite'] == 1000.0
    assert consumo['gasto'] == 850.0
    assert consumo['percentual'] == 85.0
    assert consumo['status'] == 'atencao'


def test_dashboard_com_recorrencia_ativa_retorna_quantidade_e_valor(app_context):
    categoria = Categoria(nome='Internet', ativo=True)
    recorrencia = ItemDespesa(
        categoria=categoria,
        nome='Internet Fibra',
        tipo='Simples',
        ativo=True,
        recorrente=True,
        valor=120,
    )
    db.session.add_all([categoria, recorrencia])
    db.session.commit()

    with app_context.test_client() as client:
        response = client.get('/api/dashboard/resumo')

    recorrencias = response.get_json()['data']['kpis']['recorrencias_ativas']
    assert recorrencias['quantidade'] == 1
    assert recorrencias['valor_mensal'] == 120.0


def test_dashboard_com_mobilidade_ativa_retorna_modalidade(app_context):
    categoria, categoria_cartao, cartao = _base_cartao()
    recorrencia = ItemDespesa(
        categoria=categoria,
        nome='Combustivel mensal',
        tipo='Simples',
        ativo=True,
        recorrente=True,
        valor=680,
    )
    db.session.add(recorrencia)
    db.session.flush()
    db.session.add(MobilidadeCenarioAtivo(
        tipo_modalidade='VEICULO',
        origem_id=1,
        ativo_desde=date.today(),
        meio_pagamento='cartao',
        cartao_id=cartao.id,
        categoria_id=categoria.id,
        categoria_cartao_id=categoria_cartao.id,
        recorrencia_id=recorrencia.id,
        status='ATIVO',
    ))
    db.session.commit()

    with app_context.test_client() as client:
        response = client.get('/api/dashboard/resumo')

    mobilidade = response.get_json()['data']['mobilidade']
    assert mobilidade['tipo'] == 'VEICULO'
    assert mobilidade['nome'] == 'Veiculo proprio'
    assert mobilidade['custo_mensal'] == 680.0


def test_proximos_vencimentos_retorna_lista_coerente(app_context):
    categoria = Categoria(nome='Casa', ativo=True)
    item = ItemDespesa(categoria=categoria, nome='Aluguel', tipo='Simples', ativo=True)
    conta = Conta(
        item_despesa=item,
        mes_referencia=_periodo_atual(),
        descricao='Aluguel Matriz',
        valor=4300,
        data_vencimento=date.today() + timedelta(days=2),
        status_pagamento='Pendente',
    )
    db.session.add_all([categoria, item, conta])
    db.session.commit()

    with app_context.test_client() as client:
        response = client.get('/api/dashboard/resumo')

    vencimentos = response.get_json()['data']['proximos_vencimentos']
    assert len(vencimentos) == 1
    assert vencimentos[0]['descricao'] == 'Aluguel Matriz'
    assert vencimentos[0]['valor'] == 4300.0


def test_alerta_de_limite_acima_de_80_aparece(app_context):
    categoria, categoria_cartao, cartao = _base_cartao()
    _lancamento(cartao, categoria, categoria_cartao, valor=850)

    with app_context.test_client() as client:
        response = client.get('/api/dashboard/resumo')

    alertas = response.get_json()['data']['alertas']
    assert any('acima de 80%' in alerta['mensagem'] for alerta in alertas)


def test_alerta_documental_empresarial_vencendo_aparece_no_dashboard(app_context):
    empresa = PerfilFinanceiro(nome='Empresa Teste', tipo='EMPRESA', ativo=True, padrao=True)
    db.session.add(empresa)
    db.session.flush()
    comprovante = IrComprovante(
        perfil_financeiro_id=empresa.id,
        ano_calendario=date.today().year,
        prestador_nome='Alvara Empresa',
        hash_arquivo='dashboard-doc-alerta',
    )
    db.session.add(comprovante)
    db.session.flush()
    db.session.add(DocumentoEmpresarialMetadata(
        comprovante_id=comprovante.id,
        perfil_financeiro_id=empresa.id,
        tipo_documental='CERTIDAO_LICENCA',
        categoria_documental='ALVARA_FUNCIONAMENTO',
        data_validade=date.today() + timedelta(days=10),
        status_documental='VENCENDO',
        obrigatorio=True,
    ))
    db.session.commit()

    with app_context.test_client() as client:
        response = client.get('/api/dashboard/resumo')

    alertas = response.get_json()['data']['alertas']
    assert any('documento(s) empresarial(is) com validade vencendo em 30 dias' in alerta['mensagem'] for alerta in alertas)


def test_json_contem_blocos_esperados(app_context):
    with app_context.test_client() as client:
        response = client.get('/api/dashboard/resumo')

    data = response.get_json()['data']
    assert set([
        'periodo',
        'kpis',
        'operacional',
        'fluxo_caixa',
        'categorias_cartao',
        'proximos_vencimentos',
        'cartoes_limites',
        'mobilidade',
        'acoes_rapidas',
        'alertas',
    ]).issubset(data.keys())


def test_rota_html_dashboard_renderiza(app_context):
    with app_context.test_client() as client:
        response = client.get('/')

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Dashboard Financeiro' in html
    assert 'Consumo por Categoria do Cart' in html
