from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from math import ceil

from dateutil.relativedelta import relativedelta

try:
    from backend.models import db, Veiculo, VeiculoRegraManutencaoKm, DespesaPrevista
    from backend.services.veiculo_uso_service import calcular_resumo_uso
except ImportError:
    from models import db, Veiculo, VeiculoRegraManutencaoKm, DespesaPrevista
    from services.veiculo_uso_service import calcular_resumo_uso


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


@dataclass(frozen=True)
class ProximaManutencaoEstimativa:
    regra_id: int
    tipo_evento: str
    intervalo_km: int
    meses_intervalo: int | None
    custo_estimado: float
    categoria_id: int
    km_atual_estimado: float
    km_restante: float
    media_movel_km_mes: float
    meses_estimados: int | None
    data_prevista_estimada: str | None
    existe_evento: bool
    evento_existente_id: int | None
    evento_existente_status: str | None


def _buscar_evento_existente(veiculo_id: int, tipo_evento: str) -> DespesaPrevista | None:
    """
    Regra: não gerar nova se já existir PREVISTA/ADIADA/CONFIRMADA do mesmo tipo_evento.
    IGNORADA não bloqueia geração.
    """
    candidatos = DespesaPrevista.query.filter(
        DespesaPrevista.origem_tipo == 'VEICULO',
        DespesaPrevista.origem_id == veiculo_id,
        DespesaPrevista.status.in_(['PREVISTA', 'ADIADA', 'CONFIRMADA']),
    ).all()
    for d in candidatos:
        if _get_tipo_evento(d) == tipo_evento:
            return d
    return None


def _inferir_km_mes_projetado(v: Veiculo) -> float:
    """
    Uso projetado (modo simulação):
    - baseado em gasto mensal de combustível, preço médio e autonomia (km/L)
    - não exige histórico
    """
    try:
        valor_mensal = float(v.combustivel_valor_mensal or 0)
        preco_litro = float(v.preco_medio_combustivel or 0)
        autonomia = float(v.autonomia_km_l or 0)
    except Exception:
        return 0.0

    if valor_mensal <= 0 or preco_litro <= 0 or autonomia <= 0:
        return 0.0

    litros_mes = valor_mensal / preco_litro
    return max(0.0, litros_mes * autonomia)


def _calcular_km_mes_estimado(v: Veiculo, janela_meses: int) -> tuple[float, str, str]:
    """
    Prioridade:
    1) Histórico (média móvel via consumo)
    2) Projetado (combustível mensal + preço médio + autonomia)
    """
    uso = calcular_resumo_uso(v.id, janela_meses=janela_meses)
    media = float(uso.get('media_movel_km_mes') or 0)
    if media > 0:
        return media, 'HISTORICO', 'Baseado no uso estimado (histórico via consumo). Pode variar.'

    proj = _inferir_km_mes_projetado(v)
    if proj > 0:
        return proj, 'PROJETADO', 'Baseado em uso projetado (combustível mensal, preço médio e autonomia). Pode variar.'

    return 0.0, 'INDISPONIVEL', 'Sem dados suficientes para estimar uso mensal. Informe combustível mensal e preço médio, ou gere histórico.'


def _calcular_km_restante(intervalo_km: int, km_atual: float) -> float:
    """
    Estimativa simples (contratual):
    - Não é agenda, é aproximação racional.
    - Usa o km estimado acumulado e a regra (intervalo em km).
    """
    if not intervalo_km or intervalo_km <= 0:
        return 0.0
    if km_atual <= 0:
        return float(intervalo_km)
    try:
        mod = float(km_atual) % float(intervalo_km)
    except Exception:
        mod = 0.0
    if mod == 0:
        return 0.0
    return float(intervalo_km) - mod


def calcular_impacto_mensal_manutencao(veiculo_id: int, janela_meses: int = 3) -> dict:
    """
    Informativo: converte regras (km) em custo médio mensal esperado.
    - não cria DespesaPrevista
    - não altera estado
    """
    v = Veiculo.query.get(veiculo_id)
    if not v:
        raise ValueError('Veículo não encontrado')

    regras = VeiculoRegraManutencaoKm.query.filter_by(veiculo_id=veiculo_id, ativo=True).all()
    km_mes, fonte, observacao = _calcular_km_mes_estimado(v, janela_meses=janela_meses)

    total = 0.0
    fonte_impacto = 'INDISPONIVEL'
    observacao_impacto = None

    for r in regras:
        try:
            intervalo = float(r.intervalo_km or 0)
            custo = float(r.custo_estimado or 0)
            meses_intervalo = int(getattr(r, 'meses_intervalo', None)) if getattr(r, 'meses_intervalo', None) is not None else None
        except Exception:
            continue

        if custo <= 0:
            continue

        # Prioridade:
        # 1) por km (quando uso mensal estimado existe)
        # 2) por tempo (fallback informado, ex: a cada 8 meses)
        if km_mes > 0 and intervalo > 0:
            total += custo * (km_mes / intervalo)
            fonte_impacto = 'KM'
            continue

        if meses_intervalo and meses_intervalo > 0:
            total += custo / float(meses_intervalo)
            if fonte_impacto != 'KM':
                fonte_impacto = 'TEMPO'
            continue

    if fonte_impacto == 'KM':
        observacao_impacto = 'Impacto mensal estimado via km (uso estimado/projetado). Pode variar.'
    elif fonte_impacto == 'TEMPO':
        observacao_impacto = 'Impacto mensal estimado via intervalo informado (meses). Pode variar.'

    return {
        'veiculo_id': v.id,
        'janela_meses': janela_meses,
        'km_mes_estimado': km_mes,
        'fonte_uso': fonte,
        'observacao': observacao,
        'fonte_impacto': fonte_impacto,
        'observacao_impacto': observacao_impacto,
        'impacto_mensal_total': total,
        'total_regras_ativas': len(regras),
        'tipos_evento_regras': [r.tipo_evento for r in regras],
    }


def listar_estimativas(veiculo_id: int, janela_meses: int = 3) -> dict:
    v = Veiculo.query.get(veiculo_id)
    if not v:
        raise ValueError('Veículo não encontrado')

    regras = VeiculoRegraManutencaoKm.query.filter_by(veiculo_id=veiculo_id, ativo=True).order_by(
        VeiculoRegraManutencaoKm.id.asc()
    ).all()

    km_atual = float(v.km_estimado_acumulado or 0)
    km_mes, fonte_uso, obs_uso = _calcular_km_mes_estimado(v, janela_meses=janela_meses)

    items: list[dict] = []
    for r in regras:
        existente = _buscar_evento_existente(veiculo_id, r.tipo_evento)
        km_restante = _calcular_km_restante(int(r.intervalo_km), km_atual) if r.intervalo_km else 0.0
        meses = None
        data_est = None
        if km_mes > 0 and km_restante > 0:
            meses = int(ceil(km_restante / km_mes))
            data_est = _primeiro_dia_mes(date.today() + relativedelta(months=meses)).isoformat()
        elif km_mes > 0 and km_restante == 0:
            meses = 0
            data_est = _primeiro_dia_mes(date.today()).isoformat()

        items.append(ProximaManutencaoEstimativa(
            regra_id=r.id,
            tipo_evento=r.tipo_evento,
            intervalo_km=r.intervalo_km,
            meses_intervalo=int(getattr(r, 'meses_intervalo', None)) if getattr(r, 'meses_intervalo', None) is not None else None,
            custo_estimado=float(r.custo_estimado),
            categoria_id=r.categoria_id,
            km_atual_estimado=km_atual,
            km_restante=km_restante,
            media_movel_km_mes=km_mes,
            meses_estimados=meses,
            data_prevista_estimada=data_est,
            existe_evento=bool(existente),
            evento_existente_id=existente.id if existente else None,
            evento_existente_status=existente.status if existente else None,
        ).__dict__)

    impacto = calcular_impacto_mensal_manutencao(veiculo_id, janela_meses=janela_meses)
    return {
        'veiculo_id': v.id,
        'janela_meses': janela_meses,
        'observacao': obs_uso,
        'fonte_uso': fonte_uso,
        'km_mes_estimado': km_mes,
        'regras': [r.to_dict() for r in regras],
        'estimativas': items,
        'impacto_mensal_total': impacto.get('impacto_mensal_total', 0.0),
        'fonte_impacto': impacto.get('fonte_impacto'),
        'observacao_impacto': impacto.get('observacao_impacto'),
        'tipos_evento_regras': impacto.get('tipos_evento_regras', []),
    }


def gerar_despesa_prevista_por_regra(veiculo_id: int, regra_id: int, janela_meses: int = 3) -> DespesaPrevista | None:
    """
    Gera UMA despesa prevista por regra, sem cascata e sem múltiplas ocorrências futuras.
    """
    v = Veiculo.query.get(veiculo_id)
    if not v:
        raise ValueError('Veículo não encontrado')

    regra = VeiculoRegraManutencaoKm.query.filter_by(id=regra_id, veiculo_id=veiculo_id, ativo=True).first()
    if not regra:
        raise ValueError('Regra de manutenção não encontrada')

    existente = _buscar_evento_existente(veiculo_id, regra.tipo_evento)
    if existente:
        return None

    km_mes, _, _ = _calcular_km_mes_estimado(v, janela_meses=janela_meses)
    km_atual = float(v.km_estimado_acumulado or 0)

    if km_mes <= 0:
        # Sem uso suficiente para estimar data
        return None

    km_restante = _calcular_km_restante(int(regra.intervalo_km), km_atual)
    meses = int(ceil(km_restante / km_mes)) if km_mes > 0 else None
    data_calc = _primeiro_dia_mes(date.today() + relativedelta(months=meses or 0))

    desp = DespesaPrevista(
        origem_tipo='VEICULO',
        origem_id=veiculo_id,
        categoria_id=regra.categoria_id,
        data_prevista=data_calc,
        data_original_prevista=data_calc,
        data_atual_prevista=data_calc,
        valor_previsto=Decimal(str(regra.custo_estimado)),
        status='PREVISTA',
        metadata_json=json.dumps({
            'tipo_evento': regra.tipo_evento,
            'intervalo_km': regra.intervalo_km,
            'ciclo_id': None,
            'ordem_no_ciclo': None
        }, ensure_ascii=False)
    )
    db.session.add(desp)
    return desp
