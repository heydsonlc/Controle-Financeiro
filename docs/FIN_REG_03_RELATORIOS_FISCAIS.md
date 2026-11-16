# FIN-REG-03 — Relatórios fiscais em Excel e PDF

**Situação em 15/11/2026:** implementado e testado localmente, com dados fictícios, em bancos descartáveis. **Aguarda a homologação do titular.** Nada foi publicado: sem push, sem deploy e sem migration (nenhuma foi necessária).

## 1. O que foi entregue

| Relatório | Perfil | Formatos | Referência no Flask |
|---|---|---|---|
| Imposto de Renda (comprovantes) | Pessoal | Excel e PDF | `IrRelatorioService` |
| Documentos Fiscais e Lastro | Empresa | Excel e PDF | `IrRelatorioService` |
| Saídas sem documento | Empresa | Excel e PDF | `LastroRelatorioService` |

Os arquivos são gerados no navegador. Não há chamada ao Flask nem a serviço externo, e nada é gravado no banco.

## 2. Como usar na tela

Nenhum controle foi criado. Os botões já existentes de Documentos Fiscais passaram a funcionar:

| Botão | Onde | O que gera |
|---|---|---|
| **Exportar** | Barra de ações, nos dois perfis | Excel do relatório, com os filtros da lista |
| **Excel** e **PDF** | Painel da lista de documentos, perfil Empresa | Relatório de Documentos Fiscais e Lastro |
| **Excel** e **PDF** | Painel "Saídas sem documento", perfil Empresa | Relatório de saídas sem documento |

O relatório usa os filtros da lista em tela: ano, situação, categoria, busca e, na Empresa, tipo e categoria documental, validade e obrigatoriedade. As saídas usam os filtros do próprio painel: ano, mês, origem, situação, natureza, valor mínimo e busca.

Nomes dos arquivos, iguais aos do Flask:

- `IRPF_<ano>_<perfil>.xlsx` e `.pdf`
- `Documentos_Fiscais_<ano>_<perfil>.xlsx` e `.pdf`
- `Saidas_sem_documento_<perfil>_<ano>[_<mês>].xlsx` e `.pdf`

### Ressalva: PDF do Imposto de Renda no perfil Pessoal

Na tela original do Flask, os botões "Excel" e "PDF" do painel só aparecem no modo Empresa. No perfil Pessoal existe apenas "Exportar", que gera o Excel. **O PDF do IRPF está implementado e testado, mas não tem botão visível no perfil Pessoal**, exatamente como no Flask. O contrato proíbe acrescentar botões, por isso não acrescentei. Se o titular quiser o PDF acessível no perfil Pessoal, a mudança é pequena: mostrar ali os dois botões que já existem no painel. Depende de decisão.

## 3. Conteúdo dos relatórios

Reproduz o Flask, aba por aba e linha por linha.

**Imposto de Renda (Pessoal)**
- Aba "Resumo": perfil, ano, total de comprovantes, valor potencialmente dedutível, validados, pendentes, erros de leitura, data de geração e totais por Categoria IR.
- Aba "Comprovantes": uma linha por comprovante, com 14 colunas.
- O "valor potencialmente dedutível" soma tudo que não está marcado como não dedutível. É a regra do Flask; o relatório não presume dedutibilidade e traz o aviso de que ela deve ser validada pelo contador.

**Documentos Fiscais e Lastro (Empresa)**
- Aba "Resumo": totais, documentos vinculados e sem vínculo, aguardando contador e totais por Categoria Fiscal e Natureza.
- Aba "Documentos": uma linha por documento, com 12 colunas.
- Aba "Lastros": uma linha por vínculo ativo.
- O PDF traz ainda a seção "Pendências".

**Saídas sem documento (Empresa)**
- Aba "Resumo": totais e agrupamentos por origem, natureza e situação.
- Aba "Saidas_sem_documento": uma linha por saída, com 11 colunas.
- Aba "Pendencias_contador": as saídas aguardando contador, pendentes ou divergentes.

Comportamentos herdados do Flask e mantidos:
- Sem registros para o filtro, o relatório é gerado assim mesmo, com os totais zerados. Não é erro.
- O PDF lista no máximo 80 documentos (IR) ou 90 saídas; o Excel traz todos.
- O PDF tem uma página lógica só e corta cada linha em 115 caracteres.

## 4. Arquitetura

```
filtros da tela → consultas já publicadas → relatorio-fiscal.js → exportacao-xlsx.js / exportacao-pdf.js → download
```

| Arquivo | Papel |
|---|---|
| `web/src/js/relatorio-fiscal.js` (novo) | Monta os três relatórios. Funções puras, sem rede |
| `web/src/js/exportacao-xlsx.js` (alterado) | Gerador de planilhas já existente, com duas variantes de formatação novas |
| `web/src/js/exportacao-pdf.js` (sem mudança) | Gerador de PDF já existente |
| `web/src/js/documentos-fiscais-adaptador.js` (alterado) | Rotas dos relatórios e o clique dos botões "Exportar", "Excel" e "PDF" |

Consultas reutilizadas, todas já publicadas e só de leitura:

| Consulta | Uso |
|---|---|
| `ir_comprovantes_tela` | Lista completa do filtro; não pagina |
| `vinculos_documento_tela` | Vínculos ativos dos documentos que têm vínculo, para a aba "Lastros" e o vínculo principal |
| `lastro_saidas_tela` | Saídas sem documento; não pagina |

**Nenhuma função nova e nenhuma migration.** O endpoint de resumo do Flask (`/api/ir/relatorios/resumo`) também foi atendido pela mesma base, embora a tela não o chame.

**Paginação:** as três consultas devolvem o conjunto inteiro do filtro. A paginação da tela é só visual, feita no navegador. O relatório não fica limitado à primeira página.

**Vínculo principal:** o relatório do Flask usa o primeiro vínculo ativo do documento na ordem de gravação. A lista da tela mostra o mais recente. Para manter a fidelidade ao relatório original, uso a ordem de gravação. Só há diferença quando um documento tem mais de um vínculo ativo.

## 5. Tratamento de erros

| Situação | Resultado |
|---|---|
| Nenhum registro para o filtro | Relatório gerado com totais zerados, como no Flask |
| Ano ou mês inválido | Recusa com a mensagem do Flask ("Ano do relatorio invalido", "Mes do relatorio invalido"); nenhum arquivo |
| Saídas sem documento fora do perfil Empresa | Recusa: "Relatorio de lastro empresarial disponivel apenas no perfil Empresa." O banco também recusa a consulta |
| Conta sem acesso ao perfil | O banco recusa a consulta; nenhum arquivo |
| Falha na consulta | Mensagem do aplicativo, sem detalhe interno; nenhum arquivo |
| Falha ao montar a planilha ou o PDF | "Não foi possível gerar o relatório. Nada foi alterado." |

Nenhuma falha grava dado.

## 6. Testes

Executados em 15/11/2026.

| Bateria | Resultado |
|---|---|
| `tests/test_relatorios_fiscais.py` (comparação com o Flask) | 5 aprovados, 0 falhas |
| `web/tests/e2e/reg03_relatorios_fiscais.spec.mjs` (navegador) | 2 aprovados, 0 falhas |
| `web/tests/e2e/documentos_fiscais_tela.spec.mjs` (ajustado: "Exportar" agora baixa) | aprovado |
| `tests/test_relatorios_patrimonio.py` (regressão do gerador de planilhas) | 2 aprovados, 0 falhas |

### Comparação com o Flask

Cada relatório foi gerado pelo próprio Flask e pelo novo aplicativo sobre a mesma base fictícia, com a hora de geração fixada nos dois lados.

| Conferência | Critério | Resultado |
|---|---|---|
| PDF | Byte a byte | Idêntico em todas as consultas |
| Excel: abas e valores | Lidos pelo openpyxl, célula a célula | Idênticos |
| Excel: formato de cada célula | Moeda só em valores, nunca em contagens | Idêntico |
| Excel: cabeçalhos | Linha 1 e rótulos no meio da aba | Idênticos |
| Excel: quebra de linha, painel congelado, autofiltro e larguras | — | Idênticos |
| Nome do arquivo | — | Idêntico |

Consultas comparadas:
- **IR Pessoal (8):** ano; busca com acento; situação; não dedutíveis; só validados; só pendentes; ano sem documentos; sem filtro.
- **Empresa (8):** ano; busca; situação do lastro; natureza; tipo de entidade; só pendentes; tipo documental; ano sem documentos.
- **Saídas (9):** ano; todas as situações; mês; valor mínimo; busca; aguardando contador; origem; natureza; ano sem saídas.

O cenário inclui valores com centavos, documento sem valor, sem prestador, sem categoria, dedutível indefinido, nome com acento e com caracteres especiais, documento com dois vínculos e saída com situação manual.

### Segurança

- Saídas sem documento no perfil Pessoal: 403 no Flask e recusa do banco no novo aplicativo.
- Conta sem acesso ao perfil, e requisição sem sessão: recusa do banco.
- Documentos de um perfil nunca aparecem no relatório do outro.
- Vínculos de documento de outro perfil e documento inexistente: "não encontrado".

### Nenhuma alteração de dados

Antes e depois de gerar todos os relatórios, o resumo de todas as tabelas (contagem e conteúdo) é idêntico. As três consultas usadas são declaradas como somente leitura no banco.

## 7. Diferenças em relação ao Flask

| Diferença | Motivo |
|---|---|
| A planilha é gravada sem compressão interna | O gerador próprio do aplicativo não usa biblioteca. O conteúdo lido é idêntico; o arquivo fica um pouco maior |
| Células vazias de texto não são gravadas | O Flask grava texto vazio. Ao abrir, o resultado é o mesmo |
| Filtros da Empresa por tipo, categoria, validade e obrigatoriedade | Mesma regra do Flask: valem sobre a classificação gravada |

Não há diferença de conteúdo, agrupamento ou total.

## 8. Limitações

- O PDF do IRPF não tem botão no perfil Pessoal (seção 2).
- O PDF é um relatório textual simples, igual ao do Flask: sem tabelas, com corte de linhas longas e limite de 80 ou 90 itens.
- Com centenas de documentos vinculados, a consulta de vínculos é feita em grupos de oito e leva alguns segundos.
- O OCR de imagem e as categorias de IR continuam indisponíveis nesta versão; os avisos foram mantidos.

## 9. Publicação e reversão

- **Publicação:** só arquivos do site (`web/src/js`). Não há migration. Depende de autorização específica.
- **Reversão:** republicar o deploy anterior no Cloudflare Pages. Como não há mudança no banco, não há o que desfazer nele.
