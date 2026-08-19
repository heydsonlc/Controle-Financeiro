"""
Rotas da API para gerenciamento de Financiamentos

Endpoints organizados em 4 grupos:
1. CRUD de Financiamentos
2. Gerenciamento de Parcelas
3. Amortizações Extraordinárias
4. Relatórios e Demonstrativos
5. Indexadores (TR, IPCA)
"""
from flask import Blueprint, request, jsonify, send_file
from datetime import datetime
import logging

try:
    from backend.models import db, Financiamento, FinanciamentoParcela, IndexadorMensal, FinanciamentoSeguroVigencia, FinanciamentoAmortizacaoExtra
    from backend.services.financiamento_service import FinanciamentoService
    from backend.services.financiamento_conferencia_service import FinanciamentoConferenciaService
    from backend.services.financiamento_documento_service import FinanciamentoDocumentoService
except ImportError:
    from models import db, Financiamento, FinanciamentoParcela, IndexadorMensal, FinanciamentoSeguroVigencia, FinanciamentoAmortizacaoExtra
    from services.financiamento_service import FinanciamentoService
    from services.financiamento_conferencia_service import FinanciamentoConferenciaService
    from services.financiamento_documento_service import FinanciamentoDocumentoService

# Criar blueprint
financiamentos_bp = Blueprint('financiamentos', __name__)
logger = logging.getLogger(__name__)


# ============================================================================
# FUNÇÕES AUXILIARES
# ============================================================================

def _obter_info_vigencia_para_edicao(financiamento):
    """
    Obtém informações sobre vigências de seguro para pré-preencher tela de edição

    Regras (conforme manifesto):
    - Nunca editar vigência existente
    - Histórico imutável
    - Sem inferência de valores

    Caso 1: SEM amortização após última vigência
        → Retorna dados da última vigência (referência visual)

    Caso 2: COM amortização após última vigência
        → Retorna data sugerida (mês após amortização)
        → Valor vazio
        → Mensagem orientativa

    Returns:
        dict com: data_sugerida, valor_sugerido, observacoes_sugeridas, mensagem_orientativa
    """
    from datetime import date
    from dateutil.relativedelta import relativedelta

    # Buscar última vigência ativa
    ultima_vigencia = FinanciamentoSeguroVigencia.query.filter_by(
        financiamento_id=financiamento.id,
        vigencia_ativa=True
    ).order_by(FinanciamentoSeguroVigencia.competencia_inicio.desc()).first()

    # Buscar última amortização extraordinária
    ultima_amortizacao = FinanciamentoAmortizacaoExtra.query.filter_by(
        financiamento_id=financiamento.id
    ).order_by(FinanciamentoAmortizacaoExtra.data.desc()).first()

    # Caso: nenhuma vigência cadastrada (não deveria acontecer, mas tratamos)
    if not ultima_vigencia:
        return {
            'data_sugerida': None,
            'valor_sugerido': None,
            'observacoes_sugeridas': None,
            'mensagem_orientativa': 'Nenhuma vigência de seguro cadastrada. Cadastre a primeira vigência.'
        }

    # Caso 1: SEM amortização OU amortização ANTES da última vigência
    if not ultima_amortizacao or ultima_amortizacao.data < ultima_vigencia.competencia_inicio:
        return {
            'data_sugerida': ultima_vigencia.competencia_inicio.strftime('%Y-%m-%d'),
            'valor_sugerido': float(ultima_vigencia.valor_mensal),
            'observacoes_sugeridas': ultima_vigencia.observacoes,
            'mensagem_orientativa': None
        }

    # Caso 2: Amortização APÓS a última vigência
    # Data sugerida: primeiro dia do mês seguinte à amortização
    data_amortizacao = ultima_amortizacao.data
    primeiro_dia_mes_amortizacao = date(data_amortizacao.year, data_amortizacao.month, 1)
    data_sugerida = primeiro_dia_mes_amortizacao + relativedelta(months=1)

    mes_ano_sugerido = data_sugerida.strftime('%m/%Y')

    return {
        'data_sugerida': data_sugerida.strftime('%Y-%m-%d'),
        'valor_sugerido': None,  # NÃO inferir valor
        'observacoes_sugeridas': None,
        'mensagem_orientativa': f'Após amortização extraordinária, informe o novo valor do seguro a partir de {mes_ano_sugerido}.'
    }


# ============================================================================
# 1. CRUD DE FINANCIAMENTOS
# ============================================================================

@financiamentos_bp.route('', methods=['GET'])
def listar_financiamentos():
    """
    Lista todos os financiamentos

    Query params:
        ativo: true/false - Filtrar por status ativo

    Returns:
        JSON com lista de financiamentos (com estatísticas calculadas)
    """
    try:
        ativo = request.args.get('ativo')
        if ativo is not None:
            ativo = ativo.lower() == 'true'

        financiamentos = FinanciamentoService.listar_financiamentos(ativo=ativo)

        # Enriquecer dados com estatísticas calculadas
        dados_enriquecidos = []
        for f in financiamentos:
            dados = f.to_dict()

            # Calcular parcelas pagas
            parcelas_pagas = FinanciamentoParcela.query.filter_by(
                financiamento_id=f.id,
                status='pago'
            ).count()

            # Calcular total de parcelas
            total_parcelas = FinanciamentoParcela.query.filter_by(
                financiamento_id=f.id
            ).count()

            # Adicionar campos calculados
            # NOTA: saldo_devedor_atual já vem correto do to_dict() (estado soberano)
            dados['parcelas_pagas'] = parcelas_pagas
            dados['total_parcelas'] = total_parcelas

            dados_enriquecidos.append(dados)

        return jsonify({
            'success': True,
            'data': dados_enriquecidos,
            'total': len(dados_enriquecidos)
        }), 200

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 404

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@financiamentos_bp.route('/<int:id>', methods=['GET'])
def buscar_financiamento(id):
    """
    Busca um financiamento específico por ID

    Args:
        id: ID do financiamento

    Returns:
        JSON com dados do financiamento e suas parcelas
    """
    try:
        financiamento = FinanciamentoService.obter_financiamento_no_perfil(id)

        if not financiamento:
            return jsonify({
                'success': False,
                'error': 'Financiamento não encontrado'
            }), 404

        # Buscar parcelas
        parcelas = FinanciamentoParcela.query.filter_by(
            financiamento_id=id
        ).order_by(FinanciamentoParcela.numero_parcela).all()

        # Contar parcelas pagas
        parcelas_pagas = FinanciamentoParcela.query.filter_by(
            financiamento_id=id,
            status='pago'
        ).count()

        # Buscar informações de vigência de seguro (para edição)
        vigencia_info = _obter_info_vigencia_para_edicao(financiamento)

        return jsonify({
            'success': True,
            'data': {
                **financiamento.to_dict(),
                'parcelas_pagas': parcelas_pagas,
                'parcelas': [p.to_dict() for p in parcelas],
                'total_parcelas': len(parcelas),
                'vigencia_seguro_info': vigencia_info
            }
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@financiamentos_bp.route('', methods=['POST'])
def criar_financiamento():
    """
    Cria um novo financiamento e gera automaticamente as parcelas

    Body (JSON):
        {
            "nome": "string" (obrigatório),
            "produto": "string" (opcional),
            "sistema_amortizacao": "SAC|PRICE|SIMPLES" (obrigatório),
            "valor_financiado": float (obrigatório),
            "prazo_total_meses": int (obrigatório),
            "taxa_juros_nominal_anual": float (obrigatório),
            "indexador_saldo": "TR|IPCA|..." (opcional),
            "data_contrato": "YYYY-MM-DD" (obrigatório),
            "data_primeira_parcela": "YYYY-MM-DD" (obrigatório),
            "seguro_modo": "fixo|estimado_dfi_mip" (opcional, padrão: fixo),
            "valor_seguro_mensal": float (usado no modo fixo/manual),
            "seguro_tipo": campo legado opcional, mantido por compatibilidade,
            "taxa_administracao_fixa": float (opcional, padrão: 0),
            "item_despesa_id": int (opcional)
        }

    Returns:
        JSON com o financiamento criado
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': 'Dados não fornecidos'
            }), 400

        logger.debug('Payload recebido em criar_financiamento. Chaves: %s', list(data.keys()))

        seguro_modo = data.get('seguro_modo') or 'fixo'
        if seguro_modo not in ['fixo', 'estimado_dfi_mip']:
            return jsonify({
                'success': False,
                'error': 'seguro_modo deve ser "fixo" ou "estimado_dfi_mip"'
            }), 400

        if seguro_modo == 'estimado_dfi_mip' and not data.get('seguro_data_nascimento_titular'):
            return jsonify({
                'success': False,
                'error': 'seguro_data_nascimento_titular é obrigatória no modo estimado DFI + MIP'
            }), 400

        # Validar vigências de seguro no modo fixo/manual (obrigatório pelo menos 1)
        vigencias_seguro = data.get('vigencias_seguro', [])

        if seguro_modo == 'fixo' and (not vigencias_seguro or len(vigencias_seguro) == 0):
            return jsonify({
                'success': False,
                'error': 'É obrigatório informar pelo menos uma vigência de seguro'
            }), 400

        # Validar cada vigência
        for i, vigencia in enumerate(vigencias_seguro, 1):
            if 'competencia_inicio' not in vigencia:
                return jsonify({
                    'success': False,
                    'error': f'Vigência {i}: competencia_inicio é obrigatório'
                }), 400

            if 'valor_mensal' not in vigencia or vigencia['valor_mensal'] <= 0:
                return jsonify({
                    'success': False,
                    'error': f'Vigência {i}: valor_mensal deve ser maior que zero'
                }), 400

            # Validação OPCIONAL de saldo_devedor_vigencia (backward compatibility)
            # - Se fornecido: valida se > 0 (mas será IGNORADO pelo service - usa saldo soberano)
            # - Se não fornecido: OK (backend usa financiamento.saldo_devedor_atual)
            if 'saldo_devedor_vigencia' in vigencia:
                if vigencia['saldo_devedor_vigencia'] <= 0:
                    return jsonify({
                        'success': False,
                        'error': f'Vigência {i}: saldo_devedor_vigencia, se fornecido, deve ser maior que zero'
                    }), 400

        financiamento = FinanciamentoService.criar_financiamento(data)

        return jsonify({
            'success': True,
            'message': 'Financiamento criado e parcelas geradas com sucesso',
            'data': financiamento.to_dict()
        }), 201

    except ValueError as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@financiamentos_bp.route('/<int:id>', methods=['PUT'])
def atualizar_financiamento(id):
    """
    Atualiza dados gerais do financiamento

    Args:
        id: ID do financiamento

    Body (JSON): Campos que deseja atualizar
        Campos aceitos:
        - nome, produto, ativo
        - sistema_amortizacao, valor_financiado, prazo_total_meses
        - taxa_juros_nominal_anual, indexador_saldo
        - data_contrato, data_primeira_parcela
        - seguro_modo: "fixo|estimado_dfi_mip" (campo oficial)
        - valor_seguro_mensal: float (modo fixo/manual)
        - seguro_tipo, seguro_percentual: campos legados aceitos por compatibilidade
        - taxa_administracao_fixa: float
        - item_despesa_id: int

    Nota: Alterações estruturais só são permitidas quando não há parcelas
          pagas ou vinculadas a pagamentos. Nesse caso, o cronograma é
          regenerado com base nos novos dados.

    Returns:
        JSON com o financiamento atualizado
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': 'Dados não fornecidos'
            }), 400

        if 'seguro_modo' in data:
            seguro_modo = data.get('seguro_modo') or 'fixo'
            if seguro_modo not in ['fixo', 'estimado_dfi_mip']:
                return jsonify({
                    'success': False,
                    'error': 'seguro_modo deve ser "fixo" ou "estimado_dfi_mip"'
                }), 400
            if seguro_modo == 'estimado_dfi_mip' and not data.get('seguro_data_nascimento_titular'):
                return jsonify({
                    'success': False,
                    'error': 'seguro_data_nascimento_titular é obrigatória no modo estimado DFI + MIP'
                }), 400

        # Campo legado: aceito por compatibilidade, mas seguro_modo e a regra oficial.
        if 'seguro_tipo' in data:
            seguro_tipo = data['seguro_tipo']

            if seguro_tipo not in ['fixo', 'percentual_saldo']:
                return jsonify({
                    'success': False,
                    'error': 'seguro_tipo deve ser "fixo" ou "percentual_saldo"'
                }), 400

        financiamento = FinanciamentoService.atualizar_financiamento(id, data)

        return jsonify({
            'success': True,
            'message': 'Financiamento atualizado com sucesso',
            'data': financiamento.to_dict()
        }), 200

    except ValueError as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

    except Exception as e:
        db.session.rollback()
        logger.exception('Erro interno ao atualizar financiamento %s', id)
        return jsonify({
            'success': False,
            'error': 'Erro interno ao atualizar financiamento. Verifique os logs do servidor.'
        }), 500


@financiamentos_bp.route('/<int:id>', methods=['DELETE'])
def deletar_financiamento(id):
    """
    Exclui definitivamente um financiamento (hard delete)

    Regras de negócio:
    - Só pode excluir se nenhuma parcela estiver paga
    - Só pode excluir se não houver amortizações extraordinárias
    - Se não puder excluir, retorna erro orientando para inativação

    Args:
        id: ID do financiamento

    Returns:
        JSON com confirmação ou erro com orientação
    """
    try:
        FinanciamentoService.excluir_financiamento(id)

        return jsonify({
            'success': True,
            'message': 'Financiamento excluido com sucesso.'
        }), 200

    except ValueError as e:
        return jsonify({
            'success': False,
            'message': str(e),
            'error': str(e)
        }), 400

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': 'Erro interno ao excluir financiamento'
        }), 500


def _status_erro_documento(erro):
    texto = str(erro).lower()
    if 'nao encontrado' in texto or 'não encontrado' in texto:
        return 404
    return 400


@financiamentos_bp.route('/<int:id>/documentos', methods=['GET'])
def listar_documentos_financiamento(id):
    try:
        documentos = FinanciamentoDocumentoService.listar_documentos(id)
        return jsonify({
            'success': True,
            'documentos': [documento.to_dict() for documento in documentos],
            'total': len(documentos),
        }), 200
    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e),
        }), _status_erro_documento(e)
    except Exception as e:
        logger.exception('Erro ao listar documentos do financiamento %s', id)
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@financiamentos_bp.route('/<int:id>/documentos', methods=['POST'])
def enviar_documento_financiamento(id):
    try:
        documento = FinanciamentoDocumentoService.salvar_documento(
            id,
            request.files.get('arquivo'),
            request.form,
        )
        return jsonify({
            'success': True,
            'message': 'Documento enviado com sucesso.',
            'documento': documento.to_dict(),
        }), 201
    except ValueError as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e),
        }), _status_erro_documento(e)
    except Exception as e:
        db.session.rollback()
        logger.exception('Erro ao salvar documento do financiamento %s', id)
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@financiamentos_bp.route('/<int:id>/documentos/<int:doc_id>/download', methods=['GET'])
def baixar_documento_financiamento(id, doc_id):
    try:
        documento, caminho = FinanciamentoDocumentoService.obter_documento_para_download(id, doc_id)
        return send_file(
            caminho,
            mimetype=documento.mime_type,
            as_attachment=True,
            download_name=documento.nome_original,
        )
    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e),
        }), _status_erro_documento(e)
    except Exception as e:
        logger.exception('Erro ao baixar documento %s do financiamento %s', doc_id, id)
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@financiamentos_bp.route('/<int:id>/documentos/<int:doc_id>', methods=['DELETE'])
def excluir_documento_financiamento(id, doc_id):
    try:
        resultado = FinanciamentoDocumentoService.excluir_documento(id, doc_id)
        return jsonify({
            'success': True,
            'message': 'Documento excluido com sucesso.',
            **resultado,
        }), 200
    except ValueError as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e),
        }), _status_erro_documento(e)
    except Exception as e:
        db.session.rollback()
        logger.exception('Erro ao excluir documento %s do financiamento %s', doc_id, id)
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@financiamentos_bp.route('/<int:id>/conferencias-caixa', methods=['GET'])
def listar_conferencias_caixa_financiamento(id):
    try:
        conferencias = FinanciamentoConferenciaService.listar_conferencias(id)
        return jsonify({
            'success': True,
            'conferencias': [conferencia.to_dict() for conferencia in conferencias],
            'total': len(conferencias),
        }), 200
    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e),
        }), _status_erro_documento(e)
    except Exception as e:
        logger.exception('Erro ao listar conferencias CAIXA do financiamento %s', id)
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@financiamentos_bp.route('/<int:id>/conferencias-caixa', methods=['POST'])
def registrar_conferencia_caixa_financiamento(id):
    try:
        conferencia = FinanciamentoConferenciaService.registrar_conferencia(
            id,
            request.get_json(silent=True) or {},
        )
        return jsonify({
            'success': True,
            'message': 'Conferencia CAIXA registrada com sucesso.',
            'conferencia': conferencia.to_dict(),
        }), 201
    except ValueError as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e),
        }), _status_erro_documento(e)
    except Exception as e:
        db.session.rollback()
        logger.exception('Erro ao registrar conferencia CAIXA do financiamento %s', id)
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@financiamentos_bp.route('/<int:id>/documentos/<int:doc_id>/conferencias', methods=['GET'])
def listar_conferencias_caixa_documento(id, doc_id):
    try:
        conferencias = FinanciamentoConferenciaService.listar_conferencias_documento(id, doc_id)
        return jsonify({
            'success': True,
            'conferencias': [conferencia.to_dict() for conferencia in conferencias],
            'total': len(conferencias),
        }), 200
    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e),
        }), _status_erro_documento(e)
    except Exception as e:
        logger.exception('Erro ao listar conferencias do documento %s/%s', id, doc_id)
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@financiamentos_bp.route('/<int:id>/conferencias-caixa/<int:conferencia_id>', methods=['DELETE'])
def excluir_conferencia_caixa_financiamento(id, conferencia_id):
    try:
        FinanciamentoConferenciaService.excluir_conferencia(id, conferencia_id)
        return jsonify({
            'success': True,
            'message': 'Conferencia CAIXA excluida com sucesso.',
        }), 200
    except ValueError as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e),
        }), _status_erro_documento(e)
    except Exception as e:
        db.session.rollback()
        logger.exception('Erro ao excluir conferencia CAIXA %s do financiamento %s', conferencia_id, id)
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@financiamentos_bp.route('/<int:id>/valores-simulados', methods=['GET'])
def obter_valores_simulados_financiamento(id):
    try:
        dados = FinanciamentoConferenciaService.obter_valores_simulados(
            id,
            competencia=request.args.get('competencia'),
            parcela_id=request.args.get('parcela_id'),
            data_referencia=request.args.get('data_referencia'),
        )
        return jsonify({
            'success': True,
            'data': dados,
        }), 200
    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e),
        }), _status_erro_documento(e)
    except Exception as e:
        logger.exception('Erro ao obter valores simulados do financiamento %s', id)
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@financiamentos_bp.route('/<int:id>/regenerar-parcelas', methods=['POST'])
def regenerar_parcelas(id):
    """
    Regenera todas as parcelas do financiamento

    Args:
        id: ID do financiamento

    Body (JSON):
        {
            "valor_seguro_mensal": float (opcional),
            "valor_taxa_adm_mensal": float (opcional)
        }

    Returns:
        JSON com confirmação
    """
    try:
        financiamento = FinanciamentoService.obter_financiamento_no_perfil(id)

        if not financiamento:
            return jsonify({
                'success': False,
                'error': 'Financiamento não encontrado'
            }), 404

        # Regenerar parcelas usando as configurações do financiamento
        FinanciamentoService.gerar_parcelas(financiamento)

        return jsonify({
            'success': True,
            'message': 'Parcelas regeneradas com sucesso'
        }), 200

    except ValueError as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

    except Exception as e:
        db.session.rollback()
        logger.exception('Erro interno ao regenerar parcelas do financiamento %s', id)
        return jsonify({
            'success': False,
            'error': 'Erro interno ao regenerar parcelas do financiamento. Verifique os logs do servidor.'
        }), 500


# ============================================================================
# 2. GERENCIAMENTO DE PARCELAS
# ============================================================================

@financiamentos_bp.route('/parcelas/<int:parcela_id>/pagar', methods=['POST'])
def pagar_parcela(parcela_id):
    """
    Registra pagamento de parcela de financiamento com MovimentoFinanceiro bancario.

    Body (JSON):
        {
            "conta_bancaria_id": int (obrigatorio),
            "data_pagamento": "YYYY-MM-DD" (obrigatorio)
        }
    """
    try:
        from backend.models import Conta, ContaBancaria, FinanciamentoParcela
        from backend.services.conta_bancaria_service import ContaBancariaService
        from backend.services.perfil_financeiro_service import PerfilFinanceiroService
    except ImportError:
        from models import Conta, ContaBancaria, FinanciamentoParcela
        from services.conta_bancaria_service import ContaBancariaService
        from services.perfil_financeiro_service import PerfilFinanceiroService

    try:
        data = request.get_json() or {}

        conta_bancaria_id = data.get('conta_bancaria_id')
        if not conta_bancaria_id:
            return jsonify({
                'success': False,
                'error': 'Informe a conta bancaria para registrar o pagamento da parcela.',
            }), 400
        try:
            conta_bancaria_id = int(conta_bancaria_id)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'conta_bancaria_id invalido'}), 400

        data_pagamento_str = data.get('data_pagamento')
        if not data_pagamento_str:
            return jsonify({'success': False, 'error': 'data_pagamento e obrigatorio'}), 400
        try:
            from datetime import datetime as _dt
            data_pagamento = _dt.strptime(data_pagamento_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'success': False, 'error': 'Formato de data_pagamento invalido. Use YYYY-MM-DD'}), 400

        # Buscar e validar parcela
        parcela = PerfilFinanceiroService.aplicar_perfil_query(
            FinanciamentoParcela.query, FinanciamentoParcela
        ).filter(FinanciamentoParcela.id == parcela_id).first()
        if not parcela:
            return jsonify({'success': False, 'error': 'Parcela nao encontrada'}), 404
        if parcela.status == 'pago':
            return jsonify({'success': False, 'error': 'Esta parcela ja foi paga.'}), 409

        # Se ha despesa vinculada pendente, orientar pelo fluxo de despesas (CORE-SALDO-1C)
        conta_vinculada = Conta.query.filter_by(financiamento_parcela_id=parcela.id).first()
        if conta_vinculada and conta_vinculada.status_pagamento != 'Pago':
            return jsonify({
                'success': False,
                'error': 'Esta parcela possui despesa vinculada pendente. Use o fluxo de Despesas para registrar o pagamento.',
            }), 409

        # Validar conta bancaria
        conta_bancaria = ContaBancaria.query.filter(
            ContaBancaria.id == conta_bancaria_id,
            PerfilFinanceiroService.condicao_perfil(ContaBancaria),
        ).first()
        if not conta_bancaria:
            return jsonify({'success': False, 'error': 'Conta bancaria nao encontrada'}), 404
        if conta_bancaria.status != 'ATIVO':
            return jsonify({'success': False, 'error': 'Conta bancaria esta inativa'}), 400

        # Registrar parcela (commit=False - transacao controlada aqui)
        FinanciamentoService.registrar_pagamento_parcela(
            parcela_id,
            parcela.valor_previsto_total,
            data_pagamento,
            commit=False,
        )

        # Criar movimento bancario de debito (CORE-SALDO-1C)
        financiamento = FinanciamentoService.obter_financiamento_no_perfil(parcela.financiamento_id)
        nome_fin = getattr(financiamento, 'descricao', None) or f'Financiamento #{parcela.financiamento_id}'
        ContaBancariaService.criar_movimento(
            conta_bancaria_id,
            tipo='DEBITO',
            valor=parcela.valor_previsto_total,
            descricao=f'Pagamento parcela {parcela.numero_parcela} - {nome_fin}',
            data_movimento=data_pagamento,
            origem='FINANCIAMENTO',
            financiamento_parcela_id=parcela.id,
        )

        db.session.commit()

        try:
            if financiamento and financiamento.item_despesa_id:
                FinanciamentoService.sincronizar_contas(parcela.financiamento_id)
        except Exception:
            pass

        return jsonify({
            'success': True,
            'message': 'Pagamento registrado com sucesso',
            'data': parcela.to_dict()
        }), 200

    except ValueError as e:
        db.session.rollback()
        msg = str(e)
        code = 409 if 'ja foi paga' in msg else 400
        return jsonify({'success': False, 'error': msg}), code

    except Exception:
        db.session.rollback()
        return jsonify({'success': False, 'error': 'Erro interno ao registrar pagamento'}), 500


@financiamentos_bp.route('/parcelas/<int:parcela_id>/estornar-pagamento', methods=['POST'])
def estornar_pagamento_parcela(parcela_id):
    """
    CORE-ESTORNO-4: estorno de pagamento direto de parcela de financiamento.

    Nao apaga o movimento original (DEBITO, origem=FINANCIAMENTO). Cria movimento
    compensatorio de CREDITO (origem=ESTORNO_FINANCIAMENTO), reabre a parcela como
    pendente e recompoe financiamento.saldo_devedor_atual.

    Bloqueado se:
    - parcela nao esta paga;
    - pagamento foi feito via despesa vinculada (Conta.financiamento_parcela_id),
      nao via fluxo direto de financiamento — nesse caso o estorno deve ser feito
      pelo fluxo de despesas para preservar rastreabilidade;
    - existe parcela com numero_parcela maior, tambem paga diretamente, no mesmo
      financiamento — so a parcela paga mais recente (maior numero) pode ser
      estornada, para nao corromper a cadeia de saldo_devedor_apos_pagamento;
    - ja existe estorno para esta parcela.

    Body (JSON):
        {
            "data_estorno": "YYYY-MM-DD" (obrigatorio),
            "motivo": "string" (obrigatorio)
        }
    """
    try:
        from decimal import Decimal
        from backend.models import Conta, MovimentoFinanceiro
        from backend.services.conta_bancaria_service import ContaBancariaService
        from backend.services.perfil_financeiro_service import PerfilFinanceiroService
    except ImportError:
        from decimal import Decimal
        from models import Conta, MovimentoFinanceiro
        from services.conta_bancaria_service import ContaBancariaService
        from services.perfil_financeiro_service import PerfilFinanceiroService

    try:
        parcela = PerfilFinanceiroService.aplicar_perfil_query(
            FinanciamentoParcela.query, FinanciamentoParcela
        ).filter(FinanciamentoParcela.id == parcela_id).first()
        if not parcela:
            return jsonify({'success': False, 'error': 'Parcela nao encontrada'}), 404

        if parcela.status != 'pago':
            return jsonify({'success': False, 'error': 'Apenas parcelas pagas podem ser estornadas.'}), 409

        # Regra especial: parcela paga via despesa vinculada nao pode ser estornada aqui
        conta_vinculada = Conta.query.filter_by(financiamento_parcela_id=parcela.id).first()
        if conta_vinculada and conta_vinculada.status_pagamento == 'Pago':
            return jsonify({
                'success': False,
                'error': 'Esta parcela possui despesa vinculada. Estorne pelo fluxo de despesas para preservar a rastreabilidade.',
            }), 409

        # So a parcela paga mais recente (maior numero_parcela) pode ser estornada,
        # para nao corromper a cadeia de saldo_devedor_apos_pagamento
        parcela_paga_mais_recente = PerfilFinanceiroService.aplicar_perfil_query(
            FinanciamentoParcela.query, FinanciamentoParcela
        ).filter(
            FinanciamentoParcela.financiamento_id == parcela.financiamento_id,
            FinanciamentoParcela.status == 'pago',
        ).order_by(FinanciamentoParcela.numero_parcela.desc()).first()
        if parcela_paga_mais_recente and parcela_paga_mais_recente.numero_parcela > parcela.numero_parcela:
            return jsonify({
                'success': False,
                'error': f'Existe uma parcela paga mais recente (numero {parcela_paga_mais_recente.numero_parcela}). '
                         f'Estorne a partir da parcela mais recente para preservar a cadeia de saldo devedor.',
            }), 409

        # Localizar movimento original de debito vinculado a esta parcela
        movimento_original = MovimentoFinanceiro.query.filter_by(
            financiamento_parcela_id=parcela.id,
            origem='FINANCIAMENTO',
            tipo='DEBITO',
        ).order_by(MovimentoFinanceiro.id.desc()).first()
        if not movimento_original:
            return jsonify({
                'success': False,
                'error': 'Nao foi possivel estornar porque o movimento financeiro original nao foi encontrado.',
            }), 422

        # MOV-REF-1: bloquear estorno duplicado preferencialmente via movimento_original_id;
        # fallback legado (origem + financiamento_parcela_id) cobre estornos anteriores a esta coluna.
        estorno_existente = MovimentoFinanceiro.query.filter_by(
            movimento_original_id=movimento_original.id,
            origem='ESTORNO_FINANCIAMENTO',
        ).first()
        if not estorno_existente:
            estorno_existente = MovimentoFinanceiro.query.filter_by(
                financiamento_parcela_id=parcela.id,
                origem='ESTORNO_FINANCIAMENTO',
            ).first()
        if estorno_existente:
            return jsonify({
                'success': False,
                'error': 'Este pagamento/recebimento ja foi estornado.',
            }), 409

        if not movimento_original.conta_bancaria_id:
            return jsonify({
                'success': False,
                'error': 'Movimento original nao possui conta bancaria vinculada.',
            }), 422

        valor_original = Decimal(str(movimento_original.valor or 0))
        if valor_original <= 0:
            return jsonify({
                'success': False,
                'error': 'Valor do movimento original invalido para estorno.',
            }), 422

        dados = request.get_json() or {}
        motivo = (dados.get('motivo') or '').strip()
        if not motivo:
            return jsonify({'success': False, 'error': 'Motivo do estorno e obrigatorio.'}), 400

        data_estorno_str = (dados.get('data_estorno') or '').strip()
        if not data_estorno_str:
            return jsonify({'success': False, 'error': 'Data do estorno e obrigatoria.'}), 400
        try:
            data_estorno = datetime.strptime(data_estorno_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'success': False, 'error': 'Formato de data_estorno invalido. Use YYYY-MM-DD.'}), 400

        conta_bancaria_id = movimento_original.conta_bancaria_id
        financiamento = FinanciamentoService.obter_financiamento_no_perfil(parcela.financiamento_id)
        nome_fin = getattr(financiamento, 'descricao', None) or f'Financiamento #{parcela.financiamento_id}'

        descricao_estorno = f'Estorno de pagamento da parcela {parcela.numero_parcela} - {nome_fin}'
        observacao_estorno = f'[ESTORNO] {data_estorno_str} — {motivo}'

        movimento_estorno = ContaBancariaService.criar_movimento(
            conta_bancaria_id,
            tipo='CREDITO',
            valor=valor_original,
            descricao=descricao_estorno,
            data_movimento=data_estorno,
            origem='ESTORNO_FINANCIAMENTO',
            financiamento_parcela_id=parcela.id,
            movimento_original_id=movimento_original.id,
        )

        # Recompor saldo devedor: valor antes deste pagamento e o
        # saldo_devedor_apos_pagamento da parcela anterior, ou valor_financiado se for a 1a.
        if financiamento:
            if parcela.numero_parcela > 1:
                parcela_anterior = FinanciamentoParcela.query.filter_by(
                    financiamento_id=parcela.financiamento_id,
                    numero_parcela=parcela.numero_parcela - 1,
                ).first()
                financiamento.saldo_devedor_atual = (
                    parcela_anterior.saldo_devedor_apos_pagamento
                    if parcela_anterior and parcela_anterior.saldo_devedor_apos_pagamento is not None
                    else financiamento.valor_financiado
                )
            else:
                financiamento.saldo_devedor_atual = financiamento.valor_financiado

        parcela.status = 'pendente'
        parcela.valor_pago = 0
        parcela.dif_apurada = 0

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Pagamento da parcela estornado com sucesso.',
            'data': {
                'parcela_id': parcela.id,
                'movimento_estorno_id': movimento_estorno.id,
                'status': parcela.status,
                'valor_estornado': float(valor_original),
                'saldo_devedor_atual': float(financiamento.saldo_devedor_atual) if financiamento and financiamento.saldo_devedor_atual is not None else None,
            },
        }), 200

    except Exception:
        db.session.rollback()
        return jsonify({'success': False, 'error': 'Erro interno ao estornar pagamento'}), 500


# ============================================================================
# 3. AMORTIZAÇÕES EXTRAORDINÁRIAS
# ============================================================================

@financiamentos_bp.route('/<int:id>/amortizacao-extra', methods=['POST'])
def registrar_amortizacao_extra(id):
    """
    Registra uma amortização extraordinária

    Args:
        id: ID do financiamento

    Body (JSON):
        {
            "data": "YYYY-MM-DD" (obrigatório),
            "valor": float (obrigatório),
            "tipo": "reduzir_parcela|reduzir_prazo" (obrigatório),
            "observacoes": "string" (opcional)
        }

    Returns:
        JSON com o registro da amortização
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': 'Dados não fornecidos'
            }), 400

        campos_obrigatorios = ['data', 'valor', 'tipo']
        for campo in campos_obrigatorios:
            if campo not in data:
                return jsonify({
                    'success': False,
                    'error': f'{campo} é obrigatório'
                }), 400

        if data['tipo'] not in ['reduzir_parcela', 'reduzir_prazo']:
            return jsonify({
                'success': False,
                'error': 'tipo deve ser "reduzir_parcela" ou "reduzir_prazo"'
            }), 400

        amortizacao = FinanciamentoService.registrar_amortizacao_extra(id, data)

        return jsonify({
            'success': True,
            'message': 'Amortização extraordinária registrada com sucesso',
            'data': amortizacao.to_dict()
        }), 201

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@financiamentos_bp.route('/<int:id>/ajustar-saldo', methods=['POST'])
def ajustar_saldo_devedor(id):
    """
    Ajusta saldo devedor real e recalcula parcelas futuras pendentes.
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': 'Dados não fornecidos'
            }), 400

        if not data.get('parcela_referencia_id') and not data.get('numero_parcela'):
            return jsonify({
                'success': False,
                'error': 'Informe parcela_referencia_id ou numero_parcela'
            }), 400

        if data.get('saldo_devedor_real') is None:
            return jsonify({
                'success': False,
                'error': 'saldo_devedor_real é obrigatório'
            }), 400

        ajuste, parcelas_recalculadas = FinanciamentoService.ajustar_saldo_devedor_real(id, data)

        return jsonify({
            'success': True,
            'message': 'Saldo devedor ajustado e parcelas futuras recalculadas.',
            'ajuste_id': ajuste.id,
            'parcelas_recalculadas': parcelas_recalculadas,
            'data': ajuste.to_dict()
        }), 200

    except ValueError as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': str(e),
            'error': str(e)
        }), 400

    except Exception as e:
        db.session.rollback()
        logger.exception('Erro interno ao ajustar saldo do financiamento %s', id)
        return jsonify({
            'success': False,
            'message': 'Erro interno ao ajustar saldo devedor. Verifique os logs do servidor.',
            'error': 'Erro interno ao ajustar saldo devedor. Verifique os logs do servidor.'
        }), 500


@financiamentos_bp.route('/<int:id>/vigencias-seguro', methods=['POST'])
def adicionar_vigencia_seguro(id):
    """
    Adiciona nova vigência de seguro ao financiamento

    IMPORTANTE: Este é o endpoint CORRETO para adicionar vigências.
    NÃO usar PUT /financiamentos/<id> para adicionar vigências.

    Regra de ouro: saldo_devedor_vigencia SEMPRE vem do estado soberano,
    nunca do frontend.

    Args:
        id: ID do financiamento

    Payload JSON:
        {
            "competencia_inicio": "2026-03" ou "01/03/2026" ou "2026-03-01",
            "valor_mensal": 200.00,
            "observacoes": "Reajuste anual" (opcional)
        }

    Returns:
        JSON com vigência criada e status do recálculo
    """
    try:
        from backend.services.seguro_vigencia_service import SeguroVigenciaService
        from datetime import datetime
        from decimal import Decimal

        # Buscar financiamento
        financiamento = FinanciamentoService.obter_financiamento_no_perfil(id)
        if not financiamento:
            return jsonify({
                'success': False,
                'error': 'Financiamento não encontrado'
            }), 404

        data = request.get_json()

        # Validações
        if not data.get('competencia_inicio'):
            return jsonify({
                'success': False,
                'error': 'competencia_inicio é obrigatório'
            }), 400

        if not data.get('valor_mensal'):
            return jsonify({
                'success': False,
                'error': 'valor_mensal é obrigatório'
            }), 400

        # Normalizar data (aceitar múltiplos formatos)
        competencia_str = data['competencia_inicio']

        # Remover sufixos indesejados
        if '-' in competencia_str and len(competencia_str) > 7:
            competencia_str = competencia_str.split('-')[0] + '-' + competencia_str.split('-')[1]

        competencia_inicio = None

        # Tentar formato YYYY-MM (input type="month")
        if len(competencia_str) == 7 and competencia_str[4] == '-':
            try:
                competencia_inicio = datetime.strptime(competencia_str + '-01', '%Y-%m-%d').date()
            except ValueError:
                pass

        # Tentar formato MM/YYYY
        if not competencia_inicio and '/' in competencia_str:
            partes = competencia_str.split('/')
            if len(partes) == 2:
                try:
                    mes, ano = partes
                    competencia_inicio = datetime(int(ano), int(mes), 1).date()
                except (ValueError, IndexError):
                    pass

        # Tentar formato DD/MM/YYYY
        if not competencia_inicio and '/' in competencia_str:
            try:
                competencia_inicio = datetime.strptime(competencia_str, '%d/%m/%Y').date()
                competencia_inicio = competencia_inicio.replace(day=1)
            except ValueError:
                pass

        # Tentar formato YYYY-MM-DD (ISO)
        if not competencia_inicio:
            try:
                competencia_inicio = datetime.strptime(competencia_str, '%Y-%m-%d').date()
                competencia_inicio = competencia_inicio.replace(day=1)
            except ValueError:
                pass

        if not competencia_inicio:
            return jsonify({
                'success': False,
                'error': f'Formato de data inválido: {data["competencia_inicio"]}. Use YYYY-MM, MM/YYYY ou DD/MM/YYYY'
            }), 400

        # ====================================================================
        # REGRA DE OURO: Saldo soberano NÃO vem do frontend
        # ====================================================================
        # SEMPRE usar financiamento.saldo_devedor_atual
        saldo_devedor_vigencia = financiamento.saldo_devedor_atual

        # Criar vigência
        vigencia = SeguroVigenciaService.criar_vigencia(
            financiamento_id=financiamento.id,
            competencia_inicio=competencia_inicio,
            valor_mensal=Decimal(str(data['valor_mensal'])),
            saldo_devedor_vigencia=saldo_devedor_vigencia,
            observacoes=data.get('observacoes', '')
        )

        # ====================================================================
        # RECÁLCULO SEGURO-ONLY (não toca em saldo/amortização/juros)
        # ====================================================================
        parcelas_atualizadas = FinanciamentoService.recalcular_seguro_parcelas_futuras(
            financiamento_id=financiamento.id,
            a_partir_de=competencia_inicio
        )

        return jsonify({
            'success': True,
            'message': f'Vigência criada com sucesso. {parcelas_atualizadas} parcelas atualizadas.',
            'data': {
                'vigencia': vigencia.to_dict(),
                'parcelas_atualizadas': parcelas_atualizadas,
                'saldo_devedor_atual': float(financiamento.saldo_devedor_atual)
            }
        }), 201

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================================================
# 4. RELATÓRIOS E DEMONSTRATIVOS
# ============================================================================

@financiamentos_bp.route('/<int:id>/demonstrativo-anual', methods=['GET'])
def demonstrativo_anual(id):
    """
    Gera demonstrativo anual do financiamento (similar ao da CAIXA)

    Args:
        id: ID do financiamento

    Query params:
        ano: Ano (obrigatório)

    Returns:
        JSON com demonstrativo consolidado por mês
    """
    try:
        ano = request.args.get('ano', type=int)

        if not ano:
            return jsonify({
                'success': False,
                'error': 'Parâmetro ano é obrigatório'
            }), 400

        demonstrativo = FinanciamentoService.get_demonstrativo_anual(id, ano)

        return jsonify({
            'success': True,
            'data': demonstrativo
        }), 200

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 404

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@financiamentos_bp.route('/<int:id>/evolucao-saldo', methods=['GET'])
def evolucao_saldo(id):
    """
    Retorna evolução do saldo devedor ao longo das parcelas

    Args:
        id: ID do financiamento

    Returns:
        JSON com evolução mês a mês
    """
    try:
        evolucao = FinanciamentoService.get_evolucao_saldo(id)

        return jsonify({
            'success': True,
            'data': evolucao
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================================================
# 5. INDEXADORES (TR, IPCA, etc)
# ============================================================================

@financiamentos_bp.route('/<int:id>/simular-quitacao', methods=['POST'])
def simular_quitacao(id):
    """
    Simula a quitação antecipada de um financiamento.

    Somente simulação: não altera banco, não baixa parcelas, não gera boleto.

    Body (JSON):
        {
            "data_quitacao": "YYYY-MM-DD" (obrigatório),
            "desconto_banco_percentual": float (opcional, 0-100, padrão 0)
        }

    Returns:
        JSON com saldo estimado, componentes e avisos
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': 'Dados não fornecidos'
            }), 400

        data_quitacao = data.get('data_quitacao')
        if not data_quitacao:
            return jsonify({
                'success': False,
                'error': 'data_quitacao é obrigatória'
            }), 400

        desconto = data.get('desconto_banco_percentual', 0)
        try:
            desconto = float(desconto)
        except (TypeError, ValueError):
            return jsonify({
                'success': False,
                'error': 'desconto_banco_percentual deve ser um número'
            }), 400

        resultado = FinanciamentoService.simular_quitacao(
            financiamento_id=id,
            data_quitacao=data_quitacao,
            desconto_banco_percentual=desconto,
        )

        return jsonify({
            'success': True,
            'data': resultado
        }), 200

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

    except Exception as e:
        logger.exception('Erro ao simular quitacao do financiamento %s', id)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@financiamentos_bp.route('/indexadores', methods=['GET'])
def listar_indexadores():
    """
    Lista valores de indexadores cadastrados

    Query params:
        nome: Filtrar por nome (TR, IPCA, etc)
        ano: Filtrar por ano

    Returns:
        JSON com lista de indexadores
    """
    try:
        nome = request.args.get('nome')
        ano = request.args.get('ano', type=int)

        query = IndexadorMensal.query

        if nome:
            query = query.filter_by(nome=nome)

        if ano:
            data_inicio = datetime(ano, 1, 1).date()
            data_fim = datetime(ano, 12, 31).date()
            query = query.filter(
                IndexadorMensal.data_referencia >= data_inicio,
                IndexadorMensal.data_referencia <= data_fim
            )

        indexadores = query.order_by(IndexadorMensal.data_referencia.desc()).all()

        return jsonify({
            'success': True,
            'data': [i.to_dict() for i in indexadores],
            'total': len(indexadores)
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@financiamentos_bp.route('/indexadores', methods=['POST'])
def criar_indexador():
    """
    Cadastra valor de indexador para um mês

    Body (JSON):
        {
            "nome": "TR|IPCA|..." (obrigatório),
            "data_referencia": "YYYY-MM-01" (obrigatório),
            "valor": float (obrigatório) - percentual (ex: 0.0015 = 0,15%)
        }

    Returns:
        JSON com o indexador criado
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': 'Dados não fornecidos'
            }), 400

        campos_obrigatorios = ['nome', 'data_referencia', 'valor']
        for campo in campos_obrigatorios:
            if campo not in data:
                return jsonify({
                    'success': False,
                    'error': f'{campo} é obrigatório'
                }), 400

        # Converter data
        if isinstance(data['data_referencia'], str):
            data_ref = datetime.strptime(data['data_referencia'], '%Y-%m-%d').date()
        else:
            data_ref = data['data_referencia']

        # Garantir primeiro dia do mês
        data_ref = data_ref.replace(day=1)

        # Verificar se já existe
        existe = IndexadorMensal.query.filter_by(
            nome=data['nome'],
            data_referencia=data_ref
        ).first()

        if existe:
            # Atualizar
            existe.valor = data['valor']
            db.session.commit()
            indexador = existe
            mensagem = 'Indexador atualizado com sucesso'
        else:
            # Criar novo
            indexador = IndexadorMensal(
                nome=data['nome'],
                data_referencia=data_ref,
                valor=data['valor']
            )
            db.session.add(indexador)
            db.session.commit()
            mensagem = 'Indexador criado com sucesso'

        return jsonify({
            'success': True,
            'message': mensagem,
            'data': indexador.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
