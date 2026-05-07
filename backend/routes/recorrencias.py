"""
Rotas da API para cadastros-matriz de recorrencias.

Este modulo gerencia apenas regras recorrentes baseadas em ItemDespesa.
Despesas geradas continuam sendo expostas por /api/despesas.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal

from flask import Blueprint, jsonify, request
from dateutil.relativedelta import relativedelta
from sqlalchemy import or_

try:
    from backend.models import db, ItemDespesa, Categoria, ContaBancaria
    from backend.services.categoria_cartao_service import CategoriaCartaoService
    from backend.services.perfil_financeiro_service import PerfilFinanceiroService
    from backend.routes.despesas import calcular_competencia, gerar_execucao_despesa_recorrente
except ImportError:
    from models import db, ItemDespesa, Categoria, ContaBancaria
    from services.categoria_cartao_service import CategoriaCartaoService
    from services.perfil_financeiro_service import PerfilFinanceiroService
    from routes.despesas import calcular_competencia, gerar_execucao_despesa_recorrente


recorrencias_bp = Blueprint('recorrencias', __name__)


def _to_int(value):
    try:
        if value is None:
            return None
        if isinstance(value, str) and value.strip() == '':
            return None
        return int(value)
    except Exception:
        return None


def _to_decimal(value):
    if value is None or value == '':
        return None
    return Decimal(str(value))


def _dia_semana_ui_para_python(value):
    dia_semana = _to_int(value)
    if dia_semana is None:
        return None
    # UI e storage usam 0=domingo; date.weekday() usa 0=segunda.
    return (dia_semana - 1) % 7


def _to_date(value):
    if not value:
        return None
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value)[:10], '%Y-%m-%d').date()


def _normalizar_meio_pagamento(value):
    return (value or '').strip().lower() or None


def _validar_conta_bancaria_debito_automatico(dados, meio_pagamento, conta_atual_id=None):
    if meio_pagamento != 'debito_automatico':
        return None

    conta_id = _to_int(dados.get('conta_bancaria_id')) if 'conta_bancaria_id' in dados else _to_int(conta_atual_id)
    if not conta_id:
        raise ValueError('Conta bancária é obrigatória para recorrência em débito automático.')

    conta = ContaBancaria.query.filter(
        ContaBancaria.id == conta_id,
        ContaBancaria.status == 'ATIVO',
        PerfilFinanceiroService.condicao_perfil(ContaBancaria),
    ).first()
    if not conta:
        raise ValueError('Conta bancária não encontrada no perfil financeiro ativo.')
    return conta.id


def _normalizar_tipo_recorrencia(dados):
    tipo = (dados.get('tipo_recorrencia') or dados.get('frequencia') or 'mensal').strip()

    if tipo == 'quinzenal':
        tipo = 'semanal'
        dados = {**dados, 'frequencia_semanas': 2}

    if tipo == 'semanal':
        dia_semana = _to_int(dados.get('dia_semana'))
        frequencia = _to_int(dados.get('frequencia_semanas')) or 1
        if dia_semana is None:
            raise ValueError('dia_semana e obrigatorio para recorrencia semanal ou quinzenal.')
        if dia_semana < 0 or dia_semana > 6:
            raise ValueError('dia_semana deve estar entre 0 e 6.')
        if frequencia < 1:
            frequencia = 1
        return f'semanal_{frequencia}_{dia_semana}'

    if tipo in ('mensal', 'anual', 'a_cada_2_semanas'):
        return tipo

    if tipo.startswith('semanal_'):
        return tipo

    return 'mensal'


def _perfil_id():
    return PerfilFinanceiroService.obter_perfil_ativo_id()


def _detalhes_frequencia(tipo_recorrencia):
    tipo = tipo_recorrencia or 'mensal'
    if tipo == 'mensal':
        return {'frequencia': 'mensal', 'dia_semana': None, 'intervalo_semanas': None}
    if tipo == 'anual':
        return {'frequencia': 'anual', 'dia_semana': None, 'intervalo_semanas': None}
    if tipo == 'a_cada_2_semanas':
        return {'frequencia': 'quinzenal', 'dia_semana': None, 'intervalo_semanas': 2}
    if tipo.startswith('semanal_'):
        partes = tipo.split('_')
        intervalo = _to_int(partes[1]) if len(partes) > 1 else 1
        dia_semana = _to_int(partes[2]) if len(partes) > 2 else None
        return {
            'frequencia': 'quinzenal' if intervalo == 2 else 'semanal',
            'dia_semana': dia_semana,
            'intervalo_semanas': intervalo or 1,
        }
    if tipo == 'semanal':
        return {'frequencia': 'semanal', 'dia_semana': None, 'intervalo_semanas': 1}
    return {'frequencia': tipo, 'dia_semana': None, 'intervalo_semanas': None}


def _proximo_vencimento(item):
    if not item.data_vencimento:
        return None

    hoje = date.today()
    atual = item.data_vencimento
    tipo = item.tipo_recorrencia or 'mensal'

    if tipo == 'mensal':
        if atual >= hoje:
            return atual
        while atual < hoje:
            atual += relativedelta(months=1)
        return atual

    if tipo == 'anual':
        if atual >= hoje:
            return atual
        while atual < hoje:
            atual += relativedelta(years=1)
        return atual

    if tipo == 'a_cada_2_semanas':
        if atual >= hoje:
            return atual
        while atual < hoje:
            atual += timedelta(weeks=2)
        return atual

    if tipo == 'semanal' or tipo.startswith('semanal_'):
        detalhes = _detalhes_frequencia(tipo)
        intervalo = detalhes.get('intervalo_semanas') or 1
        dia_semana = detalhes.get('dia_semana')
        if dia_semana is not None:
            dia_semana_python = _dia_semana_ui_para_python(dia_semana)
            dias_ate_alvo = (dia_semana_python - atual.weekday()) % 7
            atual += timedelta(days=dias_ate_alvo)
        if atual >= hoje:
            return atual
        while atual < hoje:
            atual += timedelta(weeks=intervalo)
        return atual

    if atual >= hoje:
        return atual

    return None


def _item_to_dict(item):
    detalhes = _detalhes_frequencia(item.tipo_recorrencia)
    proximo = _proximo_vencimento(item)
    categoria = item.categoria

    return {
        'id': item.id,
        'tipo': 'recorrencia_simples',
        'tipo_visual': 'Recorrencia',
        'nome': item.nome,
        'descricao': item.descricao,
        'valor': float(item.valor) if item.valor is not None else None,
        'categoria_id': item.categoria_id,
        'categoria_nome': categoria.nome if categoria else None,
        'categoria_icone': categoria.icone if categoria else None,
        'recorrente': bool(item.recorrente),
        'tipo_recorrencia': item.tipo_recorrencia,
        'frequencia': detalhes['frequencia'],
        'dia_semana': detalhes['dia_semana'],
        'frequencia_semanas': detalhes['intervalo_semanas'],
        'meio_pagamento': item.meio_pagamento,
        'cartao_id': item.cartao_id,
        'conta_bancaria_id': item.conta_bancaria_id,
        'conta_bancaria_nome': item.conta_bancaria.nome if item.conta_bancaria else None,
        'categoria_cartao_id': item.categoria_cartao_id,
        'categoria_cartao_nome': item.categoria_cartao.nome if item.categoria_cartao else None,
        'ativo': bool(item.ativo),
        'status': 'Ativa' if item.ativo else 'Inativa',
        'data_vencimento': item.data_vencimento.isoformat() if item.data_vencimento else None,
        'mes_competencia': item.mes_competencia,
        'proximo_vencimento': proximo.isoformat() if proximo else None,
    }


def _query_recorrencias():
    return PerfilFinanceiroService.aplicar_perfil_query(ItemDespesa.query, ItemDespesa).filter(
        ItemDespesa.recorrente == True,  # noqa: E712
        or_(ItemDespesa.tipo.is_(None), ItemDespesa.tipo != 'Consorcio'),
    )


@recorrencias_bp.route('', methods=['GET'])
@recorrencias_bp.route('/', methods=['GET'])
def listar_recorrencias():
    try:
        status = (request.args.get('status') or 'ativas').lower()
        query = _query_recorrencias()

        if status == 'ativas':
            query = query.filter(ItemDespesa.ativo == True)  # noqa: E712
        elif status == 'inativas':
            query = query.filter(ItemDespesa.ativo == False)  # noqa: E712

        itens = query.order_by(ItemDespesa.nome.asc()).all()
        return jsonify({
            'success': True,
            'data': [_item_to_dict(item) for item in itens],
            'total': len(itens),
        }), 200
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500


@recorrencias_bp.route('/<int:item_id>', methods=['GET'])
def obter_recorrencia(item_id):
    item = _query_recorrencias().filter(ItemDespesa.id == item_id).first()
    if not item:
        return jsonify({'success': False, 'error': 'Recorrencia nao encontrada'}), 404
    return jsonify({'success': True, 'data': _item_to_dict(item)}), 200


@recorrencias_bp.route('', methods=['POST'])
@recorrencias_bp.route('/', methods=['POST'])
def criar_recorrencia():
    try:
        dados = request.get_json(silent=True) or {}
        nome = (dados.get('nome') or '').strip()
        valor = _to_decimal(dados.get('valor'))
        categoria_id = _to_int(dados.get('categoria_id'))
        data_vencimento = _to_date(dados.get('data_vencimento'))

        if not nome:
            return jsonify({'success': False, 'error': 'Nome e obrigatorio'}), 400
        if valor is None:
            return jsonify({'success': False, 'error': 'Valor e obrigatorio'}), 400
        if not categoria_id:
            return jsonify({'success': False, 'error': 'Categoria e obrigatoria'}), 400
        if not Categoria.query.get(categoria_id):
            return jsonify({'success': False, 'error': 'Categoria nao encontrada'}), 404

        tipo_recorrencia = _normalizar_tipo_recorrencia(dados)
        mes_competencia = dados.get('mes_competencia')
        if not mes_competencia and data_vencimento:
            mes_competencia = calcular_competencia(data_vencimento)

        meio_pagamento = _normalizar_meio_pagamento(dados.get('meio_pagamento'))
        cartao_id = _to_int(dados.get('cartao_id'))
        categoria_cartao_id = None
        conta_bancaria_id = _validar_conta_bancaria_debito_automatico(dados, meio_pagamento)

        if meio_pagamento == 'cartao' and cartao_id:
            resolucao_cartao = CategoriaCartaoService.resolver_categoria_cartao_para_lancamento(
                cartao_id=cartao_id,
                categoria_id=categoria_id,
                categoria_cartao_id=None,
            )
            categoria_cartao_id = resolucao_cartao.get('categoria_cartao_id')
        else:
            cartao_id = None
            categoria_cartao_id = None

        item = ItemDespesa(
            perfil_financeiro_id=_perfil_id(),
            nome=nome,
            descricao=dados.get('descricao'),
            valor=valor,
            data_vencimento=data_vencimento,
            categoria_id=categoria_id,
            pago=False,
            recorrente=True,
            tipo_recorrencia=tipo_recorrencia,
            mes_competencia=mes_competencia,
            tipo='Simples',
            meio_pagamento=meio_pagamento,
            cartao_id=cartao_id,
            conta_bancaria_id=conta_bancaria_id,
            item_agregado_id=None,
            categoria_cartao_id=categoria_cartao_id,
        )
        db.session.add(item)
        db.session.flush()

        gerar_execucao_despesa_recorrente(item.id, meses_futuros=1, mes_referencia=None)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Recorrencia criada com sucesso',
            'data': _item_to_dict(item),
        }), 201
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(exc)}), 500


@recorrencias_bp.route('/<int:item_id>', methods=['PUT'])
def atualizar_recorrencia(item_id):
    try:
        item = _query_recorrencias().filter(ItemDespesa.id == item_id).first()
        if not item:
            return jsonify({'success': False, 'error': 'Recorrencia nao encontrada'}), 404

        dados = request.get_json(silent=True) or {}

        if 'nome' in dados:
            item.nome = (dados.get('nome') or '').strip() or item.nome
        if 'descricao' in dados:
            item.descricao = dados.get('descricao')
        if 'valor' in dados:
            valor = _to_decimal(dados.get('valor'))
            if valor is not None:
                item.valor = valor
        if 'categoria_id' in dados:
            categoria_id = _to_int(dados.get('categoria_id'))
            if categoria_id and Categoria.query.get(categoria_id):
                item.categoria_id = categoria_id
        if 'data_vencimento' in dados:
            item.data_vencimento = _to_date(dados.get('data_vencimento'))
            if item.data_vencimento and not dados.get('mes_competencia'):
                item.mes_competencia = calcular_competencia(item.data_vencimento)
        if 'tipo_recorrencia' in dados or 'frequencia' in dados:
            item.tipo_recorrencia = _normalizar_tipo_recorrencia(dados)
        if 'meio_pagamento' in dados:
            item.meio_pagamento = _normalizar_meio_pagamento(dados.get('meio_pagamento'))
        if 'cartao_id' in dados:
            item.cartao_id = _to_int(dados.get('cartao_id'))
        if 'ativo' in dados:
            item.ativo = bool(dados.get('ativo'))

        item.conta_bancaria_id = _validar_conta_bancaria_debito_automatico(
            dados,
            item.meio_pagamento,
            conta_atual_id=item.conta_bancaria_id,
        )

        if item.meio_pagamento == 'cartao' and item.cartao_id:
            resolucao_cartao = CategoriaCartaoService.resolver_categoria_cartao_para_lancamento(
                cartao_id=item.cartao_id,
                categoria_id=item.categoria_id,
                categoria_cartao_id=None,
            )
            item.categoria_cartao_id = resolucao_cartao.get('categoria_cartao_id')
            item.item_agregado_id = None
        else:
            item.cartao_id = None
            item.item_agregado_id = None
            item.categoria_cartao_id = None

        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Recorrencia atualizada com sucesso',
            'data': _item_to_dict(item),
        }), 200
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(exc)}), 500


@recorrencias_bp.route('/<int:item_id>', methods=['DELETE'])
def inativar_recorrencia(item_id):
    try:
        item = _query_recorrencias().filter(ItemDespesa.id == item_id).first()
        if not item:
            return jsonify({'success': False, 'error': 'Recorrencia nao encontrada'}), 404

        item.ativo = False
        db.session.commit()
        return jsonify({'success': True, 'message': 'Recorrencia inativada com sucesso'}), 200
    except Exception as exc:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(exc)}), 500
