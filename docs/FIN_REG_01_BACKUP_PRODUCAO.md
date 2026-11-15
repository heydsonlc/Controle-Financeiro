# FIN-REG-01 — Backup independente e recuperação da produção

**Data:** 15/11/2026. **Resultado: APROVADO COM RESSALVAS** (seção 9).
A produção só foi lida, em sessão somente leitura. Nenhum dado, função, migration, configuração ou deploy foi alterado. Não houve commit nem push.

## 1. Situação inicial

Auditoria de 15/11/2026: nenhum backup independente real, restauração testada só com dados fictícios, backups gerenciados não verificados.

Reconferido antes da exportação:
- PostgreSQL **17.6**;
- 67 migrations, última `20261227090000`;
- 88 tabelas;
- 569 funções em `financeiro`;
- banco de 25 MB.

## 2. Etapa A — Backups gerenciados do Supabase

Fonte: `supabase backups list` (API de gestão, somente leitura), em 15/11/2026.

| Item | Resultado |
|---|---|
| Backups automáticos | **Existem.** Físicos (WAL-G), diários, todos `COMPLETED` |
| Frequência | 1 por dia, por volta de 05:25 UTC |
| Retenção observada | 8 listados, de 08/11 a 15/11/2026, cerca de 7 dias |
| Último disponível | 15/11/2026, 05:26 UTC |
| Recuperação pontual (PITR) | Não contratada (`pitr_enabled: false`) |
| Plano | **NÃO COMPROVADO** pela CLI. Backup diário de 7 dias é o padrão do plano Pro; confirmar no painel, em Organization → Billing |
| Restauração oferecida | Pelo painel, em Database → Backups. É feita sobre o próprio projeto, com indisponibilidade; não há download do backup físico |
| Custos adicionais | Nenhum para o backup diário. O PITR é um adicional pago e não foi ativado |

Nenhuma funcionalidade paga foi ativada e o plano não foi alterado.

## 3. Etapa B — Ferramenta `scripts/backup_banco.py`

A ferramenta já atendia ao essencial:
- cobre `public`, `financeiro` e `supabase_migrations`;
- cobre `auth.users` e `auth.identities`;
- gera um arquivo separado com os documentos;
- exporta de um snapshot único, em modo somente leitura;
- grava manifesto com SHA-256 e um "retrato" do banco: linhas e md5 por tabela, funções, políticas, RLS, privilégios, restrições, gatilhos e migrations;
- restaura só em banco vazio, com homologação.

**Três deficiências, corrigidas localmente com autorização do titular (sem commit):**

| Deficiência | Correção |
|---|---|
| Não havia trava própria contra restaurar na produção; só a recusa de "banco não vazio" | `restaurar` recusa o projeto de origem do backup em qualquer caso e recusa qualquer destino Supabase sem `--confirmar-projeto <ref>` |
| A conexão ia na linha de comando do `pg_dump`/`pg_restore`, e uma falha deles exibia o comando com a conexão | A senha vai por `PGPASSWORD`, fora da linha de comando; a falha é relatada sem o comando, a conexão ou a senha |
| O manifesto não identificava o backup nem a versão da ferramenta | Campos `backup_id` e `ferramenta` (SHA-256 do script e commit) |

Arquivos alterados localmente: `scripts/backup_banco.py` (+83, −16) e `tests/test_backup_banco.py` (3 testes novos).

**Limite conhecido da autenticação.** O backup traz as contas (`auth.users`) e os logins por e-mail (`auth.identities`). Não traz sessões, refresh tokens nem fatores MFA. Também não traz a configuração do Auth (URLs, provedores, SMTP) nem as chaves da API, que são do projeto e ficam fora do banco.

## 4. Etapa C — Ambiente

| Item | Resultado |
|---|---|
| Ferramentas | A máquina tinha só o PostgreSQL 18. Com autorização, foram baixados os binários oficiais **17.6** (zip da EDB, sem instalação, fora do repositório, 134 MB) |
| Espaço em disco | C: 59 GB e D: 408 GB livres |
| Acesso | Conexão do `.env.staging`, em sessão `readonly` |
| Criptografia | AES-256-GCM pela biblioteca `cryptography` 50.0 do ambiente Python do projeto; nada instalado |
| Destino de restauração | Cluster PostgreSQL 17.6 descartável, em `127.0.0.1` |

## 5. Testes prévios, com dados fictícios

`tests/test_backup_banco.py`: **10 aprovados, 0 reprovados**, com o PostgreSQL 17 habilitado.

| Exigência do contrato | Teste | Resultado |
|---|---|---|
| Exportação em banco descartável | `test_backup_restaura_igual_num_banco_novo_e_recusa_banco_existente` | Aprovado |
| Verificador de hashes | idem | Aprovado |
| Arquivo adulterado | `test_arquivo_alterado_e_recusado` | Aprovado |
| Recusa de banco não vazio | idem ao primeiro | Aprovado |
| Proteção contra destino de produção | `test_restaurar_recusa_projeto_de_origem_e_supabase_sem_confirmacao` (novo) | Aprovado |
| Compatibilidade com o PostgreSQL 17 | `test_pg17_backup_restaura_igual_e_recusa_banco_existente`, com as ferramentas 17 e com as 18 | Aprovado |
| Credenciais fora dos logs | `test_senha_fora_da_linha_de_comando_e_das_mensagens` (novo); `test_backup_completo_homologado_num_banco_sem_auth` | Aprovado |
| Manifesto identificado | `test_manifesto_identifica_o_backup_e_a_ferramenta` (novo) | Aprovado |

## 6. Etapa D — Backup real

Comando: `scripts/backup_banco.py exportar --dsn-env <variável> --saida <pasta de trabalho>`, com `CF_PG_BIN_BACKUP` apontando para as ferramentas 17.6. A chamada foi feita por um roteiro externo, que confere o projeto antes de exportar.

| Item | Valor |
|---|---|
| Identificação | `cf-fzjmgekasjrgvmfdkdog-20261115_150732` |
| Gerado em | 15/11/2026, 15:07 (horário local) |
| Servidor e ferramenta | PostgreSQL 17.6; `pg_dump` 17.6; script `b94014e3…`, commit de base `3f480c4` |
| Conteúdo | 88 tabelas, **3.137 linhas**, 67 migrations (última `20261227090000`), 569 funções, 2 políticas, 7 gatilhos, 372 restrições; Auth: 2 contas e 2 identidades |
| Documentos fiscais | 2 arquivos em `ir_comprovante_arquivo`, 1.630.625 bytes, com o conteúdo incluído no md5 do retrato |
| Conferência com a origem | Retrato do manifesto **igual** a uma nova leitura da produção logo após a exportação |
| Segredos no manifesto | Nem a conexão nem a senha aparecem (conferido) |

**Artefatos (SHA-256)**

| Arquivo | Bytes | SHA-256 |
|---|---|---|
| `banco_20261115_150732.dump` | 4.493.623 | `3dd1ef95fb760ae99c03444c3e8b815bc1bde139b8bb82e20a563fab33917d3e` |
| `documentos_20261115_150732.dump` | 1.821.941 | `a5b43de67636d248575d1a5d4d7b9d5de17240a025180b4727a38242196443b5` |
| `usuarios_20261115_150732.dump` | 14.344 | `6a09e77c9d86934c54edd5b752e78b0b178c19fd6fbce4034340eb9b6dc1d49d` |
| `manifesto_20261115_150732.json` | 164.561 | `c97dfb2ea39f661f9e14bd3f3b57ec5439a0aebec9a10fbff826781075ec99e9` |
| Pacote (tar dos 4 arquivos) | — | `a0e2f79541790aed64041ecf4d57afd5daca46537acea0f48eb9ff547fb85671` |
| **Cópia cifrada** `…150732.cfbak` | 6.512.675 | `0328ecbd773d6d014f220890d9685977f8bef1be2c37443e08c91552b841f8d4` |

**Criptografia.** AES-256-GCM, com chave aleatória de 256 bits gravada em arquivo próprio e nunca exibida. O formato `CFBAK1` está descrito na ficha `.ficha.json`, que não contém dados. A decifragem foi conferida relendo a chave e o arquivo do disco: o pacote volta idêntico.

## 7. Etapa E — Armazenamento (decisão do titular: pasta local + OneDrive; chave em arquivo)

| Item | Onde | Conferência |
|---|---|---|
| Cópia cifrada 1 | pasta local de backups, no disco D:, fora do OneDrive | SHA-256 igual |
| Cópia cifrada 2 | pasta de backups no OneDrive (recebe **só** o arquivo cifrado) | SHA-256 igual |
| Chave | pasta própria no perfil do usuário (disco C:), separada das cópias e fora do OneDrive | impressão digital do arquivo de chave: `93c8da0a…` |
| Junto das cópias | ficha do backup e `decifrar_cfbak.py` (sem segredos) | — |

Nenhum link público e nenhum outro serviço externo. Nada foi enviado ao GitHub nem ao Cloudflare.

## 8. Etapas F e G — Ensaio e verificação da restauração

O ensaio partiu da **cópia guardada no OneDrive**: decifrada com a chave do arquivo, verificada e restaurada com `scripts/backup_banco.py restaurar`.

| Verificação | Resultado |
|---|---|
| Destino | PostgreSQL **17.6** descartável em `127.0.0.1`; conferido que não é Supabase e que está vazio |
| Estruturas e dados | Restaurados: `public`, `financeiro`, `supabase_migrations` |
| Autenticação | `auth.users` e `auth.identities`, com estrutura, chaves e índices: 2 contas e 2 identidades |
| Homologação da ferramenta | **HOMOLOGADO**: retrato restaurado idêntico ao do manifesto (linhas e md5 de cada tabela, sequências, funções, execução pelos papéis da API, políticas, RLS, restrições, gatilhos, privilégios e migrations) |
| Migrations | 67 |
| Funções | 569 |
| Documentos | 2 de 2 com o SHA-256 do conteúdo restaurado igual ao hash gravado no envio, e com o tamanho igual |
| Perfis | Pessoal e Kortex (Empresa): cada um com 1 vínculo de titular gestor, ligado a uma conta existente no Auth restaurado |
| Login no ambiente restaurado | Não realizado (proibido pelo contrato) |
| Envio de e-mails ou integrações | Nenhum; ambiente isolado |

**Divergência encontrada e tratada.** A primeira tentativa falhou porque o dump cita o papel interno `supabase_admin` em 12 comandos de privilégios padrão, e esse papel não existe num PostgreSQL comum. Com o papel criado vazio no banco de conferência, a restauração foi homologada. Num projeto Supabase esse papel sempre existe. O pré-requisito está no roteiro de recuperação.

**Classificação do ensaio: APROVADO.**

## 9. Etapa H — Arquivos temporários

| Cópia | Destino |
|---|---|
| Pasta de trabalho com os dumps em texto claro (disco D:, fora do OneDrive) | **Apagada** depois de conferir as duas cópias cifradas e a chave |
| Banco descartável do ensaio | Cluster parado e pasta temporária removida ao fim do ensaio |
| Extração de prova do decifrador | Apagada |
| Temporários dos testes com dados fictícios | Apagados |

A exclusão foi a comum do sistema de arquivos: em disco, não equivale a eliminação irrecuperável. O texto claro esteve só em disco local, nunca no OneDrive.

## 10. Riscos residuais e ressalvas

| # | Ressalva | Ação |
|---|---|---|
| 1 | **A chave existe em um único arquivo, neste computador.** Se o computador se perder, a cópia do OneDrive fica ilegível | **Titular:** copiar o arquivo de chave para um local fora desta máquina (pendrive guardado ou cofre do gerenciador de senhas). É a única pendência que impede o "APROVADO" pleno |
| 2 | A cópia local e a chave estão na mesma máquina; quem tiver acesso a ela abre o backup | Aceito pelo desenho escolhido: a máquina já tem a conexão da produção |
| 3 | Plano do Supabase e retenção não confirmados no painel | Titular confere em Billing |
| 4 | O backup é uma fotografia de 15/11/2026; o que mudar depois não está nele | Rotina periódica (FIN-REG-02) |
| 5 | Recuperação operacional completa depende de itens fora do banco: configuração do Auth, chaves da API, `config.js` do site, sessões (os usuários entram de novo) | Descrito em `FIN_REG_01_RECUPERACAO.md` |
| 6 | Restauração num **projeto Supabase novo** não foi ensaiada (o contrato proíbe criar projetos); o ensaio foi num PostgreSQL 17.6 comum | Ensaio opcional futuro, com autorização |
| 7 | As correções da ferramenta e os testes estão só no computador | Autorizar commit e push |

## 11. Relatório ao titular

| Verificação | Resultado |
|---|---|
| Backups gerenciados do Supabase | Existem: diários, cerca de 7 dias, último em 15/11; sem PITR; plano não comprovado |
| Backup independente produzido | Sim: `cf-fzjmgekasjrgvmfdkdog-20261115_150732` |
| Cópia criptografada | Sim: AES-256-GCM, 6,5 MB, decifragem conferida |
| Local de armazenamento | Pasta local (D:) e OneDrive, ambas só com o arquivo cifrado; chave em pasta separada (C:) |
| Manifesto SHA-256 | Conferido na exportação, depois de decifrar e antes de restaurar |
| Documentos fiscais incluídos | Sim: 2 de 2, com conteúdo conferido por SHA-256 após a restauração |
| Restauração isolada | Sim: PostgreSQL 17.6 descartável local |
| Integridade dos dados | Retrato restaurado idêntico ao manifesto e à produção |
| Recuperação estrutural | 88 tabelas, 569 funções, políticas, privilégios, gatilhos e 67 migrations |
| Pendências | Copiar a chave para fora do computador; confirmar o plano; autorizar o commit das correções |
| Situação final | **FIN-REG-01 — APROVADO COM RESSALVAS** |

**Critérios de aceite:** atendidos os 12. O critério 5 (local autorizado) e o 12 (riscos identificados) carregam a ressalva da chave única.
