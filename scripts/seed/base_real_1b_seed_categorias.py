"""BASE-REAL-1B: seed inicial de categorias globais e categorias do cartao.

Uso:
    .\venv\Scripts\python.exe scripts\seed\base_real_1b_seed_categorias.py

O seed e idempotente:
- Categoria de Despesa e global;
- palavras-chave seguem a Categoria de Despesa;
- Categoria do Cartao e criada apenas no perfil Pessoal;
- vinculos Categoria de Despesa -> Categoria do Cartao sao criados apenas no perfil Pessoal.
"""

from __future__ import annotations

import ipaddress
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.app import create_app
from backend.models import Categoria, CategoriaCartao, CategoriaCartaoDespesa, CategoriaPalavraChave, PerfilFinanceiro, db
from backend.services.categoria_palavra_chave_service import CategoriaPalavraChaveService
from backend.services.perfil_financeiro_service import PerfilFinanceiroService


REMOTE_MARKERS = ("digitalocean", "ondigitalocean", "do-user", "db.do-user")
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


CATEGORIAS = [
    ("Alimentacao", "Supermercado", "cart", "#2563eb", "supermercado, mercado, atacadao, atacadão, atacarejo, assai, assaí, carrefour, extra, bretas, tatico, tático, supermercado moreira"),
    ("Alimentacao", "Hortifruti / Verdurão", "food", "#16a34a", "verdurao, verdurão, hortifruti, feira, sacolao, sacolão, frutas, verduras, legumes"),
    ("Alimentacao", "Panificadora", "food", "#d97706", "panificadora, padaria, pao, pão, confeitaria, bakery"),
    ("Alimentacao", "Restaurantes / Delivery", "food", "#f97316", "restaurante, lanchonete, pizzaria, hamburgueria, ifood, delivery, aiqfome, comida"),
    ("Saude", "Saúde / Consultas", "health", "#dc2626", "consulta, medico, médico, clinica, clínica, hospital, laboratorio, laboratório, exame, exames"),
    ("Saude", "Farmácia", "health", "#16a34a", "farmacia, farmácia, drogaria, drogasil, raia, pague menos, medicamento, remedio, remédio"),
    ("Saude", "Odontologia", "health", "#0891b2", "dentista, odontologia, odontologico, odontológico, ortodontia, dental"),
    ("Saude", "Psicologia", "health", "#7c3aed", "psicologo, psicólogo, psicologia, terapia, psicanalise, psicanálise"),
    ("Moradia", "Moradia", "home", "#0f766e", "aluguel, condominio, condomínio, moradia, casa, apartamento"),
    ("Moradia", "Energia", "lightning", "#eab308", "energia, equatorial, enel, celg, conta de luz, luz"),
    ("Moradia", "Água / Saneamento", "receipt", "#0284c7", "agua, água, saneago, saneamento, esgoto"),
    ("Moradia", "Internet e Telefonia", "phone", "#2563eb", "internet, telefone, celular, vivo, claro, tim, oi, fibra, telecom"),
    ("Servicos", "Serviços domésticos", "tool", "#64748b", "diarista, faxina, domestica, doméstica, limpeza, passadeira"),
    ("Servicos", "Manutenção residencial", "tool", "#475569", "manutencao residencial, manutenção residencial, encanador, eletricista, pintura, pedreiro, marceneiro"),
    ("Servicos", "Serviços gerais", "tool", "#6b7280", "servico, serviço, manutencao, manutenção, instalacao, instalação, assistencia, assistência"),
    ("Mobilidade", "Combustível", "fuel", "#ef4444", "posto, combustivel, combustível, gasolina, etanol, diesel, shell, ipiranga, petrobras, abastecimento"),
    ("Mobilidade", "Transporte por App", "car", "#2563eb", "uber, 99, taxi, táxi, transporte app, corrida"),
    ("Mobilidade", "Estacionamento", "car", "#64748b", "estacionamento, parking, zona azul"),
    ("Mobilidade", "Manutenção de Veículo", "car", "#0f766e", "oficina, pneu, revisao, revisão, oleo, óleo, autopecas, autopeças, mecanica, mecânica"),
    ("Digital", "Assinaturas", "repeat", "#7c3aed", "assinatura, mensalidade, netflix, spotify, prime, amazon prime, disney, max, youtube, streaming"),
    ("Digital", "Software e IA", "briefcase", "#4f46e5", "openai, chatgpt, microsoft, google workspace, canva, software, ia, inteligencia artificial, inteligência artificial, saas"),
    ("Educacao", "Educação", "education", "#0891b2", "escola, faculdade, curso, matricula, matrícula, mensalidade escolar, livro, livros, treinamento"),
    ("Financeiro", "Impostos e Taxas", "receipt", "#b45309", "darf, dare, gru, imposto, taxa, tributo, iptu, ipva, iss, inss, irrf"),
    ("Financeiro", "Tarifas Bancárias", "bank", "#475569", "tarifa, anuidade, juros, encargo, banco, pacote de servicos, pacote de serviços"),
    ("Financeiro", "Transferências", "bank", "#2563eb", "transferencia, transferência, ted, doc, pix enviado, entre contas"),
    ("Empresa", "Empresa / Operacional", "briefcase", "#0f766e", "fornecedor, material escritorio, material escritório, contabilidade, contador, empresa, operacional"),
    ("Patrimonio", "Patrimônio / Bens Duráveis", "briefcase", "#7c3aed", "notebook, computador, cadeira, mesa, impressora, equipamento, monitor, ar condicionado, ar-condicionado"),
    ("Outros", "Outros", "tag", "#64748b", "outros, diversos, nao identificado, não identificado"),
]


CATEGORIAS_CARTAO_PESSOAL = [
    ("Supermercado", "Gastos mensais previsiveis de mercado", "#2563eb", "supermercado"),
    ("Farmácia", "Medicamentos e drogarias recorrentes", "#16a34a", "farmacia"),
    ("Verdurão", "Hortifruti, feira, verduras, legumes e frutas", "#22c55e", "verdurao"),
    ("Panificadora", "Padaria e compras recorrentes de panificadora", "#d97706", "padaria"),
    ("Mobilidade", "Combustivel, app, estacionamento e deslocamentos recorrentes", "#2563eb", "mobilidade"),
    ("Assinaturas", "Streaming, apps, SaaS e mensalidades recorrentes", "#7c3aed", "inteligencia-artificial"),
]


VINCULOS = [
    ("Supermercado", "Supermercado"),
    ("Farmácia", "Farmácia"),
    ("Hortifruti / Verdurão", "Verdurão"),
    ("Panificadora", "Panificadora"),
    ("Combustível", "Mobilidade"),
    ("Transporte por App", "Mobilidade"),
    ("Estacionamento", "Mobilidade"),
    ("Manutenção de Veículo", "Mobilidade"),
    ("Assinaturas", "Assinaturas"),
    ("Software e IA", "Assinaturas"),
]


def mascarar_url(url: str | None) -> str:
    if not url:
        return "(nao definida)"
    return re.sub(r"://([^:@]+:[^@]+@)", "://***:***@", url)


def validar_banco_local(url: str | None) -> tuple[str, str]:
    if not url:
        raise RuntimeError("SQLALCHEMY_DATABASE_URI/DATABASE_URL ausente.")
    url_lower = url.lower()
    if any(marker in url_lower for marker in REMOTE_MARKERS):
        raise RuntimeError("URL bloqueada: marcador remoto detectado.")

    parsed = urlparse(url)
    if parsed.scheme.startswith("sqlite"):
        return "sqlite-local", parsed.path or "(memoria)"

    host = parsed.hostname or ""
    host_lower = host.lower()
    if host_lower not in LOCAL_HOSTS:
        try:
            ip = ipaddress.ip_address(host_lower)
            if not ip.is_loopback:
                raise RuntimeError(f"Host de banco nao local bloqueado: {host}")
        except ValueError as exc:
            raise RuntimeError(f"Host de banco nao local bloqueado: {host}") from exc

    return host, (parsed.path or "").lstrip("/")


def palavras(texto: str) -> list[str]:
    vistas: set[str] = set()
    resultado: list[str] = []
    for item in texto.split(","):
        palavra = CategoriaPalavraChaveService.normalizar_palavra(item)
        if palavra and palavra not in vistas:
            vistas.add(palavra)
            resultado.append(palavra)
    return resultado


def upsert_categoria(grupo: str, nome: str, icone: str, cor: str) -> tuple[Categoria, str]:
    categoria = Categoria.query.filter_by(nome=nome).first()
    if categoria:
        categoria.perfil_financeiro_id = None
        categoria.descricao = categoria.descricao or f"Grupo: {grupo}"
        categoria.cor = categoria.cor or cor
        categoria.icone = categoria.icone or icone
        categoria.ativo = True
        return categoria, "reaproveitada"

    categoria = Categoria(
        perfil_financeiro_id=None,
        nome=nome,
        descricao=f"Grupo: {grupo}",
        cor=cor,
        icone=icone,
        ativo=True,
    )
    db.session.add(categoria)
    db.session.flush()
    return categoria, "criada"


def upsert_palavras(categoria: Categoria, lista: list[str]) -> dict[str, int]:
    criadas = 0
    reativadas = 0
    existentes = 0
    for palavra in lista:
        registro = CategoriaPalavraChave.query.filter_by(categoria_id=categoria.id, palavra=palavra).first()
        if registro:
            if not registro.ativo:
                registro.ativo = True
                reativadas += 1
            else:
                existentes += 1
            continue
        db.session.add(CategoriaPalavraChave(categoria_id=categoria.id, palavra=palavra, ativo=True))
        criadas += 1
    return {"criadas": criadas, "reativadas": reativadas, "existentes": existentes}


def upsert_categoria_cartao(perfil_id: int, nome: str, descricao: str, cor: str, icone: str) -> tuple[CategoriaCartao, str]:
    categoria = CategoriaCartao.query.filter_by(perfil_financeiro_id=perfil_id, nome=nome).first()
    if categoria:
        categoria.descricao = categoria.descricao or descricao
        categoria.cor = categoria.cor or cor
        categoria.icone = categoria.icone or icone
        categoria.ativo = True
        return categoria, "reaproveitada"
    categoria = CategoriaCartao(
        perfil_financeiro_id=perfil_id,
        nome=nome,
        descricao=descricao,
        cor=cor,
        icone=icone,
        ativo=True,
    )
    db.session.add(categoria)
    db.session.flush()
    return categoria, "criada"


def upsert_vinculo(perfil_id: int, categoria: Categoria, categoria_cartao: CategoriaCartao) -> str:
    conflito = CategoriaCartaoDespesa.query.filter(
        CategoriaCartaoDespesa.perfil_financeiro_id == perfil_id,
        CategoriaCartaoDespesa.categoria_id == categoria.id,
        CategoriaCartaoDespesa.categoria_cartao_id != categoria_cartao.id,
        CategoriaCartaoDespesa.ativo == True,  # noqa: E712
    ).first()
    if conflito:
        return "conflito_existente"

    vinculo = CategoriaCartaoDespesa.query.filter_by(
        perfil_financeiro_id=perfil_id,
        categoria_cartao_id=categoria_cartao.id,
        categoria_id=categoria.id,
    ).first()
    if vinculo:
        vinculo.ativo = True
        return "reaproveitado"

    db.session.add(CategoriaCartaoDespesa(
        perfil_financeiro_id=perfil_id,
        categoria_cartao_id=categoria_cartao.id,
        categoria_id=categoria.id,
        ativo=True,
    ))
    return "criado"


def main() -> int:
    app = create_app("development")
    app.config["SQLALCHEMY_ECHO"] = False
    db_url = app.config.get("SQLALCHEMY_DATABASE_URI") or os.getenv("DATABASE_URL")
    host, banco = validar_banco_local(db_url)

    print("BASE-REAL-1B - Seed inicial de categorias")
    print(f"Banco: {mascarar_url(db_url)}")
    print(f"Host validado: {host}")
    print(f"Database validado: {banco}")

    with app.app_context():
        db.engine.echo = False
        PerfilFinanceiroService.obter_ou_criar_perfis_iniciais()
        pessoal = PerfilFinanceiro.query.filter_by(nome="Pessoal").first()
        empresa = PerfilFinanceiro.query.filter_by(nome="Empresa").first()
        if not pessoal or not empresa:
            raise RuntimeError("Perfis Pessoal e Empresa sao obrigatorios.")

        categorias_por_nome: dict[str, Categoria] = {}
        status_categorias: dict[str, str] = {}
        resumo_palavras: dict[str, dict[str, int]] = {}

        for grupo, nome, icone, cor, palavras_csv in CATEGORIAS:
            categoria, status = upsert_categoria(grupo, nome, icone, cor)
            categorias_por_nome[nome] = categoria
            status_categorias[nome] = status
            resumo_palavras[nome] = upsert_palavras(categoria, palavras(palavras_csv))

        cartoes_por_nome: dict[str, CategoriaCartao] = {}
        status_cartoes: dict[str, str] = {}
        for nome, descricao, cor, icone in CATEGORIAS_CARTAO_PESSOAL:
            categoria_cartao, status = upsert_categoria_cartao(pessoal.id, nome, descricao, cor, icone)
            cartoes_por_nome[nome] = categoria_cartao
            status_cartoes[nome] = status

        status_vinculos: dict[tuple[str, str], str] = {}
        for categoria_nome, cartao_nome in VINCULOS:
            status_vinculos[(categoria_nome, cartao_nome)] = upsert_vinculo(
                pessoal.id,
                categorias_por_nome[categoria_nome],
                cartoes_por_nome[cartao_nome],
            )

        db.session.commit()

        empresa_cartoes = CategoriaCartao.query.filter_by(perfil_financeiro_id=empresa.id).count()
        total_categorias = Categoria.query.count()
        total_palavras = CategoriaPalavraChave.query.filter_by(ativo=True).count()

        print("[OK] Seed concluido.")
        print(f"Categorias de Despesa globais: {total_categorias}")
        print(f"Palavras-chave ativas: {total_palavras}")
        print(f"Categorias do Cartao no Pessoal: {CategoriaCartao.query.filter_by(perfil_financeiro_id=pessoal.id).count()}")
        print(f"Categorias do Cartao no Empresa: {empresa_cartoes}")
        print("")
        print("Categorias de Despesa:")
        for nome in [item[1] for item in CATEGORIAS]:
            print(f"  - {nome}: {status_categorias[nome]}")
        print("")
        print("Palavras-chave:")
        for nome, resumo in resumo_palavras.items():
            print(f"  - {nome}: +{resumo['criadas']} / reativadas {resumo['reativadas']} / existentes {resumo['existentes']}")
        print("")
        print("Categorias do Cartao - Pessoal:")
        for nome, status in status_cartoes.items():
            print(f"  - {nome}: {status}")
        print("")
        print("Vinculos:")
        for (categoria_nome, cartao_nome), status in status_vinculos.items():
            print(f"  - {categoria_nome} -> {cartao_nome}: {status}")

        if empresa_cartoes != 0:
            print("[AVISO] Perfil Empresa possui Categorias do Cartao preexistentes; o seed nao criou novas.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
