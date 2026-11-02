# FIN-CARTOES-CATEGORIAS-PUBLICACAO-01 — Publicação conjunta dos múltiplos cartões e da consolidação de categorias

**Situação (02/11/2026): preparada; aguarda autorização expressa do titular.** Nenhuma operação remota foi feita.

Pacotes: FIN-CARTOES-MULTIPLOS-01 (`docs/FIN_CARTOES_MULTIPLOS_01.md`) e FIN-CATEGORIAS-CONSOLIDACAO-01
(`docs/FIN_CATEGORIAS_CONSOLIDACAO_01.md`). Nesta etapa só código, estrutura do banco e frontend: sem limpeza de compras,
reimportação, pagamentos ou incorporação de categorias.

## 1. Verificação final (local)

| Item | Resultado |
|---|---|
| Commits locais | Os 15 commits dos dois pacotes (`f913a79`…`998ecf2`) e este documento, à frente de `origin/main` |
| Remoto | `refs/heads/main` = `3e09635`, ancestral do HEAD local (avanço direto) |
| Geradores | Os 7 geradores das migrations reproduzem os arquivos (`--verificar`: igual) |
| Hashes | 1213 `c103b399362b868ab787a740e87229ef`; 1214 `decd8a328435c373f58b97bacab62c5b` |
| Migrations versionadas | 55 (53 no remoto + 1213 + 1214) |
| Credenciais | Nenhuma no diff; só números de cartão fictícios de teste (recusados pelo próprio teste) |
| Não rastreados | Os 24 arquivos preservados, fora dos commits |
| E2E das 9 sistêmicas | Incluído (`migracao_p0p1.spec.mjs`, commit `4ca942d`) |
| Testes unitários do frontend | 59/59 |
| Regressão E2E completa | 120/120 (4,5 min). Os `ConnectionResetError` no log vêm do servidor local de teste quando o navegador cancela pedidos ao navegar; já apareciam nas execuções anteriores |

O frontend muda nesta publicação (pacote de múltiplos cartões): `web/src/paginas/cartoes.html`,
`web/src/js/cartoes-adaptador.js`, `web/src/js/importacao-pdf.js` e `web/src/js/importar-cartao-adaptador.js`.

## 2. Sequência (cada passo com autorização)

1. **GitHub:** push em avanço direto para `main`, sem force; conferir o HEAD remoto.
2. **Supabase:** aplicar só `20261213090000` e depois `20261214090000` (`aplicar_uma.py`), conferindo os hashes acima;
   esperado 55 aplicadas. Nenhum dado existente muda; nenhuma categoria é incorporada ou removida.
3. **Cloudflare Pages:** build limpo do HEAD publicado em `web/` (variáveis públicas do projeto; o build recusa chave
   secreta e procura segredos no `dist`) e deploy no projeto existente, ramo de produção, com `--commit-hash`. Conferir
   que os arquivos publicados são iguais aos do build. Sem DNS nem autenticação.
4. **Homologação só de leitura:** login e cabeçalhos de segurança; contratos Visa (388) e Black (387) existentes; nenhum
   cartão vinculado criado; compras, faturas, recorrências e previsões intactas; nenhuma categoria incorporada; Mobilidade
   com o mapeamento novo; tela de Cartões e prévia da importação compatíveis com as funções novas; saldos e movimentos
   bancários iguais. Sem importação real.

## 3. Depois da publicação (procedimentos separados)

1. Reconstrução de 11/2026: cartões vinculados → nova prévia da limpeza seletiva → limpeza com autorização →
   reimportação dos PDFs reais (Black R$ 9.599,80; Visa R$ 3.928,91, com todas as compras e parcelas, inclusive as do
   cartão físico cancelado) → conferência → pagamentos já realizados, verificando antes os movimentos bancários.
2. A recorrência SUPABASE SINGAPORE permanece no Black para as próximas cobranças.
3. Só depois: consolidação das categorias (96 → 8, 98 → 5, 4 → 5, 99 → 100 renomeada Assinaturas), com prévia, hash e
   autorização própria. Nunca entre a limpeza e a reimportação.
