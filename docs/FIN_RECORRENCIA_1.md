# FIN-RECORRENCIA-1 — Geração segura de contas recorrentes e faturas

**Data:** 2026-10-21.

**Situação:** implementado e testado **localmente**. Os testes rodaram em cluster PostgreSQL descartável, PostgREST e Playwright, com dados fictícios.

**Não foi feito:**
- aplicar migration no remoto;
- publicar;
- alterar dados reais.

O contrato está em `docs/FIN_RECORRENCIA_1_CONTRATO.md` e substitui a proposta do `10447e1`.

## 1. O que já existia (conferido antes de implementar)

**No Flask:**
- **Geração preguiçosa no GET `/api/despesas/?mes_referencia=`:**
  - recorrências por conta (`gerar_contas_despesa_recorrente`);
  - compras recorrentes no cartão (`gerar_lancamentos_cartao_recorrente`);
  - faturas virtuais (`CartaoService.get_or_create_fatura`);
  - baixa de débito automático.
- **Ao criar uma recorrência:** gera só o primeiro mês.
- **Scheduler:** desligado.

**No novo app:** só leitura.
- `contas_do_mes`;
- o aviso `mes_pode_estar_incompleto`, que continua no banco, mas a tela passou a usar a prévia.

**Financiamentos e consórcios** geram contas por serviços próprios e ficam fora.

## 2. Auditoria: como cada motor reconhece o que já gerou

| Natureza | Flask | Novo motor |
|---|---|---|
| Conta de recorrência | `(item_despesa_id, data_vencimento)`. Uma data diferente (deriva, vencimento editado) **gera outra conta** | `(item, CONTA, competência)`: registro próprio; senão, uma conta do item cujo `mes_referencia` **ou** cujo mês do vencimento seja a competência |
| Compra recorrente no cartão | `compra_id = uuid5(NS, "item-AAAA-MM-01")`. Recurso legado: `(item, mes_fatura, is_recorrente)`, **e grava o `compra_id` no registro antigo** | Mesmo `compra_id` (`extensions.uuid_generate_v5`, igual ao Python) e mesmo recurso legado, **sem alterar o registro antigo** |
| Fatura | `(cartão, is_fatura_cartao, cartao_competencia)`, com filtro de perfil | `(cartão, competência)`, sem filtro de perfil: reconhece mais e nunca duplica |

- A identidade do novo motor fica em `financeiro.recorrencia_competencia`, com situação `GERADA` ou `DISPENSADA`. A chave é **(item, natureza, competência)**.
- Uma conta gerada e depois removida também não volta. `reativar_competencia` desfaz isso.

## 3. O que foi implementado

### 3.1 Migration `supabase/migrations/20261023090000_financeiro_recorrencia.sql`

- **`financeiro.perfil_acesso.pode_gerir`** (D8, a menor extensão segura):
  - `papel = 'TITULAR'` era o padrão e "só informativo", então não comprova gestão;
  - a permissão de gerar passa a ser **explícita**, concedida só por administrador, com padrão `false`;
  - uma restrição impede `LEITOR` com gestão;
  - a função `pode_gerir_perfil` é a porta de escrita.
- **`plano_recorrencia(perfil, mês)`:** função interna e STABLE, sem EXECUTE para o navegador. Classifica cada (item, natureza, competência) como `A_GERAR`, `EXISTENTE`, `DISPENSADA`, `REJEITADA` (com motivo) ou `INATIVA`. Regras:
  - dia contratual via `dia_contratual(competência, dia)`, que usa o dia original ou o último do mês;
  - categoria do cartão como em `resolver_categoria_cartao_para_lancamento`;
  - planejado da fatura como em `calcular_planejado`: só os limites ativos do perfil, com recurso ao orçamento legado.
- **`previa_geracao(perfil, mês)`:** STABLE, para quem pode ler o perfil. Devolve:
  - as quantidades;
  - as competências;
  - se o período é `retroativo` e `extenso`;
  - os itens a gerar, os dispensados e os rejeitados;
  - `pode_gerar`.
- **`gerar_mes(perfil, mês, total_previsto, dispensar)`:** exige gestão. Funciona assim:
  - roda numa única transação, com trava por perfil (`pg_advisory_xact_lock`);
  - **se o plano mudou desde a prévia confirmada, nada é gravado**;
  - o limite é de 500 registros;
  - grava as dispensas que o usuário desmarcou;
  - cria contas, compras e faturas;
  - registra a identidade de cada uma;
  - devolve o relatório e o grava em `financeiro.geracao_execucao`.
- **`reativar_competencia`:** desfaz uma dispensa ou uma remoção.
- **Escrita:** só linhas novas em `public.conta` e `public.lancamento_agregado`. Nenhuma estrutura legada é alterada (sem FK para tabelas legadas). As tabelas novas têm RLS forçada e nenhum privilégio para `anon` e `authenticated`.
- **`create extension if not exists "uuid-ossp" with schema extensions`:** no remoto, a extensão já existe nesse schema. Foi conferido por consulta somente leitura, e o uuid5 remoto é idêntico ao do Python.

### 3.2 Tela (`web/src/contas.html`, `js/contas.js`, `css/app.css`)

- A consulta chama `contas_do_mes` e `previa_geracao`, e nada grava.
- **Aviso discreto:**
  - mostra quantos lançamentos há "a gerar até mm/aaaa" e quantos itens não podem ser gerados;
  - em "Ver itens não gerados", lista os rejeitados e dispensados com o motivo.
- **Botão "Gerar contas":** aparece só quando há algo a gerar e o usuário tem gestão. Quem só lê vê "Somente quem gerencia este perfil pode gerar."
- **Confirmação:**
  - mostra os registros e as competências;
  - alerta quando há lacunas anteriores ao mês;
  - lista cada registro (competência, nome, natureza, vencimento, valor). Desmarcar dispensa a competência; a fatura não é dispensável.
  - botões Confirmar e Cancelar.
- **Resultado:** "Geração concluída: N criadas, N já existentes, N dispensadas, N rejeitadas."
- **Build:** a lista de RPCs separa leitura de escrita. `gerar_mes` é a única escrita e só é permitida em `contas.js`.

## 4. Testes

| Conjunto | Resultado |
|---|---|
| `tests/test_supabase_recorrencia.py` (novo) | **51 passaram + 1 xfail estrito** (o item 6, ver §6) |
| E2E local (Playwright, 390 px), `run_e2e.py` | **29/29** (4 novos em `recorrencia.spec.mjs`; `contas.spec.mjs` ajustado para o novo aviso) |
| Testes unitários do `web/` | 7/7 |
| Suíte completa do repositório | 1167 passaram; só as 5 falhas antigas (§8) |

**O que os testes cobrem** (exigências da seção 5 do contrato):
- mensal e anual;
- inativação, com histórico intacto depois de inativar;
- dia 31 em janeiro, fevereiro, março e abril;
- 29/02/2028;
- `dia_contratual` (8 casos);
- faturas (vencimento, planejado, descrição) e compras (mesmo `compra_id` do Flask, categoria do cartão, legado reconhecido);
- lacunas retroativas sem duplicar existentes (inclusive o vencimento editado);
- dispensa que persiste por várias gerações, com motivo, e reativação;
- conta removida que não é recriada;
- repetição: a segunda chamada não cria nada e não registra execução;
- **concorrência**: duas chamadas simultâneas, uma cria 17 e a outra 0, sem duplicatas;
- prévia desatualizada e dispensa inválida: nada é gravado;
- **rollback**: uma falha injetada no meio desfaz tudo;
- relatório gravado igual ao devolvido, com os ids conferidos;
- nenhuma alteração em `movimento_financeiro`, `conta_bancaria` (saldo) e demais tabelas, e as contas novas ficam `Pendente`, sem data de pagamento;
- registros preexistentes idênticos byte a byte;
- **autorização:**
  - outro usuário, perfil inativo ou inexistente → mesmo erro 42501;
  - `LEITOR` vê a prévia, mas não gera nem reativa;
  - `TITULAR` sem `pode_gerir` não gera;
  - `LEITOR` não pode receber `pode_gerir`;
  - `anon` não executa nada;
  - o navegador não acessa o plano interno, as tabelas novas nem `public.conta`;
  - REST devolve 403.

## 5. Comparação com o Flask (mesmo estado inicial, dois motores)

O Flask real gerou por GET em março/2027 (Pessoal, Empresa e Perfil B); o novo motor gerou a partir de uma cópia idêntica. **Toda** divergência precisa estar classificada, e qualquer outra falharia o teste como regressão. **14 identidades ficaram iguais em todos os campos.** Entre elas:
- perfil NULL do legado;
- débito automático e conta bancária;
- `compra_id`;
- planejado da fatura.

| Identidade | Flask | Novo | Classificação |
|---|---|---|---|
| Conta 31/01: março e abril | 28/03 e 28/04 (deriva) | 31/03 e 30/04 | **Correção D5/D6** |
| Compra no cartão 31/01: março e abril | 28/03 e 28/04 | 31/03 e 30/04 | **Correção D5/D6** |
| Fevereiro com vencimento editado para 15/02 | cria outra conta em 10/02 (**duplicata**) | reconhece a existente | **Correção** (identidade por competência) |
| Recorrência inativa (4 meses) | gera | não gera | **Correção D4** |
| Recorrência que começa em 2028, vista em 03/2027 | gera janeiro/2028 | nada (só até o mês + 1) | **Correção D2** |
| Fatura com vencimento 31 em abril | não cria (o erro é engolido) | 30/04 | **Correção D6** |
| Perfil com um item inválido | desfaz **tudo** do perfil | gera os válidos e rejeita os inválidos com motivo | **Correção D7** |
| Recorrência semanal | gera | rejeitada ("fora do escopo") | **Fora do escopo D3** |

**Nenhuma regressão.** Equivalência com defeitos conhecidos não foi exigida.

**Na ordem inversa (o Flask gerou antes):** o novo motor reconheceu tudo o que o Flask gravou, inclusive a conta de 28/03. Ele criou só a fatura que o Flask não consegue criar (30/04) e nenhuma duplicata. Isso atende aos itens 3 e 4.

## 6. Incompatibilidade: o item 6 exige escritor único

**Evidência** (teste `test_incompatibilidade_documentada…`): depois de o novo motor gerar com uma dispensa, o GET do Flask no mesmo mês:
- **recria a competência dispensada** (Escola, 10/03);
- **duplica as contas corrigidas** (28/03 ao lado de 31/03, e 28/04 ao lado de 30/04);
- volta a gerar a recorrência inativa.

Compras de cartão e faturas **não** duplicam, porque a identidade é a mesma nos dois motores.

**Por que não dá para resolver só no novo motor:**
- o Flask decide pela data e não conhece a dispensa;
- registrar a dispensa como uma "conta" visível ao Flask mudaria totais e listas do sistema atual.

Por isso o teste do item 6 está como **xfail estrito**, e **não declaro equivalência entre os motores**.

**Transição proposta (para decidir):**

| Opção | Como funciona | Avaliação |
|---|---|---|
| **T1. Escritor único por perfil** (recomendada) | Uma marca administrativa por perfil, por exemplo `financeiro.motor_recorrencia(perfil, desde)`. No Flask, uma guarda única no orquestrador `gerar_execucao_despesa_recorrente` e no laço de faturas do GET pula a geração nos perfis marcados. São cerca de 15 linhas e um teste, sem mudar cálculos. | Pequena e reversível, mas **altera o Flask**: exige autorização. |
| T2. Gatilho no banco recusando inserções conflitantes | — | Não recomendo: no Flask uma recusa desfaz o lote inteiro do GET; é frágil e difícil de diagnosticar. |
| T3. Disciplina operacional | Não navegar meses no Flask para perfis que usam o novo motor. | Sem garantia; só como medida provisória. |

**Enquanto não houver escritor único**, o risco se limita a três casos:
- recorrências com dia 29 a 31;
- competências dispensadas;
- recorrências inativas.

E só aparece se o mesmo perfil for usado nos dois sistemas. Como o novo app não está publicado, isso hoje só acontece em teste.

## 7. Pendências para a etapa real (FIN-RECORRENCIA-REAL-1, com autorização própria)

- Push do commit desta etapa.
- Aplicar **apenas** `20261023090000` via `scripts/supabase_migrations.py aplicar --versoes 20261023090000`.
- Conceder `pode_gerir` aos vínculos de teste: o seed `supabase_perfis_seed_teste.py` precisa da coluna.
- Fazer a semeadura fictícia do cenário E2E.
- Incluir as novas funções nas pré-verificações de `run_e2e_real.py`.
- Limpar, conferindo a impressão digital. A limpeza deve remover também as linhas de `financeiro.recorrencia_competencia` e `financeiro.geracao_execucao`.
- Decidir T1, T2 ou T3 antes de qualquer uso misto Flask + novo app no mesmo perfil.

## 8. Suíte completa

**1167 passaram, 19 pulados, 1 xfail (o item 6), 5 falhas** — exatamente as 5 que já falhavam desde `0e04407` (mobilidade/veículos, OCR x2, receitas UX), sem relação com esta etapa. Nenhuma regressão.
