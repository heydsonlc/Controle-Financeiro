"""
Rotas da API para Dashboard - Dados Consolidados

Endpoints:
- GET /api/dashboard/resumo-mes         - Resumo financeiro do mês atual
- GET /api/dashboard/indicadores        - Indicadores inteligentes e insights
- GET /api/dashboard/grafico-categorias - Dados para gráfico de pizza (despesas por categoria)
- GET /api/dashboard/grafico-evolucao   - Dados para gráfico de evolução (últimos 6 meses)
- GET /api/dashboard/grafico-saldo      - Dados para gráfico de linha (evolução do saldo)
- GET /api/dashboard/alertas            - Alertas e agenda financeira (próximos vencimentos)
"""
from flask import Blueprint, request, jsonify
from datetime import datetime, date, timedelta
from sqlalchemy import func, extract
from decimal import Decimal

try:
    from backend.models import db, Conta, Categoria, ItemDespesa, ConfigAgregador, ItemReceita, ReceitaRealizada, ContaBancaria, Financiamento, FinanciamentoParcela, ItemAgregado, ReceitaOrcamento
except ImportError:
    from models import db, Conta, Categoria, ItemDespesa, ConfigAgregador, ItemReceita, ReceitaRealizada, ContaBancaria, Financiamento, FinanciamentoParcela, ItemAgregado, ReceitaOrcamento

# Criar blueprint
dashboard_bp = Blueprint('dashboard', __name__)


def decimal_to_float(value):
    """Converte Decimal para float"""
    if value is None:
        return 0.0
    return float(value) if isinstance(value, Decimal) else value


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

        # 1. RECEITAS DO MÊS (ReceitaRealizada)
        receitas_mes = db.session.query(func.sum(ReceitaRealizada.valor_recebido)).filter(
            extract('month', ReceitaRealizada.data_recebimento) == mes_atual,
            extract('year', ReceitaRealizada.data_recebimento) == ano_atual
        ).scalar() or 0

        # 2. DESPESAS DO MÊS (Contas pagas)
        despesas_mes = db.session.query(func.sum(Conta.valor)).filter(
            extract('month', Conta.data_pagamento) == mes_atual,
            extract('year', Conta.data_pagamento) == ano_atual,
            Conta.status_pagamento == 'Pago'
        ).scalar() or 0

        # 3. SALDO LÍQUIDO
        receitas_float = decimal_to_float(receitas_mes)
        despesas_float = decimal_to_float(despesas_mes)
        saldo_liquido = receitas_float - despesas_float

        # 4. SALDO NAS CONTAS BANCÁRIAS
        saldo_contas = db.session.query(func.sum(ContaBancaria.saldo_atual)).filter(
            ContaBancaria.status == 'ATIVO'
        ).scalar() or 0

        return jsonify({
            'success': True,
            'data': {
                'receitas_mes': receitas_float,
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

        # 1. MÉDIA HISTÓRICA DE DESPESAS (últimos 3 meses)
        tres_meses_atras = hoje - timedelta(days=90)
        primeiro_dia_mes = date(ano_atual, mes_atual, 1)

        media_historica = db.session.query(func.avg(Conta.valor)).filter(
            Conta.data_pagamento >= tres_meses_atras,
            Conta.data_pagamento < primeiro_dia_mes,
            Conta.status_pagamento == 'Pago'
        ).scalar() or 0

        despesas_mes_atual = db.session.query(func.sum(Conta.valor)).filter(
            extract('month', Conta.data_pagamento) == mes_atual,
            extract('year', Conta.data_pagamento) == ano_atual,
            Conta.status_pagamento == 'Pago'
        ).scalar() or 0

        acima_media = decimal_to_float(despesas_mes_atual) > (decimal_to_float(media_historica) * 1.1)

        # 2. GASTOS PENDENTES PRÓXIMOS (próximos 7 dias)
        proximos_7_dias = hoje + timedelta(days=7)
        gastos_pendentes = db.session.query(func.count(Conta.id)).filter(
            Conta.data_vencimento.between(hoje, proximos_7_dias),
            Conta.status_pagamento == 'Pendente'
        ).scalar() or 0

        # 3. FATURAS DE CARTÃO (simplificado - contar cartões ativos)
        faturas_proximas = db.session.query(func.count(ConfigAgregador.id)).filter(
            ConfigAgregador.ativo == True
        ).scalar() or 0

        # 4. PORCENTAGEM POUPADA
        receitas_mes = db.session.query(func.sum(ReceitaRealizada.valor_recebido)).filter(
            extract('month', ReceitaRealizada.data_recebimento) == mes_atual,
            extract('year', ReceitaRealizada.data_recebimento) == ano_atual
        ).scalar() or 0

        despesas_totais = decimal_to_float(despesas_mes_atual)
        receitas_totais = decimal_to_float(receitas_mes)
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

        # Agrupar despesas por categoria via ItemDespesa
        resultado = db.session.query(
            Categoria.nome,
            Categoria.cor,
            func.sum(Conta.valor).label('total')
        ).join(
            ItemDespesa, Conta.item_despesa_id == ItemDespesa.id
        ).join(
            Categoria, ItemDespesa.categoria_id == Categoria.id
        ).filter(
            extract('month', Conta.data_pagamento) == mes_atual,
            extract('year', Conta.data_pagamento) == ano_atual,
            Conta.status_pagamento == 'Pago'
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

            total_mes = db.session.query(func.sum(Conta.valor)).filter(
                extract('month', Conta.data_pagamento) == mes,
                extract('year', Conta.data_pagamento) == ano,
                Conta.status_pagamento == 'Pago'
            ).scalar() or 0

            # Formato do mês
            data_ref = date(ano, mes, 1)
            meses.append(data_ref.strftime('%b/%y'))
            valores.append(decimal_to_float(total_mes))

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
            receitas_mes = db.session.query(func.sum(ReceitaRealizada.valor_recebido)).filter(
                extract('month', ReceitaRealizada.data_recebimento) == mes,
                extract('year', ReceitaRealizada.data_recebimento) == ano
            ).scalar() or 0

            despesas_mes = db.session.query(func.sum(Conta.valor)).filter(
                extract('month', Conta.data_pagamento) == mes,
                extract('year', Conta.data_pagamento) == ano,
                Conta.status_pagamento == 'Pago'
            ).scalar() or 0

            diferencial = decimal_to_float(receitas_mes) - decimal_to_float(despesas_mes)

            # Projetar saldo (aproximação)
            saldo_mes = saldo_atual_float - (diferencial * (i + 1))

            data_ref = date(ano, mes, 1)
            meses.append(data_ref.strftime('%b/%y'))
            saldos.append(round(saldo_mes, 2))

        return jsonify({
            'success': True,
            'data': {
                'labels': meses,
                'valores': saldos
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
        contas_vencer = db.session.query(Conta).join(
            ItemDespesa
        ).join(
            Categoria
        ).filter(
            Conta.data_vencimento.between(hoje, proximos_7_dias),
            Conta.status_pagamento == 'Pendente'
        ).order_by(Conta.data_vencimento).limit(10).all()

        # 2. CARTÕES ATIVOS
        cartoes_vencer = db.session.query(ConfigAgregador).filter(
            ConfigAgregador.ativo == True
        ).limit(5).all()

        # 3. FINANCIAMENTOS ATIVOS
        financiamentos_mes = db.session.query(Financiamento).filter(
            Financiamento.status == 'ATIVO'
        ).limit(5).all()

        # 4. RECEITAS PREVISTAS (via orçamento)
        receitas_previstas = db.session.query(ReceitaOrcamento).join(
            ItemReceita
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
        for cartao in cartoes_vencer:
            cartoes_lista.append({
                'id': cartao.id,
                'nome': cartao.item_despesa.nome if cartao.item_despesa else 'Cartão',
                'dia_vencimento': cartao.dia_vencimento if hasattr(cartao, 'dia_vencimento') else 10,
                'tipo': 'cartao'
            })

        financiamentos_lista = []
        for fin in financiamentos_mes:
            financiamentos_lista.append({
                'id': fin.id,
                'descricao': fin.descricao,
                'valor_parcela': decimal_to_float(fin.valor_parcela_inicial) if hasattr(fin, 'valor_parcela_inicial') and fin.valor_parcela_inicial else 0,
                'parcela_atual': fin.parcelas_pagas if hasattr(fin, 'parcelas_pagas') else 0,
                'total_parcelas': fin.prazo_total_meses,
                'tipo': 'financiamento'
            })

        receitas_lista = []
        for orcamento in receitas_previstas:
            receitas_lista.append({
                'id': orcamento.id,
                'descricao': orcamento.item_receita.nome if orcamento.item_receita else 'Receita',
                'valor': decimal_to_float(orcamento.valor_previsto),
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
