# Guia de Início Rápido

## Nota de Direção Técnica

Este guia descreve o fluxo local atual. A direção documentada para os próximos MVPs é evoluir o desenvolvimento para PostgreSQL local, manter SQLite apenas como legado/fallback temporário e adotar Playwright E2E como padrão de Validação. Os dados locais atuais não são considerados dados reais e podem ser recriados durante desenvolvimento, mas qualquer reset, Exclusão ou Recriação deve ser limitado a ambiente local/dev e nunca a produção, DigitalOcean ou banco remoto.

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

### 4. Inicializar Banco de Dados

**Com dados de exemplo (recomendado para testar):**
```bash
python init_db.py --sample
```

**Ou sem dados:**
```bash
python init_db.py
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

## Resetar o Banco de Dados

Se quiser começar do zero em ambiente local/dev, confirme visualmente que o banco é local e que não há dados reais. Esta orientação não se aplica a produção, DigitalOcean, banco remoto ou qualquer `DATABASE_URL` externa.

```bash
# 1. Deletar o banco existente
del data\gastos.db

# 2. Recriar com dados de exemplo
python init_db.py --sample
```

---

## Estrutura de Desenvolvimento

### Desenvolvimento Local
- Fluxo atual ainda pode usar SQLite local como legado/fallback temporário.
- A direção dos próximos MVPs é PostgreSQL local como banco oficial de desenvolvimento.
- Dados locais de desenvolvimento são descartáveis, desde que a operação seja explicitamente local/dev.

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
4. **Use dados de exemplo** (`--sample`) para testar funcionalidades
5. **Use PostgreSQL local** em desenvolvimento quando `.env.local` tiver `DATABASE_URL` apontando para `localhost`

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

### Banco de dados não cria
**Solução:** Se estiver usando SQLite fallback, certifique-se de que a pasta `data/` existe:
```bash
mkdir data
python init_db.py --sample
```

Se estiver usando PostgreSQL local, confirme que o servico local esta ativo, que `.env.local` aponta para `localhost` e que o banco `controle_financeiro_dev` existe. Nunca use URL DigitalOcean ou banco remoto em desenvolvimento.

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
