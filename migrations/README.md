# Migrations

Scripts de migração do banco de dados.

## ⚠️ Importante

Execute migrations na ordem cronológica (data de criação) para evitar problemas.

## 📋 Migrations Disponíveis

### Estruturais

- `adicionar_campos_cartao.py` - Adiciona campos ao modelo Cartão
- `adicionar_campos_despesa.py` - Adiciona campos ao modelo Despesa
- `adicionar_recorrencia_dias_semana.py` - Suporte a dias da semana
- `atualizar_tipos_recorrencia.py` - Atualiza tipos de recorrência
- `migrar_cartao.py` - Migração de estrutura do cartão

### Funcionalidades

- `add_recorrencia_cartao.py` - Suporte a despesas recorrentes no cartão
- `add_compra_id_lancamento.py` - UUID único para parcelamento
- `add_fechamento_fatura.py` - Estados de fatura (ABERTA, FECHADA, PAGA)

## 🔧 Como Executar

```bash
# Da raiz do projeto:
python migrations/nome_da_migration.py
```

## ✅ Checklist Pré-Migration

- [ ] Backup do banco de dados
- [ ] Verificar dependências (migrations anteriores)
- [ ] Testar em ambiente de desenvolvimento

---

**Atenção:** Migrations são **irreversíveis**. Sempre faça backup antes!
