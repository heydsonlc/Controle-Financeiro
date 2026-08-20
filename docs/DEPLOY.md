# Deploy — Controle Financeiro

Guia de preparação e execução do deploy. Última atualização: 2026-08-20 (SUPABASE-MIGRATE-1).

Este documento cobre **o que já está pronto** e **o que ainda depende de ação manual** para sair do uso puramente local. O banco Supabase (staging) já foi validado com a cadeia completa de migrations; deploy real do backend, Cloudflare e migração de dados financeiros locais ainda não foram feitos.

---

## 1. Visão geral do deploy planejado

```
Cloudflare  → DNS / proxy / (futuramente) frontend estático
Backend Flask → hospedado em serviço compatível (a definir), fora do Cloudflare
Supabase → PostgreSQL gerenciado (staging validado no SUPABASE-MIGRATE-1), substitui o PostgreSQL local
```

Ordem de dependência: **SEG-1 (concluído) → DEPLOY-PREP-1 (concluído) → SUPABASE-MIGRATE-1 (banco staging validado) → DEPLOY-HOST-1 (host do Flask) → CLOUDFLARE-1 (DNS/proxy)**. Repositório é público — sem SEG-1 e sem este preparo, publicar a URL do backend seria expor dados financeiros reais sem proteção.

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
| `CORS_ORIGINS` | Se frontend/backend forem separados | Nunca usar `*`; listar origens explícitas (ex.: domínio Cloudflare futuro) |

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
2. A conexão **direta** (porta `5432`) foi a usada para rodar as migrations — é a que permite DDL sem restrições. O modo **pooler** (transaction/session pooling, porta `6543`) é recomendado para a aplicação em produção com múltiplos workers, mas pode ter restrições para `ALTER TABLE`/DDL; use a direta para `flask db upgrade` e avalie o pooler separadamente para a conexão de runtime da aplicação.
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

## 7. Cloudflare / hospedagem do backend

**Ainda não configurado.** Papel esperado de cada peça:

- **Cloudflare**: DNS do domínio e proxy (e, futuramente, hospedagem do frontend estático caso ele seja separado do Flask). Cloudflare **não hospeda o backend Flask** — Workers/Pages não rodam uma aplicação Flask tradicional.
- **Backend Flask**: precisa de um host próprio compatível com WSGI (a definir — fora do escopo desta etapa). O `requirements.txt` ainda não lista um servidor WSGI de produção (ex.: gunicorn); isso é tarefa do DEPLOY-HOST-1, não deste documento.

---

## 8. Cookies e sessão

Já configurado em `backend/config.py` por ambiente:

- `SESSION_COOKIE_HTTPONLY=True` sempre (JavaScript nunca lê o cookie de sessão)
- `SESSION_COOKIE_SAMESITE=Lax` sempre
- `SESSION_COOKIE_SECURE=True` em `staging`/`production` (exige HTTPS — se o deploy real ficar sem HTTPS, o cookie de sessão não será enviado e o login não vai funcionar; isso é intencional)
- `SESSION_COOKIE_SECURE=False` em `local` (sem HTTPS local)

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

- **DEPLOY-HOST-1**: escolher e configurar o host do backend Flask (servidor WSGI de produção, ex.: gunicorn, ainda não está em `requirements.txt`)
- **CLOUDFLARE-1**: configurar DNS/proxy no Cloudflare apontando para o host do backend
- **DATA-MIGRATE-1** (se desejado no futuro): migração seletiva de dados financeiros locais reais para o Supabase — não foi feita nesta etapa por decisão explícita (nenhum dado financeiro real foi migrado, só schema + usuário admin)
- **DB-CLEAN**: débitos técnicos de `models.py`/queries, não relacionados a deploy
- RBAC/multiusuário: fora de escopo (SEG-1 é usuário único)
- Comercialização/pagamentos: fora de escopo
