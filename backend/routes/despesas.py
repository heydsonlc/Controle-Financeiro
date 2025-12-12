"""
Rotas para gerenciamento de Despesas (Itens de Despesa)
"""
from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from sqlalchemy import func

try:
    from backend.models import db, ItemDespesa, Categoria, LancamentoAgregado, ItemAgregado, Conta
    from backend.services.cartao_service import CartaoService
except ImportError:
    from models import db, ItemDespesa, Categoria, LancamentoAgregado, ItemAgregado, Conta
    from services.cartao_service import CartaoService

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
    Lista todas as despesas, incluindo faturas virtuais de cartão

    Regra de agrupamento:
    - Despesas tipo='Simples': aparecem individualmente
    - Despesas tipo='Agregador' (cartões): faturas virtuais (Conta.is_fatura_cartao=True)
      mostram valor_planejado (pendente) ou valor_executado (pago)
    """
    try:
        resultado = []

        # 1. Buscar CONTAS que NÃO são faturas de cartão de crédito
        # (Despesas simples, consórcios, financiamentos, etc)
        from sqlalchemy import extract, or_

        # Buscar contas que:
        # - NÃO são fatura de cartão (is_fatura_cartao = False ou NULL)
        # IMPORTANTE: Não filtrar por ItemDespesa.ativo pois consórcios/financiamentos
        # podem ter ItemDespesa inativo mas geram Contas ativas
        contas_nao_cartao = db.session.query(Conta).join(
            ItemDespesa, Conta.item_despesa_id == ItemDespesa.id
        ).outerjoin(
            Categoria, ItemDespesa.categoria_id == Categoria.id
        ).filter(
            or_(
                Conta.is_fatura_cartao == False,
                Conta.is_fatura_cartao.is_(None)
            )
        ).order_by(
            Conta.data_vencimento.desc()
        ).all()

        # Converter cada conta para formato do frontend
        for conta in contas_nao_cartao:
            item = conta.item_despesa
            categoria = item.categoria if item else None

            conta_dict = {
                'id': conta.id,
                'nome': conta.descricao,
                'descricao': conta.observacoes or '',
                'tipo': item.tipo if item else 'Simples',
                'valor': float(conta.valor),
                'categoria_id': categoria.id if categoria else None,
                'categoria': categoria.to_dict() if categoria else None,
                'data_vencimento': conta.data_vencimento.isoformat(),
                'data_pagamento': conta.data_pagamento.isoformat() if conta.data_pagamento else None,
                'pago': (conta.status_pagamento == 'Pago'),
                'status_pagamento': conta.status_pagamento,
                'mes_competencia': conta.mes_referencia.strftime('%Y-%m'),
                'recorrente': item.recorrente if item else False,
                'tipo_recorrencia': item.tipo_recorrencia if item else None,
                'debito_automatico': conta.debito_automatico,
                'numero_parcela': conta.numero_parcela,
                'total_parcelas': conta.total_parcelas,
                'agrupado': False,
                'ativo': True,
                'is_fatura_cartao': False
            }
            resultado.append(conta_dict)

        # 2. Buscar FATURAS VIRTUAIS de cartão de crédito (Conta.is_fatura_cartao = True)
        faturas_cartao = db.session.query(Conta).join(
            ItemDespesa, Conta.item_despesa_id == ItemDespesa.id
        ).outerjoin(
            Categoria, ItemDespesa.categoria_id == Categoria.id
        ).filter(
            Conta.is_fatura_cartao == True
        ).order_by(
            Conta.data_vencimento.desc()
        ).all()

        # Converter cada fatura de cartão para formato do frontend
        for fatura in faturas_cartao:
            item = fatura.item_despesa
            categoria = item.categoria if item else None

            # REGRA: Exibir planejado (pendente) ou executado (pago)
            if fatura.status_pagamento == 'Pago':
                # Mostra valor executado real
                valor_exibido = float(fatura.valor_executado or fatura.valor or 0)
            else:
                # Mostra valor planejado (orçamento)
                valor_exibido = float(fatura.valor_planejado or fatura.valor or 0)

            fatura_dict = {
                'id': fatura.id,
                'nome': fatura.descricao,
                'descricao': fatura.observacoes or '',
                'tipo': 'Agregador',
                'valor': valor_exibido,
                'valor_planejado': float(fatura.valor_planejado or 0),
                'valor_executado': float(fatura.valor_executado or 0),
                'estouro_orcamento': fatura.estouro_orcamento or False,
                'categoria_id': categoria.id if categoria else None,
                'categoria': categoria.to_dict() if categoria else None,
                'data_vencimento': fatura.data_vencimento.isoformat(),
                'data_pagamento': fatura.data_pagamento.isoformat() if fatura.data_pagamento else None,
                'pago': (fatura.status_pagamento == 'Pago'),
                'status_pagamento': fatura.status_pagamento,
                'mes_competencia': fatura.cartao_competencia.strftime('%Y-%m'),
                'recorrente': False,
                'tipo_recorrencia': None,
                'debito_automatico': fatura.debito_automatico,
                'numero_parcela': None,
                'total_parcelas': None,
                'agrupado': True,  # Flag para indicar que é fatura de cartão
                'ativo': True,
                'is_fatura_cartao': True,
                'cartao_id': item.id if item else None
            }
            resultado.append(fatura_dict)

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
    """Obtém uma conta específica"""
    try:
        # Buscar na tabela Conta (não ItemDespesa)
        conta = Conta.query.get(id)
        if not conta:
            return jsonify({
                'success': False,
                'error': 'Despesa não encontrada'
            }), 404

        # Buscar ItemDespesa relacionado para pegar informações adicionais
        item_despesa = None
        if conta.item_despesa_id:
            item_despesa = ItemDespesa.query.get(conta.item_despesa_id)

        # Buscar categoria se existir
        categoria = None
        if item_despesa and item_despesa.categoria_id:
            categoria = Categoria.query.get(item_despesa.categoria_id)

        # Montar dados da conta
        conta_dict = {
            'id': conta.id,
            'item_despesa_id': conta.item_despesa_id,
            'descricao': conta.descricao,
            'valor': float(conta.valor) if conta.valor else 0,
            'data_vencimento': conta.data_vencimento.isoformat() if conta.data_vencimento else None,
            'data_pagamento': conta.data_pagamento.isoformat() if conta.data_pagamento else None,
            'status_pagamento': conta.status_pagamento,
            'mes_referencia': conta.mes_referencia.isoformat() if conta.mes_referencia else None,
            'numero_parcela': conta.numero_parcela,
            'total_parcelas': conta.total_parcelas,
            'observacoes': conta.observacoes,
            # Adicionar dados do ItemDespesa se existir
            'nome': item_despesa.nome if item_despesa else conta.descricao,
            'tipo': item_despesa.tipo if item_despesa else 'Simples',
            'categoria_id': item_despesa.categoria_id if item_despesa else None,
            'categoria_nome': categoria.nome if categoria else None,
            'recorrente': item_despesa.recorrente if item_despesa else False,
            'tipo_recorrencia': item_despesa.tipo_recorrencia if item_despesa else None,
            'pago': conta.status_pagamento == 'Pago'
        }

        return jsonify({
            'success': True,
            'data': conta_dict
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

        # Se for recorrente, gerar Contas para os próximos meses
        if despesa.recorrente and data_vencimento:
            try:
                gerar_contas_despesa_recorrente(despesa.id)
            except Exception as e:
                # Não falhar se a geração de contas der erro, apenas logar
                print(f'Aviso: Erro ao gerar contas recorrentes: {e}')

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
    """Atualiza uma conta específica"""
    try:
        # Buscar na tabela Conta (não ItemDespesa)
        conta = Conta.query.get(id)
        if not conta:
            return jsonify({
                'success': False,
                'error': 'Despesa não encontrada'
            }), 404

        dados = request.get_json()

        # Atualizar campos básicos da Conta
        if 'descricao' in dados:
            conta.descricao = dados['descricao']

        if 'valor' in dados:
            conta.valor = float(dados['valor'])

        if 'data_vencimento' in dados and dados['data_vencimento']:
            try:
                conta.data_vencimento = datetime.strptime(dados['data_vencimento'], '%Y-%m-%d').date()
            except ValueError:
                pass

        if 'observacoes' in dados:
            conta.observacoes = dados['observacoes']

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Despesa atualizada com sucesso'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@despesas_bp.route('/<int:id>_OLD', methods=['PUT'])
def atualizar_despesa_OLD(id):
    """[BACKUP] Atualiza uma despesa existente (única ou com futuras) - VERSÃO ANTIGA"""
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
    """Deleta uma conta específica"""
    try:
        # Buscar na tabela Conta (não ItemDespesa)
        conta = Conta.query.get(id)
        if not conta:
            return jsonify({
                'success': False,
                'error': 'Despesa não encontrada'
            }), 404

        # Deletar a conta
        db.session.delete(conta)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Despesa deletada com sucesso'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@despesas_bp.route('/<int:id>_OLD', methods=['DELETE'])
def deletar_despesa_OLD(id):
    """[BACKUP] Deleta uma despesa (única ou com futuras) - VERSÃO ANTIGA"""
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
    """
    Marca uma conta como paga

    IMPORTANTE: Se for fatura de cartão, usa CartaoService para
    substituir planejado por executado
    """
    try:
        # Buscar na tabela Conta (não ItemDespesa)
        conta = Conta.query.get(id)
        if not conta:
            return jsonify({
                'success': False,
                'error': 'Despesa não encontrada'
            }), 404

        dados = request.get_json() or {}

        # Determinar data de pagamento
        data_pagamento = datetime.now().date()
        if dados.get('data_pagamento'):
            try:
                data_pagamento = datetime.strptime(dados['data_pagamento'], '%Y-%m-%d').date()
            except ValueError:
                pass

        # Determinar valor pago
        valor_pago = dados.get('valor_pago')

        # SE FOR FATURA DE CARTÃO: usar CartaoService
        if conta.is_fatura_cartao:
            conta = CartaoService.pagar_fatura(
                fatura_id=id,
                data_pagamento=data_pagamento,
                valor_pago=valor_pago
            )

            db.session.commit()

            return jsonify({
                'success': True,
                'message': 'Fatura de cartão paga com sucesso',
                'data': {
                    'id': conta.id,
                    'valor_planejado': float(conta.valor_planejado),
                    'valor_executado': float(conta.valor_executado),
                    'valor_pago': float(conta.valor),
                    'data_pagamento': conta.data_pagamento.strftime('%Y-%m-%d'),
                    'estouro_orcamento': conta.estouro_orcamento
                }
            }), 200

        # SE NÃO FOR FATURA: lógica tradicional
        conta.status_pagamento = 'Pago'
        conta.data_pagamento = data_pagamento

        # Se um valor pago foi fornecido, atualizar o valor da conta
        if valor_pago is not None:
            conta.valor = float(valor_pago)

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Despesa marcada como paga',
            'data': {
                'id': conta.id,
                'status_pagamento': conta.status_pagamento,
                'data_pagamento': conta.data_pagamento.isoformat() if conta.data_pagamento else None,
                'valor': float(conta.valor) if conta.valor else 0
            }
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================================================
# FUNÇÕES AUXILIARES PARA DESPESAS RECORRENTES
# ============================================================================

def gerar_contas_despesa_recorrente(item_despesa_id, meses_futuros=12):
    """
    Gera Contas para despesas recorrentes (mensal ou semanal)

    Similar ao sistema de financiamentos, cria registros na tabela Conta
    para que a despesa recorrente apareça na listagem de despesas

    Args:
        item_despesa_id (int): ID do ItemDespesa recorrente
        meses_futuros (int): Quantos meses à frente gerar contas (padrão: 12)
    """
    item = ItemDespesa.query.get(item_despesa_id)
    if not item:
        raise ValueError('ItemDespesa não encontrado')

    if not item.recorrente:
        raise ValueError('ItemDespesa não é recorrente')

    if not item.data_vencimento:
        raise ValueError('ItemDespesa recorrente precisa ter data_vencimento')

    tipo_recorrencia = item.tipo_recorrencia or 'mensal'
    data_inicio = item.data_vencimento

    # Deletar contas futuras existentes (para regenerar)
    hoje = datetime.now().date()
    Conta.query.filter(
        Conta.item_despesa_id == item_despesa_id,
        Conta.data_vencimento >= hoje,
        Conta.status_pagamento == 'Pendente'
    ).delete()

    contas_criadas = []

    if tipo_recorrencia == 'mensal':
        # Gerar contas mensais
        for i in range(meses_futuros):
            data_vencimento = data_inicio + relativedelta(months=i)

            # Pular se já passou
            if data_vencimento < hoje:
                continue

            # Calcular competência (mês de referência)
            mes_referencia = data_vencimento.replace(day=1)

            # Verificar se já existe conta para este mês
            conta_existente = Conta.query.filter_by(
                item_despesa_id=item_despesa_id,
                mes_referencia=mes_referencia
            ).first()

            if not conta_existente:
                nova_conta = Conta(
                    item_despesa_id=item_despesa_id,
                    mes_referencia=mes_referencia,
                    descricao=item.nome,
                    valor=item.valor,
                    data_vencimento=data_vencimento,
                    status_pagamento='Pendente',
                    observacoes=item.descricao or ''
                )
                db.session.add(nova_conta)
                contas_criadas.append(nova_conta)

    elif tipo_recorrencia == 'semanal' or tipo_recorrencia.startswith('semanal_'):
        # Suporta: 'semanal' ou 'semanal_X_Y' onde X=intervalo de semanas, Y=dia da semana
        intervalo_semanas = 2  # padrão quinzenal
        dia_semana_alvo = None  # None = usa data_inicio

        if tipo_recorrencia.startswith('semanal_'):
            # Formato: semanal_2_1 (a cada 2 semanas, segunda-feira=1)
            partes = tipo_recorrencia.split('_')
            if len(partes) >= 2:
                intervalo_semanas = int(partes[1])
            if len(partes) >= 3:
                dia_semana_alvo = int(partes[2])  # 0=domingo, 1=segunda, ..., 6=sábado

        # Ajustar data_inicio para o dia da semana correto
        data_atual = data_inicio
        if dia_semana_alvo is not None:
            # Encontrar a próxima ocorrência do dia da semana alvo
            dias_ate_alvo = (dia_semana_alvo - data_atual.weekday()) % 7
            if dias_ate_alvo > 0:
                data_atual += timedelta(days=dias_ate_alvo)

        data_fim = hoje + relativedelta(months=meses_futuros)

        while data_atual <= data_fim:
            # Pular se já passou
            if data_atual >= hoje:
                # Calcular competência (mês de referência)
                mes_referencia = data_atual.replace(day=1)

                # Verificar se já existe conta para esta data
                conta_existente = Conta.query.filter_by(
                    item_despesa_id=item_despesa_id,
                    data_vencimento=data_atual
                ).first()

                if not conta_existente:
                    nova_conta = Conta(
                        item_despesa_id=item_despesa_id,
                        mes_referencia=mes_referencia,
                        descricao=f'{item.nome} - {data_atual.strftime("%d/%m/%Y")}',
                        valor=item.valor,
                        data_vencimento=data_atual,
                        status_pagamento='Pendente',
                        observacoes=item.descricao or ''
                    )
                    db.session.add(nova_conta)
                    contas_criadas.append(nova_conta)

            # Avançar pelo intervalo especificado
            data_atual += timedelta(weeks=intervalo_semanas)

    db.session.commit()
    return contas_criadas
