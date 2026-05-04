from pathlib import Path
import io

import pytest
from flask import Flask, render_template

from backend.models import (
    Categoria,
    CategoriaPalavraChave,
    IrCategoria,
    IrCategoriaDespesa,
    IrComprovante,
    IrComprovanteArquivo,
    db,
)
from backend.routes.categorias import categorias_bp
from backend.routes.ir import ir_bp
from backend.services.ir_documento_service import IrDocumentoService


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
    app.register_blueprint(ir_bp, url_prefix='/api/ir')
    app.register_blueprint(categorias_bp, url_prefix='/api/categorias')

    @app.route('/imposto-renda')
    def imposto_renda_page():
        return render_template('imposto_renda.html', active_page='imposto_renda', page_title='Imposto de Renda')

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def _pdf_bytes(text='fixture'):
    return io.BytesIO((b'%PDF-1.4\n' + text.encode('utf-8')))


def _png_bytes():
    return io.BytesIO(b'\x89PNG\r\n\x1a\n' + b'\x00' * 64)


def _criar_mapeamento_ir():
    categoria = Categoria(nome='Odontologia', descricao='Dentista', ativo=True)
    palavra = CategoriaPalavraChave(categoria=categoria, palavra='clinica', ativo=True)
    ir = IrCategoria(nome='Odontologia', descricao='Tratamentos', dedutivel=True, ativo=True, ordem=1)
    db.session.add_all([categoria, palavra, ir])
    db.session.flush()
    vinculo = IrCategoriaDespesa(categoria_id=categoria.id, categoria_ir_id=ir.id, ativo=True)
    db.session.add(vinculo)
    db.session.commit()
    return categoria, ir


def test_rota_imposto_renda_renderiza(app_context):
    with app_context.test_client() as client:
        response = client.get('/imposto-renda')

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'ir-comprovantes-tbody' in html
    assert 'Importar comprovantes' in html
    assert 'ir-review-modal' in html


def test_categorias_ir_iniciais_endpoint(app_context):
    with app_context.test_client() as client:
        response = client.get('/api/ir/categorias')

    data = response.get_json()
    nomes = {item['nome'] for item in data['data']}
    assert response.status_code == 200
    assert {'Saude', 'Odontologia', 'Educacao', 'Outros'}.issubset(nomes)


def test_upload_pdf_textual_classifica_categoria_e_ir(app_context, monkeypatch):
    categoria, ir = _criar_mapeamento_ir()
    texto = 'Clinica OdontoMais\nCNPJ 12.345.678/0001-90\nData 10/05/2026\nValor total R$ 980,00'
    monkeypatch.setattr(IrDocumentoService, 'extrair_texto_pdf', staticmethod(lambda _conteudo: texto))

    with app_context.test_client() as client:
        response = client.post(
            '/api/ir/comprovantes/upload',
            data={'ano_calendario': '2026', 'arquivos': (_pdf_bytes(), 'recibo.pdf', 'application/pdf')},
            content_type='multipart/form-data',
        )

    data = response.get_json()['data'][0]['data']['comprovante']
    comprovante = IrComprovante.query.get(data['id'])
    arquivo = IrComprovanteArquivo.query.filter_by(comprovante_id=comprovante.id).one()

    assert response.status_code == 200
    assert comprovante.status == 'CLASSIFICADO'
    assert comprovante.categoria_id == categoria.id
    assert comprovante.categoria_ir_id == ir.id
    assert comprovante.valor == 980
    assert comprovante.texto_extraido == texto
    assert arquivo.conteudo.startswith(b'%PDF')
    assert arquivo.mime_type == 'application/pdf'


def test_upload_imagem_permitida_fica_pendente_sem_ocr(app_context):
    with app_context.test_client() as client:
        response = client.post(
            '/api/ir/comprovantes/upload',
            data={'ano_calendario': '2026', 'arquivos': (_png_bytes(), 'comprovante.png', 'image/png')},
            content_type='multipart/form-data',
        )

    comprovante = IrComprovante.query.one()
    assert response.status_code == 200
    assert comprovante.status == 'PENDENTE_REVISAO'
    assert 'OCR' in comprovante.observacoes
    assert IrComprovanteArquivo.query.one().conteudo.startswith(b'\x89PNG')


def test_upload_rejeita_tipo_invalido(app_context):
    with app_context.test_client() as client:
        response = client.post(
            '/api/ir/comprovantes/upload',
            data={'ano_calendario': '2026', 'arquivos': (io.BytesIO(b'texto'), 'nota.txt', 'text/plain')},
            content_type='multipart/form-data',
        )

    resultado = response.get_json()['data'][0]
    assert response.status_code == 207
    assert resultado['success'] is False
    assert 'Tipo de arquivo nao permitido' in resultado['error']
    assert IrComprovante.query.count() == 0


def test_hash_bloqueia_duplicidade(app_context, monkeypatch):
    monkeypatch.setattr(IrDocumentoService, 'extrair_texto_pdf', staticmethod(lambda _conteudo: 'Documento simples com texto suficiente para leitura automatica.'))

    with app_context.test_client() as client:
        primeira = client.post(
            '/api/ir/comprovantes/upload',
            data={'ano_calendario': '2026', 'arquivos': (_pdf_bytes('duplicado'), 'a.pdf', 'application/pdf')},
            content_type='multipart/form-data',
        )
        segunda = client.post(
            '/api/ir/comprovantes/upload',
            data={'ano_calendario': '2026', 'arquivos': (_pdf_bytes('duplicado'), 'b.pdf', 'application/pdf')},
            content_type='multipart/form-data',
        )

    assert primeira.status_code == 200
    assert segunda.status_code == 200
    assert segunda.get_json()['data'][0]['data']['duplicado'] is True
    assert IrComprovante.query.count() == 1


def test_listagem_atualizacao_validacao_e_arquivo(app_context, monkeypatch):
    ir = IrCategoria(nome='Saude', dedutivel=True, ativo=True, ordem=1)
    db.session.add(ir)
    db.session.commit()
    monkeypatch.setattr(IrDocumentoService, 'extrair_texto_pdf', staticmethod(lambda _conteudo: 'Hospital Sao Lucas\n15/05/2026\nR$ 1.250,00\ntexto suficiente para importar'))

    with app_context.test_client() as client:
        upload = client.post(
            '/api/ir/comprovantes/upload',
            data={'ano_calendario': '2026', 'arquivos': (_pdf_bytes('hospital'), 'hospital.pdf', 'application/pdf')},
            content_type='multipart/form-data',
        )
        comprovante_id = upload.get_json()['data'][0]['data']['comprovante']['id']

        update = client.put(f'/api/ir/comprovantes/{comprovante_id}', json={
            'prestador_nome': 'Hospital Sao Lucas',
            'valor': '1250.00',
            'categoria_ir_id': ir.id,
            'ano_calendario': 2026,
            'observacoes': 'Revisado manualmente',
        })
        validado = client.post(f'/api/ir/comprovantes/{comprovante_id}/validar')
        lista = client.get('/api/ir/comprovantes?ano=2026')
        arquivo = client.get(f'/api/ir/comprovantes/{comprovante_id}/arquivo')

    assert update.status_code == 200
    assert validado.status_code == 200
    assert validado.get_json()['data']['status'] == 'VALIDADO'
    assert lista.get_json()['total'] == 1
    assert arquivo.status_code == 200
    assert arquivo.data.startswith(b'%PDF')


def test_upload_invalido_nao_expoe_stack_sensivel(app_context):
    with app_context.test_client() as client:
        response = client.post('/api/ir/comprovantes/upload', data={}, content_type='multipart/form-data')

    data = response.get_json()
    assert response.status_code == 400
    assert data['success'] is False
    assert 'Traceback' not in str(data)
