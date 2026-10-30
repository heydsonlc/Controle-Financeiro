-- Reversao de 20261203090000: devolve inferir_documento_empresa e metadata_empresarial_flask ao texto de 20261202090000
-- (byte a byte, CRLF, como foram aplicadas). Nao toca em dados. So com autorizacao, retirando a versao de
-- supabase_migrations.schema_migrations.

-- Classificacao automatica do documento sem metadados: so sugere com evidencia; sem ela, OUTRO / SEM_CATEGORIA
-- ("Nao classificado"). Palavras inteiras, sem acento. Documento-base (societario, procuracao, certidao) antes de
-- pagamento, e pagamento so com sinal de transacao (comprovante, transacao, linha digitavel...). Interna.
create or replace function financeiro.inferir_documento_empresa(p_c public.ir_comprovante)
    returns text[]
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_nat text;
    v_t   text;
begin
    select upper(coalesce(ic.natureza, '')) into v_nat from public.ir_categoria ic where ic.id = p_c.categoria_ir_id;
    v_nat := coalesce(v_nat, '');
    if v_nat = 'PATRIMONIO_IMOBILIZADO' then return array['PATRIMONIO_IMOBILIZADO', 'NOTA_BEM_PATRIMONIAL']; end if;
    if v_nat in ('IMPOSTO_TAXA', 'DOCUMENTO_CONTABIL') then return array['CONTABIL_FISCAL', 'GUIA_TAXA_PAGA']; end if;
    if v_nat in ('DESPESA_OPERACIONAL', 'SOFTWARE_ASSINATURA', 'DOCUMENTO_FISCAL') then
        return array['NOTA_FISCAL_RECEBIDA', 'DESPESA_OPERACIONAL'];
    end if;
    v_t := ' ' || btrim(regexp_replace(financeiro.texto_sem_acento(concat_ws(' ', p_c.prestador_nome, p_c.observacoes, p_c.texto_extraido)),
                                       '[^a-z0-9]+', ' ', 'g')) || ' ';
    if strpos(v_t, ' contrato social ') > 0 or strpos(v_t, ' ato constitutivo ') > 0 then
        return array['DOCUMENTO_SOCIETARIO', 'CONTRATO_SOCIAL'];
    elsif strpos(v_t, ' alteracao contratual ') > 0 then
        return array['DOCUMENTO_SOCIETARIO', 'ALTERACAO_CONTRATUAL'];
    elsif strpos(v_t, ' comprovante de inscricao e de situacao cadastral ') > 0 or strpos(v_t, ' cartao cnpj ') > 0 then
        return array['DOCUMENTO_SOCIETARIO', 'CARTAO_CNPJ'];
    elsif strpos(v_t, ' procuracao ') > 0 then
        return array['PROCURACAO_REPRESENTACAO', 'REPRESENTACAO_LEGAL'];
    elsif strpos(v_t, ' alvara de funcionamento ') > 0 then
        return array['DOCUMENTO_OBRIGATORIO', 'ALVARA_FUNCIONAMENTO'];
    elsif strpos(v_t, ' certidao ') > 0 then
        return array['CERTIDAO_LICENCA', 'SEM_CATEGORIA'];
    elsif strpos(v_t, ' pix ') > 0 and (strpos(v_t, ' comprovante ') > 0 or strpos(v_t, ' transacao ') > 0
                                         or strpos(v_t, ' pix enviado ') > 0 or strpos(v_t, ' pagamento realizado ') > 0
                                         or v_t ~ ' (pago|pagamento) (via|com|por) pix ') then
        return array['PAGAMENTO_REALIZADO', 'PIX_PAGO'];
    elsif strpos(v_t, ' boleto ') > 0 and (strpos(v_t, ' linha digitavel ') > 0 or strpos(v_t, ' comprovante de pagamento ') > 0
                                            or strpos(v_t, ' pagamento efetuado ') > 0) then
        return array['PAGAMENTO_REALIZADO', 'BOLETO_PAGO'];
    elsif strpos(v_t, ' comprovante de pagamento ') > 0 or strpos(v_t, ' comprovante de transferencia ') > 0 then
        return array['PAGAMENTO_REALIZADO', 'COMPROVANTE_BANCARIO'];
    elsif strpos(v_t, ' contrato ') > 0 then
        return array['CONTRATO_INSTRUMENTO', 'SEM_CATEGORIA'];
    end if;
    return array['OUTRO', 'SEM_CATEGORIA'];
end
$$;

-- Metadados persistidos ou inferidos: texto de 20261113090000 com a inferencia trocada e os campos marcados.
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
    v_inf    text[];
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
        -- FIN-MIGRACAO-LASTRO-EMPRESA-01: inferencia segura (inferir_documento_empresa); antes, "pix" em qualquer parte do
        -- texto vencia "contrato" e o contrato social virava Pagamento realizado / Pix pago.
        v_inf := financeiro.inferir_documento_empresa(p_c);
        v_tipo := v_inf[1]; v_cat := v_inf[2];
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
        -- FIN-MIGRACAO-LASTRO-EMPRESA-01: sem metadados e sem reconhecimento seguro = "Nao classificado" (nao um palpite).
        'tipo_documental_label', case when v_d ->> 'origem_documental' = 'INFERIDO' and v_tipo = 'OUTRO' and v_cat = 'SEM_CATEGORIA'
                                      then 'Não classificado' else
                                 coalesce((select x ->> 'rotulo' from jsonb_array_elements(v_tax -> 'tipos_documentais') x
                                            where x ->> 'codigo' = v_tipo limit 1), 'Outro') end,
        'categoria_documental_label', case when v_d ->> 'origem_documental' = 'INFERIDO' and v_tipo = 'OUTRO' and v_cat = 'SEM_CATEGORIA'
                                           then 'Não classificado' else
                                      coalesce((select x ->> 'rotulo' from jsonb_array_elements(v_tax -> 'categorias_documentais') x
                                                 where x ->> 'codigo' = v_cat limit 1), 'Sem categoria') end,
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
