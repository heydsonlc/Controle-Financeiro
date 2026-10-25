# FIN-PUBLICACAO-PREVIEW-2 — Prévia de avaliação publicada (Cloudflare Pages + Supabase de teste)

**Situação:** publicada e verificada em 24/10/2026, só como **prévia protegida**, com dados fictícios. Sem Flask, sem push e sem deploy de produção.

## 1. Publicação

| Item | Valor |
|---|---|
| Projeto Pages | `controle-financeiro` (exclusivo do Controle Financeiro; sem integração Git) |
| Método | Direct Upload: `npx wrangler pages deploy dist --project-name controle-financeiro --branch avaliacao`, rodado em `web/` |
| Branch de produção do projeto | `producao` (nunca usada). O endereço principal `controle-financeiro-jah.pages.dev` **não tem deploy** (404) |
| **Endereço da prévia** | **https://avaliacao.controle-financeiro-jah.pages.dev** |
| Endereço desta versão | https://14557b0c.controle-financeiro-jah.pages.dev |
| Versão do código | `c56e1fb`, publicada às 21:36 (24 arquivos) |
| Configuração pública | `SUPABASE_URL` do projeto de teste (`fzjmge…`) e a chave **publicável** (`sb_publishable_…`). Nenhuma chave secreta, `service_role`, senha nem conexão de banco no `dist` |
| Segurança das páginas (`_headers`) | CSP restrita (`connect-src` só o próprio site e o Supabase de teste, sem script inline, sem frames), `X-Frame-Options: DENY`, `nosniff` |
| Outros projetos da conta | `kortex-calculadora` e `kortex-site` (domínio `kortexbrasil.com`) **não foram alterados** |

## 2. Proteção de acesso

- **Configuração:** Cloudflare Access, ativado pelo titular no painel e sem custo, protege `*.controle-financeiro-jah.pages.dev`.
  - Aplicação: "controle-financeiro - Cloudflare Pages".
  - Política: "Allow Members", com Include **somente** a conta de e-mail do titular.
- **Verificado sem autenticação, antes e depois do envio:** o endereço da prévia, o desta versão, páginas internas e até o `config.js` respondem **302 para o login do Access**, sem nenhum conteúdo do aplicativo.
- **O endereço principal não é protegido por essa política.** Por isso não recebe deploy (404). Publicar sempre com `--branch avaliacao`, **nunca** com a branch `producao`.
- **Duas camadas:** depois do Access, o aplicativo ainda exige o login do Supabase. Os dados são protegidos pelas funções e permissões do banco.

## 3. Dados de demonstração (Supabase de teste)

**Script:** `scripts/supabase_demo_preview_seed.py`, que segue o padrão dos seeds de teste. O estado fica em `data/demo_preview_2.json`, fora do Git.

**Perfil:** "Demonstracao (ficticio)", vinculado **só** à conta de avaliação (TITULAR) e atribuído ao novo aplicativo. É o único vínculo do projeto.

**Dados** (marcador "(demonstracao)", 10/2026):
- 2 contas bancárias;
- 4 categorias;
- 1 cartão (fecha dia 3, vence dia 10) com 5 compras, uma delas parcelada em 6;
- 6 despesas e 4 receitas previstas;
- pagamentos (Aluguel, Condomínio) e recebimentos (Salário, parcial do Aluguel recebido);
- na verificação, mais um pagamento (Energia) e um recebimento (Freela).
- **Saldos:** conta corrente 10.941,53 e poupança 2.100,00, iguais aos movimentos.

**Preservação:** a comparação de md5 de antes e depois das tabelas financeiras, **fora do perfil de demonstração**, ficou idêntica (inclusive a fonte de receita preexistente, as 10 categorias e os 2 perfis existentes). Nenhum dado pessoal; o `gastos.db` não foi usado.

## 4. Verificações

| Verificação | Resultado |
|---|---|
| Visitante sem autorização (prévia, versão, páginas internas, `config.js`) | 302 para o Access, nenhum conteúdo |
| Build publicado (o mesmo `dist`) com login real da conta de avaliação no Supabase de teste | Aprovado |
| Telas: Contas (6 despesas, movimentos e saldos), Receitas (Recebida e Parcial), Cartões (fatura de 10/2026, 2 compras, "Pagar fatura") e Categorias (as 2 contas) | Aprovado |
| Operações: pagamento de despesa e recebimento de receita, com movimento e saldo conferidos e persistentes numa nova sessão | Aprovado |
| Sair e voltar a exigir login | Aprovado |
| Erros de JS ou CSP | Nenhum |
| Isolamento | A outra conta de teste vê 0 perfis e recebe 403 no perfil de demonstração; anônimo recebe 401 |
| Dependência de Flask | Nenhuma |

**O que só o titular pode fazer:** a verificação pelo **navegador do titular** (login do Access com código no e-mail, depois o login do aplicativo). O Access só libera o titular.

**Ressalva menor:** com as URLs sem `.html` do Pages, abrir uma página interna sem sessão leva para Contas depois do login, e não para a página pedida.

## 5. Como acessar

1. Abrir **https://avaliacao.controle-financeiro-jah.pages.dev**.
2. No Cloudflare Access, informar o e-mail autorizado e digitar o código recebido.
3. No aplicativo, entrar com a conta de avaliação (o mesmo e-mail) e a senha dela. A senha é a da conta de teste do Supabase, que o titular pode redefinir no painel do Supabase (Authentication → Users).

## 6. Atualizar a prévia

1. Em `web/`, gerar o `dist` com as variáveis públicas do projeto de teste (`npm run build`).
2. Conferir a ausência de segredos.
3. Rodar `npx wrangler pages deploy dist --project-name controle-financeiro --branch avaliacao`.

Cada envio cria uma versão nova no mesmo endereço `avaliacao.…`. Nunca usar `--branch producao` enquanto o endereço principal não estiver protegido.

## 7. Retirar a prévia

- **Aplicação:** apagar os deploys ou o projeto `controle-financeiro` no Pages (painel ou `wrangler pages project delete controle-financeiro`), e remover a aplicação do Access no Zero Trust.
- **Dados:** `scripts/supabase_demo_preview_seed.py --remover`, primeiro sem `--confirmar` (simulação) e depois com `--confirmar`. Remove só o perfil de demonstração e o que é dele, pelo estado salvo e pelo marcador.

**Cada etapa depende de autorização.**
