# FIN-MVP-MOBILE-PUBLICACAO-02 — Pagamentos, Recorrências, Perfis e ícone

**Data:** 15/11/2026.
**Autorização:** mensagem do titular de 15/11/2026: "pode fazer o deploy direto.. não vou testar.. pode fazer o deploy das pendências, pagamentos, recorrências, usuário e ícone". Por isso não houve homologação no Firefox antes da publicação.

## O que foi publicado

| Item | Ramo / commits |
|---|---|
| FIN-MVP-MOBILE-08 Pagamentos (homologado em 15/11/2026) | `835ab96`, `f7a1225`, `cf132c2` |
| FIN-MVP-MOBILE-09 Recorrências | `442152c` (merge do ícone), `deaa288`, `e2142c7`, `c4c689c` |
| FIN-MVP-MOBILE-10 Alternância de perfis | `bd1a314`, `8260e19`, `1d5c11d` |
| FIN-MVP-MOBILE-ICON-02 Carteira do portal no símbolo da Página Principal | `b0b6a3b` |

A correção P23 da Lista não entrou porque foi revista e é improcedente (`docs/FIN_MVP_MOBILE_09_RECORRENCIAS.md`, seção 6). Ela aguarda a decisão do titular para ser encerrada.

## Verificações antes da publicação

- Nenhuma migration e nenhuma alteração em `supabase/` entre `origin/main` (`86110e2`) e `b0b6a3b`. Continuam 67 migrations.
- Regressão integrada (suíte E2E completa, banco descartável) no ramo final `mobile-10-perfis`: **255 aprovados, 0 reprovados, 0 não executados** (8,5 min). Unitários: 120/120.
- Build de produção feito numa pasta separada do scratchpad, com o `config.js` idêntico ao servido em produção (só valores públicos). Comparado com o build publicado em c3dcada4: 7 arquivos novos (as duas páginas, seus scripts e CSS, e `recorrencias-servico.js`), 9 alterados (Página Principal, Despesas, Recorrências, sessão) e nenhum removido. `_headers` idêntico.

## Publicação

- **Push:** `86110e2..b0b6a3b` em `main`, por avanço rápido, sem force.
- **Deploy Cloudflare Pages:** `dd64dcb6-5eae-4158-8a3f-5e96c6ded5c6`, produção, branch `producao`, origem `b0b6a3b`.
- **Conferência:** `financas.kortexbrasil.com` e o endereço do Pages servem os arquivos do build: 18 de 18 conferidos por hash, incluindo as páginas e os scripts novos e o ícone. Num navegador sem login, as páginas protegidas levam ao login, sem erro de console nem resposta de erro (fora o script de estatísticas da própria Cloudflare, bloqueado pela política de segurança, como antes).
- **Rollback:** deploy `c3dcada4`, que contém só o ícone da PWA. Nenhum dado financeiro foi alterado e nenhum rollback de dados se aplica.

## Pendente com o titular

- Conferência com login em produção: Pagamentos, Recorrências e troca de perfil.
- Reinstalação do app no iPhone para ver o ícone novo.
- Decisão sobre a P23: encerrar sem alteração.
