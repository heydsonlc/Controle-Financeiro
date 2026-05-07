from __future__ import annotations

import re

from sqlalchemy import case, or_

try:
    from backend.models import db, ItemReceita, ReceitaOrcamento, ReceitaRealizada
    from backend.services.perfil_financeiro_service import PerfilFinanceiroService
except ImportError:
    from models import db, ItemReceita, ReceitaOrcamento, ReceitaRealizada
    from services.perfil_financeiro_service import PerfilFinanceiroService


NOME_FONTE_CONSORCIO = 'Contemplação de Consórcio'
NOME_FONTE_CONSORCIO_MOJIBAKE = 'ContemplaÃ§Ã£o de ConsÃ³rcio'
DESCRICAO_FONTE_CONSORCIO = 'Receita pontual gerada automaticamente por consórcio contemplado.'


def marcador_consorcio(consorcio_id):
    return f'consorcio_id={consorcio_id}'


def descricao_receita_contemplacao(consorcio):
    return f'Consórcio {consorcio.nome} - contemplação (ID {consorcio.id})'


def perfil_id_consorcio(consorcio):
    perfil_id = getattr(consorcio, 'perfil_financeiro_id', None)
    if perfil_id:
        return perfil_id

    perfil_padrao = PerfilFinanceiroService.obter_perfil_padrao()
    if perfil_padrao:
        consorcio.perfil_financeiro_id = perfil_padrao.id
        return perfil_padrao.id

    perfil_id = PerfilFinanceiroService.obter_perfil_ativo_id()
    consorcio.perfil_financeiro_id = perfil_id
    return perfil_id


def _observacoes_com_marcador(observacoes, marcador):
    linhas = [linha.strip() for linha in (observacoes or '').splitlines() if linha.strip()]
    if marcador not in linhas:
        linhas.append(marcador)
    return '\n'.join(linhas)


def _remover_marcador(observacoes, marcador):
    linhas = [linha.strip() for linha in (observacoes or '').splitlines() if linha.strip()]
    linhas = [linha for linha in linhas if linha != marcador]
    return '\n'.join(linhas)


def _canonical_order(perfil_id):
    return (
        case((ItemReceita.perfil_financeiro_id == perfil_id, 0), else_=1),
        case((ItemReceita.nome == NOME_FONTE_CONSORCIO, 0), else_=1),
        case((ItemReceita.ativo == True, 0), else_=1),  # noqa: E712
        ItemReceita.id.asc(),
    )


def obter_fonte_contemplacao(perfil_id):
    item = ItemReceita.query.filter(
        ItemReceita.perfil_financeiro_id == perfil_id,
        ItemReceita.nome.in_([NOME_FONTE_CONSORCIO, NOME_FONTE_CONSORCIO_MOJIBAKE]),
    ).order_by(*_canonical_order(perfil_id)).first()

    if item:
        item.nome = NOME_FONTE_CONSORCIO
        item.tipo = 'OUTROS'
        item.descricao = item.descricao or DESCRICAO_FONTE_CONSORCIO
        item.ativo = True
        item.recorrente = False
        return item

    item = ItemReceita(
        perfil_financeiro_id=perfil_id,
        nome=NOME_FONTE_CONSORCIO,
        tipo='OUTROS',
        descricao=DESCRICAO_FONTE_CONSORCIO,
        ativo=True,
        recorrente=False,
        valor_base_mensal=None,
        dia_previsto_pagamento=None,
        conta_origem_id=None,
    )
    db.session.add(item)
    db.session.flush()
    return item


def corrigir_fontes_contemplacao(perfil_id):
    canonica = obter_fonte_contemplacao(perfil_id)
    duplicadas = ItemReceita.query.filter(
        ItemReceita.id != canonica.id,
        ItemReceita.nome.in_([NOME_FONTE_CONSORCIO, NOME_FONTE_CONSORCIO_MOJIBAKE]),
        or_(ItemReceita.perfil_financeiro_id == perfil_id, ItemReceita.perfil_financeiro_id.is_(None)),
    ).all()

    for duplicada in duplicadas:
        ReceitaRealizada.query.filter(
            ReceitaRealizada.item_receita_id == duplicada.id,
            ReceitaRealizada.perfil_financeiro_id == perfil_id,
        ).update(
            {
                ReceitaRealizada.item_receita_id: canonica.id,
                ReceitaRealizada.perfil_financeiro_id: perfil_id,
            },
            synchronize_session=False,
        )
        ReceitaOrcamento.query.filter(
            ReceitaOrcamento.item_receita_id == duplicada.id,
            ReceitaOrcamento.perfil_financeiro_id == perfil_id,
        ).update(
            {
                ReceitaOrcamento.item_receita_id: canonica.id,
                ReceitaOrcamento.perfil_financeiro_id: perfil_id,
            },
            synchronize_session=False,
        )

        if duplicada.receitas_realizadas.count() == 0 and duplicada.receitas_orcamento.count() == 0:
            duplicada.ativo = False
            duplicada.nome = f'{NOME_FONTE_CONSORCIO} (legado #{duplicada.id})'
        else:
            duplicada.nome = NOME_FONTE_CONSORCIO

    return canonica


def _receita_tem_movimento(receita):
    try:
        from backend.models import MovimentoFinanceiro
    except ImportError:
        try:
            from models import MovimentoFinanceiro
        except ImportError:
            return False

    return MovimentoFinanceiro.query.filter_by(receita_realizada_id=receita.id).first() is not None


def _ordenar_receitas_canonicas(receitas, perfil_id, item_id):
    return sorted(
        receitas,
        key=lambda receita: (
            0 if receita.perfil_financeiro_id == perfil_id else 1,
            0 if receita.item_receita_id == item_id else 1,
            0 if receita.perfil_financeiro_id is not None else 1,
            receita.id,
        ),
    )


def receitas_por_marcador(consorcio_id):
    marcador = marcador_consorcio(consorcio_id)
    return ReceitaRealizada.query.filter(
        ReceitaRealizada.observacoes.ilike(f'%{marcador}%'),
    ).order_by(ReceitaRealizada.id.asc()).all()


def _atualizar_receita(receita, consorcio, item, marcador):
    competencia = consorcio.mes_contemplacao.replace(day=1)
    receita.perfil_financeiro_id = perfil_id_consorcio(consorcio)
    receita.item_receita_id = item.id
    receita.data_recebimento = consorcio.mes_contemplacao
    receita.valor_recebido = consorcio.valor_premio
    receita.mes_referencia = competencia
    receita.descricao = descricao_receita_contemplacao(consorcio)
    receita.orcamento_id = None
    receita.observacoes = _observacoes_com_marcador(receita.observacoes, marcador)
    return receita


def gerar_ou_atualizar_receita_contemplacao(consorcio):
    if not consorcio.mes_contemplacao or not consorcio.valor_premio:
        return None

    perfil_id = perfil_id_consorcio(consorcio)
    marcador = marcador_consorcio(consorcio.id)
    existentes = receitas_por_marcador(consorcio.id)

    if not getattr(consorcio, 'ativo', True) and not existentes:
        return None

    item = corrigir_fontes_contemplacao(perfil_id)
    existentes = receitas_por_marcador(consorcio.id)

    if existentes:
        canonica = _ordenar_receitas_canonicas(existentes, perfil_id, item.id)[0]
        _atualizar_receita(canonica, consorcio, item, marcador)

        for duplicada in existentes:
            if duplicada.id == canonica.id:
                continue
            if _receita_tem_movimento(duplicada):
                duplicada.observacoes = _remover_marcador(duplicada.observacoes, marcador)
                nota = f'duplicada_preservada_consorcio_id={consorcio.id}'
                duplicada.observacoes = _observacoes_com_marcador(duplicada.observacoes, nota)
            else:
                db.session.delete(duplicada)
        return canonica

    if not getattr(consorcio, 'ativo', True):
        return None

    receita = ReceitaRealizada(
        perfil_financeiro_id=perfil_id,
        item_receita_id=item.id,
        data_recebimento=consorcio.mes_contemplacao,
        valor_recebido=consorcio.valor_premio,
        mes_referencia=consorcio.mes_contemplacao.replace(day=1),
        conta_origem_id=None,
        descricao=descricao_receita_contemplacao(consorcio),
        orcamento_id=None,
        observacoes=marcador,
    )
    db.session.add(receita)
    return receita


def extrair_consorcio_id_de_observacoes(observacoes):
    match = re.search(r'\bconsorcio_id=(\d+)\b', observacoes or '')
    return int(match.group(1)) if match else None
