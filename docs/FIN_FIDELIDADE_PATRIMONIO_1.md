# FIN-FIDELIDADE-PATRIMONIO-1 (MVP 4) — Patrimônio e Mobilidade

**Situação (25/10/2026):** fase 1 de Patrimônio e fase 1 de Mobilidade (as duas só consulta) implementadas e testadas localmente.
- Mobilidade: §7.
- Com ela, nenhum módulo do menu continua "em migração".
- Sem commit, sem migration persistente e sem publicação. A migration `20261112090000` é local.

## 1. Tamanho e divisão

| Parte no Flask | Linhas |
|---|---|
| `routes/patrimonio.py` (21 rotas: caixinhas, transferências, bens, exportações, vínculos de documento) | 687 |
| serviços de patrimônio (empresarial, relatório Excel/PDF, sugestão a partir de documento) | 1114 |
| `patrimonio.js` / `.html` | 1334 / 691 |
| `routes/veiculos.py` + `routes/mobilidade_app.py` (34 rotas) | 683 + ~130 |
| serviços de mobilidade (projeções, uso, manutenção por km, financiamento do veículo, cenário ativo, assinaturas) | ~1820 |
| `veiculos.js` / `.html` | 3719 / 789 |

Mesmo critério do MVP 3: primeiro a consulta fiel, depois a escrita.
- O Flask não consulta o escritor único (`gerador_recorrencia`) em nenhuma rota de patrimônio ou de veículos.
- Se o novo aplicativo gravasse ali enquanto o Flask também grava, haveria dois escritores.

## 2. Patrimônio, fase 1 (feita): consulta

- **Migration `20261112090000_financeiro_patrimonio_leitura.sql`:** só funções de leitura.
  - `patrimonio_contas_tela(perfil, ativo)`: `GET /api/patrimonio/contas[?ativo=]`.
    - Ativas por padrão; `total_patrimonio` soma só as ativas.
    - Meta 0 vira nula (`ContaPatrimonio.to_dict`).
  - `patrimonio_conta_tela(perfil, id)`: `GET /contas/<id>`.
  - `patrimonio_transferencias_tela(perfil, data_inicio, data_fim, conta_id, id)`: `GET /transferencias[...]` e `/transferencias/<id>`.
    - Inclui os nomes das contas.
    - Ordem do Flask (data, mais recente primeiro). No empate o Flask não define ordem; aqui vale a de inserção, que é a que o Flask devolve na prática.
  - `patrimonio_bens_tela(perfil, filtros, id)`: `GET /bens` e `/bens/<id>`, só no perfil do tipo Empresa (como o Flask).
    - Filtros: categoria, status, documento ou status_documental (com os apelidos do Flask), ano, busca/q.
    - Serialização igual a `serializar_bem`: rótulos, chave e endereço da imagem, documento fiscal vinculado (vínculo ativo mais recente, com arquivo e categorias) e rótulo do documento.
  - `patrimonio_resumo_tela(perfil)`: `GET /bens/resumo`.
    - Total, lastro, pendências, aquisições do ano (ano corrente em Brasília), composição por categoria e as 6 pendências prioritárias.
  - `imagens_patrimonio()`: `GET /bens/imagens`.
    - O Flask lista a pasta `frontend/static/img`; aqui ficam fixas as 7 imagens `patrimonio*` versionadas, que são as mesmas.
- **Tela original** (`web/src/paginas/patrimonio.html`, gerada do template):
  - `url_for` das 3 imagens trocado por `/static/img/...`;
  - aviso da fase acrescentado;
  - as 10 imagens versionadas foram incluídas no build (`IMAGENS_ORIGINAIS`).
- **Adaptador** (`web/src/js/patrimonio-adaptador.js`):
  - rotas GET acima e `GET /api/perfis-financeiros/ativo` (o JS do Flask escolhe o modo Empresa pelo tipo do perfil);
  - qualquer outra ação responde, sem gravar: "Esta ação continua no sistema atual";
  - `GET /documentos-vinculaveis` responde lista vazia. Ela só alimenta o seletor de "vincular documento", ação que continua no Flask; sem ela a tela de bens não carregava, porque o Flask carrega tudo junto.

## 3. Testes

- **Fidelidade** (`tests/test_supabase_patrimonio_leitura.py`, **5 passaram**):
  - O **próprio Flask** cria no cluster descartável:
    - no Pessoal: 3 caixinhas (uma inativada, uma com meta 0) e 3 transferências (duas na mesma data);
    - na Empresa: 4 bens (com imagem, depreciação, baixado, sem categoria, sem data) e um vínculo com documento fiscal fictício.
  - Comparados **campo a campo** com o Flask: listas (ativas e inativas), conta, transferências (com filtro e por id), bens, detalhe, resumo, 8 combinações de filtros e imagens.
  - Também cobertos: privilégios, modo Pessoal (sem bens; detalhe 403), isolamento entre titulares e "nada gravado".
- **E2E** (`web/tests/e2e/patrimonio_tela.spec.mjs`, **2 passaram**), com dados fictícios de `semear_patrimonio_e2e`:
  - caixinhas e transferência do Perfil B;
  - escrita recusada sem gravar;
  - outro titular não vê as caixinhas;
  - no perfil Empresa (usuário A, leitor): bens, pendências e imagem.
- **`moldura.spec.mjs`:** Patrimônio saiu de "Em migração". Unitários: 30 passaram.
- **E2E completo (regressão dos MVPs 1–4):** **80 passaram**, 0 falhas.

## 4. Mobilidade: análise (sem implementação)

**Dependência de IDs de categoria (pedida no contrato):**
- O Flask **não** usa ID fixo. As categorias sistêmicas são achadas pelo código estável `categoria.codigo_sistema` (`MOB_COMBUSTIVEL`, `MOB_SEGURO_VEICULAR`, `MOB_TRIBUTOS_VEICULARES`, `MOB_REVISAO`, `MOB_MANUTENCAO`, `MOB_PNEUS`, `MOB_USO_VEICULO`, `MOB_APP`, `MOB_ASSINATURA`, `MOB_LAVAGEM`), em `categoria_default.obter_categoria_sistemica`.
- **Efeito colateral do Flask:** se o código não existe, essa função **cria** a categoria, ou promove uma de mesmo nome, durante leituras como as projeções.
  - No novo aplicativo, a leitura deve achar a categoria pelo código e **nunca criá-la**.
  - Se faltar, a tela informa a falta.
  - A criação fica com o Flask (ou com uma migration de dados autorizada, que use a mesma definição de `categoria_default.py`).
- A migration Alembic `a9b0c1d2e3f4` cria essas categorias. Antes da fase de Mobilidade, conferir no Supabase de teste se todas existem com `codigo_sistema`, em consulta somente leitura.
- O teste preexistente `test_categorias_sistemicas_mobilidade::test_projecoes_veiculo_usam_categorias_sistemicas_granulares` (KeyError `IPVA`) mostra que a projeção atual do Flask já não gera IPVA no cenário do teste. Isso precisa ser esclarecido antes de portar as projeções.

**Próxima fase (Mobilidade 1, só consulta):**
- `GET /api/veiculos`, `/<id>`, `/<id>/projecoes`, `/uso`, `/regras-km`, `/manutencoes-km`, `/financiamento`, `/cenario-ativo`, `/mobilidade/ativo`, `/mobilidade/assinaturas`.
- As projeções são cálculo (`mobilidade_service`, `veiculo_service`). Seguem o mesmo método do motor de recorrências: o Flask calcula nos mesmos dados fictícios e o resultado é comparado.
- O "cenário ativo" fica em arquivo em `DATA_DIR` (ver `docs/DEPLOY.md`), não no banco. Precisa de decisão de armazenamento antes de migrar.

## 5. Arquivos

**Novos:**
- `supabase/migrations/20261112090000_financeiro_patrimonio_leitura.sql`
- `tests/test_supabase_patrimonio_leitura.py`
- `web/src/paginas/patrimonio.html`
- `web/src/js/patrimonio-adaptador.js`
- `web/src/css/patrimonio-adaptacoes.css`
- `web/tests/e2e/patrimonio_tela.spec.mjs`

**Alterados:**
- `web/scripts/build.mjs`: CSS, JS e imagens do Patrimônio
- `web/src/moldura/em-migracao.json`
- `web/tests/unit/build.test.mjs`
- `web/tests/e2e/moldura.spec.mjs`
- `web/tests/e2e/run_e2e.py`
- `tests/supabase_local.py`: `semear_patrimonio_e2e`

## 6. Pendências e autorizações

1. Commit da fase 1 de Patrimônio.
2. Aplicação da migration `20261112090000` no Supabase de teste. Ela só cria funções de leitura e depende de 20261109 (contas bancárias) só pela ordem de aplicação.
3. Publicação na prévia: só consulta, com o aviso na tela.
4. **Escrita em Patrimônio** (caixinhas, transferências, bens): exige guarda de escritor único no Flask, que hoje não existe. Mesma decisão pendente do MVP 3 (`docs/FIN_FIDELIDADE_CONTRATOS_1.md` §6).
5. **Exportação Excel/PDF de bens:** pode ser feita no navegador (o XLSX já existe sem biblioteca no MVP 1). Fica para a fase de escrita/relatórios.
6. **Mobilidade:**
   - fase 1 feita (§7);
   - escrita (cadastro, projeções, ativação, financiamento, confirmação de previstas) depende do escritor único;
   - o defeito D-MOB1 do Flask precisa de decisão.

## 7. Mobilidade, fase 1 (feita): consulta

- **Migration `20261115090000_financeiro_mobilidade_leitura.sql`:** só funções de leitura.
  - `veiculos_tela(perfil, id)`: `GET /api/veiculos` e `/<id>`.
    - Inclui `Veiculo.to_dict` e o resumo mensal estimado: anuais diluídos por 12, arredondamento meio para cima, como `calcular_resumo_mensal_estimado_veiculo`.
  - `projecoes_mobilidade_tela(perfil, origem, id, meses)`: `GET /veiculos/<id>/projecoes` e `/api/mobilidade-app/<id>/projecoes`.
    - Lê as previstas que já existem.
    - Gerar projeções é POST e continua no Flask.
  - `veiculo_uso_tela`: `GET /uso`. Km por mês inferido das previstas de combustível CONFIRMADAS: litros do metadata ou valor/preço, vezes a autonomia.
  - `veiculo_regras_km_tela` e `veiculo_manutencoes_km_tela`: `GET /regras-km` e `/manutencoes-km`.
    - Estimativas: km restante, meses e data prevista.
    - Fonte de uso: histórico, projetado ou indisponível.
    - Impacto mensal: por km ou por tempo.
  - `veiculo_financiamento_tela`, `mobilidade_ativa_tela` (com nome da origem e recorrência), `mobilidade_assinaturas_tela`, `transporte_app_tela` (caminhos montados do metadata da última prevista).
  - `mobilidade_categorias_tela`: `GET /api/categorias` (globais, como no Flask).
  - "Hoje" = data de Brasília. Metadata inválido = objeto vazio, como o `except` do Flask.
- **Tela original** (`web/src/paginas/mobilidade.html`, de `frontend/templates/veiculos.html`): aviso da fase. As 5 ilustrações versionadas foram incluídas no build.
- **Adaptador** (`web/src/js/mobilidade-adaptador.js`):
  - rotas GET acima;
  - qualquer outra ação responde, sem gravar, "continua no sistema atual".
  - Isso inclui a pré-visualização de ativação: no Flask ela chama `obter_categoria_sistemica_id`, que **cria** categorias `MOB_*` quando faltam.
  - O antigo `GET /api/veiculos/cenario-ativo` lê um arquivo global em `DATA_DIR`, fora do banco e sem perfil. Não é usado na carga da tela e fica "em migração" até uma decisão de armazenamento.
- **Achados do Flask:**
  - **D-MOB1 (defeito):** salvar o financiamento do veículo (`POST /api/veiculos/<id>/financiamento`) **sempre falha** com 500 `name 'veiculo' is not defined`.
    - Em `veiculo_financiamento_service.upsert_financiamento`, linhas 181 e 211, a variável se chama `v`.
    - Nada é gravado (rollback). O teste documenta a falha.
  - Mensagem "Caminho nÇœo encontrado" com codificação quebrada no Flask. Aqui: "Caminho não encontrado".
  - `GET /api/categorias` do Flask não ordena (ordem física da tabela, que muda quando o Flask atualiza categorias). Aqui: por id.
- **Testes:**
  - `tests/test_supabase_mobilidade_leitura.py`, **4 passaram**.
    - O **próprio Flask** cria 2 veículos (com as projeções que ele gera), 3 regras de manutenção, 2 assinaturas e um caminho de transporte por app.
    - Combustível do mês confirmado, cenário ativo e financiamento fictício gravados direto no banco (por causa do D-MOB1).
    - **23 rotas GET** comparadas campo a campo com o Flask, inclusive erros (veículo e caminho inexistentes) e parâmetros fora da faixa.
    - Também cobertos: privilégios e isolamento.
  - `web/tests/e2e/mobilidade_tela.spec.mjs`, **2 passaram**:
    - comparação e configuração com veículo, assinatura e app do Perfil B;
    - geração de projeções recusada sem gravar;
    - outro titular não vê.
  - `moldura.spec.mjs`: Mobilidade saiu de "Em migração", e a lista de módulos em migração ficou vazia. Unitários: 30 passaram.
- **Arquivos:**
  - novos: migration `20261115090000`, `tests/test_supabase_mobilidade_leitura.py`, `web/src/paginas/mobilidade.html`, `web/src/js/mobilidade-adaptador.js`, `web/src/css/mobilidade-adaptacoes.css`, `web/tests/e2e/mobilidade_tela.spec.mjs`;
  - alterados: `build.mjs`, `build.test.mjs`, `moldura.spec.mjs`, `em-migracao.json`, `run_e2e.py`, `tests/supabase_local.py` (`semear_mobilidade_e2e`).
