"""Gera a migration 20261216090000 (FIN-CARTAO-CREDITOS-02) e a reversao a partir do texto VIGENTE de cada funcao, com
substituicoes conferidas (cada trecho deve ocorrer o numero de vezes esperado).

As funcoes substituidas sao longas: a migration nao e editada a mao. Para muda-la, edite este gerador e rode-o; as fontes
sao as migrations anteriores (versionadas, imutaveis). So texto SQL: nenhum dado, conexao ou credencial.

    python scripts/gerar_migration_cartao_creditos_integridade.py              # grava a migration e a reversao
    python scripts/gerar_migration_cartao_creditos_integridade.py --verificar  # so compara com os arquivos versionados

O teste tests/test_gerador_migration_cartao_creditos_integridade.py confere que os arquivos versionados sao a saida exata.
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
MARCA = 'FIN-CARTAO-CREDITOS-02'
VERSAO = '20261216090000'
F1213 = '20261213090000_financeiro_cartoes_multiplos.sql'


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
    'analisar_importacao_cartao': F1213,
    'importar_fatura_cartao': F1213,
}
ORIG = {n: bloco(a, n) for n, a in FONTES.items()}
NOVO = {}

# ---------------------------------------------------------------------------------------------------------------------
# Previa: natureza do credito e identidade do credito entre arquivos
# ---------------------------------------------------------------------------------------------------------------------
t = ORIG['analisar_importacao_cartao']
t = trocar(t, "    v_cv_lote   text;     -- o cartao na chave da duplicidade no proprio arquivo\nbegin\n",
           "    v_cv_lote   text;     -- o cartao na chave da duplicidade no proprio arquivo\n"
           f"    v_cred_exist  bigint;            -- {MARCA}: credito ja gravado que esta linha repete\n"
           "    v_cred_vistos bigint[] := '{}';  -- creditos gravados ja reconhecidos por uma linha deste arquivo\n"
           "    v_cred_chaves text[] := '{}';    -- chave exata de cada credito deste arquivo\n"
           "    v_cred_txt    text;              -- descricao sem o nome da loja entre aspas\n"
           "begin\n")
t = trocar(t, "    for v_l, v_idx in select e, o from jsonb_array_elements(p_linhas) with ordinality as x(e, o) loop\n"
              "        if jsonb_typeof(v_l) <> 'object' then\n",
           f"    -- {MARCA}: a chave exata de cada credito do arquivo (a mesma calculada abaixo), para que o credito gravado com o\n"
           "    -- mesmo texto seja reconhecido pela sua propria linha, e nao por outra de mesma data e valor.\n"
           "    for v_l in select e from jsonb_array_elements(p_linhas) e where jsonb_typeof(e) = 'object' loop\n"
           "        begin\n"
           "            if v_l ->> 'tipo_movimento' = 'credito' or (v_l ->> 'valor')::numeric < 0 then\n"
           "                v_cred_chaves := v_cred_chaves || concat_ws('|', p_cartao_id, v_comp, nullif(v_l ->> 'data_compra', '')::date,\n"
           "                    round(abs((v_l ->> 'valor')::numeric), 2),\n"
           "                    lower(btrim(coalesce(nullif(v_l ->> 'descricao_normalizada', ''), v_l ->> 'descricao_original', ''))), 'credito');\n"
           "            end if;\n"
           "        exception when others then\n"
           "            null;  -- linha invalida: a analise abaixo a aponta\n"
           "        end;\n"
           "    end loop;\n\n"
           "    for v_l, v_idx in select e, o from jsonb_array_elements(p_linhas) with ordinality as x(e, o) loop\n"
           "        if jsonb_typeof(v_l) <> 'object' then\n")
t = trocar(t, "        v_cv_esc := null;\n", "        v_cv_esc := null;\n        v_cred_exist := null;\n")
t = trocar(t, "        v_credito := case when v_tipo <> 'credito' then null\n"
              "            when lower(coalesce(v_l ->> 'descricao_original', '')) ~ '(pagamento|pgto|pag[ .]?fatura|obrigado pelo pag)' then 'pagamento_fatura'\n"
              "            when lower(coalesce(v_l ->> 'descricao_original', '')) ~ '(\\miof\\M.*(de volta|devolv|estorn|reembols)|(estorno|devolu[a-z]*|reembolso) d[eo] iof)' then 'iof_devolvido'\n",
           f"        -- {MARCA}: o nome da loja entre aspas nao decide a natureza, e o texto que comeca por estorno, devolucao ou\n"
           "        -- reembolso e estorno mesmo com \"pagamento\" no restante: Estorno de \"Pagamento Facil Loja\" abate a fatura. Na\n"
           "        -- duvida (\"Pagamento estornado\"), fica como pagamento, que nao abate.\n"
           "        v_cred_txt := regexp_replace(lower(coalesce(v_l ->> 'descricao_original', '')), '\"[^\"]*\"', ' ', 'g');\n"
           "        v_credito := case when v_tipo <> 'credito' then null\n"
           "            when lower(coalesce(v_l ->> 'descricao_original', '')) ~ '(\\miof\\M.*(de volta|devolv|estorn|reembols)|(estorno|devolu[a-z]*|reembolso) d[eo] iof)' then 'iof_devolvido'\n"
           "            when v_cred_txt ~ '(pagamento|pgto|pag[ .]?fatura|obrigado pelo pag)'\n"
           "                 and v_cred_txt !~ '^\\s*(estorno|estornad|devolu|reembolso|cancelamento|chargeback)' then 'pagamento_fatura'\n")
t = trocar(t, "            elsif exists (select 1 from financeiro.credito_fatura cf\n"
              "                           where cf.cartao_id = p_cartao_id and coalesce(cf.mes_fatura_original, cf.mes_fatura) = v_comp\n"
              "                             and cf.chave = v_chave and financeiro.pertence_ao_perfil(cf.perfil_financeiro_id, p_perfil_id)\n"
              "                             and (v_cv is null or cf.cartao_vinculado_id is null or cf.cartao_vinculado_id = v_cv)) then  -- FIN-CARTOES-MULTIPLOS-01\n"
              "                v_dup := 'banco';\n"
              "            end if;\n",
           "            elsif not coalesce((v_l ->> '_interna_sem_duplicidade')::boolean, false) then\n"
           f"                -- {MARCA}: identidade do credito entre arquivos. O texto muda entre o PDF e a planilha; cartao, fatura,\n"
           "                -- data e valor nao. Cada credito gravado responde por uma linha so: primeiro o de texto igual; senao, outro\n"
           "                -- de mesma data e valor que nenhuma linha do arquivo repete pelo texto. Creditos legitimos iguais continuam\n"
           "                -- contados um a um: so o que passa do que ja foi gravado e novo.\n"
           "                select cf.id into v_cred_exist\n"
           "                  from financeiro.credito_fatura cf\n"
           "                 where cf.cartao_id = p_cartao_id and coalesce(cf.mes_fatura_original, cf.mes_fatura) = v_comp\n"
           "                   and cf.data_credito = v_data and cf.valor = v_valor\n"
           "                   and financeiro.pertence_ao_perfil(cf.perfil_financeiro_id, p_perfil_id)\n"
           "                   and (v_cv is null or cf.cartao_vinculado_id is null or cf.cartao_vinculado_id = v_cv)  -- FIN-CARTOES-MULTIPLOS-01\n"
           "                   and not cf.id = any(v_cred_vistos)\n"
           "                   and (cf.chave = v_chave or not cf.chave = any(v_cred_chaves))\n"
           "                 order by cf.chave = v_chave desc, cf.id\n"
           "                 limit 1;\n"
           "                if v_cred_exist is not null then\n"
           "                    v_dup := 'banco';\n"
           "                    v_cred_vistos := v_cred_vistos || v_cred_exist;\n"
           "                end if;\n"
           "            end if;\n")
t = trocar(t, "                v_msgs := v_msgs || '\"Credito ja registrado nesta fatura (ou repetido no arquivo): nao e abatido de novo.\"'::jsonb;\n",
           "                v_msgs := v_msgs || coalesce((select to_jsonb(format('Credito ja registrado nesta fatura (mesmo cartao, data e valor%s): nao e abatido de novo.',\n"
           "                                                case when cf.chave <> v_chave then format('; registrado como \"%s\", de %s', cf.descricao,\n"
           "                                                    case when cf.origem_importacao in ('csv', 'xlsx') then 'planilha' else cf.origem_importacao end)\n"
           "                                                     else '' end))\n"
           f"                                                from financeiro.credito_fatura cf where cf.id = v_cred_exist),  -- {MARCA}\n"
           "                                             '\"Credito ja registrado nesta fatura (ou repetido no arquivo): nao e abatido de novo.\"'::jsonb);\n")
t = trocar(t, "                    'compra', null, 'candidatas', '[]'::jsonb, 'fatura_destino', to_char(v_comp, 'MM/YYYY'));\n",
           "                    'compra', null, 'candidatas', '[]'::jsonb, 'fatura_destino', to_char(v_comp, 'MM/YYYY'),\n"
           "                    'registrado', (select jsonb_build_object('id', cf.id, 'descricao', cf.descricao, 'data_credito', cf.data_credito, 'valor', cf.valor,\n"
           f"                                                              'origem_importacao', cf.origem_importacao)  -- {MARCA}\n"
           "                                     from financeiro.credito_fatura cf where cf.id = v_cred_exist));\n")
NOVO['analisar_importacao_cartao'] = t

# ---------------------------------------------------------------------------------------------------------------------
# Confirmacao: a marca interna nao vem do arquivo; a consulta da compra original nao repete a duplicidade
# ---------------------------------------------------------------------------------------------------------------------
t = ORIG['importar_fatura_cartao']
t = trocar(t, "    v_analise := financeiro.analisar_importacao_cartao(p_perfil_id, p_cartao_id, v_comp, p_linhas);\n",
           f"    -- {MARCA}: a marca interna que dispensa a duplicidade so vale na consulta da compra original, abaixo\n"
           "    v_analise := financeiro.analisar_importacao_cartao(p_perfil_id, p_cartao_id, v_comp,\n"
           "        case when jsonb_typeof(p_linhas) = 'array'\n"
           "             then (select coalesce(jsonb_agg(case when jsonb_typeof(e) = 'object' then e - '_interna_sem_duplicidade' else e end order by o),\n"
           "                                   '[]'::jsonb)\n"
           "                     from jsonb_array_elements(p_linhas) with ordinality as x(e, o))\n"
           "             else p_linhas end);\n")
t = trocar(t, "                           'tipo_movimento', 'credito', 'cartao_final', v_l ->> 'cartao_final',\n",
           "                           'tipo_movimento', 'credito', 'cartao_final', v_l ->> 'cartao_final',\n"
           f"                           '_interna_sem_duplicidade', true,  -- {MARCA}: decidida acima; aqui so a compra original\n")
NOVO['importar_fatura_cartao'] = t

CABECALHO = f"""-- {MARCA}: integridade dos creditos da fatura. Gerada por scripts/gerar_migration_cartao_creditos_integridade.py a
-- partir do texto vigente de cada funcao. So funcoes: nenhuma tabela, coluna ou valor muda.
--
-- - Identidade do credito entre arquivos: o mesmo credito importado da planilha e depois do PDF (ou o contrario) nao abate de
--   novo. O texto muda entre os arquivos; cartao, fatura, data e valor nao. Cada credito gravado responde por uma linha so,
--   primeiro pelo texto igual; creditos legitimos de mesmo valor e data continuam contados um a um.
-- - Estorno com "pagamento" no texto (Estorno de "Pagamento Facil Loja") e estorno e abate a fatura; o nome da loja entre
--   aspas nao decide a natureza. "Pagamento recebido" continua fora.
-- - Na confirmacao, a consulta da compra original de cada credito nao toma por duplicidade o credito gravado na mesma
--   importacao (dois creditos de mesma data e valor ficam cada um com a sua compra).
"""
partes = [CABECALHO]
for n in FONTES:
    partes.append(f"\n-- {n}: texto de {FONTES[n][:14]} + os trechos marcados.\n{como_replace(NOVO[n])}\n")
destino = MIG / f'{VERSAO}_financeiro_cartao_creditos_integridade.sql'

REV = [f"""-- Reversao de {VERSAO} ({MARCA}): volta as funcoes ao texto anterior. Nenhuma tabela ou valor muda; os creditos
-- ja gravados ficam. So com autorizacao, retirando a versao de supabase_migrations.schema_migrations.
"""]
for n in FONTES:
    REV.append(f"\n-- {n}: texto de {FONTES[n][:14]}.\n{como_replace(ORIG[n])}\n")

SAIDAS = {destino: ''.join(partes),
          RAIZ / 'supabase' / 'reversao' / f'{VERSAO}_cartao_creditos_integridade_anterior.sql': ''.join(REV)}
if ARGS.verificar:
    # Bytes exatos (UTF-8), sem CR: o checkout no Windows pode trocar LF por CRLF (core.autocrlf).
    diferentes = [str(p.relative_to(RAIZ)) for p, texto in SAIDAS.items()
                  if not p.exists() or p.read_bytes().replace(b'\r\n', b'\n') != texto.encode('utf-8')]
    print('diferente: ' + ', '.join(diferentes) if diferentes else 'igual')
    sys.exit(1 if diferentes else 0)
for caminho, texto in SAIDAS.items():
    caminho.write_text(texto, encoding='utf-8', newline='\n')
print('ok', destino.stat().st_size)
