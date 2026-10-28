-- Reversao de 20261130090000_financeiro_documentos_tela.sql (FIN-PRE-PRODUCAO-1): remove as leituras novas da tela
-- e devolve a regra "um documento, um bem" (textos originais de 20261126090000 e 20261128090000). Recusa se algum
-- documento ja estiver ativo em mais de um bem (a regra antiga deixaria esses vinculos inconsistentes).
do $$
begin
    if exists (select 1 from public.ir_comprovante_vinculo v where v.tipo_entidade = 'PATRIMONIO' and v.ativo
                group by v.comprovante_id having count(distinct v.entidade_id) > 1) then
        raise exception 'Reversao recusada: ha documento vinculado a mais de um bem (regra de FIN-PRE-PRODUCAO-1 em uso)';
    end if;
end
$$;

drop function if exists financeiro.sugestao_financeira_documento_tela(integer, integer);
drop function if exists financeiro.doc_texto_classificacao(text);
drop function if exists financeiro.lastro_resumo_tela(integer, text);
drop function if exists financeiro.vinculos_documento_tela(integer, integer);
drop function if exists financeiro.entidades_vinculaveis_tela(integer, text, text);

create or replace function financeiro.criar_vinculo_documento(p_perfil_id integer, p_comprovante_id integer, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_c    public.ir_comprovante;
    v_tipo text := financeiro.doc_opcao(p_dados ->> 'tipo_entidade',
        array['CONTA', 'DESPESA_PREVISTA', 'LANCAMENTO', 'MOVIMENTO_FINANCEIRO', 'PATRIMONIO', 'FINANCIAMENTO', 'OUTRO'], 'OUTRO');
    v_ent  jsonb;
    v_id   integer;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    v_c := financeiro.doc_comprovante(p_perfil_id, p_comprovante_id);
    v_ent := financeiro.doc_entidade(p_perfil_id, v_tipo, financeiro.mob_inteiro(p_dados -> 'entidade_id'));
    -- Correcao (regra do bem patrimonial, como a tela de Patrimonio e o novo aplicativo): um documento, um bem.
    if v_tipo = 'PATRIMONIO' and exists (select 1 from public.ir_comprovante_vinculo v
            where v.comprovante_id = v_c.id and v.tipo_entidade = 'PATRIMONIO' and v.ativo
              and v.entidade_id is distinct from (v_ent ->> 'id')::integer) then
        raise exception 'Documento fiscal ja esta vinculado a um bem patrimonial' using errcode = '22023';
    end if;
    insert into public.ir_comprovante_vinculo (comprovante_id, perfil_financeiro_id, tipo_entidade, entidade_id, resumo_entidade,
                                               tipo_vinculo, natureza, status_lastro, observacoes, ativo, created_at, updated_at)
    values (v_c.id, p_perfil_id, v_tipo, (v_ent ->> 'id')::integer, v_ent ->> 'resumo',
            financeiro.doc_opcao(p_dados ->> 'tipo_vinculo', array['COMPROVANTE', 'NOTA_FISCAL', 'RECIBO', 'CONTRATO', 'GUIA', 'DOCUMENTO_CONTABIL', 'OUTRO'], 'COMPROVANTE'),
            financeiro.doc_opcao(p_dados ->> 'natureza', array['DESPESA_OPERACIONAL', 'PATRIMONIO_IMOBILIZADO', 'SOFTWARE_ASSINATURA', 'IMPOSTO_TAXA',
                'PRO_LABORE', 'DISTRIBUICAO_LUCROS', 'REEMBOLSO', 'EMPRESTIMO', 'ADIANTAMENTO', 'OUTRO'], 'OUTRO'),
            financeiro.doc_opcao(p_dados ->> 'status_lastro', array['COM_DOCUMENTO', 'SEM_DOCUMENTO', 'PENDENTE', 'DIVERGENTE', 'VALIDADO',
                'NAO_APLICAVEL', 'AGUARDANDO_CONTADOR'], 'PENDENTE'),
            nullif(left(btrim(coalesce(p_dados ->> 'observacoes', '')), 1000), ''), true,
            (now() at time zone 'utc')::timestamp, (now() at time zone 'utc')::timestamp)
    returning id into v_id;
    return jsonb_build_object('vinculo_id', v_id);
end
$$;

create or replace function financeiro.vincular_documento_ao_bem(p_perfil_id integer, p_bem_id integer, p_comprovante_id integer,
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

create or replace function financeiro.criar_bem_de_documento(p_perfil_id integer, p_dados jsonb, p_chave uuid)
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

create or replace function financeiro.patrimonio_documentos_vinculaveis_tela(p_perfil_id integer, p_busca text)
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
