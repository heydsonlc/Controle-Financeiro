"""
Script de Migração: Criar tabela de Preferências e Configurações Gerais

Cria a tabela 'preferencia' para armazenar as configurações do sistema organizadas em 5 abas:
1. Dados Pessoais
2. Comportamento do Sistema
3. Aparência
4. Backup e Importação
5. IA e Automação

Uso:
    python backend/migrations/create_preferencias.py
"""
import sys
from pathlib import Path

# Adicionar diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.app import create_app
from backend.models import db

def run_migration():
    """Executa a migração para criar a tabela preferencia"""
    app = create_app('development')

    with app.app_context():
        # Verificar se a tabela já existe
        inspector = db.inspect(db.engine)
        if 'preferencia' in inspector.get_table_names():
            print("AVISO: Tabela 'preferencia' ja existe!")
            return

        print("Criando tabela 'preferencia'...")

        # Criar tabela
        conn = db.engine.connect()
        trans = conn.begin()

        try:
            conn.execute(db.text("""
                CREATE TABLE preferencia (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,

                    -- ABA 1: Dados Pessoais
                    nome_usuario TEXT,
                    renda_principal NUMERIC(10, 2),
                    mes_inicio_planejamento INTEGER DEFAULT 1,
                    dia_fechamento_mes INTEGER DEFAULT 1,

                    -- ABA 2: Comportamento - Lançamentos
                    ajustar_competencia_automatico BOOLEAN DEFAULT 1,
                    exibir_aviso_despesa_vencida BOOLEAN DEFAULT 1,
                    solicitar_confirmacao_exclusao BOOLEAN DEFAULT 1,
                    vincular_pagamento_cartao_auto BOOLEAN DEFAULT 1,

                    -- ABA 2: Comportamento - Dashboard
                    graficos_visiveis TEXT DEFAULT 'categorias,evolucao,saldo',
                    insights_inteligentes_ativo BOOLEAN DEFAULT 1,
                    mostrar_saldo_consolidado BOOLEAN DEFAULT 1,
                    mostrar_evolucao_historica BOOLEAN DEFAULT 1,

                    -- ABA 2: Comportamento - Cartões
                    dia_inicio_fatura INTEGER DEFAULT 1,
                    dia_corte_fatura INTEGER DEFAULT 1,
                    lancamentos_agrupados BOOLEAN DEFAULT 0,
                    orcamento_por_categoria BOOLEAN DEFAULT 1,

                    -- ABA 3: Aparência
                    tema_sistema TEXT DEFAULT 'escuro',
                    cor_principal TEXT DEFAULT '#3b82f6',
                    mostrar_icones_coloridos BOOLEAN DEFAULT 1,
                    abreviar_valores BOOLEAN DEFAULT 0,

                    -- ABA 4: Backup
                    ultimo_backup DATETIME,
                    backup_automatico BOOLEAN DEFAULT 0,

                    -- ABA 5: IA e Automação
                    modo_inteligente_ativo BOOLEAN DEFAULT 0,
                    sugestoes_economia BOOLEAN DEFAULT 0,
                    classificacao_automatica BOOLEAN DEFAULT 0,
                    correcao_categorias BOOLEAN DEFAULT 0,
                    parcelas_recorrentes_auto BOOLEAN DEFAULT 0,

                    -- Metadata
                    data_criacao DATETIME DEFAULT CURRENT_TIMESTAMP,
                    data_atualizacao DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))

            # Criar registro padrão (singleton)
            conn.execute(db.text("""
                INSERT INTO preferencia (
                    nome_usuario,
                    mes_inicio_planejamento,
                    dia_fechamento_mes,
                    tema_sistema,
                    cor_principal
                ) VALUES (
                    'Usuário',
                    1,
                    1,
                    'escuro',
                    '#3b82f6'
                )
            """))

            trans.commit()
            print("OK: Tabela 'preferencia' criada com sucesso!")
            print("OK: Registro padrao criado!")

        except Exception as e:
            trans.rollback()
            print(f"ERRO ao criar tabela: {e}")
            raise
        finally:
            conn.close()

if __name__ == '__main__':
    run_migration()
