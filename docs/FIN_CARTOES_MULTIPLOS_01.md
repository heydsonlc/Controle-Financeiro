# FIN-CARTOES-MULTIPLOS-01 — Contratos com vários cartões, fatura consolidada e reconstrução das importações

**Situação (02/11/2026): `FIN_CARTOES_MULTIPLOS_PUBLICACAO_01_PREPARADO`.** Implementado, testado e ensaiado numa cópia fiel da produção, inclusive com o PDF real do Nubank de 11/2026 (seção 6).
- A publicação (push, migration `20261213090000`, deploy) aguarda autorização expressa.
- A limpeza real, a reconstrução das faturas de 11/2026 e o registro dos pagamentos também aguardam autorização.

Base: `3e09635` (publicado), commit documental local `f913a79`, migrations até `20261212090000`.

## 1. Modelo anterior e novo

**Antes:**
- O "cartão" era o contrato: `public.item_despesa` (tipo Agregador) com `public.config_agregador` (dias, limite e o número herdado do Flask, do qual o novo aplicativo só mostra o final).
- Uma fatura por contrato e competência (`public.conta`), um pagamento e os limites de Categoria do Cartão.
- Não havia cartão físico, virtual ou adicional.
- A compra (`public.lancamento_agregado`) apontava só para o contrato.

**Agora (menor evolução segura):**
- O contrato continua o mesmo, com a fatura, o pagamento e os limites únicos. Nada foi reescrito.
- **`financeiro.cartao_vinculado`** (nova) guarda os cartões do contrato:
  - identificação, os 4 últimos dígitos, tipo (físico, virtual, adicional) e portador;
  - situação (ativo, cancelado, substituído), datas de início e de cancelamento, e o cartão substituto.
  - Nunca número completo, validade ou CVV: o banco recusa esses campos.
  - O cartão não é excluído: cancelado ou substituído, continua no histórico. O final de um cartão com compras não muda.
- **Cartão de origem:** `public.lancamento_agregado.cartao_vinculado_id` e `financeiro.credito_fatura.cartao_vinculado_id` (novas, nascem vazias; null = sem cartão identificado).
- **Integridade** (gatilhos): o cartão vinculado é do perfil do contrato; o substituto, do mesmo contrato; a compra e o crédito, só de um cartão do próprio contrato.
- **Acesso:** RLS forçada e sem acesso direto do navegador. Tudo passa por funções que conferem o perfil e o escritor único.

## 2. Tabelas e funções

**Migration `20261213090000`**, gerada por `scripts/gerar_migration_cartoes_multiplos.py`. Reversão em `supabase/reversao/20261213090000_cartoes_multiplos_anterior.sql`, recusada com cartão vinculado cadastrado.

| Objeto | O que é |
|---|---|
| `financeiro.cartao_vinculado` | nova tabela |
| colunas `cartao_vinculado_id` | novas, nas compras e nos créditos |
| gatilhos `conferir_cartao_vinculado` e `conferir_cartao_da_compra` | integridade entre perfil, contrato e cartão |
| `cartoes_vinculados` (leitura) e `salvar_cartao_vinculado` (cadastro e edição, com versão) | novas, para a tela de Cartões |
| `fatura_por_cartao` (interna) | a fatura do contrato por cartão |
| `previa_limpeza_importacoes` (leitura) e `limpar_importacoes_cartao` | limpeza seletiva (seção 7) |

Funções existentes alteradas (texto de `20261212090000` mais os trechos marcados):
- **`analisar_importacao_cartao`:**
  - cartão de origem pelo final do arquivo ou pela escolha na prévia;
  - duplicidade e conciliação que distinguem cartões;
  - a lista `cartoes_contrato`;
  - nas validações, `cartoes_nao_cadastrados` e `sem_cartao_identificado`;
  - categoria da compra reconstruída (seção 7).
- **`importar_fatura_cartao`:**
  - grava o cartão de origem na compra, na previsão realizada e no crédito;
  - a fatura já importada de um tipo de arquivo (PDF ou planilha CSV/XLSX) não recebe linhas novas do outro, porque são a mesma fatura (seção 4). A prévia mostra `fontes_importadas`;
  - na reconstrução, o crédito cuja compra original veio no mesmo arquivo é vinculado na confirmação, quando a candidata é única (a da prévia ainda não estava gravada).
- **`fatura_por_categoria`:** devolve `por_cartao`.
- **`lancamentos_fatura_por_categoria`:** o cartão de cada compra e crédito, e o filtro `cartao-<id>` (`cartao-0` = sem cartão).

## 3. Fatura consolidada

- **Uma fatura e um pagamento por contrato e competência.** Pagamento, Despesas, Dashboard e limites continuam no contrato.
- **Tela de Cartões:** "Por cartão" mostra compras, créditos e total de cada cartão vinculado. O que não tem cartão identificado aparece numa linha própria, por exemplo créditos e ajustes que o documento não atribui.
- **A soma das linhas é o valor a pagar.** "Ver lançamentos" filtra por cartão.
- **Limites:** os de Categoria do Cartão são compartilhados entre os cartões do contrato.
- **Pagamento:** continua único (`pagar_fatura`), no valor líquido.
  - Uma segunda tentativa é recusada, e a mesma chave devolve o mesmo resultado.
  - Para os pagamentos já feitos fora do aplicativo: usar Despesas → pagar fatura, com a data real e a conta de débito correta. Nada mudou nessa estrutura.

## 4. Identificação do cartão por arquivo

| Arquivo | Cartão de origem |
|---|---|
| **PDF da Caixa** | o leitor já trazia o cartão do grupo ("COMPRAS (Cartão 7136)"). Agora a importação o usa. Créditos antes do cartão ficam sem cartão. |
| **PDF do Nubank** | leitor novo (`parseTextoNubank`): cada compra traz "•••• 6830" (titular) ou "•••• 6030" (adicional). Linhas sem cartão no documento (IOF, crédito, serviço como o Plano NuCel, pagamento) ficam sem cartão identificado: não é presumido nem a seção do titular. Conferido com os PDFs reais de 09/2026 (somas por cartão iguais aos subtotais do documento) e de 11/2026 (seção 6). |
| **CSV do Nubank** | `date,title,amount`: não traz o cartão. As linhas ficam sem cartão identificado. A prévia oferece a escolha por linha e para as selecionadas. |
| **CSV da Caixa ou manual** | sem cartão; escolha na prévia |

**Regras:**
- Final não cadastrado: a linha entra sem cartão, com aviso ("cadastre o cartão ou escolha"). Não bloqueia as demais.
- Escolha de cartão de outro contrato: Revisar.
- Duplicidade: compras idênticas de cartões diferentes não se confundem, nem no arquivo nem no banco. A mesma compra reimportada continua sendo a mesma. Compra antiga sem cartão casa com qualquer uma.

**PDF e CSV são a mesma fatura** (nunca duas fontes de compras):
- comparados linha a linha, 100 das 106 linhas do Nubank de 11/2026 são iguais (data, valor, descrição, parcela);
- o resto: dois IOF arredondados diferente (Dramawave R$ 1,47 no PDF, R$ 1,46 no CSV; Cloudflare R$ 1,00 e R$ 0,99, com os "IOF de volta" iguais a cada um) e duas descrições (o estorno da Apple e o pagamento);
- o total líquido é o mesmo, R$ 9.599,80;
- por isso a confirmação recusa linhas novas do outro tipo de arquivo. A reconstrução pelo PDF, numa fatura já importada pelo CSV, exige a limpeza seletiva antes.

**Tela de importação:**
- seletor compacto "Cartão de origem" sob a descrição (`•••• 7136 · virtual (arquivo)`, cancelado marcado);
- "Cartão de origem das selecionadas" acima da tabela;
- só aparecem com cartões cadastrados no contrato. Sem eles, ou no Flask, a tela fica como antes.

**Tela de Cartões:**
- "Cartões do contrato" no detalhe do contrato: final, identificação, tipo, portador, situação, substituto e uso;
- "Adicionar cartão" e editar, em modal compacto.

## 5. Testes

- **`tests/test_supabase_cartoes_multiplos.py`** (18):
  - PDF e planilha da mesma fatura: a prévia mostra a fonte já importada, e a confirmação do outro tipo é recusada;
  - crédito e compra original no mesmo arquivo: o IOF devolvido é vinculado na confirmação, e o estorno com várias candidatas fica sem vínculo;
  - cadastro, cancelamento e substituição; versão, final repetido e dados sensíveis recusados;
  - final de cartão com compras não muda;
  - cartão pelo final do arquivo, nunca presumido; final não cadastrado; escolha e escolha inválida;
  - compras idênticas de cartões diferentes; reimportação;
  - dois cartões numa fatura, por cartão, e pagamento único;
  - limite compartilhado;
  - parcela intermediária sem futuras; despesa fixa com o cartão; recorrências intactas;
  - créditos com e sem cartão, e o filtro por cartão;
  - prévia da limpeza (elegíveis, origem não comprovada, efeito na fatura e nas previsões);
  - limpeza só das importadas, com manuais, previsões, movimentos, saldos, recorrências e cartões intactos, auditoria, idempotência e reconstrução com a categoria;
  - fatura paga protege e interrompe;
  - prévia que mudou, acesso de outro usuário e perfil não Pessoal;
  - rollback de limpeza interrompida;
  - acesso cruzado entre perfis e contratos;
  - reversão e reaplicação;
  - o procedimento por script.
- **`tests/test_gerador_migration_cartoes_multiplos.py`** (2).
- **`web/tests/unit/importacao-nubank-pdf.test.mjs`** (2): o leitor do Nubank em texto e num PDF fictício; a Caixa continua com o seu leitor.
- **`web/tests/unit/importar-cartoes.test.mjs`** (3): seletor do cartão, escolha por linha e nas selecionadas, contrato sem cartões.
- **`web/tests/e2e/cartoes_multiplos.spec.mjs`** (1), pelas telas:
  - cartões cadastrados e cancelados no detalhe do contrato;
  - PDF fictício do Nubank importado com o cartão de cada compra;
  - fatura por cartão e "Ver lançamentos" por cartão.
- **Ajustados:**
  - `tests/test_supabase_recorrencia_cartao.py`: a análise vigente passa a ser a da 1213;
  - `web/tests/unit/build.test.mjs`: as duas RPCs novas liberadas.
- **Regressão:**
  - Python por impacto: 1730 aprovados, 7 pulados; a única falha é a i3, dívida conhecida de `regularizar_historico`;
  - unitários 59/59;
  - E2E 120/120.

## 6. Ensaio (cópia fiel e descartável da produção, com a 1213)

**Ensaio final (FIN-CARTOES-MULTIPLOS-PUBLICACAO-01)**, md5 da migration `c103b399…`. O Black foi reconstruído **só pelo PDF real** `Novembro 2026.pdf`, e o CSV depois dele foi recusado.

| Conferência | Resultado |
|---|---|
| Cópia × produção | idêntica; dados e leituras iguais depois da migration |
| Inventário | 102 elegíveis (Black 89, Visa 13), R$ 9.460,65; 1 de origem não comprovada; nenhum protegido |
| Black pelo PDF | 101 compras e 4 créditos: **R$ 9.599,80** (compras R$ 9.653,22 − créditos R$ 53,42) |
| Black por cartão | 6830: 44 compras, R$ 4.879,29. 6030: 53 compras, R$ 4.700,73. Sem cartão no documento: 4 compras R$ 73,20 e os créditos, R$ 19,78 |
| Parcelas do Black | as 12, cada uma com o seu cartão (2 do 6830, 10 do 6030) |
| Créditos do Black | 3 IOF devolvidos vinculados à cobrança de IOF do mesmo arquivo; estorno da Apple sem compra vinculada (5 candidatas); pagamento fora |
| CSV depois do PDF | recusado: "a fatura de 11/2026 já foi importada de outro tipo de arquivo" |
| Visa pelo PDF | **R$ 3.928,91**: 7136 R$ 2.064,00 (10), 0548 R$ 1.864,94 (15), créditos −R$ 0,03; todas as compras e parcelas importadas, inclusive as do 0548 (Adendo 01) |
| Categorias | 100 de 100 compras que existiam voltaram com a mesma categoria |
| Reimportação | nada novo nos dois contratos |
| Protegidos, faturas pagas, previsões | intactos |

**Ensaio anterior (FIN-CARTOES-MULTIPLOS-01, com o CSV do Nubank):**

| Conferência | Resultado |
|---|---|
| Cópia × produção | idêntica |
| Migration (md5 `9e629f5e…`) | dados existentes iguais (as colunas novas vazias); leituras de Cartões e Despesas iguais |
| Inventário da limpeza (todas as competências) | 102 compras elegíveis (Black 89, Visa 13), R$ 9.460,65; 0 créditos; 0 protegidos; 1 de origem não comprovada (Anuidade do Cartão Visa, 05/2026, R$ 17,25, sem registro da operação: fora) |
| Limpeza de 11/2026 (só na cópia) | 102 removidas; movimentos, saldos, recorrências, previsões, faturas pagas, financiamento, limites e categorias intactos |
| Cartões cadastrados | Visa: 0548 físico cancelado e 7136 virtual. Black: 6830 físico e 6030 adicional |
| Reconstrução do Visa (PDF real) | 24 compras, NETFLIX.COM confirmando a previsão 580 e 3 créditos de R$ 0,01: **R$ 3.928,91** |
| Reconstrução do Black (CSV real) | 101 compras e 4 créditos: **R$ 9.599,80**, todas sem cartão identificado (o CSV não traz o cartão) |
| Categorias de Despesa | 102 de 102 compras reconstruídas com a mesma categoria de antes |
| Disponível nos limites | igual ao de antes (R$ 337,75 e R$ 172,30) |
| Reimportação | nada novo nos dois contratos |

**Visa por cartão:**

| Cartão | Compras | Valor |
|---|---|---|
| 7136 (virtual) | 10 | R$ 2.064,00 |
| 0548 (cancelado) | 15 | R$ 1.864,94 |
| Sem cartão identificado | 3 créditos | −R$ 0,03 |

**Decisões simuladas no ensaio** (na produção, são do titular):
- categoria de ensaio onde não havia sugestão: só nas linhas novas;
- estorno da Apple sem compra vinculada;
- os dois ajustes repetidos mantidos;
- a segunda Netflix (R$ 44,90) tratada como compra comum. Depois da limpeza ela volta como "segunda cobrança" e pede essa decisão.

## 7. Limpeza seletiva e reconstrução

**Elegível:** só o que a importação registrou como seu (`financeiro.operacao_cartao` "importar_fatura": as compras inseridas e os créditos), ainda marcado como importado.
- Não basta nome, data, valor, categoria, cartão ou competência.
- Compra importada sem esse registro (Flask, versão anterior) é "origem não comprovada" e nunca entra.

**Protegidos** (interrompem a execução, sem remover nada):
- fatura paga ou consolidada;
- ocorrência de recorrência vigente;
- crédito de fora da seleção vinculado.

**Preservados sempre:** movimentos, saldos, receitas, despesas não importadas, compras manuais, recorrências e previsões, financiamentos, consórcios, categorias e limites, contratos e cartões, pagamentos e faturas pagas.

**Prévia** (`previa_limpeza_importacoes`, só leitura):
- compras e créditos elegíveis, protegidos, de origem não comprovada;
- por contrato e competência: quantidade, valores, valor a pagar atual e depois, previsões pendentes;
- uma impressão (hash).

**Execução** (`limpar_importacoes_cartao`):
- só no perfil Pessoal, pelo titular;
- refaz a prévia sob as travas e recusa se a impressão mudou;
- remove numa transação e recalcula as faturas;
- guarda as linhas removidas inteiras na operação (auditoria);
- é idempotente pela chave.

**Reconstrução:** reimportar o arquivo. A mesma compra (contrato, data, valor e descrição) volta com a Categoria de Despesa que tinha, lida da foto da limpeza.

**Procedimento:** `scripts/limpeza_importacoes_cartao.py`.
- `previa` (sessão só de leitura, inventário em arquivo);
- `executar` (exige o hash conferido e a confirmação literal "LIMPAR IMPORTACOES");
- não foi executado na produção.

## 8. Fatura Caixa Visa de 11/2026 (Adendo 01)

- **A fatura de R$ 3.928,91 é válida e já foi paga.** Todas as compras e parcelas dela são importadas, do 0548 e do 7136, sem excluir ou reduzir lançamentos pela contestação.
- **O físico 0548 foi cancelado depois da contestação.** O virtual 7136 continua ativo, e o novo físico será cadastrado quando chegar.
- **Parcelas futuras não são geradas pela importação.** Ela grava só a parcela da fatura do arquivo (teste "parcela intermediária sem futuras"). Assim, as parcelas contestadas que a Caixa deixar de cobrar a partir de 12/2026 simplesmente não virão nas próximas faturas.
  - Não há parcelamento a cancelar: na produção não há parcela futura do Visa.
  - Não usar "Criar parcelamento" (gerar as futuras) nas compras contestadas.
- **Ressarcimento:** será um crédito da fatura em que o banco o lançar, importado normalmente (FIN-CARTAO-NUBANK-CREDITOS-01). Nada é antecipado nem muda em 11/2026.

## 9. Recorrência SUPABASE SINGAPORE (produção, só leitura)

| Item | Valor |
|---|---|
| Recorrência 467 | R$ 225 mensal, criada em 02/11/2026; início 10/2026, vencimento 01/11 |
| Contrato | Black (387) |
| Previsões geradas | 709 (Black 11/2026) e 710 (Black 12/2026), pendentes |
| Cobrança real | compra 615, R$ 229,28 em 07/10/2026, no Visa 11/2026, cartão 7136 (mais o IOF de R$ 8,02) |

- **Duplicidade:** em 11/2026 o Supabase conta duas vezes no previsto: R$ 225 pendentes no Black e R$ 229,28 executados no Visa. Não é a mesma fatura, por isso a importação não as concilia.
- **Correção proposta (não feita):**
  - mudar o cartão da recorrência para o Visa (edição da recorrência);
  - dispensar pelo fluxo oficial as previsões pendentes do Black (709 e 710);
  - em 11/2026, conciliar a previsão do Visa com a compra 615 (diferença +R$ 4,28) ou deixá-la ser realizada na reconstrução.

## 10. Pendências para publicação e reconstrução real

1. **Publicação:** 1213, push e deploy, com autorização.
2. **Cadastro dos cartões** na tela de Cartões:

   | Contrato | Cartão | Tipo | Situação |
   |---|---|---|---|
   | Visa | 0548 | físico | cancelado |
   | Visa | 7136 | virtual | ativo |
   | Black | 6830 | físico (titular) | ativo |
   | Black | 6030 | adicional | ativo |

   O novo físico da Caixa é cadastrado quando chegar e marcado como substituto do 0548.
3. **Black:** reconstruir pelo PDF `Novembro 2026.pdf`, que traz o cartão de cada compra, depois da limpeza. Não usar o CSV junto: a confirmação recusa.
4. **Visa:** reconstruir pelo PDF de 05/11/2026 com todas as compras e parcelas (Adendo 01).
5. **Limpeza real de 11/2026, com autorização:**
   - novo inventário depois da publicação, pelo script, porque os números podem ter mudado;
   - conferência e execução com o hash;
   - depois, a reimportação dos dois PDFs com as decisões do titular: Categoria das linhas novas, estorno da Apple, ajustes repetidos e segunda Netflix.
6. **Pagamentos de novembro** (já feitos fora do aplicativo): depois da reconstrução, em Despesas → pagar fatura, com a data real e a conta de débito. Não há movimento bancário desses pagamentos hoje; o banco recusa pagar a mesma fatura duas vezes.
7. **Recorrência "SUPABASE SINGAPORE":** corrigir o contrato (seção 9).
8. **Função para desfazer um crédito importado** (do FIN-CARTAO-NUBANK-CREDITOS-01): segue pendente.
