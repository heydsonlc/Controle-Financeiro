"""BASE-REAL-1A: backup real e reset seguro do banco local PostgreSQL.

Uso:
    .\venv\Scripts\python.exe scripts\base_real_1a_reset.py --dry-run
    .\venv\Scripts\python.exe scripts\base_real_1a_reset.py --yes

O script:
- exige PostgreSQL local;
- gera backup real via BackupService antes de qualquer limpeza;
- preserva perfil_financeiro, preferencia e alembic_version;
- limpa as demais tabelas com TRUNCATE ... RESTART IDENTITY CASCADE;
- garante os perfis Pessoal e Empresa ao final.
"""

from __future__ import annotations

import argparse
import ipaddress
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import inspect, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app import create_app
from backend.models import PerfilFinanceiro, db
from backend.services.backup_service import BackupService
from backend.services.perfil_financeiro_service import PerfilFinanceiroService


TABELAS_PRESERVADAS = {
    "alembic_version",
    "perfil_financeiro",
    "preferencia",
}

PERFIS_OBRIGATORIOS = ("Pessoal", "Empresa")
REMOTE_MARKERS = ("digitalocean", "ondigitalocean", "do-user", "db.do-user")
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def mascarar_url(url: str | None) -> str:
    if not url:
        return "(nao definida)"
    return re.sub(r"://([^:@]+:[^@]+@)", "://***:***@", url)


def validar_postgres_local(url: str | None) -> tuple[str, str]:
    if not url:
        raise RuntimeError("SQLALCHEMY_DATABASE_URI/DATABASE_URL ausente.")

    url_lower = url.lower()
    if any(marker in url_lower for marker in REMOTE_MARKERS):
        raise RuntimeError("URL bloqueada: marcador remoto detectado.")

    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    if not scheme.startswith("postgresql") and scheme != "postgres":
        raise RuntimeError("BASE-REAL-1A exige PostgreSQL. Banco atual nao e PostgreSQL.")

    host = parsed.hostname or ""
    host_lower = host.lower()
    if host_lower not in LOCAL_HOSTS:
        try:
            ip = ipaddress.ip_address(host_lower)
            if not ip.is_loopback:
                raise RuntimeError(f"Host de banco nao local bloqueado: {host}")
        except ValueError as exc:
            raise RuntimeError(f"Host de banco nao local bloqueado: {host}") from exc

    database = (parsed.path or "").lstrip("/")
    if not database:
        raise RuntimeError("Nome do banco nao identificado.")
    return host, database


def tabelas_para_limpar() -> list[str]:
    insp = inspect(db.engine)
    existentes = sorted(insp.get_table_names())
    return [nome for nome in existentes if nome not in TABELAS_PRESERVADAS]


def contar_tabelas(tabelas: list[str]) -> dict[str, int]:
    contagens: dict[str, int] = {}
    for tabela in tabelas:
        quoted = db.engine.dialect.identifier_preparer.quote(tabela)
        contagens[tabela] = int(db.session.execute(text(f"SELECT COUNT(*) FROM {quoted}")).scalar() or 0)
    return contagens


def resolver_caminho_backup(resultado: dict) -> Path:
    arquivo = str(resultado.get("arquivo") or "").strip()
    caminho_relativo = str(resultado.get("caminho") or "").strip()
    if caminho_relativo:
        caminho = Path(caminho_relativo)
        if not caminho.is_absolute():
            caminho = ROOT / caminho
    elif arquivo:
        caminho = ROOT / "data" / "backups" / "postgres" / arquivo
    else:
        raise RuntimeError("Backup nao retornou nome de arquivo.")
    return caminho.resolve()


def executar_backup_obrigatorio() -> dict:
    resultado = BackupService.executar_backup_manual()
    if resultado.get("status") != "concluido":
        mensagem = resultado.get("mensagem") or "Backup falhou."
        raise RuntimeError(f"Backup pre-reset falhou: {mensagem}")

    caminho = resolver_caminho_backup(resultado)
    if not caminho.exists() or caminho.stat().st_size <= 0:
        raise RuntimeError(f"Backup informado nao foi encontrado ou esta vazio: {caminho}")

    return {
        **resultado,
        "caminho_absoluto": str(caminho),
        "tamanho_bytes": caminho.stat().st_size,
    }


def truncar_tabelas(tabelas: list[str]) -> None:
    if not tabelas:
        return
    preparer = db.engine.dialect.identifier_preparer
    nomes = ", ".join(preparer.quote(tabela) for tabela in tabelas)
    db.session.execute(text(f"TRUNCATE TABLE {nomes} RESTART IDENTITY CASCADE"))


def garantir_perfis_essenciais() -> list[PerfilFinanceiro]:
    perfis = PerfilFinanceiroService.obter_ou_criar_perfis_iniciais()
    pessoal = PerfilFinanceiro.query.filter_by(nome="Pessoal").first()
    empresa = PerfilFinanceiro.query.filter_by(nome="Empresa").first()
    if not pessoal or not empresa:
        raise RuntimeError("Perfis Pessoal e Empresa nao foram encontrados apos reset.")
    pessoal.ativo = True
    pessoal.padrao = True
    empresa.ativo = True
    if empresa.padrao:
        empresa.padrao = False
    db.session.flush()
    return list(perfis)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BASE-REAL-1A reset seguro do banco local.")
    parser.add_argument("--yes", action="store_true", help="Confirma a limpeza apos backup.")
    parser.add_argument("--dry-run", action="store_true", help="Lista tabelas e valida conexao sem backup/reset.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    app = create_app("development")
    app.config["SQLALCHEMY_ECHO"] = False

    with app.app_context():
        db.engine.echo = False
        db_url = app.config.get("SQLALCHEMY_DATABASE_URI") or os.getenv("DATABASE_URL")
        host, database = validar_postgres_local(db_url)
        tabelas = tabelas_para_limpar()

        print("BASE-REAL-1A - Reset seguro do banco")
        print(f"Banco: {mascarar_url(db_url)}")
        print(f"Host validado: {host}")
        print(f"Database validado: {database}")
        print("Tabelas preservadas:", ", ".join(sorted(TABELAS_PRESERVADAS)))
        print("Tabelas que serao limpas:")
        for tabela in tabelas:
            print(f"  - {tabela}")

        if args.dry_run:
            print("[DRY-RUN] Nenhum backup ou reset executado.")
            return 0

        if not args.yes:
            print("[BLOQUEADO] Reexecute com --yes para confirmar backup e reset.")
            return 2

        backup = executar_backup_obrigatorio()
        print(f"[OK] Backup criado: {backup.get('arquivo')} ({backup.get('tamanho_bytes')} bytes)")

        antes = contar_tabelas(tabelas)
        truncar_tabelas(tabelas)
        garantir_perfis_essenciais()
        db.session.commit()

        depois = contar_tabelas(tabelas)
        perfis = PerfilFinanceiro.query.filter(PerfilFinanceiro.nome.in_(PERFIS_OBRIGATORIOS)).all()

        print("[OK] Reset concluido.")
        print("Perfis preservados:", ", ".join(sorted(perfil.nome for perfil in perfis)))
        print("Resumo de limpeza:")
        for tabela in tabelas:
            print(f"  - {tabela}: {antes.get(tabela, 0)} -> {depois.get(tabela, 0)}")
        print(f"BACKUP_ARQUIVO={backup.get('arquivo')}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
