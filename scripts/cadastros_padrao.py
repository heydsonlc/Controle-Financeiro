"""FIN-CADASTROS-PADRAO-01 — dados iniciais do catalogo padrao (plano conferido por previa, reversivel).

Exige a migration 20270101090000 aplicada. Nao cria nem altera categoria de despesa, despesa, compra, valor ou pagamento.
O que faz, numa transacao:
  1. MODELO de categorias de cartao: uma linha do modelo para cada categoria de cartao ATIVA do perfil de referencia, com os
     vinculos ativos dela a categorias de despesa padrao. As categorias do perfil de referencia NAO sao recriadas: so ganham
     a marca de origem (mesmo id, mesmos vinculos, mesmos limites, mesmas compras).
  2. Com --preencher-perfis: cada outro perfil existente recebe as categorias de cartao padrao que ainda nao tem (so
     acrescenta; repetir nao duplica).
  3. Palavras-chave pessoais (--pessoais arquivo.json: [{"categoria_id": n, "palavra": "..."}]): cada uma SAI do catalogo
     padrao (fica inativa la) e ENTRA como palavra propria do dono do perfil de referencia, na mesma categoria. Para ele, a
     regra efetiva nao muda; os demais usuarios deixam de recebe-la.

    python scripts/cadastros_padrao.py previa --perfil-referencia 1 [--pessoais arquivo.json] [--preencher-perfis] --saida previa.json
    python scripts/cadastros_padrao.py executar --perfil-referencia 1 [...] --hash <impressao> --confirmo "CADASTROS PADRAO" --saida feito.json
    python scripts/cadastros_padrao.py reverter --feito feito.json --confirmo "REVERTER CADASTROS"

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

FRASES = {'executar': 'CADASTROS PADRAO', 'reverter': 'REVERTER CADASTROS'}


def todos(cur, sql, params=()):
    cur.execute(sql, params)
    return [dict(r) for r in cur.fetchall()]


def ler_pessoais(caminho):
    if not caminho:
        return []
    with open(caminho, encoding='utf-8') as f:
        lista = json.load(f)
    return sorted({(int(x['categoria_id']), ' '.join(str(x['palavra']).lower().split())) for x in lista})


def estado(cur, referencia, pessoais, preencher):
    perfil = todos(cur, 'select id, user_id::text dono from public.perfil_financeiro where id = %s', (referencia,))
    if not perfil or not perfil[0]['dono']:
        raise SystemExit(f'Perfil de referencia {referencia}: inexistente ou sem dono. Nada feito.')
    if todos(cur, 'select 1 from financeiro.categoria_cartao_padrao limit 1'):
        raise SystemExit('O modelo de categorias de cartao ja existe: este roteiro so faz a carga inicial. Nada feito.')
    cartao = todos(cur, """select cc.id, cc.nome, cc.descricao, cc.cor, cc.icone, cc.padrao_id from public.categoria_cartao cc
                            where cc.perfil_financeiro_id = %s and cc.ativo order by cc.nome, cc.id""", (referencia,))
    if not cartao:
        raise SystemExit('O perfil de referencia nao tem categoria de cartao ativa. Nada feito.')
    vinculos = todos(cur, """select v.categoria_cartao_id, v.categoria_id from public.categoria_cartao_despesa v
                               join public.categoria c on c.id = v.categoria_id and c.user_id is null
                              where v.perfil_financeiro_id = %s and v.ativo and v.categoria_cartao_id = any(%s) order by 1, 2""",
                     (referencia, [c['id'] for c in cartao]))
    outros = todos(cur, """select p.id, (select count(*) from public.categoria_cartao cc where cc.perfil_financeiro_id = p.id) categorias
                             from public.perfil_financeiro p where p.id <> %s order by p.id""", (referencia,)) if preencher else []
    palavras = []
    for cat, palavra in pessoais:
        linha = todos(cur, """select p.id, p.categoria_id, lower(btrim(p.palavra)) palavra from public.categoria_palavra_chave p
                               where p.categoria_id = %s and lower(btrim(p.palavra)) = %s and p.ativo""", (cat, palavra))
        if len(linha) != 1:
            raise SystemExit(f'Palavra-chave pessoal nao encontrada, ativa e unica no catalogo: categoria {cat}, "{palavra}". Nada feito.')
        palavras.append(linha[0])
    catalogo = todos(cur, """select (select count(*) from public.categoria where user_id is null) categorias_padrao,
                                    (select count(*) from public.categoria where user_id is not null) categorias_particulares,
                                    (select count(*) from public.categoria_palavra_chave where ativo) palavras_padrao_ativas,
                                    (select count(*) from financeiro.palavra_chave_usuario) ajustes_de_usuarios""")[0]
    corpo = json.dumps({'referencia': referencia, 'dono': perfil[0]['dono'], 'cartao': cartao, 'vinculos': vinculos, 'outros': outros,
                        'palavras': palavras, 'catalogo': catalogo}, sort_keys=True, default=str)
    return {'impressao': hashlib.sha256(corpo.encode()).hexdigest(), 'dono': perfil[0]['dono'], 'cartao': cartao, 'vinculos': vinculos,
            'outros': outros, 'palavras': palavras,
            'resumo': {'categorias_de_cartao_no_modelo': len(cartao), 'vinculos_no_modelo': len(vinculos),
                       'perfis_a_preencher': [o['id'] for o in outros], 'palavras_pessoais': len(palavras), **catalogo}}


def executar(cur, e, referencia):
    feito = {'chave': str(uuid.uuid4()), 'impressao': e['impressao'], 'referencia': referencia, 'dono': e['dono'], 'modelo': [], 'preenchidos': [],
             'palavras': []}
    for ordem, c in enumerate(e['cartao'], start=1):
        cur.execute('insert into financeiro.categoria_cartao_padrao (nome, descricao, cor, icone, ativo, ordem) values (%s, %s, %s, %s, true, %s) returning id',
                    (c['nome'], c['descricao'], c['cor'] or '#6c757d', c['icone'], ordem))
        padrao_id = cur.fetchone()['id']
        cur.execute('update public.categoria_cartao set padrao_id = %s where id = %s and padrao_id is null', (padrao_id, c['id']))
        if cur.rowcount != 1:
            raise SystemExit(f'Categoria de cartao {c["id"]} mudou desde a previa. Nada alterado.')
        despesas = [v['categoria_id'] for v in e['vinculos'] if v['categoria_cartao_id'] == c['id']]
        for cat in despesas:
            cur.execute('insert into financeiro.categoria_cartao_padrao_despesa (padrao_id, categoria_id) values (%s, %s)', (padrao_id, cat))
        feito['modelo'].append({'padrao_id': padrao_id, 'categoria_cartao_id': c['id'], 'despesas': despesas})
    for o in e['outros']:
        antes = {r['id'] for r in todos(cur, 'select id from public.categoria_cartao where perfil_financeiro_id = %s', (o['id'],))}
        vinc_antes = {r['id'] for r in todos(cur, 'select id from public.categoria_cartao_despesa where perfil_financeiro_id = %s', (o['id'],))}
        adotadas_antes = {r['id'] for r in todos(cur, 'select id from public.categoria_cartao where perfil_financeiro_id = %s and padrao_id is not null', (o['id'],))}
        cur.execute('select financeiro.inicializar_categorias_cartao(%s) r', (o['id'],))
        r = cur.fetchone()['r']
        criadas = sorted({x['id'] for x in todos(cur, 'select id from public.categoria_cartao where perfil_financeiro_id = %s', (o['id'],))} - antes)
        adotadas = sorted({x['id'] for x in todos(cur, 'select id from public.categoria_cartao where perfil_financeiro_id = %s and padrao_id is not null',
                                                  (o['id'],))} - adotadas_antes - set(criadas))
        vinculos = sorted({x['id'] for x in todos(cur, 'select id from public.categoria_cartao_despesa where perfil_financeiro_id = %s', (o['id'],))} - vinc_antes)
        feito['preenchidos'].append({'perfil_id': o['id'], 'resultado': r, 'categorias_criadas': criadas, 'categorias_adotadas': adotadas, 'vinculos_criados': vinculos})
    for p in e['palavras']:
        cur.execute("update public.categoria_palavra_chave set ativo = false, updated_at = now() at time zone 'utc' where id = %s and ativo", (p['id'],))
        cur.execute("insert into financeiro.palavra_chave_usuario (user_id, tipo, palavra, categoria_id) values (%s, 'NOVA', %s, %s) returning id",
                    (e['dono'], p['palavra'], p['categoria_id']))
        feito['palavras'].append({'padrao_id': p['id'], 'ajuste_id': cur.fetchone()['id'], 'categoria_id': p['categoria_id'], 'palavra': p['palavra']})
    cur.execute('insert into financeiro.operacao_catalogo (chave, user_id, operacao, resultado) values (%s, %s, %s, %s)',
                (feito['chave'], e['dono'], 'cadastros_padrao_carga_inicial', json.dumps(feito)))
    return feito


def reverter(cur, feito):
    reg = todos(cur, "select resultado from financeiro.operacao_catalogo where chave = %s and operacao = 'cadastros_padrao_carga_inicial' for update", (feito['chave'],))
    if not reg:
        raise SystemExit('Carga inicial nao encontrada. Nada alterado.')
    if todos(cur, "select 1 from financeiro.operacao_catalogo where operacao = 'cadastros_padrao_reversao' and resultado ->> 'origem' = %s", (feito['chave'],)):
        raise SystemExit('Carga inicial ja revertida. Nada alterado.')
    f = reg[0]['resultado']
    for p in f['palavras']:
        cur.execute("delete from financeiro.palavra_chave_usuario where id = %s and user_id = %s and tipo = 'NOVA' and palavra = %s and categoria_id = %s",
                    (p['ajuste_id'], f['dono'], p['palavra'], p['categoria_id']))
        if cur.rowcount != 1:
            raise SystemExit(f'A palavra propria "{p["palavra"]}" foi alterada depois da carga: confira antes de reverter. Nada alterado.')
        cur.execute("update public.categoria_palavra_chave set ativo = true, updated_at = now() at time zone 'utc' where id = %s", (p['padrao_id'],))
    for o in f['preenchidos']:
        usadas = todos(cur, """select cc.id from public.categoria_cartao cc where cc.id = any(%s)
                                and (exists (select 1 from public.lancamento_agregado l where l.categoria_cartao_id = cc.id)
                                     or exists (select 1 from public.cartao_categoria_limite l where l.categoria_cartao_id = cc.id)
                                     or exists (select 1 from public.item_despesa i where i.categoria_cartao_id = cc.id))""", (o['categorias_criadas'],))
        if usadas:
            raise SystemExit(f'Categorias de cartao criadas no perfil {o["perfil_id"]} ja estao em uso ({[u["id"] for u in usadas]}): nao sao apagadas. Nada alterado.')
        cur.execute('delete from public.categoria_cartao_despesa where id = any(%s)', (o['vinculos_criados'],))
        cur.execute('delete from public.categoria_cartao_despesa where categoria_cartao_id = any(%s)', (o['categorias_criadas'],))
        cur.execute('delete from public.categoria_cartao where id = any(%s)', (o['categorias_criadas'],))
        cur.execute('update public.categoria_cartao set padrao_id = null where id = any(%s)', (o['categorias_adotadas'],))
    cur.execute('update public.categoria_cartao set padrao_id = null where id = any(%s)', ([m['categoria_cartao_id'] for m in f['modelo']],))
    if todos(cur, 'select 1 from public.categoria_cartao where padrao_id is not null limit 1'):
        raise SystemExit('Ha categorias de cartao copiadas do modelo depois da carga (perfis novos): a reversao nao as apaga. Nada alterado.')
    cur.execute('delete from financeiro.categoria_cartao_padrao')
    cur.execute('insert into financeiro.operacao_catalogo (chave, user_id, operacao, resultado) values (%s, %s, %s, %s)',
                (str(uuid.uuid4()), f['dono'], 'cadastros_padrao_reversao', json.dumps({'origem': feito['chave']})))
    return {'origem': feito['chave'], 'modelo_removido': len(f['modelo']), 'palavras_devolvidas': len(f['palavras']), 'perfis_desfeitos': len(f['preenchidos'])}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('etapa', choices=['previa', 'executar', 'reverter'])
    ap.add_argument('--perfil-referencia', type=int)
    ap.add_argument('--pessoais', help='JSON com as palavras-chave que saem do catalogo padrao e ficam so com o dono da referencia')
    ap.add_argument('--preencher-perfis', action='store_true', help='os outros perfis existentes recebem as categorias de cartao padrao')
    ap.add_argument('--saida')
    ap.add_argument('--hash')
    ap.add_argument('--feito')
    ap.add_argument('--confirmo')
    ap.add_argument('--dsn', default=os.environ.get('CF_REMOTO_DSN'))
    a = ap.parse_args(argv)
    if not a.dsn:
        raise SystemExit('Informe a conexao (CF_REMOTO_DSN ou --dsn).')
    if a.etapa in FRASES and a.confirmo != FRASES[a.etapa]:
        raise SystemExit(f'Recusado: informe --confirmo "{FRASES[a.etapa]}".')
    if a.etapa in ('previa', 'executar') and not a.perfil_referencia:
        raise SystemExit('Informe --perfil-referencia.')
    if a.etapa == 'executar' and not a.hash:
        raise SystemExit('Informe --hash com a impressao da previa conferida.')
    if a.etapa == 'reverter' and not a.feito:
        raise SystemExit('Informe --feito.')
    conn = psycopg2.connect(a.dsn)
    conn.set_session(readonly=a.etapa == 'previa', autocommit=False)
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if a.etapa == 'reverter':
            with open(a.feito, encoding='utf-8') as f:
                resultado = reverter(cur, json.load(f))
            conn.commit()
        else:
            e = estado(cur, a.perfil_referencia, ler_pessoais(a.pessoais), a.preencher_perfis)
            if a.etapa == 'previa':
                conn.rollback()
                resultado = {'impressao': e['impressao'], **e['resumo']}
            else:
                if a.hash != e['impressao']:
                    raise SystemExit('O estado mudou desde a previa conferida: rode a previa de novo. Nada alterado.')
                resultado = executar(cur, e, a.perfil_referencia)
                conn.commit()
        print(json.dumps({k: v for k, v in resultado.items() if k not in ('modelo', 'palavras', 'preenchidos')}, ensure_ascii=False, indent=1, default=str))
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
