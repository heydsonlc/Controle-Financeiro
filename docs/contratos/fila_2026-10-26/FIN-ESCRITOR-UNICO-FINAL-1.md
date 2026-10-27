# FIN-ESCRITOR-UNICO-FINAL-1
## Proteção integral das operações de escrita — Flask e Supabase

### Objetivo

Concluir a proteção do escritor único nos módulos que ainda permitem operações concorrentes entre o Flask e o novo aplicativo.

O trabalho deverá utilizar as estruturas e as guardas já implementadas nos contratos anteriores.

### 1. Diagnóstico direcionado

Consultar:

- FIN_AUDITORIA_GERAL_1.md.
- FIN_ESCRITOR_UNICO_CONTAS_1.md.
- FIN_CONTRATOS_2.md.
- FIN_CONTRATOS_3.md.
- ROADMAP.md.

Identificar as operações ainda sem proteção, especialmente:

- Cadastro e edição de Despesas.
- Cadastro e edição de Receitas.
- Fontes e previsões de receita.
- Recorrências.
- Cartões e compras.
- Categorias do Cartão.
- Operações de importação.
- Demais rotas de escrita que compartilhem dados financeiros.

Não reimplementar guardas já existentes.

### 2. Regra central

A atribuição do perfil determina quem pode escrever.

**Perfil FLASK:** escrita pelo Flask; o novo aplicativo recusa.

**Perfil NOVO:** escrita pelo Supabase; o Flask recusa.

Aplicar a proteção no banco e nas rotas correspondentes, sem depender apenas da interface.

### 3. Implementação

- Completar as verificações de escritor nas funções Supabase existentes.
- Implementar as guardas correspondentes no Flask.
- Preservar consultas nos dois aplicativos.
- Preservar permissões de gestão e isolamento dos perfis.
- Manter proteção contra operações duplicadas.
- Não alterar fórmulas financeiras.
- Não modificar registros históricos.

Atenção às operações que podem envolver mais de um perfil ou registros compartilhados.

### 4. Catálogos globais

Não alterar neste contrato a responsabilidade pelo catálogo global de categorias de despesa.

Durante a transição, sua escrita continua sob responsabilidade do Flask.

Categorias do Cartão, por serem vinculadas ao perfil, deverão respeitar o escritor do perfil.

### 5. Testes

Verificar, para cada operação protegida:

- Perfil FLASK grava somente pelo Flask.
- Perfil NOVO grava somente pelo Supabase.
- Aplicativo não responsável recusa sem gravar.
- Usuário somente de leitura não grava.
- Outro perfil não acessa os dados.
- Reenvio não duplica operações.
- Consultas permanecem funcionais.

Criar testes de regressão para Despesas, Receitas, Cartões, Recorrências, Contas Bancárias, Financiamentos e Consórcios.

### 6. Autonomia

Implementar diretamente guardas e testes de baixa e média complexidade.

Preparar migrations locais quando necessárias.

Não aplicar migrations persistentes sem autorização.

Caso uma operação exija mudança estrutural relevante, registrar a pendência e continuar.

### 7. Restrições

- Não alterar gastos.db.
- Não modificar dados reais.
- Não realizar commit sem autorização.
- Não realizar push.
- Não aplicar migrations persistentes.
- Não publicar.
- Não transferir perfis reais para o novo aplicativo.

### 8. Entrega

Criar `docs/FIN_ESCRITOR_UNICO_FINAL_1.md`.

Apresentar:

1. Operações anteriormente desprotegidas.
2. Guardas implementadas.
3. Testes executados.
4. Operações ainda pendentes.
5. Migrations necessárias.
6. Riscos para a transferência de perfis reais.

**Iniciar a implementação, priorizando o fechamento das operações financeiras que ainda permitem dois escritores.**
