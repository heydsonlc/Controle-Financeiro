# 🚀 Como Iniciar o Sistema

## Forma Mais Fácil (Recomendado)

**Dê um duplo-clique no arquivo:**
```
iniciar_servidor.bat
```

Isso vai:
1. Ativar o ambiente virtual automaticamente
2. Iniciar o servidor Flask
3. Abrir uma janela mostrando os logs

Depois, abra seu navegador em: **http://localhost:5000**

---

## Forma Manual (Terminal)

### 1. Abrir Terminal na Pasta do Projeto

Abra o CMD ou PowerShell e navegue até a pasta:
```bash
cd "c:\Users\heydson.cardoso\OneDrive\Kortex Brasil\Controle Financeiro"
```

### 2. Ativar Ambiente Virtual

```bash
venv\Scripts\activate
```

Você verá `(venv)` no início da linha.

### 3. Iniciar Servidor

```bash
python backend\app.py
```

### 4. Acessar no Navegador

Abra: **http://localhost:5000**

---

## Para Parar o Servidor

Pressione **Ctrl + C** no terminal onde o servidor está rodando.

---

## Resetar o Banco de Dados

Se quiser começar do zero com dados de exemplo:

```bash
# 1. Ativar ambiente virtual
venv\Scripts\activate

# 2. Deletar banco existente
del data\gastos.db

# 3. Recriar com dados de exemplo
python init_db.py --sample
```

---

## Arquivos Importantes

- **iniciar_servidor.bat** - Duplo-clique para iniciar
- **data/gastos.db** - Banco de dados SQLite
- **backend/app.py** - Aplicação principal
- **backend/models.py** - Modelos do banco (14 tabelas)

---

## Problemas Comuns

### Erro: "python não é reconhecido"
**Solução:** Certifique-se que o Python está instalado e no PATH

### Erro: "No module named flask"
**Solução:**
```bash
venv\Scripts\activate
pip install -r requirements-dev.txt
```

### Porta 5000 já está em uso
**Solução:** Outro programa está usando a porta. Feche-o ou mude a porta em `backend/app.py`

---

## Status Atual

✅ Ambiente virtual criado
✅ Dependências instaladas
✅ Banco de dados com dados de exemplo
✅ Servidor pronto para usar

**Próximos passos:** Desenvolver as rotas da API e interface do usuário.
