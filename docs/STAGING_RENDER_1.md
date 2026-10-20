# STAGING-RENDER-1 — Contrato de publicação do staging no Render

Preparado em 2026-10-19, a partir do DEPLOY-READY-FIN-1 (commit `409a650`, publicado em `origin/main`). Atualizado no STAGING-RENDER-2 com o plano Supabase confirmado e a Etapa 0 concluída (relatório em `docs/STAGING_RENDER_2.md`). **Este documento não executa nada.** Cada etapa marcada com 🔒 exige autorização específica do usuário no momento da execução.

## 1. Decisões já tomadas

| # | Decisão |
|---|---|
| D1 | Conexão do backend pelo **Session pooler IPv4** do Supabase (`aws-0-us-east-2.pooler.supabase.com:5432`, usuário `postgres.<ref>`, `sslmode=require`). Validado com TLS 1.3 |
| D2 | **Render Starter** com disco persistente em `/var/data` (`DATA_DIR`), mantendo o armazenamento local já existente no código |
| D3 | Supabase Storage fica como melhoria futura (STORAGE-2), sem refatoração agora |
| D4 | Publicação inicial **só no endereço provisório** `https://<servico>.onrender.com` |
| D5 | `financeiro.kortexbrasil.com` só depois do staging validado (etapa CLOUDFLARE-1) |

## 2. Fora de escopo nesta etapa

- Alterar DNS ou Cloudflare.
- Executar `flask db upgrade` (o banco já está no head, `5c91e95eb05d`; só é permitido `db current`, que é leitura).
- Importar dados financeiros reais ou documentos reais. O staging contém só o schema e o usuário administrador.
- Refatorar o armazenamento.

## 3. Custos (confirmar na tela do Blueprint antes de aplicar)

| Item | Valor de referência | Fonte |
|---|---|---|
| Workspace Hobby | US$ 0/mês (paga-se só o uso; 1 membro, até 25 serviços) | docs do Render ("New Workspace Plans") |
| Web service Starter | **US$ 7/mês**: 512 MB de RAM, 0,5 CPU | fontes de terceiros de 2026 (a página oficial de preços não pôde ser lida automaticamente) |
| Disco persistente de 1 GB | **US$ 0,25/GB/mês**, ou seja US$ 0,25/mês | fontes de terceiros de 2026 |
| Banda de saída | Franquia do plano Hobby **não confirmada**; excedente a US$ 0,15/GB | docs do Render (excedente) |
| **Incremento do Render** | **≈ US$ 7,25/mês**, cobrado proporcionalmente ao tempo de uso | — |
| Supabase Pro (assinatura da organização) | US$ 25,00/mês | confirmado pelo usuário no painel |
| Fatura projetada da organização Supabase | **US$ 44,96** (ciclo 07/10–07/11/2026: 3 projetos, compute e créditos) | confirmado pelo usuário no painel |
| **Total combinado projetado** | **≈ US$ 52,21/mês**, antes de variações de consumo | — |

Sobre o Supabase:
- O Controle Financeiro (`fzjmge…`) pertence à organização com assinatura **Pro**; não é preciso contratar outro plano para o staging.
- A assinatura Pro **não elimina custos por projeto** (compute) nem garante ausência de cobranças adicionais.
- O **Spend cap está ativado**: evita cobrança acima das franquias, mas pode **limitar funcionalidades** quando elas se esgotam.
- Nesta etapa não se altera plano, compute, Spend cap ou qualquer configuração de cobrança.

Bloqueio de etapa: se a tela do Blueprint mostrar valor diferente de ≈ US$ 7,25/mês, **parar** e reportar antes de aplicar.

## 4. Limites de recursos

| Recurso | Limite | Impacto |
|---|---|---|
| RAM (Starter) | 512 MB | Medido localmente: cerca de 95 MB por processo da aplicação. Com 2 workers mais o processo mestre, ≈ 220 MB ociosos. Picos ao processar PDFs grandes (limite de 10 MB por documento). Se o uso normal passar de 400 MB, trocar para `--workers 1 --threads 4` |
| CPU | 0,5 | Suficiente para um usuário. Importações de PDF ficam mais lentas que no local |
| Instâncias | **1** (serviço com disco não escala) | Sem redundância. Aceitável para staging de um único usuário |
| Deploys | **Sem zero-downtime**: a instância antiga para antes da nova subir | Alguns segundos fora do ar a cada deploy |
| Disco | Pode aumentar, **não pode diminuir** | Começar com 1 GB (os uploads locais hoje somam cerca de 56 KB) |
| Disco × build | Build e pre-deploy **não acessam** o disco | Nada no build depende de `/var/data` (verificado) |
| Conexões com o banco | Pool de 3+2 por worker, ou seja até 10 | Dentro do limite do Session pooler |
| Corpo da requisição | 64 MB (`MAX_CONTENT_LENGTH`) | — |
| Python | 3.11.9 via `PYTHON_VERSION` | **Obrigatório.** Sem essa variável o Render usaria 3.14.8, e `psycopg2-binary==2.9.9` não tem build para essa versão. O Render não lê `runtime.txt` |

## 5. Persistência: tudo o que a aplicação grava

Auditoria de todas as gravações em disco no código (`write_bytes`, `open(..., 'w')`, `mkdir`, `.save`, `tempfile`):

| O que | Onde | Persiste? |
|---|---|---|
| Logos de categorias | `DATA_DIR/uploads/logos/categorias` | ✅ disco |
| Documentos de financiamento | `DATA_DIR/uploads/financiamentos/<id>/documentos` | ✅ disco |
| Configuração e histórico de OCR | `DATA_DIR/ocr` | ✅ disco (OCR indisponível no host, só configuração) |
| Configuração e histórico de backup | `DATA_DIR/backups` | ✅ disco (backup local bloqueado no host) |
| Cenário ativo de mobilidade | `DATA_DIR/mobilidade_cenario_ativo.json` | ✅ disco |
| Comprovantes de IR | Banco (`ir_comprovante_arquivo`, BYTEA) | ✅ banco |
| Relatórios Excel e ZIP | Memória (`BytesIO`), enviados na resposta | n/a |
| Arquivos temporários do OCR | `tempfile` do sistema (`/tmp`) | ❌ efêmero, por design |
| Imagens de `frontend/static/img` | Repositório (somente leitura) | ✅ vêm do git a cada deploy |

Fora de `/var/data`, tudo se perde a cada deploy ou reinício. Isso é esperado e nenhum dado de usuário fica nessa área.

**Atenção:** há 27 arquivos **não versionados** em `frontend/static/img` (logos de bancos e alguns PDFs que parecem documentos pessoais). Nenhum é referenciado no código, então o staging não depende deles. Os PDFs pessoais **nunca** devem ser commitados, porque o repositório é público. Na migração de dados reais (DATA-MIGRATE-1), verificar se o banco local guarda nomes desses arquivos.

## 6. Backup

| Camada | Staging | Antes de produção |
|---|---|---|
| Disco `/var/data` | Snapshot automático do Render a cada 24h, retido por **pelo menos 7 dias**. A restauração é do disco inteiro (sem restauração parcial) e descarta o que foi gravado depois do snapshot | Igual. Validar uma restauração de teste |
| Banco Supabase | **Plano Pro: backups diários automáticos**, confirmados de 13 a 19/10/2026 | Definir e testar o procedimento de restauração. Opcional: `pg_dump` periódico independente via Session pooler (cliente `pg_dump` 17 ou superior, igual ou acima do servidor 17.6) |
| Backup pela tela do sistema | **Bloqueado no host** (403), por segurança | Continua bloqueado. Backup é responsabilidade da infraestrutura |

Limites importantes:
- Os backups do Supabase cobrem **apenas o PostgreSQL**. Não incluem objetos do Supabase Storage, que hoje não é usado, nem os arquivos do disco do Render.
- O **snapshot diário do Render não substitui um backup independente dos documentos**: ele fica no mesmo provedor, só restaura o disco inteiro e é perdido se o serviço for apagado. Antes de produção: BACKUP-DOCS-1.

## 7. Procedimento

### Etapa 0: pré-checagem local (sem custo, sem publicação) — ✅ concluída no STAGING-RENDER-2

Resultado: `.env.staging` aponta para o Session pooler com `sslmode=require`, e a senha foi preservada. A aplicação, em modo staging, conecta com TLS 1.3; `alembic_version = 5c91e95eb05d`; `/health` 200; `check_deploy_env.py` com exit 0. Os passos abaixo ficam como referência para repetição.

1. No Supabase (projeto de staging): *Connect* → **Session pooler**. Copiar a URI (host `aws-?-us-east-2.pooler.supabase.com`, porta `5432`, usuário `postgres.<ref>`). Senha com URL-encoding.
2. Atualizar **apenas** a `DATABASE_URL` em `.env.staging` (arquivo ignorado pelo git).
3. Rodar o gate de ambiente sem imprimir valores:
   ```bash
   venv\Scripts\python.exe -c "from dotenv import load_dotenv; load_dotenv('.env.staging', override=True); import runpy; runpy.run_path('scripts/check_deploy_env.py', run_name='__main__')"
   ```
   Esperado: nenhum problema; só o aviso de `DATA_DIR`, que no Render vem do `render.yaml`.
4. Teste de leitura pelo pooler: `alembic_version = 5c91e95eb05d` e `ssl = true` (mesma consulta do DEPLOY-READY-FIN-1).

### Etapa 1 🔒: criar o serviço pago

1. Render: conta e workspace **Hobby**. Conectar o GitHub dando acesso **só** ao repositório `heydsonlc/Controle-Financeiro`.
2. *New* → *Blueprint* → repositório → branch `main` → conferir na tela:
   - serviço `controle-financeiro-staging`, runtime Python, região **Ohio**, plano **Starter**;
   - disco `controle-financeiro-data`, 1 GB, montado em `/var/data`;
   - *Auto-Deploy* desligado;
   - custo ≈ US$ 7,25/mês (§3).
3. Preencher as variáveis marcadas como `sync: false`:
   - `SECRET_KEY`: **nova**, gerada com `secrets.token_urlsafe(64)`; nunca reaproveitar a local nem a do `.env.staging`.
   - `DATABASE_URL`: a do Session pooler.
   - `CARTOES_CVV_MASTER_PASSWORD`: forte (12 caracteres ou mais), ou vazia se o staging não tiver cartão com CVV (hoje não tem).
4. **Parar e pedir autorização** antes de clicar em *Apply*.

### Etapa 2: primeiro deploy e verificação do host

1. Acompanhar o log do build. Esperado: `pip install` concluído, `Booting worker` 2 vezes, health check verde.

   | Sinal de falha no log | Causa provável |
   |---|---|
   | `SECRET_KEY insegura` | Chave fraca ou ausente |
   | `DATABASE_URL de staging ausente` | Variável não preenchida |
   | `Network is unreachable` / `could not translate host` | Host direto em vez do pooler |
   | `password authentication failed` | Senha sem URL-encoding |

2. *Shell* do serviço (somente leitura):
   ```bash
   echo $APP_ENV $DATA_DIR $PYTHON_VERSION          # staging /var/data 3.11.9
   python --version                                  # 3.11.9
   df -h /var/data && ls -la /var/data               # disco montado, ~1 GB
   python -m flask --app backend/app.py db current   # 5c91e95eb05d (NÃO rodar upgrade)
   ```
3. Usuário de acesso: o staging já tem 1 usuário ativo (SUPABASE-MIGRATE-1). Se a senha não for conhecida, rodar `python scripts/criar_admin.py --email <email> --reset` no Shell. Isso grava no banco de staging; **pedir confirmação** antes.

### Etapa 3: testes automatizados contra o staging

Na máquina local, sem commitar credenciais:

```bash
set BASE_URL=https://<servico>.onrender.com
set SMOKE_ADMIN_EMAIL=<email>
set SMOKE_ADMIN_SENHA=<senha>
venv\Scripts\python.exe scripts\smoke_staging.py
```

Todos os itens precisam dar `OK`:
- `/health` com `database_connected: true`;
- página protegida → `/login`;
- API sem sessão → 401 JSON;
- HSTS sem `includeSubDomains`;
- `nosniff`;
- POST com `Origin` de `portal.kortexbrasil.com` → 403;
- login → 302;
- cookie `__Host-` com `Secure` e `HttpOnly`;
- `POST /api/backup/executar` → 403.

### Etapa 4: testes manuais de segurança

| # | Teste | Esperado |
|---|---|---|
| S1 | `http://<servico>.onrender.com/login` | Redireciona para `https://` |
| S2 | Login com senha errada 5 vezes | 401 genérico, sem revelar se o e-mail existe. **Não há rate limit**: registrar para o CLOUDFLARE-1 |
| S3 | DevTools → cookie de sessão | `__Host-financeiro_session`, Secure, HttpOnly, SameSite=Lax, expira em 12h |
| S4 | Logout, depois "voltar" no navegador e recarregar | Volta para `/login` |
| S5 | `GET /rota-inexistente` | JSON 404, sem traceback |
| S6 | Upload maior que 64 MB | 413 |
| S7 | Configurações → Backup → executar ou restaurar | Mensagem de indisponível no ambiente hospedado |
| S8 | Portal e site Kortex | Continuam respondendo normalmente (nada foi alterado neles) |

### Etapa 5: teste de persistência (só com arquivos sintéticos)

1. Enviar um **logo de teste** para uma categoria e um **PDF sintético** (ex.: "documento de teste STAGING") para um financiamento de teste.
2. Salvar um cenário ativo de mobilidade.
3. *Manual Deploy* → *Deploy latest commit*. Depois, *Restart service*.
4. Conferir que os três continuam disponíveis e baixáveis. No Shell: `find /var/data -type f`.
5. Remover os itens de teste ao final, ou mantê-los identificados como teste.

### Etapa 6: recursos e backup

1. *Metrics* do serviço: memória em uso normal abaixo de 400 MB. Durante o upload do PDF de teste, observar o pico.
2. Depois de 24h: *Disks* → confirmar que existe snapshot.
3. Registrar o custo real exibido em *Billing* após o primeiro dia.

## 8. Critérios de aceite

- [ ] Etapas 0–6 executadas; todos os itens da Etapa 3 em `OK` e S1–S8 conforme esperado
- [ ] Arquivos sintéticos sobrevivem a deploy e reinício
- [ ] `db current` = `5c91e95eb05d`, e nenhuma migration executada
- [ ] Memória de uso normal abaixo de 400 MB; custo conferido com §3
- [ ] Snapshot de disco visível
- [ ] Nenhum dado real, DNS ou Cloudflare alterado; Portal e site intactos

## 9. Reversão

| Situação | Ação |
|---|---|
| Deploy com falha | O serviço antigo não existe (primeiro deploy): corrigir variável e fazer *Manual Deploy* |
| Interromper custo de compute | *Suspend service*. **Não confirmado** se o disco continua sendo cobrado quando o serviço está suspenso; verificar em *Billing* |
| Encerrar o staging | *Delete service*: **apaga o disco** e os arquivos. Banco Supabase não é afetado |
| Credencial exposta | Trocar no painel (`SECRET_KEY` invalida todas as sessões) e redefinir a senha do banco no Supabase |

## 10. Próximas etapas (fora deste contrato)

- **CLOUDFLARE-1:** `financeiro.kortexbrasil.com` via CNAME (DNS only até o certificado; *Full (strict)* só para o hostname), mais rate limit em `/login` ou Cloudflare Access.
- **SEG-2:** limitar tentativas de login (bloqueador de produção; proposta em `docs/STAGING_RENDER_2.md`).
- **BACKUP-DOCS-1:** backup independente dos documentos do disco, e teste de restauração do backup diário do Supabase (§6).
- **DATA-MIGRATE-1:** dados reais e documentos para o banco e o disco, com autorização específica.
- **STORAGE-2:** Supabase Storage (futuro).
