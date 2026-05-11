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

## Segurança

O upload valida extensão, MIME, assinatura básica, tamanho e nome de arquivo. O nome original nunca é usado como caminho físico.

Download e exclusão validam que o documento pertence ao financiamento solicitado e ao perfil financeiro ativo.

## Regra financeira

Upload, download e exclusão de documentos não alteram saldo, parcelas, pagamentos, amortizações, seguros nem status do financiamento.

## Pendências futuras

- `FIN-DOC-FIN-2`: vínculo opcional com parcela, amortização ou ajuste de saldo.
- `FIN-DOC-FIN-3`: leitura automática de demonstrativos CAIXA.
- `FIN-DOC-FIN-4`: storage externo e política avançada de backup.
