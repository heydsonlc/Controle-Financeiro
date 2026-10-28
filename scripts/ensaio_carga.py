#!/usr/bin/env python
"""
FIN-PRE-PRODUCAO-1 (3.1) — ensaio repetivel da carga real: origem (ex.: controle_financeiro_dev, so leitura) para um
PostgreSQL DESCARTAVEL com o mesmo esquema do destino (shim do Supabase + tabelas do Flask + supabase/migrations),
criado e destruido aqui. Nada e gravado na origem nem em banco persistente.

Uso:
    set CARGA_ORIGEM_DSN=...   (so de variavel de ambiente; nunca impresso)
    python scripts/ensaio_carga.py --mapa docs/carga/mapa_controle_financeiro_dev.json [--relatorio saida.json]

O destino descartavel imita o projeto de producao no inicio: um usuario titular (ficticio) com os perfis "Pessoal" e
"Empresa" vazios (ids 1 e 2, como no projeto Controle-Financeiro). O relatorio tem so contagens, nomes de tabela e
resultados de conferencia (nenhum valor dos dados).
"""
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from scripts.carga_supabase import CargaRecusada, executar  # noqa: E402
from tests.supabase_local import ClusterLocal, encontrar_pg_bin  # noqa: E402

TITULAR_ENSAIO = '00000000-0000-4000-8000-0000000000e1'


def preparar_destino(cluster):
    cluster.aplicar_shim()
    cluster.criar_tabelas_legadas()
    conn = cluster.conectar()
    try:
        with conn.cursor() as cur:
            for migration in sorted((RAIZ / 'supabase' / 'migrations').glob('*.sql')):
                cur.execute(migration.read_text(encoding='utf-8'))
            cur.execute("insert into auth.users (id, email) values (%s, 'titular.ensaio@teste.local')", (TITULAR_ENSAIO,))
            for pid, nome, tipo in ((1, 'Pessoal', 'PESSOAL'), (2, 'Empresa', 'EMPRESA')):
                cur.execute("insert into public.perfil_financeiro (id, nome, tipo, cor, ativo, padrao) values (%s, %s, %s, '#2563eb', true, %s)",
                            (pid, nome, tipo, pid == 1))
                cur.execute("insert into financeiro.perfil_acesso (user_id, perfil_financeiro_id, papel, pode_gerir) values (%s, %s, 'TITULAR', true)",
                            (TITULAR_ENSAIO, pid))
            cur.execute("select setval(pg_get_serial_sequence('public.perfil_financeiro', 'id'), 100)")
            cur.execute('select version()')
            return cur.fetchone()[0].split(',')[0]
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description='Ensaio da carga num PostgreSQL descartavel.')
    parser.add_argument('--mapa', required=True)
    parser.add_argument('--origem-env', default='CARGA_ORIGEM_DSN')
    parser.add_argument('--relatorio')
    args = parser.parse_args()
    origem = os.environ.get(args.origem_env)
    if not origem:
        print(f'ENSAIO_RECUSADO: defina {args.origem_env}', file=sys.stderr)
        return 2
    mapa = json.loads(Path(args.mapa).read_text(encoding='utf-8'))
    mapa['titular_user_id'] = TITULAR_ENSAIO
    with tempfile.TemporaryDirectory(prefix='ensaio-carga-') as tmp, ClusterLocal(encontrar_pg_bin(), tmp) as cluster:
        versao = preparar_destino(cluster)
        try:
            relatorio = executar(origem, cluster.dsn(), mapa, confirmar=True)
        except CargaRecusada as erro:
            print(f'ENSAIO_RECUSADO: {erro}', file=sys.stderr)
            return 2
        relatorio['destino_descartavel'] = versao
        # Segunda carga no mesmo destino: tem de ser recusada (sem duplicar).
        try:
            executar(origem, cluster.dsn(), mapa, confirmar=True)
            relatorio['segunda_carga'] = 'ACEITA (ERRO: duplicaria)'
        except CargaRecusada as erro:
            relatorio['segunda_carga'] = f'recusada: {erro}'
    texto = json.dumps(relatorio, ensure_ascii=False, indent=1, default=str)
    if args.relatorio:
        Path(args.relatorio).write_text(texto, encoding='utf-8')
    print(texto)
    return 0 if relatorio['segunda_carga'].startswith('recusada') else 1


if __name__ == '__main__':
    sys.exit(main())
