# FIN-FIDELIDADE-RECORRENCIAS-1 — Tela original de Recorrências do Flask sobre o Supabase

**Situação:** implementada e testada **localmente**.
- Sem commit, push, publicação ou migration remota.
- Padrão do FIN-FIDELIDADE-DESPESAS-1: HTML, CSS e JS do Flask copiados no build, ponte CSP e ponte `/api/`, e um adaptador para as funções do Supabase.

## Funcionalidades identificadas no Flask

Origem: `recorrencias.html`/`.js`/`.css` e `backend/routes/recorrencias.py`.

**A tela:**
- filtros: tipo, status, frequência, categoria e busca;
- 4 indicadores, a agenda do período, a lista (com o próximo vencimento) e a composição;
- formulário de cadastro e edição, incluindo consórcio.

**Regras da rota:**
- Lista: item recorrente do perfil (NULL → Pessoal), menos consórcio.
- Criar: também gera a primeira conta.
- Editar: nome, observações, valor, categoria, vencimento, frequência, meio (com cartão ou conta do débito) e ativo.
- Excluir: na verdade inativa.

**Frequências:**
- mensal e anual;
- semanal a cada N semanas num dia (`semanal_N_D`) e a cada 2 semanas.

**Dependências:** categorias, cartões (recorrência no cartão), contas bancárias (débito automático) e consórcios (a mesma lista).

## Implementado

| Operação | Situação |
|---|---|
| Lista, filtros, indicadores, agenda e composição (tela original) | Funcionando |
| Próximo vencimento | Funcionando: calculado no banco, sem deslizar o dia contratual (31 → 30/28 sem perder o 31) |
| Criar mensal ou anual; observações; débito automático com conta; meio boleto, PIX ou débito | Funcionando. **Sem gerar conta ao salvar**: a geração é explícita em Despesas ("Gerar contas"), e a tela avisa |
| Editar (vale para as próximas contas; as já geradas, inclusive pagas, não mudam) | Funcionando |
| Inativar e reativar (a reativada volta à prévia de geração, com confirmação) | Funcionando |
| Somente leitura: lista sem ações; isolamento por perfil e usuário | Funcionando |
| Perfil gerado pelo Flask: vencimento e frequência não mudam por aqui (escritor único) | Funcionando, com aviso |
| Semanal e a cada 2 semanas | **Pendente:** o gerador só gera mensal e anual. Recusado com aviso; as semanais existentes aparecem e mantêm a frequência |
| Recorrência no cartão | **Pendente** (módulo de cartões). Aparece na lista, mas não é alterada aqui |
| Consórcios | **Pendente** (módulo Consórcios). A lista avisa que ainda não aparecem |

## Integração com Despesas (verificada em E2E)

**Conta gerada a partir da recorrência:**
- nome, valor, categoria, vencimento e competência da recorrência;
- observações no "detalhe";
- meio de pagamento na coluna "Forma de pagamento" (lido da recorrência);
- grupo "Despesas recorrentes".

**Comportamento verificado:**
- Sem duplicidade: reabrir o mês não oferece de novo a mesma conta.
- Inativada, a recorrência sai da prévia; reativada, volta.
- Uma alteração na recorrência não muda a conta já paga.

**Aviso "itens não podem ser gerados":**
- **Causa** (prévia da demonstração, consultada só para leitura): o cadastro de cartão (Flask e novo aplicativo) marca o **próprio cartão** como recorrente. O gerador o rejeitava como "Cartão marcado como recorrência", mas a fatura é gerada pela parte de cartões.
- **Corrigido na apresentação:** o aviso de Despesas ignora só essa rejeição, pelo motivo exato. As demais (sem valor, cartão sem dia de vencimento etc.) continuam.
- **Pendente:** a correção no gerador, porque troca uma função grande do banco.

## Supabase

**Migration local `20261103090000_financeiro_recorrencias_tela.sql`** (não aplicada em nenhum ambiente persistente; sem tabela nova; nenhum dado existente é alterado):
- `recorrencias_do_perfil`: leitura;
- `reativar_recorrencia`;
- `definir_meio_pagamento_recorrencia`: só boleto, PIX ou débito, informativos; o gerador só trata de forma diferente cartão e débito automático.

As duas últimas usam a mesma trava de gestão, perfil e versão de `inativar_recorrencia` e `editar_recorrencia` (FIN-DESPESAS-1).

**Reaproveitado:** `criar_despesa`, `editar_recorrencia`, `inativar_recorrencia`, `categorias_de_despesa`, `cartoes_do_perfil`, `contas_bancarias_do_perfil` e `pode_gerir_perfil`.

**Para publicar a prévia:** é preciso aplicar esta migration no Supabase de teste (autorização específica). Sem ela, a tela Recorrências não lista nada (404 em `recorrencias_do_perfil`). Despesas continua funcionando, porque a leitura do meio de pagamento é opcional.

## Decisões técnicas

1. **Adaptador comum** (`js/adaptador-comum.js`): respostas no formato do Flask, mensagens do banco e chaves de idempotência, agora compartilhados por Despesas e Recorrências. Sem segunda implementação.
2. **Meio "Débito" do formulário de Despesas:** é `debito` (débito comum), como no Flask. Agora é gravado como informativo. O débito automático, que exige a conta, é cadastrado na tela Recorrências.
3. **Diferenças em relação ao Flask:**
   - salvar não gera a primeira conta (geração explícita);
   - o campo "Dia da semana" fica oculto na frequência mensal (o JS original pede isso; no Flask o CSS da página anulava o `hidden`);
   - a data do primeiro vencimento passa a ser obrigatória (sem ela a recorrência nunca gera);
   - consórcios ainda fora da lista.

## Testes

| Conjunto | Resultado |
|---|---|
| `tests/test_supabase_recorrencias_tela.py` (novo) | 11/11 |
| Suítes de banco (`test_supabase_*`, `test_sec_supabase_public`, `test_movimentacoes`) | Todas aprovadas |
| Conferência local da migration | Só as 3 funções previstas; privilégios conforme o esperado |
| Unitários do build | 17/17 |
| E2E completos | **69/69**, incluindo `recorrencias_tela.spec`: tela, recusas, cadastro, edição, geração em Despesas, conta paga preservada, inativar e reativar, somente leitura, isolamento, perfil Flask e aviso do cartão |

**Comparação visual:** o Flask (SQLite temporário) e o novo aplicativo, com dados fictícios equivalentes, têm o mesmo layout. As capturas estão em `scratchpad/capturas_recorrencias`.

## Pendências reais (prioridades do titular, 25/10/2026)

| # | Pendência | Prioridade | Encaminhamento |
|---|---|---|---|
| R1 | Gerar semanal e a cada 2 semanas | Alta | Contrato de integração do gerador |
| R2 | Recorrência no cartão (cadastro e edição) | Alta | Bloco Cartões + Importar Cartão (FIN-FIDELIDADE-CARTOES-1) |
| R3 | Consórcios na lista e no formulário | Alta | Migração de Consórcios |
| R4 | Gerador pular o cartão marcado como recorrente | Média | Evolução segura do gerador |

**R4: correção visual não é correção da regra.** Só o **aviso** de Despesas deixou de mostrar a rejeição "Cartão marcado como recorrência". **A regra do gerador não mudou**:
- a prévia e o relatório de `gerar_mes` continuam contando essa rejeição;
- o resultado da geração pode dizer "1 rejeitada".

R4 só estará resolvida quando o gerador deixar de considerar o cartão (item "Agregador") como recorrência.
