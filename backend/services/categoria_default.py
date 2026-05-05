from __future__ import annotations

try:
    from backend.models import Categoria
    from backend.services.perfil_financeiro_service import PerfilFinanceiroService
except ImportError:
    from models import Categoria
    from services.perfil_financeiro_service import PerfilFinanceiroService


NOME_CATEGORIA_PADRAO_VEICULOS = 'Mobilidade'


def get_categoria_padrao_veiculos() -> int:
    """
    Retorna o ID da categoria padrão do módulo de veículos.

    Regra: todas as despesas de mobilidade usam a categoria "Mobilidade".
    Se não existir, falha de forma explícita (sem fallback silencioso).
    Execute o script scripts/sql/veic_homolog_2_mobilidade.sql para criá-la.
    """
    cat = PerfilFinanceiroService.aplicar_perfil_query(
        Categoria.query, Categoria
    ).filter_by(nome=NOME_CATEGORIA_PADRAO_VEICULOS).first()
    if not cat:
        raise ValueError('Categoria padrão "Mobilidade" não encontrada. Execute scripts/sql/veic_homolog_2_mobilidade.sql.')
    return cat.id
