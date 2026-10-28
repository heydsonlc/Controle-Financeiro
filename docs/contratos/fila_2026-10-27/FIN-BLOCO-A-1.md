# FIN-BLOCO-A-1 — INTEGRIDADE E MOBILIDADE

**Projeto:** Gestão Financeira  
**Ambiente:** Computador de casa / VS Code  
**Autorização:** Implementação local, testes e commits locais.

## Objetivo

Concluir as proteções do Escritor Único e implementar as funcionalidades restantes do módulo Mobilidade, preservando a equivalência com o Flask.

### A1 — Encerramento da homologação anterior

Verificar se `FIN-INTEGRACAO-1123-1126-1` já foi encerrado e commitado.

Se ainda não:

- Registrar os resultados da homologação.
- Documentar a ordem obrigatória das reversões 1126 → 1125 → 1124 → 1123.
- Atualizar o ROADMAP.
- Criar commit local exclusivo da homologação.

Não repetir testes já aprovados sem necessidade.

### A2 — Escritor Único

Corrigir as três lacunas comprovadas:

1. `criar_financeiro_comprovante` em `backend/routes/ir.py`.
2. `despesas_previstas/confirmar`.
3. `DocumentoFiscalService.criar_vinculo` e `remover_vinculo`.

Requisitos:

- Reutilizar a guarda e a trava compartilhada existentes.
- Recusar gravações do Flask em perfil NOVO com HTTP 409.
- Impedir gravações parciais.
- Preservar o funcionamento dos perfis FLASK.
- Garantir integridade de documentos e vínculos patrimoniais.
- Retirar os três `xfail(strict=True)` quando os testes passarem.
- Verificar concorrência com troca de escritor.

Examinar as operações de metadados de perfil identificadas anteriormente e registrar eventuais ajustes necessários.

Criar commit local separado após os testes direcionados.

### A3 — FIN-MOBILIDADE-2

Ler o contrato existente em:

`docs/contratos/fila_2026-10-26/FIN-MOBILIDADE-2.md`

Também consultar a documentação e os testes atuais de Mobilidade.

Implementar a migração das operações de Veículos/Mobilidade para o novo aplicativo, preservando as funcionalidades e regras do Flask.

Cobertura obrigatória:

- Cadastro e edição de veículos.
- Cenários de mobilidade.
- Simulação de custos.
- Efetivação de cenários.
- Despesas previstas decorrentes dos cenários.
- Vínculo com categorias sistemáticas.
- Integridade de recorrências e despesas financeiras.
- Isolamento entre perfis.
- Escritor único.

**Atenção especial:** verificar o comportamento após a reorganização das categorias de despesas. Não permitir que categorias recriadas provoquem perda de vínculos, despesas duplicadas ou projeções incorretas.

Preservar as despesas já executadas.

Resolver a falha conhecida relacionada à categoria `IPVA`, caso esteja dentro do escopo e a causa seja confirmada.

### A4 — Integração

Validar os fluxos:

- Mobilidade × Categorias.
- Mobilidade × Despesas Previstas.
- Mobilidade × Recorrências.
- Mobilidade × Escritor Único.
- Mobilidade × Contas Bancárias, apenas quando houver vínculo efetivo no modelo existente.

Testar criação, edição, efetivação, repetição e reversão dos cenários, respeitando as regras atuais.

### A5 — Banco e segurança

Criar migrations e reversões locais somente quando necessárias.

Verificar:

- RLS e isolamento por perfil.
- Privilégios de execução.
- Funções com privilégios elevados.
- Integridade referencial.
- Idempotência.
- Compatibilidade com migrations anteriores.

Aplicar e testar migrations apenas em bancos PostgreSQL descartáveis.

Se uma funcionalidade exigir alteração de regra de negócio ou mudança estrutural não prevista no contrato de Mobilidade, interromper somente essa frente e registrar a decisão necessária.

Não aplicar migrations no Supabase remoto.

### A6 — Validação e encerramento

Executar testes direcionados durante o desenvolvimento.

No fechamento:

- Regressão consolidada de nível 3.
- Testes de integração.
- Comparação com as falhas antigas.
- Conferência de integridade do Git.
- Conferência do banco real, sem alterá-lo.

Criar commits locais separados para:

1. Escritor Único.
2. Mobilidade.
3. Documentação e encerramento, se necessário.

Atualizar ROADMAP e documentos técnicos.

## Limites

Proibido:

- Push.
- Publicação.
- Alteração do Supabase remoto.
- Alteração do `gastos.db`.
- Transferência de perfis reais.
- Alteração de regras financeiras sem decisão do titular.
- Exclusão de dados reais.

## Relatório final

Apresentar somente:

1. Funcionalidades concluídas.
2. Migrations criadas.
3. Testes e regressões.
4. Commits locais.
5. Pendências e bloqueadores.
6. Situação: APROVADO / APROVADO COM RESSALVAS / BLOQUEADO.

Concluído o bloco, encerrar e liberar a execução do próximo contrato da fila somente se não houver bloqueador de integridade ou dependência que inviabilize o Bloco B.
