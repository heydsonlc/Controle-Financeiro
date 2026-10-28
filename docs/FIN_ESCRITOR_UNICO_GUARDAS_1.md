# FIN-ESCRITOR-UNICO-GUARDAS-1 — Guarda de escritor nas três escritas do Flask que ficavam sem ela

Data: 27/10/2026. Corrige o risco 1 do FIN-INTEGRACAO-1123-1126-1 (`docs/FIN_INTEGRACAO_1123_1126_1.md` §5). Antes desta correção, essas três rotas bloqueavam a transferência de perfis reais.

Sem migration, sem mudança de regra de negócio, sem push e sem publicação.

## 1. O que mudou

| | Rota do Flask | Antes, com o perfil no novo aplicativo | Agora |
|---|---|---|---|
| G1 | `POST /api/ir/comprovantes/<id>/criar-financeiro` | Criava `item_despesa` e `conta` (ou lançamento de cartão) e o vínculo | **409 `SISTEMA_NOVO`**, nada gravado |
| G2 | `POST /api/despesas-previstas/<id>/confirmar` com `meio_pagamento` | Criava `item_despesa` e `conta` (ou lançamento de cartão) | **409 `SISTEMA_NOVO`**, nada gravado |
| G3 | `POST`/`PUT`/`DELETE` `/api/ir/comprovantes/<id>/vinculos[/<vinculo_id>]` de vínculo `PATRIMONIO` | Criava, editava ou inativava vínculos que o novo aplicativo também grava (FIN-PATRIMONIO-2) | **409 `SISTEMA_NOVO`**, nada gravado |

Com o perfil no Flask, as três continuam iguais: mesmas respostas e mesmos dados gravados.

### Um só mecanismo

**`recusa_escritor_unico(perfil, modulo, contexto)`** (`backend/services/gerador_recorrencia_service.py`):
- é a mesma verificação de `flask_pode_gerar`, com a mesma trava compartilhada do perfil;
- devolve a mesma resposta 409 e desfaz a transação.

**`registrar_guarda_escritor_unico`**, a guarda por blueprint, passou a usar essa função, sem mudança de comportamento.

As rotas G1–G3 chamam a guarda **antes de qualquer escrita e na mesma transação**:
- a trava do perfil fica até o commit;
- uma troca de escritor em andamento faz a escrita esperar e, depois, ser recusada.

### Alcance

**G2:** a recusa vale quando a confirmação cria despesa ou lançamento (`meio_pagamento` informado). A confirmação sem meio de pagamento só troca o status da previsão, que é dado de Mobilidade, não escrito pelo novo aplicativo. Ela continua como antes e fica para o FIN-MOBILIDADE-2.

**G3:**
- vale só para vínculo `PATRIMONIO`, o único tipo que o novo aplicativo também grava;
- `DocumentoFiscalService.eh_vinculo_patrimonial` diz se a escrita é desse tipo;
- inclui a edição (`PUT`), porque ela altera as mesmas linhas;
- os vínculos de outros tipos ficam com Documentos (FIN-DOCUMENTOS-2).

### Arquivos

- `backend/services/gerador_recorrencia_service.py`: `recusa_escritor_unico`, usada também pela guarda por blueprint.
- `backend/routes/ir.py`: G1 e G3.
- `backend/routes/despesas_previstas.py`: G2.
- `backend/services/documento_fiscal_service.py`: `eh_vinculo_patrimonial`, que só lê.
- `tests/test_supabase_integracao_1123_1126.py`: I8 sem os três `xfail(strict=True)`; agora é teste de regressão.
- `tests/test_supabase_escritor_unico_guardas.py` (novo).

## 2. Testes

Todos em cluster PostgreSQL descartável, com dados fictícios.

**I8 (6 testes):**
- no perfil do novo aplicativo, as três rotas respondem 409 e **nenhuma tabela muda**;
- no perfil do Flask, as mesmas requisições gravam normalmente.

**`test_supabase_escritor_unico_guardas.py` (6 testes):**
- **Vínculo patrimonial gravado pelo novo aplicativo:** o Flask não edita, não remove nem liga o documento a outro bem (409). Vínculo, bem e documento ficam com o mesmo md5.
- **Perfil do Flask:** o Flask cria, edita e remove o vínculo `PATRIMONIO`. A remoção inativa o vínculo e mantém o histórico; bem e documento não mudam.
- **Fora da guarda, como antes:** confirmar sem meio de pagamento e vínculo que não é `PATRIMONIO` não criam despesa.
- **Troca de escritor em andamento (G1, G2, G3):** o Flask espera na trava do perfil (lock consultivo não concedido) e, depois do commit da troca, recusa com 409. Só a atribuição e o histórico de troca mudam.

**Seleção de impacto (nível 2):**
- O seletor escolheu 102 dos 137 arquivos de teste, porque o serviço da guarda é central. Nenhum E2E nem unitário web foi selecionado, já que nada em `web/` mudou.
- Resultado: **1541 aprovados e 5 falhas**, em 28,4 min. As 5 são as preexistentes do P7, as mesmas da homologação (`test_ocr_tools` ×2, `test_categorias_sistemicas_mobilidade`, `test_receitas_ux`, `test_veiculos_mobilidade_2b`). Não houve regressão nova.

## 3. Verificações sem mudança

**Mesmo documento em dois bens:**
- **Novo aplicativo** (`vincular_documento_ao_bem`) e **rota de Patrimônio do Flask:** recusam ("Documento fiscal ja esta vinculado a um bem patrimonial").
- **Rota genérica de IR do Flask:** aceita, no perfil do Flask, um segundo vínculo `PATRIMONIO` ativo para o mesmo documento, e o status documental do outro bem não é atualizado. É comportamento antigo, numa regra de negócio que este contrato não muda. Com o perfil no novo aplicativo, essa rota agora é recusada (G3).

**Metadados de perfil gravados pelo Flask**, ambos exceções legítimas, só documentadas:
- **"Tornar padrão":** é preferência do usuário, fora da guarda nos dois aplicativos (FIN-ESCRITOR-UNICO-FINAL-1 §3). Regrava `padrao` e `updated_at`.
- **`obter_ou_criar_perfis_iniciais`:** criação idempotente dos perfis iniciais. Preenche tipo, avatar e cor só quando estão vazios; na base real eles já existem. Não toca dado financeiro.

## 4. Pendências

1. **Mesmo documento em dois bens pela rota genérica de IR do Flask, no perfil do Flask:** decidir se a regra do Patrimônio passa a valer também ali. A decisão cabe no FIN-DOCUMENTOS-2.
2. **Demais escritas de Documentos/IR e de Mobilidade no Flask** (`ir`, `ocr_tools`, `veiculos`, `mobilidade_app`, `despesas_previstas` adiar e ignorar): seguem para FIN-DOCUMENTOS-2 e FIN-MOBILIDADE-2. Hoje o novo aplicativo não grava nessas tabelas.
