from __future__ import annotations

try:
    from backend.models import Categoria
except ImportError:
    from models import Categoria


NOME_CATEGORIA_PADRAO_VEICULOS = 'Transporte'


def get_categoria_padrao_veiculos() -> int:
    """
    Retorna o ID da categoria padrão do módulo de veículos.

    Regra (ajuste final):
    - Todas as despesas de veículos usam a categoria "Transporte".
    - Se não existir, falha de forma explícita (sem fallback silencioso).
    """
    cat = Categoria.query.filter_by(nome=NOME_CATEGORIA_PADRAO_VEICULOS).first()
    if not cat:
        raise ValueError('Categoria padrão "Transporte" não encontrada. Rode o seed de categorias.')
    return cat.id

