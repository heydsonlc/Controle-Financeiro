# DEPLOY-READY-FIN-1 — Prontidão para publicação em `financeiro.kortexbrasil.com`

Data: 2026-10-19. Etapa de diagnóstico e correções controladas. **Nada foi publicado**: nenhum serviço criado no Render, nenhum DNS alterado, nenhuma migration executada no banco remoto, nenhuma regra financeira alterada, nenhum push.

Arquitetura aprovada (PROD-AUDIT-KORTEX-1): Controle Financeiro independente do Portal Kortex — Cloudflare (DNS do subdomínio) → Render (backend Flask) → Supabase próprio (`fzjmge…`, separado do projeto da Calculadora/Portal) → disco persistente para documentos. Autenticação própria (Flask-Login), sem SSO com o Portal.

---

## 1. Repositório, branch e framework

| Item | Resultado |
|---|---|
| Repositório | `github.com/heydsonlc/Controle-Financeiro`, branch `main` (única branch local e remota) |
| Framework | **Flask 3.0** (Flask-SQLAlchemy, Flask-Migrate/Alembic, Flask-Login). Frontend renderizado no servidor (Jinja, `frontend/templates`) |
| FastAPI | **Não existe** no repositório: nenhuma ocorrência de `fastapi`, `FastAPI` ou `uvicorn` em `.py`, `.md`, `.txt`, `.yaml` ou `.bat`. Menções anteriores a FastAPI não correspondem ao código |
| Comando de inicialização (host) | `gunicorn backend.app:app` — `backend/app.py` cria `app = create_app()` no import |
| Comando local | `python backend/app.py` (servidor de desenvolvimento, abre o navegador) |

## 2. Diagnóstico

### Comprovado nesta etapa

- **Banco staging acessível e no head.** Conexão somente leitura ao Supabase `fzjmge…`: `alembic_version = 5c91e95eb05d`, igual ao head do repositório; conexão com SSL ativo; 1 usuário ativo.
- **O host direto do banco é somente IPv6.** `db.fzjmge….supabase.co` não tem registro A, apenas AAAA (prefixo da AWS `us-east-2`, Ohio). O Render não abre conexões de saída IPv6, então a `DATABASE_URL` atual **não funcionaria no Render**. Os hosts do pooler da região (`aws-0/aws-1-us-east-2.pooler.supabase.com`) têm IPv4.
- **Filesystem.** O sistema grava em disco:
  - logos de categorias (`data/uploads/logos/categorias`);
  - documentos de financiamento (`data/uploads/financiamentos`);
  - área de trabalho do OCR (`data/ocr`);
  - backups locais (`data/backups`);
  - cenário ativo de mobilidade (`data/mobilidade_cenario_ativo.json`).

  **Comprovantes de IR ficam no banco** (`ir_comprovante_arquivo.conteudo`, BYTEA), não no disco.
- **Risco de execução de binário.** O backup local permitia configurar pela tela o caminho do `pg_dump`/`pg_restore` (`_caminho_executavel` aceita **qualquer arquivo**) e executá-lo, inclusive uma restauração contra o próprio banco configurado. Isso é aceitável numa máquina local, mas não num servidor público.
- **CSRF entre subdomínios.** `SameSite=Lax` não protege contra `portal.kortexbrasil.com` e `kortexbrasil.com`: eles pertencem ao mesmo *site* que `financeiro.kortexbrasil.com`, e o navegador envia o cookie em POSTs vindos deles. Endpoints que aceitam formulário/multipart (login, uploads) ficavam expostos a um XSS em qualquer sistema Kortex.
- **`render.yaml` desatualizado:**
  - `env: python` é a chave obsoleta (agora `runtime`);
  - o Render não lê `runtime.txt` (a versão vem de `PYTHON_VERSION`);
  - o plano `free` não admite disco persistente e "dorme" quando fica sem uso;
  - a região padrão (Oregon) fica longe do banco (Ohio).
- **Sessão sem expiração.** O cookie era de sessão do navegador, sem validade no servidor.
- **Sem limite de corpo de requisição** (`MAX_CONTENT_LENGTH`).
- **Sem cabeçalhos de segurança** (HSTS, nosniff, frame-options).

### Funcionalidades que dependem da máquina local (degradam sem quebrar)

| Recurso | No host | Situação |
|---|---|---|
| OCR (Tesseract/Poppler) | Binários ausentes no runtime Python nativo do Render | A tela informa "Tesseract não encontrado". Exigiria runtime Docker |
| Backup/restauração via `pg_dump` | Bloqueado no host (ver §3) | Backup do banco passa a ser responsabilidade do Supabase (§5, P2) |
| Agendador (APScheduler) | Desligado também no uso local (`app.py`) | Sem mudança |

## 3. Correções aplicadas

| Arquivo | Mudança |
|---|---|
| `backend/config.py` | `DATA_DIR` centraliza todos os diretórios graváveis. Obrigatório (e absoluto) em `production`; sem ele, mantém `data/` do projeto |
| `backend/config.py` | `HospedadoConfig` (base de staging/production): cookie `__Host-financeiro_session`, sessão com expiração de 12h sem uso, `MAX_CONTENT_LENGTH` de 64 MB, flag `AMBIENTE_HOSPEDADO` |
| `backend/config.py` | `DATABASE_URL` remota: `postgres://` → `postgresql://`; `sslmode=require` quando a URL não define; `pool_pre_ping`, `pool_recycle=300`, pool de 3+2 conexões por worker (compatível com o limite do Session pooler) |
| `backend/app.py` | Verificação de `Origin`/`Referer` em POST/PUT/PATCH/DELETE no ambiente hospedado. Aceita apenas o próprio host e `CORS_ORIGINS`; `Origin: null` é recusado |
| `backend/app.py` | Cabeçalhos no ambiente hospedado: HSTS (**sem** `includeSubDomains`, para não afetar Portal/site), `nosniff`, `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy: same-origin`. Em local não se aplicam (o Windows pode servir `.js` como `text/plain`, e o `nosniff` bloquearia os scripts) |
| `backend/app.py` | Login marca a sessão como permanente quando `SESSION_PERMANENTE` está ligada (só no host) |
| `backend/routes/backup.py` | No host, bloqueia com 403: executar backup, restaurar, testar restauração, configurar e autodetectar ferramentas. Status e histórico continuam disponíveis |
| `backend/routes/veiculos.py` | O cenário ativo de mobilidade passa a ser gravado em `DATA_DIR` |
| `render.yaml` | `runtime: python`, `region: ohio`, `plan: starter`, disco `/var/data` (1 GB), `PYTHON_VERSION=3.11.9`, `DATA_DIR=/var/data`, `CORS_ORIGINS=https://financeiro.kortexbrasil.com`, gunicorn com 2 workers e timeout de 120s, segredos com `sync: false` |
| `scripts/check_deploy_env.py` | Bloqueia a `DATABASE_URL` com host direto do Supabase; valida `DATA_DIR` |
| `scripts/smoke_staging.py` | Novas verificações: HSTS sem subdomínios, `nosniff`, POST de outro subdomínio → 403, atributos do cookie (`__Host-`, Secure, HttpOnly), backup local → 403 |
| `.env.example` | Documenta `DATA_DIR` |
| `tests/test_deploy_ready_fin.py` | 33 testes novos |
| `tests/test_deploy_prep.py` | 2 testes passam a definir `DATA_DIR` ao montar a config de `production` (mudança intencional: agora é obrigatório) |

O comportamento local e o dos testes ficam **inalterados**: todas as proteções novas dependem de `AMBIENTE_HOSPEDADO`, que só é verdadeiro em staging/production.

## 4. Bloqueadores para publicar o staging

Todos dependem de ação ou decisão do usuário, e nenhum é de código.

| # | Bloqueador | Ação |
|---|---|---|
| B1 | A `DATABASE_URL` atual usa o host direto (somente IPv6) | Supabase → *Connect* → **Session pooler** (host `aws-?-us-east-2.pooler.supabase.com`, usuário `postgres.<ref>`). Senha com URL-encoding. Validar com `scripts/check_deploy_env.py` |
| B2 | Uploads persistentes exigem plano pago no Render | Decidir entre: **(a)** `starter` + disco, já configurado no `render.yaml`, sem mudança de código; ou **(b)** manter `free` e migrar os uploads para o Supabase Storage (refatorar `categorias.py` e `financiamento_documento_service.py`; etapa STORAGE-2) |
| B3 | Serviço no Render ainda não existe | Criar via Blueprint (`render.yaml`) e informar `SECRET_KEY` (nova, `secrets.token_urlsafe(64)`), `DATABASE_URL` (pooler) e `CARTOES_CVV_MASTER_PASSWORD` |
| B4 | Domínio não configurado | Render → *Custom Domains* → `financeiro.kortexbrasil.com`; no Cloudflare, CNAME `financeiro` → `<servico>.onrender.com` como **DNS only** até o certificado ser emitido. Ao ligar o proxy, o modo SSL precisa ser *Full (strict)* — a configuração é da zona inteira, então aplicar só a este hostname via *Configuration Rule*, sem mexer no Portal/site |

## 5. Pendências antes de produção (não bloqueiam o staging)

| # | Pendência |
|---|---|
| P1 | **Limitar tentativas de login.** Não há rate limit no `POST /login`. Opção sem código: regra de rate limiting do Cloudflare para `financeiro.kortexbrasil.com/login` (exige proxy ligado). Opção mais forte: **Cloudflare Access** (Zero Trust, gratuito para poucos usuários) na frente do subdomínio, como segundo fator antes do login da aplicação. As health checks do Render não passam pelo Cloudflare |
| P2 | **Backups.** O backup local foi bloqueado no host. O plano gratuito do Supabase não oferece backups restauráveis pelo painel (o Pro oferece diários). Definir: Pro, ou `pg_dump` periódico da máquina local via pooler. Disco do Render: confirmar a política de snapshots do plano escolhido |
| P3 | **DATA-MIGRATE-1.** Migração seletiva dos dados reais e cópia dos arquivos de `data/uploads/financiamentos` e `data/uploads/logos` para o disco (hoje cerca de 56 KB) |
| P4 | **Produção.** `APP_ENV=production` agora exige `DATA_DIR`, e a aplicação recusa iniciar sem ele |
| P5 | **CSP.** Não configurada, porque os templates usam scripts inline. Avaliar numa etapa própria |
| P6 | **OCR no host.** Exigiria runtime Docker com `tesseract-ocr` e `poppler-utils` |
| P7 | **Testes já falhando antes desta etapa** (não relacionados a deploy): `test_categorias_sistemicas_mobilidade::test_projecoes_veiculo_usam_categorias_sistemicas_granulares`, `test_ocr_tools::test_status_sem_ferramentas_retorna_estrutura_valida`, `test_ocr_tools::test_poppler_ausente_retorna_aviso`, `test_receitas_ux::test_cards_resumo_calculam_previsto_realizado_diferenca_confiabilidade`, `test_veiculos_mobilidade_2b::test_suprimir_despesas_previstas_futuras` |

## 6. Checklist de staging

Na máquina local, antes de criar o serviço:

- [ ] `.env.staging` com a `DATABASE_URL` do **Session pooler**
- [ ] `scripts/check_deploy_env.py` com `.env.staging` carregado → exit 0
- [ ] Suíte `pytest` sem falhas novas em relação ao §5/P7

No Render:

- [ ] Blueprint aplicado a partir do `render.yaml` (plano/disco conforme B2)
- [ ] `SECRET_KEY`, `DATABASE_URL` e `CARTOES_CVV_MASTER_PASSWORD` preenchidos no painel (nunca no repositório)
- [ ] Primeiro deploy manual; log sem erro de configuração (`SECRET_KEY`/`DATABASE_URL`/`DATA_DIR`)
- [ ] Render Shell: `python -m flask --app backend/app.py db current` → `5c91e95eb05d` (não rodar `upgrade` sem decisão explícita)
- [ ] `/health` → `database_connected: true`

No Cloudflare:

- [ ] CNAME `financeiro` criado (DNS only), certificado emitido no Render
- [ ] Proxy ligado só depois, com *Full (strict)* restrito ao hostname

Testes de segurança (`BASE_URL=https://financeiro.kortexbrasil.com scripts/smoke_staging.py`):

- [ ] `/health` 200, página protegida → redirect para `/login`, API sem sessão → 401 JSON
- [ ] HSTS presente **sem** `includeSubDomains`; `nosniff` presente
- [ ] POST com `Origin: https://portal.kortexbrasil.com` → 403
- [ ] Com `SMOKE_ADMIN_EMAIL`/`SMOKE_ADMIN_SENHA` locais: login OK; cookie `__Host-`, Secure, HttpOnly; `POST /api/backup/executar` → 403
- [ ] Manual: `http://` redireciona para `https://` (Render/Cloudflare)
- [ ] Manual: enviar um documento de financiamento, fazer redeploy, e confirmar que o arquivo continua disponível (valida o disco)
- [ ] Manual: Portal e site institucional continuam respondendo normalmente (nenhuma mudança neles)

## 7. Testes executados nesta etapa

- Baseline antes das mudanças: 5 falhas preexistentes (§5/P7).
- Depois das mudanças: a mesma lista de falhas, nenhuma nova. `tests/test_deploy_ready_fin.py` passando por completo.
- Smoke local em modo `staging` (SQLite temporário): `/health` 200 com HSTS; anônimo → `/login`; login com `Origin` de outro subdomínio → 403; login same-origin → 302. Cookie: `__Host-financeiro_session; Expires=+12h; Secure; HttpOnly; Path=/; SameSite=Lax`.
- `check_deploy_env.py` com `.env.staging`: aponta corretamente o bloqueador B1 e o aviso de `DATA_DIR`.
