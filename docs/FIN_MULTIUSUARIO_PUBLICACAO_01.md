# FIN-MULTIUSUARIO-PUBLICACAO-01 — Publicação escalonada da arquitetura multiusuário

**Situação em 18/11/2026:** janelas 1 e 2 **publicadas e conferidas**. Janela 3 **não executada**: interrompida antes da
migration, porque as configurações do Supabase Auth que só aparecem no painel não puderam ser verificadas (condição
obrigatória do contrato). Nenhum convite, nenhum usuário novo; cadastro público desligado.

## 1. O que está em produção

| Janela | Etapa | Migration | Commit na `main` | Deploy | Volta para |
|---|---|---|---|---|---|
| 1 | Segurança e propriedade dos perfis | `20261231090000` (70 → 71) | `9d215c3` | `c11d21b1` | `b410bb33` |
| 2 | Cadastros padrão, com os ajustes finais do catálogo | `20270101090000` (71 → 72) | `1fe0205`, `d49e1eb` | `f0cd0047` | `c11d21b1` |
| 3 | Acesso por convite | `20270102090000` | — | — | **não aplicada** |

Produção: `main` em `d49e1eb`, deploy `f0cd0047`, 72 migrations.

## 2. Pré-condições cumpridas antes de tocar em produção

| Verificação (ambiente isolado) | Resultado |
|---|---|
| Regressão de banco do código final, duas metades | 1.466 aprovados, 0 falhas |
| Os 20 testes antes pulados (dependiam do binário do PostgREST) | executados, 20/20 |
| Suíte permanente de isolamento, com sondas dirigidas | 11/11; nenhuma combinação sem prova |
| Homologação integrada multiusuário | 8/8 |
| Unitários | 131/131 |
| E2E do código final | 300/300 |
| Ensaio encadeado das três migrations na cópia fiel | 79 verificações, 0 falhas |
| Árvore exata da janela 2 (etapa 2 + ajustes do catálogo, sem a etapa 3) | banco 1.466/0 sem pulados; unitários 131/131; e2e 293/293 |

A intermitência antiga de Lançamentos ocorreu uma vez numa rodada e2e. Foi investigada antes de prosseguir: a operação é
gravada e uma leitura seguinte ao servidor local de testes fica sem resposta; reproduzida de forma determinística, com o banco
correto. Não é regressão nem tem efeito financeiro. A razão de o servidor local deixar de responder não foi determinada.

## 3. Janela 1 — segurança

1. Backup cifrado antes da migration, duas cópias verificadas.
2. Migration aplicada. Conferido em leitura: os dois perfis com o titular como dono; um perfil padrão; administrador da
   plataforma = titular; manutenção dos índices de TR restrita ao administrador.
3. Regularização dos itens sem perfil: prévia com 58 itens, todos com posse demonstrada, nenhum divergente, **mesma impressão
   do ensaio**; executada (58 → 0).
4. Frontend publicado; arquivos servidos iguais aos do build; sem sessão, as telas levam à entrada.

Comparação antes/depois: saldos e totais idênticos; todas as leituras de tela do titular idênticas; mudaram só a coluna do
dono nos perfis, o perfil dos 58 itens e o registro de auditoria.

## 4. Janela 2 — cadastros padrão

1. Backup cifrado antes da migration, duas cópias verificadas.
2. Migration aplicada: as 39 categorias ficam padrão (mesmos identificadores), nenhuma particular; rede de proteção nas 19
   colunas que apontam para a categoria.
3. Carga inicial com o manifesto aprovado, prévia com a **mesma impressão do ensaio**:
   - 13 palavras-chave saem do catálogo compartilhado e ficam só na conta do titular, nas mesmas categorias (regra efetiva
     igual à de antes); nenhuma outra palavra-chave alterada;
   - modelo de categorias de cartão com 6 categorias e 12 vínculos; no perfil de referência os registros são preservados
     (mesmos identificadores, limites e vínculos); o outro perfil recebe as 6 categorias e os 12 vínculos, sem duplicidade.
4. Guarda dos registros sem perfil retirada (não havia mais nenhum), sem mudar nenhuma tela.
5. Frontend publicado, com a ação "Alterar categoria" da palavra-chave; arquivos servidos iguais aos do build.

Comparação antes/depois: saldos e totais idênticos; sugestão de categoria idêntica em todas as descrições de compra já
importadas (produção depois × backup de antes da janela, restaurado num banco local descartável); mudam só quatro leituras, todas
esperadas e todas do perfil que não era o de referência (o catálogo passa a aparecer na tela fiscal; categorias de cartão
padrão). Nenhuma despesa, compra, fatura, receita ou movimento alterado.

## 5. Janela 3 — por que parou

O contrato exige, antes da terceira migration, a conferência de política de senha, redirecionamentos, validade dos links,
limites e demais controles do Supabase Auth, sem presumir que estejam corretos. De fora só é possível confirmar que o cadastro
público está desligado e que a confirmação de e-mail é exigida. O restante depende do painel do projeto.

Para destravar: conferir os itens da seção 8 de `FIN_MULTIUSUARIO_AJUSTES_FINAIS_01.md` e autorizar a janela. A migration
`20270102090000`, o frontend e os testes estão prontos (commits locais, não enviados à `main`).

## 6. Mudança em relação ao homologado

A ação "Alterar categoria" foi incorporada às migrations `20270101090000` e `20270102090000`, que ainda não tinham sido
publicadas, em vez de criar uma quarta migration. As impressões foram atualizadas e todos os ensaios e regressões foram
repetidos antes da publicação. Até a terceira janela, essa função existe sem a exigência de conta ativa, que só chega com a
etapa 3 (hoje só há a conta do titular).

## 7. O que foi verificado onde

- **Em produção, somente leitura:** estado antes e depois de cada passo (impressão de cada tabela e das leituras de tela do
  titular), dono dos perfis, administrador, catálogo, palavras-chave, categorias de cartão e vínculos, arquivos servidos,
  navegação sem sessão.
- **Só em ambiente isolado:** isolamento entre usuários, convites, ativação, suspensão, a ação "Alterar categoria" pela tela.
  Nenhuma operação de teste foi feita em produção.
- **Não verificado:** login com a conta do titular e o painel do Supabase Auth.

## 8. Reversão

Não foi necessária. Por janela: frontend ao deploy anterior; roteiro de dados (`cadastros_padrao.py reverter`,
`regularizar_itens_sem_perfil.py reverter`) com os arquivos gravados na execução; script de reversão da migration. Os backups
de antes de cada janela estão guardados.

## 9. Pendências para os primeiros usuários (autorização separada)

Terceira janela publicada; procedimento de privacidade aprovado; endereço de contato e prazos; roteiro de exclusão de conta
desenvolvido e testado; serviço de e-mail próprio para os convites; homologação do titular; ensaio com uma segunda conta do
titular.
