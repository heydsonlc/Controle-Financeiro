# Financiamento SAC com TR

## Decisão

O motor de cálculo SAC corrigido pela TR é derivado dos campos de negócio do financiamento:

```text
sistema_amortizacao = SAC
indexador_saldo = TR
```

Quando essa combinação estiver presente, o backend usa automaticamente o cálculo SAC/TR:

- taxa mensal = taxa nominal anual / 12;
- TR mensal aplicada ao saldo;
- quota de amortização corrigida pela TR;
- seguro calculado pelo helper central;
- erro explícito quando faltar TR para a competência necessária.

## Compatibilidade transitória

O campo `modo_calculo_financiamento` permanece no banco por compatibilidade, mas não deve ser enviado pela UI como regra de negócio.

Valores legados como `caixa_sac_tr` continuam aceitos temporariamente para evitar quebra técnica, mas a regra principal é a combinação `SAC + TR`.

## Escopo

Esta consolidação não altera a fórmula SAC/TR calibrada, não remove coluna técnica e não altera os modos PRICE, SIMPLES ou SAC sem TR.
