from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import unicodedata

from sqlalchemy import or_

try:
    from backend.models import (
        Conta,
        DespesaPrevista,
        IrComprovante,
        IrComprovanteVinculo,
        LancamentoAgregado,
        LastroFinanceiroPendencia,
        MovimentoFinanceiro,
        db,
    )
    from backend.services.perfil_financeiro_service import PerfilFinanceiroService
except ImportError:
    from models import (
        Conta,
        DespesaPrevista,
        IrComprovante,
        IrComprovanteVinculo,
        LancamentoAgregado,
        LastroFinanceiroPendencia,
        MovimentoFinanceiro,
        db,
    )
    from services.perfil_financeiro_service import PerfilFinanceiroService


class LastroFinanceiroService:
    TIPOS_ENTIDADE = {
        'DESPESA_PREVISTA': DespesaPrevista,
        'CONTA': Conta,
        'LANCAMENTO': LancamentoAgregado,
        'MOVIMENTO_FINANCEIRO': MovimentoFinanceiro,
    }
    ORIGENS = {
        'DESPESA_PREVISTA': 'Despesa prevista',
        'CONTA': 'Conta a pagar',
        'LANCAMENTO': 'Lancamento no cartao',
        'MOVIMENTO_FINANCEIRO': 'Movimento financeiro',
    }
    STATUS_VISIVEIS_PADRAO = {'SEM_DOCUMENTO', 'PENDENTE', 'AGUARDANDO_CONTADOR'}
    STATUS_LASTRO = {
        'SEM_DOCUMENTO',
        'PENDENTE',
        'AGUARDANDO_CONTADOR',
        'NAO_APLICAVEL',
        'VALIDADO',
        'DIVERGENTE',
        'COM_DOCUMENTO',
    }
    STATUS_MANUAIS = {'PENDENTE', 'AGUARDANDO_CONTADOR', 'NAO_APLICAVEL', 'SEM_DOCUMENTO'}
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

    @classmethod
    def listar_saidas_sem_documento(cls, filtros=None):
        filtros = filtros or {}
        perfil_id = cls._perfil_empresa_id()
        saidas = cls._saidas_enriquecidas(perfil_id, filtros)
        saidas = [saida for saida in saidas if not saida['possui_documento']]
        saidas = cls._aplicar_filtro_status(saidas, filtros)
        return sorted(saidas, key=lambda item: (item['data'] or '', item['tipo_entidade'], item['entidade_id']), reverse=True)

    @classmethod
    def resumo_saidas_sem_documento(cls, filtros=None):
        filtros = filtros or {}
        perfil_id = cls._perfil_empresa_id()
        saidas = cls._saidas_enriquecidas(perfil_id, filtros)

        resumo = {
            'total_saidas': len(saidas),
            'saidas_com_documento': 0,
            'quantidade_sem_documento': 0,
            'valor_sem_documento': 0.0,
            'aguardando_contador': 0,
            'valor_aguardando_contador': 0.0,
            'nao_aplicavel': 0,
            'valor_nao_aplicavel': 0.0,
            'pendencias_total': 0,
            'valor_pendencias_total': 0.0,
            'por_origem': [],
            'por_natureza': [],
        }
        por_origem = {}
        por_natureza = {}

        for saida in saidas:
            valor = cls._decimal(saida.get('valor'))
            status = saida.get('status_lastro') or 'SEM_DOCUMENTO'
            if saida.get('possui_documento'):
                resumo['saidas_com_documento'] += 1
                continue

            cls._somar_grupo(por_origem, saida.get('origem') or 'Outros', valor)
            cls._somar_grupo(por_natureza, saida.get('natureza_sugerida') or 'OUTRO', valor)

            if status in {'SEM_DOCUMENTO', 'PENDENTE'}:
                resumo['quantidade_sem_documento'] += 1
                resumo['valor_sem_documento'] += float(valor)
                resumo['pendencias_total'] += 1
                resumo['valor_pendencias_total'] += float(valor)
            elif status == 'AGUARDANDO_CONTADOR':
                resumo['aguardando_contador'] += 1
                resumo['valor_aguardando_contador'] += float(valor)
                resumo['pendencias_total'] += 1
                resumo['valor_pendencias_total'] += float(valor)
            elif status == 'NAO_APLICAVEL':
                resumo['nao_aplicavel'] += 1
                resumo['valor_nao_aplicavel'] += float(valor)

        resumo['por_origem'] = cls._ordenar_grupos(por_origem)
        resumo['por_natureza'] = cls._ordenar_grupos(por_natureza)
        return resumo

    @classmethod
    def marcar_status(cls, dados):
        dados = dados or {}
        perfil_id = cls._perfil_empresa_id()
        tipo_entidade = cls._normalizar_opcao(dados.get('tipo_entidade'), cls.TIPOS_ENTIDADE, None)
        entidade_id = cls._parse_int(dados.get('entidade_id'))
        if not tipo_entidade or not entidade_id:
            raise ValueError('Tipo de entidade e entidade sao obrigatorios')
        cls._obter_entidade(tipo_entidade, entidade_id, perfil_id)
        if cls._buscar_vinculo(tipo_entidade, entidade_id, perfil_id):
            raise ValueError('Saida ja possui documento vinculado')

        status = cls._normalizar_opcao(dados.get('status_lastro'), cls.STATUS_MANUAIS, 'PENDENTE')
        natureza = cls._normalizar_opcao(dados.get('natureza'), cls.NATUREZAS, 'OUTRO')
        observacoes = cls._texto(dados.get('observacoes'), 1000)

        pendencia = cls._buscar_pendencia(tipo_entidade, entidade_id, perfil_id)
        if status == 'SEM_DOCUMENTO':
            if pendencia:
                pendencia.ativo = False
                pendencia.updated_at = datetime.utcnow()
            db.session.flush()
            return {'tipo_entidade': tipo_entidade, 'entidade_id': entidade_id, 'status_lastro': 'SEM_DOCUMENTO'}

        if not pendencia:
            pendencia = LastroFinanceiroPendencia(
                perfil_financeiro_id=perfil_id,
                tipo_entidade=tipo_entidade,
                entidade_id=entidade_id,
                ativo=True,
            )
            db.session.add(pendencia)

        pendencia.status_lastro = status
        pendencia.natureza = natureza
        pendencia.observacoes = observacoes
        pendencia.updated_at = datetime.utcnow()
        db.session.flush()
        return pendencia.to_dict()

    @classmethod
    def vincular_documento(cls, dados):
        dados = dados or {}
        perfil_id = cls._perfil_empresa_id()
        tipo_entidade = cls._normalizar_opcao(dados.get('tipo_entidade'), cls.TIPOS_ENTIDADE, None)
        entidade_id = cls._parse_int(dados.get('entidade_id'))
        comprovante_id = cls._parse_int(dados.get('comprovante_id'))
        if not tipo_entidade or not entidade_id or not comprovante_id:
            raise ValueError('Saida e documento fiscal sao obrigatorios')

        entidade = cls._obter_entidade(tipo_entidade, entidade_id, perfil_id)
        comprovante = IrComprovante.query.get(comprovante_id)
        PerfilFinanceiroService.validar_pertence_ao_perfil(comprovante, perfil_id=perfil_id)

        vinculo = IrComprovanteVinculo(
            comprovante_id=comprovante.id,
            perfil_financeiro_id=perfil_id,
            tipo_entidade=tipo_entidade,
            entidade_id=entidade_id,
            resumo_entidade=cls._resumo_entidade(tipo_entidade, entidade),
            tipo_vinculo=cls._normalizar_opcao(dados.get('tipo_vinculo'), cls.TIPOS_VINCULO, 'COMPROVANTE'),
            natureza=cls._normalizar_opcao(dados.get('natureza'), cls.NATUREZAS, 'OUTRO'),
            status_lastro=cls._normalizar_opcao(dados.get('status_lastro'), cls.STATUS_LASTRO, 'VALIDADO'),
            observacoes=cls._texto(dados.get('observacoes'), 1000),
            ativo=True,
        )
        db.session.add(vinculo)

        pendencia = cls._buscar_pendencia(tipo_entidade, entidade_id, perfil_id)
        if pendencia:
            pendencia.ativo = False
            pendencia.updated_at = datetime.utcnow()

        db.session.flush()
        return vinculo

    @classmethod
    def _saidas_enriquecidas(cls, perfil_id, filtros):
        saidas = cls._coletar_saidas(perfil_id, filtros)
        vinculos = cls._vinculos_por_entidade(perfil_id)
        pendencias = cls._pendencias_por_entidade(perfil_id)
        enriquecidas = []

        for saida in saidas:
            chave = (saida['tipo_entidade'], saida['entidade_id'])
            vinculo = vinculos.get(chave)
            pendencia = pendencias.get(chave)
            possui_documento = bool(vinculo)
            status = vinculo.status_lastro if vinculo else (pendencia.status_lastro if pendencia else 'SEM_DOCUMENTO')
            natureza = vinculo.natureza if vinculo else (pendencia.natureza if pendencia else saida['natureza_sugerida'])
            observacoes = vinculo.observacoes if vinculo else (pendencia.observacoes if pendencia else None)
            saida.update({
                'status_lastro': status,
                'natureza_sugerida': natureza or saida['natureza_sugerida'],
                'possui_documento': possui_documento,
                'documento_id': vinculo.comprovante_id if vinculo else None,
                'vinculo_id': vinculo.id if vinculo else None,
                'pendencia_id': pendencia.id if pendencia else None,
                'observacoes': observacoes,
            })
            enriquecidas.append(saida)

        return cls._aplicar_filtros_basicos(enriquecidas, filtros)

    @classmethod
    def _coletar_saidas(cls, perfil_id, filtros):
        inicio, fim = cls._periodo(filtros)
        saidas = []
        saidas.extend(cls._saidas_despesas_previstas(perfil_id, inicio, fim))
        saidas.extend(cls._saidas_contas(perfil_id, inicio, fim))
        saidas.extend(cls._saidas_lancamentos(perfil_id, inicio, fim))
        saidas.extend(cls._saidas_movimentos(perfil_id, inicio, fim))
        return saidas

    @classmethod
    def _saidas_despesas_previstas(cls, perfil_id, inicio, fim):
        query = DespesaPrevista.query.filter(
            DespesaPrevista.perfil_financeiro_id == perfil_id,
            DespesaPrevista.valor_previsto > 0,
            DespesaPrevista.data_atual_prevista >= inicio,
            DespesaPrevista.data_atual_prevista < fim,
            DespesaPrevista.status.notin_(['IGNORADA', 'CANCELADA', 'SUPRIMIDA']),
        )
        return [cls._normalizar_despesa_prevista(item) for item in query.all()]

    @classmethod
    def _saidas_contas(cls, perfil_id, inicio, fim):
        query = Conta.query.filter(
            Conta.perfil_financeiro_id == perfil_id,
            Conta.valor > 0,
            Conta.data_vencimento >= inicio,
            Conta.data_vencimento < fim,
            or_(Conta.is_fatura_cartao == False, Conta.is_fatura_cartao.is_(None)),  # noqa: E712
        )
        return [cls._normalizar_conta(item) for item in query.all()]

    @classmethod
    def _saidas_lancamentos(cls, perfil_id, inicio, fim):
        query = LancamentoAgregado.query.filter(
            LancamentoAgregado.perfil_financeiro_id == perfil_id,
            LancamentoAgregado.valor > 0,
            LancamentoAgregado.data_compra >= inicio,
            LancamentoAgregado.data_compra < fim,
        )
        return [cls._normalizar_lancamento(item) for item in query.all()]

    @classmethod
    def _saidas_movimentos(cls, perfil_id, inicio, fim):
        query = MovimentoFinanceiro.query.filter(
            MovimentoFinanceiro.perfil_financeiro_id == perfil_id,
            MovimentoFinanceiro.tipo == 'DEBITO',
            MovimentoFinanceiro.valor > 0,
            MovimentoFinanceiro.data_movimento >= inicio,
            MovimentoFinanceiro.data_movimento < fim,
        )
        saidas = []
        for item in query.all():
            if item.conta_id or item.fatura_id:
                continue
            if cls._eh_transferencia_interna(item, perfil_id):
                continue
            saidas.append(cls._normalizar_movimento(item))
        return saidas

    @classmethod
    def _eh_transferencia_interna(cls, movimento, perfil_id):
        origem = str(movimento.origem or '').upper()
        if origem != 'TRANSFERENCIA' or not movimento.transferencia_id:
            return False
        return MovimentoFinanceiro.query.filter(
            MovimentoFinanceiro.perfil_financeiro_id == perfil_id,
            MovimentoFinanceiro.transferencia_id == movimento.transferencia_id,
            MovimentoFinanceiro.tipo == 'CREDITO',
            MovimentoFinanceiro.id != movimento.id,
        ).first() is not None

    @classmethod
    def _normalizar_despesa_prevista(cls, item):
        categoria = item.categoria.nome if item.categoria else None
        data_saida = item.data_atual_prevista or item.data_prevista
        descricao = cls._resumo_entidade('DESPESA_PREVISTA', item)
        return cls._saida_base(
            'DESPESA_PREVISTA',
            item.id,
            data_saida,
            descricao,
            item.valor_previsto,
            cls.ORIGENS['DESPESA_PREVISTA'],
            categoria,
            item.status,
            cls.sugerir_natureza(categoria, descricao),
        )

    @classmethod
    def _normalizar_conta(cls, item):
        categoria = item.item_despesa.categoria.nome if item.item_despesa and item.item_despesa.categoria else None
        descricao = item.descricao or (item.item_despesa.nome if item.item_despesa else f'Conta #{item.id}')
        return cls._saida_base(
            'CONTA',
            item.id,
            item.data_pagamento or item.data_vencimento,
            descricao,
            item.valor,
            cls.ORIGENS['CONTA'],
            categoria,
            item.status_pagamento,
            cls.sugerir_natureza(categoria, descricao),
        )

    @classmethod
    def _normalizar_lancamento(cls, item):
        categoria = item.categoria.nome if item.categoria else None
        return cls._saida_base(
            'LANCAMENTO',
            item.id,
            item.data_compra,
            item.descricao,
            item.valor,
            cls.ORIGENS['LANCAMENTO'],
            categoria,
            'CARTAO',
            cls.sugerir_natureza(categoria, item.descricao),
        )

    @classmethod
    def _normalizar_movimento(cls, item):
        origem = item.origem or cls.ORIGENS['MOVIMENTO_FINANCEIRO']
        return cls._saida_base(
            'MOVIMENTO_FINANCEIRO',
            item.id,
            item.data_movimento,
            item.descricao,
            item.valor,
            origem,
            None,
            item.tipo,
            cls.sugerir_natureza(None, item.descricao),
        )

    @staticmethod
    def _saida_base(tipo_entidade, entidade_id, data_saida, descricao, valor, origem, categoria, status_pagamento, natureza):
        return {
            'tipo_entidade': tipo_entidade,
            'entidade_id': entidade_id,
            'data': data_saida.isoformat() if data_saida else None,
            'descricao': descricao,
            'valor': float(valor or 0),
            'origem': origem,
            'categoria': categoria,
            'status_pagamento': status_pagamento,
            'status_lastro': 'SEM_DOCUMENTO',
            'natureza_sugerida': natureza,
            'possui_documento': False,
            'documento_id': None,
            'vinculo_id': None,
            'pendencia_id': None,
            'observacoes': None,
        }

    @classmethod
    def _aplicar_filtros_basicos(cls, saidas, filtros):
        origem = str(filtros.get('origem') or '').strip().upper()
        natureza = str(filtros.get('natureza') or '').strip().upper()
        busca = cls._normalizar_texto(filtros.get('busca'))
        valor_minimo = cls._decimal(filtros.get('valor_minimo') or filtros.get('valorMinimo') or 0)

        filtradas = []
        for saida in saidas:
            if origem and origem not in {'TODOS', 'TODAS'}:
                origem_saida = str(saida.get('origem') or '').strip().upper()
                tipo_saida = str(saida.get('tipo_entidade') or '').strip().upper()
                if origem not in {origem_saida, tipo_saida}:
                    continue
            if natureza and natureza not in {'TODOS', 'TODAS'}:
                natureza_saida = str(saida.get('natureza_sugerida') or '').strip().upper()
                if natureza_saida != natureza:
                    continue
            if busca:
                texto = cls._normalizar_texto(' '.join([
                    str(saida.get('descricao') or ''),
                    str(saida.get('categoria') or ''),
                    str(saida.get('origem') or ''),
                    str(saida.get('natureza_sugerida') or ''),
                ]))
                if busca not in texto:
                    continue
            if cls._decimal(saida.get('valor')) < valor_minimo:
                continue
            filtradas.append(saida)
        return filtradas

    @classmethod
    def _aplicar_filtro_status(cls, saidas, filtros):
        status = str(filtros.get('status') or '').strip().upper()
        if not status or status == 'PENDENTES':
            permitidos = cls.STATUS_VISIVEIS_PADRAO
        elif status in {'TODOS', 'TODAS'}:
            permitidos = {'SEM_DOCUMENTO', 'PENDENTE', 'AGUARDANDO_CONTADOR', 'NAO_APLICAVEL'}
        else:
            permitidos = {status}
        return [saida for saida in saidas if saida.get('status_lastro') in permitidos]

    @classmethod
    def _vinculos_por_entidade(cls, perfil_id):
        vinculos = IrComprovanteVinculo.query.join(IrComprovante).filter(
            IrComprovanteVinculo.perfil_financeiro_id == perfil_id,
            IrComprovanteVinculo.ativo == True,  # noqa: E712
            IrComprovante.perfil_financeiro_id == perfil_id,
        ).order_by(IrComprovanteVinculo.created_at.desc()).all()
        resultado = {}
        for vinculo in vinculos:
            if vinculo.entidade_id is None:
                continue
            resultado.setdefault((vinculo.tipo_entidade, vinculo.entidade_id), vinculo)
        return resultado

    @classmethod
    def _pendencias_por_entidade(cls, perfil_id):
        pendencias = LastroFinanceiroPendencia.query.filter_by(
            perfil_financeiro_id=perfil_id,
            ativo=True,
        ).order_by(LastroFinanceiroPendencia.updated_at.desc()).all()
        resultado = {}
        for pendencia in pendencias:
            resultado.setdefault((pendencia.tipo_entidade, pendencia.entidade_id), pendencia)
        return resultado

    @classmethod
    def _buscar_vinculo(cls, tipo_entidade, entidade_id, perfil_id):
        return IrComprovanteVinculo.query.join(IrComprovante).filter(
            IrComprovanteVinculo.perfil_financeiro_id == perfil_id,
            IrComprovanteVinculo.tipo_entidade == tipo_entidade,
            IrComprovanteVinculo.entidade_id == entidade_id,
            IrComprovanteVinculo.ativo == True,  # noqa: E712
            IrComprovante.perfil_financeiro_id == perfil_id,
        ).first()

    @classmethod
    def _buscar_pendencia(cls, tipo_entidade, entidade_id, perfil_id):
        return LastroFinanceiroPendencia.query.filter_by(
            perfil_financeiro_id=perfil_id,
            tipo_entidade=tipo_entidade,
            entidade_id=entidade_id,
            ativo=True,
        ).first()

    @classmethod
    def _obter_entidade(cls, tipo_entidade, entidade_id, perfil_id):
        model = cls.TIPOS_ENTIDADE.get(tipo_entidade)
        if model is None:
            raise ValueError('Tipo de entidade nao suportado para lastro')
        entidade = model.query.get(entidade_id)
        PerfilFinanceiroService.validar_pertence_ao_perfil(entidade, perfil_id=perfil_id)
        return entidade

    @classmethod
    def _resumo_entidade(cls, tipo_entidade, entidade):
        if tipo_entidade == 'DESPESA_PREVISTA':
            categoria = entidade.categoria.nome if entidade.categoria else 'Despesa'
            return f'{categoria} - {entidade.status}'
        if tipo_entidade == 'CONTA':
            return entidade.descricao or f'Conta #{entidade.id}'
        if tipo_entidade == 'LANCAMENTO':
            return entidade.descricao
        if tipo_entidade == 'MOVIMENTO_FINANCEIRO':
            return entidade.descricao
        return str(getattr(entidade, 'id', ''))

    @classmethod
    def sugerir_natureza(cls, categoria=None, descricao=None):
        texto = cls._normalizar_texto(f'{categoria or ""} {descricao or ""}')
        if any(sinal in texto for sinal in ['patrimonio', 'moveis', 'equipamento', 'computador', 'notebook']):
            return 'PATRIMONIO_IMOBILIZADO'
        if any(sinal in texto for sinal in ['imposto', 'taxa', 'guia']):
            return 'IMPOSTO_TAXA'
        if 'pro labore' in texto or 'pro-labore' in texto:
            return 'PRO_LABORE'
        if 'lucro' in texto or 'distribuicao' in texto:
            return 'DISTRIBUICAO_LUCROS'
        if 'reembolso' in texto:
            return 'REEMBOLSO'
        if 'software' in texto or 'assinatura' in texto:
            return 'SOFTWARE_ASSINATURA'
        return 'DESPESA_OPERACIONAL'

    @classmethod
    def _perfil_empresa_id(cls):
        perfil_id = PerfilFinanceiroService.obter_perfil_ativo_id()
        perfil = PerfilFinanceiroService.obter_perfil_por_id(perfil_id)
        tipo = str(getattr(perfil, 'tipo', '') or '').upper()
        if tipo != 'EMPRESA':
            raise PermissionError('Saidas sem documento estao disponiveis apenas no perfil Empresa')
        return perfil_id

    @staticmethod
    def _periodo(filtros):
        hoje = date.today()
        ano = LastroFinanceiroService._parse_int(filtros.get('ano')) or hoje.year
        mes = LastroFinanceiroService._parse_int(filtros.get('mes'))
        if mes and 1 <= mes <= 12:
            inicio = date(ano, mes, 1)
            fim = date(ano + 1, 1, 1) if mes == 12 else date(ano, mes + 1, 1)
            return inicio, fim
        return date(ano, 1, 1), date(ano + 1, 1, 1)

    @staticmethod
    def _somar_grupo(grupos, chave, valor):
        grupos.setdefault(chave, {'quantidade': 0, 'valor': Decimal('0')})
        grupos[chave]['quantidade'] += 1
        grupos[chave]['valor'] += valor

    @staticmethod
    def _ordenar_grupos(grupos):
        return [
            {'nome': chave, 'quantidade': dados['quantidade'], 'valor': float(dados['valor'])}
            for chave, dados in sorted(grupos.items(), key=lambda item: (-item[1]['valor'], item[0]))
        ]

    @staticmethod
    def _normalizar_opcao(valor, permitidos, padrao):
        texto = str(valor or '').strip().upper()
        if not texto:
            return padrao
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
    def _decimal(valor):
        try:
            return Decimal(str(valor or 0))
        except (InvalidOperation, TypeError, ValueError):
            return Decimal('0')

    @staticmethod
    def _texto(valor, limite):
        texto = str(valor or '').strip()
        return texto[:limite] if texto else None

    @staticmethod
    def _normalizar_texto(valor):
        texto = unicodedata.normalize('NFKD', str(valor or '').casefold())
        return ''.join(char for char in texto if not unicodedata.combining(char))
