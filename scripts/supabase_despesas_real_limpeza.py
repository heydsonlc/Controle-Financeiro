"""
FIN-DESPESAS-REAL-1 / FIN-RECEITAS-DATA-REAL-1 / FIN-CARTOES-REAL-1 — limpeza do que os TESTES criaram (alem dos seeds)
no Supabase de teste.

`marcar` (antes dos seeds): guarda o maior id de cada tabela financeira e o instante inicial.
`remover` (depois dos testes, ANTES dos removedores dos seeds): apaga so o que os testes criaram
pela tela ou pela API — despesas, recorrencias e cartoes novos (com contas/faturas, compras,
configuracao, limites, identidades, dispensas e chaves de idempotencia), categorias do cartao e
vinculos de teste, movimentos de teste e ocorrencias de recorrencia rejeitada (public.recorrencia_rejeicao)
dos itens e cartoes de teste. Linhas dos seeds ficam para os
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
TABELAS = ('item_despesa', 'conta', 'lancamento_agregado', 'movimento_financeiro',
           'item_receita', 'receita_orcamento', 'receita_realizada', 'categoria_cartao')
MARCADOR_CARTAO = '%[teste FIN-CARTOES-REAL-1]%'


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
    cartoes = RAIZ / 'data' / 'cartoes_real_1_teste.json'
    if cartoes.exists():
        ids |= set(json.loads(cartoes.read_text(encoding='utf-8'))['itens'])
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
            cur.execute("select to_regclass('public.recorrencia_rejeicao') is not null")
            com_rejeicao = cur.fetchone()[0]  # so existe depois da migration 20261030090000
            removidos = {}
            for rotulo, sql, params in (
                # FIN-CARTOES-RECORRENCIA-PENDENCIA-1: explicito (alem do cascade do item) para cobrir recorrencias dos
                # seeds rejeitadas em faturas de cartoes de teste.
                ('ocorrencias_recorrencia', 'delete from public.recorrencia_rejeicao where item_despesa_id = any(%s) '
                 'or cartao_id = any(%s)', [itens, itens] if com_rejeicao else [None]),
                ('movimentos', 'delete from public.movimento_financeiro where id > %s', [marca['movimento_financeiro']]),
                ('identidades', 'delete from financeiro.recorrencia_competencia where item_despesa_id = any(%s)', [itens]),
                ('compras', 'delete from public.lancamento_agregado where item_despesa_id = any(%s) or cartao_id = any(%s)',
                 [itens, itens]),
                ('contas', 'delete from public.conta where item_despesa_id = any(%s)', [itens]),
                # Cartoes (FIN-CARTOES-REAL-1): configuracao e limites dos cartoes criados pelos testes.
                ('limites', 'delete from public.cartao_categoria_limite where cartao_id = any(%s)', [itens]),
                ('configs_cartao', 'delete from public.config_agregador where item_despesa_id = any(%s)', [itens]),
                ('itens', 'delete from public.item_despesa where id = any(%s)', [itens]),
                ('chaves', 'delete from financeiro.operacao_despesa where criado_em >= %s::timestamptz', [marca['inicio']]),
                # Receitas (FIN-RECEITAS): tudo acima da marca e de teste (seed ficticio ou criado pelos testes).
                ('receitas_realizadas', 'delete from public.receita_realizada where id > %s',
                 [marca.get('receita_realizada', 0)]),
                ('receitas_previsoes', 'delete from public.receita_orcamento where id > %s or item_receita_id > %s',
                 [marca.get('receita_orcamento', 0), marca.get('item_receita', 0)]),
                ('receitas_fontes', 'delete from public.item_receita where id > %s', [marca.get('item_receita', 0)]),
                ('chaves_receita', 'delete from financeiro.operacao_receita where criado_em >= %s::timestamptz',
                 [marca['inicio']]),
                ('chaves_cartao', 'delete from financeiro.operacao_cartao where criado_em >= %s::timestamptz',
                 [marca['inicio']]),
                # Categorias do cartao criadas pelos testes reais: so as com o marcador (as do seed de contas
                # tambem ficam acima da marca e sao removidas pelo proprio seed).
                ('limites_teste', 'delete from public.cartao_categoria_limite where categoria_cartao_id in '
                 '(select id from public.categoria_cartao where id > %s and nome like %s)',
                 [marca.get('categoria_cartao'), MARCADOR_CARTAO]),
                ('vinculos_categoria', 'delete from public.categoria_cartao_despesa where categoria_cartao_id in '
                 '(select id from public.categoria_cartao where id > %s and nome like %s)',
                 [marca.get('categoria_cartao'), MARCADOR_CARTAO]),
                ('categorias_cartao', 'delete from public.categoria_cartao where id > %s and nome like %s',
                 [marca.get('categoria_cartao'), MARCADOR_CARTAO]),
            ):
                if any(x is None for x in params):
                    continue
                cur.execute(sql, params)
                removidos[rotulo] = cur.rowcount
            print('Removidos (criados pelos testes):', removidos)
            if com_rejeicao:
                cur.execute('select count(*) from public.recorrencia_rejeicao where item_despesa_id = any(%s) '
                            'or cartao_id = any(%s)', (itens, itens))
                print('Conferencia: ocorrencias de recorrencia dos itens/cartoes de teste restantes =', cur.fetchone()[0])
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
