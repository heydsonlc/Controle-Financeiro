# Seguro habitacional em financiamentos

## Regra oficial

O campo oficial para decidir a regra de seguro do financiamento é `seguro_modo`.

Valores aceitos:

- `fixo`
- `estimado_dfi_mip`

Campos antigos como `seguro_tipo` e `seguro_percentual` permanecem apenas como compatibilidade temporária. Eles não devem ser usados como fonte principal da regra de cálculo.

## Modo fixo/manual

O modo `fixo` usa `FinanciamentoSeguroVigencia`.

A regra é:

```text
seguro = valor_mensal da vigência válida na data da parcela
```

Os campos `taxa_percentual` e `saldo_devedor_vigencia` em `FinanciamentoSeguroVigencia` são legado. A fonte atual do seguro fixo é o valor mensal informado na vigência.

## Modo estimado DFI + MIP

O modo `estimado_dfi_mip` usa:

- `seguro_fator_dfi`
- `seguro_dfi_base`
- `seguro_data_nascimento_titular`
- `seguro_mes_reajuste_idade`
- `FinanciamentoSeguroFaixaMip`

A regra é:

```text
DFI = base DFI * fator DFI
MIP = juros contratuais * fator MIP da faixa etária
seguro = DFI + MIP
```

## Helper central

Geração de cronograma, regeneração, amortização e ajuste de saldo devem usar `calcular_seguro_habitacional(...)`.

Não duplicar cálculo de seguro em rotas ou JavaScript como regra soberana. O JavaScript pode fazer prévia visual, mas a fonte de verdade é o backend.

## Rotas legadas

A tela antiga `/financiamentos/seguro` e as rotas `/api/financiamentos/<id>/seguros` permanecem como legado temporário.

A configuração oficial atual fica no formulário principal do financiamento. A UI principal não deve apontar para a tela legada.
