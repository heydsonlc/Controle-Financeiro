# FIN-REG-02 — Rotina periódica de backup seguro

**Situação em 15/11/2026:** implementação homologada pelo titular e **primeira execução real feita e verificada** (seção 12). A chave mestra de 2026 (`2026-4e98de1a`) e a chave do backup do FIN-REG-01 estão copiadas num pendrive USB que o titular confirmou guardar fora do computador. Commit só local, sem push; sem deploy, migration ou agendamento. Falta, para encerrar: o titular conferir que o arquivo chegou à nuvem do OneDrive.

A rotina é manual assistida: o titular aciona um único comando. Ela não agenda nada e **não exclui backups**.

## 1. O que foi entregue

| Item | Arquivo |
|---|---|
| Orquestrador (comando único e consultas) | `scripts/backup_rotina.py` |
| Testes automatizados (18) | `tests/test_backup_rotina.py` |
| Este documento | `docs/FIN_REG_02_ROTINA_BACKUP.md` |
| Roteiro de recuperação, com o passo para os backups da rotina | `docs/FIN_REG_01_RECUPERACAO.md` |

`scripts/backup_banco.py` (exportação, verificação e restauração homologadas no FIN-REG-01) não foi alterado. A rotina só o chama.

## 2. Configuração

Os padrões já estão no script e correspondem ao ambiente homologado no FIN-REG-01:

| Item | Padrão |
|---|---|
| Projeto | `fzjmgekasjrgvmfdkdog` |
| Conexão | `DATABASE_URL` do arquivo local `.env.staging` (nunca impressa nem registrada) |
| Ferramentas do PostgreSQL 17 | `%LOCALAPPDATA%\cf-e2e\pg17\pgsql\bin` |
| Destino 1 (local) | `D:\CF-Backups` |
| Destino 2 (OneDrive) | `D:\OneDrive\Backups-Controle-Financeiro` |
| Pasta de trabalho (texto claro, temporária) | `D:\CF-Backups\_trabalho` |
| Pasta de chaves | `%USERPROFILE%\CF-Backup-Chave` |
| Registro das execuções | `D:\CF-Backups\registro_execucoes.jsonl` |
| Espaço mínimo livre | 300 MB em cada local |
| Aviso de atraso | mais de 10 dias |

Para trocar qualquer item, aponte a variável de ambiente `CF_BACKUP_ROTINA_CONFIG` para um arquivo JSON com os itens a substituir.

Requisitos: o `venv` do repositório (bibliotecas `cryptography`, `psycopg2` e `python-dotenv`) e as ferramentas do PostgreSQL 17.

## 3. Comando único

```
venv\Scripts\python scripts\backup_rotina.py executar
```

Antes de migration ou de manutenção de dados:

```
venv\Scripts\python scripts\backup_rotina.py executar --tipo PRE_MIGRATION --migration <identificador>
venv\Scripts\python scripts\backup_rotina.py executar --tipo MANUTENCAO --migration <descrição curta>
```

O backup antes da migration é requisito do procedimento, não garantia automática de retorno: voltar atrás exige a restauração assistida. A rotina não aplica migrations.

### Sequência executada

| Etapa | O que faz | Se falhar |
|---|---|---|
| 1 | Valida a configuração: tipos, pastas, dois destinos distintos, ferramentas, nenhum resto em texto claro | `FALHA_PREPARACAO` |
| 2 | Confere que o arquivo de ambiente aponta para o projeto esperado | `FALHA_PREPARACAO` |
| 3 | Confere a chave do ano: existe, é a registrada e tem guarda externa confirmada | `FALHA_CHAVE` |
| 4 | Confere o espaço livre na pasta de trabalho e nos dois destinos | `FALHA_PREPARACAO` |
| 5 | Abre a conexão em modo somente leitura e confere a versão do servidor com a do `pg_dump` | `FALHA_PREPARACAO` |
| 6 | Exporta pelo `backup_banco.py` (um único snapshot) | `FALHA_EXPORTACAO` |
| 7 | Verifica o manifesto (SHA-256, projeto, cobertura dos documentos fiscais, ausência de dados de conexão) e anota nele o tipo e o identificador da chave | `FALHA_INTEGRIDADE` |
| 8 | Cifra o pacote (AES-256-GCM) | `FALHA_CRIPTOGRAFIA` |
| 9 | Relê o arquivo cifrado e a chave do disco e confere a decifragem | `FALHA_CRIPTOGRAFIA` |
| 10 | Copia o arquivo cifrado e a ficha para cada destino, com nome provisório | `FALHA_COPIA` |
| 11 | Relê cada cópia do destino e confere o SHA-256; só então dá o nome final | `FALHA_INTEGRIDADE` |
| 12 | Grava uma linha no registro, também nas falhas | — |
| 13 | Sobrescreve e apaga o texto claro da pasta de trabalho | `CONCLUIDO_COM_LIMPEZA_PENDENTE` |
| 14 | Mostra a conclusão ou a falha | — |

A execução só termina como `CONCLUIDO`, com a mensagem "BACKUP CONCLUIDO" e código de saída 0, quando as duas cópias estão verificadas. Qualquer outro estado sai com código 1 e sem mensagem de sucesso.

## 4. Chave anual

- **Modelo:** uma chave mestra por ano, de 256 bits, gerada pelo sistema operacional. Fica no arquivo `cf-<projeto>-mestra-<ano>.chave`, na pasta de chaves, somente leitura.
- **Cada backup tem parâmetros próprios:** sal e nonce aleatórios por arquivo. A chave que cifra o arquivo é derivada da mestra (HKDF-SHA256) com esse sal e o identificador do backup.
- **Identificador da chave:** `<ano>-<8 primeiros caracteres do SHA-256 do arquivo>`. Vai no cabeçalho do arquivo cifrado, na ficha, no manifesto e no registro. O conteúdo da chave não vai a lugar nenhum.
- **Índice:** `chaves.json`, na pasta de chaves, guarda identificador, ano, impressão digital e as guardas confirmadas. Ele é exigido para cifrar. Para decifrar basta o arquivo da chave: num computador novo, só com a cópia externa, o backup abre, porque o identificador gravado no backup é conferido com a impressão digital do arquivo.
- A pasta de chaves não pode ficar no OneDrive nem dentro de um destino de backup. A rotina recusa.
- Não há comando que substitua ou apague uma chave. `chave criar` recusa um ano que já tem chave.

### Criar a chave e confirmar a guarda externa

```
venv\Scripts\python scripts\backup_rotina.py chave criar --ano 2026
```

Depois, copie o arquivo para fora do computador e confirme por um dos dois caminhos:

```
venv\Scripts\python scripts\backup_rotina.py chave confirmar-guarda --ano 2026 --copia E:\<pasta>\cf-...-mestra-2026.chave
venv\Scripts\python scripts\backup_rotina.py chave confirmar-guarda --ano 2026 --digitar
```

- `--copia`: a rotina lê a cópia e exige que ela seja igual à chave e esteja em outra unidade, que não seja a das chaves, a de trabalho, a dos destinos, nem o OneDrive.
- `--digitar`: para a cópia num cofre de senhas. O valor é colado no próprio terminal, sem aparecer na tela, e comparado com a chave. Nunca pelo chat.

**Sem guarda confirmada, `executar` para na etapa 3 e nada é exportado.** Recomenda-se confirmar duas guardas (pendrive e cofre de senhas).

### Rotação na troca de ano

1. Em dezembro ou no início de janeiro: `chave criar --ano <novo ano>`. A rotina aceita o ano corrente e o seguinte.
2. A chave anterior permanece no lugar, intocada.
3. `chave situacao` mostra as duas versões registradas.
4. `conferir --backup-id <um backup do ano anterior>` valida que um backup antigo continua abrindo.
5. Copiar a chave nova para fora do computador e rodar `chave confirmar-guarda`. Só depois disso a rotina a usa.

A rotação não recifra nem exclui backups antigos. Cada backup abre com a chave indicada no próprio cabeçalho. O backup do FIN-REG-01 (formato anterior, com chave própria) continua legível, e a chave dele não deve ser descartada.

## 5. Consulta, verificação e recuperação

| Quando | Comando | O que faz |
|---|---|---|
| A qualquer momento | `situacao` | Último backup válido, dias desde ele, última execução e o estado dela, idade do mais recente, chave do ano. Avisa "BACKUP ATRASADO" depois de 10 dias. Não gera backup |
| Mensal | `conferir [--backup-id ID]` | SHA-256 das duas cópias guardadas, decifragem e manifesto do backup mais recente. Não acessa a produção |
| Trimestral e antes de migration de risco | `ensaiar [--backup-id ID]` | Restaura a cópia guardada num PostgreSQL 17 descartável, criado e destruído pelo comando em `127.0.0.1`, pela ferramenta do FIN-REG-01, e exige "HOMOLOGADO". Confere cada documento fiscal com o hash gravado |
| Depois de falha de cópia | `completar --backup-id ID` | Copia o que falta a partir de uma cópia íntegra. Não sobrescreve |
| Depois de execução interrompida | `limpar-trabalho` | Apaga restos em texto claro |
| Recuperação | `decifrar --arquivo <.cfbak> --saida <pasta>` | Extrai o manifesto e os dumps numa pasta nova e protegida; segue-se o `docs/FIN_REG_01_RECUPERACAO.md` a partir do passo 5 |

O comando `ensaiar` não aceita conexão de destino: não há como apontá-lo para o Supabase. A restauração num projeto real continua sendo só a do roteiro do FIN-REG-01, com as travas dele.

Um backup só é "válido" quando o arquivo existe nos dois destinos e o SHA-256 de cada um confere com a ficha.

## 6. Retenção (só informativa)

```
venv\Scripts\python scripts\backup_rotina.py retencao
```

| Categoria | Política recomendada |
|---|---|
| Semanal | Os 8 últimos |
| Mensal | O primeiro de cada mês, por 12 meses |
| Anual | O último de dezembro de cada ano, sem prazo |
| Antes de migration | Até haver cópia posterior válida e a intervenção estar homologada |

O comando lista os backups que passaram do período recomendado e os incompletos. **Ele não exclui nada, e a rotina não tem comando de exclusão.** A decisão de apagar, no disco local e no OneDrive, é do titular.

As únicas remoções feitas pela rotina são de temporários dela: o texto claro da pasta de trabalho, a cópia cifrada provisória depois de guardada e conferida, e o resto `.parcial` de uma cópia que falhou.

## 7. Registro das execuções

Arquivo local `D:\CF-Backups\registro_execucoes.jsonl`, uma linha por execução, inclusive as que falham, as conferências e os ensaios. Campos: data e hora, operação, tipo, migration, identificador do backup, versão da ferramenta (versão, hashes dos dois scripts e commit), identificador da chave, tamanho e SHA-256 do arquivo cifrado, resultado da exportação, da verificação e da criptografia, situação de cada destino, limpeza, estado final e mensagem de erro.

O registro não tem senha, conexão, chave, dado financeiro nem documento. Fica fora do repositório e não é enviado a lugar nenhum.

## 8. Tratamento de falhas

| Estado | Significado | Providência |
|---|---|---|
| `FALHA_PREPARACAO` | Nada foi exportado | Corrigir o que a mensagem indica (espaço, conexão, pasta, restos) |
| `FALHA_CHAVE` | Nada foi exportado ou o backup não pôde ser aberto | Criar a chave, confirmar a guarda ou recuperar o arquivo da cópia externa |
| `FALHA_EXPORTACAO` | Backup inválido; o que foi gerado é apagado | Rodar de novo |
| `FALHA_INTEGRIDADE` | Manifesto ou cópia não conferem; não é backup válido | Rodar de novo ou `completar` |
| `FALHA_CRIPTOGRAFIA` | Nada foi copiado; nenhum texto claro vai aos destinos | Rodar de novo |
| `FALHA_COPIA` | A mensagem diz qual destino falhou; a cópia cifrada íntegra fica preservada | Resolver o destino e rodar `completar --backup-id <ID>` |
| `CONCLUIDO_COM_LIMPEZA_PENDENTE` | As duas cópias estão verificadas, mas restou texto claro no caminho informado | `limpar-trabalho` ou apagar a pasta |
| `INTERROMPIDA` | Execução cancelada | Rodar de novo |

- Se a cópia falha num destino, a do outro fica. Se falha nos dois, o arquivo cifrado e a ficha ficam na pasta de trabalho, sem os dumps.
- A rotina nunca sobrescreve: um identificador que já existe num destino interrompe a execução.
- Restos em texto claro de uma execução anterior bloqueiam a seguinte até a limpeza.

## 9. Segurança

- A produção é lida numa sessão somente leitura, conferida na etapa 5. O `pg_dump` só lê.
- A conexão vem do arquivo de ambiente, passa ao `pg_dump` sem a senha na linha de comando e é filtrada de toda mensagem e do registro.
- A pasta de trabalho fica fora do OneDrive e cada execução restringe a própria pasta ao usuário atual (`icacls`).
- Só o arquivo cifrado e a ficha (identificação, tamanho e hashes) vão aos destinos.
- A rotina não grava no Supabase, não chama a aplicação nem o Cloudflare e não envia dados a outros serviços.

## 10. Resultado dos testes

Executados em 15/11/2026, com dados fictícios, em clusters PostgreSQL descartáveis.

| Bateria | Resultado |
|---|---|
| `tests/test_backup_rotina.py` com as ferramentas da máquina (PostgreSQL 18) | 18 aprovados, 0 falhas |
| `tests/test_backup_rotina.py` com PostgreSQL 17 (`CF_MVP_PG_BIN`) | 18 aprovados, 0 falhas |
| `tests/test_backup_banco.py` (FIN-REG-01, com `CF_PG17_BIN`) | 10 aprovados, 0 falhas |

Cenários do contrato:

| # | Cenário | Coberto por |
|---|---|---|
| 1 | Fluxo completo | `test_fluxo_completo_...` (inclui conferência, ensaio de restauração, decifragem e `PRE_MIGRATION`) |
| 2, 3 | Chave ausente; chave incorreta | `test_chave_ausente_sem_guarda_ou_incorreta_...`, `test_backup_nao_abre_com_a_chave_errada` |
| 4, 5 | Espaço insuficiente; falha de conexão | `test_espaco_insuficiente_e_falha_de_conexao_...` |
| 6, 7 | Falha de exportação; falha de criptografia | `test_falha_na_exportacao_ou_na_criptografia_...`, `test_manifesto_adulterado_e_recusado` |
| 8, 9 | Falha na cópia local; falha na cópia do OneDrive | `test_falha_de_copia_num_destino_...` (os dois destinos), `test_falha_nos_dois_destinos_...` |
| 10 | Hash divergente | `test_hash_divergente_no_destino_recusa_o_backup` |
| 11 | Reexecução com nome existente | `test_reexecucao_com_nome_existente_nao_sobrescreve` |
| 12, 13 | Rotação anual; leitura com a chave anterior | `test_rotacao_anual_...` (inclui o formato do FIN-REG-01), `test_cada_arquivo_tem_sal_e_nonce_proprios_...` |
| 14 | Aviso por backup vencido | `test_aviso_de_backup_atrasado_sem_gerar_backup` |
| 15, 16 | Candidatos à retenção; ausência de exclusão | `test_retencao_identifica_candidatos_e_nao_exclui_nada`, `test_a_rotina_nao_tem_comando_de_exclusao_...` |
| 17 | Ausência de credenciais em logs | Verificado no fluxo completo e nas falhas: saída, registro, fichas, índice de chaves e manifesto |
| 18 | Proteções do FIN-REG-01 | `test_protecoes_do_reg01_preservadas` e a bateria do FIN-REG-01 |
| — | Falha de limpeza | `test_falha_na_limpeza_e_informada_...` |

Consultas feitas com a configuração real, só de leitura local (`situacao`, `retencao`, `chave situacao`): o backup do FIN-REG-01 aparece como válido nos dois destinos, nenhum candidato à exclusão e nenhuma chave anual registrada. Nenhum arquivo foi criado nas pastas reais.

## 11. Limitações conhecidas

- A rotina depende de o titular lembrar de executá-la. O aviso de atraso só aparece quando `situacao` é consultada.
- A confirmação da guarda externa prova que a cópia existia e era igual no momento da confirmação. Não prova que ela continua guardada. Convém repetir a confirmação no ensaio trimestral.
- Com `--copia`, a rotina distingue unidades, não aparelhos: outra partição interna com letra diferente passaria como "outro volume". **Outra letra de unidade não garante que a cópia esteja fora do computador:** a guarda só vale num pendrive ou disco fisicamente separado, ou num cofre de senhas independente.
- O pacote é cifrado em memória. Com cerca de 6,5 MB por backup isso é irrelevante; a partir de centenas de megabytes o formato precisaria de cifragem em blocos.
- Sobrescrever e apagar o texto claro não garante eliminação irrecuperável em SSD.
- O `ensaiar` usa o cluster descartável dos testes do repositório (`tests/supabase_local.py`) e não ensaia a restauração num projeto Supabase novo.
- **A rotina não distingue arquivo presente na pasta sincronizada do OneDrive de arquivo efetivamente enviado à nuvem.** Ela confere o SHA-256 na pasta local; o envio é feito pelo cliente do OneDrive. Depois de cada backup, confira no cliente (sincronização concluída) ou em onedrive.com que o arquivo chegou.
- O backup é uma fotografia. Não há recuperação pontual (PITR).

## 12. Primeira execução real (15/11/2026)

Autorizada pelo titular depois de confirmada a guarda externa das chaves.

| Item | Resultado |
|---|---|
| Comando | `backup_rotina.py executar` (tipo `SEMANAL`), código de saída 0 |
| Backup | `cf-fzjmgekasjrgvmfdkdog-20261115_201916` |
| Conteúdo | 3.137 linhas em 88 tabelas; 67 migrations; 2 contas e 2 identidades do Auth |
| Chave | `2026-4e98de1a` |
| Arquivo cifrado | 6.512.876 bytes; SHA-256 `d1f9262b99090e5f55d25846dc4b5c7a7bb8b4aeb5365bca7634c5390776da91` |
| Destino local (`D:\CF-Backups`) | VERIFICADO, mesmo SHA-256 |
| Destino OneDrive (pasta sincronizada) | VERIFICADO, mesmo SHA-256 |
| Texto claro | Removido; pasta de trabalho vazia |
| `conferir` | Cópias íntegras nos dois destinos, decifragem e manifesto conferidos |
| `ensaiar` | HOMOLOGADO: restauração idêntica ao backup num PostgreSQL 17 descartável; 2 de 2 documentos fiscais com o SHA-256 igual ao gravado; banco descartável removido |
| `situacao` | Último backup válido: o desta execução; sem avisos |
| `retencao` | 2 backups guardados, nenhum além da política; nada excluído |
| Produção | Só leitura; nenhuma escrita no Supabase |
| Backup do FIN-REG-01 | Intocado nos dois destinos |

O registro `D:\CF-Backupsegistro_execucoes.jsonl` tem as três linhas (backup, conferência e ensaio), todas `CONCLUIDO`.

### Pendências

1. **Titular:** conferir no cliente do OneDrive ou em onedrive.com que o `.cfbak` e a ficha de 20:19 chegaram à nuvem. A rotina só confere a pasta local.
2. Recomendado: segunda guarda das chaves num cofre de senhas, porque as duas cópias externas estão no mesmo pendrive.
3. Push dos arquivos, quando autorizado.
4. Próximo backup semanal: até 22/11/2026. Antes de qualquer migration: `executar --tipo PRE_MIGRATION`.
