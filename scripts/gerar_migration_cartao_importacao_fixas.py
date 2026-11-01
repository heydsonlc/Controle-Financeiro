"""Gera a migration 20261210090000 (FIN-CARTAO-IMPORTACAO-FIXAS-01) e a reversao a partir do texto VIGENTE de cada funcao,
com substituicoes conferidas (cada trecho deve ocorrer exatamente uma vez).

As funcoes substituidas sao longas: a migration nao e editada a mao. Para muda-la, edite este gerador e rode-o; as
fontes sao as migrations anteriores (ja aplicadas ou versionadas, imutaveis). So texto SQL: nenhum dado, conexao ou
credencial.

    python scripts/gerar_migration_cartao_importacao_fixas.py              # grava a migration e a reversao
    python scripts/gerar_migration_cartao_importacao_fixas.py --verificar  # so compara com os arquivos versionados

O teste tests/test_gerador_migration_cartao_importacao_fixas.py confere que os arquivos versionados sao a saida exata.
"""
import argparse
import re
import sys
from pathlib import Path

_args = argparse.ArgumentParser(description=__doc__.splitlines()[0])
_args.add_argument('raiz', nargs='?', default=str(Path(__file__).resolve().parents[1]), help='raiz do projeto')
_args.add_argument('--verificar', action='store_true', help='nao grava: falha se a saida difere dos arquivos versionados')
ARGS = _args.parse_args()
RAIZ = Path(ARGS.raiz)
MIG = RAIZ / 'supabase' / 'migrations'
MARCA = 'FIN-CARTAO-IMPORTACAO-FIXAS-01'


def bloco(arquivo, nome):
    texto = (MIG / arquivo).read_text(encoding='utf-8')
    m = list(re.finditer(r'create (?:or replace )?function financeiro\.' + nome + r'\(', texto))
    assert m, nome
    ini = m[-1].start()
    fim = texto.index('\n$$;', ini) + len('\n$$;')
    return texto[ini:fim]


def trocar(texto, antigo, novo, nome):
    n = texto.count(antigo)
    assert n == 1, f'{nome}: trecho encontrado {n} vezes: {antigo[:80]!r}'
    return texto.replace(antigo, novo)


def como_replace(b):
    return re.sub(r'^create function', 'create or replace function', b)


FONTES = {
    'analisar_importacao_cartao': '20261209090000_financeiro_cartao_previsto_executado.sql',
    'importar_fatura_cartao': '20261208090000_financeiro_cartao_despesas_fixas.sql',
}
ORIG = {n: bloco(a, n) for n, a in FONTES.items()}
NOVO = {}

PENDENTE = ("(select 1 from public.lancamento_agregado p\n"
            "                     where p.item_despesa_id = i.id and p.cartao_id = p_cartao_id and coalesce(p.is_recorrente, false)\n"
            "                       and coalesce(p.mes_fatura_original, p.mes_fatura) = v_comp and not coalesce(p.is_importado, false))")

# ---------------------------------------------------------------------------------------------------------------------
# analisar_importacao_cartao: classificacao proposta, correcao do usuario, conciliacao sugerida, nada descartado em silencio
# ---------------------------------------------------------------------------------------------------------------------
t = ORIG['analisar_importacao_cartao']
t = trocar(t, "    v_fat_occ   integer;\nbegin\n",
           "    v_fat_occ   integer;\n"
           f"    v_escolha   integer;            -- {MARCA}: recorrencia escolhida na previa (0 = compra comum)\n"
           "    v_usadas    integer[] := '{}';  -- previsoes ja atribuidas a uma linha deste arquivo\n"
           "    v_novas     integer[] := '{}';  -- recorrencias que ganham ocorrencia nova neste arquivo\n"
           "    v_existente integer;            -- compra ja lancada que e esta linha (duplicada ou conciliada pelo valor)\n"
           "    v_sug_conc  jsonb;\n"
           "    v_fixa      jsonb;\n"
           "    v_classe    text;\n"
           "    v_apelido   text;\n"
           "    v_prev_sug  public.lancamento_agregado;\n"
           "begin\n", 'ana')
t = trocar(t, "        v_conc_id := null;\n",
           "        v_conc_id := null;\n        v_existente := null;\n        v_sug_conc := null;\n        v_fixa := null;\n"
           "        v_apelido := null;\n        v_escolha := null;\n", 'ana')
t = trocar(t, "             where coalesce(i.recorrente, false) and coalesce(i.ativo, true) and i.tipo <> 'Agregador'\n",
           "             where coalesce(i.recorrente, false) and i.tipo <> 'Agregador'\n"
           f"               -- {MARCA}: inativada, mas com previsao pendente nesta competencia, ainda reconhece a cobranca\n"
           f"               and (coalesce(i.ativo, true) or exists {PENDENTE})\n", 'ana')
t = trocar(t, "        v_rec_nome := v_cands -> 0 ->> 'nome';\n",
           "        v_rec_nome := v_cands -> 0 ->> 'nome';\n"
           f"        -- {MARCA}: correcao do usuario na previa (recorrencia_escolhida_id): uma recorrencia deste cartao, ou 0 = compra\n"
           "        -- comum (nenhuma recorrencia). Prevalece sobre o reconhecimento pela descricao.\n"
           "        if v_l ? 'recorrencia_escolhida_id' and v_tipo <> 'credito' then\n"
           "            begin\n"
           "                v_escolha := coalesce(nullif(v_l ->> 'recorrencia_escolhida_id', '')::integer, 0);\n"
           "            exception when others then\n"
           "                v_escolha := -1;\n"
           "            end;\n"
           "            if v_escolha = 0 then\n"
           "                v_cands := '[]'::jsonb;\n"
           "            else\n"
           "                select coalesce(jsonb_agg(jsonb_build_object('id', i.id, 'nome', i.nome, 'categoria_id', i.categoria_id,\n"
           "                                                             'valor', i.valor, 'exato', true)), '[]'::jsonb)\n"
           "                  into v_cands\n"
           "                  from public.item_despesa i\n"
           "                 where i.id = v_escolha and coalesce(i.recorrente, false) and i.tipo <> 'Agregador'\n"
           "                   and i.meio_pagamento = 'cartao' and i.cartao_id = p_cartao_id\n"
           "                   and financeiro.pertence_ao_perfil(i.perfil_financeiro_id, p_perfil_id)\n"
           f"                   and (coalesce(i.ativo, true) or exists {PENDENTE.replace(chr(10) + '                     ', chr(10) + '                         ')});\n"
           "                if jsonb_array_length(v_cands) = 0 then\n"
           "                    v_status := 'revisar';\n"
           "                    v_msgs := v_msgs || '\"Recorrencia escolhida nao e deste cartao (ou esta inativa): escolha outra ou trate como compra comum.\"'::jsonb;\n"
           "                end if;\n"
           "            end if;\n"
           "            v_rec := case when jsonb_array_length(v_cands) = 1 then (v_cands -> 0 ->> 'id')::integer end;\n"
           "            v_rec_cat := (v_cands -> 0 ->> 'categoria_id')::integer;\n"
           "            v_rec_nome := v_cands -> 0 ->> 'nome';\n"
           "        end if;\n", 'ana')
t = trocar(t, "            if v_chave = any(v_chaves) then\n                v_dup := 'lote';\n",
           f"            -- {MARCA}: repetida no proprio arquivo, mas mantida pelo usuario (duas compras legitimas iguais)\n"
           "            if v_chave = any(v_chaves) and not coalesce((v_l ->> 'manter_duplicada')::boolean, false) then\n"
           "                v_dup := 'lote';\n", 'ana')
t = trocar(t, "            elsif exists (select 1 from public.lancamento_agregado l\n"
              "                           where l.cartao_id = p_cartao_id and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id)\n"
              "                             and coalesce(l.mes_fatura_original, l.mes_fatura) = v_comp\n"
              "                             and l.data_compra = v_data and l.valor = v_valor\n"
              "                             and l.numero_parcela = v_parc and l.total_parcelas = v_total\n"
              "                             and lower(coalesce(l.descricao_original_normalizada, l.descricao)) = lower(v_norm)) then\n"
              "                v_dup := 'banco';\n"
              "            end if;\n",
           "            else\n"
           f"                -- {MARCA}: a compra ja gravada (para sugerir a conciliacao com a previsao, abaixo)\n"
           "                select l.id into v_existente from public.lancamento_agregado l\n"
           "                 where l.cartao_id = p_cartao_id and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id)\n"
           "                   and coalesce(l.mes_fatura_original, l.mes_fatura) = v_comp\n"
           "                   and l.data_compra = v_data and l.valor = v_valor\n"
           "                   and l.numero_parcela = v_parc and l.total_parcelas = v_total\n"
           "                   and lower(coalesce(l.descricao_original_normalizada, l.descricao)) = lower(v_norm)\n"
           "                 order by l.id limit 1;\n"
           "                if v_existente is not null then\n"
           "                    v_dup := 'banco';\n"
           "                end if;\n"
           "            end if;\n", 'ana')

ini = t.index("        -- FIN-CARTAO-DESPESAS-FIXAS-01: ocorrencia da recorrencia reconhecida pela descricao (acima).")
fim = t.index("        -- Categoria do Cartao (resolver_categoria_cartao_para_lancamento)")
antigo = t[ini:fim]
assert "and o.origem = 'NAO_COBRADA')" in antigo  # parte da 1209 preservada abaixo
REALIZAVEL = ("coalesce(v_occ.is_recorrente, false) and coalesce(v_occ.total_parcelas, 1) = 1\n"
              "                   and not coalesce(v_occ.is_importado, false)\n"
              "                   and not exists (select 1 from financeiro.ocorrencia_recorrencia_cartao o\n"
              "                                    where o.lancamento_id = v_occ.id and o.revertida_em is null)\n"
              "                   and (v_fat_occ is null or not (financeiro.fatura_esta_paga(v_fat_occ)\n"
              "                        or exists (select 1 from public.conta c where c.id = v_fat_occ and c.status_fatura = 'FECHADA')))")
novo = f"""        -- {MARCA}: ocorrencia da recorrencia reconhecida (descricao, apelido ou escolha do usuario).
        -- - previsao do mes sem cobranca: a linha a realiza (uma ocorrencia, previsto preservado);
        -- - cobranca ja lancada como compra comum (a mesma linha reimportada, ou a compra conciliada pelo valor): sugere
        --   conciliar com a previsao; a conciliacao so acontece na confirmacao, se pedida (conciliar_previsao);
        -- - nada e descartado em silencio: segunda cobranca do mes, previsao ja cobrada, em fatura paga ou consolidada
        --   pedem revisao (escolher outra recorrencia, tratar como compra comum ou retirar a linha).
        v_existente := coalesce(v_existente, case when v_status = 'conciliado' then v_conc_id end);
        if v_status in ('duplicado', 'conciliado') and v_existente is not null and v_rec is not null
           and jsonb_array_length(v_cands) = 1 then
            select l.* into v_occ from public.lancamento_agregado l where l.id = v_existente;
            if financeiro.natureza_da_compra(v_occ.total_parcelas, v_occ.is_recorrente, v_occ.item_despesa_id,
                                             v_occ.categoria_cartao_id) in ('CATEGORIA', 'OUTROS')
               and v_occ.item_despesa_id is null then
                select p.* into v_prev_sug from public.lancamento_agregado p
                 where p.item_despesa_id = v_rec and p.cartao_id = p_cartao_id and p.mes_fatura = v_occ.mes_fatura
                   and coalesce(p.is_recorrente, false) and coalesce(p.total_parcelas, 1) = 1
                   and not coalesce(p.is_importado, false)
                   and not exists (select 1 from financeiro.ocorrencia_recorrencia_cartao o
                                    where o.lancamento_id = p.id and o.revertida_em is null)
                   and not p.id = any(v_usadas)
                 order by p.id limit 1;
                if found then
                    v_fat_occ := financeiro.fatura_do_mes(p_cartao_id, v_prev_sug.mes_fatura);
                    if v_fat_occ is null or not (financeiro.fatura_esta_paga(v_fat_occ)
                       or exists (select 1 from public.conta c where c.id = v_fat_occ and c.status_fatura = 'FECHADA')) then
                        v_usadas := v_usadas || v_prev_sug.id;
                        v_sug_conc := jsonb_build_object('previsto_id', v_prev_sug.id, 'cobranca_id', v_occ.id,
                            'recorrencia_id', v_rec, 'recorrencia_nome', v_rec_nome, 'valor_previsto', v_prev_sug.valor,
                            'valor_cobrado', v_occ.valor, 'diferenca', v_occ.valor - v_prev_sug.valor,
                            'fatura', to_char(v_prev_sug.mes_fatura, 'MM/YYYY'));
                        v_msgs := v_msgs || to_jsonb(format('Ja lancada como compra comum e corresponde a previsao de "%s" (R$ %s): pode ser conciliada na confirmacao (cobrado R$ %s; diferenca R$ %s).',
                            v_rec_nome, to_char(v_prev_sug.valor, 'FM999999990.00'), to_char(v_occ.valor, 'FM999999990.00'),
                            to_char(v_occ.valor - v_prev_sug.valor, 'FM999999990.00')));
                    end if;
                end if;
            end if;
        end if;
        if v_status in ('ignorado', 'duplicado', 'conciliado') or v_norm = '' then
            v_rec := null;
        elsif jsonb_array_length(v_cands) > 1 then
            v_status := 'revisar';
            v_msgs := v_msgs || to_jsonb(format('Mais de uma recorrencia do cartao combina com a descricao (%s): a linha nao foi vinculada; escolha a recorrencia ou trate como compra comum.',
                (select string_agg(c ->> 'nome', ', ' order by (c ->> 'id')::integer) from jsonb_array_elements(v_cands) c)));
        elsif v_rec is not null then
            select l.* into v_occ
              from public.lancamento_agregado l
             where l.item_despesa_id = v_rec and l.cartao_id = p_cartao_id
               and coalesce(l.mes_fatura_original, l.mes_fatura) = v_comp
               -- FIN-CARTAO-PREVISTO-EXECUTADO-01: a previsao que a fatura paga deixou sem cobranca nao e a ocorrencia; a cobranca
               -- real que chega depois entra como compra da recorrencia (na proxima fatura aberta)
               and not exists (select 1 from financeiro.ocorrencia_recorrencia_cartao o
                                where o.lancamento_id = l.id and o.revertida_em is null and o.origem = 'NAO_COBRADA')
             order by l.id limit 1;
            if found then
                v_fat_occ := financeiro.fatura_do_mes(p_cartao_id, v_occ.mes_fatura);
                if v_occ.id = any(v_usadas) then
                    v_status := 'revisar';
                    v_msgs := v_msgs || to_jsonb(format('Segunda cobranca de "%s" nesta fatura: a previsao ja ficou com outra linha do arquivo. Se esta e outra cobranca, trate como compra comum; se e a mesma, retire a linha.', v_rec_nome));
                elsif {REALIZAVEL} then
                    v_realiza := v_occ.id;
                    v_prev := v_occ.valor;
                    v_usadas := v_usadas || v_occ.id;
                    v_msgs := v_msgs || to_jsonb(format('Cobranca real da recorrencia "%s": confirma a previsao de R$ %s desta fatura (executado R$ %s%s).',
                        v_rec_nome, to_char(v_prev, 'FM999999990.00'), to_char(v_valor, 'FM999999990.00'),
                        case when v_valor <> v_prev then '; diferenca R$ ' || to_char(v_valor - v_prev, 'FM999999990.00') else '' end));
                elsif coalesce(v_occ.is_importado, false) or not coalesce(v_occ.is_recorrente, false)
                      or coalesce(v_occ.total_parcelas, 1) <> 1
                      or exists (select 1 from financeiro.ocorrencia_recorrencia_cartao o
                                  where o.lancamento_id = v_occ.id and o.revertida_em is null) then
                    v_status := 'revisar';
                    v_msgs := v_msgs || to_jsonb(format('"%s" ja tem cobranca nesta fatura (R$ %s em %s). Se esta e outra cobranca, trate como compra comum; se e a mesma, retire a linha.',
                        v_rec_nome, to_char(v_occ.valor, 'FM999999990.00'), to_char(v_occ.data_compra, 'DD/MM/YYYY')));
                elsif financeiro.fatura_esta_paga(v_fat_occ) then
                    v_status := 'revisar';
                    v_msgs := v_msgs || to_jsonb(format('A previsao de "%s" esta em fatura paga (%s): se esta cobranca e outra, trate como compra comum (entra na proxima fatura aberta); se ja foi paga, retire a linha.',
                        v_rec_nome, to_char(v_occ.mes_fatura, 'MM/YYYY')));
                else
                    v_status := 'revisar';
                    v_msgs := v_msgs || to_jsonb(format('A previsao de "%s" esta em fatura consolidada (%s): ela nao recebe cobranca por aqui; retire a linha ou trate como compra comum de outra competencia.',
                        v_rec_nome, to_char(v_occ.mes_fatura, 'MM/YYYY')));
                end if;
            elsif v_rec = any(v_novas) then
                v_status := 'revisar';
                v_msgs := v_msgs || to_jsonb(format('Segunda cobranca de "%s" nesta fatura: a ocorrencia do mes ja ficou com outra linha do arquivo. Se esta e outra cobranca, trate como compra comum; se e a mesma, retire a linha.', v_rec_nome));
            else
                v_novas := v_novas || v_rec;
                v_msgs := v_msgs || to_jsonb(format('Reconhecida como compra recorrente do cartao ("%s"): o gerador nao a lanca de novo nesta competencia.', v_rec_nome));
            end if;
        end if;

"""
t = t.replace(antigo, novo)
t = trocar(t, "        if v_class = 'classificada' then\n            v_msgs := v_msgs || '\"Linha pronta para importacao.\"'::jsonb;\n        end if;\n",
           "        if v_class = 'classificada' then\n            v_msgs := v_msgs || '\"Linha pronta para importacao.\"'::jsonb;\n        end if;\n"
           f"        -- {MARCA}: detalhe da despesa fixa e classificacao proposta na previa\n"
           "        if v_rec is not null then\n"
           "            v_fixa := jsonb_build_object('recorrencia_id', v_rec, 'nome', v_rec_nome,\n"
           "                'valor_previsto', coalesce(v_prev, (v_cands -> 0 ->> 'valor')::numeric), 'valor_cobrado', v_valor,\n"
           "                'diferenca', v_valor - coalesce(v_prev, (v_cands -> 0 ->> 'valor')::numeric),\n"
           "                'competencia', to_char(v_comp, 'MM/YYYY'),\n"
           "                'fatura_destino', to_char(case when v_realiza is not null then v_occ.mes_fatura else v_comp end, 'MM/YYYY'),\n"
           "                'realiza_lancamento_id', v_realiza, 'escolhida', coalesce(v_escolha, 0) > 0);\n"
           "            -- escolhida pelo usuario sem que a descricao a reconhecesse: o texto pode virar apelido na confirmacao\n"
           "            if coalesce(v_escolha, 0) > 0 and length(btrim(v_texto)) between 3 and 80\n"
           "               and position(' ' || financeiro.texto_cobranca(v_rec_nome) || ' ' in v_texto) = 0\n"
           "               and not exists (select 1 from financeiro.recorrencia_apelido a where a.item_despesa_id = v_rec and a.ativo\n"
           "                                  and position(' ' || a.apelido || ' ' in v_texto) > 0) then\n"
           "                v_apelido := btrim(v_texto);\n"
           "            end if;\n"
           "        end if;\n"
           "        v_classe := case\n"
           "            when v_tipo = 'credito' or v_status = 'ignorado' then 'IGNORADA'\n"
           "            when v_status in ('duplicado', 'conciliado') then case when v_total > 1 then 'PARCELA_EXISTENTE' else 'JA_EXISTENTE' end\n"
           "            when v_status = 'revisar' then 'REVISAR'\n"
           "            when v_rec is not null then 'DESPESA_FIXA'\n"
           "            when v_total > 1 then 'PARCELADA'\n"
           "            else 'COMPRA' end;\n", 'ana')
t = trocar(t, "            'mensagens', v_msgs, 'avisos', v_msgs);\n",
           "            'mensagens', v_msgs, 'avisos', v_msgs)\n"
           f"            -- {MARCA} (objeto a parte: jsonb_build_object aceita ate 100 argumentos)\n"
           "            || jsonb_build_object(\n"
           "            'classificacao_importacao', v_classe,\n"
           "            'despesa_fixa', v_fixa,\n"
           "            'conciliacao_sugerida', v_sug_conc,\n"
           "            'conciliar_previsao', v_sug_conc is not null and coalesce((v_l ->> 'conciliar_previsao')::boolean, false),\n"
           "            'recorrencia_escolhida_id', v_escolha,\n"
           "            'apelido_sugerido', v_apelido,\n"
           "            'salvar_apelido', v_apelido is not null and coalesce((v_l ->> 'salvar_apelido')::boolean, false),\n"
           "            'manter_duplicada', coalesce((v_l ->> 'manter_duplicada')::boolean, false)));\n", 'ana')
t = trocar(t, "        v_saida := v_saida || jsonb_build_object(\n", "        v_saida := v_saida || (jsonb_build_object(\n", 'ana')
t = trocar(t, "        'linhas', v_saida,\n",
           f"        -- {MARCA}: recorrencias do cartao que a previa pode escolher (ativas, ou inativas com previsao pendente)\n"
           "        'recorrencias_cartao', coalesce((select jsonb_agg(jsonb_build_object('id', i.id, 'nome', i.nome, 'valor', i.valor,\n"
           "                                                                    'ativa', coalesce(i.ativo, true)) order by i.nome, i.id)\n"
           "            from public.item_despesa i\n"
           "           where coalesce(i.recorrente, false) and i.tipo <> 'Agregador' and i.meio_pagamento = 'cartao'\n"
           "             and i.cartao_id = p_cartao_id and financeiro.pertence_ao_perfil(i.perfil_financeiro_id, p_perfil_id)\n"
           f"             and (coalesce(i.ativo, true) or exists {PENDENTE.replace(chr(10) + '                     ', chr(10) + '                   ')})), '[]'::jsonb),\n"
           "        'linhas', v_saida,\n", 'ana')
t = trocar(t, "            'realizacoes', count(*) filter (where l ->> 'realiza_lancamento_id' is not null and not (l ->> 'ignorar')::boolean),\n",
           "            'realizacoes', count(*) filter (where l ->> 'realiza_lancamento_id' is not null and not (l ->> 'ignorar')::boolean),\n"
           "            'despesas_fixas', count(*) filter (where l ->> 'classificacao_importacao' = 'DESPESA_FIXA'),\n"
           "            'conciliacoes_sugeridas', count(*) filter (where jsonb_typeof(l -> 'conciliacao_sugerida') = 'object'),\n", 'ana')
NOVO['analisar_importacao_cartao'] = t

# ---------------------------------------------------------------------------------------------------------------------
# importar_fatura_cartao: conciliacoes e apelidos pedidos na previa, na mesma transacao
# ---------------------------------------------------------------------------------------------------------------------
t = ORIG['importar_fatura_cartao']
t = trocar(t, "    v_realizadas integer := 0;  -- FIN-CARTAO-DESPESAS-FIXAS-01\nbegin\n",
           "    v_realizadas integer := 0;  -- FIN-CARTAO-DESPESAS-FIXAS-01\n"
           f"    v_conciliar  jsonb := '[]'::jsonb;  -- {MARCA}\n"
           "    v_conciliadas integer := 0;\n"
           "    v_apelidos   integer := 0;\n"
           "    v_r          jsonb;\n"
           "begin\n", 'imp')
t = trocar(t, "    for v_l in select e from jsonb_array_elements(v_analise -> 'linhas') e loop\n"
              "        continue when (v_l ->> 'ignorar')::boolean;\n",
           "    for v_l in select e from jsonb_array_elements(v_analise -> 'linhas') e loop\n"
           f"        -- {MARCA}: cobranca ja lancada que o usuario pediu para conciliar com a previsao (a linha nao e gravada)\n"
           "        if coalesce((v_l ->> 'conciliar_previsao')::boolean, false) then\n"
           "            v_conciliar := v_conciliar || v_l;\n"
           "        end if;\n"
           "        continue when (v_l ->> 'ignorar')::boolean;\n", 'imp')
t = trocar(t, "    if jsonb_array_length(v_a_gravar) = 0 then\n",
           "    if jsonb_array_length(v_a_gravar) = 0 and jsonb_array_length(v_conciliar) = 0 then\n", 'imp')
t = trocar(t, "    for i in 1..cardinality(v_meses) loop\n",
           f"    -- {MARCA}: conciliacoes pedidas na previa (previsao + cobranca ja lancada), sob as mesmas travas\n"
           "    for v_l in select e from jsonb_array_elements(v_conciliar) e loop\n"
           "        v_r := financeiro.conciliar_previsao_interna(p_perfil_id, (v_l -> 'conciliacao_sugerida' ->> 'previsto_id')::integer,\n"
           "                                                     (v_l -> 'conciliacao_sugerida' ->> 'cobranca_id')::integer);\n"
           "        v_conciliadas := v_conciliadas + 1;\n"
           "        v_alvo := (v_r ->> 'fatura')::date;\n"
           "        if not v_alvo = any(v_meses) then\n"
           "            v_meses := v_meses || v_alvo;\n"
           "        end if;\n"
           "    end loop;\n"
           "    -- e os apelidos de cobranca que o usuario pediu para lembrar (escolheu a recorrencia que a descricao nao reconhecia)\n"
           "    for v_l in select e from jsonb_array_elements(v_a_gravar) e where coalesce((e ->> 'salvar_apelido')::boolean, false) loop\n"
           "        perform financeiro.registrar_apelido_recorrencia(p_perfil_id, (v_l ->> 'recorrencia_id')::integer, v_l ->> 'apelido_sugerido');\n"
           "        v_apelidos := v_apelidos + 1;\n"
           "    end loop;\n"
           "    for i in 1..cardinality(v_meses) loop\n", 'imp')
t = trocar(t, "        'realizadas', v_realizadas,\n",
           "        'realizadas', v_realizadas,\n        'conciliadas', v_conciliadas, 'apelidos', v_apelidos,\n", 'imp')
NOVO['importar_fatura_cartao'] = t

NOVOS = r"""
-- =====================================================================================================================
-- 1. Conciliacao e apelido dentro da importacao (internas; a importacao ja autorizou e travou o perfil)
-- =====================================================================================================================
-- Previsao da recorrencia + compra comum ja lancada (a cobranca real), mesmo cartao e mesma fatura aberta: a previsao fica
-- (identidade da recorrencia) com os dados da cobranca; a compra da cobranca sai, inteira na auditoria
-- (ocorrencia_recorrencia_cartao.lancamento_absorvido). Reversivel por reverter_ocorrencia_recorrencia.
create function financeiro.conciliar_previsao_interna(p_perfil_id integer, p_previsto_id integer, p_cobranca_id integer)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_prev public.lancamento_agregado;
    v_cob  public.lancamento_agregado;
begin
    select * into v_prev from public.lancamento_agregado where id = p_previsto_id for update;
    select * into v_cob from public.lancamento_agregado where id = p_cobranca_id for update;
    if v_prev.id is null or v_cob.id is null or p_previsto_id = p_cobranca_id
       or not financeiro.pertence_ao_perfil(v_prev.perfil_financeiro_id, p_perfil_id)
       or not financeiro.pertence_ao_perfil(v_cob.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Compra nao encontrada neste perfil' using errcode = '42501';
    end if;
    if v_cob.cartao_id <> v_prev.cartao_id or v_cob.mes_fatura <> v_prev.mes_fatura then
        raise exception 'A previsao e a cobranca devem estar no mesmo cartao e na mesma fatura' using errcode = '22023';
    end if;
    if financeiro.natureza_da_compra(v_cob.total_parcelas, v_cob.is_recorrente, v_cob.item_despesa_id, v_cob.categoria_cartao_id)
       not in ('CATEGORIA', 'OUTROS') or v_cob.item_despesa_id is not null then
        raise exception 'A cobranca deve ser uma compra comum (nem parcelada, nem de recorrencia)' using errcode = '22023';
    end if;
    if exists (select 1 from public.fatura_consolidada_inclusao i where i.lancamento_id = v_cob.id) then
        raise exception 'A cobranca foi incluida numa fatura consolidada: concilie pela propria fatura' using errcode = 'P0001';
    end if;
    perform financeiro.realizar_ocorrencia_recorrencia(p_perfil_id, v_prev.id,
        jsonb_build_object('valor', v_cob.valor, 'data_compra', v_cob.data_compra,
                           'descricao_original', coalesce(v_cob.descricao_original, v_cob.descricao),
                           'descricao_original_normalizada', coalesce(v_cob.descricao_original_normalizada, v_cob.descricao),
                           'is_importado', coalesce(v_cob.is_importado, false), 'origem_importacao', v_cob.origem_importacao),
        'CONCILIACAO', to_jsonb(v_cob));
    delete from public.lancamento_agregado where id = v_cob.id;  -- inteira em ocorrencia_recorrencia_cartao.lancamento_absorvido
    return jsonb_build_object('previsto_id', v_prev.id, 'cobranca_id', v_cob.id, 'fatura', v_prev.mes_fatura,
                              'valor_previsto', v_prev.valor, 'valor_executado', v_cob.valor);
end
$$;

-- Apelido de cobranca confirmado na importacao: as mesmas regras de criar_apelido_recorrencia (texto normalizado de 3 a 80
-- letras ou numeros; recusado se reconheceria outra recorrencia do cartao).
create function financeiro.registrar_apelido_recorrencia(p_perfil_id integer, p_item_id integer, p_apelido text)
    returns bigint
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_item  public.item_despesa;
    v_texto text := financeiro.texto_cobranca(p_apelido);
    v_outra text;
    v_id    bigint;
begin
    v_item := financeiro.recorrencia_cartao_do_perfil(p_perfil_id, p_item_id);
    if length(v_texto) < 3 or length(v_texto) > 80 then
        raise exception 'Apelido deve ter de 3 a 80 letras ou numeros' using errcode = '22023';
    end if;
    select i.nome into v_outra
      from financeiro.recorrencia_apelido a join public.item_despesa i on i.id = a.item_despesa_id
     where a.apelido = v_texto and a.ativo and a.item_despesa_id <> p_item_id and i.cartao_id = v_item.cartao_id
     limit 1;
    if v_outra is null then
        select i.nome into v_outra from public.item_despesa i
         where i.id <> p_item_id and i.cartao_id = v_item.cartao_id and coalesce(i.recorrente, false) and coalesce(i.ativo, true)
           and i.meio_pagamento = 'cartao' and financeiro.texto_cobranca(i.nome) = v_texto
         limit 1;
    end if;
    if v_outra is not null then
        raise exception 'Apelido "%" ja reconhece outra recorrencia deste cartao: %', v_texto, v_outra using errcode = '22023';
    end if;
    insert into financeiro.recorrencia_apelido (perfil_financeiro_id, item_despesa_id, apelido, user_id)
    values (p_perfil_id, p_item_id, v_texto, (select auth.uid()))
    on conflict (item_despesa_id, apelido) do update set ativo = true
    returning id into v_id;
    return v_id;
end
$$;
"""

PERMISSOES = """
-- Internas: sem EXECUTE para o navegador.
revoke execute on function financeiro.conciliar_previsao_interna(integer, integer, integer) from public, anon, authenticated;
revoke execute on function financeiro.registrar_apelido_recorrencia(integer, integer, text) from public, anon, authenticated;
"""

CABECALHO = f"""-- {MARCA} — reconhecimento, classificacao e conciliacao das despesas fixas durante a importacao da fatura.
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261210090000). Depende de 20261208090000 e 20261209090000.
-- Validada em cluster local descartavel (tests/test_supabase_cartao_importacao_fixas.py) e ensaiada numa copia fiel da
-- producao. Doc: docs/FIN_CARTAO_IMPORTACAO_FIXAS_01.md. Gerada por scripts/gerar_migration_cartao_importacao_fixas.py.
-- Reversao: supabase/reversao/20261210090000_cartao_importacao_fixas_anterior.sql.
--
-- Na previa (analisar_importacao_cartao, so leitura), cada linha traz a classificacao proposta:
-- JA_EXISTENTE / PARCELA_EXISTENTE (nao grava de novo), DESPESA_FIXA (recorrencia, previsto, cobrado, diferenca,
-- competencia e fatura de destino), PARCELADA, COMPRA (Categoria do Cartao ou Outros), REVISAR ou IGNORADA. A previa aceita
-- a correcao do usuario: recorrencia_escolhida_id (outra recorrencia do cartao, ou 0 = compra comum), salvar_apelido,
-- conciliar_previsao (compra ja lancada + previsao) e manter_duplicada (duas compras iguais legitimas no arquivo).
-- Nada e descartado em silencio: segunda cobranca do mes, previsao ja cobrada, em fatura paga ou consolidada pedem revisao.
-- Recorrencia inativada com previsao pendente na competencia ainda reconhece a cobranca.
-- Na confirmacao (importar_fatura_cartao), tudo numa transacao, com a analise refeita sob as travas: realiza as
-- previsoes, grava as compras, concilia as pedidas e registra os apelidos pedidos. Nenhum dado existente e alterado
-- pela migration.
--
-- Funcoes existentes substituidas pelo texto vigente com os trechos marcados "{MARCA}": analisar_importacao_cartao
-- (texto de 20261209090000) e importar_fatura_cartao (texto de 20261208090000).
"""

ORDEM = ['analisar_importacao_cartao', 'importar_fatura_cartao']
partes = [CABECALHO, NOVOS,
          "\n-- =====================================================================================================================\n"
          "-- 2. Previa e confirmacao da importacao: texto vigente + os trechos marcados\n"
          "-- =====================================================================================================================\n"]
for n in ORDEM:
    partes.append(f"\n-- {n}: texto de {FONTES[n][:14]} + os trechos marcados.\n{como_replace(NOVO[n])}\n")
partes.append(PERMISSOES)
destino = MIG / '20261210090000_financeiro_cartao_importacao_fixas.sql'

REV = [f"""-- Reversao de 20261210090000 ({MARCA}): volta a previa e a confirmacao da importacao ao texto anterior e remove as
-- funcoes internas novas. Os apelidos registrados e as conciliacoes feitas continuam (sao dados de 20261208090000 e se
-- desfazem pelas funcoes de la). So com autorizacao, retirando a versao de supabase_migrations.schema_migrations.
"""]
for n in ORDEM:
    REV.append(f"\n-- {n}: texto de {FONTES[n][:14]}.\n{como_replace(ORIG[n])}\n")
REV.append("""
drop function financeiro.registrar_apelido_recorrencia(integer, integer, text);
drop function financeiro.conciliar_previsao_interna(integer, integer, integer);
""")

SAIDAS = {destino: ''.join(partes),
          RAIZ / 'supabase' / 'reversao' / '20261210090000_cartao_importacao_fixas_anterior.sql': ''.join(REV)}
if ARGS.verificar:
    # Bytes exatos (UTF-8), sem CR: o checkout no Windows pode trocar LF por CRLF (core.autocrlf).
    diferentes = [str(p.relative_to(RAIZ)) for p, texto in SAIDAS.items()
                  if not p.exists() or p.read_bytes().replace(b'\r\n', b'\n') != texto.encode('utf-8')]
    print('diferente: ' + ', '.join(diferentes) if diferentes else 'igual')
    sys.exit(1 if diferentes else 0)
for caminho, texto in SAIDAS.items():
    caminho.write_text(texto, encoding='utf-8', newline='\n')
print('ok', destino.stat().st_size)
