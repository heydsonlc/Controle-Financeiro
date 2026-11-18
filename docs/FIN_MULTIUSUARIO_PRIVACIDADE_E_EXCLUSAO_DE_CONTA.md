# Privacidade e exclusão de conta — procedimento operacional (proposta)

**Situação:** proposta de procedimento, preparada no FIN-MULTIUSUARIO-AJUSTES-FINAIS-01 em 18/11/2026. **Nada disto está
implementado como função do aplicativo**: não há exclusão automática. A política de retenção e este procedimento precisam ser
**aprovados pelo titular antes da abertura do aplicativo a terceiros**.

Este documento não é parecer jurídico. As referências à LGPD (Lei 13.709/2018) servem para organizar o procedimento; pontos
marcados como **decisão** devem ser confirmados pelo titular, se preciso com orientação jurídica.

## 1. Papéis e alcance

- **Operador do aplicativo (controlador dos dados):** o titular do projeto, que mantém o banco, os backups e a administração.
- **Usuário:** quem tem conta no aplicativo; é o titular dos dados que cadastra.
- **O que o aplicativo guarda de cada usuário:** e-mail e credencial (no Supabase Auth; a senha não é legível por ninguém);
  situação da conta e convite; perfis financeiros; contas bancárias, lançamentos, despesas, receitas, cartões, faturas,
  financiamentos, consórcios, patrimônio, mobilidade; documentos enviados (arquivos guardados no banco, que podem conter dados
  de terceiros, como notas e recibos); categorias particulares e ajustes de palavras-chave; registros de auditoria.
- **Decisão — alcance da LGPD:** a lei não se aplica ao tratamento feito por pessoa natural para fins exclusivamente
  particulares e não econômicos (art. 4º, I). Um aplicativo aberto a outras pessoas pode ou não se enquadrar nessa exceção,
  conforme a forma de oferta. Recomendação: adotar o procedimento abaixo de qualquer modo.

## 2. Três medidas diferentes

| Medida | O que faz | Reversível | Quando usar |
|---|---|:--:|---|
| **Suspensão de acesso** | a conta deixa de receber qualquer resposta do aplicativo; **nenhum dado é apagado** | sim | pedido de pausa, suspeita de uso indevido, enquanto um pedido de exclusão é analisado |
| **Anonimização** | os registros ficam, sem vínculo com a pessoa (e-mail, nomes, descrições e documentos removidos) | não | raramente útil aqui: os dados financeiros de um usuário não servem a mais ninguém |
| **Exclusão definitiva** | apaga os perfis do usuário e tudo o que pertence a eles, as personalizações e o login | não | pedido do usuário, depois da conferência de identidade e das exceções |

A suspensão já existe (tela de Administração). Anonimização e exclusão **não** existem como função: são executadas pelo
operador, pelo roteiro da seção 6.

## 3. Como o usuário pede

1. Canal único e registrado: e-mail enviado **do endereço da própria conta** para o endereço de contato do operador
   (**decisão:** definir e publicar esse endereço na Ajuda).
2. O pedido diz o que se quer: cópia dos dados, correção, suspensão ou exclusão.
3. O operador confirma o recebimento. **Prazos — decisão:** a LGPD prevê resposta imediata em formato simplificado ou
   declaração completa em até 15 dias para confirmação e acesso (art. 19); recomendação: responder todo pedido em até 15 dias.

## 4. Conferência de identidade

- O pedido vale quando chega **do e-mail da conta** e é confirmado por uma resposta enviada a esse mesmo e-mail (ida e volta).
- Pedido vindo de outro endereço, por telefone ou por terceiro **não é executado**; orienta-se a pessoa a pedir pelo e-mail da
  conta. Se ela perdeu o acesso ao e-mail, a recuperação é dela com o provedor; sem isso, só suspensão preventiva.
- Nunca pedir senha. Nunca enviar dados para endereço diferente do da conta.
- O administrador **não entra** na conta do usuário nem lê os dados dele para "conferir": a identificação é pelo e-mail.

## 5. O que é de quem (para não apagar dado de outro titular)

Pertence ao usuário, e só a ele:

- os **perfis financeiros de que ele é dono** (cada perfil tem dono explícito e fixo) e **todo registro ligado a esses perfis**;
- as **categorias particulares** e os **ajustes de palavras-chave** dele;
- as preferências, a conta da plataforma, o vínculo de acesso e o login no Supabase Auth.

Não pertence a ele e **não é tocado**: o catálogo padrão de categorias e palavras-chave, o modelo de categorias de cartão, os
índices de referência, e qualquer registro de perfil de outro dono.

Antes de qualquer exclusão, o roteiro produz um **inventário por tabela** (quantidades) restrito aos perfis cujo dono é o
usuário, e confere que nenhum perfil de outro dono entra na lista. Havendo perfil compartilhado no futuro (hoje não há), o
perfil é do dono; o acesso de outra pessoa a ele é apenas retirado.

## 6. Roteiro de exclusão (operador)

1. **Registrar** o pedido (seção 8) e **suspender** a conta.
2. **Conferir a identidade** (seção 4).
3. **Oferecer a cópia dos dados** antes de apagar (relatórios e arquivos que o próprio aplicativo exporta).
4. **Avaliar exceções de conservação** (seção 7). Se alguma se aplicar, informar o usuário o que fica e por quê.
5. **Backup** do banco antes da intervenção (rotina existente, tipo manutenção).
6. **Prévia**: inventário por tabela dos registros do usuário, com impressão; conferência de que só há perfis dele.
7. **Execução**, numa única transação: registros dos perfis dele; os perfis; personalizações; preferências; conta da
   plataforma; por último o login no Supabase Auth (pelo painel).
8. **Conferência**: o inventário do usuário zerado; contagens e saldos dos **demais** usuários idênticos aos de antes.
9. **Responder** ao usuário e **encerrar** o registro.

**Pendência:** o passo 6–8 exige um roteiro com prévia, impressão, confirmação e teste em banco descartável, no mesmo padrão
dos roteiros `regularizar_itens_sem_perfil.py` e `cadastros_padrao.py`. Ele **não foi escrito** (este contrato pede só o
procedimento) e deve ser desenvolvido e testado **antes do primeiro convite a terceiros**. Até lá, o que existe é a suspensão.

## 7. Conservação mesmo com pedido de exclusão

A LGPD autoriza conservar dados, entre outros casos, para cumprimento de obrigação legal ou regulatória pelo controlador
(art. 16, I). Nem todo pedido exige eliminação imediata e irrestrita.

| Dado | Tratamento proposto |
|---|---|
| Dados financeiros e documentos cadastrados pelo usuário | apagados (são dele; o operador não tem obrigação de guardá-los) |
| Registro do próprio pedido e da execução | **conservado** (prova de atendimento), sem os dados financeiros |
| Auditoria de acesso (convite, ativação, suspensão) | conservada pelo prazo definido, com o identificador da conta; **decisão:** prazo (sugestão: 12 meses) |
| Obrigação legal específica do operador sobre algum dado | conservar só o necessário, pelo prazo da obrigação, e informar o usuário |

## 8. Registro do pedido e da execução

Um registro por pedido, fora do repositório, com: data e canal; conta (e-mail e identificador); o que foi pedido; conferência
de identidade (data da ida e volta); decisão e fundamento; impressão do inventário; data da execução; backup anterior usado;
conferência final; resposta enviada. Sem dados financeiros do usuário.

## 9. Backups

- Os backups são do banco **inteiro**, cifrados, fora do repositório; contêm os dados de todos os usuários.
- A exclusão no banco **não apaga** o que já está em backups anteriores. Esses dados saem conforme a **retenção** (hoje
  recomendada: 8 semanais, 12 mensais, anual sem prazo, com exclusão manual pelo titular).
- **Decisão — retenção com terceiros:** com dados de outras pessoas, o backup anual "sem prazo" deixa de ser adequado.
  Sugestão: prazo máximo (por exemplo, 12 meses) para qualquer backup que contenha dados de terceiros, e informar esse prazo
  ao usuário na resposta ao pedido.
- Restauração de um backup anterior a uma exclusão **reintroduz** os dados apagados: depois de restaurar, repetir as
  exclusões registradas desde a data do backup (o registro da seção 8 é a lista).
- Não há restauração parcial por usuário: recuperar dados de uma pessoa exige restaurar o backup num banco descartável e
  extrair só os registros dela.

## 10. Incidentes

Acesso indevido, vazamento ou perda de dados de usuários: suspender o que for preciso, preservar os registros de auditoria,
avaliar o alcance pelo dono de cada perfil e comunicar os afetados. **Decisão:** a LGPD prevê comunicação à autoridade e aos
titulares em caso de incidente com risco ou dano relevante (art. 48); definir quem decide e em que prazo.

## 11. O que precisa ser aprovado antes da abertura a terceiros

1. Endereço de contato e prazo de resposta.
2. Prazo de conservação da auditoria de acesso e do registro de pedidos.
3. Prazo máximo de retenção dos backups com dados de terceiros.
4. Texto de aviso ao convidado (o que é guardado, por quem, como pedir cópia e exclusão).
5. Desenvolvimento e teste do roteiro de exclusão (seção 6).
