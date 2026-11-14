# FIN-MVP-MOBILE-FINAL-01: consolidação, PWA e preparação para produção

Última etapa da primeira versão mobile. Ela consolida os sete MVPs homologados em 14/11/2026, valida a integração com o desktop, configura a instalação no iPhone (PWA) e prepara a publicação conjunta.

**Situação:** executado no ramo local `mobile-final-01`. Não houve push, deploy nem migration, e nenhum dado real foi alterado. A publicação depende da autorização expressa do titular.

## 1. Consolidação dos sete MVPs

**Histórico.** Os MVPs foram feitos em ramos encadeados, cada um a partir do anterior. O ramo de consolidação parte do último (`mobile-07-contas-movimentacoes`) e por isso contém todos:

| MVP | Módulo | Commits (ramo de origem) |
|---|---|---|
| FIN-MVP-MOBILE-01 | Página Principal | `792490f`, `65bada2` (`mob-08-pagina-principal`, depois MOB-01) |
| FIN-MVP-MOBILE-02 | Lista de Despesas | `72beea6`, `57bfb59` |
| FIN-MVP-MOBILE-03 | Cartões | `544fc20`, `b6257dd`, `e887f62` (`mobile-03-cartoes`) |
| FIN-MVP-MOBILE-04 | Receitas | `eb87248`, `d7bda9f` (`mobile-04-receitas`) |
| FIN-MVP-MOBILE-05 | Cadastro de Despesas | `b3cdee5`, `0dddcb3`, `2060f3b`, `36ca987`, `421e1bb`, `46fa74a`, `ecb9080` (`mobile-05-cadastro-despesas`) |
| FIN-MVP-MOBILE-06 | Registrar Lançamento | `7f29405`, `ba555a5`, `0a969a6`, `345e012` (`mobile-06-registrar-lancamento`) |
| FIN-MVP-MOBILE-07 | Contas e Movimentações | `019c01e`, `ee5d363`, `36d955e`, `ea354ee` (`mobile-07-contas-movimentacoes`) |

**Em relação à versão publicada:**
- O `origin/main` (`7e035c5`, a versão do deploy de produção `5d608ca5`) é **ancestral** do ramo consolidado. A publicação é um **avanço rápido**, sem merge nem conflito.
- O ramo tem 29 commits a mais: 2 de documentação que ainda estavam só locais (`434fd07` saneamento e `925e9df` domínio próprio), 24 dos MVPs mobile e 3 desta etapa (`5832de9`, `4a1432e`, `940575d`).
- **Sem migration:** nenhum arquivo em `supabase/` mudou. Nenhuma função, tabela ou política do banco é alterada pela publicação.
- O `main` local está atrás do `origin/main` (`0de5820`): é só uma referência local desatualizada, sem efeito.

**Arquivos em relação ao publicado (antes desta etapa):** 80 (63 novos, 17 alterados), com 13.959 linhas incluídas e 1.381 removidas.

Os alterados de código do desktop:
- `cartoes-adaptador.js`, `despesas-adaptador.js`, `receitas-adaptador.js`, `lancamentos-adaptador.js` e `contas-bancarias-adaptador.js`: passam a chamar os serviços comuns extraídos;
- `perfil.js`: só a leitura da permissão;
- `sessao.js`: só a lista das páginas permitidas.

Os demais alterados são testes, o cenário fictício, o roteiro da homologação real e a documentação. Esta etapa acrescenta o manifesto, os ícones, os metadados das páginas mobile e do login, o gerador dos ícones e os testes.

**Serviços compartilhados, conferidos sem mudança de comportamento no desktop.** Cada extração manteve a tela do desktop chamando a mesma função do banco, com a mesma validação e a mesma chave contra reenvio:

| Serviço | Extraído de | Funções do banco | Desktop que usa |
|---|---|---|---|
| `despesas-servico.js` | `despesas-adaptador.js` (MOBILE-02) | `criar_despesa`, `pagar_despesa`, `estornar_pagamento_despesa`, `pagar_fatura`, … | Despesas |
| `cartoes-servico.js` | `cartoes-adaptador.js` (MOBILE-03) | compras, faturas, cartões | Cartões |
| `receitas-servico.js` | `receitas-adaptador.js` (MOBILE-04) | `criar_receita`, `receber_receita`, estorno | Receitas |
| `compras-servico.js` | `lancamentos-adaptador.js` (MOBILE-05) | `criar_compra`, `previa_compra`, `sugerir_competencia` | Lançamentos |
| `abastecimento-servico.js` | `lancamentos-adaptador.js` (MOBILE-06) | `salvar_lancamento_abastecimento` | Lançamentos |
| `contas-servico.js` | `contas-bancarias-adaptador.js` (MOBILE-06/07) | `transferir_entre_contas`, `extrato_conta_bancaria`, `conferir_saldo_conta` | Contas Bancárias |
| `despesas-grupos.js`, `receitas-lista.js` | regras de leitura do desktop (MOBILE-02/04) | — (puras, testadas contra o JS original numa VM) | — |

**Provas:**
- o teste unitário `build.test.mjs` confere, função por função, que cada gravação só existe no serviço comum (`RPCS_DE_ESCRITA`) e que as páginas mobile não consultam o banco diretamente;
- a regressão completa do desktop (seção 5) passou nas telas que agora chamam os serviços comuns.

**Componentes mobile compartilhados:**
- `mobile-comum.js`: competência, atalhos, Mais/Sair e permissão;
- `mobile-ui.js`: painel inferior, campos e mensagens;
- `mobile-formulario.js`, `mobile-cartao.js`, `despesa-formulario.js` e `receita-formulario.js`: formulários únicos;
- `mobile-base.css` e `mobile-modulo.css`.

**Arquivos preservados:** os 24 não rastreados continuam intactos. Nenhum comando de limpeza, exclusão ou sobrescrita foi usado; os arquivos entraram nos commits um a um.

## 2. Configuração PWA (iPhone)

| Item | Configuração |
|---|---|
| Manifesto (`manifest.webmanifest`) | Nome "Controle Financeiro", nome curto "Financeiro", `start_url` `inicio.html` (Página Principal Mobile), `scope` `./`, `display` `standalone`, `orientation` `portrait`, `theme_color` `#1d1d1f` (o preto da identidade), `background_color` `#ffffff`, idioma `pt-BR` |
| Ícones (`icones/`) | `apple-touch-icon.png` (180×180, tela de início do iOS, sem transparência; o iOS arredonda os cantos), `icone-192.png`, `icone-512.png`, `icone-maskable-512.png` (símbolo dentro da zona segura) e `icone-32.png` |
| Desenho do ícone | A marca do próprio desktop (o quadrado preto com o símbolo de livro-caixa do menu lateral), sobre fundo branco, com o símbolo ampliado para ser legível em tamanho pequeno. O logotipo do desktop **não foi substituído**. Gerado por `web/scripts/gerar_icones_pwa.py`, reproduzível |
| Metadados iOS (7 páginas mobile) | `manifest`, `icon` 32, `apple-touch-icon`, `apple-mobile-web-app-capable` e `mobile-web-app-capable` (abrir sem a barra do Safari), `apple-mobile-web-app-title` "Financeiro", `apple-mobile-web-app-status-bar-style` `default` (barra clara, como o cabeçalho branco aprovado). A viewport já tinha `viewport-fit=cover`, e o CSS base já respeita as áreas seguras (`env(safe-area-inset-*)` no cabeçalho, no conteúdo e na barra inferior) |
| Login (`index.html`) | Só manifesto, ícone do iPhone e os metadados de modo independente, para "Adicionar à Tela de Início" a partir do login. A aparência do login no desktop não muda (sem favicon novo, sem cor de tema) |
| Desktop | Nenhuma tela do desktop recebe manifesto ou metadados: o desktop não muda |
| Service worker | **Não há.** Não foi necessário, porque o iOS instala na tela de início sem service worker. Assim nenhuma resposta, página ou dado financeiro fica em cache persistente, e não há versão antiga presa no aparelho |
| Atualização | Sem service worker, cada abertura busca as páginas na rede. O Cloudflare Pages serve com revalidação (`max-age=0, must-revalidate`), então a versão nova vale na próxima abertura |
| Sem conexão | A aplicação exige internet nesta versão. Sem conexão, o iPhone mostra a mensagem padrão de falta de rede; nada financeiro é guardado ou enfileirado |
| CSP | Inalterada: manifesto e ícones são do próprio site (`default-src 'self'`, `img-src 'self' data:`) |

**Abertura do app instalado:**
1. Abre `inicio.html`, a interface mobile.
2. Sem sessão válida, `exigirUsuario()` (o mesmo controle de sempre, validado no Supabase Auth) leva ao login com `?next=inicio.html`.
3. Depois de entrar, volta à Página Principal Mobile.
4. A navegação entre os módulos são links internos do mesmo escopo, então continua no modo independente.
5. "Mais → Sair" encerra a sessão e volta ao login.

O mesmo domínio no desktop continua como está, porque o desktop não carrega o manifesto.

**Servidor local da prévia:** passou a servir `.webmanifest` e `.png` com o tipo certo, como o Cloudflare Pages já faz.

## 3. Segurança

| Item | Verificação |
|---|---|
| Autenticação | Sem mudança: Supabase Auth, sessão validada no servidor (`auth.getUser()`) antes de mostrar qualquer página protegida (`data-protegido hidden`). PWA e navegador usam o mesmo mecanismo; nenhum mecanismo paralelo |
| Autorização por perfil | Toda leitura e gravação passa pelas funções do banco, que conferem `pode_acessar_perfil` / `pode_gerir_perfil` e o escritor único. O estado dos botões é só apresentação: o cenário integrado 7 mostra o banco recusando o pagamento do leitor H com os botões escondidos |
| Encerramento de sessão | "Mais → Sair" encerra a sessão; depois disso, o acesso direto a `inicio.html`, `contas-mobile.html`, `lancamento-mobile.html` e `despesas-mobile.html` volta ao login (cenário 7) |
| Rotas diretas | Páginas mobile protegidas; destino após o login só da lista fixa (`PAGINAS_PERMITIDAS`), nunca uma URL qualquer (sem redirecionamento aberto) |
| Gravações duplicadas | Chave de idempotência por operação em todas as funções de gravação, mais o botão travado no primeiro toque. Os testes usam toque duplo e conferem um registro só |
| Dados no aparelho | Só a sessão do Supabase (`cf-financeiro-auth`) e o número do perfil ativo (`localStorage`). Nenhum dado financeiro, nenhum cache (sem service worker, Cache API ou IndexedDB; conferido no teste unitário) |
| Cartões | Só o final de 4 dígitos do cartão físico; nunca número completo nem CVV |
| Cabeçalhos | CSP sem `unsafe-inline`, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: same-origin`, `Permissions-Policy` sem câmera, microfone ou localização. Inalterados |
| Segredos | O build só embute a URL e a chave publicável do Supabase; `verificarDist` recusa chaves reais no `dist` |
| Integridade financeira | Saldo só do banco (nenhum cálculo de saldo no navegador); estornos e cancelamentos só pelos módulos de origem; nenhuma regra nova |

## 4. Testes integrados dos sete módulos

`web/tests/e2e/mobile_final_integrado.spec.mjs`, com o usuário G (escrita) e o H (leitura). Os cadastros são em 05/2033; pagamentos e recebimentos usam a data de hoje e são conferidos na tela Contas. Saldos, extratos e conferência vêm das funções do desktop.

**7/7 cenários aprovados** (também dentro da suíte completa):

| Cenário | Caminho percorrido | Conferências |
|---|---|---|
| 1. Despesa | Nova Despesa → Lista de Despesas → Pagar (toque duplo) → Contas | Uma conta pendente, depois paga com **um** pagamento; movimento "Pagamento de despesa" − R$ 271,37 em Contas, com a despesa no detalhe; saldo = anterior − 271,37 = banco; conferência consistente |
| 2. Receita | Registrar Lançamento (Receita) → Receitas → Receber → Contas | Nasce prevista (saldo inalterado); recebida uma vez; crédito "Recebimento" + R$ 432,10; saldo atualizado e consistente |
| 3. Cartão | Registrar Lançamento (Compra no cartão) → Cartões → Pagar fatura → Lista de Despesas → Contas | Compra na fatura 05/2033 sugerida pelo fechamento; fatura paga uma vez; na Lista **só a fatura** (R$ 345,60), nenhuma conta com o nome da compra; débito "Pagamento de fatura" em Contas; saldo consistente |
| 4. Transferência | Contas (⇄) → Registrar Lançamento → "Ver em Contas" → "Ver a outra conta" | Débito na origem e crédito no destino, saldos −/+ R$ 55,55; os dois movimentos com o mesmo `transferencia_id`; a outra conta no detalhe |
| 5. Abastecimento | Registrar Lançamento (Abastecimento) → Lista de Despesas (Pagar) → Contas | Abastecimento vinculado ao veículo e a **uma** conta a pagar (Combustível, R$ 125,00, 20,000 L de gasolina a R$ 6,25, litros do banco); paga pela Lista; débito e saldo em Contas |
| 6. Estornos | Lista (despesa), Receitas (recebimento), Cartões (fatura) → Contas | Despesa volta a Pendente; receita volta a prevista; fatura reaberta (a compra continua nela); três estornos em Contas, cada um com o movimento original; saldo final = anterior + 271,37 − 432,10 + 345,60, consistente |
| 7. Permissões | Leitor H em todos os módulos; Sair; endereço direto; atualizar e trocar o mês | H sem atalhos de cadastro, sem Pagar/Estornar/Editar, sem "+", sem pagar fatura, sem Transferir; **o banco recusa** o pagamento do H; atualizar mantém conta e competência; depois de Sair, as páginas mobile voltam ao login, inclusive pelo endereço direto |

## 5. Regressão completa e as três falhas conhecidas

**Unitários:** 117/117. O teste novo da PWA confere o manifesto, as dimensões dos ícones, os metadados nas páginas mobile e no login, o desktop sem manifesto, a ausência de service worker e de cache, e a CSP inalterada.

**Testes de navegador, suíte completa, nas mesmas condições:**

| Código | Arquivos | Aprovados | Reprovados | Não rodaram |
|---|---|---|---|---|
| Publicado (`7e035c5`, referência) | 44 | 157 | 1 | 0 |
| Consolidado (`mobile-final-01`) | 52 | 223 | 1 | 0 |

A única reprovação, **nos dois**, é `recorrencia.spec:262`. **Nenhuma falha foi introduzida pela versão mobile.** As telas do desktop que passaram a gravar pelos serviços comuns (Despesas, Cartões, Receitas, Lançamentos e Contas Bancárias) passaram inteiras.

**As três falhas conhecidas: o que eram.** A investigação desta etapa reproduziu cada uma no código publicado e encontrou duas causas, **ambas dos testes, nenhuma do aplicativo**:

1. **`recorrencias_inativacao:85` e `recorrencias_tela:115`, e as variações que mudavam de lugar** (nesta etapa apareceram também em `lancamentos_tela`, `recorrencia:141/160` e `financiamentos_motor`). Causa: defeito do **ambiente de teste**.
   - O cenário fictício (`semear_contas`) grava contas com **ids fixos** (501 a 512) e não avança a sequência.
   - Na suíte inteira, quando a sequência alcançava esses ids, a gravação seguinte falhava com "chave duplicada" (`conta_pkey`), no teste que estivesse gravando naquele momento.
   - Isolados, esses testes sempre passaram, no publicado e no consolidado.
   - O diagnóstico (provisório, fora do repositório) mostrou a sequência em 504, as contas 501 a 512 do cenário e as tentativas de `gerar_mes` recusadas nos ids 506 a 512. Elas passaram na 513.
   - **Correção (só no executor dos testes, `run_e2e.py`):** depois de gravar o cenário, cada sequência passa ao maior id já gravado (`alinhar_sequencias`). Com ela, as duas passam nos dois códigos.
2. **`recorrencia.spec:262`: teste desatualizado desde a P22** (FIN-RECORRENCIAS-INATIVACAO-01, publicada em 09/11/2026).
   - Desde então, "Excluir esta e as futuras" abre a prévia da interrupção, pede confirmação e termina com "Recorrência interrompida: N ocorrência(s)…".
   - O teste antigo espera a mensagem do Flask e não confirma a prévia; a mensagem que ele lê é a do passo anterior ("apenas esta").
   - O fluxo da P22 tem cobertura própria, que passa (`recorrencias_inativacao`: "Excluir esta e as futuras" em Despesas, com confirmação e a mensagem nova).

**Decisão técnica sobre a criticidade:**

| Falha | Risco para as operações financeiras | Decisão |
|---|---|---|
| Colisão de ids no ambiente de teste | Nenhum. Só acontece no banco descartável, porque o cenário grava ids fixos. Em produção as funções sempre usam a sequência, e o cenário remoto usa `ids_fixos=False`. Mesmo se acontecesse, a gravação é atômica (nada pela metade) e a tela avisa ("Recarregue a página para tentar de novo") | **Não bloqueadora.** Corrigida no executor dos testes |
| `recorrencia.spec:262` desatualizado | Nenhum. A interrupção de recorrência (P22) está coberta e funciona; sem duplicidade, sem divergência de saldo, sem obrigação gerada a mais | **Não bloqueadora.** **Proposta (aguarda autorização):** atualizar o trecho final do teste para o fluxo da P22 (confirmar a prévia e esperar "Recorrência interrompida"), sem mudar o aplicativo |

**Correções de testes desta etapa** (nenhuma do aplicativo):
- `mobile06_registrar_lancamento`: nome próprio "Fibra G (lancamento)". O nome antigo, "Internet G", coincidia com a recorrência do spec do MOBILE-05, gerada quando outro spec abria um mês posterior. Os hodômetros do abastecimento passaram a partir da última leitura do veículo.
- `mobile_final_integrado`: o mesmo cuidado com o hodômetro.

Eram colisões de dados entre specs, sem duplicidade real.

**Não executado:** a bateria de banco em Python (`pytest`). Esta versão não tem migration nem mudança em função ou tabela, e a bateria completa ocupa ~30 GB de temporários. Ela foi dispensada pela política de testes por impacto (N4).

## 6. Responsividade

- **Larguras:** 320, 375, 390 e 430 px testadas em cada módulo: sem rolagem horizontal, sem campos cortados nem sobrepostos, barra inferior sem cobrir o conteúdo.
- **Tablet e desktop:** a partir de 768 px, o login leva ao desktop (`contas.html`), como antes (`mob08_inicio`). As telas do desktop, em 1366 e 1920, estão cobertas pela regressão.
- **Áreas seguras do iPhone:** recorte superior e região inferior tratados no CSS base desde o MOBILE-01 (`env(safe-area-inset-top/bottom)` no cabeçalho, no conteúdo e na barra), com `viewport-fit=cover`.
- **Teclado virtual:** os campos usam `inputmode` e os tipos nativos (data, mês, número), e os formulários rolam dentro da página.
- **Componentes:** nenhuma altura aumentada nesta etapa; nada visual mudou nos módulos homologados.

## 7. Pendências classificadas

| # | Pendência | Análise | Classificação |
|---|---|---|---|
| 1 | Três falhas dos testes de recorrência | Ver a seção 5. As três se reproduzem no código publicado (`7e035c5`), na suíte completa, com as mesmas mensagens. Nenhuma foi introduzida pelo mobile. Duas eram colisão de ids do ambiente de teste (corrigida no executor); a terceira é um teste desatualizado desde a P22, com o fluxo coberto por outro teste. Nenhuma oferece risco às operações financeiras | **Não bloqueadora** (decisão técnica na seção 5) |
| 2 | Totalização diferente entre Receitas, Despesas e Dashboard | O "total de receitas" da tela Despesas e do Dashboard (`receitas_totais_do_mes`) conta, por exemplo, o recebido acima do previsto; a tela Receitas mostra Previsto e Recebido das linhas. O mobile segue cada tela do desktop (Receitas como Receitas, Despesas como Despesas), sem cálculo próprio. Afeta só a apresentação dos totais, nunca saldo, pagamento ou geração | **Não bloqueadora** (comportamento do desktop, conhecido); unificação dos critérios como **melhoria futura** |
| 3 | Contas recorrentes geradas ao abrir a competência | É o gerador do desktop (`gerar_mes`, idempotente, com chave e trava por perfil): as contas de uma recorrência nascem quando a competência é aberta na Lista, no desktop ou no mobile. Se a geração falhar, a tela avisa ("Recarregue a página para tentar de novo") e nada é gravado. Previsões de competências nunca abertas não aparecem em relatórios até alguém abri-las | **Não bloqueadora** (regra existente, sem duplicidade); geração agendada como **melhoria futura** |
| 4 | Competência de vencimentos entre os dias 29 e 31 no desktop | O formulário de Despesas do desktop calcula "mês anterior ao vencimento" com `Date.setMonth`: com vencimento em 29 a 31 e mês anterior mais curto, cai no próprio mês (31/03 → competência 03 em vez de 02). O usuário vê e pode corrigir a competência antes de salvar; o banco aceita até 12 meses de distância. O mobile calcula certo, por mês | **Não bloqueadora**; correção no desktop como **melhoria futura** (exige autorização: muda uma tela homologada) |
| 5 | "Observações" da fonte de receita não gravada no fluxo original | O JS do Flask não envia o campo; o novo aplicativo também não o grava, e o mobile não o mostra (para não sugerir que grava). As observações da previsão e do recebimento ("[ACIMA DO PREVISTO] …") continuam gravadas | **Melhoria futura** |
| 6 | Classificação ou limites de compras no cartão | Compras parceladas e despesas fixas do cartão não consomem limite da Categoria do Cartão (decisão do titular de 31/10/2026, FIN-CARTAO-DESPESAS-FIXAS-01). O mobile usa os grupos e totais do banco (`fatura_por_categoria`), iguais aos do desktop, e mostra créditos à parte | **Não bloqueadora** (regra decidida e igual nas duas versões) |
| 7 | Recorrência no cartão pelo mobile (Proposta B) | Adiada pelo titular (MOBILE-05). Já existe na tela Recorrências do desktop (`criar_recorrencia_cartao`) | **Melhoria futura** (contrato próprio) |
| 8 | Instalação no iPhone não comprovada localmente | A instalação exige HTTPS; a prévia é `http://127.0.0.1` e o Firefox não instala PWA. Manifesto, ícones e metadados foram validados (teste unitário e prévia) | **Não bloqueadora**; conferência na homologação depois do deploy autorizado (seção 10) |
| 9 | Verificações dependentes não executadas | Eram os testes em modo serial depois das falhas de recorrência. Com as sequências alinhadas, **todos rodam** (0 não executados nos dois códigos) | **Resolvida** |

## 8. Plano de publicação (para autorização)

**Versão candidata:**
- ramo `mobile-final-01`, o último commit do ramo (código em `5832de9` PWA e `4a1432e` testes, mais este documento);
- avanço rápido de `origin/main` (`7e035c5`) até ele;
- sem migration e sem dependência nova (o `package.json` não mudou).

**Verificações antes do deploy:**
1. **Projeto Cloudflare Pages:** `controle-financeiro`, ramo de produção `producao`, domínios `controle-financeiro-jah.pages.dev` e `financas.kortexbrasil.com`.
2. **Projeto Supabase:** `fzjmgekasjrgvmfdkdog`, a URL do build (`SUPABASE_URL`) e a chave publicável (`SUPABASE_PUBLISHABLE_KEY`). São só valores públicos, conferidos pelo `build.mjs`.
3. **Banco:** as 67 migrations do banco remoto são as do repositório (`scripts/supabase_migrations.py`, só leitura). Esta versão não traz nenhuma.
4. **Estado publicado registrado:** deploy `5d608ca5`, versão `7e035c5`. Ele é a referência do rollback.
5. **Build:** `web/dist` gerado do commit candidato, com `verificarDist` sem achados e a impressão do `dist` anotada.
6. **Sem mudança financeira inesperada:** a diferença para o publicado é só frontend (`web/`), testes e documentação.
7. **Arquivos não rastreados:** os 24 preservados; push só dos commits.

**Sequência, só com autorização:**
1. `git push origin mobile-final-01:main`, só avanço rápido, sem força.
2. Build com as variáveis de produção.
3. `npx wrangler pages deploy dist --project-name controle-financeiro --branch producao`.
4. Anotar o id do deploy novo.

**Homologação em produção (leitura primeiro):**
1. Login e navegação no desktop.
2. Login no celular, Página Principal Mobile e os sete módulos.
3. Consulta dos dados financeiros reais, sem gravar.
4. Sair.
5. Instalação na tela de início do iPhone e abertura em modo independente (seção 10).

Nenhum lançamento real só para demonstrar.

## 9. Rollback

- **Frontend:** no painel do Cloudflare Pages (projeto `controle-financeiro`, Deployments), "Rollback" para o deploy `5d608ca5`. A alternativa é publicar de novo o `dist` do commit `7e035c5` com o mesmo comando de deploy. Leva segundos e não mexe no banco.
- **Repositório:** `git revert` dos commits da versão candidata em um ramo, sem reescrever o `main` e sem `push --force`.
- **Dados:** a versão não tem migration nem mudança de regra. O rollback do frontend **não depende de reverter dados**. O que for gravado pelo mobile depois da publicação usa as mesmas funções do desktop e continua válido na versão anterior.
- **PWA instalada:** sem service worker, o ícone instalado passa a abrir a versão anterior na próxima abertura. Se o rollback for definitivo, o ícone abre `inicio.html` da versão anterior, que já existia, e nada fica preso no aparelho.

## 10. Homologação

**No Firefox (prévia local):**
1. `run_e2e.py --previa` → http://127.0.0.1:8790/__previa__/.
2. Entrar com `usuario.g@teste.local` / `Senha-ficticia-G-2026`. Somente leitura: `usuario.h@teste.local` / `Senha-ficticia-H-2026`.
3. Percorrer os sete módulos pela Página Principal e pela barra.
4. Conferir que `http://127.0.0.1:8790/manifest.webmanifest` e `http://127.0.0.1:8790/icones/apple-touch-icon.png` abrem.

**No iPhone (depois do deploy autorizado):**
1. Abrir `https://financas.kortexbrasil.com` no **Safari**.
2. Tocar em **Compartilhar** (o quadrado com a seta) → **Adicionar à Tela de Início**.
3. Conferir o nome "Financeiro" e o ícone, e tocar em **Adicionar**.
4. Abrir pelo ícone: deve abrir sem a barra do Safari (modo independente), no login ou, com a sessão ativa, na Página Principal Mobile.
5. Entrar, percorrer os módulos e tocar em **Mais → Sair**: deve voltar ao login dentro do app.
6. Sem rede (modo avião): aparece a mensagem padrão do iPhone de falta de conexão; ao voltar a rede, o app abre normalmente.

**Limitação registrada:** a instalação no iOS exige HTTPS. A prévia local é `http://127.0.0.1` e o Firefox não instala PWA, então a instalação e o modo independente **não foram comprovados localmente**. Para conferir antes da produção sem expor dados reais, a única via segura seria um deploy de avaliação no Cloudflare (ramo `avaliacao`). Ele também é um deploy e, como usa o mesmo Supabase de produção, mostraria dados reais a quem entrasse. Por isso essa conferência fica reservada para a homologação logo depois do deploy autorizado, ou para um deploy de avaliação se você o autorizar expressamente.
