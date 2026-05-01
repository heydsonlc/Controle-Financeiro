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
import re
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app import create_app
from backend.models import (
    db,
    Categoria,
    ContaBancaria,
    GrupoAgregador,
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
from backend.services.financiamento_service import FinanciamentoService


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


def _mes_anterior(d: date) -> date:
    if d.month == 1:
        return date(d.year - 1, 12, 1)
    return date(d.year, d.month - 1, 1)


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

    _get_or_create(
        ReceitaOrcamento,
        {"item_receita_id": fonte.id, "mes_referencia": competencia},
        {"valor_esperado": 8000.00, "periodicidade": "MENSAL_FIXA"},
    )

    real, criada_real = _get_or_create(
        ReceitaRealizada,
        {"item_receita_id": fonte.id, "mes_referencia": competencia, "conta_bancaria_id": conta.id},
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


def seed_grupo_supermercado() -> GrupoAgregador:
    """
    Cria GrupoAgregador para consolidar gastos de supermercado entre cartões.
    Permite que categorias 'Mercado' de diferentes cartões apareçam juntas.
    """
    nome = PREFIX + "Supermercado (Grupo)"
    grupo, criado = _get_or_create(
        GrupoAgregador,
        {"nome": nome},
        {"descricao": "Gastos de supermercado consolidados — demo", "ativo": True},
    )
    if criado:
        print(f"  [+] GrupoAgregador: {nome}")
    else:
        print(f"  [=] GrupoAgregador já existe: {nome}")
    return grupo


def seed_cartao(
    categorias: dict[str, Categoria],
    grupo_supermercado: GrupoAgregador,
    competencia: date,
) -> tuple[ItemDespesa, ItemAgregado, ItemAgregado, ItemAgregado]:
    """
    Retorna (cartao, ia_mercado, ia_streaming, ia_lazer).
    ia_mercado é vinculado ao GrupoAgregador de supermercado.
    """
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

    # ia_mercado vinculado ao GrupoAgregador — aparece consolidado com outros cartões
    ia_mercado, c1 = _get_or_create(
        ItemAgregado,
        {"item_despesa_id": cartao.id, "nome": PREFIX + "Mercado"},
        {"ativo": True, "grupo_agregador_id": grupo_supermercado.id},
    )
    if c1:
        print(f"  [+] Categoria interna: {PREFIX}Mercado (grupo: {grupo_supermercado.nome})")
    else:
        # Atualiza grupo se já existia sem ele
        if ia_mercado.grupo_agregador_id != grupo_supermercado.id:
            ia_mercado.grupo_agregador_id = grupo_supermercado.id
            db.session.flush()
            print(f"  [~] Categoria {PREFIX}Mercado: grupo atualizado")
        else:
            print(f"  [=] Categoria interna já existe: {PREFIX}Mercado")

    ia_streaming, c2 = _get_or_create(
        ItemAgregado,
        {"item_despesa_id": cartao.id, "nome": PREFIX + "Assinaturas"},
        {"ativo": True},
    )
    if c2:
        print(f"  [+] Categoria interna: {PREFIX}Assinaturas")
    else:
        print(f"  [=] Categoria interna já existe: {PREFIX}Assinaturas")

    ia_lazer, c3 = _get_or_create(
        ItemAgregado,
        {"item_despesa_id": cartao.id, "nome": PREFIX + "Lazer"},
        {"ativo": True},
    )
    if c3:
        print(f"  [+] Categoria interna: {PREFIX}Lazer")
    else:
        print(f"  [=] Categoria interna já existe: {PREFIX}Lazer")

    # Orçamentos das categorias
    for ia, teto in [(ia_mercado, 600.00), (ia_streaming, 100.00), (ia_lazer, 300.00)]:
        _get_or_create(
            OrcamentoAgregado,
            {"item_agregado_id": ia.id, "mes_referencia": competencia},
            {"valor_teto": teto, "vigencia_inicio": competencia, "ativo": True},
        )

    # --- Lançamentos avulsos no cartão ---
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
            "descricao": PREFIX + "Supermercado 2ª ida",
            "valor": 310.00,
            "item_agregado_id": ia_mercado.id,
            "categoria_id": cat_mercado.id,
            "data_compra": competencia.replace(day=17),
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

    # Compra parcelada 3x: lança nas 3 competências
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
        db.session.add(LancamentoAgregado(cartao_id=cartao.id, **dados))
        print(f"  [+] Lançamento: {dados['descricao']} R${dados['valor']:.2f} {dados['mes_fatura'].strftime('%Y-%m')} {dados['numero_parcela']}/{dados['total_parcelas']}")

    return cartao, ia_mercado, ia_streaming, ia_lazer


def seed_despesas(
    categorias: dict[str, Categoria],
    cartao: ItemDespesa,
    ia_servicos: ItemAgregado | None,
    competencia: date,
) -> None:
    """
    ia_servicos: categoria interna do cartão para lançar passadeira.
    Se None, passadeira é criada como despesa simples sem cartão.
    """
    cat_moradia = categorias["Moradia"]
    cat_saude = categorias["Saúde"]
    cat_servicos = categorias["Serviços"]

    # 1. Internet — mensal
    item_internet, criado = _get_or_create(
        ItemDespesa,
        {"nome": PREFIX + "Internet", "tipo": "Simples"},
        {"categoria_id": cat_moradia.id, "ativo": True, "recorrente": True, "tipo_recorrencia": "mensal", "valor": 120.00},
    )
    if criado:
        print(f"  [+] Despesa recorrente mensal: {PREFIX}Internet R$120,00")
    else:
        print(f"  [=] Despesa recorrente já existe: {PREFIX}Internet")

    _get_or_create(Orcamento, {"item_despesa_id": item_internet.id, "mes_referencia": competencia}, {"valor_planejado": 120.00})
    _get_or_create(
        Conta,
        {"item_despesa_id": item_internet.id, "mes_referencia": competencia},
        {"descricao": PREFIX + "Internet", "valor": 120.00, "data_vencimento": competencia.replace(day=15), "status_pagamento": "Pendente"},
    )

    # 2. Passadeira — quinzenal, paga via cartão (terças, semana sim/não)
    #    O sistema representa isso como recorrência a_cada_2_semanas paga com cartão.
    #    Lançamos também as contas do mês atual (2 ocorrências: ~dia 6 e ~dia 20).
    item_passadeira, criado2 = _get_or_create(
        ItemDespesa,
        {"nome": PREFIX + "Passadeira", "tipo": "Simples"},
        {
            "categoria_id": cat_servicos.id,
            "ativo": True,
            "recorrente": True,
            "tipo_recorrencia": "a_cada_2_semanas",
            "valor": 150.00,
            "meio_pagamento": "cartao",
            "cartao_id": cartao.id,
        },
    )
    if criado2:
        print(f"  [+] Despesa recorrente quinzenal (cartão): {PREFIX}Passadeira R$150,00 — terças alternadas")
    else:
        print(f"  [=] Despesa recorrente já existe: {PREFIX}Passadeira")

    # Orçamento: 2 ocorrências no mês = R$300
    _get_or_create(Orcamento, {"item_despesa_id": item_passadeira.id, "mes_referencia": competencia}, {"valor_planejado": 300.00})

    # Lançamentos no cartão representando as duas terças do mês
    # Encontra as duas primeiras terças-feiras (weekday=1) do mês, semanas ímpares
    cat_servicos_cat = categorias["Serviços"]
    terca1 = competencia + timedelta(days=(1 - competencia.weekday() + 7) % 7)  # primeira terça ≥ dia 1
    terca2 = terca1 + timedelta(weeks=2)  # semana sim/não → +2 semanas

    for idx, dia_compra in enumerate([terca1, terca2], start=1):
        if dia_compra.month != competencia.month:
            break
        mes_fatura = competencia if dia_compra.day <= 10 else _proximo_mes(competencia)
        existente = LancamentoAgregado.query.filter_by(
            descricao=PREFIX + "Passadeira",
            data_compra=dia_compra,
            cartao_id=cartao.id,
        ).first()
        if existente:
            print(f"  [=] Lançamento passadeira já existe: {dia_compra}")
            continue
        db.session.add(LancamentoAgregado(
            cartao_id=cartao.id,
            item_agregado_id=ia_servicos.id if ia_servicos else None,
            categoria_id=cat_servicos_cat.id,
            descricao=PREFIX + "Passadeira",
            valor=150.00,
            data_compra=dia_compra,
            mes_fatura=mes_fatura,
            numero_parcela=1,
            total_parcelas=1,
            is_recorrente=True,
            item_despesa_id=item_passadeira.id,
        ))
        print(f"  [+] Lancamento passadeira: {dia_compra} fatura {mes_fatura.strftime('%Y-%m')}")

    # 3. Consulta Médica — pontual, pendente
    item_consulta, criado3 = _get_or_create(
        ItemDespesa,
        {"nome": PREFIX + "Consulta Médica", "tipo": "Simples"},
        {"categoria_id": cat_saude.id, "ativo": True, "recorrente": False, "valor": 300.00},
    )
    if criado3:
        print(f"  [+] Despesa pontual: {PREFIX}Consulta Médica R$300,00")
    else:
        print(f"  [=] Despesa pontual já existe: {PREFIX}Consulta Médica")

    _get_or_create(Orcamento, {"item_despesa_id": item_consulta.id, "mes_referencia": competencia}, {"valor_planejado": 300.00})
    _get_or_create(
        Conta,
        {"item_despesa_id": item_consulta.id, "mes_referencia": competencia},
        {"descricao": PREFIX + "Consulta Médica", "valor": 300.00, "data_vencimento": competencia.replace(day=20), "status_pagamento": "Pendente"},
    )

    # 4. Conta de Luz — mensal, já paga
    item_luz, criado4 = _get_or_create(
        ItemDespesa,
        {"nome": PREFIX + "Conta de Luz", "tipo": "Simples"},
        {"categoria_id": cat_moradia.id, "ativo": True, "recorrente": True, "tipo_recorrencia": "mensal", "valor": 280.00},
    )
    if criado4:
        print(f"  [+] Despesa mensal: {PREFIX}Conta de Luz R$280,00")
    else:
        print(f"  [=] Despesa já existe: {PREFIX}Conta de Luz")

    _get_or_create(Orcamento, {"item_despesa_id": item_luz.id, "mes_referencia": competencia}, {"valor_planejado": 280.00})
    _get_or_create(
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


def seed_financiamento_habitacional(competencia: date) -> None:
    """
    Cria financiamento habitacional SAC com seguro mensal fixo.
    Simula contrato com ~180 meses restantes, já com algumas parcelas pagas.
    Usa FinanciamentoService.criar_financiamento para gerar parcelas corretamente.
    """
    nome = PREFIX + "Financiamento Habitacional"

    # Idempotência: verifica via ItemDespesa (o service cria automaticamente)
    from backend.models import Financiamento
    existente = Financiamento.query.filter_by(nome=nome).first()
    if existente:
        total_parcelas = existente.parcelas.count()
        print(f"  [=] Financiamento já existe: {nome} ({total_parcelas} parcelas)")
        return

    # Contrato: firmado há 2 anos (24 parcelas já pagas), prazo total 240 meses (20 anos)
    # Parcela 1 = 2 anos atrás; competência atual está na parcela ~25
    data_contrato = date(competencia.year - 2, competencia.month, 1)
    data_primeira_parcela = date(data_contrato.year, data_contrato.month + 1, 5) \
        if data_contrato.month < 12 \
        else date(data_contrato.year + 1, 1, 5)

    dados = {
        "nome": nome,
        "produto": "SFH",
        "sistema_amortizacao": "SAC",
        "valor_financiado": 350000.00,
        "prazo_total_meses": 240,
        "taxa_juros_nominal_anual": 9.50,   # % ao ano
        "indexador_saldo": "TR",
        "data_contrato": data_contrato,
        "data_primeira_parcela": data_primeira_parcela,
        "taxa_administracao_fixa": 25.00,
        # Sistema atual usa FinanciamentoSeguroVigencia; passar vigência junto
        "vigencias_seguro": [
            {
                "competencia_inicio": data_primeira_parcela,
                "valor_mensal": 185.00,
            }
        ],
    }

    try:
        financiamento = FinanciamentoService.criar_financiamento(dados)
        total = financiamento.parcelas.count()
        print(f"  [+] Financiamento: {nome} — SAC R$350.000 / 240 meses / 9,5% a.a. ({total} parcelas geradas)")

        # Marcar as primeiras 24 parcelas como pagas (simulando 2 anos de histórico)
        parcelas_pagas = financiamento.parcelas.order_by('numero_parcela').limit(24).all()
        for parcela in parcelas_pagas:
            parcela.pago = True
            parcela.data_pagamento = parcela.data_vencimento
            if parcela.conta:
                parcela.conta.status_pagamento = "Pago"
                parcela.conta.data_pagamento = parcela.data_vencimento

        db.session.flush()
        print(f"  [~] {len(parcelas_pagas)} parcelas marcadas como pagas (histórico 2 anos)")

    except Exception as exc:
        print(f"  [!] Erro ao criar financiamento: {exc}")
        db.session.rollback()
        raise


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    db_url = os.environ.get("DATABASE_URL") or os.environ.get("SQLALCHEMY_DATABASE_URI")
    _validar_url_local(db_url)

    print(f"\n=== DEV-SEED-1 — Massa de Demonstração (v2) ===")
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

        print("\n--- Grupo Agregador (Supermercado) ---")
        grupo_supermercado = seed_grupo_supermercado()
        db.session.commit()

        print("\n--- Cartão de Crédito ---")
        cartao, ia_mercado, ia_streaming, ia_lazer = seed_cartao(categorias, grupo_supermercado, competencia)

        # Cria categoria interna "Serviços" no cartão para lançamentos de passadeira
        ia_servicos, criado_sv = _get_or_create(
            ItemAgregado,
            {"item_despesa_id": cartao.id, "nome": PREFIX + "Serviços"},
            {"ativo": True},
        )
        if criado_sv:
            print(f"  [+] Categoria interna: {PREFIX}Serviços (para passadeira)")
        _get_or_create(
            OrcamentoAgregado,
            {"item_agregado_id": ia_servicos.id, "mes_referencia": competencia},
            {"valor_teto": 350.00, "vigencia_inicio": competencia, "ativo": True},
        )
        db.session.commit()

        print("\n--- Despesas ---")
        seed_despesas(categorias, cartao, ia_servicos, competencia)
        db.session.commit()

        print("\n--- Financiamento Habitacional ---")
        seed_financiamento_habitacional(competencia)
        db.session.commit()

        # --- Resumo ---
        from backend.models import Financiamento
        print("\n=== Seed concluído com sucesso ===")
        print(f"  Categorias DEV_DEMO_:        {Categoria.query.filter(Categoria.nome.like(PREFIX + '%')).count()}")
        print(f"  Contas bancárias DEV_DEMO_:  {ContaBancaria.query.filter(ContaBancaria.nome.like(PREFIX + '%')).count()}")
        print(f"  Grupos agregadores DEV_DEMO_:{GrupoAgregador.query.filter(GrupoAgregador.nome.like(PREFIX + '%')).count()}")
        print(f"  Itens despesa DEV_DEMO_:     {ItemDespesa.query.filter(ItemDespesa.nome.like(PREFIX + '%')).count()}")
        print(f"  Lançamentos DEV_DEMO_:       {LancamentoAgregado.query.filter(LancamentoAgregado.descricao.like(PREFIX + '%')).count()}")
        print(f"  Receitas realizadas DEV_DEMO_:{ReceitaRealizada.query.filter(ReceitaRealizada.descricao.like(PREFIX + '%')).count()}")
        print(f"  Financiamentos DEV_DEMO_:    {Financiamento.query.filter(Financiamento.nome.like(PREFIX + '%')).count()}")


if __name__ == "__main__":
    main()
