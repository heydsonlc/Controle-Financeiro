# FIN-FIDELIDADE-DOCUMENTOS-1 (MVP 5) — Documentos Fiscais e "A partir de documento"

**Situação (25/10/2026):** fase 1 (Imposto de Renda, modo IRPF, só consulta) implementada e testada localmente.
- Sem commit, sem migration persistente e sem publicação. A migration `20261113090000` é local.

## 1. Tamanho e divisão

| Parte no Flask | Linhas |
|---|---|
| `routes/ir.py` (37 rotas) | — |
| `ir_documento_service.py` (categorias, comprovantes, upload, OCR, NFS-e de Goiânia, cupom fiscal) | 904 |
| `documento_empresarial_service.py` (modo Documentos da Empresa: taxonomia, metadados, filtros, ZIP) | 529 |
| `lastro_financeiro_service.py` (saídas sem documento: despesas, faturas e movimentos sem lastro) | 582 |
| `imposto_renda.js` / `.html` | 2069 / 762 |

Fases:
1. **IRPF, consulta (feita).**
2. **Arquivos:** download do arquivo (bytea no banco) e envio com leitura.
   - O OCR do Flask usa Tesseract e Poppler no servidor.
   - No novo aplicativo, a leitura de PDF com texto pode usar o PDF.js já incluído no MVP 1.
   - Imagem e PDF escaneado exigem decisão (serviço de OCR ou manter no Flask).
3. **Documentos da Empresa:** taxonomia, metadados e resumo empresarial, além de saídas sem documento.
4. **Escrita:** edição, validação, vínculos, categorias e "A partir de documento".

## 2. Fase 1 — o que foi feito

- **Migration `20261113090000_financeiro_documentos_fiscais_leitura.sql`:** só funções de leitura.
  - `ir_contexto_tela`: `GET /api/ir/contexto` (perfil, modo IRPF, títulos, categorias).
  - `ir_categorias_tela`: `GET /categorias`. Ativas do tipo do perfil ou AMBOS, por ordem e nome.
  - `ir_categorias_despesa_tela(perfil, disponiveis)`:
    - `GET /categorias-despesa`: vínculos categoria de despesa → categoria IR;
    - `GET /categorias-despesa-disponiveis`: `Categoria.to_dict` com a categoria IR vinculada.
  - `ir_comprovantes_tela(perfil, filtros, id)`:
    - `GET /comprovantes`, com filtros ano, status, categoria_ir_id e busca;
    - resumo com lastro e totais por categoria IR;
    - `GET /comprovantes/<id>`, com texto extraído e eventos.
  - Perfil Empresa: responde "Documentos da Empresa: em migração" (o modo empresarial é a fase 3).
- **Diferença deliberada (leitura que grava, no Flask):**
  - `GET /api/ir/categorias` e `/contexto` **criam** as categorias IR iniciais (`garantir_categorias_ir_iniciais` e `garantir_categorias_fiscais_empresa`) e fazem commit.
  - Aqui a leitura nunca grava: lê as categorias que existem.
  - Antes de publicar, conferir no Supabase de teste se as categorias IR já existem (o Flask as cria no primeiro acesso). Se faltarem, a semeadura deve ser uma migration de dados autorizada, com as listas `CATEGORIAS_IR_INICIAIS` / `CATEGORIAS_EMPRESA_INICIAIS`.
- **Tela original** (`web/src/paginas/documentos-fiscais.html`, gerada do template): `url_for` trocado por `/static/img/...` e aviso da fase. Os ícones `documento_pdf.png` e `documento_zip.webp` (versionados) foram incluídos no build.
- **Adaptador** (`web/src/js/documentos-fiscais-adaptador.js`):
  - rotas GET acima;
  - saídas sem documento respondem "em migração". No modo IRPF o Flask não as pede;
  - qualquer outra ação responde, sem gravar: "Esta ação continua no sistema atual".

## 3. Testes

- **Fidelidade** (`tests/test_supabase_documentos_fiscais_leitura.py`, **4 passaram**):
  - Comprovantes fictícios no cluster descartável: com arquivo, 2 eventos, vínculo de lastro aguardando contador, não dedutível, sem data e sem valor.
  - O **próprio Flask** semeia as categorias e cria um vínculo de categoria pela API.
  - O resultado do Flask é comparado **campo a campo**: contexto, categorias, vínculos, disponíveis, lista com resumo, 5 combinações de filtros e detalhes.
  - Também cobertos:
    - privilégios;
    - Empresa "em migração";
    - isolamento entre titulares;
    - "nada gravado": a contagem de categorias IR não muda na leitura nova.
- **E2E** (`web/tests/e2e/documentos_fiscais_tela.spec.mjs`, **2 passaram**):
  - comprovantes do Perfil B na tela, sem avisos;
  - edição recusada sem gravar;
  - outro titular não vê.
- **`moldura.spec.mjs`:** Documentos Fiscais saiu de "Em migração". Unitários: 30 passaram.

## 4. "A partir de documento"

- No Flask há 3 caminhos:
  - `/api/patrimonio/bens/criar-a-partir-documento` e `/bens/sugestao-a-partir-documento/<id>`;
  - `/api/ir/comprovantes/<id>/sugestao-financeira`;
  - `/comprovantes/documentos-para-financeiro` (despesa ou lançamento a partir do comprovante).
- Todos gravam ou dependem de vínculos.
- Ficam na fase 4. Exigem o escritor único decidido para Patrimônio e Despesas (`docs/FIN_FIDELIDADE_CONTRATOS_1.md` §6).

## 5. Arquivos

**Novos:**
- `supabase/migrations/20261113090000_financeiro_documentos_fiscais_leitura.sql`
- `tests/test_supabase_documentos_fiscais_leitura.py`
- `web/src/paginas/documentos-fiscais.html`
- `web/src/js/documentos-fiscais-adaptador.js`
- `web/src/css/documentos-fiscais-adaptacoes.css`
- `web/tests/e2e/documentos_fiscais_tela.spec.mjs`

**Alterados:**
- `web/scripts/build.mjs`
- `web/src/moldura/em-migracao.json`
- `web/tests/unit/build.test.mjs`
- `web/tests/e2e/moldura.spec.mjs`
- `web/tests/e2e/run_e2e.py`
- `tests/supabase_local.py`: `semear_documentos_fiscais_e2e`

## 6. Pendências e autorizações

1. Commit da fase 1.
2. Aplicação da migration `20261113090000` no Supabase de teste. Depende de `20261112090000` (função `iso_python`).
3. Conferência somente leitura das categorias IR no Supabase de teste (§2).
4. Decisão sobre OCR de imagens e PDFs escaneados (fase 2).
5. Escrita e "A partir de documento": dependem do escritor único (§4).

## 7. Documentos da Empresa e saídas sem documento (feitos): consulta

- **Migration `20261113090000`, estendida, ainda local e não aplicada:** o perfil Empresa deixou de responder "em migração".
  - `tipo_perfil_ir` substitui `exigir_modo_irpf`.
  - `ir_contexto_tela`: modo `DOCUMENTOS_FISCAIS_EMPRESA`, título, subtítulo e taxonomia.
  - `ir_comprovantes_tela`, no perfil Empresa:
    - filtros empresariais (tipo, categoria, status, obrigatório, validade) sobre os metadados **persistidos**, como o Flask;
    - cada documento enriquecido com os metadados (`enriquecer_comprovante_dict`);
    - resumo com `documentos_empresa`.
  - `ir_documentos_empresa_tela(perfil, recurso, filtros, id)`:
    - `GET /documentos-empresa/taxonomia`: as constantes do Flask, copiadas literalmente;
    - `GET /documentos-empresa/resumo`: totais, distribuição por tipo, próximos vencimentos e checklist societário;
    - `GET /comprovantes/<id>/metadata-empresarial`.
  - Metadados persistidos ou **inferidos**, como no Flask: pela natureza da categoria IR, depois por "pix", "boleto" ou "contrato" no texto. O status é recalculado pela validade (vencido, vencendo em até 30 dias, válido).
- **Migration `20261117090000_financeiro_lastro_saidas_leitura.sql`:** `lastro_saidas_tela(perfil, filtros, resumo)`.
  - `GET /api/ir/lastro/saidas-sem-documento` e `/resumo`, só no perfil Empresa (403 como o Flask).
  - Fontes: despesas previstas, contas (sem faturas), lançamentos no cartão e débitos avulsos (transferência interna fica de fora).
  - Cada saída leva o vínculo de documento mais recente ou a pendência ativa mais recente, e a natureza sugerida.
  - Filtros: período, origem, natureza, busca sem acento, valor mínimo e status.
  - Resumo por origem e por natureza.
- **Achado do Flask D-DOC1 (corrigido):**
  - Um documento com validade, sem prestador e sem arquivo faz o resumo empresarial **e a lista de comprovantes** do perfil Empresa quebrarem (`AttributeError: 'NoneType' object has no attribute 'get'`, 500).
  - O novo usa "Documento #id", o mesmo texto que o Flask já usa em `documento_label`.
- **Tela:**
  - aviso da fase atualizado;
  - no perfil Empresa a tela carrega tudo sem avisos;
  - marcar status, vincular, editar metadados, exportar ZIP e relatórios respondem "continua no sistema atual", sem gravar.
- **Testes:**
  - `tests/test_supabase_documentos_fiscais_leitura.py`, **7 passaram**: 4 IRPF e 3 Empresa.
    - Contexto, categorias, lista, 9 filtros empresariais e detalhes, inclusive o documento inferido como Pix.
    - Taxonomia, resumo com 4 filtros, checklist, metadados e o não encontrado.
    - D-DOC1 numa cópia descartável à parte: o Flask quebra, o novo responde.
  - `tests/test_supabase_lastro_saidas_leitura.py`, **3 passaram**.
    - Saídas fictícias em todas as origens, com documento vinculado, pendências e transferência interna.
    - **14 combinações de filtros**, lista e resumo comparados com o Flask.
    - Também cobertos: 403 fora do perfil Empresa e isolamento.
  - `documentos_fiscais_tela.spec.mjs`, **3 passaram**: perfil Empresa com o documento fictício e checklist, sem avisos.

## 8. "Abrir arquivo" (feito): leitura

- **Migration `20261118090000_financeiro_arquivo_comprovante_leitura.sql`:** `arquivo_comprovante_tela(perfil, id)`.
  - Equivale a `GET /api/ir/comprovantes/<id>/arquivo`, com as regras de `obter_arquivo`: comprovante do perfil, "Comprovante nao encontrado" e "Arquivo do comprovante nao encontrado".
  - O conteúdo (bytea) vai em base64.
- **No navegador** (`web/src/js/arquivo-comprovante.js`):
  - No Flask, "Abrir arquivo" é um link comum, ou `window.open` em Patrimônio, para uma rota que serve o arquivo. Aqui não há servidor `/api/`.
  - O link e o `window.open` são interceptados.
  - A nova aba abre ainda no clique, para não ser barrada como pop-up, e recebe o arquivo do Supabase como blob.
  - Vale em Imposto de Renda (lista, revisão, detalhe) e no documento vinculado ao bem, em Patrimônio.
- **Relatório Excel/PDF do IR:**
  - No Flask, os botões navegam para `/api/ir/relatorios/...`. Aqui isso abriria uma página inexistente.
  - Os botões avisam que o relatório continua no sistema atual e a página não sai do lugar.
  - Gerar os relatórios (Excel/PDF/ZIP) fica para a fase de relatórios.
- **Testes:**
  - `tests/test_supabase_arquivo_comprovante.py`, **3 passaram**: PDF e imagem com bytes arbitrários, idênticos aos servidos pelo Flask, erros iguais, isolamento.
  - `documentos_fiscais_tela.spec.mjs`, **4 passaram**: abrir arquivo abre a nova aba com o conteúdo e o relatório é recusado sem navegar. `patrimonio_tela.spec.mjs` continua passando.
