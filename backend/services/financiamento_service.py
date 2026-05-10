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
from decimal import Decimal, ROUND_HALF_UP
import math
import logging

try:
    from backend.models import (db, Financiamento, FinanciamentoParcela,
                                FinanciamentoAmortizacaoExtra, IndexadorMensal, Conta,
                                FinanciamentoSeguroFaixaMip, FinanciamentoAjusteSaldo)
    from backend.services.perfil_financeiro_service import PerfilFinanceiroService
except ImportError:
    from models import (db, Financiamento, FinanciamentoParcela,
                       FinanciamentoAmortizacaoExtra, IndexadorMensal, Conta,
                       FinanciamentoSeguroFaixaMip, FinanciamentoAjusteSaldo)
    from services.perfil_financeiro_service import PerfilFinanceiroService

logger = logging.getLogger(__name__)


class FinanciamentoService:
    """
    Serviço para gerenciamento completo de financiamentos
    """

    STATUS_PARCELA_EXECUTADA = {
        'pago', 'paga',
        'baixado', 'baixada',
        'realizado', 'realizada',
        'conciliado', 'conciliada',
        'amortizado', 'amortizada',
    }

    STATUS_CONTA_EXECUTADA = {
        'pago', 'paga',
        'baixado', 'baixada',
        'realizado', 'realizada',
        'conciliado', 'conciliada',
    }

    SEGURO_MODO_FIXO = 'fixo'
    SEGURO_MODO_ESTIMADO_DFI_MIP = 'estimado_dfi_mip'
    SEGURO_FATOR_DFI_PADRAO = Decimal('0.0489')
    FAIXAS_MIP_PADRAO = [
        {'idade_inicio': 0, 'idade_fim': 45, 'fator_mip': Decimal('0.03187')},
        {'idade_inicio': 46, 'idade_fim': 50, 'fator_mip': Decimal('0.04899')},
        {'idade_inicio': 51, 'idade_fim': 55, 'fator_mip': Decimal('0.08593')},
        {'idade_inicio': 56, 'idade_fim': 60, 'fator_mip': Decimal('0.16077')},
        {'idade_inicio': 61, 'idade_fim': 65, 'fator_mip': Decimal('0.31887')},
        {'idade_inicio': 66, 'idade_fim': 70, 'fator_mip': Decimal('0.34932')},
        {'idade_inicio': 71, 'idade_fim': 75, 'fator_mip': Decimal('0.49795')},
        {'idade_inicio': 76, 'idade_fim': 80, 'fator_mip': Decimal('0.57099')},
    ]

    # ========================================================================
    # CRUD DE FINANCIAMENTOS
    # ========================================================================

    @staticmethod
    def _perfil_id():
        return PerfilFinanceiroService.obter_perfil_ativo_id()

    @staticmethod
    def _query_financiamentos():
        return PerfilFinanceiroService.aplicar_perfil_query(Financiamento.query, Financiamento)

    @staticmethod
    def obter_financiamento_no_perfil(financiamento_id):
        financiamento = FinanciamentoService._query_financiamentos().filter(Financiamento.id == financiamento_id).first()
        if not financiamento:
            raise ValueError('Financiamento não encontrado')
        return financiamento

    @staticmethod
    def _seguro_modo(financiamento):
        return getattr(financiamento, 'seguro_modo', None) or FinanciamentoService.SEGURO_MODO_FIXO

    @staticmethod
    def _decimal(valor, campo, permitir_nulo=False):
        if valor is None or valor == '':
            if permitir_nulo:
                return None
            raise ValueError(f'{campo} é obrigatório')
        try:
            return Decimal(str(valor).replace(',', '.'))
        except Exception as exc:
            raise ValueError(f'{campo} deve ser numérico') from exc

    @staticmethod
    def _inteiro(valor, campo, permitir_nulo=False):
        if valor is None or valor == '':
            if permitir_nulo:
                return None
            raise ValueError(f'{campo} é obrigatório')
        try:
            return int(valor)
        except (TypeError, ValueError) as exc:
            raise ValueError(f'{campo} deve ser inteiro') from exc

    @staticmethod
    def _calcular_idade_seguro(data_nascimento, data_vencimento, mes_reajuste_idade=None):
        if not data_nascimento:
            raise ValueError('Data de nascimento do titular é obrigatória para seguro estimado')

        mes_reajuste = int(mes_reajuste_idade or data_nascimento.month)
        if mes_reajuste < 1 or mes_reajuste > 12:
            raise ValueError('seguro_mes_reajuste_idade deve estar entre 1 e 12')

        dia_reajuste = 1 if mes_reajuste_idade else data_nascimento.day
        try:
            data_reajuste = date(data_vencimento.year, mes_reajuste, dia_reajuste)
        except ValueError:
            data_reajuste = date(data_vencimento.year, mes_reajuste, 1)

        idade = data_vencimento.year - data_nascimento.year
        if data_vencimento < data_reajuste:
            idade -= 1
        return max(idade, 0)

    @staticmethod
    def _obter_faixa_mip(financiamento, idade, data_vencimento):
        return FinanciamentoSeguroFaixaMip.query.filter(
            FinanciamentoSeguroFaixaMip.financiamento_id == financiamento.id,
            FinanciamentoSeguroFaixaMip.ativo == True,
            FinanciamentoSeguroFaixaMip.idade_inicio <= idade,
            FinanciamentoSeguroFaixaMip.idade_fim >= idade,
            db.or_(
                FinanciamentoSeguroFaixaMip.vigencia_inicio == None,
                FinanciamentoSeguroFaixaMip.vigencia_inicio <= data_vencimento
            ),
            db.or_(
                FinanciamentoSeguroFaixaMip.vigencia_fim == None,
                FinanciamentoSeguroFaixaMip.vigencia_fim >= data_vencimento
            )
        ).order_by(
            FinanciamentoSeguroFaixaMip.vigencia_inicio.desc(),
            FinanciamentoSeguroFaixaMip.idade_inicio
        ).first()

    @staticmethod
    def _normalizar_faixas_mip(faixas):
        if faixas is None:
            return []
        if not isinstance(faixas, list):
            raise ValueError('faixas_mip deve ser uma lista')

        normalizadas = []
        for indice, faixa in enumerate(faixas, 1):
            idade_inicio = FinanciamentoService._inteiro(faixa.get('idade_inicio'), f'faixas_mip[{indice}].idade_inicio')
            idade_fim = FinanciamentoService._inteiro(faixa.get('idade_fim'), f'faixas_mip[{indice}].idade_fim')
            fator_mip = FinanciamentoService._decimal(faixa.get('fator_mip'), f'faixas_mip[{indice}].fator_mip')

            if idade_inicio < 0 or idade_fim < idade_inicio:
                raise ValueError(f'Faixa MIP {indice} possui intervalo de idade inválido')
            if fator_mip < 0:
                raise ValueError(f'Faixa MIP {indice} possui fator_mip negativo')

            normalizadas.append({
                'idade_inicio': idade_inicio,
                'idade_fim': idade_fim,
                'fator_mip': fator_mip,
                'vigencia_inicio': FinanciamentoService._converter_data_iso(
                    faixa.get('vigencia_inicio'),
                    f'faixas_mip[{indice}].vigencia_inicio'
                ) if faixa.get('vigencia_inicio') else None,
                'vigencia_fim': FinanciamentoService._converter_data_iso(
                    faixa.get('vigencia_fim'),
                    f'faixas_mip[{indice}].vigencia_fim'
                ) if faixa.get('vigencia_fim') else None,
                'ativo': faixa.get('ativo', True) is not False,
            })

        return normalizadas

    @staticmethod
    def _substituir_faixas_mip(financiamento, faixas):
        FinanciamentoSeguroFaixaMip.query.filter_by(
            financiamento_id=financiamento.id
        ).delete(synchronize_session=False)

        for faixa in faixas:
            db.session.add(FinanciamentoSeguroFaixaMip(
                perfil_financeiro_id=financiamento.perfil_financeiro_id,
                financiamento_id=financiamento.id,
                idade_inicio=faixa['idade_inicio'],
                idade_fim=faixa['idade_fim'],
                fator_mip=faixa['fator_mip'],
                vigencia_inicio=faixa.get('vigencia_inicio'),
                vigencia_fim=faixa.get('vigencia_fim'),
                ativo=faixa.get('ativo', True),
            ))
        db.session.flush()

    @staticmethod
    def _garantir_faixas_mip_padrao(financiamento):
        if FinanciamentoSeguroFaixaMip.query.filter_by(financiamento_id=financiamento.id).count() > 0:
            return
        FinanciamentoService._substituir_faixas_mip(
            financiamento,
            [dict(faixa) for faixa in FinanciamentoService.FAIXAS_MIP_PADRAO]
        )

    @staticmethod
    def calcular_seguro_habitacional(financiamento, data_vencimento, amortizacao_base, juros_contratuais):
        """
        Calcula o seguro habitacional com uma unica regra central.
        """
        modo = FinanciamentoService._seguro_modo(financiamento)

        if modo == FinanciamentoService.SEGURO_MODO_ESTIMADO_DFI_MIP:
            fator_dfi = financiamento.seguro_fator_dfi
            if fator_dfi is None:
                raise ValueError('seguro_fator_dfi é obrigatório no modo estimado DFI + MIP')

            idade = FinanciamentoService._calcular_idade_seguro(
                financiamento.seguro_data_nascimento_titular,
                data_vencimento,
                financiamento.seguro_mes_reajuste_idade
            )
            faixa_mip = FinanciamentoService._obter_faixa_mip(financiamento, idade, data_vencimento)
            if not faixa_mip:
                raise ValueError(
                    f'Nenhuma faixa MIP encontrada para idade {idade} na data {data_vencimento.strftime("%Y-%m-%d")}.'
                )

            dfi = Decimal(str(amortizacao_base or 0)) * Decimal(str(fator_dfi))
            mip = Decimal(str(juros_contratuais or 0)) * Decimal(str(faixa_mip.fator_mip))
            return (dfi + mip).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        if modo != FinanciamentoService.SEGURO_MODO_FIXO:
            raise ValueError('seguro_modo deve ser "fixo" ou "estimado_dfi_mip"')

        vigencia_seguro = financiamento.obter_seguro_por_data(data_vencimento)
        if not vigencia_seguro:
            raise ValueError(
                f"Seguro não configurado para a data {data_vencimento.strftime('%d/%m/%Y')}. "
                f"Cadastre uma vigência de seguro antes de gerar as parcelas."
            )
        return vigencia_seguro.valor_mensal

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

        seguro_modo = dados.get('seguro_modo') or FinanciamentoService.SEGURO_MODO_FIXO
        if seguro_modo not in [
            FinanciamentoService.SEGURO_MODO_FIXO,
            FinanciamentoService.SEGURO_MODO_ESTIMADO_DFI_MIP
        ]:
            raise ValueError('seguro_modo deve ser "fixo" ou "estimado_dfi_mip"')

        seguro_fator_dfi = FinanciamentoService._decimal(
            dados.get('seguro_fator_dfi') if dados.get('seguro_fator_dfi') is not None else (
                FinanciamentoService.SEGURO_FATOR_DFI_PADRAO
                if seguro_modo == FinanciamentoService.SEGURO_MODO_ESTIMADO_DFI_MIP
                else None
            ),
            'seguro_fator_dfi',
            permitir_nulo=(seguro_modo == FinanciamentoService.SEGURO_MODO_FIXO)
        )
        if seguro_fator_dfi is not None and seguro_fator_dfi < 0:
            raise ValueError('seguro_fator_dfi não pode ser negativo')

        seguro_data_nascimento_titular = None
        if dados.get('seguro_data_nascimento_titular'):
            seguro_data_nascimento_titular = FinanciamentoService._converter_data_iso(
                dados['seguro_data_nascimento_titular'],
                'seguro_data_nascimento_titular'
            )
        elif seguro_modo == FinanciamentoService.SEGURO_MODO_ESTIMADO_DFI_MIP:
            raise ValueError('seguro_data_nascimento_titular é obrigatória no modo estimado DFI + MIP')

        seguro_mes_reajuste_idade = FinanciamentoService._inteiro(
            dados.get('seguro_mes_reajuste_idade', 2),
            'seguro_mes_reajuste_idade',
            permitir_nulo=True
        ) or 2
        if seguro_mes_reajuste_idade < 1 or seguro_mes_reajuste_idade > 12:
            raise ValueError('seguro_mes_reajuste_idade deve estar entre 1 e 12')

        # Se não foi fornecido item_despesa_id, criar automaticamente
        # Conforme CONTRATO: 1 parcela = 1 Conta = 1 linha em DESPESAS
        item_despesa_id = dados.get('item_despesa_id')
        if not item_despesa_id:
            from backend.models import ItemDespesa
            item_despesa = ItemDespesa(
                perfil_financeiro_id=FinanciamentoService._perfil_id(),
                nome=dados['nome'],
                tipo='Financiamento',
                ativo=True,
                valor=0,  # Valor será da parcela individual
                recorrente=False
            )
            db.session.add(item_despesa)
            db.session.flush()
            item_despesa_id = item_despesa.id

        # Criar financiamento
        financiamento = Financiamento(
            perfil_financeiro_id=FinanciamentoService._perfil_id(),
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
            item_despesa_id=item_despesa_id,
            # Configuração de seguro
            seguro_tipo=dados.get('seguro_tipo', 'fixo'),
            seguro_percentual=Decimal(str(dados.get('seguro_percentual', 0.0006))),
            valor_seguro_mensal=Decimal(str(dados.get('valor_seguro_mensal', 0))),
            seguro_modo=seguro_modo,
            seguro_fator_dfi=seguro_fator_dfi,
            seguro_data_nascimento_titular=seguro_data_nascimento_titular,
            seguro_mes_reajuste_idade=seguro_mes_reajuste_idade,
            # Taxa de administração
            taxa_administracao_fixa=Decimal(str(dados.get('taxa_administracao_fixa', 0))),
            ativo=True
        )

        db.session.add(financiamento)
        db.session.flush()  # Para obter o ID

        # ========================================================================
        # Inicializar ESTADO SOBERANO
        # ========================================================================
        financiamento.saldo_devedor_atual = financiamento.valor_financiado
        financiamento.numero_parcela_base = 0
        financiamento.data_base = data_primeira_parcela

        # Calcular amortização mensal inicial (SAC)
        if financiamento.sistema_amortizacao == 'SAC':
            financiamento.amortizacao_mensal_atual = financiamento.valor_financiado / Decimal(str(financiamento.prazo_total_meses))

        financiamento.regime_pos_amortizacao = None  # Ainda não houve amortização
        db.session.flush()

        # Criar vigências de seguro (se fornecidas)
        vigencias_seguro = dados.get('vigencias_seguro', [])
        if vigencias_seguro:
            from backend.services.seguro_vigencia_service import SeguroVigenciaService

            # Ordenar vigências por competencia_inicio para criar na ordem cronológica
            vigencias_ordenadas = sorted(
                vigencias_seguro,
                key=lambda v: v['competencia_inicio']
            )

            for idx, vigencia_data in enumerate(vigencias_ordenadas):
                # Converter string de data para objeto date (aceita múltiplos formatos)
                competencia_inicio = vigencia_data['competencia_inicio']
                if isinstance(competencia_inicio, str):
                    competencia_inicio_str = vigencia_data['competencia_inicio']

                    # Limpar e normalizar a string de data
                    # Se veio YYYY-MM-DD, manter apenas YYYY-MM
                    if '-' in competencia_inicio_str and len(competencia_inicio_str) > 7:
                        parts = competencia_inicio_str.split('-')
                        competencia_inicio_str = f"{parts[0]}-{parts[1]}"  # YYYY-MM

                    competencia_inicio = None

                    # Tentar formato YYYY-MM (input type="month")
                    if len(competencia_inicio_str) == 7 and competencia_inicio_str[4] == '-':
                        try:
                            competencia_inicio = datetime.strptime(competencia_inicio_str + '-01', '%Y-%m-%d').date()
                        except ValueError:
                            logger.debug('Formato YYYY-MM invalido para competencia_inicio=%s', competencia_inicio_str)

                    # Tentar formato MM/YYYY
                    if not competencia_inicio and '/' in competencia_inicio_str:
                        partes = competencia_inicio_str.split('/')
                        if len(partes) == 2:
                            try:
                                mes, ano = partes
                                competencia_inicio = datetime(int(ano), int(mes), 1).date()
                            except (ValueError, IndexError):
                                logger.debug('Formato MM/YYYY invalido para competencia_inicio=%s', competencia_inicio_str)

                    # Tentar formato DD/MM/YYYY
                    if not competencia_inicio and '/' in competencia_inicio_str:
                        try:
                            competencia_inicio = datetime.strptime(competencia_inicio_str, '%d/%m/%Y').date()
                            competencia_inicio = competencia_inicio.replace(day=1)
                        except ValueError:
                            logger.debug('Formato DD/MM/YYYY invalido para competencia_inicio=%s', competencia_inicio_str)

                    # Tentar formato YYYY-MM-DD (ISO)
                    if not competencia_inicio:
                        try:
                            competencia_inicio = datetime.strptime(competencia_inicio_str, '%Y-%m-%d').date()
                            competencia_inicio = competencia_inicio.replace(day=1)
                        except ValueError:
                            logger.debug('Formato YYYY-MM-DD invalido para competencia_inicio=%s', competencia_inicio_str)

                    if not competencia_inicio:
                        raise ValueError(
                            f'Formato de data inválido para competencia_inicio: {vigencia_data["competencia_inicio"]}. '
                            f'Use YYYY-MM, MM/YYYY, YYYY-MM-DD ou DD/MM/YYYY'
                        )

                    # Normalizar para o primeiro dia do mês
                    competencia_inicio = competencia_inicio.replace(day=1)

                # Se não é a primeira vigência, encerrar a anterior
                if idx > 0:
                    SeguroVigenciaService._encerrar_vigencia_anterior(
                        financiamento_id=financiamento.id,
                        nova_competencia_inicio=competencia_inicio
                    )

                SeguroVigenciaService.criar_vigencia(
                    financiamento_id=financiamento.id,
                    competencia_inicio=competencia_inicio,
                    valor_mensal=Decimal(str(vigencia_data['valor_mensal'])),
                    saldo_devedor_vigencia=financiamento.saldo_devedor_atual,
                    observacoes=vigencia_data.get('observacoes')
                )

            # CRÍTICO: Flush para persistir vigências ANTES de gerar parcelas
            # Isso garante que obter_seguro_por_data() encontre as vigências
            db.session.flush()

        if seguro_modo == FinanciamentoService.SEGURO_MODO_ESTIMADO_DFI_MIP:
            faixas_mip = FinanciamentoService._normalizar_faixas_mip(dados.get('faixas_mip'))
            if faixas_mip:
                FinanciamentoService._substituir_faixas_mip(financiamento, faixas_mip)
            else:
                FinanciamentoService._garantir_faixas_mip_padrao(financiamento)

        # Gerar parcelas (agora usa configurações do próprio financiamento + vigências criadas)
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
    def financiamento_tem_historico_alterado(financiamento_id):
        """
        Verifica se o financiamento possui histórico alterado (imutável)

        Retorna True se:
        - Existe parcela paga OU
        - Existe amortização extraordinária

        Quando True, recálculo estrutural é PROIBIDO para preservar histórico.

        Args:
            financiamento_id (int): ID do financiamento

        Returns:
            bool: True se há histórico alterado, False caso contrário
        """
        return FinanciamentoService.financiamento_possui_execucao_financeira(financiamento_id)

    @staticmethod
    def financiamento_possui_execucao_financeira(financiamento_id):
        """
        Verifica se existe qualquer evidência de execução financeira.

        Quando retorna True, dados estruturais e regeneração completa do
        cronograma devem ser bloqueados para preservar histórico.
        """
        parcela_executada = FinanciamentoParcela.query.filter(
            FinanciamentoParcela.financiamento_id == financiamento_id,
            func.lower(FinanciamentoParcela.status).in_(tuple(FinanciamentoService.STATUS_PARCELA_EXECUTADA))
        ).first()
        if parcela_executada:
            return True

        conta_executada = Conta.query.join(
            FinanciamentoParcela,
            Conta.financiamento_parcela_id == FinanciamentoParcela.id
        ).filter(
            FinanciamentoParcela.financiamento_id == financiamento_id,
            db.or_(
                func.lower(Conta.status_pagamento).in_(tuple(FinanciamentoService.STATUS_CONTA_EXECUTADA)),
                Conta.data_pagamento.isnot(None)
            )
        ).first()
        if conta_executada:
            return True

        amortizacao = FinanciamentoAmortizacaoExtra.query.filter_by(
            financiamento_id=financiamento_id
        ).first()
        if amortizacao:
            return True

        try:
            from backend.models import MovimentoFinanceiro
        except ImportError:
            from models import MovimentoFinanceiro

        movimento = db.session.query(MovimentoFinanceiro.id).join(
            Conta,
            MovimentoFinanceiro.conta_id == Conta.id
        ).join(
            FinanciamentoParcela,
            Conta.financiamento_parcela_id == FinanciamentoParcela.id
        ).filter(
            FinanciamentoParcela.financiamento_id == financiamento_id
        ).first()

        return movimento is not None

    @staticmethod
    def validar_cronograma_regeneravel(financiamento_id):
        if FinanciamentoService.financiamento_possui_execucao_financeira(financiamento_id):
            raise ValueError(
                'Não é possível alterar dados estruturais do financiamento porque já existem '
                'parcelas pagas ou vinculadas a pagamentos.'
            )

    @staticmethod
    def _remover_cronograma_sem_execucao(financiamento_id):
        """
        Remove parcelas e contas de um cronograma ainda sem execução financeira.

        Conta e FinanciamentoParcela têm FKs nos dois sentidos. Por isso, antes
        de apagar as contas antigas, é necessário soltar o ponteiro conta_id das
        parcelas para evitar violação de chave estrangeira no PostgreSQL.
        """
        FinanciamentoService.validar_cronograma_regeneravel(financiamento_id)

        ids_parcelas = [
            parcela_id for (parcela_id,) in db.session.query(FinanciamentoParcela.id)
            .filter(FinanciamentoParcela.financiamento_id == financiamento_id)
            .all()
        ]

        if not ids_parcelas:
            return

        FinanciamentoParcela.query.filter(
            FinanciamentoParcela.id.in_(ids_parcelas)
        ).update(
            {FinanciamentoParcela.conta_id: None},
            synchronize_session=False
        )
        db.session.flush()

        Conta.query.filter(
            Conta.financiamento_parcela_id.in_(ids_parcelas)
        ).delete(synchronize_session=False)
        db.session.flush()

        FinanciamentoParcela.query.filter(
            FinanciamentoParcela.id.in_(ids_parcelas)
        ).delete(synchronize_session=False)
        db.session.flush()

    @staticmethod
    def _converter_data_iso(valor, campo):
        if isinstance(valor, str):
            try:
                return datetime.strptime(valor, '%Y-%m-%d').date()
            except ValueError as exc:
                raise ValueError(f'{campo} deve estar no formato YYYY-MM-DD') from exc
        return valor

    @staticmethod
    def _valor_estrutural_alterado(atual, novo):
        if isinstance(novo, Decimal):
            return Decimal(str(atual or 0)) != novo
        return atual != novo

    @staticmethod
    def _reconfigurar_vigencia_inicial_sem_execucao(financiamento):
        """
        Em reconfiguração sem histórico financeiro, recria uma vigência inicial
        coerente com a nova primeira parcela para permitir regenerar o cronograma.
        """
        if FinanciamentoService._seguro_modo(financiamento) == FinanciamentoService.SEGURO_MODO_ESTIMADO_DFI_MIP:
            return

        try:
            from backend.models import FinanciamentoSeguroVigencia
            from backend.services.seguro_vigencia_service import SeguroVigenciaService
        except ImportError:
            from models import FinanciamentoSeguroVigencia
            from services.seguro_vigencia_service import SeguroVigenciaService

        FinanciamentoSeguroVigencia.query.filter_by(
            financiamento_id=financiamento.id
        ).delete(synchronize_session=False)

        SeguroVigenciaService.criar_vigencia(
            financiamento_id=financiamento.id,
            competencia_inicio=financiamento.data_primeira_parcela.replace(day=1),
            valor_mensal=Decimal(str(financiamento.valor_seguro_mensal or 0)),
            saldo_devedor_vigencia=financiamento.saldo_devedor_atual or financiamento.valor_financiado,
            observacoes='Vigência inicial regenerada na edição do financiamento sem parcelas pagas.'
        )

    @staticmethod
    def listar_financiamentos(ativo=None):
        """
        Lista financiamentos com filtro opcional

        Args:
            ativo (bool, opcional): Filtrar por status ativo

        Returns:
            list[Financiamento]: Lista de financiamentos
        """
        query = FinanciamentoService._query_financiamentos()

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
        financiamento = FinanciamentoService.obter_financiamento_no_perfil(financiamento_id)

        valores_estruturais = {}

        if 'sistema_amortizacao' in dados:
            sistema = dados['sistema_amortizacao']
            if sistema not in ['SAC', 'PRICE', 'SIMPLES']:
                raise ValueError('Sistema de amortização deve ser SAC, PRICE ou SIMPLES')
            valores_estruturais['sistema_amortizacao'] = sistema

        if 'valor_financiado' in dados:
            valor_financiado = Decimal(str(dados['valor_financiado']))
            if valor_financiado <= 0:
                raise ValueError('Valor financiado deve ser maior que zero')
            valores_estruturais['valor_financiado'] = valor_financiado

        if 'prazo_total_meses' in dados:
            prazo = int(dados['prazo_total_meses'])
            if prazo <= 0:
                raise ValueError('Prazo total deve ser maior que zero')
            valores_estruturais['prazo_total_meses'] = prazo

        if 'taxa_juros_nominal_anual' in dados:
            taxa_anual = Decimal(str(dados['taxa_juros_nominal_anual']))
            if taxa_anual < 0:
                raise ValueError('Taxa de juros não pode ser negativa')
            valores_estruturais['taxa_juros_nominal_anual'] = taxa_anual
            valores_estruturais['taxa_juros_mensal'] = FinanciamentoService._calcular_taxa_mensal(taxa_anual)

        if 'indexador_saldo' in dados:
            valores_estruturais['indexador_saldo'] = dados.get('indexador_saldo') or None

        if 'data_contrato' in dados:
            valores_estruturais['data_contrato'] = FinanciamentoService._converter_data_iso(
                dados['data_contrato'],
                'data_contrato'
            )

        if 'data_primeira_parcela' in dados:
            valores_estruturais['data_primeira_parcela'] = FinanciamentoService._converter_data_iso(
                dados['data_primeira_parcela'],
                'data_primeira_parcela'
            )

        if 'seguro_tipo' in dados:
            if dados['seguro_tipo'] not in ['fixo', 'percentual_saldo']:
                raise ValueError('seguro_tipo deve ser "fixo" ou "percentual_saldo"')
            valores_estruturais['seguro_tipo'] = dados['seguro_tipo']

        if 'seguro_percentual' in dados and dados['seguro_percentual'] is not None:
            seguro_percentual = Decimal(str(dados['seguro_percentual']))
            if seguro_percentual < 0:
                raise ValueError('seguro_percentual não pode ser negativo')
            valores_estruturais['seguro_percentual'] = seguro_percentual

        if 'valor_seguro_mensal' in dados:
            valor_seguro = Decimal(str(dados['valor_seguro_mensal']))
            if valor_seguro < 0:
                raise ValueError('valor_seguro_mensal não pode ser negativo')
            valores_estruturais['valor_seguro_mensal'] = valor_seguro

        if 'seguro_modo' in dados:
            seguro_modo = dados.get('seguro_modo') or FinanciamentoService.SEGURO_MODO_FIXO
            if seguro_modo not in [
                FinanciamentoService.SEGURO_MODO_FIXO,
                FinanciamentoService.SEGURO_MODO_ESTIMADO_DFI_MIP
            ]:
                raise ValueError('seguro_modo deve ser "fixo" ou "estimado_dfi_mip"')
            valores_estruturais['seguro_modo'] = seguro_modo

        if 'seguro_fator_dfi' in dados:
            seguro_fator_dfi = FinanciamentoService._decimal(
                dados.get('seguro_fator_dfi'),
                'seguro_fator_dfi',
                permitir_nulo=True
            )
            if seguro_fator_dfi is not None and seguro_fator_dfi < 0:
                raise ValueError('seguro_fator_dfi nao pode ser negativo')
            valores_estruturais['seguro_fator_dfi'] = seguro_fator_dfi

        if 'seguro_data_nascimento_titular' in dados:
            valores_estruturais['seguro_data_nascimento_titular'] = FinanciamentoService._converter_data_iso(
                dados.get('seguro_data_nascimento_titular'),
                'seguro_data_nascimento_titular'
            ) if dados.get('seguro_data_nascimento_titular') else None

        if 'seguro_mes_reajuste_idade' in dados:
            seguro_mes_reajuste_idade = FinanciamentoService._inteiro(
                dados.get('seguro_mes_reajuste_idade'),
                'seguro_mes_reajuste_idade',
                permitir_nulo=True
            ) or 2
            if seguro_mes_reajuste_idade < 1 or seguro_mes_reajuste_idade > 12:
                raise ValueError('seguro_mes_reajuste_idade deve estar entre 1 e 12')
            valores_estruturais['seguro_mes_reajuste_idade'] = seguro_mes_reajuste_idade

        if 'taxa_administracao_fixa' in dados:
            taxa_adm = Decimal(str(dados['taxa_administracao_fixa']))
            if taxa_adm < 0:
                raise ValueError('taxa_administracao_fixa não pode ser negativa')
            valores_estruturais['taxa_administracao_fixa'] = taxa_adm

        faixas_mip = None
        if 'faixas_mip' in dados:
            faixas_mip = FinanciamentoService._normalizar_faixas_mip(dados.get('faixas_mip'))

        modo_resultante = valores_estruturais.get(
            'seguro_modo',
            financiamento.seguro_modo or FinanciamentoService.SEGURO_MODO_FIXO
        )
        if modo_resultante == FinanciamentoService.SEGURO_MODO_ESTIMADO_DFI_MIP:
            if 'seguro_fator_dfi' not in valores_estruturais and financiamento.seguro_fator_dfi is None:
                valores_estruturais['seguro_fator_dfi'] = FinanciamentoService.SEGURO_FATOR_DFI_PADRAO

            data_nascimento_resultante = valores_estruturais.get(
                'seguro_data_nascimento_titular',
                financiamento.seguro_data_nascimento_titular
            )
            if not data_nascimento_resultante:
                raise ValueError('seguro_data_nascimento_titular e obrigatoria no modo estimado DFI + MIP')

        campos_alterados = [
            campo for campo, valor in valores_estruturais.items()
            if campo != 'taxa_juros_mensal'
            and FinanciamentoService._valor_estrutural_alterado(getattr(financiamento, campo), valor)
        ]
        houve_mudanca_faixas = faixas_mip is not None
        houve_mudanca_estrutural = bool(campos_alterados) or houve_mudanca_faixas

        if houve_mudanca_estrutural:
            FinanciamentoService.validar_cronograma_regeneravel(financiamento.id)

        # Atualizar campos não estruturais permitidos
        if 'nome' in dados:
            financiamento.nome = dados['nome']
        if 'produto' in dados:
            financiamento.produto = dados['produto']
        if 'ativo' in dados:
            financiamento.ativo = dados['ativo']
        if 'item_despesa_id' in dados:
            financiamento.item_despesa_id = dados['item_despesa_id']

        for campo, valor in valores_estruturais.items():
            setattr(financiamento, campo, valor)

        if faixas_mip is not None:
            FinanciamentoService._substituir_faixas_mip(financiamento, faixas_mip)
        elif FinanciamentoService._seguro_modo(financiamento) == FinanciamentoService.SEGURO_MODO_ESTIMADO_DFI_MIP:
            FinanciamentoService._garantir_faixas_mip_padrao(financiamento)

        if houve_mudanca_estrutural:
            financiamento.prazo_remanescente_meses = financiamento.prazo_total_meses
            financiamento.saldo_devedor_atual = financiamento.valor_financiado
            financiamento.numero_parcela_base = 0
            financiamento.data_base = financiamento.data_primeira_parcela
            financiamento.regime_pos_amortizacao = None
            financiamento.amortizacao_mensal_atual = None
            if financiamento.sistema_amortizacao == 'SAC':
                financiamento.amortizacao_mensal_atual = (
                    financiamento.valor_financiado / Decimal(str(financiamento.prazo_total_meses))
                )

        # Criar novas vigências de seguro (se fornecidas)
        # IMPORTANTE: Nunca editar vigências existentes, sempre criar novas
        vigencias_seguro = dados.get('vigencias_seguro', [])
        if vigencias_seguro:
            from backend.services.seguro_vigencia_service import SeguroVigenciaService
            from datetime import datetime

            for vigencia_data in vigencias_seguro:
                # Converter string de data para objeto date (aceita múltiplos formatos)
                competencia_inicio = vigencia_data['competencia_inicio']
                if isinstance(competencia_inicio, str):
                    competencia_inicio_str = vigencia_data['competencia_inicio']

                    # Limpar e normalizar a string de data
                    # Remover sufixos como "-01", "-1", etc que vêm do frontend
                    if '-' in competencia_inicio_str and len(competencia_inicio_str) > 7:
                        parts = competencia_inicio_str.split('-')
                        competencia_inicio_str = f"{parts[0]}-{parts[1]}"

                    competencia_inicio = None

                    # Tentar formato YYYY-MM (input type="month")
                    if len(competencia_inicio_str) == 7 and competencia_inicio_str[4] == '-':
                        try:
                            competencia_inicio = datetime.strptime(competencia_inicio_str + '-01', '%Y-%m-%d').date()
                        except ValueError:
                            logger.debug('Formato YYYY-MM invalido para competencia_inicio=%s', competencia_inicio_str)

                    # Tentar formato MM/YYYY (frontend pode enviar assim)
                    if not competencia_inicio and '/' in competencia_inicio_str:
                        partes = competencia_inicio_str.split('/')
                        if len(partes) == 2:
                            try:
                                mes, ano = partes
                                competencia_inicio = datetime(int(ano), int(mes), 1).date()
                            except (ValueError, IndexError):
                                logger.debug('Formato MM/YYYY invalido para competencia_inicio=%s', competencia_inicio_str)

                    # Tentar formato DD/MM/YYYY
                    if not competencia_inicio and '/' in competencia_inicio_str:
                        try:
                            competencia_inicio = datetime.strptime(competencia_inicio_str, '%d/%m/%Y').date()
                            # Normalizar para primeiro dia do mês
                            competencia_inicio = competencia_inicio.replace(day=1)
                        except ValueError:
                            logger.debug('Formato DD/MM/YYYY invalido para competencia_inicio=%s', competencia_inicio_str)

                    # Tentar formato YYYY-MM-DD (ISO)
                    if not competencia_inicio:
                        try:
                            competencia_inicio = datetime.strptime(competencia_inicio_str, '%Y-%m-%d').date()
                            # Normalizar para primeiro dia do mês
                            competencia_inicio = competencia_inicio.replace(day=1)
                        except ValueError:
                            logger.debug('Formato YYYY-MM-DD invalido para competencia_inicio=%s', competencia_inicio_str)

                    if not competencia_inicio:
                        raise ValueError(
                            f'Formato de data inválido para competencia_inicio: {vigencia_data["competencia_inicio"]}. '
                            f'Use YYYY-MM, MM/YYYY, YYYY-MM-DD ou DD/MM/YYYY'
                        )

                SeguroVigenciaService.criar_vigencia(
                    financiamento_id=financiamento.id,
                    competencia_inicio=competencia_inicio,
                    valor_mensal=Decimal(str(vigencia_data['valor_mensal'])),
                    saldo_devedor_vigencia=financiamento.saldo_devedor_atual,
                    observacoes=vigencia_data.get('observacoes')
                )

            # CRÍTICO: Flush para persistir vigências ANTES de commit
            # Isso garante que obter_seguro_por_data() encontre as vigências
            db.session.flush()

        # ========================================================================
        # DECISÃO DE RECÁLCULO: Separar mudanças estruturais de encargos acessórios
        # ========================================================================
        houve_mudanca_seguro = 'vigencias_seguro' in dados and dados['vigencias_seguro']
        parcelas_existentes = FinanciamentoParcela.query.filter_by(
            financiamento_id=financiamento.id
        ).count()
        regenerar_cronograma = dados.get('regenerar_cronograma', True)
        deve_regenerar_cronograma = (
            houve_mudanca_estrutural
            and (regenerar_cronograma or parcelas_existentes > 0)
        )

        db.session.flush()

        if deve_regenerar_cronograma:
            FinanciamentoService._reconfigurar_vigencia_inicial_sem_execucao(financiamento)
            db.session.flush()
            FinanciamentoService.gerar_parcelas(financiamento)
        elif houve_mudanca_seguro:
            # Nova vigência → recálculo seguro-only (não toca em saldo/amortização).
            primeira_vigencia = dados['vigencias_seguro'][0]
            competencia_inicio = primeira_vigencia['competencia_inicio']

            # Converter para date se for string
            if isinstance(competencia_inicio, str):
                from datetime import datetime
                if len(competencia_inicio) == 7:  # YYYY-MM
                    competencia_inicio = datetime.strptime(competencia_inicio + '-01', '%Y-%m-%d').date()
                else:
                    competencia_inicio = datetime.strptime(competencia_inicio, '%Y-%m-%d').date()

            FinanciamentoService.recalcular_seguro_parcelas_futuras(
                financiamento.id,
                a_partir_de=competencia_inicio
            )
        else:
            db.session.commit()

        return financiamento

    @staticmethod
    def inativar_financiamento(financiamento_id):
        """
        Inativa (soft delete) um financiamento

        IMPORTANTE: Remove contas futuras (despesas de parcelas pendentes)
        mas mantém histórico de parcelas pagas.

        Args:
            financiamento_id (int): ID do financiamento

        Returns:
            Financiamento: Financiamento inativado
        """
        financiamento = FinanciamentoService.obter_financiamento_no_perfil(financiamento_id)

        financiamento.ativo = False

        # Remover contas (despesas) de parcelas PENDENTES futuras
        # Manter contas de parcelas pagas (histórico imutável)
        if financiamento.item_despesa_id:
            # Buscar IDs de parcelas pendentes
            parcelas_pendentes = FinanciamentoParcela.query.filter_by(
                financiamento_id=financiamento_id,
                status='pendente'
            ).all()

            parcelas_pendentes_ids = [p.id for p in parcelas_pendentes]

            if parcelas_pendentes_ids:
                FinanciamentoParcela.query.filter(
                    FinanciamentoParcela.id.in_(parcelas_pendentes_ids)
                ).update(
                    {FinanciamentoParcela.conta_id: None},
                    synchronize_session=False
                )
                db.session.flush()

                # Remover contas vinculadas a parcelas pendentes
                Conta.query.filter(
                    Conta.financiamento_parcela_id.in_(parcelas_pendentes_ids)
                ).delete(synchronize_session=False)

        db.session.commit()

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
        return not FinanciamentoService.financiamento_possui_execucao_financeira(financiamento_id)

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
        financiamento = FinanciamentoService.obter_financiamento_no_perfil(financiamento_id)

        if not FinanciamentoService.pode_excluir_financiamento(financiamento_id):
            raise ValueError(
                "Financiamento possui histórico financeiro e não pode ser excluído. "
                "Utilize a opção de inativar."
            )

        try:
            FinanciamentoService._remover_cronograma_sem_execucao(financiamento_id)

            # Excluir despesas vinculadas que tenham ficado sem parcela associada
            if financiamento.item_despesa_id:
                Conta.query.filter(
                    Conta.item_despesa_id == financiamento.item_despesa_id
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
        import logging
        logger = logging.getLogger(__name__)

        logger.info(f"[RECALC] ========== INÍCIO RECÁLCULO FIN_ID={financiamento_id} ==========")

        financiamento = FinanciamentoService.obter_financiamento_no_perfil(financiamento_id)

        # Buscar parcelas pendentes
        parcelas_pendentes = FinanciamentoParcela.query.filter_by(
            financiamento_id=financiamento_id,
            status='pendente'
        ).order_by(FinanciamentoParcela.numero_parcela).all()

        if not parcelas_pendentes:
            return 0  # Nenhuma parcela para recalcular

        # ========================================================================
        # 🔥 CORREÇÃO CRÍTICA: Determinar saldo devedor inicial correto
        #
        # PROBLEMA: Se houver amortização extraordinária APÓS última parcela paga,
        # o saldo da última paga NÃO reflete essa amortização.
        #
        # SOLUÇÃO: Buscar a parcela IMEDIATAMENTE ANTERIOR à primeira pendente,
        # independente do status (paga ou pendente), pois ela já reflete
        # o impacto de amortizações extraordinárias.
        # ========================================================================
        primeira_pendente = parcelas_pendentes[0]
        numero_anterior = primeira_pendente.numero_parcela - 1

        logger.info(f"[RECALC] Primeira pendente: parcela #{primeira_pendente.numero_parcela}, vencimento={primeira_pendente.data_vencimento}")
        logger.info(f"[RECALC] Buscando parcela anterior: #{numero_anterior}")

        # Se primeira pendente é a parcela 1, usar valor financiado
        if numero_anterior == 0:
            saldo_devedor = financiamento.valor_financiado
            logger.info(f"[RECALC] Parcela anterior é 0, usando valor_financiado: R$ {saldo_devedor}")
        else:
            # Buscar parcela anterior (independente do status)
            parcela_anterior = FinanciamentoParcela.query.filter_by(
                financiamento_id=financiamento_id,
                numero_parcela=numero_anterior
            ).first()

            if parcela_anterior:
                # Usar saldo da parcela anterior (já reflete amortizações extras)
                saldo_devedor = parcela_anterior.saldo_devedor_apos_pagamento
                logger.info(f"[RECALC] Parcela anterior encontrada: #{parcela_anterior.numero_parcela}, status={parcela_anterior.status}")
                logger.info(f"[RECALC] Saldo da parcela anterior: R$ {saldo_devedor}")
            else:
                # Fallback: usar valor financiado
                saldo_devedor = financiamento.valor_financiado
                logger.warning(f"[RECALC] Parcela anterior NÃO encontrada! Usando valor_financiado: R$ {saldo_devedor}")

        logger.info(f"[RECALC] SALDO_BASE PARA RECÁLCULO: R$ {saldo_devedor}")

        # Taxa de juros mensal
        taxa_mensal = financiamento.taxa_juros_mensal
        sistema = financiamento.sistema_amortizacao

        logger.info(f"[RECALC] Taxa mensal: {taxa_mensal} (já em decimal)")
        logger.info(f"[RECALC] Sistema: {sistema}")
        logger.info(f"[RECALC] Total de parcelas pendentes: {len(parcelas_pendentes)}")

        # Recalcular cada parcela pendente
        for idx, parcela in enumerate(parcelas_pendentes, 1):
            logger.info(f"[RECALC] --- Recalculando parcela #{parcela.numero_parcela} ({idx}/{len(parcelas_pendentes)}) ---")
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

            valor_seguro = FinanciamentoService.calcular_seguro_habitacional(
                financiamento,
                parcela.data_vencimento,
                amortizacao,
                juros
            )
            logger.info(f"[RECALC] Seguro calculado para {parcela.data_vencimento}: R$ {valor_seguro}")

            # Taxa administrativa (valor fixo)
            valor_taxa_adm = financiamento.taxa_administracao_fixa

            # Atualizar parcela
            parcela.valor_amortizacao = amortizacao
            parcela.valor_juros = juros
            parcela.valor_seguro = valor_seguro
            parcela.valor_taxa_adm = valor_taxa_adm
            parcela.valor_previsto_total = amortizacao + juros + valor_seguro + valor_taxa_adm
            parcela.saldo_devedor_apos_pagamento = saldo_devedor - amortizacao  # ✅ REENCADEAMENTO CORRETO

            logger.info(f"[RECALC] Saldo atual: R$ {saldo_devedor}")
            logger.info(f"[RECALC] Juros: R$ {juros}")
            logger.info(f"[RECALC] Amortização: R$ {amortizacao}")
            logger.info(f"[RECALC] Seguro: R$ {valor_seguro}")
            logger.info(f"[RECALC] Taxa ADM: R$ {valor_taxa_adm}")
            logger.info(f"[RECALC] TOTAL: R$ {parcela.valor_previsto_total}")
            logger.info(f"[RECALC] Saldo após: R$ {parcela.saldo_devedor_apos_pagamento}")

            # Atualizar saldo para próxima iteração (✅ REENCADEAMENTO)
            saldo_devedor = saldo_devedor - amortizacao

        db.session.commit()
        logger.info(f"[RECALC] ========== FIM RECÁLCULO - {len(parcelas_pendentes)} parcelas atualizadas ==========")
        return len(parcelas_pendentes)

    @staticmethod
    def recalcular_seguro_parcelas_futuras(financiamento_id, a_partir_de=None):
        """
        Recálculo SEGURO-ONLY - NÃO toca em amortização, juros ou saldo devedor.

        Este método é usado quando SOMENTE o seguro muda (ex: nova vigência).
        Seguro é encargo acessório e NUNCA afeta saldo devedor ou amortização.

        Args:
            financiamento_id: ID do financiamento
            a_partir_de: Data opcional - recalcula apenas parcelas >= esta data

        Returns:
            Quantidade de parcelas atualizadas

        Raises:
            ValueError: Se faltar vigência para alguma data (fail-fast)
        """
        import logging
        logger = logging.getLogger(__name__)

        logger.info(f"[SEGURO-ONLY] ========== INÍCIO RECÁLCULO SEGURO FIN_ID={financiamento_id} ==========")
        if a_partir_de:
            logger.info(f"[SEGURO-ONLY] A partir de: {a_partir_de}")

        # Buscar financiamento
        financiamento = FinanciamentoService.obter_financiamento_no_perfil(financiamento_id)

        # Buscar parcelas pendentes
        query = FinanciamentoParcela.query.filter_by(
            financiamento_id=financiamento_id,
            status='pendente'
        )

        # Filtrar por data se fornecido
        if a_partir_de:
            query = query.filter(FinanciamentoParcela.data_vencimento >= a_partir_de)

        parcelas_pendentes = query.order_by(FinanciamentoParcela.numero_parcela).all()

        if not parcelas_pendentes:
            logger.info(f"[SEGURO-ONLY] Nenhuma parcela pendente para atualizar")
            return 0

        logger.info(f"[SEGURO-ONLY] Total de parcelas a atualizar: {len(parcelas_pendentes)}")

        # Atualizar SOMENTE o componente seguro
        for parcela in parcelas_pendentes:
            # ❗ CRÍTICO: NÃO mexe em amortização, juros ou saldo
            # Apenas atualiza seguro e total
            parcela.valor_seguro = FinanciamentoService.calcular_seguro_habitacional(
                financiamento,
                parcela.data_vencimento,
                parcela.valor_amortizacao,
                parcela.valor_juros
            )
            parcela.valor_previsto_total = (
                parcela.valor_amortizacao +
                parcela.valor_juros +
                parcela.valor_seguro +
                parcela.valor_taxa_adm
            )

            logger.info(
                f"[SEGURO-ONLY] Parcela #{parcela.numero_parcela}: "
                f"Seguro R$ {parcela.valor_seguro:,.2f} | "
                f"Total R$ {parcela.valor_previsto_total:,.2f} "
                f"(amort={parcela.valor_amortizacao}, juros={parcela.valor_juros}, saldo_após={parcela.saldo_devedor_apos_pagamento})"
            )

        db.session.commit()
        logger.info(f"[SEGURO-ONLY] ========== FIM RECÁLCULO SEGURO - {len(parcelas_pendentes)} parcelas atualizadas ==========")
        return len(parcelas_pendentes)

    @staticmethod
    def _parcela_tem_execucao_financeira(parcela):
        status = str(parcela.status or '').lower()
        if status in FinanciamentoService.STATUS_PARCELA_EXECUTADA:
            return True

        conta = Conta.query.filter_by(financiamento_parcela_id=parcela.id).first()
        if not conta:
            return False

        status_conta = str(conta.status_pagamento or '').lower()
        return (
            status_conta in FinanciamentoService.STATUS_CONTA_EXECUTADA
            or conta.data_pagamento is not None
        )

    @staticmethod
    def _saldo_projetado_antes_parcela(financiamento, numero_parcela):
        if numero_parcela <= 1:
            return financiamento.valor_financiado

        parcela_anterior = FinanciamentoParcela.query.filter_by(
            financiamento_id=financiamento.id,
            numero_parcela=numero_parcela - 1
        ).first()

        if parcela_anterior and parcela_anterior.saldo_devedor_apos_pagamento is not None:
            return parcela_anterior.saldo_devedor_apos_pagamento
        return financiamento.valor_financiado

    @staticmethod
    def _obter_parcela_referencia_ajuste(financiamento_id, dados):
        parcela = None
        if dados.get('parcela_referencia_id'):
            parcela = FinanciamentoParcela.query.filter_by(
                id=int(dados['parcela_referencia_id']),
                financiamento_id=financiamento_id
            ).first()
        elif dados.get('numero_parcela'):
            parcela = FinanciamentoParcela.query.filter_by(
                financiamento_id=financiamento_id,
                numero_parcela=int(dados['numero_parcela'])
            ).first()

        if not parcela:
            raise ValueError('Parcela de referencia nao encontrada para este financiamento')
        return parcela

    @staticmethod
    def ajustar_saldo_devedor_real(financiamento_id, dados):
        """
        Registra saldo devedor real e recalcula apenas parcelas futuras pendentes.
        """
        financiamento = FinanciamentoService.obter_financiamento_no_perfil(financiamento_id)
        parcela_referencia = FinanciamentoService._obter_parcela_referencia_ajuste(financiamento.id, dados)

        saldo_real = FinanciamentoService._decimal(dados.get('saldo_devedor_real'), 'saldo_devedor_real')
        if saldo_real <= 0:
            raise ValueError('saldo_devedor_real deve ser maior que zero')

        data_referencia = (
            FinanciamentoService._converter_data_iso(dados.get('data_referencia'), 'data_referencia')
            if dados.get('data_referencia')
            else parcela_referencia.data_vencimento
        )

        if FinanciamentoService._parcela_tem_execucao_financeira(parcela_referencia):
            numero_inicio = parcela_referencia.numero_parcela + 1
            saldo_anterior = parcela_referencia.saldo_devedor_apos_pagamento or saldo_real
        else:
            numero_inicio = parcela_referencia.numero_parcela
            saldo_anterior = FinanciamentoService._saldo_projetado_antes_parcela(
                financiamento,
                parcela_referencia.numero_parcela
            )

        parcelas_alvo = FinanciamentoParcela.query.filter(
            FinanciamentoParcela.financiamento_id == financiamento.id,
            FinanciamentoParcela.numero_parcela >= numero_inicio,
            FinanciamentoParcela.status == 'pendente'
        ).order_by(FinanciamentoParcela.numero_parcela).all()

        if not parcelas_alvo:
            raise ValueError('Nao ha parcelas futuras pendentes para recalcular a partir da referencia informada')

        parcelas_na_faixa = FinanciamentoParcela.query.filter(
            FinanciamentoParcela.financiamento_id == financiamento.id,
            FinanciamentoParcela.numero_parcela >= numero_inicio
        ).all()
        for parcela in parcelas_na_faixa:
            if FinanciamentoService._parcela_tem_execucao_financeira(parcela):
                raise ValueError(
                    'Existem parcelas futuras vinculadas a contas ja efetivadas. '
                    'O ajuste de saldo nao pode ser aplicado automaticamente.'
                )

        ajuste = FinanciamentoAjusteSaldo(
            perfil_financeiro_id=financiamento.perfil_financeiro_id,
            financiamento_id=financiamento.id,
            parcela_referencia_id=parcela_referencia.id,
            numero_parcela=parcela_referencia.numero_parcela,
            data_referencia=data_referencia,
            saldo_devedor_anterior=saldo_anterior,
            saldo_devedor_real=saldo_real,
            diferenca=saldo_real - Decimal(str(saldo_anterior or 0)),
            tipo_ajuste=dados.get('tipo_ajuste') or 'ajuste_saldo_real',
            observacao=dados.get('observacao') or dados.get('observacoes'),
            parcelas_recalculadas=0,
        )
        db.session.add(ajuste)
        db.session.flush()

        if dados.get('recalcular_parcelas_futuras', True) is False:
            financiamento.saldo_devedor_atual = saldo_real
            financiamento.data_base = data_referencia
            financiamento.numero_parcela_base = numero_inicio - 1
            db.session.commit()
            return ajuste, 0

        saldo_base = saldo_real
        taxa_mensal = financiamento.taxa_juros_mensal
        sistema = financiamento.sistema_amortizacao

        for indice, parcela in enumerate(parcelas_alvo):
            parcelas_restantes = len(parcelas_alvo) - indice
            juros = saldo_base * taxa_mensal

            if sistema == 'PRICE':
                if taxa_mensal > 0:
                    fator = (Decimal('1') + taxa_mensal) ** Decimal(str(parcelas_restantes))
                    prestacao = saldo_base * taxa_mensal * fator / (fator - Decimal('1'))
                else:
                    prestacao = saldo_base / Decimal(str(parcelas_restantes))
                amortizacao = prestacao - juros
            else:
                amortizacao = saldo_base / Decimal(str(parcelas_restantes))
                prestacao = amortizacao + juros

            if amortizacao > saldo_base:
                amortizacao = saldo_base
                prestacao = amortizacao + juros

            valor_seguro = FinanciamentoService.calcular_seguro_habitacional(
                financiamento,
                parcela.data_vencimento,
                amortizacao,
                juros
            )
            valor_taxa_adm = parcela.valor_taxa_adm or financiamento.taxa_administracao_fixa or Decimal('0')
            saldo_final = saldo_base - amortizacao

            parcela.valor_amortizacao = amortizacao
            parcela.valor_juros = juros
            parcela.valor_seguro = valor_seguro
            parcela.valor_taxa_adm = valor_taxa_adm
            parcela.valor_previsto_total = prestacao + valor_seguro + valor_taxa_adm
            parcela.saldo_devedor_apos_pagamento = saldo_final if saldo_final > Decimal('0.01') else Decimal('0')

            FinanciamentoService._criar_conta_da_parcela(financiamento, parcela)
            saldo_base = saldo_final

        financiamento.saldo_devedor_atual = saldo_real
        financiamento.data_base = data_referencia
        financiamento.numero_parcela_base = numero_inicio - 1
        financiamento.prazo_remanescente_meses = len(parcelas_alvo)
        if parcelas_alvo:
            financiamento.amortizacao_mensal_atual = parcelas_alvo[0].valor_amortizacao
        ajuste.parcelas_recalculadas = len(parcelas_alvo)

        db.session.commit()
        return ajuste, len(parcelas_alvo)

    # ========================================================================
    # GERAÇÃO DE PARCELAS
    # ========================================================================

    @staticmethod
    def gerar_parcelas(financiamento):
        """
        Gera tabela de amortização completa usando configurações do próprio financiamento

        Calcula seguro por helper central:
        - Modo 'fixo': vigencia manual por data
        - Modo 'estimado_dfi_mip': DFI + MIP por faixa etaria

        Args:
            financiamento (Financiamento): Objeto do financiamento com todas configurações
        """
        if FinanciamentoParcela.query.filter_by(financiamento_id=financiamento.id).count() > 0:
            FinanciamentoService._remover_cronograma_sem_execucao(financiamento.id)

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
    def _criar_conta_da_parcela(financiamento, parcela):
        """
        Cria ou atualiza uma Conta para a parcela, garantindo idempotência.
        """
        if not financiamento.item_despesa_id:
            return

        conta_existente = Conta.query.filter_by(financiamento_parcela_id=parcela.id).first()
        mes_referencia = parcela.data_vencimento.replace(day=1)

        if conta_existente:
            conta_existente.valor = parcela.valor_previsto_total
            conta_existente.data_vencimento = parcela.data_vencimento
            conta_existente.mes_referencia = mes_referencia
            conta_existente.numero_parcela = parcela.numero_parcela
            conta_existente.total_parcelas = financiamento.prazo_total_meses
            conta_existente.financiamento_parcela_id = parcela.id
        else:
            conta_existente = Conta(
                perfil_financeiro_id=financiamento.perfil_financeiro_id,
                item_despesa_id=financiamento.item_despesa_id,
                financiamento_parcela_id=parcela.id,
                mes_referencia=mes_referencia,
                descricao=f'{financiamento.nome} - Parcela {parcela.numero_parcela}/{financiamento.prazo_total_meses}',
                valor=parcela.valor_previsto_total,
                data_vencimento=parcela.data_vencimento,
                data_pagamento=parcela.data_vencimento if parcela.status == 'pago' else None,
                status_pagamento='Pago' if parcela.status == 'pago' else 'Pendente',
                numero_parcela=parcela.numero_parcela,
                total_parcelas=financiamento.prazo_total_meses,
                observacoes=f'Financiamento {financiamento.sistema_amortizacao}'
            )
            db.session.add(conta_existente)

        if parcela.status == 'pago':
            conta_existente.status_pagamento = 'Pago'
            conta_existente.data_pagamento = parcela.data_vencimento
        else:
            conta_existente.status_pagamento = 'Pendente'
            conta_existente.data_pagamento = None

        db.session.flush()
        parcela.conta_id = conta_existente.id

    @staticmethod
    def _gerar_parcelas_sac(financiamento):
        """
        Sistema de Amortização Constante (SAC) com Modelo de Fases

        FASE 1: Parcelas antes de amortização extraordinária
        - Amortização fixa (saldo / prazo)
        - Juros decrescentes sobre saldo devedor

        EVENTO: Amortização extraordinária (reduzir_parcela ou reduzir_prazo)

        FASE 2: Parcelas após amortização
        - Tipo 'reduzir_parcela': Recalcula amortização fixa = novo_saldo / parcelas_restantes
        - Tipo 'reduzir_prazo': Mantém amortização fixa, reduz número de parcelas

        Aplica TR/indexador se configurado (independente de fases)
        """
        valor_financiado = financiamento.valor_financiado
        prazo = financiamento.prazo_total_meses
        taxa_mensal = financiamento.taxa_juros_mensal
        indexador = financiamento.indexador_saldo

        # Buscar amortizações extraordinárias para aplicar durante a geração
        amortizacoes = FinanciamentoAmortizacaoExtra.query.filter_by(
            financiamento_id=financiamento.id
        ).order_by(FinanciamentoAmortizacaoExtra.data).all()

        # Amortização constante inicial (FASE 1)
        amortizacao_fixa = valor_financiado / Decimal(str(prazo))
        saldo_devedor = valor_financiado
        data_vencimento = financiamento.data_primeira_parcela

        # Controle de fases
        amortizacao_aplicada = None
        parcelas_geradas = 0

        for num_parcela in range(1, prazo + 1):
            # DETECÇÃO DE EVENTO: Verificar se há amortização antes desta parcela
            for amort in amortizacoes:
                if (amortizacao_aplicada != amort and
                    amort.data < data_vencimento and
                    parcelas_geradas > 0):  # Só aplica se já gerou pelo menos 1 parcela

                    # TRANSIÇÃO DE FASE: Aplicar amortização extraordinária
                    saldo_devedor = saldo_devedor - amort.valor

                    if saldo_devedor < 0:
                        saldo_devedor = Decimal('0')
                        break

                    # Recalcular amortização fixa baseado no tipo
                    parcelas_restantes = prazo - num_parcela + 1

                    if amort.tipo == 'reduzir_parcela':
                        # FASE 2A: Recalcula amortização fixa
                        amortizacao_fixa = saldo_devedor / Decimal(str(parcelas_restantes))
                    elif amort.tipo == 'reduzir_prazo':
                        # FASE 2B: Mantém amortização, reduz prazo
                        # Amortização fixa permanece a mesma
                        # O número de parcelas será ajustado quando saldo zerar
                        pass

                    amortizacao_aplicada = amort

            # Se saldo zerou, parar de gerar parcelas
            if saldo_devedor <= Decimal('0.01'):
                break

            # Buscar TR/indexador se configurado (aplica no saldo ANTES de calcular a parcela)
            taxa_indexador = Decimal('0')
            if indexador:
                taxa_indexador = FinanciamentoService._obter_indexador(indexador, data_vencimento)

            # Corrigir saldo devedor com indexador (TR faz saldo CRESCER)
            # Importante: isso só acontece UMA VEZ por mês, no início do período
            saldo_corrigido = saldo_devedor * (Decimal('1') + taxa_indexador / Decimal('100'))

            # Calcular juros sobre saldo corrigido
            # IMPORTANTE: taxa_mensal já é decimal (ex: 0.006827), não dividir por 100!
            juros = saldo_corrigido * taxa_mensal

            # Usar amortização fixa atual (pode ter sido recalculada após amortização)
            amortizacao = amortizacao_fixa

            # Proteção: Se amortização é maior que saldo, ajustar (última parcela)
            if amortizacao > saldo_corrigido:
                amortizacao = saldo_corrigido

            valor_seguro_parcela = FinanciamentoService.calcular_seguro_habitacional(
                financiamento,
                data_vencimento,
                amortizacao,
                juros
            )

            # Taxa administrativa (valor fixo mensal)
            valor_taxa_adm = financiamento.taxa_administracao_fixa

            # Compor parcela
            valor_previsto_total = amortizacao + juros + valor_seguro_parcela + valor_taxa_adm

            # Calcular saldo após pagamento (subtrai amortização do saldo CORRIGIDO)
            saldo_apos_pagamento = saldo_corrigido - amortizacao

            # Criar parcela
            parcela = FinanciamentoParcela(
                perfil_financeiro_id=financiamento.perfil_financeiro_id,
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
            db.session.flush()
            FinanciamentoService._criar_conta_da_parcela(financiamento, parcela)

            parcelas_geradas += 1

            # Atualizar saldo para próxima iteração
            # IMPORTANTE: passa o saldo SEM correção, pois a TR será aplicada no próximo mês
            saldo_devedor = saldo_apos_pagamento
            data_vencimento = data_vencimento + relativedelta(months=1)

    @staticmethod
    def _gerar_parcelas_price(financiamento):
        """
        Tabela PRICE

        Parcela fixa (amortização + juros)
        Juros decrescentes, amortização crescente
        Seguro obtido via lookup de vigência por data
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

            valor_seguro_parcela = FinanciamentoService.calcular_seguro_habitacional(
                financiamento,
                data_vencimento,
                amortizacao,
                juros
            )

            # Taxa administrativa (valor fixo mensal)
            valor_taxa_adm = financiamento.taxa_administracao_fixa

            # Valor total com seguros e taxas
            valor_previsto_total = pmt + valor_seguro_parcela + valor_taxa_adm

            # Saldo após pagamento
            saldo_apos_pagamento = saldo_devedor - amortizacao

            # Criar parcela
            parcela = FinanciamentoParcela(
                perfil_financeiro_id=financiamento.perfil_financeiro_id,
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
            db.session.flush()
            FinanciamentoService._criar_conta_da_parcela(financiamento, parcela)

            # Atualizar
            saldo_devedor = saldo_apos_pagamento
            data_vencimento = data_vencimento + relativedelta(months=1)

    @staticmethod
    def _gerar_parcelas_simples(financiamento):
        """
        Juros Simples

        Juros fixos sobre valor inicial em todas as parcelas
        Amortização constante
        Seguro obtido via lookup de vigência por data
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
            valor_seguro_parcela = FinanciamentoService.calcular_seguro_habitacional(
                financiamento,
                data_vencimento,
                amortizacao,
                juros_mensais
            )

            # Taxa administrativa (valor fixo mensal)
            valor_taxa_adm = financiamento.taxa_administracao_fixa

            valor_previsto_total = amortizacao + juros_mensais + valor_seguro_parcela + valor_taxa_adm

            saldo_apos_pagamento = saldo_devedor - amortizacao

            parcela = FinanciamentoParcela(
                perfil_financeiro_id=financiamento.perfil_financeiro_id,
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
            db.session.flush()
            FinanciamentoService._criar_conta_da_parcela(financiamento, parcela)

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
        parcela = PerfilFinanceiroService.aplicar_perfil_query(
            FinanciamentoParcela.query, FinanciamentoParcela
        ).filter(FinanciamentoParcela.id == parcela_id).first()
        if not parcela:
            raise ValueError('Parcela não encontrada')

        # Converter data se necessário
        if isinstance(data_pagamento, str):
            data_pagamento = datetime.strptime(data_pagamento, '%Y-%m-%d').date()

        # Atualizar valores
        parcela.valor_pago = Decimal(str(valor_pago))
        # Nota: FinanciamentoParcela não tem campo data_pagamento
        # A data de pagamento é armazenada na Conta vinculada
        parcela.dif_apurada = parcela.valor_previsto_total - parcela.valor_pago
        parcela.status = 'pago'

        # ========================================================================
        # ATUALIZAR SALDO SOBERANO (usar saldo calculado da parcela)
        # ========================================================================
        financiamento = FinanciamentoService.obter_financiamento_no_perfil(parcela.financiamento_id)
        if financiamento:
            # Usar saldo_devedor_apos_pagamento da parcela (já considera TR, amortização, etc.)
            # Este campo foi calculado corretamente pelo sistema SAC durante geração/recálculo
            financiamento.saldo_devedor_atual = parcela.saldo_devedor_apos_pagamento

        # Sincronizar conta vinculada diretamente
        conta_relacionada = Conta.query.filter_by(financiamento_parcela_id=parcela.id).first()
        if conta_relacionada:
            conta_relacionada.status_pagamento = 'Pago'
            conta_relacionada.data_pagamento = data_pagamento
            conta_relacionada.valor = parcela.valor_pago or parcela.valor_previsto_total

        db.session.commit()

        # Sincronizar com a Conta correspondente
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
        financiamento = FinanciamentoService.obter_financiamento_no_perfil(financiamento_id)

        # Converter data
        if isinstance(dados_amortizacao['data'], str):
            data_amort = datetime.strptime(dados_amortizacao['data'], '%Y-%m-%d').date()
        else:
            data_amort = dados_amortizacao['data']

        valor = Decimal(str(dados_amortizacao['valor']))
        tipo = dados_amortizacao['tipo']
        if valor <= 0:
            raise ValueError('Valor da amortizacao deve ser maior que zero')

        parcelas_afetadas = FinanciamentoParcela.query.filter(
            FinanciamentoParcela.financiamento_id == financiamento.id,
            FinanciamentoParcela.data_vencimento >= data_amort
        ).order_by(FinanciamentoParcela.numero_parcela).all()

        for parcela in parcelas_afetadas:
            if FinanciamentoService._parcela_tem_execucao_financeira(parcela):
                raise ValueError(
                    'Existem parcelas futuras vinculadas a contas ja efetivadas. '
                    'A amortizacao nao pode ser aplicada automaticamente.'
                )

        # Criar registro
        amortizacao = FinanciamentoAmortizacaoExtra(
            perfil_financeiro_id=financiamento.perfil_financeiro_id,
            financiamento_id=financiamento_id,
            data=data_amort,
            valor=valor,
            tipo=tipo,
            observacoes=dados_amortizacao.get('observacoes', '')
        )

        db.session.add(amortizacao)
        db.session.flush()

        # ========================================================================
        # ATUALIZAR ESTADO SOBERANO (fonte de verdade)
        # ========================================================================
        # 1) Reduzir saldo devedor ATUAL
        financiamento.saldo_devedor_atual = financiamento.saldo_devedor_atual - valor

        # 2) Atualizar regime
        financiamento.regime_pos_amortizacao = tipo.upper().replace('reduzir_', 'REDUZIR_')

        # 3) Recalcular amortização mensal ou prazo conforme regime
        if tipo == 'reduzir_parcela':
            # Mantém prazo, reduz amortização mensal
            financiamento.amortizacao_mensal_atual = financiamento.saldo_devedor_atual / Decimal(str(financiamento.prazo_remanescente_meses))
        elif tipo == 'reduzir_prazo':
            # Mantém amortização mensal, reduz prazo
            import math
            prazo_novo = math.ceil(float(financiamento.saldo_devedor_atual / financiamento.amortizacao_mensal_atual))
            financiamento.prazo_remanescente_meses = prazo_novo

        # 4) Atualizar numero_parcela_base e data_base
        # Buscar última parcela consolidada (paga ou anterior à primeira pendente)
        ultima_consolidada = FinanciamentoParcela.query.filter_by(
            financiamento_id=financiamento.id,
            status='pago'
        ).order_by(FinanciamentoParcela.numero_parcela.desc()).first()

        if ultima_consolidada:
            financiamento.numero_parcela_base = ultima_consolidada.numero_parcela
            financiamento.data_base = ultima_consolidada.data_vencimento

        db.session.flush()  # Persistir estado soberano ANTES de recalcular parcelas

        # Recalcular parcelas futuras
        FinanciamentoService._recalcular_apos_amortizacao(financiamento, data_amort, valor, tipo)

        db.session.commit()

        return amortizacao

    @staticmethod
    def _recalcular_apos_amortizacao(financiamento, data_amortizacao, valor_amortizado, tipo):
        """
        Recalcula parcelas futuras após amortização extraordinária

        IMPORTANTE: O estado soberano (saldo_devedor_atual, amortizacao_mensal_atual, etc)
        JÁ FOI ATUALIZADO antes de chamar este método.
        Aqui apenas regeneramos as parcelas pendentes com base no estado soberano.

        Args:
            financiamento (Financiamento): Objeto do financiamento
            data_amortizacao (date): Data da amortização
            valor_amortizado (Decimal): Valor amortizado
            tipo (str): 'reduzir_parcela' ou 'reduzir_prazo'
        """
        # Buscar parcelas pendentes após a data de amortização
        parcelas_pendentes = FinanciamentoParcela.query.filter(
            FinanciamentoParcela.financiamento_id == financiamento.id,
            FinanciamentoParcela.data_vencimento >= data_amortizacao,
            FinanciamentoParcela.status == 'pendente'
        ).order_by(FinanciamentoParcela.numero_parcela).all()

        if not parcelas_pendentes:
            return

        # ========================================================================
        # USAR ESTADO SOBERANO (NÃO tentar descobrir saldo de parcelas antigas)
        # ========================================================================
        # O saldo JÁ foi atualizado no financiamento.saldo_devedor_atual
        novo_saldo = financiamento.saldo_devedor_atual

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

            valor_seguro = FinanciamentoService.calcular_seguro_habitacional(
                financiamento,
                parcela.data_vencimento,
                amortizacao,
                juros
            )

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
            FinanciamentoService._criar_conta_da_parcela(financiamento, parcela)

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

            valor_seguro = FinanciamentoService.calcular_seguro_habitacional(
                financiamento,
                parcela.data_vencimento,
                amortizacao,
                juros
            )

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
            FinanciamentoService._criar_conta_da_parcela(financiamento, parcela)

            parcelas_para_manter.append(parcela)

            # Atualizar saldo
            saldo_devedor = saldo_devedor - amortizacao

            # Se quitou tudo, para
            if saldo_devedor <= Decimal('0.01'):
                break

        # Deletar parcelas excedentes
        parcelas_para_deletar = [p for p in parcelas_pendentes if p not in parcelas_para_manter]
        ids_para_deletar = [p.id for p in parcelas_para_deletar if p.id]
        if ids_para_deletar:
            FinanciamentoParcela.query.filter(
                FinanciamentoParcela.id.in_(ids_para_deletar)
            ).update(
                {FinanciamentoParcela.conta_id: None},
                synchronize_session=False
            )
            db.session.flush()

            Conta.query.filter(
                Conta.financiamento_parcela_id.in_(ids_para_deletar)
            ).delete(synchronize_session=False)
            db.session.flush()

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
        financiamento = FinanciamentoService.obter_financiamento_no_perfil(financiamento_id)

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

        financiamento = FinanciamentoService.obter_financiamento_no_perfil(financiamento_id)

        if not financiamento.item_despesa_id:
            # Se não tem item_despesa vinculado, não criar contas
            return

        # Buscar todas as parcelas
        parcelas = FinanciamentoParcela.query.filter_by(
            financiamento_id=financiamento_id
        ).order_by(FinanciamentoParcela.numero_parcela).all()

        for parcela in parcelas:
            FinanciamentoService._criar_conta_da_parcela(financiamento, parcela)
            continue
            conta_existente = Conta.query.filter_by(financiamento_parcela_id=parcela.id).first()
            if not conta_existente:
                conta_existente = Conta.query.filter(
                    Conta.item_despesa_id == financiamento.item_despesa_id,
                    Conta.numero_parcela == parcela.numero_parcela,
                    Conta.total_parcelas == financiamento.prazo_total_meses
                ).first()

            # Calcular mês de referência (mesma lógica do consórcio)
            mes_referencia = parcela.data_vencimento.replace(day=1)

            if conta_existente:
                # Atualizar conta existente
                conta_existente.valor = parcela.valor_previsto_total
                conta_existente.data_vencimento = parcela.data_vencimento
                conta_existente.mes_referencia = mes_referencia
                conta_existente.financiamento_parcela_id = parcela.id
                parcela.conta_id = conta_existente.id

                # Sincronizar status de pagamento
                if parcela.status == 'pago' and not conta_existente.data_pagamento:
                    conta_existente.status_pagamento = 'Pago'
                    conta_existente.data_pagamento = parcela.data_vencimento
                elif parcela.status == 'pendente':
                    conta_existente.status_pagamento = 'Pendente'
                    conta_existente.data_pagamento = None
            else:
                # Criar nova conta
                nova_conta = Conta(
                    perfil_financeiro_id=financiamento.perfil_financeiro_id,
                    item_despesa_id=financiamento.item_despesa_id,
                    financiamento_parcela_id=parcela.id,
                    mes_referencia=mes_referencia,
                    descricao=f'{financiamento.nome} - Parcela {parcela.numero_parcela}/{financiamento.prazo_total_meses}',
                    valor=parcela.valor_previsto_total,
                    data_vencimento=parcela.data_vencimento,
                    data_pagamento=parcela.data_vencimento if parcela.status == 'pago' else None,
                    status_pagamento='Pago' if parcela.status == 'pago' else 'Pendente',
                    numero_parcela=parcela.numero_parcela,
                    total_parcelas=financiamento.prazo_total_meses,
                    observacoes=f'Financiamento {financiamento.sistema_amortizacao} - ' +
                               f'Amortização: R$ {float(parcela.valor_amortizacao):.2f}, ' +
                               f'Juros: R$ {float(parcela.valor_juros):.2f}'
                )
                db.session.add(nova_conta)
                db.session.flush()
                parcela.conta_id = nova_conta.id

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
