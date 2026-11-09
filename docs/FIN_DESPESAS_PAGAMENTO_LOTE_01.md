# FIN-DESPESAS-PAGAMENTO-LOTE-01 — Pagamento em lote com a conta bancária (P20)

**Situação (08/11/2026): publicado com o FIN-MOB-ABAST-LANCAMENTOS-01 (`5b5e4e8`, migration `20261218090000`, deploy `9e2982ab`).** Auditoria somente leitura aprovada (seção 6); nenhuma ocorrência real foi paga. O pagamento das 6 pendentes da Diarista fica com o usuário.

## 1. Causa comprovada

| Pergunta | Resposta |
|---|---|
| Função do botão | `pagarTodasOcorrencias(index)` do `despesas.js` original (o Flask), no agrupador semanal |
| Ocorrências pendentes | As do agrupador (nome sem " - DD/MM" + competência) que não estão pagas |
| Pagamento individual | Modal com valor, data e conta → `POST /api/despesas/<id>/pagar` → `pagar_despesa` |
| Conta no individual | `conta_bancaria_id` do modal, conferida por `travar_conta_bancaria` (do perfil e ativa) |
| O que o lote enviava | `confirm()` e, para cada ocorrência, `PUT /api/despesas/<id>` com `pago: true`, data de hoje e valor; **sem conta** |
| O backend aceitava conta para o lote? | Não havia função de lote |
| Registro do pagamento | `pagar_despesa`: movimento de débito na conta, saldo recalculado, despesa Paga com a conta, `pagamento_fatura` e `operacao_despesa`, numa transação |
| Duplicidade | Chave da operação (`operacao_despesa`), trava da despesa (`for update`) e recusa de despesa já paga |
| Falhas parciais | No lote antigo, cada chamada valia por si |

**Por que "0 paga(s), 8 com erro".** O lote usava a **edição** (`PUT`), não o pagamento. O adaptador de Despesas recusa marcar como paga pela edição, de propósito: "Use a ação de pagamento para marcar a despesa como paga: ela escolhe a conta bancária e registra o movimento". Cada uma das 8 ocorrências pendentes daquele momento voltou com essa recusa, antes de qualquer validação de conta. A falta de conta no envio não chegou a ser avaliada; o Pix não teve papel no erro.

**Produção (somente leitura).** "Diarísta" são **duas recorrências semanais** de R$ 200, Pix e sem conta (terças e sextas), agrupadas pela tela: 8 ocorrências em 11/2026, 2 pagas uma a uma pela conta 96 (Caixa), 6 pendentes (R$ 1.200,00).

## 2. Correção

**Migration `20261218090000`, só uma função nova** (`pagar_despesas_lote`); nenhuma tabela, coluna ou valor muda.

- **Necessidade da migration:** o lote só é transacional no banco. Cada ocorrência continua sendo paga por `pagar_despesa` (as mesmas regras do pagamento individual), todas na mesma transação e com a mesma conta. **Se qualquer uma é recusada, nenhuma é paga.**
- **Escritor único primeiro:** a função começa por `exigir_escrita_novo`, como as demais escritas do novo aplicativo. Perfil ainda no Flask é recusado (`SISTEMA_FLASK`) antes de qualquer validação, sem gravar nada.
- **Conferido de novo na confirmação:**
  - perfil;
  - conta ativa do perfil (antes de qualquer pagamento);
  - as mesmas ocorrências pendentes das mesmas recorrências na competência (nem a mais, nem a menos), recusando com `LOTE_DESATUALIZADO`;
  - o valor de cada uma igual ao que a tela mostrou (`VALOR_MUDOU`, de `pagar_despesa`);
  - situação e bloqueios.
- **Idempotência:** a chave do lote devolve o resultado gravado; cada ocorrência usa uma chave derivada dela. Duas confirmações simultâneas: a segunda encontra as despesas pagas e é recusada inteira.
- **A recorrência não muda:** meio de pagamento e conta cadastrados ficam como estão; só cada despesa paga recebe a conta do débito, como no pagamento individual.

**Tela** (`web/src/paginas/contas.html`, `web/src/js/despesas-adaptacoes.js`, `web/src/js/despesas-adaptador.js`, `web/src/css/despesas-adaptacoes.css`):

- O botão do agrupador abre o modal **Pagamento em lote**:
  - recorrência, competência e meio de pagamento;
  - quantidade de ocorrências pendentes e valor total;
  - conta bancária de débito, entre as contas ativas do perfil. Ela é obrigatória e vem sugerida quando todas as ocorrências já têm a mesma conta.
- **Cancelar** não grava nada. **Confirmar** fica desabilitado enquanto envia.
- **Sucesso:** "Pagamento em lote concluído", com a quantidade, o valor total, a conta e o saldo; a lista é recarregada ao fechar.
- **Recusa:** "Nenhuma ocorrência foi paga", com a ocorrência e o motivo. Quando a lista mudou, a tela pede para fechar e conferir de novo.
- **Resultado desconhecido** (falha de rede): nada é repetido sozinho; a tela pede para conferir a lista. Repetir a mesma seleção devolve o resultado gravado.

## 3. Testes

Resultados na seção 4.

**Banco** (`tests/test_supabase_pagamento_lote.py`, 18 casos), com duas recorrências "Diarista" semanais (fevereiro/2027: 4 terças e 4 sextas, como 11/2026), 2 pagas uma a uma:
- as 6 pendentes pagas na conta escolhida, com 6 débitos, R$ 1.200,00 e o saldo reduzido nesse valor;
- as pagas antes intactas (despesas e movimentos);
- recorrência intacta e nenhuma despesa nova;
- conta inativa, de outro perfil e ausente recusadas sem pagar nada;
- repetição sem novos movimentos e duas confirmações simultâneas pagando uma vez;
- valor alterado numa ocorrência recusando o lote inteiro, com o nome e o valor novo;
- ocorrência paga depois da abertura, ou deixada de fora, tornando o lote desatualizado;
- ocorrência repetida, de outro perfil ou de outra competência recusada;
- lista vazia e dados inválidos recusados;
- outro meio de pagamento (boleto) pagando em lote;
- pagamento individual inalterado;
- permissões;
- perfil no Flask recusado pelo escritor único, com as pendentes e com a lista vazia, sem gravar nada;
- reversão e reaplicação.

**E2E** (`web/tests/e2e/despesas_pagamento_lote.spec.mjs`, usuário E com perfil próprio, duas recorrências "Diarista E" em 02/2030):
- modal com a recorrência, as 6 pendentes, R$ 1.200,00 e só as contas ativas do perfil (a inativa e as de outros perfis não aparecem);
- botões do mesmo tamanho e alinhados;
- cancelar não paga;
- confirmar exige a conta;
- pagamento na conta escolhida, com as pagas e a recorrência intactas e o botão desabilitado depois;
- valor alterado com o modal aberto: nada pago, motivo na tela e lista conferida de novo.

## 4. Resultados

| Bateria | Resultado |
|---|---|
| Banco (lote) | 18/18 |
| E2E do lote | 3/3 |
| Módulos relacionados (Despesas, Recorrências, Contas Bancárias, pagamentos, Dashboard, fixas do cartão) | 254/254 |
| Regressão por impacto | 287 casos, 0 falhas, 0 pulados |
| Unitários do frontend | 89/89 |
| E2E completo, sem novas tentativas | 132/132 |

**Teste instável corrigido (só o teste):** `contas.spec.mjs` "detalhe da fatura" falhava às vezes na suíte completa, e também já tinha falhado antes deste trabalho. A tela carrega o mês duas vezes ao abrir (`despesas-adaptacoes.js`); o teste clicava depois da primeira carga e a segunda renderização fechava o detalhe. Agora espera a rede ociosa antes de clicar.

**Ensaio em cópia fiel e descartável da produção (57 migrations):**
- **Aplicação:** nenhum dado mudou; a função é executável só por `authenticated`.
- **Lote simulado, só na cópia:** as 6 ocorrências pendentes reais da Diarista de 11/2026 pagas com a conta 96, somando R$ 1.200,00. Foram 6 débitos, todos na conta 96, cujo saldo caiu R$ 1.200,00; a conta 97 não mudou.
- **O que mudou:** só `conta`, `movimento_financeiro`, `conta_bancaria` (saldo), `pagamento_fatura` e `operacao_despesa`. As recorrências ficaram iguais.
- **Repetição com a mesma chave:** nada mudou.
- **Reversão:** função removida, nenhum dado alterado; reaplicação idem.

**Conjunto integrado com o FIN-MOB-ABAST-LANCAMENTOS-01 (08/11/2026, ramo `publicacao-1217-1218`).** A primeira rodada achou um defeito desta função: começava só por `pode_gerir_perfil`, e o teste do escritor único (`test_i3` de `test_supabase_integracao_1123_1126.py`) exige a recusa `SISTEMA_FLASK` logo no início. Nada era gravado, porque cada pagamento passa por `pagar_despesa`. Corrigido no commit `f3ea0e0` (seção 2). Resultados depois da correção:

| Bateria | Resultado |
|---|---|
| Módulos dos dois trabalhos e relacionados (Despesas, Lançamentos, Mobilidade, Recorrências, Cartões, Contas Bancárias, pagamentos, faturas, Dashboard) | 708/708 |
| Regressão por impacto de todos os arquivos alterados | 1.588 casos, 0 falhas (22 pulados por ambiente, rodados à parte) |
| Arquivos com PostgREST (RLS, perfis, contas do mês, segurança pública) | 162/162 |
| Unitários do frontend | 92/92 |
| E2E completo, sem novas tentativas | 137/137 |

Ensaio em cópia fiel da produção com a 1217 e depois a 1218: nenhum dado mudou com as migrations; o lote simulado das 6 pendentes da Diarista deu o mesmo resultado de antes; repetição sem efeito; reversão exata.

## 5. Publicação

Publicação conjunta com o FIN-MOB-ABAST-LANCAMENTOS-01: a `20261217090000` primeiro e depois esta `20261218090000`, ambas antes do deploy, porque as telas chamam as funções novas. Um só deploy do frontend.

Depois do deploy, o pagamento das 6 ocorrências reais da Diarista fica com o usuário, pela tela.

## 6. Publicação e auditoria (08/11/2026)

- **Publicação conjunta com o FIN-MOB-ABAST-LANCAMENTOS-01:** commits `494f8a2`, `4e50fa9` (este trabalho), `f3ea0e0` (escritor único, aprovado à parte) e `5b5e4e8`, depois de `84635ae` e `909e65e` (abastecimentos) e `5b2e036` (documentação da P19). Push `0de5820..5b5e4e8`, em avanço direto.
- **Migrations:** a `20261217090000` aplicada e conferida antes da `20261218090000`, cada uma sozinha e com o plano de teste listando só o seu arquivo. Nenhum dado existente mudou, nenhuma tabela nova, nenhuma função alterada ou removida; as 4 funções novas executáveis só por `authenticated`, com `search_path` fixo. A `pagar_despesas_lote` publicada começa por `exigir_escrita_novo`. Produção com 59 migrations, a última `20261218090000`.
- **Deploy `9e2982ab`** (build do `5b5e4e8`): 165 arquivos servidos iguais ao build; as chamadas novas estão no JavaScript publicado; 17 páginas protegidas redirecionam ao login sem erros de JavaScript ou de CSP; cabeçalhos de segurança inalterados.
- **Dados (antes e depois, somente leitura):** as 86 tabelas com os mesmos dados; contas (779, 198 pagas), compras, movimentos (35), saldos das contas 96 (R$ 85.812,08) e 97 (R$ 12.469,48), faturas de 11/2026 dos cartões 387 e 388, créditos (nenhum), recorrências, abastecimentos (nenhum), financiamento (saldo R$ 269.267,97), Clube dos Oficiais e Apple One, Dashboard e despesas de 11/2026 a 01/2027 dos dois perfis, todos iguais. As 6 ocorrências pendentes da Diarista continuam pendentes e as 2 pagas intactas.
- **Testes:** os do conjunto integrado (seção 4, "Conjunto integrado"), sem nova alteração de código depois deles.
