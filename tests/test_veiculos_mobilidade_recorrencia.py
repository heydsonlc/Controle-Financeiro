"""
VEIC-2: Testes de integração para ativação de modalidade de mobilidade e
criação de recorrências mensais de combustível.

Usa SQLite in-memory (mesmo padrão dos outros testes do projeto).
"""
from datetime import date
from decimal import Decimal

import pytest
from flask import Flask

from backend.models import (
    db,
    Categoria,
    CategoriaCartao,
    CategoriaCartaoDespesa,
    CartaoCategoriaLimite,
    ConfigAgregador,
    DespesaPrevista,
    ItemDespesa,
    MobilidadeCenarioAtivo,
    Veiculo,
)
from backend.services.mobilidade_service import (
    ativar_modalidade,
    criar_recorrencia_combustivel,
    evitar_recorrencia_duplicada,
    inativar_modalidade_atual,
    inativar_recorrencias_origem,
    obter_modalidade_ativa,
    previsualizar_ativacao_modalidade,
    resolver_categoria_cartao_para_mobilidade,
)
from backend.services.categoria_default import MOB_COMBUSTIVEL, obter_categoria_sistemica_id
from backend.routes.veiculos import veiculos_bp


@pytest.fixture()
def app_context():
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    app.register_blueprint(veiculos_bp, url_prefix='/api/veiculos')

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


# ---------------------------------------------------------------------------
# Fixtures helpers
# ---------------------------------------------------------------------------

def _categoria_mobilidade():
    cat = Categoria(nome='Mobilidade', cor='#1e40af', ativo=True)
    db.session.add(cat)
    db.session.flush()
    return cat


def _veiculo_com_combustivel(cat_id, valor_mensal=780.0):
    v = Veiculo(
        nome='Toyota Corolla',
        tipo='carro',
        combustivel='gasolina',
        autonomia_km_l=Decimal('12.5'),
        status='ATIVO',
        data_inicio=date(2026, 1, 1),
        categoria_combustivel_id=cat_id,
        combustivel_valor_mensal=Decimal(str(valor_mensal)),
    )
    db.session.add(v)
    db.session.flush()
    return v


def _veiculo_sem_combustivel(cat_id):
    v = Veiculo(
        nome='Civic Sem Comb',
        tipo='carro',
        combustivel='gasolina',
        autonomia_km_l=Decimal('11.0'),
        status='SIMULADO',
        categoria_combustivel_id=cat_id,
        combustivel_valor_mensal=None,
    )
    db.session.add(v)
    db.session.flush()
    return v


def _cartao():
    cartao = ItemDespesa(nome='Cartao Visa', tipo='Agregador', ativo=True, recorrente=True)
    db.session.add(cartao)
    db.session.flush()
    cfg = ConfigAgregador(item_despesa_id=cartao.id, dia_fechamento=25, dia_vencimento=5)
    db.session.add(cfg)
    db.session.flush()
    return cartao


def _categoria_cartao_mob():
    cc = CategoriaCartao(nome='Mobilidade CC', cor='#0088cc', ativo=True)
    db.session.add(cc)
    db.session.flush()
    return cc


def _vincular_cat_cartao(categoria_id, categoria_cartao_id, cartao_id):
    despesa_vinculo = CategoriaCartaoDespesa(
        categoria_id=categoria_id,
        categoria_cartao_id=categoria_cartao_id,
        ativo=True,
    )
    db.session.add(despesa_vinculo)
    limite = CartaoCategoriaLimite(
        cartao_id=cartao_id,
        categoria_cartao_id=categoria_cartao_id,
        limite_mensal=Decimal('2000'),
        ativo=True,
    )
    db.session.add(limite)
    db.session.flush()


# ---------------------------------------------------------------------------
# Testes: resolver_categoria_cartao_para_mobilidade
# ---------------------------------------------------------------------------

def test_resolver_sem_cartao(app_context):
    with app_context.app_context():
        cc_id, aviso = resolver_categoria_cartao_para_mobilidade(
            categoria_id=1, cartao_id=None,
        )
        assert cc_id is None
        assert aviso is None


def test_resolver_com_categoria_cartao_manual(app_context):
    with app_context.app_context():
        cc = _categoria_cartao_mob()
        cartao = _cartao()
        cc_id, aviso = resolver_categoria_cartao_para_mobilidade(
            categoria_id=None, cartao_id=cartao.id,
            categoria_cartao_id_manual=cc.id,
        )
        assert cc_id == cc.id
        assert aviso is None


def test_resolver_via_mapa_vinculado(app_context):
    with app_context.app_context():
        cat = _categoria_mobilidade()
        cc = _categoria_cartao_mob()
        cartao = _cartao()
        _vincular_cat_cartao(cat.id, cc.id, cartao.id)
        db.session.commit()

        cc_id, aviso = resolver_categoria_cartao_para_mobilidade(
            categoria_id=cat.id, cartao_id=cartao.id,
        )
        assert cc_id == cc.id
        assert aviso is None


def test_resolver_via_mapa_nao_vinculado_ao_cartao(app_context):
    with app_context.app_context():
        cat = _categoria_mobilidade()
        cc = _categoria_cartao_mob()
        # Vincula categoria->categoria_cartao mas NÃO ao cartão
        despesa_vinculo = CategoriaCartaoDespesa(
            categoria_id=cat.id, categoria_cartao_id=cc.id, ativo=True,
        )
        db.session.add(despesa_vinculo)
        cartao = _cartao()
        db.session.commit()

        cc_id, aviso = resolver_categoria_cartao_para_mobilidade(
            categoria_id=cat.id, cartao_id=cartao.id,
        )
        assert cc_id is None
        assert aviso is not None


# ---------------------------------------------------------------------------
# Testes: criar_recorrencia_combustivel
# ---------------------------------------------------------------------------

def test_criar_recorrencia_combustivel_pix(app_context):
    with app_context.app_context():
        cat = _categoria_mobilidade()
        v = _veiculo_com_combustivel(cat.id, 780.0)
        db.session.commit()

        rec, avisos = criar_recorrencia_combustivel(
            veiculo=v,
            meio_pagamento='pix',
            cartao_id=None,
            categoria_id=cat.id,
            categoria_cartao_id=None,
        )
        db.session.commit()

        assert rec.id is not None
        assert rec.recorrente is True
        assert rec.tipo_recorrencia == 'mensal'
        assert rec.meio_pagamento == 'pix'
        assert rec.origem_tipo == 'VEICULO'
        assert rec.origem_id == v.id
        assert rec.origem_contexto == 'combustivel_mensal'
        assert rec.categoria_cartao_id is None
        assert float(rec.valor) == pytest.approx(780.0)


def test_criar_recorrencia_combustivel_cartao_com_cat_cartao(app_context):
    with app_context.app_context():
        cat_id = obter_categoria_sistemica_id(MOB_COMBUSTIVEL)
        cc = _categoria_cartao_mob()
        cartao = _cartao()
        _vincular_cat_cartao(cat_id, cc.id, cartao.id)
        v = _veiculo_com_combustivel(cat_id, 650.0)
        db.session.commit()

        rec, avisos = criar_recorrencia_combustivel(
            veiculo=v,
            meio_pagamento='cartao',
            cartao_id=cartao.id,
            categoria_id=cat_id,
            categoria_cartao_id=None,
        )
        db.session.commit()

        assert rec.cartao_id == cartao.id
        assert rec.categoria_cartao_id == cc.id
        assert not avisos


def test_criar_recorrencia_sem_meio_sem_cat_cartao_retorna_aviso(app_context):
    with app_context.app_context():
        cat = _categoria_mobilidade()
        cartao = _cartao()
        v = _veiculo_com_combustivel(cat.id, 500.0)
        db.session.commit()

        rec, avisos = criar_recorrencia_combustivel(
            veiculo=v,
            meio_pagamento='cartao',
            cartao_id=cartao.id,
            categoria_id=cat.id,
            categoria_cartao_id=None,
        )
        db.session.commit()

        assert rec.id is not None  # criada sem erro
        assert rec.categoria_cartao_id is None
        assert any('Categoria do Cartao' in a for a in avisos)


def test_criar_recorrencia_sem_combustivel_levanta_erro(app_context):
    with app_context.app_context():
        cat = _categoria_mobilidade()
        v = _veiculo_sem_combustivel(cat.id)
        db.session.commit()

        with pytest.raises(ValueError, match='combustivel'):
            criar_recorrencia_combustivel(
                veiculo=v, meio_pagamento='pix',
                cartao_id=None, categoria_id=cat.id, categoria_cartao_id=None,
            )


# ---------------------------------------------------------------------------
# Testes: evitar_recorrencia_duplicada
# ---------------------------------------------------------------------------

def test_nao_duplica_recorrencia(app_context):
    with app_context.app_context():
        cat = _categoria_mobilidade()
        v = _veiculo_com_combustivel(cat.id, 780.0)
        db.session.commit()

        rec1, _ = criar_recorrencia_combustivel(v, 'pix', None, cat.id, None)
        db.session.commit()
        assert evitar_recorrencia_duplicada('VEICULO', v.id, 'combustivel_mensal') is True

        # Segunda chamada deve retornar a mesma recorrência (atualizada, não duplicada)
        rec2, _ = criar_recorrencia_combustivel(v, 'debito', None, cat.id, None)
        db.session.commit()
        assert rec1.id == rec2.id
        total = ItemDespesa.query.filter_by(
            origem_tipo='VEICULO', origem_id=v.id,
            origem_contexto='combustivel_mensal', recorrente=True,
        ).count()
        assert total == 1


# ---------------------------------------------------------------------------
# Testes: inativar_recorrencias_origem
# ---------------------------------------------------------------------------

def test_inativar_recorrencias_origem(app_context):
    with app_context.app_context():
        cat = _categoria_mobilidade()
        v = _veiculo_com_combustivel(cat.id, 800.0)
        db.session.commit()

        criar_recorrencia_combustivel(v, 'pix', None, cat.id, None)
        db.session.commit()

        count = inativar_recorrencias_origem('VEICULO', v.id)
        db.session.commit()

        assert count == 1
        rec = ItemDespesa.query.filter_by(origem_tipo='VEICULO', origem_id=v.id, recorrente=True).first()
        assert rec.ativo is False


# ---------------------------------------------------------------------------
# Testes: ativar_modalidade
# ---------------------------------------------------------------------------

def test_ativar_modalidade_cria_cenario_e_recorrencia(app_context):
    with app_context.app_context():
        cat = _categoria_mobilidade()
        v = _veiculo_com_combustivel(cat.id, 780.0)
        db.session.commit()

        resultado = ativar_modalidade({
            'tipo_modalidade': 'VEICULO',
            'origem_id': v.id,
            'meio_pagamento': 'pix',
            'categoria_id': cat.id,
            'criar_recorrencia': True,
        })
        db.session.commit()

        cenario = resultado['cenario']
        assert cenario['tipo_modalidade'] == 'VEICULO'
        assert cenario['status'] == 'ATIVO'
        assert cenario['recorrencia_id'] is not None

        rec = resultado['recorrencia']
        assert rec is not None
        assert rec['origem_tipo'] == 'VEICULO'
        assert rec['origem_id'] == v.id
        assert rec['origem_contexto'] == 'combustivel_mensal'


def test_ativar_outro_veiculo_inativa_modalidade_anterior(app_context):
    with app_context.app_context():
        cat = _categoria_mobilidade()
        v1 = _veiculo_com_combustivel(cat.id, 780.0)
        v2 = _veiculo_com_combustivel(cat.id, 600.0)
        v2.nome = 'Honda Fit'
        db.session.commit()

        ativar_modalidade({
            'tipo_modalidade': 'VEICULO', 'origem_id': v1.id,
            'meio_pagamento': 'pix', 'categoria_id': cat.id,
        })
        db.session.commit()

        resultado2 = ativar_modalidade({
            'tipo_modalidade': 'VEICULO', 'origem_id': v2.id,
            'meio_pagamento': 'pix', 'categoria_id': cat.id,
        })
        db.session.commit()

        assert resultado2['anterior_inativado'] is not None
        ativos = MobilidadeCenarioAtivo.query.filter_by(status='ATIVO').all()
        assert len(ativos) == 1
        assert ativos[0].origem_id == v2.id

        # Recorrência do v1 deve estar inativa
        rec_v1 = ItemDespesa.query.filter_by(
            origem_tipo='VEICULO', origem_id=v1.id, recorrente=True,
        ).first()
        assert rec_v1 is None or rec_v1.ativo is False


def test_ativar_sem_meio_nao_cria_recorrencia(app_context):
    with app_context.app_context():
        cat = _categoria_mobilidade()
        v = _veiculo_com_combustivel(cat.id, 780.0)
        db.session.commit()

        resultado = ativar_modalidade({
            'tipo_modalidade': 'VEICULO',
            'origem_id': v.id,
            'categoria_id': cat.id,
        })
        db.session.commit()

        assert resultado['recorrencia'] is None
        assert any('meio_pagamento' in a for a in resultado['avisos'])


def test_ativar_veiculo_via_cartao_grava_cartao_id(app_context):
    with app_context.app_context():
        cat = _categoria_mobilidade()
        cartao = _cartao()
        v = _veiculo_com_combustivel(cat.id, 780.0)
        db.session.commit()

        resultado = ativar_modalidade({
            'tipo_modalidade': 'VEICULO',
            'origem_id': v.id,
            'meio_pagamento': 'cartao',
            'cartao_id': cartao.id,
            'categoria_id': cat.id,
        })
        db.session.commit()

        rec = resultado['recorrencia']
        assert rec is not None
        assert rec['cartao_id'] == cartao.id


def test_ativar_via_cartao_com_cat_cartao_configurada(app_context):
    with app_context.app_context():
        cat_id = obter_categoria_sistemica_id(MOB_COMBUSTIVEL)
        cc = _categoria_cartao_mob()
        cartao = _cartao()
        _vincular_cat_cartao(cat_id, cc.id, cartao.id)
        v = _veiculo_com_combustivel(cat_id, 780.0)
        db.session.commit()

        resultado = ativar_modalidade({
            'tipo_modalidade': 'VEICULO',
            'origem_id': v.id,
            'meio_pagamento': 'cartao',
            'cartao_id': cartao.id,
            'categoria_id': cat_id,
        })
        db.session.commit()

        rec = resultado['recorrencia']
        assert rec['categoria_cartao_id'] == cc.id
        assert not resultado['avisos']


# ---------------------------------------------------------------------------
# Testes: IPVA/Seguro/Licenciamento permanecem como DespesaPrevista
# ---------------------------------------------------------------------------

def test_despesas_anuais_permanecem_como_despesa_prevista(app_context):
    with app_context.app_context():
        cat = _categoria_mobilidade()
        v = Veiculo(
            nome='Onix IPVA',
            tipo='carro',
            combustivel='gasolina',
            autonomia_km_l=Decimal('13.0'),
            status='ATIVO',
            data_inicio=date(2026, 1, 1),
            categoria_combustivel_id=cat.id,
            combustivel_valor_mensal=Decimal('400'),
            ipva_categoria_id=cat.id,
            ipva_mes=3,
            ipva_valor=Decimal('2400'),
            seguro_categoria_id=cat.id,
            seguro_mes=4,
            seguro_valor=Decimal('1800'),
        )
        db.session.add(v)
        db.session.flush()

        # Simular projeção manual de IPVA como DespesaPrevista
        dp_ipva = DespesaPrevista(
            origem_tipo='VEICULO',
            origem_id=v.id,
            categoria_id=cat.id,
            data_prevista=date(2026, 3, 1),
            data_original_prevista=date(2026, 3, 1),
            data_atual_prevista=date(2026, 3, 1),
            valor_previsto=Decimal('2400'),
            status='PREVISTA',
            metadata_json='{"tipo_evento":"IPVA"}',
        )
        db.session.add(dp_ipva)
        db.session.commit()

        # Ativar modalidade — não deve remover nem confirmar o IPVA
        ativar_modalidade({
            'tipo_modalidade': 'VEICULO',
            'origem_id': v.id,
            'meio_pagamento': 'pix',
            'categoria_id': cat.id,
        })
        db.session.commit()

        dp_check = DespesaPrevista.query.filter_by(
            origem_tipo='VEICULO', origem_id=v.id, status='PREVISTA',
        ).first()
        assert dp_check is not None
        assert dp_check.id == dp_ipva.id


# ---------------------------------------------------------------------------
# Testes: obter_modalidade_ativa
# ---------------------------------------------------------------------------

def test_obter_modalidade_ativa_retorna_none_quando_inexistente(app_context):
    with app_context.app_context():
        assert obter_modalidade_ativa() is None


def test_obter_modalidade_ativa_retorna_cenario(app_context):
    with app_context.app_context():
        cat = _categoria_mobilidade()
        v = _veiculo_com_combustivel(cat.id, 780.0)
        db.session.commit()

        ativar_modalidade({
            'tipo_modalidade': 'VEICULO',
            'origem_id': v.id,
            'meio_pagamento': 'pix',
            'categoria_id': cat.id,
        })
        db.session.commit()

        ativo = obter_modalidade_ativa()
        assert ativo is not None
        assert ativo['tipo_modalidade'] == 'VEICULO'
        assert ativo['status'] == 'ATIVO'
        assert ativo['nome_origem'] == v.nome


# ---------------------------------------------------------------------------
# Testes: previsualizar_ativacao_modalidade
# ---------------------------------------------------------------------------

def test_previsualizar_retorna_recorrencia_esperada(app_context):
    with app_context.app_context():
        cat = _categoria_mobilidade()
        v = _veiculo_com_combustivel(cat.id, 780.0)
        db.session.commit()

        previa = previsualizar_ativacao_modalidade({
            'tipo_modalidade': 'VEICULO',
            'origem_id': v.id,
            'meio_pagamento': 'pix',
            'categoria_id': cat.id,
        })

        assert previa['tipo_modalidade'] == 'VEICULO'
        assert previa['recorrencia'] is not None
        assert previa['recorrencia']['valor'] == pytest.approx(780.0)
        assert 'IPVA' in ' '.join(previa['despesas_previstas'])


def test_previsualizar_tipo_invalido_levanta_erro(app_context):
    with app_context.app_context():
        with pytest.raises(ValueError):
            previsualizar_ativacao_modalidade({'tipo_modalidade': 'INVALIDO', 'origem_id': 1})


# ---------------------------------------------------------------------------
# Testes: endpoint HTTP via Flask test client
# ---------------------------------------------------------------------------

def test_endpoint_get_mobilidade_ativo(app_context):
    with app_context.test_client() as client:
        resp = client.get('/api/veiculos/mobilidade/ativo')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['data'] is None


def test_endpoint_ativar_sem_confirmado_retorna_400(app_context):
    with app_context.test_client() as client:
        resp = client.post('/api/veiculos/mobilidade/ativar',
                           json={'tipo_modalidade': 'VEICULO', 'origem_id': 1})
        assert resp.status_code == 400
        data = resp.get_json()
        assert 'confirmado' in data['error']
