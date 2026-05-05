import json

from flask import Blueprint, Response, jsonify, request, send_file

try:
    from backend.services.backup_service import BackupService
except ImportError:  # pragma: no cover
    from services.backup_service import BackupService


backup_bp = Blueprint('backup', __name__)


@backup_bp.route('/status', methods=['GET'])
def status_backup():
    return jsonify(BackupService.obter_status_backup()), 200


@backup_bp.route('/historico', methods=['GET'])
def historico_backup():
    historico = BackupService.listar_backups()
    return jsonify({
        'success': True,
        'data': historico,
        'total': len(historico),
    }), 200


@backup_bp.route('/executar', methods=['POST'])
def executar_backup():
    resultado = BackupService.executar_backup_manual()
    if resultado.get('status') != 'concluido':
        return jsonify({
            'success': False,
            'error': resultado.get('mensagem') or 'Falha ao executar backup.',
            'data': resultado,
        }), 200
    return jsonify({
        'success': True,
        'message': resultado.get('mensagem') or 'Backup concluído.',
        'data': resultado,
    }), 200


@backup_bp.route('/download/<path:nome_arquivo>', methods=['GET'])
def baixar_backup(nome_arquivo):
    try:
        caminho = BackupService.baixar_backup(nome_arquivo)
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    except FileNotFoundError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 404

    return send_file(caminho, as_attachment=True, download_name=caminho.name)


@backup_bp.route('/restaurar', methods=['POST'])
def restaurar_backup():
    payload = request.get_json(silent=True) or {}
    try:
        resultado = BackupService.restaurar_backup(
            payload.get('arquivo'),
            payload.get('confirmacao'),
        )
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    except FileNotFoundError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 404
    except RuntimeError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 503

    return jsonify({
        'success': True,
        'message': resultado.get('mensagem') or 'Restauração concluída.',
        'data': resultado,
    }), 200


@backup_bp.route('/configuracoes/exportar', methods=['GET'])
def exportar_configuracoes():
    payload = BackupService.exportar_configuracoes()
    resposta = Response(
        json.dumps(payload, ensure_ascii=False, indent=2),
        content_type='application/json; charset=utf-8',
    )
    resposta.headers['Content-Disposition'] = 'attachment; filename=configuracoes_controle_financeiro.json'
    return resposta


@backup_bp.route('/configuracoes/importar', methods=['POST'])
def importar_configuracoes():
    payload = request.get_json(silent=True)
    try:
        resultado = BackupService.importar_configuracoes(payload)
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    return jsonify({
        'success': True,
        'message': resultado['mensagem'],
        'data': resultado,
    }), 200


@backup_bp.route('/agendamento', methods=['GET'])
def obter_agendamento():
    return jsonify({
        'success': True,
        'data': BackupService.obter_agendamento(),
    }), 200


@backup_bp.route('/agendamento', methods=['POST'])
def salvar_agendamento():
    payload = request.get_json(silent=True) or {}
    agendamento = BackupService.salvar_agendamento(payload)
    return jsonify({
        'success': True,
        'message': 'Configuração de agendamento salva.',
        'data': agendamento,
    }), 200


@backup_bp.route('/ferramentas/status', methods=['GET'])
def status_ferramentas():
    return jsonify(BackupService.validar_ferramentas_postgres(salvar=True)), 200


@backup_bp.route('/ferramentas/configurar', methods=['POST'])
def configurar_ferramentas():
    payload = request.get_json(silent=True) or {}
    resultado = BackupService.configurar_ferramentas_postgres(payload)
    return jsonify({
        **resultado,
        'message': 'Configuração das ferramentas PostgreSQL salva.',
    }), 200


@backup_bp.route('/ferramentas/autodetectar', methods=['POST'])
def autodetectar_ferramentas():
    resultado = BackupService.autodetectar_ferramentas_postgres()
    return jsonify(resultado), 200
