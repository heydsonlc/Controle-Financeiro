"""
ServiÃ§o de CartÃ£o de CrÃ©dito - LÃ³gica de negÃ³cio

Este serviÃ§o implementa:
1. GeraÃ§Ã£o de faturas virtuais (planejado vs executado)
2. Controle de orÃ§amento por categoria
3. Consumo de orÃ§amento por lanÃ§amentos
4. Pagamento de faturas (planejado â†’ executado)
5. Alertas de estouro de orÃ§amento
"""
import calendar
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from decimal import Decimal, InvalidOperation
from sqlalchemy import func, and_
from sqlalchemy.exc import IntegrityError
from zoneinfo import ZoneInfo
import uuid
import logging

try:
    from backend.models import (db, Conta, ItemDespesa, ItemAgregado, FaturaConsolidadaInclusao,
                                OrcamentoAgregado, LancamentoAgregado, ConfigAgregador)
    from backend.services.categoria_cartao_service import CategoriaCartaoService
    from backend.services.perfil_financeiro_service import PerfilFinanceiroService
    from backend.services.gerador_recorrencia_service import flask_pode_gerar
    from backend.services.trava_financeira import travar, travar_um
except ImportError:
    from models import (db, Conta, ItemDespesa, ItemAgregado, FaturaConsolidadaInclusao,
                       OrcamentoAgregado, LancamentoAgregado, ConfigAgregador)
    from services.categoria_cartao_service import CategoriaCartaoService
    from services.perfil_financeiro_service import PerfilFinanceiroService
    from services.gerador_recorrencia_service import flask_pode_gerar
    from services.trava_financeira import travar, travar_um

logger = logging.getLogger(__name__)

INDICE_FATURA_UNICA = 'ux_conta_fatura_cartao_competencia'


def _violou_fatura_unica(exc):
    """True so para a violacao da unicidade de fatura (cartao + competencia); o resto propaga."""
    original = getattr(exc, 'orig', None)
    diag = getattr(original, 'diag', None)
    if diag is not None and getattr(diag, 'constraint_name', None):
        return diag.constraint_name == INDICE_FATURA_UNICA
    texto = str(original)
    return INDICE_FATURA_UNICA in texto or 'conta.item_despesa_id, conta.cartao_competencia' in texto  # SQLite


FUSO_CIVIL = ZoneInfo('America/Sao_Paulo')  # data civil da compra (FIN-CARTOES-FECHAMENTO-1)
REGRAS_DIA_FECHAMENTO = ('ATUAL', 'PROXIMO')


def _reais(valor):
    return f'{Decimal(valor):.2f}'


class ConfirmacaoConsolidadaNecessaria(ValueError):
    """FIN-CARTOES-FECHAMENTO-1 (D6): a operacao incluiria compra em fatura consolidada (FECHADA) sem a
    confirmacao especifica dela ({fatura_id, total_consolidado} iguais aos atuais). Nada e gravado."""

    def __init__(self, faturas):
        self.faturas = faturas
        partes = '; '.join(f"{f['competencia'][5:7]}/{f['competencia'][:4]} (total R$ {f['total_consolidado']} passa a "
                           f"R$ {f['total_novo']})" for f in faturas)
        super().__init__(f'Fatura consolidada: confirme a inclusao desta compra na fatura de {partes}.')


class CartaoService:
    """
    ServiÃ§o para gerenciamento completo de cartÃµes de crÃ©dito
    """

    @staticmethod
    def _primeiro_dia_mes(data_ou_competencia):
        if isinstance(data_ou_competencia, datetime):
            data_ou_competencia = data_ou_competencia.date()

        if isinstance(data_ou_competencia, date):
            return data_ou_competencia.replace(day=1)

        if isinstance(data_ou_competencia, str):
            valor = data_ou_competencia.strip()
            if len(valor) == 7:
                valor = f'{valor}-01'
            return datetime.strptime(valor, '%Y-%m-%d').date().replace(day=1)

        raise ValueError('Competencia invalida para calculo de fatura')

    @staticmethod
    def _intervalo_mes(data_ou_competencia):
        inicio_mes = CartaoService._primeiro_dia_mes(data_ou_competencia)
        inicio_mes_seguinte = inicio_mes + relativedelta(months=1)
        return inicio_mes, inicio_mes_seguinte

    # ========================================================================
    # FIN-CARTOES-FECHAMENTO-1 - competencia sugerida pelo fechamento do cartao
    # ========================================================================

    @staticmethod
    def dia_contratual(competencia, dia):
        """Dia `dia` no mes de `competencia`; 29-31 viram o ultimo dia do mes curto (financeiro.dia_contratual)."""
        ultimo = calendar.monthrange(competencia.year, competencia.month)[1]
        return date(competencia.year, competencia.month, min(int(dia), ultimo))

    @staticmethod
    def data_civil(valor):
        """Data civil da compra: 'AAAA-MM-DD' e date valem como estao; datetime com fuso vira a data de Brasilia
        (uma compra as 23h30 de Brasilia nao muda de dia por estar em UTC)."""
        if valor is None or valor == '':
            return None
        if isinstance(valor, datetime):
            return (valor.astimezone(FUSO_CIVIL) if valor.tzinfo else valor).date()
        if isinstance(valor, date):
            return valor
        return datetime.strptime(str(valor).strip()[:10], '%Y-%m-%d').date()

    @staticmethod
    def competencia_da_compra(data, dia_fechamento, dia_vencimento, regra='PROXIMO'):
        """Competencia (1o dia do mes do vencimento) da fatura que recebe uma compra feita em `data`.

        Mesma regra de financeiro.competencia_da_compra (comparadas numa grade de datas):
        - o ciclo fecha no dia contratual de fechamento do mes da compra; depois dele (ou nele, com a regra
          PROXIMO, o padrao) fecha no mes seguinte;
        - o vencimento e o primeiro dia contratual de vencimento depois do fechamento;
        - None se a configuracao for invalida ou se, por causa dos dias curtos, o mes do vencimento fugir do
          padrao do cartao (vence no mes do fechamento se o dia do vencimento e maior, senao no seguinte).
        """
        data = CartaoService.data_civil(data)
        regra = regra or 'PROXIMO'
        if data is None or dia_fechamento is None or dia_vencimento is None or regra not in REGRAS_DIA_FECHAMENTO:
            return None
        fechamento_dia, vencimento_dia = int(dia_fechamento), int(dia_vencimento)
        if not (1 <= fechamento_dia <= 31 and 1 <= vencimento_dia <= 31):
            return None
        mes = data.replace(day=1)
        fechamento = CartaoService.dia_contratual(mes, fechamento_dia)
        if data > fechamento or (data == fechamento and regra == 'PROXIMO'):
            mes = mes + relativedelta(months=1)
            fechamento = CartaoService.dia_contratual(mes, fechamento_dia)
        vencimento = CartaoService.dia_contratual(mes, vencimento_dia)
        if vencimento <= fechamento:
            vencimento = CartaoService.dia_contratual(mes + relativedelta(months=1), vencimento_dia)
        if vencimento.replace(day=1) != mes + relativedelta(months=0 if vencimento_dia > fechamento_dia else 1):
            return None  # ciclo ambiguo neste mes
        return vencimento.replace(day=1)

    _capacidades = {}

    @staticmethod
    def _capacidade(nome, teste):
        chave = (str(db.engine.url), nome)
        if chave not in CartaoService._capacidades:
            from sqlalchemy import inspect
            CartaoService._capacidades[chave] = teste(inspect(db.engine))
        return CartaoService._capacidades[chave]

    @staticmethod
    def suporta_fechamento_configuravel():
        """True se o banco ja tem config_agregador.compra_no_fechamento e fechamento_confirmado (migration
        FIN-CARTOES-FECHAMENTO-1). Sem elas o Flask funciona como antes, sem sugestao de competencia."""
        return CartaoService._capacidade('fechamento', lambda i: {'compra_no_fechamento', 'fechamento_confirmado'}
                                         <= {c['name'] for c in i.get_columns('config_agregador')})

    @staticmethod
    def suporta_competencia_sugerida():
        return CartaoService._capacidade('sugerida', lambda i: 'mes_fatura_sugerido'
                                         in {c['name'] for c in i.get_columns('lancamento_agregado')})

    @staticmethod
    def suporta_auditoria_consolidada():
        return CartaoService._capacidade('auditoria', lambda i: i.has_table('fatura_consolidada_inclusao'))

    @staticmethod
    def sugestao_competencia(cartao_id, data):
        """Sugestao do cartao para a data (como financeiro.sugestao_competencia): situacao SUGERIDA,
        NAO_CONFIRMADO, CICLO_AMBIGUO, SEM_CONFIGURACAO ou SEM_DATA, competencia e datas do ciclo."""
        config = ConfigAgregador.query.filter_by(item_despesa_id=cartao_id).first()
        dados = config.dados_fechamento() if config else {'compra_no_fechamento': 'PROXIMO', 'fechamento_confirmado': False}
        fechamento_dia = config.dia_fechamento if config else None
        vencimento_dia = config.dia_vencimento if config else None
        data = CartaoService.data_civil(data)
        competencia = None
        if not (fechamento_dia and vencimento_dia and 1 <= fechamento_dia <= 31 and 1 <= vencimento_dia <= 31):
            situacao = 'SEM_CONFIGURACAO'
        elif not dados['fechamento_confirmado']:
            situacao = 'NAO_CONFIRMADO'
        elif data is None:
            situacao = 'SEM_DATA'
        else:
            competencia = CartaoService.competencia_da_compra(data, fechamento_dia, vencimento_dia,
                                                              dados['compra_no_fechamento'])
            situacao = 'SUGERIDA' if competencia else 'CICLO_AMBIGUO'
        return {
            'situacao': situacao,
            'competencia': competencia,
            'fechamento': CartaoService.dia_contratual(
                competencia - relativedelta(months=0 if vencimento_dia > fechamento_dia else 1), fechamento_dia)
            if competencia else None,
            'vencimento': CartaoService.dia_contratual(competencia, vencimento_dia) if competencia else None,
            'dia_fechamento': fechamento_dia,
            'dia_vencimento': vencimento_dia,
            'compra_no_fechamento': dados['compra_no_fechamento'],
            'fechamento_confirmado': dados['fechamento_confirmado'],
        }

    @staticmethod
    def situacao_fatura(fatura):
        if fatura is None:
            return 'SEM_FATURA'
        if CartaoService.fatura_esta_paga(fatura):
            return 'PAGA'
        return 'FECHADA' if fatura.status_fatura == 'FECHADA' else 'ABERTA'

    # D6 - fatura consolidada so recebe compra com a confirmacao desta operacao, auditada.

    @staticmethod
    def total_consolidado(fatura):
        valor = fatura.valor_consolidado if fatura.valor_consolidado is not None else (fatura.valor_executado or 0)
        return Decimal(str(valor)).quantize(Decimal('0.01'))

    @staticmethod
    def _confirmada(fatura_id, total, confirmacoes):
        for item in confirmacoes or []:
            try:
                if int(item.get('fatura_id')) == fatura_id and Decimal(str(item.get('total_consolidado'))) == total:
                    return True
            except (AttributeError, TypeError, ValueError, InvalidOperation):
                continue
        return False

    @staticmethod
    def conferir_confirmacoes(inclusoes, confirmacoes):
        """inclusoes: {fatura_id: (fatura travada e relida, valor que entraria)}. Recusa se faltar a confirmacao
        de alguma fatura ou se o banco ainda nao tiver a auditoria (nenhuma inclusao sem registro)."""
        faltando = []
        for fatura, valor in inclusoes.values():
            total = CartaoService.total_consolidado(fatura)
            if not CartaoService._confirmada(fatura.id, total, confirmacoes):
                faltando.append({'fatura_id': fatura.id, 'competencia': fatura.cartao_competencia.isoformat(),
                                 'total_consolidado': _reais(total), 'valor_incluido': _reais(valor),
                                 'total_novo': _reais(total + Decimal(valor))})
        if faltando:
            raise ConfirmacaoConsolidadaNecessaria(faltando)
        if inclusoes and not CartaoService.suporta_auditoria_consolidada():
            raise ValueError('Fatura consolidada: este banco ainda nao registra a auditoria da inclusao '
                             '(migration pendente). Nada foi gravado.')

    @staticmethod
    def registrar_inclusao_consolidada(fatura, valor, operacao, compra_id=None, lancamento_id=None):
        """Atualiza o total consolidado (anterior + incluido) e grava a auditoria, na transacao do chamador."""
        anterior = CartaoService.total_consolidado(fatura)
        novo = anterior + Decimal(str(valor))
        fatura.valor_consolidado = novo
        usuario_id = None
        try:
            from flask_login import current_user
            if current_user and current_user.is_authenticated:
                usuario_id = current_user.id
        except Exception:  # fora de requisicao (scripts, testes)
            usuario_id = None
        db.session.add(FaturaConsolidadaInclusao(
            fatura_id=fatura.id, cartao_id=fatura.item_despesa_id, perfil_financeiro_id=fatura.perfil_financeiro_id,
            competencia=fatura.cartao_competencia, compra_id=compra_id, lancamento_id=lancamento_id,
            valor_incluido=Decimal(str(valor)), total_consolidado_anterior=anterior, total_consolidado_novo=novo,
            operacao=operacao, origem='FLASK', usuario_id=usuario_id))
        return novo

    # ========================================================================
    # GERAÃ‡ÃƒO E RECUPERAÃ‡ÃƒO DE FATURAS
    # ========================================================================

    @staticmethod
    def get_or_create_fatura(cartao_id, competencia):
        """
        Busca ou cria uma fatura virtual para o cartÃ£o + mÃªs

        A fatura sempre existe, mesmo sem lanÃ§amentos.
        Valor inicial = soma dos orÃ§amentos das categorias do cartÃ£o

        Args:
            cartao_id (int): ID do ItemDespesa (tipo 'Agregador')
            competencia (date): MÃªs de referÃªncia (YYYY-MM-01)

        Returns:
            Conta: Fatura do cartÃ£o (planejado ou executado)
        """
        # Normalizar competÃªncia para primeiro dia do mÃªs
        comp_primeiro_dia = CartaoService._primeiro_dia_mes(competencia)

        # Buscar fatura existente
        fatura = Conta.query.filter(
            Conta.item_despesa_id == cartao_id,
            PerfilFinanceiroService.condicao_perfil(Conta),
            Conta.is_fatura_cartao == True,
            Conta.cartao_competencia == comp_primeiro_dia,
        ).first()

        if fatura:
            return fatura

        # Criar nova fatura virtual
        cartao = ItemDespesa.query.filter(
            ItemDespesa.id == cartao_id,
            PerfilFinanceiroService.condicao_perfil(ItemDespesa),
        ).first()
        if not cartao or cartao.tipo != 'Agregador':
            raise ValueError(f'ItemDespesa {cartao_id} nÃ£o Ã© um cartÃ£o de crÃ©dito')

        # Buscar configuraÃ§Ã£o do cartÃ£o
        config = ConfigAgregador.query.filter_by(item_despesa_id=cartao_id).first()
        if not config:
            raise ValueError(f'CartÃ£o {cartao_id} sem configuraÃ§Ã£o de fechamento/vencimento')

        # Calcular valor planejado (soma dos orÃ§amentos)
        valor_planejado = CartaoService.calcular_planejado(cartao_id, comp_primeiro_dia)

        # Calcular data de vencimento baseada no dia de vencimento configurado
        # FIN-CARTOES-FECHAMENTO-1 (D4): dia contratual; 29-31 viram o ultimo dia do mes curto (antes, ValueError).
        data_vencimento = CartaoService.dia_contratual(comp_primeiro_dia, config.dia_vencimento)

        # FIN-FATURA-INTEGRIDADE-1: criar fatura trava o cartao (ordem global cartao -> faturas). Quem
        # segura o cartao (compra, recorrencia, importacao) nao ve surgir e ser paga uma fatura nova dele.
        CartaoService.travar_cartao(cartao_id)
        existente = Conta.query.filter(
            Conta.item_despesa_id == cartao_id,
            Conta.is_fatura_cartao == True,  # noqa: E712
            Conta.cartao_competencia == comp_primeiro_dia,
        ).first()
        if existente:
            db.session.commit()  # mesmo contrato do caminho de criacao (estado gravado)
            return existente  # criada por quem tinha o cartao antes

        # Criar fatura
        fatura = Conta(
            perfil_financeiro_id=cartao.perfil_financeiro_id,
            item_despesa_id=cartao_id,
            mes_referencia=comp_primeiro_dia,
            descricao=f'Fatura {cartao.nome} - {comp_primeiro_dia.strftime("%m/%Y")}',
            valor=valor_planejado,  # Inicialmente = planejado
            valor_planejado=valor_planejado,
            valor_executado=Decimal('0'),  # SerÃ¡ calculado ao pagar
            data_vencimento=data_vencimento,
            status_pagamento='Pendente',
            is_fatura_cartao=True,
            cartao_competencia=comp_primeiro_dia,
            estouro_orcamento=False
        )

        # FIN-FATURA-UNICA-1: a consulta acima nao basta com acessos simultaneos (Flask ou
        # novo aplicativo). O indice unico decide; o INSERT vai num savepoint para que,
        # se outra transacao criou a mesma fatura, a existente seja devolvida sem desfazer
        # o restante da transacao do chamador.
        try:
            with db.session.begin_nested():
                db.session.add(fatura)
        except IntegrityError as exc:
            if not _violou_fatura_unica(exc):
                raise
            existente = Conta.query.filter(
                Conta.item_despesa_id == cartao_id,
                Conta.is_fatura_cartao == True,
                Conta.cartao_competencia == comp_primeiro_dia,
            ).first()
            if existente is None:
                raise
            if existente.perfil_financeiro_id != cartao.perfil_financeiro_id:
                logger.warning('Fatura %s do cartao %s em perfil diferente do cartao', existente.id, cartao_id)
            logger.info('Fatura cartao_id=%s competencia=%s criada por outra transacao; usando a existente (id=%s)',
                        cartao_id, comp_primeiro_dia, existente.id)
            db.session.commit()  # mantem o contrato original: o chamador recebe estado gravado
            return existente

        db.session.commit()

        return fatura

    @staticmethod
    def calcular_planejado(cartao_id, competencia):
        """
        Calcula valor planejado da fatura = soma dos limites por Categoria do Cartao.

        Args:
            cartao_id (int): ID do cartÃ£o
            competencia (date): MÃªs de referÃªncia

        Returns:
            Decimal: Valor total orÃ§ado
        """
        comp_primeiro_dia = CartaoService._primeiro_dia_mes(competencia)

        limites_categoria_cartao = CategoriaCartaoService.listar_limites_cartao(cartao_id, ativo=True)
        if limites_categoria_cartao:
            return sum(
                (Decimal(str(limite.limite_mensal or 0)) for limite in limites_categoria_cartao),
                Decimal('0')
            )

        # Compatibilidade transitÃ³ria: cartÃµes antigos podem ainda ter apenas OrcamentoAgregado.
        itens_agregados = ItemAgregado.query.filter_by(
            item_despesa_id=cartao_id
        ).all()

        total_planejado = Decimal('0')

        for item in itens_agregados:
            # Buscar orÃ§amento vigente para essa categoria nessa competÃªncia
            orcamento = OrcamentoAgregado.query.filter(
                and_(
                    OrcamentoAgregado.item_agregado_id == item.id,
                    OrcamentoAgregado.ativo == True,
                    OrcamentoAgregado.vigencia_inicio <= comp_primeiro_dia,
                    (OrcamentoAgregado.vigencia_fim == None) |
                    (OrcamentoAgregado.vigencia_fim >= comp_primeiro_dia)
                )
            ).first()

            if orcamento:
                total_planejado += orcamento.valor_teto

        return total_planejado

    @staticmethod
    def calcular_executado(cartao_id, competencia):
        """
        Calcula valor executado da fatura = soma real dos lanÃ§amentos do cartao.

        Args:
            cartao_id (int): ID do cartÃ£o
            competencia (date): MÃªs de referÃªncia

        Returns:
            Decimal: Valor total gasto
        """
        comp_primeiro_dia, proximo_mes = CartaoService._intervalo_mes(competencia)

        # Soma por cartao_id para incluir a nova arquitetura e o grupo sem Categoria do Cartao.
        total_executado = db.session.query(
            func.coalesce(func.sum(LancamentoAgregado.valor), 0)
        ).filter(
            LancamentoAgregado.cartao_id == cartao_id,
            PerfilFinanceiroService.condicao_perfil(LancamentoAgregado),
            LancamentoAgregado.mes_fatura >= comp_primeiro_dia,
            LancamentoAgregado.mes_fatura < proximo_mes
        ).scalar()

        return Decimal(str(total_executado or 0))

    @staticmethod
    def _status_consumo(gasto, limite):
        gasto_decimal = Decimal(str(gasto or 0))
        limite_decimal = Decimal(str(limite or 0))

        if limite_decimal <= 0:
            return 'Estourado' if gasto_decimal > 0 else 'Normal'

        percentual = (gasto_decimal / limite_decimal) * Decimal('100')
        if percentual > 100:
            return 'Estourado'
        if percentual > 80:
            return 'Atencao'
        return 'Normal'

    @staticmethod
    def _calcular_percentual(gasto, limite):
        gasto_decimal = Decimal(str(gasto or 0))
        limite_decimal = Decimal(str(limite or 0))
        if limite_decimal <= 0:
            return 0
        return round(float((gasto_decimal / limite_decimal) * Decimal('100')), 2)

    @staticmethod
    def obter_resumo_fatura_por_categoria_cartao(cartao_id, mes_referencia):
        """
        Retorna consumo da fatura agrupado por Categoria do Cartao global.
        """
        cartao = ItemDespesa.query.filter(
            ItemDespesa.id == cartao_id,
            ItemDespesa.tipo == 'Agregador',
            PerfilFinanceiroService.condicao_perfil(ItemDespesa),
        ).first()
        if not cartao:
            raise ValueError('Cartao nao encontrado')

        mes_ref, proximo_mes = CartaoService._intervalo_mes(mes_referencia)
        limites = CategoriaCartaoService.listar_limites_cartao(cartao_id, ativo=True)

        grupos = {}
        ordem_grupos = []
        limite_total = Decimal('0')

        for limite in limites:
            categoria = limite.categoria_cartao
            key = f'categoria:{limite.categoria_cartao_id}'
            limite_mensal = Decimal(str(limite.limite_mensal or 0))
            limite_total += limite_mensal
            grupos[key] = {
                'categoria_cartao_id': limite.categoria_cartao_id,
                'categoria_cartao_nome': categoria.nome if categoria else 'Categoria do Cartao',
                'categoria_cartao_cor': categoria.cor if categoria else None,
                'categoria_cartao_icone': categoria.icone if categoria else None,
                'limite_mensal': limite_mensal,
                'gasto_atual': Decimal('0'),
                'quantidade_lancamentos': 0,
                'vinculada_ao_cartao': True,
                'sem_categoria': False,
                'categoria_sem_limite': False,
                'avisos': [],
                'tipo_grupo': 'categoria_cartao',
            }
            ordem_grupos.append(key)

        lancamentos = LancamentoAgregado.query.filter(
            LancamentoAgregado.cartao_id == cartao_id,
            PerfilFinanceiroService.condicao_perfil(LancamentoAgregado),
            LancamentoAgregado.mes_fatura >= mes_ref,
            LancamentoAgregado.mes_fatura < proximo_mes,
        ).all()

        total_fatura = Decimal('0')
        total_com_categoria = Decimal('0')
        total_sem_categoria_cartao = Decimal('0')
        total_categorias_vinculadas = Decimal('0')
        sem_categoria_key = 'sem_categoria'

        for lancamento in lancamentos:
            valor = Decimal(str(lancamento.valor or 0))
            total_fatura += valor

            if lancamento.categoria_cartao_id:
                total_com_categoria += valor
                key = f'categoria:{lancamento.categoria_cartao_id}'
                if key not in grupos:
                    categoria = lancamento.categoria_cartao
                    key = f'categoria_sem_limite:{lancamento.categoria_cartao_id}'
                    if key not in grupos:
                        grupos[key] = {
                            'categoria_cartao_id': lancamento.categoria_cartao_id,
                            'categoria_cartao_nome': categoria.nome if categoria else 'Categoria sem limite neste cartao',
                            'categoria_cartao_cor': categoria.cor if categoria else None,
                            'categoria_cartao_icone': categoria.icone if categoria else None,
                            'limite_mensal': Decimal('0'),
                            'gasto_atual': Decimal('0'),
                            'quantidade_lancamentos': 0,
                            'vinculada_ao_cartao': False,
                            'sem_categoria': False,
                            'categoria_sem_limite': True,
                            'avisos': ['Categoria sem limite neste cartao.'],
                            'tipo_grupo': 'categoria_sem_limite',
                        }
                        ordem_grupos.append(key)
                elif grupos[key]['vinculada_ao_cartao']:
                    total_categorias_vinculadas += valor
            else:
                total_sem_categoria_cartao += valor
                key = sem_categoria_key
                if key not in grupos:
                    grupos[key] = {
                        'categoria_cartao_id': None,
                        'categoria_cartao_nome': 'Sem Categoria do Cartao',
                        'categoria_cartao_cor': None,
                        'categoria_cartao_icone': None,
                        'limite_mensal': None,
                        'gasto_atual': Decimal('0'),
                        'quantidade_lancamentos': 0,
                        'vinculada_ao_cartao': False,
                        'sem_categoria': True,
                        'categoria_sem_limite': False,
                        'avisos': ['Lancamentos sem Categoria do Cartao devem ser revisados.'],
                        'tipo_grupo': 'sem_categoria',
                    }
                    ordem_grupos.append(key)

            grupos[key]['gasto_atual'] += valor
            grupos[key]['quantidade_lancamentos'] += 1

        categorias = []
        for key in ordem_grupos:
            grupo = grupos[key]
            limite_mensal = grupo['limite_mensal']
            gasto_atual = grupo['gasto_atual']
            if grupo['sem_categoria'] or grupo['categoria_sem_limite']:
                disponivel = None
                percentual = None
                status = 'Revisar'
            else:
                disponivel = limite_mensal - gasto_atual
                percentual = CartaoService._calcular_percentual(gasto_atual, limite_mensal)
                status = CartaoService._status_consumo(gasto_atual, limite_mensal)

            categorias.append({
                'categoria_cartao_id': grupo['categoria_cartao_id'],
                'categoria_cartao_nome': grupo['categoria_cartao_nome'],
                'categoria_cartao_cor': grupo['categoria_cartao_cor'],
                'categoria_cartao_icone': grupo['categoria_cartao_icone'],
                'limite_mensal': float(limite_mensal) if limite_mensal is not None else None,
                'gasto_atual': float(gasto_atual),
                'disponivel': float(disponivel) if disponivel is not None else None,
                'percentual': percentual,
                'percentual_utilizado': percentual,
                'status': status,
                'quantidade_lancamentos': grupo['quantidade_lancamentos'],
                'vinculada_ao_cartao': grupo['vinculada_ao_cartao'],
                'sem_categoria': grupo['sem_categoria'],
                'categoria_sem_limite': grupo['categoria_sem_limite'],
                'avisos': grupo['avisos'],
                'tipo_grupo': grupo['tipo_grupo'],
            })

        disponivel_total = limite_total - total_categorias_vinculadas
        return {
            'cartao_id': cartao.id,
            'mes_referencia': mes_ref.strftime('%Y-%m'),
            'total_fatura': float(total_fatura),
            'total_com_categoria': float(total_com_categoria),
            'total_sem_categoria_cartao': float(total_sem_categoria_cartao),
            'limite_total': float(limite_total),
            'disponivel_total': float(disponivel_total),
            'percentual_total': CartaoService._calcular_percentual(total_categorias_vinculadas, limite_total),
            'status_total': CartaoService._status_consumo(total_categorias_vinculadas, limite_total),
            'categorias': categorias,
        }

    @staticmethod
    def listar_lancamentos_fatura_por_categoria_cartao(cartao_id, mes_referencia, categoria_cartao_id=None):
        """
        Lista lancamentos da fatura com Categoria de Despesa e Categoria do Cartao.
        """
        cartao = ItemDespesa.query.filter(
            ItemDespesa.id == cartao_id,
            ItemDespesa.tipo == 'Agregador',
            PerfilFinanceiroService.condicao_perfil(ItemDespesa),
        ).first()
        if not cartao:
            raise ValueError('Cartao nao encontrado')

        mes_ref, proximo_mes = CartaoService._intervalo_mes(mes_referencia)
        filtro = str(categoria_cartao_id or 'todos').strip()

        query = LancamentoAgregado.query.filter(
            LancamentoAgregado.cartao_id == cartao_id,
            PerfilFinanceiroService.condicao_perfil(LancamentoAgregado),
            LancamentoAgregado.mes_fatura >= mes_ref,
            LancamentoAgregado.mes_fatura < proximo_mes,
        )

        if filtro == 'sem_categoria':
            query = query.filter(LancamentoAgregado.categoria_cartao_id == None)
        elif filtro and filtro != 'todos':
            try:
                query = query.filter(LancamentoAgregado.categoria_cartao_id == int(filtro))
            except (TypeError, ValueError):
                raise ValueError('categoria_cartao_id invalido')

        vinculadas = {
            limite.categoria_cartao_id
            for limite in CategoriaCartaoService.listar_limites_cartao(cartao_id, ativo=True)
        }
        lancamentos = query.order_by(
            LancamentoAgregado.data_compra.asc(),
            LancamentoAgregado.id.asc(),
        ).all()

        resultado = []
        for lancamento in lancamentos:
            if not lancamento.categoria_cartao_id:
                status_classificacao = 'sem_categoria_cartao'
            elif lancamento.categoria_cartao_id not in vinculadas:
                status_classificacao = 'categoria_sem_limite'
            else:
                status_classificacao = 'classificado'

            resultado.append({
                'id': lancamento.id,
                'data': lancamento.data_compra.isoformat() if lancamento.data_compra else None,
                'descricao': lancamento.descricao_exibida or lancamento.descricao,
                'descricao_original': lancamento.descricao_original or lancamento.descricao,
                'valor': float(lancamento.valor or 0),
                'categoria_id': lancamento.categoria_id,
                'categoria_nome': lancamento.categoria.nome if lancamento.categoria else None,
                'categoria_cartao_id': lancamento.categoria_cartao_id,
                'categoria_cartao_nome': lancamento.categoria_cartao.nome if lancamento.categoria_cartao else None,
                'origem': lancamento.origem_importacao or ('recorrencia' if lancamento.is_recorrente else 'manual'),
                'parcela_atual': lancamento.numero_parcela,
                'parcelas_total': lancamento.total_parcelas,
                'compra_id': lancamento.compra_id,
                'status_classificacao': status_classificacao,
            })

        return {
            'cartao_id': cartao.id,
            'mes_referencia': mes_ref.strftime('%Y-%m'),
            'categoria_cartao_id': filtro,
            'lancamentos': resultado,
        }

    @staticmethod
    def _obter_lancamento_parcelado(lancamento_id):
        lancamento = LancamentoAgregado.query.filter(
            PerfilFinanceiroService.condicao_perfil(LancamentoAgregado),
            LancamentoAgregado.id == lancamento_id,
        ).first()
        if not lancamento:
            raise ValueError('Lancamento nao encontrado')
        if int(lancamento.total_parcelas or 1) <= 1:
            raise ValueError('Lancamento nao pertence a parcelamento')
        if not lancamento.compra_id:
            raise ValueError('Parcelamento sem identificador de compra')
        return lancamento

    @staticmethod
    def _parcelas_por_compra(lancamento):
        return LancamentoAgregado.query.filter(
            PerfilFinanceiroService.condicao_perfil(LancamentoAgregado),
            LancamentoAgregado.cartao_id == lancamento.cartao_id,
            LancamentoAgregado.compra_id == lancamento.compra_id,
            LancamentoAgregado.total_parcelas == lancamento.total_parcelas,
        ).order_by(
            LancamentoAgregado.numero_parcela.asc(),
            LancamentoAgregado.mes_fatura.asc(),
            LancamentoAgregado.id.asc(),
        ).all()

    @staticmethod
    def _fatura_lancamento(lancamento):
        return Conta.query.filter(
            PerfilFinanceiroService.condicao_perfil(Conta),
            Conta.item_despesa_id == lancamento.cartao_id,
            Conta.cartao_competencia == lancamento.mes_fatura,
            Conta.is_fatura_cartao == True,  # noqa: E712
        ).first()

    @staticmethod
    def _status_parcela_parcelamento(lancamento, base):
        fatura = CartaoService._fatura_lancamento(lancamento)
        status_fatura = fatura.status_fatura if fatura else None
        status_pagamento = fatura.status_pagamento if fatura else None

        if status_pagamento == 'Pago' or status_fatura == 'PAGA':
            return 'paga'
        if status_fatura == 'FECHADA':
            return 'fechada'
        if lancamento.mes_fatura < base.mes_fatura:
            return 'passada'
        if lancamento.mes_fatura == base.mes_fatura:
            return 'atual'
        return 'futura'

    @staticmethod
    def _parcela_futura_editavel(lancamento, base):
        return (
            lancamento.mes_fatura > base.mes_fatura
            and CartaoService._status_parcela_parcelamento(lancamento, base) == 'futura'
        )

    @staticmethod
    def _serializar_parcela_parcelamento(lancamento, base):
        status = CartaoService._status_parcela_parcelamento(lancamento, base)
        return {
            'id': lancamento.id,
            'parcela': f'{lancamento.numero_parcela}/{lancamento.total_parcelas}',
            'numero_parcela': lancamento.numero_parcela,
            'total_parcelas': lancamento.total_parcelas,
            'competencia': lancamento.mes_fatura.strftime('%Y-%m') if lancamento.mes_fatura else None,
            'data_compra': lancamento.data_compra.isoformat() if lancamento.data_compra else None,
            'valor': float(lancamento.valor or 0),
            'descricao': lancamento.descricao_exibida or lancamento.descricao,
            'categoria_id': lancamento.categoria_id,
            'categoria_nome': lancamento.categoria.nome if lancamento.categoria else None,
            'categoria_cartao_id': lancamento.categoria_cartao_id,
            'status': status,
            'editavel': CartaoService._parcela_futura_editavel(lancamento, base),
        }

    @staticmethod
    def consultar_parcelamento_lancamento(lancamento_id):
        base = CartaoService._obter_lancamento_parcelado(lancamento_id)
        parcelas = CartaoService._parcelas_por_compra(base)
        if not parcelas:
            parcelas = [base]

        primeira = min((p.mes_fatura for p in parcelas if p.mes_fatura), default=None)
        ultima = max((p.mes_fatura for p in parcelas if p.mes_fatura), default=None)
        futuras = [p for p in parcelas if CartaoService._parcela_futura_editavel(p, base)]
        bloqueadas = [
            p for p in parcelas
            if p.mes_fatura and p.mes_fatura > base.mes_fatura and not CartaoService._parcela_futura_editavel(p, base)
        ]
        cartao = ItemDespesa.query.get(base.cartao_id)

        return {
            'base': {
                'id': base.id,
                'compra_id': base.compra_id,
                'cartao_id': base.cartao_id,
                'cartao_nome': cartao.nome if cartao else None,
                'descricao': base.descricao_exibida or base.descricao,
                'valor': float(base.valor or 0),
                'parcela_atual': base.numero_parcela,
                'total_parcelas': base.total_parcelas,
                'categoria_id': base.categoria_id,
                'categoria_nome': base.categoria.nome if base.categoria else None,
                'primeira_competencia': primeira.strftime('%Y-%m') if primeira else None,
                'ultima_competencia': ultima.strftime('%Y-%m') if ultima else None,
                'futuras_editaveis': len(futuras),
                'futuras_bloqueadas': len(bloqueadas),
            },
            'parcelas': [
                CartaoService._serializar_parcela_parcelamento(parcela, base)
                for parcela in parcelas
            ],
        }

    @staticmethod
    def atualizar_parcelas_futuras(lancamento_id, dados):
        base = CartaoService._obter_lancamento_parcelado(lancamento_id)
        parcelas = CartaoService._parcelas_por_compra(base)
        # FIN-PAGAMENTO-TRAVA-1: trava as faturas das parcelas e rele tudo antes de decidir o que e
        # "futura" (um pagamento simultaneo termina antes e a parcela dele deixa de ser editavel).
        CartaoService.travar_faturas(base.cartao_id, [p.mes_fatura for p in parcelas])
        db.session.expire_all()
        base = CartaoService._obter_lancamento_parcelado(lancamento_id)
        parcelas = CartaoService._parcelas_por_compra(base)
        futuras = [p for p in parcelas if CartaoService._parcela_futura_editavel(p, base)]
        if not futuras:
            return {'atualizadas': 0, 'faturas_afetadas': [], 'parcelamento': CartaoService.consultar_parcelamento_lancamento(lancamento_id)}

        descricao = (dados.get('descricao') or '').strip()
        categoria_id = dados.get('categoria_id')
        valor = dados.get('valor')
        categoria_cartao_id = None
        if categoria_id:
            resolucao = CategoriaCartaoService.resolver_categoria_cartao_para_lancamento(
                cartao_id=base.cartao_id,
                categoria_id=categoria_id,
                categoria_cartao_id=None,
            )
            categoria_cartao_id = resolucao.get('categoria_cartao_id')

        valor_decimal = Decimal(str(valor)) if valor not in (None, '') else None
        faturas_afetadas = set()
        for parcela in futuras:
            if descricao:
                parcela.descricao = descricao
                parcela.descricao_exibida = descricao
            if categoria_id:
                parcela.categoria_id = int(categoria_id)
                parcela.categoria_cartao_id = categoria_cartao_id
            if valor_decimal is not None:
                parcela.valor = valor_decimal
            faturas_afetadas.add(parcela.mes_fatura)

        db.session.flush()
        for competencia in sorted(faturas_afetadas):
            CartaoService.recalcular_fatura(base.cartao_id, competencia)

        return {
            'atualizadas': len(futuras),
            'faturas_afetadas': [competencia.strftime('%Y-%m') for competencia in sorted(faturas_afetadas)],
            'parcelamento': CartaoService.consultar_parcelamento_lancamento(lancamento_id),
        }

    @staticmethod
    def cancelar_parcelas_futuras(lancamento_id):
        base = CartaoService._obter_lancamento_parcelado(lancamento_id)
        parcelas = CartaoService._parcelas_por_compra(base)
        # FIN-PAGAMENTO-TRAVA-1: trava as faturas das parcelas e rele tudo antes de decidir o que e
        # "futura" (um pagamento simultaneo termina antes e a parcela dele deixa de ser editavel).
        CartaoService.travar_faturas(base.cartao_id, [p.mes_fatura for p in parcelas])
        db.session.expire_all()
        base = CartaoService._obter_lancamento_parcelado(lancamento_id)
        parcelas = CartaoService._parcelas_por_compra(base)
        futuras = [p for p in parcelas if CartaoService._parcela_futura_editavel(p, base)]
        faturas_afetadas = {parcela.mes_fatura for parcela in futuras}

        for parcela in futuras:
            db.session.delete(parcela)

        db.session.flush()
        for competencia in sorted(faturas_afetadas):
            CartaoService.recalcular_fatura(base.cartao_id, competencia)

        return {
            'canceladas': len(futuras),
            'faturas_afetadas': [competencia.strftime('%Y-%m') for competencia in sorted(faturas_afetadas)],
            'parcelamento': CartaoService.consultar_parcelamento_lancamento(lancamento_id),
        }

    # ==========================================================
    # FUTURO (FASE 3): Pagamento parcial de fatura
    #
    # Quando implementado, este mÃ©todo precisarÃ¡ considerar:
    # 1. Pagamento parcial: valor_pago < valor_total
    # 2. Saldo rotativo: diferenÃ§a que vai para prÃ³xima fatura
    # 3. CÃ¡lculo de juros sobre saldo residual
    # 4. AplicaÃ§Ã£o de IOF sobre operaÃ§Ã£o rotativa
    # 5. GeraÃ§Ã£o automÃ¡tica de lanÃ§amento "Saldo rotativo"
    # 6. HistÃ³rico de mÃºltiplos pagamentos parciais
    #
    # ATUALMENTE: pagamento Ã© sempre integral
    # Fatura sÃ³ vai para status='PAGA' apÃ³s pagamento total
    # NÃ£o existe saldo residual ou cÃ¡lculo de juros
    # ==========================================================

    @staticmethod
    def fatura_esta_paga(fatura):
        """Paga pelo pagamento do Flask (status_pagamento) ou marcada PAGA (status_fatura)."""
        return fatura is not None and (fatura.status_pagamento == 'Pago' or fatura.status_fatura == 'PAGA')

    # FIN-FATURA-INTEGRIDADE-1 — ordem global de travas: cartao (item_despesa, por id) -> faturas
    # dele (por id) -> compras -> conta bancaria -> movimento. Quem trava mais de uma fatura trava o
    # cartao ANTES; quem trava uma so fatura (pagamento) nunca espera outra fatura. Assim nenhuma
    # operacao segura uma fatura enquanto espera outra fatura de um cartao que nao travou: nao ha
    # ciclo de espera (o novo aplicativo segue a mesma ordem; migration 20261029090000).

    @staticmethod
    def travar_cartao(cartao_id):
        return travar_um(ItemDespesa, cartao_id)

    @staticmethod
    def travar_faturas(cartao_id, competencias):
        """Trava o cartao e depois (em ordem de id) as faturas existentes dele nos meses dados."""
        meses = {CartaoService._primeiro_dia_mes(c) for c in competencias if c}
        if not meses:
            return []
        CartaoService.travar_cartao(cartao_id)
        ids = [f.id for f in Conta.query.filter(
            Conta.item_despesa_id == cartao_id,
            Conta.is_fatura_cartao == True,  # noqa: E712
            Conta.cartao_competencia.in_(meses),
        ).all()]
        return travar(Conta, ids)

    @staticmethod
    def _fatura_travada(cartao_id, competencia):
        """Garante a fatura do mes (a criacao confirma a transacao e solta as travas), trava o cartao
        (se ja travado, nada muda) e devolve a fatura travada e relida."""
        fatura = CartaoService.get_or_create_fatura(cartao_id, competencia)
        CartaoService.travar_cartao(cartao_id)
        return travar_um(Conta, fatura.id)

    @staticmethod
    def fatura_elegivel(cartao_id, competencia, minimo=None):
        """FIN-FATURA-INTEGRIDADE-1: primeira fatura NAO paga a partir do mes (e nao antes de `minimo`),
        travada. Fatura paga e imutavel quanto as compras; FECHADA continua elegivel (estado proprio).
        Devolve (mes_destino, fatura)."""
        mes = CartaoService._primeiro_dia_mes(competencia)
        if minimo and mes < minimo:
            mes = minimo
        fatura = CartaoService._fatura_travada(cartao_id, mes)
        desvios = 0
        while CartaoService.fatura_esta_paga(fatura):
            desvios += 1
            if desvios > 24:
                raise ValueError('Nao ha fatura aberta nos proximos 24 meses')
            mes = mes + relativedelta(months=1)
            fatura = CartaoService._fatura_travada(cartao_id, mes)
        return mes, fatura

    @staticmethod
    def planejar_destinos(pedidos):
        """FIN-FATURA-INTEGRIDADE-1: destino de cada parcela ANTES de inserir qualquer uma.

        pedidos: lista de (cartao_id, chave, [competencias pretendidas, em ordem de parcela]).
        Devolve {chave: [mes de destino por parcela]}: a primeira fatura NAO paga a partir da pretendida,
        uma por fatura (um desvio desloca as parcelas seguintes). Ao devolver, os cartoes (por id) e as
        faturas deles estao travados ate o commit do chamador. As faturas que faltam sao criadas antes
        (a criacao confirma a transacao, mas nada da compra esta pendente ainda): a compra continua
        atomica e nenhuma trava anterior e usada depois de solta.
        """
        extras = {}
        for _tentativa in range(30):
            for cartao_id, _chave, meses in pedidos:
                for mes in sorted({CartaoService._primeiro_dia_mes(m) for m in meses} | extras.get(cartao_id, set())):
                    CartaoService.get_or_create_fatura(cartao_id, mes)
            travadas = {}
            for cartao_id in sorted({c for c, _k, _m in pedidos}):
                meses = {CartaoService._primeiro_dia_mes(m) for c, _k, ms in pedidos if c == cartao_id for m in ms}
                travadas[cartao_id] = {f.cartao_competencia: f for f in
                                       CartaoService.travar_faturas(cartao_id, meses | extras.get(cartao_id, set()))}
            destinos, faltou = {}, None
            for cartao_id, chave, meses in pedidos:
                lista, anterior = [], None
                for mes in meses:
                    mes = CartaoService._primeiro_dia_mes(mes)
                    if anterior and mes <= anterior:
                        mes = anterior + relativedelta(months=1)
                    for _ in range(25):
                        fatura = travadas[cartao_id].get(mes)
                        if fatura is None or not CartaoService.fatura_esta_paga(fatura):
                            break
                        mes = mes + relativedelta(months=1)
                    else:
                        raise ValueError('Nao ha fatura aberta nos proximos 24 meses')
                    if travadas[cartao_id].get(mes) is None:
                        faltou = (cartao_id, mes)
                        break
                    lista.append(mes)
                    anterior = mes
                if faltou:
                    break
                destinos[chave] = lista
            if not faltou:
                return destinos
            extras.setdefault(faltou[0], set()).add(faltou[1])  # criada na proxima volta
        raise ValueError('Nao foi possivel definir as faturas de destino')

    @staticmethod
    def fatura_elegivel_existente(cartao_id, competencia):
        """Como fatura_elegivel, sem criar fatura nem confirmar a transacao (a geracao de recorrencias
        do Flask roda numa transacao do chamador, com a trava do gerador T1). Trava o cartao, pula as
        faturas pagas existentes e devolve o primeiro mes sem fatura paga. Com o cartao travado,
        ninguem cria (get_or_create_fatura tambem trava o cartao) nem paga uma fatura nova dele."""
        CartaoService.travar_cartao(cartao_id)
        mes = CartaoService._primeiro_dia_mes(competencia)
        for _ in range(25):
            existente = Conta.query.filter(
                Conta.item_despesa_id == cartao_id,
                Conta.is_fatura_cartao == True,  # noqa: E712
                Conta.cartao_competencia == mes,
            ).first()
            if existente is None or not CartaoService.fatura_esta_paga(travar_um(Conta, existente.id)):
                return mes
            mes = mes + relativedelta(months=1)
        raise ValueError('Nao ha fatura aberta nos proximos 24 meses')

    _colunas_desvio = {}

    @staticmethod
    def suporta_desvio_auditado():
        """True se o banco ja tem lancamento_agregado.mes_fatura_original (migration local
        FIN-FATURA-INTEGRIDADE-1). Um banco ainda nao migrado (ex.: gastos.db) continua funcionando."""
        from sqlalchemy import inspect
        chave = str(db.engine.url)
        if chave not in CartaoService._colunas_desvio:
            colunas = {c['name'] for c in inspect(db.engine).get_columns('lancamento_agregado')}
            CartaoService._colunas_desvio[chave] = 'mes_fatura_original' in colunas
        return CartaoService._colunas_desvio[chave]

    @staticmethod
    def registrar_desvio(lancamento, mes_original, exigir_coluna=False):
        """Registra de forma auditavel que a compra saiu da competencia `mes_original` (fatura paga).

        Com a coluna: mes_fatura_original. Sem ela (banco nao migrado): marca nas observacoes, ou
        recusa (exigir_coluna, usado pela importacao, que precisa da competencia original para nao
        duplicar numa reimportacao)."""
        mes_original = CartaoService._primeiro_dia_mes(mes_original)
        if lancamento.mes_fatura == mes_original:
            return
        if CartaoService.suporta_desvio_auditado():
            lancamento.mes_fatura_original = mes_original
            return
        if exigir_coluna:
            raise ValueError(f'A fatura de {mes_original.strftime("%m/%Y")} esta paga e este banco ainda nao registra '
                             'a competencia original do desvio (migration pendente). Nada foi importado.')
        marca = f'[Fatura de {mes_original.strftime("%m/%Y")} paga: lancada em {lancamento.mes_fatura.strftime("%m/%Y")}]'
        lancamento.observacoes = f'{lancamento.observacoes}\n{marca}' if lancamento.observacoes else marca

    @staticmethod
    def filtro_competencia_original(modelo, competencia):
        """Compra da competencia `competencia`, esteja nela ou desviada dela (deduplicacao)."""
        from sqlalchemy import or_
        competencia = CartaoService._primeiro_dia_mes(competencia)
        if CartaoService.suporta_desvio_auditado():
            return or_(modelo.mes_fatura == competencia, modelo.mes_fatura_original == competencia)
        return modelo.mes_fatura == competencia

    @staticmethod
    def recalcular_fatura(cartao_id, competencia):
        """
        Recalcula uma fatura existente (Ãºtil apÃ³s adicionar/remover lanÃ§amentos)

        Args:
            cartao_id (int): ID do cartÃ£o
            competencia (date): MÃªs de referÃªncia

        Returns:
            Conta: Fatura atualizada
        """
        comp_primeiro_dia = CartaoService._primeiro_dia_mes(competencia)
        # FIN-PAGAMENTO-TRAVA-1: travada e relida; sem isso um recalculo que leu "nao paga" podia
        # gravar valor = planejado por cima de um pagamento confirmado no meio do caminho.
        fatura = CartaoService._fatura_travada(cartao_id, comp_primeiro_dia)

        # Se jÃ¡ foi paga, nÃ£o recalcular
        if CartaoService.fatura_esta_paga(fatura):
            return fatura

        # Recalcular planejado (pode ter mudado o orÃ§amento)
        fatura.valor_planejado = CartaoService.calcular_planejado(cartao_id, competencia)

        # Calcular executado atual
        fatura.valor_executado = CartaoService.calcular_executado(cartao_id, competencia)

        # Verificar estouro
        if fatura.valor_executado > fatura.valor_planejado:
            fatura.estouro_orcamento = True
        else:
            fatura.estouro_orcamento = False

        # Valor exibido = planejado (enquanto nÃ£o paga)
        fatura.valor = fatura.valor_planejado

        db.session.commit()
        return fatura

    # ========================================================================
    # PAGAMENTO DE FATURAS
    # ========================================================================

    @staticmethod
    def pagar_fatura(fatura_id, data_pagamento, valor_pago=None, conta_bancaria_id=None):
        """
        Registra pagamento da fatura recalculando o valor executado imediatamente antes.

        Regras:
        - Recalcula valor_executado a partir dos lancamentos (nunca usa cache).
        - Bloqueia se a fatura ja estiver paga (ValueError).
        - Usa ContaBancariaService.criar_movimento() para atomicidade.
        """
        try:
            from backend.services.conta_bancaria_service import ContaBancariaService
        except ImportError:
            from services.conta_bancaria_service import ContaBancariaService

        fatura = Conta.query.filter(
            Conta.id == fatura_id,
            PerfilFinanceiroService.condicao_perfil(Conta),
        ).first()
        if not fatura:
            raise ValueError('Fatura nao encontrada')
        if not fatura.is_fatura_cartao:
            raise ValueError('Esta conta nao e uma fatura de cartao')
        # FIN-PAGAMENTO-TRAVA-1: travada antes de conferir e somar as compras. Compras e recalculos
        # da mesma fatura (Flask e novo aplicativo) travam a mesma linha: ou entram antes e sao
        # somadas, ou esperam e encontram a fatura paga.
        fatura = travar_um(Conta, fatura.id)

        # Bloquear pagamento duplicado
        if CartaoService.fatura_esta_paga(fatura):
            raise ValueError('Esta fatura ja foi paga e nao pode ser paga novamente')

        if isinstance(data_pagamento, str):
            data_pagamento = datetime.strptime(data_pagamento, '%Y-%m-%d').date()

        # Recalcular valor executado a partir dos lancamentos (nunca usar cache)
        valor_executado_recalculado = CartaoService.calcular_executado(
            fatura.item_despesa_id,
            fatura.cartao_competencia,
        )

        # Valor final do pagamento: valor_pago se informado, senao o executado recalculado
        valor_final_pagamento = Decimal(str(valor_pago)) if valor_pago else valor_executado_recalculado

        # Validar e debitar conta bancaria
        conta_bancaria_id = int(conta_bancaria_id) if conta_bancaria_id else None
        if conta_bancaria_id:
            from backend.models import ContaBancaria
            conta_bancaria = ContaBancaria.query.filter(
                ContaBancaria.id == conta_bancaria_id,
                PerfilFinanceiroService.condicao_perfil(ContaBancaria),
            ).first()
            if not conta_bancaria:
                raise ValueError('Conta bancaria nao encontrada')
            if conta_bancaria.status != 'ATIVO':
                raise ValueError('Conta bancaria esta inativa')

            ContaBancariaService.criar_movimento(
                conta_bancaria_id,
                tipo='DEBITO',
                valor=valor_final_pagamento,
                descricao=f'Pagamento fatura cartao - {fatura.descricao}',
                data_movimento=data_pagamento,
                origem='FATURA',
                fatura_id=fatura_id,
                conta_id=fatura_id,
            )
            fatura.conta_bancaria_id = conta_bancaria_id

        # Atualizar fatura com valores finais
        fatura.valor_executado = valor_executado_recalculado
        fatura.valor = valor_final_pagamento
        fatura.data_pagamento = data_pagamento
        fatura.status_pagamento = 'Pago'

        return fatura

    # ========================================================================
    # LANÃ‡AMENTOS
    # ========================================================================

    @staticmethod
    def adicionar_lancamento(dados_lancamento):
        """
        Adiciona um lanÃ§amento no cartÃ£o e garante que a fatura existe

        CORREÃ‡ÃƒO PARCELAMENTO:
        - Se total_parcelas > 1: cria N lanÃ§amentos, cada um em um mÃªs distinto
        - Valor Ã© dividido igualmente entre as parcelas
        - Garante idempotÃªncia: nÃ£o duplica parcelas jÃ¡ existentes

        Args:
            dados_lancamento (dict): Dados do lanÃ§amento
                - cartao_id: ID do cartÃ£o (obrigatÃ³rio)
                - item_agregado_id: ID da categoria (OPCIONAL - se None, nÃ£o controla limite)
                - valor: Valor TOTAL da compra (serÃ¡ dividido pelas parcelas)
                - descricao: DescriÃ§Ã£o
                - data_compra: Data da compra
                - mes_fatura: MÃªs da PRIMEIRA fatura
                - categoria_id: Categoria real da despesa
                - numero_parcela: ignorado (sempre comeÃ§a em 1)
                - total_parcelas: nÃºmero de parcelas (default=1)

        Returns:
            tuple: (LancamentoAgregado primeira parcela, Conta fatura primeira parcela)
        """
        # ID do cartÃ£o (agora obrigatÃ³rio nos dados)
        cartao_id = dados_lancamento['cartao_id']

        categoria_cartao_id = dados_lancamento.get('categoria_cartao_id')
        if dados_lancamento.get('categoria_id'):
            resolucao = CategoriaCartaoService.resolver_categoria_cartao_para_lancamento(
                cartao_id=cartao_id,
                categoria_id=dados_lancamento.get('categoria_id'),
                categoria_cartao_id=categoria_cartao_id,
            )
            categoria_cartao_id = resolucao.get('categoria_cartao_id')

        # Item agregado e opcional e permanece apenas para compatibilidade.
        item_agregado_id = dados_lancamento.get('item_agregado_id')
        if item_agregado_id:
            item_agregado = ItemAgregado.query.get(item_agregado_id)
            if not item_agregado:
                raise ValueError('ItemAgregado nÃ£o encontrado')

        # Parcelamento
        total_parcelas = dados_lancamento.get('total_parcelas', 1)
        valor_total = Decimal(str(dados_lancamento['valor']))

        # FASE 2: Gerar UUID Ãºnico para esta compra
        # Todas as parcelas compartilharÃ£o este ID para idempotÃªncia robusta
        compra_uuid = str(uuid.uuid4())

        # CORREÃ‡ÃƒO FINANCEIRA: DistribuiÃ§Ã£o de centavos
        # Garante que soma das parcelas = valor total (sem perda de centavos)
        total_centavos = int(round(valor_total * 100))
        centavos_base = total_centavos // total_parcelas
        centavos_resto = total_centavos % total_parcelas

        # MÃªs da primeira fatura (competÃªncia)
        mes_fatura_inicial = dados_lancamento['mes_fatura']
        if isinstance(mes_fatura_inicial, str):
            mes_fatura_inicial = datetime.strptime(mes_fatura_inicial, '%Y-%m-%d').date()
        mes_fatura_inicial = mes_fatura_inicial.replace(day=1)

        data_compra_inicial = dados_lancamento['data_compra']

        # Lista para armazenar lanÃ§amentos criados
        lancamentos_criados = []
        primeira_fatura = None
        faturas_afetadas_set = set()  # Armazena meses de faturas afetadas (considerando redirecionamento)

        # FIN-FATURA-INTEGRIDADE-1: destinos de todas as parcelas decididos (e faturas criadas) antes de
        # inserir qualquer parcela; a compra so e confirmada inteira (sem parcela solta se algo falhar).
        meses_pretendidos = [mes_fatura_inicial + relativedelta(months=n - 1) for n in range(1, total_parcelas + 1)]
        destinos = CartaoService.planejar_destinos([(cartao_id, 'compra', meses_pretendidos)])['compra']
        # FIN-CARTOES-FECHAMENTO-1 (D6): fatura consolidada (FECHADA) de destino, ja travada e relida pelo
        # planejamento, so recebe a compra com a confirmacao desta operacao; conferida antes de inserir.
        faturas_destino = {mes: Conta.query.filter(
            Conta.item_despesa_id == cartao_id,
            Conta.is_fatura_cartao == True,  # noqa: E712
            Conta.cartao_competencia == mes,
        ).one() for mes in set(destinos)}
        inclusoes = {}
        for n, mes in enumerate(destinos, start=1):
            fatura = faturas_destino[mes]
            if fatura.status_fatura == 'FECHADA' and not CartaoService.fatura_esta_paga(fatura):
                valor_n = Decimal(centavos_base + (1 if n <= centavos_resto else 0)) / 100
                anterior = inclusoes.get(fatura.id, (fatura, Decimal('0')))[1]
                inclusoes[fatura.id] = (fatura, anterior + valor_n)
        CartaoService.conferir_confirmacoes(inclusoes, dados_lancamento.get('confirmar_consolidadas'))
        # Competencia sugerida pelo fechamento (auditoria do ajuste manual), so num banco com a coluna.
        sugerida = None
        if CartaoService.suporta_competencia_sugerida():
            sugerida = CartaoService.sugestao_competencia(cartao_id, data_compra_inicial)['competencia']
        # Criar uma parcela para cada mÃªs
        for n in range(1, total_parcelas + 1):
            # Calcular data da parcela (incrementa mÃªs a cada parcela)
            data_parcela = data_compra_inicial + relativedelta(months=n-1)
            mes_fatura_parcela = mes_fatura_inicial + relativedelta(months=n-1)

            # REGRA DE FECHAMENTO DE FATURA:
            # Se a fatura do mÃªs estiver PAGA, redirecionar para a prÃ³xima fatura
            # FIN-PAGAMENTO-TRAVA-1: a fatura e travada e relida antes da conferencia (um pagamento
            # simultaneo termina antes e a compra vai para a seguinte); "paga" inclui
            # status_pagamento (o unico que o pagamento grava). Um desvio desloca as parcelas
            # seguintes, uma por fatura, como no novo aplicativo.
            mes_fatura_original = mes_fatura_parcela
            mes_fatura_parcela = destinos[n - 1]
            fatura_mes = Conta.query.filter(  # ja travada pelo planejamento
                Conta.item_despesa_id == cartao_id,
                Conta.is_fatura_cartao == True,  # noqa: E712
                Conta.cartao_competencia == mes_fatura_parcela,
            ).one()

            # Calcular valor desta parcela (distribui centavos do resto nas primeiras parcelas)
            centavos_parcela = centavos_base + (1 if n <= centavos_resto else 0)
            valor_parcela = Decimal(centavos_parcela) / 100

            # FASE 2: IDEMPOTÃŠNCIA ROBUSTA
            # Verifica se parcela jÃ¡ existe usando compra_id (UUID Ãºnico)
            # Muito mais seguro que usar descriÃ§Ã£o (texto livre)
            lancamento_existente = LancamentoAgregado.query.filter(
                PerfilFinanceiroService.condicao_perfil(LancamentoAgregado),
                LancamentoAgregado.compra_id == compra_uuid,
                LancamentoAgregado.numero_parcela == n,
            ).first()

            if lancamento_existente:
                # Parcela jÃ¡ existe, pular
                if n == 1:
                    lancamentos_criados.append(lancamento_existente)
                    primeira_fatura = fatura_mes
                continue

            # Criar lanÃ§amento da parcela
            lancamento = LancamentoAgregado(
                perfil_financeiro_id=fatura_mes.perfil_financeiro_id or PerfilFinanceiroService.obter_perfil_ativo_id(),
                cartao_id=cartao_id,
                item_agregado_id=item_agregado_id,  # Pode ser None
                categoria_cartao_id=categoria_cartao_id,
                categoria_id=dados_lancamento['categoria_id'],  # Categoria da DESPESA (obrigatÃ³ria)
                valor=valor_parcela,  # â† CORREÃ‡ÃƒO: valor com distribuiÃ§Ã£o correta de centavos
                descricao=dados_lancamento['descricao'],
                data_compra=data_parcela,  # â† Data incrementada por mÃªs
                mes_fatura=mes_fatura_parcela,  # â† MÃªs incrementado
                numero_parcela=n,  # â† Parcela correta (1, 2, 3...)
                total_parcelas=total_parcelas,
                observacoes=dados_lancamento.get('observacoes', ''),
                is_recorrente=False,  # Parcelamento NÃƒO Ã© recorrÃªncia
                compra_id=compra_uuid  # â† FASE 2: UUID Ãºnico da compra
            )

            CartaoService.registrar_desvio(lancamento, mes_fatura_original)
            if sugerida:
                lancamento.mes_fatura_sugerido = sugerida + relativedelta(months=n - 1)
            db.session.add(lancamento)
            lancamentos_criados.append(lancamento)

            # Guardar primeira fatura para retornar
            if n == 1:
                primeira_fatura = fatura_mes

            # Registrar fatura afetada (mÃªs real usado, apÃ³s possÃ­vel redirecionamento)
            faturas_afetadas_set.add(mes_fatura_parcela)

        # FIN-CARTOES-FECHAMENTO-1 (D6): total consolidado atualizado e auditado na mesma transacao.
        if inclusoes:
            db.session.flush()
            for _fatura_id, (fatura, valor) in sorted(inclusoes.items()):
                primeiro = next((l for l in lancamentos_criados if l.mes_fatura == fatura.cartao_competencia), None)
                CartaoService.registrar_inclusao_consolidada(fatura, valor, 'COMPRA', compra_uuid,
                                                             primeiro.id if primeiro else None)

        # FIN-PAGAMENTO-TRAVA-1: confirma as parcelas (cada uma entrou com a fatura dela travada) e
        # libera as travas antes dos recalculos. Cada recalculo trava UMA fatura e confirma; sem isso
        # a compra segurava a ultima fatura e voltava para travar a primeira (deadlock com outra
        # compra que segurava a primeira e esperava as seguintes).
        db.session.commit()

        # Recalcular TODAS as faturas afetadas (considerando redirecionamentos por status PAGA)
        for mes_fatura_afetada in sorted(faturas_afetadas_set):
            CartaoService.recalcular_fatura(cartao_id, mes_fatura_afetada)

        db.session.commit()

        # Retornar primeira parcela e primeira fatura (compatibilidade com cÃ³digo existente)
        return lancamentos_criados[0] if lancamentos_criados else None, primeira_fatura

    @staticmethod
    def avaliar_alertas(cartao_id, competencia):
        """
        Avalia se hÃ¡ alertas de estouro de orÃ§amento

        Args:
            cartao_id (int): ID do cartÃ£o
            competencia (date): MÃªs de referÃªncia

        Returns:
            dict: {
                'estouro_geral': bool,
                'percentual_consumo': float,
                'categorias_estouro': list
            }
        """
        comp_primeiro_dia, proximo_mes = CartaoService._intervalo_mes(competencia)
        fatura = CartaoService.get_or_create_fatura(cartao_id, comp_primeiro_dia)

        planejado = fatura.valor_planejado or Decimal('0')
        executado = fatura.valor_executado or Decimal('0')

        percentual = (float(executado) / float(planejado) * 100) if planejado > 0 else 0

        # Verificar estouros por categoria
        categorias_estouro = []
        itens_agregados = ItemAgregado.query.filter_by(item_despesa_id=cartao_id).all()

        for item in itens_agregados:
            # OrÃ§amento da categoria
            orcamento = OrcamentoAgregado.query.filter(
                and_(
                    OrcamentoAgregado.item_agregado_id == item.id,
                    OrcamentoAgregado.ativo == True,
                    OrcamentoAgregado.vigencia_inicio <= comp_primeiro_dia,
                    (OrcamentoAgregado.vigencia_fim == None) |
                    (OrcamentoAgregado.vigencia_fim >= comp_primeiro_dia)
                )
            ).first()

            if not orcamento:
                continue

            # Gasto da categoria no mÃªs por intervalo compatÃ­vel com SQLite/PostgreSQL.
            gasto = db.session.query(
                func.coalesce(func.sum(LancamentoAgregado.valor), 0)
            ).filter(
                LancamentoAgregado.item_agregado_id == item.id,
                LancamentoAgregado.mes_fatura >= comp_primeiro_dia,
                LancamentoAgregado.mes_fatura < proximo_mes
            ).scalar()

            gasto_decimal = Decimal(str(gasto or 0))

            if gasto_decimal > orcamento.valor_teto:
                categorias_estouro.append({
                    'item_agregado_id': item.id,
                    'nome': item.nome,
                    'orcado': float(orcamento.valor_teto),
                    'gasto': float(gasto_decimal),
                    'excesso': float(gasto_decimal - orcamento.valor_teto)
                })

        return {
            'estouro_geral': fatura.estouro_orcamento,
            'percentual_consumo': percentual,
            'categorias_estouro': categorias_estouro
        }

    # ========================================================================
    # GERAÃ‡ÃƒO AUTOMÃTICA DE FATURAS (JOB MENSAL)
    # ========================================================================

    @staticmethod
    def gerar_faturas_mes_atual():
        """
        Job mensal: Gera faturas virtuais para todos os cartÃµes ativos no mÃªs atual

        Deve ser executado no 1Âº dia de cada mÃªs

        Returns:
            list: Lista de faturas criadas
        """
        mes_atual = date.today().replace(day=1)

        # Buscar todos os cartÃµes ativos
        cartoes = ItemDespesa.query.filter(
            ItemDespesa.tipo == 'Agregador',
            ItemDespesa.ativo == True,
            PerfilFinanceiroService.condicao_perfil(ItemDespesa),
        ).all()

        faturas_criadas = []

        for cartao in cartoes:
            # FIN-RECORRENCIA-T1: job/scheduler nao gera faturas de perfil atribuido ao novo aplicativo.
            if not flask_pode_gerar(cartao.perfil_financeiro_id, f'job faturas cartao_id={cartao.id}'):
                continue
            try:
                fatura = CartaoService.get_or_create_fatura(cartao.id, mes_atual)
                faturas_criadas.append(fatura)
            except Exception:
                logger.warning('Falha ao gerar fatura mensal para cartao_id=%s', cartao.id, exc_info=True)
                continue

        return faturas_criadas

    # ========================================================================
    # SISTEMA DE ALERTAS (NÃƒO BLOQUEANTE)
    # ========================================================================

    @staticmethod
    def calcular_alerta_local(item_agregado_id, competencia):
        """
        Calcula alerta LOCAL para um ItemAgregado especÃ­fico

        Verifica se o consumo real ultrapassou o orÃ§amento da categoria

        IMPORTANTE: Alertas NÃƒO bloqueiam lanÃ§amentos, sÃ£o apenas informativos

        Args:
            item_agregado_id (int): ID do ItemAgregado (categoria do cartÃ£o)
            competencia (date): MÃªs de referÃªncia

        Returns:
            dict ou None: Alerta estruturado ou None se nÃ£o houver estouro
        """
        comp_primeiro_dia, proximo_mes = CartaoService._intervalo_mes(competencia)

        # Buscar item agregado
        item = ItemAgregado.query.get(item_agregado_id)
        if not item or not item.ativo:
            return None

        # Buscar orÃ§amento vigente
        orcamento = OrcamentoAgregado.query.filter(
            and_(
                OrcamentoAgregado.item_agregado_id == item_agregado_id,
                OrcamentoAgregado.ativo == True,
                OrcamentoAgregado.vigencia_inicio <= comp_primeiro_dia,
                (OrcamentoAgregado.vigencia_fim == None) |
                (OrcamentoAgregado.vigencia_fim >= comp_primeiro_dia)
            )
        ).first()

        if not orcamento:
            return None

        # Calcular consumo real (lanÃ§amentos do mÃªs)
        consumo = db.session.query(
            func.coalesce(func.sum(LancamentoAgregado.valor), 0)
        ).filter(
            LancamentoAgregado.item_agregado_id == item_agregado_id,
            LancamentoAgregado.mes_fatura >= comp_primeiro_dia,
            LancamentoAgregado.mes_fatura < proximo_mes
        ).scalar()

        consumo_decimal = Decimal(str(consumo or 0))
        orcado = orcamento.valor_teto

        # Verificar estouro
        if consumo_decimal > orcado:
            excedente = consumo_decimal - orcado
            percentual = (float(consumo_decimal) / float(orcado) * 100) if orcado > 0 else 0

            # Determinar nÃ­vel de alerta
            if percentual >= 150:
                nivel = 'CRITICO'
            elif percentual >= 120:
                nivel = 'ALTO'
            else:
                nivel = 'MODERADO'

            return {
                'tipo': 'LOCAL',
                'cartao_id': item.item_despesa_id,
                'item_agregado_id': item.id,
                'nome': item.nome,
                'valor_orcado': float(orcado),
                'valor_executado': float(consumo_decimal),
                'excedente': float(excedente),
                'percentual': round(percentual, 2),
                'nivel': nivel,
                'competencia': comp_primeiro_dia.strftime('%Y-%m')
            }

        return None

    @staticmethod
    def calcular_alerta_global(grupo_agregador_id, competencia):
        """
        Calcula alerta GLOBAL para um GrupoAgregador

        Verifica se a soma dos consumos de todas as categorias do grupo
        (em diferentes cartÃµes) ultrapassou a soma dos orÃ§amentos

        IMPORTANTE:
        - Grupos NÃƒO possuem orÃ§amento prÃ³prio
        - O limite Ã© a soma dos orÃ§amentos dos itens vinculados
        - Permite acompanhamento familiar/casal

        Args:
            grupo_agregador_id (int): ID do GrupoAgregador
            competencia (date): MÃªs de referÃªncia

        Returns:
            dict ou None: Alerta estruturado ou None se nÃ£o houver estouro
        """
        comp_primeiro_dia, proximo_mes = CartaoService._intervalo_mes(competencia)

        # Buscar grupo
        try:
            from backend.models import GrupoAgregador
        except ImportError:
            from models import GrupoAgregador

        grupo = GrupoAgregador.query.get(grupo_agregador_id)
        if not grupo or not grupo.ativo:
            return None

        # Buscar todos os itens agregados do grupo (apenas ativos)
        itens_do_grupo = ItemAgregado.query.filter_by(
            grupo_agregador_id=grupo_agregador_id,
            ativo=True
        ).all()

        if not itens_do_grupo:
            return None

        # Calcular soma dos orÃ§amentos e consumos
        total_orcado = Decimal('0')
        total_consumo = Decimal('0')
        detalhes_itens = []

        for item in itens_do_grupo:
            # Buscar orÃ§amento vigente
            orcamento = OrcamentoAgregado.query.filter(
                and_(
                    OrcamentoAgregado.item_agregado_id == item.id,
                    OrcamentoAgregado.ativo == True,
                    OrcamentoAgregado.vigencia_inicio <= comp_primeiro_dia,
                    (OrcamentoAgregado.vigencia_fim == None) |
                    (OrcamentoAgregado.vigencia_fim >= comp_primeiro_dia)
                )
            ).first()

            if orcamento:
                total_orcado += orcamento.valor_teto

            # Buscar consumo real
            consumo = db.session.query(
                func.coalesce(func.sum(LancamentoAgregado.valor), 0)
            ).filter(
                LancamentoAgregado.item_agregado_id == item.id,
                LancamentoAgregado.mes_fatura >= comp_primeiro_dia,
                LancamentoAgregado.mes_fatura < proximo_mes
            ).scalar()

            consumo_decimal = Decimal(str(consumo or 0))
            total_consumo += consumo_decimal

            # Guardar detalhes do item
            if orcamento:
                detalhes_itens.append({
                    'item_id': item.id,
                    'cartao_id': item.item_despesa_id,
                    'nome': item.nome,
                    'orcado': float(orcamento.valor_teto),
                    'consumo': float(consumo_decimal)
                })

        # Verificar estouro global
        if total_consumo > total_orcado:
            excedente = total_consumo - total_orcado
            percentual = (float(total_consumo) / float(total_orcado) * 100) if total_orcado > 0 else 0

            # Determinar nÃ­vel de alerta
            if percentual >= 150:
                nivel = 'CRITICO'
            elif percentual >= 120:
                nivel = 'ALTO'
            else:
                nivel = 'MODERADO'

            return {
                'tipo': 'GLOBAL',
                'grupo_agregador_id': grupo.id,
                'nome': grupo.nome,
                'descricao': grupo.descricao,
                'valor_orcado_total': float(total_orcado),
                'valor_executado_total': float(total_consumo),
                'excedente': float(excedente),
                'percentual': round(percentual, 2),
                'nivel': nivel,
                'competencia': comp_primeiro_dia.strftime('%Y-%m'),
                'itens': detalhes_itens
            }

        return None

    @staticmethod
    def obter_todos_alertas(cartao_id=None, competencia=None):
        """
        Retorna todos os alertas (locais e globais) para um cartÃ£o ou mÃªs

        Args:
            cartao_id (int, opcional): ID do cartÃ£o (se None, busca todos)
            competencia (date, opcional): MÃªs de referÃªncia (se None, usa mÃªs atual)

        Returns:
            dict: {
                'locais': [lista de alertas locais],
                'globais': [lista de alertas globais],
                'total_alertas': int
            }
        """
        if competencia is None:
            competencia = date.today().replace(day=1)
        else:
            competencia = CartaoService._primeiro_dia_mes(competencia)

        alertas_locais = []
        alertas_globais = []

        # Determinar quais itens agregados verificar
        if cartao_id:
            itens = ItemAgregado.query.filter_by(
                item_despesa_id=cartao_id,
                ativo=True
            ).all()
        else:
            itens = ItemAgregado.query.filter_by(ativo=True).all()

        # Calcular alertas locais
        for item in itens:
            alerta = CartaoService.calcular_alerta_local(item.id, competencia)
            if alerta:
                alertas_locais.append(alerta)

        # Calcular alertas globais (buscar todos os grupos ativos)
        try:
            from backend.models import GrupoAgregador
        except ImportError:
            from models import GrupoAgregador

        grupos = GrupoAgregador.query.filter_by(ativo=True).all()

        for grupo in grupos:
            alerta = CartaoService.calcular_alerta_global(grupo.id, competencia)
            if alerta:
                # Se cartao_id foi especificado, verificar se o grupo contÃ©m itens desse cartÃ£o
                if cartao_id:
                    tem_item_do_cartao = any(
                        item['cartao_id'] == cartao_id for item in alerta.get('itens', [])
                    )
                    if tem_item_do_cartao:
                        alertas_globais.append(alerta)
                else:
                    alertas_globais.append(alerta)

        return {
            'locais': alertas_locais,
            'globais': alertas_globais,
            'total_alertas': len(alertas_locais) + len(alertas_globais)
        }
