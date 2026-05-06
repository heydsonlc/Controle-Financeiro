from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import or_

try:
    from backend.models import (
        DocumentoEmpresarialMetadata,
        IrComprovante,
        IrComprovanteEvento,
        IrComprovanteVinculo,
        db,
    )
    from backend.services.perfil_financeiro_service import PerfilFinanceiroService
except ImportError:
    from models import (
        DocumentoEmpresarialMetadata,
        IrComprovante,
        IrComprovanteEvento,
        IrComprovanteVinculo,
        db,
    )
    from services.perfil_financeiro_service import PerfilFinanceiroService


class DocumentoEmpresarialService:
    TIPOS_DOCUMENTAIS = [
        {'codigo': 'PAGAMENTO_REALIZADO', 'rotulo': 'Pagamento realizado', 'icone': 'receipt'},
        {'codigo': 'NOTA_FISCAL_RECEBIDA', 'rotulo': 'Nota fiscal recebida', 'icone': 'receipt'},
        {'codigo': 'NOTA_FISCAL_EMITIDA', 'rotulo': 'Nota fiscal emitida', 'icone': 'receipt'},
        {'codigo': 'DOCUMENTO_OBRIGATORIO', 'rotulo': 'Documento obrigatorio', 'icone': 'shield'},
        {'codigo': 'DOCUMENTO_SOCIETARIO', 'rotulo': 'Documento societario/cadastral', 'icone': 'briefcase'},
        {'codigo': 'PROCURACAO_REPRESENTACAO', 'rotulo': 'Procuracao / representacao', 'icone': 'briefcase'},
        {'codigo': 'CONTRATO_INSTRUMENTO', 'rotulo': 'Contrato / instrumento', 'icone': 'book'},
        {'codigo': 'CERTIDAO_LICENCA', 'rotulo': 'Certidao / licenca', 'icone': 'shield'},
        {'codigo': 'PATRIMONIO_IMOBILIZADO', 'rotulo': 'Patrimonio / imobilizado', 'icone': 'tool'},
        {'codigo': 'CONTABIL_FISCAL', 'rotulo': 'Contabil / fiscal', 'icone': 'bank'},
        {'codigo': 'OUTRO', 'rotulo': 'Outro', 'icone': 'tag'},
    ]

    CATEGORIAS_DOCUMENTAIS = [
        ('PIX_PAGO', 'Pix pago', 'PAGAMENTO_REALIZADO'),
        ('BOLETO_PAGO', 'Boleto pago', 'PAGAMENTO_REALIZADO'),
        ('TRANSFERENCIA', 'Transferencia', 'PAGAMENTO_REALIZADO'),
        ('GUIA_TAXA_PAGA', 'Guia/taxa paga', 'CONTABIL_FISCAL'),
        ('COMPROVANTE_BANCARIO', 'Comprovante bancario', 'PAGAMENTO_REALIZADO'),
        ('SERVICO_TOMADO', 'Servico tomado', 'NOTA_FISCAL_RECEBIDA'),
        ('COMPRA_MERCADORIA', 'Compra de mercadoria', 'NOTA_FISCAL_RECEBIDA'),
        ('COMPRA_EQUIPAMENTO', 'Compra de equipamento', 'PATRIMONIO_IMOBILIZADO'),
        ('NOTA_FORNECEDOR', 'Nota de fornecedor', 'NOTA_FISCAL_RECEBIDA'),
        ('DESPESA_OPERACIONAL', 'Despesa operacional', 'NOTA_FISCAL_RECEBIDA'),
        ('SERVICO_PRESTADO', 'Servico prestado', 'NOTA_FISCAL_EMITIDA'),
        ('NOTA_CLIENTE', 'Nota para cliente', 'NOTA_FISCAL_EMITIDA'),
        ('NOTA_CANCELADA', 'Nota cancelada', 'NOTA_FISCAL_EMITIDA'),
        ('NOTA_SUBSTITUIDA', 'Nota substituida', 'NOTA_FISCAL_EMITIDA'),
        ('INSCRICAO_MUNICIPAL', 'Inscricao Municipal', 'DOCUMENTO_SOCIETARIO'),
        ('CAE_CADASTRO_ECONOMICO', 'CAE / Cadastro Economico', 'DOCUMENTO_SOCIETARIO'),
        ('USO_DO_SOLO', 'Uso do Solo', 'DOCUMENTO_OBRIGATORIO'),
        ('CERTIFICADO_BOMBEIROS', 'Certificado dos Bombeiros', 'DOCUMENTO_OBRIGATORIO'),
        ('ALVARA_FUNCIONAMENTO', 'Alvara de Funcionamento', 'DOCUMENTO_OBRIGATORIO'),
        ('LICENCA_SANITARIA', 'Licenca Sanitaria', 'CERTIDAO_LICENCA'),
        ('LICENCA_AMBIENTAL', 'Licenca Ambiental', 'CERTIDAO_LICENCA'),
        ('CONTRATO_SOCIAL', 'Contrato Social', 'DOCUMENTO_SOCIETARIO'),
        ('ALTERACAO_CONTRATUAL', 'Alteracao Contratual', 'DOCUMENTO_SOCIETARIO'),
        ('CARTAO_CNPJ', 'Cartao CNPJ / Constituicao', 'DOCUMENTO_SOCIETARIO'),
        ('QUADRO_SOCIETARIO', 'Quadro Societario', 'DOCUMENTO_SOCIETARIO'),
        ('PROCURACAO_CONTADOR', 'Procuracao do Contador', 'PROCURACAO_REPRESENTACAO'),
        ('PROCURACAO_BANCO', 'Procuracao Banco', 'PROCURACAO_REPRESENTACAO'),
        ('AUTORIZACAO_ADMINISTRATIVA', 'Autorizacao Administrativa', 'PROCURACAO_REPRESENTACAO'),
        ('REPRESENTACAO_LEGAL', 'Representacao Legal', 'PROCURACAO_REPRESENTACAO'),
        ('CONTRATO_CLIENTE', 'Contrato de Cliente', 'CONTRATO_INSTRUMENTO'),
        ('CONTRATO_FORNECEDOR', 'Contrato de Fornecedor', 'CONTRATO_INSTRUMENTO'),
        ('CONTRATO_LOCACAO', 'Contrato de Locacao', 'CONTRATO_INSTRUMENTO'),
        ('CONTRATO_PRESTACAO_SERVICO', 'Contrato de Prestacao de Servico', 'CONTRATO_INSTRUMENTO'),
        ('TERMO_ADITIVO', 'Termo/Aditivo', 'CONTRATO_INSTRUMENTO'),
        ('CERTIDAO_MUNICIPAL', 'Certidao Municipal', 'CERTIDAO_LICENCA'),
        ('CERTIDAO_ESTADUAL', 'Certidao Estadual', 'CERTIDAO_LICENCA'),
        ('CERTIDAO_FEDERAL', 'Certidao Federal', 'CERTIDAO_LICENCA'),
        ('FGTS', 'Certidao FGTS', 'CERTIDAO_LICENCA'),
        ('TRABALHISTA', 'Certidao Trabalhista', 'CERTIDAO_LICENCA'),
        ('REGULARIDADE_FISCAL', 'Regularidade Fiscal', 'CERTIDAO_LICENCA'),
        ('NOTA_BEM_PATRIMONIAL', 'Nota de bem patrimonial', 'PATRIMONIO_IMOBILIZADO'),
        ('TERMO_GARANTIA', 'Termo de Garantia', 'PATRIMONIO_IMOBILIZADO'),
        ('MANUAL_GARANTIA', 'Manual/Garantia', 'PATRIMONIO_IMOBILIZADO'),
        ('DOCUMENTO_AQUISICAO', 'Documento de Aquisicao', 'PATRIMONIO_IMOBILIZADO'),
        ('RELATORIO_CONTABIL', 'Relatorio Contabil', 'CONTABIL_FISCAL'),
        ('BALANCETE', 'Balancete', 'CONTABIL_FISCAL'),
        ('DEMONSTRATIVO', 'Demonstrativo', 'CONTABIL_FISCAL'),
        ('APURACAO', 'Apuracao', 'CONTABIL_FISCAL'),
        ('DECLARACAO', 'Declaracao', 'CONTABIL_FISCAL'),
        ('LIVRO_REGISTRO', 'Livro/Registro', 'CONTABIL_FISCAL'),
        ('SEM_CATEGORIA', 'Sem categoria', 'OUTRO'),
        ('DOCUMENTO_DIVERSO', 'Documento diverso', 'OUTRO'),
    ]

    STATUS_DOCUMENTAIS = [
        {'codigo': 'ATIVO', 'rotulo': 'Ativo'},
        {'codigo': 'VALIDO', 'rotulo': 'Valido'},
        {'codigo': 'VENCENDO', 'rotulo': 'Vencendo'},
        {'codigo': 'VENCIDO', 'rotulo': 'Vencido'},
        {'codigo': 'PENDENTE', 'rotulo': 'Pendente'},
        {'codigo': 'EM_REVISAO', 'rotulo': 'Em revisao'},
        {'codigo': 'AGUARDANDO_CONTADOR', 'rotulo': 'Aguardando contador'},
        {'codigo': 'SEM_LASTRO', 'rotulo': 'Sem lastro'},
        {'codigo': 'COM_LASTRO', 'rotulo': 'Com lastro'},
        {'codigo': 'NAO_APLICAVEL', 'rotulo': 'Nao aplicavel'},
        {'codigo': 'ARQUIVADO', 'rotulo': 'Arquivado'},
    ]

    @classmethod
    def obter_taxonomia(cls):
        return {
            'tipos_documentais': cls.TIPOS_DOCUMENTAIS,
            'categorias_documentais': [
                {'codigo': codigo, 'rotulo': rotulo, 'tipo_documental': tipo}
                for codigo, rotulo, tipo in cls.CATEGORIAS_DOCUMENTAIS
            ],
            'status_documentais': cls.STATUS_DOCUMENTAIS,
        }

    @classmethod
    def garantir_perfil_empresa(cls):
        perfil_id = PerfilFinanceiroService.obter_perfil_ativo_id()
        perfil = PerfilFinanceiroService.obter_perfil_por_id(perfil_id)
        if not perfil or (perfil.tipo or '').upper() != 'EMPRESA':
            raise PermissionError('Central de Documentos Empresariais disponivel apenas no perfil Empresa.')
        return perfil

    @classmethod
    def obter_metadata(cls, comprovante_id):
        perfil = cls.garantir_perfil_empresa()
        comprovante = cls._obter_comprovante_empresa(comprovante_id, perfil.id)
        metadata = cls._metadata_ou_padrao(comprovante)
        return cls.serializar_metadata(metadata, comprovante)

    @classmethod
    def atualizar_metadata(cls, comprovante_id, dados):
        perfil = cls.garantir_perfil_empresa()
        comprovante = cls._obter_comprovante_empresa(comprovante_id, perfil.id)
        dados = dados or {}
        metadata = comprovante.metadata_empresarial
        if not metadata:
            tipo_padrao, categoria_padrao = cls._inferir_tipo_categoria(comprovante)
            metadata = DocumentoEmpresarialMetadata(
                comprovante_id=comprovante.id,
                perfil_financeiro_id=perfil.id,
                tipo_documental=tipo_padrao,
                categoria_documental=categoria_padrao,
                origem_documental='USUARIO',
            )
            db.session.add(metadata)
            db.session.flush()

        tipo = cls._normalizar_codigo(dados.get('tipo_documental'), cls._codigos_tipos(), metadata.tipo_documental or 'OUTRO')
        categoria = cls._normalizar_codigo(
            dados.get('categoria_documental'),
            cls._codigos_categorias(),
            metadata.categoria_documental or 'SEM_CATEGORIA',
        )
        if categoria != 'SEM_CATEGORIA':
            categoria_tipo = cls._categoria_tipo(categoria)
            if categoria_tipo:
                tipo = categoria_tipo

        metadata.tipo_documental = tipo
        metadata.categoria_documental = categoria
        metadata.subtipo = cls._texto(dados.get('subtipo'), 120)
        metadata.numero_documento = cls._texto(dados.get('numero_documento'), 120)
        metadata.orgao_emissor = cls._texto(dados.get('orgao_emissor'), 160)
        metadata.data_emissao = cls._parse_date(dados.get('data_emissao'))
        metadata.data_validade = cls._parse_date(dados.get('data_validade'))
        metadata.obrigatorio = cls._parse_bool(dados.get('obrigatorio'))
        metadata.renovavel = cls._parse_bool(dados.get('renovavel'))
        metadata.alerta_dias_antes = cls._parse_int(dados.get('alerta_dias_antes'))
        metadata.responsavel_interno = cls._texto(dados.get('responsavel_interno'), 120)
        metadata.origem_documental = cls._texto(dados.get('origem_documental'), 40) or 'USUARIO'
        metadata.tags = cls._texto(dados.get('tags'), 1000)
        metadata.observacoes = cls._texto(dados.get('observacoes'), 2000)
        metadata.status_documental = cls.calcular_status_documental(
            metadata.data_validade,
            metadata.obrigatorio,
            dados.get('status_documental'),
            bool(metadata.tipo_documental and metadata.categoria_documental),
        )
        metadata.updated_at = datetime.utcnow()
        cls._registrar_evento(comprovante, 'METADATA_EMPRESARIAL_ATUALIZADA', 'Metadados empresariais revisados pelo usuario.')
        return cls.serializar_metadata(metadata, comprovante)

    @classmethod
    def aplicar_filtros_listagem(cls, query, filtros=None):
        filtros = filtros or {}
        precisa_join = any(str(filtros.get(chave) or '').strip() for chave in (
            'tipo_documental', 'categoria_documental', 'status_documental', 'validade', 'obrigatorio'
        ))
        if precisa_join:
            query = query.outerjoin(DocumentoEmpresarialMetadata, DocumentoEmpresarialMetadata.comprovante_id == IrComprovante.id)

        tipo = str(filtros.get('tipo_documental') or '').strip().upper()
        if tipo and tipo not in {'TODOS', 'TODAS'}:
            query = query.filter(DocumentoEmpresarialMetadata.tipo_documental == tipo)

        categoria = str(filtros.get('categoria_documental') or '').strip().upper()
        if categoria and categoria not in {'TODOS', 'TODAS'}:
            query = query.filter(DocumentoEmpresarialMetadata.categoria_documental == categoria)

        status = str(filtros.get('status_documental') or '').strip().upper()
        if status and status not in {'TODOS', 'TODAS'}:
            query = query.filter(DocumentoEmpresarialMetadata.status_documental == status)

        obrigatorio = str(filtros.get('obrigatorio') or '').strip().lower()
        if obrigatorio in {'1', 'true', 'sim', 'yes'}:
            query = query.filter(DocumentoEmpresarialMetadata.obrigatorio.is_(True))
        elif obrigatorio in {'0', 'false', 'nao', 'no'}:
            query = query.filter(or_(DocumentoEmpresarialMetadata.obrigatorio.is_(False), DocumentoEmpresarialMetadata.id.is_(None)))

        validade = str(filtros.get('validade') or '').strip().upper()
        hoje = date.today()
        if validade == 'VENCIDOS':
            query = query.filter(DocumentoEmpresarialMetadata.data_validade < hoje)
        elif validade == 'VENCENDO':
            query = query.filter(
                DocumentoEmpresarialMetadata.data_validade >= hoje,
                DocumentoEmpresarialMetadata.data_validade <= cls._somar_dias(hoje, 30),
            )
        elif validade == 'SEM_VALIDADE':
            query = query.filter(DocumentoEmpresarialMetadata.data_validade.is_(None))

        return query

    @classmethod
    def enriquecer_comprovante_dict(cls, comprovante, data=None):
        data = data or comprovante.to_dict()
        metadata = cls.serializar_metadata(cls._metadata_ou_padrao(comprovante), comprovante)
        data['metadata_empresarial'] = metadata
        data['tipo_documental'] = metadata['tipo_documental']
        data['tipo_documental_label'] = metadata['tipo_documental_label']
        data['categoria_documental'] = metadata['categoria_documental']
        data['categoria_documental_label'] = metadata['categoria_documental_label']
        data['data_validade'] = metadata['data_validade']
        data['status_documental'] = metadata['status_documental']
        data['status_documental_label'] = metadata['status_documental_label']
        data['obrigatorio'] = metadata['obrigatorio']
        data['icone_documental'] = metadata['icone']
        return data

    @classmethod
    def resumo_documentos_empresa(cls, filtros=None):
        cls.garantir_perfil_empresa()
        filtros = filtros or {}
        query = PerfilFinanceiroService.aplicar_perfil_query(IrComprovante.query, IrComprovante)

        ano = cls._parse_int(filtros.get('ano'))
        if ano:
            query = query.filter(IrComprovante.ano_calendario == ano)
        query = cls.aplicar_filtros_listagem(query, filtros)
        documentos = query.order_by(IrComprovante.created_at.desc()).all()

        total = len(documentos)
        obrigatorios = 0
        vencendo = 0
        sem_lastro = 0
        aguardando = 0
        por_tipo = {}
        proximos = []
        checklist = {
            'CONTRATO_SOCIAL': {'label': 'Contrato Social', 'status': 'pendente'},
            'CARTAO_CNPJ': {'label': 'CNPJ / Constituicao', 'status': 'pendente'},
            'INSCRICAO_MUNICIPAL': {'label': 'Inscricao Municipal', 'status': 'pendente'},
            'CERTIFICADO_BOMBEIROS': {'label': 'Certificado dos Bombeiros', 'status': 'pendente'},
        }

        for comprovante in documentos:
            item = cls.enriquecer_comprovante_dict(comprovante)
            metadata = item['metadata_empresarial']
            tipo = metadata['tipo_documental']
            por_tipo.setdefault(tipo, {
                'tipo_documental': tipo,
                'rotulo': metadata['tipo_documental_label'],
                'quantidade': 0,
                'icone': metadata['icone'],
            })
            por_tipo[tipo]['quantidade'] += 1

            if metadata['obrigatorio']:
                obrigatorios += 1
            if metadata['status_documental'] == 'VENCENDO':
                vencendo += 1
            if item.get('status_lastro') in {'SEM_DOCUMENTO', 'PENDENTE'}:
                sem_lastro += 1
            if item.get('status_lastro') == 'AGUARDANDO_CONTADOR' or metadata['status_documental'] == 'AGUARDANDO_CONTADOR':
                aguardando += 1

            categoria = metadata['categoria_documental']
            if categoria in checklist:
                checklist[categoria]['status'] = 'ok' if metadata['status_documental'] not in {'VENCIDO', 'VENCENDO', 'PENDENTE'} else metadata['status_documental'].lower()

            if metadata['data_validade']:
                proximos.append({
                    'id': comprovante.id,
                    'documento': item['prestador_nome'] or item.get('arquivo', {}).get('nome_arquivo') or f'Documento #{comprovante.id}',
                    'categoria_documental': categoria,
                    'categoria_documental_label': metadata['categoria_documental_label'],
                    'data_validade': metadata['data_validade'],
                    'status_documental': metadata['status_documental'],
                })

        proximos.sort(key=lambda item: item['data_validade'])
        return {
            'documentos_cadastrados': total,
            'documentos_obrigatorios': obrigatorios,
            'vencendo_30_dias': vencendo,
            'sem_lastro': sem_lastro,
            'aguardando_contador': aguardando,
            'distribuicao_por_tipo': sorted(por_tipo.values(), key=lambda item: item['rotulo']),
            'proximos_vencimentos': proximos[:6],
            'checklist_empresarial': list(checklist.values()),
        }

    @classmethod
    def serializar_metadata(cls, metadata, comprovante=None):
        if isinstance(metadata, DocumentoEmpresarialMetadata):
            data = metadata.to_dict()
        else:
            data = dict(metadata or {})
        data.setdefault('tipo_documental', 'OUTRO')
        data.setdefault('categoria_documental', 'SEM_CATEGORIA')
        data.setdefault('status_documental', 'ATIVO')
        data.setdefault('obrigatorio', False)
        data.setdefault('renovavel', False)
        data['status_documental'] = cls.calcular_status_documental(
            cls._parse_date(data.get('data_validade')),
            data.get('obrigatorio'),
            data.get('status_documental'),
            bool(data.get('tipo_documental') and data.get('categoria_documental')),
        )
        data['tipo_documental_label'] = cls._tipo_label(data.get('tipo_documental'))
        data['categoria_documental_label'] = cls._categoria_label(data.get('categoria_documental'))
        data['status_documental_label'] = cls._status_label(data.get('status_documental'))
        data['icone'] = cls._icone_documental(data.get('tipo_documental'), data.get('categoria_documental'))
        if comprovante is not None:
            data['documento_label'] = comprovante.prestador_nome or (comprovante.arquivo.nome_arquivo if comprovante.arquivo else f'Documento #{comprovante.id}')
        return data

    @classmethod
    def calcular_status_documental(cls, data_validade=None, obrigatorio=False, status_informado=None, tem_metadados=True):
        status = str(status_informado or '').strip().upper()
        validade = cls._parse_date(data_validade)
        if obrigatorio and not tem_metadados:
            return 'PENDENTE'
        if validade:
            dias = (validade - date.today()).days
            if dias < 0:
                return 'VENCIDO'
            if dias <= 30:
                return 'VENCENDO'
            return 'VALIDO'
        if status in {'PENDENTE', 'EM_REVISAO', 'AGUARDANDO_CONTADOR', 'SEM_LASTRO', 'COM_LASTRO', 'NAO_APLICAVEL', 'ARQUIVADO'}:
            return status
        return 'ATIVO'

    @classmethod
    def _obter_comprovante_empresa(cls, comprovante_id, perfil_id):
        comprovante = IrComprovante.query.filter_by(id=comprovante_id, perfil_financeiro_id=perfil_id).first()
        if not comprovante:
            raise ValueError('Documento empresarial nao encontrado no perfil Empresa.')
        return comprovante

    @classmethod
    def _metadata_ou_padrao(cls, comprovante):
        if comprovante.metadata_empresarial:
            return comprovante.metadata_empresarial
        tipo, categoria = cls._inferir_tipo_categoria(comprovante)
        return {
            'id': None,
            'comprovante_id': comprovante.id,
            'perfil_financeiro_id': comprovante.perfil_financeiro_id,
            'tipo_documental': tipo,
            'categoria_documental': categoria,
            'subtipo': None,
            'numero_documento': None,
            'orgao_emissor': None,
            'data_emissao': comprovante.data_documento.isoformat() if comprovante.data_documento else None,
            'data_validade': None,
            'status_documental': 'ATIVO',
            'obrigatorio': False,
            'renovavel': False,
            'alerta_dias_antes': 30,
            'responsavel_interno': None,
            'origem_documental': 'INFERIDO',
            'tags': None,
            'observacoes': None,
            'created_at': None,
            'updated_at': None,
        }

    @classmethod
    def _inferir_tipo_categoria(cls, comprovante):
        natureza = str(getattr(comprovante.categoria_ir, 'natureza', '') or '').upper()
        if natureza == 'PATRIMONIO_IMOBILIZADO':
            return 'PATRIMONIO_IMOBILIZADO', 'NOTA_BEM_PATRIMONIAL'
        if natureza in {'IMPOSTO_TAXA', 'DOCUMENTO_CONTABIL'}:
            return 'CONTABIL_FISCAL', 'GUIA_TAXA_PAGA'
        if natureza in {'DESPESA_OPERACIONAL', 'SOFTWARE_ASSINATURA', 'DOCUMENTO_FISCAL'}:
            return 'NOTA_FISCAL_RECEBIDA', 'DESPESA_OPERACIONAL'
        texto = ' '.join([
            comprovante.prestador_nome or '',
            comprovante.observacoes or '',
            comprovante.texto_extraido or '',
        ]).lower()
        if 'pix' in texto:
            return 'PAGAMENTO_REALIZADO', 'PIX_PAGO'
        if 'boleto' in texto:
            return 'PAGAMENTO_REALIZADO', 'BOLETO_PAGO'
        if 'contrato' in texto:
            return 'CONTRATO_INSTRUMENTO', 'CONTRATO_FORNECEDOR'
        return 'OUTRO', 'SEM_CATEGORIA'

    @classmethod
    def _categoria_tipo(cls, categoria):
        for codigo, _rotulo, tipo in cls.CATEGORIAS_DOCUMENTAIS:
            if codigo == categoria:
                return tipo
        return None

    @classmethod
    def _tipo_label(cls, codigo):
        for item in cls.TIPOS_DOCUMENTAIS:
            if item['codigo'] == codigo:
                return item['rotulo']
        return 'Outro'

    @classmethod
    def _categoria_label(cls, codigo):
        for item_codigo, rotulo, _tipo in cls.CATEGORIAS_DOCUMENTAIS:
            if item_codigo == codigo:
                return rotulo
        return 'Sem categoria'

    @classmethod
    def _status_label(cls, codigo):
        for item in cls.STATUS_DOCUMENTAIS:
            if item['codigo'] == codigo:
                return item['rotulo']
        return 'Ativo'

    @classmethod
    def _icone_documental(cls, tipo, categoria):
        categoria = str(categoria or '').upper()
        tipo = str(tipo or '').upper()
        if categoria in {'CERTIFICADO_BOMBEIROS'}:
            return 'shield'
        if categoria in {'USO_DO_SOLO'}:
            return 'home'
        if categoria in {'CONTRATO_SOCIAL', 'ALTERACAO_CONTRATUAL', 'CARTAO_CNPJ', 'QUADRO_SOCIETARIO'}:
            return 'briefcase'
        if categoria.startswith('PROCURACAO') or categoria in {'REPRESENTACAO_LEGAL', 'AUTORIZACAO_ADMINISTRATIVA'}:
            return 'briefcase'
        if tipo == 'PAGAMENTO_REALIZADO':
            return 'cash'
        if tipo in {'NOTA_FISCAL_RECEBIDA', 'NOTA_FISCAL_EMITIDA'}:
            return 'receipt'
        if tipo in {'DOCUMENTO_OBRIGATORIO', 'CERTIDAO_LICENCA'}:
            return 'shield'
        if tipo == 'CONTRATO_INSTRUMENTO':
            return 'book'
        if tipo == 'CONTABIL_FISCAL':
            return 'bank'
        if tipo == 'PATRIMONIO_IMOBILIZADO':
            return 'tool'
        return 'tag'

    @classmethod
    def _codigos_tipos(cls):
        return {item['codigo'] for item in cls.TIPOS_DOCUMENTAIS}

    @classmethod
    def _codigos_categorias(cls):
        return {codigo for codigo, _rotulo, _tipo in cls.CATEGORIAS_DOCUMENTAIS}

    @staticmethod
    def _normalizar_codigo(valor, permitidos, padrao):
        texto = str(valor or '').strip().upper()
        return texto if texto in permitidos else padrao

    @staticmethod
    def _parse_date(valor):
        if not valor:
            return None
        if isinstance(valor, date):
            return valor
        texto = str(valor).strip()
        for formato in ('%Y-%m-%d', '%d/%m/%Y'):
            try:
                return datetime.strptime(texto, formato).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _parse_int(valor):
        if valor in {None, ''}:
            return None
        try:
            return int(valor)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_bool(valor):
        if isinstance(valor, bool):
            return valor
        return str(valor or '').strip().lower() in {'1', 'true', 'sim', 'yes', 'on'}

    @staticmethod
    def _texto(valor, limite):
        texto = str(valor or '').strip()
        return texto[:limite] if texto else None

    @staticmethod
    def _somar_dias(base, dias):
        return date.fromordinal(base.toordinal() + dias)

    @staticmethod
    def _registrar_evento(comprovante, tipo_evento, descricao):
        db.session.add(IrComprovanteEvento(
            comprovante_id=comprovante.id,
            tipo_evento=tipo_evento,
            descricao=descricao,
        ))
