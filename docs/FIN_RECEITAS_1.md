# FIN-RECEITAS-1 — Cadastro e gestão de receitas previstas

**Data:** 2026-10-21. Implementado e testado **localmente**: cluster PostgreSQL descartável, Flask real para comparação, PostgREST e Playwright, com dados fictícios.

**Não foi feito:**
- aplicar migration no remoto;
- publicar;
- alterar dados reais;
- **registrar recebimento ou movimentar conta**.

**Autorização:** SCRIPT-CONTRATO V5 — FIN-RECEITAS-1. O push de `e0dd19c` foi feito após revisão.

## 1. Estrutura de receitas encontrada no Flask

| Tabela | Papel | Campos principais |
|---|---|---|
| `item_receita` | **Fonte** | `nome` (único por perfil), `tipo` (SALARIO_FIXO, GRATIFICACAO, RENDA_EXTRA, ALUGUEL, RENDIMENTO_FINANCEIRO, OUTROS: faz o papel de **categoria**), `valor_base_mensal`, `dia_previsto_pagamento`, `conta_bancaria_id`, `recorrente`, `ativo` |
| `receita_orcamento` | **Previsão** mensal | `item_receita_id`, `mes_referencia` (competência), `valor_esperado`, `periodicidade` (MENSAL_FIXA, EVENTUAL ou UNICA), `observacoes` |
| `receita_realizada` | **Recebimento** efetivo | `data_recebimento`, `valor_recebido`, `mes_referencia`, `conta_bancaria_id`, `orcamento_id`, `descricao`. Com `item_receita_id` NULL, é a receita **pontual** |

- **Não há coluna de status nem categoria própria.** A situação é derivada dos registros.
- O recebimento cria `movimento_financeiro` de crédito (`origem='RECEITA'`) na mesma transação.

## 2. Regras existentes no Flask (conferidas no código)

**Situação** (tela de receitas, `obterStatusReceita`), pela soma dos recebimentos da mesma fonte e competência:
- **REALIZADA:** recebido ≥ previsto;
- **PARCIAL:** 0 < recebido < previsto;
- **PREVISTA:** nada recebido.

**Recebimentos:**
- **Parcial:** o modelo permite vários recebimentos por fonte e competência; a situação PARCIAL vem da soma.
- **Estorno:** cria movimento compensatório `origem='ESTORNO_RECEITA'`, sem apagar o recebimento. "Estornada" é a presença desse movimento.
- **Excluir recebimento:** bloqueado se houver movimento vinculado.

**Recorrência:**
- Criar ou editar uma fonte **recorrente** com valor base **gera 12 previsões a partir do mês atual** (pula as existentes), com a observação "Gerado automaticamente - nome".
- A tela também mostra uma linha **virtual** para a fonte recorrente ativa sem previsão gravada no mês.

**Exclusão e inativação:**
- "Excluir previsão" na tela do Flask = **zerar** a previsão ("Removido pelo usuário"); ela não é apagada.
- "Excluir fonte" = `ativo=false`, com previsões e recebimentos mantidos.

**Outros:**
- **Duplicidade:** fonte com o mesmo nome no perfil é recusada (restrição única). A previsão por fonte e competência é "cria ou atualiza".
- **Consórcio:** a contemplação grava um `receita_realizada` **sem conta** e com `consorcio_id=N` nas observações. A tela trata isso como previsão "pendente de confirmação" (outro módulo).
- **Gravação dentro de consulta:** `GET /api/receitas/itens` e `GET /api/receitas/resumo-mensal` rodam o backfill de contemplação de consórcio, que grava.
- **Perfil:** NULL pertence ao Pessoal (`condicao_perfil`).

## 3. Funcionalidades implementadas

### 3.1 Migration `supabase/migrations/20261027090000_financeiro_receitas.sql` (só local)

| Função | O que faz |
|---|---|
| `receitas_do_mes(perfil, mês)` | Previsões e recebimentos da competência, com a **situação derivada dos registros reais**: PREVISTA, PARCIAL, RECEBIDA, INATIVA (fonte inativa), REMOVIDA (zerada), ESTORNADA, PREVISTA_CONSORCIO. Também traz a data prevista (dia da fonte na competência, ajustado nos meses curtos) e a conta |
| `fontes_de_receita(perfil)` | Fontes do perfil, para escolher no cadastro |
| `receita_para_edicao(perfil, previsão)` | Dados e permissões calculadas no banco, com motivo de bloqueio e versão |
| `criar_receita(perfil, dados, chave)` | Fonte nova (avulsa: 1 previsão `UNICA`; recorrente: 12 previsões `MENSAL_FIXA` a partir da competência) ou previsão de fonte existente. **Idempotente pela chave** |
| `editar_receita(perfil, previsão, versão, dados)` | Valor, observações e (fonte avulsa) competência |
| `excluir_receita(perfil, previsão, versão)` | Fonte recorrente: **zera como o Flask**. Fonte avulsa: apaga a previsão e a fonte sem outras referências |
| `editar_fonte_receita` / `inativar_fonte_receita` | Nome, categoria, dia, conta de destino e descrição, ou inativação. **Não altera** previsões nem recebimentos registrados |

**Funções internas, sem EXECUTE para o navegador:** `receita_estornada`, `fonte_de_outro_modulo`, `bloqueio_da_previsao`, `ler_dados_receita`, `travar_previsao`, `travar_fonte`, `versao_previsao` e `versao_fonte`.

**Tabela nova:** `financeiro.operacao_receita` (idempotência), com RLS forçada e sem privilégios para o navegador.

### 3.2 Tela

- **`web/src/receitas.html` + `js/receitas.js`**, com utilitários em `js/comum.js`.
- **Acesso:** abas **Contas | Receitas** no topo. "Contas do mês" continua sendo a tela inicial, e a aba leva ao **mesmo mês**.
- **Totais:**
  - Previsto (sem removidas e inativas);
  - Recebido (só o efetivamente recebido);
  - A receber.
  - Nota fixa: *"Previsão não altera saldo. Recebimentos continuam sendo registrados no sistema atual."*
- **"Nova receita":** só para quem gerencia o perfil. O formulário pede:
  - fonte (nova ou existente);
  - para fonte nova: nome, categoria, recorrência (avulsa ou mensal por 12 meses), dia previsto e conta de destino;
  - valor, competência e observações.
- **Ao abrir uma previsão:** só as ações permitidas pelo banco: Editar, Excluir, Editar fonte, Inativar fonte. Com recebimento, aparece o motivo do bloqueio.
- **Sem nenhum botão** de recebimento, estorno ou conciliação.
- **Build:** a lista de RPCs inclui as leituras de receitas e `pode_gerir_perfil`; as 5 escritas só são permitidas em `receitas.js`. `receitas.html` entrou nas páginas permitidas da sessão.

## 4. Diferenças intencionais em relação ao Flask

1. **Sem linhas virtuais:** a consulta mostra só **registros reais** (previsões e recebimentos), conforme o contrato. Uma fonte recorrente sem previsão no mês não aparece como prevista.
2. **Recorrência a partir da competência escolhida:** o Flask usa o mês atual. A editada **não regenera** previsões (o Flask regenera os 12 meses ao editar a fonte).
3. **Previsão com recebimento (mesmo estornado) não muda.** O Flask permite reescrever o orçamento de um mês já recebido.
4. **Previsão de fonte existente:** se já existe previsão da fonte na competência, o cadastro é **recusado** e a edição é explícita. O Flask sobrescreve em silêncio.
5. **Previsão avulsa excluída é apagada**, junto com a fonte avulsa sem outras referências. Nada fica órfão. A recorrente é zerada como no Flask.
6. **Fontes do módulo de consórcios** (contemplação) ficam **bloqueadas** e aparecem como "Prevista (consórcio)".
7. **Totais excluem estornos:** um recebimento estornado não conta como recebido. Os resumos do Flask somam todos os recebimentos.

## 5. Testes

| Conjunto | Resultado |
|---|---|
| `tests/test_supabase_receitas.py` (novo) | **50/50** |
| E2E local (390 px) | **42/42**: 6 novos em `receitas.spec.mjs` |
| Testes unitários do `web/` | 7/7 |
| Suíte completa | 1331 passaram; só as 5 falhas antigas (§9) |

| # | Teste obrigatório | Cobertura |
|---|---|---|
| 1 | Cadastro de prevista | Fonte + previsão; **nenhum recebimento ou movimento**; aparece como PREVISTA |
| 2 | Competência × data prevista | A data prevista é o dia da fonte na competência (31 → 28 em fevereiro). Ver §8 |
| 3 | Categoria | Tipo fora da lista: recusado |
| 4 | Conta de destino | Ativa e do perfil (o legado NULL do Pessoal é aceito); de outro perfil: recusada |
| 5 | Edição antes do recebimento | Valor, observações e competência (avulsa); a recorrente não muda de competência |
| 6, 7 | Bloqueio após recebimento total e **parcial** | Editar e excluir: bloqueados, e o recebido continua intacto; o estornado também preserva |
| 8 | Exclusão segura | Avulsa sem órfãos; recorrente zerada e exibida como REMOVIDA |
| 9 | Recorrência | 12 previsões a partir da competência, com o texto do Flask |
| 10, 11 | Pessoal e Empresa | Isolamento entre os perfis; Empresa com gestor cadastra só na Empresa |
| 12, 13 | Gestor e somente leitura | LEITOR vê, mas não cria, edita, exclui nem inativa (42501 e 403 no REST) |
| 14, 15 | Outro perfil e anônimo | Perfil trocado e conta alheia: 42501. Anônimo: sem permissão em todas as funções. Internas e tabelas legadas: negadas |
| 16 | Cadastros simultâneos | 3 cadastros da **mesma fonte** em paralelo: 1 fonte e 1 previsão |
| 17 | Edições simultâneas | Mesma versão em paralelo: **uma vale** |
| 18 | Chave idempotente | Repetida e 3 simultâneas: 1 cadastro |
| — | Recebimento simultâneo (como o do Flask) | Recebimento em andamento: a edição **espera e depois fica bloqueada**. Recebimento iniciado durante a edição: **espera a edição terminar** |
| 19, 20 | Saldos e movimentos | `conta_bancaria`, `movimento_financeiro` e `receita_realizada` idênticos após criar, editar, excluir, editar e inativar fonte |
| 21 | Equivalência com o Flask | Fonte recorrente com as mesmas 12 previsões e todos os campos iguais; previsão avulsa de fonte existente; "excluir" recorrente (zerada); inativação de fonte: **tudo igual** ao Flask real. A situação segue `obterStatusReceita` |
| 22 | Regressão de despesas, recorrências e cartões | Suíte completa (§9) |

## 6. Concorrência e autorização (resumo)

- **Autorização no banco:**
  - leitura exige vínculo ativo com o perfil (`pode_acessar_perfil`);
  - escrita exige **gestão explícita** (`pode_gerir_perfil`);
  - registros fora do perfil dão 42501 (NULL → Pessoal).
- **Concorrência:**
  - `FOR UPDATE` na previsão e na fonte, com versão (md5) conferida;
  - trava consultiva por perfil para cadastros em série;
  - `LOCK … IN SHARE MODE` em `receita_realizada` enquanto uma previsão é alterada. Um recebimento simultâneo do Flask nunca se cruza com a alteração.
- **Erros explícitos** (`22023`, `P0001` com motivo, `42501`); nada é engolido.

## 7. Preservação dos saldos

**Nenhuma função desta migration** escreve em `receita_realizada`, `movimento_financeiro` ou `conta_bancaria`. Os testes conferem a impressão digital dessas três tabelas em todas as operações. A tela não oferece recebimento.

## 8. Pendências e decisões

- **Data prevista em outro mês:** o modelo do Flask só guarda o **dia** previsto (na fonte), aplicado ao mês da competência. "Salário de outubro pago em 05/11" não é representável sem mudança de esquema. Opções:
  - **(a)** coluna nullable `data_prevista` em `receita_orcamento` (Alembic + Supabase), exibida pelos dois sistemas;
  - **(b)** manter como está.
  Não criei estrutura paralela; **decisão sua**.
- **Gravação dentro de consulta no Flask** (backfill de consórcio em `GET /itens` e `GET /resumo-mensal`): registrada, sem alteração.
- **FIN-PAGAMENTO-TRAVA-1 continua bloqueador** antes de qualquer recebimento ou pagamento efetivo. O recebimento do Flask (`criar_realizada`) não trava a previsão. Aqui a proteção é do lado do novo aplicativo (trava `SHARE`); o recebimento em si será tratado no módulo próprio.
- **Validação no Supabase de teste** (FIN-RECEITAS-REAL-1, autorização própria): migration `20261027090000`, mais um seed fictício de receitas para o E2E real.

## 9. Suíte completa

**1331 passaram, 19 pulados, 5 falhas** — exatamente as 5 que já falhavam desde `0e04407`:

- `test_categorias_sistemicas_mobilidade::test_projecoes_veiculo_usam_categorias_sistemicas_granulares`
- `test_ocr_tools::test_status_sem_ferramentas_retorna_estrutura_valida`
- `test_ocr_tools::test_poppler_ausente_retorna_aviso`
- `test_receitas_ux::test_cards_resumo_calculam_previsto_realizado_diferenca_confiabilidade` (Flask; não tocado)
- `test_veiculos_mobilidade_2b::test_suprimir_despesas_previstas_futuras`

Nenhuma regressão em despesas, recorrências, faturas (cartões) e demais módulos.
