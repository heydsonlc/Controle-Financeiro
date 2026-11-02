# FIN-CARTOES-CATEGORIAS-PUBLICACAO-01 — Publicação conjunta dos múltiplos cartões e da consolidação de categorias

**Situação (02/11/2026): `FIN_CARTOES_CATEGORIAS_PUBLICACAO_01_PUBLICADO`.** Publicado em 02/11/2026 no FIN-CARTOES-CATEGORIAS-PUBLICACAO-01: push `3e09635..a1eebb1`, migrations `20261213090000` e `20261214090000` aplicadas e conferidas (53 → 55, nenhum dado existente alterado), deploy `8a8a63f7` (produção, commit `a1eebb1`, 165/165 arquivos iguais ao build). Homologação só de leitura (`docs/FIN_CARTOES_CATEGORIAS_PUBLICACAO_01.md`).

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

## 2. Sequência autorizada (executada em 02/11/2026)

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

## 4. Resultado da publicação

| Etapa | Resultado |
|---|---|
| Pré-condições (só leitura) | 53 migrations (última 1212); 1213 e 1214 não aplicadas; `cartao_vinculado` inexistente; as 6 funções substituídas iguais às versionadas, 10 novas |
| GitHub | `3e09635..a1eebb1` em avanço direto, sem force; HEAD remoto `a1eebb1`; 24 não rastreados preservados |
| 1213 | Dry-run só com ela; aplicada e registrada (54); tabela nova `financeiro.cartao_vinculado` com RLS e vazia; 7 funções novas, 4 alteradas, 0 removidas; dados existentes iguais (a única diferença de md5 é a coluna nova `cartao_vinculado_id`, nula) |
| 1214 | Dry-run só com ela; aplicada e registrada (55); 3 funções novas, 2 alteradas, 0 removidas; dados existentes iguais |
| Segurança do banco | Sem bloqueios: todas as tabelas com RLS, nada para `anon` nem `public`, nenhuma função definer sem `search_path` |
| Build e deploy | Build limpo do `git archive a1eebb1` (166 arquivos, projeto `fzjmge…`, sem chave secreta); deploy `8a8a63f7` no ramo `producao` com `--commit-hash a1eebb1`; 165/165 arquivos servidos iguais ao build (fora o `_headers`); `_headers` e `build.mjs` inalterados desde `3e09635`; CSP, X-Frame-Options DENY, nosniff e Referrer-Policy servidos; `http://` → 301 `https://` |

### 4.1 Homologação (só leitura, sessão readonly, como o titular)

- **Frontend × banco:** as 196 RPCs chamadas pelo build existem e são executáveis por `authenticated`; nenhuma por `anon`.
  `fatura_por_cartao` é interna (sem execução direta) e chega à tela dentro de `fatura_por_categoria` (`por_cartao`).
- **Contratos:** Black (387) e Visa (388) ativos; `cartoes_vinculados` vazio nos dois; nenhuma compra ou crédito com cartão.
- **Fatura consolidada (11/2026):** Black R$ 7.194,80 e Visa R$ 2.265,85, cada uma num só grupo "Sem cartão identificado";
  Despesas do mês com as mesmas faturas (previsto R$ 9.114,84 e R$ 2.767,75).
- **Prévia dos PDFs reais (nada confirmado):**
  - Black: 106 linhas (6830: 44, 6030: 53, sem final: 9) — 87 já existentes, 12 parceladas, 3 créditos, 2 compras, 1 a revisar, 1 ignorada; importável R$ 2.460,87;
  - Visa: 29 linhas (0548: 15, 7136: 11, sem final: 3) — 15 já existentes, 11 parceladas, 1 fixa, 1 crédito, 1 ignorada; importável R$ 1.663,09;
  - cada final aparece com o aviso "não cadastrado neste contrato", como esperado antes do cadastro.
- **Mobilidade:** 9 categorias sistêmicas (sem `MOB_REVISAO`); REVISAO, REVISAO_GERAL e REVISAO_PROGRAMADA → 5 Manutenção Veicular.
- **Catálogo:** 40 categorias, iguais às de antes (hash); nenhuma `incorporar_categoria` em `operacao_catalogo`; prévia da
  consolidação executável, sem bloqueios (hash do momento `13e7b735…`, que mudará com a reconstrução).
- **Integridade financeira:** as 82 tabelas de `public` e `financeiro` com dados iguais aos de antes (md5 sem a coluna nova);
  compras 157 (R$ 14.212,10), despesas 778, saldos bancários 96 R$ 68.015,34 e 97 R$ 12.469,48, 24 movimentos (último 172),
  financiamento R$ 269.524,62, faturas pagas inalteradas.

### 4.2 Observação

Desde o ensaio, a categoria 99 ganhou na produção as palavras "amazon music", "amazonprimebr", "brasil paral*bras" e
"google one" (já presentes no retrato anterior à publicação). A prévia as move para a 100 como as demais.
