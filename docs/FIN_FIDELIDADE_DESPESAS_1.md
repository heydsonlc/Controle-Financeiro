# FIN-FIDELIDADE-DESPESAS-1 — Tela original de Despesas do Flask sobre o Supabase

> **Atualização (FIN-RECORRENCIAS-AUTOMATICAS-1):** a geração das recorrências voltou a ser automática ao abrir Despesas ou trocar a competência, como no Flask; o botão "Gerar contas" e a confirmação saíram. Ver `docs/FIN_RECORRENCIAS_AUTOMATICAS_1.md`.

**Situação:** implementada e testada **localmente**, com dados fictícios. Ainda não foi feito: commit, push, migration ou publicação.

**Referência:** `frontend/templates/despesas.html`, `frontend/static/js/despesas.js` e `frontend/static/css/despesas.css`, além das rotas `/api/despesas*` do Flask. Os arquivos do Flask **não foram alterados**.

## A. Fidelidade visual

**Reaproveitado diretamente.** O build copia do Flask:
- o HTML da barra de ações e do conteúdo do template: filtros, competência, busca, Atualizar, "A partir de documento", "Nova despesa";
- os 6 cartões de resumo, a lista agrupada por origem e tipo e o painel lateral (composição, por categoria, próximos vencimentos);
- todos os modais: nova/editar despesa (com recorrência, cartão, semanal e consórcio), pagar, estornar, tipo de exclusão e de edição, seletor de documento;
- `despesas.js`, sem alteração de código;
- os componentes globais `utils.js`, `icons.js`, `instituicoes.js` e `formas_pagamento.js`;
- o CSS `despesas.css`;
- as imagens dos meios de pagamento, só as que os componentes citam pelo nome, todas versionadas.

**Adaptações necessárias:**
1. **CSP sem script nem estilo inline.** O original usa 64 `onclick=` e 76 `style=`. O build troca esses atributos por `data-on-*` e `data-estilo`, a única mudança nas cópias.
   - `js/ponte-csp.js` executa as chamadas sem `eval`, só funções de uma lista gerada no build, e aplica os estilos pelo CSSOM.
   - A CSP **não foi afrouxada**.
2. **API do Flask.** As chamadas `fetch('/api/...')` da tela são entregues por `js/ponte-api.js` a `js/despesas-adaptador.js`, que responde no formato do Flask usando as funções do Supabase.
3. **Script inline do template.** Foi movido para `original/despesas-inline.js`, sem alteração.
4. **`js/despesas-adaptacoes.js`.** Substitui só o indispensável, cada caso comentado:
   - competência: o mês do menu é mantido e trocar de mês recarrega;
   - pagamento: classificação e justificativa da diferença;
   - "A partir de documento" informa que está em migração.
5. **Dois acréscimos visuais, os únicos.**
   - A geração explícita de recorrências, com prévia, confirmação e avisos de recorrência rejeitada, no topo do painel da lista. Vem do FIN-RECORRENCIA-1, extraída sem mudança de `contas.js`.
   - No modal de pagamento, "Classificação da diferença" e "Justificativa". Aparecem só quando o valor pago difere do devido.
6. **Quem só lê o perfil** não vê as ações de escrita (`body.cf-somente-leitura`); o banco também recusaria.

**Removidos:** `contas.js`, o `despesas.js` do novo aplicativo e `movimentos.js`. A antiga tela "Contas do mês" foi substituída pela original.

## B. Funcionalidades

| Operação | Situação |
|---|---|
| Consultar por competência; trocar o mês pelo filtro; mês mantido no endereço e no menu | Funcionando com adaptação (o Supabase devolve o mês pedido; o Flask devolvia todos) |
| Filtros (forma de pagamento, status, vencimento até) e busca | Funcionando |
| Agrupamento (faturas, recorrentes, avulsas, financiamentos, consórcios) e ordem do Flask | Funcionando |
| Resumos (total, pendentes, pagas, vencendo em 7 dias, cartões, saldo do mês) e painel lateral | Funcionando (somas de apresentação no adaptador, como a rota do Flask fazia) |
| Criar despesa avulsa ou recorrente mensal/anual (competência pela regra do Flask: mês anterior ao vencimento) | Funcionando |
| Editar despesa (nome, observações, valor, vencimento, categoria e competência da avulsa) | Funcionando com adaptação: despesa paga ou com movimento não abre edição (regra do banco) |
| Excluir; recorrente: "apenas esta" (competência dispensada) e "esta e as futuras" (inativa a recorrência e exclui esta conta; as já geradas continuam) | Funcionando com adaptação |
| Pagar despesa (conta bancária, valor, data); outro valor com classificação e justificativa | Funcionando com adaptação (pagamento integral; regra do FIN-MOVIMENTACOES-1) |
| Pagar fatura e estornar pagamento de despesa ou fatura | Funcionando |
| Detalhe da fatura (compras do mês) | Funcionando com adaptação (sem o bloco "por categoria com limite"; ver C) |
| Perfil ativo, isolamento e permissão | Funcionando |
| Geração de recorrências | Funcionando com adaptação: explícita, com confirmação (no Flask era automática) |
| Recorrência semanal, recorrência paga no cartão, débito automático no formulário | Dependente da tela Recorrências e do cadastro da conta do débito. Recusado com aviso, sem gravar |
| Alterar a recorrência pelo formulário (tipo e valor das próximas) | Dependente da tela Recorrências. Recusado com aviso |
| "É um Consórcio" e edição de parcela de consórcio | Dependente do módulo Consórcios (campos preservados; recusado com aviso) |
| "A partir de documento" | Dependente de Documentos Fiscais (OCR); o seletor abre e informa |
| Consolidar fatura | Dependente de Cartões (o botão só aparece com status da fatura, que a lista não traz, como no Flask) |
| Meio de pagamento boleto/PIX na recorrência | Aceito, mas ainda não registrado (a mensagem informa) |

## C. Supabase

**Funções usadas (todas existentes, sem migration):**
- leitura da lista: `contas_do_mes` (mês e vizinhos, para "vencendo em 7 dias" e "próximos"), `despesa_para_edicao` (uma por despesa do mês), `receitas_do_mes`, `categorias_de_despesa`, `contas_bancarias_do_perfil`, `compras_da_fatura`;
- geração: `previa_geracao`, `recorrencias_rejeitadas`, `gerar_mes`, `dispensar_aviso_recorrencia`;
- escrita: `criar_despesa`, `editar_despesa`, `excluir_despesa`, `inativar_recorrencia`;
- pagamento e estorno: `dados_pagamento_despesa`, `pagar_despesa`, `estornar_pagamento_despesa`, `dados_pagamento_fatura`, `pagar_fatura`, `estornar_pagamento_fatura`.

Idempotência por chave de operação: a mesma chave é reusada em reenvios.

**Dependências registradas** (não criadas: o contrato não autoriza migration):
1. **Leitura da lista no formato do Flask.** Hoje o adaptador faz 1 chamada a `despesa_para_edicao` por despesa do mês, para recorrência, categoria, observações e conta. Uma função de leitura única deixaria a lista mais rápida.
2. **Meio de pagamento** (boleto, PIX, cartão) do item, que as funções de despesa não gravam.
3. **Limites por categoria do cartão na fatura** (bloco "por categoria" do detalhe).
4. **Recorrência semanal e recorrência no cartão.**
5. **Consórcios e documentos fiscais.**

## D. Testes (locais)

| Conjunto | Resultado |
|---|---|
| Unitários do build (moldura, CSP, RPCs liberadas por arquivo, sem `innerHTML` no código novo) | 17/17 |
| E2E completos (`run_e2e.py`) | 64/64, sem erro de CSP ou JS, sem chamada recusada pela ponte, sem chamada a `/api/` |

**Specs reescritos para a tela original:**
- `contas.spec` (consulta, filtros, competência, Empresa só leitura, isolamento, celular);
- `despesas.spec` (cadastro, edição, exclusão, pedidos não atendidos, 403);
- `movimentacoes.spec` (pagar com juros, estornar, saldo por `movimentos_do_mes`);
- `recorrencia.spec` (gerar, editar conta, excluir "apenas esta" e "esta e as futuras").

**Ajustados:** `pendencia`, `moldura`, `perfis`, `perfis_gestao`, `cartoes` e `receitas`.

**Ressalva:** os testes Python não foram repetidos. O contrato não mexe no banco nem no Flask.

## E. Comparação visual (capturas em `scratchpad/capturas_despesas`, 1366×900)

O Flask rodou sobre um SQLite temporário, e o novo aplicativo sobre o banco descartável, com os mesmos dados fictícios (Pessoal, 11/2026).

**Iguais:** barra de ações, cartões de resumo, grupos, ordem, colunas e logotipos de meio de pagamento, e os modais de nova despesa, pagar e estornar. Também saem iguais três características que o Flask já tem em 1366 px: os cartões passam por baixo do painel lateral, as colunas são cortadas e o texto fica centralizado.

**Diferenças efetivas:**
1. O aviso de geração de recorrências no topo do painel da lista (geração explícita).
2. No modal de pagamento, classificação e justificativa quando o valor difere.
3. **Painel lateral:** no Flask, "Composição mensal" e "Por categoria" mostram o mês com que a página foi carregada, não o filtrado (por isso "Sem dados"). Aqui mostram o mês na tela.
4. **Plano de saúde:** aparece como "Débito automático" (dado real da conta). No Flask aparecia "Não informado".
5. **Situação:** só "Pago" ou "Pendente", como no Flask. A tela anterior do novo aplicativo mostrava "Vencida".
6. **Modal de edição:** o Flask preenchia "Nome" com o nome do item e "Descrição" com o nome da conta, e o salvar gravava a descrição sobre o nome (defeito). Aqui: nome, observações e competência corretos.
7. **"Movimentos do mês" e saldos** (que a tela anterior do novo aplicativo listava) não existem na tela original. Ficam para Contas Bancárias. A mensagem do pagamento informa a conta e o saldo.
8. **Fechar o mês:** a geração não ocorre ao abrir a tela; é pelo botão "Gerar contas", com confirmação.

## F. Git

Arquivos alterados, **sem commit**, aguardando autorização:
- `web/scripts/build.mjs`
- `web/src/paginas/contas.html`
- `web/src/js/moldura.js`
- novos:
  - `web/src/js/ponte-csp.js`, `ponte-api.js`, `despesas-adaptador.js`, `despesas-adaptacoes.js`, `despesas-recorrencias.js`;
  - `web/src/css/despesas-adaptacoes.css`;
  - `web/src/original/despesas-inline.js`;
  - `web/tests/e2e/despesas.mjs`;
- removidos: `web/src/js/contas.js`, `despesas.js`, `movimentos.js`;
- specs e teste unitário ajustados;
- este documento.

**Observação:** dois arquivos sem rastreio de uma tentativa anterior interrompida deste contrato foram examinados.
- `despesas-recorrencias.js`: reaproveitado, com os rótulos originais restaurados.
- `css/despesas-fidelidade.css`: removido, porque a conversão no build tornou a abordagem dele desnecessária.

## H. Pendências de integração (decisão do titular, 25/10/2026)

**Diretriz:** a tela do Flask é a referência visual e funcional, mas melhorias já feitas no novo aplicativo não se perdem. Quando houver conflito, a decisão é caso a caso.

| # | Pendência | Situação até lá | Quando volta |
|---|---|---|---|
| P1 | **Movimentos do mês e saldos bancários** (a tela anterior do novo aplicativo os listava em Despesas) | **Ausência temporária, não exclusão.** Os dados continuam no banco (`movimentos_do_mes`); a mensagem do pagamento informa conta e saldo | **Obrigatória** quando Contas Bancárias for integrada ao Supabase |
| P2 | Leitura da lista no formato do Flask numa função só | Uma chamada a `despesa_para_edicao` por despesa do mês | Função de leitura (migration a autorizar) |
| P3 | Meio de pagamento (boleto, PIX, cartão) gravado no item | **Resolvido (boleto, PIX, débito)** no FIN-FIDELIDADE-RECORRENCIAS-1; cartão segue P5 | — |
| P4 | Limites por categoria do cartão no detalhe da fatura | Detalhe mostra as compras, sem o bloco "por categoria" | Junto com a tela Cartões |
| P5 | Recorrência semanal, recorrência no cartão e alteração de recorrência pelo formulário | Alteração: **na tela Recorrências** (FIN-FIDELIDADE-RECORRENCIAS-1). Semanal e cartão: recusados com aviso | Gerador (R1) e Cartões (R2) |
| P6 | Débito automático no formulário (conta do débito) | **Resolvido:** cadastrado na tela Recorrências (com a conta). O "Débito" do formulário de Despesas é débito comum, gravado como informativo | — |
| P7 | Consórcios ("É um Consórcio", edição de parcela) | Campos preservados, recusado com aviso | Módulo Consórcios |
| P8 | "A partir de documento" | O seletor abre e informa | Documentos Fiscais |
| P9 | Consolidar fatura pela tela de Despesas | Como no Flask (a lista não traz o status da fatura) | Tela Cartões |

## G. Publicação (25/10/2026)

**Commit:** `352c4e6`, com os 25 arquivos do contrato e os documentos. Sem push.

**Build:** URL e chave **publicável** do Supabase de teste. 16 páginas, CSP inalterada, sem segredos e sem endereço do Flask (`localhost`, `:5000`, Render). O texto `/api/` aparece só nas rotas atendidas localmente pela ponte e pelo adaptador. Impressão do `dist`: `fe783b3226b2`.

**Validação real** (o mesmo `dist`, servido com o `_headers` real, contra o Supabase de teste). Nenhum erro de CSP ou JS e nenhuma requisição a `/api/` nem fora do site ou do Supabase.

| Verificação | Resultado |
|---|---|
| Perfil de demonstração, só leitura: 10/2026 com 6 despesas e a fatura, resumo, filtro, detalhe da fatura, modais de nova despesa e de pagamento (sem enviar), troca de competência | Aprovado |
| Perfil temporário criado pelo aplicativo (gerador NOVO), com conta bancária de teste: criar, editar, pagar com juros justificados (mensagem com o saldo), estornar e excluir pelos modais originais | Aprovado |
| Recorrência mensal cadastrada e gerada pela confirmação | Aprovado |
| Conta B com vínculo só de leitura: vê a lista, sem ações de escrita | Aprovado |
| Limpeza por identidade (perfil criado pelo aplicativo, vínculos e conta do teste; todas as tabelas com `perfil_financeiro_id` contadas; simulação e depois confirmação) | Contagem e md5 de todas as tabelas iguais ao retrato tirado antes |

**Ressalva da validação:** duas execuções pararam por cancelamentos provocados pelo próprio roteiro de teste (navegação enquanto a página ainda carregava). Em cada caso, o perfil temporário foi limpo por identidade e a validação refeita do início.

**Publicação:**
- O Access protegia a prévia antes e depois do envio: 302 para o login do Access na prévia, em páginas internas, no `config.js` e no endereço da versão. O endereço principal continua sem deploy (404).
- Enviado só para a branch `avaliacao`: implantação `d9f7a5b5` (Preview, versão `352c4e6`), endereço **https://avaliacao.controle-financeiro-jah.pages.dev**.
- Nenhuma implantação de produção.

**Próximo passo:** validação visual e funcional pelo titular na prévia. A produção continua dependendo de aprovação posterior.
