"""
Migration: Criar tabela financiamento_seguro_vigencia

Sistema de vigências para seguro habitacional:
- Usuário informa valores futuros do seguro
- Sistema deriva taxa implícita baseada no saldo devedor
- Suporta múltiplas vigências (ex: valores para próximos anos)
- Encerra vigência anterior automaticamente

Execução: python migrations/add_financiamento_seguro_vigencia.py
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.app import create_app
from backend.models import db

app = create_app()

with app.app_context():
    print("="*80)
    print("MIGRATION: Criar tabela financiamento_seguro_vigencia")
    print("="*80)
    print()

    # SQL para criar a tabela
    sql = """
    CREATE TABLE IF NOT EXISTS financiamento_seguro_vigencia (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        financiamento_id INTEGER NOT NULL,
        competencia_inicio DATE NOT NULL,
        valor_mensal NUMERIC(10, 2) NOT NULL,
        saldo_devedor_vigencia NUMERIC(12, 2) NOT NULL,
        taxa_percentual NUMERIC(8, 6) NOT NULL,
        data_nascimento_segurado DATE,
        observacoes TEXT,
        vigencia_ativa BOOLEAN DEFAULT 1,
        data_encerramento DATE,
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (financiamento_id) REFERENCES financiamento(id) ON DELETE CASCADE
    );
    """

    print("1. Criando tabela...")
    db.session.execute(db.text(sql))

    # Criar índices
    print("2. Criando índices...")

    indices = [
        "CREATE INDEX IF NOT EXISTS idx_seguro_vig_financ ON financiamento_seguro_vigencia(financiamento_id);",
        "CREATE INDEX IF NOT EXISTS idx_seguro_vig_comp ON financiamento_seguro_vigencia(competencia_inicio);",
        "CREATE INDEX IF NOT EXISTS idx_seguro_vig_ativa ON financiamento_seguro_vigencia(vigencia_ativa);"
    ]

    for idx_sql in indices:
        db.session.execute(db.text(idx_sql))

    db.session.commit()

    print()
    print("[OK] Tabela financiamento_seguro_vigencia criada com sucesso!")
    print()
    print("Estrutura:")
    print("  - competencia_inicio: Mês/ano de início da vigência")
    print("  - valor_mensal: Valor do seguro informado pelo usuário")
    print("  - saldo_devedor_vigencia: Saldo no início da vigência")
    print("  - taxa_percentual: Taxa derivada (valor / saldo * 100)")
    print("  - vigencia_ativa: True enquanto vigente, False quando substituída")
    print()
