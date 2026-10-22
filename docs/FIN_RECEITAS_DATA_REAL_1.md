# FIN-RECEITAS-DATA-REAL-1 — Data prevista de recebimento e validação no Supabase de teste

**Data:** 2026-10-22.

**Alvo:** projeto Supabase de teste **Controle-Financeiro** (`fzjmge…`). A Calculadora Judicial não foi tocada.

**Situação:** **implementado, validado localmente e no Supabase de teste**. Os dados fictícios foram removidos e o estado final ficou idêntico ao inicial, exceto pela migration autorizada.

**Autorização:** SCRIPT-CONTRATO V5 — FIN-RECEITAS-DATA-REAL-1 (decisão do usuário: opção **(a)**).

**Não foi feito:**
- publicar;
- usar ou alterar dados reais;
- executar a migration Alembic em banco pessoal (`gastos.db`) ou no remoto.

## 1. Solução: competência diferente da data prevista

Três conceitos distintos:

| Informação | Onde fica | Exemplo |
|---|---|---|
| Competência | `receita_orcamento.mes_referencia` (já existia) | 10/2026: orçamento ao qual pertence |
| **Data prevista** | **`receita_orcamento.data_prevista`** (nova, `DATE`, **nula**) | 05/11/2026: quando se espera receber |
| Data efetiva | `receita_realizada.data_recebimento` (futuro módulo de recebimentos) | 06/11/2026 |

**Regras:**
- Sem data explícita (todos os registros antigos e os criados pelo Flask), vale a **regra antiga**: o dia previsto da fonte no mês da competência.
- **Nada é preenchido retroativamente.** Nenhuma competência, valor, recebimento ou saldo é alterado.
- **Totais continuam por competência.** A previsão de outubro com recebimento em novembro soma em outubro e não aparece em novembro.
- **Recorrência:** a data informada para a primeira competência define a regra (dia e defasagem em meses). Cada uma das 12 previsões guarda **a sua** data, calculada pelo dia contratual: dia 31 vira 28/29 nos meses curtos e volta a 31 depois, sem deriva. A virada de ano e o ano bissexto são tratados.
- **Exceção:** editar a data de uma competência não desloca as seguintes. Limpar a data volta à regra do dia da fonte.
- **Validação:** a data prevista fica a até 12 meses da competência.
- **Tela:**
  - campos separados **Competência** (mês) e **Data prevista** (dia);
  - quando caem em meses diferentes, a linha mostra as duas: "Prevista para 05/11/2026 · competência 10/2026";
  - nenhum botão de recebimento.

## 2. Compatibilidade com o Flask e com registros antigos

**`backend/models.py` — `ReceitaOrcamento.data_prevista`:**
- mapeada como **`deferred`**, com `server_default NULL` e `__mapper_args__ = {'eager_defaults': False}`;
- o Flask não seleciona, não insere e não pede de volta a coluna.

**Efeitos comprovados:**
- O Flask **funciona num SQLite sem a coluna**: cria fonte recorrente, gera e atualiza previsões, lista por ano.
- Uma **data explícita é preservada** quando o Flask atualiza a previsão (valor ou observações), tanto em SQLite quanto em PostgreSQL, com o Flask real.
- Nenhum serviço ou rota do Flask foi alterado.
- O mecanismo `ensure_sqlite_schema_compat`, que altera o banco local na inicialização, **não** foi usado. O `gastos.db` não muda.

**Migration Alembic `migrations/versions/e3b7c9d1a2f4_data_prevista_receita_orcamento.py`:**
- revisa `d81f5a2b9c3e`;
- `ADD COLUMN data_prevista DATE` só se faltar; idempotente;
- **testada só em bancos fictícios** (SQLite temporário e cópia PostgreSQL descartável);
- **não executada** no `gastos.db` nem no remoto.

**Migration do Supabase `20261027090000_financeiro_receitas.sql`:**
- **consolidada** (estava pendente e nunca foi aplicada; nenhuma versão aplicada foi alterada);
- `alter table public.receita_orcamento add column if not exists data_prevista date`;
- inclui as funções ajustadas.

## 3. Arquivos e migrations alterados

- `supabase/migrations/20261027090000_financeiro_receitas.sql`:
  - coluna e comentário;
  - `validar_data_prevista` (interna);
  - `receitas_do_mes` com a data efetiva e `data_prevista_explicita`;
  - `ler_dados_receita`, `criar_receita` (data ou regra), `editar_receita` (data desta competência) e `receita_para_edicao`.
- `migrations/versions/e3b7c9d1a2f4_data_prevista_receita_orcamento.py` (novo).
- `backend/models.py`: coluna deferred.
- `web/src/js/receitas.js`: campos e exibição.
- `web/tests/e2e/receitas.spec.mjs`: cenário outubro → novembro e regra da recorrência.
- `tests/test_supabase_receitas_data.py` (novo, 16 testes).
- `scripts/supabase_receitas_seed_teste.py` (novo).
- `scripts/supabase_receitas_real.py` (novo).
- `scripts/supabase_despesas_real_limpeza.py`: cobre também as tabelas de receitas.
- `docs/FIN_RECEITAS_1.md`, `docs/FIN_RECEITAS_DATA_REAL_1.md` e `docs/ROADMAP.md`.

## 4. Testes locais

| Conjunto | Resultado |
|---|---|
| `tests/test_supabase_receitas_data.py` (novo) | **16/16** |
| `tests/test_supabase_receitas.py` | 50/50 |
| E2E local (390 px) | **43/43** |
| Testes unitários do `web/` | 7/7 |
| Suíte completa | **1347 passaram**, 19 pulados; só as 5 falhas que já existiam (§8) |

**Itens do contrato:**

| # | Item | Resultado |
|---|---|---|
| 1 | Outubro → novembro | ok |
| 2 | Dezembro → janeiro | ok |
| 3 | Mesmo mês | ok |
| 4 | Registros antigos | Regra do dia da fonte, sem preenchimento |
| 5 | Recorrência de 12 competências | Com a regra, inclusive a virada de ano |
| 6 | Bissexto | 29/02/2028 |
| 7 | Datas explícitas após editar a fonte | Preservadas; as antigas acompanham o dia da fonte |
| 8 | Concorrência | Edições simultâneas da mesma versão: só uma vale; cadastro com a mesma chave ×3: 1 |
| 9 | Receita recebida | Data bloqueada |
| 10 | Movimento | Nenhum |
| 11 | Autorização | LEITOR não edita |
| 12 | Equivalência e compatibilidade com o Flask | Atualização do Flask preserva a data; Flask em SQLite sem a coluna; migration Alembic em banco fictício |
| 13 | Regressão | Suíte completa |

## 5. Testes reais (Supabase de teste)

**Sequência:**
1. Push de `b0aafa2` após revisão. O check "Supabase Preview" ficou `skipped`: o deploy automático continua desligado.
2. `status` e `simular`: **só `20261027090000`** pendente e ainda não aplicada.
3. **Conferência do SQL e das dependências** (somente leitura):
   - colunas e funções usadas existem;
   - `data_prevista` ainda não existia;
   - nenhum dos 18 objetos novos colide;
   - a única alteração em tabela existente é a coluna nova e nula;
   - nada é apagado;
   - as funções escrevem só em `item_receita`, `receita_orcamento` e `financeiro.operacao_receita`, nunca em recebimento ou movimento;
   - `receita_realizada` pertence a `postgres` (necessário para a trava `SHARE`).
4. Impressão digital inicial; aplicação **exclusiva e única** de `20261027090000`.
5. **Privilégios:**
   - nenhuma função com EXECUTE para `anon`;
   - 8 públicas só para `authenticated`;
   - 9 internas sem EXECUTE para o navegador;
   - `operacao_receita` com RLS forçada e sem privilégios.
6. **Dados fictícios:** perfis, contas, recorrência, **receitas** (`scripts/supabase_receitas_seed_teste.py`) e MVP.
7. **E2E real:** **43/43**. Inclui as 7 telas de receitas: situação parcial e prevista, totais, competência outubro com prevista em novembro, recorrência com regra de data, LEITOR sem ações e 403.
8. **API real** (`scripts/supabase_receitas_real.py`): **12/12**.
   - competência × data: out/nov, dez/jan, mesmo mês;
   - registros antigos;
   - recorrência de 12 competências sem deriva;
   - 29/02/2032;
   - datas preservadas após editar a fonte;
   - concorrência ([200, 400]; mesma chave ×3 → 1);
   - receita recebida bloqueada;
   - **contas bancárias e movimentos idênticos**;
   - autorização (LEITOR, outro perfil e leitura alheia: 403; anônimo: 401; isolamento);
   - **totais por competência** (10/2030 = R$ 20.000,00; nada em 11/2030).

## 6. Autorização e RLS

- **Leitura:** exige vínculo ativo com o perfil.
- **Escrita:** exige **gestão explícita** (`pode_gerir`).
- **Registros fora do perfil:** 42501. REST: 403. Sem login: 401.
- **Tabelas legadas:** continuam fora da Data API (`public` não exposto).
- **Tabela nova:** com RLS forçada e sem privilégios.

## 7. Limpeza

**Ordem:**
1. `scripts/supabase_despesas_real_limpeza.py remover` removeu tudo o que os testes criaram:
   - 1 movimento, 2 identidades, 1 conta, 1 item e 2 chaves de despesas;
   - 2 recebimentos, 35 previsões, 13 fontes e 10 chaves de receitas.
2. Removedores dos seeds: MVP, receitas, recorrência, contas e perfis.

**Impressão digital final idêntica à inicial em:**
- **conteúdo** de `item_receita` (o registro preexistente ficou intacto), `receita_orcamento`, `receita_realizada`, `conta`, `item_despesa`, `lancamento_agregado`, `conta_bancaria`, `movimento_financeiro`, `perfil_financeiro`, `categoria`, `categoria_cartao`, `cartao_categoria_limite` e `usuario`;
- `financeiro.perfil_acesso` e `financeiro.categorias`;
- contagens das 52 tabelas `public`, Auth e Alembic (`c4f7a2d91b3e`).

**Diferenças, só as esperadas:**
- migrations (+`20261027090000`);
- a coluna `data_prevista` (objeto da migration);
- `financeiro.operacao_receita`, que existe **vazia** (as demais tabelas do schema também estão vazias);
- sequências avançadas, o que é normal.

## 8. Suíte completa: as 5 falhas preexistentes

- `test_categorias_sistemicas_mobilidade::test_projecoes_veiculo_usam_categorias_sistemicas_granulares`
- `test_ocr_tools::test_status_sem_ferramentas_retorna_estrutura_valida`
- `test_ocr_tools::test_poppler_ausente_retorna_aviso`
- `test_receitas_ux::test_cards_resumo_calculam_previsto_realizado_diferenca_confiabilidade` (tela do Flask; não tocada)
- `test_veiculos_mobilidade_2b::test_suprimir_despesas_previstas_futuras`

## 9. Pendências

- **Banco local do Flask (`gastos.db`):** quando você decidir, aplicar a Alembic `e3b7c9d1a2f4` (e a `d81f5a2b9c3e`, da fatura única), com backup antes. Até lá o Flask funciona sem a coluna (comprovado).
- **FIN-PAGAMENTO-TRAVA-1** continua bloqueador antes de qualquer recebimento ou pagamento efetivo.
- A tela do Flask continua mostrando a data pelo dia da fonte. Exibir a data explícita lá é opcional e ficou fora deste escopo.
