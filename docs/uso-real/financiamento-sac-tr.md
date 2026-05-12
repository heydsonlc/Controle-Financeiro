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

## TR oficial

A tabela oficial da TR usada pelo motor SAC/TR é `indice_tr_mensal`.

`IndexadorMensal` permanece como estrutura legada/genérica para outros fluxos e não alimenta o motor SAC/TR neste MVP.

Regras atuais:

- a competência usa formato `YYYY-MM`;
- o usuário informa a TR como percentual mensal;
- o sistema salva em fator decimal, por exemplo `0,16%` como `0.0016`;
- alteração de TR já usada por parcelas de financiamento SAC/TR é bloqueada;
- alteração de TR não recalcula cronogramas automaticamente.

## Manutenção

A tela `/indexadores` possui uma seção específica para **TR para financiamentos SAC/TR**.

Essa seção permite:

- listar TR por ano;
- cadastrar competência manualmente;
- editar TR quando ainda não estiver usada em cronogramas;
- importar várias competências por texto/CSV simples;
- validar duplicidade, formato de competência e valor percentual.

O motor de financiamento continua bloqueando geração ou simulação quando faltar TR obrigatória.

## Compatibilidade transitória

O campo `modo_calculo_financiamento` permanece no banco por compatibilidade, mas não deve ser enviado pela UI como regra de negócio.

Valores legados como `caixa_sac_tr` continuam aceitos temporariamente para evitar quebra técnica, mas a regra principal é a combinação `SAC + TR`.

## Escopo

Esta consolidação não altera a fórmula SAC/TR calibrada, não remove coluna técnica e não altera os modos PRICE, SIMPLES ou SAC sem TR.
