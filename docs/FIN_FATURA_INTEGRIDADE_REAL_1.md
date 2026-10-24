# FIN-FATURA-INTEGRIDADE-REAL-1 — Validação real da integridade das faturas

**Data:** 2026-10-23.

**Alvo:** projeto Supabase de teste **Controle-Financeiro** (`fzjmge…`). A Calculadora Judicial e os demais projetos não foram tocados.

**Situação:** **validado no Supabase de teste**.
- Migration `20261029090000` aplicada (somente ela).
- E2E real 47/47 e 14/14 cenários reais.
- Dados fictícios removidos; conteúdo das 61 tabelas de `public` e `financeiro` idêntico ao de antes.

**Autorização:** SCRIPT-CONTRATO V5 — FIN-FATURA-INTEGRIDADE-REAL-1.

**Não foi feito:**
- Alembic no `gastos.db` (continua em `9b8a09ecc52f`);
- produção, publicação no Cloudflare e push;
- restauração de backup;
- FIN-CARTOES-FECHAMENTO-1.

## 1. Identificação do ambiente

- Clone `C:\Users\ssp\dev\Controle-Financeiro`, HEAD `4c4dcb6`, árvore limpa. O SQL da migration é idêntico ao do commit (blob `c4261107…`, sem alteração desde `b669d5d`).
- **Projeto confirmado pela conexão efetiva:** usuário do pooler do projeto `fzjmge…` e região `us-east-2`, igual à informada pela API. A Calculadora fica em `us-west-2`. O histórico de migrations é o deste projeto.
- **Supabase CLI 2.116.0:** `db push` sem `--include-all` envia só migrations novas, sem seeds nem roles. O `scripts/supabase_migrations.py` recusa aplicar se as pendentes forem diferentes das autorizadas.
- **Recuperação disponível:** backups físicos diários (o último de 2026-10-23); PITR desligado.

## 2. Antes da aplicação

| Verificação | Resultado |
|---|---|
| Migrations | 10 locais, 9 remotas; pendente só `20261029090000`; nada só no remoto; `simular` lista só ela |
| Estrutura | As 74 funções do schema `financeiro` são idênticas ao estado local com 9 migrations (corpo, retorno e privilégios). `linha_plano` e as colunas das 7 tabelas usadas também. Dependências presentes; `fatura_elegivel_existente` ainda ausente |
| Privilégios | As 4 funções a substituir: `SECURITY DEFINER`, `search_path` vazio, dono `postgres`. EXECUTE só em `criar_compra`, para `authenticated`. Nenhuma função do schema para `PUBLIC` ou `anon`; `service_role` sem EXECUTE nelas |
| RLS | Ativa nas 7 tabelas (forçada nas de `financeiro`); nenhum privilégio de tabela para `anon` ou `authenticated` |
| Dados | 0 compras e 0 faturas; impressão digital das 61 tabelas de `public` e `financeiro` |
| Concorrência | Nenhuma outra sessão ativa |
| Diagnóstico | Definições das 4 funções salvas antes da troca (fora do repositório) |

## 3. Aplicação

`scripts/supabase_migrations.py aplicar --versoes 20261029090000`, das 11:59:06 às 11:59:17: "Aplicadas agora: ['20261029090000'] | faltando: nenhuma".

## 4. Depois da aplicação

| Verificação | Resultado |
|---|---|
| Migrations | 10 de 10; nenhuma pendente |
| Funções | 75, idênticas ao estado local com 10 migrations; nenhuma outra alterada |
| `fatura_elegivel_existente` | `SECURITY DEFINER`, `search_path` vazio; sem EXECUTE para `PUBLIC`, `anon`, `authenticated` e `service_role` |
| 4 funções substituídas | Retorno, `SECURITY DEFINER`, `search_path` e privilégios mantidos |
| Coluna | `lancamento_agregado.mes_fatura_original` (`date`, nula, sem default); 0 linhas preenchidas |
| Dados | As 61 tabelas com conteúdo idêntico ao de antes: a migration não alterou dados |
| Leitura funcional | `plano_recorrencia` executa; `dia_contratual(02/2027, 31)` = 28/02/2027 |

## 5. Validação com dados fictícios

**Procedimento:**
1. Marca da limpeza.
2. Seeds: perfis → contas → recorrência → receitas → MVP → cartões.
3. E2E real.
4. `scripts/supabase_fatura_integridade_real.py` (execução `c83bfbbc`).
5. Limpeza e removedores dos seeds, em ordem inversa.

**Escrita** só no "Perfil B" temporário (usuário B), em cartões criados pelo script, nos meses 2037 e 2038. O banco só:
- simulou o pagamento do Flask (`status_pagamento='Pago'`) em faturas criadas pelo teste;
- criou a recorrência de cartão fictícia (o novo aplicativo não cadastra recorrência de cartão);
- conferiu os resultados e sondou travas com `FOR UPDATE NOWAIT`, sem gravar nada.

**E2E real: 47/47.**

**Cenários (`scripts/supabase_fatura_integridade_real.py`): 14/14**, todos conferidos por consultas ao banco.

| # | Cenário | Resultado |
|---|---|---|
| 1 | Compra em fatura aberta | Incluída em 01/2037; fatura Pendente/ABERTA com executado 100,00; sem competência original |
| 2 | Compra em fatura paga | A prévia avisa o desvio; novo aplicativo e Flask real lançam em 03/2037; fatura 02 paga intacta (md5) |
| 3 | Competência original | `mes_fatura_original` = 02/2037 no novo aplicativo **e no Flask real**: o Flask passou a gravá-la porque a coluna agora existe no banco |
| 4 | Recorrência em fatura paga | A competência 06 (paga) é lançada em 07 com original 06, e a de 07 fica em 07; identidades GERADA; a nova geração não duplica; fatura 06 intacta |
| 5 | Parcelada atravessando fatura paga | 09, 11 (orig. 10) e 12 (orig. 11), 30,00 cada, **iguais** no novo aplicativo e no Flask real |
| 6 | Compra protegida | Editar e excluir em fatura paga: 400, compra intacta (md5). Exclusão parcial: 2 parcelas abertas excluídas e 1 paga preservada |
| 7 | Faturas pagas | As 5 continuam idênticas (md5) ao momento do pagamento |
| 8 | Acesso sem permissão | Anônimo: 401. Usuário A no Perfil B: 403. `fatura_elegivel_existente`, `travar_compra`, `gerar_mes_interno` e `plano_recorrencia` pela API: 403. Tabela direta: 406. Nada gravado |
| 9a | Simultaneidade | 3 compras simultâneas: 1 fatura, executado 30,00. Mesma chave 3 vezes: 1 compra |
| 9b | Compra durante um pagamento | Esperou a transação do pagamento e foi recusada (400); fatura com 10,00 |
| 9c | Ordem de travas do novo aplicativo | Com só a fatura presa, `criar_compra` e a exclusão (`travar_compra`) esperaram **segurando o cartão** (a sonda no cartão foi recusada); ambas concluídas |
| 9d | Flask e novo aplicativo em ordens opostas | O Flask, parado antes do commit, segurava o cartão. A exclusão do novo aplicativo esperou e concluiu (2 parcelas); o Flask também concluiu. Sem deadlock |
| 10 | Unicidade | 0 faturas e 0 parcelas duplicadas |
| 11 | Fora do Perfil B | Movimentos, contas bancárias, contas, compras e itens idênticos do início ao fim |

**Ordem de travas:** nos dois sistemas o cartão é travado antes das faturas (cenários 9c e 9d).

## 6. Limpeza

1. `supabase_despesas_real_limpeza.py remover`: só itens acima da marca e fora dos seeds. Foram 8 itens do Perfil B (6 do script e 2 do E2E), com as faturas e contas, compras, identidades, configurações e chaves deles, além dos movimentos e receitas acima da marca (seed de receitas e E2E). Antes da marca essas tabelas estavam vazias, exceto uma fonte de receita preexistente, que foi preservada.
2. Removedores dos seeds, em ordem inversa: cartões, MVP, receitas, recorrência (127 identidades, 132 contas e faturas, 3 execuções, gerador e histórico), contas e perfis.

**Resultado:**
- 0 registros com o marcador da execução; 0 cartões, compras e faturas dela; nenhum perfil ou vínculo temporário;
- **conteúdo das 61 tabelas de `public` e `financeiro` idêntico ao de antes da migration**;
- nenhum arquivo de estado em `data/`.

**Única diferença permanente:** a migration `20261029090000` (coluna e funções). As sequências avançaram, o que é normal.

## 7. Testes automatizados

- `tests/test_fatura_integridade.py` e `tests/test_alembic_mes_fatura_original.py`, depois da aplicação: **16 passed**.
- Na retomada do mesmo dia, sem mudança de código: 239 financeiros; suíte completa com 3 failed (as conhecidas) e 1471 passed; frontend 7/7; E2E local 47/47.

## 8. Pendências

- **Alembic `f1c4d8e2a7b9` no banco do Flask** (com `d81f5a2b9c3e` e `e3b7c9d1a2f4`): decisão do titular, com backup. O `gastos.db` não foi tocado.
- O Alembic do banco remoto continua em `c4f7a2d91b3e`. É o esperado: o Flask de staging nunca atualizou esse banco, e as revisões seguintes convivem com as migrations do Supabase.

## 9. Arquivos

- `scripts/supabase_fatura_integridade_real.py` (novo): testes reais.
- `docs/FIN_FATURA_INTEGRIDADE_REAL_1.md` (novo) e `docs/ROADMAP.md`.
