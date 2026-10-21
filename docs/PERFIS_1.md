# PERFIS-1 — Identidade, perfis financeiros e isolamento de dados

Data: 2026-10-21. Implementação testada localmente e **validada no Supabase real de teste** (PERFIS-REAL-1, §8).

**Não executado:** migration no Supabase remoto, publicação no Cloudflare, migração de dados reais. Nenhuma alteração no Flask nem em regras financeiras.

## 1. Mapeamento dos perfis existentes (Flask)

| Aspecto | Como é hoje |
|---|---|
| Tabela | `public.perfil_financeiro`: **global**, `nome` único, `tipo`, `avatar`, `cor`, `ativo`, `padrao` |
| Perfis iniciais | "Pessoal" (padrão) e "Empresa", criados de forma idempotente (`PerfilFinanceiroService.obter_ou_criar_perfis_iniciais`) |
| Perfil ativo | Na **sessão do Flask** (`perfil_financeiro_id`); inativo nunca é usado; sem escolha, vale o padrão |
| Vínculo com usuário | **Não existe**: o Flask é de usuário único (SEG-1) |
| Dados por perfil | **36 tabelas** com `perfil_financeiro_id` (33 anuláveis): contas, despesas, receitas, cartões, financiamentos, veículos, IR, patrimônio, movimentos… |
| Regra herdada | `condicao_perfil`: o perfil **"Pessoal"** também enxerga as linhas com `perfil_financeiro_id NULL` (dados anteriores aos perfis) |
| Categorias de despesa | **Globais**, sem filtro por perfil (decisão da migration `b2c3d4e5f6a7`) |

## 2. Modelagem implementada (menor adaptação segura)

```
auth.users ──< financeiro.perfil_acesso >── public.perfil_financeiro ──< 36 tabelas legadas (perfil_financeiro_id)
 (identidade)   (autorização explícita)       (fonte única, do Flask)
```

- **Nada foi duplicado:** os perfis continuam só em `public.perfil_financeiro`, gerenciados pelo Flask.
- **`financeiro.perfil_acesso(user_id, perfil_financeiro_id, papel)`:** vínculo explícito. Um usuário pode ter vários perfis e um perfil pode ter vários usuários. `papel` é `TITULAR` ou `LEITOR`, só informativo nesta etapa, pois tudo é leitura. FKs com `on delete cascade`.
- **Nada é vinculado automaticamente.** Os vínculos são criados por administrador (SQL); o navegador não grava nessa tabela.
- **Perfil ativo no novo frontend:** guardado no `sessionStorage`, por usuário (`cf-perfil-ativo:<user_id>`). É **só preferência de tela**: cada consulta envia o perfil ao banco, que revalida.
- **Categorias:** seguem globais, como no Flask. A tabela `financeiro.categorias` do MVP (por usuário) corresponde a "global para o dono" e fica fora do escopo de perfis.

Migration: `supabase/migrations/20261021090000_financeiro_perfis_acesso.sql` (**não aplicada no remoto**).

## 3. Autorização e RLS

| Objeto | Proteção |
|---|---|
| `financeiro.perfil_acesso` | RLS **habilitada e forçada**; policy `SELECT` só dos próprios vínculos (`user_id = auth.uid()`); só `SELECT` concedido a `authenticated`; nada para `anon` |
| `financeiro.pode_acessar_perfil(id)` | **Porta única de autorização**: vínculo do próprio usuário **e** perfil ativo. Nulo, inexistente, de outro usuário ou inativo resultam em `false` |
| `financeiro.meus_perfis()` | Lista só os perfis ativos vinculados ao usuário (padrão primeiro) |
| `financeiro.contas_bancarias_do_perfil(id)` | Fachada **somente leitura** sobre `public.conta_bancaria`. Chama `pode_acessar_perfil`; se negado, `42501` (HTTP 403). Reproduz a regra `NULL → Pessoal`. Devolve só `id, nome, instituicao, tipo, cor, status`, sem agência, número nem saldo |
| As três funções | `SECURITY DEFINER` com `search_path = ''` e nomes qualificados; `EXECUTE` revogado de `PUBLIC`/`anon` e concedido só a `authenticated` |
| Tabelas legadas | Continuam sem nenhum privilégio para `anon`/`authenticated` e fora da Data API (SEC-SUPABASE-PUBLIC-1). Só as funções acima as leem |

**Regra para os próximos módulos:** toda função que receber um perfil do navegador deve passar por `financeiro.pode_acessar_perfil`, devolver só as colunas necessárias e reproduzir as regras do `PerfilFinanceiroService`.

## 4. Testes executados

| Suíte | Resultado |
|---|---|
| `tests/test_supabase_perfis.py` (banco + REST/PostgREST) | **34 passed** |
| `tests/test_supabase_mvp_rls.py` (com o ambiente ampliado) | **26 passed** |
| E2E no ambiente isolado (`run_e2e.py`): 9 do AUTH-REAL-1 + 5 do PERFIS-1 | **14 passed, 2 execuções seguidas** |
| Build e código-fonte (`npm run test:unit`) | **7 passed**. RPC só de uma lista de funções de leitura liberadas |
| Suíte completa (`pytest`, com `POSTGREST_BIN`) | **1097 passed, 0 skipped, 5 failed**: as mesmas 5 falhas preexistentes (comprovadas no commit `0e04407`); nenhuma nova |

Cenários obrigatórios cobertos:

| Cenário | Coberto por |
|---|---|
| Sem login não acessa perfis | `meus_perfis`, `contas_bancarias_do_perfil` e `perfil_acesso` → `InsufficientPrivilege` / 401–403 |
| A não acessa perfil exclusivo de B | Banco: `42501`; REST: 403; E2E: chamada direta com o id de B → 403, sem dados |
| Usuário autorizado alterna entre os próprios perfis | A: Pessoal (inclui o legado sem perfil) ↔ Empresa; a escolha persiste ao recarregar |
| Id alterado manualmente no navegador | `sessionStorage` adulterado com o id de B → a tela volta ao perfil padrão autorizado e nada de B aparece |
| Perfil inativo | Não aparece e não é acessível, mesmo com vínculo |
| Ninguém se autoconcede acesso | INSERT/UPDATE/DELETE em `perfil_acesso` negados (banco e REST) |
| Nenhum dado modificado | Só leitura; as tentativas de escrita foram negadas |
| Tabelas legadas protegidas | `public.conta_bancaria` e `public.perfil_financeiro` → `InsufficientPrivilege` direto |
| Os 9 testes do AUTH-REAL-1 | Passam no ambiente isolado. Contra o Supabase real exigem esta migration no remoto (§7) |

O ambiente de teste (`tests/supabase_local.py`) agora reproduz o staging: tabelas do Flask criadas a partir dos modelos, proteção SEC-SUPABASE-PUBLIC-1 aplicada, migrations de `supabase/` e dados **fictícios**.

## 5. Compatibilidade com o Flask

- Nenhum arquivo de `backend/` ou `frontend/` do Flask foi alterado.
- A migration só cria objetos no schema `financeiro`. A única ligação com o legado é a FK `perfil_acesso → public.perfil_financeiro` (`on delete cascade`): o Flask não exclui perfis (inativa), e uma exclusão só removeria vínculos.
- O Alembic não enxerga o schema `financeiro` (autogenerate só do `public`).
- Suíte completa: **1097 passed**; só as 5 falhas preexistentes, sem regressão.

## 6. Preparação para o MOBILE-CONTAS-1

- **Base pronta:** identidade, perfis autorizados, perfil ativo na tela e o padrão de fachada (`pode_acessar_perfil` + função de leitura com colunas mínimas + regra `NULL → Pessoal`).
- **Próximas fachadas, só leitura e por perfil:** despesas correntes do mês (`item_despesa`/lançamentos) e faturas de cartão do mês, agrupadas por mês. Cada uma deve reproduzir as regras do serviço Flask correspondente, com testes de equivalência contra o Flask.
- **Primeiro, para usar dados de verdade:**
  - aplicar esta migration no remoto (autorização);
  - criar os vínculos do usuário definitivo aos perfis reais (Pessoal/Empresa), por SQL de administrador;
  - definir a identidade pessoal definitiva e a recuperação de acesso.
- **Interface:** a tela inicial deve ser a lista de contas do mês. A tela atual (contas bancárias + categorias) é provisória, só para validar perfis.

## 7. Pendências e autorizações necessárias

1. Aplicar `20261021090000_financeiro_perfis_acesso.sql` no Supabase de teste. Exige autorização; depois, `run_e2e_real.py` volta a valer com os perfis.
2. Vínculos para as contas de teste no remoto (fictícios) e, depois, para a identidade definitiva.
3. Escrita (cadastro e pagamentos): só por RPC transacional, no MOBILE-CONTAS-2.

## 8. Validação real — PERFIS-REAL-1 (2026-10-21)

Alvo: projeto **Controle-Financeiro** (`fzjmge…`, `us-east-2`, ACTIVE_HEALTHY). Calculadora Judicial não tocada.

### 8.1 Migration

| Item | Resultado |
|---|---|
| Verificações antes | Colunas referenciadas existem com tipos compatíveis; `auth.uid()` existe; nenhum objeto do PERFIS-1 existia; `public` fora da Data API; perfis existentes: **Pessoal (1, padrão) e Empresa (2)** |
| Aplicação | `20261021090000_financeiro_perfis_acesso` **aplicada** e registrada em `supabase_migrations.schema_migrations` (17 comandos) |
| Conferência | Os 17 comandos registrados no remoto são **idênticos** ao arquivo commitado (comparação normalizada) |
| ⚠️ Forma de aplicação | A migration apareceu no remoto **logo após o push do `d04eb9d`**, antes de qualquer comando de aplicação meu (só rodei `--dry-run` e listagens). O mesmo aconteceu com `20261020120000` após o push do `0ee59f6`. Indício forte de uma **integração GitHub do Supabase que aplica `supabase/migrations` a cada push em `main`**. **Confirmar no painel** (*Project Settings → Integrations → GitHub*): enquanto existir, **push com migration = deploy no projeto de teste** |

### 8.2 Objetos e RLS no remoto

| Objeto | Verificado |
|---|---|
| `financeiro.perfil_acesso` | RLS habilitada e **forçada**; policy única `SELECT` dos próprios vínculos; só `SELECT` para `authenticated`; FKs para `auth.users` e `public.perfil_financeiro` (`on delete cascade`) |
| `meus_perfis`, `pode_acessar_perfil`, `contas_bancarias_do_perfil` | `SECURITY DEFINER`, `search_path=""`, `EXECUTE` só para `authenticated` (não para `anon` nem `PUBLIC`) |
| Tabelas legadas | 0 grants para `anon`/`authenticated`; `public` fora da Data API |

### 8.3 Dados de teste (fictícios e temporários)

Os perfis existentes **Pessoal e Empresa foram usados sem alteração**. Criados só para o teste, por `scripts/supabase_perfis_seed_teste.py`, com estado registrado em `data/` (fora do Git):
- 2 perfis temporários: "Perfil B" (ativo) e "Perfil inativo (A)" (inativo);
- 5 contas fictícias com o marcador `Banco ficticio [teste PERFIS-REAL-1]`, uma sem perfil (regra NULL→Pessoal);
- 4 vínculos: A→Pessoal (TITULAR), A→Empresa (LEITOR), A→inativo, B→Perfil B;
- as categorias fictícias do AUTH-REAL-1.

O script recusa rodar se as contas de teste já tiverem vínculos, preservando vínculos preexistentes.

### 8.4 Testes reais

| Teste | Resultado |
|---|---|
| E2E real (`run_e2e_real.py`): 9 do AUTH-REAL-1 + 5 do PERFIS-1 | **14/14 passaram** |
| A acessa só os próprios perfis | `meus_perfis` → Pessoal, Empresa (inativo fora) |
| B acessa só os próprios perfis | `meus_perfis` → Perfil B |
| A alterna entre Pessoal e Empresa | ✅ (E2E), escolha persiste ao recarregar |
| Perfil não autorizado | A→Perfil B, B→Pessoal, B→Empresa: **HTTP 403 (42501)** |
| Perfil inativo | A→inativo próprio: **403**; `pode_acessar_perfil` → `false` |
| Id alterado no navegador | Tela volta ao perfil padrão; chamada direta com o id de B → 403 |
| Autoconcessão de vínculo | `POST perfil_acesso` com token de A → **403**; A lê só os próprios 3 vínculos; 4 vínculos no banco (os criados) |
| Tabelas legadas pela Data API | Com token: **406 PGRST106**; anônimo (`--com-escrita`): `public BLOQUEADO` |
| Anônimo | `meus_perfis` → 401 |

### 8.5 Compatibilidade com o Flask

`/health` 200; o ORM do Flask leu os perfis, inclusive os temporários enquanto existiam, o que mostra que **as duas aplicações compartilham a mesma fonte de perfis**; a API do Flask sem sessão continua 401. Nenhuma das 52 tabelas legadas teve estrutura alterada.

### 8.6 Limpeza

Removidos exatamente o que foi criado: 4 vínculos, 5 contas, 2 perfis temporários e as categorias fictícias. Comparação com a impressão digital tirada antes dos testes: perfis existentes (Pessoal/Empresa, todas as colunas) **idênticos**, e as contagens voltaram ao estado inicial (2 perfis, 0 contas, 0 vínculos, 0 categorias, 2 contas no Auth, Alembic `c4f7a2d91b3e`). As contas do Auth e os perfis existentes foram preservados.

### 8.7 Bloqueadores e próximos passos

1. **Confirmar a integração GitHub do Supabase** (§8.1): decidir se o deploy automático de migrations a cada push continua, ou se migrations passam a ser aplicadas só sob comando.
2. **Identidade definitiva:** criar a conta pessoal real e vinculá-la a Pessoal e Empresa por SQL de administrador, com recuperação de acesso definida.
3. **MOBILE-CONTAS-1:** fachadas de leitura por perfil para despesas correntes e faturas do mês, reproduzindo os valores e agrupamentos do Flask (sem duplicar compras de cartão no total de despesas), com testes de equivalência.
