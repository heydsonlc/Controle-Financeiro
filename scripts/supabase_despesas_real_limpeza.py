"""
FIN-DESPESAS-REAL-1 — limpeza do que os TESTES criaram (alem dos seeds) no Supabase de teste.

`marcar` (antes dos seeds): guarda o maior id de cada tabela financeira e o instante inicial.
`remover` (depois dos testes, ANTES dos removedores dos seeds): apaga so o que os testes criaram
pela tela ou pela API — despesas e recorrencias novas (com contas, compras, identidades,
dispensas e chaves de idempotencia) e movimentos de teste. Linhas dos seeds ficam para os
proprios removedores. Nada com id ate a marca e tocado.

Uso:
    scripts/supabase_despesas_real_limpeza.py marcar
    scripts/supabase_despesas_real_limpeza.py remover [--confirmar]
"""
import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / 'scripts'))
from supabase_contas_seed_teste import conectar  # noqa: E402

MARCA = RAIZ / 'data' / 'despesas_real_1_marca.json'
TABELAS = ('item_despesa', 'conta', 'lancamento_agregado', 'movimento_financeiro')


def itens_dos_seeds():
    ids = set()
    contas = RAIZ / 'data' / 'contas_real_1_teste.json'
    recorrencia = RAIZ / 'data' / 'recorrencia_real_1_teste.json'
    if contas.exists():
        from tests.supabase_local import ITENS_DESPESA
        mapa = json.loads(contas.read_text(encoding='utf-8'))['mapa']
        ids |= {mapa[str(i[0])] for i in ITENS_DESPESA}
    if recorrencia.exists():
        ids |= set(json.loads(recorrencia.read_text(encoding='utf-8'))['itens'].values())
    return ids


def main():
    sys.path.insert(0, str(RAIZ))
    parser = argparse.ArgumentParser()
    parser.add_argument('acao', choices=('marcar', 'remover'))
    parser.add_argument('--confirmar', action='store_true')
    args = parser.parse_args()
    conn = conectar()
    try:
        with conn.cursor() as cur:
            if args.acao == 'marcar':
                if MARCA.exists():
                    raise SystemExit('Ja existe marca: rode remover antes.')
                marca = {}
                for tabela in TABELAS:
                    cur.execute(f'select coalesce(max(id), 0) from public.{tabela}')
                    marca[tabela] = cur.fetchone()[0]
                cur.execute('select now()::text')
                marca['inicio'] = cur.fetchone()[0]
                MARCA.write_text(json.dumps(marca, indent=1), encoding='utf-8')
                conn.rollback()
                print('Marca gravada:', {k: v for k, v in marca.items() if k != 'inicio'})
                return 0
            marca = json.loads(MARCA.read_text(encoding='utf-8'))
            seeds = list(itens_dos_seeds())
            cur.execute('select id from public.item_despesa where id > %s and id <> all(%s)', (marca['item_despesa'], seeds))
            itens = [r[0] for r in cur.fetchall()]
            removidos = {}
            for rotulo, sql, params in (
                ('movimentos', 'delete from public.movimento_financeiro where id > %s', [marca['movimento_financeiro']]),
                ('identidades', 'delete from financeiro.recorrencia_competencia where item_despesa_id = any(%s)', [itens]),
                ('compras', 'delete from public.lancamento_agregado where item_despesa_id = any(%s) or cartao_id = any(%s)',
                 [itens, itens]),
                ('contas', 'delete from public.conta where item_despesa_id = any(%s)', [itens]),
                ('itens', 'delete from public.item_despesa where id = any(%s)', [itens]),
                ('chaves', 'delete from financeiro.operacao_despesa where criado_em >= %s::timestamptz', [marca['inicio']]),
            ):
                cur.execute(sql, params)
                removidos[rotulo] = cur.rowcount
            print('Removidos (criados pelos testes):', removidos)
        if args.confirmar:
            conn.commit()
            MARCA.unlink()
            print('CONFIRMADO.')
        else:
            conn.rollback()
            print('SIMULACAO: nada foi gravado (use --confirmar).')
    finally:
        conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
