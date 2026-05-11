# Documentos do financiamento

## Decisão

Documentos de financiamento usam metadados no banco e arquivo físico no filesystem local.

Arquivos fiscais de IR não são reaproveitados porque o contexto documental é diferente: aqui o vínculo principal é o contrato de financiamento.

## Armazenamento

- Pasta base: `data/uploads/financiamentos/{financiamento_id}/documentos/`
- Nome físico: `{uuid}.{extensao}`
- Metadados: tabela `financiamento_documento`
- Hash: SHA-256 do conteúdo enviado
- Limite: 10 MB por arquivo

A pasta `data/uploads/financiamentos` deve fazer parte do backup operacional. Ela não deve ser versionada no Git.

## Tipos aceitos

- contrato
- demonstrativo_valores_cobrados
- demonstrativo_evolucao
- boleto
- comprovante_pagamento
- comprovante_amortizacao
- seguro_habitacional
- extrato_anual
- quitacao
- outros

## Vínculos opcionais

Um documento pode ficar vinculado somente ao financiamento ou também a um evento específico:

- `parcela_id`
- `amortizacao_id`
- `ajuste_saldo_id`
- `competencia`
- `ano_base`
- `data_documento`

Esses vínculos são metadados documentais e não alteram parcelas, amortizações ou ajustes.

## Conferência CAIXA

Documentos podem ser usados como base de conferência manual CAIXA. O usuário registra valores reais do demonstrativo e o sistema busca, quando possível, a parcela correspondente no cronograma para comparar:

- amortização
- juros
- seguro
- taxa administrativa
- total
- saldo devedor

A conferência fica na tabela `financiamento_conferencia_caixa` e calcula diferenças como `real - simulado`.

## Conferência de quitação

A conferência de quitação reaproveita `financiamento_conferencia_caixa` com `tipo_conferencia = quitacao`.

Ela registra:

- valor oficial informado pelo banco;
- valor simulado pelo app;
- diferença em reais e percentual;
- data da proposta;
- validade da proposta, quando informada;
- documento vinculado, quando houver;
- observação.

A validade da proposta fica registrada na observação neste MVP. A conferência não quita o financiamento, não baixa parcelas, não cria conta de pagamento, não cancela parcelas futuras e não altera saldo.

## Segurança

O upload valida extensão, MIME, assinatura básica, tamanho e nome de arquivo. O nome original nunca é usado como caminho físico.

Download e exclusão validam que o documento pertence ao financiamento solicitado e ao perfil financeiro ativo.

## Regra financeira

Upload, download, exclusão e conferência de documentos não alteram saldo, parcelas, pagamentos, amortizações, seguros nem status do financiamento.

Se a conferência indicar diferença relevante entre banco e sistema, o ajuste do saldo devedor continua sendo uma ação separada e explícita.

## Pendências futuras

- `FIN-DOC-CAIXA-2`: importação manual em lote de linhas de demonstrativos.
- `FIN-DOC-CAIXA-3`: leitura automática/OCR de demonstrativos CAIXA.
- `FIN-DOC-FIN-4`: storage externo e política avançada de backup.
- `FIN-QUIT-OPER-1`: quitação operacional do financiamento.
