from datetime import date
import io

import pytest
from flask import Flask

from backend.models import (
    db,
    Categoria,
    CategoriaCartao,
    ConfigAgregador,
    ItemDespesa,
    LancamentoAgregado,
)
from backend.routes.importacao_cartao import bp as importacao_cartao_bp
from backend.services.categoria_cartao_service import CategoriaCartaoService
from backend.services.importacao_cartao_messages import MSG_CATEGORIA_DESPESA_SEM_CATEGORIA_CARTAO
from backend.services.importacao_cartao_service import ImportacaoCartaoService


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
    supermercado = Categoria(nome='Supermercado', ativo=True)
    sem_mapa = Categoria(nome='Sem Mapa', ativo=True)
    cartao = ItemDespesa(nome='Cartao Teste', tipo='Agregador', ativo=True, recorrente=True)
    db.session.add_all([combustivel, supermercado, sem_mapa, cartao])
    db.session.flush()
    db.session.add(ConfigAgregador(
        item_despesa_id=cartao.id,
        dia_fechamento=25,
        dia_vencimento=5,
    ))
    db.session.commit()
    return combustivel, supermercado, sem_mapa, cartao


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


def _mapear_sem_vincular(categoria, categoria_cartao=None):
    categoria_cartao = categoria_cartao or _categoria_cartao()
    CategoriaCartaoService.vincular_categoria_despesa(categoria_cartao.id, categoria.id)
    db.session.commit()
    return categoria_cartao


def _linha(categoria_id=None, categoria_cartao_id=None, descricao='POSTO SHELL T-63', ignorar=False):
    linha = {
        'data_compra': '2026-05-01',
        'descricao': descricao,
        'valor': '66.90',
        'parcela': '1/1',
        'ignorar': ignorar,
    }
    if categoria_id is not None:
        linha['categoria_id'] = categoria_id
    if categoria_cartao_id is not None:
        linha['categoria_cartao_id'] = categoria_cartao_id
    return linha


def _csv_upload(descricao='POSTO SHELL T-63', valor='66.90'):
    csv = f'date,title,amount\n2026-05-01,{descricao},{valor}\n'
    return io.BytesIO(csv.encode('utf-8'))


def _post_analisar(client, cartao, descricao='POSTO SHELL T-63', valor='66.90'):
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


def _historico(cartao, categoria, descricao='POSTO SHELL T-63'):
    db.session.add(LancamentoAgregado(
        cartao_id=cartao.id,
        categoria_id=categoria.id,
        descricao=descricao,
        descricao_original=descricao,
        descricao_original_normalizada=descricao,
        descricao_exibida=descricao,
        valor=10,
        data_compra=date(2026, 4, 1),
        mes_fatura=date(2026, 4, 1),
    ))
    db.session.commit()


def test_analisar_sugere_categoria_despesa_e_resolve_categoria_cartao(app_context):
    combustivel, _supermercado, _sem_mapa, cartao = _base_cartao()
    mobilidade = _mapear_e_vincular(cartao, combustivel)
    _historico(cartao, combustivel)

    with app_context.test_client() as client:
        response = _post_analisar(client, cartao)

    assert response.status_code == 200
    linha = response.get_json()['data']['linhas'][0]
    assert linha['categoria_id'] == combustivel.id
    assert linha['categoria_nome'] == 'Combustivel'
    assert linha['categoria_origem'] == 'historico'
    assert linha['categoria_cartao_id'] == mobilidade.id
    assert linha['categoria_cartao_nome'] == 'Mobilidade'
    assert linha['categoria_cartao_origem'] == 'mapa_categoria_despesa'
    assert linha['categoria_cartao_vinculada_ao_cartao'] is True
    assert linha['status_classificacao'] == 'classificada'


def test_processamento_preserva_categoria_cartao_manual(app_context):
    combustivel, _supermercado, _sem_mapa, cartao = _base_cartao()
    mobilidade = _mapear_e_vincular(cartao, combustivel, _categoria_cartao('Mobilidade'))
    casa = _categoria_cartao('Casa')
    CategoriaCartaoService.vincular_categoria_cartao_ao_cartao(cartao.id, casa.id, limite_mensal='500.00')
    db.session.commit()

    resultado = ImportacaoCartaoService.processar_linhas_mapeadas(
        [_linha(combustivel.id, casa.id)],
        cartao.id,
        date(2026, 5, 1),
    )

    assert mobilidade.id != casa.id
    assert resultado['linhas_invalidas'] == []
    assert resultado['lancamentos'][0]['categoria_cartao_id'] == casa.id


def test_analisar_categoria_cartao_nao_vinculada_gera_aviso(app_context):
    combustivel, _supermercado, _sem_mapa, cartao = _base_cartao()
    mobilidade = _mapear_sem_vincular(combustivel)
    _historico(cartao, combustivel)

    with app_context.test_client() as client:
        response = _post_analisar(client, cartao)

    assert response.status_code == 200
    linha = response.get_json()['data']['linhas'][0]
    assert linha['categoria_cartao_id'] is None
    assert linha['categoria_cartao_nome'] == mobilidade.nome
    assert linha['categoria_cartao_origem'] == 'nao_vinculada_ao_cartao'
    assert linha['categoria_cartao_vinculada_ao_cartao'] is False
    assert linha['status_classificacao'] == 'categoria_cartao_nao_vinculada'
    assert 'cartao selecionado' in linha['avisos'][0]


def test_processar_sem_categoria_cartao_nao_exige_item_agregado(app_context):
    combustivel, _supermercado, _sem_mapa, cartao = _base_cartao()

    with app_context.test_client() as client:
        response = client.post('/api/importacao-cartao/processar', json={
            'cartao_id': cartao.id,
            'competencia': '2026-05-01',
            'linhas': [_linha(combustivel.id)],
        })

    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    assert data['inseridos'] == 1
    assert data['pendencias']['categoria_cartao'] == 1
    lancamento = LancamentoAgregado.query.one()
    assert lancamento.categoria_cartao_id is None
    assert lancamento.item_agregado_id is None


def test_processar_persiste_categoria_cartao_resolvida(app_context):
    combustivel, _supermercado, _sem_mapa, cartao = _base_cartao()
    mobilidade = _mapear_e_vincular(cartao, combustivel)

    with app_context.test_client() as client:
        response = client.post('/api/importacao-cartao/processar', json={
            'cartao_id': cartao.id,
            'competencia': '2026-05-01',
            'linhas': [_linha(combustivel.id)],
        })

    assert response.status_code == 200
    data = response.get_json()
    assert data['inseridos'] == 1
    assert data['amostra_validos'][0]['categoria_cartao_id'] == mobilidade.id
    lancamento = LancamentoAgregado.query.one()
    assert lancamento.categoria_cartao_id == mobilidade.id
    assert lancamento.item_agregado_id is None


def test_deduplicacao_continua_marcando_linha_duplicada(app_context):
    combustivel, _supermercado, _sem_mapa, cartao = _base_cartao()
    _mapear_e_vincular(cartao, combustivel)
    db.session.add(LancamentoAgregado(
        cartao_id=cartao.id,
        categoria_id=combustivel.id,
        descricao='POSTO SHELL T-63',
        descricao_original='POSTO SHELL T-63',
        descricao_original_normalizada='POSTO SHELL T-63',
        descricao_exibida='POSTO SHELL T-63',
        valor=66.90,
        data_compra=date(2026, 5, 1),
        mes_fatura=date(2026, 5, 1),
    ))
    db.session.commit()

    with app_context.test_client() as client:
        response = _post_analisar(client, cartao)

    linha = response.get_json()['data']['linhas'][0]
    assert linha['duplicada'] is True
    assert linha['status'] == 'duplicado'
    assert linha['status_classificacao'] == 'duplicada'


def test_linha_ignorada_nao_e_processada(app_context):
    combustivel, supermercado, _sem_mapa, cartao = _base_cartao()
    _mapear_e_vincular(cartao, combustivel)
    _mapear_e_vincular(cartao, supermercado, _categoria_cartao('Alimentacao'))

    with app_context.test_client() as client:
        response = client.post('/api/importacao-cartao/processar', json={
            'cartao_id': cartao.id,
            'competencia': '2026-05-01',
            'linhas': [
                _linha(combustivel.id, descricao='POSTO SHELL T-63', ignorar=True),
                _linha(supermercado.id, descricao='MERCADO TESTE'),
            ],
        })

    assert response.status_code == 200
    assert response.get_json()['inseridos'] == 1
    assert LancamentoAgregado.query.count() == 1
    assert LancamentoAgregado.query.one().descricao == 'MERCADO TESTE'


def test_parcelas_futuras_preservam_categoria_cartao(app_context):
    combustivel, _supermercado, _sem_mapa, cartao = _base_cartao()
    mobilidade = _mapear_e_vincular(cartao, combustivel)

    resultado = ImportacaoCartaoService.processar_linhas_mapeadas(
        [{
            **_linha(combustivel.id, descricao='PNEUS 2/3'),
            'parcela': '2/3',
            'gerar_parcelas_futuras': True,
        }],
        cartao.id,
        date(2026, 5, 1),
    )

    assert resultado['linhas_invalidas'] == []
    assert len(resultado['lancamentos']) == 3
    assert {linha['categoria_cartao_id'] for linha in resultado['lancamentos']} == {mobilidade.id}


def test_previsualizar_retorna_status_de_pendencias_e_avisos(app_context):
    combustivel, _supermercado, _sem_mapa, cartao = _base_cartao()

    with app_context.test_client() as client:
        response = client.post('/api/importacao-cartao/previsualizar', json={
            'cartao_id': cartao.id,
            'competencia': '2026-05-01',
            'linhas': [_linha(combustivel.id)],
        })

    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    assert data['pendencias']['categoria_despesa'] == 0
    assert data['pendencias']['categoria_cartao'] == 1
    assert data['pendencias']['avisos'] == 1
    assert data['avisos_linhas'][0]['avisos'] == [MSG_CATEGORIA_DESPESA_SEM_CATEGORIA_CARTAO]


# ── IMPORT-TRIAGEM-1: separação triagem / confronto / classificação ───────────

def test_triagem_nao_bloqueia_por_ausencia_de_categoria_cartao(app_context):
    """Triagem (analisar) não deve bloquear nem marcar erro por falta de categoria_cartao."""
    combustivel, _supermercado, _sem_mapa, cartao = _base_cartao()
    _historico(cartao, combustivel)
    # Não mapeia Categoria do Cartão intencionalmente

    with app_context.test_client() as client:
        response = _post_analisar(client, cartao)

    assert response.status_code == 200
    linha = response.get_json()['data']['linhas'][0]
    # Categoria da Despesa foi sugerida normalmente
    assert linha['categoria_id'] == combustivel.id
    # Sem Categoria do Cartão mapeada — não deve bloquear
    assert linha['status'] in ('valido', 'revisar')
    assert linha['status'] != 'erro'
    # Status de classificação informa pendência, mas não bloqueia
    assert linha['status_classificacao'] in (
        'classificada', 'categoria_cartao_pendente', 'categoria_cartao_nao_vinculada'
    )


def test_triagem_nao_bloqueia_status_por_ausencia_de_categoria_cartao(app_context):
    """Ausência de categoria_cartao não deve bloquear status da linha na triagem."""
    combustivel, _supermercado, _sem_mapa, cartao = _base_cartao()
    _historico(cartao, combustivel)
    # Sem mapeamento de categoria_cartao — categoria_id é sugerida normalmente

    with app_context.test_client() as client:
        response = _post_analisar(client, cartao)

    assert response.status_code == 200
    linha = response.get_json()['data']['linhas'][0]
    # Categoria da Despesa sugerida com confiança
    assert linha['categoria_id'] == combustivel.id
    # Status da linha não deve ser 'erro' por falta de categoria_cartao
    assert linha['status'] != 'erro'
    # status_classificacao pode ser 'categoria_cartao_pendente' — é informativo, não bloqueante
    assert linha['status_classificacao'] in (
        'classificada',
        'categoria_cartao_pendente',
        'categoria_cartao_nao_vinculada',
    )


def test_descricao_original_preservada_apos_renomear(app_context):
    """descricao_original não pode ser sobrescrita; descricao_exibida é editável."""
    combustivel, _supermercado, _sem_mapa, cartao = _base_cartao()
    mobilidade = _mapear_e_vincular(cartao, combustivel)

    descricao_bruta = 'POSTO SHELL T-63'
    descricao_renomeada = 'Shell - posto'

    resultado = ImportacaoCartaoService.processar_linhas_mapeadas(
        [{
            **_linha(combustivel.id, mobilidade.id),
            'descricao_exibida': descricao_renomeada,
            'descricao': descricao_bruta,
        }],
        cartao.id,
        date(2026, 5, 1),
    )

    assert resultado['linhas_invalidas'] == []
    lancamento_dict = resultado['lancamentos'][0]

    # descricao_original deve ser o dado bruto do cartão
    assert lancamento_dict.get('descricao_original') == descricao_bruta
    # descricao_exibida é a versão renomeada pelo usuário
    assert lancamento_dict.get('descricao_exibida') == descricao_renomeada


def test_mesmo_cartao_obrigatorio_para_sugestao_operacional(app_context):
    """Recorrência de outro cartão não deve ser sugerida como operacional."""
    combustivel, _supermercado, _sem_mapa, cartao = _base_cartao()
    outro_cartao = ItemDespesa(nome='Outro Cartao', tipo='Agregador', ativo=True, recorrente=True)
    db.session.add(outro_cartao)
    db.session.flush()
    from backend.models import ConfigAgregador
    db.session.add(ConfigAgregador(
        item_despesa_id=outro_cartao.id,
        dia_fechamento=25,
        dia_vencimento=5,
    ))
    db.session.commit()

    # Histórico existe apenas no outro cartão
    db.session.add(LancamentoAgregado(
        cartao_id=outro_cartao.id,
        categoria_id=combustivel.id,
        descricao='POSTO SHELL T-63',
        descricao_original='POSTO SHELL T-63',
        descricao_original_normalizada='POSTO SHELL T-63',
        descricao_exibida='POSTO SHELL T-63',
        valor=66.90,
        data_compra=date(2026, 4, 1),
        mes_fatura=date(2026, 4, 1),
    ))
    db.session.commit()

    with app_context.test_client() as client:
        response = client.post('/api/importacao-cartao/reconhecer', json={
            'cartao_id': cartao.id,
            'competencia': '2026-05-01',
            'linhas': [_linha(combustivel.id, descricao='POSTO SHELL T-63')],
        })

    assert response.status_code == 200
    reconhecimentos = response.get_json()['reconhecimentos']
    # Nenhum reconhecimento de alto score para cartão diferente
    for rec in reconhecimentos:
        sugestoes = rec.get('sugestoes') or []
        for s in sugestoes:
            # Score alto (>=80) não deve ser sugerido para outro cartão
            if s.get('score', 0) >= 80:
                assert False, f'Sugestão de alto score gerada para outro cartão: {s}'


def test_categoria_id_nao_obrigatoria_na_triagem(app_context):
    """Linha sem categoria_id deve ter status='revisar', não 'erro' nem bloquear triagem."""
    _combustivel, _supermercado, _sem_mapa, cartao = _base_cartao()
    # Sem histórico e sem palavras-chave — nenhuma sugestão será feita

    with app_context.test_client() as client:
        response = _post_analisar(client, cartao, descricao='DESCRICAO DESCONHECIDA XYZ123')

    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['linhas'][0]['status'] == 'revisar'
    assert data['linhas'][0]['categoria_id'] is None
    # Triagem retorna payload completo mesmo sem categoria
    assert 'validacoes' in data
    assert data['validacoes']['total_linhas'] == 1


def test_categoria_cartao_opcional_nao_bloqueia_importacao(app_context):
    """Importação sem Categoria do Cartão deve funcionar: aviso mas não bloqueio."""
    combustivel, _supermercado, _sem_mapa, cartao = _base_cartao()
    # Sem mapeamento de categoria_cartao

    with app_context.test_client() as client:
        response = client.post('/api/importacao-cartao/processar', json={
            'cartao_id': cartao.id,
            'competencia': '2026-05-01',
            'linhas': [_linha(combustivel.id)],
        })

    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    assert data['inseridos'] == 1
    assert data['pendencias']['categoria_cartao'] == 1
    # Aviso padronizado deve estar presente
    avisos = [av['aviso'] for av in data.get('avisos_linhas', [])]
    assert any('pendencia de classificacao' in av for av in avisos)


def test_nao_cria_duplicidade_silenciosa(app_context):
    """Lançamento idêntico ao existente deve ser sinalizado como duplicado, não criado."""
    combustivel, _supermercado, _sem_mapa, cartao = _base_cartao()
    mobilidade = _mapear_e_vincular(cartao, combustivel)
    db.session.add(LancamentoAgregado(
        cartao_id=cartao.id,
        categoria_id=combustivel.id,
        categoria_cartao_id=mobilidade.id,
        descricao='POSTO SHELL T-63',
        descricao_original='POSTO SHELL T-63',
        descricao_original_normalizada='posto shell t-63',
        descricao_exibida='POSTO SHELL T-63',
        valor=66.90,
        data_compra=date(2026, 5, 1),
        mes_fatura=date(2026, 5, 1),
    ))
    db.session.commit()

    with app_context.test_client() as client:
        response = _post_analisar(client, cartao)

    assert response.status_code == 200
    linha = response.get_json()['data']['linhas'][0]
    assert linha['duplicada'] is True
    assert linha['status'] == 'duplicado'
    assert linha['status_classificacao'] == 'duplicada'
    assert LancamentoAgregado.query.count() == 1  # não criou novo
