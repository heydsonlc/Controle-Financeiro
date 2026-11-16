# FIN-AUDITORIA-PUBLICACAO-MIGRACAO-01 — E. Plano de regularização

**Data de referência:** 15/11/2026. Este plano é uma **proposta para análise do titular**. Nada dele foi executado. Cada item precisa de contrato e autorização próprios.

## Leitura rápida

- **Não há nada "só por publicar".** Não existe código pronto fora da produção, nem migration pendente. O que falta é desenvolvimento novo, homologação pelo titular ou decisão.
- A ordem abaixo é: primeiro o risco aos dados, depois o que o Flask fazia e o aplicativo novo ainda não faz, e por fim as homologações e a arrumação.
- **Nenhuma pendência P0** foi encontrada: não há perda ou exposição de dados, dupla gravação nem falha de autorização.

## Itens, na ordem recomendada

| Id | Descrição | Pri. | Dependências | Impacto | Migration | Deploy | Risco | Critério de aceite |
|---|---|---|---|---|---|---|---|---|
| REG-01 | **Backup real da produção.** Conferir no painel do Supabase se o plano tem backup gerenciado e por quanto tempo; gerar um backup independente com `scripts/backup_banco.py exportar`; guardá-lo em local cifrado, fora do OneDrive; testar a restauração num banco vazio | **P1** | Decisão do titular sobre o local cifrado (pendente desde o `FIN_BLOCO_D_2`); ferramentas do PostgreSQL 17 | Elimina o único risco P1: hoje não há recuperação comprovada dos dados nem dos documentos | Não | Não | Baixo: só lê a produção; a restauração é feita em banco descartável | Manifesto com SHA-256 conferido; restauração homologada pelo "retrato" igual ao do manifesto; data e local registrados |
| REG-02 | **Rotina de backup.** Definir a frequência (por exemplo, semanal e antes de cada migration) e registrar cada execução | P1 | REG-01 | Mantém a recuperação comprovada ao longo do tempo | Não | Não | Baixo | Registro das execuções; último backup com menos de N dias |
| REG-03 | **Relatórios de Documentos Fiscais:** Excel e PDF de IR, Excel e PDF de saídas sem documento, gerados no navegador com os módulos do relatório de Patrimônio (`exportacao-xlsx.js`, `exportacao-pdf.js`) | P2 | — | Fecha 2 das 6 operações documentais não migradas; os botões já estão na tela | Provável função de leitura para os dados do relatório | Sim | Baixo: só leitura | Arquivos equivalentes aos do Flask com os mesmos dados; testes; botões deixam de responder "não disponível" |
| REG-04 | **ZIP dos documentos da Empresa**, gerado no navegador, com o índice | P2 | REG-03 (gerador de XLSX do índice) | Entrega ao contador | Possível função de leitura em lote | Sim | Médio: volume em memória no navegador; exige limite | ZIP com todos os arquivos do filtro e índice conferido; limite de tamanho tratado |
| REG-05 | **Documentos do financiamento e conferências da Caixa:** envio, abertura, exclusão e conferência, com os arquivos no banco como os demais documentos | P2 | Decisão sobre onde guardar (banco ou Storage) | Fecha as linhas 35 e 36 da matriz | **Sim** (escrita e leitura; hoje só existe a tabela legada) | Sim | Médio: escrita nova em módulo de contrato | Rotas deixam de responder 501; isolamento por perfil testado; `excluir_financiamento` continua protegendo contratos com documentos |
| REG-06 | **Demonstrativo anual e valores simulados** do financiamento (leitura) | P2 | — | Consulta para o Imposto de Renda e para conferência | Sim (funções de leitura) | Sim | Baixo | Mesmos números do Flask em contrato de teste |
| REG-07 | **Consolidação (fechamento) da fatura.** ~~Decidir se a consolidação manual volta.~~ **DISPENSADA por decisão do titular em 15/11/2026:** a fatura já chega consolidada pela administradora, na importação; nenhum mecanismo de fechamento será desenvolvido. Correção deste registro: o botão não chegava a ser desenhado no novo aplicativo; o que respondia "não disponível" era a rota, agora retirada (`docs/FIN_REG_07_FATURAS_SEM_CONSOLIDACAO.md`) | — | Decisão tomada | Funcionalidade dispensada, não é pendência de migração | — | — | — | — |
| REG-08 | **Leitura automática de documentos:** classificação no envio (palavra-chave → categoria), NFS-e de Goiânia e cupom fiscal sobre o texto já extraído pelo PDF.js **Situação (16/11/2026):** implementado no ramo local `reg-08-leitura-classificacao` junto com o OCR no navegador (REG-09); aguardando homologação; sem push, deploy ou migration em produção (`docs/FIN_REG_08_LEITURA_CLASSIFICACAO_DOCUMENTAL.md`). | P2 | — | Fecha as operações 19, 23 e 24 | Possível (se a classificação ficar no banco) | Sim | Médio: os parsers precisam de amostras reais anonimizadas | Mesmos campos extraídos pelo Flask nas amostras de teste |
| REG-09 | **OCR de imagens e PDFs digitalizados.** Não roda em hospedagem estática. Opções: OCR no navegador (biblioteca pesada, exige revisão da CSP) ou serviço externo. Alternativa: retirar o botão "Reprocessar OCR" e manter a revisão manual **Situação (16/11/2026):** OCR no navegador escolhido pelo titular (Tesseract.js 7.0.0 no próprio site, CSP com `'wasm-unsafe-eval'` só nas páginas de documentos); entregue no FIN-REG-08. | P2 | Decisão de arquitetura e de custo | Fecha a operação 25 | Não | Sim | Alto: dependência nova e privacidade dos documentos | Decisão registrada; o botão funciona ou é retirado |
| REG-10 | **Homologação pelo titular do que está publicado sem uso real:** vínculos de documentos e lastro, "Gerar financeiro", exclusão de documento, Patrimônio (caixinhas, bens, relatório), gestão de perfis, preferências, Recorrências mobile, troca de perfil mobile, ícone da aba e reinstalação no iPhone | P3 | — | Passa 20 itens de PUBLICADO NÃO HOMOLOGADO para CONCLUÍDO | Não | Não | Baixo; os testes em produção são do titular, com dados reais | Roteiro de homologação assinado por módulo |
| REG-11 | **Integridade e trilha dos documentos:** reconferir o SHA-256 ao abrir ou numa verificação periódica; guardar um registro mínimo da exclusão, que hoje apaga os eventos | P3 | — | Detecta corrupção; mantém histórico | Sim | Possível | Baixo | Teste que adultera o conteúdo e a função acusa; exclusão deixa registro |
| REG-12 | **Pequenas lacunas:** alertas do sino; editar recebimento e receber sem fonte; vincular linha da importação a uma recorrência; logo de categoria; importar e exportar configurações; página de Seguro habitacional; itens e orçamentos do cartão (conferir se a tela ainda chama) | P3 | Decisão caso a caso: implementar ou retirar da tela | Tira mensagens de "não disponível" | Algumas | Sim | Baixo | Cada item implementado ou retirado, com registro |
| REG-13 | **Limpeza estrutural do legado:** retirar as colunas `numero_cartao`, `codigo_seguranca` e `data_validade` de `config_agregador` (ou trocar por "final"); decidir o destino dos 58 itens de consórcio inativos sem perfil; avaliar a tabela `alembic_version` | P3 | REG-01 (backup antes); conferir todas as leituras dessas colunas | Reduz a superfície de dados sensíveis | Sim | Não | Médio: tabela do núcleo; só com backup e ensaio | Migration ensaiada em cópia; funções sem referência às colunas; nenhuma tela afetada |
| REG-14 | **Arrumação do repositório e da documentação:** enviar o commit local de documentação e os 5 documentos desta auditoria (com autorização); atualizar a trilha do `ROADMAP` (Render, `BACKUP-DOCS-1`); apagar ramos locais já publicados; decidir os 24 arquivos não rastreados; desligar o Web Analytics da Cloudflare ou liberá-lo na CSP | P3 | Autorização para push | Evita leituras erradas do estado do projeto | Não | Só se a CSP mudar | Baixo | `ROADMAP` coerente com esta auditoria; `git status` limpo |
| REG-15 | **Reexecutar a suíte de banco completa** (998 testes) num momento com espaço em disco, para registrar o estado atual | P3 | Cerca de 30 GB livres em C: | Evidência atualizada | Não | Não | Baixo | Resultado registrado |

## Dependências e ordem

1. **REG-01 → REG-02** vêm antes de qualquer migration nova (REG-05, 06, 07, 11, 13).
2. **REG-03 → REG-04** reaproveitam os mesmos geradores de arquivo.
3. **REG-09** começa por decisão do titular, não por código. O **REG-07** foi decidido em 15/11/2026: consolidação manual dispensada.
4. **REG-10** pode correr em paralelo desde já: depende só do titular.
5. **REG-13** só depois do backup e de um ensaio em cópia.

## O que pode sair da lista de pendências

- "Aplicar as migrations de Documentos Fiscais": **já aplicadas**.
- "Correção P23 do agrupador semanal": **improcedente**; o banco já exclui a ocorrência cancelada.
- "Publicar MOBILE-08, 09 e 10": **publicados** em 15/11/2026.
- "Storage persistente e disco do Render" e `BACKUP-DOCS-1` na forma antiga: **não se aplicam** à arquitetura atual, porque os documentos estão no banco. O backup em si continua pendente (REG-01).
