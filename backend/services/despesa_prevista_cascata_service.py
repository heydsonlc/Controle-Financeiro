from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from math import ceil

from dateutil.relativedelta import relativedelta

try:
    from backend.models import (
        db,
        DespesaPrevista,
        Veiculo,
        VeiculoRegraManutencaoKm,
        VeiculoCicloManutencao,
    )
    from backend.services.veiculo_uso_service import calcular_resumo_uso
    from backend.services.categoria_default import get_categoria_padrao_veiculos
except ImportError:
    from models import db, DespesaPrevista, Veiculo, VeiculoRegraManutencaoKm, VeiculoCicloManutencao
    from services.veiculo_uso_service import calcular_resumo_uso
    from services.categoria_default import get_categoria_padrao_veiculos


EVENTOS_ANUAIS_MVP = ('IPVA', 'SEGURO', 'LICENCIAMENTO')


@dataclass(frozen=True)
class AjusteCicloResultado:
    ciclo_id: int | None
    despesa_criada_id: int | None


def _primeiro_dia_mes(d: date) -> date:
    return d.replace(day=1)


def _get_metadata(desp: DespesaPrevista) -> dict:
    raw = getattr(desp, 'metadata_json', None)
    if not raw:
        return {}
    try:
        return json.loads(raw) or {}
    except Exception:
        return {}


def _set_metadata(desp: DespesaPrevista, md: dict) -> None:
    desp.metadata_json = json.dumps(md, ensure_ascii=False)


def _get_tipo_evento(desp: DespesaPrevista) -> str | None:
    return _get_metadata(desp).get('tipo_evento')


def _buscar_regra_km(veiculo_id: int, tipo_evento: str) -> VeiculoRegraManutencaoKm | None:
    return VeiculoRegraManutencaoKm.query.filter_by(
        veiculo_id=veiculo_id,
        tipo_evento=tipo_evento,
        ativo=True
    ).first()


def _evento_elegivel(desp: DespesaPrevista) -> tuple[bool, str | None, VeiculoRegraManutencaoKm | None]:
    if desp.origem_tipo != 'VEICULO':
        return False, None, None

    tipo = _get_tipo_evento(desp)
    if not tipo:
        return False, None, None

    if tipo in EVENTOS_ANUAIS_MVP or tipo == 'COMBUSTIVEL':
        return False, tipo, None

    regra = _buscar_regra_km(desp.origem_id, tipo)
    if not regra:
        return False, tipo, None

    return True, tipo, regra


def _obter_ou_criar_ciclo(veiculo_id: int, tipo_evento: str, regra: VeiculoRegraManutencaoKm) -> VeiculoCicloManutencao:
    ciclo = VeiculoCicloManutencao.query.filter_by(veiculo_id=veiculo_id, tipo_evento=tipo_evento).first()
    if ciclo:
        return ciclo

    ciclo = VeiculoCicloManutencao(
        veiculo_id=veiculo_id,
        tipo_evento=tipo_evento,
        regra_id=regra.id,
        intervalo_km=regra.intervalo_km
    )
    db.session.add(ciclo)
    db.session.flush()  # obter id sem commit
    return ciclo


def _proxima_ordem_ciclo(ciclo_id: int) -> int:
    despesas = DespesaPrevista.query.filter(
        DespesaPrevista.origem_tipo == 'VEICULO',
        DespesaPrevista.status.in_(['PREVISTA', 'ADIADA', 'CONFIRMADA', 'IGNORADA']),
    ).all()
    max_ord = 0
    for d in despesas:
        md = _get_metadata(d)
        if md.get('ciclo_id') != ciclo_id:
            continue
        try:
            o = int(md.get('ordem_no_ciclo') or 0)
        except Exception:
            o = 0
        max_ord = max(max_ord, o)
    return max_ord + 1 if max_ord > 0 else 1


def _existe_evento_futuro_bloqueante(veiculo_id: int, tipo_evento: str, base: date, excluir_id: int | None = None) -> bool:
    """
    Não criar próxima se já existe outra do mesmo tipo_evento com status PREVISTA/ADIADA
    (e também CONFIRMADA no futuro) a partir do mês base.
    """
    candidatos = DespesaPrevista.query.filter(
        DespesaPrevista.origem_tipo == 'VEICULO',
        DespesaPrevista.origem_id == veiculo_id,
        DespesaPrevista.status.in_(['PREVISTA', 'ADIADA', 'CONFIRMADA']),
        DespesaPrevista.data_prevista >= _primeiro_dia_mes(base),
    ).all()
    for d in candidatos:
        if excluir_id and d.id == excluir_id:
            continue
        if _get_tipo_evento(d) == tipo_evento:
            return True
    return False


def ajustar_ciclo_um_passo(despesa_adiada: DespesaPrevista, janela_meses: int = 3) -> AjusteCicloResultado:
    """
    Ajuste consciente (1 passo):
    - Garante ciclo e associa (ciclo_id, ordem_no_ciclo) na despesa adiada.
    - Gera apenas a PRÓXIMA ocorrência estimada, sem tocar em outras despesas.
    """
    elegivel, tipo_evento, regra = _evento_elegivel(despesa_adiada)
    if not elegivel or not tipo_evento or not regra:
        return AjusteCicloResultado(ciclo_id=None, despesa_criada_id=None)

    veiculo = Veiculo.query.get(despesa_adiada.origem_id)
    if not veiculo:
        return AjusteCicloResultado(ciclo_id=None, despesa_criada_id=None)

    ciclo = _obter_ou_criar_ciclo(veiculo.id, tipo_evento, regra)

    md = _get_metadata(despesa_adiada)
    if not md.get('ciclo_id'):
        md['ciclo_id'] = ciclo.id
    if not md.get('ordem_no_ciclo'):
        md['ordem_no_ciclo'] = _proxima_ordem_ciclo(ciclo.id)
    _set_metadata(despesa_adiada, md)
    db.session.add(despesa_adiada)

    # Calcular próxima ocorrência a partir do novo "marco" (data adiada)
    uso = calcular_resumo_uso(veiculo.id, janela_meses=janela_meses)
    media = float(uso.get('media_movel_km_mes') or 0)
    if media <= 0:
        return AjusteCicloResultado(ciclo_id=ciclo.id, despesa_criada_id=None)

    meses = int(ceil(float(regra.intervalo_km) / media)) if regra.intervalo_km else None
    if meses is None:
        return AjusteCicloResultado(ciclo_id=ciclo.id, despesa_criada_id=None)

    base = despesa_adiada.data_atual_prevista or despesa_adiada.data_prevista
    data_prox = _primeiro_dia_mes(base + relativedelta(months=meses))

    if _existe_evento_futuro_bloqueante(veiculo.id, tipo_evento, data_prox, excluir_id=despesa_adiada.id):
        return AjusteCicloResultado(ciclo_id=ciclo.id, despesa_criada_id=None)

    desp_nova = DespesaPrevista(
        origem_tipo='VEICULO',
        origem_id=veiculo.id,
        categoria_id=get_categoria_padrao_veiculos(),
        data_prevista=data_prox,
        data_original_prevista=data_prox,
        data_atual_prevista=data_prox,
        valor_previsto=Decimal(str(regra.custo_estimado)),
        status='PREVISTA',
        metadata_json=json.dumps({
            'tipo_evento': tipo_evento,
            'ciclo_id': ciclo.id,
            'ordem_no_ciclo': int(md.get('ordem_no_ciclo')) + 1,
            'intervalo_km': regra.intervalo_km,
        }, ensure_ascii=False)
    )
    db.session.add(desp_nova)
    db.session.flush()

    return AjusteCicloResultado(ciclo_id=ciclo.id, despesa_criada_id=desp_nova.id)
