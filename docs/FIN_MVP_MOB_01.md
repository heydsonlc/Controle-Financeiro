# FIN-MVP-MOB-01 — Integridade financeira da Mobilidade e combustível Flex

**Situação (06/11/2026): implementado e testado localmente.** Sem push, sem deploy e sem migration em produção. A produção só foi lida, em sessão só de leitura.

Base: diagnóstico FIN-MOBILIDADE-DIAGNOSTICO-01, sobre o commit de produção `f3ade96`.

## 1. Regras implementadas

### Veículo ativo: a recorrência é a fonte única do combustível

Vale quando há recorrência ativa de combustível do veículo (criada ao ativar a modalidade com meio de pagamento).

- Ao ativar, as previsões de combustível das competências da recorrência ficam `SUPRIMIDA`. Continuam na tela de Mobilidade ("Coberta pela recorrência") e na estimativa do comparativo.
- Confirmar com pagamento uma competência coberta é recusado (`COMBUSTIVEL_COBERTO`).
- A recorrência não gera competência já coberta. Fica dispensada em `recorrencia_competencia` quando há:
  - despesa de outra recorrência do mesmo veículo (reativação ou troca do meio de pagamento);
  - prevista confirmada com conta ou compra.
- Trocar de modalidade devolve as previsões futuras, com o valor atual, exceto onde já há despesa lançada.

### Identidade das ocorrências

- A identidade é `obrigacao` + `periodo_referencia`: mês no combustível; ano em IPVA, seguro e licenciamento.
- O índice único `ux_despesa_prevista_obrigacao_periodo` impede repetição.
- A ação do usuário bloqueia o período em qualquer data, inclusive fora da janela de 12 meses.
- Mudar o mês de uma obrigação ainda não confirmada move a prevista e preserva o id.
- Regerar não apaga e recria: atualiza a linha existente.

### Custo novo do veículo

Alterar o custo mensal de veículo com recorrência ativa atualiza:
- a recorrência;
- as contas de **meses futuros** ainda pendentes, sem pagamento nem movimento;
- as compras de meses futuros ainda em previsão sem cobrança, recalculando a fatura.

O mês corrente, o que foi pago e o que tem movimento não mudam.

### Vínculos

`despesa_prevista.conta_id` e `lancamento_id` guardam a despesa criada na confirmação. Excluir a conta ou compra só limpa o vínculo (`on delete set null`).

### Veículo simulado

- Fica fora do fluxo e dos indicadores do Dashboard, do alerta de atrasadas e das saídas sem lastro (`prevista_financeira`).
- Continua nas telas de Mobilidade.
- Confirmar com pagamento é recusado (`VEICULO_SIMULADO`). Confirmar sem pagamento só muda o status.
- A conversão para ATIVO passa a contar as previsões, sem criar conta nem compra.

### Flex e custo

- **Colunas opcionais em `veiculo`:** autonomia e preço por combustível, `combustivel_referencia`, `km_mensal_estimado` e `custo_combustivel_modo`.
- **Campos em uso:** `autonomia_km_l` e `preco_medio_combustivel` seguem o combustível de referência, então quem os lê não muda.
- **Precedência:**
  - `MANUAL` é o padrão e mantém o valor informado. Mudar autonomia, preço, km ou referência não altera o custo;
  - `CALCULADO` grava km ÷ autonomia × preço ao salvar, recusa parâmetros incompletos e não aceita valor digitado;
  - veículo de combustível único também pode usar `CALCULADO`.
- **Histórico:** a confirmação de combustível grava combustível, autonomia e preço na prevista. Mudanças posteriores não refazem o km consolidado.
- **Km fora de ordem:** confirmar fora de ordem agora conta o km.

## 2. Antes e depois

Medido em banco descartável, com a migration revertida (antes) e aplicada (depois).

| Cenário | Antes | Depois |
|---|---|---|
| Veículo ativo, combustível de R$ 200: saídas do mês no Dashboard | +R$ 400 | +R$ 200 |
| Confirmar a previsão com a recorrência ativa | Segunda conta no mês | Recusado |
| Reativar o veículo com outro meio de pagamento | 4 contas para 2 meses | 2 contas |
| Mudar o mês do IPVA depois de confirmar | Segundo IPVA no ano | Um por ano |
| Editar o custo de R$ 200 para R$ 900 | Recorrência em R$ 200 | Recorrência e futuras elegíveis em R$ 900 |
| Veículo simulado: saídas do mês no Dashboard | +R$ 600 | Sem reflexo |
| Regerar projeções | Ids trocados | Ids preservados |

A reativação não constava do diagnóstico: apareceu na implementação e foi corrigida.

## 3. Migration

`20261215090000_financeiro_mobilidade_integridade.sql`, gerada por `scripts/gerar_migration_mobilidade_integridade.py`, com reversão em `supabase/reversao/`.

- **Estrutura:** 7 colunas em `veiculo`, 4 em `despesa_prevista`, 2 restrições e 1 índice único.
- **Dados:** preenche só a identidade das previstas existentes. Recusa aplicar se houver repetição.
- **Funções novas (10, internas):** `mob_periodo`, `prevista_financeira`, `mob_item_combustivel`, `mob_competencia_coberta`, `mob_suprimir_combustivel`, `mob_restaurar_combustivel`, `mob_dispensar_cobertas`, `mob_sincronizar_combustivel`, `mob_planejar_prevista`, `mob_dados_flex`.
- **Funções substituídas (12):** `veiculo_flask`, `uso_do_veiculo`, `mob_inserir_prevista`, `mob_dados_veiculo`, `criar_veiculo`, `editar_veiculo`, `mob_gerar_projecoes`, `ativar_mobilidade`, `mob_registrar_combustivel`, `confirmar_despesa_prevista`, `dashboard_resumo_tela`, `saidas_lastro`.
- **Reversão:** recusada com veículo Flex, custo calculado ou vínculo gravado.

**Frontend:** `web/src/paginas/mobilidade.html` e `frontend/static/js/veiculos.js`.

## 4. Ensaio na cópia fiel da produção

Cópia descartável, conferida como idêntica à produção.

| Verificação | Resultado |
|---|---|
| Esquema | 55 migrations; as 12 funções iguais ao texto de origem; nenhuma coluna nova já existente |
| Migration | 84 tabelas iguais, fora as colunas novas |
| Identidade | 15 previstas: 12 combustível, 1 IPVA, 1 seguro, 1 licenciamento |
| Veículo atual | Etanol, 7,20 km/L, R$ 800,00, modo MANUAL: sem mudança |
| Regerar | Mesmos ids e valores; nenhuma tabela muda |
| Reversão | 84 tabelas iguais ao início; nenhuma coluna restante |
| Reaplicação | Nenhuma diferença |

**Efeito esperado no Dashboard:** o veículo atual é SIMULADO, então os números caem quando a publicação acontecer.

| Mês | Saídas antes | Saídas depois | Despesas previstas antes | Depois |
|---|---|---|---|---|
| 11/2026 | R$ 11.524,23 | R$ 10.724,23 | R$ 800,00 | R$ 0,00 |
| 12/2026 | R$ 16.312,14 | R$ 11.513,14 | R$ 4.799,00 | R$ 0,00 |
| 01/2027 | R$ 15.862,15 | R$ 11.262,15 | R$ 4.600,00 | R$ 0,00 |

O alerta "1 despesa(s) prevista(s) atrasada(s)" também some. Contas, compras, saldos e movimentos não mudam.

## 5. Registros históricos

### Clube dos Oficiais, 06/2026

Contas 2360 e 2361, R$ 160,00 cada, ambas pagas e com movimento. Nada foi alterado. **Pendência:** regularização própria, com estorno de uma delas por autorização.

### Apple One, 05/2026 — proposta de regularização (não executada)

Validação só de leitura:

| Verificação | Resultado |
|---|---|
| Situação da conta 1938 | Pendente, R$ 59,90, sem data de pagamento |
| Pagamento ou movimento | Nenhum |
| Vínculos | 8 chaves estrangeiras e demais colunas `conta_id` conferidas: zero referências |
| Mesma obrigação | Sim: compra 562, mesmo item 459, mesmo valor e competência, criada 6 minutos depois, na fatura Visa 05/2026, já paga |
| Recorrências | Sem registro para 05/2026; a compra e as demais competências não dependem da conta |
| Fluxo normal | **Recusa:** `despesa_para_edicao` responde `pode_excluir = false` ("Fatura ou compra de cartao: fica no modulo de cartoes"), porque o item hoje é de cartão |

- **Proposta:** como a tela não consegue excluir, fazer uma operação própria, de uso único e autorizada, que:
  - identifica a conta pelo id e confere de novo item, valor, situação, ausência de pagamento, movimento e referências;
  - exclui só essa linha, numa transação, e registra a auditoria;
  - recusa se qualquer conferência falhar.
- **Efeito:** 05/2026 perde R$ 59,90 de pendência, a única conta pendente até esse mês. A compra 562 e a fatura paga não mudam.
- **Sem migration de dados nem SQL manual:** o procedimento precisa de contrato próprio, com prévia e ensaio em cópia.

## 6. Testes

Executados em banco descartável, com dados fictícios.

| Bateria | Resultado |
|---|---|
| `test_supabase_mobilidade_integridade.py` | 26/26 |
| Unitários do frontend | 73/73 |
| E2E completo | 124/124, incluindo o Flex pela tela |
| Seleção de impacto (pytest) | 508/508 (38 arquivos: Mobilidade, Dashboard, recorrências, despesas, cartões, lastro); a suíte Python inteira não foi rodada |

**Testes ajustados:** `test_supabase_mobilidade_escrita.py` compara o Flask pela identidade lógica, porque os ids agora são preservados. A reversão da 1127 passa a exigir antes a da 1215.

## 7. Riscos e ressalvas

- **Km do veículo ativo:** com as previsões suprimidas, confirmar abastecimento deixa de existir nesse caso. A estimativa de km usa a projeção (custo ÷ preço × autonomia), como já ocorria sem histórico.
- **Trocar para outra modalidade:** contas futuras pendentes da recorrência antiga continuam lançadas, como antes.
- **Mês corrente:** o custo novo não altera a conta ou compra do mês atual; só as seguintes.
- **Prevista confirmada antes desta versão:** não tem vínculo. A produção não tem nenhuma, então não há efeito.
- **Flask:** o Dashboard legado ainda conta veículo simulado, e o formulário dele não tem Flex. Ambos os perfis usam o novo aplicativo.
- **Transporte por app:** a restauração das previsões vale só para veículo, como pedido.

## 8. Publicação (não autorizada nesta etapa)

Quando autorizada: push, aplicar só `20261215090000`, conferir o hash e fazer build e deploy do frontend. A tela nova depende da migration, então a migration vem antes do deploy.
