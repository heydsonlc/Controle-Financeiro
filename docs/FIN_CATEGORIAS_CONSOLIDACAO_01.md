# FIN-CATEGORIAS-CONSOLIDACAO-01 — Consolidação de categorias e dependências do Mobilidade

**Situação (02/11/2026): `FIN_CATEGORIAS_CONSOLIDACAO_01_PRONTO_PARA_HOMOLOGACAO`.** Implementado, testado e ensaiado numa cópia fiel da produção.
- Push, a migration `20261214090000` na produção e a execução das incorporações aguardam autorização.
- Base: diagnóstico FIN-CATEGORIAS-REDUNDANCIA-01 e Adendo 02.

## 1. Incorporações aprovadas (IDs da produção)

| Origem | Destino (ID preservado) | Tratamento |
|---|---|---|
| 96 Transporte por App | **8 Transporte por Aplicativo** (`MOB_APP`) | incorporar |
| 98 Manutenção de Veículo | **5 Manutenção Veicular** (`MOB_MANUTENCAO`) | incorporar; `pneu` vai para Pneus (6) e `lavajato` para Lavagem Veicular (10) |
| 4 Revisão (`MOB_REVISAO`) | **5 Manutenção Veicular** | incorporar depois da correção do Mobilidade |
| 99 Assinaturas | **100**, renomeada **Assinaturas** | incorporar e renomear |

Nenhuma outra categoria é incorporada. As demais categorias sistêmicas continuam, inclusive Assinatura Veicular (`MOB_ASSINATURA`), Uso do Veículo e Estacionamento.

## 2. Mobilidade sem `MOB_REVISAO`

- **Mapeamento:** os eventos REVISAO, REVISAO_GERAL e REVISAO_PROGRAMADA usam `MOB_MANUTENCAO`. O tipo do evento continua na regra por km e no metadata da despesa prevista.
  - Flask: `backend/services/categoria_default.py`.
  - Supabase: `financeiro.mob_categoria_evento`.
- **Lista obrigatória:** são 9 categorias sistêmicas, sem `MOB_REVISAO`.
  - Flask: `CATEGORIAS_SISTEMICAS_MOBILIDADE`.
  - Supabase: `financeiro.categorias_sistemicas_mobilidade()`, usada pela troca do escritor do catálogo e pelos nomes reservados.
- **Helper do Flask:** com o catálogo no novo aplicativo (escritor NOVO), `obter_categoria_sistemica` só lê a categoria.
  - Não cria, não promove pelo nome e não reescreve nome, cor ou descrição.
  - Se a categoria faltar, recusa com `CategoriaSistemicaAusente` e nada é gravado.
  - Antes, só as rotas de categorias tinham a guarda; o helper, chamado por Veículos e Mobilidade, gravava no catálogo.
  - Com o catálogo no Flask (legado), o helper cria as 9 e nunca a "Revisão". `MOB_REVISAO` passou a ser código desconhecido.
- **Seeds e rotinas de inicialização:**
  - `scripts/seed/base_real_1b_seed_categorias.py` usa os nomes das sobreviventes e não recria "Transporte por App", "Manutenção de Veículo", "Revisão" nem "Software e IA".
  - `scripts/regularizar_schema_gastos_sqlite.py` ficou sem `MOB_REVISAO`.
  - A migration Flask `a9b0c1d2e3f4` é histórica e não foi alterada. Ela só roda num banco Flask novo e local; o Supabase não usa o Alembic.

## 3. Incorporação: prévia, hash e execução

**Migration `20261214090000`** (md5 `decd8a32…`), gerada por `scripts/gerar_migration_categorias_consolidacao.py`. Ela não altera nenhum dado.

`financeiro.previa_incorporacao_categoria(origem, destino, opcoes)` é só leitura e exige a conta que administra o catálogo. Ela mostra:
- as referências por tabela: registros, valor e perfis;
- o destino de cada palavra-chave e se ela já existe no destino;
- os vínculos com a Categoria do Cartão;
- os lançamentos por fatura, inclusive se a fatura está paga;
- as recorrências e os bloqueios.

As `opcoes` aceitam `{"renomear_destino": "...", "palavras": {"pneu": 6}}`. O hash cobre a decisão.

`financeiro.incorporar_categoria(origem, destino, opcoes, hash, chave)` executa numa só transação. Qualquer falha desfaz tudo.
1. Trava oficial do catálogo (escritor NOVO e gestor), mais a escrita e a trava de cada perfil com registros.
2. Refaz a prévia e confere o hash.
3. Estende o vínculo com a Categoria do Cartão às categorias que recebem palavras-chave, para o termo continuar no mesmo agrupamento da fatura.
4. Palavras-chave: movidas, ou unidas se já existirem no destino, sem duplicar.
5. Vínculos com a Categoria do Cartão: movidos ou unidos. O mapeamento do IR é unido.
6. As demais referências são reapontadas, descobertas pelas chaves estrangeiras do banco. Só a coluna da categoria muda.
7. Exclui a origem só sem referência restante, nunca em cascata, e renomeia o destino se pedido.
8. Auditoria em `operacao_catalogo`, com a linha da origem, os ids reapontados e a prévia.
9. Idempotente: a mesma chave, ou uma chave nova depois de feita, devolve o resultado anterior. Para outro destino, recusa com `JA_INCORPORADA`.

Bloqueios (a execução recusa):

| Código | Situação |
|---|---|
| `SISTEMICA_OBRIGATORIA` | origem sistêmica ainda obrigatória |
| `DESTINO_INATIVO`, `OUTRO_PERFIL` | destino inativo ou de outro perfil |
| `DESTINO_SISTEMICO`, `NOME_EM_USO`, `NOME_SISTEMICO`, `NOME_INVALIDO` | renomeação recusada |
| `PALAVRA_INVALIDA` | palavra-chave ou destino dela inválido |
| `VINCULO_CONFLITANTE` | a categoria ficaria com duas Categorias do Cartão |
| `PERFIL_SEM_ACESSO`, `PERFIL_NO_FLASK` | registros num perfil que a conta não administra, ou ainda no Flask |
| `RECONSTRUCAO_PENDENTE` | fatura de cartão limpa e ainda não reimportada com compras da origem |

**Script oficial** `scripts/consolidar_categorias.py`:
- tem o plano fixo dos 4 passos e confere a identidade (nome e código) de cada ID antes de tudo;
- `previa` roda em sessão só leitura;
- `executar --hash <hash> --confirmo "INCORPORAR CATEGORIAS"` roda os 4 passos numa transação;
- a repetição devolve o resultado anterior.

## 4. Palavras-chave (destino de cada termo)

| Origem | Termos | Destino |
|---|---|---|
| 96 Transporte por App | 99, corrida, taxi, táxi, transporte app, uber | 8 Transporte por Aplicativo |
| 98 Manutenção de Veículo | autopecas, autopeças, mecanica, mecânica, oficina, oleo, óleo, revisao, revisão | 5 Manutenção Veicular (todos compatíveis: a revisão agora é manutenção) |
| 98 Manutenção de Veículo | pneu | 6 Pneus |
| 98 Manutenção de Veículo | lavajato | 10 Lavagem Veicular |
| 99 Assinaturas | amazon prime, assinatura, disney, max, mensalidade, netflix, prime, spotify, streaming, youtube | 100 Assinaturas |

- Nenhum termo já existia no destino, então não houve duplicidade a unir na produção.
- "netflix" e "streaming" também estão em "Entretenimento". Essa ambiguidade é anterior e não muda: a importação continua pedindo a categoria dessas linhas.
- Pneus (6) e Lavagem Veicular (10) ganham o vínculo com a Categoria do Cartão Mobilidade (58), que era o da origem. Assim, a classificação automática fica igual.

## 5. Ensaio na cópia fiel da produção

A produção foi só lida. A cópia saiu idêntica, com as migrations `20261213090000` e `20261214090000` e os PDFs reais de 11/2026.

| Conferência | Resultado |
|---|---|
| Catálogo na produção | escritor NOVO; o único gestor é o titular |
| 1214 sozinha | nenhum dado alterado (ver 5.1) |
| Referências da origem 96 | 6 palavras-chave e 1 vínculo; nenhum lançamento, recorrência ou previsão |
| Referências da origem 98 | 11 palavras-chave, 1 vínculo e 1 compra (R$ 150,00, Black 11/2026, importada, fatura não paga) |
| Referências da origem 4 | nenhuma |
| Referências da origem 99 | 10 palavras-chave, 1 vínculo (já no destino: unido), a recorrência "TV por assinatura" e as compras de 11/2026; nenhuma em fatura paga |
| Cenário A, janela proibida | depois da limpeza (102 compras, R$ 9.460,65) e antes da reimportação, a 98 é recusada com `RECONSTRUCAO_PENDENTE` |
| Cenário A, consolidação | os 4 passos numa transação depois da reimportação. Todas as tabelas iguais, fora a coluna da categoria; leitura das faturas, Despesas do mês e totais por Categoria do Cartão de todos os meses iguais. Nenhuma referência a 4, 96, 98 ou 99 |
| Classificação automática (antes → depois) | uber 96 → 8, oficina 98 → 5, pneu 98 → 6, lavajato 98 → 10, openai 100 → 100: todas na mesma Categoria do Cartão (58 ou 59). "SUPABASE SINGAPORE" continua reconhecida como recorrência |
| Cenário B | consolidação antes da limpeza: banco preservado. Depois, limpeza e reimportação: as compras voltam com os IDs sobreviventes. Compras, faturas e totais iguais aos do cenário A |
| Nomes finais | 5 Manutenção Veicular, 6 Pneus, 8 Transporte por Aplicativo, 10 Lavagem Veicular, 100 Assinaturas |

O cenário A é a sequência preferencial.

### 5.1 Linha de comando (prévia, execução, repetição)

Ensaio separado, numa outra cópia idêntica, no estado atual da produção (antes da limpeza dos cartões):

| Passo | Resultado |
|---|---|
| `20261213090000` | muda só o que ela cria: a tabela `cartao_vinculado` e a coluna nova, vazia, de `lancamento_agregado` |
| `20261214090000` | **nenhuma tabela muda** |
| `executar` sem confirmação ou com hash errado | recusado; nada muda |
| `previa` | os 4 passos executáveis. 99 tem 7 compras de 11/2026 e a recorrência "TV por assinatura" |
| `executar --hash … --confirmo …` | mudam só `categoria`, `categoria_palavra_chave`, `categoria_cartao_despesa`, a coluna da categoria em `item_despesa` e `lancamento_agregado`, e a auditoria (`operacao_catalogo`) |
| `executar` repetido | devolve o resultado anterior; nada muda |

## 6. Testes

- **`tests/test_supabase_categorias_consolidacao.py`** (11):
  - as quatro incorporações, com histórico (fatura paga, recorrências, previsões) e o banco igual fora a coluna da categoria;
  - classificação no mesmo agrupamento da fatura;
  - duplicidades unidas e execução repetida;
  - bloqueios, prévia mudada e falha com rollback;
  - permissões e perfis;
  - revisão em Manutenção Veicular e legado incorporado sem duplicar;
  - cenário efetivado, alterado e trocado;
  - o Flask não recria nem reescreve;
  - cenários A e B da limpeza e reimportação;
  - reversão e reaplicação; privilégios.
- **`tests/test_categorias_sistemicas_mobilidade.py`:** revisão no Flask (SQLite), com as 9 categorias e sem "Revisão".
- **`tests/test_gerador_migration_categorias_consolidacao.py`** (2).
- **Atualizados para 9 sistêmicas:** `test_migracao_p0p1`, `test_supabase_mobilidade_escrita` e `test_supabase_categorias_recorrencias`.

## 7. Plano para a produção (cada passo com autorização)

Publicação conjunta com o FIN-CARTOES-MULTIPLOS-01 (contrato FIN-CARTOES-CATEGORIAS-PUBLICACAO-01):

1. Push dos commits locais em fast-forward.
2. Aplicar `20261213090000` e depois `20261214090000`, só elas (`aplicar_uma.py`). Nenhum dado muda.
3. Build limpo e deploy do frontend no projeto existente do Cloudflare Pages. Esta consolidação não muda telas, mas o
   pacote de múltiplos cartões, que vai junto, muda Cartões e Importação: publicar as migrations sem o frontend deixaria a
   interface antiga sobre a estrutura nova.
4. Sequência preferencial (cenário A): cartões vinculados → limpeza seletiva de 11/2026 → reimportação dos PDFs →
   pagamentos já realizados → consolidação.
   - Nunca consolidar entre a limpeza e a reimportação; a função recusa.
5. Consolidação:
   - `python scripts/consolidar_categorias.py previa --saida previa.json`;
   - conferir o destino de cada termo e as referências;
   - `executar --hash <hash> --confirmo "INCORPORAR CATEGORIAS"`.
6. Conferir os totais das faturas e de Despesas do mês, a classificação de uma importação de teste, só prévia, e as recorrências.

## 8. Pendências

- A migration Flask `a9b0c1d2e3f4` (histórica) ainda cria a "Revisão" num banco Flask novo. Isso só vale para o ambiente local legado, e nada a usa.
- A ambiguidade de "netflix" e "streaming" entre Assinaturas e Entretenimento é anterior e fica para decisão do titular.
