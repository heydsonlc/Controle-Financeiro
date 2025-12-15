"""
Serviço de Cartão de Crédito - Lógica de negócio

Este serviço implementa:
1. Geração de faturas virtuais (planejado vs executado)
2. Controle de orçamento por categoria
3. Consumo de orçamento por lançamentos
4. Pagamento de faturas (planejado → executado)
5. Alertas de estouro de orçamento
"""
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from decimal import Decimal
from sqlalchemy import func, and_

try:
    from backend.models import (db, Conta, ItemDespesa, ItemAgregado,
                                OrcamentoAgregado, LancamentoAgregado, ConfigAgregador)
except ImportError:
    from models import (db, Conta, ItemDespesa, ItemAgregado,
                       OrcamentoAgregado, LancamentoAgregado, ConfigAgregador)


class CartaoService:
    """
    Serviço para gerenciamento completo de cartões de crédito
    """

    # ========================================================================
    # GERAÇÃO E RECUPERAÇÃO DE FATURAS
    # ========================================================================

    @staticmethod
    def get_or_create_fatura(cartao_id, competencia):
        """
        Busca ou cria uma fatura virtual para o cartão + mês

        A fatura sempre existe, mesmo sem lançamentos.
        Valor inicial = soma dos orçamentos das categorias do cartão

        Args:
            cartao_id (int): ID do ItemDespesa (tipo 'Agregador')
            competencia (date): Mês de referência (YYYY-MM-01)

        Returns:
            Conta: Fatura do cartão (planejado ou executado)
        """
        # Normalizar competência para primeiro dia do mês
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
            raise ValueError(f'ItemDespesa {cartao_id} não é um cartão de crédito')

        # Buscar configuração do cartão
        config = ConfigAgregador.query.filter_by(item_despesa_id=cartao_id).first()
        if not config:
            raise ValueError(f'Cartão {cartao_id} sem configuração de fechamento/vencimento')

        # Calcular valor planejado (soma dos orçamentos)
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
            valor_executado=Decimal('0'),  # Será calculado ao pagar
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
        Calcula valor planejado da fatura = soma dos orçamentos das categorias

        Args:
            cartao_id (int): ID do cartão
            competencia (date): Mês de referência

        Returns:
            Decimal: Valor total orçado
        """
        comp_primeiro_dia = competencia.replace(day=1)

        # Buscar todos os itens agregados (categorias) do cartão
        itens_agregados = ItemAgregado.query.filter_by(
            item_despesa_id=cartao_id
        ).all()

        total_planejado = Decimal('0')

        for item in itens_agregados:
            # Buscar orçamento vigente para essa categoria nessa competência
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
        Calcula valor executado da fatura = soma real dos lançamentos

        Args:
            cartao_id (int): ID do cartão
            competencia (date): Mês de referência

        Returns:
            Decimal: Valor total gasto
        """
        comp_primeiro_dia = competencia.replace(day=1)

        # Buscar todos os itens agregados do cartão
        itens_agregados_ids = [item.id for item in ItemAgregado.query.filter_by(
            item_despesa_id=cartao_id
        ).all()]

        if not itens_agregados_ids:
            return Decimal('0')

        # Somar lançamentos do mês
        # Usar STRFTIME para compatibilidade com SQLite
        total_executado = db.session.query(
            func.coalesce(func.sum(LancamentoAgregado.valor), 0)
        ).filter(
            LancamentoAgregado.item_agregado_id.in_(itens_agregados_ids),
            func.strftime('%Y-%m', LancamentoAgregado.mes_fatura) == comp_primeiro_dia.strftime('%Y-%m')
        ).scalar()

        return Decimal(str(total_executado or 0))

    @staticmethod
    def recalcular_fatura(cartao_id, competencia):
        """
        Recalcula uma fatura existente (útil após adicionar/remover lançamentos)

        Args:
            cartao_id (int): ID do cartão
            competencia (date): Mês de referência

        Returns:
            Conta: Fatura atualizada
        """
        fatura = CartaoService.get_or_create_fatura(cartao_id, competencia)

        # Se já foi paga, não recalcular
        if fatura.status_pagamento == 'Pago':
            return fatura

        # Recalcular planejado (pode ter mudado o orçamento)
        fatura.valor_planejado = CartaoService.calcular_planejado(cartao_id, competencia)

        # Calcular executado atual
        fatura.valor_executado = CartaoService.calcular_executado(cartao_id, competencia)

        # Verificar estouro
        if fatura.valor_executado > fatura.valor_planejado:
            fatura.estouro_orcamento = True
        else:
            fatura.estouro_orcamento = False

        # Valor exibido = planejado (enquanto não paga)
        fatura.valor = fatura.valor_planejado

        db.session.commit()
        return fatura

    # ========================================================================
    # PAGAMENTO DE FATURAS
    # ========================================================================

    @staticmethod
    def pagar_fatura(fatura_id, data_pagamento, valor_pago=None):
        """
        Registra pagamento da fatura e substitui planejado por executado

        Args:
            fatura_id (int): ID da fatura (Conta)
            data_pagamento (date ou str): Data do pagamento
            valor_pago (Decimal, opcional): Valor pago (se None, usa executado)

        Returns:
            Conta: Fatura atualizada
        """
        fatura = Conta.query.get(fatura_id)
        if not fatura:
            raise ValueError('Fatura não encontrada')

        if not fatura.is_fatura_cartao:
            raise ValueError('Esta conta não é uma fatura de cartão')

        # Converter data se necessário
        if isinstance(data_pagamento, str):
            data_pagamento = datetime.strptime(data_pagamento, '%Y-%m-%d').date()

        # Calcular valor executado final
        valor_executado_final = CartaoService.calcular_executado(
            fatura.item_despesa_id,
            fatura.cartao_competencia
        )

        # Atualizar fatura
        fatura.valor_executado = valor_executado_final
        fatura.valor = valor_pago if valor_pago else valor_executado_final  # Substitui planejado por executado
        fatura.data_pagamento = data_pagamento
        fatura.status_pagamento = 'Pago'

        db.session.commit()
        return fatura

    # ========================================================================
    # LANÇAMENTOS
    # ========================================================================

    @staticmethod
    def adicionar_lancamento(dados_lancamento):
        """
        Adiciona um lançamento no cartão e garante que a fatura existe

        Args:
            dados_lancamento (dict): Dados do lançamento
                - item_agregado_id: ID da categoria (ItemAgregado)
                - valor: Valor do lançamento
                - descricao: Descrição
                - data_compra: Data da compra
                - mes_fatura: Mês da fatura
                - categoria_id: Categoria real da despesa
                - numero_parcela, total_parcelas (opcional)

        Returns:
            tuple: (LancamentoAgregado, Conta fatura)
        """
        # Buscar item agregado
        item_agregado = ItemAgregado.query.get(dados_lancamento['item_agregado_id'])
        if not item_agregado:
            raise ValueError('ItemAgregado não encontrado')

        # ID do cartão
        cartao_id = item_agregado.item_despesa_id

        # Mês da fatura (competência)
        mes_fatura = dados_lancamento['mes_fatura']
        if isinstance(mes_fatura, str):
            mes_fatura = datetime.strptime(mes_fatura, '%Y-%m-%d').date()
        mes_fatura = mes_fatura.replace(day=1)

        # Garantir que a fatura existe (criar se necessário)
        fatura = CartaoService.get_or_create_fatura(cartao_id, mes_fatura)

        # Criar lançamento (não cria despesa separada!)
        lancamento = LancamentoAgregado(
            item_agregado_id=dados_lancamento['item_agregado_id'],
            valor=Decimal(str(dados_lancamento['valor'])),
            descricao=dados_lancamento['descricao'],
            data_compra=dados_lancamento['data_compra'],
            mes_fatura=mes_fatura,
            numero_parcela=dados_lancamento.get('numero_parcela', 1),
            total_parcelas=dados_lancamento.get('total_parcelas', 1),
            observacoes=dados_lancamento.get('observacoes', '')
        )

        db.session.add(lancamento)
        db.session.flush()

        # Recalcular fatura (atualiza executado e verifica estouro)
        fatura = CartaoService.recalcular_fatura(cartao_id, mes_fatura)

        db.session.commit()
        return lancamento, fatura

    @staticmethod
    def avaliar_alertas(cartao_id, competencia):
        """
        Avalia se há alertas de estouro de orçamento

        Args:
            cartao_id (int): ID do cartão
            competencia (date): Mês de referência

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
            # Orçamento da categoria
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
    # GERAÇÃO AUTOMÁTICA DE FATURAS (JOB MENSAL)
    # ========================================================================

    @staticmethod
    def gerar_faturas_mes_atual():
        """
        Job mensal: Gera faturas virtuais para todos os cartões ativos no mês atual

        Deve ser executado no 1º dia de cada mês

        Returns:
            list: Lista de faturas criadas
        """
        mes_atual = date.today().replace(day=1)

        # Buscar todos os cartões ativos
        cartoes = ItemDespesa.query.filter_by(tipo='Agregador', ativo=True).all()

        faturas_criadas = []

        for cartao in cartoes:
            try:
                fatura = CartaoService.get_or_create_fatura(cartao.id, mes_atual)
                faturas_criadas.append(fatura)
            except Exception as e:
                print(f'Erro ao criar fatura para cartão {cartao.id}: {str(e)}')
                continue

        return faturas_criadas
