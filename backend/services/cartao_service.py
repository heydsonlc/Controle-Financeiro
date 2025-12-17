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
            raise ValueError('Fatura não encontrada')

        if not fatura.is_fatura_cartao:
            raise ValueError('Esta conta não é uma fatura de cartão')

        # Validar se já está paga
        if fatura.status_pagamento == 'Pago':
            raise ValueError('Fatura já foi paga anteriormente')

        # Converter data se necessário
        if isinstance(data_pagamento, str):
            data_pagamento = datetime.strptime(data_pagamento, '%Y-%m-%d').date()

        # Calcular valor executado final
        # Se a fatura já tem valor_executado, usa ele (evita recalcular desnecessariamente)
        # Senão, calcula a partir dos lançamentos
        if fatura.valor_executado and fatura.valor_executado > 0:
            valor_executado_final = fatura.valor_executado
        else:
            valor_executado_final = CartaoService.calcular_executado(
                fatura.item_despesa_id,
                fatura.cartao_competencia
            )

        # Definir valor final do pagamento
        valor_final_pagamento = valor_pago if valor_pago else valor_executado_final

        # SE conta bancária informada: debitar saldo
        if conta_bancaria_id:
            conta = ContaBancaria.query.get(conta_bancaria_id)
            if not conta:
                raise ValueError('Conta bancária não encontrada')

            if conta.status != 'ATIVO':
                raise ValueError('Conta bancária está inativa')

            # Criar movimento financeiro (débito)
            movimento = MovimentoFinanceiro(
                conta_bancaria_id=conta_bancaria_id,
                tipo='DEBITO',
                valor=valor_final_pagamento,
                descricao=f'Pagamento fatura cartão - {fatura.descricao}',
                data_movimento=data_pagamento,
                fatura_id=fatura_id
            )
            db.session.add(movimento)

            # Debitar saldo da conta
            conta.saldo_atual = conta.saldo_atual - valor_final_pagamento

        # Atualizar fatura
        fatura.valor_executado = valor_executado_final
        fatura.valor = valor_final_pagamento  # Substitui planejado por executado
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
                - cartao_id: ID do cartão (obrigatório)
                - item_agregado_id: ID da categoria (OPCIONAL - se None, não controla limite)
                - valor: Valor do lançamento
                - descricao: Descrição
                - data_compra: Data da compra
                - mes_fatura: Mês da fatura
                - categoria_id: Categoria real da despesa
                - numero_parcela, total_parcelas (opcional)

        Returns:
            tuple: (LancamentoAgregado, Conta fatura)
        """
        # ID do cartão (agora obrigatório nos dados)
        cartao_id = dados_lancamento['cartao_id']

        # Item agregado é OPCIONAL
        item_agregado_id = dados_lancamento.get('item_agregado_id')
        if item_agregado_id:
            item_agregado = ItemAgregado.query.get(item_agregado_id)
            if not item_agregado:
                raise ValueError('ItemAgregado não encontrado')

        # Mês da fatura (competência)
        mes_fatura = dados_lancamento['mes_fatura']
        if isinstance(mes_fatura, str):
            mes_fatura = datetime.strptime(mes_fatura, '%Y-%m-%d').date()
        mes_fatura = mes_fatura.replace(day=1)

        # Garantir que a fatura existe (criar se necessário)
        fatura = CartaoService.get_or_create_fatura(cartao_id, mes_fatura)

        # Criar lançamento (não cria despesa separada!)
        lancamento = LancamentoAgregado(
            cartao_id=cartao_id,
            item_agregado_id=item_agregado_id,  # Pode ser None
            categoria_id=dados_lancamento['categoria_id'],  # Categoria da DESPESA (obrigatória)
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

    # ========================================================================
    # SISTEMA DE ALERTAS (NÃO BLOQUEANTE)
    # ========================================================================

    @staticmethod
    def calcular_alerta_local(item_agregado_id, competencia):
        """
        Calcula alerta LOCAL para um ItemAgregado específico

        Verifica se o consumo real ultrapassou o orçamento da categoria

        IMPORTANTE: Alertas NÃO bloqueiam lançamentos, são apenas informativos

        Args:
            item_agregado_id (int): ID do ItemAgregado (categoria do cartão)
            competencia (date): Mês de referência

        Returns:
            dict ou None: Alerta estruturado ou None se não houver estouro
        """
        comp_primeiro_dia = competencia.replace(day=1)

        # Buscar item agregado
        item = ItemAgregado.query.get(item_agregado_id)
        if not item or not item.ativo:
            return None

        # Buscar orçamento vigente
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

        # Calcular consumo real (lançamentos do mês)
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

            # Determinar nível de alerta
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
        (em diferentes cartões) ultrapassou a soma dos orçamentos

        IMPORTANTE:
        - Grupos NÃO possuem orçamento próprio
        - O limite é a soma dos orçamentos dos itens vinculados
        - Permite acompanhamento familiar/casal

        Args:
            grupo_agregador_id (int): ID do GrupoAgregador
            competencia (date): Mês de referência

        Returns:
            dict ou None: Alerta estruturado ou None se não houver estouro
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

        # Calcular soma dos orçamentos e consumos
        total_orcado = Decimal('0')
        total_consumo = Decimal('0')
        detalhes_itens = []

        for item in itens_do_grupo:
            # Buscar orçamento vigente
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

            # Determinar nível de alerta
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
        Retorna todos os alertas (locais e globais) para um cartão ou mês

        Args:
            cartao_id (int, opcional): ID do cartão (se None, busca todos)
            competencia (date, opcional): Mês de referência (se None, usa mês atual)

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
                # Se cartao_id foi especificado, verificar se o grupo contém itens desse cartão
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
