"""
DA-AUTO-STATUS-1 — Baixa automática de despesas em Débito Automático.

Regra: despesa pendente + meio_pagamento=debito_automatico + conta_bancaria_id
       + vencimento <= hoje + saldo suficiente na conta → status vira Pago.

Reaproveitamos exatamente o mesmo fluxo da baixa manual (marcar_como_pago):
  - cria MovimentoFinanceiro(tipo='DEBITO', origem='DESPESA')
  - chama ContaBancariaService.recalcular_saldo_conta()
  - data_pagamento = data_vencimento  (conforme seção 6.1 do contrato)

Idempotência: só processa Contas com status_pagamento != 'Pago'.

FIN-PAGAMENTO-TRAVA-1: cada baixa e uma transacao propria e atomica (conta + movimento + saldo
confirmados juntos ou nada). A conta e a conta bancaria sao travadas e relidas antes das
conferencias (pagamento manual, edicao ou outra baixa simultanea esperam; saldo conferido e o
atual). Antes, uma falha desfazia as baixas anteriores do lote, que continuavam informadas como
feitas; e um debito ja estornado fazia a conta voltar a 'Pago' sem movimento valido.
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import List

logger = logging.getLogger(__name__)

try:
    from backend.models import Conta, ContaBancaria, MovimentoFinanceiro, db
    from backend.services.conta_bancaria_service import ContaBancariaService
    from backend.services.perfil_financeiro_service import PerfilFinanceiroService
    from backend.services.trava_financeira import travar_um
except ImportError:
    from models import Conta, ContaBancaria, MovimentoFinanceiro, db
    from services.conta_bancaria_service import ContaBancariaService
    from services.perfil_financeiro_service import PerfilFinanceiroService
    from services.trava_financeira import travar_um


def executar_baixa_debito_automatico(perfil_id: int | None = None) -> List[int]:
    """
    Avalia todas as contas pendentes de Débito Automático do perfil ativo
    e baixa automaticamente as que têm vencimento <= hoje e saldo suficiente.

    Retorna lista de IDs de Conta que foram baixadas.
    """
    if perfil_id is None:
        perfil_id = PerfilFinanceiroService.obter_perfil_ativo_id()

    hoje = date.today()
    baixadas: List[int] = []

    # Candidatas: não-fatura, pendente, débito automático, conta_bancaria_id preenchida,
    # vencimento já chegou.
    candidatas = (
        Conta.query.with_entities(Conta.id)
        .filter(
            Conta.perfil_financeiro_id == perfil_id,
            Conta.status_pagamento != 'Pago',
            Conta.debito_automatico == True,       # noqa: E712
            Conta.is_fatura_cartao == False,        # noqa: E712
            Conta.conta_bancaria_id.isnot(None),
            Conta.data_vencimento <= hoje,
        )
        .order_by(Conta.id)
        .all()
    )
    if not candidatas:
        return baixadas
    db.session.commit()  # encerra a leitura: cada baixa abaixo e uma transacao propria

    for (conta_id,) in candidatas:
        try:
            conta = travar_um(Conta, conta_id)
            aplicada = bool(conta) and _baixar_conta(conta, perfil_id, hoje)
            db.session.commit()  # conta, movimento e saldo juntos
            if aplicada:
                baixadas.append(conta_id)
        except Exception:
            db.session.rollback()  # so esta conta; as anteriores ja foram confirmadas
            logger.warning(
                'Falha ao baixar automaticamente conta_id=%s perfil=%s',
                conta_id, perfil_id,
                exc_info=True,
            )

    return baixadas


def _baixar_conta(conta: Conta, perfil_id: int, hoje: date | None = None) -> bool:
    """
    Aplica a baixa em uma única Conta, reaproveitando o mesmo padrão
    da baixa manual (status + MovimentoFinanceiro + recalcular_saldo).

    Retorna True se a baixa foi aplicada, False caso contrário.
    Idempotência garantida: não faz nada se já está Pago.
    Não cria movimento duplicado: verifica existência por conta_id + origem.
    """
    # Idempotência (estado relido sob trava pelo chamador)
    if conta.status_pagamento == 'Pago':
        return False
    hoje = hoje or date.today()
    if not conta.debito_automatico or conta.is_fatura_cartao or not conta.conta_bancaria_id \
            or conta.data_vencimento is None or conta.data_vencimento > hoje:
        return False  # mudou desde a selecao (edicao simultanea)

    conta_bancaria_id = conta.conta_bancaria_id

    # Validar conta bancária: mesmo perfil, ativa (travada e relida: saldo atual, sem dupla baixa)
    conta_bancaria = travar_um(ContaBancaria, conta_bancaria_id)
    if not conta_bancaria or conta_bancaria.perfil_financeiro_id != perfil_id or conta_bancaria.status != 'ATIVO':
        conta_bancaria = None
    if not conta_bancaria:
        logger.debug(
            'Conta bancária id=%s ausente/inativa para baixa automática conta=%s',
            conta_bancaria_id, conta.id,
        )
        return False

    # Verificar saldo suficiente
    saldo_disponivel = Decimal(str(conta_bancaria.saldo_atual or 0))
    valor_despesa = Decimal(str(conta.valor or 0))
    if saldo_disponivel < valor_despesa:
        logger.debug(
            'Saldo insuficiente (%.2f < %.2f) para baixa automática conta=%s conta_bancaria=%s',
            saldo_disponivel, valor_despesa, conta.id, conta_bancaria_id,
        )
        return False

    # Verificar movimento duplicado: debito (conta_id + origem DESPESA) ainda nao estornado.
    # FIN-PAGAMENTO-TRAVA-1: debito ja estornado nao conta como pagamento valido. Nesse caso a
    # baixa automatica nao refaz o debito (o usuario estornou de proposito) nem marca 'Pago'.
    debitos = MovimentoFinanceiro.query.filter_by(conta_id=conta.id, origem='DESPESA', tipo='DEBITO').count()
    if debitos:
        estornos = MovimentoFinanceiro.query.filter_by(conta_id=conta.id, origem='ESTORNO_DESPESA').count()
        if estornos >= debitos:
            logger.info('Baixa automatica ignorada: debito anterior estornado (conta=%s)', conta.id)
            return False
    movimento_existente = debitos > 0
    if movimento_existente:
        # Movimento já criado — apenas garantir status correto
        conta.status_pagamento = 'Pago'
        if not conta.data_pagamento:
            conta.data_pagamento = conta.data_vencimento
        return False  # não contabiliza como nova baixa

    # Aplicar baixa — mesmo padrão da baixa manual
    data_pagamento = conta.data_vencimento  # conforme seção 6.1 do contrato
    conta.status_pagamento = 'Pago'
    conta.data_pagamento = data_pagamento
    # conta_bancaria_id já está preenchido; não sobrescrever

    movimento = MovimentoFinanceiro(
        perfil_financeiro_id=perfil_id,
        conta_bancaria_id=conta_bancaria_id,
        tipo='DEBITO',
        valor=valor_despesa,
        descricao=f'Débito automático - {conta.descricao}',
        data_movimento=data_pagamento,
        conta_id=conta.id,
        origem='DESPESA',
        ajustavel=False,
    )
    db.session.add(movimento)
    db.session.flush()  # garante que o movimento existe antes de recalcular

    ContaBancariaService.recalcular_saldo_conta(conta_bancaria_id)

    logger.info(
        'Baixa automática aplicada: conta=%s valor=%.2f conta_bancaria=%s',
        conta.id, valor_despesa, conta_bancaria_id,
    )
    return True
