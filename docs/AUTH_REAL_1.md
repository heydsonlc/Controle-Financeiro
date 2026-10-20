# AUTH-REAL-1 — Validação do MVP com o Supabase Auth real

Data: 2026-10-20. **Preparação concluída; nada executado no projeto remoto.** Ordem acordada: segurança do banco (✅ SEC-SUPABASE-PUBLIC-1) → **autenticação real** → modelagem de perfis → migração das funcionalidades.

Alvo: projeto Supabase do Controle Financeiro (`fzjmge…`, banco de teste). Nunca o da Calculadora Judicial. Sem Docker: usa o próprio projeto.

## 1. Estado atual do projeto (diagnóstico somente leitura)

| Item | Situação |
|---|---|
| Migration `20261020120000_financeiro_mvp_categorias` | **Já aplicada no remoto** e registrada em `supabase_migrations.schema_migrations` (14 comandos). Não foi aplicada nesta sessão; **confirmar quem aplicou** |
| Estado do schema `financeiro` | Idêntico à migration: RLS **habilitada e forçada**, policy única `SELECT` para `authenticated`, só `SELECT` concedido, `anon` sem `USAGE`, 0 linhas |
| Data API | Expõe só `graphql_public`: o `financeiro` ainda **não** está exposto, e o `public` segue fora (SEC-SUPABASE-PUBLIC-1) |
| Cadastro público do Auth | ⚠️ **Ligado** (`disable_signup: false`). Hoje exige confirmação por e-mail (`mailer_autoconfirm: false`); precisa ser desligado antes de expor `financeiro` |
| Provedores | Só e-mail; usuários anônimos desligados |
| Usuários no Auth | 0 |

## 2. O que fica a cargo do usuário (painel do projeto Controle-Financeiro)

1. *Authentication → Sign In / Providers*: **desligar "Allow new users to sign up"**.
2. *Authentication → Users → Add user → Create new user*: criar **duas contas de teste**, com e-mails fictícios e "Auto Confirm User" marcado. Senhas fortes e exclusivas, **nunca** as do login real. Elas só chegam aos scripts por variável de ambiente.
3. *Project Settings → Data API → Exposed schemas*: **adicionar `financeiro`**. Manter `public` fora.

## 3. Ferramentas preparadas

| Arquivo | Função |
|---|---|
| `scripts/supabase_mvp_seed_teste.py` | Insere as categorias fictícias do ambiente isolado (`Moradia (A)`…`Educacao (B)`) **só** para as duas contas de teste. Idempotente; sem `--confirmar` desfaz a transação; `--remover` limpa; recusa o projeto da Calculadora; não imprime e-mails completos nem IDs |
| `web/tests/e2e/run_e2e_real.py` | Os **mesmos 9 cenários E2E** contra o Supabase real (Auth, Data API e RLS reais). Gera `dist/` com a chave publicável do projeto (só local, fora do Git) e serve em `127.0.0.1` com a CSP real. **Recusa rodar** se o cadastro público estiver ligado, se `financeiro` não estiver exposto, se `public` estiver exposto ou se faltarem `CF_EMAIL_A/CF_SENHA_A/CF_EMAIL_B/CF_SENHA_B` |
| `web/tests/e2e/acesso.spec.mjs` | Agora parametrizado: contas por ambiente e chamadas REST diretas na URL configurada. Continua passando no ambiente isolado (9/9) |

Trava comprovada: com a configuração atual, o `run_e2e_real.py` termina com `E2E_REAL_BLOQUEADO` (exit 2) e aponta os três pré-requisitos pendentes.

## 4. Execução (depois do §2, com autorização)

```bash
set CF_EMAIL_A=...& set CF_SENHA_A=...& set CF_EMAIL_B=...& set CF_SENHA_B=...
venv\Scripts\python.exe scripts\supabase_mvp_seed_teste.py --email-a %CF_EMAIL_A% --email-b %CF_EMAIL_B%              & rem simulacao
venv\Scripts\python.exe scripts\supabase_mvp_seed_teste.py --email-a %CF_EMAIL_A% --email-b %CF_EMAIL_B% --confirmar
venv\Scripts\python.exe web\tests\e2e\run_e2e_real.py
venv\Scripts\python.exe scripts\verificar_exposicao_supabase.py --via-cli --com-escrita                              & rem public continua bloqueado
```

Critérios de aceite, todos medidos pelo E2E real:
- sem sessão, nada é consultado;
- credencial inválida mostra mensagem genérica;
- A vê só as categorias de A, e B só as de B;
- não há ação de escrita na tela;
- sair encerra a sessão;
- token adulterado é recusado pelo Auth real;
- REST anônimo não lê;
- REST com token de A não grava;
- `next` externo é ignorado;
- nenhuma violação de CSP.

## 5. Reversão

| Ação | Como |
|---|---|
| Remover os dados fictícios | `supabase_mvp_seed_teste.py ... --remover --confirmar` |
| Remover as contas de teste | Painel → *Authentication → Users* (a FK `on delete cascade` apaga as categorias delas) |
| Fechar o frontend novo | Tirar `financeiro` dos Exposed schemas |

## 6. Depois da validação

Seguir para a **modelagem de perfis**. Identidade (usuário do Auth) não é o mesmo que perfil financeiro: uma pessoa pode administrar vários perfis ou conjuntos de contas. Isso precisa estar definido antes de migrar receitas, despesas e financiamentos.
