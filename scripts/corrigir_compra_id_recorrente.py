#!/usr/bin/env python
"""
FIN-POS-MIGRACAO-DESPESAS-1 — corrige o compra_id das compras recorrentes no cartao carregadas pelo FIN-BLOCO-D-3.

O compra_id da compra recorrente e deterministico: uuid5(NS, "<item_despesa_id>-<mes_fatura>") (Flask:
gerar_lancamentos_cartao_recorrente; Supabase: plano_recorrencia). A carga deu id novo ao item e copiou o compra_id
calculado com o id ANTIGO; o motor nao reconhece a compra ja gravada e a ofereceria de novo (duplicaria). Aqui o
compra_id passa a ser o calculado com o id novo. Nenhuma outra coluna e nenhuma outra linha muda.

Identidade (cada linha precisa de todas; se uma falhar, nada e gravado):
- no destino: lancamento recorrente com item, cujo compra_id NAO e o deterministico do proprio item;
- na origem (somente leitura): lancamento com o MESMO compra_id, recorrente, mesmo mes_fatura, descricao e valor, cujo
  compra_id e o deterministico do item antigo; e o item antigo tem o mesmo nome do item novo;
- o compra_id novo nao existe em nenhum lancamento do destino, e o antigo nao aparece em fatura_consolidada_inclusao;
- o plano do motor (financeiro.plano_recorrencia, so leitura) oferece exatamente esse compra_id como "a gerar".
Conferencia antes do commit: o plano ve cada compra como EXISTENTE; nas linhas corrigidas so o compra_id mudou; o resto
de lancamento_agregado e as tabelas financeiras vizinhas (CONFERIDAS) ficaram identicos. O relatorio (--registro) guarda
lancamento, item, mes e os compra_id anterior e novo (identificadores tecnicos, sem valores nem descricoes).

Uso (conexoes so por variavel de ambiente; nada e impresso delas nem dos valores):
    python scripts/corrigir_compra_id_recorrente.py simular --perfil 1 --mes 2026-10-01 [--registro arquivo.json]
        SOMENTE LEITURA nas duas pontas: lista o que seria corrigido e o efeito na previa do mes (a da tela Despesas,
        que vai ate o mes seguinte).
    python scripts/corrigir_compra_id_recorrente.py corrigir --perfil 1 --mes 2026-10-01 --confirmar --projeto-autorizado <ref>
                                                            [--registro arquivo.json]
        Uma transacao serializavel: refaz a identificacao, grava, e confere antes do commit que o plano passou a ver
        cada compra como EXISTENTE e que so essas linhas mudaram.
"""
import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

import psycopg2
import psycopg2.extras

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from scripts.carga_supabase import compra_id_recorrente  # noqa: E402
from scripts.limpeza_ficticios_supabase import ref_do_dsn  # noqa: E402


# Tabelas que a correcao nao pode tocar (conferidas por md5 antes e depois, na mesma transacao).
CONFERIDAS = ['conta', 'item_despesa', 'movimento_financeiro', 'fatura_consolidada_inclusao', 'config_agregador',
              'financeiro.recorrencia_competencia', 'financeiro.recorrencia_ocorrencia']


class CorrecaoRecusada(Exception):
    """A correcao nao pode seguir (nada e gravado)."""


def _q(cur, sql, params=None):
    cur.execute(sql, params)
    return cur.fetchall()


def identificar(dc, oc, perfil, mes):
    """Linhas a corrigir, conferidas pela identidade na origem e pelo plano do motor (so leitura)."""
    candidatos = [r for r in _q(dc, """
        select l.id, l.item_despesa_id, l.mes_fatura, l.compra_id, l.descricao, l.valor, i.nome as item_nome
          from public.lancamento_agregado l join public.item_despesa i on i.id = l.item_despesa_id
         where l.is_recorrente and l.compra_id is not null
           and (l.perfil_financeiro_id = %s or (l.perfil_financeiro_id is null
                and exists (select 1 from public.perfil_financeiro p where p.id = %s and p.nome = 'Pessoal')))
         order by l.id""", (perfil, perfil)) if r['compra_id'] != compra_id_recorrente(r['item_despesa_id'], r['mes_fatura'])]
    plano = _q(dc, 'select natureza, situacao, competencia, compra_id from financeiro.plano_recorrencia(%s, %s)', (perfil, mes))
    limite = max((r['competencia'] for r in plano if r['competencia'] is not None), default=mes)
    a_gerar = {r['compra_id'] for r in plano if r['natureza'] == 'LANCAMENTO_CARTAO' and r['situacao'] == 'A_GERAR'}
    linhas, recusas = [], []
    for r in candidatos:
        novo = compra_id_recorrente(r['item_despesa_id'], r['mes_fatura'])
        origem = _q(oc, """select l.item_despesa_id, l.mes_fatura, l.descricao, l.valor, i.nome as item_nome
                             from public.lancamento_agregado l join public.item_despesa i on i.id = l.item_despesa_id
                            where l.compra_id = %s and l.is_recorrente""", (r['compra_id'],))
        motivo = None
        if len(origem) != 1:
            motivo = f'{len(origem)} lancamento(s) na origem com o mesmo compra_id (esperado 1)'
        else:
            o = origem[0]
            if compra_id_recorrente(o['item_despesa_id'], o['mes_fatura']) != r['compra_id']:
                motivo = 'compra_id da origem nao e o deterministico do item antigo'
            elif (o['mes_fatura'], o['descricao'], o['valor'], o['item_nome']) != (r['mes_fatura'], r['descricao'], r['valor'], r['item_nome']):
                motivo = 'mes, descricao, valor ou item diferentes da origem'
        if motivo is None and _q(dc, 'select 1 from public.lancamento_agregado where compra_id = %s', (novo,)):
            motivo = 'o compra_id novo ja existe no destino'
        if motivo is None and _q(dc, 'select 1 from public.fatura_consolidada_inclusao where compra_id = %s', (r['compra_id'],)):
            motivo = 'o compra_id antigo esta numa inclusao de fatura consolidada'
        if motivo is None and r['mes_fatura'] <= limite and novo not in a_gerar:
            motivo = 'o plano do motor nao oferece esta compra como "a gerar"'
        if motivo:
            recusas.append({'lancamento': r['id'], 'motivo': motivo})
        else:
            linhas.append({'id': r['id'], 'item': r['item_despesa_id'], 'mes_fatura': str(r['mes_fatura']), 'novo': novo,
                           'antigo': r['compra_id'], 'no_plano': r['mes_fatura'] <= limite})
    if recusas:
        raise CorrecaoRecusada(f'Linhas sem identidade confirmada: {recusas}')
    return linhas


def retrato(dc, ids):
    """md5 das tabelas conferidas, do resto de lancamento_agregado e das linhas corrigidas sem o compra_id."""
    h = "md5(coalesce(string_agg(x::text, '|' order by x::text), ''))"
    out = {t: _q(dc, f'select {h} as h from {t if "." in t else "public." + t} x')[0]['h'] for t in CONFERIDAS}
    out['lancamento_agregado (demais linhas)'] = _q(dc, f'select {h} as h from public.lancamento_agregado x where not (x.id = any(%s))', (ids,))[0]['h']
    out['lancamento_agregado (corrigidas, sem compra_id)'] = _q(
        dc, f"select {h} as h from (select to_jsonb(l) - 'compra_id' as x from public.lancamento_agregado l where l.id = any(%s)) y", (ids,))[0]['h']
    return out


def resumo_previa(dc, perfil, mes):
    return _q(dc, """select count(*) filter (where situacao = 'A_GERAR') as a_gerar,
                            count(*) filter (where situacao = 'A_GERAR' and natureza = 'LANCAMENTO_CARTAO') as cartao_a_gerar,
                            count(*) filter (where situacao = 'EXISTENTE' and natureza = 'LANCAMENTO_CARTAO') as cartao_existente
                       from financeiro.plano_recorrencia(%s, %s)""", (perfil, mes))[0]


def executar(destino_dsn, origem_dsn, perfil, mes, confirmar):
    o = psycopg2.connect(origem_dsn)
    o.set_session(readonly=True)
    d = psycopg2.connect(destino_dsn)
    d.set_session(isolation_level=psycopg2.extensions.ISOLATION_LEVEL_SERIALIZABLE, readonly=not confirmar)
    try:
        oc = o.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        dc = d.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        linhas = identificar(dc, oc, perfil, mes)
        antes = dict(resumo_previa(dc, perfil, mes))
        n = sum(1 for x in linhas if x['no_plano'])
        relatorio = {'perfil': perfil, 'mes': str(mes), 'linhas': len(linhas),
                     'por_mes': {m: sum(1 for x in linhas if x['mes_fatura'] == m) for m in sorted({x['mes_fatura'] for x in linhas})},
                     'previa_antes': antes,
                     'previa_esperada_depois': {'a_gerar': antes['a_gerar'] - n, 'cartao_a_gerar': antes['cartao_a_gerar'] - n,
                                                'cartao_existente': antes['cartao_existente'] + n},
                     'registro': [{'lancamento': x['id'], 'item': x['item'], 'mes_fatura': x['mes_fatura'],
                                   'compra_id_anterior': x['antigo'], 'compra_id_novo': x['novo']} for x in linhas]}
        if not confirmar:
            relatorio['resultado'] = 'SIMULACAO (somente leitura: nada gravado)'
            return relatorio
        if not linhas:
            raise CorrecaoRecusada('Nada a corrigir')
        ids = [x['id'] for x in linhas]
        retrato_antes = retrato(dc, ids)
        for x in linhas:
            dc.execute('update public.lancamento_agregado set compra_id = %s where id = %s and compra_id = %s', (x['novo'], x['id'], x['antigo']))
            if dc.rowcount != 1:
                raise CorrecaoRecusada(f'Lancamento {x["id"]} mudou durante a correcao')
        depois = dict(resumo_previa(dc, perfil, mes))
        existentes = {r['compra_id'] for r in _q(dc, """select compra_id from financeiro.plano_recorrencia(%s, %s)
                                                         where natureza = 'LANCAMENTO_CARTAO' and situacao = 'EXISTENTE'""", (perfil, mes))}
        faltam = [x['id'] for x in linhas if x['no_plano'] and x['novo'] not in existentes]
        mudaram = [t for t, h in retrato(dc, ids).items() if retrato_antes[t] != h]
        corrigidas = {r['id']: r['compra_id'] for r in _q(dc, 'select id, compra_id from public.lancamento_agregado where id = any(%s)', (ids,))}
        if faltam or mudaram or depois != relatorio['previa_esperada_depois'] or corrigidas != {x['id']: x['novo'] for x in linhas}:
            raise CorrecaoRecusada(f'Conferencia falhou (nao reconhecidas {faltam}, alteradas {mudaram}, previa {depois})')
        d.commit()
        relatorio.update({'resultado': 'CORRIGIDO', 'previa_depois': depois, 'tabelas_conferidas_inalteradas': sorted(retrato_antes)})
        return relatorio
    except Exception:
        d.rollback()
        raise
    finally:
        o.rollback()
        o.close()
        d.close()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = p.add_subparsers(dest='comando', required=True)
    for nome in ('simular', 'corrigir'):
        s = sub.add_parser(nome)
        s.add_argument('--perfil', type=int, required=True)
        s.add_argument('--mes', required=True, help='mes exibido na tela Despesas (AAAA-MM-01); o plano vai ate o seguinte')
        s.add_argument('--destino-env', default='CF_REMOTO_DSN')
        s.add_argument('--origem-env', default='CARGA_ORIGEM_DSN')
        if nome == 'corrigir':
            s.add_argument('--confirmar', action='store_true')
            s.add_argument('--projeto-autorizado')
        s.add_argument('--registro', help='grava o relatorio (com os compra_id anterior e novo de cada linha) neste arquivo')
    args = p.parse_args(argv)
    destino, origem = os.environ.get(args.destino_env), os.environ.get(args.origem_env)
    try:
        if not destino or not origem:
            raise CorrecaoRecusada(f'Defina {args.destino_env} e {args.origem_env}')
        confirmar = args.comando == 'corrigir' and args.confirmar
        ref = ref_do_dsn(destino)
        if confirmar and ref is not None and args.projeto_autorizado != ref:
            raise CorrecaoRecusada('Projeto Supabase: informe --projeto-autorizado <ref> (autorizacao expressa do titular)')
        relatorio = executar(destino, origem, args.perfil, date.fromisoformat(args.mes), confirmar)
    except CorrecaoRecusada as erro:
        print(f'CORRECAO_RECUSADA: {erro}', file=sys.stderr)
        return 2
    if args.registro:
        Path(args.registro).write_text(json.dumps(relatorio, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
    relatorio['registro'] = f'{len(relatorio["registro"])} linha(s)' + (f' em {args.registro}' if args.registro else ' (use --registro)')
    print(json.dumps(relatorio, ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == '__main__':
    sys.exit(main())
