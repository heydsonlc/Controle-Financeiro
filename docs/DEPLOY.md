# Deploy — Controle Financeiro

Guia de preparação e execução do deploy. Última atualização: 2026-10-19 (STAGING-RENDER-2). Diagnóstico: `docs/DEPLOY_READY_FIN_1.md`. Procedimento de staging: `docs/STAGING_RENDER_1.md`. Estado da preparação: `docs/STAGING_RENDER_2.md`.

Este documento cobre **o que já está pronto** e **o que ainda depende de ação manual** para sair do uso puramente local. O banco Supabase (staging) já foi validado com a cadeia completa de migrations; o backend está preparado para deploy no Render (`render.yaml`, `runtime.txt`, `gunicorn`), mas o deploy real (publicar o serviço no painel do Render e configurar as variáveis de ambiente) depende de ação manual do usuário. Cloudflare e migração de dados financeiros locais ainda não foram feitos.

---

## 1. Visão geral do deploy planejado

```
Cloudflare  → DNS de financeiro.kortexbrasil.com (zona kortexbrasil.com, independente do Portal Kortex)
Backend Flask → Render (staging), servido via gunicorn, disco persistente em /var/data
Supabase → PostgreSQL gerenciado (staging validado no SUPABASE-MIGRATE-1), substitui o PostgreSQL local
```

Ordem de dependência: **SEG-1 (concluído) → DEPLOY-PREP-1 (concluído) → SUPABASE-MIGRATE-1 (concluído) → DEPLOY-HOST-1 (preparado; publicação manual pendente) → CLOUDFLARE-1 (DNS/proxy)**. Repositório é público — sem SEG-1 e sem este preparo, publicar a URL do backend seria expor dados financeiros reais sem proteção.

---

## 2. Ambientes

A aplicação reconhece três ambientes via `APP_ENV` (variável oficial; `FLASK_ENV` continua funcionando como alias de compatibilidade — `development` é sinônimo legado de `local`):

| Ambiente | Uso | Comportamento |
|----------|-----|----------------|
| `local` | Sua máquina, desenvolvimento | Aceita `SECRET_KEY` default, permite banco local ou fallback SQLite, `SESSION_COOKIE_SECURE=False` (sem HTTPS local) |
| `staging` | Ambiente de teste antes de produção (futuro) | Exige `SECRET_KEY` forte e `DATABASE_URL`, `SESSION_COOKIE_SECURE=True` |
| `production` | Ambiente real, dados reais (futuro) | Mesmas exigências de `staging`, falha fechado (a aplicação recusa iniciar sem configuração adequada) |

---

## 3. Variáveis de ambiente obrigatórias

Ver `.env.example` para o arquivo completo com comentários. Resumo:

| Variável | Obrigatória em | Observação |
|----------|-----------------|------------|
| `APP_ENV` | Sempre recomendado | `local`, `staging` ou `production` |
| `SECRET_KEY` | staging/production (bloqueante) | Assina cookie de sessão de login. Mínimo 32 caracteres, sem valores de exemplo/dev/teste |
| `DATABASE_URL` | staging/production (bloqueante) | String de conexão PostgreSQL (SQLAlchemy) |
| `CARTOES_CVV_MASTER_PASSWORD` | staging/production, apenas se houver cartão com CVV cadastrado | Senha de desbloqueio do CVV (CARD-CVV-LOCK-1) |
| `FLASK_APP` | Sempre | `backend/app.py` |
| `FLASK_DEBUG` | Sempre | Deve ser `false`/`0` fora de `local` |
| `FLASK_HOST` / `FLASK_PORT` | Local (dev server) | Não relevante atrás de um WSGI server real |
| `CORS_ORIGINS` | staging/production | Nunca usar `*`. No host: `https://financeiro.kortexbrasil.com` — também é a allowlist da verificação de `Origin` em requisições de escrita |
| `DATA_DIR` | production (bloqueante); staging (recomendado) | Raiz absoluta dos arquivos gravados em runtime (uploads, OCR, backups locais). No Render: `/var/data` (disco persistente) |

### Como gerar uma `SECRET_KEY` forte

```bash
venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

---

## 4. O que nunca commitar

- `.env`, `.env.local`, `.env.staging`, `.env.production` (todos gitignorados; só `.env.example` é versionado)
- Qualquer valor real de `SECRET_KEY`, `DATABASE_URL` ou `CARTOES_CVV_MASTER_PASSWORD`
- Dumps de banco com dados reais
- Screenshots ou logs que exponham dados financeiros reais

Como o repositório é **público**, qualquer segredo commitado é considerado comprometido no instante do push — trocar a variável, não apenas remover o commit.

---

## 5. Checagem automática antes de subir

```bash
venv\Scripts\python.exe scripts\check_deploy_env.py
```

Valida (sem nunca imprimir valores reais): `SECRET_KEY` adequada ao ambiente, `DATABASE_URL` presente e usando PostgreSQL, `CARTOES_CVV_MASTER_PASSWORD` adequada quando há cartão com CVV cadastrado, `FLASK_DEBUG` desligado fora de `local`. Exit code `1` se algo estiver inadequado — use isso como gate antes de qualquer deploy real.

---

## 6. Banco de dados — Supabase

**Projeto Supabase criado pelo usuário (fora desta ferramenta) e validado como banco `staging` no SUPABASE-MIGRATE-1**: cadeia completa de migrations rodada do zero com sucesso (52 tabelas, `alembic_version` no head), usuário admin criado, smoke tests de login/CRUD passando.

1. Use a connection string em formato compatível com SQLAlchemy: `postgresql://usuario:senha@host:porta/dbname` (funciona com o driver `psycopg2-binary` já usado no projeto; `postgresql+psycopg2://` também funciona se preferir ser explícito).
2. A conexão **direta** (`db.<ref>.supabase.co:5432`) foi a usada para rodar as migrations da máquina local. **Ela só tem IPv6, e o Render não abre conexões de saída IPv6** (DEPLOY-READY-FIN-1). No Render, use a connection string do **Session pooler** (`aws-?-us-east-2.pooler.supabase.com:5432`, usuário `postgres.<ref>`), que tem IPv4 e aceita DDL — serve tanto para a aplicação quanto para `flask db upgrade` via Render Shell. `scripts/check_deploy_env.py` recusa o host direto em staging/production. A aplicação aplica `sslmode=require`, `pool_pre_ping` e um pool pequeno (3+2 por worker) automaticamente.
3. **Nunca** use a `service_role key` nem a `anon key`/`publishable key` do Supabase como `DATABASE_URL` — essas chaves são para a API REST/SDK JS do Supabase (`@supabase/supabase-js`), não para a conexão Postgres direta que este projeto usa. O quickstart padrão do painel Supabase (Next.js + SDK JS) **não se aplica** a este projeto Flask/Python.
4. **Senhas com caracteres especiais** (`@`, `*`, etc.) precisam de URL-encoding na connection string (`urllib.parse.quote(senha, safe='')`) — do contrário o parser da URL quebra a divisão usuário/senha/host.
5. Nunca exponha nenhuma credencial do Supabase no JavaScript do frontend — o frontend deste projeto não fala com o Supabase diretamente, só o backend Flask via `DATABASE_URL`.
6. Depois de apontar `DATABASE_URL` para o Supabase:
   ```bash
   flask db upgrade
   venv\Scripts\python.exe scripts\criar_admin.py --email seu@email.com
   venv\Scripts\python.exe scripts\check_supabase_db.py
   ```
7. Testar login e `/health` (deve retornar `database_connected: true`) antes de considerar a migração concluída.

### Achado importante: drift de schema pré-existente

A cadeia de migrations tinha bugs reais de drift, não relacionados a esta etapa — 6 tabelas (`categoria_cartao`, `categoria_palavra_chave`, `categoria_cartao_despesa`, `cartao_categoria_limite`, `mobilidade_assinatura`, `mobilidade_cenario_ativo`) e várias colunas (`item_despesa.categoria_cartao_id`/`origem_tipo`/`origem_id`/`origem_contexto`, `lancamento_agregado.categoria_cartao_id`, `financiamento_documento.parcela_id`/`amortizacao_id`/`ajuste_saldo_id`) nunca foram criadas por nenhuma migration — só existiam em bancos locais mais antigos por terem sido criadas fora do Alembic (provavelmente `db.create_all()` num ponto anterior ao baseline). Isso funcionava silenciosamente porque nenhum banco tinha sido criado do zero via `flask db upgrade` desde então. Corrigido com uma nova migration (`9e67ec16977b`) e ajustes defensivos em `9b8a09ecc52f`, ambos guardados por checagem de existência via SQLAlchemy inspector — no-op em bancos onde o drift já existia (ex.: o banco local), cria o que faltava em bancos novos (Supabase).

---

## 7. Hospedagem do backend — Render (staging)

**Preparado no DEPLOY-HOST-1; publicação do serviço no painel do Render é ação manual.**

- **Cloudflare**: DNS do domínio e proxy (e, futuramente, hospedagem do frontend estático caso ele seja separado do Flask). Cloudflare **não hospeda o backend Flask** — Workers/Pages não rodam uma aplicação Flask tradicional. Fica para o CLOUDFLARE-1.
- **Backend Flask**: hospedado no Render via `render.yaml`. `requirements.txt` já lista `gunicorn`. A versão do Python vem de `PYTHON_VERSION` no `render.yaml` (o Render não lê `runtime.txt`, mantido apenas como referência).

### Configuração do serviço (`render.yaml`)

| Item | Valor |
|------|-------|
| Build command | `pip install -r requirements.txt` |
| Start command | `gunicorn backend.app:app --workers 2 --timeout 120 --access-logfile -` (usa a instância `app` já criada no import do módulo — não `create_app()`, para não instanciar o Flask app duas vezes) |
| Plano / região / disco | `starter` / `ohio` (mesma região AWS do Supabase de staging) / disco `controle-financeiro-data` em `/var/data` (1 GB) |
| Health check path | `/health` |
| Porta | Automática — o Gunicorn usa `0.0.0.0:$PORT` por padrão quando a env var `PORT` existe (o Render sempre injeta), sem precisar de `--bind` explícito |
| Auto-deploy | Desligado (`autoDeploy: false`) — deploy é disparado manualmente até staging estar validado |

`render.yaml` **não contém nenhum segredo** — `SECRET_KEY`, `DATABASE_URL` e `CARTOES_CVV_MASTER_PASSWORD` são declarados com `sync: false`: o Render pede o valor no painel ao aplicar o Blueprint, e eles nunca ficam no arquivo versionado.

### Variáveis de ambiente a configurar no painel do Render

```
APP_ENV=staging
SECRET_KEY=<gerar com secrets.token_urlsafe(64), nunca reaproveitar a do .env.local>
DATABASE_URL=<connection string do Session pooler do Supabase — NÃO o host direto db.<ref>.supabase.co>
CARTOES_CVV_MASTER_PASSWORD=<forte, ou vazio se nenhum cartão com CVV for usado em staging>
FLASK_APP=backend/app.py
FLASK_DEBUG=0
DATA_DIR=/var/data
CORS_ORIGINS=https://financeiro.kortexbrasil.com
PYTHON_VERSION=3.11.9
```

(As quatro últimas já vêm do `render.yaml`.) `APP_ENV=staging` ativa automaticamente (via `HospedadoConfig`) a validação de `SECRET_KEY`/`DATABASE_URL`, o cookie `__Host-` com `Secure`, a expiração de sessão, os cabeçalhos de segurança, a verificação de `Origin` e o bloqueio do backup local — ver seção 8.

### Migrations no Render

Depois do primeiro deploy, rodar via Render Shell (não no build automático — migrations DDL são deliberadas, nunca disparadas por push):

```bash
python -m flask --app backend/app.py db current
python -m flask --app backend/app.py db upgrade
python -m flask --app backend/app.py db current
```

Como o Supabase já foi migrado no SUPABASE-MIGRATE-1 (`alembic_version = 5c91e95eb05d`), `db upgrade` deve ser um no-op se a `DATABASE_URL` configurada no Render apontar para o mesmo banco.

### Validação local do smoke test

```bash
set BASE_URL=https://<url-do-servico>.onrender.com
venv\Scripts\python.exe scripts\smoke_staging.py
```

Testa `/health`, redirect de página protegida sem sessão, 401 JSON de API sem sessão, e `GET /login`. Login com credenciais reais é opcional — só roda se `SMOKE_ADMIN_EMAIL`/`SMOKE_ADMIN_SENHA` estiverem definidas localmente (nunca versionadas, nunca impressas).

### Armazenamento de arquivos (STORAGE-1 — preparado no DEPLOY-READY-FIN-1)

Tudo o que é gravado em runtime fica abaixo de `DATA_DIR`: logos de categorias, documentos de financiamento, OCR, backups locais e o cenário ativo de mobilidade. Comprovantes de IR ficam no banco (BYTEA). O filesystem do Render é efêmero; o `render.yaml` monta um disco persistente em `/var/data` (`DATA_DIR=/var/data`), o que exige o plano pago `starter`. Alternativa sem disco: migrar os uploads para o Supabase Storage (STORAGE-2, exige refatoração).

---

## 8. Cookies e sessão

Já configurado em `backend/config.py` por ambiente:

- `SESSION_COOKIE_HTTPONLY=True` sempre (JavaScript nunca lê o cookie de sessão)
- `SESSION_COOKIE_SAMESITE=Lax` sempre
- `SESSION_COOKIE_SECURE=True` em `staging`/`production` (exige HTTPS — se o deploy real ficar sem HTTPS, o cookie de sessão não será enviado e o login não vai funcionar; isso é intencional)
- `SESSION_COOKIE_SECURE=False` em `local` (sem HTTPS local)

Em `staging`/`production` (`AMBIENTE_HOSPEDADO`, DEPLOY-READY-FIN-1):

- Cookie `__Host-financeiro_session` (sem `Domain`: nenhum outro subdomínio `*.kortexbrasil.com` consegue sobrescrevê-lo)
- Sessão permanente com expiração de 12h sem uso (`PERMANENT_SESSION_LIFETIME`)
- POST/PUT/PATCH/DELETE com `Origin`/`Referer` diferente do próprio host ou de `CORS_ORIGINS` → 403. `SameSite=Lax` sozinho não protege contra o Portal ou o site institucional, que são o mesmo *site*
- HSTS (sem `includeSubDomains`), `nosniff`, `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy: same-origin`
- Limite de 64 MB por requisição (`MAX_CONTENT_LENGTH`)
- Backup/restauração via `pg_dump`/`pg_restore` e configuração de executáveis → 403

---

## 9. Healthcheck

`GET /health` é pública (allowlist do SEG-1) e minimalista de propósito:

```json
{
  "status": "ok",
  "app_env": "production",
  "database_connected": true
}
```

Nunca expõe `DATABASE_URL`, `SECRET_KEY`, dados de usuário ou variáveis de ambiente.

---

## 10. Passo a passo — criar o usuário de acesso

Toda rota exige login desde o SEG-1. Depois de `flask db upgrade` no ambiente de destino:

```bash
venv\Scripts\python.exe scripts\criar_admin.py --email seu@email.com
```

Pede a senha no prompt (nunca aparece no terminal, nunca é salva em arquivo). Para redefinir a senha de um usuário já existente, use `--reset`.

---

## 11. Pendências

- **Publicação real no Render**: criar o serviço no painel (ou via `render.yaml` blueprint), configurar as variáveis de ambiente sensíveis, disparar o primeiro deploy manual e rodar as migrations via Render Shell — ação manual do usuário, não feita por esta ferramenta
- **Staging**: B1 (Session pooler) e B2 (Render Starter com disco) resolvidos no STAGING-RENDER-2. Falta a autorização para criar o Web Service pago (B3); o domínio (B4) vem depois do staging validado
- **CLOUDFLARE-1**: CNAME `financeiro` → Render (DNS only até o certificado; *Full (strict)* só para este hostname). Rate limit em `/login` ou Cloudflare Access
- **Backups**: o Supabase Pro faz backups diários do PostgreSQL (confirmados), mas falta testar a restauração. Os documentos do disco precisam de backup independente (BACKUP-DOCS-1): o snapshot do Render não substitui
- **SEG-2**: limitar tentativas de login — bloqueador de produção
- **DATA-MIGRATE-1** (se desejado no futuro): migração seletiva de dados financeiros locais reais para o Supabase — não foi feita nesta etapa por decisão explícita (nenhum dado financeiro real foi migrado, só schema + usuário admin)
- **DB-CLEAN**: débitos técnicos de `models.py`/queries, não relacionados a deploy
- RBAC/multiusuário: fora de escopo (SEG-1 é usuário único)
- Comercialização/pagamentos: fora de escopo
