"""
Rotas da API para gerenciamento de Categorias

Endpoints:
- GET    /api/categorias          - Listar todas as categorias
- GET    /api/categorias/<id>     - Buscar uma categoria específica
- POST   /api/categorias          - Criar nova categoria
- PUT    /api/categorias/<id>     - Atualizar categoria
- DELETE /api/categorias/<id>     - Deletar categoria
"""
from flask import Blueprint, request, jsonify
try:
    from backend.models import db, Categoria
except ImportError:
    from models import db, Categoria

# Criar blueprint
categorias_bp = Blueprint('categorias', __name__)


@categorias_bp.route('', methods=['GET'])
def listar_categorias():
    """
    Lista todas as categorias

    Query params:
        ativo: true/false - Filtrar por status ativo

    Returns:
        JSON com lista de categorias
    """
    try:
        # Filtro opcional por status ativo
        ativo = request.args.get('ativo')

        if ativo is not None:
            ativo_bool = ativo.lower() == 'true'
            categorias = Categoria.query.filter_by(ativo=ativo_bool).all()
        else:
            categorias = Categoria.query.all()

        return jsonify({
            'success': True,
            'data': [cat.to_dict() for cat in categorias],
            'total': len(categorias)
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@categorias_bp.route('/<int:id>', methods=['GET'])
def buscar_categoria(id):
    """
    Busca uma categoria específica por ID

    Args:
        id: ID da categoria

    Returns:
        JSON com dados da categoria
    """
    try:
        categoria = Categoria.query.get(id)

        if not categoria:
            return jsonify({
                'success': False,
                'error': 'Categoria não encontrada'
            }), 404

        return jsonify({
            'success': True,
            'data': categoria.to_dict()
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@categorias_bp.route('', methods=['POST'])
def criar_categoria():
    """
    Cria uma nova categoria

    Body (JSON):
        {
            "nome": "string" (obrigatório),
            "descricao": "string" (opcional),
            "cor": "#RRGGBB" (opcional, padrão: #6c757d),
            "ativo": boolean (opcional, padrão: true)
        }

    Returns:
        JSON com a categoria criada
    """
    try:
        data = request.get_json()

        # Validação
        if not data:
            return jsonify({
                'success': False,
                'error': 'Dados não fornecidos'
            }), 400

        if 'nome' not in data or not data['nome'].strip():
            return jsonify({
                'success': False,
                'error': 'Nome é obrigatório'
            }), 400

        # Verificar se já existe categoria com mesmo nome
        existe = Categoria.query.filter_by(nome=data['nome'].strip()).first()
        if existe:
            return jsonify({
                'success': False,
                'error': 'Já existe uma categoria com este nome'
            }), 400

        # Criar categoria
        categoria = Categoria(
            nome=data['nome'].strip(),
            descricao=data.get('descricao', '').strip(),
            cor=data.get('cor', '#6c757d'),
            ativo=data.get('ativo', True)
        )

        db.session.add(categoria)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Categoria criada com sucesso',
            'data': categoria.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@categorias_bp.route('/<int:id>', methods=['PUT'])
def atualizar_categoria(id):
    """
    Atualiza uma categoria existente

    Args:
        id: ID da categoria

    Body (JSON):
        {
            "nome": "string" (opcional),
            "descricao": "string" (opcional),
            "cor": "#RRGGBB" (opcional),
            "ativo": boolean (opcional)
        }

    Returns:
        JSON com a categoria atualizada
    """
    try:
        categoria = Categoria.query.get(id)

        if not categoria:
            return jsonify({
                'success': False,
                'error': 'Categoria não encontrada'
            }), 404

        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': 'Dados não fornecidos'
            }), 400

        # Atualizar campos fornecidos
        if 'nome' in data:
            nome = data['nome'].strip()
            if not nome:
                return jsonify({
                    'success': False,
                    'error': 'Nome não pode ser vazio'
                }), 400

            # Verificar se já existe outra categoria com mesmo nome
            existe = Categoria.query.filter(
                Categoria.nome == nome,
                Categoria.id != id
            ).first()

            if existe:
                return jsonify({
                    'success': False,
                    'error': 'Já existe outra categoria com este nome'
                }), 400

            categoria.nome = nome

        if 'descricao' in data:
            categoria.descricao = data['descricao'].strip()

        if 'cor' in data:
            categoria.cor = data['cor']

        if 'ativo' in data:
            categoria.ativo = data['ativo']

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Categoria atualizada com sucesso',
            'data': categoria.to_dict()
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@categorias_bp.route('/<int:id>', methods=['DELETE'])
def deletar_categoria(id):
    """
    Deleta uma categoria

    Args:
        id: ID da categoria

    Returns:
        JSON com confirmação
    """
    try:
        categoria = Categoria.query.get(id)

        if not categoria:
            return jsonify({
                'success': False,
                'error': 'Categoria não encontrada'
            }), 404

        # Verificar se há itens de despesa vinculados
        if categoria.itens_despesa.count() > 0:
            return jsonify({
                'success': False,
                'error': 'Não é possível deletar categoria com itens de despesa vinculados'
            }), 400

        db.session.delete(categoria)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Categoria deletada com sucesso'
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
