from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re

from sqlalchemy import func

from backend.models import db, Financiamento, FinanciamentoParcela, IndiceTRMensal


class IndiceTRService:
    VALOR_MAXIMO_PERCENTUAL = Decimal('10')
    QUANTIZADOR_DECIMAL = Decimal('0.00000001')
    MSG_TR_USADA = (
        'Esta TR já é usada em parcelas de financiamento SAC/TR. '
        'Para alterar, será necessário revisar ou recalcular os cronogramas afetados em uma etapa própria.'
    )

    @staticmethod
    def validar_competencia(competencia):
        valor = str(competencia or '').strip()
        if not re.fullmatch(r'\d{4}-\d{2}', valor):
            raise ValueError('Competência deve estar no formato YYYY-MM')

        ano, mes = [int(parte) for parte in valor.split('-')]
        if mes < 1 or mes > 12:
            raise ValueError('Mês da competência deve estar entre 1 e 12')

        return valor, ano, mes

    @staticmethod
    def _normalizar_decimal(valor, campo):
        if valor is None or valor == '':
            raise ValueError(f'{campo} é obrigatório')

        try:
            texto = str(valor).strip().replace('%', '').replace(' ', '').replace(',', '.')
            return Decimal(texto)
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f'{campo} deve ser numérico') from exc

    @staticmethod
    def valor_percentual_para_decimal(valor_percentual):
        percentual = IndiceTRService._normalizar_decimal(valor_percentual, 'valor_percentual')
        if percentual < 0:
            raise ValueError('valor_percentual não pode ser negativo')
        if percentual > IndiceTRService.VALOR_MAXIMO_PERCENTUAL:
            raise ValueError('valor_percentual não pode ser maior que 10% ao mês')

        return (percentual / Decimal('100')).quantize(
            IndiceTRService.QUANTIZADOR_DECIMAL,
            rounding=ROUND_HALF_UP,
        )

    @staticmethod
    def _to_dict(indice):
        valor_decimal = Decimal(str(indice.valor_decimal or 0))
        dados = indice.to_dict()
        dados['valor_percentual'] = float(
            (valor_decimal * Decimal('100')).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
        )
        dados['usada_em_financiamento'] = IndiceTRService.tr_usada_em_financiamento(indice.competencia)
        return dados

    @staticmethod
    def listar(ano=None, inicio=None, fim=None):
        query = IndiceTRMensal.query

        if ano:
            query = query.filter(IndiceTRMensal.ano == int(ano))

        if inicio:
            inicio, _, _ = IndiceTRService.validar_competencia(inicio)
            query = query.filter(IndiceTRMensal.competencia >= inicio)

        if fim:
            fim, _, _ = IndiceTRService.validar_competencia(fim)
            query = query.filter(IndiceTRMensal.competencia <= fim)

        return [
            IndiceTRService._to_dict(indice)
            for indice in query.order_by(IndiceTRMensal.competencia.desc()).all()
        ]

    @staticmethod
    def obter(competencia):
        competencia, _, _ = IndiceTRService.validar_competencia(competencia)
        return IndiceTRMensal.query.filter_by(competencia=competencia).first()

    @staticmethod
    def criar(competencia, valor_percentual, fonte='BACEN'):
        competencia, ano, mes = IndiceTRService.validar_competencia(competencia)
        if IndiceTRMensal.query.filter_by(competencia=competencia).first():
            raise ValueError(f'TR da competência {competencia} já cadastrada')

        indice = IndiceTRMensal(
            ano=ano,
            mes=mes,
            competencia=competencia,
            valor_decimal=IndiceTRService.valor_percentual_para_decimal(valor_percentual),
            fonte=fonte or 'BACEN',
        )
        db.session.add(indice)
        db.session.commit()
        return IndiceTRService._to_dict(indice)

    @staticmethod
    def editar(competencia, valor_percentual, fonte=None):
        competencia, _, _ = IndiceTRService.validar_competencia(competencia)
        indice = IndiceTRMensal.query.filter_by(competencia=competencia).first()
        if not indice:
            raise ValueError(f'TR da competência {competencia} não encontrada')

        if IndiceTRService.tr_usada_em_financiamento(competencia):
            raise ValueError(IndiceTRService.MSG_TR_USADA)

        indice.valor_decimal = IndiceTRService.valor_percentual_para_decimal(valor_percentual)
        if fonte is not None:
            indice.fonte = fonte or 'BACEN'
        indice.atualizado_em = datetime.utcnow()
        db.session.commit()
        return IndiceTRService._to_dict(indice)

    @staticmethod
    def tr_usada_em_financiamento(competencia):
        competencia, ano, mes = IndiceTRService.validar_competencia(competencia)
        inicio = date(ano, mes, 1)
        fim = date(ano + 1, 1, 1) if mes == 12 else date(ano, mes + 1, 1)

        return db.session.query(FinanciamentoParcela.id).join(
            Financiamento,
            FinanciamentoParcela.financiamento_id == Financiamento.id,
        ).filter(
            FinanciamentoParcela.data_vencimento >= inicio,
            FinanciamentoParcela.data_vencimento < fim,
            db.or_(
                db.and_(
                    func.upper(Financiamento.sistema_amortizacao) == 'SAC',
                    func.upper(Financiamento.indexador_saldo) == 'TR',
                ),
                Financiamento.modo_calculo_financiamento == 'caixa_sac_tr',
            ),
        ).first() is not None

    @staticmethod
    def importar_texto(texto, fonte='BACEN', sobrescrever=False):
        if not texto or not str(texto).strip():
            raise ValueError('texto é obrigatório')

        resultado = {
            'criados': 0,
            'atualizados': 0,
            'ignorados': 0,
            'erros': [],
        }

        for numero_linha, linha in enumerate(str(texto).splitlines(), 1):
            conteudo = linha.strip()
            if not conteudo:
                continue
            if conteudo.lower().startswith('competencia'):
                continue

            match = re.match(r'^(\d{4}-\d{2})\s*[;,]\s*(.+?)\s*$', conteudo)
            if not match:
                resultado['erros'].append({
                    'linha': numero_linha,
                    'conteudo': conteudo,
                    'erro': 'Linha deve estar no formato YYYY-MM;valor_percentual',
                })
                continue

            competencia, valor_percentual = match.groups()
            try:
                competencia, ano, mes = IndiceTRService.validar_competencia(competencia)
                valor_decimal = IndiceTRService.valor_percentual_para_decimal(valor_percentual)
                indice = IndiceTRMensal.query.filter_by(competencia=competencia).first()

                if indice:
                    if not sobrescrever:
                        resultado['ignorados'] += 1
                        continue
                    if IndiceTRService.tr_usada_em_financiamento(competencia):
                        raise ValueError(IndiceTRService.MSG_TR_USADA)
                    indice.valor_decimal = valor_decimal
                    indice.fonte = fonte or 'BACEN'
                    indice.atualizado_em = datetime.utcnow()
                    resultado['atualizados'] += 1
                    continue

                db.session.add(IndiceTRMensal(
                    ano=ano,
                    mes=mes,
                    competencia=competencia,
                    valor_decimal=valor_decimal,
                    fonte=fonte or 'BACEN',
                ))
                resultado['criados'] += 1
            except ValueError as exc:
                resultado['erros'].append({
                    'linha': numero_linha,
                    'conteudo': conteudo,
                    'erro': str(exc),
                })

        db.session.commit()
        return resultado

    @staticmethod
    def competencias_faltantes(inicio, fim):
        inicio, ano_inicio, mes_inicio = IndiceTRService.validar_competencia(inicio)
        fim, ano_fim, mes_fim = IndiceTRService.validar_competencia(fim)
        if inicio > fim:
            raise ValueError('Competência inicial deve ser menor ou igual à final')

        existentes = {
            competencia for (competencia,) in db.session.query(IndiceTRMensal.competencia)
            .filter(IndiceTRMensal.competencia >= inicio, IndiceTRMensal.competencia <= fim)
            .all()
        }

        faltantes = []
        ano = ano_inicio
        mes = mes_inicio
        while (ano, mes) <= (ano_fim, mes_fim):
            competencia = f'{ano}-{mes:02d}'
            if competencia not in existentes:
                faltantes.append(competencia)

            if mes == 12:
                ano += 1
                mes = 1
            else:
                mes += 1

        return faltantes
