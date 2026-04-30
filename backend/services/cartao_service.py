"""
ServiÃ§o de CartÃ£o de CrÃ©dito - LÃ³gica de negÃ³cio

Este serviÃ§o implementa:
1. GeraÃ§Ã£o de faturas virtuais (planejado vs executado)
2. Controle de orÃ§amento por categoria
3. Consumo de orÃ§amento por lanÃ§amentos
4. Pagamento de faturas (planejado â†’ executado)
5. Alertas de estouro de orÃ§amento
"""
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from decimal import Decimal
from sqlalchemy import func, and_
import uuid
import logging

try:
    from backend.models import (db, Conta, ItemDespesa, ItemAgregado,
                                OrcamentoAgregado, LancamentoAgregado, ConfigAgregador)
except ImportError:
    from models import (db, Conta, ItemDespesa, ItemAgregado,
                       OrcamentoAgregado, LancamentoAgregado, ConfigAgregador)

logger = logging.getLogger(__name__)


class CartaoService:
    """
    ServiÃ§o para gerenciamento completo de cartÃµes de crÃ©dito
    """

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
        comp_primeiro_dia = competencia.replace(day=1)

        # Buscar fatura existente
        fatura = Conta.query.filter_by(
            item_despesa_id=cartao_id,
            is_fatura_cartao=True,
            cartao_competencia=comp_primeiro_dia
        ).first()

        if fatura:
            return fatura

        # Criar nova fatura virtual
        cartao = ItemDespesa.query.get(cartao_id)
        if not cartao or cartao.tipo != 'Agregador':
            raise ValueError(f'ItemDespesa {cartao_id} nÃ£o Ã© um cartÃ£o de crÃ©dito')

        # Buscar configuraÃ§Ã£o do cartÃ£o
        config = ConfigAgregador.query.filter_by(item_despesa_id=cartao_id).first()
        if not config:
            raise ValueError(f'CartÃ£o {cartao_id} sem configuraÃ§Ã£o de fechamento/vencimento')

        # Calcular valor planejado (soma dos orÃ§amentos)
        valor_planejado = CartaoService.calcular_planejado(cartao_id, comp_primeiro_dia)

        # Calcular data de vencimento baseada no dia de vencimento configurado
        data_vencimento = comp_primeiro_dia.replace(day=config.dia_vencimento)

        # Criar fatura
        fatura = Conta(
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

        db.session.add(fatura)
        db.session.commit()

        return fatura

    @staticmethod
    def calcular_planejado(cartao_id, competencia):
        """
        Calcula valor planejado da fatura = soma dos orÃ§amentos das categorias

        Args:
            cartao_id (int): ID do cartÃ£o
            competencia (date): MÃªs de referÃªncia

        Returns:
            Decimal: Valor total orÃ§ado
        """
        comp_primeiro_dia = competencia.replace(day=1)

        # Buscar todos os itens agregados (categorias) do cartÃ£o
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
        Calcula valor executado da fatura = soma real dos lanÃ§amentos

        Args:
            cartao_id (int): ID do cartÃ£o
            competencia (date): MÃªs de referÃªncia

        Returns:
            Decimal: Valor total gasto
        """
        comp_primeiro_dia = competencia.replace(day=1)

        # Buscar todos os itens agregados do cartÃ£o
        itens_agregados_ids = [item.id for item in ItemAgregado.query.filter_by(
            item_despesa_id=cartao_id
        ).all()]

        if not itens_agregados_ids:
            return Decimal('0')

        # Somar lanÃ§amentos do mÃªs
        # Usar STRFTIME para compatibilidade com SQLite
        total_executado = db.session.query(
            func.coalesce(func.sum(LancamentoAgregado.valor), 0)
        ).filter(
            LancamentoAgregado.item_agregado_id.in_(itens_agregados_ids),
            func.strftime('%Y-%m', LancamentoAgregado.mes_fatura) == comp_primeiro_dia.strftime('%Y-%m')
        ).scalar()

        return Decimal(str(total_executado or 0))

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
    def recalcular_fatura(cartao_id, competencia):
        """
        Recalcula uma fatura existente (Ãºtil apÃ³s adicionar/remover lanÃ§amentos)

        Args:
            cartao_id (int): ID do cartÃ£o
            competencia (date): MÃªs de referÃªncia

        Returns:
            Conta: Fatura atualizada
        """
        fatura = CartaoService.get_or_create_fatura(cartao_id, competencia)

        # Se jÃ¡ foi paga, nÃ£o recalcular
        if fatura.status_pagamento == 'Pago':
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
        Registra pagamento da fatura e substitui planejado por executado

        Args:
            fatura_id (int): ID da fatura (Conta)
            data_pagamento (date ou str): Data do pagamento
            valor_pago (Decimal, opcional): Valor pago (se None, usa executado)
            conta_bancaria_id (int, opcional): ID da conta para debitar

        Returns:
            Conta: Fatura atualizada
        """
        from backend.models import ContaBancaria, MovimentoFinanceiro

        fatura = Conta.query.get(fatura_id)
        if not fatura:
            raise ValueError('Fatura nÃ£o encontrada')

        if not fatura.is_fatura_cartao:
            raise ValueError('Esta conta nÃ£o Ã© uma fatura de cartÃ£o')

        # Validar se jÃ¡ estÃ¡ paga
        if fatura.status_pagamento == 'Pago':
            raise ValueError('Fatura jÃ¡ foi paga anteriormente')

        # Converter data se necessÃ¡rio
        if isinstance(data_pagamento, str):
            data_pagamento = datetime.strptime(data_pagamento, '%Y-%m-%d').date()

        # Calcular valor executado final
        # Se a fatura jÃ¡ tem valor_executado, usa ele (evita recalcular desnecessariamente)
        # SenÃ£o, calcula a partir dos lanÃ§amentos
        if fatura.valor_executado and fatura.valor_executado > 0:
            valor_executado_final = fatura.valor_executado
        else:
            valor_executado_final = CartaoService.calcular_executado(
                fatura.item_despesa_id,
                fatura.cartao_competencia
            )

        # Definir valor final do pagamento
        valor_final_pagamento = valor_pago if valor_pago else valor_executado_final

        # SE conta bancÃ¡ria informada: debitar saldo
        if conta_bancaria_id:
            conta = ContaBancaria.query.get(conta_bancaria_id)
            if not conta:
                raise ValueError('Conta bancÃ¡ria nÃ£o encontrada')

            if conta.status != 'ATIVO':
                raise ValueError('Conta bancÃ¡ria estÃ¡ inativa')

            # Criar movimento financeiro (dÃ©bito)
            movimento = MovimentoFinanceiro(
                conta_bancaria_id=conta_bancaria_id,
                tipo='DEBITO',
                valor=valor_final_pagamento,
                descricao=f'Pagamento fatura cartÃ£o - {fatura.descricao}',
                data_movimento=data_pagamento,
                fatura_id=fatura_id,
                conta_id=fatura_id,
                origem='FATURA',
                ajustavel=False
            )
            db.session.add(movimento)
            try:
                from backend.services.conta_bancaria_service import ContaBancariaService
            except ImportError:
                from services.conta_bancaria_service import ContaBancariaService
            ContaBancariaService.recalcular_saldo_conta(conta_bancaria_id)
            fatura.conta_bancaria_id = conta_bancaria_id

        # Atualizar fatura
        fatura.valor_executado = valor_executado_final
        fatura.valor = valor_final_pagamento  # Substitui planejado por executado
        fatura.data_pagamento = data_pagamento
        fatura.status_pagamento = 'Pago'

        db.session.commit()
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

        # Item agregado Ã© OPCIONAL
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

        # Criar uma parcela para cada mÃªs
        for n in range(1, total_parcelas + 1):
            # Calcular data da parcela (incrementa mÃªs a cada parcela)
            data_parcela = data_compra_inicial + relativedelta(months=n-1)
            mes_fatura_parcela = mes_fatura_inicial + relativedelta(months=n-1)

            # REGRA DE FECHAMENTO DE FATURA:
            # Se a fatura do mÃªs estiver PAGA, redirecionar para a prÃ³xima fatura
            fatura_mes = CartaoService.get_or_create_fatura(cartao_id, mes_fatura_parcela)
            if fatura_mes.status_fatura == 'PAGA':
                # Buscar prÃ³xima fatura em aberto
                mes_fatura_parcela = mes_fatura_parcela + relativedelta(months=1)
                fatura_mes = CartaoService.get_or_create_fatura(cartao_id, mes_fatura_parcela)

            # Calcular valor desta parcela (distribui centavos do resto nas primeiras parcelas)
            centavos_parcela = centavos_base + (1 if n <= centavos_resto else 0)
            valor_parcela = Decimal(centavos_parcela) / 100

            # FASE 2: IDEMPOTÃŠNCIA ROBUSTA
            # Verifica se parcela jÃ¡ existe usando compra_id (UUID Ãºnico)
            # Muito mais seguro que usar descriÃ§Ã£o (texto livre)
            lancamento_existente = LancamentoAgregado.query.filter_by(
                compra_id=compra_uuid,
                numero_parcela=n
            ).first()

            if lancamento_existente:
                # Parcela jÃ¡ existe, pular
                if n == 1:
                    lancamentos_criados.append(lancamento_existente)
                    primeira_fatura = fatura_mes
                continue

            # Criar lanÃ§amento da parcela
            lancamento = LancamentoAgregado(
                cartao_id=cartao_id,
                item_agregado_id=item_agregado_id,  # Pode ser None
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

            db.session.add(lancamento)
            lancamentos_criados.append(lancamento)

            # Guardar primeira fatura para retornar
            if n == 1:
                primeira_fatura = fatura_mes

            # Registrar fatura afetada (mÃªs real usado, apÃ³s possÃ­vel redirecionamento)
            faturas_afetadas_set.add(mes_fatura_parcela)

        db.session.flush()

        # Recalcular TODAS as faturas afetadas (considerando redirecionamentos por status PAGA)
        for mes_fatura_afetada in faturas_afetadas_set:
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
        fatura = CartaoService.get_or_create_fatura(cartao_id, competencia)

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
                    OrcamentoAgregado.vigencia_inicio <= competencia,
                    (OrcamentoAgregado.vigencia_fim == None) |
                    (OrcamentoAgregado.vigencia_fim >= competencia)
                )
            ).first()

            if not orcamento:
                continue

            # Gasto da categoria
            # Usar STRFTIME para compatibilidade com SQLite
            gasto = db.session.query(
                func.coalesce(func.sum(LancamentoAgregado.valor), 0)
            ).filter(
                LancamentoAgregado.item_agregado_id == item.id,
                func.strftime('%Y-%m', LancamentoAgregado.mes_fatura) == competencia.strftime('%Y-%m')
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
        cartoes = ItemDespesa.query.filter_by(tipo='Agregador', ativo=True).all()

        faturas_criadas = []

        for cartao in cartoes:
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
        comp_primeiro_dia = competencia.replace(day=1)

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
            func.strftime('%Y-%m', LancamentoAgregado.mes_fatura) == comp_primeiro_dia.strftime('%Y-%m')
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
        comp_primeiro_dia = competencia.replace(day=1)

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
                func.strftime('%Y-%m', LancamentoAgregado.mes_fatura) == comp_primeiro_dia.strftime('%Y-%m')
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
            competencia = competencia.replace(day=1)

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
