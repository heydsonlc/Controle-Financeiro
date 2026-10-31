# FIN-CARTAO-AGRUPAMENTO-CATEGORIAS-01 — Agrupamento da fatura por Categoria do Cartão em Despesas

**Situação (31/10/2026): `FIN_CARTAO_AGRUPAMENTO_CATEGORIAS_01_PRONTO_PARA_PUBLICACAO`.** Implementado, testado e ensaiado numa cópia fiel da produção.
- Commit, push, migration e deploy aguardam autorização.

## 1. Defeito (diagnóstico, produção só lida)

Fatura 11/2026 do Master Card Black: 89 compras importadas, R$ 7.194,80, todas em "Outros Lançamentos".

| Etapa | Situação |
|---|---|
| Importação (`importar_fatura_cartao`) | Correta. Grava `categoria_id` nas 89 e `categoria_cartao_id` nas 51 cujas categorias têm vínculo e limite no cartão. |
| Leitura das compras (`compras_da_fatura`, 20261028) | Não devolvia `categoria_cartao_id`; o adaptador de Despesas a mandava nula. |
| Resumo por categoria (`/api/cartoes/{id}/fatura-categorias`) | O adaptador de Despesas respondia `{ categorias: [] }` fixo. A função `fatura_por_categoria` (20261104) já existia e é a da tela de Cartões. |
| Agrupamento (`organizarLancamentosEmBlocos`, `despesas.js` do Flask) | Sem resumo nem Categoria do Cartão, toda compra não parcelada e não fixa ia para Outros. |

Fora do defeito:
- **Parceladas:** nenhuma compra da fatura traz parcela no arquivo.
- **Fixas:** o cartão Black não tem recorrência.
- **"Allianz Segu*02 de":** o arquivo não traz o total de parcelas. Fica como está (1/1, Outros); não se infere o total.

**Defeito escondido no Flask:** `despesas.js` lê `categorias` na raiz da resposta, mas o Flask responde `{ success, data: { categorias } }`, então lá o bloco também ficaria vazio. O novo aplicativo responde no formato que a tela lê; o arquivo do Flask não muda.

## 2. Correção

- **Migration `20261207090000`:** `compras_da_fatura` devolve `categoria_cartao_id` (coluna nova, no fim; colunas anteriores iguais).
  - A mudança do tipo de retorno exige recriar a função e repetir as permissões.
  - Só leitura; nenhum dado alterado.
- **`despesas-adaptador.js`:**
  - `/api/cartoes/{id}/lancamentos` repassa o `categoria_cartao_id` gravado;
  - `/api/cartoes/{id}/fatura-categorias` chama `fatura_por_categoria` e devolve `{ categorias }`.
- **Inalterado:** importação, compras, vínculos, limites, parcelamento, `despesas.js` e a regra do "Total previsto" (limite de cada Categoria do Cartão no lugar do gasto, regra do Flask).
- **Reversão:** `supabase/reversao/20261207090000_compras_fatura_categoria_cartao_anterior.sql` (texto de 20261028).

## 3. Regras do agrupamento (comportamento existente, agora alimentado)

Blocos exclusivos, nesta ordem:
1. **Compras Parceladas:** `total_parcelas > 1`, mesmo classificada.
2. **Despesas Fixas:** compra de recorrência no cartão, mesmo classificada.
3. **Despesas por Categoria:** Categoria do Cartão com limite maior que zero no cartão.
4. **Outros:** o resto (sem vínculo, vínculo sem limite no cartão, sem classificação).

Executado = soma das compras. Previsto = parceladas + fixas + limites + outros.

## 4. Testes

- `tests/test_supabase_compras_fatura_categoria_cartao.py` (5):
  - categoria vinculada, sem vínculo e sem limite;
  - colunas anteriores iguais;
  - leitura sem escrita;
  - segurança e isolamento;
  - reversão e reaplicação.
- `web/tests/unit/fatura-blocos.test.mjs` (7), com o `despesas.js` real:
  - vinculada e subtotal;
  - sem vínculo, sem limite e sem classificação;
  - parcelada classificada;
  - fixa classificada;
  - somatório sem perda ou duplicidade;
  - tela;
  - o defeito anterior.
- `web/tests/e2e/fatura_agrupamento.spec.mjs` (1): a tela de Despesas no banco descartável.
  - Parcelada R$ 100,00; Mercado B previsto R$ 300,00 e executado R$ 150,00; Outros R$ 45,00.
  - Totais R$ 445,00 previsto e R$ 295,00 executado.

## 5. Ensaio (cópia fiel e descartável da produção)

| Conferência | Resultado |
|---|---|
| Cópia | Idêntica à produção |
| Migration (md5 `9d17b399…338f`) | Só a função `compras_da_fatura` e o registro da versão |
| Black 11/2026 | Categorias: **51 compras, R$ 4.312,25** (6 categorias); Outros: **38, R$ 2.882,55**; executado **R$ 7.194,80**; parceladas e fixas 0; 89 compras nos blocos, sem perda nem duplicidade |
| Por categoria (previsto / executado) | Supermercado 1.200,00 / 774,63; Farmácia 1.000,00 / 402,40; Hortifruti 300,00 / 145,55; Panificadora 200,00 / 379,22; Mobilidade 1.750,00 / 1.162,30; Assinaturas 200,00 / 1.448,15 |
| "Allianz Segu*02 de" | 1/1, sem Categoria do Cartão: Outros |
| Total previsto (regra do Flask, fora deste pacote) | R$ 7.194,80 → R$ 7.532,55 |
| Visa 11/2026 | Fixas 4 (R$ 329,60); Assinaturas 4 (R$ 227,70); Outros 9 (R$ 2.038,15); 17 compras, R$ 2.595,45 |
| Cópia depois das leituras | Igual |

## 6. Pendências

- **Regra do "Total previsto":** avaliar à parte se o previsto pelo limite faz sentido.
- **"Allianz Segu*02 de":** corrigir só esse lançamento se o total de parcelas for confirmado.
- **38 compras sem Categoria do Cartão:** Restaurantes / Delivery, Outros, Internet e Telefonia, Seguro Veicular e Educação não têm vínculo. Se forem vinculadas e ganharem limite, a Categoria do Cartão pode ser reconstruída pela `categoria_id` por rotina própria, com autorização.
