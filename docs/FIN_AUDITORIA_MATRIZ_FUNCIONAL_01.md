# FIN-AUDITORIA-PUBLICACAO-MIGRACAO-01 — B. Matriz funcional (Flask → GitHub → Supabase → Cloudflare)

**Data de referência:** 15/11/2026. **Natureza:** somente leitura.

## Como ler

- **Origem:** rota ou serviço do Flask (`backend/routes/…`).
- **Destino:** adaptador ou serviço do aplicativo novo (`web/src/js/…`) e a função do Supabase.
- **Publicação:** tudo o que está em `web/src` está no deploy `45e24f88` (commit `1ce28cb`), idêntico ao build em 225 de 225 arquivos. Todas as migrations estão aplicadas, 67 de 67, com funções idênticas. Por isso a coluna de publicação só aparece quando há algo a dizer.
- **Uso real:** contagens da produção em 15/11/2026, sem conteúdo.
- **Critério de classificação:**
  - **CONCLUÍDO** = publicado, com teste automatizado e com uso real na produção ou homologação registrada do titular;
  - **PUBLICADO NÃO HOMOLOGADO** = publicado e testado, sem uso real nem homologação registrada.
  - As demais seguem a tabela do contrato.
- As 30 operações de **Documentos Fiscais** estão em `FIN_AUDITORIA_DOCUMENTOS_FISCAIS_01.md` e entram aqui só no total.

## Matriz

| # | Módulo | Funcionalidade | Origem (Flask) | Destino (novo → banco) | Testes | Uso real / homologação | Classificação | Pendência | Pri. |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Acesso | Login, sessão, sair | `app.py:242-276` (Flask-Login) | `login.js`, `sessao.js` → Supabase Auth | e2e `acesso` (9) | 1 usuário ativo, acesso em 15/11 | CONCLUÍDO | — | — |
| 2 | Acesso | Páginas protegidas | `app.py:161-185` | `sessao.js` (`exigirUsuario`, `PAGINAS_PERMITIDAS`) | e2e `acesso`, `moldura` | conferido sem login em produção | CONCLUÍDO | — | — |
| 3 | Acesso | Recuperar ou trocar senha | não existia | não existe (feito pelo painel do Supabase) | — | — | FORA DO ESCOPO | — | — |
| 4 | Perfis | Seletor de perfil (desktop) | `perfis.py:106` | `moldura.js`, `perfil.js` → `meus_perfis` | e2e `perfis` (5) | 2 perfis reais | CONCLUÍDO | — | — |
| 5 | Perfis | Criar, editar, inativar, padrão | `perfis.py:51-95` | `configuracoes.js` → `criar_perfil`, `atualizar_perfil`… | e2e `perfis_gestao` (3); `test_supabase_perfis_gestao` (25) | sem registro de uso | PUBLICADO NÃO HOMOLOGADO | Homologar | P3 |
| 6 | Perfis | Isolamento e somente leitura | filtros por perfil | `pode_acessar_perfil`, `pode_gerir_perfil` em todas as funções | `test_supabase_mvp_rls` (21), `perfis` (20) | privilégios conferidos na produção | CONCLUÍDO | — | — |
| 7 | Dashboard | Resumo operacional | `dashboard.py:47` | `dashboard-adaptador.js:37` → `dashboard_resumo_tela` | e2e `dashboard_tela`; `test_supabase_dashboard_leitura` (5) | em uso | CONCLUÍDO | — | — |
| 8 | Dashboard | Indicadores, gráficos, fluxo projetado | `dashboard.py:303-752` (7 rotas) | sem rota: a tela original só chama `/resumo` (`frontend/static/js/dashboard.js`) | — | — | FORA DO ESCOPO | — | — |
| 9 | Dashboard | Alertas (sino do topo) | `dashboard.py:611` | "Alertas: em migração para o novo aplicativo." (`moldura/base.html:228`) | e2e `moldura` (aviso) | — | NÃO MIGRADO | Implementar ou retirar o sino | P3 |
| 10 | Despesas | Listar, criar, editar, excluir | `despesas.py:285-1056` | `despesas-servico.js:594-598` → `contas_do_mes`, `criar_despesa`, `editar_despesa`, `excluir_despesa` | e2e `contas` (14), `despesas` (7); banco `despesas` (32) | 813 contas | CONCLUÍDO | — | — |
| 11 | Despesas | Pagar e estornar | `despesas.py:1173,1317` | `:600,603` → `pagar_despesa`, `estornar_pagamento_despesa` | idem | 234 pagas, 82 movimentos | CONCLUÍDO | — | — |
| 12 | Despesas | Pagamento em lote (semanal) | (lote do desktop) | `:602` → `pagar_despesas_lote` | e2e `despesas_pagamento_lote` (5); banco (23) | publicado em 08/11 | CONCLUÍDO | — | — |
| 13 | Despesas | Cancelar obrigação (P23) | não existia | `:598` → `cancelar_despesa` | e2e `despesas_cancelamento` (2); banco (20) | publicado em 11/11 | CONCLUÍDO | — | — |
| 14 | Despesas | Geração automática das recorrências | ao listar (`despesas.py:285`) | `despesas-recorrencias.js:17,29` → `previa_geracao`, `gerar_mes` | banco `gerador_t1` (19), `recorrencia` (34) | gerador NOVO nos 2 perfis | CONCLUÍDO | — | — |
| 15 | Despesas | Consolidar (fechar) fatura | `cartoes.py:1178` | `emMigracao('Consolidação de fatura')` (`despesas-servico.js:619`); nenhuma função do banco grava `status_fatura = 'FECHADA'` | — | — | NÃO MIGRADO | Decidir se a consolidação manual volta; hoje o banco só lê faturas já fechadas | P2 |
| 16 | Despesas | Despesas previstas (confirmar, adiar, ignorar) | `despesas_previstas.py` | `mobilidade-adaptador.js:226-235` → `confirmar_despesa_prevista`… | banco `mobilidade_projecoes` (37) | 15 previstas | CONCLUÍDO | — | — |
| 17 | Receitas | Fontes e previsões | `receitas.py:95-453` | `receitas-servico.js:264-277` → `criar_receita`, `editar_fonte_receita`… | e2e `receitas_tela` (4); banco `receitas` (30) | 7 fontes | CONCLUÍDO | — | — |
| 18 | Receitas | Receber e estornar | `receitas.py:694-976` | `:283-284` → `receber_receita`, `estornar_recebimento` | e2e `receitas_saldo` (3) | 11 recebimentos | CONCLUÍDO | — | — |
| 19 | Receitas | Editar recebimento; receber sem fonte; excluir recebimento sem conta | `receitas.py:580,807,918` | recusas "ainda não está disponível" (`receitas-servico.js:180,244-246,259`) | — | — | PARCIAL | Definir se entram; a correção hoje é estornar e receber de novo | P3 |
| 20 | Cartões | Cadastro, limites por categoria, cartões vinculados | `cartoes.py:111-501` | `cartoes-servico.js:326-340` → `criar_cartao`, `vincular_limite_cartao`… | e2e `cartoes_tela` (5), `cartoes_multiplos`; banco `cartoes` (36) | 2 cartões | CONCLUÍDO | — | — |
| 21 | Cartões | Compras, parcelas, fatura por categoria, pagar e estornar fatura | `cartoes.py:801-1052` | `:341-347`; `despesas-servico.js:600-607` → `criar_compra`, `pagar_fatura`… | e2e `fatura_*`; banco `fatura_unica`, `cartoes_executado` | 171 compras, 43 pagamentos de fatura | CONCLUÍDO | — | — |
| 22 | Cartões | Número completo, validade e CVV | colunas em `models.py:710-761` | recusados (`cartoes-servico.js:79,330-331`) | e2e `cartoes_tela` | produção: só 4 dígitos, sem CVV | FORA DO ESCOPO | Intencional (segurança) | — |
| 23 | Cartões | Itens internos, orçamentos com vigência, resumo e alertas de orçamento | `cartoes.py:303-382, 557-680, 1074, 1265-1301` | sem rota no serviço novo (os limites por categoria substituem) | — | não verificado se a tela original ainda os chama | NÃO COMPROVADO | Conferir na tela; se chamar, cai em "não disponível" | P3 |
| 24 | Importar cartão | Analisar e importar CSV, XLSX e PDF | `importacao_cartao.py:34-322` | `importar-cartao-adaptador.js:369-374` → `analisar_importacao_cartao`, `importar_fatura_cartao`; leitura no navegador | e2e `importar_*` (7); banco (107 em 6 arquivos) | importações de 11/2026 | CONCLUÍDO | — | — |
| 25 | Importar cartão | Vincular linha a uma recorrência escolhida | `importacao_cartao.py:366` | 501 "…em migração" (`:375-376`) | — | — | NÃO MIGRADO | O reconhecimento por nome já cobre o caso comum | P3 |
| 26 | Recorrências | Listar, criar, editar, inativar e reativar (P22) | `recorrencias.py:235-409` | `recorrencias-servico.js:409-416` → `criar_despesa`, `editar_recorrencia`, `interromper_recorrencia`, `retomar_recorrencia` | e2e `recorrencias_tela` (9), `recorrencias_inativacao`; banco (77) | 28 ativas | CONCLUÍDO | — | — |
| 27 | Recorrências | Recorrência no cartão | idem | `criar_recorrencia_cartao`, `editar_recorrencia_cartao` | banco `recorrencia_cartao` (16) | em uso | CONCLUÍDO | — | — |
| 28 | Consórcios | Contratos, parcelas, regenerar, contemplação (P24) | `consorcios.py:451-704` | `recorrencias-servico.js:421-426` → `criar_consorcio`…; `realizar_contemplacao_consorcio` | e2e `consorcios_p24` (3); banco (26) | 7 contratos | CONCLUÍDO | — | — |
| 29 | Contas bancárias | Cadastro, extrato, ajuste, conferência de saldo | `contas_bancarias.py:76-661` | `contas-bancarias-adaptador.js:102-113` → `criar_conta_bancaria`, `extrato_conta_bancaria`… | e2e `contas_bancarias_tela`, `movimentacoes`; banco (27) | 2 contas, 82 movimentos | CONCLUÍDO | — | — |
| 30 | Contas bancárias | Transferência entre contas | `contas_bancarias.py:605` | `contas-servico.js:80` → `transferir_entre_contas` | e2e `mobile06`, `mobile07` | 0 transferências reais; homologada na prévia (MOBILE-06) | CONCLUÍDO | — | — |
| 31 | Lançamentos | Compra no cartão, despesa direta, abastecimento | página `lancamentos.html` (sem blueprint) | `lancamentos-adaptador.js:260-280` → `criar_compra`, `criar_despesa`, `salvar_lancamento_abastecimento` | e2e `lancamentos_*` (10) | em uso | CONCLUÍDO | — | — |
| 32 | Lançamentos | Receita pela tela Lançamentos | `receitas.py:694,807` | recusa orientando "use Receitas → Receber" (`:257,284-285`) | e2e `lancamentos_tela` | — | PARCIAL | Recebimento exige conta; fica na tela Receitas | P3 |
| 33 | Financiamentos | Contratos SAC/TR, parcelas, amortização extra, ajuste de saldo, vigência de seguro, simular quitação | `financiamentos.py:145-1406` | `financiamentos-adaptador.js:117-127` → `criar_financiamento`, `registrar_amortizacao_extra`… | e2e `financiamentos_*` (4); banco `financiamentos_motor` (23), `tr_projetada` | 1 contrato, 420 parcelas | CONCLUÍDO | — | — |
| 34 | Financiamentos | Pagar e estornar parcela | `financiamentos.py:763,879` | pelo fluxo de Despesas (`:13-15,130`) | e2e `contratos_pagamento` (2) | parcela 30 paga | CONCLUÍDO | — | — |
| 35 | Financiamentos | Documentos do contrato e conferências da Caixa | `financiamentos.py:492-680` (arquivos em disco) | 501 (`financiamentos-adaptador.js:16,144`) | — | 0 documentos | NÃO MIGRADO | Implementar o armazenamento no banco e as conferências | P2 |
| 36 | Financiamentos | Demonstrativo anual e valores simulados | `financiamentos.py:683,1333` | caem no 501 genérico (`:144`) | — | — | NÃO MIGRADO | Implementar a leitura | P2 |
| 37 | Financiamentos | Página Seguro habitacional (faixas e vigências) | `financiamento_seguro.py`; `financiamento_seguro.html` | não há página; só "adicionar vigência" no contrato (`:125`) | — | — | PARCIAL | Avaliar se a página volta | P3 |
| 38 | Indexadores | TR mensal: cadastro, importação por texto, faltantes | `indexadores.py:74-155` | `indexadores-adaptador.js:55-61` → `criar_tr`, `importar_tr`… | e2e `indexadores_tela`; banco (8) | 30 competências, até 10/2026 | CONCLUÍDO | — | — |
| 39 | Indexadores | IPCA, IGP-M, CDI, SELIC (genéricos) | `indexadores.py:20-312` | não trazidos (`paginas/indexadores.html:6-7`) | — | 0 linhas | FORA DO ESCOPO | Intencional | — |
| 40 | Patrimônio | Caixinhas e transferências | `patrimonio.py:206-653` | `patrimonio-adaptador.js:164-172` → `criar_caixinha`, `criar_transferencia_patrimonio` | e2e `patrimonio_tela` (2); banco (16) | 0 caixinhas | PUBLICADO NÃO HOMOLOGADO | Homologar com uso real | P3 |
| 41 | Patrimônio | Bens, vínculo com documento, bem a partir de documento | `patrimonio.py:82-193` | `:173-185` → `criar_bem_patrimonial`, `vincular_documento_bem`… | idem | 0 bens | PUBLICADO NÃO HOMOLOGADO | Idem | P3 |
| 42 | Patrimônio | Relatório de bens em Excel e PDF | `patrimonio.py:118,132` (servidor) | gerado no navegador (`relatorio-patrimonio.js:89,120`) | registro de "PDF idêntico byte a byte" (`ROADMAP.md:230`) | 0 bens | PUBLICADO NÃO HOMOLOGADO | Idem | P3 |
| 43 | Mobilidade | Veículos, projeções, regras por km, financiamento simulado, transporte por app, assinaturas | `veiculos.py`, `mobilidade_app.py` | `mobilidade-adaptador.js:119-235` (cerca de 45 rotas) | e2e `mobilidade_tela*` (8); banco (130) | 1 veículo, 4 projeções; MOB-01/02 homologados | CONCLUÍDO | — | — |
| 44 | Mobilidade | Abastecimentos | não existia | `registrar_abastecimento`, `corrigir_abastecimento`, `vincular_abastecimento` | e2e `lancamentos_abastecimento` (5); banco `mobilidade_abastecimento` (51) | 0 reais; homologado em 07/11 | CONCLUÍDO | — | — |
| 45 | Categorias | Categorias de despesa e palavras-chave | `categorias.py:170-433` | `categorias-adaptador.js:153-173` → `criar_categoria`… | e2e `categorias_tela` (5) | 36 categorias; catálogo NOVO | CONCLUÍDO | — | — |
| 46 | Categorias | Categorias do cartão e vínculos | `categorias.py:652-812` | `:156-165` → `criar_categoria_cartao`… | idem; banco `categorias_consolidacao` | em uso | CONCLUÍDO | — | — |
| 47 | Categorias | Logo da categoria (upload) | `categorias.py:450-551` (disco) | "Upload de logo ainda não disponível" (`:22,174`) | — | — | NÃO MIGRADO | Exige armazenamento de arquivo | P3 |
| 48 | Configurações | Preferências gerais e de comportamento | `preferencias.py:19,51` | `configuracoes.js:332,346` → `preferencias_tela`, `salvar_preferencias` | e2e `preferencias_tela`; banco (7) | 1 registro | PUBLICADO NÃO HOMOLOGADO | Homologar | P3 |
| 49 | Configurações | Importar e exportar configurações | `backup.py:142,153` | "ainda não está disponível" (`configuracoes.js:276-280`) | — | — | NÃO MIGRADO | Baixa utilidade | P3 |
| 50 | Configurações | Aparência, IA e Automação, ferramentas de OCR | `ocr_tools.py`; abas da tela | retiradas (`paginas/configuracoes.html:3-8`) | — | — | FORA DO ESCOPO | Intencional | — |
| 51 | Backup | Backup e restauração verificável | `backup.py` (pg_dump no servidor) | CLI `scripts/backup_banco.py` (fora do aplicativo) | `tests/test_backup_banco.py` (banco descartável) | **nenhum backup real da produção comprovado** | NÃO COMPROVADO | Gerar, guardar com segurança e testar a restauração | **P1** |
| 52 | Backup | Tela de backup e agendamento | `backup.py:63-201` | não migrada (não se aplica ao Supabase) | — | — | FORA DO ESCOPO | Substituída pela CLI | — |
| 53 | Agendamento | Geração mensal agendada de faturas | `scheduler.py` (desligado no próprio Flask) | geração ao abrir a competência (linha 14) | — | — | FORA DO ESCOPO | — | — |
| 54 | Mobile | Página Principal, Lista de Despesas, Cartões, Receitas, Nova Despesa, Registrar Lançamento, Contas (MOBILE-01 a 07) | não existia | `inicio.html` e 6 páginas `*-mobile.html`, pelos serviços do desktop | e2e `mob01`, `mob08_inicio`, `mobile03` a `07`, `mobile_final_integrado` (65) | homologados e publicados em 14/11 | CONCLUÍDO | — | — |
| 55 | Mobile | Pagamentos (MOBILE-08) | não existia | `pagamentos-mobile.html` → `despesas-servico.js` | e2e `mob08_pagamentos` (14 cenários) | homologado e publicado em 15/11 | CONCLUÍDO | — | — |
| 56 | Mobile | Recorrências (MOBILE-09) | não existia | `recorrencias-mobile.html` → `recorrencias-servico.js` | e2e `mob09_recorrencias` (12 cenários) | publicado em 15/11 por autorização direta; aprovado na prévia, sem conferência em produção | PUBLICADO NÃO HOMOLOGADO | Conferir com login em produção | P3 |
| 57 | Mobile | Alternância de perfis (MOBILE-10) | não existia | `inicio.html`, `inicio-mobile.js` → `perfil.js` | e2e `mob10_perfis` (5) | idem | PUBLICADO NÃO HOMOLOGADO | Idem | P3 |
| 58 | Mobile | PWA e ícones (carteira) | não existia | `manifest.webmanifest`, `icones/`, `favicon.ico` | teste `pwa:` do build | o titular confirmou o ícone no aplicativo; o da aba foi corrigido depois | PUBLICADO NÃO HOMOLOGADO | Conferir o ícone da aba e reinstalar no iPhone | P3 |
| 59 | Mobile | Financiamentos, Patrimônio, Documentos, Mobilidade, Categorias, Configurações, Importar, Dashboard e Consórcios no celular | — | só no desktop (as páginas abrem no celular com a moldura do desktop) | e2e `moldura` (celular) | — | FORA DO ESCOPO | Não previstos na série mobile | — |
| 60 | Infra | Migrations Supabase | — | 67 de 67 aplicadas e idênticas | impressão digital de 569 funções | — | CONCLUÍDO | — | — |
| 61 | Infra | Publicação Cloudflare | — | deploy `45e24f88` = build de `1ce28cb` | 225 de 225 arquivos por hash | — | CONCLUÍDO | — | — |

## Totais

| Classificação | Matriz geral (61) | Documentos Fiscais (30) | Total (91) |
|---|---|---|---|
| CONCLUÍDO | 33 | 9 | 42 |
| PUBLICADO NÃO HOMOLOGADO | 8 | 12 | 20 |
| PARCIAL | 3 | 3 | 6 |
| NÃO MIGRADO | 7 | 6 | 13 |
| NÃO COMPROVADO | 2 | 0 | 2 |
| FORA DO ESCOPO | 8 | 0 | 8 |
| DESENVOLVIDO NÃO PUBLICADO | 0 | 0 | 0 |
| MIGRATION PENDENTE | 0 | 0 | 0 |
| DIVERGENTE | 0 | 0 | 0 |

## Testes executados ou citados

| Bateria | Resultado | Quando |
|---|---|---|
| Unitários do build (`web/tests/unit`) | 120 de 120 | 15/11/2026, commit `1ce28cb` |
| E2E completa em navegador, banco descartável (55 specs) | 255 aprovados, 0 reprovados | 15/11/2026, commit `b0b6a3b` (antes do ícone da aba, que rodou 26 de 26 por impacto) |
| Testes de banco (`tests/test_supabase_*.py`, 67 arquivos, 998 testes) | **não reexecutados nesta auditoria** (cerca de 30 GB de temporários por rodada); o último registro é do Bloco C: 2.022 aprovados em toda a suíte (`ROADMAP.md:231`) | — |
| Fidelidade banco × repositório | 569 de 569 funções e 1.057 colunas idênticas | 15/11/2026 |
| Fidelidade deploy × build | 225 de 225 arquivos | 15/11/2026 |

**Limitação.** Nenhum teste funcional foi feito com login em produção: o contrato proíbe gravações, e a sessão é do titular. A homologação com uso real cabe ao titular.
