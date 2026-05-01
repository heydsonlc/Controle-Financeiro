"""
Seed de demonstração para homologação visual — DEV-SEED-1.

Cria dados fictícios com prefixo DEV_DEMO_ em ambiente local/dev.
Idempotente: reutiliza registros existentes com o mesmo nome/prefixo.

Uso:
    python scripts/seed_demo_dev.py

Restrições:
- Só roda se DATABASE_URL aponta para localhost / 127.0.0.1 / ::1
- Não apaga dados existentes fora do prefixo DEV_DEMO_
- Não deve ser executado em produção ou DigitalOcean
"""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app import create_app
from backend.models import (
    db,
    Categoria,
    ContaBancaria,
    ItemDespesa,
    ConfigAgregador,
    ItemAgregado,
    OrcamentoAgregado,
    LancamentoAgregado,
    Orcamento,
    Conta,
    ItemReceita,
    ReceitaOrcamento,
    ReceitaRealizada,
)


PREFIX = "DEV_DEMO_"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _primeiro_dia_mes(ano: int, mes: int) -> date:
    return date(ano, mes, 1)


def _proximo_mes(d: date) -> date:
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)


def _get_or_create(model, filtro: dict, defaults: dict | None = None):
    """Retorna instância existente ou cria nova. Retorna (instance, criada)."""
    obj = model.query.filter_by(**filtro).first()
    if obj:
        return obj, False
    dados = {**filtro, **(defaults or {})}
    obj = model(**dados)
    db.session.add(obj)
    db.session.flush()
    return obj, True


def _validar_url_local(url: str | None) -> None:
    """Aborta se a URL não for local."""
    if url is None:
        return
    url_lower = url.lower()
    locais = ("localhost", "127.0.0.1", "::1", "@localhost", "@127.0.0.1")
    externos = ("digitalocean", "ondigitalocean", "do-user", "db.do-user")

    if any(ext in url_lower for ext in externos):
        print("[ERRO] DATABASE_URL aponta para DigitalOcean ou serviço externo. Abortando.")
        sys.exit(1)

    if not any(loc in url_lower for loc in locais):
        print("[AVISO] DATABASE_URL não parece apontar para localhost.")
        print("        Certifique-se de estar em ambiente local/dev antes de continuar.")
        resp = input("Continuar? [s/N] ").strip().lower()
        if resp != "s":
            print("Abortado pelo usuário.")
            sys.exit(0)


def _mascarar_url(url: str | None) -> str:
    if url is None:
        return "(SQLite fallback local)"
    import re
    return re.sub(r"://([^:@]+:[^@]+@)", "://***:***@", url)


# ---------------------------------------------------------------------------
# Seções do seed
# ---------------------------------------------------------------------------

def seed_categorias() -> dict[str, Categoria]:
    nomes = [
        "Moradia", "Alimentação", "Transporte",
        "Saúde", "Lazer", "Assinaturas", "Receitas", "Serviços",
    ]
    resultado: dict[str, Categoria] = {}
    for nome in nomes:
        chave = PREFIX + nome
        cat, criada = _get_or_create(Categoria, {"nome": chave}, {"ativo": True, "cor": "#6c757d"})
        resultado[nome] = cat
        if criada:
            print(f"  [+] Categoria: {chave}")
        else:
            print(f"  [=] Categoria já existe: {chave}")
    return resultado


def seed_conta_bancaria() -> ContaBancaria:
    nome = PREFIX + "Conta Principal"
    conta, criada = _get_or_create(
        ContaBancaria,
        {"nome": nome},
        {
            "instituicao": "Banco Demo",
            "tipo": "Conta Corrente",
            "saldo_inicial": 5000.00,
            "saldo_atual": 5000.00,
            "status": "ATIVO",
            "cor_display": "#3b82f6",
        },
    )
    if criada:
        print(f"  [+] Conta bancária: {nome} (saldo R$5.000,00)")
    else:
        print(f"  [=] Conta bancária já existe: {nome}")
    return conta


def seed_receitas(conta: ContaBancaria, competencia: date) -> None:
    nome_fonte = PREFIX + "Salário"
    fonte, criada = _get_or_create(
        ItemReceita,
        {"nome": nome_fonte},
        {
            "tipo": "SALARIO_FIXO",
            "valor_base_mensal": 8000.00,
            "dia_previsto_pagamento": 5,
            "conta_bancaria_id": conta.id,
            "recorrente": True,
            "ativo": True,
        },
    )
    if criada:
        print(f"  [+] Fonte de receita: {nome_fonte}")
    else:
        print(f"  [=] Fonte de receita já existe: {nome_fonte}")

    orc, criado_orc = _get_or_create(
        ReceitaOrcamento,
        {"item_receita_id": fonte.id, "mes_referencia": competencia},
        {
            "valor_esperado": 8000.00,
            "periodicidade": "MENSAL_FIXA",
        },
    )
    if criado_orc:
        print(f"  [+] Orçamento de receita: {competencia.strftime('%Y-%m')}")
    else:
        print(f"  [=] Orçamento de receita já existe: {competencia.strftime('%Y-%m')}")

    real, criada_real = _get_or_create(
        ReceitaRealizada,
        {
            "item_receita_id": fonte.id,
            "mes_referencia": competencia,
            "conta_bancaria_id": conta.id,
        },
        {
            "data_recebimento": competencia.replace(day=5),
            "valor_recebido": 8000.00,
            "descricao": f"{PREFIX}Salário {competencia.strftime('%m/%Y')}",
        },
    )
    if criada_real:
        print(f"  [+] Receita realizada: R$8.000,00 em {competencia.strftime('%m/%Y')}")
    else:
        print(f"  [=] Receita realizada já existe: {competencia.strftime('%m/%Y')}")


def seed_cartao(categorias: dict[str, Categoria], competencia: date) -> None:
    nome_cartao = PREFIX + "Cartão Principal"
    cartao, criado = _get_or_create(
        ItemDespesa,
        {"nome": nome_cartao, "tipo": "Agregador"},
        {"ativo": True},
    )
    if criado:
        cfg = ConfigAgregador(
            item_despesa_id=cartao.id,
            dia_fechamento=10,
            dia_vencimento=15,
            limite_credito=4000.00,
        )
        db.session.add(cfg)
        db.session.flush()
        print(f"  [+] Cartão: {nome_cartao} (fecha 10, vence 15, limite R$4.000)")
    else:
        print(f"  [=] Cartão já existe: {nome_cartao}")

    cat_mercado = categorias["Alimentação"]
    cat_lazer = categorias["Lazer"]
    cat_assin = categorias["Assinaturas"]

    ia_mercado, c1 = _get_or_create(
        ItemAgregado,
        {"item_despesa_id": cartao.id, "nome": PREFIX + "Mercado"},
        {"ativo": True},
    )
    ia_streaming, c2 = _get_or_create(
        ItemAgregado,
        {"item_despesa_id": cartao.id, "nome": PREFIX + "Assinaturas"},
        {"ativo": True},
    )
    ia_lazer, c3 = _get_or_create(
        ItemAgregado,
        {"item_despesa_id": cartao.id, "nome": PREFIX + "Lazer"},
        {"ativo": True},
    )
    if any([c1, c2, c3]):
        print(f"  [+] Categorias internas do cartão criadas")

    # Orçamentos das categorias
    for ia, teto in [(ia_mercado, 600.00), (ia_streaming, 100.00), (ia_lazer, 300.00)]:
        _get_or_create(
            OrcamentoAgregado,
            {"item_agregado_id": ia.id, "mes_referencia": competencia},
            {
                "valor_teto": teto,
                "vigencia_inicio": competencia,
                "ativo": True,
            },
        )

    # Lançamentos no cartão
    lancamentos = [
        {
            "descricao": PREFIX + "Supermercado",
            "valor": 450.00,
            "item_agregado_id": ia_mercado.id,
            "categoria_id": cat_mercado.id,
            "data_compra": competencia.replace(day=3),
            "mes_fatura": competencia,
            "numero_parcela": 1,
            "total_parcelas": 1,
        },
        {
            "descricao": PREFIX + "Streaming",
            "valor": 59.90,
            "item_agregado_id": ia_streaming.id,
            "categoria_id": cat_assin.id,
            "data_compra": competencia.replace(day=5),
            "mes_fatura": competencia,
            "numero_parcela": 1,
            "total_parcelas": 1,
        },
    ]

    # Compra parcelada: 3x R$300 em competências sucessivas
    prox = competencia
    for i in range(1, 4):
        lancamentos.append({
            "descricao": PREFIX + "Compra Parcelada",
            "valor": 300.00,
            "item_agregado_id": ia_lazer.id,
            "categoria_id": cat_lazer.id,
            "data_compra": competencia.replace(day=8),
            "mes_fatura": prox,
            "numero_parcela": i,
            "total_parcelas": 3,
        })
        prox = _proximo_mes(prox)

    for dados in lancamentos:
        existente = LancamentoAgregado.query.filter_by(
            descricao=dados["descricao"],
            mes_fatura=dados["mes_fatura"],
            numero_parcela=dados["numero_parcela"],
            cartao_id=cartao.id,
        ).first()
        if existente:
            print(f"  [=] Lançamento já existe: {dados['descricao']} {dados['mes_fatura'].strftime('%Y-%m')} {dados['numero_parcela']}/{dados['total_parcelas']}")
            continue
        lanc = LancamentoAgregado(cartao_id=cartao.id, **dados)
        db.session.add(lanc)
        print(f"  [+] Lançamento: {dados['descricao']} R${dados['valor']:.2f} {dados['mes_fatura'].strftime('%Y-%m')} {dados['numero_parcela']}/{dados['total_parcelas']}")


def seed_despesas(categorias: dict[str, Categoria], competencia: date) -> None:
    cat_moradia = categorias["Moradia"]
    cat_saude = categorias["Saúde"]

    # 1. Despesa recorrente mensal — Internet
    item_internet, criado = _get_or_create(
        ItemDespesa,
        {"nome": PREFIX + "Internet", "tipo": "Simples"},
        {
            "categoria_id": cat_moradia.id,
            "ativo": True,
            "recorrente": True,
            "tipo_recorrencia": "mensal",
            "valor": 120.00,
        },
    )
    if criado:
        print(f"  [+] Despesa recorrente mensal: {PREFIX}Internet R$120,00")
    else:
        print(f"  [=] Despesa recorrente já existe: {PREFIX}Internet")

    _get_or_create(
        Orcamento,
        {"item_despesa_id": item_internet.id, "mes_referencia": competencia},
        {"valor_planejado": 120.00},
    )

    conta_internet, c = _get_or_create(
        Conta,
        {"item_despesa_id": item_internet.id, "mes_referencia": competencia},
        {
            "descricao": PREFIX + "Internet",
            "valor": 120.00,
            "data_vencimento": competencia.replace(day=15),
            "status_pagamento": "Pendente",
        },
    )
    if c:
        print(f"  [+] Conta: {PREFIX}Internet vence {competencia.replace(day=15)}")
    else:
        print(f"  [=] Conta já existe: {PREFIX}Internet {competencia.strftime('%Y-%m')}")

    # 2. Despesa recorrente quinzenal — Diarista
    item_diarista, criado2 = _get_or_create(
        ItemDespesa,
        {"nome": PREFIX + "Diarista", "tipo": "Simples"},
        {
            "categoria_id": cat_moradia.id,
            "ativo": True,
            "recorrente": True,
            "tipo_recorrencia": "a_cada_2_semanas",
            "valor": 220.00,
        },
    )
    if criado2:
        print(f"  [+] Despesa recorrente quinzenal: {PREFIX}Diarista R$220,00")
    else:
        print(f"  [=] Despesa recorrente já existe: {PREFIX}Diarista")

    _get_or_create(
        Orcamento,
        {"item_despesa_id": item_diarista.id, "mes_referencia": competencia},
        {"valor_planejado": 440.00},
    )

    # 3. Despesa pontual pendente — Consulta Médica
    item_consulta, criado3 = _get_or_create(
        ItemDespesa,
        {"nome": PREFIX + "Consulta Médica", "tipo": "Simples"},
        {
            "categoria_id": cat_saude.id,
            "ativo": True,
            "recorrente": False,
            "valor": 300.00,
        },
    )
    if criado3:
        print(f"  [+] Despesa pontual: {PREFIX}Consulta Médica R$300,00")
    else:
        print(f"  [=] Despesa pontual já existe: {PREFIX}Consulta Médica")

    _get_or_create(
        Orcamento,
        {"item_despesa_id": item_consulta.id, "mes_referencia": competencia},
        {"valor_planejado": 300.00},
    )

    conta_consulta, c3 = _get_or_create(
        Conta,
        {"item_despesa_id": item_consulta.id, "mes_referencia": competencia},
        {
            "descricao": PREFIX + "Consulta Médica",
            "valor": 300.00,
            "data_vencimento": competencia.replace(day=20),
            "status_pagamento": "Pendente",
        },
    )
    if c3:
        print(f"  [+] Conta: {PREFIX}Consulta Médica (Pendente)")
    else:
        print(f"  [=] Conta já existe: {PREFIX}Consulta Médica {competencia.strftime('%Y-%m')}")

    # 4. Despesa paga — Conta de Luz
    item_luz, criado4 = _get_or_create(
        ItemDespesa,
        {"nome": PREFIX + "Conta de Luz", "tipo": "Simples"},
        {
            "categoria_id": cat_moradia.id,
            "ativo": True,
            "recorrente": True,
            "tipo_recorrencia": "mensal",
            "valor": 280.00,
        },
    )
    if criado4:
        print(f"  [+] Despesa: {PREFIX}Conta de Luz R$280,00")
    else:
        print(f"  [=] Despesa já existe: {PREFIX}Conta de Luz")

    _get_or_create(
        Orcamento,
        {"item_despesa_id": item_luz.id, "mes_referencia": competencia},
        {"valor_planejado": 280.00},
    )

    conta_luz, c4 = _get_or_create(
        Conta,
        {"item_despesa_id": item_luz.id, "mes_referencia": competencia},
        {
            "descricao": PREFIX + "Conta de Luz",
            "valor": 280.00,
            "data_vencimento": competencia.replace(day=10),
            "data_pagamento": competencia.replace(day=9),
            "status_pagamento": "Pago",
        },
    )
    if c4:
        print(f"  [+] Conta: {PREFIX}Conta de Luz (Pago)")
    else:
        print(f"  [=] Conta já existe: {PREFIX}Conta de Luz {competencia.strftime('%Y-%m')}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    db_url = os.environ.get("DATABASE_URL") or os.environ.get("SQLALCHEMY_DATABASE_URI")
    _validar_url_local(db_url)

    print(f"\n=== DEV-SEED-1 — Massa de Demonstração ===")
    print(f"DATABASE_URL: {_mascarar_url(db_url)}")

    hoje = date.today()
    competencia = _primeiro_dia_mes(hoje.year, hoje.month)
    print(f"Competência base: {competencia.strftime('%Y-%m')}\n")

    app = create_app("development")
    with app.app_context():
        print("--- Categorias ---")
        categorias = seed_categorias()
        db.session.commit()

        print("\n--- Conta Bancária ---")
        conta = seed_conta_bancaria()
        db.session.commit()

        print("\n--- Receitas ---")
        seed_receitas(conta, competencia)
        db.session.commit()

        print("\n--- Cartão de Crédito ---")
        seed_cartao(categorias, competencia)
        db.session.commit()

        print("\n--- Despesas ---")
        seed_despesas(categorias, competencia)
        db.session.commit()

        print("\n=== Seed concluído com sucesso ===")
        print(f"  Categorias DEV_DEMO_: {Categoria.query.filter(Categoria.nome.like(PREFIX + '%')).count()}")
        print(f"  Contas bancárias DEV_DEMO_: {ContaBancaria.query.filter(ContaBancaria.nome.like(PREFIX + '%')).count()}")
        print(f"  Itens despesa DEV_DEMO_: {ItemDespesa.query.filter(ItemDespesa.nome.like(PREFIX + '%')).count()}")
        print(f"  Lançamentos DEV_DEMO_: {LancamentoAgregado.query.filter(LancamentoAgregado.descricao.like(PREFIX + '%')).count()}")
        print(f"  Receitas realizadas DEV_DEMO_: {ReceitaRealizada.query.filter(ReceitaRealizada.descricao.like(PREFIX + '%')).count()}")


if __name__ == "__main__":
    main()
