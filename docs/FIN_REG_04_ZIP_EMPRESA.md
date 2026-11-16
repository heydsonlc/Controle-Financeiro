# FIN-REG-04 — Pacote ZIP dos documentos da Empresa

**Situação em 15/11/2026:** implementado e testado localmente, com dados fictícios, em bancos descartáveis. Homologação técnica aprovada pelo titular. **Publicado em 15/11/2026** (deploy `5c392a8a`, sem migration; detalhes em `docs/FIN_REG_03_04_HOMOLOGACAO.md`, seção 15). Falta a homologação funcional do titular com dados reais.

## 1. O que foi entregue

O botão **ZIP** que já existe no painel da lista de Documentos da Empresa passou a gerar o pacote para o contador, como o `DocumentoZipService` do Flask. O pacote é montado no navegador e baixado; nenhum arquivo passa por servidor ou armazenamento intermediário.

Nenhum controle foi criado. O botão "ZIP" do painel de saídas sem documento continua desabilitado, como na tela original.

## 2. Seleção dos documentos

- Só no perfil Empresa. Fora dele: "Pacote de documentos empresariais disponivel apenas no perfil Empresa."
- Só documentos do perfil ativo, pela mesma consulta da lista em tela.
- Os filtros são os da tela: ano, situação, tipo documental, categoria documental, categoria fiscal, validade, obrigatoriedade e busca.
- O pacote traz todos os documentos do filtro, não só a página visível.
- Sem documentos para o filtro: "Nenhum documento encontrado para os filtros selecionados.", sem arquivo.

Como no Flask, os filtros por tipo, categoria, validade e obrigatoriedade valem sobre a classificação **gravada** do documento. O titular decidiu manter esse comportamento por enquanto; a classificação automática no envio será tratada no FIN-REG-08. Um documento recém-enviado, ainda com a classificação sugerida, aparece na aba "Todos" mas não nas abas por tipo, até ser revisado. A lista da tela e o pacote seguem a mesma regra.

## 3. Estrutura do pacote

```
Documentos_Empresa_<ano>_Contador.zip
├── indice_documentos.xlsx
├── pagamentos_realizados/001_PAGAMENTO_<nome>.pdf
├── notas_fiscais_recebidas/002_NF_RECEBIDA_<nome>.pdf
└── ...
```

Pastas pelo tipo documental, iguais às do Flask:

| Tipo documental | Pasta | Prefixo do arquivo |
|---|---|---|
| Pagamento realizado | `pagamentos_realizados` | `PAGAMENTO` |
| Nota fiscal recebida | `notas_fiscais_recebidas` | `NF_RECEBIDA` |
| Nota fiscal emitida | `notas_fiscais_emitidas` | `NF_EMITIDA` |
| Documento obrigatório | `documentos_obrigatorios` | `DOC_OBRIGATORIO` |
| Documento societário | `societarios` | `SOC` |
| Procuração / representação | `procuracoes_representacoes` | `PROCURACAO` |
| Contrato / instrumento | `contratos_instrumentos` | `CONTRATO` |
| Certidão / licença | `certidoes_licencas` | `CERTIDAO` |
| Patrimônio / imobilizado | `patrimonio` | `PATRIMONIO` |
| Contábil / fiscal | `contabil_fiscal` | `CONTABIL` |
| Outro | `outros` | `DOC` |

**Nome de cada arquivo:** `NNN_PREFIXO_nome.ext`.
- `NNN` é o número do documento no índice. Por isso dois documentos com o mesmo nome nunca colidem.
- O nome vem do prestador, do nome do arquivo ou de "Documento <id>", sem acentos nem caracteres de caminho, com no máximo 80 caracteres.
- A extensão é a do arquivo original; sem ela, vem do tipo do arquivo.

**Documento sem arquivo:** fica no índice com "Arquivo nao incluido" e a observação "Arquivo nao encontrado ou indisponivel". Não gera entrada no pacote.

## 4. Índice (`indice_documentos.xlsx`)

- **Aba "Indice":** uma linha por documento, com 16 colunas: Nº, nome original, nome no ZIP, documento, tipo documental, categoria documental, categoria fiscal, data de emissão, data de validade, prestador ou emissor, CPF/CNPJ, valor, situação documental, situação do lastro, entidade vinculada e observações.
- **Aba "Resumo":** perfil, data de geração, ano, filtros aplicados, total de documentos, valor documentado, com e sem lastro, o aviso ao contador e as contagens por tipo documental e por situação.

O índice só contém documentos do perfil ativo.

## 5. Integridade dos arquivos

- Os bytes de cada documento vão para o pacote como estão no banco: sem conversão, sem recompressão e sem alterar metadados.
- **Antes de entrar no pacote, cada arquivo é conferido com o tamanho e o SHA-256 gravados no envio.** O Flask não fazia essa conferência; é um acréscimo.
- Se um arquivo divergir, ou não puder ser lido, **o pacote inteiro não é gerado**. A mensagem diz qual arquivo e por quê. Não existe pacote parcial.

## 6. Volume e memória

O pacote é montado na memória do navegador. Cada arquivo chega inteiro e é copiado para o ZIP. Limites definidos:

| Limite | Valor |
|---|---|
| Documentos por pacote | 1.000 |
| Tamanho de um arquivo | 40 MB |
| Soma dos arquivos | 250 MB |

- Os limites são conferidos **antes** de ler qualquer arquivo, pelos tamanhos registrados. Acima deles, a mensagem pede para refinar os filtros e gerar em partes.
- Falta de memória durante a montagem: mensagem própria, sem pacote.
- Os arquivos são lidos de três em três, para não manter muitos na memória ao mesmo tempo.
- Volume de hoje na produção: 2 documentos, poucos megabytes (medido no backup de 15/11/2026). Os limites têm folga grande.

**Se o volume crescer além disso,** a alternativa técnica é gerar o pacote em partes (por mês ou por tipo), o que já é possível pelos filtros, ou gravar o ZIP em fluxo direto no disco pelo navegador. Nenhuma das duas exige serviço externo. Não foi necessário implementar agora.

## 7. Proteção das informações

- Nenhum arquivo ou dado sai do navegador: o módulo não faz chamada de rede nem usa armazenamento local.
- Nada é gravado no Supabase nem no Cloudflare, nem cópia temporária.
- O conteúdo dos documentos não vai para logs.
- A leitura de cada arquivo passa pela mesma função de "Abrir arquivo", que confere o perfil no banco.
- O download só começa com o clique do usuário.

## 8. Arquitetura

| Arquivo | Papel |
|---|---|
| `web/src/js/zip-documentos.js` (novo) | Monta as entradas, o índice e o pacote; confere integridade e volume. Sem rede |
| `web/src/js/exportacao-xlsx.js` (alterado) | Gera o índice e empacota o ZIP, com o empacotador que já servia às planilhas |
| `web/src/js/documentos-fiscais-adaptador.js` (alterado) | Rota do pacote: consulta, leitura dos arquivos, conferência e entrega |

Consultas reutilizadas, todas já publicadas e só de leitura: `ir_comprovantes_tela`, `vinculos_documento_tela` e `arquivo_comprovante_tela`. **Nenhuma função nova e nenhuma migration.**

## 9. Tratamento de erros

| Situação | Resultado |
|---|---|
| Nenhum documento para o filtro | "Nenhum documento encontrado para os filtros selecionados." |
| Perfil que não é Empresa | Recusa com a mensagem do Flask |
| Documento sem arquivo | Entra só no índice, com a observação |
| Documento inacessível ao perfil | O banco responde "não encontrado"; sem pacote |
| Falha na consulta ou na leitura de um arquivo | Mensagem clara, sem detalhe interno; sem pacote |
| Divergência de tamanho ou de SHA-256 | Mensagem com o nome do arquivo; sem pacote |
| Volume acima dos limites | Mensagem com os números e a orientação; nenhum arquivo é lido |
| Falta de memória | Mensagem própria; sem pacote |
| Nomes duplicados | Não ocorrem (numeração); há ainda uma trava que recusa o pacote se ocorrerem |

Nenhuma falha grava dado.

## 10. Testes

Executados em 15/11/2026.

| Bateria | Resultado |
|---|---|
| `tests/test_zip_documentos_empresa.py` (comparação com o Flask) | 5 aprovados, 0 falhas |
| `web/tests/e2e/reg04_zip_empresa.spec.mjs` (navegador) | 3 aprovados, 0 falhas |

### Comparação com o Flask

O pacote foi gerado pelo próprio Flask e pelo novo aplicativo sobre a mesma base fictícia, em 10 consultas (ano, tipo documental, busca, mês, situação, validade, obrigatoriedade, categoria documental e situação documental pelas duas formas).

| Conferência | Resultado |
|---|---|
| Lista de arquivos, na mesma ordem | Idêntica |
| Pastas | Idênticas |
| Bytes de cada documento | Idênticos aos do Flask e aos enviados |
| Índice: abas, valores, formatos, cabeçalho, painel congelado, autofiltro e larguras | Idênticos |
| Nome do pacote | Idêntico |
| Pacote sem documentos | Mesma recusa, mesma mensagem |

O cenário inclui nome com acentos e caracteres de caminho, dois documentos com o mesmo prestador e o mesmo nome de arquivo, arquivo sem extensão, imagem PNG, documento sem arquivo, documento vencido, obrigatório, com vínculo validado e com vínculo aguardando contador.

### Integridade, volume e falhas

- Um byte trocado: recusa por SHA-256, sem pacote.
- Arquivo truncado: recusa por tamanho, sem pacote.
- Arquivo não lido: recusa, sem pacote.
- Limites de total, de arquivo e de quantidade: recusa antes de ler os arquivos.
- No navegador: resposta adulterada e falha simulada da consulta não geram download; sem a interferência, o pacote volta a ser gerado.
- Os hashes gravados no banco conferem com o conteúdo, ou seja, a conferência usa um dado real.

### Segurança

- Perfil Pessoal: botão oculto e rota recusada com a mensagem do Flask.
- Conta sem acesso à Empresa, e requisição sem sessão: o banco recusa a lista e o arquivo.
- Arquivo de documento de outro perfil ou inexistente: "não encontrado".
- O pacote da Empresa só contém documentos da Empresa; o documento do perfil Pessoal do cenário nunca entra.

### Nenhuma alteração de dados

O resumo de todas as tabelas é idêntico antes e depois de gerar os pacotes.

## 11. Diferenças em relação ao Flask

| Diferença | Motivo |
|---|---|
| O ZIP é gravado sem compressão | Preserva os bytes sem depender de biblioteca; PDFs e imagens já são comprimidos. O pacote fica um pouco maior |
| Conferência de tamanho e SHA-256 antes de incluir cada arquivo | Acréscimo exigido pelo contrato; o Flask não conferia |
| Limites de volume | O Flask montava no servidor; no navegador é preciso limitar |
| Documento sem classificação gravada aparece como "Não classificado" no índice | No Flask saía "Outro" e "Sem categoria". É a classificação do novo aplicativo, já homologada na tela (FIN-MIGRACAO-LASTRO-EMPRESA-01). A pasta e o arquivo são os mesmos. Diferença mantida por decisão do titular |

## 12. Limitações

- Pacotes acima dos limites precisam ser gerados em partes, pelos filtros.
- O parâmetro "mês" só entra no nome do pacote, como no Flask; a tela não filtra documentos por mês.
- O ZIP das saídas sem documento não existe no Flask e continua desabilitado.

## 13. Publicação e reversão

- **Publicação:** só arquivos do site (`web/src/js`). Não há migration. Depende de autorização específica.
- **Reversão:** republicar o deploy anterior no Cloudflare Pages. Não há mudança no banco a desfazer.
