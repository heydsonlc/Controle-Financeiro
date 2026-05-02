from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal

try:
    from backend.models import db, DespesaPrevista, ItemDespesa, Conta
    from backend.services.veiculo_uso_service import registrar_despesa_combustivel_confirmada
    from backend.models import DespesaPrevistaAcaoLog
    from backend.services.despesa_prevista_cascata_service import ajustar_ciclo_um_passo
    from backend.services.cartao_service import CartaoService
except ImportError:
    from models import db, DespesaPrevista, ItemDespesa, Conta
    from services.veiculo_uso_service import registrar_despesa_combustivel_confirmada
    from models import DespesaPrevistaAcaoLog
    from services.despesa_prevista_cascata_service import ajustar_ciclo_um_passo
    from services.cartao_service import CartaoService


STATUS_PREVISTA = 'PREVISTA'
STATUS_CONFIRMADA = 'CONFIRMADA'
STATUS_ADIADA = 'ADIADA'
STATUS_IGNORADA = 'IGNORADA'

STATUS_FASE2_BLOQUEADOS = (STATUS_CONFIRMADA, STATUS_ADIADA, STATUS_IGNORADA)

MEIOS_VALIDOS = ('cartao', 'pix', 'boleto', 'dinheiro', 'debito')


def _parse_date(value) -> date | None:
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value)).date()
    except Exception:
        return None


def _primeiro_dia_mes(d: date) -> date:
    return d.replace(day=1)


def _assert_prevista(desp: DespesaPrevista) -> None:
    if desp.status != STATUS_PREVISTA:
        raise ValueError('Apenas despesas PREVISTA podem ser alteradas nesta fase')

    # Backfill defensivo (caso banco antigo ainda não tenha preenchido datas)
    if desp.data_original_prevista is None:
        desp.data_original_prevista = desp.data_prevista
    if desp.data_atual_prevista is None:
        desp.data_atual_prevista = desp.data_prevista


def _descricao_para_prevista(desp: DespesaPrevista) -> str:
    try:
        meta = json.loads(desp.metadata_json or '{}') if desp.metadata_json else {}
    except Exception:
        meta = {}
    tipo_evento = meta.get('tipo_evento') or desp.origem_tipo or ''
    rotulos = {
        'COMBUSTIVEL': 'Combustível',
        'IPVA': 'IPVA',
        'SEGURO': 'Seguro',
        'LICENCIAMENTO': 'Licenciamento',
        'PARCELA_FINANCIAMENTO': 'Parcela de financiamento',
        'IOF_FINANCIAMENTO': 'IOF de financiamento',
        'TRANSPORTE_APP': 'Transporte por app',
        'TROCA_OLEO': 'Troca de óleo',
        'TROCA_PNEUS': 'Troca de pneus',
        'REVISAO_GERAL': 'Revisão geral',
        'ALINHAMENTO_BALANCEAMENTO': 'Alinhamento / Balanceamento',
    }
    label = rotulos.get(tipo_evento.upper(), tipo_evento or 'Despesa prevista')
    return label


def _criar_conta_para_prevista(desp: DespesaPrevista, meio_pagamento: str,
                                data_vencimento: date, categoria_id: int,
                                observacao: str | None) -> dict:
    nome = _descricao_para_prevista(desp)
    valor = Decimal(str(desp.valor_previsto or 0))
    mes_ref = _primeiro_dia_mes(data_vencimento)

    item = ItemDespesa(
        nome=nome,
        tipo='Simples',
        categoria_id=categoria_id,
        valor=valor,
        recorrente=False,
        ativo=True,
        meio_pagamento=meio_pagamento,
        data_vencimento=data_vencimento,
        mes_competencia=mes_ref.strftime('%Y-%m'),
    )
    db.session.add(item)
    db.session.flush()  # garante item.id antes de criar Conta

    conta = Conta(
        item_despesa_id=item.id,
        mes_referencia=mes_ref,
        descricao=nome + (f' — {observacao}' if observacao else ''),
        valor=valor,
        data_vencimento=data_vencimento,
        status_pagamento='Pendente',
        is_fatura_cartao=False,
        observacoes=observacao or None,
    )
    db.session.add(conta)
    db.session.flush()

    return {
        'tipo': 'conta',
        'id': conta.id,
        'descricao': conta.descricao,
        'valor': float(valor),
        'data_vencimento': data_vencimento.isoformat(),
    }


def _criar_lancamento_para_prevista(desp: DespesaPrevista, cartao_id: int,
                                    data_vencimento: date, categoria_id: int,
                                    observacao: str | None) -> dict:
    nome = _descricao_para_prevista(desp)
    valor = Decimal(str(desp.valor_previsto or 0))

    dados = {
        'cartao_id': cartao_id,
        'item_agregado_id': None,
        'categoria_id': categoria_id,
        'descricao': nome,
        'valor': valor,
        'data_compra': data_vencimento,
        'mes_fatura': data_vencimento,
        'total_parcelas': 1,
        'observacoes': observacao or None,
        'origem_importacao': 'manual',
    }
    lancamento, _ = CartaoService.adicionar_lancamento(dados)

    return {
        'tipo': 'lancamento_agregado',
        'id': lancamento.id,
        'descricao': lancamento.descricao,
        'valor': float(lancamento.valor),
        'data_vencimento': data_vencimento.isoformat(),
    }


def confirmar(despesa_id: int, payload: dict | None = None) -> tuple[DespesaPrevista, dict | None]:
    """Confirma uma DespesaPrevista.

    Se payload contiver meio_pagamento, cria a entidade financeira real
    (Conta ou LancamentoAgregado) na mesma transação.
    Sem payload ou com payload vazio, mantém comportamento legado
    (apenas muda status para CONFIRMADA).

    Retorna (desp, entidade_criada_dict | None).
    """
    desp = DespesaPrevista.query.get(despesa_id)
    if not desp:
        raise ValueError('Despesa prevista não encontrada')
    _assert_prevista(desp)

    entidade_criada = None
    meio = (payload or {}).get('meio_pagamento')

    if meio:
        meio = str(meio).strip().lower()
        if meio not in MEIOS_VALIDOS:
            raise ValueError(f'meio_pagamento inválido: {meio}. Use: {", ".join(MEIOS_VALIDOS)}')

        # Campos comuns
        categoria_id = int((payload or {}).get('categoria_id') or desp.categoria_id or 0)
        if not categoria_id:
            raise ValueError('categoria_id é obrigatório para conversão')

        data_raw = (payload or {}).get('data_vencimento') or desp.data_atual_prevista or desp.data_prevista
        data_vencimento = _parse_date(data_raw)
        if not data_vencimento:
            raise ValueError('data_vencimento inválida')

        observacao = str((payload or {}).get('observacao') or '').strip() or None

        if meio == 'cartao':
            cartao_id_raw = (payload or {}).get('cartao_id')
            if not cartao_id_raw:
                raise ValueError('cartao_id é obrigatório quando meio_pagamento=cartao')
            cartao_id = int(cartao_id_raw)
            entidade_criada = _criar_lancamento_para_prevista(desp, cartao_id, data_vencimento, categoria_id, observacao)
        else:
            entidade_criada = _criar_conta_para_prevista(desp, meio, data_vencimento, categoria_id, observacao)

    desp.status = STATUS_CONFIRMADA
    db.session.add(desp)
    # FASE 3 (sensor passivo): se for combustível confirmado, atualiza km estimado do veículo incrementalmente
    registrar_despesa_combustivel_confirmada(desp)
    return desp, entidade_criada


def ignorar(despesa_id: int) -> DespesaPrevista:
    desp = DespesaPrevista.query.get(despesa_id)
    if not desp:
        raise ValueError('Despesa prevista não encontrada')
    _assert_prevista(desp)

    desp.status = STATUS_IGNORADA
    db.session.add(desp)
    return desp


def adiar(despesa_id: int, nova_data, ajustar_ciclo: bool = False) -> tuple[DespesaPrevista, int | None]:
    desp = DespesaPrevista.query.get(despesa_id)
    if not desp:
        raise ValueError('Despesa prevista não encontrada')
    _assert_prevista(desp)

    nd = _parse_date(nova_data)
    if not nd:
        raise ValueError('nova_data inválida (use YYYY-MM-DD)')

    nd = _primeiro_dia_mes(nd)

    desp.status = STATUS_ADIADA
    desp.data_atual_prevista = nd
    desp.data_prevista = nd  # compatibilidade: espelha data_atual_prevista
    # data_original_prevista permanece intacta
    db.session.add(desp)

    criada_id = None
    if bool(ajustar_ciclo):
        resultado = ajustar_ciclo_um_passo(desp)
        criada_id = resultado.despesa_criada_id

    # Auditoria mínima
    log = DespesaPrevistaAcaoLog(
        despesa_prevista_id=desp.id,
        acao='ADIAR',
        ajustar_ciclo=bool(ajustar_ciclo),
        despesa_prevista_criada_id=criada_id
    )
    db.session.add(log)

    return desp, criada_id
