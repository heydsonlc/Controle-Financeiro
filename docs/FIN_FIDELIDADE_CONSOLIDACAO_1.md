# FIN-FIDELIDADE-CONSOLIDACAO-1 (MVP 6) — Dashboard, homologação integrada e relatório consolidado

**Situação (25/10/2026):** Dashboard implementado e testado localmente; relatório consolidado da fila (MVPs 1–6) abaixo.
- Sem commit, sem push, sem migration persistente e sem publicação. Nada foi aplicado no Supabase de teste nem em produção.
- O Flask, o `gastos.db` e os arquivos pessoais não foram tocados.

## 1. Dashboard (feito)

- **Migration `20261114090000_financeiro_dashboard_leitura.sql`:** `dashboard_resumo_tela(perfil, mes_referencia)`.
  - Reproduz `DashboardService.obter_resumo` (`GET /api/dashboard/resumo`):
    - KPIs, fluxo de caixa projetado e faturas em aberto;
    - recorrências e contas a vencer em 7 dias;
    - categorias e limites dos cartões;
    - alertas: vencimento hoje, limites acima de 80%, previstas atrasadas, documentos empresariais vencidos e vencendo;
    - mobilidade e ações rápidas.
  - "Hoje" é a data de Brasília. Mês inválido = mês atual, como no Flask.
- **Tela original** (`web/src/paginas/dashboard.html`, de `frontend/templates/index.html`):
  - Chart.js do próprio Flask (`frontend/static/vendor`, versionado) servido pelo site, sem mudar a CSP;
  - ícones de categoria e bandeiras versionados incluídos no build;
  - links fixos `/despesas`, `/veiculos` e `/cartoes` trocados pelas páginas daqui.
- **Adaptador** (`web/src/js/dashboard-adaptador.js`) e `dashboard-adaptacoes.js`.
  - O JS do Flask monta as "ações rápidas" com rotas do Flask; o segundo arquivo só reaponta esses links para as páginas daqui.
  - "Confirmar despesas previstas" e "Gerenciar mobilidade" vão para Mobilidade, ainda em migração, que informa isso.
- **Achados do Flask, classificados:**
  - **D1 (corrigido, isolamento):** `despesas_previstas_mes` (valor, pendentes, confirmadas) soma as despesas previstas de **todos os perfis**: a consulta do Flask não filtra o perfil. O novo filtra. O teste mostra a diferença: na Empresa o Flask exibe as previstas do Pessoal.
  - **D2 (mantido, decisão do titular):** "receitas previstas" do fluxo = recebido + orçado do mês. Quando a previsão já foi recebida, conta duas vezes. Mantido igual ao Flask até decisão.
  - Em 1366 px as duas primeiras ações rápidas rolam por baixo dos controles da barra. É o CSS do Flask, não alterado.
- **Testes:**
  - `tests/test_supabase_dashboard_leitura.py`, **6 passaram**.
    - O próprio Flask responde para Pessoal, Empresa e Perfil B em 5 meses (atual, vazio, 2027-03, data completa, inválido).
    - Comparação campo a campo, inclusive com linhas fictícias que acionam todos os alertas e a mobilidade.
  - `web/tests/e2e/dashboard_tela.spec.mjs`, **1 passou**: KPIs iguais à função, gráfico, ações rápidas para páginas daqui, sem erro de CSP.

## 2. Configurações e Manual

- Já estavam migrados antes desta fila: `configuracoes.html` (perfis financeiros) e `ajuda.html`.
- Nesta fila não houve mudança de comportamento neles.
- O menu do Manual continua apontando para as páginas migradas: o teste `moldura.spec.mjs` percorre todas.

## 3. Homologação integrada (local)

| Conjunto | Resultado |
|---|---|
| Testes de banco novos da fila (contas bancárias, lançamentos, financiamentos, consórcios, patrimônio, mobilidade, documentos fiscais e da empresa, saídas sem documento, dashboard, abrir arquivo) | **55 passaram** |
| E2E local completo (cluster descartável + PostgREST + Playwright) | **87 passaram**, 0 falhas (com Mobilidade, Consórcios, Documentos da Empresa e abrir arquivo) |
| Unitários do `web/` (build, auditoria de RPC, moldura, PDF, XLSX) | **30 passaram** |
| Suíte completa `tests/` (inclui o Flask) | 5 falhas, todas preexistentes ou de ambiente (P7 de `docs/DEPLOY_READY_FIN_1.md`). As 2 do mapa de impacto foram corrigidas (`scripts/testes_impacto.py` lê as páginas da moldura) |

- **Homologação real** (Supabase de teste): **não executada**. Exige autorização para aplicar as migrations (§5).
  - Depois disso: rodar `run_e2e_real.py` com os seeds fictícios e a limpeza por identidade.
  - O script de validação real (`fase1_real.py`, no scratchpad) precisa da lista de adaptadores atualizada.

## 4. Relatório consolidado da fila

| MVP | Entregue (local) | Bloqueado / pendente |
|---|---|---|
| 1 CARTOES-3 | R2, PDF, R4, testes de integração (`docs/FIN_FIDELIDADE_CARTOES_1.md` §21) | §17 (combustível = limite da categoria) aguarda confirmação |
| 2 MOVIMENTACOES-1 | Contas Bancárias (CRUD, saldos, extrato, ajustes, transferências) e Lançamentos (compras, despesas diretas, receitas em leitura); P1 de Despesas resolvido (`docs/FIN_FIDELIDADE_MOVIMENTACOES_1.md`) | recusas de Lançamentos do §6 aguardam confirmação |
| 3 CONTRATOS-1 | Financiamentos: consulta fiel (lista, detalhe, parcelas). **Consórcios: consulta fiel** (lista e detalhe, de volta à tela de Recorrências) | **Pagamento/estorno e motor de cálculo bloqueados pelo escritor único:** o Flask escreve parcelas mesmo em perfil do novo aplicativo; exige autorizar uma guarda pequena no Flask (§6 do doc). Escrita de consórcios: mesmo bloqueio |
| 4 PATRIMONIO-1 | Patrimônio: consulta fiel (caixinhas, transferências, bens com documento e imagem, resumo). **Mobilidade: consulta fiel** (veículos, projeções, uso, manutenção por km, financiamento do veículo, modalidade ativa, assinaturas, transporte por app; 23 rotas comparadas) | escrita (mesmo bloqueio do escritor único); defeito D-MOB1 do Flask (salvar financiamento do veículo sempre falha) |
| 5 DOCUMENTOS-1 | Imposto de Renda: consulta fiel nos modos IRPF **e Documentos da Empresa** (taxonomia, metadados persistidos ou inferidos, resumo, checklist) e **saídas sem documento** (14 combinações de filtros comparadas); **"Abrir arquivo"** com o arquivo do Supabase; defeito D-DOC1 do Flask corrigido | envio/OCR, relatórios Excel/PDF/ZIP, escrita e "A partir de documento" |
| 6 CONSOLIDACAO-1 | Dashboard fiel (com correção D1) | homologação real; D2 |

**Princípio aplicado em toda a fila:**
- Onde o Flask ainda escreve sem consultar o escritor único, o novo aplicativo só lê.
- As telas mostram um aviso de fase, e toda ação de escrita responde "continua no sistema atual. Nada foi gravado.", sem gravar.
- Leituras do Flask que gravam (categorias IR iniciais, categorias sistêmicas de Mobilidade) não foram reproduzidas como gravação.

## 5. Autorizações necessárias (nenhuma foi assumida)

1. **Commits por MVP.**
   - Os arquivos compartilhados recebem trechos de vários MVPs: `web/scripts/build.mjs`, `web/tests/unit/build.test.mjs`, `web/tests/e2e/moldura.spec.mjs`, `web/src/moldura/em-migracao.json`, `web/tests/e2e/run_e2e.py`, `tests/supabase_local.py`.
   - Proposta: um commit por MVP com os arquivos novos dele, e os compartilhados no commit do último MVP que os altera. A alternativa é separar por trechos, o que exige `git add -p` feito pelo titular.
   - Arquivos por MVP:
     - **MVP 1:** `tests/test_supabase_recorrencia_cartao.py`, `tests/test_supabase_gerador_sem_cartao.py`, migrations `20261107*` e `20261108*`, `supabase/reversao/`, `web/src/js/importacao-pdf.js`, `web/src/js/importar-cartao-adaptador.js`, `web/tests/pdf-ficticio.mjs`, `web/tests/unit/importacao-pdf.test.mjs`, `web/tests/e2e/importar_cartao.spec.mjs`, `web/tests/e2e/recorrencias_tela.spec.mjs`, `web/package*.json`, `docs/FIN_FIDELIDADE_CARTOES_1.md`.
     - **MVP 2:** migration `20261109*`, `tests/test_supabase_contas_bancarias.py`, `tests/test_supabase_lancamentos_tela.py`, `web/src/{paginas,js,css}/contas-bancarias*` e `lancamentos*`, `web/src/js/ponte-csp.js`, specs `contas_bancarias_tela` e `lancamentos_tela`, `web/tests/e2e/perfis.spec.mjs`, `docs/FIN_FIDELIDADE_MOVIMENTACOES_1.md`.
     - **MVP 3:** migrations `20261110*` e `20261116*`, `tests/test_supabase_financiamentos_leitura.py`, `tests/test_supabase_consorcios_leitura.py`, `financiamentos*` (página, adaptador, CSS, spec), `web/src/js/recorrencias-adaptador.js` e `web/src/paginas/recorrencias.html` (consórcios), `docs/FIN_FIDELIDADE_CONTRATOS_1.md`.
     - **MVP 4:** migrations `20261112*` e `20261115*`, `tests/test_supabase_patrimonio_leitura.py`, `tests/test_supabase_mobilidade_leitura.py`, `patrimonio*`, `mobilidade*`, `docs/FIN_FIDELIDADE_PATRIMONIO_1.md`.
     - **MVP 5:** migrations `20261113*`, `20261117*` e `20261118*`, `tests/test_supabase_documentos_fiscais_leitura.py`, `tests/test_supabase_lastro_saidas_leitura.py`, `tests/test_supabase_arquivo_comprovante.py`, `documentos-fiscais*`, `web/src/js/arquivo-comprovante.js`, `docs/FIN_FIDELIDADE_DOCUMENTOS_1.md`.
     - **MVP 6:** migration `20261114*`, `tests/test_supabase_dashboard_leitura.py`, `dashboard*`, `scripts/testes_impacto.py` e `tests/test_testes_impacto.py` (mapa de impacto), este documento e os arquivos compartilhados.
2. **Migrations no Supabase de teste**, nesta ordem: `20261106` (já no commit b1c1ac6, não aplicada), `20261107`, `20261108`, `20261109`, `20261110`, `20261112`, `20261113`, `20261114`, `20261115`, `20261116`, `20261117`, `20261118`.
   - As de 20261110 em diante criam só funções de leitura.
   - A 20261109 traz as funções de escrita de contas bancárias. As do MVP 1 estão em `docs/FIN_FIDELIDADE_CARTOES_1.md`.
3. **Publicação na prévia** (`--branch avaliacao`), depois da homologação real.
4. **Decisões:**
   - escritor único para parcelas de financiamento e escrita de patrimônio (guarda no Flask);
   - D1 do MVP 3 (estorno em Despesas não reabre a parcela);
   - D2 do Dashboard;
   - OCR (MVP 5);
   - §17 do MVP 1;
   - §6 do MVP 2.
5. **Conferências somente leitura no Supabase de teste:**
   - categorias IR iniciais existem;
   - categorias sistêmicas `MOB_*` existem com `codigo_sistema`.

## 6. Registro de parada (formato da diretriz)

- **Último MVP trabalhado:** 6 (FIN-FIDELIDADE-CONSOLIDACAO-1).
- **Funcionalidades concluídas:** as da coluna "Entregue" do §4.
- **Arquivos alterados:** §5 item 1. Os pessoais não rastreados não foram tocados.
- **Testes executados:** §3.
- **Pendências:** §4 (coluna "Bloqueado / pendente") e §5.
- **Próxima ação exata:** obter as autorizações do §5.
  - A Mobilidade, fase 1, foi feita depois do primeiro relatório: `docs/FIN_FIDELIDADE_PATRIMONIO_1.md` §7.
  - Todos os módulos do menu já têm ao menos a consulta no novo aplicativo.
  - Consórcios, Documentos da Empresa e saídas sem documento também ganharam a consulta.
  - O que resta depende de autorização: escrita sob escritor único, arquivos/OCR e homologação real.

## 7. E2E completo ao fim da fila

- **87 passaram, 0 falhas** (2,5 min), já com Mobilidade, Consórcios, Documentos da Empresa e abrir arquivo.
  - Eram 76 antes do MVP 3.
  - Foram acrescentados: Financiamentos 2, Patrimônio 2, Documentos Fiscais 4, Dashboard 1 e Mobilidade 2.
- `gastos.db` conferido inalterado (1294336 bytes, mtime 1778600040).
