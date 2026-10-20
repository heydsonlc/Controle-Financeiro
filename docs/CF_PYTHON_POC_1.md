# CF-PYTHON-POC-1 — Flask do Controle Financeiro em Cloudflare Python Workers

Data: 2026-10-19. Diagnóstico e prova de conceito **isolada**. Nada foi publicado, migrado ou configurado: nenhum Worker publicado, nenhum DNS, nenhuma alteração no Supabase, no código da aplicação ou em regras financeiras. A contratação do Render (STAGING-RENDER-3) segue suspensa e preparada.

Fontes da POC: `docs/poc/cf-python-poc-1/`. A execução foi apenas local, com `pywrangler dev` (workerd), sem credenciais e sem banco real.

## 1. Conclusão

**Tecnicamente possível, mas não recomendado agora.** O código real da aplicação rodou no runtime de Python Workers depois de **três ajustes obrigatórios**. Mesmo assim, a migração exige refatorações estruturais (armazenamento, configuração, senhas, driver, versão do Python), perde funcionalidades (OCR) e opera **a 114 MB de um limite rígido de 128 MB**. Partes críticas não podem ser provadas sem publicar: conexão real via Hyperdrive, snapshot de deploy e limite de memória efetivo. O Render continua sendo a opção de menor risco e menor esforço. **Recomendação: manter o Render e retomar o STAGING-RENDER-3.**

## 2. Estado oficial do suporte (documentação Cloudflare)

| Fato | Fonte |
|---|---|
| Python Workers estão em **GA**; suporte a WSGI/ASGI desde 2026-09-02 | Blog "Python Workers are now generally available"; changelog de 2026-09-02 |
| Flask roda pelo conector WSGI embutido: `from workers import wsgi` / `Default = wsgi.entrypoint(app)` | Docs → Python → Packages → Flask |
| Pacotes suportados: Python puro e wheels **PyEmscripten** no PyPI, mais os pacotes do Pyodide. Extensões C/Rust só se compiladas para WebAssembly | Docs → Packages; blog GA |
| Postgres via **Hyperdrive**; drivers testados: `asyncpg` (recomendado), `pg8000`, `psycopg`. Exige `compatibility_date` ≥ 2026-09-08 | Docs → Hyperdrive → Python Workers |
| "**Apenas ORMs SQLAlchemy síncronos** são suportados" (sem greenlet) | idem |
| Conexões abertas e fechadas por requisição nos exemplos; sem pooling documentado | idem |
| Filesystem **efêmero, em memória**, não compartilhado entre isolates; usar KV, R2 ou Durable Objects para persistir | Docs → Python → Standard library |
| `threading`/`multiprocessing` importáveis, mas **não funcionais** | idem |
| Limites (Free e Paid): **128 MB** de memória por isolate; startup do escopo global de **1 s**; bundle de 64 MiB descompactado; 6 conexões simultâneas por requisição | Docs → Workers → Limits |
| CPU por requisição: **Free 10 ms**; Paid 30 s por padrão (até 5 min) | idem |
| Preço: Workers Paid a partir de **US$ 5/mês** (10 M requisições e 30 M ms de CPU incluídos). Hyperdrive incluído no Free e no Paid. R2 com 10 GB/mês gratuitos | Docs → Workers → Pricing |

## 3. Evidências da prova de conceito

O runtime local reportou `python 3.14.2`, plataforma `emscripten` (índice Pyodide `314.0.7`). **A aplicação hoje roda e é testada em Python 3.11.9.**

### 3.1 Instalação das dependências reais (`requirements.txt`, sem alteração)

| Pacote | Resultado |
|---|---|
| `psycopg2-binary==2.9.9` | ❌ **"has no usable wheels"**: não existe build WebAssembly, e a resolução falha |
| Demais 12 dependências | ✅ resolvidas depois de trocar o driver (bundle de 42,4 MB, 2.525 módulos) |

### 3.2 Importação no runtime

| Pacote | Resultado |
|---|---|
| Flask 3.0.0, Flask-Login, Flask-CORS, Flask-WTF, python-dotenv, dateutil, APScheduler (import), openpyxl, pdfminer, pdfplumber, Pillow 12.2, pypdfium2, cryptography 47, sqlite3, pg8000 1.31.5 | ✅ |
| **SQLAlchemy 2.0.23** (versão do projeto), Flask-SQLAlchemy, Flask-Migrate | ❌ `AssertionError: ... SQLCoreOperations directly inherits TypingOnly` (incompatível com Python 3.14) |
| SQLAlchemy **2.0.55** | ✅ (Flask-SQLAlchemy levou 1,1 s só para importar) |
| psycopg 3 | ❌ `ImportError: no pq wrapper available` (não há libpq no WebAssembly) |
| asyncpg | Não testado no ORM: é só assíncrono, e a doc limita o SQLAlchemy ao modo síncrono |

**Driver viável para a aplicação síncrona: apenas `pg8000`.** O `create_engine("postgresql+pg8000://…")` funcionou, e a tentativa de socket contra uma porta local fechada falhou de forma controlada (`InterfaceError`). **A conexão real ao Supabase via Hyperdrive não foi testada**, porque exige recurso na conta e conexão com banco, fora do escopo.

### 3.3 Funcionalidades auxiliares

| Teste | Resultado |
|---|---|
| `pdfplumber` extraindo texto de PDF sintético | ✅ |
| `pypdfium2` render e `pdfplumber.to_image` | ✅ |
| `openpyxl` gerando XLSX em memória | ✅ |
| Escrita em `/tmp` | ✅, mas só dentro do isolate (o contador passou de 1 para 2 na mesma instância). Não persiste nem é compartilhado (documentação) |
| `subprocess` (OCR com Tesseract/Poppler, `pg_dump`) | ❌ `OSError: emscripten does not support processes` |
| `threading` (APScheduler) | ❌ `RuntimeError: can't start new thread` |
| **`hashlib.scrypt` e `hashlib.pbkdf2_hmac`** | ❌ **ausentes**. O Werkzeug usa scrypt por padrão, e **o usuário do staging tem hash `scrypt:32768:8:1`** (lido só o prefixo, somente leitura) |
| Shim de `hashlib.scrypt` via `cryptography` | ✅ verificou corretamente um hash gerado no CPython (senha certa `true`, errada `false`), com **261 ms** de CPU |

### 3.4 Código real do Controle Financeiro (commit HEAD, sem alterações, config `testing` com SQLite em memória)

Executado com o shim de scrypt e SQLAlchemy 2.0.55:

| Rota | Resultado |
|---|---|
| Importação + `create_app()` | ✅ 51 tabelas, **3.485 ms** |
| `GET /` sem sessão | ✅ 302 → `/login?next=/` |
| `GET /login` (Jinja) | ✅ 200 |
| `POST /login` | ✅ 302 → `/` (Flask-Login + cookie de sessão assinado) |
| `GET /` autenticado (dashboard) | ✅ 200, 23 KB |
| `GET /api/dashboard/resumo`, `/api/despesas/`, `/api/ir/comprovantes`, `/api/ocr/status`, `/health` | ✅ 200, entre 2 e 76 ms |
| `GET /api/backup/status` | ❌ `PermissionError: '/session/metadata/data'`: o diretório do bundle é somente leitura; `DATA_DIR` teria de ir para `/tmp`, que é efêmero |
| Algumas rotas retornaram 404 | Caminho testado com barra final, que não existe; **não é incompatibilidade** |

**Memória do WebAssembly:** 78,5 MB só com as dependências; **114 MB com a aplicação carregada**, de um limite de **128 MB** por isolate (que inclui também o heap JS). O scrypt com `n=32768, r=8` aloca cerca de 32 MB por verificação de senha; com um PDF grande, o risco de estouro é real. O limite local não é aplicado como em produção, então isso só se confirma publicando.

## 4. O que seria preciso mudar para rodar no Cloudflare

| # | Mudança | Natureza | Esforço / risco |
|---|---|---|---|
| 1 | `psycopg2` → `pg8000` + Hyperdrive apontando para o Supabase | Infra + driver | Médio. Diferenças de tipos e parâmetros só aparecem com o banco real |
| 2 | SQLAlchemy 2.0.23 → 2.0.5x **e** Python 3.11 → **3.14** | Plataforma | Alto. Revalidar os 1.026 testes em 3.14 e as regras financeiras |
| 3 | Hash de senha: shim scrypt via `cryptography` (ou rehash/reset) | Segurança | Médio. Código sensível; 261 ms e ~32 MB por login |
| 4 | Configuração: segredos chegam por `env` do Worker (`request.environ["workers.env"]`), e `app = create_app()` no import não teria `SECRET_KEY`/`DATABASE_URL`. Criação tardia do app | Arquitetura | Médio. Não se sabe se `os.environ` recebe os segredos; não verificado |
| 5 | Todo `DATA_DIR` (logos, documentos de financiamento, cenário de mobilidade, configs de OCR e backup) → **R2** ou banco | Armazenamento | Alto. Reescrever a camada de arquivos; é o equivalente do STORAGE-2 |
| 6 | Arquivos estáticos (11 MB) via Workers Assets com `run_worker_first` | Infra | Baixo/médio |
| 7 | Pool do SQLAlchemy → `NullPool` (conexão por requisição) | Driver | Baixo, mas comportamento sob carga não verificado |
| 8 | Perdas definitivas: OCR (Tesseract/Poppler), backup via `pg_dump`, agendador por thread | Funcionalidade | OCR teria de virar serviço externo |
| 9 | Memória a 114/128 MB: imports tardios, separar o processamento de PDF | Desempenho | Alto e incerto |
| 10 | Plano **Workers Paid** obrigatório (10 ms de CPU no Free inviabilizam login e importação) | Custo | US$ 5/mês |

**Estimativa:** é uma migração de plataforma, não um ajuste de deploy. Envolve as mudanças 1–7 e 9, uma regressão completa em Python 3.14 e a migração de arquivos para R2, com várias incertezas que só se resolvem publicando.

## 5. Comparação objetiva

| Critério | Render (STAGING-RENDER-2, pronto) | Cloudflare Python Workers |
|---|---|---|
| Mudanças no código | Nenhuma | Pelo menos 7 mudanças estruturais (§4) |
| Python | 3.11.9 (o mesmo dos testes) | 3.14.2, fixado pelo runtime |
| Driver | `psycopg2` atual | `pg8000` via Hyperdrive (não testado com banco real) |
| Senhas existentes | Funcionam | Exigem shim ou reset |
| Documentos e uploads | Disco persistente em `/var/data` | Exige R2 (refatoração) |
| OCR | Indisponível no host atual (igual) | Impossível (sem `subprocess`) |
| Memória | 512 MB (uso medido ≈ 220 MB) | 128 MB fixos (uso medido 114 MB) |
| Startup | Normal | 3,5 s de import (limite de 1 s do escopo global; depende do snapshot de deploy, não verificado) |
| Custo | ≈ US$ 7,25/mês | ≈ US$ 5/mês (Workers Paid), mais R2 se passar da franquia |
| Comprovado localmente | Smoke test, gate, conexão pooler | Rotas principais; **não** banco real, deploy nem limites reais |
| Operação | Um serviço, logs e shell | Worker + Hyperdrive + R2 + Assets |

A economia de cerca de US$ 2,25/mês não compensa o esforço nem os riscos.

## 6. Riscos registrados

- **Não concluir compatibilidade total a partir da POC:** banco real, snapshot de deploy, limites efetivos de CPU e memória e latência de cold start não foram testados.
- **Python 3.14 em produção** com a aplicação validada em 3.11.
- **Margem de memória mínima** (14 MB), com falha abrupta do isolate ao estourar.
- **Senhas:** sem o shim, nenhum login existente funcionaria.
- **Dependência de recursos recentes** (GA em 2026-09; o `workerd` local só aceitava compatibilidade até 2026-09-10).

## 7. Recomendação

1. **Manter a arquitetura aprovada** (Render + Supabase + Cloudflare DNS) e retomar o **STAGING-RENDER-3** quando autorizado.
2. Usar o Cloudflare onde ele já é forte e não exige migração: DNS, proxy, regra de rate limit em `/login` e, opcionalmente, Access (CLOUDFLARE-1).
3. Reavaliar Workers só se surgir um motivo além de custo. Nesse caso, primeiro o STORAGE-2 (arquivos fora do disco), que vale para qualquer plataforma, e uma POC com Hyperdrive real em conta de teste, que exigiria autorização específica.

Nenhuma migração foi iniciada.
