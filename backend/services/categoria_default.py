from __future__ import annotations

try:
    from backend.models import Categoria
except ImportError:
    from models import Categoria


NOME_CATEGORIA_PADRAO_VEICULOS = 'Mobilidade'


def get_categoria_padrao_veiculos() -> int:
    """
    Retorna o ID da categoria padrão do módulo de veículos.

    Categoria de Despesa é global — sem filtro por perfil.
    Se não existir, falha de forma explícita (sem fallback silencioso).
    Execute o script scripts/sql/veic_homolog_2_mobilidade.sql para criá-la.
    """
    cat = Categoria.query.filter_by(nome=NOME_CATEGORIA_PADRAO_VEICULOS, ativo=True).first()
    if not cat:
        raise ValueError('Categoria padrão "Mobilidade" não encontrada. Execute scripts/sql/veic_homolog_2_mobilidade.sql.')
    return cat.id
