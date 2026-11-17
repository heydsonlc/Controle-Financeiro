# FIN-MVP-CADASTRO-UNIFICADO-01 — Modal único e responsivo de cadastro de despesas

**Situação:** **Etapas 1 a 6 concluídas** no ramo local `cadastro-unificado-01`: diagnóstico, componente único, prévia dos seis
cenários e, com as decisões do titular de 16/11/2026, a **integração local nos três módulos** (desktop e celular), com a suíte
completa. **Sem push, sem deploy, sem migration.** Falta a homologação visual e funcional do titular na prévia. Testes só no banco
descartável, com dados fictícios.

Referência de produção: deploy `34264964` (16/11/2026), 68 migrations.

## 1. Diagnóstico dos formulários atuais

| Onde | Arquivos | O que cadastra hoje | Serviço / função |
|---|---|---|---|
| Despesas (desktop) | `paginas/contas.html` (`#modal-despesa`) + `js/original/despesas.js` | Despesa direta; recorrente (caixa "Despesa recorrente"); "Despesa já foi paga" (recusada pelo serviço); consórcio e recorrência no cartão aparecem, mas respondem "em migração" | `despesas-servico.js` → `criar_despesa` |
| Lançamentos (desktop) | `paginas/lancamentos.html` (`#form-lancamento`) + `js/original/lancamentos.js` | Cartão de crédito, Despesa direta (com "pago", recusado) e Entrada/crédito; bloco de abastecimento no próprio formulário | `lancamentos-adaptador.js` → `criar_compra`, `criar_despesa`, `salvar_lancamento_abastecimento` |
| Recorrências (desktop) | `paginas/recorrencias.html` (`#form-recorrencia`) + `js/original/recorrencias.js` + `recorrencias-adaptacoes.js` | Recorrência (conta, débito automático, cartão) e Consórcio (com "parcelas já pagas", P24) | `recorrencias-servico.js` → `criar_despesa` recorrente, `criar_recorrencia_cartao`, `criar_consorcio` |
| Nova Despesa (celular) | `despesa-nova-mobile.html` + `js/despesa-formulario.js` | Conta a pagar, compra no cartão, recorrente em conta; **recorrência no cartão bloqueada**; sem consórcio | `despesas-servico.js`, `compras-servico.js` |
| Registrar Lançamento (celular) | `lancamento-mobile.html` + `js/lancamento-mobile.js` | Despesa e Compra no cartão (o formulário acima), Receita, Transferência, Abastecimento | os mesmos + serviços próprios |
| Recorrências (celular) | `recorrencias-mobile.html` + `js/recorrencias-mobile.js` | Recorrência em conta, débito automático e cartão; sem consórcio | `recorrencias-servico.js` |

Os mesmos formulários também servem a **edição** no desktop (Despesas e Recorrências) e no celular (Recorrências). A edição fica
fora deste contrato e continua neles.

### Pontos encontrados na auditoria

1. **"Despesa já foi paga"** existe em dois formulários do desktop e já é recusada pelos serviços. No modal novo o campo não
   existe e nenhum corpo leva `pago`, `data_pagamento` ou conta de pagamento.
2. **Competência da despesa direta em Lançamentos (desktop):** hoje é o **mês da própria data** informada. Em Despesas e na
   Nova Despesa do celular é o **mês anterior ao vencimento**, com ajuste manual. O modal usa a regra de Despesas, com
   "Alterar competência". **Depende de decisão do titular** (seção 8).
3. **Abastecimento em Lançamentos (desktop):** o bloco "Dados do abastecimento" fica dentro do formulário atual e grava despesa e
   abastecimento numa transação. O modal não tem esse bloco, e a operação integrada precisa continuar (seção 8).
4. **Recorrência no cartão:** disponível em Recorrências (desktop e celular), bloqueada na Nova Despesa do celular e "em
   migração" no modal de Despesas do desktop. O modal novo usa o serviço de Recorrências em todos os pontos de entrada.
5. **Consórcio:** só é cadastrável hoje em Recorrências do desktop. No modal fica disponível em todos os pontos de entrada, pelo
   mesmo serviço e com a regra da P24.
6. **Meio de pagamento do consórcio:** o banco aceita cartão ou débito automático nas parcelas, mas o formulário atual esconde
   esses campos no modo consórcio. O contrato não os lista: o modal não envia meio de pagamento (parcelas como contas a pagar).
7. **Frequência semanal:** o formulário antigo de Despesas tem "Frequência (semanas)" de 1 a 52; o serviço só aceita 1 ou 2. O
   modal oferece "Semanal" e "A cada 2 semanas".
8. **Observações:** limite de 200 caracteres em Lançamentos (desktop) e 500 no celular. O modal usa 500, para não reduzir o que
   o celular já aceita (o modelo visual mostra 0/200).

## 2. Matriz de equivalência

Campo antigo → campo novo → regra de apresentação → campo enviado ao serviço.

### Despesa direta — `POST /api/despesas` → `criar_despesa`

| Campo antigo | Campo novo | Apresentação | Enviado |
|---|---|---|---|
| Nome (Despesas) / Descrição (Lançamentos, celular) | Nome | Sempre | `nome` |
| Valor | Valor | Sempre | `valor` |
| Categoria | Categoria | Sempre | `categoria_id` |
| Data de vencimento / Data | Data de vencimento | Sempre | `data_vencimento` |
| Mês de competência (campo inteiro) | "Competência: novembro/2026" + **Alterar competência** | Texto compacto; o campo abre pela ação ou quando há erro | `mes_competencia` |
| Descrição opcional / Observações | Observações | Recolhido em "+ Observações" | `descricao` |
| Despesa já foi paga, Data de pagamento | — (eliminados) | Não existem | nada (`recorrente: false`) |
| Despesa recorrente, É um Consórcio (caixas) | Tipo de operação | Seletor principal | — |

### Compra no cartão — `POST /api/cartoes/:id/lancamentos` → `criar_compra`

| Campo antigo | Campo novo | Apresentação | Enviado |
|---|---|---|---|
| Cartão | Cartão de crédito | Sempre; um só cartão ativo já vem escolhido | `cartao_id` |
| Categoria da despesa | Categoria | Sempre | `categoria_id` |
| Categoria do cartão (informativa) | — | Resolvida no banco pela categoria da despesa | nada |
| Descrição | Descrição | Sempre | `descricao` |
| Valor | Valor | Sempre | `valor` |
| Data | Data da compra | Sempre (hoje por padrão) | `data_compra` |
| Parcelas | Parcelas | Sempre (1 a 48) | `total_parcelas`, `numero_parcela: 1` |
| Mês da fatura + sugestão + "Usar a sugerida" | Mês da fatura | Sugestão do fechamento; nunca troca o mês escolhido | `mes_fatura` |
| Prévia das parcelas | Prévia do parcelamento | A partir de 2 parcelas | (só leitura: `previa_compra`) |
| Pergunta da fatura consolidada | A mesma pergunta, no modal | Só quando o serviço pede | `confirmar_consolidadas` |
| Observações | Observações | Recolhido | `observacoes` |

### Despesa recorrente — `POST /api/recorrencias` → `criar_despesa` (recorrente) ou `criar_recorrencia_cartao`

| Campo antigo | Campo novo | Apresentação | Enviado |
|---|---|---|---|
| Nome | Nome | Sempre | `nome` |
| Valor | Valor | Sempre | `valor` |
| Categoria | Categoria | Sempre | `categoria_id` |
| Data inicial | Data inicial (primeiro vencimento) | Sempre | `data_vencimento` |
| Frequência (mensal, semanal, quinzenal, anual) | Frequência | Sempre; semanal e quinzenal desabilitadas no cartão | `tipo_recorrencia` + `frequencia_semanas` (1 ou 2) |
| Dia da semana | Dia da semana | Só semanal e a cada 2 semanas | `dia_semana` |
| Meio de pagamento | Pagamento da conta | Conta a pagar (não informado, boleto, PIX, débito), Débito automático, Cartão de crédito; cartão desabilitado em semanal/quinzenal | `meio_pagamento` |
| Cartão + Categoria do cartão | Cartão de crédito + linha informativa | Só no cartão | `cartao_id` |
| Conta bancária | Conta bancária do débito automático | Só em débito automático (obrigatória) | `conta_bancaria_id` |
| Ativa (chave) | Cadastrar inativa | Em "+ Opções adicionais" | `ativo` |
| Observações | Observações | Recolhido | `descricao` |

O serviço grava a frequência como hoje (`mensal`, `anual`, `semanal_1_D`, `semanal_2_D`).

### Consórcio — `POST /api/consorcios` → `criar_consorcio`

| Campo antigo | Campo novo | Apresentação | Enviado |
|---|---|---|---|
| Nome | Nome do consórcio | Sempre | `nome` |
| Valor | Valor da parcela | Sempre | `valor_inicial` |
| Categoria | Categoria | Sempre | `categoria_id` |
| Número de parcelas | Número de parcelas | Sempre | `numero_parcelas` |
| Data inicial (o mês de início sai dela) | Mês de início | Sempre (mês atual por padrão) | `mes_inicio`, `data_inicial` (dia 1) |
| Tipo de reajuste | Tipo de reajuste | Sem reajuste, percentual, valor fixo | `tipo_reajuste` |
| Valor do reajuste | Reajuste por parcela | Só com reajuste | `valor_reajuste` |
| Mês de contemplação | Mês de contemplação | Opcional | `mes_contemplacao` |
| Valor do prêmio (somente leitura) | Valor do prêmio (calculado) | Informação; a conta é a da tela atual | nada (o banco calcula) |
| Parcelas já pagas antes do cadastro (P24) | O mesmo | Só com início anterior ao mês corrente | `parcelas_pagas_anteriores` |
| Observações | Observações | Recolhido | `observacoes` |
| Meio de pagamento, cartão, conta | — | Não oferecidos (item 6 da auditoria) | nada |

## 3. Arquitetura

- **`web/src/js/cadastro-despesa.js`** — o componente único.
  - `prepararCadastro(perfilId, { despesas, compras, recorrencias })`: aponta os três serviços para o perfil. A tela que já
    configurou um serviço com os ganchos dela passa `false` para ele.
  - `abrirCadastroDespesa({ origem, mes, tipoInicial, tipos, dados, destinos, aoSalvar, aoFechar })`: abre o modal e devolve uma
    Promise que termina quando ele fecha. Um cadastro por vez.
  - Um montador por tipo (`despesaDireta`, `compraCartao`, `despesaRecorrente`, `consorcio`), cada um com os campos, a validação
    visual e o corpo do seu serviço.
- **`web/src/css/cadastro-despesa.css`** — aparência única para desktop e celular (640 px, duas colunas; até 600 px, tela
  cheia com cabeçalho e rodapé fixos; até 339 px, uma coluna). Tudo sob `.cad-fundo .cad-modal`, para o tema de cada página não
  mudar o modal.
- **Reaproveitado sem mudança de regra:** `mobile-cartao.js` (cartões, fatura sugerida, prévia, validação da compra),
  `mobile-formulario.js` (campo com erro, fila de pedidos, pergunta da fatura consolidada), `mobile-ui.js`, e os três serviços.
- **Ajustes em código existente** (sem mudar comportamento):
  - `mobile-cartao.js`: rótulos opcionais dos campos e devolução da linha de sugestão e da prévia, para o modal posicioná-las;
  - `recorrencias-servico.js`: `criarConsorcio` aceita `parcelas_pagas_anteriores` no corpo (o campo da página continua valendo).
- **Sem função nova no banco e sem migration.**

### Regras do componente

- **Troca de tipo:** os campos do tipo são reconstruídos. Só nome, valor, categoria e observações seguem. Se a troca descartar
  algo já preenchido, o modal pergunta antes ("Manter" / "Trocar para …").
- **Um envio por vez:** Salvar fica bloqueado durante a gravação; depois da confirmação do servidor o formulário dá lugar à
  confirmação. As chaves de idempotência são as dos serviços.
- **Depois de salvar:** confirmação objetiva, "Novo cadastro" (mesmo tipo, em branco), link para o registro no módulo (quando a
  tela informa o endereço) e "Concluir". Nada redireciona sozinho. `aoSalvar` avisa a tela para atualizar a lista.
- **Somente leitura:** quem só lê o perfil recebe o aviso, sem formulário e sem Salvar (o banco recusaria de qualquer forma).
- **Cancelar, X e Esc:** fecham sem gravar. Clicar fora não fecha (evita perder o preenchimento).
- **Teclado virtual:** a altura do modal acompanha a área visível (`visualViewport`), para o rodapé não ficar sob o teclado.

## 4. Prévia local (Etapa 3)

```
POSTGREST_BIN=C:/Users/heyds/AppData/Local/cf-e2e/postgrest/postgrest.exe PYTHONIOENCODING=utf-8 ./venv/Scripts/python.exe -u web/tests/e2e/run_e2e.py --previa
```

- Entrar em `http://127.0.0.1:8790/index.html` com `usuario.g@teste.local` (leitura: `usuario.h@teste.local`).
- Abrir **`http://127.0.0.1:8790/__previa__/cadastro.html`**: botões dos seis cenários, dos pontos de entrada e a lista das
  gravações da sessão (tipo, serviço e campos enviados).
- Vários tamanhos lado a lado: em `http://127.0.0.1:8790/__previa__/`, usar a página `__previa__/cadastro.html?cenario=1`
  (1 a 6).

A página de demonstração (`web/previa/cadastro.*`) fica fora do dist e do deploy.

## 5. Testes desta entrega

| Verificação | Resultado |
|---|---|
| Ensaio funcional na prévia (os seis cenários gravando pelos serviços reais, troca de tipo, combinações inválidas, somente leitura, leituras no banco) | 40/40 |
| Ensaio de layout (6 cenários × desktop, tablet 820, celular 430, 390, 375 e 320): sem rolagem horizontal, rodapé visível | 36/36 |
| Modal aberto dentro de páginas reais (Despesas, Lançamentos e Recorrências do desktop; Nova Despesa e Recorrências do celular) | mesmas medidas e cores nas cinco |
| Unitários (`npm run -s test:unit`) | 127/127 |
| e2e das telas que usam o código alterado (seção 6) | 46/46 |

O que o ensaio funcional confirmou no banco descartável:

- despesa direta **Pendente**, sem data de pagamento, na competência calculada (vencimento 10/06/2031 → maio/2031);
- compra em 3 parcelas na fatura sugerida, com a prévia; nenhum campo de despesa direta no corpo;
- recorrências gravadas como `mensal` + boleto, `semanal_1_1`, `semanal_2_3`, mensal e anual no cartão, débito automático com
  conta e **inativa**;
- cartão indisponível em semanal/quinzenal e semanal/quinzenal indisponíveis no cartão;
- consórcio em andamento: 12 parcelas, 2 no histórico sem débito bancário, prêmio R$ 11.016,00 (850 × 1,08 × 12);
- nenhum corpo com `pago`, `data_pagamento` ou conta de pagamento.

O ensaio é um roteiro Playwright avulso contra a prévia. **As especificações e2e definitivas do modal entram na Etapa 5**, quando
ele estiver nas telas reais (a suíte normal não serve a página de demonstração).

## 6. Regressão por impacto

Código existente alterado: `mobile-cartao.js` e `recorrencias-servico.js`. Baterias selecionadas: `mobile05_cadastro_despesas`,
`mobile06_registrar_lancamento`, `lancamentos_03_parcelas`, `consorcios_p24`, `recorrencias_tela`, `mob09_recorrencias`.
Resultado: **46/46**. Dispensadas nesta entrega: as demais baterias (nenhuma tela de produção usa o modal ainda). A suíte
completa fica para a Etapa 6, depois da integração.

## 7. Funcionalidades preservadas

Nada foi retirado das telas: listagens, edição, pagamento, estorno, exclusão, cancelamento, inativação, reativação, filtros,
receitas, transferências, entrada/crédito, abastecimento e "A partir de documento" seguem como estão. Só o **cadastro** de
despesa mudou de formulário (seção 9).

## 8. Decisões do titular (16/11/2026)

| Item | Decisão | Como ficou |
|---|---|---|
| Competência | Preservar as regras atuais de cada origem | Aberto por **Lançamentos (desktop)**, o modal usa o mês da própria data, mostra a competência calculada e não oferece ajuste manual (a tela nunca ofereceu). Em **Despesas** e no **celular**, a regra do vencimento (mês anterior) com "Alterar competência". A padronização entre as duas fica para análise separada |
| Abastecimento | Exceção aprovada | O modal assume despesa comum e compra no cartão. O abastecimento continua no formulário especializado, numa única transação |
| Observações | 500 caracteres | Limite visual de 500 nos quatro tipos |
| Consórcio | Nos três módulos e no celular | Pelo serviço de consórcios existente, com parcelas, reajustes, contemplação e parcelas já pagas (P24), sem débito bancário |

## 9. Integração (Etapa 4)

| Tela | Como abre | Tipo inicial | O formulário antigo |
|---|---|---|---|
| Despesas (desktop) | "Nova despesa" (`abrirModal`, `abrirModalRecorrencia`, `abrirModalConsorcio`) | Despesa direta (ou o do atalho) | `#modal-despesa` continua para **editar** |
| Recorrências (desktop) | "Nova recorrência" | Despesa recorrente | O formulário lateral aparece **só na edição** e some ao salvar ou cancelar |
| Lançamentos (desktop) | Painel "Novo lançamento": **Despesa direta**, **Compra no cartão**, **Abastecimento**, **Entrada / crédito** | O escolhido na tela | Continua para abastecimento, entrada/crédito e edição |
| Nova Despesa (celular) | Atalho Despesa | Despesa direta | Removido (`montarFormularioDespesa`) |
| Registrar Lançamento (celular) | Tipos Despesa e Compra no cartão | O escolhido na tela | Receita, Transferência e Abastecimento seguem nos formulários deles |
| Recorrências (celular) | "+" | Despesa recorrente | O painel da página fica para **editar** |

- **Origem e retorno:** fechar (Cancelar, X, Esc ou Concluir) volta à tela que abriu, na mesma competência. Nas páginas do celular
  que só existem para cadastrar (Nova Despesa), volta-se à página principal na competência de origem. Depois de salvar, a lista
  da tela de origem é recarregada.
- **Um caminho por gravação:** em Lançamentos (desktop), o formulário do painel só cria despesa ou compra **com** abastecimento;
  sem ele, o adaptador recusa e orienta a usar "Despesa direta" ou "Compra no cartão". O código que gravava a despesa e a compra
  comuns por ali foi retirado.
- **Recorrência a partir de Despesas:** passa pelo serviço de Recorrências (antes, `criar_despesa` pelo serviço de Despesas). A
  função do banco é a mesma, com os mesmos dados; a geração continua a de Despesas.
- **Consórcio e recorrência no cartão:** disponíveis em todos os pontos de entrada, pelos serviços que já existiam.
- **Somente leitura:** os botões de cadastro continuam ocultos; em Lançamentos (desktop) o painel de cadastro também some.
- **"Despesa já foi paga" também fora da edição** (autorização de 16/11/2026): no modal de edição de Despesas, a caixa e a
  "Data de Pagamento" ficam ocultas; no formulário de Lançamentos, a caixa também. Pagar e estornar continuam nas ações
  próprias da lista, que escolhem a conta e registram o movimento.
- **Aviso da operação:** `recorrencias-servico.js` expõe o último aviso (`ultimoAviso`), para o modal mostrá-lo na confirmação
  sem tirar o aviso da tela que configurou o serviço.

### Arquivos

- Novos: `js/cadastro-despesa.js`, `css/cadastro-despesa.css`, `js/lancamentos-cadastro.js`, `tests/e2e/cadastro.mjs`,
  `tests/e2e/cadastro_unificado.spec.mjs`, `previa/cadastro.*`.
- Alterados (telas): `despesas-adaptador.js`, `recorrencias-adaptador.js`, `lancamentos-adaptador.js`, `despesa-nova-mobile.js`,
  `lancamento-mobile.js`, `recorrencias-mobile.js`, `despesa-formulario.js` (ficaram só as confirmações usadas por Transferência e
  Abastecimento), `css/lancamentos-adaptacoes.css`, as três páginas do desktop e as três do celular (folha de estilo do modal).
- Alterados (apoio, sem mudar regra): `mobile-cartao.js`, `recorrencias-servico.js`.
- **Sem migration e sem função nova no banco.**

## 10. Testes da integração (Etapas 5 e 6)

| Verificação | Resultado |
|---|---|
| Suíte e2e completa | **282/282** (antes da integração: 275; 6 do spec novo e 1 a mais no spec do celular) |
| Unitários | 127/127 (os dois testes de estrutura do celular passaram a conferir o modal único) |
| Spec novo `cadastro_unificado.spec.mjs` | 6/6 |

Specs adaptados ao modal (o cadastro deixou de ser pelo formulário antigo): `despesas`, `movimentacoes`, `recorrencia`,
`recorrencias_tela`, `consorcios_p24`, `lancamentos_tela`, `lancamentos_03_parcelas`, `lancamentos_abastecimento`, `cartoes_tela`,
`mobile05_cadastro_despesas`, `mobile06_registrar_lancamento`, `mob09_recorrencias`, `mobile_final_integrado`.

Cobertura da seção 14 do contrato:

- **Despesa direta:** cadastro, vencimento e competência (as duas regras), pendente, sem movimento bancário, pagamento
  posterior pelo fluxo existente, cancelamento sem gravação.
- **Compra no cartão:** à vista, parcelada, fatura sugerida, prévia, fatura paga e consolidada (com confirmação), sem conta a
  pagar duplicada.
- **Recorrências:** mensal e anual em conta, semanal, a cada 2 semanas, mensal e anual no cartão, semanal/quinzenal
  indisponíveis no cartão, débito automático com conta, cadastrada inativa, sem duplicar ocorrências.
- **Consórcios:** contrato novo, em andamento com parcelas anteriores, prêmio, reajustes fixo e percentual, contemplação,
  cronograma, nenhum movimento bancário; nome repetido recusado sem duplicar.
- **Integração:** os três pontos de entrada no desktop e no celular, tipo inicial, troca de tipo, retorno ao cancelar,
  confirmação, somente leitura, abastecimento, receitas e transferências preservados.
- **Visual:** desktop 1366 e 1920, celular em 320, 375, 390 e 430; cabeçalho e rodapé fixos; prévia longa; erros junto ao campo.

Não coberto por teste automático: teclado virtual real do celular (a altura do modal acompanha a área visível, mas isso só se
confere num aparelho).

## 11. Prévia da integração

Com a prévia no ar (seção 4), entrar com `usuario.g@teste.local` e abrir, em cada tamanho:

- Celular: `inicio.html` → atalhos **Despesa**, **Lançamento** e **Recorrências**.
- Desktop: `contas.html` (Nova despesa), `lancamentos.html` (painel Novo lançamento) e `recorrencias.html` (Nova recorrência).

A página de demonstração (`/__previa__/cadastro.html`) continua disponível para os seis cenários isolados.

## 12. Publicação e reversão (plano, sem autorização)

1. Homologação do titular na prévia.
2. Avanço rápido de `main` para o ramo e push.
3. Build de produção e deploy no Cloudflare Pages (`producao`). **Sem migration**: nenhum backup `PRE_MIGRATION` é exigido.
4. Conferência dos arquivos servidos e das três telas, sem gravar dado real.
5. Reversão: voltar ao deploy `34264964`. Nada no banco muda com este contrato.

**Publicação:** só com autorização do titular.
