# FIN-MULTIUSUARIO-SEGURANCA-01 — Propriedade dos perfis, isolamento entre usuários e testes permanentes

**Situação:** implementado e ensaiado **localmente** em 17/11/2026, no ramo `multiusuario-seguranca-01` (a partir da `main`
publicada). **Nada em produção:** sem push, sem deploy, migration `20261231090000` **não aplicada**, nenhum registro alterado.
A publicação depende de autorização do titular (seção 9).

Primeira etapa da arquitetura para vários usuários. Não cria cadastro de usuários, convites nem personalização de catálogos
(ficam para FIN-MULTIUSUARIO-ACESSO-01 e FIN-CADASTROS-PADRAO-01). O relatório de segurança completo, com as sondas, fica na
área privada de auditorias, fora do repositório.

## 1. O que muda

| Tema | Antes | Depois |
|---|---|---|
| Dono do perfil | não havia; a posse era só o vínculo de acesso | cada perfil tem dono (`perfil_financeiro.user_id`, usuário do Supabase Auth), fixo depois de definido |
| Quem administra | quem tinha o vínculo de administração | o vínculo **e** a posse: só o dono administra o perfil |
| Nome do perfil | único no aplicativo; "Pessoal" reservado | único **por dono**, sem diferença de maiúsculas ou de espaços; nenhum nome é reservado |
| Perfil padrão | um só no aplicativo | um por dono; escolher o seu não toca no dos outros |
| Registro antigo sem perfil | pertencia "ao perfil chamado Pessoal" | pertence ao perfil apontado por uma guarda explícita (por identificador). Nenhuma função decide posse pelo nome |
| Índices de TR | qualquer usuário que administrasse um perfil podia alterar | leitura para todos; manutenção só do administrador da plataforma, com a auditoria de sempre |
| Ordem das recusas | três funções validavam os dados antes da autorização | autorização primeiro |
| Testes | sondagem avulsa do diagnóstico | suíte permanente de isolamento, parte da regressão |

O que **não** muda: a autorização de leitura continua em `financeiro.perfil_acesso`; nenhuma tabela ganhou permissão direta;
nenhuma regra financeira, valor, saldo, pagamento ou identificador foi alterado; o catálogo de categorias e as palavras-chave
continuam globais.

## 2. Migration `20261231090000` (nenhum registro financeiro é alterado por ela)

Gerada por `scripts/gerar_migration_multiusuario_seguranca.py` (não se edita à mão; `--verificar` confere o arquivo versionado).

- **Dono:** coluna `user_id` em `perfil_financeiro`, preenchida pelo titular que já administra cada perfil (a migration recusa
  se algum perfil tiver mais de um administrador). Gatilhos: o dono não muda; um segundo administrador é recusado; o primeiro
  vínculo de administração define o dono de um perfil que ainda não o tem (cargas e cenários de teste).
- **Nomes e padrão:** sai a unicidade global do nome; entram os índices únicos por dono (nome normalizado; um padrão por dono).
  `criar_perfil`, `atualizar_perfil`, `definir_perfil_padrao`, `aplicar_perfil_padrao` e `reativar_perfil` passam a agir só entre
  os perfis do próprio dono. A resposta "já existe perfil com este nome" só considera os perfis de quem pede.
- **Guarda dos registros sem perfil:** tabela de linha única `financeiro.guarda_sem_perfil`. Recebe, uma única vez, o perfil que
  cumpria esse papel pela regra anterior; a partir daí a regra é por identificador. 22 funções que comparavam o nome do perfil
  foram reescritas por substituição conferida do texto vigente (nenhuma outra linha delas muda).
- **Administrador da plataforma:** `financeiro.administrador_plataforma`, com a conta que já administrava o catálogo. Só mantém
  referências globais (hoje, os índices de TR). **Não dá acesso a dados financeiros de ninguém.** A concessão é ato
  administrativo (função não executável por usuários).
- **Ordem das recusas:** `anular_abastecimento`, `corrigir_abastecimento` e `criar_despesa_paga`.
- **Auditoria da regularização:** tabela `financeiro.regularizacao_perfil`.

Reversão: `supabase/reversao/20261231090000_multiusuario_seguranca_anterior.sql`, gerada junto. Devolve as 33 funções ao texto
anterior e retira a estrutura nova. É **recusada** quando a volta não é segura: regularização não revertida, perfis de donos
diferentes com o mesmo nome, mais de um perfil padrão, ou guarda diferente da que a regra antiga daria.

## 3. Itens de despesa sem perfil

Roteiro `scripts/regularizar_itens_sem_perfil.py` (`previa` em sessão somente leitura → `executar` → `reverter`).

- A posse de cada item é **demonstrada pelos vínculos do próprio registro**: contas e compras ligadas a ele e, na parcela de
  consórcio, os contratos a que ela corresponde. Todas as evidências têm de apontar o mesmo perfil, que tem de ser o informado
  e ter dono. O nome do perfil não é critério.
- Item sem evidência, ou com evidências divergentes, **não é atribuído**: é listado para decisão.
- Só a coluna do perfil do item muda. A execução exige a impressão (SHA-256) da prévia conferida e a confirmação literal, grava
  a auditoria e é reversível (a reversão confere que cada item volta exatamente ao que era).
- A guarda **não é retirada nesta etapa**: o catálogo de categorias é global (sem perfil) e ainda é lido por ela numa tela
  fiscal. O passo `retirar-guarda` existe e é recusado enquanto isso; fica para o FIN-CADASTROS-PADRAO-01.

## 4. Suíte permanente de isolamento

`tests/test_supabase_isolamento_usuarios.py` + `tests/isolamento_cenario.py`, em PostgreSQL local descartável.

Cenário: dois usuários independentes, cada um dono de um perfil "Pessoal" e de um "Empresa" (nomes iguais), com um registro
marcado em cada tabela de dados do perfil, em todos os módulos.

| Teste | O que garante |
|---|---|
| Perfil alheio | toda função exposta que recebe perfil recusa o perfil de outro usuário, antes de validar os dados |
| Registro alheio | no próprio perfil, com o identificador de um registro do outro em cada parâmetro: recusa ou não encontra; nenhuma resposta traz dado do outro; nada dele muda |
| Sem sessão | nenhuma função executável por anônimo; nenhuma tabela legível ou gravável diretamente |
| Positivos | nomes iguais entre usuários e únicos por dono; padrão de cada um; operações legítimas; dono fixo |
| Tentativas específicas | 24 tentativas com dados completos e gravando de verdade (pagar, estornar, usar conta ou cartão de outro, documento, financiamento, consórcio, receita, veículo, conta bancária): todas recusadas; o retrato dos dados do outro fica idêntico |
| Índices de TR | usuário comum não altera; administrador mantém e não enxerga dado financeiro de ninguém |
| Registro sem perfil | não vai para quem tem um perfil chamado "Pessoal"; nenhuma função compara o nome |

**Cobertura efetiva.** Uma chamada que para na validação dos dados não prova nada. Por isso, no teste de registro alheio o
próprio dono repete cada chamada: só conta como cobertura efetiva quando o resultado do dono difere da recusa dada ao outro.
As funções que ainda não alcançam essa prova ficam registradas em `tests/isolamento_sem_cobertura.json` (só a impressão de cada entrada; a lista legível fica no relatório privado); uma função nova que caia
nessa situação faz a suíte falhar até ser avaliada. A lista não é um atestado de segurança dessas funções: é o que falta provar.

## 5. Ensaio na cópia fiel da produção

`scripts/ensaio_multiusuario_seguranca.py`: restaura um backup novo num banco local descartável e mede, a cada passo, o retrato
de todas as tabelas e **todas as leituras de tela do titular** (toda função de leitura exposta que só pede perfil e mês, nos
dois perfis).

| Passo | Resultado |
|---|---|
| Migration | nenhuma tabela de dados muda; todas as leituras idênticas; cada perfil com dono; um padrão por dono |
| Regularização | todos os itens sem perfil com posse demonstrada, nenhum divergente; só a coluna do perfil dos itens muda; leituras idênticas |
| Reversão completa | banco idêntico ao inicial (todas as tabelas) e leituras idênticas às iniciais |
| Segundo usuário fictício | cria perfis com os mesmos nomes dos do titular; todas as leituras nos perfis do titular recusadas; conta começa vazia; não altera TR; não paga com a conta bancária do titular |
| Cadastro com pagamento imediato | funciona para o titular (despesa paga, saldo debitado), desfeito ao final |

Resultado: **39 verificações, nenhuma falha**, sobre um backup de 17/11/2026 com 70 migrations; 207 leituras de tela medidas em cada passo.

## 6. Testes

| Verificação | Resultado |
|---|---|
| Suíte de isolamento | 10/10 (920 chamadas com perfil alheio; 166 pares função/parâmetro com registro alheio, 123 com cobertura efetiva; 24 tentativas específicas) |
| Roteiro de regularização e gerador | 3/3 |
| Regressão de banco completa | **1.430 aprovados, 20 pulados, 0 falhas** (76 arquivos) |
| Unitários do frontend | 131/131 |
| Suíte e2e completa | **289/289** (2 testes novos: usuário comum não altera a TR; padrão de um usuário não muda com o do outro) |

## 7. Frontend

Uma mensagem nova (manutenção de TR restrita ao administrador). Nenhuma tela muda para a conta atual.

## 8. Riscos residuais e o que fica para os próximos MVPs

1. A guarda continua existindo (aponta um perfil por identificador) até o catálogo de categorias ter dono próprio.
2. Catálogo, palavras-chave e natureza gerencial continuam globais; a reclassificação e a incorporação de categorias seguem
   sendo ferramentas do gestor do catálogo (FIN-CADASTROS-PADRAO-01).
3. Não há cadastro, convite nem recuperação de acesso; o cadastro público segue desligado (FIN-MULTIUSUARIO-ACESSO-01).
4. O vínculo de leitura de um perfil por outro usuário continua possível só por ato administrativo; não é oferecido no aplicativo.
5. A coluna do dono não é obrigatória no banco (cargas e cenários gravam o perfil antes do vínculo); a obrigatoriedade entra
   com o fluxo de criação de contas.
6. Funções registradas em `tests/isolamento_sem_cobertura.json` (lista no relatório privado): recusaram, mas sem prova efetiva de que a recusa foi pela posse.
7. Backup único com os dados de todos os usuários: governança a definir antes de abrir o acesso.

## 9. Plano de publicação (não executado)

1. Conferir a `main` e avançar o ramo; reexecutar a suíte de isolamento e a regressão.
2. Backup `PRE_MIGRATION`.
3. Migration `20261231090000` (70 → 71). Conferir: dono nos dois perfis, guarda no perfil 1, administrador, leituras iguais.
4. `regularizar_itens_sem_perfil.py previa --perfil 1`: a impressão tem de ser a do ensaio; depois `executar`.
5. Conferências: nenhuma tabela mudou além da coluna do perfil dos itens; leituras do titular idênticas.
6. Push e deploy do frontend (só a mensagem nova).
7. Reversão, se preciso: frontend ao deploy anterior; `regularizar_itens_sem_perfil.py reverter`; script de reversão da migration.

**Nada disso é executado sem autorização expressa do titular.**
