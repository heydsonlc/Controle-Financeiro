"""
Rotas da API para gerenciamento de Contas Bancárias

Endpoints:
- GET    /api/contas              - Listar todas as contas
- GET    /api/contas/<id>         - Buscar uma conta específica
- POST   /api/contas              - Criar nova conta
- PUT    /api/contas/<id>         - Atualizar conta
- DELETE /api/contas/<id>         - Inativar conta (não remove do BD)
"""
from flask import Blueprint, request, jsonify
from datetime import datetime
from decimal import Decimal
from sqlalchemy import func, case

try:
    from backend.models import db, ContaBancaria, MovimentoFinanceiro
    from backend.services.conta_bancaria_service import ContaBancariaService
except ImportError:
    from models import db, ContaBancaria, MovimentoFinanceiro
    from services.conta_bancaria_service import ContaBancariaService

# Criar blueprint
contas_bancarias_bp = Blueprint('contas_bancarias', __name__)


@contas_bancarias_bp.route('', methods=['GET'])
def listar_contas():
    """
    Lista todas as contas bancárias

    Query params:
        status: ATIVO/INATIVO - Filtrar por status

    Returns:
        JSON com lista de contas
    """
    try:
        status = request.args.get('status')

        if status:
            contas = ContaBancaria.query.filter_by(status=status.upper()).all()
        else:
            contas = ContaBancaria.query.filter_by(status='ATIVO').all()

        return jsonify({
            'success': True,
            'data': [conta.to_dict() for conta in contas],
            'total': len(contas)
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@contas_bancarias_bp.route('/<int:id>', methods=['GET'])
def buscar_conta(id):
    """
    Busca uma conta bancária específica por ID

    Args:
        id: ID da conta

    Returns:
        JSON com dados da conta
    """
    try:
        conta = ContaBancaria.query.get(id)

        if not conta:
            return jsonify({
                'success': False,
                'error': 'Conta não encontrada'
            }), 404

        return jsonify({
            'success': True,
            'data': conta.to_dict()
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@contas_bancarias_bp.route('', methods=['POST'])
def criar_conta():
    """
    Cria uma nova conta bancária

    Body params:
        nome: str (obrigatório)
        instituicao: str (obrigatório)
        tipo: str (obrigatório)
        agencia: str (opcional)
        numero_conta: str (opcional)
        digito_conta: str (opcional)
        saldo_inicial: float (opcional, default 0)
        cor_display: str (opcional, default '#3b82f6')
        icone: str (opcional)

    Returns:
        JSON com dados da conta criada
    """
    try:
        data = request.get_json()

        # Validações
        if not data.get('nome'):
            return jsonify({
                'success': False,
                'error': 'Nome é obrigatório'
            }), 400

        if not data.get('instituicao'):
            return jsonify({
                'success': False,
                'error': 'Instituição é obrigatória'
            }), 400

        if not data.get('tipo'):
            return jsonify({
                'success': False,
                'error': 'Tipo é obrigatório'
            }), 400

        # Criar nova conta
        saldo_inicial = float(data.get('saldo_inicial', 0))

        nova_conta = ContaBancaria(
            nome=data['nome'],
            instituicao=data['instituicao'],
            tipo=data['tipo'],
            agencia=data.get('agencia'),
            numero_conta=data.get('numero_conta'),
            digito_conta=data.get('digito_conta'),
            saldo_inicial=saldo_inicial,
            saldo_atual=saldo_inicial,  # derivado; sem movimentos = saldo_inicial
            cor_display=data.get('cor_display', '#3b82f6'),
            icone=data.get('icone'),
            status='ATIVO'
        )

        db.session.add(nova_conta)
        db.session.flush()
        ContaBancariaService.recalcular_saldo_conta(nova_conta.id)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Conta criada com sucesso',
            'data': nova_conta.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@contas_bancarias_bp.route('/<int:id>', methods=['PUT'])
def atualizar_conta(id):
    """
    Atualiza uma conta bancária existente

    Args:
        id: ID da conta

    Body params:
        nome: str
        instituicao: str
        tipo: str
        agencia: str
        numero_conta: str
        digito_conta: str
        saldo_inicial: float
        cor_display: str
        icone: str
        status: str

    Returns:
        JSON com dados da conta atualizada
    """
    try:
        conta = ContaBancaria.query.get(id)

        if not conta:
            return jsonify({
                'success': False,
                'error': 'Conta não encontrada'
            }), 404

        data = request.get_json()

        # Atualizar campos
        if 'nome' in data:
            conta.nome = data['nome']
        if 'instituicao' in data:
            conta.instituicao = data['instituicao']
        if 'tipo' in data:
            conta.tipo = data['tipo']
        if 'agencia' in data:
            conta.agencia = data['agencia']
        if 'numero_conta' in data:
            conta.numero_conta = data['numero_conta']
        if 'digito_conta' in data:
            conta.digito_conta = data['digito_conta']
        if 'cor_display' in data:
            conta.cor_display = data['cor_display']
        if 'icone' in data:
            conta.icone = data['icone']
        if 'status' in data:
            conta.status = data['status']

        # Saldo inicial só pode ser alterado sem movimentos (para não "teletransportar" saldo).
        # Caso contrário, use o endpoint de ajuste, que cria MovimentoFinanceiro AJUSTE.
        if 'saldo_inicial' in data:
            novo_saldo_inicial = float(data['saldo_inicial'])
            movimentos_existem = db.session.query(MovimentoFinanceiro.id).filter(
                MovimentoFinanceiro.conta_bancaria_id == conta.id
            ).first() is not None
            if movimentos_existem and novo_saldo_inicial != float(conta.saldo_inicial or 0):
                return jsonify({
                    'success': False,
                    'error': 'Não é permitido alterar saldo inicial após existirem movimentos. Use "Ajustar Saldo".'
                }), 400
            conta.saldo_inicial = novo_saldo_inicial
            ContaBancariaService.recalcular_saldo_conta(conta.id)

        conta.data_atualizacao = datetime.utcnow()

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Conta atualizada com sucesso',
            'data': conta.to_dict()
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@contas_bancarias_bp.route('/<int:id>', methods=['DELETE'])
def inativar_conta(id):
    """
    Inativa uma conta bancária (não remove do banco)

    Args:
        id: ID da conta

    Returns:
        JSON com mensagem de sucesso
    """
    try:
        conta = ContaBancaria.query.get(id)

        if not conta:
            return jsonify({
                'success': False,
                'error': 'Conta não encontrada'
            }), 404

        # Inativar ao invés de deletar
        conta.status = 'INATIVO'
        conta.data_atualizacao = datetime.utcnow()

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Conta inativada com sucesso'
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@contas_bancarias_bp.route('/<int:id>/ativar', methods=['PUT'])
def ativar_conta(id):
    """
    Reativa uma conta bancária inativa

    Args:
        id: ID da conta

    Returns:
        JSON com mensagem de sucesso
    """
    try:
        conta = ContaBancaria.query.get(id)

        if not conta:
            return jsonify({
                'success': False,
                'error': 'Conta não encontrada'
            }), 404

        conta.status = 'ATIVO'
        conta.data_atualizacao = datetime.utcnow()

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Conta reativada com sucesso',
            'data': conta.to_dict()
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@contas_bancarias_bp.route('/<int:id>/movimentos', methods=['GET'])
def listar_movimentos(id):
    """
    Lista extrato (movimentos) de uma conta bancária.

    Query params:
        inicio: YYYY-MM-DD (opcional)
        fim: YYYY-MM-DD (opcional)
        limit: int (opcional, default 200)
        incluir_saldo: 0/1 (opcional, default 1) - inclui saldo_apos_movimento
    """
    try:
        conta = ContaBancaria.query.get(id)
        if not conta:
            return jsonify({'success': False, 'error': 'Conta não encontrada'}), 404

        inicio = request.args.get('inicio')
        fim = request.args.get('fim')
        limit = request.args.get('limit', default=200, type=int)
        incluir_saldo = request.args.get('incluir_saldo', default=1, type=int) != 0

        data_inicio = ContaBancariaService.parse_data(inicio) if inicio else None
        data_fim = ContaBancariaService.parse_data(fim) if fim else None

        query = MovimentoFinanceiro.query.filter_by(conta_bancaria_id=id)
        if data_inicio:
            query = query.filter(MovimentoFinanceiro.data_movimento >= data_inicio)
        if data_fim:
            query = query.filter(MovimentoFinanceiro.data_movimento <= data_fim)

        movimentos = query.order_by(MovimentoFinanceiro.data_movimento.desc(), MovimentoFinanceiro.id.desc()).limit(limit).all()
        movimentos_dict = [m.to_dict() for m in movimentos]

        if incluir_saldo:
            # saldo base = saldo_inicial + movimentos antes do início (se houver)
            saldo_base = Decimal(str(conta.saldo_inicial or 0))
            if data_inicio:
                anterior = db.session.query(
                    func.coalesce(
                        func.sum(case((MovimentoFinanceiro.tipo == 'CREDITO', MovimentoFinanceiro.valor), else_=0)),
                        0,
                    ).label('cred'),
                    func.coalesce(
                        func.sum(case((MovimentoFinanceiro.tipo == 'DEBITO', MovimentoFinanceiro.valor), else_=0)),
                        0,
                    ).label('deb'),
                ).filter(
                    MovimentoFinanceiro.conta_bancaria_id == id,
                    MovimentoFinanceiro.data_movimento < data_inicio
                ).first()
                saldo_base = saldo_base + Decimal(str(anterior.cred or 0)) - Decimal(str(anterior.deb or 0))

            # Movimentos do período em ordem asc para calcular saldo_apos
            query_asc = MovimentoFinanceiro.query.filter_by(conta_bancaria_id=id)
            if data_inicio:
                query_asc = query_asc.filter(MovimentoFinanceiro.data_movimento >= data_inicio)
            if data_fim:
                query_asc = query_asc.filter(MovimentoFinanceiro.data_movimento <= data_fim)
            movs_asc = query_asc.order_by(MovimentoFinanceiro.data_movimento.asc(), MovimentoFinanceiro.id.asc()).all()

            saldo_corrente = saldo_base
            saldo_map = {}
            for m in movs_asc:
                if m.tipo == 'CREDITO':
                    saldo_corrente += Decimal(str(m.valor or 0))
                elif m.tipo == 'DEBITO':
                    saldo_corrente -= Decimal(str(m.valor or 0))
                saldo_map[m.id] = float(saldo_corrente)

            for md in movimentos_dict:
                md['saldo_apos_movimento'] = saldo_map.get(md['id'])

        return jsonify({'success': True, 'data': movimentos_dict}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@contas_bancarias_bp.route('/<int:id>/ajuste-saldo', methods=['POST'])
def ajuste_saldo(id):
    """
    Cria um movimento de AJUSTE para que o saldo final da conta fique explicável pelo extrato.

    Body (JSON):
        {
            "valor_final_desejado": float (opcional) ou "valor_do_ajuste": float (opcional),
            "descricao": "string" (opcional),
            "data_movimento": "YYYY-MM-DD" (opcional)
        }
    """
    try:
        conta = ContaBancaria.query.get(id)
        if not conta:
            return jsonify({'success': False, 'error': 'Conta não encontrada'}), 404

        data = request.get_json() or {}
        data_movimento = ContaBancariaService.parse_data(data.get('data_movimento'))
        descricao = (data.get('descricao') or 'Ajuste manual de saldo').strip()

        ContaBancariaService.recalcular_saldo_conta(id)
        saldo_atual = Decimal(str(conta.saldo_atual or 0))

        delta = None
        if data.get('valor_final_desejado') is not None:
            desejado = Decimal(str(data.get('valor_final_desejado')))
            delta = desejado - saldo_atual
        elif data.get('valor_do_ajuste') is not None:
            delta = Decimal(str(data.get('valor_do_ajuste')))
        else:
            return jsonify({'success': False, 'error': 'Informe valor_final_desejado ou valor_do_ajuste'}), 400

        if delta == 0:
            return jsonify({'success': True, 'message': 'Saldo já está no valor desejado', 'data': conta.to_dict()}), 200

        tipo = 'CREDITO' if delta > 0 else 'DEBITO'
        valor = abs(delta)

        movimento = ContaBancariaService.criar_movimento(
            id,
            tipo=tipo,
            valor=valor,
            descricao=descricao,
            data_movimento=data_movimento,
            origem='AJUSTE',
            ajustavel=True,
        )

        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Ajuste criado com sucesso',
            'data': {
                'conta': conta.to_dict(),
                'movimento': movimento.to_dict(),
            }
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@contas_bancarias_bp.route('/<int:conta_id>/movimentos/<int:mov_id>', methods=['PUT'])
def editar_movimento(conta_id, mov_id):
    """
    Edita um movimento ajustável (AJUSTE).
    """
    try:
        mov = MovimentoFinanceiro.query.get(mov_id)
        if not mov or mov.conta_bancaria_id != conta_id:
            return jsonify({'success': False, 'error': 'Movimento não encontrado'}), 404

        if not mov.ajustavel:
            return jsonify({'success': False, 'error': 'Apenas movimentos de AJUSTE podem ser editados'}), 400

        data = request.get_json() or {}
        if data.get('tipo') in ('CREDITO', 'DEBITO'):
            mov.tipo = data['tipo']
        if data.get('valor') is not None:
            valor = Decimal(str(data.get('valor')))
            if valor <= 0:
                return jsonify({'success': False, 'error': 'valor deve ser maior que zero'}), 400
            mov.valor = valor
        if data.get('descricao') is not None:
            mov.descricao = (data.get('descricao') or '').strip() or mov.descricao
        if data.get('data_movimento') is not None:
            mov.data_movimento = ContaBancariaService.parse_data(data.get('data_movimento'))

        ContaBancariaService.recalcular_saldo_conta(conta_id)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Movimento atualizado', 'data': mov.to_dict()}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@contas_bancarias_bp.route('/<int:conta_id>/movimentos/<int:mov_id>', methods=['DELETE'])
def deletar_movimento(conta_id, mov_id):
    """
    Exclui um movimento ajustável (AJUSTE).
    """
    try:
        mov = MovimentoFinanceiro.query.get(mov_id)
        if not mov or mov.conta_bancaria_id != conta_id:
            return jsonify({'success': False, 'error': 'Movimento não encontrado'}), 404

        if not mov.ajustavel:
            return jsonify({'success': False, 'error': 'Apenas movimentos de AJUSTE podem ser excluídos'}), 400

        db.session.delete(mov)
        ContaBancariaService.recalcular_saldo_conta(conta_id)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Movimento excluído'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@contas_bancarias_bp.route('/transferir', methods=['POST'])
def transferir():
    """
    Transferência entre contas bancárias (débito + crédito atômicos).
    """
    try:
        data = request.get_json() or {}
        conta_origem_id = data.get('conta_origem_id')
        conta_destino_id = data.get('conta_destino_id')
        valor = data.get('valor')
        if not conta_origem_id or not conta_destino_id or valor is None:
            return jsonify({'success': False, 'error': 'conta_origem_id, conta_destino_id e valor são obrigatórios'}), 400

        descricao = (data.get('descricao') or 'Transferência').strip()
        data_movimento = ContaBancariaService.parse_data(data.get('data_movimento'))

        resultado = ContaBancariaService.gerar_transferencia(
            int(conta_origem_id),
            int(conta_destino_id),
            valor=Decimal(str(valor)),
            descricao=descricao,
            data_movimento=data_movimento,
        )
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Transferência realizada',
            'data': {
                'transferencia_id': resultado['transferencia_id'],
                'debito': resultado['debito'].to_dict(),
                'credito': resultado['credito'].to_dict(),
            }
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
