# FIN-DOCUMENTOS-2 — Escrita de Documentos Fiscais no novo aplicativo

Data: 28/10/2026. É o item B1 do FIN-BLOCO-B-1 (contrato em `docs/contratos/fila_2026-10-26/FIN-DOCUMENTOS-2.md`).

**Situação:** a parte prioritária, armazenamento seguro e integração com Despesas, está implementada e testada localmente.
- Migration `20261128090000_financeiro_documentos_escrita.sql`, local, **não aplicada no remoto**.
- Reversão em `supabase/reversao/20261128090000_remover_documentos_escrita.sql`.

## 1. O que o novo aplicativo passa a gravar

São 8 funções de tela, com o escritor único do perfil. Um perfil no Flask recebe `SISTEMA_FLASK`, e nada é gravado.

| Flask (`routes/ir.py`) | Função |
|---|---|
| `POST /api/ir/comprovantes/upload` | `enviar_comprovante`, um arquivo por chamada, conteúdo em base64 |
| `PUT /api/ir/comprovantes/<id>` | `atualizar_comprovante` (revisão) |
| `POST /api/ir/comprovantes/<id>/validar` | `validar_comprovante` |
| (novo; o Flask não tinha) `DELETE /api/ir/comprovantes/<id>` | `excluir_comprovante` (exclusão segura) |
| `POST/PUT/DELETE /api/ir/comprovantes/<id>/vinculos[/<v>]` | `criar_vinculo_documento`, `atualizar_vinculo_documento`, `remover_vinculo_documento` |
| `POST /api/ir/comprovantes/<id>/criar-financeiro` | `criar_financeiro_documento` |

### Armazenamento

- **Onde fica:** o arquivo fica **no banco**, em `public.ir_comprovante_arquivo.conteudo`, como no Flask. Só as funções que conferem o perfil o leem, incluindo a `arquivo_comprovante_tela` já existente.
  - Não há bucket, público ou remoto, e nada depende de configuração remota.
  - O backup do banco leva os arquivos junto.
- **Validações do Flask:**
  - extensão `pdf`, `png`, `jpg`, `jpeg` ou `webp`;
  - MIME permitido;
  - arquivo não vazio;
  - até 10 MB;
  - assinatura do arquivo (bytes iniciais);
  - nome seguro (versão aproximada do `secure_filename`);
  - duplicidade por SHA-256 no perfil. O mesmo arquivo em outro perfil é permitido, e cada perfil vê só o seu.
- **Idempotência:** chave por envio (`financeiro.operacao_documento`, tabela nova e vazia).

### Integração com Despesas

- **Despesa** cria `item_despesa` e `conta` pendentes.
- **Lançamento** tem três caminhos:
  - realizado pela conta bancária: a conta é paga pelo `pagar_despesa`, com movimento e saldo pelo mesmo motor;
  - sem conta bancária: baixa simples, como no Flask;
  - no cartão: um lançamento pelo motor de compras. Sem fechamento confirmado, o motor pede o `mes_fatura`.
- O vínculo `DOCUMENTO_FISCAL` e os eventos ficam como no Flask.

### OCR (complementar)

- O texto de PDF textual é extraído **no navegador**, pelo `pdf.js` já usado no projeto, sem serviço externo, e guardado em `texto_extraido`.
- Sem texto, o documento fica `PENDENTE_REVISAO` para preenchimento manual. A falta de OCR não bloqueia o cadastro.

## 2. Diferenças em relação ao Flask (correções)

1. **Exclusão segura:** o Flask não tinha. Só exclui documento sem nenhum vínculo, ativo ou histórico, e não validado. Documentos ligados ao histórico financeiro ficam preservados.
2. **O mesmo documento não gera duas despesas.** O Flask permitia; aqui a segunda tentativa é recusada com `DUPLICADO`, sem gravar.
3. **Vínculo `PATRIMONIO`:** um documento, um bem, como a tela de Patrimônio e o novo aplicativo. Isso resolve, no novo aplicativo, a pendência 1 do FIN-ESCRITOR-UNICO-GUARDAS-1.
4. **Pagamento pela conta bancária** passa pelo motor de pagamento: movimento `DEBITO` e saldo coerente.
5. **Leitura automática:** a interpretação de NFS-e de Goiânia e de cupom fiscal e o OCR de imagem **não** foram portados. Ficam como pendência (§5).

## 3. Escritor único no Flask

- O blueprint `ir` passa a ter a guarda por blueprint: perfil no novo aplicativo recebe 409 `SISTEMA_NOVO` em **todas** as escritas de Documentos/IR.
- Essa guarda substitui as pontuais G1 e G3 do FIN-ESCRITOR-UNICO-GUARDAS-1. Os testes I8 e os de guarda continuam valendo.
- **`ocr_tools`:** grava só a configuração das ferramentas de OCR da máquina do Flask, em JSON no host. Não é dado de perfil e fica fora do escritor único.

## 4. Testes (bancos descartáveis, arquivos fictícios)

**`tests/test_supabase_documentos_escrita.py` (9 testes):**
- **Mesmas linhas que o Flask:** a mesma sequência roda no Flask, com envio real em multipart, e no novo aplicativo, com envio em base64. O arquivo fica igual byte a byte. A sequência:
  - envio;
  - revisão e validação;
  - vínculo criado, editado e removido;
  - despesa a partir do documento.
- **Texto de PDF:** guardado, e sem ele o documento fica para revisão manual.
- **Validações do arquivo:** tipo, MIME, vazio, mais de 10 MB, assinatura e nome; duplicidade por hash no perfil; repetição por chave; arquivo privado do perfil.
- **Escritor único e isolamento:** outro titular, documento de outro perfil, perfil no Flask.
- **Exclusão segura.**
- **Despesa não duplicada; lançamento pago pela conta (movimento e saldo) e no cartão.**
- **Um documento, um bem.**
- **Privilégios e reversão:** a reversão preserva os dados, e a reaplicação funciona.

**Também:**
- `test_supabase_escritor_unico_guardas.py`: os blueprints inteiros guardados.
- I3: as rotas de `ir` respondem 409 em perfil do novo aplicativo.
- **Web:**
  - `documentos-fiscais-adaptador.js` grava pelas funções novas;
  - `build.test.mjs` libera cada RPC só nesse adaptador;
  - o E2E `documentos_fiscais_tela.spec.mjs` cobre revisão e envio pela ponte (`FormData`), com o reenvio reconhecido como duplicado.
- **Testes vizinhos:** 103 aprovados, entre eles os de Documentos, Patrimônio, integração e guardas do Flask.

## 5. Pendências (trabalho futuro)

1. **Leitura automática:** interpretação de NFS-e e cupom fiscal (`_processar_texto_extraido`) e OCR de imagem, sem serviço externo.
2. **Documentos da Empresa:**
   - metadados empresariais (`PUT /comprovantes/<id>/metadata-empresarial`);
   - checklist;
   - saídas sem documento (vincular e status);
   - categorias IR e vínculos de categoria.

   Até lá, nesses pontos, um perfil no novo aplicativo não grava por nenhum dos dois sistemas.
3. **A partir de documento na página Despesas** (atalho da tela de Despesas para criar a despesa de um documento). A função pronta é `criar_financeiro_documento`; falta só a tela.
4. **Relatórios de Documentos** (Excel, PDF, ZIP), no B2 (FIN-RELATORIOS-CONFIG-1).
5. **Aplicação no remoto:** `20261128090000`, com autorização. Ordem de reversão: 1128 → 1127 → 1126 → 1125 → 1124 → 1123.
