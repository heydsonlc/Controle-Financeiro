# FIN-AUDITORIA-PUBLICACAO-MIGRACAO-01 — A. Relatório executivo

**Projeto:** Controle Financeiro (`heydsonlc/Controle-Financeiro`). **Data de referência:** 15/11/2026.
**Natureza:** auditoria somente leitura. Nenhum dado, migration, função, configuração ou deploy foi alterado. Não houve push. Os cinco documentos da auditoria estão apenas no computador local.

**Documentos da auditoria**
- A. este relatório
- B. `FIN_AUDITORIA_MATRIZ_FUNCIONAL_01.md`
- C. `FIN_AUDITORIA_DOCUMENTOS_FISCAIS_01.md`
- D. `FIN_AUDITORIA_INFRAESTRUTURA_01.md`
- E. `FIN_AUDITORIA_PLANO_REGULARIZACAO_01.md`

## 1. Resumo

A migração para Supabase + Cloudflare está **operacional e íntegra**. GitHub, banco e site publicado coincidem. O Flask não participa mais do funcionamento.

- **GitHub = Cloudflare.** O deploy de produção `45e24f88` corresponde ao commit `1ce28cb` do `main`. Os 225 arquivos servidos são idênticos, por hash, ao build desse commit, no domínio oficial e no endereço do Pages.
- **GitHub = Supabase.** As 67 migrations do repositório estão aplicadas, sem pendente, extra ou divergente. As 569 funções e as 1.057 colunas da produção são idênticas às geradas pelo repositório.
- **Sem dependência do Flask em funcionamento.** Os dois perfis e o catálogo de categorias são escritos só pelo aplicativo novo desde 29 e 30/10/2026. O Flask não está hospedado. O que resta dele é o código das telas, reaproveitado no build.
- **Nada pronto e não publicado.** Não há código desenvolvido fora da produção, apenas 1 commit local de documentação.

O que **falta** é de três tipos:
1. **Um risco aos dados:** não há backup da produção comprovado (P1).
2. **Funções que o servidor Flask fazia e o aplicativo estático ainda não faz** (13 itens): relatórios e ZIP de documentos, OCR, leitura de NFS-e e cupom, documentos de financiamento, demonstrativo anual, consolidação de fatura e lacunas menores.
3. **Homologação:** 20 itens estão publicados e testados, mas sem uso real nem aprovação registrada do titular.

## 2. Números

- **Módulos auditados:** 21, as áreas do contrato mais Acesso, Importação de cartão, Agendamento e Infraestrutura.
- **Funcionalidades inventariadas:** 91, sendo 61 na matriz geral e 30 de Documentos Fiscais.

| Classificação | Quantidade |
|---|---|
| CONCLUÍDO | 42 |
| PUBLICADO NÃO HOMOLOGADO | 20 |
| PARCIAL | 6 |
| NÃO MIGRADO | 13 |
| NÃO COMPROVADO | 2 |
| FORA DO ESCOPO | 8 |
| DESENVOLVIDO NÃO PUBLICADO | 0 |
| MIGRATION PENDENTE | 0 |
| DIVERGENTE | 0 |

**Pendências por prioridade:** P0 nenhuma; P1 uma (backup); P2 as lacunas de documentos, de financiamentos e a consolidação de fatura; P3 homologações e ajustes.

## 3. Respostas às dez perguntas do contrato

1. **Totalmente migrados:** Acesso e Perfis (isolamento), Dashboard (resumo), Despesas, Receitas (núcleo), Cartões, Importação de cartão, Recorrências, Consórcios, Contas bancárias, Lançamentos, Financiamentos (motor SAC/TR), Indexadores (TR), Mobilidade, Categorias e os módulos mobile 01 a 08.
2. **Desenvolvido e não publicado:** nada. Só 1 commit local de documentação (`3f480c4`).
3. **Migrations versionadas e não aplicadas:** nenhuma (67 de 67).
4. **Estrutura no Supabase que ainda depende do Flask:** nenhuma em funcionamento. A tabela legada `financiamento_documento` existe, mas não tem funções nem tela no novo.
5. **Páginas publicadas com recursos indisponíveis:**
   - Documentos Fiscais: OCR, Excel e PDF de IR e de lastro, ZIP;
   - Financiamentos: documentos, conferências da Caixa, demonstrativo anual, valores simulados;
   - Despesas: consolidar fatura;
   - Receitas: editar recebimento;
   - Categorias: logo;
   - Configurações: importar e exportar;
   - moldura: sino de alertas;
   - Importar cartão: vincular a uma recorrência escolhida.
6. **Desktop sem versão mobile:** Financiamentos, Patrimônio, Documentos, Mobilidade, Categorias, Configurações, Importação, Dashboard e Consórcios. Não estavam previstos na série mobile.
7. **Relatórios e exportações a implementar:** Excel e PDF de IR, Excel e PDF de saídas sem documento, ZIP da Empresa, demonstrativo anual do financiamento. O relatório de bens do Patrimônio (Excel e PDF) já existe.
8. **Pendências técnicas, de segurança ou integridade:** seção 5.
9. **Divergência entre GitHub, Supabase e Cloudflare:** nenhuma. Há divergência **documental**: o `ROADMAP` e documentos antigos descrevem o Render e migrations pendentes.
10. **Ações para concluir:** `FIN_AUDITORIA_PLANO_REGULARIZACAO_01.md`, REG-01 a REG-15.

## 4. Quadro consolidado

"Supabase ok" significa migrations aplicadas e funções idênticas ao repositório. "Cloudflare ok" significa arquivos servidos idênticos ao build.

| Módulo | Código | Supabase | Cloudflare | Homologação | Pendência | Prioridade |
|---|---|---|---|---|---|---|
| Acesso e Perfis | completo | ok | ok | em uso; gestão de perfis sem uso registrado | Homologar a gestão de perfis | P3 |
| Dashboard | resumo completo | ok | ok | em uso | Sino de alertas não migrado | P3 |
| Despesas | completo | ok | ok | em uso (813 contas) | Consolidar fatura não migrado | P2 |
| Pagamentos (individual e lote) | completo | ok | ok | homologado | — | — |
| Receitas | núcleo completo | ok | ok | em uso | Editar recebimento; receber sem fonte | P3 |
| Cartões | completo | ok | ok | em uso (171 compras) | Itens e orçamentos do Flask: não comprovado | P3 |
| Importação de cartão | completo | ok | ok | em uso | Vincular linha a uma recorrência escolhida | P3 |
| Recorrências | completo | ok | ok | em uso (28 ativas) | — | — |
| Consórcios | completo | ok | ok | em uso (7 contratos) | — | — |
| Contas bancárias | completo | ok | ok | em uso | — | — |
| Lançamentos | completo | ok | ok | em uso | Receita fica na tela Receitas | P3 |
| Financiamentos | motor completo | ok | ok | em uso (1 contrato) | Documentos e conferências da Caixa; demonstrativo anual; valores simulados; página de seguro | P2 |
| Indexadores | TR completa | ok | ok | em uso (30 competências) | Genéricos fora do escopo | — |
| Patrimônio | completo | ok | ok | **sem uso real** | Homologar | P3 |
| Mobilidade | completo | ok | ok | homologado | — | — |
| Documentos Fiscais | núcleo completo; 6 operações não migradas e 3 parciais | ok | ok | 9 em uso; 12 sem uso real | Relatórios, ZIP, OCR, NFS-e, cupom, classificação no envio | P2 |
| Categorias | completo | ok | ok | em uso | Logo de categoria | P3 |
| Configurações | preferências | ok | ok | sem uso registrado | Importar e exportar configurações | P3 |
| Relatórios | só o de bens do Patrimônio | ok | ok | sem uso | Os de documentos e de financiamento | P2 |
| Backup | ferramenta pronta e ensaiada | — | — | **nenhum backup real** | Gerar, guardar e testar a restauração | **P1** |
| Segurança | RLS, funções e CSP conferidos | ok | ok | — | Colunas legadas de cartão (vazias) | P3 |
| Mobile e PWA | 9 páginas e PWA | ok | ok | 01 a 08 homologados; 09, 10 e ícones publicados sem conferência em produção | Conferir com login; reinstalar no iPhone | P3 |

## 5. Riscos de segurança e integridade

| # | Risco | Evidência | Prioridade |
|---|---|---|---|
| 1 | **Sem backup comprovado da produção**, o que inclui os documentos, que ficam no banco. A ferramenta existe, mas nunca gerou um backup real. A retenção dos backups gerenciados do Supabase depende do plano e não foi verificável | `FIN_BLOCO_D_2.md:37`; `FIN_BLOCO_D_3.md:13`; Infraestrutura, seção 8 | **P1** |
| 2 | Exclusão de documento é física e apaga os eventos: não sobra trilha | migration `20261202090000`:417-420 | P3 |
| 3 | O hash dos documentos é gravado, mas nunca reconferido | migration `20261118090000`:31-36 | P3 |
| 4 | Colunas legadas de número de cartão, CVV e validade continuam na tabela, **sem dados sensíveis hoje** | consulta por contagem; Infraestrutura, seção 5 | P3 |
| 5 | 58 itens de consórcio inativos sem perfil (resíduo histórico, invisível nas telas) | consulta | P3 |
| 6 | Documentação desatualizada pode induzir a reaplicar migrations ou a retomar o Render | Infraestrutura, seção 7 | P3 |

**Conferido e sem problema**
- RLS ligada em todas as 88 tabelas.
- Nenhum acesso anônimo a tabela ou função.
- Nenhuma escrita direta em tabela: tudo passa por função que confere o perfil.
- 475 funções `SECURITY DEFINER`, todas com `search_path` fixo.
- Escritor único por perfil (NOVO).
- Sem CVV nem número completo de cartão.
- Documentos acessíveis só por função com conferência de perfil.
- Chave do site apenas publicável; CSP restritiva.
- A conta de teste B permanece banida.

## 6. Listas pedidas no contrato

1. **Concluídas (42):** linhas CONCLUÍDO da matriz B e operações 1 a 6, 11, 12 e 29 de Documentos.
2. **Parcialmente migradas (6):**
   - recebimentos: editar, receber sem fonte, excluir;
   - receita pela tela Lançamentos;
   - página de Seguro habitacional;
   - vínculos de documentos com financiamentos;
   - classificação documental no envio;
   - integridade dos arquivos.
3. **Não migradas (13):**
   - alertas do sino;
   - consolidar fatura;
   - vincular linha da importação a uma recorrência;
   - documentos e conferências do financiamento;
   - demonstrativo anual e valores simulados;
   - logo de categoria;
   - importar e exportar configurações;
   - NFS-e;
   - cupom fiscal;
   - OCR;
   - relatórios de IR;
   - relatórios de lastro;
   - ZIP da Empresa.
4. **Não publicadas:** nenhuma funcionalidade. Só o commit local de documentação e estes cinco documentos.
5. **Migrations pendentes ou divergentes:** nenhuma.
6. **Dependem de capacidade que só o Flask tinha** (servidor):
   - OCR com Tesseract e Poppler;
   - geração de Excel, PDF e ZIP dos documentos;
   - arquivos em disco: documentos de financiamento e logos de categoria;
   - `pg_dump` pela tela de backup.

   Nenhuma delas faz o aplicativo atual chamar o Flask: todas respondem "não disponível".
7. **Riscos:** seção 5.
8. **Backups:** NÃO COMPROVADO (Infraestrutura, seção 8).
9. **Plano em ordem:** documento E. Começa por REG-01 (backup), segue por REG-03 a REG-09 (lacunas P2) e REG-10 (homologações).

## 7. Limitações da auditoria

- Não houve teste funcional com login em produção: o contrato proíbe gravações, e a sessão é do titular.
- O plano do Supabase e os backups gerenciados não são verificáveis por SQL; é preciso conferir no painel.
- A suíte de testes de banco (998 testes) não foi reexecutada, por espaço em disco. Rodaram hoje os testes unitários (120 de 120) e os de navegador (255 de 255).
- Linha 23 da matriz (itens e orçamentos do cartão): não verifiquei se a tela original ainda chama essas rotas.

## 8. Recomendação

1. **Fazer o backup real e o teste de restauração (REG-01)** antes de qualquer nova migration. É o único item que protege contra perda de dados.
2. Escolher, entre as lacunas P2, as que têm uso para o titular. Os relatórios e o ZIP de documentos (REG-03 e REG-04) são os de menor risco e reaproveitam o que já existe.
3. Decidir sobre a consolidação de fatura (REG-07) e o OCR (REG-09): implementar ou retirar da tela.
4. Homologar o que está publicado sem uso (REG-10) e atualizar o `ROADMAP` (REG-14).
