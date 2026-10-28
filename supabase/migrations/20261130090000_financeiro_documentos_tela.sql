-- FIN-PRE-PRODUCAO-1 (2.2) — Documentos: as leituras que a tela original ainda nao alcancava e a regra do titular
-- "um documento pode ser vinculado a varios bens".
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261130090000).
-- Depende de 20261113090000 (leitura de Documentos), 20261105090000 (sugestao_categoria_importacao), 20261126090000
-- (Patrimonio) e 20261128090000 (escrita de Documentos). Validada em cluster local descartavel
-- (tests/test_supabase_documentos_tela.py, comparada com o Flask). Docs: docs/FIN_PRE_PRODUCAO_1.md.
--
-- Leituras novas (rotas de routes/ir.py, mesmo formato do Flask):
-- - entidades_vinculaveis_tela: GET /entidades-vinculaveis (DocumentoFiscalService.listar_entidades_vinculaveis);
-- - vinculos_documento_tela: GET /comprovantes/<id>/vinculos (vinculos ativos, mais recentes primeiro);
-- - lastro_resumo_tela: GET /lastro/resumo (IrDocumentoService.resumo_lastro);
-- - sugestao_financeira_documento_tela: GET /comprovantes/<id>/sugestao-financeira
--   (DocumentoFinanceiroSugestaoService.gerar_sugestao: categoria do documento ou por palavra-chave no texto extraido,
--   categoria IR, descricao, data, avisos e opcoes).
-- GET /comprovantes/documentos-para-financeiro usa a leitura existente (ir_comprovantes_tela) no adaptador.
--
-- Regra do titular (FIN-PRE-PRODUCAO-1): um documento pode ser vinculado a varios bens. A rota generica do Flask
-- (POST /api/ir/comprovantes/<id>/vinculos) ja permitia; a tela de Patrimonio do Flask recusava. Redefinidas, com o
-- texto anterior e so a recusa removida: criar_vinculo_documento (20261128090000), vincular_documento_ao_bem,
-- criar_bem_de_documento e patrimonio_documentos_vinculaveis_tela (20261126090000). Um bem continua com um documento
-- ativo (o vinculo anterior DO BEM e desativado, nunca apagado), como antes.
-- Nenhuma tabela nova. Nenhum dado existente e alterado.

-- GET /api/ir/entidades-vinculaveis?tipo&busca: 25 mais recentes do perfil, por tipo.
create function financeiro.entidades_vinculaveis_tela(p_perfil_id integer, p_tipo text, p_busca text)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_tipo  text := upper(btrim(coalesce(nullif(p_tipo, ''), 'OUTRO')));
    v_termo text := nullif(btrim(coalesce(p_busca, '')), '');
    v_like  text;
    v_lista jsonb;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if v_tipo not in ('CONTA', 'DESPESA_PREVISTA', 'LANCAMENTO', 'MOVIMENTO_FINANCEIRO', 'PATRIMONIO', 'FINANCIAMENTO') then
        return '[]'::jsonb;
    end if;
    v_like := '%' || v_termo || '%';
    if v_tipo = 'CONTA' then
        select jsonb_agg(jsonb_build_object('id', x.id, 'tipo_entidade', v_tipo,
                   'label', coalesce(x.nome, 'None') || ' - ' || coalesce(x.instituicao, 'None'), 'valor', x.saldo_atual, 'data', null)
                   order by x.id desc) into v_lista
          from (select c.* from public.conta_bancaria c
                 where financeiro.pertence_ao_perfil(c.perfil_financeiro_id, p_perfil_id)
                   and (v_termo is null or c.nome ilike v_like) order by c.id desc limit 25) x;
    elsif v_tipo = 'DESPESA_PREVISTA' then
        select jsonb_agg(jsonb_build_object('id', x.id, 'tipo_entidade', v_tipo,
                   'label', coalesce(x.origem_tipo, 'None') || ' - ' || coalesce(x.status, 'None'), 'valor', x.valor_previsto,
                   'data', x.data_prevista) order by x.id desc) into v_lista
          from (select d.* from public.despesa_prevista d
                 where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id)
                   and (v_termo is null or d.origem_tipo ilike v_like or d.status ilike v_like) order by d.id desc limit 25) x;
    elsif v_tipo = 'LANCAMENTO' then
        select jsonb_agg(jsonb_build_object('id', x.id, 'tipo_entidade', v_tipo, 'label', x.descricao, 'valor', x.valor,
                   'data', x.data_compra) order by x.id desc) into v_lista
          from (select l.* from public.lancamento_agregado l
                 where financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id)
                   and (v_termo is null or l.descricao ilike v_like) order by l.id desc limit 25) x;
    elsif v_tipo = 'MOVIMENTO_FINANCEIRO' then
        select jsonb_agg(jsonb_build_object('id', x.id, 'tipo_entidade', v_tipo, 'label', x.descricao, 'valor', x.valor,
                   'data', x.data_movimento) order by x.id desc) into v_lista
          from (select m.* from public.movimento_financeiro m
                 where financeiro.pertence_ao_perfil(m.perfil_financeiro_id, p_perfil_id)
                   and (v_termo is null or m.descricao ilike v_like) order by m.id desc limit 25) x;
    elsif v_tipo = 'PATRIMONIO' then
        select jsonb_agg(jsonb_build_object('id', x.id, 'tipo_entidade', v_tipo, 'label', x.nome, 'valor', x.valor_aquisicao,
                   'data', x.data_aquisicao) order by x.id desc) into v_lista
          from (select b.* from public.bem_patrimonial b
                 where financeiro.pertence_ao_perfil(b.perfil_financeiro_id, p_perfil_id)
                   and (v_termo is null or b.nome ilike v_like) order by b.id desc limit 25) x;
    else
        select jsonb_agg(jsonb_build_object('id', x.id, 'tipo_entidade', v_tipo, 'label', x.nome, 'valor', x.valor_financiado,
                   'data', x.data_contrato) order by x.id desc) into v_lista
          from (select f.* from public.financiamento f
                 where financeiro.pertence_ao_perfil(f.perfil_financeiro_id, p_perfil_id)
                   and (v_termo is null or f.nome ilike v_like) order by f.id desc limit 25) x;
    end if;
    return coalesce(v_lista, '[]'::jsonb);
end
$$;

-- GET /api/ir/comprovantes/<id>/vinculos: vinculos ativos (IrComprovanteVinculo.to_dict), mais recentes primeiro.
create function financeiro.vinculos_documento_tela(p_perfil_id integer, p_comprovante_id integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_c public.ir_comprovante;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    select * into v_c from public.ir_comprovante c where c.id = p_comprovante_id;
    if not found or not financeiro.pertence_ao_perfil(v_c.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Comprovante nao encontrado' using errcode = '22023', hint = 'NAO_ENCONTRADA';
    end if;
    return coalesce((
        select jsonb_agg(jsonb_build_object(
                   'id', v.id, 'comprovante_id', v.comprovante_id, 'perfil_financeiro_id', v.perfil_financeiro_id,
                   'tipo_entidade', v.tipo_entidade, 'entidade_id', v.entidade_id, 'resumo_entidade', v.resumo_entidade,
                   'tipo_vinculo', v.tipo_vinculo, 'natureza', v.natureza, 'status_lastro', v.status_lastro,
                   'observacoes', v.observacoes, 'ativo', coalesce(v.ativo, false),
                   'created_at', financeiro.iso_python(v.created_at), 'updated_at', financeiro.iso_python(v.updated_at))
                   order by v.created_at desc, v.id desc)
          from public.ir_comprovante_vinculo v
         where v.comprovante_id = v_c.id and v.ativo), '[]'::jsonb);
end
$$;

-- GET /api/ir/lastro/resumo?ano: documentos do perfil (do ano), com e sem vinculo ativo.
create function financeiro.lastro_resumo_tela(p_perfil_id integer, p_ano text)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_ano integer;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if btrim(coalesce(p_ano, '')) ~ '^[+-]?\d{1,9}$' then
        v_ano := nullif(btrim(p_ano)::integer, 0);
    end if;
    return (
        select jsonb_build_object(
                   'total_documentos', count(*),
                   'documentos_vinculados', count(*) filter (where x.status_lastro is not null),
                   'documentos_sem_vinculo', count(*) filter (where x.status_lastro is null),
                   'valor_com_lastro', coalesce(sum(coalesce(x.valor, 0)) filter (where x.status_lastro is not null), 0),
                   'valor_sem_lastro', coalesce(sum(coalesce(x.valor, 0)) filter (where x.status_lastro is null), 0),
                   'documentos_aguardando_contador', count(*) filter (where x.status_lastro = 'AGUARDANDO_CONTADOR'))
          from (select c.valor,
                       (select v.status_lastro from public.ir_comprovante_vinculo v
                         where v.comprovante_id = c.id and v.ativo order by v.id limit 1) as status_lastro
                  from public.ir_comprovante c
                 where financeiro.pertence_ao_perfil(c.perfil_financeiro_id, p_perfil_id)
                   and (v_ano is null or c.ano_calendario = v_ano)) x);
end
$$;

-- CategoriaPalavraChaveService.normalizar_descricao_importacao: minusculas, sem acento, so letras/numeros/espacos. Interna.
create function financeiro.doc_texto_classificacao(p_texto text)
    returns text
    language sql
    immutable
    set search_path = ''
as $$
    select btrim(regexp_replace(regexp_replace(
        translate(lower(btrim(coalesce(p_texto, ''))), 'áàâãäéèêëíìîïóòôõöúùûüçñ', 'aaaaaeeeeiiiiooooouuuucn'),
        '[^[:alnum:]_[:space:]]', ' ', 'g'), '[[:space:]]+', ' ', 'g'))
$$;

-- GET /api/ir/comprovantes/<id>/sugestao-financeira (DocumentoFinanceiroSugestaoService.gerar_sugestao).
create function financeiro.sugestao_financeira_documento_tela(p_perfil_id integer, p_comprovante_id integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_c         public.ir_comprovante;
    v_info      jsonb;
    v_cat_id    integer;
    v_origem    text;
    v_avisos    text[] := '{}';
    v_cat       public.categoria;
    v_tem_cat   boolean := false;
    v_cat_ir    public.ir_categoria;
    v_tem_ir    boolean := false;
    v_texto     text;
    v_data      date;
    v_valor     numeric;
    v_ocr       boolean;
    v_cupom     boolean;
    v_arquivo   text;
    v_forn      text;
    v_desc      text;
    v_obs       text;
    v_final     jsonb := '[]'::jsonb;
    v_aviso     text;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    select * into v_c from public.ir_comprovante c where c.id = p_comprovante_id;
    if not found or not financeiro.pertence_ao_perfil(v_c.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Comprovante nao encontrado' using errcode = '22023', hint = 'NAO_ENCONTRADA';
    end if;
    -- _resolver_categoria_sugerida: a do documento; sem ela, palavra-chave no texto extraido.
    if v_c.categoria_id is not null then
        v_cat_id := v_c.categoria_id;
        v_origem := coalesce(v_c.origem_classificacao, 'comprovante');
    else
        v_texto := financeiro.doc_texto_classificacao(v_c.texto_extraido);
        if v_texto = '' then
            v_origem := 'sem_sugestao';
            v_avisos := v_avisos || 'Nenhuma palavra-chave encontrada.'::text;
        else
            v_info := financeiro.sugestao_categoria_importacao(p_perfil_id, v_texto, null, null);
            v_cat_id := (v_info ->> 'categoria_id')::integer;
            v_origem := v_info ->> 'origem';
            v_avisos := v_avisos || (case when v_origem = 'sem_sugestao' then 'Nenhuma palavra-chave encontrada.'
                                          else v_info ->> 'aviso' end)::text;
        end if;
    end if;
    -- _obter_categoria(obrigatoria=False): inexistente ou inativa e erro, como o Flask.
    if v_cat_id is not null then
        select * into v_cat from public.categoria c where c.id = v_cat_id;
        if not found or not coalesce(v_cat.ativo, false) then
            raise exception 'Categoria de Despesa nao encontrada' using errcode = '22023';
        end if;
        v_tem_cat := true;
    end if;
    -- _resolver_categoria_ir: a do documento; sem ela, o vinculo ativo da categoria no perfil.
    if v_c.categoria_ir_id is not null then
        select * into v_cat_ir from public.ir_categoria i where i.id = v_c.categoria_ir_id;
        v_tem_ir := found;
    elsif v_cat_id is not null then
        select i.* into v_cat_ir from public.ir_categoria_despesa d join public.ir_categoria i on i.id = d.categoria_ir_id
         where d.categoria_id = v_cat_id and d.ativo and financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id)
         order by d.id limit 1;
        v_tem_ir := found;
    end if;
    v_data := coalesce(v_c.data_documento, v_c.created_at::date, financeiro.hoje_brasilia());
    v_valor := coalesce(v_c.valor, 0);
    v_ocr := exists (select 1 from public.ir_comprovante_evento e where e.comprovante_id = v_c.id
                        and upper(coalesce(e.tipo_evento, '')) in ('OCR_EXECUTADO', 'TEXTO_EXTRAIDO_OCR', 'OCR_LIMITADO'));
    v_cupom := exists (select 1 from public.ir_comprovante_evento e where e.comprovante_id = v_c.id
                          and e.tipo_evento = 'CUPOM_FISCAL_DETECTADO');
    select a.nome_arquivo into v_arquivo from public.ir_comprovante_arquivo a where a.comprovante_id = v_c.id order by a.id limit 1;
    if not v_tem_cat then
        v_avisos := v_avisos || 'Categoria de Despesa nao identificada. Selecione manualmente.'::text;
    end if;
    if v_valor <= 0 then
        v_avisos := v_avisos || 'Valor nao identificado automaticamente.'::text;
    end if;
    if v_ocr then
        v_avisos := v_avisos || 'Sugestao gerada a partir de texto extraido por OCR. Revise os dados antes de confirmar.'::text;
    end if;
    if v_tem_cat and not v_tem_ir then
        v_avisos := v_avisos || 'Categoria de Despesa sem vinculo com Categoria IR/Fiscal.'::text;
    end if;
    foreach v_aviso in array v_avisos loop  -- _deduplicar: na ordem, sem vazios nem repetidos
        v_aviso := btrim(coalesce(v_aviso, ''));
        if v_aviso <> '' and not v_final ? v_aviso then
            v_final := v_final || to_jsonb(v_aviso);
        end if;
    end loop;
    -- _descricao_sugerida.
    v_forn := btrim(coalesce(v_c.prestador_nome, ''));
    if v_forn <> '' and v_tem_cat and not v_cupom then
        v_desc := v_forn || ' - ' || v_cat.nome;
    elsif v_forn <> '' then
        v_desc := v_forn || case when v_cupom then ' — Cupom fiscal' else '' end
                  || case when v_tem_cat then ' - ' || v_cat.nome else '' end;
    else
        v_desc := case when v_cupom then 'Cupom fiscal - ' else 'Documento fiscal - ' end
                  || coalesce(nullif(v_arquivo, ''), v_c.id::text);
    end if;
    v_desc := left(btrim(v_desc), 200);
    -- _observacoes_sugeridas.
    v_obs := 'Criado a partir de sugestao financeira revisada de documento fiscal.'
             || case when nullif(v_arquivo, '') is not null then ' Documento: ' || v_arquivo || '.' else '' end
             || case when nullif(v_c.prestador_cpf_cnpj, '') is not null then ' CPF/CNPJ prestador: ' || v_c.prestador_cpf_cnpj || '.' else '' end
             || case when v_ocr then ' Texto de origem extraido por OCR local.' else '' end;
    return jsonb_build_object(
        'comprovante_id', v_c.id,
        'documento', jsonb_build_object('id', v_c.id, 'nome_arquivo', v_arquivo, 'prestador_nome', v_c.prestador_nome,
                                        'prestador_cpf_cnpj', v_c.prestador_cpf_cnpj,
                                        'origem_texto', case when v_ocr then 'OCR' else 'PDF_TEXTUAL' end),
        'tipo_destino_sugerido', 'DESPESA',
        'descricao', v_desc,
        'valor', v_valor,
        'data', to_char(v_data, 'YYYY-MM-DD'),
        'competencia', to_char(v_data, 'YYYY-MM'),
        'fornecedor', v_c.prestador_nome,
        'cpf_cnpj', v_c.prestador_cpf_cnpj,
        'categoria_id', case when v_tem_cat then v_cat.id end,
        'categoria_nome', case when v_tem_cat then v_cat.nome end,
        'categoria_origem', coalesce(v_origem, v_c.origem_classificacao),
        'categoria_ir_id', case when v_tem_ir then v_cat_ir.id end,
        'categoria_ir_nome', case when v_tem_ir then v_cat_ir.nome end,
        'forma_pagamento', 'outros',
        'observacoes', left(v_obs, 1000),
        'avisos', v_final,
        'opcoes', jsonb_build_object(
            'tipos_destino', '[{"key": "DESPESA", "nome": "Despesa prevista"}, {"key": "LANCAMENTO", "nome": "Lancamento realizado"}]'::jsonb,
            'formas_pagamento', '[{"key": "pix", "nome": "Pix"}, {"key": "dinheiro", "nome": "Dinheiro"}, {"key": "cartao", "nome": "Cartao"}, {"key": "boleto", "nome": "Boleto"}, {"key": "transferencia", "nome": "Transferencia"}, {"key": "debito_automatico", "nome": "Debito automatico"}, {"key": "outros", "nome": "Outros / Nao informado"}]'::jsonb,
            'categorias_despesa', financeiro.ir_categorias_despesa_tela(p_perfil_id, true)));
end
$$;

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
    -- FIN-PRE-PRODUCAO-1: um documento pode estar em varios bens (recusa removida); o vinculo anterior DESTE bem
    -- continua desativado (um bem, um documento ativo, como antes).
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
    -- FIN-PRE-PRODUCAO-1: o mesmo documento pode originar varios bens (nota com varios itens; recusa removida).
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
                   -- FIN-PRE-PRODUCAO-1: documento ja ligado a um bem continua vinculavel a outro.
                   and (v_termo is null or c.prestador_nome ilike '%' || v_termo || '%'
                        or c.prestador_cpf_cnpj ilike '%' || v_termo || '%' or c.observacoes ilike '%' || v_termo || '%'
                        or c.hash_arquivo ilike '%' || v_termo || '%')
                 order by c.data_documento desc nulls first, c.id desc
                 limit 50) x), '[]'::jsonb);
end
$$;
revoke execute on function financeiro.doc_texto_classificacao(text) from public, anon, authenticated;
revoke execute on function financeiro.entidades_vinculaveis_tela(integer, text, text) from public, anon;
revoke execute on function financeiro.vinculos_documento_tela(integer, integer) from public, anon;
revoke execute on function financeiro.lastro_resumo_tela(integer, text) from public, anon;
revoke execute on function financeiro.sugestao_financeira_documento_tela(integer, integer) from public, anon;
grant execute on function financeiro.entidades_vinculaveis_tela(integer, text, text) to authenticated;
grant execute on function financeiro.vinculos_documento_tela(integer, integer) to authenticated;
grant execute on function financeiro.lastro_resumo_tela(integer, text) to authenticated;
grant execute on function financeiro.sugestao_financeira_documento_tela(integer, integer) to authenticated;
