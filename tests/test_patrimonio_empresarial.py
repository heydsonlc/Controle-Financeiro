from datetime import date
from decimal import Decimal

import pytest

from backend.app import create_app
from backend.models import BemPatrimonial, IrComprovante, IrComprovanteVinculo, db
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


def _comprovante(perfil_id, sufixo='empresa', valor='6490.00', prestador='Dell Computadores do Brasil Ltda.'):
    comprovante = IrComprovante(
        perfil_financeiro_id=perfil_id,
        ano_calendario=2026,
        data_documento=date(2026, 5, 5),
        prestador_nome=prestador,
        prestador_cpf_cnpj='00000000000191',
        valor=Decimal(valor),
        status='VALIDADO',
        hash_arquivo=f'hash-patrimonio-{sufixo}',
        observacoes='Documento fiscal para patrimonio',
    )
    db.session.add(comprovante)
    db.session.flush()
    return comprovante


def _payload_bem(nome='Notebook Dell Latitude', valor=6490.0, imagem_arquivo=None):
    payload = {
        'nome': nome,
        'codigo': 'TAG-0001',
        'categoria': 'Informatica',
        'descricao': 'Notebook corporativo utilizado pela equipe administrativa.',
        'fornecedor': 'Dell Computadores do Brasil Ltda.',
        'documento_numero': '12854',
        'data_aquisicao': '2026-05-05',
        'valor_aquisicao': valor,
        'vida_util_meses': 36,
        'centro_custo': 'Administrativo',
        'localizacao': 'Escritorio - Sala 02',
        'responsavel': 'Equipe Administrativa',
        'observacoes': 'Cadastro empresarial',
    }
    if imagem_arquivo:
        payload['imagem_arquivo'] = imagem_arquivo
    return payload


def test_rota_patrimonio_contem_visao_empresarial_e_fluxo_pessoal(client):
    html = client.get('/patrimonio').get_data(as_text=True)

    assert 'Patrim&ocirc;nio Empresarial' in html
    assert 'id="patrimonio-empresarial"' in html
    assert 'id="patrimonio-pessoal"' in html
    assert 'id="bem-imagens-grid"' in html
    assert 'Novo bem' in html
    assert 'Vincular documento' in html
    assert 'Caixinhas' in html


def test_perfil_empresa_lista_bens_empresariais(client):
    _trocar_perfil(client, 'Empresa')
    response = client.post('/api/patrimonio/bens', json=_payload_bem())

    assert response.status_code == 201, response.get_data(as_text=True)
    criado = response.get_json()['data']
    assert criado['nome'] == 'Notebook Dell Latitude'

    lista = client.get('/api/patrimonio/bens').get_json()
    assert lista['success'] is True
    assert lista['total'] == 1
    assert lista['data'][0]['nome'] == 'Notebook Dell Latitude'


def test_perfil_pessoal_mantem_fluxo_atual_e_nao_ve_bem_empresa(client):
    _trocar_perfil(client, 'Empresa')
    criado = client.post('/api/patrimonio/bens', json=_payload_bem()).get_json()['data']

    _trocar_perfil(client, 'Pessoal')
    bens = client.get('/api/patrimonio/bens')
    contas = client.get('/api/patrimonio/contas')

    assert bens.status_code == 200
    assert bens.get_json()['data'] == []
    assert contas.status_code == 200
    assert criado['nome'] not in contas.get_data(as_text=True)


def test_bem_criado_sem_documento_fica_pendente_sem_lastro(client):
    _trocar_perfil(client, 'Empresa')
    response = client.post('/api/patrimonio/bens', json=_payload_bem(nome='Cadeira ergonomica'))

    assert response.status_code == 201
    bem = response.get_json()['data']
    assert bem['status_documental'] == 'SEM_DOCUMENTO'
    assert bem['documento'] is None
    assert bem['documento_label'] == 'Sem documento'


def test_documento_fiscal_da_empresa_pode_ser_vinculado_ao_bem(client, app):
    empresa = _trocar_perfil(client, 'Empresa')
    with app.app_context():
        comprovante = _comprovante(empresa['id'])
        db.session.commit()
        comprovante_id = comprovante.id

    bem = client.post('/api/patrimonio/bens', json=_payload_bem()).get_json()['data']
    response = client.post(f"/api/patrimonio/bens/{bem['id']}/vincular-documento", json={
        'comprovante_id': comprovante_id,
        'tipo_vinculo': 'NOTA_FISCAL',
        'natureza': 'PATRIMONIO_IMOBILIZADO',
        'observacoes': 'Nota vinculada ao imobilizado',
    })

    assert response.status_code == 200, response.get_data(as_text=True)
    atualizado = response.get_json()['data']
    assert atualizado['status_documental'] == 'COM_LASTRO'
    assert atualizado['documento']['id'] == comprovante_id
    with app.app_context():
        vinculo = IrComprovanteVinculo.query.filter_by(
            comprovante_id=comprovante_id,
            tipo_entidade='PATRIMONIO',
            entidade_id=bem['id'],
            ativo=True,
        ).first()
        assert vinculo is not None
        assert vinculo.natureza == 'PATRIMONIO_IMOBILIZADO'


def test_documento_fiscal_de_outro_perfil_nao_pode_ser_vinculado(client, app):
    pessoal = _trocar_perfil(client, 'Pessoal')
    with app.app_context():
        comprovante_pessoal = _comprovante(pessoal['id'], sufixo='pessoal', prestador='Fornecedor PF')
        db.session.commit()
        comprovante_id = comprovante_pessoal.id

    _trocar_perfil(client, 'Empresa')
    bem = client.post('/api/patrimonio/bens', json=_payload_bem()).get_json()['data']
    response = client.post(f"/api/patrimonio/bens/{bem['id']}/vincular-documento", json={
        'comprovante_id': comprovante_id,
        'tipo_vinculo': 'NOTA_FISCAL',
        'natureza': 'PATRIMONIO_IMOBILIZADO',
    })

    assert response.status_code in {400, 403, 404}
    detalhe = client.get(f"/api/patrimonio/bens/{bem['id']}").get_json()['data']
    assert detalhe['status_documental'] == 'SEM_DOCUMENTO'
    assert detalhe['documento'] is None


def test_criar_bem_a_partir_documento_preenche_fornecedor_data_valor(client, app):
    empresa = _trocar_perfil(client, 'Empresa')
    with app.app_context():
        comprovante = _comprovante(empresa['id'], sufixo='cadeira', valor='890.00', prestador='Moveis Office Ltda.')
        db.session.commit()
        comprovante_id = comprovante.id

    response = client.post('/api/patrimonio/bens/criar-a-partir-documento', json={
        'comprovante_id': comprovante_id,
        'nome': 'Cadeira ergonomica',
        'categoria': 'Moveis',
        'vida_util_meses': 48,
    })

    assert response.status_code == 201, response.get_data(as_text=True)
    bem = response.get_json()['data']
    assert bem['fornecedor'] == 'Moveis Office Ltda.'
    assert bem['data_aquisicao'] == '2026-05-05'
    assert bem['valor_aquisicao'] == 890.0
    assert bem['status_documental'] == 'COM_LASTRO'
    assert bem['documento']['id'] == comprovante_id


def test_resumo_calcula_total_lastro_pendencias_e_aquisicoes(client, app):
    empresa = _trocar_perfil(client, 'Empresa')
    client.post('/api/patrimonio/bens', json=_payload_bem(nome='Ar-condicionado escritorio', valor=5900.0))
    with app.app_context():
        comprovante = _comprovante(empresa['id'], sufixo='impressora', valor='2180.00')
        db.session.commit()
        comprovante_id = comprovante.id

    client.post('/api/patrimonio/bens/criar-a-partir-documento', json={
        'comprovante_id': comprovante_id,
        'nome': 'Impressora laser',
        'categoria': 'Equipamentos',
        'vida_util_meses': 60,
    })
    resumo = client.get('/api/patrimonio/bens/resumo').get_json()['data']

    assert resumo['patrimonio_total'] == 8080.0
    assert resumo['bens_cadastrados'] == 2
    assert resumo['bens_com_lastro'] == 1
    assert resumo['pendencias_documentais'] == 1
    assert resumo['aquisicoes_ano']['quantidade'] == 2


def test_detalhe_do_bem_valida_perfil_ativo(client):
    _trocar_perfil(client, 'Empresa')
    bem = client.post('/api/patrimonio/bens', json=_payload_bem()).get_json()['data']

    _trocar_perfil(client, 'Pessoal')
    response = client.get(f"/api/patrimonio/bens/{bem['id']}")

    assert response.status_code == 403


def test_imagens_locais_patrimonio_ficam_disponiveis_e_podem_ser_salvas(client):
    _trocar_perfil(client, 'Empresa')
    imagens = client.get('/api/patrimonio/bens/imagens')

    assert imagens.status_code == 200
    body = imagens.get_json()
    assert body['success'] is True
    if not body['data']:
        pytest.skip('Nenhuma imagem local de patrimonio disponivel no ambiente de teste')

    imagem = next((item for item in body['data'] if 'notebook' in item['arquivo'].lower()), body['data'][0])
    response = client.post('/api/patrimonio/bens', json=_payload_bem(imagem_arquivo=imagem['arquivo']))

    assert response.status_code == 201, response.get_data(as_text=True)
    bem = response.get_json()['data']
    assert bem['imagem_arquivo'] == imagem['arquivo']
    assert bem['imagem_url'] == imagem['url']


def test_status_documental_muda_para_com_lastro_ao_vincular(client, app):
    empresa = _trocar_perfil(client, 'Empresa')
    with app.app_context():
        comprovante = _comprovante(empresa['id'], sufixo='mesa', valor='2450.00')
        db.session.commit()
        comprovante_id = comprovante.id

    bem = client.post('/api/patrimonio/bens', json=_payload_bem(nome='Mesa de reuniao')).get_json()['data']
    assert bem['status_documental'] == 'SEM_DOCUMENTO'

    vinculado = client.post(f"/api/patrimonio/bens/{bem['id']}/vincular-documento", json={
        'comprovante_id': comprovante_id,
    }).get_json()['data']

    assert vinculado['status_documental'] == 'COM_LASTRO'
    assert vinculado['status_documental_label'] == 'Com lastro'
    with app.app_context():
        assert db.session.get(BemPatrimonial, bem['id']).status_documental == 'COM_LASTRO'
