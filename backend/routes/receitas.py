"""
Rotas da API para gerenciamento de Receitas

Endpoints organizados em 4 grupos:
1. Fontes de Receita (ItemReceita)
2. OrÃ§amento de Receitas
3. Receitas Realizadas
4. RelatÃ³rios e AnÃ¡lises
"""
from flask import Blueprint, request, jsonify
from datetime import datetime
import logging
from decimal import Decimal

try:
    from backend.models import db, ItemReceita, ReceitaOrcamento, ReceitaRealizada, ContratoConsorcio
    from backend.services.receita_service import ReceitaService
    from backend.services.consorcio_receita_service import gerar_ou_atualizar_receita_contemplacao
    from backend.services.perfil_financeiro_service import PerfilFinanceiroService
except ImportError:
    from models import db, ItemReceita, ReceitaOrcamento, ReceitaRealizada, ContratoConsorcio
    from services.receita_service import ReceitaService
    from services.consorcio_receita_service import gerar_ou_atualizar_receita_contemplacao
    from services.perfil_financeiro_service import PerfilFinanceiroService

# Criar blueprint
receitas_bp = Blueprint('receitas', __name__)
logger = logging.getLogger(__name__)


def _perfil_id():
    return PerfilFinanceiroService.obter_perfil_ativo_id()


def _internal_error(contexto='receitas'):
    logger.exception('Erro interno em %s', contexto)
    return jsonify({'success': False, 'error': 'Erro interno ao processar requisicao'}), 500


def _backfill_receitas_contemplacao_consorcios(ano: int | None = None) -> None:
    """
    Backfill idempotente para consorcios ativos com contemplacao.
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

    alterou = False

    for consorcio in consorcios:
        if not consorcio.mes_contemplacao or not consorcio.valor_premio:
            continue
        receita = gerar_ou_atualizar_receita_contemplacao(consorcio)
        if receita:
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
        # Backfill idempotente para garantir que contemplaÃ§Ãµes antigas apareÃ§am
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

    except Exception:
        return _internal_error('receitas')
@receitas_bp.route('/itens/<int:id>', methods=['GET'])
def buscar_item(id):
    """
    Busca uma fonte de receita especÃ­fica por ID

    Args:
        id: ID do item

    Returns:
        JSON com dados do item
    """
    try:
        item = ItemReceita.query.filter(
            ItemReceita.id == id,
            PerfilFinanceiroService.condicao_perfil(ItemReceita),
        ).first()

        if not item:
            return jsonify({
                'success': False,
                'error': 'Fonte de receita nÃ£o encontrada'
            }), 404

        return jsonify({
            'success': True,
            'data': item.to_dict()
        }), 200

    except Exception:
        return _internal_error('receitas')

@receitas_bp.route('/itens', methods=['POST'])
def criar_item():
    """
    Cria uma nova fonte de receita

    Body (JSON):
        {
            "nome": "string" (obrigatÃ³rio),
            "tipo": "SALARIO_FIXO|GRATIFICACAO|RENDA_EXTRA|..." (obrigatÃ³rio),
            "descricao": "string" (opcional),
            "valor_base_mensal": float (opcional),
            "dia_previsto_pagamento": int (opcional),
            "conta_origem_id": int (opcional),
            "ativo": boolean (opcional, padrÃ£o: true)
        }

    Returns:
        JSON com o item criado
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': 'Dados nÃ£o fornecidos'
            }), 400

        item = ReceitaService.criar_item_receita(data)

        # Se for receita recorrente, gerar orÃ§amentos automaticamente
        if item.recorrente and item.valor_base_mensal and item.valor_base_mensal > 0:
            try:
                from datetime import date
                from dateutil.relativedelta import relativedelta

                # Gerar orÃ§amentos para os prÃ³ximos 12 meses
                hoje = date.today()
                mes_referencia = date(hoje.year, hoje.month, 1)
                orcamentos_criados = 0

                for i in range(12):
                    # Verificar se jÃ¡ existe
                    orcamento_existente = ReceitaOrcamento.query.filter(
                        PerfilFinanceiroService.condicao_perfil(ReceitaOrcamento),
                        ReceitaOrcamento.item_receita_id == item.id,
                        ReceitaOrcamento.mes_referencia == mes_referencia
                    ).first()

                    if not orcamento_existente:
                        novo_orcamento = ReceitaOrcamento(
                            perfil_financeiro_id=_perfil_id(),
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
            except Exception:
                # Se falhar a geraÃ§Ã£o de orÃ§amentos, nÃ£o falha a criaÃ§Ã£o do item
                logger.warning('Falha ao gerar orcamentos automaticos na criacao de item de receita', exc_info=True)

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

    except Exception:
        db.session.rollback()
        return _internal_error('receitas')


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
                'error': 'Dados nÃ£o fornecidos'
            }), 400

        item = ReceitaService.atualizar_item_receita(id, data)

        # Se tornou recorrente ou valor base foi atualizado, gerar orÃ§amentos
        if item.recorrente and item.valor_base_mensal and item.valor_base_mensal > 0:
            try:
                from datetime import date
                from dateutil.relativedelta import relativedelta

                # Gerar orÃ§amentos para os prÃ³ximos 12 meses
                hoje = date.today()
                mes_referencia = date(hoje.year, hoje.month, 1)
                orcamentos_criados = 0

                for i in range(12):
                    # Verificar se jÃ¡ existe
                    orcamento_existente = ReceitaOrcamento.query.filter(
                        PerfilFinanceiroService.condicao_perfil(ReceitaOrcamento),
                        ReceitaOrcamento.item_receita_id == item.id,
                        ReceitaOrcamento.mes_referencia == mes_referencia
                    ).first()

                    if not orcamento_existente:
                        novo_orcamento = ReceitaOrcamento(
                            perfil_financeiro_id=_perfil_id(),
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
            except Exception:
                # Se falhar a geraÃ§Ã£o de orÃ§amentos, nÃ£o falha a atualizaÃ§Ã£o do item
                logger.warning('Falha ao gerar orcamentos automaticos na atualizacao de item de receita', exc_info=True)

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

    except Exception:
        db.session.rollback()
        return _internal_error('receitas')


@receitas_bp.route('/itens/<int:id>', methods=['DELETE'])
def deletar_item(id):
    """
    Inativa (soft delete) uma fonte de receita

    Args:
        id: ID do item

    Returns:
        JSON com confirmaÃ§Ã£o
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

    except Exception:
        db.session.rollback()
        return _internal_error('receitas')


# ============================================================================
# 2. ORÃ‡AMENTO DE RECEITAS
# ============================================================================

@receitas_bp.route('/orcamento', methods=['GET'])
def listar_orcamentos():
    """
    Lista orÃ§amentos de receitas

    Query params:
        ano: Ano para filtrar (ex: 2025)

    Returns:
        JSON com lista de orÃ§amentos
    """
    try:
        ano = request.args.get('ano', type=int)

        if not ano:
            return jsonify({
                'success': False,
                'error': 'ParÃ¢metro ano Ã© obrigatÃ³rio'
            }), 400

        orcamentos = ReceitaService.obter_orcamentos_por_ano(ano)

        return jsonify({
            'success': True,
            'data': [orc.to_dict() for orc in orcamentos],
            'total': len(orcamentos)
        }), 200

    except Exception:
        return _internal_error('receitas')


@receitas_bp.route('/orcamento', methods=['POST'])
def criar_orcamento():
    """
    Cria ou atualiza um orÃ§amento mensal especÃ­fico

    Body (JSON):
        {
            "item_receita_id": int (obrigatÃ³rio),
            "ano_mes": "YYYY-MM-01" (obrigatÃ³rio),
            "valor_previsto": float (obrigatÃ³rio),
            "periodicidade": "MENSAL_FIXA|EVENTUAL|UNICA" (opcional),
            "observacoes": "string" (opcional)
        }

    Returns:
        JSON com o orÃ§amento criado
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': 'Dados nÃ£o fornecidos'
            }), 400

        # ValidaÃ§Ãµes
        if not data.get('item_receita_id'):
            return jsonify({
                'success': False,
                'error': 'item_receita_id Ã© obrigatÃ³rio'
            }), 400

        if not data.get('ano_mes'):
            return jsonify({
                'success': False,
                'error': 'ano_mes Ã© obrigatÃ³rio'
            }), 400

        if data.get('valor_previsto') is None:
            return jsonify({
                'success': False,
                'error': 'valor_previsto Ã© obrigatÃ³rio'
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
            'message': 'OrÃ§amento criado/atualizado com sucesso',
            'data': orcamento.to_dict()
        }), 201

    except Exception:
        db.session.rollback()
        return _internal_error('receitas')


@receitas_bp.route('/orcamento/gerar-recorrente', methods=['POST'])
def gerar_orcamento_recorrente():
    """
    Gera orÃ§amentos recorrentes automaticamente para um perÃ­odo
    Ãštil para salÃ¡rios e gratificaÃ§Ãµes fixas

    Body (JSON):
        {
            "item_receita_id": int (obrigatÃ³rio),
            "data_inicio": "YYYY-MM-01" (obrigatÃ³rio),
            "data_fim": "YYYY-MM-01" (obrigatÃ³rio),
            "valor_mensal": float (obrigatÃ³rio),
            "periodicidade": "MENSAL_FIXA" (opcional, padrÃ£o: MENSAL_FIXA)
        }

    Returns:
        JSON com os orÃ§amentos criados
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': 'Dados nÃ£o fornecidos'
            }), 400

        # ValidaÃ§Ãµes
        campos_obrigatorios = ['item_receita_id', 'data_inicio', 'data_fim', 'valor_mensal']
        for campo in campos_obrigatorios:
            if not data.get(campo):
                return jsonify({
                    'success': False,
                    'error': f'{campo} Ã© obrigatÃ³rio'
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
            'message': f'{len(orcamentos)} orÃ§amentos gerados com sucesso',
            'data': [orc.to_dict() for orc in orcamentos],
            'total': len(orcamentos)
        }), 201

    except Exception:
        db.session.rollback()
        return _internal_error('receitas')


# ============================================================================
# 3. RECEITAS REALIZADAS
# ============================================================================

@receitas_bp.route('/realizadas', methods=['GET'])
def listar_realizadas():
    """
    Lista receitas realizadas

    Query params:
        ano_mes: Filtrar por competÃªncia (YYYY-MM)
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

    except Exception:
        return _internal_error('receitas')


@receitas_bp.route('/realizadas/<int:id>', methods=['GET'])
def buscar_realizada(id):
    """
    Busca uma receita realizada especÃ­fica

    Args:
        id: ID da receita

    Returns:
        JSON com dados da receita
    """
    try:
        receita = ReceitaRealizada.query.filter(
            ReceitaRealizada.id == id,
            PerfilFinanceiroService.condicao_perfil(ReceitaRealizada),
        ).first()

        if not receita:
            return jsonify({
                'success': False,
                'error': 'Receita nÃ£o encontrada'
            }), 404

        return jsonify({
            'success': True,
            'data': receita.to_dict()
        }), 200

    except Exception:
        return _internal_error('receitas')


@receitas_bp.route('/realizadas/<int:id>', methods=['PUT'])
def atualizar_realizada(id):
    """
    Atualiza uma receita realizada.

    Body (JSON): mesmos campos do POST /realizadas
    """
    try:
        receita_antes = ReceitaRealizada.query.filter(
            ReceitaRealizada.id == id,
            PerfilFinanceiroService.condicao_perfil(ReceitaRealizada),
        ).first()
        if not receita_antes:
            return jsonify({'success': False, 'error': 'Receita nÃ£o encontrada'}), 404

        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': 'Dados nÃ£o fornecidos'
            }), 400

        # Default de conta bancÃ¡ria: se nÃ£o veio no payload, tenta herdar da fonte
        if not data.get('conta_bancaria_id') and data.get('item_receita_id'):
            item = ItemReceita.query.filter(
                ItemReceita.id == data.get('item_receita_id'),
                PerfilFinanceiroService.condicao_perfil(ItemReceita),
            ).first()
            if item and item.conta_bancaria_id:
                data['conta_bancaria_id'] = item.conta_bancaria_id

        receita = ReceitaService.atualizar_receita_realizada(id, data)
        if not receita:
            return jsonify({
                'success': False,
                'error': 'Receita nÃ£o encontrada'
            }), 404

        # Sync do movimento financeiro (se houver conta_bancaria_id)
        try:
            from backend.services.conta_bancaria_service import ContaBancariaService
            from backend.models import MovimentoFinanceiro
        except ImportError:
            from services.conta_bancaria_service import ContaBancariaService
            from models import MovimentoFinanceiro

        mov = MovimentoFinanceiro.query.filter_by(
            receita_realizada_id=receita.id,
            origem='RECEITA',
            perfil_financeiro_id=_perfil_id(),
        ).first()
        contas_recalc = set()
        if receita_antes.conta_bancaria_id:
            contas_recalc.add(receita_antes.conta_bancaria_id)
        if receita.conta_bancaria_id:
            contas_recalc.add(receita.conta_bancaria_id)

        if receita.conta_bancaria_id:
            if mov:
                mov.conta_bancaria_id = receita.conta_bancaria_id
                mov.tipo = 'CREDITO'
                mov.valor = Decimal(str(receita.valor_recebido))
                mov.descricao = f'Receita - {receita.descricao or "Receita"}'
                mov.data_movimento = receita.data_recebimento
                mov.ajustavel = False
                mov.origem = 'RECEITA'
            else:
                ContaBancariaService.criar_movimento(
                    receita.conta_bancaria_id,
                    tipo='CREDITO',
                    valor=Decimal(str(receita.valor_recebido)),
                    descricao=f'Receita - {receita.descricao or "Receita"}',
                    data_movimento=receita.data_recebimento,
                    origem='RECEITA',
                    ajustavel=False,
                    receita_realizada_id=receita.id,
                )
        else:
            if mov:
                contas_recalc.add(mov.conta_bancaria_id)
                db.session.delete(mov)

        for cid in contas_recalc:
            ContaBancariaService.recalcular_saldo_conta(cid)
        db.session.commit()

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

    except Exception:
        db.session.rollback()
        return _internal_error('receitas')


@receitas_bp.route('/realizadas', methods=['POST'])
def criar_realizada():
    """
    Registra uma receita efetivamente recebida

    Body (JSON):
        {
            "item_receita_id": int (obrigatÃ³rio),
            "data_recebimento": "YYYY-MM-DD" (obrigatÃ³rio),
            "valor_recebido": float (obrigatÃ³rio),
            "competencia": "YYYY-MM-01" (opcional, usa mÃªs do recebimento se nÃ£o informado),
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
                'error': 'Dados nÃ£o fornecidos'
            }), 400

        # Default de conta bancÃ¡ria: se nÃ£o veio no payload, tenta herdar da fonte
        if not data.get('conta_bancaria_id') and data.get('item_receita_id'):
            try:
                from backend.models import ItemReceita
            except ImportError:
                from models import ItemReceita
            item = ItemReceita.query.filter(
                ItemReceita.id == data.get('item_receita_id'),
                PerfilFinanceiroService.condicao_perfil(ItemReceita),
            ).first()
            if item and item.conta_bancaria_id:
                data['conta_bancaria_id'] = item.conta_bancaria_id

        receita = ReceitaService.registrar_receita_realizada(data)

        # IntegraÃ§Ã£o com Contas BancÃ¡rias: crÃ©dito automÃ¡tico via MovimentoFinanceiro
        try:
            from backend.services.conta_bancaria_service import ContaBancariaService
            from backend.models import MovimentoFinanceiro
        except ImportError:
            from services.conta_bancaria_service import ContaBancariaService
            from models import MovimentoFinanceiro

        if receita.conta_bancaria_id:
            existe = MovimentoFinanceiro.query.filter_by(
                receita_realizada_id=receita.id,
                origem='RECEITA',
                perfil_financeiro_id=_perfil_id(),
            ).first()
            if not existe:
                ContaBancariaService.criar_movimento(
                    receita.conta_bancaria_id,
                    tipo='CREDITO',
                    valor=Decimal(str(receita.valor_recebido)),
                    descricao=f'Receita - {receita.descricao or "Receita"}',
                    data_movimento=receita.data_recebimento,
                    origem='RECEITA',
                    ajustavel=False,
                    receita_realizada_id=receita.id,
                )
                db.session.commit()

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

    except Exception:
        db.session.rollback()
        return _internal_error('receitas')


@receitas_bp.route('/realizadas/pontual', methods=['POST'])
def criar_receita_pontual():
    """
    Registra uma receita pontual/eventual (sem vÃ­nculo com orÃ§amento)
    Ãštil para registrar entradas ocasionais como PIX recebido, venda de item, etc.

    Body (JSON):
        {
            "conta_bancaria_id": int (obrigatÃ³rio),
            "descricao": "string" (obrigatÃ³rio),
            "valor_recebido": float (obrigatÃ³rio),
            "data_recebimento": "YYYY-MM-DD" (obrigatÃ³rio),
            "competencia": "YYYY-MM-01" (obrigatÃ³rio),
            "observacoes": "string" (opcional),
            "tipo_entrada": "string" (opcional, ex: RECEITA_PONTUAL)
        }

    Returns:
        JSON com a receita registrada
    """
    from decimal import Decimal

    try:
        from backend.models import ContaBancaria
        from backend.services.conta_bancaria_service import ContaBancariaService
    except ImportError:
        from models import ContaBancaria
        from services.conta_bancaria_service import ContaBancariaService

    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': 'Dados nÃ£o fornecidos'
            }), 400

        # ValidaÃ§Ãµes
        campos_obrigatorios = ['conta_bancaria_id', 'descricao', 'valor_recebido',
                               'data_recebimento', 'competencia']
        for campo in campos_obrigatorios:
            if not data.get(campo):
                return jsonify({
                    'success': False,
                    'error': f'{campo} Ã© obrigatÃ³rio'
                }), 400

        # Verificar se a conta bancÃ¡ria existe
        conta = ContaBancaria.query.filter(
            ContaBancaria.id == data['conta_bancaria_id'],
            PerfilFinanceiroService.condicao_perfil(ContaBancaria),
        ).first()
        if not conta:
            return jsonify({
                'success': False,
                'error': 'Conta bancÃ¡ria nÃ£o encontrada'
            }), 404

        # Converter valor para Decimal
        valor_recebido = Decimal(str(data['valor_recebido']))

        if conta.status != 'ATIVO':
            return jsonify({'success': False, 'error': 'Conta bancÃ¡ria estÃ¡ inativa'}), 400

        # Criar receita realizada sem item_receita_id e orcamento_id
        receita = ReceitaRealizada(
            perfil_financeiro_id=_perfil_id(),
            item_receita_id=None,  # Receita pontual nÃ£o tem fonte fixa
            orcamento_id=None,     # NÃ£o vinculada a orÃ§amento
            conta_bancaria_id=data['conta_bancaria_id'],
            data_recebimento=datetime.strptime(data['data_recebimento'], '%Y-%m-%d').date(),
            valor_recebido=valor_recebido,
            mes_referencia=datetime.strptime(data['competencia'], '%Y-%m-%d').date(),  # Usar mes_referencia
            descricao=data['descricao'],
            observacoes=data.get('observacoes', '')
        )
        db.session.add(receita)
        db.session.flush()

        # Movimento financeiro (crÃ©dito)
        ContaBancariaService.criar_movimento(
            conta_bancaria_id=conta.id,
            tipo='CREDITO',
            valor=valor_recebido,
            descricao=f'Receita pontual - {receita.descricao}',
            data_movimento=receita.data_recebimento,
            origem='RECEITA',
            ajustavel=False,
            receita_realizada_id=receita.id,
        )

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

    except Exception:
        db.session.rollback()
        return _internal_error('receitas')


@receitas_bp.route('/realizadas/<int:id>', methods=['DELETE'])
def deletar_realizada(id):
    """
    Deleta uma receita realizada

    Args:
        id: ID da receita

    Returns:
        JSON com confirmaÃ§Ã£o
    """
    try:
        from backend.services.conta_bancaria_service import ContaBancariaService
        from backend.models import MovimentoFinanceiro
    except ImportError:
        from services.conta_bancaria_service import ContaBancariaService
        from models import MovimentoFinanceiro

    try:
        receita = ReceitaRealizada.query.filter(
            ReceitaRealizada.id == id,
            PerfilFinanceiroService.condicao_perfil(ReceitaRealizada),
        ).first()

        if not receita:
            return jsonify({
                'success': False,
                'error': 'Receita nÃ£o encontrada'
            }), 404

        # Remover movimento financeiro vinculado (se existir) e recalcular saldo
        movimentos = MovimentoFinanceiro.query.filter_by(
            receita_realizada_id=receita.id,
            origem='RECEITA',
        ).filter(
            PerfilFinanceiroService.condicao_perfil(MovimentoFinanceiro),
        ).all()
        contas_para_recalcular = {m.conta_bancaria_id for m in movimentos}
        for m in movimentos:
            db.session.delete(m)

        db.session.delete(receita)
        for cid in contas_para_recalcular:
            ContaBancariaService.recalcular_saldo_conta(cid)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Receita deletada com sucesso'
        }), 200

    except Exception:
        db.session.rollback()
        return _internal_error('receitas')


# ============================================================================
# 4. RELATÃ“RIOS E ANÃLISES
# ============================================================================

@receitas_bp.route('/resumo-mensal', methods=['GET'])
def resumo_mensal():
    """
    Resumo consolidado de receitas por mÃªs
    Compara previsto vs realizado

    Query params:
        ano: Ano (obrigatÃ³rio)

    Returns:
        JSON com resumo por mÃªs e por tipo
    """
    try:
        ano = request.args.get('ano', type=int)

        if not ano:
            return jsonify({
                'success': False,
                'error': 'ParÃ¢metro ano Ã© obrigatÃ³rio'
            }), 400

        # Backfill idempotente para garantir que contemplaÃ§Ãµes do ano apareÃ§am no resumo
        _backfill_receitas_contemplacao_consorcios(ano=ano)

        resumo = ReceitaService.get_resumo_receitas_por_mes(ano)

        return jsonify({
            'success': True,
            'data': resumo
        }), 200

    except Exception:
        return _internal_error('receitas')


@receitas_bp.route('/confiabilidade', methods=['GET'])
def confiabilidade():
    """
    Calcula confiabilidade das receitas
    % recebido / previsto por fonte e consolidado

    Query params:
        ano_mes_ini: InÃ­cio do perÃ­odo (YYYY-MM-01)
        ano_mes_fim: Fim do perÃ­odo (YYYY-MM-01)

    Returns:
        JSON com percentuais de confiabilidade
    """
    try:
        ano_mes_ini = request.args.get('ano_mes_ini')
        ano_mes_fim = request.args.get('ano_mes_fim')

        if not ano_mes_ini or not ano_mes_fim:
            return jsonify({
                'success': False,
                'error': 'ParÃ¢metros ano_mes_ini e ano_mes_fim sÃ£o obrigatÃ³rios'
            }), 400

        confiabilidade = ReceitaService.get_confiabilidade_receitas(
            ano_mes_ini=ano_mes_ini,
            ano_mes_fim=ano_mes_fim
        )

        return jsonify({
            'success': True,
            'data': confiabilidade
        }), 200

    except Exception:
        return _internal_error('receitas')


@receitas_bp.route('/itens/<int:item_id>/detalhe', methods=['GET'])
def detalhe_item(item_id):
    """
    Detalhe completo de uma fonte de receita
    Mostra todas as projeÃ§Ãµes e realizaÃ§Ãµes mÃªs a mÃªs

    Args:
        item_id: ID do item

    Query params:
        ano: Ano (obrigatÃ³rio)

    Returns:
        JSON com detalhe mÃªs a mÃªs
    """
    try:
        ano = request.args.get('ano', type=int)

        if not ano:
            return jsonify({
                'success': False,
                'error': 'ParÃ¢metro ano Ã© obrigatÃ³rio'
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

    except Exception:
        return _internal_error('receitas')


