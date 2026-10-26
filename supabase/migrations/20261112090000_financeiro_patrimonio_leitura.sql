-- FIN-FIDELIDADE-PATRIMONIO-1 (fase 1) — leitura da tela original de Patrimonio do Flask (so consulta).
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261112090000).
-- Validada em cluster local descartavel (tests/test_supabase_patrimonio_leitura.py, comparada com o Flask).
-- Docs: docs/FIN_FIDELIDADE_PATRIMONIO_1.md.
--
-- Reproduz as rotas GET de routes/patrimonio.py no formato do Flask:
-- - caixinhas (ContaPatrimonio.to_dict) e transferencias (Transferencia.to_dict + nomes das contas);
-- - bens do perfil Empresa (PatrimonioEmpresarialService.listar_bens / resumo / serializar_bem), com o documento
--   fiscal vinculado (ir_comprovante_vinculo ativo mais recente) e a imagem escolhida entre as do sistema.
-- Nada e gravado: cadastro, edicao, inativacao, transferencias, exportacoes e vinculos continuam no Flask (escritor
-- unico) nesta fase. Nenhuma tabela nova. Nenhum dado existente e alterado.

-- Timestamp sem fuso como datetime.isoformat() do Python (micros so quando diferentes de zero). Interna.
create function financeiro.iso_python(p_valor timestamp)
    returns text
    language sql
    immutable
    set search_path = ''
as $$
    select case when p_valor is null then null
                else to_char(p_valor, 'YYYY-MM-DD"T"HH24:MI:SS')
                     || case when extract(microseconds from p_valor)::bigint % 1000000 <> 0
                             then '.' || to_char(p_valor, 'US') else '' end end
$$;

-- Imagens de bens do sistema (frontend/static/img/patrimonio*, versionadas), na ordem do Flask (nome sem caixa).
create function financeiro.imagens_patrimonio()
    returns jsonb
    language sql
    immutable
    set search_path = ''
as $$
    select coalesce(jsonb_agg(jsonb_build_object(
               'arquivo', a, 'url', '/static/img/' || a,
               'label', coalesce(nullif(initcap(btrim(replace(replace(replace(replace(
                            regexp_replace(a, '\.[^.]*$', ''), 'Patrimonio_', ''), 'patrimonio_', ''), '_', ' '), '-', ' '))), ''),
                                 'Patrimonio'))
           order by lower(a)), '[]'::jsonb)
      from unnest(array['Patrimonio_cadeira_ergonomica.jpg', 'Patrimonio_notebook.jpg', 'patrimonio_ar_condicionado.png',
                        'patrimonio_impressora.png', 'patrimonio_monitor.png', 'patrimonio_placa_de_video.png',
                        'patrimonio_webcam.png']) a
$$;

-- Documento fiscal do bem (PatrimonioEmpresarialService._documento_do_bem). Interna.
create function financeiro.documento_do_bem(p_bem public.bem_patrimonial)
    returns jsonb
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select jsonb_build_object(
               'id', c.id,
               'label', coalesce(nullif(c.prestador_nome, ''), 'Documento fiscal') || ' - '
                        || coalesce(c.data_documento::text, 'sem data') || ' - R$ '
                        || translate(to_char(coalesce(c.valor, 0), 'FM999,999,999,990.00'), ',.', '.,'),
               'prestador_nome', c.prestador_nome, 'prestador_cpf_cnpj', c.prestador_cpf_cnpj,
               'data_documento', c.data_documento, 'valor', c.valor,
               'categoria_nome', (select cat.nome from public.categoria cat where cat.id = c.categoria_id),
               'categoria_ir_nome', (select ic.nome from public.ir_categoria ic where ic.id = c.categoria_ir_id),
               'status', c.status,
               'arquivo', (select jsonb_build_object('id', a.id, 'comprovante_id', a.comprovante_id,
                                                     'nome_arquivo', a.nome_arquivo, 'mime_type', a.mime_type,
                                                     'tamanho_bytes', a.tamanho_bytes, 'hash_arquivo', a.hash_arquivo,
                                                     'created_at', financeiro.iso_python(a.created_at))
                             from public.ir_comprovante_arquivo a where a.comprovante_id = c.id order by a.id limit 1),
               'download_url', '/api/ir/comprovantes/' || c.id || '/arquivo',
               'vinculo', jsonb_build_object('id', v.id, 'comprovante_id', v.comprovante_id,
                                             'perfil_financeiro_id', v.perfil_financeiro_id, 'tipo_entidade', v.tipo_entidade,
                                             'entidade_id', v.entidade_id, 'resumo_entidade', v.resumo_entidade,
                                             'tipo_vinculo', v.tipo_vinculo, 'natureza', v.natureza,
                                             'status_lastro', v.status_lastro, 'observacoes', v.observacoes,
                                             'ativo', coalesce(v.ativo, false),
                                             'created_at', financeiro.iso_python(v.created_at),
                                             'updated_at', financeiro.iso_python(v.updated_at)),
               'tipo_vinculo_label', case v.tipo_vinculo when 'NOTA_FISCAL' then 'NF vinculada' when 'COMPROVANTE' then 'Comprovante'
                                         when 'RECIBO' then 'Recibo' when 'CONTRATO' then 'Contrato'
                                         when 'DOCUMENTO_CONTABIL' then 'Documento contabil' else 'Documento' end,
               'status_lastro', v.status_lastro, 'natureza', v.natureza)
      from public.ir_comprovante_vinculo v
      join public.ir_comprovante c on c.id = v.comprovante_id
     where v.perfil_financeiro_id = p_bem.perfil_financeiro_id and v.tipo_entidade = 'PATRIMONIO'
       and v.entidade_id = p_bem.id and v.ativo
     order by v.created_at desc, v.id desc
     limit 1
$$;

-- PatrimonioEmpresarialService.serializar_bem(bem, include_documento=True). Interna.
create function financeiro.bem_flask(p_bem public.bem_patrimonial)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_doc    jsonb := financeiro.documento_do_bem(p_bem);
    v_texto  text := lower(concat_ws(' ', coalesce(p_bem.nome, ''), coalesce(p_bem.categoria, ''), coalesce(p_bem.descricao, '')));
    v_imagem text := regexp_replace(btrim(coalesce(p_bem.imagem_arquivo, '')), '^.*[\\/]', '');
begin
    return jsonb_build_object(
        'id', p_bem.id, 'perfil_financeiro_id', p_bem.perfil_financeiro_id, 'nome', p_bem.nome, 'codigo', p_bem.codigo,
        'categoria', p_bem.categoria, 'descricao', p_bem.descricao, 'fornecedor', p_bem.fornecedor,
        'documento_numero', p_bem.documento_numero, 'imagem_arquivo', p_bem.imagem_arquivo,
        'data_aquisicao', p_bem.data_aquisicao, 'valor_aquisicao', coalesce(p_bem.valor_aquisicao, 0),
        'vida_util_meses', p_bem.vida_util_meses, 'depreciacao_mensal', p_bem.depreciacao_mensal,
        'centro_custo', p_bem.centro_custo, 'localizacao', p_bem.localizacao, 'responsavel', p_bem.responsavel,
        'status', p_bem.status, 'status_documental', p_bem.status_documental, 'observacoes', p_bem.observacoes,
        'created_at', financeiro.iso_python(p_bem.created_at), 'updated_at', financeiro.iso_python(p_bem.updated_at),
        'status_label', case p_bem.status when 'ATIVO' then 'Ativo' when 'INATIVO' then 'Inativo' when 'BAIXADO' then 'Baixado'
                                          when 'EM_REVISAO' then 'Em revisao' else coalesce(nullif(p_bem.status, ''), '-') end,
        'status_documental_label', case p_bem.status_documental when 'COM_LASTRO' then 'Com lastro'
                                       when 'SEM_DOCUMENTO' then 'Sem documento' when 'PENDENTE' then 'Pendente'
                                       when 'AGUARDANDO_CONTADOR' then 'Aguardando contador' when 'DIVERGENTE' then 'Divergente'
                                       when 'NAO_APLICAVEL' then 'Nao aplicavel'
                                       else coalesce(nullif(p_bem.status_documental, ''), '-') end,
        'imagem_chave', case
            when v_texto ~ '(notebook|laptop|computador)' then 'notebook'
            when v_texto ~ '(cadeira|ergonomica|ergonômica)' then 'cadeira'
            when v_texto ~ '(mesa|reuniao|reunião|movel|móvel|moveis|móveis)' then 'moveis'
            when v_texto ~ '(impressora|laser)' then 'impressora'
            when v_texto ~ '(ar-condicionado|ar condicionado|climatizacao|climatização)' then 'ar_condicionado'
            when strpos(v_texto, 'monitor') > 0 then 'monitor'
            when v_texto ~ '(webcam|camera|câmera)' then 'webcam'
            when v_texto ~ '(placa de video|placa de vídeo|gpu)' then 'placa_video'
            else 'equipamento' end,
        'imagem_url', (select i ->> 'url' from jsonb_array_elements(financeiro.imagens_patrimonio()) i
                        where i ->> 'arquivo' = v_imagem),
        'documento', v_doc,
        'documento_label', case when v_doc is null then 'Sem documento'
                                else coalesce(v_doc ->> 'tipo_vinculo_label', 'Documento') || ' '
                                     || coalesce(nullif(p_bem.documento_numero, ''), 'DOC-' || (v_doc ->> 'id')) end);
end
$$;

-- Perfil do tipo Empresa (os bens so existem nele). Interna.
create function financeiro.perfil_empresa(p_perfil_id integer)
    returns boolean
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select coalesce((select p.tipo = 'EMPRESA' from public.perfil_financeiro p where p.id = p_perfil_id), false)
$$;

-- GET /api/patrimonio/contas[?ativo=]: ativas por padrao; total so das ativas.
create function financeiro.patrimonio_contas_tela(p_perfil_id integer, p_ativo boolean)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_lista jsonb;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    select coalesce(jsonb_agg(jsonb_build_object(
               'id', c.id, 'perfil_financeiro_id', c.perfil_financeiro_id, 'nome', c.nome, 'tipo', c.tipo,
               'saldo_inicial', c.saldo_inicial, 'saldo_atual', c.saldo_atual, 'meta', nullif(c.meta, 0), 'cor', c.cor,
               'ativo', c.ativo, 'observacoes', c.observacoes) order by c.id), '[]'::jsonb)
      into v_lista
      from public.conta_patrimonio c
     where financeiro.pertence_ao_perfil(c.perfil_financeiro_id, p_perfil_id)
       and c.ativo is not distinct from coalesce(p_ativo, true);
    return jsonb_build_object('data', v_lista, 'total', jsonb_array_length(v_lista),
                              'total_patrimonio', coalesce((select sum((x ->> 'saldo_atual')::numeric)
                                                              from jsonb_array_elements(v_lista) x
                                                             where (x ->> 'ativo')::boolean), 0));
end
$$;

-- GET /api/patrimonio/contas/<id>
create function financeiro.patrimonio_conta_tela(p_perfil_id integer, p_conta_id integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_conta public.conta_patrimonio;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    select * into v_conta from public.conta_patrimonio c where c.id = p_conta_id;
    if not found or not financeiro.pertence_ao_perfil(v_conta.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Conta não encontrada' using errcode = '22023', hint = 'NAO_ENCONTRADA';
    end if;
    return jsonb_build_object('id', v_conta.id, 'perfil_financeiro_id', v_conta.perfil_financeiro_id, 'nome', v_conta.nome,
                              'tipo', v_conta.tipo, 'saldo_inicial', v_conta.saldo_inicial, 'saldo_atual', v_conta.saldo_atual,
                              'meta', nullif(v_conta.meta, 0), 'cor', v_conta.cor, 'ativo', v_conta.ativo,
                              'observacoes', v_conta.observacoes);
end
$$;

-- GET /api/patrimonio/transferencias[?data_inicio=&data_fim=&conta_id=] e /transferencias/<id> (p_id).
create function financeiro.patrimonio_transferencias_tela(p_perfil_id integer, p_data_inicio date, p_data_fim date,
                                                          p_conta_id integer, p_id integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_lista jsonb;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    select coalesce(jsonb_agg(jsonb_build_object(
               'id', t.id, 'perfil_financeiro_id', t.perfil_financeiro_id, 'conta_origem_id', t.conta_origem_id,
               'conta_destino_id', t.conta_destino_id, 'valor', t.valor, 'data_transferencia', t.data_transferencia,
               'descricao', t.descricao, 'observacoes', t.observacoes,
               'conta_origem_nome', (select o.nome from public.conta_patrimonio o where o.id = t.conta_origem_id),
               'conta_destino_nome', (select d.nome from public.conta_patrimonio d where d.id = t.conta_destino_id))
           order by t.data_transferencia desc, t.id), '[]'::jsonb)  -- empate: ordem de insercao (o Flask nao desempata)
      into v_lista
      from public.transferencia t
     where financeiro.pertence_ao_perfil(t.perfil_financeiro_id, p_perfil_id)
       and (p_data_inicio is null or t.data_transferencia >= p_data_inicio)
       and (p_data_fim is null or t.data_transferencia <= p_data_fim)
       and (p_conta_id is null or p_conta_id in (t.conta_origem_id, t.conta_destino_id))
       and (p_id is null or t.id = p_id);
    if p_id is not null and jsonb_array_length(v_lista) = 0 then
        raise exception 'Transferência não encontrada' using errcode = '22023', hint = 'NAO_ENCONTRADA';
    end if;
    return v_lista;
end
$$;

-- GET /api/patrimonio/bens (filtros: categoria, status, documento|status_documental, ano, busca|q) e /bens/<id>.
-- Perfil que nao e Empresa: lista vazia (detalhe: 403, como o Flask).
create function financeiro.patrimonio_bens_tela(p_perfil_id integer, p_filtros jsonb, p_bem_id integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_f         jsonb := coalesce(p_filtros, '{}'::jsonb);
    v_categoria text := left(nullif(btrim(coalesce(v_f ->> 'categoria', '')), ''), 80);
    v_status    text := upper(btrim(coalesce(v_f ->> 'status', '')));
    v_doc       text := upper(btrim(coalesce(nullif(v_f ->> 'documento', ''), v_f ->> 'status_documental', '')));
    v_ano_txt   text := btrim(coalesce(v_f ->> 'ano', ''));
    v_ano       integer;
    v_busca     text := left(nullif(btrim(coalesce(nullif(v_f ->> 'busca', ''), v_f ->> 'q', '')), ''), 120);
    v_lista     jsonb;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if not financeiro.perfil_empresa(p_perfil_id) then
        if p_bem_id is not null then
            raise exception 'Patrimonio empresarial disponivel apenas no perfil Empresa' using errcode = '42501';
        end if;
        return '[]'::jsonb;
    end if;
    if v_status not in ('ATIVO', 'INATIVO', 'BAIXADO', 'EM_REVISAO') then
        v_status := null;
    end if;
    v_doc := case v_doc when 'COM_DOCUMENTO' then 'COM_LASTRO' when 'VALIDADO' then 'COM_LASTRO'
                        when 'SEM_LASTRO' then 'SEM_DOCUMENTO' else v_doc end;
    if v_doc not in ('COM_LASTRO', 'SEM_DOCUMENTO', 'PENDENTE', 'AGUARDANDO_CONTADOR', 'DIVERGENTE', 'NAO_APLICAVEL') then
        v_doc := null;
    end if;
    if v_ano_txt ~ '^[+-]?\d{1,9}$' then
        v_ano := nullif(v_ano_txt::integer, 0);
    end if;
    select coalesce(jsonb_agg(financeiro.bem_flask(b) order by b.data_aquisicao desc, b.id desc), '[]'::jsonb)
      into v_lista
      from public.bem_patrimonial b
     where b.perfil_financeiro_id = p_perfil_id
       and (p_bem_id is null or b.id = p_bem_id)
       and (v_categoria is null or upper(v_categoria) = 'TODAS' or b.categoria = v_categoria)
       and (v_status is null or b.status = v_status)
       and (v_doc is null or b.status_documental = v_doc)
       and (v_ano is null or (b.data_aquisicao >= make_date(v_ano, 1, 1) and b.data_aquisicao <= make_date(v_ano, 12, 31)))
       and (v_busca is null or b.nome ilike '%' || v_busca || '%' or b.codigo ilike '%' || v_busca || '%'
            or b.categoria ilike '%' || v_busca || '%' or b.fornecedor ilike '%' || v_busca || '%'
            or b.documento_numero ilike '%' || v_busca || '%');
    if p_bem_id is not null then
        if jsonb_array_length(v_lista) = 0 then
            raise exception 'Bem patrimonial nao encontrado no perfil ativo' using errcode = '22023', hint = 'NAO_ENCONTRADA';
        end if;
        return v_lista -> 0;
    end if;
    return v_lista;
end
$$;

-- GET /api/patrimonio/bens/resumo (PatrimonioEmpresarialService.resumo; ano corrente em Brasilia).
create function financeiro.patrimonio_resumo_tela(p_perfil_id integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_ano       integer := extract(year from (now() at time zone 'America/Sao_Paulo'))::integer;
    v_total     numeric;
    v_qtd       integer;
    v_lastro    integer;
    v_pend      integer;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if not financeiro.perfil_empresa(p_perfil_id) then
        return jsonb_build_object('modo', 'PESSOAL', 'patrimonio_total', 0, 'bens_cadastrados', 0, 'bens_com_lastro', 0,
                                  'pendencias_documentais', 0, 'aquisicoes_ano', jsonb_build_object('quantidade', 0, 'valor', 0),
                                  'composicao', '[]'::jsonb, 'pendencias_prioritarias', '[]'::jsonb);
    end if;
    select coalesce(sum(round(coalesce(b.valor_aquisicao, 0), 2)), 0), count(*),
           count(*) filter (where b.status_documental in ('COM_LASTRO', 'COM_DOCUMENTO', 'VALIDADO')),
           count(*) filter (where b.status_documental in ('SEM_DOCUMENTO', 'PENDENTE', 'AGUARDANDO_CONTADOR', 'DIVERGENTE'))
      into v_total, v_qtd, v_lastro, v_pend
      from public.bem_patrimonial b where b.perfil_financeiro_id = p_perfil_id;
    return jsonb_build_object(
        'modo', 'EMPRESA', 'patrimonio_total', v_total, 'bens_cadastrados', v_qtd, 'bens_com_lastro', v_lastro,
        'percentual_com_lastro', case when v_qtd > 0 then round(v_lastro * 100.0 / v_qtd, 1) else 0 end,
        'pendencias_documentais', v_pend,
        'aquisicoes_ano', (select jsonb_build_object('quantidade', count(*), 'valor', coalesce(sum(round(coalesce(b.valor_aquisicao, 0), 2)), 0))
                             from public.bem_patrimonial b
                            where b.perfil_financeiro_id = p_perfil_id and extract(year from b.data_aquisicao) = v_ano),
        'composicao', coalesce((
            select jsonb_agg(jsonb_build_object('categoria', g.categoria, 'valor', g.valor,
                                                'percentual', case when v_total <> 0 then round(g.valor * 100 / v_total, 1) else 0 end)
                             order by g.valor desc, g.primeiro)
              from (select coalesce(nullif(b.categoria, ''), 'Sem categoria') categoria,
                           sum(round(coalesce(b.valor_aquisicao, 0), 2)) valor, min(b.id) primeiro
                      from public.bem_patrimonial b where b.perfil_financeiro_id = p_perfil_id
                     group by 1) g), '[]'::jsonb),
        'pendencias_prioritarias', coalesce((
            select jsonb_agg(financeiro.bem_flask(x) order by x.data_aquisicao desc nulls last, x.id desc)
              from (select * from public.bem_patrimonial b
                     where b.perfil_financeiro_id = p_perfil_id
                       and b.status_documental in ('SEM_DOCUMENTO', 'PENDENTE', 'AGUARDANDO_CONTADOR', 'DIVERGENTE')
                     order by b.data_aquisicao desc nulls last, b.id desc limit 6) x), '[]'::jsonb));
end
$$;

revoke execute on function financeiro.iso_python(timestamp) from public, anon, authenticated;
revoke execute on function financeiro.imagens_patrimonio() from public, anon;
revoke execute on function financeiro.documento_do_bem(public.bem_patrimonial) from public, anon, authenticated;
revoke execute on function financeiro.bem_flask(public.bem_patrimonial) from public, anon, authenticated;
revoke execute on function financeiro.perfil_empresa(integer) from public, anon, authenticated;
revoke execute on function financeiro.patrimonio_contas_tela(integer, boolean) from public, anon;
revoke execute on function financeiro.patrimonio_conta_tela(integer, integer) from public, anon;
revoke execute on function financeiro.patrimonio_transferencias_tela(integer, date, date, integer, integer) from public, anon;
revoke execute on function financeiro.patrimonio_bens_tela(integer, jsonb, integer) from public, anon;
revoke execute on function financeiro.patrimonio_resumo_tela(integer) from public, anon;
grant execute on function financeiro.imagens_patrimonio() to authenticated;
grant execute on function financeiro.patrimonio_contas_tela(integer, boolean) to authenticated;
grant execute on function financeiro.patrimonio_conta_tela(integer, integer) to authenticated;
grant execute on function financeiro.patrimonio_transferencias_tela(integer, date, date, integer, integer) to authenticated;
grant execute on function financeiro.patrimonio_bens_tela(integer, jsonb, integer) to authenticated;
grant execute on function financeiro.patrimonio_resumo_tela(integer) to authenticated;
