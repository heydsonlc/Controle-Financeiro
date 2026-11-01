# FIN-CARTAO-DESPESAS-FIXAS-01 — Despesas Fixas do cartão: natureza única, previsto × executado e reconhecimento seguro

**Situação (01/11/2026): `FIN_CARTAO_DESPESAS_FIXAS_02_PUBLICADO`.**
- **Commit:** `a1d3be4`, push `9c310f9..a1d3be4`; o push não disparou implantação.
- **Migration `20261208090000`:** aplicada e conferida.
  - 49 versões; as 2 tabelas novas estão vazias e com RLS; 9 funções novas e 9 alteradas.
  - Nenhum dado existente alterado; segurança sem bloqueios.
- **Deploy `a57bb919`** (Production, branch `producao`) em https://controle-financeiro-jah.pages.dev.
  - Build de exportação limpa do commit; só 3 arquivos mudaram.
  - Os 165 arquivos servidos são idênticos ao build.
- **Homologação por leitura** (titular, sessão somente leitura, com o `despesas.js` servido): Black, Visa, Dashboard, lista de Despesas, limites e reconhecimento das 15 linhas iguais ao ensaio do §5. Perfil Empresa responde (sem dados).
- **Integridade:** retratos antes, depois e no fim. Só mudaram o registro da versão, as funções e as 2 tabelas novas; saldos, movimentos, compras, faturas e financiamento iguais.
- **Fora desta publicação:** a conciliação real da Netflix 11/2026 e o cadastro de apelidos reais (ver §6).

## 1. Diagnóstico (produção só lida)

- **Previsão:** a recorrência mensal no cartão já gera a compra prevista em cada fatura, no cartão certo, com o valor da recorrência (`is_recorrente`, `item_despesa_id`). Ela nasce também com a Categoria do Cartão resolvida, como no Flask.
- **Natureza:** só o detalhe da fatura em Despesas dava prioridade à fixa. Cartões, limites, a lista de Despesas, faturas do mês e o Dashboard somavam fixas e parceladas na Categoria do Cartão. Visa 11/2026: Assinaturas com R$ 497,40 (124%, "Estourado") contra R$ 227,70 no detalhe.
- **Reconhecimento da cobrança real:**
  - era só por nome idêntico ao da recorrência;
  - antes dele, uma conciliação **só pelo valor** casava a linha com qualquer compra recorrente do mês: "CHATGPT R$ 109,90" virava o Claude e "APPLE.COM/BILL R$ 59,90" virava a Netflix;
  - reconhecida, a cobrança só saía da efetivação, e a previsão ficava com o valor antigo.
- **Netflix 11/2026:** a previsão (compra 580, R$ 59,90) e a cobrança real importada como compra comum ("NETFLIX ENTRETENIMENTO BARUERI", compra 606, R$ 44,90) contavam as duas no executado.

## 2. Decisões do titular

- **Natureza da compra**, nesta prioridade:
  1. PARCELADA (`total_parcelas > 1`);
  2. FIXA (`is_recorrente` + `item_despesa_id`);
  3. CATEGORIA (`categoria_cartao_id`);
  4. OUTROS.
- **Só a natureza CATEGORIA** consome limite, gasto e complemento da Categoria do Cartão. Parceladas e fixas são obrigações já contratadas: continuam com a `categoria_cartao_id` gravada (compatibilidade), sem efeito no orçamento.
- **Divergência aceita do Flask:** é melhoria do novo aplicativo. As telas do Flask continuam com a regra antiga.
- **Cobrança real:** substitui o **executado** da ocorrência do mês. O valor-base da recorrência não muda, e as próximas competências continuam previstas por ele.
- **Valor:** nunca concilia recorrência sozinho; o reconhecimento é pela descrição, e o valor só desempata.
- **Netflix 11/2026:** reconciliar por função oficial, reversível, com a compra absorvida inteira na auditoria. **Não executada em produção** neste pacote.
- **Fora do pacote:** a semântica global de "Total executado" e "Total previsto".

## 3. Correção

**Migration `20261208090000`** (nenhum dado existente é alterado):
- **`natureza_da_compra`:** a regra única. **`texto_cobranca`:** normalização das descrições (minúsculas, sem acento, só letras e números).
- **Tabelas novas** (RLS forçada, sem acesso direto):
  - `ocorrencia_recorrencia_cartao`: previsto, executado, a compra como era e a compra absorvida;
  - `recorrencia_apelido`: apelidos de cobrança por recorrência.
- **Leituras, todas pela regra única:**
  - `fatura_por_categoria`: novos grupos "Compras parceladas" e "Despesas fixas", status "Contratada", cada um com o próprio filtro de "Ver lançamentos" na tela de Cartões, sem alterar `cartoes.js`;
  - `gasto_categoria_fatura` (limites);
  - `lancamentos_fatura_por_categoria`: filtros `despesas_fixas` e `compras_parceladas`;
  - `contas_do_mes` e `faturas_do_mes`: o complemento do limite só conta compra variável;
  - `dashboard_resumo_tela`: o gasto das categorias só conta compra variável; o uso dos limites do cartão exclui parceladas e fixas.
- **`compras_da_fatura`:** devolve `valor_previsto`, `natureza` e `situacao_ocorrencia` (PREVISTA / CONFIRMADA).
- **Importação (`analisar_importacao_cartao` / `importar_fatura_cartao`):**
  - **Reconhecimento:** mesmo cartão, recorrência ativa paga no cartão, e o nome ou um apelido aparece como palavras inteiras na descrição normalizada.
  - **Mais de uma recorrência possível:** vale a que bate com o texto inteiro; depois, a de valor igual. Se ainda houver empate, a linha fica "revisar", com as candidatas.
  - **Conciliação por valor:** não alcança mais compra de recorrência.
  - **Previsão do mês ainda sem cobrança:** a linha a **realiza**. A compra prevista fica (identidade da recorrência), com valor, data e descrição do arquivo, e o previsto vai para `ocorrencia_recorrencia_cartao`.
  - **Previsão já realizada, ou em fatura paga ou consolidada:** a linha sai da efetivação, como antes.
  - **Categoria de Despesa:** a linha reconhecida usa a da recorrência.
- **Conciliação oficial:**
  - `conciliar_ocorrencia_recorrencia`: previsão + compra comum já lançada, no mesmo cartão e na mesma fatura aberta, com chave idempotente e versões;
  - `reverter_ocorrencia_recorrencia`: devolve a previsão como era e a compra absorvida com o mesmo id; recusada se a compra mudou depois ou se a fatura foi paga.
- **Apelidos:** `criar_apelido_recorrencia`, `remover_apelido_recorrencia` e `apelidos_da_recorrencia`. É recusado o apelido que reconheceria outra recorrência do cartão.
- **Reversão:** `supabase/reversao/20261208090000_cartao_despesas_fixas_anterior.sql`. Ela é recusada enquanto houver ocorrência reconciliada vigente ou apelido ativo.
- **Gerador:** `scripts/gerar_migration_cartao_despesas_fixas.py` monta a migration e a reversão a partir do texto vigente das funções nas migrations anteriores. A migration não é editada à mão: muda-se o gerador e roda-se de novo.
  - `--verificar` só compara, sem gravar.
  - `tests/test_gerador_migration_cartao_despesas_fixas.py` garante que os arquivos versionados são a saída exata (FIN-CARTAO-DESPESAS-FIXAS-02).

**Telas:**
- `despesas-adaptador.js`: natureza, previsto e situação da fixa.
- `frontend/static/js/despesas.js` (autorizado): a linha da fixa mostra "Previsto R$ X · diferença ±R$ Y", "· confirmado" ou "· cobrança ainda não importada". Sem os campos novos (Flask), a linha fica como antes.
- `importar-cartao-adaptador.js`: a realização conta como importada; recorrência e parcelada não aparecem como pendência de Categoria do Cartão.

## 4. Testes

- **`tests/test_supabase_cartao_despesas_fixas.py`** (42), em banco descartável com dados fictícios:
  - a regra de natureza (8 casos);
  - as seis leituras;
  - valor sozinho não concilia (Apple One × Netflix; ChatGPT × Claude);
  - descrições da administradora (5);
  - apelidos;
  - desempate e ambiguidade;
  - outro cartão;
  - análise que não grava;
  - realização na importação: uma ocorrência, previsto preservado, valor-base intacto, reimportação duplicada;
  - linha sem previsão;
  - fatura paga;
  - conciliação e reversão (a compra absorvida volta idêntica);
  - recusas;
  - segurança de funções e tabelas;
  - reversão e reaplicação da migration.
- **`web/tests/unit/fatura-blocos.test.mjs`** (+1): previsto × executado na tela, com o `despesas.js` real, incluindo a fixa sem os campos novos (Flask).
- **Ajustados à regra nova** (divergência aceita), em quatro arquivos:
  - `tests/test_supabase_cartoes_tela.py` (3 testes): a parcelada não consome a categoria;
  - `tests/test_supabase_recorrencia_cartao.py` (2 testes): a cobrança com valor diferente realiza a previsão; a definição vigente da análise passa a ser a da 1208;
  - `tests/test_supabase_compras_fatura_categoria_cartao.py` (1 teste): as colunas da 1207 continuam no começo.
  - `web/tests/e2e/cartoes_tela.spec.mjs` (2 testes): a parcela fica no grupo "Compras parceladas" e não consome o limite.
- **Regressão:**
  - Python: 2.201 aprovados, 2 pulados, 1 falha (a i3, dívida conhecida de `regularizar_historico`);
  - unitários 38/38;
  - E2E 115/116.
- **A falha de E2E restante** era `mobilidade_tela` (11 projeções em vez de 12). Ela falhava igual **sem** a migration 20261208090000.
  - Causa: o teste usava a data em UTC para o início do veículo, e o banco usa a de Brasília. Das 21h à meia-noite, no último dia do mês, o veículo nascia no mês seguinte.
  - Corrigida no FIN-CARTAO-DESPESAS-FIXAS-02: o teste usa a data de Brasília, como o banco.
- **Instabilidade:** `recorrencias_tela` teve um "Failed to fetch" de rede local numa rodada e passou ao repetir.

## 5. Ensaio (cópia fiel e descartável da produção)

| Conferência | Resultado |
|---|---|
| Cópia | Idêntica à produção |
| Migration (md5 `830e53e2…4a9edf`) | Só as 2 tabelas novas (vazias), funções, permissões e o registro da versão; nenhum dado existente mudou |
| Black 11/2026 | Igual: 51 compras / R$ 4.312,25 nas categorias, 38 / R$ 2.882,55 em Outros, executado R$ 7.194,80 |
| Visa: Assinaturas (Cartões e limite) | R$ 497,40 "Estourado" → **R$ 227,70** (4 compras, disponível R$ 172,30) |
| Visa: grupo "Despesas fixas" | 4 compras, R$ 329,60, "Contratada"; "Sem Categoria do Cartão" passa de 10 para 9 (sai a Apple One) |
| Visa: previsto na lista de Despesas | R$ 2.595,45 → **R$ 2.767,75** (igual ao detalhe) |
| Detalhe em Despesas | Blocos iguais; cada fixa com "Previsto R$ X · cobrança ainda não importada" |
| Dashboard | Uso dos limites: Black igual (R$ 7.194,80); Visa R$ 2.595,45 → R$ 2.265,85. Assinaturas (todos os cartões) R$ 1.945,55 → R$ 1.675,85 |
| Simulação das 15 linhas do diagnóstico | ChatGPT 109,90 → ChatGPT (realiza a previsão de 99,90); CLAUDE.AI, ANTHROPIC*CLAUDE, OPENAI*CHATGPT, NETFLIX.COM reconhecidas; APPLE.COM/BILL sem vínculo (precisa de apelido); recorrência do Visa no Black não reconhecida |
| Netflix 11/2026 conciliada (só na cópia) | Uma ocorrência: previsto 59,90, executado 44,90, diferença −15,00; Fixas R$ 314,60; Assinaturas R$ 182,80; executado da fatura **R$ 2.535,55**; previsto da lista R$ 2.752,75 |
| Reversão na cópia | Compras e faturas idênticas às de antes da conciliação |

## 6. Pendências

- **Netflix 11/2026 em produção:** executar `conciliar_ocorrencia_recorrencia(1, 580, …, 606, …)` só com autorização, depois da publicação.
- **Apelidos pela tela:** as funções existem, mas a tela de Recorrências (arquivo original do Flask) não tem o campo. Até lá, o apelido é cadastrado pela função. Exemplo: Apple One → "APPLE.COM/BILL". Não há como saber qual das 5 "Apple.Com/Bill" do Black é qual; não inferir.
- **Vincular uma linha a uma recorrência escolhida na importação:** continua "em migração".
- **Previsto × executado (próximo contrato; impede considerar encerrada a conciliação):**
  - a previsão da recorrência ainda sem cobrança real continua contando no **executado** da fatura e no **valor a pagar** (no Visa 11/2026, R$ 269,70 de ChatGPT, Claude e Apple One);
  - o previsto da fixa no cabeçalho da fatura usa o valor da compra (executado).
  - Objetivo do próximo pacote: a cobrança não importada permanece como previsão e só vira executada quando conciliada.
- **Parcelas:** previsto = executado = valor da parcela; conciliar parcela importada com valor diferente fica fora.
- **Telas do Flask:** continuam somando fixas e parceladas nas categorias (divergência registrada).
