"""
Rotas da API para Dashboard - Dados Consolidados

ATENÇÃO:
Este dashboard reflete dados consolidados do sistema financeiro.
O gráfico de saldo bancário é uma PROJEÇÃO, não um histórico real.

Endpoints:
- GET /api/dashboard/resumo-mes         - Resumo financeiro do mês atual
- GET /api/dashboard/indicadores        - Indicadores inteligentes e insights
- GET /api/dashboard/grafico-categorias - Dados para gráfico de pizza (despesas por categoria)
- GET /api/dashboard/grafico-evolucao   - Dados para gráfico de evolução (últimos 6 meses)
- GET /api/dashboard/grafico-saldo      - Dados para gráfico de linha (evolução do saldo - PROJEÇÃO)
- GET /api/dashboard/alertas            - Alertas e agenda financeira (próximos vencimentos)
"""
from flask import Blueprint, request, jsonify
from datetime import datetime, date, timedelta
from sqlalchemy import func, extract
from decimal import Decimal
from calendar import monthrange
import logging

try:
    from backend.models import db, Conta, Categoria, ItemDespesa, ConfigAgregador, ItemReceita, ReceitaRealizada, ContaBancaria, Financiamento, FinanciamentoParcela, ItemAgregado, ReceitaOrcamento, LancamentoAgregado, OrcamentoAgregado
except ImportError:
    from models import db, Conta, Categoria, ItemDespesa, ConfigAgregador, ItemReceita, ReceitaRealizada, ContaBancaria, Financiamento, FinanciamentoParcela, ItemAgregado, ReceitaOrcamento, LancamentoAgregado, OrcamentoAgregado

# Criar blueprint
dashboard_bp = Blueprint('dashboard', __name__)
logger = logging.getLogger(__name__)


def _internal_error(contexto='dashboard'):
    logger.exception('Erro interno em %s', contexto)
    return jsonify({'success': False, 'error': 'Erro interno ao processar requisicao'}), 500


def decimal_to_float(value):
    """Converte Decimal para float"""
    if value is None:
        return 0.0
    return float(value) if isinstance(value, Decimal) else value


def _filtro_conta_nao_fatura_cartao():
    """Restringe consultas gerais de Conta para nao misturar faturas de cartao."""
    return db.or_(
        Conta.is_fatura_cartao == False,
        Conta.is_fatura_cartao.is_(None)
    )


def _deslocar_mes(ano, mes, delta):
    """
    Desloca um par (ano, mes) em `delta` meses.
    delta negativo = meses passados; positivo = meses futuros.
    """
    indice = (ano * 12 + (mes - 1)) + delta
    novo_ano = indice // 12
    novo_mes = (indice % 12) + 1
    return novo_ano, novo_mes


def _periodo_mes(ano, mes):
    primeiro_dia = date(ano, mes, 1)
    ultimo_dia = date(ano, mes, monthrange(ano, mes)[1])
    return primeiro_dia, ultimo_dia


def _resolver_periodo_request():
    """
    Resolve período de referência do dashboard.
    Aceita:
    - ?mes=MM&ano=YYYY
    - ?periodo=YYYY-MM
    """
    hoje = date.today()
    mes = request.args.get('mes', type=int)
    ano = request.args.get('ano', type=int)
    periodo = (request.args.get('periodo') or '').strip()
    filtro_ativo = False

    if periodo and '-' in periodo:
        partes = periodo.split('-', 1)
        if len(partes) == 2 and partes[0].isdigit() and partes[1].isdigit():
            ano = int(partes[0])
            mes = int(partes[1])
            filtro_ativo = True

    if mes is not None or ano is not None:
        filtro_ativo = True
        if mes is None:
            mes = hoje.month
        if ano is None:
            ano = hoje.year

    if mes is None or ano is None:
        mes = hoje.month
        ano = hoje.year

    if not (1 <= int(mes) <= 12):
        mes = hoje.month
        filtro_ativo = False
    if int(ano) < 2000 or int(ano) > 2100:
        ano = hoje.year
        filtro_ativo = False

    return int(mes), int(ano), filtro_ativo


def _calcular_receitas_mes(mes, ano):
    """
    Soma receitas do mês:
    - realizadas
    - previstas ainda não realizadas
    """
    orcamentos_com_realizacao = db.session.query(ReceitaRealizada.orcamento_id).filter(
        extract('month', ReceitaRealizada.mes_referencia) == mes,
        extract('year', ReceitaRealizada.mes_referencia) == ano,
        ReceitaRealizada.orcamento_id.isnot(None)
    ).distinct().all()

    ids_orcamentos_realizados = [o[0] for o in orcamentos_com_realizacao]

    receitas_realizadas = db.session.query(func.sum(ReceitaRealizada.valor_recebido)).filter(
        extract('month', ReceitaRealizada.mes_referencia) == mes,
        extract('year', ReceitaRealizada.mes_referencia) == ano
    ).scalar() or 0

    query_previstas = db.session.query(func.sum(ReceitaOrcamento.valor_esperado)).filter(
        extract('month', ReceitaOrcamento.mes_referencia) == mes,
        extract('year', ReceitaOrcamento.mes_referencia) == ano
    )

    if ids_orcamentos_realizados:
        query_previstas = query_previstas.filter(~ReceitaOrcamento.id.in_(ids_orcamentos_realizados))

    receitas_previstas = query_previstas.scalar() or 0
    return decimal_to_float(receitas_realizadas) + decimal_to_float(receitas_previstas)


def _receitas_por_fonte_mes(mes, ano):
    """
    Visão gerencial simples de receitas realizadas por tipo/fonte.
    """
    resultado = db.session.query(
        ItemReceita.tipo,
        func.sum(ReceitaRealizada.valor_recebido)
    ).outerjoin(
        ItemReceita, ReceitaRealizada.item_receita_id == ItemReceita.id
    ).filter(
        extract('month', ReceitaRealizada.mes_referencia) == mes,
        extract('year', ReceitaRealizada.mes_referencia) == ano
    ).group_by(
        ItemReceita.tipo
    ).all()

    fontes = []
    for tipo, total in resultado:
        fontes.append({
            'fonte': tipo or 'Nao informado',
            'valor': decimal_to_float(total or 0)
        })
    return fontes


def _calcular_totais_fatura_cartao(cartao_id, competencia):
    """
    Calcula (total_previsto, total_executado) para fatura de cartão.

    LÓGICA IDÊNTICA ao despesas.py:
    - total_executado = soma de TODOS LancamentoAgregado do mês
    - total_previsto = total_executado + complemento de orçamentos não gastos
    """
    comp = competencia.replace(day=1)

    # Total executado = soma de todos os lançamentos do mês
    total_executado = db.session.query(
        func.coalesce(func.sum(LancamentoAgregado.valor), 0)
    ).filter(
        LancamentoAgregado.cartao_id == cartao_id,
        LancamentoAgregado.mes_fatura == comp
    ).scalar()
    total_executado = float(total_executado or 0)

    # Itens (categorias) do cartão
    itens = ItemAgregado.query.filter_by(item_despesa_id=cartao_id, ativo=True).all()
    if not itens:
        return total_executado, total_executado

    itens_ids = [i.id for i in itens]

    # Gastos por categoria
    gastos_por_item = dict(
        db.session.query(
            LancamentoAgregado.item_agregado_id,
            func.coalesce(func.sum(LancamentoAgregado.valor), 0)
        ).filter(
            LancamentoAgregado.cartao_id == cartao_id,
            LancamentoAgregado.mes_fatura == comp,
            LancamentoAgregado.item_agregado_id.in_(itens_ids)
        ).group_by(
            LancamentoAgregado.item_agregado_id
        ).all()
    )

    # Orçamentos por categoria
    orcados_por_item = dict(
        db.session.query(
            OrcamentoAgregado.item_agregado_id,
            func.coalesce(func.sum(OrcamentoAgregado.valor_teto), 0)
        ).filter(
            OrcamentoAgregado.mes_referencia == comp,
            OrcamentoAgregado.item_agregado_id.in_(itens_ids)
        ).group_by(
            OrcamentoAgregado.item_agregado_id
        ).all()
    )

    # Complemento: orçado que ainda não foi gasto
    complemento_orcamento = 0.0
    for item_id in itens_ids:
        gasto = float(gastos_por_item.get(item_id, 0) or 0)
        orcado = float(orcados_por_item.get(item_id, 0) or 0)
        if orcado > gasto:
            complemento_orcamento += (orcado - gasto)

    total_previsto = total_executado + complemento_orcamento

    return total_previsto, total_executado


def calcular_despesas_mes(mes, ano):
    """
    Calcula total de despesas do mês aplicando a regra correta para faturas de cartão.

    Regra:
    - Despesas comuns: usa Conta.valor diretamente
    - Faturas de cartão:
        - Se PAGO: usa total_executado (calculado dinamicamente)
        - Se PENDENTE: usa total_previsto (calculado dinamicamente)

    Esta é a regra soberana consolidada no sistema (mesma de /api/despesas)
    """
    # Despesas comuns (não-cartão)
    despesas_comuns = db.session.query(func.sum(Conta.valor)).filter(
        extract('month', Conta.mes_referencia) == mes,
        extract('year', Conta.mes_referencia) == ano,
        _filtro_conta_nao_fatura_cartao()
    ).scalar() or 0

    # Faturas de cartão
    faturas = db.session.query(Conta).filter(
        Conta.is_fatura_cartao == True,
        extract('month', Conta.mes_referencia) == mes,
        extract('year', Conta.mes_referencia) == ano
    ).all()

    total_faturas = 0
    for fatura in faturas:
        # Calcular valores dinamicamente (não usar campos do banco que podem estar zerados)
        if getattr(fatura, 'cartao_competencia', None) and fatura.item_despesa_id:
            total_previsto, total_executado = _calcular_totais_fatura_cartao(
                cartao_id=fatura.item_despesa_id,
                competencia=fatura.cartao_competencia
            )
        else:
            # Fallback: usar campos do banco (pode estar zerado)
            total_previsto = decimal_to_float(fatura.valor_planejado or fatura.valor or 0)
            total_executado = decimal_to_float(fatura.valor_executado or fatura.valor or 0)

        # Aplicar regra soberana
        if fatura.status_pagamento == 'Pago':
            total_faturas += total_executado
        else:
            total_faturas += total_previsto

    return decimal_to_float(despesas_comuns) + total_faturas


# ============================================================================
# BLOCO 1: RESUMO FINANCEIRO DO MÊS
# ============================================================================

@dashboard_bp.route('/resumo-mes', methods=['GET'])
def resumo_mes():
    """
    Retorna resumo financeiro do mês atual:
    - Total de receitas do mês
    - Total de despesas do mês
    - Saldo líquido (receitas - despesas)
    - Saldo total nas contas bancárias
    """
    try:
        mes_atual, ano_atual, filtro_ativo = _resolver_periodo_request()
        data_ref = date(ano_atual, mes_atual, 1)
        receitas_mes = _calcular_receitas_mes(mes_atual, ano_atual)

        # 2. DESPESAS DO MÊS (Por mês de competência)
        # Usa função auxiliar que aplica regra correta para faturas de cartão
        despesas_mes = calcular_despesas_mes(mes_atual, ano_atual)

        # 3. SALDO LÍQUIDO
        despesas_float = decimal_to_float(despesas_mes)
        saldo_liquido = receitas_mes - despesas_float

        # 4. SALDO NAS CONTAS BANCÁRIAS
        saldo_contas = db.session.query(func.sum(ContaBancaria.saldo_atual)).filter(
            ContaBancaria.status == 'ATIVO'
        ).scalar() or 0

        return jsonify({
            'success': True,
            'data': {
                'receitas_mes': receitas_mes,
                'despesas_mes': despesas_float,
                'saldo_liquido': saldo_liquido,
                'saldo_contas_bancarias': decimal_to_float(saldo_contas),
                'mes': mes_atual,
                'ano': ano_atual,
                'periodo': f'{ano_atual:04d}-{mes_atual:02d}',
                'filtro_aplicado': filtro_ativo,
                'mes_nome': data_ref.strftime('%B/%Y').capitalize()
            }
        }), 200

    except Exception:
        return _internal_error('resumo_mes')


# ============================================================================
# BLOCO 2: INDICADORES INTELIGENTES
# ============================================================================

@dashboard_bp.route('/indicadores', methods=['GET'])
def indicadores():
    """
    Retorna indicadores inteligentes e insights
    """
    try:
        mes_atual, ano_atual, filtro_ativo = _resolver_periodo_request()
        primeiro_dia_mes = date(ano_atual, mes_atual, 1)
        ano_mes_anterior, mes_anterior = _deslocar_mes(ano_atual, mes_atual, -1)

        # 1. MÉDIA HISTÓRICA DE DESPESAS (últimos 3 meses, por competência)
        tres_meses_atras = primeiro_dia_mes - timedelta(days=90)

        media_historica = db.session.query(func.avg(Conta.valor)).filter(
            Conta.mes_referencia >= tres_meses_atras,
            Conta.mes_referencia < primeiro_dia_mes
        ).scalar() or 0

        # Despesas do mês atual (usa função auxiliar que aplica regra correta)
        despesas_mes_atual = calcular_despesas_mes(mes_atual, ano_atual)

        acima_media = despesas_mes_atual > (decimal_to_float(media_historica) * 1.1)

        # 2. GASTOS PENDENTES (janela default = próximos 7 dias; com filtro = mês selecionado)
        if filtro_ativo:
            inicio_ref, fim_ref = _periodo_mes(ano_atual, mes_atual)
            gastos_pendentes = db.session.query(func.count(Conta.id)).filter(
                Conta.data_vencimento.between(inicio_ref, fim_ref),
                Conta.status_pagamento == 'Pendente',
                _filtro_conta_nao_fatura_cartao()
            ).scalar() or 0
        else:
            hoje = date.today()
            proximos_7_dias = hoje + timedelta(days=7)
            gastos_pendentes = db.session.query(func.count(Conta.id)).filter(
                Conta.data_vencimento.between(hoje, proximos_7_dias),
                Conta.status_pagamento == 'Pendente',
                _filtro_conta_nao_fatura_cartao()
            ).scalar() or 0

        # 3. FATURAS DE CARTÃO PENDENTES (mês atual)
        faturas_proximas = db.session.query(func.count(Conta.id)).filter(
            Conta.is_fatura_cartao == True,
            Conta.status_pagamento == 'Pendente',
            extract('month', Conta.mes_referencia) == mes_atual,
            extract('year', Conta.mes_referencia) == ano_atual
        ).scalar() or 0

        # 4. PORCENTAGEM POUPADA
        receitas_mes = _calcular_receitas_mes(mes_atual, ano_atual)

        despesas_totais = decimal_to_float(despesas_mes_atual)
        receitas_totais = receitas_mes
        percentual_poupado = ((receitas_totais - despesas_totais) / receitas_totais * 100) if receitas_totais > 0 else 0

        # 5. RECEITAS EXTRAS (simplificado)
        receitas_extras = 0  # Simplificado por enquanto

        # 6. Comparativos simples com mês anterior
        despesas_mes_anterior = calcular_despesas_mes(mes_anterior, ano_mes_anterior)
        receitas_mes_anterior = _calcular_receitas_mes(mes_anterior, ano_mes_anterior)

        variacao_despesas_pct = 0
        if despesas_mes_anterior > 0:
            variacao_despesas_pct = ((despesas_mes_atual - despesas_mes_anterior) / despesas_mes_anterior) * 100

        variacao_receitas_pct = 0
        if receitas_mes_anterior > 0:
            variacao_receitas_pct = ((receitas_mes - receitas_mes_anterior) / receitas_mes_anterior) * 100

        receitas_por_fonte = _receitas_por_fonte_mes(mes_atual, ano_atual)

        return jsonify({
            'success': True,
            'data': {
                'despesas_acima_media': acima_media,
                'media_historica': decimal_to_float(media_historica),
                'despesas_mes_atual': decimal_to_float(despesas_mes_atual),
                'gastos_pendentes_proximos': gastos_pendentes,
                'faturas_cartao_proximas': faturas_proximas,
                'percentual_poupado': round(percentual_poupado, 1),
                'receitas_extras': receitas_extras,
                'variacao_despesas_mes_anterior_pct': round(variacao_despesas_pct, 1),
                'variacao_receitas_mes_anterior_pct': round(variacao_receitas_pct, 1),
                'receitas_por_fonte': receitas_por_fonte,
                'periodo': f'{ano_atual:04d}-{mes_atual:02d}'
            }
        }), 200

    except Exception:
        return _internal_error('indicadores')


# ============================================================================
# BLOCO 3: GRÁFICOS
# ============================================================================

@dashboard_bp.route('/grafico-categorias', methods=['GET'])
def grafico_categorias():
    """
    Retorna dados para gráfico de pizza: Distribuição de Despesas por Categoria
    """
    try:
        mes_atual, ano_atual, _ = _resolver_periodo_request()

        # Agrupar despesas por categoria via ItemDespesa (por mês de competência)
        resultado = db.session.query(
            Categoria.nome,
            Categoria.cor,
            func.sum(Conta.valor).label('total')
        ).outerjoin(
            ItemDespesa, Conta.item_despesa_id == ItemDespesa.id
        ).outerjoin(
            Categoria, ItemDespesa.categoria_id == Categoria.id
        ).filter(
            extract('month', Conta.mes_referencia) == mes_atual,
            extract('year', Conta.mes_referencia) == ano_atual,
            _filtro_conta_nao_fatura_cartao(),
            Categoria.id.isnot(None)  # Apenas contas com categoria
        ).group_by(
            Categoria.id, Categoria.nome, Categoria.cor
        ).order_by(
            func.sum(Conta.valor).desc()
        ).all()

        categorias = []
        valores = []
        cores = []

        for cat_nome, cat_cor, total in resultado:
            categorias.append(cat_nome)
            valores.append(decimal_to_float(total))
            cores.append(cat_cor)

        return jsonify({
            'success': True,
            'data': {
                'labels': categorias,
                'valores': valores,
                'cores': cores
            }
        }), 200

    except Exception:
        return _internal_error('grafico_categorias')


@dashboard_bp.route('/grafico-evolucao', methods=['GET'])
def grafico_evolucao():
    """
    Retorna dados para gráfico de barras: Evolução de Gastos (últimos 6 meses)
    """
    try:
        mes_ref, ano_ref, _ = _resolver_periodo_request()
        meses = []
        valores = []

        # Últimos 6 meses
        for i in range(5, -1, -1):
            ano, mes = _deslocar_mes(ano_ref, mes_ref, -i)

            # Usar função auxiliar que aplica regra correta para faturas de cartão
            total_mes = calcular_despesas_mes(mes, ano)

            # Formato do mês
            data_ref = date(ano, mes, 1)
            meses.append(data_ref.strftime('%b/%y'))
            valores.append(total_mes)

        return jsonify({
            'success': True,
            'data': {
                'labels': meses,
                'valores': valores
            }
        }), 200

    except Exception:
        return _internal_error('grafico_evolucao')


@dashboard_bp.route('/grafico-saldo', methods=['GET'])
def grafico_saldo():
    """
    Retorna dados para gráfico de linha: Evolução do Saldo Bancário
    """
    try:
        mes_ref, ano_ref, _ = _resolver_periodo_request()
        meses = []
        saldos = []

        # Saldo atual
        saldo_atual = db.session.query(func.sum(ContaBancaria.saldo_atual)).filter(
            ContaBancaria.status == 'ATIVO'
        ).scalar() or 0

        saldo_atual_float = decimal_to_float(saldo_atual)

        # Últimos 6 meses (simulação simplificada)
        for i in range(5, -1, -1):
            ano, mes = _deslocar_mes(ano_ref, mes_ref, -i)

            # Calcular diferencial de receitas - despesas desse mês
            # Usar lógica condicional para receitas (confirmadas + previstas não confirmadas)
            orcamentos_realizados = db.session.query(ReceitaRealizada.orcamento_id).filter(
                extract('month', ReceitaRealizada.mes_referencia) == mes,
                extract('year', ReceitaRealizada.mes_referencia) == ano,
                ReceitaRealizada.orcamento_id.isnot(None)
            ).distinct().all()

            ids_realizados = [o[0] for o in orcamentos_realizados]

            receitas_realizadas_mes = db.session.query(func.sum(ReceitaRealizada.valor_recebido)).filter(
                extract('month', ReceitaRealizada.mes_referencia) == mes,
                extract('year', ReceitaRealizada.mes_referencia) == ano
            ).scalar() or 0

            query_prev = db.session.query(func.sum(ReceitaOrcamento.valor_esperado)).filter(
                extract('month', ReceitaOrcamento.mes_referencia) == mes,
                extract('year', ReceitaOrcamento.mes_referencia) == ano
            )

            if ids_realizados:
                query_prev = query_prev.filter(~ReceitaOrcamento.id.in_(ids_realizados))

            receitas_previstas_mes = query_prev.scalar() or 0
            receitas_mes = decimal_to_float(receitas_realizadas_mes) + decimal_to_float(receitas_previstas_mes)

            # Usar função auxiliar que aplica regra correta para faturas de cartão
            despesas_mes = calcular_despesas_mes(mes, ano)

            diferencial = receitas_mes - despesas_mes

            # Projetar saldo (aproximação)
            saldo_mes = saldo_atual_float - (diferencial * (i + 1))

            data_ref = date(ano, mes, 1)
            meses.append(data_ref.strftime('%b/%y'))
            saldos.append(round(saldo_mes, 2))

        return jsonify({
            'success': True,
            'data': {
                'labels': meses,
                'valores': saldos,
                'tipo': 'projecao',
                'descricao': 'Evolução projetada do saldo com base no saldo atual'
            }
        }), 200

    except Exception:
        return _internal_error('grafico_saldo')


# ============================================================================
# BLOCO 4: ALERTAS E AGENDA FINANCEIRA
# ============================================================================

@dashboard_bp.route('/alertas', methods=['GET'])
def alertas():
    """
    Retorna alertas e agenda financeira
    """
    try:
        mes_atual, ano_atual, filtro_ativo = _resolver_periodo_request()
        hoje = date.today()
        inicio_mes, fim_mes = _periodo_mes(ano_atual, mes_atual)

        if filtro_ativo:
            data_inicio_alerta = inicio_mes
            data_fim_alerta = fim_mes
        else:
            data_inicio_alerta = hoje
            data_fim_alerta = hoje + timedelta(days=7)

        # 1. CONTAS A VENCER (Contas pendentes)
        contas_vencer = db.session.query(Conta).outerjoin(
            ItemDespesa, Conta.item_despesa_id == ItemDespesa.id
        ).outerjoin(
            Categoria, ItemDespesa.categoria_id == Categoria.id
        ).filter(
            Conta.data_vencimento.between(data_inicio_alerta, data_fim_alerta),
            Conta.status_pagamento == 'Pendente',
            _filtro_conta_nao_fatura_cartao()
        ).order_by(Conta.data_vencimento).limit(10).all()

        # 2. FATURAS DE CARTÃO PENDENTES (mês atual)
        cartoes_vencer = db.session.query(Conta).outerjoin(
            ItemDespesa, Conta.item_despesa_id == ItemDespesa.id
        ).filter(
            Conta.is_fatura_cartao == True,
            Conta.status_pagamento == 'Pendente',
            extract('month', Conta.mes_referencia) == mes_atual,
            extract('year', Conta.mes_referencia) == ano_atual
        ).limit(5).all()

        # 3. FINANCIAMENTOS ATIVOS
        financiamentos_mes = db.session.query(Financiamento).filter(
            Financiamento.ativo == True
        ).limit(5).all()

        # 4. RECEITAS PREVISTAS (via orçamento)
        receitas_previstas = db.session.query(ReceitaOrcamento).outerjoin(
            ItemReceita, ReceitaOrcamento.item_receita_id == ItemReceita.id
        ).filter(
            extract('month', ReceitaOrcamento.mes_referencia) == mes_atual,
            extract('year', ReceitaOrcamento.mes_referencia) == ano_atual
        ).limit(10).all()

        # Formatar dados
        contas_lista = []
        for conta in contas_vencer:
            contas_lista.append({
                'id': conta.id,
                'descricao': conta.descricao,
                'valor': decimal_to_float(conta.valor),
                'data_vencimento': conta.data_vencimento.strftime('%d/%m/%Y'),
                'categoria': conta.item_despesa.categoria.nome if conta.item_despesa and conta.item_despesa.categoria else 'Sem categoria',
                'tipo': 'lancamento'
            })

        cartoes_lista = []
        for fatura in cartoes_vencer:
            # Calcular valor dinamicamente (mesma regra de calcular_despesas_mes)
            if getattr(fatura, 'cartao_competencia', None) and fatura.item_despesa_id:
                total_previsto, total_executado = _calcular_totais_fatura_cartao(
                    cartao_id=fatura.item_despesa_id,
                    competencia=fatura.cartao_competencia
                )
            else:
                # Fallback: usar campos do banco
                total_previsto = decimal_to_float(fatura.valor_planejado or fatura.valor or 0)
                total_executado = decimal_to_float(fatura.valor_executado or fatura.valor or 0)

            # Aplicar regra soberana
            valor_fatura = total_executado if fatura.status_pagamento == 'Pago' else total_previsto

            cartoes_lista.append({
                'id': fatura.id,
                'nome': fatura.item_despesa.nome if fatura.item_despesa else 'Cartão',
                'valor': valor_fatura,
                'data_vencimento': fatura.data_vencimento.strftime('%d/%m/%Y') if fatura.data_vencimento else 'N/A',
                'status': fatura.status_fatura if hasattr(fatura, 'status_fatura') else 'PENDENTE',
                'tipo': 'cartao'
            })

        financiamentos_lista = []
        for fin in financiamentos_mes:
            # Buscar parcela do mês atual
            parcela_mes = FinanciamentoParcela.query.filter(
                FinanciamentoParcela.financiamento_id == fin.id,
                extract('month', FinanciamentoParcela.data_vencimento) == mes_atual,
                extract('year', FinanciamentoParcela.data_vencimento) == ano_atual
            ).order_by(FinanciamentoParcela.numero_parcela).first()

            # Apenas adicionar se houver parcela no mês
            if parcela_mes:
                financiamentos_lista.append({
                    'id': fin.id,
                    'descricao': fin.nome,
                    'valor_parcela': decimal_to_float(parcela_mes.valor_previsto_total),
                    'parcela_atual': parcela_mes.numero_parcela,
                    'total_parcelas': fin.prazo_total_meses,
                    'tipo': 'financiamento'
                })

        receitas_lista = []
        for orcamento in receitas_previstas:
            receitas_lista.append({
                'id': orcamento.id,
                'descricao': orcamento.item_receita.nome if orcamento.item_receita else 'Receita',
                'valor': decimal_to_float(orcamento.valor_esperado),
                'data_recebimento': orcamento.mes_referencia.strftime('%d/%m/%Y'),
                'fonte': orcamento.item_receita.tipo if orcamento.item_receita else 'Não definido',
                'tipo': 'receita'
            })

        return jsonify({
            'success': True,
            'data': {
                'contas_vencer': contas_lista,
                'cartoes_vencer': cartoes_lista,
                'faturas_cartao': cartoes_lista,  # compatibilidade de contrato
                'financiamentos_mes': financiamentos_lista,
                'financiamentos': financiamentos_lista,  # compatibilidade de contrato
                'receitas_previstas': receitas_lista,
                'periodo': f'{ano_atual:04d}-{mes_atual:02d}',
                'janela_alerta': {
                    'inicio': data_inicio_alerta.isoformat(),
                    'fim': data_fim_alerta.isoformat(),
                    'tipo': 'mes' if filtro_ativo else 'proximos_7_dias'
                }
            }
        }), 200

    except Exception:
        return _internal_error('alertas')


@dashboard_bp.route('/fluxo-caixa-projetado', methods=['GET'])
def fluxo_caixa_projetado():
    """
    Projeção simplificada de fluxo de caixa.
    Premissas:
    - usa receitas e despesas por competência já registradas/projetadas no sistema;
    - não é previsão estatística avançada;
    - horizonte curto para visão gerencial.
    """
    try:
        mes_ref, ano_ref, _ = _resolver_periodo_request()
        horizonte = request.args.get('meses', default=4, type=int)
        horizonte = max(1, min(horizonte, 12))

        saldo_atual = db.session.query(func.sum(ContaBancaria.saldo_atual)).filter(
            ContaBancaria.status == 'ATIVO'
        ).scalar() or 0
        saldo_corrente = decimal_to_float(saldo_atual)

        labels = []
        entradas = []
        saidas = []
        saldos = []

        for i in range(horizonte):
            ano, mes = _deslocar_mes(ano_ref, mes_ref, i)
            receitas_mes = _calcular_receitas_mes(mes, ano)
            despesas_mes = calcular_despesas_mes(mes, ano)
            saldo_corrente += (receitas_mes - despesas_mes)

            labels.append(f'{mes:02d}/{ano}')
            entradas.append(round(receitas_mes, 2))
            saidas.append(round(despesas_mes, 2))
            saldos.append(round(saldo_corrente, 2))

        return jsonify({
            'success': True,
            'data': {
                'labels': labels,
                'entradas': entradas,
                'saidas': saidas,
                'saldo_projetado': saldos,
                'periodo_inicio': f'{ano_ref:04d}-{mes_ref:02d}',
                'horizonte_meses': horizonte,
                'tipo': 'projecao_simplificada',
                'premissas': [
                    'Baseado em receitas e despesas por competência já disponíveis',
                    'Não considera cenários múltiplos nem previsão estatística avançada',
                    'Uso gerencial para acompanhamento de tendência'
                ]
            }
        }), 200
    except Exception:
        return _internal_error('fluxo_caixa_projetado')
