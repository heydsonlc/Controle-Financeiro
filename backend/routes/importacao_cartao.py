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
from backend.services.importacao_cartao_unificado_service import ImportacaoCartaoUnificadoService
from backend.services.categoria_cartao_service import CategoriaCartaoService
from backend.models import db, ItemDespesa, Categoria, ItemAgregado

bp = Blueprint('importacao_cartao', __name__, url_prefix='/api/importacao-cartao')


@bp.route('/analisar', methods=['POST'])
def analisar_importacao_cartao():
    """
    Analisa CSV/XLSX/PDF e retorna payload intermediario unico.
    Nao persiste lancamentos.
    """
    try:
        arquivo = request.files.get('arquivo')
        cartao_id = request.form.get('cartao_id')
        competencia = request.form.get('competencia')
        formato = request.form.get('formato') or 'automatico'

        if not arquivo or arquivo.filename == '':
            return jsonify({'success': False, 'error': 'Nenhum arquivo enviado'}), 400
        if not cartao_id:
            return jsonify({'success': False, 'error': 'cartao_id obrigatorio'}), 400
        if not competencia:
            return jsonify({'success': False, 'error': 'competencia obrigatoria'}), 400

        payload = ImportacaoCartaoUnificadoService.analisar_arquivo_cartao(
            file_storage=arquivo,
            cartao_id=cartao_id,
            competencia=competencia,
            formato=formato
        )

        return jsonify({
            'success': True,
            'data': payload
        })
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception:
        return jsonify({'success': False, 'error': 'Falha ao analisar arquivo de cartao'}), 500


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

        # Ler e analisar CSV completo
        delimitador, colunas, linhas_dados, linhas_amostra, total_linhas = ImportacaoCartaoService.ler_csv(arquivo)
        perfil_info = ImportacaoCartaoService.detectar_perfil_csv(colunas)

        return jsonify({
            'success': True,
            'delimitador': delimitador,
            'colunas': colunas,
            'linhas_dados': linhas_dados,
            'linhas_amostra': linhas_amostra,
            'total_linhas': total_linhas,
            'perfil_detectado': perfil_info.get('perfil'),
            'autodeteccao_confianca': perfil_info.get('confianca'),
            'mapeamento_sugerido': perfil_info.get('mapeamento_sugerido', {}),
            'perfis_suportados': [
                {'id': ImportacaoCartaoService.PERFIL_NUBANK, 'nome': 'Nubank CSV simples'},
                {'id': ImportacaoCartaoService.PERFIL_CAIXA, 'nome': 'Caixa (Credito/Debito)'},
                {'id': ImportacaoCartaoService.PERFIL_MANUAL, 'nome': 'Manual generico'}
            ]
        })

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


def _validar_payload_importacao(data):
    if not data:
        return None, ('Payload JSON ausente ou invalido', 400)

    cartao_id = data.get('cartao_id')
    competencia_str = data.get('competencia')
    linhas = data.get('linhas', [])

    if not cartao_id:
        return None, ('cartao_id obrigatorio', 400)

    if not competencia_str:
        return None, ('competencia obrigatoria', 400)

    if not isinstance(linhas, list) or not linhas:
        return None, ('Nenhuma linha para processar', 400)

    # Verificar se cartão existe
    cartao = ItemDespesa.query.get(cartao_id)
    if not cartao or cartao.tipo != 'Agregador':
        return None, ('Cartao invalido', 400)
    cartao_id = cartao.id

    categorias_cartao_ids = {
        item.id for item in ItemAgregado.query.filter_by(item_despesa_id=cartao_id, ativo=True).all()
    }
    for idx, linha in enumerate(linhas, start=1):
        if linha.get('ignorar'):
            continue
        item_agregado_id = linha.get('item_agregado_id')
        categoria_cartao_id = linha.get('categoria_cartao_id')
        if item_agregado_id:
            try:
                item_agregado_id = int(item_agregado_id)
            except (TypeError, ValueError):
                return None, (f'Linha {idx} com Categoria do Cartao invalida', 400)
            if item_agregado_id not in categorias_cartao_ids:
                return None, (f'Linha {idx} usa Categoria do Cartao que nao pertence ao cartao selecionado', 400)
            linha['item_agregado_id'] = item_agregado_id
        if categoria_cartao_id:
            try:
                categoria_cartao_id = int(categoria_cartao_id)
            except (TypeError, ValueError):
                return None, (f'Linha {idx} com Categoria do Cartao global invalida', 400)
            if not CategoriaCartaoService.validar_categoria_cartao_disponivel_no_cartao(cartao_id, categoria_cartao_id):
                linha.setdefault('avisos', []).append(
                    'Esta Categoria do Cartao ainda nao possui limite definido neste cartao.'
                )
            linha['categoria_cartao_id'] = categoria_cartao_id
        elif not item_agregado_id:
            linha.setdefault('avisos', []).append(
                'Categoria do Cartao ainda nao configurada para esta Categoria de Despesa.'
            )

    try:
        competencia = datetime.strptime(competencia_str, '%Y-%m-%d').date().replace(day=1)
    except ValueError:
        return None, ('competencia deve estar no formato YYYY-MM-DD', 400)

    return {
        'cartao_id': cartao_id,
        'competencia': competencia,
        'linhas': linhas
    }, None


def _executar_importacao(data, dry_run=False):
    validado, erro = _validar_payload_importacao(data)
    if erro:
        mensagem, status = erro
        return jsonify({'success': False, 'message': mensagem}), status

    resultado_processamento = ImportacaoCartaoService.processar_linhas_mapeadas(
        validado['linhas'],
        validado['cartao_id'],
        validado['competencia']
    )

    lancamentos = resultado_processamento['lancamentos']
    linhas_invalidas = resultado_processamento['linhas_invalidas']
    total_recebidas = resultado_processamento['total_linhas_recebidas']

    resultado = ImportacaoCartaoService.persistir_lancamentos(lancamentos, dry_run=dry_run)

    erros = list(resultado.get('erros', []))
    for item in linhas_invalidas:
        erros.append({
            'linha': item.get('linha'),
            'erro': item.get('erro')
        })

    payload = {
        'success': True,
        'modo': 'previsualizacao' if dry_run else 'persistencia',
        'total_recebidas': total_recebidas,
        'linhas_validas': len(lancamentos),
        'linhas_invalidas': len(linhas_invalidas),
        'inseridos': resultado.get('inseridos', 0),
        'duplicados': resultado.get('duplicados', 0),
        'erros': erros,
        'amostra_duplicados': resultado.get('amostra_duplicados', []),
        'amostra_erros': resultado.get('amostra_erros', []),
        'amostra_validos': [
            {
                'descricao': l.get('descricao_exibida') or l.get('descricao'),
                'valor': float(l.get('valor', 0)),
                'data_compra': l.get('data_compra').isoformat() if l.get('data_compra') else None,
                'numero_parcela': l.get('numero_parcela'),
                'total_parcelas': l.get('total_parcelas')
            }
            for l in lancamentos[:20]
        ]
    }

    return jsonify(payload)


@bp.route('/previsualizar', methods=['POST'])
def previsualizar_importacao():
    """
    Executa validacao completa e deduplicacao sem persistir no banco.
    """
    try:
        data = request.get_json(silent=True)
        return _executar_importacao(data, dry_run=True)
    except Exception:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Falha ao gerar previsualizacao'}), 500


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
        data = request.get_json(silent=True)
        return _executar_importacao(data, dry_run=False)
    except Exception:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Falha ao processar importacao'}), 500


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
    limites = CategoriaCartaoService.listar_limites_cartao(cartao_id, ativo=True)
    categorias = []
    for limite in limites:
        categoria = limite.categoria_cartao
        if not categoria or not categoria.ativo:
            continue
        item = categoria.to_dict()
        item['limite_id'] = limite.id
        item['limite_mensal'] = float(limite.limite_mensal or 0)
        item['categoria_cartao_id'] = categoria.id
        categorias.append(item)
    return jsonify({
        'success': True,
        'categorias_cartao': categorias,
        'data': categorias
    })


@bp.route('/sugerir-categorias', methods=['POST'])
def sugerir_categorias():
    """
    Sugestao automatica simples de categoria por historico de descricao.
    """
    try:
        data = request.get_json(silent=True) or {}
        descricoes = data.get('descricoes') or []
        categoria_fallback_id = data.get('categoria_fallback_id')

        if not isinstance(descricoes, list):
            return jsonify({'success': False, 'message': 'descricoes deve ser uma lista'}), 400

        sugestoes = {}
        for descricao in descricoes:
            if descricao is None:
                continue
            categoria_id, origem = ImportacaoCartaoService.sugerir_categoria_por_descricao(
                descricao_bruta=str(descricao),
                categoria_fallback_id=categoria_fallback_id
            )
            sugestoes[str(descricao)] = {
                'categoria_id': categoria_id,
                'origem': origem
            }

        return jsonify({
            'success': True,
            'sugestoes': sugestoes
        })
    except Exception:
        return jsonify({'success': False, 'message': 'Falha ao sugerir categorias'}), 500
