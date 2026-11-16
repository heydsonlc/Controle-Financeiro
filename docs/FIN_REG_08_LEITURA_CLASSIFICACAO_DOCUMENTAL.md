# FIN-REG-08 — Leitura e classificação sugerida de documentos fiscais

**Situação:** **PUBLICADO em 16/11/2026** (push `2883f07..93bda10`, migration `20261228090000` aplicada = 68, deploy `34264964`, reversão `8685a983`).
Homologação: `docs/FIN_REG_08_HOMOLOGACAO.md`. Correção de cache preparada à parte: `docs/FIN_CACHE_01_ATUALIZACAO_JS_CSS.md`.

## 1. Objetivo e regra central

Ler o documento enviado (PDF digital, PDF digitalizado ou foto) **no próprio navegador**, reconhecer os dados (NFS-e de Goiânia,
cupom fiscal/NFC-e/SAT ou documento genérico) e sugerir a categoria. O fluxo pedido para o celular é:

> Fotografar ou selecionar documento → Reconhecer → Conferir valores → Ajustar categoria → Confirmar envio.

Regra central do contrato, mantida em todas as telas: **a leitura só preenche e sugere**. Nenhum lançamento financeiro é criado,
nenhum documento é validado e nenhuma categoria é criada ou trocada sem confirmação do usuário. O documento enviado fica
sempre **pendente de revisão**; validar continua sendo uma ação do usuário.

## 2. Decisões do titular aplicadas

| Tema | Decisão | Como ficou |
|---|---|---|
| CSP | Permitir só `'wasm-unsafe-eval'`, sem `'unsafe-eval'` e sem `'unsafe-inline'`, com escopo limitado | Liberado só em `/documentos-fiscais`, `/documentos-mobile` e `/vendor/tesseract-7.0.0/*`; o resto do site segue com `script-src 'self'` (seção 5) |
| Biblioteca de OCR | Tesseract.js 7.0.0 hospedado no site, sem CDN, carregado só quando o OCR é pedido, versões fixas, worker encerrado ao fim | Seção 4 |
| Migration | Alterar só a função necessária; não aplicar em produção nesta etapa | Só `financeiro.enviar_comprovante` (seção 6) |
| CLASSIFICADO | Não recriar | Não recriado: o documento fica `PENDENTE_REVISAO` |
| Conferência | Valor, data e CPF/CNPJ do OCR sempre exibidos para conferir; valor ambíguo sem escolha automática | Situação por campo e opções de valor (seção 3) |
| Texto e correções | Texto guardado com a origem; gravação não sobrescreve silenciosamente correções manuais | `origem_classificacao` + evento; sugestões só em campo vazio (seção 3.4) |
| WebKit | Autorizado para teste local, sem substituir o iPhone real | Ensaio aproximado registrado na homologação |
| HEIC | Avaliar conversão local sem ampliar formatos no Supabase | Conversão para JPEG onde o navegador decodifica (Safari); nos demais, orientação ao usuário |
| Preenchimento manual | Sempre disponível | Falha ou ausência de leitura deixa os campos editáveis; envio continua possível |

## 3. Regras da leitura (`web/src/js/leitura-fiscal.js`, funções puras)

### 3.1 Tipos de documento

| Tipo | Detecção (igual ao Flask) | Campos |
|---|---|---|
| NFS-e de Goiânia | `ir_nfse_goiania_parser.py` | data (competência/geração/RPS), número, prestador, CNPJ do prestador, tomador, CPF do tomador, descrição, valor |
| Cupom fiscal / NFC-e / SAT | `cupom_fiscal_parser.py` | data, estabelecimento, CNPJ, valor total, chave de acesso |
| Genérico | `IrDocumentoService._extrair_dados_simples` | data, CPF/CNPJ, prestador, valor |
| Sem texto | menos de 50 caracteres não brancos (o mesmo mínimo do banco) | nenhum: preenchimento manual |

### 3.2 Situação de cada campo

- **Informação identificada:** só para modelo conhecido (NFS-e ou cupom) lido do **texto do próprio PDF**.
- **Conferir informação:** todo campo vindo de **OCR**, todo campo de documento **genérico**, e CPF/CNPJ com dígito verificador
  inválido (com aviso).
- **Informação não reconhecida:** campo vazio.

### 3.3 Valor ambíguo (diferenças deliberadas em relação ao Flask)

- **Cupom:** o total lido é conferido com `subtotal − desconto + acréscimo` e com `dinheiro − troco`. Se não fecha (ex.: OCR leu
  `409,00` onde o cupom dizia `40,00`), o valor fica **vazio** e os candidatos aparecem como opções. O Flask aceitava o total errado.
- **Genérico com vários valores distintos:** nenhum é escolhido, e todos aparecem como opções. O Flask pegava o maior.
- **Genérico com um valor:** sugerido, mas sempre para conferir.

### 3.4 Sugestões nunca sobrescrevem dados

- **Desktop (revisão original):** ao abrir a revisão, o texto guardado é interpretado de novo.
  - **Modelo reconhecido** (NFS-e ou cupom): **campo vazio** recebe a sugestão, com a borda âmbar "sugerido" e a nota da situação.
  - **Documento genérico:** **nada é preenchido**. Cada sugestão aparece como nota com o botão **Usar**, e só o que o usuário usar
    entra no campo. Motivo: a regressão mostrou que quem abre a revisão só para classificar metadados gravaria, ao salvar, um
    prestador adivinhado que nem viu.
  - **Campo já preenchido**, seja dado anterior ou correção manual, **não é trocado**; aparece só a nota "A leitura sugere: X (o valor atual foi mantido)".
  - Nada é gravado até o usuário clicar em "Salvar revisão".
- **Celular (conferência antes do envio):** todos os campos são editáveis. O arquivo, o texto lido e os dados conferidos vão numa
  única gravação. Se o arquivo já tinha sido enviado (mesmo SHA-256 no perfil), o documento existente é devolvido **sem
  alteração** ("Documento já enviado").

### 3.5 Categoria sugerida

1. **Palavras-chave** ativas: o mesmo algoritmo do Flask (`CategoriaPalavraChaveService`). Um empate é ambíguo, e então nada é
   escolhido e as candidatas aparecem na nota.
2. **Histórico do emitente** (novo): a categoria só é sugerida quando todos os documentos anteriores do mesmo CPF/CNPJ **no perfil**
   usam a mesma categoria.
3. Só categorias **do próprio perfil**. As categorias sem perfil pertencem ao Pessoal: um perfil sem categorias próprias não
   recebe sugestão, como no desktop.
4. A categoria escolhida resolve a Categoria IR / fiscal pelo vínculo já existente. **Nenhuma categoria é criada.**

## 4. Arquitetura

| Peça | Arquivo | Papel |
|---|---|---|
| Leitura fiscal | `web/src/js/leitura-fiscal.js` | Funções puras: detecção, campos, situação, candidatos, categoria |
| Motor de leitura | `web/src/js/leitura-ocr.js` | Preparo do arquivo, texto do PDF (pdf.js), OCR (Tesseract.js), miniatura da foto |
| Serviço comum | `web/src/js/documentos-servico.js` | `sugestoesDoTexto`, `novoLeitor`, `enviarConferido`, `comprovanteCompleto`; leitura no envio do desktop |
| Desktop | `web/src/js/documentos-fiscais-adaptador.js` + CSS | Andamento da leitura, linha "Texto lido automaticamente", sugestões na revisão |
| Celular | `web/src/js/documentos-mobile-envio.js`, `documentos-mobile.{html,js}` + CSS | Botão "+" (incluir), etapas no painel inferior |
| Banco | `supabase/migrations/20261228090000_financeiro_documentos_leitura_ocr.sql` | `enviar_comprovante` aceita texto de OCR com origem e os dados conferidos |

### 4.1 Motor de leitura

- **PDF:** o texto do próprio PDF primeiro (pdf.js, já usado no aplicativo). Sem texto (digitalizado), há OCR de até 3 páginas a
  cerca de 200 dpi, como no Flask (`OcrService.MAX_PAGINAS_OCR`).
- **Imagem:** OCR sobre uma cópia reduzida a 2400 px de lado, usada só para a leitura. O arquivo guardado é o enviado.
- Limite de **120 s** e botão **Cancelar leitura**. O worker é **encerrado** ao final, com sucesso, falha ou cancelamento.
- **Tesseract:** `workerBlobURL: false`, `cacheMethod: 'none'` (o modelo não fica no IndexedDB) e caminhos locais do worker, do
  núcleo e do modelo. Sem esses caminhos a biblioteca buscaria a jsDelivr, o que a CSP também bloqueia. O motor é OEM 1 (LSTM).
- O texto do OCR é normalizado como no Flask (`OcrService.normalizar_texto_ocr`).

### 4.2 Preparo do arquivo (sem ampliar o que o Supabase aceita)

- **Formatos:** PDF, PNG, JPEG e WebP, até 10 MB, com assinatura conferida no banco (inalterado).
- **Foto acima de 10 MB:** cópia JPEG reduzida, **informada antes do envio** ("A foto tinha X; será enviada uma cópia JPEG
  reduzida de Y"). O original não é alterado.
- **HEIC:** convertido para JPEG onde o navegador decodifica (Safari). Nos demais, a mensagem orienta a usar o botão Fotografar ou
  enviar em JPEG. Pelo seletor da câmera, o iPhone costuma entregar JPEG.
- **PDF acima de 10 MB ou formato inválido:** recusado na tela, sem chamar o banco.
- **Pré-visualização:** miniatura JPEG como `data:` URL. A CSP mantém `img-src 'self' data:` e não libera `blob:`; o teste e2e
  pegou essa violação e a correção foi a miniatura, não a CSP.

### 4.3 Bibliotecas (versões fixas, hospedadas em `vendor/tesseract-7.0.0/`)

| Pacote | Versão | Licença | Arquivo servido | Bytes | SHA-256 |
|---|---|---|---|---|---|
| tesseract.js | 7.0.0 | Apache-2.0 | tesseract.esm.min.js | 63.220 | `64871d76c75609fd5413b88a8171e2ef40deedd77d5875ba23df104b2d05eb29` |
| tesseract.js | 7.0.0 | Apache-2.0 | worker.min.js | 111.307 | `576b7df7e3393e137e51849357c9adb53fe7ac1bb69bfa06cf3d61520f182c6d` |
| tesseract.js-core | 7.0.0 | Apache-2.0 | tesseract-core-lstm.wasm.js | 3.896.484 | `eef5f8b2f8e20e150680b20adaec4a60babafee3adbe8a94583c81fee46e8680` |
| tesseract.js-core | 7.0.0 | Apache-2.0 | tesseract-core-simd-lstm.wasm.js | 3.899.472 | `c58b46a4c796c0b8afccf77591d5b875b6896b45d402bbce8caa6f5362447b38` |
| tesseract.js-core | 7.0.0 | Apache-2.0 | tesseract-core-relaxedsimd-lstm.wasm.js | 3.905.767 | `861a536cf9ef8e63cb644d57bab39c388f37f7d6b6f60024b741c5f6b39a59b3` |
| @tesseract.js-data/por | 1.0.0 (modelo 4.0.0_best_int) | MIT | por.traineddata.gz | 1.392.239 | `dacebc1386ddaaf8389f81094236cca0d690897cde693d48cbdaa881c86e2b4c` |

- Instalados com `npm install --save-exact --ignore-scripts`.
- O worker escolhe um dos três núcleos conforme o suporte a SIMD do aparelho. O primeiro OCR baixa cerca de 5,5 MB (biblioteca,
  worker, um núcleo e o modelo).
- A pasta leva a versão no nome e é servida com `Cache-Control: public, max-age=31536000, immutable`: depois da primeira leitura,
  não é baixada de novo a cada publicação.

## 5. Segurança

- **CSP por caminho** (`web/scripts/build.mjs`, `cabecalhosSeguranca`): o bloco `/*` mantém `script-src 'self'`. Cada caminho de
  OCR tem `! Content-Security-Policy` e a mesma política com `script-src 'self' 'wasm-unsafe-eval'`; as demais diretivas são
  idênticas.
- A semântica foi conferida no emulador do Cloudflare (`wrangler pages dev`):
  - a política só muda nesses caminhos;
  - as URLs `.html` redirecionam (308) para o caminho limpo, que recebe o bloco;
  - o worker recebe a CSP da própria resposta.
- **Nenhum serviço externo:** OCR, modelo e worker vêm do próprio site. O e2e falha se a página pedir qualquer endereço fora do
  site ou do Supabase local, e também em erro de CSP ou de JavaScript.
- **Sem `innerHTML`, sem escrita em tabela pelo frontend** (verificado no build.test): a gravação é só pela função do banco.
- **Permissões e isolamento** inalterados: só quem gere o perfil vê o botão de incluir e consegue gravar (o banco recusa o leitor).
  O histórico usado na sugestão é só do perfil ativo.
- Os testes usam somente documentos **fictícios** gerados no próprio teste (PDF montado e "foto" de texto desenhado numa página em
  branco). Nenhum documento real é usado.

## 6. Migration (aplicada em produção em 16/11/2026)

`20261228090000_financeiro_documentos_leitura_ocr.sql`: `create or replace` só de `financeiro.enviar_comprovante`, com o corpo
anterior preservado (inclusive as mensagens de erro originais) e estes acréscimos:

- `texto_origem`: `TEXTO_PDF`, `OCR_IMAGEM` ou `OCR_PDF`, coerente com a extensão do arquivo (caso contrário, "Origem da leitura
  inválida para este arquivo").
  - Gravado em `origem_classificacao`, com o evento `TEXTO_EXTRAIDO` (PDF) ou `TEXTO_EXTRAIDO_OCR` (OCR) e a observação "Texto
    lido por OCR no navegador. Confira valor, data e CPF/CNPJ antes de validar."
  - Sem origem, o comportamento anterior continua: PDF tratado como `TEXTO_PDF`, com texto só a partir de 50 caracteres.
- `leitura`: `NFSE_GOIANIA` ou `CUPOM_FISCAL`, que só registra o evento do modelo reconhecido.
- `revisao`: os dados conferidos no celular, aplicados por `financeiro.atualizar_comprovante` **na mesma transação**, ou seja,
  tudo ou nada. Em arquivo repetido não são aplicados: o documento existente é devolvido sem alteração.
- Grants: `revoke` de public/anon e `grant` a authenticated.

**Reversão:** `supabase/reversao/20261228090000_documentos_leitura_ocr_anterior.sql` (a definição anterior, como `create or replace`).

**Compatibilidade:** o frontend publicado hoje funciona com a função nova (testado). O frontend novo **precisa** da função nova
para gravar OCR de imagem e os dados conferidos. Portanto, na publicação, a migration vem antes do deploy.

## 7. O que ficou de fora (pendências registradas)

- **"Reprocessar OCR" na revisão do desktop:** continua indisponível, com a mesma mensagem da fase 1. A leitura é feita no envio.
- **Leitura de documentos já guardados sem texto:** não há reprocessamento em lote.
- **Classificação documental da Empresa** (tipo, categoria documental, validade): continua na revisão do desktop.
- **Safari real e câmera do iPhone:** não testados. O ensaio WebKit é aproximado (seção 3 da homologação).

## 8. Plano de publicação (executado em 16/11/2026; resultado em `FIN_REG_08_HOMOLOGACAO.md`)

1. Backup `PRE_MIGRATION` (`scripts/backup_rotina.py executar --tipo PRE_MIGRATION`) e conferência.
2. Aplicar a migration `20261228090000` em produção e conferir a função (assinatura, grants e uma chamada de leitura sem gravação).
3. Build de produção e deploy no Cloudflare Pages (`controle-financeiro`, branch `producao`), junto com o FIN-CACHE-01 se autorizado.
4. Conferir os arquivos servidos (hash de cada arquivo), a CSP por caminho e o cache da pasta do OCR.
5. Homologação funcional do titular com documento real **no próprio aparelho** (iPhone: fotografar, conferir, enviar).

**Reversão:** deploy anterior (`8685a983`) e, se necessário, o SQL de reversão. Os documentos enviados nesse meio-tempo continuam
válidos: a função anterior aceita o que já foi gravado.
