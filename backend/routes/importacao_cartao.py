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
from backend.services.importacao_cartao_messages import MSG_CATEGORIA_DESPESA_SEM_CATEGORIA_CARTAO
from backend.services.categoria_palavra_chave_service import CategoriaPalavraChaveService
from backend.services.perfil_financeiro_service import PerfilFinanceiroService
from backend.models import db, ItemDespesa, Categoria

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
    cartao = PerfilFinanceiroService.aplicar_perfil_query(
        ItemDespesa.query, ItemDespesa
    ).filter(ItemDespesa.id == cartao_id).first()
    if not cartao or cartao.tipo != 'Agregador':
        return None, ('Cartao invalido', 400)
    cartao_id = cartao.id

    for idx, linha in enumerate(linhas, start=1):
        if linha.get('ignorar'):
            continue
        categoria_id = linha.get('categoria_id')
        categoria_cartao_id = linha.get('categoria_cartao_id')
        if categoria_cartao_id:
            try:
                categoria_cartao_id = int(categoria_cartao_id)
            except (TypeError, ValueError):
                return None, (f'Linha {idx} com Categoria do Cartao global invalida', 400)
            if not CategoriaCartaoService.validar_categoria_cartao_disponivel_no_cartao(cartao_id, categoria_cartao_id):
                linha.setdefault('avisos', []).append(
                    'Esta Categoria do Cartao ainda nao esta vinculada ao cartao selecionado.'
                )
            linha['categoria_cartao_id'] = categoria_cartao_id
        else:
            try:
                resolucao_cartao = CategoriaCartaoService.resolver_categoria_cartao_para_lancamento(
                    cartao_id=cartao_id,
                    categoria_id=categoria_id,
                ) if categoria_id else {}
            except ValueError as exc:
                return None, (str(exc), 400)

            categoria_cartao_resolvida = resolucao_cartao.get('categoria_cartao_id')
            if categoria_cartao_resolvida:
                linha['categoria_cartao_id'] = int(categoria_cartao_resolvida)
                linha['categoria_cartao_origem'] = resolucao_cartao.get('origem') or 'mapa_categoria_despesa'
            elif categoria_id:
                if resolucao_cartao.get('categoria_cartao_resolvida_id'):
                    linha.setdefault('avisos', []).append(
                        'Esta categoria da despesa ainda nao esta vinculada ao cartao selecionado.'
                    )
                else:
                    linha.setdefault('avisos', []).append(MSG_CATEGORIA_DESPESA_SEM_CATEGORIA_CARTAO)

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

    linhas_processaveis = [
        linha for linha in validado['linhas']
        if not linha.get('ignorar') and linha.get('tipo_movimento') != 'credito'
    ]
    sem_categoria_despesa = sum(1 for linha in linhas_processaveis if not linha.get('categoria_id'))
    sem_categoria_cartao = sum(
        1 for linha in linhas_processaveis
        if not linha.get('categoria_cartao_id')
    )
    avisos_linhas = []
    for idx, linha in enumerate(validado['linhas'], start=1):
        for aviso in linha.get('avisos') or linha.get('mensagens') or []:
            avisos_linhas.append({
                'linha': idx,
                'aviso': aviso,
                'avisos': [aviso]
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
        'pendencias': {
            'categoria_despesa': sem_categoria_despesa,
            'categoria_cartao': sem_categoria_cartao,
            'avisos': len(avisos_linhas),
        },
        'avisos_linhas': avisos_linhas[:50],
        'amostra_duplicados': resultado.get('amostra_duplicados', []),
        'amostra_erros': resultado.get('amostra_erros', []),
        'amostra_validos': [
            {
                'descricao': l.get('descricao_exibida') or l.get('descricao'),
                'valor': float(l.get('valor', 0)),
                'data_compra': l.get('data_compra').isoformat() if l.get('data_compra') else None,
                'numero_parcela': l.get('numero_parcela'),
                'total_parcelas': l.get('total_parcelas'),
                'categoria_id': l.get('categoria_id'),
                'categoria_cartao_id': l.get('categoria_cartao_id'),
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
                    'categoria_cartao_id': int (opcional)
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


@bp.route('/parcelamento', methods=['POST'])
def criar_parcelamento_importado():
    """
    Cria parcelamento oficial a partir de uma unica linha importada.
    Gera somente a parcela atual e futuras.
    """
    try:
        data = request.get_json(silent=True) or {}
        linhas = data.get('linhas')
        if linhas is None and data.get('linha'):
            linhas = [data.get('linha')]
        if not isinstance(linhas, list) or len(linhas) != 1:
            return jsonify({'success': False, 'message': 'Informe exatamente uma linha para parcelamento'}), 400

        linha = dict(linhas[0] or {})
        try:
            numero_parcela = int(linha.get('numero_parcela') or 1)
            total_parcelas = int(linha.get('total_parcelas') or 1)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'message': 'Parametros de parcela invalidos'}), 400

        if numero_parcela < 1 or total_parcelas <= 1 or numero_parcela > total_parcelas:
            return jsonify({'success': False, 'message': 'Parcela fora do intervalo permitido'}), 400
        if total_parcelas > ImportacaoCartaoService.MAX_PARCELAS_IMPORTACAO:
            return jsonify({'success': False, 'message': 'Total de parcelas acima do limite permitido'}), 400

        linha['numero_parcela'] = numero_parcela
        linha['total_parcelas'] = total_parcelas
        linha['parcela'] = f'{numero_parcela}/{total_parcelas}'
        linha['gerar_parcelas_futuras'] = True
        linha['gerar_apenas_atual_e_futuras'] = True
        linha['ignorar'] = False

        payload = {
            'cartao_id': data.get('cartao_id'),
            'competencia': data.get('competencia'),
            'linhas': [linha],
        }
        return _executar_importacao(payload, dry_run=False)
    except Exception:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Falha ao criar parcelamento importado'}), 500


@bp.route('/recorrencia', methods=['POST'])
def vincular_recorrencia_importada():
    """
    Vincula uma linha importada a uma recorrencia existente.
    Cria a ocorrencia na fatura sem transformar a linha em despesa avulsa.
    """
    try:
        data = request.get_json(silent=True) or {}
        cartao_id = data.get('cartao_id')
        competencia_str = data.get('competencia')
        linha = data.get('linha') or {}
        item_despesa_id = data.get('item_despesa_id') or linha.get('item_despesa_id') or linha.get('recorrencia_id')

        if not cartao_id:
            return jsonify({'success': False, 'message': 'cartao_id obrigatorio'}), 400
        if not competencia_str:
            return jsonify({'success': False, 'message': 'competencia obrigatoria'}), 400
        if not isinstance(linha, dict) or not linha:
            return jsonify({'success': False, 'message': 'Linha da importacao obrigatoria'}), 400
        if not item_despesa_id:
            return jsonify({'success': False, 'message': 'recorrencia obrigatoria'}), 400

        cartao = PerfilFinanceiroService.aplicar_perfil_query(
            ItemDespesa.query, ItemDespesa
        ).filter(ItemDespesa.id == cartao_id).first()
        if not cartao or cartao.tipo != 'Agregador':
            return jsonify({'success': False, 'message': 'Cartao invalido'}), 400

        try:
            competencia = datetime.strptime(competencia_str, '%Y-%m-%d').date().replace(day=1)
            item_despesa_id = int(item_despesa_id)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'message': 'Parametros de recorrencia invalidos'}), 400

        resultado = ImportacaoCartaoService.vincular_linha_recorrencia(
            linha=linha,
            cartao_id=cartao.id,
            competencia=competencia,
            item_despesa_id=item_despesa_id,
        )
        return jsonify({
            'success': True,
            **resultado,
        })
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(exc)}), 400
    except Exception:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Falha ao vincular recorrencia importada'}), 500


@bp.route('/reconhecer', methods=['POST'])
def reconhecer_lancamentos_importados():
    """
    Reconhece possiveis lancamentos conhecidos usando valor, cartao e palavra-chave.
    Nao persiste dados.
    """
    try:
        data = request.get_json(silent=True)
        validado, erro = _validar_payload_importacao(data)
        if erro:
            mensagem, status = erro
            return jsonify({'success': False, 'message': mensagem}), status

        reconhecimentos = ImportacaoCartaoService.reconhecer_linhas_flexivel(
            validado['linhas'],
            validado['cartao_id'],
            validado['competencia']
        )

        return jsonify({
            'success': True,
            'reconhecimentos': reconhecimentos
        })
    except Exception:
        return jsonify({'success': False, 'message': 'Falha ao reconhecer lancamentos conhecidos'}), 500


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
    Sugestao de categoria por palavras-chave (prioritario) e historico (fallback).
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
            desc = str(descricao)
            desc_norm = CategoriaPalavraChaveService.normalizar_descricao_importacao(desc)

            # 1. Palavras-chave
            resultado_pk = CategoriaPalavraChaveService.classificar_por_palavras_chave(desc_norm)
            if resultado_pk.get('categoria_id') and not resultado_pk.get('ambigua'):
                sugestoes[desc] = {
                    'categoria_id': resultado_pk['categoria_id'],
                    'origem': 'palavra_chave',
                    'confianca': resultado_pk.get('confianca', 'alta'),
                    'palavras_chave_encontradas': resultado_pk.get('palavras_encontradas', []),
                    'ambigua': False,
                    'categorias_candidatas': resultado_pk.get('categorias_candidatas', []),
                }
            elif resultado_pk.get('ambigua'):
                sugestoes[desc] = {
                    'categoria_id': None,
                    'origem': 'ambigua',
                    'confianca': 'baixa',
                    'palavras_chave_encontradas': resultado_pk.get('palavras_encontradas', []),
                    'ambigua': True,
                    'categorias_candidatas': resultado_pk.get('categorias_candidatas', []),
                }
            else:
                # 2. Histórico
                categoria_id, origem = ImportacaoCartaoService.sugerir_categoria_por_descricao(
                    descricao_bruta=desc,
                    categoria_fallback_id=categoria_fallback_id
                )
                sugestoes[desc] = {
                    'categoria_id': categoria_id,
                    'origem': origem or 'sem_sugestao',
                    'confianca': 'alta' if origem == 'historico' else ('media' if categoria_id else 'baixa'),
                    'palavras_chave_encontradas': [],
                    'ambigua': False,
                    'categorias_candidatas': [],
                }

        return jsonify({
            'success': True,
            'sugestoes': sugestoes
        })
    except Exception:
        return jsonify({'success': False, 'message': 'Falha ao sugerir categorias'}), 500
