# FIN-CONSORCIOS-INTEGRACAO-01 (P24): consórcio em moeda — contemplação, edição de parcelas e contrato em andamento

**Situação:** implementada localmente (ramo `consorcios-p24`, migration `20261227090000`). Publicação e correção dos contratos reais dependem de autorização própria.
**Testes:** nível N4 (integridade financeira).

**Escopo (retificação + Adendo 02):** o consórcio continua em moeda, com a mesma natureza, a mesma fórmula do prêmio e a mesma geração de parcelas. Nada de carta de crédito, novas condições de contemplação ou mudança de contabilização.

## 1. Diagnóstico

| Ponto | Causa |
|---|---|
| **A. Receita da contemplação** | O banco já cria a receita prevista no mês de contemplação (`sincronizar_receita_contemplacao`, marcador `consorcio_id=N`). Mas o "Confirmar/realizar" de Receitas envia `PUT /realizadas/:id` com a conta (como no Flask), e o novo aplicativo respondia "Editar um recebimento ainda não está disponível". A contemplação não podia ser recebida. |
| **B. Edição de parcelas** | Em Despesas, a parcela de consórcio caía em "Parcelas de consórcio: em migração". Não havia como corrigir valor ou vencimento. |
| **C. Contrato em andamento** | `criar_consorcio` gera as parcelas a partir de "Data inicial" e do número de parcelas. Não havia como dizer que as primeiras já tinham sido pagas antes do cadastro. Para um contrato já em curso, a saída era cadastrar só o restante, o que distorce a numeração (1/6 em vez de 5/10) e o prêmio. |

**Fórmula do prêmio (inalterada):** valor da parcela na posição da contemplação × número de parcelas do contrato (`consorcio_normalizar`).

### Caso real: Consórcio Diego 1 e Diego 2 (contratos 18 e 19)

Os dois contratos foram cadastrados em 11/11/2026 só com o restante:
- 6 parcelas a partir de 11/2026, 540 + 10 fixo, contemplação 02/2027.
- A parcela 1/6 (11/2026, R$ 540,00) de cada um foi paga em 11/11, com movimento (contas 2686 e 2692).
- Receitas previstas 50 e 51: R$ 3.420,00 em 02/2027, sem conta.

O valor de 11/2026 (540 = 500 + 4 × 10) indica a **5ª parcela** de um contrato de 10, iniciado em **07/2026** com R$ 500,00.

| Conferência (por contrato) | Valor |
|---|---|
| Prêmio atual | **R$ 3.420,00** (570 × 6) |
| Elementos que ficaram de fora | as 4 primeiras parcelas (07 a 10/2026: 500, 510, 520 e 530 = R$ 2.060,00 pagas antes do cadastro); por isso o multiplicador ficou 6 em vez de 10 |
| Prêmio correto | **R$ 5.700,00** (570 × 10; a contemplação é a posição 8) |
| Diferença | **R$ 2.280,00** por contrato (R$ 4.560,00 nos dois) |
| Mês da contemplação | **02/2027** (não muda) |

**A confirmar pelo titular antes de qualquer correção:**
- Início em 07/2026, valor inicial R$ 500,00 e reajuste de R$ 10,00. A dedução vem só do valor de 11/2026.
- Em produção existem os contratos legados **13 e 14** do Flask ("Consórcio", observações "Diego 1" e "Diego 2"): ativos, início 01/2026, 10 parcelas, contemplação 01/2026, prêmio R$ 5.000,00, sem parcelas geradas. Eles divergem da dedução acima e parecem rascunhos. Inativá-los é outra decisão.
- As receitas 42 e 43 (R$ 5.000,00 cada, realizadas em 01/2026 nas contas 96 e 97) apontam para os contratos 3 e 4, que não existem mais. São legado do Flask e não foram tocadas.

## 2. Solução (migration `20261227090000`)

**Funções novas:**

| Função | Acesso | Papel |
|---|---|---|
| `consorcio_parcelas_anteriores` | interna | valida o campo novo: inteiro, menor que o total e com a última parcela anterior ao mês corrente |
| `registrar_parcelas_anteriores_consorcio` | interna | marca as posições 1..N como pagas no histórico (`data_pagamento` = vencimento), **sem movimento bancário**, num lote de `regularizacao_historica` (reversível por `reverter_regularizacao_historica`) |
| `realizar_contemplacao_consorcio(perfil, receita, dados, chave)` | authenticated | recebe a contemplação prevista uma única vez: conta bancária, data, valor (padrão = previsto; diferente exige justificativa), movimento de CRÉDITO, saldo atualizado e auditoria em `operacao_receita`; idempotente pela chave |
| `editar_parcela_consorcio(perfil, conta, versão, dados, escopo)` | authenticated | valor e vencimento de uma parcela pendente sem movimento; escopo `unica` (esta) ou `futuras` (o valor vai também para as seguintes do contrato); paga, histórica ou com movimento fica como está |

**Função substituída:** `criar_consorcio` aceita `parcelas_pagas_anteriores`. O contrato é informado inteiro (Data inicial = mês da 1ª parcela, total de parcelas). As primeiras N ficam pagas no histórico e a numeração segue a do contrato (a do mês corrente é a 5/10). O prêmio e a receita prevista são calculados sobre o contrato inteiro.

**Tela (só adaptadores e adaptações; `js/original` intacto):**
- **Recorrências:** campo "Parcelas já pagas antes do cadastro", só no cadastro, com ajuda.
- **Despesas:** o lápis da parcela pendente abre a escolha original "esta / esta e as futuras". A parcela paga é recusada com orientação de estorno.
- **Receitas:** "Confirmar/realizar" da contemplação usa a RPC nova. Editar outro recebimento continua indisponível.

**Reversão:** devolve o texto publicado de `criar_consorcio` e remove as 4 funções novas.

## 3. Testes por impacto (N4)

| Bateria | Resultado |
|---|---|
| Banco, nova: `tests/test_supabase_consorcios_p24.py`. Cobre: contrato novo 1/10..10/10; retroativo com 4 pagas (sem movimento, mesmo lote, 5/10 no mês corrente, prêmio 5.700); reajuste percentual; 3 entradas inválidas; lote reversível; `regenerar` preserva as históricas; realização única com crédito e saldo; idempotência; `JA_REALIZADA`; editar o contrato não reescreve a recebida; justificativa; outro perfil; totais de receitas; edição "esta" e "esta e as futuras"; casos bloqueados; outro contrato intacto; permissões; reversão e reaplicação | 19/19 |
| Regressão de banco: 12 arquivos (P24, escrita e leitura de consórcios, cadeia de reversões i7, regularização histórica, receitas, saldo e data de receitas, cancelamento de despesas, recorrências, tela e inativação), com PostgREST | 264/264 |
| Unitários web | 92/92 |
| E2E nova: `web/tests/e2e/consorcios_p24.spec.mjs` (usuário E, dados fictícios): cadastro retroativo pelo formulário; edição "esta" e "esta e as futuras" em Despesas; "Confirmar/realizar" em Receitas com o crédito; limpeza | 3/3 |
| E2E de regressão: 10 specs (contas, despesas, cancelamento, lote, contratos, receitas, saldo de receitas, recorrências, inativação, P24) | 52/52 |

## 4. Ensaio em cópia fiel (11/11/2026)

Script `scratchpad/p24/ensaio_1227.py`. Cópia da produção em PostgreSQL local descartável; a produção só foi lida. A correção dos contratos 18 e 19 e a realização foram feitas **só na cópia**.

| Conferência | Resultado |
|---|---|
| Cópia | idêntica à produção (66 migrations) |
| Função substituída | `criar_consorcio` igual ao texto da reversão |
| Migration | nenhum dado alterado; 4 novas, 1 alterada; leituras iguais (Despesas 07/2026 a 04/2027, consórcios, receitas 50/51) |
| Reversão e reaplicação | funções iguais; nenhum dado alterado |
| Segurança | nenhuma função definer sem `search_path`; nenhuma para anon; as 2 internas sem acesso de authenticated |

### Correção proposta dos contratos 18 e 19 (simulada na cópia)

Uma transação por contrato, com conferência do estado esperado e auditoria em `operacao_despesa` (`corrigir_consorcio_retroativo`):
1. Renumerar as 6 parcelas existentes i/6 → (i+4)/10. Os valores e vencimentos já são os do contrato inteiro: 540…590 de 11/2026 a 04/2027. A 5/10 continua paga com o seu movimento.
2. `editar_consorcio`: início 07/2026, 10 parcelas, R$ 500,00. O prêmio é recalculado pela fórmula original.
3. `regenerar_parcelas_consorcio`: cria as posições 1 a 4 e preserva a paga.
4. `registrar_parcelas_anteriores_consorcio(…, 4)`: as posições 1 a 4 (07 a 10/2026) ficam pagas no histórico, sem movimento, num lote reversível.

| Resultado na cópia | Valor |
|---|---|
| Contratos 18 e 19 | 10 parcelas, início 07/2026, contemplação 02/2027, prêmio **R$ 5.700,00** |
| Parcelas | 1/10 a 4/10 pagas no histórico (sem movimento); 5/10 paga com o movimento original; 6/10 a 10/10 pendentes |
| Receitas previstas 50 e 51 | R$ 3.420,00 → **R$ 5.700,00** (02/2027, ainda sem conta) |
| Despesas por mês (os dois contratos) | 07/2026 +1.000,00; 08 +1.020,00; 09 +1.040,00; 10 +1.060,00 (todas pagas no histórico); 11/2026 em diante: **sem alteração** |
| Preservado | movimentos, saldos bancários, `pagamento_fatura` e todas as outras contas idênticos |
| Realização da contemplação do 18 (na cópia) | crédito de R$ 5.700,00 na conta 96 (movimento CRÉDITO/RECEITA); saldo 600,92 → 6.300,92 |

**Impacto financeiro se aplicada:**
- Despesas pagas de 07 a 10/2026 aumentam R$ 4.120,00, só como histórico, sem débito bancário.
- Receita prevista de 02/2027 aumenta R$ 4.560,00.
- Nenhum saldo muda até a realização.

## 5. Dependem de autorização

- **Publicação:** push de `consorcios-p24` (a partir de `689bb74`), migration 1227 (= 67) e deploy.
- **Correção dos contratos 18 e 19:** o roteiro da seção 4, depois de o titular confirmar início 07/2026, R$ 500,00 e reajuste de R$ 10,00. Executar só depois da publicação, porque usa `registrar_parcelas_anteriores_consorcio`.
- **Contratos legados 13 e 14** (ativos, sem parcelas): manter ou inativar.
- **A realização da contemplação** fica com o titular, pela tela, quando o valor entrar.
