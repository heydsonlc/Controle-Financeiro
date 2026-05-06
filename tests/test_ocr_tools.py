from pathlib import Path

import pytest

from backend.app import create_app
from backend.models import db
from backend.services.ocr_tools_service import OcrToolsService
from backend.services.perfil_financeiro_service import PerfilFinanceiroService


class FakeCompletedProcess:
    def __init__(self, returncode=0, stdout='', stderr=''):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture()
def app(tmp_path):
    app = create_app('testing')
    app.config['OCR_BASE_DIR'] = tmp_path / 'ocr'
    app.config['OCR_TESSERACT_SEARCH_ROOTS'] = [tmp_path]
    app.config['OCR_POPPLER_SEARCH_ROOTS'] = [tmp_path]
    with app.app_context():
        db.create_all()
        PerfilFinanceiroService.obter_ou_criar_perfis_iniciais()
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def _fake_run_tesseract(cmd, capture_output=True, text=True, timeout=10, check=False):
    joined = ' '.join(cmd)
    if '--version' in joined:
        return FakeCompletedProcess(stdout='tesseract v5.4.0\n leptonica-1.84.1')
    if '--list-langs' in joined:
        return FakeCompletedProcess(stdout='List of available languages in "/tmp/tessdata/" (1):\neng\n')
    return FakeCompletedProcess(returncode=1, stderr='unexpected command')


def _fake_run_tesseract_poppler(cmd, capture_output=True, text=True, timeout=10, check=False):
    name = Path(cmd[0]).name.lower()
    if 'tesseract' in name:
        return _fake_run_tesseract(cmd, capture_output, text, timeout, check)
    if name.startswith('pdftoppm'):
        return FakeCompletedProcess(stderr='pdftoppm version 24.02.0')
    if name.startswith('pdfinfo'):
        return FakeCompletedProcess(stderr='pdfinfo version 24.02.0')
    return FakeCompletedProcess(returncode=1, stderr='unexpected command')


def test_status_sem_ferramentas_retorna_estrutura_valida(client, monkeypatch):
    monkeypatch.setattr('backend.services.ocr_tools_service.shutil.which', lambda nome: None)

    response = client.get('/api/ocr/status')
    data = response.get_json()

    assert response.status_code == 200
    assert data['success'] is True
    assert data['tesseract']['disponivel'] is False
    assert data['poppler']['disponivel'] is False
    assert data['pronto_para_imagens'] is False
    assert data['pronto_para_pdf_escaneado'] is False


def test_autodeteccao_encontra_tesseract_mockado(client, app, tmp_path, monkeypatch):
    tesseract_dir = tmp_path / 'Tesseract-OCR'
    tesseract_dir.mkdir()
    tesseract = tesseract_dir / 'tesseract.exe'
    tesseract.write_text('', encoding='utf-8')
    monkeypatch.setattr('backend.services.ocr_tools_service.shutil.which', lambda nome: None)
    monkeypatch.setattr('backend.services.ocr_tools_service.subprocess.run', _fake_run_tesseract)

    response = client.post('/api/ocr/autodetectar', json={})
    data = response.get_json()

    assert response.status_code == 200
    assert data['tesseract']['caminho'] == str(tesseract)
    assert data['tesseract']['disponivel'] is True
    with app.app_context():
        assert OcrToolsService.carregar_config_ocr()['tesseract_path'] == str(tesseract)


def test_validacao_tesseract_executa_version_e_list_langs(app, tmp_path, monkeypatch):
    tesseract = tmp_path / 'tesseract.exe'
    tesseract.write_text('', encoding='utf-8')
    chamadas = []

    def fake_run(cmd, capture_output=True, text=True, timeout=10, check=False):
        chamadas.append(cmd)
        return _fake_run_tesseract(cmd, capture_output, text, timeout, check)

    monkeypatch.setattr('backend.services.ocr_tools_service.subprocess.run', fake_run)

    with app.app_context():
        info = OcrToolsService.validar_tesseract(str(tesseract))

    assert info['disponivel'] is True
    assert any('--version' in cmd for cmd in chamadas)
    assert any('--list-langs' in cmd for cmd in chamadas)


def test_detecta_eng_e_ausencia_de_por(app, tmp_path, monkeypatch):
    tesseract = tmp_path / 'tesseract.exe'
    tesseract.write_text('', encoding='utf-8')
    monkeypatch.setattr('backend.services.ocr_tools_service.subprocess.run', _fake_run_tesseract)

    with app.app_context():
        info = OcrToolsService.validar_tesseract(str(tesseract))

    assert info['eng_disponivel'] is True
    assert info['por_disponivel'] is False
    assert 'idioma portugues' in info['mensagem']


def test_poppler_ausente_retorna_aviso(client, monkeypatch):
    monkeypatch.setattr('backend.services.ocr_tools_service.shutil.which', lambda nome: None)

    response = client.post('/api/ocr/validar', json={})
    data = response.get_json()

    assert response.status_code == 200
    assert data['poppler']['disponivel'] is False
    assert 'Poppler nao encontrado' in data['poppler']['mensagem']


def test_configuracao_manual_salva_caminhos(client, app, tmp_path, monkeypatch):
    tesseract = tmp_path / 'tesseract.exe'
    tesseract.write_text('', encoding='utf-8')
    poppler = tmp_path / 'poppler' / 'bin'
    poppler.mkdir(parents=True)
    (poppler / 'pdftoppm.exe').write_text('', encoding='utf-8')
    (poppler / 'pdfinfo.exe').write_text('', encoding='utf-8')
    monkeypatch.setattr('backend.services.ocr_tools_service.subprocess.run', _fake_run_tesseract_poppler)

    response = client.post('/api/ocr/configurar', json={
        'tesseract_path': str(tesseract),
        'poppler_path': str(poppler),
    })

    assert response.status_code == 200
    with app.app_context():
        config = OcrToolsService.carregar_config_ocr()
    assert config['tesseract_path'] == str(tesseract)
    assert config['poppler_path'] == str(poppler)
    assert config['configuracao_manual'] is True


def test_endpoint_status_e_autodetectar_existentes(client):
    assert client.get('/api/ocr/status').status_code == 200
    assert client.post('/api/ocr/autodetectar', json={}).status_code == 200


def test_ui_contem_bloco_ocr_local(client):
    html = client.get('/configuracoes').get_data(as_text=True)

    assert 'OCR local' in html
    assert 'id="ocr-tesseract-path"' in html
    assert 'id="ocr-poppler-path"' in html
    assert 'id="ocr-tools-autodetect"' in html


def test_nao_altera_documentos_fiscais():
    service = (Path(__file__).resolve().parents[1] / 'backend' / 'services' / 'ir_documento_service.py').read_text(encoding='utf-8')

    assert 'ocr_tools_service' not in service
    assert 'pytesseract' not in service
    assert 'pdf2image' not in service


def test_nao_executa_ocr_real(app, tmp_path, monkeypatch):
    tesseract = tmp_path / 'tesseract.exe'
    tesseract.write_text('', encoding='utf-8')
    chamadas = []

    def fake_run(cmd, capture_output=True, text=True, timeout=10, check=False):
        chamadas.append(cmd)
        return _fake_run_tesseract(cmd, capture_output, text, timeout, check)

    monkeypatch.setattr('backend.services.ocr_tools_service.subprocess.run', fake_run)

    with app.app_context():
        OcrToolsService.validar_tesseract(str(tesseract))

    assert all('--version' in cmd or '--list-langs' in cmd for cmd in chamadas)
