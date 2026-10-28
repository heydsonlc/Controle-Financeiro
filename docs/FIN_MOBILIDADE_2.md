# FIN-MOBILIDADE-2 — Escrita de Veículos e Mobilidade no novo aplicativo

Data: 27/10/2026. É o item A3 do FIN-BLOCO-A-1 (contrato em `docs/contratos/fila_2026-10-26/FIN-MOBILIDADE-2.md`).

**Situação:** implementado e testado localmente, em bancos descartáveis.
- Migration `20261127090000_financeiro_mobilidade_escrita.sql`, local, **não aplicada no Supabase remoto**.
- Reversão em `supabase/reversao/20261127090000_remover_mobilidade_escrita.sql`.

## 1. O que o novo aplicativo passa a gravar

São 20 funções de tela, todas com o escritor único do perfil. Um perfil ainda no Flask recebe `SISTEMA_FLASK`, e nada é gravado. Elas são a contrapartida das 21 rotas de escrita do Flask.

| Flask | Função |
|---|---|
| `POST/PUT/DELETE /api/veiculos[/<id>]` | `criar_veiculo`, `editar_veiculo`, `excluir_veiculo` |
| `POST /api/veiculos/<id>/converter` | `converter_veiculo` |
| `POST /api/veiculos/<id>/projecoes/gerar` | `gerar_projecoes_veiculo` |
| `POST/DELETE /api/veiculos/<id>/regras-km[/<regra>]` | `criar_regra_km_veiculo`, `excluir_regra_km_veiculo` |
| `POST /api/veiculos/<id>/manutencoes-km/gerar` | `gerar_manutencao_km_veiculo` |
| `POST/DELETE /api/veiculos/<id>/financiamento` | `salvar_financiamento_veiculo`, `excluir_financiamento_veiculo` |
| `POST /api/veiculos/mobilidade/previsualizar` | `previa_mobilidade` (só lê) |
| `POST /api/veiculos/mobilidade/ativar` | `ativar_mobilidade` |
| `POST/PUT /api/veiculos/mobilidade/assinaturas[/<id>]` | `criar_assinatura_mobilidade`, `editar_assinatura_mobilidade` |
| `POST/PUT/DELETE /api/mobilidade-app[/<id>]` | `criar_caminho_app`, `editar_caminho_app`, `excluir_caminho_app` |
| `POST /api/despesas-previstas/<id>/confirmar \| adiar \| ignorar` | `confirmar_despesa_prevista`, `adiar_despesa_prevista`, `ignorar_despesa_prevista` |

**Regras mantidas do Flask:**
- **Projeção não vira lançamento sozinha.**
  - Só `PREVISTA` é substituída.
  - Competências em que o usuário já agiu (`CONFIRMADA`, `ADIADA`, `IGNORADA`) não são recriadas.
- **Confirmar:**
  - com meio de pagamento, cria a despesa (`item_despesa` e `conta`) ou o lançamento no cartão, pelo motor de compras do novo aplicativo;
  - sem meio de pagamento, só muda o status;
  - repetir a confirmação é recusado, então nunca duplica.
- **Adiar com ajuste de ciclo:** associa a prevista adiada ao ciclo de manutenção e gera só a próxima ocorrência.
- **Combustível confirmado:** soma o km estimado do veículo.
- **Ativar modalidade:**
  - inativa a anterior e as recorrências automáticas dela;
  - cria ou atualiza a recorrência mensal, quando há meio de pagamento;
  - suprime as previstas redundantes do caminho de app;
  - grava o cenário ativo.

**Cenário ativo por perfil:**
- Fica no banco, em `public.mobilidade_cenario_ativo`, que já tem `perfil_financeiro_id`. Não precisou de tabela nova.
- A tela atual do Flask já lia a modalidade ativa desse lugar.
- O arquivo global `mobilidade_cenario_ativo.json` (`/api/veiculos/cenario-ativo`) não é usado pela tela e **não foi reproduzido**.

**Tabela nova:** só `financeiro.operacao_mobilidade`, vazia, para a idempotência dos cadastros (reenvio não duplica). Nenhum dado existente é alterado.

## 2. Diferenças em relação ao Flask (correções)

1. **Categorias sistêmicas `MOB_*`:**
   - O novo aplicativo só as procura pelo código e nunca as cria nem altera, porque o catálogo global é do Flask.
   - Se faltar uma, a operação é recusada sem gravar (`CATEGORIA_SISTEMICA_AUSENTE`).
   - O Flask criava ou regravava categorias até em leituras, como a prévia.
2. **D-MOB1 corrigido:**
   - Salvar o financiamento do veículo funciona; no Flask, falhava sempre com 500.
   - As previstas de parcela e IOF levam o id do financiamento.
3. **Exclusão segura** de veículo e de caminho de app:
   - é recusada, sem gravar, quando há previstas confirmadas ou adiadas (histórico), quando é a modalidade ativa, ou, no caso do veículo, quando há financiamento, regras ou ciclos;
   - o Flask apagava previstas já confirmadas, e com vínculos respondia 500.
4. **Regra por km usada por ciclo** não é removida (no Flask, 500).
5. **Caminho de app inexistente** não é "editado" (o Flask criava previstas para qualquer id).
6. **Cartão informado e veículo da regra** têm de ser do perfil (o Flask só conferia a chave estrangeira).
7. **Erros de validação:** as mesmas mensagens do Flask, com código 400; não encontrado dá 404.

**Mantido por decisão:** o financiamento do veículo continua **projetivo**, só com despesas previstas.
- O contrato pedia "integrar ao motor financeiro migrado". Porém o motor (1123) cria contrato, parcelas e despesas **reais**, e o Flask diz expressamente que esta simulação "não cria lançamentos reais".
- Ligar um ao outro mudaria a regra financeira, então ficou como **decisão do titular** (§6).

## 3. Escritor único no Flask

- Os blueprints `veiculos`, `mobilidade_app` e `despesas_previstas` passam a ter a guarda por blueprint (`registrar_guarda_escritor_unico`): perfil no novo aplicativo recebe 409 `SISTEMA_NOVO`, e nada é gravado.
- Em `despesas_previstas`, a guarda substitui a do FIN-ESCRITOR-UNICO-GUARDAS-1 (G2), que só cobria o confirmar com meio de pagamento. Agora o novo aplicativo também grava despesas previstas, e confirmar, adiar e ignorar ficam todos guardados.

## 4. Testes (bancos descartáveis, dados fictícios)

**`tests/test_supabase_mobilidade_escrita.py` (11 testes):**
- **Mesmas linhas que o Flask:** a mesma sequência roda no Flask e nas funções novas, em cópias idênticas, e 11 tabelas são comparadas linha a linha, com o metadata comparado como JSON. A sequência:
  - veículos, edição, conversão e projeções;
  - regra e manutenção por km;
  - assinatura e caminho de app;
  - dois salvamentos do financiamento;
  - ativação das três modalidades;
  - confirmar, adiar com ciclo e ignorar previstas.

  O roteiro do Flask contorna o D-MOB1 só dentro do subprocesso de teste, para que a fórmula seja comparada.
- **Respostas iguais:** prévias, confirmar, adiar (com o ciclo) e ignorar.
- **Escritor único nos dois sentidos e isolamento:** outro titular recebe 42501, id de outro perfil volta "não encontrado", perfil no Flask é recusado, e as rotas do Flask respondem 409 sem gravar.
- **Categorias:** ausentes recusam sem gravar; quando existem, o catálogo não muda.
- **Exclusões seguras:** veículo e caminho de app.
- **Idempotência:** confirmação repetida recusada e projeção que não ressuscita competência confirmada.
- **Ativações simultâneas:** deixam um único cenário ativo.
- **Confirmação no cartão:** cria um lançamento.
- **Privilégios e reversão:** a reversão remove as funções e preserva os dados, e a reaplicação funciona.

**Também alterados:**
- `tests/test_supabase_integracao_1123_1126.py`: o I7 reverte e reaplica também a `20261127`. O I3 percorre as funções novas e as rotas agora guardadas.
- `tests/test_supabase_escritor_unico_guardas.py`: a confirmação sem meio de pagamento passa a ser recusada (409).
- **Falhas antigas de Mobilidade dependentes da data, corrigidas no teste** (a regra não foi alterada):
  - `test_categorias_sistemicas_mobilidade` (`KeyError: 'IPVA'`): a janela de 2 meses a partir de hoje só incluía junho em maio ou junho, e o teste passa a usar o mês corrente;
  - `test_veiculos_mobilidade_2b`: a prevista "futura" era 01/08/2026, data que já passou, e passa a ficar dois meses à frente.

**Web:**
- `web/src/js/mobilidade-adaptador.js` grava pelas funções novas.
- `build.test.mjs` libera cada RPC só nesse adaptador.
- O E2E `mobilidade_tela.spec.mjs` cobre, pela ponte da tela: cadastro, projeções, ativação com confirmação obrigatória e confirmação de prevista, uma vez só.
- `tests/supabase_local.py` semeia as categorias `MOB_*` no E2E.

## 5. Aplicação no remoto (não feita)

- Requer, nesta ordem: as categorias `MOB_*` existentes no banco (criadas pela migration Alembic `a9b0c1d2e3f4` do Flask) e a aplicação autorizada de `20261127090000`.
- **Ordem de reversão:** 1127 → 1126 → 1125 → 1124 → 1123 (`docs/FIN_INTEGRACAO_1123_1126_1.md` §3).

## 6. Pendências e decisões do titular

1. **Financiamento do veículo:** manter a simulação projetiva (atual) ou integrar ao motor de Financiamentos, gerando contrato real.
2. **Despesas previstas de Mobilidade:** o Flask não tem exclusão individual, e o novo aplicativo também não.
