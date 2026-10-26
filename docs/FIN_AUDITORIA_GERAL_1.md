# FIN-AUDITORIA-GERAL-1 — Auditoria de fidelidade, integração e prontidão operacional (Flask → Supabase)

**Data:** 25/10/2026.
**Base auditada:** branch `main`, HEAD `b1c1ac6`, mais 80 arquivos sem commit (19 modificados, 61 novos; os arquivos pessoais não rastreados foram excluídos da contagem).

**Fontes de verdade usadas:**
- o código do repositório;
- `scripts/supabase_migrations.py status`, que lê o histórico do Supabase de teste;
- consultas **somente leitura** ao Supabase de teste e ao `gastos.db` (só contagens; `mode=ro&immutable=1`; tamanho e mtime conferidos, inalterados);
- as suítes de teste executadas nesta auditoria.

**O que não foi feito:** nada foi gravado, aplicado, commitado ou publicado.

**Critério das classes:**
- **F0:** não existe.
- **F1:** só interface.
- **F2:** consulta funcional, escrita bloqueada.
- **F3:** escrita desenvolvida e testada localmente, dependendo de migration ou autorização.
- **F4:** validada no Supabase de teste e publicada na prévia.
- **F5:** homologada pelo titular.

**Nenhum item está em F5:** os documentos registram só validação técnica ("A homologação depende do titular", em `FIN_FIDELIDADE_RECORRENCIAS_1.md` e `FIN_FIDELIDADE_CARTOES_1.md` §3).

## A. Resumo executivo

1. **Todos os 15 módulos do menu abrem no novo aplicativo**, além de Consórcios e Documentos da Empresa. Nenhum continua como página "em migração" (`web/src/moldura/em-migracao.json` vazio).
   - **12 dos 15 usam a tela original do Flask**, com o JS do Flask em `js/original/`.
   - **Receitas e Categorias** ainda são telas próprias e simplificadas: 31 e 46 linhas, contra 524 e 237 no Flask.
   - **Configurações** reproduz as seções do Flask, mas só Perfis grava.
2. **Escrita real existe em 7 áreas:** Despesas (inclusive faturas e pagamentos), Receitas, Recorrências, Cartões, Importar Cartão, Contas Bancárias e Perfis. São **46 funções de escrita** auditadas (`RPCS_DE_ESCRITA` em `web/tests/unit/build.test.mjs`).
   - **37 estão no Supabase de teste.**
   - **9 dependem de migration pendente:** 6 de Contas Bancárias (`20261109`) e 3 da recorrência no cartão (`20261106`).
3. **Financiamentos, Consórcios, Patrimônio, Mobilidade, Documentos Fiscais/Empresa e Dashboard são só consulta (F2)**, e as funções deles estão **todas em migrations pendentes**. O bloqueio da escrita é o **escritor único**: o Flask grava esses módulos sem consultar `gerador_recorrencia` (§ Escritor único).
4. **Supabase de teste:** 17 migrations aplicadas (até `20261105090000`) e **12 pendentes** (`20261106` a `20261118`), sem divergência de histórico.
5. **Principais riscos (P0):**
   - **Dados sensíveis de cartão em texto no banco real do Flask.** No `gastos.db`, 2 de 2 cartões têm número completo, CVV e validade preenchidos (`config_agregador`). No Supabase de teste: 0 de 3. O novo aplicativo recusa os três campos no navegador e no banco (`20261104`, `cartoes-adaptador.js`). O risco está na origem e em qualquer carga de dados reais.
   - **Escritor duplo assimétrico em Contas Bancárias.**
     - O novo aplicativo recusa ajuste e transferência em perfil do Flask (`exigir_pagamento_novo`).
     - O Flask aceita ajuste, transferência e edição/exclusão de movimento em **qualquer** perfil: `contas_bancarias.py` tem 8 rotas de escrita e nenhuma guarda.
     - Exposição hoje: **nenhuma em dados reais.** Pessoal (1) e Empresa (2) estão no Flask; só os fictícios 31 e 39 estão no NOVO (consulta ao Supabase de teste).
   - **Rascunho da fase 2 de Financiamentos (pagar/estornar parcela) fora do repositório,** numa pasta temporária da sessão. Pode se perder.

## B. Matriz de módulos

Ambiente:
- **L** = local (cluster descartável);
- **T** = funções aplicadas no Supabase de teste;
- **P** = tela publicada na prévia (`avaliacao`, versão `ef6c0d8`).

| Módulo | Tela | Consulta | Escrita | Integração / dependências | Testes (nesta auditoria) | Situação |
|---|---|---|---|---|---|---|
| Dashboard | original | F2 (L; `20261114` pendente) | não se aplica | lê despesas, faturas, cartões, receitas, mobilidade e documentos; D1 corrigido; D2 mantido | banco 6, E2E 1 | **F2** |
| Lançamentos | original | F2 (L; 4 leituras em `20261109`) | compras e despesas diretas: F3 (funções em T, tela fora da prévia); receitas: recusadas | Cartões, Despesas | banco 4, E2E | **F3** |
| Despesas | original | F4 | criar, editar, excluir, pagar, estornar e gerar mês: **F4**; parcela de financiamento/consórcio recusada | escritor único (pagamento/estorno) protegido nos dois lados | banco, E2E | **F4** |
| Recorrências | original | F4 | mensal/anual: **F4**; no cartão (R2): F3 (`20261106`); semanal/quinzenal: **F0** no gerador novo | Consórcios (consulta, L) | banco, E2E 6 | **F4 parcial** |
| Receitas | **própria (não é a do Flask)** | F4 | previsões, recebimento e estorno: **F4** | movimentos bancários | banco | **F4 funcional / F1 fidelidade** |
| Cartões | original | F4 | cadastro, limites, compras, parcelas futuras, pagamento e estorno de fatura: **F4** | número, CVV e validade recusados | banco, E2E | **F4** |
| Importar Cartão | original | F4 | importação CSV: **F4**; PDF/XLSX: F3 (não publicados; reconhecer recorrência depende de `20261107`) | Recorrências | banco, unit (PDF/XLSX), E2E | **F4 parcial** |
| Contas Bancárias | original | F2 (L) | CRUD, ajustes, transferências e extrato: **F3** (`20261109`) | **escritor duplo assimétrico (P0)** | banco 16, E2E | **F3** |
| Financiamentos | original | F2 (L; `20261110`) | **bloqueada** (escritor único); rascunho fora do repositório | Despesas (parcela vinculada) | banco 4, E2E 2 | **F2** |
| Consórcios (em Recorrências) | original | F2 (L; `20261116`) | **bloqueada** | Despesas, Receitas | banco 3, E2E | **F2** |
| Patrimônio | original | F2 (L; `20261112`) | bloqueada; exportações: F0 | Documentos (abrir arquivo, L) | banco 5, E2E 2 | **F2** |
| Documentos Fiscais (IRPF) | original | F2 (L; `20261113`, `20261118`) | bloqueada; envio, OCR e relatórios: **F0** | categorias IR existem em T (19) | banco 4+3, E2E 4 | **F2** |
| Documentos da Empresa | original | F2 (L; `20261113`, `20261117`) | bloqueada; ZIP e relatórios: F0 | lastro: despesas, faturas, lançamentos, movimentos | banco 3+3, E2E 1 | **F2** |
| Categorias | **própria (só leitura)** | F2 (T, P) | **F0** (o Flask tem 11 rotas de escrita: cadastro, logo, palavras-chave) | categorias sistêmicas `MOB_*` existem em T (10) | E2E moldura | **F2 / F1 fidelidade** |
| Mobilidade | original | F2 (L; `20261115`) | **bloqueada**; cenário ativo legado em arquivo: F0 | categorias `MOB_*` por código (sem ID fixo) | banco 4, E2E 2 | **F2** |
| Configurações | seções do Flask | F4 | Perfis: **F4**; Preferências, Aparência, Backup, IA, Documentos: F1 ("em migração") | — | E2E | **F4 parcial** |
| Ajuda e Manual | original | F4 | não se aplica | — | E2E moldura | **F4** |

## C. Migrations

Lista gerada dos arquivos (`supabase/migrations`) e comparada com `scripts/supabase_migrations.py status`.

| Versão | Situação | Conteúdo (análise do arquivo) | Risco / dependência |
|---|---|---|---|
| `20261021`…`20261105` (17) | **aplicadas** no teste | — | — |
| `20261106` recorrência no cartão | pendente (já commitada em `b1c1ac6`) | 5 funções novas (escrita R2), SECURITY DEFINER | escrita; MVP 1 |
| `20261107` importação + recorrência | pendente | **substitui** `analisar_importacao_cartao` (de `20261105`) | substituição de função em uso pela tela publicada |
| `20261108` gerador sem cartão | pendente | **substitui** `plano_recorrencia` (núcleo do gerador) | **reversão pronta:** `supabase/reversao/20261108090000_plano_recorrencia_anterior.sql` |
| `20261109` contas bancárias | pendente | 22 funções (6 de escrita) | escritor duplo assimétrico (§ Escritor único) |
| `20261110` financiamentos | pendente | 4 funções, leitura | — |
| `20261112` patrimônio | pendente | 10 funções, leitura | define `iso_python`, usada por `20261113`/`15`/`17` |
| `20261113` documentos fiscais | pendente | 14 funções, leitura | depende de `20261112` e `20261102` |
| `20261114` dashboard | pendente | 3 funções, leitura | — |
| `20261115` mobilidade | pendente | 21 funções, leitura | depende de `20261112` |
| `20261116` consórcios | pendente | 3 funções, leitura | — |
| `20261117` saídas sem documento | pendente | 4 funções, leitura | depende de `20261113` |
| `20261118` abrir arquivo | pendente | 1 função, leitura | depende de `20261113` |

**Verificado nas 12 pendentes:**
- nenhuma cria ou altera tabela, índice ou política;
- nenhuma modifica dados no nível superior: os `insert`/`update` contados estão dentro de corpos de função;
- todas as funções SECURITY DEFINER têm `set search_path = ''`;
- as internas têm `revoke` de `public`, `anon` e `authenticated`;
- as de tela têm `grant` só a `authenticated`.

**Ordem segura de aplicação:**
1. **Bloco MVP 1 (escrita):** `20261106`, `20261107` e `20261108`, juntas.
   - A ferramenta exige o conjunto pendente exato.
   - A reversão da 1108 já existe.
   - A 1107 não tem reversão pronta: precisa da definição anterior de `analisar_importacao_cartao`, que está em `20261105`.
2. **`20261109` (escrita):** só depois da guarda do Flask em Contas Bancárias, ou com a decisão explícita de aceitar o escritor duplo enquanto nenhum perfil real estiver no NOVO.
3. **Bloco de leitura:** `20261110`, `20261112`, `20261113`, `20261114`, `20261115`, `20261116`, `20261117` e `20261118`, nesta ordem (dependências acima). Risco operacional baixo: só criam funções.
4. A ferramenta aplica **todas as pendentes de uma vez**. Para aplicar em blocos, é preciso aplicar na ordem acima com autorizações sucessivas. Hoje o conjunto pendente inclui todas.

**Reversão das funções de leitura:** `drop function` das funções criadas (nenhum dado depende delas). Não há scripts prontos para elas.

## D. Testes (executados nesta auditoria, código atual)

| Suíte | Resultado |
|---|---|
| Unitários do `web/` | **30/30** |
| E2E local completo (cluster + PostgREST + Playwright) | **87/87** (última execução sobre o código atual, que não mudou depois dela) |
| Banco da fila (11 arquivos `test_supabase_*` da fila + `test_testes_impacto.py`) | **69/69** |
| Suíte completa `tests/` (inclui o Flask) | ver §D.1 |

**Testes obsoletos e corrigidos:**
- `test_testes_impacto.py` referia `cartoes.spec.mjs` e `fechamento.spec.mjs`, removidos em `ef6c0d8`. Corrigido nesta fila.
- Também foram removidos, sem teste que os cite: `pagamento.spec.mjs` e `web/src/js/cartoes.js`.

**Lacunas de cobertura:**
- nenhuma validação real das 12 migrations pendentes;
- nenhum teste de concorrência entre Flask e novo aplicativo em Contas Bancárias;
- nenhum teste de carga com arquivos grandes em "Abrir arquivo" (base64 pelo PostgREST).

### D.1 Suíte completa `tests/`

`venv/Scripts/python.exe -m pytest tests/ -q -p no:cacheprovider -rfE` (bancos descartáveis; `gastos.db` conferido depois: 1294336 bytes, mtime 1778600040, inalterado): **1836 passaram, 5 falharam, 20 pulados, 0 erros.**

As 5 falhas são as mesmas já registradas no P7 de `docs/DEPLOY_READY_FIN_1.md`, todas em testes do Flask, nenhuma introduzida nesta fila:

| Teste | Causa |
|---|---|
| `test_ocr_tools::test_status_sem_ferramentas_retorna_estrutura_valida` | ambiente: o Poppler está instalado nesta máquina e o teste supõe a ausência |
| `test_ocr_tools::test_poppler_ausente_retorna_aviso` | ambiente: mesma causa |
| `test_categorias_sistemicas_mobilidade::test_projecoes_veiculo_usam_categorias_sistemicas_granulares` | pré-existente (Flask) |
| `test_receitas_ux::test_cards_resumo_calculam_previsto_realizado_diferenca_confiabilidade` | pré-existente (Flask) |
| `test_veiculos_mobilidade_2b::test_suprimir_despesas_previstas_futuras` | pré-existente (Flask) |

Os testes de fidelidade novos desta fila (`test_supabase_*_leitura`, `test_supabase_arquivo_comprovante`) e `test_testes_impacto` (14/14) passaram todos.

## E. Pendências (situação comprovada)

| # | Pendência | Situação atual e evidência | Prioridade |
|---|---|---|---|
| 1 | Dados de cartão em texto no Flask | `gastos.db`: número, CVV e validade em 2 de 2 cartões; o novo aplicativo recusa; Supabase de teste vazio | **P0** |
| 2 | Escritor duplo em Contas Bancárias | `contas_bancarias.py`: 8 rotas de escrita sem guarda; o novo aplicativo grava em perfil NOVO (`20261109`) | **P0** antes de atribuir perfil real ao NOVO |
| 3 | Escritor único: Financiamentos, Consórcios, Patrimônio, IR, Mobilidade, Categorias, Recorrências (edição) | Rotas de escrita sem guarda: `financiamentos.py` 15, `consorcios.py` 4, `patrimonio.py` 9, `ir.py` 14, `veiculos.py` 15, `mobilidade_app.py` 3, `categorias.py` 12, `recorrencias.py` 5, `cartoes.py` 20, `importacao_cartao.py` 8. **Com guarda:** só `despesas.py` (pagamento/estorno e geração) e `receitas.py` (recebimento/estorno), além de jobs (faturas, débito automático). | **P0** para liberar escrita; **P1** funcional |
| 4 | Pagamento e estorno de parcela de financiamento | bloqueado (item 3); rascunho fora do repositório (scratchpad) | P1 |
| 5 | Segundo estorno de parcela (Flask) | defeito do Flask, aberto (`estornar_pagamento_parcela` procura estorno pela parcela) | P2 |
| 6 | Estorno de parcela pela tela de Despesas não reabre a parcela (Flask) | aberto | P1 (integridade do saldo devedor) |
| 7 | Consórcios | consulta F2 (L); escrita bloqueada | P1 |
| 8 | Recorrências semanais/quinzenais | o gerador novo só gera mensal e anual (`recorrencias-adaptador.js`, cabeçalho) | P1 |
| 9 | Recorrência no cartão (R2) | implementada (F3), depende de `20261106` | P1 (aplicar) |
| 10 | Gerador de recorrências | `gerar_mes` aplicado; correção R4 em `20261108` pendente, com reversão | P1 (aplicar) |
| 11 | Importação PDF/XLSX | implementada (F3); não publicada | P2 |
| 12 | Documentos Fiscais: envio, OCR e "A partir de documento" | F0 | P1 (envio), P2 (OCR) |
| 13 | Documentos da Empresa | consulta F2 (L) | P2 (escrita) |
| 14 | Relatórios PDF/Excel/ZIP (IR, saídas, Patrimônio, Financiamentos) | F0; os botões avisam "continua no sistema atual" | P2 |
| 15 | Cenário ativo da Mobilidade | Flask: arquivo global em `DATA_DIR`, sem perfil; F0 | P2 (decidir armazenamento) |
| 16 | Categorias `MOB_*` | **resolvida em T:** as 10 existem com `codigo_sistema` | — |
| 17 | D-MOB1 (salvar financiamento do veículo sempre falha no Flask) | aberto no Flask (`upsert_financiamento`, linhas 181/211) | P2 |
| 18 | D-DOC1 (resumo/lista do perfil Empresa quebram no Flask) | corrigido no novo; aberto no Flask | P2 |
| 19 | Dashboard: receita prevista = recebido + orçado (D2) | mantido igual ao Flask; decisão do titular | P2 |
| 20 | Dashboard: isolamento (D1) | corrigido no novo (`dashboard_resumo_tela` filtra o perfil); aberto no Flask | — (P0 só no Flask) |
| 21 | Leituras que criam dados (Flask) | o novo aplicativo não grava em leitura; categorias IR (19) e `MOB_*` (10) já existem em T | — |
| 22 | OCR | F0 | P2 |
| 23 | Tela original de Receitas | ausente (tela própria de 31 linhas) | **P1** |
| 24 | Escrita de Categorias (cadastro, logo, palavras-chave) | F0 (o Flask tem 12 rotas de escrita) | **P1** |
| 25 | Configurações (preferências, aparência, backup, IA) | F1 | P2 |
| 26 | Rascunho da fase 2 de Financiamentos fora do repositório | risco de perda | P1 (guardar em `supabase/rascunhos/`, fora de `migrations`) |
| 27 | Commits da fila | 80 arquivos sem commit, misturando MVPs em 6 arquivos compartilhados | P1 (risco de perda e de revisão) |

## F. Plano de refinamento (contratos pequenos, em ordem de dependência)

1. **FIN-SEG-CARTAO-1 (P0, sem dependência):** decidir o destino dos dados de cartão do `gastos.db`.
   - Proposta: nunca migrar número, CVV e validade; manter só os 4 finais.
   - Diagnóstico somente leitura antes de qualquer limpeza, que precisa de autorização própria.
2. **FIN-COMMITS-FILA-1 (P1):** commits por MVP, conforme `docs/FIN_FIDELIDADE_CONSOLIDACAO_1.md` §5.1.
   - Guardar o rascunho da fase 2 em `supabase/rascunhos/`, fora de `migrations`.
3. **FIN-ESCRITOR-UNICO-2 (P0 → libera P1):** guarda mínima no Flask, no padrão já usado em `despesas.py` (`flask_pode_gerar` → 409 "feito pelo novo aplicativo"). Por bloco:
   - a) Contas Bancárias (ajuste, transferência, movimento);
   - b) parcelas de financiamento e consórcio (`_paga_pelo_novo_aplicativo` e as rotas de `financiamentos.py`);
   - c) depois, cadastros dos demais módulos.
   - Testes de concorrência Flask × novo aplicativo, como no FIN-PAGAMENTO-TRAVA-1.
4. **FIN-APLICAR-TESTE-1:** aplicar as 12 migrations no Supabase de teste, na ordem do §C.
   - Antes, criar a reversão da 1107.
   - Validação real com perfil temporário e limpeza por identidade.
   - Publicação na prévia.
5. **FIN-FIDELIDADE-RECEITAS-2 (P1):** tela original de Receitas do Flask sobre as funções já existentes (`criar/editar/excluir/receber/estornar`, já em F4).
6. **FIN-FIDELIDADE-CATEGORIAS-1 (P1):** tela original e escrita de Categorias, com logo (armazenamento) e palavras-chave.
7. **FIN-RECORRENCIA-SEMANAL-1 (P1):** frequências semanal e quinzenal no gerador novo.
8. **FIN-CONTRATOS-2 (P1, depende do 3b):**
   - pagamento e estorno de parcela de financiamento e consórcio pelo fluxo de Despesas (o caminho real do Flask);
   - estorno reabre a parcela (corrige o achado 6);
   - identidade do estorno pelo movimento original (corrige o achado 5).
9. **FIN-DOCUMENTOS-2 (P1/P2):** envio de arquivo (armazenamento), "A partir de documento" e decisão sobre OCR.
10. **FIN-RELATORIOS-1 (P2):** Excel no navegador (já há leitor XLSX; falta o escritor), PDF e ZIP.
11. **FIN-MOBILIDADE-2 (P2):** escrita sob escritor único e decisão sobre o cenário ativo.
12. **FIN-CONFIG-2 (P2):** preferências, aparência, backup e IA.

## G. Prontidão para homologação

**Podem ser homologados agora pelo titular, na prévia publicada (tela e funções no Supabase de teste):**
- Despesas, inclusive pagamento e estorno;
- Recorrências mensais/anuais;
- Cartões;
- Importar Cartão (CSV);
- Receitas: funcional, mas a tela não é a do Flask;
- Categorias: consulta;
- Configurações: Perfis;
- Ajuda.

**Prontos para homologação de consulta, depois de aplicar as migrations e publicar (FIN-APLICAR-TESTE-1):**
- Dashboard, Lançamentos, Contas Bancárias (consulta);
- Financiamentos, Consórcios, Patrimônio, Mobilidade;
- Documentos Fiscais e da Empresa.

**Não prontos:**
- escrita de Contas Bancárias (escritor duplo);
- escrita dos módulos de contrato, patrimônio, documentos e mobilidade;
- Categorias (escrita);
- tela original de Receitas;
- relatórios, envio de arquivos e OCR.

## Respostas objetivas

1. **Quanto foi migrado (critérios verificáveis):**
   - telas: 15 de 15 módulos do menu abrem no novo aplicativo, 12 com a tela original do Flask;
   - escrita: 46 funções de escrita auditadas, 37 no Supabase de teste;
   - blueprints de escrita do Flask com equivalente de escrita no novo aplicativo: **7 de 20**, alguns parciais (despesas, receitas, recorrências, cartões, importação de cartão, contas bancárias, perfis);
   - os outros 13 não têm escrita no novo aplicativo: financiamentos, consórcios, patrimônio, IR, veículos, mobilidade por app, categorias, despesas previstas, seguros de financiamento, indexadores, preferências, backup e OCR.
2. **Só consulta:** Dashboard, Financiamentos, Consórcios, Patrimônio, Mobilidade, Documentos Fiscais/Empresa e Categorias.
3. **Operações financeiras que funcionam (F4):**
   - pagar e estornar despesas e faturas;
   - receber e estornar receitas;
   - compras à vista e parceladas;
   - geração mensal de recorrências.
   - Em F3: ajustes e transferências bancárias, recorrência no cartão.
4. **Dependem do escritor único:**
   - pagamento/estorno de parcelas de financiamento e consórcio;
   - toda escrita de financiamentos, consórcios, patrimônio, documentos e mobilidade;
   - fechar o lado do Flask em Contas Bancárias.
5. **Migrations pendentes:** 12, de `20261106` a `20261118`. Só 3 gravam: 1106, 1107/1108 (substituições) e 1109.
6. **Funcionalidades essenciais do Flask que faltam:**
   - pagamento de parcelas de financiamento e consórcio;
   - escrita de contratos e patrimônio;
   - Categorias (escrita);
   - recorrências semanais/quinzenais;
   - tela original de Receitas;
   - envio de documentos;
   - relatórios.
7. **Defeitos que exigem correção:**
   - dados de cartão em texto (P0);
   - escritor duplo em Contas Bancárias (P0 na transição);
   - estorno de parcela via Despesas que não reabre a parcela (Flask);
   - segundo estorno bloqueado (Flask);
   - D-MOB1, D-DOC1 e D1 (Flask);
   - D2 (decisão).
8. **Homologáveis agora:** §G, primeiro bloco.
9. **Sequência mais eficiente:** §F (1 → 2 → 3a → 4 → 5/6/7 em paralelo → 3b → 8 → 9 → 10/11/12).
10. **O que impede desativar o Flask:**
    - Os módulos de contrato, patrimônio, documentos, mobilidade e categorias ainda só gravam no Flask, sem guarda de escritor único.
    - Faltam pagamento de parcelas, recorrências semanais, envio de documentos, relatórios e backup.
    - Os perfis reais (Pessoal e Empresa) continuam atribuídos ao Flask.
    - Não há homologação do titular em nenhum módulo.
