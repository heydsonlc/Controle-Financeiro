# FIN-MULTIUSUARIO-AJUSTES-FINAIS-01 — Ajustes funcionais, auditoria complementar e preparação da publicação

**Situação:** concluído localmente em 18/11/2026, sobre a base homologada das quatro etapas multiusuário. Complementa, sem
substituir, `FIN_MULTIUSUARIO_SEGURANCA_01.md`, `FIN_CADASTROS_PADRAO_01.md`, `FIN_MULTIUSUARIO_ACESSO_01.md` e
`FIN_MULTIUSUARIO_HOMOLOGACAO_01.md`. A publicação é tratada no FIN-MULTIUSUARIO-PUBLICACAO-01.

## 1. Alterações implementadas

### 1.1. Palavra-chave: ação "Alterar categoria" (ajuste 01)

Na tela de Categorias o usuário **seleciona a palavra** (clique no texto), e logo abaixo da lista aparecem as ações dela, em
botões pequenos com ícone e texto:

| Palavra | Ações |
|---|---|
| Padrão do aplicativo | Alterar categoria · Desativar para mim |
| Sua (particular) | Alterar categoria · Remover |
| Padrão que você trouxe para esta categoria | Alterar categoria · Restaurar padrão |
| Padrão desligada, ou levada para outra categoria (vista na categoria de origem) | Restaurar padrão |

"Alterar categoria" abre um modal simples com as categorias que o usuário pode usar (ativas; padrão ou dele). Ao confirmar, a
tela vai para a categoria de destino com a palavra já selecionada.

- **Palavra padrão:** o catálogo do aplicativo não muda; grava-se uma personalização `REASSOCIADA` só do usuário. Na
  categoria de destino ela aparece marcada, com a categoria padrão de origem; na de origem aparece riscada ("movida"), com a
  ação de restaurar. Escolher de novo a categoria padrão no modal também restaura.
- **Palavra particular:** muda a categoria da regra do próprio usuário.
- **Destino:** categoria particular de outro usuário responde como inexistente.
- **Sem duplicidade:** levar a palavra para uma categoria que já tem a mesma palavra para o usuário é recusado; repetir a mesma
  alteração não duplica nem falha.
- Nenhuma despesa ou compra já classificada é reclassificada; só a sugestão da importação muda, e só para o usuário.

### 1.2. Página de senha: link com confirmação

A página `definir-senha.html` passou a aceitar também o formato de link recomendado pelo Supabase (`token_hash`): o link só é
usado quando a pessoa clica em **Continuar**. Verificadores de links de provedores de e-mail abrem o endereço antes do
destinatário; no formato padrão isso gasta o link de uso único. O formato padrão continua aceito. Sem mudança no banco.

### 1.3. Categoria particular de outro usuário no vínculo de categoria de cartão

A gravação já era recusada pela rede de proteção nos dados, mas com mensagem diferente da de categoria inexistente. Agora a
resposta é idêntica (a sonda dirigida da seção 4 exige isso).

### 1.4. Auditoria complementar de isolamento (ajuste 04)

Ver seção 4. Resultado: nenhuma falha de autorização encontrada; a linha de base de combinações sem cobertura ficou vazia.

## 2. Arquivos modificados

| Área | Arquivos |
|---|---|
| Banco (gerado) | `scripts/cadastros_padrao_estrutura.sql`, `scripts/gerar_migration_cadastros_padrao.py`, `scripts/gerar_migration_acesso.py`, `supabase/migrations/20270101090000_…`, `supabase/migrations/20270102090000_…` e as duas reversões |
| Tela de Categorias | `web/src/js/categorias-adaptacoes.js`, `web/src/js/categorias-adaptador.js`, `web/src/css/categorias-adaptacoes.css` |
| Página de senha | `web/src/definir-senha.html`, `web/src/js/definir-senha.js` |
| Testes de banco | `tests/test_supabase_ajustes_finais.py` (novo), `tests/isolamento_dirigido.py` (novo), `tests/test_supabase_isolamento_usuarios.py`, `tests/isolamento_cenario.py`, `tests/isolamento_sem_cobertura.json`, `tests/test_supabase_cadastros_padrao.py` |
| Testes de tela | `web/tests/e2e/categorias_padrao.spec.mjs`, `web/tests/e2e/acesso_convite.spec.mjs`, `web/tests/e2e/run_e2e.py`, `web/tests/unit/build.test.mjs` |
| Ensaio | `scripts/ensaio_ajustes_finais.py` (novo) |
| Documentação | este arquivo; `FIN_MULTIUSUARIO_PRIVACIDADE_E_EXCLUSAO_DE_CONTA.md` (novo) |

## 3. Funções reutilizadas ou criadas

| Função | Situação |
|---|---|
| `alterar_categoria_da_palavra_chave(p_id, p_categoria_id)` | **criada**: a única necessária. Atende palavra padrão (id positivo) e ajuste do usuário (id negativo), inclusive a palavra particular, que `reassociar_palavra_chave_padrao` não cobria |
| `palavras_chave_tela` | **redefinida**: acrescenta, na reassociada, a categoria padrão de origem, e mostra na categoria de origem a palavra "movida". Os demais campos e linhas não mudam |
| `vincular_despesa_categoria_cartao` | definição vigente + 1 trecho (categoria visível ao dono do perfil) |
| `reassociar_palavra_chave_padrao`, `restaurar_palavra_chave_padrao`, `remover_minha_palavra_chave`, `desligar_palavra_chave_padrao`, `palavras_efetivas` | **reutilizadas** sem alteração |

## 4. Auditoria complementar de isolamento

A suíte permanente mede, para cada função exposta que recebe identificador de registro, se a recusa ao registro de outro
usuário foi **pela posse**. Eram 166 combinações de função e parâmetro: 123 comprovadas pela sonda genérica e 43 sem prova.

Para as 43, foram escritas **sondas dirigidas**: cada combinação recebe dados fictícios válidos para chegar à lógica relevante
(o registro "pai" correto, o perfil do tipo exigido, o registro do tipo procurado), e a prova é diferencial, com o próprio
atacante, no próprio perfil dele:

- com o registro **próprio**, a função encontra;
- com um identificador **inexistente**, responde "não encontrado";
- com o registro **do outro usuário**, a resposta tem de ser **idêntica** à do inexistente (código, mensagem e conteúdo), e as
  tabelas do dono são conferidas antes de a transação ser desfeita.

| Classificação | Combinações |
|---|---:|
| Comprovadas pela sonda genérica | 123 |
| Comprovadas por sonda dirigida, nos dois sentidos | 41 |
| Não aplicáveis, com motivo registrado (o parâmetro só filtra registros já restritos ao próprio perfil) | 2 |
| **Sem prova** | **0** |
| Falhas de autorização encontradas | 0 |

As sondas dirigidas cobrem, entre outras, pagamento e estorno de despesa e de fatura, ajuste e amortização de financiamento,
parcela de consórcio, limites e cartões vinculados, vínculos de documentos, patrimônio, veículos e recorrências. A relação
legível, com as respostas de cada sonda, fica na pasta privada (não no repositório).

As sondas são **permanentes**: rodam com a suíte de isolamento; função nova com identificador de registro que a sonda genérica
não comprove faz o teste falhar até receber sonda dirigida ou classificação com motivo.

## 5. Testes

Sobre o código final (as três migrations com os ajustes incorporados), em 18/11/2026:

| Verificação | Resultado |
|---|---|
| `tests/test_supabase_ajustes_finais.py` (reassociação de palavra padrão e particular, restauração, categoria particular como destino, bloqueio de categoria e de ajuste de outro usuário, configuração do outro usuário preservada, sugestões, nada reclassificado, repetição sem duplicidade) | 5/5 |
| Suíte permanente de isolamento, com as sondas dirigidas | 11/11 |
| Homologação integrada multiusuário | 8/8 |
| Regressão de banco completa, em duas metades | 1.466 aprovados, 0 falhas (703 + 763) |
| Os 20 testes que a regressão pulava, executados com o binário do PostgREST | 20/20 (164 aprovados nos cinco arquivos, nenhum pulado) |
| Unitários do frontend | 131/131 |
| Suíte e2e completa | 300/300 |
| `categorias_padrao.spec.mjs` (inclui o fluxo "Alterar categoria" pela tela) | 4/4 |
| `acesso_convite.spec.mjs` (inclui o link com confirmação) | 7/7 |

A intermitência antiga de Lançamentos não ocorreu nesta rodada completa.

### 5.1. Testes pulados

A regressão informava 20 testes pulados. Todos tinham o **mesmo motivo**: dependem do binário do PostgREST (variável
`POSTGREST_BIN`), que a regressão de banco não informa. Não havia cenário não implementado nem pendência de investigação.

| Arquivo | Pulados | O que cobrem | Classificação |
|---|---:|---|---|
| `tests/test_supabase_mvp_rls.py` | 10 | acesso pela API real: sem sessão, sessão inválida, tabelas não expostas | dependente de ambiente |
| `tests/test_supabase_perfis.py` | 5 | perfis pela API real: só os próprios, perfil alheio recusado | dependente de ambiente |
| `tests/test_sec_supabase_public.py` | 2 | esquema público não exposto pela API | dependente de ambiente |
| `tests/test_supabase_contas_mes.py` | 2 | contas do mês pela API real | dependente de ambiente |
| `tests/test_supabase_perfis_gestao.py` | 1 | gestão de perfis pela API real | dependente de ambiente |

Como parte deste contrato os 20 foram **executados** com o binário (o mesmo usado pela suíte e2e) e **passaram**. Risco
residual: nenhum; recomendação: informar `POSTGREST_BIN` também na regressão de banco, para que deixem de ser pulados.

## 6. Comparação financeira (cópia fiel da produção, backup de 17/11/2026)

`scripts/ensaio_ajustes_finais.py` encadeia os ensaios das três etapas e, no estado final, exercita a ação "Alterar categoria".

| Passo | Tabelas de dados | Telas e sugestões do titular |
|---|---|---|
| Três migrations e as duas cargas (ensaios das etapas) | só o previsto em cada etapa | idênticas (no perfil Empresa, só as mudanças esperadas da etapa 2) |
| Um usuário fictício altera a categoria de uma palavra padrão | só a tabela de ajustes daquele usuário | idênticas |
| Repetir a alteração | nada | idênticas |
| Restaurar | volta ao estado anterior | idênticas |

Resultado: **79 verificações, nenhuma falha** (as três etapas e, no fim, 9 verificações da ação "Alterar categoria").

## 7. Situação das migrations

**Continuam sendo três.** A ação "Alterar categoria" foi incorporada às duas ainda não publicadas, em vez de criar uma quarta:

| Migration | Mudou neste contrato? | Motivo |
|---|---|---|
| `20261231090000` (segurança) | **não** | — |
| `20270101090000` (cadastros padrão) | **sim** | função `alterar_categoria_da_palavra_chave`; `palavras_chave_tela` com a origem da reassociação; `vincular_despesa_categoria_cartao` com a categoria visível. A reversão retira a função nova e devolve as outras |
| `20270102090000` (acesso) | **sim** | a função nova entra na lista das funções sem perfil que exigem conta ativa (33 funções devolvidas pela reversão, eram 32) |

Motivo da incorporação: a ação precisa existir junto com a tela da segunda etapa, e a exigência de conta ativa só existe a
partir da terceira; uma migration separada só poderia ser aplicada depois da terceira. Como nenhuma das duas havia sido
publicada, a alteração foi feita pelos geradores (`--verificar` confere os arquivos), as impressões SHA-256 foram
atualizadas (relatório privado) e **todos os ensaios e regressões dependentes foram repetidos** sobre os arquivos finais.

## 8. Conferência do Supabase Auth (ajuste 06)

Nomes conforme a documentação atual do Supabase. **Conferido de fora** = configuração pública do Auth, lida em 18/11/2026.

| # | Item | Onde conferir no painel | Situação / recomendação |
|---|---|---|---|
| 1 | Cadastro público desabilitado | Authentication → Sign In / Providers | **conferido de fora: desabilitado** |
| 2 | Confirmação de e-mail obrigatória | Authentication → Sign In / Providers → Email | **conferido de fora: exigida** |
| 3 | Política de senha | Authentication → Sign In / Providers → Email (tamanho mínimo e caracteres exigidos) | a conferir. Recomendado: mínimo 10, com letras e dígitos (a tela já exige isso; o painel tem de ser igual ou mais exigente) |
| 4 | Proteção contra senhas comprometidas | mesmo lugar ("leaked password protection") | a conferir. Disponível só a partir do plano Pro |
| 5 | Limites de tentativas | Authentication → Rate Limits | a conferir. Padrões documentados: 30 pedidos por 5 min por IP em cadastro/recuperação; 150 por 5 min no login/renovação |
| 6 | Limites de envio de e-mail | Authentication → Rate Limits; e o serviço de e-mail em uso | **atenção:** o serviço de e-mail padrão do Supabase envia só para endereços da equipe do projeto e no máximo 2 mensagens por hora. Para convidar terceiros é preciso configurar **SMTP próprio** |
| 7 | Validade dos links | Authentication → Sign In / Providers → Email → "Email OTP expiration" | a conferir. Padrão 1 hora; acima de 24 horas é desaconselhado. O convite registrado no aplicativo vale de 1 a 30 dias, mas o **link do e-mail** vale o que estiver aqui: vencido o link, registra-se o reenvio e envia-se outro |
| 8 | Sessões | Authentication → Sessions | a conferir. Tempo máximo, inatividade e sessão única só no plano Pro. O token de acesso vale 1 hora por padrão |
| 9 | Redirecionamentos | Authentication → URL Configuration (Site URL e Redirect URLs) | a conferir. Site URL = domínio do aplicativo; lista com os endereços exatos de `definir-senha.html` (sem curingas em produção) |
| 10 | Modelos de e-mail | Authentication → Email Templates ("Invite user", "Reset password") | a conferir. Recomendado o formato com confirmação: link para `definir-senha.html?token_hash={{ .TokenHash }}&type=invite` (e `type=recovery`), que a página já aceita |
| 11 | Encerramento de sessões | Authentication → Users (por usuário) | sair encerra as sessões, mas o token de acesso já emitido vale até expirar; por isso o aplicativo confere a conta **em toda chamada** (conta suspensa não recebe resposta, com ou sem sessão) |
| 12 | Credenciais privilegiadas | Settings → API Keys | o navegador só recebe a chave publicável (o build recusa chave secreta e há teste disso); nenhuma chave privilegiada no repositório. Conferir que as chaves secretas só estão com o operador |

O que não é visível de fora (itens 3 a 11) **não foi conferido** e não pode ser presumido correto.

## 9. Riscos residuais

1. Itens 3 a 11 da seção 8 dependem do painel do Supabase.
2. O envio de convite continua em dois passos (aplicativo + painel) e depende de SMTP próprio para terceiros.
3. Exclusão de conta: há procedimento proposto, sem roteiro implementado (`FIN_MULTIUSUARIO_PRIVACIDADE_E_EXCLUSAO_DE_CONTA.md`).
4. A existência de uma categoria particular de outro usuário não é revelada pelas funções que recebem a categoria como
   parâmetro próprio (conferido); em funções que a recebem dentro dos dados de um cadastro, a recusa vem da rede de proteção.
5. Duas combinações de isolamento ficam classificadas como não aplicáveis por leitura de código, não por sonda.

## 10. Plano de publicação revisado

As três janelas do `FIN_MULTIUSUARIO_HOMOLOGACAO_01.md` (seção 6) continuam valendo, com estes acréscimos:

| Janela | Acréscimo |
|---|---|
| 1 — segurança (`20261231090000`) | retrato de produção em somente leitura antes e depois (impressão de cada tabela e de cada leitura de tela); conferir titularidade dos dois perfis, perfil padrão, administrador, índices de TR, os 58 itens e a impressão da prévia |
| 2 — cadastros padrão (`20270101090000`) | usar o **manifesto das 13 palavras** conferido em produção; conferir os 12 vínculos no modelo e no perfil Empresa; frontend com a ação "Alterar categoria"; retirar a guarda só depois da regularização e das conferências |
| 3 — acesso (`20270102090000`) | **só com a seção 8 conferida no painel**; conferir a conta do titular ativa e administradora, a Administração só para ele, nenhuma conta nova e nenhum convite |

Em cada janela: estado real de produção → backup cifrado → simulação → aplicação → roteiro de dados → conferência → frontend →
testes pós-publicação → registro; reversão conforme o documento de cada etapa. Nenhum usuário adicional é criado na
publicação; o primeiro convite depende de autorização própria.
