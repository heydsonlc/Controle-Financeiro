-- FIN-FIDELIDADE-DOCUMENTOS-1 (fase 1) — leitura da tela original de Imposto de Renda do Flask (modos IRPF e Documentos
-- da Empresa, so consulta).
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261113090000).
-- Depende de 20261112090000 (financeiro.iso_python) e 20261102090000 (financeiro.perfil_em_json).
-- Validada em cluster local descartavel (tests/test_supabase_documentos_fiscais_leitura.py, comparada com o Flask).
-- Docs: docs/FIN_FIDELIDADE_DOCUMENTOS_1.md.
--
-- Reproduz as rotas GET de routes/ir.py no formato do Flask (IrDocumentoService, to_dict dos modelos): contexto,
-- categorias IR, vinculos categoria de despesa -> categoria IR, categorias de despesa disponiveis, comprovantes (filtros
-- e resumo, com o lastro) e o detalhe (texto extraido e eventos); no perfil Empresa, tambem a taxonomia documental, os
-- metadados empresariais (persistidos ou inferidos, status pela validade), os filtros e o resumo empresariais.
-- Diferenca deliberada: o Flask CRIA as categorias IR iniciais ao ler /categorias e /contexto
-- (garantir_categorias_ir_iniciais / garantir_categorias_fiscais_empresa). Aqui a leitura nunca grava: as categorias
-- existentes sao lidas como estao (a semeadura fica com o Flask ou com migration de dados autorizada).
-- Fora desta fase (respondem "em migracao"): saidas sem documento (lastro_financeiro_service), download do arquivo,
-- exportacao ZIP, upload/OCR, edicao (inclusive dos metadados), validacao, vinculos e relatorios. Nenhuma tabela nova. Nenhum dado existente e alterado.

-- Tipo do perfil (PESSOAL ou EMPRESA: modo IRPF ou Documentos da Empresa), com a conferencia de acesso. Interna.
create function financeiro.tipo_perfil_ir(p_perfil_id integer)
    returns text
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_tipo text;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    select upper(coalesce(nullif(p.tipo, ''), 'PESSOAL')) into v_tipo from public.perfil_financeiro p where p.id = p_perfil_id;
    return coalesce(v_tipo, 'PESSOAL');
end
$$;

-- IrCategoria.to_dict. Interna.
create function financeiro.categoria_ir_flask(p_c public.ir_categoria)
    returns jsonb
    language sql
    stable
    set search_path = ''
as $$
    select jsonb_build_object('id', p_c.id, 'nome', p_c.nome, 'descricao', p_c.descricao, 'dedutivel', coalesce(p_c.dedutivel, false),
                              'ativo', coalesce(p_c.ativo, false), 'observacao_fiscal', p_c.observacao_fiscal, 'ordem', p_c.ordem,
                              'tipo_contexto', p_c.tipo_contexto, 'natureza', p_c.natureza,
                              'created_at', financeiro.iso_python(p_c.created_at), 'updated_at', financeiro.iso_python(p_c.updated_at))
$$;

-- Categorias IR ativas do tipo do perfil (ou AMBOS), por ordem e nome. Interna.
create function financeiro.categorias_ir_do_tipo(p_tipo text)
    returns jsonb
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select coalesce(jsonb_agg(financeiro.categoria_ir_flask(c) order by c.ordem, c.nome), '[]'::jsonb)
      from public.ir_categoria c
     where c.ativo and c.tipo_contexto in (p_tipo, 'AMBOS')
$$;

-- IrComprovante.to_dict(include_texto, include_eventos). Interna.
create function financeiro.comprovante_flask(p_c public.ir_comprovante, p_completo boolean)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_vinculo public.ir_comprovante_vinculo;
    v_dados   jsonb;
begin
    select * into v_vinculo from public.ir_comprovante_vinculo v
     where v.comprovante_id = p_c.id and v.ativo order by v.created_at desc, v.id desc limit 1;
    v_dados := jsonb_build_object(
        'id', p_c.id, 'perfil_financeiro_id', p_c.perfil_financeiro_id, 'ano_calendario', p_c.ano_calendario,
        'data_documento', p_c.data_documento, 'prestador_nome', p_c.prestador_nome, 'prestador_cpf_cnpj', p_c.prestador_cpf_cnpj,
        'tomador_nome', p_c.tomador_nome, 'tomador_cpf', p_c.tomador_cpf, 'valor', p_c.valor,
        'categoria_id', p_c.categoria_id,
        'categoria_nome', (select cat.nome from public.categoria cat where cat.id = p_c.categoria_id),
        'categoria_ir_id', p_c.categoria_ir_id,
        'categoria_ir_nome', (select ic.nome from public.ir_categoria ic where ic.id = p_c.categoria_ir_id),
        'dedutivel', p_c.dedutivel, 'status', p_c.status, 'confianca', p_c.confianca,
        'origem_classificacao', p_c.origem_classificacao, 'observacoes', p_c.observacoes, 'hash_arquivo', p_c.hash_arquivo,
        'arquivo', (select jsonb_build_object('id', a.id, 'comprovante_id', a.comprovante_id, 'nome_arquivo', a.nome_arquivo,
                                              'mime_type', a.mime_type, 'tamanho_bytes', a.tamanho_bytes,
                                              'hash_arquivo', a.hash_arquivo, 'created_at', financeiro.iso_python(a.created_at))
                      from public.ir_comprovante_arquivo a where a.comprovante_id = p_c.id order by a.id limit 1),
        'created_at', financeiro.iso_python(p_c.created_at), 'updated_at', financeiro.iso_python(p_c.updated_at),
        'vinculos_count', (select count(*) from public.ir_comprovante_vinculo v where v.comprovante_id = p_c.id and v.ativo),
        'status_lastro', coalesce(v_vinculo.status_lastro, 'SEM_DOCUMENTO'),
        'natureza_fiscal', v_vinculo.natureza, 'vinculo_resumo', v_vinculo.resumo_entidade);
    if p_completo then
        v_dados := v_dados || jsonb_build_object(
            'texto_extraido', p_c.texto_extraido,
            'eventos', coalesce((select jsonb_agg(jsonb_build_object('id', e.id, 'comprovante_id', e.comprovante_id,
                                                                     'tipo_evento', e.tipo_evento, 'descricao', e.descricao,
                                                                     'created_at', financeiro.iso_python(e.created_at))
                                                  order by e.created_at, e.id)
                                   from public.ir_comprovante_evento e where e.comprovante_id = p_c.id), '[]'::jsonb));
    end if;
    return v_dados;
end
$$;

-- ---------------------------------------------------------------------------------------------------------------------
-- Modo Documentos da Empresa (perfil Empresa): DocumentoEmpresarialService.

-- obter_taxonomia (constantes do Flask, copiadas de TIPOS/CATEGORIAS/STATUS_DOCUMENTAIS).
create function financeiro.taxonomia_documental()
    returns jsonb
    language sql
    immutable
    set search_path = ''
as $$
    select '{"tipos_documentais": [{"codigo": "PAGAMENTO_REALIZADO", "rotulo": "Pagamento realizado", "icone": "receipt"}, {"codigo": "NOTA_FISCAL_RECEBIDA", "rotulo": "Nota fiscal recebida", "icone": "receipt"}, {"codigo": "NOTA_FISCAL_EMITIDA", "rotulo": "Nota fiscal emitida", "icone": "receipt"}, {"codigo": "DOCUMENTO_OBRIGATORIO", "rotulo": "Documento obrigatorio", "icone": "shield"}, {"codigo": "DOCUMENTO_SOCIETARIO", "rotulo": "Documento societario/cadastral", "icone": "briefcase"}, {"codigo": "PROCURACAO_REPRESENTACAO", "rotulo": "Procuracao / representacao", "icone": "briefcase"}, {"codigo": "CONTRATO_INSTRUMENTO", "rotulo": "Contrato / instrumento", "icone": "book"}, {"codigo": "CERTIDAO_LICENCA", "rotulo": "Certidao / licenca", "icone": "shield"}, {"codigo": "PATRIMONIO_IMOBILIZADO", "rotulo": "Patrimonio / imobilizado", "icone": "tool"}, {"codigo": "CONTABIL_FISCAL", "rotulo": "Contabil / fiscal", "icone": "bank"}, {"codigo": "OUTRO", "rotulo": "Outro", "icone": "tag"}], "categorias_documentais": [{"codigo": "PIX_PAGO", "rotulo": "Pix pago", "tipo_documental": "PAGAMENTO_REALIZADO"}, {"codigo": "BOLETO_PAGO", "rotulo": "Boleto pago", "tipo_documental": "PAGAMENTO_REALIZADO"}, {"codigo": "TRANSFERENCIA", "rotulo": "Transferencia", "tipo_documental": "PAGAMENTO_REALIZADO"}, {"codigo": "GUIA_TAXA_PAGA", "rotulo": "Guia/taxa paga", "tipo_documental": "CONTABIL_FISCAL"}, {"codigo": "COMPROVANTE_BANCARIO", "rotulo": "Comprovante bancario", "tipo_documental": "PAGAMENTO_REALIZADO"}, {"codigo": "SERVICO_TOMADO", "rotulo": "Servico tomado", "tipo_documental": "NOTA_FISCAL_RECEBIDA"}, {"codigo": "COMPRA_MERCADORIA", "rotulo": "Compra de mercadoria", "tipo_documental": "NOTA_FISCAL_RECEBIDA"}, {"codigo": "COMPRA_EQUIPAMENTO", "rotulo": "Compra de equipamento", "tipo_documental": "PATRIMONIO_IMOBILIZADO"}, {"codigo": "NOTA_FORNECEDOR", "rotulo": "Nota de fornecedor", "tipo_documental": "NOTA_FISCAL_RECEBIDA"}, {"codigo": "DESPESA_OPERACIONAL", "rotulo": "Despesa operacional", "tipo_documental": "NOTA_FISCAL_RECEBIDA"}, {"codigo": "SERVICO_PRESTADO", "rotulo": "Servico prestado", "tipo_documental": "NOTA_FISCAL_EMITIDA"}, {"codigo": "NOTA_CLIENTE", "rotulo": "Nota para cliente", "tipo_documental": "NOTA_FISCAL_EMITIDA"}, {"codigo": "NOTA_CANCELADA", "rotulo": "Nota cancelada", "tipo_documental": "NOTA_FISCAL_EMITIDA"}, {"codigo": "NOTA_SUBSTITUIDA", "rotulo": "Nota substituida", "tipo_documental": "NOTA_FISCAL_EMITIDA"}, {"codigo": "INSCRICAO_MUNICIPAL", "rotulo": "Inscricao Municipal", "tipo_documental": "DOCUMENTO_SOCIETARIO"}, {"codigo": "CAE_CADASTRO_ECONOMICO", "rotulo": "CAE / Cadastro Economico", "tipo_documental": "DOCUMENTO_SOCIETARIO"}, {"codigo": "USO_DO_SOLO", "rotulo": "Uso do Solo", "tipo_documental": "DOCUMENTO_OBRIGATORIO"}, {"codigo": "CERTIFICADO_BOMBEIROS", "rotulo": "Certificado dos Bombeiros", "tipo_documental": "DOCUMENTO_OBRIGATORIO"}, {"codigo": "ALVARA_FUNCIONAMENTO", "rotulo": "Alvara de Funcionamento", "tipo_documental": "DOCUMENTO_OBRIGATORIO"}, {"codigo": "LICENCA_SANITARIA", "rotulo": "Licenca Sanitaria", "tipo_documental": "CERTIDAO_LICENCA"}, {"codigo": "LICENCA_AMBIENTAL", "rotulo": "Licenca Ambiental", "tipo_documental": "CERTIDAO_LICENCA"}, {"codigo": "CONTRATO_SOCIAL", "rotulo": "Contrato Social", "tipo_documental": "DOCUMENTO_SOCIETARIO"}, {"codigo": "ALTERACAO_CONTRATUAL", "rotulo": "Alteracao Contratual", "tipo_documental": "DOCUMENTO_SOCIETARIO"}, {"codigo": "CARTAO_CNPJ", "rotulo": "Cartao CNPJ / Constituicao", "tipo_documental": "DOCUMENTO_SOCIETARIO"}, {"codigo": "QUADRO_SOCIETARIO", "rotulo": "Quadro Societario", "tipo_documental": "DOCUMENTO_SOCIETARIO"}, {"codigo": "PROCURACAO_CONTADOR", "rotulo": "Procuracao do Contador", "tipo_documental": "PROCURACAO_REPRESENTACAO"}, {"codigo": "PROCURACAO_BANCO", "rotulo": "Procuracao Banco", "tipo_documental": "PROCURACAO_REPRESENTACAO"}, {"codigo": "AUTORIZACAO_ADMINISTRATIVA", "rotulo": "Autorizacao Administrativa", "tipo_documental": "PROCURACAO_REPRESENTACAO"}, {"codigo": "REPRESENTACAO_LEGAL", "rotulo": "Representacao Legal", "tipo_documental": "PROCURACAO_REPRESENTACAO"}, {"codigo": "CONTRATO_CLIENTE", "rotulo": "Contrato de Cliente", "tipo_documental": "CONTRATO_INSTRUMENTO"}, {"codigo": "CONTRATO_FORNECEDOR", "rotulo": "Contrato de Fornecedor", "tipo_documental": "CONTRATO_INSTRUMENTO"}, {"codigo": "CONTRATO_LOCACAO", "rotulo": "Contrato de Locacao", "tipo_documental": "CONTRATO_INSTRUMENTO"}, {"codigo": "CONTRATO_PRESTACAO_SERVICO", "rotulo": "Contrato de Prestacao de Servico", "tipo_documental": "CONTRATO_INSTRUMENTO"}, {"codigo": "TERMO_ADITIVO", "rotulo": "Termo/Aditivo", "tipo_documental": "CONTRATO_INSTRUMENTO"}, {"codigo": "CERTIDAO_MUNICIPAL", "rotulo": "Certidao Municipal", "tipo_documental": "CERTIDAO_LICENCA"}, {"codigo": "CERTIDAO_ESTADUAL", "rotulo": "Certidao Estadual", "tipo_documental": "CERTIDAO_LICENCA"}, {"codigo": "CERTIDAO_FEDERAL", "rotulo": "Certidao Federal", "tipo_documental": "CERTIDAO_LICENCA"}, {"codigo": "FGTS", "rotulo": "Certidao FGTS", "tipo_documental": "CERTIDAO_LICENCA"}, {"codigo": "TRABALHISTA", "rotulo": "Certidao Trabalhista", "tipo_documental": "CERTIDAO_LICENCA"}, {"codigo": "REGULARIDADE_FISCAL", "rotulo": "Regularidade Fiscal", "tipo_documental": "CERTIDAO_LICENCA"}, {"codigo": "NOTA_BEM_PATRIMONIAL", "rotulo": "Nota de bem patrimonial", "tipo_documental": "PATRIMONIO_IMOBILIZADO"}, {"codigo": "TERMO_GARANTIA", "rotulo": "Termo de Garantia", "tipo_documental": "PATRIMONIO_IMOBILIZADO"}, {"codigo": "MANUAL_GARANTIA", "rotulo": "Manual/Garantia", "tipo_documental": "PATRIMONIO_IMOBILIZADO"}, {"codigo": "DOCUMENTO_AQUISICAO", "rotulo": "Documento de Aquisicao", "tipo_documental": "PATRIMONIO_IMOBILIZADO"}, {"codigo": "RELATORIO_CONTABIL", "rotulo": "Relatorio Contabil", "tipo_documental": "CONTABIL_FISCAL"}, {"codigo": "BALANCETE", "rotulo": "Balancete", "tipo_documental": "CONTABIL_FISCAL"}, {"codigo": "DEMONSTRATIVO", "rotulo": "Demonstrativo", "tipo_documental": "CONTABIL_FISCAL"}, {"codigo": "APURACAO", "rotulo": "Apuracao", "tipo_documental": "CONTABIL_FISCAL"}, {"codigo": "DECLARACAO", "rotulo": "Declaracao", "tipo_documental": "CONTABIL_FISCAL"}, {"codigo": "LIVRO_REGISTRO", "rotulo": "Livro/Registro", "tipo_documental": "CONTABIL_FISCAL"}, {"codigo": "SEM_CATEGORIA", "rotulo": "Sem categoria", "tipo_documental": "OUTRO"}, {"codigo": "DOCUMENTO_DIVERSO", "rotulo": "Documento diverso", "tipo_documental": "OUTRO"}], "status_documentais": [{"codigo": "ATIVO", "rotulo": "Ativo"}, {"codigo": "VALIDO", "rotulo": "Valido"}, {"codigo": "VENCENDO", "rotulo": "Vencendo"}, {"codigo": "VENCIDO", "rotulo": "Vencido"}, {"codigo": "PENDENTE", "rotulo": "Pendente"}, {"codigo": "EM_REVISAO", "rotulo": "Em revisao"}, {"codigo": "AGUARDANDO_CONTADOR", "rotulo": "Aguardando contador"}, {"codigo": "SEM_LASTRO", "rotulo": "Sem lastro"}, {"codigo": "COM_LASTRO", "rotulo": "Com lastro"}, {"codigo": "NAO_APLICAVEL", "rotulo": "Nao aplicavel"}, {"codigo": "ARQUIVADO", "rotulo": "Arquivado"}]}'::jsonb
$$;

-- Metadados persistidos ou inferidos (_metadata_ou_padrao + serializar_metadata), com status recalculado pela validade
-- (calcular_status_documental), rotulos, icone e documento_label. Interna.
create function financeiro.metadata_empresarial_flask(p_c public.ir_comprovante)
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

-- enriquecer_comprovante_dict. Interna.
create function financeiro.comprovante_empresa(p_c public.ir_comprovante, p_base jsonb)
    returns jsonb
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select p_base || jsonb_build_object(
               'metadata_empresarial', md, 'tipo_documental', md -> 'tipo_documental',
               'tipo_documental_label', md -> 'tipo_documental_label', 'categoria_documental', md -> 'categoria_documental',
               'categoria_documental_label', md -> 'categoria_documental_label', 'data_validade', md -> 'data_validade',
               'status_documental', md -> 'status_documental', 'status_documental_label', md -> 'status_documental_label',
               'obrigatorio', md -> 'obrigatorio', 'icone_documental', md -> 'icone')
      from (select financeiro.metadata_empresarial_flask(p_c) md) x
$$;

-- aplicar_filtros_listagem (sobre os metadados PERSISTIDOS, como o Flask): tipo, categoria, status, obrigatorio, validade.
create function financeiro.filtro_documento_empresa(p_c public.ir_comprovante, p_f jsonb)
    returns boolean
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_m    public.documento_empresarial_metadata;
    v_hoje date := (now() at time zone 'America/Sao_Paulo')::date;
    v_t    text := upper(btrim(coalesce(p_f ->> 'tipo_documental', '')));
    v_c    text := upper(btrim(coalesce(p_f ->> 'categoria_documental', '')));
    v_s    text := upper(btrim(coalesce(p_f ->> 'status_documental', '')));
    v_o    text := lower(btrim(coalesce(p_f ->> 'obrigatorio', '')));
    v_v    text := upper(btrim(coalesce(p_f ->> 'validade', '')));
begin
    select * into v_m from public.documento_empresarial_metadata m where m.comprovante_id = p_c.id order by m.id limit 1;
    if v_t <> '' and v_t not in ('TODOS', 'TODAS') and v_m.tipo_documental is distinct from v_t then return false; end if;
    if v_c <> '' and v_c not in ('TODOS', 'TODAS') and v_m.categoria_documental is distinct from v_c then return false; end if;
    if v_s <> '' and v_s not in ('TODOS', 'TODAS') and v_m.status_documental is distinct from v_s then return false; end if;
    if v_o in ('1', 'true', 'sim', 'yes') and v_m.obrigatorio is not true then return false; end if;
    if v_o in ('0', 'false', 'nao', 'no') and not (v_m.obrigatorio is false or v_m.id is null) then return false; end if;
    if v_v = 'VENCIDOS' and not coalesce(v_m.data_validade < v_hoje, false) then return false; end if;
    if v_v = 'VENCENDO' and not coalesce(v_m.data_validade between v_hoje and v_hoje + 30, false) then return false; end if;
    if v_v = 'SEM_VALIDADE' and v_m.data_validade is not null then return false; end if;
    return true;
end
$$;

-- resumo_documentos_empresa (filtros: ano + os empresariais). Correcao D-DOC1 (docs): documento sem prestador e sem arquivo
-- com validade -> "Documento #id" (o Flask quebra com AttributeError e devolve 500). Interna.
create function financeiro.resumo_documentos_empresa(p_perfil_id integer, p_f jsonb)
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

-- GET /api/ir/documentos-empresa/taxonomia ('taxonomia'), /documentos-empresa/resumo ('resumo') e
-- /comprovantes/<id>/metadata-empresarial ('metadata', p_id). So no perfil Empresa (403 no Flask).
create function financeiro.ir_documentos_empresa_tela(p_perfil_id integer, p_recurso text, p_filtros jsonb, p_id integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_c public.ir_comprovante;
begin
    if financeiro.tipo_perfil_ir(p_perfil_id) <> 'EMPRESA' then
        raise exception 'Central de Documentos Empresariais disponivel apenas no perfil Empresa.' using errcode = '42501';
    end if;
    if p_recurso = 'taxonomia' then
        return financeiro.taxonomia_documental();
    elsif p_recurso = 'resumo' then
        return financeiro.resumo_documentos_empresa(p_perfil_id, coalesce(p_filtros, '{}'::jsonb));
    elsif p_recurso = 'metadata' then
        -- _obter_comprovante_empresa: perfil exatamente igual (sem a regra de perfil nulo).
        select * into v_c from public.ir_comprovante c where c.id = p_id and c.perfil_financeiro_id = p_perfil_id;
        if not found then
            raise exception 'Documento empresarial nao encontrado no perfil Empresa.' using errcode = '22023', hint = 'NAO_ENCONTRADA';
        end if;
        return financeiro.metadata_empresarial_flask(v_c);
    end if;
    raise exception 'Recurso invalido' using errcode = '22023';
end
$$;

-- GET /api/ir/contexto (modo IRPF ou Documentos da Empresa).
create function financeiro.ir_contexto_tela(p_perfil_id integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_tipo text := financeiro.tipo_perfil_ir(p_perfil_id);
begin
    return jsonb_build_object(
        -- PerfilFinanceiro.to_dict = perfil_em_json + datas.
        'perfil', financeiro.perfil_em_json(p_perfil_id)
                  || (select jsonb_build_object('created_at', financeiro.iso_python(p.created_at),
                                                'updated_at', financeiro.iso_python(p.updated_at))
                        from public.perfil_financeiro p where p.id = p_perfil_id),
        'modo', case when v_tipo = 'EMPRESA' then 'DOCUMENTOS_FISCAIS_EMPRESA' else 'IRPF' end,
        'titulo', case when v_tipo = 'EMPRESA' then 'Documentos da Empresa' else 'Imposto de Renda' end,
        'subtitulo', case when v_tipo = 'EMPRESA'
                          then 'Organize documentos fiscais, obrigatorios, societarios e vinculos de lastro da empresa.'
                          else 'Organize comprovantes potencialmente dedutiveis para sua declaracao anual.' end,
        'central_documentos_empresa', v_tipo = 'EMPRESA',
        'taxonomia_documental', case when v_tipo = 'EMPRESA' then financeiro.taxonomia_documental() end,
        'categorias', financeiro.categorias_ir_do_tipo(v_tipo));
end
$$;

-- GET /api/ir/categorias
create function financeiro.ir_categorias_tela(p_perfil_id integer)
    returns jsonb
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select financeiro.categorias_ir_do_tipo(financeiro.tipo_perfil_ir(p_perfil_id))
$$;

-- GET /api/ir/categorias-despesa (vinculos do perfil, por id) e /categorias-despesa-disponiveis.
create function financeiro.ir_categorias_despesa_tela(p_perfil_id integer, p_disponiveis boolean)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
begin
    perform financeiro.tipo_perfil_ir(p_perfil_id);
    if not p_disponiveis then
        return coalesce((
            select jsonb_agg(jsonb_build_object(
                       'id', v.id, 'perfil_financeiro_id', v.perfil_financeiro_id, 'categoria_ir_id', v.categoria_ir_id,
                       'categoria_ir_nome', (select ic.nome from public.ir_categoria ic where ic.id = v.categoria_ir_id),
                       'categoria_id', v.categoria_id,
                       'categoria_nome', (select c.nome from public.categoria c where c.id = v.categoria_id),
                       'ativo', coalesce(v.ativo, false),
                       'created_at', financeiro.iso_python(v.created_at), 'updated_at', financeiro.iso_python(v.updated_at))
                   order by v.id)
              from public.ir_categoria_despesa v
             where financeiro.pertence_ao_perfil(v.perfil_financeiro_id, p_perfil_id)), '[]'::jsonb);
    end if;
    return coalesce((
        select jsonb_agg(jsonb_build_object(
                   'id', c.id, 'perfil_financeiro_id', c.perfil_financeiro_id, 'nome', c.nome, 'descricao', c.descricao,
                   'cor', c.cor, 'icone', c.icone, 'logo_arquivo', c.logo_arquivo, 'logo_mime', c.logo_mime,
                   'logo_tamanho', c.logo_tamanho, 'logo_original_nome', c.logo_original_nome,
                   'logo_criado_em', financeiro.iso_python(c.logo_criado_em),
                   'logo_url', case when nullif(c.logo_arquivo, '') is not null then '/api/categorias/' || c.id || '/logo' end,
                   'ativo', c.ativo, 'sistemica', coalesce(c.sistemica, false), 'codigo_sistema', c.codigo_sistema,
                   'modulo_origem', c.modulo_origem, 'bloquear_edicao', coalesce(c.bloquear_edicao, false),
                   'bloquear_exclusao', coalesce(c.bloquear_exclusao, false), 'criado_em', financeiro.iso_python(c.criado_em),
                   'categoria_ir_id', v.categoria_ir_id,
                   'categoria_ir_nome', (select ic.nome from public.ir_categoria ic where ic.id = v.categoria_ir_id))
               order by c.nome, c.id)
          from public.categoria c
          left join lateral (select x.categoria_ir_id from public.ir_categoria_despesa x
                              where x.categoria_id = c.id and x.ativo
                                and financeiro.pertence_ao_perfil(x.perfil_financeiro_id, p_perfil_id)
                              order by x.id limit 1) v on true
         where c.ativo and financeiro.pertence_ao_perfil(c.perfil_financeiro_id, p_perfil_id)), '[]'::jsonb);
end
$$;

-- GET /api/ir/comprovantes (filtros: ano, status, categoria_ir_id, busca) com o resumo; /comprovantes/<id> (p_id).
create function financeiro.ir_comprovantes_tela(p_perfil_id integer, p_filtros jsonb, p_id integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_f      jsonb := coalesce(p_filtros, '{}'::jsonb);
    v_ano    integer;
    v_status text := upper(btrim(coalesce(v_f ->> 'status', '')));
    v_catir  integer;
    v_busca  text := nullif(btrim(coalesce(v_f ->> 'busca', '')), '');
    v_ids    integer[];
    v_um     public.ir_comprovante;
    v_empresa boolean := financeiro.tipo_perfil_ir(p_perfil_id) = 'EMPRESA';
begin
    if p_id is not null then
        select * into v_um from public.ir_comprovante c where c.id = p_id;
        if not found or not financeiro.pertence_ao_perfil(v_um.perfil_financeiro_id, p_perfil_id) then
            raise exception 'Comprovante nao encontrado' using errcode = '22023', hint = 'NAO_ENCONTRADA';
        end if;
        return case when v_empresa then financeiro.comprovante_empresa(v_um, financeiro.comprovante_flask(v_um, true))
                    else financeiro.comprovante_flask(v_um, true) end;
    end if;
    if btrim(coalesce(v_f ->> 'ano', '')) ~ '^[+-]?\d{1,9}$' then
        v_ano := nullif(btrim(v_f ->> 'ano')::integer, 0);
    end if;
    if btrim(coalesce(v_f ->> 'categoria_ir_id', '')) ~ '^[+-]?\d{1,9}$' then
        v_catir := nullif(btrim(v_f ->> 'categoria_ir_id')::integer, 0);
    end if;
    if v_status in ('', 'TODOS') then
        v_status := null;
    end if;
    select coalesce(array_agg(c.id order by c.data_documento desc, c.created_at desc, c.id desc), '{}') into v_ids
      from public.ir_comprovante c
     where financeiro.pertence_ao_perfil(c.perfil_financeiro_id, p_perfil_id)
       and (v_ano is null or c.ano_calendario = v_ano)
       and (v_status is null or c.status = v_status)
       and (v_catir is null or c.categoria_ir_id = v_catir)
       and (v_busca is null or c.prestador_nome ilike '%' || v_busca || '%' or c.prestador_cpf_cnpj ilike '%' || v_busca || '%'
            or c.observacoes ilike '%' || v_busca || '%')
       and (not v_empresa or financeiro.filtro_documento_empresa(c, v_f));
    return jsonb_build_object(
        'data', coalesce((select jsonb_agg(case when v_empresa
                                                then financeiro.comprovante_empresa(c, financeiro.comprovante_flask(c, false))
                                                else financeiro.comprovante_flask(c, false) end order by x.ordem)
                            from unnest(v_ids) with ordinality x(id, ordem) join public.ir_comprovante c on c.id = x.id), '[]'::jsonb),
        'total', cardinality(v_ids),
        'resumo', (
            select jsonb_build_object(
                'total_comprovantes', count(*),
                'valor_potencialmente_dedutivel', coalesce(sum(c.valor) filter (where c.dedutivel is distinct from false), 0),
                'pendentes_revisao', count(*) filter (where c.status in ('PENDENTE_REVISAO', 'ERRO_LEITURA', 'IMPORTADO')),
                'categorias_ir_usadas', count(distinct c.categoria_ir_id),
                'lastro', jsonb_build_object(
                    'total_documentos', count(*),
                    'documentos_vinculados', count(*) filter (where l.status_lastro is not null),
                    'documentos_sem_vinculo', count(*) filter (where l.status_lastro is null),
                    'valor_com_lastro', coalesce(sum(c.valor) filter (where l.status_lastro is not null), 0),
                    'valor_sem_lastro', coalesce(sum(c.valor) filter (where l.status_lastro is null), 0),
                    'documentos_aguardando_contador', count(*) filter (where l.status_lastro = 'AGUARDANDO_CONTADOR')),
                'totais_por_categoria_ir', coalesce((
                    select jsonb_agg(jsonb_build_object('categoria_ir_nome', t.nome, 'valor', t.valor) order by t.nome)
                      from (select coalesce(ic.nome, 'Sem categoria IR') nome, coalesce(sum(y.valor), 0) valor
                              from public.ir_comprovante y left join public.ir_categoria ic on ic.id = y.categoria_ir_id
                             where y.id = any (v_ids) group by 1) t), '[]'::jsonb),
                'documentos_empresa', case when v_empresa then financeiro.resumo_documentos_empresa(p_perfil_id, v_f) end)
              from public.ir_comprovante c
              left join lateral (select coalesce(v.status_lastro, '') status_lastro from public.ir_comprovante_vinculo v
                                  where v.comprovante_id = c.id and v.ativo order by v.id limit 1) l on true
             where c.id = any (v_ids)));
end
$$;

revoke execute on function financeiro.tipo_perfil_ir(integer) from public, anon, authenticated;
revoke execute on function financeiro.categoria_ir_flask(public.ir_categoria) from public, anon, authenticated;
revoke execute on function financeiro.categorias_ir_do_tipo(text) from public, anon, authenticated;
revoke execute on function financeiro.comprovante_flask(public.ir_comprovante, boolean) from public, anon, authenticated;
revoke execute on function financeiro.taxonomia_documental() from public, anon, authenticated;
revoke execute on function financeiro.metadata_empresarial_flask(public.ir_comprovante) from public, anon, authenticated;
revoke execute on function financeiro.comprovante_empresa(public.ir_comprovante, jsonb) from public, anon, authenticated;
revoke execute on function financeiro.filtro_documento_empresa(public.ir_comprovante, jsonb) from public, anon, authenticated;
revoke execute on function financeiro.resumo_documentos_empresa(integer, jsonb) from public, anon, authenticated;
revoke execute on function financeiro.ir_documentos_empresa_tela(integer, text, jsonb, integer) from public, anon;
grant execute on function financeiro.ir_documentos_empresa_tela(integer, text, jsonb, integer) to authenticated;
revoke execute on function financeiro.ir_contexto_tela(integer) from public, anon;
revoke execute on function financeiro.ir_categorias_tela(integer) from public, anon;
revoke execute on function financeiro.ir_categorias_despesa_tela(integer, boolean) from public, anon;
revoke execute on function financeiro.ir_comprovantes_tela(integer, jsonb, integer) from public, anon;
grant execute on function financeiro.ir_contexto_tela(integer) to authenticated;
grant execute on function financeiro.ir_categorias_tela(integer) to authenticated;
grant execute on function financeiro.ir_categorias_despesa_tela(integer, boolean) to authenticated;
grant execute on function financeiro.ir_comprovantes_tela(integer, jsonb, integer) to authenticated;
