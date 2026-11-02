# Categorias sistêmicas de Mobilidade

## Decisão

O módulo Mobilidade é tratado como origem operacional do lançamento, não como Categoria da Despesa.

Despesas geradas por Mobilidade devem usar categorias sistêmicas granulares conforme a natureza do gasto. A Categoria do Cartão permanece fora deste escopo e continua sendo apenas um agrupamento opcional de fatura.

## Categorias sistêmicas

| Código | Categoria | Abrangência |
| --- | --- | --- |
| `MOB_COMBUSTIVEL` | Combustível | combustível e abastecimento |
| `MOB_SEGURO_VEICULAR` | Seguro Veicular | seguro do veículo |
| `MOB_TRIBUTOS_VEICULARES` | Tributos Veiculares | IPVA, licenciamento e taxas obrigatórias similares |
| `MOB_MANUTENCAO` | Manutenção Veicular | manutenção geral, preventiva ou corretiva, e revisões (REVISAO, REVISAO_GERAL, REVISAO_PROGRAMADA) |
| `MOB_PNEUS` | Pneus | pneus, troca de pneus e alinhamento associado quando aplicável |
| `MOB_USO_VEICULO` | Uso do Veículo | estacionamento, pedágio e custos de uso do carro próprio |
| `MOB_APP` | Transporte por Aplicativo | Uber, 99, táxi e similares |
| `MOB_ASSINATURA` | Assinatura Veicular | carro por assinatura |
| `MOB_LAVAGEM` | Lavagem Veicular | lavagem, higienização e lava-jato |

## Proteção

Categorias sistêmicas são criadas com `sistemica = true`, `modulo_origem = mobilidade`, `bloquear_edicao = true` e `bloquear_exclusao = true`.

O backend deve buscar essas categorias por `codigo_sistema`, nunca por ID fixo nem por nome exibido ao usuário.

## Histórico

Como a base foi zerada antes desta implementação, não houve migração histórica de despesas antigas, contas antigas ou recorrências antigas vinculadas à categoria genérica Mobilidade.

## Consolidação (FIN-CATEGORIAS-CONSOLIDACAO-01)

- `MOB_REVISAO` deixou de ser categoria sistêmica: as revisões usam `MOB_MANUTENCAO` e o tipo do evento continua na regra e na despesa prevista. São 9 categorias obrigatórias.
- Com o catálogo no novo aplicativo (escritor NOVO), o Flask só lê a categoria sistêmica: não cria, não promove pelo nome e não reescreve. Se ela faltar, a operação é recusada (`CategoriaSistemicaAusente`).
- As categorias gerais equivalentes ("Transporte por App", "Manutenção de Veículo") são incorporadas às sistêmicas pela função oficial: docs/FIN_CATEGORIAS_CONSOLIDACAO_01.md.
