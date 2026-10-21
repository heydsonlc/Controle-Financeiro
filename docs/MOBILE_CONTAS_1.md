# MOBILE-CONTAS-1 — Contas do mês (somente leitura)

Data: 2026-10-21. Implementado e testado **localmente**.

**Não executado:** migration no Supabase remoto, publicação no Cloudflare, alteração de dados reais. Decisões aprovadas: D1 a D4 (ver `docs/MOBILE_CONTAS_1_CONTRATO.md`).

## 1. Tela e fluxo

Login → **Contas do mês** (`web/src/contas.html`), a nova tela inicial, no mês atual de Brasília.

| Elemento | Comportamento |
|---|---|
| Cabeçalho | Perfil financeiro autorizado (seletor), e-mail (oculto em telas estreitas), Sair |
| Mês | ◀ **Novembro de 2026** ▶, links `contas.html?mes=AAAA-MM` (áreas de toque de 44 px). Mês inválido volta ao mês atual |
| Totais | Uma linha com três colunas: **Total · Pago · A pagar** |
| Despesas | Lista por vencimento crescente: nome, "Vence dd/mm/aaaa", valor e situação (Paga / Pendente / Vencida). Toque abre o detalhe: categoria, parcela, data do pagamento, débito automático |
| Cartões | Um grupo por cartão, com a fatura ("Fatura mm/aaaa" da competência), valor e situação. Toque abre previsto × executado e as **compras** da fatura, carregadas só quando abertas |
| Aviso (D1) | Texto discreto quando **há indício** de competência ainda não gerada; um mês vazio sem indício não gera aviso |
| Vazio | "Nenhuma conta registrada neste mês." |

Sem gráficos, dashboard, cards de indicadores nem animações. Sem formulários: o único controle além de "Sair" é o seletor de perfil. A tela de categorias e contas bancárias continua acessível em `categorias.html`, fora do fluxo principal.

## 2. Funções SQL

Migration `supabase/migrations/20261022090000_financeiro_contas_do_mes.sql` (**não aplicada no remoto**).

| Função | Retorno | Segurança |
|---|---|---|
| `financeiro.contas_do_mes(p_perfil_id, p_mes)` | Contas da competência: `grupo` (DESPESA/FATURA), nome, valor exibido, previsto/executado (faturas), vencimento, pagamento, `situacao`, categoria, cartão, parcela, débito automático | `pode_acessar_perfil`; mês obrigatório |
| `financeiro.lancamentos_da_fatura(p_perfil_id, p_conta_id)` | Compras de uma fatura do perfil: descrição, valor, data, parcela, categoria do cartão | Mesmo erro (42501) para fatura inexistente, de outro perfil ou que não é fatura, para não revelar ids |
| `financeiro.mes_pode_estar_incompleto(p_perfil_id, p_mes)` | Indício (D1): recorrência **mensal** ativa já iniciada sem conta no mês, ou cartão ativo sem fatura no mês | `pode_acessar_perfil` |

Todas são **`STABLE`** (o PostgreSQL recusa escrita em funções não voláteis), `SECURITY DEFINER` com `search_path=''`, e `EXECUTE` só para `authenticated`.

Não expõem: conta bancária, observações, agência, número de conta, número ou código de cartão.

## 3. Regras financeiras reproduzidas (fonte: `GET /api/despesas/` do Flask)

| Regra | Como |
|---|---|
| Competência gravada, não o vencimento | `conta.mes_referencia` (não cartão) e `conta.cartao_competencia` (faturas) |
| Legado sem perfil no Pessoal | `perfil_financeiro_id NULL` entra quando o perfil é o "Pessoal" (contas, faturas e compras) |
| Fatura pendente | **Previsto** = executado + Σ max(0, limite − gasto) por categoria de cartão com limite **ativo** |
| Fatura paga | **Executado** = soma das compras do cartão com `mes_fatura` = competência |
| Vigência dos limites | Ignorada, **como no Flask** (filtra só `ativo`) |
| Cada fatura uma vez; compras fora do total | Compras (`lancamento_agregado`) não são contas; o total soma despesas + o valor de cada fatura |
| Situação (D3) | `Pago` → PAGA (**prioridade**: paga nunca vira vencida); `Atrasado` ou não paga com vencimento < hoje (`America/Sao_Paulo`) → VENCIDA; senão PENDENTE |
| Totais | Total = Σ valor; Pago = Σ das PAGAS; A pagar = Total − Pago. Mesma regra do resumo do Flask, somada em centavos |

## 4. Diferenças intencionais em relação ao Flask

| Flask (`GET /api/despesas/?mes_referencia=`) | Mobile | Motivo |
|---|---|---|
| **Gera** contas de recorrências e faturas virtuais ao abrir o mês | Não gera; mostra só o que existe, com aviso discreto de indício (D1) | Consulta não grava; geração será explícita e transacional |
| **Baixa** débitos automáticos vencidos com saldo | Não baixa; mostra a situação gravada (D2) | Idem |
| Ordena por vencimento decrescente | Vencimento **crescente** | Próxima conta a pagar primeiro |
| Situação só Pago / Pendente / Atrasado | Acrescenta **VENCIDA** derivada (D3) | Pedido da tela |
| — | Compras exibem `descricao_exibida` (editada pelo usuário) ou, na falta, `descricao` | **Não é diferença:** é o mesmo critério do Flask (`CartaoService`: `descricao_exibida or descricao`) |

## 5. Testes

| Suíte | Resultado |
|---|---|
| `tests/test_supabase_contas_mes.py` (equivalência + segurança, banco e REST) | **38 passed** |
| E2E isolado (`run_e2e.py`): 9 AUTH-REAL-1 + 5 PERFIS-1 + **11 Contas do mês** (celular 390 px) | **25 passed, 3 execuções seguidas** |
| Build e código-fonte (RPC só da lista de leitura) | **7 passed** |
| Suíte completa (`pytest`, com `POSTGREST_BIN`) | **1135 passed, 5 failed**: as mesmas 5 falhas preexistentes (commit `0e04407`); nenhuma regressão |

**Equivalência com o Flask.** O mesmo banco fictício é lido pelo **Flask real** e pela fachada. Os efeitos colaterais do Flask foram isolados:
- listagem sem `mes_referencia`, ou seja, sem geração, e filtrada por `mes_competencia` como no próprio resumo;
- baixa de débito automático neutralizada;
- **impressão digital das tabelas financeiras idêntica** antes e depois.

Casos comparados, com mesmas contas, valores, vencimentos, pago, totais e valores esperados calculados à mão:

| Caso | Total | Pago |
|---|---|---|
| Pessoal 11/2026 | R$ 4.390,50 | R$ 270,50 |
| Pessoal 01/2026 | R$ 3.330,50 | R$ 650,50 |
| Empresa 11/2026 | R$ 1.450,00 | — |
| Perfil B 11/2026 | R$ 999,99 | — |
| Mês vazio | R$ 0,00 | — |

**Nenhuma divergência monetária.**

Cobertura exigida:

| Caso | Onde |
|---|---|
| Competência ≠ vencimento | Aluguel de 11/2026 vence em 05/12 e fica em novembro |
| Pagas, pendentes e vencidas | Inclusive "Atrasado" e uma paga com vencimento passado (PAGA) |
| Fatura paga | Executado R$ 120,00, ignorando o limite |
| Fatura pendente com previsto por categoria | Executado R$ 1.220,00; Mercado +100; Restaurantes +0; limite inativo ignorado → R$ 1.320,00 |
| Múltiplos cartões | Azul, Verde (legado sem perfil) e Empresa |
| Compras dentro da fatura | 6 compras, incluindo uma parcelada e uma legado; compra de dezembro fora |
| Pessoal com legado sem perfil e Empresa isolada | ✅ |
| Mês sem contas | ✅, com e sem indício de não geração |
| Sem dupla contagem | Total R$ 4.390,50, e não R$ 5.730,50 com as compras somadas |

**Segurança:**
- Funções `STABLE`/definer/`search_path` vazio e só para `authenticated`.
- Perfil de outro usuário ou inativo → 42501/403.
- Fatura de outro perfil, despesa ou id inexistente no detalhe → 42501.
- Anônimo → negado.
- Consultas da fachada não alteram nada (impressão digital).
- REST sem campos sensíveis.
- E2E: perfil adulterado no navegador volta ao autorizado, e chamadas diretas com o perfil de B ou a fatura da Empresa → 403.
- Na tela de celular: sem rolagem horizontal, nenhuma ação de escrita e CSP sem violação.

## 6. Limitação: competências não geradas (D1)

O Flask cria as contas recorrentes e as faturas **quando o mês é aberto nele**. Enquanto essa geração não for explícita na nova arquitetura (MOBILE-CONTAS-2 ou rotina agendada), um mês nunca aberto no Flask pode aparecer **incompleto** no celular.

O aviso aparece quando há indício: recorrência mensal ativa sem conta no mês, ou cartão ativo sem fatura. Recorrências semanais ou anuais não disparam o aviso, e um mês vazio sem indício também não.

## 7. Próxima etapa para validar no Supabase real (exige autorização)

1. Push deste commit. Ele **não** aplica a migration, porque o deploy automático está desligado: a prova da SUPABASE-DEPLOY-CONTROL-1 é conferir que ela continua pendente depois do push.
2. `scripts/supabase_migrations.py aplicar --versoes 20261022090000`.
3. Dados fictícios temporários no projeto de teste (perfis/vínculos como no PERFIS-REAL-1, mais contas, faturas, compras e limites), com limpeza e impressão digital.
4. `run_e2e_real.py` com os 25 cenários. Hoje ele bloqueia porque a migration não está no remoto.

## 8. Arquivos alterados

- **Novos:**
  - `supabase/migrations/20261022090000_financeiro_contas_do_mes.sql`;
  - `tests/test_supabase_contas_mes.py`;
  - `web/src/contas.html`;
  - `web/src/js/contas.js`;
  - `web/tests/e2e/contas.spec.mjs`;
  - este relatório.
- **Alterados:**
  - `web/src/js/sessao.js` (tela inicial `contas.html`);
  - `web/src/css/app.css`;
  - `tests/supabase_local.py` (`semear_contas`, `CONTAS_MES_ESPERADO`);
  - `web/tests/e2e/acesso.spec.mjs` e `perfis.spec.mjs` (login agora leva a Contas do mês);
  - `web/tests/unit/build.test.mjs` (lista de RPC de leitura);
  - `web/tests/e2e/run_e2e_real.py` (trava da migration);
  - `docs/ROADMAP.md`.
- **Flask:** nenhum arquivo alterado.
