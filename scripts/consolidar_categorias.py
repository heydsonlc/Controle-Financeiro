"""FIN-CATEGORIAS-CONSOLIDACAO-01 — incorporacao das Categorias de Despesa redundantes aprovadas (plano fixo de 4 passos).

Pelas funcoes do banco (financeiro.previa_incorporacao_categoria e financeiro.incorporar_categoria), como a conta que
administra o catalogo (unica em financeiro.gestor_catalogo; nenhuma credencial e impressa):

    # 1. previa (sessao SO LEITURA): confere a identidade de cada categoria e grava as quatro previas; nada e alterado
    python scripts/consolidar_categorias.py previa --saida previa.json

    # 2. execucao, SO COM AUTORIZACAO EXPRESSA: a impressao (hash) da previa conferida e a confirmacao literal
    python scripts/consolidar_categorias.py executar --hash <hash da previa> --confirmo "INCORPORAR CATEGORIAS"

A conexao vem de CF_REMOTO_DSN (ou --dsn). Os quatro passos vao numa transacao so: qualquer recusa (previa mudada,
bloqueio, identidade diferente da esperada) desfaz tudo. Repetir a execucao depois de feita devolve o resultado anterior
(chaves derivadas do hash). Nunca rodar entre a limpeza seletiva dos cartoes e a reimportacao (a funcao recusa).
"""
import argparse
import hashlib
import json
import os
import sys
import uuid

import psycopg2
import psycopg2.extras

FRASE = 'INCORPORAR CATEGORIAS'
# (origem, destino, opcoes): ids da producao conferidos no diagnostico FIN-CATEGORIAS-REDUNDANCIA-01
PLANO = [
    (96, 8, {}),
    (98, 5, {'palavras': {'pneu': 6, 'lavajato': 10}}),
    (4, 5, {}),
    (99, 100, {'renomear_destino': 'Assinaturas'}),
]
# identidade esperada de cada id (nome e codigo sistemico): diferente = nada e feito
IDENTIDADE = {96: ('Transporte por App', None), 8: ('Transporte por Aplicativo', 'MOB_APP'),
              98: ('Manutenção de Veículo', None), 5: ('Manutenção Veicular', 'MOB_MANUTENCAO'),
              4: ('Revisão', 'MOB_REVISAO'), 99: ('Assinaturas', None), 100: ('Software e IA', None),
              6: ('Pneus', 'MOB_PNEUS'), 10: ('Lavagem Veicular', 'MOB_LAVAGEM')}


def conectar(dsn, leitura):
    conn = psycopg2.connect(dsn)
    conn.set_session(readonly=leitura, autocommit=False)
    return conn


def como_gestor(cur):
    cur.execute('select user_id::text u from financeiro.gestor_catalogo')
    linhas = cur.fetchall()
    if len(linhas) != 1:
        raise SystemExit('Gestor do catalogo nao identificado com seguranca: nada feito.')
    cur.execute('set local role authenticated')
    cur.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps({'sub': linhas[0]['u'], 'role': 'authenticated'}),))


def conferir_identidade(cur, ja_feitas=()):
    cur.execute('select id, nome, codigo_sistema from public.categoria where id = any(%s)', (list(IDENTIDADE),))
    atuais = {r['id']: (r['nome'], r['codigo_sistema']) for r in cur.fetchall()}
    for cid, esperado in IDENTIDADE.items():
        if cid in ja_feitas:
            continue
        if atuais.get(cid) != esperado:
            raise SystemExit(f'Categoria {cid}: esperado {esperado}, encontrado {atuais.get(cid)}. Nada feito.')


def previas(cur):
    saida = []
    for origem, destino, opcoes in PLANO:
        cur.execute('select financeiro.previa_incorporacao_categoria(%s, %s, %s::jsonb) j', (origem, destino, json.dumps(opcoes)))
        saida.append(cur.fetchone()['j'])
    return saida, hashlib.md5('|'.join(p['hash'] for p in saida).encode()).hexdigest()


def resumo(lista, impressao):
    for (origem, destino, _), p in zip(PLANO, lista):
        refs = ', '.join(f"{r['tabela']}.{r['coluna']}={r['registros']}" for r in p['referencias']) or 'nenhuma'
        print(f"{p['origem']['nome']} ({origem}) -> {p['destino']['nome']} ({destino})"
              f"{' renomeada ' + p['renomear_destino'] if p['renomear_destino'] else ''}: referencias {refs}")
        for w in p['palavras']:
            print(f"    palavra '{w['palavra']}' -> {w['destino']} ({w['destino_id']}) {w['situacao']}")
        for v in p['vinculos'] + p['vinculos_palavras']:
            print(f"    vinculo Categoria do Cartao {v['categoria_cartao']} ({v['categoria_cartao_id']}) "
                  f"{v.get('categoria', '')} {v['situacao']}")
        for b in p['bloqueios']:
            print(f"    BLOQUEIO {b['codigo']}: {b['motivo']}")
    print(f"Executavel: {'sim' if all(p['executavel'] for p in lista) else 'nao'} | hash: {impressao}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('etapa', choices=['previa', 'executar'])
    ap.add_argument('--saida', help='arquivo JSON das previas')
    ap.add_argument('--hash', help='impressao da previa conferida (execucao)')
    ap.add_argument('--confirmo', help=f'confirmacao literal da execucao: "{FRASE}"')
    ap.add_argument('--dsn', default=os.environ.get('CF_REMOTO_DSN'))
    a = ap.parse_args()
    if not a.dsn:
        raise SystemExit('Informe a conexao (CF_REMOTO_DSN ou --dsn).')
    if a.etapa == 'executar' and (a.confirmo != FRASE or not a.hash):
        raise SystemExit(f'Execucao recusada: informe --hash da previa conferida e --confirmo "{FRASE}".')
    conn = conectar(a.dsn, leitura=a.etapa == 'previa')
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if a.etapa == 'executar':
            # ja feita (repetida): as origens nao existem mais; devolve o resultado anterior pelas mesmas chaves
            cur.execute("select count(*) n from financeiro.operacao_catalogo where operacao = 'incorporar_categoria' "
                        "and (resultado ->> 'hash') is not null and chave = any(%s::uuid[])",
                        ([str(uuid.uuid5(uuid.NAMESPACE_URL, f'{a.hash}/{i}')) for i in range(len(PLANO))],))
            if cur.fetchone()['n'] == len(PLANO):
                como_gestor(cur)
                feitas = []
                for i, (origem, destino, opcoes) in enumerate(PLANO):
                    cur.execute('select financeiro.incorporar_categoria(%s, %s, %s::jsonb, %s, %s) j',
                                (origem, destino, json.dumps(opcoes), 'repetida', str(uuid.uuid5(uuid.NAMESPACE_URL, f'{a.hash}/{i}'))))
                    feitas.append(cur.fetchone()['j'])
                conn.rollback()
                print(json.dumps(feitas, ensure_ascii=False, indent=1, default=str))
                return
        conferir_identidade(cur)
        como_gestor(cur)
        lista, impressao = previas(cur)
        if a.etapa == 'previa':
            conn.rollback()
            resumo(lista, impressao)
            if a.saida:
                with open(a.saida, 'w', encoding='utf-8') as f:
                    json.dump({'hash': impressao, 'previas': lista}, f, ensure_ascii=False, indent=1, default=str)
            return
        if a.hash != impressao:
            raise SystemExit('A previa mudou desde a conferencia: rode a previa de novo. Nada alterado.')
        feitas = []
        for i, ((origem, destino, opcoes), p) in enumerate(zip(PLANO, lista)):
            cur.execute('select financeiro.incorporar_categoria(%s, %s, %s::jsonb, %s, %s) j',
                        (origem, destino, json.dumps(opcoes), p['hash'], str(uuid.uuid5(uuid.NAMESPACE_URL, f'{a.hash}/{i}'))))
            feitas.append(cur.fetchone()['j'])
        conn.commit()
        print(json.dumps(feitas, ensure_ascii=False, indent=1, default=str))
    except psycopg2.Error as erro:
        conn.rollback()
        raise SystemExit(f'Nada alterado: {erro.diag.message_primary}')
    finally:
        conn.close()


if __name__ == '__main__':
    sys.exit(main())
