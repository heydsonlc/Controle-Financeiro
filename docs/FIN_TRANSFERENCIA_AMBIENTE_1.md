# FIN-TRANSFERENCIA-AMBIENTE-1 — Transferência do desenvolvimento para o notebook

**Data:** 27/10/2026. **Máquina de origem:** computador de casa (Windows), pasta do projeto no OneDrive. **Destino:** notebook Windows.

**Situação:** transferência **preparada e documentada**; a troca efetiva e o push dependem de autorização separada.

Este documento é o manual de transferência e o relatório final do contrato. Ele foi escrito para ser lido no notebook: tudo o que é preciso para continuar está aqui ou num arquivo indicado por caminho relativo à raiz do projeto.

**Antes deste contrato** terminaram as operações em andamento:
- FIN-CATEGORIAS-RECORRENCIAS-2 e FIN-PATRIMONIO-2: commits, aplicação das migrations `20261125090000` e `20261126090000` no Supabase de teste, validação real e registro;
- registro da `20261122090000`, num commit só documental.

Nenhuma migration ficou pendente.

**Não foi feito:**
- push, publicação, alteração em produção;
- migration nova, transferência de perfis reais;
- alteração funcional dos módulos financeiros;
- exclusão de arquivo pessoal, banco ou backup.

---

## 1. Resumo do estado do projeto

| Item | Estado |
|---|---|
| Branch | `main` |
| Último commit | o deste contrato (FIN-TRANSFERENCIA-AMBIENTE-1); antes dele, `3ca1fb6` |
| GitHub (`origin/main`) | `9a50410`. Conferido com `git ls-remote` em 27/10/2026; é ancestral do `main` local, então o envio será por avanço direto (fast-forward) |
| Commits locais fora do GitHub | **47**: os 46 do §4 mais o deste contrato |
| Arquivos rastreados modificados | nenhum (depois do commit deste contrato) |
| Migrations | 37 locais, **37 aplicadas** no Supabase de teste, **nenhuma pendente** |
| Prévia publicada | inalterada: versão `eaea85a`, https://54a31813.controle-financeiro-jah.pages.dev (Cloudflare Pages, projeto `controle-financeiro`, ramo `avaliacao`) |
| Produção | inalterada; Pessoal e Empresa continuam no Flask |
| `data/gastos.db` | intacto: md5 `bf7c7d3a12030bf18826cacc1f46293e`, o mesmo do início das validações |

### MVPs deste bloco

| MVP | Implementado | Commit (MVP / registro) | Supabase de teste | Validação real | Prévia |
|---|---|---|---|---|---|
| FIN-FINANCIAMENTOS-MOTOR-1 | sim | `4de6fb5` / `ced5ae9` | `20261123090000` aplicada | 17/17 | não publicado |
| FIN-ESCRITOR-UNICO-FINAL-1 | sim | `0af3128` / `fd27469` | `20261124090000` aplicada | 6/6 | efeito só no banco (ver abaixo) |
| FIN-CATEGORIAS-RECORRENCIAS-2 | sim | `053abc9` / `347bb41` | `20261125090000` aplicada | 26 automáticas + 2 conferidas no banco + 1 refeita | não publicado |
| FIN-PATRIMONIO-2 | sim | `a3d8a3b` / `3ca1fb6` | `20261126090000` aplicada | 15 automáticas + 2 conferidas no banco | não publicado |

- Os registros completos estão no último § de cada documento: `docs/FIN_FINANCIAMENTOS_MOTOR_1.md` (§11), `docs/FIN_ESCRITOR_UNICO_FINAL_1.md` (§9), `docs/FIN_CATEGORIAS_RECORRENCIAS_2.md` (§9) e `docs/FIN_PATRIMONIO_2.md` (§9).
- **Prévia:** o `dist` publicado (`eaea85a`) é anterior aos quatro MVPs, mas usa o mesmo Supabase de teste. Por isso o escritor único já vale nela: cadastros em perfil ainda no Flask são recusados sem gravar. As telas novas (motor, semanal, Patrimônio) só aparecem numa nova publicação.
- **Pendentes do bloco:**
  - validação integrada dos quatro MVPs (autorizada, ainda não feita);
  - nova publicação na prévia (só com autorização, depois da validação integrada).

## 2. Último commit local

Para conferir: `git log -1 --oneline`. A mensagem é "FIN-TRANSFERENCIA-AMBIENTE-1: manual de transferencia, verificacao do ambiente e roteiros de homologacao versionados".

## 3. Branch utilizada

`main`, a única de trabalho. Não há ramo de MVP aberto. As outras pastas de trabalho que o Git registra (`.git/worktrees/wt_base`, `wt_head`) são antigas, presas pelo OneDrive. Elas geram o aviso "failed to delete … Permission denied" a cada commit; o aviso é inofensivo.

## 4. Commits pendentes de push (46 + o deste contrato)

Do mais antigo ao mais novo, depois de `9a50410` (`git log --reverse --oneline origin/main..main`):

```
db90a8e FIN-CARTOES-D6-INTEGRIDADE-1          43c76d0 FIN-CONTRATOS-2 (guarda Flask)
66ac45c FIN-CARTOES-RECORRENCIA-PENDENCIA-1   8c42925 FIN-CONTRATOS-2 (pagamento/estorno)
00f445f FIN-CARTOES-FECHAMENTO-PRE-REAL-1     83e9d16 FIN-CONTRATOS-2 (registro)
d60cc4a FIN-CARTOES-FECHAMENTO-ENCERRAMENTO-1 bd28ebc FIN-CONTRATOS-3 (fase A)
8c73baf FIN-CARTOES-PAGAMENTO-1               eaea85a FIN-CONTRATOS-3 (renomear)
86f830a FIN-CARTOES-PAGAMENTO-REAL-1          4de6fb5 FIN-FINANCIAMENTOS-MOTOR-1
435670b FIN-MOVIMENTACOES-1                   ced5ae9 FIN-FINANCIAMENTOS-MOTOR-1 (registro)
6f6c669 FIN-MOVIMENTACOES-REAL-1              0af3128 FIN-ESCRITOR-UNICO-FINAL-1
c56e1fb FIN-MOVIMENTACOES-REAL-1              fd27469 FIN-ESCRITOR-UNICO-FINAL-1 (registro)
9a30058 FIN-PUBLICACAO-PREVIEW-2              a3d35b2 FIN-CONTRATOS-3 (registro da 1122)
1cc8025 FIN-MIGRACAO-FIDELIDADE-FASE-1        053abc9 FIN-CATEGORIAS-RECORRENCIAS-2
7b4c3a3 FIN-MIGRACAO-FIDELIDADE-FASE-1-REAL   347bb41 FIN-CATEGORIAS-RECORRENCIAS-2 (registro)
352c4e6 FIN-FIDELIDADE-DESPESAS-1             a3d8a3b FIN-PATRIMONIO-2
728f234 FIN-FIDELIDADE-RECORRENCIAS-1         3ca1fb6 FIN-PATRIMONIO-2 (registro)
af1ea59 FIN-FIDELIDADE-DESPESAS-1 (registro)  (+ o commit deste contrato)
22b8076 FIN-FIDELIDADE-RECORRENCIAS-1 (registro)
ef6c0d8 FIN-FIDELIDADE-CARTOES-1
cc17c13 FIN-FIDELIDADE-CARTOES-1 (registro)
b1c1ac6 FIN-FIDELIDADE-CARTOES-2
bbf7a0a FIN-FIDELIDADE-CARTOES-3
653554b FIN-FIDELIDADE-MOVIMENTACOES-1
89bffa2 FIN-FIDELIDADE-CONTRATOS-1
ea5064c FIN-FIDELIDADE-PATRIMONIO-1
ca4b173 FIN-FIDELIDADE-DOCUMENTOS-1
4efbb22 FIN-FIDELIDADE-CONSOLIDACAO-1
e2599e9 FIN-AUDITORIA-GERAL-1
899eae2 FIN-FIDELIDADE-CONTRATOS-1 (rascunho)
b518308 FIN-ESCRITOR-UNICO-CONTAS-1
679cac3 FIN-ESCRITOR-UNICO-CONTAS-1 (D2)
7d48290 FIN-ESCRITOR-UNICO-CONTAS-1 (reversão do lote)
43f64cb FIN-ESCRITOR-UNICO-CONTAS-1 (registro)
9b977a6 FIN-FIDELIDADE-RECEITAS-CATEGORIAS-1
```

Esses commits existem **só** no repositório da pasta do OneDrive (`.git`). O notebook os recebe pelo §9, sem push.

## 5. Migrations aplicadas e pendentes

- **Supabase de teste** (projeto `fzjmge…`): as 37 locais estão aplicadas, de `20261020…` a `20261126090000`, e **nenhuma está pendente**. Para conferir: `venv\Scripts\python.exe scripts\supabase_migrations.py status`.
- **Reversões:** 9 arquivos em `supabase/reversao/`: a do lote `20261106`–`20261118` e as de `20261107`, `20261108`, `20261120`, `20261122`, `20261123`, `20261124`, `20261125` e `20261126`.
- **Alembic do Flask:** 29 revisões, head `f1c4d8e2a7b9`. O `gastos.db` está em `9b8a09ecc52f` (6 revisões atrás), de propósito: **não** rodar `alembic upgrade` no `gastos.db`.
- **Produção:** nenhuma migration do Supabase. O Flask segue com o `gastos.db`.

## 6. Arquivos importantes fora do Git

Classificação: **A** desenvolvimento, **B** testes, **C** só documentação, **D** temporário/dispensável, **E** sensível ou pessoal.

| Arquivo ou pasta | Onde está | Classe | Situação para o notebook |
|---|---|---|---|
| `.env.local` (Flask local: `SECRET_KEY`, `DATABASE_URL`, CVV) | raiz do projeto (OneDrive) | A, **E** | já copiado para o clone do notebook em 22/10 (AMBIENTE-EQUIPARACAO-2) e sem alteração desde então (data do arquivo: 19/08). Conferir com o verificador |
| `.env.staging` (`DATABASE_URL` do Supabase de **teste**) | raiz (OneDrive) | A, **E** | idem (data: 19/10) |
| `.env.e2e-real` (contas de teste A e B) | raiz (OneDrive) | B, **E** | idem (data: 20/10) |
| `data/gastos.db` (banco real do Flask) | `data/` (OneDrive) | **E** | não copiar para o clone; ver §11 |
| `data/backup/`, `data/backups/`, `data/uploads/`, `data/ocr/`, `data/sec_public/` | `data/` (OneDrive) | **E** | ficam no OneDrive; não versionar |
| `data/gastos-DESKTOP-3HHKJTN.db` | `data/` (OneDrive) | **E** | cópia antiga de outro computador (jan/2026). Não usar nem apagar sem decisão |
| `data/transferencia/memoria_claude/` | `data/` (OneDrive) | C | **criado por este contrato**: cópia das regras do projeto que o Claude Code guarda fora do projeto (ver §10) |
| `data/transferencia/contratos_fila/` | `data/` (OneDrive) | C | **criado por este contrato**: textos originais dos 6 contratos da fila, recuperados da transcrição. Também versionados em `docs/contratos/fila_2026-10-26/` |
| `data/transferencia/retrato_supabase_teste_pos_1126.json` | `data/` (OneDrive) | B | **criado por este contrato**: retrato do Supabase de teste depois da `1126` (só hashes) para a próxima conferência |
| PDFs pessoais na raiz e em `frontend/static/img/` (comprovante, CNPJ/QSA, demonstrativos da Caixa, notas fiscais, `taxa_TR.pdf`) | OneDrive, não rastreados | **E** | **nunca** adicionar ao Git. Não são usados pelo código |
| Imagens não rastreadas em `frontend/static/img/` (logos de bancos, ícones) | OneDrive, não rastreadas | D | o código não as referencia (conferido) |
| `doc-hub-ux-*.png`, `apply_veic2b_sql.py`, `redefinir_senha_db.ps1` | raiz, não rastreados | D | auxiliares antigos (capturas, aplicação manual de SQL do VEIC-2B, troca da senha do PostgreSQL local, que pede a senha no prompt). Não versionar sem revisão |
| Scratchpad da sessão do Claude (`%TEMP%\claude\…\scratchpad`) | **fora do OneDrive** | B/C/D | o que era necessário foi trazido para o repositório (§6.1); o resto é dispensável |
| Transcrição da sessão `03e0421d…jsonl` (`%USERPROFILE%\.claude\projects\…`) | **fora do OneDrive** | C, **E** | histórico completo; contém saídas de comandos. Não copiar para o Git; os contratos já foram extraídos |

### 6.1 Scratchpad: o que foi trazido e o que fica

- **Trazido para o repositório** (`scripts/homologacao_real/`): os roteiros de homologação real com perfil temporário e limpeza por identidade:
  - `lote_real.py` (base comum);
  - `motor_real.py`, `escritor_real.py`, `cr_real.py`, `pat_real.py` (um por MVP);
  - `digital_lote.py` (retrato do banco).

  Os caminhos foram trocados de absolutos para relativos à raiz do projeto, e o estado de cada execução vai para `data/homologacao_real/`, ignorada pelo Git. Os originais não foram apagados. Uso no `README.md` da pasta.
- **Fica fora** (dispensável ou sensível):
  - capturas de tela do Flask e do novo aplicativo (podem mostrar dados; classe E);
  - `backup_pre_real/` (cópia antiga de código que o Git já guarda);
  - logs de testes, saídas JUnit e retratos JSON intermediários;
  - geradores de migration já aplicados (`cr2/`, `gerar_*.py`): o resultado está nas migrations versionadas;
  - `mvp-stack/postgrest/postgrest.exe` (77 MB): o notebook já tem o PostgREST 16.5 com SHA-256 conferido (AMBIENTE-EQUIPARACAO-1).

## 7. Dependências necessárias

| Componente | Versão homologada | Manifesto / origem |
|---|---|---|
| Python | 3.11.9 | `runtime.txt`; pacotes em `requirements.txt` (versões exatas) |
| Node.js / npm | ≥ 22 (casa: 24.22.1 / 11.19.1; notebook em 22/10: 24.11.1 / 11.6.2) | `package.json` e `package-lock.json` na raiz e em `web/` |
| Playwright | 1.59.1 + Chromium | `package.json` da raiz |
| `@supabase/supabase-js` | 2.118.0 | `web/package.json` |
| `pdfjs-dist` | 6.4.299 | `web/package.json` (entrou depois de 22/10: `npm ci` em `web/` no notebook) |
| Wrangler (Cloudflare) | 4.129.0 | `web/package.json` (devDependency exata) |
| PostgreSQL | 18 (`initdb`/`pg_ctl` para os testes descartáveis) | instalação local; `bin` no PATH ou `CF_MVP_PG_BIN` |
| PostgREST | 16.5 | `POSTGREST_BIN` (sem ele, E2E e testes REST são pulados) |
| Supabase CLI | 2.116.0 | autenticada e vinculada ao projeto de teste |
| Git | 2.5x + Git Credential Manager | — |
| Tesseract / Poppler | opcionais (OCR) | com eles instalados, 2 testes de `test_ocr_tools` falham (preexistente) |
| Docker | **não usado** | — |

- **Dependências não declaradas:** nenhuma no código do aplicativo.
  - `cryptography`, `pg8000`, `pypdfium2` e `pyodide_js` só aparecem na prova de conceito `docs/poc/cf-python-poc-1/`.
  - `alembic` vem com o `Flask-Migrate`, e `pypdfium2` com o `pdfplumber`.
- **`requirements-dev.txt`** é um manifesto antigo para SQLite: falta `psycopg2-binary`, `openpyxl` e `pdfplumber`. **Usar o `requirements.txt`.**
- **Nenhuma biblioteca foi atualizada** por este contrato.

### 7.1 Variáveis de ambiente

Nomes e placeholders estão no `.env.example` (seção nova no fim).

| Variável | Onde | Uso |
|---|---|---|
| `APP_ENV`, `SECRET_KEY`, `DATABASE_URL`, `CARTOES_CVV_MASTER_PASSWORD`, `FLASK_*` | `.env.local` | Flask local |
| `DATABASE_URL` (usuário `postgres.<ref-teste>`) | `.env.staging` | migrations e homologação no Supabase de teste |
| `CF_EMAIL_A`, `CF_SENHA_A`, `CF_EMAIL_B`, `CF_SENHA_B` | `.env.e2e-real` | contas de teste A e B |
| `POSTGREST_BIN` | variável de usuário do Windows | E2E local e testes REST |
| `CF_MVP_PG_BIN` | opcional | `bin` do PostgreSQL, se não estiver no PATH |
| `CF_SUPABASE_PROJECT_REF` | opcional | padrão: projeto vinculado na Supabase CLI |
| `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` | só no build manual | os roteiros leem a chave **pública** pela CLI |

## 8. Preparar o notebook

O notebook já foi equiparado em 22/10/2026 (`docs/AMBIENTE_EQUIPARACAO_1.md`): ferramentas, venv, `npm ci`, PostgreSQL 18, PostgREST 16.5, Supabase CLI, Wrangler e os três `.env` no clone. Por isso, normalmente basta conferir.

1. Abrir o PowerShell **na raiz do clone do notebook**, fora do OneDrive (em 22/10: `C:\Users\ssp\dev\Controle-Financeiro`).
2. Atualizar o código (§9).
3. Atualizar as dependências do `web/`. Depois de 22/10 entrou o `pdfjs-dist` 6.4.299 no `web/package.json` (commit `bbf7a0a`, um dos 47), então este passo **é necessário**:
   ```powershell
   cd web; npm ci; cd ..
   ```
   Os manifestos Python e o da raiz não mudaram (`git diff --stat b669d5d HEAD -- requirements.txt runtime.txt package.json package-lock.json` vazio). Rodar `venv\Scripts\python.exe -m pip install -r requirements.txt` e `npm ci` na raiz só se esse comando mostrar diferença.
4. Rodar o verificador:
   ```powershell
   venv\Scripts\python.exe scripts\verificar_ambiente.py --rede
   ```
   Ele só lê e pode ser repetido. Esperado: **0 FALTA**. O aviso de commits fora do `origin/main` é normal até o push autorizado; o de Tesseract também.
5. Se aparecer **FALTA** em `.env.*` ou `data/`, ver o §10.

## 9. Obter o código no notebook (sem push)

O repositório com os 47 commits está na pasta do OneDrive. O clone do notebook os busca por `fetch` local, como na equiparação de 22/10.

1. **Esperar o OneDrive terminar de sincronizar** a pasta do projeto no notebook (ícone sem setas). Não abrir essa pasta no VS Code durante o processo.
2. Conferir que a cópia do OneDrive chegou inteira e no commit certo:
   ```powershell
   $origem = "$env:OneDrive\Kortex Brasil\Controle Financeiro"
   git -C $origem log -1 --oneline     # deve mostrar o commit FIN-TRANSFERENCIA-AMBIENTE-1
   git -C $origem fsck --no-dangling   # sem erros
   ```
   Se `$env:OneDrive` não apontar para a conta certa, usar o caminho completo da pasta.
3. No clone do notebook:
   ```powershell
   git status                                  # precisa estar limpo
   git fetch $origem main
   git merge-base --is-ancestor HEAD FETCH_HEAD; $?   # True: o notebook nao tem commit proprio
   git merge --ff-only FETCH_HEAD
   git log -1 --oneline
   ```
   **Se o teste der `False`**, o notebook tem commits que a casa não tem: **parar**, não mesclar e registrar. A decisão é do titular.
4. Os arquivos fora do Git (`.env.*`, `data/`) não vêm pelo Git (§10 e §11).
5. **Regra de uso:** Git só no clone. A pasta do OneDrive fica como origem e arquivo pessoal. Não usar as duas ao mesmo tempo, porque o OneDrive cria cópias de conflito dentro do `.git`.

O push dos 47 commits para o GitHub (`origin`) **não** foi feito e depende de autorização. Feito de qualquer uma das máquinas, ele é um avanço direto a partir de `9a50410`.

## 10. Configurações a recriar ou conferir manualmente

| Item | Ação | Classificação |
|---|---|---|
| `.env.local`, `.env.staging`, `.env.e2e-real` | já estão no clone desde 22/10. Se o verificador acusar falta: copiar da pasta do OneDrive para a raiz do clone (cópia local, sem e-mail nem nuvem pública) e restringir o acesso ao usuário. **Nunca** commitar | DEPENDE DO USUÁRIO |
| `POSTGREST_BIN` | já definida em 22/10; o verificador confere | PRONTO |
| `bin` do PostgreSQL no PATH | já está; o PostgREST no Windows precisa da `libpq.dll` | PRONTO |
| Supabase CLI | autenticada (`supabase login`) e vinculada ao projeto **de teste** (`supabase link --project-ref <ref-teste>`); o verificador confere o prefixo `fzjmge` | DEPENDE DO USUÁRIO, se expirou |
| Cloudflare (Wrangler) | autenticado em 22/10 (`npx wrangler login`); só é usado na publicação, que exige autorização | DEPENDE DO USUÁRIO |
| Cloudflare Access da prévia | nada a fazer no notebook (configuração da conta) | PRONTO |
| GitHub | Git Credential Manager do notebook; o push exige autorização | DEPENDE DO USUÁRIO |
| Identidade do Git | `git config user.name` / `user.email`, iguais aos da casa | PRONTO (22/10) |
| Memória do Claude Code | o Claude guarda regras do projeto em `%USERPROFILE%\.claude\projects\<pasta-do-projeto>\memory\`. No notebook a pasta tem outro nome (o do clone). Copiar o **conteúdo** de `data/transferencia/memoria_claude/` para essa pasta (abrir o Claude Code uma vez no clone para ela ser criada) | DEPENDE DO USUÁRIO |
| Credenciais | nada versionado. A varredura dos arquivos rastreados só achou placeholders (`senha…`, `SUA_…`, `<senha>`) | PRONTO |

## 11. Bancos: procedimento seguro

| Banco | Onde | Finalidade | No notebook |
|---|---|---|---|
| `data/gastos.db` (SQLite) | pasta do OneDrive | **dados reais** do Flask (Pessoal e Empresa) | **não copiar** para o clone. Usar a cópia que o OneDrive já sincroniza, e só quando for usar o Flask com dados reais. Nunca nas duas máquinas ao mesmo tempo |
| PostgreSQL local `controle_financeiro_dev` | serviço local do notebook | Flask de desenvolvimento, só com dados-padrão das migrations | já existe desde 22/10; não precisa de cópia |
| Clusters descartáveis dos testes | criados e apagados pela suíte (`tests/supabase_local.py`) | testes de banco e E2E | nada a fazer |
| Supabase de teste (`fzjmge…`) | nuvem | homologação real (só perfil temporário) | conexão pelo `.env.staging` |

**Se for preciso levar o `gastos.db` para fora do OneDrive** (não recomendado):
1. Fechar o Flask nas duas máquinas e esperar a sincronização.
2. Copiar o arquivo para uma pasta local protegida (só o usuário).
3. Conferir com `certutil -hashfile <arquivo> MD5`: deve dar o mesmo md5 da origem (o de 27/10 está no §1).
4. Não versionar, não enviar por e-mail nem por serviço público, e não abrir nas duas máquinas ao mesmo tempo.

**Backup e restauração** dos bancos locais: `docs/uso-local/backup-postgresql-local.md`, o serviço `backend/services/backup_service.py` e os testes `tests/test_backup_local.py` / `tests/test_backup_restore_test.py`. A restauração **só** em banco descartável, nunca sobre um banco existente.

## 12. Executar o aplicativo

```powershell
# Flask local (usa .env.local; PostgreSQL local de desenvolvimento)
iniciar_servidor.bat
# equivale a: venv\Scripts\python.exe backend\app.py

# Novo aplicativo: build com a URL e a chave PUBLICA do Supabase de teste (dist fica fora do Git)
cd web; $env:SUPABASE_URL="https://<ref-teste>.supabase.co"; $env:SUPABASE_PUBLISHABLE_KEY="sb_publishable_..."; node scripts/build.mjs; cd ..
```

O E2E local monta o próprio `dist` e o serve com PostgREST e um cluster descartável; não precisa de build manual. Os roteiros de homologação real também constroem o `dist` sozinhos, com a chave pública lida pela CLI.

O antivírus do notebook bloqueia os `.exe` que o pip cria no venv: usar sempre `venv\Scripts\python.exe -m …`.

## 13. Executar os testes

```powershell
venv\Scripts\python.exe -m pytest -q                       # suíte Python inteira (clusters descartáveis)
cd web; node --test "tests/unit/*.test.mjs"; cd ..          # unitários do novo aplicativo
venv\Scripts\python.exe web\tests\e2e\run_e2e.py            # E2E do novo aplicativo (precisa de POSTGREST_BIN)
venv\Scripts\python.exe scripts\testes_impacto.py           # testes pelo impacto das alterações (só lista)
venv\Scripts\python.exe scripts\testes_impacto.py --executar
```

**Resultados de referência** (casa, 27/10/2026, na árvore do `a3d8a3b`):
- Python: 1943 passed, 18 skipped, 5 failed;
- unitários: 30/30;
- E2E: 93/93.

As 5 falhas são preexistentes e conhecidas (§15). No notebook, sem Tesseract e Poppler, as 2 de OCR passam.

**Os testes nunca gravam em banco real.** A suíte usa só clusters descartáveis. Os roteiros `scripts/*_real.py` e `scripts/homologacao_real/` usam o Supabase **de teste** e perfis temporários, e só devem rodar com autorização. O `testes_impacto.py` lista esses roteiros, mas não os executa.

## 14. Validar a conexão ao Supabase de teste

Só leitura:

```powershell
venv\Scripts\python.exe scripts\supabase_migrations.py status    # "aplicadas no remoto: 37", "Pendentes: nenhuma"
venv\Scripts\python.exe scripts\verificar_ambiente.py --rede
```

O retrato completo, também só leitura, serve para comparar com o de 27/10:

```powershell
venv\Scripts\python.exe scripts\homologacao_real\digital_lote.py data\homologacao_real\retrato_agora.json
```

Comparar com `data\transferencia\retrato_supabase_teste_pos_1126.json`. As tabelas mudam se alguém usou a prévia nos perfis fictícios 31 e 39; as funções e as migrations não devem mudar.

Os scripts recusam qualquer projeto que não seja o de teste.

## 15. Problemas conhecidos

- **5 falhas preexistentes na suíte Python**, iguais antes e depois dos quatro MVPs (conferido numa cópia limpa do HEAD anterior):
  - `test_receitas_ux` e `test_veiculos_mobilidade_2b`: dependem da data;
  - `test_categorias_sistemicas_mobilidade` (`KeyError: 'IPVA'`): é de Mobilidade, FIN-MOBILIDADE-2;
  - `test_ocr_tools` (2): só falham com Tesseract e Poppler instalados.
- **E2E legado do Flask** (`npx playwright test` na raiz): as specs não fazem login desde o SEG-1 e param em "Entre para continuar". Não é regressão.
- **Clone sem `data/`:** a coleta do pytest falha com "unable to open database file". Criar `data\` vazia resolve; o verificador acusa.
- **Avisos do Git** "failed to delete '.git/worktrees/wt_base'": worktrees antigos presos pelo OneDrive na pasta de casa. Inofensivos.
- **`inspecionar` dos roteiros de homologação** acusa FALHA nos MVPs já aplicados: foi feito para rodar **antes** da aplicação.
- **Conflitos do OneDrive dentro do `.git`** (por exemplo `.git/gk/config`, gravado pelo GitLens): por isso o Git fica só no clone (§9).
- **Diferença de R$ 1,00 e calibração do contrato real da Caixa:** decisão registrada no motor (§10 do doc); o contrato real será recadastrado com os dados da Caixa, sem transferir o cronograma antigo.

## 16. Próximos MVPs

Pela ordem combinada:
1. **Validação integrada** dos quatro MVPs deste bloco: relações entre recorrências, despesas, contas bancárias, financiamentos e patrimônio. Autorizada, ainda não feita.
2. **Publicação do conjunto na prévia protegida:** só com nova autorização.
3. **FIN-MOBILIDADE-2:** escrita de Mobilidade; a migration do cenário ativo por perfil exige autorização. Contrato em `docs/contratos/fila_2026-10-26/FIN-MOBILIDADE-2.md`.
4. **FIN-DOCUMENTOS-2:** upload e Storage privado por perfil, "A partir de documento", OCR complementar.
5. **FIN-RELATORIOS-CONFIG-1:** PDF/XLSX/ZIP, configurações, backup; não armazenar CVV.
6. **Decisões guardadas para contratos futuros:**
   - saneamento dos dados sensíveis dos cartões;
   - recadastro do financiamento com os dados reais da Caixa, com proteção do histórico e sem alterações na produção.
7. **Dashboard e refinamentos:** por último.

A próxima **migration** ainda não existe. Ela virá do FIN-MOBILIDADE-2 (cenário ativo), com versão posterior a `20261126090000`.

Pendências registradas nos documentos dos MVPs:
- tela de parcelas históricas;
- documentos e conferências da Caixa;
- cadastro de índices;
- pagamento direto sem despesa;
- troca do escritor do catálogo e gestor;
- entrada de "data prevista" e de "recebimento sem previsão" na tela de Receitas;
- botão de exclusão de bem.

## 17. Checklist final (notebook)

- [ ] OneDrive sincronizado; `git -C <pasta do OneDrive> log -1` mostra o commit deste contrato; `fsck` sem erros.
- [ ] No clone: `git status` limpo, `merge-base --is-ancestor` = True, `merge --ff-only` feito.
- [ ] `git log -1` no clone = o mesmo da pasta do OneDrive.
- [ ] `npm ci` em `web/` (traz o `pdfjs-dist`).
- [ ] `venv\Scripts\python.exe scripts\verificar_ambiente.py --rede` com **0 FALTA** e "Pendentes: nenhuma".
- [ ] `.env.local`, `.env.staging` e `.env.e2e-real` presentes e ignorados pelo Git (o verificador confere).
- [ ] Memória do Claude Code copiada de `data/transferencia/memoria_claude/`.
- [ ] Suíte rápida: `node --test` em `web/` com 30/30; `pytest tests/test_verificar_ambiente.py` com 3/3.
- [ ] (Opcional) Suíte completa e E2E, comparando com os números do §13.
- [ ] A pasta do OneDrive não é mais usada para Git enquanto o clone estiver em uso.

---

## Relatório final

### A. Estado atual do repositório — **PRONTO**
- `main`, sem alterações rastreadas pendentes depois do commit deste contrato;
- 37 migrations, 9 reversões;
- documentos dos quatro MVPs e ROADMAP atualizados com a aplicação.

### B. Commits locais pendentes — **DEPENDE DO USUÁRIO**
47 commits fora do GitHub (§4). Vão para o notebook por `fetch` local (§9); o push depende de autorização.

### C. Migrations — **PRONTO**
37/37 aplicadas no Supabase de teste; nenhuma pendente; produção sem migrations do Supabase.

### D. Arquivos necessários fora do Git — **DEPENDE DO USUÁRIO**
- `.env.*` e `data/` (§6, §10, §11): já estão no clone desde 22/10 ou no OneDrive; o verificador confere.
- O que só existia no scratchpad e era necessário foi versionado (§6.1).

### E. Dependências do ambiente — **DEPENDE DO USUÁRIO** (um comando)
Só o `web/package.json` mudou desde 22/10 (`pdfjs-dist`): rodar `npm ci` em `web/`. Python e raiz sem mudança; nenhuma dependência não declarada no aplicativo (§7).

### F. Configurações que exigem intervenção — **DEPENDE DO USUÁRIO**
- renovar logins (Supabase CLI, Wrangler, GitHub) se expiraram;
- copiar a memória do Claude Code;
- copiar os `.env` só se o verificador acusar falta.

### G. Testes realizados (casa, 27/10/2026)
- **Validação de Categorias e Recorrências** (árvore do `053abc9`): Python 1932 passed, 18 skipped, 5 failed (preexistentes); unitários 30/30; E2E 93/93.
- **Validação de Patrimônio** (árvore do `a3d8a3b`): Python 1943 passed, 18 skipped, 5 failed (as mesmas); unitários 30/30; E2E 93/93.
- **Deste contrato:**
  - `tests/test_verificar_ambiente.py` 3/3;
  - `verificar_ambiente.py --rede` com 0 FALTA (avisos: commits fora do GitHub, Tesseract ausente);
  - importação dos roteiros copiados com caminhos relativos (a raiz e a pasta de estado conferidas);
  - integridade: `gastos.db` com o mesmo md5; migrations e reversões sem alteração; varredura de segredos sem achado real; nenhum push; prévia inalterada (última publicação `eaea85a`).

### H. Arquivos criados ou alterados por este contrato
- **Versionados:**
  - `docs/FIN_TRANSFERENCIA_AMBIENTE_1.md` (este documento);
  - `scripts/verificar_ambiente.py` e `tests/test_verificar_ambiente.py`;
  - `scripts/homologacao_real/` (6 roteiros + `README.md`);
  - `docs/contratos/fila_2026-10-26/` (7 textos);
  - `.env.example` (seção nova, só placeholders);
  - `docs/ROADMAP.md` (linha deste contrato).
- **Fora do Git** (`data/transferencia/`, sincronizado pelo OneDrive): memória do Claude, contratos e retrato do Supabase de teste.

### I. Riscos identificados
- **Conflitos do OneDrive no `.git`** se as duas máquinas usarem a mesma pasta: Git só no clone (§9).
- **Commits só na pasta do OneDrive** até o push autorizado: se a pasta for danificada antes do `fetch` do notebook, eles se perdem. Mitigação: fazer o `fetch` logo, e o push assim que autorizado.
- **`gastos.db` aberto nas duas máquinas** gera cópias de conflito: usar o Flask com dados reais numa máquina por vez.
- **Credenciais locais desatualizadas:** se alguma senha mudar na casa, copiar de novo (o verificador só confere os nomes).
- **Validação integrada ainda não feita:** os quatro MVPs foram validados um a um no Supabase de teste.

### J. Procedimento resumido no notebook
1. Esperar o OneDrive sincronizar.
2. No clone: `git fetch "<pasta do OneDrive>" main` e depois `git merge --ff-only FETCH_HEAD` (só se `merge-base --is-ancestor` = True).
3. `cd web; npm ci; cd ..`, depois `venv\Scripts\python.exe scripts\verificar_ambiente.py --rede`, com 0 FALTA.
4. Copiar a memória do Claude Code.
5. Seguir pelo §16, item 1 (validação integrada), quando autorizado.

### Respostas objetivas

1. **Posso continuar o desenvolvimento no notebook?** Sim, depois do §9 (fetch local e avanço direto) e do verificador com 0 FALTA.
2. **O que preciso copiar?**
   - Pelo Git (fetch da pasta do OneDrive): os 47 commits.
   - Os `.env.*` só se o verificador acusar falta (já estão no clone desde 22/10).
   - O conteúdo de `data/transferencia/memoria_claude/` para a memória do Claude Code.
   - O `gastos.db` não: fica no OneDrive.
3. **O que preciso instalar?** Só o `npm ci` em `web/`, para trazer o `pdfjs-dist` 6.4.299, que entrou depois de 22/10. As ferramentas (Python, Node, PostgreSQL, PostgREST, Supabase CLI, Playwright, Wrangler) já estão no notebook desde 22/10.
4. **O que preciso configurar?** Renovar os logins que tiverem expirado (Supabase CLI, Wrangler, GitHub) e copiar a memória do Claude. O resto, o verificador confere.
5. **Quais commits ainda não estão no remoto?** Os 46 do §4 mais o deste contrato, de `db90a8e` até o último, todos depois de `9a50410`.
6. **Existe algum arquivo importante somente no scratchpad?** Não mais.
   - Os roteiros de homologação foram versionados em `scripts/homologacao_real/`.
   - Os textos dos contratos da fila, que só existiam na transcrição, estão em `docs/contratos/fila_2026-10-26/`.
   - O último retrato do Supabase de teste está em `data/transferencia/`.
   - O resto do scratchpad é dispensável.
7. **Qual é a próxima migration pendente?** Nenhuma pendente: 37/37 aplicadas no Supabase de teste. A próxima a ser criada será a do FIN-MOBILIDADE-2 (cenário ativo), que exige autorização.
8. **Qual é o próximo MVP?**
   - Antes, fechar o bloco atual: validação integrada (autorizada) e publicação na prévia (só com autorização).
   - Depois, **FIN-MOBILIDADE-2**.
9. **Há risco de perder algum trabalho?** Baixo, com uma ressalva: os 47 commits estão só no `.git` da pasta do OneDrive até o `fetch` do notebook ou o push autorizado. Recomendação: fazer o `fetch` logo na chegada ao notebook.
10. **O ambiente está pronto para a transferência?** Sim: **PRONTO**, dependendo só das ações do usuário marcadas acima. A transferência efetiva e o push aguardam autorização.
