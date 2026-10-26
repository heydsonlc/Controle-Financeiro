-- FIN-FIDELIDADE-DOCUMENTOS-1 (arquivos, leitura) — o arquivo de um comprovante/documento fiscal, como o
-- GET /api/ir/comprovantes/<id>/arquivo do Flask (send_file inline), para "Abrir arquivo" em Imposto de Renda e Patrimonio.
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261118090000).
-- Depende de 20261113090000 (financeiro.tipo_perfil_ir).
-- Validada em cluster local descartavel (tests/test_supabase_arquivo_comprovante.py, comparada com o Flask).
-- Docs: docs/FIN_FIDELIDADE_DOCUMENTOS_1.md.
--
-- Regras do Flask (IrDocumentoService.obter_arquivo): comprovante do perfil (regra de perfil nulo = Pessoal), senao
-- "Comprovante nao encontrado"; sem arquivo, "Arquivo do comprovante nao encontrado". O conteudo vai em base64 (o
-- navegador monta o arquivo e abre numa nova aba). So leitura: envio, troca e exclusao de arquivo continuam no Flask.
-- Nenhuma tabela nova. Nenhum dado existente e alterado.

create function financeiro.arquivo_comprovante_tela(p_perfil_id integer, p_comprovante_id integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_c public.ir_comprovante;
    v_a public.ir_comprovante_arquivo;
begin
    perform financeiro.tipo_perfil_ir(p_perfil_id);  -- conferencia de acesso ao perfil
    select * into v_c from public.ir_comprovante c where c.id = p_comprovante_id;
    if not found or not financeiro.pertence_ao_perfil(v_c.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Comprovante nao encontrado' using errcode = '22023', hint = 'NAO_ENCONTRADA';
    end if;
    select * into v_a from public.ir_comprovante_arquivo a where a.comprovante_id = v_c.id order by a.id limit 1;
    if not found then
        raise exception 'Arquivo do comprovante nao encontrado' using errcode = '22023', hint = 'NAO_ENCONTRADA';
    end if;
    return jsonb_build_object('nome_arquivo', v_a.nome_arquivo, 'mime_type', v_a.mime_type, 'tamanho_bytes', v_a.tamanho_bytes,
                              'conteudo_base64', translate(encode(v_a.conteudo, 'base64'), E'\n', ''));
end
$$;

revoke execute on function financeiro.arquivo_comprovante_tela(integer, integer) from public, anon;
grant execute on function financeiro.arquivo_comprovante_tela(integer, integer) to authenticated;
