# FIN-CATEGORIAS-REORGANIZACAO-01 — Reorganização de categorias e classificação financeira

**Situação: PUBLICADO em 17/11/2026** (seção 16): migration `20261229090000` aplicada (69), reorganização executada e conferida, `main` em `040c3f1`, deploy `ce683825`. Histórico abaixo.

Em 17/11/2026, antes da publicação: Dashboard e Lista de Despesas mobile adaptados (seção 15) e suíte completa aprovada, tudo local.
**Desenvolvimento e ensaio local concluídos** em 16/11/2026, conforme o contrato final de execução: migration
preparada (só funções e uma tabela vazia), roteiro de execução com prévia e reversão, testes e ensaio completo numa cópia fiel da
produção (39/39). **Nada foi gravado em produção**: sem push, sem deploy, sem migration aplicada, nenhuma categoria criada ou
reclassificada. Ramo local `categorias-reorganizacao-01`. A publicação depende de autorização do titular (seção 12).

As seções 1 a 9 registram a primeira entrega (diagnóstico e manifesto); as seções 11 em diante, a entrega final. Onde a primeira
entrega e o contrato final divergem, vale o contrato final: **a categoria "Ajustes de Saldo" não é criada**, os lançamentos 718 e
719 ficam como estão, os consórcios inativos e o empréstimo em Outros não são tocados.

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

## 11. Entrega final — o que foi implementado

### Decisões do contrato final

| Tema | Decisão |
|---|---|
| Categorias novas | Poupança Programada (aporte), Clubes e Associações, Atividades Esportivas e Doações (consumo). **Ajustes de Saldo: cancelada** |
| Reclassificações | itens 463 → Moradia (89), 386 → Atividades Extra-Curriculares (110), 384 → Atividades Esportivas, 464 → Clubes e Associações, 479 → Doações; parcelas dos consórcios 18 e 19 → Poupança Programada; compras 616 → Impostos e Taxas (102), 615 e 614 → Assinaturas (100) |
| Incorporação | Serviços gerais (95) em Manutenção residencial (94), pelo procedimento oficial; Serviços domésticos (93) continua independente |
| Fora do escopo | lançamentos 718 e 719, consórcios inativos, empréstimo em Outros e demais compras de natureza não identificada |
| Natureza gerencial | atributo estruturado no banco, nunca pelo nome |

### Migration `20261229090000` (nenhum dado é alterado por ela)

- `financeiro.categoria_natureza`: natureza gerencial da categoria (`CONSUMO`, `APORTE`, `AJUSTE_TECNICO`,
  `TRANSFERENCIA_INTERNA`, `NAO_DEFINIDO`). Sem linha = `CONSUMO`, como hoje. Tabela própria, sem tocar em `public.categoria` e sem
  chave estrangeira (a incorporação reaponta toda tabela que referencia a categoria).
- `definir_natureza_categoria`, `naturezas_das_categorias`, `natureza_da_categoria` (interna).
- `previa_reclassificacao_categorias`, `reclassificar_categorias`, `reverter_reclassificacao_categorias`: trocam **só**
  `categoria_id` de itens de despesa e de compras de um manifesto. As contas herdam a categoria do item, então nenhuma linha de
  conta, valor, vencimento, pagamento, fatura ou movimento é tocada. Só para quem administra o catálogo e com a escrita do perfil
  dos registros; hash da prévia (concorrência), idempotência pela chave, auditoria em `operacao_catalogo` com a categoria anterior
  de cada registro, e inversa.
- `sugestao_categoria_importacao`: o histórico só vale como sugestão quando a categoria não é de natureza `NAO_DEFINIDO`. Com
  Outros definida assim, ela deixa de se propagar com confiança alta; vale a classificação específica mais recente da mesma
  descrição, se houver; senão, a tela pede a decisão ou usa a categoria que o usuário escolheu para o lote. Palavra-chave continua
  com prioridade; descrição ambígua continua sem categoria definitiva; nenhuma compra antiga muda.
- `indicadores_gerenciais(perfil, mês)`: reparte por natureza exatamente o conjunto que o Dashboard soma em despesas previstas
  (contas que não são fatura, fora as substituídas e as dispensadas, mais as previsões financeiras). O total não muda e nenhuma
  saída some do fluxo. As compras do cartão têm repartição informativa, sem somar de novo com as faturas.
- `poupanca_programada_tela(perfil)`: por contrato com parcelas em categoria de aporte, aporte previsto, pago e a pagar; resgate
  previsto e recebido (só com movimento bancário); **retorno de capital** (até o total dos aportes) separado do **ganho** (o que
  passar). Não cria saldo de investimento nem patrimônio e não altera receitas.

Criação de categorias, incorporação e palavras-chave usam as funções oficiais existentes (`criar_categoria`,
`previa_incorporacao_categoria`, `incorporar_categoria`, `criar_palavra_chave`, `remover_palavra_chave`).

**Telas:** a comparação dos indicadores foi aprovada pelo titular em 17/11/2026 e a apresentação está na seção 15 (linha de
Consumo e Aportes sob o total de saídas, no Dashboard e na Lista de Despesas mobile). Nenhuma soma existente mudou.

### Roteiro `scripts/reorganizar_categorias.py`

- `previa` (sessão somente leitura): confere a identidade de cada registro do plano e das exceções e devolve a impressão
  (SHA-256) do estado.
- `executar --hash <impressão> --confirmo "REORGANIZAR CATEGORIAS"`: uma transação; recusa se o estado mudou desde a prévia.
- `reverter --feito <arquivo> --confirmo "REVERTER CATEGORIAS"`: ordem inversa. A reversão da incorporação 95 → 94 não tem função
  oficial: o roteiro restaura a categoria pela foto guardada na auditoria, rodando como dono do banco.

Ordem da execução: categorias novas; palavras-chave genéricas de 95 desativadas e incorporação em 94; palavras-chave; naturezas;
reclassificação.

### Palavras-chave

- Desativadas: as oito de Serviços gerais (variantes de "serviço", "manutenção", "instalação" e "assistência"); "outros" e
  "diversos" em Outros; "streaming" em Assinaturas e em Entretenimento; "netflix" em Entretenimento.
- Criadas ou reativadas: expressões específicas em Manutenção residencial (higienização de sofá e de estofados, limpeza de
  estofados, manutenção de ar-condicionado, reparo residencial); "netflix" em Assinaturas; "iof" em Impostos e Taxas; os termos das
  categorias novas.
- "instalação", sozinha, não decide categoria. Não há nem foi criado termo de marketplace.

## 12. Validação

| Verificação | Resultado |
|---|---|
| Testes da migration (`tests/test_supabase_categorias_reorganizacao.py`) | 7/7 |
| Ensaio na cópia fiel da produção (`scripts/ensaio_categorias_reorganizacao.py`) | 39/39 |
| Regressão de banco (19 arquivos: categorias, importação, cartões, recorrências, consórcios, financiamentos, Dashboard e integração) | 459 aprovados, 12 pulados, 0 falhas |
| Unitários do frontend | 131/131 (4 novos, da repartição por natureza) |
| Suíte e2e completa | **284/284**, duas execuções completas seguidas em 17/11/2026 (2 testes novos); nenhum teste não executado |

### Falha intermitente de `lancamentos_tela.spec.mjs` (investigada em 17/11/2026)

Na execução de 16/11/2026 o teste não encontrou, por 10 s, a despesa recém-cadastrada na lista depois de limpar o filtro de mês.

- **Não se reproduziu:** 15 execuções isoladas seguidas e duas suítes completas (antes e depois da mudança abaixo), todas aprovadas.
  Na suíte completa o teste leva cerca de 6 s, sem lentidão.
- **Conferido no código:** a despesa é gravada antes de a tela reler a lista; as leituras da tela passam por uma fila única e em
  ordem; não há cache nem paginação. A causa exata daquela ocorrência não foi determinada (o rastro da execução não existe mais).
- **O que mudou:** o teste dependia da ordem entre duas coisas que correm juntas (a releitura automática da lista depois de salvar
  e a limpeza do filtro feita pelo teste). Agora a tela marca cada carga concluída (`#lista-lancamentos[data-cargas]`, só um
  marcador, em `js/lancamentos-adaptacoes.js`) e o teste espera a releitura terminar antes de mexer no filtro. Se a linha faltar de
  novo, a falha passa a trazer o retrato do momento (cargas, filtro, linhas na tela, diálogos e o que o banco tinha).
- Nenhuma regra financeira nem gravação foi alterada.

## 13. Pendências retiradas do escopo (registradas)

1. **FIN-CARTOES-CONCILIACAO-HISTORICA-01:** discriminação das compras agrupadas dos lançamentos 718 e 719, com as faturas físicas.
2. Diferença entre as compras lançadas e o valor pago nas duas faturas dos lançamentos agrupados.
3. Consórcios inativos (11, 12, 15, 16 e 17): parcelas continuam em Outros.
4. Empréstimo em Outros: natureza a esclarecer.
5. Compras de natureza não identificada em Outros: fila de revisão manual.
6. Natureza `TRANSFERENCIA_INTERNA`: disponível, não atribuída a nenhuma categoria.
7. Tela para definir a natureza gerencial de uma categoria: não há; a natureza é gravada pelo roteiro (seção 11).
8. Palavras genéricas restantes ("limpeza", "assinatura", "taxa"): mantidas.

## 14. Plano de publicação (não executado)

1. Conferir que a `main` não mudou e avançar o ramo.
2. Backup `PRE_MIGRATION` (`scripts/backup_rotina.py executar --tipo PRE_MIGRATION --migration 20261229090000`).
3. `scripts/supabase_migrations.py status`, `simular` e `aplicar --versoes 20261229090000` (passa a 69).
4. `scripts/reorganizar_categorias.py previa`: conferir a impressão do estado com a aprovada.
5. `scripts/reorganizar_categorias.py executar --hash <impressão> --confirmo "REORGANIZAR CATEGORIAS" --saida <arquivo privado>`.
6. Conferir: categorias criadas, registros no destino, exceções intactas, saldos e Dashboard iguais.
7. Push do código e deploy do frontend (seção 15), **depois** da migration: a linha de Consumo e Aportes lê duas funções da
   migration. Se o frontend chegar antes, a linha simplesmente não aparece e o restante da tela fica como hoje.
8. Conferir em produção: total de saídas, saldo projetado e demais números do Dashboard iguais aos de antes; a linha soma o total.
9. Reversão do frontend: voltar ao deploy anterior (`a5d1099f`). Reversão dos dados: `reorganizar_categorias.py reverter`;
   depois, se for o caso, `supabase/reversao/20261229090000_*.sql` (recusada enquanto houver natureza gravada ou reclassificação
   não revertida). O frontend novo funciona com ou sem a migration; o antigo não depende dela.

**Nada disso é executado sem autorização expressa do titular.**

## 15. Consumo e Aportes nas telas (aprovado em 17/11/2026)

Estrutura pedida pelo titular: **Consumo** (despesas de consumo, sem aportes), **Aportes** (parcelas de Poupança Programada),
**Total de saídas** (consumo + aportes + outras saídas) e **saldo** preservado pelas regras atuais. A separação é gerencial: as
parcelas dos consórcios continuam no fluxo, nas listas e no total.

| Tela | Antes | Depois |
|---|---|---|
| Dashboard, resumo do fluxo | "Despesas previstas" + valor | "Total de saídas" + **o mesmo valor** e, abaixo, uma linha pequena: `Consumo R$ … · Aportes R$ …` |
| Lista de Despesas mobile, caixa do total | Total; Pendentes · Pagas | o mesmo, e mais uma linha pequena: `Consumo R$ … · Aportes R$ …` |

- **Nada é recalculado.** O total de saídas, o gráfico, o saldo final projetado, os KPIs e os totais da lista continuam vindo das
  mesmas leituras (`dashboard_resumo_tela` e a listagem de Despesas). A linha nova só reparte o total já exibido.
- **Outras saídas:** o que está em categoria de natureza não definida (Outros), ajuste técnico ou transferência interna aparece
  como `· Outras saídas R$ …`, só quando há valor. Consumo + Aportes + Outras saídas = total exibido, ao centavo.
- **Trava:** se a repartição não fechar com o total da tela, ou se a leitura não estiver disponível, a linha não aparece (a tela
  fica como antes). Nunca se mostra uma repartição que não soma o total.
- **Dashboard:** repartição do banco (`indicadores_gerenciais`), o mesmo conjunto de "despesas previstas" (contas que não são
  fatura + previsões). **Lista mobile:** repartição das despesas visíveis (respeita os filtros), pela natureza da categoria de
  cada uma (`naturezas_das_categorias`); as faturas de cartão contam como consumo.
- **Compacto:** uma linha no estilo da que já existe sob "Receitas previstas"; nenhum painel novo; a altura do painel do fluxo
  não muda. No Dashboard em tela estreita a linha cabe sem rolagem horizontal.
- O rótulo "Saldo final projetado" não mudou (é o saldo das contas + receitas − saídas do mês, pela regra atual).

Arquivos: `web/src/js/naturezas.js` (contas, sem banco), `web/src/js/naturezas-servico.js` (duas leituras),
`web/src/js/dashboard-adaptador.js`, `web/src/paginas/dashboard.html`, `web/src/js/despesas-mobile.js`,
`web/src/css/mobile-modulo.css`. Testes: `web/tests/unit/naturezas.test.mjs` e `web/tests/e2e/naturezas_indicadores.spec.mjs`
(marca uma categoria como aporte no banco descartável e confere que só a repartição muda).

## 16. Publicação — 17/11/2026

Autorizada pelo titular, limitada a este contrato, na sequência obrigatória.

| Passo | Resultado |
|---|---|
| 1. Backup pré-migration | `cf-fzjmgekasjrgvmfdkdog-20261117_062526`, íntegro (SHA-256), duas cópias verificadas |
| 2. Manifesto e impressão | 69 operações; impressão do estado em produção igual à do ensaio (prévia somente leitura, antes e depois da migration) |
| 3. Migration | só a `20261229090000`; 68 → 69; conferido que, sozinha, não alterou nenhuma tabela de dados, saldo nem o Dashboard |
| 4. Execução | uma transação: 4 categorias criadas, 1 incorporação (95 em 94), 25 itens (480 contas por herança) e 3 compras reclassificados, 5 naturezas, 13 palavras-chave desativadas e 16 criadas ou reativadas = 67 operações executadas + 2 linhas "não alterar" do manifesto |
| 4. Conferências | 29, nenhuma falha: nenhuma tabela mudou além da coluna de categoria e do catálogo; saldos, totais, pagamentos, faturas, movimentos e Dashboard (nove meses) idênticos; consumo + aportes + outras saídas = total de saídas em todos os meses; exceções intactas; resultado por categoria e indicadores iguais aos do ensaio; importação sem Outros com confiança alta |
| 5. Código | push `7e69f18..040c3f1` na `main` (avanço rápido); deploy Cloudflare `ce683825` |
| 6. Produção | 248/248 arquivos servidos iguais ao build; 20 verificações sem login, nenhuma falha (telas levam ao login, módulo da repartição carrega sob a CSP real, Dashboard servido com "Total de saídas" e "Saldo final projetado", leituras novas recusadas sem sessão) |

Nenhum lançamento financeiro foi criado para testar. Não conferido, por exigir a conta do titular: as telas com sessão real
(Dashboard, lista mobile, Categorias) e uma importação real.

**Reversão:** frontend para o deploy `a5d1099f` (commit `716d06e`); dados com `reorganizar_categorias.py reverter --feito <arquivo
da execução, na pasta privada> --confirmo "REVERTER CATEGORIAS"`; depois, se for o caso,
`supabase/reversao/20261229090000_categorias_reorganizacao_anterior.sql`; último recurso, restauração assistida do backup acima.

Continuam pendentes e fora deste contrato: FIN-CARTOES-CONCILIACAO-HISTORICA-01 (718 e 719 e a diferença das faturas), consórcios
inativos, empréstimo em Outros e compras de natureza não identificada.
