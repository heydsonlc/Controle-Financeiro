# FIN-MVP-MOBILE-07: Contas e Movimentações mobile

Sétima etapa da versão mobile. Vem depois de seis MVPs homologados em 14/11/2026 e ainda não publicados: Página Principal, Lista de Despesas, Cartões, Receitas, Cadastro de Despesas e Registrar Lançamento.

O atalho **Contas** da página principal abre a página **Contas**. Ela tem um seletor de conta, o saldo da conta escolhida e as movimentações do período, com o detalhe de cada uma. É **só consulta**: os dados e os cálculos são os da tela Contas Bancárias do desktop, e a única operação, a transferência, é a do Registrar Lançamento (MOBILE-06).

**Situação:** implementado no ramo local `mobile-07-contas-movimentacoes`, a partir do Registrar Lançamento homologado (`345e012`). Não houve push, deploy nem migration. A publicação depende da homologação do titular e será avaliada junto com os demais MVPs mobile.

## 1. Inventário do desktop (antes de implementar)

**Tela Contas Bancárias** (`contas-bancarias.html`, `js/original/contas_bancarias.js` + `js/contas-bancarias-adaptador.js`):

| Ponto do contrato | Como é no desktop (e no banco) |
|---|---|
| Cadastro e perfis | `public.conta_bancaria` do perfil (`pertence_ao_perfil`); lista por `contas_bancarias_tela` (status ATIVO ou INATIVO, por nome). Criar, editar, inativar e reativar exigem gestão do perfil |
| Saldo atual | `saldo = saldo_inicial + créditos − débitos` (`saldo_da_conta`); `saldo_atual` é o cache recalculado depois de cada movimento (`atualizar_saldo_conta`). A tela mostra o `saldo_atual` |
| Saldo inicial e ajustes | O saldo inicial só muda sem movimentos. Depois disso, "Ajustar saldo" cria um movimento **AJUSTE** (`ajustar_saldo_conta`), o único editável e excluível (`editar_ajuste_conta`, `excluir_ajuste_conta`) |
| Conferência | `conferir_saldo_conta`: saldo inicial, créditos, débitos, saldo calculado × registrado e divergência. Só diagnóstico, "não altera o saldo" |
| Movimentações | `public.movimento_financeiro`: tipo CRÉDITO ou DÉBITO, valor, descrição, data, origem e vínculos (`conta_id` despesa ou fatura, `fatura_id`, `receita_realizada_id`, `transferencia_id`, `financiamento_parcela_id`, `movimento_original_id` no estorno) |
| Extrato | `extrato_conta_bancaria(conta, início, fim, limite, incluir_saldo)`: mais recentes primeiro (data e id), saldo após cada movimento calculado no banco (considera o que veio antes do início), limite 200 na tela (máximo 1000). A tela não filtra por período nem por tipo; a função aceita início e fim |
| Transferências | `transferir_entre_contas`: DÉBITO na origem e CRÉDITO no destino, mesmo `transferencia_id`, origem TRANSFERENCIA, contas ativas e diferentes, chave contra reenvio |
| Pagamento de despesa e estorno | `pagar_despesa` (DÉBITO, `conta_id`) e `estornar_pagamento_despesa` (CRÉDITO compensatório, `movimento_original_id`): na Lista de Despesas |
| Recebimento e estorno | `receber_receita` (CRÉDITO, `receita_realizada_id`) e o estorno: em Receitas |
| Pagamento de fatura e estorno | `pagar_fatura` (DÉBITO com `fatura_id`; a fatura também é uma conta, então vem também o `conta_id`) e `estornar_pagamento_fatura`: nos Cartões. A **compra** no cartão não gera movimento; só o pagamento da fatura |
| Operações por movimento | Só editar ou excluir **ajuste**. Os demais não têm ação no extrato (pagamentos, estornos e transferências são desfeitos no módulo de origem) |
| Permissões | Leitura: `pode_acessar_perfil`. Escrita: `pode_gerir_perfil` e o escritor único do perfil |

**Tela Movimentações** (menu do desktop): é a tela Lançamentos (compras, despesas diretas e receitas). Ela não mostra movimentos bancários. O extrato da conta é o da tela Contas Bancárias.

## 2. O que foi feito

| Arquivo | Mudança |
|---|---|
| `web/src/contas-mobile.html`, `css/contas-mobile.css`, `js/contas-mobile.js` (novos) | Página fora da moldura: cabeçalho (voltar, "Contas" e perfil, Filtros e Transferir), seletor de conta, saldo, período (o mês, com as setas), lista de movimentações, painel de detalhe e de filtros, barra com os mesmos quatro itens. CSS restrito a `body.mob-contas` |
| `js/contas-movimentos.js` (novo, puro) | Natureza do movimento pelos vínculos, sinal pelo tipo, filtro por tipo, período do mês e o nome da conta no seletor. Nenhum saldo calculado. Teste próprio (`tests/unit/contas-movimentos.test.mjs`) |
| `js/contas-servico.js` | Ganha o extrato e a conferência (extraídos de `contas-bancarias-adaptador.js`, com as mesmas validações) e a origem do movimento (só leituras já existentes). Rotas `GET /api/contas/:id/movimentos`, `/conferir-saldo` e `/api/movimentos/origem` |
| `js/contas-bancarias-adaptador.js` | O extrato e a conferência passam pelo serviço comum; a tela do desktop **não muda** |
| `js/transferencia-formulario.js`, `js/lancamento-mobile.js` | A transferência do MOBILE-06 aceita a conta de origem (`&origem=`) e a confirmação leva a "Ver em Contas" |
| `inicio.html`, `js/mobile-comum.js`, `js/sessao.js`, `scripts/homologacao_real/lote_real.py` | Atalho Contas aponta para `contas-mobile.html` e entra em `MODULOS_ATIVOS`; a página nova nas permitidas e nas rotas locais |
| `tests/supabase_local.py`, `web/tests/e2e/run_e2e.py` | Cenário fictício: Reserva G com saldo inicial de R$ 1.500,00; despesa paga, despesa paga e estornada, transferência e ajuste no mês atual |
| testes | Novos: `mobile07_contas.spec.mjs` e `contas-movimentos.test.mjs`. Atualizados: `build.test.mjs` (teste da página; atalho Contas), `mob08_inicio`, `mob01_despesas` |

**Componentes reutilizados:**
- `mobile-comum.js` (competência, atalhos, Mais/Sair, permissão);
- `mobile-ui.js` (painel inferior, detalhes, campos, mensagens);
- `mobile-formulario.js` (fila de pedidos, moeda);
- a lista e as linhas de `mobile-modulo.css`;
- o seletor no padrão dos Cartões mobile;
- o painel de filtros no padrão das Receitas mobile;
- a transferência do MOBILE-06.

**Não muda:**
- as telas do desktop;
- as regras de saldo, pagamento, recebimento, estorno, transferência e ajuste;
- o banco, as migrations e a CSP;
- os MVPs homologados, salvo a confirmação da transferência, que ganha "Ver em Contas".

## 3. Comportamento

- **Seletor de conta:**
  - mostra as contas do perfil: as ativas, por nome, e depois as inativas ("· inativa"), que guardam histórico;
  - aparece só o nome do desktop; o tipo e a instituição entram apenas se duas contas tiverem o mesmo nome; nunca agência ou número;
  - trocar de conta atualiza o saldo e a lista na mesma página, e o endereço guarda a conta (`&conta=`).
- **Saldo atual:**
  - é o `saldo_atual` do banco (o mesmo da tela do desktop), um pouco maior que os demais valores, com o tipo e a instituição abaixo;
  - não é a soma das linhas, que podem estar filtradas;
  - se a conferência do desktop apontar divergência, aparece um aviso discreto ("Nada foi ajustado; confira no desktop").
- **Período:**
  - por padrão, o mês aberto na página principal, com as setas de mês;
  - nos filtros: "De" e "Até", a mesma consulta do desktop, com início e fim; com intervalo, as setas ficam desabilitadas e o rótulo mostra as datas;
  - tipo de movimentação: entradas, saídas, transferências, estornos, pagamentos de despesa, recebimentos, pagamentos de fatura e ajustes.
- **Lista:**
  - a ordem do extrato do desktop (mais recentes primeiro);
  - cada linha: **Data | Descrição** (com a natureza abaixo) **| Valor | Detalhes**;
  - sinal "+" no crédito e "−" no débito; a entrada em verde discreto (a cor de confirmação da aplicação), a saída na cor normal;
  - descrição longa é cortada sem empurrar o valor;
  - acima de 200 movimentos no período, aviso para escolher um período menor (o limite do desktop).
- **Detalhe** (painel inferior, só leitura):
  - data, descrição, valor, conta, tipo, origem e saldo após o movimento (do banco);
  - **Pagamento de despesa:** a despesa, a competência e a situação, com "Ver na Lista de Despesas";
  - **Estorno:** o movimento original e a despesa;
  - **Transferência:** a outra conta, com "Ver a outra conta";
  - **Pagamento de fatura:** cartão, competência e situação, com "Ver no cartão";
  - **Recebimento:** "Ver em Receitas";
  - **Ajuste:** nota de que ajuste só se mexe no desktop;
  - o único botão é Fechar; estorno e cancelamento ficam no módulo de origem, que preserva as regras.
- **Transferir** (ícone ⇄ no cabeçalho):
  - abre o formulário do Registrar Lançamento já com a conta como origem;
  - a confirmação leva de volta às Contas, com o saldo relido;
  - fica escondido para quem só lê e para conta inativa.
- **Somente leitura:** consulta contas, saldos, movimentos e detalhes, sem Transferir; Lançar desabilitado, como nas outras páginas.
- **Sem cadastro, edição, exclusão de conta nem ajuste de saldo.**

## 4. Comparação de saldos com o desktop

- **Fonte única:** o saldo do mobile é o mesmo campo que a tela Contas Bancárias mostra (`contas_bancarias_tela.saldo_atual`). O spec confere:
  - o saldo do mobile é igual ao da função do banco;
  - a linha da conta na tela Contas Bancárias do desktop, no mesmo banco, mostra o mesmo valor;
  - `conferir_saldo_conta` é **consistente** em todas as contas do Perfil G;
  - na Reserva G, o saldo inclui o saldo inicial de R$ 1.500,00 e é **diferente** da soma das linhas: prova de que a tela não soma linhas.
- **Consulta não grava:** depois de filtros, troca de conta e de mês, os saldos de todas as contas são os mesmos de antes e a conferência continua consistente.
- **Divergências:** nenhuma no ambiente de teste. Se houver em algum perfil, o mobile só avisa; a correção continua no desktop (ajuste de saldo), sem nada automático.

## 5. Testes

**Unitários:** 116/116.
- `contas-movimentos.test.mjs` (3): natureza pelos vínculos, sinal e filtro por tipo, período do mês (inclusive fevereiro bissexto) e identificação da conta.
- `build.test.mjs`, teste da página:
  - sem moldura, CSS restrito, barra com os quatro itens, sem "Nova conta";
  - página só com o serviço comum e nenhuma gravação;
  - transferência pelo MOBILE-06;
  - sem ajuste nem cadastro no serviço;
  - a tela do desktop lê o extrato pelo mesmo serviço.

**Funcionais (`mobile07_contas.spec.mjs`, 8/8):**

| Requisito | Conferência |
|---|---|
| Abertura e saldo | Atalho Contas → `contas-mobile.html?mes=`; contas do perfil no seletor (só o nome); saldo = banco = tela do desktop; conferência consistente; Transferir com a origem |
| Movimentações | Mesma quantidade e mesma ordem do `extrato_conta_bancaria` do mês. Pagamento de despesa (− R$ 180,00), pagamento estornado (− R$ 99,90 e + R$ 99,90 de estorno), transferência enviada (− R$ 300,00), recebimento (+ R$ 800,00) e pagamento de fatura (− R$ 100,00), cada um com a sua natureza; entrada destacada |
| Troca de conta | Reserva G: saldo do banco, transferência recebida, ajuste + R$ 12,34; saldo ≠ soma das linhas (saldo inicial) |
| Detalhes | Despesa (Energia G, Pago, Lista de Despesas); estorno (movimento original, Academia G); transferência (Reserva G, outra conta); fatura (Nubank Master G · Set/2031, Paga, Cartões); recebimento (Receitas); ajuste (só no desktop). Só o botão Fechar |
| Filtros | Entradas; estornos; período do dia 1 ao 5 (mesma contagem do extrato com início e fim); rótulo do intervalo; data inicial maior recusada; Limpar; mês anterior e seguinte. Nenhum saldo mudou e a conferência continuou consistente |
| Transferência | Transferir → formulário do MOBILE-06 com a origem; duplo toque → uma transferência; "Ver em Contas" → saldo −10,00 (banco) e o movimento na lista |
| Somente leitura | Usuário H: saldo, movimentos e detalhe; sem Transferir; Lançar desabilitado; só Fechar |
| Responsividade | 320, 375, 390 e 430 px, lista e detalhe abertos: sem rolagem horizontal, nada fora da tela, data, descrição e valor sem sobreposição |

**Regressão por impacto:** 28 specs:
- os sete mobile;
- do desktop: Contas Bancárias, Movimentações, Contas, pagamento de contratos, Lançamentos, Despesas (lista, pagamento em lote, cancelamento), Receitas (tela e saldo), Cartões (tela, múltiplos, agrupamento e executado da fatura), Recorrências (três specs), Dashboard, Perfis, Acesso e Moldura.

**142 aprovados, 3 reprovados, 9 não rodaram** (dependentes, no modo serial).

As 3 reprovações são as **preexistentes de recorrência**, com as mesmas mensagens das rodadas anteriores:
- `recorrencia.spec:262` ("Despesa e todas as futuras foram excluídas");
- `recorrencias_inativacao:85` (1366: a conta da recorrência não é gerada);
- `recorrencias_tela:115` ("gerados automaticamente até 02/2031").

As 9 que não rodaram continuam registradas como cobertura incompleta.

**Nenhuma falha introduzida por este MVP.** A tela Contas Bancárias do desktop, que agora lê o extrato e a conferência pelo serviço comum, passou inteira, assim como os seis MVPs homologados.

## 6. Ambiente e dados

- **Banco descartável local** (`run_e2e.py`). Nenhuma escrita em produção; nenhuma migration.
- **Usuário G (`usuario.g@teste.local`):** titular do "Perfil G (fictício)", o mesmo login dos demais módulos mobile.
- **Contas:**
  - "Conta G (fictícia)", conta corrente;
  - "Reserva G (fictícia)", poupança, com saldo inicial de R$ 1.500,00.
- **Movimentos do mês atual, gravados pelas funções oficiais:**
  - recebimentos de Receitas (MOBILE-04);
  - pagamento da fatura de 09/2031 do Master (MOBILE-05);
  - "Energia G" paga;
  - "Academia G" paga e estornada;
  - transferência de R$ 300,00 da Conta G para a Reserva G;
  - ajuste de + R$ 12,34 na Reserva G.
- **Usuário H (`usuario.h@teste.local`):** leitor do Perfil G.

## 7. Decisões e limitações (para o titular)

1. **Só consulta.** Nenhuma operação nova. Pagar, receber, estornar e cancelar continuam nos módulos de origem; o detalhe leva até eles. Ajustes, só visualização. Cadastro de conta, só no desktop.
2. **Movimentações = extrato da conta** (tela Contas Bancárias). A tela "Movimentações" do desktop é a de Lançamentos, que não mostra movimentos bancários.
3. **Filtro por período** usa a mesma consulta do desktop (início e fim). **Filtro por tipo** é aplicado sobre o extrato do período, pelos vínculos que o banco grava. Não há busca por descrição, porque o desktop não tem.
4. **Limite de 200 movimentos por consulta**, como o desktop, com aviso quando atingido.
5. **Contas inativas** aparecem no seletor (histórico), sem Transferir.
6. **Seletor só com o nome** da conta; tipo e instituição entram apenas para nomes repetidos (o quadro do saldo já os mostra).
7. **Confirmação da transferência (MOBILE-06)** passou a oferecer "Ver em Contas" como caminho principal, no lugar de "Início", que continua entre as ações.
8. **Cores:** entrada em verde discreto, a cor de confirmação já usada na aplicação; saída na cor normal; sem outros indicadores.

## 8. Homologação no Firefox

1. Prévia: `run_e2e.py --previa` → http://127.0.0.1:8790/__previa__/.
2. Se a prévia estiver logada com outra conta: **Mais → Sair**.
3. Entrar com `usuario.g@teste.local` / `Senha-ficticia-G-2026`.
4. Na página principal, tocar em **Contas**.
5. Conferir:
   - o saldo e as movimentações do mês da Conta G;
   - trocar para a Reserva G;
   - abrir o detalhe de cada tipo de movimento: despesa, estorno, transferência, fatura, recebimento e ajuste.
6. Usar os filtros: tipo e período ("De" e "Até"), Limpar e as setas de mês.
7. Tocar em **⇄ Transferir**, transferir e voltar com "Ver em Contas".
8. Somente leitura: `usuario.h@teste.local` / `Senha-ficticia-H-2026`.
9. O banco é recriado a cada vez que a prévia sobe.
