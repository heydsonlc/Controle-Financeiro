# FIN-DOCUMENTOS-2
## Migração operacional de Documentos Fiscais e Documentos da Empresa

### Objetivo

Concluir as funcionalidades de escrita, armazenamento e integração documental do novo aplicativo.

As interfaces de consulta já estão disponíveis. Priorizar as operações que ainda dependem do Flask.

### 1. Diagnóstico

Investigar:

- Tipos de documento.
- Cadastros.
- Arquivos.
- Metadados.
- Vínculos financeiros.
- Armazenamento original.
- Permissões.
- Relatórios.
- Testes existentes.

Reutilizar as funções Supabase já implementadas.

### 2. Documentos Fiscais

Migrar, conforme as regras originais:

- Cadastro.
- Edição.
- Exclusão segura.
- Envio de arquivos.
- Consulta e download.
- Classificação.
- Associação com despesas.
- Geração de despesas a partir de documentos.
- Histórico de alterações.

Resolver a funcionalidade "A partir de documento" da página Despesas.

Evitar que o mesmo documento gere despesas duplicadas.

### 3. Documentos da Empresa

Implementar:

- Cadastro e manutenção.
- Tipos e categorias documentais.
- Validade.
- Obrigatoriedade.
- Situação.
- Associação de arquivos.
- Checklist societário.
- Saídas sem documento.
- Vinculação documental com movimentações.

Preservar o isolamento do perfil Empresa.

### 4. Armazenamento

Avaliar o uso do Supabase Storage para armazenar arquivos.

Garantir:

- Separação por perfil.
- Controle de acesso.
- Tipos permitidos.
- Limites de tamanho.
- Validação dos arquivos.
- Remoção segura.
- Rastreabilidade.

Não utilizar armazenamento público para documentos financeiros privados.

Não migrar automaticamente documentos reais nesta etapa.

### 5. Integração com Despesas

Verificar:

- Associação de documentos.
- Geração de despesas.
- Atualização dos vínculos.
- Prevenção de duplicidades.
- Proteção de despesas pagas.
- Preservação de documentos associados ao histórico financeiro.

### 6. OCR

Manter o OCR como funcionalidade complementar.

Não permitir que sua ausência bloqueie o cadastro, armazenamento e associação de documentos.

Não introduzir serviços externos de processamento sem autorização.

### 7. Testes

Cobrir:

- Upload.
- Download.
- Cadastro.
- Edição.
- Exclusão segura.
- Vínculos com despesas.
- Duplicidades.
- Permissões.
- Isolamento.
- Arquivos inválidos.
- Documentos históricos.

### 8. Autonomia e restrições

Implementar as funcionalidades seguras e preparar as migrations necessárias.

Não aplicar migrations persistentes.

Não modificar arquivos ou dados reais.

Não realizar commit, push ou publicação sem autorização.

### 9. Entrega

Criar `docs/FIN_DOCUMENTOS_2.md`.

Apresentar funcionalidades concluídas, armazenamento proposto, testes, migrations e pendências.

**Iniciar a migração operacional de Documentos, priorizando o armazenamento seguro e a integração com Despesas.**
