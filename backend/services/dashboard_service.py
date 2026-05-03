from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import extract, func

try:
    from backend.models import (
        db,
        CartaoCategoriaLimite,
        CategoriaCartao,
        Conta,
        ContaBancaria,
        ConfigAgregador,
        DespesaPrevista,
        ItemDespesa,
        LancamentoAgregado,
        MobilidadeAssinatura,
        MobilidadeCenarioAtivo,
        ReceitaOrcamento,
        ReceitaRealizada,
    )
    from backend.services.cartao_service import CartaoService
except ImportError:
    from models import (
        db,
        CartaoCategoriaLimite,
        CategoriaCartao,
        Conta,
        ContaBancaria,
        ConfigAgregador,
        DespesaPrevista,
        ItemDespesa,
        LancamentoAgregado,
        MobilidadeAssinatura,
        MobilidadeCenarioAtivo,
        ReceitaOrcamento,
        ReceitaRealizada,
    )
    from services.cartao_service import CartaoService


def _decimal(value):
    if value is None:
        return Decimal('0')
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _float(value):
    return float(_decimal(value))


def _round(value):
    return round(_float(value), 2)


def _periodo_mes(mes_referencia=None):
    hoje = date.today()
    valor = (mes_referencia or '').strip()
    if not valor:
        return date(hoje.year, hoje.month, 1)

    if len(valor) == 7:
        valor = f'{valor}-01'

    try:
        parsed = datetime.strptime(valor, '%Y-%m-%d').date()
        return date(parsed.year, parsed.month, 1)
    except ValueError:
        return date(hoje.year, hoje.month, 1)


def _intervalo_mes(periodo):
    inicio = periodo
    ultimo_dia = monthrange(periodo.year, periodo.month)[1]
    fim = date(periodo.year, periodo.month, ultimo_dia)
    proximo_mes = date(periodo.year + (periodo.month // 12), (periodo.month % 12) + 1, 1)
    return inicio, fim, proximo_mes


def _status_consumo(percentual):
    if percentual is None:
        return 'revisar'
    if percentual > 100:
        return 'estourado'
    if percentual > 80:
        return 'atencao'
    return 'normal'


def _percentual(gasto, limite):
    gasto_decimal = _decimal(gasto)
    limite_decimal = _decimal(limite)
    if limite_decimal <= 0:
        return 0
    return round(float((gasto_decimal / limite_decimal) * Decimal('100')), 1)


def _filtro_conta_nao_fatura_cartao():
    return db.or_(
        Conta.is_fatura_cartao == False,
        Conta.is_fatura_cartao.is_(None),
    )


def _receitas_previstas(periodo):
    total_realizado = db.session.query(func.coalesce(func.sum(ReceitaRealizada.valor_recebido), 0)).filter(
        extract('month', ReceitaRealizada.mes_referencia) == periodo.month,
        extract('year', ReceitaRealizada.mes_referencia) == periodo.year,
    ).scalar()

    total_orcado = db.session.query(func.coalesce(func.sum(ReceitaOrcamento.valor_esperado), 0)).filter(
        extract('month', ReceitaOrcamento.mes_referencia) == periodo.month,
        extract('year', ReceitaOrcamento.mes_referencia) == periodo.year,
    ).scalar()

    return _decimal(total_realizado) + _decimal(total_orcado)


def _despesas_previstas(periodo):
    total_contas = db.session.query(func.coalesce(func.sum(Conta.valor), 0)).filter(
        extract('month', Conta.mes_referencia) == periodo.month,
        extract('year', Conta.mes_referencia) == periodo.year,
        _filtro_conta_nao_fatura_cartao(),
    ).scalar()

    total_previstas = db.session.query(func.coalesce(func.sum(DespesaPrevista.valor_previsto), 0)).filter(
        extract('month', DespesaPrevista.data_atual_prevista) == periodo.month,
        extract('year', DespesaPrevista.data_atual_prevista) == periodo.year,
        DespesaPrevista.status.in_(['PREVISTA', 'ADIADA']),
    ).scalar()

    return _decimal(total_contas) + _decimal(total_previstas)


def _total_faturas_periodo(periodo):
    total = Decimal('0')
    quantidade = 0
    faturas = Conta.query.filter(
        Conta.is_fatura_cartao == True,
        extract('month', Conta.mes_referencia) == periodo.month,
        extract('year', Conta.mes_referencia) == periodo.year,
        Conta.status_pagamento != 'Pago',
    ).all()

    for fatura in faturas:
        quantidade += 1
        valor = fatura.valor_consolidado or fatura.valor_executado or fatura.valor_planejado or fatura.valor
        total += _decimal(valor)

    return total, quantidade


def _recorrencias_ativas():
    recorrencias = ItemDespesa.query.filter_by(recorrente=True, ativo=True).all()
    total = sum((_decimal(item.valor) for item in recorrencias), Decimal('0'))
    return len(recorrencias), total


def _saldo_contas():
    total = db.session.query(func.coalesce(func.sum(ContaBancaria.saldo_atual), 0)).filter(
        ContaBancaria.status == 'ATIVO'
    ).scalar()
    return _decimal(total)


def _cartoes_limites(periodo):
    cartoes = ItemDespesa.query.filter_by(tipo='Agregador', ativo=True).order_by(ItemDespesa.nome).all()
    resultado = []
    limite_total_geral = Decimal('0')
    utilizado_total_geral = Decimal('0')

    for cartao in cartoes:
        limites = CartaoCategoriaLimite.query.filter_by(cartao_id=cartao.id, ativo=True).all()
        limite_total = sum((_decimal(limite.limite_mensal) for limite in limites), Decimal('0'))
        utilizado = db.session.query(func.coalesce(func.sum(LancamentoAgregado.valor), 0)).filter(
            LancamentoAgregado.cartao_id == cartao.id,
            extract('month', LancamentoAgregado.mes_fatura) == periodo.month,
            extract('year', LancamentoAgregado.mes_fatura) == periodo.year,
        ).scalar()
        utilizado = _decimal(utilizado)
        disponivel = limite_total - utilizado
        percentual = _percentual(utilizado, limite_total)
        config = ConfigAgregador.query.filter_by(item_despesa_id=cartao.id).first()
        final = ''
        if config and config.numero_cartao:
            final = str(config.numero_cartao)[-4:]

        limite_total_geral += limite_total
        utilizado_total_geral += utilizado

        resultado.append({
            'id': cartao.id,
            'nome': cartao.nome,
            'final': final,
            'limite_total': _round(limite_total),
            'utilizado': _round(utilizado),
            'disponivel': _round(disponivel),
            'percentual': percentual,
            'status': _status_consumo(percentual),
            'categorias_vinculadas': len(limites),
        })

    return resultado, limite_total_geral, utilizado_total_geral


def _categorias_cartao(periodo):
    limites = CartaoCategoriaLimite.query.filter_by(ativo=True).all()
    categorias = {}

    for limite in limites:
        categoria = limite.categoria_cartao
        if not categoria:
            continue
        item = categorias.setdefault(categoria.id, {
            'categoria_cartao_id': categoria.id,
            'nome': categoria.nome,
            'cor': categoria.cor,
            'icone': categoria.icone,
            'limite': Decimal('0'),
            'gasto': Decimal('0'),
        })
        item['limite'] += _decimal(limite.limite_mensal)

    gastos = db.session.query(
        LancamentoAgregado.categoria_cartao_id,
        func.coalesce(func.sum(LancamentoAgregado.valor), 0),
    ).filter(
        LancamentoAgregado.categoria_cartao_id.isnot(None),
        extract('month', LancamentoAgregado.mes_fatura) == periodo.month,
        extract('year', LancamentoAgregado.mes_fatura) == periodo.year,
    ).group_by(LancamentoAgregado.categoria_cartao_id).all()

    for categoria_id, total in gastos:
        categoria = db.session.get(CategoriaCartao, categoria_id)
        if not categoria:
            continue
        item = categorias.setdefault(categoria.id, {
            'categoria_cartao_id': categoria.id,
            'nome': categoria.nome,
            'cor': categoria.cor,
            'icone': categoria.icone,
            'limite': Decimal('0'),
            'gasto': Decimal('0'),
        })
        item['gasto'] += _decimal(total)

    lista = []
    for item in categorias.values():
        disponivel = item['limite'] - item['gasto']
        percentual = _percentual(item['gasto'], item['limite'])
        lista.append({
            'categoria_cartao_id': item['categoria_cartao_id'],
            'nome': item['nome'],
            'cor': item['cor'],
            'icone': item['icone'],
            'limite': _round(item['limite']),
            'gasto': _round(item['gasto']),
            'disponivel': _round(disponivel),
            'percentual': percentual,
            'status': _status_consumo(percentual),
        })

    lista.sort(key=lambda row: row['gasto'], reverse=True)
    return lista[:6]


def _contas_a_vencer_7_dias():
    hoje = date.today()
    fim = hoje + timedelta(days=7)
    contas = Conta.query.filter(
        Conta.data_vencimento.between(hoje, fim),
        Conta.status_pagamento == 'Pendente',
    ).order_by(Conta.data_vencimento).limit(8).all()

    total = sum((_decimal(conta.valor) for conta in contas), Decimal('0'))
    lista = []
    for conta in contas:
        dias = (conta.data_vencimento - hoje).days if conta.data_vencimento else None
        lista.append({
            'id': conta.id,
            'data': conta.data_vencimento.isoformat() if conta.data_vencimento else None,
            'descricao': conta.descricao,
            'origem': 'Fatura' if conta.is_fatura_cartao else 'Conta',
            'valor': _round(conta.valor),
            'tipo': 'fatura' if conta.is_fatura_cartao else 'despesa',
            'status_visual': 'vence_hoje' if dias == 0 else f'{dias} dias' if dias is not None else 'sem data',
        })

    return lista, total


def _alertas_operacionais(categorias, proximos_vencimentos):
    alertas = []
    vencendo_hoje = [item for item in proximos_vencimentos if item['status_visual'] == 'vence_hoje']
    if vencendo_hoje:
        alertas.append({
            'tipo': 'vencimento',
            'nivel': 'critico',
            'mensagem': f'{len(vencendo_hoje)} vencimento(s) hoje',
        })

    limites_alerta = [item for item in categorias if item['percentual'] > 80]
    if limites_alerta:
        alertas.append({
            'tipo': 'limite',
            'nivel': 'atencao',
            'mensagem': f'{len(limites_alerta)} limite(s) acima de 80%',
        })

    atrasadas = DespesaPrevista.query.filter(
        DespesaPrevista.data_atual_prevista < date.today(),
        DespesaPrevista.status.in_(['PREVISTA', 'ADIADA']),
    ).count()
    if atrasadas:
        alertas.append({
            'tipo': 'prevista',
            'nivel': 'atencao',
            'mensagem': f'{atrasadas} despesa(s) prevista(s) atrasada(s)',
        })

    return alertas


def _mobilidade_ativa():
    cenario = MobilidadeCenarioAtivo.query.filter_by(status='ATIVO').order_by(
        MobilidadeCenarioAtivo.updated_at.desc()
    ).first()

    alternativas = []
    assinaturas = MobilidadeAssinatura.query.filter_by(status='ATIVO').limit(3).all()
    for assinatura in assinaturas:
        alternativas.append({
            'tipo': 'ASSINATURA',
            'nome': assinatura.nome,
            'custo_mensal': _round(assinatura.valor_mensal),
            'status': 'alternativa',
        })

    if not cenario:
        return {
            'tipo': None,
            'nome': 'Sem modalidade ativa',
            'custo_mensal': 0,
            'status': 'nao_configurada',
            'categoria_cartao': None,
            'alternativas': alternativas,
        }

    custo = Decimal('0')
    if cenario.recorrencia and cenario.recorrencia.valor:
        custo = _decimal(cenario.recorrencia.valor)

    nome = {
        'VEICULO': 'Veiculo proprio',
        'TRANSPORTE_APP': 'Transporte por app',
        'ASSINATURA': 'Assinatura',
    }.get(cenario.tipo_modalidade, cenario.tipo_modalidade or 'Mobilidade')

    return {
        'tipo': cenario.tipo_modalidade,
        'nome': nome,
        'custo_mensal': _round(custo),
        'status': 'ativa',
        'categoria_cartao': {
            'id': cenario.categoria_cartao.id,
            'nome': cenario.categoria_cartao.nome,
        } if cenario.categoria_cartao else None,
        'alternativas': alternativas,
    }


def _fluxo_caixa(periodo, saldo_inicial, receitas, despesas):
    labels = []
    entradas = []
    saidas = []
    saldo = []
    dias = monthrange(periodo.year, periodo.month)[1]
    saldo_corrente = saldo_inicial

    for ponto in range(1, 6):
        dia = min(dias, 1 + ((ponto - 1) * max(1, dias // 5)))
        labels.append(f'{dia:02d}/{periodo.month:02d}')
        fator = Decimal(str(ponto / 5))
        entrada_ponto = receitas * fator
        saida_ponto = despesas * fator
        saldo_corrente = saldo_inicial + entrada_ponto - saida_ponto
        entradas.append(_round(entrada_ponto))
        saidas.append(_round(saida_ponto))
        saldo.append(_round(saldo_corrente))

    return {
        'labels': labels,
        'entradas': entradas,
        'saidas': saidas,
        'saldo_projetado': saldo,
        'resumo': {
            'receitas_previstas': _round(receitas),
            'despesas_previstas': _round(despesas),
            'saldo_final_projetado': _round(saldo[-1] if saldo else saldo_inicial),
        },
        'tipo': 'projecao_simplificada',
    }


class DashboardService:
    @staticmethod
    def obter_resumo(mes_referencia=None):
        periodo = _periodo_mes(mes_referencia)
        inicio, fim, _proximo_mes = _intervalo_mes(periodo)

        saldo_consolidado = _saldo_contas()
        receitas = _receitas_previstas(periodo)
        despesas = _despesas_previstas(periodo)
        fluxo = _fluxo_caixa(periodo, saldo_consolidado, receitas, despesas)
        faturas_total, faturas_qtd = _total_faturas_periodo(periodo)
        recorrencias_qtd, recorrencias_total = _recorrencias_ativas()
        proximos_vencimentos, contas_7_total = _contas_a_vencer_7_dias()
        categorias = _categorias_cartao(periodo)
        cartoes, limite_total, utilizado_total = _cartoes_limites(periodo)
        mobilidade = _mobilidade_ativa()
        alertas = _alertas_operacionais(categorias, proximos_vencimentos)

        despesas_previstas_mes = db.session.query(func.coalesce(func.sum(DespesaPrevista.valor_previsto), 0)).filter(
            DespesaPrevista.data_atual_prevista >= inicio,
            DespesaPrevista.data_atual_prevista <= fim,
        ).scalar()
        despesas_previstas_pendentes = db.session.query(func.count(DespesaPrevista.id)).filter(
            DespesaPrevista.data_atual_prevista >= inicio,
            DespesaPrevista.data_atual_prevista <= fim,
            DespesaPrevista.status.in_(['PREVISTA', 'ADIADA']),
        ).scalar() or 0
        despesas_previstas_confirmadas = db.session.query(func.count(DespesaPrevista.id)).filter(
            DespesaPrevista.data_atual_prevista >= inicio,
            DespesaPrevista.data_atual_prevista <= fim,
            DespesaPrevista.status == 'CONFIRMADA',
        ).scalar() or 0

        percentual_limite = _percentual(utilizado_total, limite_total)

        return {
            'periodo': {
                'mes_referencia': f'{periodo.year:04d}-{periodo.month:02d}',
                'inicio': inicio.isoformat(),
                'fim': fim.isoformat(),
                'rotulo': periodo.strftime('%m/%Y'),
            },
            'kpis': {
                'saldo_consolidado': {
                    'valor': _round(saldo_consolidado),
                    'subtitulo': 'Disponivel em contas',
                    'tendencia': None,
                },
                'fluxo_projetado_30_dias': {
                    'valor': fluxo['resumo']['saldo_final_projetado'],
                    'subtitulo': 'Saldo projetado',
                    'tendencia': None,
                },
                'faturas_em_aberto': {
                    'valor': _round(faturas_total),
                    'quantidade_cartoes': faturas_qtd,
                    'subtitulo': f'{faturas_qtd} cartao(s)',
                },
                'recorrencias_ativas': {
                    'quantidade': recorrencias_qtd,
                    'valor_mensal': _round(recorrencias_total),
                    'subtitulo': 'fixas e variaveis',
                },
            },
            'operacional': {
                'despesas_previstas_mes': {
                    'valor': _round(despesas_previstas_mes),
                    'pendentes': int(despesas_previstas_pendentes),
                    'confirmadas': int(despesas_previstas_confirmadas),
                    'percentual_orcamento': _percentual(despesas_previstas_mes, receitas) if receitas > 0 else 0,
                },
                'contas_a_vencer_7_dias': {
                    'valor': _round(contas_7_total),
                    'quantidade': len(proximos_vencimentos),
                },
                'alertas_operacionais': {
                    'quantidade': len(alertas),
                    'itens': alertas,
                },
                'modalidade_mobilidade_ativa': mobilidade,
            },
            'fluxo_caixa': fluxo,
            'categorias_cartao': categorias,
            'proximos_vencimentos': proximos_vencimentos,
            'cartoes_limites': {
                'itens': cartoes,
                'limite_total': _round(limite_total),
                'utilizado_total': _round(utilizado_total),
                'disponivel_total': _round(limite_total - utilizado_total),
                'percentual_total': percentual_limite,
                'status': _status_consumo(percentual_limite),
            },
            'mobilidade': mobilidade,
            'acoes_rapidas': [
                {'label': 'Confirmar despesas previstas', 'url': '/despesas-previstas'},
                {'label': 'Importar fatura', 'url': '/importar-cartao'},
                {'label': 'Gerenciar categorias do cartao', 'url': '/categorias'},
                {'label': 'Revisar recorrencias', 'url': '/recorrencias'},
                {'label': 'Gerenciar mobilidade', 'url': '/veiculos'},
            ],
            'alertas': alertas,
        }
