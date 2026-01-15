"""
Rotas para gerenciamento de Consórcios
"""
from flask import Blueprint, request, jsonify
from datetime import datetime
from dateutil.relativedelta import relativedelta

try:
    from backend.models import db, ContratoConsorcio, ItemDespesa, ItemReceita, Categoria, Conta, ReceitaRealizada
except ImportError:
    from models import db, ContratoConsorcio, ItemDespesa, ItemReceita, Categoria, Conta, ReceitaRealizada

consorcios_bp = Blueprint('consorcios', __name__, url_prefix='/api/consorcios')


def gerar_parcelas_consorcio(consorcio, categoria_id):
    """
    Gera automaticamente as parcelas do consórcio como ItemDespesa

    Args:
        consorcio: Objeto ContratoConsorcio
        categoria_id: ID da categoria para as parcelas
    """
    if not categoria_id:
        raise ValueError("Categoria é obrigatória para gerar parcelas do consórcio")

    # Validar categoria
    categoria = Categoria.query.get(categoria_id)
    if not categoria:
        raise ValueError("Categoria não encontrada")

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
        data_vencimento = mes_atual.replace(day=5)
        despesa = ItemDespesa(
            nome=f"{consorcio.nome} - Parcela {i+1}/{consorcio.numero_parcelas}",
            descricao=f"Parcela {i+1} do consórcio {consorcio.nome}",
            valor=valor_ajustado,
            data_vencimento=data_vencimento,  # Vencimento no dia 5 do mês
            categoria_id=categoria_id,
            pago=False,
            recorrente=False,
            tipo='Consorcio',
            mes_competencia=mes_atual.strftime('%Y-%m')
        )

        db.session.add(despesa)
        db.session.flush()  # Garantir despesa.id para vincular a Conta

        mes_referencia = data_vencimento.replace(day=1)
        existente = Conta.query.filter_by(item_despesa_id=despesa.id, mes_referencia=mes_referencia).first()
        if not existente:
            conta = Conta(
                item_despesa_id=despesa.id,
                mes_referencia=mes_referencia,
                descricao=despesa.nome,
                valor=valor_ajustado,
                data_vencimento=data_vencimento,
                data_pagamento=None,
                status_pagamento='Pendente',
                debito_automatico=False,
                numero_parcela=i + 1,
                total_parcelas=consorcio.numero_parcelas,
                observacoes=None,
                is_fatura_cartao=False,
                valor_planejado=None,
                valor_executado=None,
                estouro_orcamento=False,
                cartao_competencia=None,
                status_fatura='ABERTA',
                data_consolidacao=None,
                valor_consolidado=None,
            )
            db.session.add(conta)
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

    # Fonte genérica (pontual, não recorrente)
    item_padrao = ItemReceita.query.filter_by(nome='Contemplação de Consórcio').first()
    if not item_padrao:
        item_padrao = ItemReceita(
            nome='Contemplação de Consórcio',
            tipo='OUTROS',
            descricao='Receita pontual gerada automaticamente por consórcio contemplado.',
            ativo=True,
            recorrente=False,
            valor_base_mensal=None,
            dia_previsto_pagamento=None,
            conta_origem_id=None,
        )
        db.session.add(item_padrao)
        db.session.flush()

    competencia = consorcio.mes_contemplacao.replace(day=1)
    marcador = f"consorcio_id={consorcio.id}"

    existente = ReceitaRealizada.query.filter(
        ReceitaRealizada.item_receita_id == item_padrao.id,
        ReceitaRealizada.mes_referencia == competencia,
        ReceitaRealizada.observacoes.ilike(f"%{marcador}%"),
    ).first()

    descricao = f"Consórcio {consorcio.nome} - contemplação (ID {consorcio.id})"

    if existente:
        existente.item_receita_id = item_padrao.id
        existente.data_recebimento = consorcio.mes_contemplacao
        existente.valor_recebido = consorcio.valor_premio
        existente.mes_referencia = competencia
        existente.descricao = descricao
        existente.observacoes = (existente.observacoes or '').strip() or marcador
        if marcador not in existente.observacoes:
            existente.observacoes = f"{existente.observacoes}\n{marcador}".strip()
        return existente

    receita = ReceitaRealizada(
        item_receita_id=item_padrao.id,
        data_recebimento=consorcio.mes_contemplacao,
        valor_recebido=consorcio.valor_premio,
        mes_referencia=competencia,
        conta_origem_id=None,
        descricao=descricao,
        orcamento_id=None,
        observacoes=marcador,
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
        campos_obrigatorios = ['nome', 'valor_inicial', 'numero_parcelas', 'mes_inicio', 'categoria_id']
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
            item_despesa_id=dados.get('item_despesa_id'),  # Opcional (legacy)
            item_receita_id=dados.get('item_receita_id'),
            observacoes=dados.get('observacoes')
        )

        db.session.add(consorcio)
        db.session.flush()  # Para obter o ID

        # Gerar parcelas automaticamente (usando categoria_id)
        categoria_id = int(dados['categoria_id'])
        parcelas = gerar_parcelas_consorcio(consorcio, categoria_id)

        # Gerar receita se houver contemplação
        receita = None
        if mes_contemplacao and dados.get('valor_premio'):
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
        if 'mes_contemplacao' in dados:
            if dados['mes_contemplacao']:
                consorcio.mes_contemplacao = datetime.strptime(dados['mes_contemplacao'][:10], '%Y-%m-%d').date()
            else:
                consorcio.mes_contemplacao = None
        if 'valor_premio' in dados:
            consorcio.valor_premio = float(dados['valor_premio']) if dados['valor_premio'] else None
        if 'ativo' in dados:
            consorcio.ativo = dados['ativo']

        receita = None
        if consorcio.mes_contemplacao and consorcio.valor_premio:
            receita = gerar_receita_contemplacao(consorcio)

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Consórcio atualizado com sucesso',
            'data': consorcio.to_dict(),
            'receita_gerada': receita is not None
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

        # Inativar parcelas (planejamento) e remover contas pendentes associadas
        parcelas = ItemDespesa.query.filter_by(tipo='Consorcio').filter(
            ItemDespesa.nome.like(f"{consorcio.nome} - Parcela%")
        ).all()
        parcela_ids = [p.id for p in parcelas]

        if parcela_ids:
            ItemDespesa.query.filter(ItemDespesa.id.in_(parcela_ids)).update(
                {'ativo': False},
                synchronize_session=False
            )
            Conta.query.filter(
                Conta.item_despesa_id.in_(parcela_ids),
                Conta.status_pagamento != 'Pago',
            ).delete(synchronize_session=False)

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

        # Buscar categoria de uma parcela existente (ou receber via body)
        dados = request.get_json() or {}
        categoria_id = dados.get('categoria_id')

        if not categoria_id:
            # Tentar pegar de uma parcela existente
            parcela_antiga = ItemDespesa.query.filter_by(tipo='Consorcio').filter(
                ItemDespesa.nome.like(f"{consorcio.nome} - Parcela%")
            ).first()

            if parcela_antiga:
                categoria_id = parcela_antiga.categoria_id
            else:
                return jsonify({
                    'success': False,
                    'error': 'categoria_id é obrigatório (nenhuma parcela anterior encontrada)'
                }), 400

        # Deletar parcelas antigas do consórcio (e suas Contas) antes de regenerar
        parcelas_query = ItemDespesa.query.filter_by(tipo='Consorcio').filter(
            ItemDespesa.nome.like(f"{consorcio.nome} - Parcela%")
        )
        parcelas_antigas = parcelas_query.all()
        ids_antigos = [p.id for p in parcelas_antigas]
        if ids_antigos:
            Conta.query.filter(Conta.item_despesa_id.in_(ids_antigos)).delete(synchronize_session=False)
        parcelas_query.delete(synchronize_session=False)

        # Gerar novas parcelas
        parcelas = gerar_parcelas_consorcio(consorcio, categoria_id)
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
