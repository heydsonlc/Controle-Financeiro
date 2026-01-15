from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta

try:
    from backend.models import db, Veiculo, Categoria, DespesaPrevista
    from backend.services.categoria_default import get_categoria_padrao_veiculos
except ImportError:
    from models import db, Veiculo, Categoria, DespesaPrevista
    from services.categoria_default import get_categoria_padrao_veiculos


EVENTOS_MVP = ('COMBUSTIVEL', 'IPVA', 'SEGURO', 'LICENCIAMENTO')


def _primeiro_dia_mes(d: date) -> date:
    return d.replace(day=1)


def _to_decimal(value) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _get_tipo_evento(desp: DespesaPrevista) -> str | None:
    if not getattr(desp, 'metadata_json', None):
        return None
    try:
        return (json.loads(desp.metadata_json) or {}).get('tipo_evento')
    except Exception:
        return None


def _categoria_por_nomes_preferidos(nomes: list[str]) -> Categoria | None:
    for nome in nomes:
        cat = Categoria.query.filter(Categoria.nome.ilike(nome)).first()
        if cat:
            return cat
    return None


def aplicar_defaults_categorias_veiculo(veiculo: Veiculo) -> None:
    """
    Preenche categoria_*_id quando o usuário não informou, usando categorias existentes.
    Nunca cria categorias novas.
    """
    # Ajuste final: o módulo de veículos usa categoria padrão única ("Transporte").
    categoria_id = get_categoria_padrao_veiculos()
    veiculo.categoria_combustivel_id = categoria_id
    veiculo.ipva_categoria_id = categoria_id
    veiculo.seguro_categoria_id = categoria_id
    veiculo.licenciamento_categoria_id = categoria_id


def gerar_projecoes_mvp(veiculo: Veiculo, meses_futuros: int = 12) -> list[DespesaPrevista]:
    """
    Gera (ou substitui) despesas previstas do MVP para um veículo.
    Nunca cria lançamentos reais (ItemDespesa/Conta/LancamentoAgregado).
    """
    if meses_futuros < 1:
        meses_futuros = 1

    inicio = veiculo.data_inicio or date.today()
    if inicio < date.today():
        inicio = date.today()

    inicio_mes = _primeiro_dia_mes(inicio)
    fim_exclusivo = _primeiro_dia_mes(inicio_mes + relativedelta(months=meses_futuros))

    # Remover projeções MVP no intervalo (idempotência simples)
    # Regra de blindagem: só remove PREVISTA (não toca em futuros status como ADIADA/CONFIRMADA).
    existentes = DespesaPrevista.query.filter(
        DespesaPrevista.origem_tipo == 'VEICULO',
        DespesaPrevista.origem_id == veiculo.id,
        DespesaPrevista.data_prevista >= inicio_mes,
        DespesaPrevista.data_prevista < fim_exclusivo,
    ).all()

    # Blindagem adicional (FASE 2):
    # - Não recriar PREVISTA quando o usuário já interagiu (CONFIRMADA/ADIADA/IGNORADA),
    #   evitando "ressuscitar" previsões que foram adiadas/ignoradas.
    bloqueadas = set()
    for desp in existentes:
        tipo_evento = _get_tipo_evento(desp)
        if tipo_evento not in EVENTOS_MVP:
            continue
        if desp.status and desp.status != 'PREVISTA':
            d1 = getattr(desp, 'data_original_prevista', None) or desp.data_prevista
            d2 = getattr(desp, 'data_atual_prevista', None) or desp.data_prevista
            if d1 and inicio_mes <= d1 < fim_exclusivo:
                bloqueadas.add((tipo_evento, d1))
            if d2 and inicio_mes <= d2 < fim_exclusivo:
                bloqueadas.add((tipo_evento, d2))

    for desp in existentes:
        if desp.status == 'PREVISTA' and _get_tipo_evento(desp) in EVENTOS_MVP:
            db.session.delete(desp)

    criadas: list[DespesaPrevista] = []

    categoria_padrao_id = get_categoria_padrao_veiculos()

    # Combustível mensal
    valor_mensal = _to_decimal(getattr(veiculo, 'combustivel_valor_mensal', None))
    if valor_mensal and valor_mensal > 0:
        data_ref = inicio_mes
        while data_ref < fim_exclusivo:
            if ('COMBUSTIVEL', data_ref) in bloqueadas:
                data_ref = _primeiro_dia_mes(data_ref + relativedelta(months=1))
                continue
            desp = DespesaPrevista(
                origem_tipo='VEICULO',
                origem_id=veiculo.id,
                categoria_id=categoria_padrao_id,
                data_prevista=data_ref,
                data_original_prevista=data_ref,
                data_atual_prevista=data_ref,
                valor_previsto=valor_mensal,
                status='PREVISTA',
                metadata_json=json.dumps(
                    {'tipo_evento': 'COMBUSTIVEL', 'ciclo_id': None, 'ordem_no_ciclo': None},
                    ensure_ascii=False
                ),
            )
            db.session.add(desp)
            criadas.append(desp)
            data_ref = _primeiro_dia_mes(data_ref + relativedelta(months=1))

    # Eventos anuais com mês fixo
    eventos_anuais = [
        ('IPVA', veiculo.ipva_mes, veiculo.ipva_valor),
        ('SEGURO', veiculo.seguro_mes, veiculo.seguro_valor),
        ('LICENCIAMENTO', veiculo.licenciamento_mes, veiculo.licenciamento_valor),
    ]

    ano_inicio = inicio_mes.year
    ano_fim = (fim_exclusivo - relativedelta(days=1)).year
    for tipo_evento, mes_evento, valor_evento in eventos_anuais:
        valor_dec = _to_decimal(valor_evento)
        if not (mes_evento and valor_dec and valor_dec > 0):
            continue
        if mes_evento < 1 or mes_evento > 12:
            continue

        for ano in range(ano_inicio, ano_fim + 1):
            d = date(ano, int(mes_evento), 1)
            if d < inicio_mes or d >= fim_exclusivo:
                continue
            if (tipo_evento, d) in bloqueadas:
                continue
            desp = DespesaPrevista(
                origem_tipo='VEICULO',
                origem_id=veiculo.id,
                categoria_id=categoria_padrao_id,
                data_prevista=d,
                data_original_prevista=d,
                data_atual_prevista=d,
                valor_previsto=valor_dec,
                status='PREVISTA',
                metadata_json=json.dumps(
                    {'tipo_evento': tipo_evento, 'ciclo_id': None, 'ordem_no_ciclo': None},
                    ensure_ascii=False
                ),
            )
            db.session.add(desp)
            criadas.append(desp)

    return criadas


def limpar_projecoes_anteriores(veiculo_id: int, data_inicio: date) -> int:
    """
    Remove projeções MVP anteriores ao mês de início (para não criar histórico retroativo).
    """
    inicio_mes = _primeiro_dia_mes(data_inicio)
    removidas = 0
    proj = DespesaPrevista.query.filter(
        DespesaPrevista.origem_tipo == 'VEICULO',
        DespesaPrevista.origem_id == veiculo_id,
        DespesaPrevista.data_prevista < inicio_mes,
    ).all()
    for desp in proj:
        if desp.status == 'PREVISTA' and _get_tipo_evento(desp) in EVENTOS_MVP:
            db.session.delete(desp)
            removidas += 1
    return removidas
