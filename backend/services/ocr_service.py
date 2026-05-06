from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

try:
    from backend.services.ocr_tools_service import OcrToolsService
except ImportError:
    from services.ocr_tools_service import OcrToolsService


class OcrService:
    MAX_PAGINAS_OCR = 3
    OCR_DPI = 200
    TIMEOUT_POR_PAGINA = 15
    TIMEOUT_CONVERSAO_PDF = 30
    EXTENSOES_IMAGEM = {
        'image/png': '.png',
        'image/jpeg': '.jpg',
        'image/webp': '.webp',
    }

    @classmethod
    def ocr_disponivel(cls) -> dict[str, Any]:
        status = OcrToolsService.obter_status_ocr()
        tesseract = status.get('tesseract') or {}
        poppler = status.get('poppler') or {}
        return {
            'imagem_disponivel': bool(status.get('pronto_para_imagens')),
            'pdf_escaneado_disponivel': bool(status.get('pronto_para_pdf_escaneado')),
            'tesseract': tesseract,
            'poppler': poppler,
            'idiomas': status.get('idiomas') or [],
            'mensagens': status.get('recomendacoes') or [],
        }

    @classmethod
    def executar_ocr_documento(cls, arquivo_bytes: bytes, mime_type: str, filename: str | None = None) -> dict[str, Any]:
        if mime_type == 'application/pdf':
            return cls.extrair_texto_pdf_escaneado(arquivo_bytes, max_paginas=cls.MAX_PAGINAS_OCR)
        if mime_type in cls.EXTENSOES_IMAGEM:
            return cls.extrair_texto_imagem(arquivo_bytes, nome_arquivo=filename, mime_type=mime_type)
        return cls._erro('Tipo de arquivo sem suporte para OCR local.')

    @classmethod
    def extrair_texto_imagem(
        cls,
        imagem_bytes: bytes | str | Path,
        nome_arquivo: str | None = None,
        mime_type: str | None = None,
    ) -> dict[str, Any]:
        status = cls.ocr_disponivel()
        if not status.get('imagem_disponivel'):
            return cls._erro('OCR local nao configurado. Configure em Configuracoes > IA e Automacao.')

        tesseract_path = status.get('tesseract', {}).get('caminho')
        idioma = cls._idioma_preferencial(status.get('idiomas') or [])
        if not tesseract_path:
            return cls._erro('Tesseract nao encontrado para OCR local.')

        try:
            if isinstance(imagem_bytes, (str, Path)):
                resultado = cls._executar_tesseract(tesseract_path, Path(imagem_bytes), idioma)
            else:
                sufixo = cls._suffix_imagem(nome_arquivo, mime_type)
                with tempfile.NamedTemporaryFile(suffix=sufixo, delete=False) as temp:
                    temp.write(imagem_bytes)
                    caminho_temp = Path(temp.name)
                try:
                    resultado = cls._executar_tesseract(tesseract_path, caminho_temp, idioma)
                finally:
                    caminho_temp.unlink(missing_ok=True)
        except Exception:
            return cls._erro('Falha controlada ao executar OCR local na imagem.')

        if resultado['returncode'] != 0:
            return cls._erro('Falha controlada ao executar OCR local na imagem.')

        texto = cls.normalizar_texto_ocr(resultado.get('output') or '')
        return {
            'sucesso': bool(texto),
            'texto': texto,
            'origem': 'ocr',
            'paginas_processadas': 1,
            'avisos': [],
            'erro': None if texto else 'OCR nao retornou texto suficiente.',
        }

    @classmethod
    def converter_pdf_para_imagens(cls, pdf_bytes: bytes, max_paginas: int = MAX_PAGINAS_OCR) -> dict[str, Any]:
        status = cls.ocr_disponivel()
        if not status.get('pdf_escaneado_disponivel'):
            return {
                'sucesso': False,
                'imagens': [],
                'paginas_total': None,
                'avisos': [],
                'erro': 'Poppler nao encontrado. Configure o Poppler para OCR de PDF escaneado.',
            }

        poppler = status.get('poppler') or {}
        pdftoppm = poppler.get('pdftoppm_path')
        pdfinfo = poppler.get('pdfinfo_path')
        if not pdftoppm or not pdfinfo:
            return {
                'sucesso': False,
                'imagens': [],
                'paginas_total': None,
                'avisos': [],
                'erro': 'Poppler nao encontrado. Configure o Poppler para OCR de PDF escaneado.',
            }

        tempdir = tempfile.TemporaryDirectory()
        base = Path(tempdir.name)
        pdf_path = base / 'documento.pdf'
        pdf_path.write_bytes(pdf_bytes)
        paginas_total = cls._contar_paginas_pdf(pdfinfo, pdf_path)
        paginas_processar = min(max_paginas, paginas_total or max_paginas)
        avisos = []
        if paginas_total and paginas_total > max_paginas:
            avisos.append('OCR limitado as 3 primeiras paginas do documento.')

        prefixo = base / 'pagina'
        comando = [
            pdftoppm,
            '-f',
            '1',
            '-l',
            str(paginas_processar),
            '-r',
            str(cls.OCR_DPI),
            '-png',
            str(pdf_path),
            str(prefixo),
        ]
        try:
            resultado = subprocess.run(
                comando,
                capture_output=True,
                text=True,
                timeout=cls.TIMEOUT_CONVERSAO_PDF,
                check=False,
            )
        except Exception:
            tempdir.cleanup()
            return {
                'sucesso': False,
                'imagens': [],
                'paginas_total': paginas_total,
                'avisos': avisos,
                'erro': 'Falha controlada ao converter PDF para imagens.',
            }
        if resultado.returncode != 0:
            tempdir.cleanup()
            return {
                'sucesso': False,
                'imagens': [],
                'paginas_total': paginas_total,
                'avisos': avisos,
                'erro': 'Falha controlada ao converter PDF para imagens.',
            }

        imagens = [imagem.read_bytes() for imagem in sorted(base.glob('pagina*.png'))[:max_paginas]]
        tempdir.cleanup()
        return {
            'sucesso': bool(imagens),
            'imagens': imagens,
            'paginas_total': paginas_total,
            'avisos': avisos,
            'erro': None if imagens else 'PDF convertido sem paginas de imagem.',
        }

    @classmethod
    def extrair_texto_pdf_escaneado(cls, pdf_bytes: bytes, max_paginas: int = MAX_PAGINAS_OCR) -> dict[str, Any]:
        conversao = cls.converter_pdf_para_imagens(pdf_bytes, max_paginas=max_paginas)
        if not conversao.get('sucesso'):
            return cls._erro(conversao.get('erro') or 'PDF escaneado nao pode ser convertido para OCR.')

        textos = []
        avisos = list(conversao.get('avisos') or [])
        for idx, imagem in enumerate(conversao.get('imagens') or [], start=1):
            resultado = cls.extrair_texto_imagem(imagem, nome_arquivo=f'pagina-{idx}.png', mime_type='image/png')
            if resultado.get('sucesso') and resultado.get('texto'):
                textos.append(resultado.get('texto'))
            elif resultado.get('erro'):
                avisos.append(resultado.get('erro'))

        texto = cls.normalizar_texto_ocr('\n\n'.join(textos))
        return {
            'sucesso': bool(texto),
            'texto': texto,
            'origem': 'ocr',
            'paginas_processadas': min(len(conversao.get('imagens') or []), max_paginas),
            'paginas_total': conversao.get('paginas_total'),
            'avisos': avisos,
            'erro': None if texto else 'OCR nao retornou texto suficiente.',
        }

    @staticmethod
    def normalizar_texto_ocr(texto: str) -> str:
        texto = str(texto or '').replace('\x00', '')
        texto = texto.replace('\r\n', '\n').replace('\r', '\n')
        linhas = []
        for linha in texto.splitlines():
            linhas.append(re.sub(r'[ \t]+', ' ', linha).strip())
        texto = '\n'.join(linha for linha in linhas if linha)
        return re.sub(r'\n{3,}', '\n\n', texto).strip()

    @classmethod
    def _executar_tesseract(cls, tesseract_path: str, caminho_imagem: Path, idioma: str) -> dict[str, Any]:
        comando = [tesseract_path, str(caminho_imagem), 'stdout', '-l', idioma]
        resultado = subprocess.run(
            comando,
            capture_output=True,
            text=True,
            timeout=cls.TIMEOUT_POR_PAGINA,
            check=False,
        )
        return {
            'returncode': resultado.returncode,
            'output': resultado.stdout or '',
        }

    @staticmethod
    def _contar_paginas_pdf(pdfinfo_path: str, pdf_path: Path) -> int | None:
        try:
            resultado = subprocess.run(
                [pdfinfo_path, str(pdf_path)],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except Exception:
            return None
        if resultado.returncode != 0:
            return None
        match = re.search(r'^Pages:\s*(\d+)\s*$', resultado.stdout or resultado.stderr or '', re.MULTILINE)
        return int(match.group(1)) if match else None

    @staticmethod
    def _idioma_preferencial(idiomas: list[str]) -> str:
        disponiveis = set(idiomas or [])
        if {'por', 'eng'}.issubset(disponiveis):
            return 'por+eng'
        if 'por' in disponiveis:
            return 'por'
        return 'eng'

    @classmethod
    def _suffix_imagem(cls, nome_arquivo: str | None, mime_type: str | None) -> str:
        if nome_arquivo and '.' in nome_arquivo:
            ext = os.path.splitext(nome_arquivo)[1].lower()
            if ext in {'.png', '.jpg', '.jpeg', '.webp'}:
                return ext
        return cls.EXTENSOES_IMAGEM.get(mime_type or '', '.png')

    @staticmethod
    def _erro(mensagem: str) -> dict[str, Any]:
        return {
            'sucesso': False,
            'texto': '',
            'origem': 'ocr',
            'paginas_processadas': 0,
            'avisos': [],
            'erro': mensagem,
        }
