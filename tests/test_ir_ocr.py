from pathlib import Path
import io
import subprocess

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
from backend.services.ocr_service import OcrService


TEXTO_OCR = (
    'Clinica OCR Local\n'
    'CNPJ 12.345.678/0001-90\n'
    'Data 10/05/2026\n'
    'Valor total R$ 980,00\n'
    'Servico odontologico com texto suficiente para classificacao automatica.'
)


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
        OCR_BASE_DIR=Path('/tmp/ocr-test-nao-usado'),
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


def _ocr_sucesso(texto=TEXTO_OCR, paginas=1, avisos=None):
    return {
        'sucesso': True,
        'texto': texto,
        'origem': 'ocr',
        'paginas_processadas': paginas,
        'avisos': avisos or [],
        'erro': None,
    }


def _ocr_falha(mensagem='OCR local nao configurado.'):
    return {
        'sucesso': False,
        'texto': '',
        'origem': 'ocr',
        'paginas_processadas': 0,
        'avisos': [],
        'erro': mensagem,
    }


def test_pdf_textual_suficiente_nao_chama_ocr(app_context, monkeypatch):
    texto_pdf = TEXTO_OCR + '\nTexto textual suficiente extraido sem OCR.'
    monkeypatch.setattr(IrDocumentoService, 'extrair_texto_pdf', staticmethod(lambda _conteudo: texto_pdf))

    def nao_deve_chamar(*_args, **_kwargs):
        raise AssertionError('OCR nao deveria ser chamado para PDF textual suficiente')

    monkeypatch.setattr(OcrService, 'executar_ocr_documento', staticmethod(nao_deve_chamar))

    with app_context.test_client() as client:
        response = client.post(
            '/api/ir/comprovantes/upload',
            data={'ano_calendario': '2026', 'arquivos': (_pdf_bytes(), 'textual.pdf', 'application/pdf')},
            content_type='multipart/form-data',
        )

    comprovante = IrComprovante.query.one()
    eventos = [evento.tipo_evento for evento in comprovante.eventos.all()]
    assert response.status_code == 200
    assert comprovante.texto_extraido == texto_pdf
    assert 'OCR_EXECUTADO' not in eventos
    assert 'TEXTO_EXTRAIDO' in eventos


def test_pdf_sem_texto_chama_ocr_com_mock_e_classifica(app_context, monkeypatch):
    categoria, ir = _criar_mapeamento_ir()
    monkeypatch.setattr(IrDocumentoService, 'extrair_texto_pdf', staticmethod(lambda _conteudo: 'curto'))
    chamadas = []

    def fake_ocr(conteudo, mime_type, filename=None):
        chamadas.append((mime_type, filename, len(conteudo)))
        return _ocr_sucesso()

    monkeypatch.setattr(OcrService, 'executar_ocr_documento', staticmethod(fake_ocr))

    with app_context.test_client() as client:
        response = client.post(
            '/api/ir/comprovantes/upload',
            data={'ano_calendario': '2026', 'arquivos': (_pdf_bytes(), 'escaneado.pdf', 'application/pdf')},
            content_type='multipart/form-data',
        )

    comprovante = IrComprovante.query.one()
    eventos = [evento.tipo_evento for evento in comprovante.eventos.order_by('id').all()]
    descricoes = ' '.join(evento.descricao or '' for evento in comprovante.eventos.all())
    assert response.status_code == 200
    assert chamadas and chamadas[0][0] == 'application/pdf'
    assert comprovante.status == 'CLASSIFICADO'
    assert comprovante.categoria_id == categoria.id
    assert comprovante.categoria_ir_id == ir.id
    assert comprovante.valor == 980
    assert 'OCR_EXECUTADO' in eventos
    assert 'TEXTO_EXTRAIDO_OCR' in eventos
    assert 'Clinica OCR Local' not in descricoes


def test_imagem_chama_ocr_com_mock(app_context, monkeypatch):
    _criar_mapeamento_ir()
    chamadas = []

    def fake_ocr(conteudo, mime_type, filename=None):
        chamadas.append((mime_type, filename, len(conteudo)))
        return _ocr_sucesso()

    monkeypatch.setattr(OcrService, 'executar_ocr_documento', staticmethod(fake_ocr))

    with app_context.test_client() as client:
        response = client.post(
            '/api/ir/comprovantes/upload',
            data={'ano_calendario': '2026', 'arquivos': (_png_bytes(), 'comprovante.png', 'image/png')},
            content_type='multipart/form-data',
        )

    comprovante = IrComprovante.query.one()
    assert response.status_code == 200
    assert chamadas and chamadas[0][0] == 'image/png'
    assert comprovante.texto_extraido.startswith('Clinica OCR Local')
    assert comprovante.status == 'CLASSIFICADO'


def test_ocr_falho_mantem_pendencia_e_nao_quebra_upload(app_context, monkeypatch):
    monkeypatch.setattr(OcrService, 'executar_ocr_documento', staticmethod(lambda *_args, **_kwargs: _ocr_falha('Tesseract ausente.')))

    with app_context.test_client() as client:
        response = client.post(
            '/api/ir/comprovantes/upload',
            data={'ano_calendario': '2026', 'arquivos': (_png_bytes(), 'comprovante.png', 'image/png')},
            content_type='multipart/form-data',
        )

    comprovante = IrComprovante.query.one()
    eventos = [evento.tipo_evento for evento in comprovante.eventos.all()]
    assert response.status_code == 200
    assert comprovante.status == 'PENDENTE_REVISAO'
    assert comprovante.texto_extraido is None
    assert 'OCR_FALHOU' in eventos


def test_ocr_limita_pdf_a_tres_paginas_e_registra_evento(app_context, monkeypatch):
    monkeypatch.setattr(IrDocumentoService, 'extrair_texto_pdf', staticmethod(lambda _conteudo: 'curto'))
    monkeypatch.setattr(
        OcrService,
        'executar_ocr_documento',
        staticmethod(lambda *_args, **_kwargs: _ocr_sucesso(paginas=3, avisos=['OCR limitado as 3 primeiras paginas do documento.'])),
    )

    with app_context.test_client() as client:
        response = client.post(
            '/api/ir/comprovantes/upload',
            data={'ano_calendario': '2026', 'arquivos': (_pdf_bytes(), 'longo.pdf', 'application/pdf')},
            content_type='multipart/form-data',
        )

    comprovante = IrComprovante.query.one()
    eventos = [evento.tipo_evento for evento in comprovante.eventos.all()]
    assert response.status_code == 200
    assert 'OCR_LIMITADO' in eventos
    assert '3 primeiras paginas' in comprovante.observacoes


def test_endpoint_reprocessar_ocr_respeita_comprovante_do_perfil(app_context, monkeypatch):
    _criar_mapeamento_ir()
    monkeypatch.setattr(OcrService, 'executar_ocr_documento', staticmethod(lambda *_args, **_kwargs: _ocr_sucesso()))

    with app_context.test_client() as client:
        upload = client.post(
            '/api/ir/comprovantes/upload',
            data={'ano_calendario': '2026', 'arquivos': (_png_bytes(), 'comprovante.png', 'image/png')},
            content_type='multipart/form-data',
        )
        comprovante_id = upload.get_json()['data'][0]['data']['comprovante']['id']
        response = client.post(f'/api/ir/comprovantes/{comprovante_id}/reprocessar-ocr')
        inexistente = client.post('/api/ir/comprovantes/999/reprocessar-ocr')

    assert response.status_code == 200
    assert response.get_json()['data']['texto_extraido'].startswith('Clinica OCR Local')
    assert inexistente.status_code == 404


def test_tesseract_ausente_retorna_erro_amigavel_para_imagem(monkeypatch):
    monkeypatch.setattr(OcrService, 'ocr_disponivel', classmethod(lambda cls: {
        'imagem_disponivel': False,
        'pdf_escaneado_disponivel': False,
        'tesseract': {},
        'poppler': {},
        'idiomas': [],
        'mensagens': [],
    }))

    resultado = OcrService.extrair_texto_imagem(b'imagem', nome_arquivo='a.png', mime_type='image/png')

    assert resultado['sucesso'] is False
    assert 'OCR local nao configurado' in resultado['erro']


def test_poppler_ausente_retorna_erro_amigavel_para_pdf(monkeypatch):
    monkeypatch.setattr(OcrService, 'ocr_disponivel', classmethod(lambda cls: {
        'imagem_disponivel': True,
        'pdf_escaneado_disponivel': False,
        'tesseract': {'caminho': 'tesseract'},
        'poppler': {},
        'idiomas': ['por', 'eng'],
        'mensagens': [],
    }))

    resultado = OcrService.converter_pdf_para_imagens(b'%PDF-1.4', max_paginas=3)

    assert resultado['sucesso'] is False
    assert 'Poppler nao encontrado' in resultado['erro']


def test_converter_pdf_limita_pdftoppm_a_tres_paginas(monkeypatch):
    comandos = []
    monkeypatch.setattr(OcrService, 'ocr_disponivel', classmethod(lambda cls: {
        'imagem_disponivel': True,
        'pdf_escaneado_disponivel': True,
        'tesseract': {'caminho': 'tesseract'},
        'poppler': {'pdftoppm_path': 'pdftoppm', 'pdfinfo_path': 'pdfinfo'},
        'idiomas': ['por', 'eng'],
        'mensagens': [],
    }))

    def fake_run(cmd, capture_output=True, text=True, timeout=10, check=False):
        comandos.append(cmd)
        if cmd[0] == 'pdfinfo':
            return subprocess.CompletedProcess(cmd, 0, stdout='Pages: 5\n', stderr='')
        if cmd[0] == 'pdftoppm':
            prefixo = Path(cmd[-1])
            for idx in range(1, 4):
                (prefixo.parent / f'{prefixo.name}-{idx}.png').write_bytes(b'png')
            return subprocess.CompletedProcess(cmd, 0, stdout='', stderr='')
        return subprocess.CompletedProcess(cmd, 1, stdout='', stderr='erro')

    monkeypatch.setattr('backend.services.ocr_service.subprocess.run', fake_run)

    resultado = OcrService.converter_pdf_para_imagens(b'%PDF-1.4', max_paginas=3)

    comando_pdftoppm = next(cmd for cmd in comandos if cmd[0] == 'pdftoppm')
    assert resultado['sucesso'] is True
    assert len(resultado['imagens']) == 3
    assert '-l' in comando_pdftoppm
    assert comando_pdftoppm[comando_pdftoppm.index('-l') + 1] == '3'
    assert 'OCR limitado as 3 primeiras paginas do documento.' in resultado['avisos']


def test_frontend_contem_badge_e_botao_reprocessar(app_context):
    with app_context.test_client() as client:
        response = client.get('/imposto-renda')

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'ir-review-ocr-alert' in html
    assert 'ir-review-ocr-reprocess' in html
