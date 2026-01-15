"""
Rotas da API para Módulo de Veículos (FASE 1 - projetivo)

IMPORTANTE:
- Projeção ≠ lançamento: estas rotas NUNCA criam despesas reais automaticamente.
- Categorias são as existentes: usamos categoria_id (FK categoria).
- Veículo é origem da despesa (origem_tipo='VEICULO', origem_id=veiculo.id).
"""

from datetime import date, datetime
from decimal import Decimal

from flask import Blueprint, jsonify, request
from dateutil.relativedelta import relativedelta

try:
    from backend.models import db, Veiculo, DespesaPrevista, VeiculoRegraManutencaoKm
    from backend.services.veiculo_service import (
        aplicar_defaults_categorias_veiculo,
        gerar_projecoes_mvp,
        limpar_projecoes_anteriores,
    )
    from backend.services.veiculo_uso_service import calcular_resumo_uso
    from backend.services.veiculo_manutencao_km_service import listar_estimativas, gerar_despesa_prevista_por_regra
    from backend.services.veiculo_financiamento_service import upsert_financiamento, obter_financiamento, remover_financiamento
except ImportError:
    from models import db, Veiculo, DespesaPrevista, VeiculoRegraManutencaoKm
    from services.veiculo_service import (
        aplicar_defaults_categorias_veiculo,
        gerar_projecoes_mvp,
        limpar_projecoes_anteriores,
    )
    from services.veiculo_uso_service import calcular_resumo_uso
    from services.veiculo_manutencao_km_service import listar_estimativas, gerar_despesa_prevista_por_regra
    from services.veiculo_financiamento_service import upsert_financiamento, obter_financiamento, remover_financiamento


veiculos_bp = Blueprint('veiculos', __name__)


def _ler_payload_request():
    dados = request.get_json(silent=True)
    if not dados:
        dados = request.form.to_dict()
    return dados or {}


def _parse_date(value):
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value)).date()
    except Exception:
        return None


def _parse_decimal(value):
    if value is None or (isinstance(value, str) and value.strip() == ''):
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _to_int(value):
    try:
        if value is None:
            return None
        if isinstance(value, str) and value.strip() == '':
            return None
        return int(value)
    except Exception:
        return None


def _validar_mes(mes):
    if mes is None:
        return True
    return 1 <= int(mes) <= 12


@veiculos_bp.route('', methods=['GET'])
def listar_veiculos():
    try:
        veiculos = Veiculo.query.order_by(Veiculo.id.desc()).all()
        return jsonify({'success': True, 'data': [v.to_dict() for v in veiculos], 'total': len(veiculos)}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@veiculos_bp.route('/<int:veiculo_id>', methods=['GET'])
def buscar_veiculo(veiculo_id):
    try:
        v = Veiculo.query.get(veiculo_id)
        if not v:
            return jsonify({'success': False, 'error': 'Veículo não encontrado'}), 404
        return jsonify({'success': True, 'data': v.to_dict()}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@veiculos_bp.route('', methods=['POST'])
def criar_veiculo():
    try:
        data = _ler_payload_request()

        nome = (data.get('nome') or '').strip()
        tipo = (data.get('tipo') or '').strip()
        combustivel = (data.get('combustivel') or '').strip()
        status = (data.get('status') or 'SIMULADO').strip().upper()
        autonomia = _parse_decimal(data.get('autonomia_km_l'))
        data_inicio = _parse_date(data.get('data_inicio'))

        if not nome:
            return jsonify({'success': False, 'error': 'Nome é obrigatório'}), 400
        if not tipo:
            return jsonify({'success': False, 'error': 'Tipo é obrigatório'}), 400
        if not combustivel:
            return jsonify({'success': False, 'error': 'Combustível é obrigatório'}), 400
        if autonomia is None or autonomia <= 0:
            return jsonify({'success': False, 'error': 'autonomia_km_l é obrigatório e deve ser > 0'}), 400
        if status not in ('SIMULADO', 'ATIVO'):
            return jsonify({'success': False, 'error': 'Status inválido (SIMULADO|ATIVO)'}), 400
        if status == 'ATIVO' and not data_inicio:
            return jsonify({'success': False, 'error': 'data_inicio é obrigatório para veículo ATIVO'}), 400

        v = Veiculo(
            nome=nome,
            tipo=tipo,
            combustivel=combustivel,
            autonomia_km_l=autonomia,
            status=status,
            data_inicio=data_inicio,
        )

        # Configurações (todas opcionais)
        v.categoria_combustivel_id = _to_int(data.get('categoria_combustivel_id'))
        v.combustivel_valor_mensal = _parse_decimal(data.get('combustivel_valor_mensal'))

        v.ipva_categoria_id = _to_int(data.get('ipva_categoria_id'))
        v.ipva_mes = _to_int(data.get('ipva_mes'))
        v.ipva_valor = _parse_decimal(data.get('ipva_valor'))

        v.seguro_categoria_id = _to_int(data.get('seguro_categoria_id'))
        v.seguro_mes = _to_int(data.get('seguro_mes'))
        v.seguro_valor = _parse_decimal(data.get('seguro_valor'))

        v.licenciamento_categoria_id = _to_int(data.get('licenciamento_categoria_id'))
        v.licenciamento_mes = _to_int(data.get('licenciamento_mes'))
        v.licenciamento_valor = _parse_decimal(data.get('licenciamento_valor'))

        v.preco_medio_combustivel = _parse_decimal(data.get('preco_medio_combustivel'))

        if not (_validar_mes(v.ipva_mes) and _validar_mes(v.seguro_mes) and _validar_mes(v.licenciamento_mes)):
            return jsonify({'success': False, 'error': 'Mês deve estar entre 1 e 12'}), 400

        db.session.add(v)

        # Defaults de categoria (sem criar categorias)
        aplicar_defaults_categorias_veiculo(v)

        # Projeções (apenas tabela despesa_prevista)
        gerar_projecoes_mvp(v, meses_futuros=int(data.get('meses_futuros') or 12))

        db.session.commit()

        return jsonify({'success': True, 'message': 'Veículo criado', 'data': v.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@veiculos_bp.route('/<int:veiculo_id>', methods=['PUT'])
def atualizar_veiculo(veiculo_id):
    try:
        v = Veiculo.query.get(veiculo_id)
        if not v:
            return jsonify({'success': False, 'error': 'Veículo não encontrado'}), 404

        data = _ler_payload_request()

        if 'nome' in data:
            v.nome = (data.get('nome') or '').strip()
        if 'tipo' in data:
            v.tipo = (data.get('tipo') or '').strip()
        if 'combustivel' in data:
            v.combustivel = (data.get('combustivel') or '').strip()
        if 'autonomia_km_l' in data:
            autonomia = _parse_decimal(data.get('autonomia_km_l'))
            if autonomia is None or autonomia <= 0:
                return jsonify({'success': False, 'error': 'autonomia_km_l deve ser > 0'}), 400
            v.autonomia_km_l = autonomia

        if 'status' in data:
            v.status = (data.get('status') or '').strip().upper()
            if v.status not in ('SIMULADO', 'ATIVO'):
                return jsonify({'success': False, 'error': 'Status inválido (SIMULADO|ATIVO)'}), 400

        if 'data_inicio' in data:
            v.data_inicio = _parse_date(data.get('data_inicio'))

        if v.status == 'ATIVO' and not v.data_inicio:
            return jsonify({'success': False, 'error': 'data_inicio é obrigatório para veículo ATIVO'}), 400

        # Configurações (opcionais)
        if 'categoria_combustivel_id' in data:
            v.categoria_combustivel_id = _to_int(data.get('categoria_combustivel_id'))
        if 'combustivel_valor_mensal' in data:
            v.combustivel_valor_mensal = _parse_decimal(data.get('combustivel_valor_mensal'))

        if 'ipva_categoria_id' in data:
            v.ipva_categoria_id = _to_int(data.get('ipva_categoria_id'))
        if 'ipva_mes' in data:
            v.ipva_mes = _to_int(data.get('ipva_mes'))
        if 'ipva_valor' in data:
            v.ipva_valor = _parse_decimal(data.get('ipva_valor'))

        if 'seguro_categoria_id' in data:
            v.seguro_categoria_id = _to_int(data.get('seguro_categoria_id'))
        if 'seguro_mes' in data:
            v.seguro_mes = _to_int(data.get('seguro_mes'))
        if 'seguro_valor' in data:
            v.seguro_valor = _parse_decimal(data.get('seguro_valor'))

        if 'licenciamento_categoria_id' in data:
            v.licenciamento_categoria_id = _to_int(data.get('licenciamento_categoria_id'))
        if 'licenciamento_mes' in data:
            v.licenciamento_mes = _to_int(data.get('licenciamento_mes'))
        if 'licenciamento_valor' in data:
            v.licenciamento_valor = _parse_decimal(data.get('licenciamento_valor'))

        if 'preco_medio_combustivel' in data:
            v.preco_medio_combustivel = _parse_decimal(data.get('preco_medio_combustivel'))

        if not (_validar_mes(v.ipva_mes) and _validar_mes(v.seguro_mes) and _validar_mes(v.licenciamento_mes)):
            return jsonify({'success': False, 'error': 'Mês deve estar entre 1 e 12'}), 400

        aplicar_defaults_categorias_veiculo(v)

        gerar_projecoes_mvp(v, meses_futuros=int(data.get('meses_futuros') or 12))

        db.session.commit()
        return jsonify({'success': True, 'message': 'Veículo atualizado', 'data': v.to_dict()}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@veiculos_bp.route('/<int:veiculo_id>', methods=['DELETE'])
def deletar_veiculo(veiculo_id):
    try:
        v = Veiculo.query.get(veiculo_id)
        if not v:
            return jsonify({'success': False, 'error': 'Veículo não encontrado'}), 404

        # Remover projeções associadas (origem = VEICULO)
        DespesaPrevista.query.filter(
            DespesaPrevista.origem_tipo == 'VEICULO',
            DespesaPrevista.origem_id == veiculo_id
        ).delete(synchronize_session=False)

        db.session.delete(v)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Veículo deletado'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@veiculos_bp.route('/<int:veiculo_id>/converter', methods=['POST'])
def converter_simulado_para_ativo(veiculo_id):
    """
    Conversão explícita e confirmada no frontend.
    Não cria histórico retroativo e não cria lançamentos reais.
    """
    try:
        v = Veiculo.query.get(veiculo_id)
        if not v:
            return jsonify({'success': False, 'error': 'Veículo não encontrado'}), 404
        if v.status != 'SIMULADO':
            return jsonify({'success': False, 'error': 'Apenas veículos SIMULADO podem ser convertidos'}), 400

        data = _ler_payload_request()
        data_inicio = _parse_date(data.get('data_inicio')) or date.today()

        v.status = 'ATIVO'
        v.data_inicio = data_inicio

        aplicar_defaults_categorias_veiculo(v)
        limpar_projecoes_anteriores(v.id, data_inicio)
        gerar_projecoes_mvp(v, meses_futuros=int(data.get('meses_futuros') or 12))

        db.session.commit()
        return jsonify({'success': True, 'message': 'Veículo convertido para ATIVO', 'data': v.to_dict()}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@veiculos_bp.route('/<int:veiculo_id>/projecoes', methods=['GET'])
def listar_projecoes(veiculo_id):
    try:
        v = Veiculo.query.get(veiculo_id)
        if not v:
            return jsonify({'success': False, 'error': 'Veículo não encontrado'}), 404

        # Por padrão: próximas 24 competências a partir do mês atual
        meses = request.args.get('meses', default=24, type=int)
        if meses < 1:
            meses = 1
        inicio = date.today().replace(day=1)
        fim = (inicio + relativedelta(months=meses)).replace(day=1)

        proj = DespesaPrevista.query.filter(
            DespesaPrevista.origem_tipo == 'VEICULO',
            DespesaPrevista.origem_id == veiculo_id,
            DespesaPrevista.data_prevista >= inicio,
            DespesaPrevista.data_prevista < fim,
        ).order_by(DespesaPrevista.data_prevista.asc(), DespesaPrevista.id.asc()).all()

        return jsonify({'success': True, 'data': [p.to_dict() for p in proj], 'total': len(proj)}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@veiculos_bp.route('/<int:veiculo_id>/projecoes/gerar', methods=['POST'])
def gerar_projecoes(veiculo_id):
    try:
        v = Veiculo.query.get(veiculo_id)
        if not v:
            return jsonify({'success': False, 'error': 'Veículo não encontrado'}), 404

        data = _ler_payload_request()
        meses = int(data.get('meses_futuros') or 12)

        aplicar_defaults_categorias_veiculo(v)
        criadas = gerar_projecoes_mvp(v, meses_futuros=meses)
        db.session.commit()

        return jsonify({'success': True, 'message': 'Projeções geradas', 'criadas': len(criadas)}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@veiculos_bp.route('/<int:veiculo_id>/uso', methods=['GET'])
def obter_resumo_uso(veiculo_id):
    """
    FASE 3: Exposição informativa de uso estimado via consumo (sem alterar histórico).
    """
    try:
        janela = request.args.get('janela_meses', default=3, type=int)
        resumo = calcular_resumo_uso(veiculo_id, janela_meses=janela)
        return jsonify({'success': True, 'data': resumo}), 200
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@veiculos_bp.route('/<int:veiculo_id>/regras-km', methods=['GET'])
def listar_regras_km(veiculo_id):
    try:
        regras = VeiculoRegraManutencaoKm.query.filter_by(veiculo_id=veiculo_id).order_by(VeiculoRegraManutencaoKm.id.asc()).all()
        return jsonify({'success': True, 'data': [r.to_dict() for r in regras], 'total': len(regras)}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@veiculos_bp.route('/<int:veiculo_id>/regras-km', methods=['POST'])
def criar_regra_km(veiculo_id):
    try:
        data = _ler_payload_request()
        tipo_evento = (data.get('tipo_evento') or '').strip().upper()
        intervalo_km = _to_int(data.get('intervalo_km'))
        meses_intervalo = _to_int(data.get('meses_intervalo'))
        custo_estimado = _parse_decimal(data.get('custo_estimado'))
        categoria_id = _to_int(data.get('categoria_id'))
        ativo = data.get('ativo', True)

        if not tipo_evento:
            return jsonify({'success': False, 'error': 'tipo_evento é obrigatório'}), 400
        if not intervalo_km or intervalo_km <= 0:
            return jsonify({'success': False, 'error': 'intervalo_km deve ser > 0'}), 400
        if meses_intervalo is not None and meses_intervalo <= 0:
            return jsonify({'success': False, 'error': 'meses_intervalo deve ser > 0 (quando informado)'}), 400
        if custo_estimado is None or custo_estimado <= 0:
            return jsonify({'success': False, 'error': 'custo_estimado deve ser > 0'}), 400
        if not categoria_id:
            return jsonify({'success': False, 'error': 'categoria_id é obrigatório'}), 400

        regra = VeiculoRegraManutencaoKm(
            veiculo_id=veiculo_id,
            tipo_evento=tipo_evento,
            intervalo_km=intervalo_km,
            meses_intervalo=meses_intervalo,
            custo_estimado=custo_estimado,
            categoria_id=categoria_id,
            ativo=bool(ativo),
        )
        db.session.add(regra)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Regra criada', 'data': regra.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@veiculos_bp.route('/<int:veiculo_id>/regras-km/<int:regra_id>', methods=['DELETE'])
def deletar_regra_km(veiculo_id, regra_id):
    try:
        regra = VeiculoRegraManutencaoKm.query.filter_by(id=regra_id, veiculo_id=veiculo_id).first()
        if not regra:
            return jsonify({'success': False, 'error': 'Regra não encontrada'}), 404
        db.session.delete(regra)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Regra removida'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@veiculos_bp.route('/<int:veiculo_id>/manutencoes-km', methods=['GET'])
def obter_manutencoes_km(veiculo_id):
    try:
        janela = request.args.get('janela_meses', default=3, type=int)
        data = listar_estimativas(veiculo_id, janela_meses=janela)
        return jsonify({'success': True, 'data': data}), 200
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@veiculos_bp.route('/<int:veiculo_id>/manutencoes-km/gerar', methods=['POST'])
def gerar_manutencao_km(veiculo_id):
    """
    Gera UMA despesa prevista por km, controlada (sem cascata e sem múltiplas ocorrências futuras).
    """
    try:
        payload = _ler_payload_request()
        regra_id = _to_int(payload.get('regra_id'))
        if not regra_id:
            return jsonify({'success': False, 'error': 'regra_id é obrigatório'}), 400

        desp = gerar_despesa_prevista_por_regra(veiculo_id, regra_id, janela_meses=int(payload.get('janela_meses') or 3))
        db.session.commit()
        if not desp:
            return jsonify({'success': True, 'message': 'Nenhuma manutenção gerada (uso insuficiente ou já existe evento ativo)'}), 200
        return jsonify({'success': True, 'message': 'Manutenção prevista gerada', 'data': desp.to_dict()}), 201
    except ValueError as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@veiculos_bp.route('/<int:veiculo_id>/financiamento', methods=['GET'])
def obter_financiamento_veiculo(veiculo_id):
    try:
        fin = obter_financiamento(veiculo_id)
        return jsonify({'success': True, 'data': fin.to_dict() if fin else None}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@veiculos_bp.route('/<int:veiculo_id>/financiamento', methods=['POST'])
def salvar_financiamento_veiculo(veiculo_id):
    """
    FASE 6: financiamento projetivo (simulação). Não cria lançamentos reais.
    Recalcula e recria apenas parcelas PREVISTAS (não toca em CONFIRMADA/ADIADA/IGNORADA).
    """
    try:
        data = _ler_payload_request()
        resultado = upsert_financiamento(veiculo_id, data)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Financiamento simulado atualizado', **resultado}), 200
    except ValueError as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@veiculos_bp.route('/<int:veiculo_id>/financiamento', methods=['DELETE'])
def deletar_financiamento_veiculo(veiculo_id):
    try:
        removidos = remover_financiamento(veiculo_id)
        db.session.commit()
        if not removidos:
            return jsonify({'success': True, 'message': 'Nenhum financiamento encontrado'}), 200
        return jsonify({'success': True, 'message': 'Financiamento removido (simulação)'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
