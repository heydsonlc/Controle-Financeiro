# FIN-BLOCO-D-3 — Conversão controlada do Supabase para produção

**Data:** 28/10/2026. **Ambiente:** computador de casa (Windows 11 Home, VS Code).
**Origem:** `controle_financeiro_dev` (PostgreSQL local, só lida). **Destino:** Supabase `Controle-Financeiro`, ref `fzjmgekasjrgvmfdkdog`, us-east-2.

**Autorizado e executado:**
1. push;
2. retirada dos fictícios;
3. as 5 migrations;
4. carga dos dados reais;
5. conferência.

**Decisão do titular:** sem backup independente. Os backups gerenciados do Supabase não foram mexidos.

**Não feito:**
- publicação no Cloudflare;
- domínio;
- criação ou exclusão de contas do Auth;
- vínculo da conta aos perfis;
- troca do escritor;
- alteração dos bancos locais;
- force push.

Continua `docs/FIN_BLOCO_D_1.md` e `docs/FIN_BLOCO_D_2.md`.

## 1. Pré-condições

| Item | Resultado |
|---|---|
| Branch | `main`, sem alteração rastreada pendente; `git fsck` sem erro |
| Commits pendentes | 66, conforme o D-2; `origin/main` ancestral do HEAD e nada atrás |
| Projeto | ref completo `fzjmgekasjrgvmfdkdog` igual na conexão (`postgres.<ref>`), na CLI (`Controle-Financeiro`, us-east-2) e no projeto da identidade |
| Remoto antes | 37 migrations e 5 pendentes; inventário igual ao homologado (§3) |
| Origem | `controle_financeiro_dev`, 1.528 linhas em 52 tabelas; hash de conteúdo registrado como linha de base |
| Push sem publicação | Cloudflare Pages `controle-financeiro` sem Git ("Git Provider: No", envio direto); Render com `autoDeploy: false`; "Deploy to production" do Supabase desligado |

**Ajuste necessário antes de qualquer escrita: carga sem titular.** A carga homologada exigia um titular já gestor do Pessoal e da Empresa e gravava as preferências de interface dessa conta. Este contrato proíbe criar a conta. Por isso entrou o modo sem titular, com `"titular_user_id": null` no mapa (commit `2040f0c`):
- **Identificação:** Pessoal e Empresa conferidos pelo id e pelo nome declarado no mapa.
- **Isolamento:**
  - recusa se o perfil de destino tiver acesso de qualquer conta;
  - confere de novo antes do commit;
  - ninguém enxerga os dados até o vínculo.
- **Perfil novo:** "criar" é recusado, porque o perfil ficaria sem gestor.
- **Preferências:**
  - as de interface (do usuário) ficam **pendentes**;
  - as de cada perfil são copiadas.

**Testes:** +2, e os 9 de `tests/test_carga_supabase.py` aprovados.

**Ensaio completo numa cópia fiel do remoto** (PostgreSQL 17 descartável): restauração idêntica; simulação sem efeito; retirada de 154 linhas; migrations; carga sem titular **GRAVADA**; segunda carga recusada. O vínculo de uma conta fictícia, feito depois por `scripts/vincular_titular_supabase.py`, deu ao titular a leitura das 2 contas do Pessoal.

## 2. GitHub

Conferido antes do push, nos 67 commits (339 arquivos):
- **Arquivos:**
  - nenhum `.env` real;
  - `.env.example` só com marcadores;
  - `.claude/settings.local.json` aparece como **removido**;
  - nenhum PDF, banco ou backup.
- **Segredos:**
  - nenhum dos 8 valores secretos dos `.env` locais aparece nas linhas adicionadas;
  - nenhum JWT, `sb_secret`, URL com senha ou chave privada;
  - os 2 números reais de cartão não aparecem.
- **Arquivos não rastreados** (imagens, `apply_veic2b_sql.py`): ficaram de fora.

**Push por avanço direto:** `9a50410..2040f0c`. HEAD remoto = HEAD local = `2040f0c`.

**Depois do push, nada foi publicado:**
- o check "Supabase Preview" saiu `skipped`;
- as 5 migrations continuaram pendentes;
- a última implantação do Pages continuou a `54a31813`, de 2 dias antes.

## 3. Inventário e simulação (só leitura)

**Relação:** igual à homologada no D-2. São 152 linhas em 21 tabelas (perfis 31 e 39, categorias globais 47–50 e dependentes), com 0 ambíguas. Preservadas iguais:

| Preservado | Linhas |
|---|---|
| Categorias de sistema | 10 |
| TR | 25 |
| Categorias de IR | 19 |
| Fonte de receita real | 1 |
| Pessoal e Empresa | 2 |
| `alembic_version` | 1 |
| `usuario` | 1 |
| Auth | 2 contas |

**Simulação** (somente leitura):
- previu 154 linhas, as 152 mais 2 de auditoria que o gatilho do gerador grava durante a retirada;
- retrato completo antes e depois sem nenhuma diferença, inclusive nas 57 sequências;
- repetição igual.

## 4. Retirada

`retirar --confirmar --projeto-autorizado fzjmgekasjrgvmfdkdog` rodou numa única transação serializable.

**Resultado RETIRADO:** 154 linhas. A conferência interna saiu OK: só as linhas da relação saíram, e as preservadas, a estrutura e os usuários ficaram idênticos.

**Conferência independente** (retrato antes × depois):
- **Linhas:** 248 → 96. Só as 21 tabelas da relação mudaram; as outras 50 estão idênticas.
- **Estrutura:** nenhuma diferença.
- **Sequência:** só a do histórico do gerador avançou, por causa das 2 linhas de auditoria, também removidas.
- **Restou:**
  - perfis 1 Pessoal e 2 Empresa;
  - 2 contas no Auth, intactas;
  - 0 acessos a perfis.
- **Integridade:** 0 FKs não validadas e 0 órfãos.

## 5. Migrations

**Método:** uma de cada vez, pelo mesmo caminho de `scripts/supabase_migrations.py` (`supabase db push` numa cópia temporária, sem `supabase/config.toml` no repositório). A cópia só tinha as migrations até a versão autorizada.

**Antes de cada uma, exigi:**
- versão anterior aplicada e esta não aplicada;
- ela ser a próxima pendente;
- nenhuma pendente fora das 5;
- nada só no remoto;
- arquivo de reversão presente;
- arquivo igual ao commit homologado;
- `db push --dry-run` listando só ela.

**Depois de cada uma, conferi:**
- o registro;
- o retrato antes × depois;
- a RLS nas tabelas novas;
- o verificador de segurança.

| Versão | Tabelas novas (vazias, RLS) | Funções | Dados existentes | Segurança |
|---|---|---|---|---|
| `20261127090000` Mobilidade | `operacao_mobilidade` | +48 | inalterados | sem bloqueio |
| `20261128090000` Documentos | `operacao_documento` | +16 | inalterados | sem bloqueio |
| `20261129090000` Indexadores | `operacao_indexador`, `indice_tr_historico` | +13 | inalterados (TR intacta) | sem bloqueio |
| `20261130090000` Integração de Documentos | — | +5, 4 redefinidas (as 4 do arquivo) | inalterados | sem bloqueio |
| `20261201090000` Preferências | `preferencia_usuario`, `preferencia_perfil` | +4 | inalterados | sem bloqueio |

**No conjunto:** 42 aplicadas e nenhuma pendente. São 6 tabelas novas e 89 funções novas ou alteradas: 86 novas e 3 que já existiam. São os mesmos números do ensaio.

## 6. Carga

**Antes da carga:**
- origem idêntica à linha de base;
- script e mapa iguais ao commit `2040f0c`.

**Simulação no remoto** (desfeita no fim):
- 1.521 linhas da origem: 1.466 inserções e 55 reaproveitamentos (categoria 10, TR 25, IR 19, fonte de receita 1);
- 20 tabelas, iguais ao ensaio;
- dados e estrutura inalterados;
- 18 sequências avançaram, porque o rollback não devolve números de sequência. Não há efeito em dados; os ids novos só começam mais adiante.

**Carga definitiva** (`--confirmar`, uma transação): **GRAVADO**, com os mesmos números e a conferência linha a linha OK.
- **Origem:** inalterada durante a carga, conferida por hash antes e depois.
- **Referências em duas etapas:** `conta.financiamento_parcela_id`, `item_despesa.cartao_id` e `movimento_financeiro.movimento_original_id`.
- **Cartões:** 2, só com os 4 últimos dígitos; 0 CVV e 0 validade.
- **Preferências:**
  - as do Pessoal e da Empresa foram copiadas;
  - a de interface ficou pendente, porque não há conta.
- **TR:** nenhuma divergente.

## 7. Conferência financeira (independente do script de carga)

**Método:** um script de conferência desta sessão, fora do repositório, que só lê as duas pontas.
- Cada linha vira uma forma canônica sem ids: referências substituídas pelo rótulo do registro apontado e perfil pelo nome.
- Os multiconjuntos da origem e do destino são comparados tabela por tabela, nas colunas comuns.

**Resultado:** 19 de 20 tabelas com conteúdo idêntico.
- **Ressalva esperada:** `item_receita`. A fonte de receita preexistente está **sem perfil** na origem (pela regra do Flask, pertence ao "Pessoal") e no **Pessoal** no destino. As outras 3 fontes estão idênticas.
- **Reaproveitados:** batem pela chave natural, e o destino manteve as suas datas de criação. Em 8 categorias de IR, também a `natureza` e a `observacao_fiscal` do destino, que são as do novo aplicativo.
- **Colunas que só existem no destino:** ficaram com o padrão. São `compra_no_fechamento = PROXIMO`, `fechamento_confirmado = false`, `mes_fatura_*` e `data_prevista` nulos.

| Conferência | Origem × destino |
|---|---|
| Saldos das contas bancárias (2) | iguais |
| Movimentos por conta e tipo | iguais |
| Despesas por situação e mês (424 grupos), pagas e não pagas | iguais |
| Faturas de cartão (11 grupos) e compras por cartão e fatura | iguais |
| Receitas realizadas e previstas por fonte | iguais |
| Recorrências de despesa | iguais |
| Financiamento e 420 parcelas (status, previsto, pago, saldo) | iguais |
| Consórcios (7) | iguais |
| Preferências por perfil (2) | iguais ao registro do Flask |
| Patrimônio, Mobilidade, Documentos, transferências, despesas previstas | 0 na origem e 0 no destino |
| FKs não validadas, órfãos de `categoria_cartao_id` e de `origem_id`, ciclo conta–parcela | 0 |
| Fonte de receita ou categoria global duplicada | 0 |
| Linhas fora do Pessoal e da Empresa | 0 |
| CVV, validade, número completo de cartão | 0 |

**Isolamento e segurança:**
- **Contas de teste A e B,** autenticadas: 0 perfis visíveis, sem acesso ao Pessoal nem à Empresa, e leitura das contas do Pessoal negada (42501).
- **Verificador de segurança:** sem bloqueios.
  - RLS em todas as tabelas;
  - anônimo sem privilégio em tabelas e funções;
  - 0 buckets;
  - cadastro público desligado;
  - só login por e-mail, com confirmação.
- **Escritor:** nenhum registro de gerador no remoto, então o Pessoal e a Empresa seguem no padrão FLASK. Nada foi transferido.

## 8. Bancos locais

O `controle_financeiro_dev` só foi lido, em transações read only.
- Conteúdo e sequências idênticos à linha de base.
- Contadores de escrita de todos os bancos locais e md5 do `gastos.db` (`bf7c7d3a12030bf18826cacc1f46293e`) iguais.

## 9. Pendências (dependem do titular)

1. **Conta do titular no Auth:** criar no painel, confirmar o e-mail e definir a senha.
2. **Vínculo da conta aos perfis:** `vincular_titular_supabase.py conferir` e depois `vincular --confirmar --projeto-autorizado fzjmgekasjrgvmfdkdog`.
3. **Testes de entrada e saída** no aplicativo.
4. **Preferências de interface:** copiar o registro do Flask para a conta, depois do vínculo.
5. **Contas de teste A e B:** trocar a senha ou desativar antes da produção. As senhas já foram expostas.
6. **Proteção do endereço:** Cloudflare Access ou equivalente no domínio, antes de abrir o aplicativo.
7. **TR posterior a maio/2026:** o destino tem a TR de 05/2024 a 05/2026 (25 competências) e precisa do lançamento das seguintes.
8. **Lançamentos posteriores a agosto/2026:** a origem tem dados até 20/08/2026. O que aconteceu depois ainda não está no sistema.
9. **Escritor:** passar o gerador ao novo aplicativo, perfil a perfil, só com autorização.
10. **Ligar no painel do Supabase:**
    - a exigência de SSL;
    - a revisão das URLs e da política de senha do Auth.

**Até as providências 1 a 6,** o aplicativo não deve ser publicado como produção operacional.
