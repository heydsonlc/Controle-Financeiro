"""
Rotas para interação humana com Despesas Previstas (FASE 2)

Regras:
- Projeção ≠ lançamento: estas rotas NÃO criam despesas reais automaticamente.
- Histórico é imutável: data_original_prevista nunca muda.
- Sem ajuste em cascata: afeta apenas a despesa alvo.
- Apenas status PREVISTA pode ser alterado nesta fase.
"""

from flask import Blueprint, jsonify, request

try:
    from backend.models import db
    from backend.services.despesa_prevista_service import confirmar, adiar, ignorar
except ImportError:
    from models import db
    from services.despesa_prevista_service import confirmar, adiar, ignorar


despesas_previstas_bp = Blueprint('despesas_previstas', __name__)


def _ler_payload_request():
    dados = request.get_json(silent=True)
    if not dados:
        dados = request.form.to_dict()
    return dados or {}


@despesas_previstas_bp.route('/<int:despesa_id>/confirmar', methods=['POST'])
def confirmar_despesa_prevista(despesa_id):
    try:
        desp = confirmar(despesa_id)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Despesa prevista confirmada', 'data': desp.to_dict()}), 200
    except ValueError as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@despesas_previstas_bp.route('/<int:despesa_id>/adiar', methods=['POST'])
def adiar_despesa_prevista(despesa_id):
    try:
        data = _ler_payload_request()
        nova_data = data.get('nova_data')
        ajustar_ciclo = bool(data.get('ajustar_ciclo') or False)
        desp, criada_id = adiar(despesa_id, nova_data, ajustar_ciclo=ajustar_ciclo)
        db.session.commit()
        payload = {'success': True, 'message': 'Despesa prevista adiada', 'data': desp.to_dict()}
        if criada_id:
            payload['ciclo'] = {'ajustado': True, 'despesa_prevista_criada_id': criada_id}
        else:
            payload['ciclo'] = {'ajustado': bool(ajustar_ciclo), 'despesa_prevista_criada_id': None}
        return jsonify(payload), 200
    except ValueError as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@despesas_previstas_bp.route('/<int:despesa_id>/ignorar', methods=['POST'])
def ignorar_despesa_prevista(despesa_id):
    try:
        desp = ignorar(despesa_id)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Despesa prevista ignorada', 'data': desp.to_dict()}), 200
    except ValueError as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
