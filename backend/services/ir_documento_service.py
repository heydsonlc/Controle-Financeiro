from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
import hashlib
import logging
import re

import pdfplumber
from sqlalchemy import or_
from werkzeug.utils import secure_filename

try:
    from backend.models import (
        Categoria,
        IrCategoria,
        IrCategoriaDespesa,
        IrComprovante,
        IrComprovanteArquivo,
        IrComprovanteEvento,
        db,
    )
    from backend.services.categoria_palavra_chave_service import CategoriaPalavraChaveService
    from backend.services.perfil_financeiro_service import PerfilFinanceiroService
except ImportError:
    from models import (
        Categoria,
        IrCategoria,
        IrCategoriaDespesa,
        IrComprovante,
        IrComprovanteArquivo,
        IrComprovanteEvento,
        db,
    )
    from services.categoria_palavra_chave_service import CategoriaPalavraChaveService
    from services.perfil_financeiro_service import PerfilFinanceiroService


logger = logging.getLogger(__name__)


class IrDocumentoService:
    EXTENSOES_PERMITIDAS = {'pdf', 'png', 'jpg', 'jpeg', 'webp'}
    MIMES_PERMITIDOS = {
        'application/pdf',
        'image/png',
        'image/jpeg',
        'image/webp',
    }
    TAMANHO_MAXIMO = 10 * 1024 * 1024
    CATEGORIAS_IR_INICIAIS = [
        ('Saude', 'Despesas medicas e assistenciais', True, 10),
        ('Odontologia', 'Tratamentos odontologicos', True, 20),
        ('Psicologia', 'Consultas e tratamentos psicologicos', True, 30),
        ('Educacao', 'Despesas educacionais', True, 40),
        ('Fisioterapia', 'Fisioterapia e reabilitacao', True, 50),
        ('Exames', 'Exames laboratoriais e diagnosticos', True, 60),
        ('Plano de Saude', 'Plano de saude e mensalidades assistenciais', True, 70),
        ('Outros', 'Comprovantes relevantes para revisao', False, 999),
    ]

    @classmethod
    def garantir_categorias_ir_iniciais(cls):
        criadas = []
        for nome, descricao, dedutivel, ordem in cls.CATEGORIAS_IR_INICIAIS:
            existente = IrCategoria.query.filter_by(nome=nome).first()
            if existente:
                continue
            categoria = IrCategoria(
                nome=nome,
                descricao=descricao,
                dedutivel=dedutivel,
                ativo=True,
                observacao_fiscal='Classificacao potencial. Revisar com contador.',
                ordem=ordem,
            )
            db.session.add(categoria)
            criadas.append(categoria)
        if criadas:
            db.session.flush()
        return criadas

    @classmethod
    def listar_categorias_ir(cls):
        cls.garantir_categorias_ir_iniciais()
        return IrCategoria.query.order_by(IrCategoria.ordem.asc(), IrCategoria.nome.asc()).all()

    @classmethod
    def criar_categoria_ir(cls, dados):
        nome = str((dados or {}).get('nome') or '').strip()
        if not nome:
            raise ValueError('Nome da Categoria IR e obrigatorio')
        if IrCategoria.query.filter_by(nome=nome).first():
            raise ValueError('Categoria IR ja cadastrada')
        categoria = IrCategoria(
            nome=nome,
            descricao=(dados or {}).get('descricao'),
            dedutivel=bool((dados or {}).get('dedutivel', True)),
            ativo=bool((dados or {}).get('ativo', True)),
            observacao_fiscal=(dados or {}).get('observacao_fiscal'),
            ordem=int((dados or {}).get('ordem') or 0),
        )
        db.session.add(categoria)
        db.session.flush()
        return categoria

    @classmethod
    def listar_vinculos(cls):
        return PerfilFinanceiroService.aplicar_perfil_query(
            IrCategoriaDespesa.query, IrCategoriaDespesa
        ).order_by(IrCategoriaDespesa.id.asc()).all()

    @classmethod
    def criar_vinculo(cls, dados):
        categoria_id = cls._parse_int((dados or {}).get('categoria_id'))
        categoria_ir_id = cls._parse_int((dados or {}).get('categoria_ir_id'))
        if not categoria_id or not categoria_ir_id:
            raise ValueError('Categoria de Despesa e Categoria IR sao obrigatorias')
        categoria = PerfilFinanceiroService.aplicar_perfil_query(
            Categoria.query, Categoria
        ).filter(Categoria.id == categoria_id).first()
        if not categoria:
            raise ValueError('Categoria de Despesa nao encontrada')
        if not IrCategoria.query.get(categoria_ir_id):
            raise ValueError('Categoria IR nao encontrada')

        ativo_existente = PerfilFinanceiroService.aplicar_perfil_query(
            IrCategoriaDespesa.query, IrCategoriaDespesa
        ).filter_by(
            categoria_id=categoria_id,
            ativo=True,
        ).first()
        if ativo_existente:
            ativo_existente.ativo = False
            ativo_existente.updated_at = datetime.utcnow()

        existente = PerfilFinanceiroService.aplicar_perfil_query(
            IrCategoriaDespesa.query, IrCategoriaDespesa
        ).filter_by(
            categoria_id=categoria_id,
            categoria_ir_id=categoria_ir_id,
        ).first()
        if existente:
            existente.ativo = True
            existente.updated_at = datetime.utcnow()
            return existente

        vinculo = IrCategoriaDespesa(
            perfil_financeiro_id=PerfilFinanceiroService.obter_perfil_ativo_id(),
            categoria_id=categoria_id,
            categoria_ir_id=categoria_ir_id,
            ativo=True,
        )
        db.session.add(vinculo)
        db.session.flush()
        return vinculo

    @staticmethod
    def inativar_vinculo(vinculo_id):
        vinculo = PerfilFinanceiroService.aplicar_perfil_query(
            IrCategoriaDespesa.query, IrCategoriaDespesa
        ).filter(IrCategoriaDespesa.id == vinculo_id).first()
        if not vinculo:
            raise ValueError('Vinculo nao encontrado')
        vinculo.ativo = False
        vinculo.updated_at = datetime.utcnow()
        return vinculo

    @classmethod
    def listar_comprovantes(cls, filtros=None):
        filtros = filtros or {}
        query = PerfilFinanceiroService.aplicar_perfil_query(IrComprovante.query, IrComprovante)

        ano = cls._parse_int(filtros.get('ano'))
        if ano:
            query = query.filter(IrComprovante.ano_calendario == ano)

        status = str(filtros.get('status') or '').strip()
        if status and status.upper() != 'TODOS':
            query = query.filter(IrComprovante.status == status.upper())

        categoria_ir_id = cls._parse_int(filtros.get('categoria_ir_id'))
        if categoria_ir_id:
            query = query.filter(IrComprovante.categoria_ir_id == categoria_ir_id)

        busca = str(filtros.get('busca') or '').strip()
        if busca:
            termo = f'%{busca}%'
            query = query.filter(
                or_(
                    IrComprovante.prestador_nome.ilike(termo),
                    IrComprovante.prestador_cpf_cnpj.ilike(termo),
                    IrComprovante.observacoes.ilike(termo),
                )
            )

        return query.order_by(IrComprovante.data_documento.desc(), IrComprovante.created_at.desc()).all()

    @classmethod
    def resumo(cls, comprovantes):
        total = len(comprovantes)
        valor_potencial = Decimal('0')
        pendentes = 0
        categorias = set()
        por_categoria = {}

        for comprovante in comprovantes:
            if comprovante.status in {'PENDENTE_REVISAO', 'ERRO_LEITURA', 'IMPORTADO'}:
                pendentes += 1
            if comprovante.categoria_ir_id:
                categorias.add(comprovante.categoria_ir_id)
            if comprovante.valor is not None and comprovante.dedutivel is not False:
                valor_potencial += Decimal(str(comprovante.valor))
            nome_ir = comprovante.categoria_ir.nome if comprovante.categoria_ir else 'Sem categoria IR'
            por_categoria.setdefault(nome_ir, Decimal('0'))
            if comprovante.valor is not None:
                por_categoria[nome_ir] += Decimal(str(comprovante.valor))

        return {
            'total_comprovantes': total,
            'valor_potencialmente_dedutivel': float(valor_potencial),
            'pendentes_revisao': pendentes,
            'categorias_ir_usadas': len(categorias),
            'totais_por_categoria_ir': [
                {'categoria_ir_nome': nome, 'valor': float(valor)}
                for nome, valor in sorted(por_categoria.items(), key=lambda item: item[0])
            ],
        }

    @classmethod
    def obter_comprovante(cls, comprovante_id):
        comprovante = PerfilFinanceiroService.aplicar_perfil_query(
            IrComprovante.query, IrComprovante
        ).filter(IrComprovante.id == comprovante_id).first()
        if not comprovante:
            raise ValueError('Comprovante nao encontrado')
        return comprovante

    @classmethod
    def atualizar_comprovante(cls, comprovante_id, dados):
        comprovante = cls.obter_comprovante(comprovante_id)
        dados = dados or {}

        if 'ano_calendario' in dados:
            ano = cls._parse_int(dados.get('ano_calendario'))
            if not ano:
                raise ValueError('Ano-calendario invalido')
            comprovante.ano_calendario = ano
        if 'data_documento' in dados:
            comprovante.data_documento = cls._parse_date(dados.get('data_documento'))
        if 'prestador_nome' in dados:
            comprovante.prestador_nome = cls._limitar_texto(dados.get('prestador_nome'), 255)
        if 'prestador_cpf_cnpj' in dados:
            comprovante.prestador_cpf_cnpj = cls._limitar_texto(dados.get('prestador_cpf_cnpj'), 20)
        if 'tomador_nome' in dados:
            comprovante.tomador_nome = cls._limitar_texto(dados.get('tomador_nome'), 255)
        if 'tomador_cpf' in dados:
            comprovante.tomador_cpf = cls._limitar_texto(dados.get('tomador_cpf'), 20)
        if 'valor' in dados:
            comprovante.valor = cls._parse_decimal(dados.get('valor'))
        if 'categoria_id' in dados:
            comprovante.categoria_id = cls._parse_int(dados.get('categoria_id'))
        if 'categoria_ir_id' in dados:
            comprovante.categoria_ir_id = cls._parse_int(dados.get('categoria_ir_id'))
            categoria_ir = IrCategoria.query.get(comprovante.categoria_ir_id) if comprovante.categoria_ir_id else None
            comprovante.dedutivel = categoria_ir.dedutivel if categoria_ir else comprovante.dedutivel
        if 'dedutivel' in dados:
            comprovante.dedutivel = bool(dados.get('dedutivel'))
        if 'observacoes' in dados:
            comprovante.observacoes = dados.get('observacoes')

        if comprovante.status not in {'VALIDADO', 'IGNORADO'}:
            comprovante.status = 'PENDENTE_REVISAO'
        comprovante.updated_at = datetime.utcnow()
        cls._registrar_evento(comprovante, 'PENDENTE_REVISAO', 'Comprovante revisado manualmente.')
        return comprovante

    @classmethod
    def validar_comprovante(cls, comprovante_id):
        comprovante = cls.obter_comprovante(comprovante_id)
        comprovante.status = 'VALIDADO'
        comprovante.updated_at = datetime.utcnow()
        cls._registrar_evento(comprovante, 'VALIDADO', 'Comprovante validado pelo usuario.')
        return comprovante

    @classmethod
    def obter_arquivo(cls, comprovante_id):
        comprovante = cls.obter_comprovante(comprovante_id)
        if not comprovante.arquivo:
            raise ValueError('Arquivo do comprovante nao encontrado')
        return comprovante.arquivo

    @classmethod
    def processar_uploads(cls, arquivos, ano_calendario):
        ano = cls._parse_int(ano_calendario) or date.today().year
        resultados = []

        for arquivo in arquivos:
            try:
                resultado = cls.processar_upload(arquivo, ano)
                resultados.append({'success': True, 'data': resultado})
            except ValueError as exc:
                resultados.append({'success': False, 'error': str(exc), 'arquivo': getattr(arquivo, 'filename', None)})
            except Exception:
                logger.exception('Erro ao processar comprovante de IR')
                resultados.append({'success': False, 'error': 'Erro interno ao processar arquivo', 'arquivo': getattr(arquivo, 'filename', None)})
        db.session.commit()
        return resultados

    @classmethod
    def processar_upload(cls, arquivo, ano_calendario):
        nome_original = arquivo.filename or ''
        extensao = cls._extensao(nome_original)
        conteudo = arquivo.read()
        mime_type = arquivo.mimetype or cls._mime_por_extensao(extensao)
        cls._validar_arquivo(nome_original, extensao, mime_type, conteudo)

        hash_arquivo = hashlib.sha256(conteudo).hexdigest()
        existente = PerfilFinanceiroService.aplicar_perfil_query(
            IrComprovante.query, IrComprovante
        ).filter_by(hash_arquivo=hash_arquivo).first()
        if existente:
            return {
                'duplicado': True,
                'comprovante': existente.to_dict(include_texto=True, include_eventos=True),
                'mensagem': 'Arquivo ja importado anteriormente.',
            }

        comprovante = IrComprovante(
            perfil_financeiro_id=PerfilFinanceiroService.obter_perfil_ativo_id(),
            ano_calendario=ano_calendario,
            status='IMPORTADO',
            hash_arquivo=hash_arquivo,
        )
        db.session.add(comprovante)
        db.session.flush()

        arquivo_model = IrComprovanteArquivo(
            comprovante_id=comprovante.id,
            nome_arquivo=secure_filename(nome_original)[:255] or 'comprovante',
            mime_type=mime_type,
            tamanho_bytes=len(conteudo),
            conteudo=conteudo,
            hash_arquivo=hash_arquivo,
        )
        db.session.add(arquivo_model)
        cls._registrar_evento(comprovante, 'IMPORTADO', 'Arquivo importado e armazenado no banco.')

        cls._analisar_comprovante(comprovante, conteudo, extensao)
        return {
            'duplicado': False,
            'comprovante': comprovante.to_dict(include_texto=True),
            'mensagem': 'Arquivo importado.',
        }

    @classmethod
    def _analisar_comprovante(cls, comprovante, conteudo, extensao):
        if extensao == 'pdf':
            try:
                texto = cls.extrair_texto_pdf(conteudo)
            except Exception:
                comprovante.status = 'ERRO_LEITURA'
                comprovante.observacoes = 'PDF armazenado, mas a leitura textual falhou. OCR fica para etapa futura.'
                cls._registrar_evento(comprovante, 'ERRO_LEITURA', 'Falha ao extrair texto do PDF.')
                return

            if not cls._texto_suficiente(texto):
                comprovante.status = 'PENDENTE_REVISAO'
                comprovante.observacoes = 'PDF armazenado, mas sem texto suficiente. OCR fica para etapa futura.'
                cls._registrar_evento(comprovante, 'PENDENTE_REVISAO', 'PDF sem texto suficiente para leitura automatica.')
                return

            comprovante.texto_extraido = texto
            cls._registrar_evento(comprovante, 'TEXTO_EXTRAIDO', 'Texto extraido de PDF textual.')
            cls._extrair_dados_simples(comprovante, texto)
            cls._classificar_comprovante(comprovante, texto)
            return

        comprovante.status = 'PENDENTE_REVISAO'
        comprovante.observacoes = 'Imagem armazenada. OCR nao disponivel neste MVP.'
        cls._registrar_evento(comprovante, 'PENDENTE_REVISAO', 'Imagem aguardando OCR futuro.')

    @staticmethod
    def extrair_texto_pdf(conteudo):
        paginas = []
        with pdfplumber.open(BytesIO(conteudo)) as pdf:
            for pagina in pdf.pages:
                paginas.append(pagina.extract_text() or '')
        return '\n'.join(paginas).strip()

    @classmethod
    def _extrair_dados_simples(cls, comprovante, texto):
        data_match = re.search(r'\b(\d{2}/\d{2}/\d{4})\b', texto or '')
        if data_match:
            comprovante.data_documento = cls._parse_date(data_match.group(1))
            if comprovante.data_documento:
                comprovante.ano_calendario = comprovante.data_documento.year

        valor = cls._extrair_maior_valor(texto)
        if valor is not None:
            comprovante.valor = valor

        doc_match = re.search(r'\b(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}|\d{3}\.?\d{3}\.?\d{3}-?\d{2})\b', texto or '')
        if doc_match:
            comprovante.prestador_cpf_cnpj = doc_match.group(1)

        prestador = cls._extrair_prestador(texto)
        if prestador:
            comprovante.prestador_nome = prestador
            return

        for linha in (texto or '').splitlines():
            limpa = linha.strip()
            if not limpa or len(limpa) < 4:
                continue
            if re.search(r'(nota|cpf|cnpj|valor|data|total|recibo|serie|prefeitura|secretaria)', limpa, re.IGNORECASE):
                continue
            comprovante.prestador_nome = limpa[:255]
            break

    @staticmethod
    def _extrair_prestador(texto):
        linhas = [linha.strip() for linha in (texto or '').splitlines() if linha.strip()]
        if not linhas:
            return None

        padroes_inicio = (
            'Dados do Prestador de Serviço',
            'Dados do Prestador de Servico',
            'PRESTADOR DE SERVIÇOS',
            'PRESTADOR DE SERVICOS',
            'PRESTADOR DOS SERVIÇOS',
            'PRESTADOR DOS SERVICOS',
        )
        bloqueios = re.compile(
            r'(data|cnpj|cpf|inscri|endere|cep|fone|telefone|email|nota|numero|série|serie|cód|cod|responsavel|identifica|natureza|local|município|municipio)',
            re.IGNORECASE,
        )
        data_ou_numero = re.compile(r'^\d{1,2}/\d{1,2}/\d{4}|^\d{2}/\d{2}/\d{4}|\d{2}:\d{2}|\d{5,}$')

        for idx, linha in enumerate(linhas):
            if not any(padrao.lower() in linha.lower() for padrao in padroes_inicio):
                continue
            for candidata in linhas[idx + 1:idx + 10]:
                if len(candidata) < 4:
                    continue
                if bloqueios.search(candidata) or data_ou_numero.search(candidata):
                    continue
                if re.search(r'[A-Za-zÀ-ÿ]', candidata):
                    return candidata[:255]

        return None

    @classmethod
    def _classificar_comprovante(cls, comprovante, texto):
        normalizado = CategoriaPalavraChaveService.normalizar_descricao_importacao(texto)
        resultado = CategoriaPalavraChaveService.classificar_por_palavras_chave(normalizado)
        comprovante.origem_classificacao = resultado.get('origem')
        comprovante.confianca = resultado.get('confianca')

        categoria_id = resultado.get('categoria_id')
        if not categoria_id:
            comprovante.status = 'PENDENTE_REVISAO'
            cls._registrar_evento(comprovante, 'PENDENTE_REVISAO', 'Sem sugestao segura de Categoria de Despesa.')
            return

        comprovante.categoria_id = categoria_id
        vinculo = PerfilFinanceiroService.aplicar_perfil_query(
            IrCategoriaDespesa.query, IrCategoriaDespesa
        ).filter_by(categoria_id=categoria_id, ativo=True).first()
        if vinculo:
            comprovante.categoria_ir_id = vinculo.categoria_ir_id
            comprovante.dedutivel = vinculo.categoria_ir.dedutivel if vinculo.categoria_ir else None
            comprovante.status = 'CLASSIFICADO'
            cls._registrar_evento(comprovante, 'CLASSIFICADO', 'Categoria de Despesa e Categoria IR sugeridas por palavras-chave.')
            return

        comprovante.status = 'PENDENTE_REVISAO'
        cls._registrar_evento(comprovante, 'PENDENTE_REVISAO', 'Categoria de Despesa sugerida, mas sem vinculo com Categoria IR.')

    @staticmethod
    def _registrar_evento(comprovante, tipo_evento, descricao):
        db.session.add(IrComprovanteEvento(
            comprovante_id=comprovante.id,
            tipo_evento=tipo_evento,
            descricao=descricao,
        ))

    @classmethod
    def _validar_arquivo(cls, nome, extensao, mime_type, conteudo):
        if not nome:
            raise ValueError('Nome de arquivo vazio')
        if extensao not in cls.EXTENSOES_PERMITIDAS:
            raise ValueError('Tipo de arquivo nao permitido')
        if mime_type not in cls.MIMES_PERMITIDOS:
            raise ValueError('MIME type nao permitido')
        if not conteudo:
            raise ValueError('Arquivo vazio')
        if len(conteudo) > cls.TAMANHO_MAXIMO:
            raise ValueError('Arquivo excede o tamanho maximo permitido')
        if not cls._assinatura_valida(conteudo, extensao):
            raise ValueError('Assinatura do arquivo invalida')

    @staticmethod
    def _assinatura_valida(conteudo, extensao):
        if extensao == 'pdf':
            return conteudo.startswith(b'%PDF')
        if extensao == 'png':
            return conteudo.startswith(b'\x89PNG\r\n\x1a\n')
        if extensao in {'jpg', 'jpeg'}:
            return conteudo.startswith(b'\xff\xd8\xff')
        if extensao == 'webp':
            return len(conteudo) >= 12 and conteudo[:4] == b'RIFF' and conteudo[8:12] == b'WEBP'
        return False

    @staticmethod
    def _extensao(nome):
        if '.' not in (nome or ''):
            return ''
        return nome.rsplit('.', 1)[1].lower()

    @staticmethod
    def _mime_por_extensao(extensao):
        return {
            'pdf': 'application/pdf',
            'png': 'image/png',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'webp': 'image/webp',
        }.get(extensao, 'application/octet-stream')

    @staticmethod
    def _texto_suficiente(texto):
        return len((texto or '').strip()) >= 30

    @staticmethod
    def _parse_int(valor):
        if valor in {None, ''}:
            return None
        try:
            return int(valor)
        except (TypeError, ValueError):
            return None

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
    def _parse_decimal(valor):
        if valor in {None, ''}:
            return None
        texto = str(valor).strip().replace('R$', '').replace(' ', '')
        if ',' in texto:
            texto = texto.replace('.', '').replace(',', '.')
        try:
            return Decimal(texto)
        except (InvalidOperation, ValueError):
            return None

    @classmethod
    def _extrair_maior_valor(cls, texto):
        valores = []
        for bruto in re.findall(r'(?:R\$\s*)?(\d{1,3}(?:\.\d{3})*,\d{2})', texto or ''):
            valor = cls._parse_decimal(bruto)
            if valor is not None:
                valores.append(valor)
        return max(valores) if valores else None

    @staticmethod
    def _limitar_texto(valor, limite):
        if valor is None:
            return None
        return str(valor).strip()[:limite] or None
