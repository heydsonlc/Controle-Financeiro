"""
Rotas API para gerenciamento de vigências de seguro habitacional

Endpoints:
- GET    /api/financiamentos/<id>/seguros - Listar vigências
- POST   /api/financiamentos/<id>/seguros - Criar nova vigência
- PUT    /api/financiamentos/seguros/<id> - Editar observações
"""

from flask import Blueprint, request, jsonify
from backend.models import db, Financiamento, FinanciamentoSeguroVigencia
from backend.services.seguro_vigencia_service import SeguroVigenciaService
from datetime import datetime, date, timedelta
from decimal import Decimal

bp = Blueprint('financiamento_seguro', __name__)


@bp.route('/api/financiamentos/<int:financiamento_id>/seguros', methods=['GET'])
def listar_vigencias(financiamento_id):
    """
    Lista todas as vigências de seguro de um financiamento

    Retorna vigências ordenadas por competência (crescente)
    """
    try:
        # Verificar se financiamento existe
        financiamento = Financiamento.query.get(financiamento_id)
        if not financiamento:
            return jsonify({
                'success': False,
                'error': 'Financiamento não encontrado'
            }), 404

        # Listar vigências
        vigencias = SeguroVigenciaService.listar_vigencias(financiamento_id)

        # Formatar resposta
        resultado = []
        for v in vigencias:
            resultado.append({
                'id': v.id,
                'competencia_inicio': v.competencia_inicio.strftime('%Y-%m-%d'),
                'competencia_fim': v.data_encerramento.strftime('%Y-%m-%d') if v.data_encerramento else None,
                'valor_mensal': float(v.valor_mensal),
                'saldo_devedor_vigencia': float(v.saldo_devedor_vigencia) if v.saldo_devedor_vigencia else None,
                'taxa_percentual': float(v.taxa_percentual) if v.taxa_percentual else None,
                'vigencia_ativa': v.vigencia_ativa,
                'observacoes': v.observacoes,
                'criado_em': v.criado_em.strftime('%Y-%m-%d %H:%M:%S')
            })

        return jsonify({
            'success': True,
            'data': resultado
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/api/financiamentos/<int:financiamento_id>/seguros', methods=['POST'])
def criar_vigencia(financiamento_id):
    """
    Cria nova vigência de seguro

    Body esperado:
    {
        "competencia_inicio": "2027-02-01",
        "valor_mensal": 241.82,
        "saldo_devedor_vigencia": 400000.00,
        "observacoes": "Tabela Caixa 2027"
    }

    Regras:
    - Encerra vigência anterior automaticamente
    - Competência deve ser futura (ou presente)
    - Valor deve ser > 0
    """
    try:
        # Verificar se financiamento existe
        financiamento = Financiamento.query.get(financiamento_id)
        if not financiamento:
            return jsonify({
                'success': False,
                'error': 'Financiamento não encontrado'
            }), 404

        # Validar dados
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': 'Dados não fornecidos'
            }), 400

        # Validar campos obrigatórios
        campos_obrigatorios = ['competencia_inicio', 'valor_mensal', 'saldo_devedor_vigencia']
        for campo in campos_obrigatorios:
            if campo not in data:
                return jsonify({
                    'success': False,
                    'error': f'Campo obrigatório ausente: {campo}'
                }), 400

        # Converter data
        try:
            competencia_inicio = datetime.strptime(
                data['competencia_inicio'],
                '%Y-%m-%d'
            ).date()
        except ValueError:
            return jsonify({
                'success': False,
                'error': 'Formato de data inválido. Use YYYY-MM-DD'
            }), 400

        # Validar valor
        try:
            valor_mensal = Decimal(str(data['valor_mensal']))
            saldo_devedor_vigencia = Decimal(str(data['saldo_devedor_vigencia']))
        except (ValueError, TypeError):
            return jsonify({
                'success': False,
                'error': 'Valores numéricos inválidos'
            }), 400

        if valor_mensal <= 0:
            return jsonify({
                'success': False,
                'error': 'Valor mensal deve ser maior que zero'
            }), 400

        if saldo_devedor_vigencia <= 0:
            return jsonify({
                'success': False,
                'error': 'Saldo devedor deve ser maior que zero'
            }), 400

        # Normalizar competencia_inicio para primeiro dia do mês
        competencia_inicio = competencia_inicio.replace(day=1)

        # ========================================================================
        # VALIDAÇÃO TEMPORAL: Bloquear se há parcelas pagas a partir desta data
        # ========================================================================
        # REGRA: Não pode criar vigência que afete parcelas já pagas
        # Exemplo:
        #   - Parcelas pagas: 08/2025, 09/2025
        #   - Nova vigência: 08/2025
        #   - Resultado: BLOQUEAR (parcelas 08 e 09 já estão pagas com valor antigo)
        tem_pagamento = SeguroVigenciaService.vigencia_tem_pagamento(
            financiamento_id=financiamento_id,
            data_inicio=competencia_inicio,
            data_fim=None  # Verificar de competencia_inicio até o futuro
        )

        if tem_pagamento:
            return jsonify({
                'success': False,
                'error': 'Não é possível criar vigência para este período. '
                         'Já existem parcelas pagas a partir desta competência. '
                         'Escolha uma data futura após as parcelas pagas.'
            }), 409  # Conflict

        # ========================================================================
        # VALIDAÇÃO DE UNICIDADE: Encerrar vigência anterior na mesma competência
        # ========================================================================
        # REGRA: Só pode existir UMA vigência ativa por competência
        # Se já existe vigência para esta competência, encerrar a anterior
        vigencia_existente = FinanciamentoSeguroVigencia.query.filter_by(
            financiamento_id=financiamento_id,
            competencia_inicio=competencia_inicio,
            vigencia_ativa=True
        ).first()

        if vigencia_existente:
            # Encerrar vigência anterior (substituição)
            # Data de encerramento = último dia do mês anterior à nova competência
            # (mesmo que seja a mesma competência, mantém histórico)
            vigencia_existente.vigencia_ativa = False
            vigencia_existente.data_encerramento = competencia_inicio - timedelta(days=1)
            db.session.flush()

        # Criar vigência
        nova_vigencia = SeguroVigenciaService.criar_vigencia(
            financiamento_id=financiamento_id,
            competencia_inicio=competencia_inicio,
            valor_mensal=valor_mensal,
            saldo_devedor_vigencia=saldo_devedor_vigencia,
            data_nascimento_segurado=None,  # Opcional, pode adicionar depois
            observacoes=data.get('observacoes')
        )

        db.session.commit()

        # ========================================================================
        # HOOK: Recalcular seguro nas parcelas futuras (nova vigência criada)
        # ========================================================================
        # IMPORTANTE: Recalcula SOMENTE o componente seguro, preservando amortizações
        from backend.services.financiamento_service import FinanciamentoService

        FinanciamentoService.recalcular_seguro_parcelas_futuras(
            financiamento_id=financiamento_id,
            a_partir_de=competencia_inicio
        )

        return jsonify({
            'success': True,
            'message': 'Vigência criada com sucesso',
            'data': {
                'id': nova_vigencia.id,
                'competencia_inicio': nova_vigencia.competencia_inicio.strftime('%Y-%m-%d'),
                'valor_mensal': float(nova_vigencia.valor_mensal),
                'taxa_percentual': float(nova_vigencia.taxa_percentual) if nova_vigencia.taxa_percentual else None,
                'vigencia_ativa': nova_vigencia.vigencia_ativa
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/api/financiamentos/seguros/<int:vigencia_id>', methods=['PUT'])
def editar_vigencia(vigencia_id):
    """
    Edita valor_mensal e/ou observações de uma vigência

    REGRA: Só permite editar valor_mensal se NÃO houver parcelas pagas no período da vigência
    Datas (competencia_inicio, data_encerramento) NÃO podem ser alteradas

    Body esperado:
    {
        "valor_mensal": 250.00,       # Opcional
        "observacoes": "Nova observação"  # Opcional
    }

    Retorna 409 (Conflict) se houver parcelas pagas no período
    """
    try:
        # Buscar vigência
        vigencia = FinanciamentoSeguroVigencia.query.get(vigencia_id)

        if not vigencia:
            return jsonify({
                'success': False,
                'error': 'Vigência não encontrada'
            }), 404

        # Validar dados
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': 'Dados não fornecidos'
            }), 400

        # Se está tentando editar valor_mensal, validar se pode
        if 'valor_mensal' in data:
            # Verificar se há parcelas pagas no período da vigência
            tem_pagamento = SeguroVigenciaService.vigencia_tem_pagamento(
                financiamento_id=vigencia.financiamento_id,
                data_inicio=vigencia.competencia_inicio,
                data_fim=vigencia.data_encerramento
            )

            if tem_pagamento:
                return jsonify({
                    'success': False,
                    'error': 'Vigência possui parcela paga no período. Não é possível alterar o valor.'
                }), 409  # Conflict

            # Validar valor
            try:
                novo_valor = Decimal(str(data['valor_mensal']))
                if novo_valor <= 0:
                    return jsonify({
                        'success': False,
                        'error': 'Valor mensal deve ser maior que zero'
                    }), 400
                vigencia.valor_mensal = novo_valor
            except (ValueError, TypeError):
                return jsonify({
                    'success': False,
                    'error': 'Valor numérico inválido'
                }), 400

        # Atualizar observações (sempre permitido)
        if 'observacoes' in data:
            vigencia.observacoes = data['observacoes']

        db.session.commit()

        # ========================================================================
        # HOOK: Recalcular seguro nas parcelas futuras (se valor_mensal mudou)
        # ========================================================================
        # Se o valor do seguro foi alterado, precisamos atualizar as parcelas
        # afetadas para refletir o novo valor.
        # IMPORTANTE: Usa recalcular_SEGURO_parcelas_futuras() que NÃO toca
        # em amortização ou saldo devedor (preserva amortizações extraordinárias)
        if 'valor_mensal' in data:
            from backend.services.financiamento_service import FinanciamentoService

            # Recalcular SOMENTE o componente seguro das parcelas afetadas
            # a_partir_de=competencia_inicio garante que só afeta parcelas desta vigência
            FinanciamentoService.recalcular_seguro_parcelas_futuras(
                financiamento_id=vigencia.financiamento_id,
                a_partir_de=vigencia.competencia_inicio
            )

        return jsonify({
            'success': True,
            'message': 'Vigência atualizada com sucesso',
            'data': {
                'id': vigencia.id,
                'valor_mensal': float(vigencia.valor_mensal),
                'observacoes': vigencia.observacoes
            }
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/api/financiamentos/seguros/<int:vigencia_id>', methods=['DELETE'])
def deletar_vigencia(vigencia_id):
    """
    Delete NÃO é permitido

    Histórico é imutável. Para corrigir, crie nova vigência.
    """
    return jsonify({
        'success': False,
        'error': 'Exclusão não permitida. Histórico é imutável. Para corrigir, crie nova vigência.'
    }), 403
