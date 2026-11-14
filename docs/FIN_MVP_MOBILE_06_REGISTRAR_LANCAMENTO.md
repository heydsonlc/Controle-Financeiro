# FIN-MVP-MOBILE-06: Registrar Lançamento mobile

Sexta etapa da versão mobile. Vem depois de cinco MVPs homologados em 14/11/2026 e ainda não publicados: Página Principal, Lista de Despesas, Cartões, Receitas e Cadastro de Despesas.

O atalho **Lançamento** da página principal e o botão **Lançar** da barra abrem **a mesma página**, Registrar Lançamento. No topo fica um seletor compacto de operações; abaixo aparece o formulário **já existente** de cada uma, gravando pelos serviços do desktop. Não há formulário duplicado nem mecanismo financeiro novo.

**Situação:** implementado no ramo local `mobile-06-registrar-lancamento`, a partir do Cadastro de Despesas homologado (`ecb9080`). Não houve push, deploy nem migration. A publicação depende da homologação do titular e será avaliada junto com os demais MVPs mobile.

## 1. Inventário do desktop (antes de implementar)

**Tela Lançamentos** (`lancamentos.html`, tipos "Cartão de crédito", "Despesa direta" e "Entrada / crédito"):

| Fluxo | Formulário e campos | Gravação no novo aplicativo | Situação |
|---|---|---|---|
| Compra no cartão | Cartão, categoria da despesa, descrição, valor, data da compra, parcelas (1 a 48), mês da fatura sugerido pelo fechamento, prévia das parcelas (P14), observações | `criar_compra` (chave de idempotência; fatura paga manda para a próxima aberta; fatura consolidada só com confirmação do total; parcelas pelo `plano_compra`) | Disponível. No mobile, `compras-servico.js` (MOBILE-05) |
| Despesa direta | Categoria, descrição, valor, data (vencimento), observações; competência = mês da data; "pago" | `criar_despesa`, pendente; "pago" é recusado (o pagamento fica em Despesas, com conta e movimento) | Disponível |
| Abastecimento | Com a categoria **Combustível** (código `MOB_COMBUSTIVEL`), o bloco "Dados do Abastecimento": veículo, combustível compatível, hodômetro, preço por litro, litros calculados, cartão físico | `salvar_lancamento_abastecimento`: a despesa (conta a pagar ou compra **à vista** no cartão) e o abastecimento vinculados numa transação, validados pelas regras da Mobilidade (hodômetro, combustível do veículo, data não futura, repetição); reaproveita abastecimento já registrado na Mobilidade sem despesa; litros calculados no banco | Disponível |
| Entrada / crédito | Conta bancária, descrição, valor, data | **Recusado** no novo aplicativo ("Recebimento sem conta bancária não é registrado: use Receitas → Receber") | Não reproduzido. A receita entra pelo cadastro de Receitas (previsão) e é recebida em Receitas |
| A partir de documento | Sugestão financeira de um documento fiscal | Módulo de documentos | Fora do escopo |

**Outras telas com operações do contrato:**

| Fluxo | Onde fica no desktop | Gravação | Situação |
|---|---|---|---|
| Receita | Receitas → "Nova Fonte de Receita" (e o "+" das Receitas mobile, MOBILE-04) | `criar_receita`: a fonte nasce **prevista** na competência (recorrente: 12 meses); nada é recebido | Disponível |
| Despesa (conta a pagar) | Despesas → "Nova Despesa" (e a Nova Despesa mobile, MOBILE-05) | `criar_despesa` com recorrência, competência e vencimento; ou `criar_compra` no cartão | Disponível |
| Transferência | Contas Bancárias → "Transferência" (origem, destino, valor, data, descrição) | `transferir_entre_contas`: movimentos pareados de débito e crédito, contas ativas do perfil e diferentes, valor > 0, escritor único de pagamentos, chave contra reenvio; o saldo é o dos movimentos | Disponível |
| Abastecimento sem despesa | Mobilidade → "Registrar abastecimento" (`registrar_abastecimento`) | Só o registro operacional | Não usado: o contrato pede o registro financeiro junto (o fluxo de Lançamentos faz os dois) |

**Regras comuns:**
- **Permissões:** todas as funções exigem `pode_gerir_perfil` e o escritor único do perfil. Quem só lê é recusado pelo banco.
- **Duplicidade:** chave de idempotência por operação em todas as gravações.
- **Competência e data:**
  - despesa: mês anterior ao vencimento (formulário de Despesas) ou o informado;
  - despesa direta do abastecimento: mês da data;
  - compra: fatura pelo fechamento;
  - receita: a competência aberta;
  - transferência: a data.

## 2. O que foi feito

| Arquivo | Mudança |
|---|---|
| `web/src/lancamento-mobile.html`, `css/lancamento-mobile.css`, `js/lancamento-mobile.js` (novos) | Página fora da moldura: cabeçalho ("Registrar Lançamento" e perfil), seletor de 5 operações (grade 3 + 2 de botões pequenos), formulário abaixo e barra com Lançar ativo. Usa os estilos da Nova Despesa (`despesa-nova-mobile.css`, pela classe `mob-despesa-nova`); o CSS próprio é restrito a `body.mob-lancamento` |
| `js/despesa-formulario.js` (novo, extraído) | O formulário da Nova Despesa (MOBILE-05), **sem mudança de comportamento**, como módulo. Serve à Nova Despesa e às opções Despesa e Compra no cartão |
| `js/mobile-cartao.js` (novo, extraído) | O bloco "Cartão de crédito" (cartão, data, parcelas, fatura sugerida, prévia), comum à despesa e ao abastecimento |
| `js/mobile-formulario.js` (novo, extraído) | Campo com erro, par de campos, fila de pedidos aos serviços e a pergunta da fatura consolidada |
| `js/receita-formulario.js` (novo, extraído) | O "Nova receita" das Receitas mobile (MOBILE-04), **sem mudança de comportamento**, como módulo. Serve às Receitas e à opção Receita |
| `js/transferencia-formulario.js`, `js/abastecimento-formulario.js` (novos) | A transferência da tela Contas Bancárias e o abastecimento da tela Lançamentos, em versão mobile |
| `js/contas-servico.js` (novo) | Contas do perfil e a gravação da transferência, extraídas de `contas-bancarias-adaptador.js`; a tela do desktop passa a gravar por ele, **sem mudança** |
| `js/abastecimento-servico.js` (novo) | Formulário do abastecimento, cartões físicos, despesa direta e a gravação `salvar_lancamento_abastecimento`, extraídos de `lancamentos-adaptador.js`; a tela do desktop passa a gravar por ele, **sem mudança** |
| `js/despesa-nova-mobile.js`, `js/receitas-mobile.js` | Passam a usar os formulários comuns (as páginas continuam iguais) |
| `js/mobile-comum.js`, `js/inicio-mobile.js`, `js/despesas-mobile.js`, `js/cartoes-mobile.js`, `js/receitas-mobile.js` | `MODULOS_ATIVOS` ganha `lancamento` e `lancar`. A permissão (`ajustarCadastrosPelaPermissao`, pela `pode_gerir_perfil` de sempre) desabilita Despesa, Lançamento e Lançar para quem só lê, em todas as páginas mobile |
| `inicio.html` e as 5 páginas mobile | Atalho Lançamento e item Lançar apontam para `lancamento-mobile.html` |
| `js/sessao.js`, `scripts/homologacao_real/lote_real.py` | A página nova entra nas permitidas; os scripts novos, nas rotas locais |
| `tests/supabase_local.py`, `web/tests/e2e/run_e2e.py` | Cenário fictício: "Reserva G" (segunda conta) e "Flex G" (veículo flex) no Perfil G |
| testes | Novo: `mobile06_registrar_lancamento.spec.mjs`. Atualizados: `build.test.mjs` (teste novo da página; gravações nos serviços comuns), `mob08_inicio`, `mob01_despesas`, `mobile05_cadastro_despesas` (Lançar agora navega) |

**Serviços reutilizados:**
- `despesas-servico.js` (despesa, categorias);
- `compras-servico.js` (compra no cartão);
- `receitas-servico.js` (receita);
- `contas-servico.js` (transferência);
- `abastecimento-servico.js` (abastecimento);
- `perfil.js` (permissão);
- `fechamento.js` (textos da fatura sugerida e da consolidada).

**Não muda:**
- as telas do desktop;
- as regras de pagamento, recebimento, transferência e abastecimento;
- o banco, as migrations e a CSP;
- o comportamento dos cinco MVPs homologados, salvo o Lançar, que agora navega.

## 3. Comportamento

- **Abertura:** sem operação escolhida ("Escolha o tipo de lançamento."). A competência da página principal é só o ponto de partida; cada operação segue as próprias regras. O endereço guarda a operação (`?tipo=`).
- **Receita:**
  - o formulário das Receitas mobile: nome, tipo, descrição, valor base, recorrente, dia previsto e conta;
  - a receita nasce **prevista** na competência, nunca recebida;
  - a confirmação leva às Receitas, onde fica o Receber.
- **Despesa:** o formulário da Nova Despesa em "Conta a pagar", com vencimento, competência, recorrência, categoria e observações.
- **Compra no cartão:**
  - o mesmo formulário, já em "Cartão de crédito": cartão ativo, data, parcelas, fatura sugerida e prévia;
  - fatura paga manda a compra para a próxima em aberto; fatura consolidada só entra com confirmação;
  - a confirmação traz "Ver no cartão" (Cartões mobile, no mês e no cartão);
  - nenhuma conta a pagar é criada.
- **Transferência:**
  - campos: conta de origem e de destino, cada uma com o saldo; valor; data (hoje); descrição ("Transferência entre contas");
  - o destino não oferece a própria origem;
  - a confirmação mostra o valor, as contas e os saldos relidos do banco;
  - com menos de duas contas ativas: "Cadastre outra conta ativa para transferir.", como no desktop.
- **Abastecimento:**
  - veículo (um só já vem escolhido);
  - data (hoje, sem data futura);
  - hodômetro, com o último registrado como dica;
  - combustível compatível (flex: gasolina ou etanol);
  - preço por litro e valor total, com os litros calculados na tela, como o desktop (três casas);
  - descrição sugerida ("Abastecimento <veículo>");
  - meio de pagamento:
    - conta a pagar: pendente na competência do mês da data, paga depois pela Lista;
    - compra **à vista** no cartão: fatura sugerida e cartão físico, quando o cartão tem algum;
  - a confirmação mostra os **litros gravados pelo banco**.
- **Erros:** junto ao campo, inclusive os do banco (por exemplo, "Hodômetro menor que a leitura de …").
- **Salvar:** trava no primeiro toque; a chave de idempotência de cada serviço impede duplicar.
- **Confirmação:** compacta, com o acesso ao registro e **Novo lançamento** (a mesma operação, vazia). Nada redireciona sozinho.
- **Perda acidental de dados:** trocar de operação com dados preenchidos pede confirmação. Sair da página com dados faz o navegador perguntar. O Cancelar é intencional e volta à página principal sem gravar.
- **Somente leitura:**
  - atalho Lançamento e Lançar desabilitados em todas as páginas mobile ("Somente leitura neste perfil");
  - acesso direto ao endereço mostra só a mensagem;
  - o banco recusa as gravações.

## 4. Testes

**Unitários:** 112/112. `build.test.mjs` ganhou o teste da página:
- sem moldura, CSS restrito, as 5 operações;
- página e formulários sem consulta própria;
- um formulário de cada (Nova Despesa e Receitas usam os módulos comuns);
- `salvar_lancamento_abastecimento` e `transferir_entre_contas` só nos serviços comuns, também para as telas do desktop.

**Funcionais (`mobile06_registrar_lancamento.spec.mjs`, 8/8):**

| Requisito | Conferência |
|---|---|
| Abertura | Atalho Lançamento e Lançar da página principal → `lancamento-mobile.html?mes=2032-01`; o Lançar das outras páginas mobile leva à mesma página; 5 operações, nenhuma escolhida; Lançar ativo |
| Receita | "Bonus G", R$ 350,00, não recorrente: uma fonte e **uma previsão** de 01/2032, sem recebimento; nas Receitas mobile, a receber |
| Despesa | "Internet G", vencimento 10/02/2032 → competência 01/2032 (regra do desktop); duplo toque → uma conta; "Novo lançamento" recomeça vazio |
| Compra parcelada | "Fone G", 2 × R$ 150,00 no Master: prévia 01 e 02/2032; duplo toque → uma parcela em cada fatura; **nenhuma** conta a pagar; Cartões mobile mostra a compra |
| Transferência | Destino sem a origem; erros junto ao campo; R$ 123,45 de Conta G para Reserva G: saldo da origem −123,45 e do destino +123,45 (pelos movimentos); duplo toque → **um** movimento no destino |
| Abastecimento, conta a pagar | Flex G, etanol, 10.000 km, R$ 5,899/L, R$ 200 → 33,904 L na tela e na confirmação (banco); um abastecimento vinculado a uma conta a pagar de R$ 200 (Combustível, competência e vencimento na data) |
| Abastecimento, cartão | Sem campo de parcelas; hodômetro 9.000 → recusa do banco junto ao campo, nada gravado; 10.350 km, R$ 150 → compra à vista na fatura sugerida, abastecimento vinculado à compra |
| Perda de dados e cancelamento | Trocar de operação com dados pede confirmação (recusar mantém; aceitar limpa); sair pelo Voltar faz o navegador perguntar; Cancelar volta sem gravar |
| Somente leitura | Usuário H: Lançamento e Lançar desabilitados (também nas Receitas mobile); endereço direto sem operações; `transferir_entre_contas` e `salvar_lancamento_abastecimento` do leitor recusados |
| Responsividade | 320, 375, 390 e 430 px em cada operação (compra com prévia, abastecimento no cartão): sem rolagem horizontal, nada fora da tela, campos sem sobreposição |
| Segurança | Nenhuma chamada a `/api/` no servidor, nenhum erro de CSP ou de JS |

**Regressão por impacto:** 32 specs:
- os seis mobile;
- do desktop: Lançamentos (tela, parcelas P14, dois de abastecimento), Contas Bancárias, Movimentações, Contas, Mobilidade (tela e projeções), Receitas (tela e saldo), Cartões (tela, múltiplos, agrupamento e executado da fatura), Despesas (lista, pagamento em lote, cancelamento), Recorrências (três specs), Dashboard, Documentos (sugestão financeira), Perfis, Acesso e Moldura.

**152 aprovados, 3 reprovados, 9 não rodaram** (dependentes, no modo serial).

As 3 reprovações são as **preexistentes de recorrência**, com as mesmas mensagens das rodadas dos MVPs anteriores:
- `recorrencia.spec:262` ("Despesa e todas as futuras foram excluídas");
- `recorrencias_inativacao:85` (1366: a conta da recorrência não é gerada);
- `recorrencias_tela:115` ("gerados automaticamente até 02/2031").

**Nenhuma falha introduzida por este MVP.** As telas do desktop que agora gravam pelos serviços comuns (Lançamentos, com e sem abastecimento, e Contas Bancárias) passaram inteiras, e os cinco MVPs homologados também.

## 5. Ambiente e dados

- **Banco descartável local** (`run_e2e.py`). Nenhuma escrita em produção; nenhuma migration.
- **Usuário G (`usuario.g@teste.local`):** titular do "Perfil G (fictício)". É o mesmo login dos Cartões, Receitas e Nova Despesa.
- **Cenário novo:**
  - "Reserva G (fictícia)", segunda conta ativa, para a transferência;
  - "Flex G (fictício)", veículo flex sem abastecimentos;
  - o "Nubank Master G" já tinha o fechamento confirmado (MOBILE-05).
- **Usuário H (`usuario.h@teste.local`):** leitor do Perfil G.

## 6. Decisões e pendências (para o titular)

1. **"Entrada / crédito" da tela Lançamentos não entra:** o novo aplicativo recusa o recebimento sem conta bancária. A opção **Receita** é o cadastro de Receitas (a receita nasce prevista); receber continua em Receitas → Receber, com a conta e o movimento. Nenhuma receita é marcada como recebida automaticamente.
2. **Abastecimento pelo fluxo de Lançamentos**, não pelo "Registrar abastecimento" da Mobilidade: é o que grava a despesa e o abastecimento juntos, como o contrato pede. Compra parcelada não recebe abastecimento (regra do banco); por isso o abastecimento no cartão é sempre à vista.
3. **Litros:** o banco calcula e grava. A tela mostra a mesma conta antes de salvar (como o desktop) e o valor gravado na confirmação.
4. **Competência:** cada operação segue a sua regra. O mês da página principal só preenche o ponto de partida da despesa e da receita e o mês padrão da fatura quando o cartão não sugere.
5. **Formulários extraídos:** a Nova Despesa (MOBILE-05) e o "Nova receita" (MOBILE-04) viraram módulos comuns. Os testes dos cinco MVPs homologados continuam passando sem mudança de comportamento; só o Lançar passou a navegar.
6. **Somente leitura:** o contrato pede Lançamento e Lançar desabilitados. A mesma consulta já desabilitava o atalho Despesa; agora vale para todas as páginas mobile.
7. **Pendências fora do escopo:**
   - recorrência no cartão (Proposta B, contrato próprio; `criar_recorrencia_cartao` já existe na tela Recorrências);
   - a tela de Contas e Movimentações mobile (FIN-MVP-MOBILE-07), que poderá reaproveitar `contas-servico.js` e o formulário de transferência.

## 7. Homologação no Firefox

1. Prévia: `run_e2e.py --previa` → http://127.0.0.1:8790/__previa__/.
2. Se a prévia estiver logada com outra conta: **Mais → Sair**.
3. Entrar com `usuario.g@teste.local` / `Senha-ficticia-G-2026`.
4. Tocar em **Lançamento** na página principal, ou em **Lançar** na barra de qualquer página mobile.
5. Testar cada operação:
   - **Receita:** confira que ela nasce prevista, em Receitas;
   - **Despesa;**
   - **Compra no cartão:** Nubank Master G, parcelada, com a prévia;
   - **Transferência:** Conta G → Reserva G; confira os saldos na confirmação;
   - **Abastecimento:** Flex G, conta a pagar e cartão; a data é a de hoje.
6. Trocar de operação com dados preenchidos e tocar em Voltar com dados preenchidos.
7. Somente leitura: `usuario.h@teste.local` / `Senha-ficticia-H-2026`. Lançamento e Lançar aparecem desabilitados.
8. O banco é recriado a cada vez que a prévia sobe.
