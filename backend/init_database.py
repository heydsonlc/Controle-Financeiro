"""
Script para inicializar/atualizar o banco de dados
Cria todas as tabelas definidas nos models
"""
import sys
import os

# Adicionar o diretório backend ao path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import *

def init_database():
    """Inicializa/atualiza todas as tabelas do banco"""
    with app.app_context():
        print("Criando/atualizando tabelas do banco de dados...")
        db.create_all()
        print("✓ Tabelas criadas/atualizadas com sucesso!")

        # Listar tabelas criadas
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        tabelas = inspector.get_table_names()
        print(f"\nTabelas no banco ({len(tabelas)}):")
        for tabela in sorted(tabelas):
            print(f"  - {tabela}")

if __name__ == '__main__':
    init_database()
