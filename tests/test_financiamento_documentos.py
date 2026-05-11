import hashlib
import io
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from flask import Flask, render_template

from backend.models import db, Financiamento, FinanciamentoDocumento
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
        MAX_FINANCIAMENTO_DOCUMENTO_SIZE=10 * 1024 * 1024,
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


def _pdf_bytes(texto='contrato'):
    return b'%PDF-1.4\n' + texto.encode('utf-8')


def _png_bytes():
    return b'\x89PNG\r\n\x1a\n' + b'\x00' * 64


def _criar_financiamento(nome='Financiamento Documento'):
    perfil_id = PerfilFinanceiroService.obter_perfil_ativo_id({})
    financiamento = Financiamento(
        perfil_financeiro_id=perfil_id,
        nome=nome,
        produto='SFH',
        sistema_amortizacao='SAC',
        valor_financiado=Decimal('250000.00'),
        prazo_total_meses=240,
        prazo_remanescente_meses=240,
        taxa_juros_nominal_anual=Decimal('9.5000'),
        taxa_juros_mensal=Decimal('0.007500'),
        data_contrato=date(2026, 5, 1),
        data_primeira_parcela=date(2026, 6, 1),
        valor_seguro_mensal=Decimal('180.00'),
        taxa_administracao_fixa=Decimal('25.00'),
        saldo_devedor_atual=Decimal('250000.00'),
        data_base=date(2026, 6, 1),
    )
    db.session.add(financiamento)
    db.session.commit()
    return financiamento


def _upload_pdf(client, financiamento_id, nome='contrato.pdf', tipo='contrato'):
    conteudo = _pdf_bytes(nome)
    return client.post(
        f'/api/financiamentos/{financiamento_id}/documentos',
        data={
            'tipo_documento': tipo,
            'competencia': '2026-05',
            'ano_base': '2026',
            'data_documento': '2026-05-10',
            'observacao': 'Documento do contrato',
            'arquivo': (io.BytesIO(conteudo), nome, 'application/pdf'),
        },
        content_type='multipart/form-data',
    ), conteudo


def test_upload_pdf_valido_grava_metadados_hash_e_arquivo(client, app_context):
    financiamento = _criar_financiamento()
    response, conteudo = _upload_pdf(client, financiamento.id)

    data = response.get_json()
    documento = FinanciamentoDocumento.query.one()
    caminho = Path(app_context.config['FINANCIAMENTO_DOCUMENTOS_DIR']) / documento.caminho_relativo

    assert response.status_code == 201
    assert data['success'] is True
    assert data['documento']['tipo_documento'] == 'contrato'
    assert data['documento']['rotulo_tipo'] == 'Contrato'
    assert data['documento']['competencia'] == '2026-05'
    assert data['documento']['ano_base'] == 2026
    assert data['documento']['data_documento'] == '2026-05-10'
    assert documento.hash_arquivo == hashlib.sha256(conteudo).hexdigest()
    assert caminho.is_file()
    assert caminho.read_bytes() == conteudo


def test_upload_imagem_valida(client):
    financiamento = _criar_financiamento()

    response = client.post(
        f'/api/financiamentos/{financiamento.id}/documentos',
        data={
            'tipo_documento': 'comprovante_pagamento',
            'arquivo': (io.BytesIO(_png_bytes()), 'comprovante.png', 'image/png'),
        },
        content_type='multipart/form-data',
    )

    documento = FinanciamentoDocumento.query.one()
    assert response.status_code == 201
    assert documento.mime_type == 'image/png'
    assert documento.nome_armazenado.endswith('.png')


@pytest.mark.parametrize(
    'payload, arquivo, erro',
    [
        (
            {'tipo_documento': 'tipo_invalido'},
            (io.BytesIO(_pdf_bytes()), 'contrato.pdf', 'application/pdf'),
            'Tipo de documento invalido',
        ),
        (
            {'tipo_documento': 'contrato', 'competencia': '2026-13'},
            (io.BytesIO(_pdf_bytes()), 'contrato.pdf', 'application/pdf'),
            'Competencia deve estar no formato YYYY-MM',
        ),
        (
            {'tipo_documento': 'contrato'},
            (io.BytesIO(b'MZ'), 'setup.exe', 'application/octet-stream'),
            'Formato de arquivo nao permitido',
        ),
        (
            {'tipo_documento': 'contrato'},
            (io.BytesIO(_pdf_bytes()), '../contrato.pdf', 'application/pdf'),
            'Nome de arquivo invalido',
        ),
    ],
)
def test_upload_bloqueios_de_validacao(client, payload, arquivo, erro):
    financiamento = _criar_financiamento()
    response = client.post(
        f'/api/financiamentos/{financiamento.id}/documentos',
        data={**payload, 'arquivo': arquivo},
        content_type='multipart/form-data',
    )

    data = response.get_json()
    assert response.status_code == 400
    assert data['success'] is False
    assert erro in data['error']
    assert FinanciamentoDocumento.query.count() == 0


def test_upload_bloqueia_arquivo_acima_do_limite(client, app_context):
    app_context.config['MAX_FINANCIAMENTO_DOCUMENTO_SIZE'] = 10
    financiamento = _criar_financiamento()

    response = client.post(
        f'/api/financiamentos/{financiamento.id}/documentos',
        data={
            'tipo_documento': 'contrato',
            'arquivo': (io.BytesIO(_pdf_bytes('muito grande')), 'contrato.pdf', 'application/pdf'),
        },
        content_type='multipart/form-data',
    )

    assert response.status_code == 400
    assert 'Arquivo excede o tamanho maximo permitido' in response.get_json()['error']
    assert FinanciamentoDocumento.query.count() == 0


def test_listagem_download_e_escopo_por_financiamento(client):
    financiamento_a = _criar_financiamento('Financiamento A')
    financiamento_b = _criar_financiamento('Financiamento B')
    upload_a, conteudo_a = _upload_pdf(client, financiamento_a.id, nome='a.pdf')
    _upload_pdf(client, financiamento_b.id, nome='b.pdf')
    doc_id = upload_a.get_json()['documento']['id']

    lista_a = client.get(f'/api/financiamentos/{financiamento_a.id}/documentos')
    download_a = client.get(f'/api/financiamentos/{financiamento_a.id}/documentos/{doc_id}/download')
    download_cruzado = client.get(f'/api/financiamentos/{financiamento_b.id}/documentos/{doc_id}/download')

    assert lista_a.status_code == 200
    assert lista_a.get_json()['total'] == 1
    assert lista_a.get_json()['documentos'][0]['nome_original'] == 'a.pdf'
    assert download_a.status_code == 200
    assert download_a.data == conteudo_a
    assert download_cruzado.status_code == 404


def test_download_bloqueia_path_traversal_em_metadado(client):
    financiamento = _criar_financiamento()
    upload, _ = _upload_pdf(client, financiamento.id)
    doc_id = upload.get_json()['documento']['id']
    documento = db.session.get(FinanciamentoDocumento, doc_id)
    documento.caminho_relativo = '../fora.pdf'
    db.session.commit()

    response = client.get(f'/api/financiamentos/{financiamento.id}/documentos/{doc_id}/download')

    assert response.status_code == 400
    assert 'Caminho de arquivo invalido' in response.get_json()['error']


def test_excluir_documento_remove_metadado_e_arquivo(client, app_context):
    financiamento = _criar_financiamento()
    upload, _ = _upload_pdf(client, financiamento.id)
    doc_id = upload.get_json()['documento']['id']
    documento = db.session.get(FinanciamentoDocumento, doc_id)
    caminho = Path(app_context.config['FINANCIAMENTO_DOCUMENTOS_DIR']) / documento.caminho_relativo

    response = client.delete(f'/api/financiamentos/{financiamento.id}/documentos/{doc_id}')

    assert response.status_code == 200
    assert response.get_json()['success'] is True
    assert FinanciamentoDocumento.query.count() == 0
    assert not caminho.exists()
