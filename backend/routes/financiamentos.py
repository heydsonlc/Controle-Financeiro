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
    from backend.models import db, Financiamento, FinanciamentoParcela, IndexadorMensal
    from backend.services.financiamento_service import FinanciamentoService
except ImportError:
    from models import db, Financiamento, FinanciamentoParcela, IndexadorMensal
    from services.financiamento_service import FinanciamentoService

# Criar blueprint
financiamentos_bp = Blueprint('financiamentos', __name__)


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
        JSON com lista de financiamentos
    """
    try:
        ativo = request.args.get('ativo')
        if ativo is not None:
            ativo = ativo.lower() == 'true'

        financiamentos = FinanciamentoService.listar_financiamentos(ativo=ativo)

        return jsonify({
            'success': True,
            'data': [f.to_dict() for f in financiamentos],
            'total': len(financiamentos)
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

        # Calcular saldo devedor atual (última parcela pendente)
        ultima_parcela_paga = FinanciamentoParcela.query.filter_by(
            financiamento_id=id,
            status='pago'
        ).order_by(FinanciamentoParcela.numero_parcela.desc()).first()

        saldo_devedor_atual = 0
        if ultima_parcela_paga:
            saldo_devedor_atual = float(ultima_parcela_paga.saldo_devedor_apos_pagamento or 0)
        else:
            saldo_devedor_atual = float(financiamento.valor_financiado)

        return jsonify({
            'success': True,
            'data': {
                **financiamento.to_dict(),
                'saldo_devedor_atual': saldo_devedor_atual,
                'parcelas': [p.to_dict() for p in parcelas],
                'total_parcelas': len(parcelas)
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

        # Validar tipo de seguro
        seguro_tipo = data.get('seguro_tipo', 'fixo')

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
    Inativa (soft delete) um financiamento

    Args:
        id: ID do financiamento

    Returns:
        JSON com confirmação
    """
    try:
        financiamento = FinanciamentoService.inativar_financiamento(id)

        return jsonify({
            'success': True,
            'message': 'Financiamento inativado com sucesso',
            'data': financiamento.to_dict()
        }), 200

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 404

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
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
