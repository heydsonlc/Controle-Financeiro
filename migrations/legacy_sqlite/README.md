# Migrations e Scripts Legados (SQLite)

Arquivado em: 2026-05-01 — MVP DB-3D

## O que está aqui

Scripts de migração de schema criados antes da adoção do Alembic como fonte oficial.
Foram usados em diferentes fases do projeto para evoluir o banco SQLite local (`financeiro.db`, `data/gastos.db`).

## Regras

1. Estes arquivos são **históricos**. Não fazem parte do fluxo oficial atual.
2. **Não executar** no ambiente atual — o banco é PostgreSQL e usa Alembic.
3. Podem conter comandos SQLite-specific: `sqlite3`, `PRAGMA`, `sqlite_master`.
4. Podem conter caminhos hardcoded para `financeiro.db` ou `data/gastos.db`.
5. Podem conter `DROP TABLE`, `ALTER TABLE` manual ou operações destrutivas.
6. Mantidos apenas para referência histórica de quais mudanças de schema foram feitas.

## Fonte oficial atual

`migrations/versions/dd1a552aec6a_baseline_inicial_schema_completo.py`

Qualquer evolução futura de schema deve usar:

```bash
flask db migrate -m "descricao"
flask db upgrade
```

## Conteúdo

### `backend_migrations/`

Scripts SQLite custom que viviam em `backend/migrations/` (removidos em DB-3D):

| Arquivo | O que fazia |
|---|---|
| `add_cartao_fatura_virtual.py` | Campos fatura virtual em Conta (`financeiro.db`) |
| `add_grupo_agregador.py` | Tabela grupo_agregador (`financeiro.db`) |
| `add_movimento_financeiro.py` | Tabela movimento_financeiro (`financeiro.db`) |
| `add_receita_fields.py` | Campos extras em receita (`data/gastos.db`) |
| `add_seguro_variavel_financiamento.py` | Campos seguro variável em financiamento (`data/gastos.db`) |
| `add_taxa_administracao_financiamento.py` | Campo taxa_administracao_fixa em financiamento (`financeiro.db`) |
| `add_tipo_reajuste_consorcio.py` | Campos reajuste em contrato_consorcio (`data/gastos.db`) |
| `add_valor_pago.py` | Campo valor_pago em item_despesa (`data/gastos.db`) |
| `create_contas_bancarias.py` | Tabela conta_bancaria (`data/gastos.db`) |
| `create_contrato_consorcio.py` | Tabela contrato_consorcio (`data/gastos.db`) |
| `create_patrimonio.py` | Tabelas patrimônio (`data/gastos.db`) |
| `create_preferencias.py` | Tabela preferencia (`data/gastos.db`) |
| `tornar_item_receita_id_nullable.py` | Tornar item_receita_id nullable (`backend/financeiro.db`) |
| `add_taxa_adm_column.py` | Script standalone (raiz `backend/`) — mesmo fim que o acima (`financeiro.db`) |
| `versions/add_cartao_id_to_lancamento_agregado.py` | Alembic parcial não integrado à chain oficial |

### `custom_scripts/`

Scripts custom que viviam em `migrations/` (raiz), fora da chain Alembic:

| Arquivo | O que fazia |
|---|---|
| `add_estado_soberano_financiamento.py` | Campos saldo soberano em Financiamento |
| `add_financiamento_seguro_vigencia.py` | Tabela financiamento_seguro_vigencia |
| `tornar_vigencia_campos_legacy_opcionais.py` | Tornar campos legacy de vigência nullable |

Estes três scripts usam SQLAlchemy/psycopg2 direto, não Alembic puro. Não fazem parte da chain `dd1a552aec6a`.

## Scripts preservados fora deste arquivo

Os seguintes scripts **não foram movidos** (continuam nos locais originais):

- `scripts/debug/*.py` — debug manual do banco; 5 deles usam `sqlite3` + `data/gastos.db` (legados),
  6 usam Flask app context com PostgreSQL (ainda úteis para diagnóstico manual). Preservados no local.
- `scripts/reset_db_dev_categorias_apenas.py` — utilitário de reset local/dev com referência a `data/gastos.db`;
  preservado no local por estar fora do escopo de arquivamento de migrations e não deve ser usado para evolução de schema.
- `scripts/seed_categorias_apenas.py` — seed oficial, não é legado SQLite.
- `scripts/seed_modulo_veiculos_mvp.py` — seed oficial, não é legado SQLite.
- `migrations/env.py`, `migrations/alembic.ini`, `migrations/script.py.mako` — infraestrutura Alembic oficial.
