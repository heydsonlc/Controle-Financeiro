"""
Rotas para gerenciamento de Consórcios
"""
from flask import Blueprint, request, jsonify
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
import re
from dateutil.relativedelta import relativedelta
from sqlalchemy import or_

try:
    from backend.models import db, ContratoConsorcio, ItemDespesa, Categoria, Conta
    from backend.services.consorcio_receita_service import (
        gerar_ou_atualizar_receita_contemplacao,
        perfil_id_consorcio,
        receitas_por_marcador,
        marcador_consorcio,
        _receita_tem_movimento,
        _remover_marcador,
    )
    from backend.services.perfil_financeiro_service import PerfilFinanceiroService
except ImportError:
    from models import db, ContratoConsorcio, ItemDespesa, Categoria, Conta
    from services.consorcio_receita_service import (
        gerar_ou_atualizar_receita_contemplacao,
        perfil_id_consorcio,
        receitas_por_marcador,
        marcador_consorcio,
        _receita_tem_movimento,
        _remover_marcador,
    )
    from services.perfil_financeiro_service import PerfilFinanceiroService

consorcios_bp = Blueprint('consorcios', __name__, url_prefix='/api/consorcios')

MOEDA_QUANT = Decimal('0.01')


def _to_int(valor):
    if valor is None or valor == '':
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _normalizar_meio_pagamento(valor):
    return (valor or '').strip().lower() or None


def _decimal(valor, padrao='0'):
    if valor is None or valor == '':
        valor = padrao
    return Decimal(str(valor))


def _quantizar_moeda(valor):
    return _decimal(valor).quantize(MOEDA_QUANT, rounding=ROUND_HALF_UP)


def _data_base_de_valor(valor):
    if not valor:
        return None
    if isinstance(valor, datetime):
        return valor.date().replace(day=1)
    if isinstance(valor, date):
        return valor.replace(day=1)

    texto = str(valor).strip()
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', texto):
        return datetime.strptime(texto, '%Y-%m-%d').date().replace(day=1)
    if re.fullmatch(r'\d{4}-\d{2}', texto):
        return datetime.strptime(f'{texto}-01', '%Y-%m-%d').date()
    if re.fullmatch(r'\d{1,2}/\d{4}', texto):
        mes, ano = texto.split('/')
        return date(int(ano), int(mes), 1)
    return None


def _mes_numerico(valor):
    if valor is None or valor == '':
        return None
    if isinstance(valor, int):
        return valor if 1 <= valor <= 12 else None
    texto = str(valor).strip()
    if re.fullmatch(r'\d{1,2}', texto):
        mes = int(texto)
        return mes if 1 <= mes <= 12 else None
    return None


def normalizar_mes_referencia(valor, data_base=None, campo='mes_inicio'):
    if valor is None or valor == '':
        return None
    if isinstance(valor, datetime):
        return valor.date().replace(day=1)
    if isinstance(valor, date):
        return valor.replace(day=1)

    texto = str(valor).strip()
    label = 'inicio' if campo == 'mes_inicio' else 'contemplacao'

    try:
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', texto):
            return datetime.strptime(texto, '%Y-%m-%d').date().replace(day=1)
        if re.fullmatch(r'\d{4}-\d{2}', texto):
            return datetime.strptime(f'{texto}-01', '%Y-%m-%d').date()
        if re.fullmatch(r'\d{1,2}/\d{4}', texto):
            mes, ano = texto.split('/')
            mes_int = int(mes)
            if mes_int < 1 or mes_int > 12:
                raise ValueError
            return date(int(ano), mes_int, 1)
        if re.fullmatch(r'\d{1,2}', texto):
            mes_int = int(texto)
            if mes_int < 1 or mes_int > 12:
                raise ValueError
            base = data_base or date.today()
            if isinstance(base, datetime):
                ano = base.year
                mes_base = base.month
            elif isinstance(base, date):
                ano = base.year
                mes_base = base.month
            else:
                ano = date.today().year
                mes_base = date.today().month
            if campo == 'mes_contemplacao' and mes_int < mes_base:
                ano += 1
            return date(ano, mes_int, 1)
    except ValueError:
        raise ValueError(f'Mes de {label} invalido. Informe um mes entre 1 e 12.')

    raise ValueError(f'Mes de {label} invalido. Informe uma data no formato YYYY-MM, YYYY-MM-DD ou mes entre 1 e 12.')


def calcular_posicao_contemplacao(mes_inicio, mes_contemplacao, numero_parcelas):
    if not mes_contemplacao:
        return None

    diferenca_meses = (
        (mes_contemplacao.year - mes_inicio.year) * 12
        + (mes_contemplacao.month - mes_inicio.month)
    )
    posicao = diferenca_meses + 1

    if posicao < 1 or posicao > numero_parcelas:
        raise ValueError('Mes de contemplacao deve estar dentro do periodo do consorcio.')
    return posicao


def calcular_valor_parcela_consorcio(valor_inicial, tipo_reajuste, valor_reajuste, posicao):
    base = _decimal(valor_inicial)
    reajuste = _decimal(valor_reajuste)
    passos = Decimal(posicao - 1)

    if tipo_reajuste == 'fixo' and reajuste > 0:
        return _quantizar_moeda(base + (passos * reajuste))
    if tipo_reajuste == 'percentual' and reajuste > 0:
        fator = Decimal('1') + ((passos * reajuste) / Decimal('100'))
        return _quantizar_moeda(base * fator)
    return _quantizar_moeda(base)


def calcular_valor_premio(valor_inicial, numero_parcelas, tipo_reajuste, valor_reajuste, posicao_contemplacao):
    if not posicao_contemplacao:
        return None
    parcela = calcular_valor_parcela_consorcio(
        valor_inicial,
        tipo_reajuste,
        valor_reajuste,
        posicao_contemplacao,
    )
    return _quantizar_moeda(parcela * Decimal(numero_parcelas))


def normalizar_pagamento_consorcio(dados):
    meio_pagamento = _normalizar_meio_pagamento(dados.get('meio_pagamento'))
    cartao_id = _to_int(dados.get('cartao_id'))
    conta_bancaria_id = _to_int(dados.get('conta_bancaria_id'))
    categoria_cartao_id = _to_int(dados.get('categoria_cartao_id'))

    if meio_pagamento != 'cartao':
        cartao_id = None
        categoria_cartao_id = None

    if meio_pagamento != 'debito_automatico':
        conta_bancaria_id = None

    return {
        'meio_pagamento': meio_pagamento,
        'cartao_id': cartao_id,
        'conta_bancaria_id': conta_bancaria_id,
        'categoria_cartao_id': categoria_cartao_id,
    }


def pagamento_de_parcela(parcela):
    if not parcela:
        return {
            'meio_pagamento': None,
            'cartao_id': None,
            'conta_bancaria_id': None,
            'categoria_cartao_id': None,
        }
    return {
        'meio_pagamento': parcela.meio_pagamento,
        'cartao_id': parcela.cartao_id,
        'conta_bancaria_id': parcela.conta_bancaria_id,
        'categoria_cartao_id': parcela.categoria_cartao_id,
    }


def query_parcelas_consorcio(consorcio, nomes=None):
    nomes_consorcio = [nome for nome in (nomes or [consorcio.nome]) if nome]
    if not nomes_consorcio:
        nomes_consorcio = [consorcio.nome]
    filtros_nome = [ItemDespesa.nome.like(f"{nome} - Parcela%") for nome in nomes_consorcio]
    perfil_id = perfil_id_consorcio(consorcio)
    return ItemDespesa.query.filter(
        ItemDespesa.tipo == 'Consorcio',
        PerfilFinanceiroService.condicao_perfil(ItemDespesa, perfil_id),
        or_(*filtros_nome),
    )


def primeira_parcela_consorcio(consorcio):
    return query_parcelas_consorcio(consorcio).order_by(ItemDespesa.data_vencimento, ItemDespesa.id).first()


def aplicar_pagamento_parcela(parcela, pagamento):
    meio_pagamento = pagamento.get('meio_pagamento')
    parcela.meio_pagamento = meio_pagamento
    parcela.cartao_id = pagamento.get('cartao_id') if meio_pagamento == 'cartao' else None
    parcela.categoria_cartao_id = pagamento.get('categoria_cartao_id') if meio_pagamento == 'cartao' else None
    parcela.conta_bancaria_id = pagamento.get('conta_bancaria_id') if meio_pagamento == 'debito_automatico' else None


def aplicar_pagamento_conta(conta, pagamento):
    meio_pagamento = pagamento.get('meio_pagamento')
    conta.debito_automatico = meio_pagamento == 'debito_automatico'
    conta.conta_bancaria_id = pagamento.get('conta_bancaria_id') if meio_pagamento == 'debito_automatico' else None


def atualizar_pagamento_parcelas_consorcio(consorcio, pagamento, nomes=None):
    parcelas = query_parcelas_consorcio(consorcio, nomes=nomes).all()
    for parcela in parcelas:
        aplicar_pagamento_parcela(parcela, pagamento)
        conta = Conta.query.filter_by(item_despesa_id=parcela.id).first()
        if conta:
            aplicar_pagamento_conta(conta, pagamento)
    return parcelas


def consorcio_to_dict(consorcio):
    dados = consorcio.to_dict()
    parcela = primeira_parcela_consorcio(consorcio)
    pagamento = pagamento_de_parcela(parcela)
    dados.update(pagamento)
    dados['categoria_id'] = parcela.categoria_id if parcela else None
    dados['categoria_nome'] = parcela.categoria.nome if parcela and parcela.categoria else None
    return dados


def normalizar_dados_consorcio(dados, consorcio_atual=None):
    numero_parcelas = int(dados.get('numero_parcelas') or getattr(consorcio_atual, 'numero_parcelas', 0) or 0)
    if numero_parcelas < 1:
        raise ValueError('Numero de parcelas deve ser maior que zero.')

    valor_inicial = _quantizar_moeda(dados.get('valor_inicial', getattr(consorcio_atual, 'valor_inicial', 0)))
    tipo_reajuste = dados.get('tipo_reajuste', getattr(consorcio_atual, 'tipo_reajuste', 'nenhum') or 'nenhum')
    valor_reajuste = _quantizar_moeda(dados.get('valor_reajuste', getattr(consorcio_atual, 'valor_reajuste', 0)))

    valor_mes_inicio = dados.get('mes_inicio', getattr(consorcio_atual, 'mes_inicio', None))
    valor_mes_contemplacao = dados.get('mes_contemplacao', getattr(consorcio_atual, 'mes_contemplacao', None))
    data_base_inicial = (
        _data_base_de_valor(dados.get('data_inicial'))
        or _data_base_de_valor(dados.get('data_vencimento'))
    )
    data_base_contemplacao = _data_base_de_valor(valor_mes_contemplacao)
    mes_inicio_numerico = _mes_numerico(valor_mes_inicio)

    base_para_inicio = data_base_inicial or getattr(consorcio_atual, 'mes_inicio', None)
    if not base_para_inicio and data_base_contemplacao:
        if mes_inicio_numerico and mes_inicio_numerico > data_base_contemplacao.month:
            base_para_inicio = date(data_base_contemplacao.year - 1, mes_inicio_numerico, 1)
        else:
            base_para_inicio = data_base_contemplacao
    if not base_para_inicio:
        base_para_inicio = date.today()
    if not valor_mes_inicio and data_base_inicial:
        valor_mes_inicio = data_base_inicial

    mes_inicio = normalizar_mes_referencia(
        valor_mes_inicio,
        data_base=base_para_inicio,
        campo='mes_inicio',
    )
    if not mes_inicio:
        raise ValueError('Mes de inicio e obrigatorio.')

    mes_contemplacao = normalizar_mes_referencia(
        valor_mes_contemplacao,
        data_base=mes_inicio,
        campo='mes_contemplacao',
    )
    posicao = calcular_posicao_contemplacao(mes_inicio, mes_contemplacao, numero_parcelas)
    valor_premio = calcular_valor_premio(
        valor_inicial,
        numero_parcelas,
        tipo_reajuste,
        valor_reajuste,
        posicao,
    )

    return {
        'valor_inicial': float(valor_inicial),
        'tipo_reajuste': tipo_reajuste,
        'valor_reajuste': float(valor_reajuste),
        'numero_parcelas': numero_parcelas,
        'mes_inicio': mes_inicio,
        'mes_contemplacao': mes_contemplacao,
        'posicao_contemplacao': posicao,
        'valor_premio': float(valor_premio) if valor_premio is not None else None,
    }


def gerar_parcelas_consorcio(consorcio, categoria_id, pagamento=None):
    """
    Gera automaticamente as parcelas do consórcio como ItemDespesa

    Args:
        consorcio: Objeto ContratoConsorcio
        categoria_id: ID da categoria para as parcelas
    """
    if not categoria_id:
        raise ValueError("Categoria é obrigatória para gerar parcelas do consórcio")

    # Validar categoria
    categoria = Categoria.query.get(categoria_id)
    if not categoria:
        raise ValueError("Categoria não encontrada")

    mes_atual = consorcio.mes_inicio
    # O valor_inicial já é o valor da parcela, não dividir pelo número de parcelas
    pagamento = pagamento or normalizar_pagamento_consorcio({})
    parcelas_criadas = []

    for i in range(consorcio.numero_parcelas):
        # Calcular o valor com reajuste
        valor_ajustado = float(calcular_valor_parcela_consorcio(
            consorcio.valor_inicial,
            consorcio.tipo_reajuste,
            consorcio.valor_reajuste,
            i + 1,
        ))

        # Criar a despesa para o mês
        data_vencimento = mes_atual.replace(day=5)
        despesa = ItemDespesa(
            perfil_financeiro_id=perfil_id_consorcio(consorcio),
            nome=f"{consorcio.nome} - Parcela {i+1}/{consorcio.numero_parcelas}",
            descricao=f"Parcela {i+1} do consórcio {consorcio.nome}",
            valor=valor_ajustado,
            data_vencimento=data_vencimento,  # Vencimento no dia 5 do mês
            categoria_id=categoria_id,
            pago=False,
            recorrente=False,
            tipo='Consorcio',
            mes_competencia=mes_atual.strftime('%Y-%m')
        )
        aplicar_pagamento_parcela(despesa, pagamento)

        db.session.add(despesa)
        db.session.flush()  # Garantir despesa.id para vincular a Conta

        mes_referencia = data_vencimento.replace(day=1)
        existente = Conta.query.filter_by(item_despesa_id=despesa.id, mes_referencia=mes_referencia).first()
        if not existente:
            conta = Conta(
                perfil_financeiro_id=perfil_id_consorcio(consorcio),
                item_despesa_id=despesa.id,
                mes_referencia=mes_referencia,
                descricao=despesa.nome,
                valor=valor_ajustado,
                data_vencimento=data_vencimento,
                data_pagamento=None,
                status_pagamento='Pendente',
                debito_automatico=pagamento.get('meio_pagamento') == 'debito_automatico',
                conta_bancaria_id=pagamento.get('conta_bancaria_id') if pagamento.get('meio_pagamento') == 'debito_automatico' else None,
                numero_parcela=i + 1,
                total_parcelas=consorcio.numero_parcelas,
                observacoes=None,
                is_fatura_cartao=False,
                valor_planejado=None,
                valor_executado=None,
                estouro_orcamento=False,
                cartao_competencia=None,
                status_fatura='ABERTA',
                data_consolidacao=None,
                valor_consolidado=None,
            )
            db.session.add(conta)
        parcelas_criadas.append(despesa)

        # Próximo mês
        mes_atual = mes_atual + relativedelta(months=1)

    return parcelas_criadas


def gerar_receita_contemplacao(consorcio):
    """
    Gera automaticamente a receita da contemplação

    Args:
        consorcio: Objeto ContratoConsorcio
    """
    return gerar_ou_atualizar_receita_contemplacao(consorcio)


@consorcios_bp.route('/', methods=['GET'])
def listar_consorcios():
    """Lista todos os consórcios"""
    try:
        consorcios = PerfilFinanceiroService.aplicar_perfil_query(
            ContratoConsorcio.query.filter_by(ativo=True),
            ContratoConsorcio,
        ).all()
        return jsonify({
            'success': True,
            'data': [consorcio_to_dict(c) for c in consorcios]
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@consorcios_bp.route('/<int:id>', methods=['GET'])
def obter_consorcio(id):
    """Obtém um consórcio específico"""
    try:
        consorcio = PerfilFinanceiroService.aplicar_perfil_query(
            ContratoConsorcio.query,
            ContratoConsorcio,
        ).filter(ContratoConsorcio.id == id).first()
        if not consorcio:
            return jsonify({
                'success': False,
                'error': 'Consórcio não encontrado'
            }), 404

        return jsonify({
            'success': True,
            'data': consorcio_to_dict(consorcio)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@consorcios_bp.route('/', methods=['POST'])
def criar_consorcio():
    """Cria um novo consórcio e gera as parcelas automaticamente"""
    try:
        dados = request.get_json()

        # Validações
        campos_obrigatorios = ['nome', 'valor_inicial', 'numero_parcelas', 'categoria_id']
        for campo in campos_obrigatorios:
            if not dados.get(campo):
                return jsonify({
                    'success': False,
                    'error': f'Campo {campo} é obrigatório'
                }), 400

        # Converter datas
        dados_normalizados = normalizar_dados_consorcio(dados)
        mes_inicio = dados_normalizados['mes_inicio']
        mes_contemplacao = dados_normalizados['mes_contemplacao']
        pagamento = normalizar_pagamento_consorcio(dados)

        # Criar consórcio
        consorcio = ContratoConsorcio(
            perfil_financeiro_id=PerfilFinanceiroService.obter_perfil_ativo_id(),
            nome=dados['nome'],
            valor_inicial=dados_normalizados['valor_inicial'],
            tipo_reajuste=dados_normalizados['tipo_reajuste'],
            valor_reajuste=dados_normalizados['valor_reajuste'],
            numero_parcelas=dados_normalizados['numero_parcelas'],
            mes_inicio=mes_inicio,
            mes_contemplacao=mes_contemplacao,
            valor_premio=dados_normalizados['valor_premio'],
            item_despesa_id=dados.get('item_despesa_id'),  # Opcional (legacy)
            item_receita_id=dados.get('item_receita_id'),
            observacoes=dados.get('observacoes')
        )

        db.session.add(consorcio)
        db.session.flush()  # Para obter o ID

        # Gerar parcelas automaticamente (usando categoria_id)
        categoria_id = int(dados['categoria_id'])
        parcelas = gerar_parcelas_consorcio(consorcio, categoria_id, pagamento=pagamento)

        # Gerar receita se houver contemplação
        receita = None
        if mes_contemplacao and consorcio.valor_premio:
            receita = gerar_receita_contemplacao(consorcio)

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Consórcio criado com sucesso',
            'data': consorcio_to_dict(consorcio),
            'parcelas_geradas': len(parcelas),
            'receita_gerada': receita is not None
        }), 201

    except ValueError as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@consorcios_bp.route('/<int:id>', methods=['PUT'])
def atualizar_consorcio(id):
    """Atualiza um consórcio existente"""
    try:
        consorcio = PerfilFinanceiroService.aplicar_perfil_query(
            ContratoConsorcio.query,
            ContratoConsorcio,
        ).filter(ContratoConsorcio.id == id).first()
        if not consorcio:
            return jsonify({
                'success': False,
                'error': 'Consórcio não encontrado'
            }), 404

        dados = request.get_json()
        nome_anterior = consorcio.nome

        # Atualizar campos
        if 'nome' in dados:
            consorcio.nome = dados['nome']
        if 'observacoes' in dados:
            consorcio.observacoes = dados['observacoes']
        campos_motor = {
            'valor_inicial',
            'numero_parcelas',
            'mes_inicio',
            'mes_contemplacao',
            'tipo_reajuste',
            'valor_reajuste',
        }
        if any(campo in dados for campo in campos_motor):
            dados_normalizados = normalizar_dados_consorcio(dados, consorcio_atual=consorcio)
            consorcio.valor_inicial = dados_normalizados['valor_inicial']
            consorcio.tipo_reajuste = dados_normalizados['tipo_reajuste']
            consorcio.valor_reajuste = dados_normalizados['valor_reajuste']
            consorcio.numero_parcelas = dados_normalizados['numero_parcelas']
            consorcio.mes_inicio = dados_normalizados['mes_inicio']
            consorcio.mes_contemplacao = dados_normalizados['mes_contemplacao']
            consorcio.valor_premio = dados_normalizados['valor_premio']
        if 'ativo' in dados:
            consorcio.ativo = dados['ativo']

        campos_pagamento = {'meio_pagamento', 'cartao_id', 'conta_bancaria_id', 'categoria_cartao_id'}
        if any(campo in dados for campo in campos_pagamento):
            pagamento = normalizar_pagamento_consorcio(dados)
            atualizar_pagamento_parcelas_consorcio(
                consorcio,
                pagamento,
                nomes={nome_anterior, consorcio.nome},
            )

        receita = None
        if consorcio.mes_contemplacao and consorcio.valor_premio:
            receita = gerar_receita_contemplacao(consorcio)

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Consórcio atualizado com sucesso',
            'data': consorcio_to_dict(consorcio),
            'receita_gerada': receita is not None
        })

    except ValueError as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@consorcios_bp.route('/<int:id>', methods=['DELETE'])
def deletar_consorcio(id):
    """Deleta um consórcio (marca como inativo)"""
    try:
        consorcio = PerfilFinanceiroService.aplicar_perfil_query(
            ContratoConsorcio.query,
            ContratoConsorcio,
        ).filter(ContratoConsorcio.id == id).first()
        if not consorcio:
            return jsonify({
                'success': False,
                'error': 'Consórcio não encontrado'
            }), 404

        # Marcar como inativo ao invés de deletar
        consorcio.ativo = False

        # Inativar parcelas (planejamento) e remover contas pendentes associadas
        parcelas = query_parcelas_consorcio(consorcio).filter(
            ItemDespesa.nome.like(f"{consorcio.nome} - Parcela%")
        ).all()
        parcela_ids = [p.id for p in parcelas]

        if parcela_ids:
            ItemDespesa.query.filter(ItemDespesa.id.in_(parcela_ids)).update(
                {'ativo': False},
                synchronize_session=False
            )
            Conta.query.filter(
                Conta.item_despesa_id.in_(parcela_ids),
                Conta.status_pagamento != 'Pago',
            ).delete(synchronize_session=False)

        # Remover receitas de contemplação geradas por este consórcio
        receitas = receitas_por_marcador(consorcio.id)
        marcador = marcador_consorcio(consorcio.id)
        for receita in receitas:
            if _receita_tem_movimento(receita):
                # Receita já efetivada: preservar histórico, apenas desvincular
                receita.observacoes = _remover_marcador(receita.observacoes, marcador)
            else:
                db.session.delete(receita)

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Consórcio desativado com sucesso'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@consorcios_bp.route('/<int:id>/regenerar-parcelas', methods=['POST'])
def regenerar_parcelas(id):
    """Regenera as parcelas de um consórcio"""
    try:
        consorcio = PerfilFinanceiroService.aplicar_perfil_query(
            ContratoConsorcio.query,
            ContratoConsorcio,
        ).filter(ContratoConsorcio.id == id).first()
        if not consorcio:
            return jsonify({
                'success': False,
                'error': 'Consórcio não encontrado'
            }), 404

        # Buscar categoria de uma parcela existente (ou receber via body)
        dados = request.get_json() or {}
        categoria_id = dados.get('categoria_id')
        parcela_pagamento = query_parcelas_consorcio(consorcio).filter(
            ItemDespesa.nome.like(f"{consorcio.nome} - Parcela%")
        ).first()
        pagamento = pagamento_de_parcela(parcela_pagamento)

        if not categoria_id:
            # Tentar pegar de uma parcela existente
            parcela_antiga = parcela_pagamento

            if parcela_antiga:
                categoria_id = parcela_antiga.categoria_id
            else:
                return jsonify({
                    'success': False,
                    'error': 'categoria_id é obrigatório (nenhuma parcela anterior encontrada)'
                }), 400

        # Deletar parcelas antigas do consórcio (e suas Contas) antes de regenerar
        parcelas_query = query_parcelas_consorcio(consorcio).filter(
            ItemDespesa.nome.like(f"{consorcio.nome} - Parcela%")
        )
        parcelas_antigas = parcelas_query.all()
        ids_antigos = [p.id for p in parcelas_antigas]
        if ids_antigos:
            Conta.query.filter(Conta.item_despesa_id.in_(ids_antigos)).delete(synchronize_session=False)
        parcelas_query.delete(synchronize_session=False)

        # Gerar novas parcelas
        parcelas = gerar_parcelas_consorcio(consorcio, categoria_id, pagamento=pagamento)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Parcelas regeneradas com sucesso',
            'parcelas_geradas': len(parcelas)
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
