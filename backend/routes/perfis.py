from flask import Blueprint, jsonify, request, session

from backend.models import db
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


@perfis_bp.route('/config', methods=['GET'])
def listar_perfis_financeiros_config():
    perfis = PerfilFinanceiroService.listar_perfis_config()
    perfil_ativo = PerfilFinanceiroService.obter_perfil_ativo(session)
    return jsonify({
        'perfis': [PerfilFinanceiroService.serializar_perfil(perfil) for perfil in perfis],
        'perfil_ativo': PerfilFinanceiroService.serializar_perfil(perfil_ativo),
    })


@perfis_bp.route('', methods=['POST'])
def criar_perfil_financeiro():
    try:
        perfil = PerfilFinanceiroService.criar_perfil(request.get_json(silent=True) or {})
        db.session.commit()
        return jsonify({'perfil': PerfilFinanceiroService.serializar_perfil(perfil)}), 201
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc), 'code': 'PERFIL_FINANCEIRO_VALIDACAO'}), 400


@perfis_bp.route('/<int:perfil_id>', methods=['PUT'])
def atualizar_perfil_financeiro(perfil_id):
    try:
        perfil = PerfilFinanceiroService.atualizar_perfil(perfil_id, request.get_json(silent=True) or {})
        db.session.commit()
        return jsonify({'perfil': PerfilFinanceiroService.serializar_perfil(perfil)})
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc), 'code': 'PERFIL_FINANCEIRO_VALIDACAO'}), 400


@perfis_bp.route('/<int:perfil_id>/inativar', methods=['POST'])
def inativar_perfil_financeiro(perfil_id):
    try:
        perfil = PerfilFinanceiroService.inativar_perfil(perfil_id, session)
        db.session.commit()
        return jsonify({'perfil': PerfilFinanceiroService.serializar_perfil(perfil)})
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc), 'code': 'PERFIL_FINANCEIRO_VALIDACAO'}), 400


@perfis_bp.route('/<int:perfil_id>/reativar', methods=['POST'])
def reativar_perfil_financeiro(perfil_id):
    try:
        perfil = PerfilFinanceiroService.reativar_perfil(perfil_id)
        db.session.commit()
        return jsonify({'perfil': PerfilFinanceiroService.serializar_perfil(perfil)})
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc), 'code': 'PERFIL_FINANCEIRO_VALIDACAO'}), 400


@perfis_bp.route('/<int:perfil_id>/padrao', methods=['POST'])
def definir_perfil_financeiro_padrao(perfil_id):
    try:
        perfil = PerfilFinanceiroService.definir_perfil_padrao(perfil_id)
        db.session.commit()
        return jsonify({'perfil': PerfilFinanceiroService.serializar_perfil(perfil)})
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc), 'code': 'PERFIL_FINANCEIRO_VALIDACAO'}), 400


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
