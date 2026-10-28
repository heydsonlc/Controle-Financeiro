# FIN-PRE-PRODUCAO-1 — Acabamento funcional, ensaio da carga e preparação da migração definitiva

Data: 28/10/2026.

**Situação:**
- Concluído localmente.
- Nada remoto foi alterado:
  - sem push e sem publicação;
  - nenhuma migration aplicada no Supabase;
  - nenhuma migração de perfil real.
- **O `gastos.db` não foi usado como origem e ficou intacto.** O md5 continua `bf7c7d3a12030bf18826cacc1f46293e`.

**Origem definida pelo titular:** o PostgreSQL local `controle_financeiro_dev`, lido só em modo de leitura.

## 1. Estado do projeto e bancos (Etapa 1)

| Item | Situação |
|---|---|
| Branch | `main` |
| Commits locais | 63 à frente do GitHub (`origin/main` = `9a50410`), incluindo os 6 deste contrato; sem push |
| Alterações preexistentes | Só arquivos não rastreados (PDFs, imagens e scripts locais), preservados. Os PDFs pessoais e o script com credenciais agora estão no `.gitignore` |
| Migrations do Supabase | 42 no repositório; **37 aplicadas no projeto remoto** (até `20261126090000`) |
| Migrations pendentes | 5, todas com reversão e ensaio (§6): `20261127` (Mobilidade), `20261128` (Documentos), `20261129` (Indexadores), `20261130` (Documentos na tela) e `20261201` (Preferências) |
| Supabase de produção | **Não existe projeto separado.** O único projeto do aplicativo é o **Controle-Financeiro** (`fzjmge…`, us-east-2, PostgreSQL 17.6), usado até hoje como "teste", com dados fictícios. Os perfis Pessoal (1) e Empresa (2) estão reservados ao titular e vazios. É uma decisão do titular (§10) |
| Origem | `controle_financeiro_dev`: 4 perfis; todos os dados no perfil 1; o 2 está vazio; o 3 ("Pessoal") e o 4 estão vazios. Alembic `5c91e95eb05d` |
| Dependência nova | Nenhuma no projeto. O ensaio em PostgreSQL 17 usou os binários oficiais 17.6 (EDB), baixados só para teste, fora do repositório |

## 2. Mapeamento da carga (1.3)

**Ferramenta:** `scripts/carga_supabase.py`. **Mapa:** `docs/carga/mapa_controle_financeiro_dev.json`.

| Entidade | Origem (tabelas do Flask) | Destino | Transformação |
|---|---|---|---|
| Usuários | `usuario` (login do Flask) | **não vai**: o login é o Auth do Supabase | O titular entra pelo id do Auth (`titular_user_id`) |
| Perfis | `perfil_financeiro` | Perfil existente e vazio (`destino_id`) ou criado | 1 → Pessoal; 2 → Empresa; 3 e 4, vazios, ignorados. Acesso TITULAR com `pode_gerir` |
| Contas bancárias e movimentos | `conta_bancaria`, `movimento_financeiro` | iguais | Ids novos; o estorno (`movimento_original_id`) é gravado em duas etapas |
| Receitas e despesas | `item_receita`, `receita_orcamento`, `receita_realizada`, `item_despesa`, `conta` | iguais | `item_despesa.origem_id` é traduzido conforme `origem_tipo` |
| Recorrências | `item_despesa` (recorrente) | iguais | — |
| Cartões e faturas | `item_despesa` (Agregador), `config_agregador`, `lancamento_agregado`, `categoria_cartao*`, `cartao_categoria_limite` | iguais | **Número só com o final ("•••• 1234"); CVV e validade não vão.** `compra_id` (identificador da compra) é copiado como está |
| Financiamentos e consórcios | `financiamento`, `financiamento_parcela`, `financiamento_seguro_faixa_mip`, `contrato_consorcio` | iguais | O ciclo conta ↔ parcela é gravado em duas etapas |
| Patrimônio, Mobilidade e Documentos | `bem_patrimonial`, `veiculo`, `despesa_prevista`, `ir_*` | iguais | **Vazios na origem.** Se houver dados com referência sem regra (por exemplo, ids dentro de JSON), a carga para |
| Globais | `categoria`, `ir_categoria`, `indice_tr_mensal`, `categoria_palavra_chave` | Reaproveitados por chave natural | Categoria pelo `codigo_sistema` ou pelo nome entre as globais; TR pela competência, sem nunca mudar o destino e com as divergências listadas no relatório |
| Preferências | `preferencia` (registro único) | `financeiro.preferencia_usuario` e `preferencia_perfil` | Viram as preferências do titular e de cada perfil, sem sobrescrever as que o destino já tiver |
| Sem perfil (legado) | Linhas com `perfil_financeiro_id` nulo | Continuam nulas | Como no Flask, pertencem ao perfil chamado "Pessoal". A carga exige um destino "Pessoal" |

**Conflitos de identificadores:** todos os registros ganham id novo no destino, que pode já ter dados de outros perfis. A carga para em quatro casos:
- o perfil de destino já tem dados, o que também impede uma segunda carga;
- o nome de um perfil a criar já existe no destino;
- um perfil a ignorar tem dados;
- há referência sem regra.

**Ordem da carga (ensaio real):**
1. categoria, categoria_cartao, conta_bancaria, indice_tr_mensal, ir_categoria;
2. categoria_cartao_despesa, categoria_palavra_chave;
3. item_despesa, item_receita;
4. cartao_categoria_limite, config_agregador, contrato_consorcio, financiamento;
5. lancamento_agregado, receita_orcamento, financiamento_seguro_faixa_mip, receita_realizada;
6. conta, financiamento_parcela, movimento_financeiro;
7. em segunda etapa: `conta.financiamento_parcela_id`, `item_despesa.cartao_id` e `movimento_financeiro.movimento_original_id`.

## 3. Acabamento funcional (Etapa 2)

### 3.1 Indexadores: TR mensal (commit `ea07cec`)

**Migration `20261129090000`:** reproduz o `IndiceTRService` do Flask:
- consulta por ano ou intervalo, cadastro, edição, importação por texto e competências faltantes;
- mesmas validações e mensagens;
- valor arredondado em 8 casas;
- a **TR já usada em parcela SAC/TR não muda**.

**Acesso:** a TR é única para todos os perfis, como no Flask:
- consultar exige um perfil autorizado;
- gravar exige gerir um perfil ativo;
- toda gravação é auditada em `financeiro.indice_tr_historico`;
- cadastro e importação são idempotentes.

**Tela:**
- a original do Flask, seção TR, sob Financiamentos (no Flask ficava fora do menu), com atalho na tela de Financiamentos;
- a seção genérica "IPCA/IGP-M" do Flask não foi trazida: não entra em nenhum cálculo e não tem dados.

**Testes:** fidelidade com o Flask (respostas e linhas), acesso, idempotência, auditoria, motor lendo a TR, privilégios, reversão e E2E.

### 3.2 Documentos (commit `69496bb`)

**Migration `20261130090000`:** quatro leituras novas, iguais ao Flask no teste de fidelidade:
- entidades vinculáveis;
- vínculos ativos;
- resumo de lastro;
- sugestão financeira, que classifica pela categoria do documento ou por palavra-chave e preenche categoria de IR, avisos e opções.

**Regra do titular: um documento pode ser vinculado a vários bens.**
- A recusa foi removida de `criar_vinculo_documento`, `vincular_documento_ao_bem`, `criar_bem_de_documento` e da lista de vinculáveis do Patrimônio.
- A rota genérica do Flask já permitia; a tela de Patrimônio do Flask continua recusando (o Flask não foi alterado).
- Um bem continua com um único documento ativo.
- A reversão recusa se a regra nova já estiver em uso.

**Tela:**
- `js/documento-financeiro.js` é comum a Documentos, Despesas e Lançamentos e atende "Gerar financeiro" e "A partir de documento" sem duplicar;
- **acréscimo ao Flask:** o modal "Vincular documento" lista os vínculos ativos com "Desvincular" (o vínculo fica inativo e o histórico é preservado);
- a ponte da CSP passou a aceitar métodos com caminho que estejam na lista do build (`window.IRDoc.*`). Sem isso, os botões "Revisar" e "Vincular" das linhas não funcionavam;
- E2E dos botões com um terceiro usuário fictício, C, titular de uma Empresa já no novo aplicativo.

### 3.3 Cartões e segurança (commit `d13592d`)

**Flask:**
- **número mascarado** em toda resposta da API;
- **consulta do CVV desativada** (410, com ou sem senha mestre);
- **cadastro e edição com CVV recusados**;
- o número mascarado devolvido pela tela nunca substitui o guardado;
- **os valores antigos guardados não mudam**;
- campo CVV desativado no formulário.

**Carga:** CVV e validade não vão, e o número vai só com o final (§2), conferido no ensaio: 2 cartões, 0 com CVV, 0 com validade e 0 com número completo.

**Bases e backups antigos:** intactos, como manda o contrato.

**Git:**
- `.claude/settings.local.json` saiu do rastreamento e continua na máquina;
- o `.gitignore` protege os PDFs pessoais da raiz e de `frontend/static/img`, além de `redefinir_senha_db.ps1`, que tem credencial e não foi exibido.
- **Atenção:** quando outra cópia do repositório, como a do notebook, receber esse commit, o Git apagará o `settings.local.json` dela. É preciso copiá-lo antes.

### 3.4 Preferências (commit `510f02c`)

**Migration `20261201090000`:**

| Escopo | Campos | Quem altera |
|---|---|---|
| Perfil (financeiras e operacionais) | renda, mês de início do planejamento, dia de fechamento, competência automática, aviso de despesa vencida, vínculo do pagamento de cartão, início e corte da fatura, lançamentos agrupados, orçamento por categoria, classificação automática, correção de categorias, parcelas recorrentes | Quem gere o perfil |
| Usuário (interface) | nome, tema, cor, ícones, abreviar valores, confirmação de exclusões, gráficos e painéis do Dashboard, modo inteligente, sugestões de economia | O próprio usuário, valendo em todos os seus perfis |

**Comportamento:**
- os padrões são iguais aos do Flask, conferidos no teste;
- a gravação valida tipos e faixas e é atômica;
- a carga copia o registro único do Flask, preservando as configurações existentes;
- no Flask nenhuma preferência muda comportamento, o que continua igual;
- `backup_automatico` não foi trazido, porque o novo aplicativo usa o backup do banco.

**Tela:** Configurações recebeu os formulários do Flask, com o escopo marcado em cada campo e os campos do perfil bloqueados para quem só lê o perfil.

### 3.5 Mobilidade

Sem mudança. O financiamento do veículo continua **só projetivo** (`salvar_financiamento_veiculo`, 20261127), como no Flask, e as regras de veículos não foram alteradas.

## 4. Ensaio da carga (3.1, commit `1966e48`)

**Ensaio repetível:** `scripts/ensaio_carga.py`:
1. cria um PostgreSQL descartável com o esquema do destino (shim do Supabase, tabelas do Flask e as 42 migrations);
2. cria o titular fictício com Pessoal e Empresa vazios;
3. carrega a partir da origem real, só leitura;
4. confere linha a linha;
5. tenta uma segunda carga, que deve ser recusada;
6. destrói o banco.

O relatório só tem contagens.

| Resultado | Destino descartável em PostgreSQL 18.0 | Destino descartável em **PostgreSQL 17.6** |
|---|---|---|
| Linhas gravadas | 1.521 em 20 tabelas | 1.521 em 20 tabelas |
| Conferência com a origem | OK: todas as linhas iguais, com as referências traduzidas de volta | OK |
| Origem | inalterada (hash antes e depois) | inalterada |
| Cartões | 2: CVV 0, validade 0, número completo 0 | idem |
| Preferências | do titular e dos 2 perfis copiadas | idem |
| Segunda carga | recusada ("Pessoal" já tem dados) | recusada |
| TR divergente | nenhuma | nenhuma |

Contagens por tabela, origem = gravadas:
- 579 contas e 420 parcelas;
- 221 palavras-chave e 93 itens de despesa;
- 40 categorias, 25 TR, 24 previsões de receita, 22 compras e 22 movimentos;
- 19 categorias IR e 11 vínculos de categoria de cartão;
- 9 recebimentos, 8 faixas MIP e 7 consórcios;
- 6 categorias de cartão e 6 limites;
- 4 fontes de receita, 2 contas bancárias, 2 configurações de cartão e 1 financiamento.

**Teste automatizado** (`tests/test_carga_supabase.py`): dois clusters descartáveis com dados fictícios. Cobre:
- ensaio sem gravar;
- fidelidade, incluindo o ciclo conta ↔ parcela e o `origem_id`;
- isolamento entre usuários e os dados de outro usuário intactos;
- categoria do sistema reaproveitada;
- TR divergente reportada sem mudar o destino;
- recusas: perfil ignorado com dados, falta de "Pessoal", referência sem regra e segunda carga.

## 5. Backup e restauração (3.2)

**`scripts/backup_banco.py`** (FIN-BLOCO-B-1): `CF_PG_BIN_BACKUP` escolhe as ferramentas.

**Ensaiado em servidores PostgreSQL 17.6 descartáveis** (`tests/test_backup_banco.py`, com `CF_PG17_BIN`):

| Ferramentas | Exportar → verificar (SHA-256) → restaurar em banco vazio | Recusa sobre banco com dados |
|---|---|---|
| 17.6 (recomendado para o Supabase) | Conteúdo idêntico (md5 por tabela) | Recusada |
| 18.0 da máquina, extraindo de um 17 e restaurando noutro 17 | Conteúdo idêntico | Recusada |

Os testes em PostgreSQL 18 continuam: conteúdo idêntico, arquivo alterado recusado e conexão só por variável de ambiente.

**Procedimento para a migração definitiva** (não executado: o contrato não autoriza backup remoto):
1. **Origem:**
   - `set CF_BACKUP_ORIGEM=<DSN do controle_financeiro_dev>`;
   - `python scripts/backup_banco.py exportar --dsn-env CF_BACKUP_ORIGEM --saida <pasta cifrada fora do OneDrive>`;
   - depois `verificar`.
2. **Destino** (Supabase, antes de qualquer gravação):
   - `set CF_PG_BIN_BACKUP=<bin do PostgreSQL 17>`;
   - `set CF_BACKUP_DESTINO=<Session pooler>`;
   - `exportar` e `verificar`.
3. **Ensaio de restauração** do backup do destino num PostgreSQL 17 descartável, só com o shim: `restaurar`, que recusa banco com dados.

## 6. Migrations (3.3)

**Ensaio** (`tests/test_migracoes_pendentes_ensaio.py`): aplicar as 5 pendentes sobre o estado do remoto com dados de todos os módulos:
- não altera nenhum dado existente;
- cria só 6 tabelas novas, vazias;
- as funções novas operam sobre os dados existentes (TR, sugestão financeira, preferências);
- reverter em ordem inversa também não altera dados, e reaplicar funciona.

**Ordem de reversão:** 1201 → 1130 → 1129 → 1128 → 1127 → 1126 → 1125 → 1124 → 1123. Recusas:
- a da 1130, se um documento estiver em mais de um bem;
- a da 1201, se houver preferências gravadas;
- as já documentadas da 1125 e da 1123.

**Escritor único (teste I3):** as escritas da TR e das preferências entram como exceções documentadas:
- a TR não tem perfil, e no Flask a rota de Indexadores também fica fora da guarda;
- as preferências por perfil só existem no novo aplicativo.

## 7. Integridade

- **`gastos.db`:** md5 `bf7c7d3a…` inalterado.
- **PostgreSQL local** (8 bancos, incluindo o `controle_financeiro_dev`): contadores de escrita (`pg_stat_database`) zerados antes e depois da campanha (§9). A origem só foi lida.
- **Supabase remoto:**
  - nenhuma escrita;
  - `supabase projects list` só para identificar o projeto;
  - o diagnóstico anterior fez apenas consultas de leitura.

## 8. Procedimento da migração definitiva (insumo para o FIN-BLOCO-D-EXECUCAO-1)

1. Decisão do destino (§10), push, e aplicação das 5 migrations pendentes na ordem, com ensaio no projeto.
2. Backups da origem e do destino (§5), conferidos por SHA-256 e com restauração de ensaio.
3. Ensaio da carga no destino real, sem `--confirmar`: `CARGA_ORIGEM_DSN` e `CARGA_DESTINO_DSN` por variável de ambiente, com o `titular_user_id` real no mapa.
4. Carga com `--confirmar` (uma transação), e o relatório guardado junto dos backups.
5. Conferência pela tela, com o perfil ainda no Flask (só leitura no novo aplicativo); depois `definir_gerador_recorrencia(perfil, 'NOVO', …)` por perfil, primeiro Pessoal e depois Empresa.
6. Lançar no novo aplicativo o período de 20/08/2026 até a data da migração, ausente da origem, e conferir a TR desde 06/2026 em Indexadores.
7. **Rollback:**
   - devolver o gerador ao Flask por perfil;
   - restaurar o backup do destino **num banco novo**;
   - reverter as migrations em ordem inversa.

## 9. Regressão final (3.4)

Uma única campanha completa no fim, com o PostgreSQL 17 habilitado (`CF_PG17_BIN`) e o mesmo único desmarcado de antes (`test_verificar_ambiente::test_saida_nao_contem_valores_dos_arquivos_locais`, que lê o `.env.staging`).

| Suíte | Referência (FIN-BLOCO-C-1) | Agora |
|---|---|---|
| Python | 2.022 aprovados, 0 falhas | **2.038 aprovados e 1 falha**, 20 pulados (condicionais, como antes) |
| Unitários web | 30/30 | **30/30** |
| E2E | 93/93 | **98/98** (+5: Indexadores, 3 de Documentos e Preferências) |

**A falha:** `test_supabase_perfis_gestao::test_nenhuma_tabela_nova` contava as tabelas do schema `financeiro` com "perfil" no nome, para garantir que a gestão de perfis só usa `perfil_acesso`. A tabela nova `preferencia_perfil` entrou na conta. O teste foi corrigido para excluí-la explicitamente; nenhuma regra mudou. Reexecutado sozinho, o arquivo dá 47 aprovados e 1 pulado, já pulado antes. Com a correção, os testes Python somam **2.039 aprovados e 0 falhas**.

Os testes novos e ajustados por assunto foram rodados durante o desenvolvimento, antes de cada commit:
- Indexadores: 8;
- Documentos: 6 novos e 2 arquivos ajustados para a regra nova;
- cartões: 201 testes do Flask ligados a cartões;
- Preferências: 16;
- carga: 5;
- backup: 5, sendo 2 em PostgreSQL 17;
- migrations pendentes: 2.

**Integridade antes e depois da campanha:**
- `gastos.db` com o mesmo md5;
- contadores de escrita dos 8 bancos PostgreSQL locais idênticos (zero).

## 10. Pendências e decisões do titular

1. **Projeto de produção:** usar o projeto Controle-Financeiro atual, retirando antes os dados fictícios por identidade, ou criar um projeto novo só para produção. A carga funciona nos dois casos.
2. **Autorizações:** push dos 63 commits, aplicação das 5 migrations, backup remoto, carga real e publicação.
3. **TR de 06/2026 em diante:** cadastrar em Indexadores, com valores oficiais e nunca inventados.
4. **Período sem dados (20/08/2026 até hoje):** lançar após a carga.

**Funcionalidades ainda no Flask** (classe 2 do FIN-PRE-MIGRACAO-1, sem dados afetados):
- OCR de imagem, NFS-e e cupom fiscal;
- metadados e checklist da Empresa;
- marcar e vincular saídas sem documento;
- categorias de IR (escrita);
- relatórios de IR, de saídas sem documento e ZIP;
- exportar e importar configurações;
- editar e excluir vigência de seguro;
- seção genérica de indexadores.

## 11. Commits (locais, sem push)

| Commit | Assunto |
|---|---|
| `ea07cec` | Indexadores |
| `69496bb` | Documentos |
| `d13592d` | Cartões e segurança (com Git e arquivos sensíveis) |
| `510f02c` | Preferências |
| `1966e48` | Preparação da carga, backup e migrations |
| (este) | Documentação e encerramento (com a correção do teste de contagem de tabelas, §9) |
