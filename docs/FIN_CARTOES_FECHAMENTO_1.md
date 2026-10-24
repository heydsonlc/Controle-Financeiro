# FIN-CARTOES-FECHAMENTO-1 — Competência sugerida pelo fechamento do cartão

**Data:** 2026-10-23.

**Situação:** implementado e validado **localmente**:
- cluster PostgreSQL descartável (todas as migrations do repositório);
- arquivos SQLite temporários;
- processos Flask reais;
- E2E no harness local;
- dados fictícios.

**Autorização:** SCRIPT-CONTRATO V5 — FIN-CARTOES-FECHAMENTO-1 (decisões D1 a D6 aprovadas).

**Não foi feito:**
- migration no Supabase remoto;
- Alembic no `gastos.db` ou em qualquer banco persistente (inclusive `controle_financeiro_dev`);
- dados reais;
- commit, push ou publicação;
- pagamentos, estornos ou conciliação.

## 1. Regra de calendário

A competência da fatura é o **mês do vencimento**. Para uma compra na data civil `D`, com fechamento `F`, vencimento `V` e regra `R`:

1. **Ciclo:** o fechamento do mês de `D` é o dia `F` desse mês. Se o mês for mais curto, vale o **último dia** (29 a 31 → 28/29/30).
2. **Compra depois do fechamento**, ou **no próprio dia com `R = PROXIMO`**: vai para o ciclo seguinte (o fechamento do mês seguinte).
3. **Vencimento:** é o primeiro dia `V` depois do fechamento do ciclo. Fica no mesmo mês se `V > F`, ou no mês seguinte se `V ≤ F`. Também usa o último dia nos meses curtos.
4. **Ciclo ambíguo:** se o mês curto empurra o vencimento para o mesmo dia do fechamento ou antes dele, **não há sugestão** e nada é atribuído em silêncio. Exemplo: `F = 29`, `V = 30` em fevereiro, quando os dois viram 28 ou 29. Isso só acontece no mês afetado.
5. **Regra do dia do fechamento (D1):** `PROXIMO` (padrão) ou `ATUAL`. Fica gravada por cartão e é explícita.

Exemplos (fecha 25, vence 5):

| Compra | `PROXIMO` | `ATUAL` |
|---|---|---|
| 24/10/2026 | 11/2026 | 11/2026 |
| 25/10/2026 (dia do fechamento) | **12/2026** | **11/2026** |
| 26/10/2026 | 12/2026 | 12/2026 |
| 26/12/2026 (virada de ano) | 02/2027 | 02/2027 |

**Fechamento igual ao vencimento não é presumido confiável.** O formulário antigo do Flask gravava `dia_fechamento = dia_vencimento`, então todo cartão existente está **não confirmado** (`fechamento_confirmado = false`). Sem confirmação explícita não há sugestão. Depois de confirmado, `F = V` vale como um ciclo normal: o vencimento cai no mês seguinte ao fechamento.

**Data civil:**
- o banco recebe uma `date`;
- o Flask converte `datetime` com fuso para a data de Brasília (`CartaoService.data_civil`);
- as telas usam a data local, e não `toISOString()`, que é UTC e trocaria o dia perto da meia-noite.

A regra está escrita duas vezes, idênticas: `financeiro.competencia_da_compra` (SQL) e `CartaoService.competencia_da_compra` (Python). Uma grade de 547 dias × 12 fechamentos × 11 vencimentos × 2 regras dá **zero divergências** (`test_grade_identica_no_flask_e_no_postgresql`).

## 2. Comportamento

- **Sugestão com ajuste manual (D2):**
  - a tela mostra a fatura sugerida, com o fechamento e o vencimento do ciclo, e recalcula ao trocar cartão ou data;
  - **a escolha manual nunca é sobrescrita**; o botão "Usar a sugerida" volta à sugestão;
  - a compra grava o mês escolhido (`mes_fatura`) e a sugestão do sistema (`lancamento_agregado.mes_fatura_sugerido`, por parcela);
  - a data da compra não muda.
- **Sem sugestão:**
  - **cartão não confirmado ou sem dias:** o campo fica no mês padrão de antes (Flask: o mês do filtro; novo aplicativo: o mês na tela), com aviso. Nunca fica com o mês que outro cartão ou outra data sugeriram;
  - **ciclo ambíguo:** o campo é **esvaziado** e a escolha é obrigatória;
  - **no banco:** `criar_compra` sem `mes_fatura` e sem sugestão é recusada com "Informe o mes da fatura: …" (HINT `SEM_SUGESTAO`).
- **Parcelamento (D3):**
  - a 1ª parcela vai para a competência escolhida (ou sugerida) e as seguintes avançam um mês cada;
  - fatura paga no caminho: o desvio existente vale e `mes_fatura_original` guarda a competência pretendida;
  - **nenhuma parcela antiga, data ou fatura é recalculada.** A nova configuração vale só para as operações seguintes.
- **Recorrências e importação (D5):** não mudaram.

## 3. Fatura consolidada (D6)

- **FECHADA** (consolidada pelo Flask) só recebe compra com a **confirmação explícita da operação**: uma lista `confirmar_consolidadas` com `{fatura_id, total_consolidado}` para cada fatura, com o total que o usuário viu.
- **Conferência no banco e no Flask, sob trava** (cartão → faturas, a ordem global do FIN-FATURA-INTEGRIDADE-1):
  - fatura que ficou consolidada depois da prévia é recusada;
  - total consolidado que mudou é recusado;
  - de duas inclusões simultâneas com a mesma confirmação, **a segunda é recusada**;
  - uma confirmação "global" ou de outra fatura não vale.
- **Com a confirmação:**
  - `valor_consolidado` passa a total anterior + valor incluído, e o executado é recalculado como antes;
  - cada inclusão gera um registro em `fatura_consolidada_inclusao`: fatura, cartão, perfil, competência, compra, lançamento, valor incluído, total anterior e novo, operação `COMPRA` ou `EDICAO`, origem `FLASK` ou `NOVO_APP`, usuário e data.
- **Sem a confirmação:**
  - nada é gravado;
  - **banco:** erro `P0001`, HINT `CONSOLIDADA`, DETAIL em JSON com a fatura e os totais;
  - **Flask:** HTTP **409** `CONFIRMAR_FATURA_CONSOLIDADA` com a lista das faturas.
- **Telas:**
  - **novo aplicativo:** uma caixa por fatura consolidada na prévia, marcada pelo usuário; a edição mostra a caixa quando o banco pede;
  - **Flask:** confirmação com os totais e reenvio.
- **Fatura paga continua protegida:** o desvio acontece antes, e a confirmação **não** abre uma fatura paga.
- **Mover uma compra para uma fatura consolidada** (edição à vista) exige a mesma confirmação e gera um registro `EDICAO`.
- **Outros caminhos do Flask que criam compra de cartão** (confirmar despesa prevista; criar lançamento a partir de documento) não têm tela de confirmação. Numa fatura consolidada eles agora **recusam** com HTTP 400 e a mensagem. Fora disso, nada mudou.

## 4. Cadastro do cartão (D4)

- **Flask:**
  - o formulário tem **dia do fechamento** e **dia do vencimento** independentes, a regra do dia e a caixa de confirmação;
  - a edição carrega os valores gravados;
  - o `PUT` **preserva** fechamento, vencimento e regra que não vierem no corpo e nunca deriva o fechamento do vencimento (antes, o Flask sobrescrevia o fechamento definido no novo aplicativo);
  - o cabeçalho do cartão mostra "Fecha dia X • vence dia Y" e o aviso "Fechamento a confirmar".
- **Novo aplicativo:** regra do dia e confirmação no cadastro; na lista, o aviso "Fechamento a confirmar" e a regra no detalhe.
- **Confirmação (nos dois):**
  - vale o valor enviado;
  - sem valor enviado, mudar um dia ou a regra **desconfirma**;
  - as telas desmarcam a caixa quando um dia ou a regra mudam.
- **Vencimento 29 a 31 no Flask:** `get_or_create_fatura` usa o último dia válido nos meses curtos (fev/2027 → 28; fev/2028 → 29; abr → 30). O novo aplicativo já fazia isso.

## 5. Banco de dados

**Supabase `20261030090000_financeiro_cartoes_fechamento.sql`** (local, **não aplicada** no remoto):

- **Colunas novas:**
  - `config_agregador.compra_no_fechamento varchar(10) not null default 'PROXIMO'` (check `ATUAL`/`PROXIMO`);
  - `config_agregador.fechamento_confirmado boolean not null default false`;
  - `lancamento_agregado.mes_fatura_sugerido date` (nula).
- **Tabela nova:** `public.fatura_consolidada_inclusao`, com RLS e sem privilégios para `anon`/`authenticated` (SEC-SUPABASE-PUBLIC-1).
- **Funções internas** (sem `EXECUTE` para o navegador):
  - `competencia_da_compra`;
  - `situacao_fatura`;
  - `sugestao_competencia`;
  - `exigir_confirmacao_consolidada`.
- **Exposta, só leitura:** `sugerir_competencia(perfil, cartão, data)`. Confere o perfil e o cartão do perfil e acrescenta a situação da fatura sugerida.
- **Atualizadas:**
  - `plano_compra`: o mês é opcional, usa a sugestão e devolve o sugerido, a situação e o total consolidado;
  - `previa_compra`: devolve a sugestão e as consolidadas;
  - `criar_compra` e `editar_compra`: D6 e o sugerido;
  - `ler_dados_cartao`, `criar_cartao`, `editar_cartao` e `cartoes_do_perfil`: regra e confirmação.
- **Assinaturas e privilégios** das funções existentes foram mantidos.

**Alembic `c7e2a9d4b8f3`** (desce de `f1c4d8e2a7b9`, cabeça única):
- as mesmas colunas e a tabela, idempotente ("a que rodar primeiro cria");
- no PostgreSQL com os papéis do Supabase, RLS e revogação;
- testada **só** em SQLite temporário e cópia PostgreSQL descartável: sobe, sobe de novo, preserva os dados e desce;
- **não executada** no `gastos.db` nem no `controle_financeiro_dev`.

**Padrões conservadores:**
- nenhum cartão existente fica confirmado;
- nenhuma compra recebe sugestão retroativa;
- nenhum valor, competência ou fatura existente muda.

**Flask num banco sem a migration** (o `gastos.db` hoje): funciona como antes.
- As colunas são `deferred` e o serviço confere se existem (`suporta_fechamento_configuravel`, `suporta_competencia_sugerida`, `suporta_auditoria_consolidada`).
- Cadastro, edição (fechamento preservado), listagem e compra funcionam.
- Não há sugestão (situação `NAO_CONFIRMADO`), e a regra e a confirmação ficam ocultas na tela.
- A inclusão em fatura consolidada é **recusada** ("migration pendente"), porque não haveria auditoria.
- A verificação das colunas fica em cache por processo: **depois de aplicar a Alembic, reinicie o Flask.**

## 6. Testes

**`tests/test_cartoes_fechamento.py`: 67 testes** (62 do módulo, 1 da conferência da migration e 4 da trava de projeto, §10).

| Bloco | Cobertura |
|---|---|
| A. Calendário | 20 casos do contrato: antes, no dia e depois do fechamento; `PROXIMO` e `ATUAL`; fechamento 28 a 31; fevereiro comum e bissexto; virada de ano; vencimento no mesmo mês e no seguinte; `F = V`. Mais 6 ciclos ambíguos ou inválidos, o ambíguo só no mês afetado, data civil perto da meia-noite (23:30 em Brasília = 02:30 UTC) e a grade Python = SQL |
| B. Parcelamento | 1ª parcela na sugerida e as seguintes mensais atravessando dezembro; ajuste manual com data e sugestão preservadas; fatura intermediária paga (desvio com original e sugerido); sem mês e sem sugestão (não confirmado e ambíguo); nova configuração sem tocar compras e faturas antigas (md5); **Flask = novo aplicativo** nas mesmas parcelas |
| C. Situação da fatura (D6) | Aberta sem confirmação; consolidada sem confirmação (nada muda, HINT e DETAIL); com confirmação (totais e auditoria); confirmações erradas; paga protegida mesmo com confirmação; situação que muda entre a prévia e a gravação; **duas inclusões concorrentes** (uma passa, uma é recusada, total 50); mover para consolidada na edição; Flask 409/201 e auditoria `FLASK`; Flask `PUT` para consolidada |
| D. Compatibilidade | Cartão criado no Flask e editado no novo aplicativo; criado no novo e editado no Flask (fechamento preservado; desconfirma ao mudar um dia; reconfirma); desconfirmação no novo aplicativo; não confirmado sem sugestão nos dois; **sugestão igual pelas duas APIs** (inclusive a situação FECHADA) |
| Privilégios | Navegador sem acesso às funções internas nem à auditoria; `sugerir_competencia` recusa anônimo, outro perfil e cartão de outro perfil |
| E. Alembic | Cabeça única; SQLite e PostgreSQL fictícios: sobe, idempotente, nada confirmado, dados preservados, desce |
| F. Flask | Vencimento 29 a 31 em meses curtos; inclusão consolidada recusada sem auditoria; **banco sem a migration** funcionando como antes |

**Ajuste de teste:** `test_fatura_integridade.py::test_fatura_fechada_nao_e_tratada_como_paga`.
- **Antes:** a fatura FECHADA recebia a compra sem confirmação.
- **Agora (D6):** sem confirmação, recusa sem gravar nada; com a confirmação do total visto, a compra entra no mesmo mês (sem desvio, porque a fatura não é paga) e `valor_consolidado` passa de 0 a 100. Movimentos e saldos continuam idênticos.

**Ajuste de teste (D4):** `test_supabase_recorrencia.py` (3 testes de equivalência com o Flask).
- **Antes:** a fatura do cartão 910 em 04/2027 (vencimento 31) estava classificada como "correção intencional": o Flask não conseguia criá-la (`date(2027, 4, 31)`) e só o novo motor a criava.
- **Agora:** o Flask cria a fatura com vencimento 30/04 e o registro fica **idêntico** ao do novo motor. A entrada saiu da lista de divergências e entrou na dos registros iguais. Com o Flask gerando primeiro, o novo motor não tem mais nada a gerar e nada é duplicado.

**Frontend:**
- **`web/tests/unit/fechamento.test.mjs`** (8 testes) cobre o módulo puro `web/src/js/fechamento.js`:
  - textos da sugestão;
  - manual × sugerida;
  - consolidada e paga;
  - situações sem sugestão;
  - mês sem sugestão;
  - confirmação;
  - erro `CONSOLIDADA`.
- **`build.test.mjs`:** `sugerir_competencia` entrou na lista de RPCs só de leitura.
- **E2E `web/tests/e2e/fechamento.spec.mjs`** (celular, usuário B no Perfil B):
  - cadastro confirmado;
  - mudança de dia que desconfirma, com o aviso, e a reconfirmação;
  - sugestão antes, no dia e depois do fechamento;
  - escolha manual preservada e "Usar a sugerida";
  - compra;
  - consolidação pelo **gancho do harness local** (`POST /__e2e__/consolidar`, só no banco descartável);
  - compra recusada sem marcar a caixa e aceita com ela;
  - fatura Fechada com R$ 110,00;
  - inativação.
  - O teste é pulado fora do harness local (`CF_E2E_LOCAL`), porque o novo aplicativo não consolida faturas.
- **Correção encontrada pelo E2E:** a prévia da compra era apagada assim que um campo mudava. O `change` do campo de valor sai no *mousedown* do Salvar, então o botão subia no meio do clique e o envio se perdia. Agora o conteúdo só é trocado quando a resposta chega.
- **Telas do Flask** (`cartoes.html`/`cartoes.js`, `lancamentos.html`/`lancamentos.js`): o Flask não tem testes de JavaScript. A sintaxe foi conferida com `node --check`, e o comportamento do back-end que elas usam está coberto nos blocos C e D. O E2E antigo do Flask está quebrado desde o SEG-1 (preexistente).

**Regressão:** ver o §9.

## 7. Compatibilidade e riscos

- **Supabase remoto:** continua com as versões anteriores até `20261030090000` ser aplicada. O novo aplicativo publicado chama `sugerir_competencia`, que só existe depois dela, e trata a falha como "não foi possível sugerir" (o mês continua editável). **Publicar o frontend só depois da migration remota.**
- **`scripts/supabase_cartoes_real.py` (cenário 17):** atualizado na RETOMADA-CASA-2 para a D6 (confirmação, auditoria, reuso recusado) e ensaiado localmente; ainda não commitado.
- **Recorrências, importação e edição no Flask:** resolvidos no FIN-CARTOES-D6-INTEGRIDADE-1 (§11).
- **Fora do escopo:** `lancamentos.js`, na confirmação de recebimento (receitas), ainda usa `toISOString()` para a data do dia.

## 8. Arquivos

**Back-end e banco:**
- `backend/models.py`
- `backend/services/cartao_service.py`
- `backend/routes/cartoes.py`
- `supabase/migrations/20261030090000_financeiro_cartoes_fechamento.sql` (novo)
- `migrations/versions/c7e2a9d4b8f3_cartoes_fechamento.py` (novo)

**Telas do Flask:**
- `frontend/templates/cartoes.html`
- `frontend/static/js/cartoes.js`
- `frontend/static/css/cartoes.css`
- `frontend/templates/lancamentos.html`
- `frontend/static/js/lancamentos.js`
- `frontend/static/css/lancamentos.css`

**Novo aplicativo:**
- `web/src/js/cartoes.js`
- `web/src/js/fechamento.js` (novo)
- `web/src/css/app.css`

**Testes:**
- `tests/test_cartoes_fechamento.py` (novo)
- `tests/test_fatura_integridade.py`
- `tests/test_supabase_recorrencia.py` (ajuste D4)
- `tests/test_sec_supabase_public.py` (ajuste do rollback para a revisão da proteção)
- `web/tests/unit/build.test.mjs`
- `web/tests/unit/fechamento.test.mjs` (novo)
- `web/tests/e2e/fechamento.spec.mjs` (novo)
- `web/tests/e2e/run_e2e.py` (gancho só de teste)

**Documentação:**
- `docs/FIN_CARTOES_FECHAMENTO_1.md` (novo)
- `docs/ROADMAP.md` (só a linha do FIN-CARTOES-FECHAMENTO-1)

## 9. Regressão

Validado com o **TESTES-IMPACTO-1** (nível 2). Seleção, motivos, evidências e tempos estão em `docs/TESTES_IMPACTO_1.md` §9.

| Conjunto | Testes | Resultado |
|---|---|---|
| Etapa "financeiros" da suíte (8 arquivos reaproveitados, mesma versão do código e dos testes) | 244 | 244 aprovados |
| Bateria direcionada: pytest (43 arquivos, inclui `test_supabase_recorrencia` já corrigido) | 596 | 594 aprovados; 1 falha preexistente (`test_veiculos_mobilidade_2b`); 1 falha de premissa de teste (`test_sec_supabase_public`, abaixo) |
| `test_sec_supabase_public.py` depois da correção | 16 | 16 aprovados |
| Web unit | 15 | 15 aprovados |
| Web E2E local (8 specs) | 48 | 48 aprovados |

**Ajuste de teste (Alembic):** `test_sec_supabase_public.py::test_ciclo_completo_de_rollback_restaura_estado_exato`.
- O teste do rollback da SEC-SUPABASE-PUBLIC-1 subia o Alembic até `head`. Com `c7e2a9d4b8f3`, `head` passou a criar `fatura_consolidada_inclusao`, que o rollback da SEC não desfaz (nem deve).
- **Correção:** o teste agora sobe só até a revisão da proteção (`c4f7a2d91b3e`).
- As invariantes em `head` (RLS, sem privilégios, sequências, tabela nova não exposta) continuam nos demais testes do módulo e **passaram com a tabela nova**.

**Suíte completa (nível 3):** não executada neste MVP. Fica para antes da publicação e da migration remota (FIN-CARTOES-FECHAMENTO-REAL-1), como manda o §5 do TESTES-IMPACTO-1.

## 10. Conferência preparada para a validação remota (FIN-CARTOES-FECHAMENTO-REAL-1)

Nada foi aplicado nem lido no remoto. A conferência foi preparada e ensaiada **só localmente**.

**Ferramenta:** `scripts/supabase_conferencia_migration.py`, somente leitura. Generaliza a verificação do FIN-FATURA-INTEGRIDADE-REAL-1.
- **Modo `local`:** monta o estado esperado num cluster descartável.
  - O estado "antes" usa as migrations anteriores e as tabelas do Flask **sem** o que o alvo cria, como está o remoto.
  - Aplica o alvo e lista o que muda.
- **Modo `antes` (remoto):**
  - confere o histórico (só o alvo pendente) e o catálogo contra o esperado;
  - grava fora do repositório a impressão digital e as **definições atuais das funções que o alvo troca** (base de um eventual rollback).
- **Modo `depois` (remoto):**
  - confere o catálogo;
  - confere o **conteúdo de todas as tabelas, idêntico ao de antes** (sem as colunas novas);
  - confere as colunas novas, **só com o valor padrão**.
- **Segurança:**
  - o projeto vem do `.env.staging` (usuário `postgres.<ref>` do pooler), como no `supabase_migrations.py`; o ref completo não é versionado;
  - recusa o da Calculadora Judicial e qualquer um fora do prefixo `fzjmge…`;
  - usa sessão read-only e nunca imprime a connection string nem linhas.

**O que `20261030090000` muda** (saída do modo `local`, conferida no teste):

| Objeto | Mudança |
|---|---|
| Funções novas internas (sem EXECUTE para PUBLIC, anon e authenticated) | `competencia_da_compra`, `situacao_fatura`, `sugestao_competencia`, `exigir_confirmacao_consolidada` |
| Função nova exposta (só `authenticated`) | `sugerir_competencia` |
| Funções alteradas, **sem mudança de privilégio** | `plano_compra` e `cartoes_do_perfil` (retorno e corpo); `previa_compra`, `criar_compra`, `editar_compra`, `ler_dados_cartao`, `criar_cartao`, `editar_cartao` (corpo) |
| Tabela nova | `public.fatura_consolidada_inclusao`, com RLS e sem privilégios para anon/authenticated |
| Colunas novas | `config_agregador.compra_no_fechamento` e `fechamento_confirmado`; `lancamento_agregado.mes_fatura_sugerido` |
| Removidos | nada |

**Ensaio local** (`test_conferencia_da_migration_sobre_banco_com_dados_da_versao_anterior`):
- **Dados de partida:** criados com as funções da **versão anterior**: cartão, compra parcelada e compra à vista, fatura paga e fatura consolidada.
- **Antes:** OK. O catálogo bate com o esperado; 60 tabelas e 75 funções; 8 definições salvas.
- **Depois:** OK. O conteúdo das 60 tabelas está idêntico e as colunas novas só têm o valor padrão.
- O fluxo é o mesmo do remoto, com o cluster no lugar do Supabase.

**Compatibilidade na janela entre a migration e a publicação do frontend:**
- **Frontend publicado (versão anterior):** continua funcionando.
  - Ele sempre envia o mês da fatura.
  - As colunas novas de `cartoes_do_perfil` são ignoradas.
  - Compra numa fatura **consolidada** passa a ser recusada com a mensagem do banco ("Fatura consolidada: confirme…"). A tela antiga não tem como confirmar, o que é coerente com a D6: nada entra em silêncio.
- **Frontend novo:** chama `sugerir_competencia` e por isso só pode ser publicado **depois** da migration.

**Sequência proposta para a REAL-1 (cada passo remoto depende de autorização):**
1. Conferência `antes`, com `--saida` fora do repositório.
2. Aplicar **só** `20261030090000` (`scripts/supabase_migrations.py aplicar --versoes 20261030090000`).
3. Conferência `depois`.
4. E2E real e cenários reais. Antes, atualizar o cenário 17 de `scripts/supabase_cartoes_real.py`: a FECHADA passa a exigir confirmação.
5. Limpeza com estado final idêntico.
6. Suíte completa (nível 3) antes de publicar; publicar o frontend só depois disso.

A Alembic `c7e2a9d4b8f3` no `gastos.db` continua sendo uma decisão separada, com backup.

## 11. D6 — Integridade transversal das faturas consolidadas (FIN-CARTOES-D6-INTEGRIDADE-1)

**Data:** 2026-10-24. **Situação:** implementado e validado **localmente** (cluster descartável, Flask real, dados fictícios). Nada remoto, nenhum commit.

### 11.1 Caminhos de escrita encontrados

| Ponto de entrada | Função | Tabelas | Consolidada (FECHADA) antes | Agora |
|---|---|---|---|---|
| Flask `POST /api/cartoes/<id>/lancamentos` | `adicionar_lancamento` | `lancamento_agregado`, `conta`, auditoria | Confirmação + auditoria (D6) | Igual |
| Flask `PUT /api/cartoes/lancamentos/<id>` (mover **para** consolidada) | `atualizar_lancamento` | idem | Confirmação + auditoria | Igual |
| Flask `PUT` de compra que **já está** na consolidada (valor, mês, parcelas) | `atualizar_lancamento` | `lancamento_agregado` | **Aceito em silêncio** (executado ≠ consolidado) | **409 `FATURA_CONSOLIDADA`**; descrição, observações, categoria e data continuam editáveis |
| Flask `DELETE /api/cartoes/lancamentos/<id>` | `excluir_lancamento` | `lancamento_agregado` | **Aceito em silêncio** | **409** |
| Flask parcelas futuras (`PUT .../futuras`, `cancelar-futuras`) | `atualizar/cancelar_parcelas_futuras` | `lancamento_agregado` | FECHADA já não é "futura" | Igual (protegido) |
| Flask `PUT /api/despesas/<id>` sobre a **fatura** (valor) | `atualizar_despesa` | `conta` | **Aceito** (contornava a D6) | **409** (descrição, vencimento e observações seguem editáveis) |
| Flask `DELETE /api/despesas/<id>` sobre a **fatura** | `deletar_despesa` | `conta` | **Aceito** (apagava a fatura) | **409** |
| Flask geração de recorrências (gerador Flask) | `gerar_lancamentos_cartao_recorrente` | `lancamento_agregado` | **Incluía em silêncio** | Não grava; registro no log (`FIN-CARTOES-D6`) |
| Flask importação de CSV | `persistir_lancamentos` | `lancamento_agregado` | **Incluía em silêncio** | Linha recusada com os dados; parcelas da mesma compra recusadas juntas |
| Flask recorrência importada | `vincular_linha_recorrencia` | `lancamento_agregado` | **Incluía em silêncio** | Recusa (400) |
| Flask despesa prevista / documento | `adicionar_lancamento` | idem | Recusa (400) | Igual |
| Flask consolidação `POST .../consolidar` | `consolidar_fatura` | `conta` | Recálculo **confirmava no meio**: compra no intervalo ficava fora do total | Recálculo e consolidação numa transação, sob a trava |
| Novo app `criar_compra`, `editar_compra` (mover para) | SQL | idem | Confirmação + auditoria | Igual |
| Novo app editar/excluir compra da consolidada | `travar_compra`/`bloqueio_da_parcela` | — | Bloqueado | Igual |
| Novo app `editar/excluir_despesa` sobre fatura | SQL | — | Bloqueado (fatura não é despesa) | Igual |
| Novo motor `gerar_mes` (recorrências) | `plano_recorrencia`, `gerar_mes_interno` | `lancamento_agregado`, `recorrencia_competencia` | **Incluía em silêncio** | `REJEITADA` com motivo na prévia; sob a trava, recusa controlada (`hint CONSOLIDADA`) |
| Escrita direta pelo navegador | tabelas/funções internas | — | Sem privilégio (RLS, revogado) | Igual (testado) |
| Triggers | — | — | Só a auditoria do gerador (T1) | Nada a mudar |

### 11.2 Regras preservadas

- **D5:** recorrências e importação **não** passam a usar o fechamento, e a competência não é trocada para contornar a consolidada. Nada é levado para outro mês, nada é confirmado em nome do usuário e nada é duplicado (as reexecuções são idempotentes).
- **D6:** a inclusão em consolidada continua possível **só** com a confirmação específica (fatura + total visto), conferida sob a trava, com o total atualizado na transação e auditoria. A confirmação reutilizada é recusada (o total já mudou) e não abre fatura paga.
- **Fatura paga:** proteções do FIN-FATURA-INTEGRIDADE-1 intactas (desvio antes, sem alteração).
- **Ordem de travas** cartão → faturas, perfis, privilégios e RLS sem mudança. Nenhuma função nova ganhou `EXECUTE` para o navegador.

### 11.3 Pendência representada

- **Novo motor:** a compra recorrente com destino consolidado vira `REJEITADA` (mecanismo existente, não persistente) com o motivo "Fatura de MM/AAAA consolidada: a compra recorrente nao entra sem confirmacao (lance-a pela compra no cartao)". Ela aparece na prévia e no aviso de geração. **Limite:** a dispensa existente só vale para itens `A_GERAR`, então essa linha não pode ser dispensada pela tela.
- **Flask:** não há mecanismo de pendência. A compra **não é gravada** (D6) e a ocorrência fica **só no log**. A visibilidade para o usuário depende de decisão (§11.6).

### 11.4 Migration

A seção foi acrescentada **à `20261030090000`**, que ainda está pendente no remoto, para manter um único alvo na REAL-1:
- nova função interna `fatura_consolidada_no_destino` (somente leitura);
- `plano_recorrencia` e `gerar_mes_interno` substituídos (só o corpo; assinatura e privilégios mantidos).

Nenhuma migration aplicada foi alterada. A conferência local (`test_conferencia_da_migration_sobre_banco_com_dados_da_versao_anterior`) passa: dados idênticos antes/depois, 5 funções novas internas + `sugerir_competencia`, 10 alteradas sem mudança de privilégio. **A conferência `antes` remota feita na RETOMADA-CASA-2 salvou 8 definições e precisa ser refeita** (agora são 10). Nenhuma mudança de schema no Flask (Alembic `c7e2a9d4b8f3` inalterada).

### 11.5 Testes

`tests/test_cartoes_d6_integridade.py`: **18 testes** (A faturas, B recorrências, C importação, D Flask, E segurança e concorrência). **Contra o código anterior, 9 falham** (recorrência nos dois motores, importação, recorrência importada, edição/exclusão no Flask, rota de despesas na fatura, edição durante a consolidação, função nova inexistente); com a correção, 18/18.

Ajustes: `test_cartoes_fechamento.py` (conferência: lista de funções da migration e 10 definições salvas); worker de `test_fatura_integridade.py` (ação `vincular_recorrencia`).

### 11.6 Decisões pendentes

1. **Visibilidade no Flask** e 2. **dispensa da linha `REJEITADA`:** resolvidas no FIN-CARTOES-RECORRENCIA-PENDENCIA-1 (§12), com ocorrência persistente, aviso e dispensa auditável nos dois sistemas.
3. **Correção de compra já consolidada** (valor ou retirada): não existe fluxo de alteração auditada; hoje é bloqueada nos dois sistemas.

## 12. Recorrência rejeitada: ocorrência persistente, aviso e dispensa auditável (FIN-CARTOES-RECORRENCIA-PENDENCIA-1)

**Data:** 2026-10-24. **Situação:** implementado e validado **localmente** (cluster descartável, SQLite temporário, Flask real, E2E local, dados fictícios). Nada remoto, nenhum commit.

**Decisão funcional aprovada:** quando a fatura de destino está consolidada, a compra recorrente continua **não sendo lançada** (D6) e a competência **não muda** (D5). A ocorrência passa a ser registrada de forma persistente, o usuário vê o aviso e pode **dispensá-lo**. Dispensar o aviso não regulariza a pendência nem cancela a recorrência.

### 12.1 Estrutura: por que uma tabela nova

| Existente | Motivo de não reutilizar |
|---|---|
| `financeiro.recorrencia_competencia` | Só o novo motor (schema `financeiro`); o Flask não a mapeia e ela não existe no SQLite. O estado `DISPENSADA` tem sentido **financeiro** (a competência não é mais gerada) e misturaria "dispensar aviso" com "cancelar a ocorrência" |
| `LastroFinanceiroPendencia` | Saída sem comprovante (`tipo_entidade/entidade_id`); a rejeição não tem entidade (nenhuma compra é criada) nem competência/fatura |
| `financeiro.geracao_execucao` | Resumo por execução (JSON); sem identidade por ocorrência nem estado de aviso |
| `fatura_consolidada_inclusao` | Auditoria de inclusões **confirmadas**, não de rejeições |
| "alertas" do cartão | Calculados na consulta; nada persistente |

Padrão seguido: o de `fatura_consolidada_inclusao` — tabela no `public`, mapeada pelo Flask e gravada pelas funções do Supabase, com RLS e sem privilégios para o navegador.

### 12.2 Modelagem — `public.recorrencia_rejeicao`

- **Identidade:** `UNIQUE (item_despesa_id, competencia)` (`ux_recorrencia_rejeicao_competencia`). Uma obrigação (recorrência + competência) é uma linha só. Uma nova competência é outra linha; uma nova tentativa da mesma competência soma `tentativas` e atualiza `ultima_tentativa_em`, sem duplicar.
- **Dados:**
  - perfil (o do item; `NULL` = legado do Pessoal);
  - recorrência, competência prevista, cartão, fatura de destino (`ON DELETE SET NULL`);
  - valor no momento da tentativa (o valor do item pode mudar depois);
  - motivo, origem (`FLASK` ou `NOVO_APP`), primeira e última tentativa.
- **Dimensão financeira (`situacao`):** `PENDENTE`. `REGULARIZADA` fica reservada (check) para a regularização futura, sem fluxo neste contrato.
- **Dimensão do aviso:** `aviso_dispensado_em`, `aviso_dispensado_user_id` (Supabase Auth) e `aviso_dispensado_usuario_id` (Flask). Aviso ativo = não dispensado. Não há estado "visualizado" (não era necessário e seria redundante).
- **Integridade:** `item_despesa_id` com `ON DELETE CASCADE` (a ocorrência não existe sem a recorrência).

### 12.3 Comportamento

- **Novo motor:**
  - `plano_recorrencia` continua marcando `REJEITADA` com o motivo; a prévia **não grava**;
  - `gerar_mes_interno` registra a ocorrência (`registrar_rejeicoes_consolidadas`, interna), sob a trava da geração. Se a geração falhar (por exemplo, "a prévia mudou"), o registro é desfeito junto;
  - `dispensar_aviso_recorrencia(perfil, recorrência, competência)` (só quem gerencia o perfil): se a ocorrência ainda não foi registrada, o banco a registra **se o plano a rejeitar agora por fatura consolidada** (o navegador só envia a identidade). Depois marca a dispensa. É idempotente: na segunda vez devolve `ja_dispensado = true`;
  - `recorrencias_rejeitadas(perfil, incluir_dispensadas)`: leitura (quem acessa o perfil);
  - **tela (Contas do mês):** o item aparece na lista "Ver itens não gerados" com o botão **Dispensar aviso**. Depois de dispensado, ele continua listado como "aviso dispensado" e sai da contagem do aviso.
- **Flask:**
  - a geração (`gerar_lancamentos_cartao_recorrente`) registra a ocorrência na transação do chamador, sem confirmar (trava T1 preservada), com upsert por identidade (PostgreSQL e SQLite);
  - `GET /api/recorrencias/pendencias[?incluir_dispensadas=1]` e `POST /api/recorrencias/pendencias/<id>/dispensar` (perfil ativo; ocorrência de outro perfil: 404; a dispensa trava e relê a linha);
  - **tela (Despesas):** bloco acima dos cards com a recorrência, a competência, o valor, o motivo e o botão **Dispensar aviso** (textos via `textContent`).
- **Banco sem a tabela** (`gastos.db` antes da Alembic): a compra continua não sendo lançada e a ocorrência fica só no log; a API devolve `disponivel = false`.
- **Dispensar o aviso não:** cancela a recorrência, cria compra, muda competência ou fatura, representa baixa ou pagamento, nem exclui a ocorrência. O histórico continua consultável.

### 12.4 Regularização futura (não implementada)

A ocorrência guarda a identidade (recorrência + competência), a fatura e o valor. Uma regularização deverá:
- partir da ocorrência e lançar a compra pelo fluxo D6 (com a confirmação do usuário, sob as travas);
- marcar `situacao = REGULARIZADA` na mesma transação, sem duplicar o lançamento;
- registrar o resultado.

Cancelar a recorrência continua sendo a operação própria de recorrências.

### 12.5 Segurança

- RLS na tabela, sem privilégios para `anon` e `authenticated`.
- `registrar_rejeicoes_consolidadas` é interna. As duas funções expostas são só para `authenticated` e conferem o perfil (leitura: acesso; dispensa: gestão).
- O Flask filtra pelo perfil ativo.
- Nenhum privilégio de função financeira foi ampliado.

### 12.6 Migrations

- **Supabase `20261030090000`** (pendente no remoto): tabela + 3 funções; `gerar_mes_interno` passa a registrar. A conferência local passa (dados idênticos antes/depois; tabela nova com RLS e sem privilégios; funções novas internas ou só para `authenticated`). **A conferência `antes` remota precisa ser refeita.**
- **Alembic `c7e2a9d4b8f3`** (nunca executada em banco persistente): a mesma tabela (PostgreSQL e SQLite), com RLS e revogação no Supabase; o `downgrade` a remove.
- O insert do banco passa todos os valores: a tabela pode ter sido criada pelo Flask (models), sem os defaults do banco (achado nos testes).

### 12.7 Testes

- **`tests/test_recorrencia_pendencia.py`, 14 testes:**
  - persistência no novo motor e no Flask (processo novo = aplicação reiniciada);
  - reexecução e duas gerações simultâneas sem duplicar; competências distintas;
  - fatura aberta e paga sem ocorrência;
  - consolidação entre a prévia e a geração (nada gravado);
  - dispensa concorrente com a geração;
  - dispensa auditada e idempotente, sem mudar compras, faturas, itens nem identidades, com histórico consultável e a prévia ainda informando;
  - dispensa antes da geração, validada pelo banco;
  - isolamento (outro usuário, outro perfil, LEITOR lê e não dispensa, anônimo, tabela e função interna);
  - API do Flask (lista, dispensa, idempotência, outro perfil 404);
  - tela do Flask; SQLite com e sem a tabela.
- **E2E `web/tests/e2e/pendencia.spec.mjs`** (usuário B, Perfil B, 2033, só no harness local): aviso, dispensa, persistência depois de recarregar, ocorrência `PENDENTE` com o aviso dispensado.
- **Ajustes:** conferência da migration (3 funções e a tabela nova); semente E2E `PENDENCIA_E2E` e o gancho de consolidação com `criar_se_faltar`; lista de RPCs do `build.test.mjs`.
