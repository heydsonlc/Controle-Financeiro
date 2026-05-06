from datetime import date
from decimal import Decimal
from io import BytesIO

import pytest

from backend.app import create_app
from backend.models import Categoria, DespesaPrevista, IrComprovante, IrComprovanteVinculo, PerfilFinanceiro, db
from backend.services.ir_nfse_goiania_parser import eh_nfse_goiania
from backend.services.perfil_financeiro_service import PerfilFinanceiroService


@pytest.fixture()
def app():
    app = create_app('testing')
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


def _perfis(client):
    return client.get('/api/perfis-financeiros').get_json()['perfis']


def _perfil(client, nome):
    return next(perfil for perfil in _perfis(client) if perfil['nome'] == nome)


def _trocar_perfil(client, nome):
    perfil = _perfil(client, nome)
    response = client.post('/api/perfis-financeiros/ativo', json={'perfil_id': perfil['id']})
    assert response.status_code == 200, response.get_data(as_text=True)
    return perfil


def _png_bytes(texto=b'CTX5'):
    return BytesIO(b'\x89PNG\r\n\x1a\n' + texto)


def _upload_png(client, nome='documento_ctx5.png'):
    response = client.post(
        '/api/ir/comprovantes/upload',
        data={'ano_calendario': '2026', 'arquivo': (_png_bytes(), nome)},
        content_type='multipart/form-data',
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()['data'][0]['data']['comprovante']


def _criar_despesa_prevista(app, perfil_id, nome_categoria='Operacional CTX5'):
    with app.app_context():
        categoria = Categoria(
            perfil_financeiro_id=perfil_id,
            nome=nome_categoria,
            descricao='Categoria para lastro',
            cor='#2563eb',
            ativo=True,
        )
        db.session.add(categoria)
        db.session.flush()
        despesa = DespesaPrevista(
            perfil_financeiro_id=perfil_id,
            origem_tipo='MANUAL',
            origem_id=1,
            categoria_id=categoria.id,
            data_prevista=date(2026, 5, 1),
            data_original_prevista=date(2026, 5, 1),
            data_atual_prevista=date(2026, 5, 1),
            valor_previsto=Decimal('250.00'),
            status='PREVISTA',
        )
        db.session.add(despesa)
        db.session.commit()
        return despesa.id


def test_contexto_irpf_pessoal_e_documentos_fiscais_empresa(client):
    pessoal = client.get('/api/ir/contexto')
    assert pessoal.status_code == 200
    assert pessoal.get_json()['data']['modo'] == 'IRPF'
    assert pessoal.get_json()['data']['titulo'] == 'Imposto de Renda'

    _trocar_perfil(client, 'Empresa')
    empresa = client.get('/api/ir/contexto')
    nomes = {categoria['nome'] for categoria in empresa.get_json()['data']['categorias']}

    assert empresa.status_code == 200
    assert empresa.get_json()['data']['modo'] == 'DOCUMENTOS_FISCAIS_EMPRESA'
    assert empresa.get_json()['data']['titulo'] == 'Documentos da Empresa'
    assert 'Despesa operacional' in nomes
    assert 'Patrimonio / Imobilizado' in nomes
    assert 'Saude' not in nomes


def test_upload_empresa_fica_no_perfil_empresa_e_nao_aparece_no_pessoal(client, app):
    empresa = _trocar_perfil(client, 'Empresa')
    comprovante = _upload_png(client)

    assert comprovante['status_lastro'] == 'SEM_DOCUMENTO'
    assert client.get('/api/ir/comprovantes?ano=2026').get_json()['total'] == 1

    _trocar_perfil(client, 'Pessoal')
    assert client.get('/api/ir/comprovantes?ano=2026').get_json()['total'] == 0
    assert client.get(f"/api/ir/comprovantes/{comprovante['id']}").status_code == 404

    with app.app_context():
        assert IrComprovante.query.get(comprovante['id']).perfil_financeiro_id == empresa['id']


def test_vinculo_documento_despesa_no_mesmo_perfil_salva_status_lastro(client, app):
    empresa = _trocar_perfil(client, 'Empresa')
    despesa_id = _criar_despesa_prevista(app, empresa['id'])
    comprovante = _upload_png(client, 'nota_empresa_ctx5.png')

    response = client.post(f"/api/ir/comprovantes/{comprovante['id']}/vinculos", json={
        'tipo_entidade': 'DESPESA_PREVISTA',
        'entidade_id': despesa_id,
        'tipo_vinculo': 'NOTA_FISCAL',
        'natureza': 'DESPESA_OPERACIONAL',
        'status_lastro': 'VALIDADO',
        'observacoes': 'Documento vinculado a despesa operacional.',
    })
    resumo = client.get('/api/ir/lastro/resumo?ano=2026')

    assert response.status_code == 201, response.get_data(as_text=True)
    data = response.get_json()['data']
    assert data['perfil_financeiro_id'] == empresa['id']
    assert data['status_lastro'] == 'VALIDADO'
    assert data['natureza'] == 'DESPESA_OPERACIONAL'
    assert resumo.get_json()['data']['documentos_vinculados'] == 1
    assert resumo.get_json()['data']['documentos_sem_vinculo'] == 0

    with app.app_context():
        assert IrComprovanteVinculo.query.count() == 1


def test_vinculo_com_entidade_de_outro_perfil_e_bloqueado(client, app):
    pessoal = _perfil(client, 'Pessoal')
    despesa_pessoal_id = _criar_despesa_prevista(app, pessoal['id'], 'Pessoal CTX5')
    _trocar_perfil(client, 'Empresa')
    comprovante = _upload_png(client, 'nota_cross_ctx5.png')

    response = client.post(f"/api/ir/comprovantes/{comprovante['id']}/vinculos", json={
        'tipo_entidade': 'DESPESA_PREVISTA',
        'entidade_id': despesa_pessoal_id,
        'natureza': 'DESPESA_OPERACIONAL',
        'status_lastro': 'VALIDADO',
    })

    assert response.status_code == 400
    assert 'perfil financeiro ativo' in response.get_json()['error']
    with app.app_context():
        assert IrComprovanteVinculo.query.count() == 0


def test_fluxo_irpf_pessoal_e_parser_nfse_goiania_continuam_funcionando(client):
    contexto = client.get('/api/ir/contexto').get_json()['data']
    categorias = {categoria['nome'] for categoria in client.get('/api/ir/categorias').get_json()['data']}
    texto_nfse = 'Prefeitura Municipal de Goiania - GO\nNota Fiscal de Servico Eletronica - NFS-e\nDados do Prestador de Servico'

    assert contexto['modo'] == 'IRPF'
    assert 'Saude' in categorias
    assert 'Despesa operacional' not in categorias
    assert eh_nfse_goiania(texto_nfse) is True
