# Guia de Início Rápido

## Nota de Direção Técnica

Este guia descreve o fluxo local atual. PostgreSQL local é o banco oficial de desenvolvimento, SQLite permanece apenas como legado/fallback temporário e Playwright E2E é o padrão de Validação. Os dados locais atuais não são considerados dados reais, mas qualquer reset, Exclusão ou Recriação deve ser limitado a ambiente local/dev e nunca a produção, DigitalOcean ou banco remoto.

Nenhuma exposição web externa deve ocorrer sem Autenticação, proteção de APIs, `DEBUG=False`, `SECRET_KEY` segura, HTTPS e revisão de CORS.

## Configuração Inicial (Primeira vez)

### 1. Criar Ambiente Virtual

```bash
python -m venv venv
```

### 2. Ativar Ambiente Virtual

**Windows:**
```bash
venv\Scripts\activate
```

**Linux/Mac:**
```bash
source venv/bin/activate
```

### 3. Instalar Dependências

```bash
pip install -r requirements.txt
```

### 4. Configurar Banco de Desenvolvimento

Configure `.env.local` com `DATABASE_URL` apontando para o PostgreSQL local. O banco de desenvolvimento já deve existir localmente.

Exemplo mascarado:

```bash
DATABASE_URL=postgresql://controle_financeiro:***@localhost:5432/controle_financeiro_dev
```

Verifique a revision atual do Alembic quando precisar conferir o schema:

```bash
flask db current
```

### 5. Iniciar o Servidor

```bash
python backend/app.py
```

### 6. Abrir no Navegador

```
http://localhost:5000
```

---

## Uso Diário

### Iniciar o Projeto

```bash
# 1. Ativar ambiente virtual
venv\Scripts\activate

# 2. Iniciar servidor
python backend/app.py
```

### Parar o Servidor

Pressione `Ctrl + C` no terminal

---

## Banco de Dados Local

PostgreSQL local é o banco oficial de desenvolvimento. Qualquer operação de reset/recriação deve ser tratada em script próprio, com confirmação explícita de ambiente local/dev e sem apontar para DigitalOcean, produção ou banco remoto.

SQLite pode existir apenas como fallback/legado/teste temporário. Não use SQLite como referência principal de evolução de schema.

---

## Estrutura de Desenvolvimento

### Desenvolvimento Local
- PostgreSQL local é o banco oficial de desenvolvimento.
- SQLite local pode existir apenas como legado/fallback temporário.
- Dados locais de desenvolvimento são descartáveis, desde que a operação seja explicitamente local/dev.

### Evolução de Schema (a partir do DB-3C)

O Alembic é a fonte oficial de evolução de schema. Para qualquer alteração futura nos models:

```bash
# 1. Após alterar backend/models.py, gerar a migration
flask db migrate -m "descricao_da_alteracao"

# 2. Revisar o arquivo gerado em migrations/versions/

# 3. Aplicar no banco local
flask db upgrade

# 4. Para novos ambientes (ex: produção futura), apenas:
flask db upgrade  # aplica todas as migrations pendentes
```

**Não usar** scripts SQLite antigos. Eles foram arquivados em `migrations/legacy_sqlite/` e não fazem parte do fluxo oficial.
**Não usar** `backend/migrations/` antigo ou `migrations/*.py` custom para evolução de schema.
**Não usar** `scripts/debug/*.py` como migration; alguns são diagnósticos legados SQLite e permanecem apenas para referência manual.
**Não usar** `scripts/reset_db_dev_categorias_apenas.py` para evolução — apenas para reset total em dev.

### PostgreSQL local em desenvolvimento
- Para usar PostgreSQL local, crie o banco local manualmente e configure `DATABASE_URL` no `.env.local`.
- A URL de desenvolvimento deve apontar somente para `localhost`, `127.0.0.1` ou `::1`.
- Se `DATABASE_URL` não estiver definida, o projeto mantém SQLite como fallback temporário.
- Nunca use URL DigitalOcean, banco remoto ou dados reais em `development`.

### Produção Futura (DigitalOcean)
- PostgreSQL (servidor remoto)
- `DATABASE_URL` remoto somente em produção/web futura
- Dados reais
- Autenticação obrigatória
- `DEBUG=False`
- `SECRET_KEY` segura
- HTTPS obrigatório

---

## Verificar se está Funcionando

### 1. Health Check
Abra: `http://localhost:5000/health`

Deve retornar:
```json
{
  "status": "ok",
  "environment": "development",
  "database": "connected"
}
```

### 2. Dashboard
Abra: `http://localhost:5000`

Você verá a página inicial do sistema.

---

## Estado Atual (v1.1 — 2026-03)

O sistema está funcionalmente completo. Módulos ativos:
- Dashboard, Despesas, Receitas, Cartões, Lançamentos
- Financiamentos, Consórcios, Patrimônio, Veículos
- Contas Bancárias (em finalização — MVP 1)

Próximas melhorias planejadas: ver `docs/HISTORIA_DO_PROJETO.md`.

---

## Dicas Importantes

### ✅ Boas Práticas

1. **Sempre ative o ambiente virtual** antes de trabalhar
2. **Commit frequente** no Git
3. **Teste localmente** antes de pensar em produção
4. **Use dados locais descartáveis** para testar funcionalidades
5. **Use PostgreSQL local** em desenvolvimento com `.env.local` apontando para `localhost`

### ❌ Evite

1. Não suba o arquivo `gastos.db` para o Git (já está no `.gitignore`)
2. Não suba o arquivo `.env.local` para o Git (já está no `.gitignore`)
3. Não aponte desenvolvimento para banco remoto, DigitalOcean ou produção
4. Não execute operação destrutiva sem confirmar que o ambiente é local/dev

---

## Problemas Comuns

### Erro: "No module named flask"
**Solução:** Ative o ambiente virtual e instale as dependências
```bash
venv\Scripts\activate
pip install -r requirements.txt
```

### Erro: "Address already in use"
**Solução:** Outra instância do servidor está rodando. Feche-a ou mude a porta em `app.py`:
```python
app.run(port=5001)  # Trocar para outra porta
```

### Banco de dados não conecta
**Solução:** Se estiver usando PostgreSQL local, confirme que o serviço local está ativo, que `.env.local` aponta para `localhost` e que o banco `controle_financeiro_dev` existe. Nunca use URL DigitalOcean ou banco remoto em desenvolvimento.

```bash
flask db current
```

Se estiver usando SQLite fallback/legado, trate como exceção temporária e não como fluxo principal de desenvolvimento.

---

## Comandos Úteis

```bash
# Ver pacotes instalados
pip list

# Atualizar requirements.txt (se instalar novos pacotes)
pip freeze > requirements.txt

# Desativar ambiente virtual
deactivate

# Verificar versão do Python
python --version
```

---

## Suporte

Para problemas ou dúvidas, consulte:
- `README.md` — Filosofia do sistema
- `README_TECNICO.md` — Arquitetura e endpoints
- `docs/ARQUITETURA.md` — Módulos e entidades
- `docs/CONTRATO_FINAL_DO_SISTEMA.md` — Regras imutáveis
