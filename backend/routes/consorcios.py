"""
Rotas para gerenciamento de Consórcios
"""
from flask import Blueprint, request, jsonify
from datetime import datetime
from dateutil.relativedelta import relativedelta

try:
    from backend.models import db, ContratoConsorcio, ItemDespesa, ItemReceita, Categoria
except ImportError:
    from models import db, ContratoConsorcio, ItemDespesa, ItemReceita, Categoria

consorcios_bp = Blueprint('consorcios', __name__, url_prefix='/api/consorcios')


def gerar_parcelas_consorcio(consorcio):
    """
    Gera automaticamente as parcelas do consórcio como ItemDespesa

    Args:
        consorcio: Objeto ContratoConsorcio
    """
    if not consorcio.item_despesa_id:
        raise ValueError("Consórcio deve ter uma categoria/item de despesa associado")

    # Buscar o item de despesa template
    item_template = ItemDespesa.query.get(consorcio.item_despesa_id)
    if not item_template:
        raise ValueError("Item de despesa não encontrado")

    mes_atual = consorcio.mes_inicio
    # O valor_inicial já é o valor da parcela, não dividir pelo número de parcelas
    valor_parcela_base = consorcio.valor_inicial

    parcelas_criadas = []

    for i in range(consorcio.numero_parcelas):
        # Calcular o valor com reajuste
        valor_ajustado = valor_parcela_base

        if consorcio.tipo_reajuste == 'percentual' and consorcio.valor_reajuste > 0:
            # Reajuste percentual progressivo: valor_base × (1 + taxa%)^mês
            fator_reajuste = (1 + (consorcio.valor_reajuste / 100)) ** i
            valor_ajustado = valor_parcela_base * fator_reajuste
        elif consorcio.tipo_reajuste == 'fixo' and consorcio.valor_reajuste > 0:
            # Reajuste fixo: valor_base + (reajuste × mês)
            valor_ajustado = valor_parcela_base + (consorcio.valor_reajuste * i)

        # Criar a despesa para o mês
        despesa = ItemDespesa(
            nome=f"{consorcio.nome} - Parcela {i+1}/{consorcio.numero_parcelas}",
            descricao=f"Parcela {i+1} do consórcio {consorcio.nome}",
            valor=valor_ajustado,
            data_vencimento=mes_atual.replace(day=5),  # Vencimento no dia 5 do mês
            categoria_id=item_template.categoria_id,
            pago=False,
            recorrente=False,
            tipo='Consorcio',
            mes_competencia=mes_atual.strftime('%Y-%m')
        )

        db.session.add(despesa)
        parcelas_criadas.append(despesa)

        # Próximo mês
        mes_atual = mes_atual + relativedelta(months=1)

    return parcelas_criadas


def gerar_receita_contemplacao(consorcio):
    """
    Gera automaticamente a receita da contemplação

    Args:
        consorcio: Objeto ContratoConsorcio
    """
    if not consorcio.mes_contemplacao or not consorcio.valor_premio:
        return None

    if not consorcio.item_receita_id:
        raise ValueError("Consórcio deve ter uma categoria de receita associada")

    # Buscar o item de receita template
    item_template = ItemReceita.query.get(consorcio.item_receita_id)
    if not item_template:
        raise ValueError("Item de receita não encontrado")

    # Criar a receita na contemplação
    from backend.models import ReceitaRealizada

    receita = ReceitaRealizada(
        nome=f"Contemplação {consorcio.nome}",
        valor=consorcio.valor_premio,
        data_recebimento=consorcio.mes_contemplacao,
        categoria_id=item_template.categoria_id if hasattr(item_template, 'categoria_id') else None,
        tipo='Eventual',
        observacoes=f"Prêmio de contemplação do consórcio {consorcio.nome}"
    )

    db.session.add(receita)
    return receita


@consorcios_bp.route('/', methods=['GET'])
def listar_consorcios():
    """Lista todos os consórcios"""
    try:
        consorcios = ContratoConsorcio.query.filter_by(ativo=True).all()
        return jsonify({
            'success': True,
            'data': [c.to_dict() for c in consorcios]
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@consorcios_bp.route('/<int:id>', methods=['GET'])
def obter_consorcio(id):
    """Obtém um consórcio específico"""
    try:
        consorcio = ContratoConsorcio.query.get(id)
        if not consorcio:
            return jsonify({
                'success': False,
                'error': 'Consórcio não encontrado'
            }), 404

        return jsonify({
            'success': True,
            'data': consorcio.to_dict()
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@consorcios_bp.route('/', methods=['POST'])
def criar_consorcio():
    """Cria um novo consórcio e gera as parcelas automaticamente"""
    try:
        dados = request.get_json()

        # Validações
        campos_obrigatorios = ['nome', 'valor_inicial', 'numero_parcelas', 'mes_inicio', 'item_despesa_id']
        for campo in campos_obrigatorios:
            if not dados.get(campo):
                return jsonify({
                    'success': False,
                    'error': f'Campo {campo} é obrigatório'
                }), 400

        # Converter datas
        mes_inicio = datetime.strptime(dados['mes_inicio'], '%Y-%m-%d').date()
        mes_contemplacao = None
        if dados.get('mes_contemplacao'):
            mes_contemplacao = datetime.strptime(dados['mes_contemplacao'], '%Y-%m-%d').date()

        # Criar consórcio
        consorcio = ContratoConsorcio(
            nome=dados['nome'],
            valor_inicial=float(dados['valor_inicial']),
            tipo_reajuste=dados.get('tipo_reajuste', 'nenhum'),
            valor_reajuste=float(dados.get('valor_reajuste', 0)),
            numero_parcelas=int(dados['numero_parcelas']),
            mes_inicio=mes_inicio,
            mes_contemplacao=mes_contemplacao,
            valor_premio=float(dados['valor_premio']) if dados.get('valor_premio') else None,
            item_despesa_id=dados['item_despesa_id'],
            item_receita_id=dados.get('item_receita_id'),
            observacoes=dados.get('observacoes')
        )

        db.session.add(consorcio)
        db.session.flush()  # Para obter o ID

        # Gerar parcelas automaticamente
        parcelas = gerar_parcelas_consorcio(consorcio)

        # Gerar receita se houver contemplação
        receita = None
        if mes_contemplacao and dados.get('valor_premio') and dados.get('item_receita_id'):
            receita = gerar_receita_contemplacao(consorcio)

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Consórcio criado com sucesso',
            'data': consorcio.to_dict(),
            'parcelas_geradas': len(parcelas),
            'receita_gerada': receita is not None
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@consorcios_bp.route('/<int:id>', methods=['PUT'])
def atualizar_consorcio(id):
    """Atualiza um consórcio existente"""
    try:
        consorcio = ContratoConsorcio.query.get(id)
        if not consorcio:
            return jsonify({
                'success': False,
                'error': 'Consórcio não encontrado'
            }), 404

        dados = request.get_json()

        # Atualizar campos
        if 'nome' in dados:
            consorcio.nome = dados['nome']
        if 'observacoes' in dados:
            consorcio.observacoes = dados['observacoes']
        if 'ativo' in dados:
            consorcio.ativo = dados['ativo']

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Consórcio atualizado com sucesso',
            'data': consorcio.to_dict()
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@consorcios_bp.route('/<int:id>', methods=['DELETE'])
def deletar_consorcio(id):
    """Deleta um consórcio (marca como inativo)"""
    try:
        consorcio = ContratoConsorcio.query.get(id)
        if not consorcio:
            return jsonify({
                'success': False,
                'error': 'Consórcio não encontrado'
            }), 404

        # Marcar como inativo ao invés de deletar
        consorcio.ativo = False
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Consórcio desativado com sucesso'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@consorcios_bp.route('/<int:id>/regenerar-parcelas', methods=['POST'])
def regenerar_parcelas(id):
    """Regenera as parcelas de um consórcio"""
    try:
        consorcio = ContratoConsorcio.query.get(id)
        if not consorcio:
            return jsonify({
                'success': False,
                'error': 'Consórcio não encontrado'
            }), 404

        # Deletar parcelas antigas do consórcio
        ItemDespesa.query.filter_by(tipo='Consorcio').filter(
            ItemDespesa.nome.like(f"{consorcio.nome} - Parcela%")
        ).delete()

        # Gerar novas parcelas
        parcelas = gerar_parcelas_consorcio(consorcio)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Parcelas regeneradas com sucesso',
            'parcelas_geradas': len(parcelas)
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
