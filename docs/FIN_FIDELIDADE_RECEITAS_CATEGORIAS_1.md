# FIN-FIDELIDADE-RECEITAS-CATEGORIAS-1 — Telas originais de Receitas e Categorias (Flask → Supabase)

**Data:** 26/10/2026.

**Situação:** implementado e testado **localmente** (cluster descartável, Flask real para comparação, PostgREST e Playwright).
- Sem commit, sem push, sem publicação.
- A migration `20261119090000` **não foi aplicada** em lugar nenhum.
- O Flask, o `gastos.db` (1294336 bytes, mtime 1778600040, conferido) e os arquivos pessoais não foram tocados.

## 1. Funcionalidades originais identificadas

| Módulo | No Flask (template, JS, rotas) |
|---|---|
| Receitas | `templates/receitas.html` + `static/js/receitas.js` (1469 linhas) + `routes/receitas.py`. A tela monta tudo no navegador a partir de três listas: `GET /itens` (fontes), `/orcamento?ano=` (previsões do ano) e `/realizadas?ano_mes_inicio=&ano_mes_fim=`. **Ações acessíveis:** nova fonte; editar fonte (ou recebimento pontual); inativar fonte; "Confirmar/realizar" (consolida o que falta, com a data de hoje, numa conta); estornar recebimento; "Cancelar/ignorar" (zera a previsão; recebimento com movimento: recusa). O modal "Planejar receita" (`modal-orcamento`) existe, mas nenhum botão o abre |
| Categorias | `templates/categorias.html` + `static/js/categorias.js` (1329 linhas) + `routes/categorias.py`. **Categorias de despesa:** globais, com cadastro, edição, exclusão, palavras-chave e logo (arquivo em disco). **Categorias do Cartão:** por perfil, com cadastro, edição, desativar/reativar e vínculos com categorias de despesa (uma categoria de despesa só pode ter um vínculo ativo por perfil) |

**Leituras do Flask que gravam** (não reproduzidas): `GET /api/receitas/itens` roda o backfill de contemplação de consórcio.

## 2. Implementado

- **Telas:**
  - `web/src/paginas/receitas.html` e `categorias.html` são os templates do Flask sem alteração, com estes acréscimos:
    - o laço Jinja do dia previsto expandido;
    - o aviso de fase;
    - em Receitas, três campos no modal "Consolidar" (§5).
  - O JS e o CSS são os do Flask (`js/original/`, `css/shared/`), com a conversão de CSP de sempre.
- **Adaptadores:**
  - `receitas-adaptador.js` e `categorias-adaptador.js` respondem as rotas `/api/...` no formato do Flask, sem chamada ao Flask.
  - `receitas-adaptacoes.js` cuida das duas adaptações de comportamento do §5.
- **Migration `20261119090000_financeiro_receitas_categorias_tela.sql`** (local):
  - **leituras no formato `to_dict` do Flask:** `receitas_fontes_tela`, `receitas_orcamentos_tela`, `receitas_realizadas_tela`, `categorias_tela`, `palavras_chave_tela`, `categorias_cartao_tela` e `categoria_cartao_despesas_tela`;
  - **escrita das Categorias do Cartão:** `criar_categoria_cartao`, `editar_categoria_cartao`, `desativar_categoria_cartao`, `vincular_despesa_categoria_cartao` e `desvincular_despesa_categoria_cartao`;
  - só funções e privilégios: nenhuma tabela e nenhum dado; nenhuma função existente é trocada.
- **Removidos:** `web/src/js/receitas.js`, `categorias.js` e `liquidacao.js` (tela simplificada, substituída) e `web/tests/e2e/receitas.spec.mjs`.

## 3. Funções do Supabase reutilizadas (sem regra duplicada no navegador)

**Receitas** (já aplicadas no Supabase de teste):

| Ação na tela | Função |
|---|---|
| Fonte nova | `criar_receita` (idempotente) |
| Editar fonte | `editar_fonte_receita` |
| Inativar fonte | `inativar_fonte_receita` |
| "Cancelar/ignorar" previsão | `excluir_receita`: a recorrente é zerada, como no Flask |
| Planejar | `editar_receita` / `criar_receita` |
| Consolidar | `dados_recebimento_receita` + `receber_receita`: escritor único, chave, justificativa acima do que falta |
| Estornar | `estornar_recebimento` |

**Contas da tela:** `contas_bancarias_tela`.

## 4. Migrations necessárias

- Só `20261119090000`, para as duas telas funcionarem no Supabase de teste e na prévia. Sem ela, as leituras não existem e as páginas ficam vazias com erro.
- **Não aplicar sem autorização:** é preciso aplicá-la antes de publicar estas telas na prévia.
- **Conferido só lendo o remoto:** as 7 tabelas que ela usa têm as mesmas colunas e tipos no Supabase de teste. Nenhuma das funções novas existe lá.

## 5. Diferenças em relação ao Flask (intencionais, registradas)

**Receitas** (melhorias do FIN-RECEITAS-1 e FIN-MOVIMENTACOES-1 preservadas):
1. **Sem linha "virtual":**
   - O Flask mostra uma fonte recorrente sem previsão gravada no mês como prevista, pelo valor base.
   - Aqui só aparecem previsões e recebimentos reais, os mesmos números do Dashboard (D2) e de Despesas.
2. **Recebimento estornado não conta** e a previsão volta a pendente. O Flask continua somando o estornado como recebido.
3. **"Consolidar" ganhou valor, data e justificativa:**
   - O Flask registra só o que falta, com a data de hoje: recebimento parcial é impossível na tela dele.
   - Com o exemplo do titular: previsto 10.000, recebido 9.500, diferença −500, aparecem nas colunas e indicadores originais, sem somar duas vezes.
   - Acima do que falta, exige justificativa: o banco recusa sem ela.
4. **Fonte nova nasce com a previsão** (`criar_receita`):
   - Valor base obrigatório.
   - Recorrente: 12 previsões a partir da competência **escolhida nos filtros** (o Flask usa o mês atual).
   - Avulsa: uma previsão na competência.
   - O Flask cria a fonte avulsa sem previsão.
5. **Editar fonte não muda valor base nem recorrência.** As previsões gravadas ficam; a tela recusa com mensagem. O Flask grava o valor base e gera as previsões que faltam nos 12 meses seguintes.
6. **Continuam no sistema atual** (recusa com mensagem, nada gravado): recebimento sem previsão, editar ou excluir recebimento (corrigir = estornar e receber de novo) e reativar fonte.
   - Excluir recebimento com movimento também é recusado no Flask, com a mesma mensagem.
7. **Perfil ainda no Flask:** consolidar e estornar recusam ("Os recebimentos deste perfil ainda são feitos pelo sistema atual").
   - O cadastro de fontes e previsões segue a regra das funções já aplicadas, que não exigem o escritor do perfil.
   - Isso está na lista do `FIN_ESCRITOR_UNICO_CONTAS_1.md` §3.1.

**Categorias:**
1. **Categorias de despesa, palavras-chave e logos: nenhuma escrita.**
   - São globais e servem a todos os perfis, inclusive Pessoal e Empresa, ainda no Flask.
   - Os botões ficam como no Flask; a ação responde que continua no sistema atual.
2. **Logos:** os arquivos estão no disco do servidor Flask. A tela mostra o ícone (`logo_url` nulo).
3. **Cor da Categoria do Cartão** precisa ser `#RRGGBB`. O Flask grava qualquer texto, e a cor vai para o estilo da página.

**Ambas:** o "descri&ccedil;&atilde;o" com escape duplo e o corte da coluna de ações de Receitas em 1366 px são do JS e do CSS originais. Foram reproduzidos, não corrigidos (§9).

## 6. Dependências pendentes

| Pendência | Prioridade |
|---|---|
| Aplicar `20261119090000` no Supabase de teste (autorização) | condição para publicar estas telas |
| **Guarda do Flask nas rotas de Categorias do Cartão** (`routes/categorias.py`, 5 rotas): o banco já recusa o perfil do Flask; o Flask ainda grava num perfil NOVO quando apontar para o mesmo banco. Este contrato não autorizou mudar o Flask | P0 antes de atribuir perfil real ao NOVO |
| **Dono do catálogo global de categorias de despesa:** escrita fica no Flask até a decisão. O novo aplicativo grava só quando todos os perfis estiverem nele, ou com uma regra explícita | P1 (decisão) |
| Logos de categoria: armazenamento no Supabase (Storage) e migração dos arquivos | P2 |
| Data prevista independente da competência (FIN-RECEITAS-DATA-REAL-1): continua no banco e em Despesas; a tela original de Receitas não a mostra nem edita | P2 |
| Editar valor base e recorrência da fonte, e reativar fonte (§5) | P2 |
| Corte da coluna de ações de Receitas e do painel de Categorias em 1366 px (CSS do Flask) | P3 (decisão: corrigir como em Cartões ou manter) |

## 7. Testes executados

| Conjunto | Resultado |
|---|---|
| `tests/test_supabase_receitas_categorias_tela.py` (novo) | **12 passaram**. Detalhes abaixo |
| E2E `receitas_tela.spec.mjs` (novo) | **4 passaram**. Detalhes abaixo |
| E2E `categorias_tela.spec.mjs` (novo) | **4 passaram**. Detalhes abaixo |
| E2E completo (cluster + PostgREST + Playwright) | **87 passaram**, 0 falhas (inclui as specs adaptadas: acesso, perfis, moldura, gestão de perfis, movimentações) |
| Banco do Supabase (`test_supabase_*`) + mapa de impacto + Flask de movimentações, receitas e categorias | **684 passaram, 2 falharam, 18 pulados.** As 2 falhas são as preexistentes do P7 de `DEPLOY_READY_FIN_1.md` (`test_receitas_ux`, `test_categorias_sistemicas_mobilidade`) |
| Unitários do `web/` (build, auditoria de RPC por arquivo, moldura) | **30 passaram** |

**Banco (`test_supabase_receitas_categorias_tela.py`):**
- O próprio Flask monta o cenário pelas rotas dele: fonte recorrente com 12 previsões, avulsa, recebimento parcial, pontual, estorno, Categoria do Cartão, vínculo e palavra-chave.
- As leituras são iguais às do Flask, campo a campo, para Pessoal, Empresa e Perfil B.
- A mesma sequência de escrita de Categoria do Cartão no Flask e no novo deixa o mesmo estado.
- As recusas usam as mensagens do Flask.
- Escritor único: o perfil no Flask não grava, e nada muda.
- Quem só lê e outro perfil são recusados.
- Vínculo e desativação não reclassificam compras.
- Privilégios conferidos.

**E2E `receitas_tela.spec.mjs`:**
- Tela original com previsto, realizado e diferença sem duplicidade e sem linha virtual.
- No Perfil B (novo aplicativo): fonte nova, recebimento parcial, recusa sem justificativa, recebimento acima com justificativa, estornos e inativação; a conta volta a 0.
- Pessoal (Flask): consolidar recusado.
- Quem só lê não vê ações.
- Isolamento.

**E2E `categorias_tela.spec.mjs`:**
- Tela original com palavras-chave, Categorias do Cartão e vínculos.
- No Perfil B: criar, editar, vincular, desvincular, desativar e reativar.
- Categoria de despesa e palavra-chave não gravam.
- Pessoal (Flask): recusa.
- Quem só lê não vê ações.

**Specs adaptadas:**
- `acesso`, `perfis`, `moldura` e `perfis_gestao` usavam a página provisória de Categorias para conferir contas e a tabela por usuário do MVP.
- Agora conferem as contas na tela original de Contas Bancárias, e a tabela do MVP pela API, com a mesma sessão.
- O teste de receita de `movimentacoes.spec` foi substituído por `receitas_tela.spec`, que cobre os mesmos fluxos pela tela original.

## 8. Arquivos alterados

- **Novos:**
  - `supabase/migrations/20261119090000_financeiro_receitas_categorias_tela.sql`;
  - `tests/test_supabase_receitas_categorias_tela.py`;
  - `web/src/js/receitas-adaptador.js`, `receitas-adaptacoes.js` e `categorias-adaptador.js`;
  - `web/src/css/receitas-adaptacoes.css` e `categorias-adaptacoes.css`;
  - `web/tests/e2e/receitas_tela.spec.mjs` e `categorias_tela.spec.mjs`;
  - este documento.
- **Alterados:**
  - `web/src/paginas/receitas.html` e `categorias.html` (geradas dos templates);
  - `web/scripts/build.mjs` (CSS e JS originais);
  - `web/tests/unit/build.test.mjs` (auditoria de RPC);
  - specs E2E: `acesso`, `perfis`, `moldura`, `perfis_gestao` e `movimentacoes`.
- **Removidos:**
  - `web/src/js/receitas.js`, `categorias.js` e `liquidacao.js`;
  - `web/tests/e2e/receitas.spec.mjs`.

## 9. Fidelidade visual (1366 × 900, mesmos dados fictícios, mesmos filtros e estados)

| Tela | Resultado |
|---|---|
| Receitas, 11/2026 (indicadores, lista, colunas, badges, rodapé) | **Igual.** Mesmos valores: previsto 5.800, realizado 2.000, diferença −3.800, confiabilidade 34,5%. A coluna de ações aparece cortada à direita **nos dois** |
| Receitas, modal "Nova fonte" | Igual |
| Categorias de Despesa (lista, detalhe, palavras-chave, resumo) | **Igual.** Diferenças só nos dados fictícios: data de criação nula no cenário E2E, uma palavra-chave a mais |
| Categorias do Cartão (lista, detalhe, vínculos, ícones) | **Igual.** Os ícones carregam (conferido no navegador; a captura imediata pegou o carregamento `lazy` em andamento) |

**Acréscimo visível nas duas telas:** o aviso de fase.

**Capturas** (fora do repositório, no scratchpad da sessão, em `capturas_receitas_categorias/`): `flask_*.png` e `novo_*.png`.

## 10. Situação da escrita de Categorias

| Operação | Situação |
|---|---|
| Categoria do Cartão: criar, editar, desativar/reativar, vincular e desvincular | **Implementada e testada localmente**: escritor único e gestão no banco, equivalência com o Flask. Depende da migration (não aplicada). Falta a guarda do lado do Flask (§6) |
| Categoria de despesa: criar, editar, excluir; palavras-chave; logo | **Bloqueada por decisão de segurança:** catálogo global compartilhado com perfis no Flask. Pendente da decisão do dono do catálogo (§6) |

**A conclusão visual não é conclusão operacional:** as duas telas reproduzem o Flask; a operação completa depende dos itens do §6.
