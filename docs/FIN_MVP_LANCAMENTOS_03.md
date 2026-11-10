# FIN-MVP-LANCAMENTOS-03 — Conciliação de abastecimentos e prévia de parcelamento

**Situação (09/11/2026): publicado em conjunto (partes A e B).**
- Commit `080e26b`, migration `20261222090000` (63 migrations), deploy `d7073ff5`.
- Auditoria somente leitura aprovada (seção C.9).
- A associação de abastecimentos será homologada na interface quando houver um abastecimento real e a compra correspondente.

**Base de produção:** `cd244b7` (62 migrations, última `20261221090000`).

| Parte | Nível | Banco | Situação |
| --- | --- | --- | --- |
| A — abastecimento × compra importada | N4 | migration `20261222090000`, só funções | pronta para homologação |
| B — P14, prévia das parcelas | N2–N3 | nenhuma mudança (usa `previa_compra`, que já existia) | pronta para homologação |

---

# PARTE A — Abastecimento × compra importada

## A.1 Diagnóstico do vínculo atual

- **Tabela `financeiro.abastecimento`** (migration 1215): evento operacional, com `lancamento_id` (compra) ou `conta_id` (conta), nunca os dois.
  - Índices únicos impedem que uma compra ou conta tenha dois abastecimentos.
  - Excluir a despesa só desfaz o vínculo (`on delete set null`).
- **Funções já prontas no banco (1215), sem tela:**
  - `candidatas_abastecimento`: mesmo valor, compra de 3 dias antes a 10 depois, mesmo cartão e cartão físico quando informados; marca `ambigua` e nunca escolhe sozinha;
  - `vincular_abastecimento`: recusa valor, cartão ou cartão físico divergente e despesa já usada; trava o abastecimento; grava histórico;
  - `desvincular_abastecimento`: com histórico.
- **Novo Lançamento** (1217, `salvar_lancamento_abastecimento`): despesa e abastecimento numa transação. A compra parcelada não recebe abastecimento.
- **Importação de cartão** (`analisar_importacao_cartao` e `importar_fatura_cartao`):
  - nunca olhava abastecimentos;
  - já reconhece a compra lançada antes (manual ou de outra importação) e a retira da efetivação (status `conciliado`);
  - por isso, um abastecimento já vinculado a essa compra continua com uma despesa só.
- **Mobilidade:** a coluna Despesa mostrava só "Vinculada" ou "Aguardando", sem a compra e sem ações.
- **Produção (somente leitura):** 0 abastecimentos e 0 cartões físicos cadastrados. Nada real é afetado.

## A.2 Solução

Regra: o abastecimento é o evento operacional; a compra é a obrigação financeira. Nada cria, altera ou exclui compra; o vínculo usa `vincular_abastecimento`.

**Migration `20261222090000`** (md5 `bc9291b0…`, só LF), só funções; nenhuma tabela, coluna ou dado muda.

- **`abastecimentos_da_importacao(perfil, cartão, linhas)`** (para o usuário logado, somente leitura):
  - recebe as linhas da análise da importação e devolve, por linha à vista, a situação do abastecimento compatível;
  - usa o mesmo critério das candidatas;
  - SUGERIDA: um abastecimento livre, a confirmar;
  - MULTIPLA: vários, ou o mesmo abastecimento servindo a mais de uma linha; escolha manual;
  - CONFIRMADA: a compra reconhecida já tem o abastecimento;
  - CONFLITO: há abastecimento compatível, mas vinculado a outra despesa;
  - linha parcelada, de crédito, de recorrência, duplicada ou ignorada não recebe sugestão.
- **`importar_fatura_cartao`** (substituída; o restante do corpo é o publicado, sem alteração):
  - a linha pode levar `abastecimento_id`, que é a escolha do usuário;
  - na mesma transação, o abastecimento é vinculado à compra criada ou à compra já lançada que a análise reconheceu;
  - sem escolha, nada muda;
  - escolha em linha parcelada, de crédito ou de recorrência é recusada (`ABASTECIMENTO_LINHA`);
  - qualquer recusa do vínculo desfaz a importação inteira, sem gravação parcial.
- **`mob_vincular_importacao`** (interna):
  - aplica as regras de `vincular_abastecimento`, mais o período das candidatas (`ABASTECIMENTO_PERIODO`) e o meio de pagamento;
  - abastecimento já vinculado à mesma compra: nada muda.
- **`abastecimentos_veiculo_tela`** (substituída): cada abastecimento ganha `despesa`, com descrição, data, valor, fatura, cartão e se foi importada.
- **`mob_despesa_do_abastecimento`** (interna): recebe os ids, não a linha, para não depender do tipo da tabela, que a reversão da 1215 remove.

**Reversão:** `supabase/reversao/20261222090000_lancamentos_abastecimento_anterior.sql`.
- Restaura as duas funções com o texto lido da produção (sem CR, exato) e remove as três novas.
- Os vínculos gravados continuam, porque são os de `vincular_abastecimento`.

## A.3 Interface

- **Importar Cartão** (`importar_cartao.js` e `importar-cartao-adaptador.js`):
  - a sugestão aparece na própria linha, discreta;
  - SUGERIDA: "Vincular ao abastecimento: veículo · data · valor · litros", com caixa desmarcada;
  - MULTIPLA: um seletor com "Sem abastecimento";
  - CONFIRMADA ou CONFLITO: só informa;
  - a linha já lançada, retirada da efetivação, também mostra a sugestão;
  - a importação não espera a confirmação: sem marcar, importa como antes.
- **Mobilidade, histórico de abastecimentos** (`veiculos.js`, `mobilidade-adaptador.js`, `mobilidade.html`):
  - a coluna Despesa mostra a compra vinculada (descrição e fatura, com data, valor e origem no título) ou "Aguardando compra";
  - ação compacta "Vincular compra" abre o modal com as candidatas: data, descrição, valor e indícios (mesmo cartão físico, estabelecimento, dias);
  - com uma candidata, ela vem marcada;
  - "Desvincular compra" pede confirmação.
  - Os botões têm o mesmo tamanho dos demais.
  - Sem o campo `despesa` (Flask), a coluna fica como antes.

## A.4 Proteções contra duplicidade

| Risco | Proteção |
| --- | --- |
| A importação criar outra despesa para o mesmo abastecimento | o vínculo só liga; a compra já lançada é reconhecida pela análise e não é gravada de novo |
| Mesmo valor sem relação | nunca vincula sozinho: a sugestão precisa ser marcada; com vários compatíveis, a escolha é manual |
| Um abastecimento em duas compras | `vincular_abastecimento` recusa o já vinculado (`ABASTECIMENTO_VINCULADO`) |
| Uma compra em dois abastecimentos | índice único em `lancamento_id`, também em corrida (teste de concorrência) |
| Veículo presumido pela fatura | o vínculo é com o abastecimento escolhido, que tem o veículo |
| Cartão físico diferente | sem sugestão; recusa (`CARTAO_DIVERGENTE`) |
| Fora do período ou de outro perfil | recusa e a importação inteira é desfeita |
| Repetir a importação | a chave devolve o resultado gravado, sem segundo vínculo |
| Pagamentos, movimentos e saldos | nenhum é criado ou alterado; vincular compra de fatura paga não muda o financeiro |

## A.5 Testes de integridade

`tests/test_supabase_lancamentos_abastecimento.py`, 25 casos, todos aprovados:
- segurança das três funções;
- prévia: sugestão sem gravar, sem correspondência, dois veículos com o mesmo valor, o mesmo abastecimento para duas linhas, cartões físicos distintos, parcelada e crédito sem sugestão, conflito com outra despesa;
- confirmação:
  - vincula sem duplicar e sem movimento;
  - sem confirmação, não vincula;
  - a compra já lançada recebe o vínculo, sem compra nova;
  - a compra reconhecida já vinculada aparece como confirmada;
  - dois veículos na mesma fatura;
  - recusas de parcelada, período e valor desfazem tudo;
  - outro perfil é recusado;
  - importação repetida;
  - fatura paga;
- Mobilidade: mostra, vincula e desvincula com a compra intacta; duas vinculações simultâneas da mesma compra; importação e vínculo manual simultâneos;
- reversão e reaplicação.

---

# PARTE B — P14, prévia das parcelas

## B.1 Diagnóstico do formulário atual

- O modal removido no MVP-FIN-AJUSTES-01 (P11) mostrava a prévia; o formulário de Novo Lançamento não mostrava (pendência P14).
- **O banco já tinha `previa_compra`:**
  - planeja pelo mesmo `plano_compra` que `criar_compra` usa para gravar;
  - devolve número, total, competência da fatura, valor, se a parcela foi redirecionada de fatura paga, faturas consolidadas e a sugestão pelo fechamento.
  - O adaptador de Lançamentos só a usava para confirmar fatura consolidada.
- Não foi preciso mudar o motor nem o banco.

## B.2 Prévia implementada

`web/src/js/lancamentos-parcelas.js`, script clássico. O `lancamentos.js` original, comum ao Flask, não muda.
- **Quando aparece:** em compra nova no cartão com 2 ou mais parcelas, abaixo de Parcelas e Mês da fatura.
- **Formato:** tabela compacta (Parcela, Competência e Valor à direita), com o total no rodapé, linhas de 26 px e rolagem limitada a 168 px.
- **Avisos:** parcela que vai para a próxima fatura porque a de origem está paga (marcada com \*) e fatura consolidada (pedirá confirmação ao salvar).
- **Atualização:** reage a valor, parcelas, data, cartão, categoria e mês da fatura, inclusive quando o mês é trocado pela sugestão do fechamento.
  - Consulta com 250 ms de espera; a resposta antiga é descartada.
  - Nada é gravado; limpar ou cancelar não cria registro.
- **Descrição e categoria:** não mudam o plano, só a validação. Ainda vazias, a prévia usa um texto provisório e a primeira categoria ativa; ao salvar valem as do formulário.
- **Cartão sem vencimento configurado:** mostra o motivo do banco.

## B.3 Regras de cálculo e competência

São as do banco (`plano_compra`); a tela não tem fórmula própria.
- R$ 100,00 em 3: R$ 33,34 + R$ 33,33 + R$ 33,33, soma exata.
- Competências seguidas a partir do mês da fatura, com virada de ano.
- Fatura paga no meio: a parcela vai para a próxima aberta.
- A sugestão pelo fechamento orienta a escolha do mês, e a prévia usa o mês escolhido, como a gravação.

## B.4 Correspondência com o banco

`tests/test_supabase_previa_parcelas.py`, 10 casos, todos aprovados:
- à vista, 2, 3 (centavos), 12 e virada de ano: a prévia é exatamente o que `criar_compra` grava (número, total, competência e valor), e a soma confere;
- fatura paga no meio: prévia e gravação iguais, com a redireção indicada;
- sugestão pelo fechamento, mudança de quantidade, data e cartão;
- cartão sem vencimento: recusa;
- a prévia nunca grava.

**E2E:** a prévia mostrada é comparada com as parcelas gravadas.

## B.5 Testes da interface

`web/tests/e2e/lancamentos_03_parcelas.spec.mjs`, em 1366 e 1920:
- à vista sem prévia, 3 parcelas com centavos, 12 com rolagem limitada, valor e quantidade alterados;
- de volta a 1, a prévia some;
- limpar o formulário não grava;
- a gravação confere com a prévia.

---

# PARTE C — Consolidação

## C.1 Arquivos alterados

| Parte | Arquivos |
| --- | --- |
| A | `supabase/migrations/20261222090000_financeiro_lancamentos_abastecimento.sql`, `supabase/reversao/20261222090000_lancamentos_abastecimento_anterior.sql`, `frontend/static/js/importar_cartao.js`, `web/src/js/importar-cartao-adaptador.js`, `web/src/css/importar-cartao-adaptacoes.css`, `frontend/static/js/veiculos.js`, `frontend/static/css/veiculos.css`, `web/src/js/mobilidade-adaptador.js`, `web/src/paginas/mobilidade.html`, `web/tests/unit/build.test.mjs`, `tests/test_supabase_lancamentos_abastecimento.py`, `tests/test_supabase_mobilidade_escrita.py` (ordem de reversão), `web/tests/e2e/lancamentos_03_abastecimento.spec.mjs` |
| B | `web/src/js/lancamentos-parcelas.js`, `web/src/js/lancamentos-adaptador.js` (rota da prévia), `web/src/paginas/lancamentos.html`, `web/src/css/lancamentos-adaptacoes.css`, `tests/test_supabase_previa_parcelas.py`, `web/tests/e2e/lancamentos_03_parcelas.spec.mjs` |

## C.2 Funções e tabelas envolvidas

- **A:**
  - novas: `abastecimentos_da_importacao`, `mob_vincular_importacao` e `mob_despesa_do_abastecimento`;
  - substituídas: `importar_fatura_cartao` e `abastecimentos_veiculo_tela`;
  - usadas como estão: `vincular_abastecimento`, `desvincular_abastecimento`, `candidatas_abastecimento`, `analisar_importacao_cartao` e `mob_abastecimento`;
  - tabelas: `financeiro.abastecimento` e `abastecimento_historico`, só o vínculo; `public.lancamento_agregado`, só leitura.
- **B:** `previa_compra` e `plano_compra` (sem alteração), e `criar_compra` na gravação, como antes.

## C.3 Ensaio na cópia fiel da produção (parte A)

- **Cópia:** IDÊNTICA, com 62 migrations.
- **Funções substituídas:** iguais ao texto da reversão, que é o estado publicado.
- **Migration:** nenhum dado alterado; 3 funções novas, 2 alteradas e nenhuma removida.
- **Leituras:** o histórico de abastecimentos ficou igual, só com o campo `despesa` a mais; a sugestão, sem abastecimentos reais, vem vazia.
- **Segurança:** nenhuma função `security definer` sem `search_path` e nenhuma executável por `anon`; só `abastecimentos_da_importacao` é executável por `authenticated`.
- **Reversão:** sem mudança de dados, com as funções iguais ao estado anterior.
- **Reaplicação:** sem mudança de dados, com as funções iguais às da primeira aplicação.

## C.4 Testes por impacto

| Bateria | Seleção (por dependência) | Resultado |
| --- | --- | --- |
| A: nova (`test_supabase_lancamentos_abastecimento.py`) | integridade do vínculo | 25/25 |
| B: nova (`test_supabase_previa_parcelas.py`) | correspondência prévia × gravação | 10/10 |
| Regressão direcionada | Todas as suítes que usam `importar_fatura_cartao` ou `analisar_importacao_cartao`, função central ampliada (importação, fixas, despesas fixas, créditos, Nubank créditos e parceladas, cartões múltiplos, recorrência no cartão, escritor único, reversão do lote, integração 1123–1127, consolidação de categorias); abastecimento (Mobilidade e Lançamentos), integridade de Mobilidade; cartões e Lançamentos (compra e prévia) | 433/436 |
| As 3 falhas | Testes antigos de reversão da 1215: a função nova recebia a linha do abastecimento e dependia do tipo da tabela. Corrigido na causa (a função passou a receber os ids). Repetidas as suítes afetadas | 154/155, depois 1/1 |
| A falha restante | Teste de reversão até a 1127, que agora reverte a 1222 primeiro e a reaplica no fim, como já fazia com a 1220 | 1/1 |
| Unitários do frontend | todos | 92/92 |
| E2E do MVP | `lancamentos_03_parcelas` e `lancamentos_03_abastecimento` | 4/4 |
| E2E afetados | importação (cartão, fixas, parceladas, créditos), Lançamentos (tela e abastecimento), Mobilidade (tela e projeções) e o do MVP | 26/26 |

**Não executados, com justificativa:**
- Suíte completa e E2E completo: não há mudança estrutural abrangente.
  - Parte A: só funções da importação e da Mobilidade, todas cobertas pela seleção.
  - Parte B: só a tela de Lançamentos.
- Despesas, Recorrências, Receitas, Financiamentos, Patrimônio, Documentos e Dashboard: não dependem das funções alteradas. Pagamentos, estornos, saldos e movimentos não foram tocados.

**Defeito real encontrado pelo E2E e corrigido:** o modal "Vincular compra" abria por baixo do histórico de abastecimentos (mesmo `z-index`).

## C.5 Evidências visuais

Em `scratchpad/l03/evidencias`: `p14_previa_1366.png`, `p14_previa_1920.png`, `l03_importacao_sugestao.png`, `l03_mobilidade_vincular_1366.png` e `l03_mobilidade_vinculada_1366.png`.

## C.6 Riscos remanescentes

- **A — data:** a sugestão usa a janela das candidatas (compra de 3 dias antes a 10 depois do abastecimento). Uma compra lançada pelo banco fora dela não é sugerida; o vínculo pela Mobilidade usa a mesma janela.
- **A — CONFLITO:** só informa. Se o abastecimento foi vinculado à despesa errada, o usuário desvincula na Mobilidade e vincula a certa.
- **A — linhas duplicadas:** linha duplicada na importação (a mesma compra reimportada) não recebe sugestão. A compra já importada pode ser vinculada na Mobilidade.
- **B:** a prévia depende do mês da fatura escolhido. Com o fechamento não confirmado, vale o mês do formulário, como na gravação.

## C.7 Commits locais

- parte A: banco, tela e testes do abastecimento × compra importada;
- parte B: prévia das parcelas;
- documentação: este arquivo e o ROADMAP.

## C.8 Prontidão para publicação

As duas partes estão prontas para homologação e podem ser publicadas separadamente.
- **A:** push, aplicar só `20261222090000`, build e deploy.
  - A tela publicada continua funcionando entre a migration e o deploy: as funções novas só são chamadas pela tela nova, e a importação sem `abastecimento_id` segue igual.
- **B:** só build e deploy, sem migration.

## C.9 Publicação e auditoria (09/11/2026)

Publicação conjunta das partes A e B, autorizada pelo usuário em 09/11/2026.

- **Conferências antes do push:**
  - `origin/main` em `cd244b7`; os commits publicados são `736cad4` (documentação da P22), `6ff3379` (A), `db5dc7d` (B) e `080e26b` (documentação);
  - produção com 62 migrations, última `20261221090000`; a 1222 era a única pendente; md5 `bc9291b0…` e só LF;
  - as 2 funções substituídas estavam iguais ao texto da reversão; as 3 novas não existiam;
  - 0 abastecimentos, 0 registros de histórico e 0 cartões físicos;
  - nenhuma tabela com dados diferentes desde o fim da regularização da P22 (e do ensaio).
- **Push** `cd244b7..080e26b`, em avanço direto.
- **Migration `20261222090000`:** aplicada sozinha, com o dry-run listando só o seu arquivo; 63 migrations.
  - Estrutura: nenhuma tabela nova ou removida; 3 funções novas e as 2 substituídas, com os 5 corpos idênticos ao arquivo e `search_path` vazio.
  - Execução: só `abastecimentos_da_importacao` executável por `authenticated`, e nenhuma execução perdida.
  - Dados e segurança: nenhum dado existente mudou e não há bloqueios de segurança.
- **Deploy `d7073ff5`** (Source `080e26b`): 169 arquivos servidos iguais ao build, sem segredos; navegação anônima sem problemas.
- **Homologação** em sessão somente leitura, como o titular, sem nenhuma compra, importação ou abastecimento:
  - **parte A:**
    - a sugestão, sem abastecimentos reais, vem vazia: nenhum vínculo sem confirmação;
    - a Mobilidade responde com a despesa vinculada;
    - os índices únicos (uma compra ou conta por abastecimento) estão ativos;
    - a importação sem vínculo segue o corpo publicado (o mesmo homologado nos testes);
  - **parte B:** `previa_compra` no Master Card - Black:
    - 3× R$ 100,00 = R$ 33,34 + 2× R$ 33,33;
    - 12× R$ 1.000,00 de 11/2026 a 10/2027;
    - 4× R$ 500,00 = 4× R$ 125,00;
    - soma exata em todos.
- **Dados (antes e depois, somente leitura):** as 88 tabelas com os mesmos dados.
  - Contas, compras, movimentos, saldos, faturas, créditos, financiamento, recorrências, abastecimentos e Dashboard iguais;
  - a regularização da P22 (contas, competências e totais) idêntica.
- **Testes:** os da seção C.4, sem alteração de código depois deles.
