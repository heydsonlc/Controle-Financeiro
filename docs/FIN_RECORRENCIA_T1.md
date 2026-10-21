# FIN-RECORRENCIA-T1 — Gerador único de recorrências por perfil financeiro

**Data:** 2026-10-21. Implementado e testado **localmente**: cluster PostgreSQL descartável, Flask real em subprocesso, PostgREST e Playwright, tudo com dados fictícios.

**Não foi feito:**
- aplicar migration no remoto;
- publicar;
- alterar dados reais.

**Autorização:** SCRIPT-CONTRATO V5 — FIN-RECORRENCIA-T1 (transição T1 aprovada).

## 1. Configuração do gerador por perfil

- **`financeiro.gerador_recorrencia(perfil_financeiro_id, gerador, alterado_em, alterado_por, motivo)`:**
  - `gerador` aceita `FLASK` ou `NOVO`;
  - **sem linha, o perfil fica em `FLASK`**, que é o padrão; nenhum perfil migra sozinho;
  - responsável e motivo são obrigatórios.
- **Troca:** só pela função `financeiro.definir_gerador_recorrencia(perfil, gerador, responsavel, motivo)`, executada por administrador no SQL Editor ou na CLI.
  - Ela não tem EXECUTE para `anon` nem para `authenticated`, e a tabela não dá privilégios a eles.
  - Valida o gerador, o responsável, o motivo e se o perfil existe.
  - Espera as gerações em andamento (trava consultiva exclusiva) e devolve, por exemplo, `Perfil 101: FLASK (padrao) -> NOVO`.
- **Auditoria:** um gatilho grava cada inserção, alteração e exclusão em `financeiro.gerador_recorrencia_historico`, com gerador anterior e novo, responsável, motivo e papel do banco. Isso vale **inclusive para SQL direto**.
- **Exemplo da troca prevista** (fase remota, só em perfil fictício):
  ```sql
  select financeiro.definir_gerador_recorrencia(<id do perfil>, 'NOVO', '<responsável>', '<motivo>');
  ```
  Nada troca automaticamente. Pessoal e Empresa continuam no Flask até uma autorização específica.

## 2. Arquivos alterados no Flask

| Arquivo | Alteração |
|---|---|
| `backend/services/gerador_recorrencia_service.py` (novo) | `flask_pode_gerar(perfil, contexto)` e `perfil_efetivo` (NULL → Pessoal) |
| `backend/routes/despesas.py` (+8 linhas) | Guarda no orquestrador `gerar_execucao_despesa_recorrente` e no laço de faturas virtuais do GET |
| `backend/services/cartao_service.py` (+5 linhas) | Guarda em `gerar_faturas_mes_atual` (job e scheduler) |

Nenhum cálculo, pagamento, estorno, saldo ou financiamento foi alterado.

**Comportamento de `flask_pode_gerar`:**

| Situação | Resultado |
|---|---|
| Banco sem a configuração (SQLite, ou migration não aplicada) | **Legado**: o Flask gera |
| Perfil sem linha ou em `FLASK` | O Flask gera |
| Perfil em `NOVO` | O Flask **não** gera (registra no log) |
| Valor inesperado, perfil indefinido ou **erro na verificação** | **Bloqueia** a geração e registra o motivo; nunca deixa os dois motores ativos |

- A verificação roda num *savepoint*: um erro nela não derruba a requisição, e a consulta continua funcionando.

## 3. Como os pontos de geração foram protegidos

| Ponto de entrada | Proteção |
|---|---|
| GET `/api/despesas/?mes_referencia=` (recorrências) | Orquestrador → guarda por item (perfil do item; NULL → Pessoal) |
| GET `/api/despesas/?mes_referencia=` (faturas virtuais) | Guarda por cartão e por fatura (verificada de novo após cada `commit`) |
| POST `/api/despesas` e `/api/recorrencias` (primeiro mês) | Orquestrador: o cadastro é feito, a geração não |
| `CartaoService.gerar_faturas_mes_atual` (`jobs/gerar_faturas_mensais.py` e `scheduler.py`) | Guarda por cartão |
| Novo motor (`financeiro.gerar_mes`, `reativar_competencia`) | Exige gestão (`pode_gerir`) e gerador `NOVO`, validados no banco com trava; nada vem do navegador |

**Fora da guarda, de propósito:** `get_or_create_fatura` chamado no cadastro de compras e parcelas, no recálculo e nos alertas. São operações legítimas, protegidas pelo contrato.
- A identidade da fatura (cartão + competência) é a mesma nos dois motores e as duas implementações verificam a existência antes de criar, então criar sob demanda não duplica em uso sequencial.
- Não há chave única no banco para a fatura. Por isso continua teórica (não testada) uma corrida entre o cadastro de uma compra no Flask e a geração do novo motor, exatamente ao mesmo tempo, no mesmo perfil.
- Veículos e transporte por app geram despesas previstas, não contas, e seguem fora do escopo.

**Concorrência:**
- O Flask toma a trava consultiva **compartilhada** `(20261023, perfil)` ao verificar.
- A troca de gerador e o novo motor tomam a trava **exclusiva**.
- Por isso a troca espera a geração em andamento de qualquer um dos dois.
- O novo motor também prende a linha da configuração (`FOR SHARE`) até o fim da transação.

## 4. Resultado do requisito 6 do FIN-RECORRENCIA-1

**Passa.** O antigo teste xfail virou um teste normal: `test_flask_nao_recria_competencias_dispensadas_nem_corrigidas`.

Com o perfil atribuído ao novo motor, depois de gerar com uma competência dispensada, o GET do Flask em março e abril **não cria nenhum registro**. Isso vale para:
- a competência dispensada;
- as contas com vencimento corrigido;
- a recorrência inativa;
- a semanal;
- as compras;
- as faturas.

**Equivalência com ressalva:** ela vale enquanto o perfil estiver em `NOVO`. Devolver o perfil ao `FLASK` reativa o comportamento antigo: o Flask volta a gerar e não conhece as dispensas. O teste `test_voltar_para_flask_reativa_o_comportamento_legado` documenta isso para o administrador.

## 5. Testes

**Requisitos do contrato T1:**

| # | Requisito | Teste |
|---|---|---|
| 1 | Perfil não migrado gera pelo Flask | `test_1_…`: Pessoal e Empresa geram com outro perfil migrado |
| 2 | Perfil migrado não gera pelo Flask | `test_2_…`: GET (dois meses), cadastro de recorrência, job de faturas |
| 3 | Perfil migrado gera pelo novo | `test_3_…` |
| 4 | Perfil não migrado não gera pelo novo | `test_4_…`: gerar e reativar recusados, nada gravado; quem só lê recebe "não autorizado" antes de saber o gerador |
| 5–8 | Dispensa, correção, inativa, compras e faturas | `test_5_a_8_…` (de ponta a ponta com o Flask) e os 51 testes do FIN-RECORRENCIA-1 |
| 9 | Troca só por administrador | `test_9_…`: navegador e anônimo não trocam nem leem; auditoria inclusive de SQL direto; trocas inválidas recusadas |
| 10 | Consulta e pagamento do Flask funcionam | `test_10_…`: o Flask lista e paga uma conta do perfil migrado (movimento criado) |
| 11 | Concorrência e repetição | `test_11_…`: a troca espera a geração do novo motor e a do Flask em andamento; repetição e geração concorrente nos testes do FIN-RECORRENCIA-1 |
| 12 | Erro na verificação não ativa os dois | `test_12_…`: no erro, o Flask não gera em nenhum perfil e a consulta segue; sem a migration, comportamento legado; no novo motor, o erro também não grava |

**Totais:**

| Conjunto | Resultado |
|---|---|
| `tests/test_supabase_gerador_t1.py` (novo) + `tests/test_supabase_recorrencia.py` | **86 passaram, 0 xfail** |
| E2E local (390 px) | **30/30**: novo teste "perfil ainda gerado pelo sistema atual"; o Perfil B é atribuído ao novo motor na semeadura |
| Testes unitários do `web/` | 7/7 |
| Suíte completa | 1202 passaram; só as 5 falhas antigas (§8) |

- A tela diferencia as duas situações. Quem gerencia um perfil ainda no Flask vê "A geração deste perfil ainda é feita pelo sistema atual". Quem só lê vê "Somente quem gerencia este perfil pode gerar".

## 6. Regressões identificadas

Nenhuma, além das 5 falhas que já existiam desde `0e04407` (ver §8).

Comportamento novo, **intencional**: num perfil migrado, o Flask cadastra recorrências, mas não gera o primeiro mês. A geração fica com o novo aplicativo.

## 7. Migrations necessárias (fase remota, com autorização própria)

1. `20261023090000_financeiro_recorrencia.sql`: FIN-RECORRENCIA-1. Já está no `main` remoto, **pendente**.
2. `20261024090000_financeiro_gerador_recorrencia.sql`: T1 (nova).
   - Cria a configuração, o histórico, `definir_gerador_recorrencia` e `exigir_gerador_novo`.
   - Renomeia as funções públicas do FIN-RECORRENCIA-1 para `*_interno`/`*_interna`, sem EXECUTE para o navegador.
   - Recria `gerar_mes`, `reativar_competencia` e `previa_geracao` com a verificação do gerador. A prévia passa a devolver `gerador`, `pode_gerir` e `pode_gerar`.

As duas devem ser aplicadas juntas e nessa ordem:

```
scripts/supabase_migrations.py aplicar --versoes 20261023090000 20261024090000
```

**Preparação da fase remota:**
- Confirmar que o deploy automático continua desligado. No push de `eb22ee8`, o check "Supabase Preview" saiu `skipped` e a migration continuou pendente.
- Ajustar os seeds de teste: `pode_gerir` nos vínculos fictícios e `definir_gerador_recorrencia` só no perfil fictício.
- Incluir as tabelas novas na limpeza e as funções novas nas pré-verificações do `run_e2e_real.py`.
- **Não** atribuir Pessoal nem Empresa ao novo gerador.

## 8. Suíte completa

**1202 passaram, 19 pulados, 0 xfail, 5 falhas** — exatamente as 5 que já falhavam desde `0e04407` (mobilidade/veículos, OCR x2, receitas UX). A suíte do Flask roda em SQLite, onde a guarda mantém o comportamento legado: nenhuma regressão na geração existente.
