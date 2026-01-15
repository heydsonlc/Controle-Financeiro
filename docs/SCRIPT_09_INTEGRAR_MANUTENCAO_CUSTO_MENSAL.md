# SCRIPT 09 — INTEGRAR MANUTENÇÃO POR KM AO CUSTO MENSAL ESTIMADO

## REFERÊNCIAS OBRIGATÓRIAS
Este script deve respeitar integralmente:
- `docs/CONTRATO_MODULO_VEICULOS.md` (v1.2)
- `docs/ARQUITETURA_INDEXADORES_E_VEICULOS.md`
- Manifesto do Módulo de Veículos (quando existir como documento separado)

Nenhuma decisão pode violar esses documentos.

---

## CONTEXTO
O custo mensal estimado do veículo deve refletir, de forma honesta, os custos de manutenção esperados
mesmo quando o veículo ainda não possui uso histórico (simulação de compra).

---

## REGRA CONCEITUAL (DO CONTRATO)
- Manutenção por km é estimativa educacional
- Não depende de uso passado obrigatoriamente
- Deve contribuir para o custo mensal consolidado
- Não cria `DespesaPrevista` automaticamente
- Não cria lançamentos reais

---

## OBJETIVO
Integrar o impacto mensal estimado das regras de manutenção por km ao cálculo do custo mensal consolidado do veículo.

---

## LÓGICA DE USO (PRIORIDADE)
1. Se existir `media_movel_km_mes > 0`: usar histórico (`HISTORICO`)
2. Caso contrário: inferir uso projetado (`PROJETADO`) a partir de:
   - gasto mensal de combustível
   - preço médio combustível
   - autonomia (km/L)

---

## CÁLCULO DO IMPACTO MENSAL (POR REGRA)
Para cada regra:

```text
meses_entre_eventos = intervalo_km / km_mes_estimado
impacto_mensal = custo_estimado / meses_entre_eventos
```

Somar todas as regras válidas.

---

## PROIBIÇÕES
- Não criar manutenção automaticamente
- Não exigir uso histórico para simulação
- Não esconder impacto da manutenção
- Não criar lançamentos reais

---

## CRITÉRIO DE ACEITE
- Custo mensal do veículo aumenta ao cadastrar regras de manutenção
- Funciona mesmo com `km_estimado_acumulado = 0`
- Usuário entende que é estimativa
- Nenhum lançamento real é criado

