# Backup PostgreSQL Local

## Objetivo

Este guia descreve como configurar o backup local do PostgreSQL no Controle Financeiro usando as ferramentas oficiais `pg_dump`, `pg_restore` e, opcionalmente, `psql`.

## Onde ficam os backups

Os backups gerados pela aplicação ficam em:

```text
data/backups/postgres/
```

O histórico operacional fica fora do banco, em:

```text
data/backups/backup_history.json
```

Esses arquivos não devem ser versionados no Git.

## Como configurar o pg_dump

1. Abra `/configuracoes#backup`.
2. Acesse o bloco `Ferramentas PostgreSQL`.
3. Clique em `Autodetectar`.
4. Se a instalação for encontrada, clique em `Validar ferramentas`.
5. Se não for encontrada, informe manualmente os caminhos.

Exemplo comum no Windows:

```text
C:\Program Files\PostgreSQL\18\bin\pg_dump.exe
C:\Program Files\PostgreSQL\18\bin\pg_restore.exe
C:\Program Files\PostgreSQL\18\bin\psql.exe
```

O `psql` só é necessário para restaurar backups em formato `.sql`.

## Como encontrar a pasta bin

No Windows, verifique estas pastas:

```text
C:\Program Files\PostgreSQL\18\bin
C:\Program Files\PostgreSQL\17\bin
C:\Program Files\PostgreSQL\16\bin
C:\Program Files\PostgreSQL\15\bin
C:\Program Files\PostgreSQL\14\bin
```

A aplicação procura apenas em diretórios padrão do PostgreSQL. Ela não varre o disco inteiro.

## Como testar backup

1. Valide as ferramentas.
2. Clique em `Executar backup`.
3. Confirme no histórico se o status ficou `Concluído`.
4. Baixe o arquivo gerado e armazene uma cópia fora da pasta do projeto.

Se aparecer erro de ferramenta ausente, instale o PostgreSQL completo ou configure manualmente os caminhos.

## Como restaurar com segurança

Antes de restaurar:

1. Gere um backup novo do estado atual.
2. Confirme que o arquivo escolhido está em `data/backups/postgres/`.
3. Use preferencialmente uma base descartável para testar.
4. Digite exatamente:

```text
CONFIRMO RESTAURACAO
```

Sem essa confirmação textual a aplicação bloqueia o restore.

## Cuidados com dados reais

- Não compartilhe arquivos de backup sem avaliar dados sensíveis.
- Não inclua senhas em documentação ou commits.
- Não execute restore real sem backup recente.
- Mantenha cópias em local seguro fora da pasta do projeto.

## Procedimento recomendado antes do uso real

1. Configurar `pg_dump` e `pg_restore`.
2. Executar um backup real.
3. Baixar o arquivo gerado.
4. Testar uma restauração em banco descartável.
5. Só então iniciar o uso com dados reais.
