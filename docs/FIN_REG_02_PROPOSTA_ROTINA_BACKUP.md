# FIN-REG-02 — Proposta de rotina periódica de backup

**Situação:** proposta para análise do titular. Nada foi agendado nem automatizado. Depende da homologação do FIN-REG-01 e de autorização específica.

## 1. Camadas de proteção

| Camada | O que cobre | Estado |
|---|---|---|
| Backup gerenciado do Supabase (diário, cerca de 7 dias) | Erro recente, com o projeto existente | Já existe; confirmar o plano no painel |
| Backup independente cifrado (FIN-REG-01) | Perda do projeto ou da conta; consulta a dados antigos | 1 backup feito em 15/11/2026 |
| Rotina periódica (esta proposta) | Manter o backup independente atual | A decidir |

## 2. Frequência proposta

| Quando | Por quê |
|---|---|
| **Semanal**, no mesmo dia e horário | O volume de lançamentos é baixo; entre os backups semanais, o gerenciado diário cobre os últimos 7 dias |
| **Antes de toda migration estrutural** e de toda carga, limpeza ou regularização de dados | É o momento de maior risco; o backup vira a referência de retorno |
| **Depois de enviar documentos fiscais importantes** (opcional) | Os documentos só existem no banco |

## 3. Retenção e rotação

- **Semanais:** manter os 8 últimos, cerca de 2 meses.
- **Mensais:** o primeiro de cada mês, por 12 meses.
- **Anuais:** o de dezembro de cada ano, sem prazo (fechamento para o Imposto de Renda).
- **Antes de migration:** manter até a migration seguinte ser homologada.
- **Tamanho:** cerca de 6,5 MB por backup hoje; o total é irrelevante para o disco e para o OneDrive.
- **Rotação:** apagar os mais antigos só depois de conferir que os mais novos estão íntegros nos dois destinos.

## 4. Chave

Duas opções, a decidir:

1. **Uma chave por backup** (como no FIN-REG-01): mais isolamento, porém muitas chaves para guardar.
2. **Uma chave anual** (recomendada para a rotina): guardada em dois lugares fora do computador, por exemplo cofre de senhas e pendrive. Troca-se uma vez por ano, e os backups antigos continuam com a chave do ano deles.

Em qualquer caso, a chave nunca fica na mesma nuvem que as cópias.

## 5. Verificação periódica

| Verificação | Frequência | Como |
|---|---|---|
| Hash das cópias guardadas | A cada backup novo | SHA-256 de cada `.cfbak` comparado com a ficha, nos dois destinos |
| Decifragem e `verificar` | Mensal | Decifrar o mais recente e conferir o manifesto |
| **Ensaio de restauração completo** | Trimestral e antes de migrations de risco | Restaurar num PostgreSQL 17 descartável e exigir "HOMOLOGADO" |
| Backups gerenciados | Mensal | `supabase backups list`: último com menos de 48 horas |

## 6. Automação: opções

| Opção | Como | Prós | Contras |
|---|---|---|---|
| **A. Manual assistida** (recomendada para começar) | Um único comando (`scripts/backup_rotina.py`, a criar) faz exportar, verificar, cifrar, copiar e registrar; roda quando o titular pedir ou no início de cada sessão de trabalho | Simples; nada exposto; sem credencial guardada em agendador | Depende de lembrar |
| B. Agendador de Tarefas do Windows | O mesmo comando, semanal | Automático | O computador precisa estar ligado; a credencial fica acessível à tarefa; a falha precisa de aviso |
| C. GitHub Actions ou serviço externo | Execução em nuvem | Independe do computador | Exige guardar a conexão da produção e a chave num terceiro, além de armazenamento externo; pior para a privacidade. **Não recomendado** |

**O que o comando único deve fazer** (contrato futuro):
- conferir o projeto;
- exportar e verificar;
- cifrar;
- copiar para os dois destinos e conferir os hashes;
- aplicar a retenção;
- gravar uma linha num registro local (data, identificação, tamanho, hashes, resultado);
- avisar claramente em caso de falha;
- nunca manter texto claro ao final.

## 7. Alertas

- **Opção A:** o próprio comando mostra o resultado e a idade do último backup. Pode-se acrescentar um aviso quando o último backup tiver mais de 10 dias.
- **Opção B:** além disso, um arquivo de estado e uma notificação do Windows em caso de falha.

## 8. Responsável

- **Pela execução e pela guarda da chave:** o titular.
- **Pela recuperação:** o titular, seguindo `docs/FIN_REG_01_RECUPERACAO.md`. Recomenda-se que uma segunda pessoa de confiança saiba onde estão o backup, a chave e o roteiro.

## 9. Decisões que o FIN-REG-02 precisa do titular

1. Frequência: semanal + antes de migrations (proposto) ou outra.
2. Chave: por backup ou anual, e onde ficam as duas cópias dela.
3. Automação: opção A, B ou C.
4. Retenção: a proposta acima ou outra.
5. Se o registro das execuções fica só local ou também no repositório (sem dados, só data, identificação e hashes).
