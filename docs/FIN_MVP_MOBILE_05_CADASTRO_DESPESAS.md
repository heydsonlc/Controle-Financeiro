# FIN-MVP-MOBILE-05: Cadastro de Despesas mobile

Quinta etapa da versão mobile. Vem depois da Página Principal (FIN-MVP-MOBILE-01), da Lista de Despesas (FIN-MVP-MOBILE-02), dos Cartões (FIN-MVP-MOBILE-03) e das Receitas (FIN-MVP-MOBILE-04), os quatro homologados pelo titular em 14/11/2026.

O atalho **Despesa** da página principal mobile abre direto a **Nova Despesa**: o formulário "Nova Despesa" do desktop em versão compacta e progressiva. Ele grava pelo mesmo serviço e pela mesma função do banco (`criar_despesa`), com os mesmos campos e as mesmas recusas. O botão **Lançar** da barra continua reservado ao FIN-MVP-MOBILE-06.

**Ajuste final (homologação visual de 14/11/2026, Proposta A aprovada):** o campo **Meio de pagamento** fica logo depois de Descrição, Valor e Categoria, com duas opções:
- **Conta a pagar:** o fluxo acima, sem mudança;
- **Cartão de crédito:** a compra da tela Lançamentos do desktop, gravada só por `criar_compra` (seção 8).

E o atalho fica desabilitado para quem só lê o perfil (decisão 6).

**Situação:** implementado no ramo local `mobile-05-cadastro-despesas`, a partir das Receitas (`d7bda9f`). Não houve push, deploy nem migration. Layout aprovado na homologação visual de 14/11/2026 e versão final (com compras à vista e parceladas no cartão de crédito e o atalho para quem só lê) **homologada pelo titular em 14/11/2026**. A publicação continua suspensa: os cinco MVPs mobile ficam no ambiente de desenvolvimento até a avaliação conjunta.

## 1. Análise do desktop (antes de implementar)

O cadastro do desktop é o modal "Nova Despesa" da tela Despesas, composto por:
- `js/original/despesas.js`, vindo de `frontend/static/js/despesas.js`, que não muda;
- o script inline do template;
- `js/despesas-servico.js`, rota `POST /api/despesas`, que chama `criar_despesa`.

| Ponto do contrato | Como é no desktop | Como o mobile segue |
|---|---|---|
| 1. Tipos de despesa | O modal oferece despesa simples, recorrente (semanal, mensal ou anual), recorrente no cartão e consórcio. No novo aplicativo, o serviço **recusa** recorrência no cartão ("em migração para o módulo de cartões") e responde "em migração" para consórcios | Simples e recorrente (mensal, anual, semanal). Cartão e consórcio não aparecem, porque nenhum caminho deles funciona neste formulário |
| 2. Campos obrigatórios e opcionais | Obrigatórios: nome, valor (> 0), categoria e vencimento (o serviço recusa sem vencimento); na semanal, o dia da semana. Opcionais: descrição, competência e meio de pagamento (só recorrência) | Os mesmos: Descrição (o "Nome" do desktop), Valor, Categoria e Vencimento obrigatórios; Competência, meio de pagamento e Observações (a "Descrição" do desktop) opcionais |
| 3. Competência e vencimento | Ao escolher o vencimento, a tela preenche a competência com **o mês anterior** ("mês do salário que pagará"), se o campo estiver vazio. O banco aceita a competência até 12 meses do vencimento; sem ela, usa o mês do vencimento. Na recorrência, a competência de cada conta é o mês do vencimento (regra do banco) e a do formulário não é enviada | A competência começa com o mês da página principal; o vencimento aplica a regra do mês anterior enquanto o usuário não mudar a competência. Na recorrência, o campo some (o banco não o usa) e uma nota explica |
| 4. Contas e formas de pagamento | O cadastro não escolhe conta bancária (`conta_bancaria_id` nulo, `debito_automatico` falso). O "meio de pagamento" (boleto, débito, PIX) só existe na recorrência e é **informativo** (`definir_meio_pagamento_recorrencia`). A conta é escolhida ao pagar | O mesmo: meio de pagamento informativo na recorrência; nenhuma conta no cadastro |
| 5. Recorrentes | `criar_despesa` grava a recorrência (item); **as contas nascem quando a competência é aberta** na lista de Despesas (gerador `gerar_mes`, idempotente). Semanal: `semanal_N_D`, com N = 1 ou 2 (o serviço recusa outras frequências) e D = dia | O mesmo corpo. A Lista de Despesas mobile usa o mesmo serviço e gera a competência ao abrir. Frequência: "Toda semana" ou "A cada 2 semanas" (as que o serviço aceita) |
| 6. Parcelamento | **Não existe** no cadastro de despesas. Parcelas só nas compras de cartão (Lançamentos, Importar Cartão) e no consórcio (em migração) | Sem parcelamento (fica para o FIN-MVP-MOBILE-06, compras no cartão) |
| 7. Cartão de crédito | "Recorrência no cartão" é recusada no formulário de Despesas. A recorrência no cartão é cadastrada na tela Recorrências; compras, em Lançamentos e Importar Cartão | Ajuste final: "Cartão de crédito" grava a compra da tela Lançamentos (`criar_compra`), nunca uma conta a pagar. A recorrência no cartão fica desabilitada (etapa posterior; seção 8) |
| 8. Despesa já paga | O modal tem "Despesa já foi paga", mas o serviço **recusa**: "Use a ação de pagamento para marcar a despesa como paga: ela escolhe a conta bancária e registra o movimento" | Não implementado (o contrato manda não criar só no mobile). A confirmação leva à Lista de Despesas, onde fica a ação Pagar |
| 9. Previsões futuras | Só pela recorrência (gerador ao abrir cada competência) | O mesmo; nada é gerado no cadastro |
| 10. Validação e duplicidade | Validações do formulário e do serviço; o banco valida de novo (`ler_dados_despesa`, competência a 12 meses). Chave de idempotência por operação (`operacao_despesa`): o reenvio com os mesmos dados devolve o mesmo resultado | O botão trava no primeiro toque e o serviço manda a mesma chave. O spec confere: duplo toque, um registro |
| 11. Permissões | O banco exige `pode_gerir_perfil` e o gerador NOVO do perfil (escritor único) | Quem só lê não recebe o formulário; o banco recusa de qualquer forma (conferido) |
| 12. Lista e movimentações | A despesa nova aparece na competência em Despesas; movimento só no pagamento | Confirmação com "Ver na Lista de Despesas" na competência certa |

**Defeito do desktop, corrigido só no mobile, sem mudar regra:** o desktop calcula "mês anterior ao vencimento" com `Date.setMonth`. Com vencimento entre 29 e 31 e um mês anterior mais curto, cai no próprio mês: 31/03 vira 03/03 e a competência fica 03, em vez de 02. O mobile calcula por mês (31/03 → 02). A regra declarada ("mês anterior") é a mesma; o desktop continua como está.

## 2. O que foi feito

| Arquivo | Mudança |
|---|---|
| `web/src/despesa-nova-mobile.html`, `css/despesa-nova-mobile.css`, `js/despesa-nova-mobile.js` (novos) | Página fora da moldura: cabeçalho (voltar, "Nova Despesa" e perfil), formulário progressivo, confirmação e barra inferior. CSS restrito a `body.mob-despesa-nova`; campos, botões e mensagens de `mobile-modulo.css`. Grava só por `POST /api/despesas` no serviço do desktop, sem consulta própria ao banco |
| `web/src/js/despesas-servico.js` | Só uma função de leitura nova, `podeGerirPerfil()` (a mesma `pode_gerir_perfil` que os outros serviços usam), para não abrir o formulário a quem só lê. Nenhuma regra mudou |
| `web/src/inicio.html`, `js/mobile-comum.js`, `js/sessao.js` | O atalho Despesa aponta para `despesa-nova-mobile.html` e entra em `MODULOS_ATIVOS`; a página entra nas permitidas. Lançar continua desabilitado |
| `web/src/js/inicio-mobile.js`, `js/mobile-comum.js`, `js/perfil.js` (ajuste final) | Página principal: consulta só a permissão do perfil ativo (`meus_perfis` + `pode_gerir_perfil`, em `perfil.js`); para quem só lê, o atalho Despesa fica visível e desabilitado (`desabilitarModulo`, sem link mesmo trocando o mês, título "Somente leitura neste perfil"). Nenhum dado financeiro é lido |
| `web/src/js/compras-servico.js` (novo, ajuste final) | A compra no cartão da tela Lançamentos, extraída de `lancamentos-adaptador.js` **sem mudar o comportamento**: cartões ativos (`cartoes_do_perfil`), fatura sugerida (`sugerir_competencia`), prévia das parcelas (`previa_compra`), validações, gravação (`criar_compra`, chave de idempotência) e a pergunta da fatura consolidada (409). Serve à tela Lançamentos do desktop, à Nova Despesa mobile e ao futuro Registrar Lançamento (MOBILE-06) |
| `web/src/js/lancamentos-adaptador.js` (ajuste final) | Passa a usar `compras-servico.js` para cartões, fatura sugerida, prévia e gravação da compra. O abastecimento e as demais rotas continuam como estavam. `criar_compra` agora é chamada só no serviço comum |
| testes | Novo: `web/tests/e2e/mobile05_cadastro_despesas.spec.mjs`. Atualizados: `build.test.mjs` (teste novo da página e quatro atalhos; cartão só por `criar_compra` no serviço comum), `mob08_inicio.spec.mjs` e `mob01_despesas.spec.mjs` |
| `tests/supabase_local.py`, `web/tests/e2e/run_e2e.py` (ajuste final) | Cenário fictício do cartão: "Nubank Master G" com fechamento confirmado (`criar_cartao`), fatura 09/2031 paga (`pagar_fatura`) e 12/2031 consolidada (como a importação grava, só no banco descartável) |
| `scripts/homologacao_real/lote_real.py` | O script novo, que cita `/api/`, entra nas rotas locais |

**Reaproveitado:**
- `despesas-servico.js` (rota, validações, chave de idempotência e mensagens);
- `mobile-ui.js` (entrada, seletor, botão, mensagem, aviso) e `mobile-modulo.css`;
- `mobile-comum.js` (competência, atalhos, "Mais"/Sair), `perfil.js` e `sessao.js`;
- `formatarCompetencia`;
- a Lista de Despesas mobile, que mostra e gera as contas.

**Não muda:**
- as telas do desktop;
- os módulos mobile anteriores, salvo o atalho;
- receitas;
- o banco, as migrations, as regras financeiras e a CSP;
- a conta a pagar grava em 06 e 07/2031 do Perfil G; a compra no cartão, de 05 a 12/2031 no "Nubank Master G", meses sem outro dado desse cartão.

## 3. Comportamento

- **Campos essenciais:**
  - Descrição;
  - Valor | Categoria;
  - Meio de pagamento: **Conta a pagar** (padrão) ou **Cartão de crédito**;
  - na conta a pagar: Vencimento | Competência ("mês do salário que pagará a despesa");
  - no cartão: Cartão | Data da compra, Parcelas | Fatura, a fatura sugerida e a prévia do parcelamento (seção 8);
  - "Despesa recorrente";
  - Observações;
  - Cancelar | Salvar.
- **Recorrente marcada (conta a pagar):** abre uma seção cinza com Periodicidade (Mensal, Anual, Semanal), na semanal Dia da semana e Frequência, e "Pagamento da conta" (Não informado, Boleto, Débito, PIX: as opções que o banco aceita, informativas). A competência some e o vencimento ocupa a linha.
- **Erros:** aparecem embaixo do campo, com borda vermelha, e o foco vai ao primeiro. A explicação do banco também vai ao campo que ela cita, como "Competência deve ficar a até 12 meses do vencimento", e aparece no rodapé do formulário.
- **Cancelar:** volta à página principal sem gravar.
- **Depois de salvar:**
  - "“Conta de água” cadastrada" e a mensagem do serviço ("Despesa salva na competência 06/2031." ou "Recorrência cadastrada. As contas são geradas automaticamente ao abrir a competência.");
  - botões **Ver na Lista de Despesas** (na competência: a escolhida, ou o mês do vencimento na recorrência), **Nova despesa** (formulário vazio, mesma competência) e **Início**;
  - nada redireciona sozinho.
- **Somente leitura:** a página mostra "Acesso somente de leitura a este perfil: não é possível cadastrar despesas." e "Voltar ao início", sem formulário.

## 4. Testes

**Unitários:** 111/111. `build.test.mjs` ganhou o teste novo da página:
- sem moldura, CSS restrito, gravação só por `POST /api/despesas` do serviço;
- sem consórcio, `pago: false`, nenhuma conta a pagar no cartão; a compra no cartão só por `POST /api/cartoes/:id/lancamentos` do serviço comum, com `criar_compra` só em `compras-servico.js` (também para a tela Lançamentos);
- barra com Lançar desabilitado;
- página principal com quatro atalhos.

**Funcionais (`mobile05_cadastro_despesas.spec.mjs`, 12/12):**

| Requisito | Conferência |
|---|---|
| Abertura pelo atalho | Atalho Despesa → `despesa-nova-mobile.html?mes=2031-06`; competência 06/2031; Lançar desabilitado; recorrência fechada ao abrir |
| Validações | Sem preencher: erros em Descrição, Valor, Categoria e Vencimento, foco na Descrição. Competência a 22 meses do vencimento: explicação do banco junto à Competência, nada gravado |
| Cancelamento | Formulário preenchido → Cancelar → página principal; `contas_do_mes` sem o registro |
| Competência | Vencimento 10/07 → 06; 31/03 → 02; competência mudada pelo usuário não é sobrescrita |
| Despesa simples sem duplicidade | Duplo toque em Salvar → **uma** conta (R$ 87,45, vencimento 10/07/2031, Moradia, Pendente) |
| Lista mobile e desktop | "Ver na Lista de Despesas" abre 06/2031 com a conta uma vez; a tela Despesas do desktop no mesmo banco também a mostra uma vez, com o mesmo valor. "Nova despesa" recomeça vazio |
| Recorrente mensal | Duplo toque → **uma** recorrência (`mensal`, R$ 119,90, 15/07/2031, meio `pix`); a Lista de 07/2031 gera a conta uma vez (vencimento 15/07) |
| Recorrente semanal | Sem dia da semana: erro junto ao campo; a cada 2 semanas na sexta → `semanal_2_5`, como o formulário do desktop |
| Somente leitura | Usuário H: atalho Despesa desabilitado na página principal (sem link, inclusive depois de trocar o mês; Receita, Cartões e Resumo seguem); acesso direto ao endereço sem formulário; `criar_despesa` do leitor recusado pelo banco |
| Responsividade | 320, 375, 390 e 430 px com a recorrência semanal aberta e, no cartão, com a prévia de 12 parcelas aberta: sem rolagem horizontal, nada fora da tela, campos sem sobreposição |
| Meio de pagamento | Logo após Descrição, Valor e Categoria; "Conta a pagar" por padrão (vencimento e competência). No cartão: Cartão (Selecione, Visa, Master), Data da compra, Parcelas (1) e Fatura; recorrência desmarcada e desabilitada, com a orientação; de volta à conta a pagar, tudo como antes. Erros do cartão junto ao campo (cartão, parcelas de 1 a 48) |
| Fatura sugerida | Master, 10/07/2031 → fatura 07/2031 ("fecha 15/07, vence 25/07"); o mês escolhido pelo usuário prevalece até "Usar a fatura sugerida"; Visa (fechamento não confirmado) → aviso e mês da página principal, como no desktop |
| Compra à vista sem duplicidade | Duplo toque em Salvar → **uma** compra (R$ 250,00, 10/07/2031, 1/1) na fatura 07/2031; **nenhuma** conta a pagar com o nome da compra; executado da fatura R$ 250,00 |
| Cartões e Despesas atualizados | "Ver no cartão" abre os Cartões mobile em 07/2031 no Master, com a compra; a Lista de Despesas mobile de 07/2031 mostra só a fatura do Master (R$ 250,00), sem linha da compra |
| Compra parcelada | 3 × R$ 300,00: a prévia (plano do banco) mostra 05, 06 e 07/2031 e o total R$ 900,00; gravada, uma parcela em cada fatura (1/3, 2/3, 3/3) |
| Fatura paga | Compra de 20/08 → fatura sugerida 09/2031, paga ("vai para a próxima em aberto") → gravada em 10/2031, nada em 09 |
| Fatura consolidada | Compra de 20/11 → 12/2031, consolidada: a pergunta do desktop no formulário ("total R$ 200,00 passa a R$ 280,00"). "Não incluir" → nada gravado; "Confirmar inclusão" com duplo toque → **uma** compra |
| Somente leitura (cartão) | `criar_compra` do leitor H recusada pelo banco |
| Segurança | Nenhuma chamada a `/api/` no servidor, nenhum erro de CSP ou de JS |

**Regressão por impacto (N3), antes do ajuste final:** 21 specs:
- os cinco mobile;
- do desktop: Despesas (lista, cancelamento, pagamento em lote), recorrências (três specs), Cartões (tela, múltiplos, executado, agrupamento), parcelas de lançamentos, contas, contas bancárias, movimentações, dashboard e moldura.

**99 aprovados, 3 reprovados, 8 não rodaram** (dependentes, no modo serial). As 3 reprovações são as **preexistentes de recorrência**, já registradas no FIN-MVP-MOBILE-02 e no FIN-MVP-MOBILE-03:
- `recorrencia.spec:262` ("Despesa e todas as futuras foram excluídas");
- `recorrencias_inativacao:85`, em que a conta da recorrência não é gerada na tela do desktop; a variante que falha alterna entre 1366 e 1920 de uma rodada para outra;
- `recorrencias_tela:115` ("gerados automaticamente até 02/2031").

**Nenhuma falha introduzida por este MVP.** Continuam como pendência à parte.

**Regressão do ajuste final (N4: o serviço da compra no cartão é comum à tela Lançamentos do desktop):** 24 specs: os cinco mobile; do desktop, Lançamentos (tela, parcelas P14, dois de abastecimento), movimentações, documentos com sugestão financeira, Cartões (tela, múltiplos, agrupamento e executado da fatura), Despesas (lista, pagamento em lote, cancelamento), recorrências (três specs), perfis, acesso e moldura. **112 aprovados, 3 reprovados, 9 não rodaram** (dependentes, no modo serial). As 3 reprovações são as mesmas preexistentes de recorrência, com as mesmas mensagens (`recorrencia.spec:262`, `recorrencias_inativacao:85` em 1366 e `recorrencias_tela:115`). Nenhuma falha introduzida pelo ajuste final; a tela Lançamentos, que agora grava pelo serviço comum, passou inteira.

## 5. Ambiente e dados

- **Banco descartável local** (`run_e2e.py`). Nenhuma escrita em produção; nenhuma migration.
- **Usuário G (`usuario.g@teste.local`):** titular do "Perfil G (fictício)". É **o mesmo login dos Cartões e das Receitas**: uma conta só para homologar os três módulos.
- **Categorias de despesa:** as do catálogo fictício do ambiente (Moradia, Saude, Cartoes, Combustível e as demais), em ordem alfabética, como no desktop.
- **Usuário H (`usuario.h@teste.local`):** leitor do Perfil G.
- **Cartão (ajuste final):** "Nubank Master G (fictício)" (fecha dia 15, vence dia 25) passou a ter o fechamento confirmado, para a fatura ser sugerida. A fatura 09/2031 está **paga** (compra-base de R$ 100,00) e a 12/2031 está **consolidada** (compra-base de R$ 200,00). O "Itau Visa G" segue com o fechamento não confirmado.

## 6. Decisões e limitações (para o titular)

1. **Sem "Despesa já paga" e sem consórcio:** o serviço do desktop recusa os dois. Pagar continua na Lista (ação Pagar, com conta, movimento e saldo). O cartão e o parcelamento entraram no ajuste final, pela compra da tela Lançamentos (seção 8).
2. **Rótulos:** "Descrição" no lugar do "Nome" do desktop, e "Observações" no lugar da "Descrição" opcional (que o banco grava nas observações da conta), como pede a tabela do contrato.
3. **Competência inicial = mês da página principal.** Ao escolher o vencimento, aplica-se a regra do desktop (mês anterior) até o usuário mudar a competência à mão. A data de 29 a 31 segue o mês, sem o defeito do desktop (seção 1).
4. **Recorrência:** a competência some porque o banco usa o mês de cada vencimento. A conta nasce quando a competência é aberta na Lista; o link da confirmação já leva ao mês do primeiro vencimento. Na semanal, só "toda semana" e "a cada 2 semanas", porque o serviço recusa as outras frequências que o campo do desktop deixa digitar.
5. **Periodicidade inicial "Mensal":** o desktop abre em "Semanal", a primeira opção da lista. É escolha de apresentação, sem efeito na regra.
6. **Somente leitura (ajuste final, 14/11/2026):** a página principal passou a consultar só a permissão do perfil ativo, e o atalho Despesa fica visível e desabilitado para quem só lê. Receita, Cartões e Resumo continuam habilitados (têm consulta). Acesso direto ao endereço: a Nova Despesa não abre o formulário, e o banco recusa a gravação. A guarda do `mob08_inicio.spec.mjs` aceita só essas duas consultas de permissão.

7. **Cartão de crédito (ajuste final):** ver a seção 8.

## 7. Homologação no Firefox

1. Prévia: `run_e2e.py --previa` → http://127.0.0.1:8790/__previa__/.
2. Se a prévia estiver logada com outra conta: **Mais → Sair**.
3. Entrar com `usuario.g@teste.local` / `Senha-ficticia-G-2026`, a mesma conta dos Cartões e das Receitas.
4. Na página principal, tocar em **Despesa**.
5. Cadastrar uma despesa simples, conferir a confirmação e "Ver na Lista de Despesas".
6. Cadastrar uma recorrente mensal e uma semanal; testar o Cancelar e os erros sem preencher.
7. **Cartão de crédito:** em Meio de pagamento, escolher "Cartão de crédito" e o "Nubank Master G":
   - compra à vista: confira a fatura sugerida, salve e use "Ver no cartão";
   - compra parcelada: Parcelas 3 ou mais, confira a prévia e salve;
   - fatura paga: data da compra 20/08/2031 (fatura 09/2031, paga): a compra vai para 10/2031;
   - fatura consolidada: data da compra 20/11/2031 (fatura 12/2031): teste "Não incluir" e "Confirmar inclusão";
   - confira que "Despesa recorrente" fica desabilitada, com a orientação.
8. Somente leitura: `usuario.h@teste.local` / `Senha-ficticia-H-2026`. Na página principal o atalho Despesa aparece desabilitado.
9. O banco é recriado a cada vez que a prévia sobe.

## 8. Ajuste final: Cartão de crédito (Proposta A, aprovada em 14/11/2026)

**Verificação antes de implementar:**
- No desktop, o campo "Meio de pagamento" do formulário de Despesas só existe na recorrência. A opção "Cartão" de lá é a recorrência no cartão, que o serviço e o banco recusam nesse formulário ("Despesas de cartão ficam no módulo de cartões"). No novo aplicativo, a recorrência no cartão é cadastrada na tela **Recorrências** (`criar_recorrencia_cartao`). A proposta de 14/11 dizia que ela não existia; isso foi corrigido nesta verificação, e a Proposta B (contrato próprio) pode reaproveitar essa função.
- A compra avulsa no cartão existe na tela **Lançamentos** ("Compra no cartão", `criar_compra`). Ela foi reaproveitada sem mudar regra.

**Decisões do titular:**

| Questão | Decisão |
|---|---|
| Proposta A: compra no cartão | Aprovada para o MOBILE-05 |
| Proposta B: recorrência no cartão | Adiada para contrato específico |
| Despesa avulsa | Conta a pagar ou Cartão de crédito |
| Despesa recorrente | As opções que o banco aceita hoje (Não informado, Boleto, Débito, PIX) |
| Atalho para somente leitura | Correção aprovada |

**Como funciona:**
- **Meio de pagamento**, logo após Descrição, Valor e Categoria: "Conta a pagar" (padrão) mantém o fluxo de antes, com vencimento e competência. O antigo "Meio de pagamento" da recorrência passou a se chamar "Pagamento da conta", para não repetir o nome.
- **"Cartão de crédito"**: vencimento e competência saem e entram:
  - Cartão, os ativos do perfil (um só cartão já vem escolhido);
  - Data da compra (hoje, em Brasília);
  - Parcelas, de 1 a 48;
  - Fatura, sugerida pelo fechamento do cartão (`sugerir_competencia`), com o mesmo texto da tela Lançamentos (`fechamento.js`);
  - "Usar a fatura sugerida", quando o usuário escolhe outro mês;
  - a prévia do parcelamento (2 ou mais parcelas), com os números de `previa_compra`, o plano que `criar_compra` grava.
- **Gravação:** `POST /api/cartoes/:id/lancamentos` → `criar_compra`, com o mesmo corpo da tela Lançamentos e a chave de idempotência (duplo toque grava uma vez).
  - **Fatura paga:** o banco manda a compra para a próxima fatura em aberto.
  - **Fatura consolidada:** a mesma pergunta do desktop, dentro do formulário ("Confirmar inclusão" ou "Não incluir"), com o total conferido sob trava pelo banco.
- **Uma coisa ou outra:** a compra entra na fatura do cartão e nenhuma conta a pagar é criada. Na Lista de Despesas aparece só a fatura.
- **Recorrência no cartão:** a caixa "Despesa recorrente" fica desmarcada e desabilitada, com a orientação "O cadastro de despesas recorrentes no cartão de crédito será disponibilizado em uma etapa posterior."
- **Confirmação:** "“Tênis” lançada no cartão", com "Compra lançada na fatura MM/AAAA do cartão X" (ou "em N parcelas: faturas MM/AAAA a MM/AAAA"), e os botões **Ver no cartão** (Cartões mobile, no mês e no cartão), **Nova despesa** e **Início**.
- **Sem regra nova:** nenhuma migration, nenhuma função nova no banco. A tela Lançamentos do desktop grava pelo mesmo serviço (`compras-servico.js`), e a regressão dela foi rodada.
- **MOBILE-06 (Registrar Lançamento):** deve integrar este fluxo (`compras-servico.js` e o bloco do cartão), sem segundo formulário nem função financeira redundante.
