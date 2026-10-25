# FIN-MIGRACAO-FIDELIDADE-FASE-1 — Moldura, navegação e perfis do Flask no novo aplicativo

**Situação:** implementada e testada **localmente**, com dados fictícios.
- Sem migration remota, sem publicação, sem commit e sem push.
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

## F. Para publicar a prévia (cada etapa depende de autorização)

1. Aplicar `20261102090000` no Supabase de teste. Sem ela, a lista de Configurações mostra "Não foi possível carregar os perfis financeiros"; o restante funciona.
2. Gerar o `dist` e publicar só na branch `avaliacao` (`docs/FIN_PUBLICACAO_PREVIEW_2.md`, seção 6).
