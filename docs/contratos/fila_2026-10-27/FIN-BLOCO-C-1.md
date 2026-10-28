# FIN-BLOCO-C-1 — HOMOLOGAÇÃO GERAL, SEGURANÇA E BACKUP

**Projeto:** Gestão Financeira  
**Autorização:** Diagnóstico, testes, correções locais justificadas e commits locais.

**Dependências:** FIN-BLOCO-A-1 e FIN-BLOCO-B-1.

## Objetivo

Realizar a homologação geral do Gestão Financeira e verificar se o sistema está tecnicamente preparado para iniciar o processo de migração dos dados reais.

**Este contrato não autoriza produção nem migração real.**

### C0 — Inventário

Conferir:

- Estado do Git.
- Commits locais pendentes.
- Migrations e reversões.
- Resultados dos blocos A e B.
- Pendências funcionais.
- Pendências de segurança.
- Estado do Supabase de teste, exclusivamente por leitura.

Produzir uma lista objetiva dos bloqueadores de produção.

### C1 — Homologação funcional

Executar uma regressão geral abrangendo:

- Autenticação e perfis.
- Contas bancárias.
- Receitas.
- Despesas.
- Recorrências.
- Cartões e faturas.
- Pagamentos e estornos.
- Financiamentos.
- Consórcios.
- Patrimônio.
- Mobilidade.
- Documentos.
- Relatórios.
- Configurações.

Validar fluxos completos, não apenas operações isoladas.

Verificar especialmente:

- Integridade de contas pagas.
- Preservação dos históricos.
- Escritor Único.
- Concorrência.
- Isolamento entre perfis.
- Idempotência.
- Ausência de duplicidades.
- Saldo financeiro consistente com os movimentos.

### C2 — Segurança de cartões

Revisar o tratamento de informações sensíveis.

Requisitos:

- Não armazenar CVV no novo aplicativo.
- Não transmitir CVV desnecessariamente.
- Verificar se números completos de cartões são armazenados.
- Caso sejam necessários, exigir criptografia adequada e controle de acesso.
- Evitar exposição em logs, respostas de API e exportações.
- Verificar dados antigos e eventual necessidade de saneamento.

Não realizar transformação destrutiva dos dados existentes.

Se for necessária migração de dados sensíveis ou definição de chave de criptografia, documentar e aguardar autorização.

### C3 — Segurança da aplicação

Auditar:

- Autenticação.
- Sessões.
- Autorização por perfil.
- RLS.
- Funções privilegiadas.
- Permissões do Storage.
- Exposição de endpoints.
- Controle de acesso a documentos.
- Proteção de dados financeiros e pessoais.
- Credenciais no código e histórico Git.
- Configurações de produção.

Verificar se o frontend utiliza somente credenciais públicas apropriadas.

Não realizar alterações de políticas remotas.

### C4 — Backup e restauração

Verificar:

- Backup do banco de dados.
- Backup independente dos documentos.
- Integridade dos arquivos.
- Possibilidade de restauração.
- Procedimentos de recuperação de falha.
- Preservação de dados históricos.

Executar restauração somente em ambientes descartáveis.

Nunca restaurar sobre banco real.

### C5 — Falhas antigas

Reavaliar as cinco falhas conhecidas da suíte Python.

Distinguir:

- Defeito funcional.
- Teste desatualizado.
- Dependência do ambiente.
- Dependência da data.

Corrigir localmente aquilo que estiver comprovado e não exigir mudança de regra de negócio.

Atualizar os testes quando a expectativa antiga estiver incorreta, documentando a razão.

### C6 — Preparação das migrations

Verificar:

- Ordem de aplicação.
- Reversões.
- Integridade das dependências.
- Segurança das funções.
- Compatibilidade com dados existentes.
- Riscos de alteração em tabelas já utilizadas.

Ensaiar a aplicação em banco descartável com dados fictícios representativos.

Não aplicar migrations no Supabase remoto.

### C7 — Validação final

Executar regressão completa de nível 3 após as correções.

Confirmar:

- Ausência de regressões novas.
- Ausência de bloqueadores de segurança conhecidos.
- Integridade dos módulos.
- Integridade dos dados.
- Compatibilidade das migrations.
- Funcionamento dos backups.
- Isolamento entre usuários.

### C8 — Encerramento

Atualizar o ROADMAP e criar um documento consolidado:

`docs/FIN_PREPARACAO_PRODUCAO_1.md`

O documento deverá indicar:

1. Funcionalidades homologadas.
2. Testes executados.
3. Falhas remanescentes.
4. Riscos de segurança.
5. Migrations pendentes no remoto.
6. Pendências de Storage.
7. Estratégia recomendada de migração.
8. Procedimento de rollback.
9. Itens necessários para produção.

Criar commits locais separados para correções e documentação.

## Limites

Proibido:

- Push.
- Publicação.
- Alteração do Supabase remoto.
- Migração de perfis reais.
- Alteração do `gastos.db`.
- Restauração em banco persistente.
- Exclusão de documentos reais.
- Ativação de produção.

Caso uma correção exija alteração de regra de negócio, tratamento irreversível de dados ou nova autorização, registrar o bloqueio e prosseguir somente nas atividades independentes e seguras.

## Relatório final

Apresentar relatório executivo contendo:

**A. Módulos homologados.**

**B. Resultado da regressão geral.**

**C. Segurança e backup.**

**D. Pendências e bloqueadores.**

**E. Commits e migrations.**

**F. Classificação final:**
- PRONTO PARA PLANEJAR MIGRAÇÃO REAL.
- PRONTO COM RESSALVAS.
- NÃO PRONTO.

Encerrar sem executar o Bloco D.

**O Bloco D dependerá de avaliação e autorização específica do titular.**
