"""Gera a migration 20261213090000 (FIN-CARTOES-MULTIPLOS-01) e a reversao a partir do texto VIGENTE de cada funcao, com
substituicoes conferidas (cada trecho deve ocorrer o numero de vezes esperado).

As funcoes substituidas sao longas: a migration nao e editada a mao. Para muda-la, edite este gerador e rode-o; as fontes
sao as migrations anteriores (versionadas, imutaveis). So texto SQL: nenhum dado, conexao ou credencial.

    python scripts/gerar_migration_cartoes_multiplos.py              # grava a migration e a reversao
    python scripts/gerar_migration_cartoes_multiplos.py --verificar  # so compara com os arquivos versionados

O teste tests/test_gerador_migration_cartoes_multiplos.py confere que os arquivos versionados sao a saida exata.
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
MARCA = 'FIN-CARTOES-MULTIPLOS-01'
VERSAO = '20261213090000'
F1212 = '20261212090000_financeiro_cartao_nubank_creditos.sql'


def bloco(arquivo, nome):
    texto = (MIG / arquivo).read_text(encoding='utf-8')
    m = list(re.finditer(r'create (?:or replace )?function financeiro\.' + nome + r'\(', texto))
    assert m, nome
    ini = m[-1].start()
    fim = texto.index('\n$$;', ini) + len('\n$$;')
    return texto[ini:fim]


def trocar(texto, antigo, novo, vezes=1):
    n = texto.count(antigo)
    assert n == vezes, f'trecho encontrado {n} vezes (esperado {vezes}): {antigo[:80]!r}'
    return texto.replace(antigo, novo)


def como_replace(b):
    return re.sub(r'^create function', 'create or replace function', b)


FONTES = {
    'analisar_importacao_cartao': F1212,
    'importar_fatura_cartao': F1212,
    'fatura_por_categoria': F1212,
    'lancamentos_fatura_por_categoria': F1212,
}
ORIG = {n: bloco(a, n) for n, a in FONTES.items()}
NOVO = {}
CARTAO_JSON = ("(select jsonb_build_object('id', v.id, 'nome', v.nome, 'final', v.final, 'tipo', v.tipo, 'situacao', v.situacao)\n"
               "                                    from financeiro.cartao_vinculado v where v.id = {col})")

# ---------------------------------------------------------------------------------------------------------------------
# Previa: cartao de origem pelo final do arquivo ou pela escolha; duplicidade e conciliacao que distinguem cartoes
# ---------------------------------------------------------------------------------------------------------------------
t = ORIG['analisar_importacao_cartao']
t = trocar(t, "    v_cred_usados integer[] := '{}';  -- compras ja vinculadas a um credito deste arquivo\nbegin\n",
           "    v_cred_usados integer[] := '{}';  -- compras ja vinculadas a um credito deste arquivo\n"
           f"    v_cv        integer;  -- {MARCA}: cartao vinculado de origem (null = sem cartao identificado)\n"
           "    v_cv_origem text;     -- ARQUIVO (final do arquivo) ou ESCOLHA (do usuario na previa)\n"
           "    v_cv_esc    integer;\n"
           "    v_final     text;     -- final do cartao informado no arquivo\n"
           "    v_cv_lote   text;     -- o cartao na chave da duplicidade no proprio arquivo\n"
           "begin\n")
t = trocar(t, "        v_cred_cands := '[]'::jsonb;\n",
           "        v_cred_cands := '[]'::jsonb;\n        v_cv := null;\n        v_cv_origem := null;\n        v_cv_esc := null;\n")
t = trocar(t, "        -- FIN-CARTAO-DESPESAS-FIXAS-01: recorrencia do cartao pela descricao.",
           f"        -- {MARCA}: cartao vinculado de origem (fisico, virtual ou adicional do mesmo contrato): pelo final que o\n"
           "        -- arquivo informa (cartao_final, lido do PDF) ou pela escolha do usuario (cartao_vinculado_escolhido_id; 0 = sem\n"
           "        -- cartao identificado). Final ausente ou nao cadastrado: sem cartao identificado, nunca um cartao presumido.\n"
           "        v_final := right(nullif(regexp_replace(coalesce(v_l ->> 'cartao_final', ''), '[^0-9]', '', 'g'), ''), 4);\n"
           "        if v_l ? 'cartao_vinculado_escolhido_id' then\n"
           "            begin\n"
           "                v_cv_esc := coalesce(nullif(v_l ->> 'cartao_vinculado_escolhido_id', '')::integer, 0);\n"
           "            exception when others then\n"
           "                v_cv_esc := -1;\n"
           "            end;\n"
           "            v_cv_origem := 'ESCOLHA';\n"
           "            if v_cv_esc <> 0 then\n"
           "                select v.id into v_cv from financeiro.cartao_vinculado v where v.id = v_cv_esc and v.contrato_id = p_cartao_id;\n"
           "                if v_cv is null then\n"
           "                    v_status := 'revisar';\n"
           "                    v_rev_nat := true;\n"
           "                    v_msgs := v_msgs || '\"Cartao escolhido nao e deste contrato: escolha outro ou deixe sem cartao identificado.\"'::jsonb;\n"
           "                end if;\n"
           "            end if;\n"
           "        elsif v_final is not null then\n"
           "            select v.id into v_cv from financeiro.cartao_vinculado v where v.contrato_id = p_cartao_id and v.final = v_final;\n"
           "            if v_cv is not null then\n"
           "                v_cv_origem := 'ARQUIVO';\n"
           "            else\n"
           "                v_msgs := v_msgs || to_jsonb(format('Cartao final %s nao cadastrado neste contrato: a linha entra sem cartao identificado (cadastre o cartao em Cartoes ou escolha na previa).', v_final));\n"
           "            end if;\n"
           "        end if;\n"
           "        v_cv_lote := coalesce('c' || v_cv::text, 'f' || v_final, '');\n"
           "\n"
           "        -- FIN-CARTAO-DESPESAS-FIXAS-01: recorrencia do cartao pela descricao.")
# duplicidade no proprio arquivo: compras identicas de cartoes diferentes nao se confundem (credito e compra)
t = trocar(t, "            if v_chave = any(v_chaves) and not coalesce((v_l ->> 'manter_duplicada')::boolean, false) then\n",
           "            if v_chave || '|' || v_cv_lote = any(v_chaves) and not coalesce((v_l ->> 'manter_duplicada')::boolean, false) then\n",
           vezes=2)
t = trocar(t, "                v_chaves := v_chaves || v_chave;\n",
           "                v_chaves := v_chaves || (v_chave || '|' || v_cv_lote);\n", vezes=2)
# reconstrucao: a compra removida pela limpeza seletiva volta com a Categoria de Despesa que o usuario lhe deu
t = trocar(t, """            else
                v_sug := financeiro.sugestao_categoria_importacao(p_perfil_id, v_l ->> 'descricao_classificacao', v_norm,
                                                                  v_cartao.categoria_id);
                v_cat := (v_sug ->> 'categoria_id')::integer;
                v_cat_origem := v_sug ->> 'origem';
                if v_sug ->> 'aviso' is not null then
                    v_msgs := v_msgs || to_jsonb(v_sug ->> 'aviso');
                end if;
            end if;
""", f"""            else
                -- {MARCA}: reconstrucao da fatura: a mesma compra (cartao, data, valor e descricao) removida pela limpeza
                -- seletiva volta com a Categoria de Despesa que o usuario lhe deu (a foto da limpeza, em operacao_cartao)
                select (f ->> 'categoria_id')::integer into v_cat
                  from financeiro.operacao_cartao o
                 cross join lateral jsonb_array_elements(coalesce(o.resultado -> 'fotos' -> 'compras', '[]'::jsonb)) f
                 where o.operacao = 'limpar_importacoes' and o.perfil_financeiro_id = p_perfil_id
                   and (f ->> 'cartao_id')::integer = p_cartao_id and (f ->> 'valor')::numeric = v_valor
                   and (f ->> 'data_compra')::date = v_data
                   and lower(coalesce(f ->> 'descricao_original_normalizada', f ->> 'descricao')) = lower(v_norm)
                   and exists (select 1 from public.categoria c where c.id = (f ->> 'categoria_id')::integer and coalesce(c.ativo, true))
                 order by o.criado_em desc
                 limit 1;
                if v_cat is not null then
                    v_cat_origem := 'reconstrucao';
                else
                    v_sug := financeiro.sugestao_categoria_importacao(p_perfil_id, v_l ->> 'descricao_classificacao', v_norm,
                                                                      v_cartao.categoria_id);
                    v_cat := (v_sug ->> 'categoria_id')::integer;
                    v_cat_origem := v_sug ->> 'origem';
                    if v_sug ->> 'aviso' is not null then
                        v_msgs := v_msgs || to_jsonb(v_sug ->> 'aviso');
                    end if;
                end if;
            end if;
""")
CV_IGUAL = "(v_cv is null or {c}.cartao_vinculado_id is null or {c}.cartao_vinculado_id = v_cv)"
t = trocar(t, "                             and cf.chave = v_chave and financeiro.pertence_ao_perfil(cf.perfil_financeiro_id, p_perfil_id)) then\n",
           "                             and cf.chave = v_chave and financeiro.pertence_ao_perfil(cf.perfil_financeiro_id, p_perfil_id)\n"
           f"                             and {CV_IGUAL.format(c='cf')}) then  -- {MARCA}\n")
t = trocar(t, "                   and not l.id = any(v_cred_usados)\n",
           "                   and not l.id = any(v_cred_usados)\n"
           f"                   and {CV_IGUAL.format(c='l')}  -- {MARCA}: a compra do mesmo cartao\n")
t = trocar(t, "                   and l.data_compra = v_data and l.valor = v_valor\n",
           "                   and l.data_compra = v_data and l.valor = v_valor\n"
           f"                   -- {MARCA}: de outro cartao vinculado nao e a mesma compra\n"
           f"                   and {CV_IGUAL.format(c='l')}\n")
t = trocar(t, "                   and not (coalesce(l.is_recorrente, false) and l.item_despesa_id is not null)\n"
              "                   and not l.id = any(v_usados)\n",
           "                   and not (coalesce(l.is_recorrente, false) and l.item_despesa_id is not null)\n"
           "                   and not l.id = any(v_usados)\n"
           f"                   and {CV_IGUAL.format(c='l')}  -- {MARCA}\n")
t = trocar(t, "            'credito', v_cred));  -- FIN-CARTAO-NUBANK-CREDITOS-01\n",
           "            'credito', v_cred)  -- FIN-CARTAO-NUBANK-CREDITOS-01\n"
           f"            -- {MARCA}: cartao de origem\n"
           "            || jsonb_build_object(\n"
           "            'cartao_final', v_final,\n"
           "            'cartao_vinculado_id', v_cv,\n"
           "            'cartao_vinculado', " + CARTAO_JSON.format(col='v_cv') + ",\n"
           "            'cartao_origem', v_cv_origem,\n"
           "            'cartao_vinculado_escolhido_id', v_cv_esc));\n")
t = trocar(t, "        'situacao_fatura', financeiro.situacao_fatura(financeiro.fatura_do_mes(p_cartao_id, v_comp)),\n",
           "        'situacao_fatura', financeiro.situacao_fatura(financeiro.fatura_do_mes(p_cartao_id, v_comp)),\n"
           f"        -- {MARCA}: cartoes vinculados do contrato (a previa pode escolher o de origem)\n"
           "        'cartoes_contrato', coalesce((select jsonb_agg(jsonb_build_object('id', v.id, 'nome', v.nome, 'final', v.final,\n"
           "                                                                 'tipo', v.tipo, 'portador', v.portador, 'situacao', v.situacao)\n"
           "                                              order by v.situacao <> 'ATIVO', v.final)\n"
           "                                        from financeiro.cartao_vinculado v where v.contrato_id = p_cartao_id), '[]'::jsonb),\n")
t = trocar(t, "            'ignorados', count(*) filter (where l ->> 'status' = 'ignorado'))\n",
           "            'ignorados', count(*) filter (where l ->> 'status' = 'ignorado'),\n"
           f"            -- {MARCA}: finais do arquivo sem cartao cadastrado e linhas sem cartao identificado\n"
           "            'cartoes_nao_cadastrados', coalesce(jsonb_agg(distinct l ->> 'cartao_final')\n"
           "                filter (where l ->> 'cartao_final' is not null and l ->> 'cartao_vinculado_id' is null), '[]'::jsonb),\n"
           "            'sem_cartao_identificado', count(*) filter (where l ->> 'cartao_vinculado_id' is null\n"
           "                                                         and l ->> 'status' not in ('ignorado', 'duplicado', 'conciliado')))\n")
NOVO['analisar_importacao_cartao'] = t

# ---------------------------------------------------------------------------------------------------------------------
# Confirmacao: o cartao de origem gravado na compra, na previsao realizada e no credito
# ---------------------------------------------------------------------------------------------------------------------
t = ORIG['importar_fatura_cartao']
t = trocar(t, "                'IMPORTACAO', null);\n            v_realizadas := v_realizadas + 1;\n",
           "                'IMPORTACAO', null);\n            v_realizadas := v_realizadas + 1;\n"
           f"            -- {MARCA}: o cartao de origem da cobranca real\n"
           "            if (v_l ->> 'cartao_vinculado_id') is not null then\n"
           "                update public.lancamento_agregado set cartao_vinculado_id = (v_l ->> 'cartao_vinculado_id')::integer where id = v_id;\n"
           "            end if;\n")
t = trocar(t, "                                                    is_importado, origem_importacao, criado_em, mes_fatura_original)\n",
           "                                                    is_importado, origem_importacao, criado_em, mes_fatura_original,\n"
           f"                                                    cartao_vinculado_id)  -- {MARCA}\n")
t = trocar(t, "                    nullif(v_orig, v_alvo))\n",
           "                    nullif(v_orig, v_alvo), (v_l ->> 'cartao_vinculado_id')::integer)\n")
t = trocar(t, "                                               chave, origem_importacao, operacao_chave, user_id)\n",
           "                                               chave, origem_importacao, operacao_chave, user_id, cartao_vinculado_id)\n")
t = trocar(t, "                left(coalesce(v_l ->> 'origem_importacao', 'csv'), 20), p_chave, (select auth.uid()))\n",
           "                left(coalesce(v_l ->> 'origem_importacao', 'csv'), 20), p_chave, (select auth.uid()),\n"
           f"                (v_l ->> 'cartao_vinculado_id')::integer)  -- {MARCA}\n")
NOVO['importar_fatura_cartao'] = t

# ---------------------------------------------------------------------------------------------------------------------
# Cartoes: a fatura unica do contrato por cartao vinculado; lancamentos com o cartao e o filtro por cartao
# ---------------------------------------------------------------------------------------------------------------------
t = ORIG['fatura_por_categoria']
t = trocar(t, "        'total_creditos', v_creditos,\n",
           "        'total_creditos', v_creditos,\n"
           f"        -- {MARCA}: a fatura (unica do contrato) por cartao vinculado; o que nao tem cartao identificado, a parte\n"
           "        'por_cartao', financeiro.fatura_por_cartao(p_perfil_id, p_cartao_id, v_mes),\n")
NOVO['fatura_por_categoria'] = t

t = ORIG['lancamentos_fatura_por_categoria']
t = trocar(t, "    v_gerir  boolean;\nbegin\n", "    v_gerir  boolean;\n" f"    v_cv     integer;  -- {MARCA}\n" "begin\n")
t = trocar(t, "    if v_filtro not in ('todos', 'sem_categoria', 'despesas_fixas', 'compras_parceladas', 'creditos') then",
           f"    if v_filtro ~ '^cartao-[0-9]{{1,9}}$' then  -- {MARCA}: compras e creditos de um cartao vinculado (0 = sem cartao)\n"
           "        v_cv := substring(v_filtro from 8)::integer;\n"
           "    elsif v_filtro not in ('todos', 'sem_categoria', 'despesas_fixas', 'compras_parceladas', 'creditos') then")
t = trocar(t, "                       'compra_id', l.compra_id,\n",
           "                       'compra_id', l.compra_id,\n"
           "                       'cartao_vinculado', " + CARTAO_JSON.format(col='l.cartao_vinculado_id') + ",\n")
t = trocar(t, "               and (v_filtro = 'todos' or (v_filtro = 'sem_categoria' and nat.n = 'OUTROS')",
           "               and (v_filtro = 'todos' or (v_cv is not null and coalesce(l.cartao_vinculado_id, 0) = v_cv)\n"
           "                    or (v_filtro = 'sem_categoria' and nat.n = 'OUTROS')")
t = trocar(t, "                       'compra_id', null,\n",
           "                       'compra_id', null,\n"
           "                       'cartao_vinculado', " + CARTAO_JSON.format(col='cf.cartao_vinculado_id') + ",\n")
t = trocar(t, "             where v_filtro in ('todos', 'creditos')\n",
           "             where (v_filtro in ('todos', 'creditos') or (v_cv is not null and coalesce(cf.cartao_vinculado_id, 0) = v_cv))\n")
NOVO['lancamentos_fatura_por_categoria'] = t

NOVOS = f"""
-- =====================================================================================================================
-- 1. Cartoes vinculados ao contrato (o "cartao" atual: public.item_despesa tipo Agregador, com a fatura unica)
-- =====================================================================================================================
create table financeiro.cartao_vinculado (
    id                   integer     generated always as identity primary key,
    perfil_financeiro_id integer     not null,
    contrato_id          integer     not null references public.item_despesa (id),
    nome                 text        not null check (length(btrim(nome)) between 1 and 60),
    final                text        not null check (final ~ '^[0-9]{{4}}$'),
    tipo                 text        not null check (tipo in ('FISICO', 'VIRTUAL', 'ADICIONAL')),
    portador             text        check (portador is null or length(portador) <= 80),
    situacao             text        not null default 'ATIVO' check (situacao in ('ATIVO', 'CANCELADO', 'SUBSTITUIDO')),
    data_inicio          date,
    data_cancelamento    date,
    substituto_id        integer     references financeiro.cartao_vinculado (id),
    user_id              uuid        references auth.users (id) on delete set null,
    criado_em            timestamptz not null default now(),
    atualizado_em        timestamptz,
    unique (contrato_id, final),
    check (substituto_id is null or substituto_id <> id),
    check (situacao <> 'SUBSTITUIDO' or substituto_id is not null),
    check (data_cancelamento is null or data_inicio is null or data_cancelamento >= data_inicio)
);
comment on table financeiro.cartao_vinculado is
    '{MARCA}: cartao fisico, virtual ou adicional de um contrato de cartao (item_despesa Agregador), que continua com a fatura e o pagamento unicos. So os 4 ultimos digitos; nunca numero completo, validade ou CVV.';
alter table financeiro.cartao_vinculado enable row level security;
alter table financeiro.cartao_vinculado force row level security;
revoke all on financeiro.cartao_vinculado from public, anon, authenticated;

-- A compra e o credito guardam o cartao de origem (null = sem cartao identificado).
alter table public.lancamento_agregado add column cartao_vinculado_id integer references financeiro.cartao_vinculado (id);
create index lancamento_agregado_cartao_vinculado on public.lancamento_agregado (cartao_vinculado_id)
    where cartao_vinculado_id is not null;
alter table financeiro.credito_fatura add column cartao_vinculado_id integer references financeiro.cartao_vinculado (id);

-- Nenhuma referencia cruzada: o cartao vinculado e do perfil do contrato; o substituto, do mesmo contrato; a compra e o
-- credito, so de um cartao do proprio contrato.
create function financeiro.conferir_cartao_vinculado()
    returns trigger
    language plpgsql
    security definer
    set search_path = ''
as $$
begin
    if not exists (select 1 from public.item_despesa i where i.id = new.contrato_id and i.tipo = 'Agregador'
                      and financeiro.pertence_ao_perfil(i.perfil_financeiro_id, new.perfil_financeiro_id)) then
        raise exception 'Contrato de cartao de outro perfil' using errcode = '23514';
    end if;
    if new.substituto_id is not null and not exists (select 1 from financeiro.cartao_vinculado v
                                                      where v.id = new.substituto_id and v.contrato_id = new.contrato_id) then
        raise exception 'O cartao substituto deve ser do mesmo contrato' using errcode = '23514';
    end if;
    return new;
end
$$;
create trigger cartao_vinculado_conferir before insert or update on financeiro.cartao_vinculado
    for each row execute function financeiro.conferir_cartao_vinculado();

create function financeiro.conferir_cartao_da_compra()
    returns trigger
    language plpgsql
    security definer
    set search_path = ''
as $$
begin
    if new.cartao_vinculado_id is not null and not exists (select 1 from financeiro.cartao_vinculado v
                                                            where v.id = new.cartao_vinculado_id and v.contrato_id = new.cartao_id) then
        raise exception 'O cartao de origem nao e deste contrato' using errcode = '23514';
    end if;
    return new;
end
$$;
create trigger lancamento_cartao_vinculado before insert or update of cartao_vinculado_id, cartao_id on public.lancamento_agregado
    for each row execute function financeiro.conferir_cartao_da_compra();
create trigger credito_cartao_vinculado before insert or update of cartao_vinculado_id, cartao_id on financeiro.credito_fatura
    for each row execute function financeiro.conferir_cartao_da_compra();
revoke execute on function financeiro.conferir_cartao_vinculado() from public, anon, authenticated;
revoke execute on function financeiro.conferir_cartao_da_compra() from public, anon, authenticated;

-- Cartoes vinculados de um contrato (com o uso: compras e creditos de origem), para a tela de Cartoes.
create function financeiro.cartoes_vinculados(p_perfil_id integer, p_contrato_id integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    perform financeiro.cartao_do_perfil(p_perfil_id, p_contrato_id, false);
    return coalesce((
        select jsonb_agg(jsonb_build_object(
                   'id', v.id, 'nome', v.nome, 'final', v.final, 'tipo', v.tipo, 'portador', v.portador,
                   'situacao', v.situacao, 'data_inicio', v.data_inicio, 'data_cancelamento', v.data_cancelamento,
                   'substituto', (select jsonb_build_object('id', s.id, 'final', s.final, 'nome', s.nome)
                                    from financeiro.cartao_vinculado s where s.id = v.substituto_id),
                   'compras', (select count(*) from public.lancamento_agregado l where l.cartao_vinculado_id = v.id),
                   'creditos', (select count(*) from financeiro.credito_fatura cf where cf.cartao_vinculado_id = v.id),
                   'versao', md5(v::text))
               order by v.situacao <> 'ATIVO', v.tipo, v.final)
          from financeiro.cartao_vinculado v
         where v.contrato_id = p_contrato_id), '[]'::jsonb);
end
$$;

-- Cadastro (p_cartao_vinculado_id null) ou edicao (com a versao lida) de um cartao vinculado. O cartao nunca e excluido:
-- cancelado ou substituido, continua no historico (as compras de origem nao mudam). O final so muda sem compra de origem.
create function financeiro.salvar_cartao_vinculado(p_perfil_id integer, p_contrato_id integer, p_cartao_vinculado_id integer,
                                                   p_dados jsonb, p_versao text)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_atual   financeiro.cartao_vinculado;
    v_nome    text;
    v_final   text;
    v_tipo    text;
    v_port    text;
    v_sit     text;
    v_ini     date;
    v_canc    date;
    v_subst   integer;
    v_id      integer;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    perform financeiro.cartao_do_perfil(p_perfil_id, p_contrato_id, false);
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' then
        raise exception 'Dados do cartao invalidos' using errcode = '22023';
    end if;
    if p_dados ?| array['numero_cartao', 'numero', 'codigo_seguranca', 'cvv', 'data_validade', 'validade'] then
        raise exception 'Numero completo, validade e codigo de seguranca nao sao guardados: informe so os 4 ultimos digitos'
            using errcode = '22023';
    end if;
    perform pg_advisory_xact_lock(20261023, p_perfil_id);  -- mesma trava das compras e da importacao do perfil
    perform 1 from public.item_despesa where id = p_contrato_id for update;
    if p_cartao_vinculado_id is not null then
        select * into v_atual from financeiro.cartao_vinculado v where v.id = p_cartao_vinculado_id and v.contrato_id = p_contrato_id
           for update;
        if not found then
            raise exception 'Cartao vinculado nao encontrado neste contrato' using errcode = '42501';
        end if;
        if p_versao is distinct from md5(v_atual::text) then
            raise exception 'O cartao foi alterado por outra operacao: recarregue a tela' using errcode = '40001';
        end if;
    end if;
    v_nome := btrim(coalesce(p_dados ->> 'nome', v_atual.nome, ''));
    v_final := regexp_replace(coalesce(p_dados ->> 'final', v_atual.final, ''), '\\s', '', 'g');
    v_tipo := upper(btrim(coalesce(p_dados ->> 'tipo', v_atual.tipo, '')));
    v_port := nullif(btrim(coalesce(p_dados ->> 'portador', v_atual.portador, '')), '');
    v_sit := upper(btrim(coalesce(p_dados ->> 'situacao', v_atual.situacao, 'ATIVO')));
    begin
        v_ini := case when p_dados ? 'data_inicio' then nullif(p_dados ->> 'data_inicio', '')::date else v_atual.data_inicio end;
        v_canc := case when p_dados ? 'data_cancelamento' then nullif(p_dados ->> 'data_cancelamento', '')::date else v_atual.data_cancelamento end;
        v_subst := case when p_dados ? 'substituto_id' then nullif(p_dados ->> 'substituto_id', '')::integer else v_atual.substituto_id end;
    exception when others then
        raise exception 'Data ou cartao substituto invalido' using errcode = '22023';
    end;
    if v_nome = '' or length(v_nome) > 60 then
        raise exception 'Nome do cartao obrigatorio (ate 60 caracteres)' using errcode = '22023';
    end if;
    if v_final !~ '^[0-9]{{4}}$' then
        raise exception 'Informe os 4 ultimos digitos do cartao' using errcode = '22023';
    end if;
    if v_tipo not in ('FISICO', 'VIRTUAL', 'ADICIONAL') then
        raise exception 'Tipo do cartao: fisico, virtual ou adicional' using errcode = '22023';
    end if;
    if v_sit not in ('ATIVO', 'CANCELADO', 'SUBSTITUIDO') then
        raise exception 'Situacao do cartao: ativo, cancelado ou substituido' using errcode = '22023';
    end if;
    if v_sit = 'SUBSTITUIDO' and v_subst is null then
        raise exception 'Informe o cartao substituto' using errcode = '22023';
    end if;
    if v_sit = 'ATIVO' then
        v_canc := null;
    end if;
    if v_atual.id is not null and v_final <> v_atual.final
       and (exists (select 1 from public.lancamento_agregado l where l.cartao_vinculado_id = v_atual.id)
            or exists (select 1 from financeiro.credito_fatura cf where cf.cartao_vinculado_id = v_atual.id)) then
        raise exception 'O final de um cartao com compras nao muda (o historico seria outro cartao): cadastre o novo cartao'
            using errcode = '22023';
    end if;
    if exists (select 1 from financeiro.cartao_vinculado v where v.contrato_id = p_contrato_id and v.final = v_final
                  and v.id is distinct from v_atual.id) then
        raise exception 'Ja ha um cartao final % neste contrato', v_final using errcode = '23505';
    end if;
    if v_atual.id is null then
        insert into financeiro.cartao_vinculado (perfil_financeiro_id, contrato_id, nome, final, tipo, portador, situacao,
                                                 data_inicio, data_cancelamento, substituto_id, user_id)
        values (p_perfil_id, p_contrato_id, v_nome, v_final, v_tipo, v_port, v_sit, v_ini, v_canc, v_subst, (select auth.uid()))
        returning id into v_id;
    else
        update financeiro.cartao_vinculado
           set nome = v_nome, final = v_final, tipo = v_tipo, portador = v_port, situacao = v_sit, data_inicio = v_ini,
               data_cancelamento = v_canc, substituto_id = v_subst, atualizado_em = now()
         where id = v_atual.id
        returning id into v_id;
    end if;
    return (select c from jsonb_array_elements(financeiro.cartoes_vinculados(p_perfil_id, p_contrato_id)) c
             where (c ->> 'id')::integer = v_id);
end
$$;

-- A fatura unica do contrato por cartao vinculado (executado das compras e creditos de cada um); o que nao tem cartao
-- identificado fica numa linha propria. A soma das linhas e o valor a pagar da fatura.
create function financeiro.fatura_por_cartao(p_perfil_id integer, p_contrato_id integer, p_mes date)
    returns jsonb
    language sql
    stable
    security definer
    set search_path = ''
as $$
    with compras as (
        select l.cartao_vinculado_id as cv,
               financeiro.valor_executado_compra(l.valor, financeiro.situacao_previsao(l.id,
                   financeiro.natureza_da_compra(l.total_parcelas, l.is_recorrente, l.item_despesa_id, l.categoria_cartao_id),
                   l.is_importado, l.cartao_id, l.mes_fatura)) as valor
          from public.lancamento_agregado l
         where l.cartao_id = p_contrato_id and l.mes_fatura = date_trunc('month', p_mes::timestamp)::date
           and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id)
    ),
    creditos as (
        select cf.cartao_vinculado_id as cv, cf.valor
          from financeiro.credito_fatura cf
         where cf.fatura_id = financeiro.fatura_do_mes(p_contrato_id, date_trunc('month', p_mes::timestamp)::date)
    ),
    linhas as (
        select v.id, v.nome, v.final, v.tipo, v.portador, v.situacao,
               coalesce((select sum(c.valor) from compras c where c.cv = v.id), 0) as compras,
               (select count(*) from compras c where c.cv = v.id and c.valor > 0) as quantidade,
               coalesce((select sum(c.valor) from creditos c where c.cv = v.id), 0) as creditos
          from financeiro.cartao_vinculado v where v.contrato_id = p_contrato_id
        union all
        select null, 'Sem cartao identificado', null, null, null, null,
               coalesce((select sum(c.valor) from compras c where c.cv is null), 0),
               (select count(*) from compras c where c.cv is null and c.valor > 0),
               coalesce((select sum(c.valor) from creditos c where c.cv is null), 0)
    )
    select coalesce(jsonb_agg(jsonb_build_object('cartao_vinculado_id', x.id, 'nome', x.nome, 'final', x.final, 'tipo', x.tipo,
                                                 'portador', x.portador, 'situacao', x.situacao, 'compras', x.compras,
                                                 'creditos', x.creditos, 'total', x.compras - x.creditos, 'quantidade', x.quantidade)
                              order by x.id is null, x.situacao <> 'ATIVO', x.final), '[]'::jsonb)
      from linhas x
     where x.id is not null or x.compras <> 0 or x.creditos <> 0
$$;
revoke execute on function financeiro.fatura_por_cartao(integer, integer, date) from public, anon, authenticated;

-- =====================================================================================================================
-- 2. Limpeza seletiva das despesas importadas (para a reconstrucao das faturas): previa e execucao
-- =====================================================================================================================
-- Elegivel: so o que a importacao registrou como seu (financeiro.operacao_cartao 'importar_fatura': as compras inseridas em
-- 'lancamentos' e os creditos em 'creditos_ids'), ainda marcado como importado. Compra importada sem essa evidencia (Flask,
-- versao anterior) e "origem nao comprovada": nunca entra. Protegidos (interrompem a execucao): fatura paga ou consolidada,
-- previsao de recorrencia realizada ou conciliada ainda vigente, credito de fora da selecao vinculado. Nada e alterado.
create function financeiro.previa_limpeza_importacoes(p_perfil_id integer, p_cartao_id integer, p_competencia date)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_mes date := date_trunc('month', p_competencia::timestamp)::date;
    v_r   jsonb;
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if p_cartao_id is not null then
        perform financeiro.cartao_do_perfil(p_perfil_id, p_cartao_id, false);
    end if;
    with ops as (
        select o.chave, o.criado_em, o.resultado from financeiro.operacao_cartao o
         where o.operacao = 'importar_fatura' and o.perfil_financeiro_id = p_perfil_id
    ),
    evid as (
        select distinct on (x.id) x.id, x.chave, x.criado_em from (
            select (e.v)::integer as id, o.chave, o.criado_em from ops o
             cross join lateral jsonb_array_elements_text(case when jsonb_typeof(o.resultado -> 'lancamentos') = 'array'
                                                               then o.resultado -> 'lancamentos' else '[]'::jsonb end) e(v)) x
         order by x.id, x.criado_em
    ),
    escopo as (
        select l.* from public.lancamento_agregado l
         where financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id)
           and (p_cartao_id is null or l.cartao_id = p_cartao_id)
           and (v_mes is null or coalesce(l.mes_fatura_original, l.mes_fatura) = v_mes)
    ),
    compras as (
        select l.id, l.cartao_id, l.mes_fatura, coalesce(l.descricao_exibida, l.descricao) as descricao, l.valor, l.data_compra,
               l.numero_parcela, l.total_parcelas, l.cartao_vinculado_id, e.chave,
               case
                   when not coalesce(l.is_importado, false) then 'Sem a marca de importacao'
                   when financeiro.fatura_esta_paga(financeiro.fatura_do_mes(l.cartao_id, l.mes_fatura)) then 'Fatura paga'
                   when exists (select 1 from public.conta c where c.id = financeiro.fatura_do_mes(l.cartao_id, l.mes_fatura)
                                   and c.status_fatura = 'FECHADA') then 'Fatura consolidada'
                   when exists (select 1 from financeiro.ocorrencia_recorrencia_cartao o
                                 where o.lancamento_id = l.id and o.revertida_em is null) then 'Ocorrencia de recorrencia vigente'
               end as protecao
          from escopo l join evid e on e.id = l.id
    ),
    ops_cred as (
        select (e.v)::bigint as id from ops o
         cross join lateral jsonb_array_elements_text(case when jsonb_typeof(o.resultado -> 'creditos_ids') = 'array'
                                                           then o.resultado -> 'creditos_ids' else '[]'::jsonb end) e(v)
    ),
    creditos as (
        select cf.id, cf.cartao_id, cf.mes_fatura, cf.descricao, cf.valor, cf.data_credito, cf.natureza, cf.lancamento_id,
               cf.cartao_vinculado_id,
               case when financeiro.fatura_esta_paga(cf.fatura_id) then 'Fatura paga'
                    when exists (select 1 from public.conta c where c.id = cf.fatura_id and c.status_fatura = 'FECHADA')
                        then 'Fatura consolidada' end as protecao
          from financeiro.credito_fatura cf
         where financeiro.pertence_ao_perfil(cf.perfil_financeiro_id, p_perfil_id)
           and (p_cartao_id is null or cf.cartao_id = p_cartao_id)
           and (v_mes is null or coalesce(cf.mes_fatura_original, cf.mes_fatura) = v_mes)
           and (cf.id in (select id from ops_cred) or cf.operacao_chave in (select chave from ops))
    ),
    -- credito de fora da selecao vinculado a uma compra da selecao: a compra fica protegida
    compras2 as (
        select c.*, coalesce(c.protecao, case when exists (select 1 from financeiro.credito_fatura cf
                                                            where cf.lancamento_id = c.id
                                                              and cf.id not in (select id from creditos)) then
                                                   'Credito de outra importacao vinculado' end) as protecao2
          from compras c
    ),
    nao_comprovadas as (
        select l.id, l.cartao_id, l.mes_fatura, coalesce(l.descricao_exibida, l.descricao) as descricao, l.valor,
               l.origem_importacao
          from escopo l where coalesce(l.is_importado, false) and l.id not in (select id from evid)
    )
    select jsonb_build_object(
        'filtro', jsonb_build_object('cartao_id', p_cartao_id, 'competencia', v_mes),
        'compras_elegiveis', coalesce((select jsonb_agg(jsonb_build_object('id', c.id, 'cartao_id', c.cartao_id,
                'mes_fatura', c.mes_fatura, 'descricao', c.descricao, 'valor', c.valor, 'data_compra', c.data_compra,
                'parcela', c.numero_parcela || '/' || c.total_parcelas, 'cartao_vinculado_id', c.cartao_vinculado_id,
                'operacao', c.chave) order by c.cartao_id, c.mes_fatura, c.id) from compras2 c where c.protecao2 is null), '[]'::jsonb),
        'creditos_elegiveis', coalesce((select jsonb_agg(jsonb_build_object('id', c.id, 'cartao_id', c.cartao_id,
                'mes_fatura', c.mes_fatura, 'descricao', c.descricao, 'valor', c.valor, 'natureza', c.natureza,
                'lancamento_id', c.lancamento_id) order by c.cartao_id, c.mes_fatura, c.id)
                from creditos c where c.protecao is null), '[]'::jsonb),
        'protegidos', coalesce((select jsonb_agg(x order by x ->> 'tipo', (x ->> 'id')::bigint) from (
                select jsonb_build_object('tipo', 'compra', 'id', c.id, 'cartao_id', c.cartao_id, 'mes_fatura', c.mes_fatura,
                                          'descricao', c.descricao, 'valor', c.valor, 'motivo', c.protecao2) x
                  from compras2 c where c.protecao2 is not null
                union all
                select jsonb_build_object('tipo', 'credito', 'id', c.id, 'cartao_id', c.cartao_id, 'mes_fatura', c.mes_fatura,
                                          'descricao', c.descricao, 'valor', c.valor, 'motivo', c.protecao)
                  from creditos c where c.protecao is not null) y), '[]'::jsonb),
        'nao_comprovadas', coalesce((select jsonb_agg(jsonb_build_object('id', n.id, 'cartao_id', n.cartao_id,
                'mes_fatura', n.mes_fatura, 'descricao', n.descricao, 'valor', n.valor, 'origem_importacao', n.origem_importacao,
                'motivo', 'Origem da importacao nao comprovada (sem registro da operacao): fora da limpeza')
                order by n.cartao_id, n.mes_fatura, n.id) from nao_comprovadas n), '[]'::jsonb),
        'por_fatura', coalesce((select jsonb_agg(jsonb_build_object(
                'cartao_id', f.cartao_id, 'mes_fatura', f.mes_fatura, 'compras', f.compras, 'total_compras', f.total_compras,
                'creditos', f.creditos, 'total_creditos', f.total_creditos,
                'valor_a_pagar_atual', financeiro.executado_fatura(financeiro.fatura_do_mes(f.cartao_id, f.mes_fatura)),
                'valor_a_pagar_depois', financeiro.executado_fatura(financeiro.fatura_do_mes(f.cartao_id, f.mes_fatura))
                                        - f.executado_compras + f.total_creditos,
                'previsoes_pendentes', (select count(*) from public.lancamento_agregado p
                                         where p.cartao_id = f.cartao_id and p.mes_fatura = f.mes_fatura
                                           and financeiro.situacao_previsao(p.id, financeiro.natureza_da_compra(p.total_parcelas,
                                               p.is_recorrente, p.item_despesa_id, p.categoria_cartao_id), p.is_importado,
                                               p.cartao_id, p.mes_fatura) = 'PREVISTA'))
                order by f.cartao_id, f.mes_fatura)
              from (select z.cartao_id, z.mes_fatura, sum(z.n_compra) as compras, sum(z.v_compra) as total_compras,
                           sum(z.e_compra) as executado_compras, sum(z.n_cred) as creditos, sum(z.v_cred) as total_creditos
                      from (select c.cartao_id, c.mes_fatura, 1 as n_compra, c.valor as v_compra,
                                   c.valor as e_compra, 0 as n_cred, 0 as v_cred
                              from compras2 c where c.protecao2 is null
                            union all
                            select c.cartao_id, c.mes_fatura, 0, 0, 0, 1, c.valor from creditos c where c.protecao is null) z
                     group by z.cartao_id, z.mes_fatura) f), '[]'::jsonb))
      into v_r;
    v_r := v_r || jsonb_build_object(
        'totais', jsonb_build_object(
            'compras_elegiveis', jsonb_array_length(v_r -> 'compras_elegiveis'),
            'valor_compras', coalesce((select sum((x ->> 'valor')::numeric) from jsonb_array_elements(v_r -> 'compras_elegiveis') x), 0),
            'creditos_elegiveis', jsonb_array_length(v_r -> 'creditos_elegiveis'),
            'valor_creditos', coalesce((select sum((x ->> 'valor')::numeric) from jsonb_array_elements(v_r -> 'creditos_elegiveis') x), 0),
            'protegidos', jsonb_array_length(v_r -> 'protegidos'),
            'nao_comprovadas', jsonb_array_length(v_r -> 'nao_comprovadas')),
        'executavel', jsonb_array_length(v_r -> 'protegidos') = 0
                      and (jsonb_array_length(v_r -> 'compras_elegiveis') + jsonb_array_length(v_r -> 'creditos_elegiveis')) > 0,
        'hash', md5(coalesce((select string_agg('c' || (x ->> 'id'), ',' order by (x ->> 'id')::integer)
                                from jsonb_array_elements(v_r -> 'compras_elegiveis') x), '') || '|'
                    || coalesce((select string_agg('k' || (x ->> 'id'), ',' order by (x ->> 'id')::bigint)
                                   from jsonb_array_elements(v_r -> 'creditos_elegiveis') x), '')));
    return v_r;
end
$$;

-- Execucao (so o perfil Pessoal, pelo titular): refaz a previa sob as travas, confere a impressao (hash) que o usuario
-- conferiu e recusa com protegido. Remove os creditos e as compras elegiveis numa transacao, recalcula as faturas e guarda
-- as linhas removidas inteiras na operacao (auditoria). Idempotente pela chave. Movimentos, saldos, pagamentos, faturas,
-- recorrencias e previsoes nao sao tocados.
create function financeiro.limpar_importacoes_cartao(p_perfil_id integer, p_cartao_id integer, p_competencia date,
                                                     p_hash text, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_anterior financeiro.operacao_cartao;
    v_previa   jsonb;
    v_compras  integer[];
    v_creditos bigint[];
    v_fotos_c  jsonb;
    v_fotos_k  jsonb;
    v_meses    record;
    v_res      jsonb;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if not exists (select 1 from public.perfil_financeiro p where p.id = p_perfil_id and p.nome = 'Pessoal') then
        raise exception 'A limpeza das importacoes e so do perfil Pessoal' using errcode = '42501';
    end if;
    if p_chave is null then
        raise exception 'Chave da operacao obrigatoria' using errcode = '22023';
    end if;
    perform pg_advisory_xact_lock(hashtextextended(p_chave::text, 20261213));
    select * into v_anterior from financeiro.operacao_cartao o where o.chave = p_chave;
    if found then
        if v_anterior.user_id is distinct from (select auth.uid()) or v_anterior.perfil_financeiro_id <> p_perfil_id then
            raise exception 'Chave da operacao ja usada' using errcode = '22023';
        end if;
        return (v_anterior.resultado - 'fotos') || jsonb_build_object('repetida', true);
    end if;
    perform pg_advisory_xact_lock(20261023, p_perfil_id);  -- mesma trava das compras e da importacao do perfil
    perform 1 from public.item_despesa i where i.tipo = 'Agregador' and (p_cartao_id is null or i.id = p_cartao_id)
                                           and financeiro.pertence_ao_perfil(i.perfil_financeiro_id, p_perfil_id) for update;
    v_previa := financeiro.previa_limpeza_importacoes(p_perfil_id, p_cartao_id, p_competencia);
    if p_hash is distinct from v_previa ->> 'hash' then
        raise exception 'A previa da limpeza mudou desde a conferencia: confira de novo' using errcode = '40001';
    end if;
    if jsonb_array_length(v_previa -> 'protegidos') > 0 then
        raise exception 'Limpeza interrompida: % registro(s) importado(s) protegido(s) (fatura paga ou consolidada, ocorrencia de recorrencia, credito vinculado). Nada foi removido.',
            jsonb_array_length(v_previa -> 'protegidos') using errcode = 'P0001';
    end if;
    select coalesce(array_agg((x ->> 'id')::integer), '{{}}') into v_compras from jsonb_array_elements(v_previa -> 'compras_elegiveis') x;
    select coalesce(array_agg((x ->> 'id')::bigint), '{{}}') into v_creditos from jsonb_array_elements(v_previa -> 'creditos_elegiveis') x;
    if cardinality(v_compras) + cardinality(v_creditos) = 0 then
        raise exception 'Nada a limpar nesta selecao' using errcode = '22023';
    end if;
    select coalesce(jsonb_agg(to_jsonb(l) order by l.id), '[]'::jsonb) into v_fotos_c from public.lancamento_agregado l where l.id = any(v_compras);
    select coalesce(jsonb_agg(to_jsonb(cf) order by cf.id), '[]'::jsonb) into v_fotos_k from financeiro.credito_fatura cf where cf.id = any(v_creditos);
    delete from financeiro.credito_fatura where id = any(v_creditos);
    delete from public.lancamento_agregado where id = any(v_compras);
    for v_meses in
        select distinct (x ->> 'cartao_id')::integer as cartao, (x ->> 'mes_fatura')::date as mes
          from (select jsonb_array_elements(v_fotos_c) x union all select jsonb_array_elements(v_fotos_k)) y
    loop
        perform financeiro.recalcular_fatura(p_perfil_id, v_meses.cartao, v_meses.mes);
    end loop;
    v_res := jsonb_build_object('compras_removidas', cardinality(v_compras), 'creditos_removidos', cardinality(v_creditos),
                                'valor_compras', v_previa -> 'totais' -> 'valor_compras',
                                'valor_creditos', v_previa -> 'totais' -> 'valor_creditos',
                                'por_fatura', v_previa -> 'por_fatura', 'filtro', v_previa -> 'filtro', 'hash', p_hash);
    insert into financeiro.operacao_cartao (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'limpar_importacoes',
            v_res || jsonb_build_object('fotos', jsonb_build_object('compras', v_fotos_c, 'creditos', v_fotos_k)));
    return v_res;
end
$$;
"""

PERMISSOES = """
revoke execute on function financeiro.cartoes_vinculados(integer, integer) from public, anon;
revoke execute on function financeiro.salvar_cartao_vinculado(integer, integer, integer, jsonb, text) from public, anon;
revoke execute on function financeiro.previa_limpeza_importacoes(integer, integer, date) from public, anon;
revoke execute on function financeiro.limpar_importacoes_cartao(integer, integer, date, text, uuid) from public, anon;
grant execute on function financeiro.cartoes_vinculados(integer, integer) to authenticated;
grant execute on function financeiro.salvar_cartao_vinculado(integer, integer, integer, jsonb, text) to authenticated;
grant execute on function financeiro.previa_limpeza_importacoes(integer, integer, date) to authenticated;
grant execute on function financeiro.limpar_importacoes_cartao(integer, integer, date, text, uuid) to authenticated;
"""

CABECALHO = f"""-- {MARCA} — contratos de cartao com varios cartoes vinculados (fisico, virtual, adicional) e fatura unica.
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes {VERSAO}). Depende de 20261212090000.
-- Validada em cluster local descartavel (tests/test_supabase_cartoes_multiplos.py) e ensaiada numa copia fiel da producao.
-- Doc: docs/FIN_CARTOES_MULTIPLOS_01.md. Gerada por scripts/gerar_migration_cartoes_multiplos.py.
-- Reversao: supabase/reversao/{VERSAO}_cartoes_multiplos_anterior.sql (recusada com cartao vinculado cadastrado).
--
-- Menor evolucao: o "cartao" de hoje (public.item_despesa Agregador + config_agregador) e o contrato, com fatura, pagamento
-- e limites unicos. financeiro.cartao_vinculado guarda os cartoes do contrato (4 ultimos digitos, tipo, portador, situacao,
-- substituto); a compra (public.lancamento_agregado.cartao_vinculado_id) e o credito guardam o cartao de origem, null =
-- sem cartao identificado. A importacao reconhece o cartao pelo final do arquivo ou pela escolha na previa (nunca por
-- presuncao) e nao confunde compras identicas de cartoes diferentes. Cartoes mostra a fatura por cartao. Limpeza seletiva
-- das despesas importadas (previa e execucao), so pelo que a importacao registrou como seu. Nenhum dado existente e
-- alterado pela migration (as colunas novas nascem vazias).
--
-- Funcoes existentes substituidas pelo texto vigente com os trechos marcados "{MARCA}": {', '.join(FONTES)} (texto de
-- 20261212090000).
"""

ORDEM = list(FONTES)
partes = [CABECALHO, NOVOS,
          "\n-- =====================================================================================================================\n"
          "-- 3. Previa, confirmacao e leituras de Cartoes: texto vigente + os trechos marcados\n"
          "-- =====================================================================================================================\n"]
for n in ORDEM:
    partes.append(f"\n-- {n}: texto de {FONTES[n][:14]} + os trechos marcados.\n{como_replace(NOVO[n])}\n")
partes.append(PERMISSOES)
destino = MIG / f'{VERSAO}_financeiro_cartoes_multiplos.sql'

REV = [f"""-- Reversao de {VERSAO} ({MARCA}): volta as funcoes ao texto anterior e remove os cartoes vinculados, as colunas de
-- cartao de origem e a limpeza seletiva. Recusada com cartao vinculado cadastrado (as compras perderiam o cartao). So com
-- autorizacao, retirando a versao de supabase_migrations.schema_migrations.
do $$
begin
    if exists (select 1 from financeiro.cartao_vinculado) then
        raise exception 'Ha cartoes vinculados cadastrados: a reversao apagaria o cartao de origem das compras';
    end if;
end
$$;
"""]
for n in ORDEM:
    REV.append(f"\n-- {n}: texto de {FONTES[n][:14]}.\n{como_replace(ORIG[n])}\n")
REV.append("""
drop function financeiro.limpar_importacoes_cartao(integer, integer, date, text, uuid);
drop function financeiro.previa_limpeza_importacoes(integer, integer, date);
drop function financeiro.fatura_por_cartao(integer, integer, date);
drop function financeiro.salvar_cartao_vinculado(integer, integer, integer, jsonb, text);
drop function financeiro.cartoes_vinculados(integer, integer);
drop trigger credito_cartao_vinculado on financeiro.credito_fatura;
drop trigger lancamento_cartao_vinculado on public.lancamento_agregado;
drop function financeiro.conferir_cartao_da_compra();
alter table financeiro.credito_fatura drop column cartao_vinculado_id;
alter table public.lancamento_agregado drop column cartao_vinculado_id;
drop table financeiro.cartao_vinculado;
drop function financeiro.conferir_cartao_vinculado();
""")

SAIDAS = {destino: ''.join(partes),
          RAIZ / 'supabase' / 'reversao' / f'{VERSAO}_cartoes_multiplos_anterior.sql': ''.join(REV)}
if ARGS.verificar:
    # Bytes exatos (UTF-8), sem CR: o checkout no Windows pode trocar LF por CRLF (core.autocrlf).
    diferentes = [str(p.relative_to(RAIZ)) for p, texto in SAIDAS.items()
                  if not p.exists() or p.read_bytes().replace(b'\r\n', b'\n') != texto.encode('utf-8')]
    print('diferente: ' + ', '.join(diferentes) if diferentes else 'igual')
    sys.exit(1 if diferentes else 0)
for caminho, texto in SAIDAS.items():
    caminho.write_text(texto, encoding='utf-8', newline='\n')
print('ok', destino.stat().st_size)
