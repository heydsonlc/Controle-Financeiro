import json
from pathlib import Path

import pytest

from backend.app import create_app
from backend.models import db
from backend.services.backup_service import (
    CONFIRMACAO_TESTE_RESTORE,
    PREFIXO_BANCO_TESTE_RESTORE,
    BackupService,
)
from backend.services.perfil_financeiro_service import PerfilFinanceiroService


@pytest.fixture()
def app(tmp_path):
    app = create_app('testing')
    app.config['BACKUP_BASE_DIR'] = tmp_path / 'backups'
    app.config['BACKUP_POSTGRES_SEARCH_ROOTS'] = []
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


def _usar_postgres(app, database='controle_financeiro'):
    app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql://backup_user:senha-secreta@localhost:5432/{database}'


def _criar_backup_fixture(app, nome='restore-test.dump', conteudo=b'dump'):
    pasta = Path(app.config['BACKUP_BASE_DIR']) / 'postgres'
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / nome
    arquivo.write_bytes(conteudo)
    return arquivo


def test_gerar_nome_banco_descartavel_com_prefixo_seguro(app):
    with app.app_context():
        nome = BackupService.gerar_nome_banco_teste()

    assert nome.startswith(PREFIXO_BANCO_TESTE_RESTORE)
    assert all(char.isalnum() or char == '_' for char in nome)


def test_validar_bloqueia_banco_principal(app):
    nome = f'{PREFIXO_BANCO_TESTE_RESTORE}principal'
    _usar_postgres(app, database=nome)

    with app.app_context(), pytest.raises(ValueError):
        BackupService.validar_nome_banco_descartavel(nome)


@pytest.mark.parametrize('nome', ['postgres', 'template0', 'template1'])
def test_validar_bloqueia_bancos_protegidos(app, nome):
    with app.app_context(), pytest.raises(ValueError):
        BackupService.validar_nome_banco_descartavel(nome)


def test_validar_bloqueia_nome_sem_prefixo_seguro(app):
    with app.app_context(), pytest.raises(ValueError):
        BackupService.validar_nome_banco_descartavel('controle_financeiro')


def test_testar_restauracao_sem_confirmacao_retorna_erro(client, app):
    _usar_postgres(app)
    _criar_backup_fixture(app)

    response = client.post('/api/backup/testar-restauracao', json={
        'arquivo': 'restore-test.dump',
        'confirmacao': '',
    })

    assert response.status_code == 400
    assert response.get_json()['success'] is False


def test_testar_restauracao_bloqueia_path_traversal(client, app):
    _usar_postgres(app)

    response = client.post('/api/backup/testar-restauracao', json={
        'arquivo': '../restore-test.dump',
        'confirmacao': CONFIRMACAO_TESTE_RESTORE,
    })

    assert response.status_code == 400
    assert response.get_json()['success'] is False


def test_service_chama_criacao_restore_validacao_e_drop(app, monkeypatch):
    _usar_postgres(app)
    _criar_backup_fixture(app)
    chamadas = []

    monkeypatch.setattr(BackupService, 'gerar_nome_banco_teste', staticmethod(lambda: f'{PREFIXO_BANCO_TESTE_RESTORE}20260505_120000'))
    monkeypatch.setattr(BackupService, 'criar_banco_teste', staticmethod(lambda nome: chamadas.append(('create', nome)) or {'status': 'criado'}))
    monkeypatch.setattr(BackupService, '_restaurar_arquivo_em_banco_teste', staticmethod(lambda caminho, nome, banco: chamadas.append(('restore', nome, caminho.name))))
    monkeypatch.setattr(BackupService, 'validar_restore_banco_teste', staticmethod(lambda nome: chamadas.append(('validate', nome)) or {
        'ok': True,
        'validacoes': [{'item': 'tabelas_publicas', 'ok': True, 'mensagem': 'ok'}],
    }))
    monkeypatch.setattr(BackupService, 'remover_banco_teste', staticmethod(lambda nome: chamadas.append(('drop', nome)) or {'status': 'removido'}))

    with app.app_context():
        resultado = BackupService.testar_restauracao_backup('restore-test.dump', CONFIRMACAO_TESTE_RESTORE)

    assert resultado['status'] == 'concluido'
    assert [item[0] for item in chamadas] == ['create', 'restore', 'validate', 'drop']
    assert resultado['removido_apos_teste'] is True


def test_se_restore_falha_drop_ainda_e_tentado(app, monkeypatch):
    _usar_postgres(app)
    _criar_backup_fixture(app)
    chamadas = []

    def falhar_restore(caminho, nome, banco):
        chamadas.append(('restore', nome))
        raise RuntimeError('falha simulada')

    monkeypatch.setattr(BackupService, 'gerar_nome_banco_teste', staticmethod(lambda: f'{PREFIXO_BANCO_TESTE_RESTORE}20260505_130000'))
    monkeypatch.setattr(BackupService, 'criar_banco_teste', staticmethod(lambda nome: chamadas.append(('create', nome)) or {'status': 'criado'}))
    monkeypatch.setattr(BackupService, '_restaurar_arquivo_em_banco_teste', staticmethod(falhar_restore))
    monkeypatch.setattr(BackupService, 'remover_banco_teste', staticmethod(lambda nome: chamadas.append(('drop', nome)) or {'status': 'removido'}))

    with app.app_context():
        resultado = BackupService.testar_restauracao_backup('restore-test.dump', CONFIRMACAO_TESTE_RESTORE)

    assert resultado['status'] == 'erro'
    assert [item[0] for item in chamadas] == ['create', 'restore', 'drop']
    assert resultado['removido_apos_teste'] is True


def test_historico_de_teste_e_registrado(app, monkeypatch):
    _usar_postgres(app)
    _criar_backup_fixture(app)
    monkeypatch.setattr(BackupService, 'gerar_nome_banco_teste', staticmethod(lambda: f'{PREFIXO_BANCO_TESTE_RESTORE}20260505_140000'))
    monkeypatch.setattr(BackupService, 'criar_banco_teste', staticmethod(lambda nome: {'status': 'criado'}))
    monkeypatch.setattr(BackupService, '_restaurar_arquivo_em_banco_teste', staticmethod(lambda caminho, nome, banco: None))
    monkeypatch.setattr(BackupService, 'validar_restore_banco_teste', staticmethod(lambda nome: {'ok': True, 'validacoes': []}))
    monkeypatch.setattr(BackupService, 'remover_banco_teste', staticmethod(lambda nome: {'status': 'removido'}))

    with app.app_context():
        BackupService.testar_restauracao_backup('restore-test.dump', CONFIRMACAO_TESTE_RESTORE)
        historico = BackupService.listar_testes_restauracao()

    assert historico
    assert historico[0]['backup_arquivo'] == 'restore-test.dump'
    assert historico[0]['database_teste'].startswith(PREFIXO_BANCO_TESTE_RESTORE)


def test_endpoint_testar_restauracao_existe(client, app, monkeypatch):
    _usar_postgres(app)
    _criar_backup_fixture(app)
    monkeypatch.setattr(BackupService, 'testar_restauracao_backup', staticmethod(lambda arquivo, confirmacao, manter_banco=False: {
        'status': 'concluido',
        'mensagem': 'ok',
        'backup_arquivo': arquivo,
        'database_teste': f'{PREFIXO_BANCO_TESTE_RESTORE}mock',
        'validacoes': [],
        'removido_apos_teste': True,
    }))

    response = client.post('/api/backup/testar-restauracao', json={
        'arquivo': 'restore-test.dump',
        'confirmacao': CONFIRMACAO_TESTE_RESTORE,
    })

    assert response.status_code == 200
    assert response.get_json()['success'] is True


def test_ui_contem_bloco_teste_de_restauracao(client):
    html = client.get('/configuracoes').get_data(as_text=True)

    assert 'Teste de restaura' in html
    assert 'id="backup-test-restore-file"' in html
    assert 'id="backup-test-restore-confirmation"' in html
    assert 'id="backup-test-restore-start"' in html
    assert 'id="backup-restore-test-history-body"' in html


def test_retorno_nao_expoe_credenciais(app, monkeypatch):
    _usar_postgres(app)
    _criar_backup_fixture(app)
    monkeypatch.setattr(BackupService, 'gerar_nome_banco_teste', staticmethod(lambda: f'{PREFIXO_BANCO_TESTE_RESTORE}20260505_150000'))
    monkeypatch.setattr(BackupService, 'criar_banco_teste', staticmethod(lambda nome: (_ for _ in ()).throw(RuntimeError('senha-secreta falhou'))))

    with app.app_context():
        resultado = BackupService.testar_restauracao_backup('restore-test.dump', CONFIRMACAO_TESTE_RESTORE)

    bruto = json.dumps(resultado)
    assert resultado['status'] == 'erro'
    assert 'senha-secreta' not in bruto
