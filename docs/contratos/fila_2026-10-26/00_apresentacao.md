Preparei 6 contratos de execução, começando pelo fechamento do escritor único e terminando com relatórios, backup e configurações. O motor de Financiamentos, que já está em desenvolvimento, fica fora dessa nova fila para não duplicar trabalho.

Todos seguem nossa metodologia:
- Diagnóstico direcionado e implementação na mesma execução.
- Fidelidade ao Flask, preservando as melhorias já realizadas.
- Reaproveitamento das funções Supabase existentes.
- Testes de banco, unitários e E2E.
- Autonomia para implementar correções seguras.
- Registro dos impedimentos sem paralisar os demais trabalhos.
- Nenhuma migration persistente, commit, push ou publicação sem autorização.
A ordem recomendada é:
1. FIN-ESCRITOR-UNICO-FINAL-1 — Fechar as proteções de escrita.
2. FIN-CATEGORIAS-RECORRENCIAS-2 — Completar categorias, fontes de receita e frequências.
3. FIN-PATRIMONIO-2 — Liberar cadastro e manutenção patrimonial.
4. FIN-MOBILIDADE-2 — Efetivar cenários e despesas previstas com segurança.
5. FIN-DOCUMENTOS-2 — Upload, manutenção e integração documental.
6. FIN-RELATORIOS-CONFIG-1 — Relatórios, preferências e backup.

Os scripts abaixo são independentes o suficiente para serem colocados na fila em sequência.
