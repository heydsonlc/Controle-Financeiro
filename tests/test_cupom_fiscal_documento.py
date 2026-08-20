"""
Testes CUPOM-FISCAL-1 — integracao de cupom fiscal no pipeline de documentos.
"""
import io

import pytest

from backend.app import create_app
from backend.models import (
    Categoria,
    CategoriaPalavraChave,
    IrCategoria,
    IrCategoriaDespesa,
    IrComprovante,
    db,
)
from backend.services.ir_documento_service import IrDocumentoService
from backend.services.ocr_service import OcrService
from backend.services.perfil_financeiro_service import PerfilFinanceiroService
from tests.conftest import autenticar_cliente_teste


TEXTO_CUPOM = (
    'SUPERMERCADO VALE VERDE LTDA\n'
    'CNPJ: 12.345.678/0001-90\n'
    'Rua das Flores, 100\n'
    'NFC-e - Nota Fiscal de Consumidor Eletronica\n'
    'Emissao: 05/05/2026  10:34:22\n'
    'Valor Total   R$ 145,80\n'
    'Chave de acesso: 52260512345678000190650010000012341234567891\n'
    'QRCode: https://nfce.sefaz.example/\n'
    'supermercado mercado compra produtos alimenticios\n'
)


@pytest.fixture()
def app_context():
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        PerfilFinanceiroService.obter_ou_criar_perfis_iniciais()
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


def _pdf_cupom():
    return io.BytesIO(b'%PDF-1.4\n' + TEXTO_CUPOM.encode('utf-8'))


def _png_cupom():
    return io.BytesIO(b'\x89PNG\r\n\x1a\n' + b'\x00' * 64)


def _ocr_sucesso(texto=TEXTO_CUPOM):
    return {'sucesso': True, 'texto': texto, 'origem': 'ocr', 'paginas_processadas': 1, 'avisos': [], 'erro': None}


def _criar_categoria_mercado():
    cat = Categoria(nome='Supermercado', descricao='Compras de mercado', ativo=True)
    palavra = CategoriaPalavraChave(categoria=cat, palavra='mercado', ativo=True)
    ir = IrCategoria(nome='Despesa operacional', descricao='Despesas operacionais', dedutivel=False, ativo=True, ordem=10, tipo_contexto='EMPRESA', natureza='DESPESA_OPERACIONAL')
    db.session.add_all([cat, palavra, ir])
    db.session.flush()
    vinculo = IrCategoriaDespesa(categoria_id=cat.id, categoria_ir_id=ir.id, ativo=True)
    db.session.add(vinculo)
    db.session.commit()
    return cat, ir


# ---------------------------------------------------------------------------
# 1. Upload com texto de cupom detecta cupom (via PDF textual)
# ---------------------------------------------------------------------------
def test_upload_pdf_com_texto_cupom_detecta_cupom(app_context, monkeypatch):
    monkeypatch.setattr(IrDocumentoService, 'extrair_texto_pdf', staticmethod(lambda _: TEXTO_CUPOM))

    with app_context.test_client() as client:
        autenticar_cliente_teste(client, app_context)
        r = client.post(
            '/api/ir/comprovantes/upload',
            data={'ano_calendario': '2026', 'arquivos': (_pdf_cupom(), 'cupom.pdf', 'application/pdf')},
            content_type='multipart/form-data',
        )

    assert r.status_code == 200
    comp = IrComprovante.query.one()
    tipos = {e.tipo_evento for e in comp.eventos.all()}
    assert 'CUPOM_FISCAL_DETECTADO' in tipos


# ---------------------------------------------------------------------------
# 2. IrComprovante recebe prestador / data / valor do cupom
# ---------------------------------------------------------------------------
def test_comprovante_recebe_dados_do_cupom(app_context, monkeypatch):
    monkeypatch.setattr(IrDocumentoService, 'extrair_texto_pdf', staticmethod(lambda _: TEXTO_CUPOM))

    with app_context.test_client() as client:
        autenticar_cliente_teste(client, app_context)
        client.post(
            '/api/ir/comprovantes/upload',
            data={'ano_calendario': '2026', 'arquivos': (_pdf_cupom(), 'cupom.pdf', 'application/pdf')},
            content_type='multipart/form-data',
        )

    comp = IrComprovante.query.one()
    assert comp.prestador_nome is not None
    assert 'VALE VERDE' in (comp.prestador_nome or '').upper() or 'SUPERMERCADO' in (comp.prestador_nome or '').upper()
    assert comp.prestador_cpf_cnpj == '12.345.678/0001-90'
    assert comp.valor is not None
    assert float(comp.valor) == 145.80
    assert comp.data_documento is not None
    assert comp.data_documento.year == 2026


# ---------------------------------------------------------------------------
# 3. Evento CUPOM_FISCAL_DETECTADO e registrado
# ---------------------------------------------------------------------------
def test_evento_cupom_fiscal_detectado_registrado(app_context, monkeypatch):
    monkeypatch.setattr(IrDocumentoService, 'extrair_texto_pdf', staticmethod(lambda _: TEXTO_CUPOM))

    with app_context.test_client() as client:
        autenticar_cliente_teste(client, app_context)
        client.post(
            '/api/ir/comprovantes/upload',
            data={'ano_calendario': '2026', 'arquivos': (_pdf_cupom(), 'cupom.pdf', 'application/pdf')},
            content_type='multipart/form-data',
        )

    comp = IrComprovante.query.one()
    tipos = [e.tipo_evento for e in comp.eventos.all()]
    assert 'CUPOM_FISCAL_DETECTADO' in tipos
    assert 'CUPOM_FISCAL_EXTRAIDO' in tipos


# ---------------------------------------------------------------------------
# 4. Sugestao financeira usa dados do cupom
# ---------------------------------------------------------------------------
def test_sugestao_financeira_usa_dados_do_cupom(app_context, monkeypatch):
    monkeypatch.setattr(IrDocumentoService, 'extrair_texto_pdf', staticmethod(lambda _: TEXTO_CUPOM))

    with app_context.test_client() as client:
        autenticar_cliente_teste(client, app_context)
        client.post(
            '/api/ir/comprovantes/upload',
            data={'ano_calendario': '2026', 'arquivos': (_pdf_cupom(), 'cupom.pdf', 'application/pdf')},
            content_type='multipart/form-data',
        )
        comp = IrComprovante.query.one()
        r = client.get(f'/api/ir/comprovantes/{comp.id}/sugestao-financeira')

    assert r.status_code == 200
    sugestao = r.get_json()['data']
    assert sugestao['valor'] == 145.80
    assert sugestao['fornecedor'] is not None
    assert 'Cupom fiscal' in sugestao['descricao']


# ---------------------------------------------------------------------------
# 5. Categoria por palavra-chave e aplicada ao cupom
# ---------------------------------------------------------------------------
def test_categoria_por_palavra_chave_e_aplicada(app_context, monkeypatch):
    with app_context.app_context():
        cat, ir = _criar_categoria_mercado()
        cat_id = cat.id

    monkeypatch.setattr(IrDocumentoService, 'extrair_texto_pdf', staticmethod(lambda _: TEXTO_CUPOM))

    with app_context.test_client() as client:
        autenticar_cliente_teste(client, app_context)
        client.post(
            '/api/ir/comprovantes/upload',
            data={'ano_calendario': '2026', 'arquivos': (_pdf_cupom(), 'cupom2.pdf', 'application/pdf')},
            content_type='multipart/form-data',
        )

    comp = IrComprovante.query.order_by(IrComprovante.id.desc()).first()
    assert comp.categoria_id == cat_id


# ---------------------------------------------------------------------------
# 6. Documento nao e validado automaticamente
# ---------------------------------------------------------------------------
def test_documento_nao_e_validado_automaticamente(app_context, monkeypatch):
    monkeypatch.setattr(IrDocumentoService, 'extrair_texto_pdf', staticmethod(lambda _: TEXTO_CUPOM))

    with app_context.test_client() as client:
        autenticar_cliente_teste(client, app_context)
        client.post(
            '/api/ir/comprovantes/upload',
            data={'ano_calendario': '2026', 'arquivos': (_pdf_cupom(), 'cupom.pdf', 'application/pdf')},
            content_type='multipart/form-data',
        )

    comp = IrComprovante.query.one()
    assert comp.status != 'VALIDADO'


# ---------------------------------------------------------------------------
# 7. Sem categoria gera aviso, nao erro
# ---------------------------------------------------------------------------
def test_sem_categoria_gera_aviso_nao_erro(app_context, monkeypatch):
    monkeypatch.setattr(IrDocumentoService, 'extrair_texto_pdf', staticmethod(lambda _: TEXTO_CUPOM))

    with app_context.test_client() as client:
        autenticar_cliente_teste(client, app_context)
        r_upload = client.post(
            '/api/ir/comprovantes/upload',
            data={'ano_calendario': '2026', 'arquivos': (_pdf_cupom(), 'cupom.pdf', 'application/pdf')},
            content_type='multipart/form-data',
        )
        assert r_upload.status_code == 200
        comp = IrComprovante.query.one()
        r_sug = client.get(f'/api/ir/comprovantes/{comp.id}/sugestao-financeira')

    assert r_sug.status_code == 200
    data = r_sug.get_json()['data']
    # Pode ter aviso sobre categoria, mas nao deve retornar erro HTTP
    if comp.categoria_id is None:
        assert any('Categoria' in a for a in data.get('avisos', []))


# ---------------------------------------------------------------------------
# 8. Perfil Empresa — upload fica isolado no perfil
# ---------------------------------------------------------------------------
def test_perfil_empresa_mantem_isolamento(app_context, monkeypatch):
    monkeypatch.setattr(IrDocumentoService, 'extrair_texto_pdf', staticmethod(lambda _: TEXTO_CUPOM))

    with app_context.test_client() as client:
        autenticar_cliente_teste(client, app_context)
        perfis = client.get('/api/perfis-financeiros').get_json()['perfis']
        empresa = next(p for p in perfis if p['nome'] == 'Empresa')
        pessoal = next(p for p in perfis if p['nome'] == 'Pessoal')

        client.post('/api/perfis-financeiros/ativo', json={'perfil_id': empresa['id']})
        client.post(
            '/api/ir/comprovantes/upload',
            data={'ano_calendario': '2026', 'arquivos': (_pdf_cupom(), 'cupom.pdf', 'application/pdf')},
            content_type='multipart/form-data',
        )
        comp_empresa = IrComprovante.query.one()

        client.post('/api/perfis-financeiros/ativo', json={'perfil_id': pessoal['id']})
        r = client.get(f'/api/ir/comprovantes/{comp_empresa.id}')

    assert r.status_code == 404


# ---------------------------------------------------------------------------
# 9. Frontend contém bloco "Cupom fiscal detectado" no HTML
# ---------------------------------------------------------------------------
def test_frontend_contem_bloco_cupom_fiscal_detectado(app_context):
    from flask import render_template
    with app_context.test_request_context():
        html = render_template('imposto_renda.html', active_page='imposto_renda', page_title='Imposto de Renda')
    assert 'ir-cupom-fiscal-bloco' in html
    assert 'Cupom fiscal detectado' in html


# ---------------------------------------------------------------------------
# 10. OCR reprocessado reaplica parser de cupom
# ---------------------------------------------------------------------------
def test_ocr_reprocessado_reaplica_parser_cupom(app_context, monkeypatch):
    # Upload sem cupom inicialmente
    texto_inicial = '%PDF-1.4 generico sem dados suficientes'
    monkeypatch.setattr(IrDocumentoService, 'extrair_texto_pdf', staticmethod(lambda _: texto_inicial))

    with app_context.test_client() as client:
        autenticar_cliente_teste(client, app_context)
        client.post(
            '/api/ir/comprovantes/upload',
            data={'ano_calendario': '2026', 'arquivos': (_pdf_cupom(), 'cupom.pdf', 'application/pdf')},
            content_type='multipart/form-data',
        )
        comp = IrComprovante.query.one()
        tipos_antes = {e.tipo_evento for e in comp.eventos.all()}
        assert 'CUPOM_FISCAL_DETECTADO' not in tipos_antes

        # Reprocessa OCR — agora retorna texto com cupom
        monkeypatch.setattr(OcrService, 'executar_ocr_documento', staticmethod(lambda *a, **k: _ocr_sucesso()))
        r = client.post(f'/api/ir/comprovantes/{comp.id}/reprocessar-ocr')

    assert r.status_code == 200
    comp = IrComprovante.query.one()
    tipos_depois = {e.tipo_evento for e in comp.eventos.all()}
    assert 'CUPOM_FISCAL_DETECTADO' in tipos_depois
    assert float(comp.valor) == 145.80
