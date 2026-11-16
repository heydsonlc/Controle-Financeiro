-- FIN-REG-08 — leitura automatica de documentos fiscais: o envio guarda o texto lido no navegador (texto de PDF digital
-- ou OCR de imagem/PDF digitalizado) com a origem da leitura e, quando o usuario conferiu os dados antes de enviar (celular),
-- grava os dados conferidos na mesma transacao.
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261228090000).
-- Depende de 20261128090000 (enviar_comprovante, atualizar_comprovante, idempotencia). Validada em cluster local descartavel
-- (tests/test_supabase_documentos_leitura.py). Docs: docs/FIN_REG_08_LEITURA_CLASSIFICACAO_DOCUMENTAL.md.
--
-- So a funcao financeiro.enviar_comprovante muda (mesma assinatura, mesmas permissoes). Nenhuma tabela, coluna ou dado novo
-- ou alterado. O que muda:
-- 1. p_dados.texto_origem ('TEXTO_PDF', 'OCR_IMAGEM' ou 'OCR_PDF'): o texto extraido passa a ser guardado tambem para imagens
--    lidas por OCR (antes so PDF). A origem fica em origem_classificacao e no evento (TEXTO_EXTRAIDO ou TEXTO_EXTRAIDO_OCR,
--    os nomes do Flask). Origem incompativel com o tipo do arquivo e recusada. Sem texto_origem, o comportamento antigo:
--    PDF com texto vira TEXTO_PDF.
-- 2. p_dados.leitura ('NFSE_GOIANIA' ou 'CUPOM_FISCAL'): o modelo reconhecido pelo navegador vira evento (os mesmos do Flask;
--    CUPOM_FISCAL_DETECTADO ja e lido pela sugestao financeira). So rotulo: nenhum campo e preenchido por ele.
-- 3. p_dados.revisao (objeto): os dados que o usuario conferiu antes de enviar, aplicados por atualizar_comprovante na mesma
--    transacao (falha = nada gravado). Arquivo repetido (mesmo SHA-256 no perfil) devolve o existente SEM aplicar a revisao:
--    nada do documento ja guardado e sobrescrito.
-- O documento continua PENDENTE_REVISAO: a leitura so sugere. Nao ha status CLASSIFICADO nem validacao automatica.
-- Reversao: supabase/reversao/20261228090000_documentos_leitura_ocr_anterior.sql (a definicao de 20261128090000).

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
    v_origem text := nullif(upper(btrim(coalesce(p_dados ->> 'texto_origem', ''))), '');
    v_leitura text := nullif(upper(btrim(coalesce(p_dados ->> 'leitura', ''))), '');
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
    -- FIN-REG-08: a origem da leitura tem de combinar com o tipo do arquivo.
    if v_origem is not null and not ((v_origem in ('TEXTO_PDF', 'OCR_PDF') and v_ext = 'pdf')
                                     or (v_origem = 'OCR_IMAGEM' and v_ext in ('png', 'jpg', 'jpeg', 'webp'))) then
        raise exception 'Origem da leitura invalida para este arquivo' using errcode = '22023';
    end if;
    if v_leitura is not null and v_leitura not in ('NFSE_GOIANIA', 'CUPOM_FISCAL') then
        raise exception 'Modelo de documento invalido' using errcode = '22023';
    end if;
    if p_dados ? 'revisao' and jsonb_typeof(p_dados -> 'revisao') <> 'object' then
        raise exception 'Dados conferidos invalidos' using errcode = '22023';
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
        -- Repetido: devolve o existente e nao aplica a revisao (nada do documento guardado e sobrescrito).
        return financeiro.registrar_operacao_documento(p_chave, p_perfil_id, 'enviar_comprovante', jsonb_build_object(
            'duplicado', true, 'comprovante_id', v_exist.id, 'mensagem', 'Arquivo ja importado anteriormente.'));
    end if;
    insert into public.ir_comprovante (perfil_financeiro_id, ano_calendario, status, hash_arquivo, created_at, updated_at)
    values (p_perfil_id, v_ano, 'IMPORTADO', v_hash, v_agora, v_agora)
    returning * into v_c;
    insert into public.ir_comprovante_arquivo (comprovante_id, nome_arquivo, mime_type, tamanho_bytes, conteudo, hash_arquivo, created_at)
    values (v_c.id, financeiro.doc_nome_seguro(v_nome), v_mime, length(v_bytes), v_bytes, v_hash, v_agora);
    perform financeiro.doc_evento(v_c.id, 'IMPORTADO', 'Arquivo importado e armazenado no banco.');
    -- Leitura automatica complementar (no navegador): texto de PDF digital ou OCR. Sem texto legivel, revisao manual.
    if v_origem is null and v_ext = 'pdf' then
        v_origem := 'TEXTO_PDF';  -- envio sem a origem (comportamento anterior)
    end if;
    if v_origem is not null and length(regexp_replace(coalesce(v_texto, ''), '\s+', '', 'g')) >= 50 then
        update public.ir_comprovante set texto_extraido = v_texto, status = 'PENDENTE_REVISAO', origem_classificacao = v_origem,
               observacoes = case when v_origem = 'TEXTO_PDF'
                                  then 'Texto extraido do PDF no navegador. Revise prestador, data, valor e categoria.'
                                  else 'Texto lido por OCR no navegador. Confira valor, data e CPF/CNPJ antes de validar.' end
         where id = v_c.id;
        if v_origem = 'TEXTO_PDF' then
            perform financeiro.doc_evento(v_c.id, 'TEXTO_EXTRAIDO', 'Texto extraido de PDF textual (leitura no navegador).');
        else
            perform financeiro.doc_evento(v_c.id, 'TEXTO_EXTRAIDO_OCR', case when v_origem = 'OCR_PDF'
                then 'Texto extraido por OCR no navegador (PDF digitalizado).' else 'Texto extraido por OCR no navegador (imagem).' end);
        end if;
        if v_leitura = 'NFSE_GOIANIA' then
            perform financeiro.doc_evento(v_c.id, case when v_origem = 'TEXTO_PDF' then 'TEXTO_EXTRAIDO' else 'TEXTO_EXTRAIDO_OCR' end,
                                          'Parser especifico NFS-e Goiania aplicado.');
        elsif v_leitura = 'CUPOM_FISCAL' then
            perform financeiro.doc_evento(v_c.id, 'CUPOM_FISCAL_DETECTADO', 'Cupom fiscal detectado na leitura no navegador.');
        end if;
    else
        update public.ir_comprovante set status = 'PENDENTE_REVISAO',
               observacoes = 'Arquivo armazenado sem texto legivel para leitura automatica; preencha os dados.'
         where id = v_c.id;
        perform financeiro.doc_evento(v_c.id, 'PENDENTE_REVISAO', 'Documento sem texto legivel para leitura automatica.');
    end if;
    -- Dados conferidos pelo usuario antes do envio: as regras da revisao (atualizar_comprovante), na mesma transacao.
    if p_dados ? 'revisao' then
        perform financeiro.atualizar_comprovante(p_perfil_id, v_c.id, p_dados -> 'revisao');
    end if;
    return financeiro.registrar_operacao_documento(p_chave, p_perfil_id, 'enviar_comprovante', jsonb_build_object(
        'duplicado', false, 'comprovante_id', v_c.id, 'mensagem', 'Arquivo importado.'));
end
$$;

revoke execute on function financeiro.enviar_comprovante(integer, jsonb, text, uuid) from public, anon;
grant execute on function financeiro.enviar_comprovante(integer, jsonb, text, uuid) to authenticated;
