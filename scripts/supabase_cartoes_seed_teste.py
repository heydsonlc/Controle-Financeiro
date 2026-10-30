"""
FIN-CARTOES-REAL-1 — cartao FICTICIO e temporario no Supabase de teste.

Mesmo dado do E2E local (tests/supabase_local.py: CARTAO_INATIVO_E2E): um cartao INATIVO no
"Perfil B" temporario, com numero ficticio, para conferir que a tela mostra so o final do numero.
Nada vai para os perfis definitivos Pessoal e Empresa. Pre-requisito:
scripts/supabase_perfis_seed_teste.py. Remover antes dele.

Recusa: projeto da Calculadora; cartao com o mesmo nome ja existente no perfil. Sem --confirmar,
executa e desfaz.

Uso:
    scripts/supabase_cartoes_seed_teste.py [--confirmar]
    scripts/supabase_cartoes_seed_teste.py --remover [--confirmar]
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

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / 'scripts'))

from supabase_contas_seed_teste import conectar  # noqa: E402
from tests.supabase_local import CARTAO_INATIVO_E2E  # noqa: E402

ESTADO = RAIZ / 'data' / 'cartoes_real_1_teste.json'
ESTADO_PERFIS = RAIZ / 'data' / 'perfis_real_1_teste.json'


def criar(cur):
    if not ESTADO_PERFIS.exists():
        raise SystemExit('Rode antes scripts/supabase_perfis_seed_teste.py.')
    perfil_b = json.loads(ESTADO_PERFIS.read_text(encoding='utf-8'))['id_perfil_b']
    _, nome, chave, fechamento, vencimento = CARTAO_INATIVO_E2E
    assert chave == 'PERFIL_B'
    cur.execute("select count(*) from public.item_despesa where nome = %s and perfil_financeiro_id = %s", (nome, perfil_b))
    if cur.fetchone()[0]:
        raise SystemExit(f'Ja existe "{nome}" no perfil: nada feito.')
    cur.execute("insert into public.item_despesa (nome, tipo, perfil_financeiro_id, ativo, recorrente, criado_em) "
                "values (%s, 'Agregador', %s, false, false, now()) returning id", (nome, perfil_b))
    item = cur.fetchone()[0]
    cur.execute('insert into public.config_agregador (item_despesa_id, dia_fechamento, dia_vencimento, numero_cartao, '
                "criado_em) values (%s, %s, %s, '5555 6666 7777 8888', now())", (item, fechamento, vencimento))
    return {'itens': [item], 'perfil': perfil_b}


def remover(cur, estado):
    cur.execute('delete from public.config_agregador where item_despesa_id = any(%s)', (estado['itens'],))
    configs = cur.rowcount
    cur.execute('delete from public.item_despesa where id = any(%s) and perfil_financeiro_id = %s',
                (estado['itens'], estado['perfil']))
    return {'configs': configs, 'itens': cur.rowcount}


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
                print('Criado: 1 cartao inativo no Perfil B')
        if args.confirmar:
            conn.commit()
            if args.remover:
                ESTADO.unlink()
            else:
                ESTADO.write_text(json.dumps(estado, indent=1), encoding='utf-8')
            print('CONFIRMADO: alteracoes gravadas.')
        else:
            conn.rollback()
            print('SIMULACAO: nada foi gravado (use --confirmar).')
    finally:
        conn.close()


if __name__ == '__main__':
    sys.exit(main())
