"""
Serviço local de backup e restauração do PostgreSQL.

O histórico fica fora do banco para sobreviver a operações de restore.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from flask import current_app


CONFIRMACAO_RESTORE = 'CONFIRMO RESTAURACAO'


class BackupService:
    @staticmethod
    def executar_backup_manual() -> dict[str, Any]:
        BackupService._ensure_dirs()
        banco = BackupService._database_config()
        arquivo = BackupService._backup_filename()
        destino = BackupService._postgres_dir() / arquivo

        if not banco['is_postgres']:
            return BackupService._registrar_historico({
                'tipo': 'manual',
                'arquivo': None,
                'caminho': None,
                'tamanho_bytes': 0,
                'status': 'erro',
                'mensagem': 'Backup local disponível apenas para PostgreSQL.',
            })

        pg_dump = shutil.which('pg_dump')
        if not pg_dump:
            return BackupService._registrar_historico({
                'tipo': 'manual',
                'arquivo': None,
                'caminho': None,
                'tamanho_bytes': 0,
                'status': 'erro',
                'mensagem': 'pg_dump não encontrado. Instale as ferramentas do PostgreSQL ou ajuste o PATH.',
            })

        comando = [
            pg_dump,
            '--format=custom',
            '--no-owner',
            '--file',
            str(destino),
            '--host',
            banco['host'],
            '--port',
            str(banco['port']),
            '--username',
            banco['username'],
            banco['database'],
        ]

        env = os.environ.copy()
        if banco.get('password'):
            env['PGPASSWORD'] = banco['password']

        try:
            resultado = subprocess.run(
                comando,
                env=env,
                capture_output=True,
                text=True,
                timeout=1800,
                check=False,
            )
        except Exception as exc:  # pragma: no cover - erro raro de sistema operacional
            destino.unlink(missing_ok=True)
            return BackupService._registrar_historico({
                'tipo': 'manual',
                'arquivo': None,
                'caminho': None,
                'tamanho_bytes': 0,
                'status': 'erro',
                'mensagem': BackupService._sanitize_message(str(exc), banco),
            })

        if resultado.returncode != 0:
            destino.unlink(missing_ok=True)
            mensagem = resultado.stderr or resultado.stdout or 'Falha ao executar pg_dump.'
            return BackupService._registrar_historico({
                'tipo': 'manual',
                'arquivo': None,
                'caminho': None,
                'tamanho_bytes': 0,
                'status': 'erro',
                'mensagem': BackupService._sanitize_message(mensagem, banco),
            })

        tamanho = destino.stat().st_size if destino.exists() else 0
        return BackupService._registrar_historico({
            'tipo': 'manual',
            'arquivo': arquivo,
            'caminho': BackupService._relative_path(destino),
            'tamanho_bytes': tamanho,
            'status': 'concluido',
            'mensagem': 'Backup manual concluído.',
        })

    @staticmethod
    def listar_backups(limit: int = 20) -> list[dict[str, Any]]:
        historico = BackupService._read_json(BackupService._history_file(), [])
        historico = historico if isinstance(historico, list) else []
        historico = sorted(historico, key=lambda item: item.get('created_at') or '', reverse=True)
        return historico[:limit]

    @staticmethod
    def obter_status_backup() -> dict[str, Any]:
        BackupService._ensure_dirs()
        historico = BackupService.listar_backups(limit=200)
        ultimo = historico[0] if historico else None
        concluidos = [item for item in historico if item.get('status') == 'concluido' and item.get('tamanho_bytes')]
        agendamento = BackupService.obter_agendamento()
        banco = BackupService._database_config()
        pg_dump_disponivel = bool(shutil.which('pg_dump'))
        tamanho_medio = int(sum(item['tamanho_bytes'] for item in concluidos) / len(concluidos)) if concluidos else 0

        checklist = [
            {
                'label': 'Pasta local de backups acessível',
                'ok': BackupService._postgres_dir().exists(),
            },
            {
                'label': 'Banco PostgreSQL configurado',
                'ok': banco['is_postgres'],
            },
            {
                'label': 'pg_dump disponível no PATH',
                'ok': pg_dump_disponivel,
            },
            {
                'label': 'Último backup concluído',
                'ok': bool(ultimo and ultimo.get('status') == 'concluido'),
            },
            {
                'label': f"Retenção configurada em {agendamento['retencao_dias']} dias",
                'ok': True,
            },
        ]

        return {
            'success': True,
            'status': 'ok' if ultimo and ultimo.get('status') == 'concluido' else 'atencao',
            'engine': 'PostgreSQL' if banco['is_postgres'] else 'Não PostgreSQL',
            'formato': 'custom .dump',
            'pasta': BackupService._relative_path(BackupService._postgres_dir()),
            'ultimo_backup': ultimo,
            'retencao_dias': agendamento['retencao_dias'],
            'tamanho_medio_bytes': tamanho_medio,
            'tamanho_medio_formatado': BackupService.formatar_bytes(tamanho_medio),
            'checklist': checklist,
            'agendamento': agendamento,
            'recomendacao': 'Exporte configurações após mudanças importantes e mantenha cópias fora desta máquina.',
        }

    @staticmethod
    def obter_agendamento() -> dict[str, Any]:
        padrao = {
            'ativo': False,
            'frequencia': 'diaria',
            'horario': '02:00',
            'retencao_dias': 30,
            'mensagem': 'Configuração visual preparada. Agendamento automático será ativado em etapa futura.',
        }
        dados = BackupService._read_json(BackupService._config_file(), {})
        if isinstance(dados, dict):
            padrao.update({
                key: dados[key]
                for key in ['ativo', 'frequencia', 'horario', 'retencao_dias']
                if key in dados
            })
        padrao['retencao_dias'] = BackupService._int_range(padrao.get('retencao_dias'), 1, 365, 30)
        padrao['horario'] = BackupService._normalizar_horario(padrao.get('horario'))
        padrao['proximo_backup_estimado'] = BackupService._proximo_backup_estimado(
            padrao['frequencia'],
            padrao['horario'],
        )
        return padrao

    @staticmethod
    def salvar_agendamento(dados: dict[str, Any] | None) -> dict[str, Any]:
        dados = dados or {}
        agendamento = {
            'ativo': bool(dados.get('ativo')),
            'frequencia': BackupService._normalizar_frequencia(dados.get('frequencia')),
            'horario': BackupService._normalizar_horario(dados.get('horario')),
            'retencao_dias': BackupService._int_range(dados.get('retencao_dias'), 1, 365, 30),
            'updated_at': BackupService._now_iso(),
        }
        BackupService._ensure_dirs()
        BackupService._write_json(BackupService._config_file(), agendamento)
        return BackupService.obter_agendamento()

    @staticmethod
    def baixar_backup(nome_arquivo: str) -> Path:
        return BackupService._safe_backup_path(nome_arquivo, must_exist=True)

    @staticmethod
    def restaurar_backup(nome_arquivo: str, confirmacao: str | None) -> dict[str, Any]:
        if str(confirmacao or '').strip() != CONFIRMACAO_RESTORE:
            raise ValueError('Confirmação forte obrigatória para restauração.')

        caminho = BackupService._safe_backup_path(nome_arquivo, must_exist=True)
        banco = BackupService._database_config()
        if not banco['is_postgres']:
            raise RuntimeError('Restauração local disponível apenas para PostgreSQL.')

        if caminho.suffix.lower() == '.dump':
            ferramenta = shutil.which('pg_restore')
            if not ferramenta:
                raise RuntimeError('pg_restore não encontrado. Restauração manual necessária.')
            comando = [
                ferramenta,
                '--clean',
                '--if-exists',
                '--no-owner',
                '--host',
                banco['host'],
                '--port',
                str(banco['port']),
                '--username',
                banco['username'],
                '--dbname',
                banco['database'],
                str(caminho),
            ]
        elif caminho.suffix.lower() == '.sql':
            ferramenta = shutil.which('psql')
            if not ferramenta:
                raise RuntimeError('psql não encontrado. Restauração manual necessária.')
            comando = [
                ferramenta,
                '--host',
                banco['host'],
                '--port',
                str(banco['port']),
                '--username',
                banco['username'],
                '--dbname',
                banco['database'],
                '--file',
                str(caminho),
            ]
        else:
            raise ValueError('Formato de backup inválido para restauração.')

        env = os.environ.copy()
        if banco.get('password'):
            env['PGPASSWORD'] = banco['password']

        resultado = subprocess.run(
            comando,
            env=env,
            capture_output=True,
            text=True,
            timeout=1800,
            check=False,
        )
        if resultado.returncode != 0:
            mensagem = resultado.stderr or resultado.stdout or 'Falha ao restaurar backup.'
            raise RuntimeError(BackupService._sanitize_message(mensagem, banco))

        return {
            'arquivo': caminho.name,
            'status': 'concluido',
            'mensagem': 'Backup restaurado com sucesso.',
            'restaurado_em': BackupService._now_iso(),
        }

    @staticmethod
    def exportar_configuracoes() -> dict[str, Any]:
        try:
            from backend.models import PerfilFinanceiro, Preferencia
        except ImportError:  # pragma: no cover
            from models import PerfilFinanceiro, Preferencia

        preferencia = Preferencia.query.first()
        perfis = PerfilFinanceiro.query.order_by(PerfilFinanceiro.id.asc()).all()
        return {
            'tipo': 'controle_financeiro_configuracoes',
            'versao': 'BACKUP-LOCAL-1',
            'gerado_em': BackupService._now_iso(),
            'conteudo': {
                'preferencias': BackupService._preferencias_seguras(preferencia),
                'perfis_financeiros': [
                    {
                        'nome': perfil.nome,
                        'tipo': perfil.tipo,
                        'avatar': perfil.avatar,
                        'cor': perfil.cor,
                        'ativo': bool(perfil.ativo),
                        'padrao': bool(perfil.padrao),
                    }
                    for perfil in perfis
                ],
            },
        }

    @staticmethod
    def importar_configuracoes(payload: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError('Arquivo de configurações inválido.')
        if payload.get('tipo') != 'controle_financeiro_configuracoes':
            raise ValueError('Tipo de arquivo de configurações não reconhecido.')
        if not isinstance(payload.get('conteudo'), dict):
            raise ValueError('Conteúdo de configurações ausente.')
        return {
            'aplicado': False,
            'mensagem': 'Arquivo validado. Importação automática de configurações ficará para etapa futura.',
        }

    @staticmethod
    def formatar_bytes(valor: int | float | None) -> str:
        tamanho = float(valor or 0)
        for unidade in ['B', 'KB', 'MB', 'GB']:
            if tamanho < 1024 or unidade == 'GB':
                if unidade == 'B':
                    return f'{int(tamanho)} B'
                return f'{tamanho:.1f} {unidade}'.replace('.', ',')
            tamanho /= 1024
        return '0 B'

    @staticmethod
    def _registrar_historico(dados: dict[str, Any]) -> dict[str, Any]:
        BackupService._ensure_dirs()
        item = {
            'id': str(uuid.uuid4()),
            'created_at': BackupService._now_iso(),
            'tipo': dados.get('tipo') or 'manual',
            'arquivo': dados.get('arquivo'),
            'caminho': dados.get('caminho'),
            'tamanho_bytes': int(dados.get('tamanho_bytes') or 0),
            'tamanho_formatado': BackupService.formatar_bytes(dados.get('tamanho_bytes') or 0),
            'status': dados.get('status') or 'erro',
            'mensagem': dados.get('mensagem') or '',
        }
        historico = BackupService._read_json(BackupService._history_file(), [])
        if not isinstance(historico, list):
            historico = []
        historico.insert(0, item)
        BackupService._write_json(BackupService._history_file(), historico[:200])
        return item

    @staticmethod
    def _database_config() -> dict[str, Any]:
        raw_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI') or os.getenv('DATABASE_URL') or ''
        parsed = urlparse(raw_uri)
        scheme = (parsed.scheme or '').lower()
        is_postgres = scheme.startswith('postgresql') or scheme == 'postgres'
        return {
            'raw_uri': raw_uri,
            'is_postgres': is_postgres,
            'host': parsed.hostname or 'localhost',
            'port': parsed.port or 5432,
            'username': unquote(parsed.username or ''),
            'password': unquote(parsed.password or ''),
            'database': unquote((parsed.path or '').lstrip('/')),
        }

    @staticmethod
    def _sanitize_message(message: str, banco: dict[str, Any]) -> str:
        texto = str(message or '')
        for segredo in [banco.get('password'), banco.get('raw_uri')]:
            if segredo:
                texto = texto.replace(str(segredo), '[oculto]')
        return texto.strip()[:500] or 'Erro operacional controlado.'

    @staticmethod
    def _preferencias_seguras(preferencia) -> dict[str, Any]:
        if not preferencia:
            return {}
        dados = preferencia.to_dict()
        return {
            chave: dados.get(chave)
            for chave in [
                'nome_usuario',
                'mes_inicio_planejamento',
                'dia_fechamento_mes',
                'ajustar_competencia_automatico',
                'exibir_aviso_despesa_vencida',
                'solicitar_confirmacao_exclusao',
                'vincular_pagamento_cartao_auto',
                'tema_sistema',
                'cor_principal',
                'mostrar_icones_coloridos',
                'abreviar_valores',
                'backup_automatico',
                'modo_inteligente_ativo',
                'sugestoes_economia',
                'classificacao_automatica',
                'correcao_categorias',
            ]
        }

    @staticmethod
    def _safe_backup_path(nome_arquivo: str, must_exist: bool = False) -> Path:
        nome = str(nome_arquivo or '').strip()
        if not nome or Path(nome).name != nome or '..' in nome.replace('\\', '/').split('/'):
            raise ValueError('Nome de arquivo inválido.')
        if not nome.lower().endswith(('.dump', '.sql')):
            raise ValueError('Formato de backup inválido.')

        base = BackupService._postgres_dir().resolve()
        caminho = (base / nome).resolve()
        try:
            caminho.relative_to(base)
        except ValueError as exc:
            raise ValueError('Arquivo fora da pasta de backups.') from exc
        if must_exist and not caminho.exists():
            raise FileNotFoundError('Backup não encontrado.')
        return caminho

    @staticmethod
    def _base_dir() -> Path:
        configurado = current_app.config.get('BACKUP_BASE_DIR')
        if configurado:
            return Path(configurado)
        return Path(__file__).resolve().parents[2] / 'data' / 'backups'

    @staticmethod
    def _postgres_dir() -> Path:
        return BackupService._base_dir() / 'postgres'

    @staticmethod
    def _history_file() -> Path:
        return BackupService._base_dir() / 'backup_history.json'

    @staticmethod
    def _config_file() -> Path:
        return BackupService._base_dir() / 'backup_config.json'

    @staticmethod
    def _ensure_dirs() -> None:
        BackupService._postgres_dir().mkdir(parents=True, exist_ok=True)

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

    @staticmethod
    def _backup_filename() -> str:
        return f"backup_controle_financeiro_{datetime.now().strftime('%Y%m%d_%H%M%S')}.dump"

    @staticmethod
    def _relative_path(caminho: Path) -> str:
        raiz = Path(__file__).resolve().parents[2]
        try:
            return str(caminho.resolve().relative_to(raiz)).replace('\\', '/')
        except ValueError:
            return str(caminho)

    @staticmethod
    def _now_iso() -> str:
        return datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'

    @staticmethod
    def _normalizar_horario(valor: Any) -> str:
        texto = str(valor or '02:00').strip()
        partes = texto.split(':')
        try:
            hora = int(partes[0])
            minuto = int(partes[1]) if len(partes) > 1 else 0
        except (TypeError, ValueError):
            return '02:00'
        if not (0 <= hora <= 23 and 0 <= minuto <= 59):
            return '02:00'
        return f'{hora:02d}:{minuto:02d}'

    @staticmethod
    def _normalizar_frequencia(valor: Any) -> str:
        texto = str(valor or 'diaria').strip().lower()
        return texto if texto in {'diaria', 'semanal', 'mensal'} else 'diaria'

    @staticmethod
    def _int_range(valor: Any, minimo: int, maximo: int, padrao: int) -> int:
        try:
            numero = int(valor)
        except (TypeError, ValueError):
            return padrao
        return min(max(numero, minimo), maximo)

    @staticmethod
    def _proximo_backup_estimado(frequencia: str, horario: str) -> str:
        agora = datetime.now()
        hora, minuto = [int(parte) for parte in horario.split(':')]
        proximo = agora.replace(hour=hora, minute=minuto, second=0, microsecond=0)
        if proximo <= agora:
            proximo += timedelta(days=1)
        if frequencia == 'semanal':
            proximo += timedelta(days=6)
        if frequencia == 'mensal':
            proximo += timedelta(days=29)
        return proximo.strftime('%Y-%m-%d %H:%M')
