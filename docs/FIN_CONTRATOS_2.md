# FIN-CONTRATOS-2 — Escrita de Financiamentos e Consórcios (Flask → Supabase): pagamento, estorno e escritor único

**Data:** 26/10/2026.

**Situação:** implementado e testado **localmente** (cluster descartável, o próprio Flask como referência, PostgREST e Playwright).
- Sem commit, push, publicação ou migration aplicada.
- O `gastos.db` foi só lido, por contagens, com `mode=ro&immutable=1`; tamanho e mtime conferidos, inalterados.

## 1. Funcionalidades implementadas

**Escritor único do lado do Flask (alteração localizada, autorizada):**
- **`routes/financiamentos.py`:** `before_request` do blueprint. Em perfil NOVO, toda escrita do módulo recebe 409 `SISTEMA_NOVO` e nada é gravado:
  - cadastro, edição, exclusão, regenerar parcelas;
  - pagar e estornar parcela;
  - amortização extraordinária, ajuste de saldo, vigências de seguro;
  - documentos e conferências de caixa.
  - Ficam fora: `simular-quitacao`, que só calcula, e indexadores, tabela global sem perfil.
- **`routes/consorcios.py`:** o mesmo, para cadastro, edição, exclusão e regenerar parcelas.
- **`routes/despesas.py` (`_paga_pelo_novo_aplicativo`):** as despesas de parcela de financiamento e de consórcio entram na guarda que já valia para despesas comuns e faturas.
- **Mesma verificação** (`flask_pode_gerar`) de Despesas, Receitas e Contas Bancárias:
  - sem a configuração (SQLite, banco sem a migration), comportamento legado;
  - erro na verificação, escrita bloqueada;
  - consultas continuam.

**Pagamento e estorno das parcelas pelo caminho real** (migration `20261120090000`):
- No Flask, cada parcela de financiamento tem a sua despesa e é paga em Despesas. A parcela de consórcio é a despesa do item `Consorcio`.
- `bloqueio_do_pagamento` libera essas despesas. A fatura de cartão continua na tela de Cartões.
- `pagar_despesa` sincroniza a parcela **na mesma transação**:
  - status `pago`;
  - `valor_pago`;
  - `dif_apurada` = previsto − pago;
  - saldo devedor do contrato.
  - É a regra de `registrar_pagamento_parcela`.
- `estornar_pagamento_despesa` **reabre a parcela** (status `pendente`, valor pago e diferença zerados) e devolve o saldo devedor à cadeia.
  - Só a partir da parcela paga mais recente, regra do estorno direto do Flask.
  - A verificação vem antes de qualquer gravação.
- **Consórcio:** a despesa é paga e estornada como despesa, com o item `Consorcio` intacto. A identidade contratual se preserva: a edição da despesa de parcela continua bloqueada.
- **Tela de Financiamentos:** "pagar/estornar parcela" orienta para Despesas, como o Flask ("Use o fluxo de Despesas"), sem gravar.

**Garantias** (do motor já aplicado, agora válidas também para parcelas):
- escritor único do perfil (`exigir_pagamento_novo`);
- gestão do perfil;
- chave de idempotência (reenvio = um débito só);
- travas em ordem despesa → financiamento → parcela → conta bancária;
- saldo da conta pelos movimentos;
- estorno identificado pelo débito original.

## 2. Os dois defeitos de estorno

| Defeito | No Flask (confirmado pelo próprio Flask no teste) | Aqui |
|---|---|---|
| **A**: estorno não reabre a parcela | O estorno em Despesas devolve a despesa a Pendente e deixa a parcela `pago`, com o saldo devedor reduzido. Por isso, **pagar de novo dá erro 500**: `registrar_pagamento_parcela` recusa "Esta parcela ja foi paga" | A parcela reabre e o saldo devedor volta ao da parcela anterior. Pagar de novo funciona |
| **B**: segundo estorno bloqueado | O estorno procura estorno anterior pela despesa (rota de Despesas) ou pela parcela (rota direta): depois de pagar, estornar e pagar de novo, o segundo estorno fica bloqueado para sempre | Cada estorno é ligado ao seu débito (`movimento_original_id`). Pagar, estornar, pagar e estornar de novo funciona, cada operação com identidade própria |

**Dados reais** (`gastos.db`, só contagem):
- 0 parcelas `pago` com despesa não paga;
- 0 despesas pagas com parcela pendente;
- 0 estornos de despesa de parcela já feitos;
- 420 de 420 parcelas com despesa vinculada.
- **Não há histórico a sanear** do Defeito A. Toda parcela real é paga pelo caminho de Despesas.

## 3. Testes executados

| Conjunto | Resultado |
|---|---|
| `tests/test_supabase_contratos_pagamento.py` (novo) | **8 passaram**. Detalhes abaixo |
| E2E `contratos_pagamento.spec.mjs` (novo), pela tela original de Despesas | **2 passaram**. Detalhes abaixo |
| Regressão de banco e Flask: `test_supabase_*` (todos), movimentações, trava de pagamento, faturas, baixa transacional, saldos, estornos de despesa e de financiamento, conferência e calibração de financiamento, documentos, consórcio/receita, recorrências de consórcio, débito automático, UX de despesas e financiamentos | **930 passaram, 0 falhas**, 18 pulados |
| E2E completo (cluster + PostgREST + Playwright) | **88 passaram, 1 falhou** (`despesas.spec`: `net::ERR_NO_BUFFER_SPACE` do Windows ao abrir a página de login, falha de ambiente). A spec rodada sozinha: 5 de 5 |
| Unitários do `web/` | **30 passaram** |

**Banco (`test_supabase_contratos_pagamento.py`):**
- O Flask cria o financiamento, paga as parcelas 1 e 2 em Despesas, estorna, paga de novo e estorna de novo. O novo aplicativo faz o mesmo noutra cópia.
- **Pagamentos:** parcela, despesa e saldo devedor iguais ao Flask.
- **Estornos:** Defeitos A e B corrigidos; o Flask confirma os dois defeitos.
- **Ordem do estorno:** só a parcela paga mais recente; fora de ordem nada é gravado, nem o crédito.
- **Atomicidade:** parcela já `pago` com despesa pendente recusa o pagamento inteiro, sem movimento.
- **Idempotência.**
- **Escritor único:** perfil no Flask recusa; quem só lê recusa.
- **Consórcio:** pago, estornado, pago e estornado de novo, com o item intacto e o saldo da conta igual aos movimentos.
- **Guarda do Flask:** perfil NOVO recusa 16 escritas de financiamentos, consórcios e despesas de parcela, e nada muda em 6 tabelas. Consultas e simulação respondem 200. Perfil no Flask segue gravando.
- **Reversão:** ida e volta conferida.

**E2E (`contratos_pagamento.spec.mjs`):**
- Parcela paga e estornada duas vezes, com parcela e saldo devedor acompanhando.
- Estorno fora de ordem recusado.
- A tela de Financiamentos orienta para Despesas.
- Tudo desfeito no fim.

**Ajustado:** `test_movimentacoes.py::test_consorcio_fica_no_flask` virou `test_consorcio_pago_pelo_escritor_do_perfil`. A regra inverteu: com o perfil no novo aplicativo, o Flask recusa e o novo paga.

**Cenário E2E:** o financiamento fictício do Perfil B ganhou as despesas das parcelas (`semear_financiamento_e2e`), como o Flask cria.

## 4. Diferenças em relação ao Flask

1. **Defeitos A e B corrigidos** (§2).
2. **Saldo devedor:** sempre o da parcela paga de **maior número**; sem parcela paga, o valor financiado. O Flask grava o da última parcela paga, mesmo fora de ordem. Pagando em ordem, o resultado é igual.
3. **Ligação parcela–despesa** pelas duas formas do Flask (`conta.financiamento_parcela_id` ou `financiamento_parcela.conta_id`). O Flask de Despesas só olha a primeira.
4. **Valor diferente do devido** segue a regra do motor de Despesas: classificar (juros, desconto, ajuste) e justificar. A `dif_apurada` da parcela registra a diferença, como no Flask.

## 5. Migrations necessárias

- **`20261120090000_financeiro_contratos_pagamento.sql`** (local, não aplicada):
  - 4 funções internas novas;
  - substitui `bloqueio_do_pagamento`, `pagar_despesa` e `estornar_pagamento_despesa`, com o texto de `20261101090000` mais as linhas marcadas e as mesmas assinaturas e privilégios;
  - nenhuma tabela e nenhum dado.
- **Reversão:** `supabase/reversao/20261120090000_pagamento_despesa_anterior.sql`, testada (ida e volta).
- **Ordem:** depois de `20261119090000` (Receitas e Categorias, também local).
- **Atenção:** a guarda do Flask e esta migration andam juntas.
  - Com a migration e sem a guarda: dois escritores para as despesas de parcela, num perfil NOVO.
  - Com a guarda e sem a migration: num perfil NOVO, ninguém paga parcela.

## 6. Pendências reais

| Pendência | Prioridade |
|---|---|
| **Motor de cálculo dos contratos** (cadastro, edição, regenerar parcelas, amortização extraordinária, redução de prazo/prestação, ajuste de saldo, seguros DFI/MIP e faixa etária, taxa administrativa, vigências, quitação): continua só no Flask. É um porte grande e próprio (SAC, PRICE, SAC/TR, indexadores) | **P0 antes de atribuir um perfil real com contratos ao novo aplicativo** (§7) |
| **Consórcios: cadastro, edição, exclusão, regenerar parcelas e receita de contemplação**: continuam só no Flask | P0 (mesma razão) |
| Pagamento direto de parcela **sem** despesa (contratos antigos): rascunho em `supabase/rascunhos/` | P3: os dados reais não têm nenhuma (420 de 420 com despesa) |
| Defeito do Flask: `regenerar-parcelas` de consórcio apaga as despesas do contrato, **inclusive pagas** (`Conta.query.filter(item_despesa_id.in_(...)).delete()`), perdendo histórico. Agora só ocorre em perfil no Flask | P1 (registrar; corrigir no porte do consórcio) |
| Guarda do Flask nas rotas de Categorias do Cartão (FIN-FIDELIDADE-RECEITAS-CATEGORIAS-1 §6) | P0 antes de perfil real NOVO |
| Escritas aplicadas que ainda não exigem o escritor (cadastros de despesas, receitas, cartões: `FIN_ESCRITOR_UNICO_CONTAS_1.md` §3.1) | P0 antes de perfil real NOVO |

## 7. Riscos de integração

- **Perfil NOVO fica sem manutenção de contratos:** a guarda tira do Flask, para esse perfil, o cadastro e a manutenção de financiamentos e consórcios. O novo aplicativo ainda não os tem (só pagamento e estorno). Hoje isso só afeta os perfis fictícios. **Nenhum perfil real deve ir para o novo aplicativo antes do porte do motor de cálculo** (§6).
- **Aplicação das duas partes juntas** (§5): publicar a guarda do Flask e aplicar a migration no mesmo momento da transição de um perfil.
- **Flask em SQLite:** a guarda só vale quando o Flask apontar para o mesmo PostgreSQL (como em Contas Bancárias).
- **Lógica nova sobre funções já aplicadas:** `pagar_despesa` e `estornar_pagamento_despesa` estão em uso na prévia. A troca mantém o texto anterior e só acrescenta as linhas da parcela. Uma despesa sem parcela segue exatamente igual (regressão de 930 testes sem falha).

## 8. Arquivos alterados

- **Flask (só a guarda):**
  - `backend/routes/financiamentos.py`;
  - `backend/routes/consorcios.py`;
  - `backend/routes/despesas.py`.
- **Banco:**
  - `supabase/migrations/20261120090000_financeiro_contratos_pagamento.sql`;
  - `supabase/reversao/20261120090000_pagamento_despesa_anterior.sql`.
- **Web:**
  - `web/src/js/financiamentos-adaptador.js` (orientação para Despesas);
  - `web/tests/e2e/contratos_pagamento.spec.mjs`.
- **Testes:**
  - `tests/test_supabase_contratos_pagamento.py`;
  - `tests/test_movimentacoes.py`;
  - `tests/supabase_local.py` (despesas das parcelas no cenário E2E).

## 9. Aplicação no Supabase de teste, validação real e prévia (26/10/2026)

**Commits** (autorizados, sem push):
- `9b977a6`: Receitas e Categorias;
- `43c76d0`: guarda do Flask;
- `8c42925`: migration de pagamentos e testes.

**Verificações antes de aplicar** (só leitura no remoto):

| Verificação | Resultado |
|---|---|
| Definições atuais de `bloqueio_do_pagamento`, `pagar_despesa` e `estornar_pagamento_despesa` | Idênticas às de `20261101090000`: a reversão devolve exatamente o que estava lá |
| Assinaturas, retorno, `security definer`, `search_path`, privilégios | Iguais; `create or replace` mantém os privilégios |
| Funções novas das duas migrations (25) | Nenhuma existia no remoto |
| Colunas e tipos das tabelas usadas | Iguais ao cluster de testes |
| `status` e `simular` | Exatamente `20261119090000` e `20261120090000`, nessa ordem |

**Aplicação:**
- As duas foram aplicadas na ordem, sem falha intermediária.
- O conteúdo das 64 tabelas ficou **idêntico** ao de antes.
- Funções: +25; só as 3 previstas foram alteradas.
- Migrations: 31 de 31.

**Validação real** (perfil temporário criado pelo aplicativo, dados marcados "(e2e-real)", **21 de 21**):
- **Despesa comum:** dois ciclos de pagar e estornar.
- **Fatura de cartão:** pagar e estornar.
- **Financiamento:**
  - 3 parcelas, com as despesas ligadas como o Flask cria;
  - pagar 1 e 2: parcela e saldo devedor corretos;
  - estorno fora de ordem recusado;
  - Defeito A: o estorno reabre a parcela;
  - Defeito B: pagar e estornar de novo;
  - tudo estornado: saldo devedor = valor financiado.
- **Consórcio:** pagar e estornar.
- **Receita:** previsão, recebimento parcial e estorno; o estornado aparece marcado.
- **Categoria do Cartão:** criar, vincular, desvincular e desativar.
- **Leituras novas:** todas responderam 200.
- **Escritor único:** perfil trocado para Flask recusa parcela e Categoria do Cartão (`SISTEMA_FLASK`); quem só lê recebe 403.
- **Conta bancária:** saldo final 0, igual aos 16 movimentos (débitos e créditos de 4.240,00).
- **Telas:** 14 páginas no perfil temporário, com o `dist` e a CSP reais, incluindo Receitas, Categorias e Financiamentos. Nenhum erro de console ou CSP, nenhuma chamada ao Flask.
- **Limpeza por identidade:** simulação, depois confirmação. O banco ficou idêntico ao retrato de logo após a aplicação.

**Prévia protegida:**
- O mesmo `dist` validado (impressão `6a36675ec250`, 155 arquivos), versão `8c42925`.
- Endereço desta versão: https://8c30afd3.controle-financeiro-jah.pages.dev
- Prévia: https://avaliacao.controle-financeiro-jah.pages.dev
- O Access exigiu login antes e depois do envio (prévia, páginas internas, `config.js`). O endereço principal continua 404.

**Inalterados:**
- produção;
- perfis Pessoal e Empresa, que continuam no Flask;
- `gastos.db` (1294336 bytes, mtime 1778600040).

**Registrado:** a falha E2E por esgotamento de sockets do Windows (`net::ERR_NO_BUFFER_SPACE`) foi de ambiente; a spec passou isolada.

**Próximo contrato (titular): FIN-CONTRATOS-3.**
- Motor de cálculo e manutenção de Financiamentos e Consórcios: cadastro e edição, geração de parcelas, SAC/PRICE e atualização, seguros DFI/MIP, amortizações (prazo ou prestação), ajustes de saldo, recálculo só das futuras, exclusão segura e quitação.
- A regeneração do consórcio **não** reproduz a exclusão de despesas pagas do Flask. Não executar regeneração sobre contratos reais até a proteção estar comprovada.
