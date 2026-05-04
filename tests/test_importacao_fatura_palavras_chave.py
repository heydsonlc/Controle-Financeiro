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
from backend.services.categoria_palavra_chave_service import CategoriaPalavraChaveService
from backend.services.importacao_cartao_service import ImportacaoCartaoService
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
    alimentacao = Categoria(nome='Alimentacao', ativo=True)
    transporte = Categoria(nome='Transporte', ativo=True)
    cartao = ItemDespesa(nome='Cartao Teste', tipo='Agregador', ativo=True, recorrente=True)
    db.session.add_all([combustivel, alimentacao, transporte, cartao])
    db.session.flush()
    db.session.add(ConfigAgregador(
        item_despesa_id=cartao.id,
        dia_fechamento=25,
        dia_vencimento=5,
    ))
    db.session.commit()
    return combustivel, alimentacao, transporte, cartao


def _categoria_cartao(nome='Mobilidade'):
    categoria = CategoriaCartaoService.criar_categoria(nome=nome, cor='#2563eb')
    db.session.commit()
    return categoria


def _mapear_e_vincular(cartao, categoria, categoria_cartao=None):
    categoria_cartao = categoria_cartao or _categoria_cartao()
    CategoriaCartaoService.vincular_categoria_despesa(categoria_cartao.id, categoria.id)
    CategoriaCartaoService.vincular_categoria_cartao_ao_cartao(
        cartao.id,
        categoria_cartao.id,
        limite_mensal='2000.00',
    )
    db.session.commit()
    return categoria_cartao


def _palavra(categoria, palavra):
    palavra_chave, _criada = CategoriaPalavraChaveService.criar(categoria.id, palavra)
    db.session.commit()
    return palavra_chave


def _linha(descricao='POSTO SHELL VILA MARIANA', categoria_id=None, categoria_cartao_id=None):
    linha = {
        'data_compra': '2026-05-01',
        'descricao': descricao,
        'descricao_original': descricao,
        'descricao_exibida': descricao,
        'valor': '66.90',
        'parcela': '1/1',
    }
    if categoria_id is not None:
        linha['categoria_id'] = categoria_id
    if categoria_cartao_id is not None:
        linha['categoria_cartao_id'] = categoria_cartao_id
    return linha


def _pipeline(cartao, linhas):
    competencia = date(2026, 5, 1)
    normalizadas = ImportacaoCartaoUnificadoService.normalizar_linhas(linhas, 'csv', cartao.id)
    ImportacaoCartaoUnificadoService.aplicar_sugestoes_categoria(normalizadas, cartao)
    ImportacaoCartaoUnificadoService.validar_linhas(normalizadas, cartao, competencia)
    ImportacaoCartaoUnificadoService.enriquecer_classificacao(normalizadas, cartao, competencia)
    return normalizadas


def _csv_upload(descricao='POSTO SHELL VILA MARIANA', valor='66.90'):
    csv = f'date,title,amount\n2026-05-01,{descricao},{valor}\n'
    return io.BytesIO(csv.encode('utf-8'))


def _post_analisar(client, cartao, descricao='POSTO SHELL VILA MARIANA', valor='66.90'):
    return client.post(
        '/api/importacao-cartao/analisar',
        data={
            'arquivo': (_csv_upload(descricao, valor), 'fatura.csv'),
            'cartao_id': str(cartao.id),
            'competencia': '2026-05',
            'formato': 'csv',
        },
        content_type='multipart/form-data',
    )


def test_palavra_chave_sugere_categoria_despesa_e_resolve_categoria_cartao(app_context):
    combustivel, _alimentacao, _transporte, cartao = _base_cartao()
    mobilidade = _mapear_e_vincular(cartao, combustivel)
    _palavra(combustivel, 'shell')

    linha = _pipeline(cartao, [_linha()])[0]

    assert linha['categoria_id'] == combustivel.id
    assert linha['categoria_origem'] == 'palavra_chave'
    assert linha['categoria_confianca'] == 'alta'
    assert linha['palavras_chave_encontradas'] == ['shell']
    assert linha['categoria_cartao_id'] == mobilidade.id
    assert linha['categoria_cartao_origem'] == 'mapa_categoria_despesa'
    assert linha['status_classificacao'] == 'classificada'


def test_multiplas_palavras_da_mesma_categoria_geram_confianca_alta(app_context):
    combustivel, _alimentacao, _transporte, cartao = _base_cartao()
    _mapear_e_vincular(cartao, combustivel)
    _palavra(combustivel, 'posto')
    _palavra(combustivel, 'shell')

    linha = _pipeline(cartao, [_linha('POSTO SHELL VILA MARIANA')])[0]

    assert linha['categoria_id'] == combustivel.id
    assert linha['categoria_confianca'] == 'alta'
    assert set(linha['palavras_chave_encontradas']) == {'posto', 'shell'}


def test_descricao_sem_palavra_chave_nao_quebra(app_context):
    _combustivel, _alimentacao, _transporte, cartao = _base_cartao()

    linha = _pipeline(cartao, [_linha('LOJA SEM REGRA')])[0]

    assert linha['categoria_id'] is None
    assert linha['status_classificacao'] == 'categoria_despesa_pendente'
    assert linha['categoria_confianca'] == 'baixa'


def test_palavra_chave_ambigua_gera_status_de_revisao(app_context):
    _combustivel, alimentacao, transporte, cartao = _base_cartao()
    _palavra(transporte, 'uber')
    _palavra(alimentacao, 'mercado')

    linha = _pipeline(cartao, [_linha('UBER MERCADO TESTE')])[0]

    assert linha['categoria_id'] is None
    assert linha['categoria_origem'] == 'ambigua'
    assert linha['status_classificacao'] == 'ambigua'
    assert set(linha['palavras_chave_encontradas']) == {'uber', 'mercado'}
    assert {item['categoria_id'] for item in linha['categorias_candidatas']} == {transporte.id, alimentacao.id}


def test_categoria_despesa_manual_prevalece_sobre_palavra_chave(app_context):
    combustivel, alimentacao, _transporte, cartao = _base_cartao()
    _mapear_e_vincular(cartao, combustivel, _categoria_cartao('Mobilidade'))
    alimentacao_cartao = _mapear_e_vincular(cartao, alimentacao, _categoria_cartao('Alimentacao'))
    _palavra(combustivel, 'shell')

    linha = _pipeline(cartao, [_linha(categoria_id=alimentacao.id)])[0]

    assert linha['categoria_id'] == alimentacao.id
    assert linha['categoria_origem'] == 'manual'
    assert linha['categoria_confianca'] == 'manual'
    assert linha['categoria_cartao_id'] == alimentacao_cartao.id


def test_categoria_cartao_manual_prevalece_sobre_resolucao(app_context):
    combustivel, _alimentacao, _transporte, cartao = _base_cartao()
    mobilidade = _mapear_e_vincular(cartao, combustivel, _categoria_cartao('Mobilidade'))
    casa = _categoria_cartao('Casa')
    CategoriaCartaoService.vincular_categoria_cartao_ao_cartao(cartao.id, casa.id, limite_mensal='500.00')
    db.session.commit()

    linha = _pipeline(cartao, [_linha(categoria_id=combustivel.id, categoria_cartao_id=casa.id)])[0]

    assert linha['categoria_cartao_id'] == casa.id
    assert linha['categoria_cartao_origem'] == 'manual'
    assert linha['categoria_cartao_id'] != mobilidade.id


def test_processamento_persiste_categoria_cartao_id_e_nao_exige_item_agregado(app_context):
    combustivel, _alimentacao, _transporte, cartao = _base_cartao()
    mobilidade = _mapear_e_vincular(cartao, combustivel)

    with app_context.test_client() as client:
        response = client.post('/api/importacao-cartao/processar', json={
            'cartao_id': cartao.id,
            'competencia': '2026-05-01',
            'linhas': [_linha(categoria_id=combustivel.id)],
        })

    assert response.status_code == 200
    assert response.get_json()['inseridos'] == 1
    lancamento = LancamentoAgregado.query.one()
    assert lancamento.categoria_cartao_id == mobilidade.id
    assert lancamento.item_agregado_id is None


def test_deduplicacao_continua_independente_da_classificacao(app_context):
    combustivel, _alimentacao, _transporte, cartao = _base_cartao()
    _mapear_e_vincular(cartao, combustivel)
    payload = {
        'cartao_id': cartao.id,
        'competencia': '2026-05-01',
        'linhas': [_linha(categoria_id=combustivel.id)],
    }

    with app_context.test_client() as client:
        primeira = client.post('/api/importacao-cartao/processar', json=payload)
        segunda = client.post('/api/importacao-cartao/processar', json=payload)

    assert primeira.status_code == 200
    assert primeira.get_json()['inseridos'] == 1
    assert segunda.status_code == 200
    assert segunda.get_json()['duplicados'] == 1
    assert LancamentoAgregado.query.count() == 1


def test_parcelamento_preserva_classificacao_resolvida(app_context):
    combustivel, _alimentacao, _transporte, cartao = _base_cartao()
    mobilidade = _mapear_e_vincular(cartao, combustivel)

    resultado = ImportacaoCartaoService.processar_linhas_mapeadas(
        [{
            **_linha('PNEUS 2/3', categoria_id=combustivel.id),
            'parcela': '2/3',
            'gerar_parcelas_futuras': True,
        }],
        cartao.id,
        date(2026, 5, 1),
    )

    assert resultado['linhas_invalidas'] == []
    assert len(resultado['lancamentos']) == 3
    assert {linha['categoria_cartao_id'] for linha in resultado['lancamentos']} == {mobilidade.id}


def test_previa_retorna_origem_confianca_e_palavras_encontradas(app_context):
    combustivel, _alimentacao, _transporte, cartao = _base_cartao()
    _mapear_e_vincular(cartao, combustivel)
    _palavra(combustivel, 'shell')

    with app_context.test_client() as client:
        response = _post_analisar(client, cartao)

    assert response.status_code == 200
    linha = response.get_json()['data']['linhas'][0]
    assert linha['descricao_normalizada'] == 'posto shell vila mariana'
    assert linha['categoria_origem'] == 'palavra_chave'
    assert linha['categoria_confianca'] == 'alta'
    assert linha['palavras_chave_encontradas'] == ['shell']
