# MOBILE-CONTAS-1 — Proposta de contrato: Contas do mês (somente leitura)

Preparado em 2026-10-21 a partir da leitura do código do Flask. **Nada foi implementado ainda.** Pré-requisitos atendidos: login real (AUTH-REAL-1), perfis autorizados (PERFIS-REAL-1) e deploy manual de migrations (SUPABASE-DEPLOY-CONTROL-1).

## 1. Objetivo

Tela inicial do Controle Financeiro Mobile, seguindo a lógica da planilha original e sem dashboard:
- mês selecionado, com anterior/próximo;
- **despesas correntes** do mês, ordenadas por vencimento;
- **faturas de cartão** em grupo separado, uma por cartão;
- situação de cada conta: paga, pendente ou vencida;
- **total do mês, total pago e total a pagar**, em uma linha simples de texto;
- detalhe de cada conta e de cada fatura (lançamentos), **somente leitura**.

## 2. Como o Flask calcula hoje (fonte da verdade)

Referência: `GET /api/despesas/?mes_referencia=AAAA-MM` (`backend/routes/despesas.py`, `listar_despesas`).

| Regra | Implementação no Flask |
|---|---|
| Unidade "conta do mês" | Tabela `conta` (uma linha por vencimento). Despesas simples, parcelas, consórcios e financiamentos têm `is_fatura_cartao = false`; **faturas de cartão** são linhas `conta` com `is_fatura_cartao = true` |
| Mês da conta | **Competência explícita**: `conta.mes_referencia` para as não-cartão e `conta.cartao_competencia` para faturas (decisão técnica 14: nunca inferir de datas) |
| Perfil | `condicao_perfil` em `conta` e `lancamento_agregado`: perfil selecionado, e o "Pessoal" inclui linhas com perfil `NULL` |
| Valor da despesa | `conta.valor` |
| Valor da fatura | **Paga** → total executado; **pendente** → total previsto. Executado = soma de `lancamento_agregado.valor` do cartão (`cartao_id`) com `mes_fatura` = competência. Previsto = executado + Σ max(0, limite − gasto) por categoria de cartão com limite ativo (`cartao_categoria_limite`) |
| **Sem duplicar compras de cartão** | As compras ficam em `lancamento_agregado` e **não** são linhas `conta`. O total do mês soma as contas não-cartão **mais** o valor de cada fatura, nunca as compras individuais |
| Pago | `status_pagamento == 'Pago'` (valores possíveis: `Pendente`, `Pago`, `Atrasado`) |
| Totais do mês | `total_mes` = Σ valor das contas da competência; `total_pagas` = Σ das pagas; `total_pendentes` = Σ das não pagas |
| Ordenação no Flask | Vencimento decrescente. A tela mobile usará **crescente** (próximo vencimento primeiro) |

**Efeitos colaterais dentro do GET (ponto crítico):**
1. **Geração preguiçosa:** ao navegar para um mês, o Flask **cria** as contas das despesas recorrentes até o mês + 1 e as faturas "virtuais" dos cartões ativos (mês e mês + 1).
2. **Baixa automática de débito automático** (`executar_baixa_debito_automatico`): marca como pagos débitos vencidos com saldo.

Uma fachada **somente leitura** não reproduz esses dois efeitos. Isso exige decisão (§3).

## 3. Decisões necessárias (usuário)

| # | Decisão | Opções | Recomendação |
|---|---|---|---|
| D1 | Meses ainda não gerados (recorrências e faturas virtuais) | (a) MVP mostra **só o que já existe** no banco, com aviso discreto quando o mês não tiver sido gerado; (b) RPC transacional de geração, que é escrita e fica para o MOBILE-CONTAS-2; (c) geração agendada no banco (`pg_cron`) | **(a) agora**; (b) ou (c) quando houver escrita |
| D2 | Baixa automática de débito automático | (a) MVP não executa, e a conta aparece como está no banco; (b) mover para rotina agendada | **(a) agora**, registrando a diferença |
| D3 | "Vencida" | Derivada: não paga e `data_vencimento < hoje` (fuso `America/Sao_Paulo`), ou `status_pagamento = 'Atrasado'` | Conforme ao lado |
| D4 | Dados para validar no Supabase de teste | Fictícios temporários (como no PERFIS-REAL-1), ou esperar o DATA-MIGRATE | **Fictícios temporários**; migração real só com autorização própria |

## 4. Implementação proposta

**Banco** (nova migration em `supabase/migrations`, aplicada só por `scripts/supabase_migrations.py aplicar --versoes`):

| Função (somente leitura, `SECURITY DEFINER`, `search_path=''`, `EXECUTE` só para `authenticated`) | Retorno |
|---|---|
| `financeiro.contas_do_mes(p_perfil_id int, p_mes date)` | Uma linha por conta da competência: `id, grupo ('DESPESA' ou 'FATURA'), nome, valor, valor_previsto, valor_executado, data_vencimento, data_pagamento, situacao ('PAGA','PENDENTE','VENCIDA'), categoria_nome, categoria_cor, cartao_id, cartao_nome, numero_parcela, total_parcelas, debito_automatico` |
| `financeiro.lancamentos_da_fatura(p_perfil_id int, p_conta_id int)` | Compras da fatura: `descricao, valor, data_compra, numero_parcela, total_parcelas, categoria_cartao` |

As duas validam `financeiro.pode_acessar_perfil` (recusa com 42501), aplicam a regra `NULL → Pessoal`, e expõem **só** as colunas acima: sem conta bancária, observações nem dados de cartão.

**Totais:** calculados a partir das linhas devolvidas, com a mesma regra do Flask. Os testes de equivalência comparam com o resumo (`sidebar`) do Flask.

**Frontend:**
- `contas.html` passa a ser a tela após o login: cabeçalho com perfil e mês (◀ mês ▶); linha de totais; seções "Despesas" e "Cartões"; toque abre o detalhe.
- Mobile primeiro e só leitura, sem gráficos nem cards de indicadores.
- A tela provisória de categorias e contas bancárias sai do fluxo principal.

## 5. Testes obrigatórios

1. **Equivalência com o Flask** (cluster descartável):
   - montar dados fictícios pelos próprios serviços do Flask: despesa simples, recorrente, parcelada, débito automático, cartão com limites por categoria, lançamentos, uma fatura paga e outra pendente, linhas sem perfil e um perfil Empresa;
   - chamar o `GET /api/despesas/?mes_referencia=` do Flask;
   - comparar com `contas_do_mes`: mesmo conjunto (nome, valor, vencimento, pago) e mesmos `total_mes`, `total_pagas` e `total_pendentes`, em vários meses;
   - cobrir os casos: **compras de cartão não somadas fora da fatura**; previsto × executado; Pessoal com `NULL`; isolamento Empresa.
2. **Autorização:** sem login → negado; perfil de outro usuário ou inativo → 403; `p_conta_id` de outro perfil em `lancamentos_da_fatura` → negado; nenhuma escrita.
3. **E2E** (ambiente isolado e depois real): navegação de mês, agrupamento por cartão, situações, totais, detalhe, perfil adulterado, CSP.
4. **Regressão:** testes do AUTH-REAL-1 e do PERFIS-1, suíte completa do Flask, tabelas legadas bloqueadas.
5. **Prova do deploy manual:** a nova migration continua **pendente** depois do push, até `aplicar --versoes` autorizado.

## 6. Fora do escopo

Cadastro e edição de despesas, pagamentos, estornos, geração de recorrências, financiamentos (motor SAC/TR), veículos, OCR, migração de dados reais, publicação no Cloudflare (MOBILE-PWA-1).

## 7. Autorizações que o contrato pedirá

1. Implementação local e testes.
2. Push do código, que **não** aplica a migration, já com o deploy automático desligado.
3. Aplicação da migration nova no Supabase de teste (`aplicar --versoes`).
4. Dados fictícios temporários no remoto e testes reais, com limpeza.
