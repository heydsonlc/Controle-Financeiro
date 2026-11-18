# FIN-CADASTROS-PADRAO-01 — Catálogo padrão e personalização por usuário

**Situação:** implementado e ensaiado **localmente** em 18/11/2026, no ramo `cadastros-padrao-01` (sobre o
`multiusuario-seguranca-01`). **Nada em produção:** sem push, sem deploy, migration `20270101090000` **não aplicada**, nenhum
catálogo alterado. Segunda etapa da fila multiusuário; depende do FIN-MULTIUSUARIO-SEGURANCA-01.

## 1. O que cada um recebe e o que pode mudar

| Cadastro | Padrão do aplicativo | Do usuário |
|---|---|---|
| Categorias de despesa | as categorias atuais, iguais para todos, **fixas** (só quem administra o catálogo cria, edita, exclui ou muda a natureza) | categorias **particulares**: só o dono vê; valem em todos os perfis dele; ele edita, define a natureza e, com registros vinculados, inativa em vez de excluir |
| Palavras-chave | as regras atuais, mantidas pelo administrador | cada usuário acrescenta as suas, **desliga** uma regra padrão só para si, ou a **reassocia** a outra categoria; restaura quando quiser |
| Categorias de cartão | um **modelo** do aplicativo | cada perfil recebe uma **cópia** do modelo (nome e situação protegidos) e pode ter categorias adicionais |

Nada é copiado de um usuário para outro. Nenhuma categoria muda de identificador. Palavra-chave só influencia a **sugestão** da
importação: nenhuma despesa ou compra já classificada muda quando uma regra é alterada.

## 2. Categorias de despesa

- `public.categoria.user_id`: nulo = padrão do aplicativo; preenchido = particular daquele usuário. As categorias existentes
  ficam todas como padrão, no lugar.
- Nome único entre as padrão; a particular não repete nome de padrão nem de outra particular do mesmo dono (dois usuários
  podem ter particulares de mesmo nome).
- Leituras (`categorias_de_despesa`, `categorias_tela`, `mobilidade_categorias_tela`, `naturezas_das_categorias`, tela fiscal):
  devolvem o padrão + as particulares de quem pede (ou do dono do perfil). O catálogo deixa de depender do perfil que guardava
  os registros sem perfil: passa a aparecer em todos os perfis.
- `criar_categoria` cria **particular** por padrão; categoria padrão só com `padrao: true` e por quem administra o catálogo.
  `editar_categoria`, `excluir_categoria` e `definir_natureza_categoria`: na padrão, quem administra o catálogo; na particular,
  o dono. A categoria de outro usuário responde como inexistente.
- **Rede de proteção nos dados:** um gatilho em toda coluna que aponta para a categoria (19) recusa gravar uma categoria
  particular em registro de perfil de outro dono, qualquer que seja a função. Palavras-chave padrão e o modelo de categorias de
  cartão só apontam para categoria padrão.
- **Escritor do catálogo:** enquanto o catálogo for administrado pelo sistema anterior, nada dele é gravado pelo novo
  aplicativo — nem o padrão, nem categoria particular, nem ajuste de palavra-chave, nem o modelo de categorias de cartão
  (`exigir_catalogo_no_novo`). O sistema anterior não conhece o dono da categoria. Em produção o catálogo já é do novo aplicativo.
- **Natureza gerencial** (Consumo, Aporte, Ajuste técnico, Transferência interna, Não definido): a tabela é a mesma. Mudar a
  natureza só muda a repartição gerencial do Dashboard; o total, os saldos e os pagamentos não são tocados.

## 3. Palavras-chave em duas camadas

- Camada padrão: a tabela atual (`public.categoria_palavra_chave`).
- Camada do usuário: `financeiro.palavra_chave_usuario`, com três tipos de ajuste — `NOVA`, `DESLIGADA`, `REASSOCIADA`. O ajuste
  se refere ao par (categoria padrão, palavra).
- Regra efetiva de um usuário (`palavras_efetivas`) = padrão − o que ele desligou ou reassociou + as dele. É calculada; ninguém
  recebe cópia das regras.
- **Mudança do administrador:** vale para quem não ajustou aquela palavra; quem a desligou ou reassociou mantém a própria
  escolha, mesmo que a regra padrão seja retirada e recolocada. Regra padrão nova chega a todos. A reassociação só vale enquanto
  a regra padrão de origem existir.
- A sugestão da importação (`sugestao_categoria_importacao`) usa a regra efetiva do dono do perfil. Confiança, ambiguidade e a
  não propagação de categoria de natureza não definida ficam como estão.
- Funções do usuário: `criar_minha_palavra_chave`, `desligar_palavra_chave_padrao`, `reassociar_palavra_chave_padrao`,
  `remover_minha_palavra_chave`, `restaurar_palavra_chave_padrao`. As do catálogo padrão (`criar_palavra_chave`,
  `remover_palavra_chave`) continuam só de quem o administra.

## 4. Categorias de cartão (cópia controlada por perfil)

- Modelo: `financeiro.categoria_cartao_padrao` e `categoria_cartao_padrao_despesa` (vínculo padrão com categoria de despesa).
- `public.categoria_cartao.padrao_id`: marca de origem da cópia; nula nas categorias adicionais do perfil.
- `inicializar_categorias_cartao(perfil)`: só acrescenta, nunca duplica. Categoria já copiada é pulada; categoria do perfil com
  o mesmo nome é **adotada** (ganha a marca, nada mais muda); vínculo já existente é pulado. Repetir não muda nada.
  Chamada em `criar_perfil` (perfil novo já nasce com as padrão) e disponível ao dono de um perfil antigo.
- Proteção: categoria padrão não é renomeada nem desativada pelo usuário; cor, ícone, descrição, limites e vínculos continuam
  dele. Categorias adicionais continuam livres. Cada perfil tem a sua cópia: mexer numa não muda a de outro.
- Administração do modelo: `manter_categoria_cartao_padrao`, `categorias_cartao_padrao_tela`,
  `propagar_categorias_cartao_padrao` (leva categorias novas do modelo aos perfis existentes, só acrescentando).

## 5. Carga inicial (`scripts/cadastros_padrao.py`)

Prévia em sessão somente leitura → execução com a impressão conferida e confirmação literal → reversão.

1. Monta o modelo a partir das categorias de cartão ativas do perfil de referência e dos vínculos delas. As categorias do perfil
   de referência **não são recriadas**: só ganham a marca de origem.
2. Com `--preencher-perfis`, os outros perfis existentes recebem as categorias de cartão padrão.
3. Com `--pessoais`, as palavras-chave indicadas saem do catálogo padrão e viram palavras próprias do dono do perfil de
   referência, na mesma categoria: para ele a regra efetiva não muda; os demais usuários não as recebem.

A lista de palavras pessoais é decisão do titular (proposta na pasta privada). A reversão devolve tudo, e se recusa se alguma
categoria de cartão criada já estiver em uso.

## 6. Tela de Categorias

- Selo discreto **Padrão** ou **Minha** em cada categoria de despesa; **Padrão** nas categorias de cartão copiadas do modelo.
- Categoria padrão: sem Editar nem Excluir para o usuário comum. Particular: editável.
- Formulário de categoria com a **natureza gerencial**; o título diz se a categoria é particular ou padrão.
- Palavras-chave na mesma lista: a própria com um ponto; a padrão desligada aparece riscada, com o botão de restaurar. O texto
  do cartão diz que os ajustes valem só para a conta de quem os faz.
- **Modo "catálogo padrão":** interruptor pequeno, que só existe para quem administra o catálogo e começa desligado. Ligado,
  criar, editar e remover passam a valer para o catálogo de todos.
- Nenhum painel novo. O aviso de catálogo bloqueado saiu: todo usuário pode criar categorias particulares e ajustar as próprias
  palavras.

## 7. Migration `20270101090000` e reversão

Geradas por `scripts/gerar_migration_cadastros_padrao.py` (parte fixa em `scripts/cadastros_padrao_estrutura.sql`; cinco funções
longas reescritas por substituição conferida da definição vigente). A migration não altera nenhum registro financeiro.

Reversão: `supabase/reversao/20270101090000_cadastros_padrao_anterior.sql`. Devolve as 17 funções substituídas e retira a
estrutura (18 funções novas retiradas). É **recusada** enquanto existir categoria particular, palavra-chave de usuário ou modelo de categorias de cartão em
uso (a regra anterior não sabe representá-los): os dados são desfeitos antes, pelo roteiro.

## 8. Efeito sobre a etapa anterior

Com esta migration o catálogo tem regra própria e deixa de ser lido pela guarda dos registros sem perfil. Depois da
regularização dos itens sem perfil, `regularizar_itens_sem_perfil.py retirar-guarda` passa a ser aceito; no ensaio, retirar a
guarda não mudou nenhuma tela.

## 9. Ensaio na cópia fiel da produção

`scripts/ensaio_cadastros_padrao.py` (backup de 17/11/2026, 70 migrations; etapa anterior aplicada como pré-requisito).

| Passo | Resultado |
|---|---|
| Migration | nenhuma tabela de dados muda; sugestões de categoria idênticas em todas as descrições e perfis; telas do perfil de referência idênticas; todas as categorias ficam padrão |
| Carga inicial | perfil de referência com as mesmas categorias de cartão, vínculos e limites (mesmos identificadores); o outro perfil recebe as padrão; sugestões do titular idênticas; só mudam o catálogo de palavras, as categorias de cartão e os vínculos |
| Reversão | carga e migration desfeitas: banco idêntico ao de antes; sugestões idênticas; estrutura retirada |
| Guarda | retirada sem mudar nenhuma tela nem sugestão |
| Segundo usuário fictício | perfil novo já nasce com as categorias de cartão e os vínculos; vê o catálogo padrão; não recebe as palavras pessoais; cria categoria e palavra próprias sem que nada apareça ou mude para o titular |

Única mudança de tela para o titular, esperada: o catálogo de categorias passa a aparecer na tela fiscal do outro perfil (antes só
aparecia no perfil que guardava os registros sem perfil), e esse perfil ganha as categorias de cartão padrão.

Resultado: **42 verificações, nenhuma falha** (18/11/2026).

## 10. Testes

| Verificação | Resultado |
|---|---|
| `tests/test_supabase_cadastros_padrao.py` | 10/10 |
| Suíte permanente de isolamento (com esta migration) | 10/10 (mais 3/3 da regularização dos itens sem perfil) |
| Regressão de banco completa | 1.440 aprovados, 20 pulados, nenhuma falha (em duas metades: 714 + 726) |
| Unitários do frontend | 131/131 |
| Suíte e2e completa | 292/292 |

## 11. Decisões que ficam com o titular

1. Lista das palavras-chave pessoais (as que saem do catálogo padrão).
2. Os vínculos padrão entre categorias de cartão e de despesa (o ensaio levou todos os atuais para o modelo).
3. Preencher o perfil Empresa com as categorias de cartão padrão na publicação (o ensaio preencheu).
4. Reassociação pela tela: hoje o usuário desliga a palavra padrão e a adiciona na outra categoria; a função de reassociar existe,
   sem botão próprio.

## 12. Plano de publicação (não executado)

Depois do FIN-MULTIUSUARIO-SEGURANCA-01 publicado: backup → migration `20270101090000` → `cadastros_padrao.py previa` e
`executar` → conferências (sugestões e telas iguais) → `retirar-guarda` → push e deploy. Reversão: frontend ao deploy anterior;
`cadastros_padrao.py reverter`; script de reversão da migration. **Nada disso é executado sem autorização expressa do titular.**
