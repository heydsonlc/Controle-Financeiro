# FIN-RECORRENCIA-REAL-1 — Validação real da geração e da transição T1

**Data:** 2026-10-21.

**Alvo:** projeto Supabase de teste **Controle-Financeiro** (`fzjmge…`). A Calculadora Judicial não foi tocada.

**Situação:** **validado**. Os dados fictícios foram removidos e o estado final ficou idêntico ao inicial, exceto pelas migrations autorizadas.

**Autorização:** usuário, 2026-10-21. Foram autorizados:
- o push de `8ebc96d`;
- as migrations `20261023090000` e `20261024090000`, só no banco de teste;
- os dados fictícios;
- os testes reais;
- a remoção obrigatória.

Ficaram vedados: alterar os perfis reais Pessoal e Empresa, e publicar no Cloudflare.

## 1. Sequência executada

1. **Push de `8ebc96d`** depois da revisão, sem segredos nem arquivos pessoais. O check "Supabase Preview" ficou `completed/skipped` e as duas migrations seguiram **pendentes**. Isso confirma que o deploy automático continua desligado.
2. **Impressão digital inicial**, somente leitura: 52 tabelas `public`, 2 usuários no Auth, Alembic `c4f7a2d91b3e`, migrations 3.
3. **Dry-run** do `supabase db push`: exatamente as duas migrations autorizadas.
4. **Aplicação** com `scripts/supabase_migrations.py aplicar --versoes 20261023090000,20261024090000`. As duas foram aplicadas e nenhuma ficou pendente.
5. **Verificação pós-migration** (somente leitura):
   - todas as funções pertencem a `postgres` (BYPASSRLS);
   - **nenhuma** tem EXECUTE para `anon`;
   - as internas não têm EXECUTE para `authenticated`: `plano_recorrencia`, `*_interno`, `exigir_gerador_novo`, `gerador_do_perfil`, `definir_gerador_recorrencia`, `dia_contratual` e `auditar_…`;
   - as 4 tabelas novas têm RLS forçada e nenhum privilégio para `anon` e `authenticated`;
   - `perfil_acesso.pode_gerir` tem padrão `false`;
   - **0 perfis atribuídos ao novo gerador**;
   - a Data API continua expondo só `graphql_public` e `financeiro`, com `public` bloqueado (`verificar_exposicao_supabase.py --via-cli`).
6. **Dados fictícios**, nesta ordem:
   - `supabase_perfis_seed_teste.py`: Perfil B (id 11) e perfil inativo temporários, e 4 vínculos de teste. `pode_gerir` ficou só nos vínculos TITULAR de teste; o vínculo da Empresa ficou como LEITOR.
   - `supabase_contas_seed_teste.py`.
   - `supabase_recorrencia_seed_teste.py` (novo): 4 itens fictícios e **o novo gerador atribuído só ao Perfil B temporário**.
   - `supabase_mvp_seed_teste.py`.
   - **Pessoal e Empresa não foram atribuídos e continuaram no Flask.**
7. **E2E real** (`run_e2e_real.py`, Auth e Data API reais, celular de 390 px): **30/30**. A pré-verificação passou a exigir a função `previa_geracao`.
8. **Coexistência com o Flask real** apontando para o banco de teste. Os resultados estão na §2.
9. **Limpeza**, na ordem inversa. A remoção de recorrência apagou:
   - 4 identidades e 1 execução;
   - 7 contas: 3 da Mensalidade B gerada no E2E, 2 faturas do Cartão B e 2 contas "Aluguel sala" geradas pelo Flask;
   - a configuração do cartão, os 4 itens, a atribuição do gerador e as 2 linhas de histórico.
   Depois vieram contas, perfis e MVP. Todos os arquivos de estado foram removidos.
10. **Impressão digital final:**
   - **conteúdo, contagens de `public`, Auth e Alembic idênticos ao início**;
   - mudou só a lista de migrations (+`20261023090000` e `20261024090000`);
   - as 4 tabelas novas existem e estão **vazias**;
   - `movimento_financeiro` ficou em 0 durante todo o teste.

## 2. Resultados

| Verificação | Resultado |
|---|---|
| Geração confirmada pelo usuário B no Perfil B (NOVO), com dispensa de 02/2027 | 5 criadas, 1 dispensada. Vencimentos 31/01, 31/03 e 30/04, com o dia contratual preservado |
| Repetição e reabertura do mês | Nada a gerar e nenhuma duplicata |
| Flask real abrindo 02, 03, 04 e 06/2027 no Perfil B (NOVO) | HTTP 200 e **0 contas e 0 compras novas**. A competência dispensada **não foi recriada**, e o log registra a guarda T1 |
| Flask real abrindo 05/2027 na Empresa (FLASK) | O Flask **continuou gerando**: Aluguel sala em 15/05 e 15/06 |
| Usuário A no Pessoal (gestor, perfil no Flask) | Vê o aviso "A geração deste perfil ainda é feita pelo sistema atual"; `gerar_mes` direto devolve HTTP 400 e nada é gravado |
| Usuário A na Empresa (LEITOR) | Vê o aviso "Somente quem gerencia este perfil pode gerar"; `gerar_mes` devolve 403 |
| Usuário A chamando `gerar_mes` e `previa_geracao` no Perfil B | 403. A função interna `plano_recorrencia` também é negada ao navegador |
| Pagamentos e movimentos bancários | Nenhum. `movimento_financeiro` ficou em 0 |

## 3. Riscos e pendências registrados

- **Faturas criadas exatamente ao mesmo tempo:** um cadastro de compra no Flask e a geração do novo motor, simultâneos no mesmo perfil.
  - A tabela legada `conta` não tem chave única para fatura (cartão + competência), então a duplicação é possível em teoria.
  - Em uso sequencial não há duplicata, e isso foi comprovado.
  - Por decisão do usuário, **deve ser corrigido antes do uso financeiro real**. Item FIN-FATURA-UNICA-1 no roadmap.
- Devolver um perfil ao Flask reativa a geração antiga, que desconhece as dispensas. Documentado em `docs/FIN_RECORRENCIA_T1.md`.
- **Para manter:** a troca de gerador de perfis reais (Pessoal e Empresa) exige autorização específica.

## 4. Arquivos desta etapa

- `scripts/supabase_recorrencia_seed_teste.py` (novo).
- `scripts/supabase_perfis_seed_teste.py`: `pode_gerir` nos vínculos de teste.
- `web/tests/e2e/run_e2e_real.py`: pré-verificação do FIN-RECORRENCIA-1/T1.
