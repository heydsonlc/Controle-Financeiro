"""FIN-CADASTROS-PADRAO-01 — ensaio completo numa copia fiel da producao, em PostgreSQL DESCARTAVEL local.

    python scripts/ensaio_cadastros_padrao.py --saida <pasta privada> --pessoais <arquivo.json> [--backup-id ID]

--pessoais: lista de palavras-chave (texto) propostas como pessoais do titular: ["palavra", ...]. O ensaio as localiza no
catalogo e monta o manifesto. Restaura o backup guardado num cluster local criado e destruido aqui e ensaia, medindo:
  0. a etapa anterior (FIN-MULTIUSUARIO-SEGURANCA-01: migration e regularizacao dos itens sem perfil), que e pre-requisito;
  1. a migration 20270101090000: nenhum dado muda; telas e sugestoes de categoria do titular identicas;
  2. a carga inicial (scripts/cadastros_padrao.py): modelo de categorias de cartao a partir das atuais, preenchimento do
     outro perfil, palavras-chave pessoais fora do catalogo padrao e mantidas para o titular;
  3. a reversao completa (carga e migration), comparada com o estado de antes;
  4. de novo migration e carga; retirada da guarda dos registros sem perfil (agora possivel);
  5. um SEGUNDO USUARIO ficticio: recebe o catalogo padrao e as categorias de cartao, nao recebe as palavras pessoais, cria
     categoria e palavra proprias; nada disso aparece para o titular.
O relatorio vai SO para a pasta privada indicada. Nada e impresso alem do resumo.
"""
import argparse
import datetime as dt
import json
import os
import sys
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / 'scripts'))

import psycopg2  # noqa: E402
import psycopg2.extras  # noqa: E402

import backup_banco as B  # noqa: E402
import backup_rotina as R  # noqa: E402
import cadastros_padrao as CP  # noqa: E402
import ensaio_multiusuario_seguranca as E1  # noqa: E402
import regularizar_itens_sem_perfil as REG  # noqa: E402
from tests.supabase_local import ClusterLocal  # noqa: E402

MIG_SEG = RAIZ / 'supabase' / 'migrations' / '20261231090000_financeiro_multiusuario_seguranca.sql'
MIGRATION = RAIZ / 'supabase' / 'migrations' / '20270101090000_financeiro_cadastros_padrao.sql'
REVERSAO = RAIZ / 'supabase' / 'reversao' / '20270101090000_cadastros_padrao_anterior.sql'
REFERENCIA = 1
NOVAS_ESTRUTURAS = {'financeiro.palavra_chave_usuario', 'financeiro.categoria_cartao_padrao', 'financeiro.categoria_cartao_padrao_despesa'}
NOVAS_FUNCOES = {'categorias_cartao_padrao_tela'}
# Campos que a migration ACRESCENTA as respostas das telas (o restante tem de ser identico).
ACRESCIMOS = {'padrao', 'natureza', 'origem', 'created_at', 'updated_at'}
IGNORA = {'public.perfil_financeiro': ['user_id'], 'public.categoria': ['user_id'], 'public.categoria_cartao': ['padrao_id']}
consulta, diferencas, como = E1.consulta, E1.diferencas, E1.como


def sem_acrescimos(x):
    if isinstance(x, dict):
        return {k: sem_acrescimos(v) for k, v in x.items() if k not in ACRESCIMOS}
    if isinstance(x, list):
        return [sem_acrescimos(v) for v in x]
    return x


def leituras(conn, usuario, perfis):
    E1.NOVAS_FUNCOES.update(NOVAS_FUNCOES)
    saida = {}
    for k, v in E1.leituras(conn, usuario, perfis).items():
        v = sem_acrescimos(v)
        if k.startswith('palavras_chave_tela(') and isinstance(v, list) and v and isinstance(v[0], dict):
            # o que importa e a REGRA (categoria, palavra) em vigor: a palavra que passa do catalogo padrao para o usuario
            # muda de identificador, nao de efeito
            v = sorted((int(cat), p['palavra']) for cat, lista in v[0].items() for p in lista if p.get('ativo', True))
        saida[k] = v
    return saida


# Mudancas ESPERADAS nas telas dos outros perfis do titular (nao o de referencia), e por que:
#  - ir_categorias_despesa_tela: o catalogo de categorias aparecia so no perfil que guardava os registros sem perfil; agora e
#    do aplicativo e aparece em todos os perfis;
#  - categorias de cartao e vinculos: o perfil recebeu as categorias de cartao padrao na carga inicial.
def esperada(chave, referencia, com_cartao):
    nome, args = chave.split('(', 1)
    perfil = args.split(',')[0].rstrip(')').strip()
    if perfil == str(referencia):
        return False
    return nome == 'ir_categorias_despesa_tela' or (com_cartao and nome in ('categorias_cartao_tela', 'categoria_cartao_despesas_tela', 'categorias_cartao_do_perfil'))


def retrato(cur):
    E1.NOVAS_ESTRUTURAS.update(NOVAS_ESTRUTURAS)
    return E1.retrato(cur, IGNORA)


def sugestoes(cur, perfis):
    """A sugestao de categoria de cada descricao de compra ja importada, em cada perfil (o que a importacao sugeriria hoje)."""
    descricoes = [r['d'] for r in consulta(cur, "select distinct lower(coalesce(descricao_original_normalizada, descricao)) d from public.lancamento_agregado "
                                                "where coalesce(descricao_original_normalizada, descricao) is not null order by 1")]
    return {f'{p}|{d}': consulta(cur, 'select financeiro.sugestao_categoria_importacao(%s, %s, %s, null) s', (p, d, d))[0]['s'] for p in perfis for d in descricoes}


def cartao(cur, perfil):
    return {'categorias': consulta(cur, 'select id, nome, descricao, cor, icone, ativo from public.categoria_cartao where perfil_financeiro_id = %s order by id', (perfil,)),
            'vinculos': consulta(cur, 'select id, categoria_cartao_id, categoria_id, ativo from public.categoria_cartao_despesa where perfil_financeiro_id = %s order by id', (perfil,)),
            'limites': consulta(cur, 'select id, cartao_id, categoria_cartao_id, ativo from public.cartao_categoria_limite where perfil_financeiro_id = %s order by id', (perfil,))}


def ensaiar(saida, pessoais_texto, backup_id=None, depois=None):
    # depois: continuacao opcional sobre o mesmo banco descartavel (o ensaio da etapa seguinte parte do estado final deste)
    cfg = R.configuracao()
    ficha = R._escolher(cfg, backup_id)
    pasta = R._pasta_temporaria(cfg, 'ensaio-cadastros')
    rel = {'data_hora': dt.datetime.now().isoformat(timespec='seconds'), 'backup_id': ficha['backup_id'], 'verificacoes': [], 'falhas': []}

    def conferir(nome, ok, detalhe=''):
        rel['verificacoes'].append({'verificacao': nome, 'resultado': 'ok' if ok else 'FALHA', 'detalhe': str(detalhe)[:400]})
        if not ok:
            rel['falhas'].append(nome)

    anteriores = {k: os.environ.get(k) for k in ('CF_BACKUP_ROTINA_ENSAIO', 'CF_PG_BIN_BACKUP')}
    try:
        caminho, _ = R._extrair(cfg, ficha, pasta / 'bk')
        os.environ['CF_PG_BIN_BACKUP'] = cfg['pg_bin']
        with ClusterLocal(cfg['pg_bin'], pasta / 'pg') as destino:
            dsn = destino.dsn()
            if psycopg2.extensions.parse_dsn(dsn).get('host') != '127.0.0.1' or B._destino_supabase(dsn):
                raise SystemExit('o destino do ensaio nao e um banco local descartavel')
            destino.aplicar_shim()
            conn = psycopg2.connect(dsn)
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute('drop table auth.users')
                cur.execute("do $$ begin if not exists (select 1 from pg_roles where rolname = 'supabase_admin') then create role supabase_admin; end if; end $$")
            conn.close()
            os.environ['CF_BACKUP_ROTINA_ENSAIO'] = dsn
            restaurado = B.restaurar(argparse.Namespace(manifesto=str(caminho), dsn_env='CF_BACKUP_ROTINA_ENSAIO', confirmar_projeto=None))
            conferir('copia restaurada identica ao backup', str(restaurado.get('homologacao')).startswith('HOMOLOGADO'))
            conn = psycopg2.connect(dsn)
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute('create schema if not exists extensions')
                cur.execute('create extension if not exists "uuid-ossp" with schema extensions')
            conn.close()

            def abrir():
                c = psycopg2.connect(dsn)
                return c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # ------------------------------------------------------------ 0. etapa anterior (pre-requisito)
            conn, cur = abrir()
            rel['migrations_antes'] = consulta(cur, 'select count(*) n from supabase_migrations.schema_migrations')[0]['n']
            cur.execute(MIG_SEG.read_text(encoding='utf-8'))
            conn.commit()
            e = REG.estado(cur, REFERENCIA)
            conn.rollback()
            conn.close()
            REG.main(['executar', '--perfil', str(REFERENCIA), '--hash', e['impressao'], '--confirmo', 'REGULARIZAR ITENS', '--dsn', dsn, '--por', 'ensaio',
                      '--saida', str(pasta / 'regularizacao.json')])
            conn, cur = abrir()
            titular = consulta(cur, 'select user_id::text u from public.perfil_financeiro where id = %s', (REFERENCIA,))[0]['u']
            perfis = [r['id'] for r in consulta(cur, 'select id from public.perfil_financeiro order by id')]
            conn.rollback()
            base = {'retrato': retrato(cur), 'sugestoes': sugestoes(cur, perfis), 'cartao': {p: cartao(cur, p) for p in perfis},
                    'catalogo': consulta(cur, """select (select count(*) from public.categoria) categorias,
                                                        (select count(*) from public.categoria_palavra_chave where ativo) palavras_ativas""")[0]}
            conn.rollback()
            base['leituras'] = leituras(conn, titular, perfis)
            rel['base'] = {'leituras': len(base['leituras']), 'descricoes_com_sugestao_medida': len(base['sugestoes']), **base['catalogo'],
                           'categorias_de_cartao': {p: len(base['cartao'][p]['categorias']) for p in perfis}}

            def aplicar():
                cur.execute(MIGRATION.read_text(encoding='utf-8'))
                conn.commit()

            # ------------------------------------------------------------ 1. migration
            aplicar()
            m1 = retrato(cur)
            conn.rollback()
            conferir('migration: nenhuma tabela de dados muda (fora as duas colunas novas)', diferencas(base['retrato'], m1) == [], diferencas(base['retrato'], m1))
            s1 = sugestoes(cur, perfis)
            conn.rollback()
            conferir('migration: sugestoes de categoria da importacao identicas (todas as descricoes, todos os perfis)', s1 == base['sugestoes'],
                     [k for k in s1 if s1[k] != base['sugestoes'].get(k)][:5])
            l1 = leituras(conn, titular, perfis)
            dif1 = diferencas(base['leituras'], l1)
            rel['leituras_que_mudam_com_a_migration'] = dif1
            conferir('migration: leituras de tela do titular identicas (fora os campos acrescentados e o catalogo, que passa a aparecer na tela fiscal dos outros perfis)',
                     all(esperada(d, REFERENCIA, False) for d in dif1), [d for d in dif1 if not esperada(d, REFERENCIA, False)][:8])
            conferir('migration: no perfil de referencia, TODAS as leituras identicas', not [d for d in dif1 if f'({REFERENCIA},' in d or d.endswith(f'({REFERENCIA})')])
            conferir('todas as categorias atuais sao padrao (nenhuma particular)', consulta(
                cur, 'select count(*) filter (where user_id is null) p, count(*) filter (where user_id is not null) u from public.categoria')[0] == {
                    'p': base['catalogo']['categorias'], 'u': 0})
            rede = consulta(cur, """select (select count(*) from pg_trigger t where t.tgname like 'categoria_do_dono_%%' and not t.tgisinternal) gatilhos,
                                           (select count(*) from pg_constraint k join pg_class t on t.oid = k.conrelid join pg_namespace n on n.oid = t.relnamespace
                                             where k.contype = 'f' and k.confrelid = 'public.categoria'::regclass and cardinality(k.conkey) = 1
                                               and n.nspname in ('public', 'financeiro')) colunas""")[0]
            rel['rede_de_protecao'] = rede
            conferir('rede de protecao instalada em TODA coluna que aponta para a categoria', rede['gatilhos'] == rede['colunas'] >= 19, rede)
            conn.rollback()

            # ------------------------------------------------------------ 2. carga inicial
            achadas = consulta(cur, """select p.categoria_id, lower(btrim(p.palavra)) palavra, c.nome categoria from public.categoria_palavra_chave p
                                         join public.categoria c on c.id = p.categoria_id where p.ativo and lower(btrim(p.palavra)) = any(%s) order by 3, 2""",
                               ([' '.join(x.lower().split()) for x in pessoais_texto],))
            conn.rollback()
            rel['palavras_pessoais'] = {'propostas': len(pessoais_texto), 'encontradas_no_catalogo': len(achadas),
                                        'nao_encontradas': sorted(set(' '.join(x.lower().split()) for x in pessoais_texto) - {a['palavra'] for a in achadas})}
            manifesto = pasta / 'pessoais.json'
            manifesto.write_text(json.dumps([{'categoria_id': a['categoria_id'], 'palavra': a['palavra']} for a in achadas]), encoding='utf-8')
            comum = ['--perfil-referencia', str(REFERENCIA), '--pessoais', str(manifesto), '--preencher-perfis', '--dsn', dsn]
            ep = CP.estado(cur, REFERENCIA, CP.ler_pessoais(str(manifesto)), True)
            conn.rollback()
            rel['previa'] = {'impressao': ep['impressao'], **ep['resumo']}
            conn.close()
            feito_arq = pasta / 'feito.json'
            CP.main(['executar', *comum, '--hash', ep['impressao'], '--confirmo', 'CADASTROS PADRAO', '--saida', str(feito_arq)])
            conn, cur = abrir()
            n_modelo = len(base['cartao'][REFERENCIA]['categorias'])

            def conferir_carga(rotulo):
                c1 = cartao(cur, REFERENCIA)
                conferir(f'{rotulo}: perfil de referencia com as MESMAS categorias de cartao, vinculos e limites (mesmos ids)', c1 == base['cartao'][REFERENCIA])
                conferir(f'{rotulo}: as categorias de cartao ativas do perfil de referencia ficaram marcadas como padrao', consulta(
                    cur, 'select count(*) n from public.categoria_cartao where perfil_financeiro_id = %s and ativo and padrao_id is null', (REFERENCIA,))[0]['n'] == 0)
                modelo = consulta(cur, 'select (select count(*) from financeiro.categoria_cartao_padrao) m, (select count(*) from financeiro.categoria_cartao_padrao_despesa) v')[0]
                rel['modelo'] = modelo
                conferir(f'{rotulo}: modelo com as categorias de cartao atuais e os vinculos delas', modelo['m'] == n_modelo and modelo['v'] == ep['resumo']['vinculos_no_modelo'], modelo)
                for p in perfis:
                    if p == REFERENCIA:
                        continue
                    cp = cartao(cur, p)
                    conferir(f'{rotulo}: perfil {p} recebeu as categorias de cartao padrao, uma de cada, com os vinculos',
                             len(cp['categorias']) == len(base['cartao'][p]['categorias']) + n_modelo
                             and len(cp['vinculos']) == len(base['cartao'][p]['vinculos']) + modelo['v'], (len(cp['categorias']), len(cp['vinculos'])))
                s2 = sugestoes(cur, perfis)
                conferir(f'{rotulo}: sugestoes de categoria do titular identicas, em todos os perfis (palavras pessoais continuam valendo para ele)',
                         s2 == base['sugestoes'], [k for k in s2 if s2[k] != base['sugestoes'].get(k)][:5])
                cat = consulta(cur, """select (select count(*) from public.categoria_palavra_chave where ativo) padrao_ativas,
                                              (select count(*) from financeiro.palavra_chave_usuario where user_id = %s and tipo = 'NOVA') do_titular,
                                              (select count(*) from financeiro.palavras_efetivas(%s)) efetivas_do_titular""", (titular, titular))[0]
                rel['palavras_depois'] = cat
                conferir(f'{rotulo}: palavras pessoais sairam do catalogo padrao e a regra efetiva do titular tem o mesmo tamanho',
                         cat['padrao_ativas'] == base['catalogo']['palavras_ativas'] - len(achadas) and cat['do_titular'] == len(achadas)
                         and cat['efetivas_do_titular'] == base['catalogo']['palavras_ativas'], cat)
                r2 = retrato(cur)
                mudaram = diferencas(base['retrato'], r2)
                conn.rollback()
                rel['tabelas_que_mudaram_na_carga'] = mudaram
                conferir(f'{rotulo}: so mudam catalogo de palavras, categorias de cartao e vinculos (e a auditoria)',
                         set(mudaram) <= {'public.categoria_palavra_chave', 'public.categoria_cartao', 'public.categoria_cartao_despesa', 'financeiro.operacao_catalogo'}, mudaram)
                l2 = leituras(conn, titular, perfis)
                dif = diferencas(base['leituras'], l2)
                rel['leituras_que_mudaram_na_carga'] = dif
                conferir(f'{rotulo}: leituras do titular identicas, fora o que o outro perfil ganhou (catalogo na tela fiscal e categorias de cartao padrao)',
                         all(esperada(d, REFERENCIA, True) for d in dif), [d for d in dif if not esperada(d, REFERENCIA, True)][:8])
                conferir(f'{rotulo}: leituras do perfil de referencia todas identicas', not [d for d in dif if f'({REFERENCIA},' in d or d.endswith(f'({REFERENCIA})')],
                         [d for d in dif if f'({REFERENCIA},' in d or d.endswith(f'({REFERENCIA})')][:6])

            conferir_carga('carga')
            conn.close()
            conferir('repetir a carga inicial e recusado', E1._recusa(lambda: CP.main(['executar', *comum, '--hash', ep['impressao'], '--confirmo', 'CADASTROS PADRAO'])))

            # ------------------------------------------------------------ 3. reversao completa
            CP.main(['reverter', '--feito', str(feito_arq), '--confirmo', 'REVERTER CADASTROS', '--dsn', dsn])
            conn, cur = abrir()
            rv = retrato(cur)
            conn.rollback()
            mud = diferencas(base['retrato'], rv)
            conferir('reversao da carga: banco identico ao de antes (fora a auditoria e a hora de atualizacao das palavras)',
                     set(mud) <= {'financeiro.operacao_catalogo', 'public.categoria_palavra_chave'}, mud)
            conferir('reversao da carga: palavras-chave padrao todas ativas de novo, mesmas categorias de cartao', consulta(
                cur, 'select count(*) n from public.categoria_palavra_chave where ativo')[0]['n'] == base['catalogo']['palavras_ativas']
                and all(cartao(cur, p) == base['cartao'][p] for p in perfis))
            cur.execute(REVERSAO.read_text(encoding='utf-8'))
            conn.commit()
            E1.NOVAS_ESTRUTURAS.difference_update(NOVAS_ESTRUTURAS)
            rf = E1.retrato(cur, {'public.perfil_financeiro': ['user_id']})
            conn.rollback()
            base_sem_colunas = dict(base['retrato'])  # a base foi medida ja com as colunas ignoradas: mesma conta
            mud = [t for t in diferencas(base_sem_colunas, rf) if t not in ('financeiro.operacao_catalogo', 'public.categoria_palavra_chave')]
            conferir('reversao da migration: banco identico ao de antes dela', mud == [], mud)
            E1.NOVAS_ESTRUTURAS.update(NOVAS_ESTRUTURAS)
            conferir('reversao da migration: sugestoes identicas', sugestoes(cur, perfis) == base['sugestoes'])
            conn.rollback()
            conferir('reversao da migration: estrutura retirada', consulta(cur, """select
                (select count(*) from information_schema.columns where table_schema = 'public' and table_name in ('categoria', 'categoria_cartao') and column_name in ('user_id', 'padrao_id'))
              + (select count(*) from pg_tables where schemaname = 'financeiro' and tablename in ('palavra_chave_usuario', 'categoria_cartao_padrao'))
              + (select count(*) from pg_trigger where tgname like 'categoria_do_dono_%%') n""")[0]['n'] == 0)
            conn.rollback()

            # ------------------------------------------------------------ 4. de novo; a guarda sai
            aplicar()
            ep2 = CP.estado(cur, REFERENCIA, CP.ler_pessoais(str(manifesto)), True)
            conn.rollback()
            conferir('reaplicada a migration, a previa da carga da a mesma impressao', ep2['impressao'] == ep['impressao'])
            conn.close()
            CP.main(['executar', *comum, '--hash', ep2['impressao'], '--confirmo', 'CADASTROS PADRAO', '--saida', str(feito_arq)])
            conn, cur = abrir()
            conferir_carga('carga refeita')
            l_antes = leituras(conn, titular, perfis)
            conn.close()
            REG.main(['retirar-guarda', '--confirmo', 'RETIRAR GUARDA', '--dsn', dsn, '--por', 'ensaio'])
            conn, cur = abrir()
            conferir('guarda dos registros sem perfil retirada (o catalogo nao depende mais dela)',
                     consulta(cur, 'select perfil_financeiro_id p from financeiro.guarda_sem_perfil')[0]['p'] is None)
            conn.rollback()
            l_sem = leituras(conn, titular, perfis)
            conferir('sem a guarda: TODAS as leituras de tela do titular identicas', diferencas(l_antes, l_sem) == [], diferencas(l_antes, l_sem)[:8])
            conferir('sem a guarda: sugestoes identicas', sugestoes(cur, perfis) == base['sugestoes'])
            conn.rollback()

            # ------------------------------------------------------------ 5. segundo usuario
            outro = str(uuid.uuid4())
            cur.execute("insert into auth.users (id, email) values (%s, 'segundo.usuario@teste.local')", (outro,))
            conn.commit()
            como(cur, outro)
            cur.execute('select financeiro.criar_perfil(%s::jsonb) j', (json.dumps({'nome': 'Pessoal'}),))
            novo = cur.fetchone()['j']['id']
            conn.commit()
            conferir('segundo usuario: o perfil novo ja nasce com as categorias de cartao padrao e os vinculos',
                     len(cartao(cur, novo)['categorias']) == n_modelo and len(cartao(cur, novo)['vinculos']) == rel['modelo']['v'])
            como(cur, outro)
            cur.execute("select coalesce(json_agg(x), '[]'::json) j from financeiro.categorias_de_despesa() x")
            vistas = cur.fetchone()['j']
            conn.rollback()
            conferir('segundo usuario: ve o catalogo padrao inteiro (categorias ativas)', len(vistas) == consulta(
                cur, 'select count(*) n from public.categoria where coalesce(ativo, true) and user_id is null')[0]['n'], len(vistas))
            ef = consulta(cur, 'select count(*) n, count(*) filter (where palavra = any(%s)) pessoais from financeiro.palavras_efetivas(%s)', ([a['palavra'] for a in achadas], outro))[0]
            conferir('segundo usuario: recebe as palavras-chave padrao e NENHUMA das pessoais do titular',
                     ef == {'n': base['catalogo']['palavras_ativas'] - len(achadas), 'pessoais': 0}, ef)
            uma_padrao = consulta(cur, 'select id from public.categoria_palavra_chave where ativo order by id limit 1')[0]['id']
            conn.rollback()
            como(cur, outro)
            cur.execute('select financeiro.criar_categoria(%s::jsonb, %s) j', (json.dumps({'nome': 'Categoria do segundo usuario', 'natureza': 'CONSUMO'}), str(uuid.uuid4())))
            propria = cur.fetchone()['j']['categoria_id']
            cur.execute('select financeiro.criar_minha_palavra_chave(%s, %s)', (propria, 'palavra do segundo usuario'))
            cur.execute('select financeiro.desligar_palavra_chave_padrao(%s)', (uma_padrao,))
            conn.commit()
            l_fim = leituras(conn, titular, perfis)
            conferir('com o segundo usuario personalizando: TODAS as leituras de tela do titular identicas', diferencas(l_sem, l_fim) == [], diferencas(l_sem, l_fim)[:8])
            conferir('com o segundo usuario personalizando: sugestoes do titular identicas', sugestoes(cur, perfis) == base['sugestoes'])
            conn.rollback()
            como(cur, titular)
            cur.execute("select coalesce(json_agg(x.id), '[]'::json) j from financeiro.categorias_de_despesa() x")
            conferir('a categoria particular do segundo usuario nao aparece para o titular', propria not in cur.fetchone()['j'])
            cur.execute('savepoint x')
            try:
                cur.execute('select financeiro.criar_despesa(%s, %s::jsonb, %s)', (REFERENCIA, json.dumps(
                    {'nome': 'x', 'valor': '1.00', 'categoria_id': propria, 'data_vencimento': '2026-12-10'}), str(uuid.uuid4())))
                usou = 'GRAVOU'
            except psycopg2.Error as erro:
                usou = (erro.diag.message_primary or '')[:60]
            conn.rollback()
            conferir('o titular nao consegue gravar despesa na categoria particular de outro usuario', usou != 'GRAVOU', usou)
            conn.close()
            if depois:
                depois({'dsn': dsn, 'conferir': conferir, 'rel': rel, 'titular': titular, 'perfis': perfis, 'abrir': abrir, 'outro': outro,
                        'perfil_do_outro': novo, 'pasta': pasta})
        rel['banco_descartavel'] = 'removido'
    finally:
        for k, v in anteriores.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        R._apagar_pasta_clara(pasta)
    saida.mkdir(parents=True, exist_ok=True)
    (saida / 'ENSAIO_RESULTADO.json').write_text(json.dumps(rel, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
    return rel


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--saida', required=True, help='pasta privada do relatorio (fora do repositorio)')
    ap.add_argument('--pessoais', required=True, help='JSON com a lista de palavras-chave propostas como pessoais do titular')
    ap.add_argument('--backup-id')
    a = ap.parse_args(argv)
    saida = Path(a.saida).resolve()
    if RAIZ in saida.parents or saida == RAIZ:
        raise SystemExit('A pasta do relatorio tem de ficar FORA do repositorio.')
    rel = ensaiar(saida, json.loads(Path(a.pessoais).read_text(encoding='utf-8')), a.backup_id)
    for v in rel['verificacoes']:
        print(('ok    ' if v['resultado'] == 'ok' else 'FALHA ') + v['verificacao'] + (f" [{v['detalhe']}]" if v['resultado'] != 'ok' and v['detalhe'] else ''))
    print(f"backup {rel['backup_id']} | {len(rel['verificacoes'])} verificacoes | {len(rel['falhas'])} falha(s)")
    return 1 if rel['falhas'] else 0


if __name__ == '__main__':
    sys.exit(main())
