from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
import unicodedata

try:
    from backend.models import IrComprovante, IrComprovanteVinculo
    from backend.services.patrimonio_empresarial_service import PatrimonioEmpresarialService
    from backend.services.perfil_financeiro_service import PerfilFinanceiroService
except ImportError:
    from models import IrComprovante, IrComprovanteVinculo
    from services.patrimonio_empresarial_service import PatrimonioEmpresarialService
    from services.perfil_financeiro_service import PerfilFinanceiroService


class PatrimonioSugestaoService:
    CATEGORIAS = ('Informatica', 'Moveis', 'Equipamentos', 'Estrutura', 'Veiculos', 'Ferramentas', 'Outros')
    VIDA_UTIL = {
        'Informatica': 36,
        'Moveis': 120,
        'Equipamentos': 60,
        'Estrutura': 120,
        'Veiculos': 60,
        'Ferramentas': 60,
        'Outros': 60,
    }
    REGRAS = [
        ('Informatica', (
            ('notebook', 'Notebook'),
            ('laptop', 'Notebook'),
            ('computador', 'Computador'),
            ('monitor', 'Monitor'),
            ('teclado', 'Teclado'),
            ('mouse', 'Mouse'),
            ('impressora', 'Impressora'),
        )),
        ('Moveis', (
            ('cadeira ergonomica', 'Cadeira ergonomica'),
            ('cadeira', 'Cadeira'),
            ('mesa de reuniao', 'Mesa de reuniao'),
            ('mesa', 'Mesa'),
            ('armario', 'Armario'),
            ('gaveteiro', 'Gaveteiro'),
            ('estante', 'Estante'),
        )),
        ('Estrutura', (
            ('ar-condicionado', 'Ar-condicionado'),
            ('ar condicionado', 'Ar-condicionado'),
            ('climatizador', 'Climatizador'),
            ('instalacao', 'Estrutura'),
            ('split', 'Ar-condicionado'),
        )),
        ('Equipamentos', (
            ('camera', 'Camera'),
            ('roteador', 'Roteador'),
            ('nobreak', 'Nobreak'),
            ('telefone', 'Telefone'),
        )),
        ('Ferramentas', (
            ('furadeira', 'Furadeira'),
            ('ferramenta', 'Ferramenta'),
            ('serra', 'Serra'),
            ('parafusadeira', 'Parafusadeira'),
        )),
        ('Veiculos', (
            ('veiculo', 'Veiculo'),
            ('carro', 'Veiculo'),
            ('moto', 'Moto'),
        )),
    ]

    @classmethod
    def gerar_sugestao(cls, comprovante_id):
        perfil_id, perfil, is_empresa = PatrimonioEmpresarialService.contexto()
        if not is_empresa:
            raise PermissionError('Sugestao patrimonial disponivel apenas no perfil Empresa')

        comprovante = PatrimonioEmpresarialService._obter_comprovante_perfil(comprovante_id, perfil_id)
        if not comprovante:
            raise LookupError('Documento fiscal nao encontrado no perfil ativo')

        avisos = []
        vinculo_existente = cls._vinculo_patrimonial_existente(comprovante.id, perfil_id)
        if vinculo_existente:
            avisos.append('Este documento fiscal ja esta vinculado a um bem patrimonial.')

        texto_base = cls._texto_base(comprovante)
        categoria, nome_base, termo = cls._inferir_categoria_nome(texto_base)
        valor = cls._decimal(comprovante.valor)
        vida_util = cls.VIDA_UTIL.get(categoria, cls.VIDA_UTIL['Outros'])
        depreciacao = cls._calcular_depreciacao(valor, vida_util)
        documento_numero = cls._extrair_numero_documento(texto_base) or f'DOC-{comprovante.id}'
        data_aquisicao = cls._data_documento(comprovante)
        imagem = cls._sugerir_imagem(categoria, nome_base, texto_base)

        if not texto_base.strip():
            avisos.append('Texto extraido indisponivel. Revise os campos manualmente.')
        if categoria == 'Outros':
            avisos.append('Categoria patrimonial nao identificada com seguranca.')
        if valor <= Decimal('0'):
            avisos.append('Valor de aquisicao nao identificado automaticamente.')

        observacoes = [
            'Sugestao gerada a partir de documento fiscal importado.',
            'Vida util sugerida apenas para controle gerencial. Validacao contabil deve ser feita pelo contador.',
        ]
        if termo:
            observacoes.append(f'Termo usado na heuristica: {termo}.')
        if comprovante.origem_classificacao and 'OCR' in str(comprovante.origem_classificacao).upper():
            avisos.append('Sugestao baseada em texto extraido por OCR. Revise os dados antes de confirmar.')

        return {
            'comprovante_id': comprovante.id,
            'documento': PatrimonioEmpresarialService.serializar_documento(comprovante),
            'bloqueado': bool(vinculo_existente),
            'vinculo_existente': vinculo_existente.to_dict() if vinculo_existente else None,
            'nome': cls._montar_nome(nome_base, texto_base),
            'categoria': categoria,
            'descricao': cls._descricao(comprovante, nome_base),
            'fornecedor': comprovante.prestador_nome or '',
            'documento_numero': documento_numero,
            'data_aquisicao': data_aquisicao.isoformat() if data_aquisicao else None,
            'valor_aquisicao': float(valor),
            'vida_util_meses': vida_util,
            'depreciacao_mensal': float(depreciacao) if depreciacao is not None else None,
            'centro_custo': '',
            'localizacao': '',
            'responsavel': '',
            'imagem_arquivo': imagem,
            'status_documental': 'COM_LASTRO',
            'natureza': 'PATRIMONIO_IMOBILIZADO',
            'observacoes': '\n'.join(observacoes),
            'avisos': avisos,
            'origem': 'texto_extraido' if comprovante.texto_extraido else 'dados_revisados',
            'campos_editaveis': [
                'nome',
                'categoria',
                'descricao',
                'fornecedor',
                'documento_numero',
                'data_aquisicao',
                'valor_aquisicao',
                'vida_util_meses',
                'centro_custo',
                'localizacao',
                'responsavel',
                'imagem_arquivo',
                'observacoes',
            ],
        }

    @staticmethod
    def _texto_base(comprovante):
        partes = [
            comprovante.texto_extraido,
            comprovante.observacoes,
            comprovante.prestador_nome,
            comprovante.categoria.nome if comprovante.categoria else None,
            comprovante.categoria_ir.nome if comprovante.categoria_ir else None,
            comprovante.arquivo.nome_arquivo if comprovante.arquivo else None,
        ]
        return ' '.join(str(parte or '') for parte in partes)

    @classmethod
    def _inferir_categoria_nome(cls, texto):
        normalizado = cls._normalizar(texto)
        melhor = None
        for categoria, regras in cls.REGRAS:
            for termo, nome in regras:
                posicao = normalizado.find(termo)
                if posicao >= 0 and (melhor is None or posicao < melhor[0]):
                    melhor = (posicao, categoria, nome, termo)
        if melhor:
            return melhor[1], melhor[2], melhor[3]
        return 'Outros', 'Bem patrimonial', None

    @classmethod
    def _montar_nome(cls, nome_base, texto):
        normalizado = cls._normalizar(texto)
        if nome_base == 'Notebook':
            match = re.search(r'\bnotebook\s+([a-z0-9][a-z0-9\s-]{1,40})', normalizado)
            if match:
                candidato = 'Notebook ' + match.group(1).strip()
                return candidato.title()[:160]
        if nome_base == 'Impressora':
            match = re.search(r'\bimpressora\s+([a-z0-9][a-z0-9\s-]{1,32})', normalizado)
            if match:
                candidato = 'Impressora ' + match.group(1).strip()
                return candidato.title()[:160]
        return nome_base[:160]

    @staticmethod
    def _descricao(comprovante, nome_base):
        fornecedor = comprovante.prestador_nome or 'fornecedor nao identificado'
        arquivo = comprovante.arquivo.nome_arquivo if comprovante.arquivo else None
        base = f'{nome_base} sugerido a partir de documento fiscal de {fornecedor}.'
        if arquivo:
            base += f' Arquivo: {arquivo}.'
        return base[:2000]

    @staticmethod
    def _extrair_numero_documento(texto):
        normalizado = PatrimonioSugestaoService._normalizar(texto)
        padroes = [
            r'(?:nf|nfs-e|nota fiscal|nota|numero|nro|no)\D{0,16}(\d{3,})',
            r'\b(\d{5,})\b',
        ]
        for padrao in padroes:
            match = re.search(padrao, normalizado)
            if match:
                return match.group(1)[:80]
        return None

    @staticmethod
    def _data_documento(comprovante):
        if comprovante.data_documento:
            return comprovante.data_documento
        if comprovante.created_at:
            return comprovante.created_at.date()
        return date.today()

    @classmethod
    def _sugerir_imagem(cls, categoria, nome_base, texto):
        imagens = PatrimonioEmpresarialService.listar_imagens_disponiveis()
        if not imagens:
            return None
        alvo = cls._normalizar(' '.join([categoria, nome_base, texto]))
        preferencias = {
            'Informatica': ('notebook', 'impressora', 'monitor', 'webcam'),
            'Moveis': ('cadeira', 'mesa', 'moveis'),
            'Estrutura': ('ar_condicionado', 'ar condicionado'),
            'Equipamentos': ('impressora', 'webcam', 'monitor'),
            'Ferramentas': ('ferramenta',),
            'Veiculos': ('veiculo',),
            'Outros': (),
        }
        chaves = []
        if 'impressora' in alvo:
            chaves.append('impressora')
        if 'monitor' in alvo:
            chaves.append('monitor')
        if 'cadeira' in alvo:
            chaves.append('cadeira')
        if 'ar condicionado' in alvo or 'ar-condicionado' in alvo:
            chaves.append('ar_condicionado')
        chaves.extend(preferencias.get(categoria, ()))
        for chave in chaves:
            for imagem in imagens:
                nome = cls._normalizar(imagem.get('arquivo'))
                if cls._normalizar(chave).replace(' ', '_') in nome.replace(' ', '_'):
                    return imagem.get('arquivo')
        return None

    @staticmethod
    def _vinculo_patrimonial_existente(comprovante_id, perfil_id):
        return IrComprovanteVinculo.query.filter_by(
            comprovante_id=comprovante_id,
            perfil_financeiro_id=perfil_id,
            tipo_entidade='PATRIMONIO',
            ativo=True,
        ).order_by(IrComprovanteVinculo.created_at.desc()).first()

    @staticmethod
    def _normalizar(valor):
        texto = str(valor or '').lower()
        texto = unicodedata.normalize('NFKD', texto)
        texto = ''.join(ch for ch in texto if not unicodedata.combining(ch))
        texto = re.sub(r'[^a-z0-9\s-]+', ' ', texto)
        return re.sub(r'\s+', ' ', texto).strip()

    @staticmethod
    def _decimal(valor):
        if valor in {None, ''}:
            return Decimal('0')
        try:
            return Decimal(str(valor)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        except (InvalidOperation, ValueError):
            return Decimal('0')

    @staticmethod
    def _calcular_depreciacao(valor, vida_util_meses):
        if not vida_util_meses or vida_util_meses <= 0:
            return None
        return (PatrimonioSugestaoService._decimal(valor) / Decimal(vida_util_meses)).quantize(
            Decimal('0.01'),
            rounding=ROUND_HALF_UP,
        )
