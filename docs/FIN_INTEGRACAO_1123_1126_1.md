# FIN-INTEGRACAO-1123-1126-1 — Homologação integrada dos MVPs 1123 a 1126

Data: 27/10/2026. Computador de casa, só bancos descartáveis e dados fictícios. **Resultado: homologação integrada aprovada.**

Ficaram de fora: correções funcionais, migrations, Supabase remoto, perfis reais, push e publicação.

| MVP | Migration |
|---|---|
| FIN-FINANCIAMENTOS-MOTOR-1 | `20261123090000` |
| FIN-ESCRITOR-UNICO-FINAL-1 | `20261124090000` |
| FIN-CATEGORIAS-RECORRENCIAS-2 | `20261125090000` |
| FIN-PATRIMONIO-2 | `20261126090000` |

## 1. Etapa 1 — Diagnóstico (só leitura)

**Estado:**
- 47 commits locais à frente do GitHub (`9a50410`);
- 37/37 migrations aplicadas no Supabase de teste.

**Guardas no esquema:** 80 das 82 funções de escrita liberadas ao usuário passam pela guarda de escritor. As duas restantes são a gestão de perfil (`criar_perfil`, `definir_perfil_padrao`), fora da guarda por decisão.

**Riscos encontrados:**
1. Três escritas do Flask sem guarda de escritor: comprovante → despesa, confirmar despesa prevista, vínculos de documento.
2. Reversão da 1124 sem conferência de ordem.
3. Concorrência entre módulos sem teste.

**Patrimônio sem vínculo com conta bancária:** é o modelo do Flask. Fica como está, por decisão do titular.

## 2. Etapa 2 — Resultados

### Regressão completa (nível 3)

| Suíte | Resultado |
|---|---|
| Python | **1965 aprovados**, 5 falhas preexistentes, 0 pulados, 1 desmarcado (31 min) |
| Unitários do `web/` | **30/30** |
| E2E | **93/93** (3,4 min) |

**As 5 falhas são as do P7** (`docs/DEPLOY_READY_FIN_1.md`), conferidas por identidade e causa:
- `test_ocr_tools` (2): o Poppler está instalado e o teste supõe que não;
- `test_categorias_sistemicas_mobilidade`: `KeyError: 'IPVA'`, uma projeção que depende da data atual;
- `test_receitas_ux` e `test_veiculos_mobilidade_2b`: código não alterado desde `a3d35b2`.

**Teste desmarcado:** `test_verificar_ambiente.py::test_saida_nao_contem_valores_dos_arquivos_locais`. Ele lê o `.env.staging` localmente, e o contrato proibia o acesso a esse arquivo.

### Testes integrados

Arquivo `tests/test_supabase_integracao_1123_1126.py`.

**Resultado:** 14 aprovados e 3 `xfail(strict=True)`, iguais em quatro execuções (três diretas e uma pelo seletor de nível 2), cerca de 2,4 min cada.

| Cenário | O que prova |
|---|---|
| I1 | Ciclo no mesmo perfil, sem perder pagamentos, saldos ou histórico (detalhe abaixo) |
| I2 | Regra atual do motor para estorno e amortização (detalhe abaixo) |
| I3 | Guarda de escritor nos dois aplicativos (detalhe abaixo) |
| I4 | Alternância Flask → novo → Flask: só o escritor da vez grava; histórico e trocas registrados |
| I5 | Três perfis (A e B no novo, C no Flask): 13 tentativas cruzadas recusadas, nenhum perfil alterado |
| I6 | Concorrência entre módulos, sem bloqueio nem impasse (detalhe abaixo) |
| I7 | Reversão em ordem inversa = esquema até `20261122`; reaplicação = esquema completo, e tudo funciona |
| I8 | Três escritas do Flask sem guarda: controles passam no perfil do Flask; o comportamento exigido fica em `xfail(strict=True)` |

**I1 — operações no mesmo perfil:**
- semanal e quinzenal geradas;
- financiamento do motor;
- pagamentos pela conta bancária;
- edição do valor da recorrência e nova geração;
- amortização;
- transferências de patrimônio.

**I1 — conferências:**
- contas pagas, movimentos e parcela paga com o mesmo md5;
- nenhuma duplicidade;
- saldo bancário igual aos movimentos;
- transferências de patrimônio sem movimento bancário;
- saldos do patrimônio conservados;
- outros perfis intactos.

**I2 — regra atual do motor:**
- amortização com parcela protegida depois da data: recusada (`PARCELA_PROTEGIDA`), sem gravar;
- amortização depois da última protegida: permitida;
- o estorno não tira a proteção;
- regeneração com parcela paga: recusada (`COM_EXECUCAO`), igual ao Flask.

**I3 — guarda nos dois aplicativos:**
- **Novo aplicativo:** toda função de escrita, chamada contra perfil do Flask, recusa pelo escritor (`SISTEMA_FLASK`, `GERADOR_FLASK`, `CATALOGO_FLASK`) sem gravar nada.
- **Flask:** toda rota de escrita guardada responde 409 `SISTEMA_NOVO` em perfil do novo aplicativo, fora as isenções do código.

**I6 — concorrência entre módulos:**
- pagar parcela × amortizar;
- gerar mês × excluir semanal;
- 12 transferências cruzadas simultâneas;
- troca de escritor × escrita: uma espera a outra.

### Integridade

- **`gastos.db`:** md5 inalterado.
- **PostgreSQL local persistente:** os 8 bancos estão idênticos antes e depois, com os mesmos contadores de escrita e o mesmo conteúdo.
- **Supabase remoto:** sem alteração, conferido só com leitura. Continua com 37/37 migrations, Pessoal e Empresa no Flask e o catálogo no Flask.

## 3. Ordem obrigatória das reversões

As reversões só podem ser aplicadas nesta ordem:

**1126 → 1125 → 1124 → 1123**

**Atualização (FIN-MOBILIDADE-2):** a `20261127090000` (escrita de Mobilidade) usa `exigir_escrita_novo`, da 1124, e por isso é revertida **antes** de todas: **1127 → 1126 → 1125 → 1124 → 1123**. O cenário I7 cobre a cadeia completa.

Os arquivos ficam em `supabase/reversao/`. A reaplicação é em ordem crescente: 1123 → 1124 → 1125 → 1126.

A reversão da 1124 **não confere a ordem**. Se for aplicada com a 1125 ou a 1126 ainda presentes:
- remove `financeiro.exigir_escrita_novo`, que as escritas da 1125 e da 1126 chamam, e essas escritas passam a falhar;
- devolve `excluir_despesa` à versão anterior à 1125, sem o tratamento da semanal.

**Por isso, reverter a 1124 exige reverter antes a 1126 e a 1125.** A ordem inversa foi provada no cenário I7.

## 4. Observações

- Nove funções do novo aplicativo validam a entrada antes da guarda: pagar e estornar, receber, transferir entre contas, criar conta bancária. Não gravam nada; com dados válidos, recusam pelo escritor.
- O Flask grava metadados de perfil mesmo com o perfil no novo aplicativo:
  - "tornar padrão" (exceção documentada) regrava `updated_at` dos perfis;
  - `obter_ou_criar_perfis_iniciais` preenche avatar, tipo e cor quando estão vazios.

  Nenhum dos dois toca dado financeiro.

## 5. Pendência bloqueadora

As três escritas do Flask do I8 bloqueiam a transferência de perfis reais. A correção é o FIN-ESCRITOR-UNICO-GUARDAS-1.
