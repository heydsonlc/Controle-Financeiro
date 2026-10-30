-- FIN-MIGRACAO-LASTRO-EMPRESA-01 — Documentos da Empresa: classificacao segura, metadados empresariais, lastro so para
-- documento que comprova operacao financeira, saidas sem documento (vincular e situacao) e exclusao completa.
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261202090000).
-- Depende de 20261113090000 (leitura de Documentos), 20261117090000 (saidas sem documento), 20261124090000
-- (exigir_escrita_novo), 20261128090000 (escrita de Documentos) e 20261130090000 (criar_vinculo_documento).
-- Validada em cluster local descartavel (tests/test_supabase_lastro_empresa.py). Docs: docs/FIN_MIGRACAO_LASTRO_EMPRESA_01.md.
--
-- Achados que originam o pacote (documento real id 4, "Contrato_Social_e_Procuracao.pdf"):
-- - metadata_empresarial_flask (= _inferir_tipo_categoria do Flask) inferia na leitura, por substring e em ordem fixa
--   ("pix" antes de "contrato"): o contrato social, que cita Pix, virou Pagamento realizado / Pix pago;
-- - resumo_documentos_empresa contava "sem lastro" todo documento sem vinculo, inclusive contrato social e certidao;
-- - a revisao da tela original grava os metadados (PUT /comprovantes/<id>/metadata-empresarial), mas nao havia escrita;
-- - "CONTA" no vinculo pelo documento era conta BANCARIA; no lastro e no "Gerar financeiro", conta A PAGAR. A leitura
--   das saidas casa por tipo + id: um vinculo com a conta bancaria 5 marcaria a conta a pagar 5 como documentada;
-- - excluir_comprovante nao apagava os metadados (a exclusao quebraria depois da revisao, por chave estrangeira).
--
-- Lastro (conceito): vinculo ATIVO entre um documento e uma operacao financeira do perfil (conta a pagar, lancamento no
-- cartao, despesa prevista, movimento) em ir_comprovante_vinculo; sem vinculo, a saida pode ter uma pendencia manual
-- (lastro_financeiro_pendencia: pendente, aguardando contador, nao aplicavel). Documento empresarial geral (societario,
-- procuracao, certidao, contrato, contabil) existe sem lastro e nao e pendencia financeira.
-- Nenhuma tabela nova. Nenhum dado existente e alterado (na producao nao ha vinculo nem metadado gravado).

-- Documento que comprova operacao financeira (exige lastro). Interna.
create function financeiro.documento_exige_lastro(p_tipo text, p_categoria text)
    returns boolean
    language sql
    immutable
    set search_path = ''
as $$
    select upper(coalesce(p_tipo, '')) in ('PAGAMENTO_REALIZADO', 'NOTA_FISCAL_RECEBIDA', 'NOTA_FISCAL_EMITIDA')
        or upper(coalesce(p_categoria, '')) = 'GUIA_TAXA_PAGA'
$$;

-- Classificacao automatica do documento sem metadados: so sugere com evidencia; sem ela, OUTRO / SEM_CATEGORIA
-- ("Nao classificado"). Palavras inteiras, sem acento. Documento-base (societario, procuracao, certidao) antes de
-- pagamento, e pagamento so com sinal de transacao (comprovante, transacao, linha digitavel...). Interna.
create function financeiro.inferir_documento_empresa(p_c public.ir_comprovante)
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
        -- FIN-MIGRACAO-LASTRO-EMPRESA-01: "sem lastro" so para o documento que comprova operacao financeira (pagamento,
        -- nota fiscal, guia paga); contrato social, procuracao, certidao etc. existem sem vinculo financeiro.
        if v_lastro in ('SEM_DOCUMENTO', 'PENDENTE')
           and financeiro.documento_exige_lastro(v_md ->> 'tipo_documental', v_md ->> 'categoria_documental') then
            v_sem := v_sem + 1;
        end if;
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

-- Central de Documentos Empresariais so no perfil Empresa (PermissionError do Flask -> 403). Interna.
create function financeiro.exigir_documentos_empresa(p_perfil_id integer)
    returns void
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
begin
    if financeiro.tipo_perfil_ir(p_perfil_id) <> 'EMPRESA' then
        raise exception 'Central de Documentos Empresariais disponivel apenas no perfil Empresa.' using errcode = '42501';
    end if;
end
$$;

-- Data do Flask (_parse_date: AAAA-MM-DD ou DD/MM/AAAA; invalida = NULL). Interna.
create function financeiro.doc_data(p_valor text)
    returns date
    language plpgsql
    immutable
    set search_path = ''
as $$
declare
    v text := btrim(coalesce(p_valor, ''));
begin
    if v ~ '^\d{4}-\d{2}-\d{2}$' then return v::date; end if;
    if v ~ '^\d{2}/\d{2}/\d{4}$' then return to_date(v, 'DD/MM/YYYY'); end if;
    return null;
exception when others then
    return null;
end
$$;

-- PUT /api/ir/comprovantes/<id>/metadata-empresarial (DocumentoEmpresarialService.atualizar_metadata). Regras do Flask:
-- tipo e categoria da taxonomia (a categoria define o tipo), textos cortados, datas e booleanos normalizados, situacao
-- recalculada pela validade. Correcoes: campo ausente no pedido nao apaga o gravado (subtipo, tags, observacoes, que a
-- tela nao envia); o evento leva antes -> depois; a operacao (chave) guarda antes/depois, conta e hora (auditoria).
create function financeiro.salvar_metadata_empresarial(p_perfil_id integer, p_id integer, p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_rep    jsonb;
    v_c      public.ir_comprovante;
    v_m      public.documento_empresarial_metadata;
    v_d      jsonb := coalesce(p_dados, '{}'::jsonb);
    v_tax    jsonb := financeiro.taxonomia_documental();
    v_antes  jsonb;
    v_depois jsonb;
    v_tipo   text;
    v_cat    text;
    v_ctipo  text;
    v_val    date;
    v_status text;
    v_hoje   date := (now() at time zone 'America/Sao_Paulo')::date;
    v_agora  timestamp := (now() at time zone 'utc')::timestamp;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    perform financeiro.exigir_documentos_empresa(p_perfil_id);
    v_rep := financeiro.repeticao_documento(p_chave, p_perfil_id, 'salvar_metadata_empresarial');
    if v_rep is not null then
        return v_rep;
    end if;
    select * into v_c from public.ir_comprovante c where c.id = p_id and c.perfil_financeiro_id = p_perfil_id for update;
    if not found then
        raise exception 'Documento empresarial nao encontrado no perfil Empresa.' using errcode = '22023', hint = 'NAO_ENCONTRADA';
    end if;
    v_antes := financeiro.metadata_empresarial_flask(v_c);
    select * into v_m from public.documento_empresarial_metadata m where m.comprovante_id = v_c.id order by m.id limit 1 for update;
    if not found then
        insert into public.documento_empresarial_metadata (comprovante_id, perfil_financeiro_id, tipo_documental,
                                                           categoria_documental, status_documental, obrigatorio, renovavel,
                                                           alerta_dias_antes, origem_documental, created_at, updated_at)
        values (v_c.id, p_perfil_id, v_antes ->> 'tipo_documental', v_antes ->> 'categoria_documental', 'ATIVO', false, false,
                30, 'USUARIO', v_agora, v_agora)
        returning * into v_m;
    end if;
    v_tipo := upper(btrim(coalesce(v_d ->> 'tipo_documental', '')));
    if not exists (select 1 from jsonb_array_elements(v_tax -> 'tipos_documentais') x where x ->> 'codigo' = v_tipo) then
        v_tipo := coalesce(v_m.tipo_documental, 'OUTRO');
    end if;
    v_cat := upper(btrim(coalesce(v_d ->> 'categoria_documental', '')));
    if not exists (select 1 from jsonb_array_elements(v_tax -> 'categorias_documentais') x where x ->> 'codigo' = v_cat) then
        v_cat := coalesce(v_m.categoria_documental, 'SEM_CATEGORIA');
    end if;
    if v_cat <> 'SEM_CATEGORIA' then
        select x ->> 'tipo_documental' into v_ctipo from jsonb_array_elements(v_tax -> 'categorias_documentais') x
         where x ->> 'codigo' = v_cat limit 1;
        v_tipo := coalesce(v_ctipo, v_tipo);
    end if;
    v_m.tipo_documental := v_tipo;
    v_m.categoria_documental := v_cat;
    if v_d ? 'subtipo' then v_m.subtipo := nullif(left(btrim(coalesce(v_d ->> 'subtipo', '')), 120), ''); end if;
    v_m.numero_documento := nullif(left(btrim(coalesce(v_d ->> 'numero_documento', '')), 120), '');
    v_m.orgao_emissor := nullif(left(btrim(coalesce(v_d ->> 'orgao_emissor', '')), 160), '');
    v_m.data_emissao := financeiro.doc_data(v_d ->> 'data_emissao');
    v_m.data_validade := financeiro.doc_data(v_d ->> 'data_validade');
    v_m.obrigatorio := lower(btrim(coalesce(v_d ->> 'obrigatorio', ''))) in ('1', 'true', 'sim', 'yes', 'on');
    v_m.renovavel := lower(btrim(coalesce(v_d ->> 'renovavel', ''))) in ('1', 'true', 'sim', 'yes', 'on');
    v_m.alerta_dias_antes := case when btrim(coalesce(v_d ->> 'alerta_dias_antes', '')) ~ '^[+-]?\d{1,9}$'
                                  then btrim(v_d ->> 'alerta_dias_antes')::integer end;
    v_m.responsavel_interno := nullif(left(btrim(coalesce(v_d ->> 'responsavel_interno', '')), 120), '');
    v_m.origem_documental := coalesce(nullif(left(btrim(coalesce(v_d ->> 'origem_documental', '')), 40), ''), 'USUARIO');
    if v_d ? 'tags' then v_m.tags := nullif(left(btrim(coalesce(v_d ->> 'tags', '')), 1000), ''); end if;
    if v_d ? 'observacoes' then v_m.observacoes := nullif(left(btrim(coalesce(v_d ->> 'observacoes', '')), 2000), ''); end if;
    -- calcular_status_documental (tem_metadados: tipo e categoria sempre preenchidos aqui).
    v_val := v_m.data_validade;
    v_status := upper(btrim(coalesce(v_d ->> 'status_documental', '')));
    v_m.status_documental := case
        when v_val is not null then case when v_val < v_hoje then 'VENCIDO' when v_val - v_hoje <= 30 then 'VENCENDO' else 'VALIDO' end
        when v_status in ('PENDENTE', 'EM_REVISAO', 'AGUARDANDO_CONTADOR', 'SEM_LASTRO', 'COM_LASTRO', 'NAO_APLICAVEL', 'ARQUIVADO')
            then v_status
        else 'ATIVO' end;
    update public.documento_empresarial_metadata
       set tipo_documental = v_m.tipo_documental, categoria_documental = v_m.categoria_documental, subtipo = v_m.subtipo,
           numero_documento = v_m.numero_documento, orgao_emissor = v_m.orgao_emissor, data_emissao = v_m.data_emissao,
           data_validade = v_m.data_validade, status_documental = v_m.status_documental, obrigatorio = v_m.obrigatorio,
           renovavel = v_m.renovavel, alerta_dias_antes = v_m.alerta_dias_antes, responsavel_interno = v_m.responsavel_interno,
           origem_documental = v_m.origem_documental, tags = v_m.tags, observacoes = v_m.observacoes, updated_at = v_agora
     where id = v_m.id;
    v_depois := financeiro.metadata_empresarial_flask(v_c);
    perform financeiro.doc_evento(v_c.id, 'METADATA_EMPRESARIAL_ATUALIZADA', left(format(
        'Metadados empresariais revisados pelo usuario: %s / %s (%s) -> %s / %s.',
        v_antes ->> 'tipo_documental_label', v_antes ->> 'categoria_documental_label', lower(v_antes ->> 'origem_documental'),
        v_depois ->> 'tipo_documental_label', v_depois ->> 'categoria_documental_label'), 1000));
    perform financeiro.registrar_operacao_documento(p_chave, p_perfil_id, 'salvar_metadata_empresarial', jsonb_build_object(
        'comprovante_id', v_c.id,
        'antes', v_antes - array['created_at', 'updated_at', 'icone'],
        'depois', v_depois - array['created_at', 'updated_at', 'icone']));
    return v_depois;
end
$$;

-- Exclusao segura (texto de 20261128090000) + os metadados empresariais do documento, que antes ficavam e travavam a
-- exclusao por chave estrangeira. Continua recusando documento com vinculo (inclusive inativo: historico) e validado.
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
    delete from public.documento_empresarial_metadata where comprovante_id = v_c.id;  -- FIN-MIGRACAO-LASTRO-EMPRESA-01
    delete from public.ir_comprovante_evento where comprovante_id = v_c.id;
    delete from public.ir_comprovante_arquivo where comprovante_id = v_c.id;
    delete from public.ir_comprovante where id = v_c.id;
    return jsonb_build_object('comprovante_id', v_c.id, 'excluido', true);
end
$$;

-- Vinculo pelo documento (texto de 20261130090000): "Conta bancaria" (CONTA na tela) passa a ser gravada como
-- CONTA_BANCARIA. CONTA fica so para conta a pagar, como no lastro e no "Gerar financeiro".
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
    values (v_c.id, p_perfil_id, case when v_tipo = 'CONTA' then 'CONTA_BANCARIA' else v_tipo end,  -- FIN-MIGRACAO-LASTRO-EMPRESA-01
            (v_ent ->> 'id')::integer, v_ent ->> 'resumo',
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

-- Saida do lastro (LastroFinanceiroService._obter_entidade + _resumo_entidade): a operacao do perfil e o resumo gravado
-- no vinculo. CONTA = conta a pagar (public.conta). Interna.
create function financeiro.lastro_saida_entidade(p_perfil_id integer, p_tipo text, p_id integer)
    returns text
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_resumo text;
    v_perfil integer;
    v_achou  boolean := false;
begin
    if p_tipo = 'DESPESA_PREVISTA' then
        select coalesce(cat.nome, 'Despesa') || ' - ' || coalesce(d.status, 'None'), d.perfil_financeiro_id, true
          into v_resumo, v_perfil, v_achou
          from public.despesa_prevista d left join public.categoria cat on cat.id = d.categoria_id where d.id = p_id;
    elsif p_tipo = 'CONTA' then
        select coalesce(nullif(c.descricao, ''), 'Conta #' || c.id), c.perfil_financeiro_id, true
          into v_resumo, v_perfil, v_achou from public.conta c where c.id = p_id;
    elsif p_tipo = 'LANCAMENTO' then
        select la.descricao, la.perfil_financeiro_id, true into v_resumo, v_perfil, v_achou from public.lancamento_agregado la where la.id = p_id;
    elsif p_tipo = 'MOVIMENTO_FINANCEIRO' then
        select m.descricao, m.perfil_financeiro_id, true into v_resumo, v_perfil, v_achou from public.movimento_financeiro m where m.id = p_id;
    else
        raise exception 'Tipo de entidade nao suportado para lastro' using errcode = '22023';
    end if;
    if not coalesce(v_achou, false) or v_perfil is distinct from p_perfil_id then
        raise exception 'Recurso nao encontrado no perfil financeiro ativo' using errcode = '22023';
    end if;
    return v_resumo;
end
$$;

-- POST /api/ir/lastro/saidas-sem-documento/vincular (LastroFinanceiroService.vincular_documento): vinculo ativo do documento
-- do perfil com a saida (padrao VALIDADO) e a pendencia manual da saida desativada. Correcao: o mesmo documento nao e
-- vinculado duas vezes a mesma saida (o Flask duplicava).
create function financeiro.vincular_saida_documento(p_perfil_id integer, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_tipo   text := upper(btrim(coalesce(p_dados ->> 'tipo_entidade', '')));
    v_ent    integer := financeiro.mob_inteiro(p_dados -> 'entidade_id');
    v_doc    integer := financeiro.mob_inteiro(p_dados -> 'comprovante_id');
    v_c      public.ir_comprovante;
    v_resumo text;
    v_id     integer;
    v_agora  timestamp := (now() at time zone 'utc')::timestamp;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    perform financeiro.exigir_documentos_empresa(p_perfil_id);
    if v_tipo not in ('DESPESA_PREVISTA', 'CONTA', 'LANCAMENTO', 'MOVIMENTO_FINANCEIRO') or v_ent is null or v_doc is null then
        raise exception 'Saida e documento fiscal sao obrigatorios' using errcode = '22023';
    end if;
    v_resumo := financeiro.lastro_saida_entidade(p_perfil_id, v_tipo, v_ent);
    v_c := financeiro.doc_comprovante(p_perfil_id, v_doc);
    if exists (select 1 from public.ir_comprovante_vinculo v where v.comprovante_id = v_c.id and v.ativo
                 and v.tipo_entidade = v_tipo and v.entidade_id = v_ent) then
        raise exception 'Este documento ja esta vinculado a esta saida' using errcode = '22023', hint = 'DUPLICADO';
    end if;
    insert into public.ir_comprovante_vinculo (comprovante_id, perfil_financeiro_id, tipo_entidade, entidade_id, resumo_entidade,
                                               tipo_vinculo, natureza, status_lastro, observacoes, ativo, created_at, updated_at)
    values (v_c.id, p_perfil_id, v_tipo, v_ent, v_resumo,
            financeiro.doc_opcao(p_dados ->> 'tipo_vinculo', array['COMPROVANTE', 'NOTA_FISCAL', 'RECIBO', 'CONTRATO', 'GUIA', 'DOCUMENTO_CONTABIL', 'OUTRO'], 'COMPROVANTE'),
            financeiro.doc_opcao(p_dados ->> 'natureza', array['DESPESA_OPERACIONAL', 'PATRIMONIO_IMOBILIZADO', 'SOFTWARE_ASSINATURA', 'IMPOSTO_TAXA',
                'PRO_LABORE', 'DISTRIBUICAO_LUCROS', 'REEMBOLSO', 'EMPRESTIMO', 'ADIANTAMENTO', 'OUTRO'], 'OUTRO'),
            financeiro.doc_opcao(p_dados ->> 'status_lastro', array['SEM_DOCUMENTO', 'PENDENTE', 'AGUARDANDO_CONTADOR', 'NAO_APLICAVEL', 'VALIDADO',
                'DIVERGENTE', 'COM_DOCUMENTO'], 'VALIDADO'),
            nullif(left(btrim(coalesce(p_dados ->> 'observacoes', '')), 1000), ''), true, v_agora, v_agora)
    returning id into v_id;
    update public.lastro_financeiro_pendencia set ativo = false, updated_at = v_agora
     where perfil_financeiro_id = p_perfil_id and tipo_entidade = v_tipo and entidade_id = v_ent and ativo;
    return (select jsonb_build_object('id', v.id, 'comprovante_id', v.comprovante_id, 'perfil_financeiro_id', v.perfil_financeiro_id,
                                      'tipo_entidade', v.tipo_entidade, 'entidade_id', v.entidade_id, 'resumo_entidade', v.resumo_entidade,
                                      'tipo_vinculo', v.tipo_vinculo, 'natureza', v.natureza, 'status_lastro', v.status_lastro,
                                      'observacoes', v.observacoes, 'ativo', v.ativo)
              from public.ir_comprovante_vinculo v where v.id = v_id);
end
$$;

-- POST /api/ir/lastro/saidas-sem-documento/status (LastroFinanceiroService.marcar_status): situacao manual da saida sem
-- documento (pendente, aguardando contador, nao aplicavel); SEM_DOCUMENTO desativa a pendencia. Recusa saida ja documentada.
create function financeiro.marcar_status_saida(p_perfil_id integer, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_tipo   text := upper(btrim(coalesce(p_dados ->> 'tipo_entidade', '')));
    v_ent    integer := financeiro.mob_inteiro(p_dados -> 'entidade_id');
    v_status text := financeiro.doc_opcao(p_dados ->> 'status_lastro', array['PENDENTE', 'AGUARDANDO_CONTADOR', 'NAO_APLICAVEL', 'SEM_DOCUMENTO'], 'PENDENTE');
    v_nat    text := financeiro.doc_opcao(p_dados ->> 'natureza', array['DESPESA_OPERACIONAL', 'PATRIMONIO_IMOBILIZADO', 'SOFTWARE_ASSINATURA',
                         'IMPOSTO_TAXA', 'PRO_LABORE', 'DISTRIBUICAO_LUCROS', 'REEMBOLSO', 'EMPRESTIMO', 'ADIANTAMENTO', 'OUTRO'], 'OUTRO');
    v_p      public.lastro_financeiro_pendencia;
    v_agora  timestamp := (now() at time zone 'utc')::timestamp;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    perform financeiro.exigir_documentos_empresa(p_perfil_id);
    if v_tipo not in ('DESPESA_PREVISTA', 'CONTA', 'LANCAMENTO', 'MOVIMENTO_FINANCEIRO') or v_ent is null then
        raise exception 'Tipo de entidade e entidade sao obrigatorios' using errcode = '22023';
    end if;
    perform financeiro.lastro_saida_entidade(p_perfil_id, v_tipo, v_ent);
    if exists (select 1 from public.ir_comprovante_vinculo v join public.ir_comprovante c on c.id = v.comprovante_id
                where v.perfil_financeiro_id = p_perfil_id and v.ativo and c.perfil_financeiro_id = p_perfil_id
                  and v.tipo_entidade = v_tipo and v.entidade_id = v_ent) then
        raise exception 'Saida ja possui documento vinculado' using errcode = '22023';
    end if;
    select * into v_p from public.lastro_financeiro_pendencia p
     where p.perfil_financeiro_id = p_perfil_id and p.tipo_entidade = v_tipo and p.entidade_id = v_ent and p.ativo
     order by p.id limit 1 for update;
    if v_status = 'SEM_DOCUMENTO' then
        update public.lastro_financeiro_pendencia set ativo = false, updated_at = v_agora where id = v_p.id;
        return jsonb_build_object('tipo_entidade', v_tipo, 'entidade_id', v_ent, 'status_lastro', 'SEM_DOCUMENTO');
    end if;
    if v_p.id is null then
        insert into public.lastro_financeiro_pendencia (perfil_financeiro_id, tipo_entidade, entidade_id, status_lastro, natureza,
                                                        observacoes, ativo, created_at, updated_at)
        values (p_perfil_id, v_tipo, v_ent, v_status, v_nat, nullif(left(btrim(coalesce(p_dados ->> 'observacoes', '')), 1000), ''),
                true, v_agora, v_agora)
        returning * into v_p;
    else
        update public.lastro_financeiro_pendencia
           set status_lastro = v_status, natureza = v_nat,
               observacoes = nullif(left(btrim(coalesce(p_dados ->> 'observacoes', '')), 1000), ''), updated_at = v_agora
         where id = v_p.id
        returning * into v_p;
    end if;
    return jsonb_build_object('id', v_p.id, 'perfil_financeiro_id', v_p.perfil_financeiro_id, 'tipo_entidade', v_p.tipo_entidade,
                              'entidade_id', v_p.entidade_id, 'status_lastro', v_p.status_lastro, 'natureza', v_p.natureza,
                              'observacoes', v_p.observacoes, 'ativo', v_p.ativo);
end
$$;

revoke execute on function financeiro.documento_exige_lastro(text, text) from public, anon, authenticated;
revoke execute on function financeiro.inferir_documento_empresa(public.ir_comprovante) from public, anon, authenticated;
revoke execute on function financeiro.exigir_documentos_empresa(integer) from public, anon, authenticated;
revoke execute on function financeiro.doc_data(text) from public, anon, authenticated;
revoke execute on function financeiro.lastro_saida_entidade(integer, text, integer) from public, anon, authenticated;
revoke execute on function financeiro.salvar_metadata_empresarial(integer, integer, jsonb, uuid) from public, anon;
revoke execute on function financeiro.vincular_saida_documento(integer, jsonb) from public, anon;
revoke execute on function financeiro.marcar_status_saida(integer, jsonb) from public, anon;
grant execute on function financeiro.salvar_metadata_empresarial(integer, integer, jsonb, uuid) to authenticated;
grant execute on function financeiro.vincular_saida_documento(integer, jsonb) to authenticated;
grant execute on function financeiro.marcar_status_saida(integer, jsonb) to authenticated;
