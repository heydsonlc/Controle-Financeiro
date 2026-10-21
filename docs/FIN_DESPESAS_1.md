# FIN-DESPESAS-1 — Cadastro e edição de despesas

**Data:** 2026-10-21. Implementado e testado **localmente**: cluster PostgreSQL descartável, Flask real para comparação, PostgREST e Playwright, com dados fictícios.

**Não foi feito:**
- aplicar migration no remoto;
- publicar;
- alterar dados reais.

**Autorização:** SCRIPT-CONTRATO V5 — FIN-DESPESAS-1. O push de `18b201c` foi feito após revisão.

## 1. Critério de conclusão

**Cadastrar despesa → visualizar no mês correto → editar ou inativar quando permitido → excluir com segurança, sem alterar o histórico financeiro.**

Atendido, e coberto por testes de banco e de tela (§5).

## 2. Diagnóstico (Flask × novo aplicativo)

| Tema | Flask (conferido no código) | Novo aplicativo |
|---|---|---|
| Item × conta | `item_despesa` é o cadastro (tipos `Simples`, `Agregador`, `Consorcio`, `Financiamento`; `origem_tipo` para veículos, mobilidade e assinaturas). `conta` é a ocorrência do mês (competência em `mes_referencia`) | **Mesmo modelo**, sem tabela paralela. Só `Simples` sem origem é administrado aqui |
| Avulsa | `POST /api/despesas`: item + 1 conta. Competência = mês do vencimento (o `mes_competencia` enviado só vai para o item). **Aceita criar já "paga", sem movimento bancário** | Item + 1 conta **sempre pendente**. **Competência explícita**: o padrão é o mês do vencimento, igual ao Flask, e pode ficar a até 12 meses dele |
| Recorrente | `POST /api/recorrencias`: item; gera o 1º mês na hora | Só o item; as contas vêm do **FIN-RECORRENCIA-1** ("Gerar contas", explícito, sem segundo gerador) |
| Parcelada | Só nos consórcios e financiamentos (contas `n/N`) | Bloqueada: fica com os módulos próprios |
| Editar conta | `PUT /api/despesas/<id>` muda descrição, valor, vencimento e observações **mesmo de conta paga** (só impede marcar como paga) | **Bloqueia** conta paga, com movimento, fatura, financiamento, consórcio ou origem automática |
| Excluir conta | Bloqueia paga ou com movimento; o **item fica órfão** | Mesmo bloqueio, e mais: **conta recorrente vira competência dispensada** (não volta); **item avulso** sem outras referências é removido |
| Editar recorrência | `PUT /api/recorrencias`: muda o item; as contas existentes ficam iguais | Igual. Dia e frequência só mudam com o perfil no novo gerador (T1), porque o Flask identifica a conta pela data e duplicaria |
| Inativar | `DELETE /api/recorrencias/<id>` → `ativo=false`; as contas existentes ficam | Igual |
| Conta bancária | Só com débito automático (obrigatória, ativa, do perfil) | Igual. Também na avulsa com débito (extensão) |
| Categoria | Global (`public.categoria`) | Igual: só ativas |
| Cartão | Recorrência no cartão vira compra | Recusado: fica para o FIN-CARTOES-1 |

## 3. Implementação

### 3.1 Migration `supabase/migrations/20261026090000_financeiro_despesas.sql` (só local)

**Funções públicas (EXECUTE só para `authenticated`; nenhuma para `anon`):**

| Função | O que faz |
|---|---|
| `categorias_de_despesa()` | Categorias globais ativas, para quem tem algum perfil |
| `despesa_para_edicao(perfil, conta)` | Dados da conta e do item, mais as permissões calculadas no banco: `pode_editar`, `pode_mudar_vencimento`, `pode_excluir`, `pode_editar_recorrencia`, `pode_mudar_calendario`, `pode_inativar_recorrencia`, o `bloqueio` (motivo) e a `versao` |
| `criar_despesa(perfil, dados, chave)` | Avulsa (item + conta pendente) ou recorrente (só o item). **Idempotente pela chave** (uuid gerado pelo navegador): repetir devolve o mesmo resultado |
| `editar_despesa(perfil, conta, versao, dados)` | Avulsa: tudo (inclusive competência e categoria; o item acompanha). Recorrente: valor, nome, observações e débito; vencimento só no novo gerador; competência e categoria não |
| `excluir_despesa(perfil, conta, versao)` | Recorrente: registra a competência como **DISPENSADA** e exclui (só no novo gerador). Avulsa: exclui a conta e o item sem outras referências |
| `editar_recorrencia(perfil, item, versao, dados)` | Vale para as próximas gerações; as contas existentes não mudam |
| `inativar_recorrencia(perfil, item, versao)` | `ativo=false`; o histórico fica |

**Funções internas, sem EXECUTE para o navegador:** `pertence_ao_perfil`, `bloqueio_da_despesa`, `ler_dados_despesa` (todas as validações), `travar_despesa`, `travar_recorrencia`, `versao_despesa` e `versao_recorrencia`.

**Proteções:**
- **Gestão explícita** (`pode_gerir`): `LEITOR` só lê.
- **Perfil:** a conta e o item precisam pertencer ao perfil informado (NULL → Pessoal). Não adianta trocar o perfil no navegador.
- **Linhas travadas (`FOR UPDATE`)** e **versão (md5)** conferida antes de alterar: uma edição concorrente ou feita sobre dados velhos é recusada.
- **Trava de geração** `(20261023, perfil)` ao excluir, editar ou inativar recorrência: nada muda no meio de uma geração.
- **Nenhum pagamento, saldo ou movimento** é tocado. As faturas não entram (a fatura única continua garantida).
- **Tabela nova** `financeiro.operacao_despesa` (idempotência): RLS forçada e sem privilégios para o navegador.

### 3.2 Tela (`web/src/contas.html`, `js/contas.js`, `js/despesas.js` novo, `css/app.css`)

A tela inicial continua sendo **Contas do mês**, sem painéis, gráficos ou navegação novos.

- **"Nova despesa":** só aparece para quem gerencia o perfil. Abre um formulário curto com:
  - tipo (avulsa, recorrente mensal ou anual);
  - nome, valor (aceita `350,40`) e categoria;
  - vencimento e competência (só na avulsa; acompanha o vencimento até ser alterada);
  - débito automático e conta bancária (só ativas do perfil);
  - observações.
- **Ao abrir uma despesa:** o banco informa o que é permitido, e só esses botões aparecem: **Editar**, **Excluir**, **Editar recorrência**, **Inativar recorrência**.
  - Exclusão e inativação pedem confirmação, com o efeito explicado (por exemplo, "a competência fica dispensada e não volta a ser gerada").
  - Uma conta bloqueada mostra só o motivo (por exemplo, "Despesa paga: correção só por estorno.").
  - Fatura não tem ações.
- **Depois de cada operação:** mensagem curta e o mês recarregado.
- **Build:** a lista de RPCs separa leitura de escrita; as 5 RPCs de escrita de despesas só são permitidas em `despesas.js`.

## 4. Diferenças intencionais em relação ao Flask

1. **Conta paga não é editada** (o Flask permite mudar o valor de conta paga). Teste: `test_correcao_intencional_flask_altera_conta_paga_e_o_novo_bloqueia`.
2. **Despesa nunca nasce paga.** Pagamento só no FIN-PAGAMENTOS-1, com movimento.
3. **Competência explícita na avulsa** (o Flask sempre usa o mês do vencimento, que segue sendo o padrão).
4. **Recorrência não gera o 1º mês ao cadastrar.** A geração é a do FIN-RECORRENCIA-1 (ação explícita, decisão D1).
5. **Excluir conta recorrente dispensa a competência** (no Flask ela volta na próxima navegação).
6. **Item avulso excluído junto com a conta** (o Flask o deixa órfão).
7. **Calendário de recorrência e exclusão de conta recorrente** só com o perfil no novo gerador. Com o gerador do Flask, o próprio Flask duplicaria ou recriaria pela data.
8. **Débito automático também na avulsa** (o Flask só oferece na recorrência).

Fora isso, **equivalência comprovada com o Flask real**:
- cadastro de avulsa e de recorrente: todos os campos de item e conta iguais, exceto ids e data de criação;
- edição e exclusão de conta pendente: mesmos campos resultantes.

## 5. Testes

**Conjuntos:**

| Conjunto | Resultado |
|---|---|
| `tests/test_supabase_despesas.py` (novo) | **52/52** |
| Suíte completa (inclui FIN-RECORRENCIA-1, T1 e FIN-FATURA-UNICA-1) | 1281 passaram; só as 5 falhas antigas (§7) |
| E2E local (390 px) | **36/36**: 5 novos em `despesas.spec.mjs`, mais o fluxo de recorrência pela tela em `recorrencia.spec.mjs`; `contas.spec.mjs` ajustado para o botão "Nova despesa" |
| Testes unitários do `web/` | 7/7 |

**Cobertura dos testes obrigatórios do contrato:**

| # | Teste obrigatório | Cobertura |
|---|---|---|
| 1 | Despesa avulsa | Criação com todos os campos, no mês da competência; padrão igual ao Flask |
| 2 | Recorrência mensal e anual | Só o item; a prévia oferece as competências (com dia contratual) e a geração cria |
| 3 | Edição antes da execução | Conta e item atualizados; nova versão |
| 4 | Bloqueio após pagamento | Paga **e** com movimento: edição e exclusão recusadas, md5 da conta e das tabelas financeiras intacto; consórcio e financiamento bloqueados; fatura fora |
| 5 | Exclusão segura | Avulsa (conta + item, nada mais tocado); recorrente vira dispensada e não volta em gerações seguintes |
| 6 | Inativação | Para a geração e mantém o histórico (md5) |
| 7 | Competência ≠ vencimento | Aparece no mês da competência, não no do vencimento |
| 8 | Troca de mês | Mudar a competência move a conta de mês |
| 9 | Categoria e conta | Categoria inválida ou inativa recusada; débito exige conta ativa do próprio perfil (aceita o legado NULL do Pessoal; recusa Empresa, Perfil B e inativa); sem débito, a conta bancária não é gravada |
| 10, 11 | Perfil autorizado e somente leitura | `LEITOR` vê, mas não cria, edita, exclui nem inativa |
| 12 | Outro usuário e anônimo | Outro usuário e perfil trocado: 42501. Anônimo: sem permissão em todas as funções. Internas e tabelas: negadas ao navegador. REST: 403 |
| 13 | Concorrência e repetição | Mesma chave repetida e 3 criações simultâneas com a mesma chave criam **1** despesa. Duas edições simultâneas sobre a mesma versão: **só uma vale**. Edição esperando um pagamento em andamento (linha travada) é **bloqueada** depois dele |
| 14 | Movimentos bancários | Saldos, movimentos, compras de cartão e faturas idênticos após criar, editar e excluir |
| 15 | FIN-RECORRENCIA-1 | Geração só pelo mecanismo existente; dispensa ao excluir; calendário e exclusão bloqueados com o gerador do Flask |
| 16 | FIN-FATURA-UNICA-1 | Faturas não são tratadas como despesa; nada cria fatura; cartão recusado |
| 17 | Equivalência com o Flask | Cadastro, edição e exclusão iguais nos campos; diferenças da §4 verificadas |

## 6. Pendências e observações

- **Pagamento concorrente no Flask:** a edição do novo aplicativo trava a linha e recusa se a conta já estiver paga. Mas a rota de pagamento do Flask lê a conta sem trava. Uma edição gravada exatamente entre a leitura e a gravação do pagamento do Flask faria o pagamento usar o valor anterior. O tratamento é no **FIN-PAGAMENTOS-1** (pagamento com trava e versão).
- **Recorrência sem nenhuma conta** só é editada ou inativada a partir de uma conta dela. Uma lista de recorrências não entrou, para não criar navegação nova.
- **A categoria é do item:** editar a categoria de uma recorrência muda a exibição também das contas anteriores. É o mesmo comportamento do Flask, que a lê do item.
- **Migration a aplicar no remoto, com autorização própria:** `20261026090000`.

## 7. Suíte completa



**1281 passaram, 19 pulados, 5 falhas** — exatamente as 5 que já falhavam desde `0e04407`:

- `test_categorias_sistemicas_mobilidade::test_projecoes_veiculo_usam_categorias_sistemicas_granulares`
- `test_ocr_tools::test_status_sem_ferramentas_retorna_estrutura_valida`
- `test_ocr_tools::test_poppler_ausente_retorna_aviso`
- `test_receitas_ux::test_cards_resumo_calculam_previsto_realizado_diferenca_confiabilidade`
- `test_veiculos_mobilidade_2b::test_suprimir_despesas_previstas_futuras`

Nenhuma regressão (inclui FIN-RECORRENCIA-1, T1 e FIN-FATURA-UNICA-1).
