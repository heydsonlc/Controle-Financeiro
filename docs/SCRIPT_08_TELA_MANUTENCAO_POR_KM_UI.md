# SCRIPT 08 — TELA DE MANUTENÇÃO POR KM (UI)

## REFERÊNCIAS OBRIGATÓRIAS
Este script deve respeitar integralmente:
- `docs/CONTRATO_MODULO_VEICULOS.md` (v1.2)
- Manifesto do Módulo de Veículos (quando existir como documento separado)

Qualquer comportamento que viole esses documentos é proibido.

---

## OBJETIVO
Implementar a tela de "Manutenção por km" como camada narrativa e operacional,
permitindo ao usuário:
- configurar regras de manutenção por uso (km)
- visualizar próximas manutenções estimadas
- gerar despesas previstas de forma explícita (manual)

---

## REGRAS FUNDAMENTAIS (DO CONTRATO)
- Manutenção por km é **estimativa**, não agenda fixa
- Nenhuma despesa é criada automaticamente
- Toda geração exige ação explícita do usuário
- Despesas criadas são **sempre** `DespesaPrevista`
- Nenhum lançamento real pode ser criado

---

## BACKEND (JÁ EXISTENTE)
Utilizar endpoints existentes:
- `GET /api/veiculos/<id>/uso`
- `GET /api/veiculos/<id>/manutencoes-km`
- `POST /api/veiculos/<id>/manutencoes-km/gerar`
- `GET /api/veiculos/<id>/regras-km`
- `POST /api/veiculos/<id>/regras-km`
- `DELETE /api/veiculos/<id>/regras-km/<regra_id>`

Proibido:
- criar manutenção automaticamente
- criar novas tabelas para esta entrega

---

## FRONTEND — IMPLEMENTAÇÃO

### 1) Ação do botão "Manutenção por km"
- Abrir modal ou página dedicada
- Nunca deixar o botão sem ação

### 2) Estrutura da tela

#### a) Cabeçalho (educacional)
- "Manutenção por uso (estimativa)"
- Explicar: baseado em uso estimado, ajuda a prever, não cria automaticamente

#### b) Bloco de uso estimado (leitura)
Exibir:
- km_estimado_acumulado
- media_movel_km_mes (últimos X meses)
- aviso de estimativa baseada em consumo

#### c) Próximas manutenções estimadas
Para cada regra:
- tipo_evento (com rótulo amigável)
- intervalo_km
- data estimada (mês/ano)
- custo estimado
- botão explícito "Gerar despesa prevista"

#### d) Regras de manutenção
- listar regras existentes
- permitir criar nova regra
- permitir remover regra

#### e) Impacto no custo mensal (educacional)
- Exibir um valor aproximado (R$/mês) baseado em uso estimado e regras
- Aviso: custo mensal consolidado considera regras como estimativa (não cria despesa automaticamente)

---

## CRITÉRIO DE ACEITE
- Usuário entende quando e por que uma manutenção foi estimada
- Usuário vê o impacto financeiro (educacional)
- Usuário gera a `DespesaPrevista` de forma explícita
- Nenhum lançamento real é criado
