"""
Serviço de Receitas - Lógica de negócio para gestão de receitas

Este serviço implementa:
1. CRUD de fontes de receita (ItemReceita)
2. Planejamento de receitas (Orçamento)
3. Registro de receitas realizadas
4. Análises e relatórios (KPIs)
"""
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from sqlalchemy import func, extract, and_
from decimal import Decimal

try:
    from backend.models import db, ItemReceita, ReceitaOrcamento, ReceitaRealizada, ContaPatrimonio
except ImportError:
    from models import db, ItemReceita, ReceitaOrcamento, ReceitaRealizada, ContaPatrimonio


class ReceitaService:
    """
    Serviço para gerenciamento completo de receitas
    """

    # ========================================================================
    # CRUD DE FONTES DE RECEITA (ItemReceita)
    # ========================================================================

    @staticmethod
    def criar_item_receita(dados):
        """
        Cria uma nova fonte de receita

        Args:
            dados (dict): Dados da receita
                - nome (str): Nome da fonte
                - tipo (str): SALARIO_FIXO, GRATIFICACAO, RENDA_EXTRA, etc.
                - descricao (str, opcional)
                - valor_base_mensal (float, opcional)
                - dia_previsto_pagamento (int, opcional)
                - conta_origem_id (int, opcional)

        Returns:
            ItemReceita: Objeto criado

        Raises:
            ValueError: Se dados inválidos
        """
        # Validações
        if not dados.get('nome'):
            raise ValueError('Nome é obrigatório')

        if not dados.get('tipo'):
            raise ValueError('Tipo é obrigatório')

        # Tipos válidos
        tipos_validos = [
            'SALARIO_FIXO', 'GRATIFICACAO', 'RENDA_EXTRA',
            'ALUGUEL', 'RENDIMENTO_FINANCEIRO', 'OUTROS'
        ]

        if dados['tipo'] not in tipos_validos:
            raise ValueError(f'Tipo inválido. Use um dos seguintes: {", ".join(tipos_validos)}')

        # Verificar se já existe
        existe = ItemReceita.query.filter_by(nome=dados['nome']).first()
        if existe:
            raise ValueError('Já existe uma fonte de receita com este nome')

        # Criar
        item = ItemReceita(
            nome=dados['nome'],
            tipo=dados['tipo'],
            descricao=dados.get('descricao', ''),
            ativo=dados.get('ativo', True),
            valor_base_mensal=dados.get('valor_base_mensal'),
            dia_previsto_pagamento=dados.get('dia_previsto_pagamento'),
            conta_origem_id=dados.get('conta_origem_id')
        )

        db.session.add(item)
        db.session.commit()

        return item

    @staticmethod
    def listar_itens_receita(tipo=None, ativo=None):
        """
        Lista fontes de receita com filtros opcionais

        Args:
            tipo (str, opcional): Filtrar por tipo
            ativo (bool, opcional): Filtrar por status ativo

        Returns:
            list[ItemReceita]: Lista de fontes
        """
        query = ItemReceita.query

        if tipo:
            query = query.filter_by(tipo=tipo)

        if ativo is not None:
            query = query.filter_by(ativo=ativo)

        return query.order_by(ItemReceita.nome).all()

    @staticmethod
    def atualizar_item_receita(item_id, dados):
        """
        Atualiza uma fonte de receita

        Args:
            item_id (int): ID do item
            dados (dict): Dados para atualizar

        Returns:
            ItemReceita: Item atualizado

        Raises:
            ValueError: Se item não encontrado ou dados inválidos
        """
        item = ItemReceita.query.get(item_id)
        if not item:
            raise ValueError('Fonte de receita não encontrada')

        # Atualizar campos
        if 'nome' in dados:
            # Verificar duplicidade
            existe = ItemReceita.query.filter(
                ItemReceita.nome == dados['nome'],
                ItemReceita.id != item_id
            ).first()
            if existe:
                raise ValueError('Já existe outra fonte com este nome')
            item.nome = dados['nome']

        if 'tipo' in dados:
            item.tipo = dados['tipo']

        if 'descricao' in dados:
            item.descricao = dados['descricao']

        if 'ativo' in dados:
            item.ativo = dados['ativo']

        if 'valor_base_mensal' in dados:
            item.valor_base_mensal = dados['valor_base_mensal']

        if 'dia_previsto_pagamento' in dados:
            item.dia_previsto_pagamento = dados['dia_previsto_pagamento']

        if 'conta_origem_id' in dados:
            item.conta_origem_id = dados['conta_origem_id']

        db.session.commit()
        return item

    @staticmethod
    def inativar_item_receita(item_id):
        """
        Inativa (soft delete) uma fonte de receita

        Args:
            item_id (int): ID do item

        Returns:
            ItemReceita: Item inativado
        """
        item = ItemReceita.query.get(item_id)
        if not item:
            raise ValueError('Fonte de receita não encontrada')

        item.ativo = False
        db.session.commit()
        return item

    # ========================================================================
    # PLANEJAMENTO (ORÇAMENTO DE RECEITAS)
    # ========================================================================

    @staticmethod
    def criar_ou_atualizar_orcamento_mensal(item_receita_id, ano_mes, valor_previsto,
                                            periodicidade='MENSAL_FIXA', observacoes=None):
        """
        Cria ou atualiza o orçamento de receita para um mês específico

        Args:
            item_receita_id (int): ID da fonte
            ano_mes (str ou date): Mês no formato 'YYYY-MM-01' ou objeto date
            valor_previsto (float): Valor esperado
            periodicidade (str): MENSAL_FIXA, EVENTUAL ou UNICA
            observacoes (str, opcional): Observações

        Returns:
            ReceitaOrcamento: Orçamento criado ou atualizado
        """
        # Converter string para date se necessário
        if isinstance(ano_mes, str):
            ano_mes = datetime.strptime(ano_mes[:10], '%Y-%m-%d').date()

        # Garantir que seja primeiro dia do mês
        ano_mes = ano_mes.replace(day=1)

        # Verificar se já existe
        orcamento = ReceitaOrcamento.query.filter_by(
            item_receita_id=item_receita_id,
            mes_referencia=ano_mes
        ).first()

        if orcamento:
            # Atualizar
            orcamento.valor_esperado = valor_previsto
            orcamento.periodicidade = periodicidade
            if observacoes:
                orcamento.observacoes = observacoes
        else:
            # Criar novo
            orcamento = ReceitaOrcamento(
                item_receita_id=item_receita_id,
                mes_referencia=ano_mes,
                valor_esperado=valor_previsto,
                periodicidade=periodicidade,
                observacoes=observacoes
            )
            db.session.add(orcamento)

        db.session.commit()
        return orcamento

    @staticmethod
    def gerar_orcamento_recorrente(item_receita_id, data_inicio, data_fim,
                                   valor_mensal, periodicidade='MENSAL_FIXA'):
        """
        Gera projeções mensais automáticas para um período
        Útil para salários e gratificações fixas

        Args:
            item_receita_id (int): ID da fonte
            data_inicio (str ou date): Data de início (YYYY-MM-01)
            data_fim (str ou date): Data de fim (YYYY-MM-01)
            valor_mensal (float): Valor mensal fixo
            periodicidade (str): Tipo de periodicidade

        Returns:
            list[ReceitaOrcamento]: Lista de orçamentos criados
        """
        # Converter strings para date
        if isinstance(data_inicio, str):
            data_inicio = datetime.strptime(data_inicio[:10], '%Y-%m-%d').date()
        if isinstance(data_fim, str):
            data_fim = datetime.strptime(data_fim[:10], '%Y-%m-%d').date()

        # Garantir primeiro dia do mês
        data_inicio = data_inicio.replace(day=1)
        data_fim = data_fim.replace(day=1)

        orcamentos = []
        mes_atual = data_inicio

        while mes_atual <= data_fim:
            orcamento = ReceitaService.criar_ou_atualizar_orcamento_mensal(
                item_receita_id=item_receita_id,
                ano_mes=mes_atual,
                valor_previsto=valor_mensal,
                periodicidade=periodicidade
            )
            orcamentos.append(orcamento)

            # Próximo mês
            mes_atual = mes_atual + relativedelta(months=1)

        return orcamentos

    @staticmethod
    def obter_orcamentos_por_ano(ano):
        """
        Retorna todos os orçamentos de um ano específico

        Args:
            ano (int): Ano

        Returns:
            list[ReceitaOrcamento]: Lista de orçamentos
        """
        data_inicio = date(ano, 1, 1)
        data_fim = date(ano, 12, 31)

        return ReceitaOrcamento.query.filter(
            ReceitaOrcamento.mes_referencia >= data_inicio,
            ReceitaOrcamento.mes_referencia <= data_fim
        ).order_by(ReceitaOrcamento.mes_referencia, ReceitaOrcamento.item_receita_id).all()

    # ========================================================================
    # REGISTRO DE RECEITAS REALIZADAS
    # ========================================================================

    @staticmethod
    def registrar_receita_realizada(dados_receita):
        """
        Registra uma receita efetivamente recebida

        Args:
            dados_receita (dict):
                - item_receita_id (int): ID da fonte
                - data_recebimento (str ou date): Data do recebimento
                - valor_recebido (float): Valor recebido
                - competencia (str ou date): Mês de referência
                - descricao (str, opcional)
                - conta_origem_id (int, opcional)
                - observacoes (str, opcional)

        Returns:
            ReceitaRealizada: Receita registrada
        """
        # Validações
        if not dados_receita.get('item_receita_id'):
            raise ValueError('item_receita_id é obrigatório')

        if not dados_receita.get('data_recebimento'):
            raise ValueError('data_recebimento é obrigatório')

        if not dados_receita.get('valor_recebido'):
            raise ValueError('valor_recebido é obrigatório')

        # Converter datas
        data_recebimento = dados_receita['data_recebimento']
        if isinstance(data_recebimento, str):
            data_recebimento = datetime.strptime(data_recebimento[:10], '%Y-%m-%d').date()

        competencia = dados_receita.get('competencia')
        if competencia:
            if isinstance(competencia, str):
                competencia = datetime.strptime(competencia[:10], '%Y-%m-%d').date()
            competencia = competencia.replace(day=1)
        else:
            # Se não informada, usa o mês do recebimento
            competencia = data_recebimento.replace(day=1)

        # Procurar orçamento correspondente
        orcamento = ReceitaOrcamento.query.filter_by(
            item_receita_id=dados_receita['item_receita_id'],
            mes_referencia=competencia
        ).first()

        # Criar receita realizada
        receita = ReceitaRealizada(
            item_receita_id=dados_receita['item_receita_id'],
            data_recebimento=data_recebimento,
            valor_recebido=dados_receita['valor_recebido'],
            mes_referencia=competencia,
            conta_origem_id=dados_receita.get('conta_origem_id'),
            descricao=dados_receita.get('descricao', ''),
            orcamento_id=orcamento.id if orcamento else None,
            observacoes=dados_receita.get('observacoes', '')
        )

        db.session.add(receita)
        db.session.commit()

        return receita

    @staticmethod
    def atualizar_receita_realizada(id, dados_receita):
        """
        Atualiza uma receita realizada existente.

        Args:
            id (int): ID da receita realizada
            dados_receita (dict): mesmos campos do registrar_receita_realizada

        Returns:
            ReceitaRealizada | None: Receita atualizada ou None se não encontrada
        """
        receita = ReceitaRealizada.query.get(id)
        if not receita:
            return None

        if not dados_receita.get('item_receita_id'):
            raise ValueError('item_receita_id é obrigatório')

        if not dados_receita.get('data_recebimento'):
            raise ValueError('data_recebimento é obrigatório')

        if not dados_receita.get('valor_recebido'):
            raise ValueError('valor_recebido é obrigatório')

        data_recebimento = dados_receita['data_recebimento']
        if isinstance(data_recebimento, str):
            data_recebimento = datetime.strptime(data_recebimento[:10], '%Y-%m-%d').date()

        competencia = dados_receita.get('competencia')
        if competencia:
            if isinstance(competencia, str):
                competencia = datetime.strptime(competencia[:10], '%Y-%m-%d').date()
            competencia = competencia.replace(day=1)
        else:
            competencia = data_recebimento.replace(day=1)

        orcamento = ReceitaOrcamento.query.filter_by(
            item_receita_id=dados_receita['item_receita_id'],
            mes_referencia=competencia
        ).first()

        receita.item_receita_id = dados_receita['item_receita_id']
        receita.data_recebimento = data_recebimento
        receita.valor_recebido = dados_receita['valor_recebido']
        receita.mes_referencia = competencia
        receita.conta_origem_id = dados_receita.get('conta_origem_id')
        receita.descricao = dados_receita.get('descricao', '')
        receita.orcamento_id = orcamento.id if orcamento else None
        receita.observacoes = dados_receita.get('observacoes', '')

        db.session.commit()
        return receita

    @staticmethod
    def listar_receitas_realizadas(ano_mes=None, item_receita_id=None):
        """
        Lista receitas realizadas com filtros opcionais

        Args:
            ano_mes (str ou date, opcional): Filtrar por competência
            item_receita_id (int, opcional): Filtrar por fonte

        Returns:
            list[ReceitaRealizada]: Lista de receitas
        """
        query = ReceitaRealizada.query

        if ano_mes:
            if isinstance(ano_mes, str):
                ano_mes = datetime.strptime(ano_mes[:10], '%Y-%m-%d').date()
            ano_mes = ano_mes.replace(day=1)
            query = query.filter_by(mes_referencia=ano_mes)

        if item_receita_id:
            query = query.filter_by(item_receita_id=item_receita_id)

        return query.order_by(ReceitaRealizada.data_recebimento.desc()).all()

    # ========================================================================
    # ANÁLISES E RELATÓRIOS (KPIs)
    # ========================================================================

    @staticmethod
    def get_resumo_receitas_por_mes(ano):
        """
        Retorna resumo consolidado de receitas por mês do ano
        Compara previsto vs realizado

        Args:
            ano (int): Ano

        Returns:
            dict: Resumo por mês e por tipo
        """
        data_inicio = date(ano, 1, 1)
        data_fim = date(ano, 12, 31)

        # Buscar orçamentos
        orcamentos = db.session.query(
            extract('month', ReceitaOrcamento.mes_referencia).label('mes'),
            ItemReceita.tipo,
            func.sum(ReceitaOrcamento.valor_esperado).label('total_previsto')
        ).join(ItemReceita).filter(
            ReceitaOrcamento.mes_referencia >= data_inicio,
            ReceitaOrcamento.mes_referencia <= data_fim
        ).group_by('mes', ItemReceita.tipo).all()

        # Buscar realizadas
        realizadas = db.session.query(
            extract('month', ReceitaRealizada.mes_referencia).label('mes'),
            ItemReceita.tipo,
            func.sum(ReceitaRealizada.valor_recebido).label('total_recebido')
        ).join(ItemReceita).filter(
            ReceitaRealizada.mes_referencia >= data_inicio,
            ReceitaRealizada.mes_referencia <= data_fim
        ).group_by('mes', ItemReceita.tipo).all()

        # Organizar dados
        resumo = {}
        for mes in range(1, 13):
            resumo[mes] = {
                'mes': mes,
                'previsto': {},
                'realizado': {},
                'total_previsto': 0,
                'total_realizado': 0
            }

        # Preencher previstos
        for orc in orcamentos:
            mes = int(orc.mes)
            tipo = orc.tipo
            valor = float(orc.total_previsto or 0)
            resumo[mes]['previsto'][tipo] = valor
            resumo[mes]['total_previsto'] += valor

        # Preencher realizados
        for real in realizadas:
            mes = int(real.mes)
            tipo = real.tipo
            valor = float(real.total_recebido or 0)
            resumo[mes]['realizado'][tipo] = valor
            resumo[mes]['total_realizado'] += valor

        return resumo

    @staticmethod
    def get_confiabilidade_receitas(ano_mes_ini, ano_mes_fim):
        """
        Calcula percentual de confiabilidade das receitas
        % recebido / previsto por fonte e consolidado

        Args:
            ano_mes_ini (str ou date): Início do período
            ano_mes_fim (str ou date): Fim do período

        Returns:
            dict: Confiabilidade por item e total
        """
        # Converter datas
        if isinstance(ano_mes_ini, str):
            ano_mes_ini = datetime.strptime(ano_mes_ini[:10], '%Y-%m-%d').date()
        if isinstance(ano_mes_fim, str):
            ano_mes_fim = datetime.strptime(ano_mes_fim[:10], '%Y-%m-%d').date()

        ano_mes_ini = ano_mes_ini.replace(day=1)
        ano_mes_fim = ano_mes_fim.replace(day=1)

        # Buscar dados agregados por item
        previstos = db.session.query(
            ReceitaOrcamento.item_receita_id,
            ItemReceita.nome,
            ItemReceita.tipo,
            func.sum(ReceitaOrcamento.valor_esperado).label('total_previsto')
        ).join(ItemReceita).filter(
            ReceitaOrcamento.mes_referencia >= ano_mes_ini,
            ReceitaOrcamento.mes_referencia <= ano_mes_fim
        ).group_by(
            ReceitaOrcamento.item_receita_id,
            ItemReceita.nome,
            ItemReceita.tipo
        ).all()

        realizados = db.session.query(
            ReceitaRealizada.item_receita_id,
            func.sum(ReceitaRealizada.valor_recebido).label('total_recebido')
        ).filter(
            ReceitaRealizada.mes_referencia >= ano_mes_ini,
            ReceitaRealizada.mes_referencia <= ano_mes_fim
        ).group_by(ReceitaRealizada.item_receita_id).all()

        # Mapear realizados
        map_realizados = {r.item_receita_id: float(r.total_recebido or 0) for r in realizados}

        # Calcular confiabilidade
        itens = []
        total_previsto = 0
        total_recebido = 0

        for prev in previstos:
            previsto = float(prev.total_previsto or 0)
            recebido = map_realizados.get(prev.item_receita_id, 0)

            percentual = (recebido / previsto * 100) if previsto > 0 else 0

            itens.append({
                'item_receita_id': prev.item_receita_id,
                'nome': prev.nome,
                'tipo': prev.tipo,
                'previsto': previsto,
                'recebido': recebido,
                'diferenca': recebido - previsto,
                'percentual_confiabilidade': round(percentual, 2)
            })

            total_previsto += previsto
            total_recebido += recebido

        percentual_geral = (total_recebido / total_previsto * 100) if total_previsto > 0 else 0

        return {
            'itens': itens,
            'total': {
                'previsto': total_previsto,
                'recebido': total_recebido,
                'diferenca': total_recebido - total_previsto,
                'percentual_confiabilidade': round(percentual_geral, 2)
            }
        }

    @staticmethod
    def get_detalhe_receitas_item(item_receita_id, ano):
        """
        Mostra todas as projeções e realizações de um item específico

        Args:
            item_receita_id (int): ID da fonte
            ano (int): Ano

        Returns:
            dict: Detalhe mês a mês
        """
        data_inicio = date(ano, 1, 1)
        data_fim = date(ano, 12, 31)

        # Buscar item
        item = ItemReceita.query.get(item_receita_id)
        if not item:
            raise ValueError('Fonte de receita não encontrada')

        # Buscar orçamentos
        orcamentos = ReceitaOrcamento.query.filter(
            ReceitaOrcamento.item_receita_id == item_receita_id,
            ReceitaOrcamento.mes_referencia >= data_inicio,
            ReceitaOrcamento.mes_referencia <= data_fim
        ).order_by(ReceitaOrcamento.mes_referencia).all()

        # Buscar realizadas
        realizadas = ReceitaRealizada.query.filter(
            ReceitaRealizada.item_receita_id == item_receita_id,
            ReceitaRealizada.mes_referencia >= data_inicio,
            ReceitaRealizada.mes_referencia <= data_fim
        ).order_by(ReceitaRealizada.mes_referencia, ReceitaRealizada.data_recebimento).all()

        # Organizar por mês
        meses = {}
        for mes in range(1, 13):
            meses[mes] = {
                'mes': mes,
                'ano_mes': date(ano, mes, 1).strftime('%Y-%m'),
                'previsto': 0,
                'recebido': 0,
                'receitas': []
            }

        # Preencher previstos
        for orc in orcamentos:
            mes = orc.mes_referencia.month
            meses[mes]['previsto'] = float(orc.valor_esperado)

        # Preencher realizados
        for real in realizadas:
            mes = real.mes_referencia.month
            valor = float(real.valor_recebido)
            meses[mes]['recebido'] += valor
            meses[mes]['receitas'].append({
                'id': real.id,
                'descricao': real.descricao,
                'valor': valor,
                'data_recebimento': real.data_recebimento.strftime('%Y-%m-%d')
            })

        return {
            'item': item.to_dict(),
            'meses': list(meses.values())
        }
