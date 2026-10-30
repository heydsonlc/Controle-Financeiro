"""
FIN-RECEITAS-DATA-REAL-1 — receitas FICTICIAS e temporarias no Supabase de teste.

Mesmos dados do E2E local (tests/supabase_local.py: RECEITAS_E2E): fontes e previsoes de 11/2026
nos perfis Pessoal, Empresa e no "Perfil B" temporario, e um recebimento parcial (com movimento)
no Pessoal. Pre-requisito: scripts/supabase_perfis_seed_teste.py (usa o Perfil B e a conta
bancaria ficticia "Conta Pessoal (A)"). Remover antes dele.

Recusa: projeto da Calculadora; fonte com o mesmo nome ja existente no perfil (nada
preexistente e tocado). Sem --confirmar, executa e desfaz.

Uso:
    scripts/supabase_receitas_seed_teste.py [--confirmar]
    scripts/supabase_receitas_seed_teste.py --remover [--confirmar]
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
from tests.supabase_local import RECEITAS_E2E  # noqa: E402

ESTADO = RAIZ / 'data' / 'receitas_real_1_teste.json'
ESTADO_PERFIS = RAIZ / 'data' / 'perfis_real_1_teste.json'


def criar(cur):
    if not ESTADO_PERFIS.exists():
        raise SystemExit('Rode antes scripts/supabase_perfis_seed_teste.py.')
    perfis_estado = json.loads(ESTADO_PERFIS.read_text(encoding='utf-8'))
    perfis = {'PESSOAL': perfis_estado['ids_existentes_usados']['Pessoal'],
              'EMPRESA': perfis_estado['ids_existentes_usados']['Empresa'], 'PERFIL_B': perfis_estado['id_perfil_b']}
    cur.execute("select id from public.conta_bancaria where id = any(%s) and nome = 'Conta Pessoal (A)'",
                (perfis_estado['contas'],))
    conta = cur.fetchone()[0]
    estado = {'itens': [], 'orcamentos': [], 'realizadas': [], 'movimentos': []}
    for nome, tipo, chave, recorrente, base, dia, previsto in RECEITAS_E2E:
        cur.execute('select count(*) from public.item_receita where nome = %s and perfil_financeiro_id = %s',
                    (nome, perfis[chave]))
        if cur.fetchone()[0]:
            raise SystemExit(f'Ja existe fonte "{nome}" no perfil: nada feito.')
        cur.execute('insert into public.item_receita (perfil_financeiro_id, nome, tipo, descricao, ativo, valor_base_mensal, '
                    "dia_previsto_pagamento, recorrente, criado_em) values (%s, %s, %s, '', true, %s, %s, %s, now()) "
                    'returning id', (perfis[chave], nome, tipo, base, dia, recorrente))
        item = cur.fetchone()[0]
        estado['itens'].append(item)
        cur.execute("insert into public.receita_orcamento (perfil_financeiro_id, item_receita_id, mes_referencia, "
                    "valor_esperado, periodicidade, criado_em) values (%s, %s, '2026-11-01', %s, %s, now()) returning id",
                    (perfis[chave], item, previsto, 'MENSAL_FIXA' if recorrente else 'UNICA'))
        estado['orcamentos'].append(cur.fetchone()[0])
        if nome == 'Salário (A)':
            cur.execute("insert into public.receita_realizada (perfil_financeiro_id, item_receita_id, data_recebimento, "
                        "valor_recebido, mes_referencia, conta_bancaria_id, criado_em, atualizado_em) values "
                        "(%s, %s, '2026-11-05', 2000, '2026-11-01', %s, now(), now()) returning id", (perfis[chave], item, conta))
            realizada = cur.fetchone()[0]
            estado['realizadas'].append(realizada)
            cur.execute("insert into public.movimento_financeiro (conta_bancaria_id, tipo, valor, descricao, data_movimento, "
                        "receita_realizada_id, origem, criado_em) values (%s, 'CREDITO', 2000, 'Recebimento (teste)', "
                        "'2026-11-05', %s, 'RECEITA', now()) returning id", (conta, realizada))
            estado['movimentos'].append(cur.fetchone()[0])
    return estado


def remover(cur, estado):
    removidos = {}
    for rotulo, sql, ids in (
        ('movimentos', 'delete from public.movimento_financeiro where id = any(%s)', estado['movimentos']),
        ('realizadas', 'delete from public.receita_realizada where id = any(%s)', estado['realizadas']),
        ('orcamentos', 'delete from public.receita_orcamento where item_receita_id = any(%s)', estado['itens']),
        ('itens', 'delete from public.item_receita where id = any(%s)', estado['itens']),
    ):
        cur.execute(sql, (ids,))
        removidos[rotulo] = cur.rowcount
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
                print(f"Criados: {len(estado['itens'])} fontes, {len(estado['orcamentos'])} previsoes, "
                      f"{len(estado['realizadas'])} recebimento ficticio")
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
