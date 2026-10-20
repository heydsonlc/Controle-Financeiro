# CF-SUPABASE-REFACTOR-1 — Primeiro módulo da nova arquitetura (Cloudflare Pages + Supabase)

Data: 2026-10-20. Implementação controlada do **primeiro MVP**. Não é uma reescrita geral.

Nada foi publicado: nenhum deploy no Cloudflare, nenhuma migration no Supabase remoto, nenhuma alteração em DNS, na Calculadora Judicial, em dados reais ou em regras financeiras. O Flask segue intacto como aplicação em uso e implementação de referência.

## 1. Arquitetura-alvo e o que este MVP cobre

```
Cloudflare Pages (web/dist, estático)
        │  supabase-js com chave publicável
        ▼
Supabase Auth ──JWT──► Data API (PostgREST) ──► PostgreSQL (schema financeiro, RLS)
                                                 Storage / RPC / Edge Functions: módulos futuros
```

| Entregável | Situação |
|---|---|
| Frontend estático, reaproveitando o tema atual | ✅ `web/`. `style.css` e `theme-light.css` copiados de `frontend/static/css` no build, sem duplicar no Git |
| Integração com Supabase Auth | ✅ `signInWithPassword`, `getUser()` (validação no servidor) e `signOut` |
| Tela protegida após o login | ✅ `categorias.html` |
| Categorias somente leitura com RLS | ✅ `financeiro.categorias`: RLS habilitada e forçada, só SELECT para `authenticated` |
| Configuração de desenvolvimento e testes isolados | ✅ cluster PostgreSQL descartável + PostgREST + E2E, sem Docker |
| Testes automatizados de controle de acesso | ✅ 26 de banco/REST, 7 unitários do build e 9 E2E |
| Plano de migração por módulos | ✅ §6 |
| Relatório de compatibilidade, limitações e custos | ✅ §5 e §7 |

## 2. ⚠️ Achado de segurança preexistente no Supabase de staging (ação urgente)

Diagnóstico somente leitura no projeto do Controle Financeiro (`fzjmge…`), que já guarda as tabelas criadas pelo Flask/Alembic:

| Verificação | Resultado |
|---|---|
| Tabelas no schema `public` | 52, **nenhuma com RLS** |
| Privilégios do papel `anon` | **SELECT, INSERT, UPDATE e DELETE nas 52** (padrão do Supabase para tabelas criadas no `public`) |
| Exemplos | `anon` pode ler e alterar `usuario` (hash de senha) e `config_agregador` (dados de cartão) |
| Data API do projeto | **Ativa** (`/rest/v1/` responde e exige apenas a chave do projeto) |

**Consequência:** quem tiver a chave publicável/anon do projeto, que pelo modelo do Supabase não é segredo, consegue ler e **gravar** em todas as tabelas do Flask pela API REST. Isso inclui trocar o hash de senha do usuário e assumir o login do Flask. Hoje o staging só tem o schema e o usuário administrador, mas o risco vale para qualquer dado futuro.

**Correção recomendada.** É mudança no projeto remoto e **exige sua autorização**; não foi feita.
1. **Imediata, sem migration:** *Project Settings → Data API*: tirar o `public` dos schemas expostos (ou desligar a Data API enquanto a nova arquitetura não estiver pronta). O Flask não é afetado, porque conecta direto no Postgres.
2. **Definitiva (migration revisada):** `enable row level security` nas 52 tabelas e `revoke all ... from anon, authenticated`. O Flask conecta como dono das tabelas e não é afetado pela RLS sem `FORCE`.
3. Antes de usar o Auth: desligar o cadastro público (*Allow new users to sign up*).

O MVP já nasce isolado desse problema: usa o schema próprio `financeiro`, que não herda os privilégios padrão do `public` (provado em teste).

## 3. Implementação

### Banco: `supabase/migrations/20261020120000_financeiro_mvp_categorias.sql`

- Schema `financeiro`. `anon` sem `USAGE`; `authenticated` com `USAGE`.
- `financeiro.categorias(user_id → auth.users, nome, descricao, cor, icone, ativo, criado_em)`, com `CHECK` de formato e nome único por usuário.
- **RLS habilitada e forçada**; única policy: `SELECT` para `authenticated` com `user_id = (select auth.uid())`.
- **Grants mínimos:** só `SELECT` para `authenticated`. Mesmo um erro de policy não liberaria escrita.
- Default privileges do schema revogam tabelas futuras de `anon`/`authenticated`. Para funções isso não é possível, então **toda RPC futura deve revogar `EXECUTE` de `PUBLIC`/`anon` explicitamente** (anotado na migration).

### Frontend: `web/`

- Cliente único com `storageKey` próprio (`cf-financeiro-auth`): nunca compartilha sessão com outro sistema Kortex.
- Guarda de página com `getUser()`, que valida o token no Supabase Auth; `getSession()` aceitaria um token adulterado. Corpo oculto até a validação.
- `next` do login restrito a uma allowlist (sem redirecionamento aberto).
- Renderização só com `textContent` (sem `innerHTML`); cor validada por regex.
- **Nenhuma escrita**: a página não tem formulário nem ação além de "Sair".
- `_headers` (Cloudflare Pages): CSP `script-src 'self'`, `style-src 'self'`, `connect-src` só o próprio site e o projeto Supabase, `frame-ancestors 'none'`, `nosniff` etc. **Testada de fato no E2E**: qualquer violação reprova o teste.
- Build (`scripts/build.mjs`) falha fechado com chave `sb_secret_`/`service_role`, com o projeto da Calculadora Judicial, sem https, ou com conteúdo sensível em `dist/`.

### Ambiente isolado (sem Docker)

Docker não está instalado, e um projeto Supabase novo seria recurso pago. Por isso:

| Peça | Como |
|---|---|
| PostgreSQL | Cluster **descartável** (`initdb` em pasta temporária, só `127.0.0.1`, porta livre) com os binários locais do PostgreSQL 18. **Nunca** usa o banco local de desenvolvimento |
| Objetos do Supabase | `supabase/tests/local_supabase_shim.sql`: roles `anon`/`authenticated`/`authenticator`, `auth.uid()` lendo `request.jwt.claims`, e os default privileges perigosos do `public` (reproduzidos de propósito) |
| Data API | **PostgREST 16.5 oficial**, com JWT HS256 |
| Auth | **Única parte simulada**: endpoints `/auth/v1/token`, `/user` e `/logout` emitindo JWTs reais assinados com o mesmo segredo do PostgREST |

## 4. Testes

| Suíte | Comando | Resultado |
|---|---|---|
| RLS, camada de banco | `pytest tests/test_supabase_mvp_rls.py` | **16 passed** (os 10 de REST pulam com motivo quando falta `POSTGREST_BIN`) |
| RLS, camada REST | idem, com `POSTGREST_BIN` | **26 passed** |
| Build e código-fonte | `cd web && npm run test:unit` | **7 passed** |
| E2E (Playwright, Chromium) | `python web/tests/e2e/run_e2e.py` | **9 passed, 5 execuções seguidas** (~4,5 s cada) |
| Flask (projeto original) | `pytest` completo | **1037 passed, 10 skipped, 5 failed**: as mesmas 5 falhas preexistentes, comprovadas no commit `0e04407`; nenhuma nova |

Cobertura de controle de acesso:
- **Anônimo:** não lê (banco: `InsufficientPrivilege`; REST: 401/403; navegador: a página protegida redireciona **sem nenhuma chamada REST**).
- **Isolamento entre usuários:** A vê só as categorias de A, e B só as de B, inclusive filtrando por `user_id` ou `id` alheio.
- **Sem escrita:** nenhum papel escreve (INSERT/UPDATE/DELETE no banco; POST/PATCH/DELETE via REST, e também pelo próprio navegador com token válido de A). Depois das tentativas, os dados de A estão intactos.
- **Tokens:** assinado com outro segredo, expirado, com `role: service_role` forjado e adulterado no `localStorage` são todos recusados, e a tela não mostra dados.
- **Outros:** login inválido mostra mensagem genérica e não grava sessão; sair limpa a sessão; `next` externo é ignorado.
- **Estrutura:** RLS forçada, policy única, grants exatos, `anon` sem acesso ao schema, schema novo sem herdar grants do `public`.

**Problemas encontrados durante a implementação (todos no ambiente de teste, não no produto):**
- `pg_ctl` travava com pipes no Windows;
- o servidor estático do Python resetava conexões, o que se resolveu com HTTP/1.1, leitura integral do corpo e arquivos em memória;
- um teste lia a tabela antes do carregamento assíncrono.

Foram corrigidos e documentados no código.

## 5. Compatibilidade e limitações

| Tema | Situação |
|---|---|
| Supabase Auth real | **Não exercitado** (simulado no E2E). Validar num ambiente com Auth real: Docker + `supabase start`, ou o projeto remoto depois da correção do §2 |
| PostgreSQL | Cluster local em 18; remoto em 17.6. Os recursos usados (RLS, policies, grants, identity) são idênticos |
| PostgREST | Local 16.5; a versão da Data API do Supabase pode diferir. Só recursos básicos (filtros, `Accept-Profile`) |
| Schema `financeiro` | Precisa ser exposto explicitamente na Data API (configuração do projeto) |
| Modelo de dono | O MVP usa `user_id` (usuário do Auth). O Flask usa perfis financeiros (`perfil_financeiro_id`), que precisam ser modelados antes de migrar os módulos financeiros |
| Usuários | Nenhum usuário ou senha migrado. O dono deve ser criado por convite no Supabase Auth; o login do Flask continua valendo |
| Frontend atual | Só o tema foi reaproveitado. As páginas atuais dependem das APIs Flask (`/api/...`) e de templates Jinja, então serão portadas módulo a módulo |

## 6. Plano de migração por módulos

Escala do que existe no Flask: cerca de **283 rotas de API**, **20,8 mil linhas** de serviços e 3 mil de modelos.

Cada módulo segue as 7 etapas do contrato:
1. inventário;
2. contratos das APIs Flask;
3. testes de referência do comportamento atual;
4. nova implementação;
5. comparação de resultados;
6. validação de segurança, transações, histórico e desempenho;
7. substituição só com equivalência comprovada.

| Ordem | Módulo | Rotas Flask | Abordagem | Risco |
|---|---|---|---|---|
| 0 | **Pré-requisitos:** correção do §2, cadastro público desligado, schema exposto, usuário dono por convite | — | Configuração do projeto | — |
| 1 | Categorias (leitura) | parte de 19 | ✅ **este MVP** | Baixo |
| 2 | Categorias (escrita) e palavras-chave | restante | RPCs `security definer` com validação e `revoke` de `PUBLIC` | Baixo |
| 3 | Perfis financeiros | 9 | Tabela de perfis + RLS por perfil do usuário | Médio (define o modelo de dono) |
| 4 | Contas bancárias e patrimônio (leitura) | 12 + 21 | Views/RLS; saldo calculado no banco | Médio |
| 5 | Receitas, despesas e recorrências | 18 + 9 + 7 | Leitura via RLS; escrita só por RPC transacional | Alto (saldos e histórico) |
| 6 | Dashboard | 8 | Views/RPC de agregação | Médio (desempenho) |
| 7 | IR e documentos | 37 | **Supabase Storage** com policies por usuário | Médio |
| 8 | Cartões, faturas, importação, estornos | 33 + 10 | RPC/Edge Function; comparação exaustiva com o Flask | Alto |
| 9 | Financiamentos (motor SAC/PRICE/TR) e consórcios | 25 + 6 | Decisão própria: manter o motor em Python como serviço, ou portar com testes de equivalência numérica | Muito alto |
| 10 | OCR, backup e scheduler | — | OCR como serviço externo; backups do Supabase Pro; `pg_cron` no lugar do APScheduler | Médio |

## 7. Custos adicionais potenciais

Valores de referência, a confirmar nos painéis.

| Serviço | Uso no MVP | Custo adicional |
|---|---|---|
| Cloudflare Pages | Site estático | US$ 0 no plano gratuito (limite de builds por mês) |
| Supabase (projeto existente `fzjmge…`) | Auth, Data API, Postgres | **Nenhum novo**: já está na organização Pro. Usar outro projeto acrescentaria custo de compute |
| Supabase Storage / Edge Functions | Módulos futuros | Dentro das franquias do Pro para uso pessoal; acima delas é cobrado (Spend cap ativado pode limitar) |
| Cloudflare Workers | Só se for necessário | US$ 0 no plano gratuito; US$ 5/mês no pago |
| Docker Desktop | Para validar o Auth real localmente | Gratuito para uso pessoal |

## 8. Validação final

| Verificação | Resultado |
|---|---|
| Projeto original continua funcionando | ✅ 1037 passed; só as 5 falhas preexistentes (`docs/STAGING_RENDER_2.md` §F) |
| Nova aplicação não depende do Flask para carregar | ✅ O E2E roda sem nenhum processo Flask |
| Não autenticado não lê dados protegidos | ✅ banco, REST e navegador |
| Nenhuma regra financeira alterada | ✅ nenhum arquivo de `backend/` modificado |
| Nenhum dado operacional migrado | ✅ só dados fictícios em cluster descartável |
| Nenhum segredo no repositório | ✅ varredura do diff; o build recusa chaves privilegiadas |
| Cluster, PostgREST e servidores encerrados ao final | ✅ verificado depois de cada execução |

## 9. Próxima etapa recomendada

1. **Autorizar a correção do §2** (tirar o `public` da Data API). É urgente e independe do resto.
2. **Validar o Auth real:** instalar Docker Desktop e rodar `supabase start` localmente, ou aplicar a migration no projeto remoto depois da correção, com cadastro desligado e usuário por convite. Isso exige autorização específica.
3. Só então: módulo 2 (escrita de categorias por RPC) e o desenho do modelo de perfis (módulo 3), seguindo as 7 etapas.
