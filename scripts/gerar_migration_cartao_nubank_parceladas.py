"""Gera a migration 20261211090000 (FIN-CARTAO-NUBANK-PARCELADAS-01) e a reversao a partir do texto VIGENTE da analise da
importacao, com substituicoes conferidas (cada trecho deve ocorrer exatamente uma vez).

A funcao substituida e longa: a migration nao e editada a mao. Para muda-la, edite este gerador e rode-o; a fonte e a
migration anterior (versionada, imutavel). So texto SQL: nenhum dado, conexao ou credencial.

    python scripts/gerar_migration_cartao_nubank_parceladas.py              # grava a migration e a reversao
    python scripts/gerar_migration_cartao_nubank_parceladas.py --verificar  # so compara com os arquivos versionados

O teste tests/test_gerador_migration_cartao_nubank_parceladas.py confere que os arquivos versionados sao a saida exata.
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
MARCA = 'FIN-CARTAO-NUBANK-PARCELADAS-01'
VERSAO = '20261211090000'
FONTE = '20261210090000_financeiro_cartao_importacao_fixas.sql'


def bloco(arquivo, nome):
    texto = (MIG / arquivo).read_text(encoding='utf-8')
    m = list(re.finditer(r'create (?:or replace )?function financeiro\.' + nome + r'\(', texto))
    assert m, nome
    ini = m[-1].start()
    fim = texto.index('\n$$;', ini) + len('\n$$;')
    return texto[ini:fim]


def trocar(texto, antigo, novo):
    n = texto.count(antigo)
    assert n == 1, f'trecho encontrado {n} vezes: {antigo[:80]!r}'
    return texto.replace(antigo, novo)


ORIG = bloco(FONTE, 'analisar_importacao_cartao')
t = ORIG
t = trocar(t, "    v_prev_sug  public.lancamento_agregado;\nbegin\n",
           "    v_prev_sug  public.lancamento_agregado;\n"
           f"    v_rev_nat   boolean;  -- {MARCA}: revisao pela natureza da linha (nao so pela categoria pendente)\n"
           "    v_amb       jsonb;    -- numero no texto que pode ser parcela, fora do padrao do arquivo\n"
           "    v_amb_parc  integer;\n"
           "    v_amb_total integer;\n"
           "    v_amb_res   text;     -- decisao do usuario na previa: PARCELADA ou AVISTA\n"
           "begin\n")
t = trocar(t, "        v_escolha := null;\n",
           "        v_escolha := null;\n        v_rev_nat := false;\n        v_amb := null;\n        v_amb_res := null;\n")

# Parcela no texto fora do padrao do arquivo: decisao do usuario, nada inventado
t = trocar(t, "        v_norm := btrim(coalesce(nullif(v_l ->> 'descricao_normalizada', ''), v_l ->> 'descricao_original', ''));\n",
           "        v_norm := btrim(coalesce(nullif(v_l ->> 'descricao_normalizada', ''), v_l ->> 'descricao_original', ''));\n"
           f"        -- {MARCA}: numero no texto que pode ser parcela, fora do padrao do arquivo (\"MERCADO XYZ 03/10\" no\n"
           "        -- Nubank, que escreve \"Loja - Parcela 3/10\"): pede a decisao do usuario na previa (natureza_parcela PARCELADA,\n"
           "        -- com esse numero, ou AVISTA). Nada e inventado: ate a decisao, a linha fica 1/1 e em revisao.\n"
           "        if jsonb_typeof(v_l -> 'parcela_ambigua') = 'object' and v_tipo <> 'credito' and v_total = 1 then\n"
           "            begin\n"
           "                v_amb_parc := (v_l -> 'parcela_ambigua' ->> 'parcela_atual')::integer;\n"
           "                v_amb_total := (v_l -> 'parcela_ambigua' ->> 'total_parcelas')::integer;\n"
           "            exception when others then\n"
           "                v_amb_parc := null;\n"
           "                v_amb_total := null;\n"
           "            end;\n"
           "            if v_amb_parc >= 1 and v_amb_total between 2 and 60 and v_amb_parc <= v_amb_total then\n"
           "                v_amb := jsonb_build_object('parcela_atual', v_amb_parc, 'total_parcelas', v_amb_total,\n"
           "                                            'rotulo', lpad(v_amb_parc::text, 2, '0') || '/' || lpad(v_amb_total::text, 2, '0'));\n"
           "                v_amb_res := upper(nullif(btrim(v_l ->> 'natureza_parcela'), ''));\n"
           "                if v_amb_res = 'PARCELADA' then\n"
           "                    v_parc := v_amb_parc;\n"
           "                    v_total := v_amb_total;\n"
           "                elsif v_amb_res is distinct from 'AVISTA' then\n"
           "                    v_amb_res := null;\n"
           "                end if;\n"
           "            end if;\n"
           "        end if;\n")

# Precedencia Parcelada -> Fixa: a parcela nao e reconhecida como recorrencia, nem escolhida como uma
t = trocar(t, "        if v_tipo <> 'credito' and btrim(v_texto) <> '' then\n",
           f"        if v_tipo <> 'credito' and btrim(v_texto) <> '' and v_total <= 1 then  -- {MARCA}: parcela nao e despesa fixa\n")
t = trocar(t, "            if v_escolha = 0 then\n                v_cands := '[]'::jsonb;\n            else\n",
           "            if v_escolha = 0 or v_total > 1 then\n"
           "                v_cands := '[]'::jsonb;\n"
           f"                -- {MARCA}: parcela de compra parcelada nao vira despesa fixa (Parcelada antes de Fixa)\n"
           "                if v_escolha <> 0 then\n"
           "                    v_status := 'revisar';\n"
           "                    v_msgs := v_msgs || '\"Parcela de compra parcelada nao e despesa fixa: retire a recorrencia escolhida.\"'::jsonb;\n"
           "                end if;\n"
           "            else\n")

t = trocar(t, "            if v_valor >= 100000000 then\n",
           f"            -- {MARCA}: parcela possivel no texto, sem a decisao do usuario\n"
           "            if v_amb is not null and v_amb_res is null then\n"
           "                v_status := 'revisar';\n"
           "                v_msgs := v_msgs || to_jsonb(format('Possivel parcela %s no texto, fora do padrao do arquivo: confirme se e compra parcelada (%s) ou a vista.',\n"
           "                    v_amb ->> 'rotulo', v_amb ->> 'rotulo'));\n"
           "            end if;\n"
           "            if v_valor >= 100000000 then\n")

# Parcela ja gravada: pela identidade (inclusive a decidida numa importacao anterior) e sem a regra de 5 dias
t = trocar(t, "                   and l.numero_parcela = v_parc and l.total_parcelas = v_total\n",
           "                   and ((l.numero_parcela = v_parc and l.total_parcelas = v_total)\n"
           f"                        -- {MARCA}: ja gravada como a parcela do texto (decidida numa importacao anterior)\n"
           "                        or (v_amb is not null and v_amb_res is null\n"
           "                            and l.numero_parcela = v_amb_parc and l.total_parcelas = v_amb_total))\n")
t = trocar(t, "                if v_existente is not null then\n                    v_dup := 'banco';\n",
           "                if v_existente is not null then\n                    v_dup := 'banco';\n"
           "                    select l.numero_parcela, l.total_parcelas into v_parc, v_total\n"
           "                      from public.lancamento_agregado l where l.id = v_existente;\n")
t = trocar(t, "                   and abs(l.data_compra - v_data) <= 5\n",
           f"                   -- {MARCA}: a parcela (da 2a em diante) nao traz a data da compra (o Nubank usa o inicio do\n"
           "                   -- ciclo da fatura): a mesma parcela N/M, com o mesmo valor, na mesma fatura, e a parcela ja lancada\n"
           "                   and (abs(l.data_compra - v_data) <= 5 or v_total > 1)\n")
t = trocar(t, "                 order by abs(l.data_compra - v_data), l.id\n",
           "                 order by (lower(coalesce(l.descricao_original_normalizada, l.descricao)) = lower(v_norm)) desc,\n"
           "                          abs(l.data_compra - v_data), l.id\n")

# Parcela nao precisa de Categoria do Cartao (nao consome limite) e fica classificada com a Categoria de Despesa
t = trocar(t, "            elsif v_rec is null then  -- FIN-CARTAO-DESPESAS-FIXAS-01: recorrencia nao precisa de Categoria do Cartao\n",
           "            elsif v_rec is null and v_total <= 1 then  -- FIN-CARTAO-DESPESAS-FIXAS-01: recorrencia nao precisa de Categoria do Cartao\n"
           f"                                                      -- (nem a parcela: {MARCA})\n")
t = trocar(t, "            when v_rec is not null then 'classificada'\n",
           "            when v_rec is not null or v_total > 1 then 'classificada'\n")

# A categoria pendente nao esconde a natureza; Parcelada antes de Fixa
t = trocar(t, "            when v_status = 'revisar' then 'REVISAR'\n            when v_rec is not null then 'DESPESA_FIXA'\n"
              "            when v_total > 1 then 'PARCELADA'\n",
           f"            -- {MARCA}: a categoria pendente nao esconde a natureza (Parcelada antes de Fixa)\n"
           "            when v_status = 'revisar' and v_rev_nat then 'REVISAR'\n"
           "            when v_total > 1 then 'PARCELADA'\n"
           "            when v_rec is not null then 'DESPESA_FIXA'\n")
t = trocar(t, "            'manter_duplicada', coalesce((v_l ->> 'manter_duplicada')::boolean, false)));\n",
           "            'manter_duplicada', coalesce((v_l ->> 'manter_duplicada')::boolean, false))\n"
           f"            -- {MARCA}\n"
           "            || jsonb_build_object(\n"
           "            'parcela_ambigua', v_amb,\n"
           "            'natureza_parcela', v_amb_res,\n"
           "            'categoria_pendente', v_tipo <> 'credito' and v_cat is null));\n")
t = trocar(t, "            'despesas_fixas', count(*) filter (where l ->> 'classificacao_importacao' = 'DESPESA_FIXA'),\n",
           "            'despesas_fixas', count(*) filter (where l ->> 'classificacao_importacao' = 'DESPESA_FIXA'),\n"
           "            'parceladas', count(*) filter (where l ->> 'classificacao_importacao' = 'PARCELADA'),\n"
           "            'parcelas_ambiguas', count(*) filter (where jsonb_typeof(l -> 'parcela_ambigua') = 'object'\n"
           "                                                      and l ->> 'natureza_parcela' is null),\n")

# Toda revisao marca a natureza, exceto a da Categoria de Despesa pendente
n_revisar = len(re.findall(r"^[ \t]*v_status := 'revisar';$", t, flags=re.M))
t = re.sub(r"^([ \t]*)v_status := 'revisar';$", r"\1v_status := 'revisar';\n\1v_rev_nat := true;", t, flags=re.M)
t = trocar(t, "            if v_cat is null and v_status = 'valido' then\n                v_status := 'revisar';\n                v_rev_nat := true;\n",
           "            if v_cat is null and v_status = 'valido' then\n                v_status := 'revisar';\n")
assert n_revisar == 14, n_revisar
NOVO = t

CABECALHO = f"""-- {MARCA} — compras parceladas na importacao da fatura (Nubank e demais arquivos).
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes {VERSAO}). Depende de 20261210090000.
-- Validada em cluster local descartavel (tests/test_supabase_cartao_nubank_parceladas.py) e ensaiada numa copia fiel da
-- producao. Doc: docs/FIN_CARTAO_NUBANK_PARCELADAS_01.md. Gerada por scripts/gerar_migration_cartao_nubank_parceladas.py.
-- Reversao: supabase/reversao/{VERSAO}_cartao_nubank_parceladas_anterior.sql.
--
-- Na previa (analisar_importacao_cartao, so leitura):
-- - a parcela ja lancada (manual, gerada por parcelamento ou importada) e reconhecida pela mesma parcela N/M, com o mesmo
--   valor, na mesma fatura, sem a regra de 5 dias entre as datas: o Nubank data a parcela (da 2a em diante) pelo inicio
--   do ciclo da fatura, nao pela compra. Entre duas candidatas, a de mesma descricao;
-- - Parcelada antes de Fixa: a parcela nao e reconhecida como recorrencia (nem pode ser escolhida como uma);
-- - a Categoria de Despesa pendente nao esconde a natureza: a linha continua PARCELADA / COMPRA / DESPESA_FIXA e diz
--   categoria_pendente; REVISAR fica para a duvida sobre a propria linha;
-- - numero no texto fora do padrao do arquivo (parcela_ambigua, enviada pelo leitor do arquivo): REVISAR ate o usuario
--   decidir natureza_parcela (PARCELADA, com esse numero, ou AVISTA). Nada e inventado;
-- - a parcela nao pede Categoria do Cartao (nao consome limite de categoria).
-- A confirmacao (importar_fatura_cartao) nao muda: grava o que a analise refeita sob as travas classifica. Nenhum dado
-- existente e alterado pela migration.
--
-- Funcao existente substituida pelo texto vigente com os trechos marcados "{MARCA}": analisar_importacao_cartao
-- (texto de 20261210090000).
"""


def como_replace(b):
    return re.sub(r'^create function', 'create or replace function', b)


destino = MIG / f'{VERSAO}_financeiro_cartao_nubank_parceladas.sql'
REVERSAO = RAIZ / 'supabase' / 'reversao' / f'{VERSAO}_cartao_nubank_parceladas_anterior.sql'
SAIDAS = {
    destino: CABECALHO + f"\n-- analisar_importacao_cartao: texto de {FONTE[:14]} + os trechos marcados.\n{como_replace(NOVO)}\n",
    REVERSAO: (f"-- Reversao de {VERSAO} ({MARCA}): volta a previa da importacao ao texto de {FONTE[:14]}. As compras\n"
               "-- gravadas continuam. So com autorizacao, retirando a versao de supabase_migrations.schema_migrations.\n"
               f"\n-- analisar_importacao_cartao: texto de {FONTE[:14]}.\n{como_replace(ORIG)}\n"),
}
if ARGS.verificar:
    # Bytes exatos (UTF-8), sem CR: o checkout no Windows pode trocar LF por CRLF (core.autocrlf).
    diferentes = [str(p.relative_to(RAIZ)) for p, texto in SAIDAS.items()
                  if not p.exists() or p.read_bytes().replace(b'\r\n', b'\n') != texto.encode('utf-8')]
    print('diferente: ' + ', '.join(diferentes) if diferentes else 'igual')
    sys.exit(1 if diferentes else 0)
for caminho, texto in SAIDAS.items():
    caminho.write_text(texto, encoding='utf-8', newline='\n')
print('ok', destino.stat().st_size)
