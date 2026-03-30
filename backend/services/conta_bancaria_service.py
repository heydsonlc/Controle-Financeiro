from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
import uuid

from sqlalchemy import func, case

try:
    from backend.models import db, ContaBancaria, MovimentoFinanceiro
except ImportError:
    from models import db, ContaBancaria, MovimentoFinanceiro


class ContaBancariaService:
    @staticmethod
    def recalcular_saldo_conta(conta_id: int) -> Decimal:
        conta = ContaBancaria.query.get(conta_id)
        if not conta:
            raise ValueError('Conta bancária não encontrada')

        total_creditos = db.session.query(
            func.coalesce(
                func.sum(
                    case(
                        (MovimentoFinanceiro.tipo == 'CREDITO', MovimentoFinanceiro.valor),
                        else_=0,
                    )
                ),
                0,
            )
        ).filter(MovimentoFinanceiro.conta_bancaria_id == conta_id).scalar()

        total_debitos = db.session.query(
            func.coalesce(
                func.sum(
                    case(
                        (MovimentoFinanceiro.tipo == 'DEBITO', MovimentoFinanceiro.valor),
                        else_=0,
                    )
                ),
                0,
            )
        ).filter(MovimentoFinanceiro.conta_bancaria_id == conta_id).scalar()

        saldo_inicial = Decimal(str(conta.saldo_inicial or 0))
        saldo = saldo_inicial + Decimal(str(total_creditos or 0)) - Decimal(str(total_debitos or 0))
        conta.saldo_atual = saldo
        db.session.flush()
        return saldo

    @staticmethod
    def criar_movimento(
        conta_bancaria_id: int,
        *,
        tipo: str,
        valor: Decimal,
        descricao: str,
        data_movimento: date,
        origem: str = 'MANUAL',
        ajustavel: bool = False,
        fatura_id: Optional[int] = None,
        conta_id: Optional[int] = None,
        receita_realizada_id: Optional[int] = None,
        transferencia_id: Optional[str] = None,
    ) -> MovimentoFinanceiro:
        if tipo not in {'CREDITO', 'DEBITO'}:
            raise ValueError('Tipo de movimento inválido (use CREDITO ou DEBITO)')

        valor_dec = Decimal(str(valor or 0))
        if valor_dec <= 0:
            raise ValueError('Valor do movimento deve ser maior que zero')

        movimento = MovimentoFinanceiro(
            conta_bancaria_id=conta_bancaria_id,
            tipo=tipo,
            valor=valor_dec,
            descricao=(descricao or '').strip() or 'Movimento',
            data_movimento=data_movimento,
            origem=origem,
            ajustavel=bool(ajustavel),
            fatura_id=fatura_id,
            conta_id=conta_id,
            receita_realizada_id=receita_realizada_id,
            transferencia_id=transferencia_id,
        )
        db.session.add(movimento)
        db.session.flush()
        ContaBancariaService.recalcular_saldo_conta(conta_bancaria_id)
        return movimento

    @staticmethod
    def gerar_transferencia(
        conta_origem_id: int,
        conta_destino_id: int,
        *,
        valor: Decimal,
        descricao: str,
        data_movimento: date,
    ) -> dict:
        if conta_origem_id == conta_destino_id:
            raise ValueError('Conta de origem e destino devem ser diferentes')

        conta_origem = ContaBancaria.query.get(conta_origem_id)
        conta_destino = ContaBancaria.query.get(conta_destino_id)
        if not conta_origem or not conta_destino:
            raise ValueError('Conta bancária não encontrada')
        if conta_origem.status != 'ATIVO' or conta_destino.status != 'ATIVO':
            raise ValueError('Conta bancária inativa')

        transferencia_id = str(uuid.uuid4())
        valor_dec = Decimal(str(valor or 0))

        mov_debito = ContaBancariaService.criar_movimento(
            conta_origem_id,
            tipo='DEBITO',
            valor=valor_dec,
            descricao=descricao,
            data_movimento=data_movimento,
            origem='TRANSFERENCIA',
            ajustavel=False,
            transferencia_id=transferencia_id,
        )

        mov_credito = ContaBancariaService.criar_movimento(
            conta_destino_id,
            tipo='CREDITO',
            valor=valor_dec,
            descricao=descricao,
            data_movimento=data_movimento,
            origem='TRANSFERENCIA',
            ajustavel=False,
            transferencia_id=transferencia_id,
        )

        return {
            'transferencia_id': transferencia_id,
            'debito': mov_debito,
            'credito': mov_credito,
        }

    @staticmethod
    def parse_data(value) -> date:
        if not value:
            return datetime.utcnow().date()
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str):
            return datetime.strptime(value[:10], '%Y-%m-%d').date()
        raise ValueError('Data inválida')

