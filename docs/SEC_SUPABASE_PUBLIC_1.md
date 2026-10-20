# SEC-SUPABASE-PUBLIC-1 — Exposição das tabelas legadas pela Data API do Supabase

Data: 2026-10-20. Projeto: **somente** o do Controle Financeiro (`fzjmge…`). Nenhum outro projeto Supabase foi consultado ou alterado.

Situação atual:
- **Contenção (Etapa A) aguardando a ação do usuário no painel.**
- Migration permanente (Etapa B) preparada e testada, **não executada no remoto**.

Nenhum registro foi lido: as sondagens usam `limit=0` ou filtros impossíveis, e o diagnóstico no banco só lê catálogos e estatísticas.

## 1. Situação anterior à contenção (comprovada)

| Verificação | Resultado | Como |
|---|---|---|
| Schemas expostos pela Data API | **`public`, `graphql_public`** | erro PGRST106 numa rota de tabela (lista os schemas, sem dados) |
| Tabelas do Flask no `public` | 52, dono `postgres`, **nenhuma com RLS** | catálogo |
| Privilégios de `anon` e `authenticated` | **SELECT/INSERT/UPDATE/DELETE nas 52 tabelas**; usage/select/update nas **51 sequências** | `has_*_privilege` |
| Default privileges no `public` | `postgres` e `supabase_admin` concedem tudo a `anon`/`authenticated` em tabelas, sequências e funções | `pg_default_acl` |
| Leitura anônima via HTTP (só a chave pública) | **HTTP 200** em `usuario`, `config_agregador`, `conta_bancaria`, `categoria`, `alembic_version` | `scripts/verificar_exposicao_supabase.py` (`limit=0`: nenhuma linha retornada) |
| GraphQL | `pg_graphql` **não está habilitado**: sem exposição por esse caminho hoje | introspecção (só nomes) |
| Papel do Flask | `postgres`: sem superuser, **com BYPASSRLS**, dono das 52 tabelas | `pg_roles` |

**Dependências legítimas da Data API no `public`: nenhuma.**
- O Flask conecta direto no Postgres (pooler).
- O frontend legado não usa supabase-js nem `/rest/v1`.
- Nenhum outro repositório Kortex referencia este projeto.
- O novo MVP usa o schema `financeiro`.

## 2. Etapa A — Contenção (ação do usuário)

No painel do projeto **Controle-Financeiro** (nunca no da Calculadora Judicial), em *Project Settings → Data API* (ou *Integrations → Data API*):

1. Em **Exposed schemas**, **remover `public`**. Manter `graphql_public`, que é inofensivo enquanto o `pg_graphql` estiver desligado.
2. **Não** desligar a Data API: o novo frontend vai precisar dela para o schema `financeiro`, que só será exposto depois da validação.
3. Salvar.

Verificação depois da alteração (somente leitura, mais escritas com filtro impossível `id=eq.-1`, que afetam zero linhas):

```bash
venv\Scripts\python.exe scripts\verificar_exposicao_supabase.py --via-cli --com-escrita
```

Esperado:
- a lista de schemas expostos sem `public`;
- GET, PATCH e DELETE anônimos **bloqueados** em `usuario` e nas demais tabelas;
- `RESULTADO: public BLOQUEADO para anonimo` (exit 0).

Depois disso, confirmar que o Flask continua funcionando: `/health` e o gate `check_deploy_env.py` com `.env.staging`.

O script usa **somente a chave pública**, que é o que um terceiro teria. Pela CLI, as chaves privilegiadas são descartadas em memória e nenhuma chave é impressa. O ref do projeto vem do `.env.staging` local e nunca entra no Git.

## 3. Etapa B — Proteção permanente (migration preparada, não executada)

`migrations/versions/c4f7a2d91b3e_protege_schema_public_no_supabase.py` (revisa `5c91e95eb05d`):

- **RLS habilitada** em todas as tabelas do `public` **cujo dono é o papel que executa a migration**, que é o mesmo do Flask. Tabelas de outro dono são ignoradas e registradas em log, porque ligar RLS nelas poderia cortar o acesso do Flask.
- **Sem `FORCE`.** O dono não é afetado por RLS sem `FORCE`, e no Supabase o `postgres` ainda tem `BYPASSRLS`, então `FORCE` não traria ganho. Testado com um papel equivalente.
- **Nenhuma policy criada.** Sem policy, a RLS nega tudo a quem não é dono. Não há policy permissiva "para compatibilidade".
- **Revoga de `anon` e `authenticated` todos os privilégios** em tabelas, sequências e funções do `public`, objeto a objeto e só nos do próprio papel.
- **Revoga os default privileges** do papel no `public`, para que tabelas de migrations futuras não nasçam expostas.
- **No-op fora do Supabase:** em SQLite ou num PostgreSQL sem os papéis `anon`/`authenticated` (o banco local de desenvolvimento), não faz nada.
- **Idempotente.** O `downgrade` é intencionalmente vazio: desfazer reabriria a exposição.

**Defeito encontrado e corrigido pelos testes:** a primeira versão usava `REVOKE ... ON ALL TABLES IN SCHEMA public`, que **aborta a migration inteira** se houver no `public` um objeto de outro dono sem privilégio para o papel atual. A versão final revoga objeto a objeto.

**Limite residual:** os default privileges do papel de plataforma `supabase_admin` não podem ser alterados pelo `postgres`. Objetos criados **pela plataforma** no `public` no futuro ainda receberiam grants. Mitigação: manter o `public` fora da Data API.

Aplicação no remoto (**exige autorização separada**):

```bash
python -m flask --app backend/app.py db upgrade   # com .env.staging carregado
```

Depois, repetir `verificar_exposicao_supabase.py --com-escrita` e o smoke do Flask.

## 4. Testes

`tests/test_sec_supabase_public.py` roda num cluster PostgreSQL **descartável** que reproduz o Supabase:
- o shim cria `anon`/`authenticated`/`authenticator`;
- um papel que imita o `postgres` da plataforma (sem superuser, com BYPASSRLS e os mesmos default privileges);
- a **cadeia real das 26 migrations Alembic**;
- o PostgREST oficial expondo o `public`, como está hoje.

| Teste | Resultado |
|---|---|
| Antes (5c91): RLS em 0 tabelas, `anon`/`authenticated` com CRUD em todas | ✅ reproduz o problema |
| Antes, via REST: anônimo lê (200) e grava (PATCH aceito) | ✅ reproduz o problema |
| Depois (head): RLS em todas, nenhuma com FORCE | ✅ |
| Depois: zero privilégios de `anon`/`authenticated` em tabelas e sequências | ✅ |
| Tabela criada depois da migration não nasce exposta | ✅ |
| Dono continua com SELECT/INSERT/UPDATE/DELETE | ✅ |
| **Flask real** contra o banco migrado: login, listar e criar categoria | ✅ login 302, listagem 200, criação aceita e visível na listagem |
| `anon`/`authenticated` recebem `InsufficientPrivilege` no banco | ✅ |
| REST depois: GET/PATCH/DELETE anônimos e leitura/POST com JWT autenticado → 401/403 | ✅ |
| Idempotência (segunda execução não muda nada) | ✅ |
| Tabela de outro dono: ignorada, sem RLS | ✅ |
| No-op em SQLite e em PostgreSQL sem os papéis do Supabase | ✅ |

**Resultados:**
- Este arquivo e `test_supabase_mvp_rls.py` juntos: **40 passed, 2 execuções seguidas**.
- E2E do MVP: **9 passed**.
- Suíte completa do Flask: **1049 passed, 12 skipped** (REST sem `POSTGREST_BIN`) **e as mesmas 5 falhas preexistentes** (comprovadas no commit `0e04407`). Nenhuma regressão.

Os problemas do ambiente de teste foram corrigidos no helper `tests/supabase_local.py`:
- o PostgREST agora espera `/ready` no servidor admin e encerra o processo se não subir, para não deixar órfão;
- os schemas expostos são parametrizáveis, porque um schema inexistente deixa o PostgREST em 503.

## 5. Etapa C — Auditoria de possível exposição

Fontes somente leitura no banco: `pg_stat_statements` (desde **2026-08-20 02:28 UTC**, criação do projeto; 1.576 de 5.000 entradas, sem descarte), `pg_stat_user_tables`, `auth.*`.

| Pergunta | Evidência |
|---|---|
| Consultas executadas por `anon`/`authenticated` | Só **as minhas sondagens de hoje** (5 tabelas × 3 execuções com `limit=0`, mais 1 introspecção GraphQL = 16 chamadas). `authenticated`: nenhuma |
| Escritas por `anon`/`authenticated` | **Nenhum** INSERT/UPDATE/DELETE |
| Alterações em `usuario` | 1 inserção, **0 atualizações, 0 exclusões**: o hash de senha nunca foi alterado |
| Outras escritas no `public` | Seeds, índices TR e smoke tests compatíveis com o SUPABASE-MIGRATE-1 |
| Cadastros no Supabase Auth | `auth.users` = 0; `auth.audit_log_entries` = 0 |
| `service_role` | 4 consultas de metadados (típicas do painel) |

**Conclusão:** **não há indício de acesso indevido** nas fontes disponíveis. A ausência de registro não prova a ausência de acesso, por três motivos:
- o `pg_stat_statements` não registra requisições recusadas;
- não registra o conteúdo devolvido;
- não cobre eventuais reinícios que limpem estatísticas.

Os logs HTTP do gateway ficam no painel, com retenção conforme o plano. Para conferir: *Logs → Logs Explorer*, com a consulta:

```sql
select timestamp, request.method, request.path, response.status_code
from edge_logs
cross join unnest(metadata) as m
cross join unnest(m.request) as request
cross join unnest(m.response) as response
where request.path like '/rest/v1/%'
order by timestamp desc
limit 200
```

As requisições anônimas de 2026-10-20 a `usuario`, `config_agregador`, `conta_bancaria`, `categoria` e `alembic_version` (`limit=0`) e a `/graphql/v1` são as sondagens desta etapa.

**Senhas e chaves:**
- **Redefinir a senha não é necessário**: o hash nunca foi alterado.
- **Rotacionar chaves também não**: as chaves nunca saíram do painel e da CLI, e não estão em nenhum repositório (verificado no histórico).
- Rotacionar a chave publicável continua opcional, de baixo custo.

## 6. Etapa D — Integração com o novo MVP

| Item | Situação |
|---|---|
| `financeiro` isolado do `public` | ✅ schema próprio, sem herdar default privileges (testado) |
| RLS ativa e forçada em `financeiro.categorias` | ✅ |
| `anon` sem acesso | ✅ sem USAGE no schema |
| `authenticated` só com SELECT nas próprias linhas | ✅ |
| Front usa o Auth sem tocar nas tabelas legadas | ✅ só `financeiro.categorias`; depois da Etapa A o `public` nem é alcançável pela API |
| Isolamento entre usuários | ✅ (banco, REST e E2E) |
| No remoto | **Pendente**: a migration do schema `financeiro` não foi aplicada; isso vem na etapa de Auth real |

## 7. Pendências de segurança

1. **Etapa A:** remover `public` dos Exposed schemas (usuário) e rodar a verificação.
2. **Etapa B:** autorizar `flask db upgrade` da migration `c4f7a2d91b3e` no staging.
3. **Antes do Auth real:** desligar o cadastro público, criar o usuário dono por convite e expor apenas `financeiro`.
4. **Se o `pg_graphql` for habilitado um dia:** revisar a exposição (a Etapa B já remove os privilégios que ele usaria).
5. Itens anteriores: SEG-2 (limite de tentativas de login), CARD-SEC-1 (dados de cartão em texto puro no banco), BACKUP-DOCS-1.
