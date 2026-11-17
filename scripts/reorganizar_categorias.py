"""FIN-CATEGORIAS-REORGANIZACAO-01 — reorganizacao das Categorias de Despesa (plano fixo, aprovado pelo titular).

Pelas funcoes do banco, como a conta que administra o catalogo (unica em financeiro.gestor_catalogo; nenhuma credencial
e impressa). Exige a migration 20261229090000 aplicada.

    # 1. previa (sessao SO LEITURA): confere a identidade de cada registro e imprime a impressao do estado
    python scripts/reorganizar_categorias.py previa --saida previa.json

    # 2. execucao, SO COM AUTORIZACAO EXPRESSA: a impressao da previa conferida e a confirmacao literal
    python scripts/reorganizar_categorias.py executar --hash <impressao> --confirmo "REORGANIZAR CATEGORIAS" --saida feito.json

    # 3. reversao (se necessaria): desfaz a execucao registrada em feito.json, na ordem inversa
    python scripts/reorganizar_categorias.py reverter --feito feito.json --confirmo "REVERTER CATEGORIAS"

A conexao vem de CF_REMOTO_DSN (ou --dsn). Cada etapa vai numa transacao so: qualquer recusa (estado mudado, bloqueio,
identidade diferente da esperada) desfaz tudo. O que o plano faz, nesta ordem:
  1. cria Poupanca Programada, Clubes e Associacoes, Atividades Esportivas e Doacoes (criar_categoria);
  2. desativa as oito palavras-chave genericas de Servicos gerais (95) e incorpora 95 em Manutencao residencial (94)
     pelo procedimento oficial (previa_incorporacao_categoria / incorporar_categoria);
  3. palavras-chave: sai "outros" e "diversos" de Outros; "streaming" deixa de decidir categoria; "netflix" fica em
     Assinaturas; entram os termos especificos das categorias novas e de Manutencao residencial (criar/remover_palavra_chave);
  4. natureza gerencial: Poupanca Programada = APORTE; Outros = NAO_DEFINIDO; as outras tres novas = CONSUMO;
  5. reclassifica so a categoria (reclassificar_categorias): financiamento 463 -> Moradia; 386 -> Atividades
     Extra-Curriculares; 384 -> Atividades Esportivas; 464 -> Clubes e Associacoes; 479 -> Doacoes; as parcelas dos
     consorcios 18 e 19 -> Poupanca Programada; compras 616 -> Impostos e Taxas, 615 e 614 -> Assinaturas.
FORA do plano, por decisao do titular (o roteiro confere que continuam identicos): compras 718 e 719, consorcios
inativos 11, 12, 15, 16 e 17, o emprestimo em Outros, Servicos domesticos (93) e as demais compras em Outros.
Nenhum valor, vencimento, pagamento, fatura, movimento ou saldo e tocado: so categoria, palavras-chave e natureza.
"""
import argparse
import hashlib
import json
import os
import sys
import uuid

import psycopg2
import psycopg2.extras

FRASE, FRASE_REVERSAO = 'REORGANIZAR CATEGORIAS', 'REVERTER CATEGORIAS'
NOVAS = [  # (chave do plano, nome, descricao, natureza)
    ('poupanca', 'Poupança Programada', 'Aportes periódicos para formação de capital, com resgate posterior.', 'APORTE'),
    ('clubes', 'Clubes e Associações', 'Mensalidades de clubes, associações e entidades de participação voluntária.', 'CONSUMO'),
    ('esportes', 'Atividades Esportivas', 'Mensalidades e pagamentos regulares de prática esportiva.', 'CONSUMO'),
    ('doacoes', 'Doações', 'Doações e contribuições voluntárias, sem contraprestação.', 'CONSUMO'),
]
OUTROS, GERAIS, MANUTENCAO, DOMESTICOS, ASSINATURAS, ENTRETENIMENTO, IMPOSTOS, MORADIA, EXTRA = 107, 95, 94, 93, 100, 108, 102, 89, 110
# identidade esperada: diferente = nada e feito
CATEGORIAS = {MORADIA: 'Moradia', DOMESTICOS: 'Serviços domésticos', MANUTENCAO: 'Manutenção residencial', GERAIS: 'Serviços gerais',
              ASSINATURAS: 'Assinaturas', IMPOSTOS: 'Impostos e Taxas', OUTROS: 'Outros', ENTRETENIMENTO: 'Entretenimento',
              EXTRA: 'Atividades Extra-Curriculares'}
ITENS = {463: (None, MORADIA, 'Financiamento'), 386: (OUTROS, EXTRA, 'Simples'), 384: (OUTROS, 'esportes', 'Simples'),
         464: (OUTROS, 'clubes', 'Simples'), 479: (OUTROS, 'doacoes', 'Simples')}  # id: (de, para, tipo)
CONSORCIOS = (18, 19)
COMPRAS = {616: (IMPOSTOS, 'IOF'), 615: (ASSINATURAS, 'SUPABASE'), 614: (ASSINATURAS, 'GOOGLE ONE')}  # id: (para, trecho da descricao)
INTOCADAS = (718, 719)
PALAVRAS_SAEM = {OUTROS: ['outros', 'diversos'], ASSINATURAS: ['streaming'], ENTRETENIMENTO: ['streaming', 'netflix']}
PALAVRAS_ENTRAM = {MANUTENCAO: ['higienizacao de sofa', 'higienização de sofá', 'higienizacao de estofados', 'higienização de estofados',
                                'limpeza de estofados', 'manutencao de ar condicionado', 'manutenção de ar-condicionado',
                                'reparo residencial', 'reparos residenciais'],
                   ASSINATURAS: ['netflix'], IMPOSTOS: ['iof'],
                   'clubes': ['clube dos oficiais'], 'esportes': ['futebol', 'escolinha de futebol'], 'doacoes': ['doacao', 'doação']}


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


def um(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchone()


def todos(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchall()


def parcelas_dos_consorcios(cur):
    """Itens de parcela (tipo Consorcio) de cada contrato vigente, pelo vinculo do banco (nome do contrato)."""
    saida = {}
    for cid in CONSORCIOS:
        c = um(cur, 'select id, nome, ativo, numero_parcelas from public.contrato_consorcio where id = %s', (cid,))
        if not c or not c['ativo']:
            raise SystemExit(f'Consorcio {cid}: nao encontrado ou inativo. Nada feito.')
        itens = todos(cur, "select i.id, i.categoria_id from public.item_despesa i where i.tipo = 'Consorcio' "
                           "and financeiro.posicao_parcela_consorcio(i.nome, array[%s]) is not null order by i.id", (c['nome'],))
        if len(itens) != c['numero_parcelas']:
            raise SystemExit(f"Consorcio {cid}: {len(itens)} itens de parcela para {c['numero_parcelas']} parcelas. Nada feito.")
        saida[cid] = itens
    return saida


def estado(cur):
    """Identidade de tudo o que o plano toca ou deve preservar e a impressao (SHA-256) desse estado."""
    cats = {r['id']: r['nome'] for r in todos(cur, 'select id, nome from public.categoria where id = any(%s)', (list(CATEGORIAS),))}
    for cid, nome in CATEGORIAS.items():
        if cats.get(cid) != nome:
            raise SystemExit(f'Categoria {cid}: esperado {nome!r}, encontrado {cats.get(cid)!r}. Nada feito.')
    existentes = {r['n'] for r in todos(cur, 'select lower(nome) n from public.categoria')}
    for _, nome, _, _ in NOVAS:
        if nome.lower() in existentes:
            raise SystemExit(f'Ja existe a categoria {nome!r}: confira antes de criar. Nada feito.')
    if 'ajustes de saldo' in existentes or 'ajuste de saldo' in existentes:
        raise SystemExit('Existe uma categoria de ajustes de saldo: fora do plano aprovado. Nada feito.')
    itens = {r['id']: r for r in todos(cur, 'select id, nome, tipo, categoria_id, valor::text valor from public.item_despesa where id = any(%s)', (list(ITENS),))}
    for iid, (de, _, tipo) in ITENS.items():
        if iid not in itens or itens[iid]['tipo'] != tipo or itens[iid]['categoria_id'] != de:
            raise SystemExit(f'Item {iid}: esperado tipo {tipo} na categoria {de}, encontrado {itens.get(iid)}. Nada feito.')
    parcelas = parcelas_dos_consorcios(cur)
    for cid, lista in parcelas.items():
        if any(p['categoria_id'] != OUTROS for p in lista):
            raise SystemExit(f'Consorcio {cid}: ha parcela fora de Outros. Nada feito.')
    compras = {r['id']: r for r in todos(cur, 'select id, descricao, categoria_id, valor::text valor, mes_fatura::text mes_fatura, cartao_id '
                                              'from public.lancamento_agregado where id = any(%s)', (list(COMPRAS) + list(INTOCADAS),))}
    for lid, (_, trecho) in COMPRAS.items():
        if lid not in compras or compras[lid]['categoria_id'] != OUTROS or trecho not in (compras[lid]['descricao'] or '').upper():
            raise SystemExit(f'Compra {lid}: esperada em Outros com "{trecho}" na descricao. Nada feito.')
    for lid in INTOCADAS:
        if lid not in compras or compras[lid]['categoria_id'] != OUTROS:
            raise SystemExit(f'Compra {lid}: esperada em Outros. Nada feito.')
    todos_itens = list(ITENS) + [p['id'] for lista in parcelas.values() for p in lista]
    contas = todos(cur, 'select id, item_despesa_id, valor::text valor, status_pagamento, mes_referencia::text mes from public.conta '
                        'where item_despesa_id = any(%s) order by id', (todos_itens,))
    palavras = todos(cur, 'select id, categoria_id, palavra, ativo from public.categoria_palavra_chave order by id')
    em_outros = todos(cur, "select 'item' t, id from public.item_despesa where categoria_id = %s union all "
                           "select 'compra', id from public.lancamento_agregado where categoria_id = %s order by 1, 2", (OUTROS, OUTROS))
    catalogo = todos(cur, 'select id, nome, ativo from public.categoria order by id')
    corpo = json.dumps({'catalogo': catalogo, 'itens': [itens[i] for i in sorted(itens)], 'parcelas': parcelas, 'contas': contas,
                        'compras': [compras[i] for i in sorted(compras)], 'palavras': palavras, 'em_outros': em_outros},
                       sort_keys=True, ensure_ascii=False, default=str)
    return {'impressao': hashlib.sha256(corpo.encode()).hexdigest(), 'parcelas': parcelas, 'palavras': palavras,
            'resumo': {'categorias': len(catalogo), 'itens': len(todos_itens), 'contas_por_heranca': len(contas), 'compras': len(COMPRAS),
                       'palavras_chave': len(palavras), 'registros_em_outros': len(em_outros)}}


def chave(impressao, passo):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f'FIN-CATEGORIAS-REORGANIZACAO-01/{impressao}/{passo}'))


def rpc(cur, funcao, *args):
    marcadores = ', '.join('%s::jsonb' if isinstance(a, (dict, list)) else '%s' for a in args)
    return um(cur, f'select financeiro.{funcao}({marcadores}) j', [json.dumps(a) if isinstance(a, (dict, list)) else a for a in args])['j']


def executar(cur, e):
    imp = e['impressao']
    feito = {'impressao': imp, 'categorias': {}, 'palavras_desativadas': [], 'palavras_criadas': [], 'naturezas': [], 'chaves': {}}
    # 1. categorias novas
    for k, nome, descricao, _ in NOVAS:
        feito['categorias'][k] = rpc(cur, 'criar_categoria', {'nome': nome, 'descricao': descricao}, chave(imp, f'criar/{k}'))['categoria_id']
    alvo = lambda x: feito['categorias'][x] if isinstance(x, str) else x  # noqa: E731
    # 2. Servicos gerais: palavras genericas desativadas e incorporacao oficial em Manutencao residencial
    ativa = {(p['categoria_id'], p['palavra']): p['id'] for p in e['palavras'] if p['ativo']}
    for p in [p for p in e['palavras'] if p['categoria_id'] == GERAIS and p['ativo']]:
        rpc(cur, 'remover_palavra_chave', GERAIS, p['id'])
        feito['palavras_desativadas'].append({'id': p['id'], 'categoria_id': GERAIS, 'palavra': p['palavra']})
    previa = rpc(cur, 'previa_incorporacao_categoria', GERAIS, MANUTENCAO, {})
    if previa['bloqueios']:
        raise SystemExit('Incorporacao 95 -> 94 bloqueada: ' + '; '.join(b['motivo'] for b in previa['bloqueios']) + '. Nada feito.')
    feito['incorporacao'] = rpc(cur, 'incorporar_categoria', GERAIS, MANUTENCAO, {}, previa['hash'], chave(imp, 'incorporar/95-94'))
    feito['chaves']['incorporacao'] = chave(imp, 'incorporar/95-94')
    feito['incorporacao_referencias'] = previa.get('referencias')
    # 3. palavras-chave
    for cat, lista in PALAVRAS_SAEM.items():
        for palavra in lista:
            pid = ativa.get((cat, palavra))
            if pid:
                rpc(cur, 'remover_palavra_chave', cat, pid)
                feito['palavras_desativadas'].append({'id': pid, 'categoria_id': cat, 'palavra': palavra})
    for cat, lista in PALAVRAS_ENTRAM.items():
        for palavra in lista:
            if (alvo(cat), palavra) in ativa:
                continue
            r = rpc(cur, 'criar_palavra_chave', alvo(cat), palavra)
            feito['palavras_criadas'].append({'id': r['id'], 'categoria_id': alvo(cat), 'palavra': palavra, 'nova_linha': r['created']})
    # 4. natureza gerencial
    for cat, natureza in [(feito['categorias'][k], n) for k, _, _, n in NOVAS] + [(OUTROS, 'NAO_DEFINIDO')]:
        r = rpc(cur, 'definir_natureza_categoria', cat, natureza, chave(imp, f'natureza/{cat}'))
        feito['naturezas'].append({'categoria_id': cat, 'natureza': natureza, 'anterior': r['natureza_anterior'], 'tinha_linha': r['tinha_linha']})
    # 5. reclassificacao (so a categoria)
    manifesto = {'itens': [{'id': i, 'de': de, 'para': alvo(para)} for i, (de, para, _) in ITENS.items()]
                          + [{'id': p['id'], 'de': OUTROS, 'para': feito['categorias']['poupanca']} for c in CONSORCIOS for p in e['parcelas'][c]],
                 'compras': [{'id': lid, 'de': OUTROS, 'para': para} for lid, (para, _) in COMPRAS.items()]}
    previa = rpc(cur, 'previa_reclassificacao_categorias', manifesto)
    if previa['bloqueios']:
        raise SystemExit('Reclassificacao bloqueada: ' + '; '.join(b['motivo'] for b in previa['bloqueios']) + '. Nada feito.')
    feito['manifesto'] = manifesto
    feito['chaves']['reclassificacao'] = chave(imp, 'reclassificar')
    feito['reclassificacao'] = rpc(cur, 'reclassificar_categorias', manifesto, previa['hash'], feito['chaves']['reclassificacao'])
    return feito


def reverter(cur, feito):
    """Ordem inversa. Pelas funcoes oficiais; a categoria 95 volta pela foto guardada na auditoria da incorporacao."""
    imp = feito['impressao']
    saida = {'reclassificacao': rpc(cur, 'reverter_reclassificacao_categorias', feito['chaves']['reclassificacao'], chave(imp, 'reverter/reclassificar'))}
    for n in feito['naturezas']:
        rpc(cur, 'definir_natureza_categoria', n['categoria_id'], n['anterior'] if n['tinha_linha'] else None, chave(imp, f"reverter/natureza/{n['categoria_id']}"))
    for p in feito['palavras_criadas']:
        rpc(cur, 'remover_palavra_chave', p['categoria_id'], p['id'])
    return saida


def restaurar_catalogo(cur, feito):
    """Parte da reversao que nao tem funcao oficial (roda como dono do banco, como uma migration): a categoria 95 de volta,
    com as palavras-chave dela, a partir da foto da auditoria; as palavras-chave criadas e as categorias novas removidas
    (ja sem uso); as palavras-chave desativadas, ativas de novo. Recusa se alguma categoria nova ainda tiver referencia."""
    foto = um(cur, "select resultado -> 'fotos' -> 'origem' o from financeiro.operacao_catalogo where chave = %s", (feito['chaves']['incorporacao'],))['o']
    if not foto or foto['id'] != GERAIS:
        raise SystemExit('Foto da categoria incorporada nao encontrada: nada feito.')
    novas = list(feito['categorias'].values())
    for tabela, coluna in (('item_despesa', 'categoria_id'), ('lancamento_agregado', 'categoria_id'), ('despesa_prevista', 'categoria_id')):
        if um(cur, f'select count(*) n from public.{tabela} where {coluna} = any(%s)', (novas,))['n']:
            raise SystemExit(f'Ha registros em {tabela} nas categorias novas: reverta a reclassificacao antes. Nada feito.')
    colunas = [c['column_name'] for c in todos(cur, "select column_name from information_schema.columns where table_schema = 'public' "
                                                    "and table_name = 'categoria' order by ordinal_position")]
    presentes = [c for c in colunas if c in foto]
    cur.execute(f"insert into public.categoria ({', '.join(presentes)}) select {', '.join('r.' + c for c in presentes)} "
                'from jsonb_populate_record(null::public.categoria, %s::jsonb) r', (json.dumps(foto),))
    ids_95 = [p['id'] for p in feito['palavras_desativadas'] if p['categoria_id'] == GERAIS]
    cur.execute('update public.categoria_palavra_chave set categoria_id = %s where id = any(%s)', (GERAIS, ids_95))
    cur.execute('update public.categoria_palavra_chave set ativo = true where id = any(%s)', ([p['id'] for p in feito['palavras_desativadas']],))
    cur.execute('delete from public.categoria_palavra_chave where id = any(%s)', ([p['id'] for p in feito['palavras_criadas'] if p['nova_linha']],))
    cur.execute('update public.categoria_palavra_chave set ativo = false where id = any(%s)',
                ([p['id'] for p in feito['palavras_criadas'] if not p['nova_linha']],))
    cur.execute('delete from financeiro.categoria_natureza where categoria_id = any(%s)', (novas,))
    cur.execute('delete from public.categoria_palavra_chave where categoria_id = any(%s)', (novas,))
    cur.execute('delete from public.categoria where id = any(%s)', (novas,))
    return {'categoria_restaurada': GERAIS, 'categorias_novas_removidas': novas}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('etapa', choices=['previa', 'executar', 'reverter'])
    ap.add_argument('--saida', help='arquivo JSON do resultado')
    ap.add_argument('--hash', help='impressao da previa conferida (execucao)')
    ap.add_argument('--feito', help='arquivo JSON gravado pela execucao (reversao)')
    ap.add_argument('--confirmo', help=f'confirmacao literal: "{FRASE}" (execucao) ou "{FRASE_REVERSAO}" (reversao)')
    ap.add_argument('--dsn', default=os.environ.get('CF_REMOTO_DSN'))
    a = ap.parse_args(argv)
    if not a.dsn:
        raise SystemExit('Informe a conexao (CF_REMOTO_DSN ou --dsn).')
    if a.etapa == 'executar' and (a.confirmo != FRASE or not a.hash):
        raise SystemExit(f'Execucao recusada: informe --hash da previa conferida e --confirmo "{FRASE}".')
    if a.etapa == 'reverter' and (a.confirmo != FRASE_REVERSAO or not a.feito):
        raise SystemExit(f'Reversao recusada: informe --feito e --confirmo "{FRASE_REVERSAO}".')
    conn = conectar(a.dsn, leitura=a.etapa == 'previa')
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if a.etapa == 'reverter':
            with open(a.feito, encoding='utf-8') as f:
                feito = json.load(f)
            como_gestor(cur)
            resultado = reverter(cur, feito)
            cur.execute('reset role')
            resultado.update(restaurar_catalogo(cur, feito))
            conn.commit()
        else:
            e = estado(cur)
            if a.etapa == 'previa':
                conn.rollback()
                resultado = {'impressao': e['impressao'], **e['resumo']}
            else:
                if a.hash != e['impressao']:
                    raise SystemExit('O estado mudou desde a previa conferida: rode a previa de novo. Nada alterado.')
                como_gestor(cur)
                resultado = executar(cur, e)
                conn.commit()
        print(json.dumps({k: v for k, v in resultado.items() if k not in ('manifesto', 'incorporacao')}, ensure_ascii=False, indent=1, default=str))
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
