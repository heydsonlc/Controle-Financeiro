# FIN-MOBILE-11 e FIN-MOBILE-12 — Documentos Fiscais e Mobilidade no celular

**Data:** 15/11/2026. **Situação:** implementado e testado localmente, com dados fictícios, em banco descartável. **Aguarda a homologação do titular.** Sem push, sem deploy e sem migration (nenhuma foi necessária).

**Identificação.** O contrato conjunto chamava as entregas de "FIN-REG-08/09 + MOBILE-10/11". Por decisão do titular, ficaram assim:

| Identificação | Entrega | Situação |
|---|---|---|
| FIN-MOBILE-11 | Documentos Fiscais no celular | Este documento |
| FIN-MOBILE-12 | Mobilidade no celular | Este documento |
| FIN-REG-08 | Leitura e classificação automática de documentos | Contrato próprio, ainda não iniciado |

O escopo funcional do contrato conjunto foi mantido. Este arquivo substitui o nome previsto no contrato (`FIN_REG_08_09_MOBILE_DOCUMENTOS_MOBILIDADE.md`), para não confundir com o FIN-REG-08.

## 1. Escopo implementado

1. **Página Principal mobile:** dois atalhos novos, "Documentos" e "Mobilidade".
2. **Documentos Fiscais mobile:** lista, detalhe, lastro, revisão, validação, vínculo, saídas sem documento e exportações.
3. **Mobilidade mobile:** veículos, novo abastecimento, histórico e resumo do veículo.
4. **Desktop:** nenhuma mudança de tela nem de regra. As regras dos dois módulos passaram para serviços comuns ao desktop e ao celular, sem alteração de código.

Nenhuma regra financeira nova, nenhuma função nova no banco e nenhuma migration.

## 2. Inventário das telas

### Página Principal

A grade passou de 2 colunas por 4 linhas para 2 colunas por 5 linhas. Os atalhos novos ocupam a quinta linha, com as mesmas medidas dos demais (80 px de altura, mesmo espaçamento). Cabeçalho (ícone, "Financeiro", sino e perfil), competência e barra inferior não mudaram. Os nomes couberam sem ajuste.

### Documentos (FIN-MOBILE-11)

| Tela | Conteúdo |
|---|---|
| **Lista** | Cabeçalho com voltar, título, filtros e exportar. Ano com setas. Situação: Todos, Pendentes, Validados. Busca. Resumo de três valores. Linhas compactas com nome, data, classificação, valor e selo da situação |
| **Detalhe** | Cartão do arquivo (tipo, nome e tamanho), fornecedor, CPF/CNPJ, data, valor, classificação, situação e observações. Ações: Baixar, Lastro, Vincular e Revisar. Lista dos vínculos, com Desvincular |
| **Revisar** | Fornecedor, CPF/CNPJ, data, valor, ano-calendário, categoria e observações. Botão Validar |
| **Vincular** | Tipo de entidade, entidade, natureza, situação do lastro e observações |
| **Saídas sem documento** (só Empresa) | Mês com setas. Resumo: Pendentes, Com documento e Sem documento. Situação: Pendentes, Sem lastro, Todas. Lista com selo "Sem lastro", "Aguardando contador" ou "Justificado". No detalhe: Situação e Vincular documento |
| **Filtros** | Documentos: categoria e, na Empresa, tipo documental. Saídas: origem e valor mínimo |
| **Exportar** | Documentos: Excel, PDF e, na Empresa, ZIP. Saídas: Excel e PDF |

### Mobilidade (FIN-MOBILE-12)

| Tela | Conteúdo |
|---|---|
| **Veículos** | Um cartão compacto por veículo: quilometragem, combustível e o abastecido na competência. Ações: Abastecer, Histórico e Resumo. O "+" do cabeçalho abre um abastecimento sem veículo escolhido |
| **Novo abastecimento** | O formulário já homologado no Registrar Lançamento, aberto com o veículo escolhido: veículo, data, hodômetro, combustível, preço por litro, valor total, litros, descrição e meio de pagamento (conta a pagar ou cartão de crédito) |
| **Histórico** | Data, valor, hodômetro, combustível, litros, preço por litro e km rodados. Filtro: Todos ou o mês da competência. Anulados aparecem riscados |
| **Resumo** | Gasto do mês, consumo médio, custo por km, quilometragem, último abastecimento, gráfico de barras dos últimos seis meses e os cinco últimos abastecimentos |

## 3. Decisões tomadas

1. **Segmentação "Todos / IR / Empresa".** No sistema, cada perfil é pessoal ou Empresa; a mesma lista nunca mistura os dois. A tela mostra, portanto, o contexto do perfil ativo: "Comprovantes do Imposto de Renda" no perfil pessoal e "Documentos da Empresa" na Empresa. A segmentação visível é por situação (Todos, Pendentes, Validados) e, na Empresa, entre Documentos e Saídas sem documento.
2. **Documentos por ano, saídas por mês.** É como o desktop consulta: documentos pelo ano-calendário e saídas pelo mês. As setas mudam o ano numa visão e o mês na outra.
3. **Novo abastecimento reaproveitado.** O formulário de abastecimento do Registrar Lançamento já estava homologado no celular, com conta ou cartão. A Mobilidade abre esse mesmo formulário com o veículo escolhido. A única mudança nele foi aceitar o veículo já selecionado.
4. **Indicadores do resumo** (aprovados pelo titular com ressalva, já atendida). São somas de apresentação sobre o histórico que o banco devolve; nenhum dado é alterado e nenhum campo novo foi criado.
   - **Consumo médio (estimado):** km rodados entre as leituras de hodômetro ÷ litros. Aparece como "≈ 10,0 km/L", com o rótulo "estimado", porque supõe o tanque completado a cada abastecimento, o que o sistema não registra.
   - **Custo por km (combustível):** valor pago ÷ km rodados. É indicador financeiro, mostrado em linha separada do consumo.
   - Só entram abastecimentos com leitura anterior de hodômetro, cuja distância o banco informa. O primeiro abastecimento do veículo e os anulados ficam de fora dos dois indicadores.
   - A tela explica a conta e diz quantos abastecimentos entraram nela.
5. **Quilometragem.** É a que o banco informa: a leitura real do último abastecimento ou a estimativa a partir dela, com a indicação de qual das duas.
6. **Desvincular pede dois toques.** O primeiro troca o rótulo para "Confirmar"; só o segundo desvincula. O vínculo fica inativo e o histórico é preservado, como no desktop.
7. **Serviços comuns.** As regras saíram de `documentos-fiscais-adaptador.js` e de `mobilidade-adaptador.js` para `documentos-servico.js` e `mobilidade-servico.js`, sem mudança de código, como foi feito com as Recorrências. Desktop e celular usam as mesmas consultas e gravações.

## 4. Diferenças entre desktop e mobile

| Função | Desktop | Mobile |
|---|---|---|
| Lista, busca, situação e filtros de documentos | Sim | Sim |
| Detalhe e lastro | Sim | Sim |
| Baixar o arquivo | Abre em nova aba | Baixa o arquivo |
| Revisar dados básicos e validar | Sim | Sim |
| Vincular e desvincular | Sim | Sim |
| Saídas sem documento: lista, vínculo e situação | Sim | Sim |
| Exportar Excel, PDF e ZIP | Sim | Sim |
| **Enviar arquivo** | Sim | Não |
| **Classificação documental da Empresa** (tipo, categoria, validade, órgão emissor) | Sim | Não; a revisão mobile não altera esses dados |
| **Excluir documento** | Sim | Não |
| **Gerar financeiro e patrimônio a partir do documento** | Sim | Não |
| Veículos: consulta | Sim | Sim |
| Novo abastecimento | Sim | Sim |
| Histórico e resumo do veículo | Sim | Sim |
| **Cadastro e edição de veículos** | Sim | Não |
| **Projeções, modalidades, assinaturas e transporte por app** | Sim | Não |
| **Corrigir, anular e vincular abastecimento a compra** | Sim | Não |

O que fica só no desktop está indicado nas próprias telas, nos pontos em que o usuário poderia procurar a função.

## 5. Integrações

- **Documentos x Financeiro:** vínculo com despesas previstas, lançamentos de cartão, movimentos, patrimônio, financiamentos e contas; saídas sem documento a partir de contas a pagar, lançamentos e movimentos. Tudo pelas mesmas funções do desktop.
- **Mobilidade x Financeiro:** o abastecimento grava a despesa (conta a pagar na competência da data, ou compra à vista no cartão) e o registro do veículo numa só operação, pela função já existente. O histórico mostra o vínculo.
- **Exportações:** as do FIN-REG-03 e do FIN-REG-04, sem alteração.

## 6. Arquivos

| Arquivo | Mudança |
|---|---|
| `web/src/inicio.html`, `css/inicio-mobile.css` | Dois atalhos |
| `web/src/js/mobile-comum.js`, `js/sessao.js` | Módulos ativos e páginas protegidas |
| `web/src/documentos-mobile.html`, `js/documentos-mobile.js`, `css/documentos-mobile.css` | Novos |
| `web/src/mobilidade-mobile.html`, `js/mobilidade-mobile.js`, `css/mobilidade-mobile.css` | Novos |
| `web/src/js/documentos-servico.js`, `js/mobilidade-servico.js` | Novos: as regras que estavam nos adaptadores, sem mudança |
| `web/src/js/documentos-fiscais-adaptador.js`, `js/mobilidade-adaptador.js` | Ficam com a moldura e o que é só da tela do desktop |
| `web/src/js/arquivo-comprovante.js` | Função para baixar o arquivo no celular (a mesma consulta de "Abrir arquivo") |
| `web/src/js/abastecimento-formulario.js`, `js/lancamento-mobile.js` | Aceitam o veículo já escolhido |
| `web/tests/e2e/mob11_documentos.spec.mjs`, `mob12_mobilidade.spec.mjs` | Novos |
| `web/tests/e2e/mob08_inicio.spec.mjs`, `mob10_perfis.spec.mjs`, `web/tests/unit/build.test.mjs` | Dez atalhos; testes das páginas novas; lista de funções de gravação por arquivo |
| `tests/test_relatorios_fiscais.py`, `tests/test_zip_documentos_empresa.py` | Passam a ler o serviço no lugar do adaptador |

## 7. Testes

Executados em 15/11/2026.

| Bateria | Resultado |
|---|---|
| `mob11_documentos.spec.mjs` | 4 aprovados, 0 falhas |
| `mob12_mobilidade.spec.mjs` | 3 aprovados, 0 falhas |
| Documentos no desktop depois da separação do serviço (REG-03, REG-04, Documentos Fiscais, Lastro, Documento financeiro, P0/P1) | 23 aprovados, 0 falhas |
| Mobilidade no desktop depois da separação do serviço (Mobilidade, projeções e abastecimento em Lançamentos) | 15 aprovados, 0 falhas |
| Unitários do site, com o build de produção | 122 aprovados, 0 falhas (eram 120; +2 das páginas novas) |
| Suíte completa de navegador | 267 aprovados, 0 falhas (eram 260; +7 dos dois módulos) |

Uma rodada anterior da suíte completa teve 1 falha, do próprio teste: o cenário de Documentos da Empresa dependia de dados deixados por outros testes. Passou a usar um documento próprio, e a rodada seguinte foi limpa.

### O que os testes cobrem

**Mobile**
- Os dois atalhos da Página Principal abrem os módulos, com a competência.
- Sem rolagem horizontal e nada fora da tela em 320, 375, 390 e 430 px, em cada tela e painel.
- O título do cabeçalho não encosta nos ícones, inclusive em 320 px.
- Voltar leva à Página Principal com a competência.
- Sem sessão, as duas páginas voltam ao login.

**Documentos**
- Lista igual à consulta do desktop, por ano; busca; situação; ano sem documentos.
- Detalhe, lastro e ações. Baixar entrega os bytes guardados, sem alteração.
- Revisar grava observação e valor e preserva a categoria de despesa. Validar muda a situação.
- Empresa: saídas com resumo igual ao da consulta; situação manual; vínculo de documento a uma saída; vínculo sem entidade; desvincular com dois toques; filtro por tipo documental.
- Exportações: Excel e PDF do IR, Excel e PDF das saídas, e o ZIP da Empresa, com os nomes corretos.
- Perfil pessoal não mostra saídas nem ZIP.

**Mobilidade**
- Veículos iguais à consulta do desktop; ações na mesma linha, com a altura do botão compacto.
- Abastecer abre o formulário com o veículo escolhido e grava o abastecimento e a conta a pagar na competência da data.
- Histórico na ordem do banco, com o filtro do mês.
- Resumo conferido com números conhecidos: dois abastecimentos de 40 L, 400 km entre eles. Só o segundo tem leitura anterior, e dá "≈ 10,0 km/L" no consumo estimado e R$ 0,55 por km no custo. A nota da tela informa que é estimativa e que 1 abastecimento entrou na conta.
- Troca de competência; perfil sem veículos.

**Somente leitura**
- O leitor consulta, baixa e exporta. Não vê Revisar, Vincular, Desvincular, Situação nem Abastecer.
- O banco também recusa as gravações do leitor, e os dados ficam iguais.

## 8. Capturas

As capturas das telas em 320 e 390 px são geradas pelos testes quando a variável `CF_EVIDENCIAS_DIR` aponta para uma pasta. Não foram incluídas no repositório. Para a homologação visual, a prévia local mostra as telas com dados fictícios.

## 9. Pendências e sugestões

1. **Homologação visual do titular**, pela prévia local, antes de qualquer publicação.
2. **Enviar documento pelo celular** (fotografar o comprovante) não estava na lista de ações do contrato e ficou no desktop. É o uso de campo mais natural; pode entrar junto com o FIN-REG-08.
3. **Depois de abastecer**, a confirmação é a do Registrar Lançamento e leva à Lista de Despesas ou à Página Principal. Um atalho "Ver na Mobilidade" nessa confirmação é possível, mas mexe numa tela homologada; depende de decisão.
4. **Desktop:** o contrato previa evoluções de navegação por situação e de organização. Não alterei nenhuma tela do desktop; a preparação feita foi a separação dos serviços. Se houver evolução específica desejada no desktop, precisa ser descrita.

## 10. Limitações

- Baixar e exportar no iPhone usam o mecanismo de download do navegador. No aplicativo instalado na tela de início, o iOS abre a folha de compartilhamento ou a visualização do arquivo; o comportamento exato depende da versão do iOS e precisa ser conferido no aparelho.
- O filtro por tipo documental vale sobre a classificação gravada, como no desktop. A tela avisa.
- Consumo médio e custo por km dependem de abastecimentos consecutivos com hodômetro; com um só abastecimento aparecem como "Sem dados suficientes".
- O gráfico mostra só o gasto com abastecimento, não os demais custos do veículo.
- As exportações têm os limites do FIN-REG-04 (1.000 documentos, 40 MB por arquivo, 250 MB no total).

## 11. Critérios de aceite

**Página Principal mobile**

| Critério | Situação |
|---|---|
| Dois novos botões incluídos | Atendido |
| Layout principal preservado | Atendido: mesmas medidas, quinta linha |
| Navegação funcional | Atendido |
| Sem crescimento desnecessário da tela | Atendido: uma linha a mais, do mesmo tamanho |

**Documentos Fiscais mobile**

| Critério | Situação |
|---|---|
| Lista funcional | Atendido |
| Detalhe funcional | Atendido |
| Saídas sem documento funcional | Atendido |
| Ações principais acessíveis | Atendido |
| Exportações adequadamente tratadas | Atendido |
| Perfis respeitados | Atendido |
| Sem alteração indevida de dados | Atendido |

**Mobilidade mobile**

| Critério | Situação |
|---|---|
| Lista de veículos funcional | Atendido |
| Novo abastecimento funcional | Atendido, pelo formulário já homologado |
| Histórico funcional | Atendido |
| Resumo funcional | Atendido |
| Integração financeira preservada | Atendido |
| Modo somente leitura respeitado | Atendido |

**Geral**

| Critério | Situação |
|---|---|
| Testes aprovados | Atendido: suíte completa 267 de 267, unitários 122 de 122 |
| Sem deploy, sem push, sem migration em produção, sem alteração de dados reais | Atendido |

## 12. Publicação e reversão

- **Publicação:** só o site, sem migration. Depende da homologação do titular e de autorização específica.
- **Reversão:** republicar o deploy `ed3ffcdc` no Cloudflare Pages. Não há mudança no banco.
