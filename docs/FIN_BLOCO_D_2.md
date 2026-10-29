# FIN-BLOCO-D-2 — Backup, segurança e preparação de acesso

**Data:** 28/10/2026. **Ambiente:** computador de casa (Windows 11 Home, VS Code). **Projeto:** Supabase `Controle-Financeiro` (`fzjmge…`).

**O que não foi feito:** nenhuma exclusão, migration, carga, criação de usuário, troca de credencial, push ou publicação. No remoto houve só leituras:
- sessões `read only`;
- GET público do Auth;
- comandos de leitura da CLI.

As bases locais só foram lidas: `gastos.db` com o mesmo md5 e contadores de escrita dos bancos locais iguais.

Este documento continua o `docs/FIN_BLOCO_D_1.md`.

## 1. Pré-condições

| Item | Situação |
|---|---|
| Branch / HEAD | `main` / `3602222`; árvore sem alterações rastreadas |
| Commits locais | 64, sem push; `git fsck` íntegro |
| Projeto | `fzjmge…` conferido pelo usuário do pooler antes de cada leitura |
| PostgreSQL 17 | binários 17.6 do scratchpad (`CF_PG17_BIN`); servidor remoto 17.6 |
| Regressão anterior | 2.039 aprovados, 20 pulados, 0 falhas (FIN-BLOCO-D-1) |

## 2. Local do backup: **não validado**

**Exigências:** criptografia **comprovada**, fora do OneDrive e do Git, acesso restrito, sem sincronização e sem compartilhamento.

| Verificação | Resultado |
|---|---|
| Edição do Windows | 11 Home Single Language: sem BitLocker completo; só "Criptografia do dispositivo", se o hardware suportar |
| Estado da criptografia de C: e D: | **Não comprovável sem administrador**: o WMI de cifragem e o `manage-bde` negam acesso, e o indicador do Shell volta indeterminado. A sessão não tem elevação, e nada foi elevado nem ativado |
| Espaço | C: 39 GB livres, D: 414 GB livres (o banco tem 19 MB) |
| Sincronização | Só o OneDrive (D:\OneDrive) |
| Compartilhamentos | Só os administrativos padrão (C$, D$, ADMIN$, IPC$), nenhum de usuário |
| Ferramentas de cifragem | 7-Zip ausente; EFS indisponível na edição Home |

**Conclusão:** nenhum local atende ao requisito 3. Pelo contrato, o backup não foi gerado. Também não houve teste de restauração de um backup real.

**Alternativas para o titular** (todas exigem ação ou autorização dele):
1. **Comprovar a criptografia existente.** O titular confere em Configurações → Privacidade e segurança → Criptografia do dispositivo, ou num PowerShell como administrador com `manage-bde -status`. Se D: (ou C:) estiver cifrada:
   - pasta dedicada fora do OneDrive, por exemplo `D:\BackupsSeguros\ControleFinanceiro`;
   - herança de permissões removida e acesso só do usuário.
2. **Ativar a Criptografia do dispositivo** (Home, se o hardware suportar). A chave de recuperação fica na conta Microsoft.
3. **Atualizar para o Windows 11 Pro** e usar o BitLocker.
4. **Instalar uma ferramenta de contêiner cifrado** (por exemplo VeraCrypt) ou usar um disco externo já cifrado. Exige autorização para instalar.
5. **Aceitar expressamente a cópia física diária do Supabase** como ponto de restauração. Restaurá-la substitui o projeto inteiro (§4).

## 3. Ferramenta de backup preparada (`scripts/backup_banco.py`)

A revisão mostrou que a ferramenta **não atendia** ao item 3 do contrato. Agora atende:

| Antes | Agora |
|---|---|
| `--no-privileges`: as permissões não iam no backup | Vão `GRANT` e `REVOKE` de tabelas, sequências e funções, junto com as políticas |
| Sem o histórico `supabase_migrations` | Histórico incluído quando existe |
| Só `auth.users`, sem `auth.identities` (o login por e-mail depende dela) | Contas do Auth: `users` e `identities`, com a estrutura |
| Cada `pg_dump` com seu próprio instante | **Um único snapshot exportado**, usado pelos 3 arquivos e pelo retrato do manifesto |
| Manifesto só com linhas por tabela | O manifesto também traz o retrato do banco (nenhum valor de dados, só hashes e nomes): linhas e md5 por tabela, sequências, funções, execução pelos papéis da API, políticas, RLS, restrições, gatilhos, privilégios por ACL e migrations |
| Restauração conferia só as linhas | **Homologação:** o retrato restaurado tem de ser **igual** ao do manifesto, e as contas do Auth com as mesmas linhas; senão, "Backup NÃO HOMOLOGADO" |

**Privilégios padrão do destino.** Num projeto Supabase novo, o padrão dá ALL para `anon` e `authenticated` nas tabelas novas do `public`. Como o dump não emite REVOKE para ACL igual ao padrão do PostgreSQL, as tabelas restauradas ficariam mais abertas que as do backup. Por isso:
- a restauração revoga esses padrões antes de começar;
- a homologação compara os privilégios.

**O que é restaurado e o que depende do Supabase:**
- **Restaurado:** `public`, `financeiro` e `supabase_migrations` (estrutura, dados, funções, políticas e privilégios), mais as contas `auth.users` e `auth.identities`.
  - Num projeto Supabase as contas entram só como dados.
  - Num banco de conferência sem o Auth, entram com estrutura, chaves e índices.
- **Depende do Supabase:**
  - configuração do Auth: provedores, cadastro, URLs, SMTP e MFA;
  - chaves da API;
  - demais tabelas do Auth: sessões e refresh tokens (o titular entra de novo);
  - privilégios internos da plataforma sobre o schema `auth`.

**GRANTs do esquema remoto** (só leitura, sem dados): citam apenas `anon`, `authenticated`, `service_role` e `postgres`. Esses papéis existem em qualquer projeto Supabase e no ambiente local.

**Testes** (`tests/test_backup_banco.py`, 7, todos aprovados):
- os 5 anteriores, entre eles PostgreSQL 17 com as ferramentas 17 e com as 18;
- **novo:** caminho "como o Supabase", com histórico de migrations, `auth.identities` e destino sem o Auth e com os privilégios padrão da plataforma. Resultado HOMOLOGADO, retrato idêntico e nenhum privilégio a mais para `anon`;
- **novo:** uma divergência faz a restauração ser recusada como NÃO HOMOLOGADA.

**Procedimento de backup** (para quando o local for validado):
```
set CF_PG_BIN_BACKUP=<bin do PostgreSQL 17>
set CF_BACKUP_SUPABASE=<Session pooler do projeto>   (variável de ambiente; nunca na linha de comando)
python scripts/backup_banco.py exportar --dsn-env CF_BACKUP_SUPABASE --saida <pasta validada>
python scripts/backup_banco.py verificar --manifesto <pasta>\manifesto_<data>.json
```
Registrar para o titular: SHA-256 e tamanho de cada arquivo, data, projeto e migrations, todos já no manifesto.

**Teste de recuperação:** num PostgreSQL 17 descartável com o shim, retirar a `auth.users` simplificada do shim e rodar `restaurar`. A aprovação é "HOMOLOGADO".

**Recuperação real:**
- restaurar num projeto ou banco **novo**, nunca sobre o atual;
- reconfigurar o Auth e as chaves;
- o titular entra de novo.

## 4. Backup gerenciado do Supabase

- **Cópias:** físicas diárias (WAL-G), 8 disponíveis, de 21 a 28/10/2026; PITR desativado.
- **Restauração:** só pelo painel e sobre o próprio projeto, substituindo tudo. Não serve para ensaio isolado nem para recuperar um registro.
- **Uso:** é a rede de segurança da plataforma, não o backup da migração.

## 5. Modo de simulação da retirada (dry-run): **corrigido**

**Problema:** o ensaio sem `--confirmar` executava a retirada e depois desfazia. O gatilho de auditoria do gerador consumia um número da sequência `gerador_recorrencia_historico_id_seq`, e o rollback não devolve número de sequência.

**Correção** (`scripts/limpeza_ficticios_supabase.py`):
- Sem `--confirmar`, roda `simular`: transação **somente leitura** (`read only`, repeatable read).
- **Nenhum comando de escrita é executado:** nenhum UPDATE ou DELETE, nenhum gatilho, nenhuma sequência, nenhuma auditoria, nenhum metadado.
- Faz as mesmas conferências da retirada:
  - ambiguidade;
  - relação igual à salva;
  - ordem;
  - colunas de ciclo que aceitam nulo.
- Devolve só o plano: ordem, linhas a apagar por tabela, colunas anuladas antes e as linhas de auditoria que o gatilho gravaria (e que a retirada apagaria).
- É determinístico.
- A retirada real (`--confirmar`) não mudou e continua exigindo `--projeto-autorizado` num projeto Supabase. **Não foi executada.**

**Evidências:**

| Prova | Resultado |
|---|---|
| Teste `test_simulacao_somente_leitura_sem_efeito_e_repetivel` (banco descartável) | Estado integral igual antes e depois: md5 de todas as tabelas, **todas as sequências** e estrutura (migrations, políticas, funções, privilégios, RLS, usuários). Auditoria sem linha nova. Duas simulações iguais. O plano previsto é exatamente o que a retirada real faz numa cópia descartável (mesma ordem e mesmo total) |
| Teste `test_simulacao_recusa_relacao_desatualizada_sem_efeito` | Relação desatualizada recusada, também sem efeito |
| `scripts/ensaio_bloco_d.py` (cópia fiel do projeto em PostgreSQL 17 descartável, sem arquivo) | Simulação: removeria 154; **estado integralmente igual** (nenhuma diferença, inclusive nas sequências); repetição igual. A retirada real na cópia removeu as mesmas 154. A restauração da cópia é idêntica ao remoto; migrations e carga seguem OK |

## 6. Dados fictícios: inventário de leitura repetido

`inventario` contra o remoto, comparado chave a chave com o do FIN-BLOCO-D-1:
- **idêntico:** 152 linhas em 21 tabelas, 0 ambíguas e nenhum aviso;
- **preservadas iguais:** perfis 1 e 2, 10 categorias de sistema, 25 TR, 19 categorias de IR, a fonte real do Pessoal, `public.usuario` e `alembic_version`;
- as 2 linhas a mais do ensaio de exclusão são as de auditoria que o gatilho grava durante a retirada. A simulação agora as prevê.

**Divergências:** nenhuma.

## 7. Conta do titular (procedimento preparado, nada criado)

**Estado atual do Auth** (leitura):
- só as 2 contas de teste (§8);
- cadastro público desativado, só e-mail, sem autoconfirmação;
- sem login anônimo, sem SAML e sem SSO.

**Limites encontrados:**
1. **Configuração privada do Auth.** Site URL, URLs de redirecionamento, SMTP, MFA, política de senha e limites não são públicos. Lê-los exigiria extrair o token da CLI do cofre de credenciais do Windows, o que não foi feito. São itens a conferir no painel.
2. **O aplicativo não tem:**
   - página para definir senha a partir de um convite;
   - recuperação de senha ("esqueci a senha");
   - desafio MFA.
   - Ele tem saída de sessão (`signOut`).
3. **SMTP padrão do Supabase:** segundo a documentação do Supabase, só entrega a endereços autorizados (membros da equipe da organização) e com limite baixo. Convite e recuperação por e-mail dependem disso ou de um SMTP próprio.
4. **Login antigo do Flask:** o `public.usuario` não é identidade do Auth e não é usado.

**Procedimento para o FIN-BLOCO-D-3** (cada passo com autorização):
1. **E-mail:** o titular confirma o endereço de acesso (pendência).
2. **Criação da conta:** pelo painel (Authentication → Users → Add user → Create new user).
   - O e-mail é o confirmado no passo 1.
   - A senha é **digitada pelo próprio titular**, forte e guardada num gerenciador. A IA não gera nem vê senhas.
   - "Auto Confirm User" ligado: o e-mail fica confirmado pela ação do próprio titular, dono do projeto.
   - Convite por e-mail só depois de existir a página de definir senha e um SMTP que entregue.
3. **Vínculo** com `scripts/vincular_titular_supabase.py`, depois da retirada e antes da carga:
   - **`conferir` (só leitura).** Recusa se:
     - não houver exatamente uma conta com o e-mail;
     - a conta for de teste ou não estiver confirmada;
     - os perfis 1 e 2 tiverem acesso de outra conta.
   - **`vincular --confirmar --projeto-autorizado <ref>`:** grava TITULAR + `pode_gerir` nos 2 perfis e, antes do commit, confere:
     - como o próprio titular, ele vê exatamente os 2 perfis como gestor;
     - nenhuma outra conta os alcança.
4. **Testes no aplicativo:**
   - login;
   - ver e gerir Pessoal e Empresa;
   - sair (a página protegida volta ao login);
   - outra conta não alcança os perfis.
5. **Recuperação de acesso:** hoje só pelo dono do projeto (painel ou Admin API). Antes da publicação, decidir entre:
   - implementar "esqueci a senha" com a página de definir senha, mais SMTP próprio;
   - aceitar a recuperação só administrativa.
6. **Autenticação forte:** o Cloudflare Access (código por e-mail) já fica na frente do aplicativo, como segunda camada. O MFA (TOTP) do Supabase exige suporte no aplicativo, que ainda não existe.

**Teste local** (`tests/test_vincular_titular_supabase.py`, 4 aprovados):
- recusas de conta inexistente, conta de teste, e-mail não confirmado e perfil com acesso de outra conta;
- conferência sem gravar;
- vínculo TITULAR com gestão;
- isolamento: as contas A e B não alcançam os perfis, o titular não alcança o perfil de outro e a leitura de dados é recusada com 42501;
- repetir não duplica;
- num projeto Supabase, só com autorização expressa.

## 8. Contas de teste A e B

| Conta | Id | Situação |
|---|---|---|
| A (avaliação) | `d9c71371…` | E-mail confirmado, último login em 27/10, 74 sessões. Titular dos perfis fictícios 31 e 39 |
| B | `4e7a9b60…` | E-mail confirmado, último login em 27/10, 141 sessões. Sem acesso a perfil |

**Exposição:** as senhas apareceram na saída de uma ferramenta numa sessão anterior. **É preciso rotacionar ou excluir as contas antes da publicação.**

**Dependências:**
- O E2E local (`web/tests/e2e/run_e2e.py`) **não depende delas**: usa contas fictícias próprias, criadas no banco descartável a cada execução.
- Dependem do projeto remoto, e portanto delas:
  - `web/tests/e2e/run_e2e_real.py`;
  - `scripts/homologacao_cartoes.py`;
  - `scripts/supabase_demo_preview_seed.py`;
  - os `scripts/supabase_*_real.py` e `scripts/homologacao_real/*`.
  - Todos leem `.env.e2e-real`.

**Procedimento no D-3:**
1. Depois da retirada, `scripts/verificar_seguranca_supabase.py` deve mostrar que nenhuma conta de teste tem acesso a perfil.
2. Excluir A e B pelo painel (Authentication → Users → Delete user). A exclusão leva identidades, sessões e refresh tokens, e as FKs do `financeiro` em cascata.
3. Apagar o `.env.e2e-real`.
4. Nunca mais apontar o E2E real nem os scripts `*_real` para o projeto de produção. Testes reais futuros vão num projeto de teste separado.
5. Se o titular quiser manter o E2E real até a conversão: trocar as senhas pelo painel (o titular digita) e atualizar o `.env.e2e-real`.

## 9. Revisão de segurança (`scripts/verificar_seguranca_supabase.py`, só leitura)

O verificador é novo e não faz sondagem de escrita. O `verificar_exposicao_supabase.py` antigo faz.

| Item | Resultado no projeto |
|---|---|
| RLS | ativo em todas as tabelas de `public` e `financeiro` |
| `anon` | nenhum privilégio em tabela, sequência ou função; só USAGE no schema `public` (padrão) |
| `PUBLIC` | nenhum privilégio em tabela |
| `authenticated` | SELECT direto só em `financeiro.categorias` e `financeiro.perfil_acesso`, cada uma com política "só as próprias"; o resto por 162 funções |
| Funções `security definer` | todas com `search_path` fixo |
| Documentos | só no banco (0 hoje), acessíveis só pelas funções; 0 buckets no Storage |
| Cartões | nenhum CVV, validade ou número completo preenchido |
| Auth | cadastro desativado, só e-mail, confirmação exigida, sem login anônimo, sem SAML |
| Frontend | build com a chave publicável; nenhuma chave privilegiada, JWT ou string de conexão em `web/src`, `web/dist` ou `web/scripts`; CSP restrita |
| Isolamento entre perfis | testes locais aprovados (perfis, RLS, exposição de `public`, gestão de perfis, vínculo do titular) |
| Bloqueios | **nenhum** |

**Recomendações para o D-3** (configuração do projeto, não alterada aqui):
- **SSL obrigatório para o banco está desligado.** Ligar.
- **Rede do banco aberta a qualquer IP** (`0.0.0.0/0`). Isso não afeta a API; avaliar restringir.
- **No painel:** conferir Site URL, URLs de redirecionamento, política de senha, limites e SMTP.

## 10. Testes

| Bateria | Resultado |
|---|---|
| Direcionada: backup (com PostgreSQL 17), simulação e retirada, vínculo do titular, carga, segurança e isolamento (`sec_supabase_public`, `supabase_mvp_rls`, `supabase_perfis`, `supabase_perfis_gestao`, `card_cvv_lock`), com PostgREST | **168 aprovados, 0 falhas, 0 pulados** |

**Regressão completa:** não repetida.
- Sem alteração funcional no aplicativo: as mudanças estão só em scripts de operação e testes.
- O E2E não foi afetado.

## 11. Pendências

1. **Bloqueia o backup:** comprovar ou providenciar a criptografia do local (§2), ou aceitar a alternativa 5.
2. **E-mail de acesso:** confirmar.
3. **Recuperação de senha e convite:** decidir (§7, item 5).
4. **Contas A e B:** excluir no D-3 ou rotacionar as senhas antes da publicação.
5. **Painel do Supabase:** ligar o SSL obrigatório e conferir a configuração do Auth.
6. **Autorizações do D-3:** push, retirada, migrations, conta, carga e publicação.
