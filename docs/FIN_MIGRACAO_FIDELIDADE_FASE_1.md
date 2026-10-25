# FIN-MIGRACAO-FIDELIDADE-FASE-1 — Moldura, navegação e perfis do Flask no novo aplicativo

**Situação:** concluída tecnicamente (FIN-MIGRACAO-FIDELIDADE-FASE-1-REAL, 24/10/2026).
- Migration aplicada só no Supabase de teste.
- Validada com dados fictícios e publicada na prévia protegida: **https://avaliacao.controle-financeiro-jah.pages.dev**.
- Sem push e sem deploy de produção. A aprovação da fidelidade visual depende da avaliação do titular no navegador (§G).
- Diagnóstico e plano: `docs/FIN_MIGRACAO_FIDELIDADE_1.md`, com as decisões do titular na seção H.

## A. Interface reaproveitada e adaptada

**Reaproveitado sem alteração** (o build copia do `frontend/static`):
- CSS: `style.css`, `layout.css`, `instituicoes.css`, `formas_pagamento.css`, `configuracoes.css`, `ajuda.css` e `theme-light.css`;
- JS: `ajuda.js`.

**Convertido para página estática, com a mesma marcação** (o build monta cada página):
- `base.html` virou `web/src/moldura/base.html`. Gerado mecanicamente do original, preserva barra lateral, seções, ícones SVG, barra superior e barra de ações.
- `ajuda.html`: sem alteração.
- `configuracoes.html`:
  - Perfis Financeiros e o resumo de Documentos Fiscais: sem alteração;
  - Preferências, Aparência, Comportamento, Backup e IA: mantêm o título original e mostram "Em migração".

**Adaptado:**
- `contexto_financeiro.js` virou `web/src/js/moldura.js`, sobre `meus_perfis`. Os elementos são criados por DOM, porque a CSP proíbe `innerHTML` e estilo inline.
- A parte de perfis de `configuracoes.js` virou `web/src/js/configuracoes.js`. Mesmo fluxo ao salvar: dados, depois ativar ou inativar, depois padrão.

**Telas existentes:** Despesas (a antiga "Contas"), Receitas, Cartões e Categorias passaram para a moldura. O conteúdo não mudou (será refeito na Fase 2). As abas Contas | Receitas | Cartões deram lugar ao menu.

**Não carregados por enquanto:** `icons.js`, `modals.js`, `instituicoes.js`, `formas_pagamento.js` e `auth.js`. Nenhuma tela migrada os usa ainda; entram na Fase 2 com as telas originais.

## B. Navegação

**Menu:** idêntico ao do Flask, nas mesmas seções, ordem, nomes e ícones (conferido por teste em todas as 15 páginas).

| Item | Página | Situação |
|---|---|---|
| Despesas | `contas.html` | Funcional; é a entrada temporária depois do login |
| Receitas | `receitas.html` | Funcional |
| Cartões | `cartoes.html` | Funcional |
| Categorias | `categorias.html` | Funcional |
| Configurações e Preferências | `configuracoes.html` | Perfis funcionais; demais seções "Em migração" |
| Ajuda e Manual | `ajuda.html` | Funcional (manual original) |
| Dashboard, Lançamentos, Recorrencias, Contas Bancárias, Financiamentos, Patrimônio, Documentos Fiscais, Mobilidade, Importar Cartão | página própria | "Em migração" |

**Itens "Em migração":**
- No menu, um selo discreto, sem esconder nem desabilitar o item.
- A página é informativa: título e função do módulo, aviso de que nada foi removido e links para o que já funciona. Não lê dados financeiros.
- O build falha se algum item do menu não tiver página.

**Barra superior:**
- ☰, título do Flask (`page_title`), Ajuda, seletor de perfil, Alertas e Sair.
- Alertas mostra "Alertas: em migração para o novo aplicativo.".

**Navegação por competência:** os itens Despesas, Receitas e Cartões mantêm o `?mes=` aberto.

**Celular:** o ☰ abre e fecha a mesma barra lateral, com fundo escurecido. Fecha por Esc, toque no fundo ou escolha de item. Corrige o defeito do Flask, sem mudar o visual.

**URLs sem `.html` do Pages:** passam a manter o destino depois do login. Isso corrige a ressalva da prévia.

## C. Perfis

| Requisito | Como ficou |
|---|---|
| Ver o perfil ativo | No seletor original do topo: avatar, nome e tipo |
| Alternar | Pelo seletor. A página recarrega, como no Flask, e nada do perfil anterior fica na tela |
| Manter ao navegar | Escolha por usuário no navegador. Vale em todas as páginas e abas e é revalidada no banco a cada consulta |
| Criar, editar, ativar, inativar, padrão | Configurações → Perfis Financeiros (tela original) |
| Usuário, perfil e permissão distintos | O menu de perfis mostra a conta conectada. Perfis só de leitura aparecem marcados ("somente leitura" e o selo "Somente leitura"), com o formulário bloqueado |

**Regras do Flask preservadas:**
- nome obrigatório e único;
- tipo PESSOAL/EMPRESA/OUTRO;
- apelido derivado do nome;
- cor padrão `#2563eb`;
- não inativar o único perfil ativo nem o perfil em uso;
- o padrão passa a outro perfil ao inativar;
- o perfil reativado vira padrão se não houver outro.

**Adaptações e correções** (não perpetuar defeitos):
1. **O nome "Pessoal" fica reservado e o perfil "Pessoal" não é renomeado.** Registros sem perfil pertencem ao perfil de nome "Pessoal". Renomeá-lo, ou dar esse nome a outro perfil, mudaria quem vê esses registros.
2. **Cor só em `#RRGGBB`.** O Flask aceitava qualquer texto de 7 caracteres.
3. **"Padrão" continua sendo a coluna única do Flask.** Só muda quando o usuário também gere o padrão atual, para nunca alterar o perfil de outro titular. "Único perfil ativo" conta os perfis do próprio usuário.
4. **Quem cria um perfil recebe gestão só desse perfil** (vínculo TITULAR).
5. **O perfil criado pelo novo aplicativo já nasce com o gerador de recorrências NOVO** (FIN-MIGRACAO-FIDELIDADE-FASE-1-REAL).
   - A atribuição ocorre na mesma transação da criação, pela função de administrador `definir_gerador_recorrencia`, com auditoria no histórico.
   - Se a atribuição falhar, o perfil não é criado.
   - Perfis existentes mantêm o gerador que já tinham (Flask ou novo aplicativo); nenhum perfil real é alterado.

## D. Funções de integração

**Migration local:** `supabase/migrations/20261102090000_financeiro_perfis_gestao.sql`. Não foi aplicada no remoto. Sem tabela nova.

**Funções públicas** (`authenticated`; `security definer`, `search_path` vazio):
- `perfis_para_configuracao`: só leitura; os próprios perfis, inclusive inativos, com papel e gestão;
- `criar_perfil`;
- `atualizar_perfil`;
- `inativar_perfil`;
- `reativar_perfil`;
- `definir_perfil_padrao`.

Todas as de escrita exigem `perfil_acesso.pode_gerir` do perfil e serializam pela mesma trava.

**Funções internas** (sem EXECUTE): `gere_perfil`, `perfil_em_json`, `normalizar_dados_perfil` e `aplicar_perfil_padrao`.

**Camada de dados no navegador:** única, em `web/src/js/perfil.js`. O teste do build exige que as RPCs de perfil só sejam chamadas dali.

## E. Testes (locais)

| Conjunto | Resultado |
|---|---|
| `tests/test_supabase_perfis_gestao.py` (novo, banco e REST; inclui gerador do perfil novo, atomicidade e geração de recorrências) | 48/48 |
| Todos os `tests/test_supabase_*.py` + `test_sec_supabase_public.py` + `test_movimentacoes.py` | 461/461 |
| Conferência local da migration (`supabase_conferencia_migration.py --alvo 20261102090000 local`) | Privilégios conforme o esperado |
| Unitários do web (build, moldura, RPCs liberadas) | 17/17 |
| E2E completos (`run_e2e.py`), incluindo `moldura.spec` e `perfis_gestao.spec` (novos) | 63/63, sem erro de CSP ou JS |

**Comparação visual com o Flask** (mesmas resoluções das capturas do diagnóstico):
- Barra lateral: mesmas alturas e posições, item a item.
- Barra superior, seletor de perfil e Configurações: iguais ao original, inclusive a coluna central estreita que o Flask já tem em 1366 px.
- As telas de conteúdo seguem as atuais até a Fase 2.

**Observação para a Fase 2:** as notas "Recebimentos/Pagamento de fatura continuam sendo registrados no sistema atual", em Receitas e Cartões, estão desatualizadas desde o FIN-MOVIMENTACOES-1.

## F. Publicação

Executada no FIN-MIGRACAO-FIDELIDADE-FASE-1-REAL (§G): migration aplicada no Supabase de teste e `dist` publicado só na branch `avaliacao`, conforme `docs/FIN_PUBLICACAO_PREVIEW_2.md` §6.

## G. Validação real e publicação (FIN-MIGRACAO-FIDELIDADE-FASE-1-REAL)

**Correção da responsabilidade pelos perfis novos.** Foi incorporada à `20261102090000`, que ainda estava só no repositório: o status remoto mostrava 13 aplicadas e só ela pendente.
- `criar_perfil` atribui o gerador NOVO na mesma transação, por `definir_gerador_recorrencia`, auditado em `gerador_recorrencia_historico` ("criar_perfil (usuario …)").
- Perfis existentes não mudam.
- Testes locais:
  - atribuição e histórico;
  - geradores dos demais perfis idênticos;
  - falha simulada na atribuição desfaz a criação (nenhum perfil nem vínculo sobra);
  - geração de recorrências no perfil novo;
  - o criador administra e o outro usuário não vê.
- Resultados: 48/48 na suíte de perfis; suítes de gerador, perfis e recorrência e E2E de moldura e perfis 16/16.

**Migration no Supabase de teste (`fzjmge…`).**

| Etapa | Resultado |
|---|---|
| `antes` (somente leitura) | Projeto confirmado pela conexão; 13 aplicadas, só `20261102090000` pendente, nada só no banco; 64 tabelas e 106 funções registradas |
| Aplicação | `supabase_migrations.py aplicar --versoes 20261102090000`: só ela |
| `depois` | 14/14. Só as 10 funções previstas (6 públicas para `authenticated`, 4 internas sem EXECUTE; todas `search_path` vazio). Contagem e md5 de todas as tabelas iguais (nada existente mudou) |

**Validação real** (mesmo `dist` depois publicado, servido com o `_headers` real, contas de teste).

Interface e perfis (4/4):
- login, menu do Flask, navegação pelas 15 páginas e competência mantida;
- Alertas, Ajuda, menu e seletor no celular, saída.

Gestão pela tela, num perfil temporário criado pelo próprio aplicativo:
- criar, editar, usar, inativar e reativar;
- isolamento: o perfil novo não vê dados da demonstração;
- definição de padrão recusada, porque o padrão atual (Pessoal) não é gerido pela conta de teste e nada pode mudar nos perfis existentes.

Operações dentro da moldura, só no perfil temporário (4/4):
- despesa: pagar com juros justificados e estornar;
- receita: receber parcial e estornar;
- cartão: comprar, pagar a fatura e estornar;
- saldos conferidos a cada passo.
- Leitor: a conta B vê, mas não altera (formulário bloqueado, sem "Nova despesa").

Data API:
- Isolamento: B não lê a demonstração (403).
- O leitor recebe 403 em atualizar, inativar, definir padrão e criar despesa.
- A recebe 403 ao alterar o Pessoal; o padrão é recusado com 42501.
- Anônimo recebe 401.
- Geração real no perfil novo: prévia com gerador NOVO e `pode_gerar`; `gerar_mes` 200; contas de 06/2035 geradas.

Nenhuma chamada fora do próprio site e do Supabase; nenhuma chamada ao Flask; sem erro de CSP ou JS.

**Limpeza.**
- Identidade conferida:
  - perfil criado pelo aplicativo (histórico do gerador);
  - só os vínculos do teste;
  - só a conta bancária marcada;
  - todas as tabelas com `perfil_financeiro_id` contadas, sem sobra.
- Simulação, depois confirmação.
- Resultado: o banco ficou idêntico ao de antes da migration (contagem e md5 de todas as tabelas, inclusive os dados de demonstração). Perfis 1 (Pessoal), 2 (Empresa) e 31 (demonstração) intactos.

**Publicação.**
- Build com a URL e a chave **publicável** do projeto de teste. 16 páginas, CSP inalterada, sem segredos e sem referência ao Flask (`/api/`, `localhost`, `:5000`, Render).
- Cloudflare Access protegia a prévia antes e depois do envio: 302 para o login do Access na prévia, em páginas internas, em `config.js` e no endereço da versão. O endereço principal continua sem deploy (404).
- Envio: `wrangler pages deploy dist --project-name controle-financeiro --branch avaliacao`, versão `1cc8025` (impressão do `dist` `49189f04a7b2`).
  - Implantação `17a39256` (Preview, branch `avaliacao`), endereço **https://avaliacao.controle-financeiro-jah.pages.dev**.
  - Nenhuma implantação de produção; `kortex-site` e `kortex-calculadora` não foram tocados.
- Pós-publicação (mesmo `dist`, 1/1):
  - perfil de demonstração disponível, com 6 despesas, 4 receitas, faturas e 2 contas;
  - menu completo e competência mantida;
  - Configurações e uma página "Em migração" sem erros e sem chamadas ao Flask.
- **Limite da conferência:** a política do Access (só o e-mail do titular) foi conferida pelo comportamento: tudo exige o login do Access. O conteúdo da política no painel do Zero Trust não pode ser lido com o escopo atual do Wrangler.

**Diferenças visuais que permanecem** (Fase 2):
- o conteúdo de Despesas, Receitas, Cartões e Categorias ainda é o das telas atuais, não o do Flask;
- as páginas dos módulos "Em migração" são informativas;
- Configurações tem as seções além de Perfis "Em migração";
- o selo "Em migração" é o único acréscimo visual no menu.

**Pendências da Fase 2:**
- telas originais de Despesas e Recorrências, Receitas, Lançamentos e Cartões, Contas Bancárias e Categorias, que precisam de funções de escrita novas;
- notas desatualizadas de Receitas e Cartões;
- `icons.js` e `modals.js` com as telas originais;
- Importar Cartão com prioridade elevada logo depois.
