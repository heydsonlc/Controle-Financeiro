# FIN-MOB-ABAST-LANCAMENTOS-01 — Abastecimento no formulário de Novo Lançamento

**Situação (08/11/2026): publicado com a P20 (`5b5e4e8`, migration `20261217090000`, deploy `9e2982ab`).** Auditoria somente leitura aprovada (seção 8). O primeiro abastecimento real fica com o usuário.

**Princípio:** uma despesa financeira e, no máximo, um registro operacional de abastecimento vinculado a ela. O abastecimento nunca é outra despesa.

## 1. Diagnóstico

| Ponto | O que existe | Onde |
|---|---|---|
| Categoria no formulário | Cartão: "Categoria da despesa" (`#lancamento-categoria-despesa-cartao`). Despesa direta: "Categoria" (`#lancamento-categoria-geral`). As opções vêm de `categorias_de_despesa` (id, nome, cor), sem código | `web/src/paginas/lancamentos.html`, `frontend/static/js/lancamentos.js` |
| Categoria Combustível | `categoria.codigo_sistema = 'MOB_COMBUSTIVEL'` (id 1 na produção); a Mobilidade já a encontra por `mob_categoria_evento('COMBUSTIVEL')` | migrations 1127 e 1214 |
| Compra no cartão | `criar_compra` (escritor único; idempotente por chave; fatura consolidada só com confirmação). Devolve `lancamentos` (ids das parcelas) | migration 1124 |
| Despesa direta | `criar_despesa` (pendente; pagar fica em Despesas). Devolve `conta_id` | migration 1124 |
| Cartões físicos | `financeiro.cartao_vinculado` (só o final de 4 dígitos), lidos por `cartoes_vinculados`; a compra guarda `cartao_vinculado_id` (o gatilho confere o contrato). `criar_compra` não recebe o cartão físico | migration 1213 |
| Abastecimento | `financeiro.abastecimento`: litros gerados (`valor_total / preco_litro`), `lancamento_id` ou `conta_id` (nunca os dois), um abastecimento por despesa (índices únicos), contrato e cartão físico. Exclusão da despesa só desfaz o vínculo (`on delete set null`) | migration 1215 |
| Funções do abastecimento | `registrar_abastecimento` (valida hodômetro, combustível do veículo, cartão; recusa repetição); `vincular_abastecimento` (mesmo valor, mesmo cartão, uma despesa por abastecimento, histórico); `desvincular_abastecimento`; `corrigir_abastecimento` (com motivo e histórico; vinculado não muda veículo nem valor); `candidatas_abastecimento` | migration 1215 |
| Transações | Cada função do banco é uma transação. Hoje a tela teria de chamar a compra e o abastecimento separadamente: a compra poderia ficar sem o abastecimento | — |
| Edição de compra em Lançamentos | Recusada de propósito (o Flask criava uma compra nova); a correção fica em Cartões (`editar_lancamento_cartao`, que muda valor e categoria) | `lancamentos-adaptador.js` |
| Recorrências e categorias | O abastecimento não toca em recorrência; a categoria é a da despesa | — |

**Produção (somente leitura):** 1 veículo (SIMULADO, etanol), nenhum cartão físico cadastrado, 6 compras na categoria Combustível.

### Por que uma migration

As peças existem, mas gravar a despesa e o abastecimento juntos só é atômico no banco. A migration `20261217090000` **só cria funções**: nenhuma tabela, coluna ou valor muda, e as regras são as funções existentes, chamadas na mesma transação.

## 2. Modelo adotado

`salvar_lancamento_abastecimento(perfil, {lancamento, abastecimento}, chave)`:

| `lancamento.tipo` | Despesa | Abastecimento |
|---|---|---|
| `compra` | `criar_compra` (à vista) e o cartão físico na compra | novo (ou reaproveitado), vinculado |
| `despesa` | `criar_despesa` | novo (ou reaproveitado), vinculado |
| `compra_existente` | não muda | novo, reaproveitado ou escolhido, vinculado |
| `despesa_existente` | `editar_despesa`, se houver dados | o vinculado acompanha (desvincular, corrigir, vincular, com histórico) |

1. Valor, data, cartão e estabelecimento do abastecimento vêm da despesa (os campos não se repetem).
2. Os dados do abastecimento são validados **antes** de criar a despesa, com a mesma função da Mobilidade.
3. Qualquer falha desfaz tudo. Repetir com a mesma chave devolve o resultado gravado; as chamadas internas usam chaves derivadas dela.
4. Um abastecimento já registrado em Mobilidade, ainda sem despesa, com o mesmo veículo, data, hodômetro e valor, é **reaproveitado**: não fica um segundo registro.
5. Compra parcelada não recebe abastecimento (o valor da parcela não é o do abastecimento).

Leituras: `formulario_abastecimento_lancamento` (id da categoria pelo código, veículos com o último hodômetro, exceto elétricos) e `abastecimento_do_lancamento` (o vinculado, os candidatos ainda sem despesa e a categoria da despesa).

## 3. Interface

Bloco **Dados do Abastecimento** no formulário (`web/src/paginas/lancamentos.html`, `web/src/js/lancamentos-abastecimento.js`, `web/src/css/lancamentos-adaptacoes.css`):

- Aparece com a categoria Combustível (pelo id que o banco informa, nunca pelo nome); some com outra categoria **sem apagar** o que foi preenchido.
- Veículo, combustível compatível (flex: gasolina ou etanol), hodômetro (com o último registrado), preço por litro, litros calculados (três casas, recalculados a cada mudança de valor ou preço) e cartão físico (só quando o contrato tem cartões cadastrados; "Não identificado" é aceito).
- "Só a despesa (sem abastecimento)" lança a despesa como antes.
- Grade de duas colunas quando há espaço; uma no celular.

Comportamento no adaptador (`web/src/js/lancamentos-adaptador.js`):

| Ação | Resultado |
|---|---|
| Compra nova ou despesa nova com veículo | Uma operação: despesa e abastecimento vinculados |
| Editar compra já lançada e informar o abastecimento | Só o complemento; se valor, data, descrição, categoria ou fatura mudaram, nada é gravado (a correção da compra continua em Cartões) |
| Editar despesa direta com abastecimento | Despesa e abastecimento juntos, com histórico |
| Despesa deixa de ser Combustível | Aviso e decisão: continuar; depois manter ou desvincular. Nunca exclui |
| Cartões: mudar o valor de compra vinculada | Confirmação; a compra muda e o abastecimento é desvinculado (fica aguardando outra despesa) |
| Cartões: compra deixa de ser Combustível | Aviso e decisão, como acima |

A edição de compra herdada não preenchia a categoria (a lista não a traz); o bloco a completa com a categoria informada pelo banco, só quando o campo está vazio.

## 4. Testes

Resultados na seção 6.

**Banco** (`tests/test_supabase_abastecimento_lancamento.py`, 30 casos), cobrindo os itens 7 a 22 do contrato:
- formulário (categoria pelo código, veículos só do perfil);
- compra e despesa com abastecimento único;
- dois veículos na mesma competência;
- dois cartões físicos na mesma fatura;
- cartão sem cartão físico;
- cartão físico de outro contrato, veículo de outro perfil, hodômetro regressivo, preço e combustível inválidos, valor inválido, compra parcelada e data futura recusados sem gravar;
- falha depois da compra desfaz tudo;
- repetição sem duplicar e chave de outra operação recusada;
- compra existente sem mudar;
- abastecimento registrado reaproveitado (escolhido ou com os mesmos dados);
- despesa editada com o abastecimento acompanhando (histórico VINCULO, DESVINCULO, CORRECAO, VINCULO);
- exclusão da compra e da despesa preservando o abastecimento;
- mudança de categoria sem excluir;
- fatura, Dashboard, saldos, movimentos e recorrências iguais com e sem o abastecimento;
- custo do veículo sem contagem dupla;
- cenário da Mobilidade intacto;
- permissões;
- reversão e reaplicação.

**E2E** (`web/tests/e2e/lancamentos_abastecimento.spec.mjs`, usuário E com perfil próprio: dois veículos e um cartão com dois cartões físicos):
- bloco só com Combustível, combustíveis por veículo, cartões físicos, litros, dados preservados ao alternar e celular sem rolagem lateral;
- compra com abastecimento e cartão físico;
- compra já lançada complementada (e correção recusada);
- despesa direta com abastecimento e troca de categoria com decisão;
- Cartões: valor alterado desvincula sem excluir.

**Unitários:** `web/tests/unit/lancamentos-abastecimento.test.mjs` (litros e formatação).

## 5. Limitações

- O formulário de Lançamentos não edita compra de cartão (regra anterior); corrigir dados operacionais de compra vinculada é pela Mobilidade (corrigir com motivo) ou desvinculando e complementando de novo.
- Despesa direta não registra o meio de pagamento no abastecimento (o formulário não tem esse campo).
- Compra parcelada não recebe abastecimento.
- O reconhecimento durante a importação da fatura fica para contrato próprio; os vínculos já suportam esse fluxo (candidatos e reaproveitamento).

## 6. Resultados

| Bateria | Resultado |
|---|---|
| Banco (`test_supabase_abastecimento_lancamento.py`) | 30/30 |
| E2E do bloco (`lancamentos_abastecimento.spec.mjs`) | 5/5 |
| E2E completo, sem novas tentativas | 134/134 (uma rodada anterior teve 1 falha de login em financiamentos, instabilidade do ambiente; repetida limpa) |
| Unitários do frontend | 92/92 (3 novos) |
| Regressão por impacto | 314 casos, 0 falhas, 0 pulados |

**Ensaio em cópia fiel e descartável da produção (57 migrations):** aplicação sem mudar dados; as 3 funções criadas, só para `authenticated`. Uma compra real de Combustível à vista (R$ 113,12, 22/10/2026) complementada com o veículo real: 22,624 L, vinculado, compra idêntica; fatura (R$ 7.194,80), saídas do Dashboard (R$ 10.704,02) e despesas do mês iguais; só `abastecimento`, `abastecimento_historico` e `operacao_mobilidade` mudaram. Reversão: funções removidas, nenhum dado alterado; reaplicação idem.

**Sem duplicidade:** cada caso de gravação confere a contagem de compras, contas e abastecimentos antes e depois; repetir a operação (mesma chave) devolve o mesmo resultado sem gravar; falha depois da compra desfaz a compra.

## 7. Publicação

Push, aplicação da migration `20261217090000` (antes do deploy, porque a tela usa as funções novas) e deploy do frontend. Se a P20 (FIN-DESPESAS-PAGAMENTO-LOTE-01) for publicada antes com a sua migration, as versões precisam ficar em ordem crescente na produção.

## 8. Publicação e auditoria (08/11/2026)

- **Publicação conjunta com o FIN-DESPESAS-PAGAMENTO-LOTE-01 (P20):** commits `84635ae` e `909e65e` (este trabalho), `494f8a2`, `4e50fa9`, `f3ea0e0` e `5b5e4e8` (a P20), sobre `5b2e036` (documentação da P19). Push `0de5820..5b5e4e8`, em avanço direto.
- **Migrations:** a `20261217090000` aplicada e conferida antes da `20261218090000`, cada uma sozinha e com o plano de teste listando só o seu arquivo. Nenhum dado existente mudou, nenhuma tabela nova, nenhuma função alterada ou removida; as 4 funções novas executáveis só por `authenticated`, com `search_path` fixo. A `pagar_despesas_lote` publicada começa por `exigir_escrita_novo`. Produção com 59 migrations, a última `20261218090000`.
- **Deploy `9e2982ab`** (build do `5b5e4e8`): 165 arquivos servidos iguais ao build; as chamadas novas estão no JavaScript publicado; 17 páginas protegidas redirecionam ao login sem erros de JavaScript ou de CSP; cabeçalhos de segurança inalterados.
- **Dados (antes e depois, somente leitura):** as 86 tabelas com os mesmos dados; contas (779, 198 pagas), compras, movimentos (35), saldos das contas 96 (R$ 85.812,08) e 97 (R$ 12.469,48), faturas de 11/2026 dos cartões 387 e 388, créditos (nenhum), recorrências, abastecimentos (nenhum), financiamento (saldo R$ 269.267,97), Clube dos Oficiais e Apple One, Dashboard e despesas de 11/2026 a 01/2027 dos dois perfis, todos iguais. As 6 ocorrências pendentes da Diarista continuam pendentes e as 2 pagas intactas.
- **Testes:** os do conjunto integrado (`docs/FIN_DESPESAS_PAGAMENTO_LOTE_01.md`, "Conjunto integrado"), sem nova alteração de código depois deles.
