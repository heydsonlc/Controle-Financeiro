# FIN-RECORRENCIA-1 — Contrato (decisões definitivas)

> **Este contrato substitui a proposta do commit `10447e1`.** Aquela proposta recomendava
> reproduzir defeitos do Flask (deriva do dia, recriação de competências, fatura não criada
> nos meses curtos). As decisões abaixo, do SCRIPT-CONTRATO V5 (2026-10-21), são as
> definitivas. A implementação e os resultados estão em `docs/FIN_RECORRENCIA_1.md`.

## 1. Objetivo

O novo Controle Financeiro deve gerar contas recorrentes e faturas de forma **explícita, transacional e idempotente**, sem repetir os defeitos conhecidos do Flask. O Flask é a referência para os cálculos corretos, não para os defeitos.

**Autorização:** diagnóstico e implementação local controlada. Ficam proibidos:
- aplicar migrations remotas;
- publicar no Cloudflare;
- alterar dados reais.

## 2. Decisões aprovadas

| # | Decisão |
|---|---|
| D1 — Acionamento | A consulta do mês é sempre somente leitura. Havendo geração pendente, a tela mostra um aviso discreto e a ação **"Gerar contas"**, que só grava após confirmação do usuário. |
| D2 — Período | Gera até o mês selecionado + 1, preenchendo as lacunas. Antes de gravar, mostra a quantidade de competências e de registros. Um período extenso (lacunas anteriores ao mês ou mais de dois meses) é destacado na confirmação. |
| D3 — Tipos | Mensal e anual, tanto de despesas quanto de compras no cartão, além das faturas. Recorrências semanais ficam fora. |
| D4 — Inativação | Uma recorrência inativa não produz lançamentos novos. O histórico anterior não é apagado. |
| D5 — Vencimentos e dispensa | O dia contratual é preservado, sem deslocamento progressivo. Uma competência **dispensada** é registrada e não é recriada. |
| D6 — Meses curtos | Os dias 29, 30 e 31 só são ajustados na competência em que o dia não existe. Na competência seguinte, volta o dia contratual. Vale também para o vencimento das faturas. |
| D7 — Falhas | Cada item inválido é identificado e informado. Os válidos são gravados de forma atômica, com relatório verificável. Não há resultado parcial silencioso. |
| D8 — Autorização | Gera somente o titular ou quem tem **permissão explícita de gestão** do perfil. O acesso de leitura não implica escrita. |
| D9 — Débito automático | A conta é gerada pendente. Este MVP não faz pagamento, baixa nem movimento bancário. |

## 3. Regra crítica: compatibilidade com o Flask

- Não usar só a data de vencimento como identidade.
- A identidade é estável: **(recorrência, natureza, competência)**, respeitando as particularidades das faturas.

**Testes obrigatórios da compatibilidade:**

1. Repetir a geração não duplica.
2. Requisições concorrentes não duplicam.
3. Registros do Flask são reconhecidos.
4. A correção do vencimento não duplica registros antigos.
5. A dispensa permanece.
6. O Flask não recria o que foi dispensado ou corrigido.

**Se o item 6 exigir mudança significativa no Flask ou um escritor único:**
- interromper essa parte;
- apresentar a incompatibilidade;
- propor uma transição segura;
- não declarar equivalência.

**Resultado:** os itens 1 a 5 estão garantidos e testados. O item 6 **não é garantido sem escritor único**: o GET do Flask recria a competência dispensada e duplica as contas cujo vencimento foi corrigido. A transição proposta está em `docs/FIN_RECORRENCIA_1.md` §6.

## 4. Interface

A tela "Contas do mês" continua simples:
- mês e perfil selecionados;
- contas e faturas já existentes;
- aviso de geração pendente;
- ação "Gerar contas" e confirmação antes de gravar;
- resultado com a quantidade de registros criados, já existentes, dispensados ou rejeitados.

Sem dashboards, gráficos ou cards novos.

## 5. Testes obrigatórios

Os testes devem cobrir:
- recorrência mensal e anual;
- inativação;
- vencimento contratual no dia 31 em janeiro, fevereiro e março;
- fevereiro de ano bissexto;
- faturas de cartão;
- lacunas retroativas;
- competência dispensada;
- repetição e concorrência;
- perfil autorizado e não autorizado;
- compatibilidade com registros do Flask;
- rollback da transação;
- ausência de pagamento e de movimento bancário;
- preservação do histórico.

A comparação com o Flask classifica cada divergência como correção intencional ou regressão.

## 6. Git e travas

- Push de `dbff152` e `10447e1` autorizado após revisão de segurança (feito).
- O novo commit fica local; push só com nova autorização.
- Parar após a implementação, os testes e o relatório.
- Ficam proibidos:
  - aplicar migration no Supabase remoto;
  - alterar dados reais;
  - iniciar o FIN-DESPESAS-1;
  - publicar a aplicação.
