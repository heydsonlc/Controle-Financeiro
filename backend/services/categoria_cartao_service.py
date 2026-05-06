from decimal import Decimal, InvalidOperation
from datetime import datetime

from sqlalchemy import func

try:
    from backend.models import (
        db,
        CartaoCategoriaLimite,
        Categoria,
        CategoriaCartao,
        CategoriaCartaoDespesa,
        ItemDespesa,
    )
    from backend.services.perfil_financeiro_service import PerfilFinanceiroService
except ImportError:
    from models import (
        db,
        CartaoCategoriaLimite,
        Categoria,
        CategoriaCartao,
        CategoriaCartaoDespesa,
        ItemDespesa,
    )
    from services.perfil_financeiro_service import PerfilFinanceiroService


class CategoriaCartaoService:
    @staticmethod
    def _perfil_id():
        return PerfilFinanceiroService.obter_perfil_ativo_id()

    @staticmethod
    def listar_categorias(ativo=None):
        query = PerfilFinanceiroService.aplicar_perfil_query(CategoriaCartao.query, CategoriaCartao)
        if ativo is not None:
            query = query.filter(CategoriaCartao.ativo == bool(ativo))
        return query.order_by(CategoriaCartao.nome.asc()).all()

    @staticmethod
    def criar_categoria(nome, descricao='', cor='#6c757d', icone=None, ativo=True):
        nome = CategoriaCartaoService._normalizar_nome(nome)
        CategoriaCartaoService._validar_nome_unico(nome)

        categoria = CategoriaCartao(
            perfil_financeiro_id=CategoriaCartaoService._perfil_id(),
            nome=nome,
            descricao=(descricao or '').strip() or None,
            cor=cor or '#6c757d',
            icone=(icone or '').strip()[:50] or None,
            ativo=bool(ativo),
        )
        db.session.add(categoria)
        return categoria

    @staticmethod
    def atualizar_categoria(categoria_cartao_id, **dados):
        categoria = CategoriaCartaoService._validar_categoria_cartao(categoria_cartao_id)

        if 'nome' in dados and dados.get('nome') is not None:
            nome = CategoriaCartaoService._normalizar_nome(dados.get('nome'))
            CategoriaCartaoService._validar_nome_unico(nome, ignorar_id=categoria.id)
            categoria.nome = nome
        if 'descricao' in dados:
            categoria.descricao = (dados.get('descricao') or '').strip() or None
        if 'cor' in dados and dados.get('cor'):
            categoria.cor = dados.get('cor')
        if 'icone' in dados:
            categoria.icone = (dados.get('icone') or '').strip()[:50] or None
        if 'ativo' in dados and dados.get('ativo') is not None:
            categoria.ativo = bool(dados.get('ativo'))

        categoria.updated_at = datetime.utcnow()
        db.session.add(categoria)
        return categoria

    @staticmethod
    def desativar_categoria(categoria_cartao_id):
        categoria = CategoriaCartaoService._validar_categoria_cartao(categoria_cartao_id)
        categoria.ativo = False
        categoria.updated_at = datetime.utcnow()
        db.session.add(categoria)
        return categoria

    @staticmethod
    def listar_despesas_vinculadas(categoria_cartao_id, ativo=None):
        CategoriaCartaoService._validar_categoria_cartao(categoria_cartao_id)
        query = CategoriaCartaoDespesa.query.filter_by(
            categoria_cartao_id=int(categoria_cartao_id),
            perfil_financeiro_id=CategoriaCartaoService._perfil_id(),
        )
        if ativo is not None:
            query = query.filter(CategoriaCartaoDespesa.ativo == bool(ativo))
        return query.order_by(CategoriaCartaoDespesa.id.asc()).all()

    @staticmethod
    def vincular_categoria_despesa(categoria_cartao_id, categoria_id, ativo=True):
        categoria_cartao = CategoriaCartaoService._validar_categoria_cartao(categoria_cartao_id)
        categoria = CategoriaCartaoService._validar_categoria_despesa(categoria_id)

        if ativo:
            CategoriaCartaoService._validar_categoria_despesa_sem_vinculo_ativo(
                categoria.id,
                ignorar_categoria_cartao_id=categoria_cartao.id,
            )

        existente = CategoriaCartaoDespesa.query.filter_by(
            categoria_cartao_id=categoria_cartao.id,
            categoria_id=categoria.id,
            perfil_financeiro_id=CategoriaCartaoService._perfil_id(),
        ).first()

        if existente:
            existente.ativo = bool(ativo)
            existente.updated_at = datetime.utcnow()
            db.session.add(existente)
            return existente, False

        vinculo = CategoriaCartaoDespesa(
            perfil_financeiro_id=CategoriaCartaoService._perfil_id(),
            categoria_cartao_id=categoria_cartao.id,
            categoria_id=categoria.id,
            ativo=bool(ativo),
        )
        db.session.add(vinculo)
        return vinculo, True

    @staticmethod
    def desvincular_categoria_despesa(categoria_cartao_id, categoria_id):
        categoria_cartao_id = CategoriaCartaoService._to_int(categoria_cartao_id)
        categoria_id = CategoriaCartaoService._to_int(categoria_id)
        vinculo = CategoriaCartaoDespesa.query.filter_by(
            categoria_cartao_id=categoria_cartao_id,
            categoria_id=categoria_id,
            perfil_financeiro_id=CategoriaCartaoService._perfil_id(),
        ).first()
        if not vinculo:
            raise ValueError('Vinculo nao encontrado')

        vinculo.ativo = False
        vinculo.updated_at = datetime.utcnow()
        db.session.add(vinculo)
        return vinculo

    @staticmethod
    def resolver_categoria_cartao_por_categoria_despesa(categoria_id):
        categoria_id = CategoriaCartaoService._to_int(categoria_id)
        if not categoria_id:
            return None

        vinculos = CategoriaCartaoDespesa.query.join(CategoriaCartao).filter(
            CategoriaCartaoDespesa.categoria_id == categoria_id,
            PerfilFinanceiroService.condicao_perfil(CategoriaCartaoDespesa),
            CategoriaCartaoDespesa.ativo == True,
            CategoriaCartao.ativo == True,
            PerfilFinanceiroService.condicao_perfil(CategoriaCartao),
        ).all()

        if len(vinculos) > 1:
            raise ValueError('Categoria de despesa possui mais de uma Categoria do Cartao ativa')
        if not vinculos:
            return None
        return vinculos[0].categoria_cartao_id

    @staticmethod
    def listar_limites_cartao(cartao_id, ativo=None):
        CategoriaCartaoService._validar_cartao(cartao_id)
        query = CartaoCategoriaLimite.query.filter_by(
            cartao_id=int(cartao_id),
            perfil_financeiro_id=CategoriaCartaoService._perfil_id(),
        )
        if ativo is not None:
            query = query.filter(CartaoCategoriaLimite.ativo == bool(ativo))
        return query.order_by(CartaoCategoriaLimite.id.asc()).all()

    @staticmethod
    def vincular_categoria_cartao_ao_cartao(
        cartao_id,
        categoria_cartao_id,
        limite_mensal=0,
        vigencia_inicio=None,
        vigencia_fim=None,
        ativo=True,
    ):
        cartao = CategoriaCartaoService._validar_cartao(cartao_id)
        categoria_cartao = CategoriaCartaoService._validar_categoria_cartao(categoria_cartao_id)
        limite = CategoriaCartaoService._parse_decimal(limite_mensal)

        existente = CartaoCategoriaLimite.query.filter_by(
            cartao_id=cartao.id,
            categoria_cartao_id=categoria_cartao.id,
            perfil_financeiro_id=CategoriaCartaoService._perfil_id(),
        ).first()

        if existente:
            existente.limite_mensal = limite
            existente.vigencia_inicio = CategoriaCartaoService._parse_date(vigencia_inicio)
            existente.vigencia_fim = CategoriaCartaoService._parse_date(vigencia_fim)
            existente.ativo = bool(ativo)
            existente.updated_at = datetime.utcnow()
            db.session.add(existente)
            return existente, False

        registro = CartaoCategoriaLimite(
            perfil_financeiro_id=CategoriaCartaoService._perfil_id(),
            cartao_id=cartao.id,
            categoria_cartao_id=categoria_cartao.id,
            limite_mensal=limite,
            vigencia_inicio=CategoriaCartaoService._parse_date(vigencia_inicio),
            vigencia_fim=CategoriaCartaoService._parse_date(vigencia_fim),
            ativo=bool(ativo),
        )
        db.session.add(registro)
        return registro, True

    @staticmethod
    def atualizar_limite(cartao_id, limite_id, **dados):
        CategoriaCartaoService._validar_cartao(cartao_id)
        limite = CategoriaCartaoService._obter_limite(cartao_id, limite_id)

        if 'limite_mensal' in dados and dados.get('limite_mensal') is not None:
            limite.limite_mensal = CategoriaCartaoService._parse_decimal(dados.get('limite_mensal'))
        if 'vigencia_inicio' in dados:
            limite.vigencia_inicio = CategoriaCartaoService._parse_date(dados.get('vigencia_inicio'))
        if 'vigencia_fim' in dados:
            limite.vigencia_fim = CategoriaCartaoService._parse_date(dados.get('vigencia_fim'))
        if 'ativo' in dados and dados.get('ativo') is not None:
            limite.ativo = bool(dados.get('ativo'))

        limite.updated_at = datetime.utcnow()
        db.session.add(limite)
        return limite

    @staticmethod
    def desativar_limite(cartao_id, limite_id):
        limite = CategoriaCartaoService._obter_limite(cartao_id, limite_id)
        limite.ativo = False
        limite.updated_at = datetime.utcnow()
        db.session.add(limite)
        return limite

    @staticmethod
    def validar_categoria_cartao_disponivel_no_cartao(cartao_id, categoria_cartao_id):
        cartao_id = CategoriaCartaoService._to_int(cartao_id)
        categoria_cartao_id = CategoriaCartaoService._to_int(categoria_cartao_id)
        if not cartao_id or not categoria_cartao_id:
            return False

        return CartaoCategoriaLimite.query.join(CategoriaCartao).filter(
            CartaoCategoriaLimite.cartao_id == cartao_id,
            CartaoCategoriaLimite.categoria_cartao_id == categoria_cartao_id,
            PerfilFinanceiroService.condicao_perfil(CartaoCategoriaLimite),
            CartaoCategoriaLimite.ativo == True,
            CategoriaCartao.ativo == True,
            PerfilFinanceiroService.condicao_perfil(CategoriaCartao),
        ).first() is not None

    @staticmethod
    def obter_limite_cartao(cartao_id, categoria_cartao_id):
        cartao_id = CategoriaCartaoService._to_int(cartao_id)
        categoria_cartao_id = CategoriaCartaoService._to_int(categoria_cartao_id)
        if not cartao_id or not categoria_cartao_id:
            return None
        return CartaoCategoriaLimite.query.filter_by(
            cartao_id=cartao_id,
            categoria_cartao_id=categoria_cartao_id,
            perfil_financeiro_id=CategoriaCartaoService._perfil_id(),
            ativo=True,
        ).first()

    @staticmethod
    def resolver_categoria_cartao_para_lancamento(cartao_id, categoria_id=None, categoria_cartao_id=None):
        categoria_cartao_id = CategoriaCartaoService._to_int(categoria_cartao_id)
        if categoria_cartao_id:
            categoria = CategoriaCartaoService._validar_categoria_cartao(categoria_cartao_id)
            return {
                'categoria_cartao_id': categoria_cartao_id,
                'categoria_cartao_nome': categoria.nome,
                'origem': 'manual',
                'vinculada_ao_cartao': CategoriaCartaoService.validar_categoria_cartao_disponivel_no_cartao(
                    cartao_id,
                    categoria_cartao_id,
                ),
            }

        resolvida = CategoriaCartaoService.resolver_categoria_cartao_por_categoria_despesa(categoria_id)
        if not resolvida:
            return {
                'categoria_cartao_id': None,
                'categoria_cartao_nome': None,
                'origem': None,
                'vinculada_ao_cartao': False,
            }

        vinculada = CategoriaCartaoService.validar_categoria_cartao_disponivel_no_cartao(cartao_id, resolvida)
        categoria_resolvida = CategoriaCartaoService._validar_categoria_cartao(resolvida)
        if not vinculada:
            return {
                'categoria_cartao_id': None,
                'categoria_cartao_resolvida_id': resolvida,
                'categoria_cartao_nome': categoria_resolvida.nome,
                'origem': 'categoria_cartao_nao_vinculada',
                'vinculada_ao_cartao': False,
            }

        return {
            'categoria_cartao_id': resolvida,
            'categoria_cartao_nome': categoria_resolvida.nome,
            'origem': 'mapa_categoria_despesa',
            'vinculada_ao_cartao': True,
        }

    @staticmethod
    def _validar_nome_unico(nome, ignorar_id=None):
        query = CategoriaCartao.query.filter(
            func.lower(CategoriaCartao.nome) == nome.lower(),
            PerfilFinanceiroService.condicao_perfil(CategoriaCartao),
        )
        if ignorar_id:
            query = query.filter(CategoriaCartao.id != int(ignorar_id))
        if query.first():
            raise ValueError('Ja existe uma Categoria do Cartao com este nome')

    @staticmethod
    def _validar_categoria_cartao(categoria_cartao_id):
        categoria_cartao_id = CategoriaCartaoService._to_int(categoria_cartao_id)
        if not categoria_cartao_id:
            raise ValueError('categoria_cartao_id invalido')
        categoria = CategoriaCartao.query.filter(
            CategoriaCartao.id == categoria_cartao_id,
            PerfilFinanceiroService.condicao_perfil(CategoriaCartao),
        ).first()
        if not categoria:
            raise ValueError('Categoria do Cartao nao encontrada')
        return categoria

    @staticmethod
    def _validar_categoria_despesa(categoria_id):
        categoria_id = CategoriaCartaoService._to_int(categoria_id)
        if not categoria_id:
            raise ValueError('categoria_id invalido')
        categoria = Categoria.query.get(categoria_id)
        if not categoria:
            raise ValueError('Categoria de despesa nao encontrada')
        return categoria

    @staticmethod
    def _validar_categoria_despesa_sem_vinculo_ativo(categoria_id, ignorar_categoria_cartao_id=None):
        query = CategoriaCartaoDespesa.query.filter(
            CategoriaCartaoDespesa.categoria_id == categoria_id,
            PerfilFinanceiroService.condicao_perfil(CategoriaCartaoDespesa),
            CategoriaCartaoDespesa.ativo == True,
        )
        if ignorar_categoria_cartao_id:
            query = query.filter(CategoriaCartaoDespesa.categoria_cartao_id != int(ignorar_categoria_cartao_id))
        if query.first():
            raise ValueError('Categoria de despesa ja vinculada a outra Categoria do Cartao ativa')

    @staticmethod
    def _validar_cartao(cartao_id):
        cartao_id = CategoriaCartaoService._to_int(cartao_id)
        if not cartao_id:
            raise ValueError('cartao_id invalido')
        cartao = ItemDespesa.query.filter(
            ItemDespesa.id == cartao_id,
            PerfilFinanceiroService.condicao_perfil(ItemDespesa),
        ).first()
        if not cartao or cartao.tipo != 'Agregador':
            raise ValueError('Cartao invalido')
        return cartao

    @staticmethod
    def _obter_limite(cartao_id, limite_id):
        limite_id = CategoriaCartaoService._to_int(limite_id)
        if not limite_id:
            raise ValueError('limite_id invalido')
        limite = CartaoCategoriaLimite.query.filter_by(
            id=limite_id,
            cartao_id=int(cartao_id),
            perfil_financeiro_id=CategoriaCartaoService._perfil_id(),
        ).first()
        if not limite:
            raise ValueError('Limite nao encontrado')
        return limite

    @staticmethod
    def _normalizar_nome(nome):
        nome = (nome or '').strip()
        if not nome:
            raise ValueError('Nome e obrigatorio')
        return nome

    @staticmethod
    def _parse_decimal(value):
        if value is None or value == '':
            return Decimal('0')
        try:
            return Decimal(str(value)).quantize(Decimal('0.01'))
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError('limite_mensal invalido')

    @staticmethod
    def _parse_date(value):
        if not value:
            return None
        if hasattr(value, 'isoformat') and not isinstance(value, str):
            return value
        try:
            return datetime.strptime(str(value)[:10], '%Y-%m-%d').date()
        except (TypeError, ValueError):
            raise ValueError('Data invalida')

    @staticmethod
    def _to_int(value):
        try:
            if value is None:
                return None
            if isinstance(value, str) and value.strip() == '':
                return None
            return int(value)
        except (TypeError, ValueError):
            return None
