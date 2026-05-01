"""Popula icones padrao em categorias existentes no banco local/dev.

Uso:
    python scripts/seed_icones_categorias.py --dry-run
    python scripts/seed_icones_categorias.py
    python scripts/seed_icones_categorias.py --overwrite

Restricoes:
- roda apenas contra banco local (localhost, 127.0.0.1 ou ::1) ou SQLite local;
- nunca apaga dados;
- atualiza somente Categoria.icone;
- por padrao, preenche apenas categorias sem icone.
"""

from __future__ import annotations

import argparse
import ipaddress
import os
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app import create_app
from backend.models import Categoria, db


ICON_KEYS = {
    "wifi",
    "home",
    "heart",
    "cart",
    "food",
    "car",
    "bus",
    "fuel",
    "cash",
    "credit-card",
    "qr-code",
    "receipt",
    "bank",
    "briefcase",
    "shield",
    "lightning",
    "phone",
    "book",
    "gift",
    "tool",
    "repeat",
    "calendar",
    "tag",
    "education",
    "health",
    "travel",
    "pet",
    "default",
}

REMOTE_MARKERS = (
    "digitalocean",
    "ondigitalocean",
    "do-user",
    "db.do-user",
)

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

MAPPING_RULES: list[tuple[tuple[str, ...], str]] = [
    (("dev demo moradia", "moradia", "aluguel", "casa", "condominio"), "home"),
    (("dev demo saude", "saude", "medico", "consulta", "farmacia"), "health"),
    (("dev demo servicos", "servicos", "servico", "diarista", "manutencao", "mao de obra"), "tool"),
    (("dev demo mercado", "alimentacao", "alimentos", "mercado", "supermercado"), "cart"),
    (("dev demo assinaturas", "assinatura", "assinaturas", "streaming", "netflix", "spotify"), "repeat"),
    (("dev demo lazer", "lazer", "entretenimento", "cinema", "restaurante"), "gift"),
    (("dev demo receitas", "salario", "subsidio", "remuneracao", "kortex"), "briefcase"),
    (("bombeiros", "cbm", "corpo de bombeiros"), "shield"),
    (("internet", "wifi"), "wifi"),
    (("telefone", "celular", "comunicacao"), "phone"),
    (("transporte", "combustivel", "uber", "taxi", "veiculo", "carro"), "car"),
    (("educacao", "curso", "escola", "faculdade"), "education"),
    (("energia", "luz", "eletricidade"), "lightning"),
    (("agua", "saneamento"), "receipt"),
    (("tarifa bancaria", "banco"), "bank"),
    (("cartao", "fatura", "credito"), "credit-card"),
    (("financiamento",), "bank"),
    (("consorcio", "contemplacao"), "shield"),
    (("imposto", "impostos", "taxa", "taxas", "tributo", "tributos"), "receipt"),
    (("pet",), "pet"),
    (("viagem",), "travel"),
    (("aluguel recebido",), "home"),
    (("rendimento", "juros", "aplicacao", "investimento", "transferencia"), "bank"),
    (("premio", "receita avulsa"), "cash"),
    (("outro", "outros", "diverso", "diversos"), "tag"),
]


def normalizar(texto: str | None) -> str:
    if not texto:
        return ""
    sem_acento = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(ch for ch in sem_acento if not unicodedata.combining(ch))
    sem_acento = sem_acento.lower()
    sem_acento = sem_acento.replace("dev_demo_", "dev demo ")
    sem_acento = re.sub(r"[_\-/]+", " ", sem_acento)
    sem_acento = re.sub(r"\s+", " ", sem_acento).strip()
    return sem_acento


def sugerir_icone(nome: str | None) -> str | None:
    nome_normalizado = normalizar(nome)
    for termos, icone in MAPPING_RULES:
        if any(termo in nome_normalizado for termo in termos):
            if icone not in ICON_KEYS:
                raise RuntimeError(f"Icone mapeado nao existe no catalogo: {icone}")
            return icone
    return None


def mascarar_url(url: str | None) -> str:
    if not url:
        return "(nao definida)"
    return re.sub(r"://([^:@]+:[^@]+@)", "://***:***@", url)


def validar_url_local(url: str | None) -> tuple[str, str]:
    """Retorna (host, banco) se a URL for local; aborta caso contrario."""
    if not url:
        raise RuntimeError("DATABASE_URL/SQLALCHEMY_DATABASE_URI ausente.")

    url_lower = url.lower()
    if any(marker in url_lower for marker in REMOTE_MARKERS):
        raise RuntimeError("URL bloqueada: marcador de DigitalOcean/remoto detectado.")

    parsed = urlparse(url)

    if parsed.scheme.startswith("sqlite"):
        db_path = parsed.path or "(memoria)"
        return "sqlite-local", db_path

    host = parsed.hostname
    if not host:
        raise RuntimeError("Nao foi possivel identificar host do banco.")

    host_lower = host.lower()
    if host_lower not in LOCAL_HOSTS:
        try:
            ip = ipaddress.ip_address(host_lower)
            if not ip.is_loopback:
                raise RuntimeError(f"Host de banco nao local bloqueado: {host}")
        except ValueError as exc:
            raise RuntimeError(f"Host de banco nao local bloqueado: {host}") from exc

    banco = (parsed.path or "").lstrip("/") or "(sem nome)"
    return host, banco


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Popula icones padrao em categorias locais.")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o que seria alterado, sem gravar.")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Sobrescreve icones existentes. Sem esta flag, preenche apenas vazios.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    app = create_app("development")
    db_url = app.config.get("SQLALCHEMY_DATABASE_URI") or os.environ.get("DATABASE_URL")
    host, banco = validar_url_local(db_url)

    print("ICONES-1B - Popular icones de categorias")
    print(f"Modo: {'dry-run' if args.dry_run else 'execucao real'}")
    print(f"Overwrite: {'sim' if args.overwrite else 'nao'}")
    print(f"DATABASE_URL: {mascarar_url(db_url)}")
    print(f"Host validado: {host}")
    print(f"Banco validado: {banco}")
    print("")

    resultados: list[dict[str, str | int | None]] = []

    with app.app_context():
        categorias = Categoria.query.order_by(Categoria.nome.asc()).all()

        for categoria in categorias:
            sugestao = sugerir_icone(categoria.nome)
            icone_atual = categoria.icone
            status = "sem_sugestao"

            if sugestao is None:
                pass
            elif icone_atual == sugestao:
                status = "sem_alteracao"
            elif icone_atual and not args.overwrite:
                status = "preservada"
            else:
                status = "atualizada"
                if not args.dry_run:
                    categoria.icone = sugestao

            resultados.append(
                {
                    "id": categoria.id,
                    "nome": categoria.nome,
                    "tipo": getattr(categoria, "tipo", None) or "categoria",
                    "icone_anterior": icone_atual,
                    "icone_sugerido": sugestao,
                    "status": status,
                }
            )

        if args.dry_run:
            db.session.rollback()
        else:
            db.session.commit()

    total = len(resultados)
    atualizadas = sum(1 for r in resultados if r["status"] == "atualizada")
    sem_alteracao = sum(1 for r in resultados if r["status"] == "sem_alteracao")
    preservadas = sum(1 for r in resultados if r["status"] == "preservada")
    sem_sugestao = sum(1 for r in resultados if r["status"] == "sem_sugestao")

    print("Resumo:")
    print(f"  Total de categorias: {total}")
    print(f"  Atualizadas: {atualizadas}")
    print(f"  Sem alteracao: {sem_alteracao}")
    print(f"  Preservadas com icone existente: {preservadas}")
    print(f"  Sem sugestao: {sem_sugestao}")
    print("")
    print("Detalhes:")
    for item in resultados:
        print(
            "  "
            f"[{item['status']}] "
            f"#{item['id']} {item['nome']} "
            f"({item['tipo']}): "
            f"{item['icone_anterior'] or '-'} -> {item['icone_sugerido'] or '-'}"
        )

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"[ERRO] {exc}")
        raise SystemExit(1)
