"""
MOBILE-CONTAS-REAL-1 — contas do mes FICTICIAS e temporarias no Supabase de teste.

Mesmos dados declarados em tests/supabase_local.py (ITENS_DESPESA, CONTAS_FICTICIAS,
LANCAMENTOS_FICTICIOS, LIMITES_FICTICIOS), cujos valores foram comparados com o
Flask no cluster local. Aqui os ids sao gerados pelo banco; o mapeamento id logico
-> id real fica em data/contas_real_1_teste.json (fora do Git) e e o UNICO alvo
do --remover.

Pre-requisito: scripts/supabase_perfis_seed_teste.py ja executado (usa o "Perfil B"
temporario dele). "Pessoal" e "Empresa" sao os perfis existentes (so lidos).

Recusa: projeto da Calculadora; tabelas de contas/compras/limites/cartoes ja com
dados (garante valores esperados exatos e que nada preexistente seja tocado).
Sem --confirmar, executa e desfaz (rollback).

Uso:
    scripts/supabase_contas_seed_teste.py [--confirmar]
    scripts/supabase_contas_seed_teste.py --remover [--confirmar]
"""
# FIN-PUBLICACAO-SEGURA-1: o projeto de teste virou a producao; recusa antes de ler credenciais ou conectar.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from guarda_producao import recusar_em_producao
recusar_em_producao(__file__)
import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from tests.supabase_local import (  # noqa: E402
    CATEGORIAS_CARTAO,
    CATEGORIAS_CONTAS,
    CONTAS_FICTICIAS,
    ITENS_DESPESA,
    LANCAMENTOS_FICTICIOS,
    LIMITES_FICTICIOS,
    semear_contas,
)

ESTADO = RAIZ / 'data' / 'contas_real_1_teste.json'
ESTADO_PERFIS = RAIZ / 'data' / 'perfis_real_1_teste.json'
SUFIXO = ' [teste MOBILE-CONTAS-REAL-1]'
PROJETOS_PROIBIDOS = {'dshqjhyymtpxpxuntzbz'}
TABELAS_VAZIAS = ('conta', 'item_despesa', 'lancamento_agregado', 'cartao_categoria_limite', 'categoria_cartao')
# Ordem de remocao respeitando as dependencias (FKs).
REMOCAO = [
    ('cartao_categoria_limite', [x[0] for x in LIMITES_FICTICIOS]),
    ('lancamento_agregado', [x[0] for x in LANCAMENTOS_FICTICIOS]),
    ('conta', [x[0] for x in CONTAS_FICTICIAS]),
    ('item_despesa', [x[0] for x in ITENS_DESPESA]),
    ('categoria_cartao', [x[0] for x in CATEGORIAS_CARTAO]),
    ('categoria', [x[0] for x in CATEGORIAS_CONTAS]),
]


def conectar():
    import psycopg2
    from dotenv import dotenv_values
    url = dotenv_values(RAIZ / '.env.staging', encoding='utf-8-sig').get('DATABASE_URL') or ''
    usuario = urlsplit(url).username or ''
    ref = usuario.split('.', 1)[1] if usuario.startswith('postgres.') else ''
    if not ref or ref in PROJETOS_PROIBIDOS:
        raise SystemExit('Projeto invalido ou proibido no .env.staging.')
    conn = psycopg2.connect(url, connect_timeout=15)
    conn.autocommit = False
    return conn


def criar(cur):
    if not ESTADO_PERFIS.exists():
        raise SystemExit('Rode antes scripts/supabase_perfis_seed_teste.py (Perfil B temporario).')
    for tabela in TABELAS_VAZIAS:
        cur.execute(f'select count(*) from public.{tabela}')
        if cur.fetchone()[0]:
            raise SystemExit(f'public.{tabela} ja tem dados: nada feito (preserva registros preexistentes).')
    cur.execute('select count(*) from public.categoria where nome like %s', ('%' + SUFIXO,))
    if cur.fetchone()[0]:
        raise SystemExit('Ja existem categorias de teste: remova antes de criar de novo.')
    perfis = {}
    for chave, nome in (('PESSOAL', 'Pessoal'), ('EMPRESA', 'Empresa')):
        cur.execute('select id from public.perfil_financeiro where nome = %s and ativo', (nome,))
        linha = cur.fetchone()
        if not linha:
            raise SystemExit(f'Perfil existente "{nome}" nao encontrado ativo.')
        perfis[chave] = linha[0]
    perfis['PERFIL_B'] = json.loads(ESTADO_PERFIS.read_text(encoding='utf-8'))['id_perfil_b']
    mapa = semear_contas(cur, perfis_ids=perfis, sufixo_nomes=SUFIXO, ids_fixos=False)
    return {'perfis': perfis, 'mapa': {str(k): v for k, v in mapa.items()}}


def remover(cur, estado):
    mapa = estado['mapa']
    removidos = {}
    for tabela, logicos in REMOCAO:
        ids = [mapa[str(i)] for i in logicos if str(i) in mapa]
        extra = ' and nome like %s' if tabela in ('categoria', 'categoria_cartao') else ''
        params = [ids] + (['%' + SUFIXO] if extra else [])
        cur.execute(f'delete from public.{tabela} where id = any(%s){extra}', params)
        removidos[tabela] = cur.rowcount
    return removidos


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--remover', action='store_true')
    parser.add_argument('--confirmar', action='store_true')
    args = parser.parse_args()
    conn = conectar()
    try:
        with conn.cursor() as cur:
            if args.remover:
                if not ESTADO.exists():
                    raise SystemExit('Sem estado de teste para remover.')
                estado = json.loads(ESTADO.read_text(encoding='utf-8'))
                print('Removidos:', remover(cur, estado))
            else:
                if ESTADO.exists():
                    raise SystemExit('Ja existe estado de teste: remova antes de criar de novo.')
                estado = criar(cur)
                print(f"Criados: {len(estado['mapa'])} registros ficticios | perfis usados: {estado['perfis']}")
        if args.confirmar:
            conn.commit()
            if args.remover:
                ESTADO.unlink()
            else:
                ESTADO.write_text(json.dumps(estado, indent=1), encoding='utf-8')
                print(f"CF_ID_FATURA_EMPRESA={estado['mapa']['511']}")
            print('CONFIRMADO: alteracoes gravadas.')
        else:
            conn.rollback()
            print('SIMULACAO: nada foi gravado (use --confirmar).')
    finally:
        conn.close()


if __name__ == '__main__':
    sys.exit(main())
