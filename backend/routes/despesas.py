"""
Rotas para gerenciamento de Despesas (Itens de Despesa)
"""
from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
import json
from dateutil.relativedelta import relativedelta
from sqlalchemy import func

try:
    from backend.models import db, ItemDespesa, Categoria, LancamentoAgregado, ItemAgregado, OrcamentoAgregado, Conta
    from backend.services.cartao_service import CartaoService
except ImportError:
    from models import db, ItemDespesa, Categoria, LancamentoAgregado, ItemAgregado, OrcamentoAgregado, Conta
    from services.cartao_service import CartaoService

despesas_bp = Blueprint('despesas', __name__, url_prefix='/api/despesas')


def _ler_payload_request():
    dados = request.get_json(silent=True)
    if not dados:
        dados = request.form.to_dict()
    return dados or {}


def _to_int(value):
    try:
        if value is None:
            return None
        if isinstance(value, str) and value.strip() == '':
            return None
        return int(value)
    except Exception:
        return None


def _normalizar_meio_pagamento(value):
    return (value or '').strip().lower() or None


def gerar_execucao_despesa_recorrente(item_despesa_id, meses_futuros=1, mes_referencia=None):
    """
    Orquestrador único de recorrência:
    - Se meio_pagamento == 'cartao' → gera LancamentoAgregado
    - Caso contrário → gera Conta

    IMPORTANTE: esta função NÃO faz commit; o caller controla a transação.
    """
    item = ItemDespesa.query.get(item_despesa_id)
    if not item:
        raise ValueError('ItemDespesa não encontrado')
    if not item.recorrente:
        return []

    if item.meio_pagamento == 'cartao':
        if not item.cartao_id:
            return []
        return gerar_lancamentos_cartao_recorrente(item.id, meses_futuros=meses_futuros, mes_referencia=mes_referencia)

    return gerar_contas_despesa_recorrente(item.id, meses_futuros=meses_futuros, mes_referencia=mes_referencia)


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


def _calcular_totais_fatura_cartao_previsto(cartao_id, competencia):
    """
    Retorna (total_previsto, total_executado) para a fatura de um cartão no mês.

    Definição:
    - total_executado = soma de TODOS os LancamentoAgregado do mês (com e sem categoria)
    - total_previsto = total_executado + soma(max(0, orcado_categoria - gasto_categoria))
      (equivalente a somar max(orcado, gasto) por categoria sem duplo-contar os gastos)
    """
    comp = competencia.replace(day=1)

    total_executado = db.session.query(
        func.coalesce(func.sum(LancamentoAgregado.valor), 0)
    ).filter(
        LancamentoAgregado.cartao_id == cartao_id,
        LancamentoAgregado.mes_fatura == comp
    ).scalar()
    total_executado = float(total_executado or 0)

    itens = ItemAgregado.query.filter_by(item_despesa_id=cartao_id, ativo=True).all()
    if not itens:
        return total_executado, total_executado

    itens_ids = [i.id for i in itens]

    gastos_por_item = dict(
        db.session.query(
            LancamentoAgregado.item_agregado_id,
            func.coalesce(func.sum(LancamentoAgregado.valor), 0)
        ).filter(
            LancamentoAgregado.cartao_id == cartao_id,
            LancamentoAgregado.mes_fatura == comp,
            LancamentoAgregado.item_agregado_id.in_(itens_ids)
        ).group_by(
            LancamentoAgregado.item_agregado_id
        ).all()
    )

    orcados_por_item = dict(
        db.session.query(
            OrcamentoAgregado.item_agregado_id,
            func.coalesce(func.sum(OrcamentoAgregado.valor_teto), 0)
        ).filter(
            OrcamentoAgregado.mes_referencia == comp,
            OrcamentoAgregado.item_agregado_id.in_(itens_ids)
        ).group_by(
            OrcamentoAgregado.item_agregado_id
        ).all()
    )

    complemento_orcamento = 0.0
    for item_id in itens_ids:
        gasto = float(gastos_por_item.get(item_id, 0) or 0)
        orcado = float(orcados_por_item.get(item_id, 0) or 0)
        if orcado > gasto:
            complemento_orcamento += (orcado - gasto)

    total_previsto = total_executado + complemento_orcamento
    return total_previsto, total_executado


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
        # ✅ LAZY GENERATION: Preencher lacunas até o mês navegado + 1 mês futuro
        # ⚠️ Dashboard NÃO deve passar mes_arg - apenas navegação explícita por mês
        mes_arg = request.args.get('mes_referencia') or request.args.get('mes')

        if mes_arg:
            try:
                mes_referencia = datetime.strptime(f"{mes_arg}-01", "%Y-%m-%d").date()
                despesas_recorrentes = ItemDespesa.query.filter_by(recorrente=True).all()

                for desp in despesas_recorrentes:
                    if not desp.data_vencimento:
                        continue

                    # Calcular quantos meses entre o início da despesa e o mês navegado
                    inicio = desp.data_vencimento.replace(day=1)

                    # Calcular diferença em meses
                    meses_diferenca = (mes_referencia.year - inicio.year) * 12 + \
                                     (mes_referencia.month - inicio.month)

                    # Garantir que preencha ATÉ o mês navegado + 1 mês futuro (UX suave)
                    # Se meses_diferenca < 0, a despesa é futura, então gerar apenas se for o mês
                    # Se meses_diferenca >= 0, gerar até o mês navegado + 1
                    if meses_diferenca >= 0:
                        meses_futuros = meses_diferenca + 2  # Mês navegado + próximo mês
                    else:
                        meses_futuros = 1  # Despesa futura, gerar apenas se for o mês

                    # Gerar todas as contas necessárias (preenchendo lacunas)
                    # mes_referencia=None faz gerar a partir da data_vencimento
                    gerar_execucao_despesa_recorrente(
                        desp.id,
                        meses_futuros=meses_futuros,
                        mes_referencia=None
                    )

                # ✅ LAZY GENERATION (CARTÕES): garantir que a fatura exista
                # mesmo sem lançamentos, para o mês navegado (+1 mês futuro)
                competencias_fatura = [
                    mes_referencia.replace(day=1),
                    (mes_referencia + relativedelta(months=1)).replace(day=1),
                ]
                cartoes_ativos = ItemDespesa.query.filter_by(tipo='Agregador', ativo=True).all()
                for cartao in cartoes_ativos:
                    for comp in competencias_fatura:
                        try:
                            CartaoService.get_or_create_fatura(cartao.id, comp)
                        except Exception:
                            continue

                db.session.commit()
            except Exception as e:
                db.session.rollback()
                # Continuar mesmo com erro (modo degradado - lista apenas o que existe)
                pass

        resultado = []

        # 1. Buscar CONTAS que NÃO são faturas de cartão de crédito
        # (Despesas simples, consórcios, financiamentos, etc)
        from sqlalchemy import extract, or_

        # Buscar contas que:
        # - NÃO são fatura de cartão (is_fatura_cartao = False ou NULL)
        # IMPORTANTE: Não filtrar por ItemDespesa.ativo pois consórcios/financiamentos
        # podem ter ItemDespesa inativo mas geram Contas ativas
        contas_nao_cartao = db.session.query(Conta).outerjoin(
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
                'financiamento_parcela_id': conta.financiamento_parcela_id,
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
        faturas_cartao = db.session.query(Conta).outerjoin(
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

            # REGRA: Card da fatura:
            # - Se PENDENTE → exibe TOTAL PREVISTO da fatura
            # - Se PAGA → exibe TOTAL EXECUTADO
            total_previsto = float(fatura.valor_planejado or fatura.valor or 0)
            total_executado = float(fatura.valor_executado or 0)

            if getattr(fatura, 'cartao_competencia', None) and fatura.item_despesa_id:
                total_previsto_calc, total_executado_calc = _calcular_totais_fatura_cartao_previsto(
                    cartao_id=fatura.item_despesa_id,
                    competencia=fatura.cartao_competencia
                )
                total_previsto = total_previsto_calc
                total_executado = total_executado_calc  # Sempre usar valor recalculado (fonte da verdade: LancamentoAgregado)

            valor_exibido = total_executado if fatura.status_pagamento == 'Pago' else total_previsto

            fatura_dict = {
                'id': fatura.id,
                'nome': fatura.descricao,
                'descricao': fatura.observacoes or '',
                'tipo': 'cartao',  # ← CORRIGIDO: era 'Agregador', mas frontend espera 'cartao'
                'valor': valor_exibido,
                'financiamento_parcela_id': None,
                'valor_fatura': valor_exibido,  # ← ADICIONADO: campo que frontend espera ler
                'valor_planejado': total_previsto,
                'valor_executado': total_executado,
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
        # ==========================================================
        # CORREÇÃO DEFINITIVA — LEITURA CORRETA DO PAYLOAD
        # SUPORTA JSON E FORM-DATA
        # ==========================================================

        dados = _ler_payload_request()

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
        db.session.flush()  # Garante despesa.id antes de qualquer lógica derivada

        # ==========================================================
        # PERSISTÊNCIA CORRETA — PAGAMENTO VIA CARTÃO
        # ==========================================================

        meio_pagamento = _normalizar_meio_pagamento(dados.get('meio_pagamento'))
        despesa.meio_pagamento = meio_pagamento

        # Se for despesa recorrente paga via cartão de crédito
        if bool(despesa.recorrente) and meio_pagamento == 'cartao':
            cartao_id = _to_int(dados.get('cartao_id'))
            item_agregado_id = _to_int(dados.get('item_agregado_id'))

            # Validação mínima de integridade
            if not cartao_id:
                db.session.rollback()
                return jsonify({
                    'success': False,
                    'error': "cartao_id é obrigatório quando meio_pagamento = 'cartao'."
                }), 400

            despesa.cartao_id = cartao_id
            despesa.item_agregado_id = item_agregado_id
        else:
            # Garantir limpeza para outros meios de pagamento
            despesa.cartao_id = None
            despesa.item_agregado_id = None

        try:
            if despesa.recorrente:
                # ✅ LAZY GENERATION: Gerar apenas o mês inicial
                # O restante será gerado conforme o usuário navegar pelos meses
                gerar_execucao_despesa_recorrente(despesa.id, meses_futuros=1, mes_referencia=None)
            else:
                # Se NÃO for recorrente, criar UMA Conta imediatamente
                # Isso garante que a despesa apareça no histórico de lançamentos
                if data_vencimento:
                    mes_referencia = data_vencimento.replace(day=1)
                    status = 'Pago' if dados.get('pago') or data_pagamento else 'Pendente'

                    nova_conta = Conta(
                        item_despesa_id=despesa.id,
                        mes_referencia=mes_referencia,
                        descricao=despesa.nome,
                        valor=despesa.valor,
                        data_vencimento=data_vencimento,
                        data_pagamento=data_pagamento,
                        status_pagamento=status,
                        debito_automatico=False,
                        numero_parcela=1,
                        total_parcelas=1,
                        observacoes=despesa.descricao,
                        is_fatura_cartao=False
                    )
                    db.session.add(nova_conta)

            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return jsonify({
                'success': False,
                'error': f'Falha ao gerar recorrência: {str(e)}'
            }), 500

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

        if 'data_pagamento' in dados:
            if dados['data_pagamento']:
                try:
                    conta.data_pagamento = datetime.strptime(dados['data_pagamento'], '%Y-%m-%d').date()
                    # Se definir data de pagamento, marcar como pago
                    if conta.status_pagamento != 'Pago':
                        conta.status_pagamento = 'Pago'
                except ValueError:
                    pass
            else:
                conta.data_pagamento = None
                conta.status_pagamento = 'Pendente'

        # Atualizar status de pagamento se fornecido explicitamente
        if 'pago' in dados:
            if dados['pago']:
                conta.status_pagamento = 'Pago'
                # Se não tem data de pagamento, usar data de vencimento
                if not conta.data_pagamento:
                    conta.data_pagamento = conta.data_vencimento
            else:
                conta.status_pagamento = 'Pendente'
                conta.data_pagamento = None

        db.session.commit()

        # ========================================================================
        # HOOK: Sincronizar pagamento com Financiamento (se aplicável)
        # ========================================================================
        # Se esta conta está vinculada a uma parcela de financiamento E foi marcada como paga,
        # chamar o motor do financiamento para sincronizar estado
        if conta.financiamento_parcela_id and conta.status_pagamento == 'Pago':
            from backend.services.financiamento_service import FinanciamentoService

            # Registrar pagamento no motor do financiamento
            # Isso atualiza: parcela.status, parcela.valor_pago, saldo soberano, etc.
            FinanciamentoService.registrar_pagamento_parcela(
                parcela_id=conta.financiamento_parcela_id,
                valor_pago=conta.valor,
                data_pagamento=conta.data_pagamento or conta.data_vencimento
            )

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
                valor_pago=valor_pago,
                conta_bancaria_id=dados.get('conta_bancaria_id')
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

        # ========================================================================
        # HOOK: Sincronizar pagamento com Financiamento (se aplicável)
        # ========================================================================
        # Se esta conta está vinculada a uma parcela de financiamento E foi marcada como paga,
        # chamar o motor do financiamento para sincronizar estado
        if conta.financiamento_parcela_id and conta.status_pagamento == 'Pago':
            from backend.services.financiamento_service import FinanciamentoService

            # Registrar pagamento no motor do financiamento
            # Isso atualiza: parcela.status, parcela.valor_pago, saldo soberano, etc.
            FinanciamentoService.registrar_pagamento_parcela(
                parcela_id=conta.financiamento_parcela_id,
                valor_pago=conta.valor,
                data_pagamento=conta.data_pagamento or conta.data_vencimento
            )

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

def normalizar_dias_semana(dias):
    """
    Recebe lista ou string e retorna lista padronizada sem acentos:
    ['segunda','terca','quarta','quinta','sexta','sabado','domingo']
    """
    if not dias:
        return []
    if isinstance(dias, str):
        try:
            import json
            parsed = json.loads(dias)
            if isinstance(parsed, list):
                dias = parsed
            else:
                dias = [d.strip() for d in dias.split(",") if d.strip()]
        except Exception:
            dias = [d.strip() for d in dias.split(",") if d.strip()]
    nomes = {
        'segunda': 'segunda', 'seg': 'segunda', '1': 'segunda',
        'terca': 'terca', 'ter': 'terca', '2': 'terca',
        'quarta': 'quarta', 'qua': 'quarta', '3': 'quarta',
        'quinta': 'quinta', 'qui': 'quinta', '4': 'quinta',
        'sexta': 'sexta', 'sex': 'sexta', '5': 'sexta',
        'sabado': 'sabado', 'sab': 'sabado', '6': 'sabado',
        'domingo': 'domingo', 'dom': 'domingo', '0': 'domingo'
    }
    resultado = []
    for d in dias:
        chave = str(d).strip().lower()
        if chave in nomes:
            resultado.append(nomes[chave])
    return resultado

def gerar_contas_despesa_recorrente(item_despesa_id, meses_futuros=12, mes_referencia=None):
    """Gera contas reais para despesas recorrentes (mensal, anual, semanal, a_cada_2_semanas ou dias_semana)."""
    item = ItemDespesa.query.get(item_despesa_id)
    if not item:
        raise ValueError('ItemDespesa nao encontrado')
    if not item.recorrente:
        raise ValueError('ItemDespesa nao e recorrente')
    if not item.data_vencimento:
        raise ValueError('ItemDespesa recorrente precisa ter data_vencimento')

    tipo_recorrencia = item.tipo_recorrencia or 'mensal'
    data_inicio = item.data_vencimento
    inicio_geracao = data_inicio.replace(day=1)
    mes_ref_base = mes_referencia.replace(day=1) if mes_referencia else None
    inicio_janela = max(inicio_geracao, mes_ref_base) if mes_ref_base else inicio_geracao
    data_fim_base = (inicio_janela + relativedelta(months=meses_futuros)) - timedelta(days=1)

    contas_criadas = []

    def criar_conta(data_venc, descricao_custom=None):
        mes_ref = data_venc.replace(day=1)
        existente = Conta.query.filter_by(
            item_despesa_id=item_despesa_id,
            data_vencimento=data_venc
        ).first()
        if existente:
            return
        nova = Conta(
            item_despesa_id=item_despesa_id,
            mes_referencia=mes_ref,
            descricao=descricao_custom or item.nome,
            valor=item.valor,
            data_vencimento=data_venc,
            status_pagamento='Pendente',
            observacoes=item.descricao or ''
        )
        db.session.add(nova)
        contas_criadas.append(nova)

    if tipo_recorrencia == 'mensal':
        data_venc = data_inicio
        while data_venc < inicio_janela:
            data_venc += relativedelta(months=1)
        while data_venc <= data_fim_base:
            criar_conta(data_venc)
            data_venc += relativedelta(months=1)

    elif tipo_recorrencia == 'anual':
        data_ref = data_inicio
        while data_ref < inicio_janela:
            data_ref += relativedelta(years=1)
        while data_ref <= data_fim_base:
            criar_conta(data_ref)
            data_ref += relativedelta(years=1)

    elif tipo_recorrencia == 'semanal' or tipo_recorrencia.startswith('semanal_') or tipo_recorrencia == 'a_cada_2_semanas':
        intervalo = 1 if tipo_recorrencia == "semanal" else 2
        dia_semana_alvo = None
        if tipo_recorrencia.startswith("semanal_"):
            partes = tipo_recorrencia.split("_")
            if len(partes) > 1:
                try:
                    intervalo = int(partes[1])
                except Exception:
                    intervalo = max(intervalo, 1)
            if len(partes) > 2:
                try:
                    dia_semana_alvo = int(partes[2])
                except Exception:
                    dia_semana_alvo = None

        data_atual = max(data_inicio, inicio_janela)
        if dia_semana_alvo is not None:
            dias_ate_alvo = (dia_semana_alvo - data_atual.weekday()) % 7
            data_atual += timedelta(days=dias_ate_alvo)

        while data_atual <= data_fim_base:
            if data_atual >= inicio_geracao:
                criar_conta(data_atual, descricao_custom=f"{item.nome} - {data_atual.strftime('%d/%m')}")
            data_atual += timedelta(weeks=intervalo)

    elif tipo_recorrencia == 'dias_semana':
        dias_lista = normalizar_dias_semana(getattr(item, 'dias_semana', None))
        frequencia = getattr(item, 'frequencia_semanal', '') or 'toda_semana'
        mapa_num = {
            'segunda': 0, 'terca': 1, 'quarta': 2, 'quinta': 3, 'sexta': 4, 'sabado': 5, 'domingo': 6
        }
        dias_alvo = [mapa_num[d] for d in dias_lista if d in mapa_num]
        data_atual = inicio_janela
        while data_atual <= data_fim_base:
            if dias_alvo and data_atual.weekday() in dias_alvo:
                if frequencia == 'alternado' and data_atual.isocalendar()[1] % 2 != 0:
                    data_atual += timedelta(days=1)
                    continue
                criar_conta(data_atual, descricao_custom=f"{item.nome} - {data_atual.strftime('%d/%m')}")
            data_atual += timedelta(days=1)

    return contas_criadas


def gerar_lancamentos_cartao_recorrente(item_despesa_id, meses_futuros=12, mes_referencia=None):
    """
    Gera lançamentos automaticamente para despesas recorrentes pagas via cartão de crédito.
    
    Diferença da geração de Conta:
    - Gera LancamentoAgregado ao invés de Conta
    - Aparece na fatura do cartão
    - Classificado como "Despesas Fixas"
    
    Garante idempotência: 1 recorrência = 1 lançamento/mês
    """
    from datetime import date

    item = ItemDespesa.query.get(item_despesa_id)
    if not item:
        raise ValueError('ItemDespesa não encontrado')
    if not item.recorrente:
        raise ValueError('ItemDespesa não é recorrente')
    if item.meio_pagamento != 'cartao':
        raise ValueError('ItemDespesa não é pago via cartão')
    if not item.cartao_id:
        raise ValueError('ItemDespesa recorrente pago via cartão precisa ter cartao_id')
    if not item.categoria_id:
        raise ValueError('ItemDespesa recorrente precisa ter categoria_id')

    tipo_recorrencia = item.tipo_recorrencia or 'mensal'

    # Fallback obrigatório para conseguir inferir mes_fatura quando não há data_vencimento/mes_competencia
    if item.data_vencimento:
        data_base = item.data_vencimento
    elif item.mes_competencia:
        if isinstance(item.mes_competencia, str):
            # Aceitar "YYYY-MM" ou "YYYY-MM-DD"
            try:
                data_base = datetime.strptime(item.mes_competencia + '-01', '%Y-%m-%d').date()
            except ValueError:
                data_base = datetime.strptime(item.mes_competencia, '%Y-%m-%d').date()
        else:
            data_base = item.mes_competencia
    else:
        data_base = date.today()

    data_inicio = data_base
    inicio_geracao = data_inicio.replace(day=1)
    mes_ref_base = mes_referencia.replace(day=1) if mes_referencia else None
    inicio_janela = max(inicio_geracao, mes_ref_base) if mes_ref_base else inicio_geracao
    data_fim_base = (inicio_janela + relativedelta(months=meses_futuros)) - timedelta(days=1)
    
    lancamentos_criados = []
    
    def criar_lancamento(data_compra):
        """Cria LancamentoAgregado se ainda não existe para esta competência"""
        mes_fatura = data_compra.replace(day=1)
        
        # Verificar se já existe lançamento deste item_despesa para este mês (idempotência)
        existente = LancamentoAgregado.query.filter_by(
            item_despesa_id=item_despesa_id,
            mes_fatura=mes_fatura,
            is_recorrente=True
        ).first()
        
        if existente:
            return  # Já existe, não cria duplicado
        
        novo = LancamentoAgregado(
            cartao_id=item.cartao_id,
            item_agregado_id=item.item_agregado_id,  # Opcional - categoria do cartão
            categoria_id=item.categoria_id,  # Categoria analítica obrigatória
            descricao=item.nome,
            valor=item.valor,
            data_compra=data_compra,
            mes_fatura=mes_fatura,
            numero_parcela=1,
            total_parcelas=1,
            observacoes=item.descricao or '',
            is_recorrente=True,  # Marca como recorrente para aparecer em "Despesas Fixas"
            item_despesa_id=item_despesa_id  # Referência à despesa recorrente
        )
        db.session.add(novo)
        lancamentos_criados.append(novo)
    
    # Gerar lançamentos conforme tipo de recorrência (apenas mensal por enquanto)
    if tipo_recorrencia == 'mensal':
        data_ref = data_inicio
        while data_ref < inicio_janela:
            data_ref += relativedelta(months=1)
        while data_ref <= data_fim_base:
            criar_lancamento(data_ref)
            data_ref += relativedelta(months=1)
    
    elif tipo_recorrencia == 'anual':
        data_ref = data_inicio
        while data_ref < inicio_janela:
            data_ref += relativedelta(years=1)
        while data_ref <= data_fim_base:
            criar_lancamento(data_ref)
            data_ref += relativedelta(years=1)
    
    return lancamentos_criados
