"""
FIN-RECORRENCIA-REAL-1 — cenario FICTICIO e temporario de recorrencias no Supabase de teste.

Mesmos dados do E2E local (tests/supabase_local.py: RECORRENCIAS_E2E, CARTAO_E2E), com
ids gerados pelo banco. Atribui ao novo gerador (FIN-RECORRENCIA-T1) SOMENTE o
"Perfil B" temporario; Pessoal e Empresa continuam no padrao (Flask) e nunca sao
atribuidos aqui.

Pre-requisitos, nesta ordem: supabase_perfis_seed_teste.py e supabase_contas_seed_teste.py.
Remover ANTES deles (ordem inversa). A remocao apaga tambem tudo o que os testes
geraram a partir destes itens (contas, compras, identidades, execucoes) e a atribuicao
do gerador com o seu historico.

Recusa: projeto da Calculadora; tabelas novas ja com dados (garante que so o que o
teste criou sera removido). Sem --confirmar, executa e desfaz (rollback).

Uso:
    scripts/supabase_recorrencia_seed_teste.py [--confirmar]
    scripts/supabase_recorrencia_seed_teste.py --remover [--confirmar]
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
from tests.supabase_local import CARTAO_E2E, GERADOR_NOVO_E2E, RECORRENCIAS_E2E  # noqa: E402

ESTADO = RAIZ / 'data' / 'recorrencia_real_1_teste.json'
ESTADO_CONTAS = RAIZ / 'data' / 'contas_real_1_teste.json'
TABELAS_NOVAS_VAZIAS = ('financeiro.recorrencia_competencia', 'financeiro.geracao_execucao',
                        'financeiro.gerador_recorrencia', 'financeiro.gerador_recorrencia_historico')
RESPONSAVEL = 'FIN-RECORRENCIA-REAL-1 (teste)'


def criar(cur):
    if not ESTADO_CONTAS.exists():
        raise SystemExit('Rode antes scripts/supabase_contas_seed_teste.py.')
    contas = json.loads(ESTADO_CONTAS.read_text(encoding='utf-8'))
    perfis, categoria = contas['perfis'], contas['mapa']['201']
    if set(GERADOR_NOVO_E2E) != {'PERFIL_B'}:
        raise SystemExit('So o Perfil B temporario pode ser atribuido ao novo gerador.')
    for tabela in TABELAS_NOVAS_VAZIAS:
        cur.execute(f'select count(*) from {tabela}')
        if cur.fetchone()[0]:
            raise SystemExit(f'{tabela} ja tem dados: nada feito.')
    itens = {}
    for logico, nome, chave, ancora, valor in RECORRENCIAS_E2E:
        cur.execute("insert into public.item_despesa (nome, tipo, perfil_financeiro_id, categoria_id, ativo, recorrente, "
                    "tipo_recorrencia, data_vencimento, valor, meio_pagamento, criado_em) "
                    "values (%s, 'Simples', %s, %s, true, true, 'mensal', %s, %s, 'boleto', now()) returning id",
                    (nome, perfis[chave], categoria, ancora, valor))
        itens[str(logico)] = cur.fetchone()[0]
    logico, nome, chave, dia = CARTAO_E2E
    cur.execute("insert into public.item_despesa (nome, tipo, perfil_financeiro_id, categoria_id, ativo, recorrente, criado_em) "
                "values (%s, 'Agregador', %s, %s, true, false, now()) returning id", (nome, perfis[chave], categoria))
    itens[str(logico)] = cur.fetchone()[0]
    cur.execute('insert into public.config_agregador (item_despesa_id, dia_fechamento, dia_vencimento, criado_em) '
                'values (%s, 25, %s, now()) returning id', (itens[str(logico)], dia))
    config = cur.fetchone()[0]
    for chave in GERADOR_NOVO_E2E:
        cur.execute("select financeiro.definir_gerador_recorrencia(%s, 'NOVO', %s, 'Perfil ficticio do teste real')",
                    (perfis[chave], RESPONSAVEL))
    return {'itens': itens, 'config_agregador': config, 'perfis': perfis,
            'perfis_novo_gerador': [perfis[c] for c in GERADOR_NOVO_E2E]}


def remover(cur, estado):
    itens = list(estado['itens'].values())
    perfis = list(estado['perfis'].values())
    removidos = {}
    comandos = [
        ('identidades', 'delete from financeiro.recorrencia_competencia where item_despesa_id = any(%s)', [itens]),
        ('execucoes', 'delete from financeiro.geracao_execucao where perfil_financeiro_id = any(%s)', [perfis]),
        ('compras', 'delete from public.lancamento_agregado where item_despesa_id = any(%s) or cartao_id = any(%s)',
         [itens, itens]),
        ('contas', 'delete from public.conta where item_despesa_id = any(%s)', [itens]),
        ('config_agregador', 'delete from public.config_agregador where id = %s', [estado['config_agregador']]),
        ('itens', 'delete from public.item_despesa where id = any(%s)', [itens]),
        ('gerador', 'delete from financeiro.gerador_recorrencia where perfil_financeiro_id = any(%s)',
         [estado['perfis_novo_gerador']]),
        ('historico_gerador', 'delete from financeiro.gerador_recorrencia_historico where perfil_financeiro_id = any(%s)',
         [estado['perfis_novo_gerador']]),
    ]
    for rotulo, sql, params in comandos:
        cur.execute(sql, params)
        removidos[rotulo] = cur.rowcount
    for tabela in TABELAS_NOVAS_VAZIAS:  # o teste e o unico usuario dessas tabelas no projeto de teste
        cur.execute(f'select count(*) from {tabela}')
        if cur.fetchone()[0]:
            raise SystemExit(f'{tabela} nao ficou vazia: remocao desfeita.')
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
                print(f"Criados: {len(estado['itens'])} itens ficticios | novo gerador so nos perfis "
                      f"{estado['perfis_novo_gerador']} (Perfil B temporario)")
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
