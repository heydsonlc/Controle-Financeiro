# supabase/ — banco da nova arquitetura

| Caminho | Conteúdo |
|---|---|
| `migrations/` | Migrations da nova arquitetura (schema `financeiro`). **Nenhuma foi aplicada no Supabase remoto.** |
| `tests/local_supabase_shim.sql` | Reprodução mínima dos objetos que o Supabase já fornece (roles `anon`/`authenticated`, `auth.uid()`). **Só para o cluster descartável dos testes**; nunca aplicar num projeto Supabase |

As tabelas do Flask continuam sendo geridas pelo Alembic (`migrations/` na raiz). Esta pasta não as altera.

## Validação

`tests/test_supabase_mvp_rls.py` aplica o shim e as migrations num cluster PostgreSQL descartável e prova o controle de acesso:
- na camada de banco (`SET ROLE` + claims do JWT, como o PostgREST faz);
- na camada REST (PostgREST real), quando `POSTGREST_BIN` está definido.

## Antes de aplicar no projeto remoto (exige autorização específica)

1. **Corrigir a exposição atual do schema `public`** (ver `docs/CF_SUPABASE_REFACTOR_1.md` §2).
2. Em *Authentication*: **desligar o cadastro público** (*Allow new users to sign up*) e criar o usuário dono por convite.
3. Em *Data API*: expor o schema `financeiro` e **não** expor o `public`.
4. Aplicar as migrations desta pasta (ex.: `supabase db push`, depois de `supabase link` no projeto do Controle Financeiro, **nunca** no da Calculadora Judicial).
5. Repetir os testes de acesso contra o projeto: anônimo não lê; usuário só vê as próprias linhas; ninguém escreve pela API.
