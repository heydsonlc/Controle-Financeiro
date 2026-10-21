# FIN-FATURA-UNICA-1 — Proteção contra duplicidade de faturas

**Data:** 2026-10-21. Implementado e testado **localmente**: cluster PostgreSQL descartável, processos Flask reais e novo motor em concorrência real, mais SQLite.

**Não foi feito:**
- aplicar migration no remoto;
- publicar;
- alterar dados reais.

**Autorização:** SCRIPT-CONTRATO V5 — FIN-FATURA-UNICA-1. O push de `019e3b9` foi feito após revisão.

## 1. Causa da possibilidade de duplicação

Os dois motores fazem **"consulta → insere"** sem garantia no banco:
- **Flask:** `CartaoService.get_or_create_fatura` procura a fatura (cartão, `is_fatura_cartao`, `cartao_competencia`, com filtro de perfil) e, se não acha, calcula o planejado e insere.
- **Novo aplicativo:** `financeiro.gerar_mes_interno` monta o plano (fatura "a gerar" quando não existe) e insere.

Duas transações simultâneas podem ver "não existe" e inserir as duas. A tabela legada `public.conta` não tinha nenhuma restrição de unicidade.

O teste de controle `test_controle_sem_o_indice_a_mesma_corrida_duplica` reproduz a duplicação real: dois processos Flask, sem o índice, criam **2 faturas**.

**Diagnóstico dos pontos de criação:**

| # | Ponto | Como cria a fatura |
|---|---|---|
| 1 | Geração de recorrências no Flask: GET `/api/despesas/?mes_referencia=` (laço de faturas virtuais) e job/scheduler `gerar_faturas_mes_atual` | `get_or_create_fatura`. Protegidos pela T1 no perfil migrado |
| 2 | Compras e parcelas no Flask (`adicionar_lancamento`), recálculo (`recalcular_fatura`) e alertas (`avaliar_alertas`) | `get_or_create_fatura` (único criador no Flask). As demais referências, como `consolidar_fatura` e consórcios, só consultam ou criam contas comuns |
| 3 | Novo aplicativo | `gerar_mes_interno`, por perfil, com trava consultiva |

## 2. Chave de unicidade e justificativa

```sql
create unique index ux_conta_fatura_cartao_competencia
    on public.conta (item_despesa_id, cartao_competencia)
    where is_fatura_cartao;
```

- **Cartão = `item_despesa_id`:** a fatura aponta para o `item_despesa` do tipo `Agregador`. O cartão tem **um único perfil**.
- **Competência = `cartao_competencia`:** os dois motores sempre a normalizam para o dia 1. O diagnóstico verifica isso.
- **Só faturas (`where is_fatura_cartao`):** contas comuns do mesmo item e mês continuam permitidas, como antes (testado).
- **O perfil não entra na chave:**
  - o Flask só cria a fatura no perfil do próprio cartão (`cartao.perfil_financeiro_id`);
  - o novo motor faz o mesmo;
  - incluir o perfil permitiria duas faturas do mesmo cartão e mês.
  - Se um dia aparecer uma fatura em perfil diferente do cartão (dado inconsistente), a fatura existente é devolvida e um aviso é registrado no log. O diagnóstico também aponta esse caso.
- **Faturas pagas** continuam no índice: são a mesma fatura. O redirecionamento de parcelas para a fatura seguinte, quando a do mês está paga, não mudou (testado).

**Diagnóstico do banco de teste** (`scripts/diagnostico_faturas_duplicadas.py`, somente leitura): **0 faturas**. Também deu zero em:
- grupos duplicados;
- competência ausente ou fora do dia 1;
- perfil divergente do cartão;
- item que não é cartão.

O banco local do Flask (`gastos.db`) não foi aberto, porque pode ter dados reais. A migration Alembic faz a mesma verificação ao ser aplicada.

## 3. Alterações nos pontos de criação

- **Flask, `CartaoService.get_or_create_fatura`:**
  - o INSERT passou a ser feito num **savepoint**;
  - se o índice acusar a violação **desta** restrição, a fatura existente (gravada pela outra transação) é devolvida e a transação do chamador continua intacta;
  - qualquer outra violação de integridade **propaga**. O reconhecimento se baseia no nome da restrição (PostgreSQL) ou nas colunas (SQLite), em `_violou_fatura_unica`;
  - a consulta prévia continua lá, mas **o banco é quem decide**.
- **Flask, `Conta.__table_args__`:** declara o índice, com o mesmo nome e predicado, para `create_all` e testes.
- **Novo aplicativo, `gerar_mes_interno`:**
  - o INSERT da fatura usa `ON CONFLICT (item_despesa_id, cartao_competencia) WHERE is_fatura_cartao DO NOTHING`;
  - a fatura criada simultaneamente por outro caminho é contada como **existente** no relatório;
  - nada mais mudou na função, que foi gerada a partir da original.
- Os cálculos de planejado e executado, pagamento, estorno, compras e saldos **não mudaram**.

## 4. Testes simultâneos (concorrência real no PostgreSQL)

Os processos Flask reais param numa barreira **depois** de a consulta responder "não existe" e **antes** do INSERT, ou depois do INSERT e **antes** do commit. Isso garante corrida de verdade, não execução sequencial.

| # | Cenário | Resultado |
|---|---|---|
| 1 | Dois processos Flask, mesma fatura | **1 fatura**; os dois recebem o mesmo id |
| — | Controle: a mesma corrida **sem** o índice | **2 faturas** (a duplicação era real) |
| 2 | Duas gerações do novo aplicativo | 1 fatura por competência; uma geração cria 2 e a outra 0 |
| 3a | O Flask consultou, o novo app criou e gravou, o Flask insere | O Flask recebe a fatura do novo app; 1 fatura |
| 3b | O Flask inseriu sem commit, o novo app tenta inserir (fica **esperando a trava**, verificado em `pg_stat_activity`) e o Flask faz o commit | O novo app conta a fatura como existente e cria só a de abril; 1 fatura |
| 4 | Duas compras parceladas (3x) simultâneas no mesmo cartão | 1 fatura em cada um dos 3 meses; **6 parcelas** (2 compras × 3), cada compra somando 300,00 |
| 5 | Geração de recorrências e compra no mesmo mês | 1 fatura; a compra e o lançamento recorrente estão nela |
| — | Fatura paga + duas compras simultâneas | Fatura paga idêntica (md5); parcelas redirecionadas para julho; 1 fatura em julho |

**Outros testes:**
- **Migration:**
  - preserva faturas e lançamentos existentes (md5 idêntico);
  - **aborta sem alterar nada** quando há duplicidade (as faturas duplicadas permanecem);
  - é idempotente.
- **Movimentos bancários e saldo:** inalterados (impressão digital).
- **Segurança:** o navegador continua sem inserir em `public.conta` e sem executar `gerar_mes_interno`; a T1 continua valendo.
- **SQLite (Flask):**
  - índice no modelo;
  - outras competências e contas comuns permitidas;
  - idempotência;
  - conflito simulado devolve a existente;
  - outra violação de integridade não é engolida;
  - a migration Alembic aborta com duplicidade e é idempotente.

| Conjunto | Resultado |
|---|---|
| `tests/test_supabase_fatura_unica.py` (novo, concorrência real) | 11/11 |
| `tests/test_fatura_unica_flask.py` (novo, SQLite) | 11/11 |
| Regressão FIN-RECORRENCIA-1 + T1 | 86/86 |
| E2E local | 30/30 |
| Suíte completa | 1224 passaram; só as 5 falhas antigas (§10) |

## 5. Impacto no Flask

- O comportamento é o mesmo em uso normal.
- Na corrida, quem perde recebe a fatura existente em vez de criar uma segunda.
- O commit interno de `get_or_create_fatura` foi mantido (contrato original do método).
- Bancos sem o índice (antes da migration) seguem como antes.

## 6. Compatibilidade com o novo aplicativo

- A identidade da fatura é a mesma do plano (`plano_recorrencia` reconhece por cartão + competência).
- A trava por perfil e a T1 continuam.
- Uma corrida com o Flask não gera erro nem duplicata: a fatura entra como "já existente".
- A prévia não mudou.

## 7. Dados históricos inconsistentes

**Nenhum no banco de teste.** Se houver em outro banco:
- as duas migrations **abortam sem alterar nada**;
- `scripts/diagnostico_faturas_duplicadas.py` lista os grupos (só ids);
- o tratamento (manter, consolidar ou excluir) fica para decisão explícita, nunca automática.

## 8. Migrations preparadas

| Migration | Para | Observação |
|---|---|---|
| `supabase/migrations/20261025090000_financeiro_fatura_unica.sql` | Supabase | Verificação de duplicidade → índice (`IF NOT EXISTS`) → `gerar_mes_interno` com `ON CONFLICT` |
| `migrations/versions/d81f5a2b9c3e_fatura_unica_cartao_competencia.py` | Alembic (bancos do Flask, inclusive SQLite local) | Revisa `c4f7a2d91b3e`; mesma verificação e mesmo índice (`IF NOT EXISTS`) |

- As duas usam o mesmo nome de índice: a que rodar primeiro cria e a outra não faz nada.
- No Supabase de teste, a aplicação seria por `scripts/supabase_migrations.py aplicar --versoes 20261025090000`, **com nova autorização**.
- Sem aplicar a Alembic no remoto, a versão do Alembic lá continua `c4f7a2d91b3e`, e o índice viria só da migration do Supabase.

## 9. Arquivos alterados

- `backend/services/cartao_service.py`: savepoint e `_violou_fatura_unica`.
- `backend/models.py`: índice declarado em `Conta`.
- `migrations/versions/d81f5a2b9c3e_fatura_unica_cartao_competencia.py` (novo).
- `supabase/migrations/20261025090000_financeiro_fatura_unica.sql` (novo).
- `scripts/diagnostico_faturas_duplicadas.py` (novo, somente leitura).
- `tests/test_supabase_fatura_unica.py` e `tests/test_fatura_unica_flask.py` (novos).
- `docs/FIN_FATURA_UNICA_1.md` e `docs/ROADMAP.md`.

## 10. Suíte completa

**1224 passaram, 19 pulados, 5 falhas** — exatamente as 5 que já falhavam desde `0e04407` (mobilidade/veículos, OCR x2, receitas UX). O índice declarado no model não quebrou nenhum teste existente do Flask (cartões, parcelamento, faturas). Nenhuma regressão.
