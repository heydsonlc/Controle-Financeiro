# web/ — frontend estático (Cloudflare Pages + Supabase)

Primeiro módulo da nova arquitetura (CF-SUPABASE-REFACTOR-1): login pelo **Supabase Auth** e **categorias em modo somente leitura**, protegidas por RLS. É **independente do Flask**: não chama nenhuma rota do backend atual. O Flask continua sendo a aplicação em uso e a implementação de referência.

**Ainda não publicado** no Cloudflare. Validado contra o Supabase real no AUTH-REAL-1 (`docs/AUTH_REAL_1.md`). A migration de perfis (PERFIS-1) ainda não foi aplicada no remoto.

## Estrutura

| Caminho | Conteúdo |
|---|---|
| `src/index.html` | Login (Supabase Auth, e-mail e senha) |
| `src/contas.html` + `src/js/contas.js` | **Tela inicial: Contas do mês** (MOBILE-CONTAS-1), somente leitura, mobile |
| `src/categorias.html` | Tela protegida provisória: seletor de perfil, contas bancárias do perfil ativo (PERFIS-1) e categorias, só leitura |
| `src/js/perfil.js` | Perfis autorizados (`meus_perfis`) e perfil ativo por usuário no `sessionStorage` (só preferência; o banco revalida) |
| `src/js/cliente.js` | Cliente Supabase único (`storageKey` próprio, schema `financeiro`) |
| `src/js/sessao.js` | Guarda de sessão com `getUser()` (valida o token no servidor); `next` restrito a uma allowlist |
| `src/css/app.css` | Estilos próprios. O tema vem de `frontend/static/css` no build |
| `scripts/build.mjs` | Gera `dist/` (config pública, `_headers` com CSP, tema, supabase-js) e falha fechado com segredo |
| `tests/unit/` | Testes do build (`node:test`) |
| `tests/e2e/` | Playwright + `run_e2e.py`, o ambiente isolado |

## Build

```bash
cd web
npm ci
SUPABASE_URL=https://<ref>.supabase.co SUPABASE_PUBLISHABLE_KEY=sb_publishable_... npm run build
```

O build **recusa**:
- chave `sb_secret_...` ou JWT com role diferente de `anon`;
- o projeto Supabase da Calculadora Judicial;
- URL sem https;
- qualquer `service_role`, `DATABASE_URL` ou `postgres://` dentro de `dist/`.

Só o build de teste aceita `http://127.0.0.1`, e apenas com `--local`.

## Testes

```bash
cd web && npm run test:unit                                   # build e regras do código-fonte
set POSTGREST_BIN=C:\caminho\postgrest.exe                     # binário oficial do PostgREST
venv\Scripts\python.exe web\tests\e2e\run_e2e.py              # E2E (da raiz do repositório)
```

O E2E sobe, só em `127.0.0.1` e com dados fictícios:
- um cluster PostgreSQL **descartável**, com a migration real e a RLS;
- o **PostgREST**, a mesma camada REST do Supabase;
- um servidor que entrega `dist/` com a CSP real do `_headers`.

**A única parte simulada é o Supabase Auth**: endpoints `/auth/v1/token`, `/user` e `/logout`, que emitem JWTs reais assinados com o mesmo segredo que o PostgREST valida. Ao terminar, tudo é derrubado.

## Regras deste frontend

- O navegador **só lê**. Escrita futura apenas por RPC transacional validada no banco, nunca `insert`/`update`/`delete` diretos (verificado em `tests/unit`).
- Nada de `innerHTML` com dados do banco (verificado em `tests/unit`).
- A guarda de página é experiência de uso; quem protege os dados é a **RLS**.
- Nunca usar o projeto Supabase nem a sessão da Calculadora Judicial.
