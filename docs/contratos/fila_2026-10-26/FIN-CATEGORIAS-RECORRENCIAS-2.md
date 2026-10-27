# FIN-CATEGORIAS-RECORRENCIAS-2
## Complementação funcional dos cadastros e recorrências

### Objetivo

Concluir funcionalidades de Categorias, Receitas e Recorrências que permanecem indisponíveis no novo aplicativo.

As interfaces originais já foram migradas. Priorizar as operações, sem redesenhar as telas.

### 1. Categorias

Investigar e implementar:

- Cadastro.
- Edição.
- Exclusão segura.
- Palavras-chave.
- Logos.
- Vinculação com outros módulos.
- Proteção de categorias sistêmicas.
- Validação de categorias com lançamentos históricos.

**O catálogo global continua sob responsabilidade do Flask durante a transição.**

Preparar a implementação Supabase, mas não liberar escrita global concorrente.

Verificar especialmente os códigos sistêmicos utilizados por Mobilidade.

### 2. Receitas

Concluir as funcionalidades pendentes:

- Alterar valor base da fonte.
- Alterar recorrência da fonte.
- Reativar fonte.
- Data prevista independente da competência.
- Recebimento sem previsão, quando admitido pelas regras originais.

Preservar os conceitos de receita prevista, realizada e recebida.

Não duplicar a receita quando ocorrer o recebimento.

Não modificar previsões futuras automaticamente sem observar as regras originais.

### 3. Recorrências

Implementar:

- Frequência semanal.
- Frequência quinzenal.
- Regras de competência e vencimento.
- Geração de lançamentos.
- Alterações futuras.
- Suspensão e reativação.
- Prevenção de duplicidades.

Preservar pagamentos e lançamentos efetivados.

Integrar com Despesas e Cartões.

Verificar a interação com recorrências de consórcios.

### 4. Testes

Cobrir:

- Categorias com vínculos.
- Categorias sistêmicas.
- Fontes de receita.
- Previsões futuras.
- Recorrências semanais e quinzenais.
- Geração repetida.
- Alterações futuras.
- Preservação de registros pagos.
- Permissões e isolamento de perfis.

### 5. Autonomia

Executar diagnóstico e implementação na mesma sessão.

Reutilizar funções existentes.

Preparar migrations locais, sem aplicá-las em ambiente persistente.

Não remover proteções de escritor único.

### 6. Restrições

- Não modificar dados reais.
- Não alterar gastos.db.
- Não realizar commit, push ou publicação.
- Não aplicar migrations persistentes.
- Não transferir o catálogo global de categorias sem autorização.

### 7. Entrega

Criar `docs/FIN_CATEGORIAS_RECORRENCIAS_2.md`.

Informar funcionalidades concluídas, testes, dependências e pendências.

**Priorizar a conclusão funcional, preservando a integridade dos lançamentos históricos.**
