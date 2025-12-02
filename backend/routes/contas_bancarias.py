"""
Rotas da API para gerenciamento de Contas Bancárias

Endpoints:
- GET    /api/contas              - Listar todas as contas
- GET    /api/contas/<id>         - Buscar uma conta específica
- POST   /api/contas              - Criar nova conta
- PUT    /api/contas/<id>         - Atualizar conta
- DELETE /api/contas/<id>         - Inativar conta (não remove do BD)
"""
from flask import Blueprint, request, jsonify
from datetime import datetime
try:
    from backend.models import db, ContaBancaria
except ImportError:
    from models import db, ContaBancaria

# Criar blueprint
contas_bancarias_bp = Blueprint('contas_bancarias', __name__)


@contas_bancarias_bp.route('', methods=['GET'])
def listar_contas():
    """
    Lista todas as contas bancárias

    Query params:
        status: ATIVO/INATIVO - Filtrar por status

    Returns:
        JSON com lista de contas
    """
    try:
        status = request.args.get('status')

        if status:
            contas = ContaBancaria.query.filter_by(status=status.upper()).all()
        else:
            contas = ContaBancaria.query.filter_by(status='ATIVO').all()

        return jsonify({
            'success': True,
            'data': [conta.to_dict() for conta in contas],
            'total': len(contas)
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@contas_bancarias_bp.route('/<int:id>', methods=['GET'])
def buscar_conta(id):
    """
    Busca uma conta bancária específica por ID

    Args:
        id: ID da conta

    Returns:
        JSON com dados da conta
    """
    try:
        conta = ContaBancaria.query.get(id)

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


@contas_bancarias_bp.route('', methods=['POST'])
def criar_conta():
    """
    Cria uma nova conta bancária

    Body params:
        nome: str (obrigatório)
        instituicao: str (obrigatório)
        tipo: str (obrigatório)
        agencia: str (opcional)
        numero_conta: str (opcional)
        digito_conta: str (opcional)
        saldo_inicial: float (opcional, default 0)
        cor_display: str (opcional, default '#3b82f6')
        icone: str (opcional)

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

        if not data.get('instituicao'):
            return jsonify({
                'success': False,
                'error': 'Instituição é obrigatória'
            }), 400

        if not data.get('tipo'):
            return jsonify({
                'success': False,
                'error': 'Tipo é obrigatório'
            }), 400

        # Criar nova conta
        saldo_inicial = float(data.get('saldo_inicial', 0))

        nova_conta = ContaBancaria(
            nome=data['nome'],
            instituicao=data['instituicao'],
            tipo=data['tipo'],
            agencia=data.get('agencia'),
            numero_conta=data.get('numero_conta'),
            digito_conta=data.get('digito_conta'),
            saldo_inicial=saldo_inicial,
            saldo_atual=saldo_inicial,  # Saldo inicial = saldo atual na criação
            cor_display=data.get('cor_display', '#3b82f6'),
            icone=data.get('icone'),
            status='ATIVO'
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


@contas_bancarias_bp.route('/<int:id>', methods=['PUT'])
def atualizar_conta(id):
    """
    Atualiza uma conta bancária existente

    Args:
        id: ID da conta

    Body params:
        nome: str
        instituicao: str
        tipo: str
        agencia: str
        numero_conta: str
        digito_conta: str
        saldo_inicial: float
        cor_display: str
        icone: str
        status: str

    Returns:
        JSON com dados da conta atualizada
    """
    try:
        conta = ContaBancaria.query.get(id)

        if not conta:
            return jsonify({
                'success': False,
                'error': 'Conta não encontrada'
            }), 404

        data = request.get_json()

        # Atualizar campos
        if 'nome' in data:
            conta.nome = data['nome']
        if 'instituicao' in data:
            conta.instituicao = data['instituicao']
        if 'tipo' in data:
            conta.tipo = data['tipo']
        if 'agencia' in data:
            conta.agencia = data['agencia']
        if 'numero_conta' in data:
            conta.numero_conta = data['numero_conta']
        if 'digito_conta' in data:
            conta.digito_conta = data['digito_conta']
        if 'cor_display' in data:
            conta.cor_display = data['cor_display']
        if 'icone' in data:
            conta.icone = data['icone']
        if 'status' in data:
            conta.status = data['status']

        # Se o saldo inicial for alterado e não existirem lançamentos
        # associados, atualizar também o saldo atual
        if 'saldo_inicial' in data:
            novo_saldo_inicial = float(data['saldo_inicial'])
            diferenca = novo_saldo_inicial - float(conta.saldo_inicial)
            conta.saldo_inicial = novo_saldo_inicial
            # Atualizar saldo atual somando a diferença
            conta.saldo_atual = float(conta.saldo_atual) + diferenca

        conta.data_atualizacao = datetime.utcnow()

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


@contas_bancarias_bp.route('/<int:id>', methods=['DELETE'])
def inativar_conta(id):
    """
    Inativa uma conta bancária (não remove do banco)

    Args:
        id: ID da conta

    Returns:
        JSON com mensagem de sucesso
    """
    try:
        conta = ContaBancaria.query.get(id)

        if not conta:
            return jsonify({
                'success': False,
                'error': 'Conta não encontrada'
            }), 404

        # Inativar ao invés de deletar
        conta.status = 'INATIVO'
        conta.data_atualizacao = datetime.utcnow()

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


@contas_bancarias_bp.route('/<int:id>/ativar', methods=['PUT'])
def ativar_conta(id):
    """
    Reativa uma conta bancária inativa

    Args:
        id: ID da conta

    Returns:
        JSON com mensagem de sucesso
    """
    try:
        conta = ContaBancaria.query.get(id)

        if not conta:
            return jsonify({
                'success': False,
                'error': 'Conta não encontrada'
            }), 404

        conta.status = 'ATIVO'
        conta.data_atualizacao = datetime.utcnow()

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Conta reativada com sucesso',
            'data': conta.to_dict()
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
