import json
import subprocess
from pathlib import Path

import pytest

from backend.app import create_app
from backend.models import Preferencia, db
from backend.services.backup_service import BackupService
from backend.services.perfil_financeiro_service import PerfilFinanceiroService


@pytest.fixture()
def app(tmp_path):
    app = create_app('testing')
    app.config['BACKUP_BASE_DIR'] = tmp_path / 'backups'
    with app.app_context():
        db.create_all()
        PerfilFinanceiroService.obter_ou_criar_perfis_iniciais()
        db.session.add(Preferencia(
            nome_usuario='Usuário Backup',
            renda_principal=12345.67,
            tema_sistema='claro',
            cor_principal='#2563eb',
        ))
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def _usar_postgres(app):
    app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://backup_user:senha-secreta@localhost:5432/controle_financeiro'


def _criar_backup_fixture(app, nome='fixture.dump', conteudo=b'backup fixture'):
    pasta = Path(app.config['BACKUP_BASE_DIR']) / 'postgres'
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / nome
    arquivo.write_bytes(conteudo)
    return arquivo


def test_status_inicial_retorna_estrutura_valida(client):
    response = client.get('/api/backup/status')
    data = response.get_json()

    assert response.status_code == 200
    assert data['success'] is True
    assert 'checklist' in data
    assert data['formato'] == 'custom .dump'
    assert data['agendamento']['retencao_dias'] == 30


def test_historico_vazio_funciona(client):
    response = client.get('/api/backup/historico')
    data = response.get_json()

    assert response.status_code == 200
    assert data['success'] is True
    assert data['data'] == []


def test_backup_manual_com_pg_dump_mockado_registra_historico(client, app, monkeypatch):
    _usar_postgres(app)

    def fake_which(comando):
        return 'pg_dump.exe' if comando == 'pg_dump' else None

    def fake_run(comando, **kwargs):
        destino = Path(comando[comando.index('--file') + 1])
        destino.write_bytes(b'conteudo dump')
        return subprocess.CompletedProcess(comando, 0, stdout='', stderr='')

    monkeypatch.setattr('backend.services.backup_service.shutil.which', fake_which)
    monkeypatch.setattr('backend.services.backup_service.subprocess.run', fake_run)

    response = client.post('/api/backup/executar', json={})
    data = response.get_json()

    assert response.status_code == 200
    assert data['success'] is True
    assert data['data']['status'] == 'concluido'
    assert data['data']['arquivo'].endswith('.dump')

    historico = client.get('/api/backup/historico').get_json()['data']
    assert historico[0]['status'] == 'concluido'
    assert historico[0]['tamanho_bytes'] > 0


def test_falha_de_pg_dump_retorna_erro_controlado(client, app, monkeypatch):
    _usar_postgres(app)
    monkeypatch.setattr('backend.services.backup_service.shutil.which', lambda comando: None)

    response = client.post('/api/backup/executar', json={})
    data = response.get_json()

    assert response.status_code == 200
    assert data['success'] is False
    assert 'pg_dump' in data['error']
    assert 'senha-secreta' not in json.dumps(data)


def test_download_bloqueia_path_traversal(client):
    response = client.get('/api/backup/download/%2E%2E%2Fsegredo.dump')
    data = response.get_json()

    assert response.status_code == 400
    assert data['success'] is False


def test_download_de_backup_existente_funciona(client, app):
    _criar_backup_fixture(app, 'download.dump', b'dump bytes')

    response = client.get('/api/backup/download/download.dump')

    assert response.status_code == 200
    assert response.data == b'dump bytes'
    assert 'attachment' in response.headers['Content-Disposition']


def test_restauracao_sem_confirmacao_e_bloqueada(client, app):
    _criar_backup_fixture(app, 'restore.dump')

    response = client.post('/api/backup/restaurar', json={
        'arquivo': 'restore.dump',
        'confirmacao': '',
    })

    assert response.status_code == 400
    assert 'Confirmação forte' in response.get_json()['error']


def test_restauracao_com_arquivo_fora_da_pasta_e_bloqueada(client):
    response = client.post('/api/backup/restaurar', json={
        'arquivo': '../restore.dump',
        'confirmacao': 'CONFIRMO RESTAURACAO',
    })

    assert response.status_code == 400
    assert response.get_json()['success'] is False


def test_exportar_configuracoes_retorna_json_sem_dados_financeiros(client):
    response = client.get('/api/backup/configuracoes/exportar')
    data = response.get_json()
    bruto = response.get_data(as_text=True)

    assert response.status_code == 200
    assert data['tipo'] == 'controle_financeiro_configuracoes'
    assert 'preferencias' in data['conteudo']
    assert 'perfis_financeiros' in data['conteudo']
    assert 'renda_principal' not in bruto
    assert '12345.67' not in bruto


def test_importar_configuracoes_placeholder_seguro_valida_json(client):
    response = client.post('/api/backup/configuracoes/importar', json={
        'tipo': 'controle_financeiro_configuracoes',
        'conteudo': {'preferencias': {}},
    })
    data = response.get_json()

    assert response.status_code == 200
    assert data['success'] is True
    assert data['data']['aplicado'] is False


def test_ui_configuracoes_contem_secao_backup_reformulada(client):
    html = client.get('/configuracoes').get_data(as_text=True)

    assert 'Backup e Restauração' in html
    assert 'Exportar configurações' in html
    assert 'Importar configurações' in html
    assert 'Backup do PostgreSQL' in html
    assert 'Backups agendados' in html
    assert 'Histórico recente' in html
    assert 'Restauração segura' in html
    assert 'Boas práticas' in html


def test_botao_executar_backup_e_historico_renderizam(client):
    html = client.get('/configuracoes').get_data(as_text=True)

    assert 'id="backup-run"' in html
    assert 'Executar backup' in html
    assert 'id="backup-history-body"' in html
    assert 'id="backup-restore-confirmation"' in html


def test_agendamento_visual_e_persistido(client):
    response = client.post('/api/backup/agendamento', json={
        'ativo': True,
        'frequencia': 'semanal',
        'horario': '03:30',
        'retencao_dias': 45,
    })
    data = response.get_json()['data']

    assert response.status_code == 200
    assert data['ativo'] is True
    assert data['frequencia'] == 'semanal'
    assert data['horario'] == '03:30'
    assert data['retencao_dias'] == 45

    assert BackupService.obter_agendamento()['retencao_dias'] == 45
