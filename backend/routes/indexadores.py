"""
Rotas para gerenciamento de Indexadores Mensais (TR, IPCA, etc.)
"""

from flask import Blueprint, request, jsonify, render_template
from backend.models import db, IndexadorMensal
from datetime import datetime, date
from decimal import Decimal

indexadores_bp = Blueprint('indexadores', __name__)


@indexadores_bp.route('/indexadores')
def pagina_indexadores():
    """Página de gerenciamento de indexadores"""
    return render_template('indexadores.html')


@indexadores_bp.route('/api/indexadores', methods=['GET'])
def listar_indexadores():
    """
    Lista todos os indexadores cadastrados

    Query params:
    - nome: Filtro por nome do indexador (TR, IPCA, etc.)
    - ano: Filtro por ano
    - mes: Filtro por mês
    """
    try:
        # Filtros
        nome = request.args.get('nome')
        ano = request.args.get('ano', type=int)
        mes = request.args.get('mes', type=int)

        # Query base
        query = IndexadorMensal.query

        # Aplicar filtros
        if nome:
            query = query.filter_by(nome=nome)

        if ano and mes:
            data_ref = date(ano, mes, 1)
            query = query.filter_by(data_referencia=data_ref)
        elif ano:
            query = query.filter(
                db.extract('year', IndexadorMensal.data_referencia) == ano
            )

        # Ordenar por data (mais recentes primeiro)
        indexadores = query.order_by(IndexadorMensal.data_referencia.desc()).all()

        # Formatar resposta
        resultado = []
        for idx in indexadores:
            resultado.append({
                'id': idx.id,
                'nome': idx.nome,
                'data_referencia': idx.data_referencia.strftime('%Y-%m-%d'),
                'mes': idx.data_referencia.month,
                'ano': idx.data_referencia.year,
                'mes_ano': idx.data_referencia.strftime('%m/%Y'),
                'valor': float(idx.valor),
                'criado_em': idx.criado_em.strftime('%Y-%m-%d %H:%M:%S')
            })

        return jsonify(resultado), 200

    except Exception as e:
        return jsonify({'erro': str(e)}), 500


@indexadores_bp.route('/api/indexadores', methods=['POST'])
def criar_indexador():
    """
    Cria ou atualiza um indexador mensal

    Body:
    {
        "nome": "TR",
        "ano": 2026,
        "mes": 1,
        "valor": 0.15
    }
    """
    try:
        dados = request.get_json()

        # Validações
        if not dados.get('nome'):
            return jsonify({'erro': 'Campo "nome" é obrigatório'}), 400

        if not dados.get('ano') or not dados.get('mes'):
            return jsonify({'erro': 'Campos "ano" e "mes" são obrigatórios'}), 400

        if dados.get('valor') is None:
            return jsonify({'erro': 'Campo "valor" é obrigatório'}), 400

        # Criar data de referência
        ano = int(dados['ano'])
        mes = int(dados['mes'])

        if mes < 1 or mes > 12:
            return jsonify({'erro': 'Mês deve estar entre 1 e 12'}), 400

        data_ref = date(ano, mes, 1)

        # Verificar se já existe
        indexador_existente = IndexadorMensal.query.filter_by(
            nome=dados['nome'],
            data_referencia=data_ref
        ).first()

        if indexador_existente:
            # Atualizar
            indexador_existente.valor = Decimal(str(dados['valor']))
            mensagem = f'Indexador {dados["nome"]} de {mes:02d}/{ano} atualizado'
        else:
            # Criar novo
            indexador = IndexadorMensal(
                nome=dados['nome'],
                data_referencia=data_ref,
                valor=Decimal(str(dados['valor']))
            )
            db.session.add(indexador)
            mensagem = f'Indexador {dados["nome"]} de {mes:02d}/{ano} criado'

        db.session.commit()

        return jsonify({
            'mensagem': mensagem,
            'indexador': {
                'nome': dados['nome'],
                'data_referencia': data_ref.strftime('%Y-%m-%d'),
                'valor': float(dados['valor'])
            }
        }), 201

    except ValueError as e:
        return jsonify({'erro': f'Valor inválido: {str(e)}'}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'erro': str(e)}), 500


@indexadores_bp.route('/api/indexadores/<int:indexador_id>', methods=['PUT'])
def atualizar_indexador(indexador_id):
    """
    Atualiza um indexador existente

    Body:
    {
        "valor": 0.20
    }
    """
    try:
        dados = request.get_json()

        # Buscar indexador
        indexador = IndexadorMensal.query.get(indexador_id)

        if not indexador:
            return jsonify({'erro': 'Indexador não encontrado'}), 404

        # Atualizar valor
        if dados.get('valor') is not None:
            indexador.valor = Decimal(str(dados['valor']))

        db.session.commit()

        return jsonify({
            'mensagem': 'Indexador atualizado com sucesso',
            'indexador': {
                'id': indexador.id,
                'nome': indexador.nome,
                'data_referencia': indexador.data_referencia.strftime('%Y-%m-%d'),
                'valor': float(indexador.valor)
            }
        }), 200

    except ValueError as e:
        return jsonify({'erro': f'Valor inválido: {str(e)}'}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'erro': str(e)}), 500


@indexadores_bp.route('/api/indexadores/<int:indexador_id>', methods=['DELETE'])
def deletar_indexador(indexador_id):
    """Deleta um indexador"""
    try:
        indexador = IndexadorMensal.query.get(indexador_id)

        if not indexador:
            return jsonify({'erro': 'Indexador não encontrado'}), 404

        db.session.delete(indexador)
        db.session.commit()

        return jsonify({'mensagem': 'Indexador deletado com sucesso'}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'erro': str(e)}), 500


@indexadores_bp.route('/api/indexadores/tipos', methods=['GET'])
def listar_tipos_indexadores():
    """Lista os tipos de indexadores disponíveis"""
    return jsonify([
        {'nome': 'TR', 'descricao': 'Taxa Referencial'},
        {'nome': 'IPCA', 'descricao': 'Índice de Preços ao Consumidor Amplo'},
        {'nome': 'IPCA-E', 'descricao': 'IPCA Especial'},
        {'nome': 'IGP-M', 'descricao': 'Índice Geral de Preços do Mercado'},
        {'nome': 'CDI', 'descricao': 'Certificado de Depósito Interbancário'},
        {'nome': 'SELIC', 'descricao': 'Sistema Especial de Liquidação e Custódia'}
    ]), 200
