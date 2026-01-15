# Arquitetura: Indexadores Econômicos e Módulo de Veículos

**Versão:** 1.0
**Data:** 03/01/2026
**Status:** Fundação Implementada
**Próximo Passo:** Integração com Módulo de Veículos

---

## 🎯 Visão Estratégica

### O que foi construído

Não implementamos "apenas" uma tabela de índices econômicos.

Criamos uma **infraestrutura de tempo econômico** dentro do sistema — a capacidade de modelar o **custo do dinheiro ao longo do tempo**, não apenas o custo do bem.

Isso eleva o sistema de um controle financeiro para um **simulador de decisões financeiras de longo prazo**.

### Impacto no Módulo de Veículos

Antes desta implementação, o módulo de veículos (ainda não implementado) projetaria apenas:
- Combustível
- Manutenção
- Impostos
- Seguro

Agora, ele pode projetar também:
- **Custo financeiro da decisão de compra**

Isso muda fundamentalmente o valor entregue ao usuário.

---

## 🏗️ Fundação Implementada

### 1. Tabela `indexador_mensal`

**Estrutura:**
```
- id (PK)
- nome (TR, IPCA, IPCA-E, IGP-M, CDI, SELIC)
- data_referencia (primeiro dia do mês)
- valor (em percentual decimal)
- criado_em
```

**Dados atuais:**
- 419 registros históricos de TR (1991-2025)
- Preparado para IPCA, IGP-M, CDI, SELIC

**Interface de gestão:**
- Rota: `/indexadores`
- API: `/api/indexadores` (CRUD completo)
- Filtros por tipo e ano

### 2. Integração com Financiamentos

**Aplicação da TR:**
- Método: `_calcular_parcela_sac()` em `financiamento_service.py`
- Lógica: Saldo devedor é corrigido mensalmente ANTES do cálculo de juros
- Fórmula: `saldo_corrigido = saldo * (1 + TR_mensal)`

**Resultado alcançado:**
- Diferença de apenas R$ 1,10 na amortização vs. Caixa Econômica Federal
- Precisão de 99,84% no valor total da parcela
- Sistema agora reflete realidade econômica, não apenas matemática teórica

---

## 🔗 Conceito Central: Dois Vetores de Custo

### Veículo passa a ter dois vetores de custo independentes:

#### 1️⃣ Vetor Operacional (uso do bem)
- Combustível (variável com km rodados)
- Manutenção (preventiva + corretiva)
- Impostos (IPVA, licenciamento)
- Seguro
- Estacionamento, pedágios, etc.

**Característica:** Ligado ao **uso físico** do veículo

#### 2️⃣ Vetor Financeiro (forma de aquisição)
- Amortização do principal
- Juros (corrigidos por indexador)
- Taxas administrativas
- Seguro do financiamento
- IOF (quando aplicável)

**Característica:** Ligado à **decisão de compra**, não ao uso

### ⚠️ Separação Conceitual CRÍTICA

```
custo_do_veiculo ≠ custo_do_dinheiro
```

**O financiamento NÃO define o custo do veículo.**
**Ele define o custo da DECISÃO de compra.**

Tecnicamente:
- Veículo pode existir sem financiamento (compra à vista)
- Financiamento pode existir sem veículo (outros módulos)
- Quando ligados: financiamento **alimenta projeções veiculares**

---

## 📊 Novo Conceito Formal: Despesa Financeira do Veículo

### Classificação

**Tipo:** Despesa Financeira Veicular
**Origem:** Financiamento vinculado a veículo
**Categoria:** "Financiamento" ou "Juros" (categoria já existente no sistema)
**Natureza:** Fortemente projetiva, sensível a indexadores econômicos

### Diferenciação

- ❌ Não é despesa operacional
- ❌ Não é despesa pontual
- ✅ É compromisso financeiro de longo prazo
- ✅ É afetada por variáveis macroeconômicas (TR, IPCA)
- ✅ É anterior ao uso do bem

---

## 🎮 Simulação Pré-Compra (Poder Habilitado)

### Antes da implementação de indexadores:
```
Sistema: "Esse carro custa R$ 50.000"
Usuário: "OK, vou financiar"
Sistema: "Parcela de R$ 1.200 por 48 meses"
```

### Depois da implementação:
```
Sistema: "Esse carro custa R$ 50.000 à vista"

Cenário A (à vista):
- Custo total: R$ 50.000
- Impacto no patrimônio: imediato

Cenário B (financiado em 60 meses com TR):
- Custo do veículo: R$ 50.000
- Custo do dinheiro: R$ 18.500 (juros projetados)
- Custo TOTAL da decisão: R$ 68.500
- Parcela estimada: R$ 1.142/mês
- Impacto no orçamento futuro: -R$ 1.142/mês por 60 meses

Cenário C (financiado em 48 meses com TR):
- Custo do veículo: R$ 50.000
- Custo do dinheiro: R$ 14.200
- Custo TOTAL da decisão: R$ 64.200
- Parcela estimada: R$ 1.338/mês
- Economia vs 60 meses: R$ 4.300

O que cabe melhor no seu orçamento projetado?
```

### Perguntas que o sistema pode responder:

1. **Comparação de cenários:**
   - "Quanto eu economizo pagando à vista?"
   - "Qual a diferença entre 48 e 60 meses?"
   - "Esse financiamento cabe no meu orçamento futuro?"

2. **Análise de impacto:**
   - "Quanto vou pagar SÓ de juros?"
   - "Qual o custo REAL da decisão?"
   - "Como a TR pode afetar minhas parcelas?"

3. **Decisão informada:**
   - "Vale a pena usar minha reserva de emergência?"
   - "Compro agora ou espero 6 meses juntando dinheiro?"
   - "Financio 100% ou dou entrada?"

---

## 🧩 Integração Técnica (Quando Implementar Veículos)

### Fluxo de Cadastro de Veículo

```
1. Usuário informa dados do veículo
   ├─ Marca, modelo, ano
   ├─ Preço à vista
   └─ Km rodados por mês (estimativa)

2. Sistema pergunta: forma de aquisição?
   ├─ [ ] À vista
   └─ [ ] Financiado

3. Se financiado:
   ├─ Sistema abre wizard de simulação
   ├─ Usuário escolhe: prazo, entrada, indexador
   ├─ Sistema projeta: parcelas, juros totais, impacto no orçamento
   └─ Usuário decide: confirma ou ajusta parâmetros

4. Sistema cria:
   ├─ Registro do veículo (módulo veículos)
   ├─ Financiamento (módulo financiamentos) ← JÁ EXISTE
   ├─ Parcelas projetadas com TR aplicada ← JÁ FUNCIONA
   └─ Vincula veículo ↔ financiamento (nova relação)

5. Sistema projeta custo total:
   ├─ Custo operacional (combustível, manutenção...)
   └─ Custo financeiro (parcelas do financiamento)
```

### Relacionamento no Banco de Dados

```sql
-- Tabela de veículos (a ser criada)
CREATE TABLE veiculo (
    id INTEGER PRIMARY KEY,
    marca TEXT,
    modelo TEXT,
    ano_modelo INTEGER,
    ano_fabricacao INTEGER,
    preco_aquisicao NUMERIC(12,2),
    km_inicial INTEGER,
    data_aquisicao DATE,
    financiamento_id INTEGER,  -- ← VINCULO COM MÓDULO EXISTENTE
    ativo BOOLEAN,
    FOREIGN KEY (financiamento_id) REFERENCES financiamento(id)
);
```

**Nota:** Relacionamento 1:1 (um veículo pode ter um financiamento)

### Projeção Mensal de Custos

```python
def projetar_custos_veiculo(veiculo_id, meses=12):
    """
    Projeta custos totais do veículo

    Returns:
        [{
            'mes': '01/2026',
            'custo_operacional': {
                'combustivel': 450.00,
                'manutencao': 200.00,
                'ipva': 0.00,  # apenas em janeiro
                'seguro': 150.00,
                'total': 800.00
            },
            'custo_financeiro': {
                'amortizacao': 680.37,
                'juros': 2151.40,
                'seguro_financ': 155.47,
                'taxa_adm': 25.00,
                'total': 3012.24
            },
            'custo_total_mes': 3812.24
        }, ...]
    """
```

---

## 📋 Atualização do Contrato (Versão 1.2)

### Nova Seção: Financiamento como Componente Projetivo do Veículo

**Princípios:**

1. **Separação de conceitos**
   - O sistema DEVE distinguir custo do bem vs custo do dinheiro
   - O financiamento é uma DECISÃO, não uma característica do veículo

2. **Projeção obrigatória**
   - O sistema DEVE projetar custo financeiro total
   - O sistema DEVE aplicar indexadores econômicos cadastrados
   - O sistema DEVE mostrar impacto no orçamento futuro

3. **Simulação pré-compra**
   - O sistema DEVE permitir simular ANTES de criar o veículo
   - O sistema DEVE comparar: à vista vs financiado
   - O sistema DEVE comparar: diferentes prazos
   - O sistema DEVE comparar: diferentes indexadores (TR, IPCA, etc.)

4. **Transparência total**
   - O sistema DEVE mostrar: valor do bem
   - O sistema DEVE mostrar: custo do dinheiro (juros totais)
   - O sistema DEVE mostrar: custo TOTAL da decisão
   - O sistema NUNCA deve esconder o custo real

5. **Decisão informada**
   - O usuário DEVE ver todas as variáveis antes de decidir
   - O usuário DEVE poder comparar cenários lado a lado
   - O sistema DEVE alertar quando financiamento compromete orçamento futuro

---

## 🎯 Alinhamento com DNA do Sistema

### Princípios preservados:

✅ **Projetivo** - Simula antes de gastar
✅ **Não reativo** - Planeja, não apenas registra
✅ **Histórico preservado** - Indexadores mantêm série temporal
✅ **Decisão antes do gasto** - Simulação pré-compra
✅ **Transparência total** - Custo real sempre visível
✅ **Usuário no controle** - Múltiplos cenários comparáveis

### Diferencial competitivo:

A maioria dos sistemas de controle financeiro trata financiamento como:
```
Despesa fixa mensal de R$ X
```

Este sistema trata financiamento como:
```
Decisão financeira de longo prazo com:
- custo explícito do dinheiro
- impacto projetado no orçamento
- sensibilidade a variáveis macroeconômicas
- comparação de cenários alternativos
```

---

## 🚀 Roadmap de Implementação

### ✅ Fase 1: Fundação (CONCLUÍDA)
- [x] Tabela `indexador_mensal`
- [x] Série histórica TR (1991-2025)
- [x] Interface de gestão `/indexadores`
- [x] Aplicação de TR em financiamentos
- [x] Validação com dados reais (Caixa)

### 🔄 Fase 2: Preparação (PRÓXIMO)
- [x] Atualizar CONTRATO_MODULO_VEICULOS.md (v1.2)
- [ ] Definir estrutura da tabela `veiculo`
- [ ] Definir relacionamento `veiculo` ↔ `financiamento`
- [ ] Documentar fluxo de simulação pré-compra

### 📦 Fase 3: Implementação Veículos (FUTURO)
- [ ] Criar módulo de veículos
- [ ] Implementar wizard de simulação
- [ ] Integrar com módulo de financiamentos existente
- [ ] Projetar custos operacionais + financeiros
- [ ] Tela de comparação de cenários

### 🎨 Fase 4: Refinamento (FUTURO)
- [ ] Gráficos de evolução de custo
- [ ] Alertas de comprometimento orçamentário
- [ ] Simulação de venda antecipada
- [ ] Histórico de decisões vs realidade

---

## 📌 Decisões Arquiteturais Importantes

### 1. Por que indexadores em tabela separada?

**Decisão:** Não embutir TR diretamente no cálculo
**Motivo:** Permitir histórico, governança e simulação

**Benefícios:**
- Usuário controla dados econômicos
- Sistema pode simular cenários futuros
- Auditoria e transparência total
- Facilita comparação de indexadores

### 2. Por que vincular veículo → financiamento (e não o contrário)?

**Decisão:** `veiculo.financiamento_id` (1:1)
**Motivo:** Financiamento é módulo genérico (imóveis, empréstimos, etc.)

**Benefícios:**
- Financiamento permanece genérico
- Veículo "puxa" informações do financiamento
- Mesmo financiamento serve para qualquer módulo
- Baixo acoplamento

### 3. Por que separar custo operacional e financeiro?

**Decisão:** Dois vetores independentes
**Motivo:** São naturezas diferentes de custo

**Benefícios:**
- Usuário entende custo do BEM vs custo do DINHEIRO
- Permite comparar à vista vs financiado
- Facilita decisão de quitação antecipada
- Transparência máxima

---

## 🧪 Casos de Uso Habilitados

### Caso 1: Simulação antes da compra
```
Usuário: "Quero comprar um carro de R$ 50.000"
Sistema: "Vamos simular cenários..."

[Mostra 3 opções lado a lado]
- À vista
- Financiado 48 meses
- Financiado 60 meses

[Para cada opção]
- Custo total
- Impacto no orçamento mensal
- Quanto sobra de reserva de emergência
```

### Caso 2: Acompanhamento pós-compra
```
Usuário acessa dashboard de veículos
Sistema mostra:
- Custo operacional mês atual
- Custo financeiro mês atual
- Custo total acumulado desde compra
- Projeção próximos 12 meses
- Quanto falta pagar (principal + juros)
```

### Caso 3: Decisão de quitação antecipada
```
Usuário: "Vale a pena quitar o financiamento?"
Sistema calcula:
- Saldo devedor atual
- Juros que ainda pagaria
- Economia total ao quitar
- Impacto na reserva de emergência
- Retorno esperado se investisse o valor
```

---

## 🔐 Garantias Contratuais

### Para o usuário:
1. Sistema NUNCA esconderá custo real
2. Sistema SEMPRE mostrará custo do dinheiro separado
3. Sistema SEMPRE permitirá simular antes de decidir
4. Sistema SEMPRE aplicará indexadores corretamente

### Para a IA:
1. NUNCA misturar custo operacional e financeiro
2. NUNCA criar financiamento sem simulação prévia
3. NUNCA ocultar juros totais
4. SEMPRE preservar série histórica de indexadores

---

## 📚 Referências Técnicas

### Arquivos-chave implementados:
- `backend/models.py` → Modelo `IndexadorMensal`
- `backend/services/financiamento_service.py` → Aplicação de TR
- `backend/routes/indexadores.py` → API de gestão
- `frontend/templates/indexadores.html` → Interface web
- `scripts/popular_tr_historica.py` → Carga inicial de dados

### Contratos relacionados:
- `CONTRATO_FINAL_DO_SISTEMA.md` → Manifesto geral
- `CONTRATO_MODULO_VEICULOS.md` → Especificação veículos (v1.2)
- Este documento → Arquitetura de integração (v1.0)

---

## ✍️ Conclusão

Esta implementação não é incremental.
É **estrutural**.

Transformamos o sistema de um **controlador de gastos** para um **simulador de decisões financeiras**.

O módulo de veículos, quando implementado, será o mais poderoso do sistema — não porque tem mais features, mas porque **conecta três camadas** que raramente andam juntas:

1. Uso do bem (operacional)
2. Custo do bem (aquisição)
3. Custo do dinheiro (macroeconômico)

Isso é arquitetura de sistema financeiro maduro.

---

**Próximo passo (após contrato v1.2):**
- Definir estrutura da tabela `veiculo`
- Definir relacionamento `veiculo` ↔ `financiamento`
- Documentar fluxo de simulação pré-compra

Quando tiver token disponível, a base está pronta para execução.
