from __future__ import annotations

import json
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from dateutil.relativedelta import relativedelta

try:
    from backend.models import db, Veiculo, Categoria, DespesaPrevista
    from backend.services.categoria_default import (
        MOB_COMBUSTIVEL,
        MOB_SEGURO_VEICULAR,
        MOB_TRIBUTOS_VEICULARES,
        categoria_sistemica_mobilidade_id_para_tipo_evento,
        obter_categoria_sistemica_id,
    )
    from backend.services.perfil_financeiro_service import PerfilFinanceiroService
except ImportError:
    from models import db, Veiculo, Categoria, DespesaPrevista
    from services.categoria_default import (
        MOB_COMBUSTIVEL,
        MOB_SEGURO_VEICULAR,
        MOB_TRIBUTOS_VEICULARES,
        categoria_sistemica_mobilidade_id_para_tipo_evento,
        obter_categoria_sistemica_id,
    )
    from services.perfil_financeiro_service import PerfilFinanceiroService


EVENTOS_MVP = ('COMBUSTIVEL', 'IPVA', 'SEGURO', 'LICENCIAMENTO')
CENTAVOS = Decimal('0.01')


def _primeiro_dia_mes(d: date) -> date:
    return d.replace(day=1)


def _to_decimal(value) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def calcular_resumo_mensal_estimado_veiculo(veiculo: Veiculo) -> dict:
    """
    Calcula o custo mensal contratual/cadastral da modalidade veículo.

    Este cálculo não depende da janela de DespesaPrevista: IPVA, seguro e
    licenciamento são sempre diluídos por 12 para o resumo mensal da tela.
    """
    combustivel = _to_decimal(getattr(veiculo, 'combustivel_valor_mensal', None)) or Decimal('0')
    ipva = _to_decimal(getattr(veiculo, 'ipva_valor', None)) or Decimal('0')
    seguro = _to_decimal(getattr(veiculo, 'seguro_valor', None)) or Decimal('0')
    licenciamento = _to_decimal(getattr(veiculo, 'licenciamento_valor', None)) or Decimal('0')

    componentes = {
        'combustivel_mensal': _money(combustivel),
        'seguro_mensal_diluido': _money(seguro / Decimal('12')) if seguro else Decimal('0.00'),
        'ipva_mensal_diluido': _money(ipva / Decimal('12')) if ipva else Decimal('0.00'),
        'licenciamento_mensal_diluido': _money(licenciamento / Decimal('12')) if licenciamento else Decimal('0.00'),
        'manutencao_mensal_media': Decimal('0.00'),
        'assinatura_mensal': Decimal('0.00'),
        'transporte_app_mensal': Decimal('0.00'),
        'outros_custos_mensais': Decimal('0.00'),
    }
    total = _money(sum(componentes.values(), Decimal('0')))

    return {
        'componentes': {k: float(v) for k, v in componentes.items()},
        'total_mensal': float(total),
    }


def calcular_total_mensal_estimado_veiculo(veiculo: Veiculo) -> Decimal:
    resumo = calcular_resumo_mensal_estimado_veiculo(veiculo)
    return Decimal(str(resumo['total_mensal'])).quantize(CENTAVOS)


def serializar_veiculo_mobilidade(veiculo: Veiculo) -> dict:
    dados = veiculo.to_dict()
    resumo = calcular_resumo_mensal_estimado_veiculo(veiculo)
    dados['resumo_mensal_estimado'] = resumo['componentes']
    dados['total_mensal_estimado'] = resumo['total_mensal']
    return dados


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
    veiculo.categoria_combustivel_id = obter_categoria_sistemica_id(MOB_COMBUSTIVEL)
    veiculo.ipva_categoria_id = obter_categoria_sistemica_id(MOB_TRIBUTOS_VEICULARES)
    veiculo.seguro_categoria_id = obter_categoria_sistemica_id(MOB_SEGURO_VEICULAR)
    veiculo.licenciamento_categoria_id = obter_categoria_sistemica_id(MOB_TRIBUTOS_VEICULARES)


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
    existentes = PerfilFinanceiroService.aplicar_perfil_query(DespesaPrevista.query, DespesaPrevista).filter(
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

    # Combustível mensal
    valor_mensal = _to_decimal(getattr(veiculo, 'combustivel_valor_mensal', None))
    if valor_mensal and valor_mensal > 0:
        categoria_combustivel_id = categoria_sistemica_mobilidade_id_para_tipo_evento('COMBUSTIVEL')
        data_ref = inicio_mes
        while data_ref < fim_exclusivo:
            if ('COMBUSTIVEL', data_ref) in bloqueadas:
                data_ref = _primeiro_dia_mes(data_ref + relativedelta(months=1))
                continue
            desp = DespesaPrevista(
                perfil_financeiro_id=veiculo.perfil_financeiro_id or PerfilFinanceiroService.obter_perfil_ativo_id(),
                origem_tipo='VEICULO',
                origem_id=veiculo.id,
                categoria_id=categoria_combustivel_id,
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
                perfil_financeiro_id=veiculo.perfil_financeiro_id or PerfilFinanceiroService.obter_perfil_ativo_id(),
                origem_tipo='VEICULO',
                origem_id=veiculo.id,
                categoria_id=categoria_sistemica_mobilidade_id_para_tipo_evento(tipo_evento),
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
    proj = PerfilFinanceiroService.aplicar_perfil_query(DespesaPrevista.query, DespesaPrevista).filter(
        DespesaPrevista.origem_tipo == 'VEICULO',
        DespesaPrevista.origem_id == veiculo_id,
        DespesaPrevista.data_prevista < inicio_mes,
    ).all()
    for desp in proj:
        if desp.status == 'PREVISTA' and _get_tipo_evento(desp) in EVENTOS_MVP:
            db.session.delete(desp)
            removidas += 1
    return removidas
