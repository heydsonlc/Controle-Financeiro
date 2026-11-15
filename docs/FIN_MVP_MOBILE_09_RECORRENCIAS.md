# FIN-MVP-MOBILE-09 — Recorrências mobile

**Situação:** implementado no ramo local `mobile-09-recorrencias`. O ramo parte do `mobile-08-pagamentos` (MOBILE-08, homologado em 15/11/2026) e inclui o merge do ícone publicado (`86110e2`). Não houve push, deploy nem migration, nem função nova no banco. Nenhum dado real foi alterado.
**Escopo:** a mensagem de autorização do titular (15/11/2026) dispensou um novo contrato e listou as prioridades: lista de ativas e inativas, cadastro de todas as periodicidades, assinaturas no cartão, edição, desativação preservando o histórico e integração com Despesas, Cartões e Pagamentos. Valem as restrições dos MVPs mobile: sem push, deploy ou migration, sem mudança de regra financeira e reaproveitando os serviços do desktop.
**Publicação:** suspensa. Depois da homologação vêm a regressão integrada e a publicação conjunta com o MOBILE-08, só com autorização.

## 1. Como o desktop funciona

A tela Recorrências do desktop (`recorrencias.html`) roda o script original do Flask (`js/original/recorrencias.js`). As rotas `/api/recorrencias` são respondidas pelo adaptador (`js/recorrencias-adaptador.js`) com as funções do banco:

| Operação | Função do banco | Regras |
|---|---|---|
| Lista | `recorrencias_do_perfil` | ativas e inativas; versão, próximo vencimento, meio, cartão ou conta, gerenciável |
| Cadastro | `criar_despesa` (recorrente); no cartão, `criar_recorrencia_cartao` | mensal, anual, semanal e a cada 2 semanas (`semanal_N_D`); semanal e quinzenal recusadas no cartão; débito automático exige conta; data inicial obrigatória |
| Meio informativo | `definir_meio_pagamento_recorrencia` | boleto, PIX e débito |
| Edição | `editar_recorrencia`; no cartão, `editar_recorrencia_cartao` | conferência de versão; troca entre cartão e outro meio recusada (inativar e cadastrar outra); recorrência de outro módulo recusada |
| Inativar (P22) | `previa_interrupcao_recorrencia` → `interromper_recorrencia` | prévia com a data de efeito, as ocorrências que deixam de ser exigíveis e as protegidas (paga, com movimento, vencida, cobrança real); a confirmação leva a versão e a quantidade da prévia |
| Reativar (P22) | `previa_retomada_recorrencia` → `retomar_recorrencia` | período inativo não gerado; restauração opcional das canceladas pela inativação |
| Consórcios | `consorcios_tela`, `criar/editar/excluir_consorcio`... | ficam na mesma tela do desktop |

As contas e as compras são geradas ao abrir a competência em Despesas. Salvar uma recorrência não gera nada.

## 2. Decisões

1. **Um serviço para as duas telas.** O código do adaptador foi movido sem mudança de regra para `js/recorrencias-servico.js`, conferido por diff: só mudaram o cabeçalho, o aviso e a exportação. O adaptador do desktop passou a fazer apenas três coisas: iniciar a moldura, verificar a permissão e registrar o serviço na ponte. O aviso da última operação vai para quem configurou o serviço: o desktop escreve em `#recorrencias-resultado` e o mobile mostra acima da lista. Os textos são os mesmos.
2. **Situação pela ação própria.** O formulário do desktop tem a caixa "Ativa", mas no mobile a situação muda pelos botões Inativar e Reativar, sempre com a prévia da P22. O formulário não envia `ativo`, então salvar nunca inativa nem reativa nada.
3. **Inativa com "Cancelar ocorrências futuras".** No desktop, o Inativar de uma recorrência já inativa cancela as ocorrências futuras que sobraram. No mobile, essa ação aparece com o nome explícito e abre a mesma prévia.
4. **Consórcios continuam no desktop.** Não aparecem na lista mobile.
5. **Cartão.** No cadastro, Semanal e A cada 2 semanas ficam desabilitadas quando o meio é cartão, e o serviço recusa com a mesma mensagem. Na edição, o meio de uma recorrência no cartão fica travado; nas demais, a opção Cartão fica desabilitada. Em ambos os casos a tela mostra o motivo do desktop.

## 3. Implementação

**Página** `recorrencias-mobile.html`, aberta pelo atalho Recorrências da Página Principal (último atalho que faltava):

- **Cabeçalho:** Voltar | Recorrências (perfil) | "+". O "+" só aparece para quem gere o perfil.
- **Filtros:** Ativas | Inativas | Todas, mais a busca por nome, descrição, categoria ou cartão.
- **Resumo:** Ativas (n de total), Mensal estimado e Próximo vencimento, com as regras dos indicadores do desktop (`valorMensalEstimado`, `obterEventosAgenda`).
- **Lista:** dois grupos, CONTAS A PAGAR e CARTÃO DE CRÉDITO. Cada linha mostra nome, frequência ("Mensal, dia 5", "A cada 2 semanas (quarta-feira)", "Anual (20/12)"), próximo vencimento, meio ou cartão e valor. A inativa aparece discreta.
- **Detalhes:** situação, valor, frequência, dia da semana, data inicial, próximo vencimento, categoria, meio, cartão ou conta e observações. As ações são Editar, Inativar ou Reativar e Cancelar ocorrências futuras. Há também um link para a Lista de Despesas, ou para Cartões no caso do cartão.
- **Formulário:** os campos do desktop, exceto Tipo e Ativa. Os erros aparecem junto ao campo e os valores são aceitos em "1.234,56". A categoria do cartão é resolvida pela categoria da despesa, como no desktop (`resolver_categoria_cartao_tela`).
- **Inativar e Reativar:** as prévias do modal do desktop (`js/interrupcao-recorrencia.js`) em painel inferior, com os mesmos textos e regras: incluir a competência atual, tabela das afetadas e das protegidas, mês da retomada e restauração opcional.
- **Somente leitura:** consulta e detalhes, sem "+" e sem ações. O banco também recusa.

**Serviços reaproveitados:** `recorrencias-servico.js` (novo, extraído do adaptador), `mobile-ui.js`, `mobile-formulario.js` (campo com erro, par, erros do serviço), `receita-formulario.js` (`lerValor`, `valorParaCampo`), `mobile-comum.js`, `perfil.js` e `sessao.js`.

**Arquivos**

- Novos: `web/src/recorrencias-mobile.html`, `web/src/js/recorrencias-mobile.js`, `web/src/css/recorrencias-mobile.css` (regras restritas a `body.mob-recorrencias`), `web/src/js/recorrencias-servico.js`.
- Alterados: `web/src/js/recorrencias-adaptador.js` (só a moldura e o registro do serviço), `web/src/js/mobile-comum.js` (`MODULOS_ATIVOS` com `recorrencias`), `web/src/inicio.html` (destino do atalho), `web/src/js/sessao.js` (página permitida).
- Testes: `web/tests/unit/build.test.mjs` (lista de RPC por arquivo, atalhos, moldura, PWA e teste novo da página), `web/tests/e2e/mob09_recorrencias.spec.mjs` (novo), `mob08_inicio.spec.mjs` e `mob01_despesas.spec.mjs` (os oito atalhos ativos), `tests/supabase_local.py` e `web/tests/e2e/run_e2e.py`. Estes dois semeiam recorrências da prévia, só com `--previa`.

## 4. Testes

- **Unitários:** 119/119.
- **Funcionais** (`mob09_recorrencias.spec`): 12/12. Perfil G, recorrências a partir de 01/2035, período sem outro dado:
  1. atalho, lista, resumo e "+";
  2. cadastro com erros junto ao campo e mensal com boleto gravada como no desktop;
  3. a cada 2 semanas exige o dia e grava `semanal_2_3`;
  4. assinatura no cartão: semanal e quinzenal desabilitadas, cartão obrigatório, gravada pela função do cartão e listada em Cartão de crédito;
  5. edição de valor; Cartão desabilitado para quem não é do cartão; no cartão o meio fica travado e o valor muda pela função do cartão;
  6. inativar: as ocorrências geradas ao abrir 02/2035 aparecem na prévia; Cancelar não grava; confirmar as tira das pendentes (`contas_do_mes`) e preserva o cadastro;
  7. reativar com restauração: as ocorrências voltam ao reabrir a competência em Despesas;
  8. somente leitura, com o banco recusando a inativação;
  9. busca e filtros;
  10. 320, 375 e 430 px sem rolagem lateral.
- **Regressão completa:** 250/0/0 (seção 7).

## 5. Comparação com o desktop

| Desktop | Mobile |
|---|---|
| Indicadores: ativas, valor mensal, próxima geração, categorias | Ativas, mensal estimado, próximo vencimento |
| Agenda do período e composição por categoria | Não incluídas (consulta compacta) |
| Filtros: tipo, situação, competência, frequência, categoria, busca | Situação e busca (a busca cobre nome, categoria e cartão) |
| Tabela: descrição, frequência, próximo vencimento, valor, categoria, situação, ações | Linha compacta e detalhes |
| Formulário com Tipo (recorrência ou consórcio) e Ativa | Só recorrência; situação por Inativar e Reativar |
| Inativar e Reativar com o modal da P22 | As mesmas prévias em painel |
| Consórcios | No desktop |

## 6. Revisão da pendência P23 do MOBILE-08

A correção pontual autorizada para "ocorrências canceladas pela P23 no agrupador semanal da Lista" foi revista antes de mexer no código. A pendência era **improcedente**. Desde a migration 1226 (P23, publicada), `contas_do_mes` deixa a situação `Dispensada` de fora. Assim, a ocorrência cancelada nunca chega à Lista (desktop ou mobile), ao agrupador nem ao lote. O teste `despesas_cancelamento.spec`, que passou na regressão, confirma: depois do cancelamento, o agrupador mostra R$ 500,00 e o lote tem 2 ocorrências. Nenhum código mudou. O registro do MOBILE-08 foi corrigido em `docs/FIN_MVP_MOBILE_08_PAGAMENTOS.md`.

## 7. Regressão

Suíte E2E completa no ramo `mobile-09-recorrencias` (MOBILE-08, ícone e MOBILE-09 juntos): **250 aprovados, 0 reprovados, 0 não executados** (9,0 min). Entram aí as telas do desktop afetadas pela extração do serviço (`recorrencias_tela`, `recorrencias_inativacao`, `recorrencia`, `consorcios_p24`), a Página Principal e a Lista mobile (os oito atalhos ativos), os Pagamentos mobile e o cancelamento da P23. Referência: MOBILE-08 fechou em 238/0/0; os 12 a mais são os cenários novos. O intermitente `lancamentos_tela:60`, visto uma vez no MOBILE-08, passou.

## 8. Pendências

| # | Pendência | Classificação |
|---|---|---|
| 1 | Consórcios só no desktop | Por decisão; MVP próprio, se desejado |
| 2 | Cadastrar uma recorrência já inativa (caixa "Ativa" do desktop) não é oferecido no mobile | Melhoria futura (pouco uso) |
| 3 | Agenda, composição por categoria e filtros de competência, frequência e categoria só no desktop | Melhoria futura |
| 4 | As ocorrências restauradas na reativação voltam ao reabrir a competência em Despesas, regra do banco (`retomar_recorrencia`) | Por desenho, igual ao desktop |

## 9. Homologação no Firefox

Prévia em http://127.0.0.1:8790/__previa__/ com `usuario.g@teste.local` / `Senha-ficticia-G-2026`; tocar em **Recorrências**. O leitor é `usuario.h@teste.local` / `Senha-ficticia-H-2026`.

Só nesta prévia, o Perfil G tem estas recorrências, a partir do mês seguinte:

- Aluguel G (mensal, boleto);
- Energia G (débito automático na Conta G);
- Seguro Residencial G (anual, PIX);
- Assinatura Musica G (cartão Nubank Master G);
- Curso de Inglês G (inativa).

A Diarista G (semanal) e o Streaming G (cartão Itau Visa G) já vinham do cenário.
