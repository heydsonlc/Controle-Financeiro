# FIN-ESCRITOR-UNICO-FINAL-1 — Proteção integral das escritas (Flask e Supabase)

**Regra:** a atribuição do perfil (`financeiro.gerador_recorrencia`) decide quem escreve.
- **Perfil FLASK:** só o Flask grava; o novo aplicativo recusa (`SISTEMA_FLASK`).
- **Perfil NOVO:** só o Supabase grava; o Flask recusa (409 `SISTEMA_NOVO`).
- Consultas continuam nos dois.

**Restrições cumpridas:**
- Migration **só local**.
- Sem commit, push ou publicação.
- `gastos.db` e dados reais intocados.
- Nenhum perfil real transferido.

## 1. Operações que estavam desprotegidas

**No Supabase:** 29 funções de escrita expostas a `authenticated` gravavam em perfil ainda no Flask (já listadas em `FIN_ESCRITOR_UNICO_CONTAS_1.md` §3.1, mais a gestão do perfil). Exigiam só a gestão do perfil e, em alguns casos, a versão do registro.

| Área | Funções |
|---|---|
| Despesas e recorrências | `criar_despesa`, `editar_despesa`, `excluir_despesa`, `editar_recorrencia`, `inativar_recorrencia`, `reativar_recorrencia`, `definir_meio_pagamento_recorrencia`, `dispensar_aviso_recorrencia` |
| Receitas (previsões e fontes) | `criar_receita`, `editar_receita`, `excluir_receita`, `editar_fonte_receita`, `inativar_fonte_receita` |
| Cartões, limites, compras e lançamentos | `criar_cartao`, `editar_cartao`, `inativar_cartao`, `vincular_limite_cartao`, `atualizar_limite_cartao`, `desativar_limite_cartao`, `criar_compra`, `editar_compra`, `excluir_compra`, `editar_lancamento_cartao`, `editar_parcelas_futuras`, `cancelar_parcelas_futuras` |
| Importação | `importar_fatura_cartao` |
| Gestão do perfil | `atualizar_perfil`, `inativar_perfil`, `reativar_perfil` |

**Já protegidas antes e não reimplementadas:**
- pagamentos e estornos (despesa, fatura, receita);
- geração do mês;
- contas bancárias, ajustes e transferências;
- recorrência no cartão;
- Categorias do Cartão (`exigir_escrita_categoria_cartao`);
- consórcios;
- financiamentos (FIN-FINANCIAMENTOS-MOTOR-1).

**No Flask:** a guarda cobria só consórcios, financiamentos e contas bancárias (o blueprint inteiro), além de pagamento, estorno, geração e jobs. **O cadastro e a edição de despesas, recorrências, receitas, cartões, importação, Categorias do Cartão, seguros de financiamento e perfis gravavam em perfil NOVO.**

## 2. Guardas implementadas

**Supabase** (migration `20261124090000`):
- Nova função `financeiro.exigir_escrita_novo(perfil, inativo_ok)`, que verifica, nesta ordem:
  - quem gere o perfil ativo (`pode_gerir_perfil`), senão 42501; só a gestão do próprio perfil (editar, inativar, reativar) aceita perfil inativo, pelo vínculo de gestão;
  - a mesma trava do Flask (`pg_advisory_xact_lock(20261023, perfil)`);
  - perfil NOVO, senão `SISTEMA_FLASK`, sem gravar nada.
- Cada uma das 29 funções é o texto da sua última definição com **uma** linha marcada no início (mesma assinatura e privilégios).
- A ordem preserva os códigos de antes: quem só lê ou não tem vínculo continua recebendo 42501.

**Flask:**
- `registrar_guarda_escritor_unico(blueprint, módulo, isentos, perfil_da_rota)`, em `backend/services/gerador_recorrencia_service.py`.
- É um `before_request` do blueprint inteiro: para POST, PUT, PATCH e DELETE, usa `flask_pode_gerar` sobre o perfil da rota ou, na falta dele, sobre o perfil ativo (o escopo das consultas do Flask).

| Blueprint | Perfil verificado | Fora da guarda (só leem) |
|---|---|---|
| `despesas` | ativo | — |
| `recorrencias` | ativo | — |
| `receitas` | ativo | — |
| `cartoes` | ativo | `revelar_codigo_seguranca` |
| `importacao_cartao` | ativo | `analisar`, `upload_csv`, `previsualizar`, `sugerir_categorias` |
| `categorias_cartao` | ativo | — (o catálogo global `categorias` fica de fora: continua no Flask) |
| `financiamento_seguro` | o do contrato | — |
| `perfis_financeiros` | o da rota (`perfil_id`) | criar perfil, perfil padrão e perfil ativo (preferências do usuário) |

- Sem a configuração no banco (SQLite, migration ausente), o comportamento é o de antes.
- Se a verificação falhar, a escrita é bloqueada.

## 3. Testes

**`tests/test_supabase_escritor_unico_final.py`** (5 testes):
- As 29 funções num perfil no Flask: `SISTEMA_FLASK` e **nenhuma tabela alterada** (digest de `public` e `financeiro`).
- Usuário sem gestão: 42501 em todas.
- Perfil NOVO grava; reenvio pela mesma chave não duplica; de volta ao Flask, a mesma escrita é recusada.
- O Flask, com o perfil NOVO, responde 409 `SISTEMA_NOVO` em sete escritas (despesa, recorrência, fonte de receita, cartão, Categoria do Cartão, importação e edição do perfil) e **não grava nada**. A prévia da importação e o catálogo global de categorias continuam.
- O Flask, com o perfil no Flask, grava.

**Suítes ajustadas:**
- As que gravavam pelo novo aplicativo em perfil fictício ainda no Flask passaram a atribuir o perfil ao novo aplicativo (cartões, cartões/tela, receitas, importação, gestão de perfis).
- Nos testes de equivalência, a cópia do novo aplicativo é atribuída a ele.
- Nos testes que verificam uma recusa própria do Flask (fatura paga, conta paga), o perfil volta ao Flask antes de o Flask agir, para a recusa testada continuar sendo a original.

**Testes que codificavam a regra antiga** (dois escritores no cadastro) e **mudaram de expectativa de propósito:**
- `test_supabase_despesas.py::test_perfil_no_flask_nao_exclui_nem_move_conta_recorrente` e `test_perfil_no_flask_nao_muda_o_calendario_da_recorrencia`: com o perfil no Flask, o novo aplicativo editava o valor; agora recusa tudo, e nada muda.
- `test_supabase_despesas.py::test_equivalencia_com_o_flask_no_cadastro`: o Flask cadastrava no perfil migrado; agora a comparação é com o Flask no perfil dele.
- `test_supabase_gerador_t1.py::test_2_perfil_migrado_flask_cadastra_recorrencia_sem_gerar_contas`: o Flask cadastrava no perfil migrado (201, sem gerar); agora 409, sem gravar.

**Suítes do Flask com PostgreSQL que alternavam os dois aplicativos no mesmo perfil:**
- `test_cartoes_fechamento.py`: o Flask é chamado pelas rotas; um invólucro local passa o Pessoal ao Flask durante a chamada e o devolve ao novo aplicativo depois, como numa transferência do escritor.
- `test_cartoes_d6_integridade.py`, `test_fatura_integridade.py`, `test_recorrencia_pendencia.py`: o processo Flask age pelos **serviços** e é um teste de travas e concorrência no banco; o perfil é atribuído ao novo aplicativo para o lado dele.
- `test_pagamento_trava.py`: a compra do novo aplicativo durante um pagamento do Flask espera a mesma trava e então é **recusada** (perfil do Flask). Antes ia para a fatura seguinte; a expectativa mudou de propósito.
- `test_cartoes_pagamento.py`:
  - a consolidação pelo Flask acontece antes de o perfil passar ao novo aplicativo;
  - na compra durante o pagamento, o Flask **espera a mesma trava e então recusa** (409), sem gravar, e só a compra do novo aplicativo vai para a fatura seguinte. Essa expectativa mudou de propósito.

**E2E** (o Pessoal segue no Flask na semente; o Perfil B, no novo aplicativo):
- `despesas.spec.mjs`: o cadastro completo passou ao Perfil B; novo teste confirma que, no Pessoal, o cadastro é recusado sem gravar.
- `cartoes_tela.spec.mjs`, `perfis_gestao.spec.mjs`, `recorrencias_tela.spec.mjs`: no Pessoal, a recusa agora é a do escritor único.
- **Tela de Configurações** (`web/src/js/configuracoes.js`): só grava os dados do perfil quando eles mudam. Tornar padrão, que é preferência do usuário (`definir_perfil_padrao`, fora da guarda nos dois aplicativos), continua valendo para perfil do Flask.

**Regressão:** §6.

## 4. Operações ainda pendentes (sem dois escritores hoje)

Nestes módulos o novo aplicativo **só consulta**, então não há escrita concorrente. A guarda do Flask entra no mesmo MVP que liberar a escrita no Supabase:

| Módulo | Rotas de escrita no Flask | MVP |
|---|---|---|
| Patrimônio | `patrimonio` (9) | FIN-PATRIMONIO-2 |
| Mobilidade | `veiculos` (15), `despesas_previstas` (3), `mobilidade_app` (3) | FIN-MOBILIDADE-2 |
| Documentos e IR | `ir` (14), `ocr_tools` (3) | FIN-DOCUMENTOS-2 |
| Configurações e backup | `preferencias` (1), `backup` (7, já com guarda própria) | FIN-RELATORIOS-CONFIG-1 |

**Catálogos globais, sem perfil, escritos só pelo Flask por decisão:**
- categorias de despesa;
- índices (`indexadores`).

**Escrita de despesa pelo módulo de Categorias do Cartão** (vincular/desvincular): já tem guarda no Supabase; no Flask, agora fica pela guarda do blueprint.

## 5. Migrations

- **`20261124090000_financeiro_escritor_unico_final.sql`** (local, não aplicada):
  - 1 função nova (`exigir_escrita_novo`);
  - 29 substituídas, cada uma com uma linha marcada;
  - nenhuma tabela nem dado.
- **Reversão:** `supabase/reversao/20261124090000_escritas_sem_escritor_anterior.sql` (as 29 definições anteriores; remove a guarda).
- Não depende da `20261123090000` (motor de Financiamentos). Pela ordem das versões, a 1123 é aplicada antes.

## 6. Regressão

- **Pasta `tests/` inteira** (Flask em SQLite e em PostgreSQL, Supabase): **1900 passaram**, 20 pulados.
  - As 5 falhas restantes já existiam antes e não têm relação com este MVP (P7): `test_receitas_ux`, `test_categorias_sistemicas_mobilidade`, `test_ocr_tools` (2) e `test_veiculos_mobilidade_2b`.
- **E2E completo:** **92 passaram, 0 falhas** (91 + o novo teste de recusa no Pessoal).
- **Unitários do `web/`:** 30 passaram.

## 7. Riscos para a transferência de perfis reais

1. **Depois de aplicar a 1124, os perfis reais (no Flask) ficam só de consulta no novo aplicativo também nos cadastros.** Hoje isso já valia para pagamentos. A tela do novo aplicativo continua mostrando os botões, e a recusa vem com a mensagem "Este perfil ainda é administrado pelo sistema atual (Flask). Nada foi gravado."
2. **Patrimônio, Mobilidade, Documentos e IR continuam graváveis só pelo Flask, mesmo em perfil NOVO** (§4). Transferir um perfil antes desses MVPs significa que esses módulos continuam no Flask para ele. Não há dois escritores, mas os módulos ficam divididos entre os aplicativos.
3. **Escopo pelo perfil ativo no Flask:** a guarda usa o perfil ativo da sessão, que é o filtro das consultas do Flask. Uma rota que gravasse registro de outro perfil sem filtrar escaparia. Não encontrei nenhuma nos blueprints protegidos, e pagamento e estorno continuam com a guarda pelo registro.
4. **Catálogo global de categorias:** continua escrito só pelo Flask. Uma categoria nova criada no Flask aparece para os perfis NOVO, porque a leitura é compartilhada.
5. **Operação de transferência:** trocar a atribuição do perfil continua sendo um procedimento administrativo (`definir_gerador_recorrencia`), com trava e histórico. Não houve mudança.

## 8. Arquivos

- **Novos:**
  - `supabase/migrations/20261124090000_financeiro_escritor_unico_final.sql`;
  - `supabase/reversao/20261124090000_escritas_sem_escritor_anterior.sql`;
  - `tests/test_supabase_escritor_unico_final.py`;
  - este documento.
- **Alterados:**
  - Flask:
    - `backend/services/gerador_recorrencia_service.py` (função nova no fim);
    - `backend/routes/{despesas,recorrencias,receitas,cartoes,importacao_cartao,categorias,financiamento_seguro,perfis}.py` (um bloco marcado logo após a criação do blueprint).
  - Testes:
    - `tests/test_supabase_{cartoes,cartoes_tela,receitas,importacao_cartao,perfis_gestao,despesas,gerador_t1}.py`;
    - `tests/test_{cartoes_fechamento,cartoes_d6_integridade,cartoes_pagamento,fatura_integridade,recorrencia_pendencia,pagamento_trava}.py`.
  - Web:
    - `web/src/js/configuracoes.js`;
    - `web/tests/e2e/{despesas,cartoes_tela,perfis_gestao,recorrencias_tela}.spec.mjs`.

**Separação por MVP (commits separados):**
- Nenhum arquivo deste MVP coincide com os do FIN-FINANCIAMENTOS-MOTOR-1, exceto `docs/ROADMAP.md`, onde cada MVP tem a sua linha.
- `tests/test_supabase_contratos_pagamento.py`, `tests/supabase_local.py`, `web/tests/unit/build.test.mjs` e `web/tests/e2e/financiamentos_*.spec.mjs` são só do motor.

## 9. Aplicação no Supabase de teste (26/10/2026)

**Commit:** `0af3128` (só este MVP, sem push). Nos arquivos compartilhados com o FIN-CATEGORIAS-RECORRENCIAS-2 entraram só os trechos deste MVP. Na árvore exata do commit: 578 testes Python das suítes afetadas, 30 unitários e 22 E2E passaram. Duas falhas iniciais vieram da ausência da pasta `data/` na árvore exportada; com a pasta, passaram.

**Inspeção antes de aplicar** (só leitura, todas aprovadas):
- as 29 funções existem no remoto com o texto que a reversão devolve (fim de linha normalizado);
- em todas, a definição nova é a anterior mais só a linha marcada;
- `exigir_escrita_novo` não existia; dependências presentes;
- no remoto, só os perfis fictícios 31 e 39 estão no novo aplicativo;
- a migration só cria e substitui funções e revoga privilégios: nenhum comando de dados.

**Aplicação:**
- só a `20261124090000`, com as migrations locais posteriores fora da pasta durante o envio (voltaram idênticas, md5);
- as 65 tabelas ficaram com o conteúdo idêntico (211 linhas); +1 função (`exigir_escrita_novo`); 29 substituídas; nenhuma removida.

**Validação real** (perfil temporário criado pelo aplicativo, **6 de 6**):
- perfil no novo aplicativo: o cadastro grava, e o reenvio pela mesma chave não duplica; a edição grava;
- perfil passado ao Flask: criar, editar e excluir despesa, criar receita, criar cartão, atualizar e inativar o perfil são **recusados** (`SISTEMA_FLASK`), e **nenhuma tabela do perfil muda**;
- quem só lê recebe 403;
- inativar e reativar o próprio perfil funciona (gestão com o perfil inativo).
- **Telas:** as 14 da árvore commitada, com o `dist` e a CSP reais, no perfil temporário: sem erro de console nem chamada ao Flask.

**Limpeza por identidade** (simulação, depois confirmação): banco idêntico ao retrato pós-aplicação. A linha a mais no histórico do gerador vem do gatilho de auditoria ao excluir o gerador, removida na mesma transação.

**Efeito na prévia já publicada:** cadastros pelo novo aplicativo em perfil ainda no Flask (Pessoal e Empresa) passam a ser recusados sem gravar, que é o objetivo. Os perfis fictícios 31 e 39 seguem gravando.

**Inalterados:** produção; Pessoal e Empresa, que continuam no Flask; `gastos.db`. **Pendentes no remoto:** `20261125090000` e `20261126090000`.

