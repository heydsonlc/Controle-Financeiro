"""
FIN-FATURA-INTEGRIDADE-REAL-1 — validacao real da migration 20261029090000 no Supabase de teste.

So dados FICTICIOS: toda escrita no "Perfil B" temporario (usuario B, gestor), em cartoes criados aqui
(meses 2037-2038, longe dos seeds e do E2E). Cada execucao tem um identificador (RUN) no nome dos cartoes
e nas descricoes; o que ela cria fica em data/fatura_integridade_real_1.json (fora do Git). As operacoes do
novo aplicativo passam pela Data API real com login real; processos Flask reais (DATABASE_URL do
.env.staging) fazem compras, um deles parado antes do commit. O banco (postgres) so:
- simula o pagamento do Flask (status_pagamento = 'Pago') em faturas criadas aqui;
- cria a recorrencia de cartao ficticia do cenario 4 (o novo aplicativo nao cadastra recorrencia de cartao);
- confere resultados e sonda travas com FOR UPDATE NOWAIT (sem gravar nada).

Pre-requisitos: supabase_despesas_real_limpeza.py marcar; seeds perfis -> contas -> recorrencia -> receitas
-> mvp -> cartoes; .env.e2e-real. Limpeza: supabase_despesas_real_limpeza.py remover (cartoes, compras,
faturas, recorrencia e chaves criados aqui) e os removedores dos seeds. Nao imprime credenciais nem a URL.
"""
# FIN-PUBLICACAO-SEGURA-1: o projeto de teste virou a producao; recusa antes de ler credenciais ou conectar.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from guarda_producao import recusar_em_producao
recusar_em_producao(__file__)
import json
import sys
import tempfile
import time
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / 'scripts'))

from supabase_cartoes_real import (  # noqa: E402
    B, MORADIA, anonimo, cartao, comprar, edicao, editar, excluir, md5_fatura, ok, paralelo, previa, protegidos,
    soma, tabela_direta,
)
from supabase_fatura_concorrencia_real import URL, Flask, aguardar, banco, em_thread, liberar, rpc  # noqa: E402

import psycopg2  # noqa: E402
from psycopg2 import errors  # noqa: E402

D = date
RUN = uuid.uuid4().hex[:8]
TAG = f'[INTEG-REAL {RUN}]'
NS_FLASK = uuid.UUID('7f3a1b2c-4d5e-6f7a-8b9c-0d1e2f3a4b5c')  # namespace do compra_id das recorrencias
ESTADO = RAIZ / 'data' / 'fatura_integridade_real_1.json'
CRIADOS = {'run': RUN, 'cartoes': [], 'itens': [], 'compras': [], 'faturas_pagas': []}
PAGAS = {}  # fatura paga -> md5 logo depois do pagamento
RESULTADOS = []


def registrar(nome, certo, detalhe):
    RESULTADOS.append((nome, certo))
    print(f"{'OK ' if certo else 'FALHA'} | {nome} | {detalhe}", flush=True)


def salvar():
    ESTADO.write_text(json.dumps(CRIADOS, indent=1, default=str), encoding='utf-8')


def novo_cartao(rotulo):
    cid = cartao(f'Integridade {RUN} {rotulo}', 10)  # fecha dia 3, vence dia 10
    CRIADOS['cartoes'].append(cid)
    salvar()
    return cid


def anotar(compra_id):
    if compra_id not in CRIADOS['compras']:
        CRIADOS['compras'].append(compra_id)
        salvar()


def compra_ok(*args, **kwargs):
    r = ok(comprar(*args, **kwargs))
    anotar(r['compra_id'])
    return r


def linhas(compra_id):
    return [tuple(x) for x in banco(
        'select numero_parcela, mes_fatura, mes_fatura_original, valor from public.lancamento_agregado '
        'where compra_id = %s order by numero_parcela', (compra_id,))]


def faturas_do(cartao_id, mes):
    return [r[0] for r in banco('select id from public.conta where is_fatura_cartao and item_despesa_id = %s '
                                'and cartao_competencia = %s order by id', (cartao_id, mes))]


def pagar(cartao_id, mes):
    """Simula o pagamento do Flask (status_fatura continua ABERTA), so em fatura criada aqui."""
    ids = banco("update public.conta set status_pagamento = 'Pago', data_pagamento = %s where is_fatura_cartao "
                "and item_despesa_id = %s and cartao_competencia = %s returning id",
                (mes[:8] + '10', cartao_id, mes), escrever=True)
    assert len(ids) == 1, ids
    fid = ids[0][0]
    CRIADOS['faturas_pagas'].append(fid)
    salvar()
    PAGAS[fid] = md5_fatura(fid)
    return fid


def compra_flask(pasta, nome, cartao_id, descricao, mes, valor, parcelas=1, **cfg):
    dados = {'cartao_id': cartao_id, 'valor': valor, 'descricao': descricao, 'data_compra': mes[:8] + '05',
             'mes_fatura': mes, 'categoria_id': MORADIA, 'total_parcelas': parcelas}
    return Flask(pasta, nome, acao='compra', dados=dados, **cfg)


def compra_id_de(lancamento_id):
    cid = banco('select compra_id from public.lancamento_agregado where id = %s', (lancamento_id,))[0][0]
    anotar(cid)
    return cid


def sonda_cartao(cartao_id):
    """'TRAVADO' se outra transacao segura a linha do cartao (FOR UPDATE NOWAIT); nada e gravado."""
    conn = psycopg2.connect(URL, connect_timeout=15)
    try:
        with conn.cursor() as cur:
            cur.execute('select 1 from public.item_despesa where id = %s for update nowait', (cartao_id,))
        return 'LIVRE'
    except errors.LockNotAvailable:
        return 'TRAVADO'
    finally:
        conn.rollback()
        conn.close()


def segurar_fatura(fatura_id):
    """Transacao propria segurando SO a fatura (o cartao fica livre)."""
    conn = psycopg2.connect(URL, connect_timeout=15)
    conn.cursor().execute('select 1 from public.conta where id = %s for update', (fatura_id,))
    return conn


def gerar_b(mes):
    st, pv = rpc('previa_geracao', {'p_perfil_id': B, 'p_mes': mes})
    if st != 200:
        return st, pv
    return rpc('gerar_mes', {'p_perfil_id': B, 'p_mes': mes, 'p_total_previsto': pv['a_gerar']})


def main():
    if ESTADO.exists():
        raise SystemExit(f'{ESTADO.name} ja existe: limpe a execucao anterior antes.')
    salvar()
    print(f'Execucao {RUN} (Perfil B ficticio)', flush=True)
    inicio = protegidos()

    with tempfile.TemporaryDirectory(prefix='cf-integ-real-') as tmp:
        pasta = Path(tmp)

        # 1. Compra em fatura aberta
        c1 = novo_cartao('A')
        r1 = compra_ok(c1, f'{TAG} 1 aberta', '2037-01-01', '100.00')
        f1 = banco('select status_pagamento, status_fatura, valor_executado from public.conta where id = %s',
                   (faturas_do(c1, '2037-01-01')[0],))[0]
        registrar('1. Compra em fatura aberta',
                  linhas(r1['compra_id']) == [(1, D(2037, 1, 1), None, Decimal('100.00'))]
                  and tuple(f1) == ('Pendente', 'ABERTA', Decimal('100.00')) and soma(c1, '2037-01-01') == Decimal('100.00'),
                  'incluida em 01/2037; fatura Pendente/ABERTA com executado 100,00; mes_fatura_original nulo')

        # 2 e 3. Compra em fatura paga: desvio e competencia original (novo aplicativo e Flask real)
        base = compra_ok(c1, f'{TAG} 2 base', '2037-02-01', '60.00')
        paga02 = pagar(c1, '2037-02-01')
        pv = previa(c1, f'{TAG} 2 desvio', '2037-02-01', '40.00')
        r2 = compra_ok(c1, f'{TAG} 2 desvio', '2037-02-01', '40.00')
        rf = compra_flask(pasta, 'desvio', c1, f'{TAG} 3 flask desvio', '2037-02-01', '25.00').resultado()
        cf = compra_id_de(rf['lancamento'])
        registrar('2. Compra em fatura paga vai para a proxima elegivel',
                  pv['parcelas'][0]['redirecionada'] and str(pv['parcelas'][0]['mes_fatura']) == '2037-03-01'
                  and linhas(r2['compra_id'])[0][1] == D(2037, 3, 1) and linhas(cf)[0][1] == D(2037, 3, 1)
                  and soma(c1, '2037-02-01') == Decimal('60.00') and md5_fatura(paga02) == PAGAS[paga02],
                  'previa avisa o desvio; novo app e Flask real lancam em 03/2037; fatura 02 paga intacta (md5)')
        registrar('3. Competencia original preservada na compra desviada',
                  linhas(r2['compra_id']) == [(1, D(2037, 3, 1), D(2037, 2, 1), Decimal('40.00'))]
                  and linhas(cf) == [(1, D(2037, 3, 1), D(2037, 2, 1), Decimal('25.00'))],
                  'mes_fatura_original = 02/2037 no novo app e no Flask real (a coluna agora existe no remoto)')

        # 4. Recorrencia de cartao com a fatura da competencia paga (novo motor)
        c2 = novo_cartao('Rec')
        compra_ok(c2, f'{TAG} 4 base', '2037-06-01', '20.00')
        paga06 = pagar(c2, '2037-06-01')
        item = banco("insert into public.item_despesa (nome, tipo, perfil_financeiro_id, categoria_id, ativo, recorrente, "
                     "tipo_recorrencia, data_vencimento, valor, meio_pagamento, cartao_id) values "
                     "(%s, 'Simples', %s, %s, true, true, 'mensal', '2037-06-15', 25.00, 'cartao', %s) returning id",
                     (f'{TAG} 4 assinatura', B, MORADIA, c2), escrever=True)[0][0]
        CRIADOS['itens'].append(item)
        salvar()
        g1 = gerar_b('2037-06-01')
        g2 = gerar_b('2037-06-01')
        rec = [tuple(x) for x in banco(
            'select mes_fatura, mes_fatura_original, valor, is_recorrente, compra_id from public.lancamento_agregado '
            'where item_despesa_id = %s order by mes_fatura_original nulls last, id', (item,))]
        for x in rec:
            anotar(x[4])
        ident = [tuple(x) for x in banco(
            "select competencia, situacao from financeiro.recorrencia_competencia where item_despesa_id = %s "
            "and natureza = 'LANCAMENTO_CARTAO' order by competencia", (item,))]
        cid06 = str(uuid.uuid5(NS_FLASK, f'{item}-2037-06-01'))
        cid07 = str(uuid.uuid5(NS_FLASK, f'{item}-2037-07-01'))
        registrar('4. Recorrencia em fatura paga nao altera a fatura paga',
                  g1[0] == 200 and g2[0] == 200
                  and rec == [(D(2037, 7, 1), D(2037, 6, 1), Decimal('25.00'), True, cid06),
                              (D(2037, 7, 1), None, Decimal('25.00'), True, cid07)]
                  and ident == [(D(2037, 6, 1), 'GERADA'), (D(2037, 7, 1), 'GERADA')]
                  and soma(c2, '2037-06-01') == Decimal('20.00') and md5_fatura(paga06) == PAGAS[paga06],
                  'competencia 06 (paga) lancada em 07 com original 06; 07 em 07; identidades GERADA; '
                  'segunda geracao sem duplicar; fatura 06 intacta (md5)')

        # 5. Parcelada atravessando fatura paga: novo app = Flask real
        c3 = novo_cartao('Parc')
        compra_ok(c3, f'{TAG} 5 base', '2037-10-01', '15.00')
        paga10 = pagar(c3, '2037-10-01')
        r5 = compra_ok(c3, f'{TAG} 5 novo 3x', '2037-09-01', '90.00', 3)
        rf5 = compra_flask(pasta, 'parcelada', c3, f'{TAG} 5 flask 3x', '2037-09-01', '90.00', 3).resultado()
        cf5 = compra_id_de(rf5['lancamento'])
        esperado = [(1, D(2037, 9, 1), None, Decimal('30.00')), (2, D(2037, 11, 1), D(2037, 10, 1), Decimal('30.00')),
                    (3, D(2037, 12, 1), D(2037, 11, 1), Decimal('30.00'))]
        registrar('5. Parcelada atravessando fatura paga (novo app = Flask)',
                  linhas(r5['compra_id']) == linhas(cf5) == esperado
                  and soma(c3, '2037-10-01') == Decimal('15.00') and md5_fatura(paga10) == PAGAS[paga10],
                  'parcelas em 09, 11 (orig. 10) e 12 (orig. 11), 30,00 cada, nos dois sistemas; fatura 10 intacta')

        # 6. Alteracao de compra protegida
        lanc_pago = base['lancamentos'][0]
        md5_l = banco('select md5(t::text) from public.lancamento_agregado t where id = %s', (lanc_pago,))[0][0]
        s_ed, erro_ed = editar(lanc_pago, {'descricao': 'X'})
        s_ex, _ = excluir(lanc_pago)
        paga09 = pagar(c3, '2037-09-01')  # parcela 1 da compra 5 fica em fatura paga
        abertas = edicao(r5['lancamentos'][0])['abertas']
        s_parc, corpo_parc = excluir(r5['lancamentos'][0])
        registrar('6. Alteracao de compra protegida bloqueada',
                  (s_ed, s_ex) == (400, 400) and 'paga' in str(erro_ed).lower()
                  and banco('select md5(t::text) from public.lancamento_agregado t where id = %s', (lanc_pago,))[0][0] == md5_l
                  and abertas == 2 and s_parc == 200 and corpo_parc == {'excluidas': 2, 'preservadas': 1}
                  and [x[0] for x in linhas(r5['compra_id'])] == [1] and md5_fatura(paga09) == PAGAS[paga09],
                  f'editar/excluir em fatura paga: {s_ed}/{s_ex}, compra intacta (md5); exclusao parcial: '
                  f'{corpo_parc}, parcela paga preservada')

        # 8. Acesso sem permissao
        dados = {'cartao_id': c1, 'descricao': f'{TAG} 8 sem permissao', 'valor': '1.00', 'total_parcelas': 1,
                 'data_compra': '2037-04-05', 'mes_fatura': '2037-04-01', 'categoria_id': MORADIA}
        s_anon = anonimo('criar_compra', {'p_perfil_id': B, 'p_dados': dados, 'p_chave': str(uuid.uuid4())})
        s_a = comprar(c1, f'{TAG} 8 sem permissao', '2037-04-01', '1.00', usuario='A')[0]
        internas = {
            'fatura_elegivel_existente': rpc('fatura_elegivel_existente', {'p_cartao_id': c1, 'p_competencia': '2037-02-01'})[0],
            'travar_compra': rpc('travar_compra', {'p_perfil_id': B, 'p_lancamento_id': r1['lancamentos'][0], 'p_versao': 'x'})[0],
            'gerar_mes_interno': rpc('gerar_mes_interno', {'p_perfil_id': B, 'p_mes': '2037-04-01', 'p_total_previsto': 0})[0],
            'plano_recorrencia': rpc('plano_recorrencia', {'p_perfil_id': B, 'p_mes': '2037-04-01'})[0],
        }
        direta = tabela_direta('lancamento_agregado', 'public', 'B')
        nada = banco('select count(*) from public.lancamento_agregado where descricao = %s', (f'{TAG} 8 sem permissao',))[0][0]
        registrar('8. Acesso sem permissao rejeitado',
                  s_anon == 401 and s_a == 403 and all(s in (401, 403, 404) for s in internas.values())
                  and (direta[0] != 200 or direta[1] == []) and nada == 0,
                  f'anonimo {s_anon}; usuario A no Perfil B {s_a}; funcoes internas pela API {internas}; '
                  f'tabela direta {direta[0]}; nada gravado')

        # 9. Concorrencia
        c4 = novo_cartao('Conc')
        rs = paralelo([lambda i=i: comprar(c4, f'{TAG} 9a simultanea {i}', '2037-11-01', '10.00') for i in range(3)])
        for st, corpo in rs:
            if st == 200:
                anotar(corpo['compra_id'])
        chave = str(uuid.uuid4())
        rk = paralelo([lambda: comprar(c4, f'{TAG} 9b mesma chave', '2037-12-01', '10.00', chave=chave)] * 3)
        for st, corpo in rk:
            if st == 200:
                anotar(corpo['compra_id'])
        n_chave = banco('select count(*) from public.lancamento_agregado where descricao = %s', (f'{TAG} 9b mesma chave',))[0][0]
        registrar('9a. Compras simultaneas e repeticao da mesma solicitacao',
                  [x[0] for x in rs] == [200] * 3 and len(faturas_do(c4, '2037-11-01')) == 1
                  and soma(c4, '2037-11-01') == Decimal('30.00')
                  and [x[0] for x in rk] == [200] * 3 and len({x[1]['compra_id'] for x in rk}) == 1 and n_chave == 1,
                  '3 compras simultaneas: 1 fatura, executado 30,00; mesma chave 3x: 1 compra')

        compra_ok(c4, f'{TAG} 9c fatura sendo paga', '2038-01-01', '10.00')
        pagando = psycopg2.connect(URL, connect_timeout=15)
        cur = pagando.cursor()
        cur.execute("update public.conta set status_pagamento = 'Pago', data_pagamento = '2038-01-10' where is_fatura_cartao "
                    "and item_despesa_id = %s and cartao_competencia = '2038-01-01' returning id", (c4,))
        paga_c = cur.fetchone()[0]
        tarefa, resposta = em_thread(lambda: comprar(c4, f'{TAG} 9c durante o pagamento', '2038-01-01', '5.00'))
        time.sleep(4)
        esperando = tarefa.is_alive()
        pagando.commit()
        pagando.close()
        CRIADOS['faturas_pagas'].append(paga_c)
        salvar()
        PAGAS[paga_c] = md5_fatura(paga_c)
        tarefa.join(120)
        st_c, corpo_c = resposta['valor']
        registrar('9b. Compra durante um pagamento',
                  esperando and st_c == 400 and 'paga durante o cadastro' in str(corpo_c)
                  and soma(c4, '2038-01-01') == Decimal('10.00'),
                  f'esperou a transacao do pagamento: {esperando}; depois recusada ({st_c}); fatura com 10,00')

        # 9c. Ordem de travas no novo aplicativo: cartao ANTES da fatura (criar_compra e travar_compra)
        c5 = novo_cartao('Ordem')
        compra_ok(c5, f'{TAG} 9d base', '2038-03-01', '5.00')
        f_ordem = faturas_do(c5, '2038-03-01')[0]
        segura = segurar_fatura(f_ordem)
        tarefa, resposta = em_thread(lambda: comprar(c5, f'{TAG} 9d ordem', '2038-03-01', '7.00'))
        time.sleep(3)
        sonda_compra, esperou_compra = sonda_cartao(c5), tarefa.is_alive()
        segura.rollback()
        segura.close()
        tarefa.join(120)
        st_o, corpo_o = resposta['valor']
        if st_o == 200:
            anotar(corpo_o['compra_id'])
        versao = edicao(corpo_o['lancamentos'][0])['versao'] if st_o == 200 else None
        segura = segurar_fatura(f_ordem)
        tarefa, resposta = em_thread(lambda: excluir(corpo_o['lancamentos'][0], versao))
        time.sleep(3)
        sonda_trava, esperou_trava = sonda_cartao(c5), tarefa.is_alive()
        segura.rollback()
        segura.close()
        tarefa.join(120)
        st_x, corpo_x = resposta['valor']
        registrar('9c. Ordem de travas do novo aplicativo: cartao antes da fatura',
                  st_o == 200 and esperou_compra and sonda_compra == 'TRAVADO'
                  and st_x == 200 and corpo_x == {'excluidas': 1, 'preservadas': 0} and esperou_trava and sonda_trava == 'TRAVADO'
                  and soma(c5, '2038-03-01') == Decimal('5.00'),
                  f'com so a fatura presa: criar_compra esperou ({esperou_compra}) segurando o cartao ({sonda_compra}); '
                  f'exclusao (travar_compra) esperou ({esperou_trava}) segurando o cartao ({sonda_trava}); ambas concluidas')

        # 9d. Flask x novo aplicativo em ordens opostas: sem deadlock, ambos concluem
        r_e = compra_ok(c5, f'{TAG} 9e existente 2x', '2038-05-01', '60.00', 2)
        v_e = edicao(r_e['lancamentos'][0])['versao']
        fl = compra_flask(pasta, 'opostas', c5, f'{TAG} 9e flask 2x', '2038-05-01', '40.00', 2, pausa='antes_do_commit')
        aguardar(pasta, ['opostas_inseriu'], [fl])
        sonda_flask = sonda_cartao(c5)
        tarefa, resposta = em_thread(lambda: excluir(r_e['lancamentos'][0], v_e))
        time.sleep(3)
        esperou_flask = tarefa.is_alive()
        liberar(pasta, 'inseriu')
        rfl = fl.resultado()
        tarefa.join(120)
        st_e, corpo_e = resposta['valor']
        cfe = compra_id_de(rfl['lancamento'])
        registrar('9d. Flask e novo aplicativo em ordens opostas, sem deadlock',
                  sonda_flask == 'TRAVADO' and esperou_flask and st_e == 200
                  and corpo_e == {'excluidas': 2, 'preservadas': 0}
                  and [x[1] for x in linhas(cfe)] == [D(2038, 5, 1), D(2038, 6, 1)] and linhas(r_e['compra_id']) == [],
                  f'Flask parado antes do commit segurando o cartao ({sonda_flask}); exclusao do novo app esperou '
                  f'({esperou_flask}) e concluiu ({st_e}, {corpo_e}); Flask concluiu com 2 parcelas')

    # 7. Faturas pagas preservadas; 10. unicidade; 11. dados fora do Perfil B
    estados = {fid: banco('select status_pagamento from public.conta where id = %s', (fid,))[0][0] for fid in PAGAS}
    registrar('7. Faturas pagas com valor e estado preservados',
              all(md5_fatura(fid) == m for fid, m in PAGAS.items()) and set(estados.values()) == {'Pago'},
              f'{len(PAGAS)} faturas pagas identicas (md5) ao momento do pagamento')
    dup_f = banco('select count(*) from (select 1 from public.conta where is_fatura_cartao and perfil_financeiro_id = %s '
                  'group by item_despesa_id, cartao_competencia having count(*) > 1) d', (B,))[0][0]
    dup_p = banco('select count(*) from (select 1 from public.lancamento_agregado where compra_id is not null '
                  'group by compra_id, numero_parcela having count(*) > 1) d')[0][0]
    registrar('10. Sem duplicidade de faturas e parcelas', dup_f == 0 and dup_p == 0, f'faturas: {dup_f}; parcelas: {dup_p}')
    registrar('11. Registros fora do Perfil B, saldos e movimentos preservados', protegidos() == inicio,
              'movimentos, contas bancarias, contas, compras e itens fora do Perfil B identicos')

    total = banco('select count(*) from public.lancamento_agregado where cartao_id = any(%s)', (CRIADOS['cartoes'],))[0][0]
    CRIADOS['parcelas_nos_cartoes_do_teste'] = total
    salvar()
    falhas = [n for n, certo in RESULTADOS if not certo]
    print(f'\nResumo {RUN}: {len(RESULTADOS) - len(falhas)}/{len(RESULTADOS)} aprovados'
          + (f' | FALHAS: {falhas}' if falhas else ''))
    print(f'Criados: {len(CRIADOS["cartoes"])} cartoes, {len(CRIADOS["itens"])} recorrencia, '
          f'{len(CRIADOS["compras"])} compras ({total} parcelas), {len(CRIADOS["faturas_pagas"])} faturas pagas simuladas')
    return 1 if falhas else 0


if __name__ == '__main__':
    sys.exit(main())
