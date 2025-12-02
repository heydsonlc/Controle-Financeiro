"""
Rotas da API para gerenciamento de Patrimônio (Caixinhas)

Endpoints Contas de Patrimônio:
- GET    /api/patrimonio/contas              - Listar todas as contas
- GET    /api/patrimonio/contas/<id>         - Buscar conta específica
- POST   /api/patrimonio/contas              - Criar nova conta
- PUT    /api/patrimonio/contas/<id>         - Atualizar conta
- DELETE /api/patrimonio/contas/<id>         - Inativar conta

Endpoints Transferências:
- GET    /api/patrimonio/transferencias      - Listar transferências
- GET    /api/patrimonio/transferencias/<id> - Buscar transferência específica
- POST   /api/patrimonio/transferencias      - Criar nova transferência
- DELETE /api/patrimonio/transferencias/<id> - Deletar transferência
"""
from flask import Blueprint, request, jsonify
from datetime import datetime, date
try:
    from backend.models import db, ContaPatrimonio, Transferencia
except ImportError:
    from models import db, ContaPatrimonio, Transferencia

# Criar blueprint
patrimonio_bp = Blueprint('patrimonio', __name__)


# ============================================================================
# ROTAS DE CONTAS DE PATRIMÔNIO
# ============================================================================

@patrimonio_bp.route('/contas', methods=['GET'])
def listar_contas():
    """
    Lista todas as contas de patrimônio

    Query params:
        ativo: true/false - Filtrar por status ativo

    Returns:
        JSON com lista de contas
    """
    try:
        ativo = request.args.get('ativo')

        if ativo is not None:
            ativo_bool = ativo.lower() == 'true'
            contas = ContaPatrimonio.query.filter_by(ativo=ativo_bool).all()
        else:
            contas = ContaPatrimonio.query.filter_by(ativo=True).all()

        # Calcular total do patrimônio
        total_patrimonio = sum(float(c.saldo_atual) for c in contas if c.ativo)

        return jsonify({
            'success': True,
            'data': [conta.to_dict() for conta in contas],
            'total': len(contas),
            'total_patrimonio': total_patrimonio
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@patrimonio_bp.route('/contas/<int:id>', methods=['GET'])
def buscar_conta(id):
    """
    Busca uma conta de patrimônio específica por ID

    Args:
        id: ID da conta

    Returns:
        JSON com dados da conta
    """
    try:
        conta = ContaPatrimonio.query.get(id)

        if not conta:
            return jsonify({
                'success': False,
                'error': 'Conta não encontrada'
            }), 404

        return jsonify({
            'success': True,
            'data': conta.to_dict()
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@patrimonio_bp.route('/contas', methods=['POST'])
def criar_conta():
    """
    Cria uma nova conta de patrimônio

    Body params:
        nome: str (obrigatório, único)
        tipo: str (opcional)
        saldo_inicial: float (opcional, default 0)
        meta: float (opcional)
        cor: str (opcional, default '#28a745')
        observacoes: str (opcional)

    Returns:
        JSON com dados da conta criada
    """
    try:
        data = request.get_json()

        # Validações
        if not data.get('nome'):
            return jsonify({
                'success': False,
                'error': 'Nome é obrigatório'
            }), 400

        # Verificar se já existe conta com mesmo nome
        conta_existente = ContaPatrimonio.query.filter_by(nome=data['nome']).first()
        if conta_existente:
            return jsonify({
                'success': False,
                'error': 'Já existe uma conta com este nome'
            }), 400

        # Criar nova conta
        saldo_inicial = float(data.get('saldo_inicial', 0))

        nova_conta = ContaPatrimonio(
            nome=data['nome'],
            tipo=data.get('tipo'),
            saldo_inicial=saldo_inicial,
            saldo_atual=saldo_inicial,  # Saldo inicial = saldo atual
            meta=data.get('meta'),
            cor=data.get('cor', '#28a745'),
            observacoes=data.get('observacoes'),
            ativo=True
        )

        db.session.add(nova_conta)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Conta criada com sucesso',
            'data': nova_conta.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@patrimonio_bp.route('/contas/<int:id>', methods=['PUT'])
def atualizar_conta(id):
    """
    Atualiza uma conta de patrimônio existente

    Args:
        id: ID da conta

    Body params:
        nome: str
        tipo: str
        meta: float
        cor: str
        observacoes: str
        ativo: bool

    Returns:
        JSON com dados da conta atualizada
    """
    try:
        conta = ContaPatrimonio.query.get(id)

        if not conta:
            return jsonify({
                'success': False,
                'error': 'Conta não encontrada'
            }), 404

        data = request.get_json()

        # Atualizar campos
        if 'nome' in data:
            # Verificar se já existe outra conta com mesmo nome
            outra_conta = ContaPatrimonio.query.filter_by(nome=data['nome']).first()
            if outra_conta and outra_conta.id != id:
                return jsonify({
                    'success': False,
                    'error': 'Já existe uma conta com este nome'
                }), 400
            conta.nome = data['nome']

        if 'tipo' in data:
            conta.tipo = data['tipo']
        if 'meta' in data:
            conta.meta = data['meta']
        if 'cor' in data:
            conta.cor = data['cor']
        if 'observacoes' in data:
            conta.observacoes = data['observacoes']
        if 'ativo' in data:
            conta.ativo = data['ativo']

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Conta atualizada com sucesso',
            'data': conta.to_dict()
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@patrimonio_bp.route('/contas/<int:id>', methods=['DELETE'])
def inativar_conta(id):
    """
    Inativa uma conta de patrimônio

    Args:
        id: ID da conta

    Returns:
        JSON com mensagem de sucesso
    """
    try:
        conta = ContaPatrimonio.query.get(id)

        if not conta:
            return jsonify({
                'success': False,
                'error': 'Conta não encontrada'
            }), 404

        # Inativar ao invés de deletar
        conta.ativo = False
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Conta inativada com sucesso'
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================================================
# ROTAS DE TRANSFERÊNCIAS
# ============================================================================

@patrimonio_bp.route('/transferencias', methods=['GET'])
def listar_transferencias():
    """
    Lista todas as transferências

    Query params:
        data_inicio: YYYY-MM-DD - Filtrar por data início
        data_fim: YYYY-MM-DD - Filtrar por data fim
        conta_id: int - Filtrar por conta (origem ou destino)

    Returns:
        JSON com lista de transferências
    """
    try:
        query = Transferencia.query

        # Filtros opcionais
        data_inicio = request.args.get('data_inicio')
        data_fim = request.args.get('data_fim')
        conta_id = request.args.get('conta_id')

        if data_inicio:
            query = query.filter(Transferencia.data_transferencia >= data_inicio)
        if data_fim:
            query = query.filter(Transferencia.data_transferencia <= data_fim)
        if conta_id:
            query = query.filter(
                (Transferencia.conta_origem_id == conta_id) |
                (Transferencia.conta_destino_id == conta_id)
            )

        transferencias = query.order_by(Transferencia.data_transferencia.desc()).all()

        # Enriquecer dados com nomes das contas
        result = []
        for t in transferencias:
            dados = t.to_dict()
            dados['conta_origem_nome'] = t.conta_origem.nome if t.conta_origem else None
            dados['conta_destino_nome'] = t.conta_destino.nome if t.conta_destino else None
            result.append(dados)

        return jsonify({
            'success': True,
            'data': result,
            'total': len(result)
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@patrimonio_bp.route('/transferencias/<int:id>', methods=['GET'])
def buscar_transferencia(id):
    """
    Busca uma transferência específica por ID

    Args:
        id: ID da transferência

    Returns:
        JSON com dados da transferência
    """
    try:
        transferencia = Transferencia.query.get(id)

        if not transferencia:
            return jsonify({
                'success': False,
                'error': 'Transferência não encontrada'
            }), 404

        dados = transferencia.to_dict()
        dados['conta_origem_nome'] = transferencia.conta_origem.nome
        dados['conta_destino_nome'] = transferencia.conta_destino.nome

        return jsonify({
            'success': True,
            'data': dados
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@patrimonio_bp.route('/transferencias', methods=['POST'])
def criar_transferencia():
    """
    Cria uma nova transferência entre contas de patrimônio

    Body params:
        conta_origem_id: int (obrigatório)
        conta_destino_id: int (obrigatório)
        valor: float (obrigatório)
        data_transferencia: str YYYY-MM-DD (obrigatório)
        descricao: str (opcional)
        observacoes: str (opcional)

    Returns:
        JSON com dados da transferência criada
    """
    try:
        data = request.get_json()

        # Validações
        if not data.get('conta_origem_id'):
            return jsonify({
                'success': False,
                'error': 'Conta de origem é obrigatória'
            }), 400

        if not data.get('conta_destino_id'):
            return jsonify({
                'success': False,
                'error': 'Conta de destino é obrigatória'
            }), 400

        if data.get('conta_origem_id') == data.get('conta_destino_id'):
            return jsonify({
                'success': False,
                'error': 'Conta de origem e destino não podem ser iguais'
            }), 400

        if not data.get('valor') or float(data['valor']) <= 0:
            return jsonify({
                'success': False,
                'error': 'Valor deve ser maior que zero'
            }), 400

        if not data.get('data_transferencia'):
            return jsonify({
                'success': False,
                'error': 'Data da transferência é obrigatória'
            }), 400

        # Verificar se as contas existem e estão ativas
        conta_origem = ContaPatrimonio.query.get(data['conta_origem_id'])
        conta_destino = ContaPatrimonio.query.get(data['conta_destino_id'])

        if not conta_origem or not conta_origem.ativo:
            return jsonify({
                'success': False,
                'error': 'Conta de origem não encontrada ou inativa'
            }), 404

        if not conta_destino or not conta_destino.ativo:
            return jsonify({
                'success': False,
                'error': 'Conta de destino não encontrada ou inativa'
            }), 404

        valor = float(data['valor'])

        # Verificar se conta de origem tem saldo suficiente
        if float(conta_origem.saldo_atual) < valor:
            return jsonify({
                'success': False,
                'error': 'Saldo insuficiente na conta de origem'
            }), 400

        # Criar transferência
        nova_transferencia = Transferencia(
            conta_origem_id=data['conta_origem_id'],
            conta_destino_id=data['conta_destino_id'],
            valor=valor,
            data_transferencia=datetime.strptime(data['data_transferencia'], '%Y-%m-%d').date(),
            descricao=data.get('descricao'),
            observacoes=data.get('observacoes')
        )

        # Atualizar saldos das contas
        conta_origem.saldo_atual = float(conta_origem.saldo_atual) - valor
        conta_destino.saldo_atual = float(conta_destino.saldo_atual) + valor

        db.session.add(nova_transferencia)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Transferência criada com sucesso',
            'data': nova_transferencia.to_dict()
        }), 201

    except ValueError as ve:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Formato de data inválido. Use YYYY-MM-DD'
        }), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@patrimonio_bp.route('/transferencias/<int:id>', methods=['DELETE'])
def deletar_transferencia(id):
    """
    Deleta uma transferência e reverte os saldos

    Args:
        id: ID da transferência

    Returns:
        JSON com mensagem de sucesso
    """
    try:
        transferencia = Transferencia.query.get(id)

        if not transferencia:
            return jsonify({
                'success': False,
                'error': 'Transferência não encontrada'
            }), 404

        # Reverter saldos
        conta_origem = transferencia.conta_origem
        conta_destino = transferencia.conta_destino

        valor = float(transferencia.valor)
        conta_origem.saldo_atual = float(conta_origem.saldo_atual) + valor
        conta_destino.saldo_atual = float(conta_destino.saldo_atual) - valor

        # Deletar transferência
        db.session.delete(transferencia)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Transferência deletada e saldos revertidos'
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
