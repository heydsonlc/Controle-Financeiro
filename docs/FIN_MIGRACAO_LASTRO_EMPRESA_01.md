# FIN-MIGRACAO-LASTRO-EMPRESA-01 — Lastro e documentos da Empresa

**Situação (30/10/2026): Etapa 2 em produção, com correção autorizada.**
- Migration `20261202090000` aplicada e build publicado (§7).
- Correção da inferência de "Documento contábil" (migration `20261203090000`) e "Excluir documento" na Revisar, autorizados depois do teste real (§8).
- O documento real id 4 não é alterado por nenhuma etapa automática; o titular o revisa pela tela.

## 1. Conceitos (como o sistema funciona hoje)

| Termo | No banco | Significado |
|---|---|---|
| Documento fiscal / comprovante | `public.ir_comprovante` + `ir_comprovante_arquivo` (bytes) + `ir_comprovante_evento` | Arquivo enviado e seus dados (prestador, valor, texto extraído) |
| Metadados empresariais | `public.documento_empresarial_metadata` (1 por documento) | Tipo, categoria, número, órgão, emissão, validade, situação, obrigatório, renovável, alerta |
| Taxonomia documental | `financeiro.taxonomia_documental()` | 11 tipos, 55 categorias (cada uma com o seu tipo) e 11 situações |
| Lastro | Vínculo **ativo** em `public.ir_comprovante_vinculo` entre o documento e uma operação financeira do perfil | Comprovação documental de uma saída |
| Saída sem documento | `financeiro.saidas_lastro` | Conta a pagar, lançamento no cartão, despesa prevista ou débito avulso do ano, sem vínculo ativo |
| Pendência de lastro | `public.lastro_financeiro_pendencia` | Situação manual da saída sem documento (pendente, aguardando contador, não aplicável) |

**O que muda com este pacote:**
- *Documento empresarial geral* (societário, procuração, certidão, contrato, contábil) existe sem lastro e não é pendência financeira.
- *Documento que comprova operação financeira* (pagamento realizado, nota fiscal recebida ou emitida, guia paga) pede lastro (`financeiro.documento_exige_lastro`).

## 2. Causas exatas (documento real id 4, `Contrato_Social_e_Procuracao.pdf`)

| Sintoma | Causa |
|---|---|
| "Pagamento realizado / Pix pago" | **Não há metadados gravados** para o id 4, então `financeiro.metadata_empresarial_flask` (migration `20261113090000`, linhas 157–175, cópia de `_inferir_tipo_categoria` do Flask) infere na leitura. A ordem é fixa e o teste é por substring: natureza IR → "pix" → "boleto" → "contrato". O texto do PDF contém "pix" (1 vez), "boleto", "contrato" e "contrato social"; "pix" vence |
| "Sem lastro" | `resumo_documentos_empresa` (linhas 303–316) conta todo documento sem vínculo ativo, de qualquer tipo |
| Não dava para corrigir | A revisão da tela original grava os metadados por `PUT /comprovantes/<id>/metadata-empresarial`, mas o adaptador respondia 501 e o banco não tinha escrita |

## 3. Mudanças (sem tabela nova; nenhum dado existente alterado)

**Migration `20261202090000` (reversão em `supabase/reversao/20261202090000_lastro_empresa_anterior.sql`):**

- **Classificação automática segura** (`inferir_documento_empresa`):
  - palavras inteiras, sem acento;
  - documento-base vem antes de pagamento (contrato social, alteração contratual, cartão CNPJ, procuração, alvará, certidão);
  - pagamento só com sinal de transação ("comprovante", "transação", "pix enviado", "pago via pix", linha digitável...);
  - "contrato" genérico vira Contrato/instrumento, sem chutar a categoria;
  - sem evidência: **"Não classificado"**.
- **Sem lastro:** só conta documento financeiro (`documento_exige_lastro`). A tela usa o mesmo critério nas "Pendências de lastro".
- **Metadados empresariais:** `salvar_metadata_empresarial`, com as regras do Flask:
  - a taxonomia vem de lista fechada, e a categoria define o tipo;
  - textos são cortados no limite, e datas e booleanos normalizados;
  - a situação é recalculada pela validade.
- **Correções em relação ao Flask:**
  - campo ausente no pedido não apaga o gravado;
  - o evento registra antes → depois;
  - a operação guarda antes/depois, a conta e a hora (auditoria);
  - a chave evita gravar duas vezes.
- **Saídas sem documento:**
  - `vincular_saida_documento`: vínculo VALIDADO por padrão e pendência desativada. Correção: recusa vincular o mesmo documento duas vezes à mesma saída.
  - `marcar_status_saida`: situação manual; recusa saída que já tem documento.
- **CONTA × conta bancária:**
  - no vínculo pelo documento, "Conta bancária" passa a ser gravada como `CONTA_BANCARIA`;
  - antes era `CONTA`, o mesmo código da conta a pagar, e a leitura das saídas casa por tipo + id;
  - em produção não há vínculo nenhum para converter.
- **Exclusão:** `excluir_comprovante` também apaga os metadados (antes a exclusão quebraria por chave estrangeira depois da revisão).

**Tela (sem alterar o JS do Flask, salvo um defeito de texto):**
- Adaptador: rotas de metadados, de vincular saída e de situação da saída.
- Botão **Excluir documento** (ícone de lixeira, com `title` e `aria-label`) em cada linha da lista, só para quem gere o perfil:
  - pede confirmação;
  - a recusa aparece com o motivo;
  - lista e contadores são recarregados pela própria tela.
- `frontend/static/js/categorias.js`: "Sem descri&ccedil;&atilde;o cadastrada." e "Categoria global do cart&atilde;o" passavam por `escapeHtml`. O texto foi corrigido na origem; isso corrige também o Flask.

## 4. Testes

| Suíte | Cobertura |
|---|---|
| `tests/test_supabase_lastro_empresa.py` (14) | Classificação: contrato social com Pix, Pix, boleto, procuração, "pago via PIX", "pixel" e neutro. Inferir não grava; sem lastro só financeiro; checklist. Metadados: reclassificação, regras, evento, auditoria, repetição, campos preservados, recusas (Pessoal, outro perfil, outra conta, Flask). Saídas: situação, vincular, duplicado, desvincular, perfil alheio; `CONTA_BANCARIA`; exclusão com metadados e recusas; reversão |
| `tests/test_supabase_documentos_fiscais_leitura.py` | Comparação com o Flask. Divergência intencional registrada: "sem lastro" pelo critério novo |
| `web/tests/e2e/lastro_empresa.spec.mjs` (5) | Pela tela, conta C: classificação, "Sem lastro" e pendências; reclassificação pela revisão (evento); saídas (vincular, aguardando contador, desvincular); excluir pela lista (confirmação, contadores, recusa com motivo); arquivo recusado com mensagem |
| `web/tests/e2e/categorias_tela.spec.mjs` | "Sem descrição cadastrada." sem códigos HTML |

## 5. Pendências

- Em 1366 px, a coluna "Natureza sugerida" da tabela de saídas (tela original) cobre os botões de ação da linha; em 1600 px fica normal. Cosmético.
- `web/tests/e2e/lancamentos_tela.spec.mjs` falha às vezes na rodada completa, em passos diferentes, e passa isolado. É instabilidade do spec.
- Fora deste pacote: OCR de imagem, relatórios Excel/PDF/ZIP e categorias IR.

## 6. Ensaio da migration (cópia fiel e descartável da produção)

Cópia por fluxo `pg_dump → pg_restore` (sem arquivo) num PostgreSQL 18 local, apagado no fim; a produção só foi lida.

| Conferência | Resultado |
|---|---|
| Cópia × produção (linhas e md5 por tabela, funções, políticas, privilégios) | Idêntica |
| Dados existentes alterados pela migration | Nenhum; nenhuma tabela nova ou removida |
| Funções | 8 novas; 4 redefinidas (`metadata_empresarial_flask`, `resumo_documentos_empresa`, `excluir_comprovante`, `criar_vinculo_documento`) |
| Id 4, sugestão exibida | Antes "Pagamento realizado / Pix pago"; depois "Documento societário / Contrato Social", ainda `INFERIDO`, sem metadados gravados |
| Resumo da Empresa | "Sem lastro" 1 → 0; checklist "Contrato Social" pendente → ok |
| Ciclo fictício na cópia ("TESTE LASTRO EMPRESA") | Sugestão "Não classificado"; revisão grava Certidão federal (`USUARIO`), um evento; repetição pela chave marcada `repetida`; exclusão sem restos (arquivo, eventos, metadados, vínculos) |
| Reversão e reaplicação | Estrutura e funções iguais ao estado anterior; reaplicação igual à aplicação; dados preservados |

O ensaio aplica os arquivos byte a byte, como a CLI. A produção guarda o texto das funções com o fim de linha do arquivo aplicado (CRLF, salvo `excluir_comprovante`). Por isso as funções são comparadas sem o CR.

## 7. Etapa 2 em produção

- Commit `d5baca6`, push `c66db6e..d5baca6`.
- Migration `20261202090000` aplicada pelo script de aplicação única: dry-run só com ela, nenhum dado existente alterado, segurança sem bloqueios.
- Deploy `c5b6d2cd` (build de `git archive d5baca6`); os 165 arquivos servidos na URL de produção são iguais ao build.

**Teste real do titular (30/10/2026, documento fictício id 5 "TESTE LASTRO EMPRESA"):**
- Revisão e reclassificação gravadas (Certidão federal, `USUARIO`), com um evento por gravação.
- O titular não encontrou a lixeira da lista. Localmente ela aparece de 1024 a 1920 px, e a causa em produção segue em análise.
- O titular revisou o id 4 pela tela com a categoria de IR "Documento contábil" e o validou. A regra herdada do Flask (natureza `DOCUMENTO_CONTABIL` → Guia/taxa paga) voltou a sugerir pagamento: "sem lastro" voltou a 1 e o "Contrato Social" do checklist voltou a pendente.

## 8. Correção autorizada (migration `20261203090000`)

**Inferência** (só documento sem classificação gravada; a gravada prevalece sempre):
1. O conteúdo decide primeiro: documento societário/cadastral, procuração, alvará ou certidão claramente identificados.
2. Pagamento só com evidência de transação (comprovante, transação, Pix enviado/pago, linha digitável, boleto pago...). Se a categoria de IR for imposto/taxa, vira Guia/taxa paga.
3. Sem nada disso, a categoria de IR:
   - "Documento contábil" ou "Imposto/taxa" → **Contábil/fiscal / Não classificado**, fora do "sem lastro";
   - patrimônio, despesa e nota fiscal seguem o Flask.
4. Contrato genérico → Contrato/instrumento; sem evidência → Não classificado.

Categoria inferida sem categoria aparece como "Não classificado" em qualquer tipo. Só redefine `inferir_documento_empresa` e `metadata_empresarial_flask`; nenhum dado é alterado. A reversão (`supabase/reversao/20261203090000_inferencia_documento_contabil_anterior.sql`) devolve o texto exato da `20261202090000`.

**Tela:** botão **Excluir documento** também no rodapé da Revisar, à esquerda das ações. Usa a mesma rota oficial e a mesma confirmação da lixeira; a recusa mostra o motivo e mantém a revisão aberta, e a exclusão fecha a revisão e atualiza a lista.

**Testes:** `tests/test_supabase_lastro_empresa.py` ganhou:
- 8 casos de conteúdo × categoria de IR;
- "sem lastro" sem contábil nem societário;
- classificação gravada prevalece;
- reversão da correção.

`web/tests/e2e/lastro_empresa.spec.mjs` ganhou "excluir pela revisão" (cancelar, recusa com motivo, exclusão).

**Regressão:** integração Python 442 aprovados (0 falhas), telas 113/113, unitários 30/30.

**Ensaio numa cópia fiel e descartável da produção:**

| Conferência | Resultado |
|---|---|
| Cópia × produção | Idêntica |
| Dados e sequências | Nenhuma alteração; nenhuma tabela nova ou removida |
| Funções | Só `inferir_documento_empresa` e `metadata_empresarial_flask` |
| Id 4 (sem classificação gravada) | Antes "Contábil / fiscal / Guia/taxa paga"; depois "Documento societário / Contrato Social", ainda `INFERIDO`, sem metadados gravados |
| Id 5 (classificação gravada) | Inalterado (Certidão federal, `USUARIO`) |
| Resumo | "Sem lastro" 1 → 0; checklist "Contrato Social" pendente → ok |
| Reversão / reaplicação | Volta exatamente ao estado anterior / igual à aplicação |
