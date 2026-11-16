# FIN-CACHE-01 — Atualização garantida de JS e CSS após cada publicação

**Situação:** preparado no ramo local `reg-08-leitura-classificacao`, em commit próprio, separado do FIN-REG-08. **Sem push e
sem deploy.** Não depende de alterar a configuração da zona do Cloudflare.

## 1. Ocorrência

Depois da publicação do FIN-MOBILE-11/12 (15/11/2026, deploy `8685a983`), o titular relatou que os botões novos da página
principal mobile (Documentos e Mobilidade) **apareciam, mas não tinham ação**.

Por decisão do titular, a correção é definitiva, no mecanismo de atualização: o HTML revalida, JS e CSS recebem versão, e o cache
dos arquivos estáticos grandes (modelos de OCR) é mantido. Primeiro diagnosticar e só depois corrigir, sem presumir que o cache seja a
causa comprovada.

## 2. Diagnóstico (produção, somente leitura)

| Recurso | `Cache-Control` servido | Origem |
|---|---|---|
| HTML (`/inicio`, `/documentos-mobile`…) | `public, max-age=0, must-revalidate` | Padrão do Cloudflare Pages |
| JS e CSS (`/js/*.js`, `/css/*.css`) | `public, max-age=14400, must-revalidate` (4 h) | "Browser Cache TTL" da **zona** do domínio, que substitui o padrão do Pages para arquivos estáticos |

- Antes da correção, os endereços de JS e CSS eram sempre os mesmos (`js/inicio-mobile.js`, `js/mobile-comum.js`…).
- Depois de uma publicação, o navegador busca o HTML novo, que sempre revalida, mas pode reaproveitar por até 4 h os módulos
  antigos que já tem em cache. O HTML novo traz os botões novos; o JS antigo não conhece esses botões (em `MODULOS_ATIVOS`,
  `mobile-comum.js`) e não liga a ação.
- Isso é coerente com o relato: botões visíveis e sem ação, e o problema some ao limpar os dados do site ou depois de 4 h.

**Conclusão:** a causa mais provável, compatível com tudo o que foi observado, é a combinação de HTML novo com JS antigo do cache.
Não foi possível reproduzir no aparelho do titular, e por isso ela fica registrada como **causa provável**, não comprovada. A
correção abaixo elimina essa classe de problema seja qual for o motivo do JS antigo (cache do navegador, do sistema ou do
aplicativo instalado na tela inicial).

## 3. Correção

`web/scripts/versionar.mjs`, chamado no fim do build (`construir`):

- **Toda referência a JS/CSS do próprio site recebe `?v=<hash do conteúdo>`** (12 hexadecimais do SHA-256):
  - no HTML: `src` e `href`;
  - nos módulos: `import … from`, `export … from`, `import './x.js'`, `import('…')` com texto fixo e
    `new URL('…', import.meta.url)`.
- **Hash encadeado:** o hash de um módulo inclui o hash do que ele importa. Uma mudança num módulo interno muda o endereço de
  quem o importa, até o HTML. Importações em ciclo recebem um hash comum.
- **Mesmo arquivo, mesmo endereço em todo lugar:** cada módulo continua sendo carregado uma única vez, e o estado compartilhado
  entre módulos (sessão, perfil ativo) não se divide.
- **Arquivo que não mudou mantém o endereço**, e com ele o cache (pdf.js, Supabase, Chart.js e CSS sem alteração não são baixados
  de novo).
- **Vendor não é lido por dentro**, só recebe a versão. A pasta do OCR já leva a versão no nome (`vendor/tesseract-7.0.0/`), não
  recebe consulta, e é servida com `Cache-Control: public, max-age=31536000, immutable` (`_headers`).
- **Build interrompido** se uma importação ou referência apontar para arquivo inexistente no dist.
- **HTML:** continua `max-age=0, must-revalidate` (padrão do Pages, conferido em produção). Por isso o HTML novo chega sempre, e é
  ele que aponta para os endereços novos.

Com isso, a configuração de 4 h da zona deixa de causar mistura de versões: endereço novo significa arquivo que o navegador
ainda não tem.

### Por que não só ajustar a zona

Mudar o "Browser Cache TTL" para "Respeitar cabeçalhos existentes" ainda deixaria o navegador revalidando cada JS a cada carga, o
que custa mais nas redes móveis. Também continuaria dependendo de uma configuração fora do repositório. A versão por conteúdo
resolve no próprio build e permite manter o cache longo. O ajuste da zona continua opcional e pendente de decisão do titular.

## 4. Testes

- `web/tests/unit/versionar.test.mjs`:
  - referências do HTML e dos módulos (inclusive import em várias linhas, `export * from`, `import()` e `new URL`);
  - consulta própria (`?v=2` dos ícones) e endereço externo intactos;
  - ciclo com hash comum;
  - propagação de mudança até o HTML, com arquivos não alterados mantendo o endereço;
  - build determinístico;
  - referência inexistente interrompe o build.
- `web/tests/unit/build.test.mjs`: no dist real, **nenhuma** referência a JS/CSS do site sem `?v=`, o mesmo arquivo com a mesma
  versão em todo lugar, e a pasta do OCR com cache longo. As verificações de estrutura existentes leem o dist sem a versão.
- Suíte e2e completa no dist versionado (resultado em `docs/FIN_REG_08_HOMOLOGACAO.md`). O servidor local do e2e ignora a consulta
  ao aplicar os cabeçalhos, como o Cloudflare.

## 5. Conferência após a publicação

- Baixar o HTML publicado e conferir que toda referência a JS/CSS tem `?v=`.
- Baixar cada endereço versionado e comparar o hash com o dist local (o script de conferência dos arquivos servidos continua
  valendo, pois os caminhos não mudaram).
- Conferir `Cache-Control` do HTML (`max-age=0`) e da pasta do OCR (`immutable`).

## 6. Reversão

Deploy anterior. A correção só muda o build: não há migration nem dado envolvido.
