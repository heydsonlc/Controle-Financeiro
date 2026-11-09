# FIN-DESPESAS-PAGAMENTO-LOTE-02 — Identidade do lote no pagamento em lote (P21)

**Situação (08/11/2026): publicado (`de5bf20`, migration `20261219090000`, deploy `04dd7c99`).** Auditoria somente leitura aprovada (seção 7). Os pagamentos da Passadeira foram confirmados pelo usuário como devidos e ficam como estão.

**Problema:** depois da publicação da P20 (`5b5e4e8`, deploy `9e2982ab`), o botão "Pagar em lote" da Diarista abria o modal da Psicóloga, e o da Psicóloga abria o da Diarista.

## 1. Causa comprovada

| Pergunta | Resposta |
|---|---|
| Vínculo do botão | O original (`despesas.js`, sem alteração) desenha cada agrupador semanal com `pagarTodasOcorrencias(<posição>)`. A posição é a do agrupador em `agruparDespesasSemanais(lista desenhada)` |
| Posição ou identificador | **Posição.** A P20 manteve a busca do original: `agruparDespesasSemanais(despesas)[posição]`, sobre a lista **inteira** do mês |
| Filtros e ordenação | Mudam o vínculo. A lista desenhada passa pelos filtros (situação, forma de pagamento, "vencimento até", busca). Os agrupadores ficam na ordem da primeira ocorrência na lista (vencimento mais recente primeiro), e os filtros mudam essa ordem |
| Seleção anterior guardada | Não. O modal é montado a cada clique, mas com o agrupador da posição errada |
| O que ia ao banco | As ocorrências do agrupador errado. Modal e pedido vinham do mesmo agrupador: o modal mostrava a recorrência que seria paga, só que não a do botão clicado |
| Pagar outra recorrência | **Sim.** O banco conferia que eram todas as pendentes das mesmas recorrências na competência, e isso valia para a outra recorrência. Confirmar o modal trocado pagava a outra |
| Origem | Defeito herdado do Flask (o mesmo `pagarTodasOcorrencias`, com o comentário "manter o índice original"). No novo aplicativo, antes da P20, o lote nunca pagava ("0 paga(s), 8 com erro"); a P20 fez o lote funcionar e manteve a busca por posição |

**Reprodução com os dados reais de 11/2026 (somente leitura).** Sem filtro, a lista começa por "Diarísta - 27/11" (paga), e os agrupadores ficam nesta ordem: Diarísta, Psicóloga, Passadeira. Com o filtro "Pendentes", as duas Diarístas mais recentes (pagas) saem, a lista começa por "Psicóloga - 24/11", e a ordem desenhada é Psicóloga, Diarísta.
- O botão da Diarísta (posição 1) abria a posição 1 da lista inteira, a Psicóloga.
- O da Psicóloga (posição 0) abria a Diarísta.

O E2E reproduz exatamente isso com o código publicado (seção 4).

## 2. Pagamentos depois da publicação (produção, somente leitura)

| Horário (Brasília) | Operação | Ocorrências | Situação |
|---|---|---|---|
| 08/11 22:07:10 | `pagar_despesas_lote` | Passadeira 09/11 e 23/11 (2515, 2516), R$ 500,00, conta 96 | **Continua paga** |
| 08/11 22:07:34 | `pagar_despesas_lote` | Psicóloga 03, 10, 17 e 24/11 (2499 a 2502), R$ 1.000,00, conta 96 | Estornada uma a uma pelo usuário entre 22:08:21 e 22:09:04 |

- A Diarísta não foi paga: as 6 pendentes continuam pendentes e as 2 pagas antes estão intactas.
- Conta 96: R$ 85.312,08, igual ao recalculado (85.812,08 − 500,00 − 1.000,00 + 1.000,00).
- **O pagamento da Passadeira pode não ter sido intencional.** Com o filtro "Pendentes" naquele momento, a ordem desenhada era Psicóloga, Passadeira, Diarísta, e a da lista inteira era Diarísta, Psicóloga, Passadeira: o botão da **Diarísta** (posição 2) abria a **Passadeira**. Depois disso, o mesmo botão (posição 1) abria a Psicóloga, o lote pago 24 segundos depois e estornado. A sequência é compatível com duas tentativas de pagar a Diarísta, mas só o usuário pode confirmar. Nenhum registro foi alterado.

## 3. Correção

**Tela** (`web/src/js/despesas-adaptacoes.js`, sem alterar o original):
- **Identidade de cada posição:** cada desenho da lista guarda o nome e a competência de cada agrupador desenhado. O clique usa a posição só para achar essa identidade, nunca para indexar outra lista. Um desenho novo descarta as posições do anterior.
- **Ocorrências por identidade:** as pendentes são as do agrupador com essa identidade na lista inteira do mês. O banco exige todas as pendentes das recorrências na competência, mesmo as escondidas por "vencimento até".
- **O modal** mostra o nome, a competência, as ocorrências e o total dessa identidade.
- **Nova conferência na confirmação:** se a lista foi recarregada com outras pendentes, a tela recusa antes de enviar ("A lista mudou desde a abertura") e recarrega ao fechar.
- **Pedido:** além das ocorrências e da conta, leva o lote mostrado: `descricao`, `competencia`, `recorrencias`, `quantidade` e `valor_total`.

**Adaptador** (`web/src/js/despesas-adaptador.js`): cada linha passa a ter `item_despesa_id` (a recorrência), e o pedido repassa o lote ao banco.

**Banco, migration `20261219090000`**, só a função `pagar_despesas_lote` (mesma assinatura, permissões e segurança; nenhuma tabela, coluna ou valor):
- **Escritor único:** continua a primeira verificação.
- **Identidade obrigatória:** pedido sem identidade válida é recusado (`LOTE_IDENTIDADE`). Isso inclui a tela publicada com a P20, que não a envia.
- **Correspondência exata:** as ocorrências precisam ser exatamente o lote mostrado. Senão, a recusa vem com o nome e a competência, sem pagar nada:
  - o nome de cada ocorrência, sem o " - DD/MM", igual ao mostrado;
  - as recorrências iguais às declaradas, nem a mais nem a menos;
  - a mesma competência, a mesma quantidade e o mesmo total.
- **Demais conferências:** continuam como na P20 (conta ativa do perfil, todas as pendentes, valores e situação). Cada ocorrência continua sendo paga por `pagar_despesa`, tudo ou nada.
- **Reversão** (`supabase/reversao/20261219090000_pagamento_lote_identidade_anterior.sql`): volta ao corpo da 1218.

## 4. Testes

**Banco** (`tests/test_supabase_pagamento_lote_identidade.py`, 18 casos). Cenário: duas recorrências "Diarista" (terça e sexta, R$ 200; 6 pendentes) e uma "Psicologa" (terça, R$ 250; 4 pendentes) em 02/2027.
- **Identidade divergente**, recusada sem gravar nada:
  - ocorrências da Psicóloga com o nome da Diarista;
  - recorrência da outra;
  - recorrências a mais;
  - outra competência, outra quantidade ou outro total;
  - ocorrências das duas recorrências no mesmo lote.
- **Pedido sem identidade válida** (como o da tela antiga), em 7 formas, recusado.
- **Identidade certa:** paga só a recorrência mostrada; a outra fica intacta até o seu próprio lote.
- **Segurança e reversão:**
  - o escritor único continua antes da identidade;
  - permissões (`authenticated` sim, `anon` não), `security definer` e `search_path` fixo;
  - a reversão volta ao corpo anterior sem mudar dados, e a reaplicação volta a exigir a identidade.

Os 18 casos da P20 (`tests/test_supabase_pagamento_lote.py`) passam a enviar a identidade como a tela nova.

**E2E** (`web/tests/e2e/despesas_pagamento_lote.spec.mjs`). Cenário: usuário E, com uma "Psicologa E" de R$ 250 às segundas somada às duas "Diarista E" de 02/2030.
- **Ordem trocada:** com as duas Diaristas mais recentes pagas, o filtro "Pendentes" inverte a ordem dos agrupadores. Cada botão abre a própria recorrência:
  - Diarista: 6 ocorrências, R$ 1.200,00;
  - Psicóloga: 4 ocorrências, R$ 1.000,00;
  - três vezes alternando, com "vencimento até", com a busca e sem filtros;
  - cancelar não paga nada.
- **Pagamento da Psicóloga com a ordem trocada:**
  - o pedido leva as 4 ocorrências dela, a conta escolhida e a identidade;
  - só ela é paga, com R$ 1.000,00 na conta escolhida;
  - a Diarista fica intacta.
- **Lista recarregada com o modal aberto e uma ocorrência paga em outra aba:** a tela recusa sem enviar nada, e ao fechar mostra as 8 restantes.
- **Prova do defeito:** com o `despesas-adaptacoes.js` publicado (`5b5e4e8`), o caso da ordem trocada falha como em produção. Esperado "Diarista E", recebido "Psicologa E".

## 5. Resultados

| Bateria | Resultado |
|---|---|
| Banco do lote (P21 + P20) | 36/36 |
| E2E do lote e de Despesas | 12/12 |
| Regressão por impacto (90 arquivos: Despesas, pagamentos e estornos, Recorrências, Contas Bancárias, faturas, saldos, Dashboard, escritor único, segurança) | 1.578 casos, 0 falhas (2 pulados: backup com PostgreSQL 17, binários ausentes) |
| Unitários do frontend | 92/92 |
| E2E completo, sem novas tentativas | 138/139. A falha foi `acesso.spec` "barra superior da moldura": `ERR_NO_BUFFER_SPACE` do Windows ao carregar `vendor/supabase.js`, sem relação com Despesas. Repetido sozinho: 9/9 |

## 6. Publicação

- **Ordem:** push, migration `20261219090000` antes do deploy e um deploy do frontend.
- **Entre a migration e o deploy:** a tela publicada (P20) não consegue pagar em lote. O banco recusa o pedido sem identidade, de propósito. O pagamento individual não muda.
- **Depois do deploy, com o usuário:**
  - confirmar se o pagamento da Passadeira (2515, 2516) foi intencional;
  - pagar a Diarista pelo lote corrigido.

## 7. Publicação e auditoria (08/11/2026)

- **Commits:** `0edfe88` (documentação da publicação 1217 + 1218), `43a52d9` e `de5bf20`. Push `5b5e4e8..de5bf20`, em avanço direto.
- **Migration `20261219090000`:** aplicada sozinha, com o plano de teste listando só o seu arquivo. A conferência:
  - só `pagar_despesas_lote` alterada, nenhuma função criada ou removida, nenhum dado existente mudou;
  - o corpo publicado é idêntico ao do arquivo (md5 `a1640a42…`), começa por `exigir_escrita_novo` e tem a conferência de identidade;
  - executável só por `authenticated`, `security definer` e `search_path` fixo, sem bloqueios de segurança;
  - produção com 60 migrations.
- **Deploy `04dd7c99`** (build do `de5bf20`): 165 arquivos servidos iguais ao build; 17 páginas protegidas redirecionam ao login sem erros de JavaScript ou de CSP.
- **Dados (antes e depois, somente leitura):** as 86 tabelas com os mesmos dados.
  - 45 movimentos, conta 96 com R$ 85.312,08 e conta 97 com R$ 12.469,48;
  - os pagamentos e estornos da Psicóloga, com cada débito e o seu estorno vinculados;
  - a Passadeira paga, as 6 pendentes da Diarista e as recorrências;
  - faturas, financiamento, Dashboard e despesas de 11/2026 a 01/2027 iguais.
- **Testes:** os da seção 5, sem nova alteração de código depois deles.
