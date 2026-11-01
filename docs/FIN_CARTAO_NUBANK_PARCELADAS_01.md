# FIN-CARTAO-NUBANK-PARCELADAS-01 — Compras parceladas na importação do Nubank

**Situação (01/11/2026): `FIN_CARTAO_NUBANK_PARCELADAS_01_PUBLICADO`.** Publicado em 01/11/2026 no FIN-CARTAO-NUBANK-PUBLICACAO-01: push `87ba747..3e09635`, migrations `20261211090000` e `20261212090000` aplicadas e conferidas (51 → 53, nenhum dado existente alterado), deploy `abd08b7a` (produção, commit `3e09635`, 165/165 arquivos iguais ao build). Homologação só de leitura: as prévias dos arquivos reais de 11/2026 batem com o ensaio; nenhuma importação confirmada.
- A regularização das parcelas de 11/2026 (Black e Visa, pela tela) aguarda autorização.

Base: commit `87ba747`, migrations até `20261210090000` (`docs/FIN_CARTAO_IMPORTACAO_FIXAS_01.md`, `docs/FIN_CARTAO_DESPESAS_FIXAS_01.md`).

## 1. Causa confirmada

A fatura Nubank de 11/2026 (Master Card Black, 387) foi importada em 31/10/2026 pelo novo aplicativo.

**O que aconteceu com as linhas do arquivo (106):**

| Linhas | Valor | Destino |
|---|---|---|
| 89 compras à vista | R$ 7.194,80 | gravadas |
| 12 parcelas | R$ 2.458,40 | **não gravadas** |
| 4 créditos | R$ 53,40 | não importados, por regra |
| 1 pagamento | — | não importado, por regra |

- **Registro da operação:** `inseridos 89, duplicados 0`.
- **As 12 parcelas não chegaram ao banco.** Não estão gravadas nem como compra comum.

**Onde o defeito ocorre**, na ordem do fluxo:

| Etapa | Situação |
|---|---|
| Leitura do arquivo e extração da parcela | correta: `importacao-csv.js` lê "Loja - Parcela 3/10" como 3/10 |
| Regra de classificação no banco | correta: a parcela vira `PARCELADA` |
| **Envio pela interface** | **defeito.** O confronto da tela (`montarAnaliseConfronto`) põe toda linha com padrão de parcela no grupo "possíveis parcelamentos" e a retira da confirmação. É o MVP herdado do Flask; a confirmação até dizia "Possiveis parcelamentos fora deste MVP: 12". Só o botão "Criar parcelamento", linha a linha, gravava a parcela. |
| Gravação | correta para o que recebe |
| Leitura das compras já importadas | correta |

**Problemas encontrados no caminho e corrigidos no mesmo pacote:**
- A Categoria de Despesa pendente transformava a classificação em `REVISAR` e escondia a natureza da linha.
- As 12 parcelas não tinham categoria sugerida, e a tela não oferecia como informá-la.
- A parcela já cadastrada só era reconhecida com datas a até 5 dias. O Nubank data a parcela, da 2ª em diante, pelo início do ciclo da fatura, não pela data da compra.
  - Exemplo: na fatura de 09/2026, "Haikar Veiculos - Parcela 3/6" vem com 29/07, início de "TRANSAÇÕES DE 29 JUL A 29 AGO".
  - A parcela que o aplicativo gera ou cadastra fica com a data da compra mais um mês. Ela não seria reconhecida no mês seguinte e seria duplicada.
- Na classificação da importação, a despesa fixa vinha antes da parcelada. A precedência definida é Parcelada → Fixa → Categoria do Cartão → Outros.

## 2. Formatos do Nubank

- **Arquivo:** CSV `date,title,amount`, separador vírgula, valor com vírgula decimal entre aspas (`"79,70"`), crédito com sinal e espaço (`"- 50,22"`).
- **Parcela:** no fim do título, `Nome - Parcela N/M`, da primeira à última.
- **Data da 1ª parcela:** a da compra.
- **Data da 2ª parcela em diante:** o início do ciclo da fatura (28/09/2026 em 11/2026; 29/07/2026 em 09/2026).
- **Outros números no título não são parcela:** "Allianz Segu*02 de", "Pao de Acucar-2378", "IOF de "Dramawave"".
- **Créditos:** "Pagamento recebido", "Estorno de …", "IOF de volta de …".
- **PDF do Nubank:** não é lido pelo importador; o leitor de PDF aceita o layout da Caixa. O mesmo padrão "- Parcela N/M" aparece no PDF.

## 3. Correção

**Leitor do arquivo (`web/src/js/importacao-csv.js`), perfil Nubank:**
- só `Nome - Parcela N/M` no fim do título é parcela;
- outro N/M no título ("MERCADO XYZ 03/10") vai como `parcela_ambigua`: a linha fica 1/1, nenhum número é inventado, e o usuário decide;
- Caixa e mapeamento manual seguem a regra do Flask.

**Prévia no banco (migration `20261211090000`, gerada por `scripts/gerar_migration_cartao_nubank_parceladas.py`; só `analisar_importacao_cartao` muda):**
- **Parcela já lançada** (manual, gerada por parcelamento ou importada): reconhecida pela mesma parcela N/M, com o mesmo valor, na mesma fatura, sem a regra de 5 dias. Entre duas candidatas, fica a de mesma descrição. Continua valendo "Manter como compra diferente".
- **Parcelada antes de Fixa:** a parcela não é reconhecida como recorrência, nem pode ser escolhida como uma (pede revisão).
- **Categoria pendente não esconde a natureza:** a linha continua `PARCELADA`, `COMPRA` ou `DESPESA_FIXA`, com `categoria_pendente`. `REVISAR` fica para dúvida sobre a própria linha.
- **Número ambíguo:** `REVISAR` até a decisão (`natureza_parcela` PARCELADA, com o número do texto, ou AVISTA). A importação recusa a linha sem decisão. Na reimportação, a parcela decidida é reconhecida.
- **Parcela não pede Categoria do Cartão** e não consome limite (natureza `PARCELADA`).
- **Confirmação** (`importar_fatura_cartao`): não muda. Grava o que a análise, refeita sob as travas, classifica. A parcela é gravada com número, total, descrição, valor, data, cartão e competência; as futuras só com "Criar parcelamento".

**Tela (`importar_cartao.js`, só nos campos novos; linha do Flask sem eles fica como antes):**
- **Status na linha:** "Compra parcelada", sugestão "Parcela 05/06", Categoria da despesa editável. A linha entra na confirmação e na contagem de "Criar despesas (N)".
- **Número ambíguo:** "Revisar · Possível parcela 03/10: parcelada ou à vista?", com ações compactas "Confirmar parcela 03/10" e "Tratar como compra à vista". Sem decisão, a confirmação é bloqueada.
- **"Criar parcelamento"** (gerar as futuras) continua na linha.
- **Mensagem de confirmação:** "Compras parceladas: N".
- **"Manter como compra diferente"** numa parcela: a linha volta como compra parcelada. Antes ficava retida.

## 4. Compras históricas (produção, só leitura)

| Verificação | Resultado |
|---|---|
| Compras do Nubank (Black) gravadas | 92 (89 importadas em 31/10, 3 previsões do Plano NullCel) |
| Potencialmente parceladas entre as gravadas | 0: as 89 batem uma a uma com as linhas à vista do arquivo |
| Classificadas como compra comum por engano | 0 |
| Com informação de parcela gravada | 0 no Black; 1 no Visa (Anuidade do Cartão 5/12, PDF da Caixa, já `PARCELADA`) |
| Que precisam de correção de dados | nenhuma alteração: faltam 12 parcelas, de R$ 2.458,40 no total |

As 12 parcelas que faltam, todas na fatura 11/2026:

| Linha | Valor |
|---|---|
| Shopee*Classic Comerci 1/2 | R$ 79,70 |
| Farmacias Pa*Paguemeno 1/2 | R$ 43,29 |
| Farmacias Pa*Paguemeno 1/2 | R$ 80,31 |
| Pb*Truesource 1/2 | R$ 94,93 |
| Pb*Truesource 2/2 | R$ 197,49 |
| Fernando Bicicletas Ei 2/2 | R$ 279,50 |
| Haikar Veiculos 5/6 | R$ 416,81 |
| Doce Paladar 2/3 | R$ 145,50 |
| Anacapri Goiania 3/3 | R$ 83,30 |
| Detroit T9 2/4 | R$ 314,07 |
| Mlp *Magalu-Samsung 9/10 | R$ 482,80 |
| Statusfestas 2/2 | R$ 240,70 |

## 5. Valores (Black, 11/2026)

| | Hoje (produção) | Depois da regularização (ensaio na cópia) |
|---|---|---|
| Executado | R$ 7.194,80 | R$ 9.653,20 |
| Compras parceladas | — | R$ 2.458,40 (12) |
| Categorias do Cartão (gasto) | R$ 4.312,25 | R$ 4.312,25 |
| Sem Categoria do Cartão | R$ 2.882,55 | R$ 2.882,55 |
| Disponível nos limites | R$ 337,75 | R$ 337,75 |
| Previsto (lista de Despesas) | R$ 8.889,84 | R$ 11.348,24 |

- **Visa:** igual (executado R$ 2.265,85; previsto pendente R$ 329,60; Netflix 580 + 606 sugerida, −R$ 15,00).
- **Não mudam:** faturas pagas, movimentos e contas bancárias.
- **Diferença para o boleto:** a fatura do arquivo soma R$ 9.599,80, porque os 4 créditos não são importados por regra (estorno Apple R$ 50,22 e IOF de volta R$ 3,18). O aplicativo fica com R$ 9.653,20, R$ 53,40 acima. É assunto à parte (pendência 2 da seção 8).

## 6. Testes

- **`tests/test_supabase_cartao_nubank_parceladas.py`** (15):
  - parcela cadastrada com a data do ciclo;
  - parcela gerada pelo parcelamento reconhecida no mês seguinte;
  - desempate pela descrição;
  - parcela nova primeira, intermediária e última, com os dados preservados e a natureza `PARCELADA`;
  - categoria pendente;
  - número ambíguo e a decisão;
  - decisão reconhecida na reimportação;
  - à vista, despesa fixa e Parcelada antes de Fixa;
  - reimportação integral e complementar;
  - repetidas legítimas;
  - fatura paga preservada, com a parcela na próxima aberta;
  - limites por categoria e executado;
  - reversão e reaplicação da migration.
- **`tests/test_gerador_migration_cartao_nubank_parceladas.py`** (2).
- **`web/tests/unit/importacao-csv.test.mjs`:** o padrão do Nubank, com títulos fictícios no formato real.
  - Ajustados: o caso Nubank `Loja 1/3` passa a ser ambíguo, como pede o contrato; o arquivo XLSX com cabeçalho Nubank usa `Loja - Parcela 2/5`.
- **`web/tests/unit/importar-parceladas.test.mjs`** (5), com o `importar_cartao.js` real:
  - a parcela entra na confirmação;
  - categoria obrigatória;
  - número ambíguo;
  - "Manter" numa parcela;
  - linha do Flask como antes.
- **`web/tests/e2e/importar_parceladas.spec.mjs`** (1), pela tela, com CSV no formato Nubank: parcela nova, parcela cadastrada reconhecida, número ambíguo decidido, confirmação, naturezas e reimportação sem nada novo.
- **Ajustado:** `tests/test_supabase_recorrencia_cartao.py`, porque a análise vigente passa a ser a da 1211.
- **Regressão:**
  - Python por impacto: 115 arquivos, 1607 aprovados, 7 pulados; a única falha é a i3, dívida conhecida de `regularizar_historico`;
  - unitários 49/49;
  - E2E 118/118.

## 7. Ensaio (cópia fiel e descartável da produção)

| Conferência | Resultado |
|---|---|
| Cópia × produção | idêntica |
| Migration 1211 (md5 `5000de8e…`) | compras, faturas, movimentos e contas bancárias iguais; leituras de Cartões e Despesas iguais |
| Prévia do arquivo Nubank real (106 linhas, leitor novo) | 89 `JA_EXISTENTE`, 12 `PARCELADA` (todas com N/M, categoria pendente), 5 `IGNORADA`; nenhuma ambígua |
| Regularização simulada (categoria de ensaio nas 12; confirmação oficial) | 12 inseridas, 89 duplicadas protegidas; executado R$ 7.194,80 → R$ 9.653,20; grupo "Compras parceladas" R$ 2.458,40; categorias e disponível iguais |
| Reimportação | 12 `PARCELA_EXISTENTE`, 89 `JA_EXISTENTE`; "Nenhuma linha para importar" |
| Visa (despesas fixas) | igual antes e depois |

## 8. Pendências

1. **Regularização das 12 parcelas de 11/2026**, depois da publicação e com autorização:
   - reimportar o mesmo arquivo `Nubank_2026-11-05.csv` na tela, no Black, competência 11/2026;
   - as 89 compras aparecem como já existentes; as 12 parcelas, como Compra parcelada;
   - informar a Categoria da despesa de cada uma e confirmar.
   - Grava só as 12, sem alterar nenhuma compra existente. A confirmação é idempotente e recusa a segunda vez.
   - Antes e depois, retrato só de leitura.
   - Pagamentos, faturas pagas, movimentos e saldos não mudam.
2. **Créditos da fatura** (estorno e IOF de volta): resolvido no FIN-CARTAO-NUBANK-CREDITOS-01 (`docs/FIN_CARTAO_NUBANK_CREDITOS_01.md`). Lá também: o Visa 11/2026 tem a mesma falha (11 parcelas e a Netflix R$ 59,90 não gravadas), e a regularização das duas faturas é feita junto.
3. **Plano NuCel:** a cobrança de R$ 70,00 (compra 652) foi importada como compra comum. A previsão "Plano NullCel" de 11/2026 continua pendente: o nome difere. É candidata à conciliação pela tela (como a Netflix), ou a um apelido.
4. **Parcelas futuras:** a importação grava só a parcela da fatura. As futuras, quando desejadas, ficam com "Criar parcelamento". Nos meses seguintes, a parcela do arquivo é reconhecida.
5. Netflix 11/2026 e apelido da Apple One: seguem como antes, cada um com autorização própria.
