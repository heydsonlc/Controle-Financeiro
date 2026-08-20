from datetime import date
from decimal import Decimal

import pytest

from backend.app import create_app
from backend.models import (
    Categoria,
    Conta,
    ContaBancaria,
    DespesaPrevista,
    IrComprovante,
    IrComprovanteVinculo,
    ItemDespesa,
    LancamentoAgregado,
    LastroFinanceiroPendencia,
    MovimentoFinanceiro,
    db,
)
from backend.services.perfil_financeiro_service import PerfilFinanceiroService
from tests.conftest import autenticar_cliente_teste


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
    return autenticar_cliente_teste(app.test_client(), app)


def _perfis(client):
    return client.get('/api/perfis-financeiros').get_json()['perfis']


def _perfil(client, nome):
    return next(perfil for perfil in _perfis(client) if perfil['nome'] == nome)


def _trocar_perfil(client, nome):
    perfil = _perfil(client, nome)
    response = client.post('/api/perfis-financeiros/ativo', json={'perfil_id': perfil['id']})
    assert response.status_code == 200, response.get_data(as_text=True)
    return perfil


def _categoria(perfil_id, nome='Operacional'):
    categoria = Categoria(
        perfil_financeiro_id=perfil_id,
        nome=nome,
        descricao='Categoria fiscal teste',
        cor='#2563eb',
        ativo=True,
    )
    db.session.add(categoria)
    db.session.flush()
    return categoria


def _despesa_prevista(perfil_id, categoria=None, valor='250.00', status='PREVISTA'):
    categoria = categoria or _categoria(perfil_id)
    despesa = DespesaPrevista(
        perfil_financeiro_id=perfil_id,
        origem_tipo='MANUAL',
        origem_id=1,
        categoria_id=categoria.id,
        data_prevista=date(2026, 5, 10),
        data_original_prevista=date(2026, 5, 10),
        data_atual_prevista=date(2026, 5, 10),
        valor_previsto=Decimal(valor),
        status=status,
    )
    db.session.add(despesa)
    db.session.flush()
    return despesa


def _conta_pagar(perfil_id, categoria=None, valor='320.00'):
    categoria = categoria or _categoria(perfil_id, 'Conta operacional')
    item = ItemDespesa(
        perfil_financeiro_id=perfil_id,
        categoria_id=categoria.id,
        nome='Aluguel escritorio',
        tipo='Simples',
        valor=Decimal(valor),
        ativo=True,
    )
    db.session.add(item)
    db.session.flush()
    conta = Conta(
        perfil_financeiro_id=perfil_id,
        item_despesa_id=item.id,
        mes_referencia=date(2026, 5, 1),
        descricao='Aluguel escritorio',
        valor=Decimal(valor),
        data_vencimento=date(2026, 5, 12),
        status_pagamento='Pendente',
        is_fatura_cartao=False,
    )
    db.session.add(conta)
    db.session.flush()
    return conta


def _cartao(perfil_id):
    item = ItemDespesa(
        perfil_financeiro_id=perfil_id,
        nome='Cartao Empresa',
        tipo='Agregador',
        ativo=True,
    )
    db.session.add(item)
    db.session.flush()
    return item


def _lancamento(perfil_id, categoria=None, valor='180.00', descricao='Software mensal'):
    categoria = categoria or _categoria(perfil_id, 'Software')
    cartao = _cartao(perfil_id)
    lancamento = LancamentoAgregado(
        perfil_financeiro_id=perfil_id,
        cartao_id=cartao.id,
        categoria_id=categoria.id,
        descricao=descricao,
        valor=Decimal(valor),
        data_compra=date(2026, 5, 8),
        mes_fatura=date(2026, 5, 1),
        numero_parcela=1,
        total_parcelas=1,
    )
    db.session.add(lancamento)
    db.session.flush()
    return lancamento


def _conta_bancaria(perfil_id, nome='Conta Empresa'):
    conta = ContaBancaria(
        perfil_financeiro_id=perfil_id,
        nome=nome,
        instituicao='Banco Teste',
        tipo='Conta Corrente',
        saldo_inicial=Decimal('0.00'),
        saldo_atual=Decimal('0.00'),
        status='ATIVO',
    )
    db.session.add(conta)
    db.session.flush()
    return conta


def _movimento(perfil_id, tipo='DEBITO', valor='90.00', descricao='Debito manual', origem='MANUAL', transferencia_id=None):
    conta = _conta_bancaria(perfil_id, f'Conta {tipo} {descricao[:10]}')
    movimento = MovimentoFinanceiro(
        perfil_financeiro_id=perfil_id,
        conta_bancaria_id=conta.id,
        tipo=tipo,
        valor=Decimal(valor),
        descricao=descricao,
        data_movimento=date(2026, 5, 9),
        origem=origem,
        transferencia_id=transferencia_id,
    )
    db.session.add(movimento)
    db.session.flush()
    return movimento


def _comprovante(perfil_id, sufixo='doc', valor='250.00'):
    comprovante = IrComprovante(
        perfil_financeiro_id=perfil_id,
        ano_calendario=2026,
        data_documento=date(2026, 5, 10),
        prestador_nome=f'Prestador {sufixo}',
        valor=Decimal(valor),
        status='VALIDADO',
        hash_arquivo=f'hash-{perfil_id}-{sufixo}',
    )
    db.session.add(comprovante)
    db.session.flush()
    return comprovante


def _ids(response):
    return {(item['tipo_entidade'], item['entidade_id']) for item in response.get_json()['data']}


def test_perfil_empresa_lista_despesa_sem_documento(client, app):
    empresa = _trocar_perfil(client, 'Empresa')
    with app.app_context():
        despesa = _despesa_prevista(empresa['id'])
        despesa_id = despesa.id
        db.session.commit()

    response = client.get('/api/ir/lastro/saidas-sem-documento?ano=2026&mes=5')

    assert response.status_code == 200
    assert ('DESPESA_PREVISTA', despesa_id) in _ids(response)
    item = response.get_json()['data'][0]
    assert item['status_lastro'] == 'SEM_DOCUMENTO'
    assert item['valor'] == 250.0


def test_perfil_pessoal_nao_ve_saida_da_empresa(client, app):
    empresa = _trocar_perfil(client, 'Empresa')
    with app.app_context():
        _despesa_prevista(empresa['id'])
        db.session.commit()

    _trocar_perfil(client, 'Pessoal')
    response = client.get('/api/ir/lastro/saidas-sem-documento?ano=2026&mes=5')

    assert response.status_code == 403
    assert 'perfil Empresa' in response.get_json()['error']


def test_saida_com_documento_vinculado_nao_aparece_como_sem_documento(client, app):
    empresa = _trocar_perfil(client, 'Empresa')
    with app.app_context():
        despesa = _despesa_prevista(empresa['id'])
        comprovante = _comprovante(empresa['id'], 'vinculado')
        despesa_id = despesa.id
        db.session.add(IrComprovanteVinculo(
            comprovante_id=comprovante.id,
            perfil_financeiro_id=empresa['id'],
            tipo_entidade='DESPESA_PREVISTA',
            entidade_id=despesa.id,
            resumo_entidade='Despesa vinculada',
            tipo_vinculo='NOTA_FISCAL',
            natureza='DESPESA_OPERACIONAL',
            status_lastro='VALIDADO',
            ativo=True,
        ))
        db.session.commit()

    response = client.get('/api/ir/lastro/saidas-sem-documento?ano=2026&mes=5')

    assert response.status_code == 200
    assert ('DESPESA_PREVISTA', despesa_id) not in _ids(response)


def test_marcar_nao_aplicavel_remove_da_lista_padrao(client, app):
    empresa = _trocar_perfil(client, 'Empresa')
    with app.app_context():
        despesa = _despesa_prevista(empresa['id'])
        despesa_id = despesa.id
        db.session.commit()

    response = client.post('/api/ir/lastro/saidas-sem-documento/status', json={
        'tipo_entidade': 'DESPESA_PREVISTA',
        'entidade_id': despesa_id,
        'status_lastro': 'NAO_APLICAVEL',
        'natureza': 'OUTRO',
        'observacoes': 'Sem exigencia documental.',
    })
    lista_padrao = client.get('/api/ir/lastro/saidas-sem-documento?ano=2026&mes=5')
    lista_na = client.get('/api/ir/lastro/saidas-sem-documento?ano=2026&mes=5&status=NAO_APLICAVEL')

    assert response.status_code == 200, response.get_data(as_text=True)
    assert ('DESPESA_PREVISTA', despesa_id) not in _ids(lista_padrao)
    assert ('DESPESA_PREVISTA', despesa_id) in _ids(lista_na)
    with app.app_context():
        assert LastroFinanceiroPendencia.query.filter_by(status_lastro='NAO_APLICAVEL').count() == 1


def test_marcar_aguardando_contador_aparece_no_resumo(client, app):
    empresa = _trocar_perfil(client, 'Empresa')
    with app.app_context():
        despesa = _despesa_prevista(empresa['id'], valor='410.00')
        despesa_id = despesa.id
        db.session.commit()

    response = client.post('/api/ir/lastro/saidas-sem-documento/status', json={
        'tipo_entidade': 'DESPESA_PREVISTA',
        'entidade_id': despesa_id,
        'status_lastro': 'AGUARDANDO_CONTADOR',
        'natureza': 'DISTRIBUICAO_LUCROS',
        'observacoes': 'Validar natureza com contador.',
    })
    resumo = client.get('/api/ir/lastro/saidas-sem-documento/resumo?ano=2026&mes=5')

    assert response.status_code == 200
    assert resumo.get_json()['data']['aguardando_contador'] == 1
    assert resumo.get_json()['data']['valor_aguardando_contador'] == 410.0


def test_vincular_documento_existente_remove_saida_da_lista(client, app):
    empresa = _trocar_perfil(client, 'Empresa')
    with app.app_context():
        despesa = _despesa_prevista(empresa['id'])
        comprovante = _comprovante(empresa['id'], 'endpoint')
        despesa_id = despesa.id
        comprovante_id = comprovante.id
        db.session.commit()

    response = client.post('/api/ir/lastro/saidas-sem-documento/vincular', json={
        'tipo_entidade': 'DESPESA_PREVISTA',
        'entidade_id': despesa_id,
        'comprovante_id': comprovante_id,
        'tipo_vinculo': 'NOTA_FISCAL',
        'natureza': 'DESPESA_OPERACIONAL',
        'status_lastro': 'VALIDADO',
    })
    lista = client.get('/api/ir/lastro/saidas-sem-documento?ano=2026&mes=5')

    assert response.status_code == 201, response.get_data(as_text=True)
    assert ('DESPESA_PREVISTA', despesa_id) not in _ids(lista)


def test_tentativa_de_vincular_documento_de_outro_perfil_e_bloqueada(client, app):
    pessoal = _perfil(client, 'Pessoal')
    empresa = _trocar_perfil(client, 'Empresa')
    with app.app_context():
        despesa = _despesa_prevista(empresa['id'])
        comprovante_pessoal = _comprovante(pessoal['id'], 'pessoal')
        despesa_id = despesa.id
        comprovante_pessoal_id = comprovante_pessoal.id
        db.session.commit()

    response = client.post('/api/ir/lastro/saidas-sem-documento/vincular', json={
        'tipo_entidade': 'DESPESA_PREVISTA',
        'entidade_id': despesa_id,
        'comprovante_id': comprovante_pessoal_id,
        'natureza': 'DESPESA_OPERACIONAL',
    })

    assert response.status_code == 400
    assert 'perfil financeiro ativo' in response.get_json()['error']


def test_natureza_sugerida_por_categoria_e_descricao(client, app):
    empresa = _trocar_perfil(client, 'Empresa')
    with app.app_context():
        cat = _categoria(empresa['id'], 'Equipamento notebook')
        despesa = _despesa_prevista(empresa['id'], categoria=cat)
        movimento = _movimento(empresa['id'], descricao='Pro labore socio maio')
        despesa_id = despesa.id
        movimento_id = movimento.id
        db.session.commit()

    response = client.get('/api/ir/lastro/saidas-sem-documento?ano=2026&mes=5&status=TODOS')
    dados = {(item['tipo_entidade'], item['entidade_id']): item for item in response.get_json()['data']}

    assert dados[('DESPESA_PREVISTA', despesa_id)]['natureza_sugerida'] == 'PATRIMONIO_IMOBILIZADO'
    assert dados[('MOVIMENTO_FINANCEIRO', movimento_id)]['natureza_sugerida'] == 'PRO_LABORE'


def test_resumo_calcula_quantidade_e_valor(client, app):
    empresa = _trocar_perfil(client, 'Empresa')
    with app.app_context():
        _despesa_prevista(empresa['id'], valor='100.00')
        _conta_pagar(empresa['id'], valor='200.00')
        db.session.commit()

    resumo = client.get('/api/ir/lastro/saidas-sem-documento/resumo?ano=2026&mes=5').get_json()['data']

    assert resumo['quantidade_sem_documento'] == 2
    assert resumo['valor_sem_documento'] == 300.0
    assert resumo['total_saidas'] == 2
    assert {item['nome'] for item in resumo['por_origem']} == {'Despesa prevista', 'Conta a pagar'}


def test_endpoint_no_perfil_pessoal_retorna_erro_controlado(client):
    response = client.get('/api/ir/lastro/saidas-sem-documento/resumo?ano=2026&mes=5')

    assert response.status_code == 403
    assert response.get_json()['success'] is False


def test_nao_inclui_receitas_ou_entradas(client, app):
    empresa = _trocar_perfil(client, 'Empresa')
    with app.app_context():
        _movimento(empresa['id'], tipo='CREDITO', valor='900.00', descricao='Receita cliente')
        db.session.commit()

    response = client.get('/api/ir/lastro/saidas-sem-documento?ano=2026&mes=5')

    assert response.status_code == 200
    assert response.get_json()['data'] == []


def test_transferencia_interna_e_excluida_e_saida_para_socio_pende(client, app):
    empresa = _trocar_perfil(client, 'Empresa')
    with app.app_context():
        debito_interno = _movimento(
            empresa['id'],
            tipo='DEBITO',
            valor='500.00',
            descricao='Transferencia interna origem',
            origem='TRANSFERENCIA',
            transferencia_id='tx-interna',
        )
        _movimento(
            empresa['id'],
            tipo='CREDITO',
            valor='500.00',
            descricao='Transferencia interna destino',
            origem='TRANSFERENCIA',
            transferencia_id='tx-interna',
        )
        debito_socio = _movimento(
            empresa['id'],
            tipo='DEBITO',
            valor='700.00',
            descricao='Transferencia para socio',
            origem='TRANSFERENCIA',
            transferencia_id='tx-socio',
        )
        debito_interno_id = debito_interno.id
        debito_socio_id = debito_socio.id
        db.session.commit()

    response = client.get('/api/ir/lastro/saidas-sem-documento?ano=2026&mes=5&origem=MOVIMENTO_FINANCEIRO')

    assert ('MOVIMENTO_FINANCEIRO', debito_interno_id) not in _ids(response)
    assert ('MOVIMENTO_FINANCEIRO', debito_socio_id) in _ids(response)
