from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re

from sqlalchemy import extract

try:
    from backend.models import (
        db,
        Financiamento,
        FinanciamentoConferenciaCaixa,
        FinanciamentoDocumento,
        FinanciamentoParcela,
    )
    from backend.services.perfil_financeiro_service import PerfilFinanceiroService
except ImportError:
    from models import (
        db,
        Financiamento,
        FinanciamentoConferenciaCaixa,
        FinanciamentoDocumento,
        FinanciamentoParcela,
    )
    from services.perfil_financeiro_service import PerfilFinanceiroService


class FinanciamentoConferenciaService:
    """
    Registra conferencias manuais entre demonstrativos CAIXA e o cronograma.

    A conferencia e somente auditoria: nao altera saldo, parcelas, pagamentos
    ou qualquer regra financeira do financiamento.
    """

    COMPETENCIA_RE = re.compile(r'^\d{4}-(0[1-9]|1[0-2])$')
    CENTAVOS = Decimal('0.01')
    CAMPOS_REAL = (
        'valor_real_amortizacao',
        'valor_real_juros',
        'valor_real_seguro',
        'valor_real_taxa_adm',
        'valor_real_total',
        'saldo_devedor_real',
        'juros_correcao_mes_real',
        'amortizacao_mes_real',
    )

    @staticmethod
    def listar_conferencias(financiamento_id):
        financiamento = FinanciamentoConferenciaService._obter_financiamento(financiamento_id)
        return financiamento.conferencias_caixa.order_by(
            FinanciamentoConferenciaCaixa.criado_em.desc()
        ).all()

    @staticmethod
    def listar_conferencias_documento(financiamento_id, documento_id):
        documento = FinanciamentoConferenciaService._obter_documento(financiamento_id, documento_id)
        return documento.conferencias_caixa.order_by(FinanciamentoConferenciaCaixa.criado_em.desc()).all()

    @staticmethod
    def registrar_conferencia(financiamento_id, dados):
        financiamento = FinanciamentoConferenciaService._obter_financiamento(financiamento_id)
        dados_validados = FinanciamentoConferenciaService._validar_dados_conferencia(financiamento.id, dados or {})

        documento = None
        if dados_validados['documento_id']:
            documento = FinanciamentoConferenciaService._obter_documento(
                financiamento.id,
                dados_validados['documento_id'],
            )

        parcela = FinanciamentoConferenciaService._obter_parcela_simulada(
            financiamento.id,
            dados_validados.get('parcela_id'),
            dados_validados.get('competencia'),
            dados_validados.get('data_referencia'),
        )

        simulados = FinanciamentoConferenciaService._valores_simulados_da_parcela(parcela)
        conferencia = FinanciamentoConferenciaCaixa(
            perfil_financeiro_id=PerfilFinanceiroService.obter_perfil_ativo_id(),
            financiamento_id=financiamento.id,
            documento_id=documento.id if documento else None,
            tipo_conferencia=dados_validados['tipo_conferencia'],
            competencia=dados_validados['competencia'],
            ano_base=dados_validados['ano_base'],
            data_referencia=dados_validados['data_referencia'],
            parcela_id=parcela.id if parcela else None,
            valor_real_amortizacao=dados_validados['valor_real_amortizacao'],
            valor_real_juros=dados_validados['valor_real_juros'],
            valor_real_seguro=dados_validados['valor_real_seguro'],
            valor_real_taxa_adm=dados_validados['valor_real_taxa_adm'],
            valor_real_total=dados_validados['valor_real_total'],
            saldo_devedor_real=dados_validados['saldo_devedor_real'],
            juros_correcao_mes_real=dados_validados['juros_correcao_mes_real'],
            amortizacao_mes_real=dados_validados['amortizacao_mes_real'],
            prazo_remanescente_real=dados_validados['prazo_remanescente_real'],
            observacao=dados_validados['observacao'],
            **simulados,
        )
        FinanciamentoConferenciaService._calcular_diferencas(conferencia)

        db.session.add(conferencia)
        db.session.commit()
        return conferencia

    @staticmethod
    def excluir_conferencia(financiamento_id, conferencia_id):
        financiamento = FinanciamentoConferenciaService._obter_financiamento(financiamento_id)
        conferencia = FinanciamentoConferenciaCaixa.query.filter_by(
            id=conferencia_id,
            financiamento_id=financiamento.id,
        ).first()
        if not conferencia:
            raise ValueError('Conferencia nao encontrada')
        PerfilFinanceiroService.validar_pertence_ao_perfil(conferencia)
        db.session.delete(conferencia)
        db.session.commit()

    @staticmethod
    def obter_valores_simulados(financiamento_id, competencia=None, parcela_id=None, data_referencia=None):
        financiamento = FinanciamentoConferenciaService._obter_financiamento(financiamento_id)
        competencia_validada = FinanciamentoConferenciaService._validar_competencia(competencia)
        data_validada = FinanciamentoConferenciaService._validar_data(data_referencia, 'data_referencia')
        parcela_id_validado = FinanciamentoConferenciaService._inteiro_opcional(parcela_id, 'parcela_id')
        parcela = FinanciamentoConferenciaService._obter_parcela_simulada(
            financiamento.id,
            parcela_id_validado,
            competencia_validada,
            data_validada,
        )
        return FinanciamentoConferenciaService._dados_simulados_publicos(parcela)

    @staticmethod
    def _obter_financiamento(financiamento_id):
        financiamento = PerfilFinanceiroService.aplicar_perfil_query(
            Financiamento.query,
            Financiamento,
        ).filter(Financiamento.id == financiamento_id).first()
        if not financiamento:
            raise ValueError('Financiamento nao encontrado')
        return financiamento

    @staticmethod
    def _obter_documento(financiamento_id, documento_id):
        documento = FinanciamentoDocumento.query.filter_by(
            id=documento_id,
            financiamento_id=financiamento_id,
        ).first()
        if not documento:
            raise ValueError('Documento nao encontrado para este financiamento')
        PerfilFinanceiroService.validar_pertence_ao_perfil(documento)
        return documento

    @staticmethod
    def _validar_dados_conferencia(financiamento_id, dados):
        tipo = str(dados.get('tipo_conferencia') or '').strip()
        if tipo not in FinanciamentoConferenciaCaixa.TIPOS_CONFERENCIA:
            raise ValueError('Tipo de conferencia invalido')

        documento_id = FinanciamentoConferenciaService._inteiro_opcional(dados.get('documento_id'), 'documento_id')
        parcela_id = FinanciamentoConferenciaService._inteiro_opcional(dados.get('parcela_id'), 'parcela_id')
        if parcela_id and not FinanciamentoParcela.query.filter_by(
            id=parcela_id,
            financiamento_id=financiamento_id,
        ).first():
            raise ValueError('Parcela nao encontrada para este financiamento')

        ano_base = FinanciamentoConferenciaService._ano_opcional(dados.get('ano_base'))
        data_referencia = FinanciamentoConferenciaService._validar_data(dados.get('data_referencia'), 'data_referencia')
        competencia = FinanciamentoConferenciaService._validar_competencia(dados.get('competencia'))
        observacao = str(dados.get('observacao') or '').strip() or None
        if observacao and len(observacao) > 3000:
            raise ValueError('Observacao deve ter no maximo 3000 caracteres')

        valores = {
            campo: FinanciamentoConferenciaService._decimal_opcional(dados.get(campo), campo)
            for campo in FinanciamentoConferenciaService.CAMPOS_REAL
        }
        prazo_remanescente_real = FinanciamentoConferenciaService._inteiro_nao_negativo_opcional(
            dados.get('prazo_remanescente_real'),
            'prazo_remanescente_real',
        )

        return {
            'tipo_conferencia': tipo,
            'documento_id': documento_id,
            'parcela_id': parcela_id,
            'competencia': competencia,
            'ano_base': ano_base,
            'data_referencia': data_referencia,
            'prazo_remanescente_real': prazo_remanescente_real,
            'observacao': observacao,
            **valores,
        }

    @staticmethod
    def _validar_competencia(valor):
        texto = str(valor or '').strip()
        if not texto:
            return None
        if not FinanciamentoConferenciaService.COMPETENCIA_RE.match(texto):
            raise ValueError('Competencia deve estar no formato YYYY-MM')
        return texto

    @staticmethod
    def _validar_data(valor, campo):
        texto = str(valor or '').strip()
        if not texto:
            return None
        try:
            return datetime.strptime(texto, '%Y-%m-%d').date()
        except ValueError as exc:
            raise ValueError(f'{campo} deve estar no formato YYYY-MM-DD') from exc

    @staticmethod
    def _ano_opcional(valor):
        if valor is None or str(valor).strip() == '':
            return None
        try:
            ano = int(valor)
        except ValueError as exc:
            raise ValueError('ano_base deve ser numerico') from exc
        if ano < 1900 or ano > 2200:
            raise ValueError('ano_base deve estar entre 1900 e 2200')
        return ano

    @staticmethod
    def _inteiro_opcional(valor, campo):
        if valor is None or str(valor).strip() == '':
            return None
        try:
            numero = int(valor)
        except ValueError as exc:
            raise ValueError(f'{campo} deve ser numerico') from exc
        if numero <= 0:
            raise ValueError(f'{campo} deve ser positivo')
        return numero

    @staticmethod
    def _inteiro_nao_negativo_opcional(valor, campo):
        if valor is None or str(valor).strip() == '':
            return None
        try:
            numero = int(valor)
        except ValueError as exc:
            raise ValueError(f'{campo} deve ser numerico') from exc
        if numero < 0:
            raise ValueError(f'{campo} nao pode ser negativo')
        return numero

    @staticmethod
    def _decimal_opcional(valor, campo):
        if valor is None:
            return None
        texto = str(valor).strip()
        if not texto:
            return None
        texto = texto.replace('R$', '').replace(' ', '')
        if ',' in texto and '.' in texto:
            texto = texto.replace('.', '').replace(',', '.')
        elif ',' in texto:
            texto = texto.replace(',', '.')
        try:
            numero = Decimal(texto)
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f'{campo} deve ser numerico') from exc
        if numero < 0:
            raise ValueError(f'{campo} nao pode ser negativo')
        return numero.quantize(FinanciamentoConferenciaService.CENTAVOS, rounding=ROUND_HALF_UP)

    @staticmethod
    def _obter_parcela_simulada(financiamento_id, parcela_id=None, competencia=None, data_referencia=None):
        query = FinanciamentoParcela.query.filter_by(financiamento_id=financiamento_id)
        if parcela_id:
            parcela = query.filter_by(id=parcela_id).first()
            if not parcela:
                raise ValueError('Parcela nao encontrada para este financiamento')
            return parcela

        competencia_busca = competencia
        if not competencia_busca and data_referencia:
            competencia_busca = data_referencia.strftime('%Y-%m')
        if not competencia_busca:
            return None

        ano, mes = [int(parte) for parte in competencia_busca.split('-')]
        return query.filter(
            extract('year', FinanciamentoParcela.data_vencimento) == ano,
            extract('month', FinanciamentoParcela.data_vencimento) == mes,
        ).order_by(FinanciamentoParcela.data_vencimento.asc()).first()

    @staticmethod
    def _valores_simulados_da_parcela(parcela):
        if not parcela:
            return {
                'valor_simulado_amortizacao': None,
                'valor_simulado_juros': None,
                'valor_simulado_seguro': None,
                'valor_simulado_taxa_adm': None,
                'valor_simulado_total': None,
                'saldo_devedor_simulado': None,
            }
        return {
            'valor_simulado_amortizacao': FinanciamentoConferenciaService._decimal_banco(parcela.valor_amortizacao),
            'valor_simulado_juros': FinanciamentoConferenciaService._decimal_banco(parcela.valor_juros),
            'valor_simulado_seguro': FinanciamentoConferenciaService._decimal_banco(parcela.valor_seguro),
            'valor_simulado_taxa_adm': FinanciamentoConferenciaService._decimal_banco(parcela.valor_taxa_adm),
            'valor_simulado_total': FinanciamentoConferenciaService._decimal_banco(parcela.valor_previsto_total),
            'saldo_devedor_simulado': FinanciamentoConferenciaService._decimal_banco(parcela.saldo_devedor_apos_pagamento),
        }

    @staticmethod
    def _dados_simulados_publicos(parcela):
        if not parcela:
            return {'encontrado': False}
        simulados = FinanciamentoConferenciaService._valores_simulados_da_parcela(parcela)
        return {
            'encontrado': True,
            'competencia': parcela.data_vencimento.strftime('%Y-%m'),
            'parcela_id': parcela.id,
            'numero_parcela': parcela.numero_parcela,
            'amortizacao': FinanciamentoConferenciaService._float(simulados['valor_simulado_amortizacao']),
            'juros': FinanciamentoConferenciaService._float(simulados['valor_simulado_juros']),
            'seguro': FinanciamentoConferenciaService._float(simulados['valor_simulado_seguro']),
            'taxa_adm': FinanciamentoConferenciaService._float(simulados['valor_simulado_taxa_adm']),
            'total': FinanciamentoConferenciaService._float(simulados['valor_simulado_total']),
            'saldo_devedor': FinanciamentoConferenciaService._float(simulados['saldo_devedor_simulado']),
        }

    @staticmethod
    def _decimal_banco(valor):
        if valor is None:
            return None
        return Decimal(str(valor)).quantize(FinanciamentoConferenciaService.CENTAVOS, rounding=ROUND_HALF_UP)

    @staticmethod
    def _calcular_diferencas(conferencia):
        conferencia.diferenca_amortizacao = FinanciamentoConferenciaService._diferenca(
            conferencia.valor_real_amortizacao,
            conferencia.valor_simulado_amortizacao,
        )
        conferencia.diferenca_juros = FinanciamentoConferenciaService._diferenca(
            conferencia.valor_real_juros,
            conferencia.valor_simulado_juros,
        )
        conferencia.diferenca_seguro = FinanciamentoConferenciaService._diferenca(
            conferencia.valor_real_seguro,
            conferencia.valor_simulado_seguro,
        )
        conferencia.diferenca_taxa_adm = FinanciamentoConferenciaService._diferenca(
            conferencia.valor_real_taxa_adm,
            conferencia.valor_simulado_taxa_adm,
        )
        conferencia.diferenca_total = FinanciamentoConferenciaService._diferenca(
            conferencia.valor_real_total,
            conferencia.valor_simulado_total,
        )
        conferencia.diferenca_saldo = FinanciamentoConferenciaService._diferenca(
            conferencia.saldo_devedor_real,
            conferencia.saldo_devedor_simulado,
        )

    @staticmethod
    def _diferenca(real, simulado):
        if real is None or simulado is None:
            return None
        return (real - simulado).quantize(FinanciamentoConferenciaService.CENTAVOS, rounding=ROUND_HALF_UP)

    @staticmethod
    def _float(valor):
        return float(valor) if valor is not None else None
