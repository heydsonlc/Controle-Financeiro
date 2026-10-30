# FIN-MIGRACAO-P0P1-01 — Empresa, Documentos Fiscais e catálogo de categorias no novo aplicativo

**Situação (30/10/2026): Etapa 1 pronta.**
- Código e testes prontos.
- A produção não foi alterada: nenhuma ativação, nenhum envio real e nenhuma categoria criada.
- Nada foi publicado; sem commit e sem push.

A Etapa 2 (ativação em produção) depende de autorização expressa.

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
