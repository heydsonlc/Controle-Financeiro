# FIN-MVP-MOBILE-ICON-01 — Ícone da PWA: carteira do portal

**Situação:** implementado, validado localmente e publicado com autorização do contrato (seção 7).
**Escopo:** só o ícone da PWA e as referências a ele. Sem migration, sem `supabase/`, sem dados, sem mudança funcional.

## 1. Arquivo-base

O ícone de carteira do portal está em `kortex-site/sistemas/index.html`, no item "Controle Financeiro" da Central de
Sistemas (SVG 64×64). Foi copiado **sem alteração do desenho** para `web/scripts/icone-carteira-portal.svg`
(conferido linha a linha com o portal). As cores são as do portal: traço `#ecebe8` (`.system-item__icon`), dourado
`#c9a86a` e fundo `#0a0a0c` (`--color-bg`), que o fecho da carteira usa para cobrir o contorno; por isso o ícone tem o
fundo escuro do portal.

## 2. Geração

`web/scripts/gerar_icones_pwa.mjs` desenha o SVG no Chromium do Playwright (o mesmo motor que o exibe no portal) e
grava os PNG em `web/src/icones/` com os mesmos nomes e tamanhos de antes. Ele substitui `gerar_icones_pwa.py`, que
desenhava a marca do desktop. Uso, em `web/`: `node scripts/gerar_icones_pwa.mjs src/icones`.

| Arquivo | Tamanho | Uso |
|---|---|---|
| `apple-touch-icon.png` | 180×180 | iPhone (quadrado inteiro, opaco; o iOS arredonda os cantos) |
| `icone-192.png`, `icone-512.png` | 192, 512 | manifesto (`any`) |
| `icone-maskable-512.png` | 512 | manifesto (`maskable`, desenho dentro da zona segura de 80%) |
| `icone-32.png` | 32 | aba do navegador nas páginas mobile (cantos arredondados, transparente fora) |

## 3. Referências

As imagens são servidas com `Cache-Control: max-age=14400` (4 h no navegador); HTML e manifesto são revalidados a cada
acesso. Para o ícone novo não ser trocado pelo antigo guardado no aparelho, os endereços ganharam versão (`?v=2`) no
manifesto (4 ícones), no `apple-touch-icon` das 7 páginas mobile e do login e no ícone da aba das 7 páginas mobile.
Nada mais mudou no manifesto (nome `Controle Financeiro`, nome curto `Financeiro`, início, standalone, cores). O desktop
continua sem manifesto e sem ícone. Sem service worker.

## 4. Testes

- Unitários: 117/117 (teste da PWA atualizado: endereços com `?v=2` e PNG nos tamanhos declarados).
- E2E por impacto: `acesso`, `moldura`, `mob08_inicio`, `mobile_final_integrado`: 32/32.
- Build de produção (pasta separada, `config.js` idêntico ao servido) comparado com o publicado em 14/11/2026: mesma lista
  de 217 arquivos; diferem só os 5 PNG, as 8 linhas `apple-touch-icon`, as 7 linhas do ícone da aba e os 4 `src` do manifesto.
- Build servido localmente, sem login: login, Página Principal Mobile, Despesas mobile e desktop abrem (redirecionam ao
  login sem sessão); os 5 ícones respondem 200 `image/png` com o conteúdo do build; nenhum erro de console ligado aos
  ícones (os `ERR_CONNECTION_RESET` vistos vêm do servidor local de Python e aparecem igual com o build publicado).

## 5. Pendência para a consolidação com o MOBILE-08/09

A página `pagamentos-mobile.html` (MOBILE-08, ainda não publicada) nasceu com os endereços antigos; ao trazer este
commit para o ramo do MOBILE-08/09, ela recebe `?v=2` e o teste da PWA passa a incluí-la.

## 6. Homologação no iPhone

Remover o ícone atual da tela de início; abrir `https://financas.kortexbrasil.com` no Safari; Compartilhar → Adicionar à
Tela de Início; conferir a carteira.
