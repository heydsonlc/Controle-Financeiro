# FIN-MVP-MOBILE-10 — Alternância de perfis na Página Principal mobile

**Situação:** implementado no ramo local `mobile-10-perfis`, a partir de `mobile-09-recorrencias`. Não houve push, deploy nem migration, e nenhum dado real foi alterado.
**Escopo (titular, 15/11/2026):** "adicionar exclusivamente o pequeno ícone de usuário ao lado do sino, sem modificar o restante da Página Principal".
**Publicação:** suspensa até a homologação e a autorização expressa.

## 1. Comportamento

- Ícone de usuário à esquerda do sino, com o mesmo tamanho (44 px). Abaixo de 360 px ele passa a 36 px, para o título "Financeiro" não encostar nele.
- O toque abre um menu no padrão do "Mais", com o título "Perfil financeiro". Cada perfil do usuário aparece numa linha e o ativo leva a marca ✓. A lista vem de `meus_perfis`, a mesma do seletor do desktop: perfis ativos vinculados ao usuário.
- Escolher outro perfil grava a escolha como o desktop faz (`perfil.js` → `salvarPerfilAtivo`) e recarrega a página na mesma competência. Todas as páginas mobile, e o desktop, passam a abrir no perfil escolhido. Escolher o perfil já ativo só fecha o menu.
- O menu fecha com Esc, com toque fora ou ao escolher.
- O rótulo de acessibilidade do ícone diz o perfil ativo ("Perfil financeiro: X. Trocar perfil").
- É só preferência de tela: o banco revalida o acesso a cada consulta (`pode_acessar_perfil`).

O sino, a marca, a competência, os atalhos e a barra continuam iguais.

## 2. Arquivos

- `web/src/inicio.html`: o ícone e o menu, junto com o sino, num grupo `mob-cabecalho-acoes`. O cabeçalho distribui os filhos nas pontas e o grupo mantém os dois botões juntos à direita.
- `web/src/css/inicio-mobile.css`: ícone, grupo e menu. As regras são restritas a `body.mob-inicio`.
- `web/src/js/inicio-mobile.js`: `prepararPerfis` (lista, marca, escolha), sem consulta própria.
- Testes: `web/tests/unit/build.test.mjs` (teste novo) e `web/tests/e2e/mob10_perfis.spec.mjs` (novo).
- Prévia: `tests/supabase_local.py` e `web/tests/e2e/run_e2e.py` criam, só com `--previa`, o segundo perfil do usuário G, "Perfil G Empresa (fictício)", vazio.

## 3. Testes

- Unitários: 120/120.
- Funcionais (`mob10_perfis.spec`): 5/5.
  1. Ícone ao lado do sino, do mesmo tamanho, com o restante igual.
  2. Menu com os perfis do usuário A e o ativo marcado; Esc e toque fora fecham sem trocar. A troca grava a escolha do desktop, recarrega na mesma competência e a Lista de Despesas mobile abre no perfil escolhido; depois, volta ao anterior.
  3. Com um perfil só (usuário G), o menu mostra o perfil marcado e escolher o mesmo só fecha.
  4. e 5. Em 320 e 430 px, o menu cabe na tela e o título não encosta no ícone.
- Por impacto, as specs que passam pela Página Principal: `mob08_inicio`, `mob01_despesas`, `mobile_final_integrado` e `acesso`. Todas aprovadas.

## 4. Homologação no Firefox

Prévia em http://127.0.0.1:8790/__previa__/ com `usuario.g@teste.local` / `Senha-ficticia-G-2026`.

1. Na Página Principal, tocar no ícone de usuário ao lado do sino.
2. Escolher "Perfil G Empresa (fictício)", que é vazio, só para a troca.
3. Abrir qualquer módulo para conferir o perfil no subtítulo.
4. Voltar ao "Perfil G (fictício)" pelo mesmo menu.
