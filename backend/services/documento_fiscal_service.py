from datetime import datetime
from decimal import Decimal

from sqlalchemy import or_

try:
    from backend.models import (
        BemPatrimonial,
        ContaBancaria,
        ContaPatrimonio,
        DespesaPrevista,
        Financiamento,
        IrComprovante,
        IrComprovanteVinculo,
        LancamentoAgregado,
        MovimentoFinanceiro,
        db,
    )
    from backend.services.ir_documento_service import IrDocumentoService
    from backend.services.perfil_financeiro_service import PerfilFinanceiroService
except ImportError:
    from models import (
        BemPatrimonial,
        ContaBancaria,
        ContaPatrimonio,
        DespesaPrevista,
        Financiamento,
        IrComprovante,
        IrComprovanteVinculo,
        LancamentoAgregado,
        MovimentoFinanceiro,
        db,
    )
    from services.ir_documento_service import IrDocumentoService
    from services.perfil_financeiro_service import PerfilFinanceiroService


class DocumentoFiscalService:
    TIPOS_ENTIDADE = {
        'CONTA': ContaBancaria,
        'DESPESA_PREVISTA': DespesaPrevista,
        'LANCAMENTO': LancamentoAgregado,
        'MOVIMENTO_FINANCEIRO': MovimentoFinanceiro,
        'PATRIMONIO': BemPatrimonial,
        'FINANCIAMENTO': Financiamento,
        'OUTRO': None,
    }
    TIPOS_VINCULO = {'COMPROVANTE', 'NOTA_FISCAL', 'RECIBO', 'CONTRATO', 'GUIA', 'DOCUMENTO_CONTABIL', 'OUTRO'}
    NATUREZAS = {
        'DESPESA_OPERACIONAL',
        'PATRIMONIO_IMOBILIZADO',
        'SOFTWARE_ASSINATURA',
        'IMPOSTO_TAXA',
        'PRO_LABORE',
        'DISTRIBUICAO_LUCROS',
        'REEMBOLSO',
        'EMPRESTIMO',
        'ADIANTAMENTO',
        'OUTRO',
    }
    STATUS_LASTRO = {
        'COM_DOCUMENTO',
        'SEM_DOCUMENTO',
        'PENDENTE',
        'DIVERGENTE',
        'VALIDADO',
        'NAO_APLICAVEL',
        'AGUARDANDO_CONTADOR',
    }

    @classmethod
    def listar_vinculos(cls, comprovante_id):
        comprovante = IrDocumentoService.obter_comprovante(comprovante_id)
        return comprovante.vinculos.filter_by(ativo=True).order_by(IrComprovanteVinculo.created_at.desc()).all()

    @classmethod
    def criar_vinculo(cls, comprovante_id, dados):
        comprovante = IrDocumentoService.obter_comprovante(comprovante_id)
        perfil_id = PerfilFinanceiroService.obter_perfil_ativo_id()
        dados = dados or {}
        tipo_entidade = cls._normalizar_opcao(dados.get('tipo_entidade'), cls.TIPOS_ENTIDADE, 'OUTRO')
        entidade_id = cls._parse_int(dados.get('entidade_id'))
        entidade = cls._obter_entidade(tipo_entidade, entidade_id, perfil_id)

        vinculo = IrComprovanteVinculo(
            comprovante_id=comprovante.id,
            perfil_financeiro_id=perfil_id,
            tipo_entidade=tipo_entidade,
            entidade_id=entidade_id if entidade is not None else None,
            resumo_entidade=cls._resumo_entidade(tipo_entidade, entidade),
            tipo_vinculo=cls._normalizar_opcao(dados.get('tipo_vinculo'), cls.TIPOS_VINCULO, 'COMPROVANTE'),
            natureza=cls._normalizar_opcao(dados.get('natureza'), cls.NATUREZAS, 'OUTRO'),
            status_lastro=cls._normalizar_opcao(dados.get('status_lastro'), cls.STATUS_LASTRO, 'PENDENTE'),
            observacoes=cls._texto(dados.get('observacoes'), 1000),
            ativo=True,
        )
        db.session.add(vinculo)
        db.session.flush()
        return vinculo

    @classmethod
    def atualizar_vinculo(cls, comprovante_id, vinculo_id, dados):
        vinculo = cls._obter_vinculo(comprovante_id, vinculo_id)
        dados = dados or {}
        if 'tipo_vinculo' in dados:
            vinculo.tipo_vinculo = cls._normalizar_opcao(dados.get('tipo_vinculo'), cls.TIPOS_VINCULO, vinculo.tipo_vinculo)
        if 'natureza' in dados:
            vinculo.natureza = cls._normalizar_opcao(dados.get('natureza'), cls.NATUREZAS, vinculo.natureza)
        if 'status_lastro' in dados:
            vinculo.status_lastro = cls._normalizar_opcao(dados.get('status_lastro'), cls.STATUS_LASTRO, vinculo.status_lastro)
        if 'observacoes' in dados:
            vinculo.observacoes = cls._texto(dados.get('observacoes'), 1000)
        vinculo.updated_at = datetime.utcnow()
        return vinculo

    @classmethod
    def remover_vinculo(cls, comprovante_id, vinculo_id):
        vinculo = cls._obter_vinculo(comprovante_id, vinculo_id)
        vinculo.ativo = False
        vinculo.updated_at = datetime.utcnow()
        return vinculo

    @classmethod
    def listar_entidades_vinculaveis(cls, tipo, busca=None):
        tipo_entidade = cls._normalizar_opcao(tipo, cls.TIPOS_ENTIDADE, 'OUTRO')
        model = cls.TIPOS_ENTIDADE.get(tipo_entidade)
        if model is None:
            return []

        query = PerfilFinanceiroService.aplicar_perfil_query(model.query, model)
        termo = str(busca or '').strip()
        if termo:
            like = f'%{termo}%'
            if tipo_entidade in {'CONTA', 'PATRIMONIO', 'FINANCIAMENTO'}:
                query = query.filter(model.nome.ilike(like))
            elif tipo_entidade == 'LANCAMENTO':
                query = query.filter(LancamentoAgregado.descricao.ilike(like))
            elif tipo_entidade == 'MOVIMENTO_FINANCEIRO':
                query = query.filter(MovimentoFinanceiro.descricao.ilike(like))
            elif tipo_entidade == 'DESPESA_PREVISTA':
                query = query.outerjoin(DespesaPrevista.categoria).filter(
                    or_(DespesaPrevista.origem_tipo.ilike(like), DespesaPrevista.status.ilike(like))
                )

        entidades = query.order_by(model.id.desc()).limit(25).all()
        return [cls._serializar_entidade(tipo_entidade, entidade) for entidade in entidades]

    @classmethod
    def resumo_lastro(cls, ano=None):
        filtros = {}
        if ano:
            filtros['ano'] = ano
        comprovantes = IrDocumentoService.listar_comprovantes(filtros)
        return IrDocumentoService.resumo_lastro(comprovantes)

    @classmethod
    def _obter_vinculo(cls, comprovante_id, vinculo_id):
        IrDocumentoService.obter_comprovante(comprovante_id)
        vinculo = PerfilFinanceiroService.aplicar_perfil_query(
            IrComprovanteVinculo.query, IrComprovanteVinculo
        ).filter_by(id=vinculo_id, comprovante_id=comprovante_id, ativo=True).first()
        if not vinculo:
            raise ValueError('Vinculo de lastro nao encontrado')
        return vinculo

    @classmethod
    def _obter_entidade(cls, tipo_entidade, entidade_id, perfil_id):
        model = cls.TIPOS_ENTIDADE.get(tipo_entidade)
        if model is None:
            return None
        if not entidade_id:
            raise ValueError('Entidade vinculavel e obrigatoria')
        entidade = model.query.get(entidade_id)
        PerfilFinanceiroService.validar_pertence_ao_perfil(entidade, perfil_id=perfil_id)
        return entidade

    @classmethod
    def _serializar_entidade(cls, tipo_entidade, entidade):
        valor = cls._valor_entidade(tipo_entidade, entidade)
        return {
            'id': entidade.id,
            'tipo_entidade': tipo_entidade,
            'label': cls._resumo_entidade(tipo_entidade, entidade),
            'valor': float(valor) if valor is not None else None,
            'data': cls._data_entidade(tipo_entidade, entidade),
        }

    @staticmethod
    def _resumo_entidade(tipo_entidade, entidade):
        if entidade is None:
            return None
        if tipo_entidade == 'CONTA':
            return f'{entidade.nome} - {entidade.instituicao}'
        if tipo_entidade == 'PATRIMONIO':
            return entidade.nome
        if tipo_entidade == 'FINANCIAMENTO':
            return entidade.nome
        if tipo_entidade == 'LANCAMENTO':
            return entidade.descricao
        if tipo_entidade == 'MOVIMENTO_FINANCEIRO':
            return entidade.descricao
        if tipo_entidade == 'DESPESA_PREVISTA':
            return f'{entidade.origem_tipo} - {entidade.status}'
        return str(getattr(entidade, 'id', ''))

    @staticmethod
    def _valor_entidade(tipo_entidade, entidade):
        if entidade is None:
            return None
        if tipo_entidade == 'CONTA':
            return entidade.saldo_atual
        if tipo_entidade == 'PATRIMONIO':
            return entidade.valor_aquisicao
        if tipo_entidade == 'FINANCIAMENTO':
            return entidade.valor_financiado
        if tipo_entidade == 'LANCAMENTO':
            return entidade.valor
        if tipo_entidade == 'MOVIMENTO_FINANCEIRO':
            return entidade.valor
        if tipo_entidade == 'DESPESA_PREVISTA':
            return entidade.valor_previsto
        return None

    @staticmethod
    def _data_entidade(tipo_entidade, entidade):
        if entidade is None:
            return None
        valor = None
        if tipo_entidade == 'LANCAMENTO':
            valor = entidade.data_compra
        elif tipo_entidade == 'MOVIMENTO_FINANCEIRO':
            valor = entidade.data_movimento
        elif tipo_entidade == 'DESPESA_PREVISTA':
            valor = entidade.data_prevista
        elif tipo_entidade == 'FINANCIAMENTO':
            valor = entidade.data_contrato
        elif tipo_entidade == 'PATRIMONIO':
            valor = entidade.data_aquisicao
        return valor.isoformat() if valor else None

    @staticmethod
    def _normalizar_opcao(valor, permitidos, padrao):
        texto = str(valor or padrao).strip().upper()
        return texto if texto in permitidos else padrao

    @staticmethod
    def _parse_int(valor):
        if valor in {None, ''}:
            return None
        try:
            return int(valor)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _texto(valor, limite):
        texto = str(valor or '').strip()
        return texto[:limite] if texto else None
