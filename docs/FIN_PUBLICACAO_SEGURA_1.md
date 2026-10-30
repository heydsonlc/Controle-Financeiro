# FIN-PUBLICACAO-SEGURA-1 — Disponibilização do Controle Financeiro

**Situação (30/10/2026):** versão homologada e pronta para publicar.
- Servidor local no ar, com o build homologado.
- Nada publicado, sem push e nenhuma configuração do Cloudflare ou do Supabase alterada.
- Nenhum registro financeiro modificado; nenhuma competência aberta.

## 1. Conferência inicial (só leitura)

| Item | Resultado |
|---|---|
| Repositório | Íntegro (`git fsck`). `main` está 2 commits à frente de `origin/main` (`80d4e1b`), em avanço direto |
| Commits pendentes | `c7c049e` (correção das 21 compras) e `cf9c9e7` (geração automática), mais o commit deste contrato |
| Conteúdo dos commits pendentes | Sem migration, sem workflow, sem `.env`, banco, chave ou e-mail |
| Publicação automática no push | Nenhuma: o projeto do Pages não tem integração Git, não há workflow, e "Deploy to production" do Supabase está desligado desde 21/10 |
| Build | 166 arquivos, impressão `4b6cdb67b601`. Refeito a partir de `git archive cf9c9e7`: os mesmos arquivos e o mesmo conteúdo (a única diferença é o fim de linha do checkout). Nenhum arquivo não versionado de `frontend/static` no build |
| Configuração pública do build | Só a URL do projeto e a chave publicável. CSP restrita ao próprio site e ao Supabase do projeto |
| Supabase | 42 migrations (`20261020120000` … `20261201090000`) |
| Escritor | Pessoal = NOVO. Empresa sem registro = FLASK (`pode_gerar` falso) |

## 2. Recorrências (produção, transação somente leitura)

Comparação com o retrato tirado logo depois da transferência do Pessoal, antes de o titular gerar pela tela:
- **As 21 compras corrigidas:** presentes, com o identificador novo, e o motor as reconhece como existentes.
- **As 65 ocorrências:** uma única execução de geração (titular, 30/10, 02:53 UTC).
  - Criou 53 contas, 4 faturas e 8 compras, todas de 10 e 11/2026.
  - Nenhuma está paga e nenhuma tem movimento.
- **Outubro/2026:**
  - a prévia do Pessoal mostra 0 a gerar, 221 existentes e nada retroativo;
  - 30 contas no mês: 27 recorrentes, 2 faturas e a parcela da CAIXA, nenhuma paga.
- **Contas e compras que já existiam:** o conteúdo é idêntico, incluindo as pagas e as faturas.
- **Outras 79 tabelas:** sem mudança, entre elas movimentos, saldos, financiamento CAIXA (420 parcelas), consórcios, receitas e Empresa.
  - Mudaram só as 3 tabelas de registro da geração.
- **Duplicidades:**
  - nenhuma nova;
  - continua só "Clube dos Oficiais" 06/2026, herdada do Flask.

## 3. Cloudflare

| Item | Estado |
|---|---|
| Projeto Pages | `controle-financeiro`, Direct Upload, sem Git. Os outros projetos (`kortex-calculadora`, `kortex-site`) não foram tocados |
| Deploys | 9, todos de prévia na branch `avaliacao`, de 24 a 27/10. O mais recente é `eaea85a` |
| Cloudflare Access | Sem login, respondem **302 para o login do Access**: `avaliacao.…`, o endereço de um deploy, páginas internas, `config.js` e até `producao.…` |
| Endereço principal `controle-financeiro-jah.pages.dev` | **404, sem deploy, e fora da regra do Access.** Nunca publicar com a branch de produção enquanto ele não estiver protegido |
| HTTPS | `http://` leva a `https://` (301). Todo o `.dev` é HSTS pré-carregado nos navegadores |
| Variáveis públicas | `config.js` com a URL do projeto e a chave `sb_publishable_…`. Nenhuma chave privilegiada no build |

**Achado:** os deploys `avaliacao` são builds antigos, anteriores à geração automática. Eles apontam para o mesmo projeto Supabase, que hoje tem os dados reais, e só o titular passa pelo Access. O próximo envio para `avaliacao` substitui o endereço principal da prévia. Apagar os deploys antigos depende de autorização.

**A conferir pelo titular no painel do Zero Trust** (a CLI não lê o Access):
- a aplicação "controle-financeiro - Cloudflare Pages" cobre `*.controle-financeiro-jah.pages.dev`;
- a política tem Include **somente** com o e-mail do titular;
- não há regra "Everyone" nem "Bypass".

**Domínio, duas opções:**
1. **Recomendada para começar:** usar `https://avaliacao.controle-financeiro-jah.pages.dev`, já protegido. Não exige mudança de DNS nem de política.
2. **Domínio próprio** (por exemplo, um subdomínio de `kortexbrasil.com`, que já está na conta), nesta ordem:
   1. criar no Access a aplicação desse nome com a mesma política;
   2. proteger também o endereço principal `controle-financeiro-jah.pages.dev`;
   3. só então ligar o domínio ao projeto e publicar na branch de produção.

   Exige autorização para o DNS, a política e a publicação.

## 4. Supabase Auth

O aplicativo só usa login por e-mail e senha (`signInWithPassword`) e saída. Não usa link por e-mail, convite, recuperação nem OTP, então nenhum redirecionamento participa do login.

**No painel (Authentication → URL Configuration), conferir:**
- **Site URL:** o endereço escolhido no §3.
- **Redirect URLs:** só esse endereço, sem `localhost`.

**Situação de hoje** (lida do banco, somente leitura):
- 2 contas: a do titular (acesso aos 2 perfis) e a de teste B;
- cadastro público desligado;
- nenhuma conta SSO ou anônima;
- 0 fatores MFA.

## 5. Servidor local

- **O que é servido:** uma cópia congelada do build homologado, em `http://127.0.0.1:8765`, com os cabeçalhos de segurança.
  - O script de serviço recusa iniciar se a impressão não for `4b6cdb67b601`.
- **Conferido sem login:**
  - páginas e `config.js` respondem 200;
  - a tela de login abre sem erro de JavaScript nem de CSP;
  - uma página interna sem sessão volta ao login.
- **O que só o titular faz** (a senha não passa por terceiros):
  - login com a conta definitiva;
  - alternância Pessoal/Empresa;
  - abrir Despesas;
  - os demais módulos.
- **Ao abrir Despesas em 10/2026,** nada é gerado: 10 e 11/2026 já existem.
- **Abrir 11/2026 ou depois gera as competências seguintes de verdade.** Isso é o uso normal, decisão do titular.

## 6. Contas de teste e scripts antigos

**Conta B** (`4e7a9b60…`):
- senha exposta;
- sem acesso a perfil;
- último login em 27/10;
- 141 sessões ativas;
- não bloqueada.

**Desativação preparada**, pelo titular no painel, com autorização (Authentication → Users → conta B), uma destas:
- **Bloquear** ("Ban user"), reversível. Novas sessões e renovações são recusadas.
- **Excluir** ("Delete user"), definitivo. Leva sessões e tokens. Exige autorização específica.

**Depois:** apagar o arquivo local `.env.e2e-real`, que guarda as credenciais das contas de teste.

**Scripts bloqueados** (`scripts/guarda_producao.py`): os 23 scripts que semeiam dados fictícios, testam pela API ou pela tela, homologam migrations ou limpam o que os testes criaram. Eles foram escritos para o projeto `fzjmge…` como projeto de teste e só sabem apontar para ele. Agora recusam no início, antes de ler credenciais ou conectar:
- os 6 seeds `supabase_*_seed_teste.py` e `supabase_demo_preview_seed.py`;
- os 8 `supabase_*_real.py` e `supabase_despesas_real_limpeza.py`;
- `homologacao_cartoes.py`;
- `homologacao_real/{lote,motor,escritor,cr,pat}_real.py`;
- `web/tests/e2e/run_e2e_real.py`.

Ficam liberados os de leitura (`digital_lote.py`, `verificar_seguranca_supabase.py`) e os de operação por identidade (`vincular_titular_supabase.py`, `limpeza_ficticios_supabase.py`).

**Teste:** `tests/test_guarda_producao.py`, com 24 aprovados. Cada script roda sem credenciais e sai com "BLOQUEADO", e nada é importado antes da trava.

## 7. Publicação (cada passo com autorização expressa)

**Pré-condições:**
1. proteção do endereço confirmada no painel (§3);
2. login seguro validado pelo titular no servidor local (§5);
3. Site URL e Redirect URLs conferidos (§4);
4. autorização do titular.

**Procedimento:**
1. **Push:** `git push origin main`, sem force.
2. **Build:** em `web/`, com `SUPABASE_URL=https://fzjmgekasjrgvmfdkdog.supabase.co` e `SUPABASE_PUBLISHABLE_KEY=<chave publicável>`, rodar `npm run build`. O build recusa chave secreta e procura segredos no `dist`.
   - Conferir 166 arquivos, sem `127.0.0.1` no `config.js`.
3. **Envio:** `npx wrangler pages deploy dist --project-name controle-financeiro --branch avaliacao --commit-hash <commit>`.
   - **Nunca** `--branch producao` enquanto o endereço principal estiver fora do Access.
4. **Conferência sem login:** o endereço novo e `config.js` respondem 302 para o Access.
5. **Titular:**
   - entra pelo Access e pelo aplicativo;
   - confere Pessoal e Empresa;
   - abre Despesas em 10/2026 (nada a gerar).
   - A geração das competências seguintes acontece no uso normal.
6. **Opcional, com autorização:** apagar os deploys antigos de `avaliacao`.

O perfil Empresa continua no Flask; nada aqui transfere a Empresa nem altera o escritor único.
