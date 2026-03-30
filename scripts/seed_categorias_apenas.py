"""
Seed de categorias (apenas) para desenvolvimento.

Importante:
- Não cria nenhuma outra entidade.
- Mantém categorias genéricas (sem "Veículo") para respeitar o contrato do módulo.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app import create_app
from backend.models import db, Categoria


CATEGORIAS_PADRAO = [
    'Transporte',
]


def main():
    app = create_app('development')
    with app.app_context():
        criadas = 0
        for nome in CATEGORIAS_PADRAO:
            existe = Categoria.query.filter_by(nome=nome).first()
            if existe:
                continue
            db.session.add(Categoria(nome=nome, ativo=True))
            criadas += 1

        db.session.commit()
        total = Categoria.query.count()
        print(f'[OK] Categorias seed concluído: criadas={criadas} total={total}')


if __name__ == '__main__':
    main()
