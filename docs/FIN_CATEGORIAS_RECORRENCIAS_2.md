# FIN-CATEGORIAS-RECORRENCIAS-2 — complementação de Categorias, Receitas e Recorrências

Data: 26/10/2026. Situação: **implementado e testado localmente**. Sem commit, push, publicação ou migration aplicada.

Migration local: `supabase/migrations/20261125090000_financeiro_categorias_recorrencias.sql`.
Reversão: `supabase/reversao/20261125090000_categorias_recorrencias_anterior.sql`.
Ambas foram geradas a partir do texto vigente das funções substituídas.

## 1. Diagnóstico (o que já existia)

| Item do contrato | Antes deste MVP |
|---|---|
| Recorrência semanal e a cada 2 semanas (R1) | Recusada com aviso em Recorrências e em Despesas. O gerador do Supabase só gerava mensal e anual; a identidade era uma linha por recorrência e competência |
| Recorrência no cartão (R2), consórcios (R3) | Já resolvidas (FIN-FIDELIDADE-CARTOES-2 e FIN-CONTRATOS-3) |
| Gerador lendo o cartão como recorrência (R4) | Já resolvido na `20261108090000`. O `FIN_FIDELIDADE_RECORRENCIAS_1.md` ainda o lista como pendente |
| Suspensão e reativação, alterações futuras, geração idempotente, pagamentos preservados | Já existiam para mensal e anual (FIN-RECORRENCIA-1, FIN-DESPESAS-1, FIN-FIDELIDADE-RECORRENCIAS-1) |
| Receitas: valor base, recorrência e reativação da fonte | Recusados pela tela ("continua no sistema atual") |
| Receitas: recebimento sem previsão | Recusado |
| Receitas: data prevista independente da competência | No banco desde FIN-RECEITAS-DATA-REAL-1; a tela original não a mostrava |
| Categorias de despesa: cadastro, edição, exclusão, palavras-chave, logos | Sem escrita no novo aplicativo (catálogo global no Flask) |

## 2. Funcionalidades concluídas

### 2.1 Recorrências semanais e a cada 2 semanas

- **Formato do Flask:** `semanal_N_D`, a cada N semanas no dia D (0 = domingo). O cadastro aceita N = 1 ou 2, como a tela. Os tipos antigos `semanal` e `a_cada_2_semanas` são lidos e gerados.
- **Datas:** a primeira ocorrência é o vencimento levado ao dia da semana; as seguintes vêm a cada N semanas. É a regra do "próximo vencimento" do Flask.
- **Mesmas datas do Flask:** conferido em teste com o Flask real, nos quatro tipos (`semanal_1_3`, `semanal_2_1`, `semanal`, `a_cada_2_semanas`). Datas, descrição (`nome - dd/mm`), competência, valor e situação são iguais.
- **Fase do Flask:** o gerador do Flask só recomeçaria a contagem se chamado com uma janela posterior, caminho que a tela não usa. Aqui a fase é sempre a do primeiro vencimento.
- **Identidade por ocorrência** (`financeiro.recorrencia_ocorrencia`):
  - gerada ou dispensada uma vez, a ocorrência não volta;
  - gerações repetidas ou concorrentes não duplicam;
  - o caminho mensal e anual não mudou.
- **Transição de perfil:** uma conta já gravada pelo Flask em qualquer dia do ciclo (N semanas a partir da ocorrência) é reconhecida. Nada é duplicado.
- **Dispensa na prévia:** vale para a ocorrência, e a tela envia a data. Uma dispensa de semanal sem data é recusada.
- **Excluir uma conta semanal** dispensa só a ocorrência dela. As outras semanas continuam.
- **Alterações futuras:** como no Flask, valem para as próximas contas. As já geradas e as pagas não mudam. Conta paga não é excluída.
- **Suspensão e reativação:** inativa não entra na prévia; reativada, volta com confirmação.
- **Cartão:** o Flask só lança compra recorrente mensal ou anual. A semanal no cartão é recusada no cadastro; se já existir, fica rejeitada na prévia com o motivo.
- **Telas:**
  - Recorrências e Despesas aceitam semanal e a cada 2 semanas.
  - Na prévia de geração, cada ocorrência aparece numa linha.
  - Em Despesas, as semanais aparecem agrupadas, como no Flask.
  - A lista de Recorrências mostra o próximo vencimento igual ao do Flask.
- **Escritor único:** a guarda do FIN-ESCRITOR-UNICO-FINAL-1 continua em `excluir_despesa`. A geração exige o gerador NOVO. Perfil no Flask recusa o cadastro.

### 2.2 Receitas

- **Valor base, recorrência e reativação da fonte** (`redefinir_fonte_receita`). É a regra original do PUT do Flask:
  - grava os valores e cria só as previsões que faltam nos 12 meses a partir do mês atual, pelo valor base;
  - as previsões gravadas nunca mudam, inclusive as futuras e as zeradas por "remover previsão";
  - correção: o Flask criava previsões também para fonte inativa; aqui, só para fonte ativa;
  - reativar é o "ativo" do mesmo PUT; inativar continua pela inativação.
- **Recebimento sem previsão** (`receber_sem_previsao`), no mesmo motor do `receber_receita`:
  - exige o escritor do perfil e uma conta bancária ativa;
  - gera crédito no extrato e atualiza o saldo;
  - a chave impede repetição, e o recebimento é estornável.
- **Não duplica a receita:** com previsão na competência, o recebimento sem previsão é recusado (`TEM_PREVISAO`) e vai pela previsão. Uma previsão criada depois conta esse recebimento.
- **Data prevista:** "Próximos recebimentos" mostra a data gravada na previsão, mesmo em outro mês. Sem data gravada, vale o dia da fonte, como no Flask. A tela de Previsões passa a receber `data_prevista` e `data_prevista_efetiva`.
- **Previsto, realizado e recebido:** os conceitos continuam os do FIN-RECEITAS-1. Recebimento estornado não conta.

### 2.3 Catálogo global de categorias (preparado, sem escrita concorrente)

- **Escritor do catálogo** (`financeiro.catalogo_categorias`):
  - sem linha equivale a FLASK, e nada muda sozinho;
  - só administrador troca, com responsável e motivo (`definir_escritor_catalogo`, sem EXECUTE para o navegador);
  - NOVO só é aceito com as 10 categorias sistêmicas de Mobilidade presentes. O Flask as cria sob demanda e, depois da troca, não poderia mais criá-las.
- **Conta gestora** (`financeiro.gestor_catalogo`, concedida só por administrador). Ter perfil não basta: o catálogo atinge todos os perfis.
- **Escritas:**
  - funções: criar, editar e excluir categoria; criar e remover palavra-chave;
  - exigem catálogo NOVO (senão `CATALOGO_FLASK`, nada gravado) e conta gestora (senão 42501);
  - a trava consultiva `(20261125, 0)` é exclusiva aqui e compartilhada na guarda do Flask.
- **Guarda do Flask** (`backend/services/catalogo_categorias_service.py`, registrada em `routes/categorias.py`):
  - com o catálogo NOVO, as escritas globais respondem 409 `CATALOGO_NOVO` e nada é gravado;
  - consultas continuam;
  - sem a tabela (SQLite ou migration não aplicada), o comportamento é o de antes.
- **Regras do Flask preservadas:**
  - nome único sem diferenciar maiúsculas;
  - categoria sistêmica ou bloqueada não é editada nem excluída;
  - palavra-chave é normalizada (minúsculas, espaços simples) e única por categoria;
  - palavra-chave removida é inativada, e recadastrada é reativada.
- **Correções classificadas:**
  - exclusão recusa qualquer vínculo e lista as tabelas. O Flask só olhava as despesas e falhava com erro 500 nos outros vínculos;
  - cor só no formato `#RRGGBB`;
  - os nomes das 10 sistêmicas ficam reservados. O Flask promoveria a sistêmica uma categoria comum com esse nome.
- **Códigos de Mobilidade:** a lista no banco (`categorias_sistemicas_mobilidade`) é comparada em teste com `CATEGORIAS_SISTEMICAS_MOBILIDADE` do Flask.
- **Tela de Categorias:**
  - as rotas globais chamam as funções novas;
  - enquanto o catálogo estiver no Flask, a mensagem continua "continuam no sistema atual (Flask)… Nada foi gravado";
  - logos continuam recusados com aviso (armazenamento de arquivos: FIN-DOCUMENTOS-2).

## 3. Testes

| Conjunto | Resultado |
|---|---|
| `tests/test_supabase_categorias_recorrencias.py` (novo) | **31 passaram**, detalhados abaixo |
| `tests/test_supabase_recorrencia.py` (comparação com o Flask) | 57 passaram. A divergência "FORA DO ESCOPO D3" do item semanal 908 sumiu: agora é igual ao Flask em todos os campos |
| `test_supabase_gerador_t1`, `gerador_sem_cartao`, `despesas`, `recorrencias_tela`, `recorrencia_cartao`, `receitas`, `receitas_categorias_tela`, `escritor_unico_final` | passaram |
| E2E `recorrencias_tela`, `despesas`, `receitas_tela`, `categorias_tela`, `recorrencia` | 34 passaram |
| Unitários do `web/` | 30 passaram |
| Regressão completa | ver §6 |

O que o teste novo cobre:
- **Semanal:**
  - uma conta por ocorrência no dia da semana, com a descrição do Flask;
  - geração repetida e concorrente sem duplicar;
  - quinzenal com fase fixa entre gerações;
  - dispensa por ocorrência, e a sem data é recusada;
  - excluir uma conta dispensa só a ocorrência;
  - conta paga preservada; alteração vale para as próximas;
  - contas do Flask no ciclo reconhecidas;
  - cartão rejeitado; formatos inválidos recusados;
  - mensal que vira semanal; inativa e reativada;
  - permissões e perfil no Flask;
  - próximo vencimento igual ao `_proximo_vencimento` do Flask;
  - mesmas datas e descrições do Flask nas quatro frequências.
- **Receitas:**
  - só as previsões que faltam, sem mudar as gravadas nem a zerada;
  - recorrência desligada e fonte inativa não criam previsões; reativação completa;
  - versão, escritor e permissão;
  - recebimento sem previsão: crédito, saldo, repetição, previsão posterior descontando, `TEM_PREVISAO`, estorno;
  - escritor, perfil e valor inválido;
  - data prevista na tela.
- **Catálogo:**
  - nasce no Flask e nada é gravado, nem por gestor nem por outra conta;
  - troca exige as sistêmicas, a auditoria e o administrador;
  - códigos sistêmicos iguais aos do Flask;
  - cadastro, edição, nomes únicos e reservados, cor, sistêmicas protegidas;
  - exclusão segura com despesa e com compra histórica;
  - palavras-chave normalizadas, reativadas e únicas;
  - guarda do Flask: grava com FLASK e recusa com NOVO, sem alterar o catálogo.
- **Reversão:** recusada com ocorrências registradas; sem elas, restaura as definições anteriores.

### Testes antigos ajustados (expectativa mudou de propósito)

- **`test_supabase_recorrencia.py`:** os totais incluem as 17 ocorrências semanais do item 908 (segundas de 04/01 a 26/04/2027), que deixou de ser rejeitada. A conferência de duplicidade passou a ser por ocorrência para a semanal.
- **`test_supabase_gerador_t1.py`:** os totais (17 → 34) incluem as mesmas 17 ocorrências.
- **`test_supabase_gerador_sem_cartao.py`:** compara só a regra do R4 com a definição anterior a ele. O item semanal fica fora da comparação; está coberto pelo teste novo.
- **`test_supabase_reversao_lote.py`:** a comparação final ignora as funções do lote 1106–1118 redefinidas por migrations posteriores: `plano_recorrencia`, redefinida aqui. Reaplicar só o lote devolve a definição dele. Na recuperação real, as migrations seguintes são reaplicadas depois.
- **`despesas.spec.mjs`:** saiu o passo "semanal recusada".
- **`recorrencias_tela.spec.mjs`:** a recusa passou a ser "semanal no cartão". Novo teste de a cada 2 semanas pela tela: cadastro, geração agrupada em Despesas, sem duplicar ao reabrir, inativação.
- **`receitas_tela.spec.mjs`:** o valor base é gravado e a previsão de 03/2028 não muda. "Próximos recebimentos" mostra a data prevista de outro mês.

## 4. Dependências e pendências

| Pendência | Encaminhamento |
|---|---|
| **Passar o catálogo ao novo aplicativo** (`definir_escritor_catalogo('NOVO', …)` e `definir_gestor_catalogo`) | Decisão e autorização do titular. Antes: aplicar a `20261125`, conferir as 10 sistêmicas no banco real e decidir quem será gestor. Enquanto houver perfil no Flask, o Flask continua lendo o catálogo; só não grava |
| Logos de categoria | Armazenamento de arquivos (FIN-DOCUMENTOS-2) e migração dos arquivos do disco do Flask |
| **Editar a data prevista na tela de Receitas** | A tela original não tem onde editar uma previsão: o modal "Planejar receita" existe no JS do Flask, mas nenhum botão o abre. Decidir entre um botão na linha e um campo no modal da fonte. O banco já aceita (`criar_receita` e `editar_receita`) |
| **Recebimento sem previsão pela tela** | Na tela original, ele só acontece ao consolidar uma linha "virtual" (fonte recorrente sem previsão no mês), que o titular decidiu não mostrar (FIN-FIDELIDADE-RECEITAS-CATEGORIAS-1 §5.1). A rota e a função estão prontas; falta decidir a entrada na tela. Com o valor base completando as previsões, o caso fica raro |
| Recebimento pontual sem fonte (`/realizadas/pontual`) | Sem entrada na tela original; não implementado |
| Frequência `dias_semana` (legado do Flask) | Continua "fora do escopo" na prévia; nenhum cadastro atual a usa |
| `mes_pode_estar_incompleto` (aviso de mês incompleto) | Considera só a mensal. A prévia de geração mostra as semanais a gerar |
| Reativar uma ocorrência semanal dispensada | `reativar_competencia` só trata da competência mensal, e nenhuma tela usa essa função |
| Falha preexistente `test_categorias_sistemicas_mobilidade` (projeção de IPVA) | É de Mobilidade (FIN-MOBILIDADE-2), não do catálogo |
| `FIN_FIDELIDADE_RECORRENCIAS_1.md` | R1 resolvido aqui. R4 já estava resolvido pela `20261108` (o documento antigo não foi atualizado) |

## 5. Migration (não aplicada)

`20261125090000_financeiro_categorias_recorrencias.sql`:
- **Tabelas novas, vazias, com RLS forçado e sem acesso direto:** `recorrencia_ocorrencia`, `catalogo_categorias`, `gestor_catalogo`, `operacao_catalogo`.
- **Funções novas:**
  - da semanal (internas);
  - `redefinir_fonte_receita` e `receber_sem_previsao`;
  - as do catálogo; as de troca e de gestor ficam sem EXECUTE para o navegador.
- **Substituídas:** seis funções, pelo texto vigente com trechos marcados: `plano_recorrencia`, `gerar_mes_interno`, `ler_dados_despesa`, `excluir_despesa`, `recorrencias_do_perfil` e `receita_orcamento_flask`.
- **Dados:** nenhum dado existente é alterado.

A reversão restaura as seis funções e remove o resto. Ela recusa se já houver ocorrência semanal registrada ou se o catálogo estiver no novo aplicativo.

**Ordem:** depende da `20261124` (escritor único), que por sua vez segue a `20261123`.

## 6. Regressão

Regressão completa ao fim (com as migrations `20261125` e `20261126` no cluster):
- **Python, pasta `tests/` inteira:** 1942 aprovados, 20 pulados, 5 falhas. As 5 são as preexistentes do P7, sem relação com esta entrega: `test_receitas_ux`, `test_categorias_sistemicas_mobilidade`, `test_ocr_tools` (2) e `test_veiculos_mobilidade_2b`. A contagem veio das marcas de progresso, porque o resumo final do pytest não foi gravado no arquivo.
- **E2E completo:** 93 aprovados.
- **Unitários do `web/`:** 30 aprovados.

## 7. Riscos

- **Volume da prévia:** uma semanal antiga, cadastrada no Flask e nunca gerada, entra na prévia desde o primeiro vencimento, como a mensal. A prévia marca "extensa", e a confirmação permite dispensar. O limite de 500 registros por geração continua.
- **Troca do catálogo:** depois dela, o Flask não cria categorias. Uma rotina do Flask que precisasse criar uma sistêmica nova (fora das 10) falharia. A troca exige as 10 presentes, e a lista é conferida em teste.
- **Valor base:** cada edição de fonte recorrente e ativa completa as previsões que faltam nos 12 meses seguintes, como no Flask. Previsões "removidas" são zeradas e não voltam.

## 8. Arquivos (separação por MVP)

Só deste MVP:
- **Migration e reversão:** `supabase/migrations/20261125090000_financeiro_categorias_recorrencias.sql`, `supabase/reversao/20261125090000_categorias_recorrencias_anterior.sql`.
- **Flask:** `backend/services/catalogo_categorias_service.py`.
- **Testes:** `tests/test_supabase_categorias_recorrencias.py`, `tests/test_supabase_recorrencia.py`, `tests/test_supabase_gerador_sem_cartao.py`, `tests/test_supabase_reversao_lote.py`.
- **Web:**
  - adaptadores: `web/src/js/recorrencias-adaptador.js`, `despesas-adaptador.js`, `despesas-recorrencias.js`;
  - Receitas e Categorias: `receitas-adaptador.js`, `receitas-adaptacoes.js`, `categorias-adaptador.js`;
  - specs: `web/tests/e2e/receitas_tela.spec.mjs`.
- **Doc:** `docs/FIN_CATEGORIAS_RECORRENCIAS_2.md`.

Compartilhados com o FIN-ESCRITOR-UNICO-FINAL-1 (trechos separados, cada um com a marca do seu MVP):
- `backend/routes/categorias.py`: bloco do catálogo depois do bloco do escritor;
- `tests/test_supabase_gerador_t1.py`;
- `web/tests/e2e/despesas.spec.mjs` e `recorrencias_tela.spec.mjs`;
- `web/tests/unit/build.test.mjs`;
- `docs/ROADMAP.md`: uma linha por MVP.
