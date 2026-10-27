# FIN-FINANCIAMENTOS-MOTOR-1 — Motor de Financiamentos SAC/TR da Caixa (Flask → Supabase)

**Estado:** etapas A a E implementadas e testadas contra o próprio Flask.
- **A:** motor SAC/TR da Caixa.
- **B:** cadastro e edição.
- **C:** amortização extraordinária.
- **D:** vigências de seguro, ajuste de saldo, regeneração e exclusão seguras.
- **E:** SAC sem TR (com ou sem outro índice), PRICE, SIMPLES e simulação de quitação.
- Também: registro explícito de parcelas históricas.

Fora deste contrato ficam documentos e conferências da Caixa (FIN-DOCUMENTOS-2).

**Restrições cumpridas:**
- Migration **só local**.
- Sem commit, push ou publicação.
- `gastos.db` lido só com `mode=ro&immutable=1` (tamanho e mtime conferidos).
- Nenhum dado real alterado.

## 1. Diagnóstico direcionado

**O contrato real** (`gastos.db`, leitura):
- **Configuração:**
  - gravado como `SAC` + índice `TR`, `modo_calculo_financiamento = 'padrao'`, `modo_taxa_mensal = 'efetiva_equivalente'`, taxa 9,79% a.a.;
  - as 420 parcelas foram geradas por um motor **anterior** ao SAC/TR da Caixa: taxa efetiva equivalente e **sem correção pela TR** (`valor_atualizacao_monetaria = 0`);
  - o Flask de hoje trata SAC+TR como motor Caixa (nominal/12, TR mês a mês). Portanto, **regenerar ou amortizar o contrato real no próprio Flask mudaria todas as parcelas pendentes**.
- **Parcelas:**
  - 22 pagas sem movimento bancário, todas com data de pagamento igual ao vencimento;
  - 398 pendentes;
  - 1 amortização (30/07/2025, reduzir parcela);
  - 9 vigências de seguro, com duas na mesma competência 2026-03 (249 e 239; a parcela usa 249).
- **Despesas pendentes:** as 398 estão **R$ 1,00 acima** do previsto da parcela. A causa foi identificada e reproduzida em teste: é o recálculo só do seguro do Flask (§5, M8).
- Achados só registrados; nada foi alterado. Ver §7.

**Supabase de teste:**
- tabela de TR `indice_tr_mensal` com 25 competências (2024-05 a 2026-05);
- sem contratos;
- `financiamento_parcela` sem unicidade por número;
- `movimento_financeiro` também aponta para a parcela (`financiamento_parcela_id`, do pagamento direto antigo).

## 2. Funcionalidades implementadas (migration `20261123090000`)

| Operação | Rota original da tela | RPC |
|---|---|---|
| Cadastro com geração das parcelas e despesas (SAC/TR) | `POST /api/financiamentos` | `criar_financiamento(perfil, dados, chave)` |
| Amortização extraordinária (reduzir parcela / prazo) | `POST /api/financiamentos/<id>/amortizacao-extra` | `registrar_amortizacao_extra(perfil, id, dados, chave)` |
| Regeneração (só sem execução financeira, como o Flask) | `POST /api/financiamentos/<id>/regenerar-parcelas` | `regenerar_parcelas_financiamento(perfil, id)` |
| Exclusão segura (só sem execução financeira) | `DELETE /api/financiamentos/<id>` | `excluir_financiamento(perfil, id)` |
| Parcelas históricas (quitadas antes do sistema) | — (sem rota no Flask) | `registrar_parcelas_historicas(perfil, id, {ate_parcela}, chave)` |
| Edição (estrutural só sem execução; nome, produto, situação e item sempre) | `PUT /api/financiamentos/<id>` | `atualizar_financiamento(perfil, id, dados, chave)` |
| Vigência de seguro nova, com recálculo só do seguro | `POST /api/financiamentos/<id>/vigencias-seguro` | `adicionar_vigencia_seguro(perfil, id, dados, chave)` |
| Ajuste auditável do saldo devedor | `POST /api/financiamentos/<id>/ajustar-saldo` | `ajustar_saldo_devedor(perfil, id, dados, chave)` |
| Simulação de quitação (só leitura) | `POST /api/financiamentos/<id>/simular-quitacao` | `simular_quitacao(perfil, id, dados)` |

**Modalidades:**
- **Caixa SAC/TR:** SAC com índice TR, ou o modo técnico antigo `caixa_sac_tr`.
- **SAC:** sem índice ou com outro índice de `indexador_mensal`, em %.
- **PRICE e SIMPLES.**
- Todas passam por cadastro, edição, regeneração, amortização e ajuste.

**Como é ligado:**
- O adaptador `web/src/js/financiamentos-adaptador.js` liga as rotas da tela original. Mapeia `SISTEMA_FLASK` para 409, `NAO_ENCONTRADO` para 404 e quem só lê para 403.
- Pagamento e estorno continuam pelo motor de Despesas do FIN-CONTRATOS-2. **Não foi criado outro mecanismo de pagamento.**

**Arredondamento:**
- igual ao `Decimal` do Flask: cada operação é arredondada a **28 dígitos significativos**, pela regra do par (`financeiro.fin_r`, `fin_div`, `fin_pow_int`);
- gravação em `numeric(10,2)` e `numeric(12,2)`, como o Flask no PostgreSQL;
- isso foi necessário: com 30 casas decimais, um meio centavo exato (quota 20.856,255 no prazo de 24 meses) dava 1 centavo de diferença.

**Fórmulas do SAC/TR** (iguais às do Flask):
- taxa mensal = nominal / 100 / 12;
- quota inicial = financiado / prazo;
- a cada parcela:
  - `tr` = TR da competência do vencimento (sem índice, erro `TR_AUSENTE`);
  - quota = quota × (1 + tr);
  - saldo corrigido = saldo × (1 + tr);
  - juros = saldo corrigido × taxa;
  - amortização = mín(quota, saldo corrigido);
  - total = amortização + juros + seguro + taxa administrativa;
  - saldo final = saldo corrigido − amortização;
- vencimentos por mês somado de forma acumulada (como `relativedelta`).

**Seguro:**
- fixo = vigência do vencimento (empate de competência: a cadastrada primeiro);
- estimado = DFI (base × fator) + MIP (juros × fator da faixa etária), arredondado; a estrutura de faixas MIP foi mantida.

**Outras modalidades:**
- **SAC:** juros sobre o saldo corrigido pelo índice do mês; amortização constante.
- **PRICE:** prestação = PV·i·(1+i)ⁿ / ((1+i)ⁿ − 1).
- **SIMPLES:** juros fixos sobre o financiado.
- Taxa mensal efetiva equivalente ou nominal/12.
- Amortização nessas modalidades (como o Flask):
  - taxa **sempre** efetiva equivalente;
  - sem índice;
  - PRICE refaz a prestação a cada parcela;
  - reduzir prazo mantém a amortização da 1ª pendente.

**Amortização no SAC/TR** (`_recalcular_apos_amortizacao`):
- novo saldo = base − valor;
- quota base:
  - reduzir parcela = novo saldo / nº de pendentes;
  - reduzir prazo = amortização da 1ª pendente / (1 + tr);
- recalcula **só** as pendentes elegíveis a partir da data;
- atualiza o estado do contrato como o Flask: saldo atual, regime, amortização mensal, prazo remanescente, parcela e data base.

## 3. Regras de integridade (§9 de FIN_CONTRATOS_3)

1. **Despesa paga ou com qualquer movimento, inclusive estornado,** nunca é alterada pelo motor (`fin_gravar_despesa`, `fin_parcela_elegivel`).
2. **O status da despesa nunca é copiado da parcela.** O motor só grava valor, vencimento e competência das despesas pendentes. O status muda só por pagamento e estorno.
3. **Parcelas históricas:**
   - registro explícito em `financeiro.parcela_historica`;
   - parcela fica `pago` com valor pago = previsto; despesa fica `Pago` na data do vencimento;
   - **nenhum movimento bancário**;
   - só parcelas já vencidas;
   - não são reabertas: o estorno exige movimento, e o motor não as toca.
4. **Recálculo, redução de prazo, regeneração e exclusão** só alcançam parcelas pendentes sem movimento. Amortização com parcela protegida depois da data é recusada (`PARCELA_PROTEGIDA`), preservando a continuidade da cadeia.
5. **Teste de preservação:** cenário de 420 parcelas (§4).

**Também:**
- índices únicos (parcela por número; despesa por parcela);
- contrato travado (`for update`) e trava por perfil;
- idempotência por chave;
- tudo numa transação.

## 4. Testes

**`tests/test_supabase_financiamentos_motor.py` (27 casos, todos passam):** cluster descartável, o próprio Flask na comparação.

| Teste | O que prova |
|---|---|
| `test_cadastro_sac_tr_igual_ao_flask` | 420 parcelas e despesas, contrato, item e vigências **iguais ao Flask campo a campo** (seguro fixo por vigência, taxa adm 25) |
| `test_cadastro_dfi_mip_igual_ao_flask` | Mesmo para DFI + MIP com faixas (payload da calibração) |
| `test_historicas_igual_ao_estado_do_flask_sem_movimento` | 15 históricas = o estado do `gastos.db` (parcela e despesa pagas), sem movimento |
| `test_amortizacao_reduzir_parcela_igual_ao_flask` | Amortização de 216.670 (calibração) **igual ao Flask** nas 405 parcelas recalculadas |
| `test_reduzir_prazo_igual_ao_flask_sem_parcelas_so_de_taxa` | Igual ao Flask; só as parcelas que ficaram sem saldo saem (§5) |
| `test_calibracao_caixa_preservada_no_motor_novo` | Tolerâncias contra os valores cobrados pela Caixa (jan–dez/2025, saldo de maio/2026, junho/2026) valem para o motor novo |
| `test_cenario_420_parcelas_22_historicas` | 420 / 22 pagas / 398 pendentes, sem movimento; saldo atual = saldo da 22ª |
| `test_segunda_amortizacao_preserva_historico_igual_ao_flask` | **As sete provas:** (1) 22 históricas intactas, (2) nenhum movimento, (3) nenhuma despesa histórica recriada, (4) 1ª amortização preservada, (5) continuidade do saldo, (6) só as futuras recalculadas, (7) sem duplicidade (reenvio = mesma operação). E igual ao Flask no mesmo estado |
| `test_regeneracao_e_reregistro_nao_alteram_historico` | Regeneração recusada com execução; re-registro não muda nada; parcela futura não vira histórica |
| `test_pagamento_e_estorno_em_despesas_protegem_parcela` | Parcela paga com débito (FIN-CONTRATOS-2) fica intacta na amortização; com movimento estornado, bloqueia |
| `test_continuidade_com_parcelas_pendentes_antes_da_data` | Correção de continuidade (§5) |
| `test_exclusao_segura_igual_ao_flask` | Exclusão igual ao Flask; item de despesa fica; com execução é recusada |
| `test_tr_ausente_falha_sem_gravar` | Sem TR: erro do Flask e nada gravado (atômico) |
| `test_price_amortiza_e_validacoes_do_flask` | PRICE cadastra e amortiza; validações do Flask (vigência obrigatória, taxa); valor acima do saldo recusado; regeneração sem execução não duplica |
| `test_escritor_unico_permissoes_isolamento_e_idempotencia` | Perfil no Flask: recusado; quem só lê: 42501; outro perfil: não encontrado; reenvio: um contrato só; o Flask recusa o perfil do novo app (409) |
| `test_edicao_estrutural_sem_execucao_igual_ao_flask` | Valor, prazo, taxa, seguro e taxa adm alterados: cronograma regenerado igual ao Flask |
| `test_edicao_com_execucao_bloqueia_estrutural_e_renomeia_so_pendentes` | Estrutural recusada nos dois; nome aceito. O novo renomeia só as despesas pendentes (§5, M7) |
| `test_vigencia_nova_igual_ao_flask_e_despesa_acompanha` | Parcelas iguais ao Flask. Reproduz o defeito do Flask: despesas ficam com o valor antigo (M8) |
| `test_ajuste_de_saldo_igual_ao_flask` | Com e sem recálculo, igual ao Flask; parcela protegida na faixa: recusado sem gravar |
| `test_demais_modalidades_iguais_ao_flask` (6 casos: SAC sem índice, SAC IPCA, SAC nominal, PRICE, SIMPLES, PRICE DFI+MIP) | Cadastro, edição estrutural, regeneração, 2 históricas, amortização reduzir parcela e prazo, ajuste de saldo: **tudo igual ao Flask ao centavo** |
| `test_simulacao_de_quitacao_igual_ao_flask_sem_gravar` | Mesmos valores do Flask (TR da competência, desconto); nada gravado; sem acesso: 42501; sem TR: erro |
| `test_reversao_remove_o_motor_e_volta` | Reversão tira tudo e devolve o saldo pela cadeia da 1120; reaplicar volta ao mesmo catálogo |

**E2E:**
- `web/tests/e2e/financiamentos_motor.spec.mjs`, na tela original:
  - cadastro pelo formulário;
  - juros = saldo corrigido × nominal/12;
  - amortização pelo modal;
  - exclusão recusada com execução e aceita sem.
- `financiamentos_tela.spec.mjs` ajustado: a ação fora da fase agora é o ajuste de saldo.
- `contratos_pagamento.spec.mjs` passa.

**Unitários `web/`:** passam (as RPCs novas estão liberadas só para `financiamentos-adaptador.js`).

**Regressão completa:** §8.

## 5. Diferenças em relação ao Flask (classificadas)

| # | Flask | Novo aplicativo | Classe |
|---|---|---|---|
| M1 | Na amortização, a base é o saldo atual (saldo da última **paga** menos as amortizações). Com pendentes antes da data, a amortização ordinária delas é descontada duas vezes | A base é o saldo após a parcela imediatamente anterior à 1ª recalculada, menos as amortizações registradas depois do vencimento dela. Tudo pago antes da data: igual ao Flask | Correção (continuidade do saldo) |
| M2 | Reduzir prazo (SAC/TR) mantém as parcelas sem saldo cobrando só a taxa administrativa (R$ 25 até o fim) | Essas parcelas pendentes, sem movimento, são removidas com as despesas. As demais ficam iguais ao Flask | Correção (despesa sem obrigação) |
| M3 | A execução que bloqueia a amortização olha só pago e data de pagamento | Também movimento, inclusive estornado, pela despesa ou pela parcela | Regra 1 |
| M4 | Amortização maior que o saldo deixa o saldo negativo | Recusada (`VALOR_ACIMA_DO_SALDO`); quitação é operação própria | Correção |
| M5 | Vigências ordenadas pelo texto da competência (`MM/AAAA` fica fora de ordem) | Ordenadas pela data | Correção menor |
| M6 | `_criar_conta_da_parcela` regrava valor e vencimento de despesa paga e copia o status da parcela (R1/R2) | Nunca | Regras 1 e 2 |
| M7 | Renomear o contrato não muda a descrição das despesas | As pendentes sem movimento passam ao novo nome; as efetivadas guardam o histórico (mesma regra aprovada em consórcios) | Correção |
| M8 | Vigência nova recalcula o seguro só na parcela; a despesa fica com o valor antigo. **É a origem das 398 despesas reais R$ 1,00 acima** (vigências 250 → 249 em 2026-03) | A despesa pendente sem movimento acompanha; a protegida fica e é contada em `parcelas_preservadas` | Correção |
| M9 | Aceita amortização com data anterior a outra já registrada | Recusada (`AMORTIZACAO_POSTERIOR`): reescreveria o efeito da posterior | Correção |
| M10 | Pagar ou registrar parcela vencida antes de uma amortização já registrada devolve o saldo de antes da amortização | `saldo_devedor_pelas_parcelas` (da 1120) redefinida: saldo da última paga menos as amortizações datadas depois dela. Pagando em ordem, igual ao Flask | Correção |
| M11 | Na vigência nova, recalcula também parcela pendente com despesa que tem movimento | Essa parcela fica intacta (Regra 1) | Regra 1 |

## 6. Migrations

- **`20261123090000_financeiro_financiamentos_motor.sql`** (local, não aplicada):
  - 37 funções novas (36 do motor e a do gatilho de proteção do registro histórico, §10);
  - **1 substituída:** `saldo_devedor_pelas_parcelas`, da 1120 (M10), com a mesma assinatura e privilégios;
  - tabela `financeiro.parcela_historica` (RLS forçado, sem acesso direto, registro coerente e permanente por gatilho);
  - índices únicos `financiamento_parcela_numero_unico` e `conta_financiamento_parcela_unica`.
- **Reversão:** `supabase/reversao/20261123090000_remover_motor_financiamentos.sql`. Recusa se houver parcela histórica registrada. Devolve o saldo pela cadeia da 1120 (testado: reverter e reaplicar volta ao mesmo catálogo).
- O teste de reversão da 1120 (`test_supabase_contratos_pagamento.py`) passou a desconsiderar a função que a 1123 redefine.
- **Antes de aplicar no remoto:** conferir que não há número de parcela nem despesa por parcela duplicados (hoje o teste não tem contratos; o `gastos.db` tem 420 números distintos).

## 7. Pendências e riscos

**Pendências:**
1. **Tela para registrar parcelas históricas** (a RPC existe; o Flask não tem a ação). Para migrar contratos do Flask, as pagas sem movimento já são protegidas como `pago`. Reconhecê-las no registro histórico é um passo do procedimento de transferência de perfil.
2. **Documentos e conferências da Caixa** (inclusive o registro da quitação oficial): FIN-DOCUMENTOS-2.
3. **Cadastro de índices** (TR e `indexador_mensal`): continua no Flask; o motor só lê.
4. **Pagamento direto de parcela sem despesa** (contratos antigos): continua pendente (P3 do FIN-CONTRATOS-2).

**Riscos:**
- **Contrato real** (§1):
  - suas parcelas não são do motor SAC/TR atual;
  - qualquer recálculo (amortização, regeneração) por **qualquer** dos dois aplicativos mudaria as 398 pendentes;
  - transferir esse perfil exige uma decisão de calibração antes: manter o cronograma gravado ou recalcular as futuras com o motor Caixa a partir do saldo da 22ª.
  - **Nada foi feito nele.**
- **Despesas pendentes reais R$ 1,00 acima das parcelas** (causa: M8). Na transferência do perfil, decidir se as 398 despesas são alinhadas às parcelas, valendo a vigência 249, ou se fica a cobrança de 250. Nada foi alterado.
- **TR:** o Supabase tem TR só até 2026-05. O motor recusa gerar sem TR, como o Flask. O cadastro de TR (Indexadores) continua no Flask.

## 8. Regressão completa

- **Banco do Supabase e Flask** (todos os `test_supabase_*`, calibração Caixa/TR, saldo de financiamento, estorno de financiamento, conferência Caixa, UX de financiamentos, movimentações, consórcios): **811 passaram, 0 falhas**, 18 pulados.
- **E2E completo:** **91 passaram, 0 falhas** (90 anteriores + o novo).
- **Unitários do `web/`:** 30 passaram.

## 9. Arquivos

- **Novos:**
  - `supabase/migrations/20261123090000_financeiro_financiamentos_motor.sql`;
  - `supabase/reversao/20261123090000_remover_motor_financiamentos.sql`;
  - `tests/test_supabase_financiamentos_motor.py`;
  - `web/tests/e2e/financiamentos_motor.spec.mjs`;
  - este documento.
- **Alterados:**
  - `web/src/js/financiamentos-adaptador.js` (rotas de escrita);
  - `web/src/paginas/financiamentos.html` (aviso da fase);
  - `web/tests/unit/build.test.mjs` (RPCs liberadas);
  - `web/tests/e2e/financiamentos_tela.spec.mjs` (ação fora da fase);
  - `tests/supabase_local.py` (TR fictícia 2034–2035 para o E2E).

## 10. Conferência final (26/10/2026)

Reconciliação entre o relatório parcial (só SAC/TR) e o final (etapas A–E), feita contra o repositório.

| Ponto | Resultado |
|---|---|
| Funcionalidades | Etapas A–E presentes: cadastro (SAC/TR Caixa, SAC com ou sem índice, PRICE, SIMPLES, seguro fixo por vigência e DFI/MIP), regeneração, parcelas históricas, amortização (reduzir parcela e reduzir prazo), ajuste de saldo, vigência de seguro, edição, exclusão segura, simulação de quitação. Adaptador com as rotas de escrita |
| Migration `20261123090000` | 36 funções do motor + 1 de proteção, 1 substituída (`saldo_devedor_pelas_parcelas`), tabela `parcela_historica`, 2 índices únicos. Nenhum comando altera dados fora das funções (conferido no texto) |
| Modalidades contra o Flask | SAC/TR (cadastro, amortização reduzir parcela e reduzir prazo, segunda amortização, vigência, ajuste, quitação, edição, exclusão), calibração Caixa, DFI/MIP, SAC sem índice, SAC IPCA, SAC nominal, PRICE, PRICE DFI/MIP, SIMPLES |
| Testes (agora) | `test_supabase_financiamentos_motor.py` **28 passaram** (27 + o da proteção nova); `test_supabase_contratos_pagamento.py` 8; `test_supabase_financiamentos_leitura.py` 4; E2E `financiamentos_motor` e `financiamentos_tela` 3. Nenhuma falha |
| 22 parcelas históricas | Intactas em todas as operações (cenário 420/22/398 e as sete provas); sem movimento; regeneração recusada (`COM_EXECUCAO`); re-registro não altera nada |
| Continuidade do saldo | Base da amortização = saldo após a parcela anterior à 1ª recalculada, menos as amortizações posteriores (M1); amortização fora de ordem recusada (`AMORTIZACAO_POSTERIOR`); saldo pela cadeia (M10); ajuste igual ao Flask |
| `parcela_historica` | **Lacuna encontrada e corrigida:** a coerência e a permanência dependiam só da função que grava, e o RLS não era forçado. Agora: RLS forçado, sem acesso do navegador; gatilho que só aceita registro coerente (parcela do financiamento, financiamento do perfil, parcela paga, despesa da própria parcela) e recusa UPDATE, DELETE e TRUNCATE. Testes: `test_registro_historico_e_permanente_e_coerente_no_banco` (SQL direto do administrador e função `SECURITY DEFINER` chamada pelo navegador, recusados) |
| Reversão | Não altera dado nenhum (só remove objetos). Recusa se houver registro histórico; com a tabela vazia, devolve a 1120. Testada |
| Cronograma real | Intocado. `data/gastos.db` sem modificação desde 12/05/2026. No Supabase de teste, a `20261123090000` está **pendente** (status lido; nada aplicado) |
| Sobras do relatório parcial | A linha da tabela de testes que falava em `MODALIDADE_PENDENTE` e o nome do teste foram corrigidos (`test_price_amortiza_e_validacoes_do_flask`); o código não tinha mais essa recusa |

**Alcance da proteção do registro histórico (precisão pedida pelo titular):**
- **Bloqueia:** o navegador (sem privilégio na tabela); todas as funções do banco, inclusive as `SECURITY DEFINER`, que rodam como o dono das tabelas (o gatilho vale para qualquer papel); e comandos diretos `UPDATE`, `DELETE` e `TRUNCATE` do próprio administrador, por engano ou por roteiro.
- **Não bloqueia:** quem tem privilégio de alterar a estrutura da tabela (o dono, `postgres`, ou um superusuário do Supabase) e decide, de propósito, desligar ou remover o gatilho (`ALTER TABLE ... DISABLE TRIGGER`, `DROP TRIGGER`) ou mudar `session_replication_role` (só superusuário). Isso é ato deliberado de alteração de estrutura, fora dos caminhos do aplicativo, e não fica impedido por nenhuma regra dentro do próprio banco.
- **A reversão** só remove a tabela vazia: com registros, ela recusa.

**Pendências que restam:** as do §7 (tela de registro histórico, documentos e conferências Caixa, cadastro de índices, pagamento direto sem despesa) e as decisões do contrato real (calibração e os R$ 1,00 das 398 despesas). Antes de aplicar no Supabase de teste: conferir duplicidade de número de parcela e de despesa por parcela, só lendo.

**Fechamento:** o motor está completo conforme o relatório final. Arquivos do commit: os do §9 e `tests/test_supabase_contratos_pagamento.py` (reversão da 1120). `web/tests/unit/build.test.mjs` e `docs/ROADMAP.md` são compartilhados com outros MVPs: entram só as linhas do motor.

## 11. Aplicação no Supabase de teste (26/10/2026)

**Commit:** `4de6fb5` (só o motor, sem push). Autorização do titular: aplicar só no Supabase de teste, depois da inspeção, e validar com perfil temporário. Sem produção, sem push e sem transferir Pessoal ou Empresa.

**Inspeção antes de aplicar** (só leitura, todas aprovadas):
- nenhum número de parcela duplicado por contrato e nenhuma despesa duplicada por parcela. O Supabase de teste não tem contrato de financiamento: 0 contratos, 0 parcelas;
- as 37 funções novas, a tabela e os 2 índices não existiam;
- as 8 funções de que a migration depende estão presentes;
- as colunas das 14 tabelas usadas (236) são iguais às do cluster local;
- o dono das funções `SECURITY DEFINER` é `postgres`, **sem superusuário e com BYPASSRLS**: as funções passam pelo RLS forçado, e o gatilho vale para ele;
- `saldo_devedor_pelas_parcelas` no remoto é igual ao texto que a reversão devolve. A única diferença é o fim de linha (o remoto guarda CRLF), que o PL/pgSQL ignora;
- TR disponível de 2024-05 a 2026-05; última versão aplicada era a `20261122090000`;
- migration e reversão iguais ao commit; a reversão remove as 37 funções, a tabela e os índices e devolve o saldo da 1120.

**Aplicação:**
- só a `20261123090000`. As migrations locais posteriores ficaram fora da pasta durante o envio e voltaram idênticas (md5), então a trava da ferramenta, que só aplica o conjunto pendente exato, ficou como estava;
- as 64 tabelas existentes mantiveram o conteúdo idêntico (211 linhas); +1 tabela (`parcela_historica`); +37 funções; 1 alterada (`saldo_devedor_pelas_parcelas`); nenhuma removida.

**Validação real** (perfil temporário criado pelo aplicativo, **17 de 17**):
- **Cadastro SAC/TR fictício** (300 mil, 23 parcelas, seguro fixo por vigência, taxa administrativa): o reenvio pela mesma chave não duplicou; 23 parcelas e 23 despesas.
- **Parcelas históricas 1 a 6:**
  - pagas, sem movimento; saldo atual = saldo da 6ª;
  - registrar de novo registra 0; a regeneração é recusada (`COM_EXECUCAO`); o histórico fica idêntico.
- **Proteção sob os privilégios reais** (conexão como `postgres`, o dono das funções e das tabelas, numa transação desfeita): UPDATE, DELETE e TRUNCATE do registro recusados (`HISTORICO_PERMANENTE`); inserção incoerente recusada (`HISTORICO_INCOERENTE`); o navegador recebe 403 na tabela.
- **Pagamento e amortização:**
  - parcela 7 paga em Despesas, com movimento;
  - amortização reduzir parcela: saldo = saldo da 7ª − 50 mil;
  - reduzir prazo: as duas amortizações ficam, e o saldo segue a cadeia;
  - amortização anterior a uma já registrada é recusada;
  - em tudo isso, o histórico e a 7ª ficaram intactos.
- **Simulação de quitação:** não grava nada. Na primeira tentativa, o roteiro mandou o campo com nome errado e recebeu 400. Refeita com `data_quitacao`, passou.
- **Escritor e permissões:** com o perfil no Flask, amortização e cadastro são recusados (`SISTEMA_FLASK`); quem só lê recebe 403; a exclusão com execução é recusada.
- **Contratos fora do perfil temporário:** nenhum foi tocado.
- **Telas:** Despesas e Financiamentos com o `dist` e a CSP reais, sem erro de console nem chamada ao Flask: aprovadas.

**Limpeza por identidade** (simulação, depois confirmação):
- **Registro histórico:** é permanente. Para apagar as 6 linhas fictícias do perfil temporário, o gatilho de linha foi desligado **só dentro da transação da limpeza**, a exclusão ficou limitada ao perfil e o gatilho foi religado antes do commit (conferido: os dois gatilhos ativos, nenhum registro de outro perfil afetado). É o limite descrito no §10: só uma alteração deliberada de estrutura passa pela proteção.
- **Resultado:** banco idêntico ao retrato pós-aplicação (tabelas, funções e histórico de migrations); `parcela_historica` vazia.

**Inalterados:** produção; Pessoal e Empresa, que continuam no Flask; `gastos.db`; o cronograma real de 420 parcelas.

**Pendentes no remoto:** `20261124090000`, `20261125090000`, `20261126090000` (sem autorização).

