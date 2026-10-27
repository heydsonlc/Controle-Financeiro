-- FIN-PATRIMONIO-2 — escrita do modulo Patrimonio no novo aplicativo (caixinhas, transferencias e bens da Empresa).
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261126090000).
-- Validada em cluster PostgreSQL local descartavel (tests/test_supabase_patrimonio_escrita.py, comparada com o Flask).
-- Docs: docs/FIN_PATRIMONIO_2.md. Reversao: supabase/reversao/20261126090000_remover_patrimonio_escrita.sql.
--
-- Reproduz as rotas de escrita de routes/patrimonio.py e de PatrimonioEmpresarialService, com o escritor unico do
-- perfil (financeiro.exigir_escrita_novo, FIN-ESCRITOR-UNICO-FINAL-1): perfil ainda no Flask e recusado (SISTEMA_FLASK)
-- antes de qualquer gravacao; o Flask recusa o perfil do novo aplicativo (guarda em routes/patrimonio.py).
-- - Caixinhas (conta_patrimonio): criar (saldo atual = saldo inicial), editar (nome unico no perfil, tipo, meta, cor,
--   observacoes, ativo), inativar. O saldo so muda pelas transferencias, como no Flask.
-- - Transferencias: criar (contas ativas do perfil, distintas, saldo suficiente na origem) e excluir (desfaz os saldos).
--   As duas contas sao travadas em ordem de id: transferencias simultaneas nao deixam saldo errado.
-- - Bens (bem_patrimonial, so no perfil Empresa): criar, editar, criar a partir de documento fiscal, vincular documento
--   (ir_comprovante_vinculo, um documento para um bem; o vinculo anterior do bem e desativado, nunca apagado) e excluir.
--   Campos normalizados como o Flask (_texto, _decimal, _parse_date, _normalizar_opcao, _normalizar_imagem) e a
--   depreciacao mensal recalculada (valor / vida util, meio para cima).
-- Correcoes classificadas (docs §5): valores em numeric (o Flask somava float), saldo inicial e valor da transferencia
-- com 2 casas e sem negativo, cor #RRGGBB, exclusao de transferencia recusada se deixar a conta de destino negativa,
-- e a exclusao de bem (o Flask nao tem) so sem documento vinculado: bem com lastro e baixado (status), nao apagado.
-- Leitura nova: documentos vinculaveis e os dados do documento para a sugestao (a heuristica fica no adaptador).
-- Nenhum dado existente e alterado pela migration; uma tabela nova (operacao_patrimonio, vazia).

create table financeiro.operacao_patrimonio (
    chave                uuid        primary key,
    user_id              uuid        not null references auth.users (id) on delete cascade,
    perfil_financeiro_id integer     not null,
    operacao             text        not null,
    resultado            jsonb       not null,
    criado_em            timestamptz not null default now()
);

comment on table financeiro.operacao_patrimonio is
    'FIN-PATRIMONIO-2: resultado de cada cadastro por chave do cliente (repeticao devolve o mesmo resultado).';

alter table financeiro.operacao_patrimonio enable row level security;
alter table financeiro.operacao_patrimonio force row level security;
revoke all on financeiro.operacao_patrimonio from public, anon, authenticated;

-- Repeticao da mesma chave: o resultado gravado (ou NULL se for nova). Trava a chave ate o fim da transacao. Interna.
create function financeiro.repeticao_patrimonio(p_chave uuid, p_perfil_id integer, p_operacao text)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_anterior financeiro.operacao_patrimonio;
begin
    if p_chave is null then
        raise exception 'Chave da operacao obrigatoria' using errcode = '22023';
    end if;
    perform pg_advisory_xact_lock(hashtextextended(p_chave::text, 20261126));
    select * into v_anterior from financeiro.operacao_patrimonio o where o.chave = p_chave;
    if not found then
        return null;
    end if;
    if v_anterior.user_id is distinct from (select auth.uid()) or v_anterior.perfil_financeiro_id <> p_perfil_id
       or v_anterior.operacao <> p_operacao then
        raise exception 'Chave da operacao ja usada' using errcode = '22023';
    end if;
    return v_anterior.resultado || jsonb_build_object('repetida', true);
end
$$;

create function financeiro.registrar_operacao_patrimonio(p_chave uuid, p_perfil_id integer, p_operacao text,
                                                         p_resultado jsonb)
    returns jsonb
    language sql
    volatile
    security definer
    set search_path = ''
as $$
    insert into financeiro.operacao_patrimonio (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, p_operacao, p_resultado)
    returning resultado
$$;

-- Valor monetario: 2 casas, sem negativo (NULL quando vazio). Interna.
create function financeiro.valor_patrimonio(p_valor jsonb, p_campo text)
    returns numeric
    language plpgsql
    immutable
    set search_path = ''
as $$
declare
    v numeric;
begin
    if p_valor is null or p_valor = 'null'::jsonb or p_valor #>> '{}' = '' then
        return null;
    end if;
    begin
        v := (p_valor #>> '{}')::numeric;
    exception when others then
        raise exception '% invalido', p_campo using errcode = '22023';
    end;
    if v < 0 or v >= 100000000 or v <> round(v, 2) then
        raise exception '% deve ser zero ou positivo, com ate 2 casas decimais', p_campo using errcode = '22023';
    end if;
    return v;
end
$$;

-- =====================================================================================================================
-- Caixinhas
-- =====================================================================================================================

create function financeiro.travar_caixinha(p_perfil_id integer, p_conta_id integer)
    returns public.conta_patrimonio
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_conta public.conta_patrimonio;
begin
    select * into v_conta from public.conta_patrimonio c where c.id = p_conta_id for update;
    if not found or not financeiro.pertence_ao_perfil(v_conta.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Conta não encontrada' using errcode = 'P0001', hint = 'NAO_ENCONTRADA';
    end if;
    return v_conta;
end
$$;

-- Nome, tipo, meta, cor e observacoes (POST/PUT /api/patrimonio/contas). Interna.
create function financeiro.ler_dados_caixinha(p_perfil_id integer, p_conta_id integer, p_dados jsonb, p_parcial boolean)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_saida jsonb := '{}'::jsonb;
    v_nome  text;
begin
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' then
        raise exception 'Dados da conta invalidos' using errcode = '22023';
    end if;
    if p_dados ? 'nome' or not p_parcial then
        v_nome := btrim(coalesce(p_dados ->> 'nome', ''));
        if v_nome = '' then
            raise exception 'Nome é obrigatório' using errcode = '22023';
        end if;
        if length(v_nome) > 100 then
            raise exception 'Nome ate 100 caracteres' using errcode = '22023';
        end if;
        if exists (select 1 from public.conta_patrimonio c
                    where c.nome = v_nome and c.id is distinct from p_conta_id
                      and financeiro.pertence_ao_perfil(c.perfil_financeiro_id, p_perfil_id)) then
            raise exception 'Já existe uma conta com este nome' using errcode = '22023';
        end if;
        v_saida := v_saida || jsonb_build_object('nome', v_nome);
    end if;
    if p_dados ? 'tipo' then
        v_saida := v_saida || jsonb_build_object('tipo', nullif(left(btrim(coalesce(p_dados ->> 'tipo', '')), 50), ''));
    end if;
    if p_dados ? 'meta' then
        v_saida := v_saida || jsonb_build_object('meta', financeiro.valor_patrimonio(p_dados -> 'meta', 'Meta'));
    end if;
    if p_dados ? 'cor' and nullif(p_dados ->> 'cor', '') is not null then
        if p_dados ->> 'cor' !~ '^#[0-9A-Fa-f]{6}$' then
            raise exception 'Cor deve ser #RRGGBB' using errcode = '22023';
        end if;
        v_saida := v_saida || jsonb_build_object('cor', p_dados ->> 'cor');
    end if;
    if p_dados ? 'observacoes' then
        v_saida := v_saida || jsonb_build_object('observacoes', nullif(p_dados ->> 'observacoes', ''));
    end if;
    if p_dados ? 'ativo' then
        if jsonb_typeof(p_dados -> 'ativo') <> 'boolean' then
            raise exception 'Ativo deve ser verdadeiro ou falso' using errcode = '22023';
        end if;
        v_saida := v_saida || jsonb_build_object('ativo', p_dados -> 'ativo');
    end if;
    return v_saida;
end
$$;

create function financeiro.criar_caixinha(p_perfil_id integer, p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_repetida jsonb;
    v_d        jsonb;
    v_saldo    numeric;
    v_id       integer;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    v_repetida := financeiro.repeticao_patrimonio(p_chave, p_perfil_id, 'criar_caixinha');
    if v_repetida is not null then
        return v_repetida;
    end if;
    perform pg_advisory_xact_lock(20261126, p_perfil_id);  -- nome unico no perfil
    v_d := financeiro.ler_dados_caixinha(p_perfil_id, null, p_dados, false);
    v_saldo := coalesce(financeiro.valor_patrimonio(p_dados -> 'saldo_inicial', 'Saldo inicial'), 0);
    insert into public.conta_patrimonio (perfil_financeiro_id, nome, tipo, saldo_inicial, saldo_atual, meta, cor,
                                         observacoes, ativo, criado_em)
    values (p_perfil_id, v_d ->> 'nome', v_d ->> 'tipo', v_saldo, v_saldo, (v_d ->> 'meta')::numeric,
            coalesce(v_d ->> 'cor', '#28a745'), v_d ->> 'observacoes', true, now() at time zone 'utc')
    returning id into v_id;
    return financeiro.registrar_operacao_patrimonio(p_chave, p_perfil_id, 'criar_caixinha', jsonb_build_object('conta_id', v_id));
end
$$;

create function financeiro.editar_caixinha(p_perfil_id integer, p_conta_id integer, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_d jsonb;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    perform pg_advisory_xact_lock(20261126, p_perfil_id);
    perform financeiro.travar_caixinha(p_perfil_id, p_conta_id);
    v_d := financeiro.ler_dados_caixinha(p_perfil_id, p_conta_id, p_dados, true);
    update public.conta_patrimonio c
       set nome = coalesce(v_d ->> 'nome', c.nome),
           tipo = case when v_d ? 'tipo' then v_d ->> 'tipo' else c.tipo end,
           meta = case when v_d ? 'meta' then (v_d ->> 'meta')::numeric else c.meta end,
           cor = coalesce(v_d ->> 'cor', c.cor),
           observacoes = case when v_d ? 'observacoes' then v_d ->> 'observacoes' else c.observacoes end,
           ativo = coalesce((v_d ->> 'ativo')::boolean, c.ativo)
     where c.id = p_conta_id;
    return jsonb_build_object('conta_id', p_conta_id);
end
$$;

-- Inativa (o Flask nunca apaga caixinha: ela sustenta transferencias e fontes de receita antigas).
create function financeiro.inativar_caixinha(p_perfil_id integer, p_conta_id integer)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    perform financeiro.travar_caixinha(p_perfil_id, p_conta_id);
    update public.conta_patrimonio set ativo = false where id = p_conta_id;
    return jsonb_build_object('conta_id', p_conta_id, 'ativo', false);
end
$$;

-- =====================================================================================================================
-- Transferencias
-- =====================================================================================================================

-- As duas contas travadas em ordem de id (transferencias simultaneas em sentidos opostos nao se bloqueiam). Interna.
create function financeiro.travar_contas_transferencia(p_origem integer, p_destino integer)
    returns void
    language sql
    volatile
    security definer
    set search_path = ''
as $$
    select 1 from public.conta_patrimonio c where c.id in (p_origem, p_destino) order by c.id for update
$$;

create function financeiro.criar_transferencia_patrimonio(p_perfil_id integer, p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_repetida jsonb;
    v_origem   public.conta_patrimonio;
    v_destino  public.conta_patrimonio;
    v_id_o     integer;
    v_id_d     integer;
    v_valor    numeric;
    v_data     date;
    v_id       integer;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    v_repetida := financeiro.repeticao_patrimonio(p_chave, p_perfil_id, 'criar_transferencia');
    if v_repetida is not null then
        return v_repetida;
    end if;
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' then
        raise exception 'Dados da transferencia invalidos' using errcode = '22023';
    end if;
    begin
        v_id_o := nullif(p_dados ->> 'conta_origem_id', '')::integer;
        v_id_d := nullif(p_dados ->> 'conta_destino_id', '')::integer;
    exception when others then
        raise exception 'Conta de origem ou de destino invalida' using errcode = '22023';
    end;
    if v_id_o is null then
        raise exception 'Conta de origem é obrigatória' using errcode = '22023';
    end if;
    if v_id_d is null then
        raise exception 'Conta de destino é obrigatória' using errcode = '22023';
    end if;
    if v_id_o = v_id_d then
        raise exception 'Conta de origem e destino não podem ser iguais' using errcode = '22023';
    end if;
    v_valor := financeiro.valor_patrimonio(p_dados -> 'valor', 'Valor');
    if v_valor is null or v_valor <= 0 then
        raise exception 'Valor deve ser maior que zero' using errcode = '22023';
    end if;
    if nullif(p_dados ->> 'data_transferencia', '') is null then
        raise exception 'Data da transferência é obrigatória' using errcode = '22023';
    end if;
    begin
        v_data := to_date(p_dados ->> 'data_transferencia', 'YYYY-MM-DD');
        if to_char(v_data, 'YYYY-MM-DD') <> p_dados ->> 'data_transferencia' then
            raise exception using errcode = '22007';
        end if;
    exception when others then
        raise exception 'Formato de data inválido. Use YYYY-MM-DD' using errcode = '22023';
    end;
    if length(coalesce(p_dados ->> 'descricao', '')) > 200 then
        raise exception 'Descricao ate 200 caracteres' using errcode = '22023';
    end if;

    perform financeiro.travar_contas_transferencia(v_id_o, v_id_d);
    select * into v_origem from public.conta_patrimonio where id = v_id_o;
    select * into v_destino from public.conta_patrimonio where id = v_id_d;
    if v_origem.id is null or not financeiro.pertence_ao_perfil(v_origem.perfil_financeiro_id, p_perfil_id)
       or not coalesce(v_origem.ativo, false) then
        raise exception 'Conta de origem não encontrada ou inativa' using errcode = 'P0001', hint = 'NAO_ENCONTRADA';
    end if;
    if v_destino.id is null or not financeiro.pertence_ao_perfil(v_destino.perfil_financeiro_id, p_perfil_id)
       or not coalesce(v_destino.ativo, false) then
        raise exception 'Conta de destino não encontrada ou inativa' using errcode = 'P0001', hint = 'NAO_ENCONTRADA';
    end if;
    if coalesce(v_origem.saldo_atual, 0) < v_valor then
        raise exception 'Saldo insuficiente na conta de origem' using errcode = '22023';
    end if;

    insert into public.transferencia (perfil_financeiro_id, conta_origem_id, conta_destino_id, valor, data_transferencia,
                                      descricao, observacoes, criado_em)
    values (p_perfil_id, v_id_o, v_id_d, v_valor, v_data, nullif(p_dados ->> 'descricao', ''),
            nullif(p_dados ->> 'observacoes', ''), now() at time zone 'utc')
    returning id into v_id;
    update public.conta_patrimonio set saldo_atual = coalesce(saldo_atual, 0) - v_valor where id = v_id_o;
    update public.conta_patrimonio set saldo_atual = coalesce(saldo_atual, 0) + v_valor where id = v_id_d;
    return financeiro.registrar_operacao_patrimonio(p_chave, p_perfil_id, 'criar_transferencia',
                                                    jsonb_build_object('transferencia_id', v_id));
end
$$;

-- Exclui e desfaz os saldos (DELETE /api/patrimonio/transferencias/<id>). Correcao: recusa se a conta de destino nao
-- tem mais o valor (o Flask deixava o saldo negativo).
create function financeiro.excluir_transferencia_patrimonio(p_perfil_id integer, p_transferencia_id integer)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_t public.transferencia;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    select * into v_t from public.transferencia t where t.id = p_transferencia_id;
    if not found or not financeiro.pertence_ao_perfil(v_t.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Transferência não encontrada' using errcode = 'P0001', hint = 'NAO_ENCONTRADA';
    end if;
    perform financeiro.travar_contas_transferencia(v_t.conta_origem_id, v_t.conta_destino_id);
    select * into v_t from public.transferencia t where t.id = p_transferencia_id for update;
    if not found then
        raise exception 'Transferência não encontrada' using errcode = 'P0001', hint = 'NAO_ENCONTRADA';
    end if;
    if (select coalesce(c.saldo_atual, 0) from public.conta_patrimonio c where c.id = v_t.conta_destino_id) < v_t.valor then
        raise exception 'A conta de destino não tem mais o valor desta transferência: desfazê-la deixaria o saldo negativo'
            using errcode = 'P0001', hint = 'SALDO_DESTINO';
    end if;
    update public.conta_patrimonio set saldo_atual = coalesce(saldo_atual, 0) + v_t.valor where id = v_t.conta_origem_id;
    update public.conta_patrimonio set saldo_atual = coalesce(saldo_atual, 0) - v_t.valor where id = v_t.conta_destino_id;
    delete from public.transferencia where id = p_transferencia_id;
    return jsonb_build_object('transferencia_id', p_transferencia_id, 'excluida', true);
end
$$;

-- =====================================================================================================================
-- Bens da Empresa
-- =====================================================================================================================

-- Perfil Empresa obrigatorio (PermissionError do Flask -> 403 na tela). Interna.
create function financeiro.exigir_perfil_empresa(p_perfil_id integer)
    returns void
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
begin
    if not financeiro.perfil_empresa(p_perfil_id) then
        raise exception 'Patrimonio empresarial disponivel apenas no perfil Empresa' using errcode = 'P0001', hint = 'SO_EMPRESA';
    end if;
end
$$;

-- _texto do Flask: sem espacos nas pontas, cortado no limite; vazio = NULL. Interna.
create function financeiro.texto_bem(p_valor text, p_limite integer)
    returns text
    language sql
    immutable
    set search_path = ''
as $$
    select nullif(left(btrim(coalesce(p_valor, '')), p_limite), '')
$$;

-- _decimal do Flask: 2 casas, meio para cima; invalido ou vazio = 0. Interna.
create function financeiro.decimal_bem(p_valor text)
    returns numeric
    language plpgsql
    immutable
    set search_path = ''
as $$
begin
    if p_valor is null or btrim(p_valor) = '' then
        return 0;
    end if;
    return round(btrim(p_valor)::numeric, 2);
exception when others then
    return 0;
end
$$;

-- _parse_int e _parse_date do Flask: invalido = NULL. Interna.
create function financeiro.inteiro_bem(p_valor jsonb)
    returns integer
    language plpgsql
    immutable
    set search_path = ''
as $$
begin
    if p_valor is null or p_valor = 'null'::jsonb or p_valor #>> '{}' = '' then
        return null;
    end if;
    if jsonb_typeof(p_valor) = 'number' then
        return trunc((p_valor #>> '{}')::numeric)::integer;  -- int(12.5) = 12
    end if;
    return (p_valor #>> '{}')::integer;
exception when others then
    return null;
end
$$;

create function financeiro.data_bem(p_valor text)
    returns date
    language plpgsql
    immutable
    set search_path = ''
as $$
declare
    v date;
begin
    if p_valor is null or btrim(p_valor) = '' then
        return null;
    end if;
    v := to_date(left(btrim(p_valor), 10), 'YYYY-MM-DD');
    return case when to_char(v, 'YYYY-MM-DD') = left(btrim(p_valor), 10) then v end;
exception when others then
    return null;
end
$$;

-- _normalizar_opcao do Flask. Interna.
create function financeiro.opcao_bem(p_valor text, p_permitidos text[], p_padrao text)
    returns text
    language sql
    immutable
    set search_path = ''
as $$
    select case when p_valor is null or p_valor = '' then p_padrao
                when upper(btrim(p_valor)) = any(p_permitidos) then upper(btrim(p_valor))
                else p_padrao end
$$;

-- _normalizar_imagem do Flask: so uma das imagens patrimonio* do sistema. Interna.
create function financeiro.imagem_bem(p_valor text)
    returns text
    language sql
    immutable
    set search_path = ''
as $$
    select i ->> 'arquivo'
      from jsonb_array_elements(financeiro.imagens_patrimonio()) i
     where i ->> 'arquivo' = regexp_replace(btrim(coalesce(p_valor, '')), '^.*[\\/]', '')
       and lower(i ->> 'arquivo') like 'patrimonio%'
$$;

-- Aplica ao bem os campos presentes em p_dados, como criar_bem/atualizar_bem do Flask. Interna.
create function financeiro.aplicar_dados_bem(p_bem public.bem_patrimonial, p_dados jsonb, p_novo boolean)
    returns public.bem_patrimonial
    language plpgsql
    immutable
    set search_path = ''
as $$
declare
    v_bem  public.bem_patrimonial := p_bem;
    v_texto record;
begin
    for v_texto in select * from (values ('nome', 160), ('codigo', 60), ('categoria', 80), ('descricao', 2000),
                                         ('fornecedor', 255), ('documento_numero', 80), ('centro_custo', 120),
                                         ('localizacao', 120), ('responsavel', 120), ('observacoes', 2000)) t(campo, limite)
    loop
        if p_dados ? v_texto.campo or p_novo then
            v_bem := jsonb_populate_record(v_bem, jsonb_build_object(v_texto.campo,
                         financeiro.texto_bem(p_dados ->> v_texto.campo, v_texto.limite)));
        end if;
    end loop;
    if p_dados ? 'nome' or p_novo then
        if v_bem.nome is null then
            raise exception 'Nome do bem e obrigatorio' using errcode = '22023';
        end if;
    end if;
    if p_novo then
        v_bem.categoria := coalesce(v_bem.categoria, 'Equipamentos');
    end if;
    if p_dados ? 'imagem_arquivo' or p_novo then
        v_bem.imagem_arquivo := financeiro.imagem_bem(p_dados ->> 'imagem_arquivo');
    end if;
    if p_dados ? 'data_aquisicao' or p_novo then
        v_bem.data_aquisicao := financeiro.data_bem(p_dados ->> 'data_aquisicao');
    end if;
    if p_dados ? 'valor_aquisicao' or p_novo then
        v_bem.valor_aquisicao := financeiro.decimal_bem(p_dados ->> 'valor_aquisicao');
    end if;
    if p_dados ? 'vida_util_meses' or p_novo then
        v_bem.vida_util_meses := financeiro.inteiro_bem(p_dados -> 'vida_util_meses');
    end if;
    if p_dados ? 'status' or p_novo then
        v_bem.status := financeiro.opcao_bem(p_dados ->> 'status', array['ATIVO', 'INATIVO', 'BAIXADO', 'EM_REVISAO'],
                                             coalesce(p_bem.status, 'ATIVO'));
    end if;
    if p_dados ? 'status_documental' or p_novo then
        v_bem.status_documental := financeiro.opcao_bem(p_dados ->> 'status_documental',
            array['COM_LASTRO', 'SEM_DOCUMENTO', 'PENDENTE', 'AGUARDANDO_CONTADOR', 'DIVERGENTE', 'NAO_APLICAVEL'],
            coalesce(p_bem.status_documental, 'SEM_DOCUMENTO'));
    end if;
    v_bem.depreciacao_mensal := financeiro.depreciacao_bem(v_bem.valor_aquisicao, v_bem.vida_util_meses);
    return v_bem;
end
$$;

-- _calcular_depreciacao do Flask. Interna.
create function financeiro.depreciacao_bem(p_valor numeric, p_meses integer)
    returns numeric
    language sql
    immutable
    set search_path = ''
as $$
    select case when p_meses is null or p_meses <= 0 then null
                else round(coalesce(round(p_valor, 2), 0) / p_meses, 2) end
$$;

create function financeiro.travar_bem(p_perfil_id integer, p_bem_id integer)
    returns public.bem_patrimonial
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_bem public.bem_patrimonial;
begin
    perform financeiro.exigir_perfil_empresa(p_perfil_id);
    select * into v_bem from public.bem_patrimonial b where b.id = p_bem_id and b.perfil_financeiro_id = p_perfil_id for update;
    if not found then
        raise exception 'Bem patrimonial nao encontrado no perfil ativo' using errcode = 'P0001', hint = 'NAO_ENCONTRADA';
    end if;
    return v_bem;
end
$$;

-- Documento fiscal do perfil, travado (dois bens nao levam o mesmo documento ao mesmo tempo). Interna.
create function financeiro.travar_documento_patrimonio(p_perfil_id integer, p_comprovante_id integer)
    returns public.ir_comprovante
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_doc public.ir_comprovante;
begin
    select * into v_doc from public.ir_comprovante c where c.id = p_comprovante_id for update;
    if not found or not financeiro.pertence_ao_perfil(v_doc.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Documento fiscal nao encontrado no perfil ativo' using errcode = '22023';
    end if;
    return v_doc;
end
$$;

-- _validar_documento_sem_vinculo_patrimonial + _criar_vinculo_documento do Flask. O vinculo anterior do bem fica
-- inativo (historico preservado). Interna.
create function financeiro.vincular_documento_ao_bem(p_perfil_id integer, p_bem_id integer, p_comprovante_id integer,
                                                     p_dados jsonb)
    returns void
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_doc public.ir_comprovante := financeiro.travar_documento_patrimonio(p_perfil_id, p_comprovante_id);
    v_bem public.bem_patrimonial;
begin
    if exists (select 1 from public.ir_comprovante_vinculo v
                where v.comprovante_id = v_doc.id and v.perfil_financeiro_id = p_perfil_id
                  and v.tipo_entidade = 'PATRIMONIO' and v.ativo and v.entidade_id is distinct from p_bem_id) then
        raise exception 'Documento fiscal ja esta vinculado a um bem patrimonial' using errcode = '22023';
    end if;
    select * into v_bem from public.bem_patrimonial where id = p_bem_id;
    update public.ir_comprovante_vinculo v set ativo = false, updated_at = now() at time zone 'utc'
     where v.perfil_financeiro_id = p_perfil_id and v.tipo_entidade = 'PATRIMONIO' and v.entidade_id = p_bem_id and v.ativo;
    insert into public.ir_comprovante_vinculo (comprovante_id, perfil_financeiro_id, tipo_entidade, entidade_id,
                                               resumo_entidade, tipo_vinculo, natureza, status_lastro, observacoes, ativo,
                                               created_at, updated_at)
    values (v_doc.id, p_perfil_id, 'PATRIMONIO', p_bem_id,
            left(v_bem.nome || ' (' || coalesce(v_bem.codigo, v_bem.id::text) || ')', 255),
            financeiro.opcao_bem(p_dados ->> 'tipo_vinculo',
                array['NOTA_FISCAL', 'COMPROVANTE', 'RECIBO', 'CONTRATO', 'DOCUMENTO_CONTABIL', 'OUTRO'], 'NOTA_FISCAL'),
            financeiro.opcao_bem(p_dados ->> 'natureza',
                array['PATRIMONIO_IMOBILIZADO', 'DESPESA_OPERACIONAL', 'SOFTWARE_ASSINATURA', 'IMPOSTO_TAXA', 'OUTRO'],
                'PATRIMONIO_IMOBILIZADO'),
            financeiro.opcao_bem(p_dados ->> 'status_lastro', array['VALIDADO', 'COM_DOCUMENTO', 'PENDENTE'], 'VALIDADO'),
            financeiro.texto_bem(p_dados ->> 'observacoes', 1000), true, now() at time zone 'utc', now() at time zone 'utc');
    update public.bem_patrimonial b
       set status_documental = 'COM_LASTRO',
           fornecedor = coalesce(b.fornecedor, nullif(v_doc.prestador_nome, '')),
           data_aquisicao = coalesce(b.data_aquisicao, v_doc.data_documento),
           valor_aquisicao = case when coalesce(b.valor_aquisicao, 0) = 0 and v_doc.valor is not null
                                  then v_doc.valor else b.valor_aquisicao end,
           documento_numero = coalesce(b.documento_numero, 'DOC-' || v_doc.id)
     where b.id = p_bem_id;
    update public.bem_patrimonial b
       set depreciacao_mensal = financeiro.depreciacao_bem(b.valor_aquisicao, b.vida_util_meses)
     where b.id = p_bem_id;
end
$$;

-- Insercao comum de criar_bem e criar_a_partir_documento. Interna.
create function financeiro.inserir_bem(p_perfil_id integer, p_dados jsonb)
    returns integer
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_bem  public.bem_patrimonial;
    v_doc  integer := financeiro.inteiro_bem(p_dados -> 'comprovante_id');
    v_id   integer;
begin
    v_bem := financeiro.aplicar_dados_bem(null::public.bem_patrimonial, p_dados, true);
    if v_doc is not null then
        v_bem.status_documental := 'COM_LASTRO';
    end if;
    insert into public.bem_patrimonial (perfil_financeiro_id, nome, codigo, categoria, descricao, fornecedor,
                                        documento_numero, imagem_arquivo, data_aquisicao, valor_aquisicao, vida_util_meses,
                                        depreciacao_mensal, centro_custo, localizacao, responsavel, status,
                                        status_documental, observacoes, created_at, updated_at)
    values (p_perfil_id, v_bem.nome, v_bem.codigo, v_bem.categoria, v_bem.descricao, v_bem.fornecedor,
            v_bem.documento_numero, v_bem.imagem_arquivo, v_bem.data_aquisicao, v_bem.valor_aquisicao, v_bem.vida_util_meses,
            v_bem.depreciacao_mensal, v_bem.centro_custo, v_bem.localizacao, v_bem.responsavel, v_bem.status,
            v_bem.status_documental, v_bem.observacoes, now() at time zone 'utc', now() at time zone 'utc')
    returning id into v_id;
    if v_doc is not null then
        perform financeiro.vincular_documento_ao_bem(p_perfil_id, v_id, v_doc, p_dados);
    end if;
    return v_id;
end
$$;

create function financeiro.criar_bem_patrimonial(p_perfil_id integer, p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_repetida jsonb;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    perform financeiro.exigir_perfil_empresa(p_perfil_id);
    v_repetida := financeiro.repeticao_patrimonio(p_chave, p_perfil_id, 'criar_bem');
    if v_repetida is not null then
        return v_repetida;
    end if;
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' then
        raise exception 'Dados do bem invalidos' using errcode = '22023';
    end if;
    return financeiro.registrar_operacao_patrimonio(p_chave, p_perfil_id, 'criar_bem',
        jsonb_build_object('bem_id', financeiro.inserir_bem(p_perfil_id, p_dados)));
end
$$;

-- Criar a partir de documento fiscal: os campos vazios vem do documento, como o Flask.
create function financeiro.criar_bem_de_documento(p_perfil_id integer, p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_repetida   jsonb;
    v_doc        public.ir_comprovante;
    v_fornecedor text;
    v_nome       text;
    v_dados      jsonb;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    perform financeiro.exigir_perfil_empresa(p_perfil_id);
    v_repetida := financeiro.repeticao_patrimonio(p_chave, p_perfil_id, 'criar_bem_de_documento');
    if v_repetida is not null then
        return v_repetida;
    end if;
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' or financeiro.inteiro_bem(p_dados -> 'comprovante_id') is null then
        raise exception 'Documento fiscal e obrigatorio' using errcode = '22023';
    end if;
    v_doc := financeiro.travar_documento_patrimonio(p_perfil_id, financeiro.inteiro_bem(p_dados -> 'comprovante_id'));
    if exists (select 1 from public.ir_comprovante_vinculo v
                where v.comprovante_id = v_doc.id and v.perfil_financeiro_id = p_perfil_id
                  and v.tipo_entidade = 'PATRIMONIO' and v.ativo) then
        raise exception 'Documento fiscal ja esta vinculado a um bem patrimonial' using errcode = '22023';
    end if;
    v_fornecedor := coalesce(financeiro.texto_bem(p_dados ->> 'fornecedor', 255), v_doc.prestador_nome);
    v_nome := coalesce(financeiro.texto_bem(p_dados ->> 'nome', 160),
                       left('Bem patrimonial - ' || coalesce(v_fornecedor, 'Documento fiscal'), 160));
    v_dados := p_dados || jsonb_build_object(
        'nome', v_nome, 'fornecedor', v_fornecedor,
        'data_aquisicao', coalesce(nullif(p_dados ->> 'data_aquisicao', ''), v_doc.data_documento::text),
        'valor_aquisicao', case when nullif(p_dados ->> 'valor_aquisicao', '') is null then v_doc.valor::text
                                else p_dados ->> 'valor_aquisicao' end,
        'categoria', coalesce(nullif(p_dados ->> 'categoria', ''), 'Equipamentos'),
        'documento_numero', coalesce(nullif(p_dados ->> 'documento_numero', ''), 'DOC-' || v_doc.id),
        'comprovante_id', v_doc.id, 'status_documental', 'COM_LASTRO');
    return financeiro.registrar_operacao_patrimonio(p_chave, p_perfil_id, 'criar_bem_de_documento',
        jsonb_build_object('bem_id', financeiro.inserir_bem(p_perfil_id, v_dados)));
end
$$;

create function financeiro.editar_bem_patrimonial(p_perfil_id integer, p_bem_id integer, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_bem public.bem_patrimonial;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    v_bem := financeiro.travar_bem(p_perfil_id, p_bem_id);
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' then
        raise exception 'Dados do bem invalidos' using errcode = '22023';
    end if;
    v_bem := financeiro.aplicar_dados_bem(v_bem, p_dados, false);
    update public.bem_patrimonial b
       set nome = v_bem.nome, codigo = v_bem.codigo, categoria = v_bem.categoria, descricao = v_bem.descricao,
           fornecedor = v_bem.fornecedor, documento_numero = v_bem.documento_numero, imagem_arquivo = v_bem.imagem_arquivo,
           data_aquisicao = v_bem.data_aquisicao, valor_aquisicao = v_bem.valor_aquisicao,
           vida_util_meses = v_bem.vida_util_meses, depreciacao_mensal = v_bem.depreciacao_mensal,
           centro_custo = v_bem.centro_custo, localizacao = v_bem.localizacao, responsavel = v_bem.responsavel,
           status = v_bem.status, status_documental = v_bem.status_documental, observacoes = v_bem.observacoes,
           updated_at = now() at time zone 'utc'
     where b.id = p_bem_id;
    return jsonb_build_object('bem_id', p_bem_id);
end
$$;

create function financeiro.vincular_documento_bem(p_perfil_id integer, p_bem_id integer, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_doc integer;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    perform financeiro.travar_bem(p_perfil_id, p_bem_id);
    v_doc := financeiro.inteiro_bem(coalesce(p_dados, '{}'::jsonb) -> 'comprovante_id');
    if v_doc is null then
        raise exception 'Documento fiscal e obrigatorio' using errcode = '22023';
    end if;
    perform financeiro.vincular_documento_ao_bem(p_perfil_id, p_bem_id, v_doc, coalesce(p_dados, '{}'::jsonb));
    update public.bem_patrimonial set updated_at = now() at time zone 'utc' where id = p_bem_id;
    return jsonb_build_object('bem_id', p_bem_id, 'comprovante_id', v_doc);
end
$$;

-- Exclusao segura (o Flask nao exclui bens): so sem nenhum vinculo de documento, nem inativo (lastro e historico).
-- Com documento, o caminho e a baixa (status Baixado).
create function financeiro.excluir_bem_patrimonial(p_perfil_id integer, p_bem_id integer)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    perform financeiro.travar_bem(p_perfil_id, p_bem_id);
    if exists (select 1 from public.ir_comprovante_vinculo v
                where v.tipo_entidade = 'PATRIMONIO' and v.entidade_id = p_bem_id
                  and financeiro.pertence_ao_perfil(v.perfil_financeiro_id, p_perfil_id)) then
        raise exception 'Bem com documento fiscal vinculado (lastro): nao e excluido. Mude a situacao para Baixado.'
            using errcode = 'P0001', hint = 'COM_DOCUMENTO';
    end if;
    delete from public.bem_patrimonial where id = p_bem_id;
    return jsonb_build_object('bem_id', p_bem_id, 'excluido', true);
end
$$;

-- =====================================================================================================================
-- Leituras novas
-- =====================================================================================================================

-- serializar_documento do Flask (sem o vinculo). Interna.
create function financeiro.documento_patrimonio_flask(p_c public.ir_comprovante)
    returns jsonb
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select jsonb_build_object(
        'id', p_c.id,
        'label', coalesce(nullif(p_c.prestador_nome, ''), 'Documento fiscal') || ' - '
                 || coalesce(p_c.data_documento::text, 'sem data') || ' - R$ '
                 || translate(to_char(coalesce(p_c.valor, 0), 'FM999,999,999,990.00'), ',.', '.,'),
        'prestador_nome', p_c.prestador_nome, 'prestador_cpf_cnpj', p_c.prestador_cpf_cnpj,
        'data_documento', p_c.data_documento, 'valor', p_c.valor,
        'categoria_nome', (select cat.nome from public.categoria cat where cat.id = p_c.categoria_id),
        'categoria_ir_nome', (select ic.nome from public.ir_categoria ic where ic.id = p_c.categoria_ir_id),
        'status', p_c.status,
        'arquivo', (select jsonb_build_object('id', a.id, 'comprovante_id', a.comprovante_id, 'nome_arquivo', a.nome_arquivo,
                                              'mime_type', a.mime_type, 'tamanho_bytes', a.tamanho_bytes,
                                              'hash_arquivo', a.hash_arquivo, 'created_at', financeiro.iso_python(a.created_at))
                      from public.ir_comprovante_arquivo a where a.comprovante_id = p_c.id order by a.id limit 1),
        'download_url', '/api/ir/comprovantes/' || p_c.id || '/arquivo')
$$;

-- GET /api/patrimonio/documentos-vinculaveis[?busca=]: documentos do perfil Empresa sem vinculo patrimonial ativo.
create function financeiro.patrimonio_documentos_vinculaveis_tela(p_perfil_id integer, p_busca text)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_termo text := financeiro.texto_bem(p_busca, 120);
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if not financeiro.perfil_empresa(p_perfil_id) then
        return '[]'::jsonb;
    end if;
    return coalesce((
        select jsonb_agg(financeiro.documento_patrimonio_flask(x) order by x.data_documento desc nulls first, x.id desc)
          from (select c.* from public.ir_comprovante c
                 where c.perfil_financeiro_id = p_perfil_id
                   and not exists (select 1 from public.ir_comprovante_vinculo v
                                    where v.comprovante_id = c.id and v.perfil_financeiro_id = p_perfil_id
                                      and v.tipo_entidade = 'PATRIMONIO' and v.ativo)
                   and (v_termo is null or c.prestador_nome ilike '%' || v_termo || '%'
                        or c.prestador_cpf_cnpj ilike '%' || v_termo || '%' or c.observacoes ilike '%' || v_termo || '%'
                        or c.hash_arquivo ilike '%' || v_termo || '%')
                 order by c.data_documento desc nulls first, c.id desc
                 limit 50) x), '[]'::jsonb);
end
$$;

-- Dados do documento para a sugestao de bem (GET /bens/sugestao-a-partir-documento/<id>): o texto base e os campos que a
-- heuristica do Flask (PatrimonioSugestaoService) usa; a heuristica roda no adaptador.
create function financeiro.patrimonio_documento_sugestao_tela(p_perfil_id integer, p_comprovante_id integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_c public.ir_comprovante;
    v_v public.ir_comprovante_vinculo;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if not financeiro.perfil_empresa(p_perfil_id) then
        raise exception 'Sugestao patrimonial disponivel apenas no perfil Empresa' using errcode = 'P0001', hint = 'SO_EMPRESA';
    end if;
    select * into v_c from public.ir_comprovante c where c.id = p_comprovante_id;
    if not found or not financeiro.pertence_ao_perfil(v_c.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Documento fiscal nao encontrado no perfil ativo' using errcode = 'P0001', hint = 'NAO_ENCONTRADA';
    end if;
    select * into v_v from public.ir_comprovante_vinculo v
     where v.comprovante_id = v_c.id and v.perfil_financeiro_id = p_perfil_id and v.tipo_entidade = 'PATRIMONIO' and v.ativo
     order by v.created_at desc, v.id desc limit 1;
    return jsonb_build_object(
        'comprovante_id', v_c.id,
        'documento', financeiro.documento_patrimonio_flask(v_c),
        'vinculo_existente', case when v_v.id is null then null else jsonb_build_object(
            'id', v_v.id, 'comprovante_id', v_v.comprovante_id, 'perfil_financeiro_id', v_v.perfil_financeiro_id,
            'tipo_entidade', v_v.tipo_entidade, 'entidade_id', v_v.entidade_id, 'resumo_entidade', v_v.resumo_entidade,
            'tipo_vinculo', v_v.tipo_vinculo, 'natureza', v_v.natureza, 'status_lastro', v_v.status_lastro,
            'observacoes', v_v.observacoes, 'ativo', coalesce(v_v.ativo, false),
            'created_at', financeiro.iso_python(v_v.created_at), 'updated_at', financeiro.iso_python(v_v.updated_at)) end,
        'texto_extraido', v_c.texto_extraido, 'observacoes', v_c.observacoes, 'prestador_nome', v_c.prestador_nome,
        'categoria_nome', (select cat.nome from public.categoria cat where cat.id = v_c.categoria_id),
        'categoria_ir_nome', (select ic.nome from public.ir_categoria ic where ic.id = v_c.categoria_ir_id),
        'arquivo_nome', (select a.nome_arquivo from public.ir_comprovante_arquivo a where a.comprovante_id = v_c.id
                          order by a.id limit 1),
        'origem_classificacao', v_c.origem_classificacao, 'valor', v_c.valor,
        'data_documento', coalesce(v_c.data_documento, v_c.created_at::date,
                                   (now() at time zone 'America/Sao_Paulo')::date),
        'imagens', financeiro.imagens_patrimonio());
end
$$;

-- =====================================================================================================================
-- Privilegios
-- =====================================================================================================================

revoke execute on function financeiro.repeticao_patrimonio(uuid, integer, text) from public, anon, authenticated;
revoke execute on function financeiro.registrar_operacao_patrimonio(uuid, integer, text, jsonb) from public, anon, authenticated;
revoke execute on function financeiro.valor_patrimonio(jsonb, text) from public, anon, authenticated;
revoke execute on function financeiro.travar_caixinha(integer, integer) from public, anon, authenticated;
revoke execute on function financeiro.ler_dados_caixinha(integer, integer, jsonb, boolean) from public, anon, authenticated;
revoke execute on function financeiro.travar_contas_transferencia(integer, integer) from public, anon, authenticated;
revoke execute on function financeiro.exigir_perfil_empresa(integer) from public, anon, authenticated;
revoke execute on function financeiro.texto_bem(text, integer) from public, anon, authenticated;
revoke execute on function financeiro.decimal_bem(text) from public, anon, authenticated;
revoke execute on function financeiro.inteiro_bem(jsonb) from public, anon, authenticated;
revoke execute on function financeiro.data_bem(text) from public, anon, authenticated;
revoke execute on function financeiro.opcao_bem(text, text[], text) from public, anon, authenticated;
revoke execute on function financeiro.imagem_bem(text) from public, anon, authenticated;
revoke execute on function financeiro.aplicar_dados_bem(public.bem_patrimonial, jsonb, boolean) from public, anon, authenticated;
revoke execute on function financeiro.depreciacao_bem(numeric, integer) from public, anon, authenticated;
revoke execute on function financeiro.travar_bem(integer, integer) from public, anon, authenticated;
revoke execute on function financeiro.travar_documento_patrimonio(integer, integer) from public, anon, authenticated;
revoke execute on function financeiro.vincular_documento_ao_bem(integer, integer, integer, jsonb) from public, anon, authenticated;
revoke execute on function financeiro.inserir_bem(integer, jsonb) from public, anon, authenticated;
revoke execute on function financeiro.documento_patrimonio_flask(public.ir_comprovante) from public, anon, authenticated;

revoke execute on function financeiro.criar_caixinha(integer, jsonb, uuid) from public, anon;
revoke execute on function financeiro.editar_caixinha(integer, integer, jsonb) from public, anon;
revoke execute on function financeiro.inativar_caixinha(integer, integer) from public, anon;
revoke execute on function financeiro.criar_transferencia_patrimonio(integer, jsonb, uuid) from public, anon;
revoke execute on function financeiro.excluir_transferencia_patrimonio(integer, integer) from public, anon;
revoke execute on function financeiro.criar_bem_patrimonial(integer, jsonb, uuid) from public, anon;
revoke execute on function financeiro.criar_bem_de_documento(integer, jsonb, uuid) from public, anon;
revoke execute on function financeiro.editar_bem_patrimonial(integer, integer, jsonb) from public, anon;
revoke execute on function financeiro.vincular_documento_bem(integer, integer, jsonb) from public, anon;
revoke execute on function financeiro.excluir_bem_patrimonial(integer, integer) from public, anon;
revoke execute on function financeiro.patrimonio_documentos_vinculaveis_tela(integer, text) from public, anon;
revoke execute on function financeiro.patrimonio_documento_sugestao_tela(integer, integer) from public, anon;
grant execute on function financeiro.criar_caixinha(integer, jsonb, uuid) to authenticated;
grant execute on function financeiro.editar_caixinha(integer, integer, jsonb) to authenticated;
grant execute on function financeiro.inativar_caixinha(integer, integer) to authenticated;
grant execute on function financeiro.criar_transferencia_patrimonio(integer, jsonb, uuid) to authenticated;
grant execute on function financeiro.excluir_transferencia_patrimonio(integer, integer) to authenticated;
grant execute on function financeiro.criar_bem_patrimonial(integer, jsonb, uuid) to authenticated;
grant execute on function financeiro.criar_bem_de_documento(integer, jsonb, uuid) to authenticated;
grant execute on function financeiro.editar_bem_patrimonial(integer, integer, jsonb) to authenticated;
grant execute on function financeiro.vincular_documento_bem(integer, integer, jsonb) to authenticated;
grant execute on function financeiro.excluir_bem_patrimonial(integer, integer) to authenticated;
grant execute on function financeiro.patrimonio_documentos_vinculaveis_tela(integer, text) to authenticated;
grant execute on function financeiro.patrimonio_documento_sugestao_tela(integer, integer) to authenticated;
