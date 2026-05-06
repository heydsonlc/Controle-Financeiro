from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from sqlalchemy import func, or_

try:
    from backend.models import BemPatrimonial, IrComprovante, IrComprovanteVinculo, db
    from backend.services.perfil_financeiro_service import PerfilFinanceiroService
except ImportError:
    from models import BemPatrimonial, IrComprovante, IrComprovanteVinculo, db
    from services.perfil_financeiro_service import PerfilFinanceiroService


STATUS_DOCUMENTAIS_COM_LASTRO = {'COM_LASTRO', 'COM_DOCUMENTO', 'VALIDADO'}
STATUS_DOCUMENTAIS_PENDENTES = {'SEM_DOCUMENTO', 'PENDENTE', 'AGUARDANDO_CONTADOR', 'DIVERGENTE'}


class PatrimonioEmpresarialService:
    STATUS_BEM = {'ATIVO', 'INATIVO', 'BAIXADO', 'EM_REVISAO'}
    STATUS_DOCUMENTAL = {
        'COM_LASTRO',
        'SEM_DOCUMENTO',
        'PENDENTE',
        'AGUARDANDO_CONTADOR',
        'DIVERGENTE',
        'NAO_APLICAVEL',
    }
    TIPOS_VINCULO = {'NOTA_FISCAL', 'COMPROVANTE', 'RECIBO', 'CONTRATO', 'DOCUMENTO_CONTABIL', 'OUTRO'}
    NATUREZAS = {
        'PATRIMONIO_IMOBILIZADO',
        'DESPESA_OPERACIONAL',
        'SOFTWARE_ASSINATURA',
        'IMPOSTO_TAXA',
        'OUTRO',
    }

    @classmethod
    def contexto(cls):
        perfil_id = PerfilFinanceiroService.obter_perfil_ativo_id()
        perfil = PerfilFinanceiroService.obter_perfil_por_id(perfil_id)
        return perfil_id, perfil, bool(perfil and perfil.tipo == 'EMPRESA')

    @classmethod
    def listar_bens(cls, filtros=None):
        perfil_id, perfil, is_empresa = cls.contexto()
        if not is_empresa:
            return []

        filtros = filtros or {}
        query = BemPatrimonial.query.filter(BemPatrimonial.perfil_financeiro_id == perfil_id)

        categoria = cls._texto(filtros.get('categoria'), 80)
        if categoria and categoria.upper() != 'TODAS':
            query = query.filter(BemPatrimonial.categoria == categoria)

        status = cls._normalizar_opcao(filtros.get('status'), cls.STATUS_BEM, None)
        if status:
            query = query.filter(BemPatrimonial.status == status)

        status_documental = cls._normalizar_status_documento(filtros.get('documento') or filtros.get('status_documental'))
        if status_documental:
            query = query.filter(BemPatrimonial.status_documental == status_documental)

        ano = cls._parse_int(filtros.get('ano'))
        if ano:
            query = query.filter(
                BemPatrimonial.data_aquisicao >= date(ano, 1, 1),
                BemPatrimonial.data_aquisicao <= date(ano, 12, 31),
            )

        busca = cls._texto(filtros.get('busca') or filtros.get('q'), 120)
        if busca:
            like = f'%{busca}%'
            query = query.filter(or_(
                BemPatrimonial.nome.ilike(like),
                BemPatrimonial.codigo.ilike(like),
                BemPatrimonial.categoria.ilike(like),
                BemPatrimonial.fornecedor.ilike(like),
                BemPatrimonial.documento_numero.ilike(like),
            ))

        bens = query.order_by(
            BemPatrimonial.data_aquisicao.desc(),
            BemPatrimonial.id.desc(),
        ).all()
        return [cls.serializar_bem(bem, include_documento=True) for bem in bens]

    @classmethod
    def obter_bem(cls, bem_id):
        perfil_id, perfil, is_empresa = cls.contexto()
        if not is_empresa:
            raise PermissionError('Patrimonio empresarial disponivel apenas no perfil Empresa')
        bem = BemPatrimonial.query.filter_by(id=bem_id, perfil_financeiro_id=perfil_id).first()
        if not bem:
            raise LookupError('Bem patrimonial nao encontrado no perfil ativo')
        return cls.serializar_bem(bem, include_documento=True)

    @classmethod
    def criar_bem(cls, dados):
        perfil_id, perfil, is_empresa = cls.contexto()
        if not is_empresa:
            raise PermissionError('Patrimonio empresarial disponivel apenas no perfil Empresa')

        dados = dados or {}
        nome = cls._texto(dados.get('nome'), 160)
        if not nome:
            raise ValueError('Nome do bem e obrigatorio')

        comprovante_id = cls._parse_int(dados.get('comprovante_id'))
        status_documental = 'COM_LASTRO' if comprovante_id else cls._normalizar_opcao(
            dados.get('status_documental'), cls.STATUS_DOCUMENTAL, 'SEM_DOCUMENTO'
        )

        bem = BemPatrimonial(
            perfil_financeiro_id=perfil_id,
            nome=nome,
            codigo=cls._texto(dados.get('codigo'), 60),
            categoria=cls._texto(dados.get('categoria'), 80) or 'Equipamentos',
            descricao=cls._texto(dados.get('descricao'), 2000),
            fornecedor=cls._texto(dados.get('fornecedor'), 255),
            documento_numero=cls._texto(dados.get('documento_numero'), 80),
            imagem_arquivo=cls._normalizar_imagem(dados.get('imagem_arquivo')),
            data_aquisicao=cls._parse_date(dados.get('data_aquisicao')),
            valor_aquisicao=cls._decimal(dados.get('valor_aquisicao')),
            vida_util_meses=cls._parse_int(dados.get('vida_util_meses')),
            centro_custo=cls._texto(dados.get('centro_custo'), 120),
            localizacao=cls._texto(dados.get('localizacao'), 120),
            responsavel=cls._texto(dados.get('responsavel'), 120),
            status=cls._normalizar_opcao(dados.get('status'), cls.STATUS_BEM, 'ATIVO'),
            status_documental=status_documental,
            observacoes=cls._texto(dados.get('observacoes'), 2000),
        )
        bem.depreciacao_mensal = cls._calcular_depreciacao(bem.valor_aquisicao, bem.vida_util_meses)
        db.session.add(bem)
        db.session.flush()

        if comprovante_id:
            cls._criar_vinculo_documento(bem, comprovante_id, dados)

        db.session.commit()
        return cls.serializar_bem(bem, include_documento=True)

    @classmethod
    def atualizar_bem(cls, bem_id, dados):
        perfil_id, perfil, is_empresa = cls.contexto()
        if not is_empresa:
            raise PermissionError('Patrimonio empresarial disponivel apenas no perfil Empresa')
        bem = BemPatrimonial.query.filter_by(id=bem_id, perfil_financeiro_id=perfil_id).first()
        if not bem:
            raise LookupError('Bem patrimonial nao encontrado no perfil ativo')
        dados = dados or {}

        campos_texto = {
            'nome': 160,
            'codigo': 60,
            'categoria': 80,
            'descricao': 2000,
            'fornecedor': 255,
            'documento_numero': 80,
            'imagem_arquivo': 255,
            'centro_custo': 120,
            'localizacao': 120,
            'responsavel': 120,
            'observacoes': 2000,
        }
        for campo, limite in campos_texto.items():
            if campo in dados:
                valor = cls._normalizar_imagem(dados.get(campo)) if campo == 'imagem_arquivo' else cls._texto(dados.get(campo), limite)
                if campo == 'nome' and not valor:
                    raise ValueError('Nome do bem e obrigatorio')
                setattr(bem, campo, valor)
        if 'data_aquisicao' in dados:
            bem.data_aquisicao = cls._parse_date(dados.get('data_aquisicao'))
        if 'valor_aquisicao' in dados:
            bem.valor_aquisicao = cls._decimal(dados.get('valor_aquisicao'))
        if 'vida_util_meses' in dados:
            bem.vida_util_meses = cls._parse_int(dados.get('vida_util_meses'))
        if 'status' in dados:
            bem.status = cls._normalizar_opcao(dados.get('status'), cls.STATUS_BEM, bem.status)
        if 'status_documental' in dados:
            bem.status_documental = cls._normalizar_opcao(
                dados.get('status_documental'), cls.STATUS_DOCUMENTAL, bem.status_documental
            )
        bem.depreciacao_mensal = cls._calcular_depreciacao(bem.valor_aquisicao, bem.vida_util_meses)
        bem.updated_at = datetime.utcnow()
        db.session.commit()
        return cls.serializar_bem(bem, include_documento=True)

    @classmethod
    def vincular_documento(cls, bem_id, dados):
        perfil_id, perfil, is_empresa = cls.contexto()
        if not is_empresa:
            raise PermissionError('Patrimonio empresarial disponivel apenas no perfil Empresa')
        bem = BemPatrimonial.query.filter_by(id=bem_id, perfil_financeiro_id=perfil_id).first()
        if not bem:
            raise LookupError('Bem patrimonial nao encontrado no perfil ativo')
        dados = dados or {}
        comprovante_id = cls._parse_int(dados.get('comprovante_id'))
        if not comprovante_id:
            raise ValueError('Documento fiscal e obrigatorio')

        cls._criar_vinculo_documento(bem, comprovante_id, dados)
        bem.status_documental = 'COM_LASTRO'
        bem.updated_at = datetime.utcnow()
        db.session.commit()
        return cls.serializar_bem(bem, include_documento=True)

    @classmethod
    def criar_a_partir_documento(cls, dados):
        perfil_id, perfil, is_empresa = cls.contexto()
        if not is_empresa:
            raise PermissionError('Patrimonio empresarial disponivel apenas no perfil Empresa')
        dados = dados or {}
        comprovante = cls._obter_comprovante_perfil(cls._parse_int(dados.get('comprovante_id')), perfil_id)
        if not comprovante:
            raise ValueError('Documento fiscal e obrigatorio')
        cls._validar_documento_sem_vinculo_patrimonial(comprovante.id, perfil_id)

        fornecedor = cls._texto(dados.get('fornecedor'), 255) or comprovante.prestador_nome
        nome = cls._texto(dados.get('nome'), 160)
        if not nome:
            base = fornecedor or 'Documento fiscal'
            nome = f'Bem patrimonial - {base}'[:160]

        payload = {
            **dados,
            'nome': nome,
            'fornecedor': fornecedor,
            'data_aquisicao': dados.get('data_aquisicao') or (comprovante.data_documento.isoformat() if comprovante.data_documento else None),
            'valor_aquisicao': dados.get('valor_aquisicao') if dados.get('valor_aquisicao') not in {None, ''} else comprovante.valor,
            'categoria': dados.get('categoria') or 'Equipamentos',
            'documento_numero': dados.get('documento_numero') or f'DOC-{comprovante.id}',
            'comprovante_id': comprovante.id,
            'status_documental': 'COM_LASTRO',
        }
        return cls.criar_bem(payload)

    @classmethod
    def documentos_vinculaveis(cls, busca=None):
        perfil_id, perfil, is_empresa = cls.contexto()
        if not is_empresa:
            return []

        subquery = db.session.query(IrComprovanteVinculo.comprovante_id).filter(
            IrComprovanteVinculo.perfil_financeiro_id == perfil_id,
            IrComprovanteVinculo.tipo_entidade == 'PATRIMONIO',
            IrComprovanteVinculo.ativo == True,  # noqa: E712
        )
        query = IrComprovante.query.filter(
            IrComprovante.perfil_financeiro_id == perfil_id,
            ~IrComprovante.id.in_(subquery),
        )

        termo = cls._texto(busca, 120)
        if termo:
            like = f'%{termo}%'
            query = query.filter(or_(
                IrComprovante.prestador_nome.ilike(like),
                IrComprovante.prestador_cpf_cnpj.ilike(like),
                IrComprovante.observacoes.ilike(like),
                IrComprovante.hash_arquivo.ilike(like),
            ))

        comprovantes = query.order_by(
            IrComprovante.data_documento.desc(),
            IrComprovante.id.desc(),
        ).limit(50).all()
        return [cls.serializar_documento(comprovante) for comprovante in comprovantes]

    @classmethod
    def listar_imagens_disponiveis(cls):
        img_dir = Path(__file__).resolve().parents[2] / 'frontend' / 'static' / 'img'
        if not img_dir.exists():
            return []
        imagens = []
        for arquivo in sorted(img_dir.iterdir(), key=lambda item: item.name.lower()):
            if not arquivo.is_file():
                continue
            if not arquivo.name.lower().startswith('patrimonio'):
                continue
            if arquivo.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp'}:
                continue
            imagens.append({
                'arquivo': arquivo.name,
                'url': f'/static/img/{arquivo.name}',
                'label': cls._label_imagem(arquivo.stem),
            })
        return imagens

    @classmethod
    def resumo(cls):
        perfil_id, perfil, is_empresa = cls.contexto()
        if not is_empresa:
            return {
                'modo': 'PESSOAL',
                'patrimonio_total': 0,
                'bens_cadastrados': 0,
                'bens_com_lastro': 0,
                'pendencias_documentais': 0,
                'aquisicoes_ano': {'quantidade': 0, 'valor': 0},
                'composicao': [],
                'pendencias_prioritarias': [],
            }

        bens = BemPatrimonial.query.filter_by(perfil_financeiro_id=perfil_id).all()
        total = sum(cls._decimal(bem.valor_aquisicao) for bem in bens)
        com_lastro = [bem for bem in bens if bem.status_documental in STATUS_DOCUMENTAIS_COM_LASTRO]
        pendentes = [bem for bem in bens if bem.status_documental in STATUS_DOCUMENTAIS_PENDENTES]
        ano_atual = date.today().year
        aquisicoes_ano = [
            bem for bem in bens
            if bem.data_aquisicao and bem.data_aquisicao.year == ano_atual
        ]

        composicao = cls._composicao_por_categoria(bens, total)
        pendencias = [
            cls.serializar_bem(bem, include_documento=True)
            for bem in sorted(pendentes, key=lambda item: (item.data_aquisicao or date.min, item.id), reverse=True)[:6]
        ]

        return {
            'modo': 'EMPRESA',
            'patrimonio_total': float(total),
            'bens_cadastrados': len(bens),
            'bens_com_lastro': len(com_lastro),
            'percentual_com_lastro': round((len(com_lastro) / len(bens)) * 100, 1) if bens else 0,
            'pendencias_documentais': len(pendentes),
            'aquisicoes_ano': {
                'quantidade': len(aquisicoes_ano),
                'valor': float(sum(cls._decimal(bem.valor_aquisicao) for bem in aquisicoes_ano)),
            },
            'composicao': composicao,
            'pendencias_prioritarias': pendencias,
        }

    @classmethod
    def serializar_bem(cls, bem, include_documento=False):
        data = bem.to_dict()
        data['status_label'] = cls._status_label(bem.status)
        data['status_documental_label'] = cls._status_documental_label(bem.status_documental)
        data['imagem_chave'] = cls._imagem_chave(bem)
        data['imagem_url'] = cls._imagem_url(bem.imagem_arquivo)
        data['documento'] = None
        data['documento_label'] = 'Sem documento'
        if include_documento:
            documento = cls._documento_do_bem(bem)
            if documento:
                data['documento'] = documento
                numero = bem.documento_numero or f"DOC-{documento['id']}"
                data['documento_label'] = f"{documento.get('tipo_vinculo_label') or 'Documento'} {numero}"
        return data

    @classmethod
    def serializar_documento(cls, comprovante):
        return {
            'id': comprovante.id,
            'label': cls._documento_label(comprovante),
            'prestador_nome': comprovante.prestador_nome,
            'prestador_cpf_cnpj': comprovante.prestador_cpf_cnpj,
            'data_documento': comprovante.data_documento.isoformat() if comprovante.data_documento else None,
            'valor': float(comprovante.valor or 0) if comprovante.valor is not None else None,
            'categoria_nome': comprovante.categoria.nome if comprovante.categoria else None,
            'categoria_ir_nome': comprovante.categoria_ir.nome if comprovante.categoria_ir else None,
            'status': comprovante.status,
            'arquivo': comprovante.arquivo.to_dict() if comprovante.arquivo else None,
            'download_url': f'/api/ir/comprovantes/{comprovante.id}/arquivo',
        }

    @classmethod
    def _criar_vinculo_documento(cls, bem, comprovante_id, dados):
        comprovante = cls._obter_comprovante_perfil(comprovante_id, bem.perfil_financeiro_id)
        if not comprovante:
            raise ValueError('Documento fiscal nao encontrado no perfil ativo')
        cls._validar_documento_sem_vinculo_patrimonial(comprovante.id, bem.perfil_financeiro_id, bem.id)

        existentes = IrComprovanteVinculo.query.filter_by(
            perfil_financeiro_id=bem.perfil_financeiro_id,
            tipo_entidade='PATRIMONIO',
            entidade_id=bem.id,
            ativo=True,
        ).all()
        for vinculo in existentes:
            vinculo.ativo = False
            vinculo.updated_at = datetime.utcnow()

        vinculo = IrComprovanteVinculo(
            comprovante_id=comprovante.id,
            perfil_financeiro_id=bem.perfil_financeiro_id,
            tipo_entidade='PATRIMONIO',
            entidade_id=bem.id,
            resumo_entidade=f'{bem.nome} ({bem.codigo or bem.id})',
            tipo_vinculo=cls._normalizar_opcao(dados.get('tipo_vinculo'), cls.TIPOS_VINCULO, 'NOTA_FISCAL'),
            natureza=cls._normalizar_opcao(dados.get('natureza'), cls.NATUREZAS, 'PATRIMONIO_IMOBILIZADO'),
            status_lastro=cls._normalizar_opcao(dados.get('status_lastro'), {'VALIDADO', 'COM_DOCUMENTO', 'PENDENTE'}, 'VALIDADO'),
            observacoes=cls._texto(dados.get('observacoes'), 1000),
            ativo=True,
        )
        db.session.add(vinculo)
        bem.status_documental = 'COM_LASTRO'
        if not bem.fornecedor and comprovante.prestador_nome:
            bem.fornecedor = comprovante.prestador_nome
        if not bem.data_aquisicao and comprovante.data_documento:
            bem.data_aquisicao = comprovante.data_documento
        if not bem.valor_aquisicao and comprovante.valor is not None:
            bem.valor_aquisicao = comprovante.valor
        if not bem.documento_numero:
            bem.documento_numero = f'DOC-{comprovante.id}'
        bem.depreciacao_mensal = cls._calcular_depreciacao(bem.valor_aquisicao, bem.vida_util_meses)
        return vinculo

    @classmethod
    def _validar_documento_sem_vinculo_patrimonial(cls, comprovante_id, perfil_id, bem_id_atual=None):
        vinculo = IrComprovanteVinculo.query.filter_by(
            comprovante_id=comprovante_id,
            perfil_financeiro_id=perfil_id,
            tipo_entidade='PATRIMONIO',
            ativo=True,
        ).first()
        if vinculo and (bem_id_atual is None or int(vinculo.entidade_id or 0) != int(bem_id_atual or 0)):
            raise ValueError('Documento fiscal ja esta vinculado a um bem patrimonial')
        return True

    @classmethod
    def _obter_comprovante_perfil(cls, comprovante_id, perfil_id):
        if not comprovante_id:
            return None
        comprovante = db.session.get(IrComprovante, comprovante_id)
        PerfilFinanceiroService.validar_pertence_ao_perfil(comprovante, perfil_id=perfil_id)
        return comprovante

    @classmethod
    def _documento_do_bem(cls, bem):
        vinculo = IrComprovanteVinculo.query.filter_by(
            perfil_financeiro_id=bem.perfil_financeiro_id,
            tipo_entidade='PATRIMONIO',
            entidade_id=bem.id,
            ativo=True,
        ).order_by(IrComprovanteVinculo.created_at.desc()).first()
        if not vinculo or not vinculo.comprovante:
            return None
        documento = cls.serializar_documento(vinculo.comprovante)
        documento['vinculo'] = vinculo.to_dict()
        documento['tipo_vinculo_label'] = cls._tipo_vinculo_label(vinculo.tipo_vinculo)
        documento['status_lastro'] = vinculo.status_lastro
        documento['natureza'] = vinculo.natureza
        return documento

    @classmethod
    def _composicao_por_categoria(cls, bens, total):
        acumulado = {}
        for bem in bens:
            categoria = bem.categoria or 'Sem categoria'
            acumulado.setdefault(categoria, Decimal('0'))
            acumulado[categoria] += cls._decimal(bem.valor_aquisicao)
        itens = []
        for categoria, valor in sorted(acumulado.items(), key=lambda item: item[1], reverse=True):
            percentual = float((valor / total) * 100) if total else 0
            itens.append({
                'categoria': categoria,
                'valor': float(valor),
                'percentual': round(percentual, 1),
            })
        return itens

    @staticmethod
    def _calcular_depreciacao(valor, vida_util_meses):
        valor_decimal = PatrimonioEmpresarialService._decimal(valor)
        meses = PatrimonioEmpresarialService._parse_int(vida_util_meses)
        if not meses or meses <= 0:
            return None
        return (valor_decimal / Decimal(meses)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    @staticmethod
    def _decimal(valor):
        if valor in {None, ''}:
            return Decimal('0')
        try:
            return Decimal(str(valor)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        except (InvalidOperation, ValueError):
            return Decimal('0')

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
        if isinstance(valor, date):
            return valor
        texto = str(valor or '').strip()
        if not texto:
            return None
        try:
            return datetime.strptime(texto[:10], '%Y-%m-%d').date()
        except ValueError:
            return None

    @staticmethod
    def _texto(valor, limite):
        texto = str(valor or '').strip()
        return texto[:limite] if texto else None

    @staticmethod
    def _normalizar_opcao(valor, permitidos, padrao):
        if valor in {None, ''}:
            return padrao
        texto = str(valor).strip().upper()
        return texto if texto in permitidos else padrao

    @staticmethod
    def _normalizar_status_documento(valor):
        if valor in {None, '', 'TODOS'}:
            return None
        texto = str(valor).strip().upper()
        aliases = {
            'COM_DOCUMENTO': 'COM_LASTRO',
            'VALIDADO': 'COM_LASTRO',
            'SEM_LASTRO': 'SEM_DOCUMENTO',
        }
        texto = aliases.get(texto, texto)
        return texto if texto in PatrimonioEmpresarialService.STATUS_DOCUMENTAL else None

    @staticmethod
    def _normalizar_imagem(valor):
        nome = Path(str(valor or '').strip()).name
        if not nome:
            return None
        if not nome.lower().startswith('patrimonio'):
            return None
        if Path(nome).suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp'}:
            return None
        disponiveis = {imagem['arquivo'] for imagem in PatrimonioEmpresarialService.listar_imagens_disponiveis()}
        return nome if nome in disponiveis else None

    @staticmethod
    def _imagem_url(nome):
        imagem = PatrimonioEmpresarialService._normalizar_imagem(nome)
        return f'/static/img/{imagem}' if imagem else None

    @staticmethod
    def _label_imagem(stem):
        texto = stem.replace('Patrimonio_', '').replace('patrimonio_', '').replace('_', ' ').replace('-', ' ')
        return texto.strip().title() or 'Patrimonio'

    @staticmethod
    def _documento_label(comprovante):
        nome = comprovante.prestador_nome or 'Documento fiscal'
        data_doc = comprovante.data_documento.isoformat() if comprovante.data_documento else 'sem data'
        valor = float(comprovante.valor or 0) if comprovante.valor is not None else 0
        return f'{nome} - {data_doc} - R$ {valor:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')

    @staticmethod
    def _status_label(status):
        return {
            'ATIVO': 'Ativo',
            'INATIVO': 'Inativo',
            'BAIXADO': 'Baixado',
            'EM_REVISAO': 'Em revisao',
        }.get(status, status or '-')

    @staticmethod
    def _status_documental_label(status):
        return {
            'COM_LASTRO': 'Com lastro',
            'SEM_DOCUMENTO': 'Sem documento',
            'PENDENTE': 'Pendente',
            'AGUARDANDO_CONTADOR': 'Aguardando contador',
            'DIVERGENTE': 'Divergente',
            'NAO_APLICAVEL': 'Nao aplicavel',
        }.get(status, status or '-')

    @staticmethod
    def _tipo_vinculo_label(tipo_vinculo):
        return {
            'NOTA_FISCAL': 'NF vinculada',
            'COMPROVANTE': 'Comprovante',
            'RECIBO': 'Recibo',
            'CONTRATO': 'Contrato',
            'DOCUMENTO_CONTABIL': 'Documento contabil',
            'OUTRO': 'Documento',
        }.get(tipo_vinculo, 'Documento')

    @staticmethod
    def _imagem_chave(bem):
        texto = ' '.join([
            str(bem.nome or ''),
            str(bem.categoria or ''),
            str(bem.descricao or ''),
        ]).lower()
        if any(chave in texto for chave in ('notebook', 'laptop', 'computador')):
            return 'notebook'
        if any(chave in texto for chave in ('cadeira', 'ergonomica', 'ergonômica')):
            return 'cadeira'
        if any(chave in texto for chave in ('mesa', 'reuniao', 'reunião', 'movel', 'móvel', 'moveis', 'móveis')):
            return 'moveis'
        if any(chave in texto for chave in ('impressora', 'laser')):
            return 'impressora'
        if any(chave in texto for chave in ('ar-condicionado', 'ar condicionado', 'climatizacao', 'climatização')):
            return 'ar_condicionado'
        if 'monitor' in texto:
            return 'monitor'
        if any(chave in texto for chave in ('webcam', 'camera', 'câmera')):
            return 'webcam'
        if any(chave in texto for chave in ('placa de video', 'placa de vídeo', 'gpu')):
            return 'placa_video'
        return 'equipamento'
