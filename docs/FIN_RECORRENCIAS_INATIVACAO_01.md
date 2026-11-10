# FIN-RECORRENCIAS-INATIVACAO-01 — P22: inativação de recorrências

**Situação (09/11/2026): publicado e regularizado.**
- Publicação: `cd244b7`, migration `20261221090000` (62 migrations), deploy `03ed0f18`.
- Regularização autorizada: as 10 contas futuras de Telefonia e USP - MBA, R$ 2.890,50.
- Auditoria somente leitura aprovada (seção 12).

**Base de produção:** `c3cf1a4` (61 migrations, última `20261220090000`).
**Nível de impacto:** N4 (integridade financeira).

## 1. Diagnóstico da causa

Há duas causas, ambas no banco.

1. **`inativar_recorrencia` só gravava `item_despesa.ativo = false`.**
   - O gerador (`plano_recorrencia` / `gerar_mes_interno`) deixa de criar ocorrências novas para a recorrência inativa (linha `INATIVA`).
   - As ocorrências já geradas não eram tocadas. Despesas gera até o mês seguinte, e a tela abre meses adiante; em produção, as contas de Telefonia e USP existem até 04/2027.
   - Por isso elas continuavam exigíveis em Despesas, nas Faturas (compras previstas de recorrência no cartão) e no Dashboard.
   - O mesmo valia para o cartão: `definir_situacao_recorrencia_cartao` só trocava `ativo`.
2. **"Excluir esta e as parcelas futuras" (Despesas) exigia a recorrência ativa.**
   - O adaptador (`despesas-adaptador.js`) recusava com "A recorrência não pode ser inativada por aqui." quando `pode_inativar_recorrencia` era falso.
   - Em `despesa_para_edicao`, esse campo exige `ativo`. Numa recorrência já inativa (Telefonia, USP), a ação oferecida era sempre recusada.
   - "Excluir apenas esta" funcionava (`excluir_despesa` não exige `ativo`): foi assim que as contas de 11/2026 das duas saíram.

**Risco encontrado na reativação.**
- `reativar_recorrencia` só gravava `ativo = true`.
- O planejador percorre todas as competências desde o primeiro vencimento, e as do período inativo que nunca foram geradas aparecem como "a gerar".
- Como Despesas gera automaticamente ao abrir a competência, a reativação criaria contas atrasadas.
- Isso está provado com o corpo antigo: `test_sem_a_correcao_a_reativacao_geraria_contas_atrasadas`.

## 2. Funções e tabelas envolvidas

- **Cadastro:** `public.item_despesa` (`ativo`, `recorrente`, `tipo_recorrencia`, `data_vencimento`, `meio_pagamento`).
- **Ocorrências:**
  - `public.conta`: boleto, Pix, débito, débito automático;
  - `public.lancamento_agregado`: previsão de recorrência no cartão (`is_recorrente`).
- **Identidade e cancelamento (já existentes):**
  - `financeiro.recorrencia_competencia`: mensal e anual, situações `GERADA` e `DISPENSADA`;
  - `financeiro.recorrencia_ocorrencia`: semanal.
  - A competência DISPENSADA não é recriada pelo gerador.
- **Proteções reaproveitadas:**
  - contas: `bloqueio_da_despesa` (paga, com movimento, cartão, consórcio, financiamento, outro módulo);
  - cartão: `situacao_previsao` (PREVISTA, CONFIRMADA, NAO_COBRADA, PAGA), fatura fechada e crédito vinculado.
- **Travas reaproveitadas:** `travar_recorrencia`, `travar_recorrencia_cartao`, a trava da geração (`pg_advisory_xact_lock(20261023, perfil)`) e `exigir_escrita_novo` (escritor único).

## 3. Solução: menor mudança segura

Sem tabela nova e sem segundo mecanismo.
- **Conta:** a competência fica DISPENSADA e a conta pendente sai, como em "Excluir apenas esta".
- **Cartão:** a previsão sai da fatura, como em `excluir_compra`, com a fatura recalculada.
- **Rastreabilidade:** o motivo da dispensa guarda a conta ou compra, o valor e o vencimento ("Interrompida pela inativação da recorrência: conta #2538 de R$ 70.00, vencimento 15/12/2026").

### Regra (matriz do contrato)

| Ocorrência | Tratamento |
| --- | --- |
| Paga, com movimento, ou outro bloqueio | Fica (aparece na prévia como protegida) |
| Vencida e pendente | Fica; em Despesas, a escolhida em "esta e as futuras" entra (escolha explícita) |
| Futura, pendente e sem proteção | Deixa de ser exigível |
| Ainda não gerada | Não é gerada (recorrência inativa) |
| Já cancelada | Não muda (repetir não altera nada) |
| Cartão com cobrança real (importada, confirmada, não cobrada), fatura paga ou fechada, crédito | Fica |

- **Data de efeito:** início da competência seguinte; a tela oferece "Incluir a competência atual", e as vencidas ficam mesmo assim.
- **Competência:** vale o mês da ocorrência (`mes_referencia`; no cartão, a competência original da compra), igual para mensal, anual e semanal.
- **Transação:**
  - inativar e cancelar acontecem na mesma transação; uma falha no meio desfaz tudo (teste com falha simulada);
  - a confirmação leva a versão da recorrência e a quantidade da prévia; se algo mudou, a operação é recusada (`PREVIA` / `VERSAO`) sem gravar.
- **Travas:** as contas candidatas primeiro, depois a recorrência e depois a trava da geração, na mesma ordem de `travar_despesa`, sem deadlock com exclusão ou pagamento simultâneos. No cartão: geração, cartão, faturas e compras, como em `travar_compra`.

### Retomada (reativar)

- Retoma na competência atual, ou na escolhida na tela.
- As competências do período inativo que nunca foram geradas ficam DISPENSADAS ("Período inativo: recorrência retomada a partir de MM/AAAA"), sem contas atrasadas.
- As ocorrências canceladas pela inativação só voltam se o usuário marcar "Restaurar". As excluídas uma a uma continuam excluídas.
- Recorrência já ativa: nada muda. Contas pagas nunca são recriadas e não há duplicidade (identidade por competência).

## 4. Migration `20261221090000`

**Funções novas.**
- Para o usuário logado (`authenticated`): `previa_interrupcao_recorrencia`, `interromper_recorrencia`, `previa_retomada_recorrencia` e `retomar_recorrencia`.
- Internas, sem acesso pela API: `dispensar_conta_recorrente`, `efeito_interrupcao`, `motivo_sem_interrupcao`, `ocorrencias_interrupcao`, `lacunas_da_recorrencia` e `exigir_recorrencia_fora_do_cartao`.

**Funções substituídas** (mesmas assinaturas e permissões):
- `inativar_recorrencia`: interrompe a partir da competência seguinte;
- `reativar_recorrencia`: retoma sem o período inativo e sem restaurar;
- `definir_situacao_recorrencia_cartao`: as duas regras acima, no cartão;
- `excluir_despesa`: a dispensa passou para `dispensar_conta_recorrente`, mesmo comportamento.
- As duas primeiras continuam recusando recorrência de cartão, como antes.

**Dados:** a migration não muda nenhum dado e não cancela nada.

**Reversão:** `supabase/reversao/20261221090000_recorrencias_inativacao_anterior.sql`.
- Restaura as 4 funções com o texto lido da produção e remove as novas.
- As dispensas gravadas continuam válidas no modelo anterior.
- O arquivo está em CRLF, como a cópia de trabalho; três dos quatro corpos em produção têm CRLF.
- `excluir_despesa`, que em produção não tem CR, volta idêntica exceto pelos finais de linha (conferido no ensaio).

## 5. Interface

O modal é compacto e comum às duas telas (`web/src/js/interrupcao-recorrencia.js`, `css/interrupcao-recorrencia.css`). Os JS originais do Flask não mudaram: as adaptações substituem funções globais, como nas outras telas.

**Recorrências: "Inativar"** (`recorrencias-adaptacoes.js`).
- O modal mostra a recorrência, a data de efeito (com a opção da competência atual), a quantidade e o valor que deixam de ser exigíveis, as competências e as protegidas, com o motivo de cada uma.
- Botões padronizados: Cancelar e Inativar.
- Numa recorrência já inativa, a mesma ação cancela as ocorrências futuras que ficaram. É o caminho da regularização, que depende de autorização.
- Ao reativar pelo formulário, o modal mostra a retomada (mês, período inativo e restauração opcional, desmarcada).

**Despesas.**
- "Excluir esta e as parcelas futuras" mostra a mesma prévia: esta conta e as futuras elegíveis.
- Interrompe a recorrência, ativa ou já inativa, numa só transação.
- Ao abrir a escolha, cada opção que o banco recusaria fica visível e desabilitada, com o motivo.
- "Excluir apenas esta" continua só nesta.

**Totais:** Despesas, Faturas e Dashboard leem as contas e compras existentes. Como as canceladas saem, os totais acompanham sem mudança nas consultas, e o indicador de recorrências ativas cai.

## 6. Prévia em produção (somente leitura, efeito padrão 12/2026)

| Recorrência | Situação | Deixam de ser exigíveis | Total | Ficam |
| --- | --- | --- | --- | --- |
| Telefonia (381, débito automático) | Inativa | contas 2538, 2565, 2591, 2619, 2649 (12/2026 a 04/2027, R$ 70,00 cada) | R$ 350,00 | conta 2480 (10/2026, vencida e pendente) e as pagas de 05 a 09/2026 |
| USP - MBA (385, débito) | Inativa | contas 2542, 2569, 2595, 2623, 2653 (12/2026 a 04/2027, R$ 508,10 cada) | R$ 2.540,50 | conta 2484 (10/2026, vencida e pendente) e as pagas de 05 a 09/2026 |
| X Premium (458, cartão, anual) | Inativa | nenhuma (a compra 558 é de 10/2026, antes do efeito) | R$ 0,00 | compra 558 |

- **Pagamentos e movimentos:** nenhuma das 10 contas elegíveis tem pagamento ou movimento.
- **Competência atual:** incluí-la não muda nada, porque as competências de 11/2026 já tinham sido excluídas pelo usuário (DISPENSADA, "Conta excluida pelo usuario").
- **Vencidas de 10/2026:** ficam, como manda a matriz; só saem com cancelamento específico autorizado.
- **Simulação na cópia descartável** (as 3 interrompidas com a quantidade da prévia):
  - só `public.conta` e `financeiro.recorrencia_competencia` mudaram; movimentos, saldos e compras ficaram iguais;
  - Despesas de 12/2026 a 04/2027 ficam R$ 578,10 menor por mês (R$ 70,00 + R$ 508,10), e as despesas previstas do Dashboard caem o mesmo valor;
  - 11/2026 fica igual.
- **Regularização:** não foi executada. Depende de autorização específica, pelo modal de Recorrências ("Inativar" numa recorrência inativa) ou por "Excluir esta e as futuras".

## 7. Ensaio na cópia fiel da produção

O ensaio está em `scratchpad/p22/ensaio.py`, com o resultado em `ensaio.json`.

- **Cópia:** IDÊNTICA, com 61 migrations.
- **Migration:**
  - nenhuma tabela com dados alterados; 10 funções novas, 4 alteradas e nenhuma removida;
  - Despesas e Dashboard de 11/2026 a 04/2027 iguais antes da simulação.
- **Segurança:** nenhuma função `security definer` sem `search_path`, nenhuma função executável por `anon`, nenhuma tabela sem RLS; só as 4 de tela executáveis por `authenticated`.
- **Reversão:** sem mudança de dados. Funções iguais ao estado anterior, exceto `excluir_despesa`, que difere só nos finais de linha.
- **Reaplicação:** sem mudança de dados e com as funções iguais às da primeira aplicação.

## 8. Testes por impacto (N4)

**Arquivos e funções afetados:**
- a migration acima;
- `web/src/js/recorrencias-adaptador.js`, `recorrencias-adaptacoes.js`, `despesas-adaptador.js`, `despesas-adaptacoes.js` e `interrupcao-recorrencia.js`;
- as páginas `recorrencias.html` e `contas.html`.

| Bateria | Seleção (por dependência) | Resultado |
| --- | --- | --- |
| Nova: `test_supabase_recorrencias_inativacao.py` | As 15 baterias do contrato (detalhe abaixo) | 45/45 |
| Regressão direcionada N4 | Recorrências (tela, cartão, gerador), Despesas, categorias e semanais, escritor único, importação com fixas, integração 1123–1127, abastecimento (usa `excluir_despesa`), pendências de recorrência, integridade de Mobilidade (competências), pagamento em lote e identidade | 368/370. As 2 falhas eram testes que fixavam o comportamento antigo, ajustados e repetidos: 2/2 |
| Testes da reversão | O i7 da integração e o da P22 | 2/2 |
| Unitários do frontend | Todos (lista de RPCs do build) | 92/92 |
| E2E do fluxo | `recorrencias_inativacao.spec` (novo: inativar em 1366 e 1920, reativar, Despesas ativa e já inativa) + `recorrencias_tela.spec` | 12/12 |
| E2E de Despesas | `despesas.spec` + `despesas_pagamento_lote.spec` (adaptador e adaptações de Despesas alterados) | 12/12 |

**Baterias da suíte nova:**

| Bateria do contrato | Testes |
| --- | --- |
| 1 Inativação | `test_interromper_cancela_futuras_e_preserva_paga_vencida_e_atual`, `test_funcoes_antigas_passam_pelo_mesmo_caminho` |
| 2 Ocorrências já geradas | `test_previa_mostra_afetadas_e_preservadas_sem_gravar`, `test_incluir_competencia_atual_so_tira_o_que_nao_venceu` |
| 3 Pagas preservadas | `test_conta_paga_e_com_movimento_depois_do_efeito_fica` |
| 4 Movimentos e saldos | `test_interromper_...` (movimento e saldo iguais), `test_conta_paga_e_com_movimento...` |
| 5 Cancelamento individual | `test_excluir_apenas_esta_continua_so_nesta` |
| 6 Futuras | `test_recorrencia_ja_inativa_tem_as_futuras_interrompidas`, `test_esta_e_as_futuras_inclui_a_escolhida_mesmo_vencida`, `test_conta_de_outra_recorrencia_recusada` |
| 7 Reativação | `test_retomada_nao_gera_o_periodo_inativo`, `test_sem_a_correcao_a_reativacao_geraria_contas_atrasadas`, `test_retomada_nao_restaura_canceladas_sem_pedido`, `test_retomada_com_restauracao_regera_sem_duplicar`, `test_reativar_padrao_e_retomar_ativa_nao_mudam_o_que_nao_deve` |
| 8 Geração | `test_geracao_nao_recria_as_canceladas_nem_gera_depois` |
| 9 Pix, débito automático, boleto, semanal e cartão | `test_meios_de_pagamento_conta[pix, boleto, debito_automatico]`, `test_semanal_dispensa_cada_ocorrencia`, `test_cartao_previsoes_futuras_saem_e_fatura_recalcula`, `test_cartao_pela_situacao_antiga_e_retomada`, `test_funcoes_antigas_continuam_recusando_cartao` |
| 10–12 Totais de Despesas, Faturas e Dashboard | `test_totais_de_despesas_e_dashboard_sem_as_canceladas`, `test_cartao_previsoes_futuras_saem_e_fatura_recalcula` |
| 13 Isolamento e escritor único | `test_isolamento_por_perfil_e_usuario`, `test_perfil_no_flask_recusado`, `test_recorrencia_de_outro_modulo_bloqueada`, `test_funcoes_seguras[10]` |
| 14 Transação e idempotência | `test_previa_desatualizada_recusa_sem_gravar`, `test_repetir_nao_muda_mais_nada`, `test_versao_antiga_recusada`, `test_falha_no_meio_desfaz_tudo` |
| 15 Concorrência | interrupção com pagamento, com exclusão, com geração e duas simultâneas (sem deadlock; uma vale) |
| Reversão | `test_reversao_e_reaplicacao_preservam_os_dados` |

**Testes ajustados ao comportamento corrigido:**
- `test_supabase_despesas.py::test_inativacao_para_a_geracao_e_mantem_o_historico`: fixava que a conta futura pendente continuava. Agora a paga fica e a futura fica DISPENSADA.
- `test_supabase_cartao_importacao_fixas.py::test_recorrencia_inativada_reconhece_a_previsao_pendente`: inativava em 2029 com o efeito calculado a partir de hoje e esperava a previsão de 05/2029. Agora inativa com efeito 06/2029 (como a tela faria em 05/2029) e a previsão de 05 continua reconhecida.
- `recorrencias_tela.spec`: o `confirm()` deu lugar ao modal.

**Testes não executados, com justificativa:**
- Suíte completa e E2E completo: não houve mudança estrutural abrangente. O gerador (`plano_recorrencia` / `gerar_mes_interno`), os pagamentos, os estornos, as faturas e os saldos não foram alterados. A interrupção usa os mesmos caminhos de exclusão, e os módulos que os usam entraram na seleção.
- Financiamentos, Mobilidade (projeções), Importação PDF/OFX, Patrimônio, Documentos e Receitas: sem dependência das funções alteradas.
- `test_veiculos_mobilidade_recorrencia.py`: teste do Flask (`inativar_recorrencias_origem`), que não muda.
- Antes da publicação, vale o protocolo vigente: conferências da migration remota e auditoria.

## 9. Riscos remanescentes

- **Ocorrência ainda não gerada no mês atual.** Se a recorrência for inativada antes de a competência atual ser gerada (Despesas ainda não aberta no mês), a ocorrência do mês atual não é gerada, porque o gerador só olha `ativo`. Na prática, a competência atual já existe, porque Despesas gera até o mês seguinte.
- **Mecanismo de cancelamento.** A conta pendente cancelada sai da tabela, como na exclusão de uma ocorrência que já existia. O registro DISPENSADA guarda conta, valor, vencimento, usuário e data. Não existe status "cancelada" em `conta`; criá-lo seria um segundo mecanismo, fora do escopo.
- **Contas vencidas e pendentes** de recorrências inativas (Telefonia e USP, 10/2026) continuam exigíveis até decisão específica.

## 10. Commits locais

- **banco:** migration `20261221090000`, reversão e testes;
- **tela:** modal, adaptadores, páginas e E2E;
- **documentação:** este arquivo e o ROADMAP.

## 11. Prontidão para publicação

Pronto para homologação.
- **Ordem na publicação:** push, aplicar só `20261221090000`, depois build e um deploy.
- **Entre a migration e o deploy:**
  - a tela publicada continua funcionando: "Inativar" usa `inativar_recorrencia`, que já interrompe com o efeito padrão, ainda sem a prévia;
  - "Excluir esta e as futuras" numa recorrência inativa continua recusada até o deploy;
  - na tela antiga, "Excluir esta e as futuras" numa recorrência ativa inativa primeiro, o que agora já cancela as futuras elegíveis, e depois tenta excluir a conta escolhida. Se ela for de uma competência posterior à atual, já terá saído, e a tela mostra um erro sem nada a desfazer. Por isso, o deploy deve vir logo depois da migration.
- **Regularização de Telefonia e USP:** só com autorização própria, depois da publicação.

## 12. Publicação e regularização (09/11/2026)

Autorizadas pelo usuário em 09/11/2026, em duas etapas separadas e nesta ordem.

### Etapa 1 — publicação

- **Conferências antes do push:**
  - `origin/main` em `c3cf1a4`; os commits publicados são `c59ca8d` (documentação do MOB-02), `17484a4`, `d082378` e `cd244b7`;
  - produção com 61 migrations, última `20261220090000`; a 1221 era a única pendente; md5 `64b95537…` e só LF;
  - as 4 funções substituídas estavam iguais aos textos da reversão; as 10 novas não existiam;
  - as 12 contas de Telefonia e USP a partir de 10/2026 estavam como no ensaio.
- **Push** `c3cf1a4..cd244b7`, em avanço direto.
- **Migration `20261221090000`:** aplicada sozinha, com o dry-run listando só o seu arquivo; 62 migrations.
  - Estrutura: nenhuma tabela nova ou removida; 10 funções novas e as 4 substituídas, com os 14 corpos idênticos ao arquivo e `search_path` vazio.
  - Execução: só as 4 de tela executáveis por `authenticated`, e nenhuma execução perdida.
  - Dados e segurança: nenhum dado existente mudou e não há bloqueios de segurança.
- **Deploy `03ed0f18`** (Source `cd244b7`): 168 arquivos servidos iguais ao build; navegação anônima sem problemas.
- **Homologação** em sessão somente leitura, como o titular:
  - as prévias publicadas listaram exatamente as contas 2538, 2565, 2591, 2619 e 2649 (Telefonia, R$ 350,00) e 2542, 2569, 2595, 2623 e 2653 (USP, R$ 2.540,50), sem protegidas;
  - X Premium sem nada; uma recorrência ativa (Diarista) com prévia normal; as retomadas sem lacunas.
  - Nenhuma operação financeira.
- **Dados depois da Etapa 1:** as 88 tabelas iguais (86 anteriores à MOB-02 e as 2 dela), e o retrato da P22 idêntico.

### Etapa 2 — regularização controlada

Foi feita numa única transação (`regularizar_p22.py`), pelo fluxo aprovado, `interromper_recorrencia` como o titular. Qualquer divergência faria rollback.

1. **Reconsulta:** as 10 contas existiam, eram das recorrências, competências e valores autorizados, estavam pendentes, sem pagamento, sem movimento e sem bloqueio, e eram do perfil Pessoal. As duas recorrências estavam inativas.
2. **Prévia:** a de cada recorrência (efeito 12/2026) listou exatamente as 5 autorizadas, sem protegidas.
3. **Interrupção:** feita com 5 esperadas: Telefonia com 5 canceladas (R$ 350,00) e USP com 5 canceladas (R$ 2.540,50), sem preservadas.
4. **Conferência ainda na transação:**
   - as 10 contas saíram;
   - as 10 competências ficaram DISPENSADAS, com a conta no motivo e o titular como autor;
   - não mudaram as demais contas, as competências das outras recorrências e as de 10 e 11/2026 destas, as ocorrências semanais, os movimentos, os saldos, as compras, os cadastros, as faturas, as contas 2480 e 2484 e as recorrências.
   - COMMIT.

| Conta | Recorrência | Competência | Valor | Registro histórico |
| --- | --- | --- | --- | --- |
| 2538 | Telefonia (381) | 12/2026 | R$ 70,00 | DISPENSADA: "conta #2538 de R$ 70.00, vencimento 15/12/2026" |
| 2565 | Telefonia (381) | 01/2027 | R$ 70,00 | DISPENSADA: "conta #2565 …, vencimento 15/01/2027" |
| 2591 | Telefonia (381) | 02/2027 | R$ 70,00 | DISPENSADA: "conta #2591 …, vencimento 15/02/2027" |
| 2619 | Telefonia (381) | 03/2027 | R$ 70,00 | DISPENSADA: "conta #2619 …, vencimento 15/03/2027" |
| 2649 | Telefonia (381) | 04/2027 | R$ 70,00 | DISPENSADA: "conta #2649 …, vencimento 15/04/2027" |
| 2542 | USP - MBA (385) | 12/2026 | R$ 508,10 | DISPENSADA: "conta #2542 de R$ 508.10, vencimento 05/12/2026" |
| 2569 | USP - MBA (385) | 01/2027 | R$ 508,10 | DISPENSADA: "conta #2569 …, vencimento 05/01/2027" |
| 2595 | USP - MBA (385) | 02/2027 | R$ 508,10 | DISPENSADA: "conta #2595 …, vencimento 05/02/2027" |
| 2623 | USP - MBA (385) | 03/2027 | R$ 508,10 | DISPENSADA: "conta #2623 …, vencimento 05/03/2027" |
| 2653 | USP - MBA (385) | 04/2027 | R$ 508,10 | DISPENSADA: "conta #2653 …, vencimento 05/04/2027" |

### Auditoria posterior (somente leitura)

| Competência | Despesas antes | Despesas depois | Diferença | Previstas no Dashboard (antes → depois) |
| --- | --- | --- | --- | --- |
| 11/2026 | R$ 22.615,08 | R$ 22.615,08 | — | R$ 10.704,02 → R$ 10.704,02 |
| 12/2026 | R$ 17.216,21 | R$ 16.638,11 | −R$ 578,10 | R$ 11.513,14 → R$ 10.935,04 |
| 01/2027 | R$ 16.965,22 | R$ 16.387,12 | −R$ 578,10 | R$ 11.262,15 → R$ 10.684,05 |
| 02/2027 | R$ 11.061,14 | R$ 10.483,04 | −R$ 578,10 | R$ 11.061,14 → R$ 10.483,04 |
| 03/2027 | R$ 17.139,72 | R$ 16.561,62 | −R$ 578,10 | R$ 11.760,12 → R$ 11.182,02 |
| 04/2027 | R$ 16.638,68 | R$ 16.060,58 | −R$ 578,10 | R$ 11.259,08 → R$ 10.680,98 |

- **Contas:** 779 → 769, com valor total menor em exatamente R$ 2.890,50. Executado (R$ 9.790,25) e pagas (206) iguais.
- **Tabelas:** só `public.conta` e `financeiro.recorrencia_competencia` mudaram. As outras 86 das 88 ficaram iguais, entre elas movimentos, contas bancárias (saldos), compras, faturas, créditos, financiamento, abastecimentos e cadastros.
- **Preservados:** as contas 2480 e 2484 (10/2026, vencidas e pendentes), as 10 pagas de 05 a 09/2026, as competências de 11/2026 ("Conta excluida pelo usuario") e o X Premium.
- **Sem novas cobranças:** a prévia de geração de 12/2026 a 06/2027 não tem nada a gerar de Telefonia ou USP.
- **Dashboard e telas:** diferem só no perfil Pessoal, nos meses afetados. A Empresa ficou igual.
- **Testes:** os da seção 8, sem alteração de código depois deles. O código publicado é o homologado (`cd244b7`).
