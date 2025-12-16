"""
Serviço de Financiamentos - Lógica de negócio

Este serviço implementa:
1. CRUD de financiamentos
2. Geração de tabelas de amortização (SAC, PRICE, SIMPLES)
3. Aplicação de indexadores (TR, IPCA)
4. Amortizações extraordinárias
5. Integração com contas a pagar
6. Demonstrativos e relatórios
"""
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from sqlalchemy import func, extract, and_
from decimal import Decimal
import math

try:
    from backend.models import (db, Financiamento, FinanciamentoParcela,
                                FinanciamentoAmortizacaoExtra, IndexadorMensal, Conta)
except ImportError:
    from models import (db, Financiamento, FinanciamentoParcela,
                       FinanciamentoAmortizacaoExtra, IndexadorMensal, Conta)


class FinanciamentoService:
    """
    Serviço para gerenciamento completo de financiamentos
    """

    # ========================================================================
    # CRUD DE FINANCIAMENTOS
    # ========================================================================

    @staticmethod
    def criar_financiamento(dados):
        """
        Cria um financiamento e gera automaticamente as parcelas

        Args:
            dados (dict): Dados do financiamento
                - nome (str): Nome do financiamento
                - produto (str): Tipo de produto
                - sistema_amortizacao (str): SAC, PRICE ou SIMPLES
                - valor_financiado (float): Valor total financiado
                - prazo_total_meses (int): Prazo em meses
                - taxa_juros_nominal_anual (float): Taxa anual em %
                - indexador_saldo (str, opcional): TR, IPCA, etc
                - data_contrato (str ou date): Data do contrato
                - data_primeira_parcela (str ou date): Data da 1ª parcela
                - valor_seguro_mensal (float, opcional): Valor fixo mensal do seguro
                - valor_taxa_adm_mensal (float, opcional): Valor fixo mensal da taxa administrativa

        Returns:
            Financiamento: Objeto criado com parcelas geradas

        Raises:
            ValueError: Se dados inválidos
        """
        # Validações
        if not dados.get('nome'):
            raise ValueError('Nome é obrigatório')

        if not dados.get('sistema_amortizacao') or dados['sistema_amortizacao'] not in ['SAC', 'PRICE', 'SIMPLES']:
            raise ValueError('Sistema de amortização deve ser SAC, PRICE ou SIMPLES')

        if not dados.get('valor_financiado') or float(dados['valor_financiado']) <= 0:
            raise ValueError('Valor financiado deve ser maior que zero')

        if not dados.get('prazo_total_meses') or int(dados['prazo_total_meses']) <= 0:
            raise ValueError('Prazo total deve ser maior que zero')

        if not dados.get('taxa_juros_nominal_anual') or float(dados['taxa_juros_nominal_anual']) < 0:
            raise ValueError('Taxa de juros não pode ser negativa')

        # Converter taxas
        taxa_anual = Decimal(str(dados['taxa_juros_nominal_anual']))
        taxa_mensal = FinanciamentoService._calcular_taxa_mensal(taxa_anual)

        # Converter datas
        if isinstance(dados['data_contrato'], str):
            data_contrato = datetime.strptime(dados['data_contrato'], '%Y-%m-%d').date()
        else:
            data_contrato = dados['data_contrato']

        if isinstance(dados['data_primeira_parcela'], str):
            data_primeira_parcela = datetime.strptime(dados['data_primeira_parcela'], '%Y-%m-%d').date()
        else:
            data_primeira_parcela = dados['data_primeira_parcela']

        # Criar financiamento
        financiamento = Financiamento(
            nome=dados['nome'],
            produto=dados.get('produto', ''),
            sistema_amortizacao=dados['sistema_amortizacao'],
            valor_financiado=Decimal(str(dados['valor_financiado'])),
            prazo_total_meses=int(dados['prazo_total_meses']),
            prazo_remanescente_meses=int(dados['prazo_total_meses']),
            taxa_juros_nominal_anual=taxa_anual,
            taxa_juros_efetiva_anual=Decimal(str(dados.get('taxa_juros_efetiva_anual', 0))) if dados.get('taxa_juros_efetiva_anual') else None,
            taxa_juros_efetiva_relacionamento_anual=Decimal(str(dados.get('taxa_juros_efetiva_relacionamento_anual', 0))) if dados.get('taxa_juros_efetiva_relacionamento_anual') else None,
            taxa_juros_mensal=taxa_mensal,
            indexador_saldo=dados.get('indexador_saldo'),
            data_contrato=data_contrato,
            data_primeira_parcela=data_primeira_parcela,
            item_despesa_id=dados.get('item_despesa_id'),
            # Configuração de seguro
            seguro_tipo=dados.get('seguro_tipo', 'fixo'),
            seguro_percentual=Decimal(str(dados.get('seguro_percentual', 0.0006))),
            valor_seguro_mensal=Decimal(str(dados.get('valor_seguro_mensal', 0))),
            # Taxa de administração
            taxa_administracao_fixa=Decimal(str(dados.get('taxa_administracao_fixa', 0))),
            ativo=True
        )

        db.session.add(financiamento)
        db.session.flush()  # Para obter o ID

        # Gerar parcelas (agora usa configurações do próprio financiamento)
        FinanciamentoService.gerar_parcelas(financiamento)

        db.session.commit()
        return financiamento

    @staticmethod
    def _calcular_taxa_mensal(taxa_anual_percentual):
        """
        Converte taxa anual nominal em taxa mensal

        Args:
            taxa_anual_percentual (Decimal): Taxa anual em % (ex: 8.5)

        Returns:
            Decimal: Taxa mensal (ex: 0.006827)
        """
        taxa_anual = taxa_anual_percentual / Decimal('100')
        # Fórmula: (1 + taxa_anual)^(1/12) - 1
        taxa_mensal = (Decimal('1') + taxa_anual) ** (Decimal('1') / Decimal('12')) - Decimal('1')
        return taxa_mensal

    @staticmethod
    def listar_financiamentos(ativo=None):
        """
        Lista financiamentos com filtro opcional

        Args:
            ativo (bool, opcional): Filtrar por status ativo

        Returns:
            list[Financiamento]: Lista de financiamentos
        """
        query = Financiamento.query

        if ativo is not None:
            query = query.filter_by(ativo=ativo)

        return query.order_by(Financiamento.data_contrato.desc()).all()

    @staticmethod
    def atualizar_financiamento(financiamento_id, dados):
        """
        Atualiza dados gerais do financiamento

        Args:
            financiamento_id (int): ID do financiamento
            dados (dict): Dados para atualizar

        Returns:
            Financiamento: Financiamento atualizado

        Nota: Ao alterar configurações de seguro, considere regenerar as parcelas
        """
        financiamento = Financiamento.query.get(financiamento_id)
        if not financiamento:
            raise ValueError('Financiamento não encontrado')

        # Atualizar campos permitidos
        if 'nome' in dados:
            financiamento.nome = dados['nome']
        if 'produto' in dados:
            financiamento.produto = dados['produto']
        if 'ativo' in dados:
            financiamento.ativo = dados['ativo']
        if 'item_despesa_id' in dados:
            financiamento.item_despesa_id = dados['item_despesa_id']

        # Atualizar configurações de seguro
        if 'seguro_tipo' in dados:
            financiamento.seguro_tipo = dados['seguro_tipo']
        if 'seguro_percentual' in dados:
            financiamento.seguro_percentual = Decimal(str(dados['seguro_percentual']))
        if 'valor_seguro_mensal' in dados:
            financiamento.valor_seguro_mensal = Decimal(str(dados['valor_seguro_mensal']))

        # Atualizar taxa de administração
        if 'taxa_administracao_fixa' in dados:
            financiamento.taxa_administracao_fixa = Decimal(str(dados['taxa_administracao_fixa']))

        # Identificar se houve mudança em encargos que requerem recálculo
        campos_que_afetam_parcelas = ['seguro_tipo', 'seguro_percentual', 'valor_seguro_mensal', 'taxa_administracao_fixa']
        requer_recalculo = any(campo in dados for campo in campos_que_afetam_parcelas)

        db.session.commit()

        # Recalcular parcelas futuras se houve mudança em encargos
        if requer_recalculo:
            FinanciamentoService.recalcular_parcelas_futuras(financiamento.id)

        return financiamento

    @staticmethod
    def inativar_financiamento(financiamento_id):
        """
        Inativa (soft delete) um financiamento

        Args:
            financiamento_id (int): ID do financiamento

        Returns:
            Financiamento: Financiamento inativado
        """
        financiamento = Financiamento.query.get(financiamento_id)
        if not financiamento:
            raise ValueError('Financiamento não encontrado')

        financiamento.ativo = False
        db.session.commit()

        # Criar contas (despesas) para as parcelas
        if financiamento.item_despesa_id:
            FinanciamentoService.sincronizar_contas(financiamento.id)

        return financiamento

    @staticmethod
    def pode_excluir_financiamento(financiamento_id: int) -> bool:
        """
        Verifica se um financiamento pode ser excluído definitivamente.

        Um financiamento só pode ser excluído se:
        - nenhuma parcela estiver paga
        - não existir amortização extraordinária

        Args:
            financiamento_id (int): ID do financiamento

        Returns:
            bool: True se pode excluir, False caso contrário
        """
        # Verificar se existe alguma parcela paga
        parcelas_pagas = FinanciamentoParcela.query.filter_by(
            financiamento_id=financiamento_id,
            status='pago'
        ).count()

        if parcelas_pagas > 0:
            return False

        # Verificar se existe alguma amortização extraordinária
        amortizacoes = FinanciamentoAmortizacaoExtra.query.filter_by(
            financiamento_id=financiamento_id
        ).count()

        if amortizacoes > 0:
            return False

        return True

    @staticmethod
    def excluir_financiamento(financiamento_id: int):
        """
        Exclusão definitiva de financiamento SEM impacto financeiro.

        Regra:
        - nenhuma parcela paga
        - nenhuma amortização registrada

        Args:
            financiamento_id (int): ID do financiamento

        Raises:
            ValueError: Se financiamento não existe ou não pode ser excluído
        """
        financiamento = Financiamento.query.get(financiamento_id)

        if not financiamento:
            raise ValueError("Financiamento não encontrado")

        if not FinanciamentoService.pode_excluir_financiamento(financiamento_id):
            raise ValueError(
                "Financiamento possui histórico financeiro e não pode ser excluído. "
                "Utilize a opção de inativar."
            )

        try:
            # Excluir despesas vinculadas (1 parcela = 1 despesa)
            if financiamento.item_despesa_id:
                Conta.query.filter(
                    Conta.item_despesa_id == financiamento.item_despesa_id
                ).delete(synchronize_session=False)

            # Excluir parcelas
            FinanciamentoParcela.query.filter_by(
                financiamento_id=financiamento_id
            ).delete(synchronize_session=False)

            # Excluir financiamento
            db.session.delete(financiamento)

            db.session.commit()

        except Exception:
            db.session.rollback()
            raise

    @staticmethod
    def recalcular_parcelas_futuras(financiamento_id):
        """
        Recalcula APENAS as parcelas futuras (status PENDENTE) de um financiamento
        Preserva parcelas já pagas

        Args:
            financiamento_id (int): ID do financiamento

        Returns:
            int: Número de parcelas recalculadas
        """
        financiamento = Financiamento.query.get(financiamento_id)
        if not financiamento:
            raise ValueError('Financiamento não encontrado')

        # Buscar parcelas pendentes
        parcelas_pendentes = FinanciamentoParcela.query.filter_by(
            financiamento_id=financiamento_id,
            status='pendente'
        ).order_by(FinanciamentoParcela.numero_parcela).all()

        if not parcelas_pendentes:
            return 0  # Nenhuma parcela para recalcular

        # Buscar última parcela paga para determinar saldo atual
        ultima_paga = FinanciamentoParcela.query.filter_by(
            financiamento_id=financiamento_id,
            status='pago'
        ).order_by(FinanciamentoParcela.numero_parcela.desc()).first()

        # Determinar saldo devedor inicial
        if ultima_paga:
            saldo_devedor = ultima_paga.saldo_devedor_apos_pagamento
        else:
            saldo_devedor = financiamento.valor_financiado

        # Taxa de juros mensal
        taxa_mensal = financiamento.taxa_juros_mensal
        sistema = financiamento.sistema_amortizacao

        # Recalcular cada parcela pendente
        for parcela in parcelas_pendentes:
            # Calcular juros sobre saldo atual
            juros = saldo_devedor * taxa_mensal

            # Calcular amortização baseada no sistema
            if sistema == 'SAC':
                # Amortização constante = saldo / parcelas restantes
                num_parcelas_restantes = len([p for p in parcelas_pendentes if p.numero_parcela >= parcela.numero_parcela])
                amortizacao = saldo_devedor / Decimal(str(num_parcelas_restantes))
            elif sistema == 'PRICE':
                # Recalcular PMT com saldo e parcelas restantes
                n = len([p for p in parcelas_pendentes if p.numero_parcela >= parcela.numero_parcela])
                if taxa_mensal > 0:
                    fator = (Decimal('1') + taxa_mensal) ** Decimal(str(n))
                    pmt = saldo_devedor * taxa_mensal * fator / (fator - Decimal('1'))
                else:
                    pmt = saldo_devedor / Decimal(str(n))
                amortizacao = pmt - juros
            else:  # SIMPLES
                num_parcelas_restantes = len([p for p in parcelas_pendentes if p.numero_parcela >= parcela.numero_parcela])
                amortizacao = saldo_devedor / Decimal(str(num_parcelas_restantes))
                # Juros simples fixos
                juros = financiamento.valor_financiado * taxa_mensal

            # Calcular seguro baseado no tipo
            if financiamento.seguro_tipo == 'percentual_saldo':
                valor_seguro = saldo_devedor * financiamento.seguro_percentual
            else:  # fixo
                valor_seguro = financiamento.valor_seguro_mensal

            # Taxa administrativa (valor fixo)
            valor_taxa_adm = financiamento.taxa_administracao_fixa

            # Atualizar parcela
            parcela.valor_amortizacao = amortizacao
            parcela.valor_juros = juros
            parcela.valor_seguro = valor_seguro
            parcela.valor_taxa_adm = valor_taxa_adm
            parcela.valor_previsto_total = amortizacao + juros + valor_seguro + valor_taxa_adm
            parcela.saldo_devedor_apos_pagamento = saldo_devedor - amortizacao

            # Atualizar saldo para próxima iteração
            saldo_devedor = saldo_devedor - amortizacao

        db.session.commit()
        return len(parcelas_pendentes)

    # ========================================================================
    # GERAÇÃO DE PARCELAS
    # ========================================================================

    @staticmethod
    def gerar_parcelas(financiamento):
        """
        Gera tabela de amortização completa usando configurações do próprio financiamento

        Calcula seguro de duas formas:
        - Tipo 'fixo': valor_seguro_mensal constante
        - Tipo 'percentual_saldo': saldo_devedor * seguro_percentual

        Args:
            financiamento (Financiamento): Objeto do financiamento com todas configurações
        """
        # Deletar parcelas existentes
        FinanciamentoParcela.query.filter_by(financiamento_id=financiamento.id).delete()

        sistema = financiamento.sistema_amortizacao

        if sistema == 'SAC':
            FinanciamentoService._gerar_parcelas_sac(financiamento)
        elif sistema == 'PRICE':
            FinanciamentoService._gerar_parcelas_price(financiamento)
        elif sistema == 'SIMPLES':
            FinanciamentoService._gerar_parcelas_simples(financiamento)

        db.session.commit()

        # Criar contas (despesas) para as parcelas
        if financiamento.item_despesa_id:
            FinanciamentoService.sincronizar_contas(financiamento.id)

    @staticmethod
    def _gerar_parcelas_sac(financiamento):
        """
        Sistema de Amortização Constante (SAC)

        Amortização fixa em todas as parcelas
        Juros decrescentes sobre saldo devedor
        Seguro calculado conforme tipo (fixo ou percentual do saldo)
        Aplica TR/indexador se configurado
        """
        valor_financiado = financiamento.valor_financiado
        prazo = financiamento.prazo_total_meses
        taxa_mensal = financiamento.taxa_juros_mensal
        indexador = financiamento.indexador_saldo

        # Amortização constante
        amortizacao = valor_financiado / Decimal(str(prazo))
        saldo_devedor = valor_financiado
        data_vencimento = financiamento.data_primeira_parcela

        for num_parcela in range(1, prazo + 1):
            # Buscar TR/indexador se configurado
            taxa_indexador = Decimal('0')
            if indexador:
                taxa_indexador = FinanciamentoService._obter_indexador(indexador, data_vencimento)

            # Atualizar saldo com indexador
            saldo_corrigido = saldo_devedor * (Decimal('1') + taxa_indexador)

            # Calcular juros sobre saldo corrigido
            juros = saldo_corrigido * taxa_mensal

            # Calcular seguro baseado no tipo
            if financiamento.seguro_tipo == 'percentual_saldo':
                valor_seguro_parcela = saldo_corrigido * financiamento.seguro_percentual
            else:  # fixo
                valor_seguro_parcela = financiamento.valor_seguro_mensal

            # Taxa administrativa (valor fixo mensal)
            valor_taxa_adm = financiamento.taxa_administracao_fixa

            # Compor parcela
            valor_previsto_total = amortizacao + juros + valor_seguro_parcela + valor_taxa_adm

            # Calcular saldo após pagamento
            saldo_apos_pagamento = saldo_corrigido - amortizacao

            # Criar parcela
            parcela = FinanciamentoParcela(
                financiamento_id=financiamento.id,
                numero_parcela=num_parcela,
                data_vencimento=data_vencimento,
                valor_amortizacao=amortizacao,
                valor_juros=juros,
                valor_seguro=valor_seguro_parcela,
                valor_taxa_adm=valor_taxa_adm,
                valor_previsto_total=valor_previsto_total,
                saldo_devedor_apos_pagamento=saldo_apos_pagamento if saldo_apos_pagamento > Decimal('0.01') else Decimal('0'),
                status='pendente'
            )

            db.session.add(parcela)

            # Atualizar para próxima iteração
            saldo_devedor = saldo_apos_pagamento
            data_vencimento = data_vencimento + relativedelta(months=1)

    @staticmethod
    def _gerar_parcelas_price(financiamento):
        """
        Tabela PRICE

        Parcela fixa (amortização + juros)
        Juros decrescentes, amortização crescente
        Seguro calculado conforme tipo (fixo ou percentual do saldo)
        """
        valor_financiado = financiamento.valor_financiado
        prazo = financiamento.prazo_total_meses
        taxa_mensal = financiamento.taxa_juros_mensal

        # Calcular parcela fixa (PMT)
        # PMT = PV * i * (1+i)^n / ((1+i)^n - 1)
        if taxa_mensal == Decimal('0'):
            pmt = valor_financiado / Decimal(str(prazo))
        else:
            fator = (Decimal('1') + taxa_mensal) ** Decimal(str(prazo))
            pmt = valor_financiado * taxa_mensal * fator / (fator - Decimal('1'))

        saldo_devedor = valor_financiado
        data_vencimento = financiamento.data_primeira_parcela

        for num_parcela in range(1, prazo + 1):
            # Juros sobre saldo
            juros = saldo_devedor * taxa_mensal

            # Amortização = PMT - Juros
            amortizacao = pmt - juros

            # Calcular seguro baseado no tipo
            if financiamento.seguro_tipo == 'percentual_saldo':
                valor_seguro_parcela = saldo_devedor * financiamento.seguro_percentual
            else:  # fixo
                valor_seguro_parcela = financiamento.valor_seguro_mensal

            # Taxa administrativa (valor fixo mensal)
            valor_taxa_adm = financiamento.taxa_administracao_fixa

            # Valor total com seguros e taxas
            valor_previsto_total = pmt + valor_seguro_parcela + valor_taxa_adm

            # Saldo após pagamento
            saldo_apos_pagamento = saldo_devedor - amortizacao

            # Criar parcela
            parcela = FinanciamentoParcela(
                financiamento_id=financiamento.id,
                numero_parcela=num_parcela,
                data_vencimento=data_vencimento,
                valor_amortizacao=amortizacao,
                valor_juros=juros,
                valor_seguro=valor_seguro_parcela,
                valor_taxa_adm=valor_taxa_adm,
                valor_previsto_total=valor_previsto_total,
                saldo_devedor_apos_pagamento=saldo_apos_pagamento if saldo_apos_pagamento > Decimal('0.01') else Decimal('0'),
                status='pendente'
            )

            db.session.add(parcela)

            # Atualizar
            saldo_devedor = saldo_apos_pagamento
            data_vencimento = data_vencimento + relativedelta(months=1)

    @staticmethod
    def _gerar_parcelas_simples(financiamento):
        """
        Juros Simples

        Juros fixos sobre valor inicial em todas as parcelas
        Amortização constante
        Seguro calculado conforme tipo (fixo ou percentual do saldo)
        """
        valor_financiado = financiamento.valor_financiado
        prazo = financiamento.prazo_total_meses
        taxa_mensal = financiamento.taxa_juros_mensal

        # Juros fixos por mês
        juros_mensais = valor_financiado * taxa_mensal

        # Amortização constante
        amortizacao = valor_financiado / Decimal(str(prazo))

        saldo_devedor = valor_financiado
        data_vencimento = financiamento.data_primeira_parcela

        for num_parcela in range(1, prazo + 1):
            # Calcular seguro baseado no tipo
            if financiamento.seguro_tipo == 'percentual_saldo':
                valor_seguro_parcela = saldo_devedor * financiamento.seguro_percentual
            else:  # fixo
                valor_seguro_parcela = financiamento.valor_seguro_mensal

            # Taxa administrativa (valor fixo mensal)
            valor_taxa_adm = financiamento.taxa_administracao_fixa

            valor_previsto_total = amortizacao + juros_mensais + valor_seguro_parcela + valor_taxa_adm

            saldo_apos_pagamento = saldo_devedor - amortizacao

            parcela = FinanciamentoParcela(
                financiamento_id=financiamento.id,
                numero_parcela=num_parcela,
                data_vencimento=data_vencimento,
                valor_amortizacao=amortizacao,
                valor_juros=juros_mensais,
                valor_seguro=valor_seguro_parcela,
                valor_taxa_adm=valor_taxa_adm,
                valor_previsto_total=valor_previsto_total,
                saldo_devedor_apos_pagamento=saldo_apos_pagamento if saldo_apos_pagamento > Decimal('0.01') else Decimal('0'),
                status='pendente'
            )

            db.session.add(parcela)

            saldo_devedor = saldo_apos_pagamento
            data_vencimento = data_vencimento + relativedelta(months=1)

    @staticmethod
    def _obter_indexador(nome_indexador, data_referencia):
        """
        Busca valor do indexador para o mês

        Args:
            nome_indexador (str): Nome do indexador (TR, IPCA, etc)
            data_referencia (date): Data de referência

        Returns:
            Decimal: Valor do indexador (0 se não encontrado)
        """
        data_mes = data_referencia.replace(day=1)

        indexador = IndexadorMensal.query.filter_by(
            nome=nome_indexador,
            data_referencia=data_mes
        ).first()

        return indexador.valor if indexador else Decimal('0')

    # ========================================================================
    # REGISTRO DE PAGAMENTOS
    # ========================================================================

    @staticmethod
    def registrar_pagamento_parcela(parcela_id, valor_pago, data_pagamento):
        """
        Registra pagamento de uma parcela

        Args:
            parcela_id (int): ID da parcela
            valor_pago (float): Valor efetivamente pago
            data_pagamento (str ou date): Data do pagamento

        Returns:
            FinanciamentoParcela: Parcela atualizada
        """
        parcela = FinanciamentoParcela.query.get(parcela_id)
        if not parcela:
            raise ValueError('Parcela não encontrada')

        # Converter data se necessário
        if isinstance(data_pagamento, str):
            data_pagamento = datetime.strptime(data_pagamento, '%Y-%m-%d').date()

        # Atualizar valores
        parcela.valor_pago = Decimal(str(valor_pago))
        parcela.data_pagamento = data_pagamento
        parcela.dif_apurada = parcela.valor_previsto_total - parcela.valor_pago
        parcela.status = 'pago'

        db.session.commit()

        # Sincronizar com a Conta correspondente
        financiamento = Financiamento.query.get(parcela.financiamento_id)
        if financiamento and financiamento.item_despesa_id:
            FinanciamentoService.sincronizar_contas(parcela.financiamento_id)

        return parcela

    # ========================================================================
    # AMORTIZAÇÕES EXTRAORDINÁRIAS
    # ========================================================================

    @staticmethod
    def registrar_amortizacao_extra(financiamento_id, dados_amortizacao):
        """
        Registra amortização extraordinária e recalcula parcelas futuras

        Args:
            financiamento_id (int): ID do financiamento
            dados_amortizacao (dict):
                - data (str ou date): Data da amortização
                - valor (float): Valor da amortização
                - tipo (str): 'reduzir_parcela' ou 'reduzir_prazo'
                - observacoes (str, opcional)

        Returns:
            FinanciamentoAmortizacaoExtra: Registro criado
        """
        financiamento = Financiamento.query.get(financiamento_id)
        if not financiamento:
            raise ValueError('Financiamento não encontrado')

        # Converter data
        if isinstance(dados_amortizacao['data'], str):
            data_amort = datetime.strptime(dados_amortizacao['data'], '%Y-%m-%d').date()
        else:
            data_amort = dados_amortizacao['data']

        valor = Decimal(str(dados_amortizacao['valor']))
        tipo = dados_amortizacao['tipo']

        # Criar registro
        amortizacao = FinanciamentoAmortizacaoExtra(
            financiamento_id=financiamento_id,
            data=data_amort,
            valor=valor,
            tipo=tipo,
            observacoes=dados_amortizacao.get('observacoes', '')
        )

        db.session.add(amortizacao)
        db.session.flush()

        # Recalcular parcelas futuras
        FinanciamentoService._recalcular_apos_amortizacao(financiamento, data_amort, valor, tipo)

        db.session.commit()

        # Sincronizar despesas com os novos valores das parcelas
        if financiamento.item_despesa_id:
            FinanciamentoService.sincronizar_contas(financiamento_id)

        return amortizacao

    @staticmethod
    def _recalcular_apos_amortizacao(financiamento, data_amortizacao, valor_amortizado, tipo):
        """
        Recalcula parcelas futuras após amortização extraordinária

        Args:
            financiamento (Financiamento): Objeto do financiamento
            data_amortizacao (date): Data da amortização
            valor_amortizado (Decimal): Valor amortizado
            tipo (str): 'reduzir_parcela' ou 'reduzir_prazo'
        """
        # Buscar última parcela paga ou a primeira pendente após a data
        parcelas_pendentes = FinanciamentoParcela.query.filter(
            FinanciamentoParcela.financiamento_id == financiamento.id,
            FinanciamentoParcela.data_vencimento >= data_amortizacao,
            FinanciamentoParcela.status == 'pendente'
        ).order_by(FinanciamentoParcela.numero_parcela).all()

        if not parcelas_pendentes:
            return

        # Buscar última parcela paga para pegar saldo correto
        ultima_paga = FinanciamentoParcela.query.filter(
            FinanciamentoParcela.financiamento_id == financiamento.id,
            FinanciamentoParcela.status == 'pago'
        ).order_by(FinanciamentoParcela.numero_parcela.desc()).first()

        # Calcular saldo devedor atual (antes da amortização)
        if ultima_paga:
            saldo_atual = ultima_paga.saldo_devedor_apos_pagamento
        else:
            saldo_atual = financiamento.valor_financiado

        # Reduzir saldo com a amortização
        novo_saldo = saldo_atual - valor_amortizado

        if novo_saldo < 0:
            raise ValueError('Valor da amortização maior que o saldo devedor')

        # Taxa de juros mensal
        taxa_anual = financiamento.taxa_juros_nominal_anual / Decimal('100')
        taxa_mensal = (Decimal('1') + taxa_anual) ** (Decimal('1') / Decimal('12')) - Decimal('1')

        if tipo == 'reduzir_prazo':
            FinanciamentoService._recalcular_reduzir_prazo(
                financiamento, parcelas_pendentes, novo_saldo, taxa_mensal
            )
        elif tipo == 'reduzir_parcela':
            FinanciamentoService._recalcular_reduzir_parcela(
                financiamento, parcelas_pendentes, novo_saldo, taxa_mensal
            )

    @staticmethod
    def _recalcular_reduzir_parcela(financiamento, parcelas_pendentes, novo_saldo, taxa_mensal):
        """
        Mantém prazo, reduz valor das parcelas futuras

        Recalcula juros e seguro baseados no novo saldo
        Se seguro for percentual, será recalculado automaticamente
        """
        sistema = financiamento.sistema_amortizacao
        saldo_devedor = novo_saldo

        for parcela in parcelas_pendentes:
            # Calcular juros sobre novo saldo
            juros = saldo_devedor * taxa_mensal

            # Calcular amortização baseada no sistema
            if sistema == 'SAC':
                # Amortização constante = saldo / parcelas restantes
                num_parcelas_restantes = len([p for p in parcelas_pendentes if p.numero_parcela >= parcela.numero_parcela])
                amortizacao = saldo_devedor / Decimal(str(num_parcelas_restantes))
            elif sistema == 'PRICE':
                # Recalcular PMT com novo saldo e parcelas restantes
                n = len([p for p in parcelas_pendentes if p.numero_parcela >= parcela.numero_parcela])
                if taxa_mensal > 0:
                    pmt = saldo_devedor * (taxa_mensal * (1 + taxa_mensal) ** n) / ((1 + taxa_mensal) ** n - 1)
                else:
                    pmt = saldo_devedor / Decimal(str(n))
                amortizacao = pmt - juros
            else:  # SIMPLES
                num_parcelas_restantes = len([p for p in parcelas_pendentes if p.numero_parcela >= parcela.numero_parcela])
                amortizacao = saldo_devedor / Decimal(str(num_parcelas_restantes))

            # Calcular seguro baseado no tipo
            if financiamento.seguro_tipo == 'percentual_saldo':
                valor_seguro = saldo_devedor * financiamento.seguro_percentual
            else:  # fixo
                valor_seguro = financiamento.valor_seguro_mensal

            # Taxa administrativa (mantida)
            valor_taxa_adm = parcela.valor_taxa_adm or Decimal('0')

            # Atualizar parcela
            parcela.valor_amortizacao = amortizacao
            parcela.valor_juros = juros
            parcela.valor_seguro = valor_seguro
            parcela.valor_taxa_adm = valor_taxa_adm
            parcela.valor_previsto_total = amortizacao + juros + valor_seguro + valor_taxa_adm
            parcela.saldo_devedor_antes_pagamento = saldo_devedor
            parcela.saldo_devedor_apos_pagamento = saldo_devedor - amortizacao

            # Atualizar saldo para próxima iteração
            saldo_devedor = saldo_devedor - amortizacao

        db.session.flush()

    @staticmethod
    def _recalcular_reduzir_prazo(financiamento, parcelas_pendentes, novo_saldo, taxa_mensal):
        """
        Reduz número de parcelas, mantém valor das parcelas

        Calcula quantas parcelas podem ser eliminadas
        Recalcula as parcelas restantes com o novo saldo
        """
        sistema = financiamento.sistema_amortizacao

        # Calcular valor da parcela (mantém o valor original de amortização + juros)
        if parcelas_pendentes:
            parcela_referencia = parcelas_pendentes[0]
            valor_amortizacao_original = parcela_referencia.valor_amortizacao
        else:
            return

        # Calcular quantas parcelas podem ser quitadas com o novo saldo
        saldo_devedor = novo_saldo
        parcelas_para_manter = []

        for parcela in parcelas_pendentes:
            # Calcular juros sobre saldo atual
            juros = saldo_devedor * taxa_mensal

            # Usar mesma amortização original
            amortizacao = valor_amortizacao_original

            # Se o saldo é menor que a amortização, essa é a última parcela
            if saldo_devedor <= amortizacao:
                amortizacao = saldo_devedor
                juros = saldo_devedor * taxa_mensal

            # Calcular seguro baseado no tipo
            if financiamento.seguro_tipo == 'percentual_saldo':
                valor_seguro = saldo_devedor * financiamento.seguro_percentual
            else:  # fixo
                valor_seguro = financiamento.valor_seguro_mensal

            # Taxa administrativa (mantida)
            valor_taxa_adm = parcela.valor_taxa_adm or Decimal('0')

            # Atualizar parcela
            parcela.valor_amortizacao = amortizacao
            parcela.valor_juros = juros
            parcela.valor_seguro = valor_seguro
            parcela.valor_taxa_adm = valor_taxa_adm
            parcela.valor_previsto_total = amortizacao + juros + valor_seguro + valor_taxa_adm
            parcela.saldo_devedor_antes_pagamento = saldo_devedor
            parcela.saldo_devedor_apos_pagamento = saldo_devedor - amortizacao

            parcelas_para_manter.append(parcela)

            # Atualizar saldo
            saldo_devedor = saldo_devedor - amortizacao

            # Se quitou tudo, para
            if saldo_devedor <= Decimal('0.01'):
                break

        # Deletar parcelas excedentes
        parcelas_para_deletar = [p for p in parcelas_pendentes if p not in parcelas_para_manter]
        for parcela in parcelas_para_deletar:
            db.session.delete(parcela)

        # Atualizar prazo remanescente no financiamento
        financiamento.prazo_remanescente_meses = len(parcelas_para_manter)

        db.session.flush()

    # ========================================================================
    # RELATÓRIOS E DEMONSTRATIVOS
    # ========================================================================

    @staticmethod
    def get_demonstrativo_anual(financiamento_id, ano):
        """
        Gera demonstrativo anual similar ao da CAIXA

        Args:
            financiamento_id (int): ID do financiamento
            ano (int): Ano

        Returns:
            dict: Demonstrativo consolidado
        """
        financiamento = Financiamento.query.get(financiamento_id)
        if not financiamento:
            raise ValueError('Financiamento não encontrado')

        data_inicio = date(ano, 1, 1)
        data_fim = date(ano, 12, 31)

        parcelas = FinanciamentoParcela.query.filter(
            FinanciamentoParcela.financiamento_id == financiamento_id,
            FinanciamentoParcela.data_vencimento >= data_inicio,
            FinanciamentoParcela.data_vencimento <= data_fim
        ).order_by(FinanciamentoParcela.data_vencimento).all()

        # Agrupar por mês
        resumo_mensal = {}
        for parcela in parcelas:
            mes = parcela.data_vencimento.month
            if mes not in resumo_mensal:
                resumo_mensal[mes] = {
                    'amortizacao': Decimal('0'),
                    'juros': Decimal('0'),
                    'seguro': Decimal('0'),
                    'taxa_adm': Decimal('0'),
                    'total_previsto': Decimal('0'),
                    'total_pago': Decimal('0')
                }

            resumo_mensal[mes]['amortizacao'] += parcela.valor_amortizacao
            resumo_mensal[mes]['juros'] += parcela.valor_juros
            resumo_mensal[mes]['seguro'] += parcela.valor_seguro
            resumo_mensal[mes]['taxa_adm'] += parcela.valor_taxa_adm
            resumo_mensal[mes]['total_previsto'] += parcela.valor_previsto_total
            resumo_mensal[mes]['total_pago'] += parcela.valor_pago

        return {
            'financiamento': financiamento.to_dict(),
            'ano': ano,
            'resumo_mensal': {mes: {k: float(v) for k, v in dados.items()} for mes, dados in resumo_mensal.items()}
        }

    @staticmethod
    def sincronizar_contas(financiamento_id):
        """
        Cria/atualiza contas (despesas) a partir das parcelas do financiamento

        Similar ao comportamento de consórcios, cria uma Conta para cada
        FinanciamentoParcela para que apareçam na listagem de despesas

        Args:
            financiamento_id (int): ID do financiamento
        """
        from datetime import datetime
        from dateutil.relativedelta import relativedelta

        financiamento = Financiamento.query.get(financiamento_id)
        if not financiamento:
            raise ValueError('Financiamento não encontrado')

        if not financiamento.item_despesa_id:
            # Se não tem item_despesa vinculado, não criar contas
            return

        # Buscar todas as parcelas
        parcelas = FinanciamentoParcela.query.filter_by(
            financiamento_id=financiamento_id
        ).order_by(FinanciamentoParcela.numero_parcela).all()

        for parcela in parcelas:
            # Verificar se já existe uma Conta para esta parcela
            conta_existente = Conta.query.filter(
                Conta.item_despesa_id == financiamento.item_despesa_id,
                Conta.descricao.like(f'%{financiamento.nome}%Parcela {parcela.numero_parcela}/%')
            ).first()

            # Calcular mês de referência (mesma lógica do consórcio)
            mes_referencia = parcela.data_vencimento.replace(day=1)

            if conta_existente:
                # Atualizar conta existente
                conta_existente.valor = parcela.valor_previsto_total
                conta_existente.data_vencimento = parcela.data_vencimento
                conta_existente.mes_referencia = mes_referencia

                # Sincronizar status de pagamento
                if parcela.status == 'pago' and not conta_existente.data_pagamento:
                    conta_existente.status_pagamento = 'Pago'
                    conta_existente.data_pagamento = parcela.data_pagamento or parcela.data_vencimento
                elif parcela.status == 'pendente':
                    conta_existente.status_pagamento = 'Pendente'
                    conta_existente.data_pagamento = None
            else:
                # Criar nova conta
                nova_conta = Conta(
                    item_despesa_id=financiamento.item_despesa_id,
                    mes_referencia=mes_referencia,
                    descricao=f'{financiamento.nome} - Parcela {parcela.numero_parcela}/{financiamento.prazo_total_meses}',
                    valor=parcela.valor_previsto_total,
                    data_vencimento=parcela.data_vencimento,
                    data_pagamento=parcela.data_pagamento if parcela.status == 'pago' else None,
                    status_pagamento='Pago' if parcela.status == 'pago' else 'Pendente',
                    numero_parcela=parcela.numero_parcela,
                    total_parcelas=financiamento.prazo_total_meses,
                    observacoes=f'Financiamento {financiamento.sistema_amortizacao} - ' +
                               f'Amortização: R$ {float(parcela.valor_amortizacao):.2f}, ' +
                               f'Juros: R$ {float(parcela.valor_juros):.2f}'
                )
                db.session.add(nova_conta)

        db.session.commit()

    @staticmethod
    def get_evolucao_saldo(financiamento_id):
        """
        Retorna evolução do saldo devedor

        Args:
            financiamento_id (int): ID do financiamento

        Returns:
            dict: Evolução do saldo
        """
        parcelas = FinanciamentoParcela.query.filter_by(
            financiamento_id=financiamento_id
        ).order_by(FinanciamentoParcela.numero_parcela).all()

        evolucao = []
        for parcela in parcelas:
            evolucao.append({
                'numero_parcela': parcela.numero_parcela,
                'data_vencimento': parcela.data_vencimento.strftime('%Y-%m-%d'),
                'saldo_devedor': float(parcela.saldo_devedor_apos_pagamento) if parcela.saldo_devedor_apos_pagamento else 0,
                'status': parcela.status
            })

        return evolucao
