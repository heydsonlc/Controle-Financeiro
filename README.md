# Controle-Financeiro
Controle de Gastos Pessoal que gerencia as despesas com previsão e realização destas. 
### Documento de Arquitetura e Lógica: Sistema de Controle de Gastos

#### 1. Visão Geral do Projeto

O objetivo é criar um sistema de controle financeiro local (via navegador) que espelhe e substitua a lógica avançada da sua planilha Excel. O núcleo do sistema é a distinção entre **Projeção (Orçamento)** e **Execução (Real/Pago)**, permitindo uma visão precisa do custo total do mês, mesmo com despesas ainda não pagas.

O sistema deve gerenciar o ciclo financeiro completo:
1.  **Ganhar:** Registro de receitas (Fixas e Eventuais).
2.  **Planejar (Orçar):** Definição de projeções de gastos (Lançamento em Lote, Orçamento do Cartão).
3.  **Executar (Gastar):** Registro de contas a pagar, faturas de cartão e baixa de pagamentos.
4.  **Guardar (Alocar):** Transferência do saldo (Receitas - Despesas) para "Caixinhas" de patrimônio.

#### 2. Tecnologias Utilizadas (A Stack)

* **Linguagem (Backend):** Python
* **Servidor Web (API):** Flask
* **Banco de Dados (Desenvolvimento Local):** SQLite (um único arquivo `gastos.db`)
* **Banco de Dados (Produção):** PostgreSQL (no seu servidor DigitalOcean)
* **Interface (Frontend):** HTML, CSS e JavaScript básicos (servidos pelo Flask)
* **Comunicação com BD (ORM):** Flask-SQLAlchemy (permite alternar entre SQLite e PostgreSQL sem mudar o código principal)

#### 3. Lógica da Aplicação (As Regras de Negócio)

Esta é a "Fase 1", o cérebro do sistema.

1.  **Lógica Central (Projeção x Real):** A tela principal (dashboard) terá uma coluna "Projeção" que é a mais importante.
    * **Para despesas simples (boletos):** A Projeção será o valor da `Conta` registrada (mesmo que pendente). Se nenhuma conta foi registrada para o item, a Projeção assume o valor do `Orçamento` (plano).
    * **Para despesas agregadoras (cartão):** A Projeção será a soma do `OrçamentoAgregado` (a soma dos tetos de gasto definidos para o cartão, ex: Supermercado + Farmácia).

2.  **Lançamento em Lote:** O sistema permitirá lançar projeções de despesas (`Orcamento`) e receitas (`ReceitaOrcamento`) para múltiplos meses futuros de uma só vez (ex: "Aluguel = R$ 3000, de Jan/25 a Dez/25").

3.  **Lançamento Parcelado (Compromissos):**
    * **Despesa Simples (Boleto):** O lançamento de um parcelamento (ex: "Dentista R$ 900 em 3x") irá **atualizar** o `Orcamento` dos meses correspondentes, substituindo o plano por um compromisso.
    * **Despesa Agregadora (Cartão):** O lançamento de uma compra parcelada (ex: "TV R$ 3000 em 3x") criará 3 registros na `LancamentoAgregado`, um para cada fatura futura.

4.  **Guia de Contas a Pagar:** O sistema funcionará como um "contas a pagar". A tabela `Conta` armazenará todos os boletos e faturas, incluindo `data_vencimento`, `status_pagamento` (Pendente/Pago) e `debito_automatico`. Isso permite "dar baixa" nos pagamentos.

5.  **Receitas (Fixa vs. Eventual):** As receitas são classificadas como 'Fixa' (ex: Salário) ou 'Eventual' (ex: Comissão), permitindo flexibilidade no planejamento e análise do saldo.

6.  **Ciclo do Cartão de Crédito:** O sistema lida com a complexidade do fechamento da fatura. Cada cartão (`ConfigAgregador`) terá um `dia_fechamento` e `dia_vencimento`. Ao lançar um gasto (`LancamentoAgregado`), o sistema usa a `data_compra` para calcular automaticamente para qual `mes_fatura` aquele gasto será alocado.

7.  **Orçamento do Cartão (Abatimento):** O cartão funciona como um mini-orçamento. Você define tetos de gasto (`OrcamentoAgregado`) para sub-itens (ex: "Supermercado = R$ 1000"). Cada gasto real (`LancamentoAgregado`) é abatido desse teto, mostrando o saldo disponível para gastar naquele sub-item.

8.  **Automação (Consórcio):** O sistema terá um módulo para "Contratos" (`ContratoConsorcio`). Ao preencher os dados (valor inicial, correção, parcelas, mês contemplado), o sistema **gera automaticamente** todas as `Conta` (boletos) futuras e a `ReceitaOrcamento` (prêmio) de uma só vez.

9.  **Caixinhas (Patrimônio):** O sistema gerencia o patrimônio. O "saldo" (Receitas - Despesas) não desaparece; ele fica em uma `ContaPatrimonio` (ex: "Conta Corrente"). O usuário pode então realizar `Transferencia` desse valor para outras contas (ex: "Reserva Emergência", "Viagem").

#### 4. Estrutura do Banco de Dados (As 14 Tabelas)

Este é o `models.py` que define a estrutura de dados completa.

**Módulo 1: Orçamento (Receitas e Despesas)**
1.  `Categoria`: Agrupador de despesas (ex: "Moradia").
2.  `ItemDespesa`: O item de gasto (ex: "Aluguel", "Cartão VISA"). Possui um `tipo` ('Simples' ou 'Agregador').
3.  `ConfigAgregador`: Armazena as regras do cartão (item 'Agregador'), como `dia_fechamento` e `dia_vencimento`.
4.  `Orcamento`: O **plano** mensal para itens 'Simples' (ex: {Aluguel, 11/2025, R$ 3000}).
5.  `Conta`: O "Contas a Pagar". Armazena boletos e faturas de itens 'Simples', com vencimento, status, etc.
6.  `ItemAgregado`: Os sub-itens de um 'Agregador' (ex: "Supermercado", "Farmácia", vinculados ao "Cartão VISA").
7.  `OrcamentoAgregado`: O **plano/teto** de gastos para os sub-itens do cartão (ex: {Supermercado, 11/2025, R$ 1000}).
8.  `LancamentoAgregado`: O **gasto real** no cartão (ex: {Compra Assaí, R$ 500, data: 15/11/25}).
9.  `ItemReceita`: A fonte da receita (ex: "Salário", "Comissão"), com `tipo` ('Fixa' ou 'Eventual').
10. `ReceitaOrcamento`: O **plano** mensal de receitas (ex: {Salário, 11/2025, R$ 27000}).
11. `ReceitaRealizada`: O **recebimento real** ("baixa") da receita (ex: {Salário, 05/11/2025, R$ 27000}).

**Módulo 2: Automação**
12. `ContratoConsorcio`: Armazena as regras do contrato (valor, correção, parcelas, prêmio) que gera automaticamente `Conta` e `ReceitaOrcamento`.

**Módulo 3: Patrimônio (Caixinhas)**
13. `ContaPatrimonio`: As "caixinhas" onde o dinheiro fica (ex: "Conta Corrente", "Reserva Emergência").
14. `Transferencia`: O registro de movimentação de dinheiro entre as `ContaPatrimonio`.

#### 5. Passo a Passo da Implementação (Fase 3)

Este é o roteiro para construir o sistema.

1.  **Configuração do Ambiente Local:**
    * Criar a pasta do projeto (ex: `meus_gastos`).
    * Configurar o ambiente virtual Python (`venv`).
    * Instalar `Flask` e `Flask-SQLAlchemy`.

2.  **Criação dos Modelos e Servidor:**
    * Criar o arquivo `models.py` (com as 14 tabelas, conforme código já fornecido).
    * Criar o arquivo `app.py` (com a configuração do Flask e do BD SQLite, conforme código já fornecido).
    * Executar `python app.py` para criar o arquivo `gastos.db` e iniciar o servidor.

3.  **Desenvolvimento do Backend (API):**
    * Criar rotas no `app.py` para as funções básicas (CRUD - Criar, Ler, Atualizar, Deletar).
    * **Prioridade 1:** CRUD de `Categoria` e `ItemDespesa` (A configuração inicial).
    * **Prioridade 2:** CRUD de `ItemReceita`.
    * **Prioridade 3:** Lógica de Lançamentos (Contas, Orçamento, Receitas).
    * **Prioridade 4:** Lógica do Dashboard (A tela principal que consolida tudo).

4.  **Desenvolvimento do Frontend (Interface):**
    * Criar uma pasta `templates` no projeto.
    * Criar arquivos HTML básicos para cada tela (ex: `index.html`, `contas.html`, `cartao.html`).
    * Usar JavaScript (Fetch API) para se comunicar com o Backend (rotas do `app.py`) e exibir os dados nas tabelas.

5.  **Testes e Refinamento:**
    * Usar o sistema localmente, cadastrando dados reais e validando se a lógica do Dashboard bate com a sua planilha.

6.  **Migração para Produção (DigitalOcean):**
    * Quando o sistema estiver 100% funcional localmente.
    * Configurar o `app.py` para apontar para o seu banco de dados PostgreSQL (mudar a linha `app.config['SQLALCHEMY_DATABASE_URI']`).
    * Instalar a biblioteca `psycopg2-binary` (`pip install psycopg2-binary`).
    * Hospedar a aplicação Flask no seu servidor DigitalOcean.
