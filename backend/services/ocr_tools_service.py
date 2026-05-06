from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import current_app


EXEMPLO_TESSERACT_WINDOWS = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
EXEMPLO_POPPLER_WINDOWS = r'C:\Program Files\poppler\Library\bin'


class OcrToolsService:
    @classmethod
    def carregar_config_ocr(cls) -> dict[str, Any]:
        padrao = {
            'tesseract_path': '',
            'poppler_path': '',
            'ultima_validacao': None,
            'status_ferramentas': {},
            'idiomas': [],
            'configuracao_manual': False,
        }
        dados = cls._read_json(cls._config_file(), {})
        if isinstance(dados, dict):
            padrao.update({chave: dados.get(chave, padrao[chave]) for chave in padrao})
        return padrao

    @classmethod
    def salvar_config_ocr(cls, config: dict[str, Any]) -> dict[str, Any]:
        atual = cls.carregar_config_ocr()
        atual.update(config or {})
        cls._write_json(cls._config_file(), atual)
        return atual

    @classmethod
    def autodetectar_tesseract(cls) -> str | None:
        candidatos = []
        if current_app.config.get('OCR_TESSERACT_SEARCH_ROOTS') is None:
            candidatos.extend([
                Path(r'C:\Program Files\Tesseract-OCR\tesseract.exe'),
                Path(r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe'),
            ])
        for root in cls._tesseract_search_roots():
            try:
                candidatos.append(Path(root) / 'Tesseract-OCR' / 'tesseract.exe')
                candidatos.append(Path(root) / 'tesseract.exe')
            except (OSError, ValueError):
                continue
        vistos = set()
        for candidato in candidatos:
            texto = str(candidato)
            chave = texto.lower()
            if chave in vistos:
                continue
            vistos.add(chave)
            if candidato.is_file():
                return texto
        return None

    @classmethod
    def validar_tesseract(cls, path: str | None = None, config: dict[str, Any] | None = None) -> dict[str, Any]:
        resolucao = cls._resolver_tesseract(path=path, config=config)
        info = {
            'disponivel': False,
            'caminho': resolucao.get('caminho'),
            'origem': resolucao.get('origem'),
            'versao': None,
            'idiomas': [],
            'por_disponivel': False,
            'eng_disponivel': False,
            'mensagem': resolucao.get('mensagem') or '',
        }
        caminho = resolucao.get('caminho')
        if not caminho:
            info['mensagem'] = 'Tesseract nao encontrado. Configure o caminho em Configuracoes > IA e Automacao.'
            return info

        try:
            versao = cls._run_tool([caminho, '--version'])
            langs = cls._run_tool([caminho, '--list-langs'])
        except Exception as exc:
            info['mensagem'] = cls._sanitize_message(str(exc))
            return info

        if versao['returncode'] != 0:
            info['mensagem'] = cls._sanitize_message(versao['output'] or 'Falha ao validar Tesseract.')
            return info
        if langs['returncode'] != 0:
            info['mensagem'] = cls._sanitize_message(langs['output'] or 'Falha ao listar idiomas do Tesseract.')
            return info

        idiomas = cls._parse_langs(langs['output'])
        info.update({
            'disponivel': True,
            'versao': cls._primeira_linha(versao['output']),
            'idiomas': idiomas,
            'por_disponivel': 'por' in idiomas,
            'eng_disponivel': 'eng' in idiomas,
        })
        if not info['por_disponivel']:
            info['mensagem'] = (
                'Tesseract encontrado, mas o idioma portugues nao esta instalado. '
                'O OCR pode funcionar, mas tera menor precisao em documentos brasileiros.'
            )
        else:
            info['mensagem'] = 'Tesseract disponivel.'
        return info

    @classmethod
    def autodetectar_poppler(cls) -> str | None:
        candidatos = []
        for root in cls._poppler_search_roots():
            base = Path(root)
            try:
                if base.is_dir():
                    candidatos.extend([base, base / 'bin', base / 'Library' / 'bin'])
                    for child in base.glob('poppler*'):
                        candidatos.extend([child, child / 'bin', child / 'Library' / 'bin'])
            except (OSError, ValueError):
                continue
        for candidato in candidatos:
            resolvido = cls._poppler_bin_dir(candidato)
            if resolvido:
                return str(resolvido)
        return None

    @classmethod
    def validar_poppler(cls, path: str | None = None, config: dict[str, Any] | None = None) -> dict[str, Any]:
        resolucao = cls._resolver_poppler(path=path, config=config)
        info = {
            'disponivel': False,
            'caminho': resolucao.get('caminho'),
            'origem': resolucao.get('origem'),
            'pdftoppm_path': resolucao.get('pdftoppm_path'),
            'pdfinfo_path': resolucao.get('pdfinfo_path'),
            'versao': None,
            'mensagem': resolucao.get('mensagem') or '',
        }
        pdftoppm = resolucao.get('pdftoppm_path')
        pdfinfo = resolucao.get('pdfinfo_path')
        if not pdftoppm or not pdfinfo:
            info['mensagem'] = 'Poppler nao encontrado. PDFs escaneados exigirao conversao de paginas em etapa futura.'
            return info

        try:
            ppm = cls._run_tool([pdftoppm, '-v'])
            pinfo = cls._run_tool([pdfinfo, '-v'])
        except Exception as exc:
            info['mensagem'] = cls._sanitize_message(str(exc))
            return info

        if ppm['returncode'] != 0 or pinfo['returncode'] != 0:
            info['mensagem'] = cls._sanitize_message(ppm['output'] or pinfo['output'] or 'Falha ao validar Poppler.')
            return info

        info.update({
            'disponivel': True,
            'versao': cls._primeira_linha(ppm['output']) or cls._primeira_linha(pinfo['output']),
            'mensagem': 'Poppler disponivel.',
        })
        return info

    @classmethod
    def obter_status_ocr(cls, salvar: bool = False) -> dict[str, Any]:
        config = cls.carregar_config_ocr()
        tesseract = cls.validar_tesseract(config=config)
        poppler = cls.validar_poppler(config=config)
        idiomas = tesseract.get('idiomas') or []
        pronto_imagens = bool(tesseract.get('disponivel') and (tesseract.get('por_disponivel') or tesseract.get('eng_disponivel')))
        pronto_pdf = bool(pronto_imagens and poppler.get('disponivel'))
        recomendacoes = cls._recomendacoes(tesseract, poppler)
        payload = {
            'success': True,
            'configuracao': cls._config_publica(config),
            'tesseract': tesseract,
            'poppler': poppler,
            'idiomas': idiomas,
            'pronto_para_imagens': pronto_imagens,
            'pronto_para_pdf_escaneado': pronto_pdf,
            'recomendacoes': recomendacoes,
        }
        if salvar:
            cls._salvar_resultado_validacao(config, tesseract, poppler)
            payload['configuracao'] = cls._config_publica(cls.carregar_config_ocr())
        return payload

    @classmethod
    def configurar_ferramentas_ocr(cls, payload: dict[str, Any] | None) -> dict[str, Any]:
        payload = payload or {}
        tesseract_path = cls._validar_caminho_recebido(payload.get('tesseract_path'), 'tesseract_path')
        poppler_path = cls._validar_caminho_recebido(payload.get('poppler_path'), 'poppler_path')
        config = cls.carregar_config_ocr()
        config.update({
            'tesseract_path': tesseract_path,
            'poppler_path': poppler_path,
            'configuracao_manual': True,
        })
        cls.salvar_config_ocr(config)
        return cls.obter_status_ocr(salvar=True)

    @classmethod
    def autodetectar_ferramentas_ocr(cls) -> dict[str, Any]:
        tesseract = cls.autodetectar_tesseract()
        poppler = cls.autodetectar_poppler()
        config = cls.carregar_config_ocr()
        if tesseract:
            config['tesseract_path'] = tesseract
        if poppler:
            config['poppler_path'] = poppler
        config['configuracao_manual'] = False
        cls.salvar_config_ocr(config)
        resultado = cls.obter_status_ocr(salvar=True)
        resultado['encontrados'] = {
            'tesseract_path': tesseract,
            'poppler_path': poppler,
        }
        resultado['mensagem'] = 'Autodeteccao concluida.'
        return resultado

    @classmethod
    def validar_ferramentas_ocr(cls) -> dict[str, Any]:
        return cls.obter_status_ocr(salvar=True)

    @classmethod
    def _resolver_tesseract(cls, path: str | None = None, config: dict[str, Any] | None = None) -> dict[str, Any]:
        config = config or cls.carregar_config_ocr()
        candidatos = [
            ('informado', path),
            ('configurado', config.get('tesseract_path')),
            ('variavel_ambiente', os.getenv('TESSERACT_PATH')),
            ('path', shutil.which('tesseract')),
            ('autodetectado', cls.autodetectar_tesseract()),
        ]
        for origem, candidato in candidatos:
            caminho = str(candidato or '').strip()
            if not caminho:
                continue
            if cls._caminho_tesseract(caminho):
                return {'caminho': caminho, 'origem': origem, 'mensagem': 'Tesseract localizado.'}
        return {'caminho': None, 'origem': None, 'mensagem': 'Tesseract nao encontrado.'}

    @classmethod
    def _resolver_poppler(cls, path: str | None = None, config: dict[str, Any] | None = None) -> dict[str, Any]:
        config = config or cls.carregar_config_ocr()
        path_pair = cls._poppler_from_path()
        candidatos = [
            ('informado', path),
            ('configurado', config.get('poppler_path')),
            ('variavel_ambiente', os.getenv('POPPLER_PATH')),
            ('path', path_pair.get('caminho')),
            ('autodetectado', cls.autodetectar_poppler()),
        ]
        for origem, candidato in candidatos:
            caminho = str(candidato or '').strip()
            if not caminho:
                continue
            resolvido = cls._poppler_bin_dir(caminho)
            if resolvido:
                return {
                    'caminho': str(resolvido),
                    'origem': origem,
                    'pdftoppm_path': str(resolvido / cls._exe('pdftoppm')),
                    'pdfinfo_path': str(resolvido / cls._exe('pdfinfo')),
                    'mensagem': 'Poppler localizado.',
                }
        if path_pair.get('pdftoppm_path') and path_pair.get('pdfinfo_path'):
            return {**path_pair, 'origem': 'path', 'mensagem': 'Poppler localizado.'}
        return {'caminho': None, 'origem': None, 'mensagem': 'Poppler nao encontrado.'}

    @staticmethod
    def _run_tool(comando: list[str]) -> dict[str, Any]:
        resultado = subprocess.run(
            comando,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return {
            'returncode': resultado.returncode,
            'output': (resultado.stdout or resultado.stderr or '').strip(),
        }

    @staticmethod
    def _parse_langs(output: str) -> list[str]:
        idiomas = []
        for linha in str(output or '').splitlines():
            valor = linha.strip()
            if not valor or valor.lower().startswith('list of available'):
                continue
            if re.fullmatch(r'[A-Za-z0-9_+-]+', valor):
                idiomas.append(valor)
        return sorted(set(idiomas))

    @classmethod
    def _salvar_resultado_validacao(cls, config, tesseract, poppler):
        config = dict(config or {})
        config['ultima_validacao'] = cls._now_iso()
        config['idiomas'] = tesseract.get('idiomas') or []
        config['status_ferramentas'] = {
            'tesseract': tesseract,
            'poppler': poppler,
        }
        cls.salvar_config_ocr(config)

    @staticmethod
    def _recomendacoes(tesseract, poppler):
        recomendacoes = []
        if not tesseract.get('disponivel'):
            recomendacoes.append(f'Configure o caminho do Tesseract. Exemplo: {EXEMPLO_TESSERACT_WINDOWS}')
        elif not tesseract.get('por_disponivel'):
            recomendacoes.append('Instale o idioma portugues por.traineddata para melhorar documentos brasileiros.')
        if not poppler.get('disponivel'):
            recomendacoes.append('Configure o Poppler para preparar OCR de PDFs escaneados.')
        if not recomendacoes:
            recomendacoes.append('Ferramentas OCR configuradas.')
        return recomendacoes

    @staticmethod
    def _config_publica(config):
        return {
            'tesseract_path': str(config.get('tesseract_path') or ''),
            'poppler_path': str(config.get('poppler_path') or ''),
            'ultima_validacao': config.get('ultima_validacao'),
            'status_ferramentas': config.get('status_ferramentas') or {},
            'idiomas': config.get('idiomas') or [],
            'configuracao_manual': bool(config.get('configuracao_manual')),
        }

    @classmethod
    def _caminho_tesseract(cls, caminho: str) -> bool:
        try:
            path = Path(caminho)
            if path.is_file() and path.name.lower() in {'tesseract.exe', 'tesseract'}:
                return True
        except (OSError, ValueError):
            return False
        achado = shutil.which(caminho)
        return bool(achado and Path(achado).name.lower() in {'tesseract.exe', 'tesseract'})

    @classmethod
    def _poppler_bin_dir(cls, caminho: str | Path | None) -> Path | None:
        if not caminho:
            return None
        try:
            base = Path(caminho)
        except (OSError, ValueError):
            return None
        candidatos = [base, base / 'bin', base / 'Library' / 'bin']
        if base.is_file():
            candidatos.insert(0, base.parent)
        for candidato in candidatos:
            if (candidato / cls._exe('pdftoppm')).is_file() and (candidato / cls._exe('pdfinfo')).is_file():
                return candidato
        return None

    @classmethod
    def _poppler_from_path(cls) -> dict[str, Any]:
        pdftoppm = shutil.which('pdftoppm')
        pdfinfo = shutil.which('pdfinfo')
        if not pdftoppm or not pdfinfo:
            return {}
        try:
            path_dir = Path(pdftoppm).parent
        except (OSError, ValueError):
            path_dir = None
        return {
            'caminho': str(path_dir) if path_dir else None,
            'pdftoppm_path': pdftoppm,
            'pdfinfo_path': pdfinfo,
        }

    @staticmethod
    def _validar_caminho_recebido(valor, campo):
        texto = str(valor or '').strip()
        if not texto:
            return ''
        proibidos = ['\n', '\r', '\x00', ';', '|', '`']
        if any(item in texto for item in proibidos):
            raise ValueError(f'Caminho invalido em {campo}')
        partes = texto.replace('\\', '/').split('/')
        if '..' in partes:
            raise ValueError(f'Caminho invalido em {campo}')
        return texto[:500]

    @staticmethod
    def _sanitize_message(message):
        texto = str(message or '').strip()
        return texto[:500]

    @staticmethod
    def _primeira_linha(output):
        for linha in str(output or '').splitlines():
            texto = linha.strip()
            if texto:
                return texto[:200]
        return None

    @staticmethod
    def _exe(nome):
        return f'{nome}.exe' if os.name == 'nt' else nome

    @staticmethod
    def _now_iso():
        return datetime.now().isoformat(timespec='seconds')

    @staticmethod
    def _base_dir() -> Path:
        configurado = current_app.config.get('OCR_BASE_DIR')
        if configurado:
            return Path(configurado)
        return Path(__file__).resolve().parents[2] / 'data' / 'ocr'

    @classmethod
    def _config_file(cls) -> Path:
        return cls._base_dir() / 'ocr_config.json'

    @staticmethod
    def _tesseract_search_roots() -> list[Path]:
        configurado = current_app.config.get('OCR_TESSERACT_SEARCH_ROOTS')
        if configurado is not None:
            return [Path(item) for item in configurado]
        roots = []
        for env_name in ['ProgramFiles', 'ProgramFiles(x86)']:
            base = os.environ.get(env_name)
            if base:
                roots.append(Path(base))
        roots.extend([Path(r'C:\Program Files'), Path(r'C:\Program Files (x86)')])
        return cls_unique_paths(roots)

    @staticmethod
    def _poppler_search_roots() -> list[Path]:
        configurado = current_app.config.get('OCR_POPPLER_SEARCH_ROOTS')
        if configurado is not None:
            return [Path(item) for item in configurado]
        roots = []
        for env_name in ['ProgramFiles', 'ProgramFiles(x86)']:
            base = os.environ.get(env_name)
            if base:
                roots.append(Path(base))
        roots.extend([Path(r'C:\Program Files'), Path(r'C:\Program Files (x86)'), Path('C:/')])
        return cls_unique_paths(roots)

    @staticmethod
    def _read_json(caminho: Path, default: Any) -> Any:
        try:
            if not caminho.exists():
                return default
            return json.loads(caminho.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            return default

    @staticmethod
    def _write_json(caminho: Path, dados: Any) -> None:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        temporario = caminho.with_suffix(f'{caminho.suffix}.tmp')
        temporario.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding='utf-8')
        temporario.replace(caminho)


def cls_unique_paths(paths):
    unicos = []
    vistos = set()
    for path in paths:
        texto = str(path).lower()
        if texto in vistos:
            continue
        vistos.add(texto)
        unicos.append(path)
    return unicos
