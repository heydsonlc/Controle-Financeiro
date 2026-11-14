# FIN-MVP-MOBILE-03: Cartões de Crédito mobile

Terceira etapa da versão mobile, depois da Página Principal (FIN-MVP-MOBILE-01, antes chamada MOB-08) e da Lista de Despesas (FIN-MVP-MOBILE-02, antes chamada MOB-01), as duas aprovadas pelo titular em 14/11/2026. O atalho **Cartões** da página principal mobile abre o cartão escolhido e sua fatura da competência. A tela mostra o resumo da fatura, as compras nos grupos do desktop e os detalhes num painel inferior. Ela também permite pagar e estornar a fatura, editar e excluir compras e gerenciar parcelas futuras. Os registros, os serviços e as regras são os do desktop, sem controle paralelo.

**Situação:** implementado no ramo local `mobile-03-cartoes`, a partir da Lista de Despesas (`57bfb59`). Não houve push, deploy nem migration. A publicação depende da homologação do titular e será avaliada junto com os demais MVPs mobile.

## 1. Análise do desktop (antes de implementar)

| Ponto do contrato | Onde está no desktop | Como o mobile segue |
|---|---|---|
| Cartões e perfis | Tela Cartões (`js/original/cartoes.js` + `js/cartoes-adaptador.js`): `cartoes_da_tela` mostra só os cartões ativos do perfil em uso. Do número, só o final de 4 dígitos (`final_numero`); validade e CVV nunca são guardados (FIN-CARTOES-1) | O seletor lista os mesmos cartões, na mesma ordem, como "nome · final 1234". O primeiro vem selecionado, como no desktop |
| Competência, fechamento e vencimento | A fatura do mês é `conta` com `is_fatura_cartao` e `cartao_competencia`. A tela Cartões lê pelo `mes_fatura` das compras; a tela Despesas mostra a fatura na competência (`contas_do_mes`), com o vencimento da conta | A competência da tela é a competência da fatura; o vencimento é o da fatura em Despesas |
| Compras, parcelas, recorrências e faturas | A natureza vem do banco (`natureza_da_compra`): CATEGORIA, PARCELADA, FIXA (recorrência do cartão), OUTROS e CRÉDITO. A situação da previsão (`situacao_previsao`) e o bloqueio (`bloqueio_da_parcela`: fatura paga ou fechada, gerada por recorrência, crédito vinculado) também vêm de lá | Tudo lido do banco, sem regra recalculada. A linha mostra data, parcela "1/6", "prevista" ou "à vista" e o cartão do contrato |
| Previsto, executado e pagamentos | A tela Despesas mostra Previsto e Executado da fatura (`contas_do_mes`). Executado = compras executadas − créditos. Previsto = executado + o que falta dos limites; na fatura paga, o executado. A tela Cartões mostra "Total da fatura" (= executado) e o consumo por Categoria do Cartão | O cabeçalho mostra exatamente o Previsto, o Executado e o Vencimento da fatura em Despesas, **sem soma própria**. Os créditos aparecem à parte ("Compras R$ 571,30 · créditos −R$ 5,50"), como na métrica do desktop |
| Agrupamentos | "Fatura por Categoria do Cartão" (`fatura_por_categoria`). Ordem: Categorias do Cartão com limite (ordem do vínculo), categorias sem limite, Compras parceladas, Despesas fixas, Sem Categoria do Cartão e Créditos e ajustes, cada uma com o executado. O "Ver lançamentos" de cada grupo filtra as compras (`lancamentos_fatura_por_categoria`) | **Os mesmos grupos e totais, vindos do banco**, em accordion. Cada compra entra no grupo pelo mesmo critério do filtro do desktop. Nenhum grupo artificial |
| Criação, edição e exclusão de compras | Compra nova só em Lançamentos, Importar Cartão e Recorrências (MVP-FIN-AJUSTES-01, P11). Editar (`editar_lancamento_cartao`) muda descrição, valor, data e Categoria de Despesa; parcela e total não mudam e a classificação é regravada. Excluir (`excluir_compra`) tira a compra à vista; na parcelada, as parcelas em fatura aberta, depois de uma segunda confirmação com as quantidades. Abastecimento vinculado: as perguntas do FIN-MOB-ABAST-LANCAMENTOS-01. "Gerenciar parcelamento" altera ou cancela só as parcelas futuras | As mesmas rotas e confirmações (no painel), sem botão de compra nova (fica para o FIN-MVP-MOBILE-06) |
| Pagamento e estorno | Não existem na tela Cartões: a fatura é paga na tela Despesas (`pagar_fatura`). O executado consolidado é o valor sugerido; outro valor pede a diferença classificada e justificada. A chave de idempotência e a conferência do executado (`EXECUTADO_MUDOU`) evitam pagamento duplicado. O estorno (`estornar_pagamento_fatura`) cria o movimento compensatório e reabre a fatura | O mesmo formulário do Despesas mobile e as mesmas funções do serviço de Despesas (nada de pagamento só do mobile) |
| Integração com despesas e movimentações | O pagamento grava o movimento na conta bancária e marca a fatura paga em Despesas; o estorno compensa. Os créditos abatem o valor a pagar | Igual, porque são as mesmas funções. O spec confere no banco: um pagamento vigente, o segundo recusado, e o estorno reabrindo a fatura |

## 2. O que foi feito

| Arquivo | Mudança |
|---|---|
| `web/src/js/cartoes-servico.js` (novo) | O código de `cartoes-adaptador.js`, sem alteração de regra: rotas, tradução de formato, versões, chaves e confirmações. Única diferença: as confirmações (`window.confirm`) passam por um gancho `confirmar(texto)`, que no desktop continua sendo o `window.confirm` |
| `web/src/js/cartoes-adaptador.js` | Fica só com a moldura e o modo somente leitura, e registra `responderCartoes` na ponte, como antes |
| `web/src/js/despesas-servico.js` | Três rotas novas, sem regra nova, só para a fatura fora da lista do mês: `GET /api/faturas?mes_referencia=` (as linhas de fatura de `contas_do_mes`, sem a geração de recorrências que a lista faz; a tela Cartões do desktop também não gera), `POST /api/faturas/{id}/pagar` (o mesmo `pagarFatura`) e `POST /api/faturas/{id}/estornar-pagamento` (o mesmo `estornar`, avisado de que é fatura) |
| `web/src/js/cartoes-grupos.js` (novo) | Regras de leitura puras: grupos do banco, compra no grupo pelo critério do filtro do desktop, filtros do painel, legendas e situações |
| `web/src/cartoes-mobile.html`, `css/cartoes-mobile.css`, `js/cartoes-mobile.js` (novos) | Página fora da moldura com cabeçalho, competência, seletor de cartão, resumo da fatura, lista e painel. CSS restrito a `body.mob-cartoes`. Os dados vêm só pelos dois serviços, sem consulta própria ao banco |
| `web/src/css/mobile-modulo.css` (era `despesas-mobile.css`) | O mesmo texto, com o escopo trocado de `body.mob-despesas` para `body.mob-modulo` (mesma especificidade), para Despesas e Cartões usarem a mesma lista, painel e formulários. As 10 capturas do Despesas mobile ficaram idênticas pixel a pixel |
| `web/src/js/mobile-ui.js`, `js/mobile-pagamento.js` (novos) | Elementos, painel inferior, aviso e o formulário de pagamento/estorno, retirados de `despesas-mobile.js` sem mudança. Os dois módulos usam o mesmo formulário. Única adição: `quandoFechar`, para a confirmação pedida pelo serviço tratar o fechamento do painel como "Cancelar" |
| `web/src/despesas-mobile.html`, `js/despesas-mobile.js` | Passam a usar os módulos comuns (classe `mob-modulo`, `mobile-modulo.css`) |
| `web/src/inicio.html`, `js/mobile-comum.js`, `js/sessao.js` | O atalho Cartões aponta para `cartoes-mobile.html` e entra em `MODULOS_ATIVOS`; a página entra nas permitidas. A barra inferior não muda |
| `tests/supabase_local.py`, `web/tests/e2e/run_e2e.py` | Usuários G (titular) e H (leitor) e o "Perfil G (fictício)", só deste cenário (seção 5) |
| testes | Novos: `web/tests/unit/cartoes-grupos.test.mjs` e `web/tests/e2e/mobile03_cartoes.spec.mjs`. Atualizados: `build.test.mjs`, `mob08_inicio.spec.mjs` e `mob01_despesas.spec.mjs` (agora são dois atalhos habilitados) |
| `scripts/homologacao_real/lote_real.py` | Os arquivos novos que citam rotas `/api/` entram nas rotas locais |

**Não muda:**
- as telas do desktop: HTML, CSS, `js/original/cartoes.js`, `js/cartoes-adaptacoes.js` e Despesas;
- as regras de negócio, o banco, as migrations e a CSP.

## 3. Comportamento

- **Acesso:** o atalho Cartões abre `cartoes-mobile.html?mes=AAAA-MM` na competência da página principal. Início e voltar mantêm o mês. A barra fica igual (Início, Lançar desabilitado, Resumo, Mais).
- **Seletor de cartão:** mostra "nome · final 1234". Trocar de cartão relê a fatura; o cartão fica no endereço (`&cartao=`), e trocar de competência o mantém.
- **Resumo da fatura:**
  - "Fatura Abr/2031" e a situação: Aberta, Fechada, Vencida ou "Paga em dd/mm";
  - Vencimento | Previsto | Executado;
  - a linha de créditos, quando houver;
  - "Pagar fatura", quando a fatura tem compras, ou "Estornar pagamento", quando está paga.
- **Compras:** grupos recolhidos ao abrir, com nome (quantidade), total e seta; vários podem ficar abertos. Nas Categorias do Cartão com limite, uma linha discreta mostra limite e disponível. A linha de compra é descrição | valor | seta, com data, parcela ou previsão e cartão do contrato embaixo. Grupo de categoria sem compra: "Nenhuma compra nesta categoria." Sem compras na competência: "Nenhuma compra nesta competência" (tela 6 do mockup).
- **Detalhe (painel inferior):**
  - campos: descrição, valor, data, cartão (e o cartão do contrato), competência, parcela, recorrência, previsto e executado da despesa fixa, Categoria, Categoria do Cartão, situação da cobrança e o motivo do bloqueio, quando houver;
  - no crédito: o tipo e a compra original, sem ações;
  - ações: Editar (só quando o banco permite), Parcelamento (compra parcelada) e Excluir.
- **Filtros (painel):** cartão do contrato (o "Ver lançamentos" por cartão do desktop, só quando há cartão identificado) e situação ("a revisar": sem Categoria do Cartão ou sem limite; "previstas aguardando cobrança").
- **Depois de cada operação**, a tela relê o resumo, os grupos e as compras.
- **Perfil só leitura:** os mesmos dados, sem nenhuma ação.

## 4. Testes

**Unitários:** 105/105.
- `cartoes-grupos.test.mjs` (5): ordem e totais dos grupos, compra no grupo do filtro, nenhuma compra fora, filtros, textos e situações.
- `build.test.mjs`:
  - novo teste dos Cartões mobile: sem moldura, CSS restrito, dados só pelos serviços, sem botão de compra nova, barra sem item novo;
  - mapa das funções de escrita apontando para `cartoes-servico.js`;
  - testes das páginas mobile anteriores atualizados.

**Funcionais (`mobile03_cartoes.spec.mjs`, 7/7)**, sempre comparando com o banco e com as telas do desktop no mesmo banco:

| Requisito | Conferência |
|---|---|
| Seleção de cartões e competências | Atalho → página na competência; seletor com os cartões ativos e o final; troca de cartão e de mês mantendo o cartão; Início/voltar com o mês |
| Consulta de faturas; previsto e executado iguais ao desktop | Cabeçalho igual a `contas_do_mes`; Executado igual ao "Total da fatura" da tela Cartões; Previsto igual ao valor da linha da fatura na tela Despesas |
| Compras, parcelas e agrupamentos | Grupos, quantidades e totais iguais a `fatura_por_categoria` e à tabela da tela Cartões; as compras de cada grupo iguais ao filtro "Ver lançamentos" (`lancamentos_fatura_por_categoria`) |
| Detalhamento | Parcelada (1 de 6, cartão do contrato), despesa fixa (prevista, sem Editar porque o banco bloqueia) e crédito (compra original, sem ações) |
| Edição permitida | Valor alterado pelo mesmo corpo do desktop; grupo, limite disponível e cabeçalho relidos e iguais ao banco |
| Exclusão | À vista: o grupo some e o executado cai. Parcelada: a segunda confirmação do desktop ("6 parcelas…"); cancelar não exclui nada |
| Parcelas futuras | 6 parcelas; cancelar as 5 futuras mantém a de 04/2031; banco com 0 futuras editáveis |
| Pagamento sem duplicidade | Duplo toque em "Confirmar pagamento" → um pagamento vigente (R$ 565,80); um segundo `pagar_fatura` é recusado; "Paga em dd/mm" e "Estornar pagamento" |
| Estorno | Movimento compensatório; fatura reaberta; o pagamento original continua no histórico |
| Sem rolagem horizontal | 320, 360, 390 e 412 px com todos os grupos abertos |
| Permissões | Usuário leitor: a mesma fatura, sem nenhuma ação |
| Segurança | Nenhuma chamada a `/api/` no servidor, nenhum erro de CSP ou de JS; nunca número completo, validade ou CVV na página |

**Página principal e Lista de Despesas mobile:** `mob08_inicio` e `mob01_despesas` 15/15. As 10 capturas do Despesas mobile e as 6 da página principal ficaram **idênticas pixel a pixel** às de antes da extração dos módulos comuns.

**Regressão por impacto (N3):** 34 specs: tela Despesas e faturas, Cartões (tela, múltiplos), importações de cartão (CSV, parceladas, fixas, créditos), lançamentos com abastecimento e parcelas, recorrências, receitas, perfis, acesso, moldura e as três páginas mobile. **133 aprovados, 3 reprovados, 9 não rodaram** (dependentes, no modo serial). As 3 reprovações são **preexistentes**, com as mesmas mensagens da base `65bada2`, anterior a todo o trabalho mobile (FIN-MVP-MOB-01, seção 4): `recorrencia.spec:262` ("Despesa e todas as futuras foram excluídas"), `recorrencias_inativacao` e `recorrencias_tela:115`. **Nenhuma falha introduzida por este MVP.** As falhas de recorrência continuam como pendência à parte.

## 5. Ambiente e dados

- **Banco descartável local** (`run_e2e.py`). Nenhuma escrita em produção; nenhuma migration.
- **Usuário G (`usuario.g@teste.local`):** titular do "Perfil G (fictício)" (id 160, gerador NOVO), com "Conta G (fictícia)".
  - "Visa G" (fechamento 10, vencimento 20, final 1234):
    - limites de Mercado G (R$ 500) e Viagem G (R$ 300); Restaurantes G com o limite desativado depois da compra;
    - compras de 04/2031: Mercado Online G R$ 240,00; Loja Eletrônicos G R$ 540,00 em 6x; Padaria G R$ 35,50; Restaurante Centro G R$ 120,00; Farmácia G R$ 45,90 (sem Categoria do Cartão);
    - despesa fixa Streaming G R$ 39,90, prevista e gerada pelo gerador do mês.
  - "Master G" (vencimento 25, final 5678): sem compras.
  - Executado R$ 565,80 e previsto R$ 1.090,30.
  - Tudo isso foi criado pelas funções oficiais, como o usuário G. Os cartões do contrato (físico 1234, virtual 9876), o final dos contratos e um estorno parcial de R$ 5,50 da padaria foram gravados como a importação grava, só no banco descartável.
- **Usuário H (`usuario.h@teste.local`):** leitor do Perfil G.
- Os usuários A a F e seus perfis não mudam (os cenários aprovados continuam iguais).

## 6. Decisões e limitações (para o titular)

1. **Grupos:** são os da tela Cartões do desktop ("Fatura por Categoria do Cartão"), não os blocos do detalhe da fatura em Despesas. São os mesmos dados agrupados de outra forma: aqui as compras parceladas e as fixas também ficam em grupo próprio. Os nomes fixos que o banco grava sem acento aparecem acentuados ("Sem Categoria do Cartão", "Créditos e ajustes").
2. **Limite na linha do grupo:** só nas Categorias do Cartão com limite ("Limite R$ 500,00 · disponível R$ 224,50"). Sem gráfico nem percentual.
3. **Primeiro cartão:** como no desktop, abre o primeiro da lista (ordem alfabética); a escolha fica no endereço. No mockup, o Visa aparecia primeiro só por exemplo.
4. **"Pagar fatura" só com compras:** fatura vazia (R$ 0,00) não mostra o botão, porque o banco não paga fatura sem compras.
5. **Editar regrava a classificação** (regra do banco, igual no desktop): uma compra de categoria cujo limite foi desativado vai para "Sem Categoria do Cartão" ao ser editada.
6. **Despesa fixa ainda não gerada:** a tela Cartões, mobile ou desktop, não gera recorrências. A previsão do mês aparece depois que a competência é aberta em Despesas, como hoje no desktop.
7. **Botão "Parcelamento":** a segunda confirmação da exclusão usa o texto do desktop ("use Gerenciar parcelamento"); no celular, o botão se chama "Parcelamento" para caber ao lado de Editar e Excluir.
8. **Sem compra nova:** a inclusão fica para o FIN-MVP-MOBILE-06.

## 7. Homologação no Firefox

1. Prévia: `run_e2e.py --previa` → http://127.0.0.1:8790/__previa__/.
2. Entrar com `usuario.g@teste.local` / `Senha-ficticia-G-2026`. Na página principal, ir a Abr/2031 e tocar em **Cartões**, ou abrir `cartoes-mobile.html?mes=2031-04`.
3. Escolher "Visa G (ficticio) · final 1234". Conferir o resumo, abrir os grupos, tocar nas compras, usar os filtros, pagar e estornar a fatura, editar e excluir compras e abrir o parcelamento da Loja Eletrônicos G.
4. "Master G": cartão sem compras. Somente leitura: `usuario.h@teste.local` / `Senha-ficticia-H-2026`.
5. O banco é recriado a cada vez que a prévia sobe.
