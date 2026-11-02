"""FIN-CARTOES-MULTIPLOS-01 — procedimento da limpeza seletiva das despesas importadas de cartao (reconstrucao das faturas).

Duas etapas, pelas funcoes do banco (financeiro.previa_limpeza_importacoes e financeiro.limpar_importacoes_cartao), como o
titular do perfil Pessoal (identidade lida de financeiro.perfil_acesso; nenhuma credencial e impressa):

    # 1. previa (sessao SO LEITURA): o inventario vai para o arquivo; nada e alterado
    python scripts/limpeza_importacoes_cartao.py previa --cartao 388 --competencia 2026-11 --saida previa.json

    # 2. execucao, SO COM AUTORIZACAO EXPRESSA: a impressao (hash) da previa conferida e a confirmacao literal
    python scripts/limpeza_importacoes_cartao.py executar --cartao 388 --competencia 2026-11 --hash <hash da previa> \\
        --confirmo "LIMPAR IMPORTACOES"

A conexao vem de CF_REMOTO_DSN (ou --dsn). A execucao refaz a previa sob as travas e recusa se ela mudou, se ha registro
protegido (fatura paga ou consolidada, ocorrencia de recorrencia, credito vinculado) ou se nada e elegivel. Remove so o que
a importacao registrou como seu, numa transacao, e guarda as linhas removidas na operacao (auditoria). Movimentos, saldos,
pagamentos, faturas, recorrencias, previsoes e compras manuais nao sao tocados. A reimportacao do arquivo reconstroi a
fatura, com a Categoria de Despesa que cada compra tinha.
"""
import argparse
import json
import os
import sys
import uuid

import psycopg2
import psycopg2.extras

FRASE = 'LIMPAR IMPORTACOES'


def conectar(dsn, leitura):
    conn = psycopg2.connect(dsn)
    conn.set_session(readonly=leitura, autocommit=False)
    return conn


def como_titular(cur):
    cur.execute("select a.user_id::text u from financeiro.perfil_acesso a join public.perfil_financeiro p "
                "on p.id = a.perfil_financeiro_id where p.nome = 'Pessoal' and a.papel = 'TITULAR' and a.pode_gerir")
    linhas = cur.fetchall()
    if len(linhas) != 1:
        raise SystemExit('Titular do perfil Pessoal nao identificado com seguranca: nada feito.')
    cur.execute("select id from public.perfil_financeiro where nome = 'Pessoal'")
    perfil = cur.fetchone()['id']
    cur.execute('set local role authenticated')
    cur.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps({'sub': linhas[0]['u'], 'role': 'authenticated'}),))
    return perfil


def resumo(p):
    t = p['totais']
    print(f"Compras elegiveis: {t['compras_elegiveis']} (R$ {t['valor_compras']:.2f}) | creditos: {t['creditos_elegiveis']} "
          f"(R$ {t['valor_creditos']:.2f}) | protegidos: {t['protegidos']} | origem nao comprovada: {t['nao_comprovadas']}")
    for f in p['por_fatura']:
        print(f"  contrato {f['cartao_id']} {f['mes_fatura']}: {f['compras']} compras R$ {f['total_compras']:.2f}, "
              f"{f['creditos']} creditos R$ {f['total_creditos']:.2f}; valor a pagar R$ {f['valor_a_pagar_atual']:.2f} -> "
              f"R$ {f['valor_a_pagar_depois']:.2f}; previsoes pendentes {f['previsoes_pendentes']}")
    for x in p['protegidos']:
        print(f"  PROTEGIDO {x['tipo']} {x['id']} ({x['motivo']}): {x['descricao']} R$ {x['valor']:.2f}")
    print(f"Executavel: {'sim' if p['executavel'] else 'nao'} | hash: {p['hash']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('etapa', choices=['previa', 'executar'])
    ap.add_argument('--cartao', type=int, help='contrato de cartao (item_despesa); sem ele, todos do perfil')
    ap.add_argument('--competencia', help='AAAA-MM; sem ela, todas')
    ap.add_argument('--saida', help='arquivo JSON da previa')
    ap.add_argument('--hash', help='impressao da previa conferida (execucao)')
    ap.add_argument('--confirmo', help=f'confirmacao literal da execucao: "{FRASE}"')
    ap.add_argument('--dsn', default=os.environ.get('CF_REMOTO_DSN'))
    a = ap.parse_args()
    if not a.dsn:
        raise SystemExit('Informe a conexao (CF_REMOTO_DSN ou --dsn).')
    mes = f'{a.competencia}-01' if a.competencia else None
    if a.etapa == 'executar' and (a.confirmo != FRASE or not a.hash):
        raise SystemExit(f'Execucao recusada: informe --hash da previa conferida e --confirmo "{FRASE}".')
    conn = conectar(a.dsn, leitura=a.etapa == 'previa')
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        perfil = como_titular(cur)
        if a.etapa == 'previa':
            cur.execute('select financeiro.previa_limpeza_importacoes(%s, %s, %s) j', (perfil, a.cartao, mes))
            p = cur.fetchone()['j']
            conn.rollback()
            resumo(p)
            if a.saida:
                with open(a.saida, 'w', encoding='utf-8') as f:
                    json.dump(p, f, ensure_ascii=False, indent=1, default=str)
            return
        cur.execute('select financeiro.limpar_importacoes_cartao(%s, %s, %s, %s, %s) j', (perfil, a.cartao, mes, a.hash, str(uuid.uuid4())))
        r = cur.fetchone()['j']
        conn.commit()
        print(json.dumps(r, ensure_ascii=False, indent=1, default=str))
    except psycopg2.Error as erro:
        conn.rollback()
        raise SystemExit(f'Nada alterado: {erro.diag.message_primary}')
    finally:
        conn.close()


if __name__ == '__main__':
    sys.exit(main())
