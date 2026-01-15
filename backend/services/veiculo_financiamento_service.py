from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta

try:
    from backend.models import db, Veiculo, VeiculoFinanciamento, Categoria, DespesaPrevista, IndexadorMensal
    from backend.services.categoria_default import get_categoria_padrao_veiculos
except ImportError:
    from models import db, Veiculo, VeiculoFinanciamento, Categoria, DespesaPrevista, IndexadorMensal
    from services.categoria_default import get_categoria_padrao_veiculos


TIPO_EVENTO_PARCELA = 'PARCELA_FINANCIAMENTO'
TIPO_EVENTO_IOF = 'IOF_FINANCIAMENTO'


def _primeiro_dia_mes(d: date) -> date:
    return d.replace(day=1)


def _to_decimal(value) -> Decimal | None:
    if value is None or (isinstance(value, str) and value.strip() == ''):
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _to_int(value) -> int | None:
    try:
        if value is None:
            return None
        if isinstance(value, str) and value.strip() == '':
            return None
        return int(value)
    except Exception:
        return None


def _categoria_padrao_financiamento_id() -> int | None:
    return get_categoria_padrao_veiculos()


def _obter_indexador_percentual(nome: str | None, data_ref: date) -> Decimal:
    if not nome:
        return Decimal('0')
    data_mes = _primeiro_dia_mes(data_ref)
    idx = IndexadorMensal.query.filter_by(nome=nome, data_referencia=data_mes).first()
    return idx.valor if idx and idx.valor is not None else Decimal('0')


def _existe_parcela_na_competencia(veiculo_id: int, competencia: date) -> bool:
    """
    Evitar duplicidade quando existirem parcelas não-PREVISTA (confirmadas/adiadas/ignoradas).
    """
    candidatos = DespesaPrevista.query.filter(
        DespesaPrevista.origem_tipo == 'VEICULO',
        DespesaPrevista.origem_id == veiculo_id,
        DespesaPrevista.data_prevista == competencia,
    ).all()
    for d in candidatos:
        try:
            md = json.loads(getattr(d, 'metadata_json', None) or '{}') or {}
        except Exception:
            md = {}
        if md.get('tipo_evento') == TIPO_EVENTO_PARCELA:
            if d.status != 'PREVISTA':
                return True
    return False


def _existe_iof_na_competencia(veiculo_id: int, competencia: date) -> bool:
    candidatos = DespesaPrevista.query.filter(
        DespesaPrevista.origem_tipo == 'VEICULO',
        DespesaPrevista.origem_id == veiculo_id,
        DespesaPrevista.data_prevista == competencia,
    ).all()
    for d in candidatos:
        try:
            md = json.loads(getattr(d, 'metadata_json', None) or '{}') or {}
        except Exception:
            md = {}
        if md.get('tipo_evento') == TIPO_EVENTO_IOF and d.status != 'PREVISTA':
            return True
    return False


def _limpar_previstas_financiamento(veiculo_id: int) -> int:
    """
    Remove apenas despesas PREVISTAS de financiamento (parcelas + iof) para o veículo.
    Nunca toca em CONFIRMADAS/ADIADAS/IGNORADAS.
    """
    removidas = 0
    despesas = DespesaPrevista.query.filter(
        DespesaPrevista.origem_tipo == 'VEICULO',
        DespesaPrevista.origem_id == veiculo_id,
        DespesaPrevista.status == 'PREVISTA',
    ).all()
    for d in despesas:
        try:
            md = json.loads(getattr(d, 'metadata_json', None) or '{}') or {}
        except Exception:
            md = {}
        if md.get('tipo_evento') in (TIPO_EVENTO_PARCELA, TIPO_EVENTO_IOF):
            db.session.delete(d)
            removidas += 1
    return removidas


def upsert_financiamento(veiculo_id: int, payload: dict) -> dict:
    """
    Cria/atualiza financiamento projetivo e (re)gera DespesaPrevista de parcelas (e IOF).
    """
    v = Veiculo.query.get(veiculo_id)
    if not v:
        raise ValueError('Veículo não encontrado')

    valor_bem = _to_decimal(payload.get('valor_bem'))
    entrada = _to_decimal(payload.get('entrada')) or Decimal('0')
    numero_parcelas = _to_int(payload.get('numero_parcelas'))
    taxa_juros_mensal = _to_decimal(payload.get('taxa_juros_mensal'))
    indexador_tipo = (payload.get('indexador_tipo') or '').strip() or None
    iof_percentual = _to_decimal(payload.get('iof_percentual')) or Decimal('0')
    categoria_id = _categoria_padrao_financiamento_id()

    if valor_bem is None or valor_bem <= 0:
        raise ValueError('valor_bem é obrigatório e deve ser > 0')
    if entrada < 0:
        raise ValueError('entrada deve ser >= 0')
    if numero_parcelas is None or numero_parcelas < 24 or numero_parcelas > 72:
        raise ValueError('numero_parcelas deve estar entre 24 e 72')
    if taxa_juros_mensal is None or taxa_juros_mensal < Decimal('1.2') or taxa_juros_mensal > Decimal('3.5'):
        raise ValueError('taxa_juros_mensal deve estar entre 1.20 e 3.50 (% a.m.)')
    if iof_percentual < 0:
        raise ValueError('iof_percentual deve ser >= 0')

    valor_financiado = valor_bem - entrada
    if valor_financiado <= 0:
        raise ValueError('valor_financiado deve ser > 0 (valor_bem - entrada)')

    iof_valor = (valor_financiado * iof_percentual) / Decimal('100')

    fin = VeiculoFinanciamento.query.filter_by(veiculo_id=veiculo_id).first()
    if not fin:
        fin = VeiculoFinanciamento(veiculo_id=veiculo_id)
        db.session.add(fin)

    fin.valor_bem = valor_bem
    fin.entrada = entrada
    fin.valor_financiado = valor_financiado
    fin.numero_parcelas = numero_parcelas
    fin.taxa_juros_mensal = taxa_juros_mensal
    fin.indexador_tipo = indexador_tipo
    fin.iof_percentual = iof_percentual
    fin.iof_valor = iof_valor
    fin.categoria_id = categoria_id

    # (Re)gerar despesas previstas (somente PREVISTA)
    _limpar_previstas_financiamento(veiculo_id)

    inicio = v.data_inicio or date.today()
    if inicio < date.today():
        inicio = date.today()
    competencia = _primeiro_dia_mes(inicio)

    # IOF (uma vez)
    if iof_valor > 0 and categoria_id and not _existe_iof_na_competencia(veiculo_id, competencia):
        desp_iof = DespesaPrevista(
            origem_tipo='VEICULO',
            origem_id=veiculo_id,
            categoria_id=categoria_id,
            data_prevista=competencia,
            data_original_prevista=competencia,
            data_atual_prevista=competencia,
            valor_previsto=iof_valor,
            status='PREVISTA',
            metadata_json=json.dumps({'tipo_evento': TIPO_EVENTO_IOF, 'financiamento_id': fin.id}, ensure_ascii=False),
        )
        db.session.add(desp_iof)

    amort_base = valor_financiado / Decimal(str(numero_parcelas))
    saldo = valor_financiado
    total_parcelas = Decimal('0')

    for i in range(1, numero_parcelas + 1):
        comp = _primeiro_dia_mes(competencia + relativedelta(months=i - 1))

        if _existe_parcela_na_competencia(veiculo_id, comp):
            saldo = saldo - amort_base
            continue

        juros_mes = saldo * (taxa_juros_mensal / Decimal('100'))
        idx_pct = _obter_indexador_percentual(indexador_tipo, comp)
        correcao_mes = saldo * (idx_pct / Decimal('100'))
        parcela = amort_base + juros_mes + correcao_mes

        desp = DespesaPrevista(
            origem_tipo='VEICULO',
            origem_id=veiculo_id,
            categoria_id=categoria_id,
            data_prevista=comp,
            data_original_prevista=comp,
            data_atual_prevista=comp,
            valor_previsto=parcela,
            status='PREVISTA',
            metadata_json=json.dumps({
                'tipo_evento': TIPO_EVENTO_PARCELA,
                'financiamento_id': fin.id,
                'numero_parcela': i,
                'total_parcelas': numero_parcelas,
                'amortizacao_base': float(amort_base),
                'juros_mes': float(juros_mes),
                'correcao_mes': float(correcao_mes),
                'taxa_juros_mensal': float(taxa_juros_mensal),
                'indexador_tipo': indexador_tipo,
                'indexador_mes_percentual': float(idx_pct),
            }, ensure_ascii=False),
        )
        db.session.add(desp)

        total_parcelas += parcela
        saldo = saldo - amort_base

    fin.custo_total_financiamento = total_parcelas + iof_valor
    db.session.add(fin)
    db.session.flush()

    valor_medio_parcela = float((total_parcelas / Decimal(str(numero_parcelas))) if numero_parcelas else Decimal('0'))

    return {
        'financiamento': fin.to_dict(),
        'resumo': {
            'valor_medio_parcela': valor_medio_parcela,
            'custo_total_financiamento': float(fin.custo_total_financiamento or 0),
            'iof_valor': float(fin.iof_valor or 0),
            'iof_percentual': float(fin.iof_percentual or 0),
        }
    }


def obter_financiamento(veiculo_id: int) -> VeiculoFinanciamento | None:
    return VeiculoFinanciamento.query.filter_by(veiculo_id=veiculo_id).first()


def remover_financiamento(veiculo_id: int) -> int:
    fin = VeiculoFinanciamento.query.filter_by(veiculo_id=veiculo_id).first()
    if not fin:
        return 0
    _limpar_previstas_financiamento(veiculo_id)
    db.session.delete(fin)
    return 1
