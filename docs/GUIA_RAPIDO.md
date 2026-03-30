# Guia de Início Rápido

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

Se quiser começar do zero:

```bash
# 1. Deletar o banco existente
del data\gastos.db

# 2. Recriar com dados de exemplo
python init_db.py --sample
```

---

## Estrutura de Desenvolvimento

### Desenvolvimento Local (Atual)
- ✅ SQLite (arquivo local)
- ✅ Não precisa de servidor de banco
- ✅ Tudo funciona offline
- ✅ Perfeito para desenvolvimento

### Produção Futura (DigitalOcean)
- PostgreSQL (servidor remoto)
- **Migração:** Apenas alterar variável de ambiente
- **Código:** Permanece exatamente o mesmo

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

### ❌ Evite

1. Não suba o arquivo `gastos.db` para o Git (já está no `.gitignore`)
2. Não suba o arquivo `.env.local` para o Git (já está no `.gitignore`)
3. Não se preocupe com PostgreSQL agora (foque no desenvolvimento local)

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
**Solução:** Certifique-se de que a pasta `data/` existe:
```bash
mkdir data
python init_db.py --sample
```

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
