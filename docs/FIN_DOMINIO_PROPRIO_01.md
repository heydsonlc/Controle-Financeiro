# FIN-DOMINIO-PROPRIO-01: domínio financas.kortexbrasil.com

Configuração de infraestrutura (12–13/11/2026). A mesma aplicação, o mesmo projeto Cloudflare Pages e o mesmo Supabase passam a responder também em `https://financas.kortexbrasil.com`. Não houve deploy, commit funcional, migration nem alteração de dados.

## 1. Diagnóstico

| Item | Situação |
|---|---|
| Conta Cloudflare | a mesma dos demais projetos Kortex |
| Projeto Pages | `controle-financeiro` (branch de produção `producao`, deploy `5d608ca5`, versão `7e035c5`); sem domínio próprio antes |
| Zona `kortexbrasil.com` | no Cloudflare da mesma conta (nameservers `kianchau` e `mckinley.ns.cloudflare.com`), ativa; o apex `kortexbrasil.com` pertence ao projeto `kortex-site` |
| Subdomínio `financas` | inexistente (NXDOMAIN, sem curinga): sem conflito |
| Outros registros da zona | `api`, `_domainconnect`, apex, `portal`, `www`, `_dmarc`, `pagamentos` (Worker): intocados |
| Endereços fixos no código | nenhum; a ponte e os comprovantes usam `window.location.origin` |
| CSP | `default-src 'self'` + Supabase; não depende do domínio |
| Autenticação | só e-mail e senha (`signInWithPassword`); sessão no `localStorage` (`cf-financeiro-auth`), por endereço; não há recuperação de senha, link mágico, OAuth nem `redirectTo` |
| CORS do Supabase | `Access-Control-Allow-Origin: *` no login e nas funções |

## 2. Alterações realizadas

1. **Domínio no projeto Pages:** `financas.kortexbrasil.com` adicionado ao projeto `controle-financeiro` pela API oficial de Custom Domains, com a credencial do wrangler (escopo `pages:write`).
2. **DNS:** registro criado pelo titular no painel, porque a credencial não tem permissão de escrita em DNS.
   - Tipo: `CNAME`
   - Nome: `financas`
   - Destino: `controle-financeiro-jah.pages.dev`
   - Proxy ligado, TTL automático
3. **Ativação:** verificação e certificado ativos às 22:07 de 12/11. Certificado emitido pelo Cloudflare com a autoridade Google, válido até 11/02/2027 e renovado automaticamente.

**Não alterados:**
- nameservers e demais registros DNS;
- o endereço antigo;
- o Supabase: Site URL, Redirect URLs, usuários, RLS e chaves;
- código, banco e migrations.

**Supabase Auth:** a Site URL e as Redirect URLs só valem para links enviados por e-mail (confirmação, recuperação, convite), que o app não usa. O login por senha funciona em qualquer origem. Por isso não é preciso acrescentar o domínio novo agora. Se no futuro houver recuperação de senha pelo app, acrescentar `https://financas.kortexbrasil.com/**` às Redirect URLs e, depois de homologado, usá-lo como Site URL.

## 3. Verificações (N2)

| Verificação | Endereço novo | Endereço antigo |
|---|---|---|
| HTTPS | TLS 1.3, certificado para `financas.kortexbrasil.com` | inalterado |
| HTTP → HTTPS | 301, preservando caminho e parâmetros | inalterado |
| Arquivos servidos (169) | idênticos ao deploy, salvo a linha injetada do Web Analytics (seção 4) | 169 idênticos |
| Páginas protegidas sem login (17) | todas redirecionam ao login (`/?next=...`) | idem |
| Cabeçalhos | CSP, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy`, `Permissions-Policy` preservados | idem |
| CORS do Supabase para a nova origem | login e funções: 200 | n/a |
| Erros de JS e CSP | só os bloqueios do script do Web Analytics (66 = 33 carregamentos × 2) | nenhum |
| Banco | migrations 67; nenhuma gravação da configuração | — |

**Retrato da produção:** entre o fim do saneamento e a configuração, só aparece o uso normal do titular: em 12/11 foi criada e paga uma despesa de R$ 100,00 ("Conviver - Apresentação de Encerramento"), e a Caixa foi de 600,92 para 500,92. Nada vem da troca de domínio.

**Ressalva:** nesta máquina o antivírus (Avast Web/Mail Shield) intercepta o TLS, então o emissor visto localmente é o do antivírus. O certificado real foi conferido pela API do Cloudflare (ativo, autoridade Google).

**Homologação com login:** é feita pelo titular. Não há usuário de teste na produção e a senha não é usada pelo agente. O titular deve:
- entrar em `https://financas.kortexbrasil.com`;
- abrir Dashboard, Despesas, Receitas, Cartões, Mobilidade e Consórcios;
- atualizar uma rota interna e sair.

## 4. Pendências de infraestrutura

| Item | Recomendação |
|---|---|
| Cloudflare Web Analytics da zona | injeta `static.cloudflareinsights.com/beacon.min.js` nas páginas do subdomínio; a CSP bloqueia (nada é enviado), mas gera erro no console. Recomenda-se excluir o host `financas.kortexbrasil.com` da injeção automática (Web Analytics → site `kortexbrasil.com` → regras), sem afrouxar a CSP |
| HSTS | ausente nos dois endereços (situação anterior); avaliar ativar na zona depois da homologação |
| Redirecionamento 301 do endereço antigo | só depois da homologação completa e com autorização; preservar caminho e parâmetros. Observação: a sessão é por endereço, então quem migrar precisa entrar de novo uma vez |
| Supabase Auth | sem mudança necessária enquanto não houver fluxos por e-mail |

## 5. Recuperação

Para desfazer, basta remover o domínio personalizado do projeto Pages e o CNAME `financas`. O endereço antigo, o projeto e o Supabase não dependem deles.
