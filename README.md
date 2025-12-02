# 💰 Sistema de Controle Financeiro

Sistema completo de controle de gastos financeiros desenvolvido com Flask e SQLite, preparado para migração futura para PostgreSQL.

## 📋 Índice

- [Visão Geral](#visão-geral)
- [Funcionalidades](#funcionalidades)
- [Arquitetura](#arquitetura)
- [Instalação](#instalação)
- [Uso](#uso)
- [Estrutura do Projeto](#estrutura-do-projeto)
- [Migração para Produção](#migração-para-produção)

---

## 🎯 Visão Geral

O sistema implementa a lógica completa de controle financeiro com distinção entre **Projeção (Orçamento)** e **Execução (Real/Pago)**, cobrindo todo o ciclo financeiro:

1. **Ganhar** - Registro de receitas (Fixas e Eventuais)
2. **Planejar** - Definição de projeções de gastos
3. **Executar** - Registro de contas a pagar e baixa de pagamentos
4. **Guardar** - Alocação do saldo em caixinhas de patrimônio

---

## 🆕 Últimas Implementações

### Módulo de Receitas Completo (Dezembro 2024)
Implementação expandida do sistema de receitas com classificação detalhada e análises avançadas:

**Backend:**
- Modelo `ItemReceita` expandido com novos campos:
  - Tipos detalhados: `SALARIO_FIXO`, `GRATIFICACAO`, `RENDA_EXTRA`, `ALUGUEL`, `RENDIMENTO_FINANCEIRO`, `OUTROS`
  - Campos de configuração: `valor_base_mensal`, `dia_previsto_pagamento`, `conta_origem_id`
- Modelo `ReceitaOrcamento` com campo `periodicidade`:
  - `MENSAL_FIXA`: Receitas fixas (salários, gratificações)
  - `EVENTUAL`: Receitas esporádicas
  - `UNICA`: Receita única
- Modelo `ReceitaRealizada` enriquecido:
  - Campo `competencia` para mês de referência
  - Vinculação com `orcamento_id` para comparação
  - Campo `conta_origem_id` para rastreabilidade
  - Timestamps automáticos (`criado_em`, `atualizado_em`)
- **Serviço ReceitaService** completo em [receita_service.py](backend/services/receita_service.py):
  - CRUD de fontes de receita
  - Geração de orçamentos recorrentes (automático para 12, 24, 36 meses)
  - Registro de receitas realizadas com vinculação automática ao orçamento
  - KPIs e análises:
    - Resumo mensal consolidado (previsto vs realizado)
    - Confiabilidade por fonte (% recebido / previsto)
    - Detalhe mês a mês por item

**Regras de Negócio:**
- Salários e gratificações podem ter orçamentos gerados automaticamente para múltiplos meses
- Rendas extras podem ser eventuais ou únicas
- Comparação automática entre valor previsto e realizado
- Cálculo de confiabilidade das projeções

### Sistema de Consórcios (Dezembro 2024)
Implementação completa do módulo de automação de consórcios com as seguintes características:

**Backend:**
- Modelo `ContratoConsorcio` estendido com campos `tipo_reajuste` e `valor_reajuste`
- API REST completa em [consorcios.py](backend/routes/consorcios.py)
- Geração automática de parcelas com 3 modalidades de reajuste:
  - **Sem reajuste:** Valor fixo em todas as parcelas
  - **Reajuste percentual:** Aplicação progressiva com juros compostos
  - **Reajuste fixo:** Incremento linear a cada parcela
- Geração automática de receita no mês de contemplação
- Endpoint `/regenerar-parcelas` para recalcular parcelas após alterações

**Frontend:**
- Checkbox "É um Consórcio" integrado ao modal de despesas
- Formulário condicional com campos específicos:
  - Número de parcelas e mês de início
  - Tipo e valor de reajuste
  - Mês de contemplação e valor do prêmio
- Interface responsiva com validação de campos

**Regras de Negócio:**
- Parcelas identificadas com `tipo='Consorcio'` no banco
- Data de vencimento automática (dia 5 de cada mês)
- Vinculação automática entre contrato, despesas e receitas
- Soft delete (inativação em vez de exclusão física)

### Rastreamento de Pagamentos (Dezembro 2024)
Sistema de acompanhamento de divergências entre valores projetados e realizados:

**Funcionalidades:**
- Modal minimalista para registro de pagamentos
- Comparação automática: Valor Previsto vs Valor Pago
- Histórico de divergências para análise financeira
- Interface integrada ao fluxo de execução de contas

**Objetivo:**
Permite identificar economias ou gastos extras em relação ao planejado, facilitando ajustes no orçamento futuro.

---

## ✨ Funcionalidades

### Módulo 1: Orçamento (Receitas e Despesas)
- ✅ Gestão de categorias e itens de despesa
- ✅ Suporte a despesas simples (boletos) e agregadoras (cartões)
- ✅ Orçamento mensal com projeções
- ✅ Contas a pagar com controle de vencimento e status
- ✅ **Rastreamento de Pagamentos (Previsto vs Realizado)**
  - Modal minimalista para registro de pagamentos
  - Comparação entre valor previsto e valor efetivamente pago
  - Histórico de divergências entre projeção e execução
- ✅ Gestão de cartão de crédito com ciclo de faturamento
- ✅ Lançamentos em lote para múltiplos meses
- ✅ Parcelamentos automáticos
- ✅ Controle de receitas fixas e eventuais

### Módulo 2: Automação
- ✅ **Sistema Completo de Consórcios**
  - Cadastro de contratos com valor inicial e número de parcelas
  - Definição de mês de início e contemplação
  - **Reajuste Inteligente de Parcelas:**
    - Sem reajuste (valor fixo)
    - Reajuste percentual (aplicado progressivamente)
    - Reajuste por valor fixo (incremento linear)
  - **Geração Automática:**
    - Parcelas mensais como despesas (ItemDespesa)
    - Receita de contemplação automática no mês definido
  - Interface integrada no modal de despesas
  - Endpoint de regeneração de parcelas

### Módulo 3: Patrimônio
- ✅ Caixinhas para alocação de patrimônio
- ✅ Transferências entre contas

---

## 🏗️ Arquitetura

### Stack Tecnológica

**Backend:**
- Python 3.8+
- Flask (Framework web)
- SQLAlchemy (ORM)
- Flask-Migrate (Migrations)

**Banco de Dados:**
- **Desenvolvimento:** SQLite (local, arquivo `data/gastos.db`)
- **Produção:** PostgreSQL (DigitalOcean)

**Frontend:**
- HTML5 + CSS3
- JavaScript (Vanilla)

### Estrutura do Banco de Dados

**14 Tabelas organizadas em 3 módulos:**

**Orçamento (11 tabelas):**
1. `categoria` - Agrupador de despesas
2. `item_despesa` - Itens de gasto (Simples ou Agregador)
3. `config_agregador` - Configuração de cartões
4. `orcamento` - Plano mensal para itens simples
5. `conta` - Contas a pagar
6. `item_agregado` - Sub-itens de cartões
7. `orcamento_agregado` - Tetos de gasto do cartão
8. `lancamento_agregado` - Gastos reais no cartão
9. `item_receita` - Fontes de receita
10. `receita_orcamento` - Plano mensal de receitas
11. `receita_realizada` - Receitas efetivamente recebidas

**Automação (1 tabela):**
12. `contrato_consorcio` - Contratos que geram lançamentos automáticos
    - Campos de reajuste: `tipo_reajuste` (nenhum/percentual/fixo), `valor_reajuste`
    - Geração automática de parcelas (ItemDespesa) e contemplação (ReceitaRealizada)

**Patrimônio (2 tabelas):**
13. `conta_patrimonio` - Caixinhas de patrimônio
14. `transferencia` - Movimentações entre caixinhas

---

## 🚀 Instalação

### Pré-requisitos

- Python 3.8 ou superior
- pip (gerenciador de pacotes Python)

### Passo 1: Clonar/Baixar o Projeto

```bash
cd "c:\Users\heydson.cardoso\OneDrive\Kortex Brasil\Controle Financeiro"
```

### Passo 2: Criar Ambiente Virtual

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/Mac
python3 -m venv venv
source venv/bin/activate
```

### Passo 3: Instalar Dependências

```bash
pip install -r requirements.txt
```

### Passo 4: Inicializar o Banco de Dados

```bash
# Apenas criar as tabelas
python init_db.py

# Criar tabelas + dados de exemplo
python init_db.py --sample
```

---

## 💻 Uso

### Iniciar o Servidor de Desenvolvimento

```bash
python backend/app.py
```

O servidor estará disponível em: `http://localhost:5000`

### Verificar Status da Aplicação

Acesse: `http://localhost:5000/health`

Deve retornar:
```json
{
  "status": "ok",
  "environment": "development",
  "database": "connected"
}
```

### Acessar o Dashboard

Abra no navegador: `http://localhost:5000`

---

## 📁 Estrutura do Projeto

```
controle-financeiro/
├── backend/                    # Backend da aplicação
│   ├── app.py                 # Aplicação Flask principal
│   ├── config.py              # Configurações por ambiente
│   ├── models.py              # Modelos do banco (14 tabelas)
│   ├── routes/                # Rotas da API
│   │   ├── __init__.py
│   │   ├── categorias.py     # ✅ CRUD de categorias
│   │   ├── despesas.py       # ✅ CRUD de despesas
│   │   ├── cartoes.py        # ✅ Gestão de cartões
│   │   ├── consorcios.py     # ✅ Sistema de consórcios
│   │   ├── receitas.py
│   │   ├── patrimonio.py
│   │   └── dashboard.py
│   ├── services/              # Lógica de negócio
│   │   ├── __init__.py
│   │   ├── orcamento_service.py
│   │   ├── cartao_service.py
│   │   └── consorcio_service.py
│   └── utils/                 # Utilitários
│       └── __init__.py
│
├── frontend/                   # Frontend da aplicação
│   ├── static/
│   │   ├── css/
│   │   │   └── style.css
│   │   ├── js/
│   │   │   └── app.js
│   │   └── img/
│   └── templates/
│       └── index.html
│
├── data/                       # Banco de dados SQLite
│   └── gastos.db              # (criado automaticamente)
│
├── tests/                      # Testes unitários
│
├── init_db.py                 # Script de inicialização do BD
├── requirements.txt           # Dependências Python
├── .env.local                 # Config de desenvolvimento
├── .env.example               # Template de configuração
├── .gitignore                 # Arquivos ignorados pelo Git
└── README.md                  # Este arquivo
```

---

## 🔄 Próximos Passos de Desenvolvimento

### Fase 1: API Backend (CRUD Básico) ✅
1. ✅ Estrutura base criada
2. ✅ Rotas de Categorias implementadas
3. ✅ Rotas de Itens de Despesa implementadas
4. ✅ Rotas de Cartões de Crédito implementadas
5. ✅ **Rotas de Consórcios implementadas**
6. ✅ **Rotas de Receitas implementadas** (15 endpoints completos)
7. ⏳ Implementar rotas de Patrimônio

### Fase 2: Lógica de Negócio 🔄
1. ✅ **Sistema de Consórcios (geração automática de parcelas e contemplação)**
2. ✅ **Rastreamento de Pagamentos (Previsto vs Realizado)**
3. ✅ **Serviço de Receitas completo** (ItemReceita, Orçamento, Realizadas, KPIs)
4. ⏳ Serviço de Orçamento (lançamento em lote)
5. ⏳ Serviço de Cartão (ciclo de faturamento completo)
6. ⏳ Serviço de Parcelamentos
7. ⏳ Serviço de Dashboard (Projeção vs Real completo)

### Fase 3: Frontend
1. ✅ **Modal de Nova Despesa com suporte a Consórcios**
2. ✅ **Modal minimalista de Rastreamento de Pagamentos**
3. ⏳ Interface do Dashboard principal
4. ⏳ Visualizações e gráficos de análise
5. ⏳ Interface de gerenciamento de consórcios cadastrados
6. ⏳ Tabelas interativas com filtros

### Fase 4: Funcionalidades Avançadas
1. ✅ **Automação de consórcios com reajuste inteligente**
2. ⏳ Relatórios e exportações (PDF/Excel)
3. ⏳ Gráficos de análise financeira
4. ⏳ Notificações de vencimento
5. ⏳ Comparativo mensal (tendências)

---

## 🎨 Como o Sistema Ficará

### Visão do Dashboard Completo

O sistema está sendo construído seguindo uma arquitetura modular com foco na experiência do usuário:

#### Layout Principal (3 Colunas Responsivas)

**Coluna "Planejar"** - Projeções e Orçamento
- Widgets para lançamento de orçamentos em lote
- Tabelas com categorias mostrando: Projeção, Real e Desvio
- Cartões especiais para cada cartão de crédito com barras de progresso
- Indicadores coloridos (cinza=projeção, verde/laranja=real)

**Coluna "Executar"** - Contas a Pagar e Pagamentos
- Lista Kanban com status: Pendente, Pago, Débito Automático
- Destaque visual para vencimentos próximos
- Sistema de rastreamento de pagamentos (previsto vs realizado)
- Widget de parcelamentos com evolução visual
- Gestão integrada de consórcios com cronograma de parcelas

**Coluna "Guardar"** - Patrimônio
- Grid de caixinhas com saldo atual e metas
- Função de transferência entre contas
- Histórico de movimentações

#### Painel de Receitas
- Cards separados: Fixas vs Eventuais
- Timeline de projeções vs realizações
- Indicador de confiabilidade (% recebido vs projetado)
- Badges de classificação

#### Seção de Automação (Consórcios)
- Cartões expandíveis por contrato
- Cronograma visual com barras de progresso
- Parcelas pagas vs pendentes
- Destaque para contemplação e valor do prêmio
- Badge "Automação ativa"

### Identidade Visual

**Paleta de Cores:**
- Background: tons sóbrios de cinza-azulado
- Verde: saldo positivo, concluído
- Laranja: pendente, atenção
- Vermelho: atrasado, urgente

**Tipografia:**
- Fonte geométrica moderna (Inter ou Poppins)
- Pesos variados para hierarquia visual

**Interatividade:**
- Hover effects e microinterações
- Skeleton loaders durante carregamento
- Tooltips informativos
- Gráficos Sparkline para evolução mensal

### Navegação

**Menu Lateral Retrátil:**
- Dashboard
- Cartões
- Receitas
- Patrimônio
- Automação (Consórcios)

**Filtros Globais:**
- Seleção de mês/período
- Filtro por carteira
- Filtro por cartão
- Atualização simultânea de todos os painéis

### Fluxo de Uso

1. **Ganhar:** Usuário registra receitas fixas e eventuais
2. **Planejar:** Define orçamentos mensais, configura consórcios
3. **Executar:** Registra pagamentos, compara previsto vs real
4. **Guardar:** Aloca saldos positivos em caixinhas de patrimônio
5. **Analisar:** Dashboard consolida tudo com gráficos e tendências

---

## 🌐 Migração para Produção (PostgreSQL)

### Quando o sistema estiver completo localmente:

### 1. Configurar Variáveis de Ambiente

Criar arquivo `.env.production`:

```bash
FLASK_ENV=production
SECRET_KEY=sua-chave-secreta-super-segura
DATABASE_URL=postgresql://usuario:senha@host:porta/nome_banco
FLASK_APP=backend/app.py
FLASK_DEBUG=0
```

### 2. Instalar Driver PostgreSQL

```bash
pip install psycopg2-binary
```

### 3. Executar Migrations

```bash
# Inicializar migrations (primeira vez)
flask db init

# Criar migration
flask db migrate -m "Initial migration"

# Aplicar no PostgreSQL
FLASK_ENV=production flask db upgrade
```

### 4. Deploy no DigitalOcean

O código **não precisa ser alterado**! O SQLAlchemy abstrai a diferença entre SQLite e PostgreSQL.

Apenas:
1. Configure as variáveis de ambiente
2. Execute as migrations
3. Inicie a aplicação

---

## 📝 Comandos Úteis

```bash
# Ativar ambiente virtual
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# Instalar dependências
pip install -r requirements.txt

# Inicializar banco (limpo)
python init_db.py

# Inicializar banco (com dados de exemplo)
python init_db.py --sample

# Iniciar servidor de desenvolvimento
python backend/app.py

# Criar migration
flask db migrate -m "Descrição da mudança"

# Aplicar migration
flask db upgrade

# Reverter migration
flask db downgrade

# Executar testes
pytest
```

---

## 🔧 Desenvolvimento Local vs Produção

| Aspecto | Desenvolvimento (Local) | Produção (DigitalOcean) |
|---------|------------------------|-------------------------|
| Banco de Dados | SQLite (`data/gastos.db`) | PostgreSQL |
| Debug | Ativado | Desativado |
| Arquivo Config | `.env.local` | `.env.production` |
| Alteração de Código | **Nenhuma!** | **Nenhuma!** |

**A mudança é apenas de CONFIGURAÇÃO, não de CÓDIGO!**

---

## 📡 APIs Disponíveis

### Categorias
- `GET /api/categorias` - Listar todas
- `POST /api/categorias` - Criar nova
- `PUT /api/categorias/:id` - Atualizar
- `DELETE /api/categorias/:id` - Excluir

### Despesas
- `GET /api/despesas` - Listar todas
- `GET /api/despesas/:id` - Obter por ID
- `POST /api/despesas` - Criar nova
- `PUT /api/despesas/:id` - Atualizar
- `DELETE /api/despesas/:id` - Excluir

### Cartões de Crédito
- `GET /api/cartoes` - Listar todos
- `GET /api/cartoes/:id` - Obter por ID
- `POST /api/cartoes` - Criar novo
- `PUT /api/cartoes/:id` - Atualizar
- `DELETE /api/cartoes/:id` - Excluir

### Consórcios
- `GET /api/consorcios` - Listar todos
- `GET /api/consorcios/:id` - Obter por ID
- `POST /api/consorcios` - Criar e gerar parcelas automaticamente
- `PUT /api/consorcios/:id` - Atualizar
- `DELETE /api/consorcios/:id` - Inativar (soft delete)
- `POST /api/consorcios/:id/regenerar-parcelas` - Regenerar parcelas

**Exemplo de criação de consórcio:**
```json
POST /api/consorcios
{
  "nome": "Consórcio Imóvel",
  "valor_inicial": 200000.00,
  "numero_parcelas": 120,
  "mes_inicio": "2025-01-01",
  "tipo_reajuste": "percentual",
  "valor_reajuste": 0.5,
  "mes_contemplacao": "2027-06-01",
  "valor_premio": 180000.00,
  "item_despesa_id": 1,
  "item_receita_id": 2
}
```

### Receitas (Novo!)

**Fontes de Receita:**
- `GET /api/receitas/itens` - Listar fontes
- `GET /api/receitas/itens/:id` - Obter fonte específica
- `POST /api/receitas/itens` - Criar fonte
- `PUT /api/receitas/itens/:id` - Atualizar fonte
- `DELETE /api/receitas/itens/:id` - Inativar fonte

**Orçamento de Receitas:**
- `GET /api/receitas/orcamento?ano=2025` - Listar orçamentos do ano
- `POST /api/receitas/orcamento` - Criar/atualizar orçamento mensal
- `POST /api/receitas/orcamento/gerar-recorrente` - Gerar orçamentos para múltiplos meses

**Receitas Realizadas:**
- `GET /api/receitas/realizadas?ano_mes=2025-05` - Listar receitas do mês
- `GET /api/receitas/realizadas/:id` - Obter receita específica
- `POST /api/receitas/realizadas` - Registrar recebimento
- `DELETE /api/receitas/realizadas/:id` - Deletar receita

**Relatórios:**
- `GET /api/receitas/resumo-mensal?ano=2025` - Resumo consolidado por mês
- `GET /api/receitas/confiabilidade?ano_mes_ini=2025-01&ano_mes_fim=2025-12` - % confiabilidade
- `GET /api/receitas/itens/:id/detalhe?ano=2025` - Detalhe mês a mês de uma fonte

**Exemplo de criação de fonte de receita:**
```json
POST /api/receitas/itens
{
  "nome": "Salário PMGO",
  "tipo": "SALARIO_FIXO",
  "descricao": "Salário mensal da prefeitura",
  "valor_base_mensal": 8500.00,
  "dia_previsto_pagamento": 5,
  "conta_origem_id": 1
}
```

**Exemplo de geração de orçamentos recorrentes:**
```json
POST /api/receitas/orcamento/gerar-recorrente
{
  "item_receita_id": 1,
  "data_inicio": "2025-01-01",
  "data_fim": "2025-12-01",
  "valor_mensal": 8500.00,
  "periodicidade": "MENSAL_FIXA"
}
```

**Exemplo de registro de receita realizada:**
```json
POST /api/receitas/realizadas
{
  "item_receita_id": 1,
  "data_recebimento": "2025-05-06",
  "valor_recebido": 8500.00,
  "competencia": "2025-05-01",
  "descricao": "Salário Maio/2025",
  "conta_origem_id": 1
}
```

---

## 📚 Referências

- [Documentação Flask](https://flask.palletsprojects.com/)
- [SQLAlchemy ORM](https://docs.sqlalchemy.org/)
- [Flask-Migrate](https://flask-migrate.readthedocs.io/)

---

## 👨‍💻 Desenvolvimento

**Status:** Em desenvolvimento ativo

**Prioridade atual:**
- ✅ Sistema de Consórcios implementado
- ✅ Rastreamento de Pagamentos implementado
- ✅ **Módulo de Receitas Completo implementado**
- 🔄 Finalização do JavaScript do frontend de receitas
- ⏳ Implementação do dashboard principal
- ⏳ Integração de receitas com o dashboard

---

## 📄 Licença

Uso interno - Kortex Brasil
