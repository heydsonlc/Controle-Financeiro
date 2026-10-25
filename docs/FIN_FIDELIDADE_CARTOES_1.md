# FIN-FIDELIDADE-CARTOES-1 — Cartões e Importar Cartão do Flask sobre o Supabase

**Situação:** concluído tecnicamente (25/10/2026). A homologação funcional depende da avaliação do titular na prévia.
- Commit `ef6c0d8`.
- As duas migrations aplicadas **só no Supabase de teste**.
- Validado com perfil temporário e publicado na prévia protegida (§ 9).
- Sem push e sem produção.
- Mesmo padrão de Despesas e Recorrências: HTML, CSS e JS do Flask copiados no build, ponte CSP, ponte `/api/` e um adaptador por tela sobre funções do Supabase.

## 1. Cartões

**Tela:** `frontend/templates/cartoes.html` (barra e conteúdo) + `cartoes.js` + `cartoes.css` do Flask, sem alteração. Adaptador: `web/src/js/cartoes-adaptador.js`.

| Funcionalidade do Flask | Situação |
|---|---|
| Lista de cartões, pesquisa, status, resumo (ativos, categorias vinculadas, limite total) | Funcionando |
| Novo cartão e edição: nome, banco/emissor, dias de fechamento e vencimento, regra do dia do fechamento, confirmação, limite, observações, "possui código" | Funcionando. Mudar um dia desfaz a confirmação (tela e banco) |
| Número, validade e CVV | **Não guardados** (decisão de segurança anterior): campos desativados, nada é digitado nem enviado; "Ver CVV" não existe |
| Vincular Categoria do Cartão com limite mensal, editar, desativar e reativar | Funcionando (único por cartão + categoria; reativar exige a categoria ativa) |
| Limites com gasto do mês, disponível e percentual | Funcionando (só os vínculos do perfil, como o Flask) |
| Fatura por Categoria do Cartão no mês: total, limite, disponível, consumo; grupos "sem limite" e "sem categoria" | Funcionando (mesmo cálculo e status Normal / Atenção / Estourado) |
| Lançamentos da fatura com filtro por categoria | Funcionando |
| Editar um lançamento | Funcionando, só este lançamento (descrição, valor, data na compra à vista, categoria) |
| Gerenciar parcelamento: consultar, alterar parcelas futuras, cancelar parcelas futuras | Funcionando, só parcelas futuras em fatura aberta |
| Excluir lançamento | Funcionando (ver diferenças) |

**Acréscimos (melhorias do novo aplicativo mantidas):**
- **Nova compra:** botão e modal com o formulário do novo aplicativo: prévia das parcelas, fatura sugerida pelo fechamento, confirmação de fatura consolidada. No Flask a compra é cadastrada em Lançamentos, uma tela mista com Receitas e IR que continua em migração.
- **Inativar cartão** no modal de edição: a rota `DELETE /api/cartoes/<id>` do Flask existe, mas a tela dele não tinha o botão. Nunca há exclusão física.

**Pagamento e estorno da fatura:** em Despesas, como no Flask (FIN-FIDELIDADE-DESPESAS-1). A lista de faturas e o pagamento que a tela de Cartões anterior do novo aplicativo tinha saíram dela; a mesma função continua em Despesas.

## 2. Importar Cartão

**Tela:** `frontend/templates/importar_cartao.html` + `importar_cartao.js` (3698 linhas) + `importar_cartao.css`, sem alteração. Adaptador: `web/src/js/importar-cartao-adaptador.js`.

**Leitura do arquivo:** no navegador, em `web/src/js/importacao-csv.js`. O arquivo não sai do aparelho; o banco recebe só as linhas lidas. As regras do Flask foram portadas:
- delimitador `;`, `,` ou tabulação;
- codificação UTF-8 ou Windows-1252;
- perfis Nubank (`date`/`title`/`amount`) e Caixa (`data`/`descritivo`/crédito/débito);
- outro cabeçalho vai para o mapeamento manual da tela original;
- parcela na descrição ("PARC 03/10", "2/5", "1 DE 12");
- valores brasileiros;
- datas conferidas, sem deixar dia e mês para o banco interpretar.

**Análise** (`analisar_importacao_cartao`, só leitura). É o pipeline do `ImportacaoCartaoUnificadoService`:
- validação;
- sugestão de categoria por palavra-chave, depois pelo histórico, por fim o "fallback" do cartão;
- Categoria do Cartão;
- duplicidade no lote e no banco (mesma chave de negócio);
- **conciliação com compras já lançadas** (manual, por recorrência ou importação com outra descrição): mesmo cartão, competência, valor e parcela, data a até 5 dias. A linha vem retirada da efetivação como "Já existe na fatura", com o lançamento encontrado;
- compra recorrente do cartão reconhecida pelo nome (`reconhecer_despesa_fixa` do Flask).

**Gravação** (`importar_fatura_cartao`): só depois da confirmação do usuário na tela, e com estas garantias:
- **tudo ou nada**;
- idempotência por chave;
- travas cartão → faturas, com a análise refeita sob a trava;
- fatura paga: a compra vai para a próxima fatura, com a competência original registrada;
- fatura consolidada: a importação inteira é recusada;
- rastreio no lançamento: `is_importado`, `origem_importacao`, `descricao_original`, `descricao_original_normalizada`; o resumo fica em `operacao_cartao`.

**Crédito na fatura** (verificado a pedido do titular):
- **No Flask e no banco:** crédito na fatura não tem representação como lançamento. O Flask ignora toda linha de crédito, e o leitor de PDF descarta até "OBRIGADO PELO PAGAMENTO". O pagamento da fatura existe só em `financeiro.pagamento_fatura`, registrado em Despesas.
- **Aqui:** nenhum crédito entra como compra nem reduz a fatura. A análise classifica e explica cada tipo:
  - pagamento da fatura: registrado em Despesas, como pagamento;
  - estorno de compra: a compra original continua; se deve sair, corrige-se pela própria compra;
  - crédito ou ajuste da administradora.
- **Valor negativo é sempre crédito:** o sinal nunca é descartado, mesmo que a linha chegue marcada como débito (risco encontrado no mapeamento manual e corrigido no banco e no adaptador).
- **Testes:** cobrem os quatro tipos, a linha forjada como débito e a fatura com crédito no meio, cujo total não muda.

**Parcelamento a partir da linha** (modal "Criar parcelamento"): a parcela do arquivo e as futuras, como o Flask.

| Funcionalidade | Situação |
|---|---|
| CSV Nubank, Caixa e manual; prévia; confronto; retirados; confirmação; resultado | Funcionando |
| Reimportar o mesmo arquivo | Nada novo; nada gravado (verificado em E2E) |
| Créditos e estornos | Identificados e não importados como despesa (ver diferenças) |
| PDF e XLSX | **Pendente** (I1) |
| Vincular a linha a uma recorrência escolhida (`/recorrencia`) | **Pendente** (I2). A recorrência com o mesmo nome já é reconhecida |

## 3. Integrações

**Cartões → Despesas** (verificado em E2E):
- a fatura em Despesas tem o valor das compras;
- paga, os lançamentos dela ficam protegidos ("Fatura paga: para corrigir, estorne o pagamento da fatura");
- estornada, voltam a ser editáveis;
- excluir a compra zera a fatura, sem dupla contagem.

**Cartões → Recorrências (R2):**
- **Parcial:** a importação reconhece a compra recorrente do cartão e grava com a identidade da competência (`compra_id` do gerador). O gerador a vê como existente e não a lança de novo (teste de banco).
- **Continua pendente:** o cadastro e a edição de recorrência no cartão (tela Recorrências).

**Importação → Cartões:**
- cartão e fatura da competência escolhida;
- fatura paga desvia; fatura consolidada recusa;
- limites e Categoria do Cartão resolvidos como na compra manual.

**Cartões → Contas Bancárias:** só pelo pagamento da fatura (Despesas), sem mudança neste contrato.

## 4. Diferenças em relação ao Flask

Defeitos do Flask não reproduzidos:

1. Editar um lançamento não troca o número nem o total de parcelas: no Flask isso desmonta o parcelamento.
2. Excluir uma parcela exclui as parcelas abertas da compra (regra do FIN-CARTOES-1, nada órfão). Isso vem depois de uma segunda confirmação com as quantidades; as parcelas em fatura paga ou fechada ficam. Para tirar só as próximas, há "Gerenciar parcelamento".
3. **Layout em 1366 px:**
   - **Defeito:** as três colunas não cabem ao lado do menu, e o painel "Como funciona" encobria as ações dos lançamentos (captura do Flask em `scratchpad/capturas_cartoes`).
   - **Correção** em `cartoes-adaptacoes.css`: o mesmo arranjo que o original usa abaixo de 1320 px, com o corte deslocado pela largura do menu; as tabelas rolam dentro do cartão.
4. A confirmação de "Cancelar parcelas futuras" tinha os acentos corrompidos no arquivo original; o texto foi corrigido.
5. **Importação:**
   - valor negativo no perfil de coluna única (pagamento ou estorno da Nubank) é crédito; o Flask importava o valor absoluto como despesa (na captura, "Pagamento recebido" virou despesa de R$ 500,00);
   - nenhuma gravação parcial (o Flask gravava as boas e listava as com erro);
   - CSV sem o total da fatura: a "Diferença" fica em R$ 0,00 (o Flask subtraía de zero e mostrava o total importável negativo).

Outras diferenças:

6. Cartão inativado sai da lista (como o Flask, que lista só os ativos). O filtro "Inativos" fica vazio, como no Flask.
7. Editar a compra à vista não troca mais o mês da fatura nesta tela (a do Flask não tem o campo). O banco continua tendo a função (`editar_compra`).

## 5. Pendências

| # | Pendência | Prioridade sugerida | Causa |
|---|---|---|---|
| I1 | Importar PDF (Caixa) e XLSX | Alta | A leitura do Flask é feita no servidor, em Python; no navegador exigiria biblioteca nova (pdf.js, leitor de XLSX), o que o contrato pede para evitar sem decisão |
| I2 | Vincular linha importada a uma recorrência escolhida | Média | Depende do cadastro de recorrência no cartão (R2) |
| R2 | Cadastro e edição de recorrência no cartão | Alta | Tela Recorrências; a importação já reconhece a recorrência existente |
| C1 | Segurança do cartão: criptografia do número completo, se um dia for guardado, controle de acesso e revisão de dados sensíveis | Registrada | Mantida a decisão atual (não guardar); nada mudou |
| C2 | Histórico de importações numa tela | Baixa | O rastro existe (lançamentos e `operacao_cartao`), sem tela própria (o Flask também não tem) |

## 6. Supabase

**`20261104090000_financeiro_cartoes_tela.sql`:**
- 13 funções novas: leitura da tela, limites, fatura e lançamentos por categoria, edição de um lançamento, parcelamento e auxiliares internas;
- 3 trocadas com a mesma assinatura: `ler_dados_cartao`, `criar_cartao` e `editar_cartao`, agora com emissor e "possui código";
- sem tabela, sem coluna e sem alteração de dados.

**`20261105090000_financeiro_importacao_cartao.sql`:**
- 5 funções novas: análise, gravação, sugestões, resolução e a interna de sugestão;
- sem tabela, sem coluna e sem alteração de dados.

**Privilégios:** todas `SECURITY DEFINER` com `search_path` vazio. As da tela executam só para `authenticated`; as internas, para ninguém.

## 7. Testes

| Conjunto | Resultado |
|---|---|
| `tests/test_supabase_cartoes_tela.py` (novo) | 69/69 |
| `tests/test_supabase_importacao_cartao.py` (novo; inclui crédito, concorrência e falha no meio) | 26/26 |
| Suítes de cartões existentes (FIN-CARTOES-1, fechamento, pagamento, D6, fatura) e segurança do schema | Aprovadas, sem regressão |
| Unitários do build + leitor de CSV (`importacao-csv.test.mjs`, novo) | 23/23 |
| E2E `cartoes_tela.spec` (novo; substitui `cartoes`, `fechamento` e `pagamento` da tela anterior) | 5/5 |
| E2E `importar_cartao.spec` (novo) | 3/3 |
| E2E completos | **71/71** |
| Banco: todas as suítes Supabase de cartões, despesas, recorrências, receitas, perfis, movimentos e segurança | **626 aprovados**, nenhuma falha |

## 8. Comparação visual

Flask sobre SQLite temporário e novo aplicativo com dados fictícios equivalentes, em 1366×900. Capturas em `scratchpad/capturas_cartoes` e `scratchpad/capturas_importar`.

- **Cartões:** a mesma tela; a diferença é a correção do defeito de layout (item 4.3).
- **Importação:** a mesma tela, com o mesmo arquivo. O Flask leva "Pagamento recebido −500,00" para despesa nova de R$ 500,00 (total importável R$ 592,50). O novo aplicativo o retira como "Crédito/estorno" (total R$ 42,50). A conciliação ("Já existe na fatura") e a duplicidade ("Duplicado na fatura") coincidem.

## 9. Aplicação no teste, validação real e publicação (25/10/2026)

**Verificações pedidas antes de aplicar:**

| Verificação | Resultado |
|---|---|
| Compatibilidade das 3 funções substituídas | A diferença é só acréscimo (emissor e "possui código"). Sem esses campos, o comportamento é o anterior. Assinaturas iguais. Suítes de cartões sem regressão |
| Segurança | As 28 definições têm `search_path` vazio. Todas as expostas validam o perfil (leitura) ou a gestão (escrita), direto ou pelas travas. As internas não executam para ninguém. Nenhuma executa para `anon` |
| Integridade | A importação é uma transação. Teste: uma falha na segunda linha desfaz a primeira, e faturas e compras ficam idênticas |
| Concorrência | Três confirmações simultâneas do mesmo arquivo gravam uma vez só; a mesma chave em paralelo devolve o mesmo resultado |
| Reversibilidade | Definições anteriores salvas. Roteiro de reversão pronto e não aplicado: remove as 25 funções novas e devolve as 3, sem tocar dados |
| Auditoria do build | Exceção para `/api/` só para `js/cartoes-adaptador.js` e `js/importar-cartao-adaptador.js`, por nome. Os comentários que citavam a rota foram reescritos para não ampliar nada |

**Crédito na fatura:** verificado e coberto por testes (§ 2). O pagamento recebido nunca entra como compra negativa nem reduz o valor devido.

**Aplicação:**
1. "Antes": banco igual ao esperado sem as duas migrations.
2. Aplicadas as duas: o projeto tem 17/17.
3. "Depois": OK, com o conteúdo de todas as tabelas idêntico.
4. Demonstração idêntica.

**Validação real**, com um perfil temporário criado pelo aplicativo, o mesmo `dist` publicado e dados marcados "(e2e-real)":
- **Cartões:** cadastro com número, validade e CVV desativados; limite por categoria; compras; edição de uma parcela; alterar e cancelar parcelas futuras.
- **Despesas:**
  - a fatura aberta mostra o previsto pelo limite (R$ 300,00);
  - o pagamento cobra o executado (R$ 90,00);
  - paga, ela bloqueia a edição; estornada, libera.
- **Importação:**
  - categoria pelo histórico;
  - conciliação com a compra manual;
  - "Pagamento recebido" retirado como crédito;
  - confirmação com 1 inserida; reimportação sem nada novo.
- **Quem só lê:** vê sem ações, e a escrita direta é recusada (403), inclusive em perfil alheio.
- **Regressão real de Despesas e Recorrências:** cadastro, geração, pagamento e estorno.
- **Limpeza por identidade** (simulação e depois confirmação): banco idêntico ao retrato de antes da aplicação.

**Testes depois da aplicação:** banco (importação) 26/26; regressão local de Despesas e Recorrências: E2E 31/31 e banco 163/163.

**Publicação:**
- O Access protegia antes e depois: 302 para o login, inclusive no endereço da implantação; o endereço principal continua 404.
- Branch `avaliacao`, implantação `59954c53`, versão `ef6c0d8` (impressão do `dist` `543ae51d0636`).
- Envio direto, sem push e sem produção.

## 10. Proposta de dados de demonstração (não inserida; depende de autorização)

Para homologar Cartões e Importar Cartão com dados, em vez de telas vazias. Proposta: num perfil próprio de demonstração ou no perfil 31, conforme o titular decidir, todos os nomes marcados "(demonstracao)":

- **Cartões:**
  - "Cartão Azul (demonstracao)": fecha dia 3, vence dia 12, limite R$ 5.000, fechamento confirmado;
  - "Cartão Verde (demonstracao)": fecha dia 25, vence dia 5, sem confirmação, para mostrar a falta de sugestão.
- **Categorias do Cartão** do perfil: Mercado, Restaurantes e Assinaturas, com limites de R$ 800, R$ 400 e R$ 150 no Azul, mapeadas a categorias de despesa existentes.
- **Compras no mês corrente e no seguinte:**
  - à vista, uma delas acima do limite da categoria, para mostrar o status "Estourado";
  - parcelada 3/10 com parcelas futuras;
  - uma sem Categoria do Cartão, para mostrar "Revisar".
- **Faturas:** uma paga, com pagamento e movimento na conta de demonstração; uma aberta; uma consolidada (FECHADA), para mostrar a proteção.
- **Arquivos de importação**, só arquivos e nada gravado:
  - CSV Nubank: compras, uma repetida, um "Pagamento recebido" negativo, uma já lançada a mão e uma parcela "2/5";
  - CSV Caixa: crédito e débito;
  - CSV de layout genérico, para o mapeamento manual.
- **Inserção:** por script auditável, com identidade registrada para a limpeza, como nas validações reais.
