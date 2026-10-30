# FIN-RECORRENCIAS-AUTOMATICAS-1 — Geração automática das recorrências ao abrir Despesas

**Situação:** implementada e testada localmente: E2E em banco descartável e homologação numa cópia fiel e descartável da produção. Há commit local, mas não push nem publicação. Nenhuma geração foi feita nos dados reais por script ou teste.

**Regra restaurada (Flask, `backend/routes/despesas.py`, `listar_despesas`):** abrir Despesas ou trocar a competência gera, sem confirmação, o que falta até o mês seguinte:
- **recorrências:** lacunas incluídas, desde o primeiro vencimento de cada uma;
- **faturas:** as dos cartões ativos no mês exibido e no seguinte.

Este contrato substitui a geração explícita do FIN-RECORRENCIA-1: o botão "Gerar contas", a prévia e a confirmação.

## 1. O que mudou

Só o aplicativo (`web/src`). **Nenhuma migration**: o motor do banco é o mesmo.

| Arquivo | Mudança |
|---|---|
| `js/despesas-recorrencias.js` | `gerarRecorrencias(perfil, mes)` faz o que a tela fazia em dois passos, agora sem confirmação: `previa_geracao`, depois `gerar_mes` com o `a_gerar` da prévia e sem dispensas. Se outra aba gerou no meio, o banco recusa a prévia velha ("A prévia mudou") e a geração refaz a prévia (até 3 tentativas). O aviso mostra só: itens rejeitados (com "Dispensar aviso"), perfil gerado pelo sistema atual, perfil somente leitura e falha. O botão e o painel de confirmação saíram |
| `js/despesas-adaptador.js` | A listagem (`GET /api/despesas`) gera primeiro e só depois lê as contas do mês e dos vizinhos. Lista, cards, barra lateral e gráficos já saem com o que foi gerado. Mensagem ao cadastrar recorrência atualizada |
| `js/recorrencias-adaptador.js` | Mensagem: "As contas são geradas automaticamente ao abrir a competência em Despesas." |
| `paginas/contas.html`, `css/app.css` | Sai o painel de confirmação e o CSS só dele |

**O que continua com o banco**, sem mudança:
- autorização (gestão do perfil);
- escritor único: `exigir_gerador_novo`, perfil FLASK recusado;
- trava por perfil: `pg_advisory_xact_lock(20261023, perfil)`;
- reconhecimento dos existentes:
  - contas por item e competência;
  - compras de cartão por `compra_id` determinístico, inclusive as 21 corrigidas no FIN-RECORRENCIAS-POS-MIGRACAO-2;
  - faturas por cartão e competência;
- competências dispensadas: uma conta excluída fica dispensada e não volta;
- rejeição de compra com destino em fatura consolidada;
- histórico (`financeiro.geracao_execucao`).

A tela não dispensa nada sozinha.

**Requisições duplicadas e respostas atrasadas:**
- **Na mesma aba:** `ponte-api.js` atende as chamadas `/api/` uma de cada vez e em ordem. A resposta de uma competência anterior nunca chega depois da selecionada, e duas gerações não rodam ao mesmo tempo. A segunda consulta encontra `a_gerar = 0` e não chama `gerar_mes`.
- **Entre abas:** a trava do banco serializa as gerações. A segunda encontra tudo existente: "nada a gerar", sem erro.

**Falha de rede ou de geração:**
- a lista mostra as despesas já registradas;
- o aviso diz "Não foi possível gerar as recorrências deste mês agora… Recarregue a página para tentar de novo";
- `gerar_mes` é uma transação, então uma tentativa que falha não grava nada.

**Perfil Empresa (FLASK):** `previa_geracao` responde `pode_gerar = false`, e a tela não chama `gerar_mes`. Ela mantém o aviso "A geração deste perfil ainda é feita pelo sistema atual." A atribuição não foi alterada.

## 2. Testes (ambiente descartável)

- **Unitários (`web/tests/unit`):** 30/30. Inclui a lista de RPCs de escrita por arquivo; `gerar_mes` continua só em `despesas-recorrencias.js`.
- **E2E (`web/tests/e2e/run_e2e.py`):** 102/102, com PostgreSQL local + PostgREST e dados fictícios.
  - A base antes da mudança era 98/98.
  - Numa das rodadas intermediárias, um teste de Lançamentos falhou uma vez sem chamar o banco; não se repetiu nas rodadas seguintes.

| Item do contrato | Onde |
|---|---|
| Abertura, até o mês seguinte, mensal, fatura, existente, atualização da página, troca de competência (pelo endereço e pelo filtro) | `recorrencia.spec.mjs` — "abrir Despesas gera ate o mes seguinte…" (recorrência própria em 2040) |
| Conta paga preservada; conta excluída (dispensada) não volta | `recorrencia.spec.mjs` — "conta paga continua paga e conta excluida nao volta" |
| Falha de rede/geração | `recorrencia.spec.mjs` — "falha na geracao…" (`gerar_mes` abortado; lista mantida; recarregar gera) |
| Duas requisições simultâneas | `recorrencia.spec.mjs` — "duas abas…" |
| Resposta atrasada de outra competência | `recorrencia.spec.mjs` — "resposta atrasada…" |
| Perfil FLASK e somente leitura | `recorrencia.spec.mjs` — testes FIN-RECORRENCIA-T1 e de leitura (inalterados) |
| Semanal | `recorrencias_tela.spec.mjs` — "semanal…" (toda quarta, 2036: 4 + 5 ocorrências, depois 4 em maio) |
| Quinzenal | `recorrencias_tela.spec.mjs` — "a cada 2 semanas…" |
| Compra recorrente no cartão (sem duplicar; a já gerada não muda com o novo valor) | `recorrencias_tela.spec.mjs` — "recorrencia no cartao…" |
| Fatura consolidada (compra rejeitada, aviso dispensável) | `pendencia.spec.mjs`, movido para 2041 |

**Efeito nos outros testes:** abrir um mês distante completa todas as lacunas, como no Flask. Por isso:
- os cenários que precisam de meses "virgens" usam 2040 e 2041, depois de todos os meses que os outros specs abrem;
- `contas.spec` e `despesas.spec` passaram a considerar as faturas e recorrências do Perfil B que a abertura gera.

## 3. Homologação em cópia fiel da produção

O script de ensaio foi rodado da pasta temporária da sessão e não faz parte do repositório. Ele faz:
- `pg_dump → pg_restore` num cluster local, apagado no fim, idêntico ao remoto;
- o mesmo algoritmo da tela, como o titular, na sequência 10/2026 → 11/2026 → 12/2026 → 10/2026.

**Estado da produção antes, só leitura:**
- Pessoal no gerador NOVO;
- prévia de 10/2026 com 0 a gerar e 221 existentes;
- 1 execução de geração: as 65 de 10 e 11/2026 já tinham sido geradas pela tela.

| Abertura | Gerado | Detalhe |
|---|---|---|
| 10/2026 | 0 | Tudo existente |
| 11/2026 | 34 | 12/2026: 28 contas, 4 compras no cartão e 2 faturas |
| 12/2026 | 33 | 01/2027: 27 contas, 4 compras no cartão e 2 faturas |
| 10/2026 (de novo) | 0 | Nada novo |

**Resultados:**
- **Horizonte:** nada além de 01/2027, nenhuma competência retroativa, nada pago e nenhum movimento.
- **Preservação** (md5 antes e depois), sem mudança:
  - contas e compras que já existiam;
  - movimentos e contas bancárias;
  - financiamentos e parcelas, consórcios, receitas, recorrências;
  - configuração dos cartões, inclusões em fatura consolidada, dispensas;
  - Empresa e atribuição do gerador.
- **Duplicidades:** nenhuma nova. Segue a única que já existia: "Clube dos Oficiais" 06/2026, herdada do Flask.
- **Regra do Flask:** para cada abertura, todas as ocorrências mensais e anuais que o Flask geraria existem: 113, 129, 145 e 113. As semanais seguem o plano, sem duplicidade por vencimento.
- **Empresa:** `pode_gerar = false`; a chamada direta de `gerar_mes` é recusada (P0001, gerador Flask).

## 4. Disponibilizar a versão

Cada etapa depende de autorização.

1. **Push** do commit deste contrato.
2. **Build:** em `web/`, com as variáveis públicas do projeto (`SUPABASE_URL` e a chave `sb_publishable_…`), rodar `npm run build`. O build recusa chave secreta e confere a ausência de segredos no `dist`.
3. **Publicação:** pelo procedimento já usado, `npx wrangler pages deploy dist --project-name controle-financeiro --branch <ramo autorizado>`, com o acesso protegido. Ver `docs/FIN_PUBLICACAO_PREVIEW_2.md`.
4. **Primeira geração real:** acontece quando o titular abre Despesas na versão nova. Se abrir 10/2026, nada é gerado, porque 10 e 11/2026 já existem. Se abrir 11/2026, são geradas as 34 ocorrências de 12/2026, como na homologação, se nada mudar até lá.
