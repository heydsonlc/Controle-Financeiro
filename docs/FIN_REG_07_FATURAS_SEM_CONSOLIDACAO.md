# FIN-REG-07 — Simplificação do fluxo de faturas: retirada da consolidação manual

**Data:** 15/11/2026. **Situação:** alteração local feita, testada e **tecnicamente homologada** (regressão completa sem falhas). Falta só a publicação, que depende de autorização específica. Sem migration, sem push e sem deploy.

**Classificação:** funcionalidade **dispensada por decisão do titular**. Não é pendência de migração.

## 1. Decisão

O titular importa a fatura já consolidada pela administradora do cartão. Não há necessidade de um mecanismo adicional de fechamento dentro do Controle Financeiro. A consolidação manual de faturas fica retirada, e nenhum novo mecanismo de fechamento será desenvolvido.

## 2. O que existia

| Onde | O que havia |
|---|---|
| Flask | Botão "Consolidar fatura" na linha da fatura em aberto, em Despesas, e a rota `POST /api/cartoes/<id>/faturas/<mês>/consolidar`, que marcava a fatura como "FECHADA" |
| Novo aplicativo, tela de Despesas | O código da tela original, reaproveitado sem alteração, ainda contém o desenho do botão. **Na prática ele não aparecia:** a tela só o desenha quando a linha traz a situação "ABERTA", e o novo aplicativo nunca enviou essa informação para a lista |
| Novo aplicativo, serviço de Despesas | Uma rota que respondia "em migração" para a consolidação. Era o único resto ativo |
| Banco | Nenhuma função do novo aplicativo grava "FECHADA". O banco só lê faturas que já estejam fechadas |

**Correção de um registro anterior.** O plano de regularização da auditoria dizia: "hoje o botão em Despesas responde 'não disponível'". A frase estava imprecisa. O que respondia "não disponível" era a rota; o botão não chegava a ser desenhado. Conferi no código e no navegador, e corrigi o texto do plano e da matriz.

Não há botão de consolidar ou fechar fatura em nenhuma outra tela: Cartões, Importar Cartão, Dashboard e as telas do celular não têm esse controle.

## 3. O que foi alterado

| Arquivo | Mudança |
|---|---|
| `web/src/js/despesas-adaptacoes.js` | Trava: qualquer botão "Consolidar fatura" que a tela original venha a desenhar na lista é retirado na hora. Nenhum controle entra no lugar |
| `web/src/js/despesas-servico.js` | Saiu a rota de consolidação que respondia "em migração". Uma chamada a esse endereço recebe agora a recusa genérica do serviço, sem gravar nada |
| `web/tests/e2e/fatura_executado.spec.mjs` | Conferências novas (seção 5) |

**Por que uma trava, se o botão já não aparecia?** A tela original não é alterada (regra do projeto), então o desenho do botão continua dentro dela. Sem a trava, ele voltaria a aparecer no dia em que a lista passasse a informar a situação da fatura. Com a trava, a decisão fica garantida e testada. São seis linhas.

**Decisão do titular (15/11/2026): manter a trava preventiva**, restrita ao botão de consolidação de fatura, e manter a retirada da rota inoperante. A trava só procura esse botão, pelo marcador que a tela original usa para ele, dentro da lista de despesas; não toca em nenhum outro controle nem na lógica financeira.

## 4. O que foi preservado

- Importação de faturas, compras parceladas e créditos.
- Recorrências no cartão e despesas fixas.
- Valores previstos e executados, e o "executado consolidado" usado como valor sugerido do pagamento. Esse termo descreve a soma das compras e parcelas da fatura; não tem relação com o botão retirado.
- Pagamento e estorno de faturas, inclusive pelo celular.
- O aviso "fatura consolidada" ao incluir uma compra numa fatura que já esteja marcada como fechada. É leitura de uma situação que pode existir em dados antigos; não fecha fatura.
- "Consolidar Receita", em Receitas. É outra funcionalidade (registrar o recebimento) e não foi tocada.
- Regras de cálculo, lançamentos e saldos: nenhuma alteração.
- Banco: nenhuma tabela, coluna ou função excluída ou alterada. A coluna de situação da fatura continua existindo.

## 5. Testes

| Bateria | Selecionada por | Resultado |
|---|---|---|
| `fatura_executado.spec.mjs`, com as conferências do REG-07 | Alteração | 1 aprovado, 0 falhas |
| Unitários do site, com o build de produção | Regressão | 120 aprovados, 0 falhas |
| Suíte completa de navegador (Despesas, Cartões, Importação, Pagamentos e as demais) | Regressão | 260 aprovados, 0 falhas |

Conferências do REG-07, na tela de Despesas com uma fatura em aberto:

1. Nenhum botão "Consolidar fatura" na lista, por marcador, por título e por rótulo acessível.
2. A linha da fatura tem só os três controles de sempre: ver detalhes, pagar e estornar.
3. A trava funciona: um botão com o mesmo marcador da tela original, inserido na lista, é retirado na hora.
4. O endereço da consolidação recebe a recusa genérica (501), sem gravar nada.
5. O restante do cenário continua igual: valores previsto e executado, Dashboard, pagamento e estorno da fatura.

## 6. Publicação e reversão

- **Publicação:** só o site, dois arquivos de `web/src/js`. Sem migration. Depende de autorização específica do titular; o push e o deploy não foram autorizados nesta etapa.
- **Reversão:** republicar o deploy anterior do Cloudflare Pages (`5c392a8a`). Não há mudança no banco.

## 7. Limpeza futura (não autorizada nesta etapa)

Ficam para uma decisão posterior, se o titular quiser:

- A coluna de situação da fatura e as leituras de "fatura fechada" no banco.
- A função `consolidarFatura` dentro da tela original, que ficou sem uso.
- As confirmações de inclusão em fatura consolidada, se não houver nenhuma fatura marcada como fechada nos dados reais.

## 8. Conclusão

- **Decisão funcional encerrada:** o Controle Financeiro não usa consolidação manual de faturas.
- **Homologação técnica:** regressão completa aprovada, 260 de 260, e unitários 120 de 120.
- **Commits locais:** `1602ea6` (código e teste) e o desta documentação, no ramo `reg-07-retirar-consolidacao-fatura`.
- **Pendente:** publicação (push e deploy), quando autorizada.

