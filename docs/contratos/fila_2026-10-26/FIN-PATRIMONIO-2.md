# FIN-PATRIMONIO-2
## Migração operacional de Patrimônio

### Objetivo

Concluir as funcionalidades de escrita do módulo Patrimônio, cuja interface original já funciona em modo consulta no novo aplicativo.

### 1. Diagnóstico

Inspecionar:

- Rotas e serviços do Flask.
- Modelos de dados.
- Regras de cadastro.
- Vínculos financeiros.
- Documentos associados.
- Testes existentes.
- Funções Supabase disponíveis.

Não refazer a migração visual.

### 2. Implementação

Migrar as funcionalidades originais de:

- Cadastro de bens.
- Edição.
- Exclusão segura.
- Atualização de valores.
- Aquisição.
- Alienação.
- Vinculação com financiamentos.
- Vinculação com documentos.
- Histórico patrimonial.
- Demais operações existentes no Flask.

### 3. Regras de integridade

Preservar:

- Histórico das aquisições.
- Vínculos com contratos.
- Parcelas e pagamentos relacionados.
- Documentos associados.
- Movimentações financeiras.

Não excluir registros que sustentem operações financeiras históricas.

Não alterar saldos de financiamento como efeito colateral de uma edição patrimonial.

### 4. Escritor único

Utilizar a proteção já implementada.

Perfil atribuído ao Flask não poderá executar escrita patrimonial no novo aplicativo.

Implementar e testar as funções que faltarem.

### 5. Testes

Verificar:

- Cadastro.
- Edição.
- Exclusão segura.
- Vínculos com Financiamentos.
- Documentos.
- Valores.
- Isolamento por perfil.
- Permissões.
- Integridade histórica.

### 6. Autonomia

Diagnosticar e implementar progressivamente.

Preparar migrations locais e testes.

Não aplicar alterações persistentes sem autorização.

### 7. Restrições

- Não modificar o banco original.
- Não alterar dados reais.
- Não realizar commit, push ou publicação.
- Não aplicar migrations persistentes.

### 8. Entrega

Criar `docs/FIN_PATRIMONIO_2.md`.

Apresentar funcionalidades concluídas, testes, migrations e pendências.

**Iniciar a migração operacional de Patrimônio, reutilizando a interface original já implementada.**
