# FIN-MVP-MOB-08: página principal mobile

Primeiro MVP da versão mobile: área de trabalho simplificada, com atalhos para os módulos. Os 8 atalhos ficam visíveis e desabilitados até cada módulo mobile ser homologado. O desktop não muda.

**Situação:** implementado no ramo local `mob-08-inicio`. Layout aprovado com ressalvas na homologação de 13/11/2026, e os ajustes foram feitos (botões mais baixos, menos espaço abaixo da competência, Sair no Mais). Publicação só depois da aprovação final do titular.

## 1. O que foi feito

| Arquivo | Mudança |
|---|---|
| `web/src/inicio.html` | página nova, fora da moldura do desktop (como o login): cabeçalho, competência, grade 2×4 e barra inferior |
| `web/src/css/inicio-mobile.css` | folha própria, carregada só por `inicio.html`, com todas as regras restritas a `body.mob-inicio` |
| `web/src/js/inicio-mobile.js` | sessão (`exigirUsuario`), competência e atalhos; `MODULOS_ATIVOS` vazio; não lê nem grava dados |
| `web/src/js/sessao.js` | `inicio.html` entre as páginas permitidas; no celular (largura até 767 px), o destino padrão após o login é `inicio.html` |

**Não muda:**
- desktop, moldura, CSS compartilhado e regras de negócio;
- banco, migrations e dados;
- CSP do deploy.

**Comportamento:**
- **Celular** (até 767 px): o login leva a `inicio.html`. Um destino pedido (`?next=`, ou acesso direto a uma página) continua valendo.
- **Tablet e desktop:** o login segue levando a Despesas (`contas.html`), com a moldura de sempre.
- **Sem sessão:** `inicio.html` leva ao login e volta para ela depois.
- **Competência:** mês e ano correntes no formato do mockup (`Nov/2026`). As setas trocam o mês só na interface; o mês fica no endereço (`?mes=`), então atualizar a página o mantém. Mês inválido volta ao corrente.
- **Atalhos e barra:** os 8 atalhos e os itens Lançar e Resumo ficam com a aparência original, desabilitados (`aria-disabled`, sem link, "Em breve" no título) e não navegam. O sino não tem função.
- **Início:** destacado em preto; recarrega a página principal mantendo o mês escolhido.
- **Mais:** abre um menu com **Sair**, que encerra a sessão (aprovado na homologação de 13/11/2026). O menu fecha com Esc, com toque fora ou com a escolha.
- **Ativação gradual:** cada MVP homologado entra em `MODULOS_ATIVOS` pelo `data-modulo`. O atalho passa a apontar para o seu `data-destino` com a competência aberta.
- **FIN-MVP-MOB-01 (Lista de Despesas mobile):** o Resumo (atalho e barra) ficou habilitado e abre `despesas-mobile.html`. A estrutura comum das páginas mobile passou para `css/mobile-base.css` e `js/mobile-comum.js`, sem mudar o layout (capturas idênticas pixel a pixel). Ver `docs/FIN_MVP_MOB_01_LISTA_DESPESAS.md`.

## 2. Mockup e divergências para decisão do titular

O layout segue as medidas do mockup aprovado:
- tela de 390 pt e margens de 17 pt;
- competência em pílula de 46 pt, com calendário;
- botões de 92 pt, espaço de 10 a 11 pt entre eles e cantos de 14 pt; na homologação, reduzidos para 80 px, com ícones de 32 px;
- ícones de 34 pt e nomes em semi-negrito;
- espaço entre a competência e a grade reduzido de 20 para 12 px na homologação;
- título grande, com linha divisória;
- barra inferior com a casa preenchida no item ativo.

O azul do mockup foi trocado pelo preto do menu lateral do desktop (`#1d1d1f`).

| Ponto | Mockup | Implementado (tabela do contrato) |
|---|---|---|
| Nomes | "Nova Receita", "Nova Despesa", "Registrar Lançamento", "Resumo Despesas" | "Receita", "Despesa", "Lançamento", "Resumo" |
| 3ª linha | Cartões (cartão), Pagamentos (setas circulares) | Pagamentos (cartão), Recorrências (setas circulares) |
| 4ª linha | Contas (instituição), Recorrências (calendário) | Cartões (cartão de crédito), Contas (instituição) |
| Ícone do cabeçalho | barras, em quadro claro | ícone da aplicação do desktop (quadro preto) |

As quatro trocas são simples: só o HTML e o teste.

## 3. Ambiente de pré-visualização (adendo de 13/11/2026)

Serve para amadurecer o layout no computador, com dados fictícios, antes de qualquer publicação.

```
set POSTGREST_BIN=C:\Users\heyds\AppData\Local\cf-e2e\postgrest\postgrest.exe
venv\Scripts\python.exe web\tests\e2e\run_e2e.py --previa
```

Abrir no Firefox: `http://127.0.0.1:8790/__previa__/`. Conta fictícia: `usuario.a@teste.local` / `Senha-ficticia-A-2026`, que só existe nesse ambiente.

- **Ambiente:** o mesmo dos testes E2E, com banco descartável, usuários fictícios e os cabeçalhos reais do `_headers`. Nada é publicado e nenhum dado real é tocado.
- **Página `/__previa__/`** (arquivos em `web/previa/`, fora do `dist` e do deploy):
  - mostra a mesma página lado a lado em tamanhos à escolha: 320×568, 360×740, 375×667, 390×844, 412×915, 430×932, tablet 820×1180 e desktop 1366×900;
  - tem zoom;
  - a página `index.html` abre a página inicial de cada aparelho (celular no início mobile, desktop em Despesas), o que permite comparar celular e desktop;
  - o login num quadro vale para todos.
- **Botão Recompilar e recarregar:** depois de ajustar fontes, ícones, botões ou espaçamentos em `web/src`, recompila o `dist` e recarrega os quadros.
- **Restrição de quadros:** só nesse modo e só nesse servidor local, as páginas podem ser emolduradas pela própria origem (`frame-ancestors 'self'`). O `_headers` do deploy continua com `frame-ancestors 'none'` e `X-Frame-Options: DENY`.
- **Alternativa no Firefox:** o Modo de Design Responsivo (Ctrl+Shift+M) também funciona direto em `http://127.0.0.1:8790/inicio.html`.

**Fluxo de homologação de cada MVP mobile:** implementação no ramo → ajustes na pré-visualização → aprovação do titular → publicação, com autorização própria.

## 4. Testes por impacto

| Nível | Selecionados | Resultado |
|---|---|---|
| Unitários (`web`) | todos, com um teste novo (incluindo o menu Sair): página protegida, fora da moldura, 8 atalhos desabilitados, só Início com link, CSS restrito a `body.mob-inicio`, nenhuma leitura de dados, pré-visualização fora do `dist` | 93/93 |
| E2E (ambiente isolado) | `mob08_inicio` (8: sem sessão, celular com botões de 80 px e espaço de 12 px, competência e Início mantendo o mês, Mais e Sair, larguras de 320 a 430 sem rolagem horizontal nem corte, destino pedido, tablet, desktop) e a regressão afetada pelo novo destino no celular: `acesso`, `moldura`, `contas`, `movimentacoes`, `pendencia` | 40/40; depois dos ajustes, `mob08_inicio` + `acesso` + `moldura`: 25/25 |

Ajuste nos specs existentes: `moldura`, `contas`, `movimentacoes` e `pendencia` entravam pelo login com viewport de celular e esperavam Despesas. Agora pedem esse destino explicitamente (`?next=contas.html`), porque no celular o login leva à página mobile, como pede o contrato. Nenhuma asserção de comportamento do desktop mudou.

Dispensados: testes de banco e a regressão financeira completa, porque não há mudança de dados, funções ou migrations.

## 5. Pendências

- Decidir as divergências da seção 2.
- Homologação visual do titular no Firefox, pela pré-visualização.
- Publicação (push e deploy) só depois da aprovação.
