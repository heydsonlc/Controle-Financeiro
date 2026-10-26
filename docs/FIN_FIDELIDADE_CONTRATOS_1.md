# FIN-FIDELIDADE-CONTRATOS-1 (MVP 3) — Financiamentos e Consórcios

**Situação (25/10/2026):** fase 1 (Financiamentos, só consulta) implementada e testada localmente.
- Fases 2 e 3 (gravar contratos e parcelas) bloqueadas pelo escritor único: o Flask continua escrevendo parcelas mesmo em perfil do novo aplicativo (§6).
- Sem commit, sem migration persistente e sem publicação.
- A migration `20261110090000` é local.

## 1. Tamanho e divisão

| Parte no Flask | Linhas |
|---|---|
| `financiamento_service.py` (motor: SAC, PRICE, SAC/TR da Caixa, seguros MIP/DFI por faixa de idade, indexadores TR/IPCA, amortização extra, ajuste de saldo, regeneração de cronograma) | 3033 |
| `routes/financiamentos.py` (26 rotas) | 1553 |
| conferência e documentos (`financiamento_conferencia_service.py`, `financiamento_documento_service.py`) | 849 |
| `financiamentos.js` / `.html` / `.css` | 2196 / 846 / 1735 |
| `routes/consorcios.py` (a tela fica dentro de Despesas) | 735 |

Portar o motor exige comparar cada cálculo com o próprio Flask nos mesmos dados (como no gerador de recorrências). Por isso a migração vai por fases:

1. **Fase 1 (feita): consulta.** Lista, detalhe e parcelas no formato do Flask. Nada é gravado: o Flask continua o escritor único dos contratos.
2. **Fase 2: pagamento e estorno de parcela**, pelo motor de movimentos do MVP 2 (débito na conta, estorno ligado), com o escritor único por perfil.
3. **Fase 3: motor de cálculo** (criação, edição, regeneração, amortização extra, ajuste de saldo, seguros e indexadores), comparado com o Flask contrato a contrato.
4. **Fase 4: documentos e conferência Caixa** (arquivos: dependem do armazenamento, ainda não definido) e **Consórcios** (rotas `/api/consorcios`, hoje "em migração" dentro de Despesas).

## 2. Fase 1 — o que foi feito

- **Migration `20261110090000_financeiro_financiamentos_leitura.sql`:** só funções de leitura.
  - `financiamentos_tela(perfil, ativo)`: `GET /api/financiamentos[?ativo=]`, na ordem do Flask (data do contrato, mais recente primeiro).
  - `financiamento_tela(perfil, id)`: `GET /api/financiamentos/<id>`, com parcelas e `vigencia_seguro_info`.
  - Reproduzem `Financiamento.to_dict` e `FinanciamentoParcela.to_dict`:
    - saldo devedor atual (o gravado; sem ele, o saldo após a parcela anterior à primeira pendente);
    - padrões do `to_dict` e zero virando nulo onde o Flask faz isso;
    - faixas MIP e último ajuste de saldo;
    - contagem de parcelas pagas.
- **Tela original** (`web/src/paginas/financiamentos.html`): os dois laços do Jinja (meses e dias) foram expandidos sem mudar o resultado.
  - Foi acrescentado um aviso da fase: "cadastro, edição, pagamento… continuam no sistema atual nesta fase".
- **Adaptador** (`web/src/js/financiamentos-adaptador.js`): lista, detalhe e contas bancárias.
  - Qualquer outra ação responde, sem gravar: "Esta ação continua no sistema atual".

## 3. Testes

- **Fidelidade** (`tests/test_supabase_financiamentos_leitura.py`, **4 passaram**):
  - O **próprio Flask** cria, no cluster descartável, dois financiamentos fictícios (SAC e PRICE, seguro fixo com vigência, taxa de administração) e faz uma amortização extraordinária.
  - Depois, a lista (todas e só ativas) e o detalhe do Flask são comparados **campo a campo** com as funções novas: parcelas, saldos, seguro e sugestão de vigência.
  - Também cobertos: privilégios, isolamento entre titulares e "nada gravado".
- **E2E** (`web/tests/e2e/financiamentos_tela.spec.mjs`, **2 passaram**):
  - lista, detalhe e 3 parcelas (1 paga) do financiamento fictício do Perfil B (`semear_financiamento_e2e`);
  - ação fora da fase recusada sem gravar;
  - outro titular não vê o contrato.
- **`moldura.spec.mjs`:** Financiamentos saiu de "Em migração". Unitários: 30 passaram.
- **Suíte completa `tests/` (regressão, 25/10/2026):** 7 falhas, nenhuma nos arquivos deste MVP nem nos dos MVPs 1–2.
  - `test_testes_impacto.py` (2): esperam `cartoes.spec.mjs` e `fechamento.spec.mjs`, removidos no commit ef6c0d8 (CARTOES-1, já no repositório).
    - **Corrigido depois:** `scripts/testes_impacto.py` passou a ler as páginas da moldura (`web/src/paginas`) e a mapear os arquivos do Flask reaproveitados (`frontend/static/js|css`, `frontend/templates`).
    - O teste usa os specs atuais e ganhou um caso novo. **14 passaram.**
  - `test_ocr_tools.py` (2): a máquina tem o Poppler instalado e o teste espera que ele falte (ambiente).
  - `test_categorias_sistemicas_mobilidade.py`, `test_veiculos_mobilidade_2b.py`, `test_receitas_ux.py` (3): testes do Flask sobre código não alterado, já registrados como preexistentes (P7 de `docs/DEPLOY_READY_FIN_1.md`). Os dois de OCR também estão lá.

## 4. Arquivos

**Novos:**
- `supabase/migrations/20261110090000_financeiro_financiamentos_leitura.sql`
- `tests/test_supabase_financiamentos_leitura.py`
- `web/src/paginas/financiamentos.html`
- `web/src/js/financiamentos-adaptador.js`
- `web/src/css/financiamentos-adaptacoes.css`
- `web/tests/e2e/financiamentos_tela.spec.mjs`

**Alterados:**
- `web/scripts/build.mjs`
- `web/src/moldura/em-migracao.json`
- `web/tests/unit/build.test.mjs`
- `web/tests/e2e/moldura.spec.mjs`
- `web/tests/e2e/run_e2e.py`
- `tests/supabase_local.py`: financiamento fictício do E2E

## 5. Pendências e autorizações

1. Commit da fase 1.
2. Aplicação da migration `20261110090000` no Supabase de teste. Ela só cria funções de leitura.
3. Publicação na prévia: só consulta, com o aviso na tela.
4. **Fase 2: BLOQUEADA, depende de autorização para alterar o Flask.** Detalhes no §6.

## 6. Fase 2 (pagamento e estorno de parcela): bloqueio do escritor único

**O que a análise do Flask mostrou:**
- Todo financiamento criado pelo Flask ganha um item de despesa e uma despesa (`Conta`) por parcela (`criar_financiamento`: "1 parcela = 1 Conta = 1 linha em DESPESAS").
  - Por isso a rota direta `/parcelas/<id>/pagar` recusa ("Use o fluxo de Despesas").
  - O pagamento real é feito em Despesas: débito DESPESA mais `registrar_pagamento_parcela`.
  - A rota direta só serve a contratos antigos, sem despesas.
- **O Flask continua escritor das parcelas mesmo em perfil do novo aplicativo:**
  - `_paga_pelo_novo_aplicativo` (`routes/despesas.py`) devolve falso para consórcio e financiamento;
  - as rotas de `routes/financiamentos.py` não consultam `gerador_recorrencia`.
  - Se o novo aplicativo também pagasse, haveria **dois escritores**. O Flask não trava a parcela, então poderia haver débito em dobro.
- **Defeitos do Flask encontrados (para classificar):**
  - D1: o estorno pela tela de Despesas devolve a despesa a "Pendente", mas não reabre a parcela, que fica "pago", com saldo devedor reduzido.
  - D2: o estorno direto procura estorno anterior pela parcela. Depois de pagar, estornar e pagar de novo, o segundo estorno fica bloqueado para sempre.
  - D3: a descrição do movimento usa `financiamento.descricao`, que não existe no modelo, e grava sempre "Financiamento #id".
  - D4: o motivo do estorno é montado e descartado.

**Rascunho pronto, fora do repositório para não ser aplicado por engano:**
- Migration `20261111090000_financeiro_financiamentos_pagamento.sql`, com `pagar_parcela_financiamento` e `estornar_parcela_financiamento`.
  - Regras do Flask, com as correções D2–D4.
  - Escritor único, chave de idempotência, saldo pelos movimentos.
  - Parcela com despesa vinculada recusada.
- Testes de fidelidade (o Flask executa o mesmo roteiro).
- Local: `C:\Users\heyds\AppData\Local\Temp\claude\d--OneDrive-Kortex-Brasil-Controle-Financeiro\03e0421d-53db-45c5-9cf9-647f7595e1dc\scratchpad\fase2_financiamentos\`
- Os testes precisam ser revistos: o cenário deve usar a despesa vinculada, que é o caminho real.

**Para desbloquear (decisão do titular):**
1. Autorizar uma alteração pequena no Flask.
   - Em perfil do novo aplicativo, recusar o pagamento e o estorno de parcela de financiamento: em `_paga_pelo_novo_aplicativo` e nas rotas `/parcelas/<id>/pagar` e `/estornar-pagamento`.
   - Mesmo padrão já usado nas despesas comuns ("Os pagamentos deste perfil sao feitos pelo novo aplicativo").
2. Então, no novo aplicativo:
   - liberar a despesa da parcela em Despesas (`bloqueio_do_pagamento`), sincronizando a parcela na mesma transação: status, valor pago, diferença e saldo devedor;
   - no estorno, reabrir a parcela (corrige D1), só da última paga para trás.
3. Decidir se D1 deve ser corrigido também no histórico.
   - Parcelas "pago" com despesa "Pendente" depois de estorno.
   - É uma conferência por identidade, sem reescrever saldos.

## 7. Consórcios, fase 1 (feita): consulta

- **Migration `20261116090000_financeiro_consorcios_leitura.sql`:** `consorcios_tela(perfil, id)`.
  - `GET /api/consorcios/`: só os ativos, como o Flask.
  - `GET /api/consorcios/<id>`: ativo ou não; "Consórcio não encontrado" como no Flask.
  - Reproduz `consorcio_to_dict`: `ContratoConsorcio.to_dict`, mais meio de pagamento, cartão, conta, categoria do cartão e categoria da primeira parcela (`<nome> - Parcela%`, tipo Consorcio, no perfil do contrato).
  - **Diferença deliberada:** ao ler um contrato sem perfil, o Flask atribui o perfil padrão ao objeto em memória (`perfil_id_consorcio`). Aqui a leitura usa o mesmo perfil, mas nunca altera o contrato.
- **Tela:**
  - Os consórcios voltam a aparecer na lista de Recorrências, como no Flask (`recorrencias-adaptador.js`).
  - O aviso mudou para "Consórcios: só consulta nesta fase. Cadastro, edição e exclusão continuam no sistema atual."
  - As escritas (Despesas e Recorrências) continuam respondendo "em migração", sem gravar.
  - Pagamento de parcela de consórcio: o mesmo bloqueio do escritor único das parcelas de financiamento (§6).
- **Testes:**
  - `tests/test_supabase_consorcios_leitura.py`, **3 passaram**.
    - O próprio Flask cria 3 consórcios fictícios: com reajuste, contemplação, prêmio e débito automático; sem meio de pagamento; e um inativado.
    - Lista e detalhes comparados campo a campo, inclusive o não encontrado.
    - Também cobertos: isolamento e "nada gravado".
  - `recorrencias_tela.spec.mjs`: **6 passaram** (aviso atualizado).
