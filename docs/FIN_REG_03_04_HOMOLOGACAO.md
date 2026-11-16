# FIN-REG-03/04 — Relatório integrado de homologação

**Data:** 15/11/2026. **Situação:** os dois MVPs estão implementados e testados localmente. O titular aprovou a homologação técnica com três pontos; os três estão tratados (seção 9). Nada foi publicado: sem push, sem deploy, sem migration.

Detalhes de cada entrega: `docs/FIN_REG_03_RELATORIOS_FISCAIS.md` e `docs/FIN_REG_04_ZIP_EMPRESA.md`.

## 1. Resumo

| Entrega | Situação | Comparação com o Flask |
|---|---|---|
| REG-03: Excel do Imposto de Renda | Funcional | Planilha idêntica |
| REG-03: PDF do Imposto de Renda | Funcional, com botão nos dois perfis | Byte a byte |
| REG-03: Excel de saídas sem documento | Funcional | Planilha idêntica |
| REG-03: PDF de saídas sem documento | Funcional | Byte a byte |
| REG-04: ZIP dos documentos da Empresa | Funcional | Lista, pastas, bytes e índice idênticos |

Os dois MVPs têm código, testes e commits separados e podem ser homologados individualmente.

## 2. Arquivos criados e modificados

| Arquivo | MVP | Mudança |
|---|---|---|
| `web/src/js/relatorio-fiscal.js` | REG-03 | Novo: monta os três relatórios |
| `web/src/js/zip-documentos.js` | REG-04 | Novo: monta o pacote, o índice e as conferências |
| `web/src/js/exportacao-xlsx.js` | Ambos | Duas variantes de formatação de planilha; o empacotador ZIP passa a ser exportado e aceita a data das entradas |
| `web/src/js/documentos-fiscais-adaptador.js` | Ambos | Rotas dos relatórios e do pacote; clique de "Exportar", "Excel" e "PDF"; sai o aviso de relatório indisponível |
| `tests/test_relatorios_fiscais.py` | REG-03 | Novo: comparação com o Flask |
| `tests/test_zip_documentos_empresa.py` | REG-04 | Novo: comparação com o Flask |
| `web/tests/e2e/reg03_relatorios_fiscais.spec.mjs` | REG-03 | Novo: navegador |
| `web/tests/e2e/reg04_zip_empresa.spec.mjs` | REG-04 | Novo: navegador |
| `web/tests/e2e/documentos_fiscais_tela.spec.mjs` | REG-03 | Ajuste: "Exportar" agora baixa o relatório |
| `web/src/paginas/documentos-fiscais.html` | REG-03 | Ajuste autorizado: "Excel" e "PDF" visíveis também no perfil Pessoal (três linhas) |
| `web/src/css/documentos-fiscais-adaptacoes.css` | REG-03 | Ajuste autorizado: altura compacta dos dois botões no Pessoal (uma regra) |
| `docs/FIN_REG_03_RELATORIOS_FISCAIS.md`, `docs/FIN_REG_04_ZIP_EMPRESA.md`, este arquivo, `docs/ROADMAP.md` | — | Documentação |

**Não foram alterados:** a tela original (`imposto_renda.js` e o CSS dela), as demais páginas, o Flask (`backend/`), as migrations (`supabase/`) e qualquer função de gravação. Na página de Documentos Fiscais mudou só a visibilidade dos dois botões, com autorização.

## 3. Funções reutilizadas

| Recurso | Uso |
|---|---|
| `exportacao-xlsx.js` (`gerarXlsx`, empacotador ZIP) | Planilhas dos relatórios, índice do pacote e o próprio ZIP |
| `exportacao-pdf.js` (`pdfSimples`) | Os três PDFs |
| `documentos-fiscais-adaptador.js` | Rotas, no mesmo mecanismo das demais |
| `ponte-api.js` | Entrega do arquivo gerado, como já fazia para o relatório de patrimônio |
| `ir_comprovantes_tela` | Lista de documentos (relatórios e pacote) |
| `vinculos_documento_tela` | Vínculos ativos (aba "Lastros", índice) |
| `lastro_saidas_tela` | Saídas sem documento |
| `arquivo_comprovante_tela` | Bytes de cada documento do pacote |
| `ir_contexto_tela`, `ir_categorias_tela` | Já usadas pela tela; não foram necessárias para os relatórios |

`relatorio-patrimonio.js` serviu de modelo e continua intacto.

## 4. Funções novas e migrations

**Nenhuma função nova no banco e nenhuma migration.** As consultas publicadas já devolvem tudo o que os relatórios e o pacote precisam, sem paginação.

## 5. Resultado dos testes

| Bateria | Selecionada por | Resultado |
|---|---|---|
| `tests/test_relatorios_fiscais.py` | REG-03 | 6 aprovados, 0 falhas (um novo: vínculo mais recente) |
| `tests/test_zip_documentos_empresa.py` | REG-04 | 5 aprovados, 0 falhas |
| `tests/test_relatorios_patrimonio.py` | Regressão do gerador de planilhas | 2 aprovados, 0 falhas |
| Testes unitários do site (`npm run test:unit`, inclui o build de produção) | Regressão | 120 aprovados, 0 falhas |
| `reg03_relatorios_fiscais.spec.mjs` | REG-03 | 2 aprovados, 0 falhas (agora com os botões do Pessoal e as medidas de posição) |
| `reg04_zip_empresa.spec.mjs` | REG-04 | 3 aprovados, 0 falhas |
| Suíte completa de navegador | Regressão integrada | 260 aprovados, 0 falhas (eram 255 antes; +5 dos dois MVPs) |
| Documentos Fiscais, Lastro, Documento financeiro e Patrimônio, de novo, depois da correção do botão | Regressão | 20 aprovados, 0 falhas |
| **Depois dos ajustes de 15/11/2026** (botões no Pessoal e vínculo mais recente): comparação com o Flask (relatórios, ZIP, patrimônio) | Ajustes | 13 aprovados, 0 falhas |
| **Depois dos ajustes:** navegador, as 8 baterias afetadas (REG-03, REG-04, Documentos Fiscais, Lastro, Documento financeiro, Patrimônio, migração P0/P1 e moldura) | Ajustes | 33 aprovados, 0 falhas |
| **Depois dos ajustes:** unitários do site, com o build de produção | Ajustes | 120 aprovados, 0 falhas |

A suíte de navegador cobre Documentos Fiscais, Lastro da Empresa, Despesas, Lançamentos, Patrimônio, Financiamentos, autenticação, perfis e as telas do celular.

**Dispensados, com o motivo:** os testes de banco das funções de documentos, lastro e arquivo (`test_supabase_documentos_*`, `test_supabase_lastro_*`, `test_supabase_arquivo_comprovante`) e os testes do Flask. Nenhum arquivo de `supabase/` nem de `backend/` foi alterado.

Durante o desenvolvimento, o teste unitário que proíbe `innerHTML` no código próprio do site acusou um uso meu no botão do relatório. Corrigi antes do fechamento; a suíte unitária está em 120 de 120.

## 6. Comparação com o Flask

Método: cada arquivo é gerado pelo próprio Flask (`IrRelatorioService`, `LastroRelatorioService`, `DocumentoZipService`) e pelo novo aplicativo sobre a mesma base fictícia, num PostgreSQL descartável, com a hora de geração fixada nos dois lados.

| Item | Consultas comparadas | Critério | Resultado |
|---|---|---|---|
| PDF do IR (Pessoal e Empresa) | 16 | Byte a byte | Idêntico |
| Excel do IR (Pessoal e Empresa) | 16 | Valores, formatos, cabeçalhos, larguras, painel, autofiltro | Idêntico |
| PDF de saídas | 9 | Byte a byte | Idêntico |
| Excel de saídas | 9 | Idem | Idêntico |
| ZIP da Empresa | 10 | Lista e ordem dos arquivos, pastas, bytes, índice | Idêntico |
| Recusas (ano e mês inválidos, perfil não Empresa, sem documentos) | 6 | Mesmo código e mesma mensagem | Idêntico |

Diferenças, todas de forma e justificadas:
1. Planilhas e ZIP sem compressão interna (gerador próprio, sem biblioteca). O conteúdo é o mesmo.
2. No índice do pacote, documento sem classificação gravada sai como "Não classificado", e não "Outro" / "Sem categoria". É a classificação do novo aplicativo, já homologada na tela.
3. Acréscimos pedidos pelo contrato, que o Flask não tinha: conferência de SHA-256 e tamanho, e limites de volume.

4. Documento com mais de um vínculo ativo: o relatório mostra o vínculo mais recente (decisão do titular); o Flask mostrava o primeiro gravado.

Fora o item 4, nenhuma diferença de conteúdo, agrupamento ou total nos relatórios.

## 7. Evidências de que os dados não foram alterados

- **Nos testes:** o resumo de todas as tabelas (contagem e conteúdo) é comparado antes e depois de gerar todos os relatórios e todos os pacotes. É idêntico.
- **No código:** as rotas novas chamam só quatro funções do banco, todas de consulta e declaradas como somente leitura (`stable`). Nenhuma rota de gravação foi tocada; a diferença no adaptador é só de acréscimo.
- **No repositório:** `supabase/` e `backend/` sem nenhuma alteração.
- **Na produção:** nada foi executado. Nenhum relatório real foi gerado, conforme o contrato.

## 8. Impacto no build

| Item | Valor |
|---|---|
| Arquivos novos no site | 2 (`relatorio-fiscal.js`, 21 KB; `zip-documentos.js`, 13 KB) |
| Arquivos alterados no site | 2 |
| Bibliotecas novas | Nenhuma |
| Páginas, CSS, CSP | Página de Documentos Fiscais: três linhas de HTML e uma regra de CSS (visibilidade dos botões). CSP sem mudança |
| Carregamento | Os módulos novos só são carregados na página de Documentos Fiscais |
| Teste do build de produção | Aprovado (dentro da suíte unitária) |

## 9. Decisões do titular e ajustes feitos (15/11/2026)

| Ponto | Decisão | Situação |
|---|---|---|
| PDF do IRPF sem botão no perfil Pessoal | Disponibilizar "Excel" e "PDF" também no Pessoal, com os mesmos botões compactos, sem novas barras nem espaços | **Feito** |
| Classificação dos documentos (filtro por tipo vale sobre a classificação gravada; "Não classificado" no índice do ZIP) | Manter por enquanto e documentar; a classificação automática no envio fica para o FIN-REG-08 | **Mantido e documentado** |
| Documento com mais de um vínculo | O relatório deve usar o vínculo ativo mais recente, como a lista da tela | **Feito** |

### Botões no perfil Pessoal

- Mudança de visibilidade: três linhas no HTML da página e uma regra de estilo. Nenhum botão novo.
- "Filtros avançados" e "ZIP" continuam só na Empresa.
- Conferido no navegador, por medida: no Pessoal, "Excel" e "PDF" têm 32 x 32 px, ficam na mesma linha, dentro do cabeçalho do painel e à direita do título, e a altura do cabeçalho é a mesma com e sem os botões. Na Empresa, os quatro controles continuam na mesma linha e o cabeçalho mede 49 px, o mesmo valor medido antes da mudança.

### Vínculo mais recente

- Conferi antes de alterar, como pedido: **não existe no modelo de dados um vínculo marcado como "principal"**. O "principal" do relatório do Flask era apenas o primeiro que o banco devolvia. O mais recente já era o critério da lista da tela, da consulta do banco e do índice do ZIP. Não há, portanto, diferença entre "mais recente" e "principal" a apontar.
- A alteração ficou restrita à ordem em que a tela entrega os vínculos ao gerador do relatório. O banco não mudou e os vínculos históricos seguem intactos; a aba "Lastros" continua listando todos.
- Teste novo: em todos os documentos, a natureza e a situação do lastro do relatório são iguais às da lista da tela; no documento com dois vínculos, o relatório mostra o mais recente, e a ordem antiga mostraria o outro.
- Para os documentos com um vínculo só, o relatório continua idêntico ao do Flask, byte a byte no PDF.

### Comportamentos mantidos

- Sem registros, o relatório é gerado com totais zerados (regra do Flask). O pacote ZIP, ao contrário, recusa com mensagem (também regra do Flask).

## 10. Limitações

- PDFs textuais simples, com limite de 80 documentos ou 90 saídas listados, como no Flask.
- Pacote ZIP limitado a 1.000 documentos, 40 MB por arquivo e 250 MB no total; acima disso, gerar em partes pelos filtros.
- OCR de imagem e categorias de IR continuam indisponíveis; os avisos foram mantidos.
- A homologação técnica usou só dados fictícios. A conferência com os documentos reais cabe ao titular, depois da publicação.

## 11. Necessidade de publicação

- **O que publicar:** só o site (Cloudflare Pages). Quatro arquivos de `web/src/js`.
- **Migration:** nenhuma.
- **Supabase:** nenhuma mudança.
- **Antes de publicar:** não há migration, então o backup `PRE_MIGRATION` não se aplica; o backup semanal de 15/11/2026 está válido.
- A publicação depende de autorização específica do titular.

## 12. Plano de reversão

1. Republicar o deploy anterior do Cloudflare Pages (`45e24f88`).
2. Não há nada a desfazer no banco.
3. No repositório, reverter os commits do REG-03 e do REG-04, que são independentes: o REG-04 pode ser revertido sozinho; o REG-03 também, desde que o REG-04 saia junto (o pacote usa o gerador de planilhas estendido no REG-03).

## 13. Critérios de aceite

**REG-03**

| Critério | Situação |
|---|---|
| Excel de Imposto de Renda funcional | Atendido |
| PDF de Imposto de Renda funcional | Atendido, com botão nos dois perfis |
| Excel de saídas sem documento funcional | Atendido |
| PDF de saídas sem documento funcional | Atendido |
| Filtros preservados | Atendido |
| Agrupamentos e totais conferidos | Atendido |
| Arquivos válidos | Atendido |
| Isolamento entre perfis | Atendido |
| Comparação com o Flask aprovada | Atendido |
| Nenhuma alteração financeira | Atendido |
| Interface preservada | Atendido: só a visibilidade de "Excel" e "PDF" no Pessoal, autorizada |

**REG-04**

| Critério | Situação |
|---|---|
| Exportação ZIP funcional | Atendido |
| Organização conforme o Flask | Atendido |
| Índice documental correto | Atendido |
| Todos os arquivos autorizados incluídos | Atendido |
| Arquivos sem alteração de conteúdo | Atendido |
| Duplicidades de nome tratadas | Atendido |
| Integridade conferida | Atendido |
| Limites de tamanho tratados | Atendido |
| Acesso restrito ao perfil Empresa | Atendido |
| Nenhuma alteração no banco | Atendido |
| Interface preservada | Atendido |

## 14. Commits locais

| Commit | Conteúdo |
|---|---|
| `b974526` | REG-03: relatórios fiscais, testes |
| `5c1c1ef` | REG-04: pacote ZIP, testes |
| `191755d` | REG-03: botão do relatório sem `innerHTML` |
| `9806c7f` | Documentação dos dois MVPs e ROADMAP |
| (seguintes) | Ajustes de 15/11/2026: botões no Pessoal e vínculo mais recente; documentação dos ajustes |

Ramo local `reg-03-04-relatorios-fiscais`, a partir de `1386088` (documentação do encerramento do REG-02, também só local).

Nenhum foi enviado ao GitHub.
