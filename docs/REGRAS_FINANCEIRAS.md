# Regras Financeiras do Sistema

Regras globais e por módulo que governam o comportamento do Controle Financeiro.

Última atualização: 2026-08-19 (CORE-ESTORNO-UI-1)

---

## Regras Globais de Proteção Financeira

Estas regras são invioláveis. Nenhuma funcionalidade nova pode quebrá-las.

1. **Dados financeiros executados não são alterados silenciosamente.** Qualquer mudança em parcelas ou contas já efetivadas exige bloqueio ou auditoria explícita.

2. **Parcelas pagas são preservadas.** Recálculos, edições estruturais e amortizações afetam apenas o trecho futuro.

3. **Contas pagas, baixadas, conciliadas ou efetivadas bloqueiam recálculos** que alterem seu valor ou competência.

4. **Recálculos atingem apenas parcelas ou contas pendentes.** O passado é soberano.

5. **Exclusões são permitidas apenas sem execução financeira.** Financiamento com parcela paga, consórcio contemplado, cartão com fatura paga — todos bloqueiam exclusão total.

6. **Cadastros mestres compartilháveis não são apagados automaticamente.** `ItemDespesa` usado por financiamento, recorrência ou cartão permanece mesmo após remoção da entidade principal.

7. **Alterações estruturais preservam rastreabilidade.** Amortizações, ajustes de saldo e recálculos são registrados com auditoria.

8. **Divergência entre simulação e extrato real usa marcos de ajuste documentados.** O sistema não reescreve o passado; registra a diferença e recalcula o futuro.

9. **Frontend não exibe botão visível sem função real**, salvo marcado explicitamente como "em desenvolvimento".

10. **Backend é soberano para regras financeiras.** Frontend apenas exibe dados já calculados e coleta entrada do usuário.

---

## Regras da Tela Despesas (Regra-Mãe)

A tela Despesas representa a **fatura mensal consolidada** da vida financeira. Tudo no sistema converge para essa regra.

**O que entra em Despesas**:
- Todas as `Conta` da competência selecionada
- Fatura de cartão de crédito (como `Conta` única por cartão)
- Parcelas de financiamento
- Despesas correntes e recorrentes

**O que não entra**:
- Lançamentos individuais de cartão
- Simulações
- Planejamentos sem execução
- Histórico bruto

**Regra soberana de fatura**:
- `status_pagamento == 'Pago'` → usar `total_executado` (soma de `LancamentoAgregado`)
- `status_pagamento == 'Pendente'` → usar `total_previsto` (soma de `OrcamentoAgregado`)

Esta regra não tem exceções.

**Competência**:
- Sempre definida explicitamente pelo usuário ou pelo sistema no momento da criação
- Nunca inferida de datas de transação, fechamento ou vencimento

---

## Regras de Receitas

- Receita prevista (`ReceitaOrcamento`) ≠ receita realizada (`ReceitaRealizada`)
- Valor realizado permanece zerado até efetivação explícita
- Pendências de competências anteriores permanecem visíveis até confirmação
- Confirmação de pendência preserva a competência original (não usa a data da confirmação)
- Contemplação de consórcio sem efetivação bancária aparece como receita prevista

**Recebimento protegido (CORE-RECEITA-1)**:
- `POST /api/receitas/realizadas` é o fluxo oficial de recebimento: exige `conta_bancaria_id`, cria `ReceitaRealizada` e `MovimentoFinanceiro` (`CREDITO`, `origem='RECEITA'`) na mesma transação.
- Receita sem conta bancária informada nem herdada da fonte (`ItemReceita.conta_bancaria_id`) é rejeitada com HTTP 400 — recebimento sem conta não existe.
- Duplicidade de recebimento é bloqueada: uma `ReceitaRealizada` não pode ter mais de um `MovimentoFinanceiro` de `origem='RECEITA'`.
- `PUT /api/receitas/realizadas/{id}` não pode alterar `valor_recebido`, `conta_bancaria_id` ou `data_recebimento` de uma receita que já tem movimento vinculado — retorna HTTP 400 com mensagem "Receitas realizadas só podem ser alteradas por fluxo financeiro próprio". Campos neutros (`descricao`, `observações`, `item_receita_id`/competência) continuam editáveis.
- Exceção intencional: receita **sem** movimento vinculado ainda (ex.: contemplação de consórcio pendente, ver regra acima) pode ser completada via `PUT` — nesse caso o movimento é criado nessa chamada, preservando o fluxo de "consolidar receita pendente" já existente no frontend.
- `DELETE /api/receitas/realizadas/{id}` é bloqueado (HTTP 409) se existir `MovimentoFinanceiro` vinculado — receita recebida preserva histórico financeiro; correção exige estorno (`CORE-ESTORNO-2`, ver abaixo).

**Estorno de recebimento (CORE-ESTORNO-2)**:
- `POST /api/receitas/realizadas/{id}/estornar` estorna uma receita realizada. Não apaga `ReceitaRealizada` nem o `MovimentoFinanceiro` original (`origem='RECEITA'`) — cria movimento compensatório de `DEBITO` com `origem='ESTORNO_RECEITA'`, mantendo ambos os movimentos vinculados ao mesmo `receita_realizada_id` para rastreabilidade.
- `ReceitaRealizada` não tem campo de status próprio (a existência do registro já significa "recebido" desde o CORE-RECEITA-1); o estado "estornada" é calculado dinamicamente pela presença de um `MovimentoFinanceiro` com `origem='ESTORNO_RECEITA'` vinculado — nenhum campo novo foi adicionado ao model.
- Exige `motivo` e `data_estorno` (HTTP 400 se ausentes); registra o motivo em `observacoes` sem apagar o conteúdo anterior.
- Bloqueia estorno duplicado (HTTP 409) e receita sem movimento original vinculado (HTTP 422, ex.: contemplação de consórcio ainda pendente de confirmação).
- **UI (CORE-ESTORNO-UI-1)**: botão "Estornar recebimento" na listagem de receitas (`frontend/static/js/receitas.js`), visível apenas quando `receita.status === 'REALIZADA'` e `receita.realizada_id` está definido (linha agregada de múltiplas realizações não mostra o botão, evitando ambiguidade). Modal próprio (`modal-estornar-receita`) com aviso, data e motivo obrigatórios; frontend só coleta e envia — todo bloqueio (409/422) é decidido pelo backend.

**Saneamento de receitas históricas (DATA-HYGIENE-RECEITA-1)**:
- Script `scripts/data_hygiene_receitas_historicas.py` audita `ReceitaRealizada` sem `conta_bancaria_id` e sem `MovimentoFinanceiro` vinculado, no banco real da aplicação (`DATABASE_URL`, não em arquivos SQLite legados).
- Classificação é sempre determinística — nenhuma conta bancária é inferida por heurística (única conta existente, conta mais usada, descrição parecida, etc.). Só é aceita conta explícita em `ItemReceita.conta_bancaria_id` da fonte vinculada à receita.
- `REGULARIZAR_MOVIMENTO`: conta explícita + valor válido (`> 0`) → cria `MovimentoFinanceiro` via `ContaBancariaService.criar_movimento()`.
- `REABRIR_COMO_PENDENTE`: `valor_recebido` ausente ou `<= 0` → exclui a `ReceitaRealizada` (não há evidência de recebimento real, mesmo com `data_recebimento` preenchida — o campo é `NOT NULL` no schema, então "sem data" não ocorre em dado não corrompido).
- `PENDENTE_DECISAO_USUARIO`: valor válido mas conta não pode ser inferida com segurança → nenhuma alteração automática.
- `BLOQUEADO_INCONSISTENTE`: já existe `MovimentoFinanceiro` vinculado apesar de `conta_bancaria_id` ausente na receita → investigação manual, sem correção automática.
- Backup obrigatório (`BackupService.executar_backup_manual()`, PostgreSQL) antes de qualquer escrita; nenhum backup é criado se não houver ação segura a aplicar.

**Atomicidade de transações (TX-ATOMIC-1)**:
- `PerfilFinanceiroService.obter_ou_criar_perfis_iniciais()` usa apenas `db.session.flush()`, nunca `db.session.commit()` — esse método é acionado indiretamente por praticamente qualquer leitura/escrita escopada por perfil (`obter_perfil_ativo_id()`, `condicao_perfil()`, `aplicar_perfil_query()`, e por consequência `ContaBancariaService.criar_movimento()`), então um `commit()` ali finalizaria prematuramente qualquer transação maior em andamento — quebrando a garantia de atomicidade de que CORE-RECEITA-1, CORE-SALDO-1A/1B e futuros fluxos de estorno dependem.
- A persistência da criação idempotente dos perfis padrão (Pessoal/Empresa) fica a cargo do hook global `commit_pending_session` (`backend/app.py`, `teardown_request`), que comita ao fim de qualquer requisição HTTP bem-sucedida com mudanças pendentes na sessão. Rotas de escrita continuam responsáveis pelo próprio `commit()`/`rollback()` explícito; o hook cobre apenas o que sobrar pendente (tipicamente rotas GET).
- Descoberto durante o diagnóstico de rollback do `DATA-HYGIENE-RECEITA-1`.

---

## Regras de Cartões

**Fatura**:
- Fatura paga → valor = soma dos `LancamentoAgregado` (executado)
- Fatura pendente → valor = soma dos `OrcamentoAgregado` por Categoria do Cartão (previsto)

**Pagamento de fatura (CORE-FATURA-1)**:
- `valor_executado` é **sempre recalculado** a partir dos `LancamentoAgregado` imediatamente antes do pagamento — nunca usa cache.
- Fatura já paga bloqueia segunda baixa (`ValueError`); rota HTTP retorna 409.
- Movimento bancário criado via `ContaBancariaService.criar_movimento()` com `origem='FATURA'`.
- `db.session.commit()` controlado pelo chamador (rota), não pelo service.

**Estorno de pagamento de fatura (CORE-ESTORNO-3)**:
- Fatura de cartão é uma `Conta` com `is_fatura_cartao=True`, paga pela mesma rota genérica de despesas (`POST /api/despesas/{id}/pagar`). O estorno reaproveita, pelo mesmo motivo, `POST /api/despesas/{id}/estornar-pagamento` — a rota detecta `is_fatura_cartao` e usa `origem='ESTORNO_FATURA'` em vez de `origem='ESTORNO_DESPESA'`. Não existe rota separada em `cartoes.py` para isso.
- Não apaga o movimento `DEBITO` original. Cria movimento compensatório `CREDITO` (`origem='ESTORNO_FATURA'`) e volta `status_pagamento` para `'Pendente'`.
- **Não altera** `status_fatura` (fechamento/consolidação, controlado por `POST /cartoes/{id}/faturas/{competencia}/consolidar`), `valor_executado`, `LancamentoAgregado`, `compra_id` ou `categoria_cartao_id` — o estorno é puramente financeiro/bancário.
- Bloqueia estorno de fatura não paga (HTTP 409), sem movimento vinculado (HTTP 422) e estorno duplicado (HTTP 409).
- **UI (CORE-ESTORNO-UI-1)**: fatura de cartão é exibida e paga na tela de Despesas, não em Cartões — o botão "Estornar pagamento" reaproveita o mesmo modal do estorno de despesa comum (CORE-ESTORNO-1), trocando dinamicamente título/rótulo/aviso quando `despesa.is_fatura_cartao === true` (`abrirModalEstorno()` em `frontend/static/js/despesas.js`). Mesmo endpoint (`POST /api/despesas/{id}/estornar-pagamento`) para os dois casos.

**Idempotência de lançamentos recorrentes (CORE-CARTAO-1)**:
- Lançamentos recorrentes de cartão usam `compra_id` UUID5 determinístico: `uuid5(NS, f'{item_despesa_id}-{mes_fatura.isoformat()}')`.
- Namespace fixo (`7f3a1b2c-...`) exclusivo para recorrências — não colide com UUID v4 da importação.
- Deduplicação primária por `compra_id`; fallback para registros legados (sem `compra_id`) que preenchem o campo retroativamente.
- Garantia: 1 recorrência = 1 lançamento por mês, independente de quantas vezes `gerar_lancamentos_cartao_recorrente()` é chamado.

**Categoria do Cartão × Categoria da Despesa**:
- **Categoria do Cartão** (`CategoriaCartao`): organiza internamente a fatura do cartão
- **Categoria da Despesa** (`Categoria`): organiza o orçamento geral e o fluxo de despesas
- São independentes. Um lançamento pode ter as duas preenchidas ou apenas uma.

**Lançamentos da fatura**:
- Todo lançamento é `LancamentoAgregado`, independentemente da origem (recorrência ou manual)
- Editável via `PUT /api/cartoes/lancamentos/{id}`
- Categoria do Cartão obrigatória no fluxo de importação

**Status de limite por Categoria do Cartão**:
- Normal: utilizado < 80% do limite
- Atenção: utilizado entre 80% e 100%
- Estourado: utilizado > 100%
- Revisar: sem limite definido

---

## Regras de Importação de Cartão

**Descrição**:
- `descricao_original`: texto bruto do arquivo, imutável após importação
- `descricao_exibida`: editável pelo usuário, usada para exibição
- Reconhecimento futuro usa `descricao_original` como assinatura, não `descricao_exibida`

**Reconhecimento de recorrência**:
- Exige **mesmo cartão** como candidato (lançamentos de outro cartão não sugerem recorrência)
- Assinatura = descrição original + valor + cartão/competência

**Idempotência**:
- Garantida por `compra_id` (UUID v4) + `numero_parcela`
- Reimportação do mesmo arquivo não duplica lançamentos

**Fluxo** (IMPORT-TRIAGEM-1 + IMPORT-TRIAGEM-2):
1. **Triagem** — decidir se cada lançamento vira despesa, ignorar ou revisar. Categoria do Cartão NÃO é resolvida nesta fase.
2. **Confronto** — reconhecimento fuzzy executado automaticamente pelo backend no `/analisar`. Resultado entregue inline em cada linha (`reconhecimento_status`, `reconhecimento_score`, `reconhecimento_tipo`, `reconhecimento_match`). Chamada separada ao `/reconhecer` não é mais necessária no fluxo unificado.
3. **Classificação** — confirmar Categoria da Despesa. Somente após isso a Categoria do Cartão é resolvida pelo mapeamento existente.
4. **Persistência** — criação do lançamento. Ausência de Categoria do Cartão gera aviso, não bloqueia.

**Categoria do Cartão**:
- É agrupamento opcional da fatura. Não deve bloquear triagem nem importação.
- Ausência gera aviso padronizado: `MSG_CATEGORIA_DESPESA_SEM_CATEGORIA_CARTAO`
- Resolvida automaticamente via mapeamento `Categoria da Despesa → Categoria do Cartão`

---

## Regras de Financiamentos

### Composição do total

```
total_previsto = amortização + juros + seguro + taxa_administrativa
```

Nenhum componente pode ser omitido do extrato ou da visualização.

### Seguro habitacional

**Modo fixo/manual**:
- Seguro = valor fixo da vigência ativa no mês
- Definido pelo usuário por período de vigência

**Modo estimado DFI+MIP**:
- DFI = base_DFI × fator_DFI (base pode ser original ou segurada)
- MIP = juros_contratuais × fator_MIP da faixa etária corrente
- Faixa etária determinada por competência configurável
- Todos os cálculos usam o helper central de seguro (único ponto de verdade)

### Modo SAC + TR

- Ativado quando `sistema_amortizacao = SAC` e `indexador_saldo = TR`
- `modo_calculo_financiamento` permanece apenas como compatibilidade transitória
- Taxa mensal = taxa_nominal_anual / 12
- TR mensal aplicada ao saldo: `saldo_corrigido = saldo × (1 + TR_mensal)`
- Quota de amortização = `saldo_corrigido / parcelas_restantes`
- Juros = `saldo_corrigido × taxa_mensal`
- TR ausente para a competência bloqueia a geração (erro explícito)
- TR oficial vem de `indice_tr_mensal`; `IndexadorMensal` não alimenta este motor
- Seguro calculado pelo helper central após correção

### Ajuste de saldo devedor real

- Preserva todas as parcelas do passado (pagas ou não)
- Recalcula apenas parcelas futuras (a partir do mês seguinte ao ajuste)
- Registra auditoria: saldo informado, saldo calculado, diferença, data do ajuste
- Bloqueia se houver conta efetivada no trecho a ser recalculado

### Amortização extraordinária

- Não altera parcelas pagas nem contas efetivadas
- Recalcula saldo devedor e parcelas futuras
- Seguro recalculado pelo helper central para cada parcela futura
- Comportamento padrão: reduz valor da prestação, mantém prazo
- Opção de reduzir prazo mantendo prestação: pendência futura (FIN-AMORT-OPCAO-1)

### Documentos e conferência CAIXA

- Documentos do financiamento usam metadados no banco e arquivo físico em `data/uploads/financiamentos`.
- Documentos podem ser vinculados opcionalmente a parcela, amortização, ajuste de saldo, competência, ano-base ou data.
- Conferências CAIXA registram valores reais digitados pelo usuário e comparam com valores simulados do cronograma.
- Diferenças são calculadas como `valor_real - valor_simulado`.
- Upload, exclusão e conferência documental não alteram saldo, parcelas, pagamentos, amortizações, seguro ou cronograma.
- Ajuste de saldo devedor continua sendo ação separada e explícita.
- Leitura automática/OCR de demonstrativos não faz parte da regra atual.

### Conferência de quitação

- A conferência de quitação registra o valor oficial informado pelo banco e compara com o valor simulado pelo app.
- A diferença é calculada como `valor_oficial_banco - valor_simulado_app`.
- Documento de proposta, boleto ou demonstrativo pode ser vinculado opcionalmente.
- A conferência de quitação não marca financiamento como quitado, não baixa parcelas, não cria conta de pagamento, não cancela parcelas futuras e não altera saldo.
- Quitação operacional é MVP separado.

### Exclusão

Bloqueada quando existir qualquer dos seguintes:
- Parcela com `status_pagamento == 'Pago'`
- `Conta` efetivada vinculada
- `FinanciamentoAmortizacaoExtra` registrada
- Ajuste de saldo registrado
- Movimentação financeira vinculada

### ItemDespesa e Financiamento

- `ItemDespesa` nunca é excluído automaticamente (é cadastro mestre)
- Troca de `item_despesa_id` bloqueada com execução financeira
- Sem execução: contas pendentes sincronizadas automaticamente após troca

---

## Regras de Baixa / Pagamento de Despesas (CORE-BAIXA-1)

- **Conta bancária é obrigatória** para registrar o pagamento de qualquer despesa que impacte saldo.
- **Despesa paga não pode ser baixada novamente.** Tentativa retorna HTTP 409.
- **A baixa é transacional.** Status pago, movimento financeiro e atualização de saldo ocorrem juntos — ou nada é persistido.
- **Sincronização com financiamento** ocorre dentro da mesma transação antes do commit.
- `MovimentoFinanceiro` criado na baixa sempre tem `conta_bancaria_id` preenchido e `origem='DESPESA'`.
- O hook de financiamento foi movido para antes do `commit` — se falhar, a baixa é revertida.

**Proteção de saldo contra edição e exclusão (CORE-SALDO-1A/1B)**:
- **Pagamento só pelo fluxo oficial** (`POST /despesas/<id>/pagar`). `PUT /despesas/<id>` com `pago`, `status_pagamento`, `data_pagamento` ou `valor_pago` retorna HTTP 400. Edição comum nunca cria `MovimentoFinanceiro`.
- **Despesa paga não pode ser excluída.** `DELETE /despesas/<id>` retorna HTTP 409 se `status_pagamento == 'Pago'`.
- **Despesa com movimento vinculado não pode ser excluída** diretamente. Remoção exige estorno controlado via `POST /despesas/<id>/estornar-pagamento`.

**Estorno de pagamento de despesa (CORE-ESTORNO-1)**:
- `POST /despesas/<id>/estornar-pagamento` — payload: `{ data_estorno, motivo }`.
- **Movimento original preservado.** O débito original não é apagado.
- **Movimento compensatório criado** com `tipo='CREDITO'`, `origem='ESTORNO_DESPESA'`, `conta_id` vinculado à despesa.
- **Despesa reaberta como Pendente** — `status_pagamento='Pendente'`, `data_pagamento=NULL`, `valor_pago=NULL`.
- **Motivo é obrigatório** (HTTP 400 sem ele). Registrado em `Conta.observacoes`.
- **Saldo bancário recalculado** automaticamente após criação do movimento compensatório.
- **Estorno duplicado bloqueado** — se já existe `MovimentoFinanceiro` com `origem='ESTORNO_DESPESA'` vinculado à despesa, retorna HTTP 409.
- **Estorno de despesa pendente bloqueado** — HTTP 409.
- **Movimento original ausente** — HTTP 422 com mensagem descritiva.
- Operação transacional: se falhar, nenhuma alteração persiste.
- Mesmo padrão aplicado em **CORE-ESTORNO-2** (receita), **CORE-ESTORNO-3** (fatura de cartão) e **CORE-ESTORNO-4** (parcela de financiamento), ver seções específicas abaixo.
- Dívida técnica: campo `movimento_original_id` em `MovimentoFinanceiro` para rastreabilidade explícita.

**Pagamento de parcelas de financiamento (CORE-SALDO-1C)**:
- `POST /financiamentos/parcelas/<id>/pagar` requer `conta_bancaria_id` e `data_pagamento` (HTTP 400 sem eles).
- Cria `MovimentoFinanceiro` com `tipo='DEBITO'`, `origem='FINANCIAMENTO'`, `financiamento_parcela_id` preenchido.
- Saldo da conta bancária é debitado e recalculado automaticamente.
- **Parcela já paga retorna HTTP 409** — bloqueio de duplicata.
- **Parcela com despesa vinculada pendente retorna HTTP 409** — o pagamento deve ocorrer pelo fluxo de Despesas.
- Transação atômica: se criação do `MovimentoFinanceiro` falhar, o status da parcela é revertido.
- `MovimentoFinanceiro.financiamento_parcela_id` rastreia qual parcela originou o movimento (coluna adicionada em `9b8a09ecc52f`).

**Estorno de pagamento direto de parcela (CORE-ESTORNO-4)**:
- `POST /financiamentos/parcelas/<id>/estornar-pagamento` estorna apenas pagamentos feitos pelo fluxo direto de financiamento (`MovimentoFinanceiro.origem='FINANCIAMENTO'`). Não apaga o movimento original; cria `CREDITO` compensatório (`origem='ESTORNO_FINANCIAMENTO'`) e volta a parcela para `status='pendente'`.
- **Parcela com despesa vinculada paga é bloqueada (HTTP 409)** — orienta a estornar pelo fluxo de Despesas (`CORE-ESTORNO-1`), simétrico ao bloqueio de pagamento duplicado do CORE-SALDO-1C. Preserva a regra de que despesa e parcela não podem "brigar" sobre quem é dono do pagamento.
- **Só a parcela paga mais recente (maior `numero_parcela` entre as pagas) pode ser estornada** — o sistema permite pagar parcelas fora de ordem sem validação de sequência, então estornar uma parcela do meio corromperia a cadeia de `saldo_devedor_apos_pagamento`. Existe parcela paga posterior → HTTP 409.
- Recompõe `Financiamento.saldo_devedor_atual` com o `saldo_devedor_apos_pagamento` da parcela anterior (`numero_parcela - 1`), ou `valor_financiado` se for a primeira parcela — mesma lógica de fallback já usada em `Financiamento.to_dict()`.
- Não altera amortizações extraordinárias, ajustes de saldo, documentos/conferências CAIXA, simulação de quitação nem cronograma futuro em massa.
- Bloqueia estorno duplicado (HTTP 409) e parcela sem movimento vinculado (HTTP 422).
- **UI (CORE-ESTORNO-UI-1)**: botão "Estornar pagamento" na coluna de ações do cronograma de parcelas (`renderizarTabelaParcelas()` em `frontend/static/js/financiamentos.js`), visível sempre que `parcela.status === 'pago'`. O payload da parcela não expõe se o pagamento foi direto ou via despesa vinculada nem se já existe estorno — o frontend não infere essas regras; o backend bloqueia com HTTP 409 e mensagem clara quando aplicável.

---

## Regras de Contas Bancárias

1. `saldo_atual` é sempre derivado: `saldo_inicial + Σ(créditos) - Σ(débitos)`
2. Toda alteração de saldo gera `MovimentoFinanceiro` (sem exceção)
3. Ajuste manual é lançamento explícito — aparece no extrato, auditável
4. Extrato é a fonte de verdade do saldo
5. Transferência entre contas gera 2 movimentos atômicos (débito na origem, crédito no destino)

**Conferência read-only de saldo (CORE-SALDO-1D)**:
- `GET /api/contas/<id>/conferir-saldo` — compara `saldo_atual` persistido com `saldo_inicial + Σcréditos − Σdébitos`.
- **Read-only**: não altera `saldo_atual`, não cria movimentos, não corrige divergências automaticamente.
- `divergencia = saldo_atual − saldo_calculado`; `consistente = abs(divergencia) <= 0.01`.
- Divergência é informativa: correção operacional requer ajuste de saldo explícito pelo usuário (CORE-SALDO-2 — pendência futura).
- Pendência futura: **CORE-SALDO-2 — Ajuste assistido de divergência de saldo bancário**.

---

## Regras de Recorrências

- Despesas recorrentes com prazo: termo oficial (não "recorrência parcelada" ou "recorrência com prazo")
- Parcelas pagas são protegidas contra recálculos
- Encerramento por quantidade de parcelas ou data final (configurável)
- Débito automático vinculável a conta bancária específica
- Vínculo com cartão e Categoria do Cartão disponível

---

## Regras de Veículos / Mobilidade

- Cenário ativo persistido via backend (`data/mobilidade_cenario_ativo.json`)
- Efetivação atômica: guard `status == 'PREVISTA'` + rollback em caso de falha
- Meio cartão → `LancamentoAgregado` via `CartaoService.adicionar_lancamento()`
- Demais meios → `ItemDespesa(tipo='Simples')` + `Conta`
- Mobilidade é módulo/origem do lançamento, não Categoria da Despesa genérica
- Despesas geradas por Mobilidade usam categorias sistêmicas granulares por natureza do gasto
- Categorias sistêmicas são buscadas por `codigo_sistema`, não por nome ou ID fixo
- Categoria do Cartão continua fora do escopo da classificação sistêmica de Mobilidade

---

## Regras de UX / Frontend

- Botão visível = função real implementada
- Se funcionalidade incompleta: ocultar o botão ou marcar como "em desenvolvimento"
- Ícones monocromáticos com `currentColor` (sem emoji em botões funcionais)
- Cores vermelho/verde apenas para status objetivo (Pago/Pendente), nunca como julgamento
- Linguagem descritiva e neutra: "Você gastou R$ 300 além do previsto" (não "Você gastou demais")
- Colunas de ação: slots fixos, botões desabilitados quando indisponível (não ausentes)

---

## Filosofia Central

O sistema descreve a realidade financeira. Não prescreve comportamento.

- "Você gastou R$ 300 além do previsto" ✅
- "Você gastou demais" ❌

Previsto vs Executado são **ambos legítimos**. A diferença é informação, não falha.
