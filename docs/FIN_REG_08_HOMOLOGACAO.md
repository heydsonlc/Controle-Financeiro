# FIN-REG-08 — Homologação (prévia local)

Leitura e classificação sugerida de documentos (`docs/FIN_REG_08_LEITURA_CLASSIFICACAO_DOCUMENTAL.md`) e a correção de cache
FIN-CACHE-01 (`docs/FIN_CACHE_01_ATUALIZACAO_JS_CSS.md`, em commit próprio). Ramo local `reg-08-leitura-classificacao`.
**PUBLICADO em 16/11/2026** (seção "Publicação", no fim). Testes só no banco descartável, com dados fictícios.

## 1. Roteiro para o titular (prévia no Firefox, modo celular e desktop)

Amostras fictícias para selecionar (geradas para a prévia, sem dado real):

- `1-nfse-goiania-ficticia.pdf`: NFS-e de Goiânia, R$ 130,80;
- `2-recibo-varios-valores-ficticio.pdf`: R$ 80,00, R$ 45,50 e R$ 12,00, valor ambíguo;
- `3-foto-cupom-ficticio.png`: cupom com total coerente, R$ 25,00;
- `4-foto-cupom-total-incoerente-ficticio.png`: total que não fecha com o troco.

| # | Onde | Passos | Esperado |
|---|---|---|---|
| 1 | Celular, Documentos (Empresa C ou Perfil G) | Tocar no **+** ao lado do título da lista | Painel "Incluir documento" com **Fotografar** e **Selecionar arquivo** |
| 2 | Celular | Selecionar a amostra 1 | Pré-visualização com nome, formato e tamanho; Cancelar, Substituir e Continuar. Cancelar não grava nada |
| 3 | Celular | Continuar | "Lendo o documento…" e depois "Conferir documento": NFS-e de Goiânia, lido pelo texto do PDF; data, prestador, CNPJ e valor **identificados** |
| 4 | Celular | Escolher a categoria (Empresa C: "Servicos C (ficticia)") e tocar em **Confirmar e enviar** | "Documento enviado"; o documento aparece **pendente** na lista; Abrir documento mostra os dados conferidos |
| 5 | Celular | Enviar a amostra 1 de novo, mudando o prestador | Categoria já sugerida pelo histórico do emitente; ao confirmar, "Documento já enviado" e o documento existente **sem alteração** |
| 6 | Celular | Amostra 2 | Valor **vazio** e as opções R$ 80,00, R$ 45,50 e R$ 12,00; nenhuma escolhida sozinha; tocar numa opção preenche o valor |
| 7 | Celular | Fotografar ou selecionar a amostra 3 | Miniatura da foto; reconhecimento por OCR; **tudo para conferir** (nada "identificado") |
| 8 | Celular | Amostra 4 | Valor vazio com as opções e o aviso de que o total não confere |
| 9 | Celular | Leitor (somente leitura) | Sem o botão **+** |
| 10 | Desktop, Documentos Fiscais | Importar a amostra 3 | "Documento enviado." e "Texto lido automaticamente em 1 documento…" |
| 11 | Desktop | Revisar esse documento | Resumo "Leitura automática (OCR da imagem): Cupom fiscal"; campos vazios preenchidos com borda âmbar e a nota "Conferir informação" |
| 12 | Desktop | Corrigir o prestador, Salvar revisão e reabrir | A correção fica; a leitura aparece só como nota "A leitura sugere: … (o valor atual foi mantido)" |
| 13 | Desktop | Importar a amostra 2 (genérico) e revisar | "Documento sem modelo reconhecido: nada foi preenchido"; cada sugestão com o botão **Usar**; só o que for usado é gravado ao salvar |

## 2. Testes automatizados

| Bateria | Resultado |
|---|---|
| `tests/test_leitura_fiscal.py`: o módulo JS comparado aos leitores do Flask nos mesmos textos, mais as diferenças deliberadas | 21 passaram |
| `tests/test_supabase_documentos_leitura.py`: migration, origem e eventos, compatibilidade, revisão na mesma transação, repetido sem sobrescrever, recusas sem gravação parcial, permissões, isolamento, reversão | passaram (com `test_supabase_documentos_escrita.py` e `test_leitura_fiscal.py`: 45 passaram) |
| Unitários do frontend (`npm run test:unit`), incluindo a CSP por caminho, os arquivos do Tesseract e o versionamento do FIN-CACHE-01 | 127/127 |
| `reg08_leitura.spec.mjs` (Chromium): desktop OCR e revisão; NFS-e no celular com cancelar, ajustar categoria, confirmar, histórico e repetido; valor ambíguo; foto por OCR; preparo do arquivo; leitor; CSP por caminho; documento genérico no desktop (nada preenchido, botão Usar) | 8/8 |
| Suíte e2e completa (Chromium, dist versionado) | **275/0** (antes: 267) |
| Testes Python de documentos, relatórios e ZIP (8 arquivos) | 72 passaram |

## 3. Ensaio aproximado no WebKit (não equivale ao iPhone)

O motor WebKit do Playwright 1.59.1 (WebKit 26.4, no Windows, com emulação do iPhone 13) rodou `reg08_leitura.spec.mjs` com o
projeto `webkit-aproximado`: **7/7** (rodado antes de entrar o oitavo teste, do documento genérico no desktop), **com o OCR funcionando** (WebAssembly do Tesseract sob a CSP com `'wasm-unsafe-eval'`).
Também `mob11_documentos.spec.mjs` 4/4 e `mob12_mobilidade.spec.mjs` 2/3.

Observações do ensaio, que não são defeitos do REG-08:

- Um pedido interrompido pela troca de página aparece no WebKit como erro "access control checks". No REG-08 essa mensagem é
  tolerada **só** no projeto WebKit; o mob12 falhou por ela.
- `mob08_inicio`: na largura 320×568 a barra inferior não ficou colada ao rodapé na emulação. Precisa ser conferido num iPhone real.

**Não testado:** Safari real, câmera do iPhone (`capture="environment"`), HEIC real e memória de aparelho antigo. Nada disso
é afirmado como compatível sem o teste no aparelho.

## 4. Limitações conhecidas

- O OCR pode errar dígitos (no ensaio, `40,00` foi lido como `409,00`): por isso todo campo de OCR fica para conferir, e o cupom
  incoerente não recebe valor.
- O primeiro OCR baixa cerca de 5,5 MB. Depois, a pasta do OCR fica no cache por 1 ano, por ter a versão no nome.
- PDF digitalizado: OCR de no máximo 3 páginas; tempo máximo de 120 s, com Cancelar.
- Perfil sem categorias próprias não recebe sugestão de categoria (as categorias sem perfil pertencem ao Pessoal), como no desktop.
- "Reprocessar OCR" na revisão do desktop continua indisponível.
- `Permissions-Policy: camera=()` continua no site. O botão Fotografar usa o seletor de arquivos do sistema (câmera nativa), não
  a câmera pela página, e deve funcionar. A confirmação depende do teste num iPhone real.

## 5. Critérios de aceite

- [ ] O fluxo Fotografar/Selecionar → Reconhecer → Conferir → Ajustar categoria → Confirmar funciona no celular (prévia).
- [ ] Nada é gravado ao cancelar ou fechar; o documento enviado fica pendente; nenhuma despesa ou lançamento é criado.
- [ ] Valor ambíguo nunca é escolhido sozinho; OCR sempre para conferir.
- [ ] Correção manual nunca é trocada pela leitura.
- [ ] Desktop: envio com leitura e sugestões na revisão sem mudar o restante da tela.
- [ ] Decisão sobre a publicação (migration antes do deploy) e sobre publicar o FIN-CACHE-01 junto.

## Publicação (16/11/2026, autorizada pelo titular)

| Etapa | Resultado |
|---|---|
| Backup `PRE_MIGRATION` | `cf-fzjmgekasjrgvmfdkdog-20261116_081319`, duas cópias verificadas (67 migrations no retrato) |
| Migration `20261228090000` | Simulada (só ela pendente) e aplicada: 68/68; corpo da função em produção idêntico ao da migration; execução só para `authenticated` |
| Push | `2883f07..93bda10` em `main` (avanço rápido) |
| Deploy | `34264964` (Cloudflare Pages, `producao`); reversão: `8685a983` |
| Arquivos servidos | 243/243 iguais ao build (215 arquivos por SHA-256 e 28 páginas HTML, descontado o script de métricas da Cloudflare) |
| CSP em produção | `'wasm-unsafe-eval'` só em `/documentos-fiscais`, `/documentos-mobile` e `/vendor/tesseract-7.0.0/*`; demais caminhos com `script-src 'self'` |
| Cache em produção | HTML `max-age=0, must-revalidate`; pasta do OCR `max-age=31536000, immutable`; toda referência a JS/CSS com `?v=<hash>` |
| OCR em produção (sem login, imagem fictícia desenhada no teste) | Funciona sob a CSP real no Chromium e no WebKit aproximado (cerca de 1 s); nenhum pedido a endereço externo |
| Acesso sem sessão | Consultas continuam recusadas (HTTP 401); sem erros de console |

Nenhum dado financeiro ou documento real foi lido ou alterado na publicação. **Falta a homologação funcional do titular no
iPhone real** (fotografar, conferir, enviar): Safari e câmera continuam não testados.
