"""
Rotas da API para Caminho de Mobilidade: Transporte por App (FASE 1/2 - projetivo)

Regras:
- Gera apenas DespesaPrevista (nunca cria lanÇõamentos reais automaticamente).
- Uma previsÇœo mensal por competÇ¦ncia (tipo_evento='TRANSPORTE_APP').
- Origem prÇüpria: origem_tipo='TRANSPORTE_APP', origem_id = id do caminho.
"""

from datetime import date

from flask import Blueprint, jsonify, request
from dateutil.relativedelta import relativedelta

try:
    from backend.models import db, DespesaPrevista
    from backend.services.transporte_app_service import (
        ORIGEM_TIPO_TRANSPORTE_APP,
        listar_caminhos_transporte_app,
        obter_config_transporte_app,
        criar_caminho_transporte_app,
        atualizar_caminho_transporte_app,
    )
except ImportError:
    from models import db, DespesaPrevista
    from services.transporte_app_service import (
        ORIGEM_TIPO_TRANSPORTE_APP,
        listar_caminhos_transporte_app,
        obter_config_transporte_app,
        criar_caminho_transporte_app,
        atualizar_caminho_transporte_app,
    )


mobilidade_app_bp = Blueprint('mobilidade_app', __name__)


def _ler_payload_request():
    dados = request.get_json(silent=True)
    if not dados:
        dados = request.form.to_dict()
    return dados or {}


@mobilidade_app_bp.route('', methods=['GET'])
def listar_caminhos():
    try:
        caminhos = listar_caminhos_transporte_app()
        return jsonify({'success': True, 'data': caminhos, 'total': len(caminhos)}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@mobilidade_app_bp.route('', methods=['POST'])
def criar_caminho():
    try:
        data = _ler_payload_request()
        meses = int(data.get('meses_futuros') or 12)
        origem_id = criar_caminho_transporte_app(data, meses_futuros=meses)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Caminho criado', 'data': {'id': origem_id}}), 201
    except ValueError as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@mobilidade_app_bp.route('/<int:caminho_id>', methods=['GET'])
def obter_caminho(caminho_id: int):
    try:
        cfg = obter_config_transporte_app(caminho_id)
        if cfg is None:
            return jsonify({'success': False, 'error': 'Caminho nÇœo encontrado'}), 404
        return jsonify({'success': True, 'data': {'id': caminho_id, **cfg}}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@mobilidade_app_bp.route('/<int:caminho_id>', methods=['PUT'])
def atualizar_caminho(caminho_id: int):
    try:
        data = _ler_payload_request()
        meses = int(data.get('meses_futuros') or 12)
        atualizado = atualizar_caminho_transporte_app(caminho_id, data, meses_futuros=meses)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Caminho atualizado', 'data': {'id': atualizado}}), 200
    except ValueError as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@mobilidade_app_bp.route('/<int:caminho_id>', methods=['DELETE'])
def deletar_caminho(caminho_id: int):
    try:
        itens = DespesaPrevista.query.filter(
            DespesaPrevista.origem_tipo == ORIGEM_TIPO_TRANSPORTE_APP,
            DespesaPrevista.origem_id == caminho_id,
        ).all()
        if not itens:
            return jsonify({'success': False, 'error': 'Caminho nÇœo encontrado'}), 404
        for d in itens:
            db.session.delete(d)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Caminho removido'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@mobilidade_app_bp.route('/<int:caminho_id>/projecoes', methods=['GET'])
def listar_projecoes(caminho_id: int):
    try:
        meses = request.args.get('meses', default=24, type=int)
        if meses < 1:
            meses = 1
        inicio = date.today().replace(day=1)
        fim = (inicio + relativedelta(months=meses)).replace(day=1)

        proj = DespesaPrevista.query.filter(
            DespesaPrevista.origem_tipo == ORIGEM_TIPO_TRANSPORTE_APP,
            DespesaPrevista.origem_id == caminho_id,
            DespesaPrevista.data_prevista >= inicio,
            DespesaPrevista.data_prevista < fim,
        ).order_by(DespesaPrevista.data_prevista.asc(), DespesaPrevista.id.asc()).all()

        return jsonify({'success': True, 'data': [p.to_dict() for p in proj], 'total': len(proj)}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

