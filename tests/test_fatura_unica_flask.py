"""
Testes FIN-FATURA-UNICA-1 no Flask (SQLite em memoria): indice unico de fatura,
tratamento idempotente do conflito em CartaoService.get_or_create_fatura e a
migration Alembic d81f5a2b9c3e. A concorrencia real (PostgreSQL, processos Flask e
novo motor simultaneos) esta em tests/test_supabase_fatura_unica.py.
"""
import importlib.util
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from flask import Flask
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from backend.models import ConfigAgregador, Conta, ItemDespesa, db
from backend.services import cartao_service
from backend.services.cartao_service import CartaoService, _violou_fatura_unica

COMP = date(2027, 6, 1)
MIGRATION = next((Path(__file__).resolve().parent.parent / 'migrations' / 'versions').glob('d81f5a2b9c3e_*.py'))


@pytest.fixture()
def app():
    app = Flask(__name__)
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI='sqlite:///:memory:', SQLALCHEMY_TRACK_MODIFICATIONS=False)
    db.init_app(app)
    with app.app_context():
        db.create_all()
        cartao = ItemDespesa(nome='Cartao Unico', tipo='Agregador', ativo=True)
        db.session.add(cartao)
        db.session.flush()
        db.session.add(ConfigAgregador(item_despesa_id=cartao.id, dia_fechamento=25, dia_vencimento=10))
        db.session.commit()
        app.cartao_id = cartao.id
        yield app
        db.session.remove()
        db.drop_all()


def _fatura(cartao_id, comp=COMP, **extra):
    return Conta(item_despesa_id=cartao_id, mes_referencia=comp, descricao='Fatura', valor=Decimal('0'),
                 data_vencimento=comp.replace(day=10), is_fatura_cartao=True, cartao_competencia=comp, **extra)


def _faturas(cartao_id):
    return Conta.query.filter_by(item_despesa_id=cartao_id, is_fatura_cartao=True).all()


def test_indice_unico_impede_segunda_fatura_do_mesmo_cartao_e_competencia(app):
    db.session.add(_fatura(app.cartao_id))
    db.session.commit()
    db.session.add(_fatura(app.cartao_id))
    with pytest.raises(IntegrityError) as erro:
        db.session.commit()
    assert _violou_fatura_unica(erro.value)
    db.session.rollback()
    assert len(_faturas(app.cartao_id)) == 1


def test_indice_nao_afeta_outras_competencias_nem_contas_comuns(app):
    db.session.add_all([_fatura(app.cartao_id), _fatura(app.cartao_id, date(2027, 7, 1))])
    for _ in range(2):  # conta comum do mesmo item e mes: permitida, como antes
        db.session.add(Conta(item_despesa_id=app.cartao_id, mes_referencia=COMP, descricao='Comum', valor=Decimal('1'),
                             data_vencimento=COMP, is_fatura_cartao=False))
    db.session.commit()
    assert Conta.query.count() == 4


def test_get_or_create_fatura_e_idempotente(app):
    primeira = CartaoService.get_or_create_fatura(app.cartao_id, COMP)
    segunda = CartaoService.get_or_create_fatura(app.cartao_id, date(2027, 6, 20))
    assert primeira.id == segunda.id and len(_faturas(app.cartao_id)) == 1


def test_conflito_com_outra_transacao_devolve_a_fatura_existente(app, monkeypatch):
    """Simula a corrida: a outra transacao grava a fatura depois da consulta e antes do INSERT."""
    original = CartaoService.calcular_planejado

    def outra_transacao_cria_primeiro(cartao_id, competencia):
        db.session.execute(text(
            "insert into conta (item_despesa_id, mes_referencia, descricao, valor, data_vencimento, "
            "is_fatura_cartao, cartao_competencia, status_pagamento) "
            "values (:c, :m, 'Fatura concorrente', 0, :v, 1, :m, 'Pendente')"),
            {'c': cartao_id, 'm': COMP, 'v': COMP.replace(day=10)})
        db.session.commit()
        return original(cartao_id, competencia)

    monkeypatch.setattr(CartaoService, 'calcular_planejado', staticmethod(outra_transacao_cria_primeiro))
    fatura = CartaoService.get_or_create_fatura(app.cartao_id, COMP)
    assert fatura.descricao == 'Fatura concorrente'
    assert len(_faturas(app.cartao_id)) == 1


def test_outra_violacao_de_integridade_nao_e_engolida(app, monkeypatch):
    def falha_qualquer(*_args, **_kwargs):
        raise IntegrityError('insert', {}, Exception('NOT NULL constraint failed: conta.descricao'))

    monkeypatch.setattr(cartao_service.db.session, 'begin_nested', falha_qualquer)
    with pytest.raises(IntegrityError):
        CartaoService.get_or_create_fatura(app.cartao_id, COMP)


@pytest.mark.parametrize('original,esperado', [
    (SimpleNamespace(diag=SimpleNamespace(constraint_name='ux_conta_fatura_cartao_competencia')), True),
    (SimpleNamespace(diag=SimpleNamespace(constraint_name='conta_pkey')), False),
    (Exception('UNIQUE constraint failed: conta.item_despesa_id, conta.cartao_competencia'), True),
    (Exception('UNIQUE constraint failed: usuario.email'), False),
])
def test_reconhece_so_a_violacao_da_fatura_unica(original, esperado):
    assert _violou_fatura_unica(SimpleNamespace(orig=original)) is esperado


def _rodar_migration(conn, funcao='upgrade'):
    spec = importlib.util.spec_from_file_location('migration_fatura_unica', MIGRATION)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    with Operations.context(MigrationContext.configure(conn)):
        getattr(modulo, funcao)()


def _indice_existe(conn):
    return conn.exec_driver_sql(
        "select count(*) from sqlite_master where type = 'index' and name = 'ux_conta_fatura_cartao_competencia'"
    ).scalar() == 1


def test_migration_alembic_aborta_sem_alterar_nada_se_houver_duplicidade(app):
    with db.engine.begin() as conn:
        _rodar_migration(conn, 'downgrade')
        assert not _indice_existe(conn)
    db.session.add_all([_fatura(app.cartao_id), _fatura(app.cartao_id)])
    db.session.commit()
    with db.engine.begin() as conn:
        with pytest.raises(RuntimeError, match='duplicada'):
            _rodar_migration(conn)
        assert not _indice_existe(conn)
    assert len(_faturas(app.cartao_id)) == 2  # nada excluido nem consolidado


def test_migration_alembic_cria_o_indice_e_e_idempotente(app):
    with db.engine.begin() as conn:
        _rodar_migration(conn, 'downgrade')
        db.session.add(_fatura(app.cartao_id))
        _rodar_migration(conn)
        _rodar_migration(conn)
        assert _indice_existe(conn)


def test_indice_do_model_e_a_mesma_regra_da_migration_e_nao_e_recriado(app):
    with db.engine.begin() as conn:
        definicao = conn.exec_driver_sql(
            "select sql from sqlite_master where name = 'ux_conta_fatura_cartao_competencia'").scalar()
        _rodar_migration(conn)  # indice ja existe com a mesma definicao: nada a fazer
        assert conn.exec_driver_sql(
            "select sql from sqlite_master where name = 'ux_conta_fatura_cartao_competencia'").scalar() == definicao
    spec = importlib.util.spec_from_file_location('migration_fatura_unica_def', MIGRATION)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    assert modulo.definicao_confere(definicao, 'sqlite')


def test_migration_aborta_se_existir_indice_com_o_mesmo_nome_e_outra_regra(app):
    with db.engine.begin() as conn:
        conn.exec_driver_sql('drop index ux_conta_fatura_cartao_competencia')
        conn.exec_driver_sql('create unique index ux_conta_fatura_cartao_competencia on conta (item_despesa_id, '
                             'cartao_competencia, perfil_financeiro_id) where is_fatura_cartao = 1')
        with pytest.raises(RuntimeError, match='outra definicao'):
            _rodar_migration(conn)
