# FIN-PATRIMONIO-2 — escrita do módulo Patrimônio

Data: 26/10/2026. Situação: **implementado e testado localmente**. Sem commit, push, publicação ou migration aplicada.

Migration local: `supabase/migrations/20261126090000_financeiro_patrimonio_escrita.sql`.
Reversão: `supabase/reversao/20261126090000_remover_patrimonio_escrita.sql`.

## 1. Diagnóstico

| Item | O que existia |
|---|---|
| Flask (`routes/patrimonio.py`, `PatrimonioEmpresarialService`, `PatrimonioSugestaoService`) | **Caixinhas:** criar, editar (inclui reativar) e inativar; nunca apaga. **Transferências:** criar (saldo suficiente na origem) e excluir, desfazendo os saldos. **Bens** (só perfil Empresa): criar, editar, criar a partir de documento fiscal, vincular documento, sugestão a partir de documento, documentos vinculáveis, exportação Excel/PDF |
| O que o Flask **não** tem | Exclusão de bem; vínculo de bem com financiamento (o único financiamento de bem é o do veículo, em Mobilidade); fluxo próprio de aquisição ou alienação (a aquisição são os campos do bem, a alienação é o status "Baixado"); tabela de histórico patrimonial (o histórico são as transferências e os vínculos de documento, ativos e inativos) |
| Novo aplicativo | Tela original já migrada, **só consulta** (`20261112090000`, FIN-FIDELIDADE-PATRIMONIO-1). As escritas respondiam "continua no sistema atual" |
| Escritor único | O Flask não consultava o escritor em Patrimônio |

## 2. Funcionalidades concluídas

**Todas as escritas exigem o escritor do perfil** (`exigir_escrita_novo`, do FIN-ESCRITOR-UNICO-FINAL-1):
- perfil ainda no Flask: recusa `SISTEMA_FLASK`, nada gravado;
- quem só lê ou não tem vínculo: 42501;
- **no Flask:** guarda no blueprint de Patrimônio. Perfil do novo aplicativo recebe 409 `SISTEMA_NOVO`, nada gravado. Consultas e exportações continuam.

### 2.1 Caixinhas
- **Criar:** o saldo atual nasce igual ao saldo inicial.
- **Editar:** nome (único no perfil), tipo, meta, cor, observações e ativo. Reativar é este caminho.
- **Inativar.** Caixinha não é apagada: ela sustenta transferências e fontes de receita antigas (`conta_origem_id`).
- **Saldo:** só muda pelas transferências, como no Flask.

### 2.2 Transferências
- **Criar:**
  - mensagens do Flask para contas iguais, valor zero, data ausente ou inválida e saldo insuficiente;
  - contas do perfil e ativas;
  - as duas contas são travadas em ordem de id, então transferências simultâneas não deixam saldo negativo (testado).
- **Excluir:** desfaz os saldos.
- **Repetição:** a chave impede duplicar.

### 2.3 Bens da Empresa
- **Criar e editar:**
  - campos normalizados como o Flask: textos cortados, valor com meio para cima, data e inteiro inválidos viram vazio, opções inválidas voltam ao padrão, imagem só entre as do sistema;
  - depreciação mensal recalculada.
- **Atualização de valores e aquisição:** pelos campos valor, data, fornecedor, vida útil e documento.
- **Alienação:** status "Baixado", como no Flask. O bem fica com o histórico.
- **Vincular documento fiscal:**
  - um documento serve a um único bem;
  - o vínculo anterior do bem fica **inativo**, nunca é apagado;
  - os campos vazios do bem vêm do documento (fornecedor, data, valor, número).
- **Criar a partir de documento:** os campos vazios vêm do documento, como no Flask.
- **Excluir (novo, pedido pelo contrato):**
  - só sem nenhum vínculo de documento, nem inativo;
  - com documento, a recusa (`COM_DOCUMENTO`) orienta a baixar o bem;
  - a tela original não tem botão: a rota existe no adaptador.
- **Documentos vinculáveis:** documentos do perfil Empresa sem vínculo ativo, com a busca do Flask. Antes, a lista vinha vazia.
- **Sugestão a partir de documento:**
  - o banco devolve os dados do documento (`patrimonio_documento_sugestao_tela`);
  - a heurística do Flask roda no navegador (`web/src/js/patrimonio-sugestao.js`): mesmas regras, ordem dos avisos e formato.

### 2.4 Tela
- O aviso da fase foi atualizado.
- A tela original não mudou.

## 3. Testes

| Conjunto | Resultado |
|---|---|
| `tests/test_supabase_patrimonio_escrita.py` (novo) | **11 passaram** |
| `tests/test_supabase_patrimonio_leitura.py` | 5 passaram |
| E2E `patrimonio_tela.spec.mjs` | 2 passaram |
| E2E completo | **93 passaram** |
| Unitários do `web/` | 30 passaram |
| Regressão Python completa | ver §6 |

O que o teste novo cobre:
- **Fidelidade:**
  - a mesma sequência de operações feita pelo **próprio Flask** numa cópia do banco e pelas funções novas noutra cópia idêntica;
  - a sequência inclui caixinhas, edição, inativação e reativação, transferências e exclusão de uma, 4 bens com entradas inválidas, edição, dois vínculos (troca de documento), bem a partir de documento e vínculo que preenche o valor;
  - resultado: as tabelas `conta_patrimonio`, `transferencia`, `bem_patrimonial` e `ir_comprovante_vinculo` são **iguais linha a linha**, fora a hora;
  - as leituras da tela (bens, resumo, caixinhas, transferências, documentos vinculáveis) também são iguais.
- **Documentos vinculáveis:** iguais ao `GET` do Flask, com e sem busca.
- **Sugestão:** a do navegador é igual à do Flask nos 6 documentos fictícios (com e sem texto, com OCR, sem valor, já vinculado).
- **Validações:** as de transferência e caixinha; nada muda quando recusa.
- **Repetição** sem duplicar; exclusão que deixaria o destino negativo recusada.
- **Concorrência:** duas transferências simultâneas que juntas passam do saldo; só uma grava.
- **Bens:**
  - só no perfil Empresa; nome obrigatório;
  - documento de outro perfil ou já vinculado é recusado;
  - exclusão só sem documento;
  - histórico de vínculos preservado.
- **Escritor e permissões:** escritor único nos dois sentidos, sem gravar; outro titular e outro perfil; privilégios das funções e da tabela.
- **Reversão:** remove as funções e preserva os dados.

## 4. Pendências

| Pendência | Encaminhamento |
|---|---|
| Exportação Excel e PDF de bens | FIN-RELATORIOS-CONFIG-1 |
| Botão de exclusão de bem na tela | A tela original não tem. A função e a rota estão prontas; decisão do titular |
| Vínculo de bem com financiamento | Não existe no Flask. Seria recurso novo, não migração |
| Histórico patrimonial (valores ao longo do tempo) | Não existe no Flask. Hoje o histórico são as transferências e os vínculos de documento |
| Exclusão de transferência é exclusão física (como no Flask) | Ela desfaz os saldos e é recusada se deixar o destino negativo. Um estorno com registro seria mudança de regra: decisão do titular |
| Abrir o arquivo do documento fiscal | Segue o caminho de Documentos (FIN-DOCUMENTOS-2) |
| Aplicar a `20261126` no Supabase de teste | Autorização. Depende da `20261124` (escritor único) e da `20261112` |

## 5. Correções classificadas (divergências intencionais)

1. **Valores em numeric.** O Flask somava saldos em float. Nos testes, os resultados são iguais.
2. **Valores monetários:** saldo inicial, meta e valor de transferência com 2 casas e sem negativo. O Flask aceitava qualquer número.
3. **Cor** só no formato `#RRGGBB`.
4. **Exclusão de transferência** recusada se a conta de destino já não tiver o valor. O Flask deixava o saldo negativo.
5. **Exclusão de bem** (o Flask não tem) só sem documento vinculado.
6. **Transferências simultâneas** travam as contas. O Flask não travava; duas transferências ao mesmo tempo podiam passar do saldo.
7. **Documento de outro perfil:** a mensagem é sempre "não encontrado", sem revelar que existe.

## 6. Regressão

Regressão completa ao fim (com as migrations `20261125` e `20261126` no cluster):
- **Python, pasta `tests/` inteira:** 1942 aprovados, 20 pulados, 5 falhas. As 5 são as preexistentes do P7, sem relação com esta entrega: `test_receitas_ux`, `test_categorias_sistemicas_mobilidade`, `test_ocr_tools` (2) e `test_veiculos_mobilidade_2b`. A contagem veio das marcas de progresso, porque o resumo final do pytest não foi gravado no arquivo.
- **E2E completo:** 93 aprovados.
- **Unitários do `web/`:** 30 aprovados.

## 7. Riscos

- **Exclusão de transferência é física,** como no Flask. Com o perfil no novo aplicativo, quem gere o perfil desfaz uma transferência antiga, e o registro some. Os saldos voltam.
- **Bens só em perfil do tipo Empresa.** A Empresa real continua no Flask até a transferência. Os testes de bens usam a Empresa fictícia atribuída ao novo aplicativo.

## 8. Arquivos

- **Migration e reversão:** `supabase/migrations/20261126090000_financeiro_patrimonio_escrita.sql`, `supabase/reversao/20261126090000_remover_patrimonio_escrita.sql`.
- **Flask:** `backend/routes/patrimonio.py` (guarda).
- **Web:**
  - `web/src/js/patrimonio-adaptador.js`;
  - `web/src/js/patrimonio-sugestao.js` (novo);
  - `web/src/paginas/patrimonio.html` (aviso).
- **Testes:**
  - `tests/test_supabase_patrimonio_escrita.py` (novo);
  - `web/tests/e2e/patrimonio_tela.spec.mjs`;
  - `web/tests/unit/build.test.mjs`: linhas deste MVP, arquivo compartilhado.
- **Docs:** `docs/FIN_PATRIMONIO_2.md`; `docs/ROADMAP.md` (uma linha).

## 9. Aplicação no Supabase de teste (27/10/2026)

**Commit:** `a3d8a3b` (só este MVP, sem push). Na árvore exata do commit:
- 30 unitários e 93 E2E passaram;
- Python, pasta `tests/` inteira: 1943 aprovados, 18 pulados, 5 falhas, as mesmas preexistentes de antes deste MVP (§6).

**Inspeção antes de aplicar** (só leitura, todas aprovadas):
- a migration não substitui nenhuma função existente: só cria;
- as 32 funções novas e a tabela `operacao_patrimonio` não existiam no remoto;
- a reversão remove exatamente as funções criadas e a tabela de controle, sem comando de dados;
- as 6 funções e as 8 tabelas de que a migration depende existem;
- nenhum comando de dados, `drop` ou alteração de tabela existente;
- nenhum perfil do remoto tinha caixinha, transferência ou bem.

**Aplicação:**
- só a `20261126090000` (a última local);
- as 69 tabelas existentes ficaram com o conteúdo idêntico (211 linhas); +1 tabela vazia; +32 funções; nenhuma alterada nem removida.

**Validação real** (perfil temporário criado pelo aplicativo; 17 verificações: **15 aprovadas automaticamente**, 2 conferidas no banco):
- **Caixinhas:** criar (o reenvio pela mesma chave devolve a mesma caixinha com `repetida: true`, sem duplicar), editar meta, cor e observações, nome repetido recusado, inativar e reativar.
- **Transferências:** A→B 300 deixa 4700 / 1100 (reenvio não duplica); saldo insuficiente recusado sem gravar; exclusão que deixaria o destino negativo recusada (`SALDO_DESTINO`); excluir desfaz os saldos (5000 / 800 / 0).
- **Bens:** no perfil Pessoal, recusados (`SO_EMPRESA`). Com o perfil passado a Empresa pelo próprio aplicativo e 3 documentos fiscais fictícios:
  - bem com documento: `COM_LASTRO`, valor 7500,56 e depreciação 208,35 (a regra do Flask, meio para cima);
  - documento já vinculado a outro bem: recusado;
  - bem a partir de documento; troca de documento desativa o vínculo anterior, que fica no histórico;
  - editar; com documento não exclui (`COM_DOCUMENTO`); sem documento exclui;
  - documentos vinculáveis e dados para a sugestão.
- **Perfil passado ao Flask:** as 8 escritas (caixinha, transferência e bem) recusadas (`SISTEMA_FLASK`), e nenhuma tabela do perfil mudou.
- **Quem só lê:** 403 nas escritas; lê as caixinhas.
- **Telas:** as 14 da árvore commitada, com o `dist` e a CSP reais, no perfil temporário (Empresa: a tela de Patrimônio é a de bens, como no Flask): sem erro de console nem chamada ao Flask; os bens gravados aparecem.

As 2 verificações conferidas no banco compararam a resposta do reenvio com a primeira por igualdade exata. O reenvio devolve o mesmo id mais `repetida: true` (comportamento previsto). No banco: uma operação registrada por chave, uma transferência e um bem por envio, sem duplicata.

**Limpeza por identidade** (simulação, depois confirmação): só o perfil temporário, criado pelo aplicativo, com os vínculos do teste e caixinhas, bens e documentos marcados. Banco idêntico ao retrato pós-aplicação (tabelas e funções).

**Inalterados:** produção; Pessoal e Empresa, que continuam no Flask; os perfis fictícios 31 e 39; `gastos.db`. **Pendentes no remoto:** nenhuma migration.
