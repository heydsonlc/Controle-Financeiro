"""
Rotas da API para gerenciamento de Categorias

Endpoints:
- GET    /api/categorias          - Listar todas as categorias
- GET    /api/categorias/<id>     - Buscar uma categoria específica
- POST   /api/categorias          - Criar nova categoria
- PUT    /api/categorias/<id>     - Atualizar categoria
- DELETE /api/categorias/<id>     - Deletar categoria
"""
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, current_app, jsonify, request, send_from_directory
from werkzeug.utils import secure_filename
try:
    from backend.models import db, Categoria
except ImportError:
    from models import db, Categoria

# Criar blueprint
categorias_bp = Blueprint('categorias', __name__)

ALLOWED_LOGO_EXTENSIONS = {'png', 'webp', 'jpg', 'jpeg'}
ALLOWED_LOGO_MIME_TYPES = {
    'png': 'image/png',
    'webp': 'image/webp',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
}


def _logos_dir():
    return Path(current_app.config['UPLOAD_LOGOS_DIR']).resolve()


def _max_logo_size():
    return int(current_app.config.get('MAX_LOGO_SIZE', 1024 * 1024))


def _path_dentro_diretorio(base_dir, path):
    try:
        path.resolve().relative_to(base_dir.resolve())
        return True
    except ValueError:
        return False


def _extensao_logo(filename):
    nome = filename or ''
    if '.' not in nome:
        return ''
    return nome.rsplit('.', 1)[1].lower()


def _assinatura_logo_valida(conteudo, extensao):
    if extensao == 'png':
        return conteudo.startswith(b'\x89PNG\r\n\x1a\n')
    if extensao in {'jpg', 'jpeg'}:
        return conteudo.startswith(b'\xff\xd8\xff')
    if extensao == 'webp':
        return len(conteudo) >= 12 and conteudo[:4] == b'RIFF' and conteudo[8:12] == b'WEBP'
    return False


def _validar_logo_upload(arquivo):
    if not arquivo:
        raise ValueError('Arquivo de logo nao fornecido')

    if not arquivo.filename:
        raise ValueError('Nome de arquivo vazio')

    extensao = _extensao_logo(arquivo.filename)
    if extensao not in ALLOWED_LOGO_EXTENSIONS:
        raise ValueError('Formato invalido. Use PNG, JPG ou WebP')

    mimetype = (arquivo.mimetype or '').lower()
    if mimetype != ALLOWED_LOGO_MIME_TYPES[extensao]:
        raise ValueError('Tipo MIME invalido para o arquivo enviado')

    limite = _max_logo_size()
    conteudo = arquivo.stream.read(limite + 1)
    arquivo.stream.seek(0)

    if not conteudo:
        raise ValueError('Arquivo vazio')

    if len(conteudo) > limite:
        raise ValueError('Arquivo acima do limite de tamanho')

    if not _assinatura_logo_valida(conteudo, extensao):
        raise ValueError('Assinatura do arquivo invalida')

    nome_original = secure_filename(Path(arquivo.filename).name)[:255] or None
    return conteudo, extensao, mimetype, nome_original


def _remover_arquivo_logo(nome_arquivo):
    if not nome_arquivo:
        return

    base_dir = _logos_dir()
    caminho = (base_dir / Path(nome_arquivo).name).resolve()
    if not _path_dentro_diretorio(base_dir, caminho):
        return

    try:
        if caminho.is_file():
            caminho.unlink()
    except OSError:
        current_app.logger.warning('Nao foi possivel remover logo antigo: %s', caminho)


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
        icone_raw = data.get('icone', '') or ''
        categoria = Categoria(
            nome=data['nome'].strip(),
            descricao=data.get('descricao', '').strip(),
            cor=data.get('cor', '#6c757d'),
            icone=icone_raw.strip()[:50] or None,
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

        if 'icone' in data:
            icone_raw = data['icone'] or ''
            categoria.icone = icone_raw.strip()[:50] or None

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


@categorias_bp.route('/<int:id>/logo', methods=['POST'])
def enviar_logo_categoria(id):
    """
    Envia ou substitui o logo personalizado de uma categoria.
    """
    categoria = Categoria.query.get(id)

    if not categoria:
        return jsonify({
            'success': False,
            'error': 'Categoria nao encontrada'
        }), 404

    try:
        arquivo = request.files.get('file')
        conteudo, extensao, mimetype, nome_original = _validar_logo_upload(arquivo)
    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

    upload_dir = _logos_dir()
    upload_dir.mkdir(parents=True, exist_ok=True)

    nome_arquivo = f'{uuid4().hex}.{extensao}'
    caminho = (upload_dir / nome_arquivo).resolve()

    if not _path_dentro_diretorio(upload_dir, caminho):
        return jsonify({
            'success': False,
            'error': 'Caminho de upload invalido'
        }), 400

    logo_antigo = categoria.logo_arquivo

    try:
        caminho.write_bytes(conteudo)

        categoria.logo_arquivo = nome_arquivo
        categoria.logo_mime = mimetype
        categoria.logo_tamanho = len(conteudo)
        categoria.logo_original_nome = nome_original
        categoria.logo_criado_em = datetime.utcnow()

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        _remover_arquivo_logo(nome_arquivo)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

    _remover_arquivo_logo(logo_antigo)

    return jsonify({
        'success': True,
        'message': 'Logo atualizado com sucesso',
        'data': categoria.to_dict()
    }), 200


@categorias_bp.route('/<int:id>/logo', methods=['DELETE'])
def remover_logo_categoria(id):
    """
    Remove o logo personalizado de uma categoria.
    """
    try:
        categoria = Categoria.query.get(id)

        if not categoria:
            return jsonify({
                'success': False,
                'error': 'Categoria nao encontrada'
            }), 404

        logo_antigo = categoria.logo_arquivo
        categoria.logo_arquivo = None
        categoria.logo_mime = None
        categoria.logo_tamanho = None
        categoria.logo_original_nome = None
        categoria.logo_criado_em = None

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

    _remover_arquivo_logo(logo_antigo)

    return jsonify({
        'success': True,
        'message': 'Logo removido com sucesso',
        'data': categoria.to_dict()
    }), 200


@categorias_bp.route('/<int:id>/logo', methods=['GET'])
def servir_logo_categoria(id):
    """
    Serve o logo personalizado de uma categoria.
    """
    categoria = Categoria.query.get(id)

    if not categoria or not categoria.logo_arquivo:
        return jsonify({
            'success': False,
            'error': 'Logo nao encontrado'
        }), 404

    upload_dir = _logos_dir()
    nome_arquivo = Path(categoria.logo_arquivo).name
    caminho = (upload_dir / nome_arquivo).resolve()

    if nome_arquivo != categoria.logo_arquivo or not _path_dentro_diretorio(upload_dir, caminho):
        return jsonify({
            'success': False,
            'error': 'Logo invalido'
        }), 404

    if not caminho.is_file():
        return jsonify({
            'success': False,
            'error': 'Arquivo de logo nao encontrado'
        }), 404

    response = send_from_directory(
        str(upload_dir),
        nome_arquivo,
        mimetype=categoria.logo_mime,
        conditional=True,
        max_age=3600
    )
    response.headers['Cache-Control'] = 'private, max-age=3600'
    return response


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

        logo_antigo = categoria.logo_arquivo
        db.session.delete(categoria)
        db.session.commit()
        _remover_arquivo_logo(logo_antigo)

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
