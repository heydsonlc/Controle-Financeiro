# BASE-REAL-1A - Reset seguro do banco para uso real

Este procedimento limpa dados operacionais do banco local PostgreSQL e preserva:

- estrutura do banco;
- migrations/Alembic;
- perfis financeiros essenciais `Pessoal` e `Empresa`;
- preferencias tecnicas do usuario, quando existentes;
- backups e configuracoes locais fora do banco.

Antes de qualquer limpeza, o script executa um backup real via `pg_dump` usando o
servico local de backup da aplicacao.

## Comandos

Auditoria sem alterar dados:

```powershell
.\venv\Scripts\python.exe scripts\base_real_1a_reset.py --dry-run
```

Execucao real:

```powershell
.\venv\Scripts\python.exe scripts\base_real_1a_reset.py --yes
```

## Segurança

O script aborta quando:

- o banco nao e PostgreSQL;
- o host do banco nao e local;
- a URL contem marcadores de servico remoto;
- o backup pre-reset falha;
- o arquivo `.dump` nao e criado ou esta vazio.

## Tabelas preservadas

- `alembic_version`
- `perfil_financeiro`
- `preferencia`

As demais tabelas de aplicacao sao limpas com `TRUNCATE ... RESTART IDENTITY CASCADE`.

## Pos-reset

Depois do reset, execute o seed inicial:

```powershell
.\venv\Scripts\python.exe scripts\seed\base_real_1b_seed_categorias.py
```

Em seguida valide:

- perfis `Pessoal` e `Empresa`;
- categorias globais;
- categorias do cartao apenas no perfil `Pessoal`;
- troca de perfil na aplicacao.
