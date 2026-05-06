from flask import Blueprint, jsonify, request

try:
    from backend.services.ocr_tools_service import OcrToolsService
except ImportError:
    from services.ocr_tools_service import OcrToolsService


ocr_tools_bp = Blueprint('ocr_tools', __name__)


def _json_error(message, status_code=400):
    return jsonify({'success': False, 'error': message}), status_code


@ocr_tools_bp.route('/status', methods=['GET'])
def status_ocr():
    return jsonify(OcrToolsService.obter_status_ocr(salvar=False)), 200


@ocr_tools_bp.route('/autodetectar', methods=['POST'])
def autodetectar_ocr():
    try:
        return jsonify(OcrToolsService.autodetectar_ferramentas_ocr()), 200
    except ValueError as exc:
        return _json_error(str(exc), 400)


@ocr_tools_bp.route('/configurar', methods=['POST'])
def configurar_ocr():
    try:
        payload = request.get_json(silent=True) or {}
        resultado = OcrToolsService.configurar_ferramentas_ocr(payload)
        resultado['message'] = 'Configuracao das ferramentas OCR salva.'
        return jsonify(resultado), 200
    except ValueError as exc:
        return _json_error(str(exc), 400)


@ocr_tools_bp.route('/validar', methods=['POST'])
def validar_ocr():
    return jsonify(OcrToolsService.validar_ferramentas_ocr()), 200
