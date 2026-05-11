from datetime import datetime
from pathlib import Path
from uuid import uuid4
import hashlib
import re

from flask import current_app
from werkzeug.utils import secure_filename

try:
    from backend.models import (
        db,
        Financiamento,
        FinanciamentoAjusteSaldo,
        FinanciamentoAmortizacaoExtra,
        FinanciamentoDocumento,
        FinanciamentoParcela,
    )
    from backend.services.perfil_financeiro_service import PerfilFinanceiroService
except ImportError:
    from models import (
        db,
        Financiamento,
        FinanciamentoAjusteSaldo,
        FinanciamentoAmortizacaoExtra,
        FinanciamentoDocumento,
        FinanciamentoParcela,
    )
    from services.perfil_financeiro_service import PerfilFinanceiroService


class FinanciamentoDocumentoService:
    TIPOS_DOCUMENTO = {
        'contrato',
        'demonstrativo_valores_cobrados',
        'demonstrativo_evolucao',
        'boleto',
        'comprovante_pagamento',
        'comprovante_amortizacao',
        'seguro_habitacional',
        'extrato_anual',
        'quitacao',
        'outros',
    }

    EXTENSOES_PERMITIDAS = {'pdf', 'jpg', 'jpeg', 'png', 'webp', 'csv', 'xlsx', 'docx'}
    EXTENSOES_PROIBIDAS = {'exe', 'bat', 'cmd', 'ps1', 'sh', 'js', 'html', 'php', 'py'}
    MIME_POR_EXTENSAO = {
        'pdf': {'application/pdf'},
        'jpg': {'image/jpeg'},
        'jpeg': {'image/jpeg'},
        'png': {'image/png'},
        'webp': {'image/webp'},
        'csv': {'text/csv', 'text/plain', 'application/csv', 'application/vnd.ms-excel'},
        'xlsx': {'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'application/zip'},
        'docx': {'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'application/zip'},
    }
    COMPETENCIA_RE = re.compile(r'^\d{4}-(0[1-9]|1[0-2])$')
    HASH_RE = re.compile(r'^[a-f0-9]{64}$')

    @staticmethod
    def listar_documentos(financiamento_id):
        financiamento = FinanciamentoDocumentoService._obter_financiamento(financiamento_id)
        return financiamento.documentos.order_by(FinanciamentoDocumento.criado_em.desc()).all()

    @staticmethod
    def salvar_documento(financiamento_id, arquivo, dados):
        financiamento = FinanciamentoDocumentoService._obter_financiamento(financiamento_id)
        metadados = FinanciamentoDocumentoService._validar_metadados(dados or {})
        FinanciamentoDocumentoService._validar_vinculos_documento(financiamento.id, metadados)
        conteudo, extensao, mime_type, nome_original = FinanciamentoDocumentoService._validar_arquivo(arquivo)

        nome_armazenado = f'{uuid4().hex}.{extensao}'
        diretorio = FinanciamentoDocumentoService._diretorio_documentos(financiamento.id)
        caminho = (diretorio / nome_armazenado).resolve()
        base_dir = FinanciamentoDocumentoService._diretorio_base().resolve()
        if not FinanciamentoDocumentoService._path_dentro_diretorio(base_dir, caminho):
            raise ValueError('Caminho de arquivo invalido')

        caminho_relativo = Path(str(financiamento.id)) / 'documentos' / nome_armazenado
        hash_arquivo = hashlib.sha256(conteudo).hexdigest()

        documento = FinanciamentoDocumento(
            perfil_financeiro_id=PerfilFinanceiroService.obter_perfil_ativo_id(),
            financiamento_id=financiamento.id,
            tipo_documento=metadados['tipo_documento'],
            competencia=metadados['competencia'],
            ano_base=metadados['ano_base'],
            data_documento=metadados['data_documento'],
            parcela_id=metadados['parcela_id'],
            amortizacao_id=metadados['amortizacao_id'],
            ajuste_saldo_id=metadados['ajuste_saldo_id'],
            nome_original=nome_original,
            nome_armazenado=nome_armazenado,
            mime_type=mime_type,
            tamanho_bytes=len(conteudo),
            hash_arquivo=hash_arquivo,
            caminho_relativo=caminho_relativo.as_posix(),
            observacao=metadados['observacao'],
        )

        try:
            diretorio.mkdir(parents=True, exist_ok=True)
            caminho.write_bytes(conteudo)
            db.session.add(documento)
            db.session.commit()
            return documento
        except Exception:
            db.session.rollback()
            if caminho.is_file():
                try:
                    caminho.unlink()
                except OSError:
                    current_app.logger.warning('Nao foi possivel remover arquivo apos falha no upload: %s', caminho)
            raise

    @staticmethod
    def obter_documento_para_download(financiamento_id, documento_id):
        documento = FinanciamentoDocumentoService._obter_documento(financiamento_id, documento_id)
        caminho = FinanciamentoDocumentoService._resolver_caminho_documento(documento, exigir_existe=True)
        return documento, caminho

    @staticmethod
    def excluir_documento(financiamento_id, documento_id):
        documento = FinanciamentoDocumentoService._obter_documento(financiamento_id, documento_id)
        caminho = None
        aviso = None
        try:
            caminho = FinanciamentoDocumentoService._resolver_caminho_documento(documento, exigir_existe=False)
        except ValueError:
            aviso = 'Metadado removido. O caminho fisico estava invalido.'

        db.session.delete(documento)
        db.session.commit()

        if caminho and caminho.exists():
            try:
                caminho.unlink()
                FinanciamentoDocumentoService._remover_diretorios_vazios(caminho.parent)
            except OSError:
                aviso = 'Metadado removido, mas o arquivo fisico nao pode ser excluido automaticamente.'
        elif caminho:
            aviso = 'Metadado removido. O arquivo fisico ja nao existia.'

        return {'aviso': aviso}

    @staticmethod
    def caminhos_documentos_financiamento(financiamento):
        caminhos = []
        if not financiamento:
            return caminhos
        documentos = financiamento.documentos.all() if hasattr(financiamento.documentos, 'all') else financiamento.documentos
        for documento in documentos:
            try:
                caminhos.append(FinanciamentoDocumentoService._resolver_caminho_documento(documento, exigir_existe=False))
            except ValueError:
                continue
        return caminhos

    @staticmethod
    def remover_arquivos_por_caminhos(caminhos):
        for caminho in caminhos or []:
            try:
                if caminho.is_file():
                    caminho.unlink()
                    FinanciamentoDocumentoService._remover_diretorios_vazios(caminho.parent)
            except OSError:
                current_app.logger.warning('Nao foi possivel remover documento de financiamento: %s', caminho)

    @staticmethod
    def _obter_financiamento(financiamento_id):
        financiamento = PerfilFinanceiroService.aplicar_perfil_query(
            Financiamento.query,
            Financiamento,
        ).filter(Financiamento.id == financiamento_id).first()
        if not financiamento:
            raise ValueError('Financiamento nao encontrado')
        return financiamento

    @staticmethod
    def _obter_documento(financiamento_id, documento_id):
        financiamento = FinanciamentoDocumentoService._obter_financiamento(financiamento_id)
        documento = FinanciamentoDocumento.query.filter_by(
            id=documento_id,
            financiamento_id=financiamento.id,
        ).first()
        if not documento:
            raise ValueError('Documento nao encontrado')
        PerfilFinanceiroService.validar_pertence_ao_perfil(documento)
        return documento

    @staticmethod
    def _validar_metadados(dados):
        tipo = str(dados.get('tipo_documento') or '').strip()
        if tipo not in FinanciamentoDocumentoService.TIPOS_DOCUMENTO:
            raise ValueError('Tipo de documento invalido')

        competencia = str(dados.get('competencia') or '').strip() or None
        if competencia and not FinanciamentoDocumentoService.COMPETENCIA_RE.match(competencia):
            raise ValueError('Competencia deve estar no formato YYYY-MM')

        ano_base = str(dados.get('ano_base') or '').strip()
        if ano_base:
            try:
                ano_base = int(ano_base)
            except ValueError as exc:
                raise ValueError('ano_base deve ser numerico') from exc
            if ano_base < 1900 or ano_base > 2200:
                raise ValueError('ano_base deve estar entre 1900 e 2200')
        else:
            ano_base = None

        data_documento = str(dados.get('data_documento') or '').strip()
        if data_documento:
            try:
                data_documento = datetime.strptime(data_documento, '%Y-%m-%d').date()
            except ValueError as exc:
                raise ValueError('data_documento deve estar no formato YYYY-MM-DD') from exc
        else:
            data_documento = None

        observacao = str(dados.get('observacao') or '').strip() or None
        if observacao and len(observacao) > 2000:
            raise ValueError('Observacao deve ter no maximo 2000 caracteres')

        parcela_id = FinanciamentoDocumentoService._inteiro_opcional(dados.get('parcela_id'), 'parcela_id')
        amortizacao_id = FinanciamentoDocumentoService._inteiro_opcional(dados.get('amortizacao_id'), 'amortizacao_id')
        ajuste_saldo_id = FinanciamentoDocumentoService._inteiro_opcional(dados.get('ajuste_saldo_id'), 'ajuste_saldo_id')

        return {
            'tipo_documento': tipo,
            'competencia': competencia,
            'ano_base': ano_base,
            'data_documento': data_documento,
            'parcela_id': parcela_id,
            'amortizacao_id': amortizacao_id,
            'ajuste_saldo_id': ajuste_saldo_id,
            'observacao': observacao,
        }

    @staticmethod
    def _inteiro_opcional(valor, campo):
        if valor is None:
            return None
        texto = str(valor).strip()
        if not texto:
            return None
        try:
            numero = int(texto)
        except ValueError as exc:
            raise ValueError(f'{campo} deve ser numerico') from exc
        if numero <= 0:
            raise ValueError(f'{campo} deve ser positivo')
        return numero

    @staticmethod
    def _validar_vinculos_documento(financiamento_id, metadados):
        parcela_id = metadados.get('parcela_id')
        if parcela_id and not FinanciamentoParcela.query.filter_by(
            id=parcela_id,
            financiamento_id=financiamento_id,
        ).first():
            raise ValueError('Parcela vinculada nao encontrada para este financiamento')

        amortizacao_id = metadados.get('amortizacao_id')
        if amortizacao_id and not FinanciamentoAmortizacaoExtra.query.filter_by(
            id=amortizacao_id,
            financiamento_id=financiamento_id,
        ).first():
            raise ValueError('Amortizacao vinculada nao encontrada para este financiamento')

        ajuste_saldo_id = metadados.get('ajuste_saldo_id')
        if ajuste_saldo_id and not FinanciamentoAjusteSaldo.query.filter_by(
            id=ajuste_saldo_id,
            financiamento_id=financiamento_id,
        ).first():
            raise ValueError('Ajuste de saldo vinculado nao encontrado para este financiamento')

    @staticmethod
    def _validar_arquivo(arquivo):
        if not arquivo:
            raise ValueError('Arquivo nao fornecido')
        if not arquivo.filename:
            raise ValueError('Nome de arquivo vazio')

        nome_bruto = str(arquivo.filename)
        FinanciamentoDocumentoService._validar_nome_sem_traversal(nome_bruto)
        extensao = FinanciamentoDocumentoService._extensao(nome_bruto)

        if extensao in FinanciamentoDocumentoService.EXTENSOES_PROIBIDAS:
            raise ValueError('Formato de arquivo nao permitido')
        if extensao not in FinanciamentoDocumentoService.EXTENSOES_PERMITIDAS:
            raise ValueError('Formato de arquivo nao permitido')

        limite = FinanciamentoDocumentoService._tamanho_maximo()
        conteudo = arquivo.stream.read(limite + 1)
        arquivo.stream.seek(0)
        if not conteudo:
            raise ValueError('Arquivo vazio')
        if len(conteudo) > limite:
            raise ValueError('Arquivo excede o tamanho maximo permitido')

        mime_type = (arquivo.mimetype or '').lower()
        if mime_type and mime_type != 'application/octet-stream':
            esperados = FinanciamentoDocumentoService.MIME_POR_EXTENSAO.get(extensao, set())
            if esperados and mime_type not in esperados:
                raise ValueError('Tipo MIME invalido para o arquivo enviado')

        if not FinanciamentoDocumentoService._assinatura_valida(conteudo, extensao):
            raise ValueError('Assinatura do arquivo invalida')

        nome_original = secure_filename(Path(nome_bruto).name)[:255]
        if not nome_original:
            raise ValueError('Nome de arquivo invalido')
        return conteudo, extensao, mime_type or FinanciamentoDocumentoService._mime_padrao(extensao), nome_original

    @staticmethod
    def _validar_nome_sem_traversal(nome):
        normalizado = nome.replace('\\', '/')
        if Path(normalizado).is_absolute():
            raise ValueError('Nome de arquivo invalido')
        partes = [parte for parte in normalizado.split('/') if parte]
        if len(partes) != 1 or any(parte == '..' for parte in partes):
            raise ValueError('Nome de arquivo invalido')

    @staticmethod
    def _extensao(nome_arquivo):
        nome = nome_arquivo or ''
        if '.' not in nome:
            return ''
        return nome.rsplit('.', 1)[1].lower()

    @staticmethod
    def _mime_padrao(extensao):
        return {
            'pdf': 'application/pdf',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'png': 'image/png',
            'webp': 'image/webp',
            'csv': 'text/csv',
            'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        }.get(extensao, 'application/octet-stream')

    @staticmethod
    def _assinatura_valida(conteudo, extensao):
        if extensao == 'pdf':
            return conteudo.startswith(b'%PDF')
        if extensao in {'jpg', 'jpeg'}:
            return conteudo.startswith(b'\xff\xd8')
        if extensao == 'png':
            return conteudo.startswith(b'\x89PNG\r\n\x1a\n')
        if extensao == 'webp':
            return len(conteudo) >= 12 and conteudo[:4] == b'RIFF' and conteudo[8:12] == b'WEBP'
        if extensao in {'xlsx', 'docx'}:
            return conteudo.startswith((b'PK\x03\x04', b'PK\x05\x06', b'PK\x07\x08'))
        if extensao == 'csv':
            return b'\x00' not in conteudo
        return False

    @staticmethod
    def _diretorio_base():
        configurado = current_app.config.get('FINANCIAMENTO_DOCUMENTOS_DIR')
        if configurado:
            return Path(configurado).resolve()
        return (Path(__file__).resolve().parents[2] / 'data' / 'uploads' / 'financiamentos').resolve()

    @staticmethod
    def _diretorio_documentos(financiamento_id):
        return (FinanciamentoDocumentoService._diretorio_base() / str(financiamento_id) / 'documentos').resolve()

    @staticmethod
    def _resolver_caminho_documento(documento, exigir_existe=True):
        base_dir = FinanciamentoDocumentoService._diretorio_base().resolve()
        relativo = Path(str(documento.caminho_relativo or ''))
        if relativo.is_absolute() or '..' in relativo.parts:
            raise ValueError('Caminho de arquivo invalido')
        caminho = (base_dir / relativo).resolve()
        if not FinanciamentoDocumentoService._path_dentro_diretorio(base_dir, caminho):
            raise ValueError('Caminho de arquivo invalido')
        if exigir_existe and not caminho.is_file():
            raise ValueError('Arquivo fisico do documento nao encontrado')
        return caminho

    @staticmethod
    def _path_dentro_diretorio(base_dir, caminho):
        try:
            caminho.resolve().relative_to(base_dir.resolve())
            return True
        except ValueError:
            return False

    @staticmethod
    def _tamanho_maximo():
        return int(current_app.config.get('MAX_FINANCIAMENTO_DOCUMENTO_SIZE', 10 * 1024 * 1024))

    @staticmethod
    def _remover_diretorios_vazios(diretorio):
        base_dir = FinanciamentoDocumentoService._diretorio_base().resolve()
        atual = diretorio.resolve()
        while atual != base_dir and FinanciamentoDocumentoService._path_dentro_diretorio(base_dir, atual):
            try:
                atual.rmdir()
            except OSError:
                break
            atual = atual.parent
