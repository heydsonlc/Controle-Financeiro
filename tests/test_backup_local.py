import json
import subprocess
from pathlib import Path

import pytest

from backend.app import create_app
from backend.models import Preferencia, db
from backend.services.backup_service import BackupService
from backend.services.perfil_financeiro_service import PerfilFinanceiroService
from tests.conftest import autenticar_cliente_teste


@pytest.fixture()
def app(tmp_path):
    app = create_app('testing')
    app.config['BACKUP_BASE_DIR'] = tmp_path / 'backups'
    app.config['BACKUP_POSTGRES_SEARCH_ROOTS'] = []
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
    return autenticar_cliente_teste(app.test_client(), app)


def _usar_postgres(app):
    app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://backup_user:senha-secreta@localhost:5432/controle_financeiro'


def _criar_backup_fixture(app, nome='fixture.dump', conteudo=b'backup fixture'):
    pasta = Path(app.config['BACKUP_BASE_DIR']) / 'postgres'
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / nome
    arquivo.write_bytes(conteudo)
    return arquivo


def _criar_ferramenta(tmp_path, nome):
    arquivo = tmp_path / nome
    arquivo.write_text('binario mockado', encoding='utf-8')
    return arquivo


def _configurar_ferramentas(app, **paths):
    config_file = Path(app.config['BACKUP_BASE_DIR']) / 'backup_config.json'
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(json.dumps(paths), encoding='utf-8')


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


def test_status_ferramentas_sem_configuracao_retorna_erro_controlado(client, monkeypatch):
    monkeypatch.setattr('backend.services.backup_service.shutil.which', lambda comando: None)

    response = client.get('/api/backup/ferramentas/status')
    data = response.get_json()

    assert response.status_code == 200
    assert data['success'] is True
    assert data['disponivel'] is False
    assert data['ferramentas']['pg_dump']['disponivel'] is False
    assert 'pg_dump' in data['ferramentas']['pg_dump']['mensagem']


def test_autodeteccao_encontra_binarios_mockados(client, app, tmp_path, monkeypatch):
    raiz = tmp_path / 'PostgreSQL'
    bin_dir = raiz / '18' / 'bin'
    bin_dir.mkdir(parents=True)
    for nome in ['pg_dump.exe', 'pg_restore.exe', 'psql.exe']:
        (bin_dir / nome).write_text('mock', encoding='utf-8')
    app.config['BACKUP_POSTGRES_SEARCH_ROOTS'] = [raiz]
    monkeypatch.setattr('backend.services.backup_service.subprocess.run', lambda comando, **kwargs: subprocess.CompletedProcess(comando, 0, stdout=f'{Path(comando[0]).name} 18.0', stderr=''))

    response = client.post('/api/backup/ferramentas/autodetectar', json={})
    data = response.get_json()

    assert response.status_code == 200
    assert data['disponivel'] is True
    assert data['configuracao']['pg_dump_path'].endswith('pg_dump.exe')
    assert data['configuracao']['pg_restore_path'].endswith('pg_restore.exe')


def test_configuracao_manual_salva_caminhos(client, tmp_path, monkeypatch):
    pg_dump = _criar_ferramenta(tmp_path, 'pg_dump.exe')
    pg_restore = _criar_ferramenta(tmp_path, 'pg_restore.exe')
    monkeypatch.setattr('backend.services.backup_service.subprocess.run', lambda comando, **kwargs: subprocess.CompletedProcess(comando, 0, stdout='PostgreSQL mock 18', stderr=''))

    response = client.post('/api/backup/ferramentas/configurar', json={
        'pg_dump_path': str(pg_dump),
        'pg_restore_path': str(pg_restore),
        'psql_path': '',
    })
    data = response.get_json()

    assert response.status_code == 200
    assert data['disponivel'] is True
    assert data['configuracao']['pg_dump_path'] == str(pg_dump)
    assert data['configuracao']['pg_restore_path'] == str(pg_restore)


def test_validacao_executa_version_com_mock(client, app, tmp_path, monkeypatch):
    pg_dump = _criar_ferramenta(tmp_path, 'pg_dump.exe')
    pg_restore = _criar_ferramenta(tmp_path, 'pg_restore.exe')
    _configurar_ferramentas(app, pg_dump_path=str(pg_dump), pg_restore_path=str(pg_restore))
    chamadas = []

    def fake_run(comando, **kwargs):
        chamadas.append(comando)
        return subprocess.CompletedProcess(comando, 0, stdout='PostgreSQL 18.0', stderr='')

    monkeypatch.setattr('backend.services.backup_service.subprocess.run', fake_run)

    data = client.get('/api/backup/ferramentas/status').get_json()

    assert data['disponivel'] is True
    assert all('--version' in chamada for chamada in chamadas)
    assert any(str(pg_dump) == chamada[0] for chamada in chamadas)


def test_backup_manual_com_pg_dump_mockado_registra_historico(client, app, tmp_path, monkeypatch):
    _usar_postgres(app)
    pg_dump_path = _criar_ferramenta(tmp_path, 'pg_dump.exe')

    def fake_which(comando):
        return str(pg_dump_path) if comando == 'pg_dump' else None

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


def test_backup_manual_usa_caminho_configurado(client, app, tmp_path, monkeypatch):
    _usar_postgres(app)
    pg_dump = _criar_ferramenta(tmp_path, 'pg_dump-configurado.exe')
    _configurar_ferramentas(app, pg_dump_path=str(pg_dump))
    monkeypatch.setattr('backend.services.backup_service.shutil.which', lambda comando: None)
    comandos = []

    def fake_run(comando, **kwargs):
        comandos.append(comando)
        destino = Path(comando[comando.index('--file') + 1])
        destino.write_bytes(b'conteudo dump')
        return subprocess.CompletedProcess(comando, 0, stdout='', stderr='')

    monkeypatch.setattr('backend.services.backup_service.subprocess.run', fake_run)

    data = client.post('/api/backup/executar', json={}).get_json()

    assert data['success'] is True
    assert comandos[0][0] == str(pg_dump)


def test_backup_manual_fallback_path_continua_funcionando(client, app, tmp_path, monkeypatch):
    _usar_postgres(app)
    pg_dump_path = _criar_ferramenta(tmp_path, 'pg_dump-path.exe')

    def fake_which(comando):
        return str(pg_dump_path) if comando == 'pg_dump' else None

    def fake_run(comando, **kwargs):
        destino = Path(comando[comando.index('--file') + 1])
        destino.write_bytes(b'conteudo dump')
        return subprocess.CompletedProcess(comando, 0, stdout='', stderr='')

    monkeypatch.setattr('backend.services.backup_service.shutil.which', fake_which)
    monkeypatch.setattr('backend.services.backup_service.subprocess.run', fake_run)

    data = client.post('/api/backup/executar', json={}).get_json()

    assert data['success'] is True
    assert data['data']['status'] == 'concluido'


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


def test_restore_usa_pg_restore_configurado(client, app, tmp_path, monkeypatch):
    _usar_postgres(app)
    _criar_backup_fixture(app, 'restore-config.dump')
    pg_restore = _criar_ferramenta(tmp_path, 'pg_restore.exe')
    _configurar_ferramentas(app, pg_restore_path=str(pg_restore))
    comandos = []

    def fake_run(comando, **kwargs):
        comandos.append(comando)
        return subprocess.CompletedProcess(comando, 0, stdout='', stderr='')

    monkeypatch.setattr('backend.services.backup_service.shutil.which', lambda comando: None)
    monkeypatch.setattr('backend.services.backup_service.subprocess.run', fake_run)

    response = client.post('/api/backup/restaurar', json={
        'arquivo': 'restore-config.dump',
        'confirmacao': 'CONFIRMO RESTAURACAO',
    })

    assert response.status_code == 200
    assert response.get_json()['success'] is True
    assert comandos[0][0] == str(pg_restore)


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
    assert 'Ferramentas PostgreSQL' in html
    assert 'id="backup-pg-dump-path"' in html
    assert 'id="backup-pg-restore-path"' in html


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
