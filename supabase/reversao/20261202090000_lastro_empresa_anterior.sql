-- Reversao de 20261202090000 (FIN-MIGRACAO-LASTRO-EMPRESA-01): devolve as quatro funcoes redefinidas ao texto anterior e
-- remove as novas. Nao apaga dados: metadados empresariais, vinculos e pendencias gravados pelas funcoes novas ficam. Depois
-- da reversao, documento com metadados gravados volta a nao poder ser excluido (a exclusao anterior nao os apagava).
-- So com autorizacao (scripts/supabase_migrations.py), e retirando a versao de supabase_migrations.schema_migrations.

drop function if exists financeiro.salvar_metadata_empresarial(integer, integer, jsonb, uuid);
drop function if exists financeiro.vincular_saida_documento(integer, jsonb);
drop function if exists financeiro.marcar_status_saida(integer, jsonb);
drop function if exists financeiro.lastro_saida_entidade(integer, text, integer);
drop function if exists financeiro.exigir_documentos_empresa(integer);
drop function if exists financeiro.doc_data(text);

-- metadata_empresarial_flask e resumo_documentos_empresa: texto de 20261113090000.
create or replace function financeiro.metadata_empresarial_flask(p_c public.ir_comprovante)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_tax    jsonb := financeiro.taxonomia_documental();
    v_hoje   date := (now() at time zone 'America/Sao_Paulo')::date;
    v_m      public.documento_empresarial_metadata;
    v_d      jsonb;
    v_nat    text;
    v_txt    text;
    v_tipo   text;
    v_cat    text;
    v_val    date;
    v_status text;
    v_arq    text;
begin
    select * into v_m from public.documento_empresarial_metadata m where m.comprovante_id = p_c.id order by m.id limit 1;
    if found then
        v_d := jsonb_build_object(
            'id', v_m.id, 'comprovante_id', v_m.comprovante_id, 'perfil_financeiro_id', v_m.perfil_financeiro_id,
            'tipo_documental', v_m.tipo_documental, 'categoria_documental', v_m.categoria_documental, 'subtipo', v_m.subtipo,
            'numero_documento', v_m.numero_documento, 'orgao_emissor', v_m.orgao_emissor, 'data_emissao', v_m.data_emissao,
            'data_validade', v_m.data_validade, 'status_documental', v_m.status_documental,
            'obrigatorio', coalesce(v_m.obrigatorio, false), 'renovavel', coalesce(v_m.renovavel, false),
            'alerta_dias_antes', v_m.alerta_dias_antes, 'responsavel_interno', v_m.responsavel_interno,
            'origem_documental', v_m.origem_documental, 'tags', v_m.tags, 'observacoes', v_m.observacoes,
            'created_at', financeiro.iso_python(v_m.created_at), 'updated_at', financeiro.iso_python(v_m.updated_at));
    else
        -- _inferir_tipo_categoria: natureza da categoria IR, depois palavras do texto.
        select upper(coalesce(ic.natureza, '')) into v_nat from public.ir_categoria ic where ic.id = p_c.categoria_ir_id;
        v_nat := coalesce(v_nat, '');
        v_txt := lower(concat_ws(' ', coalesce(p_c.prestador_nome, ''), coalesce(p_c.observacoes, ''), coalesce(p_c.texto_extraido, '')));
        if v_nat = 'PATRIMONIO_IMOBILIZADO' then
            v_tipo := 'PATRIMONIO_IMOBILIZADO'; v_cat := 'NOTA_BEM_PATRIMONIAL';
        elsif v_nat in ('IMPOSTO_TAXA', 'DOCUMENTO_CONTABIL') then
            v_tipo := 'CONTABIL_FISCAL'; v_cat := 'GUIA_TAXA_PAGA';
        elsif v_nat in ('DESPESA_OPERACIONAL', 'SOFTWARE_ASSINATURA', 'DOCUMENTO_FISCAL') then
            v_tipo := 'NOTA_FISCAL_RECEBIDA'; v_cat := 'DESPESA_OPERACIONAL';
        elsif strpos(v_txt, 'pix') > 0 then
            v_tipo := 'PAGAMENTO_REALIZADO'; v_cat := 'PIX_PAGO';
        elsif strpos(v_txt, 'boleto') > 0 then
            v_tipo := 'PAGAMENTO_REALIZADO'; v_cat := 'BOLETO_PAGO';
        elsif strpos(v_txt, 'contrato') > 0 then
            v_tipo := 'CONTRATO_INSTRUMENTO'; v_cat := 'CONTRATO_FORNECEDOR';
        else
            v_tipo := 'OUTRO'; v_cat := 'SEM_CATEGORIA';
        end if;
        v_d := jsonb_build_object(
            'id', null, 'comprovante_id', p_c.id, 'perfil_financeiro_id', p_c.perfil_financeiro_id, 'tipo_documental', v_tipo,
            'categoria_documental', v_cat, 'subtipo', null, 'numero_documento', null, 'orgao_emissor', null,
            'data_emissao', p_c.data_documento, 'data_validade', null, 'status_documental', 'ATIVO', 'obrigatorio', false,
            'renovavel', false, 'alerta_dias_antes', 30, 'responsavel_interno', null, 'origem_documental', 'INFERIDO',
            'tags', null, 'observacoes', null, 'created_at', null, 'updated_at', null);
    end if;
    v_tipo := v_d ->> 'tipo_documental';
    v_cat := v_d ->> 'categoria_documental';
    v_val := (v_d ->> 'data_validade')::date;
    v_status := case
        when (v_d ->> 'obrigatorio')::boolean and not (coalesce(v_tipo, '') <> '' and coalesce(v_cat, '') <> '') then 'PENDENTE'
        when v_val is not null then case when v_val < v_hoje then 'VENCIDO' when v_val - v_hoje <= 30 then 'VENCENDO' else 'VALIDO' end
        when upper(btrim(coalesce(v_d ->> 'status_documental', ''))) in ('PENDENTE', 'EM_REVISAO', 'AGUARDANDO_CONTADOR',
                                                                          'SEM_LASTRO', 'COM_LASTRO', 'NAO_APLICAVEL', 'ARQUIVADO')
            then upper(btrim(v_d ->> 'status_documental'))
        else 'ATIVO' end;
    select a.nome_arquivo into v_arq from public.ir_comprovante_arquivo a where a.comprovante_id = p_c.id order by a.id limit 1;
    return v_d || jsonb_build_object(
        'status_documental', v_status,
        'tipo_documental_label', coalesce((select x ->> 'rotulo' from jsonb_array_elements(v_tax -> 'tipos_documentais') x
                                            where x ->> 'codigo' = v_tipo limit 1), 'Outro'),
        'categoria_documental_label', coalesce((select x ->> 'rotulo' from jsonb_array_elements(v_tax -> 'categorias_documentais') x
                                                 where x ->> 'codigo' = v_cat limit 1), 'Sem categoria'),
        'status_documental_label', coalesce((select x ->> 'rotulo' from jsonb_array_elements(v_tax -> 'status_documentais') x
                                              where x ->> 'codigo' = v_status limit 1), 'Ativo'),
        'icone', case
            when upper(coalesce(v_cat, '')) = 'CERTIFICADO_BOMBEIROS' then 'shield'
            when upper(coalesce(v_cat, '')) = 'USO_DO_SOLO' then 'home'
            when upper(coalesce(v_cat, '')) in ('CONTRATO_SOCIAL', 'ALTERACAO_CONTRATUAL', 'CARTAO_CNPJ', 'QUADRO_SOCIETARIO') then 'briefcase'
            when upper(coalesce(v_cat, '')) like 'PROCURACAO%'
                 or upper(coalesce(v_cat, '')) in ('REPRESENTACAO_LEGAL', 'AUTORIZACAO_ADMINISTRATIVA') then 'briefcase'
            when upper(coalesce(v_tipo, '')) = 'PAGAMENTO_REALIZADO' then 'cash'
            when upper(coalesce(v_tipo, '')) in ('NOTA_FISCAL_RECEBIDA', 'NOTA_FISCAL_EMITIDA') then 'receipt'
            when upper(coalesce(v_tipo, '')) in ('DOCUMENTO_OBRIGATORIO', 'CERTIDAO_LICENCA') then 'shield'
            when upper(coalesce(v_tipo, '')) = 'CONTRATO_INSTRUMENTO' then 'book'
            when upper(coalesce(v_tipo, '')) = 'CONTABIL_FISCAL' then 'bank'
            when upper(coalesce(v_tipo, '')) = 'PATRIMONIO_IMOBILIZADO' then 'tool'
            else 'tag' end,
        'documento_label', coalesce(nullif(p_c.prestador_nome, ''), nullif(v_arq, ''), 'Documento #' || p_c.id));
end
$$;

create or replace function financeiro.resumo_documentos_empresa(p_perfil_id integer, p_f jsonb)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_ano       integer;
    v_c         public.ir_comprovante;
    v_md        jsonb;
    v_lastro    text;
    v_total     integer := 0;
    v_obrig     integer := 0;
    v_venc      integer := 0;
    v_sem       integer := 0;
    v_aguard    integer := 0;
    v_tipos     jsonb := '{}'::jsonb;
    v_check     jsonb := jsonb_build_object(
                    'CONTRATO_SOCIAL', jsonb_build_object('label', 'Contrato Social', 'status', 'pendente'),
                    'CARTAO_CNPJ', jsonb_build_object('label', 'CNPJ / Constituicao', 'status', 'pendente'),
                    'INSCRICAO_MUNICIPAL', jsonb_build_object('label', 'Inscricao Municipal', 'status', 'pendente'),
                    'CERTIFICADO_BOMBEIROS', jsonb_build_object('label', 'Certificado dos Bombeiros', 'status', 'pendente'));
    v_prox      jsonb := '[]'::jsonb;
    v_arq       text;
begin
    if btrim(coalesce(p_f ->> 'ano', '')) ~ '^[+-]?\d{1,9}$' then
        v_ano := nullif(btrim(p_f ->> 'ano')::integer, 0);
    end if;
    for v_c in select c.* from public.ir_comprovante c
                where financeiro.pertence_ao_perfil(c.perfil_financeiro_id, p_perfil_id)
                  and (v_ano is null or c.ano_calendario = v_ano) and financeiro.filtro_documento_empresa(c, p_f)
                order by c.created_at desc, c.id desc
    loop
        v_md := financeiro.metadata_empresarial_flask(v_c);
        select coalesce((select v.status_lastro from public.ir_comprovante_vinculo v
                          where v.comprovante_id = v_c.id and v.ativo order by v.created_at desc, v.id desc limit 1), 'SEM_DOCUMENTO')
          into v_lastro;
        v_total := v_total + 1;
        if not v_tipos ? (v_md ->> 'tipo_documental') then
            v_tipos := v_tipos || jsonb_build_object(v_md ->> 'tipo_documental', jsonb_build_object(
                'tipo_documental', v_md -> 'tipo_documental', 'rotulo', v_md -> 'tipo_documental_label', 'quantidade', 0,
                'icone', v_md -> 'icone', '_ordem', v_total));
        end if;
        v_tipos := jsonb_set(v_tipos, array[v_md ->> 'tipo_documental', 'quantidade'],
                             to_jsonb((v_tipos -> (v_md ->> 'tipo_documental') ->> 'quantidade')::integer + 1));
        if (v_md ->> 'obrigatorio')::boolean then v_obrig := v_obrig + 1; end if;
        if v_md ->> 'status_documental' = 'VENCENDO' then v_venc := v_venc + 1; end if;
        if v_lastro in ('SEM_DOCUMENTO', 'PENDENTE') then v_sem := v_sem + 1; end if;
        if v_lastro = 'AGUARDANDO_CONTADOR' or v_md ->> 'status_documental' = 'AGUARDANDO_CONTADOR' then v_aguard := v_aguard + 1; end if;
        if v_check ? (v_md ->> 'categoria_documental') then
            v_check := jsonb_set(v_check, array[v_md ->> 'categoria_documental', 'status'], to_jsonb(
                case when v_md ->> 'status_documental' in ('VENCIDO', 'VENCENDO', 'PENDENTE') then lower(v_md ->> 'status_documental')
                     else 'ok' end));
        end if;
        if v_md ->> 'data_validade' is not null then
            v_arq := null;
            select a.nome_arquivo into v_arq from public.ir_comprovante_arquivo a where a.comprovante_id = v_c.id order by a.id limit 1;
            v_prox := v_prox || jsonb_build_array(jsonb_build_object(
                'id', v_c.id, 'documento', coalesce(nullif(v_c.prestador_nome, ''), nullif(v_arq, ''), 'Documento #' || v_c.id),
                'categoria_documental', v_md -> 'categoria_documental',
                'categoria_documental_label', v_md -> 'categoria_documental_label',
                'data_validade', v_md -> 'data_validade', 'status_documental', v_md -> 'status_documental',
                '_ordem', jsonb_array_length(v_prox)));
        end if;
    end loop;
    return jsonb_build_object(
        'documentos_cadastrados', v_total, 'documentos_obrigatorios', v_obrig, 'vencendo_30_dias', v_venc,
        'sem_lastro', v_sem, 'aguardando_contador', v_aguard,
        -- sorted() do Python: ordem de codigo (collate "C"), estavel pela primeira aparicao.
        'distribuicao_por_tipo', coalesce((select jsonb_agg(x.value - '_ordem' order by (x.value ->> 'rotulo') collate "C",
                                                            (x.value ->> '_ordem')::integer)
                                             from jsonb_each(v_tipos) x), '[]'::jsonb),
        'proximos_vencimentos', coalesce((select jsonb_agg(y.value - '_ordem' order by y.ord)
                                            from (select p.value, row_number() over (order by p.value ->> 'data_validade',
                                                                                     (p.value ->> '_ordem')::integer) ord
                                                    from jsonb_array_elements(v_prox) p) y where y.ord <= 6), '[]'::jsonb),
        'checklist_empresarial', jsonb_build_array(v_check -> 'CONTRATO_SOCIAL', v_check -> 'CARTAO_CNPJ',
                                                   v_check -> 'INSCRICAO_MUNICIPAL', v_check -> 'CERTIFICADO_BOMBEIROS'));
end
$$;

-- excluir_comprovante: texto de 20261128090000.
create or replace function financeiro.excluir_comprovante(p_perfil_id integer, p_id integer)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_c public.ir_comprovante;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    v_c := financeiro.doc_comprovante(p_perfil_id, p_id);
    if exists (select 1 from public.ir_comprovante_vinculo v where v.comprovante_id = v_c.id) then
        raise exception 'O documento tem vinculos (lastro, despesa, bem ou historico). Remova os vinculos ativos; documentos com historico ficam preservados. Nada foi excluido.'
            using errcode = '22023', hint = 'COM_VINCULOS';
    end if;
    if v_c.status = 'VALIDADO' then
        raise exception 'Documento validado fica preservado. Nada foi excluido.' using errcode = '22023', hint = 'COM_HISTORICO';
    end if;
    delete from public.ir_comprovante_evento where comprovante_id = v_c.id;
    delete from public.ir_comprovante_arquivo where comprovante_id = v_c.id;
    delete from public.ir_comprovante where id = v_c.id;
    return jsonb_build_object('comprovante_id', v_c.id, 'excluido', true);
end
$$;

-- criar_vinculo_documento: texto de 20261130090000.
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
    -- FIN-PRE-PRODUCAO-1: regra do titular, um documento pode ser vinculado a varios bens (recusa removida).
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

drop function if exists financeiro.inferir_documento_empresa(public.ir_comprovante);
drop function if exists financeiro.documento_exige_lastro(text, text);
