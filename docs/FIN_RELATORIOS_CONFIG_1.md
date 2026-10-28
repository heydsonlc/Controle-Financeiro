# FIN-RELATORIOS-CONFIG-1 — Relatórios, Configurações e Backup

Data: 28/10/2026. São os itens B2 e B3 do FIN-BLOCO-B-1 (contrato em `docs/contratos/fila_2026-10-26/FIN-RELATORIOS-CONFIG-1.md`).

**Situação:**
- O primeiro relatório completo está pronto e conferido com o Flask: **bens do Patrimônio, em Excel e PDF**.
- A rotina de backup e restauração verificável também está pronta.
- Os demais relatórios ficam inventariados, com o caminho já aberto (§5).
- **Nenhuma dependência nova e nenhuma migration.**

## 1. Relatórios migrados

### Bens patrimoniais da Empresa (Excel e PDF)

- **Rotas:** `GET /api/patrimonio/bens/exportar-excel|pdf`, com os mesmos filtros e só no perfil Empresa. Outros perfis recebem 403, como no Flask.
- **Geração:** no navegador, a partir de `patrimonio_bens_tela`, a mesma lista que a tela já mostra (leitura conferida com o Flask no FIN-PATRIMONIO-2).
  - `web/src/js/relatorio-patrimonio.js` monta as planilhas "Resumo" e "Bens" e as linhas do PDF, como o `PatrimonioRelatorioService`.
  - `web/src/js/exportacao-xlsx.js` é o XLSX sem biblioteca: ZIP armazenado com CRC32, estilos e a formatação do `_formatar_planilha` (cabeçalho, painel congelado, autofiltro, larguras, formato `R$ #,##0.00`).
  - `web/src/js/exportacao-pdf.js` é o mesmo PDF mínimo do Flask (`_pdf_simples`).
- **Ponte da tela:** `ponte-api.js` passou a entregar arquivo como o `send_file` do Flask (`Content-Type` e `Content-Disposition`). A tela original baixa o arquivo sem alteração.
- **Conferência com o Flask** (`tests/test_relatorios_patrimonio.py`), sem filtro e com filtro de categoria e ano, com a hora de geração fixada nos dois lados:
  - **PDF idêntico byte a byte**;
  - **XLSX igual** em abas, valores, formatos, estilo do cabeçalho, painel congelado, autofiltro e larguras, lidos pelo `openpyxl`.
- **Fidelidade nos detalhes do Flask:**
  - soma em `Decimal` sobre o texto do `float`;
  - moeda com arredondamento meio para o par;
  - formato monetário só em `int` e `float`;
  - zero contando como texto vazio na largura;
  - data vazia impressa como "None" no PDF.
- **E2E:** `patrimonio_tela.spec.mjs` baixa o Excel e o PDF pelos botões da tela, com o nome do Flask e assinatura válida.

## 2. Configurações

| Item | Situação |
|---|---|
| Perfis (nome, tipo, documento, cor, avatar, padrão, inativar e reativar) | Já no novo aplicativo (FIN-MIGRACAO-FIDELIDADE-FASE-1 e FIN-ESCRITOR-UNICO-FINAL-1), com escritor único |
| **Preferências** (`/api/preferencias`) | **Decisão do titular.** No Flask é um registro **único e global** (`Preferencia.query.first()`): nome do usuário, tema, renda, mês de início, entre outros. Num aplicativo com várias contas isso precisa de dono. Proposta: tabela por usuário (`auth.users`), o que exige migration estrutural. Não foi implementado |
| Exportar/importar configurações (`/api/backup/configuracoes/*`) | Depende da decisão sobre Preferências |
| Ferramentas de OCR e de backup do Flask (`/api/ocr/*`, `/api/backup/ferramentas/*`) | São caminhos de executáveis da máquina do Flask. Não se aplicam ao aplicativo estático |

## 3. Backup e restauração

**Mecanismo do Flask:**
- `pg_dump` local, agendado na máquina; bloqueado em ambiente hospedado (`backup_bp.before_request`).
- Restauração sobre o próprio banco.

**Estratégia para o Supabase:**
1. **Backups gerenciados do Supabase** (diários; PITR conforme o plano) como primeira linha.
2. **`scripts/backup_banco.py`**, a cópia verificável fora do Supabase, sem dependência nova (`pg_dump` e `pg_restore` do PostgreSQL instalado):
   - `exportar`:
     - dump dos esquemas `public` e `financeiro`;
     - arquivo **separado dos documentos** (`ir_comprovante_arquivo`);
     - dados de `auth.users`;
     - **manifesto** com SHA-256, tamanho e linhas por tabela.
   - **Segurança:** a conexão vem só de variável de ambiente e nunca é impressa; a exportação apenas lê o banco.
   - `verificar` confere os SHA-256.
   - `restaurar`:
     - **só num banco vazio**, recusa banco existente;
     - restaura primeiro as contas de login e depois o banco;
     - confere as linhas por tabela com o manifesto.
3. **Documentos:** ficam no banco, então vão no backup do banco e, também, no arquivo próprio.

**Testes** (`tests/test_backup_banco.py`, só clusters descartáveis):
- backup restaurado num banco novo com **conteúdo idêntico**, incluindo o arquivo do documento byte a byte;
- restauração sobre banco existente recusada;
- arquivo alterado detectado;
- conexão nunca aparece na saída.

**Achado:** as tabelas `categorias`, `perfil_acesso` e `operacao_*` apontam para `auth.users`. Um backup só de `public` e `financeiro` não restaura sem as contas de login, e por isso o script também as leva.

**Pendente de autorização (Bloco C/D):**
- rodar `exportar` contra o Supabase de teste, que só lê;
- definir onde guardar os backups, sempre cifrados e fora do OneDrive público;
- ensaiar a restauração num projeto Supabase novo.

## 4. Segurança (B3)

- **Armazenamento:**
  - nenhum bucket;
  - os arquivos ficam no banco, lidos só por funções que conferem o perfil (`arquivo_comprovante_tela`);
  - id de outro perfil volta "não encontrado" (testado em `test_supabase_documentos_escrita.py`).
- **Escritas:** todas por funções `security definer` com o escritor do perfil. `anon` sem acesso, e as auxiliares sem `EXECUTE` (testes de privilégios por MVP).
- **Frontend:** só a chave publicável. A lista de RPCs liberadas (`build.test.mjs`) amarra cada RPC de escrita à tela que a usa.
- **Exportações:** não alteram dados (a do Patrimônio só lê `patrimonio_bens_tela`) e não levam dados de cartão.
- **CVV:** não é armazenado no novo aplicativo. Número completo e validade do cartão são recusados no cadastro (FIN-FIDELIDADE-CARTOES-1). O saneamento dos dados antigos do Flask segue para procedimento próprio (Bloco C, C2).

## 5. Relatórios pendentes

Todos usam o mesmo caminho do §1: dados das leituras já conferidas, geradores sem biblioteca e conferência com o Flask.

| Relatório (Flask) | Serviço | Observação |
|---|---|---|
| IR: `GET /api/ir/relatorios/excel` e `pdf` | `IrRelatorioService` (419 linhas) | Usa o mesmo `_pdf_simples`; o Excel segue o padrão do `openpyxl` |
| IR: `GET /api/ir/relatorios/resumo` | idem | Só leitura (JSON) |
| Saídas sem documento: Excel e PDF | `LastroRelatorioService` (331 linhas) | — |
| Documentos da Empresa: ZIP | `DocumentoZipService` (407 linhas) | O ZIP armazenado do `exportacao-xlsx.js` serve de base |
| Exportar e importar configurações | `BackupService` | Depende da decisão sobre Preferências (§2) |

## 6. Arquivos

**Novos:**
- `web/src/js/exportacao-xlsx.js`, `web/src/js/exportacao-pdf.js`, `web/src/js/relatorio-patrimonio.js`;
- `scripts/backup_banco.py`;
- `tests/test_relatorios_patrimonio.py`, `tests/test_backup_banco.py`.

**Alterados:**
- `web/src/js/ponte-api.js` (resposta de arquivo);
- `web/src/js/patrimonio-adaptador.js` (exportações);
- `web/src/paginas/patrimonio.html` (aviso);
- `web/tests/e2e/patrimonio_tela.spec.mjs`;
- `tests/test_supabase_documentos_escrita.py` (Documentos × Financiamentos).
