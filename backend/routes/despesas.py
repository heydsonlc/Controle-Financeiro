"""
Rotas para gerenciamento de Despesas (Itens de Despesa)
"""
from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
from decimal import Decimal
import json
import logging
from dateutil.relativedelta import relativedelta
from sqlalchemy import func, or_

try:
    from backend.models import db, ItemDespesa, Categoria, LancamentoAgregado, CartaoCategoriaLimite, Conta
    from backend.services.cartao_service import CartaoService
    from backend.services.categoria_cartao_service import CategoriaCartaoService
    from backend.services.perfil_financeiro_service import PerfilFinanceiroService
    from backend.routes.dashboard import _calcular_receitas_mes
except ImportError:
    from models import db, ItemDespesa, Categoria, LancamentoAgregado, CartaoCategoriaLimite, Conta
    from services.cartao_service import CartaoService
    from services.categoria_cartao_service import CategoriaCartaoService
    from services.perfil_financeiro_service import PerfilFinanceiroService
    from routes.dashboard import _calcular_receitas_mes

despesas_bp = Blueprint('despesas', __name__, url_prefix='/api/despesas')
logger = logging.getLogger(__name__)


def _internal_error(contexto='despesas'):
    logger.exception('Erro interno em %s', contexto)
    return jsonify({'success': False, 'error': 'Erro interno ao processar requisicao'}), 500


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


def _dia_semana_ui_para_python(value):
    dia_semana = _to_int(value)
    if dia_semana is None:
        return None
    # UI e storage usam 0=domingo; date.weekday() usa 0=segunda.
    return (dia_semana - 1) % 7


def _descricao_recorrencia_com_data(item, data_venc):
    return f"{item.nome} - {data_venc.strftime('%d/%m')}"


def _conta_recorrente_automatica_pendente(conta, item):
    descricao = conta.descricao or ''
    return (
        conta.status_pagamento == 'Pendente'
        and conta.data_pagamento is None
        and not conta.is_fatura_cartao
        and descricao.startswith(f"{item.nome} - ")
    )


def _ciclo_recorrencia(data_venc, datas_esperadas, intervalo):
    dias_ciclo = max(int(intervalo or 1), 1) * 7
    for data_esperada in datas_esperadas:
        if data_esperada <= data_venc < data_esperada + timedelta(days=dias_ciclo):
            return data_esperada
    return None


def _reconciliar_ocorrencias_semanais(item, datas_esperadas, inicio_janela, data_fim_base, intervalo):
    if not datas_esperadas:
        return

    datas_esperadas = sorted(set(datas_esperadas))
    datas_set = set(datas_esperadas)
    contas = _query_contas().filter(
        Conta.item_despesa_id == item.id,
        Conta.data_vencimento >= inicio_janela,
        Conta.data_vencimento <= data_fim_base,
        or_(
            Conta.is_fatura_cartao == False,  # noqa: E712
            Conta.is_fatura_cartao.is_(None)
        )
    ).order_by(Conta.data_vencimento.asc(), Conta.id.asc()).all()

    ocupadas = {conta.data_vencimento for conta in contas if conta.data_vencimento in datas_set}
    usadas = set()

    for data_esperada in datas_esperadas:
        if data_esperada in ocupadas:
            continue

        candidata = next((
            conta for conta in contas
            if conta.id not in usadas
            and conta.data_vencimento not in datas_set
            and _conta_recorrente_automatica_pendente(conta, item)
            and _ciclo_recorrencia(conta.data_vencimento, [data_esperada], intervalo) == data_esperada
        ), None)
        if not candidata:
            continue

        candidata.data_vencimento = data_esperada
        candidata.mes_referencia = data_esperada.replace(day=1)
        candidata.descricao = _descricao_recorrencia_com_data(item, data_esperada)
        usadas.add(candidata.id)
        ocupadas.add(data_esperada)

    for conta in contas:
        if conta.id in usadas or conta.data_vencimento in datas_set:
            continue
        if not _conta_recorrente_automatica_pendente(conta, item):
            continue
        if _ciclo_recorrencia(conta.data_vencimento, datas_esperadas, intervalo):
            db.session.delete(conta)


def _perfil_id():
    return PerfilFinanceiroService.obter_perfil_ativo_id()


def _query_itens():
    return PerfilFinanceiroService.aplicar_perfil_query(ItemDespesa.query, ItemDespesa)


def _query_contas():
    return PerfilFinanceiroService.aplicar_perfil_query(Conta.query, Conta)


def _query_lancamentos():
    return PerfilFinanceiroService.aplicar_perfil_query(LancamentoAgregado.query, LancamentoAgregado)


def gerar_execucao_despesa_recorrente(item_despesa_id, meses_futuros=1, mes_referencia=None):
    """
    Orquestrador Ãºnico de recorrÃªncia:
    - Se meio_pagamento == 'cartao' â†’ gera LancamentoAgregado
    - Caso contrÃ¡rio â†’ gera Conta

    IMPORTANTE: esta funÃ§Ã£o NÃƒO faz commit; o caller controla a transaÃ§Ã£o.
    """
    item = _query_itens().filter(ItemDespesa.id == item_despesa_id).first()
    if not item:
        raise ValueError('ItemDespesa nÃ£o encontrado')
    if not item.recorrente:
        return []

    if item.meio_pagamento == 'cartao':
        if not item.cartao_id:
            return []
        return gerar_lancamentos_cartao_recorrente(item.id, meses_futuros=meses_futuros, mes_referencia=mes_referencia)

    return gerar_contas_despesa_recorrente(item.id, meses_futuros=meses_futuros, mes_referencia=mes_referencia)


def calcular_competencia(data_vencimento):
    """
    Calcula o mÃªs de competÃªncia (mÃªs do salÃ¡rio que paga a despesa)
    Regra: A competÃªncia Ã© o mÃªs anterior ao vencimento

    Exemplo:
    - Vencimento em 15/12/2025 â†’ CompetÃªncia: 11/2025 (Novembro)
    - Vencimento em 05/01/2026 â†’ CompetÃªncia: 12/2025 (Dezembro)

    Args:
        data_vencimento: objeto date ou None

    Returns:
        String no formato 'YYYY-MM' ou None
    """
    if not data_vencimento:
        return None

    # Subtrai 1 mÃªs da data de vencimento
    mes_competencia = data_vencimento - relativedelta(months=1)
    return mes_competencia.strftime('%Y-%m')


def _calcular_totais_fatura_cartao_previsto(cartao_id, competencia):
    """
    Retorna (total_previsto, total_executado) para a fatura de um cartÃ£o no mÃªs.

    DefiniÃ§Ã£o:
    - total_executado = soma de TODOS os LancamentoAgregado do mÃªs (com e sem categoria)
    - total_previsto = total_executado + soma(max(0, orcado_categoria - gasto_categoria))
      (equivalente a somar max(orcado, gasto) por categoria sem duplo-contar os gastos)
    """
    comp = competencia.replace(day=1)

    total_executado = db.session.query(
        func.coalesce(func.sum(LancamentoAgregado.valor), 0)
    ).filter(
        LancamentoAgregado.cartao_id == cartao_id,
        PerfilFinanceiroService.condicao_perfil(LancamentoAgregado),
        LancamentoAgregado.mes_fatura == comp
    ).scalar()
    total_executado = float(total_executado or 0)

    limites = CartaoCategoriaLimite.query.filter_by(cartao_id=cartao_id, ativo=True).all()
    if not limites:
        return total_executado, total_executado

    categorias_cartao_ids = [limite.categoria_cartao_id for limite in limites]

    gastos_por_categoria = dict(
        db.session.query(
            LancamentoAgregado.categoria_cartao_id,
            func.coalesce(func.sum(LancamentoAgregado.valor), 0)
        ).filter(
            LancamentoAgregado.cartao_id == cartao_id,
            PerfilFinanceiroService.condicao_perfil(LancamentoAgregado),
            LancamentoAgregado.mes_fatura == comp,
            LancamentoAgregado.categoria_cartao_id.in_(categorias_cartao_ids)
        ).group_by(
            LancamentoAgregado.categoria_cartao_id
        ).all()
    )

    limites_por_categoria = {
        limite.categoria_cartao_id: float(limite.limite_mensal or 0)
        for limite in limites
    }

    complemento_limite = 0.0
    for categoria_cartao_id, limite_mensal in limites_por_categoria.items():
        gasto = float(gastos_por_categoria.get(categoria_cartao_id, 0) or 0)
        if limite_mensal > gasto:
            complemento_limite += (limite_mensal - gasto)

    total_previsto = total_executado + complemento_limite
    return total_previsto, total_executado


@despesas_bp.route('/', methods=['GET'])
def listar_despesas():
    """
    Lista todas as despesas, incluindo faturas virtuais de cartÃ£o

    Regra de agrupamento:
    - Despesas tipo='Simples': aparecem individualmente
    - Despesas tipo='Agregador' (cartÃµes): faturas virtuais (Conta.is_fatura_cartao=True)
      mostram valor_planejado (pendente) ou valor_executado (pago)
    """
    try:
        # âœ… LAZY GENERATION: Preencher lacunas atÃ© o mÃªs navegado + 1 mÃªs futuro
        # âš ï¸ Dashboard NÃƒO deve passar mes_arg - apenas navegaÃ§Ã£o explÃ­cita por mÃªs
        mes_arg = request.args.get('mes_referencia') or request.args.get('mes')

        if mes_arg:
            try:
                mes_referencia = datetime.strptime(f"{mes_arg}-01", "%Y-%m-%d").date()
                despesas_recorrentes = _query_itens().filter_by(recorrente=True).all()

                for desp in despesas_recorrentes:
                    if not desp.data_vencimento:
                        continue

                    # Calcular quantos meses entre o inÃ­cio da despesa e o mÃªs navegado
                    inicio = desp.data_vencimento.replace(day=1)

                    # Calcular diferenÃ§a em meses
                    meses_diferenca = (mes_referencia.year - inicio.year) * 12 + \
                                     (mes_referencia.month - inicio.month)

                    # Garantir que preencha ATÃ‰ o mÃªs navegado + 1 mÃªs futuro (UX suave)
                    # Se meses_diferenca < 0, a despesa Ã© futura, entÃ£o gerar apenas se for o mÃªs
                    # Se meses_diferenca >= 0, gerar atÃ© o mÃªs navegado + 1
                    if meses_diferenca >= 0:
                        meses_futuros = meses_diferenca + 2  # MÃªs navegado + prÃ³ximo mÃªs
                    else:
                        meses_futuros = 1  # Despesa futura, gerar apenas se for o mÃªs

                    # Gerar todas as contas necessÃ¡rias (preenchendo lacunas)
                    # mes_referencia=None faz gerar a partir da data_vencimento
                    gerar_execucao_despesa_recorrente(
                        desp.id,
                        meses_futuros=meses_futuros,
                        mes_referencia=None
                    )

                # âœ… LAZY GENERATION (CARTÃ•ES): garantir que a fatura exista
                # mesmo sem lanÃ§amentos, para o mÃªs navegado (+1 mÃªs futuro)
                competencias_fatura = [
                    mes_referencia.replace(day=1),
                    (mes_referencia + relativedelta(months=1)).replace(day=1),
                ]
                cartoes_ativos = _query_itens().filter_by(tipo='Agregador', ativo=True).all()
                for cartao in cartoes_ativos:
                    for comp in competencias_fatura:
                        try:
                            CartaoService.get_or_create_fatura(cartao.id, comp)
                        except Exception:
                            logger.warning(
                                'Falha ao garantir fatura virtual no lazy generation cartao_id=%s competencia=%s',
                                cartao.id,
                                comp,
                                exc_info=True,
                            )
                            continue

                db.session.commit()
            except Exception:
                db.session.rollback()
                # Continua em modo degradado, mas com rastreabilidade
                logger.warning('Falha no lazy generation de despesas; seguindo com dados existentes', exc_info=True)

        # DA-AUTO-STATUS-1: baixar débitos automáticos vencidos com saldo suficiente
        try:
            from backend.services.debito_automatico_service import executar_baixa_debito_automatico
        except ImportError:
            from services.debito_automatico_service import executar_baixa_debito_automatico
        try:
            executar_baixa_debito_automatico(perfil_id=_perfil_id())
        except Exception:
            logger.warning('Falha na baixa automática de débitos automáticos; seguindo', exc_info=True)

        resultado = []

        # 1. Buscar CONTAS que NÃƒO sÃ£o faturas de cartÃ£o de crÃ©dito
        # (Despesas simples, consÃ³rcios, financiamentos, etc)
        from sqlalchemy import extract, or_

        # Buscar contas que:
        # - NÃƒO sÃ£o fatura de cartÃ£o (is_fatura_cartao = False ou NULL)
        # IMPORTANTE: NÃ£o filtrar por ItemDespesa.ativo pois consÃ³rcios/financiamentos
        # podem ter ItemDespesa inativo mas geram Contas ativas
        contas_nao_cartao = db.session.query(Conta).outerjoin(
            ItemDespesa, Conta.item_despesa_id == ItemDespesa.id
        ).outerjoin(
            Categoria, ItemDespesa.categoria_id == Categoria.id
        ).filter(
            PerfilFinanceiroService.condicao_perfil(Conta),
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
                'conta_bancaria_id': getattr(conta, 'conta_bancaria_id', None),
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
                'meio_pagamento': item.meio_pagamento if item else ('debito' if conta.debito_automatico else None),
                'debito_automatico': conta.debito_automatico,
                'numero_parcela': conta.numero_parcela,
                'total_parcelas': conta.total_parcelas,
                'agrupado': False,
                'ativo': True,
                'is_fatura_cartao': False
            }
            resultado.append(conta_dict)

        # 2. Buscar FATURAS VIRTUAIS de cartÃ£o de crÃ©dito (Conta.is_fatura_cartao = True)
        faturas_cartao = db.session.query(Conta).outerjoin(
            ItemDespesa, Conta.item_despesa_id == ItemDespesa.id
        ).outerjoin(
            Categoria, ItemDespesa.categoria_id == Categoria.id
        ).filter(
            PerfilFinanceiroService.condicao_perfil(Conta),
            Conta.is_fatura_cartao == True
        ).order_by(
            Conta.data_vencimento.desc()
        ).all()

        # Converter cada fatura de cartÃ£o para formato do frontend
        for fatura in faturas_cartao:
            item = fatura.item_despesa
            categoria = item.categoria if item else None

            # REGRA: Card da fatura:
            # - Se PENDENTE â†’ exibe TOTAL PREVISTO da fatura
            # - Se PAGA â†’ exibe TOTAL EXECUTADO
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
                'tipo': 'cartao',  # â† CORRIGIDO: era 'Agregador', mas frontend espera 'cartao'
                'valor': valor_exibido,
                'conta_bancaria_id': getattr(fatura, 'conta_bancaria_id', None),
                'financiamento_parcela_id': None,
                'valor_fatura': valor_exibido,  # â† ADICIONADO: campo que frontend espera ler
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
                'meio_pagamento': 'cartao',
                'debito_automatico': fatura.debito_automatico,
                'numero_parcela': None,
                'total_parcelas': None,
                'agrupado': True,  # Flag para indicar que Ã© fatura de cartÃ£o
                'ativo': True,
                'is_fatura_cartao': True,
                'cartao_id': item.id if item else None
            }
            resultado.append(fatura_dict)

        # Ordenar por data de vencimento (mais recente primeiro)
        resultado.sort(key=lambda x: x.get('data_vencimento', ''), reverse=True)

        # ============================================================
        # SIDEBAR SUMMARY DATA — apenas leitura dos dados ja buscados
        # Nenhuma logica de pagamento e alterada aqui
        # ============================================================
        hoje = datetime.now().date()
        sete_dias = hoje + timedelta(days=7)

        # Filtrar apenas o mes de referencia para o sidebar (resultado contem todos os meses)
        mes_ref_dt = datetime.strptime(f"{mes_arg}-01", "%Y-%m-%d").date() if mes_arg else hoje.replace(day=1)
        mes_ref_str = mes_ref_dt.strftime('%Y-%m')
        resultado_mes = [d for d in resultado if d.get('mes_competencia', '') == mes_ref_str]

        total_mes = sum(float(d.get('valor', 0)) for d in resultado_mes)
        total_pendentes = sum(float(d.get('valor', 0)) for d in resultado_mes if not d.get('pago'))
        total_pagas = sum(float(d.get('valor', 0)) for d in resultado_mes if d.get('pago'))

        # Vencendo em 7 dias (pendentes com vencimento entre hoje e hoje+7, todos os meses)
        vencendo_7d = [
            d for d in resultado
            if not d.get('pago')
            and d.get('data_vencimento')
            and hoje.isoformat() <= d['data_vencimento'] <= sete_dias.isoformat()
        ]
        vencendo_7d_count = len(vencendo_7d)
        vencendo_7d_valor = sum(float(d.get('valor', 0)) for d in vencendo_7d)

        # Recorrentes do mes de referencia
        recorrentes = [d for d in resultado_mes if d.get('recorrente') and not d.get('is_fatura_cartao')]
        recorrentes_count = len(recorrentes)
        recorrentes_valor = sum(float(d.get('valor', 0)) for d in recorrentes)

        # Cartoes / faturas do mes de referencia
        cartoes_faturas = [d for d in resultado_mes if d.get('is_fatura_cartao')]
        cartoes_count = len(cartoes_faturas)
        cartoes_valor = sum(float(d.get('valor', 0)) for d in cartoes_faturas)

        # Composicao por categoria do mes de referencia — faturas de cartao ficam fora
        composicao_categoria = {}
        for d in resultado_mes:
            if d.get('is_fatura_cartao'):
                continue
            cat = d.get('categoria')
            if cat:
                nome_cat = cat.get('nome', 'Sem categoria')
                cor_cat = cat.get('cor', '#6e6e73')
            else:
                nome_cat = 'Sem categoria'
                cor_cat = '#6e6e73'
            if nome_cat not in composicao_categoria:
                composicao_categoria[nome_cat] = {'valor': 0.0, 'cor': cor_cat}
            composicao_categoria[nome_cat]['valor'] += float(d.get('valor', 0))

        composicao_lista = sorted(
            [{'nome': k, 'valor': v['valor'], 'cor': v['cor']} for k, v in composicao_categoria.items()],
            key=lambda x: x['valor'],
            reverse=True
        )

        # Proximos vencimentos (pendentes nao-cartao com vencimento a partir de hoje, limite 5)
        proximos = sorted(
            [d for d in resultado
             if not d.get('pago')
             and d.get('data_vencimento')
             and d['data_vencimento'] >= hoje.isoformat()
             and not d.get('is_fatura_cartao')],
            key=lambda x: x['data_vencimento']
        )[:5]
        proximos_vencimentos = [
            {
                'id': d['id'],
                'nome': d['nome'],
                'valor': d['valor'],
                'data_vencimento': d['data_vencimento'],
                'status_pagamento': d.get('status_pagamento', 'Pendente'),
                'categoria': d.get('categoria', {}).get('nome', '') if d.get('categoria') else '',
                'tipo': d.get('tipo', ''),
            }
            for d in proximos
        ]

        receitas_mes_val = float(_calcular_receitas_mes(mes_ref_dt.month, mes_ref_dt.year))

        sidebar = {
            'total_mes': total_mes,
            'total_pendentes': total_pendentes,
            'total_pagas': total_pagas,
            'vencendo_7d_count': vencendo_7d_count,
            'vencendo_7d_valor': vencendo_7d_valor,
            'recorrentes_count': recorrentes_count,
            'recorrentes_valor': recorrentes_valor,
            'cartoes_count': cartoes_count,
            'cartoes_valor': cartoes_valor,
            'composicao_categoria': composicao_lista,
            'proximos_vencimentos': proximos_vencimentos,
            'receitas_mes': receitas_mes_val,
            'saldo_mes': receitas_mes_val - total_mes,
        }

        return jsonify({
            'success': True,
            'data': resultado,
            'sidebar': sidebar,
        })
    except Exception:
        return _internal_error('despesas')


@despesas_bp.route('/<int:id>', methods=['GET'])
def obter_despesa(id):
    """ObtÃ©m uma conta especÃ­fica"""
    try:
        # Buscar na tabela Conta (nÃ£o ItemDespesa)
        conta = _query_contas().filter(Conta.id == id).first()
        if not conta:
            return jsonify({
                'success': False,
                'error': 'Despesa nÃ£o encontrada'
            }), 404

        # Buscar ItemDespesa relacionado para pegar informaÃ§Ãµes adicionais
        item_despesa = None
        if conta.item_despesa_id:
            item_despesa = _query_itens().filter(ItemDespesa.id == conta.item_despesa_id).first()

        # Buscar categoria se existir — Categoria de Despesa é global
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
    except Exception:
        return _internal_error('despesas')


@despesas_bp.route('/', methods=['POST'])
def criar_despesa():
    """Cria uma nova despesa"""
    try:
        # ==========================================================
        # CORREÃ‡ÃƒO DEFINITIVA â€” LEITURA CORRETA DO PAYLOAD
        # SUPORTA JSON E FORM-DATA
        # ==========================================================

        dados = _ler_payload_request()

        # ValidaÃ§Ãµes
        if not dados.get('nome'):
            return jsonify({
                'success': False,
                'error': 'Nome Ã© obrigatÃ³rio'
            }), 400

        if not dados.get('valor'):
            return jsonify({
                'success': False,
                'error': 'Valor Ã© obrigatÃ³rio'
            }), 400

        if not dados.get('categoria_id'):
            return jsonify({
                'success': False,
                'error': 'Categoria Ã© obrigatÃ³ria'
            }), 400

        # Verificar se categoria existe — Categoria de Despesa é global
        categoria = Categoria.query.get(dados.get('categoria_id'))
        if not categoria:
            return jsonify({
                'success': False,
                'error': 'Categoria nÃ£o encontrada'
            }), 404

        # Converter datas
        data_vencimento = None
        if dados.get('data_vencimento'):
            try:
                data_vencimento = datetime.strptime(dados['data_vencimento'], '%Y-%m-%d').date()
            except ValueError:
                return jsonify({
                    'success': False,
                    'error': 'Formato de data invÃ¡lido. Use YYYY-MM-DD'
                }), 400

        data_pagamento = None
        if dados.get('data_pagamento'):
            try:
                data_pagamento = datetime.strptime(dados['data_pagamento'], '%Y-%m-%d').date()
            except ValueError:
                return jsonify({
                    'success': False,
                    'error': 'Formato de data de pagamento invÃ¡lido. Use YYYY-MM-DD'
                }), 400

        # Calcular competÃªncia automaticamente se nÃ£o fornecida
        mes_competencia = dados.get('mes_competencia')
        if not mes_competencia and data_vencimento:
            mes_competencia = calcular_competencia(data_vencimento)

        # Criar despesa
        despesa = ItemDespesa(
            perfil_financeiro_id=_perfil_id(),
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
            tipo='Simples'  # Define o tipo como 'Simples' por padrÃ£o
        )

        db.session.add(despesa)
        db.session.flush()  # Garante despesa.id antes de qualquer lÃ³gica derivada

        # ==========================================================
        # PERSISTÃŠNCIA CORRETA â€” PAGAMENTO VIA CARTÃƒO
        # ==========================================================

        meio_pagamento = _normalizar_meio_pagamento(dados.get('meio_pagamento'))
        despesa.meio_pagamento = meio_pagamento

        # Se for despesa recorrente paga via cartÃ£o de crÃ©dito
        if bool(despesa.recorrente) and meio_pagamento == 'cartao':
            cartao_id = _to_int(dados.get('cartao_id'))

            # ValidaÃ§Ã£o mÃ­nima de integridade
            if not cartao_id:
                db.session.rollback()
                return jsonify({
                    'success': False,
                    'error': "cartao_id Ã© obrigatÃ³rio quando meio_pagamento = 'cartao'."
                }), 400

            despesa.cartao_id = cartao_id
            despesa.item_agregado_id = None
            resolucao_cartao = CategoriaCartaoService.resolver_categoria_cartao_para_lancamento(
                cartao_id=cartao_id,
                categoria_id=despesa.categoria_id,
                categoria_cartao_id=None,
            )
            despesa.categoria_cartao_id = resolucao_cartao.get('categoria_cartao_id')
        else:
            # Garantir limpeza para outros meios de pagamento
            despesa.cartao_id = None
            despesa.item_agregado_id = None
            despesa.categoria_cartao_id = None

        try:
            if despesa.recorrente:
                # âœ… LAZY GENERATION: Gerar apenas o mÃªs inicial
                # O restante serÃ¡ gerado conforme o usuÃ¡rio navegar pelos meses
                gerar_execucao_despesa_recorrente(despesa.id, meses_futuros=1, mes_referencia=None)
            else:
                # Se NÃƒO for recorrente, criar UMA Conta imediatamente
                # Isso garante que a despesa apareÃ§a no histÃ³rico de lanÃ§amentos
                if data_vencimento:
                    mes_referencia = data_vencimento.replace(day=1)
                    status = 'Pago' if dados.get('pago') or data_pagamento else 'Pendente'

                    nova_conta = Conta(
                        perfil_financeiro_id=_perfil_id(),
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
        except Exception:
            db.session.rollback()
            return _internal_error('criar_despesa_recorrente')

        return jsonify({
            'success': True,
            'message': 'Despesa criada com sucesso',
            'data': despesa.to_dict()
        }), 201

    except Exception:
        db.session.rollback()
        return _internal_error('despesas')


@despesas_bp.route('/<int:id>', methods=['PUT'])
def atualizar_despesa(id):
    """Atualiza uma conta especÃ­fica"""
    try:
        # Buscar na tabela Conta (nÃ£o ItemDespesa)
        conta = _query_contas().filter(Conta.id == id).first()
        if not conta:
            return jsonify({
                'success': False,
                'error': 'Despesa nÃ£o encontrada'
            }), 404

        dados = request.get_json()

        # Atualizar campos bÃ¡sicos da Conta
        if 'descricao' in dados:
            conta.descricao = dados['descricao']

        if 'valor' in dados:
            conta.valor = float(dados['valor'])

        if 'data_vencimento' in dados and dados['data_vencimento']:
            try:
                conta.data_vencimento = datetime.strptime(dados['data_vencimento'], '%Y-%m-%d').date()
            except ValueError:
                logger.warning('Data de vencimento invalida na atualizacao da despesa id=%s', id)
                return jsonify({'success': False, 'error': 'Formato de data_vencimento invalido. Use YYYY-MM-DD'}), 400

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
                    logger.warning('Data de pagamento invalida na atualizacao da despesa id=%s', id)
                    return jsonify({'success': False, 'error': 'Formato de data_pagamento invalido. Use YYYY-MM-DD'}), 400
            else:
                conta.data_pagamento = None
                conta.status_pagamento = 'Pendente'

        # Atualizar status de pagamento se fornecido explicitamente
        if 'pago' in dados:
            if dados['pago']:
                conta.status_pagamento = 'Pago'
                # Se nÃ£o tem data de pagamento, usar data de vencimento
                if not conta.data_pagamento:
                    conta.data_pagamento = conta.data_vencimento
            else:
                conta.status_pagamento = 'Pendente'
                conta.data_pagamento = None

        db.session.commit()

        # ========================================================================
        # HOOK: Sincronizar pagamento com Financiamento (se aplicÃ¡vel)
        # ========================================================================
        # Se esta conta estÃ¡ vinculada a uma parcela de financiamento E foi marcada como paga,
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

    except Exception:
        db.session.rollback()
        return _internal_error('despesas')


@despesas_bp.route('/<int:id>_OLD', methods=['PUT'])
def atualizar_despesa_OLD(id):
    """[BACKUP] Atualiza uma despesa existente (Ãºnica ou com futuras) - VERSÃƒO ANTIGA"""
    try:
        despesa = _query_itens().filter(ItemDespesa.id == id).first()
        if not despesa:
            return jsonify({
                'success': False,
                'error': 'Despesa nÃ£o encontrada'
            }), 404

        dados = request.get_json()

        # Verificar se deve atualizar apenas esta ou incluir futuras
        tipo_edicao = request.args.get('tipo_edicao', 'unica')

        despesas_para_atualizar = [despesa]

        if tipo_edicao == 'futuras':
            # Atualizar esta despesa e todas as futuras do mesmo grupo
            if despesa.tipo == 'Consorcio':
                # Para consÃ³rcio, buscar parcelas futuras pelo nome base
                nome_base = despesa.nome.rsplit(' - Parcela ', 1)[0] if ' - Parcela ' in despesa.nome else despesa.nome
                mes_competencia_atual = despesa.mes_competencia

                # Buscar parcelas futuras do mesmo consÃ³rcio
                parcelas_futuras = _query_itens().filter(
                    ItemDespesa.tipo == 'Consorcio',
                    ItemDespesa.nome.like(f"{nome_base} - Parcela%"),
                    ItemDespesa.mes_competencia >= mes_competencia_atual,
                    ItemDespesa.id != id
                ).all()

                despesas_para_atualizar.extend(parcelas_futuras)

            elif despesa.recorrente:
                # Para recorrente, buscar despesas futuras com mesmo nome e categoria
                mes_competencia_atual = despesa.mes_competencia

                despesas_futuras = _query_itens().filter(
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
                'error': 'Nome nÃ£o pode ser vazio'
            }), 400

        if 'categoria_id' in dados:
            categoria = Categoria.query.get(dados['categoria_id'])
            if not categoria:
                return jsonify({
                    'success': False,
                    'error': 'Categoria nÃ£o encontrada'
                }), 404

        # Atualizar todos os campos para cada despesa
        for desp in despesas_para_atualizar:
            if 'nome' in dados:
                # Se for mÃºltiplas parcelas de consÃ³rcio, manter o nÃºmero da parcela
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

            # Para ediÃ§Ã£o Ãºnica, permitir alterar datas
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
                                'error': 'Formato de data invÃ¡lido. Use YYYY-MM-DD'
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
                                'error': 'Formato de data de pagamento invÃ¡lido. Use YYYY-MM-DD'
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

    except Exception:
        db.session.rollback()
        return _internal_error('despesas')


@despesas_bp.route('/<int:id>', methods=['DELETE'])
def deletar_despesa(id):
    """Deleta uma conta especÃ­fica"""
    try:
        # Buscar na tabela Conta (nÃ£o ItemDespesa)
        conta = _query_contas().filter(Conta.id == id).first()
        if not conta:
            return jsonify({
                'success': False,
                'error': 'Despesa nÃ£o encontrada'
            }), 404

        # Deletar a conta
        db.session.delete(conta)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Despesa deletada com sucesso'
        })

    except Exception:
        db.session.rollback()
        return _internal_error('despesas')


@despesas_bp.route('/<int:id>_OLD', methods=['DELETE'])
def deletar_despesa_OLD(id):
    """[BACKUP] Deleta uma despesa (Ãºnica ou com futuras) - VERSÃƒO ANTIGA"""
    try:
        despesa = _query_itens().filter(ItemDespesa.id == id).first()
        if not despesa:
            return jsonify({
                'success': False,
                'error': 'Despesa nÃ£o encontrada'
            }), 404

        # Verificar se deve deletar apenas esta ou incluir futuras
        tipo_exclusao = request.args.get('tipo_exclusao', 'unica')

        despesas_para_deletar = [despesa]

        if tipo_exclusao == 'futuras':
            # Deletar esta despesa e todas as futuras do mesmo grupo
            if despesa.tipo == 'Consorcio':
                # Para consÃ³rcio, buscar parcelas futuras pelo nome base
                # Nome formato: "ConsÃ³rcio X - Parcela N/M"
                nome_base = despesa.nome.rsplit(' - Parcela ', 1)[0] if ' - Parcela ' in despesa.nome else despesa.nome
                mes_competencia_atual = despesa.mes_competencia

                # Buscar parcelas futuras do mesmo consÃ³rcio
                parcelas_futuras = _query_itens().filter(
                    ItemDespesa.tipo == 'Consorcio',
                    ItemDespesa.nome.like(f"{nome_base} - Parcela%"),
                    ItemDespesa.mes_competencia >= mes_competencia_atual,
                    ItemDespesa.id != id
                ).all()

                despesas_para_deletar.extend(parcelas_futuras)

            elif despesa.recorrente:
                # Para recorrente, buscar despesas futuras com mesmo nome e categoria
                mes_competencia_atual = despesa.mes_competencia

                despesas_futuras = _query_itens().filter(
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

    except Exception:
        db.session.rollback()
        return _internal_error('despesas')


@despesas_bp.route('/<int:id>/pagar', methods=['POST'])
def marcar_como_pago(id):
    """
    Marca uma conta como paga.

    IMPORTANTE: Se for fatura de cartão, usa CartaoService para
    substituir planejado por executado.
    """
    try:
        from backend.models import ContaBancaria
        from backend.services.conta_bancaria_service import ContaBancariaService
    except ImportError:
        from models import ContaBancaria
        from services.conta_bancaria_service import ContaBancariaService

    try:
        conta = _query_contas().filter(Conta.id == id).first()
        if not conta:
            return jsonify({'success': False, 'error': 'Despesa não encontrada'}), 404

        # Bloquear baixa duplicada — despesa já paga não pode ser baixada novamente
        if conta.status_pagamento == 'Pago':
            return jsonify({'success': False, 'error': 'Esta despesa já foi paga e não pode ser baixada novamente'}), 409

        dados = request.get_json() or {}

        # Conta bancária é obrigatória para registrar o movimento
        conta_bancaria_id = dados.get('conta_bancaria_id') or getattr(conta, 'conta_bancaria_id', None)
        if not conta_bancaria_id:
            return jsonify({'success': False, 'error': 'Selecione uma conta bancária para executar o pagamento'}), 400
        try:
            conta_bancaria_id = int(conta_bancaria_id)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'Conta bancária inválida'}), 400

        # Validar conta bancária antes de alterar qualquer estado
        conta_bancaria = ContaBancaria.query.filter(
            ContaBancaria.id == conta_bancaria_id,
            PerfilFinanceiroService.condicao_perfil(ContaBancaria),
        ).first()
        if not conta_bancaria:
            return jsonify({'success': False, 'error': 'Conta bancária não encontrada'}), 404
        if conta_bancaria.status != 'ATIVO':
            return jsonify({'success': False, 'error': 'Conta bancária está inativa'}), 400

        # Determinar data de pagamento
        data_pagamento = datetime.now().date()
        if dados.get('data_pagamento'):
            try:
                data_pagamento = datetime.strptime(dados['data_pagamento'], '%Y-%m-%d').date()
            except ValueError:
                logger.warning('Data de pagamento invalida ao marcar despesa como paga id=%s', id)
                return jsonify({'success': False, 'error': 'Formato de data_pagamento invalido. Use YYYY-MM-DD'}), 400

        # Determinar valor pago
        valor_pago = dados.get('valor_pago')

        # SE FOR FATURA DE CARTÃO: usar CartaoService
        if conta.is_fatura_cartao:
            conta = CartaoService.pagar_fatura(
                fatura_id=id,
                data_pagamento=data_pagamento,
                valor_pago=valor_pago,
                conta_bancaria_id=conta_bancaria_id
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
                    'estouro_orcamento': conta.estouro_orcamento,
                    'conta_bancaria_id': conta.conta_bancaria_id
                }
            }), 200

        # SE NÃO FOR FATURA: atualizar despesa e criar movimento atomicamente
        if valor_pago is not None:
            conta.valor = float(valor_pago)

        conta.status_pagamento = 'Pago'
        conta.data_pagamento = data_pagamento
        conta.conta_bancaria_id = conta_bancaria_id

        # Criar movimento usando o service (inclui flush+recalcular_saldo internamente)
        ContaBancariaService.criar_movimento(
            conta_bancaria_id,
            tipo='DEBITO',
            valor=Decimal(str(conta.valor)),
            descricao=f'Pagamento despesa - {conta.descricao}',
            data_movimento=data_pagamento,
            origem='DESPESA',
            conta_id=conta.id,
        )

        # Sincronizar parcela de financiamento dentro da mesma transação
        if conta.financiamento_parcela_id:
            try:
                from backend.services.financiamento_service import FinanciamentoService
            except ImportError:
                from services.financiamento_service import FinanciamentoService
            FinanciamentoService.registrar_pagamento_parcela(
                parcela_id=conta.financiamento_parcela_id,
                valor_pago=conta.valor,
                data_pagamento=conta.data_pagamento or conta.data_vencimento,
            )

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Despesa marcada como paga',
            'data': {
                'id': conta.id,
                'status_pagamento': conta.status_pagamento,
                'data_pagamento': conta.data_pagamento.isoformat() if conta.data_pagamento else None,
                'valor': float(conta.valor) if conta.valor else 0,
                'conta_bancaria_id': conta.conta_bancaria_id
            }
        })

    except Exception:
        db.session.rollback()
        return _internal_error('despesas')


# ============================================================================
# FUNÃ‡Ã•ES AUXILIARES PARA DESPESAS RECORRENTES
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
    item = _query_itens().filter(ItemDespesa.id == item_despesa_id).first()
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
        existente = _query_contas().filter_by(
            item_despesa_id=item_despesa_id,
            data_vencimento=data_venc
        ).first()
        if existente:
            return
        nova = Conta(
            perfil_financeiro_id=item.perfil_financeiro_id,
            item_despesa_id=item_despesa_id,
            mes_referencia=mes_ref,
            descricao=descricao_custom or item.nome,
            valor=item.valor,
            data_vencimento=data_venc,
            status_pagamento='Pendente',
            debito_automatico=item.meio_pagamento == 'debito_automatico',
            conta_bancaria_id=item.conta_bancaria_id,
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
            dia_semana_python = _dia_semana_ui_para_python(dia_semana_alvo)
            dias_ate_alvo = (dia_semana_python - data_atual.weekday()) % 7
            data_atual += timedelta(days=dias_ate_alvo)

        datas_esperadas = []
        while data_atual <= data_fim_base:
            if data_atual >= inicio_geracao:
                datas_esperadas.append(data_atual)
            data_atual += timedelta(weeks=intervalo)

        _reconciliar_ocorrencias_semanais(item, datas_esperadas, inicio_janela, data_fim_base, intervalo)
        for data_venc in datas_esperadas:
            criar_conta(data_venc, descricao_custom=_descricao_recorrencia_com_data(item, data_venc))

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
    Gera lanÃ§amentos automaticamente para despesas recorrentes pagas via cartÃ£o de crÃ©dito.
    
    DiferenÃ§a da geraÃ§Ã£o de Conta:
    - Gera LancamentoAgregado ao invÃ©s de Conta
    - Aparece na fatura do cartÃ£o
    - Classificado como "Despesas Fixas"
    
    Garante idempotÃªncia: 1 recorrÃªncia = 1 lanÃ§amento/mÃªs
    """
    from datetime import date

    item = _query_itens().filter(ItemDespesa.id == item_despesa_id).first()
    if not item:
        raise ValueError('ItemDespesa nÃ£o encontrado')
    if not item.recorrente:
        raise ValueError('ItemDespesa nÃ£o Ã© recorrente')
    if item.meio_pagamento != 'cartao':
        raise ValueError('ItemDespesa nÃ£o Ã© pago via cartÃ£o')
    if not item.cartao_id:
        raise ValueError('ItemDespesa recorrente pago via cartÃ£o precisa ter cartao_id')
    if not item.categoria_id:
        raise ValueError('ItemDespesa recorrente precisa ter categoria_id')

    tipo_recorrencia = item.tipo_recorrencia or 'mensal'

    # Fallback obrigatÃ³rio para conseguir inferir mes_fatura quando nÃ£o hÃ¡ data_vencimento/mes_competencia
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
        """Cria LancamentoAgregado se ainda nÃ£o existe para esta competÃªncia"""
        mes_fatura = data_compra.replace(day=1)
        
        # Verificar se jÃ¡ existe lanÃ§amento deste item_despesa para este mÃªs (idempotÃªncia)
        existente = _query_lancamentos().filter_by(
            item_despesa_id=item_despesa_id,
            mes_fatura=mes_fatura,
            is_recorrente=True
        ).first()
        
        if existente:
            return  # JÃ¡ existe, nÃ£o cria duplicado
        
        resolucao_cartao = CategoriaCartaoService.resolver_categoria_cartao_para_lancamento(
            cartao_id=item.cartao_id,
            categoria_id=item.categoria_id,
            categoria_cartao_id=item.categoria_cartao_id,
        )

        novo = LancamentoAgregado(
            perfil_financeiro_id=item.perfil_financeiro_id,
            cartao_id=item.cartao_id,
            item_agregado_id=None,
            categoria_cartao_id=resolucao_cartao.get('categoria_cartao_id'),
            categoria_id=item.categoria_id,  # Categoria analÃ­tica obrigatÃ³ria
            descricao=item.nome,
            valor=item.valor,
            data_compra=data_compra,
            mes_fatura=mes_fatura,
            numero_parcela=1,
            total_parcelas=1,
            observacoes=item.descricao or '',
            is_recorrente=True,  # Marca como recorrente para aparecer em "Despesas Fixas"
            item_despesa_id=item_despesa_id  # ReferÃªncia Ã  despesa recorrente
        )
        db.session.add(novo)
        lancamentos_criados.append(novo)
    
    # Gerar lanÃ§amentos conforme tipo de recorrÃªncia (apenas mensal por enquanto)
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
