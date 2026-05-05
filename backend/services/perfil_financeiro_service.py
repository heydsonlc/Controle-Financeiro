from typing import Any, Mapping

from flask import has_request_context, session as flask_session
from sqlalchemy import or_

from backend.models import PerfilFinanceiro, db


PERFIL_SESSION_KEY = 'perfil_financeiro_id'

PERFIS_INICIAIS = (
    {
        'nome': 'Pessoal',
        'tipo': 'PESSOAL',
        'avatar': 'PE',
        'cor': '#2563eb',
    },
    {
        'nome': 'Empresa',
        'tipo': 'EMPRESA',
        'avatar': 'EM',
        'cor': '#0f766e',
    },
)


class PerfilFinanceiroService:
    @staticmethod
    def _session_get(sessao, chave, default=None):
        try:
            return sessao.get(chave, default)
        except RuntimeError:
            return default

    @staticmethod
    def _session_set(sessao, chave, valor):
        try:
            sessao[chave] = valor
            return True
        except RuntimeError:
            return False

    @staticmethod
    def obter_ou_criar_perfis_iniciais():
        criados = []

        for dados in PERFIS_INICIAIS:
            perfil = PerfilFinanceiro.query.filter_by(nome=dados['nome']).first()
            if not perfil:
                perfil = PerfilFinanceiro(**dados, ativo=True)
                db.session.add(perfil)
                criados.append(perfil)
            else:
                perfil.ativo = True
                perfil.tipo = perfil.tipo or dados['tipo']
                perfil.avatar = perfil.avatar or dados['avatar']
                perfil.cor = perfil.cor or dados['cor']

        if criados:
            db.session.commit()
        else:
            db.session.flush()

        return PerfilFinanceiro.query.filter(
            PerfilFinanceiro.nome.in_([perfil['nome'] for perfil in PERFIS_INICIAIS])
        ).order_by(PerfilFinanceiro.id.asc()).all()

    @staticmethod
    def listar_perfis_ativos():
        PerfilFinanceiroService.obter_ou_criar_perfis_iniciais()
        return PerfilFinanceiro.query.filter_by(ativo=True).order_by(PerfilFinanceiro.id.asc()).all()

    @staticmethod
    def obter_perfil_por_id(perfil_id):
        try:
            perfil_id_int = int(perfil_id)
        except (TypeError, ValueError):
            return None

        return PerfilFinanceiro.query.filter_by(id=perfil_id_int, ativo=True).first()

    @staticmethod
    def obter_perfil_padrao():
        PerfilFinanceiroService.obter_ou_criar_perfis_iniciais()
        perfil = PerfilFinanceiro.query.filter_by(nome='Pessoal', ativo=True).first()
        if perfil:
            return perfil
        return PerfilFinanceiro.query.filter_by(ativo=True).order_by(PerfilFinanceiro.id.asc()).first()

    @staticmethod
    def obter_perfil_ativo(sessao: Mapping[str, Any]):
        PerfilFinanceiroService.obter_ou_criar_perfis_iniciais()
        perfil_id = PerfilFinanceiroService._session_get(sessao, PERFIL_SESSION_KEY)
        perfil = PerfilFinanceiroService.obter_perfil_por_id(perfil_id)
        if perfil:
            return perfil

        perfil_padrao = PerfilFinanceiroService.obter_perfil_padrao()
        if perfil_padrao is not None and hasattr(sessao, '__setitem__'):
            PerfilFinanceiroService._session_set(sessao, PERFIL_SESSION_KEY, perfil_padrao.id)
        return perfil_padrao

    @staticmethod
    def definir_perfil_ativo(sessao, perfil_id):
        perfil = PerfilFinanceiroService.obter_perfil_por_id(perfil_id)
        if not perfil:
            return None

        if not PerfilFinanceiroService._session_set(sessao, PERFIL_SESSION_KEY, perfil.id):
            return None
        return perfil

    @staticmethod
    def serializar_perfil(perfil):
        if perfil is None:
            return None
        return perfil.to_dict()

    @staticmethod
    def obter_perfil_ativo_id(sessao: Mapping[str, Any] | None = None):
        if sessao is None:
            sessao = flask_session if has_request_context() else {}
        perfil = PerfilFinanceiroService.obter_perfil_ativo(sessao)
        return perfil.id if perfil else None

    @staticmethod
    def aplicar_perfil_query(query, model, perfil_id=None):
        if not hasattr(model, 'perfil_financeiro_id'):
            return query
        perfil_id = perfil_id or PerfilFinanceiroService.obter_perfil_ativo_id()
        return query.filter(PerfilFinanceiroService.condicao_perfil(model, perfil_id))

    @staticmethod
    def condicao_perfil(model, perfil_id=None):
        perfil_id = perfil_id or PerfilFinanceiroService.obter_perfil_ativo_id()
        perfil = PerfilFinanceiroService.obter_perfil_por_id(perfil_id)
        if perfil and perfil.nome == 'Pessoal':
            return or_(model.perfil_financeiro_id == perfil_id, model.perfil_financeiro_id.is_(None))
        return model.perfil_financeiro_id == perfil_id

    @staticmethod
    def atribuir_perfil_ativo(obj, perfil_id=None):
        if hasattr(obj, 'perfil_financeiro_id') and getattr(obj, 'perfil_financeiro_id', None) is None:
            obj.perfil_financeiro_id = perfil_id or PerfilFinanceiroService.obter_perfil_ativo_id()
        return obj

    @staticmethod
    def pertence_ao_perfil(obj, perfil_id=None):
        if obj is None:
            return False
        if not hasattr(obj, 'perfil_financeiro_id'):
            return True
        perfil_id = perfil_id or PerfilFinanceiroService.obter_perfil_ativo_id()
        perfil_obj_id = getattr(obj, 'perfil_financeiro_id', None)
        if perfil_obj_id == perfil_id:
            return True
        perfil = PerfilFinanceiroService.obter_perfil_por_id(perfil_id)
        return perfil_obj_id is None and perfil is not None and perfil.nome == 'Pessoal'

    @staticmethod
    def validar_pertence_ao_perfil(obj, perfil_id=None):
        if not PerfilFinanceiroService.pertence_ao_perfil(obj, perfil_id=perfil_id):
            raise ValueError('Recurso nao encontrado no perfil financeiro ativo')
        return obj
