from __future__ import annotations

from datetime import date, datetime

try:
    from backend.models import db, DespesaPrevista
    from backend.services.veiculo_uso_service import registrar_despesa_combustivel_confirmada
    from backend.models import DespesaPrevistaAcaoLog
    from backend.services.despesa_prevista_cascata_service import ajustar_ciclo_um_passo
except ImportError:
    from models import db, DespesaPrevista
    from services.veiculo_uso_service import registrar_despesa_combustivel_confirmada
    from models import DespesaPrevistaAcaoLog
    from services.despesa_prevista_cascata_service import ajustar_ciclo_um_passo


STATUS_PREVISTA = 'PREVISTA'
STATUS_CONFIRMADA = 'CONFIRMADA'
STATUS_ADIADA = 'ADIADA'
STATUS_IGNORADA = 'IGNORADA'

STATUS_FASE2_BLOQUEADOS = (STATUS_CONFIRMADA, STATUS_ADIADA, STATUS_IGNORADA)


def _parse_date(value) -> date | None:
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value)).date()
    except Exception:
        return None


def _primeiro_dia_mes(d: date) -> date:
    return d.replace(day=1)


def _assert_prevista(desp: DespesaPrevista) -> None:
    if desp.status != STATUS_PREVISTA:
        raise ValueError('Apenas despesas PREVISTA podem ser alteradas nesta fase')

    # Backfill defensivo (caso banco antigo ainda não tenha preenchido datas)
    if desp.data_original_prevista is None:
        desp.data_original_prevista = desp.data_prevista
    if desp.data_atual_prevista is None:
        desp.data_atual_prevista = desp.data_prevista


def confirmar(despesa_id: int) -> DespesaPrevista:
    desp = DespesaPrevista.query.get(despesa_id)
    if not desp:
        raise ValueError('Despesa prevista não encontrada')
    _assert_prevista(desp)

    desp.status = STATUS_CONFIRMADA
    db.session.add(desp)
    # FASE 3 (sensor passivo): se for combustível confirmado, atualiza km estimado do veículo incrementalmente
    registrar_despesa_combustivel_confirmada(desp)
    return desp


def ignorar(despesa_id: int) -> DespesaPrevista:
    desp = DespesaPrevista.query.get(despesa_id)
    if not desp:
        raise ValueError('Despesa prevista não encontrada')
    _assert_prevista(desp)

    desp.status = STATUS_IGNORADA
    db.session.add(desp)
    return desp


def adiar(despesa_id: int, nova_data, ajustar_ciclo: bool = False) -> tuple[DespesaPrevista, int | None]:
    desp = DespesaPrevista.query.get(despesa_id)
    if not desp:
        raise ValueError('Despesa prevista não encontrada')
    _assert_prevista(desp)

    nd = _parse_date(nova_data)
    if not nd:
        raise ValueError('nova_data inválida (use YYYY-MM-DD)')

    nd = _primeiro_dia_mes(nd)

    desp.status = STATUS_ADIADA
    desp.data_atual_prevista = nd
    desp.data_prevista = nd  # compatibilidade: espelha data_atual_prevista
    # data_original_prevista permanece intacta
    db.session.add(desp)

    criada_id = None
    if bool(ajustar_ciclo):
        resultado = ajustar_ciclo_um_passo(desp)
        criada_id = resultado.despesa_criada_id

    # Auditoria mínima
    log = DespesaPrevistaAcaoLog(
        despesa_prevista_id=desp.id,
        acao='ADIAR',
        ajustar_ciclo=bool(ajustar_ciclo),
        despesa_prevista_criada_id=criada_id
    )
    db.session.add(log)

    return desp, criada_id
