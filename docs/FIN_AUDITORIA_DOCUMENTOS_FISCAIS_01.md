# FIN-AUDITORIA-PUBLICACAO-MIGRACAO-01 — C. Documentos Fiscais

**Data de referência:** 15/11/2026. **Natureza:** somente leitura. Nenhum documento foi criado, alterado, excluído, aberto ou baixado.

**Abreviações**
- **ADP** = `web/src/js/documentos-fiscais-adaptador.js`
- **DF** = `web/src/js/documento-financeiro.js`
- **AC** = `web/src/js/arquivo-comprovante.js`
- **M1113** = migration `20261113090000`, e assim por diante (M1117, M1118, M1126, M1128, M1130, M1202, M1203)
- **Flask** = `backend/routes/ir.py` e serviços em `backend/services/`

## 1. Situação geral

- **Banco.** As cinco migrations citadas no contrato (M1113, M1128, M1130, M1202, M1203) e as auxiliares (M1117, M1118) **estão aplicadas na produção e idênticas ao repositório**. As 43 funções de documentos da produção têm a mesma impressão digital das geradas pelo repositório (`FIN_AUDITORIA_INFRAESTRUTURA_01.md`, seção 2). **Nada a reaplicar.**
- **Publicação.** A tela `documentos-fiscais.html`, o adaptador e os módulos auxiliares estão no deploy `45e24f88`, idênticos ao build.
- **Uso real na produção** (contagens, sem conteúdo):
  - 2 documentos, ambos do perfil Empresa, com arquivo (1,6 MB): 1 `VALIDADO` e 1 `PENDENTE_REVISAO`;
  - 1 registro de metadados empresariais;
  - 12 eventos e 5 operações idempotentes registradas;
  - **0 vínculos** e 0 pendências de lastro;
  - 0 documentos de financiamento.
- **Resultado das 30 operações:**

| Classificação | Quantidade |
|---|---|
| CONCLUÍDO | 9 |
| PUBLICADO NÃO HOMOLOGADO | 12 |
| PARCIAL | 3 |
| NÃO MIGRADO | 6 |

Não há item em DESENVOLVIDO NÃO PUBLICADO, MIGRATION PENDENTE ou DIVERGENTE.

**Critério usado**
- **CONCLUÍDO:** publicado, com teste automatizado e com uso real comprovado na produção.
- **PUBLICADO NÃO HOMOLOGADO:** publicado e testado, mas sem registro de uso real ou de homologação do titular.

## 2. Matriz das 30 operações

| # | Operação | Flask | Aplicativo novo (rota → função) | Testes | Classificação | Pendência |
|---|---|---|---|---|---|---|
| 1 | Consulta de documentos | `ir.py:107,150` | `GET /api/ir/comprovantes` → `ir_comprovantes_tela` (ADP:271-272; M1113:466) | `test_supabase_documentos_fiscais_leitura.py`; e2e `documentos_fiscais_tela` | CONCLUÍDO | — |
| 2 | Cadastro e envio | `ir.py:223` | `POST /comprovantes/upload` → `enviar_comprovante`, um arquivo por chamada (ADP:278; M1128:119) | `test_supabase_documentos_escrita.py::test_validacoes_do_arquivo_e_duplicidade_por_perfil` | CONCLUÍDO | — |
| 3 | Armazenamento | bytea no banco (`models.py:528-539`) | a mesma tabela, `ir_comprovante_arquivo.conteudo` (M1128:180-181); sem bucket | idem | CONCLUÍDO | Ver seção 4 |
| 4 | Abertura e download | `ir.py:299` | link interceptado → `arquivo_comprovante_tela` → abre em nova aba (AC:30-65; M1118:15) | `test_supabase_arquivo_comprovante.py` | CONCLUÍDO | — |
| 5 | Revisão | `ir.py:240` | `PUT /comprovantes/<id>` → `atualizar_comprovante` (ADP:282; M1128:201) | `test_mesmas_linhas_que_o_flask` | CONCLUÍDO | — |
| 6 | Validação | `ir.py:251` | `POST …/validar` → `validar_comprovante` (ADP:284; M1128:267) | idem; sem e2e específico | CONCLUÍDO | Sem e2e próprio |
| 7 | Exclusão segura | não existe | `DELETE /comprovantes/<id>` → `excluir_comprovante` (ADP:283; M1202:398); recusa com vínculo ou validado | `test_exclusao_segura`; e2e `lastro_empresa` | PUBLICADO NÃO HOMOLOGADO | A exclusão é física e apaga também os eventos: não sobra trilha |
| 8 | Vínculos com despesas | `documento_fiscal_service.py:77-122` | `POST/PUT/DELETE …/vinculos` → `criar_/atualizar_/remover_vinculo_documento` (ADP:285-289) | `test_mesmas_linhas_que_o_flask` | PUBLICADO NÃO HOMOLOGADO | 0 vínculos reais |
| 9 | Vínculos com patrimônio | `routes/patrimonio.py:146-193` | `patrimonio-adaptador.js:179-185` → `vincular_documento_bem`, `criar_bem_de_documento` (M1130:341,384) | `test_supabase_documentos_tela.py`; e2e `documentos_financeiro_tela` | PUBLICADO NÃO HOMOLOGADO | 0 bens reais |
| 10 | Vínculos com financiamentos | vínculo genérico + módulo próprio de arquivos em disco e conferências da Caixa (`routes/financiamentos.py:492-680`) | o vínculo genérico funciona (M1128:355); as rotas `/api/financiamentos/<id>/documentos*` e `conferencias-caixa*` respondem 501 (`financiamentos-adaptador.js:16,144`) | `test_documento_vinculado_a_financiamento_do_perfil` | **PARCIAL** | Faltam envio, download e exclusão dos documentos do contrato e as conferências da Caixa |
| 11 | Documentos da Empresa | `ir.py:163-177` | `ir_documentos_empresa_tela` (ADP:273-275; M1113:352) | e2e "perfil Empresa: documentos da empresa…" | CONCLUÍDO | Exceto o ZIP (#28) |
| 12 | Metadados empresariais | `ir.py:196-220` | `PUT …/metadata-empresarial` → `salvar_metadata_empresarial` (ADP:279; M1202:297) | `test_supabase_lastro_empresa.py` | CONCLUÍDO | — |
| 13 | Checklist documental | 4 itens fixos (`documento_empresarial_service.py:265-316`) | dentro do resumo (M1202:191-256) | `test_supabase_documentos_fiscais_leitura.py` | PUBLICADO NÃO HOMOLOGADO | — |
| 14 | Validade de documentos | `documento_empresarial_service.py:345-359` | `data_validade` nos metadados; situação calculada na leitura (M1202:135-141) | `test_reclassificar_e_editar_metadados_com_auditoria` | PUBLICADO NÃO HOMOLOGADO | — |
| 15 | Alertas de vencimento | KPI "vencendo em 30 dias" e dashboard | o mesmo KPI e a lista de próximos vencimentos (M1202:220-254; dashboard M1114:248) | `test_supabase_dashboard_leitura.py` | PUBLICADO NÃO HOMOLOGADO | Igual ao Flask: 30 dias fixos (`alerta_dias_antes` é gravado e não usado); sem notificação externa |
| 16 | Saídas sem documento | `ir.py:370-385` | `GET /lastro/saidas-sem-documento` → `lastro_saidas_tela` (ADP:276-277; M1117:157) | `test_supabase_lastro_saidas_leitura.py` | PUBLICADO NÃO HOMOLOGADO | — |
| 17 | Ausência de lastro | resumo empresarial | `lastro_resumo_tela` (ADP:290; M1130:122); critério corrigido: só documento financeiro (M1202:26-34) | `test_sem_lastro_so_para_documento_financeiro` | PUBLICADO NÃO HOMOLOGADO | — |
| 18 | Vincular documento à saída | `ir.py:388-413` | `POST …/vincular` e `…/status` → `vincular_saida_documento`, `marcar_status_saida` (ADP:280-281; M1202:499-599) | e2e "saidas sem documento: vincular…" | PUBLICADO NÃO HOMOLOGADO | — |
| 19 | Classificação documental | por palavra-chave no envio (status `CLASSIFICADO`) + inferência empresarial | inferência empresarial na leitura (M1203:9) e classificação manual | `test_classificacao_automatica_segura` | **PARCIAL** | O envio não classifica Categoria de Despesa/IR nem gera `CLASSIFICADO` (M1128:184-194) |
| 20 | Despesa a partir de documento | `ir.py:274-296` | `sugestao_financeira_documento_tela` e `criar_financeiro_documento` (DF:51-68; M1128:479) | e2e "Gerar financeiro…" | PUBLICADO NÃO HOMOLOGADO | — |
| 21 | Lançamento a partir de documento | mesmo serviço | DF em Lançamentos (`lancamentos-adaptador.js:291`); cartão via `criar_compra` | idem | PUBLICADO NÃO HOMOLOGADO | — |
| 22 | Extração de texto de PDF | pdfplumber no servidor | PDF.js no navegador (ADP:68-91); guarda o texto se tiver ≥ 50 caracteres | `test_texto_de_pdf_e_revisao_manual_sem_ocr` | PUBLICADO NÃO HOMOLOGADO | Só guarda o texto; não extrai campos |
| 23 | Reconhecimento de NFS-e | `ir_nfse_goiania_parser.py` (só Goiânia) | não existe | só no Flask | **NÃO MIGRADO** | Implementar no navegador ou no banco |
| 24 | Reconhecimento de cupom fiscal | `cupom_fiscal_parser.py` | não existe (o banco só lê o evento antigo) | só no Flask | **NÃO MIGRADO** | Idem |
| 25 | OCR de imagem e PDF digitalizado | Tesseract + Poppler (`ocr_service.py`) | botão "Reprocessar OCR" → 501 (ADP:308) | — | **NÃO MIGRADO** (interface sem serviço) | Exige serviço que rode OCR, ou OCR no navegador |
| 26 | Relatórios de IR (Excel/PDF) | `ir.py:448-481` | botões interceptados com aviso (ADP:467) | e2e "…relatorio recusado sem navegar" | **NÃO MIGRADO** (interface sem serviço) | Gerar no navegador, como o relatório do Patrimônio |
| 27 | Relatórios de lastro (Excel/PDF) | `ir.py:416-445` | botões → 501 | — | **NÃO MIGRADO** (interface sem serviço) | Idem |
| 28 | ZIP de documentos da Empresa | `documento_zip_service.py`; `ir.py:180` | botão → 501 | — | **NÃO MIGRADO** (interface sem serviço) | Gerar o ZIP no navegador |
| 29 | Controle de acesso entre perfis | filtros por perfil | todas as funções conferem `pode_acessar_perfil`; escrita por `exigir_escrita_novo`; Empresa por `exigir_documentos_empresa` | `test_escritor_unico_e_isolamento`, `test_isolamento_entre_perfis`; e2e "outro titular nao ve…" | CONCLUÍDO | Conferido na produção (seção 3) |
| 30 | Integridade dos arquivos | SHA-256 gravado, não reconferido | SHA-256 gravado (M1128:169); `arquivo_comprovante_tela` não reconfere | sem teste de reconferência | **PARCIAL** | Reconferir o hash ao abrir ou em rotina |

**Mensagens exibidas hoje**
- Itens 25, 27 e 28: "Documentos fiscais: esta ação (OCR de imagem, categorias IR ou relatórios) ainda não está disponível nesta versão do aplicativo. Nada foi gravado."
- Item 26: "Relatório de documentos fiscais (Excel/PDF): ainda não está disponível nesta versão do aplicativo. Nada foi gravado."
- A própria tela avisa: "OCR de imagem e relatórios ainda não estão disponíveis nesta versão" (`web/src/paginas/documentos-fiscais.html:59`).

## 3. Atenção especial (5.3 do contrato)

| Situação | Itens |
|---|---|
| Só no Flask | NFS-e (23), cupom fiscal (24), OCR (25), relatórios de IR (26) e de lastro (27), ZIP (28), documentos de financiamento e conferências da Caixa (10) |
| Aparece na tela e responde "não disponível" | Reprocessar OCR; Excel e PDF de IR; Excel e PDF de saídas sem documento; ZIP da Empresa |
| Já desabilitado no próprio Flask | "ZIP para contador" das saídas (`frontend/templates/imposto_renda.html:122`): não existia |
| Função no banco sem interface | Nenhuma: as RPCs de documentos expostas a `authenticated` na produção (24 com nome de documento, comprovante, lastro ou IR, mais `marcar_status_saida` e `entidades_vinculaveis_tela`) têm rota no ADP, no DF ou no adaptador do Patrimônio |
| Interface sem serviço | As 6 ações acima; em Financiamentos, documentos e conferências |
| Testado localmente e não publicado | Nada: o repositório e o deploy coincidem |
| Publicado sem teste suficiente | Validação (6) sem e2e próprio; reconferência de hash (30) sem teste |

**Rotas do Flask sem uso pela tela.** `POST /api/ir/categorias` e `POST`/`DELETE /api/ir/categorias-despesa` não são chamadas pela tela original. Classificação: FORA DO ESCOPO.

## 4. Armazenamento (5.4 do contrato)

| Ponto | Situação | Evidência |
|---|---|---|
| Local | No banco, coluna bytea `public.ir_comprovante_arquivo.conteudo`. **Não há bucket do Supabase Storage** (0 buckets na produção) | M1128:180-181; consulta a `storage.buckets` |
| Integridade | SHA-256 gravado em `hash_arquivo`; não é reconferido na leitura | M1128:169; M1118:31-36 |
| Limite de tamanho | 10 MB por arquivo | M1128:158 |
| Formatos | pdf, png, jpg/jpeg, webp, com conferência do MIME e da assinatura do arquivo | M1128:148-168 |
| Duplicidade | Recusada por SHA-256 dentro do perfil; não há índice único, mas o envio é serializado por perfil | M1128:169-176; migration `20261124090000`:31 |
| Isolamento por perfil | Pelo campo `perfil_financeiro_id` da linha e pelas funções. A tabela tem RLS ligada e nenhum privilégio para `anon` ou `authenticated` | consulta de privilégios na produção |
| Exclusão | Física: apaga metadados, eventos, arquivo e comprovante. Recusa documento com vínculo ou validado | M1202:398-423 |
| Backup | Entra no dump do banco, e `scripts/backup_banco.py` gera um arquivo separado só dos documentos. **Não há backup real comprovado** | `backup_banco.py:36,225-226`; `FIN_AUDITORIA_INFRAESTRUTURA_01.md`, seção 8 |

**Risco de escala.** Guardar arquivos no banco funciona para o volume atual (1,6 MB num banco de 25 MB). Se o volume crescer, pesa no tamanho do banco e nos backups. O `ROADMAP` já previa storage externo (`FIN-DOC-FIN-4`, prioridade baixa).

## 5. Conclusão do módulo

O núcleo documental (consultar, enviar, guardar, abrir, revisar, validar, metadados, lastro, vínculos, gerar financeiro) está **migrado, aplicado e publicado**, sem nenhuma dependência do Flask em funcionamento.

Faltam três grupos, todos atendidos antes pelo servidor Flask:
1. **Relatórios e exportações:** Excel e PDF de IR, Excel e PDF de lastro, ZIP da Empresa.
2. **Leitura automática:** OCR, NFS-e, cupom fiscal e classificação no envio.
3. **Documentos do financiamento** e conferências da Caixa.

O que falta homologar é o uso real de vínculos, lastro e "Gerar financeiro": hoje há 0 vínculos na produção.
