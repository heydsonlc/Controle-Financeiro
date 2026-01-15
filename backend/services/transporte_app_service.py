from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from sqlalchemy import func

try:
    from backend.models import db, DespesaPrevista
    from backend.services.categoria_default import get_categoria_padrao_veiculos
except ImportError:
    from models import db, DespesaPrevista
    from services.categoria_default import get_categoria_padrao_veiculos


ORIGEM_TIPO_TRANSPORTE_APP = 'TRANSPORTE_APP'
TIPO_EVENTO_TRANSPORTE_APP = 'TRANSPORTE_APP'


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


def _to_float(value) -> float | None:
    if value is None or (isinstance(value, str) and value.strip() == ''):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _get_tipo_evento(desp: DespesaPrevista) -> str | None:
    raw = getattr(desp, 'metadata_json', None)
    if not raw:
        return None
    try:
        return (json.loads(raw) or {}).get('tipo_evento')
    except Exception:
        return None


def _next_origem_id() -> int:
    max_id = db.session.query(func.max(DespesaPrevista.origem_id)).filter(
        DespesaPrevista.origem_tipo == ORIGEM_TIPO_TRANSPORTE_APP
    ).scalar()
    try:
        return int(max_id or 0) + 1
    except Exception:
        return 1


@dataclass(frozen=True)
class TransporteAppConfig:
    nome: str
    km_mensal_estimado: Decimal
    preco_medio_por_km: Decimal
    perfis: list[dict]
    corridas_mes: int | None
    km_medio_por_corrida: Decimal | None

    @property
    def valor_mensal(self) -> Decimal:
        total_km = self.km_mensal_estimado
        base_preco = self.preco_medio_por_km

        km_perfis = Decimal('0')
        valor_perfis = Decimal('0')
        for p in self.perfis or []:
            km = _to_decimal(p.get('km_mensal'))
            preco = _to_decimal(p.get('preco_medio_por_km'))
            if not km or km <= 0:
                continue
            if not preco or preco <= 0:
                preco = base_preco
            km_perfis += km
            valor_perfis += km * preco

        restante = total_km - km_perfis
        if restante < 0:
            restante = Decimal('0')

        return valor_perfis + (restante * base_preco)


def parse_config(payload: dict) -> TransporteAppConfig:
    nome = (payload.get('nome') or '').strip() or 'Transporte por App'
    km_mensal_estimado = _to_decimal(payload.get('km_mensal_estimado'))
    preco_medio_por_km = _to_decimal(payload.get('preco_medio_por_km'))

    if km_mensal_estimado is None or km_mensal_estimado <= 0:
        raise ValueError('km_mensal_estimado é obrigatório e deve ser > 0')
    if preco_medio_por_km is None or preco_medio_por_km <= 0:
        raise ValueError('preco_medio_por_km é obrigatório e deve ser > 0')

    perfis_raw = payload.get('perfis') or []
    if isinstance(perfis_raw, str):
        try:
            perfis_raw = json.loads(perfis_raw) or []
        except Exception:
            perfis_raw = []

    perfis: list[dict] = []
    soma_km = Decimal('0')
    if isinstance(perfis_raw, list):
        for p in perfis_raw:
            if not isinstance(p, dict):
                continue
            nome_p = (p.get('nome') or '').strip() or 'Perfil'
            km_p = _to_decimal(p.get('km_mensal'))
            preco_p = _to_decimal(p.get('preco_medio_por_km'))
            if km_p is None or km_p <= 0:
                continue
            if preco_p is None or preco_p <= 0:
                preco_p = preco_medio_por_km
            soma_km += km_p
            perfis.append({
                'nome': nome_p,
                'km_mensal': float(km_p),
                'preco_medio_por_km': float(preco_p),
            })

    if soma_km > km_mensal_estimado:
        raise ValueError('A soma de km_mensal dos perfis deve ser <= km_mensal_estimado')

    corridas_mes = _to_int(payload.get('corridas_mes'))
    km_medio_por_corrida = _to_decimal(payload.get('km_medio_por_corrida'))

    return TransporteAppConfig(
        nome=nome,
        km_mensal_estimado=km_mensal_estimado,
        preco_medio_por_km=preco_medio_por_km,
        perfis=perfis,
        corridas_mes=corridas_mes,
        km_medio_por_corrida=km_medio_por_corrida,
    )


def gerar_projecoes_transporte_app(origem_id: int, config: TransporteAppConfig, meses_futuros: int = 12) -> list[DespesaPrevista]:
    if meses_futuros < 1:
        meses_futuros = 1

    inicio_mes = _primeiro_dia_mes(date.today())
    fim_exclusivo = _primeiro_dia_mes(inicio_mes + relativedelta(months=meses_futuros))

    existentes = DespesaPrevista.query.filter(
        DespesaPrevista.origem_tipo == ORIGEM_TIPO_TRANSPORTE_APP,
        DespesaPrevista.origem_id == origem_id,
        DespesaPrevista.data_prevista >= inicio_mes,
        DespesaPrevista.data_prevista < fim_exclusivo,
    ).all()

    bloqueadas = set()
    for desp in existentes:
        if _get_tipo_evento(desp) != TIPO_EVENTO_TRANSPORTE_APP:
            continue
        if desp.status and desp.status != 'PREVISTA':
            d1 = getattr(desp, 'data_original_prevista', None) or desp.data_prevista
            d2 = getattr(desp, 'data_atual_prevista', None) or desp.data_prevista
            if d1 and inicio_mes <= d1 < fim_exclusivo:
                bloqueadas.add(d1)
            if d2 and inicio_mes <= d2 < fim_exclusivo:
                bloqueadas.add(d2)

    for desp in existentes:
        if desp.status == 'PREVISTA' and _get_tipo_evento(desp) == TIPO_EVENTO_TRANSPORTE_APP:
            db.session.delete(desp)

    categoria_id = get_categoria_padrao_veiculos()
    criadas: list[DespesaPrevista] = []

    data_ref = inicio_mes
    valor_mensal = config.valor_mensal

    while data_ref < fim_exclusivo:
        if data_ref in bloqueadas:
            data_ref = _primeiro_dia_mes(data_ref + relativedelta(months=1))
            continue

        md = {
            'tipo_evento': TIPO_EVENTO_TRANSPORTE_APP,
            'caminho': {
                'nome': config.nome,
                'km_mensal_estimado': float(config.km_mensal_estimado),
                'preco_medio_por_km': float(config.preco_medio_por_km),
                'perfis': config.perfis,
                'corridas_mes': config.corridas_mes,
                'km_medio_por_corrida': float(config.km_medio_por_corrida) if config.km_medio_por_corrida is not None else None,
            },
            'calculo': {
                'valor_mensal': float(valor_mensal),
                'base': 'KM',
            },
            'ciclo_id': None,
            'ordem_no_ciclo': None,
        }

        desp = DespesaPrevista(
            origem_tipo=ORIGEM_TIPO_TRANSPORTE_APP,
            origem_id=origem_id,
            categoria_id=categoria_id,
            data_prevista=data_ref,
            data_original_prevista=data_ref,
            data_atual_prevista=data_ref,
            valor_previsto=valor_mensal,
            status='PREVISTA',
            metadata_json=json.dumps(md, ensure_ascii=False),
        )
        db.session.add(desp)
        criadas.append(desp)
        data_ref = _primeiro_dia_mes(data_ref + relativedelta(months=1))

    return criadas


def listar_caminhos_transporte_app() -> list[dict]:
    origem_ids = db.session.query(DespesaPrevista.origem_id).filter(
        DespesaPrevista.origem_tipo == ORIGEM_TIPO_TRANSPORTE_APP
    ).distinct().all()
    ids = [int(x[0]) for x in origem_ids if x and x[0] is not None]

    caminhos: list[dict] = []
    for oid in sorted(ids, reverse=True):
        ultimo = DespesaPrevista.query.filter(
            DespesaPrevista.origem_tipo == ORIGEM_TIPO_TRANSPORTE_APP,
            DespesaPrevista.origem_id == oid,
        ).order_by(DespesaPrevista.id.desc()).first()
        if not ultimo:
            continue
        try:
            md = json.loads(getattr(ultimo, 'metadata_json', None) or '{}') or {}
        except Exception:
            md = {}
        caminho = md.get('caminho') or {}
        nome = (caminho.get('nome') or f'Caminho {oid}').strip()
        km = _to_float(caminho.get('km_mensal_estimado')) or 0.0
        preco = _to_float(caminho.get('preco_medio_por_km')) or 0.0
        valor = _to_float(md.get('calculo', {}).get('valor_mensal')) or _to_float(getattr(ultimo, 'valor_previsto', None)) or 0.0
        caminhos.append({
            'id': oid,
            'nome': nome,
            'km_mensal_estimado': km,
            'preco_medio_por_km': preco,
            'valor_mensal': valor,
        })
    return caminhos


def obter_config_transporte_app(origem_id: int) -> dict | None:
    ultimo = DespesaPrevista.query.filter(
        DespesaPrevista.origem_tipo == ORIGEM_TIPO_TRANSPORTE_APP,
        DespesaPrevista.origem_id == origem_id,
    ).order_by(DespesaPrevista.id.desc()).first()
    if not ultimo:
        return None
    try:
        md = json.loads(getattr(ultimo, 'metadata_json', None) or '{}') or {}
    except Exception:
        md = {}
    return md.get('caminho') or {}


def criar_caminho_transporte_app(payload: dict, meses_futuros: int = 12) -> int:
    origem_id = _next_origem_id()
    config = parse_config(payload)
    gerar_projecoes_transporte_app(origem_id, config, meses_futuros=meses_futuros)
    return origem_id


def atualizar_caminho_transporte_app(origem_id: int, payload: dict, meses_futuros: int = 12) -> int:
    config = parse_config(payload)
    gerar_projecoes_transporte_app(origem_id, config, meses_futuros=meses_futuros)
    return origem_id

