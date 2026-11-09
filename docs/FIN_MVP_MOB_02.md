# FIN-MVP-MOB-02 — Projeções dinâmicas de veículos (P13)

**Situação (09/11/2026): publicado (`c3cf1a4`, migration `20261220090000`, deploy `702254dc`).** Auditoria somente leitura aprovada (seção 11).

**Base de produção:** `de5bf20` (60 migrations, última `20261219090000`).

## 1. Diagnóstico da arquitetura atual

Lido sobre o código publicado, com o MOB-01 e o abastecimento no lançamento já aplicados (1215 e 1217).

| Ponto | Situação encontrada |
|---|---|
| `veiculo` | Projeções em colunas fixas: `combustivel_valor_mensal`, `ipva_mes/valor`, `seguro_mes/valor`, `licenciamento_mes/valor` e as categorias de cada uma. O MOB-01 acrescentou Flex, modo do custo (manual ou calculado), km mensal e uso paralelo. |
| `despesa_prevista` | Ocorrências com `obrigacao` + `periodo_referencia` e índice único (MOB-01). Vínculos `conta_id` e `lancamento_id` sem cascata. Status `PREVISTA`, `CONFIRMADA`, `ADIADA`, `IGNORADA` e `SUPRIMIDA`. |
| `mob_gerar_projecoes` | Janela de 12 meses a partir do mês corrente (ou do início do veículo). Combustível mensal e as três anuais, cada uma pela coluna fixa. Atualiza a ocorrência do mesmo período (mesmo id) e só apaga o que ainda é `PREVISTA` na janela. |
| Confirmar, adiar, ignorar | Só sobre `PREVISTA`. Confirmar cria conta ou compra e guarda o vínculo. Adiar move o mês e preserva o período. Ignorar só muda o status. Não existe "desativar" uma projeção: zerar o valor no veículo apagava as futuras. |
| Identidade | Período em que o usuário agiu nunca volta, pela data original e pela data atual. Regerar não troca ids. |
| SIMULADO, ATIVO, uso paralelo | `mob_situacao_uso` e `prevista_financeira`: simulado e fora de uso ficam só nas telas de Mobilidade. A ativação do cenário é exclusiva por perfil. |
| Combustível e recorrência | Com recorrência ativa, as previstas de combustível ficam `SUPRIMIDA`. Confirmar competência coberta é recusado e o custo novo vai só às futuras elegíveis. |
| Categorias | As sistêmicas `MOB_*`, por código, nunca criadas pelo novo aplicativo. |
| Indicadores | Dashboard, saídas sem lastro e `custos_veiculos_tela` leem `despesa_prevista`. `veiculo_flask` soma o total mensal pelas colunas (anual ÷ 12). |
| Manutenção por km | Regras em `veiculo_regra_manutencao_km` e ciclos que geram previstas sem `obrigacao`, pelo uso médio (`mob_km_veiculo`, com hodômetro real). |
| Migrations | Nenhuma restrição impede uma tabela de itens. O índice único de identidade comporta qualquer obrigação nova. |

**O diagnóstico FIN-MOBILIDADE-DIAGNOSTICO-01 continua adequado, com um ajuste.** A tabela `veiculo_projecao` proposta é necessária, mas não basta como cadastro paralelo: ela precisa ser a fonte única, e as ocorrências continuam no motor existente. A identidade do MOB-01 é o que permite converter sem recriar nada, porque cada item novo assume a obrigação das ocorrências já geradas.

**Produção hoje:** um veículo, Carro Heydson (SIMULADO, etanol, custo manual), com combustível de R$ 800,00, IPVA em janeiro (R$ 3.500,00), seguro em dezembro (R$ 3.999,00) e licenciamento em janeiro (R$ 300,00). Tem 15 previstas, todas `PREVISTA`, sem vínculo. Não há recorrência de combustível, cenário ativo, regra de km nem abastecimento.

## 2. Modelo dinâmico

### `financeiro.veiculo_projecao`

| Campo | Regra |
|---|---|
| `id` | Identidade estável do item |
| `veiculo_id`, `perfil_financeiro_id` | Obrigatórios. O perfil é o do veículo. |
| `tipo` | Combustível, IPVA, Seguro, Licenciamento, Pneus, Revisão, Manutenção preventiva, Manutenção corretiva ou Outro. **Fixo depois de criado.** |
| `nome` | Livre, até 80 caracteres. Sem nome, o rótulo do tipo. |
| `categoria_id` | Qualquer categoria ativa. Sem escolha, a sistêmica do tipo. |
| `valor` | Valor de cada ocorrência: por semana no semanal, integral no mês de cobrança no anual. No combustível fica vazio, porque o valor é o do veículo. |
| `frequencia` | Semanal, mensal, trimestral, semestral, anual ou data programada. IPVA e licenciamento são só anuais. |
| `data_inicio`, `data_fim` | Primeira competência ou data, e término opcional (data programada não tem término). |
| `ativo` | Ativa ou inativa |
| `obrigacao` | Origem das ocorrências: `COMBUSTIVEL`, `IPVA`, `SEGURO` ou `LICENCIAMENTO` (as mesmas das ocorrências já geradas) ou `PROJ:<id>` nos itens novos |

- **Novos itens:** nomes personalizados e o tipo Outro dispensam ampliar listas no código.
- **Unicidade:** `(veiculo_id, obrigacao)` é única. Há um só combustível, IPVA, seguro e licenciamento por veículo, e itens novos sem limite.
- **Segurança:** RLS forçada, sem acesso direto do navegador; só as funções gravam, com o escritor único primeiro.
- **Histórico:** `financeiro.veiculo_projecao_historico` registra conversão, criação, edição, ativação, desativação e exclusão, com o antes, o depois, o usuário e a data. Não tem chave estrangeira, para sobreviver à exclusão do item.

### Periodicidade e identidade das ocorrências

| Frequência | Ocorrências | Período (identidade) |
|---|---|---|
| Semanal | A cada 7 dias desde a primeira data | Semana |
| Mensal | Todo mês desde o mês de início | Mês |
| Trimestral | A cada 3 meses desde a primeira competência | Trimestre |
| Semestral | A cada 6 meses | Semestre |
| Anual | No mês de cobrança, com o valor integral | Ano |
| Data programada | Uma, na data | Único: depois de agir, não volta em outra data |

- **Início no passado:** a cadência é mantida. Um trimestral iniciado há 5 meses cai no mês +1, +4 e assim por diante.
- **Frequências do motor:** as que as recorrências financeiras não têm (trimestral e semestral) continuam como previstas com confirmação individual, como pede o contrato.
- **Média mensal:** é só informativa (anual ÷ 12, semestral ÷ 6, trimestral ÷ 3, semanal × 52 ÷ 12). Não gera despesa, e a data programada fica fora dela.

## 3. Tabelas, funções e componentes

**Migration `20261220090000_financeiro_mobilidade_projecoes.sql`**

- **Tabelas novas:** `veiculo_projecao` e `veiculo_projecao_historico`.
- **Funções internas novas (17):**
  - `mob_periodo_frequencia`, `mob_rotulo_tipo_projecao`, `mob_valor_projecao`, `mob_media_mensal_projecao`, `mob_datas_projecao`;
  - `mob_planejar_projecao`, `mob_historico_projecao`, `mob_inicio_anual`, `mob_inserir_projecao`, `mob_converter_legado`;
  - `mob_espelhar_legado`, `mob_projecao_legada`, `mob_projecoes_dinamicas`, `mob_projecao`, `mob_protegidas_projecao`;
  - `mob_projecao_tela`, `mob_dados_projecao`.
- **De tela, só `authenticated` (4):** `projecoes_veiculo_tela`, `salvar_projecao_veiculo`, `alternar_projecao_veiculo` e `excluir_projecao_veiculo`.
- **Substituídas (7), com o texto anterior e os trechos marcados:**
  - `mob_gerar_projecoes` agora percorre os itens, com a mesma janela, identidade, bloqueios e limpeza;
  - `veiculo_flask` tira os totais e a lista dos itens quando há item fora do formato antigo;
  - `criar_veiculo` e `editar_veiculo` convertem e gravam os campos antigos nos itens;
  - `excluir_veiculo` leva os itens e guarda o histórico;
  - `mob_rotulo_prevista` usa o nome do item;
  - `mob_ajustar_ciclo` não abre ciclo por km para ocorrência de item.
- **Sem mudança:** confirmação, adiamento, ignorar, recorrência, troca de modalidade, Dashboard, saídas, abastecimentos e financiamento.

**Tela**

- `web/src/paginas/mobilidade.html`:
  - o modal do veículo perde IPVA, seguro e licenciamento e fica com a seção Combustível;
  - modal novo "Adicionar projeção".
- `frontend/static/js/veiculos.js`:
  - lista de Projeções com os modais;
  - campos antigos só no formulário do Flask;
  - custo pelos itens e ocorrências rotuladas pelo nome.
- `frontend/static/css/veiculos.css`: tabela compacta.
- `web/src/js/mobilidade-adaptador.js`: 4 rotas.
- `web/tests/unit/build.test.mjs`: as RPCs liberadas.

**Área de Projeções do veículo** (botão Projeções): tabela **Despesa | Valor | Periodicidade | Próxima ocorrência | Situação | Ações**, com uma linha por item e "+ Adicionar projeção".

- **Modal:**
  - tipo, nome, valor, categoria, frequência, início e término;
  - campos conforme a frequência: mês para mensal, trimestral, semestral e anual; data para semanal e data programada; data programada sem término;
  - IPVA e licenciamento travados em anual.
- **Ações:** editar, ativar ou desativar e excluir, sempre visíveis, com botões de 32 px. Indisponível aparece desabilitado e com o motivo no título.
- **Regras de manutenção por km:** aparecem na mesma tabela ("A cada 10.000 km"), com acesso ao cadastro próprio.
- **Totais:** média mensal e próximos 12 meses no cabeçalho.

## 4. Regras de integridade

| Regra do contrato | Como ficou |
|---|---|
| Identidade estável e vínculo à origem | O item tem id fixo e a ocorrência tem `obrigacao` (a do item) + período |
| Sem duas ocorrências no mesmo período | Índice único existente e bloqueio pelo período da data original, pelo período gravado e pela data atual |
| Regerar sem trocar ids | A ocorrência `PREVISTA` do mesmo período é atualizada (mesmo id) só se algo mudou |
| Alteração só no futuro elegível | Só `PREVISTA` da janela (desde o mês corrente). Confirmada, adiada, ignorada, suprimida e vinculada nunca mudam. |
| Desativar | Saem só as `PREVISTA` da janela. O item continua no histórico e reativa com as mesmas regras. |
| Excluir | Só sem ocorrência confirmada, adiada, ignorada, suprimida, vinculada ou com registro de ação. Senão, recusa com o motivo e oferece desativar. O combustível nunca é excluído, só desativado. |
| Contas e compras vinculadas | Intactas. Os vínculos ficam na ocorrência confirmada. |
| IPVA sem duplicidade anual | Um IPVA por veículo, sempre anual, e período = ano |
| Combustível e recorrência | O item de combustível usa o valor do veículo e a lógica do MOB-01. Editar o valor passa por `editar_veiculo`, que atualiza a recorrência e as futuras elegíveis. No custo calculado, o valor é recusado e vem da quilometragem. |
| Manutenção por km | Item novo da mesma categoria ou tipo de uma regra de km ativa pede confirmação (`PROJECAO_KM_EXISTENTE`). A ocorrência do item nunca entra no ciclo por km. |
| Rastreabilidade | Histórico por item; nada reescreve despesa paga, saldo ou movimento |

### Quilometragem como frequência (avaliação do item 6)

Não implementada como frequência do cadastro. As regras de km já existentes geram previsões pelo uso real (hodômetro e estimativa entre abastecimentos), e duplicá-las no cadastro criaria duas obrigações para o mesmo serviço. No MVP:
- as regras aparecem na mesma lista, só para leitura e com acesso ao cadastro delas;
- item por competência da mesma categoria de uma regra exige confirmação;
- a ocorrência de item não abre ciclo por km.

**Proposta separada:** transformar a regra de km num tipo de item, com o próprio item como fonte, e migrar as regras existentes. A produção não tem regras, então a migração seria vazia.

## 5. Conversão dos dados

- **Na migration:** para cada veículo com perfil, `mob_converter_legado` cria:
  - o item de combustível, com o valor do veículo;
  - IPVA, seguro e licenciamento anuais, quando há mês e valor (exatamente o que o gerador antigo projetava).
- **Valores do item:** a mesma obrigação das ocorrências já geradas, a categoria sistêmica que o gerador gravava e o mês de cobrança. O início é a primeira ocorrência já gerada, ou a próxima cobrança.
- **Nada mais muda:** nenhuma ocorrência, conta, compra ou coluna do veículo.
- **Leitura de transição:**
  - as colunas antigas do veículo ficam como espelho dos itens anuais, gravadas pelo mesmo caminho;
  - `veiculo_flask` responde exatamente como antes enquanto não há item fora do formato antigo.
- **Um só mecanismo de gravação:**
  - os campos antigos enviados pelo formulário do Flask ou pela tela anterior gravam nos itens;
  - se o item tem outra periodicidade, a gravação é recusada (`PROJECAO_DINAMICA`), nunca sobrescrita.
- **Veículo sem itens** (gravado por outro caminho): é convertido na primeira gravação. A tela mostra os campos antigos como itens provisórios, sem ações.

## 6. Resultados dos testes

Executados em banco descartável, com dados fictícios.

| Bateria | Resultado |
|---|---|
| `test_supabase_mobilidade_projecoes.py` (novo) | 40/40 |
| Mobilidade existentes (integridade, escrita com fidelidade ao Flask, leitura) | aprovados |
| E2E de Mobilidade (8 testes, 2 novos) | 8/8 |
| Unitários do frontend | 92/92 |
| Regressão por impacto (89 arquivos: Mobilidade, Despesas, Recorrências, Cartões, Lançamentos, Dashboard, categorias, escritor único, segurança) | 1.595 casos: 1.572 aprovados, 22 pulados, 1 falha, corrigida e repetida (11/11; ver abaixo) |
| E2E completo, sem novas tentativas | 141/141 |

**Cobertura dos 36 testes obrigatórios:**

| Grupo | Testes |
|---|---|
| Cadastro (1–6) | criação personalizada, edição com ids preservados, desativar e reativar, exclusão sem histórico, recusa de exclusão (ignorada e combustível), vínculo ao veículo e ao perfil, escritor único, validações e repetição da criação |
| Periodicidades (7–14) | semanal, mensal, trimestral, semestral, anual (integral), data programada (fora da janela, reprogramada e travada depois de agir), término (encurtar, alongar e retirar), mudança de competência (mesmo id, ano confirmado sem segundo IPVA), mudança de frequência sem repetir período e início no passado |
| Integridade (15–23) | regerar três vezes sem mudar nenhuma linha, confirmada com conta paga e confirmada no cartão preservadas em editar, reprogramar, desativar e reativar, IPVA único, combustível com a recorrência (sem conta nova e sem prevista voltando a contar), valores financeiros e Dashboard iguais, isolamento por perfil |
| Mobilidade (24–30) | Flex com custo calculado (valor recusado) e manual, combustível único com desativação, simulado fora e ativo dentro do Dashboard, dois veículos em uso paralelo independentes, abastecimento sem mexer nas projeções, regra de km com confirmação e sem ciclo |
| Interface (31–36) | lista compacta com os seis cabeçalhos, modal, campos por frequência, botões do mesmo tamanho (indisponível desabilitado e visível), 1366 e 1920 px sem rolagem, sobreposição nem linha acima de 40 px |
| Categorias | incorporação de uma categoria usada por um item (FIN-CATEGORIAS-CONSOLIDACAO-01): item e ocorrências passam ao destino |
| Transição | campos antigos gravando nos itens, espelho das colunas, leitura com itens novos, conversão equivalente ao gerador antigo em quatro edições, pela lista e pelo campo antigo, reversão recusada com item novo e reaplicação, veículo sem itens convertido na primeira gravação, privilégios e RLS |

**Testes ajustados:**
- Os de reversão da 1215 passam a reverter antes a 1220 (ordem: a mais nova primeiro) e a reaplicá-la depois.
- `test_supabase_categorias_consolidacao.py`: a conferência final procurava as tabelas que apontam a categoria só no esquema `public` e falhou ao encontrar `financeiro.veiculo_projecao`. Passou a usar o esquema de cada tabela.
  - A função de incorporação já descobre as chaves estrangeiras com o esquema.
  - Um teste novo confirma que incorporar uma categoria leva o item e as ocorrências dele para o destino.

## 7. Ensaio na cópia fiel da produção

Cópia descartável, conferida como idêntica à produção (60 migrations).

| Verificação | Resultado |
|---|---|
| Gerador anterior sobre o veículo real | 15 ocorrências, iguais às da produção; nenhuma tabela muda |
| Migration | Só `veiculo_projecao` e o histórico (4 conversões): combustível R$ 800,00 mensal, IPVA R$ 3.500,00 (01/2027), seguro R$ 3.999,00 (12/2026), licenciamento R$ 300,00 (01/2027) |
| Gerador novo | **As mesmas 15 ocorrências: mesmos ids, datas, valores, categorias, status, períodos e metadata, sem atualizar nenhuma linha** |
| Leituras | Veículos, projeções, Dashboard de 11/2026, 12/2026 e 01/2027 e custos por veículo iguais |
| Lista de Projeções | Média mensal R$ 1.449,92 (o mesmo total do veículo hoje); próximos 12 meses R$ 17.399,00 |
| Uso da lista | Pneus semestrais de R$ 1.200,00 geram 01/2027 e 07/2027; editar para R$ 1.350,00 mantém os ids; desativar tira as duas; reativar devolve; excluir remove item e ocorrências |
| Dados financeiros | Contas, compras, movimentos, saldos, recorrências e faturas iguais durante todo o uso |
| Reversão com item novo | Recusada |
| Reversão sem item novo | Previstas e veículo iguais aos de antes da migration; o gerador anterior produz o mesmo |
| Reaplicação | Os mesmos 4 itens; previstas iguais |

**Efeito esperado na publicação:** nenhum valor muda. O Carro Heydson passa a mostrar os quatro itens na lista, com os mesmos números.

## 8. Riscos e ressalvas

- **Mês corrente:** editar ou desativar um item muda a ocorrência `PREVISTA` do mês corrente, como no gerador anterior. Confirmada não muda.
- **Data programada:** é uma por item. Para outra data depois de agir, cria-se outro item.
- **Frequência alterada:** um período em que o usuário agiu bloqueia também o período gravado. Ao voltar de trimestral para mensal, o mês do trimestre confirmado não ganha outra ocorrência.
- **Tela do Flask:** continua com os campos fixos, gravando nos itens pelo mesmo caminho, e não tem a lista. Ambos os perfis usam o novo aplicativo.
- **Entre a migration e o deploy:** a tela publicada continua funcionando. Os campos antigos do modal gravam nos itens e as leituras são iguais.
- **Categoria de item novo:** qualquer categoria ativa do catálogo. A sugestão é a sistêmica do tipo.

## 9. Commits locais

- `454c2fa`: banco (migration `20261220090000`, md5 `ee12726b2257cec1d00739dc0b470762`, LF; reversão e testes)
- `dc02e3e`: tela (lista de Projeções, modal, adaptador e E2E)
- documentação: este arquivo e o ROADMAP

## 10. Prontidão para publicação

Pronto para homologação. Todas as baterias passaram e o ensaio na cópia fiel não mostrou diferença nas ocorrências nem nos dados financeiros. Na publicação:
1. push;
2. aplicar só `20261220090000`, conferindo o hash e as funções;
3. build e deploy do frontend.

A tela nova depende da migration, então a migration vem antes do deploy.

## 11. Publicação e auditoria (09/11/2026)

Autorizada pelo usuário em 09/11/2026 ("FIN-MVP-MOB-02 — Ordem de publicação").

- **Conferências antes do push** (sessão somente leitura):
  - `origin/main` em `de5bf20`; os commits publicados são `b0052a6` (só documentação da P21), `454c2fa`, `dc02e3e` e `c3cf1a4`;
  - produção com 60 migrations, última `20261219090000`; a 1220 era a única pendente; md5 `ee12726b…` e só LF;
  - as 7 funções substituídas estavam em produção idênticas aos textos que a reversão restaura; as 21 funções e as 2 tabelas novas ainda não existiam;
  - veículo e ocorrências iguais aos do ensaio.
- **Ensaio repetido** numa cópia nova e descartável da produção do dia: idêntico ao da seção 6 em todas as partes (geradores, migration, leituras, uso da lista, reversão e reaplicação).
- **Testes antes do push:** 251/251, sem pulados, com o commit `c3cf1a4`. Incluem os 40 do MVP, a consolidação de categorias, a escrita e a integridade de Mobilidade, e os 20 testes de RLS e perfis por HTTP que a regressão por impacto tinha pulado. Nesta rodada eles usaram o PostgREST local.
  - Os outros 2 pulados da regressão (`test_backup_banco`, que pede os binários do PostgreSQL 17) não envolvem projeções.
- **Push** `de5bf20..c3cf1a4`, em avanço direto.
- **Migration `20261220090000`:** aplicada sozinha, com o dry-run listando só o seu arquivo; produção com 61 migrations.
  - Estrutura: 2 tabelas novas com RLS forçada e sem grants da API; 21 funções novas e as 7 substituídas, com os 28 corpos idênticos ao arquivo e `search_path` vazio. Só as 4 funções de tela são executáveis por `authenticated`, e nenhuma execução foi perdida.
  - Dados: 4 itens convertidos, iguais ao ensaio (Combustível mensal, que segue o veículo; IPVA R$ 3.500,00 em 01/2027; Seguro R$ 3.999,00 em 12/2026; Licenciamento R$ 300,00 em 01/2027), e 4 registros CONVERSAO. Nenhum dado das tabelas existentes mudou.
  - Segurança: sem bloqueios.
- **As 15 ocorrências:** idênticas linha a linha (ids 1 a 15, mesmas competências, valores e situação PREVISTA), sem nenhuma adicional. O veículo, a recorrência de combustível e as telas de veículos, projeções e custos ficaram iguais. A lista mostra média mensal de R$ 1.449,92 e R$ 17.399,00 nos próximos 12 meses.
- **Deploy `702254dc`** (build do `c3cf1a4`, Source `c3cf1a4` no Cloudflare): 165 arquivos servidos iguais ao build; navegação anônima sem problemas, com a CSP vigente.
- **Dados (antes e depois, somente leitura):** das 86 tabelas existentes, nenhuma mudou; só as 2 novas têm dados.
  - Contas, compras, 51 movimentos, conta 96 com R$ 84.112,08 e conta 97 com R$ 12.469,48;
  - financiamento, faturas, créditos, abastecimentos e recorrências;
  - Dashboard e contas do mês de 11/2026 a 01/2027 nos dois perfis.
- **Fora do escopo, nada executado:** pagamentos, abastecimentos, reconstrução de faturas, regularizações, consolidação de categorias e a P22.

