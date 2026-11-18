"""FIN-MULTIUSUARIO-SEGURANCA-01 — ensaio completo numa copia fiel da producao, em PostgreSQL DESCARTAVEL local.

    python scripts/ensaio_multiusuario_seguranca.py --saida <pasta privada> [--backup-id ID]

Restaura o backup guardado (o mais recente, ou o indicado) num cluster local criado e destruido aqui (nunca recebe uma
conexao de fora: nao ha como apontar para o Supabase) e ensaia, medindo a cada passo:
  1. a migration 20261231090000 (dono do perfil, guarda dos registros sem perfil, administrador, funcoes);
  2. a regularizacao dos itens sem perfil (scripts/regularizar_itens_sem_perfil.py): previa e execucao (a guarda fica);
  3. a reversao completa (itens, guarda e migration), comparada com o estado inicial;
  4. de novo a migration e a regularizacao, e entao um SEGUNDO USUARIO ficticio, com perfis de mesmo nome dos do titular:
     ele nao ve nem altera nada do titular, e o cadastro com pagamento imediato do titular continua funcionando.
Medicoes: o retrato (hash) de todas as tabelas e TODAS as leituras de tela do titular (toda funcao de leitura exposta que
so pede perfil e mes), nos dois perfis. O relatorio vai SO para a pasta privada indicada. Nada e impresso alem do resumo.
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
import regularizar_itens_sem_perfil as REG  # noqa: E402
from tests.supabase_local import ClusterLocal  # noqa: E402

MIGRATION = RAIZ / 'supabase' / 'migrations' / '20261231090000_financeiro_multiusuario_seguranca.sql'
REVERSAO = RAIZ / 'supabase' / 'reversao' / '20261231090000_multiusuario_seguranca_anterior.sql'
MESES = ['2026-09', '2026-10', '2026-11', '2026-12', '2027-01']
NOVAS_ESTRUTURAS = {'financeiro.guarda_sem_perfil', 'financeiro.regularizacao_perfil', 'financeiro.administrador_plataforma'}
NOVAS_FUNCOES = {'sou_administrador_plataforma'}
PERFIL_DESTINO = 1
UNICO_NO_NOME = """select count(*) n from pg_index i where i.indrelid = 'public.perfil_financeiro'::regclass and i.indisunique and not i.indisprimary
                     and i.indnatts = 1 and (select a.attname from pg_attribute a where a.attrelid = i.indrelid and a.attnum = i.indkey[0]) = 'nome'"""


def consulta(cur, sql, params=()):
    cur.execute(sql, params)
    return [dict(r) for r in cur.fetchall()]


def retrato(cur, sem_colunas=None):
    """md5 de cada tabela de public, financeiro e auth. sem_colunas: {tabela: [colunas a ignorar]}."""
    sem_colunas = sem_colunas or {}
    saida = {}
    for t in consulta(cur, "select n.nspname esquema, c.relname tabela from pg_class c join pg_namespace n on n.oid = c.relnamespace "
                           "where c.relkind = 'r' and n.nspname in ('public', 'financeiro', 'auth') order by 1, 2"):
        nome = f"{t['esquema']}.{t['tabela']}"
        if nome in NOVAS_ESTRUTURAS:
            continue
        menos = ''.join(f" - '{c}'" for c in sem_colunas.get(nome, []))
        saida[nome] = consulta(cur, f"select md5(coalesce(string_agg(x, '|' order by x), '')) h, count(*) n from "
                                    f"(select (to_jsonb(t){menos})::text x from {t['esquema']}.\"{t['tabela']}\" t) z")[0]
    return saida


def leituras(conn, usuario, perfis):
    """Toda funcao de LEITURA exposta cujos argumentos sao so perfil, mes e opcionais: o que as telas do usuario mostram."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    fs = consulta(cur, """select p.proname nome, p.proargnames nomes, p.pronargs n,
                                 (select array_agg(format_type(t, null) order by o) from unnest(p.proargtypes::oid[]) with ordinality x(t, o)) tipos
                            from pg_proc p join pg_namespace n on n.oid = p.pronamespace
                           where n.nspname = 'financeiro' and p.prokind = 'f' and p.provolatile <> 'v'
                             and has_function_privilege('authenticated', p.oid, 'execute') order by 1""")
    saida = {}
    for f in fs:
        if f['nome'] in NOVAS_FUNCOES:
            continue
        nomes, tipos = (f['nomes'] or [])[:f['n']], f['tipos'] or []
        combinacoes = [{}]
        ok = True
        for n, t in zip(nomes, tipos):
            if n == 'p_perfil_id':
                valores = perfis
            elif t == 'date':
                valores = [m + '-01' for m in MESES]
            elif t == 'text' and ('mes' in n or 'compet' in n or 'periodo' in n):
                valores = MESES
            elif t in ('boolean', 'jsonb', 'json', 'text'):
                valores = [None]
            elif t == 'integer' and n in ('p_id', 'p_ano'):
                valores = [None]
            else:
                ok = False
                break
            combinacoes = [dict(c, **{n: v}) for c in combinacoes for v in valores]
        if not ok:
            continue
        for c in combinacoes:
            marc = ', '.join(f'{n} => %s::{t}' for n, t in zip(nomes, tipos))
            chave = f"{f['nome']}({', '.join(str(c[n]) for n in nomes)})"
            cur.execute('savepoint leitura')
            try:
                cur.execute('set local role authenticated')
                cur.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps({'sub': usuario, 'role': 'authenticated'}),))
                cur.execute(f"select to_jsonb(x) from financeiro.{f['nome']}({marc}) x", [c[n] for n in nomes])
                saida[chave] = json.loads(json.dumps([r['to_jsonb'] for r in cur.fetchall()], default=str))
            except psycopg2.Error as e:
                saida[chave] = f'ERRO {e.pgcode}: {(e.diag.message_primary or "")[:100]}'
            cur.execute('rollback to savepoint leitura')
            cur.execute('reset role')
    conn.rollback()
    return saida


def diferencas(a, b):
    return sorted(t for t in set(a) | set(b) if a.get(t) != b.get(t))


def como(cur, usuario):
    cur.execute('set local role authenticated')
    cur.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps({'sub': usuario, 'role': 'authenticated'}),))


def ensaiar(saida, backup_id=None):
    cfg = R.configuracao()
    ficha = R._escolher(cfg, backup_id)
    pasta = R._pasta_temporaria(cfg, 'ensaio-multiusuario')
    rel = {'data_hora': dt.datetime.now().isoformat(timespec='seconds'), 'backup_id': ficha['backup_id'], 'verificacoes': [], 'falhas': []}

    def conferir(nome, ok, detalhe=''):
        rel['verificacoes'].append({'verificacao': nome, 'resultado': 'ok' if ok else 'FALHA', 'detalhe': str(detalhe)[:300]})
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
            rel['restauracao'] = restaurado.get('homologacao')
            conferir('copia restaurada identica ao backup', str(rel['restauracao']).startswith('HOMOLOGADO'), rel['restauracao'])

            # a copia local nao traz as extensoes do Supabase: a de UUID (usada pelas chaves derivadas) e instalada aqui
            conn = psycopg2.connect(dsn)
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute('create schema if not exists extensions')
                cur.execute('create extension if not exists "uuid-ossp" with schema extensions')
            conn.close()

            conn = psycopg2.connect(dsn)
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            rel['migrations_antes'] = consulta(cur, 'select count(*) n from supabase_migrations.schema_migrations')[0]['n']
            titular = consulta(cur, 'select distinct user_id::text u from financeiro.perfil_acesso where pode_gerir')
            conferir('um unico titular administra os perfis existentes', len(titular) == 1, len(titular))
            titular = titular[0]['u']
            perfis = [r['id'] for r in consulta(cur, 'select id from public.perfil_financeiro order by id')]
            rel['perfis'] = perfis
            conn.rollback()
            IGNORA = {'public.perfil_financeiro': ['user_id']}

            # ---------------------------------------------------------------- 0. estado inicial
            r0 = retrato(cur)
            conn.rollback()
            l0 = leituras(conn, titular, perfis)
            rel['leituras_medidas'] = len(l0)
            rel['leituras_com_erro_no_inicio'] = sorted(k for k, v in l0.items() if isinstance(v, str))[:30]

            def aplicar_migration():
                cur.execute(MIGRATION.read_text(encoding='utf-8'))
                conn.commit()

            # ---------------------------------------------------------------- 1. migration
            aplicar_migration()
            r1 = retrato(cur, IGNORA)
            conn.rollback()
            r0s = dict(r0)
            cur.execute("select md5(coalesce(string_agg(x, '|' order by x), '')) h, count(*) n from (select (to_jsonb(t) - 'user_id')::text x from public.perfil_financeiro t) z")
            r0s['public.perfil_financeiro'] = dict(cur.fetchone())  # o retrato inicial ja nao tinha a coluna: mesma conta
            conferir('migration: nenhuma tabela de dados muda (fora a coluna nova do dono)', diferencas(r0s, r1) == [], diferencas(r0s, r1))
            l1 = leituras(conn, titular, perfis)
            conferir('migration: TODAS as leituras de tela do titular identicas', diferencas(l0, l1) == [], diferencas(l0, l1)[:10])
            donos = consulta(cur, 'select id, user_id::text dono, padrao from public.perfil_financeiro order by id')
            conferir('cada perfil tem dono, e e o titular', all(p['dono'] == titular for p in donos), [p['id'] for p in donos if p['dono'] != titular])
            conferir('um perfil padrao por dono', consulta(cur, 'select count(*) n from public.perfil_financeiro where padrao')[0]['n'] == 1)
            guarda = consulta(cur, 'select perfil_financeiro_id p from financeiro.guarda_sem_perfil')[0]['p']
            conferir('a guarda dos registros sem perfil e o perfil de destino', guarda == PERFIL_DESTINO, guarda)
            conferir('o titular e o administrador da plataforma (unico)',
                     [r['user_id'] for r in consulta(cur, 'select user_id::text user_id from financeiro.administrador_plataforma')] == [titular])
            conferir('nenhuma funcao decide posse pelo nome do perfil', consulta(cur, """select count(*) n from pg_proc p join pg_namespace n on n.oid = p.pronamespace
                where n.nspname = 'financeiro' and regexp_replace(p.prosrc, '--[^\\n]*', '', 'g') ~ 'nome\\s*=\\s*''Pessoal'''""")[0]['n'] == 0)
            conferir('nome unico por dono e padrao por dono (indices)', consulta(cur, """select count(*) n from pg_indexes where schemaname = 'public'
                and indexname in ('perfil_financeiro_dono_nome_uq', 'perfil_financeiro_padrao_por_dono_uq')""")[0]['n'] == 2)
            conferir('unicidade global do nome retirada', consulta(cur, UNICO_NO_NOME)[0]['n'] == 0)
            conn.rollback()

            # ---------------------------------------------------------------- 2. regularizacao dos itens sem perfil
            e = REG.estado(cur, PERFIL_DESTINO)
            conn.rollback()
            rel['previa'] = {'impressao': e['impressao'], **e['resumo'], 'divergentes_lista': e['divergentes']}
            conferir('previa: todos os itens sem perfil com posse demonstrada, nenhum divergente',
                     e['resumo']['divergentes'] == 0 and e['resumo']['com_posse_demonstrada'] == e['resumo']['itens_sem_perfil'] > 0, e['resumo'])
            conferir('previa repetida da a mesma impressao', REG.estado(cur, PERFIL_DESTINO)['impressao'] == e['impressao'])
            conn.rollback()
            conn.close()
            feito_arq = pasta / 'feito.json'
            REG.main(['executar', '--perfil', str(PERFIL_DESTINO), '--hash', e['impressao'], '--confirmo', 'REGULARIZAR ITENS', '--saida', str(feito_arq), '--dsn', dsn,
                      '--por', 'ensaio'])
            feito = json.loads(feito_arq.read_text(encoding='utf-8'))
            rel['execucao'] = {k: v for k, v in feito.items() if k != 'ids'}
            conn = psycopg2.connect(dsn)
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            r2 = retrato(cur, {**IGNORA, 'public.item_despesa': ['perfil_financeiro_id']})
            r1i = retrato(cur, IGNORA)
            conn.rollback()
            base = dict(r1)
            base['public.item_despesa'] = r2['public.item_despesa']  # so a coluna do perfil pode ter mudado nessa tabela
            cur.execute("select count(*) n from public.item_despesa where perfil_financeiro_id is null")
            conferir('regularizacao: nao resta item de despesa sem perfil', cur.fetchone()['n'] == 0)
            conferir('regularizacao: nenhuma tabela muda fora a coluna do perfil dos itens', diferencas(base, r2) == [], diferencas(base, r2))
            conferir('regularizacao: so a tabela de itens tem diferenca', diferencas(r1, r1i) == ['public.item_despesa'], diferencas(r1, r1i))
            conferir('regularizacao: todos os itens atribuidos estao no perfil de destino', consulta(
                cur, 'select count(*) n from public.item_despesa where id = any(%s) and perfil_financeiro_id = %s', (feito['ids'], PERFIL_DESTINO))[0]['n'] == len(feito['ids']))
            conn.rollback()
            l2 = leituras(conn, titular, perfis)
            conferir('regularizacao: TODAS as leituras de tela do titular identicas', diferencas(l1, l2) == [], diferencas(l1, l2)[:10])
            conferir('regularizacao: nenhuma outra tabela com registro sem perfil', feito['sem_perfil_restantes'] == {}, feito['sem_perfil_restantes'])
            conferir('repetir a execucao com a impressao antiga e recusado', _recusa(lambda: REG.main(
                ['executar', '--perfil', str(PERFIL_DESTINO), '--hash', e['impressao'], '--confirmo', 'REGULARIZAR ITENS', '--dsn', dsn])))

            # A guarda NAO sai nesta etapa: o catalogo de categorias (global, sem perfil) ainda e lido por ela.
            conferir('retirar a guarda e recusado enquanto o catalogo de categorias depender dela',
                     _recusa(lambda: REG.main(['retirar-guarda', '--confirmo', 'RETIRAR GUARDA', '--dsn', dsn, '--por', 'ensaio'])))
            conferir('a guarda continua no perfil de destino', consulta(cur, 'select perfil_financeiro_id p from financeiro.guarda_sem_perfil')[0]['p'] == PERFIL_DESTINO)
            conn.rollback()
            # e o que aconteceria sem ela (medido e desfeito): so a tela que le o catalogo pela guarda mudaria
            cur.execute("select financeiro.definir_guarda_sem_perfil(null, 'ensaio', 'medicao, desfeita em seguida')")
            conn.commit()
            l3 = leituras(conn, titular, perfis)
            rel['leituras_que_mudariam_sem_a_guarda'] = diferencas(l1, l3)
            cur.execute("select financeiro.definir_guarda_sem_perfil(%s, 'ensaio', 'guarda de volta')", (PERFIL_DESTINO,))
            conn.commit()
            conferir('sem a guarda, so mudaria a leitura que usa o catalogo de categorias (motivo de ela ficar)',
                     set(diferencas(l1, l3)) <= {f'ir_categorias_despesa_tela({PERFIL_DESTINO}, None)'}, diferencas(l1, l3))

            # ---------------------------------------------------------------- 3. reversao completa
            conn.close()
            REG.main(['reverter', '--feito', str(feito_arq), '--confirmo', 'REVERTER ITENS', '--dsn', dsn, '--por', 'ensaio'])
            conn = psycopg2.connect(dsn)
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            conferir('reversao dos itens: guarda restaurada', consulta(cur, 'select perfil_financeiro_id p from financeiro.guarda_sem_perfil')[0]['p'] == PERFIL_DESTINO)
            rv = retrato(cur, IGNORA)
            conn.rollback()
            conferir('reversao dos itens: banco identico ao de depois da migration', diferencas(r1, rv) == [], diferencas(r1, rv))
            cur.execute(REVERSAO.read_text(encoding='utf-8'))
            conn.commit()
            rf = retrato(cur)
            conn.rollback()
            conferir('reversao da migration: banco identico ao inicial (todas as tabelas)', diferencas(r0, rf) == [], diferencas(r0, rf))
            lf = leituras(conn, titular, perfis)
            conferir('reversao da migration: TODAS as leituras de tela identicas as iniciais', diferencas(l0, lf) == [], diferencas(l0, lf)[:10])
            estrutura = consulta(cur, """select (select count(*) from information_schema.columns where table_schema = 'public' and table_name = 'perfil_financeiro' and column_name = 'user_id') coluna,
                (select count(*) from pg_tables where schemaname = 'financeiro' and tablename in ('guarda_sem_perfil', 'regularizacao_perfil', 'administrador_plataforma')) tabelas,
                (select count(*) from pg_index i where i.indrelid = 'public.perfil_financeiro'::regclass and i.indisunique and not i.indisprimary and i.indnatts = 1
                    and (select a.attname from pg_attribute a where a.attrelid = i.indrelid and a.attnum = i.indkey[0]) = 'nome') unico_global""")[0]
            conferir('reversao da migration: estrutura nova retirada e nome unico global de volta', estrutura == {'coluna': 0, 'tabelas': 0, 'unico_global': 1}, estrutura)
            conn.rollback()

            # ---------------------------------------------------------------- 4. de novo, e um segundo usuario
            aplicar_migration()
            e2 = REG.estado(cur, PERFIL_DESTINO)
            conn.rollback()
            conferir('reaplicada a migration, a previa da a mesma impressao', e2['impressao'] == e['impressao'])
            conn.close()
            REG.main(['executar', '--perfil', str(PERFIL_DESTINO), '--hash', e2['impressao'], '--confirmo', 'REGULARIZAR ITENS', '--saida', str(feito_arq), '--dsn', dsn])
            conn = psycopg2.connect(dsn)
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            l4 = leituras(conn, titular, perfis)
            outro = str(uuid.uuid4())
            cur.execute("insert into auth.users (id, email) values (%s, 'segundo.usuario@teste.local')", (outro,))
            conn.commit()
            nomes = [r['nome'] for r in consulta(cur, 'select nome from public.perfil_financeiro order by id')]
            conn.rollback()
            novos = []
            for nome in nomes:  # os MESMOS nomes dos perfis do titular
                como(cur, outro)
                cur.execute('select financeiro.criar_perfil(%s::jsonb) j', (json.dumps({'nome': nome}),))
                novos.append(cur.fetchone()['j']['id'])
                conn.commit()
            conferir('segundo usuario cria perfis com os MESMOS nomes dos do titular', len(novos) == len(nomes))
            como(cur, outro)
            cur.execute('select financeiro.definir_perfil_padrao(%s)', (novos[0],))
            conn.commit()
            conferir('cada um com o seu perfil padrao', consulta(cur, 'select user_id::text u, count(*) n from public.perfil_financeiro where padrao group by 1 order by 1')
                     == sorted([{'u': titular, 'n': 1}, {'u': outro, 'n': 1}], key=lambda x: x['u']))
            conn.rollback()
            l_outro = leituras(conn, outro, perfis)
            com_perfil = {k: v for k, v in l_outro.items() if any(k.endswith(f'({p}') or f'({p},' in k for p in perfis)}
            conferir('segundo usuario: TODAS as leituras nos perfis do titular recusadas (42501)',
                     com_perfil and all(isinstance(v, str) and v.startswith('ERRO 42501') for v in com_perfil.values()),
                     [k for k, v in com_perfil.items() if not (isinstance(v, str) and v.startswith('ERRO 42501'))][:8])
            rel['leituras_recusadas_ao_segundo_usuario'] = len(com_perfil)
            proprias = leituras(conn, outro, novos)
            texto = json.dumps(proprias, default=str)
            conferir('segundo usuario: nos proprios perfis, nenhum registro financeiro (conta comeca vazia)',
                     consulta(cur, """select (select count(*) from public.conta where perfil_financeiro_id = any(%s)) + (select count(*) from public.item_despesa where perfil_financeiro_id = any(%s))
                                           + (select count(*) from public.conta_bancaria where perfil_financeiro_id = any(%s)) n""", (novos, novos, novos))[0]['n'] == 0)
            rel['leituras_do_segundo_usuario_nos_proprios_perfis'] = len(proprias)
            rel['tamanho_das_respostas_proprias'] = len(texto)
            conn.rollback()
            l5 = leituras(conn, titular, perfis)
            conferir('com o segundo usuario: TODAS as leituras de tela do titular identicas', diferencas(l4, l5) == [], diferencas(l4, l5)[:10])
            conferir('leituras do titular depois de tudo = as do estado inicial', diferencas(l0, l5) == [], diferencas(l0, l5)[:10])
            como(cur, outro)
            cur.execute('savepoint tr')
            try:
                cur.execute("select financeiro.criar_tr(%s::jsonb, %s)", (json.dumps({'competencia': '2031-01', 'valor_percentual': '0.10'}), str(uuid.uuid4())))
                tr = 'GRAVOU'
            except psycopg2.Error as erro:
                tr = erro.pgcode
            conn.rollback()
            conferir('segundo usuario nao altera indices de TR', tr == '42501', tr)

            # cadastro com pagamento imediato do titular (publicado em 17/11/2026): funciona e e desfeito
            banco_id = consulta(cur, "select id from public.conta_bancaria where perfil_financeiro_id = %s and status = 'ATIVO' order by id limit 1", (PERFIL_DESTINO,))[0]['id']
            cat = consulta(cur, 'select id from public.categoria where coalesce(ativo, true) order by id limit 1')[0]['id']
            saldo = consulta(cur, 'select saldo_atual s from public.conta_bancaria where id = %s', (banco_id,))[0]['s']
            como(cur, titular)
            cur.execute('select financeiro.criar_despesa_paga(%s, %s::jsonb, %s::jsonb, %s) j',
                        (PERFIL_DESTINO, json.dumps({'nome': 'Ensaio de pagamento imediato', 'valor': '10.00', 'categoria_id': cat, 'data_vencimento': '2026-11-20'}),
                         json.dumps({'conta_bancaria_id': banco_id, 'data_pagamento': '2026-11-20'}), str(uuid.uuid4())))
            j = cur.fetchone()['j']
            conferir('cadastro com pagamento imediato do titular: despesa paga e saldo debitado em 10,00',
                     j['paga'] is True and float(j['pagamento']['saldo_conta']) == round(float(saldo) - 10, 2), j['pagamento'].get('valor_pago'))
            como(cur, outro)
            cur.execute('savepoint alheia')
            try:
                cur.execute('select financeiro.criar_despesa_paga(%s, %s::jsonb, %s::jsonb, %s)',
                            (novos[0], json.dumps({'nome': 'x', 'valor': '1.00', 'categoria_id': cat, 'data_vencimento': '2026-11-20'}),
                             json.dumps({'conta_bancaria_id': banco_id, 'data_pagamento': '2026-11-20'}), str(uuid.uuid4())))
                alheia = 'GRAVOU'
            except psycopg2.Error as erro:
                alheia = (erro.diag.message_primary or '')[:60]
            conferir('segundo usuario nao paga com a conta bancaria do titular', alheia != 'GRAVOU', alheia)
            conn.rollback()  # desfaz o pagamento de ensaio
            conferir('pagamento de ensaio desfeito: saldo igual', consulta(cur, 'select saldo_atual s from public.conta_bancaria where id = %s', (banco_id,))[0]['s'] == saldo)
            conn.rollback()
            conn.close()
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


def _recusa(funcao):
    try:
        funcao()
    except SystemExit as e:
        return e.code not in (0, None)
    return False


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--saida', required=True, help='pasta privada do relatorio (fora do repositorio)')
    ap.add_argument('--backup-id')
    a = ap.parse_args(argv)
    saida = Path(a.saida).resolve()
    if RAIZ in saida.parents or saida == RAIZ:
        raise SystemExit('A pasta do relatorio tem de ficar FORA do repositorio.')
    rel = ensaiar(saida, a.backup_id)
    for v in rel['verificacoes']:
        print(('ok    ' if v['resultado'] == 'ok' else 'FALHA ') + v['verificacao'] + (f" [{v['detalhe']}]" if v['resultado'] != 'ok' and v['detalhe'] else ''))
    print(f"backup {rel['backup_id']} | {len(rel['verificacoes'])} verificacoes | {len(rel['falhas'])} falha(s) | leituras medidas: {rel.get('leituras_medidas')}")
    return 1 if rel['falhas'] else 0


if __name__ == '__main__':
    sys.exit(main())
