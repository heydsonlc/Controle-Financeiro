# FIN-MVP-MOBILE-04: Receitas mobile

Quarta etapa da versão mobile. Vem depois da Página Principal (FIN-MVP-MOBILE-01), da Lista de Despesas (FIN-MVP-MOBILE-02) e dos Cartões (FIN-MVP-MOBILE-03), os três aprovados pelo titular em 14/11/2026. O atalho **Receita** da página principal mobile abre a lista de receitas da competência. A tela tem:
- resumo com Previsto, Recebido e Pendente;
- as receitas do mês e as atrasadas;
- detalhes num painel inferior, com as operações do desktop: receber, editar, estornar e cancelar a previsão;
- um "+" compacto no cabeçalho para cadastrar uma receita.

Os registros, o serviço e as regras são os da tela de Receitas do desktop, sem controle paralelo.

**Situação:** implementado no ramo local `mobile-04-receitas`, a partir dos Cartões (`e887f62`). Não houve push, deploy nem migration. A publicação depende da homologação do titular e será avaliada junto com os demais MVPs mobile.

## 1. Análise do desktop (antes de implementar)

| Ponto do contrato | Onde está no desktop | Como o mobile segue |
|---|---|---|
| Rotas, componentes e serviços | A tela original do Flask é `js/original/receitas.js`, que vem de `frontend/static/js/receitas.js` e não muda. Ela recebe as adaptações de `js/receitas-adaptacoes.js` e passa pelo adaptador (`js/receitas-adaptador.js`). As leituras são `receitas_fontes_tela`, `receitas_orcamentos_tela` (previsões do ano), `receitas_realizadas_tela` (recebimentos, com os estornados fora) e `contas_bancarias_tela` | As mesmas rotas e funções, agora no serviço comum `js/receitas-servico.js` |
| Agrupamento | **Não há grupos por categoria.** São dois painéis: "Receitas do mês" (competência escolhida, com os filtros Tipo e Busca) e "Receitas atrasadas" (competências anteriores do mesmo ano ainda não realizadas). Ordem: prevista, parcial e realizada; depois competência e nome | A lista do mês é compacta, sem grupo, na mesma ordem. As atrasadas ficam num bloco próprio, recolhido ao abrir, com a quantidade e o que falta receber |
| Competência e vencimento | A previsão (`receita_orcamento`) tem competência e, opcionalmente, data prevista. Sem a data, vale o dia previsto da fonte (limitado ao último dia do mês) | Legenda "Prev. 05/04" com a mesma conta (`montarDataPrevista`) |
| Previstas, recebidas e canceladas | A situação é calculada por linha: recebido ≥ previsto é "Realizada"; recebido abaixo do previsto é "Parcial"; sem recebimento é "Prevista". O recebimento estornado não conta. Previsão removida fica com valor 0 e sai da lista (FIN-MVP-SANEAMENTO-FINAL-01) | O mesmo cálculo (módulo puro conferido contra o original) e a legenda "· recebida" / "· parcial" |
| Cadastro | "Nova receita" abre "Nova Fonte de Receita" com nome, tipo, descrição, valor base mensal, recorrente, dia previsto, conta e ativa. `criar_receita` cria a fonte e a previsão na competência da tela; se recorrente, as 12 previsões a partir dela | "+" abre o mesmo formulário; a competência é a aberta no mobile |
| Edição | "Editar" abre **a fonte**, não a previsão do mês: `editar_fonte_receita`, inativar e `redefinir_fonte_receita`, que completa as previsões que faltam nos 12 meses a partir do mês atual. Depois de salvar, se houver previsões pendentes com outro valor, aparece a prévia "Atualizar previsões pelo valor-base" (`previa_atualizacao_previsoes` / `atualizar_previsoes_fonte`) | O mesmo formulário e a mesma prévia, com "Manter as previsões" ou "Atualizar N previsões" |
| Recorrência | Mensal. A fonte recorrente tem previsões gravadas; o novo aplicativo não mostra a linha "virtual" do Flask para o mês sem previsão. **Nada é gerado ao abrir a tela**: previsões só nascem no cadastro e no salvar da fonte | O mesmo. O spec confere que abrir e navegar não muda nenhuma previsão |
| Recebimento | "Confirmar/realizar" abre "Consolidar Receita": conta, valor (o que falta), data e justificativa. Com previsão, usa `receber_receita`: aceita parcial, outra data ou valor acima do previsto com justificativa obrigatória. O banco confere o que falta (`VALOR_MUDOU`), usa chave de idempotência, grava o recebimento, o crédito na conta e atualiza o saldo. Sem previsão, `receber_sem_previsao`. Contemplação de consórcio: `realizar_contemplacao_consorcio` | Os mesmos campos e o mesmo corpo, pelas mesmas rotas |
| Estorno | Só na linha "Realizada" com um recebimento (`estornar_recebimento`). Cria um débito compensatório; o recebimento fica no histórico e a previsão volta a pendente | O mesmo, com data e motivo obrigatórios |
| Cancelamento e exclusão | "Cancelar/ignorar" remove a previsão (`excluir_receita`): na fonte recorrente ela fica com valor 0 e "Removido pelo usuário". O banco recusa se já houver recebimento na competência. Excluir recebimento não existe no novo aplicativo; para corrigir, estorna-se | "Cancelar previsão" só aparece quando o banco aceita (prevista, sem recebimento, fora do consórcio). Recebimento não se exclui |
| Perfis | O banco exige `pode_gerir_perfil` em toda escrita; a tela marca `cf-somente-leitura` | O leitor vê a lista e os detalhes, sem "+" e sem ações. O spec confere que o banco recusa a escrita do leitor |

**Inconsistências e limitações do desktop, só documentadas (nenhuma regra mudou):**
1. **"Observações" do formulário da fonte não é gravada:** o JS do Flask não a envia. Por isso o mobile não mostra o campo.
2. **"Editar" altera a fonte, não a previsão daquele mês:** o modal "Planejar receita" existe no HTML, mas nenhum botão o abre. Para mudar o valor de um mês, muda-se o valor-base e confirma-se a atualização das previsões.
3. **"Cancelar/ignorar" aparece em todas as linhas do desktop**, inclusive onde o banco recusa (parcial, realizada). O mobile só mostra o que é executável.
4. **Atrasadas só do mesmo ano:** o desktop carrega as previsões do ano da competência; em janeiro, as de dezembro não aparecem como atrasadas.
5. **O filtro de ano do desktop vai do ano atual −3 ao +2:** 2031, usado nos testes, não é selecionável no desktop. A comparação mobile × desktop do spec usa o mês atual.
6. **A data padrão do estorno no desktop é a do UTC;** no mobile é a de Brasília.

## 2. O que foi feito

| Arquivo | Mudança |
|---|---|
| `web/src/js/receitas-servico.js` (novo) | O código de `receitas-adaptador.js`, sem alteração de regra: rotas, funções do banco, versões e chaves. Duas leituras da tela do desktop ganharam alternativa: (1) a competência da fonte nova vem dos filtros do desktop ou do gancho `competencia` da tela que configurou o serviço; (2) data e justificativa do recebimento vêm do modal "Consolidar" quando ele está aberto (desktop, como antes) ou do corpo do pedido (o desktop nunca as manda no corpo) |
| `web/src/js/receitas-adaptador.js` | Fica só com a moldura e o modo somente leitura, e registra `responderReceitas` na ponte, como antes |
| `web/src/js/receitas-lista.js` (novo) | Regras de leitura puras: `montarReceitasMes` do desktop já com as adaptações do novo aplicativo; separação do mês e das atrasadas com os filtros Tipo e Busca; totais; legenda; recebimentos da linha; ações possíveis |
| `web/src/receitas-mobile.html`, `css/receitas-mobile.css`, `js/receitas-mobile.js` (novos) | Página fora da moldura com cabeçalho (voltar, "Receitas" e perfil, Filtros, "+"), competência, resumo, lista, atrasadas e painel. CSS restrito a `body.mob-receitas`; lista, painel e formulários vêm de `mobile-modulo.css` (comum). Os dados vêm só pelo serviço, sem consulta própria ao banco |
| `web/src/inicio.html`, `js/mobile-comum.js`, `js/sessao.js` | O atalho Receita aponta para `receitas-mobile.html` e entra em `MODULOS_ATIVOS`; a página entra nas permitidas. A barra inferior não muda |
| `tests/supabase_local.py`, `web/tests/e2e/run_e2e.py` | Receitas fictícias no Perfil G (o mesmo login dos Cartões), gravadas pelas funções oficiais (seção 5) |
| testes | Novos: `web/tests/unit/receitas-lista.test.mjs` e `web/tests/e2e/mobile04_receitas.spec.mjs`. Atualizados: `build.test.mjs`, `mob08_inicio.spec.mjs` e `mob01_despesas.spec.mjs` (agora são três atalhos habilitados) |
| `scripts/homologacao_real/lote_real.py` | Os arquivos novos que citam rotas `/api/` entram nas rotas locais |

**Não muda:**
- as telas do desktop: HTML, CSS, `js/original/receitas.js` e `js/receitas-adaptacoes.js`;
- os módulos mobile anteriores, salvo o atalho;
- as regras de negócio, o banco, as migrations e a CSP.

**Reaproveitado:** `mobile-ui.js` (painel, campos, aviso), `mobile-modulo.css` (lista, linha, grupo, painel, formulários), `mobile-comum.js` (competência, atalhos, "Mais"/Sair), `perfil.js` e `sessao.js`, e `formatarCompetencia` de `despesas-grupos.js`.

## 3. Comportamento

- **Cabeçalho:** voltar | "Receitas" e o perfil | Filtros e "+". O "+" fica escondido para quem só lê. A competência vem da página principal (`?mes=`); as setas trocam o mês, e Início e Voltar levam o mesmo mês.
- **Resumo (uma linha):**
  - **Previsto** e **Recebido** são os cartões "Previsto" e "Realizado" da tela do desktop: a soma das linhas do mês, com os filtros.
  - **Pendente** é o que falta receber das linhas previstas e parciais, a conta do painel "Recebimentos pendentes" do desktop. Não é Previsto − Recebido, porque o recebido acima do previsto e as receitas pontuais não abatem o pendente de outra receita.
- **Linha:**
  - descrição | valor | seta;
  - abaixo, em cinza: "Prev. dd/mm" (pendente), "Prev. dd/mm · parcial" ou "Receb. dd/mm · recebida";
  - o valor é o previsto da pendente e o recebido da recebida, que aparece em cinza.
- **Atrasadas:** bloco "Receitas atrasadas (N) · a receber R$ …", recolhido ao abrir. A legenda das linhas traz a competência ("Mar/2031 · Prev. 05/03").
- **Detalhes:**
  - campos: descrição, tipo (a "categoria" da receita), competência, data prevista, valor previsto, valor recebido, falta receber, data do recebimento (ou a lista, se houver mais de um), conta, recorrência, situação e observações (da previsão e dos recebimentos, como "[ACIMA DO PREVISTO] …");
  - ações conforme a situação: **Receber** (prevista ou parcial); **Editar** (fonte da receita, fora do módulo de consórcios); **Estornar** (recebida com um recebimento); **Cancelar previsão** (prevista sem recebimento).
- **Receber:**
  - campos: conta (padrão: a da fonte), valor (padrão: o que falta), data (hoje) e justificativa (obrigatória acima do que falta; o banco confere);
  - o botão trava no primeiro toque, e o serviço manda a mesma chave da operação nos reenvios;
  - ao concluir: "Receita registrada com sucesso: R$ … em Conta …", e a lista e o resumo são relidos.
- **Nova receita ("+"):**
  - campos do desktop: nome, tipo, descrição, valor base, recorrente, dia previsto (só se recorrente) e conta;
  - nasce prevista na competência aberta (recorrente: 12 meses a partir dela) e volta à lista.
- **Editar:** o mesmo formulário, mais "Fonte ativa". Ao salvar, se houver previsões pendentes com outro valor, aparece a prévia (a partir de qual competência, o que muda e o que fica, com o motivo), com "Manter as previsões" ou "Atualizar N previsões".
- **Filtros:** Tipo e Busca, os do desktop. Valem para a lista do mês e para o resumo; as atrasadas não são filtradas, como no desktop.

## 4. Testes

**Unitários:** 110/110.
- `receitas-lista.test.mjs` (4) **roda o arquivo original do Flask** (`frontend/static/js/receitas.js`) com as adaptações do novo aplicativo numa VM sem tela e compara:
  - a lista inteira: linhas, campos e ordem, em 4 competências, num cenário com parcial, realizada acima do previsto, pontual sem fonte, fonte não recorrente sem previsão, fonte recorrente sem previsão, previsão removida, data prevista gravada em outro mês e contemplação de consórcio pendente;
  - a separação mês/atrasadas e os filtros Tipo e Busca (6 combinações);
  - os totais e a data prevista.
- `build.test.mjs`:
  - novo teste das Receitas mobile: sem moldura, CSS restrito, dados só pelo serviço, "+" escondido até saber se pode gravar, barra sem item novo;
  - mapa das funções de escrita apontando para `receitas-servico.js`;
  - página principal com três atalhos.

**Funcionais (`mobile04_receitas.spec.mjs`, 9/9):**

| Requisito | Conferência |
|---|---|
| Atalho, competência, navegação | Atalho Receita → `receitas-mobile.html?mes=2031-04`; troca de mês; Voltar e Início com o mês; barra sem item novo |
| Lista, ordem, totais | Linhas, valores e legendas na ordem do desktop; Previsto R$ 8.545,30, Recebido R$ 1.300,00, Pendente R$ 7.245,30 |
| Comparação com o desktop | No mês atual, a tela de Receitas do desktop no mesmo banco: Previsto e Realizado iguais aos do mobile, as mesmas 4 receitas |
| Atrasadas | Bloco recolhido, (1) e R$ 6.500,00; ao abrir, "Mar/2031 · Prev. 05/03" |
| Detalhes e ações | Prevista: Receber, Editar, Cancelar previsão. Parcial: Receber e Editar. Recebida: Editar e Estornar |
| Recebimento | Duplo toque → **um** recebimento (`dados_recebimento_receita`), falta 0, saldo da conta +R$ 6.500,00 |
| Acima do que falta | Sem justificativa, o banco recusa e nada é gravado; com justificativa, registra e a observação "[ACIMA DO PREVISTO]" aparece no detalhe; saldo conferido |
| Estorno | Motivo obrigatório; recebimento marcado como estornado; previsão volta a pendente; saldo −R$ 800,00 |
| Cancelar previsão | A linha sai; previsão com 0 e "Removido pelo usuário"; saldo inalterado |
| Cadastro | Nome e tipo obrigatórios; não recorrente; duplo toque → **uma** fonte e **uma** previsão (04/2031, R$ 350,00) |
| Edição | Descrição e valor-base gravados; prévia da atualização; "Manter" não muda as previsões gravadas |
| Filtros | Tipo (Aluguel) e Busca ("salário", sem acento no nome) |
| Somente leitura | Usuário H: mesma lista, sem "+" e sem ações; `receber_receita` do leitor é recusado pelo banco |
| Responsividade | 320, 375, 390 e 430 px: sem rolagem horizontal, nada fora da tela, título sem sobrepor os botões |
| Nada gerado ao abrir | Previsões de 2031 iguais antes e depois de abrir e navegar |
| Segurança | Nenhuma chamada a `/api/` no servidor, nenhum erro de CSP ou de JS |

**Regressão por impacto (N3):** 13 specs, **68/68 aprovados**:
- as quatro páginas mobile: `mobile04_receitas`, `mobile03_cartoes`, `mob01_despesas` e `mob08_inicio`;
- as telas do desktop que usam o serviço de Receitas ou as listas tocadas: `receitas_tela`, `receitas_saldo`, `receitas_dispensadas`, `consorcios_p24`, `dashboard_tela`, `movimentacoes`, `contas_bancarias_tela`, `moldura` e `contas`.

Não foram rodados os specs de recorrências, cartões do desktop e importações: nada deles mudou. As 3 falhas preexistentes de recorrência (`recorrencia.spec:262`, `recorrencias_inativacao` e `recorrencias_tela:115`, registradas no FIN-MVP-MOBILE-03) continuam como pendência à parte.

## 5. Ambiente e dados

- **Banco descartável local** (`run_e2e.py`). Nenhuma escrita em produção; nenhuma migration.
- **Usuário G (`usuario.g@teste.local`)**, titular do "Perfil G (fictício)", **o mesmo login dos Cartões mobile**. Tudo gravado pelas funções oficiais como o usuário G (`criar_receita`, `receber_receita`), na "Conta G (fictícia)".
- **Mês atual (Brasília),** para a homologação começar com dados:
  - "Salario G" recorrente R$ 6.500,00, dia 5, desde o mês anterior (o do mês anterior fica atrasado);
  - "Aluguel Sala G" R$ 1.200,00, dia 10, com R$ 500,00 recebidos;
  - "Gratificacao G" não recorrente R$ 800,00, recebida;
  - "Rendimento G" R$ 45,30, dia 1, previsto.
- **04/2031 (testes):**
  - as mesmas fontes com previsões avulsas: salário de 02 recebido, de 03 atrasado e de 04 previsto;
  - aluguel parcial (R$ 500,00), gratificação recebida e rendimento previsto.
- **Usuário H (`usuario.h@teste.local`):** leitor do Perfil G.
- Os Cartões do Perfil G não mudam (o spec dos Cartões passou igual). Os usuários A a F não mudam.

## 6. Decisões e limitações (para o titular)

1. **Sem grupos por categoria:** o desktop não agrupa receitas. O mobile mostra a lista do mês compacta e as atrasadas num bloco recolhido (o painel "Receitas atrasadas" do desktop), sem grupo artificial. Ao abrir, a lista do mês fica visível, porque recolhê-la esconderia tudo.
2. **Pendente:** é o que falta das previstas e parciais, a conta do painel "Recebimentos pendentes" do desktop, que não mostra esse total. Não é Previsto − Recebido.
3. **Previsto e Recebido são os da tela de Receitas**, não o "total de receitas" da tela Despesas e do Dashboard (`receitas_totais_do_mes`). Este conta, por exemplo, o recebido quando passa do previsto. Os números podem diferir nesses casos, como já diferem entre as duas telas do desktop.
4. **Editar = editar a fonte** (como o desktop). Mudar o valor de um mês só pelo valor-base e pela atualização das previsões. Salvar também completa as previsões que faltam nos 12 meses a partir do mês atual (regra do desktop: "1 previsão criada nos próximos meses").
5. **Ações só quando executáveis:**
   - sem "Cancelar previsão" na parcial;
   - sem estorno na parcial (o desktop só oferece na realizada);
   - sem excluir recebimento (corrigir = estornar).
6. **Rótulos:** "Recebida" e "Parcialmente recebida" no lugar de "Realizada" e "Parcial", e "Cancelar previsão" no lugar do ícone "Cancelar/ignorar". O "+" do cabeçalho segue a diretriz do contrato. Ele é a exceção às telas sem inclusão (Despesas, Cartões), que esperam o FIN-MVP-MOBILE-06.
7. **Observações da fonte** não aparecem no formulário porque o desktop não as grava (seção 1).

## 7. Homologação no Firefox

1. Prévia: `run_e2e.py --previa` → http://127.0.0.1:8790/__previa__/.
2. Se a prévia ainda estiver logada com outra conta, tocar em **Mais → Sair**.
3. Entrar com `usuario.g@teste.local` / `Senha-ficticia-G-2026` e tocar em **Receita** na página principal (mês atual).
4. Conferir o resumo, a lista e as "Receitas atrasadas" (o salário do mês anterior). Tocar nas receitas, receber o salário, receber o resto do aluguel (com valor acima do que falta, para ver a justificativa), estornar a gratificação, cancelar a previsão do rendimento, cadastrar pelo "+" e editar uma fonte.
5. Abr/2031 tem o cenário dos testes.
6. Somente leitura: `usuario.h@teste.local` / `Senha-ficticia-H-2026`.
7. O banco é recriado a cada vez que a prévia sobe.
