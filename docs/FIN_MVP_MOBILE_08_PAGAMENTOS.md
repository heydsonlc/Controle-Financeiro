# FIN-MVP-MOBILE-08: Pagamentos mobile

Tela mobile para consultar as obrigações pendentes da competência e registrar a baixa, individual ou em lote, pelos mecanismos que o desktop já tem. Nenhuma regra financeira nova, nenhuma migration, nenhuma função nova no banco.

**Situação:** implementado no ramo local `mobile-08-pagamentos` (a partir de `13f0da3`, a versão publicada em 14/11/2026 com o commit local de documentação). Sem push, deploy ou migration; nenhum dado real alterado. Homologação individual na prévia local; a publicação fica para depois, preferencialmente junto com o FIN-MVP-MOBILE-09 (Recorrências), com autorização expressa.

## 1. Análise do desktop

| # | Ponto | O que existe |
|---|---|---|
| 1 | Organização das pendentes | Lista de Despesas: grupos Financiamentos, Faturas de cartão, Despesas recorrentes, Avulsas e Investimentos; recorrências semanais da mesma competência agrupadas numa linha (`despesas-grupos.js`, as regras do `despesas.js` original) |
| 2 | Baixa individual | `pagar_despesa` (despesa) e `pagar_fatura` (fatura), pelo serviço comum `despesas-servico.js` (`POST /api/despesas/:id/pagar`, que desvia a fatura para `pagarFatura`) |
| 3 | Lote | `pagar_despesas_lote` (P20/P21): só as ocorrências de **uma mesma recorrência** (mesmo nome, sem " - DD/MM"), **todas** as pendentes dela na competência, uma conta, valor exato, sem faturas; tudo ou nada; confere de novo ocorrências, valores e identidade (`LOTE_DESATUALIZADO`, `LOTE_IDENTIDADE`, `VALOR_MUDOU`) |
| 4 | Conta bancária | Obrigatória; só as ativas do perfil (`travar_conta_bancaria`). Conta já vinculada à despesa fixa a conta do pagamento; no lote vem sugerida quando todas as ocorrências têm a mesma |
| 5 | Valor diferente | Só no individual: "Pagar outro valor" exige classificar (Juros/multa, Desconto, Ajuste) e justificar; na fatura, o executado consolidado é o sugerido |
| 6 | Classificação e justificativa | Conferidas na tela e no banco (`pagar_despesa` / `pagar_fatura`) |
| 7 | Pagamento parcial | Não existe como saldo em aberto: "outro valor" quita a obrigação com a diferença classificada |
| 8 | Recorrentes e semanais | As contas nascem ao abrir a competência na Lista (gerador do desktop, `gerar_mes`); a semanal é paga uma a uma ou pelo lote do agrupador |
| 9 | Faturas | `pagar_fatura` pelo executado; fatura sem compras não pode ser paga; a compra nunca vira conta a pagar |
| 10 | Competência e vencimento | `contas_do_mes`: despesa pela competência (`mes_referencia`), fatura pela competência do cartão |
| 11 | Duplicidade | Chave de idempotência por operação, trava da conta (`for update`) e recusa de conta já paga; no lote, chave do lote e chaves derivadas |
| 12 | Permissões | `pode_gerir_perfil` (titular); o leitor só consulta; o banco recusa a escrita de qualquer forma |
| 13 | Estorno e cancelamento | Estorno pelo movimento compensatório (Lista de Despesas e Cartões); obrigação cancelada (P23) fica com a situação `Dispensada` e não pode ser paga |

Bloqueios de pagamento no banco (`bloqueio_do_pagamento`): fatura (tem o fluxo próprio), despesa substituída na Mobilidade (fora de `contas_do_mes`) e obrigação cancelada. Despesa pendente com valor é pagável.

## 2. Decisão do titular (15/11/2026)

O layout sugerido mostra várias obrigações diferentes pagas de uma vez, o que o banco não oferece como operação única. Opções apresentadas: (A) só o que o banco tem; (B) sequência de pagamentos individuais, sem tudo-ou-nada; (C) nova função de lote atômico (migration). **Escolhida a opção A:**

- uma obrigação marcada → o pagamento individual;
- a linha da recorrência semanal marcada → o lote existente, com todas as pendentes dela;
- marcar outra obrigação com uma já marcada não seleciona e a tela explica: "O pagamento em lote reúne só as ocorrências de uma mesma recorrência semanal. Para pagar outra obrigação, desmarque a selecionada."

## 3. Implementação

**Página** `pagamentos-mobile.html` (atalho Pagamentos da Página Principal; a barra inferior não ganha item):

- cabeçalho "Pagamentos" com o perfil ativo; seletor de competência homologado;
- resumo numa linha: Pendente | Selecionadas | Selecionado;
- lista: só as pendentes (nem pagas nem canceladas), nos grupos do desktop, abertos (recolhem e expandem);
- linha: caixa de seleção | descrição (vencimento discreto; na fatura, o executado) | valor | detalhes. A caixa seleciona sem abrir; o restante da linha abre os detalhes;
- barra da seleção logo acima da barra inferior: total selecionado, Limpar e "Pagar selecionada" ("Pagar selecionadas (N)" no agrupador semanal);
- detalhes: valor, vencimento, competência, situação (Pendente ou Vencida), previsto e executado da fatura, categoria, conta ou cartão, forma de pagamento, recorrência, parcela, observações; "Pagar" quando elegível e "Ver na Lista de Despesas" (edição, exclusão e estorno continuam lá);
- resultado: "Pagamento registrado" com a mensagem do banco, "Ver em Contas" (a conta debitada no mês do pagamento, a navegação do MOBILE-07) e "Continuar"; lista, totais e seleção atualizados;
- trocar a competência limpa a seleção;
- somente leitura: consulta e detalhes, sem caixas de seleção, sem barra e sem "Pagar".

**Valores (os critérios existentes):** a linha mostra o mesmo valor da Lista de Despesas (na fatura pendente, o previsto); o "Pendente" é a soma dessas linhas (o "Pendentes" da Lista); o "Selecionado" é o que o pagamento vai sugerir (na fatura, o executado consolidado).

**Leitura sem gravar:** a rota nova `GET /api/pagamentos` do serviço comum lê `contas_do_mes` (+ `despesa_para_edicao` e `recorrencias_do_perfil`, como a Lista) **sem** a geração de recorrências que a Lista faz ao abrir o mês. Consultar Pagamentos não grava nada; uma competência ainda não aberta na Lista não tem as ocorrências recorrentes.

**Serviços reutilizados (inventário):**

| Parte | Origem | Funções do banco |
|---|---|---|
| Leitura das obrigações | `despesas-servico.js` (`obrigacoesDoMes`, rota nova, só leitura) | `contas_do_mes`, `despesa_para_edicao`, `recorrencias_do_perfil`, `categorias_de_despesa`, `contas_bancarias_do_perfil` |
| Grupos, agrupador semanal, valores | `despesas-grupos.js` (sem mudança) | — |
| Pagamento individual | `mobile-pagamento.js` → `despesas-servico.js` (`pagar`, `pagarFatura`, `composicaoFatura`) | `dados_pagamento_despesa`, `pagar_despesa`, `dados_pagamento_fatura`, `pagar_fatura` |
| Lote da recorrência semanal | `mobile-pagamento.js` (`abrirLote`, vindo da Lista de Despesas mobile sem mudança de texto nem regra) → `despesas-servico.js` (`pagarLote`) | `pagar_despesas_lote` |
| Permissão | `despesas-servico.js` (`podeGerirPerfil`) | `pode_gerir_perfil` |
| Competência, barra, Mais, painel | `mobile-comum.js`, `mobile-ui.js` | — |

**Arquivos:**

- novos: `web/src/pagamentos-mobile.html`, `web/src/js/pagamentos-mobile.js`, `web/src/css/pagamentos-mobile.css`, `web/tests/e2e/mob08_pagamentos.spec.mjs`, este documento;
- alterados:
  - `web/src/js/despesas-servico.js`: rota `GET /api/pagamentos` (só leitura);
  - `web/src/js/mobile-pagamento.js`: painel do lote comum (`abrirLote`); a conclusão do pagamento recebe também a conta e a data (as outras telas ignoram);
  - `web/src/js/despesas-mobile.js`: usa o painel comum do lote (mesmos textos e comportamento);
  - `web/src/js/mobile-comum.js`: `pagamentos` em `MODULOS_ATIVOS`;
  - `web/src/inicio.html`: destino do atalho Pagamentos;
  - `web/src/js/sessao.js`: a página como destino permitido;
  - `web/tests/unit/build.test.mjs`, `web/tests/e2e/mob08_inicio.spec.mjs`, `web/tests/e2e/mob01_despesas.spec.mjs`: o atalho habilitado;
  - `tests/supabase_local.py` e `web/tests/e2e/run_e2e.py`: pendências do mês atual no Perfil G **só na prévia** (`semear_pagamentos_previa`).

Desktop: nenhuma tela, CSS ou regra alterada.

## 4. Testes

**Unitários:** 118/118 (teste novo dos Pagamentos: página fora da moldura, CSS restrito, nenhuma consulta própria, leitura sem geração, pagamento só pelos fluxos comuns, um painel de lote só).

**Funcionais** (`mob08_pagamentos.spec.mjs`, 14 testes, usuário G em 03/2034 com dados próprios; leitor H):

| Item do contrato | Teste |
|---|---|
| 1 Atalho | atalho habilitado com a competência; abre a página; barra sem item novo |
| 2 Consulta | só pendentes (a paga fica de fora), grupos do desktop, valores, total pendente igual ao do banco |
| 3–5 Seleção e total | marcar, desmarcar, recusa de outra obrigação com aviso, agrupador com as 4 pendentes, total e quantidade, Limpar |
| 6, 9, 10 Individual | outro valor exige classificação; JUROS e justificativa gravados; data de hoje |
| 7 Lote | painel com quantidade, total, data e conta obrigatória; as 4 pagas, 4 movimentos, saldo |
| 8 Conta | conta obrigatória; débito na conta escolhida |
| 11 Recorrentes e semanais | agrupador semanal; ocorrências geradas pela Lista, não pelos Pagamentos |
| 12 Fatura | paga pelo executado; a compra não vira conta; sai das pendentes |
| 13, 16 Duplicidade e falhas | toque duplo paga uma vez; conta paga por outro aparelho com o painel aberto: "Esta despesa já está paga.", nenhum movimento a mais; lote com as pendentes mudando: recusado inteiro, nada pago, lista conferida de novo |
| 14, 15 Saldos e movimentos | saldo pelas funções do desktop e conferência consistente; "Ver em Contas" abre a conta com o movimento |
| 17 Somente leitura | sem seleção, barra nem "Pagar"; o banco recusa o pagamento do leitor |
| 18 Consulta não grava | competência nunca aberta continua sem ocorrências; a aberta, igual |
| Responsividade | 320, 375, 390 e 430 px: sem rolagem horizontal, valores, barra e rótulos inteiros |

**Regressão:** ver a seção 7.

## 5. Comparação com o desktop

| Operação | Desktop | Pagamentos mobile |
|---|---|---|
| Lista das pendentes | Lista de Despesas (filtro "Pendentes") | as mesmas linhas e grupos, só pendentes, sem gerar ao consultar |
| Pagar uma | modal de pagamento (`pagar_despesa` / `pagar_fatura`) | o mesmo formulário mobile da Lista e dos Cartões, as mesmas funções |
| Lote | botão do agrupador semanal (`pagar_despesas_lote`) | a linha do agrupador marcada, o mesmo lote; data de hoje mostrada |
| Várias diferentes | não existe | não existe (opção A) |
| Editar, excluir, estornar | Lista de Despesas | continuam lá ("Ver na Lista de Despesas") |

## 6. Pendências

| # | Pendência | Classificação |
|---|---|---|
| 1 | **Ocorrência semanal cancelada (P23) no agrupador da Lista** (desktop e Lista mobile): o agrupador conta como pendentes as ocorrências com a situação `Dispensada` (o campo `cancelada` que o código original lê nunca é preenchido), e o lote do banco as deixa de fora. Se uma ocorrência semanal for cancelada, o lote da Lista é recusado com `LOTE_DESATUALIZADO`: nada é pago, falha segura. Os Pagamentos mobile já deixam a cancelada de fora. Correção na Lista exige autorização (tela homologada) | **Não bloqueadora**; correção futura |
| 2 | Pagar obrigações diferentes de uma vez, tudo ou nada (proposta C: uma função nova, como a da P20) | **Melhoria futura** (migration e regra nova, contrato próprio) |
| 3 | Data do lote fixa no dia de hoje (como no desktop); o individual permite escolher | **Melhoria futura** |
| 4 | Competência ainda não aberta na Lista não mostra as ocorrências recorrentes (a consulta não gera, por contrato) | **Por desenho**; registrada |
| 5 | Pendências de meses anteriores não aparecem (só a competência selecionada) | **Melhoria futura** |
| 6 | Fatura sem compras aparece na lista, sem seleção ("sem compras a pagar"), como na Lista de Despesas | **Por desenho** |

## 7. Regressão

Suíte completa de navegador (os sete MVPs mobile, o integrado do FINAL-01 e todas as telas do desktop: Despesas, pagamento individual e em lote, Recorrências, Cartões, Contas Bancárias, Lançamentos, Dashboard, autenticação e permissões):

| Rodada | Aprovados | Reprovados | Não rodaram |
|---|---|---|---|
| Versão publicada (`9056a4a`, 14/11/2026) | 224 | 0 | 0 |
| MOBILE-08, 1ª rodada | 236 | 1 | 1 |
| MOBILE-08, 2ª rodada | **238** | **0** | **0** |

238 = os 224 da versão publicada + os 14 novos dos Pagamentos.

**A falha da 1ª rodada** foi `lancamentos_tela.spec:60` (tela Lançamentos do desktop, usuário B, 02/2034): a compra no cartão, logo depois de recarregar a página, saiu como "despesa direta". Nenhum arquivo dessa tela foi alterado (o MOBILE-08 só toca o serviço de Despesas, com uma rota de leitura, e as páginas mobile); o teste passou isolado duas vezes e na 2ª rodada completa. Intermitência de tempo da tela original, sem gravação indevida (o banco recusou e nada ficou gravado). **Não bloqueadora**; registrada.

Desktop: nenhuma tela alterada; o serviço comum ganhou só a rota de leitura (as rotas de pagamento são as mesmas).

## 8. Homologação no Firefox

1. A prévia: http://127.0.0.1:8790/__previa__/ (`run_e2e.py --previa`).
2. Entrar com `usuario.g@teste.local` / `Senha-ficticia-G-2026` e tocar no atalho **Pagamentos** (mês atual). Somente leitura: `usuario.h@teste.local` / `Senha-ficticia-H-2026`.
3. Dados fictícios do mês atual: IPTU, Internet Casa e Condomínio (avulsas), Academia (estornada, pendente), Diarista (semanal, 4 terças), fatura do Itau Visa (com compras) e a do Master (sem compras).
4. Conferir: seleção de uma e a recusa de outra; o agrupador semanal; pagamento individual (inclusive outro valor); lote; fatura; "Ver em Contas"; trocar a competência; o leitor.
