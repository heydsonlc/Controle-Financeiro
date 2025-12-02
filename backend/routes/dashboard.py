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
    from backend.models import db, Lancamento, Categoria, Cartao, FonteReceita, Receita, ContaBancaria, Financiamento, Parcela
except ImportError:
    from models import db, Lancamento, Categoria, Cartao, FonteReceita, Receita, ContaBancaria, Financiamento, Parcela

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
    - Total de despesas do mês (lançamentos + cartões)
    - Saldo líquido (receitas - despesas)
    - Saldo total nas contas bancárias
    """
    try:
        hoje = date.today()
        mes_atual = hoje.month
        ano_atual = hoje.year

        # 1. RECEITAS DO MÊS
        receitas_mes = db.session.query(func.sum(Receita.valor)).filter(
            extract('month', Receita.data_recebimento) == mes_atual,
            extract('year', Receita.data_recebimento) == ano_atual,
            Receita.status == 'RECEBIDA'
        ).scalar() or 0

        # 2. DESPESAS DO MÊS
        # Lançamentos do mês
        lancamentos_mes = db.session.query(func.sum(Lancamento.valor)).filter(
            extract('month', Lancamento.data_lancamento) == mes_atual,
            extract('year', Lancamento.data_lancamento) == ano_atual,
            Lancamento.status == 'PAGO'
        ).scalar() or 0

        # Parcelas de cartão do mês (considerar mês de vencimento)
        parcelas_mes = db.session.query(func.sum(Parcela.valor)).filter(
            extract('month', Parcela.data_vencimento) == mes_atual,
            extract('year', Parcela.data_vencimento) == ano_atual,
            Parcela.status == 'PAGA'
        ).scalar() or 0

        despesas_mes = decimal_to_float(lancamentos_mes) + decimal_to_float(parcelas_mes)

        # 3. SALDO LÍQUIDO
        saldo_liquido = decimal_to_float(receitas_mes) - despesas_mes

        # 4. SALDO NAS CONTAS BANCÁRIAS
        saldo_contas = db.session.query(func.sum(ContaBancaria.saldo_atual)).filter(
            ContaBancaria.status == 'ATIVO'
        ).scalar() or 0

        return jsonify({
            'success': True,
            'data': {
                'receitas_mes': decimal_to_float(receitas_mes),
                'despesas_mes': despesas_mes,
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
    Retorna indicadores inteligentes e insights:
    - Despesas acima da média histórica
    - Gastos pendentes próximos ao vencimento
    - Fatura do cartão disponível
    - Porcentagem poupada da renda
    - Receitas extras no mês
    """
    try:
        hoje = date.today()
        mes_atual = hoje.month
        ano_atual = hoje.year

        # 1. MÉDIA HISTÓRICA DE DESPESAS (últimos 3 meses, excluindo o atual)
        tres_meses_atras = hoje - timedelta(days=90)
        media_historica = db.session.query(func.avg(Lancamento.valor)).filter(
            Lancamento.data_lancamento >= tres_meses_atras,
            Lancamento.data_lancamento < date(ano_atual, mes_atual, 1),
            Lancamento.status == 'PAGO'
        ).scalar() or 0

        despesas_mes_atual = db.session.query(func.sum(Lancamento.valor)).filter(
            extract('month', Lancamento.data_lancamento) == mes_atual,
            extract('year', Lancamento.data_lancamento) == ano_atual,
            Lancamento.status == 'PAGO'
        ).scalar() or 0

        acima_media = decimal_to_float(despesas_mes_atual) > decimal_to_float(media_historica) * 1.1

        # 2. GASTOS PENDENTES PRÓXIMOS (próximos 7 dias)
        proximos_7_dias = hoje + timedelta(days=7)
        gastos_pendentes = db.session.query(func.count(Lancamento.id)).filter(
            Lancamento.data_vencimento.between(hoje, proximos_7_dias),
            Lancamento.status == 'PENDENTE'
        ).scalar() or 0

        # 3. FATURA DE CARTÃO PRÓXIMA (próximos 7 dias)
        # Procurar cartões com vencimento próximo
        dia_atual = hoje.day
        faturas_proximas = db.session.query(func.count(Cartao.id)).filter(
            Cartao.dia_vencimento.between(dia_atual, dia_atual + 7)
        ).scalar() or 0

        # 4. PORCENTAGEM POUPADA
        receitas_mes = db.session.query(func.sum(Receita.valor)).filter(
            extract('month', Receita.data_recebimento) == mes_atual,
            extract('year', Receita.data_recebimento) == ano_atual,
            Receita.status == 'RECEBIDA'
        ).scalar() or 0

        despesas_totais = decimal_to_float(despesas_mes_atual)
        receitas_totais = decimal_to_float(receitas_mes)
        percentual_poupado = ((receitas_totais - despesas_totais) / receitas_totais * 100) if receitas_totais > 0 else 0

        # 5. RECEITAS EXTRAS (receitas variáveis)
        receitas_extras = db.session.query(func.sum(Receita.valor)).join(FonteReceita).filter(
            extract('month', Receita.data_recebimento) == mes_atual,
            extract('year', Receita.data_recebimento) == ano_atual,
            Receita.status == 'RECEBIDA',
            FonteReceita.tipo == 'VARIAVEL'
        ).scalar() or 0

        return jsonify({
            'success': True,
            'data': {
                'despesas_acima_media': acima_media,
                'media_historica': decimal_to_float(media_historica),
                'despesas_mes_atual': decimal_to_float(despesas_mes_atual),
                'gastos_pendentes_proximos': gastos_pendentes,
                'faturas_cartao_proximas': faturas_proximas,
                'percentual_poupado': round(percentual_poupado, 1),
                'receitas_extras': decimal_to_float(receitas_extras)
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

        # Agrupar despesas por categoria no mês atual
        resultado = db.session.query(
            Categoria.nome,
            Categoria.cor,
            func.sum(Lancamento.valor).label('total')
        ).join(
            Lancamento, Lancamento.categoria_id == Categoria.id
        ).filter(
            extract('month', Lancamento.data_lancamento) == mes_atual,
            extract('year', Lancamento.data_lancamento) == ano_atual,
            Lancamento.status == 'PAGO'
        ).group_by(
            Categoria.id, Categoria.nome, Categoria.cor
        ).order_by(
            func.sum(Lancamento.valor).desc()
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
            data_referencia = hoje - timedelta(days=i * 30)
            mes = data_referencia.month
            ano = data_referencia.year

            total_mes = db.session.query(func.sum(Lancamento.valor)).filter(
                extract('month', Lancamento.data_lancamento) == mes,
                extract('year', Lancamento.data_lancamento) == ano,
                Lancamento.status == 'PAGO'
            ).scalar() or 0

            meses.append(data_referencia.strftime('%b/%y'))
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
    (Simulação com base em receitas e despesas)
    """
    try:
        hoje = date.today()
        meses = []
        saldos = []

        # Saldo atual
        saldo_atual = db.session.query(func.sum(ContaBancaria.saldo_atual)).filter(
            ContaBancaria.status == 'ATIVO'
        ).scalar() or 0

        saldo_atual = decimal_to_float(saldo_atual)
        saldo_acumulado = saldo_atual

        # Últimos 6 meses (retroativo)
        for i in range(5, -1, -1):
            data_referencia = hoje - timedelta(days=i * 30)
            mes = data_referencia.month
            ano = data_referencia.year

            # Receitas do mês
            receitas = db.session.query(func.sum(Receita.valor)).filter(
                extract('month', Receita.data_recebimento) == mes,
                extract('year', Receita.data_recebimento) == ano,
                Receita.status == 'RECEBIDA'
            ).scalar() or 0

            # Despesas do mês
            despesas = db.session.query(func.sum(Lancamento.valor)).filter(
                extract('month', Lancamento.data_lancamento) == mes,
                extract('year', Lancamento.data_lancamento) == ano,
                Lancamento.status == 'PAGO'
            ).scalar() or 0

            # Calcular saldo (retroativo: subtrair das receitas futuras)
            if i > 0:
                saldo_acumulado -= (decimal_to_float(receitas) - decimal_to_float(despesas))

            meses.append(data_referencia.strftime('%b/%y'))
            saldos.append(round(saldo_acumulado, 2))

        # Inverter para ordem cronológica
        meses.reverse()
        saldos.reverse()

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
    Retorna alertas e agenda financeira:
    - Contas a vencer nos próximos 7 dias
    - Faturas de cartão com vencimento próximo
    - Parcelas de financiamento do mês
    - Receitas fixas previstas
    """
    try:
        hoje = date.today()
        proximos_7_dias = hoje + timedelta(days=7)
        mes_atual = hoje.month
        ano_atual = hoje.year

        # 1. CONTAS A VENCER (Lançamentos pendentes)
        contas_vencer = db.session.query(Lancamento).filter(
            Lancamento.data_vencimento.between(hoje, proximos_7_dias),
            Lancamento.status == 'PENDENTE'
        ).order_by(Lancamento.data_vencimento).limit(10).all()

        # 2. FATURAS DE CARTÃO (próximo vencimento)
        dia_atual = hoje.day
        cartoes_vencer = db.session.query(Cartao).filter(
            Cartao.dia_vencimento.between(dia_atual, dia_atual + 7)
        ).limit(5).all()

        # 3. FINANCIAMENTOS DO MÊS
        financiamentos_mes = db.session.query(Financiamento).filter(
            Financiamento.status == 'ATIVO'
        ).limit(5).all()

        # 4. RECEITAS FIXAS PREVISTAS DO MÊS
        receitas_previstas = db.session.query(Receita).join(FonteReceita).filter(
            extract('month', Receita.data_recebimento) == mes_atual,
            extract('year', Receita.data_recebimento) == ano_atual,
            Receita.status == 'PREVISTA',
            FonteReceita.tipo == 'FIXA'
        ).limit(10).all()

        # Formatar dados
        contas_lista = []
        for lancamento in contas_vencer:
            contas_lista.append({
                'id': lancamento.id,
                'descricao': lancamento.descricao,
                'valor': decimal_to_float(lancamento.valor),
                'data_vencimento': lancamento.data_vencimento.strftime('%d/%m/%Y'),
                'categoria': lancamento.categoria.nome if lancamento.categoria else 'Sem categoria',
                'tipo': 'lancamento'
            })

        cartoes_lista = []
        for cartao in cartoes_vencer:
            cartoes_lista.append({
                'id': cartao.id,
                'nome': cartao.nome,
                'dia_vencimento': cartao.dia_vencimento,
                'tipo': 'cartao'
            })

        financiamentos_lista = []
        for fin in financiamentos_mes:
            financiamentos_lista.append({
                'id': fin.id,
                'descricao': fin.descricao,
                'valor_parcela': decimal_to_float(fin.valor_parcela_inicial) if fin.valor_parcela_inicial else 0,
                'parcela_atual': fin.parcelas_pagas,
                'total_parcelas': fin.prazo_total_meses,
                'tipo': 'financiamento'
            })

        receitas_lista = []
        for receita in receitas_previstas:
            receitas_lista.append({
                'id': receita.id,
                'descricao': receita.descricao,
                'valor': decimal_to_float(receita.valor),
                'data_recebimento': receita.data_recebimento.strftime('%d/%m/%Y'),
                'fonte': receita.fonte_receita.nome if receita.fonte_receita else 'Sem fonte',
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
