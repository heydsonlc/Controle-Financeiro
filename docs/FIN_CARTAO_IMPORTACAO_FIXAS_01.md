# FIN-CARTAO-IMPORTACAO-FIXAS-01 — Despesas fixas na importação da fatura: reconhecimento, classificação e conciliação

**Situação (01/11/2026): `FIN_CARTAO_IMPORTACAO_FIXAS_01_PUBLICADO`.** Publicado em 01/11/2026 no FIN-CARTAO-CONSOLIDACAO-PUBLICACAO-01, junto com o FIN-CARTAO-PREVISTO-EXECUTADO-01: push `a1d3be4..87ba747`, migrations `20261209090000` e `20261210090000` aplicadas e conferidas (49 → 51, nenhum dado existente alterado), deploy `3ce04e95` (produção, commit `87ba747`).
- Homologação só de leitura em produção (nenhuma importação confirmada): reimportação do Visa 11/2026 com 13 `JA_EXISTENTE` e a conciliação da Netflix sugerida (580 + 606, diferença −R$ 15,00); APPLE.COM/BILL como compra comum e, escolhida a Apple One, como despesa fixa com o apelido só sugerido; compra casada pelo valor com "Manter como compra diferente"; segunda cobrança da Netflix em revisão.
- A conciliação real da Netflix 11/2026 continua fora.

Base: `docs/FIN_CARTAO_DESPESAS_FIXAS_01.md` e `docs/FIN_CARTAO_PREVISTO_EXECUTADO_01.md` (publicados).

## 1. Antes

- **No banco:** a análise da importação já reconhecia a despesa fixa e realizava a previsão na confirmação.
- **Na tela:** a linha reconhecida não aparecia como despesa fixa.
  - O vínculo a uma recorrência escolhida respondia "em migração".
  - Uma cobrança que o banco não podia conciliar (segunda cobrança do mês, previsão já cobrada, fatura paga) saía da efetivação como "já lançada", em silêncio.
  - Uma cobrança já importada como compra comum não podia ser conciliada pela importação.

## 2. Prévia (`analisar_importacao_cartao`, só leitura)

**Classificação proposta em cada linha (`classificacao_importacao`):**

| Classificação | Quando | Na tela |
|---|---|---|
| `JA_EXISTENTE` | a mesma compra já gravada (reimportação), ou conciliada pelo valor com compra lançada | retirada, "Duplicado / Já existe" |
| `PARCELA_EXISTENTE` | a mesma parcela já gravada | retirada |
| `DESPESA_FIXA` | recorrência ativa do cartão reconhecida pelo nome, por apelido ou pela escolha do usuário | "Despesa fixa · Netflix · previsto R$ 59,90 · cobrado R$ 44,90 · diferença −R$ 15,00 · fatura 11/2026" |
| `PARCELADA` | parcela nova | "Parcelado" (fluxo de parcelamento existente) |
| `COMPRA` | compra comum (Categoria do Cartão ou Outros pelas regras atuais) | "Novo" |
| `REVISAR` | ambígua, segunda cobrança do mesmo serviço, previsão já cobrada, em fatura paga ou consolidada, escolha inválida | "Revisar", com o motivo; bloqueia a confirmação até a decisão |

- **Ordem do reconhecimento:** duplicidade (identidade da compra), depois parcela já lançada (mesmo valor, mesma parcela, até 5 dias, regra existente), depois despesa fixa, depois compra comum.
- **Reconhecimento da fixa:** regras do FIXAS-01 (mesmo cartão, nome ou apelido por palavras inteiras, valor só para desempate).
  - Recorrência **inativada** com previsão pendente na competência ainda reconhece a cobrança.
  - O mesmo nome não basta para duas cobranças: a segunda pede revisão.
- **Detalhe da fixa (`despesa_fixa`):** recorrência, previsto, cobrado, diferença, competência, fatura de destino e a previsão que será realizada.
- **Conciliação sugerida (`conciliacao_sugerida`):** se a linha é uma compra comum já lançada que corresponde à previsão pendente da recorrência, a prévia mostra previsão, cobrança, previsto, cobrado e diferença.
- **Recorrências do cartão (`recorrencias_cartao`):** as que a tela pode escolher.
- **Correções aceitas na prévia** (nada gravado antes da confirmação):
  - `recorrencia_escolhida_id`: outra recorrência do cartão, ou 0 = compra comum;
  - `salvar_apelido`: lembrar a descrição da cobrança como apelido da recorrência escolhida;
  - `conciliar_previsao`: conciliar a compra já lançada com a previsão;
  - `manter_duplicada`: duas compras iguais legítimas no mesmo arquivo.

## 3. Confirmação (`importar_fatura_cartao`)

Tudo numa transação, com a análise refeita sob as travas (idempotente pela chave, protegida contra importações concorrentes):
- **Despesa fixa com previsão pendente:** realiza a previsão. O executado passa a ser o cobrado; o previsto fica guardado; o valor-base da recorrência não muda; há uma ocorrência só.
- **Despesa fixa sem previsão no mês:** a compra entra como ocorrência da recorrência, e o gerador não a lança de novo.
- **Compra já lançada com conciliação pedida:** concilia com a previsão (`conciliar_previsao_interna`). A compra absorvida fica inteira na auditoria; a reversão é pela função oficial.
- **Apelido pedido:** registrado (`registrar_apelido_recorrencia`, mesmas regras de `criar_apelido_recorrencia`).
- **Compra comum e parcelada:** gravadas como antes, executadas uma vez.
- **Já existente:** nada gravado nem sobrescrito.
- **Se algo falha:** nada fica gravado.

## 4. Tela (`importar_cartao.js` do Flask, só com os campos novos; no Flask nada muda)

- **Linha:** status "Despesa fixa" ou "Revisar", tipo "Despesa fixa" e o resumo previsto · cobrado · diferença · fatura.
- **Seletor compacto de recorrência** em toda linha da prévia que não é parcela: automática, outra recorrência do cartão, ou compra comum.
- **"Lembrar esta descrição":** aparece quando a recorrência foi escolhida.
- **Ação "Tratar como compra comum"** na despesa fixa.
- **Linhas retiradas:** a compra já lançada mostra a conciliação proposta, com "Conciliar com a previsão" marcado, e pode ser desmarcada.
- **Confirmação:** envia novos, despesas fixas e conciliações. A mensagem mostra "Despesas fixas reconhecidas" e "Compras já lançadas conciliadas".
- **Revisão:** uma despesa fixa em revisão impede confirmar até a decisão.
- **"Manter como compra diferente"** na linha retirada pela regra herdada: a compra casada pelo valor com outra já lançada (mesmo valor e parcela, até 5 dias) ou repetida no próprio arquivo volta como compra nova. A decisão vai na confirmação (`manter_conciliada` / `manter_duplicada`), e o banco a respeita. A mesma compra reimportada não tem essa ação.
- **Ponte de CSP (`ponte-csp.js`):** passa a aceitar `this.checked`. As caixas de seleção da tela original não funcionavam no novo aplicativo.

## 5. Testes

- **`tests/test_supabase_cartao_importacao_fixas.py`** (18, incluindo a compra casada pelo valor mantida como diferente):
  - prévia classificando as 6 naturezas sem gravar;
  - escolha de recorrência com apelido gravado só na confirmação e reconhecido no mês seguinte;
  - compra comum;
  - escolha inválida;
  - conciliação da compra já lançada (executado igual, reimportação e reversão);
  - concorrência na conciliação;
  - reimportação integral e complementar, com mesma chave;
  - repetida no arquivo;
  - duas cobranças do mesmo serviço;
  - ambiguidade resolvida pela escolha;
  - recorrência inativada;
  - fatura fechada e paga;
  - parcelada nova e reimportada;
  - sem permissão;
  - funções internas;
  - reversão e reaplicação da migration.
- **`tests/test_gerador_migration_cartao_importacao_fixas.py`** (2).
- **`web/tests/unit/importar-fixas.test.mjs`** (5), com o `importar_cartao.js` real: conversão (Flask sem os campos fica como antes), linha da fixa, seletor, conciliação proposta, correção e o que vai na confirmação.
- **`web/tests/e2e/importar_fixas.spec.mjs`** (1), pela tela no banco descartável: fixa reconhecida, escolha da recorrência com "Lembrar", segunda cobrança em revisão tratada como compra comum, confirmação, naturezas gravadas, apelido e reimportação sem nada novo.

- **Ajustados à regra** (cobrança em fatura paga ou consolidada, ou já cobrada, pede revisão em vez de sair em silêncio):
  - 2 testes de `tests/test_supabase_cartao_despesas_fixas.py`;
  - 1 de `tests/test_supabase_cartao_previsto_executado.py`;
  - 1 de `tests/test_supabase_recorrencia_cartao.py` (a análise vigente passa a ser a da 1210).
- **Regressão:**
  - Python por impacto: 30 arquivos, 625 aprovados; a única falha é a i3, dívida conhecida de `regularizar_historico`;
  - unitários 43/43;
  - E2E 117/117 (e os de importação de novo depois da ação "Manter", 5/5).

## 6. Ensaio (cópia fiel e descartável da produção, com 1209 e 1210)

| Conferência | Resultado |
|---|---|
| Cópia × produção | idêntica |
| Migrations 1209 (md5 `e0354acd…`) e 1210 (md5 `965ed1f4…`) | compras, faturas, movimentos e contas bancárias iguais |
| Reimportação do Visa 11/2026 (13 cobranças reais) | 13 `JA_EXISTENTE`; a Netflix (`NETFLIX ENTRETENIMENTO BARUERI`) com a conciliação sugerida: previsão 580 (R$ 59,90) + compra 606 (R$ 44,90), diferença −R$ 15,00 |
| Confirmação com a conciliação (só na cópia) | 1 conciliada, 0 inseridas; executado **R$ 2.265,85** (igual, sem duplicidade); previsto R$ 2.767,75 → R$ 2.752,75; aguardando cobrança R$ 329,60 → R$ 269,70; Netflix CONFIRMADA (previsto 59,90 / executado 44,90) |
| Reversão da conciliação (cópia) | previsão de volta, compra 606 de volta; compras idênticas às de antes |
| Reimportação do Black 11/2026 (89 cobranças) | 89 `JA_EXISTENTE` |
| As mesmas linhas como fatura nova de 12/2026 | Visa: a Netflix reconhecida automaticamente (realiza a previsão de 12/2026, diferença −R$ 15,00); 12 compras comuns com a mesma Categoria do Cartão de hoje. Black: 89 compras comuns, todas com a mesma Categoria do Cartão; nenhuma vira despesa fixa |
| Movimentos e contas bancárias | não mudam em nenhum passo |

## 7. Pendências

- **Netflix 11/2026 em produção:** pode ser feita pela própria tela, reimportando a fatura com "Conciliar com a previsão", ou pela função oficial, com autorização.
- **Apelido da Apple One:** pela tela ("Lembrar esta descrição"), com autorização.
- **Conciliação por valor de compra comum ou parcela** (mesmo valor e parcela, até 5 dias, regra herdada do Flask): continua. A tela mostra "Já existe" e oferece "Manter como compra diferente" (corrigido no FIN-CARTAO-CONSOLIDACAO-PUBLICACAO-01: a opção existia no banco, mas não na tela).
