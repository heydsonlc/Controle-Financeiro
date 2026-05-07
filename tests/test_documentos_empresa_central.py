from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from backend.app import create_app
from backend.models import DocumentoEmpresarialMetadata, IrComprovante, db
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


def _comprovante(perfil_id, sufixo='doc', data_documento=None):
    comprovante = IrComprovante(
        perfil_financeiro_id=perfil_id,
        ano_calendario=2026,
        data_documento=data_documento or date.today(),
        prestador_nome=f'Documento Empresa {sufixo}',
        prestador_cpf_cnpj='00000000000191',
        valor=Decimal('100.00'),
        status='PENDENTE_REVISAO',
        hash_arquivo=f'hash-doc-hub-{perfil_id}-{sufixo}',
    )
    db.session.add(comprovante)
    db.session.flush()
    return comprovante


def _put_metadata(client, comprovante_id, **extra):
    payload = {
        'tipo_documental': 'DOCUMENTO_OBRIGATORIO',
        'categoria_documental': 'CERTIFICADO_BOMBEIROS',
        'numero_documento': 'CB-2026',
        'orgao_emissor': 'Bombeiros',
        'data_emissao': date.today().isoformat(),
        'data_validade': (date.today() + timedelta(days=60)).isoformat(),
        'obrigatorio': True,
        'renovavel': True,
        'alerta_dias_antes': 30,
        'responsavel_interno': 'Administrativo',
        'observacoes': 'Controle gerencial',
    }
    payload.update(extra)
    return client.put(f'/api/ir/comprovantes/{comprovante_id}/metadata-empresarial', json=payload)


def test_perfil_pessoal_mantem_contexto_irpf(client):
    contexto = client.get('/api/ir/contexto')

    assert contexto.status_code == 200
    assert contexto.get_json()['data']['modo'] == 'IRPF'
    assert contexto.get_json()['data']['titulo'] == 'Imposto de Renda'


def test_perfil_empresa_retorna_contexto_documentos_da_empresa(client):
    _trocar_perfil(client, 'Empresa')

    contexto = client.get('/api/ir/contexto')

    assert contexto.status_code == 200
    data = contexto.get_json()['data']
    assert data['modo'] == 'DOCUMENTOS_FISCAIS_EMPRESA'
    assert data['titulo'] == 'Documentos da Empresa'
    assert data['central_documentos_empresa'] is True


def test_taxonomia_retorna_tipos_categorias_e_status(client):
    _trocar_perfil(client, 'Empresa')

    response = client.get('/api/ir/documentos-empresa/taxonomia')

    assert response.status_code == 200
    data = response.get_json()['data']
    tipos = {item['codigo'] for item in data['tipos_documentais']}
    categorias = {item['codigo'] for item in data['categorias_documentais']}
    status = {item['codigo'] for item in data['status_documentais']}
    assert 'DOCUMENTO_OBRIGATORIO' in tipos
    assert 'CONTRATO_SOCIAL' in categorias
    assert {'VALIDO', 'VENCENDO', 'VENCIDO'}.issubset(status)


def test_metadados_empresariais_podem_ser_criados_e_atualizados(client, app):
    empresa = _trocar_perfil(client, 'Empresa')
    with app.app_context():
        comprovante = _comprovante(empresa['id'], 'metadata')
        db.session.commit()
        comprovante_id = comprovante.id

    response = _put_metadata(client, comprovante_id)
    get_response = client.get(f'/api/ir/comprovantes/{comprovante_id}/metadata-empresarial')

    assert response.status_code == 200, response.get_data(as_text=True)
    assert response.get_json()['data']['categoria_documental'] == 'CERTIFICADO_BOMBEIROS'
    assert response.get_json()['data']['status_documental'] == 'VALIDO'
    assert get_response.get_json()['data']['numero_documento'] == 'CB-2026'
    with app.app_context():
        assert DocumentoEmpresarialMetadata.query.count() == 1


def test_status_validade_valido_vencendo_e_vencido(client, app):
    empresa = _trocar_perfil(client, 'Empresa')
    with app.app_context():
        valido = _comprovante(empresa['id'], 'valido')
        vencendo = _comprovante(empresa['id'], 'vencendo')
        vencido = _comprovante(empresa['id'], 'vencido')
        db.session.commit()
        ids = (valido.id, vencendo.id, vencido.id)

    r_valido = _put_metadata(client, ids[0], data_validade=(date.today() + timedelta(days=60)).isoformat())
    r_vencendo = _put_metadata(client, ids[1], data_validade=(date.today() + timedelta(days=10)).isoformat())
    r_vencido = _put_metadata(client, ids[2], data_validade=(date.today() - timedelta(days=1)).isoformat())

    assert r_valido.get_json()['data']['status_documental'] == 'VALIDO'
    assert r_vencendo.get_json()['data']['status_documental'] == 'VENCENDO'
    assert r_vencido.get_json()['data']['status_documental'] == 'VENCIDO'


def test_resumo_conta_obrigatorios_e_proximos_vencimentos(client, app):
    empresa = _trocar_perfil(client, 'Empresa')
    with app.app_context():
        comprovante = _comprovante(empresa['id'], 'resumo')
        db.session.commit()
        comprovante_id = comprovante.id

    _put_metadata(client, comprovante_id, data_validade=(date.today() + timedelta(days=10)).isoformat())
    response = client.get('/api/ir/documentos-empresa/resumo?ano=2026')

    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['documentos_obrigatorios'] == 1
    assert data['vencendo_30_dias'] == 1
    assert data['proximos_vencimentos'][0]['id'] == comprovante_id


def test_perfil_pessoal_nao_acessa_metadata_da_empresa(client, app):
    empresa = _trocar_perfil(client, 'Empresa')
    with app.app_context():
        comprovante = _comprovante(empresa['id'], 'isolamento')
        db.session.commit()
        comprovante_id = comprovante.id

    _trocar_perfil(client, 'Pessoal')
    response = client.get(f'/api/ir/comprovantes/{comprovante_id}/metadata-empresarial')

    assert response.status_code == 403


def test_listagem_filtra_por_tipo_documental(client, app):
    empresa = _trocar_perfil(client, 'Empresa')
    with app.app_context():
        obrigatorio = _comprovante(empresa['id'], 'obrigatorio')
        pagamento = _comprovante(empresa['id'], 'pagamento')
        db.session.commit()
        ids = (obrigatorio.id, pagamento.id)

    _put_metadata(client, ids[0], tipo_documental='DOCUMENTO_OBRIGATORIO', categoria_documental='ALVARA_FUNCIONAMENTO')
    _put_metadata(client, ids[1], tipo_documental='PAGAMENTO_REALIZADO', categoria_documental='PIX_PAGO')

    response = client.get('/api/ir/comprovantes?ano=2026&tipo_documental=DOCUMENTO_OBRIGATORIO')

    assert response.status_code == 200
    data = response.get_json()
    assert data['total'] == 1
    assert data['data'][0]['tipo_documental'] == 'DOCUMENTO_OBRIGATORIO'


def test_ui_contem_abas_kpis_e_fluxos_existentes():
    template = Path('frontend/templates/imposto_renda.html').read_text(encoding='utf-8')
    js = Path('frontend/static/js/imposto_renda.js').read_text(encoding='utf-8')

    assert 'ir-doc-tabs' in template
    assert 'Documentos obrigatorios' in template
    assert 'Filtros avancados' in template
    assert 'Vencendo em 30 dias' in js
    assert 'ir-review-metadata-block' in template
    assert 'Gerar sugestao financeira' in template
    assert 'Sugerir bem patrimonial' in template
    assert 'metadata-empresarial' in js
    assert 'documentos-empresa/taxonomia' in js


def test_fluxos_antigos_de_saidas_sem_documento_continuam_na_tela():
    template = Path('frontend/templates/imposto_renda.html').read_text(encoding='utf-8')

    assert 'ir-saidas-sem-documento-panel' in template
    assert 'Exportar Excel' in template
    assert 'Gerar relat&oacute;rio em PDF' in template
    assert 'data-ir-icon="report-pdf"' in template
