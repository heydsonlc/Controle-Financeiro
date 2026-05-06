"""
Serviço local de backup e restauração do PostgreSQL.

O histórico fica fora do banco para sobreviver a operações de restore.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from flask import current_app


CONFIRMACAO_RESTORE = 'CONFIRMO RESTAURACAO'
CONFIRMACAO_TESTE_RESTORE = 'TESTAR RESTAURACAO'
PREFIXO_BANCO_TESTE_RESTORE = 'controle_financeiro_restore_test_'
EXEMPLO_PG_DUMP_WINDOWS = r'C:\Program Files\PostgreSQL\18\bin\pg_dump.exe'
NOMES_BANCO_PROTEGIDOS = {'postgres', 'template0', 'template1'}

POSTGRES_TOOLS = {
    'pg_dump': {
        'campo': 'pg_dump_path',
        'env': 'PG_DUMP_PATH',
        'exe': 'pg_dump.exe',
        'obrigatorio': True,
    },
    'pg_restore': {
        'campo': 'pg_restore_path',
        'env': 'PG_RESTORE_PATH',
        'exe': 'pg_restore.exe',
        'obrigatorio': True,
    },
    'psql': {
        'campo': 'psql_path',
        'env': 'PSQL_PATH',
        'exe': 'psql.exe',
        'obrigatorio': False,
    },
}


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

        pg_dump = BackupService._resolver_ferramenta_postgres('pg_dump')
        if not pg_dump.get('caminho'):
            return BackupService._registrar_historico({
                'tipo': 'manual',
                'arquivo': None,
                'caminho': None,
                'tamanho_bytes': 0,
                'status': 'erro',
                'mensagem': (
                    'pg_dump não encontrado. Configure o caminho em Configurações > Backup. '
                    f'Exemplo: {EXEMPLO_PG_DUMP_WINDOWS}'
                ),
            })

        comando = [
            pg_dump['caminho'],
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
        ferramentas = BackupService.validar_ferramentas_postgres(salvar=False)
        pg_dump_disponivel = ferramentas['ferramentas']['pg_dump']['disponivel']
        pg_restore_disponivel = ferramentas['ferramentas']['pg_restore']['disponivel']
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
                'label': 'pg_dump disponível',
                'ok': pg_dump_disponivel,
            },
            {
                'label': 'pg_restore disponível',
                'ok': pg_restore_disponivel,
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
            'ferramentas': ferramentas,
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
        config = BackupService._read_config()
        config.update(agendamento)
        BackupService._write_json(BackupService._config_file(), config)
        return BackupService.obter_agendamento()

    @staticmethod
    def configurar_ferramentas_postgres(dados: dict[str, Any] | None) -> dict[str, Any]:
        dados = dados or {}
        config = BackupService._read_config()
        for meta in POSTGRES_TOOLS.values():
            campo = meta['campo']
            if campo in dados:
                config[campo] = str(dados.get(campo) or '').strip()
        config['auto_detectado'] = False
        config['updated_at'] = BackupService._now_iso()
        BackupService._ensure_dirs()
        BackupService._write_json(BackupService._config_file(), config)
        return BackupService.validar_ferramentas_postgres(salvar=True)

    @staticmethod
    def autodetectar_ferramentas_postgres() -> dict[str, Any]:
        encontrados = BackupService._autodetectar_ferramentas_postgres()
        config = BackupService._read_config()
        for nome, caminho in encontrados.items():
            campo = POSTGRES_TOOLS[nome]['campo']
            config[campo] = caminho
        config['auto_detectado'] = bool(encontrados)
        config['updated_at'] = BackupService._now_iso()
        BackupService._ensure_dirs()
        BackupService._write_json(BackupService._config_file(), config)
        resultado = BackupService.validar_ferramentas_postgres(salvar=True)
        resultado['encontrados'] = encontrados
        resultado['mensagem'] = (
            'Ferramentas PostgreSQL detectadas e salvas.'
            if encontrados else
            'Nenhuma instalação local do PostgreSQL foi detectada nos caminhos padrão.'
        )
        return resultado

    @staticmethod
    def validar_ferramentas_postgres(salvar: bool = True) -> dict[str, Any]:
        config = BackupService._read_config()
        banco = BackupService._database_config()
        ferramentas = {}
        for nome in POSTGRES_TOOLS:
            resolucao = BackupService._resolver_ferramenta_postgres(nome, config=config)
            info = {
                'nome': nome,
                'disponivel': False,
                'caminho': resolucao.get('caminho'),
                'origem': resolucao.get('origem'),
                'versao': None,
                'mensagem': resolucao.get('mensagem') or '',
            }
            if resolucao.get('caminho'):
                try:
                    resultado = subprocess.run(
                        [resolucao['caminho'], '--version'],
                        capture_output=True,
                        text=True,
                        timeout=10,
                        check=False,
                    )
                    saida = (resultado.stdout or resultado.stderr or '').strip()
                    info['disponivel'] = resultado.returncode == 0
                    info['versao'] = BackupService._sanitize_message(saida, banco) if saida else None
                    info['mensagem'] = 'Disponível.' if info['disponivel'] else BackupService._sanitize_message(saida, banco)
                except Exception as exc:  # pragma: no cover - depende do sistema operacional
                    info['mensagem'] = BackupService._sanitize_message(str(exc), banco)
            ferramentas[nome] = info

        ultima_validacao = BackupService._now_iso()
        disponivel = all(
            ferramentas[nome]['disponivel']
            for nome, meta in POSTGRES_TOOLS.items()
            if meta['obrigatorio']
        )
        payload = {
            'success': True,
            'disponivel': disponivel,
            'ultima_validacao': ultima_validacao,
            'auto_detectado': bool(config.get('auto_detectado')),
            'configuracao': BackupService._configuracao_ferramentas(config),
            'ferramentas': ferramentas,
        }
        if salvar:
            config['ultima_validacao'] = ultima_validacao
            config['status_ferramentas'] = {
                nome: {
                    'disponivel': info['disponivel'],
                    'caminho': info.get('caminho'),
                    'origem': info.get('origem'),
                    'versao': info.get('versao'),
                    'mensagem': info.get('mensagem'),
                }
                for nome, info in ferramentas.items()
            }
            BackupService._write_json(BackupService._config_file(), config)
            payload['configuracao'] = BackupService._configuracao_ferramentas(config)
        return payload

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
            ferramenta = BackupService._resolver_ferramenta_postgres('pg_restore')
            if not ferramenta.get('caminho'):
                raise RuntimeError('pg_restore não encontrado. Configure o caminho em Configurações > Backup.')
            comando = [
                ferramenta['caminho'],
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
            ferramenta = BackupService._resolver_ferramenta_postgres('psql')
            if not ferramenta.get('caminho'):
                raise RuntimeError('psql não encontrado. Configure o caminho em Configurações > Backup.')
            comando = [
                ferramenta['caminho'],
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
    def testar_restauracao_backup(
        nome_arquivo: str,
        confirmacao: str | None,
        manter_banco: bool = False,
    ) -> dict[str, Any]:
        if str(confirmacao or '').strip() != CONFIRMACAO_TESTE_RESTORE:
            raise ValueError('Confirmacao forte obrigatoria para teste de restauracao.')

        caminho = BackupService._safe_backup_path(nome_arquivo, must_exist=True)
        banco = BackupService._database_config()
        if not banco['is_postgres']:
            raise RuntimeError('Teste de restauracao disponivel apenas para PostgreSQL.')

        banco_teste = BackupService.gerar_nome_banco_teste()
        BackupService.validar_nome_banco_descartavel(banco_teste)
        if banco_teste == banco.get('database'):
            raise RuntimeError('Banco descartavel nao pode ser igual ao banco principal.')

        inicio = datetime.utcnow()
        criado = False
        removido = False
        validacoes: list[dict[str, Any]] = []
        status = 'erro'
        mensagem = ''
        erro_controlado = ''

        try:
            BackupService.criar_banco_teste(banco_teste)
            criado = True
            BackupService._restaurar_arquivo_em_banco_teste(caminho, banco_teste, banco)
            resultado_validacao = BackupService.validar_restore_banco_teste(banco_teste)
            validacoes = resultado_validacao.get('validacoes') or []
            if not resultado_validacao.get('ok'):
                raise RuntimeError(resultado_validacao.get('mensagem') or 'Validacao basica do restore falhou.')
            status = 'concluido'
            mensagem = 'Teste de restauracao concluido em banco descartavel.'
        except Exception as exc:
            mensagem = BackupService._sanitize_message(str(exc), banco)
            erro_controlado = mensagem
        finally:
            if criado and not manter_banco:
                try:
                    BackupService.remover_banco_teste(banco_teste)
                    removido = True
                except Exception as exc:  # pragma: no cover - depende de permissao/ambiente
                    aviso = BackupService._sanitize_message(str(exc), banco)
                    validacoes.append({
                        'item': 'remocao_banco_descartavel',
                        'ok': False,
                        'mensagem': aviso,
                    })
                    if status == 'concluido':
                        status = 'erro'
                        mensagem = f'Teste restaurou o backup, mas falhou ao remover o banco descartavel: {aviso}'
                        erro_controlado = aviso

        duracao = max(0.0, (datetime.utcnow() - inicio).total_seconds())
        return BackupService._registrar_historico_teste_restauracao({
            'backup_arquivo': caminho.name,
            'database_teste': banco_teste,
            'status': status,
            'duracao_segundos': round(duracao, 2),
            'validacoes': validacoes,
            'mensagem': mensagem or erro_controlado or 'Falha controlada no teste de restauracao.',
            'removido_apos_teste': removido,
            'erro_controlado': erro_controlado,
        })

    @staticmethod
    def gerar_nome_banco_teste() -> str:
        sufixo = uuid.uuid4().hex[:6]
        return f"{PREFIXO_BANCO_TESTE_RESTORE}{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{sufixo}"

    @staticmethod
    def validar_nome_banco_descartavel(nome: str) -> None:
        banco = BackupService._database_config()
        valor = str(nome or '').strip()
        if not valor.startswith(PREFIXO_BANCO_TESTE_RESTORE):
            raise ValueError('Nome do banco descartavel deve usar prefixo seguro.')
        if not re.fullmatch(r'[a-zA-Z0-9_]+', valor):
            raise ValueError('Nome do banco descartavel contem caracteres invalidos.')
        if valor.lower() in NOMES_BANCO_PROTEGIDOS:
            raise ValueError('Nome de banco protegido nao pode ser usado.')
        if valor == banco.get('database'):
            raise ValueError('Banco descartavel nao pode ser o banco principal.')

    @staticmethod
    def criar_banco_teste(nome: str) -> dict[str, Any]:
        BackupService.validar_nome_banco_descartavel(nome)
        banco = BackupService._database_config()
        comando = BackupService._psql_command('postgres', f'CREATE DATABASE "{nome}"')
        resultado = BackupService._run_postgres_command(comando, banco, timeout=120)
        if resultado.returncode != 0:
            mensagem = resultado.stderr or resultado.stdout or 'Falha ao criar banco descartavel.'
            texto = BackupService._sanitize_message(mensagem, banco)
            if 'permission denied' in texto.lower() or 'permiss' in texto.lower():
                raise RuntimeError('Usuario do PostgreSQL nao possui permissao para criar banco descartavel.')
            raise RuntimeError(texto)
        return {'database': nome, 'status': 'criado'}

    @staticmethod
    def remover_banco_teste(nome: str) -> dict[str, Any]:
        BackupService.validar_nome_banco_descartavel(nome)
        banco = BackupService._database_config()
        comando = BackupService._psql_command('postgres', f'DROP DATABASE IF EXISTS "{nome}" WITH (FORCE)')
        resultado = BackupService._run_postgres_command(comando, banco, timeout=120)
        if resultado.returncode != 0:
            mensagem = resultado.stderr or resultado.stdout or 'Falha ao remover banco descartavel.'
            raise RuntimeError(BackupService._sanitize_message(mensagem, banco))
        return {'database': nome, 'status': 'removido'}

    @staticmethod
    def validar_restore_banco_teste(nome: str) -> dict[str, Any]:
        BackupService.validar_nome_banco_descartavel(nome)
        validacoes: list[dict[str, Any]] = []

        tabelas = BackupService._psql_scalar(
            nome,
            "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE'",
        )
        try:
            total_tabelas = int(tabelas or 0)
        except ValueError:
            total_tabelas = 0
        validacoes.append({
            'item': 'tabelas_publicas',
            'ok': total_tabelas > 0,
            'valor': total_tabelas,
            'mensagem': f'{total_tabelas} tabela(s) publicas encontradas.',
        })

        tabelas_principais = [
            'perfil_financeiro',
            'categoria',
            'conta_bancaria',
            'item_despesa',
            'ir_comprovante',
            'bem_patrimonial',
            'alembic_version',
        ]
        for tabela in tabelas_principais:
            existe = BackupService._psql_scalar(nome, f"SELECT to_regclass('public.{tabela}') IS NOT NULL")
            existe_bool = str(existe).strip().lower() in {'t', 'true', '1'}
            validacao = {
                'item': f'tabela_{tabela}',
                'ok': True if tabela != 'perfil_financeiro' else existe_bool,
                'presente': existe_bool,
                'mensagem': 'Tabela encontrada.' if existe_bool else 'Tabela nao encontrada neste backup.',
            }
            if existe_bool:
                try:
                    registros = int(BackupService._psql_scalar(nome, f'SELECT count(*) FROM "{tabela}"') or 0)
                except ValueError:
                    registros = 0
                validacao['registros'] = registros
            validacoes.append(validacao)

        ok = all(
            item.get('ok')
            for item in validacoes
            if item.get('item') in {'tabelas_publicas', 'tabela_perfil_financeiro'}
        )
        return {
            'ok': ok,
            'validacoes': validacoes,
            'mensagem': 'Validacoes basicas concluidas.' if ok else 'Validacao basica encontrou pendencias.',
        }

    @staticmethod
    def listar_testes_restauracao(limit: int = 20) -> list[dict[str, Any]]:
        historico = BackupService._read_json(BackupService._restore_test_history_file(), [])
        historico = historico if isinstance(historico, list) else []
        historico = sorted(historico, key=lambda item: item.get('data_hora') or '', reverse=True)
        return historico[:limit]

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
    def _registrar_historico_teste_restauracao(dados: dict[str, Any]) -> dict[str, Any]:
        BackupService._ensure_dirs()
        item = {
            'id': str(uuid.uuid4()),
            'data_hora': BackupService._now_iso(),
            'backup_arquivo': dados.get('backup_arquivo'),
            'database_teste': dados.get('database_teste'),
            'status': dados.get('status') or 'erro',
            'duracao_segundos': float(dados.get('duracao_segundos') or 0),
            'validacoes': dados.get('validacoes') or [],
            'mensagem': dados.get('mensagem') or '',
            'removido_apos_teste': bool(dados.get('removido_apos_teste')),
            'erro_controlado': dados.get('erro_controlado') or '',
        }
        historico = BackupService._read_json(BackupService._restore_test_history_file(), [])
        if not isinstance(historico, list):
            historico = []
        historico.insert(0, item)
        BackupService._write_json(BackupService._restore_test_history_file(), historico[:200])
        return item

    @staticmethod
    def _restaurar_arquivo_em_banco_teste(caminho: Path, banco_teste: str, banco: dict[str, Any]) -> None:
        BackupService.validar_nome_banco_descartavel(banco_teste)
        if caminho.suffix.lower() == '.dump':
            ferramenta = BackupService._resolver_ferramenta_postgres('pg_restore')
            if not ferramenta.get('caminho'):
                raise RuntimeError('pg_restore nao encontrado. Configure o caminho em Configuracoes > Backup.')
            comando = [
                ferramenta['caminho'],
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
                banco_teste,
                str(caminho),
            ]
        elif caminho.suffix.lower() == '.sql':
            ferramenta = BackupService._resolver_ferramenta_postgres('psql')
            if not ferramenta.get('caminho'):
                raise RuntimeError('psql nao encontrado. Configure o caminho em Configuracoes > Backup.')
            comando = [
                ferramenta['caminho'],
                '--host',
                banco['host'],
                '--port',
                str(banco['port']),
                '--username',
                banco['username'],
                '--dbname',
                banco_teste,
                '--file',
                str(caminho),
            ]
        else:
            raise ValueError('Formato de backup invalido para teste de restauracao.')

        resultado = BackupService._run_postgres_command(comando, banco, timeout=1800)
        if resultado.returncode != 0:
            mensagem = resultado.stderr or resultado.stdout or 'Falha ao restaurar backup no banco descartavel.'
            raise RuntimeError(BackupService._sanitize_message(mensagem, banco))

    @staticmethod
    def _psql_command(database: str, sql: str) -> list[str]:
        banco = BackupService._database_config()
        ferramenta = BackupService._resolver_ferramenta_postgres('psql')
        if not ferramenta.get('caminho'):
            raise RuntimeError('psql nao encontrado. Configure o caminho em Configuracoes > Backup.')
        return [
            ferramenta['caminho'],
            '--host',
            banco['host'],
            '--port',
            str(banco['port']),
            '--username',
            banco['username'],
            '--dbname',
            database,
            '--command',
            sql,
        ]

    @staticmethod
    def _psql_scalar(database: str, sql: str) -> str:
        banco = BackupService._database_config()
        comando = BackupService._psql_command(database, sql)
        comando.extend(['--tuples-only', '--no-align'])
        resultado = BackupService._run_postgres_command(comando, banco, timeout=120)
        if resultado.returncode != 0:
            mensagem = resultado.stderr or resultado.stdout or 'Falha ao consultar banco descartavel.'
            raise RuntimeError(BackupService._sanitize_message(mensagem, banco))
        return (resultado.stdout or '').strip().splitlines()[-1].strip() if (resultado.stdout or '').strip() else ''

    @staticmethod
    def _run_postgres_command(comando: list[str], banco: dict[str, Any], timeout: int) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        if banco.get('password'):
            env['PGPASSWORD'] = banco['password']
        try:
            return subprocess.run(
                comando,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except Exception as exc:  # pragma: no cover - depende do sistema operacional
            raise RuntimeError(BackupService._sanitize_message(str(exc), banco)) from exc

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
    def _read_config() -> dict[str, Any]:
        dados = BackupService._read_json(BackupService._config_file(), {})
        return dados if isinstance(dados, dict) else {}

    @staticmethod
    def _configuracao_ferramentas(config: dict[str, Any] | None = None) -> dict[str, Any]:
        config = config or BackupService._read_config()
        return {
            'pg_dump_path': str(config.get('pg_dump_path') or ''),
            'pg_restore_path': str(config.get('pg_restore_path') or ''),
            'psql_path': str(config.get('psql_path') or ''),
            'auto_detectado': bool(config.get('auto_detectado')),
            'ultima_validacao': config.get('ultima_validacao'),
            'status_ferramentas': config.get('status_ferramentas') or {},
        }

    @staticmethod
    def _resolver_ferramenta_postgres(nome: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
        meta = POSTGRES_TOOLS[nome]
        config = config or BackupService._read_config()
        candidatos = [
            ('configurado', config.get(meta['campo'])),
            ('variavel_ambiente', os.getenv(meta['env'])),
            ('path', shutil.which(nome)),
            ('autodetectado', BackupService._autodetectar_ferramentas_postgres().get(nome)),
        ]
        erros = []
        for origem, candidato in candidatos:
            caminho = str(candidato or '').strip()
            if not caminho:
                continue
            if BackupService._caminho_executavel(caminho):
                return {
                    'caminho': caminho,
                    'origem': origem,
                    'mensagem': 'Ferramenta localizada.',
                }
            erros.append(f'{origem}: caminho inválido')
        return {
            'caminho': None,
            'origem': None,
            'mensagem': '; '.join(erros) or f'{nome} não encontrado.',
        }

    @staticmethod
    def _caminho_executavel(caminho: str) -> bool:
        try:
            path = Path(caminho)
            if path.is_file():
                return True
        except (OSError, ValueError):
            return False
        return bool(shutil.which(caminho))

    @staticmethod
    def _autodetectar_ferramentas_postgres() -> dict[str, str]:
        encontrados: dict[str, str] = {}
        for nome, meta in POSTGRES_TOOLS.items():
            candidatos = []
            for raiz in BackupService._postgres_search_roots():
                try:
                    for versao_dir in Path(raiz).iterdir():
                        if not versao_dir.is_dir():
                            continue
                        caminho = versao_dir / 'bin' / meta['exe']
                        if caminho.is_file():
                            candidatos.append((BackupService._versao_sort_key(versao_dir.name), caminho))
                except (OSError, ValueError):
                    continue
            if candidatos:
                candidatos.sort(key=lambda item: item[0], reverse=True)
                encontrados[nome] = str(candidatos[0][1])
        return encontrados

    @staticmethod
    def _postgres_search_roots() -> list[Path]:
        configurado = current_app.config.get('BACKUP_POSTGRES_SEARCH_ROOTS')
        if configurado is not None:
            return [Path(item) for item in configurado]
        roots = []
        for env_name in ['ProgramFiles', 'ProgramFiles(x86)']:
            base = os.environ.get(env_name)
            if base:
                roots.append(Path(base) / 'PostgreSQL')
        roots.extend([
            Path(r'C:\Program Files\PostgreSQL'),
            Path(r'C:\Program Files (x86)\PostgreSQL'),
        ])
        unicos = []
        vistos = set()
        for root in roots:
            texto = str(root).lower()
            if texto not in vistos:
                vistos.add(texto)
                unicos.append(root)
        return unicos

    @staticmethod
    def _versao_sort_key(valor: str) -> tuple[int, ...]:
        partes = []
        for parte in str(valor or '').replace('-', '.').split('.'):
            try:
                partes.append(int(parte))
            except ValueError:
                partes.append(0)
        return tuple(partes or [0])

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
    def _restore_test_history_file() -> Path:
        return BackupService._base_dir() / 'restore_test_history.json'

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
