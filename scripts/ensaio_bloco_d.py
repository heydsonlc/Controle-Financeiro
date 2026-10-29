#!/usr/bin/env python
"""
FIN-BLOCO-D-1 — ensaio completo da conversao do projeto Supabase para producao, num PostgreSQL 17 DESCARTAVEL.

O projeto remoto e a origem (controle_financeiro_dev) so sao LIDOS. Passos, todos no banco descartavel:
 1. copia do projeto (public, financeiro, supabase_migrations) por fluxo pg_dump -> pg_restore, sem arquivo de backup;
    os usuarios do Auth entram so com o id (e-mail ficticio, sem senha); os dados de public.usuario (login do Flask,
    com hash de senha) ficam de fora;
 2. conferencia da restauracao com o remoto: linhas e md5 por tabela, sequencias, funcoes, politicas, RLS, FKs,
    gatilhos e privilegios;
 3. retirada dos ficticios (scripts/limpeza_ficticios_supabase.py): relacao igual a do remoto, ensaio sem gravar e
    retirada confirmada, com as conferencias do proprio script;
 4. migrations pendentes: aplicar, reverter em ordem inversa e reaplicar, sem alterar dados;
 5. titular ficticio com acesso aos perfis 1 e 2 e carga da origem (scripts/carga_supabase.py), com conferencia
    linha a linha; uma segunda carga tem de ser recusada.
O relatorio so tem contagens, nomes de tabela e resultados (nenhum valor dos dados).

Uso (conexoes so por variavel de ambiente, nunca impressas):
    set CF_ENSAIO_REMOTO_DSN=...   (projeto Supabase, Session pooler)   set CARGA_ORIGEM_DSN=...   set CF_PG17_BIN=...
    python scripts/ensaio_bloco_d.py --identidade docs/carga/identidade_ficticios_supabase.json
                                     --mapa docs/carga/mapa_controle_financeiro_dev.json [--relatorio saida.json]
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import psycopg2
import psycopg2.extras

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from scripts.backup_banco import comparar, conectar, retrato, retrato_dsn  # noqa: E402
from scripts.carga_supabase import CargaRecusada, executar  # noqa: E402
from scripts.limpeza_ficticios_supabase import LimpezaRecusada, montar_relacao, ref_do_dsn, retirar  # noqa: E402
from tests.supabase_local import ClusterLocal, encontrar_pg_bin  # noqa: E402

ESQUEMAS_COPIA = ('public', 'financeiro', 'supabase_migrations')
SEM_DADOS = ('public.usuario',)
TITULAR_ENSAIO = '00000000-0000-4000-8000-0000000000d1'
PAPEIS_SUPABASE = ('supabase_admin', 'supabase_auth_admin', 'supabase_storage_admin', 'supabase_realtime_admin',
                   'dashboard_user', 'pgbouncer', 'supabase_replication_admin', 'supabase_read_only_user')


def copiar_projeto(remoto_dsn, cluster, pg_bin):
    """Remoto -> descartavel por fluxo (nenhum arquivo). Devolve os avisos do pg_restore."""
    cluster.aplicar_shim()
    conn = cluster.conectar()
    with conn.cursor() as cur:
        for papel in PAPEIS_SUPABASE:
            cur.execute(f"do $$ begin create role {papel} nologin; exception when duplicate_object then null; end $$")
        # O shim imita o padrao da plataforma (ALL para anon/authenticated nas tabelas novas do public). Na copia, os
        # privilegios tem de ser SO os do remoto (o dump nao emite REVOKE para ACL igual ao padrao do PostgreSQL).
        cur.execute('alter default privileges in schema public revoke all on tables from anon, authenticated, service_role')
        remoto = conectar(remoto_dsn)
        rc = remoto.cursor()
        rc.execute('select id::text from auth.users order by created_at')
        ids = [r[0] for r in rc.fetchall()]
        remoto.rollback()
        remoto.close()
        for n, uid in enumerate(ids, 1):
            cur.execute('insert into auth.users (id, email) values (%s, %s)', (uid, f'usuario.{n}@ensaio.local'))
    conn.close()
    exe = '.exe' if os.name == 'nt' else ''
    dump = subprocess.Popen([str(Path(pg_bin) / f'pg_dump{exe}'), '--format=custom', '--no-owner',
                             *[f'--schema={e}' for e in ESQUEMAS_COPIA], *[f'--exclude-table-data={t}' for t in SEM_DADOS],
                             f'--dbname={remoto_dsn}'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    restauracao = subprocess.run([str(Path(pg_bin) / f'pg_restore{exe}'), '--no-owner', f'--dbname={cluster.dsn()}'],
                                 stdin=dump.stdout, capture_output=True, text=True)
    dump.stdout.close()
    erro_dump = dump.stderr.read().decode(errors='replace')
    if dump.wait() != 0:
        raise SystemExit('pg_dump falhou: ' + erro_dump[-800:])
    avisos = [l for l in (restauracao.stderr or '').splitlines() if 'error:' in l.lower()]
    return len(ids), avisos


TABELAS_DE_VALOR = ('conta_bancaria', 'conta', 'movimento_financeiro', 'lancamento_agregado', 'receita_realizada',
                    'receita_orcamento', 'financiamento', 'financiamento_parcela', 'contrato_consorcio')


def somas(origem_dsn, destino_dsn):
    """Saldos, faturas e financiamentos: soma de cada coluna numerica, origem x destino (o destino so tem a carga nessas
    tabelas). Devolve, por tabela, 'iguais' ou as colunas divergentes."""
    saida = {}
    o, d = conectar(origem_dsn), conectar(destino_dsn)
    try:
        oc, dc = o.cursor(), d.cursor()
        for t in TABELAS_DE_VALOR:
            oc.execute("select column_name from information_schema.columns where table_schema = 'public' and table_name = %s "
                       "and data_type in ('numeric', 'double precision', 'real')", (t,))
            colunas = [c for (c,) in oc.fetchall()]
            if not colunas:
                continue
            sql = f'select count(*), {", ".join(f"coalesce(sum({c}), 0)" for c in colunas)} from public."{t}"'
            oc.execute(sql)
            dc.execute(sql)
            a, b = oc.fetchone(), dc.fetchone()
            difs = [c for c, x, y in zip(['linhas', *colunas], a, b) if x != y]
            saida[t] = 'iguais' if not difs else difs
    finally:
        o.rollback()
        d.rollback()
        o.close()
        d.close()
    return saida


def aplicar_pendentes(conn, versoes):
    with conn.cursor() as cur:
        for v in versoes:
            arquivo = next((RAIZ / 'supabase' / 'migrations').glob(f'{v}_*.sql'))
            cur.execute(arquivo.read_text(encoding='utf-8'))
            cur.execute('insert into supabase_migrations.schema_migrations (version, name) values (%s, %s)',
                        (v, arquivo.stem.split('_', 1)[1]))
    conn.commit()


def reverter(conn, versoes):
    with conn.cursor() as cur:
        for v in reversed(versoes):
            arquivo = next((RAIZ / 'supabase' / 'reversao').glob(f'{v}_*.sql'))
            cur.execute(arquivo.read_text(encoding='utf-8'))
            cur.execute('delete from supabase_migrations.schema_migrations where version = %s', (v,))
    conn.commit()


def main():
    parser = argparse.ArgumentParser(description='Ensaio do Bloco D num PostgreSQL 17 descartavel.')
    parser.add_argument('--identidade', required=True)
    parser.add_argument('--mapa', required=True)
    parser.add_argument('--remoto-env', default='CF_ENSAIO_REMOTO_DSN')
    parser.add_argument('--origem-env', default='CARGA_ORIGEM_DSN')
    parser.add_argument('--relatorio')
    args = parser.parse_args()
    remoto_dsn, origem_dsn = os.environ.get(args.remoto_env), os.environ.get(args.origem_env)
    if not remoto_dsn or not origem_dsn:
        print(f'ENSAIO_RECUSADO: defina {args.remoto_env} e {args.origem_env}', file=sys.stderr)
        return 2
    identidade = json.loads(Path(args.identidade).read_text(encoding='utf-8'))
    if not (ref_do_dsn(remoto_dsn) or '').startswith(identidade['projeto_ref_prefixo']):
        print('ENSAIO_RECUSADO: a conexao remota nao e a do projeto da identidade', file=sys.stderr)
        return 2
    pg_bin = os.environ.get('CF_PG17_BIN') or str(encontrar_pg_bin())
    rel = {'pg_bin_versao': subprocess.run([str(Path(pg_bin) / ('pg_dump.exe' if os.name == 'nt' else 'pg_dump')), '--version'],
                                           capture_output=True, text=True).stdout.strip()}

    remoto = conectar(remoto_dsn)
    retrato_remoto = retrato(remoto)
    relacao_remota, _ = montar_relacao(remoto.cursor(cursor_factory=psycopg2.extras.RealDictCursor), identidade)
    remoto.rollback()
    remoto.close()
    rel['remoto'] = {'tabelas_com_linhas': sum(1 for n in retrato_remoto['tabelas'].values() if n),
                     'linhas': sum(retrato_remoto['tabelas'].values()), 'funcoes': len(retrato_remoto['funcoes']),
                     'politicas': len(retrato_remoto['politicas']), 'migrations': len(retrato_remoto['migrations']),
                     'ficticios': relacao_remota['total'], 'ambiguos': relacao_remota['ambiguos']}

    with tempfile.TemporaryDirectory(prefix='ensaio-bloco-d-') as tmp, ClusterLocal(pg_bin, tmp) as cluster:
        # 1-2. Copia e conferencia da restauracao.
        usuarios, avisos = copiar_projeto(remoto_dsn, cluster, pg_bin)
        retrato_copia = retrato_dsn(cluster.dsn())
        difs = comparar(retrato_remoto, retrato_copia, ignorar_tabelas=SEM_DADOS)
        rel['restauracao'] = {'usuarios_auth_so_id': usuarios, 'avisos_pg_restore': avisos[:20],
                              'tabelas': len(retrato_copia['tabelas']), 'linhas': sum(retrato_copia['tabelas'].values()),
                              'diferencas_com_o_remoto': difs,
                              'resultado': 'IDENTICA' if not difs else 'DIVERGENTE',
                              'fora_da_copia': {t: retrato_remoto['tabelas'][t] for t in SEM_DADOS}}
        if difs:
            rel['interrompido'] = 'restauracao divergente: limpeza, migrations e carga nao ensaiadas'
            return fechar(rel, args)

        # 3. Retirada dos ficticios.
        conn = conectar(cluster.dsn(), leitura=False)
        relacao_copia, _ = montar_relacao(conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor), identidade)
        conn.rollback()
        rel['limpeza'] = {'relacao_igual_a_do_remoto': relacao_copia['tabelas'] == relacao_remota['tabelas'],
                          'a_retirar': relacao_copia['total']}
        try:
            ensaio = retirar(conn, identidade, relacao_copia, confirmar=False)
            conn.close()
            # FIN-BLOCO-D-2: a simulacao e somente leitura; o banco tem de ficar integralmente igual (dados, sequencias,
            # estrutura), e repetir tem de dar o mesmo plano.
            difs_ensaio = comparar(retrato_copia, retrato_dsn(cluster.dsn()))
            conn = conectar(cluster.dsn(), leitura=False)
            repetida = retirar(conn, identidade, relacao_copia, confirmar=False)
            conn.close()
            rel['limpeza']['ensaio_sem_gravar'] = {
                'resultado': ensaio['resultado'], 'removeria': ensaio['total_previsto'],
                'estado_integralmente_igual': not difs_ensaio, 'diferencas': difs_ensaio,
                'repeticao_igual': repetida == ensaio}
            conn = conectar(cluster.dsn(), leitura=False)
            feito = retirar(conn, identidade, relacao_copia, confirmar=True)
            conn.close()
        except LimpezaRecusada as erro:
            rel['limpeza']['retirada'] = f'RECUSADA: {erro}'
            rel['interrompido'] = 'retirada recusada: migrations e carga nao ensaiadas'
            return fechar(rel, args)
        limpo = retrato_dsn(cluster.dsn())
        rel['limpeza']['retirada'] = {k: feito[k] for k in ('resultado', 'removidas', 'geradas_por_gatilho_e_removidas',
                                                             'total_removido', 'conferencia', 'ordem')}
        c = conectar(cluster.dsn())
        cur = c.cursor()
        cur.execute('select id, nome from public.perfil_financeiro order by id')
        rel['limpeza']['depois'] = {'perfis': cur.fetchall(), 'linhas': sum(limpo['tabelas'].values()),
                                    'estrutura_igual': not [d for d in comparar(retrato_copia, limpo)
                                                            if not d.startswith(('tabelas:', 'md5:', 'sequencias:'))]}
        c.close()

        # 4. Migrations pendentes.
        locais = sorted(p.name.split('_', 1)[0] for p in (RAIZ / 'supabase' / 'migrations').glob('*.sql'))
        pendentes = [v for v in locais if v not in limpo['migrations']]
        conn = conectar(cluster.dsn(), leitura=False)
        aplicar_pendentes(conn, pendentes)
        aplicado = retrato_dsn(cluster.dsn())
        novas = sorted(set(aplicado['tabelas']) - set(limpo['tabelas']))
        dados_alterados = [t for t in limpo['md5'] if limpo['md5'][t] != aplicado['md5'].get(t) and t != 'supabase_migrations.schema_migrations']
        reverter(conn, pendentes)
        revertido = retrato_dsn(cluster.dsn())
        aplicar_pendentes(conn, pendentes)
        reaplicado = retrato_dsn(cluster.dsn())
        conn.close()
        rel['migrations'] = {
            'pendentes': pendentes, 'tabelas_novas': {t: aplicado['tabelas'][t] for t in novas},
            'funcoes_novas_ou_alteradas': sum(1 for f, h in aplicado['funcoes'].items() if limpo['funcoes'].get(f) != h),
            'dados_existentes_alterados': dados_alterados,
            'reversao_volta_ao_estado_anterior': comparar(limpo, revertido, ignorar_tabelas=('supabase_migrations.schema_migrations',)),
            'reaplicacao_igual_a_aplicacao': comparar(aplicado, reaplicado, ignorar_tabelas=('supabase_migrations.schema_migrations',)),
        }

        # 5. Titular (ficticio) e carga.
        c = conectar(cluster.dsn(), leitura=False)
        with c.cursor() as cur:
            cur.execute("insert into auth.users (id, email) values (%s, 'titular@ensaio.local')", (TITULAR_ENSAIO,))
            for pid in (1, 2):
                cur.execute("insert into financeiro.perfil_acesso (user_id, perfil_financeiro_id, papel, pode_gerir) "
                            "values (%s, %s, 'TITULAR', true)", (TITULAR_ENSAIO, pid))
        c.commit()
        c.close()
        mapa = json.loads(Path(args.mapa).read_text(encoding='utf-8'))
        mapa['titular_user_id'] = TITULAR_ENSAIO
        antes_carga = retrato_dsn(cluster.dsn())
        try:
            carga = executar(origem_dsn, cluster.dsn(), mapa, confirmar=True)
            rel['carga'] = {k: carga.get(k) for k in ('resultado', 'conferencia', 'origem_inalterada', 'sensiveis', 'preferencias',
                                                       'tr_divergentes', 'preexistentes', 'avisos', 'perfis')}
            rel['carga']['linhas_gravadas'] = sum(v['inseridos'] for v in carga['tabelas'].values())
            rel['carga']['linhas_da_origem'] = sum(v['origem'] for v in carga['tabelas'].values())
            rel['carga']['reaproveitadas_do_destino'] = {t: v['reaproveitados'] for t, v in carga['tabelas'].items() if v['reaproveitados']}
            rel['carga']['tabelas'] = len(carga['tabelas'])
            rel['carga']['somas_origem_x_destino'] = somas(origem_dsn, cluster.dsn())
            depois_carga = retrato_dsn(cluster.dsn())
            rel['carga']['tabelas_preservadas_alteradas'] = [
                t for t in antes_carga['md5'] if antes_carga['tabelas'][t] == depois_carga['tabelas'][t]
                and antes_carga['md5'][t] != depois_carga['md5'][t]]
            try:
                executar(origem_dsn, cluster.dsn(), mapa, confirmar=True)
                rel['carga']['segunda_carga'] = 'ACEITA (ERRO: duplicaria)'
            except CargaRecusada as erro:
                rel['carga']['segunda_carga'] = f'recusada: {erro}'
        except CargaRecusada as erro:
            rel['carga'] = {'resultado': f'RECUSADA: {erro}'}
    return fechar(rel, args)


def fechar(rel, args):
    texto = json.dumps(rel, ensure_ascii=False, indent=1, default=str)
    if args.relatorio:
        Path(args.relatorio).write_text(texto, encoding='utf-8')
    print(texto)
    return 0 if 'interrompido' not in rel and str(rel.get('carga', {}).get('resultado', '')).startswith('GRAVADO') else 1


if __name__ == '__main__':
    sys.exit(main())
