-- REVERSAO DO LOTE 20261106090000..20261118090000 (12 migrations do FIN-FIDELIDADE, aplicadas juntas).
-- Nao e migration (fora de supabase/migrations). Recuperacao do Supabase de TESTE se a aplicacao falhar no meio ou se o
-- lote precisar ser desfeito; aplicar so com autorizacao, numa unica transacao (psql -1 -f ou equivalente).
-- O lote so cria funcoes e privilegios (nenhuma tabela, politica ou dado); duas funcoes existentes sao substituidas.
-- Idempotente e valido tambem para aplicacao parcial:
-- 1. remove as 87 funcoes novas (drop function if exists, ordem inversa; os privilegios saem com elas);
-- 2. devolve as 2 substituidas a definicao anterior, com os mesmos privilegios (o mesmo texto de
--    supabase/reversao/20261107090000_*.sql e 20261108090000_*.sql, incluidos abaixo);
-- 3. tira as 12 versoes de supabase_migrations.schema_migrations (o historico volta a mostra-las pendentes).
-- Gerado das migrations; tests/test_supabase_reversao_lote.py aplica o lote e esta reversao num cluster descartavel
-- e confere que as funcoes do schema financeiro voltam exatamente ao estado anterior.

-- 1. Funcoes novas do lote
drop function if exists financeiro.arquivo_comprovante_tela(integer, integer);  -- 20261118090000
drop function if exists financeiro.lastro_saidas_tela(integer, jsonb, boolean);  -- 20261117090000
drop function if exists financeiro.saidas_lastro(integer, jsonb);  -- 20261117090000
drop function if exists financeiro.natureza_sugerida_lastro(text, text);  -- 20261117090000
drop function if exists financeiro.texto_sem_acento(text);  -- 20261117090000
drop function if exists financeiro.consorcios_tela(integer, integer);  -- 20261116090000
drop function if exists financeiro.consorcio_flask(public.contrato_consorcio);  -- 20261116090000
drop function if exists financeiro.perfil_do_consorcio(public.contrato_consorcio);  -- 20261116090000
drop function if exists financeiro.transporte_app_tela(integer, integer);  -- 20261115090000
drop function if exists financeiro.mobilidade_assinaturas_tela(integer, boolean);  -- 20261115090000
drop function if exists financeiro.mobilidade_ativa_tela(integer);  -- 20261115090000
drop function if exists financeiro.veiculo_financiamento_tela(integer, integer);  -- 20261115090000
drop function if exists financeiro.veiculo_manutencoes_km_tela(integer, integer, integer);  -- 20261115090000
drop function if exists financeiro.veiculo_regras_km_tela(integer, integer);  -- 20261115090000
drop function if exists financeiro.veiculo_uso_tela(integer, integer, integer);  -- 20261115090000
drop function if exists financeiro.projecoes_mobilidade_tela(integer, text, integer, integer);  -- 20261115090000
drop function if exists financeiro.veiculos_tela(integer, integer);  -- 20261115090000
drop function if exists financeiro.mobilidade_categorias_tela(integer);  -- 20261115090000
drop function if exists financeiro.caminho_app_md(integer, integer);  -- 20261115090000
drop function if exists financeiro.item_despesa_flask(public.item_despesa);  -- 20261115090000
drop function if exists financeiro.regra_km_flask(public.veiculo_regra_manutencao_km);  -- 20261115090000
drop function if exists financeiro.uso_do_veiculo(public.veiculo, integer);  -- 20261115090000
drop function if exists financeiro.veiculo_flask(public.veiculo);  -- 20261115090000
drop function if exists financeiro.veiculo_do_perfil(integer, integer);  -- 20261115090000
drop function if exists financeiro.hoje_brasilia();  -- 20261115090000
drop function if exists financeiro.despesa_prevista_flask(public.despesa_prevista);  -- 20261115090000
drop function if exists financeiro.categoria_flask(public.categoria);  -- 20261115090000
drop function if exists financeiro.numero_seguro(jsonb);  -- 20261115090000
drop function if exists financeiro.json_seguro(text);  -- 20261115090000
drop function if exists financeiro.dashboard_resumo_tela(integer, text);  -- 20261114090000
drop function if exists financeiro.status_consumo_flask(numeric);  -- 20261114090000
drop function if exists financeiro.percentual_flask(numeric, numeric);  -- 20261114090000
drop function if exists financeiro.ir_comprovantes_tela(integer, jsonb, integer);  -- 20261113090000
drop function if exists financeiro.ir_categorias_despesa_tela(integer, boolean);  -- 20261113090000
drop function if exists financeiro.ir_categorias_tela(integer);  -- 20261113090000
drop function if exists financeiro.ir_contexto_tela(integer);  -- 20261113090000
drop function if exists financeiro.ir_documentos_empresa_tela(integer, text, jsonb, integer);  -- 20261113090000
drop function if exists financeiro.resumo_documentos_empresa(integer, jsonb);  -- 20261113090000
drop function if exists financeiro.filtro_documento_empresa(public.ir_comprovante, jsonb);  -- 20261113090000
drop function if exists financeiro.comprovante_empresa(public.ir_comprovante, jsonb);  -- 20261113090000
drop function if exists financeiro.metadata_empresarial_flask(public.ir_comprovante);  -- 20261113090000
drop function if exists financeiro.taxonomia_documental();  -- 20261113090000
drop function if exists financeiro.comprovante_flask(public.ir_comprovante, boolean);  -- 20261113090000
drop function if exists financeiro.categorias_ir_do_tipo(text);  -- 20261113090000
drop function if exists financeiro.categoria_ir_flask(public.ir_categoria);  -- 20261113090000
drop function if exists financeiro.tipo_perfil_ir(integer);  -- 20261113090000
drop function if exists financeiro.patrimonio_resumo_tela(integer);  -- 20261112090000
drop function if exists financeiro.patrimonio_bens_tela(integer, jsonb, integer);  -- 20261112090000
drop function if exists financeiro.patrimonio_transferencias_tela(integer, date, date, integer, integer);  -- 20261112090000
drop function if exists financeiro.patrimonio_conta_tela(integer, integer);  -- 20261112090000
drop function if exists financeiro.patrimonio_contas_tela(integer, boolean);  -- 20261112090000
drop function if exists financeiro.perfil_empresa(integer);  -- 20261112090000
drop function if exists financeiro.bem_flask(public.bem_patrimonial);  -- 20261112090000
drop function if exists financeiro.documento_do_bem(public.bem_patrimonial);  -- 20261112090000
drop function if exists financeiro.imagens_patrimonio();  -- 20261112090000
drop function if exists financeiro.iso_python(timestamp);  -- 20261112090000
drop function if exists financeiro.financiamento_tela(integer, integer);  -- 20261110090000
drop function if exists financeiro.financiamentos_tela(integer, boolean);  -- 20261110090000
drop function if exists financeiro.vigencia_seguro_info(integer);  -- 20261110090000
drop function if exists financeiro.financiamento_flask(public.financiamento);  -- 20261110090000
drop function if exists financeiro.receitas_lancamentos_tela(integer, date, integer);  -- 20261109090000
drop function if exists financeiro.despesas_diretas_tela(integer);  -- 20261109090000
drop function if exists financeiro.compras_do_cartao_tela(integer, integer);  -- 20261109090000
drop function if exists financeiro.transferir_entre_contas(integer, jsonb, uuid);  -- 20261109090000
drop function if exists financeiro.excluir_ajuste_conta(integer, integer, integer);  -- 20261109090000
drop function if exists financeiro.editar_ajuste_conta(integer, integer, integer, jsonb);  -- 20261109090000
drop function if exists financeiro.travar_ajuste(integer, integer, integer);  -- 20261109090000
drop function if exists financeiro.ajustar_saldo_conta(integer, integer, jsonb, uuid);  -- 20261109090000
drop function if exists financeiro.editar_conta_bancaria(integer, integer, text, jsonb);  -- 20261109090000
drop function if exists financeiro.criar_conta_bancaria(integer, jsonb, uuid);  -- 20261109090000
drop function if exists financeiro.conferir_saldo_conta(integer, integer);  -- 20261109090000
drop function if exists financeiro.extrato_conta_bancaria(integer, integer, date, date, integer, boolean);  -- 20261109090000
drop function if exists financeiro.conta_bancaria_tela(integer, integer);  -- 20261109090000
drop function if exists financeiro.contas_bancarias_tela(integer, text);  -- 20261109090000
drop function if exists financeiro.operacao_repetida(integer, uuid, text);  -- 20261109090000
drop function if exists financeiro.ler_data_movimento(text);  -- 20261109090000
drop function if exists financeiro.ler_valor_movimento(text, text);  -- 20261109090000
drop function if exists financeiro.ler_dados_conta_bancaria(jsonb, boolean);  -- 20261109090000
drop function if exists financeiro.travar_conta_do_perfil(integer, integer);  -- 20261109090000
drop function if exists financeiro.movimento_flask(public.movimento_financeiro);  -- 20261109090000
drop function if exists financeiro.conta_bancaria_flask(public.conta_bancaria);  -- 20261109090000
drop function if exists financeiro.versao_conta_bancaria(public.conta_bancaria);  -- 20261109090000
drop function if exists financeiro.definir_situacao_recorrencia_cartao(integer, integer, text, boolean);  -- 20261106090000
drop function if exists financeiro.editar_recorrencia_cartao(integer, integer, text, jsonb);  -- 20261106090000
drop function if exists financeiro.travar_recorrencia_cartao(integer, integer, text);  -- 20261106090000
drop function if exists financeiro.criar_recorrencia_cartao(integer, jsonb, uuid);  -- 20261106090000
drop function if exists financeiro.ler_dados_recorrencia_cartao(integer, jsonb, boolean);  -- 20261106090000

-- 2. Funcoes substituidas (definicoes anteriores)

-- ==== 20261108090000_plano_recorrencia_anterior.sql ====
-- REVERSAO da migration 20261108090000 (R4): devolve financeiro.plano_recorrencia a definicao de 20261030090000.
-- Nao e migration (fora de supabase/migrations). Aplicar so com autorizacao, se a correcao precisar ser desfeita.

create or replace function financeiro.plano_recorrencia(p_perfil_id integer, p_mes date)
    returns setof financeiro.linha_plano
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_mes     date := date_trunc('month', p_mes::timestamp)::date;
    v_limite  date := (date_trunc('month', p_mes::timestamp) + interval '1 month')::date;
    v_ns      constant uuid := '7f3a1b2c-4d5e-6f7a-8b9c-0d1e2f3a4b5c';  -- namespace do Flask
    v_pessoal boolean;
    v_consolidada date;  -- FIN-CARTOES-D6-INTEGRIDADE-1
    v_item    record;
    v_cartao  record;
    v_reg     record;
    v_linha   financeiro.linha_plano;
    v_comp    date;
    v_passo   interval;
    v_dia     integer;
    v_motivo  text;
    v_ccs     integer[];
    v_qtd     integer;
    v_id      integer;
begin
    v_pessoal := exists (select 1 from public.perfil_financeiro p where p.id = p_perfil_id and p.nome = 'Pessoal');

    -- 1) Recorrencias: conta (boleto, debito, pix...) ou compra no cartao.
    for v_item in
        select i.*
          from public.item_despesa i
         where (i.perfil_financeiro_id = p_perfil_id or (i.perfil_financeiro_id is null and v_pessoal))
           and coalesce(i.recorrente, false)
         order by i.id
    loop
        v_linha := null;
        v_linha.natureza := case when v_item.meio_pagamento = 'cartao' then 'LANCAMENTO_CARTAO' else 'CONTA' end;
        v_linha.item_despesa_id := v_item.id;
        v_linha.nome := v_item.nome;
        v_linha.valor := v_item.valor;
        v_linha.perfil_destino := v_item.perfil_financeiro_id;
        v_linha.observacoes := coalesce(v_item.descricao, '');
        v_motivo := null;

        if not coalesce(v_item.ativo, true) then
            v_linha.situacao := 'INATIVA';
            v_linha.motivo := 'Recorrencia inativa: nao gera novos lancamentos';
            return next v_linha;
            continue;
        end if;

        if v_item.tipo = 'Agregador' then
            v_motivo := 'Cartao marcado como recorrencia';
        elsif v_item.data_vencimento is null then
            v_motivo := 'Sem data de vencimento';
        elsif coalesce(v_item.tipo_recorrencia, 'mensal') not in ('mensal', 'anual') then
            v_motivo := 'Tipo de recorrencia fora do escopo: ' || v_item.tipo_recorrencia;
        elsif v_item.valor is null or v_item.valor < 0 then
            v_motivo := 'Sem valor valido';
        elsif v_linha.natureza = 'LANCAMENTO_CARTAO' then
            if v_item.cartao_id is null then
                v_motivo := 'Sem cartao';
            elsif v_item.categoria_id is null then
                v_motivo := 'Sem categoria';
            else
                select c.* into v_cartao
                  from public.item_despesa c
                 where c.id = v_item.cartao_id
                   and c.tipo = 'Agregador'
                   and coalesce(c.ativo, true)
                   and (c.perfil_financeiro_id = p_perfil_id or (c.perfil_financeiro_id is null and v_pessoal));
                if not found then
                    v_motivo := 'Cartao inexistente, inativo ou de outro perfil';
                end if;
            end if;

            -- Categoria do cartao como CategoriaCartaoService.resolver_categoria_cartao_para_lancamento.
            if v_motivo is null then
                v_linha.cartao_id := v_item.cartao_id;
                v_linha.categoria_id := v_item.categoria_id;
                if v_item.categoria_cartao_id is not null then
                    if exists (select 1 from public.categoria_cartao cc
                                where cc.id = v_item.categoria_cartao_id
                                  and (cc.perfil_financeiro_id = p_perfil_id or (cc.perfil_financeiro_id is null and v_pessoal))) then
                        v_linha.categoria_cartao_id := v_item.categoria_cartao_id;
                    else
                        v_motivo := 'Categoria do cartao nao encontrada';
                    end if;
                else
                    select array_agg(v.categoria_cartao_id order by v.id) into v_ccs
                      from public.categoria_cartao_despesa v
                      join public.categoria_cartao cc on cc.id = v.categoria_cartao_id
                     where v.categoria_id = v_item.categoria_id
                       and v.ativo and cc.ativo
                       and (v.perfil_financeiro_id = p_perfil_id or (v.perfil_financeiro_id is null and v_pessoal))
                       and (cc.perfil_financeiro_id = p_perfil_id or (cc.perfil_financeiro_id is null and v_pessoal));
                    if cardinality(v_ccs) > 1 then
                        v_motivo := 'Categoria de despesa com mais de uma categoria do cartao ativa';
                    elsif cardinality(v_ccs) = 1 and exists (
                        select 1 from public.cartao_categoria_limite lim
                          join public.categoria_cartao cc on cc.id = lim.categoria_cartao_id
                         where lim.cartao_id = v_item.cartao_id
                           and lim.categoria_cartao_id = v_ccs[1]
                           and lim.ativo and cc.ativo
                           and (lim.perfil_financeiro_id = p_perfil_id or (lim.perfil_financeiro_id is null and v_pessoal))
                           and (cc.perfil_financeiro_id = p_perfil_id or (cc.perfil_financeiro_id is null and v_pessoal))) then
                        v_linha.categoria_cartao_id := v_ccs[1];
                    end if;
                end if;
            end if;
        else
            v_linha.conta_bancaria_id := v_item.conta_bancaria_id;
            v_linha.debito_automatico := coalesce(v_item.meio_pagamento = 'debito_automatico', false);
        end if;

        if v_motivo is not null then
            v_linha.situacao := 'REJEITADA';
            v_linha.motivo := v_motivo;
            v_linha.cartao_id := null;
            v_linha.categoria_id := null;
            v_linha.categoria_cartao_id := null;
            return next v_linha;
            continue;
        end if;

        v_dia := extract(day from v_item.data_vencimento)::integer;
        v_passo := case when coalesce(v_item.tipo_recorrencia, 'mensal') = 'anual' then interval '1 year' else interval '1 month' end;
        v_comp := date_trunc('month', v_item.data_vencimento::timestamp)::date;
        while v_comp <= v_limite loop
            v_linha.competencia := v_comp;
            v_linha.data_vencimento := financeiro.dia_contratual(v_comp, v_dia);
            v_linha.registro_id := null;
            v_linha.motivo := null;
            v_linha.compra_id := case when v_linha.natureza = 'LANCAMENTO_CARTAO' then
                extensions.uuid_generate_v5(v_ns, format('%s-%s', v_item.id, to_char(v_comp, 'YYYY-MM-DD')))::text end;

            select r.* into v_reg
              from financeiro.recorrencia_competencia r
             where r.item_despesa_id = v_item.id and r.natureza = v_linha.natureza and r.competencia = v_comp;
            if found then
                if v_reg.situacao = 'GERADA' and (
                       exists (select 1 from public.conta c where c.id = v_reg.conta_id)
                    or exists (select 1 from public.lancamento_agregado l where l.id = v_reg.lancamento_id)) then
                    v_linha.situacao := 'EXISTENTE';
                    v_linha.registro_id := coalesce(v_reg.conta_id, v_reg.lancamento_id);
                else
                    v_linha.situacao := 'DISPENSADA';
                    v_linha.motivo := case when v_reg.situacao = 'DISPENSADA'
                                           then coalesce(v_reg.motivo, 'Competencia dispensada')
                                           else 'Registro gerado foi removido; nao sera recriado' end;
                end if;
            else
                -- Reconhece o que o Flask (ou outro caminho) ja gravou, sem depender da data.
                if v_linha.natureza = 'CONTA' then
                    select c.id into v_id
                      from public.conta c
                     where c.item_despesa_id = v_item.id
                       and coalesce(c.is_fatura_cartao, false) = false
                       and (date_trunc('month', c.mes_referencia) = v_comp or date_trunc('month', c.data_vencimento) = v_comp)
                     order by c.id
                     limit 1;
                else
                    select l.id into v_id
                      from public.lancamento_agregado l
                     where l.compra_id = v_linha.compra_id
                        -- FIN-FATURA-INTEGRIDADE-1: pelo mes so os antigos, sem compra_id (uma compra de outra
                        -- competencia desviada para este mes por fatura paga nao e a deste mes).
                        or (l.item_despesa_id = v_item.id and l.mes_fatura = v_comp and l.is_recorrente
                            and l.compra_id is null)
                     order by l.id
                     limit 1;
                end if;
                v_linha.situacao := case when v_id is null then 'A_GERAR' else 'EXISTENTE' end;
                -- FIN-CARTOES-D6-INTEGRIDADE-1: a geracao automatica nao e confirmacao do usuario (D6) e nao muda a
                -- competencia (D5): compra recorrente cujo destino e fatura consolidada nao e gerada (nem em silencio,
                -- nem em outro mes). Fica REJEITADA, com o motivo na previa, ate o usuario lancar pela compra, com a
                -- confirmacao. Nada e gravado; a proxima previa reavalia (idempotente).
                if v_linha.natureza = 'LANCAMENTO_CARTAO' and v_linha.situacao = 'A_GERAR' then
                    v_consolidada := financeiro.fatura_consolidada_no_destino(v_linha.cartao_id, v_comp);
                    if v_consolidada is not null then
                        v_linha.situacao := 'REJEITADA';
                        v_linha.motivo := 'Fatura de ' || to_char(v_consolidada, 'MM/YYYY')
                            || ' consolidada: a compra recorrente nao entra sem confirmacao (lance-a pela compra no cartao)';
                    end if;
                end if;
                v_linha.registro_id := v_id;
            end if;
            return next v_linha;
            v_comp := (v_comp + v_passo)::date;
        end loop;
    end loop;

    -- 2) Faturas do mes e do seguinte para cada cartao ativo do perfil.
    for v_cartao in
        select c.id, c.nome, c.perfil_financeiro_id, cfg.dia_vencimento
          from public.item_despesa c
          left join public.config_agregador cfg on cfg.item_despesa_id = c.id
         where (c.perfil_financeiro_id = p_perfil_id or (c.perfil_financeiro_id is null and v_pessoal))
           and c.tipo = 'Agregador'
           and coalesce(c.ativo, true)
         order by c.id
    loop
        foreach v_comp in array array[v_mes, v_limite] loop
            v_linha := null;
            v_linha.natureza := 'FATURA';
            v_linha.item_despesa_id := v_cartao.id;
            v_linha.nome := v_cartao.nome;
            v_linha.competencia := v_comp;
            v_linha.perfil_destino := v_cartao.perfil_financeiro_id;
            v_linha.cartao_id := v_cartao.id;

            select c.id into v_id
              from public.conta c
             where c.item_despesa_id = v_cartao.id
               and c.is_fatura_cartao
               and date_trunc('month', c.cartao_competencia) = v_comp
             order by c.id
             limit 1;
            if v_id is not null then
                v_linha.situacao := 'EXISTENTE';
                v_linha.registro_id := v_id;
            elsif v_cartao.dia_vencimento is null or v_cartao.dia_vencimento not between 1 and 31 then
                v_linha.situacao := 'REJEITADA';
                v_linha.motivo := 'Cartao sem dia de vencimento configurado';
            else
                -- Planejado como CartaoService.calcular_planejado: limites ativos do cartao
                -- no perfil; sem limites, orcamento legado vigente por item agregado.
                select count(*), coalesce(sum(lim.limite_mensal), 0) into v_qtd, v_linha.valor
                  from public.cartao_categoria_limite lim
                 where lim.cartao_id = v_cartao.id and lim.perfil_financeiro_id = p_perfil_id and lim.ativo;
                if v_qtd = 0 then
                    select coalesce(sum(o.valor_teto), 0) into v_linha.valor
                      from public.item_agregado ia
                      cross join lateral (
                          select oa.valor_teto
                            from public.orcamento_agregado oa
                           where oa.item_agregado_id = ia.id
                             and oa.ativo
                             and oa.vigencia_inicio <= v_comp
                             and (oa.vigencia_fim is null or oa.vigencia_fim >= v_comp)
                           order by oa.id
                           limit 1
                      ) o
                     where ia.item_despesa_id = v_cartao.id;
                end if;
                v_linha.situacao := 'A_GERAR';
                v_linha.data_vencimento := financeiro.dia_contratual(v_comp, v_cartao.dia_vencimento);
            end if;
            return next v_linha;
        end loop;
    end loop;
end
$$;

revoke execute on function financeiro.plano_recorrencia(integer, date) from public, anon, authenticated;

-- ==== 20261107090000_analisar_importacao_cartao_anterior.sql ====
-- REVERSAO da migration 20261107090000: devolve financeiro.analisar_importacao_cartao a definicao de 20261105090000
-- (sem a regra da ocorrencia de recorrencia no cartao). Mesma assinatura e privilegios; nenhuma tabela ou dado.
-- Nao e migration (fora de supabase/migrations). Aplicar so com autorizacao, se a correcao precisar ser desfeita.
-- Gerado do trecho de 20261105090000_financeiro_importacao_cartao.sql; tests/test_supabase_recorrencia_cartao.py confere.

create or replace function financeiro.analisar_importacao_cartao(p_perfil_id integer, p_cartao_id integer, p_competencia date,
                                                      p_linhas jsonb)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_cartao    public.item_despesa;
    v_comp      date := date_trunc('month', p_competencia::timestamp)::date;
    v_l         jsonb;
    v_idx       bigint;
    v_saida     jsonb := '[]'::jsonb;
    v_msgs      jsonb;
    v_status    text;
    v_ignorar   boolean;
    v_data      date;
    v_valor     numeric;
    v_parc      integer;
    v_total     integer;
    v_norm      text;
    v_chave     text;
    v_chaves    text[] := '{}';
    v_usados    integer[] := '{}';
    v_dup       text;
    v_cat       integer;
    v_sug       jsonb;
    v_cc        integer;
    v_cc_res    integer;
    v_vinc      boolean;
    v_cc_origem text;
    v_class     text;
    v_conc      jsonb;
    v_conc_id   integer;
    v_manter    boolean;
    v_rec       integer;
    v_tipo      text;
    v_cat_origem text;
    v_bruto     numeric;
    v_credito   text;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    v_cartao := financeiro.cartao_do_perfil(p_perfil_id, p_cartao_id, true);
    if p_competencia is null then
        raise exception 'competencia obrigatoria' using errcode = '22023';
    end if;
    if p_linhas is null or jsonb_typeof(p_linhas) <> 'array' then
        raise exception 'Linhas da importacao invalidas' using errcode = '22023';
    end if;
    if jsonb_array_length(p_linhas) > 2000 then
        raise exception 'Arquivo com mais de 2000 linhas: divida a importacao' using errcode = '22023';
    end if;

    for v_l, v_idx in select e, o from jsonb_array_elements(p_linhas) with ordinality as x(e, o) loop
        if jsonb_typeof(v_l) <> 'object' then
            raise exception 'Linha % invalida', v_idx using errcode = '22023';
        end if;
        v_msgs := '[]'::jsonb;
        v_status := 'valido';
        v_ignorar := coalesce((v_l ->> 'ignorar')::boolean, false);
        v_dup := null;
        v_rec := null;
        v_conc := null;
        v_conc_id := null;
        v_manter := coalesce((v_l ->> 'manter_conciliada')::boolean, false);
        v_tipo := coalesce(nullif(v_l ->> 'tipo_movimento', ''), 'debito');
        begin
            v_data := nullif(v_l ->> 'data_compra', '')::date;
        exception when others then
            v_data := null;
        end;
        begin
            v_bruto := (v_l ->> 'valor')::numeric;
        exception when others then
            v_bruto := null;
        end;
        v_valor := round(abs(v_bruto), 2);
        -- Valor negativo nunca vira compra (o sinal nao e descartado): e credito, qualquer que seja o tipo informado.
        if v_bruto < 0 then
            v_tipo := 'credito';
        end if;
        -- Credito na fatura nao e despesa negativa: pagamento da fatura, estorno de compra e ajuste tem efeitos
        -- diferentes e nenhum entra como compra nem reduz a fatura por aqui (como o Flask, que nao importa credito).
        v_credito := case when v_tipo <> 'credito' then null
            when lower(coalesce(v_l ->> 'descricao_original', '')) ~ '(pagamento|pgto|pag[ .]?fatura|obrigado pelo pag)' then 'pagamento_fatura'
            when lower(coalesce(v_l ->> 'descricao_original', '')) ~ '(estorno|estornad|devolu|reembolso|cancelamento|chargeback)' then 'estorno'
            else 'credito_ajuste' end;
        begin
            v_parc := coalesce(nullif(v_l ->> 'parcela_atual', '')::integer, 1);
            v_total := coalesce(nullif(v_l ->> 'total_parcelas', '')::integer, 1);
        exception when others then
            v_parc := 0;
            v_total := 0;
        end;
        v_norm := btrim(coalesce(nullif(v_l ->> 'descricao_normalizada', ''), v_l ->> 'descricao_original', ''));

        -- Validacao (ImportacaoCartaoUnificadoService.validar_linhas)
        if v_tipo = 'credito' then
            v_status := 'ignorado';
            v_ignorar := true;
            v_msgs := v_msgs || case v_credito
                when 'pagamento_fatura' then '"Pagamento da fatura: nao e compra nem desconto; o pagamento e registrado em Despesas (pagar fatura)."'::jsonb
                when 'estorno' then '"Estorno de compra: nao importado; a compra original continua na fatura. Se ela deve sair, corrija pela propria compra."'::jsonb
                else '"Credito ou ajuste da administradora: nao importado como despesa."'::jsonb end;
        elsif v_valor is null or v_valor = 0 then
            v_status := 'ignorado';
            v_ignorar := true;
            v_msgs := v_msgs || '"Valor ausente ou zero."'::jsonb;
        else
            if v_data is null then
                v_status := 'revisar';
                v_msgs := v_msgs || '"Data de compra ausente."'::jsonb;
            end if;
            if v_norm = '' then
                v_status := 'revisar';
                v_msgs := v_msgs || '"Descricao ausente."'::jsonb;
            end if;
            if v_parc < 1 or v_total < 1 or v_parc > v_total or v_total > 60 then
                v_status := 'revisar';
                v_msgs := v_msgs || to_jsonb(format('Parcela fora do intervalo: %s/%s', v_parc, v_total));
            end if;
            if v_valor >= 100000000 then
                v_status := 'revisar';
                v_msgs := v_msgs || '"Valor acima do permitido."'::jsonb;
            end if;
        end if;

        -- Categoria de Despesa: a do usuario prevalece; senao, sugestao (palavra-chave, historico, fallback do cartao)
        v_sug := null;
        v_cat := null;
        v_cat_origem := null;
        if v_tipo <> 'credito' then
            if nullif(v_l ->> 'categoria_id', '') is not null then
                begin
                    v_cat := (v_l ->> 'categoria_id')::integer;
                exception when others then
                    v_cat := null;
                end;
                if v_cat is null or not exists (select 1 from public.categoria c where c.id = v_cat and coalesce(c.ativo, true)) then
                    v_cat := null;
                    v_msgs := v_msgs || '"Categoria da despesa inexistente ou inativa."'::jsonb;
                else
                    v_cat_origem := coalesce(nullif(v_l ->> 'categoria_origem', ''), 'manual');
                end if;
            else
                v_sug := financeiro.sugestao_categoria_importacao(p_perfil_id, v_l ->> 'descricao_classificacao', v_norm,
                                                                  v_cartao.categoria_id);
                v_cat := (v_sug ->> 'categoria_id')::integer;
                v_cat_origem := v_sug ->> 'origem';
                if v_sug ->> 'aviso' is not null then
                    v_msgs := v_msgs || to_jsonb(v_sug ->> 'aviso');
                end if;
            end if;
            if v_cat is null and v_status = 'valido' then
                v_status := 'revisar';
                v_msgs := v_msgs || '"Informe a categoria da despesa."'::jsonb;
            end if;
        end if;

        -- Duplicidade (chave de negocio do Flask) no lote e no banco; depois, conciliacao com compra ja lancada.
        v_chave := null;
        if v_status <> 'ignorado' and v_data is not null and v_norm <> '' and v_valor is not null then
            v_chave := concat_ws('|', p_cartao_id, v_comp, v_data, v_valor, lower(v_norm), v_parc, v_total);
            if v_chave = any(v_chaves) then
                v_dup := 'lote';
            elsif exists (select 1 from public.lancamento_agregado l
                           where l.cartao_id = p_cartao_id and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id)
                             and coalesce(l.mes_fatura_original, l.mes_fatura) = v_comp
                             and l.data_compra = v_data and l.valor = v_valor
                             and l.numero_parcela = v_parc and l.total_parcelas = v_total
                             and lower(coalesce(l.descricao_original_normalizada, l.descricao)) = lower(v_norm)) then
                v_dup := 'banco';
            end if;
            if v_dup is not null then
                v_status := 'duplicado';
                v_ignorar := true;
                v_msgs := v_msgs || '"Possivel duplicidade detectada."'::jsonb;
            else
                v_chaves := v_chaves || v_chave;
                -- Compra ja lancada (manual, por recorrencia ou importacao com outra descricao): mesmo cartao,
                -- competencia, valor e parcela, data a ate 5 dias (ou gerada por recorrencia). Cada lancamento
                -- concilia uma linha so.
                select l.id, jsonb_build_object('lancamento_id', l.id,
                                                'descricao', coalesce(nullif(l.descricao_exibida, ''), l.descricao),
                                                'data_compra', l.data_compra, 'valor', l.valor, 'categoria_id', l.categoria_id,
                                                'recorrente', coalesce(l.is_recorrente, false), 'mantida', v_manter)
                  into v_conc_id, v_conc
                  from public.lancamento_agregado l
                 where l.cartao_id = p_cartao_id and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id)
                   and coalesce(l.mes_fatura_original, l.mes_fatura) = v_comp and l.valor = v_valor
                   and coalesce(l.numero_parcela, 1) = v_parc and coalesce(l.total_parcelas, 1) = v_total
                   and (abs(l.data_compra - v_data) <= 5 or coalesce(l.is_recorrente, false))
                   and not l.id = any(v_usados)
                 order by abs(l.data_compra - v_data), l.id
                 limit 1;
                if v_conc_id is not null then
                    v_usados := v_usados || v_conc_id;
                    if not v_manter then
                        v_status := 'conciliado';
                        v_ignorar := true;
                    end if;
                    v_msgs := v_msgs || to_jsonb(format('Ja lancada no cartao: %s (%s, R$ %s)%s.', v_conc ->> 'descricao',
                        to_char((v_conc ->> 'data_compra')::date, 'DD/MM/YYYY'), to_char((v_conc ->> 'valor')::numeric, 'FM999999990.00'),
                        case when v_manter then '; mantida pelo usuario como compra diferente' else '; retirada da efetivacao' end));
                end if;
            end if;
        end if;

        -- Compra recorrente do cartao (reconhecer_despesa_fixa do Flask: nome igual, recorrente, no cartao).
        if v_status not in ('ignorado', 'duplicado', 'conciliado') and v_norm <> '' then
            select i.id into v_rec from public.item_despesa i
             where coalesce(i.recorrente, false) and coalesce(i.ativo, true) and i.tipo <> 'Agregador'
               and i.meio_pagamento = 'cartao' and i.cartao_id = p_cartao_id
               and financeiro.pertence_ao_perfil(i.perfil_financeiro_id, p_perfil_id)
               and lower(i.nome) = lower(v_norm)
             order by i.id limit 1;
            if v_rec is not null then
                v_msgs := v_msgs || '"Reconhecida como compra recorrente do cartao: o gerador nao a lanca de novo nesta competencia."'::jsonb;
            end if;
        end if;

        -- Categoria do Cartao (resolver_categoria_cartao_para_lancamento)
        v_cc := null;
        v_cc_res := null;
        v_vinc := false;
        v_cc_origem := null;
        if v_cat is not null and v_tipo <> 'credito' then
            v_cc := financeiro.resolver_categoria_cartao(p_perfil_id, p_cartao_id, v_cat);
            if v_cc is not null then
                v_vinc := true;
                v_cc_origem := 'mapa_categoria_despesa';
            else
                select v.categoria_cartao_id into v_cc_res
                  from public.categoria_cartao_despesa v join public.categoria_cartao cc on cc.id = v.categoria_cartao_id
                 where v.categoria_id = v_cat and v.ativo and cc.ativo
                   and financeiro.pertence_ao_perfil(v.perfil_financeiro_id, p_perfil_id)
                 order by v.id limit 1;
                if v_cc_res is not null then
                    v_cc_origem := 'nao_vinculada_ao_cartao';
                    v_msgs := v_msgs || '"Esta Categoria do Cartao ainda nao esta vinculada ao cartao selecionado."'::jsonb;
                else
                    v_cc_origem := 'nao_configurada';
                    v_msgs := v_msgs || '"Categoria de despesa sem Categoria do Cartao configurada."'::jsonb;
                end if;
            end if;
        end if;

        v_class := case
            when v_status = 'duplicado' then 'duplicada'
            when v_status = 'conciliado' then 'conciliada'
            when v_ignorar or v_status = 'ignorado' then 'ignorada'
            when v_cat_origem = 'ambigua' then 'ambigua'
            when v_cat is null then 'categoria_despesa_pendente'
            when v_cc_origem = 'nao_vinculada_ao_cartao' then 'categoria_cartao_nao_vinculada'
            when v_cc is null then 'categoria_cartao_pendente'
            else 'classificada' end;
        if v_class = 'classificada' then
            v_msgs := v_msgs || '"Linha pronta para importacao."'::jsonb;
        end if;

        v_saida := v_saida || jsonb_build_object(
            'linha_id', coalesce(v_l ->> 'linha_id', 'linha-' || v_idx), 'tipo_credito', v_credito, 'linha_origem', coalesce((v_l ->> 'linha_origem')::integer, v_idx::integer),
            'status', v_status, 'ignorar', v_ignorar, 'tipo_movimento', v_tipo,
            'data_compra', v_data, 'valor', v_valor,
            'descricao_original', v_l ->> 'descricao_original', 'descricao_normalizada', v_norm,
            'descricao_exibida', coalesce(nullif(btrim(v_l ->> 'descricao_exibida'), ''), v_norm),
            'parcela_atual', v_parc, 'numero_parcela', v_parc, 'total_parcelas', v_total, 'parcela', v_parc || '/' || v_total,
            'categoria_id', v_cat, 'categoria_despesa_id', v_cat,
            'categoria_nome', (select c.nome from public.categoria c where c.id = v_cat),
            'categoria_origem', v_cat_origem, 'categoria_sugerida_origem', coalesce(v_sug ->> 'origem', v_cat_origem),
            'confianca_categoria', coalesce(v_sug ->> 'confianca', case when v_cat is not null then 'manual' else 'baixa' end),
            'palavras_chave_encontradas', coalesce(v_sug -> 'palavras_chave_encontradas', '[]'::jsonb),
            'categorias_candidatas', coalesce(v_sug -> 'categorias_candidatas', '[]'::jsonb),
            'categoria_cartao_id', v_cc, 'categoria_cartao_resolvida_id', v_cc_res,
            'categoria_cartao_nome', (select cc.nome from public.categoria_cartao cc where cc.id = coalesce(v_cc, v_cc_res)),
            'categoria_cartao_origem', v_cc_origem, 'categoria_cartao_vinculada_ao_cartao', v_vinc,
            'status_classificacao', v_class, 'duplicidade', v_dup, 'duplicada', v_status = 'duplicado',
            'ignorada', v_ignorar,
            'conciliacao', v_conc,
            'recorrencia_id', v_rec,
            'gerar_parcelas_futuras', coalesce((v_l ->> 'gerar_parcelas_futuras')::boolean, false),
            'origem_importacao', coalesce(nullif(v_l ->> 'origem_importacao', ''), 'csv'),
            'hash_deduplicacao', v_chave,
            'mensagens', v_msgs, 'avisos', v_msgs);
    end loop;

    return jsonb_build_object(
        'cartao_id', p_cartao_id, 'competencia', to_char(v_comp, 'YYYY-MM'),
        'situacao_fatura', financeiro.situacao_fatura(financeiro.fatura_do_mes(p_cartao_id, v_comp)),
        'linhas', v_saida,
        'validacoes', (select jsonb_build_object(
            'total_linhas', count(*),
            'validas', count(*) filter (where l ->> 'status' = 'valido'),
            'revisar', count(*) filter (where l ->> 'status' = 'revisar'),
            'duplicadas', count(*) filter (where l ->> 'status' = 'duplicado'),
            'conciliadas', count(*) filter (where jsonb_typeof(l -> 'conciliacao') = 'object'),
            'sem_categoria_cartao', count(*) filter (where l ->> 'tipo_movimento' = 'debito'
                                                       and l ->> 'status' not in ('duplicado', 'ignorado', 'conciliado')
                                                       and l ->> 'categoria_cartao_id' is null),
            'total_importavel', coalesce(sum((l ->> 'valor')::numeric) filter (where l ->> 'tipo_movimento' = 'debito'
                                                       and not (l ->> 'ignorar')::boolean), 0),
            'creditos', count(*) filter (where l ->> 'tipo_movimento' = 'credito'),
            'total_creditos', coalesce(sum((l ->> 'valor')::numeric) filter (where l ->> 'tipo_movimento' = 'credito'), 0),
            'ignorados', count(*) filter (where l ->> 'status' = 'ignorado'))
            from jsonb_array_elements(v_saida) l));
end
$$;

revoke execute on function financeiro.analisar_importacao_cartao(integer, integer, date, jsonb) from public, anon;
grant execute on function financeiro.analisar_importacao_cartao(integer, integer, date, jsonb) to authenticated;

-- 3. Historico de migrations
do $reversao$
begin
    if to_regclass('supabase_migrations.schema_migrations') is not null then
        delete from supabase_migrations.schema_migrations where version in ('20261106090000', '20261107090000', '20261108090000', '20261109090000', '20261110090000', '20261112090000', '20261113090000', '20261114090000', '20261115090000', '20261116090000', '20261117090000', '20261118090000');
    end if;
end
$reversao$;
