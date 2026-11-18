"""FIN-MULTIUSUARIO-SEGURANCA-01 — regularizacao dos itens de despesa sem perfil (posse explicita).

Exige a migration 20261231090000 aplicada. A posse de cada item e DEMONSTRADA pelos vinculos do proprio registro, nunca
pelo nome de um perfil:
  - contas e compras ligadas ao item: todas tem de ser do mesmo perfil;
  - item de parcela de consorcio: todos os contratos de consorcio a que a parcela corresponde tem de ser do mesmo perfil.
Um item so e atribuido quando ha pelo menos uma evidencia e TODAS apontam o mesmo perfil, que tem de ser o informado em
--perfil e ter dono definido. Item sem evidencia ou com evidencias divergentes NAO e atribuido: e listado para decisao.
So a coluna perfil_financeiro_id do item muda. Nenhum valor, vencimento, pagamento, conta, compra ou id e tocado.

    # 1. previa (sessao SOMENTE LEITURA): evidencias de cada item e a impressao do estado
    python scripts/regularizar_itens_sem_perfil.py previa --perfil 1 --saida previa.json

    # 2. execucao, SO COM AUTORIZACAO EXPRESSA: a impressao conferida e a confirmacao literal (uma transacao)
    python scripts/regularizar_itens_sem_perfil.py executar --perfil 1 --hash <impressao> --confirmo "REGULARIZAR ITENS" --saida feito.json

    # 3. (futuro) retira a guarda: so quando nao restar NENHUM registro sem perfil, nem no catalogo de categorias, que
    #    hoje e global e ainda e lido pela guarda. Ate o FIN-CADASTROS-PADRAO-01 este passo e recusado.
    python scripts/regularizar_itens_sem_perfil.py retirar-guarda --confirmo "RETIRAR GUARDA"

    # reversao: devolve os itens ao estado anterior (sem perfil) e a guarda que havia
    python scripts/regularizar_itens_sem_perfil.py reverter --feito feito.json --confirmo "REVERTER ITENS"

A conexao vem de CF_REMOTO_DSN (ou --dsn). Nenhuma credencial e impressa.
"""
import argparse
import hashlib
import json
import os
import sys
import uuid

import psycopg2
import psycopg2.extras

FRASES = {'executar': 'REGULARIZAR ITENS', 'reverter': 'REVERTER ITENS', 'retirar-guarda': 'RETIRAR GUARDA'}


def todos(cur, sql, params=()):
    cur.execute(sql, params)
    return [dict(r) for r in cur.fetchall()]


def estado(cur, perfil):
    """Itens sem perfil, as evidencias de posse de cada um e a impressao (SHA-256) desse estado."""
    dono = todos(cur, 'select id, user_id::text dono, ativo from public.perfil_financeiro where id = %s', (perfil,))
    if not dono or not dono[0]['dono']:
        raise SystemExit(f'Perfil {perfil}: inexistente ou sem dono definido. Nada feito.')
    itens = todos(cur, """
        select i.id, i.tipo, i.ativo, md5(i::text) retrato,
               (select coalesce(array_agg(distinct c.perfil_financeiro_id order by c.perfil_financeiro_id), '{}') from public.conta c
                 where c.item_despesa_id = i.id) perfis_das_contas,
               (select count(*) from public.conta c where c.item_despesa_id = i.id) contas,
               (select coalesce(array_agg(distinct l.perfil_financeiro_id order by l.perfil_financeiro_id), '{}') from public.lancamento_agregado l
                 where i.id in (l.cartao_id, l.item_despesa_id)) perfis_das_compras,
               (select count(*) from public.lancamento_agregado l where i.id in (l.cartao_id, l.item_despesa_id)) compras,
               case when i.tipo = 'Consorcio' then
                   (select coalesce(array_agg(distinct k.perfil_financeiro_id order by k.perfil_financeiro_id), '{}') from public.contrato_consorcio k
                     where financeiro.posicao_parcela_consorcio(i.nome, array[k.nome]) is not null)
               else '{}' end perfis_dos_contratos,
               case when i.tipo = 'Consorcio' then
                   (select coalesce(array_agg(k.id order by k.id), '{}') from public.contrato_consorcio k
                     where financeiro.posicao_parcela_consorcio(i.nome, array[k.nome]) is not null)
               else '{}' end contratos
          from public.item_despesa i where i.perfil_financeiro_id is null order by i.id""")
    atribuir, divergentes = [], []
    for i in itens:
        evidencias = list(i['perfis_das_contas']) + list(i['perfis_das_compras']) + list(i['perfis_dos_contratos'])
        if not evidencias:
            divergentes.append({'id': i['id'], 'tipo': i['tipo'], 'motivo': 'sem evidencia de posse (nenhuma conta, compra ou contrato ligado)'})
        elif None in evidencias:
            divergentes.append({'id': i['id'], 'tipo': i['tipo'], 'motivo': 'ligado a registro tambem sem perfil'})
        elif set(evidencias) != {perfil}:
            divergentes.append({'id': i['id'], 'tipo': i['tipo'], 'motivo': f'evidencias apontam o(s) perfil(is) {sorted(set(evidencias))}'})
        else:
            atribuir.append(i)
    guarda = todos(cur, 'select perfil_financeiro_id p from financeiro.guarda_sem_perfil')
    corpo = json.dumps({'perfil': perfil, 'dono': dono[0]['dono'], 'itens': itens, 'guarda': guarda}, sort_keys=True, default=str)
    return {'impressao': hashlib.sha256(corpo.encode()).hexdigest(), 'perfil': perfil, 'atribuir': atribuir, 'divergentes': divergentes,
            'guarda': guarda[0]['p'] if guarda else None,
            'resumo': {'itens_sem_perfil': len(itens), 'com_posse_demonstrada': len(atribuir), 'divergentes': len(divergentes),
                       'por_tipo': sorted({(i['tipo'], sum(1 for x in itens if x['tipo'] == i['tipo'])) for i in itens}),
                       'contas_ligadas': sum(i['contas'] for i in itens), 'compras_ligadas': sum(i['compras'] for i in itens),
                       'contratos_de_consorcio': sorted({c for i in itens for c in i['contratos']}), 'guarda_atual': guarda[0]['p'] if guarda else None}}


def sem_perfil_restantes(cur):
    """Tabelas de dados com alguma linha sem perfil (o catalogo de categorias nao conta: e global)."""
    saida = {}
    for t in todos(cur, """select table_schema || '.' || table_name t from information_schema.columns
                            where column_name = 'perfil_financeiro_id' and table_schema in ('public', 'financeiro')
                              and table_schema || '.' || table_name not in ('public.categoria', 'financeiro.guarda_sem_perfil') order by 1"""):
        esq, nome = t['t'].split('.')
        n = todos(cur, f'select count(*) n from {esq}."{nome}" where perfil_financeiro_id is null')[0]['n']
        if n:
            saida[t['t']] = n
    # consorcios antigos sem perfil tambem dependem da guarda
    return saida


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('etapa', choices=['previa', 'executar', 'retirar-guarda', 'reverter'])
    ap.add_argument('--perfil', type=int, help='perfil que as evidencias tem de apontar')
    ap.add_argument('--saida', help='arquivo JSON do resultado')
    ap.add_argument('--hash', help='impressao da previa conferida (execucao)')
    ap.add_argument('--feito', help='arquivo JSON gravado pela execucao (reversao)')
    ap.add_argument('--confirmo', help='confirmacao literal da etapa')
    ap.add_argument('--por', default='titular', help='quem executa (auditoria)')
    ap.add_argument('--dsn', default=os.environ.get('CF_REMOTO_DSN'))
    a = ap.parse_args(argv)
    if not a.dsn:
        raise SystemExit('Informe a conexao (CF_REMOTO_DSN ou --dsn).')
    if a.etapa in FRASES and a.confirmo != FRASES[a.etapa]:
        raise SystemExit(f'Recusado: informe --confirmo "{FRASES[a.etapa]}".')
    if a.etapa in ('previa', 'executar') and not a.perfil:
        raise SystemExit('Informe --perfil.')
    if a.etapa == 'executar' and not a.hash:
        raise SystemExit('Informe --hash com a impressao da previa conferida.')
    if a.etapa == 'reverter' and not a.feito:
        raise SystemExit('Informe --feito.')
    conn = psycopg2.connect(a.dsn)
    conn.set_session(readonly=a.etapa == 'previa', autocommit=False)
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if a.etapa in ('previa', 'executar'):
            e = estado(cur, a.perfil)
            resultado = {'impressao': e['impressao'], **e['resumo'], 'divergentes_lista': e['divergentes']}
            if a.etapa == 'executar':
                if a.hash != e['impressao']:
                    raise SystemExit('O estado mudou desde a previa conferida: rode a previa de novo. Nada alterado.')
                ids = [i['id'] for i in e['atribuir']]
                cur.execute('update public.item_despesa set perfil_financeiro_id = %s where id = any(%s) and perfil_financeiro_id is null', (a.perfil, ids))
                if cur.rowcount != len(ids):
                    raise SystemExit('Quantidade alterada diferente da previa. Nada alterado.')
                chave = str(uuid.uuid4())
                registros = [{'id': i['id'], 'retrato_anterior': i['retrato']} for i in e['atribuir']]
                cur.execute('insert into financeiro.regularizacao_perfil (chave, executada_por, impressao, perfil_destino, registros) values (%s, %s, %s, %s, %s)',
                            (chave, a.por, e['impressao'], a.perfil, json.dumps({'tabela': 'public.item_despesa', 'itens': registros, 'guarda_anterior': e['guarda']})))
                resultado.update({'chave': chave, 'atribuidos': len(ids), 'ids': ids, 'perfil': a.perfil, 'guarda_anterior': e['guarda'],
                                  'sem_perfil_restantes': sem_perfil_restantes(cur)})
                conn.commit()
            else:
                conn.rollback()
        elif a.etapa == 'retirar-guarda':
            restam = sem_perfil_restantes(cur)
            if restam:
                raise SystemExit(f'Ainda ha registros sem perfil: {restam}. A guarda fica como esta. Nada alterado.')
            # O catalogo de categorias (global, sem perfil) ainda e lido pela guarda em tela fiscal: enquanto ele nao tiver
            # dono proprio (FIN-CADASTROS-PADRAO-01), retirar a guarda mudaria o que o titular ve.
            cur.execute('select count(*) n from public.categoria where perfil_financeiro_id is null')
            if cur.fetchone()['n']:
                raise SystemExit('O catalogo de categorias ainda depende da guarda (categorias sem perfil). A guarda fica como esta ate o '
                                 'FIN-CADASTROS-PADRAO-01. Nada alterado.')
            anterior = todos(cur, 'select perfil_financeiro_id p from financeiro.guarda_sem_perfil')
            cur.execute('select financeiro.definir_guarda_sem_perfil(null, %s, %s)', (a.por, 'Nenhum registro sem perfil: guarda retirada'))
            resultado = {'guarda_anterior': anterior[0]['p'] if anterior else None, 'guarda_atual': None}
            conn.commit()
        else:
            with open(a.feito, encoding='utf-8') as f:
                feito = json.load(f)
            reg = todos(cur, 'select * from financeiro.regularizacao_perfil where chave = %s for update', (feito['chave'],))
            if not reg or reg[0]['revertida_em'] is not None:
                raise SystemExit('Regularizacao nao encontrada ou ja revertida. Nada alterado.')
            ids = [i['id'] for i in reg[0]['registros']['itens']]
            cur.execute('update public.item_despesa set perfil_financeiro_id = null where id = any(%s) and perfil_financeiro_id = %s', (ids, reg[0]['perfil_destino']))
            if cur.rowcount != len(ids):
                raise SystemExit('Algum item ja nao esta no perfil de destino: confira antes de reverter. Nada alterado.')
            retratos = {r['id']: r['retrato'] for r in todos(cur, 'select id, md5(i::text) retrato from public.item_despesa i where id = any(%s)', (ids,))}
            diferentes = [i['id'] for i in reg[0]['registros']['itens'] if retratos.get(i['id']) != i['retrato_anterior']]
            if diferentes:
                raise SystemExit(f'Itens alterados depois da regularizacao (nao voltariam ao estado anterior): {diferentes}. Nada alterado.')
            guarda_anterior = reg[0]['registros'].get('guarda_anterior')
            cur.execute('select financeiro.definir_guarda_sem_perfil(%s, %s, %s)', (guarda_anterior, a.por, 'Reversao da regularizacao dos itens sem perfil'))
            cur.execute('update financeiro.regularizacao_perfil set revertida_em = now() where chave = %s', (feito['chave'],))
            resultado = {'chave': feito['chave'], 'revertidos': len(ids), 'guarda_restaurada': guarda_anterior}
            conn.commit()
        print(json.dumps({k: v for k, v in resultado.items() if k not in ('ids',)}, ensure_ascii=False, indent=1, default=str))
        if a.saida:
            with open(a.saida, 'w', encoding='utf-8') as f:
                json.dump(resultado, f, ensure_ascii=False, indent=1, default=str)
        return 0
    except psycopg2.Error as erro:
        conn.rollback()
        raise SystemExit(f'Nada alterado: {erro.diag.message_primary}')
    except SystemExit:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    sys.exit(main())
