# Guia para IA — Regras de Implementação

> Este documento tem **prioridade absoluta** sobre qualquer script ou solicitação pontual.
> Leia antes de implementar qualquer funcionalidade.

---

## Filosofia Central: Consciência, não Controle

O sistema **nunca diz ao usuário o que fazer**. Ele descreve a realidade financeira, sem julgamentos.

### O que implementar
- Mostrar dados reais e fatos objetivos
- Calcular totais, médias, percentuais, comparações
- Exibir previsto vs executado (ambos como informação neutra)

### O que nunca implementar
- Sugestões prescritivas ("Você deveria economizar em...")
- Alertas moralistas ("Atenção: orçamento estourado!")
- Cores vermelho/verde para indicar certo/errado (apenas para status objetivo: Pago/Pendente)
- Julgamentos de comportamento

**Exemplo crítico**:
- ✅ "Você gastou R$ 300 além do previsto" — descritivo, permitido
- ❌ "Você gastou demais" — prescritivo, bloqueado

---

## Regras Técnicas Soberanas

### 1. Backend Soberano
Toda lógica de negócio fica no servidor. Frontend apenas exibe dados já calculados.

### 2. Cálculo Dinâmico
Valores financeiros calculados em tempo real — nunca armazenados como campos estáticos.
- Executado = soma de `LancamentoAgregado`
- Previsto = soma de `OrcamentoAgregado`

### 3. Mês como Eixo Soberano
Toda consulta começa filtrando por `mes_competencia` ou `mes_referencia`. Vencimentos são refinadores secundários.

### 4. Regra Soberana de Fatura
- Se `status_pagamento == 'Pago'` → usar `total_executado`
- Se `status_pagamento == 'Pendente'` → usar `total_previsto`

Esta regra é inviolável — sem exceções.

### 5. Previsto vs Executado (ambos legítimos)
Diferença não é falha — é informação. Sem julgar se é bom ou ruim.

---

## Processo Obrigatório antes de Implementar

1. **Ler o código existente** relacionado ao tema
2. **Verificar se já existe** implementação total ou parcial
3. **Identificar conflitos** com regras de negócio, contratos, fluxos consolidados
4. **Confirmar explicitamente**: "Faz sentido implementar? SIM / NÃO / PARCIAL"
5. Só então implementar — de forma cirúrgica, sem efeitos colaterais

### Regras de conduta
- Não implementar imediatamente sem verificação
- Não refatorar por iniciativa própria
- Não remover endpoints, telas ou regras sem mapear impacto
- Não adicionar bibliotecas sem necessidade (preferir Vanilla JS, Python stdlib)

---

## Design e UX

**Estilo**: Minimalismo Apple-inspired — espaçamento generoso, tipografia clara, animações suaves (0.2s), bordas arredondadas (8-12px).

**Cores**: Azul para previsto, roxo/lilás para executado, cinza para neutro. Vermelho/verde apenas para status objetivo.

**Linguagem**: Objetiva, sem julgamento.

| Errado | Correto |
|--------|---------|
| "Gastos excessivos" | "Total executado: R$ 1.200" |
| "Você está no vermelho" | "Diferença: -R$ 300" |
| "Meta atingida!" | "Executado = Previsto" |

---

## Validação por Impacto (TESTES-IMPACTO-1)

Todo MVP é validado na proporção do que alterou. Detalhes, matriz e comandos estão em [TESTES_IMPACTO_1.md](TESTES_IMPACTO_1.md).

- **Nível 1 (desenvolvimento):** os testes do que está sendo mexido.
- **Nível 2 (encerramento do MVP, padrão):** a seleção de `venv\Scripts\python.exe scripts\testes_impacto.py`. Revise a lista e os motivos e depois rode com `--executar`, que mede o tempo.
- **Nível 3 (suíte completa):** só nos marcos. Isso inclui publicar, aplicar migration remota, mexer em código central compartilhado, integrar vários MVPs, ter falha de alcance desconhecido ou dúvida relevante.
- **Nunca, para ganhar tempo:**
  - tirar um teste necessário;
  - desligar isolamento, travas, transações ou limpeza;
  - reaproveitar resultado de outra versão dos arquivos.
- **Na dúvida:** ampliar a seleção e registrar a incerteza no relatório.
- **Regra permanente:** na dúvida sobre o impacto financeiro de uma alteração, ampliar. Isso vale sobretudo para pagamentos, estornos, conciliação, consolidação de faturas, saldos e movimentações entre contas: a integridade dos valores vale mais que alguns minutos de execução. O seletor já aplica essa regra quando o trecho alterado cita esses temas.

---

## Checklist Pré-Commit

- [ ] Lógica de negócio está no backend?
- [ ] Valores são calculados dinamicamente?
- [ ] Linguagem é descritiva (não prescritiva)?
- [ ] Código segue padrões existentes?
- [ ] Não há duplicação de funcionalidade?
- [ ] Não conflita com regras soberanas?

---

## Hierarquia de Prioridades (em conflito)

1. Filosofia soberana (Consciência, não Controle)
2. Regras técnicas invioláveis (Backend soberano, Cálculo dinâmico, Regra de fatura)
3. Padrões do código existente
4. Solicitação específica do usuário

Se o usuário solicitar algo que viola (1) ou (2), questionar antes de implementar.
