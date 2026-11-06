# MVP-FIN-AJUSTES-01 — Correções e simplificação da interface

**Situação (05/11/2026): `FIN_MVP_AJUSTES_01_PUBLICADO`.** Publicado no FIN-MVP-AJUSTES-01-PUBLICACAO: push `a1eebb1..f3ade96`, deploy `633a6b90` (produção, commit `f3ade96`), sem migration (55 aplicadas) e sem nenhuma alteração de dados.

Contrato: FIN-MVP-AJUSTES-01 (11 pendências em quatro telas). Commits por módulo: Faturas, Recorrências, Despesas e Cartões.

## 1. Faturas de cartão (detalhe em Despesas)

| Pendência | Resultado |
|---|---|
| **P01** | A linha da despesa fixa mostra o valor definido na recorrência antes da cobrança, em itálico e cinza, com "Previsto · aguardando cobrança". Antes mostrava R$ 0,00. O subtotal continua separando o executado do que aguarda cobrança. O executado não muda |
| **P02** | O cabeçalho direito de Despesas por Categoria passa a "Executado", porque a coluna da direita é o executado. "Consolidado" foi evitado: no sistema, significa fatura fechada. As setas viraram "Saldo R$ X", "Excedente R$ X" ou "No limite". Valores e cálculos preservados |
| **P03** | Auditoria e correção (seção 2) |
| **P04** | Linha única DATA, DESCRIÇÃO e VALOR, com 30 px (categorias 32 px), em todos os blocos e também em tela estreita. A legenda fica ao lado da descrição e o texto inteiro no título da linha. A descrição agora é escapada |

## 2. Auditoria dos totais (P03)

O detalhe calcula o previsto na tela, e o banco calcula o da lista (`contas_do_mes`). As duas fórmulas foram comparadas nas 16 faturas de 05/2026 a 12/2026 da produção, com as mesmas respostas que a tela recebe.

- **Defeito comprovado:** a tela somava o limite da categoria mesmo com gasto acima dele. O banco e o rodapé do próprio detalhe usam o maior entre limite e gasto.
- **Único caso na produção:** Black 11/2026.

| | Valor |
|---|---|
| Tela antes | R$ 7.827,55 |
| Banco e tela depois | R$ 9.114,84 |
| Diferença | R$ 1.287,29 = excedentes das categorias 57 (R$ 179,22) e 59 (R$ 1.108,07) |

- **Correção:** só a tela. Com ela, as 16 faturas ficam iguais ao banco, e nenhum valor gravado muda.

**Conferido, sem defeito:**
- Parcelada, fixa e categoria: cada compra entra em um bloco só, pela mesma regra do banco (`natureza_da_compra`).
- Fixa conciliada: uma linha só, no previsto e no executado.
- Fixa e parcelada não consomem limite: regra do FIN-CARTAO-DESPESAS-FIXAS-01. Por isso o previsto soma a fixa e o limite inteiro da categoria.
- Previsão sem conciliar ao lado de cobrança real conta nos dois lados até a conciliação. É o caso da Netflix 11/2026, que o titular decidiu não conciliar.

**Ressalva:** limite legado sem perfil entra no previsto da lista, mas não em `fatura_por_categoria`. Só aparece nos dados fictícios de teste: a auditoria não achou o caso na produção. Corrigir exigiria migration, por isso ficou fora.

## 3. Recorrências

- **P05:** o filtro Status abre em Ativas. O filtro novo Competência abre no mês corrente.
  - Mensal: a partir do mês de início.
  - Anual: só no mês do vencimento.
  - Semanal e a cada 2 semanas: quando há ocorrência no mês, pela mesma âncora do banco.
  - Consórcio: dentro do prazo das parcelas.
  - Início futuro nunca é antecipado.
  - Limpar o mês lista todos os cadastros.
  - A lista continua com uma linha por cadastro. Os indicadores, a agenda e a composição não mudam.
- **P06:** sai a coluna Tipo; as larguras foram redistribuídas. O ícone da forma de pagamento, que estava nessa coluna, passou para Frequência.
- **Barra de filtros:** com seis filtros, ela quebra em duas linhas quando não cabem.

## 4. Despesas

- **P07:** Forma de pagamento mostra só o ícone, com título e nome acessível (`role="img"`). A coluna ficou mais estreita.
- **P08:** sai o card Vencendo em 7 dias. Os cinco restantes dividem a largura: uma linha em tela larga, duas a 1366 px.
- **Barra de filtros (FIN-MVP-AJUSTES-01-PUBLICACAO):** a sobreposição a 1366 px foi corrigida com a solução de Recorrências: os filtros quebram em duas linhas, com controles de 130 px. Valores e comportamento dos filtros não mudam.
- **P09:** toda linha tem três ações nas mesmas posições: editar, pagar e estornar. Na fatura e no agrupador semanal, a primeira é a de detalhes. A ação impossível fica visível e desabilitada, com o motivo no título.
  - No Flask, "Consolidar fatura" continua como quarta ação. No novo aplicativo ela não aparece.
  - **Mudança de comportamento:** a ocorrência paga dentro do agrupador semanal passa a oferecer o estorno, pelo mesmo fluxo das demais despesas.

## 5. Cartões

- **P10:** sai o painel Categorias do Cartão Vinculadas. A tabela Fatura por Categoria do Cartão ganha editar limite, desvincular e olho.
  - Desvincular só desativa o vínculo; lançamentos e totais ficam iguais.
  - A categoria desvinculada volta para Categorias disponíveis, e vincular de novo reaproveita o vínculo.
  - Ao vincular, a tabela se atualiza.
  - Grupos sem vínculo (parceladas, fixas, sem categoria) têm editar e desvincular desabilitados.
  - As colunas foram reduzidas: a coluna de ações era cortada a 1366 px.
  - O status do vínculo inativo deixa de aparecer em lista própria: ele só reaparece em Categorias disponíveis.
- **P11:** sai Nova compra da barra, com o modal e o `compra-cartao.js`, que só ela usava. As compras seguem por Importar Cartão, Lançamentos e Recorrências.

**Pendência P14 (fora deste MVP):** recuperar a prévia das parcelas. O modal removido a mostrava antes de gravar, e o formulário de Lançamentos não mostra. A sugestão de fatura pelo fechamento e a confirmação de fatura consolidada existem lá.

## 6. Testes

| Bateria | Resultado |
|---|---|
| Unitários web | 70/70, com os novos de `fatura-blocos` e `recorrencias-competencia` |
| E2E completo | 123/123, com o teste de sobreposição dos filtros de Despesas (falhava antes da correção) |
| Seleção de impacto (nível 2, pytest) | 359/359; a suíte Python inteira não foi rodada |

- **E2E novos:** recorrência prevista, excedente, previsto igual ao da lista e altura das linhas em 1366 e 390 px; filtros de Recorrências; ícone e posições das três ações; editar, desvincular, olho e revincular em Cartões.
- **Compra nova no E2E:** o cenário do fechamento passou para o formulário de Lançamentos; os demais criam a compra pela função do banco.
- **Conferência visual:** as quatro telas capturadas a 1366 e 1920 px, com dados fictícios.
- **As 16 faturas auditadas:** o `calcularTotaisFatura` da tela, sobre as respostas reais, é igual ao previsto e ao executado do banco nas 16.

## 7. Ajustes aceitos pelo titular

- **Estorno na ocorrência semanal paga:** mantido, com as proteções financeiras existentes.
- **Despesas a 1366 px:** a rolagem horizontal da tabela fica aceita provisoriamente. As três ações ficam à direita da rolagem; em 1920 px tudo aparece.
- **Netflix:** continua sem conciliação automática.
- **Limites antigos sem perfil:** não modificados.
- **Cartões:** a tabela Lançamentos da fatura também rola na horizontal, como antes.

## 8. Publicação

Autorizada pelo titular no contrato FIN-MVP-AJUSTES-01-PUBLICACAO, sem homologação manual.

| Etapa | Resultado |
|---|---|
| GitHub | `a1eebb1..f3ade96` em avanço direto, sem force; 24 arquivos não rastreados preservados |
| Migrations | Nenhuma; 55 aplicadas, como antes |
| Build e deploy | Build limpo do `git archive f3ade96`; deploy `633a6b90` no ramo `producao`, com `--commit-hash` |
| Arquivos | 164/164 iguais ao build, com e sem parâmetro de cache (`max-age=0`) |
| Segurança | CSP, X-Frame-Options DENY, nosniff e Referrer-Policy servidos; `http://` → 301 `https://` |
| Navegação sem login | Seis telas levam ao login a 1366 e 1920 px, sem erro de CSP e sem nenhum pedido de escrita |
| Frontend × banco | As 196 RPCs do build existem e são executáveis por `authenticated`; nenhuma por `anon` |
| 16 faturas | O `despesas.js` publicado, sobre as respostas reais, é igual ao previsto e ao executado do banco nas 16 |
| Dados | As 82 tabelas de `public` e `financeiro` iguais antes e depois da publicação; saldos, movimentos e financiamento iguais |

- **Não verificado em produção:** as telas com sessão autenticada. Não há credencial de teste, e as contas reais não foram usadas. A tela autenticada foi conferida no ambiente isolado.
- **Cache residual:** `js/compra-cartao.js`, removido do deploy, ainda responde pelo cache de borda até expirar (até 7 dias). Nenhuma página o carrega.

## 9. Pendências

- **P12 e P13 (Mobilidade):** fora desta publicação.
- **P14:** recuperar a prévia das parcelas (seção 5).
- **Reconstrução de 11/2026 e consolidação das categorias:** seguem aguardando autorização própria.
