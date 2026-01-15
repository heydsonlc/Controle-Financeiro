"""
Rotas da API para gerenciamento de Receitas

Endpoints organizados em 4 grupos:
1. Fontes de Receita (ItemReceita)
2. Orçamento de Receitas
3. Receitas Realizadas
4. Relatórios e Análises
"""
from flask import Blueprint, request, jsonify
from datetime import datetime

try:
    from backend.models import db, ItemReceita, ReceitaOrcamento, ReceitaRealizada, ContratoConsorcio
    from backend.services.receita_service import ReceitaService
except ImportError:
    from models import db, ItemReceita, ReceitaOrcamento, ReceitaRealizada, ContratoConsorcio
    from services.receita_service import ReceitaService

# Criar blueprint
receitas_bp = Blueprint('receitas', __name__)


def _backfill_receitas_contemplacao_consorcios(ano: int | None = None) -> None:
    """
    Backfill idempotente para consórcios antigos (já cadastrados antes da automação),
    garantindo que contemplações gerem ReceitaRealizada e apareçam no módulo de receitas.
    """
    query = ContratoConsorcio.query.filter(ContratoConsorcio.ativo == True)
    if ano:
        ini = datetime.strptime(f'{ano}-01-01', '%Y-%m-%d').date()
        fim = datetime.strptime(f'{ano}-12-31', '%Y-%m-%d').date()
        query = query.filter(
            ContratoConsorcio.mes_contemplacao.isnot(None),
            ContratoConsorcio.mes_contemplacao >= ini,
            ContratoConsorcio.mes_contemplacao <= fim,
        )

    consorcios = query.all()
    if not consorcios:
        return

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

    alterou = False

    for consorcio in consorcios:
        if not consorcio.mes_contemplacao or not consorcio.valor_premio:
            continue

        competencia = consorcio.mes_contemplacao.replace(day=1)
        marcador = f"consorcio_id={consorcio.id}"

        existente = ReceitaRealizada.query.filter(
            ReceitaRealizada.item_receita_id == item_padrao.id,
            ReceitaRealizada.mes_referencia == competencia,
            ReceitaRealizada.observacoes.ilike(f"%{marcador}%"),
        ).first()

        descricao = f"Consórcio {consorcio.nome} - contemplação (ID {consorcio.id})"

        if existente:
            # Atualizar para refletir possíveis mudanças no contrato
            existente.data_recebimento = consorcio.mes_contemplacao
            existente.valor_recebido = consorcio.valor_premio
            existente.mes_referencia = competencia
            existente.descricao = descricao
            if not existente.observacoes:
                existente.observacoes = marcador
            elif marcador not in existente.observacoes:
                existente.observacoes = f"{existente.observacoes}\n{marcador}".strip()
            alterou = True
            continue

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
        alterou = True

    if alterou:
        db.session.commit()


# ============================================================================
# 1. FONTES DE RECEITA (ItemReceita)
# ============================================================================

@receitas_bp.route('/itens', methods=['GET'])
def listar_itens():
    """
    Lista todas as fontes de receita

    Query params:
        tipo: Filtrar por tipo (SALARIO_FIXO, GRATIFICACAO, etc.)
        ativo: true/false - Filtrar por status ativo

    Returns:
        JSON com lista de fontes
    """
    try:
        # Backfill idempotente para garantir que contemplações antigas apareçam
        _backfill_receitas_contemplacao_consorcios()

        tipo = request.args.get('tipo')
        ativo = request.args.get('ativo')

        if ativo is not None:
            ativo = ativo.lower() == 'true'

        itens = ReceitaService.listar_itens_receita(tipo=tipo, ativo=ativo)

        return jsonify({
            'success': True,
            'data': [item.to_dict() for item in itens],
            'total': len(itens)
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@receitas_bp.route('/itens/<int:id>', methods=['GET'])
def buscar_item(id):
    """
    Busca uma fonte de receita específica por ID

    Args:
        id: ID do item

    Returns:
        JSON com dados do item
    """
    try:
        item = ItemReceita.query.get(id)

        if not item:
            return jsonify({
                'success': False,
                'error': 'Fonte de receita não encontrada'
            }), 404

        return jsonify({
            'success': True,
            'data': item.to_dict()
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@receitas_bp.route('/itens', methods=['POST'])
def criar_item():
    """
    Cria uma nova fonte de receita

    Body (JSON):
        {
            "nome": "string" (obrigatório),
            "tipo": "SALARIO_FIXO|GRATIFICACAO|RENDA_EXTRA|..." (obrigatório),
            "descricao": "string" (opcional),
            "valor_base_mensal": float (opcional),
            "dia_previsto_pagamento": int (opcional),
            "conta_origem_id": int (opcional),
            "ativo": boolean (opcional, padrão: true)
        }

    Returns:
        JSON com o item criado
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': 'Dados não fornecidos'
            }), 400

        item = ReceitaService.criar_item_receita(data)

        # Se for receita recorrente, gerar orçamentos automaticamente
        if item.recorrente and item.valor_base_mensal and item.valor_base_mensal > 0:
            try:
                from datetime import date
                from dateutil.relativedelta import relativedelta

                # Gerar orçamentos para os próximos 12 meses
                hoje = date.today()
                mes_referencia = date(hoje.year, hoje.month, 1)
                orcamentos_criados = 0

                for i in range(12):
                    # Verificar se já existe
                    orcamento_existente = ReceitaOrcamento.query.filter(
                        ReceitaOrcamento.item_receita_id == item.id,
                        ReceitaOrcamento.mes_referencia == mes_referencia
                    ).first()

                    if not orcamento_existente:
                        novo_orcamento = ReceitaOrcamento(
                            item_receita_id=item.id,
                            mes_referencia=mes_referencia,
                            valor_esperado=item.valor_base_mensal,
                            periodicidade='MENSAL_FIXA',
                            observacoes=f'Gerado automaticamente - {item.nome}'
                        )
                        db.session.add(novo_orcamento)
                        orcamentos_criados += 1

                    mes_referencia = mes_referencia + relativedelta(months=1)

                db.session.commit()
            except Exception as e:
                # Se falhar a geração de orçamentos, não falha a criação do item
                print(f'Aviso: Erro ao gerar orçamentos automáticos: {e}')

        return jsonify({
            'success': True,
            'message': 'Fonte de receita criada com sucesso',
            'data': item.to_dict()
        }), 201

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@receitas_bp.route('/itens/<int:id>', methods=['PUT'])
def atualizar_item(id):
    """
    Atualiza uma fonte de receita existente

    Args:
        id: ID do item

    Body (JSON): Campos que deseja atualizar

    Returns:
        JSON com o item atualizado
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': 'Dados não fornecidos'
            }), 400

        item = ReceitaService.atualizar_item_receita(id, data)

        # Se tornou recorrente ou valor base foi atualizado, gerar orçamentos
        if item.recorrente and item.valor_base_mensal and item.valor_base_mensal > 0:
            try:
                from datetime import date
                from dateutil.relativedelta import relativedelta

                # Gerar orçamentos para os próximos 12 meses
                hoje = date.today()
                mes_referencia = date(hoje.year, hoje.month, 1)
                orcamentos_criados = 0

                for i in range(12):
                    # Verificar se já existe
                    orcamento_existente = ReceitaOrcamento.query.filter(
                        ReceitaOrcamento.item_receita_id == item.id,
                        ReceitaOrcamento.mes_referencia == mes_referencia
                    ).first()

                    if not orcamento_existente:
                        novo_orcamento = ReceitaOrcamento(
                            item_receita_id=item.id,
                            mes_referencia=mes_referencia,
                            valor_esperado=item.valor_base_mensal,
                            periodicidade='MENSAL_FIXA',
                            observacoes=f'Gerado automaticamente - {item.nome}'
                        )
                        db.session.add(novo_orcamento)
                        orcamentos_criados += 1

                    mes_referencia = mes_referencia + relativedelta(months=1)

                db.session.commit()
            except Exception as e:
                # Se falhar a geração de orçamentos, não falha a atualização do item
                print(f'Aviso: Erro ao gerar orçamentos automáticos: {e}')

        return jsonify({
            'success': True,
            'message': 'Fonte de receita atualizada com sucesso',
            'data': item.to_dict()
        }), 200

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@receitas_bp.route('/itens/<int:id>', methods=['DELETE'])
def deletar_item(id):
    """
    Inativa (soft delete) uma fonte de receita

    Args:
        id: ID do item

    Returns:
        JSON com confirmação
    """
    try:
        item = ReceitaService.inativar_item_receita(id)

        return jsonify({
            'success': True,
            'message': 'Fonte de receita inativada com sucesso',
            'data': item.to_dict()
        }), 200

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 404

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================================================
# 2. ORÇAMENTO DE RECEITAS
# ============================================================================

@receitas_bp.route('/orcamento', methods=['GET'])
def listar_orcamentos():
    """
    Lista orçamentos de receitas

    Query params:
        ano: Ano para filtrar (ex: 2025)

    Returns:
        JSON com lista de orçamentos
    """
    try:
        ano = request.args.get('ano', type=int)

        if not ano:
            return jsonify({
                'success': False,
                'error': 'Parâmetro ano é obrigatório'
            }), 400

        orcamentos = ReceitaService.obter_orcamentos_por_ano(ano)

        return jsonify({
            'success': True,
            'data': [orc.to_dict() for orc in orcamentos],
            'total': len(orcamentos)
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@receitas_bp.route('/orcamento', methods=['POST'])
def criar_orcamento():
    """
    Cria ou atualiza um orçamento mensal específico

    Body (JSON):
        {
            "item_receita_id": int (obrigatório),
            "ano_mes": "YYYY-MM-01" (obrigatório),
            "valor_previsto": float (obrigatório),
            "periodicidade": "MENSAL_FIXA|EVENTUAL|UNICA" (opcional),
            "observacoes": "string" (opcional)
        }

    Returns:
        JSON com o orçamento criado
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': 'Dados não fornecidos'
            }), 400

        # Validações
        if not data.get('item_receita_id'):
            return jsonify({
                'success': False,
                'error': 'item_receita_id é obrigatório'
            }), 400

        if not data.get('ano_mes'):
            return jsonify({
                'success': False,
                'error': 'ano_mes é obrigatório'
            }), 400

        if data.get('valor_previsto') is None:
            return jsonify({
                'success': False,
                'error': 'valor_previsto é obrigatório'
            }), 400

        orcamento = ReceitaService.criar_ou_atualizar_orcamento_mensal(
            item_receita_id=data['item_receita_id'],
            ano_mes=data['ano_mes'],
            valor_previsto=data['valor_previsto'],
            periodicidade=data.get('periodicidade', 'MENSAL_FIXA'),
            observacoes=data.get('observacoes')
        )

        return jsonify({
            'success': True,
            'message': 'Orçamento criado/atualizado com sucesso',
            'data': orcamento.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@receitas_bp.route('/orcamento/gerar-recorrente', methods=['POST'])
def gerar_orcamento_recorrente():
    """
    Gera orçamentos recorrentes automaticamente para um período
    Útil para salários e gratificações fixas

    Body (JSON):
        {
            "item_receita_id": int (obrigatório),
            "data_inicio": "YYYY-MM-01" (obrigatório),
            "data_fim": "YYYY-MM-01" (obrigatório),
            "valor_mensal": float (obrigatório),
            "periodicidade": "MENSAL_FIXA" (opcional, padrão: MENSAL_FIXA)
        }

    Returns:
        JSON com os orçamentos criados
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': 'Dados não fornecidos'
            }), 400

        # Validações
        campos_obrigatorios = ['item_receita_id', 'data_inicio', 'data_fim', 'valor_mensal']
        for campo in campos_obrigatorios:
            if not data.get(campo):
                return jsonify({
                    'success': False,
                    'error': f'{campo} é obrigatório'
                }), 400

        orcamentos = ReceitaService.gerar_orcamento_recorrente(
            item_receita_id=data['item_receita_id'],
            data_inicio=data['data_inicio'],
            data_fim=data['data_fim'],
            valor_mensal=data['valor_mensal'],
            periodicidade=data.get('periodicidade', 'MENSAL_FIXA')
        )

        return jsonify({
            'success': True,
            'message': f'{len(orcamentos)} orçamentos gerados com sucesso',
            'data': [orc.to_dict() for orc in orcamentos],
            'total': len(orcamentos)
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================================================
# 3. RECEITAS REALIZADAS
# ============================================================================

@receitas_bp.route('/realizadas', methods=['GET'])
def listar_realizadas():
    """
    Lista receitas realizadas

    Query params:
        ano_mes: Filtrar por competência (YYYY-MM)
        item_receita_id: Filtrar por fonte

    Returns:
        JSON com lista de receitas
    """
    try:
        ano_mes = request.args.get('ano_mes')
        item_receita_id = request.args.get('item_receita_id', type=int)

        receitas = ReceitaService.listar_receitas_realizadas(
            ano_mes=ano_mes,
            item_receita_id=item_receita_id
        )

        return jsonify({
            'success': True,
            'data': [rec.to_dict() for rec in receitas],
            'total': len(receitas)
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@receitas_bp.route('/realizadas/<int:id>', methods=['GET'])
def buscar_realizada(id):
    """
    Busca uma receita realizada específica

    Args:
        id: ID da receita

    Returns:
        JSON com dados da receita
    """
    try:
        receita = ReceitaRealizada.query.get(id)

        if not receita:
            return jsonify({
                'success': False,
                'error': 'Receita não encontrada'
            }), 404

        return jsonify({
            'success': True,
            'data': receita.to_dict()
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@receitas_bp.route('/realizadas/<int:id>', methods=['PUT'])
def atualizar_realizada(id):
    """
    Atualiza uma receita realizada.

    Body (JSON): mesmos campos do POST /realizadas
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': 'Dados não fornecidos'
            }), 400

        receita = ReceitaService.atualizar_receita_realizada(id, data)
        if not receita:
            return jsonify({
                'success': False,
                'error': 'Receita não encontrada'
            }), 404

        return jsonify({
            'success': True,
            'message': 'Receita atualizada com sucesso',
            'data': receita.to_dict()
        }), 200

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@receitas_bp.route('/realizadas', methods=['POST'])
def criar_realizada():
    """
    Registra uma receita efetivamente recebida

    Body (JSON):
        {
            "item_receita_id": int (obrigatório),
            "data_recebimento": "YYYY-MM-DD" (obrigatório),
            "valor_recebido": float (obrigatório),
            "competencia": "YYYY-MM-01" (opcional, usa mês do recebimento se não informado),
            "descricao": "string" (opcional),
            "conta_origem_id": int (opcional),
            "observacoes": "string" (opcional)
        }

    Returns:
        JSON com a receita registrada
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': 'Dados não fornecidos'
            }), 400

        receita = ReceitaService.registrar_receita_realizada(data)

        return jsonify({
            'success': True,
            'message': 'Receita registrada com sucesso',
            'data': receita.to_dict()
        }), 201

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@receitas_bp.route('/realizadas/pontual', methods=['POST'])
def criar_receita_pontual():
    """
    Registra uma receita pontual/eventual (sem vínculo com orçamento)
    Útil para registrar entradas ocasionais como PIX recebido, venda de item, etc.

    Body (JSON):
        {
            "conta_bancaria_id": int (obrigatório),
            "descricao": "string" (obrigatório),
            "valor_recebido": float (obrigatório),
            "data_recebimento": "YYYY-MM-DD" (obrigatório),
            "competencia": "YYYY-MM-01" (obrigatório),
            "observacoes": "string" (opcional),
            "tipo_entrada": "string" (opcional, ex: RECEITA_PONTUAL)
        }

    Returns:
        JSON com a receita registrada
    """
    from decimal import Decimal

    try:
        from backend.models import ContaBancaria
    except ImportError:
        from models import ContaBancaria

    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': 'Dados não fornecidos'
            }), 400

        # Validações
        campos_obrigatorios = ['conta_bancaria_id', 'descricao', 'valor_recebido',
                               'data_recebimento', 'competencia']
        for campo in campos_obrigatorios:
            if not data.get(campo):
                return jsonify({
                    'success': False,
                    'error': f'{campo} é obrigatório'
                }), 400

        # Verificar se a conta bancária existe
        conta = ContaBancaria.query.get(data['conta_bancaria_id'])
        if not conta:
            return jsonify({
                'success': False,
                'error': 'Conta bancária não encontrada'
            }), 404

        # Converter valor para Decimal
        valor_recebido = Decimal(str(data['valor_recebido']))

        # Criar receita realizada sem item_receita_id e orcamento_id
        receita = ReceitaRealizada(
            item_receita_id=None,  # Receita pontual não tem fonte fixa
            orcamento_id=None,     # Não vinculada a orçamento
            conta_origem_id=data['conta_bancaria_id'],  # Usar conta_origem_id
            data_recebimento=datetime.strptime(data['data_recebimento'], '%Y-%m-%d').date(),
            valor_recebido=valor_recebido,
            mes_referencia=datetime.strptime(data['competencia'], '%Y-%m-%d').date(),  # Usar mes_referencia
            descricao=data['descricao'],
            observacoes=data.get('observacoes', '')
        )

        # Atualizar saldo da conta bancária (usando Decimal)
        conta.saldo_atual = (conta.saldo_atual or Decimal('0')) + valor_recebido

        db.session.add(receita)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Receita pontual registrada com sucesso',
            'data': receita.to_dict()
        }), 201

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@receitas_bp.route('/realizadas/<int:id>', methods=['DELETE'])
def deletar_realizada(id):
    """
    Deleta uma receita realizada

    Args:
        id: ID da receita

    Returns:
        JSON com confirmação
    """
    from decimal import Decimal

    try:
        from backend.models import ContaBancaria
    except ImportError:
        from models import ContaBancaria

    try:
        receita = ReceitaRealizada.query.get(id)

        if not receita:
            return jsonify({
                'success': False,
                'error': 'Receita não encontrada'
            }), 404

        # Se for receita pontual, reverter o saldo da conta
        if receita.conta_origem_id and not receita.orcamento_id:
            conta = ContaBancaria.query.get(receita.conta_origem_id)
            if conta:
                conta.saldo_atual = (conta.saldo_atual or Decimal('0')) - receita.valor_recebido

        db.session.delete(receita)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Receita deletada com sucesso'
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================================================
# 4. RELATÓRIOS E ANÁLISES
# ============================================================================

@receitas_bp.route('/resumo-mensal', methods=['GET'])
def resumo_mensal():
    """
    Resumo consolidado de receitas por mês
    Compara previsto vs realizado

    Query params:
        ano: Ano (obrigatório)

    Returns:
        JSON com resumo por mês e por tipo
    """
    try:
        ano = request.args.get('ano', type=int)

        if not ano:
            return jsonify({
                'success': False,
                'error': 'Parâmetro ano é obrigatório'
            }), 400

        # Backfill idempotente para garantir que contemplações do ano apareçam no resumo
        _backfill_receitas_contemplacao_consorcios(ano=ano)

        resumo = ReceitaService.get_resumo_receitas_por_mes(ano)

        return jsonify({
            'success': True,
            'data': resumo
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@receitas_bp.route('/confiabilidade', methods=['GET'])
def confiabilidade():
    """
    Calcula confiabilidade das receitas
    % recebido / previsto por fonte e consolidado

    Query params:
        ano_mes_ini: Início do período (YYYY-MM-01)
        ano_mes_fim: Fim do período (YYYY-MM-01)

    Returns:
        JSON com percentuais de confiabilidade
    """
    try:
        ano_mes_ini = request.args.get('ano_mes_ini')
        ano_mes_fim = request.args.get('ano_mes_fim')

        if not ano_mes_ini or not ano_mes_fim:
            return jsonify({
                'success': False,
                'error': 'Parâmetros ano_mes_ini e ano_mes_fim são obrigatórios'
            }), 400

        confiabilidade = ReceitaService.get_confiabilidade_receitas(
            ano_mes_ini=ano_mes_ini,
            ano_mes_fim=ano_mes_fim
        )

        return jsonify({
            'success': True,
            'data': confiabilidade
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@receitas_bp.route('/itens/<int:item_id>/detalhe', methods=['GET'])
def detalhe_item(item_id):
    """
    Detalhe completo de uma fonte de receita
    Mostra todas as projeções e realizações mês a mês

    Args:
        item_id: ID do item

    Query params:
        ano: Ano (obrigatório)

    Returns:
        JSON com detalhe mês a mês
    """
    try:
        ano = request.args.get('ano', type=int)

        if not ano:
            return jsonify({
                'success': False,
                'error': 'Parâmetro ano é obrigatório'
            }), 400

        detalhe = ReceitaService.get_detalhe_receitas_item(item_id, ano)

        return jsonify({
            'success': True,
            'data': detalhe
        }), 200

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 404

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
