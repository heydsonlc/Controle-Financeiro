# FIN-FATURA-INTEGRIDADE-1 — Fatura paga imutável nas compras e ordem global de travas

**Data:** 2026-10-22.

**Situação:** implementado e validado **localmente**:
- cluster PostgreSQL descartável;
- arquivos SQLite temporários;
- processos Flask reais;
- dados fictícios.

**Autorização:** SCRIPT-CONTRATO V5 — FIN-FATURA-INTEGRIDADE-1. Antes de começar, revisei e enviei o `7460f00`; o check do Supabase ficou `skipped`.

**Não foi feito:**
- migration remota;
- Alembic no `gastos.db`;
- dados reais;
- publicação;
- FIN-CARTOES-FECHAMENTO-1.

## 1. Pontos de inclusão indevida encontrados

| # | Caminho | Problema |
|---|---|---|
| 1 | Flask: geração de recorrências no cartão (`routes/despesas.py`, `gerar_lancamentos_cartao_recorrente`) | Gravava a compra recorrente na fatura da competência, **sem conferir se estava paga** e sem trava |
| 2 | Flask: importação de CSV (`ImportacaoCartaoService.persistir_lancamentos`) | Idem. A deduplicação usa o mês da fatura: uma compra desviada seria **duplicada** na reimportação |
| 3 | Flask: recorrência importada (`importar_recorrencia…`) | Idem ao 1 |
| 4 | Novo aplicativo: geração (`financeiro.gerar_mes_interno`) | A compra recorrente entrava em fatura paga |
| 5 | Flask: compra (`adicionar_lancamento`) | **Não era atômica:** a criação de uma fatura confirmava a parcela 1 antes da parcela 2 (encontrado pelos testes de rollback) |
| 6 | Flask e novo aplicativo: reconhecimento de recorrência "pelo mês" | Uma compra de outra competência **desviada** para o mês era tomada pela compra do mês, que **deixava de ser gerada** (encontrado pelos testes) |

A compra do Flask (`adicionar_lancamento`) e o cadastro do novo aplicativo (`criar_compra`) já desviavam da fatura paga desde o FIN-PAGAMENTO-TRAVA-1 e o FIN-CARTOES-1.

## 2. Política de fatura elegível

- **Fatura paga** (`status_pagamento='Pago'` ou `status_fatura='PAGA'`) é **imutável** quanto às compras: nenhuma compra nova, recorrente ou importada entra nela.
- **Desvio:** a compra vai para a **primeira fatura não paga** a partir da competência pretendida. Se uma parcela for desviada, as seguintes **andam junto**, uma por fatura (distribuição dos centavos inalterada).
- **Fatura FECHADA** (consolidada) tem estado próprio: **continua elegível**, como no Flask. Não é confundida com paga.
- **Auditoria:** a nova coluna `lancamento_agregado.mes_fatura_original` (data, nula) guarda a competência em que a compra entraria. Ela é preenchida **só quando houve desvio** e **nunca retroativamente**. A identidade da recorrência continua a da competência (`recorrencia_competencia` e `compra_id` determinístico), então a compra desviada não é gerada de novo.
- **Reimportação:** a deduplicação considera a competência original (`mes_fatura = X ou mes_fatura_original = X`) e roda de novo **sob a trava** do cartão. Duas importações simultâneas do mesmo arquivo ficam em série e a segunda encontra tudo duplicado.
- **Banco ainda sem a coluna** (o `gastos.db` hoje):
  - compra e recorrência são desviadas com uma marca nas observações ("[Fatura de MM/AAAA paga: lançada em MM/AAAA]");
  - a **importação para fatura paga é recusada** com mensagem clara ("migration pendente"), para não perder a competência original usada na deduplicação. Nada é importado nesse caso.

## 3. Ordem global de travas

**cartão (`item_despesa`, por id) → faturas dele (por id) → compras → conta bancária → movimento**

- Quem trava **mais de uma fatura** trava **antes o cartão**:
  - compra parcelada;
  - importação;
  - parcelas futuras;
  - edição e exclusão de compra;
  - geração de recorrências;
  - `criar_compra` e `travar_compra` do novo aplicativo.
- O **pagamento** trava uma só fatura e nunca espera outra fatura. O **recálculo** trava cartão e fatura e confirma.
- **Criar fatura** (`get_or_create_fatura`) também trava o cartão (com nova consulta) antes do INSERT. Quem segura o cartão não vê surgir e ser paga uma fatura nova dele.
- **Por que não há ciclo:** uma operação só espera uma fatura de cartão cujo cartão ela já travou; o dono dessa fatura ou é de fatura única (pagamento, que só espera a conta bancária) ou precisaria do mesmo cartão. Os cartões são travados por id e antes de qualquer fatura. Isso **não depende** da detecção de deadlock do PostgreSQL.
- **Compra atômica no Flask:** `CartaoService.planejar_destinos` decide o destino de todas as parcelas e cria as faturas que faltam **antes** de inserir qualquer parcela. Depois trava o cartão e as faturas e só então insere e confirma.
- **Geração de recorrências do Flask:** roda na transação do chamador, com a trava T1. Por isso usa `fatura_elegivel_existente`, que **não cria fatura nem confirma**.

**Prova do ciclo no código anterior.** O mesmo teste de ordens opostas rodou contra o `7460f00` (worktree temporário):
- o Flask segurava a fatura de outubro e ia pedir a de novembro;
- o novo aplicativo travava novembro (id menor) e esperava outubro;
- o PostgreSQL abortou a exclusão do novo aplicativo com **`DeadlockDetected`**.

Com a correção, o novo aplicativo espera o cartão, sem travar fatura nenhuma, e as duas operações terminam.

## 4. Alterações

**Flask:**

| Arquivo | Mudança |
|---|---|
| `models.py` | `LancamentoAgregado.mes_fatura_original` (deferred, `server_default NULL`, `eager_defaults=False`: o Flask funciona num banco sem a coluna) |
| `services/cartao_service.py` | `travar_cartao`; `travar_faturas` trava o cartão antes; `_fatura_travada`; `fatura_elegivel`; `fatura_elegivel_existente` (sem commit); `planejar_destinos` (compra atômica); `suporta_desvio_auditado`, `registrar_desvio` e `filtro_competencia_original`; `get_or_create_fatura` trava o cartão antes do INSERT; `adicionar_lancamento` usa o planejamento |
| `routes/despesas.py` | A recorrência do cartão desvia de fatura paga, sem commit; o reconhecimento "pelo mês" vale só para compras antigas sem `compra_id` |
| `services/importacao_cartao_service.py` | Destinos planejados sob trava; deduplicação pela competência original e de novo sob a trava; recorrência importada desviada |

**Migrations (locais, não aplicadas no remoto):**
- **Supabase `20261029090000_financeiro_fatura_integridade.sql`:**
  - coluna `mes_fatura_original`;
  - `fatura_elegivel_existente` (interna);
  - `plano_recorrencia` (fallback só sem `compra_id`);
  - `gerar_mes_interno` (cartões travados e desvio de fatura paga);
  - `criar_compra` (cartão travado e competência original no desvio);
  - `travar_compra` (cartão antes das faturas);
  - assinaturas e privilégios mantidos.
- **Alembic `f1c4d8e2a7b9`:** a mesma coluna, idempotente. Testada **só** em SQLite temporário e cópia PostgreSQL descartável (sobe, sobe de novo, preserva dados, desce). **Não executada** no `gastos.db`.

## 5. Testes

**`tests/test_fatura_integridade.py`: 13 testes.**
- Processos Flask reais, com conexão e transação próprias.
- Barreiras antes do commit ou logo depois da primeira trava de fatura.
- Espera conferida em `pg_stat_activity`.
- Novo aplicativo como `authenticated` em outra conexão.

| # | Item do contrato | Resultado |
|---|---|---|
| 1 | Recorrência com fatura paga | Novo motor e Flask: a compra de 03 vai para 04 (original 03); a de 04 continua; nova geração não duplica |
| 2 | Importação para fatura paga | Desviada, com a competência original |
| 3 | Importação repetida | 4 inseridas e, na repetição, 0 inseridas e 4 duplicadas. **Simultâneas:** a segunda esperou o cartão; 1 inserida e 1 duplicada |
| 4 | Parcelada atravessando fatura paga | **Flask = novo aplicativo:** 06, 08 (orig. 07), 09 (orig. 08); 30,00 cada |
| 5 | Compra concorrente com pagamento | Coberto no FIN-PAGAMENTO-TRAVA-1 (regressão abaixo) |
| 6 | Recorrência × compra | A geração esperou o cartão; sem duplicidade; 2 parcelas e 2 recorrências |
| 7 | Importação × geração | A geração esperou; ambas completas; sem duplicidade |
| 8 | Recálculo de várias faturas | Edição parcelada do novo aplicativo × compra 4× do Flask em paralelo: executado de cada fatura = soma real |
| 9 | Ordens opostas | Sem deadlock (no código anterior: `DeadlockDetected`) |
| 10 | Rollback | Falha na parcela 2: **nenhuma parcela** gravada; fatura paga e saldos intactos |
| 11 | Faturas pagas | md5 idêntico em todos os cenários |
| 12 | Unicidade | Nenhuma fatura duplicada |
| 13 | Movimentos e saldos | Idênticos |
| 14 | SQLite e PostgreSQL | SQLite migrado (desvio com a coluna) e **sem a coluna** (marca nas observações; importação recusada); FECHADA continua elegível |

**`tests/test_alembic_mes_fatura_original.py`: 3 testes** (encadeamento; SQLite e PostgreSQL fictícios).

**Ajuste de teste (2):** `test_importacao_cartao_triagem_ux` confere o texto do serviço. A recorrência importada agora recalcula a fatura de **destino** (`recalcular_fatura(cartao_id, mes_destino)`), que difere da competência quando a compra é desviada; o texto esperado foi atualizado.

**Ajuste de teste:** o antigo controle da FIN-FATURA-UNICA-1 ("sem o índice, a corrida duplica") passou a exigir que **mesmo sem o índice** a trava do cartão impeça a duplicidade. O índice único continua como segunda defesa.

**Regressão:**
- FIN-PAGAMENTO-TRAVA-1, FIN-FATURA-UNICA-1, FIN-RECORRENCIA-1, FIN-CARTOES-1 e FIN-DESPESAS-1: passam.
- E2E local: **47/47**.
- Suíte completa: 1450 passaram; só as 5 falhas que já existiam (§8).

## 6. Compatibilidade

- **Flask num banco sem a coluna** (`gastos.db` hoje): funciona (compra, recorrência, deduplicação). Só a importação para uma fatura **já paga** é recusada até a migration local ser aplicada.
- **Novo aplicativo:** as funções mantêm assinatura e privilégios. Até `20261029090000` ser aplicada no remoto, o remoto continua com as versões anteriores.
- **Equivalência:** a compra parcelada atravessando fatura paga dá o mesmo resultado no Flask e no novo aplicativo. As equivalências do FIN-CARTOES-1 seguem passando.
- **Valores, competências, faturas e compras existentes não mudam:** nada é recalculado nem preenchido retroativamente.

## 7. Riscos e pendências

- **Aplicar `20261029090000` no Supabase de teste:** validação remota, a autorizar.
- **Aplicar a Alembic `f1c4d8e2a7b9`** (com `d81f5a2b9c3e` e `e3b7c9d1a2f4`) no banco do Flask: decisão do usuário, com backup.
- **Consolidação (FECHADA):** recalcula sob trava e grava o estado depois. Não mexe em valor pago (inalterado).

## 8. Suíte completa

Comando original (`venv\Scripts\python.exe -m pytest`). Resumo real impresso pelo pytest: **`5 failed, 1450 passed, 19 skipped, 1140 warnings in 872.32s`** (1434 anteriores + 16 novos). A primeira rodada acusou 1 regressão nova (o teste de texto do §5, ajuste 2), corrigida antes desta. O código de saída 1 vem só das 5 falhas que já existiam:
- `test_categorias_sistemicas_mobilidade::test_projecoes_veiculo_usam_categorias_sistemicas_granulares`
- `test_ocr_tools::test_status_sem_ferramentas_retorna_estrutura_valida`
- `test_ocr_tools::test_poppler_ausente_retorna_aviso`
- `test_receitas_ux::test_cards_resumo_calculam_previsto_realizado_diferenca_confiabilidade`
- `test_veiculos_mobilidade_2b::test_suprimir_despesas_previstas_futuras`

## 9. Arquivos

- `backend/models.py`
- `backend/services/cartao_service.py`
- `backend/services/importacao_cartao_service.py`
- `backend/routes/despesas.py`
- `supabase/migrations/20261029090000_financeiro_fatura_integridade.sql` (novo)
- `migrations/versions/f1c4d8e2a7b9_mes_fatura_original_lancamento.py` (novo)
- `tests/test_fatura_integridade.py` e `tests/test_alembic_mes_fatura_original.py` (novos)
- `tests/test_supabase_fatura_unica.py`
- `docs/FIN_FATURA_INTEGRIDADE_1.md` e `docs/ROADMAP.md`
