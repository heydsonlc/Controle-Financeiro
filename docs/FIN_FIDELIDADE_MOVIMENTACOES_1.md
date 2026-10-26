# FIN-FIDELIDADE-MOVIMENTACOES-1 (MVP 2) — Contas Bancárias e Lançamentos

**Situação (25/10/2026):** Contas Bancárias e Lançamentos implementadas e testadas localmente.
- Sem commit, sem migration persistente e sem publicação.
- A migration `20261109090000` é local e aguarda autorização.

## 1. O que foi migrado

A tela original do Flask é usada sem alteração: `frontend/templates/contas_bancarias.html`, `frontend/static/js/contas_bancarias.js` e `frontend/static/css/contas_bancarias.css`.
- Ponte CSP e ponte de API, como em Cartões.
- `web/src/js/contas-bancarias-adaptador.js` responde as 12 rotas `/api/contas` no formato do Flask, com as funções da migration `20261109090000_financeiro_contas_bancarias.sql`.

| Rota do Flask | Função no Supabase | Regra |
|---|---|---|
| `GET /api/contas?status=` | `contas_bancarias_tela` | Ativas por padrão; contas legadas sem perfil aparecem no Pessoal |
| `GET /api/contas/<id>` | `conta_bancaria_tela` | Conta do perfil |
| `POST /api/contas` | `criar_conta_bancaria` | Validação como no Flask; o reenvio com a mesma chave não duplica |
| `PUT /api/contas/<id>`, `DELETE`, `PUT .../ativar` | `editar_conta_bancaria` | Só os campos enviados; versão do cadastro; saldo inicial só sem movimentos |
| `GET /api/contas/<id>/movimentos` | `extrato_conta_bancaria` | Mais recentes primeiro; saldo após cada movimento; período e limite como no Flask |
| `POST /api/contas/<id>/ajuste-saldo` | `ajustar_saldo_conta` | Movimento AJUSTE (ajustável) pela diferença; diferença zero não grava nada |
| `PUT` / `DELETE /api/contas/<id>/movimentos/<mov>` | `editar_ajuste_conta`, `excluir_ajuste_conta` | Só AJUSTE |
| `POST /api/contas/transferir` | `transferir_entre_contas` | Débito e crédito com o mesmo `transferencia_id`; contas travadas em ordem de id |
| `GET /api/contas/<id>/conferir-saldo` | `conferir_saldo_conta` | Somente leitura |

**Saldo:** `saldo_inicial + créditos − débitos` (`saldo_da_conta`).
- `saldo_atual` é o mesmo cache do Flask, recalculado a cada movimento.
- Transferência tem origem TRANSFERENCIA: não é receita nem despesa, e o total do perfil não muda (teste).
- O histórico fica: inativar ou reativar não toca em movimentos.
- Só o AJUSTE se edita ou exclui, como no Flask.

## 2. Diferenças em relação ao Flask (correções classificadas)

| Item | Flask | Novo aplicativo | Classificação |
|---|---|---|---|
| Movimento (ajuste, transferência) em perfil ainda no Flask | Grava | Recusa: "As movimentações deste perfil ainda são feitas pelo sistema atual (Flask)" | Escritor único (D5), mesma regra dos pagamentos |
| Reenvio da mesma operação | Duplica | A chave devolve o resultado anterior | Correção |
| Cadastro editado por outra pessoa enquanto o formulário estava aberto | Sobrescreve | Recusa: "registro alterado por outra operação" | Correção |
| Excluir um ajuste que outro movimento referencia | Exclui | Recusa (movimento vinculado) | Correção |
| Valores com mais de 2 casas, cor fora de `#RRGGBB`, textos acima do tamanho da coluna | Grava o que vier, ou falha no banco | Mensagem clara, nada gravado | Correção |
| Data vazia do movimento | Data UTC | Data de Brasília | Correção |

Mantidos como no Flask:
- ajustar e editar conta inativa;
- excluir AJUSTE;
- o formulário sempre envia o saldo inicial, e o mesmo valor é aceito com movimentos.

## 3. P1 de Despesas (movimentos do mês e saldos bancários)

**Resolvido pela tela de Contas Bancárias**, como no Flask: a tela de Despesas do Flask não lista movimentos; o saldo e o extrato ficam aqui.
- Os movimentos gravados aqui (AJUSTE e TRANSFERENCIA) entram em `movimentos_do_mes` e nos saldos usados nos pagamentos (teste `test_movimentos_do_mes_listam_ajuste_e_transferencia`).
- Nenhum saldo histórico foi reescrito: as funções novas só gravam por ação do usuário, e nada foi aplicado ao Supabase.

## 4. Testes

- **Banco, cluster descartável** (`tests/test_supabase_contas_bancarias.py`): **16 passaram**.
  - privilégios: tela só para `authenticated`; internas fechadas; SECURITY DEFINER com `search_path` vazio;
  - lista e formato do Flask; isolamento entre titulares; leitor;
  - criação idempotente e validada; edição parcial com versão;
  - saldo inicial só sem movimentos; inativar e reativar com histórico preservado;
  - ajuste pela diferença e pelo valor; escritor único;
  - só AJUSTE editável ou excluível; ajuste estornado protegido;
  - transferência pareada, sem receita nem despesa, idempotente;
  - recusas sem gravar; 10 transferências simultâneas em sentidos opostos sem impasse;
  - extrato (ordem, saldo após, período, limite); conferência só leitura;
  - P1 (`movimentos_do_mes`).
- **Unitários web:** 30 passaram, com auditoria do build: as 4 funções de leitura e as 6 de escrita liberadas só para `contas-bancarias-adaptador.js`.
- **E2E local** (`web/tests/e2e/contas_bancarias_tela.spec.mjs`): **2 passaram**, sem erro de CSP, de JS nem chamada `/api/`.
  - Fluxo com o usuário B: criar duas contas, transferir, recusa do saldo inicial, ajuste, extrato, editar e excluir ajuste, conferência, inativar e reativar.
  - Perfil ainda no Flask: movimento recusado sem gravar.
  - Leitor: sem ações de escrita.
- **`moldura.spec.mjs`:** 8 passaram (Contas Bancárias saiu de "Em migração").

## 5. Arquivos

**Novos:**
- `supabase/migrations/20261109090000_financeiro_contas_bancarias.sql`
- `tests/test_supabase_contas_bancarias.py`
- `web/src/paginas/contas-bancarias.html`
- `web/src/js/contas-bancarias-adaptador.js`
- `web/src/css/contas-bancarias-adaptacoes.css`
- `web/tests/e2e/contas_bancarias_tela.spec.mjs`
- este documento

**Alterados:**
- `web/scripts/build.mjs`: `contas_bancarias.css` e `contas_bancarias.js` do Flask.
- `web/src/moldura/em-migracao.json`: Contas Bancárias removida.
- `web/tests/unit/build.test.mjs`: funções liberadas e página migrada.
- `web/tests/e2e/moldura.spec.mjs`.

## 6. Lançamentos

A tela original do Flask é usada sem alteração: `lancamentos.html`, `lancamentos.js` e `lancamentos.css`. O adaptador é `web/src/js/lancamentos-adaptador.js`.

A tela junta três listas de todos os meses (o filtro inicial é o mês atual, como no Flask):
- compras dos cartões;
- despesas diretas;
- receitas pontuais.

| Rota do Flask | No novo aplicativo |
|---|---|
| `GET /api/cartoes/<id>/lancamentos` | `compras_do_cartao_tela` (nova, só leitura): todas as compras, da mais recente à mais antiga |
| `GET /api/despesas/` (sem mês) | `despesas_diretas_tela` (nova, só leitura): contas fora de fatura no formato de `listar_despesas` |
| `GET /api/receitas/realizadas`, `/orcamento?ano=`, `/itens` | `receitas_lancamentos_tela` (nova, só leitura) |
| `GET /api/cartoes`, `/categorias`, `/contas`, `/cartoes/<id>/categorias-limite`, `/categorias-cartao/resolver`, `/cartoes/<id>/competencia-sugerida` | Funções de leitura existentes |
| `POST /api/cartoes/<id>/lancamentos` | `criar_compra`. A fatura consolidada recebe a mesma pergunta do Flask (409 `CONFIRMAR_FATURA_CONSOLIDADA`, totais da prévia do banco) |
| `DELETE /api/cartoes/lancamentos/<id>` | `excluir_compra`: as parcelas em fatura aberta saem, com a confirmação das quantidades (regra de Cartões) |
| `POST` / `PUT` / `DELETE /api/despesas/...` | `criar_despesa`, `editar_despesa`, `excluir_despesa` (regras e bloqueios de Despesas) |
| `POST /api/receitas/realizadas[/pontual]`, `DELETE .../realizadas/<id>` | **Recusados** (ver abaixo) |
| `/api/ir/...` ("A partir de documento") | Em migração (MVP 5) |

**Correções em relação ao Flask (classificadas):**

| Item | Flask | Novo aplicativo |
|---|---|---|
| Abertura da tela | `carregarLancamentos()` roda antes de os cartões chegarem: **as compras de cartão não aparecem** até salvar algo | Corrigido sem tocar no JS do Flask: `web/src/js/lancamentos-adaptacoes.js` faz a lista esperar a carga de cartões |
| Editar compra de cartão | O salvar sempre faz POST: **cria outra compra** (duplica) | Recusado com orientação: corrigir na tela de Cartões. Nada é gravado |
| Despesa direta marcada "paga" na criação | Fica paga sem conta bancária e sem movimento | Recusada, como em Despesas: o pagamento escolhe a conta e registra o movimento |
| Confirmar recebimento e entrada pontual | Gravam recebimento sem conta bancária e sem movimento | Recusados: o recebimento fica em Receitas, com conta e movimento. A entrada pontual sem previsão já tinha ficado no Flask no FIN-MOVIMENTACOES-1 |
| Excluir recebimento | Apaga | Recusado: o estorno fica em Receitas |
| Mensagem de erro nas despesas diretas e nas exclusões | Genérica ("Erro ao salvar despesa direta") | O motivo aparece antes, no mesmo aviso da tela |

**Ponte CSP:** o Flask chama `editarLancamento({...})` com o lançamento inteiro em JSON no `onclick`.
- A ponte (`ponte-csp.js`) passou a aceitar objeto ou lista JSON como argumento.
- `JSON.parse` lê só dados, nunca código; a separação dos argumentos respeita `{}`, `[]`, aspas e escape.
- Testada com vírgulas, aspas, apóstrofo, barra invertida e objetos aninhados; as demais telas continuam passando no E2E.

**Testes:**
- banco: `tests/test_supabase_lancamentos_tela.py`, **4 passaram** (privilégios, formatos, ordem, filtros de mês e ano, isolamento, só leitura);
- E2E: `web/tests/e2e/lancamentos_tela.spec.mjs`, **2 passaram**:
  - com o usuário B: despesa direta, recusa de "paga", compra parcelada em 3 vezes, recusa da edição de compra, exclusão da compra parcelada (com a confirmação) e da despesa;
  - leitor sem ações.
- `perfis.spec.mjs` passou a ignorar, pelo nome, as duas contas que `contas_bancarias_tela.spec` cria (e inativa) no Perfil B.

**Arquivos:**
- novos: `web/src/paginas/lancamentos.html`, `web/src/js/lancamentos-adaptador.js`, `web/src/js/lancamentos-adaptacoes.js`, `web/src/css/lancamentos-adaptacoes.css`, `tests/test_supabase_lancamentos_tela.py`, `web/tests/e2e/lancamentos_tela.spec.mjs`;
- alterados: a migration `20261109090000` (seção 6), `build.mjs`, `em-migracao.json`, `build.test.mjs`, `moldura.spec.mjs`, `perfis.spec.mjs`, `ponte-csp.js`.

## 7. Pendências e autorizações (MVP 2)

1. Commit do MVP 2.
2. Aplicação da migration `20261109090000` no Supabase de teste. Ela só cria funções; nenhuma tabela ou dado muda.
   - A ferramenta aplica as pendentes juntas: `20261106`, `20261107` e `20261108` (MVP 1) ainda aguardam.
3. Publicação na prévia, depois da validação real com perfil temporário.
4. Decisão do titular: confirmar as recusas do § 6 (recebimento sem conta, "paga" sem movimento, edição de compra fora de Cartões).
