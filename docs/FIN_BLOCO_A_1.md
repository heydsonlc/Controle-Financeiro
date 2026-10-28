# Relatório A — FIN-BLOCO-A-1 (Integridade e Mobilidade)

Data: 27–28/10/2026. Contrato: `docs/contratos/fila_2026-10-27/FIN-BLOCO-A-1.md`.

**Situação: APROVADO COM RESSALVAS.** As ressalvas estão no §5.

## 1. Funcionalidades concluídas

- **A1, homologação 1123–1126:** encerrada e commitada (`91004af`). Ordem de reversão documentada: 1127 → 1126 → 1125 → 1124 → 1123.
- **A2, escritor único:** as três escritas do Flask sem guarda foram corrigidas (`0ed2ea6`, `docs/FIN_ESCRITOR_UNICO_GUARDAS_1.md`):
  - comprovante → despesa;
  - confirmar despesa prevista;
  - vínculos `PATRIMONIO` de documento.

  As três recusam com 409 sem gravar e usam o mesmo mecanismo e a mesma trava. O `xfail` saiu, e a concorrência com a troca de escritor está testada. Os metadados de perfil ("tornar padrão", preenchimento dos perfis iniciais) são exceções legítimas, apenas documentadas.
- **A3, FIN-MOBILIDADE-2:** escrita de Veículos/Mobilidade no novo aplicativo (`a9e704a`, `docs/FIN_MOBILIDADE_2.md`), com 20 funções e escritor único:
  - veículos;
  - projeções;
  - regras e manutenção por km;
  - financiamento projetivo do veículo, com o D-MOB1 corrigido;
  - prévia e ativação de modalidade, com o cenário ativo no banco, por perfil;
  - assinaturas;
  - transporte por app;
  - confirmar, adiar com ciclo e ignorar despesas previstas.

  Mesmas linhas que o Flask em 11 tabelas. As categorias `MOB_*` são só procuradas, nunca criadas, e a categoria recriada não perde vínculos nem duplica previstas: tudo é resolvido pelo código estável. Despesas já executadas (confirmadas) são preservadas.
- **Falhas antigas:** duas das cinco eram de Mobilidade e dependiam da data, não de defeito funcional, e foram corrigidas no teste:
  - `test_categorias_sistemicas_mobilidade` (IPVA);
  - `test_veiculos_mobilidade_2b`.
- **A4, integração:**
  - Mobilidade × Categorias: sistêmicas, catálogo inalterado.
  - × Despesas Previstas: confirmação cria a conta uma vez; projeção não ressuscita competência confirmada.
  - × Recorrências: a recorrência da modalidade entra no gerador, e sai ao trocar de modalidade.
  - × Escritor Único: nos dois sentidos.
  - × Contas Bancárias: não há vínculo direto no modelo. O pagamento acontece depois, pela despesa gerada.

## 2. Migrations criadas

- `20261127090000_financeiro_mobilidade_escrita.sql`, com reversão `supabase/reversao/20261127090000_remover_mobilidade_escrita.sql`.
  - **Só local**, testada em bancos descartáveis. **Não aplicada no Supabase remoto**, que segue com 37 aplicadas e esta pendente.
  - Uma tabela nova, vazia (`financeiro.operacao_mobilidade`, idempotência). Nenhum dado existente alterado.

## 3. Testes e regressões

- **Nível 3, no fechamento:** Python **2001 aprovados**, 3 falhas preexistentes e 1 teste desmarcado (o que lê o `.env.staging`); web unit **30/30**; E2E **93/93**.
  - As 3 falhas: `test_ocr_tools` ×2 (o Poppler está instalado na máquina) e `test_receitas_ux`, preexistente e não alterada. Nenhuma regressão nova.
- **Testes novos de Mobilidade:** 12 (11 no nível 3, mais o da recorrência no gerador, rodado depois e aprovado).
- **Integração 1123–1126:** I1–I8 aprovados. O I7 cobre a cadeia de reversão até a 1127.
- **Integridade:** `gastos.db` inalterado (md5 `bf7c7d3a…`); PostgreSQL local persistente idêntico (contadores e conteúdo); Supabase remoto sem alteração.

## 4. Commits locais (sem push)

| Commit | Conteúdo |
|---|---|
| `91004af` | Homologação FIN-INTEGRACAO-1123-1126-1 |
| `0ed2ea6` | FIN-ESCRITOR-UNICO-GUARDAS-1 |
| `a9e704a` | FIN-MOBILIDADE-2 |
| (este) | Documentação e encerramento do Bloco A, e os textos da fila de 27/10 |

## 5. Pendências e bloqueadores

**Nenhum bloqueador de integridade para o Bloco B.**

Decisões do titular:
1. **Financiamento do veículo:** hoje é simulação projetiva (só previstas), como no Flask. Integrá-lo ao motor de Financiamentos, como pedia o contrato original, mudaria a regra, porque passaria a gerar contrato e despesas reais.
2. **Mesmo documento em dois bens pela rota genérica de IR do Flask, no perfil do Flask:** comportamento antigo; a decisão fica para o FIN-DOCUMENTOS-2.

Trabalho futuro e autorizações:
- Aplicar a `20261127090000` no remoto, com autorização. Requer as categorias `MOB_*` no banco.
- 1 falha antiga ainda aberta além das de ambiente (`test_receitas_ux`), reavaliada no Bloco C (C5).
- 47 + 4 commits locais aguardando push.
