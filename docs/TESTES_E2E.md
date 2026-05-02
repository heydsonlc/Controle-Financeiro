# Testes E2E com Playwright

## Objetivo

Os testes E2E validam fluxos reais em navegador para proteger o Controle Financeiro contra regressões de carregamento, Navegação e erros críticos de JavaScript.

No MVP TEST-1, o escopo é intencionalmente mínimo: smoke tests das rotas HTML principais, sem criar, editar, pagar, baixar ou excluir dados.

## Pré-requisitos

- Node.js e npm instalados.
- Ambiente Python do projeto criado em `venv/`.
- Dependências Python instaladas.
- Execução local, nunca apontando para DigitalOcean, produção ou banco remoto.

## Instalação

```bash
npm install -D @playwright/test
npx playwright install chromium
```

O MVP TEST-1 usa somente Chromium. Firefox e WebKit ficam fora deste MVP.

## Comandos

```bash
npm run test:e2e
npm run test:e2e:smoke
npm run test:e2e:smoke:headed
npm run test:e2e:headed
npm run test:e2e:functional
npm run test:e2e:functional:safe
npm run test:e2e:functional:create
npm run test:e2e:all
npm run test:e2e:debug
python -m pytest tests -q
```

Comandos equivalentes:

```bash
npx playwright test
npx playwright test tests/e2e/smoke.spec.js
npx playwright test tests/e2e/smoke.spec.js --headed
npx playwright test tests/e2e/functional/ --workers=1
npx playwright test --headed
npx playwright test --debug
```

Comandos oficiais apos TEST-BASE-1:

| Comando | Finalidade |
|---------|------------|
| `npm run test:e2e:smoke` | Smoke estavel das 13 rotas principais. Deve terminar com 13 passed e 2 skipped. |
| `npm run test:e2e:smoke:headed` | Mesmo smoke em navegador visivel para homologacao local. |
| `npm run test:e2e:functional` | Funcionais TEST-2A/2B com `--workers=1`; cria dados apenas se `/health` retornar `environment=testing`. |
| `npm run test:e2e:functional:safe` | Apenas testes `[safe]`, que abrem telas/modais e nao criam dados. |
| `npm run test:e2e:functional:create` | Apenas testes `[create]`; em `development`, devem ser skipped pelo guard de ambiente. |
| `npm run test:e2e:all` | Smoke + funcionais em sequencia. |
| `python -m pytest tests -q` | Valida a infraestrutura pytest com testes `test_*.py`. Scripts legados `teste_*.py` não são coletados automaticamente. |

## Servidor Flask

O Playwright está configurado para subir o Flask automaticamente via `webServer`, reutilizando um servidor existente em `http://127.0.0.1:5000` quando houver.

No Windows, o comando configurado é:

```bash
set FLASK_ENV=testing&& set FLASK_DEBUG=0&& venv\Scripts\python.exe -c "<sobe Flask em testing sem reloader>"
```

Em Linux/Mac, a configuração usa:

```bash
FLASK_ENV=testing FLASK_DEBUG=0 python -c "<sobe Flask em testing sem reloader>"
```

O uso de `FLASK_ENV=testing` mantém os testes no ambiente de teste da aplicação. Os testes E2E não devem usar banco remoto, DigitalOcean ou dados reais.

O comando usa a factory `create_app('testing')` e executa o Flask em `127.0.0.1:5000`, com `debug=False` e `use_reloader=False`, para evitar processos residuais do reloader durante a execução do Playwright. Para uso manual fora do Playwright, o fluxo cotidiano do projeto continua sendo `venv\Scripts\python.exe backend\app.py`.

### Guard de ambiente nos testes funcionais

Os testes funcionais de criacao são marcados com `[create]` e chamam `skipUnlessTestingEnvironment(...)` antes de qualquer mutação. Se o Playwright reutilizar um servidor já aberto em `development`, esses testes devem ser marcados como skipped, não como falha, e nenhum dado deve ser criado.

Os testes funcionais sem criacao são marcados com `[safe]`. Eles podem rodar em `development` porque apenas abrem telas/modais e validam estrutura visual mínima.

O script funcional usa `--workers=1` para reduzir consumo de memória e evitar OOM/worker crash observado no baseline do TEST-BASE-1.

## Rotas Cobertas no Smoke

- `/`
- `/configuracoes`
- `/despesas`
- `/cartoes`
- `/receitas`
- `/lancamentos`
- `/financiamentos`
- `/contas-bancarias`
- `/patrimonio`
- `/categorias`
- `/veiculos`
- `/preferencias`
- `/importar-cartao`

Cada rota valida:

- status HTTP 200;
- ausência de status 500;
- existência do `body`;
- existência de elemento estrutural simples;
- ausência de `pageerror`;
- ausência de `console.error`.

Warnings e logs de console não falham o teste neste MVP.

Exceção temporária: `favicon.ico` 404 é ignorado pelo helper de console, pois é uma requisição automática do navegador para um asset ainda não definido e não representa falha funcional das rotas testadas.

## Rotas com Pendência Conhecida

- `/financiamentos/seguro`: rota conhecida como pendente até UX-1B. Após UX-1A, `base.html` existe e a rota pode renderizar parcialmente, mas a tela ainda mantém estrutura visual legada com Bootstrap/Font Awesome órfãos e continua fora do smoke principal.
- `/indexadores`: rota existente, mantida fora do smoke principal até validação visual/asset dedicada.

Essas rotas aparecem como testes ignorados/diagnósticos, sem correção neste MVP.

## Uso em MVPs de UX

Para MVPs de interface, o smoke E2E deve ser executado antes e depois das alterações. No UX-1A, o baseline deve confirmar as 13 rotas principais passando antes da criação do shell visual, e a validação final deve repetir o smoke e a suíte Playwright completa.

No UX-1C, a migração das demais telas para `base.html` deve ser validada em lotes, repetindo o smoke após cada grupo de templates. Ao final, o smoke cobre as 13 rotas principais já dentro do shell visual, mantendo `/financiamentos/seguro` e `/indexadores` como rotas diagnósticas ignoradas.

No UX-2, o smoke E2E valida que Configurações continua carregando após deixar de ser hub de módulos e que as rotas removidas da tela continuam acessíveis pela sidebar e pelas rotas principais.

No UX-3A, o smoke E2E valida que a inclusão do bloco vazio `action_bar` no shell não desloca as telas existentes nem introduz erro crítico. A aplicação da faixa em telas específicas fica para etapas posteriores.

## Como Interpretar Falhas

Falha de status HTTP indica que a página não carregou corretamente.

Falha de `pageerror` indica exceção JavaScript não tratada no navegador.

Falha de `console.error` indica erro crítico reportado pela página ou por um asset carregado. A saída informa rota, tipo, mensagem e origem quando disponível.

Falhas em rotas específicas devem ser corrigidas em MVP próprio, sem alterar regras financeiras ou contratos de API sem diagnóstico.

## Regras de Dados

Os testes E2E do TEST-1:

- não criam seed;
- não criam registros;
- não editam registros;
- não pagam ou baixam despesas;
- não excluem dados;
- não chamam endpoints diretamente para mutação;
- não usam banco remoto.

## TEST-2A — Testes Funcionais de Baixo Risco

MVP TEST-2A implementou testes funcionais para os módulos mais seguros, sem dependências críticas e sem risco de contaminação de dados reais.

### Módulos cobertos

- **Categorias** (`tests/e2e/functional/categorias.spec.js`)
- **Contas Bancárias** (`tests/e2e/functional/contas-bancarias.spec.js`)
- **Receitas / Fontes** (`tests/e2e/functional/receitas.spec.js`)

### Fluxos por módulo (2 testes cada)

1. Abre o modal ao clicar no botão da action bar (sem criar dados).
2. Cria um registro com nome prefixado `TESTE_E2E_` + timestamp e confirma que aparece na lista.

### Execução

```bash
npm run test:e2e:functional
# ou
npx playwright test tests/e2e/functional/
```

### Helpers criados

- `tests/e2e/helpers/test-data.js` — geradores `makeCategoriaNome()`, `makeContaNome()`, `makeFonteNome()` com prefixo `TESTE_E2E_` + timestamp.
- `tests/e2e/helpers/api.js` — `skipUnlessTestingEnvironment(test, request, label)`: verifica `GET /health` e marca testes de criacao como skipped se `environment !== 'testing'`, impedindo criacao de dados em banco real.
- `tests/e2e/helpers/assertions.js` — `assertModalAberto(page, selector)` e `assertTextoVisivel(page, texto)`.

### Regra de ambiente

Testes que criam dados chamam `skipUnlessTestingEnvironment(...)` como primeira instrução. Se o Playwright reutilizar um servidor de desenvolvimento (`reuseExistingServer: true`), os testes de criação ficam skipped com mensagem explícita em vez de persistir dados reais.

### Cautelas aplicadas

- `#fonte-recorrente` (Receitas) é desmarcado explicitamente antes de salvar, pois vem `checked` por padrão e geraria orçamentos automáticos no banco de testing.
- `page.on('dialog', dialog => dialog.accept())` captura os `alert()` de sucesso de todos os módulos.
- Patrimônio foi coberto posteriormente no TEST-2B.

### Comportamento esperado com servidor de desenvolvimento ativo

- 5 testes `[safe]` de abertura de modal: **passam** (não criam dados).
- 5 testes `[create]` de criação: **skipped** quando `/health` retorna `environment=development`.
- Para executar criação real, parar o servidor de desenvolvimento e deixar o Playwright subir o servidor `testing`.

## TEST-2B - Testes Funcionais Complementares

MVP TEST-2B ampliou a cobertura funcional em fluxos de baixo/médio risco, sem alterar a aplicação e sem tocar em banco real.

### Módulos cobertos

- **Veículos** (`tests/e2e/functional/veiculos.spec.js`)
- **Patrimônio / Caixinhas** (`tests/e2e/functional/patrimonio.spec.js`)

### Fluxos por módulo (2 testes cada)

1. Abre o modal principal da tela a partir da action bar, sem criar dados.
2. Cria um registro simples com nome prefixado `TESTE_E2E_` + timestamp e confirma que aparece na lista.

### Regra de ambiente

Os testes de criação usam `skipUnlessTestingEnvironment(test, request, 'TEST-2B')` antes de qualquer mutação. Se o Playwright reutilizar um servidor em `development`, a criação é marcada como skipped de forma explícita para evitar gravação em PostgreSQL local ou qualquer banco fora de `testing`.

### Cautelas aplicadas

- Veículos cria apenas um veículo `SIMULADO`, com campos obrigatórios mínimos, sem testar manutenção, financiamento, transporte por app, simulação ou exclusão.
- Patrimônio cria apenas uma caixinha com saldo inicial zero, sem testar transferências, inativação, ajustes de saldo, metas complexas ou exclusão.
- Patrimônio entrou no TEST-2B porque `frontend/static/js/patrimonio.js` já usa API relativa `/api/patrimonio`.

### Fora do escopo do TEST-2B

- Despesas;
- Cartões;
- Financiamentos;
- Lançamentos;
- pagamentos/baixas;
- transferências patrimoniais;
- Importar Cartão/CSV;
- login/mobile;
- exclusões.

## TEST-BASE-1 — Infraestrutura de testes estabilizada (2026-05-01)

O TEST-BASE-1 estabilizou a execucao dos testes existentes sem criar novos fluxos sensiveis. O script funcional passou a usar `--workers=1`, os testes funcionais foram classificados com tags `[safe]` e `[create]`, e os testes de criacao passaram a ser skipped em `development` em vez de falhar por guard.

Tambem foi criado `pytest.ini` para estabilizar a descoberta Python usando apenas `test_*.py`. Os arquivos legados `teste_*.py` foram mantidos fora da coleta automatica porque executam codigo em tempo de import e podem mutar banco local; a conversao desses scripts para pytest seguro fica para MVP proprio.

Módulos sensíveis que continuam exigindo diagnóstico antes de testes funcionais:

1. **Despesas** — modal de nova despesa, edição, baixa de pagamento, filtros de competência
2. **Cartões** — fatura consolidada, lançamentos, modal de pagamento
3. **Financiamentos** — criação, parcelas, amortização, fluxo de pagamento
4. **Lançamentos** — histórico unificado, filtros, confirmação de receitas

Esses testes devem seguir o mesmo padrão de TEST-2A/2B: prefixo `TESTE_E2E_` + timestamp, `skipUnlessTestingEnvironment` obrigatório, sem criar dados fora do ambiente de teste.

Despesas é o módulo mais crítico para o usuário final e deve ser tratado como primeira entrega do TEST-BASE-1.

## Próximos Testes Planejados

- Despesas: nova despesa, edição, baixa (TEST-BASE-1);
- Cartões: fatura, lançamentos, pagamento (TEST-BASE-1);
- Financiamentos: parcelas, amortização (TEST-BASE-1);
- login/logout após SEG-1;
- proteção de rotas sem login;
- tela Despesas em viewport mobile;
- filtros de Competência;
- regressões visuais e funcionais por módulo.
