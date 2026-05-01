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
npm run test:e2e:headed
npm run test:e2e:debug
```

Comandos equivalentes:

```bash
npx playwright test
npx playwright test tests/e2e/smoke.spec.js
npx playwright test --headed
npx playwright test --debug
```

## Servidor Flask

O Playwright está configurado para subir o Flask automaticamente via `webServer`, reutilizando um servidor existente em `http://localhost:5000` quando houver.

No Windows, o comando configurado é:

```bash
set FLASK_ENV=testing&& set FLASK_DEBUG=0&& venv\Scripts\python.exe -c "<sobe Flask em testing sem reloader>"
```

Em Linux/Mac, a configuração usa:

```bash
FLASK_ENV=testing FLASK_DEBUG=0 python -c "<sobe Flask em testing sem reloader>"
```

O uso de `FLASK_ENV=testing` mantém os testes no ambiente de teste da aplicação. Os testes E2E do TEST-1 não devem usar banco remoto, DigitalOcean ou dados reais.

O comando usa a factory `create_app('testing')` e executa o Flask com `debug=False` e `use_reloader=False` para evitar processos residuais do reloader durante a execução do Playwright. Para uso manual fora do Playwright, o fluxo cotidiano do projeto continua sendo `venv\Scripts\python.exe backend\app.py`.

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

## Próximos Testes Planejados

- sidebar/topbar após UX-1A;
- login/logout após SEG-1;
- proteção de rotas sem login;
- tela Despesas em viewport mobile;
- abertura do modal de pagamento;
- baixa de despesa;
- filtros de Competência;
- regressões visuais e funcionais por módulo.
