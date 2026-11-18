-- FIN-MVP-CADASTRO-UNIFICADO-02 — despesa direta cadastrada e paga na mesma operacao.
--
-- Nenhuma regra financeira nova: a funcao chama, NA MESMA TRANSACAO, o cadastro oficial (criar_despesa) e o pagamento
-- oficial (pagar_despesa, o do botao Pagar): movimento de debito, saldo da conta, pagamento registrado e despesa paga.
-- Se o pagamento for recusado (conta invalida, pagamento nao habilitado no perfil, dados invalidos), a excecao desfaz
-- tambem o cadastro: nao fica despesa "paga" sem registro financeiro, nem despesa pendente criada pela metade.
-- Sem tabela nova e sem alteracao de dados. So para despesa direta (nao recorrente), pelo valor integral.
--
-- Idempotencia: a chave e a do cadastro; a do pagamento deriva dela. Repetir a chamada (duplo clique, reenvio) devolve o
-- mesmo resultado, sem segunda despesa nem segundo pagamento.

create function financeiro.criar_despesa_paga(p_perfil_id integer, p_dados jsonb, p_pagamento jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_criada  jsonb;
    v_paga    jsonb;
    v_chave   uuid;
    v_valor   numeric;
begin
    if p_chave is null then
        raise exception 'Chave da operacao obrigatoria' using errcode = '22023';
    end if;
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' then
        raise exception 'Dados da despesa invalidos' using errcode = '22023';
    end if;
    if coalesce(p_dados ->> 'recorrente', 'false') not in ('false', 'f') then
        raise exception 'Pagamento no cadastro: so para despesa direta (as ocorrencias da recorrencia sao pagas uma a uma)'
            using errcode = '22023';
    end if;
    if p_pagamento is null or jsonb_typeof(p_pagamento) <> 'object' then
        raise exception 'Dados do pagamento invalidos' using errcode = '22023';
    end if;
    if nullif(btrim(coalesce(p_pagamento ->> 'conta_bancaria_id', '')), '') is null then
        raise exception 'Informe a conta bancaria do pagamento' using errcode = '22023';
    end if;
    if nullif(btrim(coalesce(p_pagamento ->> 'data_pagamento', '')), '') is null then
        raise exception 'Informe a data do pagamento' using errcode = '22023';
    end if;
    v_chave := extensions.uuid_generate_v5(p_chave, 'pagar');

    -- 1. Cadastro oficial (permissao, escritor, validacoes, competencia e idempotencia sao os dele).
    v_criada := financeiro.criar_despesa(p_perfil_id, p_dados, p_chave);
    if coalesce((v_criada ->> 'repetida')::boolean, false)
       and not exists (select 1 from financeiro.operacao_despesa o where o.chave = v_chave and o.operacao = 'pagar_despesa') then
        -- a chave ja foi usada por um cadastro SEM pagamento: nao se paga uma despesa que esta chamada nao criou
        raise exception 'Chave da operacao ja usada' using errcode = '22023';
    end if;
    if (v_criada ->> 'conta_id') is null then
        raise exception 'Pagamento no cadastro: so para despesa direta' using errcode = '22023';
    end if;

    -- 2. Pagamento oficial, integral, pelo valor que acabou de ser gravado (sem ajuste, juros ou desconto).
    select c.valor into v_valor from public.conta c where c.id = (v_criada ->> 'conta_id')::integer;
    v_paga := financeiro.pagar_despesa(p_perfil_id, (v_criada ->> 'conta_id')::integer,
        jsonb_build_object('conta_bancaria_id', p_pagamento -> 'conta_bancaria_id', 'data_pagamento', p_pagamento -> 'data_pagamento',
                           'valor_pago', v_valor, 'valor_devido', v_valor),
        v_chave);
    return (v_criada - 'repetida') || jsonb_build_object('paga', true, 'pagamento', v_paga - 'repetida',
                                                         'repetida', coalesce((v_criada ->> 'repetida')::boolean, false));
end
$$;

revoke execute on function financeiro.criar_despesa_paga(integer, jsonb, jsonb, uuid) from public, anon;
grant execute on function financeiro.criar_despesa_paga(integer, jsonb, jsonb, uuid) to authenticated;

comment on function financeiro.criar_despesa_paga(integer, jsonb, jsonb, uuid) is
    'FIN-MVP-CADASTRO-UNIFICADO-02: despesa direta cadastrada e paga numa transacao (criar_despesa + pagar_despesa).';
