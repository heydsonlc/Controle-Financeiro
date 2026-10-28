# Relatório C — FIN-BLOCO-C-1 (Homologação geral, Segurança e Backup)

Data: 28/10/2026. Contrato: `docs/contratos/fila_2026-10-27/FIN-BLOCO-C-1.md`. Documento consolidado: `docs/FIN_PREPARACAO_PRODUCAO_1.md`.

**Classificação: PRONTO COM RESSALVAS** para planejar a migração real.
- Não há bloqueador técnico de integridade nem de segurança no novo aplicativo.
- As ressalvas são decisões e autorizações do titular, mais funcionalidades parciais de Documentos e Relatórios (§D).

## A. Módulos homologados

**Com escrita no novo aplicativo e escritor único nos dois sentidos:**
- autenticação e perfis;
- contas bancárias;
- receitas e despesas;
- recorrências (mensal, semanal, a cada 2 semanas);
- cartões e faturas;
- pagamentos e estornos;
- financiamentos (motor);
- consórcios;
- patrimônio;
- mobilidade.

**Parciais:**
- Documentos: envio, revisão, vínculos e despesa a partir do documento;
- Relatórios: bens do Patrimônio iguais ao Flask, e faturas.

**Só leitura:** Dashboard.

**Pendentes de decisão:** Preferências.

Os fluxos completos entre módulos estão cobertos por `test_supabase_integracao_1123_1126.py` (I1–I8) e pelos testes de integração de Mobilidade e Documentos (detalhe no §1 do documento consolidado).

## B. Resultado da regressão geral

| Suíte | Resultado |
|---|---|
| Python, nível 3 final | **2022 aprovados, 0 falhas** (1 desmarcado por ler `.env.staging`) |
| Unitários web | **30/30** |
| E2E | **93/93** |

**Falhas antigas (C5):** as cinco falhas antigas foram **todas de teste**, sem mudar regra:
- três dependiam da data: IPVA, supressão de previstas e resumo de receitas;
- duas dependiam do ambiente: `POPPLER_PATH`.

Pela primeira vez a suíte completa não tem nenhuma falha.

**Ensaio das migrations pendentes (C6):** aplicar a 1127 e a 1128 sobre o estado do remoto, com dados de todos os módulos, não altera nenhum dado. Reverter também não, e a reaplicação funciona.

## C. Segurança e backup

**Auditoria do esquema:** com as 39 migrations, não há função `security definer` sem `search_path` (de 354), nada acessível a `anon`, nenhuma tabela sem RLS acessível a `authenticated` e nenhuma coluna sensível de cartão legível.

**Cartões (C2):** o novo aplicativo não grava nem lê CVV, número completo ou validade. **O Flask guarda os três em texto puro** em `config_agregador` e devolve o número completo na API. O Supabase de teste está limpo.

**Git (C3):** nenhum segredo em 408 commits. Ficam dois pontos menores:
- o seu e-mail pessoal está em documentos, já presente no GitHub;
- o `.claude/settings.local.json` está rastreado, sem segredo.

**Frontend:** só a chave publicável, com as RPCs de escrita amarradas à tela que as usa.

**Backup (C4):** `scripts/backup_banco.py`, testado só em bancos descartáveis:
- banco, documentos em arquivo separado e contas de login;
- manifesto SHA-256;
- restauração só em banco vazio, com o mesmo conteúdo do original.

## D. Pendências e bloqueadores

**Bloqueadores de produção, que dependem do titular:**
1. **Origem dos dados reais:** o banco oficial do Flask é o PostgreSQL local `controle_financeiro_dev`, e o `gastos.db` é legado. É preciso confirmar de qual dos dois parte a carga.
2. **Saneamento de cartões:** não levar CVV, número completo nem validade. O tratamento dos dados antigos é destrutivo e precisa de autorização.
3. **Autorizações:**
   - push dos 57 commits;
   - aplicação da 1127 e da 1128 no teste;
   - homologação real;
   - `exportar` contra o Supabase;
   - local seguro dos backups;
   - publicação.

**Decisões:**
- financiamento do veículo: projetivo ou pelo motor;
- Preferências: registro global ou por usuário;
- documento em dois bens pela rota de IR do Flask;
- tirar o `.claude/settings.local.json` do Git.

**Funcionalidades pendentes** (um perfil transferido fica sem elas até serem feitas):
- OCR e interpretação de NFS-e;
- Documentos da Empresa;
- relatórios de IR, de saídas sem documento e o ZIP;
- exportar e importar configurações;
- atalho "A partir de documento" em Despesas.

## E. Commits e migrations

**Commits do Bloco C** (locais, sem push):
- `15bc1d8`: correções de teste e ensaio das migrations;
- este: documentação.

São **57 commits** à frente do GitHub.

**Migrations só locais**, pendentes no remoto: `20261127090000` (Mobilidade) e `20261128090000` (Documentos), ambas com reversão e ensaiadas.

## F. Classificação final

**PRONTO COM RESSALVAS.** O Bloco D não foi iniciado: depende da avaliação e da autorização específica do titular.
