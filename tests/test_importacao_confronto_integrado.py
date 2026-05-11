"""
Testes IMPORT-TRIAGEM-2: confronto integrado como etapa padrão do pipeline.
"""
from datetime import date
import io

import pytest
from flask import Flask

from backend.models import (
    Categoria,
    CategoriaCartao,
    ConfigAgregador,
    ItemDespesa,
    LancamentoAgregado,
    db,
)
from backend.routes.importacao_cartao import bp as importacao_cartao_bp
from backend.services.categoria_cartao_service import CategoriaCartaoService
from backend.services.importacao_cartao_unificado_service import ImportacaoCartaoUnificadoService


@pytest.fixture()
def app_context():
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    app.register_blueprint(importacao_cartao_bp)

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def _base_cartao():
    combustivel = Categoria(nome='Combustivel', ativo=True)
    cartao = ItemDespesa(nome='Cartao Teste', tipo='Agregador', ativo=True, recorrente=True)
    db.session.add_all([combustivel, cartao])
    db.session.flush()
    db.session.add(ConfigAgregador(
        item_despesa_id=cartao.id,
        dia_fechamento=25,
        dia_vencimento=5,
    ))
    db.session.commit()
    return combustivel, cartao


def _categoria_cartao_vinculada(cartao, categoria, nome='Mobilidade'):
    cc = CategoriaCartaoService.criar_categoria(nome=nome, cor='#2563eb')
    db.session.commit()
    CategoriaCartaoService.vincular_categoria_despesa(cc.id, categoria.id)
    CategoriaCartaoService.vincular_categoria_cartao_ao_cartao(cartao.id, cc.id, limite_mensal='2000.00')
    db.session.commit()
    return cc


def _linha(descricao='POSTO SHELL', valor='66.90', categoria_id=None):
    return {
        'data_compra': '2026-05-01',
        'descricao': descricao,
        'descricao_original': descricao,
        'descricao_exibida': descricao,
        'valor': valor,
        'parcela': '1/1',
        'categoria_id': categoria_id,
    }


def _pipeline(cartao, linhas):
    competencia = date(2026, 5, 1)
    normalizadas = ImportacaoCartaoUnificadoService.normalizar_linhas(linhas, 'csv', cartao.id)
    ImportacaoCartaoUnificadoService.aplicar_sugestoes_categoria(normalizadas, cartao)
    ImportacaoCartaoUnificadoService.validar_linhas(normalizadas, cartao, competencia)
    ImportacaoCartaoUnificadoService.executar_confronto_linhas(normalizadas, cartao.id, competencia)
    ImportacaoCartaoUnificadoService.resolver_categoria_cartao_linhas(normalizadas, cartao)
    ImportacaoCartaoUnificadoService.enriquecer_classificacao(normalizadas, cartao, competencia)
    return normalizadas


def _csv_upload(descricao='POSTO SHELL', valor='66.90'):
    csv = f'date,title,amount\n2026-05-01,{descricao},{valor}\n'
    return io.BytesIO(csv.encode('utf-8'))


def test_linha_sem_historico_recebe_sem_match(app_context):
    """Linha nova sem histórico deve ter reconhecimento_status='sem_match'."""
    _combustivel, cartao = _base_cartao()

    normalizadas = ImportacaoCartaoUnificadoService.normalizar_linhas([_linha()], 'csv', cartao.id)
    ImportacaoCartaoUnificadoService.executar_confronto_linhas(normalizadas, cartao.id, date(2026, 5, 1))

    linha = normalizadas[0]
    assert linha['reconhecimento_status'] == 'sem_match'
    assert linha['reconhecimento_score'] is None
    assert linha['reconhecimento_match'] is None
    assert linha['reconhecimento_acao_recomendada'] == 'despesa_avulsa'


def test_linha_ignorada_nao_e_processada_no_confronto(app_context):
    """Linhas ignoradas (crédito) não devem ter campos reconhecimento_* preenchidos."""
    _combustivel, cartao = _base_cartao()

    linha_credito = dict(_linha(), tipo_movimento='credito')
    normalizadas = ImportacaoCartaoUnificadoService.normalizar_linhas([linha_credito], 'csv', cartao.id)
    ImportacaoCartaoUnificadoService.validar_linhas(normalizadas, cartao, date(2026, 5, 1))
    ImportacaoCartaoUnificadoService.executar_confronto_linhas(normalizadas, cartao.id, date(2026, 5, 1))

    linha = normalizadas[0]
    assert linha.get('status') == 'ignorado'
    assert linha.get('reconhecimento_status') is None


def test_linha_duplicada_nao_e_processada_no_confronto(app_context):
    """Linhas duplicadas (status='duplicado') são puladas pelo confronto."""
    combustivel, cartao = _base_cartao()
    _categoria_cartao_vinculada(cartao, combustivel)

    payload = {
        'cartao_id': cartao.id,
        'competencia': '2026-05-01',
        'linhas': [dict(_linha(), categoria_id=combustivel.id)],
    }
    with app_context.test_client() as client:
        client.post('/api/importacao-cartao/processar', json=payload)

    normalizadas = ImportacaoCartaoUnificadoService.normalizar_linhas([_linha()], 'csv', cartao.id)
    ImportacaoCartaoUnificadoService.validar_linhas(normalizadas, cartao, date(2026, 5, 1))
    ImportacaoCartaoUnificadoService.executar_confronto_linhas(normalizadas, cartao.id, date(2026, 5, 1))

    linha = normalizadas[0]
    assert linha.get('status') == 'duplicado'
    assert linha.get('reconhecimento_status') is None


def test_confronto_com_historico_retorna_match(app_context):
    """Linha com histórico exato no banco deve retornar reconhecimento_status preenchido."""
    combustivel, cartao = _base_cartao()
    _categoria_cartao_vinculada(cartao, combustivel)

    from decimal import Decimal
    lancamento = LancamentoAgregado(
        cartao_id=cartao.id,
        mes_fatura=date(2026, 4, 1),
        data_compra=date(2026, 4, 10),
        descricao='POSTO SHELL',
        descricao_original='POSTO SHELL',
        valor=Decimal('66.90'),
        numero_parcela=1,
        total_parcelas=1,
        categoria_id=combustivel.id,
    )
    db.session.add(lancamento)
    db.session.commit()

    normalizadas = ImportacaoCartaoUnificadoService.normalizar_linhas([_linha()], 'csv', cartao.id)
    ImportacaoCartaoUnificadoService.executar_confronto_linhas(normalizadas, cartao.id, date(2026, 5, 1))

    linha = normalizadas[0]
    assert linha['reconhecimento_status'] != 'sem_match'
    assert linha['reconhecimento_score'] is not None
    assert linha['reconhecimento_score'] >= 60
    assert linha['reconhecimento_match'] is not None
    assert linha['reconhecimento_candidato_id'] == lancamento.id


def test_confronto_nao_quebra_pipeline_sem_banco(app_context):
    """executar_confronto_linhas não deve lançar exceção mesmo sem dados no banco."""
    _combustivel, cartao = _base_cartao()

    normalizadas = ImportacaoCartaoUnificadoService.normalizar_linhas(
        [_linha('LOJA SEM HISTORICO')], 'csv', cartao.id
    )
    result = ImportacaoCartaoUnificadoService.executar_confronto_linhas(
        normalizadas, cartao.id, date(2026, 5, 1)
    )
    assert result is normalizadas
    assert normalizadas[0]['reconhecimento_status'] == 'sem_match'


def test_analisar_retorna_confronto_executado_true(app_context):
    """Endpoint /analisar deve retornar confronto_executado=True."""
    _combustivel, cartao = _base_cartao()
    csv = b'date,title,amount\n2026-05-01,POSTO SHELL,66.90\n'

    with app_context.test_client() as client:
        response = client.post(
            '/api/importacao-cartao/analisar',
            data={
                'arquivo': (io.BytesIO(csv), 'fatura.csv'),
                'cartao_id': str(cartao.id),
                'competencia': '2026-05',
                'formato': 'csv',
            },
            content_type='multipart/form-data',
        )

    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    assert data['data']['confronto_executado'] is True


def test_analisar_retorna_reconhecimento_status_por_linha(app_context):
    """Cada linha no retorno de /analisar deve ter reconhecimento_status."""
    _combustivel, cartao = _base_cartao()
    csv = b'date,title,amount\n2026-05-01,POSTO SHELL,66.90\n2026-05-02,FARMACIA,45.00\n'

    with app_context.test_client() as client:
        response = client.post(
            '/api/importacao-cartao/analisar',
            data={
                'arquivo': (io.BytesIO(csv), 'fatura.csv'),
                'cartao_id': str(cartao.id),
                'competencia': '2026-05',
                'formato': 'csv',
            },
            content_type='multipart/form-data',
        )

    linhas = response.get_json()['data']['linhas']
    assert len(linhas) == 2
    for linha in linhas:
        assert 'reconhecimento_status' in linha
        assert linha['reconhecimento_status'] == 'sem_match'


def test_pipeline_completo_preserva_reconhecimento(app_context):
    """Pipeline completo retorna campos reconhecimento_* nas linhas enriquecidas."""
    combustivel, cartao = _base_cartao()
    _categoria_cartao_vinculada(cartao, combustivel)

    linhas = _pipeline(cartao, [_linha(categoria_id=combustivel.id)])

    linha = linhas[0]
    assert 'reconhecimento_status' in linha
    assert linha['reconhecimento_status'] == 'sem_match'
    assert linha['reconhecimento_match'] is None
    assert linha['reconhecimento_acao_recomendada'] == 'despesa_avulsa'


def test_multiplas_linhas_mapeadas_por_indice(app_context):
    """Com múltiplas linhas, cada uma recebe seu próprio resultado de reconhecimento."""
    _combustivel, cartao = _base_cartao()

    normalizadas = ImportacaoCartaoUnificadoService.normalizar_linhas(
        [_linha('POSTO A'), _linha('RESTAURANTE B', '35.00'), _linha('FARMACIA C', '22.00')],
        'csv',
        cartao.id,
    )
    ImportacaoCartaoUnificadoService.executar_confronto_linhas(normalizadas, cartao.id, date(2026, 5, 1))

    assert len(normalizadas) == 3
    for linha in normalizadas:
        assert 'reconhecimento_status' in linha
        assert 'reconhecimento_acao_recomendada' in linha
