"""
Serviço para gerenciamento de vigências de seguro habitacional

REGRAS DE NEGÓCIO (CANÔNICAS):
1. Seguro é MANUAL: usuário informa valor absoluto por vigência
2. taxa_percentual NÃO é calculada automaticamente (campo legacy)
3. Vigência pode ser editada (UPDATE) se NÃO houver parcela paga no período
4. Encerramento de vigência anterior NÃO é automático (usuário controla)
5. Histórico com parcelas pagas é imutável
6. Apenas UMA vigência ativa por financiamento
"""

from backend.models import db, FinanciamentoSeguroVigencia
from datetime import date, timedelta
from decimal import Decimal
from sqlalchemy import and_


class SeguroVigenciaService:

    @staticmethod
    def criar_vigencia(financiamento_id, competencia_inicio, valor_mensal,
                      saldo_devedor_vigencia, data_nascimento_segurado=None,
                      observacoes=None):
        """
        Cria nova vigência de seguro

        Parâmetros:
        - financiamento_id: ID do financiamento
        - competencia_inicio: Primeiro dia do mês de início (date)
        - valor_mensal: Valor do seguro informado pelo usuário (Decimal)
        - saldo_devedor_vigencia: Saldo devedor no início da vigência (Decimal)
        - data_nascimento_segurado: Data de nascimento (opcional)
        - observacoes: Anotações livres (opcional)

        Retorna:
        - Nova vigência criada

        Comportamento:
        1. Normaliza competencia_inicio para primeiro dia do mês
        2. Cria nova vigência como ativa

        NOTA:
        - taxa_percentual não é mais calculada automaticamente (seguro é manual)
        - Encerramento de vigência anterior NÃO é automático (usuário controla via UPDATE)
        """

        # 1. Normalizar competencia_inicio para primeiro dia do mês (CRÍTICO)
        competencia_inicio = competencia_inicio.replace(day=1)

        # 2. Criar nova vigência (sem calcular taxa, sem encerrar anterior)
        nova_vigencia = FinanciamentoSeguroVigencia(
            financiamento_id=financiamento_id,
            competencia_inicio=competencia_inicio,
            valor_mensal=valor_mensal,
            saldo_devedor_vigencia=saldo_devedor_vigencia,
            taxa_percentual=None,  # Não calculado automaticamente
            data_nascimento_segurado=data_nascimento_segurado,
            observacoes=observacoes,
            vigencia_ativa=True,
            data_encerramento=None
        )

        db.session.add(nova_vigencia)
        db.session.flush()

        return nova_vigencia

    @staticmethod
    def _encerrar_vigencia_anterior(financiamento_id, nova_competencia_inicio):
        """
        Encerra vigência anterior ao criar nova

        Regra:
        - competencia_fim = último dia do mês anterior à nova_competencia_inicio
        - Marca vigencia_ativa = False

        Exemplo:
        - Nova vigência: 2026-02-01
        - Vigência anterior encerrada em: 2026-01-31

        NÃO altera valores históricos.
        NÃO apaga registros.
        """

        # Buscar vigência anterior ativa
        vigencia_anterior = FinanciamentoSeguroVigencia.query.filter_by(
            financiamento_id=financiamento_id,
            vigencia_ativa=True
        ).first()

        if vigencia_anterior:
            # Calcular último dia do mês anterior
            # nova_competencia_inicio - 1 dia = último dia do mês anterior
            data_encerramento = nova_competencia_inicio - timedelta(days=1)

            # Atualizar vigência anterior
            vigencia_anterior.vigencia_ativa = False
            vigencia_anterior.data_encerramento = data_encerramento

            db.session.flush()

    @staticmethod
    def obter_vigencia_por_data(financiamento_id, data_referencia):
        """
        Retorna a vigência válida para uma data específica

        Lógica:
        1. Buscar vigências onde competencia_inicio <= data_referencia
        2. Se vigência tem data_encerramento, verificar se data_referencia <= data_encerramento
        3. Ordenar por competencia_inicio decrescente
        4. Retornar a primeira

        Exemplo:
        Vigências:
        - A: 2025-02-01 até 2026-01-31 (encerrada)
        - B: 2026-02-01 até None (ativa)

        Data 2025-06-15 → retorna A
        Data 2026-06-15 → retorna B
        """

        # Buscar todas as vigências do financiamento
        vigencias_candidatas = FinanciamentoSeguroVigencia.query.filter(
            and_(
                FinanciamentoSeguroVigencia.financiamento_id == financiamento_id,
                FinanciamentoSeguroVigencia.competencia_inicio <= data_referencia,
                db.or_(
                    FinanciamentoSeguroVigencia.data_encerramento == None,
                    FinanciamentoSeguroVigencia.data_encerramento >= data_referencia
                )
            )
        ).order_by(
            FinanciamentoSeguroVigencia.competencia_inicio.desc()
        ).all()

        # ====================================================================
        # VALIDAÇÃO DEFENSIVA: Detectar duplicação de vigências ativas
        # ====================================================================
        if len(vigencias_candidatas) > 1:
            # Verificar se há múltiplas vigências ativas na mesma competência
            competencias_ativas = {}
            for v in vigencias_candidatas:
                if v.vigencia_ativa:
                    competencia_mes = v.competencia_inicio.strftime('%Y-%m')
                    if competencia_mes not in competencias_ativas:
                        competencias_ativas[competencia_mes] = []
                    competencias_ativas[competencia_mes].append(v.id)

            # Logar warning se detectar duplicação
            for comp, ids in competencias_ativas.items():
                if len(ids) > 1:
                    import logging
                    logging.warning(
                        f"[VIGÊNCIA DUPLICADA] Financiamento {financiamento_id} "
                        f"tem {len(ids)} vigências ativas na competência {comp}: {ids}. "
                        f"Isso pode causar cálculos incorretos!"
                    )

        vigencia = vigencias_candidatas[0] if vigencias_candidatas else None
        return vigencia

    @staticmethod
    def listar_vigencias(financiamento_id, apenas_ativas=False):
        """
        Lista vigências de um financiamento

        Parâmetros:
        - financiamento_id: ID do financiamento
        - apenas_ativas: Se True, retorna apenas vigencia_ativa=True

        Retorna:
        - Lista ordenada por competencia_inicio (crescente)
        """

        query = FinanciamentoSeguroVigencia.query.filter_by(
            financiamento_id=financiamento_id
        )

        if apenas_ativas:
            query = query.filter_by(vigencia_ativa=True)

        return query.order_by(
            FinanciamentoSeguroVigencia.competencia_inicio
        ).all()

    @staticmethod
    def validar_vigencia_unica_ativa(financiamento_id):
        """
        Valida constraint: apenas UMA vigência ativa por financiamento

        Retorna:
        - True se válido (0 ou 1 vigência ativa)
        - False se inválido (mais de 1 vigência ativa)
        """

        count_ativas = FinanciamentoSeguroVigencia.query.filter_by(
            financiamento_id=financiamento_id,
            vigencia_ativa=True
        ).count()

        return count_ativas <= 1

    @staticmethod
    def vigencia_tem_pagamento(financiamento_id, data_inicio, data_fim=None):
        """
        Verifica se existe alguma parcela PAGA dentro do período DA VIGÊNCIA

        REGRA TEMPORAL:
        - Só considera parcelas cujo vencimento está DENTRO do período da vigência
        - Parcelas pagas ANTES da vigência NÃO bloqueiam edição
        - Parcelas pagas DEPOIS da vigência NÃO bloqueiam edição

        Exemplo:
            Vigência: 11/2025 até None (ativa)
            Parcelas pagas: 08/2025, 09/2025
            Resultado: False (pode editar, pois 08 e 09 < 11)

            Vigência: 11/2025 até None
            Parcelas pagas: 12/2025, 01/2026
            Resultado: True (NÃO pode editar, pois 12 e 01 >= 11)

        Parâmetros:
        - financiamento_id: ID do financiamento
        - data_inicio: Data de início da vigência (competencia_inicio)
        - data_fim: Data de fim da vigência (data_encerramento, None se ativa)

        Retorna:
        - True: Existe parcela paga NO PERÍODO (vigência IMUTÁVEL)
        - False: Não existe parcela paga NO PERÍODO (vigência EDITÁVEL)
        """
        from backend.models import FinanciamentoParcela

        # Construir filtros de período
        filtros = [
            FinanciamentoParcela.financiamento_id == financiamento_id,
            FinanciamentoParcela.status == 'pago',
            FinanciamentoParcela.data_vencimento >= data_inicio
        ]

        # Se vigência tem fim definido, limitar até essa data
        # Caso contrário, considera todas as parcelas >= data_inicio
        if data_fim:
            filtros.append(FinanciamentoParcela.data_vencimento <= data_fim)

        # Buscar primeira parcela paga dentro do período
        parcela_paga = FinanciamentoParcela.query.filter(
            and_(*filtros)
        ).first()

        # DEBUG: Log para diagnóstico
        resultado = parcela_paga is not None
        print(f"[DEBUG] vigencia_tem_pagamento:")
        print(f"  Financiamento: {financiamento_id}")
        print(f"  Período vigência: {data_inicio} até {data_fim or 'None (ativa)'}")
        print(f"  Parcela paga encontrada no período: {resultado}")
        if parcela_paga:
            print(f"  Parcela bloqueadora: #{parcela_paga.numero_parcela}, venc: {parcela_paga.data_vencimento}")

        return resultado
