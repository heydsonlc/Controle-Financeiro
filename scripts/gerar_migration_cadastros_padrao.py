"""Gera a migration 20270101090000 (FIN-CADASTROS-PADRAO-01) e a reversao a partir da definicao VIGENTE das funcoes.

A parte estrutural (categoria com dono, palavras-chave do usuario, modelo de categorias de cartao) e escrita aqui a mao.
Cinco funcoes longas sao reescritas por substituicoes conferidas sobre a definicao vigente, lida de um PostgreSQL local
descartavel com as migrations anteriores aplicadas. Nenhum dado real, conexao remota ou credencial.

    python scripts/gerar_migration_cadastros_padrao.py              # grava a migration e a reversao
    python scripts/gerar_migration_cadastros_padrao.py --verificar  # so compara com os arquivos versionados
"""
import argparse
import re
import sys
import tempfile
from pathlib import Path

_args = argparse.ArgumentParser(description=__doc__.splitlines()[0])
_args.add_argument('--verificar', action='store_true', help='nao grava: falha se a saida difere dos arquivos versionados')
ARGS = _args.parse_args()
RAIZ = Path(__file__).resolve().parents[1]
MIG = RAIZ / 'supabase' / 'migrations'
VERSAO = '20270101090000'
SAIDA = MIG / f'{VERSAO}_financeiro_cadastros_padrao.sql'
REVERSAO = RAIZ / 'supabase' / 'reversao' / f'{VERSAO}_cadastros_padrao_anterior.sql'
ANTERIORES = sorted(p for p in MIG.glob('*.sql') if p.name < VERSAO)
# Funcoes que esta migration substitui (a reversao devolve cada uma ao texto anterior).
SUBSTITUIDAS = ['categorias_de_despesa', 'categorias_tela', 'mobilidade_categorias_tela', 'naturezas_das_categorias', 'validar_nome_categoria',
                'criar_categoria', 'editar_categoria', 'excluir_categoria', 'definir_natureza_categoria', 'criar_palavra_chave', 'palavras_chave_tela',
                'sugestao_categoria_importacao', 'ir_categorias_despesa_tela', 'criar_perfil', 'editar_categoria_cartao', 'desativar_categoria_cartao',
                'categorias_cartao_tela']


def carregar():
    sys.path.insert(0, str(RAIZ))
    from tests.supabase_local import ClusterLocal, encontrar_pg_bin
    pg = encontrar_pg_bin()
    assert pg, 'binarios do PostgreSQL nao encontrados'
    with tempfile.TemporaryDirectory(prefix='cf-gerador-', ignore_cleanup_errors=True) as tmp, ClusterLocal(pg, Path(tmp)) as c:
        c.aplicar_shim()
        c.criar_tabelas_legadas()
        conn = c.conectar()
        try:
            with conn.cursor() as cur:
                for migration in ANTERIORES:
                    cur.execute(migration.read_text(encoding='utf-8'))
                cur.execute("""select p.proname, pg_get_functiondef(p.oid) from pg_proc p join pg_namespace n on n.oid = p.pronamespace
                                where n.nspname = 'financeiro' and p.prokind = 'f' order by 1""")
                linhas = cur.fetchall()
                cur.execute("""select 'alter table public.categoria add constraint ' || quote_ident(c.conname) || ' ' || pg_get_constraintdef(c.oid) || ';'
                                 from pg_constraint c where c.conrelid = 'public.categoria'::regclass and c.contype = 'u'
                                  and (select array_agg(a.attname::text) from pg_attribute a where a.attrelid = c.conrelid and a.attnum = any(c.conkey)) = array['nome']
                               union all
                               select pg_get_indexdef(i.indexrelid) || ';' from pg_index i
                                where i.indrelid = 'public.categoria'::regclass and i.indisunique and not i.indisprimary and i.indnatts = 1
                                  and (select a.attname from pg_attribute a where a.attrelid = i.indrelid and a.attnum = i.indkey[0]) = 'nome'
                                  and not exists (select 1 from pg_constraint c where c.conindid = i.indexrelid)""")
                unicidade = [r[0] for r in cur.fetchall()]
        finally:
            conn.close()
    defs = {}
    for nome, texto in linhas:
        defs.setdefault(nome, []).append(texto.replace('\r\n', '\n').rstrip() + ';')
    return defs, unicidade


VIGENTES, UNICIDADE = carregar()


def vigente(nome):
    assert len(VIGENTES.get(nome, [])) == 1, f'{nome}: {len(VIGENTES.get(nome, []))} definicoes'
    return VIGENTES[nome][0]


def trocar(texto, padrao, novo, nome, vezes=1):
    saida, n = re.subn(padrao, novo, texto)
    assert n == vezes, f'{nome}: trecho encontrado {n} vez(es), esperado {vezes}: {padrao[:70]!r}'
    return saida


gerado = []

# sugestao da importacao: as palavras-chave EFETIVAS do dono do perfil (padrao - o que ele desligou/reassociou + as dele)
s = vigente('sugestao_categoria_importacao')
s = trocar(s, r"from public\.categoria_palavra_chave pk\s+join public\.categoria c on c\.id = pk\.categoria_id and coalesce\(c\.ativo, true\)\s+where pk\.ativo and btrim\(pk\.palavra\) <> ''",
           "from financeiro.palavras_efetivas(financeiro.dono_do_perfil(p_perfil_id)) pk\n"
           "                  join public.categoria c on c.id = pk.categoria_id and coalesce(c.ativo, true)\n"
           "                 where btrim(pk.palavra) <> ''", 'sugestao_categoria_importacao')
s = trocar(s, r"array_agg\(lower\(btrim\(pk\.palavra\)\) order by pk\.id\)", "array_agg(lower(btrim(pk.palavra)) order by pk.ordem)", 'sugestao_categoria_importacao')
gerado.append('-- sugestao_categoria_importacao: definicao vigente + palavras-chave efetivas do dono do perfil (2 trechos).\n' + s)

# categorias disponiveis na tela fiscal: o catalogo visivel ao dono do perfil (nao mais "sem perfil = do perfil da guarda")
s = vigente('ir_categorias_despesa_tela')
s = trocar(s, r"financeiro\.pertence_ao_perfil\(c\.perfil_financeiro_id, p_perfil_id\)", "financeiro.categoria_visivel(c.user_id, p_perfil_id)", 'ir_categorias_despesa_tela')
gerado.append('-- ir_categorias_despesa_tela: definicao vigente + catalogo visivel ao dono do perfil (1 trecho).\n' + s)

# perfil novo ja nasce com as categorias de cartao padrao
s = vigente('criar_perfil')
s = trocar(s, r"('Perfil criado pelo novo aplicativo'\);\n)", r"\1    perform financeiro.inicializar_categorias_cartao(v_id);  -- FIN-CADASTROS-PADRAO-01\n", 'criar_perfil')
gerado.append('-- criar_perfil: definicao vigente + categorias de cartao padrao no perfil novo (1 trecho).\n' + s)

# categorias de cartao padrao: nome e situacao protegidos
PROTECAO = """    if v_c.padrao_id is not null and ({condicao}) then
        raise exception 'Categoria padrao do aplicativo: o nome e a situacao nao podem ser alterados. Nada foi gravado.'
            using errcode = '22023', hint = 'CATEGORIA_PADRAO';
    end if;
"""
s = vigente('editar_categoria_cartao')
s = trocar(s, r"(    v_d := financeiro\.ler_dados_categoria_cartao\(p_perfil_id, p_dados, true, v_c\.id\);\n)",
           lambda m: m.group(1) + PROTECAO.format(condicao="(v_d ? 'nome' and financeiro.nome_de_perfil_normalizado(v_d ->> 'nome') <> financeiro.nome_de_perfil_normalizado(v_c.nome))\n"
                                                           "                                    or (v_d ? 'ativo' and not (v_d ->> 'ativo')::boolean)"), 'editar_categoria_cartao')
gerado.append('-- editar_categoria_cartao: definicao vigente + protecao da categoria padrao (1 trecho).\n' + s)
s = vigente('desativar_categoria_cartao')
s = trocar(s, r"(    v_c := financeiro\.travar_categoria_cartao\(p_perfil_id, p_id\);\n)", lambda m: m.group(1) + PROTECAO.format(condicao='true'), 'desativar_categoria_cartao')
gerado.append('-- desativar_categoria_cartao: definicao vigente + protecao da categoria padrao (1 trecho).\n' + s)

ESTRUTURA = (RAIZ / 'scripts' / 'cadastros_padrao_estrutura.sql').read_text(encoding='utf-8')
texto = ESTRUTURA.rstrip('\n') + """

-- =====================================================================================================================
-- 7. Funcoes longas: definicao vigente com as substituicoes conferidas (nenhuma outra linha muda)
-- =====================================================================================================================
""" + '\n\n'.join(gerado) + '\n'

assert UNICIDADE, 'unicidade global do nome da categoria nao encontrada no estado anterior'
reversao = f"""-- FIN-CADASTROS-PADRAO-01 — reversao da migration {VERSAO}.
--
-- GERADA por scripts/gerar_migration_cadastros_padrao.py: nao editar a mao.
-- NAO aplicar no Supabase remoto sem autorizacao especifica. Antes: volte o frontend ao deploy anterior e desfaca os dados
-- pelo roteiro (scripts/cadastros_padrao.py reverter). Recusada enquanto existir personalizacao de usuario que a regra
-- anterior nao sabe representar (categoria particular, palavra-chave do usuario, modelo de categorias de cartao em uso).

do $$
begin
    if exists (select 1 from public.categoria where user_id is not null) then
        raise exception 'Reversao recusada: ha categorias particulares de usuarios. A regra anterior as mostraria a todos.';
    end if;
    if exists (select 1 from financeiro.palavra_chave_usuario) then
        raise exception 'Reversao recusada: ha palavras-chave personalizadas por usuarios. Reverta os dados antes.';
    end if;
    if exists (select 1 from public.categoria_cartao where padrao_id is not null) or exists (select 1 from financeiro.categoria_cartao_padrao) then
        raise exception 'Reversao recusada: o modelo de categorias de cartao esta em uso. Reverta os dados antes.';
    end if;
    if exists (select 1 from public.categoria group by lower(nome) having count(*) > 1) then
        raise exception 'Reversao recusada: ha categorias com o mesmo nome. A regra anterior exige nome unico.';
    end if;
end
$$;

""" + '\n\n'.join(vigente(n) for n in SUBSTITUIDAS) + """

do $$
declare
    r record;
begin
    for r in select t.tgname, c.oid::regclass::text tabela from pg_trigger t join pg_class c on c.oid = t.tgrelid
              where t.tgname like 'categoria_do_dono_%' and not t.tgisinternal loop
        execute format('drop trigger %I on %s', r.tgname, r.tabela);
    end loop;
end
$$;
drop function financeiro.conferir_categoria_do_dono();
drop function financeiro.propagar_categorias_cartao_padrao();
drop function financeiro.manter_categoria_cartao_padrao(jsonb);
drop function financeiro.categorias_cartao_padrao_tela();
drop function financeiro.inicializar_categorias_cartao_do_perfil(integer);
drop function financeiro.inicializar_categorias_cartao(integer);
drop index public.categoria_cartao_padrao_por_perfil_uq;
alter table public.categoria_cartao drop column padrao_id;
drop table financeiro.categoria_cartao_padrao_despesa;
drop table financeiro.categoria_cartao_padrao;
drop function financeiro.restaurar_palavra_chave_padrao(integer);
drop function financeiro.remover_minha_palavra_chave(bigint);
drop function financeiro.reassociar_palavra_chave_padrao(integer, integer);
drop function financeiro.desligar_palavra_chave_padrao(integer);
drop function financeiro.criar_minha_palavra_chave(integer, text);
drop function financeiro.palavras_efetivas(uuid);
drop table financeiro.palavra_chave_usuario;
drop function financeiro.exigir_alteracao_da_categoria(integer);
drop function financeiro.categoria_do_usuario(integer, uuid);
drop function financeiro.categoria_visivel(uuid, integer);
drop function financeiro.dono_do_perfil(integer);
drop function financeiro.exigir_catalogo_no_novo();
drop function financeiro.e_administrador_plataforma();
drop index public.categoria_particular_nome_uq;
drop index public.categoria_padrao_nome_uq;
drop index public.categoria_dono_idx;
alter table public.categoria drop column user_id;
""" + '\n'.join(UNICIDADE) + '\n'

if ARGS.verificar:
    ok = (SAIDA.exists() and SAIDA.read_text(encoding='utf-8') == texto and REVERSAO.exists() and REVERSAO.read_text(encoding='utf-8') == reversao)
    print('igual aos arquivos versionados' if ok else 'DIFERENTE dos arquivos versionados: rode o gerador sem --verificar.')
    sys.exit(0 if ok else 1)
SAIDA.write_text(texto, encoding='utf-8', newline='\n')
REVERSAO.write_text(reversao, encoding='utf-8', newline='\n')
print(f'{SAIDA.name}: {len(texto.splitlines())} linhas | {REVERSAO.name}: {len(reversao.splitlines())} linhas; {len(SUBSTITUIDAS)} funcoes devolvidas')
