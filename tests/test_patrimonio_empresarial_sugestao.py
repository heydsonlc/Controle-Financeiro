from datetime import date
from decimal import Decimal
from pathlib import Path

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


def _perfil(client, nome):
    perfis = client.get('/api/perfis-financeiros').get_json()['perfis']
    return next(perfil for perfil in perfis if perfil['nome'] == nome)


def _trocar_perfil(client, nome):
    perfil = _perfil(client, nome)
    response = client.post('/api/perfis-financeiros/ativo', json={'perfil_id': perfil['id']})
    assert response.status_code == 200, response.get_data(as_text=True)
    return perfil


def _comprovante(perfil_id, sufixo, texto, valor='6490.00', prestador='Dell Computadores do Brasil Ltda.'):
    comprovante = IrComprovante(
        perfil_financeiro_id=perfil_id,
        ano_calendario=2026,
        data_documento=date(2026, 5, 5),
        prestador_nome=prestador,
        prestador_cpf_cnpj='00000000000191',
        valor=Decimal(valor),
        status='PENDENTE_REVISAO',
        confianca='MEDIA',
        origem_classificacao='OCR_LOCAL',
        texto_extraido=texto,
        observacoes='Documento fiscal empresarial',
        hash_arquivo=f'hash-patrimonio-sugestao-{sufixo}',
    )
    db.session.add(comprovante)
    db.session.flush()
    return comprovante


def test_gerar_sugestao_para_documento_da_empresa(client, app):
    empresa = _trocar_perfil(client, 'Empresa')
    with app.app_context():
        comprovante = _comprovante(
            empresa['id'],
            'notebook',
            'Nota Fiscal numero 12854 Notebook Dell Latitude valor total 6490,00',
        )
        db.session.commit()
        comprovante_id = comprovante.id

    response = client.get(f'/api/patrimonio/bens/sugestao-a-partir-documento/{comprovante_id}')

    assert response.status_code == 200, response.get_data(as_text=True)
    sugestao = response.get_json()['data']
    assert sugestao['comprovante_id'] == comprovante_id
    assert sugestao['categoria'] == 'Informatica'
    assert sugestao['nome'].startswith('Notebook')
    assert sugestao['fornecedor'] == 'Dell Computadores do Brasil Ltda.'
    assert sugestao['data_aquisicao'] == '2026-05-05'
    assert sugestao['valor_aquisicao'] == 6490.0
    assert sugestao['vida_util_meses'] == 36
    assert sugestao['status_documental'] == 'COM_LASTRO'


def test_bloqueia_sugestao_no_perfil_pessoal(client, app):
    pessoal = _trocar_perfil(client, 'Pessoal')
    with app.app_context():
        comprovante = _comprovante(pessoal['id'], 'pessoal', 'Notebook pessoal')
        db.session.commit()
        comprovante_id = comprovante.id

    response = client.get(f'/api/patrimonio/bens/sugestao-a-partir-documento/{comprovante_id}')

    assert response.status_code == 403


def test_bloqueia_documento_de_outro_perfil(client, app):
    pessoal = _trocar_perfil(client, 'Pessoal')
    with app.app_context():
        comprovante = _comprovante(pessoal['id'], 'outro-perfil', 'Mesa de reuniao')
        db.session.commit()
        comprovante_id = comprovante.id

    _trocar_perfil(client, 'Empresa')
    response = client.get(f'/api/patrimonio/bens/sugestao-a-partir-documento/{comprovante_id}')

    assert response.status_code in {400, 403, 404}


@pytest.mark.parametrize(
    ('texto', 'categoria', 'vida_util'),
    [
        ('Compra de notebook computador monitor corporativo', 'Informatica', 36),
        ('Nota de cadeira ergonomica e mesa para escritorio', 'Moveis', 120),
        ('Ar-condicionado split com instalacao no escritorio', 'Estrutura', 120),
    ],
)
def test_heuristica_categoria_e_vida_util(client, app, texto, categoria, vida_util):
    empresa = _trocar_perfil(client, 'Empresa')
    with app.app_context():
        comprovante = _comprovante(empresa['id'], categoria, texto, valor='1200.00', prestador='Fornecedor Ltda.')
        db.session.commit()
        comprovante_id = comprovante.id

    sugestao = client.get(f'/api/patrimonio/bens/sugestao-a-partir-documento/{comprovante_id}').get_json()['data']

    assert sugestao['categoria'] == categoria
    assert sugestao['vida_util_meses'] == vida_util


def test_criar_bem_a_partir_da_sugestao_revisada_vincula_documento(client, app):
    empresa = _trocar_perfil(client, 'Empresa')
    with app.app_context():
        comprovante = _comprovante(
            empresa['id'],
            'cadeira',
            'Nota fiscal 54321 cadeira ergonomica para sala administrativa',
            valor='890.00',
            prestador='Moveis Office Ltda.',
        )
        db.session.commit()
        comprovante_id = comprovante.id

    sugestao = client.get(f'/api/patrimonio/bens/sugestao-a-partir-documento/{comprovante_id}').get_json()['data']
    payload = {
        **sugestao,
        'nome': 'Cadeira ergonomica revisada',
        'centro_custo': 'Administrativo',
        'localizacao': 'Escritorio - Sala 02',
        'responsavel': 'Equipe Administrativa',
    }
    response = client.post('/api/patrimonio/bens/criar-a-partir-documento', json=payload)

    assert response.status_code == 201, response.get_data(as_text=True)
    bem = response.get_json()['data']
    assert bem['nome'] == 'Cadeira ergonomica revisada'
    assert bem['status_documental'] == 'COM_LASTRO'
    assert bem['documento']['id'] == comprovante_id
    assert bem['depreciacao_mensal'] == 7.42
    with app.app_context():
        vinculo = IrComprovanteVinculo.query.filter_by(
            comprovante_id=comprovante_id,
            tipo_entidade='PATRIMONIO',
            entidade_id=bem['id'],
            ativo=True,
        ).first()
        assert vinculo is not None
        assert vinculo.natureza == 'PATRIMONIO_IMOBILIZADO'
        assert db.session.get(BemPatrimonial, bem['id']).status_documental == 'COM_LASTRO'


def test_documento_ja_vinculado_nao_cria_bem_duplicado(client, app):
    empresa = _trocar_perfil(client, 'Empresa')
    with app.app_context():
        comprovante = _comprovante(empresa['id'], 'duplicado', 'Impressora laser nota fiscal')
        db.session.commit()
        comprovante_id = comprovante.id

    payload = {
        'comprovante_id': comprovante_id,
        'nome': 'Impressora laser',
        'categoria': 'Informatica',
        'vida_util_meses': 36,
    }
    primeiro = client.post('/api/patrimonio/bens/criar-a-partir-documento', json=payload)
    segundo = client.post('/api/patrimonio/bens/criar-a-partir-documento', json={**payload, 'nome': 'Impressora duplicada'})
    sugestao = client.get(f'/api/patrimonio/bens/sugestao-a-partir-documento/{comprovante_id}').get_json()['data']

    assert primeiro.status_code == 201
    assert segundo.status_code == 400
    assert sugestao['bloqueado'] is True
    assert any('ja esta vinculado' in aviso for aviso in sugestao['avisos'])


def test_depreciacao_informativa_calculada_na_sugestao(client, app):
    empresa = _trocar_perfil(client, 'Empresa')
    with app.app_context():
        comprovante = _comprovante(empresa['id'], 'ar', 'Ar condicionado split', valor='5900.00')
        db.session.commit()
        comprovante_id = comprovante.id

    sugestao = client.get(f'/api/patrimonio/bens/sugestao-a-partir-documento/{comprovante_id}').get_json()['data']

    assert sugestao['categoria'] == 'Estrutura'
    assert sugestao['vida_util_meses'] == 120
    assert sugestao['depreciacao_mensal'] == 49.17


def test_frontend_contem_botao_e_modal_de_sugestao():
    template = Path('frontend/templates/imposto_renda.html').read_text(encoding='utf-8')
    patrimonio_js = Path('frontend/static/js/patrimonio.js').read_text(encoding='utf-8')

    assert 'Sugerir bem patrimonial' in template
    assert 'id="ir-sugestao-patrimonio-modal"' in template
    assert 'sugestao-a-partir-documento' in patrimonio_js
