"""
Rotas da API para gerenciamento de Financiamentos

Endpoints organizados em 4 grupos:
1. CRUD de Financiamentos
2. Gerenciamento de Parcelas
3. Amortizações Extraordinárias
4. Relatórios e Demonstrativos
5. Indexadores (TR, IPCA)
"""
from flask import Blueprint, request, jsonify
from datetime import datetime

try:
    from backend.models import db, Financiamento, FinanciamentoParcela, IndexadorMensal, FinanciamentoSeguroVigencia, FinanciamentoAmortizacaoExtra
    from backend.services.financiamento_service import FinanciamentoService
except ImportError:
    from models import db, Financiamento, FinanciamentoParcela, IndexadorMensal, FinanciamentoSeguroVigencia, FinanciamentoAmortizacaoExtra
    from services.financiamento_service import FinanciamentoService

# Criar blueprint
financiamentos_bp = Blueprint('financiamentos', __name__)


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
        financiamento = Financiamento.query.get(id)

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
            "seguro_tipo": "fixo|percentual_saldo" (opcional, padrão: fixo),
            "seguro_percentual": float (obrigatório se seguro_tipo=percentual_saldo),
            "valor_seguro_mensal": float (obrigatório se seguro_tipo=fixo),
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

        # DEBUG: Log do payload recebido
        import json
        print("DEBUG: Payload recebido no backend:")
        print(json.dumps(data, indent=2, ensure_ascii=False))

        # Validar vigências de seguro (obrigatório pelo menos 1)
        vigencias_seguro = data.get('vigencias_seguro', [])

        if not vigencias_seguro or len(vigencias_seguro) == 0:
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
        - nome, produto
        - seguro_tipo: "fixo|percentual_saldo"
        - seguro_percentual: float (se seguro_tipo=percentual_saldo)
        - valor_seguro_mensal: float (se seguro_tipo=fixo)
        - taxa_administracao_fixa: float
        - item_despesa_id: int

    Nota: Ao alterar seguro_tipo, seguro_percentual, valor_seguro_mensal ou
          taxa_administracao_fixa, as parcelas futuras (status PENDENTE) serão
          automaticamente recalculadas

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

        # Validar tipo de seguro se fornecido
        if 'seguro_tipo' in data:
            seguro_tipo = data['seguro_tipo']

            if seguro_tipo not in ['fixo', 'percentual_saldo']:
                return jsonify({
                    'success': False,
                    'error': 'seguro_tipo deve ser "fixo" ou "percentual_saldo"'
                }), 400

            # Validar campos de seguro baseado no tipo
            if seguro_tipo == 'percentual_saldo':
                if 'seguro_percentual' not in data or data['seguro_percentual'] is None:
                    return jsonify({
                        'success': False,
                        'error': 'seguro_percentual é obrigatório quando seguro_tipo é "percentual_saldo"'
                    }), 400

                # Validar range do percentual (0.01% a 1%)
                percentual = float(data['seguro_percentual'])
                if percentual < 0.0001 or percentual > 0.01:
                    return jsonify({
                        'success': False,
                        'error': 'seguro_percentual deve estar entre 0.0001 (0.01%) e 0.01 (1%)'
                    }), 400

            elif seguro_tipo == 'fixo':
                if 'valor_seguro_mensal' not in data or data['valor_seguro_mensal'] is None:
                    return jsonify({
                        'success': False,
                        'error': 'valor_seguro_mensal é obrigatório quando seguro_tipo é "fixo"'
                    }), 400

        financiamento = FinanciamentoService.atualizar_financiamento(id, data)

        return jsonify({
            'success': True,
            'message': 'Financiamento atualizado com sucesso',
            'data': financiamento.to_dict()
        }), 200

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
            'message': 'Financiamento excluído com sucesso'
        }), 200

    except ValueError as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 400

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': 'Erro interno ao excluir financiamento'
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
        financiamento = Financiamento.query.get(id)

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

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================================================
# 2. GERENCIAMENTO DE PARCELAS
# ============================================================================

@financiamentos_bp.route('/parcelas/<int:parcela_id>/pagar', methods=['POST'])
def pagar_parcela(parcela_id):
    """
    Registra o pagamento de uma parcela específica

    Args:
        parcela_id: ID da parcela

    Body (JSON):
        {
            "valor_pago": float (obrigatório),
            "data_pagamento": "YYYY-MM-DD" (obrigatório)
        }

    Returns:
        JSON com a parcela atualizada
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': 'Dados não fornecidos'
            }), 400

        if 'valor_pago' not in data:
            return jsonify({
                'success': False,
                'error': 'valor_pago é obrigatório'
            }), 400

        if 'data_pagamento' not in data:
            return jsonify({
                'success': False,
                'error': 'data_pagamento é obrigatório'
            }), 400

        parcela = FinanciamentoService.registrar_pagamento_parcela(
            parcela_id,
            data['valor_pago'],
            data['data_pagamento']
        )

        return jsonify({
            'success': True,
            'message': 'Pagamento registrado com sucesso',
            'data': parcela.to_dict()
        }), 200

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
        financiamento = Financiamento.query.get(id)
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
