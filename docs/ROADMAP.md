# Roadmap — Controle Financeiro

Pendências conhecidas, MVPs planejados e débitos técnicos.

Última atualização: 2026-08-19 (DEPLOY-PREP-1)

---

## Ordem de Trabalho (Prioridade)

```
SEC-0 ✅ → TEST-BASE-1 ✅ → SEG-1 ✅ → DEPLOY-PREP-1 ✅ → SUPABASE-MIGRATE-1 → DEPLOY-HOST-1 → CLOUDFLARE-1 → ICONES-1B → DB-CLEAN-1 → CARD-SEC-1 → FIN-RULES-1 → TEST-FIN-1 → DATA-HYGIENE-1 → PERF-1 → FRONT-ARCH-1
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
| SUPABASE-MIGRATE-1 | Criar projeto Supabase e migrar o banco de PostgreSQL local para Supabase | Alta (depende de DEPLOY-PREP-1, concluído) |
| DEPLOY-HOST-1 | Escolher e configurar host do backend Flask (servidor WSGI de produção) | Alta |
| CLOUDFLARE-1 | Configurar DNS/proxy no Cloudflare apontando para o host do backend | Alta |
| SCHED-1 | Ativar scheduler de geração automática mensal de contas recorrentes | Futuro |

---

## Débitos Técnicos Conhecidos

| Item | Localização | Impacto |
|------|-------------|---------|
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
