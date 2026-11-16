# FIN-REG-03/04 — Relatório integrado de homologação

**Data:** 15/11/2026. **Situação:** os dois MVPs estão implementados e testados localmente. **Aguardam a homologação do titular.** Nada foi publicado: sem push, sem deploy, sem migration.

Detalhes de cada entrega: `docs/FIN_REG_03_RELATORIOS_FISCAIS.md` e `docs/FIN_REG_04_ZIP_EMPRESA.md`.

## 1. Resumo

| Entrega | Situação | Comparação com o Flask |
|---|---|---|
| REG-03: Excel do Imposto de Renda | Funcional | Planilha idêntica |
| REG-03: PDF do Imposto de Renda | Funcional, com ressalva (seção 9) | Byte a byte |
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
| `docs/FIN_REG_03_RELATORIOS_FISCAIS.md`, `docs/FIN_REG_04_ZIP_EMPRESA.md`, este arquivo, `docs/ROADMAP.md` | — | Documentação |

**Não foram alterados:** páginas HTML, CSS, a tela original (`imposto_renda.js`), o Flask (`backend/`), as migrations (`supabase/`) e qualquer função de gravação.

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
| `tests/test_relatorios_fiscais.py` | REG-03 | 5 aprovados, 0 falhas |
| `tests/test_zip_documentos_empresa.py` | REG-04 | 5 aprovados, 0 falhas |
| `tests/test_relatorios_patrimonio.py` | Regressão do gerador de planilhas | 2 aprovados, 0 falhas |
| Testes unitários do site (`npm run test:unit`, inclui o build de produção) | Regressão | 120 aprovados, 0 falhas |
| `reg03_relatorios_fiscais.spec.mjs` | REG-03 | 2 aprovados, 0 falhas |
| `reg04_zip_empresa.spec.mjs` | REG-04 | 3 aprovados, 0 falhas |
| Suíte completa de navegador | Regressão integrada | 260 aprovados, 0 falhas (eram 255 antes; +5 dos dois MVPs) |
| Documentos Fiscais, Lastro, Documento financeiro e Patrimônio, de novo, depois da correção do botão | Regressão | 20 aprovados, 0 falhas |

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

Nenhuma diferença de conteúdo, agrupamento ou total nos relatórios.

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
| Páginas, CSS, CSP | Sem mudança |
| Carregamento | Os módulos novos só são carregados na página de Documentos Fiscais |
| Teste do build de produção | Aprovado (dentro da suíte unitária) |

## 9. Ressalvas e decisões pedidas ao titular

1. **PDF do IRPF no perfil Pessoal não tem botão.** Na tela original, "Excel" e "PDF" do painel só aparecem na Empresa; no Pessoal há apenas "Exportar" (Excel). O PDF está pronto e testado, mas inacessível pela tela nesse perfil, como no Flask. Decidir: manter assim, ou mostrar os dois botões já existentes também no perfil Pessoal (mudança pequena, de visibilidade).
2. **Vínculo principal do relatório.** Com mais de um vínculo ativo no mesmo documento, o relatório usa o primeiro gravado (regra do Flask), e a lista da tela mostra o mais recente. Mantive a regra do relatório original.
3. **Filtro por tipo documental.** Vale sobre a classificação gravada, como no Flask. Documento recém-enviado e não revisado não aparece nas abas por tipo, nem no pacote filtrado por tipo.
4. **Sem registros, o relatório é gerado com totais zerados** (regra do Flask). O pacote ZIP, ao contrário, recusa com mensagem (também regra do Flask).

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
| PDF de Imposto de Renda funcional | Atendido; sem botão no perfil Pessoal (ressalva 1) |
| Excel de saídas sem documento funcional | Atendido |
| PDF de saídas sem documento funcional | Atendido |
| Filtros preservados | Atendido |
| Agrupamentos e totais conferidos | Atendido |
| Arquivos válidos | Atendido |
| Isolamento entre perfis | Atendido |
| Comparação com o Flask aprovada | Atendido |
| Nenhuma alteração financeira | Atendido |
| Interface preservada | Atendido: nenhum HTML ou CSS alterado |

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
| (seguinte) | Documentação dos dois MVPs e ROADMAP |

Ramo local `reg-03-04-relatorios-fiscais`, a partir de `1386088` (documentação do encerramento do REG-02, também só local).

Nenhum foi enviado ao GitHub.
