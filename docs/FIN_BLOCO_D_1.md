# FIN-BLOCO-D-1 — Preparação do Supabase para produção

**Data:** 28/10/2026. **Ambiente:** computador de casa (VS Code).

**Destino definitivo:** projeto Supabase `Controle-Financeiro` (`fzjmge…`). **Origem dos dados reais:** `controle_financeiro_dev` (PostgreSQL local).

**Autorização:** diagnóstico, inventário, backup protegido, testes locais e preparação do procedimento.

**O que não foi feito:** nenhuma exclusão, migration ou carga no remoto; nenhum push; nenhuma publicação.
- No remoto houve só consultas de leitura (sessão `read only`), as listagens da CLI e GETs públicos.
- As bases locais só foram lidas.

## 1. Git e testes

| Item | Situação |
|---|---|
| Branch / HEAD inicial | `main` / `39cb5fc` |
| À frente do GitHub | 63 commits, sem push; +1 commit local deste contrato (§10) |
| `git fsck` | íntegro (só objetos soltos de operações antigas) |
| Migrations locais | 42, das quais 5 pendentes no remoto (§5) |

**Regressão Python completa** (PostgreSQL 17 habilitado, o mesmo único item desmarcado de antes):
- 2.039 aprovados, 20 pulados, 0 falhas;
- confirma a correção registrada no FIN-PRE-PRODUCAO-1.

**E2E:** não repetido (98/98). Nenhuma mudança funcional nas telas.

**Testes novos deste contrato:**
- `tests/test_limpeza_ficticios_supabase.py`: 7 testes;
- `tests/test_carga_supabase.py`: +2 testes, 7 no total;
- os 14 passam.

**Integridade local:**
- `gastos.db` com o mesmo md5;
- contadores de escrita dos 8 bancos PostgreSQL locais iguais antes e depois (zero).

## 2. Supabase: identificação e estrutura (só leitura)

| Item | Valor |
|---|---|
| Projeto | `Controle-Financeiro`, ref completo conferido (prefixo `fzjmge`), `ACTIVE_HEALTHY` |
| Região / PostgreSQL | `us-east-2` / 17.6 (17.6.1.155) |
| Conexão | Session pooler do `.env.staging`; usuário `postgres.<ref>` conferido antes de cada leitura |
| Schemas | `auth`, `extensions`, `financeiro`, `graphql`, `graphql_public`, `pgbouncer`, `public`, `realtime`, `storage`, `supabase_migrations`, `vault` |
| Tabelas | `public` 54, `financeiro` 16, `auth` 27, `storage` 8 |
| Funções `financeiro` | 362, todas `security definer` com `search_path` fixo |
| Migrations | 37 aplicadas, iguais às 37 primeiras locais. Nenhuma remota sem arquivo. Pendentes: 1127, 1128, 1129, 1130 e 1201. Alembic em `c4f7a2d91b3e` |
| RLS | ativo em todas as tabelas de `public` e `financeiro`; 2 políticas |
| Privilégios | `anon` sem nenhum. `authenticated`: SELECT em 2 tabelas do `financeiro` e EXECUTE em 162 funções |
| Storage | 0 buckets; os documentos ficam no banco |
| Auth | cadastro público desativado; só e-mail; sem autoconfirmação |
| Contas no Auth | só as 2 contas de teste (A e B), com 215 sessões e 231 refresh tokens. **O titular ainda não tem conta** |
| Tamanho | 19,1 MB (documentos: 0) |

## 3. Dados fictícios: inventário por identidade

**Procedimento:** `scripts/limpeza_ficticios_supabase.py inventario`, com a identidade declarada em `docs/carga/identidade_ficticios_supabase.json`. Cada linha precisa provar que é fictícia; não basta o nome nem a data.

**Perfis fictícios**, conferidos pelo nome, pelos acessos e pelo arquivo de estado:
- **31 "Demonstracao (ficticio)":** criado pelo `scripts/supabase_demo_preview_seed.py`. O estado em `data/demo_preview_2.json` registra o perfil, o usuário A, as categorias 47–50, as contas 74–75 e o cartão 230.
- **39 "Homologacao Cartoes (ficticio)":** criado pelo `scripts/homologacao_cartoes.py`.

Os dois têm acesso só do usuário de teste A, que é o titular deles, e o gerador é NOVO.

**A retirar: 152 linhas em 21 tabelas, e nenhuma ambígua.**

| Origem da identidade | Tabela: linhas |
|---|---|
| Perfil fictício | `lancamento_agregado` 30, `conta` 25, `operacao_cartao` 20, `item_despesa` 9, `operacao_despesa` 9, `movimento_financeiro` 7, `operacao_receita` 7, `cartao_categoria_limite` 4, `categoria_cartao` 4, `categoria_cartao_despesa` 4, `item_receita` 4, `pagamento_fatura` 4, `receita_orcamento` 4, `conta_bancaria` 3, `receita_realizada` 3, `gerador_recorrencia` 2, `gerador_recorrencia_historico` 2, `perfil_acesso` 2, `perfil_financeiro` 2 |
| Global declarado | `categoria` 4: ids 47–50, "(demonstracao)", sem perfil |
| Dependente (FK) | `config_agregador` 3: cartões dos itens 230, 251 e 252, sem número e sem CVV |

**Dependências:**
- as linhas fictícias apontam para 4 categorias de sistema preservadas, e essas categorias ficam;
- nenhuma linha preservada depende de linha fictícia;
- nenhuma linha fictícia aponta para usuário que não seja de teste.

**Por que retirar as categorias 47–50:** estão sem perfil. Pela regra herdada do Flask, registro sem perfil pertence ao "Pessoal". Se ficassem, apareceriam no Pessoal real.

**Preservadas: 96 linhas.**

| Registro | Por quê |
|---|---|
| Perfis 1 "Pessoal" e 2 "Empresa" | Recebem a carga. Hoje não têm nenhum acesso |
| `item_receita` 1, do Pessoal, inativa | **Real:** cópia da fonte 1 do `controle_financeiro_dev` (mesmo nome conferido por hash), gravada em 20/08/2026 |
| 10 categorias de sistema (`MOB_*`) | Globais da Mobilidade |
| 25 TR (05/2024 a 05/2026) e 19 categorias de IR | Globais |
| `public.usuario` (1 linha) | Login do titular no Flask, com hash de senha. Não é usado pelo novo aplicativo; ver §8 |
| `alembic_version` | Estrutura |

## 4. Backup

**Arquivo:** não criado. Não existe diretório protegido configurado para backups:
- nenhuma variável de ambiente nem pasta dedicada;
- nada documentado;
- os procedimentos anteriores deixaram `<pasta cifrada fora do OneDrive>` só como indicação.

Pelo contrato, a pendência fica registrada (§8). Sem arquivo, não há hash.

**Backup gerenciado do Supabase:**
- cópias físicas diárias (WAL-G), 8 disponíveis, de 21 a 28/10/2026; a última em 28/10 às 05:24 UTC;
- PITR desativado;
- restaurar uma cópia física substitui o projeto inteiro, então ela não serve para ensaio isolado.

**Capacidade de backup lógico:**
- `pg_dump` 17.6, compatível com o servidor 17.6;
- espaço amplo: banco de 19,1 MB, com 40 GB livres em C: e 414 GB em D:;
- `scripts/backup_banco.py` está pronto (`CF_PG_BIN_BACKUP` = binários do PostgreSQL 17).

**Teste de restauração** (`scripts/ensaio_bloco_d.py`): a cópia do projeto foi feita **por fluxo**, `pg_dump` → `pg_restore` direto num PostgreSQL 17.6 descartável.
- Não ficou nenhum arquivo, e o banco descartável foi destruído no fim.
- Ficaram de fora da cópia o hash de senha da `public.usuario` e os segredos do Auth. Os usuários entram só com o id.
- **Resultado: idêntico ao remoto.** Batem 71 tabelas e 247 linhas, o md5 de cada tabela, as sequências, as 362 funções, as políticas, o RLS, as FKs e CHECKs, os gatilhos, os privilégios por ACL e as 37 migrations.
- Duas diferenças da primeira rodada eram do ensaio, não do backup:
  - **privilégios padrão do shim local:** foram removidos antes de restaurar;
  - **forma de escrita de 3 CHECKs depois da restauração:** é a mesma regra, e a comparação passou a normalizar a forma.

**Para a exclusão real:** falta um arquivo de backup protegido, com SHA-256, antes da retirada. Hoje isso é ressalva; vira bloqueador se não for resolvido (§8).

## 5. Migrations pendentes

**Ordem:** 1127 Mobilidade → 1128 Documentos → 1129 Indexadores → 1130 Integração de Documentos → 1201 Preferências.
- Todas têm reversão em `supabase/reversao/`.
- A reversão segue a ordem inversa, com as recusas documentadas no FIN-PRE-PRODUCAO-1.

**Ensaio na cópia fiel do projeto, já sem os fictícios:**
- **Aplicação:** 6 tabelas novas e vazias, 89 funções novas ou alteradas, e **nenhum dado existente alterado**.
- **Reversão em ordem inversa:** o banco volta **exatamente** ao estado anterior em dados, funções, políticas, RLS, privilégios, restrições e gatilhos.
- **Reaplicação:** idêntica à primeira aplicação.

**Aplicação real (futura):** `scripts/supabase_migrations.py aplicar --versoes <as 5>`. É o mesmo procedimento das 37 anteriores, e só aplica se o conjunto pendente for exatamente o informado.

## 6. Carga dos dados reais

**Revisão de `scripts/carga_supabase.py`.** O ensaio sobre a estrutura real revelou **duas falhas que teriam impedido a carga definitiva.** O ensaio do FIN-PRE-PRODUCAO-1 não as pegou, porque montava o destino a partir dos models, não da estrutura real. Corrigidas:

1. **`lancamento_agregado.categoria_cartao_id` sem chave estrangeira no Supabase.**
   - O esquema veio do Alembic, que não criou essa FK; os models criam.
   - A carga recusava com "referência sem regra".
   - Agora a referência é traduzida como as demais (`REFERENCIAS_SEM_FK`).
2. **Fonte de receita real já no Pessoal.**
   - A carga recusava com "Pessoal já tem dados".
   - O mapa ganhou `preexistentes` (`{"item_receita": {"1": 1}}`): o registro é reaproveitado, não duplicado.
   - Só é aceito se for o mesmo registro, com o mesmo nome e no perfil de destino correspondente.

**Ensaio na cópia fiel, depois da retirada e das migrations,** com um titular fictício com acesso aos perfis 1 e 2:

| Conferência | Resultado |
|---|---|
| Linhas da origem | 1.521 em 20 tabelas: 1.466 gravadas e 55 reaproveitadas (10 categorias de sistema, 25 TR, 19 categorias de IR, 1 fonte) |
| Linha a linha | OK |
| Somas origem × destino | Saldos (`conta_bancaria`), contas e faturas (`conta`), movimentos, compras de cartão, receitas, financiamento e parcelas, consórcios: **todas iguais** |
| Cartões | 2 cartões: 0 CVV, 0 validade, 0 número completo |
| Preferências | do titular e dos 2 perfis copiadas |
| TR divergente | nenhuma |
| Origem | inalterada (hash antes e depois) |
| Segunda carga | recusada ("Pessoal" já tem dados) |
| Linhas preservadas | intactas |

**Mapeamento:** 1 → Pessoal (1); 2 → Empresa (2); 3 e 4 ignorados (sem registros). O `titular_user_id` real só existe depois que a conta do titular for criada no Auth (§8).

## 7. Procedimento preparado para a execução

**Arquivos:**
- `scripts/limpeza_ficticios_supabase.py`;
- `docs/carga/identidade_ficticios_supabase.json`;
- `scripts/ensaio_bloco_d.py`;
- `scripts/carga_supabase.py`;
- `docs/carga/mapa_controle_financeiro_dev.json`.

**Retirada:**
- `inventario` só lê e grava a relação das linhas a retirar.
- `retirar` roda numa transação serializable e refaz a relação, que tem de ser **igual** à salva. Só então apaga essas chaves, das dependentes para as principais, com o perfil por último.
- Conferências antes do commit:
  - quantidades;
  - md5 de cada linha preservada;
  - estrutura: migrations, políticas, funções, privilégios, RLS e usuários.
- Sem `--confirmar`, tudo é desfeito. Num projeto Supabase, o comando exige ainda `--projeto-autorizado <ref>`.
- **Ensaio:**
  - relação idêntica à do remoto;
  - o ensaio sem gravar não mudou dados nem estrutura;
  - na retirada confirmada saíram 154 linhas (as 152 mais 2 linhas de auditoria que o gatilho do gerador grava durante a própria retirada), e o banco ficou com 95 linhas e só os perfis 1 e 2.
- **Riscos:**
  - O ensaio sem gravar avança a sequência do histórico do gerador; o rollback não a desfaz. Não há efeito em dados.
  - Se alguém escrever nos perfis fictícios entre o inventário e a retirada, a retirada é recusada (relação diferente) e é preciso refazer o inventário.
  - Um conflito de transação serializable exige repetir o comando.

**Ordem proposta para o FIN-BLOCO-D-EXECUCAO-1** (cada passo só com autorização):
1. Backup protegido do projeto, com SHA-256 e restauração de ensaio.
2. `inventario` e depois `retirar --confirmar --projeto-autorizado <ref>`.
3. Push e aplicação das 5 migrations.
4. Conta do titular no Auth, por convite, e acesso TITULAR com `pode_gerir` aos perfis 1 e 2.
5. Carga: primeiro o ensaio sem `--confirmar`, depois com.
6. Conferência pela tela; passar o gerador a NOVO, perfil a perfil.
7. Publicação.

**Rollback:**
- devolver o gerador ao Flask;
- reverter as migrations em ordem inversa;
- restaurar o backup num banco novo.

## 8. Pendências e decisões do titular

**Bloqueia a retirada real:**
- **Backup:** definir um destino protegido para o arquivo (cifrado e fora do OneDrive e do Git) e autorizar o backup lógico. Alternativa: aceitar expressamente a cópia física diária do Supabase como ponto de restauração.

**Antes da carga:**
- **Conta do titular no Auth.** Hoje só existem as contas de teste.

**Contas de teste A e B:**
- As senhas apareceram na saída de uma ferramenta numa sessão anterior.
- Antes da produção, excluir as contas (painel ou Admin API, depois da retirada) ou trocar as senhas. A exclusão também derruba as 215 sessões abertas.
- O E2E real (`web/tests/e2e/run_e2e_real.py`) escreve no projeto e precisa deixar de apontar para ele.

**`public.usuario`:** guarda o hash de senha do login do titular no Flask. Decidir se fica no banco de produção.
- O novo aplicativo não usa essa tabela.
- Ela tem RLS e não é acessível por `anon`.

**Autorizações:** push, retirada, migrations, carga real e publicação.

## 9. Publicação (só verificação)

| Item | Situação |
|---|---|
| Cloudflare Pages | Projeto `controle-financeiro`, Direct Upload, sem Git |
| Prévia | `avaliacao.controle-financeiro-jah.pages.dev`, protegida pelo **Cloudflare Access**; hoje responde 302 para o login, sem conteúdo do aplicativo. Último envio há 2 dias |
| Endereço principal | Branch de produção `producao`, nunca usada. **Sem deploy (404) e fora da política do Access** |
| Domínio previsto | `financeiro.kortexbrasil.com` (documentado na época do Render). **Não configurado no Pages** |
| Variáveis públicas do frontend | `SUPABASE_URL` e `SUPABASE_PUBLISHABLE_KEY`. O `build.mjs` exige https e `<ref>.supabase.co`. Continua o mesmo projeto, então nada muda |
| Segurança | O build gera `_headers`: CSP restrita (`connect-src` só o site e o Supabase), `X-Frame-Options: DENY` e `nosniff` |
| Autenticação | Cadastro desativado, só e-mail. A Site URL e as URLs de redirecionamento do Auth não são públicas: conferir no painel antes de publicar (links de troca de senha) |
| Rollback | O Pages mantém os deploys anteriores; voltar a um deles pelo painel. Os dados voltam pelo §7 |

**Pendências da publicação:**
- definir o endereço de produção;
- estender o Access a esse endereço **antes** do primeiro deploy;
- conferir a configuração de URLs do Auth.

## 10. Commit

O commit local deste contrato reúne:
- procedimento de retirada e identidade;
- ensaio do Bloco D;
- correções da carga e mapa;
- testes;
- documentação.

Sem push.
