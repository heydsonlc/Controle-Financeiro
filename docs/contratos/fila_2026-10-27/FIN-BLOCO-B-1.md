# FIN-BLOCO-B-1 — DOCUMENTOS, RELATÓRIOS E CONFIGURAÇÕES

**Projeto:** Gestão Financeira  
**Autorização:** Implementação local, testes e commits locais.

**Dependência:** FIN-BLOCO-A-1.

## Objetivo

Concluir os módulos Documentos, Relatórios e Configurações, preparando o sistema para a homologação geral.

### B0 — Conferência inicial

Antes de iniciar:

- Conferir o estado do Git.
- Ler o relatório do Bloco A.
- Verificar as migrations locais.
- Identificar pendências que afetem Documentos ou Relatórios.
- Preservar todas as alterações preexistentes.

Se o Bloco A apresentar bloqueador que comprometa a integridade financeira ou documental, interromper e informar.

### B1 — FIN-DOCUMENTOS-2

Consultar os contratos e documentos existentes de Documentos, Patrimônio e financiamentos.

Implementar:

1. Upload de documentos.
2. Armazenamento privado por perfil.
3. Consulta e visualização.
4. Download autorizado.
5. Exclusão segura.
6. Associação de documentos a registros financeiros e patrimoniais.
7. Criação de bens a partir de documentos.
8. Preservação dos vínculos históricos.
9. Extração de informações por OCR, quando aplicável.
10. Integração com documentos já existentes no Flask.

Verificar limites de tamanho, formatos permitidos, nomes de arquivo, permissões e integridade dos uploads.

O armazenamento deverá impedir acesso a arquivos de outros perfis.

Não criar buckets públicos para documentos financeiros ou pessoais.

Utilizar dados e arquivos fictícios nos testes.

### B2 — FIN-RELATORIOS-CONFIG-1

Implementar as funcionalidades pendentes de Relatórios e Configurações.

Cobertura:

- Relatórios financeiros.
- Exportações PDF.
- Exportações XLSX.
- Exportações ZIP, quando previstas.
- Extratos e demonstrativos.
- Exportações de Patrimônio.
- Consultas por perfil e período.
- Configurações de usuário e perfil.
- Funcionalidades administrativas existentes.
- Rotinas de backup e restauração previstas para o aplicativo.

Preservar os cálculos e critérios financeiros atuais.

Não criar novos indicadores gerenciais que não estejam previstos no roadmap.

### B3 — Segurança documental

Verificar:

- RLS e isolamento entre perfis.
- Permissões de leitura e escrita.
- Segurança do Storage.
- Controle de acesso a downloads.
- Proteção contra acesso por identificador de outro usuário.
- Exclusão segura de arquivos vinculados.
- Ausência de exposição de credenciais.
- Tratamento de arquivos inválidos.

Nenhuma chave privilegiada poderá ser incorporada ao frontend.

### B4 — Integração

Testar:

- Documentos × Patrimônio.
- Documentos × Financiamentos.
- Documentos × Despesas.
- Relatórios × Dados financeiros.
- Relatórios × Perfis.
- Configurações × Escritor Único.

Conferir que consultas e exportações não alteram dados financeiros.

### B5 — Banco

Criar migrations e reversões locais apenas quando necessárias.

Validar em bancos descartáveis.

Não aplicar migrations remotas.

Se o armazenamento privado depender de configuração remota, preparar o procedimento e registrar como pendente de autorização.

### B6 — Encerramento

Executar testes direcionados durante o desenvolvimento.

Ao final:

- Testes de integração.
- Regressão consolidada de nível 3.
- Verificação de permissões.
- Verificação de integridade.
- Documentação.
- Commits locais separados por módulo.

Atualizar ROADMAP.

## Limites

Não executar:

- Push.
- Publicação.
- Aplicação de migrations no remoto.
- Criação ou alteração de buckets remotos.
- Migração de dados reais.
- Exclusão de documentos reais.
- Restauração sobre bancos existentes.
- Alterações no `gastos.db`.

## Relatório final

Apresentar:

1. Documentos: funcionalidades concluídas.
2. Relatórios e Configurações: funcionalidades concluídas.
3. Migrations e Storage: estado local e pendências remotas.
4. Testes.
5. Commits.
6. Bloqueadores.
7. Situação final.

Liberar o Bloco C apenas se a implementação estiver consistente e sem bloqueadores que impeçam a homologação geral.
