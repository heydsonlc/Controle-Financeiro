# FIN-MULTIUSUARIO-HOMOLOGACAO-01 — Homologação integrada do aplicativo multiusuário

**Situação:** homologação técnica **local** concluída em 18/11/2026, no ramo `multiusuario-homologacao-01` (sobre os três
ramos anteriores, em sequência). **Nada em produção:** sem push, sem merge, sem deploy, nenhuma das três migrations aplicada,
nenhum convite real, nenhum usuário criado, cadastro público desligado. O plano de publicação abaixo está **preparado, não
executado**; depende de autorização expressa do titular.

Etapas homologadas em conjunto:

| Etapa | Documento | Migration | Commit local |
|---|---|---|---|
| 1. Propriedade dos perfis e isolamento | `docs/FIN_MULTIUSUARIO_SEGURANCA_01.md` | `20261231090000` | `9d215c3` |
| 2. Catálogo padrão e personalização | `docs/FIN_CADASTROS_PADRAO_01.md` | `20270101090000` | `1fe0205` |
| 3. Entrada por convite e administração | `docs/FIN_MULTIUSUARIO_ACESSO_01.md` | `20270102090000` | `5752fdf` |

## 1. Cenário da homologação integrada

`tests/test_supabase_homologacao_multiusuario.py`, em banco local descartável, com dados fictícios e as três migrations.

- **Administrador:** o titular fictício, com os dados do cenário base (perfis, contas, despesas, cartões).
- **Usuários X e Y:** entram pelo **fluxo real** (convite registrado pelo administrador → ativação). Cada um tem dois perfis
  com os **mesmos nomes** ("Pessoal" e "Empresa"), a mesma conta "Conta Principal", o mesmo "Cartão Principal" e uma categoria
  particular "Pets", com valores diferentes e marcas próprias em cada registro.
- Em cada perfil, uso de ponta a ponta pelas funções do aplicativo: conta bancária, despesa cadastrada e paga, cartão, compra
  parcelada, categoria particular e palavra-chave própria.

## 2. Matriz de testes

| Área | O que é conferido | Onde | Resultado |
|---|---|---|---|
| Fluxo funcional | X e Y usam o aplicativo; saldo = saldo inicial − despesa paga; cada um vê só os seus perfis, contas, cartões, categorias e palavras; a categoria particular vale nos dois perfis do dono; o catálogo padrão é o mesmo para os dois | homologação, teste 1 | ok |
| Isolamento por perfil | **toda** função exposta que recebe perfil é chamada nos **seis sentidos** (X→Y, Y→X, X→Admin, Y→Admin, Admin→X, Admin→Y), em todos os perfis: recusa e nenhuma resposta com dado alheio; nada gravado | homologação, teste 2 | ok |
| Isolamento por registro | X, no próprio perfil, apontando para conta bancária, cartão e categoria particular de Y: recusado, nada alterado | homologação, teste 3; suíte permanente | ok |
| Suíte permanente de isolamento | perfil alheio, registro alheio com cobertura medida, sem sessão, nomes iguais entre usuários, dono fixo, tentativas específicas, índices de referência, registros sem perfil | `test_supabase_isolamento_usuarios.py` | 10/10 |
| Catálogo e personalização | padrão protegido; particulares e palavras de um não alcançam o outro; mudança do administrador chega a todos e respeita o ajuste individual; nada já classificado muda | `test_supabase_cadastros_padrao.py`; homologação, teste 6 | 10/10; ok |
| Administração | 18 funções de administração recusam o usuário comum sem gravar; o administrador vê só e-mail, situação, datas e quantidade de perfis; não vê categoria particular nem palavra de ninguém | homologação, teste 4; `test_supabase_acesso.py` | ok; 12/12 |
| Conta sem acesso | conta suspensa e conta nunca ativada chamam **todas** as funções expostas: nenhuma responde | `test_supabase_acesso.py` (permanente) | ok |
| Convites e ativação | válido, vencido, revogado, reutilizado, e-mail com conta, e-mail não confirmado, ativação incompleta e repetida | `test_supabase_acesso.py` | ok |
| Suspensão | suspender X não muda nada para Y nem para o administrador; nada de X é apagado; reativar devolve o acesso | homologação, teste 7 | ok |
| Preservação | tabelas, saldos e telas do titular idênticos antes e depois da entrada e do uso de X e Y | homologação, teste 5; ensaios na cópia fiel | ok |
| Backup e restauração | backup do banco multiusuário restaura idêntico num banco novo; donos, telas, isolamento, conta suspensa e convite pendente preservados | homologação, teste 8; `test_backup_banco.py` | ok |
| Telas | convite, link, senha, primeiro acesso, sem convite, vencido, recuperação, suspensão, auditoria; catálogo padrão e personalização; menu | `acesso_convite.spec.mjs`, `categorias_padrao.spec.mjs` e a suíte e2e | 298/298 |

Resultados consolidados (código final das três etapas):

| Verificação | Resultado |
|---|---|
| Homologação integrada | 8/8 |
| Conjunto de segurança (isolamento, regularização, catálogo, acesso, homologação, backup) numa rodada só | 51 aprovados, 2 pulados, 0 falhas |
| Regressão de banco completa | 1.452 aprovados, 20 pulados, 0 falhas |
| Unitários do frontend | 131/131 |
| Suíte e2e completa | 298/298 |
| Ensaio encadeado das três etapas na cópia fiel da produção | 70 verificações, 0 falhas |

## 3. Comparação financeira (cópia fiel da produção, backup de 17/11/2026)

O ensaio aplica as três migrations e as duas cargas, na ordem da publicação, sobre uma cópia restaurada do backup, e compara
antes e depois (impressão de todas as tabelas e todas as funções de leitura das telas, nos dois perfis, em vários meses).

| Etapa | Tabelas de dados | Telas do titular |
|---|---|---|
| 1. Segurança (migration + regularização dos itens sem perfil) | só os itens regularizados e a auditoria | idênticas |
| 2. Catálogo (migration + carga inicial) | só catálogo de palavras, categorias de cartão e vínculos | idênticas no perfil de referência; no outro perfil mudam só as esperadas (catálogo visível e categorias de cartão padrão) |
| 3. Acesso (migration) | nenhuma | idênticas |
| Segundo e terceiro usuários fictícios usando o aplicativo | só os registros deles | idênticas |
| Reversão de cada etapa | volta ao estado anterior | idênticas |

Nenhum saldo, lançamento, fatura, pagamento ou documento do titular muda em nenhum passo.

## 4. Backup e restauração com vários usuários (procedimento operacional)

A rotina de backup existente (FIN-REG-01/02) **já cobre** o aplicativo multiusuário, sem alteração: as estruturas novas ficam
nos esquemas que o backup leva (junto com as contas do Supabase Auth). Comprovado por teste: o banco com três contas, conta
suspensa, convite pendente e personalizações restaura idêntico num banco novo.

1. **Rotina:** inalterada (semanal e antes de cada migration, `--tipo PRE_MIGRATION`).
2. **Restauração:** sempre do banco **inteiro**, num banco **novo e vazio**; nunca sobre a produção (a ferramenta recusa o
   projeto de origem). O ensaio de restauração é em banco local descartável.
3. **Conferência depois de restaurar:** quantidade de contas da plataforma e situação de cada uma; convites; dono de cada
   perfil; a suíte de isolamento contra o banco restaurado (descartável).
4. **Pedido de um único usuário** (recuperar dados apagados por engano): não há restauração parcial. O caminho é restaurar o
   backup num banco descartável e extrair de lá, por análise específica, só os registros daquele usuário. O backup contém
   dados de **todos** os usuários: o acesso a ele continua restrito ao operador, cifrado, fora do repositório.
5. **Exclusão de conta a pedido:** não implementada nesta fila. Suspender preserva os dados; apagar exige roteiro próprio (e os
   backups anteriores continuam contendo os dados até expirarem).

## 5. Inventário das migrations (nenhuma aplicada)

Produção hoje: 70 migrations. As três abaixo são geradas por script (`--verificar` confere o arquivo versionado) e nenhuma
altera registro financeiro.

| Ordem | Migration | Linhas | Gerador | Dados depois dela | Reversão |
|---|---|---:|---|---|---|
| 71 | `20261231090000_financeiro_multiusuario_seguranca` | 1.886 | `gerar_migration_multiusuario_seguranca.py` | `regularizar_itens_sem_perfil.py` (58 itens, prévia → execução) | `supabase/reversao/20261231090000_…` (depois de reverter a regularização) |
| 72 | `20270101090000_financeiro_cadastros_padrao` | 1.276 | `gerar_migration_cadastros_padrao.py` | `cadastros_padrao.py` (modelo de categorias de cartão, palavras pessoais, perfil Empresa); depois `retirar-guarda` | `supabase/reversao/20270101090000_…` (depois de `cadastros_padrao.py reverter`) |
| 73 | `20270102090000_financeiro_multiusuario_acesso` | 1.601 | `gerar_migration_acesso.py` | nenhum | `supabase/reversao/20270102090000_…` |

A ordem é obrigatória (cada uma parte das funções da anterior). As impressões SHA-256 dos seis arquivos estão no relatório
privado, para conferência no dia da publicação.

## 6. Plano de publicação (preparado, NÃO executado)

Recomendação: **três janelas**, uma por etapa, com conferência entre elas (podem ser no mesmo dia). Em cada janela:

| Passo | Etapa 1 | Etapa 2 | Etapa 3 |
|---|---|---|---|
| 1. Pré-condições | produção = 70 migrations; ramo conferido; `--verificar` dos três geradores | etapa 1 publicada e conferida | etapa 2 publicada e conferida; painel do Supabase conferido (senha, limites, sessão, redirecionamento, modelos de e-mail) |
| 2. Backup | `backup_rotina.py executar --tipo PRE_MIGRATION` | idem | idem |
| 3. Migration | `supabase_migrations.py simular` e `aplicar --versoes 20261231090000` | `… 20270101090000` | `… 20270102090000` |
| 4. Dados | prévia da regularização (58 itens; a impressão tem de ser a do ensaio ou explicada) → execução | prévia da carga (lista de palavras pessoais **decidida pelo titular**) → execução → `retirar-guarda` | — |
| 5. Permissões | o titular continua dono dos perfis e administrador da plataforma (ato do operador, já previsto na etapa 1) | o titular continua gestor do catálogo | a conta do titular fica ativa e administradora (conferir) |
| 6. Frontend | push e deploy do ramo da etapa | idem | idem |
| 7. Conferências | telas do titular iguais; índices de TR; nomes e perfil padrão | catálogo, sugestões de importação, categorias de cartão nos dois perfis, tela de Categorias | login do titular; menu Administração; nenhuma conta além da dele; nenhum convite |
| 8. Reversão, se algo divergir | frontend ao deploy anterior → `regularizar… reverter` → script de reversão | frontend → `cadastros_padrao.py reverter` → script de reversão | frontend → script de reversão |

Testes depois da publicação (sem criar dados de teste em produção): leitura das telas do titular; contagens das tabelas novas;
`sou_administrador_plataforma`; tentativa de entrada com um login antigo sem perfil, se houver um à mão (deve ficar em "acesso
não liberado").

**Regularização do legado:** os 58 itens sem perfil (parcelas de consórcios inativos, todos do perfil de referência) entram na
janela da etapa 1. Depois da etapa 2 a guarda dos registros sem perfil é retirada.

## 7. Critérios para o primeiro convite real

Só depois de **todos**:

1. As três etapas publicadas e conferidas, com backup feito depois da última.
2. Painel do Supabase conferido pelo titular (política de senha, limites, sessão, redirecionamento, modelos de e-mail).
3. Homologação do titular com a conta real: telas iguais, Administração visível só para ele.
4. Um ensaio completo de convite com um **e-mail do próprio titular** (segunda caixa), do convite à ativação, incluindo
   recuperação de senha e suspensão/reativação, e conferência de que essa conta não vê nada do titular.
5. Decisão registrada sobre o envio do convite (dois passos, hoje) e sobre a lista de palavras pessoais.
6. Texto de orientação ao convidado (o aplicativo começa vazio; dados são só dele).

## 8. Riscos de mudança sem volta simples

| Mudança | A partir de quando | Consequência |
|---|---|---|
| Categoria particular ou palavra-chave de usuário | o primeiro usuário personalizar | a reversão da etapa 2 é recusada até desfazer as personalizações |
| Conta ativada por convite | a primeira ativação | a reversão da etapa 3 mantém a conta e os perfis; perde-se a suspensão como recurso e a auditoria de acesso |
| Nomes de perfil iguais entre usuários | o segundo usuário criar "Pessoal" | a reversão da etapa 1 é recusada (a regra antiga exigia nome único global) |
| Dados de terceiros no banco e nos backups | a primeira ativação | o titular passa a guardar dados de outras pessoas: backups, acesso de operador e eventual pedido de exclusão passam a envolver terceiros |

Por isso: publicar as três etapas e conferir com calma **antes** do primeiro convite; depois do primeiro usuário real, corrigir
para frente em vez de reverter.

## 9. Critérios de aprovação desta homologação

| Critério | Situação |
|---|---|
| Suíte permanente de isolamento, incluindo categorias, palavras-chave e funções de administração, sem falha | atendido |
| Nenhuma função exposta responde a conta sem acesso liberado | atendido |
| Administrador sem acesso funcional a dado financeiro de outro usuário | atendido |
| Fluxos de ponta a ponta com dois usuários e o administrador | atendido |
| Preservação dos dados e das telas do titular (cenário fictício e cópia fiel) | atendido |
| Backup e restauração do banco multiusuário | atendido (local) |
| Regressão completa de banco, unitários e e2e | atendido |
| Reversão de cada etapa ensaiada | atendido |
| Homologação do titular com a conta real | **pendente** (depende da publicação) |
| Conferência do painel do Supabase | **pendente** (titular) |

## 10. Riscos residuais

1. **Cobertura por identificador de registro:** a suíte mede a cobertura efetiva (função × parâmetro de identificador) e mantém
   uma linha de base das combinações ainda não exercitadas com dado real; função nova entra na conferência automaticamente,
   mas a linha de base não é zero.
2. **Envio de convite em dois passos** e **encerramento de sessões de terceiros** dependem do painel do Supabase.
3. **Um único administrador** e um único operador do banco: a recuperação de acesso do administrador é pelo banco.
4. **Sem restauração parcial por usuário** e **sem exclusão de conta a pedido** (seção 4).
5. **Catálogo padrão:** categoria padrão nova com o nome de uma particular já existente passa a aparecer junto dela.
6. **Limites e política de senha** são do Supabase Auth: valem os do painel, não os da tela.
7. Volume: os testes usam três contas; não houve ensaio de carga com muitos usuários.

Relatórios com detalhe de sondas, impressões e dados da cópia fiel ficam fora do repositório, na pasta privada do titular.
