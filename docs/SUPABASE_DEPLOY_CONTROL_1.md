# SUPABASE-DEPLOY-CONTROL-1 — Controle da aplicação automática de migrations

Data: 2026-10-21. Diagnóstico e preparação. **Nenhuma configuração remota foi alterada**, nenhuma migration executada, nada publicado.

## 1. Mecanismo identificado

**A integração GitHub do Supabase, com o projeto do Controle Financeiro tendo `main` como branch de produção.** A cada push em `main`, o GitHub App `supabase` aplica as migrations novas de `supabase/migrations` no banco.

| Evidência | Fonte |
|---|---|
| Não há GitHub Actions nem nunca houve (`.github/workflows` inexistente no histórico) | repositório |
| Não há `supabase/config.toml` no repositório | repositório |
| Cada push em `main` recebe o check **"Supabase Preview"** do app **`supabase`** | `gh api .../commits/<sha>/check-runs` |
| Branch padrão do projeto vinculada à Git branch **`main`** (`is_default: true`, `project_ref` = o próprio projeto), criada em 2026-08-20 junto com o projeto | `supabase branches list` (somente leitura) |
| `d04eb9d` (com `20261021090000`): check entre **00:54:26 e 00:54:30 UTC**. Às 00:54 a migration estava **pendente** no `--dry-run`; segundos depois, **aplicada**, sem nenhum comando de aplicação meu | check-run + histórico `supabase_migrations` |
| `0ee59f6` (com `20261020120000`): check às 09:52:33 UTC; a migration apareceu aplicada depois, sem comando meu | idem |
| Documentação oficial: com **"Deploy to production"** ligado, push/merge na branch de produção aplica migrations novas (e Edge Functions/buckets declarados no `config.toml`) | supabase.com/docs: GitHub integration |

Estado do histórico: as duas migrations aplicadas são **idênticas** aos arquivos do repositório (conferido no PERFIS-REAL-1). Nada a corrigir no banco.

## 2. Alternativas avaliadas

| Opção | Efeito | Recomendação |
|---|---|---|
| **Desligar "Deploy to production"** (*Project Settings → Integrations → GitHub*) | Para a aplicação automática na produção; mantém a conexão com o GitHub | **Recomendada:** menor mudança, direta na causa, não afeta Auth, Data API nem o frontend |
| `[db.migrations] enabled = false` em `supabase/config.toml` | Documentado só para **preview branches**; efeito em produção não documentado. Criar `config.toml` também faria a integração passar a ler o arquivo (funções/buckets declarados seriam publicados) | **Não usar como controle principal**. No máximo, defesa adicional depois de testada |
| Desconectar a integração GitHub | Elimina o mecanismo por completo (perde o check "Supabase Preview") | Alternativa se o toggle não bastar |
| Trocar a branch de produção para uma branch que não recebe push | Contorno indireto, fácil de esquecer | Não recomendado |

## 3. Ação necessária (usuário, no painel do projeto Controle-Financeiro)

1. *Project Settings → Integrations → GitHub*.
2. Confirmar que o repositório conectado é `heydsonlc/Controle-Financeiro` e a branch de produção é `main`.
3. **Desligar "Deploy to production"** (ou "Automatic branching"/deploy, conforme o nome atual na interface). Não alterar Auth, Data API nem chaves.

**Até isso ser feito:** todo push que contenha arquivo novo em `supabase/migrations` **é** um deploy no banco. Nenhum push assim será feito sem autorização expressa da migration.

## 4. Como verificar depois do desligamento

Sem aplicar nada:
- `scripts/supabase_migrations.py status` antes e depois de um push com uma migration nova: ela deve continuar **pendente** no remoto.
- O check "Supabase Preview" pode continuar aparecendo nos commits. O que importa é o histórico `supabase_migrations.schema_migrations` não mudar.

Opcional, para provar já, se autorizado: um commit com uma migration inócua (ex.: `comment on schema financeiro is '...'`) e confirmação de que ela permanece pendente após o push. Depois, aplicação manual explícita ou remoção antes do próximo uso.

## 5. Procedimento seguro para migrations futuras

`scripts/supabase_migrations.py`:
- projeto lido do `.env.staging`; recusa o da Calculadora;
- nunca imprime a connection string;
- usa uma cópia temporária com `config.toml` mínimo, **sem** criar `supabase/config.toml` no repositório.

| Passo | Comando / ação |
|---|---|
| 1. Criar a migration e os testes locais (cluster descartável) | `pytest tests/test_supabase_*.py` |
| 2. Revisão e commit | — |
| 3. Ver o estado | `python scripts/supabase_migrations.py status` (locais × aplicadas; acusa divergência) |
| 4. Simular | `python scripts/supabase_migrations.py simular` (`db push --dry-run`) |
| 5. **Autorização expressa** da(s) versão(ões) | usuário |
| 6. Aplicar só o autorizado | `python scripts/supabase_migrations.py aplicar --versoes <v1,v2>`: recusa se as pendentes forem diferentes das autorizadas, ou se o histórico remoto divergir |
| 7. Verificar | `status`; testes reais pertinentes; `verificar_exposicao_supabase.py --com-escrita`; Flask `/health` |

Validado agora, sem efeito no banco: `status` (2 locais, 2 aplicadas, nenhuma pendente); `simular` ("Remote database is up to date"); `aplicar` com versão não pendente **recusado** ("nada aplicado").

## 6. Não alterado

Migrations existentes e o histórico do banco; a integração GitHub (aguarda o usuário); Supabase Auth; Data API (`graphql_public` + `financeiro`); frontend.
