# 💰 Sistema de Controle Financeiro

Sistema completo de controle de gastos financeiros desenvolvido com Flask, SQLAlchemy e PostgreSQL local como banco oficial de desenvolvimento. SQLite permanece apenas como fallback/legado/teste temporário, e Alembic/Flask-Migrate é a fonte oficial de evolução de schema.

## 📋 Índice

- [Visão Geral](#visão-geral)
- [Funcionalidades](#funcionalidades)
- [Arquitetura](#arquitetura)
- [Instalação](#instalação)
- [Uso](#uso)
- [Estrutura do Projeto](#estrutura-do-projeto)
- [Produção Futura](#produção-futura-postgresql)

---

## 🎯 Visão Geral

O sistema implementa a lógica completa de controle financeiro com distinção entre **Projeção (Orçamento)** e **Execução (Real/Pago)**, cobrindo todo o ciclo financeiro:

1. **Ganhar** - Registro de receitas (Fixas e Eventuais)
2. **Planejar** - Definição de projeções de gastos
3. **Executar** - Registro de contas a pagar e baixa de pagamentos
4. **Guardar** - Alocação do saldo em caixinhas de patrimônio

---

## 🆕 Últimas Implementações

### Sistema de Receitas com Lógica de Confirmação (Dezembro 2024)
Implementação da lógica de priorização entre valores confirmados e previstos:

**Arquitetura de Competência:**
- Sistema baseado em **mês de competência** (não data de vencimento/pagamento)
- Campo `mes_referencia` usado em todas as tabelas principais
- Sincronização entre ReceitaOrcamento (previsto) e ReceitaRealizada (confirmado)

**Lógica de Cálculo no Dashboard ([dashboard.py](backend/routes/dashboard.py) linhas 51-82):**
1. **Buscar IDs de orçamentos já confirmados** no mês atual
2. **Somar receitas realizadas** (confirmadas pelo usuário)
3. **Somar receitas previstas** EXCLUINDO as já confirmadas
4. **Total = Realizadas + Previstas não confirmadas**

**Regra de Prioridade:**
- Se ReceitaRealizada existe para um orçamento → usa `valor_recebido`
- Se não existe → usa `valor_esperado` do ReceitaOrcamento
- Garante que valores confirmados sobrescrevem previsões

**Exemplo Prático:**
```
Orçamento de Salário: R$ 5.000,00
Usuário confirma: R$ 5.000,03
Dashboard exibe: R$ 5.000,03 (valor confirmado)
```

**Padrão Único de Dados:**
- Tabela `Conta` é a **fonte única de verdade** para todas as despesas
- Dashboard e página de despesas usam a mesma query base
- Eliminação de divergências entre diferentes telas
- Sem "remendos" ou lógicas divergentes

### Lógica Completa de Despesas (Dezembro 2024)
Sistema unificado de gerenciamento de despesas com geração automática de registros:

**Arquitetura de Despesas:**
- **Tabela `Conta`** é a fonte única de verdade para TODAS as despesas do sistema
- **Tabela `ItemDespesa`** serve apenas como template/configuração
- Todas as despesas aparecem por **competência** (`mes_referencia`), não por data de vencimento/pagamento
- Princípio fundamental: **Uma despesa = Um registro na tabela Conta**

**Tipos de Despesas e Geração de Contas:**

1. **Despesas Simples** (tipo='Simples'):
   - Criadas manualmente pelo usuário
   - Gera 1 registro na tabela Conta
   - Exemplo: Boleto de internet, conta de luz

2. **Consórcios** (tipo='Consórcio'):
   - Criados via modal de consórcios
   - Gera automaticamente N parcelas como registros em Conta
   - Cada parcela é um registro independente com `numero_parcela` e `total_parcelas`
   - Aplicação de reajustes (percentual/fixo) calculada na geração

3. **Financiamentos** (tipo='Financiamento'):
   - Criados via módulo de financiamentos
   - Gera automaticamente cronograma em `FinanciamentoParcela`
   - Função `sincronizar_contas()` cria registros em Conta para cada parcela
   - Integração bidirecional: pagar parcela → atualiza Conta
   - Exemplo: Financiamento imobiliário SAC com 360 parcelas

4. **Despesas Recorrentes** (recorrente=True):
   - Cadastradas via Configurações → Despesas Recorrentes
   - Função `gerar_contas_despesa_recorrente()` cria Contas automaticamente
   - Suporta múltiplos tipos de recorrência:
     - **'mensal'**: Gera 1 conta por mês (padrão: 12 meses à frente)
     - **'semanal'**: Quinzenal (padrão a cada 2 semanas)
     - **'semanal_X_Y'**: Personalizado onde X=intervalo de semanas, Y=dia da semana
       - Exemplo: 'semanal_2_1' = a cada 2 semanas na terça-feira (1)
       - Dias da semana: 0=Monday, 1=Tuesday, 2=Wednesday, 3=Thursday, 4=Friday, 5=Saturday, 6=Sunday
   - Exemplos: Psicólogo (mensal), Diarista (semanal_2_1)

**Exceção: Cartões de Crédito** (tipo='Agregador'):
- Despesas de cartão NÃO aparecem como Contas individuais
- São agrupadas por fatura mensal na tela de despesas
- Transações individuais ficam em `LancamentoAgregado`
- Filtro usado: `ItemDespesa.tipo != 'Agregador' OR Conta.numero_parcela IS NOT NULL`
- Exceção dentro da exceção: Consórcios/Financiamentos vinculados incorretamente a Agregador ainda aparecem (se tiverem numero_parcela)

**Endpoint de Listagem** ([despesas.py](backend/routes/despesas.py) linhas 62-73):
```python
# Buscar contas que:
# - NÃO são de cartão (tipo != 'Agregador') OU
# - SÃO de cartão MAS têm numero_parcela (consórcios/financiamentos)
contas_nao_cartao = db.session.query(Conta).join(
    ItemDespesa, Conta.item_despesa_id == ItemDespesa.id
).filter(
    or_(
        ItemDespesa.tipo != 'Agregador',
        Conta.numero_parcela.isnot(None)
    )
).order_by(Conta.data_vencimento.desc()).all()
```

**Função de Geração de Despesas Recorrentes** ([despesas.py](backend/routes/despesas.py) linhas 557-656):
- Chamada automaticamente ao criar ItemDespesa com `recorrente=True`
- Deleta Contas futuras pendentes antes de regenerar (evita duplicatas)
- Para recorrência mensal: calcula próximos N meses a partir de `data_vencimento`
- Para recorrência semanal: ajusta para dia da semana alvo e avança pelo intervalo
- Cada Conta criada tem:
  - `mes_referencia`: mês de competência (sempre dia 1)
  - `data_vencimento`: data real de vencimento
  - `descricao`: nome do item + data (para semanais)
  - `status_pagamento`: 'Pendente' por padrão

**Fluxo Completo:**
```
Usuário cria ItemDespesa recorrente
    ↓
Sistema chama gerar_contas_despesa_recorrente(item_id)
    ↓
Função gera N registros em Conta (12 meses padrão)
    ↓
Dashboard e página de despesas consultam Conta
    ↓
Usuário vê todas as ocorrências futuras
```

**Exemplo Prático - Diarista Quinzenal:**
```
ItemDespesa:
  nome: "Diarista"
  tipo: "Simples"
  recorrente: True
  tipo_recorrencia: "semanal_2_1"  (a cada 2 semanas, terça-feira)
  data_vencimento: 2025-12-01
  valor: R$ 240,00

Contas geradas:
  - 2025-12-16 (terça) - Competência: 2025-12-01
  - 2025-12-30 (terça) - Competência: 2025-12-01
  - 2026-01-13 (terça) - Competência: 2026-01-01
  - 2026-01-27 (terça) - Competência: 2026-01-01
  ...
```

**Resultado Final:**
- Dashboard dezembro/2025: R$ 1.520,00 (2 consórcios + 2 despesas recorrentes + 2 diaristas)
- Página de despesas dezembro/2025: R$ 1.520,00 (mesma fonte: tabela Conta)
- ✅ Zero divergências entre telas
- ✅ Todas as despesas aparecem por competência
- ✅ Automação completa para consórcios, financiamentos e recorrentes

### Módulo de Dashboard e Preferências (Dezembro 2024)
Sistema completo de visualização consolidada e configurações personalizáveis:

**Dashboard Backend:**
- **7 Endpoints REST** em [dashboard.py](backend/routes/dashboard.py):
  - `GET /api/dashboard/resumo-mes` - Resumo financeiro do mês atual
  - `GET /api/dashboard/indicadores` - Indicadores inteligentes e insights
  - `GET /api/dashboard/grafico-categorias` - Dados para gráfico de pizza
  - `GET /api/dashboard/grafico-evolucao` - Evolução dos últimos 6 meses
  - `GET /api/dashboard/grafico-saldo` - Evolução do saldo consolidado
  - `GET /api/dashboard/alertas` - Alertas e agenda financeira
  - `GET /api/dashboard/contas-proximos-vencimentos` - Próximas contas
- Queries otimizadas com agregação de dados:
  - **Total de receitas do mês:** Lógica condicional (confirmadas + previstas não confirmadas)
  - Total de despesas do mês (Conta table)
  - Saldo líquido mensal (receitas - despesas)
  - Despesas por categoria para gráficos
  - Evolução histórica de 6 meses

**Preferências Backend:**
- **Modelo Preferencia** (singleton) com 30+ configurações
- **Sistema de 5 abas:**
  1. **Dados Pessoais:** nome, renda, mês de início, dia de fechamento
  2. **Comportamento:** Lançamentos, Dashboard, Cartões (12 configurações)
  3. **Aparência:** Tema (claro/escuro/auto), cor principal, ícones
  4. **Backup:** Backup automático, exportar/importar dados
  5. **IA e Automação:** Modo inteligente, sugestões de economia, classificação automática
- **2 Endpoints REST:**
  - `GET /api/preferencias` - Buscar preferências (cria com padrões se não existir)
  - `PUT /api/preferencias` - Atualizar qualquer combinação de campos

**Frontend Completo:**
- Dashboard responsivo com 4 blocos principais
- Cards de resumo (receitas, despesas, saldo líquido, saldo bancário)
- 3 gráficos interativos (Chart.js):
  - Gráfico de pizza: despesas por categoria
  - Gráfico de barras: evolução dos últimos 6 meses
  - Gráfico de linha: evolução do saldo
- Preferências com tabs animadas e formulários por aba
- Color picker para personalização da cor principal
- Validações client-side e server-side
- Sistema de notificações (sucesso/erro)

**Banco de Dados:**
- Schema corrigido e sincronizado com os modelos
- Tabela `receita_realizada` com coluna `valor_recebido`
- Migração de constraints com nomes explícitos
- Histórico inicial usou `db.create_all()` em desenvolvimento; a evolução oficial de schema agora é Alembic, a partir do baseline `dd1a552aec6a`

### Integração Financiamentos → Despesas (Dezembro 2024)
Sincronização automática entre parcelas de financiamento e despesas:

**Funcionalidades:**
- **Método `sincronizar_contas()`** no FinanciamentoService
- Cria automaticamente uma `Conta` para cada `FinanciamentoParcela`
- Parcelas aparecem na listagem de DESPESAS (igual consórcios)
- Sincronização bidirecional de status de pagamento:
  - Pagar parcela → marca Conta como "Pago"
  - Status atualizado em tempo real
- Descrição detalhada nas contas:
  - Nome do financiamento + número da parcela
  - Observações com breakdown: Amortização + Juros
- Execução automática:
  - Na criação do financiamento
  - Ao pagar uma parcela
  - Ao atualizar dados do contrato

**Frontend:**
- Botões **Editar** e **Excluir** na listagem de financiamentos
- Modal reutilizado para criação e edição
- Função `editarFinanciamento()`: carrega dados e preenche formulário
- Função `excluirFinanciamento()`: soft delete com confirmação
- Atualização da função `salvarFinanciamento()`: detecta modo (criar/editar)
- Integração perfeita com o fluxo existente

### Reorganização da UI (Dezembro 2024)
Separação clara entre despesas recorrentes e lançamentos pontuais:

**Mudanças:**
- **Configurações → Despesas Recorrentes** (novo card):
  - Ícone 📋 "Despesas Recorrentes"
  - Descrição: "Cadastre despesas fixas mensais e consórcios"
  - Link para /despesas
- **Página DESPESAS:**
  - Removido botão "Nova Despesa" da barra de ações
  - Adicionado texto informativo com link para Configurações
  - Agora é apenas uma **listagem** de contas (visualização)
- **Página LANÇAMENTOS:**
  - Mantém "Novo Lançamento" para gastos pontuais
  - Farmácia, combustível, compras parceladas no cartão
  - Interface simplificada para dia a dia

**Fluxo de Uso Atualizado:**
- Despesa recorrente (aluguel, internet, psicólogo) → **Configurações → Despesas Recorrentes**
- Consórcio → **Configurações → Despesas Recorrentes**
- Compra pontual → **Lançamentos**
- Compra parcelada no cartão → **Lançamentos**
- Consultar todas as despesas → **DESPESAS** (menu inferior)

### Módulo de Contas Bancárias Completo (Dezembro 2024)
Implementação completa do sistema de contas bancárias para rastreamento de saldos e origem/destino de transações:

**Backend:**
- **Modelo `ContaBancaria`** com campos completos:
  - Identificação: nome, instituição, tipo, agência, número da conta
  - Controle financeiro: saldo_inicial, saldo_atual
  - Personalização: cor_display, ícone
  - Status e timestamps: status (ATIVO/INATIVO), data_criação, data_atualizacao
- **API REST (6 endpoints):**
  - `GET /api/contas` - Listar contas ativas/inativas
  - `GET /api/contas/:id` - Buscar conta específica
  - `POST /api/contas` - Criar nova conta
  - `PUT /api/contas/:id` - Atualizar dados
  - `DELETE /api/contas/:id` - Inativar conta (soft delete)
  - `PUT /api/contas/:id/ativar` - Reativar conta

**Frontend Completo:**
- Página dedicada acessível via Configurações > Contas Bancárias
- Grid responsivo de cards com barra colorida lateral
- Cards de resumo: Total em Contas, Contas Ativas, Maior Saldo
- Filtros por status (Ativo/Inativo/Todos)
- Modal completo para criar/editar com seletor de cores
- Suporte a 13 instituições pré-cadastradas (CAIXA, Nubank, Itaú, Inter, etc)
- CSS e JavaScript otimizados

**Funcionalidades:**
- Soft delete (contas são inativadas, não deletadas)
- Saldo inicial = saldo atual na criação
- Ajuste automático de saldo ao editar saldo inicial
- Preparado para integração com lançamentos, despesas e receitas

### Módulo de Patrimônio Completo (Dezembro 2024)
Sistema de "caixinhas" para alocação e gestão de patrimônio com transferências inteligentes:

**Backend:**
- **2 Modelos já implementados:**
  - `ContaPatrimonio`: Caixinhas de alocação de patrimônio
    - Campos: nome, tipo, saldo_inicial, saldo_atual, meta, cor
    - Status ativo/inativo
  - `Transferencia`: Movimentações entre caixinhas
    - Campos: conta_origem_id, conta_destino_id, valor, data
    - Atualização automática de saldos
- **API REST (10 endpoints):**
  - **Caixinhas:** GET/POST/PUT/DELETE /api/patrimonio/contas
  - **Transferências:** GET/POST/DELETE /api/patrimonio/transferencias
  - Cálculo automático do patrimônio total
  - Validação de saldo suficiente antes de transferir
  - Reversão automática de saldos ao deletar transferência

**Frontend Completo:**
- Sistema de abas: "📦 Caixinhas" | "🔄 Transferências"
- Página dedicada via Configurações > Patrimônio (Caixinhas)
- Grid de caixinhas com barra colorida e progresso de meta
- Lista de transferências com indicação visual origem→destino
- 2 modais especializados (caixinha e transferência)
- CSS minificado e JavaScript otimizado

**Funcionalidades Avançadas:**
- Progresso visual de metas (% alcançado)
- Validação: contas origem ≠ destino
- Validação: saldo suficiente na origem
- Soft delete para caixinhas
- Hard delete para transferências (com reversão de saldos)
- Cálculo em tempo real do patrimônio total

### Módulo de Financiamentos Completo (Dezembro 2024)
Implementação completa do sistema de financiamentos com suporte aos sistemas SAC, PRICE e SIMPLES:

**Backend:**
- **4 Novos Modelos de Dados:**
  - `Financiamento`: Contratos de financiamento (imobiliário, veículo, empréstimo)
    - Campos: valor_financiado, prazo_total_meses, taxa_juros_nominal_anual, sistema_amortizacao
    - Suporte a indexadores: TR e IPCA para correção do saldo devedor
  - `FinanciamentoParcela`: Estrutura detalhada inspirada nos demonstrativos da CAIXA
    - **Seção A - Encargo Mensal:** amortizacao, juros, seguro, taxa_administrativa
    - **Seção B - Descontos:** fgts_usado, subsidio
    - **Seção C - Encargos de Atraso:** mora, multa, atualizacao_monetaria
    - **Seção D - Totais:** encargo_total, valor_pago, DIF (diferença previsto vs pago)
  - `FinanciamentoAmortizacaoExtra`: Amortizações extraordinárias
    - Tipo `reduzir_parcela`: Mantém prazo, reduz valor das parcelas
    - Tipo `reduzir_prazo`: Mantém valor, reduz número de parcelas
  - `IndexadorMensal`: Valores históricos de TR/IPCA por mês de referência

- **Service Layer Completo** ([financiamento_service.py](backend/services/financiamento_service.py)):
  - **Sistema SAC (Amortização Constante):**
    - Amortização fixa = valor_financiado / prazo
    - Juros decrescentes sobre saldo devedor
    - Aplicação de indexador (TR/IPCA) no saldo a cada mês
  - **Sistema PRICE (Parcelas Fixas):**
    - Cálculo via fórmula PMT: `PV * i * (1+i)^n / ((1+i)^n - 1)`
    - Parcelas fixas, amortização crescente, juros decrescentes
  - **Sistema SIMPLES (Juros Simples):**
    - Juros fixos sobre principal: `valor_financiado * taxa_mensal`
    - Amortização constante
  - **Funcionalidades Avançadas:**
    - Conversão de taxa anual para mensal: `(1 + taxa_anual)^(1/12) - 1`
    - Integração com indexadores para correção monetária
    - Registro de pagamentos com cálculo automático de DIF
    - Recálculo automático de parcelas após amortização extra
    - Demonstrativo anual consolidado (estilo CAIXA)
    - Evolução mês a mês do saldo devedor

**API REST (11 Endpoints):**
1. **CRUD de Financiamentos:**
   - `GET /api/financiamentos` - Listar todos
   - `GET /api/financiamentos/:id` - Detalhes + parcelas
   - `POST /api/financiamentos` - Criar + gerar parcelas automaticamente
   - `PUT /api/financiamentos/:id` - Atualizar
   - `DELETE /api/financiamentos/:id` - Soft delete (inativar)
   - `POST /api/financiamentos/:id/regenerar-parcelas` - Regenerar cronograma

2. **Gerenciamento de Parcelas:**
   - `POST /api/financiamentos/parcelas/:id/pagar` - Registrar pagamento

3. **Amortizações Extraordinárias:**
   - `POST /api/financiamentos/:id/amortizacao-extra` - Registrar e recalcular

4. **Relatórios:**
   - `GET /api/financiamentos/:id/demonstrativo-anual?ano=2025` - Demonstrativo consolidado
   - `GET /api/financiamentos/:id/evolucao-saldo` - Evolução mensal do saldo

5. **Indexadores:**
   - `GET /api/financiamentos/indexadores?nome=TR&ano=2024` - Consultar valores
   - `POST /api/financiamentos/indexadores` - Cadastrar TR/IPCA

**Frontend Completo:**
- HTML responsivo com 5 modais especializados:
  - Modal de criação de financiamento (com info contextual dos sistemas)
  - Modal de detalhes com tabela completa de parcelas
  - Modal de registro de pagamento
  - Modal de amortização extraordinária
  - Modal de demonstrativo anual (com seleção de ano)
- CSS customizado com cards, badges de sistema (SAC/PRICE/SIMPLES) e tabelas detalhadas
- JavaScript com funções para:
  - CRUD completo, formatação de moeda/percentual
  - Cálculo de demonstrativos e evolução
  - Interface intuitiva com tooltips explicativos

**Regras de Negócio:**
- Geração automática de todas as parcelas na criação do contrato
- Integração com módulo de contas a pagar via `conta_id`
- Rastreamento de divergências (DIF) entre previsto e pago
- Suporte a seguros e taxas administrativas mensais
- Indexação automática do saldo devedor quando TR/IPCA está configurado
- Recálculo inteligente após amortizações extras

### Sistema de Faturas Virtuais de Cartão de Crédito (Dezembro 2024)
Reformulação completa do módulo de cartões com lógica **orçamento-primeiro** (planejado vs executado):

**Problema Resolvido:**
- **Antes (errado):** Fatura = soma das compras (bottom-up)
- **Agora (correto):** Orçamento primeiro (top-down), fatura sempre existe

**Conceito Fundamental:**
- Orçamento é definido ANTES das compras (budget mensal recorrente)
- Fatura virtual existe mesmo sem compras
- Compras apenas consomem orçamento, não criam despesas individuais
- Ao pagar: fatura muda de PLANEJADO → EXECUTADO (valor real gasto)

**Backend Completo:**
- **Modelo Conta** expandido com 5 novos campos:
  - `is_fatura_cartao`: Identifica faturas virtuais
  - `valor_planejado`: Soma dos orçamentos das categorias do cartão
  - `valor_executado`: Soma real dos gastos
  - `estouro_orcamento`: Flag de alerta
  - `cartao_competencia`: Mês de referência (YYYY-MM-01)

- **Modelo OrcamentoAgregado** com histórico de vigência:
  - `vigencia_inicio`, `vigencia_fim`, `ativo`
  - Permite rastrear mudanças de orçamento ao longo do tempo

- **CartaoService Completo** ([cartao_service.py](backend/services/cartao_service.py)):
  - `get_or_create_fatura()`: Cria fatura virtual automaticamente
  - `calcular_planejado()`: Soma orçamentos das categorias
  - `calcular_executado()`: Soma lançamentos reais
  - `recalcular_fatura()`: Atualiza valores e detecta estouro
  - `pagar_fatura()`: **Substitui planejado por executado**
  - `adicionar_lancamento()`: Adiciona compra sem criar despesa separada
  - `avaliar_alertas()`: Detecta estouros por categoria
  - `gerar_faturas_mes_atual()`: Job mensal automático

**Automação:**
- **Scheduler APScheduler** integrado ao app.py
- Job mensal: Gera faturas virtuais no 1º dia de cada mês (00:01)
- Criação on-demand ao adicionar lançamentos

**Frontend Completo:**
- **Cards de Despesas** com visualização aprimorada:
  - Badge "Fatura Virtual" azul iOS style
  - Comparação lado a lado: Planejado vs Executado
  - Indicador dinâmico: "(Planejado)" ou "(Executado)"
  - Alerta pulsante de estouro com valor exato da diferença

- **Modal de Pagamento Inteligente:**
  - Interface especial para faturas de cartão
  - Explicação clara da transição planejado → executado
  - Aviso visual com comparação de valores
  - Destaque de estouro se aplicável

**Estilos CSS:**
- Gradientes azuis sutis para faturas de cartão
- Animações de pulso para alertas de estouro
- Grid de comparação com destaque do valor ativo
- Glow sutil em cards com estouro

**Fluxo Completo:**
```
1. Usuário define orçamentos por categoria no cartão (ex: R$ 1.500 alimentação)
2. Sistema gera fatura virtual automaticamente no mês
3. Usuário adiciona compras (consomem orçamento)
4. Fatura mostra PLANEJADO (R$ 2.800) vs EXECUTADO (R$ 2.915)
5. Sistema alerta: "Orçamento ultrapassado em R$ 115"
6. Ao pagar: fatura "congela" no valor EXECUTADO (R$ 2.915)
```

**Resultado:**
- ✅ Controle preciso de orçamento por categoria
- ✅ Visibilidade de estouros em tempo real
- ✅ Histórico de planejado vs executado
- ✅ Automação completa (faturas geradas sem intervenção)
- ✅ Interface profissional com feedback visual claro

### Grupos Agregadores para Categorias Compartilhadas (Dezembro 2024)
Sistema de agrupamento opcional de categorias entre múltiplos cartões de crédito para casais e famílias:

**Problema Resolvido:**
- Permite consolidar gastos de categorias similares entre diferentes cartões
- Exemplo: Cartão João (Farmácia R$ 200) + Cartão Maria (Farmácia R$ 200) = Total R$ 400
- Facilita planejamento familiar e alertas compartilhados

**Princípios Fundamentais:**
1. **Cartões são donos do orçamento** - Cada cartão mantém seu orçamento individual
2. **Grupos são opcionais** - Categorias podem ou não pertencer a um grupo
3. **Grupos NÃO bloqueiam** - São apenas para análise e consolidação
4. **Grupos NÃO possuem orçamento próprio** - Orçamento permanece no nível do cartão
5. **Permite categorias com mesmo nome** - Múltiplos cartões podem ter "Farmácia", "Supermercado", etc.

**Backend Implementado:**
- **Modelo GrupoAgregador** ([models.py](backend/models.py)):
  - `id`, `nome`, `descricao`, `ativo`, `criado_em`
  - Representa agrupamento lógico de categorias
  - Exemplo: Grupo "Farmácia Casal" agrupa Farmácia João + Farmácia Maria

- **Modelo ItemAgregado** atualizado:
  - Campo `grupo_agregador_id` (nullable FK)
  - Relacionamento opcional com GrupoAgregador
  - Categorias podem existir sem grupo (individual)

**Arquitetura de Dados:**
```
GrupoAgregador (id=1, nome="Farmácia Casal")
    ↓
ItemAgregado (id=10, nome="Farmácia", item_despesa_id=5 [Cartão João], grupo_id=1)
    → OrcamentoAgregado (valor_teto=R$ 200)
    → LancamentoAgregado (compras realizadas)
    ↓
ItemAgregado (id=15, nome="Farmácia", item_despesa_id=8 [Cartão Maria], grupo_id=1)
    → OrcamentoAgregado (valor_teto=R$ 200)
    → LancamentoAgregado (compras realizadas)

Total consolidado do grupo: R$ 400 (análise)
Orçamentos individuais: Cada cartão possui seu teto próprio
```

**Regras de Negócio:**
- Categorias sem `grupo_agregador_id` = individuais do cartão
- Categorias com `grupo_agregador_id` = participam de consolidação
- Grupo serve para:
  - Análise consolidada de gastos
  - Alertas futuros quando total do grupo ultrapassar limite
  - Relatórios familiares/compartilhados
- Grupo NÃO serve para:
  - Bloquear lançamentos
  - Distribuir orçamento automaticamente
  - Criar ratios entre cartões

**Migration:**
- Histórico arquivado: `migrations/legacy_sqlite/backend_migrations/add_grupo_agregador.py`
- Cria tabela `grupo_agregador`
- Adiciona coluna `grupo_agregador_id` em `item_agregado`
- Compatível com dados existentes (campo nullable)
- Não executar o script legado no fluxo atual; alterações futuras devem passar por Alembic.

**Casos de Uso:**
1. **Casal com 2 cartões:**
   - Cartão João: Farmácia (R$ 200), Mercado (R$ 800)
   - Cartão Maria: Farmácia (R$ 200), Mercado (R$ 1.200)
   - Grupo "Farmácia Casal": R$ 400 consolidado
   - Grupo "Mercado Casal": R$ 2.000 consolidado

2. **Planejamento familiar:**
   - Definir limite total para categoria (ex: máximo R$ 500 em farmácia)
   - Sistema alerta quando soma dos cartões ultrapassar
   - Cada cartão mantém autonomia de gastos

3. **Análise consolidada:**
   - Relatórios mostrando gasto total por grupo
   - Comparação entre meses de gasto familiar
   - Insights sobre categorias compartilhadas

**Implementação Futura (Frontend):**
- Endpoints prontos para CRUD de grupos
- API retorna dados de grupo em `ItemAgregado.to_dict()`
- Estrutura preparada para tela de gestão de grupos
- Sistema de alertas quando limite consolidado for excedido

**Resultado:**
- ✅ Suporte multi-cartão para casais/famílias
- ✅ Consolidação opcional de categorias
- ✅ Orçamento individual preservado (cartão é o dono)
- ✅ Preparado para alertas e relatórios futuros
- ✅ Sem impacto em funcionalidades existentes

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

- ✅ **Sistema Completo de Financiamentos**
  - Suporte a 3 sistemas de amortização: **SAC**, **PRICE** e **SIMPLES**
  - Cadastro de financiamentos (imobiliário, veículo, empréstimo pessoal)
  - **Geração Automática de Cronograma:**
    - Cálculo matemático preciso de cada parcela
    - Aplicação de indexadores (TR/IPCA) no saldo devedor
    - Inclusão de seguros e taxas administrativas
  - **Amortizações Extraordinárias:**
    - Reduzir valor das parcelas (manter prazo)
    - Reduzir prazo (manter valor das parcelas)
    - Recálculo automático do cronograma
  - **Relatórios Detalhados:**
    - Demonstrativo anual estilo CAIXA
    - Evolução do saldo devedor mês a mês
    - Rastreamento de DIF (diferença previsto vs pago)
  - Interface completa com modais especializados
  - Integração com módulo de contas a pagar

### Módulo 3: Patrimônio
- ✅ Caixinhas para alocação de patrimônio
- ✅ Transferências entre contas

---

## 🏗️ Arquitetura

### Decisões Arquiteturais Críticas

**1. Sistema de Competência (não Caixa):**
- Todo o sistema funciona baseado em **mês de competência**
- Campo `mes_referencia` é usado como padrão em todas as tabelas
- Despesas e receitas são contabilizadas pelo mês de competência, não pela data de pagamento/recebimento
- Importante: NÃO usar `data_vencimento` ou `data_pagamento` para agregações mensais

**2. Fonte Única de Verdade:**
- **Tabela `Conta`** é a fonte única para todas as despesas do sistema
- Dashboard, página de despesas e relatórios DEVEM consultar a mesma tabela
- Tabela `ItemDespesa` serve apenas como template/configuração
- Princípio: Sem lógicas divergentes, sem "remendos"

**3. Priorização de Dados Confirmados:**
- Valores confirmados (ReceitaRealizada, Conta paga) SEMPRE prevalecem sobre previsões
- Dashboard implementa lógica condicional para priorizar dados reais
- Garante que o usuário vê a realidade financeira, não apenas projeções

**4. Campos de Banco de Dados:**
- ReceitaRealizada: usa `mes_referencia` (NÃO `competencia`)
- Conta: tem campo `valor` (NÃO `valor_pago`)
- ItemDespesa: tem campo `tipo` que diferencia despesas simples de agregadores (cartões)

**5. Agrupamento de Cartões de Crédito:**
- Despesas de cartão aparecem AGRUPADAS por mês na listagem
- Não exibir transações individuais na página de despesas
- Transações individuais aparecem apenas na tela específica de cartão de crédito
- Filtro: `ItemDespesa.tipo != 'Agregador'` para despesas individuais

### Stack Tecnológica

**Backend:**
- Python 3.8+
- Flask (Framework web)
- SQLAlchemy (ORM)
- Flask-Migrate (Migrations)

**Banco de Dados:**
- **Desenvolvimento:** PostgreSQL local (`controle_financeiro_dev`) via `DATABASE_URL` em `.env.local`
- **Testing:** SQLite em memória para isolamento automatizado
- **Fallback legado:** SQLite local apenas quando `DATABASE_URL` não estiver definida
- **Produção futura:** PostgreSQL remoto (Supabase) somente em `production`/`staging`

**Frontend:**
- HTML5 + CSS3
- JavaScript (Vanilla)

### Estrutura do Banco de Dados

O baseline Alembic oficial `dd1a552aec6a` cobre 29 tabelas do schema atual. A lista abaixo resume as tabelas principais documentadas historicamente.

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

**Automação (5 tabelas):**
12. `contrato_consorcio` - Contratos que geram lançamentos automáticos
    - Campos de reajuste: `tipo_reajuste` (nenhum/percentual/fixo), `valor_reajuste`
    - Geração automática de parcelas (ItemDespesa) e contemplação (ReceitaRealizada)
13. `financiamento` - Contratos de financiamento (SAC/PRICE/SIMPLES)
    - Campos: valor_financiado, prazo_total_meses, taxa_juros_nominal_anual, sistema_amortizacao
    - Indexadores: TR/IPCA para correção do saldo devedor
14. `financiamento_parcela` - Parcelas detalhadas estilo CAIXA
    - Seção A: amortizacao, juros, seguro, taxa_administrativa
    - Seção B: fgts_usado, subsidio
    - Seção C: mora, multa, atualizacao_monetaria
    - Seção D: encargo_total, valor_pago, DIF
15. `financiamento_amortizacao_extra` - Amortizações extraordinárias
    - Tipos: reduzir_parcela ou reduzir_prazo
16. `indexador_mensal` - Valores de TR/IPCA por mês de referência

**Patrimônio (2 tabelas):**
17. `conta_patrimonio` - Caixinhas de patrimônio
18. `transferencia` - Movimentações entre caixinhas

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

### Passo 4: Configurar Banco de Desenvolvimento

```bash
# Configure .env.local com DATABASE_URL local
DATABASE_URL=postgresql://controle_financeiro:***@localhost:5432/controle_financeiro_dev

# Conferir revision Alembic atual
flask db current
```

### Passo 5: Criar Usuário de Acesso (SEG-1)

Desde o SEG-1, toda rota exige login. Crie o usuário local antes do primeiro acesso:

```bash
venv\Scripts\python.exe scripts\criar_admin.py --email seu@email.com
# Pede a senha no prompt (nao aparece no terminal, nao fica salva em arquivo)
```

Para redefinir a senha de um usuário já existente, use `--reset`. Detalhes completos das opções em `scripts/criar_admin.py`.

---

## 💻 Uso

### Iniciar o Servidor de Desenvolvimento

```bash
python backend/app.py
```

O servidor local fica restrito por padrão a: `http://127.0.0.1:5000`

### Verificar Status da Aplicação

Acesse: `http://127.0.0.1:5000/health`

Deve retornar:
```json
{
  "status": "ok",
  "environment": "development",
  "database": "connected"
}
```

### Acessar o Dashboard

Abra no navegador: `http://127.0.0.1:5000`

---

## 📁 Estrutura do Projeto

```
controle-financeiro/
├── backend/                    # Backend da aplicação
│   ├── app.py                 # Aplicação Flask principal
│   ├── config.py              # Configurações por ambiente
│   ├── models.py              # Modelos do banco (baseline Alembic cobre 29 tabelas)
│   ├── routes/                # Rotas da API
│   │   ├── __init__.py
│   │   ├── categorias.py     # ✅ CRUD de categorias
│   │   ├── despesas.py       # ✅ CRUD de despesas
│   │   ├── cartoes.py        # ✅ Gestão de cartões
│   │   ├── consorcios.py     # ✅ Sistema de consórcios
│   │   ├── receitas.py       # ✅ Sistema de receitas
│   │   ├── financiamentos.py # ✅ Sistema de financiamentos
│   │   ├── patrimonio.py
│   │   └── dashboard.py
│   ├── services/              # Lógica de negócio
│   │   ├── __init__.py
│   │   ├── orcamento_service.py
│   │   ├── cartao_service.py
│   │   ├── consorcio_service.py
│   │   ├── receita_service.py       # ✅ Service de receitas
│   │   └── financiamento_service.py # ✅ Service de financiamentos
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
├── migrations/                 # Alembic/Flask-Migrate
│   ├── versions/              # Baseline oficial e migrations futuras
│   ├── versions_archived/     # Revisions Alembic antigas arquivadas
│   └── legacy_sqlite/         # Scripts SQLite/custom históricos
│
├── tests/                      # Testes E2E/funcionais
│
├── requirements.txt           # Dependências Python
├── .env.local                 # Config de desenvolvimento
├── .env.example               # Template de configuração
├── .gitignore                 # Arquivos ignorados pelo Git
└── README.md                  # Este arquivo
```

---

## 🔄 Roadmap Técnico — Pós-Auditoria (2026-05)

A auditoria técnica de 2026-05 identificou os principais riscos e definiu a ordem de trabalho:

| MVP | Título | Tipo | Prioridade | Dependência |
|-----|--------|------|-----------|-------------|
| SEC-0 | Postura segura local por padrão | Segurança | ✅ Concluído | — |
| TEST-BASE-1 | Ampliar cobertura E2E nos módulos de maior risco | Qualidade | Alta | — |
| ICONES-1B | Ícones de categoria nos lançamentos de cartão | UX | Média | ICONES-1A ✅ |
| DB-CLEAN-1 | `lazy='dynamic'`, `utcnow` depreciado, N+1 queries | Débito técnico | Alta | — |
| CARD-SEC-1 | Remover `numero_cartao`/`codigo_seguranca` em texto puro | Segurança | Alta | — |
| FIN-RULES-1 | Testes de regressão para SAC/PRICE e amortizações | Qualidade | Alta | TEST-BASE-1 |
| TEST-FIN-1 | Ampliar cobertura E2E em Despesas e Financiamentos | Qualidade | Média | TEST-BASE-1 |
| DATA-HYGIENE-1 | `SENHA_MESTRE` hardcoded, rotas sem uso, limpeza geral | Débito técnico | Média | — |
| PERF-1 | Eager loading, índices de query críticos | Performance | Baixa | DB-CLEAN-1 |
| FRONT-ARCH-1 | Extrair helpers JS comuns, eliminar duplicação de código | Débito técnico | Baixa | — |
| SEG-1 | Autenticação global (Flask-Login ativo, proteção de rotas e APIs) | Segurança | Concluído | — |
| DEPLOY-PREP-1 | Preparação segura para deploy (ambientes, hardening, `docs/DEPLOY.md`) | Segurança | Concluído | SEG-1 |
| SUPABASE-MIGRATE-1 | Migração do PostgreSQL local para Supabase | Infra | Depende de DEPLOY-PREP-1 | DEPLOY-PREP-1 |
| DEPLOY-HOST-1 / CLOUDFLARE-1 | Host do backend Flask + DNS/proxy Cloudflare | Infra | Depende de SUPABASE-MIGRATE-1 | SUPABASE-MIGRATE-1 |

**Regra de ouro**: Qualquer acesso externo à internet exige SEG-1 e DEPLOY-PREP-1 completos antes.

### Pontos fortes identificados na auditoria

- Arquitetura de backend sólida: serviços bem separados, lógica financeira correta
- Regras soberanas de fatura consistentemente aplicadas (SAC/PRICE/SIMPLES)
- Shell visual desktop completo com sidebar, topbar e faixa de ações
- Playwright E2E como padrão de validação progressiva
- Alembic como fonte oficial de evolução de schema (baseline `dd1a552aec6a`)

### Débitos técnicos críticos identificados

- `lazy='dynamic'` depreciado: ~12 relacionamentos em `models.py`
- `datetime.utcnow` depreciado: ~20 campos em models e rotas
- N+1 queries em `to_dict()` com lazy load de relacionamentos
- `Query.get()` legacy API SQLAlchemy 2.0: múltiplos usos
- Zero autenticação nas 18 rotas de API
- CORS agora fica restrito localmente por padrão no SEC-0, mas deve ser revisado novamente antes de qualquer deploy
- `numero_cartao` e `codigo_seguranca` em texto puro no banco

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

## 🌐 Produção Futura (Supabase + Cloudflare)

Guia completo em [`docs/DEPLOY.md`](docs/DEPLOY.md) — variáveis obrigatórias, hardening de `SECRET_KEY`/CVV por ambiente, `scripts/check_deploy_env.py`, e o papel de cada peça (Supabase para PostgreSQL, Cloudflare para DNS/proxy, host separado para o backend Flask).

Resumo rápido: produção usa `APP_ENV=production`, PostgreSQL remoto (Supabase), `SECRET_KEY` forte gerada com `secrets.token_urlsafe(48)`, `FLASK_DEBUG=0`, HTTPS obrigatório. A aplicação recusa iniciar em `staging`/`production` sem essas condições — falha fechado, sem fallback silencioso.

Migrations seguem a mesma chain Alembic oficial iniciada pelo baseline `dd1a552aec6a`; não execute scripts SQLite/custom arquivados.

---

## 📝 Comandos Úteis

```bash
# Ativar ambiente virtual
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# Instalar dependências
pip install -r requirements.txt

# Iniciar servidor de desenvolvimento
python backend/app.py

# Conferir revision atual do Alembic
flask db current

# Criar migration
flask db migrate -m "Descrição da mudança"

# Aplicar migration
flask db upgrade

# Validação mínima após mudanças estruturais
npx playwright test tests/e2e/smoke.spec.js
```

---

## 🔧 Desenvolvimento Local vs Produção

| Aspecto | Desenvolvimento (Local) | Produção (Supabase) |
|---------|------------------------|-------------------------|
| Banco de Dados | PostgreSQL local (`controle_financeiro_dev`) | PostgreSQL remoto (Supabase) |
| Debug | Ativado | Desativado |
| Arquivo Config | `.env.local` | `.env.production` (nunca commitado) |
| Schema | Alembic baseline `dd1a552aec6a` + migrations futuras | Mesma chain Alembic |

SQLite permanece apenas como fallback/legado/teste temporário. Não execute scripts de `backend/migrations/`, `migrations/*.py` custom, `migrations/legacy_sqlite/` ou `scripts/debug/` como fluxo de schema.

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

### Financiamentos (Novo!)

**CRUD de Financiamentos:**
- `GET /api/financiamentos` - Listar todos os financiamentos
- `GET /api/financiamentos/:id` - Obter detalhes + cronograma completo de parcelas
- `POST /api/financiamentos` - Criar financiamento e gerar parcelas automaticamente
- `PUT /api/financiamentos/:id` - Atualizar dados do contrato
- `DELETE /api/financiamentos/:id` - Inativar contrato (soft delete)
- `POST /api/financiamentos/:id/regenerar-parcelas` - Regenerar cronograma

**Gerenciamento de Parcelas:**
- `POST /api/financiamentos/parcelas/:id/pagar` - Registrar pagamento e calcular DIF

**Amortizações Extraordinárias:**
- `POST /api/financiamentos/:id/amortizacao-extra` - Registrar amortização e recalcular parcelas

**Relatórios:**
- `GET /api/financiamentos/:id/demonstrativo-anual?ano=2025` - Demonstrativo consolidado por mês
- `GET /api/financiamentos/:id/evolucao-saldo` - Evolução mês a mês do saldo devedor

**Indexadores (TR/IPCA):**
- `GET /api/financiamentos/indexadores?nome=TR&ano=2024` - Consultar valores históricos
- `POST /api/financiamentos/indexadores` - Cadastrar/atualizar valores de TR ou IPCA

**Exemplo de criação de financiamento:**
```json
POST /api/financiamentos
{
  "nome": "Financiamento Imóvel - Caixa",
  "produto": "Imóvel Residencial",
  "sistema_amortizacao": "SAC",
  "valor_financiado": 350000.00,
  "prazo_total_meses": 360,
  "taxa_juros_nominal_anual": 8.5,
  "indexador_saldo": "TR",
  "data_contrato": "2025-01-15",
  "data_primeira_parcela": "2025-02-05",
  "valor_seguro_mensal": 150.00,
  "valor_taxa_adm_mensal": 25.00
}
```

**Exemplo de registro de pagamento:**
```json
POST /api/financiamentos/parcelas/123/pagar
{
  "valor_pago": 2850.50,
  "data_pagamento": "2025-02-05"
}
```

**Exemplo de amortização extraordinária:**
```json
POST /api/financiamentos/1/amortizacao-extra
{
  "data": "2025-12-20",
  "valor": 50000.00,
  "tipo": "reduzir_prazo",
  "observacoes": "FGTS + Décimo terceiro"
}
```

**Exemplo de cadastro de indexador:**
```json
POST /api/financiamentos/indexadores
{
  "nome": "TR",
  "data_referencia": "2025-01-01",
  "valor_percentual": 0.0542
}
```

---

## 🐛 Troubleshooting e Erros Comuns

### Erro: "No attribute 'competencia'"
**Problema:** Tentando acessar campo `competencia` em ReceitaRealizada
**Solução:** Usar `mes_referencia` em vez de `competencia`

### Erro: "No attribute 'valor_pago'"
**Problema:** Tentando acessar campo `valor_pago` na tabela Conta
**Solução:** Usar apenas o campo `valor` (Conta não tem campo valor_pago)

### Dashboard zerado (R$ 0,00 em todos os cards)
**Problema:** Query incorreta ou campo inexistente
**Solução:**
1. Verificar logs do backend para erros SQL
2. Confirmar uso de `mes_referencia` e não `competencia`
3. Reverter mudanças com `git checkout` se necessário

### Divergência entre Dashboard e Página de Despesas
**Problema:** Dashboards mostram valor X mas página de despesas mostra valor Y
**Causa:** Queries consultando tabelas diferentes (Conta vs ItemDespesa)
**Solução:** SEMPRE usar tabela `Conta` como fonte única de verdade

### Despesas de Cartão Aparecem Duplicadas
**Problema:** Transações individuais e agregado mensal aparecem juntos
**Solução:** Filtrar `ItemDespesa.tipo != 'Agregador'` para remover agregadores da lista

### Commits com Hooks Falhando
**Problema:** Pre-commit hooks modificam arquivos após commit
**Solução:**
1. Verificar se commit em HEAD é seu: `git log -1 --format='[%h] (%an <%ae>) %s'`
2. Verificar que branch está ahead: `git status`
3. Se ambos verdadeiros: usar `git commit --amend`
4. Senão: criar novo commit

### Receitas Confirmadas Não Aparecem
**Problema:** Dashboard mostra valor previsto ao invés do confirmado
**Solução:**
1. Verificar se ReceitaRealizada tem `orcamento_id` preenchido
2. Confirmar query condicional em dashboard.py linhas 51-82
3. Usar lógica: Realizadas + (Previstas EXCLUINDO confirmadas)

---

## 📚 Referências

- [Documentação Flask](https://flask.palletsprojects.com/)
- [SQLAlchemy ORM](https://docs.sqlalchemy.org/)
- [Flask-Migrate](https://flask-migrate.readthedocs.io/)

---

## 👨‍💻 Desenvolvimento

**Status:** Em desenvolvimento ativo (retomado em 2026-03-30)

**Estado atual (2026-05):**
- ✅ Sistema funcional completo — Dashboard, Despesas, Receitas, Cartões, Lançamentos, Financiamentos, Contas Bancárias, Patrimônio, Veículos, Categorias
- ✅ Shell visual desktop com sidebar, topbar e faixa de ações padronizada
- ✅ Playwright E2E: smoke (13 passed) + testes funcionais em 5 módulos
- ✅ Alembic como fonte oficial de schema (baseline `dd1a552aec6a`)
- ✅ PostgreSQL local como banco oficial de desenvolvimento
- ✅ Ícones monocromáticos por categoria e meio de pagamento
- ⏳ Próxima prioridade: DB-CLEAN-1 (débitos SQLAlchemy 2.0) e CARD-SEC-1 (dados sensíveis em texto puro)
- ⏳ SEG-1 (autenticação) é bloqueante para qualquer acesso externo

Para a ordem completa de trabalho, ver tabela de Roadmap acima.

---

## 📄 Licença

Uso interno - Kortex Brasil
