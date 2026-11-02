# FIN-CARTOES-MULTIPLOS-01 — Contratos com vários cartões, fatura consolidada e reconstrução das importações

**Situação (02/11/2026): `FIN_CARTOES_MULTIPLOS_01_PRONTO_PARA_HOMOLOGACAO`.** Implementado, testado e ensaiado numa cópia fiel da produção.
- Migration remota `20261213090000`, push e deploy aguardam autorização.
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
- **`importar_fatura_cartao`:** grava o cartão de origem na compra, na previsão realizada e no crédito.
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
| **PDF do Nubank** | leitor novo (`parseTextoNubank`): cada compra traz "•••• 6830" (titular) ou "•••• 6030" (adicional). Linhas sem cartão no documento (IOF, crédito, serviço como o Plano NuCel, pagamento) ficam sem cartão identificado: não é presumido nem a seção do titular. Confere com o PDF real de 09/2026: as somas por cartão batem com os subtotais do documento. |
| **CSV do Nubank** | `date,title,amount`: não traz o cartão. As linhas ficam sem cartão identificado. A prévia oferece a escolha por linha e para as selecionadas. |
| **CSV da Caixa ou manual** | sem cartão; escolha na prévia |

**Regras:**
- Final não cadastrado: a linha entra sem cartão, com aviso ("cadastre o cartão ou escolha"). Não bloqueia as demais.
- Escolha de cartão de outro contrato: Revisar.
- Duplicidade: compras idênticas de cartões diferentes não se confundem, nem no arquivo nem no banco. A mesma compra reimportada continua sendo a mesma. Compra antiga sem cartão casa com qualquer uma.

**Tela de importação:**
- seletor compacto "Cartão de origem" sob a descrição (`•••• 7136 · virtual (arquivo)`, cancelado marcado);
- "Cartão de origem das selecionadas" acima da tabela;
- só aparecem com cartões cadastrados no contrato. Sem eles, ou no Flask, a tela fica como antes.

**Tela de Cartões:**
- "Cartões do contrato" no detalhe do contrato: final, identificação, tipo, portador, situação, substituto e uso;
- "Adicionar cartão" e editar, em modal compacto.

## 5. Testes

- **`tests/test_supabase_cartoes_multiplos.py`** (16):
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

## 8. Pendências para publicação e reconstrução real

1. **Publicação:** 1213, push e deploy, com autorização.
2. **Cadastro dos cartões** na tela de Cartões:

   | Contrato | Cartão | Tipo | Situação |
   |---|---|---|---|
   | Visa | 0548 | físico | cancelado |
   | Visa | 7136 | virtual | ativo |
   | Black | 6830 | físico (titular) | ativo |
   | Black | 6030 | adicional | ativo |

   O novo físico da Caixa é cadastrado quando chegar e marcado como substituto do 0548.
3. **Black:** para o cartão de cada compra, importar o **PDF de novembro do Nubank** (não está no computador; só o de 09/2026). Com o CSV, as 101 linhas ficam sem cartão, ou precisam de escolha manual.
4. **Visa: compras contestadas do 0548.** O PDF de 05/11/2026 traz as parcelas do cartão cancelado. Pela documentação da Caixa (cancelamentos e estornos), decidir na prévia quais retirar antes de confirmar. O valor original de R$ 3.928,91 é referência, não autorização.
5. **Limpeza real de 11/2026, com autorização:** prévia pelo script, conferência e execução com o hash. Depois, a reimportação dos dois arquivos com as decisões do titular:
   - Categoria das linhas novas;
   - estorno da Apple;
   - ajustes repetidos;
   - segunda Netflix;
   - parcelas contestadas.
6. **Pagamentos de novembro** (já feitos fora do aplicativo): depois da reconstrução, em Despesas → pagar fatura, com a data real e a conta de débito. Não há movimento bancário desses pagamentos hoje; o banco recusa pagar a mesma fatura duas vezes.
7. **Recorrência "SUPABASE SINGAPORE"** (R$ 225), criada no Black: a cobrança real (R$ 229,28 + IOF) está no Visa, cartão 7136. Revisar o cartão da recorrência.
8. **Função para desfazer um crédito importado** (do FIN-CARTAO-NUBANK-CREDITOS-01): segue pendente.
