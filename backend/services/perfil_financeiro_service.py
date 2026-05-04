from typing import Any, Mapping

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
        perfil_id = sessao.get(PERFIL_SESSION_KEY)
        perfil = PerfilFinanceiroService.obter_perfil_por_id(perfil_id)
        if perfil:
            return perfil

        perfil_padrao = PerfilFinanceiroService.obter_perfil_padrao()
        if perfil_padrao is not None and hasattr(sessao, '__setitem__'):
            sessao[PERFIL_SESSION_KEY] = perfil_padrao.id
        return perfil_padrao

    @staticmethod
    def definir_perfil_ativo(sessao, perfil_id):
        perfil = PerfilFinanceiroService.obter_perfil_por_id(perfil_id)
        if not perfil:
            return None

        sessao[PERFIL_SESSION_KEY] = perfil.id
        return perfil

    @staticmethod
    def serializar_perfil(perfil):
        if perfil is None:
            return None
        return perfil.to_dict()
