"""
Testes DOC-SHORTCUTS-1 — atalhos "A partir de documento" em Lançamentos e Despesas.
"""
import io

import pytest

from backend.app import create_app
from backend.models import (
    IrComprovante,
    IrComprovanteVinculo,
    db,
)
from backend.services.ir_documento_service import IrDocumentoService
from backend.services.perfil_financeiro_service import PerfilFinanceiroService
from tests.conftest import autenticar_cliente_teste


TEXTO_CUPOM = (
    'SUPERMERCADO VALE VERDE LTDA\n'
    'CNPJ: 12.345.678/0001-90\n'
    'NFC-e - Nota Fiscal de Consumidor Eletronica\n'
    'Emissao: 05/05/2026  10:34:22\n'
    'Valor Total   R$ 145,80\n'
    'Chave de acesso: 52260512345678000190650010000012341234567891\n'
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


def _fazer_upload(client):
    return client.post(
        '/api/ir/comprovantes/upload',
        data={'ano_calendario': '2026', 'arquivos': (_pdf_cupom(), 'nota.pdf', 'application/pdf')},
        content_type='multipart/form-data',
    )


# ---------------------------------------------------------------------------
# 1. Endpoint documentos-para-financeiro retorna lista
# ---------------------------------------------------------------------------
def test_endpoint_documentos_para_financeiro_retorna_lista(app_context, monkeypatch):
    monkeypatch.setattr(IrDocumentoService, 'extrair_texto_pdf', staticmethod(lambda _: TEXTO_CUPOM))

    with app_context.test_client() as client:
        autenticar_cliente_teste(client, app_context)
        _fazer_upload(client)
        r = client.get('/api/ir/comprovantes/documentos-para-financeiro')

    assert r.status_code == 200
    dados = r.get_json()
    assert dados['success'] is True
    assert isinstance(dados['data'], list)
    assert len(dados['data']) == 1


# ---------------------------------------------------------------------------
# 2. Endpoint retorna campos minimos esperados
# ---------------------------------------------------------------------------
def test_endpoint_retorna_campos_minimos(app_context, monkeypatch):
    monkeypatch.setattr(IrDocumentoService, 'extrair_texto_pdf', staticmethod(lambda _: TEXTO_CUPOM))

    with app_context.test_client() as client:
        autenticar_cliente_teste(client, app_context)
        _fazer_upload(client)
        r = client.get('/api/ir/comprovantes/documentos-para-financeiro')

    doc = r.get_json()['data'][0]
    for campo in ('id', 'prestador_nome', 'valor', 'data_documento', 'vinculos_count'):
        assert campo in doc, f'Campo ausente: {campo}'


# ---------------------------------------------------------------------------
# 3. Filtro sem_vinculo exclui documentos ja vinculados
# ---------------------------------------------------------------------------
def test_filtro_sem_vinculo_exclui_vinculados(app_context, monkeypatch):
    monkeypatch.setattr(IrDocumentoService, 'extrair_texto_pdf', staticmethod(lambda _: TEXTO_CUPOM))

    with app_context.test_client() as client:
        autenticar_cliente_teste(client, app_context)
        _fazer_upload(client)
        comp = IrComprovante.query.one()

        # Criar vinculo manualmente
        vinculo = IrComprovanteVinculo(
            comprovante_id=comp.id,
            tipo_entidade='DESPESA',
            entidade_id=1,
            natureza='DESPESA_OPERACIONAL',
            status_lastro='PENDENTE',
            ativo=True,
        )
        db.session.add(vinculo)
        db.session.commit()

        r = client.get('/api/ir/comprovantes/documentos-para-financeiro?sem_vinculo=true')

    assert r.status_code == 200
    assert len(r.get_json()['data']) == 0


# ---------------------------------------------------------------------------
# 4. Filtro sem_vinculo=false inclui documentos vinculados
# ---------------------------------------------------------------------------
def test_filtro_sem_vinculo_false_inclui_vinculados(app_context, monkeypatch):
    monkeypatch.setattr(IrDocumentoService, 'extrair_texto_pdf', staticmethod(lambda _: TEXTO_CUPOM))

    with app_context.test_client() as client:
        autenticar_cliente_teste(client, app_context)
        _fazer_upload(client)
        comp = IrComprovante.query.one()
        vinculo = IrComprovanteVinculo(
            comprovante_id=comp.id,
            tipo_entidade='DESPESA',
            entidade_id=1,
            natureza='DESPESA_OPERACIONAL',
            status_lastro='PENDENTE',
            ativo=True,
        )
        db.session.add(vinculo)
        db.session.commit()

        r = client.get('/api/ir/comprovantes/documentos-para-financeiro?sem_vinculo=false')

    assert r.status_code == 200
    assert len(r.get_json()['data']) == 1


# ---------------------------------------------------------------------------
# 5. Sugestao financeira retorna dados enriquecidos com cupom
# ---------------------------------------------------------------------------
def test_sugestao_financeira_enriquecida_com_cupom(app_context, monkeypatch):
    monkeypatch.setattr(IrDocumentoService, 'extrair_texto_pdf', staticmethod(lambda _: TEXTO_CUPOM))

    with app_context.test_client() as client:
        autenticar_cliente_teste(client, app_context)
        _fazer_upload(client)
        comp = IrComprovante.query.one()
        r = client.get(f'/api/ir/comprovantes/{comp.id}/sugestao-financeira')

    assert r.status_code == 200
    sugestao = r.get_json()['data']
    assert sugestao['valor'] == 145.80
    assert 'opcoes' in sugestao
    assert 'categorias_despesa' in sugestao['opcoes']


# ---------------------------------------------------------------------------
# 6. Criar lancamento a partir de documento cria vinculo
# ---------------------------------------------------------------------------
def test_criar_lancamento_a_partir_documento_cria_vinculo(app_context, monkeypatch):
    monkeypatch.setattr(IrDocumentoService, 'extrair_texto_pdf', staticmethod(lambda _: TEXTO_CUPOM))

    with app_context.test_client() as client:
        autenticar_cliente_teste(client, app_context)
        _fazer_upload(client)
        comp = IrComprovante.query.one()

        r = client.post(
            f'/api/ir/comprovantes/{comp.id}/criar-financeiro',
            json={
                'tipo_destino': 'LANCAMENTO',
                'descricao': 'Compra supermercado',
                'valor': 145.80,
                'data': '2026-05-05',
                'competencia': '2026-05',
                'forma_pagamento': 'pix',
            },
        )

    assert r.status_code == 201
    comp = IrComprovante.query.one()
    assert comp.vinculos.filter_by(ativo=True).count() == 1
    vinculo = comp.vinculos.filter_by(ativo=True).first()
    # tipo_destino=LANCAMENTO sem cartao cria Conta (pago=True); via cartao cria LANCAMENTO
    assert vinculo.tipo_entidade in ('LANCAMENTO', 'CONTA')


# ---------------------------------------------------------------------------
# 7. Criar despesa a partir de documento cria vinculo
# ---------------------------------------------------------------------------
def test_criar_despesa_a_partir_documento_cria_vinculo(app_context, monkeypatch):
    monkeypatch.setattr(IrDocumentoService, 'extrair_texto_pdf', staticmethod(lambda _: TEXTO_CUPOM))

    with app_context.test_client() as client:
        autenticar_cliente_teste(client, app_context)
        _fazer_upload(client)
        comp = IrComprovante.query.one()

        r = client.post(
            f'/api/ir/comprovantes/{comp.id}/criar-financeiro',
            json={
                'tipo_destino': 'DESPESA',
                'descricao': 'Compra supermercado',
                'valor': 145.80,
                'data': '2026-05-05',
                'competencia': '2026-05',
                'forma_pagamento': 'outros',
            },
        )

    assert r.status_code == 201
    comp = IrComprovante.query.one()
    assert comp.vinculos.filter_by(ativo=True).count() == 1
    vinculo = comp.vinculos.filter_by(ativo=True).first()
    # tipo_destino=DESPESA sempre usa _criar_conta_operacional (pago=False) -> CONTA
    assert vinculo.tipo_entidade == 'CONTA'


# ---------------------------------------------------------------------------
# 8. Evento LANCAMENTO_CRIADO_A_PARTIR_DOCUMENTO e registrado
# ---------------------------------------------------------------------------
def test_evento_lancamento_criado_registrado(app_context, monkeypatch):
    monkeypatch.setattr(IrDocumentoService, 'extrair_texto_pdf', staticmethod(lambda _: TEXTO_CUPOM))

    with app_context.test_client() as client:
        autenticar_cliente_teste(client, app_context)
        _fazer_upload(client)
        comp = IrComprovante.query.one()
        client.post(
            f'/api/ir/comprovantes/{comp.id}/criar-financeiro',
            json={'tipo_destino': 'LANCAMENTO', 'descricao': 'x', 'valor': 10, 'data': '2026-05-05', 'competencia': '2026-05', 'forma_pagamento': 'pix'},
        )

    comp = IrComprovante.query.one()
    tipos = {e.tipo_evento for e in comp.eventos.all()}
    assert 'LANCAMENTO_CRIADO_A_PARTIR_DOCUMENTO' in tipos


# ---------------------------------------------------------------------------
# 9. Evento DESPESA_CRIADA_A_PARTIR_DOCUMENTO e registrado
# ---------------------------------------------------------------------------
def test_evento_despesa_criada_registrado(app_context, monkeypatch):
    monkeypatch.setattr(IrDocumentoService, 'extrair_texto_pdf', staticmethod(lambda _: TEXTO_CUPOM))

    with app_context.test_client() as client:
        autenticar_cliente_teste(client, app_context)
        _fazer_upload(client)
        comp = IrComprovante.query.one()
        client.post(
            f'/api/ir/comprovantes/{comp.id}/criar-financeiro',
            json={'tipo_destino': 'DESPESA', 'descricao': 'x', 'valor': 10, 'data': '2026-05-05', 'competencia': '2026-05', 'forma_pagamento': 'outros'},
        )

    comp = IrComprovante.query.one()
    tipos = {e.tipo_evento for e in comp.eventos.all()}
    assert 'DESPESA_CRIADA_A_PARTIR_DOCUMENTO' in tipos


# ---------------------------------------------------------------------------
# 10. tipo_destino invalido retorna erro 400
# ---------------------------------------------------------------------------
def test_tipo_destino_invalido_retorna_erro(app_context, monkeypatch):
    monkeypatch.setattr(IrDocumentoService, 'extrair_texto_pdf', staticmethod(lambda _: TEXTO_CUPOM))

    with app_context.test_client() as client:
        autenticar_cliente_teste(client, app_context)
        _fazer_upload(client)
        comp = IrComprovante.query.one()
        r = client.post(
            f'/api/ir/comprovantes/{comp.id}/criar-financeiro',
            json={'tipo_destino': 'INVALIDO', 'descricao': 'x', 'valor': 10},
        )

    assert r.status_code == 400


# ---------------------------------------------------------------------------
# 11. Documento de outro perfil nao aparece na listagem
# ---------------------------------------------------------------------------
def test_documento_de_outro_perfil_nao_aparece(app_context, monkeypatch):
    monkeypatch.setattr(IrDocumentoService, 'extrair_texto_pdf', staticmethod(lambda _: TEXTO_CUPOM))

    with app_context.test_client() as client:
        autenticar_cliente_teste(client, app_context)
        perfis = client.get('/api/perfis-financeiros').get_json()['perfis']
        empresa = next(p for p in perfis if p['nome'] == 'Empresa')
        pessoal = next(p for p in perfis if p['nome'] == 'Pessoal')

        client.post('/api/perfis-financeiros/ativo', json={'perfil_id': empresa['id']})
        _fazer_upload(client)

        client.post('/api/perfis-financeiros/ativo', json={'perfil_id': pessoal['id']})
        r = client.get('/api/ir/comprovantes/documentos-para-financeiro')

    assert r.status_code == 200
    assert len(r.get_json()['data']) == 0


# ---------------------------------------------------------------------------
# 12. vinculos_count reflete numero correto de vinculos ativos
# ---------------------------------------------------------------------------
def test_vinculos_count_reflete_vinculos_ativos(app_context, monkeypatch):
    monkeypatch.setattr(IrDocumentoService, 'extrair_texto_pdf', staticmethod(lambda _: TEXTO_CUPOM))

    with app_context.test_client() as client:
        autenticar_cliente_teste(client, app_context)
        _fazer_upload(client)
        comp = IrComprovante.query.one()

        # Criar dois vinculos: um ativo, um inativo
        db.session.add(IrComprovanteVinculo(
            comprovante_id=comp.id, tipo_entidade='DESPESA', entidade_id=1,
            natureza='DESPESA_OPERACIONAL', status_lastro='PENDENTE', ativo=True,
        ))
        db.session.add(IrComprovanteVinculo(
            comprovante_id=comp.id, tipo_entidade='DESPESA', entidade_id=2,
            natureza='DESPESA_OPERACIONAL', status_lastro='PENDENTE', ativo=False,
        ))
        db.session.commit()

        r = client.get('/api/ir/comprovantes/documentos-para-financeiro')

    doc = r.get_json()['data'][0]
    assert doc['vinculos_count'] == 1


# ---------------------------------------------------------------------------
# 13. Filtro busca por nome do prestador
# ---------------------------------------------------------------------------
def test_filtro_busca_por_nome_prestador(app_context, monkeypatch):
    monkeypatch.setattr(IrDocumentoService, 'extrair_texto_pdf', staticmethod(lambda _: TEXTO_CUPOM))

    with app_context.test_client() as client:
        autenticar_cliente_teste(client, app_context)
        _fazer_upload(client)
        r_match = client.get('/api/ir/comprovantes/documentos-para-financeiro?busca=VALE+VERDE')
        r_no_match = client.get('/api/ir/comprovantes/documentos-para-financeiro?busca=INEXISTENTE')

    assert len(r_match.get_json()['data']) == 1
    assert len(r_no_match.get_json()['data']) == 0


# ---------------------------------------------------------------------------
# 14. Sugestao para documento inexistente retorna 404
# ---------------------------------------------------------------------------
def test_sugestao_documento_inexistente_retorna_404(app_context):
    with app_context.test_client() as client:
        autenticar_cliente_teste(client, app_context)
        r = client.get('/api/ir/comprovantes/99999/sugestao-financeira')

    assert r.status_code == 404
