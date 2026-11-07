# FIN-CARTAO-CREDITOS-02 — Integridade e deduplicação dos créditos da fatura

**Situação (07/11/2026): publicado (`f94b207`, migration `20261216090000`, 57 no total).** Sem deploy: a tela não mudou. Auditoria somente leitura aprovada (seção 6). A reconstrução das faturas de 11/2026 sai do bloqueio técnico e passa a etapa própria de planejamento e autorização.

## 1. Diagnóstico

As duas pendências vieram do FIN-CARTAO-CREDITOS-01 (seção 6), com `xfail` estrito.

| Defeito | Causa | Efeito |
|---|---|---|
| Mesmo crédito por outro tipo de arquivo | A chave do crédito inclui o texto normalizado. O CSV do Nubank traz `Estorno de "Apple.Com/Bill" (Apple)`; outro arquivo pode trazer o mesmo crédito sem a categoria entre parênteses. A trava `OUTRA_FONTE` só barra compras novas. | O crédito parece novo e abate de novo: 100,00 − 20,00 − 20,00 = 60,00 |
| Estorno com "pagamento" no texto | "Pagamento" era testado antes de "estorno", no texto inteiro, inclusive no nome da loja entre aspas. | `Estorno de "Pagamento Facil Loja"` era retirado como pagamento da fatura e não abatia |

### Por que exige migration

A duplicidade e a natureza do crédito são decididas no banco, em `analisar_importacao_cartao`, e a confirmação (`importar_fatura_cartao`) refaz a análise sob a trava do perfil. A tela só repassa o tipo da linha (débito ou crédito) e não classifica nada. Corrigir só na tela deixaria a confirmação gravar em dobro. Toda mudança de função do banco é uma migration.

**Não é preciso coluna nova nem preenchimento de dados.** A identidade usa campos que `credito_fatura` já guarda. A migration `20261216090000` só substitui as duas funções e vem depois da `20261215090000` (MOB-01, publicada).

### Dados reais conferidos (somente leitura)

- **Produção:** `credito_fatura` vazia. A correção não muda nenhum registro, e a reversão só restaura as funções.
- **Visa, PDF de 11/2026:** três créditos legítimos idênticos, `AJUSTE CREDITO PARC. LOJISTAA`, R$ 0,01, 05/10. É o caso em que descrição e valor não bastam.
- **Nubank:** o CSV não informa o final do cartão. No PDF, a linha de crédito também vem sem cartão. O IOF devolvido tem o mesmo texto nos dois formatos.

## 2. Identidade do crédito

O texto muda entre o PDF e a planilha; cartão, fatura, data e valor não.

| Passo | Regra |
|---|---|
| 1 | Crédito gravado com o **mesmo texto**, mesmo cartão, fatura, data e valor: é esta linha |
| 2 | Senão, outro crédito gravado de **mesma data e valor**, ainda não reconhecido e que nenhuma outra linha do arquivo repete pelo texto |
| 3 | Senão, crédito novo |

- **Cada crédito gravado responde por uma linha só.** Créditos legítimos iguais continuam contados um a um: três ajustes gravados reconhecem três linhas, e um quarto, de fato novo, abate.
- **Reserva do texto igual.** Se o arquivo traz um crédito novo de mesma data e valor antes do que já existe, o gravado fica com a linha de texto igual e o novo entra com o seu próprio texto.
- **Cartão vinculado:** mantida a regra do FIN-CARTOES-MULTIPLOS-01. Crédito sem cartão identificado casa com qualquer cartão do contrato; cartões diferentes não se misturam.
- **Repetido no próprio arquivo:** continua pedindo a confirmação do usuário (`manter_duplicada`), como antes.
- **Mensagem:** a prévia mostra qual crédito já foi registrado e de que tipo de arquivo, por exemplo: registrado como "Estorno de "Loja" (Som)", de planilha.

## 3. Natureza do crédito

| Texto | Antes | Agora |
|---|---|---|
| `Estorno de "Pagamento Facil Loja"` | Pagamento (fora) | Estorno, abate |
| `Estorno de Pagamento Facil Loja` | Pagamento (fora) | Estorno, abate |
| `Pagamento recebido`, `Obrigado pelo pagamento`, `Pgto fatura` | Pagamento (fora) | Pagamento (fora) |
| `Pagamento estornado` | Pagamento (fora) | Pagamento (fora): na dúvida, não abate |

O nome da loja entre aspas não decide a natureza. Texto que começa por estorno, devolução ou reembolso é estorno mesmo com "pagamento" no restante.

## 4. Idempotência

- **Mesma operação repetida:** devolve o resultado gravado (`repetida`), como antes.
- **Mesmo arquivo, ou o outro formato, de novo:** "Nenhuma linha para importar", sem gravar.
- **Confirmações simultâneas:** a trava do perfil e a análise refeita sob ela continuam valendo.
- **Compra original:** na confirmação, a consulta da compra de cada crédito não toma por duplicidade o crédito gravado na mesma importação, e dois créditos de mesma data e valor ficam cada um com a sua compra. A marca interna que permite isso é retirada das linhas que vêm da tela, então não serve para burlar a duplicidade.

## 5. Arquivos

- `scripts/gerar_migration_cartao_creditos_integridade.py`: gera a migration e a reversão a partir do texto vigente (`20261213090000`), com trocas conferidas.
- `supabase/migrations/20261216090000_financeiro_cartao_creditos_integridade.sql`
- `supabase/reversao/20261216090000_cartao_creditos_integridade_anterior.sql`
- `tests/test_supabase_cartao_creditos_importacao.py`: os dois `xfail` viraram testes, mais 8 cenários.
- `tests/test_gerador_migration_cartao_creditos_integridade.py`

A tela não muda.

## 6. Publicação e auditoria (07/11/2026)

- **Antes:** 56 migrations, a 1216 única pendente; as duas funções vigentes iguais ao texto anterior (o da reversão); 89 testes direcionados aprovados, inclusive o arquivo de recorrências do cartão.
- **Migration:** aplicada e conferida; 2 funções alteradas, nenhuma criada ou removida, nenhuma tabela nova, nenhum dado existente alterado, nenhum bloqueio de segurança.
- **Funções publicadas:** iguais ao texto da migration; mesma assinatura, `security definer`, `search_path` fixo, executáveis só por `authenticated`.
- **Dados financeiros:** contas, compras, movimentos, saldos, financiamento, faturas, recorrências, cartões, duplicidades, despesas dos meses e Dashboard iguais antes e depois. `credito_fatura` vazia.
- **Atividade do app durante a publicação:** duas linhas gravadas pela tela, fora da migration (identificador de transação anterior e posterior ao dela): a recorrência 377 (Energia Elétrica), com valor e situação inalterados, e a conta bancária 96, com o saldo inalterado.

