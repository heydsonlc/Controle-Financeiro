# Mapa dos Módulos do Sistema

Visão consolidada de todos os módulos do Controle Financeiro, com estado atual, função principal e observações relevantes.

Última atualização: 2026-05-10

---

## Visão Geral

| Módulo | Situação | Função principal | Observações |
|--------|----------|-----------------|-------------|
| Dashboard | Funcional / Em evolução | Visão consolidada da vida financeira | Cards, gráficos, alertas e agenda; sem elementos estáticos |
| Receitas | Funcional | Controle de receitas previstas e realizadas | Pendências antigas visíveis até confirmação; competência original preservada |
| Despesas | Funcional | Fatura mensal consolidada | Tela principal do sistema; preservada de redesenhos; prioridade mobile futura |
| Cartões | Funcional / Em evolução | Faturas, categorias e lançamentos | Categoria do Cartão separada de Categoria da Despesa |
| Importação de Cartão | Funcional / Em evolução | Triagem e conversão de lançamentos CSV/XLSX/PDF | Descrição original preservada; reconhecimento restrito ao mesmo cartão |
| Recorrências | Funcional / Em evolução | Despesas recorrentes e recorrentes com prazo | Tela própria `/recorrencias`; débito automático vinculável |
| Consórcios | Funcional | Contemplação e receitas pendentes | Tipo especial de recorrência; integrado com Receitas |
| Financiamentos | Em evolução avançada | Cronograma, seguro, saldo, amortização | SAC/PRICE/SIMPLES/CAIXA SAC com TR; exclusão segura; ajuste de saldo real |
| Veículos / Mobilidade | Funcional / Em evolução | Comparação de custos de transporte e efetivação de despesas | 3 cenários: veículo próprio, assinatura, app; categoria padrão Mobilidade |
| Contas Bancárias | Funcional | Saldo operacional e movimentações | Saldo derivado de MovimentoFinanceiro; nunca editado diretamente |
| Patrimônio | Funcional | Alocação de patrimônio em caixinhas | Separado de Contas Bancárias; caixinhas com metas e transferências |
| Lançamentos | Funcional | Entrada unificada de lançamentos | Cartão, direto, crédito; painel único com histórico |
| Categorias | Funcional | Agrupamento de despesas com ícone e cor | Global por usuário; seletor visual de ícones; upload de logo |
| Documentos / Fiscal | Funcional (parcial) | Central documental empresarial | Cupom fiscal, pacote para contador, alertas de validade; IR futuro |
| Configurações | Parcial / Enxuta | Preferências e parâmetros globais | Módulos operacionais removidos; acesso via sidebar |
| Indexadores | Funcional | TR, IPCA, IGP-M, CDI, SELIC por competência | 419+ registros TR históricos (1991–2025); obrigatório para CAIXA SAC/TR |
| Perfis Financeiros | Futuro | Contextos alternáveis pessoal/empresa | Diagnóstico CTX-FIN-1 planejado |
| Imposto de Renda | Futuro | Documentos fiscais IRPF por contexto | Evolução após módulo Documentos/Fiscal |

---

## Módulo: Dashboard

**Rota**: `/`
**Status**: Funcional, em evolução

Exibe:
- Cards de resumo financeiro (receitas, despesas, cartões, saldo)
- Gráficos de distribuição por categoria
- Fluxo de caixa mensal
- Alertas e agenda financeira (compromissos próximos)
- Leitura do mês corrente e indicadores

**Princípio**: todos os dados são reais, sem cards mockados. Alertas descritivos, sem julgamento moral.

---

## Módulo: Receitas

**Rota**: `/receitas`
**Status**: Funcional

Controla:
- Fontes de receita (salário, aluguel, freelance, etc.)
- Receitas previstas (`ReceitaOrcamento`) por competência
- Receitas realizadas (`ReceitaRealizada`) com efetivação
- Pendências abertas: receitas previstas de competências anteriores não efetivadas
- Painel "Recebimentos pendentes" com filtro por intervalo de competência

**Regras importantes**:
- Pendências antigas permanecem visíveis até confirmação
- Confirmação preserva a competência original, não usa a data atual
- Receita prevista ≠ receita realizada (valor realizado fica zerado até efetivação)
- Contemplação de consórcio sem conta bancária aparece como receita prevista

---

## Módulo: Despesas

**Rota**: `/despesas`
**Status**: Funcional — tela principal do sistema

Representa a **fatura mensal consolidada** da vida financeira. É a manifestação da Regra-Mãe do sistema.

Exibe:
- Todas as `Conta` da competência selecionada
- Faturas de cartão (consolidadas por cartão)
- Parcelas de financiamento
- Despesas correntes e recorrentes

**Regras imutáveis**:
- Conta paga → usa `total_executado`
- Conta pendente → usa `total_previsto`
- Competência sempre definida explicitamente (nunca inferida de datas de transação)
- Despesas recorrentes com prazo são o termo oficial (não "recorrência parcelada")

**UX**:
- Forma de pagamento exibida como ícone (sem texto)
- Tela preservada de redesenhos; ajuste mobile futuro será leve e estrutural

---

## Módulo: Cartões de Crédito

**Rota**: `/cartoes`
**Status**: Funcional / Em evolução

Controla:
- Cadastro de cartões (`ItemDespesa` com `tipo='Agregador'`)
- Faturas mensais por cartão
- Lançamentos da fatura (`LancamentoAgregado`)
- Categoria do Cartão (`CategoriaCartao`): organiza a fatura internamente
- Limite por Categoria do Cartão (status: Normal / Atenção / Estourado / Revisar)
- Gerenciamento de parcelamento de lançamento

**Distinção fundamental**:
- **Categoria do Cartão**: organiza a fatura (ex.: Alimentação do cartão, Lazer do cartão)
- **Categoria da Despesa**: organiza o orçamento e o fluxo de despesas

**Lançamentos sem Categoria do Cartão** aparecem em seção separada ("Sem Categoria do Cartão").

**Evolução recente**:
- Substituição do modelo legado `ItemAgregado` por `CategoriaCartao` global com tabelas de vínculo
- Tabela de lançamentos reformada: uma linha por lançamento, ícones de ação, sem origem/pdf
- Parcelamento gerenciável diretamente da fatura

---

## Módulo: Importação de Cartão

**Rota**: `/importar-cartao`
**Status**: Funcional / Em evolução

Fluxo:
1. Upload de arquivo (CSV, XLSX, PDF)
2. Análise pelo motor unificado (`POST /api/importacao-cartao/analisar`)
3. Triagem: decidir se cada lançamento vira despesa ou não
4. Classificação: Categoria da Despesa e Categoria do Cartão (obrigatória)
5. Revisão e confirmação → `LancamentoAgregado`

**Regras técnicas**:
- `descricao_original` — texto bruto do arquivo (imutável após importação)
- `descricao_original_normalizada` — sem parcelamento (NN/TT)
- `descricao_exibida` — editável pelo usuário
- `is_importado` — flag de origem
- Idempotência via `compra_id` (UUID v4) + `numero_parcela`
- Reconhecimento de recorrência exige **mesmo cartão** (lançamentos de outro cartão não sugerem recorrência)
- Vínculo a recorrência existente disponível na triagem

**Regra de assinatura de reconhecimento**:
- Usa descrição original + valor + cartão/competência
- Não depende apenas da descrição amigável (editável)
- Exemplo: Apple pode ter mesma descrição original mas ser renomeada para ChatGPT, iTunes, iCloud

**Tabelas**:
- Colunas centralizadas (exceto Descrição Original)
- Botões de ação como ícones fixos (3 slots na tabela operacional, 2 slots na tabela retirada)
- Botões desabilitados quando ação indisponível na etapa atual do fluxo

---

## Módulo: Recorrências

**Rota**: `/recorrencias`
**Status**: Funcional / Em evolução

Controla:
- Despesas recorrentes (mensais ou intra-mensais)
- **Despesas recorrentes com prazo** (termo oficial — não "recorrência parcelada")
- Consórcios (tipo especial de recorrência)

**Funcionalidades**:
- Débito automático vinculável a conta bancária
- Vínculo com cartão e Categoria do Cartão
- Encerramento por quantidade de parcelas ou data final
- Importação de cartão pode vincular lançamento a recorrência existente

**Proteção de histórico**: parcelas pagas não são alteradas por recálculos ou edições estruturais.

---

## Módulo: Consórcios

**Status**: Funcional (integrado a Recorrências e Receitas)

Controla:
- Consórcio como ativo/obrigação financeira
- Contemplação → gera receita prevista em `ReceitaOrcamento`
- Integrado com Receitas: contemplação sem efetivação bancária aparece como pendente
- Confirmação de pendência preserva competência original

---

## Módulo: Financiamentos

**Rota**: `/financiamentos`
**Status**: Em evolução avançada

Controla contratos de financiamento com cronograma completo de parcelas.

### Sistemas de amortização suportados

| Sistema | Descrição |
|---------|-----------|
| SAC | Quota de amortização constante, juros decrescentes |
| PRICE | Parcela constante, composição variável |
| SIMPLES | Parcela fixa simples |
| SFH | Sistema Financeiro de Habitação (SAC com regras CEF) |
| CAIXA SAC/TR | SAC com correção monetária por TR mensal (opt-in) |

### Composição do total previsto

```
total_previsto = amortização + juros + seguro + taxa_administrativa
```

### Seguro habitacional — dois modos

**Fixo/manual**:
```
seguro = valor_mensal_da_vigência
```

**Estimado DFI+MIP**:
```
seguro = DFI + MIP
DFI = base_DFI × fator_DFI
MIP = juros_contratuais × fator_MIP[faixa_etária]
```
- DFI pode usar base original ou base segurada
- MIP varia com juros e saldo
- Faixa etária configurável por competência
- Helper central de seguro usado por geração, amortização, ajuste de saldo e recálculo

### Modo CAIXA SAC/TR (opt-in)

- Taxa mensal = taxa nominal anual / 12
- TR mensal aplicada ao saldo devedor
- Quota de amortização corrigida pela TR
- Juros sobre saldo corrigido pela TR
- Seguro calculado pelo helper central
- TR ausente bloqueia geração (não silenciosa)
- Modo opt-in por financiamento, não global

**Calibração de referência** (sem dados pessoais):
- Sistema SAC, prazo 420 meses, início mai/2024
- Taxa nominal com relacionamento 9,38%, taxa administrativa R$ 25,00
- Indexador TR
- Antes da amortização (jul/2025): total ~R$ 5.335,44
- Após amortização (ago/2025): total ~R$ 3.002,21
- Saldo teórico em mai/2026: ~R$ 270.800,85
- Modelo calibrado chegou a erro de ~R$ 3,06 no saldo

### Ajuste de saldo devedor real

- Usuário informa saldo observado no extrato do banco
- Sistema preserva histórico integralmente
- Recalcula apenas parcelas futuras
- Registra auditoria do ajuste
- Bloqueia se houver conta/parcela efetivada no trecho afetado

### Amortização extraordinária

- Recalcula parcelas futuras a partir do mês do pagamento
- Parcelas pagas e contas efetivadas são protegidas
- Seguro recalculado pelo helper central
- Redução de prestação com prazo mantido (comportamento padrão)
- Escolha formal entre reduzir prazo e reduzir prestação: pendência futura (FIN-AMORT-OPCAO-1)

### Exclusão segura

Permite excluir somente quando não há execução financeira:
- Sem parcela paga
- Sem conta efetivada
- Sem amortização registrada
- Sem ajuste de saldo
- Sem movimentação vinculada

Remove: parcelas, contas pendentes vinculadas, vigências de seguro, faixas MIP.
Preserva: `ItemDespesa` (cadastro mestre compartilhável).

### ItemDespesa no financiamento

- `ItemDespesa` é cadastro mestre compartilhável; nunca apagado automaticamente
- Pode receber `origem_tipo`, `origem_id`, `origem_contexto` quando criado automaticamente
- Troca de `item_despesa_id` bloqueada com execução financeira
- Sem execução: contas pendentes são sincronizadas automaticamente

### Extrato anual

- Exibe todas as colunas: amortização, juros, seguro, taxa adm, total previsto
- Total previsto fecha visualmente (não esconde componentes)

### UX da lista

- Formato tabular: header compartilhado + uma linha por contrato
- Ícones de ação: visualizar, amortizar, extrato, editar, quitar
- Barra de ações do formulário (action_bar) com Cancelar e Salvar
- Formulário compacto (inputs 34px, sidebar 340px)

---

## Módulo: Veículos / Mobilidade

**Rota**: `/veiculos`
**Status**: Funcional / Em evolução (homologação visual pendente)

Três blocos:
1. **Comparação de Cenários**: até 3 cenários simultâneos (veículo próprio, assinatura, app)
2. **Configuração das Modalidades**: lista veículos e apps com destaque para cenário ativo
3. **Efetivação das Despesas**: lista `DespesaPrevista` com confirmação e meio de pagamento

**KPIs**: mais econômico, custo médio, custo estimado, cenário ativo.

**Regras de efetivação**:
- Meio cartão → cria `LancamentoAgregado` via `CartaoService.adicionar_lancamento()`
- Demais meios → cria `ItemDespesa(tipo='Simples')` + `Conta`
- Guard de idempotência: `status == 'PREVISTA'` + transação atômica

**Categoria padrão**: Mobilidade (criada automaticamente se não existir).

**Pendências**:
- Homologação visual dos mockups
- Validação do motor de cálculo de custo mensal
- Padronização das imagens (veículo próprio, assinatura, app)

---

## Módulo: Contas Bancárias

**Rota**: `/contas`
**Status**: Funcional

**Princípios invioláveis**:
1. Saldo nunca editado diretamente — `saldo_atual` sempre derivado
2. Toda alteração de saldo gera `MovimentoFinanceiro`
3. Ajuste manual é lançamento explícito no extrato
4. Extrato é a verdade

**Tipos de movimento**: CREDITO, DEBITO, AJUSTE
**Origens**: MANUAL, RECEITA, DESPESA, TRANSFERENCIA

---

## Módulo: Documentos / Fiscal

**Status**: Funcional (parcial)

Funcionalidades implementadas:
- Leitura de cupom fiscal básico (OCR local)
- Central de documentos empresariais
- Pacote ZIP para contador
- Alertas de validade de documentos empresariais
- Sugestão de bem a partir de documento fiscal
- Criação de atalhos financeiros a partir de documento

**Futuro**: módulo amplo de IR/IRPF reutilizável por contexto financeiro.

---

## Módulo: Indexadores

**Rota**: `/indexadores`
**Status**: Funcional

- 419+ registros históricos de TR (1991–2025)
- IPCA, IGP-M, CDI, SELIC
- Obrigatório para modo CAIXA SAC/TR em Financiamentos
- Tela de manutenção e importação: pendência FIN-INDICES-1

---

## Navegação e UX

**Shell visual**:
- Menu lateral principal
- Barra superior de contexto
- Faixa de ações por módulo (`action_bar`)
- Ícones monocromáticos com `currentColor`
- Configurações enxuta: apenas preferências e parâmetros globais

**Padrões consolidados**:
- `action_bar` com filtros à esquerda e ações à direita
- Botões de ação por linha: ícones pequenos, sempre visíveis, `title` e `aria-label`
- Listas tabulares: header compartilhado + linhas de dados (mesmo grid)
- Colunas secundárias centralizadas; primeira coluna alinhada à esquerda
- Botões visíveis devem ter função real ou estar marcados como "em desenvolvimento"
