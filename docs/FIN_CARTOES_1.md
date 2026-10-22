# FIN-CARTOES-1 — Cartões, compras à vista e parceladas e faturas (sem pagamento)

**Data:** 2026-10-21.

**Situação:** implementado e validado **só localmente**: cluster PostgreSQL descartável, Flask real em bancos fictícios e E2E local.

**Autorização:** SCRIPT-CONTRATO V5 — FIN-CARTOES-1.

**Não foi feito:**
- aplicar migration remota;
- publicar no Cloudflare;
- executar Alembic no `gastos.db`;
- tocar dados reais;
- pagar fatura, fazer estorno, conciliação, alterar movimento, saldo ou recebimento.

## 1. Diagnóstico do Flask (código real)

| Tema | O que o Flask faz | Onde |
|---|---|---|
| Cartão | `item_despesa` (`tipo='Agregador'`, `recorrente=True`, categoria "Cartoes de Credito" se existir) + `config_agregador` (dias, limite, número, validade, CVV, observações). Excluir = `ativo=False` | `routes/cartoes.py` `POST/PUT/DELETE /api/cartoes` |
| Fechamento | `dia_fechamento` é **gravado, mas não usado** em nenhuma regra. O mês da fatura é **escolhido pelo usuário** (campo "Mês da fatura", padrão = mês atual ou o do filtro) | `lancamentos.js`, `lancamentos.html` |
| Vencimento | `comp.replace(day=dia_vencimento)`: **quebra** com dia 31 em mês de 30 dias | `CartaoService.get_or_create_fatura` |
| Compra | `adicionar_lancamento`: `compra_id` uuid4; centavos = `total // n`, +1 centavo nas primeiras `resto` parcelas; parcela n na fatura `mês + (n-1)` e data `data + (n-1)` meses; perfil = perfil da fatura (ou o ativo); categoria do cartão pelo mapa categoria-de-despesa → categoria do cartão, se vinculada ao cartão; recalcula as faturas afetadas | `cartao_service.py` |
| Fatura paga | Desvia a parcela para o mês seguinte se `status_fatura == 'PAGA'`, mas **nenhum código grava `'PAGA'`** (`pagar_fatura` grava só `status_pagamento='Pago'`). Na prática a compra **entra na fatura paga** | `adicionar_lancamento`, `pagar_fatura` |
| Fatura fechada | `FECHADA` (consolidar) ainda aceita compras | docstring/consolidar |
| Unicidade | Índice único parcial `ux_conta_fatura_cartao_competencia` (FIN-FATURA-UNICA-1) | `models.py` |
| Planejado / executado | `calcular_planejado` = limites ativos **do perfil** (senão orçamento legado vigente); executado = soma das compras; `recalcular_fatura` grava planejado, executado, estouro e `valor = planejado` se não paga | `cartao_service.py` |
| Previsto na tela | executado + Σ max(0, limite − gasto) dos limites ativos do cartão; fatura paga = executado | `despesas.py` `_calcular_totais_fatura_cartao_previsto`; `contas_do_mes` |
| Editar/excluir compra | `PUT`/`DELETE /api/cartoes/lancamentos/<id>` **sem conferir fatura paga e sem recalcular** a fatura | `routes/cartoes.py` |
| Parcelas futuras | `atualizar_parcelas_futuras` / `cancelar_parcelas_futuras`: só parcelas "futuras" (não pagas, não FECHADA, mês > base) | `cartao_service.py` |
| Recorrência no cartão | `lancamento_agregado.is_recorrente` (FIN-RECORRENCIA-1, `compra_id` uuid5) | — |
| Pagamento/estorno | `marcar_como_pago` → `pagar_fatura` (movimento origem FATURA); `estornar_pagamento` (ESTORNO_FATURA). **Sem trava** (FIN-PAGAMENTO-TRAVA-1) | `despesas.py` |
| GETs que gravam | `avaliar_alertas` e o resumo chamam `get_or_create_fatura` (criam fatura em consulta). No novo app, **nenhuma consulta grava** | `routes/cartoes.py` |
| Perfis | `condicao_perfil`: perfil exato; no "Pessoal", também `perfil_financeiro_id IS NULL` | `perfil_financeiro_service.py` |
| Dados sensíveis | `to_dict` devolve o número completo; CVV só com senha mestra | `models.py` |

## 2. O que foi implementado

**Migration `supabase/migrations/20261028090000_financeiro_cartoes.sql`** (não aplicada no remoto). Reutiliza as tabelas do Flask; a única tabela nova é `financeiro.operacao_cartao`, que guarda as chaves de idempotência (RLS forçada, sem privilégios).

**Funções para o navegador** (`authenticated`; nenhuma para `anon`):

| Função | Tipo | Regra |
|---|---|---|
| `cartoes_do_perfil` | leitura | Dias, limite, **só os 4 últimos dígitos**, versão. Nunca número completo, validade ou CVV |
| `faturas_do_mes` | leitura | Por cartão ativo: situação (ABERTA/FECHADA/PAGA/SEM_FATURA), executado, previsto (mesma fórmula de `contas_do_mes`), nº de compras |
| `compras_da_fatura` | leitura | Compras da competência com parcela, categoria, bloqueio e `pode_editar` |
| `compra_para_edicao` | leitura | Parcelas, bloqueio de cada uma, parcelas abertas, versão |
| `previa_compra` | leitura | Mesmas regras do cadastro, sem gravar: parcelas, valores, fatura de destino e desvio |
| `criar_compra` | escrita | Compra à vista ou parcelada (1–60), idempotente pela chave |
| `editar_compra` | escrita | Descrição, categoria, observações das parcelas abertas; à vista também valor, data e mês da fatura |
| `excluir_compra` | escrita | Remove as parcelas em fatura aberta; preserva as de fatura paga/fechada |
| `criar_cartao` | escrita | Como o Flask, **recusando número, validade e CVV** |
| `editar_cartao` | escrita | Nome, dias, limite, observações; com versão |
| `inativar_cartao` | escrita | `ativo=false`; nunca exclusão física |

**Funções internas** (sem EXECUTE para o navegador): `fatura_esta_paga`, `fatura_do_mes`, `planejado_fatura`, `garantir_fatura`, `recalcular_fatura`, `resolver_categoria_cartao`, `cartao_do_perfil`, `plano_compra`, `parcelas_da_compra`, `bloqueio_da_parcela`, `versao_compra`, `travar_compra`, `ler_dados_cartao`.

**Tela `web/src/cartoes.html` + `js/cartoes.js`** (aba "Cartões" ao lado de Contas e Receitas):
- faturas do mês por cartão;
- compras de cada fatura, com editar/excluir só quando o banco permite;
- "Nova compra" com prévia das parcelas calculada no banco;
- cadastro de cartões (final do número; editar e inativar);
- **nenhum botão de pagamento** e um aviso de que o pagamento continua no sistema atual.

## 3. Regras de fechamento, competência e vencimento

- **Mês da fatura:** é o escolhido pelo usuário, como no Flask, e a prévia mostra o destino de cada parcela. O dia de fechamento **não** é aplicado (**regra que exige decisão**, §9).
- **Vencimento:** dia contratual. 31 vira 30/28/29 nos meses curtos, como no FIN-RECORRENCIA-1. O Flask quebraria nesses casos.
- **Edição do dia de vencimento** vale para as próximas faturas; as já criadas não mudam.
- **Fatura paga** (`status_pagamento='Pago'` ou `status_fatura='PAGA'`) **nunca recebe compra**. A parcela vai para a próxima fatura não paga e as seguintes andam junto, uma por fatura.
- **Fatura fechada** aceita compra nova (como no Flask), mas bloqueia edição e exclusão.

## 4. Cálculos de fatura

- **Gravados como no Flask** (`recalcular_fatura`, só se não paga): `valor_planejado` = limites ativos do perfil (ou orçamento legado), `valor_executado` = soma das compras, `estouro_orcamento`, `valor = planejado`.
- **Exibido** (`faturas_do_mes`): executado + complemento dos limites ativos do cartão. É a **mesma fórmula** de `contas_do_mes`, comparada em teste. A fatura paga mostra o executado.
- **Sem dupla contagem:**
  - cada parcela pertence a uma fatura;
  - a soma das parcelas é exata;
  - a soma por fatura é igual ao total das compras listadas;
  - existe uma fatura por cartão e competência.

## 5. Testes locais

**`tests/test_supabase_cartoes.py`: 70 testes**, todos passando.

| # | Item | Resultado |
|---|---|---|
| 1 | Cadastro de cartão | Igual ao Flask; inválidos recusados (número, CVV, dias, limite, nome) |
| 2 | Edição e inativação | Com versão; versão antiga recusada; faturas existentes preservadas; inativo sem compras novas |
| 3 | À vista | Fatura criada e recalculada (planejado 500, executado 120) |
| 4 | Parcelada | 33,34 / 33,33 / 33,33 em meses consecutivos, mesmo `compra_id` |
| 5 | Arredondamento | 0,05/3; 1000/7; 99,99/12: soma exata e diferença ≤ 1 centavo; mínimo de 1 centavo por parcela |
| 6 | Virada de mês/ano | 31/10 → 30/11 → 31/12 → 31/01; faturas 11/2029 a 02/2030 |
| 7 | Fechamento | Vale o mês escolhido (como no Flask), visível na prévia |
| 8 | Vencimento | 31/01, 29/02/2028, 31/03, 30/04 |
| 9 | Fatura paga | Compra desviada (prévia avisa); fatura paga intacta; parcela em fatura paga não é editada nem excluída |
| 10 | Fatura pendente | Situação ABERTA; campos recalculados; estouro |
| 11 | Previsto por categoria | 750,00 = valor de `contas_do_mes` |
| 12 | Unicidade | Fatura criada por outra transação (como o Flask) é reaproveitada; compras simultâneas → 1 fatura |
| 13 | Recorrência | Compra recorrente bloqueada aqui; compra + geração do mês convivem com 1 fatura |
| 14 | Exclusão segura | Parcelas abertas removidas e faturas recalculadas; pagas preservadas com o mesmo `compra_id` |
| 15 | Edição concorrente | Mesma versão ×2: só uma vale |
| 16 | Idempotência | Mesma chave ×3 em paralelo: 1 compra; chave de outro usuário recusada |
| 17 | Perfis | LEITOR lê e não escreve; outro usuário, perfil inativo e cartão de outro perfil → 42501 |
| 18 | Anônimo | As 11 funções públicas são recusadas; funções internas e tabelas, recusadas também para `authenticated` |
| 19 | Movimentos e saldos | `conta_bancaria`, `movimento_financeiro`, contas comuns, categorias e limites idênticos |
| 20 | Dupla contagem | Soma por fatura = compras listadas; 3 faturas para 3 meses |
| 21 | Regressão | Suíte completa (§7) |

**Equivalência com o Flask real** (mesmos dados fictícios):
- três compras (3×, 1× de 0,05, 7× de 1000,00 com virada de ano) geraram **11 parcelas idênticas** (todos os campos exceto id, `compra_id` e `criado_em`);
- as **faturas são idênticas**;
- o **cadastro de cartão** é idêntico (`item_despesa` + `config_agregador`).

**Concorrência:**
- duas e três compras simultâneas no mesmo cartão;
- compra repetida (mesma chave);
- compra × geração de recorrências: serializadas pela mesma trava (`20261023`, perfil). Se a compra vence e cria as faturas, a geração recusa com "a prévia mudou" e gera na nova confirmação, sem duplicar;
- criação simultânea da mesma fatura;
- edições simultâneas;
- compra numa fatura sendo paga: espera a linha e recusa ("foi paga durante o cadastro");
- edição durante um pagamento: espera e fica bloqueada.

**E2E local (390 px): 47/47** (4 novos em `web/tests/e2e/cartoes.spec.mjs`):
- faturas iguais às de Contas do mês e nenhum botão de pagamento;
- compras de fatura paga sem ações;
- final do número sem o número completo;
- ciclo completo (cartão → prévia → compra parcelada → edição → exclusão → inativação), escrito pelo usuário B no Perfil B (ajuste do FIN-CARTOES-REAL-1);
- LEITOR sem nenhuma ação.

**Unitários do `web/`:** allowlist de RPCs atualizada; 7/7.

## 6. Proteção do histórico

- Nenhuma função escreve em `movimento_financeiro`, `conta_bancaria`, recebimentos ou contas que não sejam fatura.
- Parcelas em fatura **paga** ou **fechada** e compras **recorrentes** não são editadas nem excluídas. A mensagem informa que a correção exige estorno, sem executá-lo.
- Fatura paga não tem valores recalculados nem recebe compra.
- Cartão só é inativado; compras e faturas ficam.
- Nenhuma consulta grava (ao contrário de alertas/resumo do Flask).

## 7. Suíte completa

**1417 passaram**, 19 pulados (número confirmado pelo resumo real do pytest no FIN-CARTOES-REAL-1); só as 5 falhas que já existiam:
- `test_categorias_sistemicas_mobilidade::test_projecoes_veiculo_usam_categorias_sistemicas_granulares`
- `test_ocr_tools::test_status_sem_ferramentas_retorna_estrutura_valida`
- `test_ocr_tools::test_poppler_ausente_retorna_aviso`
- `test_receitas_ux::test_cards_resumo_calculam_previsto_realizado_diferenca_confiabilidade`
- `test_veiculos_mobilidade_2b::test_suprimir_despesas_previstas_futuras`

## 8. Diferenças intencionais em relação ao Flask

1. **Compra em fatura paga** é desviada. No Flask o desvio nunca dispara; as parcelas seguintes andam junto, sem duas parcelas na mesma fatura.
2. **Editar/excluir compra** confere fatura paga, fechada ou recorrência, trava, usa versão e recalcula a fatura. O Flask altera sem conferir nem recalcular (comprovado em teste com o Flask real).
3. **Vencimento pelo dia contratual.** O Flask quebra com dia 31 em mês de 30 dias.
4. **Número, validade e CVV não são tratados nem expostos.** Só o final do número.
5. **Consultas não criam faturas.**
6. **Exclusão de compra parcelada** remove só as parcelas abertas e informa as preservadas.
7. **Validações no banco:**
   - valor positivo com 2 casas;
   - 1–60 parcelas com ao menos R$ 0,01 cada;
   - mês da fatura a até 12 meses da compra;
   - categoria ativa;
   - dias de 1 a 31.

**O Flask não foi alterado.** Os defeitos 1 e 2 continuam na tela do Flask (corrigi-los lá é decisão à parte).

## 9. Decisão pendente

**Fechamento:** derivar o mês da fatura do dia de fechamento (compra depois do fechamento → próxima fatura) mudaria a regra em uso no Flask. Hoje o mês é escolhido pelo usuário e exibido na prévia. Se desejado, a sugestão automática pode ser só um padrão do formulário, sem mudar a regra do banco.

## 10. Arquivos

- `supabase/migrations/20261028090000_financeiro_cartoes.sql` (novo)
- `web/src/cartoes.html`, `web/src/js/cartoes.js` (novos)
- `web/src/contas.html`, `web/src/receitas.html`, `web/src/js/contas.js`, `web/src/js/receitas.js`: aba Cartões
- `web/src/js/sessao.js`: página permitida
- `web/src/css/app.css`: classes da tela
- `web/tests/unit/build.test.mjs`: RPCs liberadas
- `web/tests/e2e/cartoes.spec.mjs` (novo), `web/tests/e2e/run_e2e.py`
- `tests/test_supabase_cartoes.py` (novo), `tests/supabase_local.py` (`semear_cartoes_e2e`)
- `docs/FIN_CARTOES_1.md`, `docs/ROADMAP.md`

## 11. Próximos passos (não autorizados)

- **FIN-CARTOES-REAL-1:** concluído em 2026-10-22 (`docs/FIN_CARTOES_REAL_1.md`).
- **FIN-PAGAMENTO-TRAVA-1** continua obrigatório antes de pagamentos, recebimentos e estornos.
