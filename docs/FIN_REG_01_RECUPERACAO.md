# FIN-REG-01 — Procedimento de recuperação do banco

Roteiro para recuperar os dados do Controle Financeiro a partir de um backup independente. Não contém credenciais. Foi ensaiado em 15/11/2026 num PostgreSQL 17.6 descartável.

**Regra de ouro.** Nunca restaurar sobre o projeto de produção em uso. A ferramenta recusa o projeto de origem do backup e qualquer banco que já tenha tabelas.

## Quando usar cada caminho

| Situação | Caminho |
|---|---|
| Erro recente (até cerca de 7 dias) e o projeto Supabase existe | **Backup gerenciado**: painel do Supabase → Database → Backups → restaurar o dia. Volta o projeto inteiro àquele dia, com indisponibilidade |
| Projeto ou conta perdidos, backup gerenciado indisponível, ou necessidade de conferir dados antigos | **Backup independente**, este roteiro |
| Só consultar um dado antigo | Passos 1 a 7 num banco local; não mexe na produção |

## 1. Localizar o backup

- As cópias cifradas `cf-<projeto>-<data>_<hora>.cfbak` ficam em dois lugares: a pasta local de backups no disco D: e a pasta de backups no OneDrive.
- Ao lado de cada cópia há a ficha `….ficha.json` (identificação, tamanho e hashes, sem dados) e o `decifrar_cfbak.py`.
- Use a cópia mais recente, a menos que precise de uma data anterior.

## 2. Verificar a integridade da cópia cifrada

Calcule o SHA-256 do `.cfbak` e compare com `sha256_cifrado` da ficha:

```
certutil -hashfile <arquivo>.cfbak SHA256
```

## 3. Obter a chave

- A chave é um arquivo `cf-<projeto>-<data>_<hora>.chave`, com o mesmo nome do backup. Fica na pasta de chave do perfil do usuário, no disco C:, e na cópia que o titular guardou fora do computador.
- **Sem a chave, o backup não pode ser aberto.**
- A impressão digital do arquivo de chave está na ficha (`sha256_chave`), para confirmar que é a chave certa.

## 4. Ferramentas necessárias

- Python 3.11 com as bibliotecas `cryptography` e `psycopg2`. O ambiente `venv` do repositório já tem as duas.
- Ferramentas do **PostgreSQL 17** (`pg_restore`, `psql`): o mesmo major do servidor de produção. Aponte `CF_PG_BIN_BACKUP` para a pasta `bin`.
- O repositório `heydsonlc/Controle-Financeiro`, por causa de `scripts/backup_banco.py`.

## 5. Decifrar e conferir

```
python decifrar_cfbak.py <arquivo>.cfbak <arquivo>.chave <pasta protegida>
python scripts/backup_banco.py verificar --manifesto <pasta>/manifesto_<data>.json
```

- O primeiro comando mostra o SHA-256 do pacote; compare com `sha256_pacote_claro` da ficha.
- O segundo deve responder "Backup integro (SHA-256 conferidos)".
- A pasta passa a ter dados reais em texto claro. Use um local fora do OneDrive e apague ao final.

## 6. Preparar o banco de destino (vazio)

**A. Banco de conferência local (PostgreSQL 17 comum)**
1. Crie um servidor ou banco novo e vazio.
2. Crie os papéis da plataforma que o backup referencia: `anon`, `authenticated`, `service_role` e `supabase_admin`. O arquivo `supabase/tests/local_supabase_shim.sql` cria os três primeiros; o `supabase_admin` basta existir (`create role supabase_admin;`).
3. Se o `shim` foi aplicado, apague a tabela simplificada dele com `drop table auth.users;`. As contas vêm do backup, com a estrutura real.

**B. Projeto Supabase novo** (recuperação de verdade, com autorização)
1. Crie um projeto novo, PostgreSQL 17, vazio. Os papéis e o schema `auth` já existem.
2. Não aplique migrations antes: o backup traz a estrutura e o histórico.

## 7. Restaurar e conferir

```
set CF_PG_BIN_BACKUP=<pasta bin do PostgreSQL 17>
set CF_DESTINO=<conexão do banco de destino>
python scripts/backup_banco.py restaurar --manifesto <pasta>/manifesto_<data>.json --dsn-env CF_DESTINO
```

- A conexão vai sempre por variável de ambiente, nunca na linha de comando.
- Para um projeto Supabase novo, acrescente `--confirmar-projeto <ref do projeto novo>`.
- A ferramenta restaura primeiro as contas do Auth e depois o banco. Ao final compara o resultado com o manifesto.
- O resultado esperado é **"HOMOLOGADO: restauracao identica ao backup"**. Qualquer divergência interrompe com "Backup NAO HOMOLOGADO" e a lista das diferenças.

Conferências adicionais, usadas no ensaio:
- cada documento com o hash igual ao gravado: `select count(*) filter (where encode(sha256(conteudo), 'hex') = hash_arquivo), count(*) from public.ir_comprovante_arquivo;`
- 67 migrations em `supabase_migrations.schema_migrations`, ou o número do manifesto;
- cada perfil com seu titular: `financeiro.perfil_acesso` ligado a `auth.users`.

## 8. Para a aplicação voltar a funcionar (só no caminho B)

O banco restaurado não basta. Faltam itens que ficam fora dele:

1. **Configuração do Auth do projeto novo:** URL do site (`https://financas.kortexbrasil.com`), cadastro público desligado, provedores e SMTP como no projeto original.
2. **Exposição da API:** o schema `financeiro` precisa estar na lista de schemas expostos (Settings → API), como no projeto original.
3. **Site:** gerar o build com a URL e a chave publicável do projeto novo (`web/scripts/build.mjs`) e publicar no Cloudflare Pages. A CSP do site cita a URL do Supabase.
4. **Login:** as contas e senhas vêm no backup. As sessões não: cada usuário entra de novo. Fatores MFA, se existirem no futuro, não são copiados.
5. **`.env.staging`** local: apontar para o projeto novo.
6. Conferir com o titular os saldos e as últimas operações antes de voltar a usar.

## 9. Limitações

- O backup é uma fotografia: o que foi gravado depois da data do backup não é recuperado por ele.
- A restauração num projeto Supabase novo não foi ensaiada. O ensaio de 15/11/2026 foi num PostgreSQL 17.6 comum e saiu homologado.
- Não há recuperação pontual (PITR).
- A configuração do projeto (Auth, API, chaves) não está no backup; mantenha-a anotada.
- Apagar arquivos decifrados pelo sistema operacional não garante eliminação irrecuperável do disco.

## 10. Depois de restaurar

- Apague a pasta com os arquivos decifrados e o banco de conferência, se foi só consulta.
- Registre a data, o backup usado e o resultado da homologação.
