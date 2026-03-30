# Scripts Utilitários

Scripts auxiliares para manutenção e geração de dados do sistema.

## 📋 Conteúdo

### Inicialização

- **`init_db.py`** - Inicializa o banco de dados
  - Cria tabelas
  - Popula dados iniciais
  - Uso: `python scripts/init_db.py`

### Geradores de Dados

- **`gerar_orcamentos_receitas.py`** - Gera orçamentos e receitas
  - Útil para popular dados de teste
  - Uso: `python scripts/gerar_orcamentos_receitas.py`

- **`gerar_parcelas_consorcios.py`** - Gera parcelas de consórcios
  - Cria parcelas automáticas
  - Uso: `python scripts/gerar_parcelas_consorcios.py`

### Correção de Dados

- **`corrigir_nomes.py`** - Corrige nomes no banco
  - Normaliza dados inconsistentes
  - Uso: `python scripts/corrigir_nomes.py`

---

**Nota:** Execute sempre a partir da raiz do projeto.
