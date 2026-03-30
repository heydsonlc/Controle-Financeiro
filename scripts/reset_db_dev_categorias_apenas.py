"""
RESET LIMPO DO BANCO (DEV): recria schema atual e popula APENAS categorias.

O que faz:
1) Remove `data/gastos.db` (SQLite) se existir
2) Executa `db.create_all()` com os models atuais (FASES 1–6)
3) Insere apenas categorias base (sem dados de exemplo)

O que NÃO faz:
- Não roda Alembic/Flask-Migrate
- Não cria itens/despesas/receitas/cartões/etc.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app import create_app
from backend.models import db


def main():
    db_path = Path(__file__).resolve().parents[1] / 'data' / 'gastos.db'

    if '--yes' not in sys.argv and '-y' not in sys.argv:
        print('[AVISO] Isto vai apagar o banco DEV em:', db_path)
        resp = input('Digite "SIM" para confirmar: ').strip().upper()
        if resp != 'SIM':
            print('[CANCELADO] Nenhuma alteração foi feita.')
            return

    if db_path.exists():
        db_path.unlink()
        print('[OK] Banco removido:', db_path)
    else:
        print('[OK] Banco não existia (nada a remover).')

    app = create_app('development')
    with app.app_context():
        (db_path.parent).mkdir(exist_ok=True)
        db.create_all()
        print('[OK] Schema criado com os models atuais.')

    # Seed somente categorias
    from scripts.seed_categorias_apenas import main as seed_categorias
    seed_categorias()

    print('[OK] Reset concluído. Agora inicie o servidor e teste `/veiculos`.')


if __name__ == '__main__':
    main()

