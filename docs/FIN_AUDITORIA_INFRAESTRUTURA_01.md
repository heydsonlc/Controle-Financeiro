# FIN-AUDITORIA-PUBLICACAO-MIGRACAO-01 — D. Infraestrutura (Supabase, Cloudflare, repositório)

**Data de referência:** 15/11/2026. **Natureza:** somente leitura. Nenhum dado, migration, função, configuração ou deploy foi alterado.

**Método**
- **Supabase de produção (`fzjmgekasjrgvmfdkdog`):** consultas SQL em sessão `readonly` (`transaction_read_only = on`), só de metadados e contagens.
- **Repositório:** as 67 migrations foram aplicadas num PostgreSQL descartável local (`tests/supabase_local.py`, `ClusterLocal.preparar`) para gerar a impressão digital de comparação.
- **Cloudflare:** `wrangler pages deployment list` e download dos arquivos servidos, comparados por SHA-256 com o build do commit publicado.

## 1. Repositório

| Item | Estado | Evidência |
|---|---|---|
| Ramo remoto `main` | `1ce28cb` | `git rev-parse origin/main` |
| Ramo local de trabalho | `mobile-10-perfis` em `3f480c4`, 1 commit à frente do remoto | `git log origin/main..HEAD` |
| Commit local não enviado | `3f480c4`, só documentação (registro da publicação do ícone da aba) | idem |
| Arquivos modificados | nenhum | `git status` |
| Arquivos não rastreados | 24: `apply_veic2b_sql.py`, 3 imagens `doc-hub-ux-*.png` e 20 imagens em `frontend/static/img/` | `git status` |
| Ramos locais antigos | cerca de 25 ramos de entregas já publicadas (`mob-*`, `mobile-0*`, `despesas-*`, `cartao-*` etc.); `main` local está 70+ commits atrás do remoto | `git branch -vv` |
| Rascunhos fora das migrations | `supabase/rascunhos/financiamentos_pagamento` e 16 scripts em `supabase/reversao/`; não são aplicados | `ls supabase` |

**Conclusão:** o GitHub e o que está publicado coincidem. Fora do GitHub existe apenas 1 commit de documentação e os 5 documentos desta auditoria.

## 2. Migrations (Etapa D)

| Medida | Valor | Evidência |
|---|---|---|
| Versionadas no repositório | **67** (`20261020120000` a `20261227090000`) | `ls supabase/migrations` |
| Aplicadas na produção | **67**, última `20261227090000` | `supabase_migrations.schema_migrations` |
| Só no repositório (pendentes) | **0** | comparação de versões |
| Só na produção | **0** | idem |
| Nome divergente | **0** | comparação `versão_nome` |
| Conteúdo divergente | **0** | impressão digital, abaixo |

**Impressão digital, repositório × produção**
- **Funções do schema `financeiro`:** 569 no banco gerado pelo repositório e 569 na produção. O `md5` de `pg_get_functiondef` é idêntico nas 569. Nenhuma existe só de um lado e nenhuma tem corpo diferente.
- **Colunas (`public` e `financeiro`):** 1.057 idênticas em nome e tipo. A produção tem 1 a mais, `public.alembic_version.version_num`, que é herança do Alembic do Flask (versão `c4f7a2d91b3e`) e não é usada pelo aplicativo novo.
- **Alterações fora do histórico:** nenhuma detectada em funções ou colunas.

As migrations de Documentos Fiscais citadas no contrato (`20261113090000`, `20261128090000`, `20261130090000`, `20261202090000`, `20261203090000`) **estão aplicadas** e idênticas ao repositório. Documentos antigos que as dão como pendentes estão desatualizados (ver seção 7).

## 3. Banco de produção: estrutura

| Item | Valor |
|---|---|
| Tabelas | `public` 54, `financeiro` 34; nenhuma view |
| RLS | ligada nas 88 tabelas; forçada nas 34 de `financeiro` |
| Políticas RLS | 2, só `SELECT` para `authenticated`: `financeiro.categorias` e `financeiro.perfil_acesso`. As demais tabelas não têm política, ou seja, ficam inacessíveis fora das funções |
| Privilégios de tabela | `anon`: nenhum. `authenticated`: só `SELECT` nas 2 tabelas acima. Nenhum `INSERT`, `UPDATE` ou `DELETE` direto |
| Funções | 569 em `financeiro`: 475 `SECURITY DEFINER`, todas com `search_path` fixo; 245 executáveis por `authenticated` (as RPCs) e 324 internas; 0 executáveis por `anon`; 0 para `PUBLIC` |
| Uso do schema `financeiro` | `authenticated` sim, `anon` não |
| Triggers | 7, em 6 tabelas: `cartao_vinculado`, `credito_fatura`, `gerador_recorrencia`, `pagamento_fatura`, `parcela_historica` (2) e `lancamento_agregado` |
| Storage | **nenhum bucket e nenhum objeto**; os documentos ficam no banco (seção 5) |
| Extensões | `pgcrypto`, `uuid-ossp`, `pg_stat_statements`, `supabase_vault`; sem `pg_cron` e sem `pg_net`, ou seja, não há tarefas agendadas no banco |
| Tamanho do banco | 25 MB |
| Usuários do Auth | 2 confirmados: 1 ativo (último acesso em 15/11/2026) e 1 banido (a conta B de testes) |
| Perfis | 2 ativos: `Pessoal` (padrão) e `Kortex` (Empresa), cada um com 1 titular gestor |

## 4. Escritor único (Etapa G, 10.4)

| Verificação | Resultado | Evidência |
|---|---|---|
| Gerador e escritor por perfil | Perfil 1 **NOVO** desde 29/10/2026; perfil 2 **NOVO** desde 30/10/2026 | `financeiro.gerador_recorrencia` |
| Catálogo de categorias | **NOVO** desde 30/10/2026 | `financeiro.catalogo_categorias` |
| Flask gravando na produção | Não. O Flask não está hospedado (o Render ficou só preparado, `render.yaml`), e o Flask local recusa escrita em perfil NOVO com 409 `SISTEMA_NOVO` | `backend/services/gerador_recorrencia_service.py:97` |

**Conclusão:** não há dois sistemas gravando os mesmos dados. A produção é escrita só pelo aplicativo novo.

## 5. Dados sensíveis e documentos (Etapa G, 10.2 e 10.3)

- **Cartões.** A tabela legada `public.config_agregador` ainda tem as colunas `numero_cartao`, `codigo_seguranca` e `data_validade`, que são do Flask. Na produção, por contagem e sem exibir valores:
  - 2 cartões;
  - `numero_cartao` com no máximo 4 dígitos nos 2;
  - `codigo_seguranca` vazio nos 2;
  - `data_validade` vazia nos 2.

  O aplicativo novo recusa gravar número completo, validade e CVV (`web/src/js/cartoes-servico.js:79`, `:330-331`). **Não há CVV nem número completo armazenado.**
- **Documentos.** Ficam em `public.ir_comprovante_arquivo.conteudo` (bytea). São 2 arquivos, 1,6 MB no total, ambos do perfil 2. A tabela tem RLS ligada e nenhum privilégio para `anon` ou `authenticated`. O acesso é só pela função `arquivo_comprovante_tela`, que confere o perfil.
- **Registros sem perfil.** Há 58 `item_despesa` do tipo `Consorcio`, inativos, com `perfil_financeiro_id` nulo. São resíduos históricos e não aparecem em nenhum perfil. As 36 linhas de `public.categoria` formam o catálogo global, sem perfil por desenho.

## 6. Cloudflare Pages (Etapa E)

| Item | Valor | Evidência |
|---|---|---|
| Projeto | `controle-financeiro`; domínios `financas.kortexbrasil.com` e `controle-financeiro-jah.pages.dev`; sem integração Git (deploy manual por `wrangler`) | `wrangler pages project list` |
| Deploy atual de produção | `45e24f88-ee0c-446d-856a-c37b384e8e47`, branch `producao`, origem `1ce28cb` | `wrangler pages deployment list` |
| Deploys anteriores | `dd64dcb6` (`b0b6a3b`), `c3dcada4` (`86110e2`), `1307bf18` (`9056a4a`); 25 no total | idem |
| Arquivos servidos × build | **225 de 225 idênticos** por SHA-256, no domínio oficial e no endereço Pages (HTML, JS, CSS, ícones, manifesto, `favicon.ico`, `config.js`) | build de `1ce28cb` comparado por download |
| `config.js` | só valores públicos: URL do projeto e chave publicável `sb_publishable_…` | arquivo servido |
| Cabeçalhos de segurança | CSP `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self' https://fzjmgekasjrgvmfdkdog.supabase.co; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'`; `X-Frame-Options: DENY`; `X-Content-Type-Options: nosniff`; `Referrer-Policy: same-origin`; `Permissions-Policy` | `curl -I` |
| Rotas protegidas | sem sessão, `inicio.html`, `pagamentos-mobile.html`, `recorrencias-mobile.html`, `despesas-mobile.html` e `recorrencias.html` redirecionam para o login | navegador sem login, 15/11/2026 |
| Páginas no build | 16 do desktop (moldura), login, Página Principal mobile e 8 módulos mobile; `em-migracao.json` vazio, ou seja, nenhuma página "em migração" | `web/scripts/build.mjs`, `web/src/moldura/em-migracao.json` |
| Backend no Cloudflare | não existe e não é necessário: o site é estático e toda operação é RPC do Supabase; nenhum `fetch` externo | `web/src/js/ponte-api.js:20-24` |
| Service worker | não existe; o PWA tem só manifesto e ícones | teste `pwa:` em `web/tests/unit/build.test.mjs` |

**Observação.** O painel da Cloudflare injeta o script de estatísticas `cloudflareinsights`, que a CSP bloqueia. Isso gera um aviso de console em toda página, sem efeito funcional. O ajuste é desligar o Web Analytics no painel ou liberar o domínio na CSP.

**Dependência de código do Flask no build.** O build copia 20 scripts de `frontend/static/js/` e os CSS de `frontend/static/css/` para o `dist` (`web/scripts/build.mjs:29-33, 278-283`). É uma dependência de **código-fonte**, não de serviço: as telas do desktop continuam sendo as originais do Flask, respondidas pelos adaptadores.

## 7. Divergências documentais

| Documento | Divergência | Situação real |
|---|---|---|
| `docs/ROADMAP.md:12` (trilha "ordem oficial") | Ainda aponta "criação do staging no Render", `BACKUP-DOCS-1`, `CLOUDFLARE-1` | A arquitetura vigente é Cloudflare Pages + Supabase, em produção desde 30/10/2026 |
| `docs/ROADMAP.md:54, 258` | `FIN-DOC-FIN-4` e `BACKUP-DOCS-1` falam de documentos em disco | Os documentos fiscais ficam no banco; só os documentos de financiamento ficavam em disco no Flask, e eles não foram migrados |
| `docs/FIN_BLOCO_D_1.md`, `FIN_PRE_PRODUCAO_1.md` | "37 migrations + 5 pendentes" | 67 aplicadas, 0 pendentes |
| `docs/FIN_MVP_MOBILE_08_PAGAMENTOS.md` (pendência 1) | Ocorrência cancelada no agrupador | Já corrigido no próprio documento: improcedente |
| `web/src/js/arquivo-comprovante.js:67-68` (comentário) | Fala em relatório "do sistema atual" | Não há sistema Flask em produção para gerar o relatório |

## 8. Backup e recuperação (Etapa H)

| # | Verificação | Resultado |
|---|---|---|
| 1 | Rotina de backup | Existe a ferramenta `scripts/backup_banco.py` (exportar, verificar, restaurar), que é uma CLI manual. **Não há rotina automática.** A tela de backup do Flask (`backend/routes/backup.py`) não foi migrada e não se aplica ao Supabase |
| 2 | Frequência e último backup comprovado | **NÃO COMPROVADO.** `docs/FIN_BLOCO_D_2.md:37` registra "o backup não foi gerado" e `docs/FIN_BLOCO_D_3.md:13` registra a decisão do titular: "sem backup independente. Os backups gerenciados do Supabase não foram mexidos". Não encontrei manifesto de backup em disco |
| 3 | Abrangência | A ferramenta cobre `public`, `financeiro`, `supabase_migrations`, `auth.users` e `auth.identities` (`backup_banco.py:34-40`) |
| 4 | Documentos | Incluídos: estão no banco, e a ferramenta gera um arquivo separado de `ir_comprovante_arquivo` (`:36, 225-226`) |
| 5 | Metadados para restauração | Manifesto com SHA-256 e "retrato" do banco: linhas e md5 por tabela, funções, políticas, privilégios e migrations |
| 6 | Criptografia e local seguro | **NÃO COMPROVADO.** Nenhum local atendeu ao requisito de criptografia comprovada (`FIN_BLOCO_D_2.md:25-37`) |
| 7 | Procedimento de recuperação | Documentado e automatizado: restauração só em banco vazio, com homologação por retrato |
| 8 | Teste de restauração | Só com dados fictícios, em banco descartável (`tests/test_backup_banco.py`; ensaio do Bloco D). **Nenhum teste com backup real** |
| 9 | Dependências externas | Os backups gerenciados do Supabase dependem do plano do projeto, que **não é verificável por SQL nesta auditoria**. É preciso conferir no painel: Database → Backups |
| 10 | Recuperação sem perda | **NÃO COMPROVADO** enquanto não houver um backup real e um teste de restauração dele |

**Classificação:** NÃO COMPROVADO, prioridade **P1** (ausência de estratégia comprovada de recuperação). É o principal risco identificado.
