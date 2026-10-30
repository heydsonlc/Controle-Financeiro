# FIN-MIGRACAO-P0P1-01 — Empresa, Documentos Fiscais e catálogo de categorias no novo aplicativo

**Situação (30/10/2026): `FIN_MIGRACAO_P0P1_01_CONCLUIDA`** (Etapa 2 em §6).
- O build foi publicado antes da ativação.
- A Empresa e o catálogo estão no novo aplicativo, e o titular é gestor do catálogo.
- Os testes reais foram feitos pela tela.
- Commits `646912c` (código) e `c66db6e` (documentação), enviados ao GitHub pelo push autorizado pelo titular: `origin/main` avançou de `34daa7c` para `c66db6e`, sem force.
- Produção: deploy `ad78c215`.

## 1. Por que

| Achado (diagnóstico de completude) | Causa |
|---|---|
| Anexo em Documentos Fiscais "sumia" da tela | A Empresa não tem escritor no novo aplicativo (`gerador_recorrencia` sem linha = FLASK). `enviar_comprovante` recusava (P0001, hint `SISTEMA_FLASK`). O adaptador respondia 409 sem `data`, e a tela original (`renderResultadoUpload(json.data \|\| [])`) apagava a lista sem mostrar nada |
| Categoria de despesa: o formulário inteiro era preenchido e só o salvar recusava, citando o Flask | O catálogo global não tem escritor (`catalogo_categorias` vazio = FLASK) nem conta gestora (`gestor_catalogo` vazio) |
| Mensagens "continua no sistema atual (Flask)" | O Flask grava num banco local (`controle_financeiro_dev`), fora da produção. Nenhum desses caminhos altera os dados reais |

## 2. Mecanismo oficial (sem migration)

| Operação | Função (só administrador; sem EXECUTE para o navegador) | O que grava |
|---|---|---|
| Empresa grava no novo aplicativo | `financeiro.definir_gerador_recorrencia(2, 'NOVO', responsável, motivo)` | 1 linha em `gerador_recorrencia` e 1 em `gerador_recorrencia_historico` (gatilho de auditoria) |
| Catálogo no novo aplicativo | `financeiro.definir_escritor_catalogo('NOVO', responsável, motivo)`; exige as 10 categorias sistêmicas `MOB_*` | 1 linha em `catalogo_categorias` (sem histórico próprio: o relatório da Etapa 2 registra antes e depois) |
| Titular gestor do catálogo | `financeiro.definir_gestor_catalogo(<auth user id>, true, responsável, motivo)` | 1 linha em `gestor_catalogo`, pelo id do Auth, nunca pelo e-mail |

**Efeitos colaterais investigados:**
- **Gatilhos:** a única tabela administrativa com gatilho é `gerador_recorrencia`, e o gatilho só grava a auditoria. Nada gera dados no momento da troca.
- **Geração automática:** a tela de Despesas só chama `gerar_mes` com `pode_gerar` e `a_gerar > 0`. Com zero a gerar, `gerar_mes_interno` sai antes de gravar.
- **Itens sem perfil:**
  - são lidos como Pessoal, e só pelo nome "Pessoal" (`plano_recorrencia` e `recorrencias_do_perfil`);
  - nunca entram na Empresa;
  - em produção são 58, todos consórcios inativos.
- **Empresa em produção (30/10, somente leitura):**
  - só 1 acesso (titular, gestor) e 1 preferência de interface;
  - todas as outras tabelas com perfil estão vazias;
  - prévia zero em 2025-01, 2026-10…2027-01 e 2027-06.

## 3. O que mudou no código

- **Envio em Documentos Fiscais** (`documentos-fiscais-adaptador.js`):
  - Toda falha volta por arquivo, com o motivo.
  - Recusa do perfil inteiro (escritor ou permissão) interrompe o envio e vale para todos os arquivos (409, `success:false`, `data` por arquivo).
  - Quando o arquivo é gravado mas a releitura falha, ele não vira "não enviado".
  - O painel "Arquivos importados" mostra o retorno (`#cf-upload-retorno`: sucesso, parcial ou erro, com `role=alert` no erro).
  - O selo do arquivo recusado passa de "Erro de leitura" para "Não enviado".
  - O JS do Flask não muda.
- **Mensagens** (`adaptador-comum.js`):
  - As dicas do banco viram um texto único: `SISTEMA_FLASK` → "Este perfil ainda não está habilitado para gravação no novo aplicativo"; também `GERADOR_FLASK`, `CATALOGO_FLASK` e `COM_DOCUMENTOS`.
  - O mesmo vale para os dois textos do banco que citavam o sistema atual.
  - Rotas fora da fase: "ainda não está disponível nesta versão do aplicativo".
  - Avisos das páginas revistos.
  - Nenhum texto visível manda o usuário ao Flask.
- **Categorias** (`categorias-adaptador.js`):
  - A tela consulta `situacao_catalogo_categorias`.
  - Sem catálogo NOVO ou sem conta gestora, as ações das categorias de despesa ficam escondidas e um aviso diz o motivo.
  - O painel de logo fica desabilitado: "Upload de logo ainda não disponível nesta versão."
- **`scripts/verificar_ambiente.py`:** ausência do `.env.e2e-real` = OK (`NAO_CONFIGURADO_INTENCIONALMENTE`). Se o arquivo reaparecer, sai um AVISO.

## 4. Testes

| Suíte | Cobertura |
|---|---|
| `tests/test_migracao_p0p1.py` (cluster descartável, estado igual ao da produção) | Empresa FLASK recusa e não grava. Ativação muda só as 2 tabelas administrativas (+1 linha cada), com prévia zero em 7 competências, inclusive retroativa, e o item legado sem perfil ativo; `gerar_mes` com zero não grava; Pessoal igual. Empresa NOVO grava documento (bytes, nome, MIME, tamanho, perfil) e conta bancária. Catálogo: `CATALOGO_FLASK`, não gestor 42501, gestor com CRUD completo e palavras-chave, sistêmica protegida, categoria em uso protegida, NOVO exige as sistêmicas |
| `web/tests/e2e/migracao_p0p1.spec.mjs` (usuário fictício D, Empresa vazia) | Pela tela: envio recusado com o motivo (409, `success:false`, nada gravado); ativação + Despesas em 4 competências sem gerar nada; envio autorizado (aparece, abre e os bytes conferem); catálogo como não gestor (ações escondidas, 403) e como gestor (criar, editar, palavras-chave, proteções, excluir; sistêmicas intactas) |
| Gancho só de teste `/__e2e__/admin` (`run_e2e.py`) | As operações de administrador da Etapa 2, só sobre a Empresa D e o usuário D do banco descartável, e o retrato do perfil |

## 5. Etapa 2 (preparada, não executada)

O roteiro fica fora do Git, na pasta temporária da sessão: `scratchpad/p0p1/etapa2_ativar.py`.
- **`verificar`:** somente leitura; foi rodado em 30/10, com resultado `PRE_CONDICOES_OK`.
- **`ativar --confirmar`:**
  - faz as três operações numa transação;
  - verifica o retrato completo depois de cada passo;
  - desfaz tudo se qualquer verificação falhar.

## 6. Etapa 2 (autorizada pelo titular em 30/10/2026; ordem: publicar antes de ativar)

| Passo | Resultado |
|---|---|
| Commit do código | `646912c` (46 arquivos); push depois, junto com `c66db6e` |
| Publicação | Cloudflare Pages, deploy `ad78c215` (branch `producao`), em https://controle-financeiro-jah.pages.dev. Build de 166 arquivos, só com a URL do projeto e a chave publicável. O rótulo do commit no deploy ficou `646912c2` por erro de digitação (o conteúdo é o do `646912c`) |
| Conferência antes de ativar (só leitura) | `PRE_CONDICOES_OK` às 17:01 UTC. Empresa em FLASK, com 1 acesso e 1 preferência; catálogo e gestor vazios; 10 sistêmicas intactas |
| Ativação (`etapa2_ativar.py ativar --confirmar`, uma transação, executor `postgres`, 17:02:33 UTC) | COMMIT, com todas as verificações internas aprovadas. Empresa FLASK → NOVO (histórico 101); catálogo FLASK → NOVO; gestor = conta `51f5d1d1`. Responsável "Titular (conta 51f5d1d1)" |
| Conferência depois do commit (só leitura) | Mudaram 4 tabelas, com +1 linha cada (escritor, histórico, catálogo, gestor). As outras 80 tabelas estão idênticas. Nenhuma conta, compra, movimento ou execução de geração nova. Prévias do Pessoal e da Empresa: 0 a gerar |
| Teste A: envio na Empresa (titular, pela tela, 17:10 UTC) | Documento 4, perfil 2, PDF de 1.629.760 bytes. O SHA-256 do conteúdo confere com o hash registrado; 1 operação e 2 eventos. Nenhuma outra tabela mudou |
| Teste B: catálogo (titular, pela tela) | 1ª tentativa (categoria 111): criar, adicionar palavra-chave e excluir; edição e remoção da palavra-chave não chegaram ao servidor. 2ª tentativa completa (categoria 112): criar 17:26:55, palavra-chave 17:27:09, editar 17:31:05, remover palavra-chave 17:31:18, excluir 17:31:30, todas com status 200 |
| Estado final do catálogo | 40 categorias e 221 palavras-chave, como antes; 10 sistêmicas com o mesmo md5. Ficam só os 2 registros de idempotência em `operacao_catalogo` |
| Documento do teste A | Mantido. É real, pelo nome (`Contrato_Social_e_Procuracao.pdf`), e não existe ação de excluir documento na tela (§7). Aguarda a decisão do titular |

## 7. Pendências registradas

1. **Documentos Fiscais sem ação de excluir documento.**
   - Nem a tela do Flask nem a do novo aplicativo têm o botão; o Flask não tem a rota.
   - O banco já tem `excluir_comprovante`.
2. **Classificação automática na Empresa.** O documento do teste A ficou como "Pagamento realizado / Pix pago" e conta como "Sem lastro". Editar os metadados empresariais continua fora (P1, Lastro da Empresa).
3. **Texto "Sem descri&ccedil;&atilde;o cadastrada."** com os códigos HTML aparecendo literalmente na tela de Categorias.
   - Defeito do JS original (`frontend/static/js/categorias.js:396`, `escapeHtml` sobre texto já codificado); também acontece no Flask.
   - P3, cosmético.
4. ~~Push~~ concluído: `34daa7c..c66db6e`. O documento real id 4 foi mantido por decisão do titular. Pendências 1 a 3 seguem para o FIN-MIGRACAO-LASTRO-EMPRESA-01.
