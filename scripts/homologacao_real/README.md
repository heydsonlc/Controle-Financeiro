# Homologação real no Supabase de teste

Roteiros usados para aplicar e validar as migrations `20261106`–`20261126` no Supabase **de teste** (`fzjmge…`). Eles gravam só dados fictícios num **perfil temporário** criado pelo próprio aplicativo e depois o removem, conferindo a identidade de cada registro.

Nunca gravam nos perfis 1 (Pessoal), 2 (Empresa), 31 e 39. Não imprimem e-mails, senhas, chaves nem a URL do banco.

| Arquivo | Uso |
|---|---|
| `lote_real.py` | Base comum: sessão, chamadas à Data API, criação do perfil temporário, troca do escritor (`atribuir`), build com varredura de segredos, telas com Playwright. Também valida o lote `20261106`–`20261118` |
| `motor_real.py` | FIN-FINANCIAMENTOS-MOTOR-1 (`20261123090000`) |
| `escritor_real.py` | FIN-ESCRITOR-UNICO-FINAL-1 (`20261124090000`) |
| `cr_real.py` | FIN-CATEGORIAS-RECORRENCIAS-2 (`20261125090000`) |
| `pat_real.py` | FIN-PATRIMONIO-2 (`20261126090000`) |
| `digital_lote.py` | Retrato só de leitura do banco de teste (md5 de cada tabela e função, migrations aplicadas) |

As quatro migrations já estão aplicadas no Supabase de teste. Os roteiros ficam como referência e modelo para os próximos MVPs: copiar o do MVP mais parecido e trocar `VERSAO`, os nomes e as verificações.

## Pré-requisitos

- Arquivos locais na raiz do projeto (fora do Git): `.env.staging` (`DATABASE_URL` do Supabase de teste) e `.env.e2e-real` (contas de teste A e B). Os roteiros carregam os dois sozinhos.
- Supabase CLI autenticada (a chave **pública** é lida por ela).
- Para `ui`: `npm ci` em `web/` e o Chromium do Playwright.

## Etapas (cada uma auditável)

```powershell
venv\Scripts\python.exe scripts\homologacao_real\digital_lote.py data\homologacao_real\antes.json
venv\Scripts\python.exe scripts\homologacao_real\pat_real.py inspecionar   # só leitura; não aplicar se houver FALHA
venv\Scripts\python.exe scripts\homologacao_real\pat_real.py aplicar       # SÓ com autorização: aplica uma única versão
venv\Scripts\python.exe scripts\homologacao_real\pat_real.py criar         # perfil temporário pelo aplicativo
venv\Scripts\python.exe scripts\homologacao_real\pat_real.py api
venv\Scripts\python.exe scripts\homologacao_real\pat_real.py ui web        # dist construído da pasta web indicada
venv\Scripts\python.exe scripts\homologacao_real\pat_real.py limpar        # simulação
venv\Scripts\python.exe scripts\homologacao_real\pat_real.py limpar --confirmar
```

- `aplicar` tira temporariamente da pasta `supabase/migrations` as migrations locais posteriores à versão, chama `scripts/supabase_migrations.py aplicar --versoes <versão>` e as devolve, conferindo o md5. Rodar com o VS Code sem arquivos dessa pasta abertos.
- O estado (perfil temporário) e os retratos ficam em `data/homologacao_real/`, ignorada pelo Git.
- `inspecionar` dos MVPs já aplicados acusa FALHA ("objetos novos ausentes", "última aplicada") por definição: ela foi feita para rodar **antes** da aplicação.
- `limpar` para sem gravar nada se o perfil não for o temporário criado pelo aplicativo, se tiver vínculos ou registros fora do teste, ou se sobrar qualquer linha.
