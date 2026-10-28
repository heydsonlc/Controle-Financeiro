# FIN-PREPARACAO-PRODUCAO-1 — Homologação geral e prontidão para a migração real

Data: 28/10/2026. Documento consolidado do FIN-BLOCO-C-1 (contrato em `docs/contratos/fila_2026-10-27/FIN-BLOCO-C-1.md`).

Este documento **não autoriza** produção nem migração real. Ele serve de base para o Bloco D.

## 1. Funcionalidades homologadas

**Escrita** quer dizer que o novo aplicativo grava pelas funções do banco, com o escritor único do perfil: um perfil no Flask é recusado sem gravar, e o Flask recusa escrever num perfil do novo aplicativo.

| Módulo | Situação no novo aplicativo | Prova principal |
|---|---|---|
| Autenticação e perfis | Escrita (gestão de perfis) | `test_supabase_perfis*`, E2E `acesso`, `perfis`, `perfis_gestao` |
| Contas bancárias | Escrita (movimentos, ajustes, transferências) | `test_supabase_contas_bancarias`, `test_movimentacoes` |
| Receitas | Escrita (fontes, previsões, recebimentos, sem previsão) | `test_supabase_receitas*`, `test_supabase_categorias_recorrencias` |
| Despesas | Escrita | `test_supabase_despesas`, E2E `despesas` |
| Recorrências | Escrita, gerador próprio (mensal, semanal, a cada 2 semanas) | `test_supabase_recorrencia`, `test_supabase_categorias_recorrencias` |
| Cartões e faturas | Escrita (compras, parcelamento, fechamento, importação) | `test_supabase_cartoes*`, `test_supabase_fatura_unica`, `test_supabase_importacao_cartao` |
| Pagamentos e estornos | Escrita (despesas, faturas, parcelas, receitas) | `test_supabase_contratos_pagamento`, `test_pagamento_trava`, `test_estorno_*` |
| Financiamentos | Escrita (motor SAC/TR, PRICE, SIMPLES, amortização, históricas) | `test_supabase_financiamentos_motor` (calibração Caixa) |
| Consórcios | Escrita | `test_supabase_consorcios_escrita` |
| Patrimônio | Escrita (caixinhas, transferências, bens) | `test_supabase_patrimonio_escrita` |
| Mobilidade | Escrita (veículos, projeções, km, financiamento projetivo, modalidade, app, previstas) | `test_supabase_mobilidade_escrita` (11 tabelas iguais ao Flask) |
| Documentos | Escrita **parcial** (envio, revisão, vínculos, despesa a partir do documento) | `test_supabase_documentos_escrita` |
| Relatórios | **Parcial**: bens do Patrimônio em Excel/PDF iguais ao Flask; XLSX de faturas (Cartões) | `test_relatorios_patrimonio` |
| Configurações | Perfis sim; Preferências pendentes de decisão | — |
| Dashboard | Leitura | `test_supabase_dashboard_leitura` |

**Fluxos completos entre módulos:**
- `tests/test_supabase_integracao_1123_1126.py` (I1–I8):
  - ciclo financeiro no mesmo perfil;
  - estorno × amortização;
  - guarda de escritor percorrendo o esquema e as rotas;
  - alternância de escritor;
  - isolamento entre três perfis;
  - concorrência entre módulos;
  - reversões;
  - as três guardas do Flask.
- Além disso: Mobilidade × Recorrências, Documentos × Patrimônio, Financiamentos e Despesas.

## 2. Testes executados

- **Regressão completa (nível 3) no fechamento do C:** ver o §10.
- **Antes, no A e no B:**
  - A: Python 2001 aprovados, com 3 falhas antigas;
  - B: Python 2017 aprovados, com 3 falhas antigas;
  - nos dois: web unit 30/30 e E2E 93/93.
- **Ensaio das migrations pendentes** (`tests/test_migracoes_pendentes_ensaio.py`):
  - estado do remoto (até a 1126) com dados fictícios de todos os módulos;
  - aplicar a 1127 e a 1128 não altera nenhum dado existente;
  - as funções novas operam sobre os dados antigos;
  - a reversão em ordem inversa também não altera dado, e a reaplicação funciona.
- **Auditoria do esquema** (39 migrations num cluster descartável):
  - 0 função `security definer` sem `search_path` fixo (de 354);
  - 0 função ou tabela acessível a `anon`;
  - 0 tabela acessível a `authenticated` sem RLS (as 18 de `financeiro` têm RLS);
  - 0 coluna sensível de cartão legível por `authenticated`.
- **Backup e restauração** (`tests/test_backup_banco.py`), só em clusters descartáveis:
  - conteúdo idêntico depois de restaurar;
  - documento byte a byte;
  - recusa de banco existente;
  - detecção de arquivo alterado.
- **Integridade em todas as baterias:**
  - `gastos.db` com md5 `bf7c7d3a…`, inalterado;
  - PostgreSQL local persistente idêntico (8 bancos, contadores de escrita e conteúdo);
  - Supabase remoto sem alteração (consultas só em transação `READ ONLY`).

## 3. Falhas remanescentes

As cinco falhas antigas da suíte Python foram **todas resolvidas no teste**, sem mudar regra de negócio:

| Teste | Classificação | Correção |
|---|---|---|
| `test_categorias_sistemicas_mobilidade` (`KeyError 'IPVA'`) | Dependência da data | Mês dos eventos anuais = mês atual (a projeção começa hoje) |
| `test_veiculos_mobilidade_2b` (1 == 2) | Dependência da data | Prevista "futura" a 2 meses de hoje (era 01/08/2026) |
| `test_receitas_ux` (1500 == 3000) | Dependência da data | Recebimento no mês atual (a fonte orça os 12 meses a partir de hoje) |
| `test_ocr_tools` ×2 | Dependência do ambiente | Isola `POPPLER_PATH` e `TESSERACT_PATH`, definidas na máquina |

**Teste desmarcado:** `test_verificar_ambiente.py::test_saida_nao_contem_valores_dos_arquivos_locais`, porque lê o `.env.staging`, cujo acesso os contratos proibiram. Ele passa quando rodado à parte.

## 4. Riscos de segurança

1. **Cartões no Flask (alto, para a migração real):**
   - `public.config_agregador` guarda o **número completo, a validade e o CVV (`codigo_seguranca`) em texto puro**;
   - a API do Flask devolve o número completo (`to_dict`).
   - O novo aplicativo nunca grava nem lê esses campos: recusa as chaves e mostra só os 4 últimos dígitos, e nenhum privilégio de leitura existe para `authenticated`.
   - O Supabase de teste está limpo (3 cartões, nenhum com esses dados).
   - **Na migração real, essas colunas não podem ser levadas.** O saneamento dos dados antigos (apagar o CVV, guardar só os 4 últimos dígitos) é destrutivo e **depende de autorização**.
2. **Histórico do Git (baixo):**
   - nenhum segredo em 408 commits: JWT, URL com senha, chaves `sb_secret_`, `sk-`, `ghp_` e AWS foram procurados;
   - há o seu e-mail pessoal em documentos e scripts, já presente no GitHub, e o `.claude/settings.local.json` rastreado, sem segredo.
   - **Recomendação:** tirar esse arquivo do Git (`git rm --cached`), com autorização.
3. **Frontend:**
   - só a chave publicável;
   - as RPCs de escrita ficam amarradas à tela que as usa (`build.test.mjs`);
   - CSP do Pages (`_headers`) inalterada.
4. **Escritor único:** coberto nos dois sentidos para todos os módulos que o novo aplicativo grava. Exceções documentadas:
   - gestão de perfil;
   - "tornar padrão";
   - ferramentas de OCR e backup da máquina do Flask.
5. **Documentos:** ficam no banco, só lidos por funções que conferem o perfil. Não há bucket para configurar nem para expor.

## 5. Migrations pendentes no remoto

| Versão | Conteúdo | Pré-requisito | Ensaio |
|---|---|---|---|
| `20261127090000` | Escrita de Mobilidade | Categorias `MOB_*` no banco: **as 10 existem no Supabase de teste** (consulta só leitura) | Aprovado (§2) |
| `20261128090000` | Escrita de Documentos | — | Aprovado (§2) |

- **Aplicação:** `scripts/supabase_migrations.py aplicar --versoes 20261127090000 20261128090000`, só com autorização.
- **Reversão, em ordem inversa:** 1128 → 1127 → 1126 → 1125 → 1124 → 1123. A reversão da 1124 não confere a ordem sozinha.

## 6. Pendências de Storage

**Nenhuma configuração remota é necessária.** Os arquivos ficam em `public.ir_comprovante_arquivo` (binário), como no Flask, e entram no backup do banco.

Ponto de atenção: o banco de teste tem 19 MB. Com muitos documentos, avaliar o limite de tamanho do plano. A opção futura é um bucket **privado** por perfil no Supabase Storage, que exigiria autorização e uma migration nova.

## 7. Estratégia recomendada de migração (insumo para o Bloco D)

1. **Confirmar a origem dos dados reais.** Desde o DB-3, o banco oficial do Flask é o **PostgreSQL local `controle_financeiro_dev`**; o `gastos.db` (SQLite, alterado pela última vez em maio de 2026) ficou como legado. A carga precisa partir da fonte certa.
2. **Consolidar o remoto de teste:** push dos commits locais e aplicação da 1127 e da 1128 no teste, com homologação real por perfil temporário, como nos MVPs anteriores.
3. **Backups antes de tudo:**
   - origem: `scripts/backup_banco.py exportar` ou o `pg_dump` do Flask;
   - destino: backup gerenciado do Supabase e `exportar`;
   - verificação por SHA-256 e restauração de ensaio num banco novo.
4. **Carga dos dados** (procedimento do Bloco D):
   - tabelas do Flask para `public` do Supabase, **sem** `numero_cartao`, `codigo_seguranca` e `data_validade` (só os 4 últimos dígitos);
   - conferência de contagens e resumos por tabela.
5. **Transferência por perfil:**
   - `definir_gerador_recorrencia(perfil, 'NOVO', responsável, motivo)`, que espera as escritas em andamento (trava do perfil), primeiro Pessoal e depois Empresa;
   - a partir daí, o Flask recusa as escritas desse perfil (409);
   - conferir as leituras da tela e um ciclo real (gerar o mês, pagar, estornar).
6. **Publicação:** Cloudflare Pages, primeiro na prévia e depois em produção.
7. **Convivência:** Flask apenas para consulta, por um período de observação, com backups diários.

## 8. Procedimento de rollback

- **Por perfil:** `definir_gerador_recorrencia(perfil, 'FLASK', …)` devolve a escrita ao Flask (auditado em `gerador_recorrencia_historico`). O que o novo aplicativo gravou fica no mesmo banco e o Flask lê, porque as tabelas são as mesmas.
- **Migrations:** reversões em ordem inversa. A da 1125 recusa se houver ocorrências semanais registradas; a da 1123, se houver parcelas históricas.
- **Dados:** restaurar o backup **num banco novo** (o script recusa banco existente) e reapontar o aplicativo. Nunca restaurar sobre o banco em uso.
- **Publicação:** voltar à implantação anterior no Cloudflare Pages.

## 9. Itens necessários para produção

**Autorizações:**
- push dos commits;
- aplicação da 1127 e da 1128 no teste e depois na produção;
- homologação real;
- `exportar` contra o Supabase;
- local seguro dos backups, cifrado e fora de pasta pública;
- publicação.

**Decisões:**
1. Origem dos dados reais (`controle_financeiro_dev` × `gastos.db`).
2. Saneamento de cartões: CVV e número completo.
3. Financiamento do veículo: projetivo (atual) × motor de Financiamentos.
4. Preferências: registro global no Flask × por usuário no novo aplicativo (migration estrutural).
5. Mesmo documento em dois bens pela rota genérica de IR do Flask, no perfil do Flask.
6. Tirar o `.claude/settings.local.json` do Git.

**Funcionalidades ainda pendentes** (o perfil transferido não as terá até lá):
- OCR de imagem e interpretação de NFS-e/cupom;
- Documentos da Empresa (metadados, checklist, saídas sem documento, categorias IR);
- relatórios de IR, de saídas sem documento e o ZIP de documentos;
- exportar/importar configurações;
- atalho "A partir de documento" em Despesas.

## 10. Regressão final (C7)

Executada em 28/10/2026, das 01h29 às 02h11, depois das correções do C5 (commit `15bc1d8`):

| Suíte | Resultado |
|---|---|
| Python (`tests/` inteira) | **2022 aprovados, 0 falhas**, 1 desmarcado (§3), 35 min |
| Unitários do `web/` | **30/30** |
| E2E completo | **93/93** (3,5 min) |

**É a primeira regressão completa sem nenhuma falha.**

**Integridade depois dela:**
- `gastos.db` com md5 `bf7c7d3a…`;
- PostgreSQL local persistente idêntico ao retrato inicial;
- Supabase remoto com 37 aplicadas e a 1127 e a 1128 pendentes (só locais).
