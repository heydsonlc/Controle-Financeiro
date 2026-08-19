from datetime import datetime
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
        """
        TX-ATOMIC-1: usa apenas flush(), nunca commit() — este service pode ser chamado
        no meio de uma transacao maior (ex.: ContaBancariaService.criar_movimento()), e um
        commit() aqui finalizaria prematuramente a transacao do chamador. A persistencia da
        criacao idempotente dos perfis padrao fica a cargo do hook global
        `commit_pending_session` (backend/app.py, teardown_request), que comita ao fim de
        qualquer requisicao bem-sucedida com mudancas pendentes.
        """
        for dados in PERFIS_INICIAIS:
            perfil = PerfilFinanceiro.query.filter_by(nome=dados['nome']).first()
            if not perfil:
                perfil = PerfilFinanceiro(**dados, ativo=True, padrao=dados['nome'] == 'Pessoal')
                db.session.add(perfil)
            else:
                perfil.tipo = perfil.tipo or dados['tipo']
                perfil.avatar = perfil.avatar or dados['avatar']
                perfil.cor = perfil.cor or dados['cor']

        db.session.flush()

        if not PerfilFinanceiro.query.filter_by(padrao=True, ativo=True).first():
            perfil_padrao = PerfilFinanceiro.query.filter_by(nome='Pessoal').first()
            if perfil_padrao:
                perfil_padrao.ativo = True
                perfil_padrao.padrao = True
                db.session.flush()

        return PerfilFinanceiro.query.filter(
            PerfilFinanceiro.nome.in_([perfil['nome'] for perfil in PERFIS_INICIAIS])
        ).order_by(PerfilFinanceiro.id.asc()).all()

    @staticmethod
    def listar_perfis_config():
        PerfilFinanceiroService.obter_ou_criar_perfis_iniciais()
        return PerfilFinanceiro.query.order_by(PerfilFinanceiro.ativo.desc(), PerfilFinanceiro.nome.asc()).all()

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
        perfil = PerfilFinanceiro.query.filter_by(padrao=True, ativo=True).order_by(PerfilFinanceiro.id.asc()).first()
        if perfil:
            return perfil
        perfil = PerfilFinanceiro.query.filter_by(nome='Pessoal', ativo=True).first()
        if perfil:
            return perfil
        perfil = PerfilFinanceiro.query.filter_by(ativo=True).order_by(PerfilFinanceiro.id.asc()).first()
        if perfil:
            return perfil
        perfil = PerfilFinanceiro.query.filter_by(nome='Pessoal').first()
        if perfil:
            perfil.ativo = True
            perfil.padrao = True
            db.session.flush()
            return perfil
        perfil = PerfilFinanceiro(nome='Pessoal', tipo='PESSOAL', avatar='PE', cor='#2563eb', ativo=True, padrao=True)
        db.session.add(perfil)
        db.session.flush()
        return perfil

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
    def criar_perfil(dados):
        dados = dados or {}
        nome = str(dados.get('nome') or '').strip()
        if not nome:
            raise ValueError('Nome do perfil financeiro e obrigatorio')
        if PerfilFinanceiro.query.filter_by(nome=nome).first():
            raise ValueError('Ja existe perfil financeiro com este nome')

        tipo = PerfilFinanceiroService._normalizar_tipo(dados.get('tipo'))
        perfil = PerfilFinanceiro(
            nome=nome,
            tipo=tipo,
            documento=PerfilFinanceiroService._texto_opcional(dados.get('documento'), 32),
            avatar=PerfilFinanceiroService._avatar(dados.get('avatar') or nome),
            logo_url=PerfilFinanceiroService._texto_opcional(dados.get('logo_url'), 255),
            cor=PerfilFinanceiroService._cor(dados.get('cor')),
            ativo=bool(dados.get('ativo', True)),
            padrao=False,
        )
        db.session.add(perfil)
        db.session.flush()
        if dados.get('padrao') and perfil.ativo:
            PerfilFinanceiroService.definir_perfil_padrao(perfil.id)
        return perfil

    @staticmethod
    def atualizar_perfil(perfil_id, dados):
        perfil = PerfilFinanceiro.query.get(perfil_id)
        if not perfil:
            raise ValueError('Perfil financeiro nao encontrado')
        dados = dados or {}

        if 'nome' in dados:
            nome = str(dados.get('nome') or '').strip()
            if not nome:
                raise ValueError('Nome do perfil financeiro e obrigatorio')
            existente = PerfilFinanceiro.query.filter(
                PerfilFinanceiro.nome == nome,
                PerfilFinanceiro.id != perfil.id,
            ).first()
            if existente:
                raise ValueError('Ja existe perfil financeiro com este nome')
            perfil.nome = nome

        if 'tipo' in dados:
            perfil.tipo = PerfilFinanceiroService._normalizar_tipo(dados.get('tipo'))
        if 'documento' in dados:
            perfil.documento = PerfilFinanceiroService._texto_opcional(dados.get('documento'), 32)
        if 'avatar' in dados:
            perfil.avatar = PerfilFinanceiroService._avatar(dados.get('avatar') or perfil.nome)
        if 'logo_url' in dados:
            perfil.logo_url = PerfilFinanceiroService._texto_opcional(dados.get('logo_url'), 255)
        if 'cor' in dados:
            perfil.cor = PerfilFinanceiroService._cor(dados.get('cor'))
        if 'ativo' in dados:
            if bool(dados.get('ativo')):
                perfil.ativo = True
            else:
                PerfilFinanceiroService.inativar_perfil(perfil.id)

        perfil.updated_at = datetime.utcnow()
        if dados.get('padrao') and perfil.ativo:
            PerfilFinanceiroService.definir_perfil_padrao(perfil.id)
        return perfil

    @staticmethod
    def inativar_perfil(perfil_id, sessao=None):
        perfil = PerfilFinanceiro.query.get(perfil_id)
        if not perfil:
            raise ValueError('Perfil financeiro nao encontrado')
        if not perfil.ativo:
            return perfil

        ativos = PerfilFinanceiro.query.filter_by(ativo=True).count()
        if ativos <= 1:
            raise ValueError('Nao e possivel inativar o unico perfil ativo')

        perfil_ativo_id = PerfilFinanceiroService._session_get(sessao or {}, PERFIL_SESSION_KEY)
        if perfil_ativo_id and int(perfil_ativo_id) == int(perfil.id):
            raise ValueError('Selecione outro perfil antes de inativar o perfil ativo')

        perfil.ativo = False
        perfil.padrao = False
        perfil.updated_at = datetime.utcnow()
        if not PerfilFinanceiro.query.filter_by(padrao=True, ativo=True).filter(PerfilFinanceiro.id != perfil.id).first():
            novo_padrao = PerfilFinanceiro.query.filter(
                PerfilFinanceiro.ativo == True,  # noqa: E712
                PerfilFinanceiro.id != perfil.id,
            ).order_by(PerfilFinanceiro.id.asc()).first()
            if novo_padrao:
                novo_padrao.padrao = True
        return perfil

    @staticmethod
    def reativar_perfil(perfil_id):
        perfil = PerfilFinanceiro.query.get(perfil_id)
        if not perfil:
            raise ValueError('Perfil financeiro nao encontrado')
        perfil.ativo = True
        perfil.updated_at = datetime.utcnow()
        if not PerfilFinanceiro.query.filter_by(padrao=True, ativo=True).first():
            PerfilFinanceiroService.definir_perfil_padrao(perfil.id)
        return perfil

    @staticmethod
    def definir_perfil_padrao(perfil_id):
        perfil = PerfilFinanceiroService.obter_perfil_por_id(perfil_id)
        if not perfil:
            raise ValueError('Perfil financeiro ativo nao encontrado')
        PerfilFinanceiro.query.update({PerfilFinanceiro.padrao: False})
        perfil.padrao = True
        perfil.updated_at = datetime.utcnow()
        db.session.flush()
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

    @staticmethod
    def _normalizar_tipo(tipo):
        tipo_normalizado = str(tipo or 'OUTRO').strip().upper()
        return tipo_normalizado if tipo_normalizado in {'PESSOAL', 'EMPRESA', 'OUTRO'} else 'OUTRO'

    @staticmethod
    def _texto_opcional(valor, limite):
        texto = str(valor or '').strip()
        return texto[:limite] if texto else None

    @staticmethod
    def _avatar(valor):
        texto = str(valor or '').strip().upper()
        if not texto:
            return 'PF'
        partes = texto.split()
        if len(partes) >= 2:
            return f'{partes[0][0]}{partes[1][0]}'[:3]
        return texto[:3]

    @staticmethod
    def _cor(valor):
        texto = str(valor or '').strip()
        if not texto:
            return '#2563eb'
        if not texto.startswith('#'):
            texto = f'#{texto}'
        if len(texto) == 7:
            return texto
        return '#2563eb'
