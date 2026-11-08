# FIN-DESPESAS-DEBITO-AUTOMATICO-01 — Edição de despesa recorrente em débito automático (P19)

**Situação (07/11/2026): publicado (`0de5820`, deploy `c8220af1`), sem migration.** Auditoria somente leitura aprovada (seção 6). A edição da Energia Elétrica fica com o usuário.

## 1. Causa comprovada

Fluxo: recorrência → geração da despesa → edição → validação bancária → gravação.

| Etapa | O que acontece |
|---|---|
| Geração | A despesa copia o débito automático e a conta bancária **que a recorrência tem naquele momento** (`plano_recorrencia`) |
| Vínculo posterior | Editar a recorrência (`editar_recorrencia`) grava a conta só no item; as despesas já geradas continuam sem conta |
| Edição da despesa | O formulário não tem seletor de conta. A tela reenviava o débito automático e a conta **da própria despesa** (`edicao.conta`), vazia |
| Validação | `ler_dados_despesa` recusa débito automático sem conta ativa do perfil: "Debito automatico exige uma conta bancaria ativa do perfil" |

A validação está certa. A falha é de mapeamento: `despesa_para_edicao` já devolvia a conta da recorrência (`item.conta_bancaria_id`), e a tela não a usava.

### Produção (somente leitura, 07/11/2026)

| Registro | Débito automático | Conta na recorrência | Conta nas despesas |
|---|---|---|---|
| Energia Elétrica (377) | Sim | 96 (Caixa), vinculada em 07/11/2026 | vazia nas 7 pendentes (10/2026 a 04/2027) e nas 5 pagas (05 a 09/2026) |
| Água (380) | Sim | 96 | 96 em todas |
| Futebol | Sim | **nenhuma** | vazia nas 7 pendentes |

- A Água funciona porque as despesas dela têm conta. O pagamento sempre pede a conta no modal e não depende da conta gravada na despesa.
- A diferença de valor (R$ 510,33 → R$ 581,20) não tem relação com o erro.
- Os meios de pagamento não divergem: Recorrências grava `debito_automatico` no item e a geração copia para a despesa.
- Contas bancárias 96 e 97 ativas e do Pessoal.
- Não há baixa automática do débito no novo aplicativo que dependa da conta gravada na despesa.

## 2. Correção

`contaDoDebito(edicao)` (`web/src/js/adaptador-comum.js`), usada pela edição em Despesas e em Lançamentos:

| Situação da despesa | Conta enviada |
|---|---|
| Débito automático com conta própria | A própria (nada é trocado em silêncio) |
| Débito automático sem conta própria | A da recorrência |
| Sem débito automático | A própria (o banco descarta) |

- **A validação do banco não muda:** conta ativa e do perfil continua obrigatória. Sem conta em lugar nenhum (caso do Futebol), conta inativa ou de outro perfil, a edição é recusada, agora com uma mensagem que diz onde vincular: "Vincule a conta na recorrência (tela Recorrências) ou reative a conta bancária".
- **O que muda ao editar:** só a despesa editada: valor e conta. O valor padrão da recorrência, a competência, as outras despesas, as pagas e a quantidade de despesas ficam como estavam. Nenhuma ocorrência é recriada.
- As outras despesas pendentes sem conta recebem a conta da recorrência quando forem editadas. Propagar a conta para todas ao vincular exigiria migration e alteraria dados; não foi feito.

## 3. Testes

| Bateria | Resultado |
|---|---|
| Banco (Despesas), com o estado real reproduzido | 56/56: causa, vínculo, edição de R$ 510,33 para R$ 581,20, recorrência, outras despesas e paga preservadas; conta inativa, de outro perfil e ausente recusadas |
| Unitários do frontend | 89/89 (5 novos) |
| E2E completo, sem novas tentativas | 129/129 |
| Contraprova (E2E sem a correção) | O teste novo falha |

- **E2E:** usuário E fictício, com perfil próprio, conta bancária e a recorrência em débito sem conta, mais despesas geradas antes do vínculo (uma paga). Perfil próprio porque abrir Despesas gera as lacunas de todas as recorrências do perfil: no Perfil B, o cenário mudava o que os specs de pendência e de recorrência esperam.
- **Fluxo testado:** a edição é recusada com a mensagem nova; a conta é vinculada na recorrência; a edição grava R$ 581,20 com a conta da recorrência; a recorrência fica em R$ 510,33; o mês seguinte e o pago ficam iguais.

## 4. Arquivos

- `web/src/js/adaptador-comum.js`: `contaDoDebito` e a mensagem da recusa.
- `web/src/js/despesas-adaptador.js`, `web/src/js/lancamentos-adaptador.js`: edição.
- `tests/test_supabase_despesas.py`: 4 casos novos.
- `web/tests/unit/despesas-debito-automatico.test.mjs`
- `tests/supabase_local.py`, `web/tests/e2e/run_e2e.py`: usuário E e o cenário.
- `web/tests/e2e/despesas.spec.mjs`

## 5. Publicação

Deploy do frontend (sem migration). Depois dele, editar a Energia Elétrica de 11/2026 grava R$ 581,20 com a conta Caixa. O Futebol continua pedindo a conta na recorrência.

## 6. Publicação e auditoria (07/11/2026)

- **Commits:** `aafc752` (documentação do CREDITOS-02), `476cb7a` e `0de5820` (os da P19, reaplicados sobre ele; antes `7d77986` e `c867960`, mesmo conteúdo). Push `f94b207..0de5820`, em avanço direto.
- **Antes:** unitários 89/89, banco de Despesas 56/56, E2E de Despesas, Lançamentos e Contas Bancárias 11/11.
- **Deploy `c8220af1`:** 164 arquivos servidos iguais ao build; a correção está no JavaScript publicado; 17 páginas protegidas, sem erros de JavaScript ou de CSP.
- **Dados:** 86 tabelas iguais antes e depois; as 36 despesas e as 3 recorrências de Energia Elétrica, Água e Futebol sem nenhuma alteração (as 7 pendentes da Energia continuam sem conta até serem editadas; as 5 pagas intactas); Clube dos Oficiais e Apple One iguais. Sem migration (57 no total).
- **Atividade do app antes da publicação:** duas receitas de 11/2026 lançadas na conta 96 (saldo de R$ 68.015,34 para R$ 90.940,32, igual ao recalculado) e a Água de 11/2026 editada de R$ 300,00 para R$ 279,92.

