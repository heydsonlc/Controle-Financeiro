# FIN-MVP-MOB-01: Lista de Despesas mobile

Segunda etapa da versão mobile. O atalho **Resumo** da página principal mobile (FIN-MVP-MOB-08) e o Resumo da barra inferior abrem uma lista de despesas compacta: os grupos do desktop em accordion, detalhes num painel inferior e as operações do desktop (pagar, editar, estornar, excluir, cancelar a obrigação, interromper a recorrência e pagar em lote). Os registros, o serviço e as regras são os mesmos do desktop, sem controle paralelo.

> **Nome:** o identificador `FIN-MVP-MOB-01` já foi usado pela Mobilidade (abastecimentos, `docs/FIN_MVP_MOB_01.md`, publicado em 07/11/2026), e `FIN-MVP-MOB-02` também (projeções de veículos). Por isso este documento tem nome próprio (`FIN_MVP_MOB_01_LISTA_DESPESAS.md`). Sugestão para as próximas etapas: uma série própria para a versão mobile, como `FIN-MVP-MOBILE-NN`.

**Situação:** implementado no ramo local `mob-01-despesas` (a partir do MOB-08, `65bada2`). Sem push, deploy nem migration. Publicação só depois da homologação do titular, junto com o MOB-08, do qual depende.

> **Atualização (14/11/2026):** aprovado pelo titular; a série passou a se chamar FIN-MVP-MOBILE-NN (esta etapa é a FIN-MVP-MOBILE-02). No FIN-MVP-MOBILE-03 (Cartões), `css/despesas-mobile.css` virou `css/mobile-modulo.css`, com o mesmo texto e o escopo `body.mob-modulo`. Os elementos, o painel e o formulário de pagamento foram para `js/mobile-ui.js` e `js/mobile-pagamento.js`, sem mudança. As capturas desta tela ficaram idênticas pixel a pixel (`docs/FIN_MVP_MOBILE_03_CARTOES.md`).

## 1. Análise da tela do desktop (antes de implementar)

| Ponto | Onde está | Como o mobile reaproveita |
|---|---|---|
| Lista e grupos | `frontend/static/js/despesas.js` (arquivo do Flask, vai sem mudança para `js/original/despesas.js`): `renderizarDespesas`, `grupoLeitura`, `agruparDespesasSemanais` | `js/despesas-grupos.js`: as mesmas funções e regras. O teste unitário roda o arquivo original numa VM e compara a saída |
| Grupos e ordem | FINANCIAMENTOS, FATURAS DE CARTÃO DE CRÉDITO, DESPESAS RECORRENTES, DESPESAS AVULSAS, INVESTIMENTOS; dentro do grupo, a ordem do serviço (vencimento mais recente primeiro), com os agrupadores semanais antes | os mesmos, sem grupo novo |
| Valores e totais | `obterValorDespesa` (fatura usa `valor_fatura`), `calcularTotaisAgrupamento`, cartões de resumo (`atualizarResumo`: total, pendentes, pagas) | o total do grupo é a soma das suas linhas; o total final é o mesmo do desktop |
| Competência | `?mes=` e o filtro MM/AAAA (`js/despesas-adaptacoes.js`); o serviço lê só o mês pedido | `?mes=` no endereço, sincronizado com a página principal |
| Filtros | forma de pagamento, status, vencimento até (`aplicarFiltros`) e busca (`filtrarBusca`) | os mesmos, num painel |
| Rotas e regras | `js/despesas-adaptador.js`: rotas `/api/despesas...` sobre as funções do banco (`contas_do_mes`, `despesa_para_edicao`, `editar/excluir/cancelar_despesa`, `dados_pagamento_*`, `pagar_despesa`, `pagar_fatura`, `pagar_despesas_lote`, `estornar_*`, `previa_*`, `interromper_recorrencia`, `editar_parcela_consorcio`) | **as mesmas rotas e funções**: o código passou para `js/despesas-servico.js`, sem DOM, usado pelos dois |
| Fluxos | pagamento (outro valor com diferença classificada e justificada), estorno (motivo e data), edição (consórcio: esta ou esta e as futuras; recorrência muda em Recorrências), exclusão (simples; recorrente: esta ou esta e as futuras, com a prévia do P22; pagamento estornado: "Cancelar obrigação", P23), lote semanal (P20/P21) | os mesmos pedidos, campos e validações, num painel compacto; a prévia de "esta e as futuras" usa o mesmo modal (`js/interrupcao-recorrencia.js`) |

## 2. O que foi feito

| Arquivo | Mudança |
|---|---|
| `web/src/js/despesas-servico.js` (novo) | o código de `despesas-adaptador.js`, sem alteração de regra: as rotas, a tradução de formato, as validações e as chaves de idempotência. O que era da tela (aviso da geração, competência da moldura) chega por ganchos (`configurarDespesas`) |
| `web/src/js/despesas-adaptador.js` | fica só com a moldura, a competência do menu e o aviso da geração, e registra `responderDespesas` na ponte, como antes |
| `web/src/js/despesas-grupos.js` (novo) | regras de leitura do desktop em funções puras: grupos, ordem, agrupador semanal, valores, forma de pagamento, filtros, totais e textos |
| `web/src/despesas-mobile.html` (novo) | página fora da moldura (como `inicio.html`): cabeçalho (voltar, Despesas e o perfil em uso, filtros), competência, lista, total, barra inferior e painel inferior |
| `web/src/css/despesas-mobile.css` (novo) | regras restritas a `body.mob-despesas` |
| `web/src/js/despesas-mobile.js` (novo) | lista, accordion, detalhes, operações e filtros, só pelo serviço comum (nenhuma consulta própria ao banco) |
| `web/src/css/mobile-base.css` (novo) | estrutura comum das páginas mobile (corpo, cabeçalho, competência, barra, menu do Mais), retirada de `inicio-mobile.css` sem alterar nenhuma regra (43 = 43 conferidas) e restrita a `body.mob` |
| `web/src/js/mobile-comum.js` (novo) | competência, módulos ativos (`MODULOS_ATIVOS = ['resumo']`), links da barra e menu do Mais, retirados de `inicio-mobile.js` |
| `web/src/inicio.html`, `css/inicio-mobile.css`, `js/inicio-mobile.js` | passam a usar as partes comuns; o atalho Resumo e o Resumo da barra apontam para `despesas-mobile.html` |
| `web/src/js/sessao.js` | `despesas-mobile.html` entre as páginas permitidas |
| `tests/supabase_local.py`, `web/tests/e2e/run_e2e.py` | usuário F e "Perfil F (fictício)", só deste cenário (ver seção 5) |
| testes | `web/tests/unit/despesas-grupos.test.mjs` (novo), `build.test.mjs`, `web/tests/e2e/mob01_despesas.spec.mjs` (novo), `mob08_inicio.spec.mjs` |
| `scripts/homologacao_real/lote_real.py` | os dois arquivos novos que citam rotas `/api/` entre as rotas locais |

**Não muda:** a tela do desktop (HTML, CSS, `js/original/despesas.js`, `js/despesas-adaptacoes.js`), as regras de negócio, o banco, as migrations e a CSP. A pré-visualização da página principal ficou idêntica pixel a pixel (seção 4).

## 3. Comportamento

- **Acesso:** Resumo (atalho e barra) abre `despesas-mobile.html?mes=<competência da página principal>`. Voltar, Início e a seta da barra levam de volta com o mês em uso. Os outros atalhos e o Lançar seguem desabilitados.
- **Competência:** as setas trocam o mês e relêem a lista; o mês fica no endereço, de modo que atualizar a página o mantém e as duas páginas ficam sincronizadas. Ao abrir o mês, as recorrências que faltam são geradas, como no desktop.
- **Grupos:** os do desktop, recolhidos ao abrir, com nome, total e seta. Tocar expande ou recolhe; vários podem ficar abertos. Depois de uma operação, os grupos abertos continuam abertos.
- **Linha:** descrição | valor | seta. A descrição longa é cortada sem empurrar o valor. Abaixo da descrição aparece o vencimento, discreto ("Venc. 15/04"), com "· paga" quando já foi paga. Categoria, Status e a primeira Data não aparecem; o banco e o desktop não mudam.
- **Recorrência semanal:** uma linha por recorrência no mês ("Diarista F", "3/5 pagas"), como no desktop. O toque abre as ocorrências, cada uma com os seus detalhes, e "Pagar pendentes (N)" quando há pendentes.
- **Detalhes (painel inferior):** valor, vencimento, competência, situação (com a data do pagamento), previsto e executado (fatura), forma de pagamento, conta bancária (quando vinculada), categoria, recorrência, parcela e observações.
- **Ações:**

  | Linha | Ações |
  |---|---|
  | Despesa pendente | Pagar, Editar, Excluir |
  | Despesa paga | Estornar pagamento, Editar, Excluir |
  | Fatura pendente | Pagar fatura |
  | Fatura paga | Estornar pagamento |

  O banco confere tudo de novo e a recusa aparece no painel com o motivo (por exemplo, "Esta despesa não pode ser editada…" numa despesa paga). Num perfil só de leitura, nenhuma ação aparece.
- **Pagamento:** data (hoje, em Brasília), conta bancária (fixa quando a despesa já tem conta vinculada), "Valor total" ou "Pagar outro valor". A diferença exige classificação (juros, desconto ou ajuste) e justificativa. Na fatura, o executado consolidado é o valor sugerido e vem com a nota da parte prevista.
- **Estorno:** data e motivo obrigatório; o pagamento original não é apagado.
- **Edição:** nome, valor, vencimento, competência, categoria e observações. Numa recorrência, competência e categoria ficam bloqueadas, com o aviso de que mudam na tela Recorrências. Parcela de consórcio: só valor e vencimento, desta ou desta e das futuras. Pagamento integralmente estornado: só "Cancelar obrigação".
- **Exclusão:** sempre com confirmação. Recorrente: "Excluir somente esta" ou "Excluir esta e as futuras". A segunda mostra antes a prévia do banco e fica desabilitada, com o motivo, quando não é possível. Com pagamento estornado, a ação vira "Cancelar obrigação".
- **Filtros (painel):** status, forma de pagamento, vencimento até e busca. Um ponto no ícone indica filtro ativo. No desktop a busca substitui os demais filtros; aqui valem juntos.
- **Total:** ao final, o total e "Pendentes · Pagas" da lista mostrada, com os mesmos valores dos cartões de resumo do desktop.

## 4. Testes por impacto

| Nível | Selecionados | Resultado |
|---|---|---|
| Unitários (`web`) | todos. Novos: `despesas-grupos.test.mjs` (o arquivo original do desktop numa VM, com 12 despesas fictícias dos 5 grupos: grupos, ordem, valores, agrupadores semanais, totais, 13 combinações de filtro, busca, forma de pagamento e textos) e o teste do build da página mobile (fora da moldura, CSS restrito, só o serviço comum, serviço sem DOM). A lista de funções de escrita por arquivo passa de `despesas-adaptador.js` para `despesas-servico.js`, sem função nova | 99/99 |
| E2E `mob01_despesas` | 7 testes com o usuário F: navegação e competência; grupos, linhas, valores e totais iguais ao desktop no mesmo banco; accordion; colunas; alinhamento; 320 a 430 px sem rolagem horizontal; detalhes e pagamento (conta e justificativa exigidas; um pagamento só no banco, com valor, ajuste e conta); estorno; edição e exclusão recusadas na despesa paga; cancelamento da obrigação; exclusão; edição; recorrente bloqueada; "esta e as futuras" com prévia; lote semanal; filtros; perfil só de leitura (usuário A, Empresa). Sem erro de CSP ou de JS e sem pedido a `/api/` | 7/7 |
| E2E regressão afetada | os specs que operam a tela Despesas do desktop (o adaptador mudou de forma) e os mobile: `acesso`, `pendencia`, `documentos_financeiro_tela`, `cartoes_tela`, `categorias_tela`, `consorcios_p24`, `contas`, `contratos_pagamento`, `despesas`, `despesas_cancelamento`, `despesas_pagamento_lote`, `fatura_agrupamento`, `fatura_executado`, `importar_creditos`, `migracao_p0p1`, `mob01_despesas`, `mob08_inicio`, `moldura`, `movimentacoes`, `perfis`, `perfis_gestao`, `receitas_dispensadas`, `receitas_saldo`, `recorrencia`, `recorrencias_inativacao`, `recorrencias_tela` | 111 aprovados e 3 reprovados (`recorrencia:262`, `recorrencias_inativacao`, `recorrencias_tela:115`). Com o MOB-08 e o MOB-01 depois dos ajustes: 15/15. As 3 falhas são anteriores e não vêm desta mudança: a mesma lista no commit base `65bada2` (sem o MOB-01) também falha nesses 3 specs (106 aprovados, 3 reprovados). Rodados sozinhos, `recorrencias_inativacao` e `recorrencias_tela` passam nos dois commits (dependem da ordem dos specs); `recorrencia:262` falha nos dois ("Despesa e todas as futuras foram excluídas" esperado, "Despesa excluída" recebido). Fica registrado como pendência à parte. |
| Página principal (MOB-08) | capturas antes e depois da troca para o CSS comum, comparadas pixel a pixel | 6 de 6 idênticas (320, 360 e 390 px, menu Mais, desktop e início no desktop) |

Dispensados: testes de banco e a regressão financeira completa. Não há mudança de funções, tabelas ou migrations, e as telas que não passam pela lista de Despesas não mudaram.

## 5. Ambiente de teste e pré-visualização

- **Usuário F** (`usuario.f@teste.local`, senha fictícia só do ambiente local): titular do "Perfil F (fictício)", com gerador NOVO, duas contas bancárias e três recorrências a partir de 04/2031 ("Diarista F" semanal às terças, "Aluguel F" em boleto e "Internet F" em débito automático). Como o perfil é só dele, pagamentos e estornos não mudam saldos nem listas que outros specs conferem.
- **Pré-visualização:**
  1. Subir o ambiente:
     ```
     set POSTGREST_BIN=C:\Users\heyds\AppData\Local\cf-e2e\postgrest\postgrest.exe
     venv\Scripts\python.exe web\tests\e2e\run_e2e.py --previa
     ```
  2. Entrar com o usuário F e abrir a página `despesas-mobile.html?mes=2031-04`, ou partir da página principal e tocar em Resumo.
  3. As despesas avulsas não vêm prontas: dá para criá-las na tela do desktop, no mesmo ambiente.
  4. O banco é descartável e recriado a cada vez.

## 6. Decisões para o titular

| Ponto | Implementado | Alternativa |
|---|---|---|
| Situação na linha | "· paga" ao lado do vencimento, discreto, sem coluna | sem nenhuma indicação (o valor fica cinza na paga) |
| Perfil em uso | nome do perfil abaixo de "Despesas" (o perfil é o mesmo do desktop) | sem o nome |
| Compras da fatura | fora desta etapa (a fatura mostra previsto, executado, pagar e estornar) | a lista de compras entra no MVP mobile de Cartões |
| Nova despesa | fora do escopo (o contrato pede consulta, pagamento, edição e demais operações existentes) | atalho "Despesa" num próximo MVP |
| Busca com os filtros | valem juntos | como no desktop, a busca substitui os filtros |

## 7. Pendências

- Homologação visual e funcional do titular no Firefox, pela pré-visualização.
- Publicação (push e deploy) só depois da aprovação, junto com o MOB-08.
- Nome das próximas etapas mobile (seção inicial).
- À parte deste MVP: as 3 falhas antigas de recorrência na regressão do desktop (seção 4), que já existiam no commit base.
