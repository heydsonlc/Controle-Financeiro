# AMBIENTE-EQUIPARACAO-1 — Equiparação do ambiente de desenvolvimento (casa × notebook)

**Data:** 2026-10-22.

**Situação:** notebook equiparado ao computador de casa e validado, com as mesmas ferramentas e os mesmos resultados de teste. A finalização (AMBIENTE-EQUIPARACAO-2) está no §8.

**Autorização:** SCRIPT-CONTRATO V5 — AMBIENTE-EQUIPARACAO-1 e AMBIENTE-EQUIPARACAO-2. O push do `b669d5d` foi autorizado no segundo.

**Não foi feito:**
- migration remota (`20261029090000` continua pendente);
- Alembic no `gastos.db`;
- dados reais;
- publicação no Cloudflare, DNS ou criação de projetos;
- FIN-CARTOES-FECHAMENTO-1.

## 1. Cópia de trabalho

| Item | Situação |
|---|---|
| Pasta do OneDrive | Preservada. `git fsck` sem erros; nenhum arquivo rastreado modificado |
| Nova cópia | `C:\Users\ssp\dev\Controle-Financeiro`, fora do OneDrive. Clone do GitHub e `fetch` do repositório do OneDrive com fast-forward, para trazer o `b669d5d` com o histórico |
| Uso simultâneo | Há cópias de conflito do OneDrive do `gastos.db` e do `.git/gk/config` (gravado pela extensão GitLens). Não foram tocadas. Regra: Git só na nova cópia, com a pasta do OneDrive fechada no VS Code |
| Fim de linha | O clone usa CRLF (`core.autocrlf=true`); arquivos criados na casa estão com LF. Os blobs do Git são idênticos |

## 2. Ferramentas

| Componente | Requerido pelo projeto | Notebook | Providência |
|---|---|---|---|
| Python | 3.11.9 (`runtime.txt`) | 3.11.9 | venv próprio no clone; 45 pacotes nas mesmas versões do venv da casa |
| PostgreSQL | 18 (testes com `initdb`/`pg_ctl`) | 18.0, serviço local | `bin` no PATH do usuário |
| PostgREST | 16.5 | 16.5 oficial, SHA-256 conferido | `POSTGREST_BIN` (variável do usuário) |
| Node.js / npm | ≥ 22 | 24.11.1 / 11.6.2 | `npm ci` na raiz e em `web/` |
| Playwright | 1.59.1 (lockfile) | 1.59.1 + Chromium 1217 | navegador instalado |
| Git | — | 2.51.2 + Git Credential Manager | identidade local igual à da casa |
| Supabase CLI | — | 2.116.0 (Scoop), autenticada | — |
| Wrangler | 4.129.0 (`web/package.json`, §8) | 4.129.0, autenticado | devDependency exata |
| Docker | não usado (testes sem Docker) | ausente | desnecessário |
| Alembic | 1.19.1, head `f1c4d8e2a7b9` | 1.19.1 | — |

- O PostgREST para Windows depende da `libpq.dll` do PostgreSQL: sem o `bin` no PATH, encerra com `0xC0000135`.
- O antivírus do notebook bloqueia os `.exe` que o pip cria no venv (`flask.exe`, `pytest.exe`, `alembic.exe`). Usar `venv\Scripts\python.exe -m pytest` (ou `-m flask`, `-m alembic`), forma já usada nesta documentação.
- Não atualizados por decisão, embora haja versões novas: PostgreSQL 18.6, Node 24.22.1, Supabase CLI 2.121.0 e Wrangler 4.152.0.
- Tesseract e Poppler não foram instalados: o OCR hoje só valida as ferramentas (§5).
- As versões Python transitivas da casa ficaram registradas num arquivo de constraints fora do repositório.

## 3. Serviços externos

| Serviço | Resultado |
|---|---|
| GitHub | Leitura, autenticação e push (§8) |
| Supabase (`fzjmge…`) | CLI autenticada; pooler acessível; `status` e `simular` somente leitura |
| Cloudflare | Autenticado via OAuth (§8); projetos Pages listados só para leitura |
| npm, PyPI, CDN do Playwright | Instalações feitas pela rede do notebook |

Nenhum bloqueio de rede.

## 4. Banco pessoal e migrations

- `gastos.db` (OneDrive): lido uma vez em modo imutável, só para conferir a revisão: `9b8a09ecc52f`, 6 revisões atrás do head. Data e tamanho do arquivo inalterados. Nenhum `alembic upgrade`.
- Cadeia Alembic: 29 revisões, base `dd1a552aec6a`, head único `f1c4d8e2a7b9`. Num PostgreSQL 18 descartável, as 29 sobem do zero.
- SQLite do zero: a baseline usa ALTER de constraint, que o SQLite não suporta. É limitação conhecida (o SQLite é legado); as migrations incrementais em SQLite são testadas pela suíte.

## 5. Testes

| Conjunto | Notebook | Casa |
|---|---|---|
| Financeiros (8 arquivos dos 6 módulos FIN) | 239 passed | 239 |
| Suíte completa (`venv\Scripts\python.exe -m pytest`) | 3 failed, 1471 passed | 5 failed, 1450 passed, 19 skipped |
| Unitários `web/` | 7/7 | — |
| E2E do novo aplicativo (`web/tests/e2e/run_e2e.py`) | 47 passed | 47 |
| E2E legado do Flask (`npx playwright test`, na raiz) | 20 failed, 5 skipped | — |

- As 3 falhas são 3 das 5 preexistentes: `test_categorias_sistemicas_mobilidade`, `test_receitas_ux` e `test_veiculos_mobilidade_2b`.
- As 2 falhas de OCR da casa vêm de Tesseract e Poppler instalados lá (`STAGING_RENDER_2.md`); sem eles, os testes passam.
- Os 19 ignorados da casa são os testes REST sem `POSTGREST_BIN`: rodando sem a variável, o notebook ignora exatamente 19.
- **E2E legado do Flask:** as specs de `tests/e2e` são de maio de 2026 e não fazem login. Desde o SEG-1 (agosto de 2026) toda página exige sessão, e elas param na tela "Entre para continuar"; os 5 ignorados são rotas diagnósticas marcadas como `skip`. É falha das specs, **não** regressão do novo aplicativo nem do ambiente: o E2E do novo aplicativo passa 47/47.
- **Clone novo sem `.env.local`:** a coleta do pytest falha com "unable to open database file", porque o app criado na importação cai no fallback SQLite, que exige a pasta `data/`. Ter o `.env.local` ou criar `data\` vazia resolve.

## 6. Integridade

- Pasta do OneDrive: nenhum arquivo do projeto alterado. As únicas gravações foram caches: `supabase/.temp/cli-latest` (CLI do Supabase) e o cache de stat do `.git/index` (`git status`).
- Supabase remoto: nenhuma migration aplicada e nenhum dado gravado; `run_e2e_real.py` não foi executado.
- Cloudflare: nenhuma alteração.

## 7. Recomendações

- Revisar a configuração de autenticação local (`pg_hba.conf`) do PostgreSQL do notebook. Exige administrador.
- Atualizações disponíveis (PostgreSQL 18.6, Node 24.22.1, Supabase CLI 2.121.0, Wrangler 4.152.0) só quando houver motivo.
- Specs do E2E legado do Flask: incluir login ou aposentá-las, em etapa própria.

## 8. Finalização — AMBIENTE-EQUIPARACAO-2

| Item | Resultado |
|---|---|
| Push | `b669d5d` revisado: 12 arquivos de texto, sem segredos, dados pessoais ou arquivos indevidos (só credenciais fictícias de teste). Enviado (`7460f00..b669d5d`). O check "Supabase Preview" ficou `completed/skipped`, e `20261029090000` continuou pendente antes e depois do push |
| Arquivos de ambiente | `.env.local`, `.env.staging` e `.env.e2e-real` copiados para o clone: idênticos à origem, ignorados pelo Git, acesso restrito ao usuário, SYSTEM e Administradores. Nenhum caminho absoluto da outra máquina; nenhuma credencial nova |
| PostgreSQL de desenvolvimento | `controle_financeiro_dev` não existia. Criado vazio, com role sem privilégios elevados e a credencial já existente do `.env.local`. Migrations verificadas antes num cluster descartável e aplicadas (head `f1c4d8e2a7b9`). Contém só os dados-padrão inseridos pelas migrations. Flask local com `/health` conectado ao banco |
| Cloudflare | Wrangler autenticado; token com `pages (write)`; é a conta que hospeda os projetos Pages da Kortex. Somente leitura |
| Wrangler reproduzível | `wrangler` 4.129.0 como devDependency exata em `web/package.json` e no lockfile. `npm ci` reproduz; `npx wrangler` usa a versão local; `test:unit` 7/7 |
| Validação final | Suíte completa `3 failed, 1471 passed` (as mesmas 3 preexistentes); E2E do novo aplicativo 47 passed |

**Sem commit:** este documento e a fixação do Wrangler (`web/package.json`, `web/package-lock.json`) aguardam decisão.

**Para entrar na aplicação local:** criar o usuário com `venv\Scripts\python.exe scripts\criar_admin.py --email <e-mail>` (a senha é pedida no prompt).
