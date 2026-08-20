from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from backend.app import create_app
from backend.models import (
    CartaoCategoriaLimite,
    Categoria,
    CategoriaCartao,
    CategoriaCartaoDespesa,
    CategoriaPalavraChave,
    ConfigAgregador,
    Conta,
    IrCategoria,
    IrCategoriaDespesa,
    IrComprovante,
    IrComprovanteArquivo,
    IrComprovanteVinculo,
    ItemDespesa,
    LancamentoAgregado,
    db,
)
from backend.services.perfil_financeiro_service import PerfilFinanceiroService
from tests.conftest import autenticar_cliente_teste


ROOT = Path(__file__).resolve().parents[1]


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


def _categoria(perfil_id, nome='Saude', palavra='laboratorio'):
    categoria = Categoria(
        perfil_financeiro_id=perfil_id,
        nome=nome,
        descricao='Categoria teste',
        cor='#2563eb',
        ativo=True,
    )
    db.session.add(categoria)
    db.session.flush()
    if palavra:
        db.session.add(CategoriaPalavraChave(categoria_id=categoria.id, palavra=palavra, ativo=True))
    return categoria


def _categoria_ir(perfil_id, categoria, nome='Saude fiscal'):
    ir = IrCategoria(nome=nome, descricao='Fiscal', dedutivel=True, ativo=True, ordem=1)
    db.session.add(ir)
    db.session.flush()
    db.session.add(IrCategoriaDespesa(
        perfil_financeiro_id=perfil_id,
        categoria_id=categoria.id,
        categoria_ir_id=ir.id,
        ativo=True,
    ))
    return ir


def _comprovante(perfil_id, *, categoria=None, categoria_ir=None, valor='130.80', texto=None, sufixo='doc'):
    comprovante = IrComprovante(
        perfil_financeiro_id=perfil_id,
        ano_calendario=2026,
        data_documento=date(2026, 5, 10),
        prestador_nome='Laboratorio Padrao SA',
        prestador_cpf_cnpj='01.588.888/0001-98',
        valor=Decimal(valor) if valor is not None else None,
        categoria_id=categoria.id if categoria else None,
        categoria_ir_id=categoria_ir.id if categoria_ir else None,
        status='CLASSIFICADO' if categoria else 'PENDENTE_REVISAO',
        origem_classificacao='palavra_chave' if categoria else None,
        confianca='alta' if categoria else None,
        texto_extraido=texto or 'Laboratorio Padrao SA exames laboratoriais valor total 130,80',
        hash_arquivo=f'hash-{perfil_id}-{sufixo}',
    )
    db.session.add(comprovante)
    db.session.flush()
    db.session.add(IrComprovanteArquivo(
        comprovante_id=comprovante.id,
        nome_arquivo=f'nota-{sufixo}.pdf',
        mime_type='application/pdf',
        tamanho_bytes=10,
        conteudo=b'%PDF-1.4',
        hash_arquivo=comprovante.hash_arquivo,
    ))
    db.session.flush()
    return comprovante


def _cartao(perfil_id, nome='Cartao Empresa'):
    cartao = ItemDespesa(
        perfil_financeiro_id=perfil_id,
        nome=nome,
        tipo='Agregador',
        ativo=True,
        recorrente=True,
    )
    db.session.add(cartao)
    db.session.flush()
    db.session.add(ConfigAgregador(item_despesa_id=cartao.id, dia_fechamento=25, dia_vencimento=5))
    return cartao


def _categoria_cartao_vinculada(perfil_id, cartao, categoria, nome='Saude Cartao'):
    categoria_cartao = CategoriaCartao(
        perfil_financeiro_id=perfil_id,
        nome=nome,
        cor='#2563eb',
        ativo=True,
    )
    db.session.add(categoria_cartao)
    db.session.flush()
    db.session.add(CategoriaCartaoDespesa(
        perfil_financeiro_id=perfil_id,
        categoria_cartao_id=categoria_cartao.id,
        categoria_id=categoria.id,
        ativo=True,
    ))
    db.session.add(CartaoCategoriaLimite(
        perfil_financeiro_id=perfil_id,
        cartao_id=cartao.id,
        categoria_cartao_id=categoria_cartao.id,
        limite_mensal=Decimal('1000.00'),
        ativo=True,
    ))
    return categoria_cartao


def test_gerar_sugestao_usa_texto_valor_data_prestador_categoria_e_nao_cria_financeiro(client, app):
    empresa = _trocar_perfil(client, 'Empresa')
    with app.app_context():
        categoria = _categoria(empresa['id'], palavra='laboratorio')
        ir = _categoria_ir(empresa['id'], categoria)
        comprovante = _comprovante(
            empresa['id'],
            texto='Laboratorio Padrao SA exames laboratoriais valor total 130,80',
            sufixo='sugestao',
        )
        categoria_id = categoria.id
        ir_id = ir.id
        comprovante_id = comprovante.id
        db.session.commit()

    response = client.get(f'/api/ir/comprovantes/{comprovante_id}/sugestao-financeira')

    data = response.get_json()['data']
    assert response.status_code == 200
    assert data['valor'] == 130.8
    assert data['data'] == '2026-05-10'
    assert data['fornecedor'] == 'Laboratorio Padrao SA'
    assert data['categoria_id'] == categoria_id
    assert data['categoria_ir_id'] == ir_id
    assert 'Laboratorio Padrao SA' in data['descricao']
    assert ItemDespesa.query.count() == 0
    assert Conta.query.count() == 0
    assert LancamentoAgregado.query.count() == 0
    assert IrComprovanteVinculo.query.count() == 0


def test_criar_despesa_a_partir_sugestao_cria_conta_pendente_e_vincula_documento(client, app):
    empresa = _trocar_perfil(client, 'Empresa')
    with app.app_context():
        categoria = _categoria(empresa['id'])
        ir = _categoria_ir(empresa['id'], categoria)
        comprovante = _comprovante(empresa['id'], categoria=categoria, categoria_ir=ir, sufixo='despesa')
        categoria_id = categoria.id
        comprovante_id = comprovante.id
        db.session.commit()

    response = client.post(f'/api/ir/comprovantes/{comprovante_id}/criar-financeiro', json={
        'tipo_destino': 'DESPESA',
        'descricao': 'Laboratorio Padrao SA - Exames',
        'valor': '130.80',
        'data': '2026-05-10',
        'competencia': '2026-05',
        'categoria_id': categoria_id,
        'forma_pagamento': 'boleto',
        'observacoes': 'Revisado pelo usuario',
    })

    data = response.get_json()['data']
    conta = Conta.query.one()
    vinculo = IrComprovanteVinculo.query.one()
    assert response.status_code == 201, response.get_data(as_text=True)
    assert data['tipo_destino'] == 'DESPESA'
    assert data['tipo_entidade'] == 'CONTA'
    assert conta.status_pagamento == 'Pendente'
    assert conta.item_despesa.meio_pagamento == 'boleto'
    assert vinculo.comprovante_id == comprovante_id
    assert vinculo.tipo_entidade == 'CONTA'
    assert vinculo.entidade_id == conta.id
    assert vinculo.status_lastro == 'COM_DOCUMENTO'


def test_criar_lancamento_cartao_resolve_categoria_cartao_sem_select_manual(client, app):
    empresa = _trocar_perfil(client, 'Empresa')
    with app.app_context():
        categoria = _categoria(empresa['id'])
        ir = _categoria_ir(empresa['id'], categoria)
        cartao = _cartao(empresa['id'])
        categoria_cartao = _categoria_cartao_vinculada(empresa['id'], cartao, categoria)
        comprovante = _comprovante(empresa['id'], categoria=categoria, categoria_ir=ir, sufixo='cartao')
        categoria_id = categoria.id
        cartao_id = cartao.id
        categoria_cartao_id = categoria_cartao.id
        comprovante_id = comprovante.id
        db.session.commit()

    response = client.post(f'/api/ir/comprovantes/{comprovante_id}/criar-financeiro', json={
        'tipo_destino': 'LANCAMENTO',
        'descricao': 'Laboratorio no cartao',
        'valor': '130.80',
        'data': '2026-05-10',
        'categoria_id': categoria_id,
        'forma_pagamento': 'cartao',
        'cartao_id': cartao_id,
        'categoria_cartao_id': 999999,
    })

    lancamento = LancamentoAgregado.query.one()
    vinculo = IrComprovanteVinculo.query.one()
    assert response.status_code == 201, response.get_data(as_text=True)
    assert lancamento.categoria_cartao_id == categoria_cartao_id
    assert lancamento.item_agregado_id is None
    assert vinculo.tipo_entidade == 'LANCAMENTO'
    assert vinculo.entidade_id == lancamento.id


def test_perfil_pessoal_nao_acessa_documento_empresa(client, app):
    empresa = _trocar_perfil(client, 'Empresa')
    with app.app_context():
        comprovante = _comprovante(empresa['id'], sufixo='empresa-isolada')
        comprovante_id = comprovante.id
        db.session.commit()

    _trocar_perfil(client, 'Pessoal')
    response = client.get(f'/api/ir/comprovantes/{comprovante_id}/sugestao-financeira')

    assert response.status_code == 404
    assert 'Comprovante nao encontrado' in response.get_json()['error']


def test_cartao_de_outro_perfil_e_bloqueado_categoria_global_aceita(client, app):
    # Categoria de Despesa é global — pode ser usada de qualquer perfil.
    # Cartão permanece isolado por perfil — usar cartão de outro perfil deve ser bloqueado.
    pessoal = _trocar_perfil(client, 'Pessoal')
    with app.app_context():
        categoria_pessoal = _categoria(pessoal['id'], nome='Pessoal categoria', palavra=None)
        cartao_pessoal = _cartao(pessoal['id'], nome='Cartao Pessoal')
        categoria_pessoal_id = categoria_pessoal.id
        cartao_pessoal_id = cartao_pessoal.id
        db.session.commit()

    empresa = _trocar_perfil(client, 'Empresa')
    with app.app_context():
        categoria_empresa = _categoria(empresa['id'], nome='Empresa categoria', palavra=None)
        comprovante = _comprovante(empresa['id'], sufixo='cross-profile')
        categoria_empresa_id = categoria_empresa.id
        comprovante_id = comprovante.id
        db.session.commit()

    # Categoria global: usar categoria_pessoal no perfil Empresa agora é aceito
    categoria_response = client.post(f'/api/ir/comprovantes/{comprovante_id}/criar-financeiro', json={
        'tipo_destino': 'DESPESA',
        'descricao': 'Categoria global usada no perfil empresa',
        'valor': '50.00',
        'data': '2026-05-10',
        'categoria_id': categoria_pessoal_id,
        'forma_pagamento': 'pix',
    })
    assert categoria_response.status_code == 201

    # Cartão de outro perfil: ainda bloqueado
    cartao_response = client.post(f'/api/ir/comprovantes/{comprovante_id}/criar-financeiro', json={
        'tipo_destino': 'LANCAMENTO',
        'descricao': 'Cartao errado',
        'valor': '50.00',
        'data': '2026-05-10',
        'categoria_id': categoria_empresa_id,
        'forma_pagamento': 'cartao',
        'cartao_id': cartao_pessoal_id,
    })
    assert cartao_response.status_code in {400, 404}


def test_sugestao_sem_categoria_ou_valor_retorna_avisos_sem_criar_entidade(client, app):
    empresa = _trocar_perfil(client, 'Empresa')
    with app.app_context():
        comprovante = _comprovante(
            empresa['id'],
            valor=None,
            texto='Documento sem palavras conhecidas suficientes para classificar',
            sufixo='sem-dados',
        )
        comprovante_id = comprovante.id
        db.session.commit()

    response = client.get(f'/api/ir/comprovantes/{comprovante_id}/sugestao-financeira')

    avisos = response.get_json()['data']['avisos']
    assert response.status_code == 200
    assert any('Categoria de Despesa nao identificada' in aviso for aviso in avisos)
    assert any('Valor nao identificado' in aviso for aviso in avisos)
    assert ItemDespesa.query.count() == 0
    assert Conta.query.count() == 0


def test_frontend_contem_botao_modal_e_nao_tem_select_manual_de_categoria_cartao():
    template = (ROOT / 'frontend/templates/imposto_renda.html').read_text(encoding='utf-8')
    js = (ROOT / 'frontend/static/js/imposto_renda.js').read_text(encoding='utf-8')

    assert 'Gerar sugestao financeira' in template
    assert 'ir-sugestao-financeira-modal' in template
    assert 'Criar despesa' in template
    assert 'Criar lancamento' in js
    assert 'ir-sugestao-categoria-cartao-info' in template
    assert 'id="ir-sugestao-categoria-cartao"' not in template
    assert "categoria_cartao_id:" not in js
