# FIN-ESCRITOR-UNICO-CONTAS-1 — Preservação, escritor único em Contas Bancárias, D2 e preparação do lote de migrations

**Data:** 25/10/2026. **Origem:** decisões do titular sobre `docs/FIN_AUDITORIA_GERAL_1.md`.

**Critério daqui até a substituição do Flask (titular):** não é mais preciso provar que as telas mostram os dados do
Flask. É preciso provar que o novo aplicativo administra esses dados com a mesma fidelidade, sem duplicar operações,
comprometer históricos ou alterar indevidamente saldos e projeções.

## 1. Decisões do titular registradas

| Tema | Decisão |
|---|---|
| Commits por MVP | autorizados (feitos, §2) |
| Rascunho de pagamento de Financiamentos no repositório | autorizado, fora das migrations (§2) |
| Reversão da 20261107 | autorizada (feita, §6) |
| Guarda do Flask em Contas Bancárias | autorizada (feita, §3) |
| Aplicar as 12 migrations no Supabase de teste | condicionada às 6 condições do §6 |
| Validação com perfis temporários | autorizada |
| Prévia protegida | só depois da validação |
| Push e produção | **não autorizados** |
| Dados de cartão (P0) | não migrar número, validade nem CVV; o CVV nunca é guardado no novo aplicativo; **não apagar** nada do Flask agora (§5) |
| D2 do Dashboard | corrigir a duplicidade preservando previsto, recebido e diferença (§4) |
| Ordem do escritor único | Contas Bancárias → parcelas de financiamentos → parcelas de consórcios → cadastros de contratos → Patrimônio → Documentos → Mobilidade → Categorias e demais |

**Ordem de refinamento aprovada** (substitui a §F da auditoria):
1. preservação do trabalho;
2. proteção financeira (escritor único, reversões);
3. integração do ambiente de teste (migrations, testes, prévia após validação);
4. fidelidade funcional pendente (Receitas, Categorias, recorrências semanais/quinzenais);
5. operações financeiras complexas (pagamento e estorno de financiamentos e consórcios);
6. complementações (Documentos, relatórios, Mobilidade, Configurações, backup);
7. segurança e homologação final.

A segurança dos dados de cartão é acompanhada desde já (§5).

## 2. Preservação do trabalho (commits locais, sem push)

| Commit | Conteúdo |
|---|---|
| `bbf7a0a` | MVP 1, CARTOES-3: PDF da fatura, R4, testes R2 |
| `653554b` | MVP 2, MOVIMENTACOES-1: Contas Bancárias e Lançamentos |
| `89bffa2` | MVP 3, CONTRATOS-1: consulta de Financiamentos e Consórcios |
| `ea5064c` | MVP 4, PATRIMONIO-1: consulta de Patrimônio e Mobilidade |
| `ca4b173` | MVP 5, DOCUMENTOS-1: Documentos Fiscais, Empresa, abrir arquivo |
| `4efbb22` | MVP 6, CONSOLIDACAO-1: Dashboard, mapa de impacto, arquivos compartilhados |
| `e2599e9` | FIN-AUDITORIA-GERAL-1 |
| (seguinte) | rascunho de pagamento/estorno de parcela de financiamento em `supabase/rascunhos/financiamentos_pagamento/` (não é migration; o pytest não o coleta; README diz como retomar) |

- Os arquivos compartilhados entre MVPs ficaram no commit do MVP 6, como proposto em `FIN_FIDELIDADE_CONSOLIDACAO_1.md` §5.
- Os testes obsoletos (`test_testes_impacto.py`) já estavam corrigidos no commit do MVP 6.
- Arquivos pessoais não rastreados não entraram em nenhum commit.

## 3. Escritor único em Contas Bancárias (os dois lados)

**Regra:** a atribuição do perfil (`financeiro.gerador_recorrencia`) decide quem grava contas bancárias, ajustes e
transferências. É a mesma atribuição que já decidia pagamentos, recebimentos e geração.
- Perfil sem linha ou com FLASK: só o Flask grava.
- Perfil NOVO: só o novo aplicativo grava.

**Flask** (`backend/routes/contas_bancarias.py`, `_escrita_do_novo_aplicativo`):
- as 8 rotas de escrita recusam com 409 `SISTEMA_NOVO` e "Nada foi gravado" quando o perfil é NOVO: criar, editar, inativar, reativar, ajuste de saldo, editar ajuste, excluir ajuste, transferir;
- usa `flask_pode_gerar`, a verificação já usada em Despesas e Receitas: sem a configuração (SQLite, banco sem a migration), comportamento legado; erro na verificação = escrita bloqueada;
- consultas (lista, conta, extrato, conferência) continuam;
- o perfil verificado é o dono da conta ou do movimento; no cadastro e na transferência, é o perfil ativo, porque `gerar_transferencia` só aceita contas do perfil ativo.

**Banco** (migration `20261109`, ainda não aplicada):
- `criar_conta_bancaria` e `editar_conta_bancaria` (que cobre inativar e reativar) passam a exigir o escritor do perfil (`exigir_pagamento_novo`), como os ajustes e transferências já exigiam;
- **brecha corrigida:** antes o cadastro e a edição eram permitidos com o perfil ainda no Flask ("cadastro não é movimento"). Isso contrariava a diretriz de que a existência da função não libera a escrita.

**Mesma correção na `20261106`** (recorrência no cartão, ainda não aplicada): `criar_recorrencia_cartao`,
`editar_recorrencia_cartao` e `definir_situacao_recorrencia_cartao` passam a exigir o gerador do perfil
(`exigir_gerador_novo`). Antes, a edição de valor era permitida com o perfil no Flask.

**Testes:**

| Teste | O que prova |
|---|---|
| `tests/test_supabase_contas_bancarias.py::test_flask_recusa_as_8_escritas_de_contas_em_perfil_do_novo_aplicativo` | O próprio Flask, em processo real e banco descartável, tenta as 8 escritas em perfil NOVO: 8 × 409, nenhuma linha de `conta_bancaria` ou `movimento_financeiro` muda, as 3 consultas respondem 200. **Sem a guarda, o teste falha** (o Flask grava: 201), conferido |
| `…::test_flask_continua_gravando_contas_em_perfil_do_flask` | Perfil no Flask: as 8 escritas gravam como antes; o novo aplicativo recusa a edição |
| `…::test_cadastro_e_movimento_so_pelo_escritor_unico_do_perfil` | Perfil no Flask: o novo aplicativo recusa criar, editar, inativar, ajustar e transferir, e nada muda |
| `tests/test_supabase_recorrencia_cartao.py::test_perfil_gerado_pelo_flask_nao_grava_recorrencia_no_cartao` | Perfil no Flask: cadastro, edição e inativação da recorrência no cartão recusados, nada muda |
| `web/tests/e2e/contas_bancarias_tela.spec.mjs` | Pela tela: perfil no Flask recusa ajuste **e** edição do cadastro, com a mensagem "ainda são administradas pelo sistema atual (Flask). Nada foi gravado." |

**Limite desta guarda (registrado):**
- O Flask em uso local grava no `gastos.db` (SQLite), onde a verificação não existe: comportamento legado.
- Hoje Flask e novo aplicativo **não compartilham banco**. A guarda vale quando o Flask apontar para o mesmo PostgreSQL do Supabase, que é o cenário da transição.
- Até lá, um perfil NOVO no Supabase e o mesmo perfil no `gastos.db` são cópias independentes. A transição de cada perfil real precisa de um procedimento próprio (carga, conferência, atribuição), ainda não definido.

### 3.1 Escritas do novo aplicativo já aplicadas que não exigem o escritor do perfil (próxima etapa)

Funções aplicadas no Supabase de teste antes desta decisão (migrations até `20261105`) que gravam com o perfil ainda no Flask. Em geral, os cadastros eram permitidos nos dois sistemas, com controle de versão. Pela nova diretriz, isso precisa de uma migration nova e da guarda correspondente no Flask, na ordem aprovada.

| Área | Funções (só gestão e versão; algumas recusam campos específicos) |
|---|---|
| Despesas e recorrências | `criar_despesa`, `editar_despesa` (dia e frequência já exigem o gerador), `excluir_despesa`, `inativar_recorrencia`, `editar_recorrencia`, `reativar_recorrencia`, `definir_meio_pagamento_recorrencia` |
| Receitas (previsões) | `criar_receita`, `editar_receita`, `excluir_receita`, `editar_fonte_receita`, `inativar_fonte_receita` |
| Cartões e compras | `criar_cartao`, `editar_cartao`, `inativar_cartao`, `vincular/atualizar/desativar_limite_cartao`, `editar_lancamento_cartao`, `editar/cancelar_parcelas_futuras`, `criar_compra`, `excluir_compra`, `importar_fatura_cartao`, `dispensar_aviso_recorrencia` |

**Já exigem o escritor:**
- `gerar_mes`;
- `pagar_fatura` e `estornar_pagamento_fatura`;
- `pagar_despesa` e `estornar_pagamento_despesa`;
- `receber_receita` e `estornar_recebimento`;
- ajustes e transferências bancárias;
- e, com as correções acima, o cadastro de contas e a recorrência no cartão.

**Exposição real hoje:** nenhuma, porque o Supabase de teste só tem perfis fictícios e o Flask não grava nele. Mas não é seguro atribuir um perfil real ao novo aplicativo antes de fechar esta lista.

## 4. D2 do Dashboard: receita sem duplicidade

**Defeito do Flask:**
- `_receitas_previstas` soma recebido + orçado do mês;
- uma previsão de R$ 10.000 recebida por R$ 9.500 aparece como R$ 19.500;
- isso infla o fluxo projetado e reduz o percentual de orçamento das despesas.

**Correção** (`20261114`, ainda não aplicada; nenhum registro alterado):

| Indicador | Regra |
|---|---|
| Receitas previstas | orçado do mês + recebimentos sem previsão (`orcamento_id` nulo): a mesma previsão da tela de Receitas do Flask (`ReceitaService.get_resumo_receitas_por_mes`) |
| Receitas recebidas (novo) | tudo o que foi recebido no mês: a realização |
| Diferença da execução (nova) | recebido − previsto (no exemplo: −R$ 500) |

- O fluxo, o saldo projetado e o percentual de orçamento usam a previsão corrigida.
- A tela mostra o recebido e a diferença logo abaixo de "Receitas previstas". A diferença negativa aparece em vermelho.
- Arquivos: `web/src/paginas/dashboard.html`, `web/src/css/dashboard-adaptacoes.css`, `web/src/js/dashboard-adaptador.js`.
- O JS do Flask não muda.

**Testes:**
- `tests/test_supabase_dashboard_leitura.py`, 7 testes.
  - O próprio Flask responde duas vezes: original e com `_receitas_previstas` trocada pela previsão da tela de Receitas. A comparação campo a campo é com a segunda resposta.
  - O teste novo cria previsão de 10.000 recebida por 9.500 e um recebimento sem previsão de 300. Confere previsto, recebido e diferença.
  - Também mostra que o Flask original soma de novo os 9.500.
- `web/tests/e2e/dashboard_tela.spec.mjs`: os três valores na tela iguais à função.

**Observação, não alterada:**
- Na projeção simplificada do Flask, o saldo inicial é o saldo atual das contas, que já inclui o que foi recebido e pago no mês.
- Receitas e despesas do mês entram inteiras, então o que já foi realizado pesa duas vezes no saldo projetado, dos dois lados.
- É outra regra (D3), para decisão do titular. Não faz parte do D2.

## 5. Dados de cartão (P0): situação e inventário de cópias

- **Novo aplicativo:**
  - o cadastro e a edição de cartão recusam número, validade e código de segurança (`20261028`, `20261104`);
  - a leitura mostra só os 4 últimos dígitos;
  - nenhuma função grava esses campos.
- **Supabase de teste** (consulta só de leitura, 25/10/2026): `config_agregador` com 0 CVV, 0 número completo e 0 validade.
- **Nenhum script do repositório** copia dados do `gastos.db` para o Supabase.
  - A carga dos perfis reais, quando existir, deve copiar só instituição, bandeira e 4 últimos dígitos, e descartar CVV e validade.
  - Esta regra vale desde já para qualquer carga.
- **Cópias que podem conter os dados**, só listadas por nome (nenhuma aberta, nada apagado), a considerar no saneamento:
  - `data/gastos.db`, o original preservado (1294336 bytes, mtime 1778600040, inalterado);
  - `data/gastos-DESKTOP-3HHKJTN.db` e `data/backup/gastos-DESKTOP-3HHKJTN.db`;
  - `data/backups/`: 6 cópias `gastos_antes_*.db`, de 11–12/05/2026;
  - `data/tmp/`: `gastos_regularizacao_teste.db` e `gastos_teste_migration.db`;
  - `data/backups/postgres/controle_financeiro_full.dump`, de 26/05/2026, e o banco PostgreSQL local `controle_financeiro` de onde ele veio;
  - **sincronização do OneDrive:** a pasta do projeto fica no OneDrive, então todas as cópias acima também estão na nuvem e no histórico de versões do OneDrive;
  - **git:** nenhum arquivo de banco no histórico (`data/` ignorado; conferido com `git log --all`).
- O procedimento de saneamento ainda não foi feito e precisa de decisão: cópias, ordem, verificação, OneDrive.

## 6. Condições para a aplicação conjunta no Supabase de teste

A ferramenta (`scripts/supabase_migrations.py aplicar`) só aplica se a lista autorizada for **exatamente** a lista de
pendentes. O `supabase db push` aplica cada arquivo na sua transação: uma falha no meio deixa os anteriores aplicados.

| # | Condição | Situação e evidência |
|---|---|---|
| 1 | Guarda do Flask em Contas Bancárias concluída e testada | feita (§3) |
| 2 | Reversão da função substituída em 20261107 | `supabase/reversao/20261107090000_analisar_importacao_cartao_anterior.sql`; teste de ida e volta em `test_supabase_recorrencia_cartao.py` |
| 3 | Conferir as 12 migrations e dependências | ver "Conferência das 12" abaixo |
| 4 | Perfis reais continuam no Flask | Supabase de teste (só leitura): Pessoal (1) e Empresa (2) sem atribuição (= FLASK); só os fictícios 31 e 39 são NOVO |
| 5 | Nenhuma escrita liberada só porque a função passou a existir | as únicas migrations do lote com escrita (1106, 1109) exigem o escritor do perfil em **todas** as funções que gravam (§3); as outras 10 só leem |
| 6 | Recuperação do ambiente de teste | ver "Recuperação" abaixo |

**Conferência das 12:**
- só `create function`, `create or replace function` (2), `grant` e `revoke`: nenhuma tabela, política, tipo ou dado;
- nenhum `grant` para `anon` ou `public`;
- funções de leitura todas `stable`, sem `insert`, `update` ou `delete`;
- cada migration só usa funções de versões anteriores (1113 e 1115 → 1112; 1117 e 1118 → 1113);
- colunas e tipos das 43 tabelas usadas: iguais entre o cluster de testes e o Supabase de teste;
- nenhuma das 87 funções novas existe no remoto;
- as 2 substituídas (`plano_recorrencia`, `analisar_importacao_cartao`) estão no remoto exatamente na definição que a reversão restaura (a segunda difere só no fim de linha, CRLF).

**Recuperação:**
- `supabase/reversao/lote_20261106_20261118.sql`, numa transação, desfaz o lote inteiro e também serve para aplicação parcial (idempotente):
  - remove as 87 funções novas;
  - devolve as 2 substituídas, com os mesmos privilégios;
  - tira as 12 versões do histórico;
- `tests/test_supabase_reversao_lote.py` aplica o lote e a reversão num cluster descartável:
  - as funções do `financeiro` voltam exatamente ao estado anterior (corpo, privilégios, `security definer`, `search_path`);
  - nada mais muda;
  - repetir a reversão não muda nada;
  - reaplicar o lote volta ao estado com o lote;
- retrato do esquema remoto antes do lote: dump só de estrutura do `financeiro` (144 funções), guardado fora do repositório, no scratchpad da sessão.

## 7. Testes desta etapa (antes da aplicação)

| Conjunto | Resultado |
|---|---|
| Banco (`tests/test_supabase_*.py`, inclusive reversões e guardas) + Flask ligado a contas, movimentos, estornos, saldos, pagamentos e Dashboard (22 arquivos) | **870 passaram, 1 falhou, 18 pulados** |
| E2E local completo (cluster descartável + PostgREST + Playwright) | **87 passaram**, 0 falhas |
| Unitários do `web/` | **30 passaram** |

**A falha:**
- `test_contexto_financeiro_escopo.py::test_conta_cartao_receita_despesa_e_recorrencia_sao_isolados_por_perfil`: `POST /api/cartoes` do Flask responde 500 (`ObjectDeletedError` em `ItemDespesa.to_dict` logo após o commit, `routes/cartoes.py` linha 188).
- **Não vem desta etapa:** falha igual com `backend/routes/contas_bancarias.py` original (conferido trocando o arquivo).
- Passou na suíte completa da auditoria, às 19h40 de 25/10. Voltou a falhar depois da virada do dia em UTC (26/10).
- Registrada como pendência do Flask (P2) para investigar. Não afeta o novo aplicativo.

## 8. Aplicação no Supabase de teste (26/10/2026, 00:5x UTC)

**Antes:**
- commits `b518308`, `679cac3` e `7d48290`; árvore limpa, fora os arquivos pessoais;
- `status`: 12 pendentes, sem divergência;
- `simular`: exatamente as 12;
- impressão digital do banco: 64 tabelas, 211 linhas, 144 funções do `financeiro`, 17 migrations.

**Aplicação:**
- `scripts/supabase_migrations.py aplicar --versoes` com as 12 versões;
- as 12 aplicadas em ordem, **sem falha intermediária**: nada a avaliar, a reversão não foi usada.

**Depois** (impressão digital, só leitura):

| Item | Resultado |
|---|---|
| Conteúdo das 64 tabelas | **idêntico** ao de antes (nenhum dado alterado) |
| Funções | +87 novas, 0 removidas, só as 2 substituídas previstas alteradas (`analisar_importacao_cartao`, `plano_recorrencia`) |
| Migrations | 29/29 |
| `gastos.db` | inalterado (1294336 bytes, mtime 1778600040) |

## 9. Validação real (perfil temporário, dados fictícios)

**Roteiro:** `lote_real.py`, no scratchpad da sessão, por etapas:
1. build;
2. criar;
3. api;
4. complemento;
5. ui;
6. limpar (simulação, depois confirmação);
7. conferir.

**Perfil:**
- "Validacao Lote 1106-1118 (e2e-real)", criado **pelo aplicativo** (`criar_perfil`, usuário A), gerador NOVO pela criação;
- mais o vínculo LEITOR do usuário B;
- nenhuma gravação nos perfis 1, 2, 31 e 39.

**Build:**
- 16 páginas;
- só a chave publicável;
- nenhum segredo, conexão de banco ou endereço do Flask;
- `/api/` só nas rotas locais da ponte e nos adaptadores, por nome.

| Bloco | Resultado |
|---|---|
| Contas Bancárias pela Data API real: criar (reenvio com a mesma chave não duplica), ajuste pelo saldo desejado, editar e excluir ajuste, transferência (reenvio: um par só), extrato, conferência, editar cadastro | aprovado; saldos 900/250 pelos movimentos |
| Escritor único: perfil temporário trocado para FLASK. Criar, inativar, ajustar e transferir pelo novo aplicativo | 4 × recusa `SISTEMA_FLASK`; contas, saldos e situação idênticos antes e depois; perfil devolvido ao NOVO |
| Quem só lê (B) | lê; criar e ajustar recusados (403); não lê perfil alheio (31: 403) |
| Anônimo | 401 |
| D2: previsão de 1.000, recebimento parcial de 950 | Dashboard: previsto 1.000, recebido 950, diferença −50 (não 1.950) |
| As 41 leituras novas do lote, no perfil temporário | 39 respondem 200, ou a recusa de negócio do Flask para um id inexistente. As 2 do perfil Empresa recusam em perfil pessoal ("disponível apenas no perfil Empresa", como no Flask); com o perfil temporário como Empresa (`atualizar_perfil`), taxonomia, resumo e saídas sem documento respondem 200 |
| Telas, com o `dist` real e a CSP real: Contas Bancárias, Lançamentos, Financiamentos, Patrimônio, Documentos Fiscais, Dashboard, Mobilidade, Recorrências, Despesas, Cartões, Importar Cartão e Receitas, no perfil temporário | aprovado: nenhum erro de console, JS ou CSP e nenhuma requisição a `/api/` (na primeira rodada, um "Failed to fetch" de requisição interrompida pela troca de perfil; esperando a rede ociosa, nada) |

**Limpeza por identidade:**
- conferências: perfil único com o nome do teste e a criação pelo aplicativo no histórico, só os vínculos do teste, só contas e fonte com os nomes do teste, nenhum movimento de outro perfil;
- simulação, depois confirmação;
- **impressão digital final idêntica à de logo após a aplicação**: 64 tabelas, funções e migrations iguais.

**Ressalva:** a validação percorreu as telas e as operações pela Data API. A homologação pelo navegador continua com o titular.

## 10. Prévia protegida

| Item | Valor |
|---|---|
| Envio | `npx wrangler pages deploy dist --project-name controle-financeiro --branch avaliacao` (o mesmo `dist` validado, impressão `215e6dace12c`, 149 arquivos), versão `7d48290` |
| Endereço desta versão | https://feaa6454.controle-financeiro-jah.pages.dev |
| Prévia | https://avaliacao.controle-financeiro-jah.pages.dev |
| Access, antes e depois | 302 para o login do Access (prévia, versão, páginas internas, `config.js`) |
| Endereço principal | continua 404 |
| Push e produção | não feitos |

## 11. Próxima análise (titular)

1. **D3, prioridade alta**, depois da prévia. A projeção do Dashboard parte do saldo atual, que já contém o que foi recebido e pago no mês, e soma de novo receitas e despesas do mês inteiras.
   - Exemplo do titular: 5.000 + 3.000 − 1.000 = 7.000 atuais; somar de novo leva a 9.000.
   - **Não corrigir por suposição:** reconstruir como o Flask calcula as projeções (obrigações e receitas ainda não realizadas) antes de propor a regra.
2. **Escrita de financiamentos e consórcios**, em especial pagamento e estorno de parcelas, pela ordem do escritor único: guarda no Flask, depois o rascunho de `supabase/rascunhos/`.
3. **Cartões:** sem migrar CVV, validade nem número completo; nada excluído; saneamento (cópias, backups, OneDrive e histórico de versões) em procedimento próprio, com autorização específica.
