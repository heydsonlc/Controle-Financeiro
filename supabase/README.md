# supabase/ — banco da nova arquitetura

| Caminho | Conteúdo |
|---|---|
| `migrations/` | Migrations da nova arquitetura (schema `financeiro`). No Supabase de teste: `20261020120000` (categorias) **consta aplicada**; `20261021090000` (perfis) **não aplicada** |
| `tests/local_supabase_shim.sql` | Reprodução mínima dos objetos que o Supabase já fornece (roles `anon`/`authenticated`, `auth.uid()`). **Só para o cluster descartável dos testes**; nunca aplicar num projeto Supabase |

As tabelas do Flask continuam sendo geridas pelo Alembic (`migrations/` na raiz). Esta pasta não as altera.

## Perfis (PERFIS-1)

`financeiro.perfil_acesso` liga usuários do Auth aos perfis de `public.perfil_financeiro`. **Vínculos só por administrador**, nunca pelo navegador. Exemplo (SQL editor, com os ids reais):

```sql
insert into financeiro.perfil_acesso (user_id, perfil_financeiro_id, papel)
values ('<uuid do usuario em auth.users>', <id do perfil>, 'TITULAR');
```

Toda função nova que receber um perfil do navegador deve chamar `financeiro.pode_acessar_perfil(id)` e revogar `EXECUTE` de `PUBLIC`/`anon`.

## Validação

`tests/test_supabase_mvp_rls.py` aplica o shim e as migrations num cluster PostgreSQL descartável e prova o controle de acesso:
- na camada de banco (`SET ROLE` + claims do JWT, como o PostgREST faz);
- na camada REST (PostgREST real), quando `POSTGREST_BIN` está definido.

## Deploy de migrations (SUPABASE-DEPLOY-CONTROL-1)

"Deploy to production" da integração GitHub do Supabase foi **desligado** em 2026-10-21: um push **não** aplica mais as migrations desta pasta. **Padrão:** aplicar só com `scripts/supabase_migrations.py aplicar --versoes <v>`, com autorização expressa (`docs/SUPABASE_DEPLOY_CONTROL_1.md`). Na primeira migration nova, confirmar que ela continua pendente após o push.

## Antes de aplicar no projeto remoto (exige autorização específica)

1. **Corrigir a exposição atual do schema `public`** (ver `docs/CF_SUPABASE_REFACTOR_1.md` §2).
2. Em *Authentication*: **desligar o cadastro público** (*Allow new users to sign up*) e criar o usuário dono por convite.
3. Em *Data API*: expor o schema `financeiro` e **não** expor o `public`.
4. Aplicar as migrations desta pasta (ex.: `supabase db push`, depois de `supabase link` no projeto do Controle Financeiro, **nunca** no da Calculadora Judicial).
5. Repetir os testes de acesso contra o projeto: anônimo não lê; usuário só vê as próprias linhas; ninguém escreve pela API.
