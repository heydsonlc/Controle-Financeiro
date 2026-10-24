# TESTES-IMPACTO-1 — Testes proporcionais ao impacto das alterações

**Data:** 2026-10-23.

**Situação:** em vigor. É o padrão de validação dos MVPs a partir do FIN-CARTOES-FECHAMENTO-1, que foi o primeiro caso de aplicação (§9).

**Autorização:** SCRIPT-CONTRATO V5 — TESTES-IMPACTO-1.

## 1. Objetivo

Validar cada MVP no tempo proporcional ao que ele alterou, sem perder a cobertura das regras financeiras afetadas.

- A suíte completa continua existindo, mas só nos marcos do §5.
- **Tempo nunca justifica tirar um teste necessário.** Concorrência, transações e equivalência Flask × PostgreSQL rodam sempre que a alteração os alcança, mesmo que passem das metas.

## 2. Níveis de validação

| Nível | Quando | O que roda | Meta de referência |
|---|---|---|---|
| **1 — Desenvolvimento** | Durante a implementação | Testes da função ou tela alterada e dos consumidores diretos (`pytest arquivo::teste`, `-k`) | 1 a 5 min |
| **2 — Encerramento do MVP** | Antes de entregar o relatório do MVP | A seleção do `scripts/testes_impacto.py`: testes do módulo, integração com os módulos ligados, proteções financeiras, equivalência Flask × PostgreSQL, invariantes do esquema e E2E das telas afetadas | 5 a 15 min, quando viável |
| **3 — Regressão completa** | Nos marcos do §5 | `pytest` inteiro, web unit e E2E completo | ~65 min hoje |

As metas são referências de desempenho, não limites. Uma bateria de nível 2 que passe de 15 min por causa de testes de concorrência necessários está correta.

## 3. Critérios de seleção (o que o seletor faz)

`scripts/testes_impacto.py` usa só a biblioteca padrão, o Git, o pytest e o npm já usados no projeto.

0. **Regra permanente: na dúvida sobre impacto financeiro, ampliar.**
   - **Gatilho:** o trecho alterado de código (linhas novas ou removidas) cita pagamento, estorno, conciliação, consolidação, saldo, baixa ou movimentação.
   - **Testes Python:** entram **todas** as proteções financeiras: cartão e fatura, `test_pagamento_*`, `test_estorno_*`, `test_core_saldo_*`, baixas, débito automático e movimento de estorno.
   - **E2E:** se o novo aplicativo pode ser afetado (`supabase/` ou `web/src/`), entram os specs que mostram faturas, pagamentos e saldos (`contas`, `despesas`, `recorrencia`, `cartoes`, `fechamento`).
   - **Prioridade:** a integridade dos valores vale mais que alguns minutos de execução.
1. **O que mudou.** Lê o `git diff` (ou `--arquivos`) e, para Python, as **linhas alteradas** → funções, métodos, constantes e classes tocados (AST).
   - Mudar só um método não arrasta a classe inteira.
   - Atributo **privado** (`_cache`) entra pelo próprio nome, sem arrastar a classe.
   - Colunas, atributos públicos, código de nível de módulo e arquivo novo arrastam.
2. **Quem depende (até 2 níveis).** Funções do backend que citam o símbolo alterado; quem cita essas; e as **rotas HTTP** delas.
   - A rota é casada pelo **caminho inteiro**: `/api/despesas/<int:id>/pagar` casa `f'/api/despesas/{id}/pagar'`, mas não a raiz `/api/despesas/` nem outra rota do blueprint.
   - Nomes genéricos (`to_dict`, nomes definidos em 3 ou mais módulos) não propagam, para não ligar tudo a tudo.
3. **Migrations do Supabase.**
   - Funções `create function financeiro.x` da migration e as funções SQL que **chamam** essas (`financeiro.x(`), até 2 níveis.
   - Tabelas alteradas.
   - Telas do novo aplicativo cujo JS chama `rpc('x')`.
4. **Novo aplicativo.**
   - **JS alterado:** módulos que o importam (fecho) → páginas que os carregam → specs que abrem essas páginas.
   - **Por dados:** tabela alterada pela migration → funções SQL que a leem (e as que chamam essas) → JS que chama essas RPCs (e quem o importa) → páginas → specs. Exemplo: a tela de Contas mostra faturas de cartão sem importar o JS de cartões.
   - **Login não conta:** esperar cair em `contas.html` depois do login (`waitForURL`) não é testar a tela; vale só a navegação explícita (`goto`).
   - **CSS compartilhado e infraestrutura do E2E** (`run_e2e.py`, `playwright.config.mjs`, `build.mjs`, `tests/supabase_local.py`): todos os specs.
   - **Unitários web:** sempre que `web/` muda (levam ~5 s).
5. **Testes escolhidos.** Os que importam o módulo (só quando muda código de nível de módulo ou o arquivo é novo), usam um símbolo alterado ou dependente, chamam uma rota afetada, usam uma função ou tabela SQL afetada ou **citam o arquivo alterado** (os testes de UX que leem o frontend como texto). Mais os testes alterados e os que importam símbolos alterados deles.
6. **Matriz curada (§4).** Cobre o que a análise estática não vê:
   - as **proteções financeiras de cartão e fatura**;
   - as **invariantes globais do esquema**, que percorrem todas as tabelas e funções sem citar nomes.
7. **Na dúvida, amplia.**
   - Arquivo alterado sem nenhum teste encontrado aparece em "Sem teste encontrado" e é revisado à mão.
   - Arquivo central aparece em "Avisos" (avaliar o nível 3).
   - Falha de análise amplia ao módulo inteiro.
   - **Nenhum teste é excluído só por não haver dependência estática detectável:** quem decide excluir registra o motivo.
8. **Remotos** (`scripts/*_real.py`, `scripts/supabase_*.py`, `run_e2e_real.py`): só listados, **nunca executados** pelo seletor. Os testes locais que os usam (por exemplo, com o cluster no papel do remoto) entram normalmente.

## 4. Matriz de impacto (real, levantada no código e nos testes)

| Componente | Código | Testes |
|---|---|---|
| Cadastro de cartões | `routes/cartoes.py` (criar/atualizar), `ConfigAgregador`; SQL `criar_cartao`, `editar_cartao`, `cartoes_do_perfil` | `test_card_cvv_lock`, `test_cartao_clean_legado`, `test_categoria_cartao_arquitetura`, `test_supabase_cartoes`, `test_cartoes_fechamento` (D); E2E `cartoes`, `fechamento` |
| Competência pelo fechamento | `CartaoService.competencia_da_compra`/`sugestao_competencia`; SQL `competencia_da_compra`, `sugestao_competencia`, `sugerir_competencia`, `plano_compra` | `test_cartoes_fechamento` (A, B, D); web unit `fechamento.test`; E2E `fechamento` |
| Faturas (criação, vencimento, recálculo) | `get_or_create_fatura`, `fatura_elegivel`, `recalcular_fatura` | `test_core_cartao_fatura`, `test_cartao_fatura_categoria_cartao`, `test_fatura_unica_flask`, `test_supabase_fatura_unica`, `test_supabase_cartoes`, `test_fatura_integridade`, `test_supabase_recorrencia` (vencimento igual nos dois motores) |
| Compras e parcelamentos | `adicionar_lancamento`, `planejar_destinos`, parcelas futuras; SQL `plano_compra`, `criar_compra`, `editar_compra`, `excluir_compra` | `test_cartao_parcelamento_ux`, `test_cartao_operacional_categoria_cartao`, `test_supabase_cartoes`, `test_fatura_integridade`, `test_cartoes_fechamento` (B) |
| Fatura paga e consolidada | desvio de fatura paga; D6 (`conferir_confirmacoes`, auditoria); `consolidar_fatura` | `test_fatura_integridade`, `test_cartoes_fechamento` (C), `test_supabase_cartoes`, `test_estorno_fatura` |
| Recorrências | `routes/despesas.py` (`gerar_execucao_despesa_recorrente`, `gerar_lancamentos_cartao_recorrente`); SQL `gerar_mes_interno`, `plano_recorrencia` | `test_supabase_recorrencia`, `test_supabase_gerador_t1`, `test_recorrencias_*`, `test_core_cartao_fatura`, `test_fatura_integridade` |
| Importação de fatura | `importacao_cartao_service`, `importacao_cartao_unificado_service` | `test_importacao_*`, `test_fatura_integridade` |
| Pagamentos, baixas e travas | `pagar_fatura`, `trava_financeira`, rotas de contas e despesas | `test_pagamento_trava`, `test_pagamento_fluxo_operacional`, `test_baixa_despesa_transacional`, `test_debito_automatico_baixa_status`, `test_core_saldo_*` |
| Estornos | estorno de fatura, despesa, receita e financiamento | `test_estorno_*`, `test_movimento_original_estorno` |
| Equivalência Flask × PostgreSQL | Flask real (subprocesso) × funções `financeiro.*` | `test_supabase_cartoes`, `test_supabase_despesas`, `test_supabase_recorrencia`, `test_supabase_contas_mes`, `test_cartoes_fechamento` (D) |
| Esquema e segurança do Supabase | RLS, privilégios, exposição | `test_sec_supabase_public` e `test_supabase_mvp_rls` (percorrem o esquema inteiro: matriz, sempre que `supabase/migrations` muda); `test_supabase_perfis` (tabelas de perfil) |
| Alembic | `migrations/versions` | `test_alembic_*`, `test_cartoes_fechamento` (E) |
| Receitas | rotas e funções de receita | `test_supabase_receitas`, `test_supabase_receitas_data`, `test_core_receita_1`, `test_receitas_ux`, `test_estorno_receita` |
| Autenticação, perfis e escopo | login, perfil ativo, contexto | `test_autenticacao`, `test_perfis_financeiros*`, `test_contexto_financeiro_*`, `test_supabase_perfis`; E2E `acesso`, `perfis` |
| Telas do Flask (lidas como texto) | `frontend/templates`, `frontend/static/js`, `frontend/static/css` | `test_*_ux`, `test_payment_assets`, `test_brand_assets_instituicoes` (pelo nome do arquivo citado) |
| Novo aplicativo | `web/src/js`, `web/src/css`, páginas | `web/tests/unit` (inclui a lista de RPCs liberadas), specs E2E da página |

A matriz curada do seletor (`REGRAS` em `scripts/testes_impacto.py`) contém só as linhas que a análise estática não alcança: **proteções de cartão e fatura**, **invariantes do esquema** e **cadeia Alembic**. As demais associações saem do código. Ao criar um módulo com proteção ou invariante global nova, atualize `REGRAS` e esta tabela.

## 5. Quando a regressão completa (nível 3) é obrigatória

- Antes de publicar (Cloudflare) ou de aplicar migration no Supabase remoto.
- Antes ou depois de uma mudança estrutural abrangente (arquitetura, dependências, versão de Python ou Node).
- Após alterar código central compartilhado. O seletor avisa nestes casos:
  - `backend/app.py`, `config.py`, `models.py` (quando a mudança não é localizada);
  - `tests/conftest.py`, `pytest.ini`, `requirements*.txt`, `web/package*.json`.
- Ao integrar vários MVPs que ainda não passaram juntos por uma regressão completa.
- Quando a bateria direcionada falhar de forma inesperada ou com alcance desconhecido.
- Quando houver dúvida relevante sobre o efeito das alterações.

Não rodar automaticamente a suíte completa ao fim de todo MVP.

## 6. Procedimento

1. **Ver a seleção (não executa nada):**
   ```
   venv\Scripts\python.exe scripts\testes_impacto.py
   ```
   Revise os motivos, "Sem teste encontrado" e "Avisos". Se algo parecer faltar, rode mais (`--profundidade 3` ou arquivos extras), nunca menos.
2. **Executar e medir:**
   ```
   set POSTGREST_BIN=C:\caminho\postgrest.exe
   venv\Scripts\python.exe scripts\testes_impacto.py --executar
   ```
   - Roda pytest (com `--durations=15` e relatório JUnit), web unit e o E2E local das specs selecionadas.
   - Imprime o tempo por etapa e por arquivo de teste.
   - `--sem-e2e` deixa o E2E de fora (por exemplo, sem PostgREST); nesse caso, registre a pendência.
3. **Reaproveitar resultados:** `--excluir arquivo...` só para testes executados **na mesma versão** dos arquivos de que dependem. A evidência fica no relatório:
   - o horário da execução;
   - a última alteração dos arquivos de código e de teste (`stat`, `git status`).
   - Resultado anterior a uma correção nunca comprova a versão corrigida.
4. **Comparar com outra base:** `--base origin/main` (tudo o que o ramo mudou) ou `--arquivos a b c`.
5. **Nível 1:** rode direto os testes do que está mexendo (`pytest tests/x.py -k nome`). O seletor ajuda a achar os consumidores.

## 7. Isolamento e segurança

- **Bancos:** só descartáveis.
  - SQLite em memória ou arquivo temporário.
  - Clusters PostgreSQL criados pelos testes (`tests/supabase_local.py`), com cópia por teste.
  - Harness E2E local.
- **Nunca usar** o `gastos.db`, o `controle_financeiro_dev`, o Supabase remoto ou dados reais.
- **Proibido para ganhar tempo:**
  - desligar isolamento de banco, transações, travas ou limpeza;
  - paralelizar testes que compartilham estado;
  - mudar regra financeira.
- **Remotos** (validações `*-REAL-1`): seguem o procedimento próprio e só rodam com autorização.

## 8. Critérios de aceite de uma bateria direcionada

- A seleção, os motivos, os avisos e o que ficou sem teste aparecem no relatório do MVP.
- **Testes:**
  - todos os selecionados passaram, ou cada falha foi analisada;
  - falha que não seja preexistente e conhecida bloqueia o encerramento;
  - reaproveitados vieram com evidência de mesma versão.
- **Tempo:** total, por etapa e os maiores consumidores foram registrados, medidos e não estimados.
- **Escalar para o nível 3** quando o §5 se aplica.

## 9. Primeira aplicação: FIN-CARTOES-FECHAMENTO-1

**Bateria anterior (suíte completa em 4 etapas, iniciada às 17:17:22):**
- **Etapa "financeiros":** 301 testes, **298 aprovados e 3 falhas**. As 3 são de `test_supabase_recorrencia.py` e já estavam corrigidas quando a etapa terminou (o arquivo foi alterado às 17:51, depois da coleta).
- **Interrupção:** às 18:28, com a etapa "completa" em ~10% e 40 a 60 min ainda pela frente, sendo que ela repetiria os 301 testes financeiros. A parada foi pelo mecanismo do harness, que encerra a tarefa em segundo plano.
- **Depois da parada:**
  - nenhum processo restante;
  - o serviço PostgreSQL local intacto;
  - logs preservados.

**Seleção** (27 arquivos alterados em relação ao HEAD):

| | Selecionados | Total |
|---|---|---|
| Python | 51 arquivos (840 testes) | 106 arquivos (1540 testes) |
| Web unit | todos (15) | 15 |
| Web E2E | 8 specs (48 testes) | 8 specs |

| Motivo da seleção (Python) | Arquivos |
|---|---|
| Dependência direta comprovada (símbolo, função SQL, rota de handler alterado, teste que lê o arquivo alterado, teste alterado) | 34 |
| Dependência indireta comprovada (`GET /api/despesas/` → `listar_despesas` → `get_or_create_fatura`; `gerar_faturas_mes_atual` → `get_or_create_fatura`) | 8 |
| Sem dependência comprovada: 6 pela rota `/api/despesas` casada de forma larga e 3 pela matriz curada | 9 |

- **E2E:** os 8 specs entraram por causa do `app.css` compartilhado e da infraestrutura (`run_e2e.py`), ambos alterados neste MVP.
- **Reaproveitados (`--excluir`)**, com evidência de mesma versão:
  - **Os 8 arquivos:** `test_fatura_integridade`, `test_alembic_mes_fatura_original`, `test_pagamento_trava`, `test_supabase_fatura_unica`, `test_fatura_unica_flask`, `test_supabase_cartoes`, `test_supabase_despesas` e `test_cartoes_fechamento`, com 244 testes aprovados na etapa "financeiros".
  - **Código:** o último arquivo de código, migration ou tela foi alterado às 17:16:43, antes do início da etapa (17:17:22), e nenhum mudou até o fim (18:23:29).
  - **Testes:** os 8 não mudaram depois das 17:16:43.
  - **Apoios importados:** `tests/supabase_local.py`, `test_supabase_cartoes` e `test_supabase_despesas` estão intactos. O único apoio alterado depois, `test_supabase_recorrencia.py` (17:51), mudou só `DIVERGENCIAS_INTENCIONAIS` e 3 funções de teste, e nenhum dos 8 importa esses nomes.

**Execução** (21:18:53 a 21:43:21, sem standby, notebook **na bateria**):

| Etapa | Testes | Resultado | Duração |
|---|---|---|---|
| pytest (43 arquivos) | 596 | 594 aprovados, **2 falhas**, 0 ignorados | 13,9 min |
| Web unit | 15 | 15 aprovados | 0,3 min |
| Web E2E (8 specs) | 48 | 48 aprovados | 9,7 min (8,7 de Playwright) |
| **Total** | 659 | | **23,9 min** (24,5 com a análise) |

- **Falha preexistente:** `test_veiculos_mobilidade_2b::test_suprimir_despesas_previstas_futuras`, uma das 3 conhecidas.
- **Falha nova, pega pela matriz (invariantes do esquema):** `test_sec_supabase_public::test_ciclo_completo_de_rollback_restaura_estado_exato`.
  - O teste do rollback da SEC-SUPABASE-PUBLIC-1 subia o Alembic até `head`, e a revisão `c7e2a9d4b8f3` cria `fatura_consolidada_inclusao`. O rollback da SEC não desfaz tabelas de revisões posteriores, e nem deve.
  - **Correção:** subir só até a revisão da proteção (`c4f7a2d91b3e`). As invariantes em `head` continuam no fixture `ambiente`, cujos testes passaram com a tabela nova (RLS, sem privilégios para anon/authenticated, sequências, tabela nova não exposta).
  - **Nível 1 depois da correção:** o arquivo inteiro, **16/16 em 1,9 min**.

**Comparação de duração:** a economia percentual **não foi calculada**, porque as durações disponíveis não são comparáveis:
- a referência completa (≈ 64,5 min: Python 38,5 min com 1474 testes, financeiros 18,6 min, E2E 5,6 min) foi medida de manhã, **na tomada**;
- a bateria direcionada foi medida à noite, **na bateria**.

No mesmo dia, o E2E (47 a 48 testes) levou 5,2 min na tomada e 8,7 min na bateria. A comparação justa exige as duas medições na tomada (§10).

## 10. Diagnóstico de desempenho

- **Onde está o tempo:** os 5 arquivos com PostgreSQL descartável selecionados levaram **12,3 dos 13,8 min (89%)** do pytest. Os outros 38 arquivos, juntos, levaram 1,5 min. Na suíte completa, os 8 arquivos financeiros tinham 16% dos testes e 48% do tempo.

| Mais lentos | Tempo |
|---|---|
| `test_supabase_recorrencia` (57 testes) | 5,9 min |
| `test_supabase_gerador_t1` (29) | 3,5 min |
| `test_sec_supabase_public` (16) | 1,5 min |
| `test_supabase_contas_mes` (38) | 0,8 min |
| `test_supabase_mvp_rls` (26) | 0,6 min |

- **Custos repetidos de preparação:**
  - **Cluster PostgreSQL:** `initdb`, todas as migrations e as sementes custam **19 a 35 s por módulo** (os *setups* mais lentos do `--durations`). Os 15 módulos que sobem cluster pagam isso cada um.
  - **Flask real em subprocesso:** cada chamada a `flask()` inicia um Python novo e importa o app inteiro. Isso domina as chamadas de 10 a 16 s.
- **Ambiente:**
  - **Na bateria**, com o plano "HP Optimized (Modern Standby)" e o i5-1345U a 1,6 GHz, o E2E ficou ~1,7× mais lento.
  - **O Modern Standby suspende as baterias:** a etapa "financeiros" da tarde teve **22,6 min de standby** (17:43–17:46 e 17:57–18:16). Por isso levou 66 min de relógio, contra 18,6 min de manhã, na tomada.
  - **Medir e rodar baterias longas na tomada e sem suspensão.**
- **Otimizações possíveis, não aplicadas** (exigem um contrato próprio e preservam o isolamento):
  1. **Cluster único por sessão:** um modelo migrado por sessão, com as sementes de cada módulo em bancos-modelo próprios. Cada teste continua com a sua cópia.
  2. **Flask reaproveitado:** um processo Flask por módulo, reaproveitado entre chamadas. Continua em processo separado, com conexão e transação próprias.
  3. **Paralelismo:** só entre módulos que não compartilham cluster nem portas, e só depois de medir.
  - **Fora de cogitação para ganhar tempo:** desligar travas, transações ou limpeza.

## 11. Calibração (feita depois da avaliação de 2026-10-23)

Achados da primeira aplicação. Nada foi mudado no seletor durante a execução; a calibração veio depois, com testes próprios em `tests/test_testes_impacto.py` (13).

1. **Rota com parâmetro (corrigido).**
   - **Problema:** `'/<int:id>/pagar'` virava `/api/despesas/` quando o caminho era cortado no primeiro `<`, e casava qualquer teste de despesas.
   - **Agora:** o caminho é casado inteiro (`padrao_rota`).
2. **Atributo privado de classe (corrigido).**
   - **Problema:** o cache `CartaoService._capacidades` arrastava a classe inteira, e com ela `marcar_como_pago`.
   - **Agora:** `_privados` entram pelo próprio nome.
3. **E2E por dados (corrigido, era risco de subseleção).**
   - **Problema:** `contas`, `despesas` e `recorrencia` conferem faturas de cartão na tela de Contas (`#lista-cartoes`) e dependem das tabelas, não do JS de cartões.
   - **Agora:** tabela alterada → funções SQL que a leem → RPCs → telas → specs.
   - **Simulação** (migration de cartões sozinha): 6 specs. Entram `cartoes`, `fechamento`, `contas`, `despesas`, `recorrencia` e `receitas` (abre `contas.html`); ficam fora `acesso` e `perfis`, que só caem em `contas.html` no login.
   - **Tela de cartões sozinha** (sem trecho financeiro): 2 specs.
4. **Regra financeira permanente (nova).** É o critério 0 do §3: na dúvida sobre impacto financeiro, ampliar.
5. **Matriz curada: mantida.** Um dos 3 arquivos que entraram só por ela (`test_sec_supabase_public`) achou a única falha nova desta aplicação.
6. **Efeito na seleção do FIN-CARTOES-FECHAMENTO-1:** de 51 para 56 arquivos.
   - **Saiu:** 1 arquivo que entrava só pela rota larga.
   - **Voltaram com motivo:** 5, pela regra financeira.
   - **Entraram:** 6 proteções financeiras (saldos, estornos de financiamento e receita, débito automático), porque o trecho alterado cita "consolidada".
7. **Pendente:** medir a economia de tempo na tomada, sem suspensão, no próximo marco obrigatório.
