# 📜 CONTRATO DO MÓDULO DE VEÍCULOS

## 🔄 ADENDO — VERSÃO 1.3 (CAMINHOS DE MOBILIDADE E CUSTO DO CAPITAL)

**Versão:** 1.3  
**Status:** Adendo normativo (obrigatório)  

Este adendo complementa a versão 1.2 sem revogá-la.  
Todas as regras anteriores permanecem válidas.

## Caminhos Ativos e Custo Mensal de Mobilidade

O sistema permite que m?ltiplos Caminhos de Mobilidade estejam ativos simultaneamente.

Um Caminho Ativo indica que ele est? em uso no contexto atual do usu?rio e deve participar do c?lculo do custo mensal de mobilidade.

O custo mensal de mobilidade ? definido como a soma dos custos mensais consolidados de todos os caminhos ativos.

Caminhos inativos:
- n?o participam da soma,
- permanecem dispon?veis para simula??o e compara??o,
- n?o geram lan?amentos autom?ticos.

O status ativo ou inativo de um caminho representa apenas inten??o de uso e n?o implica, por si s?, cria??o de despesas reais ou execu??o financeira autom?tica.

## 🔄 ADENDO — VERSÃO 1.2 (DECISÃO FINANCEIRA)

**Versão:** 1.2 (corrigida)  
**Data:** 2026-01-05  
**Status:** Normativo (obrigatório)

### 🎯 Propósito do Módulo (definitivo)

O módulo de veículos tem como objetivo auxiliar o controle financeiro e a tomada de decisão, permitindo ao usuário compreender:

- o custo total mensal de possuir um veículo
- o impacto no orçamento ao comprar, vender, financiar ou substituir
- a comparação com alternativas (aluguel, app, táxi, etc.)

O Módulo de Veículos existe para auxiliar **decisões financeiras relevantes**, permitindo ao usuário avaliar, de forma racional, se deve:

- comprar
- manter
- vender
- substituir
- alugar um veículo

O módulo não é apenas previsão de gastos; ele é um instrumento de **comparação de cenários de mobilidade**.

O módulo não cria lançamentos reais automaticamente.

### 🔑 Regra Fundamental (obrigatória)

Um veículo só é considerado “compreensível” pelo sistema quando o **custo mensal total estimado** é calculado e exibido ao usuário.

Sem essa informação:
- o módulo é considerado incompleto
- a UI é considerada funcionalmente inválida
- o usuário não consegue decidir

### 🧠 Conceito central: custo mensal consolidado

Todo veículo deve expor, de forma clara, um **CUSTO MENSAL ESTIMADO**.

Esse valor é:
- informativo
- projetivo
- não gera lançamentos reais

O custo mensal estimado:
- não é lançamento real
- não é “chute” solto
- é uma **agregação racional** das projeções existentes

O cálculo usa:
- `DespesaPrevista` (custos explícitos projetivos)
- estimativas informativas quando aplicável (ex: manutenção por km via regras)

E considera:

1) Custos mensais diretos
- Combustível
- Financiamento (parcelas + IOF diluído, quando existir)
- Outros custos mensais previstos vinculados ao veículo

2) Custos anuais rateados (÷ 12)
- IPVA / Licenciamento
- Seguro
- Manutenção por km (impacto mensal estimado via regras + uso estimado/projetado)

3) Custos excluídos
- Despesas `IGNORADA`
- Despesas fora do veículo (origem ≠ veículo)
- Qualquer lançamento real não relacionado

### 🧩 Manutenção por km (camada conceitual)

A manutenção por km é tratada como:

- regras configuráveis por veículo
- baseadas em uso estimado
- sem agenda fixa automática
- com geração explícita de `DespesaPrevista` pelo usuário

A UI deve:

- explicar o conceito
- permitir cadastrar regras
- mostrar “próxima manutenção estimada”
- permitir gerar a despesa prevista manualmente

### 💰 Valor do veículo (campo obrigatório conceitual)

O veículo deve possuir **valor de aquisição** (informativo), usado para:

- simulações de financiamento
- análise de custo de capital
- decisões de compra/venda

📌 Não é lançamento.  
📌 Não é patrimônio contábil.  
📌 É base de decisão.  

### 🔁 Relação com outros cenários

O custo mensal total do veículo deve permitir comparação direta com:
- aluguel de veículo
- transporte por aplicativo
- táxi
- manter apenas um veículo
- vender um veículo existente

A comparação é sempre feita por **custo mensal**.

### 🧱 Papel do Backend e do Frontend

Backend:
- Armazena projeções (`DespesaPrevista`)
- Mantém integridade temporal e rastreabilidade
- Não decide cenários
- Não agrega custos automaticamente como “verdade” (apenas expõe dados)

Frontend (ou API de leitura):
- Obrigatoriamente agrega (de forma transparente)
- Obrigatoriamente exibe
- Obrigatoriamente destaca o custo mensal total

### ❌ Proibições (reforço)

- Não ocultar o custo mensal total
- Não exigir interpretação do usuário (mostrar apenas valores individuais sem agregação)
- Não criar lançamentos reais automaticamente
- Não misturar custo mensal com saldo/fluxo de caixa (são conceitos diferentes)

### 🏁 Condição de conclusão (congelamento)

O módulo de veículos só pode ser congelado quando:
- o custo mensal total é exibido
- o usuário entende o impacto no orçamento
- a comparação de cenários é possível

---

## Sistema Financeiro Projetivo

> **Este documento define regras obrigatórias para qualquer implementação do Módulo de Veículos.
> A IA não pode criar soluções fora deste contrato.**

---

## 1. Princípio Fundamental

O sistema financeiro é **projetivo**, não reativo.

> **Veículo não é um bem financeiro.
> Veículo é um gerador contínuo de compromissos financeiros futuros.**

Qualquer implementação que trate veículo apenas como registro de gastos passados **viola este contrato**.

---

## 2. Finalidade do Módulo de Veículos

O módulo de veículos existe exclusivamente para:

* projetar despesas futuras
* antecipar picos financeiros
* integrar custos veiculares ao orçamento global
* permitir decisões antes da despesa ocorrer

❌ O módulo não existe para:

* controle histórico isolado
* relatórios puramente retroativos
* lançamentos automáticos silenciosos

---

## 3. Integração com o Sistema Financeiro

### 3.1 Categorias Unificadas (Regra Obrigatória)

Todas as despesas veiculares **devem utilizar o mesmo sistema de categorias** já existente no sistema financeiro e nos cartões de crédito.

Exemplos válidos:

* Combustível
* Manutenção
* Seguro
* Impostos
* Outros

❌ É proibida a criação de categorias exclusivas como "Carro" ou "Veículo".

O veículo define **a origem da despesa**, nunca sua categoria.

---

### 3.2 Origem da Despesa

Toda despesa gerada pelo módulo deve conter:

* origem = veículo
* referência ao veículo específico

Isso é obrigatório para:

* conciliação
* relatórios
* rastreabilidade

---

## 4. Projeção ≠ Lançamento

O sistema deve manter separação absoluta entre:

* **Despesa Prevista** (projeção)
* **Despesa Lançada** (real)

Nenhuma despesa prevista:

* pode virar lançamento automaticamente
* pode impactar histórico sem confirmação
* pode ser criada de forma invisível ao usuário

---

## 5. Tipos de Despesas Veiculares

O sistema reconhece três naturezas temporais:

### 5.1 Recorrentes

* combustível
* pequenos custos frequentes

Devem:

* ser projetadas mensalmente
* poder ser conciliadas com cartão ou conta
* nunca gerar duplicidade

---

### 5.2 Periódicas

* IPVA
* seguro
* licenciamento

Devem:

* possuir mês definido
* gerar alertas antecipados
* impactar projeções futuras

---

### 5.3 Condicionadas

* troca de óleo
* pneus
* manutenção preventiva

Devem:

* depender de tempo, km ou ambos
* nunca ser tratadas como datas rígidas
* sempre permitir adiamento
* ser modeladas como regras configuráveis por veículo
* gerar `DespesaPrevista` apenas por ação explícita do usuário

---

## 6. Inferência de Quilometragem via Consumo

### 6.1 Princípio de Simplicidade

O sistema **não exige** que o usuário registre quilometragem manualmente.

A quilometragem é **inferida** a partir do consumo de combustível.

---

### 6.2 Autonomia Declarada (Obrigatório no MVP)

Ao cadastrar o veículo, o usuário informa:

* **Autonomia média (km/L)**: `12` km/L

Toda despesa de combustível registrada permite calcular:

```
Litros abastecidos: 45L
Autonomia declarada: 12 km/L
Km percorridos estimados: 45 × 12 = 540 km
```

**Regras:**
* Campo obrigatório no cadastro do veículo
* Valor único, informado uma vez
* Usado para todas as projeções

---

### 6.3 Aprendizado Progressivo (Opcional - Fase 2)

O sistema pode **aprender a autonomia real** ao longo do tempo.

**Como funciona:**

1. Usuário informa hodômetro inicial (opcional) ao cadastrar veículo
2. Sistema solicita atualização espaçada (a cada 3-6 meses, nunca mais de 1x por trimestre)
3. Sistema calcula autonomia real:
   ```
   Km percorridos: hodômetro atual - hodômetro anterior
   Combustível consumido: soma dos abastecimentos no período
   Autonomia real: km percorridos / combustível consumido
   ```
4. Sistema usa autonomia real para projeções futuras

**Gatilhos para solicitar atualização:**
* Após 6 meses do último registro
* Quando despesa condicionada se aproxima (faltam 2 meses)
* Nunca de forma intrusiva

**Modelo de solicitação:**
```
💡 Quer deixar as projeções mais precisas?

Seu hodômetro atual é ~47.500 km (estimado)
Se souber o valor exato, pode atualizar abaixo:

Hodômetro atual: [_____] km

[Agora não]  [Atualizar]
```

---

### 6.4 Regras de Inferência

**Projeção de despesas condicionadas:**

Exemplo: Troca de óleo a cada 10.000 km

```
Última troca: 45.000 km
Próxima troca: 55.000 km
Intervalo: 10.000 km

Km atual estimado: 45.000 + (combustível acumulado × autonomia)
Km atual: ~47.500 km
Km restantes: 55.000 - 47.500 = 7.500 km

Consumo mensal médio: ~1.500 km/mês (inferido dos últimos 3 meses)
Meses restantes: 7.500 / 1.500 = 5 meses

Previsão: troca de óleo em Maio/2025
```

O sistema pode estimar automaticamente a “próxima manutenção estimada”, mas a criação de `DespesaPrevista` deve ser uma ação explícita do usuário (ex: “Gerar despesa prevista”).

---

### 6.5 Proibições

❌ É proibido:

* Exigir que o usuário registre km manualmente com frequência
* Criar alertas insistentes para atualização de hodômetro
* Bloquear funcionalidades se hodômetro não for informado
* Solicitar hodômetro mais de 1 vez a cada 3 meses

---

## 7. Eventos Encadeados (Ciclos)

Despesas condicionadas **não são eventos isolados**.

Elas pertencem a **ciclos temporais** definidos por:

* intervalo em meses
* intervalo em km (inferido via consumo)
* ou modelo híbrido (tempo + km)

Cada ocorrência influencia diretamente as próximas.

A IA **deve modelar ciclos**, não listas de datas fixas.

---

## 8. Adiamento (Regra Crítica)

Quando uma despesa prevista chega ao mês esperado, o usuário deve poder:

* confirmar
* adiar
* ignorar (exceção)

Adiamento:

* **não é erro**
* **não é falha**
* é um novo dado de uso real

---

## 9. Ajuste em Cascata (Obrigatório)

Se uma despesa pertencente a um ciclo for adiada, a IA deve:

1. Reconhecer quebra do ciclo
2. Oferecer explicitamente ao usuário:

   * recalcular o intervalo a partir da nova data
   * manter o calendário original

❌ É proibido:

* ajustar eventos futuros automaticamente
* recalcular ciclos sem consentimento
* alterar datas silenciosamente

---

## 10. Histórico é Imutável

A IA **não pode**:

* reescrever despesas confirmadas
* alterar lançamentos passados
* modificar histórico financeiro

Planejamento é dinâmico.
Histórico é imutável.

---

## 11. Impacto no Orçamento

Todas as despesas veiculares devem:

* impactar projeções futuras
* aparecer no orçamento mensal projetado
* influenciar alertas de sobrecarga

O orçamento deve funcionar como:

> **mapa de pressão futura**, não apenas teto de gasto.

---

## 12. Integração com Cartões e Importações

A IA deve considerar que:

* despesas veiculares podem aparecer em faturas
* o sistema deve permitir conciliação (manual inicialmente, sugestões automáticas em fase posterior)
* duplicidade é proibida

**Regra de Conciliação:**

* **Fase 1 (MVP):** Conciliação manual — usuário confirma que lançamento importado corresponde à despesa prevista
* **Fase 2:** Sugestões automáticas baseadas em padrões (valor similar + categoria combustível + proximidade de data)
* **Nunca:** Conciliação silenciosa sem confirmação do usuário

Veículo e cartão **não competem** — eles se reconhecem.

---

## 13. Modo Simulação (Pré-Compra)

### 13.1 Veículo Simulado

O sistema deve permitir criar veículos em modo **simulação**.

Veículos simulados:

* não geram lançamentos
* não afetam orçamento real
* não entram em alertas reais
* existem apenas como projeção

---

### 13.2 Finalidade da Simulação

A simulação deve responder:

* custo mensal médio
* custo anual total
* custo por km (baseado em autonomia estimada)
* meses de pico
* impacto no orçamento global

A comparação entre veículos deve ser feita por:

> **custo total projetado**, nunca apenas por preço.

**Exemplo de comparação:**
```
Veículo A (simulado):
- Custo mensal médio: R$ 1.200
- Maior pico: R$ 3.500 (março - IPVA)
- Custo total 12 meses: R$ 14.400

Veículo B (simulado):
- Custo mensal médio: R$ 800
- Maior pico: R$ 2.100 (março - IPVA)
- Custo total 12 meses: R$ 9.600
```

---

## 14. Conversão Simulado → Ativo

Quando o usuário decide comprar um veículo:

* o veículo simulado pode ser convertido em ativo
* as projeções passam a ser reais
* nenhuma despesa retroativa é criada

A conversão deve ser:

* explícita
* consciente
* controlada pelo usuário

---

## 15. Princípio Educacional

O sistema deve:

* mostrar consequências
* sem julgamento
* sem punição
* sem culpa

A IA **não deve** induzir decisões.
Ela deve **revelar impactos futuros**.

---

## 16. Estratégia de Implementação em Fases

### Fase 1 - MVP Viável

**Objetivo:** Sistema funcional e útil desde o primeiro dia.

**Funcionalidades obrigatórias:**
* Cadastro de veículo com autonomia declarada (km/L)
* Despesas periódicas (IPVA, seguro, licenciamento) — data fixa anual
* Despesas recorrentes (combustível) — valor mensal estimado
* Modo simulação (comparar 2 veículos lado a lado)
* Projeção automática de km via consumo de combustível
* Despesas condicionadas apenas por **tempo** (ex: troca de óleo a cada 6 meses)

**Funcionalidades proibidas no MVP:**
* Despesas condicionadas por km
* Conciliação automática com cartão
* Aprendizado progressivo de autonomia
* Ajuste em cascata complexo

---

### Fase 2 - Refinamento

**Pré-requisito:** Fase 1 estável e em uso por pelo menos 30 dias.

**Adicionar:**
* Regras de manutenção por **km estimado** (ex: troca de óleo a cada 10.000 km), com geração manual de `DespesaPrevista`
* Adiamento com ajuste em cascata (com confirmação visual do usuário)
* Aprendizado progressivo de autonomia (hodômetro opcional)
* Conciliação manual assistida (sistema sugere, usuário confirma)

---

### Fase 3 - Inteligência

**Pré-requisito:** Fase 2 validada com dados reais de uso.

**Adicionar:**
* Despesas híbridas (tempo + km — o que ocorrer primeiro)
* Conciliação automática inteligente (baseada em padrões aprendidos)
* Alertas preditivos ("Seu IPVA vence em 60 dias — R$ 2.500")
* Relatórios de custo comparativo (custo/km real vs. estimado)

---

## 17. Princípio Final (Cláusula Máxima)

> **O sistema não decide pelo usuário.
> Ele mostra o futuro antes que ele aconteça.**

Qualquer implementação que:

* esconda impactos
* automatize sem transparência
* force comportamentos

**viola este contrato.**

---

## 18. Caminhos de Mobilidade (Novo Conceito Central)

O sistema passa a reconhecer **Caminhos de Mobilidade**, definidos como:

> Estruturas projetivas que representam decisões alternativas de locomoção, comparáveis exclusivamente por **custo mensal total**.

São caminhos válidos (exemplos):

* Veículo próprio
  * compra à vista
  * compra financiada
* Carro por assinatura
  * contrato mensal
  * prazo definido
* Transporte por aplicativo
  * Uber / Táxi / 99
  * custo por km

📌 Caminhos:

* geram projeções
* não geram lançamentos
* existem para comparação

---

## 19. Custo do Capital Imobilizado (Obrigatório)

Sempre que um veículo for adquirido (simulado ou ativo), o sistema deve considerar o **custo do capital imobilizado**.

### 19.1 Definição

Custo do capital é o **custo mensal equivalente** de manter recursos próprios imobilizados na aquisição de um veículo.

### 19.2 Aplicação

| Situação | Custo do capital | Juros |
|---|---:|---:|
| Compra à vista | ✔ | ❌ |
| Compra financiada | ✔ (sobre a entrada) | ✔ |
| Carro por assinatura | ❌ | ❌ |
| Transporte por app | ❌ | ❌ |

### 19.3 Cálculo Conceitual

`custo_capital_mensal = valor_capital_proprio × taxa_referencia_mensal`

📌 A taxa é:

* informativa
* configurável
* educacional
* não vinculada a produto financeiro específico

---

## 20. Integração do Custo do Capital ao Custo Mensal

O custo do capital:

* deve aparecer na visão consolidada
* deve compor o custo mensal total
* deve ser claramente rotulado como: **“estimado / custo de oportunidade”**

❌ É proibido:

* ocultar esse custo
* embutir em parcelas
* tratá-lo como lançamento real

---

## 21. Caminho: Carro por Assinatura

O Carro por Assinatura é um caminho de mobilidade com as seguintes características:

* custo mensal fixo
* prazo contratual definido (em meses)
* ausência de capital imobilizado
* ausência de juros
* combustível não incluído, salvo informação explícita

Gera:

* projeções mensais com data de fim
* custo mensal consolidado comparável aos demais caminhos

---

## 22. Caminho: Transporte por Aplicativo

O Transporte por App é um caminho de mobilidade baseado em **distância percorrida**.

### 22.1 Base de cálculo

* km mensal estimado (obrigatório)
* preço médio por km (obrigatório)

Perfis de uso são:

* opcionais
* explicativos
* não geram projeções separadas

### 22.2 Projeção

* gera uma única `DespesaPrevista` mensal
* recorrente
* sem meio de pagamento definido nesta fase

---

## 23. Regra de Comparação (Reforço)

Todos os caminhos devem ser comparáveis exclusivamente por **custo mensal total**, composto por:

* custos explícitos projetivos
* custos anuais diluídos
* custos condicionados mensalizados
* custos financeiros implícitos (custo do capital)

---

## 24. Proibição de Decisão Automática (Reforço)

Mesmo com múltiplos caminhos:

* o sistema não escolhe
* a IA não recomenda
* a decisão é sempre do usuário

🧠 FRASE FINAL (PARA GUIAR A IA)

> Mobilidade é decisão financeira contínua, não evento pontual.

---

## 📌 Status do Contrato

* Documento **normativo**
* Documento **imutável em conceito**
* Pode evoluir apenas com decisão explícita do autor
* Data de criação: 2025-12-31
* Versão: 1.3 — Adendo: Caminhos de mobilidade e custo do capital (nenhuma regra anterior revogada)

---

## 🔮 Próximos Passos (Quando Houver Token)

Quando for implementar este módulo, a IA deverá:

1. **Quebrar em tarefas técnicas** — Mapear models, services, routes, frontend
2. **Gerar checklist de validação** — Garantir que cada regra foi implementada
3. **Mapear impacto no banco** — Definir schema e migrations necessárias
4. **Integrar com módulos existentes** — Categorias, Despesas, Cartões, Dashboard

---

**Este contrato está pronto para implementação futura.**
