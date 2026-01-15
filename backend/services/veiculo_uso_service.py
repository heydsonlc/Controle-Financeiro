from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal

from dateutil.relativedelta import relativedelta

try:
    from backend.models import db, Veiculo, DespesaPrevista
except ImportError:
    from models import db, Veiculo, DespesaPrevista


def _to_decimal(value) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _primeiro_dia_mes(d: date) -> date:
    return d.replace(day=1)


def _get_tipo_evento(desp: DespesaPrevista) -> str | None:
    raw = getattr(desp, 'metadata_json', None)
    if not raw:
        return None
    try:
        return (json.loads(raw) or {}).get('tipo_evento')
    except Exception:
        return None


def _inferir_litros(veiculo: Veiculo, desp: DespesaPrevista) -> Decimal | None:
    """
    FASE 3: se não há litros armazenados, inferir por valor / preco_medio_combustivel do veículo.
    """
    # Caso futuro: litros explícitos em metadata (se existir, respeitar)
    raw = getattr(desp, 'metadata_json', None)
    if raw:
        try:
            md = json.loads(raw) or {}
            litros = md.get('litros_abastecidos')
            litros_dec = _to_decimal(litros)
            if litros_dec and litros_dec > 0:
                return litros_dec
        except Exception:
            pass

    preco = _to_decimal(getattr(veiculo, 'preco_medio_combustivel', None))
    if not preco or preco <= 0:
        return None

    valor = _to_decimal(getattr(desp, 'valor_previsto', None))
    if not valor or valor <= 0:
        return None

    return (valor / preco)


def _inferir_km(veiculo: Veiculo, desp: DespesaPrevista) -> Decimal | None:
    autonomia = _to_decimal(getattr(veiculo, 'autonomia_km_l', None))
    if not autonomia or autonomia <= 0:
        return None

    litros = _inferir_litros(veiculo, desp)
    if not litros or litros <= 0:
        return None

    return litros * autonomia


def registrar_despesa_combustivel_confirmada(desp: DespesaPrevista) -> Decimal:
    """
    Atualiza incremento de km estimado acumulado SOMENTE para despesas de combustível confirmadas.
    Não altera outras despesas e não recalcula histórico.
    """
    if desp.origem_tipo != 'VEICULO':
        return Decimal('0')
    if desp.status != 'CONFIRMADA':
        return Decimal('0')
    if _get_tipo_evento(desp) != 'COMBUSTIVEL':
        return Decimal('0')

    veiculo = Veiculo.query.get(desp.origem_id)
    if not veiculo:
        return Decimal('0')

    last_id = getattr(veiculo, 'km_estimado_ultimo_despesa_prevista_id', None)
    if last_id is not None and desp.id <= int(last_id):
        return Decimal('0')

    km = _inferir_km(veiculo, desp)
    if not km or km <= 0:
        # Sem dados suficientes (ex: preço médio não configurado); não avança o cursor
        return Decimal('0')

    atual = _to_decimal(getattr(veiculo, 'km_estimado_acumulado', None)) or Decimal('0')
    veiculo.km_estimado_acumulado = atual + km
    veiculo.km_estimado_ultimo_despesa_prevista_id = desp.id
    veiculo.km_estimado_ultimo_calculo_em = datetime.utcnow()

    db.session.add(veiculo)
    return km


def calcular_resumo_uso(veiculo_id: int, janela_meses: int = 3) -> dict:
    """
    Retorna estatísticas informativas (não altera histórico):
    - km estimado por mês (últimos N meses)
    - média móvel dos últimos N meses
    """
    v = Veiculo.query.get(veiculo_id)
    if not v:
        raise ValueError('Veículo não encontrado')

    if janela_meses < 1:
        janela_meses = 1
    if janela_meses > 12:
        janela_meses = 12

    hoje = date.today()
    fim_exclusivo = _primeiro_dia_mes(hoje + relativedelta(months=1))
    inicio = _primeiro_dia_mes(fim_exclusivo - relativedelta(months=janela_meses))

    despesas = DespesaPrevista.query.filter(
        DespesaPrevista.origem_tipo == 'VEICULO',
        DespesaPrevista.origem_id == veiculo_id,
        DespesaPrevista.status == 'CONFIRMADA',
        DespesaPrevista.data_prevista >= inicio,
        DespesaPrevista.data_prevista < fim_exclusivo,
    ).all()

    km_por_mes: dict[str, float] = {}
    soma = Decimal('0')

    for desp in despesas:
        if _get_tipo_evento(desp) != 'COMBUSTIVEL':
            continue
        km = _inferir_km(v, desp)
        if not km or km <= 0:
            continue
        chave = (getattr(desp, 'data_atual_prevista', None) or desp.data_prevista).strftime('%Y-%m')
        km_por_mes[chave] = float(Decimal(str(km_por_mes.get(chave, 0))) + km)
        soma += km

    media = float((soma / Decimal(str(janela_meses))) if janela_meses else Decimal('0'))

    return {
        'veiculo_id': v.id,
        'km_estimado_acumulado': float(v.km_estimado_acumulado or 0),
        'km_estimado_ultimo_calculo_em': v.km_estimado_ultimo_calculo_em.isoformat() if v.km_estimado_ultimo_calculo_em else None,
        'janela_meses': janela_meses,
        'km_por_mes': km_por_mes,
        'media_movel_km_mes': media,
        'observacao': 'Estimativa baseada em consumo. Pode variar.',
        'preco_medio_combustivel': float(v.preco_medio_combustivel) if v.preco_medio_combustivel else None,
        'autonomia_km_l': float(v.autonomia_km_l) if v.autonomia_km_l else None,
    }

