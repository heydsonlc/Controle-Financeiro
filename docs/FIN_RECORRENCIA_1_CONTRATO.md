# FIN-RECORRENCIA-1 — Proposta de contrato (geração de recorrências e faturas)

> Situação: **proposta para aprovação**. Nada foi implementado, nenhuma migration
> foi criada ou aplicada e nenhum dado foi alterado.

## 1. Objetivo

A consulta das contas do mês (`financeiro.contas_do_mes`) já funciona sem o Flask,
mas **as contas recorrentes e as faturas de cartão do mês só existem se o Flask as
gerar** — hoje isso acontece como efeito colateral do `GET /api/despesas/?mes_referencia=`.
Este MVP leva essa geração para uma **operação explícita, transacional, idempotente e
autorizada por perfil** no banco, reproduzindo as regras do Flask.

É o primeiro passo do ciclo financeiro decidido no roadmap (planejar o mês →
registrar → pagar → conferir → corrigir/estornar).

## 2. O que já existe

| Onde | O que há | Situação |
|---|---|---|
| Flask `GET /api/despesas/?mes_referencia=` | Geração preguiçosa de recorrências e faturas + baixa de débito automático | Referência (efeito colateral em GET) |
| Flask `POST /api/recorrencias` e `POST /api/despesas` | Ao criar uma recorrência, gera **só o primeiro mês** | Referência |
| Flask `scheduler.py` / `jobs/gerar_faturas_mensais.py` | Job APScheduler de faturas | **Desligado** no `app.py` |
| `financeiro.mes_pode_estar_incompleto` | Só **sinaliza** que falta gerar (recorrência mensal ativa sem conta no mês ou cartão ativo sem fatura) | Aplicada no remoto |
| `web/` (contas.html) | Mostra o aviso "o mês pode estar incompleto"; **não gera nada** | Local / sem publicação |
| Escrita no novo app | **Nenhuma.** Todas as RPCs atuais são `STABLE` (somente leitura) | — |

Não há nada para reaproveitar do lado novo além do aviso e das regras de autorização
(`pode_acessar_perfil`, regra NULL → Pessoal).

## 3. Regras do Flask a reproduzir (lidas no código)

### 3.1 Recorrência paga por conta (`gerar_contas_despesa_recorrente`, `despesas.py:1409`)

- **R1.** Considera os itens com `recorrente = true` **e `data_vencimento` preenchida**.
  O perfil segue a regra NULL → Pessoal.
- **R2.** A janela começa em `data_vencimento` do item, no dia 1 do mês, e vai até o
  **mês navegado + 1**. Quando o item começa depois do mês navegado, gera só o mês de
  início. Lacunas antigas também são preenchidas.
- **R3.** `mensal`: soma `relativedelta(months=1)` à data anterior, que é a data que
  pode ter sido ajustada. Por isso 31/01 → 28/02 → **28/03** → 28/04… (há deriva do dia).
  `anual`: soma `relativedelta(years=1)`.
- **R4.** A deduplicação é por **(item_despesa_id, data_vencimento)**. Se o usuário
  mudou o vencimento de uma conta gerada ou a excluiu, o Flask **gera de novo** a
  conta da data original.
- **R5.** A conta criada fica assim:
  - `mes_referencia` = mês do vencimento; `descricao` = `item.nome`; `valor` = `item.valor`;
  - `status_pagamento` = `Pendente`;
  - `debito_automatico` = (`meio_pagamento` = `debito_automatico`);
  - `conta_bancaria_id` = `item.conta_bancaria_id`; `observacoes` = `item.descricao` ou `''`;
  - `perfil_financeiro_id` = o do item, **inclusive NULL**.
- **R6.** Tipos `semanal`, `semanal_N_D`, `a_cada_2_semanas` e `dias_semana`:
  - a descrição é `"<nome> - dd/mm"`;
  - existe a **reconciliação** (`_reconciliar_ocorrencias_semanais`): ela **move** contas
    automáticas pendentes para a data esperada e **exclui** as que sobram no ciclo.

### 3.2 Recorrência paga no cartão (`gerar_lancamentos_cartao_recorrente`, `despesas.py:1518`)

- **R7.** Exige `cartao_id` e `categoria_id`; sem eles, lança erro.
  - A data-base é `data_vencimento`, depois `mes_competencia`, depois hoje.
  - Só `mensal` e `anual`.
- **R8.** Cria um `lancamento_agregado` por mês de fatura:
  - `mes_fatura` = mês da data de compra (o `dia_fechamento` **não** é usado);
  - `valor` = `item.valor`; `numero_parcela` = 1 e `total_parcelas` = 1;
  - `is_recorrente` = true; `item_despesa_id` = item; `descricao` = `item.nome`.
- **R9.** É idempotente:
  - `compra_id = uuid5('7f3a1b2c-4d5e-6f7a-8b9c-0d1e2f3a4b5c', f'{item_id}-{AAAA-MM-01}')`;
  - recurso legado: um lançamento com (item, mes_fatura, is_recorrente) e sem `compra_id` recebe o `compra_id` e não é duplicado.
- **R10.** A categoria do cartão vem de `resolver_categoria_cartao_para_lancamento`:
  - usa a `categoria_cartao_id` do item, quando houver;
  - senão, o mapa categoria de despesa → categoria do cartão, e só se a categoria estiver vinculada ao cartão;
  - senão, fica NULL.

### 3.3 Fatura virtual (`CartaoService.get_or_create_fatura`, `cartao_service.py:64`)

- **R11.** No GET, garante a fatura do **mês navegado e do mês seguinte** para cada cartão (`tipo = 'Agregador'`, `ativo`) do perfil.
- **R12.** A deduplicação é por (cartão, `is_fatura_cartao`, `cartao_competencia`).
- **R13.** Exige `config_agregador` (`dia_vencimento`). A fatura criada fica assim:
  - `data_vencimento` = competência com o dia `dia_vencimento`;
  - `valor` = `valor_planejado` = soma dos limites ativos das categorias do cartão (havendo recurso legado de `orcamento_agregado`);
  - `valor_executado` = 0; `status` = `Pendente`;
  - `descricao` = `"Fatura <nome> - mm/aaaa"`; `mes_referencia` = `cartao_competencia` = competência.

## 4. Peculiaridades encontradas no Flask (pedem decisão)

| # | Comportamento atual | Efeito |
|---|---|---|
| Q1 | O GET **não filtra `ativo`** dos itens recorrentes, e "excluir recorrência" só faz `ativo = false` | **Uma recorrência inativada continua gerando contas** ao navegar |
| Q2 | Deriva do dia na recorrência mensal (R3) | Vencimento 31 vira 28 de forma permanente a partir de fevereiro |
| Q3 | Com `dia_vencimento` 29–31, o `replace(day=…)` falha nos meses curtos; o erro é engolido | **A fatura daquele mês não é criada** (só um aviso no log) |
| Q4 | Um único item inválido (ex.: cartão sem categoria) faz a geração **inteira** voltar atrás. Já as faturas fazem `commit` no meio | Gera de forma parcial e imprevisível |
| Q5 | R4: conta excluída ou com vencimento alterado é recriada | O usuário não consegue "pular" um mês |
| Q6 | A baixa automática de débito filtra `perfil_financeiro_id = perfil` | Contas legadas (NULL) do Pessoal não são baixadas — fica para o FIN-PAGAMENTOS-1 |

**Restrição importante:** enquanto o Flask coexistir escrevendo nas mesmas tabelas,
**qualquer diferença na data gerada cria duplicata**. Se a nova função gerar 31/03 e o
Flask gerar 28/03, as duas contas passam a existir. Já gerar *menos* (pular inativos ou
itens inválidos) não duplica nada. Por isso a recomendação é: **mesmas datas e chaves
do Flask**; as diferenças só podem existir no sentido de gerar menos.

## 5. Decisões para aprovar

- **D1 — Gatilho.** **Recomendo:** a função só roda por ação explícita.
  - A tela chama `gerar_mes` ao abrir um mês em que `mes_pode_estar_incompleto` = true e depois recarrega.
  - Um botão "Gerar contas do mês" fica como alternativa manual.
  - Nunca roda dentro de uma consulta (as RPCs de leitura continuam `STABLE`).
  - Agendamento (pg_cron) fica fora.
- **D2 — Janela.** **Recomendo:** igual ao Flask — do início de cada item até o mês pedido + 1, preenchendo lacunas — e a fatura do mês e do seguinte.
- **D3 — Tipos.** **Recomendo:**
  - Neste MVP: `mensal` e `anual` (conta e cartão) e faturas.
  - Os tipos semanais e `dias_semana` (R6) movem e excluem contas. Ficam para o **FIN-RECORRENCIA-2**: a função não os gera e os devolve como "não gerado (tipo não suportado)".
- **D4 — Inativos (Q1).** **Recomendo:** a nova função **respeita `ativo = false`**, porque inativar é a intenção do usuário. Isso diverge do Flask só no sentido de "gerar menos", sem risco de duplicar. O ajuste do Flask fica registrado como pendência, sem alteração agora.
- **D5 — Deriva do dia (Q2) e recriação (Q5).** **Recomendo:** reproduzir exatamente, pela restrição da seção 4. A correção é um MVP futuro, a ser feito nos dois lados ao mesmo tempo.
- **D6 — Vencimento 29–31 (Q3).** **Recomendo:** reproduzir — não criar a fatura e devolvê-la como "não gerada: dia de vencimento inválido no mês". A alternativa é limitar ao último dia do mês; ela não duplica, porque a chave é a competência, mas muda a regra.
- **D7 — Itens inválidos (Q4).** **Recomendo:**
  - pular o item e informá-lo na resposta, sem desfazer o resto;
  - tudo em **uma única transação**, que conclui ou desfaz por inteiro em caso de erro inesperado.
- **D8 — Quem pode gerar.** **Recomendo:** só um vínculo `TITULAR` do perfil (`financeiro.perfil_acesso.papel`); um `LEITOR` recebe 42501. Isso cria a porta `financeiro.pode_alterar_perfil(perfil)`, que será reaproveitada nos próximos MVPs de escrita.
- **D9 — Débito automático.** **Recomendo:** fora deste MVP. A conta nasce `Pendente` com `debito_automatico` = true (como no Flask); a baixa fica para o FIN-PAGAMENTOS-1.

## 6. Desenho proposto (sujeito às decisões)

### 6.1 `financeiro.gerar_mes(p_perfil_id int, p_mes date) returns jsonb`

- `SECURITY DEFINER`, `VOLATILE`, `search_path = ''`; `EXECUTE` só para `authenticated`.
- Autoriza com `pode_alterar_perfil` e devolve o **mesmo erro 42501** para perfil inexistente, de outro usuário ou só de leitura.
- Valida a entrada: `p_mes` vira o dia 1. Recusa meses absurdos (ex.: fora de ±5 anos de hoje) para limitar a janela.
- Concorrência: `pg_advisory_xact_lock` por perfil impede que duas abas gerem ao mesmo tempo.
  - Contra o Flask não há trava comum. A proteção vem da deduplicação pelas mesmas chaves, e o risco que resta (corrida simultânea dos dois) é aceito para uso pessoal e documentado.
- Gera, na ordem:
  1. contas das recorrências mensais/anuais (R1–R5);
  2. lançamentos recorrentes de cartão (R7–R10);
  3. faturas do mês e do seguinte (R11–R13).
- Escreve **somente** nas tabelas `public.conta` e `public.lancamento_agregado`, sem tocar em nenhuma estrutura legada.
- Retorno, sem dados sensíveis:
  `{contas_criadas, lancamentos_criados, faturas_criadas, nao_gerados: [{item_id, motivo}]}`.
- Chamada repetida: zero criações (idempotente).

### 6.2 Front-end (`web/`)

- `contas.js`: se `mes_pode_estar_incompleto`, chama `gerar_mes` uma vez por mês e por sessão e depois recarrega a lista. Mostra um resumo curto do que foi gerado e não gerado.
- Usuário `LEITOR`: mantém o aviso atual, sem gerar.
- A allowlist de RPCs do build ganha `gerar_mes` numa lista separada de **escrita**, para ficar explícito.

### 6.3 O que não muda

- Flask, regras financeiras e GET do Flask continuam iguais.
- Nada de `service_role` no navegador.
- `public` continua fora da Data API.
- Nenhuma escrita direta do navegador em tabela legada; só a RPC autorizada.

## 7. Testes (local, sem Docker, antes de qualquer remoto)

1. **Equivalência com o Flask real.** Dados fictícios com recorrências mensais (inclusive dia 31), anuais, de cartão (com e sem `compra_id` legado), item NULL → Pessoal, lacunas e cartões com e sem `config_agregador`.
   - Base A: o GET do Flask com `mes_referencia`, em subprocesso e com a baixa automática desligada.
   - Base B, partindo do mesmo estado: `gerar_mes`.
   - Comparação, com as diferenças permitidas listadas em D3/D4/D6/D7:
     - conjunto de (item, vencimento, valor, status, débito, conta bancária, perfil);
     - lançamentos (compra_id, mes_fatura, categoria do cartão);
     - faturas (competência, vencimento, valor planejado).
2. **Convivência.** Rodar `gerar_mes` e depois o GET do Flask: o Flask não cria nada (zero duplicatas). E o inverso.
3. **Idempotência.** Duas chamadas seguidas: na segunda, zero criações. Duas chamadas concorrentes: sem duplicata.
4. **Segurança.**
   - Usuário B, perfil de outro, perfil inexistente, `LEITOR` e `anon` são negados com o mesmo erro.
   - Nenhum dado de outro perfil é tocado (fingerprint).
   - As outras tabelas ficam inalteradas.
5. **Transação.** Uma falha injetada no meio não deixa nenhuma criação parcial.
6. **E2E local** (Playwright, 390 px): abrir um mês incompleto → gera → aviso some → totais iguais aos esperados.
7. Suíte completa sem regressão (os 5 testes que já falhavam continuam documentados).

## 8. Etapa real (FIN-RECORRENCIA-REAL-1, autorização separada)

- Push.
- Aplicar **apenas** a nova migration com `scripts/supabase_migrations.py aplicar --versoes <v>`.
- Usar dados fictícios temporários, com a equivalência real e o E2E real.
- Fazer a limpeza com fingerprint final idêntica.
- Sem Cloudflare.

## 9. Fora de escopo

- Recorrências semanais e por dias da semana (FIN-RECORRENCIA-2).
- Baixa de débito automático (FIN-PAGAMENTOS-1).
- Pagamentos, estornos, movimentos e saldo.
- Financiamentos e consórcios: geram contas por serviços próprios (`financiamento_service`, `consorcios`), não por este fluxo; continuam só no Flask e devem aparecer como indisponíveis no novo app.
- Veículos e transporte por app (`despesa_prevista`), OCR e importação.
- Edição de recorrências (cadastro: FIN-DESPESAS-1).

## 10. Autorizações necessárias

1. Aprovar ou ajustar **D1–D9**.
2. Autorizar a **implementação local** (migration nova, front-end e testes), com commit local e sem push.
3. Depois, em separado: push, aplicação da migration no projeto de teste e validação real (seção 8).
