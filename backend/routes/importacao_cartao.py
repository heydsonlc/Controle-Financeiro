"""
Rotas para Importação Assistida de Fatura de Cartão (CSV)

FASE 6.2

Endpoints:
- POST /api/importacao-cartao/upload - Upload e análise do CSV
- POST /api/importacao-cartao/processar - Processar linhas mapeadas e persistir
"""

from flask import Blueprint, request, jsonify
from datetime import datetime
from backend.services.importacao_cartao_service import ImportacaoCartaoService
from backend.models import db, ItemDespesa, Categoria, ItemAgregado

bp = Blueprint('importacao_cartao', __name__, url_prefix='/api/importacao-cartao')


@bp.route('/upload', methods=['POST'])
def upload_csv():
    """
    Recebe CSV, detecta delimitador, retorna colunas e amostra

    Returns:
        {
            'success': bool,
            'delimitador': str,
            'colunas': [str],
            'linhas_amostra': [[str]],
            'total_linhas': int
        }
    """
    try:
        if 'arquivo' not in request.files:
            return jsonify({'success': False, 'message': 'Nenhum arquivo enviado'}), 400

        arquivo = request.files['arquivo']

        if arquivo.filename == '':
            return jsonify({'success': False, 'message': 'Arquivo vazio'}), 400

        if not arquivo.filename.endswith('.csv'):
            return jsonify({'success': False, 'message': 'Apenas arquivos CSV são permitidos'}), 400

        # Ler e analisar CSV
        delimitador, colunas, linhas_amostra = ImportacaoCartaoService.ler_csv(arquivo)

        # Ler total de linhas
        arquivo.seek(0)
        total_linhas = len(arquivo.read().decode('utf-8', errors='ignore').split('\n')) - 1  # -1 cabeçalho

        return jsonify({
            'success': True,
            'delimitador': delimitador,
            'colunas': colunas,
            'linhas_amostra': linhas_amostra,
            'total_linhas': total_linhas
        })

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@bp.route('/processar', methods=['POST'])
def processar_importacao():
    """
    Processa linhas mapeadas e persiste lançamentos

    Payload:
        {
            'cartao_id': int,
            'competencia': 'YYYY-MM-DD',
            'linhas': [
                {
                    'data_compra': 'YYYY-MM-DD',
                    'descricao': str,
                    'descricao_exibida': str (editável),
                    'valor': str,
                    'parcela': str (opcional, ex: "1/12"),
                    'categoria_id': int,
                    'item_agregado_id': int (opcional)
                }
            ]
        }

    Returns:
        {
            'success': bool,
            'inseridos': int,
            'duplicados': int,
            'erros': []
        }
    """
    try:
        data = request.json

        cartao_id = data.get('cartao_id')
        competencia_str = data.get('competencia')
        linhas = data.get('linhas', [])

        # Validações
        if not cartao_id:
            return jsonify({'success': False, 'message': 'cartao_id obrigatório'}), 400

        if not competencia_str:
            return jsonify({'success': False, 'message': 'competencia obrigatória'}), 400

        if not linhas:
            return jsonify({'success': False, 'message': 'Nenhuma linha para processar'}), 400

        # Verificar se cartão existe
        cartao = ItemDespesa.query.get(cartao_id)
        if not cartao or cartao.tipo != 'Agregador':
            return jsonify({'success': False, 'message': 'Cartão inválido'}), 400

        # Parsear competência
        competencia = datetime.strptime(competencia_str, '%Y-%m-%d').date().replace(day=1)

        # Processar linhas
        lancamentos = ImportacaoCartaoService.processar_linhas_mapeadas(linhas, cartao_id, competencia)

        # Persistir
        resultado = ImportacaoCartaoService.persistir_lancamentos(lancamentos)

        return jsonify({
            'success': True,
            **resultado
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@bp.route('/categorias', methods=['GET'])
def listar_categorias():
    """Lista categorias de despesas disponíveis"""
    categorias = Categoria.query.filter_by(ativo=True).all()
    return jsonify({
        'success': True,
        'categorias': [cat.to_dict() for cat in categorias]
    })


@bp.route('/categorias-cartao/<int:cartao_id>', methods=['GET'])
def listar_categorias_cartao(cartao_id):
    """Lista categorias agregadas do cartão (opcionais)"""
    itens = ItemAgregado.query.filter_by(item_despesa_id=cartao_id, ativo=True).all()
    return jsonify({
        'success': True,
        'categorias_cartao': [item.to_dict() for item in itens]
    })
