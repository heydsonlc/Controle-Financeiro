# Checklist de Estabilizacao Local

Data da rodada: 2026-05-05

## Ambiente

- Branch: `main`
- Migration atual: `f6a7b8c9d0e1`
- Migration head: `f6a7b8c9d0e1`
- Banco: PostgreSQL configurado pelo ambiente local
- Objetivo: validar prontidao para uso real local com foco em seguranca, isolamento por perfil e backup

## Testes automatizados

| Validacao | Resultado |
| --- | --- |
| Suite Python completa | Aprovado |
| Smoke E2E | Aprovado: 14 passed, 2 skipped conhecidos |
| Functional E2E | Aprovado: 10 passed em servidor testing |
| Teste de isolamento local | Aprovado em execucao isolada |

## Modulos validados

| Modulo | Status | Observacao |
| --- | --- | --- |
| Perfil financeiro | Validado por testes e smoke | Troca e isolamento cobertos por APIs e fluxos E2E |
| Configuracoes | Validado por smoke | Secao Backup acessivel |
| Backup local | Validado com ressalva ambiental | `pg_dump` nao encontrado no PATH; erro controlado e historico registrados |
| Contas Bancarias | Validado por E2E | Botao principal recebeu seletor estavel |
| Categorias | Validado por E2E | Teste ajustado para seletor atual |
| Receitas | Validado por E2E | Fluxo recorrente estabilizado |
| Mobilidade | Validado por E2E | Categoria de teste criada em setup isolado |
| Patrimonio | Validado por E2E | Helper de texto ajustado para elementos visiveis |
| Documentos fiscais | Validado por suite Python | Sem alteracao de regra fiscal |

## Pendencias

| Pendencia | Gravidade | Acao recomendada |
| --- | --- | --- |
| Confirmar `pg_dump` no PATH da maquina de uso real | Media | Instalar PostgreSQL client tools ou ajustar PATH |
| Testes manuais finais de restore real | Media | Executar somente com base descartavel |
| Cobertura funcional por navegador de todos os modulos | Baixa | Ampliar testes E2E por fluxo critico |

## Status

Pronto com ressalvas: a aplicacao passou na suite automatizada, smoke, functional E2E e validacao manual leve. A principal ressalva operacional antes do uso real e instalar as ferramentas cliente do PostgreSQL ou adicionar `pg_dump` ao PATH para permitir backup real.
