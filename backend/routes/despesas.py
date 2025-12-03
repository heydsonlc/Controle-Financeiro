"""
Rotas para gerenciamento de Despesas (Itens de Despesa)
"""
from flask import Blueprint, request, jsonify
from datetime import datetime
from dateutil.relativedelta import relativedelta
from sqlalchemy import func

try:
    from backend.models import db, ItemDespesa, Categoria, LancamentoAgregado, ItemAgregado
except ImportError:
    from models import db, ItemDespesa, Categoria, LancamentoAgregado, ItemAgregado

despesas_bp = Blueprint('despesas', __name__, url_prefix='/api/despesas')


def calcular_competencia(data_vencimento):
    """
    Calcula o mês de competência (mês do salário que paga a despesa)
    Regra: A competência é o mês anterior ao vencimento

    Exemplo:
    - Vencimento em 15/12/2025 → Competência: 11/2025 (Novembro)
    - Vencimento em 05/01/2026 → Competência: 12/2025 (Dezembro)

    Args:
        data_vencimento: objeto date ou None

    Returns:
        String no formato 'YYYY-MM' ou None
    """
    if not data_vencimento:
        return None

    # Subtrai 1 mês da data de vencimento
    mes_competencia = data_vencimento - relativedelta(months=1)
    return mes_competencia.strftime('%Y-%m')


@despesas_bp.route('/', methods=['GET'])
def listar_despesas():
    """
    Lista todas as despesas, agrupando cartões de crédito por competência

    Regra de agrupamento:
    - Despesas tipo='Simples': aparecem individualmente
    - Despesas tipo='Agregador' (cartões): são agrupadas por mes_competencia,
      somando todos os lançamentos (LancamentoAgregado) daquele mês
    """
    try:
        resultado = []

        # 1. Buscar despesas que NÃO são cartões de crédito (Simples, Consorcio, etc)
        # Todos os tipos EXCETO 'Agregador' aparecem individualmente
        despesas_individuais = ItemDespesa.query.filter(
            ItemDespesa.tipo != 'Agregador',
            ItemDespesa.ativo == True
        ).all()
        for despesa in despesas_individuais:
            resultado.append(despesa.to_dict())

        # 2. Buscar cartões de crédito (tipo='Agregador')
        cartoes = ItemDespesa.query.filter_by(tipo='Agregador', ativo=True).all()

        # Para cada cartão, agrupar lançamentos por mês de fatura
        for cartao in cartoes:
            # Buscar todos os itens agregados (categorias) deste cartão
            itens_cartao = ItemAgregado.query.filter_by(
                item_despesa_id=cartao.id,
                ativo=True
            ).all()

            if not itens_cartao:
                continue

            # IDs dos itens agregados
            ids_itens = [item.id for item in itens_cartao]

            # Agrupar lançamentos por mes_fatura e somar valores
            faturas = db.session.query(
                LancamentoAgregado.mes_fatura,
                func.sum(LancamentoAgregado.valor).label('total_fatura')
            ).filter(
                LancamentoAgregado.item_agregado_id.in_(ids_itens)
            ).group_by(
                LancamentoAgregado.mes_fatura
            ).all()

            # Criar uma "despesa virtual" para cada fatura do cartão
            for fatura in faturas:
                mes_fatura = fatura.mes_fatura
                total = float(fatura.total_fatura)

                # Calcular competência (mês anterior ao vencimento da fatura)
                mes_competencia = calcular_competencia(mes_fatura)

                # Criar dict representando a fatura agrupada
                fatura_agrupada = {
                    'id': f"cartao_{cartao.id}_{mes_fatura.strftime('%Y%m')}",  # ID único para frontend
                    'nome': f"{cartao.nome} - Fatura {mes_fatura.strftime('%m/%Y')}",
                    'tipo': 'Agregador',
                    'valor': total,
                    'categoria_id': cartao.categoria_id,
                    'categoria': cartao.categoria.to_dict() if cartao.categoria else None,
                    'mes_competencia': mes_competencia,
                    'data_vencimento': mes_fatura.isoformat(),
                    'pago': False,  # TODO: verificar se fatura foi paga
                    'recorrente': False,
                    'agrupado': True,  # Flag para indicar que é um item agrupado
                    'cartao_id': cartao.id
                }

                resultado.append(fatura_agrupada)

        # Ordenar por data de vencimento (mais recente primeiro)
        resultado.sort(key=lambda x: x.get('data_vencimento', ''), reverse=True)

        return jsonify({
            'success': True,
            'data': resultado
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@despesas_bp.route('/<int:id>', methods=['GET'])
def obter_despesa(id):
    """Obtém uma despesa específica"""
    try:
        despesa = ItemDespesa.query.get(id)
        if not despesa:
            return jsonify({
                'success': False,
                'error': 'Despesa não encontrada'
            }), 404

        return jsonify({
            'success': True,
            'data': despesa.to_dict()
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@despesas_bp.route('/', methods=['POST'])
def criar_despesa():
    """Cria uma nova despesa"""
    try:
        dados = request.get_json()

        # Validações
        if not dados.get('nome'):
            return jsonify({
                'success': False,
                'error': 'Nome é obrigatório'
            }), 400

        if not dados.get('valor'):
            return jsonify({
                'success': False,
                'error': 'Valor é obrigatório'
            }), 400

        if not dados.get('categoria_id'):
            return jsonify({
                'success': False,
                'error': 'Categoria é obrigatória'
            }), 400

        # Verificar se categoria existe
        categoria = Categoria.query.get(dados.get('categoria_id'))
        if not categoria:
            return jsonify({
                'success': False,
                'error': 'Categoria não encontrada'
            }), 404

        # Converter datas
        data_vencimento = None
        if dados.get('data_vencimento'):
            try:
                data_vencimento = datetime.strptime(dados['data_vencimento'], '%Y-%m-%d').date()
            except ValueError:
                return jsonify({
                    'success': False,
                    'error': 'Formato de data inválido. Use YYYY-MM-DD'
                }), 400

        data_pagamento = None
        if dados.get('data_pagamento'):
            try:
                data_pagamento = datetime.strptime(dados['data_pagamento'], '%Y-%m-%d').date()
            except ValueError:
                return jsonify({
                    'success': False,
                    'error': 'Formato de data de pagamento inválido. Use YYYY-MM-DD'
                }), 400

        # Calcular competência automaticamente se não fornecida
        mes_competencia = dados.get('mes_competencia')
        if not mes_competencia and data_vencimento:
            mes_competencia = calcular_competencia(data_vencimento)

        # Criar despesa
        despesa = ItemDespesa(
            nome=dados['nome'],
            descricao=dados.get('descricao'),
            valor=float(dados['valor']),
            data_vencimento=data_vencimento,
            data_pagamento=data_pagamento,
            categoria_id=dados['categoria_id'],
            pago=dados.get('pago', False),
            recorrente=dados.get('recorrente', False),
            tipo_recorrencia=dados.get('tipo_recorrencia', 'mensal'),
            mes_competencia=mes_competencia,
            tipo='Simples'  # Define o tipo como 'Simples' por padrão
        )

        db.session.add(despesa)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Despesa criada com sucesso',
            'data': despesa.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@despesas_bp.route('/<int:id>', methods=['PUT'])
def atualizar_despesa(id):
    """Atualiza uma despesa existente (única ou com futuras)"""
    try:
        despesa = ItemDespesa.query.get(id)
        if not despesa:
            return jsonify({
                'success': False,
                'error': 'Despesa não encontrada'
            }), 404

        dados = request.get_json()

        # Verificar se deve atualizar apenas esta ou incluir futuras
        tipo_edicao = request.args.get('tipo_edicao', 'unica')

        despesas_para_atualizar = [despesa]

        if tipo_edicao == 'futuras':
            # Atualizar esta despesa e todas as futuras do mesmo grupo
            if despesa.tipo == 'Consorcio':
                # Para consórcio, buscar parcelas futuras pelo nome base
                nome_base = despesa.nome.rsplit(' - Parcela ', 1)[0] if ' - Parcela ' in despesa.nome else despesa.nome
                mes_competencia_atual = despesa.mes_competencia

                # Buscar parcelas futuras do mesmo consórcio
                parcelas_futuras = ItemDespesa.query.filter(
                    ItemDespesa.tipo == 'Consorcio',
                    ItemDespesa.nome.like(f"{nome_base} - Parcela%"),
                    ItemDespesa.mes_competencia >= mes_competencia_atual,
                    ItemDespesa.id != id
                ).all()

                despesas_para_atualizar.extend(parcelas_futuras)

            elif despesa.recorrente:
                # Para recorrente, buscar despesas futuras com mesmo nome e categoria
                mes_competencia_atual = despesa.mes_competencia

                despesas_futuras = ItemDespesa.query.filter(
                    ItemDespesa.nome == despesa.nome,
                    ItemDespesa.categoria_id == despesa.categoria_id,
                    ItemDespesa.recorrente == True,
                    ItemDespesa.mes_competencia >= mes_competencia_atual,
                    ItemDespesa.id != id
                ).all()

                despesas_para_atualizar.extend(despesas_futuras)

        # Validar campos antes de atualizar
        if 'nome' in dados and not dados['nome']:
            return jsonify({
                'success': False,
                'error': 'Nome não pode ser vazio'
            }), 400

        if 'categoria_id' in dados:
            categoria = Categoria.query.get(dados['categoria_id'])
            if not categoria:
                return jsonify({
                    'success': False,
                    'error': 'Categoria não encontrada'
                }), 404

        # Atualizar todos os campos para cada despesa
        for desp in despesas_para_atualizar:
            if 'nome' in dados:
                # Se for múltiplas parcelas de consórcio, manter o número da parcela
                if tipo_edicao == 'futuras' and desp.tipo == 'Consorcio' and ' - Parcela ' in desp.nome:
                    sufixo_parcela = ' - Parcela ' + desp.nome.split(' - Parcela ')[1]
                    desp.nome = dados['nome'] + sufixo_parcela
                else:
                    desp.nome = dados['nome']

            if 'descricao' in dados:
                desp.descricao = dados['descricao']

            if 'valor' in dados:
                desp.valor = float(dados['valor'])

            if 'categoria_id' in dados:
                desp.categoria_id = dados['categoria_id']

            # Para edição única, permitir alterar datas
            if tipo_edicao == 'unica':
                if 'data_vencimento' in dados:
                    if dados['data_vencimento']:
                        try:
                            desp.data_vencimento = datetime.strptime(dados['data_vencimento'], '%Y-%m-%d').date()
                            if 'mes_competencia' not in dados:
                                desp.mes_competencia = calcular_competencia(desp.data_vencimento)
                        except ValueError:
                            return jsonify({
                                'success': False,
                                'error': 'Formato de data inválido. Use YYYY-MM-DD'
                            }), 400
                    else:
                        desp.data_vencimento = None
                        desp.mes_competencia = None

                if 'data_pagamento' in dados:
                    if dados['data_pagamento']:
                        try:
                            desp.data_pagamento = datetime.strptime(dados['data_pagamento'], '%Y-%m-%d').date()
                        except ValueError:
                            return jsonify({
                                'success': False,
                                'error': 'Formato de data de pagamento inválido. Use YYYY-MM-DD'
                            }), 400
                    else:
                        desp.data_pagamento = None

            if 'pago' in dados:
                desp.pago = dados['pago']

            if 'recorrente' in dados:
                desp.recorrente = dados['recorrente']

            if 'tipo_recorrencia' in dados:
                desp.tipo_recorrencia = dados['tipo_recorrencia']

            if 'mes_competencia' in dados:
                desp.mes_competencia = dados['mes_competencia']

        db.session.commit()

        mensagem = 'Despesa atualizada com sucesso'
        if tipo_edicao == 'futuras' and len(despesas_para_atualizar) > 1:
            mensagem = f'Despesa e {len(despesas_para_atualizar) - 1} parcela(s) futura(s) atualizadas com sucesso'

        return jsonify({
            'success': True,
            'message': mensagem,
            'quantidade_atualizada': len(despesas_para_atualizar),
            'data': despesa.to_dict()
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@despesas_bp.route('/<int:id>', methods=['DELETE'])
def deletar_despesa(id):
    """Deleta uma despesa (única ou com futuras)"""
    try:
        despesa = ItemDespesa.query.get(id)
        if not despesa:
            return jsonify({
                'success': False,
                'error': 'Despesa não encontrada'
            }), 404

        # Verificar se deve deletar apenas esta ou incluir futuras
        tipo_exclusao = request.args.get('tipo_exclusao', 'unica')

        despesas_para_deletar = [despesa]

        if tipo_exclusao == 'futuras':
            # Deletar esta despesa e todas as futuras do mesmo grupo
            if despesa.tipo == 'Consorcio':
                # Para consórcio, buscar parcelas futuras pelo nome base
                # Nome formato: "Consórcio X - Parcela N/M"
                nome_base = despesa.nome.rsplit(' - Parcela ', 1)[0] if ' - Parcela ' in despesa.nome else despesa.nome
                mes_competencia_atual = despesa.mes_competencia

                # Buscar parcelas futuras do mesmo consórcio
                parcelas_futuras = ItemDespesa.query.filter(
                    ItemDespesa.tipo == 'Consorcio',
                    ItemDespesa.nome.like(f"{nome_base} - Parcela%"),
                    ItemDespesa.mes_competencia >= mes_competencia_atual,
                    ItemDespesa.id != id
                ).all()

                despesas_para_deletar.extend(parcelas_futuras)

            elif despesa.recorrente:
                # Para recorrente, buscar despesas futuras com mesmo nome e categoria
                mes_competencia_atual = despesa.mes_competencia

                despesas_futuras = ItemDespesa.query.filter(
                    ItemDespesa.nome == despesa.nome,
                    ItemDespesa.categoria_id == despesa.categoria_id,
                    ItemDespesa.recorrente == True,
                    ItemDespesa.mes_competencia >= mes_competencia_atual,
                    ItemDespesa.id != id
                ).all()

                despesas_para_deletar.extend(despesas_futuras)

        # Deletar todas as despesas selecionadas
        for d in despesas_para_deletar:
            db.session.delete(d)

        db.session.commit()

        mensagem = f'{len(despesas_para_deletar)} despesa(s) deletada(s) com sucesso'
        if tipo_exclusao == 'futuras' and len(despesas_para_deletar) > 1:
            mensagem = f'Despesa e {len(despesas_para_deletar) - 1} parcela(s) futura(s) deletadas com sucesso'

        return jsonify({
            'success': True,
            'message': mensagem,
            'quantidade_deletada': len(despesas_para_deletar)
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@despesas_bp.route('/<int:id>/pagar', methods=['POST'])
def marcar_como_pago(id):
    """Marca uma despesa como paga"""
    try:
        despesa = ItemDespesa.query.get(id)
        if not despesa:
            return jsonify({
                'success': False,
                'error': 'Despesa não encontrada'
            }), 404

        dados = request.get_json() or {}

        despesa.pago = True
        despesa.data_pagamento = datetime.now().date()

        # Se uma data específica foi fornecida
        if dados.get('data_pagamento'):
            try:
                despesa.data_pagamento = datetime.strptime(dados['data_pagamento'], '%Y-%m-%d').date()
            except ValueError:
                pass

        # Se um valor pago foi fornecido, usar ele; caso contrário, usar o valor previsto
        if dados.get('valor_pago') is not None:
            despesa.valor_pago = float(dados['valor_pago'])
        else:
            # Se nenhum valor foi fornecido, assumir que pagou o valor previsto
            despesa.valor_pago = despesa.valor

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Despesa marcada como paga',
            'data': despesa.to_dict()
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
