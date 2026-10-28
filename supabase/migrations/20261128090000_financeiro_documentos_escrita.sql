-- FIN-DOCUMENTOS-2 (FIN-BLOCO-B-1, B1) — escrita de Documentos Fiscais no novo aplicativo, com o escritor unico do perfil.
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261128090000).
-- Depende de 20261113090000 (leitura de Documentos: comprovante_flask), 20261124090000 (exigir_escrita_novo, criar_compra),
-- 20261120090000 (pagar_despesa) e 20261126090000 (regra do bem patrimonial). Validada em cluster local descartavel
-- (tests/test_supabase_documentos_escrita.py, comparada com o Flask). Docs: docs/FIN_DOCUMENTOS_2.md.
--
-- Reproduz as rotas de routes/ir.py: envio de arquivo (POST /comprovantes/upload), revisao (PUT /comprovantes/<id>),
-- validacao, vinculos (criar, editar, remover) e a criacao de despesa/lancamento a partir do documento.
-- Armazenamento: o arquivo fica no banco (public.ir_comprovante_arquivo.conteudo), como no Flask, e so e lido pelas
-- funcoes que conferem o perfil (arquivo_comprovante_tela). Nenhum bucket publico ou remoto.
-- Validacoes do Flask: extensao (pdf, png, jpg, jpeg, webp), MIME, arquivo nao vazio, ate 10 MB, assinatura do arquivo
-- (bytes iniciais) e duplicidade por SHA-256 no perfil.
-- Correcoes (docs/FIN_DOCUMENTOS_2.md): exclusao segura (o Flask nao tinha; recusa com vinculos ou historico
-- financeiro); o mesmo documento nao gera duas despesas (o Flask permitia); vinculo PATRIMONIO segue a regra do bem
-- (um documento, um bem); pagamento pela conta bancaria passa pelo pagar_despesa (movimento e saldo pelo mesmo motor).
-- OCR e leitura automatica (NFS-e, cupom fiscal) continuam complementares: o texto de PDF textual e extraido no navegador
-- (pdf.js) e guardado; sem ele o documento fica para revisao manual. Nenhum servico externo.
-- Uma tabela nova (operacao_documento, vazia, idempotencia). Nenhum dado existente e alterado.

create table financeiro.operacao_documento (
    chave                uuid        primary key,
    user_id              uuid        not null references auth.users (id) on delete cascade,
    perfil_financeiro_id integer     not null,
    operacao             text        not null,
    resultado            jsonb       not null,
    criado_em            timestamptz not null default now()
);
comment on table financeiro.operacao_documento is
    'FIN-DOCUMENTOS-2: resultado de cada envio/criacao a partir de documento por chave (reenvio nao duplica).';
alter table financeiro.operacao_documento enable row level security;
alter table financeiro.operacao_documento force row level security;
revoke all on financeiro.operacao_documento from public, anon, authenticated;

create function financeiro.repeticao_documento(p_chave uuid, p_perfil_id integer, p_operacao text)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_anterior financeiro.operacao_documento;
begin
    if p_chave is null then
        raise exception 'Chave da operacao obrigatoria' using errcode = '22023';
    end if;
    perform pg_advisory_xact_lock(hashtextextended(p_chave::text, 20261128));
    select * into v_anterior from financeiro.operacao_documento o where o.chave = p_chave;
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

create function financeiro.registrar_operacao_documento(p_chave uuid, p_perfil_id integer, p_operacao text,
                                                        p_resultado jsonb)
    returns jsonb
    language sql
    volatile
    security definer
    set search_path = ''
as $$
    insert into financeiro.operacao_documento (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, p_operacao, p_resultado)
    returning resultado
$$;

-- Comprovante do perfil, travado ('Comprovante nao encontrado', ValueError do Flask).
create function financeiro.doc_comprovante(p_perfil_id integer, p_id integer)
    returns public.ir_comprovante
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_c public.ir_comprovante;
begin
    select * into v_c from public.ir_comprovante c where c.id = p_id for update;
    if not found or not financeiro.pertence_ao_perfil(v_c.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Comprovante nao encontrado' using errcode = '22023', hint = 'NAO_ENCONTRADA';
    end if;
    return v_c;
end
$$;

create function financeiro.doc_evento(p_comprovante_id integer, p_tipo text, p_descricao text)
    returns void
    language sql
    volatile
    security definer
    set search_path = ''
as $$
    insert into public.ir_comprovante_evento (comprovante_id, tipo_evento, descricao, created_at)
    values (p_comprovante_id, p_tipo, p_descricao, (now() at time zone 'utc')::timestamp)
$$;

-- secure_filename do werkzeug (aproximado: so ASCII, espacos viram _, sem caracteres especiais nem pontos nas pontas).
create function financeiro.doc_nome_seguro(p_nome text)
    returns text
    language sql
    immutable
    set search_path = ''
as $$
    select coalesce(nullif(left(btrim(regexp_replace(regexp_replace(
        translate(coalesce(p_nome, ''), 'áàâãäéèêëíìîïóòôõöúùûüçñÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑ',
                  'aaaaaeeeeiiiiooooouuuucnAAAAAEEEEIIIIOOOOOUUUUCN'),
        '\s+', '_', 'g'), '[^A-Za-z0-9_.-]', '', 'g'), '._'), 255), ''), 'comprovante')
$$;

-- POST /api/ir/comprovantes/upload (um arquivo por chamada; a tela envia cada arquivo). Conteudo em base64.
create function financeiro.enviar_comprovante(p_perfil_id integer, p_dados jsonb, p_conteudo text, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_rep    jsonb;
    v_nome   text := coalesce(p_dados ->> 'nome_arquivo', '');
    v_ext    text := case when strpos(coalesce(p_dados ->> 'nome_arquivo', ''), '.') > 0
                          then lower(regexp_replace(p_dados ->> 'nome_arquivo', '^.*\.', '')) else '' end;
    v_mime   text;
    v_bytes  bytea;
    v_hash   text;
    v_ano    integer := coalesce(financeiro.mob_inteiro(p_dados -> 'ano_calendario'), extract(year from financeiro.hoje_brasilia())::integer);
    v_texto  text := p_dados ->> 'texto_extraido';
    v_exist  public.ir_comprovante;
    v_c      public.ir_comprovante;
    v_agora  timestamp := (now() at time zone 'utc')::timestamp;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    v_rep := financeiro.repeticao_documento(p_chave, p_perfil_id, 'enviar_comprovante');
    if v_rep is not null then
        return v_rep;
    end if;
    v_mime := coalesce(nullif(p_dados ->> 'mime_type', ''), case v_ext when 'pdf' then 'application/pdf' when 'png' then 'image/png'
        when 'jpg' then 'image/jpeg' when 'jpeg' then 'image/jpeg' when 'webp' then 'image/webp' else 'application/octet-stream' end);
    if v_nome = '' then raise exception 'Nome de arquivo vazio' using errcode = '22023'; end if;
    if v_ext not in ('pdf', 'png', 'jpg', 'jpeg', 'webp') then raise exception 'Tipo de arquivo nao permitido' using errcode = '22023'; end if;
    if v_mime not in ('application/pdf', 'image/png', 'image/jpeg', 'image/webp') then
        raise exception 'MIME type nao permitido' using errcode = '22023';
    end if;
    begin
        v_bytes := decode(coalesce(p_conteudo, ''), 'base64');
    exception when others then
        raise exception 'Arquivo invalido' using errcode = '22023';
    end;
    if v_bytes is null or length(v_bytes) = 0 then raise exception 'Arquivo vazio' using errcode = '22023'; end if;
    if length(v_bytes) > 10 * 1024 * 1024 then
        raise exception 'Arquivo excede o tamanho maximo permitido' using errcode = '22023';
    end if;
    if not (case v_ext
              when 'pdf' then substring(v_bytes from 1 for 4) = '\x25504446'::bytea
              when 'png' then substring(v_bytes from 1 for 8) = '\x89504e470d0a1a0a'::bytea
              when 'webp' then length(v_bytes) >= 12 and substring(v_bytes from 1 for 4) = '\x52494646'::bytea
                               and substring(v_bytes from 9 for 4) = '\x57454250'::bytea
              else substring(v_bytes from 1 for 3) = '\xffd8ff'::bytea end) then
        raise exception 'Assinatura do arquivo invalida' using errcode = '22023';
    end if;
    v_hash := encode(sha256(v_bytes), 'hex');
    select * into v_exist from public.ir_comprovante c
     where c.hash_arquivo = v_hash and financeiro.pertence_ao_perfil(c.perfil_financeiro_id, p_perfil_id)
     order by c.id limit 1;
    if found then
        return financeiro.registrar_operacao_documento(p_chave, p_perfil_id, 'enviar_comprovante', jsonb_build_object(
            'duplicado', true, 'comprovante_id', v_exist.id, 'mensagem', 'Arquivo ja importado anteriormente.'));
    end if;
    insert into public.ir_comprovante (perfil_financeiro_id, ano_calendario, status, hash_arquivo, created_at, updated_at)
    values (p_perfil_id, v_ano, 'IMPORTADO', v_hash, v_agora, v_agora)
    returning * into v_c;
    insert into public.ir_comprovante_arquivo (comprovante_id, nome_arquivo, mime_type, tamanho_bytes, conteudo, hash_arquivo, created_at)
    values (v_c.id, financeiro.doc_nome_seguro(v_nome), v_mime, length(v_bytes), v_bytes, v_hash, v_agora);
    perform financeiro.doc_evento(v_c.id, 'IMPORTADO', 'Arquivo importado e armazenado no banco.');
    -- Leitura automatica complementar: texto do PDF textual (extraido no navegador); sem ele, revisao manual.
    if v_ext = 'pdf' and length(regexp_replace(coalesce(v_texto, ''), '\s+', '', 'g')) >= 50 then
        update public.ir_comprovante set texto_extraido = v_texto, status = 'PENDENTE_REVISAO', origem_classificacao = 'TEXTO_PDF',
               observacoes = 'Texto extraido do PDF no navegador. Revise prestador, data, valor e categoria.'
         where id = v_c.id;
        perform financeiro.doc_evento(v_c.id, 'TEXTO_EXTRAIDO', 'Texto extraido de PDF textual (leitura no navegador).');
    else
        update public.ir_comprovante set status = 'PENDENTE_REVISAO',
               observacoes = 'Arquivo armazenado. Leitura automatica (OCR) nao disponivel no novo aplicativo; preencha os dados.'
         where id = v_c.id;
        perform financeiro.doc_evento(v_c.id, 'PENDENTE_REVISAO', 'Documento sem texto legivel para leitura automatica.');
    end if;
    return financeiro.registrar_operacao_documento(p_chave, p_perfil_id, 'enviar_comprovante', jsonb_build_object(
        'duplicado', false, 'comprovante_id', v_c.id, 'mensagem', 'Arquivo importado.'));
end
$$;

-- PUT /api/ir/comprovantes/<id> (atualizar_comprovante do Flask).
create function financeiro.atualizar_comprovante(p_perfil_id integer, p_id integer, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_c   public.ir_comprovante;
    v_ano integer;
    v_cat integer;
    v_ir  public.ir_categoria;
    v_vir integer;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    v_c := financeiro.doc_comprovante(p_perfil_id, p_id);
    p_dados := coalesce(p_dados, '{}'::jsonb);
    if p_dados ? 'ano_calendario' then
        v_ano := financeiro.mob_inteiro(p_dados -> 'ano_calendario');
        if coalesce(v_ano, 0) = 0 then raise exception 'Ano-calendario invalido' using errcode = '22023'; end if;
        v_c.ano_calendario := v_ano;
    end if;
    if p_dados ? 'data_documento' then v_c.data_documento := financeiro.mob_data(p_dados ->> 'data_documento'); end if;
    if p_dados ? 'prestador_nome' then v_c.prestador_nome := nullif(left(btrim(coalesce(p_dados ->> 'prestador_nome', '')), 255), ''); end if;
    if p_dados ? 'prestador_cpf_cnpj' then v_c.prestador_cpf_cnpj := nullif(left(btrim(coalesce(p_dados ->> 'prestador_cpf_cnpj', '')), 20), ''); end if;
    if p_dados ? 'tomador_nome' then v_c.tomador_nome := nullif(left(btrim(coalesce(p_dados ->> 'tomador_nome', '')), 255), ''); end if;
    if p_dados ? 'tomador_cpf' then v_c.tomador_cpf := nullif(left(btrim(coalesce(p_dados ->> 'tomador_cpf', '')), 20), ''); end if;
    if p_dados ? 'valor' then v_c.valor := financeiro.numero_seguro(p_dados -> 'valor'); end if;
    if p_dados ? 'categoria_id' then
        v_cat := nullif(financeiro.mob_inteiro(p_dados -> 'categoria_id'), 0);
        if v_cat is not null and not exists (select 1 from public.categoria c where c.id = v_cat) then
            raise exception 'Categoria de Despesa nao encontrada' using errcode = '22023';
        end if;
        v_c.categoria_id := v_cat;
    end if;
    if p_dados ? 'categoria_ir_id' then
        v_c.categoria_ir_id := nullif(financeiro.mob_inteiro(p_dados -> 'categoria_ir_id'), 0);
        select * into v_ir from public.ir_categoria where id = v_c.categoria_ir_id;
        v_c.dedutivel := coalesce(v_ir.dedutivel, v_c.dedutivel);
    elsif p_dados ? 'categoria_id' and v_c.categoria_id is not null then
        select v.categoria_ir_id into v_vir from public.ir_categoria_despesa v
         where v.categoria_id = v_c.categoria_id and v.ativo and financeiro.pertence_ao_perfil(v.perfil_financeiro_id, p_perfil_id)
         order by v.id limit 1;
        if v_vir is not null then
            v_c.categoria_ir_id := v_vir;
            select * into v_ir from public.ir_categoria where id = v_vir;
            v_c.dedutivel := coalesce(v_ir.dedutivel, v_c.dedutivel);
        end if;
    end if;
    if p_dados ? 'dedutivel' then v_c.dedutivel := financeiro.mob_bool(p_dados -> 'dedutivel', false); end if;
    if p_dados ? 'observacoes' then v_c.observacoes := p_dados ->> 'observacoes'; end if;
    if v_c.status not in ('VALIDADO', 'IGNORADO') then
        v_c.status := 'PENDENTE_REVISAO';
    end if;
    update public.ir_comprovante
       set ano_calendario = v_c.ano_calendario, data_documento = v_c.data_documento, prestador_nome = v_c.prestador_nome,
           prestador_cpf_cnpj = v_c.prestador_cpf_cnpj, tomador_nome = v_c.tomador_nome, tomador_cpf = v_c.tomador_cpf,
           valor = v_c.valor, categoria_id = v_c.categoria_id, categoria_ir_id = v_c.categoria_ir_id, dedutivel = v_c.dedutivel,
           observacoes = v_c.observacoes, status = v_c.status, updated_at = (now() at time zone 'utc')::timestamp
     where id = v_c.id;
    perform financeiro.doc_evento(v_c.id, 'PENDENTE_REVISAO', 'Comprovante revisado manualmente.');
    return jsonb_build_object('comprovante_id', v_c.id);
end
$$;

-- POST /api/ir/comprovantes/<id>/validar
create function financeiro.validar_comprovante(p_perfil_id integer, p_id integer)
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
    update public.ir_comprovante set status = 'VALIDADO', updated_at = (now() at time zone 'utc')::timestamp where id = v_c.id;
    perform financeiro.doc_evento(v_c.id, 'VALIDADO', 'Comprovante validado pelo usuario.');
    return jsonb_build_object('comprovante_id', v_c.id);
end
$$;

-- Exclusao segura (nao existe no Flask): so documento sem nenhum vinculo (ativo ou historico).
create function financeiro.excluir_comprovante(p_perfil_id integer, p_id integer)
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

-- =====================================================================================================================
-- Vinculos (POST/PUT/DELETE /api/ir/comprovantes/<id>/vinculos[/<vinculo>]) — DocumentoFiscalService do Flask
-- =====================================================================================================================

create function financeiro.doc_opcao(p_valor text, p_permitidos text[], p_padrao text)
    returns text
    language sql
    immutable
    set search_path = ''
as $$
    select case when upper(btrim(coalesce(nullif(p_valor, ''), p_padrao))) = any (p_permitidos)
                then upper(btrim(coalesce(nullif(p_valor, ''), p_padrao))) else p_padrao end
$$;

-- _obter_entidade + _resumo_entidade: {id, resumo} da entidade do perfil (ou erro do Flask).
create function financeiro.doc_entidade(p_perfil_id integer, p_tipo text, p_id integer)
    returns jsonb
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
    if p_tipo = 'OUTRO' then
        return jsonb_build_object('id', null, 'resumo', null);
    end if;
    if p_id is null or p_id = 0 then
        raise exception 'Entidade vinculavel e obrigatoria' using errcode = '22023';
    end if;
    if p_tipo = 'CONTA' then
        select x.nome || ' - ' || x.instituicao, x.perfil_financeiro_id, true into v_resumo, v_perfil, v_achou from public.conta_bancaria x where x.id = p_id;
    elsif p_tipo = 'DESPESA_PREVISTA' then
        select x.origem_tipo || ' - ' || x.status, x.perfil_financeiro_id, true into v_resumo, v_perfil, v_achou from public.despesa_prevista x where x.id = p_id;
    elsif p_tipo = 'LANCAMENTO' then
        select x.descricao, x.perfil_financeiro_id, true into v_resumo, v_perfil, v_achou from public.lancamento_agregado x where x.id = p_id;
    elsif p_tipo = 'MOVIMENTO_FINANCEIRO' then
        select x.descricao, x.perfil_financeiro_id, true into v_resumo, v_perfil, v_achou from public.movimento_financeiro x where x.id = p_id;
    elsif p_tipo = 'PATRIMONIO' then
        select x.nome, x.perfil_financeiro_id, true into v_resumo, v_perfil, v_achou from public.bem_patrimonial x where x.id = p_id;
    elsif p_tipo = 'FINANCIAMENTO' then
        select x.nome, x.perfil_financeiro_id, true into v_resumo, v_perfil, v_achou from public.financiamento x where x.id = p_id;
    end if;
    if not coalesce(v_achou, false) or not financeiro.pertence_ao_perfil(v_perfil, p_perfil_id) then
        raise exception 'Recurso nao encontrado no perfil financeiro ativo' using errcode = '22023';
    end if;
    return jsonb_build_object('id', p_id, 'resumo', v_resumo);
end
$$;

create function financeiro.criar_vinculo_documento(p_perfil_id integer, p_comprovante_id integer, p_dados jsonb)
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

create function financeiro.doc_vinculo(p_perfil_id integer, p_comprovante_id integer, p_vinculo_id integer)
    returns public.ir_comprovante_vinculo
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v public.ir_comprovante_vinculo;
begin
    perform financeiro.doc_comprovante(p_perfil_id, p_comprovante_id);
    select * into v from public.ir_comprovante_vinculo x
     where x.id = p_vinculo_id and x.comprovante_id = p_comprovante_id and x.ativo
       and financeiro.pertence_ao_perfil(x.perfil_financeiro_id, p_perfil_id) for update;
    if not found then
        raise exception 'Vinculo de lastro nao encontrado' using errcode = '22023';
    end if;
    return v;
end
$$;

create function financeiro.atualizar_vinculo_documento(p_perfil_id integer, p_comprovante_id integer, p_vinculo_id integer, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v public.ir_comprovante_vinculo;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    v := financeiro.doc_vinculo(p_perfil_id, p_comprovante_id, p_vinculo_id);
    if p_dados ? 'tipo_vinculo' then
        v.tipo_vinculo := financeiro.doc_opcao(p_dados ->> 'tipo_vinculo', array['COMPROVANTE', 'NOTA_FISCAL', 'RECIBO', 'CONTRATO', 'GUIA',
            'DOCUMENTO_CONTABIL', 'OUTRO'], v.tipo_vinculo);
    end if;
    if p_dados ? 'natureza' then
        v.natureza := financeiro.doc_opcao(p_dados ->> 'natureza', array['DESPESA_OPERACIONAL', 'PATRIMONIO_IMOBILIZADO', 'SOFTWARE_ASSINATURA',
            'IMPOSTO_TAXA', 'PRO_LABORE', 'DISTRIBUICAO_LUCROS', 'REEMBOLSO', 'EMPRESTIMO', 'ADIANTAMENTO', 'OUTRO'], v.natureza);
    end if;
    if p_dados ? 'status_lastro' then
        v.status_lastro := financeiro.doc_opcao(p_dados ->> 'status_lastro', array['COM_DOCUMENTO', 'SEM_DOCUMENTO', 'PENDENTE', 'DIVERGENTE',
            'VALIDADO', 'NAO_APLICAVEL', 'AGUARDANDO_CONTADOR'], v.status_lastro);
    end if;
    if p_dados ? 'observacoes' then v.observacoes := nullif(left(btrim(coalesce(p_dados ->> 'observacoes', '')), 1000), ''); end if;
    update public.ir_comprovante_vinculo
       set tipo_vinculo = v.tipo_vinculo, natureza = v.natureza, status_lastro = v.status_lastro, observacoes = v.observacoes,
           updated_at = (now() at time zone 'utc')::timestamp
     where id = v.id;
    return jsonb_build_object('vinculo_id', v.id);
end
$$;

-- Remover = inativar (historico preservado), como o Flask.
create function financeiro.remover_vinculo_documento(p_perfil_id integer, p_comprovante_id integer, p_vinculo_id integer)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v public.ir_comprovante_vinculo;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    v := financeiro.doc_vinculo(p_perfil_id, p_comprovante_id, p_vinculo_id);
    update public.ir_comprovante_vinculo set ativo = false, updated_at = (now() at time zone 'utc')::timestamp where id = v.id;
    return jsonb_build_object('vinculo_id', v.id);
end
$$;

-- =====================================================================================================================
-- Despesa ou lancamento a partir do documento (POST /api/ir/comprovantes/<id>/criar-financeiro)
-- =====================================================================================================================

create function financeiro.criar_financeiro_documento(p_perfil_id integer, p_comprovante_id integer, p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_rep     jsonb;
    v_c       public.ir_comprovante;
    v_arquivo text;
    v_destino text := upper(btrim(coalesce(p_dados ->> 'tipo_destino', '')));
    v_forma   text;
    v_cat     integer := nullif(financeiro.mob_inteiro(p_dados -> 'categoria_id'), 0);
    v_catnome text;
    v_valor   numeric;
    v_data    date;
    v_desc    text;
    v_obs     text;
    v_comp    text;
    v_banco   integer := nullif(financeiro.mob_inteiro(coalesce(p_dados -> 'conta_bancaria_id', p_dados -> 'conta_id')), 0);
    v_cartao  integer := nullif(financeiro.mob_inteiro(p_dados -> 'cartao_id'), 0);
    v_cupom   boolean;
    v_item    integer;
    v_conta   integer;
    v_compra  jsonb;
    v_tipo    text;
    v_ent     integer;
    v_resumo  text;
    v_natur   text := 'DESPESA_OPERACIONAL';
    v_irnome  text;
    v_pg      jsonb;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    v_rep := financeiro.repeticao_documento(p_chave, p_perfil_id, 'criar_financeiro_documento');
    if v_rep is not null then
        return v_rep;
    end if;
    v_c := financeiro.doc_comprovante(p_perfil_id, p_comprovante_id);
    if v_destino not in ('DESPESA', 'LANCAMENTO') then
        raise exception 'Escolha se a sugestao sera criada como Despesa ou Lancamento' using errcode = '22023';
    end if;
    -- Correcao: o mesmo documento nao gera duas despesas/lancamentos (o Flask permitia).
    if exists (select 1 from public.ir_comprovante_vinculo v where v.comprovante_id = v_c.id and v.ativo
                 and v.tipo_vinculo = 'DOCUMENTO_FISCAL' and v.tipo_entidade in ('CONTA', 'LANCAMENTO')) then
        raise exception 'Este documento ja gerou uma despesa ou lancamento (vinculo ativo). Nada foi gravado.'
            using errcode = '22023', hint = 'DUPLICADO';
    end if;
    v_forma := case regexp_replace(lower(btrim(coalesce(p_dados ->> 'forma_pagamento', ''))), '[-_\s]+', ' ', 'g')
        when 'pix' then 'pix' when 'dinheiro' then 'dinheiro' when 'cash' then 'dinheiro' when 'cartao' then 'cartao'
        when 'cartao de credito' then 'cartao' when 'credito' then 'cartao' when 'boleto' then 'boleto'
        when 'transferencia' then 'transferencia' when 'transferencia bancaria' then 'transferencia' when 'ted' then 'transferencia'
        when 'doc' then 'transferencia' when 'debito automatico' then 'debito_automatico' when 'debito em conta' then 'debito_automatico'
        else 'outros' end;
    if v_cat is not null then
        select c.nome into v_catnome from public.categoria c where c.id = v_cat and coalesce(c.ativo, true);
        if not found then raise exception 'Categoria de Despesa nao encontrada' using errcode = '22023'; end if;
    end if;
    begin
        v_valor := coalesce(nullif(replace(btrim(coalesce(p_dados ->> 'valor', '')), ',', '.'), '')::numeric, 0);
    exception when others then
        raise exception 'Valor invalido' using errcode = '22023';
    end;
    if v_valor <= 0 then
        raise exception 'Valor deve ser maior que zero para criar a entidade financeira' using errcode = '22023';
    end if;
    v_data := coalesce(financeiro.mob_data(coalesce(p_dados ->> 'data', p_dados ->> 'vencimento', p_dados ->> 'data_vencimento')),
                       v_c.data_documento, v_c.created_at::date, financeiro.hoje_brasilia());
    select a.nome_arquivo into v_arquivo from public.ir_comprovante_arquivo a where a.comprovante_id = v_c.id;
    v_cupom := exists (select 1 from public.ir_comprovante_evento e where e.comprovante_id = v_c.id and e.tipo_evento = 'CUPOM_FISCAL_DETECTADO');
    v_desc := left(btrim(coalesce(nullif(p_dados ->> 'descricao', ''), case
        when nullif(btrim(coalesce(v_c.prestador_nome, '')), '') is not null and v_catnome is not null and not v_cupom
            then btrim(v_c.prestador_nome) || ' - ' || v_catnome
        when nullif(btrim(coalesce(v_c.prestador_nome, '')), '') is not null
            then btrim(v_c.prestador_nome) || case when v_cupom then ' — Cupom fiscal' else '' end
                 || case when v_catnome is not null then ' - ' || v_catnome else '' end
        else case when v_cupom then 'Cupom fiscal - ' else 'Documento fiscal - ' end || coalesce(v_arquivo, v_c.id::text) end)), 200);
    v_obs := left(btrim(coalesce(nullif(p_dados ->> 'observacoes', ''), left(concat_ws(' ',
        'Criado a partir de sugestao financeira revisada de documento fiscal.',
        case when v_arquivo is not null then 'Documento: ' || v_arquivo || '.' end,
        case when v_c.prestador_cpf_cnpj is not null then 'CPF/CNPJ prestador: ' || v_c.prestador_cpf_cnpj || '.' end,
        case when exists (select 1 from public.ir_comprovante_evento e where e.comprovante_id = v_c.id
                           and upper(e.tipo_evento) in ('OCR_EXECUTADO', 'TEXTO_EXTRAIDO_OCR', 'OCR_LIMITADO'))
             then 'Texto de origem extraido por OCR local.' end), 1000))), 1000);
    v_comp := case when length(btrim(coalesce(p_dados ->> 'competencia', ''))) >= 7 then left(btrim(p_dados ->> 'competencia'), 7)
                   else to_char(v_data, 'YYYY-MM') end;
    if v_banco is not null and not exists (select 1 from public.conta_bancaria b where b.id = v_banco and b.status = 'ATIVO'
            and financeiro.pertence_ao_perfil(b.perfil_financeiro_id, p_perfil_id)) then
        raise exception 'Conta bancaria nao encontrada no perfil ativo' using errcode = '22023';
    end if;

    if v_forma = 'cartao' then
        if v_cartao is null then raise exception 'Cartao e obrigatorio quando a forma de pagamento for cartao' using errcode = '22023'; end if;
        if v_cat is null then raise exception 'Categoria de Despesa e obrigatoria para lancamento no cartao' using errcode = '22023'; end if;
    end if;

    if v_destino = 'LANCAMENTO' and v_forma = 'cartao' then
        -- Pelo motor de compras do novo aplicativo; sem fechamento confirmado, ele pede o mes da fatura (mes_fatura).
        v_compra := financeiro.criar_compra(p_perfil_id, jsonb_strip_nulls(jsonb_build_object('cartao_id', v_cartao, 'categoria_id', v_cat,
            'descricao', v_desc, 'valor', v_valor, 'data_compra', v_data, 'total_parcelas', 1, 'observacoes', v_obs,
            'mes_fatura', nullif(p_dados ->> 'mes_fatura', ''))), gen_random_uuid());
        v_ent := (v_compra -> 'lancamentos' ->> 0)::integer;
        v_tipo := 'LANCAMENTO';
    else
        insert into public.item_despesa (perfil_financeiro_id, categoria_id, nome, tipo, descricao, ativo, valor, data_vencimento, pago,
                                         recorrente, tipo_recorrencia, mes_competencia, meio_pagamento, cartao_id, categoria_cartao_id,
                                         criado_em)
        values (p_perfil_id, v_cat, left(v_desc, 100), 'Simples', v_obs, true, v_valor, v_data, false, false, 'mensal', v_comp,
                v_forma, case when v_forma = 'cartao' then v_cartao end,
                case when v_forma = 'cartao' then financeiro.resolver_categoria_cartao(p_perfil_id, v_cartao, v_cat) end,
                (now() at time zone 'utc')::timestamp)
        returning id into v_item;
        insert into public.conta (perfil_financeiro_id, item_despesa_id, mes_referencia, descricao, valor, data_vencimento,
                                  status_pagamento, debito_automatico, conta_bancaria_id, numero_parcela, total_parcelas, observacoes,
                                  is_fatura_cartao, estouro_orcamento, status_fatura, criado_em)
        values (p_perfil_id, v_item, date_trunc('month', v_data)::date, v_desc, v_valor, v_data, 'Pendente', v_forma = 'debito_automatico',
                v_banco, 1, 1, v_obs, false, false, 'ABERTA', (now() at time zone 'utc')::timestamp)
        returning id into v_conta;
        if v_destino = 'LANCAMENTO' then
            -- Lancamento realizado: pago. Com conta bancaria, pelo motor de pagamento (movimento e saldo); sem, baixa
            -- simples como o Flask.
            if v_banco is not null then
                v_pg := financeiro.pagar_despesa(p_perfil_id, v_conta, jsonb_build_object('conta_bancaria_id', v_banco,
                    'data_pagamento', v_data, 'valor_pago', v_valor, 'valor_devido', v_valor), gen_random_uuid());
            else
                update public.conta set status_pagamento = 'Pago', data_pagamento = v_data where id = v_conta;
                update public.item_despesa set pago = true, valor_pago = v_valor, data_pagamento = v_data where id = v_item;
            end if;
        end if;
        v_ent := v_conta;
        v_tipo := 'CONTA';
    end if;

    select upper(btrim(coalesce(ic.nome, ''))) into v_irnome from public.ir_categoria_despesa v join public.ir_categoria ic on ic.id = v.categoria_ir_id
     where v.categoria_id = v_cat and v.ativo and financeiro.pertence_ao_perfil(v.perfil_financeiro_id, p_perfil_id) order by v.id limit 1;
    v_natur := case when v_irnome ~ '(PATRIMONIO|IMOBILIZADO|EQUIPAMENTO)' then 'PATRIMONIO_IMOBILIZADO'
                    when v_irnome ~ '(IMPOSTO|TAXA|GUIA)' then 'IMPOSTO_TAXA' else 'DESPESA_OPERACIONAL' end;
    insert into public.ir_comprovante_vinculo (comprovante_id, perfil_financeiro_id, tipo_entidade, entidade_id, resumo_entidade,
                                               tipo_vinculo, natureza, status_lastro, observacoes, ativo, created_at, updated_at)
    values (v_c.id, p_perfil_id, v_tipo, v_ent, v_desc, 'DOCUMENTO_FISCAL', v_natur, 'COM_DOCUMENTO', left(v_obs, 1000), true,
            (now() at time zone 'utc')::timestamp, (now() at time zone 'utc')::timestamp);
    perform financeiro.doc_evento(v_c.id, 'SUGESTAO_FINANCEIRA_CRIADA',
        format('Sugestao confirmada como %s e vinculada a %s #%s.', lower(v_destino), v_tipo, v_ent));
    perform financeiro.doc_evento(v_c.id, case when v_destino = 'DESPESA' then 'DESPESA_CRIADA_A_PARTIR_DOCUMENTO' else 'LANCAMENTO_CRIADO_A_PARTIR_DOCUMENTO' end,
        case when v_destino = 'DESPESA' then 'Despesa criada a partir de sugestao financeira revisada.'
             else 'Lancamento criado a partir de sugestao financeira revisada.' end);
    update public.ir_comprovante set updated_at = (now() at time zone 'utc')::timestamp where id = v_c.id;
    return financeiro.registrar_operacao_documento(p_chave, p_perfil_id, 'criar_financeiro_documento', jsonb_build_object(
        'tipo_destino', v_destino, 'tipo_entidade', v_tipo, 'entidade_id', v_ent, 'conta_id', v_conta, 'item_despesa_id', v_item));
end
$$;

-- =====================================================================================================================
-- Privilegios
-- =====================================================================================================================

revoke execute on function financeiro.repeticao_documento(uuid, integer, text) from public, anon, authenticated;
revoke execute on function financeiro.registrar_operacao_documento(uuid, integer, text, jsonb) from public, anon, authenticated;
revoke execute on function financeiro.doc_comprovante(integer, integer) from public, anon, authenticated;
revoke execute on function financeiro.doc_evento(integer, text, text) from public, anon, authenticated;
revoke execute on function financeiro.doc_nome_seguro(text) from public, anon, authenticated;
revoke execute on function financeiro.doc_opcao(text, text[], text) from public, anon, authenticated;
revoke execute on function financeiro.doc_entidade(integer, text, integer) from public, anon, authenticated;
revoke execute on function financeiro.doc_vinculo(integer, integer, integer) from public, anon, authenticated;

revoke execute on function financeiro.enviar_comprovante(integer, jsonb, text, uuid) from public, anon;
revoke execute on function financeiro.atualizar_comprovante(integer, integer, jsonb) from public, anon;
revoke execute on function financeiro.validar_comprovante(integer, integer) from public, anon;
revoke execute on function financeiro.excluir_comprovante(integer, integer) from public, anon;
revoke execute on function financeiro.criar_vinculo_documento(integer, integer, jsonb) from public, anon;
revoke execute on function financeiro.atualizar_vinculo_documento(integer, integer, integer, jsonb) from public, anon;
revoke execute on function financeiro.remover_vinculo_documento(integer, integer, integer) from public, anon;
revoke execute on function financeiro.criar_financeiro_documento(integer, integer, jsonb, uuid) from public, anon;

grant execute on function financeiro.enviar_comprovante(integer, jsonb, text, uuid) to authenticated;
grant execute on function financeiro.atualizar_comprovante(integer, integer, jsonb) to authenticated;
grant execute on function financeiro.validar_comprovante(integer, integer) to authenticated;
grant execute on function financeiro.excluir_comprovante(integer, integer) to authenticated;
grant execute on function financeiro.criar_vinculo_documento(integer, integer, jsonb) to authenticated;
grant execute on function financeiro.atualizar_vinculo_documento(integer, integer, integer, jsonb) to authenticated;
grant execute on function financeiro.remover_vinculo_documento(integer, integer, integer) to authenticated;
grant execute on function financeiro.criar_financeiro_documento(integer, integer, jsonb, uuid) to authenticated;
