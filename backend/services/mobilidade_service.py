"""
VEIC-2 / VEIC-2B: Service de mobilidade — ativação de modalidade e criação de recorrências.

Regras:
- Apenas uma modalidade ATIVA por vez (a anterior é inativada).
- Recorrência mensal criada apenas para custos estáveis (combustível, assinatura).
- categoria_cartao_id resolvido via CategoriaCartaoService quando meio=cartão.
- item_agregado_id NUNCA usado como regra nova; compatibilidade transitória apenas.
- IPVA, seguro, licenciamento e parcelas de financiamento permanecem como DespesaPrevista.
- VEIC-2B: suporte a TRANSPORTE_APP e ASSINATURA; supressão de DespesaPrevista redundante.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal

try:
    from backend.models import db, DespesaPrevista, ItemDespesa, MobilidadeAssinatura, MobilidadeCenarioAtivo, Veiculo
    from backend.services.categoria_cartao_service import CategoriaCartaoService
    from backend.services.categoria_default import get_categoria_padrao_veiculos
    from backend.services.transporte_app_service import obter_config_transporte_app, parse_config as parse_transporte_config
except ImportError:
    from models import db, DespesaPrevista, ItemDespesa, MobilidadeAssinatura, MobilidadeCenarioAtivo, Veiculo
    from services.categoria_cartao_service import CategoriaCartaoService
    from services.categoria_default import get_categoria_padrao_veiculos
    from services.transporte_app_service import obter_config_transporte_app, parse_config as parse_transporte_config


MEIOS_VALIDOS = ('cartao', 'pix', 'boleto', 'dinheiro', 'debito')
TIPOS_VALIDOS = ('VEICULO', 'TRANSPORTE_APP', 'ASSINATURA')


def _to_int(v):
    try:
        return int(v) if v is not None else None
    except Exception:
        return None


def _to_decimal(v) -> Decimal | None:
    if v is None or (isinstance(v, str) and v.strip() == ''):
        return None
    try:
        return Decimal(str(v))
    except Exception:
        return None


def _parse_date(v) -> date | None:
    if not v:
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v)).date()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Resolução de categoria_cartao_id
# ---------------------------------------------------------------------------

def resolver_categoria_cartao_para_mobilidade(
    categoria_id: int | None,
    cartao_id: int | None,
    categoria_cartao_id_manual: int | None = None,
) -> tuple[int | None, str | None]:
    """
    Retorna (categoria_cartao_id_resolvido, aviso_ou_None).

    Lógica (conforme regra VEIC-2 item 9):
    1. Se vier categoria_cartao_id_manual → preservar (sem validação bloqueante).
    2. Senão, tentar resolver via mapa categoria_despesa → categoria_cartao.
    3. Se resolveu mas não está vinculada ao cartão → retorna None + aviso.
    4. Se não resolveu → retorna None + aviso (não bloqueia).
    """
    if not cartao_id:
        return None, None

    if categoria_cartao_id_manual:
        return _to_int(categoria_cartao_id_manual), None

    if not categoria_id:
        return None, 'Categoria do Cartao nao configurada para esta Categoria de Despesa no cartao escolhido.'

    try:
        resultado = CategoriaCartaoService.resolver_categoria_cartao_para_lancamento(
            cartao_id=cartao_id,
            categoria_id=categoria_id,
            categoria_cartao_id=None,
        )
    except Exception:
        return None, 'Categoria do Cartao nao configurada para esta Categoria de Despesa no cartao escolhido.'

    cc_id = resultado.get('categoria_cartao_id')
    origem = resultado.get('origem')
    vinculada = resultado.get('vinculada_ao_cartao', False)

    if not cc_id:
        return None, 'Categoria do Cartao nao configurada para esta Categoria de Despesa no cartao escolhido.'

    if not vinculada:
        return None, 'Categoria do Cartao resolvida mas nao vinculada ao cartao escolhido.'

    return cc_id, None


# ---------------------------------------------------------------------------
# Controle de duplicidade de recorrência
# ---------------------------------------------------------------------------

def _buscar_recorrencia_existente(origem_tipo: str, origem_id: int, origem_contexto: str) -> ItemDespesa | None:
    return ItemDespesa.query.filter_by(
        origem_tipo=origem_tipo,
        origem_id=origem_id,
        origem_contexto=origem_contexto,
        recorrente=True,
        ativo=True,
    ).first()


def evitar_recorrencia_duplicada(origem_tipo: str, origem_id: int, origem_contexto: str) -> bool:
    """Retorna True se já existe recorrência ativa para este contexto."""
    return _buscar_recorrencia_existente(origem_tipo, origem_id, origem_contexto) is not None


def inativar_recorrencias_origem(origem_tipo: str, origem_id: int) -> int:
    """Inativa todas as recorrências automáticas vinculadas a esta origem. Retorna count."""
    itens = ItemDespesa.query.filter_by(
        origem_tipo=origem_tipo,
        origem_id=origem_id,
        recorrente=True,
        ativo=True,
    ).all()
    for item in itens:
        item.ativo = False
        db.session.add(item)
    return len(itens)


# ---------------------------------------------------------------------------
# Criação de recorrência de combustível
# ---------------------------------------------------------------------------

def criar_recorrencia_combustivel(
    veiculo: Veiculo,
    meio_pagamento: str,
    cartao_id: int | None,
    categoria_id: int | None,
    categoria_cartao_id: int | None,
    data_inicio: date | None = None,
) -> tuple[ItemDespesa, list[str]]:
    """
    Cria (ou atualiza) recorrência mensal de combustível para um veículo.
    Retorna (recorrencia, avisos).
    """
    avisos: list[str] = []

    valor = _to_decimal(veiculo.combustivel_valor_mensal)
    if not valor or valor <= 0:
        raise ValueError('Veiculo nao tem valor de combustivel mensal configurado')

    cat_id = categoria_id or veiculo.categoria_combustivel_id
    if not cat_id:
        try:
            cat_id = get_categoria_padrao_veiculos()
        except ValueError:
            avisos.append('Granularidade de Categoria de Despesa pendente: combustivel deveria ter categoria propria, mas modulo usa categoria padrao.')
            cat_id = None

    if cat_id is None:
        raise ValueError('Nao foi possivel determinar categoria para a recorrencia de combustivel')

    cc_id_resolvido, aviso_cc = resolver_categoria_cartao_para_mobilidade(
        categoria_id=cat_id,
        cartao_id=cartao_id,
        categoria_cartao_id_manual=categoria_cartao_id,
    )
    if aviso_cc:
        avisos.append(aviso_cc)

    existente = _buscar_recorrencia_existente('VEICULO', veiculo.id, 'combustivel_mensal')
    if existente:
        existente.valor = valor
        existente.meio_pagamento = meio_pagamento
        existente.cartao_id = cartao_id
        existente.categoria_id = cat_id
        existente.categoria_cartao_id = cc_id_resolvido
        existente.ativo = True
        db.session.add(existente)
        return existente, avisos

    nome = f'Combustivel - {veiculo.nome}'
    data_venc = data_inicio or date.today().replace(day=1)
    mes_comp = data_venc.strftime('%Y-%m')

    recorrencia = ItemDespesa(
        nome=nome,
        tipo='Simples',
        recorrente=True,
        tipo_recorrencia='mensal',
        valor=valor,
        categoria_id=cat_id,
        categoria_cartao_id=cc_id_resolvido,
        meio_pagamento=meio_pagamento,
        cartao_id=cartao_id,
        data_vencimento=data_venc,
        mes_competencia=mes_comp,
        ativo=True,
        pago=False,
        origem_tipo='VEICULO',
        origem_id=veiculo.id,
        origem_contexto='combustivel_mensal',
    )
    db.session.add(recorrencia)
    return recorrencia, avisos


# ---------------------------------------------------------------------------
# Criação de recorrência de transporte por app (VEIC-2B)
# ---------------------------------------------------------------------------

def criar_recorrencia_transporte_app(
    caminho_id: int,
    nome: str,
    valor_mensal: Decimal,
    meio_pagamento: str,
    cartao_id: int | None,
    categoria_id: int | None,
    categoria_cartao_id: int | None,
    data_inicio: date | None = None,
) -> tuple[ItemDespesa, list[str]]:
    avisos: list[str] = []

    if not valor_mensal or valor_mensal <= 0:
        raise ValueError('valor_mensal deve ser > 0 para recorrencia de transporte por app')

    if not categoria_id:
        try:
            categoria_id = get_categoria_padrao_veiculos()
        except ValueError:
            avisos.append('Categoria padrao de veiculos nao encontrada — recorrencia sem categoria.')

    cc_id_resolvido, aviso_cc = resolver_categoria_cartao_para_mobilidade(
        categoria_id=categoria_id,
        cartao_id=cartao_id,
        categoria_cartao_id_manual=categoria_cartao_id,
    )
    if aviso_cc:
        avisos.append(aviso_cc)

    existente = _buscar_recorrencia_existente('TRANSPORTE_APP', caminho_id, 'transporte_app_mensal')
    if existente:
        existente.valor = valor_mensal
        existente.meio_pagamento = meio_pagamento
        existente.cartao_id = cartao_id
        existente.categoria_id = categoria_id
        existente.categoria_cartao_id = cc_id_resolvido
        existente.ativo = True
        db.session.add(existente)
        return existente, avisos

    data_venc = data_inicio or date.today().replace(day=1)
    mes_comp = data_venc.strftime('%Y-%m')

    recorrencia = ItemDespesa(
        nome=f'Transporte por app - {nome}',
        tipo='Simples',
        recorrente=True,
        tipo_recorrencia='mensal',
        valor=valor_mensal,
        categoria_id=categoria_id,
        categoria_cartao_id=cc_id_resolvido,
        meio_pagamento=meio_pagamento,
        cartao_id=cartao_id,
        data_vencimento=data_venc,
        mes_competencia=mes_comp,
        ativo=True,
        pago=False,
        origem_tipo='TRANSPORTE_APP',
        origem_id=caminho_id,
        origem_contexto='transporte_app_mensal',
    )
    db.session.add(recorrencia)
    return recorrencia, avisos


# ---------------------------------------------------------------------------
# Criação de recorrência de assinatura (VEIC-2B)
# ---------------------------------------------------------------------------

def criar_recorrencia_assinatura(
    assinatura: MobilidadeAssinatura,
    meio_pagamento: str,
    cartao_id: int | None,
    categoria_cartao_id: int | None,
    data_inicio: date | None = None,
) -> tuple[ItemDespesa, list[str]]:
    avisos: list[str] = []

    valor = _to_decimal(assinatura.valor_mensal)
    if not valor or valor <= 0:
        raise ValueError('MobilidadeAssinatura sem valor_mensal configurado')

    cat_id = assinatura.categoria_id
    if not cat_id:
        try:
            cat_id = get_categoria_padrao_veiculos()
        except ValueError:
            avisos.append('Categoria padrao de veiculos nao encontrada — recorrencia sem categoria.')

    cc_id_resolvido, aviso_cc = resolver_categoria_cartao_para_mobilidade(
        categoria_id=cat_id,
        cartao_id=cartao_id,
        categoria_cartao_id_manual=categoria_cartao_id,
    )
    if aviso_cc:
        avisos.append(aviso_cc)

    existente = _buscar_recorrencia_existente('ASSINATURA', assinatura.id, 'assinatura_mensal')
    if existente:
        existente.valor = valor
        existente.meio_pagamento = meio_pagamento
        existente.cartao_id = cartao_id
        existente.categoria_id = cat_id
        existente.categoria_cartao_id = cc_id_resolvido
        existente.ativo = True
        db.session.add(existente)
        return existente, avisos

    data_venc = data_inicio or date.today().replace(day=1)
    mes_comp = data_venc.strftime('%Y-%m')

    recorrencia = ItemDespesa(
        nome=f'Assinatura - {assinatura.nome}',
        tipo='Simples',
        recorrente=True,
        tipo_recorrencia='mensal',
        valor=valor,
        categoria_id=cat_id,
        categoria_cartao_id=cc_id_resolvido,
        meio_pagamento=meio_pagamento,
        cartao_id=cartao_id,
        data_vencimento=data_venc,
        mes_competencia=mes_comp,
        ativo=True,
        pago=False,
        origem_tipo='ASSINATURA',
        origem_id=assinatura.id,
        origem_contexto='assinatura_mensal',
    )
    db.session.add(recorrencia)
    return recorrencia, avisos


# ---------------------------------------------------------------------------
# Supressão de DespesaPrevista redundante (VEIC-2B)
# ---------------------------------------------------------------------------

def suprimir_despesas_previstas_por_recorrencia(
    origem_tipo: str,
    origem_id: int,
    tipo_evento: str,
) -> int:
    """
    Marca como SUPRIMIDA toda DespesaPrevista PREVISTA futura para esta origem.
    Não toca CONFIRMADA, ADIADA ou IGNORADA.
    Retorna o número de registros suprimidos.
    """
    hoje = date.today().replace(day=1)
    candidatas = DespesaPrevista.query.filter(
        DespesaPrevista.origem_tipo == origem_tipo,
        DespesaPrevista.origem_id == origem_id,
        DespesaPrevista.status == 'PREVISTA',
        DespesaPrevista.data_prevista >= hoje,
    ).all()

    suprimidas = 0
    for desp in candidatas:
        raw = getattr(desp, 'metadata_json', None)
        if raw:
            try:
                md = json.loads(raw) or {}
            except Exception:
                md = {}
            if md.get('tipo_evento') != tipo_evento:
                continue
        desp.status = 'SUPRIMIDA'
        db.session.add(desp)
        suprimidas += 1

    return suprimidas


# ---------------------------------------------------------------------------
# Inativação da modalidade atual
# ---------------------------------------------------------------------------

def inativar_modalidade_atual() -> MobilidadeCenarioAtivo | None:
    """Inativa o cenário ativo atual (se existir) e suas recorrências."""
    atual = MobilidadeCenarioAtivo.query.filter_by(status='ATIVO').first()
    if not atual:
        return None

    inativar_recorrencias_origem(atual.tipo_modalidade, atual.origem_id)
    atual.status = 'INATIVO'
    atual.updated_at = datetime.utcnow()
    db.session.add(atual)
    return atual


# ---------------------------------------------------------------------------
# Prévia de ativação
# ---------------------------------------------------------------------------

def previsualizar_ativacao_modalidade(payload: dict) -> dict:
    """
    Calcula e retorna o que será criado ao ativar a modalidade.
    Não grava nada no banco.
    """
    tipo = (payload.get('tipo_modalidade') or '').upper()
    origem_id = _to_int(payload.get('origem_id'))
    meio = (payload.get('meio_pagamento') or '').lower()
    cartao_id = _to_int(payload.get('cartao_id'))
    categoria_id = _to_int(payload.get('categoria_id'))
    categoria_cartao_id_manual = _to_int(payload.get('categoria_cartao_id'))
    data_inicio = _parse_date(payload.get('data_inicio'))

    if tipo not in TIPOS_VALIDOS:
        raise ValueError(f'tipo_modalidade invalido: {tipo}')

    avisos: list[str] = []
    recorrencia_previa = None

    if tipo == 'VEICULO':
        if not origem_id:
            raise ValueError('origem_id (veiculo.id) e obrigatorio para tipo_modalidade=VEICULO')
        v = Veiculo.query.get(origem_id)
        if not v:
            raise ValueError('Veiculo nao encontrado')

        valor_comb = _to_decimal(v.combustivel_valor_mensal) or Decimal('0')
        cat_id = categoria_id or v.categoria_combustivel_id

        cc_id_resolvido, aviso_cc = resolver_categoria_cartao_para_mobilidade(
            categoria_id=cat_id,
            cartao_id=cartao_id,
            categoria_cartao_id_manual=categoria_cartao_id_manual,
        )
        if aviso_cc:
            avisos.append(aviso_cc)

        if valor_comb > 0:
            recorrencia_previa = {
                'nome': f'Combustivel - {v.nome}',
                'valor': float(valor_comb),
                'tipo_recorrencia': 'mensal',
                'categoria_id': cat_id,
                'categoria_cartao_id': cc_id_resolvido,
                'meio_pagamento': meio or None,
                'cartao_id': cartao_id,
                'origem_tipo': 'VEICULO',
                'origem_id': origem_id,
                'origem_contexto': 'combustivel_mensal',
            }
        else:
            avisos.append('Veiculo nao possui valor de combustivel mensal configurado — recorrencia nao sera criada.')

        despesas_previstas = ['IPVA (anual)', 'Seguro (anual)', 'Licenciamento (anual)', 'Parcelas de financiamento (se houver)']

        return {
            'tipo_modalidade': tipo,
            'origem_id': origem_id,
            'nome_origem': v.nome,
            'recorrencia': recorrencia_previa,
            'despesas_previstas': despesas_previstas,
            'avisos': avisos,
        }

    if tipo == 'TRANSPORTE_APP':
        if not origem_id:
            raise ValueError('origem_id (caminho_id) e obrigatorio para tipo_modalidade=TRANSPORTE_APP')
        caminho = obter_config_transporte_app(origem_id)
        if not caminho:
            raise ValueError('Caminho de transporte por app nao encontrado')

        try:
            config = parse_transporte_config(caminho)
            valor_mensal = config.valor_mensal
            nome_origem = config.nome
        except Exception:
            valor_mensal = Decimal(str(caminho.get('valor_mensal') or 0))
            nome_origem = caminho.get('nome') or f'Caminho {origem_id}'

        cc_id_resolvido, aviso_cc = resolver_categoria_cartao_para_mobilidade(
            categoria_id=categoria_id,
            cartao_id=cartao_id,
            categoria_cartao_id_manual=categoria_cartao_id_manual,
        )
        if aviso_cc:
            avisos.append(aviso_cc)

        if valor_mensal > 0:
            recorrencia_previa = {
                'nome': f'Transporte por app - {nome_origem}',
                'valor': float(valor_mensal),
                'tipo_recorrencia': 'mensal',
                'categoria_id': categoria_id,
                'categoria_cartao_id': cc_id_resolvido,
                'meio_pagamento': meio or None,
                'cartao_id': cartao_id,
                'origem_tipo': 'TRANSPORTE_APP',
                'origem_id': origem_id,
                'origem_contexto': 'transporte_app_mensal',
            }
        else:
            avisos.append('Caminho sem valor mensal calculado — recorrencia nao sera criada.')

        return {
            'tipo_modalidade': tipo,
            'origem_id': origem_id,
            'nome_origem': nome_origem,
            'recorrencia': recorrencia_previa,
            'despesas_previstas': [],
            'avisos': avisos,
        }

    if tipo == 'ASSINATURA':
        if not origem_id:
            raise ValueError('origem_id (assinatura.id) e obrigatorio para tipo_modalidade=ASSINATURA')
        assinatura = MobilidadeAssinatura.query.get(origem_id)
        if not assinatura:
            raise ValueError('MobilidadeAssinatura nao encontrada')
        if assinatura.status != 'ATIVO':
            avisos.append('Assinatura esta INATIVA.')

        cat_id = categoria_id or assinatura.categoria_id
        cc_id_resolvido, aviso_cc = resolver_categoria_cartao_para_mobilidade(
            categoria_id=cat_id,
            cartao_id=cartao_id,
            categoria_cartao_id_manual=categoria_cartao_id_manual,
        )
        if aviso_cc:
            avisos.append(aviso_cc)

        recorrencia_previa = {
            'nome': f'Assinatura - {assinatura.nome}',
            'valor': float(assinatura.valor_mensal),
            'tipo_recorrencia': 'mensal',
            'categoria_id': cat_id,
            'categoria_cartao_id': cc_id_resolvido,
            'meio_pagamento': meio or None,
            'cartao_id': cartao_id,
            'origem_tipo': 'ASSINATURA',
            'origem_id': origem_id,
            'origem_contexto': 'assinatura_mensal',
        }

        return {
            'tipo_modalidade': tipo,
            'origem_id': origem_id,
            'nome_origem': assinatura.nome,
            'recorrencia': recorrencia_previa,
            'despesas_previstas': [],
            'avisos': avisos,
        }

    raise ValueError(f'Previa nao implementada para tipo_modalidade={tipo}')


# ---------------------------------------------------------------------------
# Ativação
# ---------------------------------------------------------------------------

def ativar_modalidade(payload: dict) -> dict:
    """
    Ativa uma modalidade de mobilidade:
    1. Inativa a modalidade anterior + suas recorrências.
    2. Cria recorrência mensal (se aplicável).
    3. Grava MobilidadeCenarioAtivo.
    Não faz commit — responsabilidade do chamador.
    """
    tipo = (payload.get('tipo_modalidade') or '').upper()
    origem_id = _to_int(payload.get('origem_id'))
    meio = (payload.get('meio_pagamento') or '').lower() or None
    cartao_id = _to_int(payload.get('cartao_id'))
    categoria_id = _to_int(payload.get('categoria_id'))
    categoria_cartao_id_manual = _to_int(payload.get('categoria_cartao_id'))
    data_inicio = _parse_date(payload.get('data_inicio')) or date.today().replace(day=1)
    criar_recorrencia = payload.get('criar_recorrencia', True)

    if tipo not in TIPOS_VALIDOS:
        raise ValueError(f'tipo_modalidade invalido: {tipo}')
    if meio and meio not in MEIOS_VALIDOS:
        raise ValueError(f'meio_pagamento invalido: {meio}')

    avisos: list[str] = []
    recorrencia = None

    # 1. Inativar modalidade anterior
    anterior = inativar_modalidade_atual()

    # 2. Criar recorrência
    cat_id = categoria_id
    cc_id_resolvido = _to_int(payload.get('categoria_cartao_id'))

    if tipo == 'VEICULO':
        if not origem_id:
            raise ValueError('origem_id (veiculo.id) e obrigatorio')
        v = Veiculo.query.get(origem_id)
        if not v:
            raise ValueError('Veiculo nao encontrado')

        cat_id = categoria_id or v.categoria_combustivel_id
        cc_id_resolvido, aviso_cc = resolver_categoria_cartao_para_mobilidade(
            categoria_id=cat_id,
            cartao_id=cartao_id,
            categoria_cartao_id_manual=categoria_cartao_id_manual,
        )
        if aviso_cc:
            avisos.append(aviso_cc)

        valor_comb = _to_decimal(v.combustivel_valor_mensal) or Decimal('0')
        if criar_recorrencia and valor_comb > 0 and meio:
            recorrencia, avisos_rec = criar_recorrencia_combustivel(
                veiculo=v,
                meio_pagamento=meio,
                cartao_id=cartao_id,
                categoria_id=cat_id,
                categoria_cartao_id=cc_id_resolvido,
                data_inicio=data_inicio,
            )
            avisos.extend(avisos_rec)
            db.session.flush()
        elif criar_recorrencia and valor_comb > 0 and not meio:
            avisos.append('meio_pagamento nao informado — recorrencia de combustivel nao foi criada.')
        elif criar_recorrencia and valor_comb <= 0:
            avisos.append('Veiculo sem valor de combustivel — recorrencia nao criada.')

    elif tipo == 'TRANSPORTE_APP':
        if not origem_id:
            raise ValueError('origem_id (caminho_id) e obrigatorio')
        caminho = obter_config_transporte_app(origem_id)
        if not caminho:
            raise ValueError('Caminho de transporte por app nao encontrado')

        try:
            config = parse_transporte_config(caminho)
            valor_app = config.valor_mensal
            nome_app = config.nome
        except Exception:
            valor_app = _to_decimal(caminho.get('valor_mensal') or 0) or Decimal('0')
            nome_app = caminho.get('nome') or f'Caminho {origem_id}'

        cc_id_resolvido, aviso_cc = resolver_categoria_cartao_para_mobilidade(
            categoria_id=cat_id,
            cartao_id=cartao_id,
            categoria_cartao_id_manual=categoria_cartao_id_manual,
        )
        if aviso_cc:
            avisos.append(aviso_cc)

        if criar_recorrencia and valor_app > 0 and meio:
            recorrencia, avisos_rec = criar_recorrencia_transporte_app(
                caminho_id=origem_id,
                nome=nome_app,
                valor_mensal=valor_app,
                meio_pagamento=meio,
                cartao_id=cartao_id,
                categoria_id=cat_id,
                categoria_cartao_id=cc_id_resolvido,
                data_inicio=data_inicio,
            )
            avisos.extend(avisos_rec)
            db.session.flush()
            n_sup = suprimir_despesas_previstas_por_recorrencia('TRANSPORTE_APP', origem_id, 'TRANSPORTE_APP')
            if n_sup:
                avisos.append(f'{n_sup} DespesaPrevista(s) suprimida(s) por recorrencia ativa.')
        elif criar_recorrencia and valor_app > 0 and not meio:
            avisos.append('meio_pagamento nao informado — recorrencia de transporte por app nao foi criada.')
        elif criar_recorrencia and valor_app <= 0:
            avisos.append('Caminho sem valor mensal — recorrencia nao criada.')

    elif tipo == 'ASSINATURA':
        if not origem_id:
            raise ValueError('origem_id (assinatura.id) e obrigatorio')
        assinatura = MobilidadeAssinatura.query.get(origem_id)
        if not assinatura:
            raise ValueError('MobilidadeAssinatura nao encontrada')

        cat_id = categoria_id or assinatura.categoria_id
        cc_id_resolvido, aviso_cc = resolver_categoria_cartao_para_mobilidade(
            categoria_id=cat_id,
            cartao_id=cartao_id,
            categoria_cartao_id_manual=categoria_cartao_id_manual,
        )
        if aviso_cc:
            avisos.append(aviso_cc)

        if criar_recorrencia and meio:
            recorrencia, avisos_rec = criar_recorrencia_assinatura(
                assinatura=assinatura,
                meio_pagamento=meio,
                cartao_id=cartao_id,
                categoria_cartao_id=cc_id_resolvido,
                data_inicio=data_inicio,
            )
            avisos.extend(avisos_rec)
            db.session.flush()
        elif criar_recorrencia and not meio:
            avisos.append('meio_pagamento nao informado — recorrencia de assinatura nao foi criada.')

    # 3. Gravar cenário ativo
    cenario = MobilidadeCenarioAtivo(
        tipo_modalidade=tipo,
        origem_id=origem_id or 0,
        ativo_desde=data_inicio,
        meio_pagamento=meio,
        cartao_id=cartao_id,
        categoria_id=cat_id,
        categoria_cartao_id=cc_id_resolvido,
        recorrencia_id=recorrencia.id if recorrencia else None,
        status='ATIVO',
    )
    db.session.add(cenario)
    db.session.flush()

    return {
        'cenario': cenario.to_dict(),
        'recorrencia': recorrencia.to_dict() if recorrencia else None,
        'anterior_inativado': anterior.id if anterior else None,
        'avisos': avisos,
    }


# ---------------------------------------------------------------------------
# Consulta do cenário ativo
# ---------------------------------------------------------------------------

def obter_modalidade_ativa() -> dict | None:
    cenario = MobilidadeCenarioAtivo.query.filter_by(status='ATIVO').first()
    if not cenario:
        return None
    resultado = cenario.to_dict()
    if cenario.tipo_modalidade == 'VEICULO' and cenario.origem_id:
        v = Veiculo.query.get(cenario.origem_id)
        resultado['nome_origem'] = v.nome if v else None
    elif cenario.tipo_modalidade == 'TRANSPORTE_APP' and cenario.origem_id:
        caminho = obter_config_transporte_app(cenario.origem_id)
        resultado['nome_origem'] = (caminho or {}).get('nome') or f'Caminho {cenario.origem_id}'
    elif cenario.tipo_modalidade == 'ASSINATURA' and cenario.origem_id:
        ass = MobilidadeAssinatura.query.get(cenario.origem_id)
        resultado['nome_origem'] = ass.nome if ass else None
    if cenario.recorrencia_id:
        rec = ItemDespesa.query.get(cenario.recorrencia_id)
        resultado['recorrencia'] = rec.to_dict() if rec else None
    return resultado


# ---------------------------------------------------------------------------
# CRUD de MobilidadeAssinatura (VEIC-2B)
# ---------------------------------------------------------------------------

def listar_assinaturas(apenas_ativas: bool = False) -> list[dict]:
    q = MobilidadeAssinatura.query
    if apenas_ativas:
        q = q.filter_by(status='ATIVO')
    return [a.to_dict() for a in q.order_by(MobilidadeAssinatura.nome).all()]


def criar_assinatura(payload: dict) -> MobilidadeAssinatura:
    nome = (payload.get('nome') or '').strip()
    if not nome:
        raise ValueError('nome e obrigatorio')
    valor = _to_decimal(payload.get('valor_mensal'))
    if not valor or valor <= 0:
        raise ValueError('valor_mensal deve ser > 0')

    ass = MobilidadeAssinatura(
        nome=nome,
        valor_mensal=valor,
        categoria_id=_to_int(payload.get('categoria_id')),
        status='ATIVO',
        metadata_json=payload.get('metadata_json'),
    )
    db.session.add(ass)
    db.session.flush()
    return ass


def atualizar_assinatura(assinatura_id: int, payload: dict) -> MobilidadeAssinatura:
    ass = MobilidadeAssinatura.query.get(assinatura_id)
    if not ass:
        raise ValueError('MobilidadeAssinatura nao encontrada')

    if 'nome' in payload:
        ass.nome = (payload['nome'] or '').strip() or ass.nome
    if 'valor_mensal' in payload:
        v = _to_decimal(payload['valor_mensal'])
        if v and v > 0:
            ass.valor_mensal = v
    if 'categoria_id' in payload:
        ass.categoria_id = _to_int(payload['categoria_id'])
    if 'status' in payload and payload['status'] in ('ATIVO', 'INATIVO'):
        ass.status = payload['status']
    if 'metadata_json' in payload:
        ass.metadata_json = payload['metadata_json']

    ass.updated_at = datetime.utcnow()
    db.session.add(ass)
    db.session.flush()
    return ass
