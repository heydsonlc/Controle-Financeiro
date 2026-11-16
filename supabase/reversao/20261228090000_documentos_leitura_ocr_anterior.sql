-- Reversao do FIN-REG-08 (20261228090000): devolve financeiro.enviar_comprovante a definicao de 20261128090000 (texto so de
-- PDF, sem origem de OCR nem dados conferidos). Nenhum dado e alterado: documentos ja enviados com texto de OCR o mantem.
-- NAO aplicar no Supabase remoto sem autorizacao especifica.

create or replace function financeiro.enviar_comprovante(p_perfil_id integer, p_dados jsonb, p_conteudo text, p_chave uuid)
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

revoke execute on function financeiro.enviar_comprovante(integer, jsonb, text, uuid) from public, anon;
grant execute on function financeiro.enviar_comprovante(integer, jsonb, text, uuid) to authenticated;
