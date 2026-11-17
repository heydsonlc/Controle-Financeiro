# FIN-CATEGORIAS-REORGANIZACAO-01 — Reorganização de categorias e classificação financeira

**Situação:** **primeira entrega (Etapas 1 e 2)** concluída em 16/11/2026: diagnóstico atualizado, manifesto de alterações e proposta
de impacto nos indicadores, para homologação do titular. **Nada foi gravado em produção**: nenhuma categoria criada, nenhuma
reclassificação, nenhuma palavra-chave alterada, nenhuma migration. Ramo local `categorias-reorganizacao-01`, isolado do
FIN-MVP-CADASTRO-UNIFICADO-01.

Origem: FIN-CATEGORIAS-DIAGNOSTICO-01 (retrato de 16/11/2026).

> Este documento não traz valores, descrições de despesas nem nomes de recebedores. Os relatórios com dados individuais ficam só
> na pasta privada do titular, fora do repositório e do frontend:
> `%LOCALAPPDATA%\Kortex\Auditorias\FIN-CATEGORIAS-REORGANIZACAO-01\` (leitura principal: `FIN_CATEGORIAS_REORGANIZACAO_PREVIA.md`).

## 1. Método

1. **Retrato somente leitura** da produção (`extrair.py`): conexão com `default_transaction_read_only=on`, isolamento
   `REPEATABLE READ`, conferência de `transaction_read_only`, colunas sensíveis excluídas e encerramento com rollback.
2. **Análise sem conexão** (`analisar.py`): lê só o arquivo do retrato e gera os relatórios.
3. **Comparação com o retrato do diagnóstico**, linha a linha, tabela por tabela.
4. **Impressão digital do estado relevante** (SHA-256 de categorias, itens e contas afetados, compras afetadas, palavras-chave e
   tudo o que está em Outros). Ela identifica o estado que o titular homologa: se mudar até a execução, a prévia perde a validade e
   é refeita.

## 2. Diagnóstico atualizado (Etapa 1)

- O banco não mudou desde o diagnóstico: as 40 tabelas comparadas estão idênticas.
- 36 categorias, todas ativas, em catálogo compartilhado pelos perfis Pessoal e Empresa. Só o Pessoal tem obrigações e compras.
- Todos os identificadores citados no contrato foram confirmados (itens, compras, contratos e categorias).
- Nenhuma das cinco categorias novas tem nome igual ou equivalente a uma existente.
- 14 categorias continuam sem contas nem compras; permanecem no inventário, com as dependências.

**Como a categoria chega a cada registro:** a conta (obrigação) não tem categoria própria, herda a do item de despesa
(`item_despesa.categoria_id`). A compra de cartão tem a sua (`lancamento_agregado.categoria_id`). Reclassificar um item muda de uma
vez todas as contas dele, pagas e futuras, sem tocar em nenhuma linha de conta, valor, pagamento ou movimento.

## 3. Manifesto (Etapa 2)

Relatórios privados: `09_MANIFESTO_OPERACOES.csv` (uma linha por operação, com os campos da seção 13.1 do contrato) e
`03_MANIFESTO_REGISTROS.csv` (cada registro afetado: 25 itens diretos, 480 contas por herança e 3 compras).

### Fase A — prontas para aprovação

| Operação | Entidade | De → para |
|---|---|---|
| Criar 5 categorias | catálogo | Poupança Programada, Clubes e Associações, Atividades Esportivas, Doações, Ajustes de Saldo |
| Reclassificar | item 463 (financiamento habitacional, 420 contas) | sem categoria → Moradia (89) |
| Reclassificar | item 386 | Outros (107) → Atividades Extra-Curriculares (110) |
| Reclassificar | item 384 | Outros → Atividades Esportivas (nova) |
| Reclassificar | item 464 | Outros → Clubes e Associações (nova) |
| Reclassificar | item 479 | Outros → Doações (nova) |
| Reclassificar | 20 itens de parcela dos contratos de consórcio 18 e 19 | Outros → Poupança Programada (nova) |
| Reclassificar | compra 616 | Outros → Impostos e Taxas (102) |
| Incorporar | categoria 95 (Serviços gerais) | em 94 (Manutenção residencial); 95 não tem contas, compras nem vínculos, só 8 palavras-chave |

### Dependem de confirmação do titular

- Compras 614 e 615 → Assinaturas (100): confirmar que são cobrança de serviço ou assinatura.
- Palavras-chave marcadas (seção 5).

### Ficam como estão

- Compras 718 e 719 ("ajuste de saldo"): natureza a esclarecer (seção 6). A categoria Ajustes de Saldo é criada vazia.
- Fila de revisão manual: 18 compras e 68 itens em Outros sem destino confirmado (`08_FILA_REVISAO_MANUAL.csv`), entre eles as
  parcelas dos cinco contratos de consórcio inativos, que o contrato não inclui.

### O que nenhuma operação toca

Valores, vencimentos, pagamentos, estornos, movimentos bancários, saldos, faturas, parcelamentos, recorrências (frequência,
geração e ocorrências), contratos de consórcio e de financiamento (amortização, juros, seguros, indexadores, cronograma) e
documentos. Só muda o campo de categoria de itens e compras.

## 4. Impacto nos indicadores

- **Por categoria:** os totais mudam entre categorias, como esperado; o total geral é idêntico antes e depois. Outros cai para
  cerca de um terço do que tinha, e o "sem categoria" do financiamento zera. Detalhe por competência nos relatórios privados
  `05_PREVIA_ANTES_DEPOIS_*`.
- **Fase B (proposta):** três leituras do mesmo conjunto de registros, sem alterar nenhum deles:
  - fluxo de caixa, como hoje, com todas as saídas, inclusive aportes; saldos só pelos movimentos;
  - consumo: despesas menos os aportes de Poupança Programada (e menos ajustes técnicos, se algum for confirmado);
  - poupança programada, por contrato: aporte previsto, pago e a pagar, resgate previsto e recebido.
- A marcação de aporte não deve depender do nome da categoria. Proposta: atributo de natureza gerencial na categoria (consumo,
  aporte, ajuste técnico), lido pelos serviços. Exige migration e mudança no Dashboard e em Despesas; fica para a Etapa 4, em banco
  isolado.

### Consórcios

- O resgate dos dois contratos está previsto como receita de contemplação, ainda não recebida. Se entrar inteiro como receita, a
  devolução do capital aparece como ganho. A proposta distingue capital recuperado de ganho.
- A contemplação ocorre antes do fim dos aportes: não se cria saldo de investimento nem patrimônio; mostram-se aportado, recebido
  e a diferença.
- Nada muda nas receitas já previstas nem na P24 nesta entrega.

## 5. Palavras-chave

Relatório privado `04_PALAVRAS_CHAVE.csv`: cada uma das 240 regras com a ação proposta (manter, mover, remover, decidir) e as
regras a criar para as categorias novas.

- Categoria 95: seis regras a remover por serem genéricas ou ambíguas (variantes de "serviço", "manutenção" e "assistência") e
  duas ("instalação") a mover para 94, com decisão do titular.
- Dois termos repetidos em duas categorias (Assinaturas e Entretenimento): decisão do titular.
- "outros" e "diversos" em Outros sugerem a categoria residual por palavra-chave: proposta de remoção.
- As variantes com e sem acento são regras separadas, porque a comparação usa minúsculas, mas não tira acentos.

### Por que Outros se perpetua na importação

`financeiro.sugestao_categoria_importacao` decide nesta ordem: palavra-chave; a categoria do **último lançamento com a mesma
descrição**, com confiança alta; a categoria padrão. Uma descrição classificada em Outros uma vez volta como Outros, com
confiança alta, em toda importação seguinte.

Proposta, a implementar e comparar antes/depois em banco isolado: histórico em Outros não vale como sugestão e a importação pede
a decisão; histórico em categoria específica continua valendo; a escolha confirmada é preservada; nenhum lançamento antigo muda.

## 6. Ajustes de saldo (718 e 719)

Relatório privado `07_AJUSTES_DE_SALDO.csv`. O que os dados mostram:

- são **compras de cartão lançadas à mão** nas faturas de 11/2026, depois de as faturas estarem pagas; não são movimentos
  bancários de conciliação;
- não alteram o valor executado da fatura (o valor pago); participam do total de compras por categoria;
- sem eles, as compras discriminadas ficam abaixo do valor pago; com eles, passam um pouco do valor pago.

Recomendação: não tratá-los como ajuste técnico sem a explicação do titular. Retirá-los do consumo esconderia despesa
efetivamente paga. Ficam em Outros até a decisão.

## 7. Mecanismo de execução (proposta)

- **Criar e incorporar:** funções oficiais existentes (`criar_categoria`, `previa_incorporacao_categoria`,
  `incorporar_categoria`), com foto da origem e hash do estado em `financeiro.operacao_catalogo`.
- **Reclassificar:** não há função oficial que troque só a categoria de um item de financiamento, de uma parcela de consórcio ou de
  uma compra em fatura paga. Proposta: função nova, só de categoria, que recebe o manifesto, confere a impressão digital, grava a
  foto de cada registro, aplica tudo numa transação e registra a operação; e a função inversa. É uma **migration só de funções**,
  a escrever e ensaiar em banco descartável na Etapa 3.
- **Concorrência:** a impressão digital é conferida na execução; se o estado mudou, nada é aplicado.
- **Reversão:** restaurar as categorias pela foto, desfazer a incorporação pelo retrato e excluir as categorias novas sem uso.
  Nenhum pagamento é tocado.
- **Produção:** só depois do ensaio homologado, com backup `PRE_MIGRATION` (FIN-REG-01/02) e autorização específica.

## 8. Decisões pendentes do titular

1. Aprovar as operações da Fase A prontas (seção 3).
2. Confirmar a natureza das compras 614 e 615.
3. Explicar a origem dos ajustes 718 e 719 e decidir o tratamento.
4. Decidir as palavras-chave marcadas.
5. Consórcios inativos: reclassificar o histórico ou manter em Outros.
6. Natureza do empréstimo que está em Outros.
7. Fase B: aceitar o atributo de natureza gerencial na categoria (com migration).

## 9. Próximas etapas

- Etapa 3: migration de funções e ensaio da Fase A em banco descartável (criar, incorporar, reclassificar, conferir dependências,
  validar reversão), com comparação antes/depois de contas, valores, pagamentos, movimentos, saldos, faturas, recorrências,
  consórcios e financiamento.
- Etapa 4: Fase B em banco isolado.
- Etapas 5 e 6: homologação e plano de publicação. **Nada em produção sem autorização expressa.**

## 10. Entregáveis desta entrega

| Entregável do contrato | Onde |
|---|---|
| Inventário atualizado | privado: `02_INVENTARIO_ATUALIZADO.csv`, `01_COMPARACAO_RETRATOS.csv` |
| Manifesto de reorganização | privado: `09_MANIFESTO_OPERACOES.csv`, `03_MANIFESTO_REGISTROS.csv` |
| Prévia antes/depois | privado: `05_PREVIA_ANTES_DEPOIS_POR_COMPETENCIA.csv`, `05_PREVIA_ANTES_DEPOIS_RESUMO.csv` |
| Relatório de palavras-chave | privado: `04_PALAVRAS_CHAVE.csv` |
| Análise de consórcios | privado: `06_CONSORCIOS_18_19.csv` e seção 4 da prévia |
| Análise de ajustes de saldo | privado: `07_AJUSTES_DE_SALDO.csv` e seção 5 da prévia |
| Relatório de testes | ainda não há: os ensaios começam na Etapa 3 |
| Plano de execução e reversão | seção 7 (proposta); roteiro reproduzível depois do ensaio |
