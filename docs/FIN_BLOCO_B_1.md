# Relatório B — FIN-BLOCO-B-1 (Documentos, Relatórios e Configurações)

Data: 28/10/2026. Contrato: `docs/contratos/fila_2026-10-27/FIN-BLOCO-B-1.md`.

**Situação: APROVADO COM RESSALVAS.**
- O que foi entregue está consistente, conferido com o Flask e sem regressão.
- Parte do escopo fica pendente, registrada abaixo; nada disso bloqueia a homologação geral (Bloco C).

## 1. Documentos (B1, FIN-DOCUMENTOS-2)

Commit `4277cd0`; detalhe em `docs/FIN_DOCUMENTOS_2.md`.

**Concluído:**
- **Envio de documentos:**
  - o arquivo fica **no banco, privado do perfil**, sem bucket;
  - validações do Flask: tipo, MIME, vazio, 10 MB, assinatura e nome seguro;
  - duplicidade por SHA-256 no perfil.
- **Consulta e download** autorizados só pelo perfil (já existiam), agora com arquivos enviados pelo próprio novo aplicativo.
- **Revisão e validação.**
- **Exclusão segura** (o Flask não tinha): só documento sem vínculo nenhum e não validado.
- **Vínculos:** criar, editar e remover (remover inativa, preservando o histórico), com "um documento, um bem".
- **Despesa ou lançamento a partir do documento**, sem duplicar:
  - pagamento pela conta bancária através do motor de pagamento;
  - no cartão, pelo motor de compras.
- **OCR complementar:** o texto de PDF textual é extraído no navegador (`pdf.js`). Sem ele, o documento fica para revisão manual, sem bloquear o cadastro.
- **Integração:** Documentos × Patrimônio, × Financiamentos e × Despesas testados.
- **Escritor único:** o blueprint `ir` inteiro foi guardado no Flask.
- **Fidelidade:** as mesmas linhas que o Flask, com envio real em multipart.

**Pendente:**
- interpretação de NFS-e e cupom fiscal, e OCR de imagem;
- Documentos da Empresa (metadados, checklist, saídas sem documento, categorias IR);
- o atalho "A partir de documento" na tela de Despesas, que já tem a função pronta.

## 2. Relatórios e Configurações (B2, FIN-RELATORIOS-CONFIG-1)

Commit `41d8353`; detalhe em `docs/FIN_RELATORIOS_CONFIG_1.md`.

**Concluído:**
- **Relatório de bens do Patrimônio (Excel e PDF), gerado no navegador sem biblioteca:**
  - **PDF idêntico byte a byte** ao do Flask;
  - **XLSX igual** em valores, formatos, estilo, painel, filtro e larguras;
  - baixado pela tela, com o mesmo nome de arquivo.

  Os geradores (`exportacao-xlsx.js`, `exportacao-pdf.js`) servem de base para os demais relatórios.
- **Backup e restauração verificáveis** (`scripts/backup_banco.py`):
  - dump de `public` e `financeiro`, arquivo separado de documentos, contas de login e manifesto SHA-256;
  - restauração só em banco vazio, conferida por linhas.

  Testado só em clusters descartáveis.
- **Configurações de perfil:** já existiam, com escritor único.

**Pendente:**
- relatórios de IR (Excel, PDF, resumo), de saídas sem documento (Excel, PDF) e o ZIP dos documentos da empresa;
- exportar e importar configurações.

**Decisão do titular:**
- **Preferências:** no Flask é um registro único e global. No novo aplicativo precisa de dono, e a proposta é uma tabela por usuário, o que é migration estrutural.

## 3. Migrations e armazenamento

- **Locais, não aplicadas no remoto:** `20261127090000` (Mobilidade, do Bloco A) e `20261128090000` (Documentos), ambas com reversão. O remoto segue com 37 aplicadas, e estas 2 constam como pendentes.
- **Armazenamento:** **nenhuma configuração remota necessária.** Os arquivos ficam no banco e entram no backup. Não foi criado bucket nem alterado nada remoto.
- **Ordem de reversão:** 1128 → 1127 → 1126 → 1125 → 1124 → 1123.

## 4. Testes

- **Nível 3, no fechamento:** Python **2017 aprovados**, 3 falhas preexistentes e 1 desmarcado (o que lê `.env.staging`); web unit **30/30**; E2E **93/93**. Nenhuma regressão nova.
  - Causas das 3 falhas, já diagnosticadas para o C5:
    - `test_receitas_ux` depende da data: a fonte orça os 12 meses a partir do mês atual, e o teste fixa maio de 2026;
    - `test_ocr_tools` ×2 dependem do ambiente: a variável `POPPLER_PATH` está definida na máquina e os testes não a isolam.
- **Testes novos:**
  - `test_supabase_documentos_escrita.py` (10);
  - `test_relatorios_patrimonio.py` (2);
  - `test_backup_banco.py` (3);
  - E2E de Documentos (revisão e envio pela ponte) e de Patrimônio (downloads).
- **Integridade:** `gastos.db` inalterado; PostgreSQL local persistente idêntico; Supabase remoto sem alteração.

## 5. Commits locais (sem push)

`4277cd0` (Documentos), `41d8353` (Relatórios e backup) e este, de encerramento. São 54 commits à frente do GitHub.

## 6. Bloqueadores

Nenhum bloqueador para o Bloco C. Itens para o C e o D:
- **Segurança de cartões (C2):** o Flask guarda o **CVV e o número completo em texto puro** (`config_agregador`). O Supabase de teste está limpo (3 cartões, nenhum dado sensível). Na migração real, essas colunas não podem ser levadas, e o saneamento dos dados antigos pede decisão.
- **Restauração e backup no Supabase:** rodar contra o remoto (o `exportar` só lê) e ensaiar a restauração num projeto novo dependem de autorização.
