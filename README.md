# Controle Financeiro Pessoal

## O que é este sistema?

Um sistema de gestão financeira pessoal que reflete a **vida real como ela é**, não como deveria ser.

Este não é um planejador perfeito. É uma **ferramenta de consciência financeira** que reconhece:
- Que orçamentos estouram
- Que imprevistos acontecem
- Que comportamento humano é flexível
- Que controle total é ilusão

## Filosofia: Consciência, não Controle

### O problema dos sistemas tradicionais

A maioria dos aplicativos financeiros opera sob a premissa do **controle total**:
- "Planeje tudo"
- "Siga o orçamento"
- "Não gaste além do previsto"
- "Discipline-se"

**Resultado**: Frustração, abandono, culpa.

### Nossa abordagem: Flexibilidade Controlada

Este sistema opera sob um princípio diferente: **consciência em vez de controle**.

**Não dizemos**: "Você gastou demais — isso é errado"
**Dizemos**: "Você gastou R$ 300 além do previsto em Alimentação este mês"

**Não dizemos**: "Você falhou"
**Dizemos**: "Até hoje, 65% das despesas do mês já venceram"

**Não dizemos**: "Controle-se"
**Dizemos**: "Aqui está o que aconteceu. Você decide o que fazer"

## Conceitos Centrais

### 1. Previsto vs Executado (não Certo vs Errado)

- **Previsto**: O que você planejou
- **Executado**: O que realmente aconteceu

**Ambos são legítimos.**
Um não é "erro" do outro — são apenas **visões diferentes da mesma realidade financeira**.

### 2. Mês como Eixo Soberano

Tudo gira em torno da **competência mensal** (MM/AAAA).

Por quê? Porque é assim que vivemos:
- Salários chegam mensalmente
- Contas vencem mensalmente
- Faturas de cartão fecham mensalmente
- Financiamentos se organizam mensalmente

O mês é o **ritmo financeiro natural**.

### 3. Cartão como Comportamento (não Método de Pagamento)

Cartão de crédito não é "como você pagou".
É **como você consumiu**.

**Diferença crítica**:
- Compra parcelada no cartão → **despesa recorrente de 12 meses**
- Compra à vista no cartão → **despesa pontual do mês**

O sistema trata cartão como **canal de consumo**, não como destino de dinheiro.

### 4. Três Níveis de Informação

O sistema opera em 3 camadas:

#### a) Leitura (o que o sistema faz)
- Mostra dados
- Apresenta fatos
- Organiza informação
- **Sem julgamento**

Exemplo: "Você tem R$ 1.200 em despesas vencendo nos próximos 7 dias"

#### b) Alerta (o que o sistema poderia fazer, mas não faz)
- Avisos de situações críticas
- Notificações de eventos importantes
- **Ainda descritivo, mas com senso de urgência**

Exemplo: "Atenção: 3 contas vencendo amanhã"

#### c) Mentoria (o que o sistema NUNCA faz)
- Dizer o que fazer
- Dar conselhos
- Julgar escolhas
- **Prescritivo, invasivo**

Exemplo: ❌ "Você deveria cortar gastos em Alimentação"

**Este sistema para na Leitura.**
Futuramente pode evoluir para Alerta.
**NUNCA será Mentoria.**

## Regras Técnicas Soberanas

### Backend Soberano
- Toda lógica de negócio acontece no **backend**
- Frontend apenas **exibe** o que o backend calcula
- Zero lógica financeira em JavaScript

### Cálculo Dinâmico
- Valores calculados em **tempo real** a partir de transações
- Não confiamos em campos pré-calculados
- Fonte de verdade: `LancamentoAgregado` + `OrcamentoAgregado`

### Regra Soberana de Fatura
Para faturas de cartão:
- Se **Pago** → usar `valor_executado`
- Se **Pendente** → usar `valor_planejado`

Simples. Claro. Inviolável.

## O que torna este sistema diferente?

### 1. Reconhece a realidade
Imprevistos não são "falhas" — são **parte da vida**.
O sistema não pune você por ser humano.

### 2. Transparência radical
Mostra **tudo**:
- O que você planejou
- O que realmente aconteceu
- A diferença entre os dois

Sem esconder. Sem suavizar.

### 3. Respeito à autonomia
**Você está no controle.**
O sistema informa. Você decide.

### 4. Design minimalista
Interface limpa, focada, sem ruído.
Inspiração: Apple, Stripe, Linear.

Cada pixel tem propósito.

## Estrutura do Sistema

### Módulos principais

**Dashboard** → Visão geral do mês
**Despesas** → Gerenciamento detalhado de gastos
**Receitas** → Controle de entradas
**Contas** → Despesas não recorrentes
**Financiamentos** → Parcelamentos e empréstimos
**Cartões** → Configuração de cartões de crédito
**Configurações** → Categorias, itens agregados, contas bancárias

### Tecnologias

- **Backend**: Python (Flask) + SQLAlchemy
- **Frontend**: Vanilla JavaScript + Jinja2
- **Database**: SQLite (desenvolvimento)
- **Charts**: Chart.js

## Roadmap Conceitual

### ✅ Fase 1-6 (Concluída)
- Sistema funcional completo
- Dashboard com métricas visuais
- Gestão de despesas, receitas, contas
- Cartões com recorrência
- Financiamentos
- Agenda financeira + Insights temporais

### 🔒 Congelamento Intencional (2 meses)
**Status atual**: Teste no mundo real

O sistema está **completo** para sua proposta inicial.
Agora precisa de **uso real** para validar decisões de produto.

**Não adicionar features.**
**Apenas corrigir bugs críticos.**

### 🔮 Fase 7 (Futuro)
Possíveis evoluções após validação:
- Alertas inteligentes (ainda descritivos, nunca prescritivos)
- Comparações temporais (mês atual vs anterior)
- Exportação de dados
- Multi-moeda (se necessário)

**Critério para evolução**: Necessidade comprovada, não "seria legal ter".

## Para Desenvolvedores

### Antes de implementar qualquer coisa

1. **Leia o código existente** relacionado
2. **Verifique se já existe** funcionalidade similar
3. **Confirme que faz sentido** com a filosofia do sistema
4. **Documente tudo** após implementar

Consulte:
- `docs/AI_IMPLEMENTATION_STANDARD.md` → Processo obrigatório
- `docs/MANIFESTO_TECNICO_IA.md` → Regras técnicas
- `README_TECNICO.md` → Documentação técnica detalhada

### Princípio de ouro

> "O código deve refletir a vida real, não uma fantasia de perfeição financeira."

## Contribuindo

Este é um projeto pessoal em evolução.

Se você chegou aqui:
- Respeite a filosofia
- Mantenha a simplicidade
- Priorize clareza sobre sofisticação
- Lembre-se: **consciência, não controle**

---

**Versão**: 1.0
**Data de congelamento**: 2025-12-27
**Próxima revisão**: Após 2 meses de uso real

---

*"Um sistema financeiro que reconhece que você é humano."*
