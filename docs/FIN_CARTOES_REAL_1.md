# FIN-CARTOES-REAL-1 — Validação real de cartões e compras

**Data:** 2026-10-22.

**Alvo:** projeto Supabase de teste **Controle-Financeiro** (`fzjmge…`). A Calculadora Judicial não foi tocada.

**Situação:** **validado no Supabase de teste**. Os dados fictícios foram removidos. O estado final é idêntico ao inicial, exceto pela migration autorizada.

**Autorização:** SCRIPT-CONTRATO V5 — FIN-CARTOES-REAL-1.

**Não foi feito:**
- publicar;
- alterar dados reais;
- rodar Alembic no `gastos.db`;
- implementar pagamento, estorno ou regra de fechamento.

## 1. Push e deploy

- Revisão do commit `476daa0`: sem segredos, chaves ou arquivos pessoais. Os números de cartão no diff são fictícios de teste.
- Push `2017df6..476daa0`.
- O check "Supabase Preview" ficou `skipped`: o deploy automático de migrations continua desligado.

## 2. Migration

1. **`status` e `simular`:** só `20261028090000` pendente.
2. **Conferência somente leitura antes da aplicação:**
   - todas as colunas usadas existem nas 11 tabelas envolvidas;
   - as dependências existem: `pode_acessar_perfil`, `pode_gerir_perfil`, `pertence_ao_perfil`, `dia_contratual` e `gen_random_uuid`;
   - o índice `ux_conta_fatura_cartao_competencia` está presente;
   - nenhum dos 25 objetos novos colide com outro (24 funções + a tabela `operacao_cartao`);
   - não há `drop` nem `truncate`, e nada é concedido a `anon`;
   - as únicas alterações de tabela são a RLS da tabela nova;
   - as funções escrevem só em `item_despesa`, `config_agregador`, `conta` (faturas), `lancamento_agregado` e `financeiro.operacao_cartao`;
   - **0** faturas duplicadas e **0** faturas com `status_fatura='PAGA'` no banco.
3. **Impressão digital inicial** e aplicação **exclusiva** de `20261028090000`. O remoto ficou com 9 migrations.
4. **Privilégios no banco:**
   - todas as 24 funções são `SECURITY DEFINER` com `search_path` vazio;
   - as 11 expostas só para `authenticated`;
   - as 13 internas sem EXECUTE para o navegador;
   - nenhuma para `anon`;
   - `operacao_cartao` com RLS forçada, sem privilégios e vazia.

## 3. Dados fictícios e perfis

- **Decisão do usuário:** o seed de contas roda como nas validações anteriores. Ele coloca dados fictícios em Pessoal e Empresa, sem alterar as linhas desses perfis, e é removido no fim.
- **Todo o cenário novo de cartões ficou no "Perfil B" temporário:**
  - o cartão inativo do seed novo `scripts/supabase_cartoes_seed_teste.py`;
  - os cartões criados pela tela e pela API, com compras, faturas, categoria do cartão, vínculo e limite.
- **Usuário A:** só leu ou teve tentativas recusadas em Pessoal e Empresa.
- **Teste de navegador de cartões:** passou a escrever com o usuário B no Perfil B também no ambiente local, então os dois cenários são iguais.
- **Ordem dos seeds:** perfis → contas → recorrência → receitas → MVP → cartões. A remoção foi na ordem inversa.

## 4. Resultados

**Navegador (E2E real, celular de 390 px): 47/47**, os mesmos 47 do ambiente local. Os 4 de cartões:
- faturas iguais às de Contas do mês, sem nenhuma ação de pagamento;
- fatura paga sem ações;
- final do número sem o número completo;
- ciclo completo: cartão → prévia → compra parcelada → edição → exclusão → inativação;
- LEITOR sem nenhuma ação.

**API, concorrência e Flask** (`scripts/supabase_cartoes_real.py`): **21/21**. Login real, Data API real, threads com transações independentes, conexões próprias ao banco e processos Flask reais.

| Item do contrato | Resultado |
|---|---|
| Criação e edição de cartões | Edição com versão; versão antiga e número de cartão recusados (400); final 8888 sem o número completo |
| Inativação | Compra e fatura preservadas; compra nova recusada; cartão fora das faturas do mês |
| À vista + limite por categoria | Planejado 300 (limite), executado 120; previsto 300 = valor da fatura em Contas do mês (1 linha, sem dupla contagem) |
| Parcelamento e centavos | 1000/7, 0,05/3, 100/3: soma exata; **prévia = gravado** |
| Virada de mês e ano | Faturas 11/2034 a 02/2035; dia 31 vira 30 |
| Vencimentos 29/30/31 | 29/02/2036 nos três; 28/02/2035 (dia 29); 30/04/2035 (dia 31) |
| Compras simultâneas no mesmo cartão | 3 × 200; 1 fatura; executado = soma real das compras do mês |
| Repetição da mesma solicitação | Mesma chave × 3 em paralelo: 1 compra |
| Concorrência com a geração de recorrências | Compra e geração simultâneas no Perfil B (gerador novo): ambas 200 e nenhuma fatura duplicada |
| Unicidade com o Flask | Flask inseriu a fatura sem commit: a compra nova **esperou** e reaproveitou a fatura. Flask e novo app no mesmo mês: 1 fatura com as duas compras |
| Compatibilidade com compras do Flask | Parcelada 3× criada pelo Flask real = parcelas do novo app (todos os campos de negócio); agrupada pelo `compra_id`, editada (3) e excluída (3) pelo novo app; faturas recalculadas |
| Edições simultâneas | Mesma versão: uma 200, outra 400 (versão) |
| Fatura paga | Compra nova desviada para 07–09/2035 (a prévia avisa); fatura paga **intacta (md5)**; editar e excluir 400; exclusão parcial: 2 abertas removidas e 1 paga preservada |
| Compra durante um pagamento | Esperou a transação do pagamento e depois foi recusada (400); fatura sem a compra |
| Fatura fechada × paga | `FECHADA` aparece como fechada, não como paga; edição 400; compra nova aceita (como no Flask) |
| Autorização | Gestor só no próprio perfil. Recusados com 403: A no Perfil B, B no Pessoal, A em perfil inativo e A editando compra alheia por outro perfil. LEITOR lê a Empresa (200) e não cria cartão (403) |
| Anônimo | As 11 funções: 401 |
| Acesso direto às tabelas | `lancamento_agregado`, `config_agregador` e `conta`: 406 (`public` fora da Data API); `operacao_cartao`: 403 |
| Unicidade geral | 0 faturas e 0 parcelas duplicadas |
| Saldos e movimentos | Movimentos, contas bancárias e contas, compras e itens fora do Perfil B **idênticos** do início ao fim |

**Primeira rodada:** 3 itens falharam por **asserções erradas do script**, e não por defeito do sistema. Elas esperavam valores fixos em meses que também tinham parcelas de outras compras do próprio teste: os 202,86 eram 60,00 mais a parcela de 142,86 da compra em 7 vezes. As asserções passaram a comparar com a soma real das compras do mês. Os dados da rodada foram limpos e o script rodou de novo do zero: 21/21.

## 5. Atenções específicas

**Exclusão parcial de compra parcelada.** Com parcela em fatura paga ou fechada, a tela pergunta: "Excluir as N parcelas em fatura aberta? M em fatura paga ou fechada ficam (para corrigi-las é preciso estorno)." Na edição, avisa que "M em fatura paga ou fechada ficam como estão". O banco devolve `{excluidas, preservadas}` e nunca toca a parcela paga. **Sugestão (não implementada):** deixar explícito "isto não cancela as parcelas já pagas", junto da futura tela de estorno.

**Fatura fechada.**
- É identificada **só** por `conta.status_fatura = 'FECHADA'`, que a consolidação do Flask grava.
- Paga é `status_pagamento = 'Pago'` ou `status_fatura = 'PAGA'`.
- Nada é inferido do vencimento nem do dia de fechamento.
- No banco de teste não havia fatura fechada nem paga antes dos testes.

## 6. Limpeza

**Ordem:**
1. `supabase_despesas_real_limpeza.py remover`. Ela agora cobre a configuração e os limites dos cartões criados pelos testes, as categorias do cartão **com o marcador do teste** e seus vínculos, e as chaves de `operacao_cartao`.
2. Removedores dos seeds, em ordem inversa.

A primeira rodada também foi limpa antes da segunda. **Nenhum arquivo de estado ficou em `data/`.**

**Impressão digital final idêntica à inicial em:**
- conteúdo de 19 tabelas, entre elas:
  - `conta`, `item_despesa`, `lancamento_agregado`, `config_agregador`;
  - `cartao_categoria_limite`, `categoria_cartao`, `categoria_cartao_despesa`;
  - `conta_bancaria`, `movimento_financeiro`, `perfil_financeiro`, `usuario`;
  - receitas, `financeiro.perfil_acesso` (nenhum vínculo temporário ficou) e `financeiro.categorias`;
- contagens das 52 tabelas `public`, Auth e Alembic (`c4f7a2d91b3e`).

**Diferenças, só as esperadas:** a migration `20261028090000` e a tabela `financeiro.operacao_cartao`, existente e **vazia**. As sequências avançaram, o que é normal.

## 7. Suíte completa

Comando original (`venv\Scripts\python.exe -m pytest`; o `pytest.ini` já tem `addopts = -q`). Resumo real impresso pelo pytest: **`5 failed, 1417 passed, 19 skipped, 1140 warnings in 703.77s`**. O código de saída 1 vem só destas 5 falhas que já existiam:
- `test_categorias_sistemicas_mobilidade::test_projecoes_veiculo_usam_categorias_sistemicas_granulares`
- `test_ocr_tools::test_status_sem_ferramentas_retorna_estrutura_valida`
- `test_ocr_tools::test_poppler_ausente_retorna_aviso`
- `test_receitas_ux::test_cards_resumo_calculam_previsto_realizado_diferenca_confiabilidade`
- `test_veiculos_mobilidade_2b::test_suprimir_despesas_previstas_futuras`

**Observação:** no FIN-CARTOES-1 a suíte foi chamada com `-q` a mais. Somado ao `-q` do `pytest.ini`, isso vira `-qq`, que omite a linha final de resumo, e o total foi deduzido da contagem dos testes coletados. Agora o resumo vem do próprio pytest e confirma o mesmo número.

## 8. Arquivos

- `scripts/supabase_cartoes_real.py` (novo): testes reais.
- `scripts/supabase_cartoes_seed_teste.py` (novo): cartão inativo fictício no Perfil B.
- `scripts/supabase_despesas_real_limpeza.py`: cobre cartões.
- `web/tests/e2e/cartoes.spec.mjs`: escrita com o usuário B no Perfil B.
- `tests/supabase_local.py`: cartão inativo do E2E no Perfil B.
- `docs/FIN_CARTOES_REAL_1.md`, `docs/FIN_CARTOES_1.md` e `docs/ROADMAP.md`.

## 9. Riscos e pendências

- **FIN-PAGAMENTO-TRAVA-1** continua **obrigatório**. O pagamento do Flask lê a conta sem trava. Do lado do novo app, compra e edição já esperam e recusam (item "Compra durante um pagamento").
- **Defeitos do Flask continuam na tela dele** (não alterado):
  - compra entra em fatura paga;
  - editar ou excluir compra sem conferir nem recalcular;
  - vencimento no dia 31 quebra.
- **Faturas vazias:** o Flask e o novo app deixam a fatura (com valor 0) depois que todas as compras são excluídas.
- **FIN-CARTOES-FECHAMENTO-1** (adiado): sugerir a competência pelo dia de fechamento, com ajuste manual e sem recalcular o histórico.
- **Alembic `d81f5a2b9c3e` e `e3b7c9d1a2f4`** seguem não executadas no `gastos.db`.
