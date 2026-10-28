# Roadmap — Controle Financeiro

Pendências conhecidas, MVPs planejados e débitos técnicos.

Última atualização: 2026-10-23 (FIN-FATURA-INTEGRIDADE-REAL-1)

---

## Ordem de Trabalho (Prioridade)

```
SEC-0 ✅ → TEST-BASE-1 ✅ → SEG-1 ✅ → DEPLOY-PREP-1 ✅ → SUPABASE-MIGRATE-1 ✅ → DEPLOY-HOST-1 ✅ → DEPLOY-READY-FIN-1 ✅ → STAGING-RENDER-2 ✅ (preparação) → **criação do staging no Render (aguarda autorização comercial)** → SEG-2 → BACKUP-DOCS-1 → CLOUDFLARE-1 → ICONES-1B → DB-CLEAN-1 → CARD-SEC-1 → FIN-RULES-1 → TEST-FIN-1 → DATA-HYGIENE-1 → PERF-1 → FRONT-ARCH-1
```

Para detalhes de priorização completa, ver `README_TECNICO.md`.

---

## Pendências por Módulo

### Financiamentos

| ID | Descrição | Prioridade |
|----|-----------|-----------|
| FIN-AMORT-OPCAO-1 | Escolha formal entre reduzir prazo e reduzir prestação na amortização extraordinária | Média |
| FIN-TR-2 | Modo CAIXA SAC/TR com TR no saldo e na quota de amortização | Concluído |
| FIN-INDICES-1 | Tela de manutenção/importação de TR por competência | Concluído |
| FIN-SEGURO-UI-2 | Central de configuração do seguro habitacional (vigências, faixas, fatores) | Média |
| FIN-CLEAN-2 | Consolidar SAC+TR como derivação de SAC + TR, sem modo técnico visível | Concluído |
| FIN-CLEAN-3 | Consolidar seguro fixo/estimado, nomenclaturas e rotas legadas | Concluído |
| FIN-PARCELAS-UI-1 | Tabela avançada e filtros do cronograma de parcelas | Baixa |
| FIN-DOC-FIN-1 | Documentos/anexos vinculados ao financiamento (contratos, extratos) | Concluído |
| FIN-DOC-CAIXA-1 | Conferência manual CAIXA real x simulado em documentos do financiamento | Concluído |
| FIN-DOC-CAIXA-2 | Importação manual em lote de linhas de demonstrativos CAIXA | Baixa |
| FIN-DOC-CAIXA-3 | Leitura automática/OCR de demonstrativos CAIXA | Baixa |
| FIN-DOC-FIN-4 | Storage externo e política avançada de backup documental | Baixa |
| FIN-QUIT-CHECK-1 | Conferência do valor oficial de quitação informado pelo banco | Concluído |
| FIN-QUIT-OPER-1 | Quitação operacional do financiamento | Baixa |
| FIN-QUIT-1 | Simulação de quitação antecipada com cálculo de desconto | Concluído |
| FIN-CAIXA-IMPORT-1 | Importação de demonstrativos CAIXA para comparação real × simulado | Baixa |
| CORE-ESTORNO-4 | Estorno de pagamento direto de parcela de financiamento (backend + UI) | Concluído |

### Importação de Cartão

| ID | Descrição | Prioridade |
|----|-----------|-----------|
| IMPORT-3A | Confrontar lançamento importado com despesa já existente antes de classificar | Concluído |
| IMPORT-3B | Parser PDF para faturas além do formato CAIXA (outros bancos) | Média |
| IMPORT-3C | OCR para PDFs escaneados | Baixa |
| IMPORT-3D | Melhorar assinatura de reconhecimento (histórico acumulativo) | Média |

### Receitas

| ID | Descrição | Prioridade |
|----|-----------|-----------|
| CORE-RECEITA-1 | Fluxo protegido de recebimento: conta bancária obrigatória, movimento transacional, PUT/DELETE bloqueados após recebimento | Concluído |
| DATA-HYGIENE-RECEITA-1 | Saneamento de receitas históricas sem conta/movimento (`scripts/data_hygiene_receitas_historicas.py`) — dry-run auditado; 1 receita real pendente de decisão manual (id=20) | Concluído (com pendência manual) |
| CORE-ESTORNO-2 | Estorno de receita realizada com movimento compensatório (backend + UI) | Concluído |

### Cartões

| ID | Descrição | Prioridade |
|----|-----------|-----------|
| CORE-CARTAO-FATURA-1 | Idempotência e pagamento seguro de fatura de cartão | Concluído |
| CORE-ESTORNO-3 | Estorno de pagamento de fatura de cartão (reaproveita rota e modal de estorno de despesas; backend + UI) | Concluído |
| CART-1 | Despesas fatura: parcelamento inline com descrição, categoria e edição no mesmo modal | Alta |
| CART-2 | Relatório de gastos por Categoria do Cartão com histórico | Média |

### Veículos / Mobilidade

| ID | Descrição | Prioridade |
|----|-----------|-----------|
| CAT-SIST-1 | Categorias sistêmicas granulares para Mobilidade | Concluído |
| VEIC-ENCODING-1 | Correção controlada de encoding em Veículos/Mobilidade | Concluído |
| VEIC-3A | Homologação visual dos mockups (imagens veículo próprio, assinatura, app) | Alta |
| VEIC-3B | Validação do motor de cálculo de custo mensal | Alta |
| VEIC-3C | Padronização das imagens do mockup | Média |

### Segurança

| ID | Descrição | Prioridade |
|----|-----------|-----------|
| SEG-1 | Autenticação global de rotas e APIs — usuário único, sessão via Flask-Login, allowlist fechada (`/login`, `/logout`, `/static/*`, `/health`) | Concluído |
| CARD-CVV-LOCK-1 | Bloqueio de visibilidade do CVV: oculto por padrão, revelação por senha (`CARTOES_CVV_MASTER_PASSWORD`), falha fechada | Concluído |
| DEPLOY-READY-FIN-1 | Hardening para internet pública: cookie `__Host-` com expiração de 12h, verificação de `Origin` em escritas (CSRF entre subdomínios `*.kortexbrasil.com`), HSTS/cabeçalhos, limite de 64 MB, backup local via `pg_dump`/`pg_restore` bloqueado no host | Concluído |
| SEC-SUPABASE-PUBLIC-1 | Exposição das tabelas do Flask pela Data API: **contida** (`public` fora da Data API) e **corrigida no banco** (migration `c4f7a2d91b3e` aplicada no staging em 2026-10-20: RLS nas 52 tabelas, sem grants para anon/authenticated; Flask OK). Auditoria sem indício de acesso indevido (`docs/SEC_SUPABASE_PUBLIC_1.md`) | Concluído |
| SEG-2 | Limitar tentativas de login (não existe hoje). **Bloqueador de produção.** Proposta em `docs/STAGING_RENDER_2.md` §D | Alta |
| CARD-SEC-1 | Restante: mascarar/criptografar `numero_cartao` e criptografar `codigo_seguranca` em repouso no banco (hoje só a exposição na API/UI foi bloqueada, o dado continua em texto puro no banco) | Alta |

### Banco de Dados / Backend

| ID | Descrição | Prioridade |
|----|-----------|-----------|
| TX-ATOMIC-1 | Remover commit interno de `PerfilFinanceiroService.obter_ou_criar_perfis_iniciais()` que quebrava atomicidade de transações maiores | Concluído |
| MOV-REF-1 | `MovimentoFinanceiro.movimento_original_id` — referência explícita ao movimento compensado pelos 4 fluxos de estorno (migration `76fa60a587fd`) | Concluído |
| DB-CLEAN-1 | Corrigir `lazy='dynamic'` depreciado (~12 relacionamentos em `models.py`) | Média |
| DB-CLEAN-2 | Corrigir `datetime.utcnow` depreciado (~20 ocorrências) | Média |
| DB-CLEAN-3 | Corrigir N+1 queries em `to_dict()` com lazy load | Média |
| DB-CLEAN-4 | Corrigir `Query.get()` legado SQLAlchemy 2.0 | Média |

### Testes

| ID | Descrição | Prioridade |
|----|-----------|-----------|
| TEST-FIN-1 | Ampliar cobertura E2E em Despesas, Cartões e Financiamentos | Alta |
| TESTES-IMPACTO-1 | Validação por impacto adotada como padrão (`scripts/testes_impacto.py`, `docs/TESTES_IMPACTO_1.md`), com seletor calibrado (rota pelo caminho inteiro, atributo privado, E2E por dados de fatura) e regra permanente "na dúvida sobre impacto financeiro, ampliar". Pendente: medir a economia de tempo na tomada, no próximo marco obrigatório | Alta |
| TEST-CONV-1 | Converter scripts legados `teste_*.py` para pytest seguro | Baixa |

### Interface / UX Global

| ID | Descrição | Prioridade |
|----|-----------|-----------|
| UI-CLEAN-1 | Remover ações mockadas/no-op da interface global | Concluído |
| APPJS-CLEAN-1 | Remover legado órfão de `frontend/static/js/app.js` | Concluído |
| PREF-CLEAN-1 | Consolidar Preferências em Configurações | Concluído |
| REC-AGENDA-1 | Agenda completa de recorrências | Baixa |
| REC-EXPORT-1 | Exportação de recorrências | Baixa |
| CONTAS-EXPORT-1 | Exportação de contas bancárias | Baixa |
| RECEITAS-EXPORT-1 | Exportação de receitas | Baixa |
| CONFIG-PERFIS-2 | Gestão avançada de perfis financeiros | Média |
| HELP-SUPORTE-1 | Canal real de suporte/chamado | Baixa |
| DASH-FILTROS-1 | Filtros reais no Dashboard | Baixa |
| IR-ZIP-SAIDAS-1 | ZIP de documentos de saídas para contador | Baixa |

### Módulos Futuros

| ID | Descrição | Prioridade |
|----|-----------|-----------|
| IR-1 | Módulo de Imposto de Renda / Documentos Fiscais IRPF | Futuro |
| CTX-FIN-1 | Diagnóstico de perfis financeiros alternáveis (pessoal/empresa) | Futuro |
| DEPLOY-PREP-1 | Preparação segura para deploy: ambientes (`APP_ENV`), hardening de `SECRET_KEY`/CVV, `.env.example`, `check_deploy_env.py`, `docs/DEPLOY.md` | Concluído |
| SUPABASE-MIGRATE-1 | Projeto Supabase validado como banco `staging`: migrations completas do zero, admin criado, smoke tests OK. Também corrigiu 6 tabelas + 8 colunas de drift pré-existente nunca criadas por nenhuma migration | Concluído |
| DEPLOY-HOST-1 | Backend preparado para Render (gunicorn, render.yaml, runtime.txt, smoke test); publicação real no painel do Render é ação manual pendente | Concluído (preparação) |
| STORAGE-1 | Storage persistente: `DATA_DIR` centraliza os diretórios graváveis; disco Render de 1 GB em `/var/data` (DEPLOY-READY-FIN-1) | Concluído (preparação) |
| STAGING-RENDER-1/2 | Contrato e preparação do staging: Supabase Pro confirmado, Session pooler IPv4 validado, `.env.staging` no pooler, custos e checklist (`docs/STAGING_RENDER_1.md`, `docs/STAGING_RENDER_2.md`) | Concluído (preparação) |
| STAGING-RENDER-3 | Criar o Web Service pago no Render e executar o checklist de staging com dados fictícios | Aguarda autorização |
| CF-SUPABASE-REFACTOR-1 | Nova arquitetura (Cloudflare Pages + Supabase Auth/PostgREST/RLS): MVP de login e categorias somente leitura em `web/` + `supabase/`, testado em ambiente isolado (26 RLS/REST, 7 build, 9 E2E). Plano por módulos em `docs/CF_SUPABASE_REFACTOR_1.md` §6 | Concluído (MVP local, não publicado) |
| AUTH-REAL-1 | MVP validado com o Supabase Auth real: cadastro público desligado, só `graphql_public` + `financeiro` expostos, E2E real 9/9 com isolamento entre duas contas, nenhuma escrita indevida, dados fictícios removidos (`docs/AUTH_REAL_1.md`) | Concluído |
| PERFIS-1 | Identidade ↔ perfil financeiro (`financeiro.perfil_acesso`, `meus_perfis`, `pode_acessar_perfil`, fachada `contas_bancarias_do_perfil`), reutilizando os perfis do Flask. **Validado no Supabase real** (PERFIS-REAL-1: migration aplicada e conferida, E2E real 14/14, acesso cruzado negado, limpeza exata) (`docs/PERFIS_1.md`) | Concluído |
| SUPABASE-DEPLOY-CONTROL-1 | Deploy automático de migrations identificado (integração GitHub do Supabase) e **desligado** ("Deploy to production" off, confirmado no painel). Padrão: migrations só por `scripts/supabase_migrations.py aplicar --versoes`, com autorização expressa (`docs/SUPABASE_DEPLOY_CONTROL_1.md`) | Concluído |
| MOBILE-CONTAS-1 | Tela inicial "Contas do mês" (somente leitura): `contas_do_mes`, `lancamentos_da_fatura`, `mes_pode_estar_incompleto`; equivalência com o Flask sem divergência (5 cenários), 38 testes de banco/REST e 25 E2E locais (`docs/MOBILE_CONTAS_1.md`). Migration **não aplicada no remoto** | Concluído (local) |
| MOBILE-CONTAS-REAL-1 | Validado no Supabase real: push não aplicou a migration (deploy manual comprovado); `20261022090000` aplicada manualmente e conferida; equivalência Flask × fachada sem divergência; E2E real 25/25; acesso cruzado negado; limpeza com estado final idêntico (`docs/MOBILE_CONTAS_1.md` §9) | Concluído |
| CICLO-FIN (decisão 2026-10-21) | **Nada vai para o Cloudflare antes de o ciclo financeiro estar completo e validado.** Critério de publicação: criar despesa → ver na competência certa → pagar → saldo bancário atualizado → conferir movimento → estornar; o mesmo para receitas e faturas. Exige equivalência financeira, autorização por perfil e nenhuma alteração indevida de histórico. Antes de cada MVP, conferir o que já existe no Flask e no `web/`. Financiamentos, veículos, OCR e relatórios avançados não bloqueiam, mas devem aparecer como indisponíveis. O mobile vem depois do ciclo | Decisão vigente |
| FIN-RECORRENCIA-1 | Geração explícita e confirmada de recorrências mensais/anuais (conta e cartão) e faturas: prévia somente leitura + `gerar_mes` transacional e idempotente, identidade (recorrência, natureza, competência), dia contratual preservado (31→28/29→31), competência dispensada não recriada, itens inválidos rejeitados com motivo, gestão explícita (`pode_gerir`). Decisões D1–D9 definitivas (contrato V5, substitui a proposta do `10447e1`). 51 testes + 1 xfail (item 6: o Flask recria dispensadas — exige escritor único, transição T1 proposta), E2E 29/29 (`docs/FIN_RECORRENCIA_1.md`). Migration `20261023090000` **não aplicada no remoto** | Concluído (enviado em `eb22ee8`) |
| FIN-RECORRENCIA-T1 | Gerador único por perfil: `financeiro.gerador_recorrencia` (padrão FLASK, troca só por administrador, auditada), guarda no Flask (orquestrador, faturas do GET, job/scheduler) e no novo motor; trava consultiva compartilhada/exclusiva; erro de verificação bloqueia. Item 6 do FIN-RECORRENCIA-1 passa. 86 testes + E2E 30/30 (`docs/FIN_RECORRENCIA_T1.md`). Migration `20261024090000` **não aplicada no remoto** | Concluído (local) |
| FIN-RECORRENCIA-REAL-1 | Validado no Supabase de teste: `20261023090000` + `20261024090000` aplicadas manualmente; novo gerador só no Perfil B fictício; E2E real 30/30; Flask real não gerou nada no perfil NOVO (dispensa preservada) e seguiu gerando na Empresa (FLASK); limpeza com estado final idêntico (`docs/FIN_RECORRENCIA_REAL_1.md`) | Concluído |
| FIN-FATURA-UNICA-1 | Índice único parcial `ux_conta_fatura_cartao_competencia` (cartão + competência, só faturas) com verificação prévia de duplicidade; Flask devolve a fatura existente no conflito (savepoint), novo motor usa ON CONFLICT. Concorrência real testada (Flask×Flask, novo×novo, Flask×novo nos dois sentidos, parceladas, recorrência+compra, fatura paga); controle sem índice duplica. Migrations `20261025090000` (Supabase) e Alembic `d81f5a2b9c3e` **não aplicadas no remoto** (`docs/FIN_FATURA_UNICA_1.md`) | Concluído (enviado em `42d073b`) |
| FIN-FATURA-UNICA-REAL-1 | Validado no Supabase de teste: só `20261025090000` aplicada (manual); um único índice com a definição aprovada; concorrência real Flask×Flask, novo×novo, Flask×novo (nos dois sentidos), parceladas, recorrência+compra, fatura paga, repetição e isolamento — 0 duplicidades, saldos e movimentos intactos; E2E real 30/30; limpeza com estado final idêntico; Alembic passa a conferir a definição (regra única) (`docs/FIN_FATURA_UNICA_REAL_1.md`) | Concluído |
| FIN-DESPESAS-1 | Cadastro, edição, inativação e exclusão segura de despesas (avulsas e recorrentes) no próprio modelo do Flask; regras no banco (gestão explícita, bloqueio de conta paga/com movimento/de outros módulos, versão + trava, criação idempotente, exclusão de conta recorrente = competência dispensada); geração só pelo FIN-RECORRENCIA-1. 52 testes + E2E 36/36; equivalência com o Flask e 8 diferenças intencionais (`docs/FIN_DESPESAS_1.md`). Migration `20261026090000` **não aplicada no remoto** | Concluído (enviado em `2fdca76`) |
| FIN-DESPESAS-REAL-1 | Validado no Supabase de teste: só `20261026090000` aplicada (conferências prévias); E2E real 36/36; 22/22 testes reais pela API (cadastro, edição, dispensa, bloqueios, concorrência, idempotência, autorização); limpeza com estado final idêntico (`docs/FIN_DESPESAS_REAL_1.md`) | Concluído |
| FIN-PAGAMENTO-TRAVA-1 | Travas no Flask (`backend/services/trava_financeira.py`: PostgreSQL `FOR UPDATE` + `lock_timeout`; SQLite trava de escrita antes da releitura) em pagamento, estorno, edição/exclusão de despesa, fatura (pagamento, recálculo, compras), baixa automática (atômica por conta) e saldo bancário; ordem conta → compras → conta bancária → movimento; conflito = 409 sem gravar. Cenário 350,40 × 500,00 reproduzido no código antigo e corrigido; 17 testes com processos Flask reais (PostgreSQL e SQLite). Só local, sem migration (`docs/FIN_PAGAMENTO_TRAVA_1.md`) | Implementado localmente |
| FIN-RECEITAS-1 | Receitas PREVISTAS sobre o modelo do Flask (fonte/previsão/recebimento): consulta por competência com situação derivada dos registros reais, cadastro (avulsa ou 12 meses), edição, exclusão segura (zera a recorrente como o Flask), inativação de fonte; nenhum recebimento/movimento/saldo; previsão com recebimento bloqueada; trava SHARE contra recebimento simultâneo do Flask. 50 testes + E2E 42/42 (`docs/FIN_RECEITAS_1.md`). Migration `20261027090000` aplicada no Supabase de teste (FIN-RECEITAS-DATA-REAL-1) | Concluído |
| FIN-RECEITAS-DATA-REAL-1 | Data prevista de recebimento independente da competência (`receita_orcamento.data_prevista`, nula; fallback pelo dia da fonte; regra sem deriva na recorrência; Flask compatível via coluna deferred; Alembic `e3b7c9d1a2f4` testada só em banco fictício). `20261027090000` (consolidada) aplicada no Supabase de teste; E2E real 43/43; 12/12 testes reais; limpeza com estado final idêntico (`docs/FIN_RECEITAS_DATA_REAL_1.md`) | Concluído |
| FIN-CARTOES-1 | Cartões (cadastro/edição/inativação sem número nem CVV), compras à vista e parceladas (centavos exatos, prévia no banco, fatura paga nunca recebe compra), edição/exclusão só de parcelas em fatura aberta com recálculo como o Flask; nenhum pagamento. 70 testes (equivalência com o Flask real) + E2E 47/47 (`docs/FIN_CARTOES_1.md`). Migration `20261028090000` aplicada no Supabase de teste (FIN-CARTOES-REAL-1) | Concluído |
| FIN-CARTOES-REAL-1 | `20261028090000` aplicada no Supabase de teste; E2E real 47/47; 21/21 testes reais (API, concorrência com transações independentes, Flask real, autorização); cenário de cartões só no Perfil B temporário; limpeza com estado final idêntico (`docs/FIN_CARTOES_REAL_1.md`) | Concluído |
| FIN-FATURA-INTEGRIDADE-1 | Fatura paga imutável nas compras (recorrência do Flask e do novo motor, importação, recorrência importada): desvio para a próxima não paga com `lancamento_agregado.mes_fatura_original`; reimportação sem duplicar; compra do Flask atômica. Ordem global de travas cartão → faturas → compras → conta bancária → movimento nos dois sistemas (deadlock do código anterior reproduzido e eliminado). 13 + 3 testes. Migration `20261029090000` aplicada no Supabase de teste (FIN-FATURA-INTEGRIDADE-REAL-1); Alembic `f1c4d8e2a7b9` testada só em bancos fictícios (`docs/FIN_FATURA_INTEGRIDADE_1.md`) | Concluído |
| FIN-FATURA-INTEGRIDADE-REAL-1 | Validado no Supabase de teste: só `20261029090000` aplicada, com conferências antes e depois (funções, privilégios, RLS e conteúdo das 61 tabelas idêntico); E2E real 47/47; 14/14 cenários reais: desvio de fatura paga no novo app e no Flask real com a competência original, recorrência, parcelada igual nos dois, bloqueios, permissões, concorrência e ordem de travas cartão → faturas; limpeza com conteúdo final idêntico (`docs/FIN_FATURA_INTEGRIDADE_REAL_1.md`) | Concluído |
| FIN-CARTOES-FECHAMENTO-1 | Competência da compra sugerida pelo fechamento do cartão (mês do vencimento; compra no dia do fechamento vai para a próxima por padrão, regra `ATUAL`/`PROXIMO` por cartão; sugestão só com `fechamento_confirmado`; ciclo ambíguo sem atribuição silenciosa; dias 29–31 no último dia dos meses curtos), com ajuste manual auditado (`mes_fatura_sugerido`), parceladas mensais e desvio de fatura paga mantidos. Fatura consolidada só recebe compra com confirmação do total visto, auditoria (`fatura_consolidada_inclusao`) e total atualizado, conferida sob trava no Flask e no banco. Flask com fechamento e vencimento independentes (edição preserva o fechamento). 67 testes (grade de datas Flask = PostgreSQL; conferência da migration ensaiada sobre dados da versão anterior) + web unit 15 + E2E local; migrations **só locais** (Supabase `20261030090000`, Alembic `c7e2a9d4b8f3`); validação remota pendente (`docs/FIN_CARTOES_FECHAMENTO_1.md`) | Concluído e validado (ressalva de teste documentada: cenário 10, §15) |
| FIN-CARTOES-D6-INTEGRIDADE-1 | Nenhum caminho altera fatura consolidada em silêncio: recorrências (Flask e novo motor) e importação não incluem em FECHADA (novo motor: `REJEITADA` com motivo; Flask: não grava e registra no log; importação: compra recusada inteira, competência do arquivo mantida, D5 preservada); Flask bloqueia mudar valor/mês/parcelas e excluir compra de fatura consolidada e mudar valor ou excluir a fatura pela rota de despesas; consolidação numa só transação. Seção acrescentada à `20261030090000` (pendente no remoto). 18 testes (9 falham no código anterior) (`docs/FIN_CARTOES_FECHAMENTO_1.md` §11). Validação remota pendente (FIN-CARTOES-FECHAMENTO-REAL-1) | Implementado localmente |
| FIN-CARTOES-RECORRENCIA-PENDENCIA-1 | Recorrência não lançada por fatura consolidada vira ocorrência persistente (`public.recorrencia_rejeicao`, uma por recorrência + competência; nova tentativa só conta), com aviso no Flask (Despesas) e no novo aplicativo (Contas do mês) e dispensa auditável e idempotente, que não muda situação, recorrência, compra nem fatura. Na `20261030090000` e na Alembic `c7e2a9d4b8f3` (só locais). 14 testes + E2E (`docs/FIN_CARTOES_FECHAMENTO_1.md` §12). Validação remota pendente | Implementado localmente |
| FIN-CARTOES-FECHAMENTO-PRE-REAL-1 | D6 e PENDENCIA-1 em commits locais separados; regressão única nível 3 (1581 aprovados, 5 falhas preexistentes; web unit 15/15; E2E 49/49); conferência local e `antes` remota da `20261030090000` OK (só leitura); cenários reais 17a/17b (fechamento automático, recorrência rejeitada, aviso e dispensa) preparados e ensaiados localmente (`docs/FIN_CARTOES_FECHAMENTO_1.md` §13). Migration não aplicada | Pronto para aplicação controlada |
| FIN-CARTOES-FECHAMENTO-REAL-1 | `20261030090000` aplicada só no Supabase de teste (24/10/2026); conferência `depois` OK (9 funções novas, 10 substituídas, 2 tabelas com RLS, 3 colunas, dados idênticos). Reais: E2E 47/47 (2 ignorados, só harness local), cartões 22/23 (17, 17a e 17b OK; cenário 10 com roteiro de teste anterior à ordem global de travas, sem defeito funcional), integridade de faturas 14/14. Limpeza com conteúdo idêntico ao de antes da migration (`docs/FIN_CARTOES_FECHAMENTO_1.md` §14). Publicação do frontend pendente | Validado com ressalva |
| FIN-CARTOES-FECHAMENTO-ENCERRAMENTO-1 | FIN-CARTOES-FECHAMENTO-1 concluído e validado, com ressalva de teste documentada. Cenário 10 de `supabase_cartoes_real.py` reescrito como o 9d (compra do novo app em thread esperando a trava do cartão segurada pelo Flask; sem deadlock, sem duplicidade, executado correto); ensaio local aprovado e controle reproduzindo a falha remota; concorrência local 27/27. Reexecução remota isolada pendente (`docs/FIN_CARTOES_FECHAMENTO_1.md` §15) | Concluído |
| FIN-CARTOES-PAGAMENTO-1 | Pagamento integral e estorno de fatura no novo aplicativo (Supabase como motor): débito/crédito nos movimentos existentes, saldo pelos movimentos, valor diferente do executado só classificado (juros, desconto, ajuste) e justificado, idempotência, ordem de travas, um sistema por perfil (D5, atribuição do T1; o Flask recusa fatura de perfil NOVO). Corrige o 2º estorno bloqueado do Flask. Migration `20261031090000` (só local). 15 testes novos + E2E; impacto 806/807 (1 expectativa atualizada) e E2E 50/50 (`docs/FIN_CARTOES_PAGAMENTO_1.md`) | Concluído e validado no Supabase de teste |
| FIN-CARTOES-PAGAMENTO-REAL-1 | `20261031090000` aplicada só no Supabase de teste (24/10/2026); `depois` OK (9 funções novas, 1 tabela com RLS forçada, nada alterado, dados idênticos). Reais: E2E 48/48 (2 ignorados, só harness local), pagamento 16/16, cartões 23/23 com o cenário 10 do fechamento aprovado no remoto. Limpeza com conteúdo idêntico ao de antes da migration (`docs/FIN_CARTOES_PAGAMENTO_1.md` §10). Publicação do frontend pendente | Validado |
| FIN-MOVIMENTACOES-1 | Pagar e estornar despesa comum, receber (parcial mantido, decisão do titular) e estornar receita, movimentos do mês na tela de Contas, no mesmo motor do PAGAMENTO-1 (movimentos, saldo, idempotência, travas, escritor único). Flask recusa essas operações em perfil NOVO e não baixa débito automático nele (decisão do titular); consórcio, financiamento e recebimento pontual seguem no Flask. Corrige o recebimento não atômico e o 2º estorno do Flask. Migration `20261101090000` (só local, sem tabela nova). 14 testes + E2E 2; impacto: Python 711/714 (1 expectativa D6 atualizada, 2 preexistentes), E2E 52/52 (`docs/FIN_MOVIMENTACOES_1.md`) | Concluído e validado no Supabase de teste |
| FIN-MOVIMENTACOES-REAL-1 | `20261101090000` aplicada só no Supabase de teste (24/10/2026); `depois` OK (13 funções novas, nada alterado, dados idênticos). Reais: E2E 50/50 (2 ignorados, só harness local), movimentações 21/21, pagamento de cartões 16/16. Limpeza com identidade conferida registro a registro e conteúdo idêntico ao de antes da migration (`docs/FIN_MOVIMENTACOES_1.md` §10). Publicação pendente | Validado |
| FIN-PUBLICACAO-PREVIEW-2 | Prévia protegida no Cloudflare Pages (projeto `controle-financeiro`, branch `avaliacao`, Cloudflare Access só para o titular) com dados fictícios de demonstração no Supabase de teste (`docs/FIN_PUBLICACAO_PREVIEW_2.md`) | Publicado |
| FIN-MIGRACAO-FIDELIDADE-1 | Diagnóstico da fidelidade ao Flask e plano em 4 fases; todos os módulos obrigatórios, Importar Cartão com prioridade elevada (`docs/FIN_MIGRACAO_FIDELIDADE_1.md`) | Concluído (diagnóstico) |
| FIN-MIGRACAO-FIDELIDADE-FASE-1 | Moldura do Flask (menu, barra superior, seletor de perfil), itens "Em migração", menu no celular, gestão de perfis em Configurações. Migration `20261102090000` (gestão de perfis; perfil novo nasce no gerador NOVO na mesma transação) | Concluído |
| FIN-MIGRACAO-FIDELIDADE-FASE-1-REAL | `20261102090000` aplicada só no Supabase de teste; `depois` OK (10 funções novas, dados idênticos). Reais: interface e perfis 4/4, operações 4/4, Data API (isolamento, somente leitura, geração no perfil novo) e pós-publicação 1/1. Limpeza por identidade, dados idênticos aos de antes. Prévia atualizada (versão `1cc8025`, implantação `17a39256`) (`docs/FIN_MIGRACAO_FIDELIDADE_FASE_1.md` §G) | Publicado na prévia; aguarda avaliação visual do titular |
| FIN-FIDELIDADE-DESPESAS-1 | Tela original de Despesas do Flask sobre o Supabase. HTML, CSS e JS do Flask copiados, com ponte CSP (sem afrouxar a CSP) e adaptador das rotas `/api/` para as funções existentes; sem migration. Unit 17/17, E2E 64/64 (`docs/FIN_FIDELIDADE_DESPESAS_1.md`) | Concluído localmente; prévia em validação |
| FIN-FIDELIDADE-RECORRENCIAS-1 | Tela original de Recorrências do Flask sobre o Supabase (mesmo padrão de Despesas); migration local `20261103090000` (listagem, reativar, meio informativo). Integração com Despesas (meio de pagamento; aviso do cartão marcado como recorrente). Banco 11/11, E2E 69/69 (`docs/FIN_FIDELIDADE_RECORRENCIAS_1.md`). Pendências R1–R4 | `20261103090000` aplicada no Supabase de teste; validado e publicado na prévia (implantação `4ba9a4d9`); aguarda homologação do titular |
| FIN-FIDELIDADE-CARTOES-1 | Telas originais de Cartões e Importar Cartão do Flask sobre o Supabase (mesmo padrão). Cartões: limites por Categoria do Cartão, fatura por categoria, edição de um lançamento, parcelas futuras, compra nova (acréscimo) e inativar; número, validade e CVV não guardados. Importar: CSV lido no navegador, análise com duplicidade e conciliação, gravação confirmada tudo ou nada. Migrations locais `20261104090000` e `20261105090000` (não aplicadas). Banco 69 + 26, unit 23/23, E2E novos 5 + 3 (`docs/FIN_FIDELIDADE_CARTOES_1.md`). Pendências I1 (PDF/XLSX), I2, R2 (cadastro de recorrência no cartão) | `20261104090000` e `20261105090000` aplicadas no Supabase de teste; validado e publicado na prévia (implantação `59954c53`, versão `ef6c0d8`); aguarda homologação do titular |
| FIN-FIDELIDADE-RECEITAS-CATEGORIAS-1 | Telas originais de Receitas e Categorias do Flask sobre o Supabase; escrita só das Categorias do Cartão (escritor único); categorias de despesa (globais) ficam no Flask. Migration `20261119090000` (só local) (`docs/FIN_FIDELIDADE_RECEITAS_CATEGORIAS_1.md`) | Implementado localmente |
| FIN-CONTRATOS-2 | Guarda de escritor único no Flask (financiamentos, consórcios, despesas de parcela); pagamento e estorno das parcelas pelas despesas no novo aplicativo, Defeitos A e B corrigidos. Migration `20261120090000` (só local, com reversão). Motor de cálculo (cadastro, amortização, seguros) e cadastro de consórcio: pendentes, P0 antes de perfil real NOVO (`docs/FIN_CONTRATOS_2.md`) | Implementado localmente |
| FIN-FINANCIAMENTOS-MOTOR-1 | Motor de Financiamentos no novo aplicativo: SAC/TR da Caixa, SAC (com ou sem índice), PRICE e SIMPLES; cadastro, edição, vigências de seguro, amortização extraordinária, ajuste de saldo, regeneração, exclusão segura, simulação de quitação e parcelas históricas sem movimento. Igual ao Flask ao centavo (arredondamento do Decimal reproduzido), calibração Caixa preservada, cenário 420/22/398 com as sete provas; correções M1–M11 classificadas (inclui a origem da diferença de R$ 1,00 das despesas reais). Migration `20261123090000` (com reversão) aplicada só no Supabase de teste e validada com perfil temporário, 17/17 (§11). Contrato real não é do motor SAC/TR atual: decisão de calibração antes de transferir o perfil (`docs/FIN_FINANCIAMENTOS_MOTOR_1.md`) | Concluído (commit `4de6fb5`); aplicado e validado no Supabase de teste |
| FIN-ESCRITOR-UNICO-FINAL-1 | Escritor único em todas as escritas compartilhadas: no Supabase, 29 funções antigas (despesas, recorrências, receitas, cartões, compras, lançamentos, importação, gestão do perfil) exigem o perfil atribuído ao novo aplicativo (`exigir_escrita_novo`); no Flask, guarda por blueprint (despesas, recorrências, receitas, cartões, importação, Categorias do Cartão, seguros de financiamento, perfis) recusa perfil NOVO (409). Catálogo global de categorias segue no Flask. Patrimônio, Mobilidade, Documentos e IR: guarda no MVP que liberar a escrita. Migration `20261124090000` (com reversão) aplicada só no Supabase de teste e validada com perfil temporário, 6/6 (§9) (`docs/FIN_ESCRITOR_UNICO_FINAL_1.md`) | Concluído (commit `0af3128`); aplicado e validado no Supabase de teste |
| FIN-CATEGORIAS-RECORRENCIAS-2 | Recorrências semanais e a cada 2 semanas (R1) no gerador do novo aplicativo: identidade por ocorrência, mesmas datas e descrições do Flask, contas do Flask reconhecidas no ciclo, dispensa e exclusão por ocorrência; semanal no cartão recusada (como o Flask). Receitas: valor base, recorrência e reativação da fonte (só as previsões que faltam), recebimento sem previsão (crédito, sem duplicar), data prevista em "Próximos recebimentos". Catálogo global de categorias com escritor próprio (padrão FLASK) e conta gestora: cadastro, edição, exclusão segura e palavras-chave prontos, sem escrita concorrente (guarda no Flask). Migration `20261125090000` (com reversão) aplicada só no Supabase de teste e validada com perfil temporário; catálogo segue com o Flask (§9) (`docs/FIN_CATEGORIAS_RECORRENCIAS_2.md`) | Concluído (commit `053abc9`); aplicado e validado no Supabase de teste |
| FIN-PATRIMONIO-2 | Escrita de Patrimônio no novo aplicativo com escritor único nos dois sentidos (guarda no blueprint do Flask): caixinhas (criar, editar, reativar, inativar), transferências (saldo travado, exclusão que desfaz os saldos, recusada se deixar o destino negativo), bens da Empresa (criar, editar, baixar, criar a partir de documento, vincular documento com histórico, excluir só sem documento), documentos vinculáveis e sugestão a partir de documento. Mesmas linhas que o Flask grava (comparação em cópias idênticas). Exportações ficam para FIN-RELATORIOS-CONFIG-1. Migration `20261126090000` (com reversão) aplicada só no Supabase de teste e validada com perfil temporário (§9) (`docs/FIN_PATRIMONIO_2.md`) | Concluído (commit `a3d8a3b`); aplicado e validado no Supabase de teste |
| FIN-TRANSFERENCIA-AMBIENTE-1 | Transferência do desenvolvimento para o notebook: inventário do estado (47 commits locais fora do GitHub, 37/37 migrations aplicadas no Supabase de teste), manual Windows com fetch local sem push, `scripts/verificar_ambiente.py` (só leitura, sem segredos), roteiros de homologação real versionados em `scripts/homologacao_real/`, contratos da fila em `docs/contratos/fila_2026-10-26/`, `.env.example` atualizado. Push e troca efetiva dependem de autorização (`docs/FIN_TRANSFERENCIA_AMBIENTE_1.md`) | Preparado |
| FIN-INTEGRACAO-1123-1126-1 | Homologação integrada dos MVPs 1123–1126 em bancos descartáveis: nível 3 (Python 1965 aprovados, 5 falhas preexistentes do P7, 1 desmarcado; web unit 30/30; E2E 93/93) e `tests/test_supabase_integracao_1123_1126.py` (I1–I7 aprovados; I8 com 3 `xfail(strict=True)` das escritas do Flask sem guarda). Ordem obrigatória das reversões 1126 → 1125 → 1124 → 1123 (`docs/FIN_INTEGRACAO_1123_1126_1.md`) | Concluído |
| FIN-ESCRITOR-UNICO-GUARDAS-1 | Guarda de escritor nas três escritas do Flask que ficavam sem ela (bloqueadoras da transferência de perfis reais): comprovante → despesa (`ir.py`), confirmar despesa prevista com meio de pagamento, vínculos `PATRIMONIO` de documento fiscal (criar, editar, remover). Mesmo mecanismo e trava (`recusa_escritor_unico`, usada também pela guarda por blueprint); I8 sem `xfail`; nível 2: 1541 aprovados, só as 5 falhas do P7 (`docs/FIN_ESCRITOR_UNICO_GUARDAS_1.md`) | Concluído |
| FIN-MOBILIDADE-2 | Escrita de Veículos/Mobilidade no novo aplicativo (20 funções, escritor único): veículos (criar, editar, converter, excluir com segurança), projeções, regras e manutenção por km, financiamento projetivo do veículo (D-MOB1 corrigido), prévia e ativação de modalidade (cenário ativo no banco, por perfil), assinaturas, transporte por app, confirmar/adiar com ciclo/ignorar previstas. Mesmas linhas que o Flask (11 tabelas). Categorias `MOB_*` nunca criadas pelo novo aplicativo. Guarda nos blueprints de Mobilidade do Flask. Migration `20261127090000` (com reversão) **local, não aplicada no remoto**. Decisão pendente: financiamento do veículo projetivo × motor (`docs/FIN_MOBILIDADE_2.md`) | Concluído localmente |
| FIN-DOCUMENTOS-2 | Escrita de Documentos Fiscais no novo aplicativo (8 funções, escritor único): envio de arquivo guardado no banco e privado do perfil (validações do Flask, duplicidade por SHA-256), revisão, validação, exclusão segura, vínculos (um documento, um bem) e despesa/lançamento a partir do documento sem duplicar (pago pela conta via motor de pagamento; cartão pelo motor de compras). Texto de PDF no navegador (pdf.js); OCR/NFS-e e Documentos da Empresa pendentes. Guarda no blueprint `ir` inteiro. Migration `20261128090000` (com reversão) **local, não aplicada no remoto** (`docs/FIN_DOCUMENTOS_2.md`) | Concluído localmente (parcial) |
| FIN-RELATORIOS-CONFIG-1 | Relatório de bens do Patrimônio (Excel e PDF) gerado no navegador sem biblioteca, **PDF idêntico byte a byte e XLSX igual** ao do Flask (valores, formatos, estilo, larguras); ponte entrega arquivo como send_file. Backup/restauração verificável (`scripts/backup_banco.py`: dump de public/financeiro + documentos + auth.users, manifesto SHA-256, restauração só em banco vazio). Preferências (singleton global no Flask) e demais relatórios (IR, saídas sem documento, ZIP) pendentes (`docs/FIN_RELATORIOS_CONFIG_1.md`) | Concluído localmente (parcial) |
| FIN-BLOCO-A-1 / B-1 / C-1 | Fila de 27/10: integridade e Mobilidade (A), Documentos/Relatórios/Configurações (B), homologação geral, segurança e backup (C). Nível 3 final: **2022 aprovados, 0 falhas**, web unit 30/30, E2E 93/93; as 5 falhas antigas eram de teste (data/ambiente). Ensaio das migrations pendentes 1127/1128 sem alterar dados; auditoria do esquema limpa; CVV/número de cartão em texto puro no Flask (não migrar). Relatórios `docs/FIN_BLOCO_A_1.md`, `FIN_BLOCO_B_1.md`, `FIN_BLOCO_C_1.md`; consolidado `docs/FIN_PREPARACAO_PRODUCAO_1.md` | Concluído (pronto com ressalvas; Bloco D aguarda o titular) |
| FIN-PRE-PRODUCAO-1 | Acabamento antes do Bloco D (origem: `controle_financeiro_dev`): Indexadores (TR mensal), Documentos (vincular/desvincular, um documento em vários bens, Gerar financeiro e "A partir de documento"), cartões no Flask (número mascarado, CVV bloqueado), Preferências por perfil e por usuário, `.claude/settings.local.json` e PDFs pessoais fora do Git; carga seletiva `scripts/carga_supabase.py` com ensaio real em PostgreSQL 17 e 18 (1.521 linhas, conferência OK, origem inalterada, nada sensível), backup/restauração em PostgreSQL 17, 5 migrations pendentes ensaiadas. Doc `docs/FIN_PRE_PRODUCAO_1.md` | Concluído localmente (sem push; migração real aguarda o FIN-BLOCO-D-EXECUCAO-1) |
| PEND-DESPESAS-MOVIMENTOS | **Movimentos do mês e saldos bancários** voltam com a integração de Contas Bancárias (ausência temporária aceita no FIN-FIDELIDADE-DESPESAS-1, P1). Demais dependências P2–P9 no mesmo documento | Pendente (obrigatória) |
| FIN-MIGRACAO-FIDELIDADE-FASE-2 | Telas originais de Despesas, Recorrências, Receitas, Lançamentos, Cartões, Contas Bancárias e Categorias sobre o Supabase; Importar Cartão com prioridade elevada na sequência | Próxima |
| FIN-PAGAMENTOS-1 | Pagamentos, movimentos e saldo bancário (inclui baixa de débito automático) | Ciclo |
| FIN-ESTORNOS-1 | Estornos e correções | Ciclo |
| FIN-CONCILIACAO-1 | Conferência e conciliação | Ciclo |
| WEB-VALIDACAO-1 | Validação do ciclo completo pelo critério de publicação | Ciclo |
| WEB-PROD-1 | Publicação no Cloudflare Pages (substitui o MOBILE-PWA-1) | Após o ciclo |
| MOBILE-PWA-1 | Publicar a consulta no Cloudflare Pages com ícone no celular | Adiado (vira WEB-PROD-1, após o ciclo financeiro) |
| CF-PYTHON-POC-1 | Viabilidade de Flask em Cloudflare Python Workers: possível com ≥7 mudanças estruturais (driver pg8000/Hyperdrive, Python 3.14, shim de scrypt, R2, config por `env`) e 114/128 MB de memória. Não recomendado; manter Render (`docs/CF_PYTHON_POC_1.md`) | Concluído (diagnóstico) |
| BACKUP-DOCS-1 | Backup independente dos documentos do disco (o snapshot diário do Render não substitui). Bloqueador de produção | Alta |
| CLOUDFLARE-1 | `financeiro.kortexbrasil.com` → Render (CNAME, DNS only até o certificado; *Full (strict)* só para o hostname); rate limit em `/login` | Alta |
| DATA-MIGRATE-1 | Migração seletiva de dados e documentos reais para produção | Futuro (autorização específica) |
| STORAGE-2 | Migrar uploads para Supabase Storage (elimina dependência do disco) | Futuro |
| SCHED-1 | Ativar scheduler de geração automática mensal de contas recorrentes | Futuro |

---

## Débitos Técnicos Conhecidos

| Item | Localização | Impacto |
|------|-------------|---------|
| ~~Drift de schema pré-Alembic~~ | ~~6 tabelas + 8 colunas nunca criadas por migration~~ | Resolvido no SUPABASE-MIGRATE-1 (`9e67ec16977b`, `9b8a09ecc52f`) — ver `docs/DEPLOY.md` §6 |
| `lazy='dynamic'` depreciado | `models.py` (~12 relacionamentos) | SQLAlchemy 2.x avisa; futuro erro |
| `datetime.utcnow` depreciado | Múltiplos arquivos (~20 ocorrências) | Python 3.12+ avisa |
| N+1 queries em `to_dict()` | Vários serviços | Performance degradada em listas grandes |
| `Query.get()` legado | Múltiplos serviços | SQLAlchemy 2.0 remove em versões futuras |
| ~~Autenticação ausente~~ | ~~18 rotas de API~~ | Resolvido no SEG-1 (autenticação global, usuário único) |
| `SECRET_KEY` fraca em `.env.local` | `dev-secret-key-local-123456` | Aceitável em `local` por design (bloqueada automaticamente em `staging`/`production` desde o DEPLOY-PREP-1); ainda assim, trocar por valor forte se este `.env.local` for reutilizado em qualquer ambiente exposto |
| CORS irrestrito | `backend/app.py` | Parcialmente corrigido no SEC-0 |
| Dados de cartão em texto puro | `ContaCartao` | Risco de segurança em dados em repouso |
| Scheduler comentado | `backend/app.py:264` | Geração automática de recorrências desabilitada |
| Estorno de transferência entre contas | `ContaBancariaService.gerar_transferencia()` | Não implementado — só estorno de despesa/receita/fatura/financiamento |
| Estorno de ajuste manual de saldo (`origem='AJUSTE'`) | — | Não implementado |
| Conciliação bancária (extrato real × sistema) | — | Não implementada |
| Dependências transitivas não fixadas | `requirements.txt` | O Render instala versões atuais (ex.: pillow, pypdfium2, cryptography), que podem diferir do venv local; avaliar arquivo de lock |
| 5 testes falhando desde antes do deploy | ver `docs/STAGING_RENDER_2.md` §F | Comprovado em `0e04407`; não relacionados a deploy |

---

## Decisões Técnicas Registradas

Estas decisões devem ser mantidas em novas implementações.

1. **Backend soberano**: toda regra financeira fica no servidor; frontend apenas exibe e coleta.
2. **Proteção de histórico financeiro**: dados executados não são alterados silenciosamente.
3. **`ItemDespesa` como cadastro mestre**: nunca apagado automaticamente.
4. **SAC/TR derivado por regra de negócio**: `sistema_amortizacao=SAC` + `indexador_saldo=TR` ativa o motor SAC corrigido pela TR; `modo_calculo_financiamento` é legado transitório.
5. **TR por competência**: `indice_tr_mensal` é a tabela oficial para financiamentos SAC/TR; ausência bloqueia geração/simulação.
6. **Descrição original imutável**: `descricao_original` do lançamento importado nunca alterada.
7. **Categoria do Cartão ≠ Categoria da Despesa**: distinção fundamental, sempre preservada.
8. **Alembic como único caminho de migration**: `flask db migrate` + `flask db upgrade`; scripts custom são legados.
9. **PostgreSQL local como banco oficial de desenvolvimento**: SQLite apenas fallback/legado/teste.
10. **Playwright E2E como barreira de regressão**: smoke deve passar antes de qualquer merge.
11. **Mobilidade usa categorias sistêmicas granulares**: Mobilidade é origem/módulo, não Categoria da Despesa genérica.
12. **Documentos e conferências de financiamento são auditoria**: upload, conferência CAIXA e conferência de quitação não alteram saldo, parcelas, pagamentos ou cronograma.
13. **Botões visíveis = função real**: sem mockups funcionais em produção.
14. **Competência sempre explícita**: nunca inferida de datas de transação ou vencimento.
