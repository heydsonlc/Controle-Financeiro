# BASE-REAL-1B - Seed inicial de categorias e palavras-chave

Este seed popula a base limpa com:

- Categorias de Despesa globais;
- palavras-chave globais vinculadas a Categoria de Despesa;
- Categorias do Cartao apenas no perfil `Pessoal`;
- vinculos Categoria de Despesa -> Categoria do Cartao no perfil `Pessoal`.

O perfil `Empresa` permanece sem Categorias do Cartao criadas pelo seed.

## Comando

```powershell
.\venv\Scripts\python.exe scripts\seed\base_real_1b_seed_categorias.py
```

## Regras

- idempotente;
- nao apaga dados;
- reaproveita categorias existentes;
- reativa palavras-chave existentes quando necessario;
- nao cria Categoria do Cartao para o perfil `Empresa`;
- bloqueia banco remoto por seguranca.

## Validacoes esperadas

Depois da execucao:

- Categorias de Despesa aparecem em `Pessoal` e `Empresa`;
- Categorias do Cartao aparecem apenas no `Pessoal`;
- palavras-chave classificam documentos/importacoes de forma global;
- vinculos de cartao funcionam apenas no perfil `Pessoal`.
