"""
Script para inicializar o banco de dados

Executa:
- Criação das tabelas
- Opcionalmente popula com dados de exemplo
"""
import sys
import os
from pathlib import Path

# Adicionar o diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent))

from backend.app import create_app
from backend.models import db


def init_database(with_sample_data=False):
    """
    Inicializa o banco de dados

    Args:
        with_sample_data: Se True, popula com dados de exemplo
    """
    app = create_app('development')

    with app.app_context():
        # Criar diretório data se não existir
        data_dir = Path(__file__).parent / 'data'
        data_dir.mkdir(exist_ok=True)

        print("=> Criando tabelas do banco de dados...")
        db.create_all()
        print("=> Tabelas criadas com sucesso!")

        if with_sample_data:
            print("\n=> Populando banco com dados de exemplo...")
            populate_sample_data()
            print("=> Dados de exemplo inseridos com sucesso!")

        print(f"\n=> Banco de dados SQLite criado em: {data_dir / 'gastos.db'}")
        print("\n=> Para iniciar o servidor, execute: python backend/app.py")


def populate_sample_data():
    """Popula o banco com dados de exemplo para testes"""
    from backend.models import (
        Categoria, ItemDespesa, ItemReceita, ContaPatrimonio,
        ConfigAgregador, ItemAgregado
    )
    from datetime import date

    # Categorias
    categorias = [
        Categoria(nome='Moradia', descricao='Despesas relacionadas à moradia', cor='#ff6b6b'),
        Categoria(nome='Transporte', descricao='Despesas com transporte', cor='#4ecdc4'),
        Categoria(nome='Alimentação', descricao='Despesas com alimentação', cor='#45b7d1'),
        Categoria(nome='Saúde', descricao='Despesas com saúde', cor='#96ceb4'),
        Categoria(nome='Lazer', descricao='Despesas com lazer e entretenimento', cor='#ffeaa7'),
    ]
    db.session.add_all(categorias)
    db.session.flush()

    # Itens de Despesa - Simples
    itens_simples = [
        ItemDespesa(categoria_id=1, nome='Aluguel', tipo='Simples', descricao='Aluguel mensal'),
        ItemDespesa(categoria_id=1, nome='Condomínio', tipo='Simples', descricao='Condomínio mensal'),
        ItemDespesa(categoria_id=1, nome='Energia', tipo='Simples', descricao='Conta de luz'),
        ItemDespesa(categoria_id=1, nome='Água', tipo='Simples', descricao='Conta de água'),
        ItemDespesa(categoria_id=1, nome='Internet', tipo='Simples', descricao='Internet banda larga'),
    ]
    db.session.add_all(itens_simples)
    db.session.flush()

    # Itens de Despesa - Agregadores (Cartões)
    cartao_visa = ItemDespesa(
        categoria_id=3,
        nome='Cartão VISA',
        tipo='Agregador',
        descricao='Cartão de crédito VISA'
    )
    db.session.add(cartao_visa)
    db.session.flush()

    # Configuração do Cartão
    config_cartao = ConfigAgregador(
        item_despesa_id=cartao_visa.id,
        dia_fechamento=15,
        dia_vencimento=25,
        limite_credito=5000.00
    )
    db.session.add(config_cartao)

    # Sub-itens do Cartão
    subitens_cartao = [
        ItemAgregado(item_despesa_id=cartao_visa.id, nome='Supermercado', descricao='Compras de supermercado'),
        ItemAgregado(item_despesa_id=cartao_visa.id, nome='Farmácia', descricao='Medicamentos e produtos farmacêuticos'),
        ItemAgregado(item_despesa_id=cartao_visa.id, nome='Restaurantes', descricao='Refeições fora de casa'),
    ]
    db.session.add_all(subitens_cartao)

    # Itens de Receita
    receitas = [
        ItemReceita(nome='Salário', tipo='Fixa', descricao='Salário mensal'),
        ItemReceita(nome='Freelance', tipo='Eventual', descricao='Trabalhos freelance'),
        ItemReceita(nome='Investimentos', tipo='Eventual', descricao='Rendimentos de investimentos'),
    ]
    db.session.add_all(receitas)

    # Contas de Patrimônio
    contas_patrimonio = [
        ContaPatrimonio(
            nome='Conta Corrente',
            tipo='Corrente',
            saldo_inicial=5000.00,
            saldo_atual=5000.00,
            cor='#3498db'
        ),
        ContaPatrimonio(
            nome='Reserva de Emergência',
            tipo='Reserva',
            saldo_inicial=10000.00,
            saldo_atual=10000.00,
            meta=20000.00,
            cor='#e74c3c'
        ),
        ContaPatrimonio(
            nome='Investimentos',
            tipo='Investimento',
            saldo_inicial=15000.00,
            saldo_atual=15000.00,
            meta=50000.00,
            cor='#2ecc71'
        ),
    ]
    db.session.add_all(contas_patrimonio)

    # Commit de todas as alterações
    db.session.commit()


if __name__ == '__main__':
    # Verificar se deve popular com dados de exemplo
    with_sample = '--sample' in sys.argv or '-s' in sys.argv

    print("="*60)
    print("  INICIALIZAÇÃO DO BANCO DE DADOS")
    print("  Sistema de Controle Financeiro")
    print("="*60)

    init_database(with_sample_data=with_sample)

    if not with_sample:
        print("\n=> Dica: Execute com --sample para adicionar dados de exemplo")
        print("   Exemplo: python init_db.py --sample")
