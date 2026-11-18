-- FIN-MVP-CADASTRO-UNIFICADO-02 — reversao da migration 20261230090000.
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica. So retira a funcao: as despesas pagas por ela continuam como
-- qualquer despesa paga (despesa, movimento e pagamento sao os registros de sempre; o estorno e o de sempre). Antes de
-- aplicar, volte o frontend ao deploy anterior: sem a funcao, a opcao "Registrar esta despesa como paga" recusa a gravacao.

drop function if exists financeiro.criar_despesa_paga(integer, jsonb, jsonb, uuid);
