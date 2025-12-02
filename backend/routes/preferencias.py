"""
Rotas da API para Preferências e Configurações Gerais

Endpoints:
- GET /api/preferencias       - Obter preferências atuais
- PUT /api/preferencias       - Atualizar preferências
"""
from flask import Blueprint, request, jsonify

try:
    from backend.models import db, Preferencia
except ImportError:
    from models import db, Preferencia

# Criar blueprint
preferencias_bp = Blueprint('preferencias', __name__)


@preferencias_bp.route('', methods=['GET'])
def get_preferencias():
    """
    Retorna as preferências atuais do sistema
    Sistema singleton - retorna o primeiro e único registro
    """
    try:
        # Buscar o primeiro registro (singleton)
        preferencia = Preferencia.query.first()

        if not preferencia:
            # Se não existe, criar com valores padrão
            preferencia = Preferencia(
                nome_usuario='Usuário',
                tema_sistema='escuro',
                cor_principal='#3b82f6'
            )
            db.session.add(preferencia)
            db.session.commit()

        return jsonify({
            'success': True,
            'data': preferencia.to_dict()
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@preferencias_bp.route('', methods=['PUT'])
def update_preferencias():
    """
    Atualiza as preferências do sistema
    Aceita qualquer combinação de campos das 5 abas
    """
    try:
        data = request.get_json()

        # Buscar preferência existente
        preferencia = Preferencia.query.first()

        if not preferencia:
            # Criar se não existir
            preferencia = Preferencia()
            db.session.add(preferencia)

        # Atualizar campos enviados (ABA 1: Dados Pessoais)
        if 'nome_usuario' in data:
            preferencia.nome_usuario = data['nome_usuario']
        if 'renda_principal' in data:
            preferencia.renda_principal = data['renda_principal']
        if 'mes_inicio_planejamento' in data:
            preferencia.mes_inicio_planejamento = data['mes_inicio_planejamento']
        if 'dia_fechamento_mes' in data:
            preferencia.dia_fechamento_mes = data['dia_fechamento_mes']

        # ABA 2: Comportamento - Lançamentos
        if 'ajustar_competencia_automatico' in data:
            preferencia.ajustar_competencia_automatico = data['ajustar_competencia_automatico']
        if 'exibir_aviso_despesa_vencida' in data:
            preferencia.exibir_aviso_despesa_vencida = data['exibir_aviso_despesa_vencida']
        if 'solicitar_confirmacao_exclusao' in data:
            preferencia.solicitar_confirmacao_exclusao = data['solicitar_confirmacao_exclusao']
        if 'vincular_pagamento_cartao_auto' in data:
            preferencia.vincular_pagamento_cartao_auto = data['vincular_pagamento_cartao_auto']

        # ABA 2: Comportamento - Dashboard
        if 'graficos_visiveis' in data:
            preferencia.graficos_visiveis = data['graficos_visiveis']
        if 'insights_inteligentes_ativo' in data:
            preferencia.insights_inteligentes_ativo = data['insights_inteligentes_ativo']
        if 'mostrar_saldo_consolidado' in data:
            preferencia.mostrar_saldo_consolidado = data['mostrar_saldo_consolidado']
        if 'mostrar_evolucao_historica' in data:
            preferencia.mostrar_evolucao_historica = data['mostrar_evolucao_historica']

        # ABA 2: Comportamento - Cartões
        if 'dia_inicio_fatura' in data:
            preferencia.dia_inicio_fatura = data['dia_inicio_fatura']
        if 'dia_corte_fatura' in data:
            preferencia.dia_corte_fatura = data['dia_corte_fatura']
        if 'lancamentos_agrupados' in data:
            preferencia.lancamentos_agrupados = data['lancamentos_agrupados']
        if 'orcamento_por_categoria' in data:
            preferencia.orcamento_por_categoria = data['orcamento_por_categoria']

        # ABA 3: Aparência
        if 'tema_sistema' in data:
            preferencia.tema_sistema = data['tema_sistema']
        if 'cor_principal' in data:
            preferencia.cor_principal = data['cor_principal']
        if 'mostrar_icones_coloridos' in data:
            preferencia.mostrar_icones_coloridos = data['mostrar_icones_coloridos']
        if 'abreviar_valores' in data:
            preferencia.abreviar_valores = data['abreviar_valores']

        # ABA 4: Backup
        if 'backup_automatico' in data:
            preferencia.backup_automatico = data['backup_automatico']

        # ABA 5: IA e Automação
        if 'modo_inteligente_ativo' in data:
            preferencia.modo_inteligente_ativo = data['modo_inteligente_ativo']
        if 'sugestoes_economia' in data:
            preferencia.sugestoes_economia = data['sugestoes_economia']
        if 'classificacao_automatica' in data:
            preferencia.classificacao_automatica = data['classificacao_automatica']
        if 'correcao_categorias' in data:
            preferencia.correcao_categorias = data['correcao_categorias']
        if 'parcelas_recorrentes_auto' in data:
            preferencia.parcelas_recorrentes_auto = data['parcelas_recorrentes_auto']

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Preferências atualizadas com sucesso',
            'data': preferencia.to_dict()
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
