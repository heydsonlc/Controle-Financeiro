from flask import Blueprint, jsonify, request, session

from backend.services.perfil_financeiro_service import PerfilFinanceiroService


perfis_bp = Blueprint('perfis_financeiros', __name__, url_prefix='/api/perfis-financeiros')


@perfis_bp.route('', methods=['GET'])
def listar_perfis_financeiros():
    perfis = PerfilFinanceiroService.listar_perfis_ativos()
    perfil_ativo = PerfilFinanceiroService.obter_perfil_ativo(session)

    return jsonify({
        'perfis': [PerfilFinanceiroService.serializar_perfil(perfil) for perfil in perfis],
        'perfil_ativo': PerfilFinanceiroService.serializar_perfil(perfil_ativo),
        'isolamento_dados_ativo': False,
    })


@perfis_bp.route('/ativo', methods=['GET'])
def obter_perfil_financeiro_ativo():
    perfil_ativo = PerfilFinanceiroService.obter_perfil_ativo(session)
    return jsonify({
        'perfil_ativo': PerfilFinanceiroService.serializar_perfil(perfil_ativo),
        'isolamento_dados_ativo': False,
    })


@perfis_bp.route('/ativo', methods=['POST'])
def definir_perfil_financeiro_ativo():
    data = request.get_json(silent=True) or {}
    perfil = PerfilFinanceiroService.definir_perfil_ativo(session, data.get('perfil_id'))

    if not perfil:
        return jsonify({
            'error': 'Perfil financeiro nao encontrado ou inativo',
            'code': 'PERFIL_FINANCEIRO_INVALIDO',
        }), 404

    return jsonify({
        'perfil_ativo': PerfilFinanceiroService.serializar_perfil(perfil),
        'isolamento_dados_ativo': False,
    })
