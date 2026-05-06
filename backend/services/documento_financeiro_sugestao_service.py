from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

try:
    from backend.models import (
        Categoria,
        Conta,
        ContaBancaria,
        IrComprovante,
        IrComprovanteEvento,
        IrComprovanteVinculo,
        ItemDespesa,
        LancamentoAgregado,
        db,
    )
    from backend.services.cartao_service import CartaoService
    from backend.services.categoria_cartao_service import CategoriaCartaoService
    from backend.services.categoria_palavra_chave_service import CategoriaPalavraChaveService
    from backend.services.conta_bancaria_service import ContaBancariaService
    from backend.services.ir_documento_service import IrDocumentoService
    from backend.services.perfil_financeiro_service import PerfilFinanceiroService
except ImportError:
    from models import (
        Categoria,
        Conta,
        ContaBancaria,
        IrComprovante,
        IrComprovanteEvento,
        IrComprovanteVinculo,
        ItemDespesa,
        LancamentoAgregado,
        db,
    )
    from services.cartao_service import CartaoService
    from services.categoria_cartao_service import CategoriaCartaoService
    from services.categoria_palavra_chave_service import CategoriaPalavraChaveService
    from services.conta_bancaria_service import ContaBancariaService
    from services.ir_documento_service import IrDocumentoService
    from services.perfil_financeiro_service import PerfilFinanceiroService


class DocumentoFinanceiroSugestaoService:
    FORMAS_PAGAMENTO = [
        {'key': 'pix', 'nome': 'Pix'},
        {'key': 'dinheiro', 'nome': 'Dinheiro'},
        {'key': 'cartao', 'nome': 'Cartao'},
        {'key': 'boleto', 'nome': 'Boleto'},
        {'key': 'transferencia', 'nome': 'Transferencia'},
        {'key': 'debito_automatico', 'nome': 'Debito automatico'},
        {'key': 'outros', 'nome': 'Outros / Nao informado'},
    ]

    @classmethod
    def gerar_sugestao(cls, comprovante_id):
        comprovante = IrDocumentoService.obter_comprovante(comprovante_id)
        categoria_info = cls._resolver_categoria_sugerida(comprovante)
        categoria_id = categoria_info.get('categoria_id') or comprovante.categoria_id
        categoria = cls._obter_categoria(categoria_id, obrigatoria=False) if categoria_id else None
        categoria_ir = cls._resolver_categoria_ir(comprovante, categoria_id)
        data_sugerida = cls._data_sugerida(comprovante)
        valor = cls._decimal(comprovante.valor) if comprovante.valor is not None else Decimal('0')

        avisos = []
        avisos.extend(categoria_info.get('avisos') or [])
        if not categoria:
            avisos.append('Categoria de Despesa nao identificada. Selecione manualmente.')
        if valor <= 0:
            avisos.append('Valor nao identificado automaticamente.')
        if cls._documento_usou_ocr(comprovante):
            avisos.append('Sugestao gerada a partir de texto extraido por OCR. Revise os dados antes de confirmar.')
        if categoria and not categoria_ir:
            avisos.append('Categoria de Despesa sem vinculo com Categoria IR/Fiscal.')

        return {
            'comprovante_id': comprovante.id,
            'documento': {
                'id': comprovante.id,
                'nome_arquivo': comprovante.arquivo.nome_arquivo if comprovante.arquivo else None,
                'prestador_nome': comprovante.prestador_nome,
                'prestador_cpf_cnpj': comprovante.prestador_cpf_cnpj,
                'origem_texto': 'OCR' if cls._documento_usou_ocr(comprovante) else 'PDF_TEXTUAL',
            },
            'tipo_destino_sugerido': 'DESPESA',
            'descricao': cls._descricao_sugerida(comprovante, categoria),
            'valor': float(valor) if valor is not None else 0.0,
            'data': data_sugerida.isoformat(),
            'competencia': data_sugerida.strftime('%Y-%m'),
            'fornecedor': comprovante.prestador_nome,
            'cpf_cnpj': comprovante.prestador_cpf_cnpj,
            'categoria_id': categoria.id if categoria else None,
            'categoria_nome': categoria.nome if categoria else None,
            'categoria_origem': categoria_info.get('origem') or comprovante.origem_classificacao,
            'categoria_ir_id': categoria_ir.id if categoria_ir else None,
            'categoria_ir_nome': categoria_ir.nome if categoria_ir else None,
            'forma_pagamento': 'outros',
            'observacoes': cls._observacoes_sugeridas(comprovante),
            'avisos': cls._deduplicar(avisos),
            'opcoes': {
                'tipos_destino': [
                    {'key': 'DESPESA', 'nome': 'Despesa prevista'},
                    {'key': 'LANCAMENTO', 'nome': 'Lancamento realizado'},
                ],
                'formas_pagamento': cls.FORMAS_PAGAMENTO,
                'categorias_despesa': IrDocumentoService.listar_categorias_despesa_disponiveis(),
            },
        }

    @classmethod
    def criar_financeiro(cls, comprovante_id, dados):
        comprovante = IrDocumentoService.obter_comprovante(comprovante_id)
        perfil_id = PerfilFinanceiroService.obter_perfil_ativo_id()
        dados = dados or {}
        tipo_destino = str(dados.get('tipo_destino') or '').strip().upper()
        if tipo_destino not in {'DESPESA', 'LANCAMENTO'}:
            raise ValueError('Escolha se a sugestao sera criada como Despesa ou Lancamento')

        forma_pagamento = cls._normalizar_forma_pagamento(dados.get('forma_pagamento'))
        categoria_id = cls._parse_int(dados.get('categoria_id'))
        categoria = cls._obter_categoria(categoria_id, obrigatoria=False) if categoria_id else None
        valor = cls._decimal(dados.get('valor'))
        if valor <= 0:
            raise ValueError('Valor deve ser maior que zero para criar a entidade financeira')
        data_referencia = cls._parse_date(dados.get('data') or dados.get('vencimento') or dados.get('data_vencimento')) or cls._data_sugerida(comprovante)
        descricao = cls._limitar(dados.get('descricao') or cls._descricao_sugerida(comprovante, categoria), 200)
        observacoes = cls._limitar(dados.get('observacoes') or cls._observacoes_sugeridas(comprovante), 1000)
        competencia = cls._competencia(dados.get('competencia'), data_referencia)
        conta_bancaria_id = cls._parse_int(dados.get('conta_bancaria_id') or dados.get('conta_id'))
        cartao_id = cls._parse_int(dados.get('cartao_id'))

        if conta_bancaria_id:
            cls._obter_conta_bancaria(conta_bancaria_id)

        avisos = []
        resolucao_cartao = None
        if forma_pagamento == 'cartao':
            if not cartao_id:
                raise ValueError('Cartao e obrigatorio quando a forma de pagamento for cartao')
            if not categoria_id:
                raise ValueError('Categoria de Despesa e obrigatoria para lancamento no cartao')
            cls._obter_cartao(cartao_id)
            resolucao_cartao = CategoriaCartaoService.resolver_categoria_cartao_para_lancamento(
                cartao_id=cartao_id,
                categoria_id=categoria_id,
                categoria_cartao_id=None,
            )
            if not resolucao_cartao.get('categoria_cartao_id'):
                avisos.append(resolucao_cartao.get('aviso') or 'Categoria do Cartao nao configurada para esta Categoria de Despesa.')

        if tipo_destino == 'LANCAMENTO' and forma_pagamento == 'cartao':
            entidade, tipo_entidade = cls._criar_lancamento_cartao(
                cartao_id=cartao_id,
                categoria_id=categoria_id,
                descricao=descricao,
                valor=valor,
                data_compra=data_referencia,
                observacoes=observacoes,
            )
        else:
            pago = tipo_destino == 'LANCAMENTO'
            entidade, tipo_entidade = cls._criar_conta_operacional(
                categoria_id=categoria_id,
                descricao=descricao,
                valor=valor,
                data_referencia=data_referencia,
                competencia=competencia,
                observacoes=observacoes,
                forma_pagamento=forma_pagamento,
                pago=pago,
                conta_bancaria_id=conta_bancaria_id,
                cartao_id=cartao_id if forma_pagamento == 'cartao' else None,
                categoria_cartao_id=resolucao_cartao.get('categoria_cartao_id') if resolucao_cartao else None,
            )

        vinculo = cls._criar_vinculo(comprovante, tipo_entidade, entidade, categoria_id, observacoes)
        cls._registrar_evento(
            comprovante,
            'SUGESTAO_FINANCEIRA_CRIADA',
            f'Sugestao confirmada como {tipo_destino.lower()} e vinculada a {tipo_entidade} #{entidade.id}.',
        )
        if tipo_destino == 'DESPESA':
            cls._registrar_evento(comprovante, 'DESPESA_CRIADA_A_PARTIR_DOCUMENTO', 'Despesa criada a partir de sugestao financeira revisada.')
        else:
            cls._registrar_evento(comprovante, 'LANCAMENTO_CRIADO_A_PARTIR_DOCUMENTO', 'Lancamento criado a partir de sugestao financeira revisada.')
        comprovante.updated_at = datetime.utcnow()
        db.session.flush()

        return {
            'entidade': cls._serializar_entidade(tipo_entidade, entidade),
            'tipo_destino': tipo_destino,
            'tipo_entidade': tipo_entidade,
            'vinculo': vinculo.to_dict(),
            'categoria_cartao': resolucao_cartao,
            'avisos': cls._deduplicar(avisos),
            'comprovante': comprovante.to_dict(include_eventos=True),
        }

    @classmethod
    def _criar_lancamento_cartao(cls, *, cartao_id, categoria_id, descricao, valor, data_compra, observacoes):
        mes_fatura = data_compra.replace(day=1)
        lancamento, _fatura = CartaoService.adicionar_lancamento({
            'cartao_id': cartao_id,
            'categoria_id': categoria_id,
            'categoria_cartao_id': None,
            'descricao': descricao,
            'valor': valor,
            'data_compra': data_compra,
            'mes_fatura': mes_fatura,
            'numero_parcela': 1,
            'total_parcelas': 1,
            'observacoes': observacoes,
        })
        return lancamento, 'LANCAMENTO'

    @classmethod
    def _criar_conta_operacional(
        cls,
        *,
        categoria_id,
        descricao,
        valor,
        data_referencia,
        competencia,
        observacoes,
        forma_pagamento,
        pago,
        conta_bancaria_id,
        cartao_id,
        categoria_cartao_id,
    ):
        perfil_id = PerfilFinanceiroService.obter_perfil_ativo_id()
        item = ItemDespesa(
            perfil_financeiro_id=perfil_id,
            categoria_id=categoria_id,
            nome=cls._limitar(descricao, 100),
            tipo='Simples',
            descricao=observacoes,
            ativo=True,
            valor=valor,
            valor_pago=valor if pago else None,
            data_vencimento=data_referencia,
            data_pagamento=data_referencia if pago else None,
            pago=bool(pago),
            recorrente=False,
            tipo_recorrencia='mensal',
            mes_competencia=competencia,
            meio_pagamento=forma_pagamento,
            cartao_id=cartao_id,
            item_agregado_id=None,
            categoria_cartao_id=categoria_cartao_id,
        )
        db.session.add(item)
        db.session.flush()

        conta = Conta(
            perfil_financeiro_id=perfil_id,
            item_despesa_id=item.id,
            mes_referencia=data_referencia.replace(day=1),
            descricao=descricao,
            valor=valor,
            data_vencimento=data_referencia,
            data_pagamento=data_referencia if pago else None,
            status_pagamento='Pago' if pago else 'Pendente',
            debito_automatico=forma_pagamento == 'debito_automatico',
            conta_bancaria_id=conta_bancaria_id,
            numero_parcela=1,
            total_parcelas=1,
            observacoes=observacoes,
            is_fatura_cartao=False,
        )
        db.session.add(conta)
        db.session.flush()

        if pago and conta_bancaria_id:
            ContaBancariaService.criar_movimento(
                conta_bancaria_id,
                tipo='DEBITO',
                valor=valor,
                descricao=f'Lancamento documento fiscal - {descricao}',
                data_movimento=data_referencia,
                origem='DOCUMENTO_FISCAL',
                ajustavel=False,
                conta_id=conta.id,
            )

        return conta, 'CONTA'

    @classmethod
    def _criar_vinculo(cls, comprovante, tipo_entidade, entidade, categoria_id, observacoes):
        natureza = cls._natureza_por_categoria(categoria_id) or 'DESPESA_OPERACIONAL'
        resumo = cls._resumo_entidade(tipo_entidade, entidade)
        vinculo = IrComprovanteVinculo(
            comprovante_id=comprovante.id,
            perfil_financeiro_id=PerfilFinanceiroService.obter_perfil_ativo_id(),
            tipo_entidade=tipo_entidade,
            entidade_id=entidade.id,
            resumo_entidade=resumo,
            tipo_vinculo='DOCUMENTO_FISCAL',
            natureza=natureza,
            status_lastro='COM_DOCUMENTO',
            observacoes=cls._limitar(observacoes, 1000),
            ativo=True,
        )
        db.session.add(vinculo)
        db.session.flush()
        return vinculo

    @classmethod
    def _resolver_categoria_sugerida(cls, comprovante):
        if comprovante.categoria_id:
            return {
                'categoria_id': comprovante.categoria_id,
                'categoria_nome': comprovante.categoria.nome if comprovante.categoria else None,
                'origem': comprovante.origem_classificacao or 'comprovante',
                'avisos': [],
            }
        texto = CategoriaPalavraChaveService.normalizar_descricao_importacao(comprovante.texto_extraido or '')
        return CategoriaPalavraChaveService.classificar_por_palavras_chave(texto)

    @staticmethod
    def _resolver_categoria_ir(comprovante, categoria_id):
        if comprovante.categoria_ir:
            return comprovante.categoria_ir
        if not categoria_id:
            return None
        vinculo = IrDocumentoService._buscar_vinculo_ir_por_categoria(categoria_id)
        return vinculo.categoria_ir if vinculo and vinculo.categoria_ir else None

    @staticmethod
    def _natureza_por_categoria(categoria_id):
        categoria_ir = None
        if categoria_id:
            vinculo = IrDocumentoService._buscar_vinculo_ir_por_categoria(categoria_id)
            categoria_ir = vinculo.categoria_ir if vinculo and vinculo.categoria_ir else None
        nome = (categoria_ir.nome if categoria_ir else '').strip().upper()
        if any(chave in nome for chave in ['PATRIMONIO', 'IMOBILIZADO', 'EQUIPAMENTO']):
            return 'PATRIMONIO_IMOBILIZADO'
        if any(chave in nome for chave in ['IMPOSTO', 'TAXA', 'GUIA']):
            return 'IMPOSTO_TAXA'
        return 'DESPESA_OPERACIONAL'

    @staticmethod
    def _descricao_sugerida(comprovante, categoria=None):
        fornecedor = (comprovante.prestador_nome or '').strip()
        complemento = categoria.nome if categoria else None
        if fornecedor and complemento:
            return DocumentoFinanceiroSugestaoService._limitar(f'{fornecedor} - {complemento}', 200)
        if fornecedor:
            return DocumentoFinanceiroSugestaoService._limitar(fornecedor, 200)
        arquivo = comprovante.arquivo.nome_arquivo if comprovante.arquivo else None
        return DocumentoFinanceiroSugestaoService._limitar(f'Documento fiscal - {arquivo or comprovante.id}', 200)

    @staticmethod
    def _observacoes_sugeridas(comprovante):
        partes = ['Criado a partir de sugestao financeira revisada de documento fiscal.']
        if comprovante.arquivo and comprovante.arquivo.nome_arquivo:
            partes.append(f'Documento: {comprovante.arquivo.nome_arquivo}.')
        if comprovante.prestador_cpf_cnpj:
            partes.append(f'CPF/CNPJ prestador: {comprovante.prestador_cpf_cnpj}.')
        if DocumentoFinanceiroSugestaoService._documento_usou_ocr(comprovante):
            partes.append('Texto de origem extraido por OCR local.')
        return ' '.join(partes)[:1000]

    @staticmethod
    def _data_sugerida(comprovante):
        if comprovante.data_documento:
            return comprovante.data_documento
        if comprovante.created_at:
            return comprovante.created_at.date()
        return date.today()

    @staticmethod
    def _documento_usou_ocr(comprovante):
        eventos = comprovante.eventos.order_by(IrComprovanteEvento.created_at.asc()).all()
        return any(str(evento.tipo_evento or '').upper() in {'OCR_EXECUTADO', 'TEXTO_EXTRAIDO_OCR', 'OCR_LIMITADO'} for evento in eventos)

    @staticmethod
    def _obter_categoria(categoria_id, obrigatoria=True):
        categoria_id = DocumentoFinanceiroSugestaoService._parse_int(categoria_id)
        if not categoria_id:
            if obrigatoria:
                raise ValueError('Categoria de Despesa e obrigatoria')
            return None
        categoria = Categoria.query.filter(
            Categoria.id == categoria_id,
            PerfilFinanceiroService.condicao_perfil(Categoria),
        ).first()
        if not categoria or not categoria.ativo:
            raise ValueError('Categoria de Despesa nao encontrada no perfil ativo')
        return categoria

    @staticmethod
    def _obter_cartao(cartao_id):
        cartao = ItemDespesa.query.filter(
            ItemDespesa.id == cartao_id,
            ItemDespesa.tipo == 'Agregador',
            ItemDespesa.ativo == True,  # noqa: E712
            PerfilFinanceiroService.condicao_perfil(ItemDespesa),
        ).first()
        if not cartao:
            raise ValueError('Cartao nao encontrado no perfil ativo')
        return cartao

    @staticmethod
    def _obter_conta_bancaria(conta_bancaria_id):
        conta = ContaBancaria.query.filter(
            ContaBancaria.id == conta_bancaria_id,
            ContaBancaria.status == 'ATIVO',
            PerfilFinanceiroService.condicao_perfil(ContaBancaria),
        ).first()
        if not conta:
            raise ValueError('Conta bancaria nao encontrada no perfil ativo')
        return conta

    @staticmethod
    def _serializar_entidade(tipo_entidade, entidade):
        if tipo_entidade == 'LANCAMENTO':
            return {
                'tipo_entidade': tipo_entidade,
                'id': entidade.id,
                'descricao': entidade.descricao,
                'valor': float(entidade.valor),
                'data': entidade.data_compra.isoformat() if entidade.data_compra else None,
                'categoria_id': entidade.categoria_id,
                'categoria_cartao_id': entidade.categoria_cartao_id,
            }
        return {
            'tipo_entidade': tipo_entidade,
            'id': entidade.id,
            'descricao': entidade.descricao,
            'valor': float(entidade.valor),
            'data': entidade.data_vencimento.isoformat() if entidade.data_vencimento else None,
            'status_pagamento': entidade.status_pagamento,
            'item_despesa_id': entidade.item_despesa_id,
        }

    @staticmethod
    def _resumo_entidade(tipo_entidade, entidade):
        if tipo_entidade == 'LANCAMENTO':
            return entidade.descricao
        return entidade.descricao

    @staticmethod
    def _normalizar_forma_pagamento(valor):
        texto = str(valor or '').strip().lower().replace('-', ' ').replace('_', ' ')
        texto = ' '.join(texto.split())
        aliases = {
            'pix': 'pix',
            'dinheiro': 'dinheiro',
            'cash': 'dinheiro',
            'cartao': 'cartao',
            'cartao de credito': 'cartao',
            'credito': 'cartao',
            'boleto': 'boleto',
            'transferencia': 'transferencia',
            'transferencia bancaria': 'transferencia',
            'ted': 'transferencia',
            'doc': 'transferencia',
            'debito automatico': 'debito_automatico',
            'debito em conta': 'debito_automatico',
            'outros': 'outros',
            'nao informado': 'outros',
        }
        return aliases.get(texto, texto if texto in {item['key'] for item in DocumentoFinanceiroSugestaoService.FORMAS_PAGAMENTO} else 'outros')

    @staticmethod
    def _competencia(valor, data_referencia):
        texto = str(valor or '').strip()
        if len(texto) >= 7:
            return texto[:7]
        return data_referencia.strftime('%Y-%m')

    @staticmethod
    def _parse_date(valor):
        if not valor:
            return None
        if isinstance(valor, date) and not isinstance(valor, datetime):
            return valor
        if isinstance(valor, datetime):
            return valor.date()
        try:
            return datetime.strptime(str(valor)[:10], '%Y-%m-%d').date()
        except ValueError:
            raise ValueError('Data invalida. Use YYYY-MM-DD')

    @staticmethod
    def _parse_int(valor):
        if valor is None or valor == '':
            return None
        try:
            return int(valor)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _decimal(valor):
        if valor is None or valor == '':
            return Decimal('0')
        try:
            return Decimal(str(valor).replace(',', '.'))
        except (InvalidOperation, ValueError):
            raise ValueError('Valor invalido')

    @staticmethod
    def _limitar(valor, tamanho):
        texto = str(valor or '').strip()
        return texto[:tamanho]

    @staticmethod
    def _deduplicar(itens):
        resultado = []
        for item in itens or []:
            texto = str(item or '').strip()
            if texto and texto not in resultado:
                resultado.append(texto)
        return resultado

    @staticmethod
    def _registrar_evento(comprovante: IrComprovante, tipo_evento: str, descricao: str):
        db.session.add(IrComprovanteEvento(
            comprovante_id=comprovante.id,
            tipo_evento=tipo_evento,
            descricao=descricao,
        ))
