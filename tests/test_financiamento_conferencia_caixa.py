from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from flask import Flask, render_template

from backend.models import (
    Conta,
    db,
    Financiamento,
    FinanciamentoConferenciaCaixa,
    FinanciamentoDocumento,
    FinanciamentoParcela,
)
from backend.routes.financiamentos import financiamentos_bp
from backend.services.perfil_financeiro_service import PerfilFinanceiroService


@pytest.fixture()
def app_context(tmp_path):
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
        FINANCIAMENTO_DOCUMENTOS_DIR=tmp_path / 'uploads' / 'financiamentos',
    )
    db.init_app(app)
    app.register_blueprint(financiamentos_bp, url_prefix='/api/financiamentos')

    @app.route('/financiamentos')
    def financiamentos_page():
        return render_template(
            'financiamentos.html',
            active_page='financiamentos',
            page_title='Financiamentos',
        )

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app_context):
    return app_context.test_client()


def _criar_financiamento(nome='Financiamento CAIXA'):
    perfil_id = PerfilFinanceiroService.obter_perfil_ativo_id({})
    financiamento = Financiamento(
        perfil_financeiro_id=perfil_id,
        nome=nome,
        produto='SFH',
        sistema_amortizacao='SAC',
        indexador_saldo='TR',
        valor_financiado=Decimal('500000.00'),
        prazo_total_meses=420,
        prazo_remanescente_meses=420,
        taxa_juros_nominal_anual=Decimal('9.3800'),
        taxa_juros_mensal=Decimal('0.007816'),
        data_contrato=date(2024, 5, 1),
        data_primeira_parcela=date(2024, 6, 5),
        valor_seguro_mensal=Decimal('180.00'),
        taxa_administracao_fixa=Decimal('25.00'),
        saldo_devedor_atual=Decimal('500000.00'),
        data_base=date(2024, 6, 5),
    )
    db.session.add(financiamento)
    db.session.commit()
    return financiamento


def _criar_parcela(financiamento, competencia='2025-08', numero=16):
    ano, mes = [int(parte) for parte in competencia.split('-')]
    parcela = FinanciamentoParcela(
        perfil_financeiro_id=financiamento.perfil_financeiro_id,
        financiamento_id=financiamento.id,
        numero_parcela=numero,
        data_vencimento=date(ano, mes, 5),
        valor_amortizacao=Decimal('675.70'),
        valor_juros=Decimal('2139.11'),
        valor_seguro=Decimal('163.01'),
        valor_taxa_adm=Decimal('25.00'),
        valor_previsto_total=Decimal('3002.82'),
        saldo_devedor_apos_pagamento=Decimal('273000.00'),
        status='pendente',
    )
    db.session.add(parcela)
    db.session.commit()
    return parcela


def _criar_documento(financiamento, tipo='demonstrativo_valores_cobrados'):
    documento = FinanciamentoDocumento(
        perfil_financeiro_id=financiamento.perfil_financeiro_id,
        financiamento_id=financiamento.id,
        tipo_documento=tipo,
        competencia='2025-08',
        ano_base=2025,
        data_documento=date(2025, 8, 5),
        nome_original='demonstrativo.pdf',
        nome_armazenado='arquivo.pdf',
        mime_type='application/pdf',
        tamanho_bytes=100,
        hash_arquivo='a' * 64,
        caminho_relativo=f'{financiamento.id}/documentos/arquivo.pdf',
    )
    db.session.add(documento)
    db.session.commit()
    return documento


def test_registra_conferencia_de_parcela_calcula_diferencas(client):
    financiamento = _criar_financiamento()
    parcela = _criar_parcela(financiamento)
    documento = _criar_documento(financiamento)

    response = client.post(
        f'/api/financiamentos/{financiamento.id}/conferencias-caixa',
        json={
            'documento_id': documento.id,
            'tipo_conferencia': 'parcela',
            'competencia': '2025-08',
            'valor_real_amortizacao': '675,65',
            'valor_real_juros': '2138,11',
            'valor_real_seguro': '163,43',
            'valor_real_taxa_adm': '25,00',
            'valor_real_total': '3002,21',
            'observacao': 'Linha de agosto/2025 do demonstrativo CAIXA',
        },
    )

    data = response.get_json()
    assert response.status_code == 201
    assert data['success'] is True
    assert data['conferencia']['parcela_id'] == parcela.id
    assert data['conferencia']['valor_simulado_total'] == 3002.82
    assert data['conferencia']['diferenca_amortizacao'] == -0.05
    assert data['conferencia']['diferenca_juros'] == -1.0
    assert data['conferencia']['diferenca_seguro'] == 0.42
    assert data['conferencia']['diferenca_total'] == -0.61
    assert FinanciamentoConferenciaCaixa.query.count() == 1


def test_registra_conferencia_de_evolucao_de_saldo_sem_alterar_financiamento(client):
    financiamento = _criar_financiamento()
    _criar_parcela(financiamento, competencia='2026-05', numero=25)
    documento = _criar_documento(financiamento, tipo='demonstrativo_evolucao')
    documento.competencia = '2026-05'
    documento.data_documento = date(2026, 5, 5)
    db.session.commit()

    saldo_original = financiamento.saldo_devedor_atual
    response = client.post(
        f'/api/financiamentos/{financiamento.id}/conferencias-caixa',
        json={
            'documento_id': documento.id,
            'tipo_conferencia': 'evolucao_saldo',
            'data_referencia': '2026-05-05',
            'saldo_devedor_real': '270800,85',
            'juros_correcao_mes_real': '450,00',
            'amortizacao_mes_real': '680,00',
            'prazo_remanescente_real': 398,
        },
    )

    data = response.get_json()
    db.session.refresh(financiamento)
    assert response.status_code == 201
    assert data['conferencia']['saldo_devedor_simulado'] == 273000.0
    assert data['conferencia']['diferenca_saldo'] == -2199.15
    assert financiamento.saldo_devedor_atual == saldo_original
    assert FinanciamentoParcela.query.filter_by(financiamento_id=financiamento.id).count() == 1


def test_bloqueia_conferencia_com_documento_de_outro_financiamento(client):
    financiamento_a = _criar_financiamento('Contrato A')
    financiamento_b = _criar_financiamento('Contrato B')
    _criar_parcela(financiamento_a)
    documento_b = _criar_documento(financiamento_b)

    response = client.post(
        f'/api/financiamentos/{financiamento_a.id}/conferencias-caixa',
        json={
            'documento_id': documento_b.id,
            'tipo_conferencia': 'parcela',
            'competencia': '2025-08',
            'valor_real_total': '3002,21',
        },
    )

    assert response.status_code == 404
    assert 'Documento nao encontrado' in response.get_json()['error']
    assert FinanciamentoConferenciaCaixa.query.count() == 0


def test_excluir_conferencia_preserva_documento_parcela_e_financiamento(client):
    financiamento = _criar_financiamento()
    parcela = _criar_parcela(financiamento)
    documento = _criar_documento(financiamento)
    criar = client.post(
        f'/api/financiamentos/{financiamento.id}/conferencias-caixa',
        json={
            'documento_id': documento.id,
            'tipo_conferencia': 'parcela',
            'competencia': '2025-08',
            'valor_real_total': '3002,21',
        },
    )
    conferencia_id = criar.get_json()['conferencia']['id']

    response = client.delete(f'/api/financiamentos/{financiamento.id}/conferencias-caixa/{conferencia_id}')

    assert response.status_code == 200
    assert FinanciamentoConferenciaCaixa.query.count() == 0
    assert db.session.get(Financiamento, financiamento.id) is not None
    assert db.session.get(FinanciamentoDocumento, documento.id) is not None
    assert db.session.get(FinanciamentoParcela, parcela.id) is not None


def test_endpoint_valores_simulados_retorna_parcela_por_competencia(client):
    financiamento = _criar_financiamento()
    parcela = _criar_parcela(financiamento)

    response = client.get(f'/api/financiamentos/{financiamento.id}/valores-simulados?competencia=2025-08')

    data = response.get_json()
    assert response.status_code == 200
    assert data['success'] is True
    assert data['data']['encontrado'] is True
    assert data['data']['parcela_id'] == parcela.id
    assert data['data']['total'] == 3002.82


def test_registra_conferencia_de_quitacao_com_simulacao_e_percentual(client):
    financiamento = _criar_financiamento()
    financiamento.indexador_saldo = ''
    _criar_parcela(financiamento, competencia='2028-01', numero=42)
    documento = _criar_documento(financiamento, tipo='quitacao')
    db.session.commit()

    sim = client.post(
        f'/api/financiamentos/{financiamento.id}/simular-quitacao',
        json={'data_quitacao': '2028-01-10'},
    ).get_json()['data']
    valor_simulado = Decimal(str(sim['valor_quitacao_estimado'])).quantize(Decimal('0.01'))
    valor_oficial = valor_simulado + Decimal('149.40')

    response = client.post(
        f'/api/financiamentos/{financiamento.id}/conferencias-caixa',
        json={
            'tipo_conferencia': 'quitacao',
            'documento_id': documento.id,
            'data_referencia': '2028-01-10',
            'data_validade': '2028-01-15',
            'valor_oficial_banco': str(valor_oficial),
            'observacao': 'Proposta de quitação emitida pelo banco.',
        },
    )

    data = response.get_json()
    assert response.status_code == 201
    assert data['conferencia']['tipo_conferencia'] == 'quitacao'
    assert data['conferencia']['documento_id'] == documento.id
    assert data['conferencia']['valor_oficial_banco'] == float(valor_oficial)
    assert data['conferencia']['valor_simulado_app'] == float(valor_simulado)
    assert data['conferencia']['diferenca_total'] == 149.4
    assert data['conferencia']['percentual_diferenca'] > 0
    assert 'Validade da proposta: 2028-01-15' in data['conferencia']['observacao']


def test_conferencia_de_quitacao_nao_altera_estado_financeiro(client):
    financiamento = _criar_financiamento()
    financiamento.indexador_saldo = ''
    parcela = _criar_parcela(financiamento, competencia='2028-01', numero=42)
    saldo_original = financiamento.saldo_devedor_atual
    status_original = parcela.status
    contas_antes = Conta.query.count()
    db.session.commit()

    response = client.post(
        f'/api/financiamentos/{financiamento.id}/conferencias-caixa',
        json={
            'tipo_conferencia': 'quitacao',
            'data_referencia': '2028-01-10',
            'valor_oficial_banco': '270950,25',
            'valor_simulado_app': '270800,85',
        },
    )

    db.session.refresh(financiamento)
    db.session.refresh(parcela)
    assert response.status_code == 201
    assert financiamento.saldo_devedor_atual == saldo_original
    assert financiamento.ativo is True
    assert parcela.status == status_original
    assert Conta.query.count() == contas_antes


def test_conferencia_de_quitacao_bloqueia_documento_de_outro_financiamento(client):
    financiamento_a = _criar_financiamento('Contrato A')
    financiamento_b = _criar_financiamento('Contrato B')
    documento_b = _criar_documento(financiamento_b, tipo='quitacao')

    response = client.post(
        f'/api/financiamentos/{financiamento_a.id}/conferencias-caixa',
        json={
            'tipo_conferencia': 'quitacao',
            'documento_id': documento_b.id,
            'data_referencia': '2028-01-10',
            'valor_oficial_banco': '270950,25',
            'valor_simulado_app': '270800,85',
        },
    )

    assert response.status_code == 404
    assert 'Documento nao encontrado' in response.get_json()['error']


@pytest.mark.parametrize(
    'payload, erro',
    [
        (
            {'data_referencia': '2028-01-10', 'valor_oficial_banco': '0', 'valor_simulado_app': '270800,85'},
            'valor_oficial_banco deve ser maior que zero',
        ),
        (
            {'data_referencia': '2028/01/10', 'valor_oficial_banco': '270950,25', 'valor_simulado_app': '270800,85'},
            'data_referencia deve estar no formato YYYY-MM-DD',
        ),
        (
            {
                'data_referencia': '2028-01-10',
                'data_validade': '2028-01-09',
                'valor_oficial_banco': '270950,25',
                'valor_simulado_app': '270800,85',
            },
            'data_validade deve ser maior ou igual a data_referencia',
        ),
    ],
)
def test_conferencia_de_quitacao_validacoes(client, payload, erro):
    financiamento = _criar_financiamento()

    response = client.post(
        f'/api/financiamentos/{financiamento.id}/conferencias-caixa',
        json={'tipo_conferencia': 'quitacao', **payload},
    )

    assert response.status_code == 400
    assert erro in response.get_json()['error']
