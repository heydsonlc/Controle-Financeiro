# FIN-RELATORIOS-CONFIG-1
## Relatórios, Configurações e Backup

### Objetivo

Concluir as funcionalidades complementares necessárias para que o novo aplicativo possa substituir o Flask.

Priorizar operações efetivamente existentes no sistema original.

### 1. Relatórios

Investigar e migrar:

- Exportação PDF.
- Exportação Excel/XLSX.
- Exportação ZIP.
- Relatórios financeiros.
- Relatórios patrimoniais.
- Relatórios de financiamentos.
- Relatórios de documentos.
- Relatórios de Imposto de Renda.

Preservar os dados, filtros e critérios utilizados pelo Flask.

Não considerar a funcionalidade concluída apenas porque um arquivo pode ser gerado.

Conferir o conteúdo exportado com o relatório original.

### 2. Configurações

Migrar as funcionalidades efetivamente disponíveis no Flask:

- Preferências.
- Aparência.
- Configurações financeiras.
- Parâmetros de usuário.
- Configurações de documentos.
- Demais opções existentes.

Preservar o isolamento entre usuários e perfis.

Não criar novas funcionalidades que não façam parte do sistema sem necessidade comprovada.

### 3. Backup

Investigar o mecanismo original e propor uma estratégia adequada ao Supabase.

A solução deverá contemplar:

- Exportação de dados.
- Preservação dos relacionamentos.
- Integridade referencial.
- Proteção de informações sensíveis.
- Recuperação verificável.
- Controle de acesso.
- Rastreabilidade.

Não implementar restauração sobre bancos persistentes sem autorização.

Não executar operações destrutivas.

### 4. Segurança

Verificar:

- Dados sensíveis de cartão.
- Permissões.
- Segredos.
- Acesso a arquivos.
- Exportações.
- Dados de outros perfis.
- Segurança dos backups.

**Não armazenar CVV.**

Não copiar números completos ou validade do banco Flask para o Supabase.

O saneamento dos dados antigos será objeto de procedimento próprio.

### 5. Testes

Validar:

- Conteúdo dos relatórios.
- Arquivos exportados.
- Filtros.
- Permissões.
- Integridade dos backups.
- Isolamento.
- Ausência de exposição de dados sensíveis.
- Compatibilidade com os dados existentes.

### 6. Autonomia

Diagnosticar e implementar progressivamente.

Reaproveitar bibliotecas existentes quando adequadas.

Se uma dependência nova for necessária, apresentar justificativa e aguardar autorização para instalá-la.

Não executar restaurações persistentes.

### 7. Restrições

- Não realizar commit.
- Não realizar push.
- Não aplicar migrations persistentes.
- Não publicar.
- Não alterar produção.
- Não modificar gastos.db.
- Não modificar arquivos pessoais.
- Não apagar backups existentes.

### 8. Entrega

Criar `docs/FIN_RELATORIOS_CONFIG_1.md`.

Apresentar:

1. Relatórios migrados.
2. Configurações implementadas.
3. Estratégia de backup.
4. Testes executados.
5. Funcionalidades pendentes.
6. Migrations ou dependências necessárias.
7. Riscos para produção.

**Iniciar o FIN-RELATORIOS-CONFIG-1, priorizando a substituição das funcionalidades complementares ainda dependentes do Flask.**
