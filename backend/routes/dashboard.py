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

try:
    from backend.models import db, Conta, Categoria, ItemDespesa, ConfigAgregador, ItemReceita, ReceitaRealizada, ContaBancaria, Financiamento, FinanciamentoParcela, ItemAgregado, ReceitaOrcamento, LancamentoAgregado, OrcamentoAgregado
except ImportError:
    from models import db, Conta, Categoria, ItemDespesa, ConfigAgregador, ItemReceita, ReceitaRealizada, ContaBancaria, Financiamento, FinanciamentoParcela, ItemAgregado, ReceitaOrcamento, LancamentoAgregado, OrcamentoAgregado

# Criar blueprint
dashboard_bp = Blueprint('dashboard', __name__)


def decimal_to_float(value):
    """Converte Decimal para float"""
    if value is None:
        return 0.0
    return float(value) if isinstance(value, Decimal) else value


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
        db.or_(
            Conta.is_fatura_cartao == False,
            Conta.is_fatura_cartao.is_(None)
        )
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
        hoje = date.today()
        mes_atual = hoje.month
        ano_atual = hoje.year

        # 1. RECEITAS DO MÊS (Por mês de competência)
        # Se houver ReceitaRealizada correspondente, usa o valor recebido
        # Senão, usa o valor esperado do orçamento

        # Buscar IDs dos orçamentos que JÁ TÊM receita realizada no mês
        orcamentos_com_realizacao = db.session.query(ReceitaRealizada.orcamento_id).filter(
            extract('month', ReceitaRealizada.mes_referencia) == mes_atual,
            extract('year', ReceitaRealizada.mes_referencia) == ano_atual,
            ReceitaRealizada.orcamento_id.isnot(None)
        ).distinct().all()

        ids_orcamentos_realizados = [o[0] for o in orcamentos_com_realizacao]

        # Somar receitas REALIZADAS (confirmadas)
        receitas_realizadas = db.session.query(func.sum(ReceitaRealizada.valor_recebido)).filter(
            extract('month', ReceitaRealizada.mes_referencia) == mes_atual,
            extract('year', ReceitaRealizada.mes_referencia) == ano_atual
        ).scalar() or 0

        # Somar receitas PREVISTAS (apenas as que NÃO foram confirmadas)
        query_previstas = db.session.query(func.sum(ReceitaOrcamento.valor_esperado)).filter(
            extract('month', ReceitaOrcamento.mes_referencia) == mes_atual,
            extract('year', ReceitaOrcamento.mes_referencia) == ano_atual
        )

        if ids_orcamentos_realizados:
            query_previstas = query_previstas.filter(~ReceitaOrcamento.id.in_(ids_orcamentos_realizados))

        receitas_previstas = query_previstas.scalar() or 0

        # Total = Realizadas + Previstas (que não foram realizadas)
        receitas_mes = decimal_to_float(receitas_realizadas) + decimal_to_float(receitas_previstas)

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
                'mes_nome': hoje.strftime('%B/%Y').capitalize()
            }
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================================================
# BLOCO 2: INDICADORES INTELIGENTES
# ============================================================================

@dashboard_bp.route('/indicadores', methods=['GET'])
def indicadores():
    """
    Retorna indicadores inteligentes e insights
    """
    try:
        hoje = date.today()
        mes_atual = hoje.month
        ano_atual = hoje.year

        # 1. MÉDIA HISTÓRICA DE DESPESAS (últimos 3 meses, por competência)
        tres_meses_atras = date(ano_atual, mes_atual, 1) - timedelta(days=90)
        primeiro_dia_mes = date(ano_atual, mes_atual, 1)

        media_historica = db.session.query(func.avg(Conta.valor)).filter(
            Conta.mes_referencia >= tres_meses_atras,
            Conta.mes_referencia < primeiro_dia_mes
        ).scalar() or 0

        # Despesas do mês atual (usa função auxiliar que aplica regra correta)
        despesas_mes_atual = calcular_despesas_mes(mes_atual, ano_atual)

        acima_media = despesas_mes_atual > (decimal_to_float(media_historica) * 1.1)

        # 2. GASTOS PENDENTES PRÓXIMOS (próximos 7 dias)
        proximos_7_dias = hoje + timedelta(days=7)
        gastos_pendentes = db.session.query(func.count(Conta.id)).filter(
            Conta.data_vencimento.between(hoje, proximos_7_dias),
            Conta.status_pagamento == 'Pendente'
        ).scalar() or 0

        # 3. FATURAS DE CARTÃO PENDENTES (mês atual)
        faturas_proximas = db.session.query(func.count(Conta.id)).filter(
            Conta.is_fatura_cartao == True,
            Conta.status_pagamento == 'Pendente',
            extract('month', Conta.mes_referencia) == mes_atual,
            extract('year', Conta.mes_referencia) == ano_atual
        ).scalar() or 0

        # 4. PORCENTAGEM POUPADA
        # Usar mesma lógica do resumo-mes para calcular receitas (confirmadas + previstas não confirmadas)
        orcamentos_com_realizacao = db.session.query(ReceitaRealizada.orcamento_id).filter(
            extract('month', ReceitaRealizada.mes_referencia) == mes_atual,
            extract('year', ReceitaRealizada.mes_referencia) == ano_atual,
            ReceitaRealizada.orcamento_id.isnot(None)
        ).distinct().all()

        ids_orcamentos_realizados = [o[0] for o in orcamentos_com_realizacao]

        receitas_realizadas = db.session.query(func.sum(ReceitaRealizada.valor_recebido)).filter(
            extract('month', ReceitaRealizada.mes_referencia) == mes_atual,
            extract('year', ReceitaRealizada.mes_referencia) == ano_atual
        ).scalar() or 0

        query_previstas = db.session.query(func.sum(ReceitaOrcamento.valor_esperado)).filter(
            extract('month', ReceitaOrcamento.mes_referencia) == mes_atual,
            extract('year', ReceitaOrcamento.mes_referencia) == ano_atual
        )

        if ids_orcamentos_realizados:
            query_previstas = query_previstas.filter(~ReceitaOrcamento.id.in_(ids_orcamentos_realizados))

        receitas_previstas = query_previstas.scalar() or 0
        receitas_mes = decimal_to_float(receitas_realizadas) + decimal_to_float(receitas_previstas)

        despesas_totais = decimal_to_float(despesas_mes_atual)
        receitas_totais = receitas_mes
        percentual_poupado = ((receitas_totais - despesas_totais) / receitas_totais * 100) if receitas_totais > 0 else 0

        # 5. RECEITAS EXTRAS (receitas acima da média ou variáveis)
        receitas_extras = 0  # Simplificado por enquanto

        return jsonify({
            'success': True,
            'data': {
                'despesas_acima_media': acima_media,
                'media_historica': decimal_to_float(media_historica),
                'despesas_mes_atual': decimal_to_float(despesas_mes_atual),
                'gastos_pendentes_proximos': gastos_pendentes,
                'faturas_cartao_proximas': faturas_proximas,
                'percentual_poupado': round(percentual_poupado, 1),
                'receitas_extras': receitas_extras
            }
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================================================
# BLOCO 3: GRÁFICOS
# ============================================================================

@dashboard_bp.route('/grafico-categorias', methods=['GET'])
def grafico_categorias():
    """
    Retorna dados para gráfico de pizza: Distribuição de Despesas por Categoria
    """
    try:
        hoje = date.today()
        mes_atual = hoje.month
        ano_atual = hoje.year

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

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@dashboard_bp.route('/grafico-evolucao', methods=['GET'])
def grafico_evolucao():
    """
    Retorna dados para gráfico de barras: Evolução de Gastos (últimos 6 meses)
    """
    try:
        hoje = date.today()
        meses = []
        valores = []

        # Últimos 6 meses
        for i in range(5, -1, -1):
            # Calcular o primeiro dia do mês i meses atrás
            ano = hoje.year
            mes = hoje.month - i

            if mes <= 0:
                mes += 12
                ano -= 1

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

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@dashboard_bp.route('/grafico-saldo', methods=['GET'])
def grafico_saldo():
    """
    Retorna dados para gráfico de linha: Evolução do Saldo Bancário
    """
    try:
        hoje = date.today()
        meses = []
        saldos = []

        # Saldo atual
        saldo_atual = db.session.query(func.sum(ContaBancaria.saldo_atual)).filter(
            ContaBancaria.status == 'ATIVO'
        ).scalar() or 0

        saldo_atual_float = decimal_to_float(saldo_atual)

        # Últimos 6 meses (simulação simplificada)
        for i in range(5, -1, -1):
            ano = hoje.year
            mes = hoje.month - i

            if mes <= 0:
                mes += 12
                ano -= 1

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

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================================================
# BLOCO 4: ALERTAS E AGENDA FINANCEIRA
# ============================================================================

@dashboard_bp.route('/alertas', methods=['GET'])
def alertas():
    """
    Retorna alertas e agenda financeira
    """
    try:
        hoje = date.today()
        proximos_7_dias = hoje + timedelta(days=7)
        mes_atual = hoje.month
        ano_atual = hoje.year

        # 1. CONTAS A VENCER (Contas pendentes)
        contas_vencer = db.session.query(Conta).outerjoin(
            ItemDespesa, Conta.item_despesa_id == ItemDespesa.id
        ).outerjoin(
            Categoria, ItemDespesa.categoria_id == Categoria.id
        ).filter(
            Conta.data_vencimento.between(hoje, proximos_7_dias),
            Conta.status_pagamento == 'Pendente'
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
            parcela_mes = FinanciamentoParcela.query.filter_by(
                financiamento_id=fin.id,
                mes_referencia=date(ano_atual, mes_atual, 1)
            ).first()

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
                'financiamentos_mes': financiamentos_lista,
                'receitas_previstas': receitas_lista
            }
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
