# STAGING-RENDER-2 — Preparação final do staging (relatório)

Data: 2026-10-19. Base: commit `7e799dd`. Este documento **registra o resultado** da preparação. O procedimento de publicação continua único, em `docs/STAGING_RENDER_1.md`.

Nesta etapa **não** foram feitos: criação de serviço no Render, publicação, alteração de DNS/Cloudflare, alteração no Supabase (plano, compute, Spend cap, cobrança), migrations remotas ou migração de dados reais.

## A. Banco: Session pooler

| Item | Resultado |
|---|---|
| Configuração local de staging | `.env.staging` (fora do Git, confirmado com `git check-ignore`) atualizado **apenas** na `DATABASE_URL` |
| Formato | `postgresql://postgres.<ref>:<senha>@aws-0-us-east-2.pooler.supabase.com:5432/postgres?sslmode=require`. A senha foi preservada com o mesmo URL-encoding; nenhuma credencial foi impressa |
| `.env.local` (desenvolvimento) | Inalterado (hash conferido antes e depois) |
| Conexão pela própria aplicação (`create_app()` em staging, transação somente leitura) | Host do pooler, **TLS 1.3**, PostgreSQL 17.6, `alembic_version = 5c91e95eb05d`, `/health` 200 com `database_connected: true` |
| Pool | 3 + 2 conexões por worker; SSL vindo da URL |
| `check_deploy_env.py` com `.env.staging` | Exit 0. Único aviso: `DATA_DIR` ausente localmente (no Render ele vem do `render.yaml`) |
| `check_deploy_env.py` local (como no contrato) | Exit 0, ambiente `local` |
| Migrations | Nenhuma executada |

## B. Supabase

Dados confirmados pelo usuário no painel:

- Organização com assinatura **Pro** (US$ 25,00/mês). O projeto `fzjmge…` (Controle-Financeiro) pertence a ela, junto com `Calculadora_judicial` e `db_teste_dare`.
- **Backups diários** confirmados de 13 a 19/10/2026.
- **Spend cap ativado.**
- Fatura projetada da organização: **US$ 44,96** (ciclo 07/10–07/11/2026: 3 projetos, compute e créditos).

Consequências:
- Não é preciso contratar outro plano para o staging.
- Os backups cobrem o PostgreSQL, **não** os objetos do Supabase Storage nem os arquivos do disco do Render.
- A assinatura Pro não elimina custos por projeto.
- O Spend cap pode limitar funcionalidades quando as franquias se esgotam.

## C. Render

**Configuração proposta.** Auditada no `render.yaml`; a confirmação final é no painel.

| Item | Valor | Evidência local |
|---|---|---|
| Runtime | Python **3.11.9**, fixado por `PYTHON_VERSION` | O Render não lê `runtime.txt`; sem a variável usaria 3.14.8 |
| Dependências | Todas com build binário para Linux/CPython 3.11 | `pip install --dry-run --platform manylinux… --python-version 3.11` resolveu sem erro, inclusive `psycopg2-binary 2.9.9`. Todos os imports de terceiros do backend estão no `requirements.txt` |
| Start | `gunicorn backend.app:app --workers 2 --timeout 120 --access-logfile -` | gunicorn 21.2 faz bind em `0.0.0.0:$PORT` quando `PORT` existe (`gunicorn/config.py`) |
| Plano / região | Starter / Ohio | Mesma região AWS do banco (`us-east-2`) |
| Instâncias | 1 | Padrão do Blueprint; um serviço com disco não escala |
| Disco | 1 GB em `/var/data`; `DATA_DIR=/var/data` | — |
| Banco | Session pooler, via `DATABASE_URL` com `sync: false` | — |
| Healthcheck | `/health` | — |
| Autenticação | Flask-Login | — |
| Ambiente | `APP_ENV=staging`, `FLASK_DEBUG=0`, `DEBUG=False` (`HospedadoConfig`) | — |

**Custo:**

| Item | Valor |
|---|---|
| Incremento estimado do Render | **US$ 7,25/mês** (Starter US$ 7,00 + disco de 1 GB US$ 0,25) |
| Combinado com o Supabase | **≈ US$ 52,21/mês** |

Esses valores precisam ser conferidos na tela do Blueprint; se divergirem, parar antes de contratar. A franquia de banda do workspace Hobby não foi confirmada (excedente a US$ 0,15/GB).

Observação: as dependências transitivas não são fixadas. O Render instalará versões atuais (ex.: pillow, pypdfium2, cryptography), que podem diferir do venv local. Isso foi registrado como débito técnico.

**Pendência de contratação:** autorização expressa para criar o Web Service pago.

## D. Segurança

**Controles revalidados** (testes automatizados e verificação direta):

| Controle | Situação |
|---|---|
| `SECRET_KEY` de staging | Forte (≥ 32 caracteres, passa na validação de produção) e **diferente** da de desenvolvimento (comparação por hash). No Render será gerada **uma nova** |
| Cookie | `__Host-financeiro_session`, Secure, HttpOnly, SameSite=Lax |
| Sessão | Expira após 12h sem uso |
| Escritas vindas de outra origem | 403 (inclusive `portal.kortexbrasil.com` e `Origin: null`) |
| Uploads | Limite de 64 MB por requisição |
| Cabeçalhos | HSTS sem `includeSubDomains`, `nosniff`, `X-Frame-Options`, `Referrer-Policy` |
| Backup/restauração local | Bloqueados no servidor (403) |
| Credenciais no repositório público | Nenhuma no HEAD nem no histórico (320 commits). Os 4 `SECRET_KEY=` históricos são placeholders: 2 em `.env.example` e 2 frases de exemplo em READMEs antigos, com 30 caracteres, que não coincidem com nenhuma chave atual. Nenhum arquivo `.env` real foi versionado |

**Lacuna: não há limite de tentativas de login.** `login_submit` não tem contador, atraso nem bloqueio. **Bloqueador de produção (SEG-2).** Para o staging, com dados fictícios e senha forte, o risco é aceitável.

Proposta simples para o SEG-2, que **não altera a autenticação** nesta etapa:
1. **Contador no banco** (nova tabela via Alembic): chave e-mail normalizado + IP, janela de 15 min, 5 falhas → HTTP 429 por 15 min. Funciona entre os 2 workers e sobrevive a reinícios; contador em memória não serviria. O IP deve vir de `X-Forwarded-For` com `ProxyFix(x_for=1)` no Render, ou de `CF-Connecting-IP` quando passar pelo Cloudflare.
2. **Regra de rate limiting do Cloudflare** em `POST /login`, ao ativar o domínio (CLOUDFLARE-1). Ela **não protege** o endereço `*.onrender.com`, por isso o item 1 é necessário.

## E. Armazenamento

Auditoria das gravações em disco (`write_bytes`, `open(..., 'w')`, `mkdir`, `.save`, `tempfile`) e das colunas de modelo que referenciam arquivos:

| Dado | Destino | Tipo |
|---|---|---|
| Logos de categorias | `DATA_DIR/uploads/logos/categorias` (nomes `uuid4`) | Persistente (disco) |
| Documentos de financiamento | `DATA_DIR/uploads/financiamentos` (`FinanciamentoDocumento.caminho_relativo`) | Persistente (disco) |
| Comprovantes de IR e documentos fiscais | Banco (`IrComprovanteArquivo.conteudo`, BYTEA) | Persistente (banco + backup Supabase) |
| Cenário ativo de mobilidade | `DATA_DIR/mobilidade_cenario_ativo.json` | Persistente (disco) |
| Configuração e histórico de OCR | `DATA_DIR/ocr` | Persistente (disco) |
| Configuração e histórico de backup | `DATA_DIR/backups` | Persistente (disco) |
| Imagens de bens patrimoniais | `frontend/static/img/patrimonio*` (5 arquivos **versionados**; o banco guarda só o nome) | Vêm do Git a cada deploy |
| Logo de perfil financeiro | `logo_url` (texto/URL no banco) | Persistente (banco) |
| Exportações Excel e ZIP | Memória (`BytesIO`) | Não grava em disco |
| Processamento de OCR | `tempfile` em `/tmp` | **Temporário** (pode se perder) |

`CategoriaCartao.logo_arquivo` não tem rota de upload; é uma coluna legada.

**Arquivos pessoais:** os 27 arquivos não versionados em `frontend/static/img` (PDFs que parecem documentos pessoais e logos avulsos) não são referenciados pelo código. Eles **não vão para o deploy**, porque o Render publica a partir do Git, e não devem ser commitados.

**O snapshot diário do Render não substitui um plano de backup independente dos documentos.** Ele fica no mesmo provedor, restaura só o disco inteiro e se perde se o serviço for apagado. Antes de produção: **BACKUP-DOCS-1**.

**Limitações do disco:**
- 1 instância;
- sem zero-downtime deploy;
- só aumenta de tamanho;
- inacessível no build e no pre-deploy;
- snapshot diário retido por ao menos 7 dias, com restauração apenas total.

## F. Testes

| Comando | Resultado |
|---|---|
| `check_deploy_env.py` (local) | Exit 0 |
| `check_deploy_env.py` (`.env.staging`) | Exit 0 |
| Suíte focada: deploy, autenticação, CVV, backup, documentos (financiamento, IR, empresa, fiscais), logos e conexão/health (14 arquivos) | **202 passed** |
| Suíte completa (`tests/`, sem E2E) | 1026 testes coletados: **5 falhas**, nenhum erro. São as mesmas 5 do baseline |
| `git diff --check` | Sem problemas |
| `git status --short` | Só os documentos desta etapa alterados (mais os arquivos não versionados que já existiam) |

**Evidência de que as 5 falhas já existiam.** Foram reexecutadas numa cópia isolada do commit `0e04407`, anterior a todo o trabalho de deploy, e falham da mesma forma:

| Teste | Erro |
|---|---|
| `test_categorias_sistemicas_mobilidade::test_projecoes_veiculo_usam_categorias_sistemicas_granulares` | `KeyError: 'IPVA'` |
| `test_ocr_tools::test_status_sem_ferramentas_retorna_estrutura_valida` | `assert True is False` (a máquina tem Tesseract/Poppler instalados) |
| `test_ocr_tools::test_poppler_ausente_retorna_aviso` | `assert True is False` (mesma causa) |
| `test_receitas_ux::test_cards_resumo_calculam_previsto_realizado_diferenca_confiabilidade` | `1500.0 == 3000.0` |
| `test_veiculos_mobilidade_2b::test_suprimir_despesas_previstas_futuras` | `1 == 2` |

## G. Arquivos alterados

| Arquivo | Mudança |
|---|---|
| `docs/STAGING_RENDER_1.md` | Supabase Pro, custos combinados, Spend cap, backups confirmados, limites dos backups, Etapa 0 marcada como concluída, próximas etapas (SEG-2, BACKUP-DOCS-1) |
| `docs/STAGING_RENDER_2.md` | Este relatório |
| `docs/DEPLOY.md` | Ponteiros para os documentos e pendências atualizadas |
| `docs/ROADMAP.md` | Ordem de trabalho; itens DEPLOY-READY-FIN-1, SEG-2, STORAGE-1, STAGING-RENDER-1/2/3, BACKUP-DOCS-1, DATA-MIGRATE-1, STORAGE-2; débitos (dependências transitivas, 5 testes) |
| `.env.staging` | Só local, **fora do Git**: `DATABASE_URL` → Session pooler |

Nenhum código ou configuração versionada foi alterado nesta etapa: `render.yaml`, `requirements.txt`, `backend/` e `scripts/` foram auditados e mantidos.

## H. Próxima autorização necessária

**STAGING-RENDER-3:** autorização comercial e operacional para:
1. criar o Web Service pago no Render (Starter, Ohio, disco de 1 GB), **depois de conferir na tela o valor de ≈ US$ 7,25/mês**;
2. preencher `SECRET_KEY` (nova), `DATABASE_URL` (pooler) e `CARTOES_CVV_MASTER_PASSWORD` pelo painel;
3. executar as Etapas 1–6 de `docs/STAGING_RENDER_1.md` com dados fictícios.

O domínio `financeiro.kortexbrasil.com` (CLOUDFLARE-1) só entra depois do staging validado.
