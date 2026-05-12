# Regularizacao do schema do banco local

Registro operacional da regularizacao controlada do banco `data/gastos.db`.

## Contexto

O banco local existia sem tabela `alembic_version`, mas ja continha tabelas antigas
do sistema. Por isso, `flask db upgrade` direto nao era seguro: a baseline do
Alembic tentava criar tabelas ja existentes.

## Procedimento adotado

Foi criada uma rotina idempotente em:

```bash
scripts/regularizar_schema_gastos_sqlite.py
```

Modos principais:

```bash
venv\Scripts\python.exe scripts\regularizar_schema_gastos_sqlite.py --db data\gastos.db --dry-run
venv\Scripts\python.exe scripts\regularizar_schema_gastos_sqlite.py --db data\gastos.db --apply --backup --stamp-head
```

A rotina:

- cria backup antes da aplicacao quando `--backup` e usado;
- cria tabelas ausentes a partir do `models.py`;
- adiciona somente colunas ausentes em tabelas existentes;
- nao remove tabelas;
- nao apaga dados;
- semeia perfis padrao, categorias sistemicas de Mobilidade e TR oficial de forma idempotente;
- marca `alembic_version` no head apenas quando nao restam divergencias de tabelas/colunas do model.

## Cuidados

- Nao rodar `flask db upgrade` direto em banco antigo sem regularizacao previa.
- Nao versionar `data/gastos.db`, copias temporarias ou backups.
- Antes de nova regularizacao em banco real, repetir o fluxo:

```text
backup -> copia de teste -> dry-run -> apply na copia -> validacao -> apply no original
```

## Resultado esperado

Apos a regularizacao, o banco deve apontar para:

```text
9b8a09ecc52f (head)
```

E deve conter as estruturas recentes usadas por categorias sistemicas,
Categoria do Cartao, Mobilidade, TR oficial, documentos e conferencias de
financiamento.
