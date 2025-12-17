"""
Rotas para gerenciamento de Cartões de Crédito
"""
from flask import Blueprint, request, jsonify
from backend.models import db, ItemDespesa, ConfigAgregador, ItemAgregado, OrcamentoAgregado, LancamentoAgregado, Categoria
from backend.services.cartao_service import CartaoService
from datetime import datetime
from dateutil.relativedelta import relativedelta
from sqlalchemy import func

cartoes_bp = Blueprint('cartoes', __name__, url_prefix='/api/cartoes')


# ============================================================================
# ROTAS PARA CARTÕES DE CRÉDITO (ItemDespesa tipo='Agregador')
# ============================================================================

@cartoes_bp.route('', methods=['GET'])
def listar_cartoes():
    """Lista todos os cartões de crédito"""
    try:
        cartoes = ItemDespesa.query.filter_by(tipo='Agregador', ativo=True).all()
        resultado = []

        for cartao in cartoes:
            cartao_dict = cartao.to_dict()
            # Adicionar configuração do agregador
            if cartao.config_agregador:
                cartao_dict['config'] = cartao.config_agregador.to_dict()
            # Adicionar categoria
            if cartao.categoria:
                cartao_dict['categoria_nome'] = cartao.categoria.nome
            resultado.append(cartao_dict)

        return jsonify(resultado), 200
    except Exception as e:
        return jsonify({'erro': str(e)}), 500


@cartoes_bp.route('/<int:id>', methods=['GET'])
def obter_cartao(id):
    """Obtém detalhes de um cartão específico"""
    try:
        cartao = ItemDespesa.query.filter_by(id=id, tipo='Agregador').first()
        if not cartao:
            return jsonify({'erro': 'Cartão não encontrado'}), 404

        cartao_dict = cartao.to_dict()
        if cartao.config_agregador:
            cartao_dict['config'] = cartao.config_agregador.to_dict()
        if cartao.categoria:
            cartao_dict['categoria_nome'] = cartao.categoria.nome

        return jsonify(cartao_dict), 200
    except Exception as e:
        return jsonify({'erro': str(e)}), 500


@cartoes_bp.route('', methods=['POST'])
def criar_cartao():
    """Cria um novo cartão de crédito"""
    try:
        dados = request.json

        # Se não especificou categoria, usa a categoria padrão "Cartões de Crédito"
        categoria_id = dados.get('categoria_id')
        if not categoria_id:
            categoria_padrao = Categoria.query.filter_by(nome='Cartoes de Credito').first()
            if categoria_padrao:
                categoria_id = categoria_padrao.id

        # Criar o ItemDespesa
        novo_cartao = ItemDespesa(
            categoria_id=categoria_id,
            nome=dados['nome'],
            tipo='Agregador',
            descricao=dados.get('descricao', ''),
            ativo=True,
            recorrente=True,
            tipo_recorrencia='mensal'
        )

        db.session.add(novo_cartao)
        db.session.flush()  # Para obter o ID

        # Criar a configuração do agregador
        config = ConfigAgregador(
            item_despesa_id=novo_cartao.id,
            dia_fechamento=dados['dia_fechamento'],
            dia_vencimento=dados['dia_vencimento'],
            limite_credito=dados.get('limite_credito'),
            numero_cartao=dados.get('numero_cartao'),
            data_validade=dados.get('data_validade'),
            codigo_seguranca=dados.get('codigo_seguranca'),
            tem_codigo=dados.get('tem_codigo', True),
            observacoes=dados.get('observacoes', '')
        )

        db.session.add(config)
        db.session.commit()

        resultado = novo_cartao.to_dict()
        resultado['config'] = config.to_dict()

        return jsonify(resultado), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'erro': str(e)}), 500


@cartoes_bp.route('/<int:id>', methods=['PUT'])
def atualizar_cartao(id):
    """Atualiza um cartão existente"""
    try:
        cartao = ItemDespesa.query.filter_by(id=id, tipo='Agregador').first()
        if not cartao:
            return jsonify({'erro': 'Cartão não encontrado'}), 404

        dados = request.json

        # Atualizar ItemDespesa
        cartao.categoria_id = dados.get('categoria_id', cartao.categoria_id)
        cartao.nome = dados.get('nome', cartao.nome)
        cartao.descricao = dados.get('descricao', cartao.descricao)

        # Atualizar ConfigAgregador
        if cartao.config_agregador:
            cartao.config_agregador.dia_fechamento = dados.get('dia_fechamento', cartao.config_agregador.dia_fechamento)
            cartao.config_agregador.dia_vencimento = dados.get('dia_vencimento', cartao.config_agregador.dia_vencimento)
            cartao.config_agregador.limite_credito = dados.get('limite_credito', cartao.config_agregador.limite_credito)
            cartao.config_agregador.numero_cartao = dados.get('numero_cartao', cartao.config_agregador.numero_cartao)
            cartao.config_agregador.data_validade = dados.get('data_validade', cartao.config_agregador.data_validade)
            cartao.config_agregador.codigo_seguranca = dados.get('codigo_seguranca', cartao.config_agregador.codigo_seguranca)
            cartao.config_agregador.tem_codigo = dados.get('tem_codigo', cartao.config_agregador.tem_codigo)
            cartao.config_agregador.observacoes = dados.get('observacoes', cartao.config_agregador.observacoes)

        db.session.commit()

        resultado = cartao.to_dict()
        if cartao.config_agregador:
            resultado['config'] = cartao.config_agregador.to_dict()

        return jsonify(resultado), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'erro': str(e)}), 500


@cartoes_bp.route('/<int:id>/codigo-seguranca', methods=['POST'])
def revelar_codigo_seguranca(id):
    """Revela o código de segurança mediante senha"""
    try:
        dados = request.json
        senha = dados.get('senha')

        # Validar senha (por enquanto, senha fixa - pode ser melhorado futuramente)
        SENHA_MESTRE = '1234'  # TODO: Mover para configuração ou autenticação real

        if senha != SENHA_MESTRE:
            return jsonify({'erro': 'Senha incorreta'}), 401

        # Buscar cartão
        cartao = ItemDespesa.query.filter_by(id=id, tipo='Agregador').first()
        if not cartao or not cartao.config_agregador:
            return jsonify({'erro': 'Cartão não encontrado'}), 404

        return jsonify({
            'codigo_seguranca': cartao.config_agregador.codigo_seguranca or ''
        }), 200

    except Exception as e:
        return jsonify({'erro': str(e)}), 500


@cartoes_bp.route('/<int:id>', methods=['DELETE'])
def excluir_cartao(id):
    """Exclui (desativa) um cartão"""
    try:
        cartao = ItemDespesa.query.filter_by(id=id, tipo='Agregador').first()
        if not cartao:
            return jsonify({'erro': 'Cartão não encontrado'}), 404

        cartao.ativo = False
        db.session.commit()

        return jsonify({'mensagem': 'Cartão excluído com sucesso'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'erro': str(e)}), 500


# ============================================================================
# ROTAS PARA ITENS AGREGADOS (Categorias dentro do cartão)
# ============================================================================

@cartoes_bp.route('/<int:cartao_id>/itens', methods=['GET'])
def listar_itens_agregados(cartao_id):
    """Lista todas as categorias de um cartão"""
    try:
        itens = ItemAgregado.query.filter_by(item_despesa_id=cartao_id, ativo=True).all()
        return jsonify([item.to_dict() for item in itens]), 200
    except Exception as e:
        return jsonify({'erro': str(e)}), 500


@cartoes_bp.route('/<int:cartao_id>/itens', methods=['POST'])
def criar_item_agregado(cartao_id):
    """Cria uma nova categoria dentro do cartão"""
    try:
        dados = request.json

        novo_item = ItemAgregado(
            item_despesa_id=cartao_id,
            nome=dados['nome'],
            descricao=dados.get('descricao', ''),
            ativo=True
        )

        db.session.add(novo_item)
        db.session.commit()

        return jsonify(novo_item.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'erro': str(e)}), 500


@cartoes_bp.route('/itens/<int:item_id>', methods=['PUT'])
def atualizar_item_agregado(item_id):
    """Atualiza uma categoria do cartão"""
    try:
        item = ItemAgregado.query.get(item_id)
        if not item:
            return jsonify({'erro': 'Item não encontrado'}), 404

        dados = request.json
        item.nome = dados.get('nome', item.nome)
        item.descricao = dados.get('descricao', item.descricao)

        db.session.commit()
        return jsonify(item.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'erro': str(e)}), 500


@cartoes_bp.route('/itens/<int:item_id>', methods=['DELETE'])
def excluir_item_agregado(item_id):
    """
    Exclui (inativa) uma categoria do cartão

    Regra: Só permite exclusão se não existirem lançamentos
    """
    try:
        item = ItemAgregado.query.get(item_id)
        if not item:
            return jsonify({'erro': 'Item não encontrado'}), 404

        # Verificar se existem lançamentos (Teste 5 do roteiro)
        total_lancamentos = LancamentoAgregado.query.filter_by(
            item_agregado_id=item_id
        ).count()

        if total_lancamentos > 0:
            return jsonify({
                'erro': f'Não é possível excluir esta categoria. '
                        f'Existem {total_lancamentos} lançamento(s) vinculado(s).',
                'total_lancamentos': total_lancamentos
            }), 400

        # Se não houver lançamentos, permitir inativação
        item.ativo = False
        db.session.commit()

        return jsonify({'mensagem': 'Categoria excluída com sucesso'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'erro': str(e)}), 500


# ============================================================================
# ROTAS PARA ORÇAMENTOS AGREGADOS (Previsão de gastos)
# ============================================================================

@cartoes_bp.route('/itens/<int:item_id>/orcamentos', methods=['GET'])
def listar_orcamentos(item_id):
    """Lista orçamentos de um item agregado"""
    try:
        mes_referencia = request.args.get('mes_referencia')

        query = OrcamentoAgregado.query.filter_by(item_agregado_id=item_id)

        if mes_referencia:
            # Converter para primeiro dia do mês
            mes_ref_date = datetime.strptime(mes_referencia + '-01', '%Y-%m-%d').date()
            query = query.filter_by(mes_referencia=mes_ref_date)

        orcamentos = query.all()
        return jsonify([orc.to_dict() for orc in orcamentos]), 200
    except Exception as e:
        return jsonify({'erro': str(e)}), 500


@cartoes_bp.route('/itens/<int:item_id>/orcamentos', methods=['POST'])
def criar_orcamento(item_id):
    """Cria um orçamento para um item agregado"""
    try:
        dados = request.json

        # Converter mes_referencia para Date (primeiro dia do mês)
        mes_ref_str = dados['mes_referencia']
        mes_ref_date = datetime.strptime(mes_ref_str + '-01', '%Y-%m-%d').date()

        # Verificar se já existe orçamento para este mês
        orcamento_existente = OrcamentoAgregado.query.filter_by(
            item_agregado_id=item_id,
            mes_referencia=mes_ref_date
        ).first()

        if orcamento_existente:
            return jsonify({'erro': 'Já existe orçamento para este mês'}), 400

        novo_orcamento = OrcamentoAgregado(
            item_agregado_id=item_id,
            mes_referencia=mes_ref_date,
            valor_teto=dados['valor_teto'],
            observacoes=dados.get('observacoes', '')
        )

        db.session.add(novo_orcamento)
        db.session.commit()

        return jsonify(novo_orcamento.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'erro': str(e)}), 500


@cartoes_bp.route('/orcamentos/<int:orcamento_id>', methods=['PUT'])
def atualizar_orcamento(orcamento_id):
    """Atualiza um orçamento"""
    try:
        orcamento = OrcamentoAgregado.query.get(orcamento_id)
        if not orcamento:
            return jsonify({'erro': 'Orçamento não encontrado'}), 404

        dados = request.json
        orcamento.valor_teto = dados.get('valor_teto', orcamento.valor_teto)
        orcamento.observacoes = dados.get('observacoes', orcamento.observacoes)

        db.session.commit()
        return jsonify(orcamento.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'erro': str(e)}), 500


@cartoes_bp.route('/orcamentos/<int:orcamento_id>', methods=['DELETE'])
def excluir_orcamento(orcamento_id):
    """Exclui um orçamento"""
    try:
        orcamento = OrcamentoAgregado.query.get(orcamento_id)
        if not orcamento:
            return jsonify({'erro': 'Orçamento não encontrado'}), 404

        db.session.delete(orcamento)
        db.session.commit()

        return jsonify({'mensagem': 'Orçamento excluído com sucesso'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'erro': str(e)}), 500


# ============================================================================
# ROTAS PARA LANÇAMENTOS AGREGADOS (Gastos reais)
# ============================================================================

@cartoes_bp.route('/itens/<int:item_id>/lancamentos', methods=['GET'])
def listar_lancamentos(item_id):
    """Lista lançamentos de um item agregado"""
    try:
        mes_fatura = request.args.get('mes_fatura')

        query = LancamentoAgregado.query.filter_by(item_agregado_id=item_id)

        if mes_fatura:
            # Converter para primeiro dia do mês
            mes_fat_date = datetime.strptime(mes_fatura + '-01', '%Y-%m-%d').date()
            query = query.filter_by(mes_fatura=mes_fat_date)

        lancamentos = query.order_by(LancamentoAgregado.data_compra.desc()).all()
        return jsonify([lanc.to_dict() for lanc in lancamentos]), 200
    except Exception as e:
        return jsonify({'erro': str(e)}), 500


@cartoes_bp.route('/itens/<int:item_id>/lancamentos', methods=['POST'])
def criar_lancamento(item_id):
    """
    Cria um lançamento (gasto) em um item agregado

    IMPORTANTE: Não cria despesa individual, apenas consome orçamento
    A fatura virtual é criada automaticamente se não existir
    """
    try:
        dados = request.json

        # Converter datas
        data_compra = datetime.strptime(dados['data_compra'], '%Y-%m-%d').date()

        # Processar mes_fatura (pode vir como YYYY-MM ou YYYY-MM-DD)
        mes_fatura_str = dados['mes_fatura']
        if len(mes_fatura_str) == 7:  # Formato YYYY-MM
            mes_fatura_str += '-01'
        mes_fatura = datetime.strptime(mes_fatura_str, '%Y-%m-%d').date()

        # Buscar item agregado para pegar o cartao_id
        item_agregado = ItemAgregado.query.get(item_id)
        if not item_agregado:
            return jsonify({'erro': 'Item agregado não encontrado'}), 404

        # Preparar dados para o service
        dados_lancamento = {
            'cartao_id': item_agregado.item_despesa_id,
            'item_agregado_id': item_id,
            'descricao': dados['descricao'],
            'valor': dados['valor'],
            'data_compra': data_compra,
            'mes_fatura': mes_fatura,
            'numero_parcela': dados.get('numero_parcela', 1),
            'total_parcelas': dados.get('total_parcelas', 1),
            'observacoes': dados.get('observacoes', '')
        }

        # Usar CartaoService para adicionar lançamento e garantir fatura
        lancamento, fatura = CartaoService.adicionar_lancamento(dados_lancamento)

        return jsonify({
            'success': True,
            'message': 'Lançamento criado com sucesso',
            'lancamento': lancamento.to_dict(),
            'fatura': {
                'id': fatura.id,
                'valor_planejado': float(fatura.valor_planejado),
                'valor_executado': float(fatura.valor_executado),
                'estouro_orcamento': fatura.estouro_orcamento
            }
        }), 201

    except ValueError as e:
        return jsonify({'success': False, 'erro': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'erro': str(e)}), 500


@cartoes_bp.route('/<int:cartao_id>/lancamentos', methods=['POST'])
def criar_lancamento_sem_categoria(cartao_id):
    """
    Cria um lançamento diretamente no cartão (sem categoria)

    Este endpoint aceita lançamentos que NÃO consomem limite orçamentário.
    O item_agregado_id é opcional - se fornecido, consome limite; se None, apenas vai para fatura.
    """
    try:
        dados = request.json

        # Converter datas
        data_compra = datetime.strptime(dados['data_compra'], '%Y-%m-%d').date()

        # Processar mes_fatura (pode vir como YYYY-MM ou YYYY-MM-DD)
        mes_fatura_str = dados['mes_fatura']
        if len(mes_fatura_str) == 7:  # Formato YYYY-MM
            mes_fatura_str += '-01'
        mes_fatura = datetime.strptime(mes_fatura_str, '%Y-%m-%d').date()

        # Preparar dados para o service
        dados_lancamento = {
            'cartao_id': cartao_id,
            'item_agregado_id': dados.get('item_agregado_id'),  # OPCIONAL (None se não informado)
            'descricao': dados['descricao'],
            'valor': dados['valor'],
            'data_compra': data_compra,
            'mes_fatura': mes_fatura,
            'numero_parcela': dados.get('numero_parcela', 1),
            'total_parcelas': dados.get('total_parcelas', 1),
            'observacoes': dados.get('observacoes', '')
        }

        # Usar CartaoService para adicionar lançamento e garantir fatura
        lancamento, fatura = CartaoService.adicionar_lancamento(dados_lancamento)

        return jsonify({
            'success': True,
            'message': 'Lançamento criado com sucesso',
            'lancamento': lancamento.to_dict(),
            'fatura': {
                'id': fatura.id,
                'valor_planejado': float(fatura.valor_planejado),
                'valor_executado': float(fatura.valor_executado),
                'estouro_orcamento': fatura.estouro_orcamento
            }
        }), 201

    except ValueError as e:
        return jsonify({'success': False, 'erro': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'erro': str(e)}), 500


@cartoes_bp.route('/lancamentos/<int:lancamento_id>', methods=['PUT'])
def atualizar_lancamento(lancamento_id):
    """Atualiza um lançamento"""
    try:
        lancamento = LancamentoAgregado.query.get(lancamento_id)
        if not lancamento:
            return jsonify({'erro': 'Lançamento não encontrado'}), 404

        dados = request.json

        lancamento.descricao = dados.get('descricao', lancamento.descricao)
        lancamento.valor = dados.get('valor', lancamento.valor)

        if 'data_compra' in dados:
            lancamento.data_compra = datetime.strptime(dados['data_compra'], '%Y-%m-%d').date()

        if 'mes_fatura' in dados:
            lancamento.mes_fatura = datetime.strptime(dados['mes_fatura'] + '-01', '%Y-%m-%d').date()

        lancamento.numero_parcela = dados.get('numero_parcela', lancamento.numero_parcela)
        lancamento.total_parcelas = dados.get('total_parcelas', lancamento.total_parcelas)
        lancamento.observacoes = dados.get('observacoes', lancamento.observacoes)

        db.session.commit()
        return jsonify(lancamento.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'erro': str(e)}), 500


@cartoes_bp.route('/lancamentos/<int:lancamento_id>', methods=['DELETE'])
def excluir_lancamento(lancamento_id):
    """Exclui um lançamento"""
    try:
        lancamento = LancamentoAgregado.query.get(lancamento_id)
        if not lancamento:
            return jsonify({'erro': 'Lançamento não encontrado'}), 404

        db.session.delete(lancamento)
        db.session.commit()

        return jsonify({'mensagem': 'Lançamento excluído com sucesso'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'erro': str(e)}), 500


# ============================================================================
# ROTAS PARA RESUMO E RELATÓRIOS
# ============================================================================

@cartoes_bp.route('/<int:cartao_id>/resumo', methods=['GET'])
def obter_resumo_cartao(cartao_id):
    """Obtém resumo completo do cartão com orçamentos e gastos"""
    try:
        mes_referencia = request.args.get('mes_referencia', datetime.now().strftime('%Y-%m'))
        mes_ref_date = datetime.strptime(mes_referencia + '-01', '%Y-%m-%d').date()

        # Buscar cartão
        cartao = ItemDespesa.query.filter_by(id=cartao_id, tipo='Agregador').first()
        if not cartao:
            return jsonify({'erro': 'Cartão não encontrado'}), 404

        # Calcular EXECUTADO TOTAL do cartão (TODOS os lançamentos, com ou sem categoria)
        total_gasto_cartao = db.session.query(func.sum(LancamentoAgregado.valor)).filter(
            LancamentoAgregado.cartao_id == cartao_id,
            LancamentoAgregado.mes_fatura == mes_ref_date
        ).scalar() or 0
        total_gasto_cartao = float(total_gasto_cartao)

        # Buscar itens agregados ativos (categorias)
        itens = ItemAgregado.query.filter_by(item_despesa_id=cartao_id, ativo=True).all()

        resumo_itens = []
        total_orcado = 0

        for item in itens:
            # Buscar orçamento do mês
            orcamento = OrcamentoAgregado.query.filter_by(
                item_agregado_id=item.id,
                mes_referencia=mes_ref_date
            ).first()

            # Buscar gastos do mês (apenas lançamentos DESTA categoria)
            gastos = LancamentoAgregado.query.filter_by(
                item_agregado_id=item.id,
                mes_fatura=mes_ref_date
            ).all()

            valor_orcado = float(orcamento.valor_teto) if orcamento else 0
            valor_gasto = sum(float(g.valor) for g in gastos)

            total_orcado += valor_orcado

            resumo_itens.append({
                'id': item.id,
                'nome': item.nome,
                'descricao': item.descricao,
                'valor_orcado': valor_orcado,
                'valor_gasto': valor_gasto,
                'saldo': valor_orcado - valor_gasto,
                'percentual_utilizado': round((valor_gasto / valor_orcado * 100) if valor_orcado > 0 else 0, 2),
                'orcamento_id': orcamento.id if orcamento else None
            })

        resultado = {
            'cartao': cartao.to_dict(),
            'mes_referencia': mes_referencia,
            'total_orcado': total_orcado,
            'total_gasto': total_gasto_cartao,  # Inclui lançamentos sem categoria
            'saldo_disponivel': total_orcado - total_gasto_cartao,
            'limite_credito': float(cartao.config_agregador.limite_credito) if cartao.config_agregador and cartao.config_agregador.limite_credito else None,
            'itens': resumo_itens
        }

        return jsonify(resultado), 200
    except Exception as e:
        import traceback
        traceback.print_exc()  # Log completo no console
        return jsonify({'erro': f'Erro ao carregar resumo: {str(e)}'}), 500


# ============================================================================
# ROTAS PARA ALERTAS (NÃO BLOQUEANTES)
# ============================================================================

@cartoes_bp.route('/alertas', methods=['GET'])
def obter_alertas():
    """
    Retorna todos os alertas de orçamento (locais e globais)

    Query params:
        - cartao_id (opcional): ID do cartão para filtrar
        - mes_referencia (opcional): Mês no formato YYYY-MM (padrão: mês atual)

    IMPORTANTE: Alertas NÃO bloqueiam lançamentos, são apenas informativos
    """
    try:
        cartao_id = request.args.get('cartao_id', type=int)
        mes_referencia = request.args.get('mes_referencia')

        # Converter mes_referencia para date
        if mes_referencia:
            competencia = datetime.strptime(mes_referencia + '-01', '%Y-%m-%d').date()
        else:
            competencia = None

        # Buscar alertas
        alertas = CartaoService.obter_todos_alertas(
            cartao_id=cartao_id,
            competencia=competencia
        )

        return jsonify({
            'success': True,
            'data': alertas
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'erro': str(e)
        }), 500


@cartoes_bp.route('/<int:cartao_id>/alertas', methods=['GET'])
def obter_alertas_cartao(cartao_id):
    """
    Retorna alertas específicos de um cartão

    Query params:
        - mes_referencia (opcional): Mês no formato YYYY-MM (padrão: mês atual)
    """
    try:
        mes_referencia = request.args.get('mes_referencia')

        # Converter mes_referencia para date
        if mes_referencia:
            competencia = datetime.strptime(mes_referencia + '-01', '%Y-%m-%d').date()
        else:
            competencia = None

        # Buscar alertas do cartão
        alertas = CartaoService.obter_todos_alertas(
            cartao_id=cartao_id,
            competencia=competencia
        )

        return jsonify({
            'success': True,
            'cartao_id': cartao_id,
            'data': alertas
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'erro': str(e)
        }), 500

