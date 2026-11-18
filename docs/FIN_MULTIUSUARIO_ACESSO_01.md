# FIN-MULTIUSUARIO-ACESSO-01 — Entrada por convite, ativação da conta e administração da plataforma

**Situação:** implementado e ensaiado **localmente** em 18/11/2026, no ramo `multiusuario-acesso-01` (sobre o
`cadastros-padrao-01`). **Nada em produção:** sem push, sem deploy, migration `20270102090000` **não aplicada**, nenhum convite
real, nenhum usuário criado, cadastro público **continua desligado**. Terceira etapa da fila multiusuário; depende do
FIN-MULTIUSUARIO-SEGURANCA-01 e do FIN-CADASTROS-PADRAO-01.

## 1. Como alguém passa a usar o aplicativo

1. O **administrador da plataforma** registra, no aplicativo, um **convite** para um e-mail (validade de 1 a 30 dias).
2. O e-mail com o link é enviado pelo **Supabase Auth** (convite do próprio Supabase, pelo painel do projeto), para o mesmo
   endereço. O aplicativo não envia e-mail e o navegador não tem credencial para criar usuários.
3. A pessoa abre o link, **define a senha** (`definir-senha.html`) e cai no **primeiro acesso** (`primeiro-acesso.html`).
4. No primeiro acesso ela dá nome ao primeiro perfil e **ativa a conta**. A ativação é uma operação única no banco.

Quem tem login no Supabase mas não tem convite válido registrado no aplicativo **não ativa a conta e não usa nada**. O convite
do aplicativo não é credencial: quem prova a identidade é o login do Supabase Auth, com o e-mail confirmado; o convite só
autoriza aquele e-mail. O aplicativo **não guarda senha nem token**.

## 2. Conta da plataforma

`financeiro.usuario_plataforma`: uma linha por conta, `ATIVA` ou `SUSPENSA`. **Sem conta ativa, nenhuma função do aplicativo
responde.** A conferência fica em dois lugares:

- nas funções centrais de acesso ao perfil (`pode_acessar_perfil`, `pode_gerir_perfil`, `gere_perfil`, `meus_perfis`), por onde
  passa toda função que recebe um perfil;
- como primeira instrução das funções expostas que não recebem perfil (22) e na guarda do catálogo padrão. O gerador da
  migration **interrompe** se aparecer função exposta sem perfil que não esteja coberta.

As contas que já têm perfil ficam `ATIVA` na migration: para elas nada muda. A resposta a quem não tem conta ativa é a mesma,
nunca tenha sido ativada ou esteja suspensa.

## 3. Convites

`financeiro.convite`: e-mail, situação (`PENDENTE`, `USADO`, `REVOGADO`; vencido aparece como `EXPIRADO`), validade, número de
envios, quem registrou, quem usou. Não tem token.

| Regra | Como é garantida |
|---|---|
| Uso único | a ativação marca o convite como `USADO`, na mesma transação |
| Validade limitada | 1 a 30 dias (padrão 7); vencido não ativa |
| Um pendente por e-mail | índice único; registrar outro com um pendente válido é recusado; o vencido é encerrado pelo novo |
| Revogação | pelo administrador; o revogado não ativa nem é reenviado |
| Reenvio controlado | no máximo 5 envios por convite e um a cada 10 minutos; renova a validade |
| Conta existente | e-mail que já tem conta no aplicativo não recebe convite (inclusive conta suspensa) |
| Login já existente no Supabase, sem conta no aplicativo | o convite é aceito e a tela do administrador avisa "já tem login criado" |

## 4. Ativação (`ativar_minha_conta`)

Uma transação, **repetível sem efeito**. A identidade é a da sessão e o e-mail é o que o Supabase Auth tem para ela, já
confirmado: nada do que o usuário envia decide quem ele é, qual convite vale ou que permissão recebe.

Cria: a conta da plataforma, o primeiro perfil (dono = o próprio usuário, marcado como padrão), o vínculo de titular, o gerador
do perfil, as preferências do usuário e as **categorias de cartão padrão** do perfil. O catálogo padrão de categorias de
despesa e de palavras-chave não é copiado: é o mesmo para todos (etapa anterior).

Não cria conta bancária, despesa, lançamento, nem copia nada de outro usuário. Se qualquer passo falhar, nada fica gravado: não
existe conta parcialmente configurada. Repetir (segundo toque, retomada depois de falha de rede) devolve o estado atual.

## 5. Administrador da plataforma

É uma conta ativa marcada em `financeiro.administrador_plataforma` (ato do operador do banco, da etapa de segurança). Pode:
registrar, reenviar e revogar convites; ver a situação das contas; suspender e reativar; ver a auditoria de acesso; manter os
catálogos padrão e os índices de referência (etapas anteriores).

**Não tem acesso funcional aos dados financeiros de outros usuários.** As funções de administração só leem as tabelas de
acesso; a lista de contas informa e-mail, situação, datas e **quantidade** de perfis. O administrador continua recusado no
perfil de qualquer outro usuário, como qualquer pessoa.

O administrador não suspende a própria conta nem a de outro administrador. Se o único administrador perder o acesso, o
operador do banco redefine a situação (`definir_conta_plataforma`, não executável pelo navegador).

## 6. Matriz de permissões

| Operação | Sem sessão | Login sem conta ativa | Usuário | Administrador |
|---|:--:|:--:|:--:|:--:|
| Ver a situação da própria conta | — | sim | sim | sim |
| Ativar a própria conta (com convite válido) | — | sim | — (já ativa) | — |
| Usar os próprios perfis e dados | — | — | sim | sim (os dele) |
| Ver ou alterar perfil ou dado de outro usuário | — | — | — | **—** |
| Criar perfil, categoria particular, palavra-chave própria | — | — | sim | sim |
| Alterar o catálogo padrão e o modelo de categorias de cartão | — | — | — | sim |
| Manter índices de referência (TR) | — | — | — | sim |
| Registrar, reenviar, revogar convite | — | — | — | sim |
| Ver contas, suspender, reativar, ver auditoria de acesso | — | — | — | sim |
| Tornar alguém administrador; mudar a situação pelo banco | — | — | — | — (só o operador do banco) |

Nenhum atributo de autorização é editável pelo usuário: papel, administração, situação da conta e dono do perfil só mudam por
funções que conferem quem pede, e as tabelas não são acessíveis diretamente.

## 7. Recuperação e segurança de acesso

| Caso | Tratamento |
|---|---|
| Esqueci a senha | `recuperar-senha.html` pede o link ao Supabase Auth. A resposta é **a mesma** exista ou não conta com o e-mail |
| Link de convite ou de recuperação | `definir-senha.html`: o link é lido uma vez e retirado do endereço; senha com 10+ caracteres, letras e números (a política do Supabase continua valendo); depois de salvar, as outras sessões da conta são encerradas |
| Link vencido, já usado ou adulterado | mensagem única de link inválido, com atalho para pedir outro |
| E-mail não confirmado | a ativação é recusada |
| Convite vencido | aviso para pedir novo convite; o reenvio registrado pelo administrador renova a validade |
| Conta suspensa | a sessão aberta deixa de receber qualquer resposta **na hora** (a conferência é feita em cada chamada, no banco); nada é apagado; a reativação devolve o acesso |
| Erros | não dizem se outro e-mail tem conta, convite ou suspensão |

**Conferido em produção (somente leitura, configuração pública do Auth, 18/11/2026):** cadastro público desligado; confirmação
de e-mail exigida; só o provedor de e-mail e senha.

**A conferir pelo titular no painel do Supabase antes do primeiro convite** (não é visível de fora):

1. Tamanho mínimo e exigências da senha (recomendado: 10+, letras e números) e proteção contra senhas vazadas.
2. Limites de tentativas e de envio de e-mail (login, recuperação, convite).
3. Duração da sessão e tempo de inatividade.
4. Endereços de redirecionamento permitidos: o domínio do aplicativo, com `definir-senha.html`.
5. Modelos de e-mail de convite e de recuperação apontando para `definir-senha.html`; validade do link.

## 8. Telas

- **Administração da Plataforma** (`administracao.html`): atalho no menu só para o administrador. Três abas — Convites
  (formulário de uma linha e lista), Usuários, Auditoria. Uma linha por item, botões pequenos.
- **Primeiro acesso**, **Definir senha**, **Recuperar senha**: páginas simples, no formato da entrada.
- Entrada: atalho "Esqueci minha senha". Não há cadastro na tela.
- Qualquer página aberta por conta sem acesso liberado leva ao primeiro acesso, que explica a situação.

## 9. Migration `20270102090000` e reversão

Geradas por `scripts/gerar_migration_acesso.py` (parte fixa em `scripts/acesso_estrutura.sql`; as funções sem perfil recebem
só a linha da exigência de conta ativa sobre a definição vigente). Nenhum registro financeiro é alterado.

Reversão: `supabase/reversao/20270102090000_multiusuario_acesso_anterior.sql`. Devolve as 32 funções e retira a estrutura. É
**recusada** enquanto houver conta suspensa (a regra anterior devolveria o acesso a ela) ou convite pendente. O histórico de
convites e a auditoria de acesso são apagados pela reversão: exportar antes, se preciso. Contas ativadas por convite continuam
existindo, com os seus perfis.

## 10. Ensaio na cópia fiel da produção

`scripts/ensaio_multiusuario_acesso.py` (continua o ensaio da etapa anterior, no mesmo banco descartável).

| Passo | Resultado |
|---|---|
| Migration | nenhuma tabela de dados muda; a conta do titular fica ativa e administradora; **todas** as leituras de tela do titular idênticas; logins do Supabase sem perfil continuam sem acesso |
| Convite e ativação de usuário fictício | sem convite, recusada; com convite, cria só perfil, vínculo, gerador, preferências e categorias de cartão padrão; repetir não cria nada; leituras do titular idênticas; o administrador não alcança o perfil novo |
| Suspensão e reativação | nada responde à conta suspensa; nada é apagado; reativada, volta a usar |
| Reversão | estrutura retirada; dados idênticos; funções idênticas às de antes (3 delas a menos do fim de linha do texto); migration reaplicada sem erro |

Resultado: **70 verificações (28 desta etapa), nenhuma falha** (18/11/2026).

## 11. Testes

| Verificação | Resultado |
|---|---|
| `tests/test_supabase_acesso.py` (convite válido, vencido, revogado, reutilizado; e-mail com conta; ativação incompleta e repetida; suspensão; tentativa de administração por usuário comum; administrador sem dado financeiro; reversão) | 12/12 |
| **Permanente:** conta suspensa e conta nunca ativada chamam todas as funções expostas e nenhuma responde | incluído acima |
| Suíte permanente de isolamento (com esta migration) | 10/10 |
| Regressão de banco completa | 1.452 aprovados, 20 pulados, nenhuma falha (em duas metades: 698 + 754; na segunda, 5 testes antigos precisaram conhecer esta etapa e foram ajustados e repetidos por arquivo, sem mudança de SQL) |
| Unitários do frontend | 131/131 |
| `web/tests/e2e/acesso_convite.spec.mjs` (telas: convite, link, senha, primeiro acesso, sem convite, vencido, recuperação, suspensão, auditoria) | 6/6 |
| Suíte e2e completa | 298/298 |

Nenhum e-mail é enviado nos testes: o link do e-mail é simulado no formato do Supabase Auth.

## 12. Decisões e pendências do titular

1. **Envio do convite:** hoje em dois passos (registrar no aplicativo; enviar pelo painel do Supabase). Um envio de um passo só
   exige uma função no servidor com credencial de serviço; fica como evolução, com análise própria.
2. Conferir os cinco itens do painel do Supabase (seção 7).
3. Texto dos e-mails de convite e de recuperação.
4. Logins antigos do Supabase sem perfil continuam sem acesso; reativar algum deles exige convite.

## 13. Roteiro de entrada de um novo usuário (depois da publicação)

**Administrador**

1. Menu → Administração → Convites: informar o e-mail e a validade; **Registrar convite**.
2. Painel do Supabase → Authentication → Users → **Invite user**, para o mesmo e-mail.
3. Acompanhar na lista: Pendente → Usado. Se vencer: **Registrar reenvio** e enviar o convite de novo pelo painel.
4. Para encerrar o acesso de alguém: aba Usuários → **Suspender** (com motivo). Os dados ficam guardados; **Reativar** devolve o
   acesso. Para encerrar também as sessões do Supabase Auth, usar o painel do Supabase (a conta suspensa já não recebe
   resposta do aplicativo, com ou sem sessão).

**Convidado**

1. Abrir o link do e-mail e definir a senha.
2. Dar nome ao primeiro perfil e ativar a conta.
3. Cadastrar as próprias contas bancárias e lançamentos. O aplicativo começa vazio, só com o catálogo padrão de categorias.
4. Outros perfis: Configurações. Esqueceu a senha: "Esqueci minha senha" na entrada.

## 14. Plano de publicação (não executado)

Depois das duas etapas anteriores publicadas: backup → migration `20270102090000` → conferências (titular ativo e
administrador; telas iguais) → push e deploy → conferência do painel do Supabase → primeiro convite só com os critérios do
FIN-MULTIUSUARIO-HOMOLOGACAO-01. Reversão: frontend ao deploy anterior; script de reversão da migration. **Nada disso é
executado sem autorização expressa do titular.**
