# FIN-MOBILIDADE-2
## Migração operacional de Veículos e Mobilidade

### Objetivo

Concluir as funcionalidades de escrita do módulo Mobilidade, preservando as regras originais do Flask para veículos, custos, projeções e cenários.

A interface de consulta já está migrada. Priorizar sua operação.

### 1. Funcionalidades

Investigar e implementar:

- Cadastro e edição de veículos.
- Exclusão segura.
- Consumo de combustível.
- Manutenção por quilometragem.
- Custos mensais.
- Financiamento de veículo.
- Assinaturas de veículos.
- Transporte por aplicativo.
- Comparação de modalidades.
- Geração de projeções.
- Ativação de cenários.
- Efetivação das despesas previstas.

Preservar o modelo financeiro original.

### 2. Cenário ativo

A decisão arquitetural já foi estabelecida:

**O cenário ativo deverá ser persistido no Supabase e associado ao perfil financeiro.**

Não reproduzir o arquivo global utilizado pelo Flask.

Verificar se a estrutura atual permite armazenar essa informação.

Caso seja necessária alteração estrutural, preparar a migration e solicitar autorização antes de aplicá-la.

### 3. Categorias sistêmicas

Verificar os vínculos das categorias utilizadas pela Mobilidade.

Existe uma dívida técnica anterior relacionada à recriação das categorias de despesas.

Antes de efetivar cenários, conferir:

- Existência das categorias.
- Códigos sistêmicos.
- Vínculos corretos.
- Ausência de identificadores obsoletos.
- Prevenção de despesas duplicadas.

Não recriar categorias automaticamente durante consultas.

### 4. Financiamentos de veículos

Integrar com o motor financeiro migrado.

Não duplicar cálculos de financiamento.

Preservar o histórico de prestações, amortizações e pagamentos.

Não reproduzir o defeito D-MOB1 do Flask.

### 5. Efetivação de cenários

Garantir que:

- A prévia não grava dados.
- A efetivação exige confirmação.
- As despesas geradas mantenham o vínculo com o cenário.
- A operação seja atômica.
- Repetir a confirmação não duplique despesas.
- Alterações futuras preservem despesas efetivadas.

### 6. Testes

Verificar:

- Cadastro e edição.
- Custos e projeções.
- Comparação de modalidades.
- Cenário ativo por perfil.
- Efetivação.
- Geração de despesas.
- Categorias sistêmicas.
- Financiamentos vinculados.
- Exclusão segura.
- Escritor único e permissões.

### 7. Autonomia e restrições

Diagnosticar e implementar na mesma execução.

Preparar migrations locais e testes.

Não aplicar migrations persistentes, realizar commit, push ou publicação sem autorização.

Não modificar gastos.db nem dados reais.

### 8. Entrega

Criar `docs/FIN_MOBILIDADE_2.md`.

Apresentar funcionalidades implementadas, testes, diferenças em relação ao Flask, migrations e pendências.

**Iniciar a migração operacional de Mobilidade, priorizando a geração segura das despesas previstas.**
