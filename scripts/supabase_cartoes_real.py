"""
FIN-CARTOES-REAL-1 — testes reais de cartoes, compras e faturas no Supabase de teste.

So dados FICTICIOS: toda escrita no "Perfil B" temporario (usuario B, gestor), em cartoes criados
aqui (meses 2034-2036, longe dos seeds); leituras e tentativas negadas no Pessoal/Empresa (usuario
A: gestor do Pessoal, LEITOR da Empresa), sem gravar nada neles. As operacoes passam pela Data API
real com login real; o banco (postgres) so prepara categoria/limite do cartao, simula o pagamento
do Flask e confere resultados. Processos Flask reais (DATABASE_URL do .env.staging) fazem compras e
criam faturas, alguns parados em barreiras por arquivo. Concorrencia: requisicoes HTTP em threads
(transacoes independentes) e conexoes proprias ao banco.

Pre-requisitos: supabase_despesas_real_limpeza.py marcar; seeds perfis -> contas -> recorrencia ->
cartoes; .env.e2e-real. Limpeza: supabase_despesas_real_limpeza.py remover (cartoes, compras,
faturas, limites, categorias e chaves criados aqui; a recorrencia do 17b e suas ocorrencias em
public.recorrencia_rejeicao). Nao imprime credenciais nem a URL do banco.
Cenarios 17a/17b (fechamento automatico, recorrencia rejeitada, aviso e dispensa) em
supabase_cartoes_fechamento_cenarios.py, ensaiados localmente com o mesmo codigo.
"""
import json
import sys
import tempfile
import threading
import time
import uuid
from datetime import date
from types import SimpleNamespace
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / 'scripts'))

from supabase_fatura_concorrencia_real import (  # noqa: E402
    ORIGEM, URL, Flask, aguardar, banco, em_thread, liberar, rpc,
)
import urllib.error  # noqa: E402
import urllib.request  # noqa: E402

from supabase_cartoes_fechamento_cenarios import fechamento_automatico, recorrencia_rejeitada  # noqa: E402
from verificar_exposicao_supabase import chave_publica_via_cli  # noqa: E402

PERFIS = json.loads((RAIZ / 'data' / 'perfis_real_1_teste.json').read_text(encoding='utf-8'))
B, PESSOAL, EMPRESA = PERFIS['id_perfil_b'], PERFIS['ids_existentes_usados']['Pessoal'], PERFIS['ids_existentes_usados']['Empresa']
INATIVO = PERFIS['perfis_temporarios'][1]  # "Perfil inativo (A)": A e TITULAR com gestao, perfil inativo
MAPA = json.loads((RAIZ / 'data' / 'contas_real_1_teste.json').read_text(encoding='utf-8'))['mapa']
MORADIA, SAUDE = MAPA['201'], MAPA['202']
CHAVE, _ = chave_publica_via_cli()
D = date
RESULTADOS = []


def registrar(nome, ok, detalhe):
    RESULTADOS.append((nome, ok))
    print(f"{'OK ' if ok else 'FALHA'} | {nome} | {detalhe}", flush=True)


def ok(resposta):
    status, corpo = resposta
    if status != 200:
        raise SystemExit(f'chamada falhou: {status} {corpo}')
    return corpo


def anonimo(funcao, corpo):
    req = urllib.request.Request(f'{ORIGEM}/rest/v1/rpc/{funcao}', method='POST', data=json.dumps(corpo).encode())
    for nome, valor in (('apikey', CHAVE), ('Content-Type', 'application/json'), ('Content-Profile', 'financeiro')):
        req.add_header(nome, valor)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


def tabela_direta(tabela, perfil, usuario):
    from supabase_fatura_concorrencia_real import TOKENS
    req = urllib.request.Request(f'{ORIGEM}/rest/v1/{tabela}?select=*&limit=1')
    for nome, valor in (('apikey', CHAVE), ('Authorization', f'Bearer {TOKENS[usuario]}'), ('Accept-Profile', perfil)):
        req.add_header(nome, valor)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read() or b'null')
    except urllib.error.HTTPError as exc:
        return exc.code, None


def cartao(nome, vencimento, fechamento=3, **extra):
    r = ok(rpc('criar_cartao', {'p_perfil_id': B, 'p_dados': {'nome': nome, 'dia_fechamento': fechamento,
                                                               'dia_vencimento': vencimento, **extra},
                                'p_chave': str(uuid.uuid4())}))
    return r['cartao_id']


def comprar(cartao_id, descricao, mes, valor, parcelas=1, data_compra=None, categoria=MORADIA, chave=None, usuario='B',
            perfil=B, extra=None):
    dados = {'cartao_id': cartao_id, 'descricao': descricao, 'valor': valor, 'total_parcelas': parcelas,
             'data_compra': data_compra or mes[:8] + '05', 'mes_fatura': mes, 'categoria_id': categoria, **(extra or {})}
    return rpc('criar_compra', {'p_perfil_id': perfil, 'p_dados': dados, 'p_chave': chave or str(uuid.uuid4())}, usuario)


def previa(cartao_id, descricao, mes, valor, parcelas=1, data_compra=None, categoria=MORADIA):
    dados = {'cartao_id': cartao_id, 'descricao': descricao, 'valor': valor, 'total_parcelas': parcelas,
             'data_compra': data_compra or mes[:8] + '05', 'mes_fatura': mes, 'categoria_id': categoria}
    return ok(rpc('previa_compra', {'p_perfil_id': B, 'p_dados': dados}))


def edicao(lancamento):
    return ok(rpc('compra_para_edicao', {'p_perfil_id': B, 'p_lancamento_id': lancamento}))


def editar(lancamento, dados, versao=None):
    return rpc('editar_compra', {'p_perfil_id': B, 'p_lancamento_id': lancamento,
                                 'p_versao': versao or edicao(lancamento)['versao'], 'p_dados': dados})


def excluir(lancamento, versao=None):
    return rpc('excluir_compra', {'p_perfil_id': B, 'p_lancamento_id': lancamento,
                                  'p_versao': versao or edicao(lancamento)['versao']})


def parcelas(compra_id):
    return banco('select numero_parcela, valor, mes_fatura, data_compra from public.lancamento_agregado '
                 'where compra_id = %s order by numero_parcela', (compra_id,))


def faturas(cartao_id, mes):
    return banco('select id, data_vencimento, valor_planejado, valor_executado, status_pagamento, status_fatura '
                 'from public.conta where is_fatura_cartao and item_despesa_id = %s and cartao_competencia = %s order by id',
                 (cartao_id, mes))


def fatura_tela(cartao_id, mes):
    return next(f for f in ok(rpc('faturas_do_mes', {'p_perfil_id': B, 'p_mes': mes})) if f['cartao_id'] == cartao_id)


def soma(cartao_id, mes):
    """Soma real das compras do cartao no mes (verdade independente do valor gravado na fatura)."""
    return banco('select coalesce(sum(valor), 0) from public.lancamento_agregado where cartao_id = %s and mes_fatura = %s',
                 (cartao_id, mes))[0][0]


def md5_fatura(fatura_id):
    return banco('select md5(t::text) from public.conta t where id = %s', (fatura_id,))[0][0]


def paralelo(funcoes):
    barreira = threading.Barrier(len(funcoes))
    tarefas = [em_thread(lambda f=f: (barreira.wait(60), f())[1]) for f in funcoes]
    for t, _ in tarefas:
        t.join(240)
    return [r.get('valor') for _, r in tarefas]


def protegidos():
    """Registros financeiros fora do Perfil B (Pessoal, Empresa, legado) e saldos/movimentos."""
    return (banco('select count(*) from public.movimento_financeiro')[0][0],
            banco("select md5(coalesce(string_agg(t::text, '|' order by id), '')) from public.conta_bancaria t")[0][0],
            banco("select md5(coalesce(string_agg(t::text, '|' order by id), '')) from public.conta t "
                  "where perfil_financeiro_id is distinct from %s", (B,))[0][0],
            banco("select md5(coalesce(string_agg(t::text, '|' order by id), '')) from public.lancamento_agregado t "
                  "where perfil_financeiro_id is distinct from %s", (B,))[0][0],
            banco("select md5(coalesce(string_agg(t::text, '|' order by id), '')) from public.item_despesa t "
                  "where perfil_financeiro_id is distinct from %s", (B,))[0][0],
            banco("select md5(coalesce(string_agg(t::text, '|' order by id), '')) from public.recorrencia_rejeicao t "
                  "where perfil_financeiro_id is distinct from %s", (B,))[0][0])


def main():
    banco("update public.perfil_financeiro set avatar = 'PB' where id = %s and nome = 'Perfil B' and avatar is null",
          (B,), escrever=True)  # o Flask completa o avatar na 1a leitura; so no perfil ficticio
    inicio = protegidos()

    # 1. Cartoes: cadastro, edicao com versao, dados sensiveis
    c10 = cartao('Cartao Real 10', 10, limite_credito='1000.00')
    c29, c30, c31 = cartao('Cartao Real 29', 29), cartao('Cartao Real 30', 30), cartao('Cartao Real 31', 31)
    lista = ok(rpc('cartoes_do_perfil', {'p_perfil_id': B}))
    texto = json.dumps(lista)
    antigo = next(c for c in lista if c['nome'] == 'Cartao Antigo')
    versao = next(c for c in lista if c['id'] == c10)['versao']
    s_ed = rpc('editar_cartao', {'p_perfil_id': B, 'p_cartao_id': c10, 'p_versao': versao,
                                 'p_dados': {'limite_credito': '1500.00', 'observacoes': 'teste real'}})[0]
    s_velha = rpc('editar_cartao', {'p_perfil_id': B, 'p_cartao_id': c10, 'p_versao': versao, 'p_dados': {'nome': 'X'}})[0]
    s_num = rpc('criar_cartao', {'p_perfil_id': B, 'p_dados': {'nome': 'X', 'dia_fechamento': 1, 'dia_vencimento': 2,
                                                               'numero_cartao': '4111111111111111'},
                                 'p_chave': str(uuid.uuid4())})[0]
    cfg = banco('select limite_credito, numero_cartao, codigo_seguranca from public.config_agregador '
                'where item_despesa_id = %s', (c10,))[0]
    registrar('1. Cadastro e edicao de cartoes',
              antigo['final_numero'] == '8888' and '5555' not in texto and 'numero_cartao' not in texto
              and 'codigo_seguranca' not in texto and (s_ed, s_velha, s_num) == (200, 400, 400)
              and cfg == (Decimal('1500.00'), None, None),
              f'4 cartoes; final 8888 sem numero completo; edicao {s_ed}, versao velha {s_velha}, numero recusado {s_num}')

    # 2. Inativacao sem exclusao do historico
    ctmp = cartao('Cartao Real Inativar', 10)
    r = ok(comprar(ctmp, 'Antes de inativar', '2034-01-01', '40.00'))
    antes = (faturas(ctmp, '2034-01-01'), parcelas(r['compra_id']))
    vt = next(c for c in ok(rpc('cartoes_do_perfil', {'p_perfil_id': B})) if c['id'] == ctmp)['versao']
    s_in = rpc('inativar_cartao', {'p_perfil_id': B, 'p_cartao_id': ctmp, 'p_versao': vt})[0]
    s_nova = comprar(ctmp, 'Depois', '2034-02-01', '1.00')[0]
    na_tela = any(f['cartao_id'] == ctmp for f in ok(rpc('faturas_do_mes', {'p_perfil_id': B, 'p_mes': '2034-01-01'})))
    registrar('2. Inativacao sem excluir historico',
              s_in == 200 and banco('select ativo from public.item_despesa where id = %s', (ctmp,))[0][0] is False
              and (faturas(ctmp, '2034-01-01'), parcelas(r['compra_id'])) == antes and s_nova == 400 and not na_tela,
              f'inativado {s_in}; compra e fatura preservadas; compra nova {s_nova}; fora das faturas do mes')

    # 3 e limites. A vista com limite por categoria; previsto = Contas do mes (sem dupla contagem)
    cc = banco("insert into public.categoria_cartao (nome, ativo, perfil_financeiro_id, created_at, updated_at) "
               "values ('CC Real [teste FIN-CARTOES-REAL-1]', true, %s, now(), now()) returning id", (B,), escrever=True)[0][0]
    banco('insert into public.categoria_cartao_despesa (perfil_financeiro_id, categoria_cartao_id, categoria_id, ativo, '
          'created_at, updated_at) values (%s, %s, %s, true, now(), now())', (B, cc, SAUDE), escrever=True)
    banco('insert into public.cartao_categoria_limite (perfil_financeiro_id, cartao_id, categoria_cartao_id, limite_mensal, '
          'ativo, created_at, updated_at) values (%s, %s, %s, 300, true, now(), now())', (B, c10, cc), escrever=True)
    r = ok(comprar(c10, 'A vista saude', '2034-02-01', '120.00', categoria=SAUDE))
    [f] = faturas(c10, '2034-02-01')
    tela = fatura_tela(c10, '2034-02-01')
    contas = ok(rpc('contas_do_mes', {'p_perfil_id': B, 'p_mes': '2034-02-01'}))
    na_home = [c for c in contas if c['id'] == f[0]]
    cat_cartao = banco('select categoria_cartao_id from public.lancamento_agregado where compra_id = %s',
                       (r['compra_id'],))[0][0]
    registrar('3. Compra a vista + limite por categoria',
              f[1:4] == (D(2034, 2, 10), Decimal('300.00'), Decimal('120.00')) and cat_cartao == cc
              and Decimal(str(tela['valor_executado'])) == Decimal('120.00')
              and Decimal(str(tela['valor_previsto'])) == Decimal('300.00')
              and len(na_home) == 1 and Decimal(str(na_home[0]['valor'])) == Decimal('300.00'),
              'vence 10/02/2034; planejado 300 (limite), executado 120, previsto 300 = Contas do mes (1 linha)')

    # 4. Parcelamento, centavos e previa = gravado
    casos = [('1000.00', 7, ['142.86'] * 5 + ['142.85'] * 2), ('0.05', 3, ['0.02', '0.02', '0.01']),
             ('100.00', 3, ['33.34', '33.33', '33.33'])]
    certos = []
    for valor, n, esperado in casos:
        p = previa(c10, f'Parcelada {valor}', '2034-03-01', valor, n)
        r = ok(comprar(c10, f'Parcelada {valor}', '2034-03-01', valor, n))
        gravado = parcelas(r['compra_id'])
        certos.append([str(x[1]) for x in gravado] == esperado and sum(x[1] for x in gravado) == Decimal(valor)
                      and [(x['mes_fatura'], Decimal(str(x['valor']))) for x in p['parcelas']]
                      == [(x[2].isoformat(), x[1]) for x in gravado])
    registrar('4. Parcelamento e centavos (previa = gravado)', all(certos),
              '1000/7 = 5x142,86 + 2x142,85; 0,05/3 = 0,02+0,02+0,01; 100/3 = 33,34+33,33+33,33')

    # 5. Virada de mes e de ano
    r = ok(comprar(c10, 'Virada', '2034-11-01', '400.00', 4, data_compra='2034-10-31'))
    registrar('5. Virada de mes e ano', [(x[2], x[3]) for x in parcelas(r['compra_id'])] == [
        (D(2034, 11, 1), D(2034, 10, 31)), (D(2034, 12, 1), D(2034, 11, 30)),
        (D(2035, 1, 1), D(2034, 12, 31)), (D(2035, 2, 1), D(2035, 1, 31))], 'faturas 11/2034 a 02/2035; dia 31 -> 30')

    # 6. Vencimentos 29, 30 e 31 (2036 bissexto; 2035 nao)
    venc = {}
    for c, nome in ((c29, 29), (c30, 30), (c31, 31)):
        ok(comprar(c, f'Venc {nome}', '2036-01-01', '30.00', 3))
        venc[nome] = [faturas(c, m)[0][1] for m in ('2036-01-01', '2036-02-01', '2036-03-01')]
    ok(comprar(c29, 'Venc 29 fev', '2035-02-01', '1.00'))
    ok(comprar(c31, 'Venc 31 abr', '2035-04-01', '1.00'))
    extra = (faturas(c29, '2035-02-01')[0][1], faturas(c31, '2035-04-01')[0][1])
    registrar('6. Vencimentos 29/30/31', venc == {
        29: [D(2036, 1, 29), D(2036, 2, 29), D(2036, 3, 29)], 30: [D(2036, 1, 30), D(2036, 2, 29), D(2036, 3, 30)],
        31: [D(2036, 1, 31), D(2036, 2, 29), D(2036, 3, 31)]} and extra == (D(2035, 2, 28), D(2035, 4, 30)),
        '29/02/2036 nos tres; 28/02/2035 (dia 29); 30/04/2035 (dia 31)')

    # 7. Compras simultaneas no mesmo cartao (fatura ainda inexistente)
    rs = paralelo([lambda v=v: comprar(c10, f'Simultanea {v}', '2034-06-01', v) for v in ('10.00', '20.00', '30.00')])
    fs = faturas(c10, '2034-06-01')
    novas = banco("select coalesce(sum(valor), 0) from public.lancamento_agregado where cartao_id = %s "
                  "and descricao like 'Simultanea %%'", (c10,))[0][0]
    registrar('7. Compras simultaneas no mesmo cartao', [x[0] for x in rs] == [200] * 3 and len(fs) == 1
              and novas == Decimal('60.00') and fs[0][3] == soma(c10, '2034-06-01'),
              f'3x 200; faturas 06/2034: {len(fs)}; as 3 somam {novas}; executado {fs[0][3]} = soma real do mes '
              '(inclui parcela de outra compra)')

    # 8. Mesma solicitacao repetida (mesma chave, em paralelo)
    chave = str(uuid.uuid4())
    rs = paralelo([lambda: comprar(c10, 'Repetida', '2034-07-01', '15.00', 3, chave=chave) for _ in range(3)])
    n = banco("select count(*) from public.lancamento_agregado where descricao = 'Repetida' and cartao_id = %s", (c10,))[0][0]
    registrar('8. Repeticao da mesma solicitacao', [x[0] for x in rs] == [200] * 3
              and len({x[1]['compra_id'] for x in rs}) == 1 and n == 3, f'3x 200, 1 compra ({n} parcelas)')

    # 9. Concorrencia com a geracao de recorrencias (Perfil B no gerador novo)
    def gerar():
        st, pv = rpc('previa_geracao', {'p_perfil_id': B, 'p_mes': '2034-08-01'})
        return rpc('gerar_mes', {'p_perfil_id': B, 'p_mes': '2034-08-01', 'p_total_previsto': pv['a_gerar']}) if st == 200 \
            else (st, pv)
    geracao, compra = paralelo([gerar, lambda: comprar(c10, 'Durante a geracao', '2034-08-01', '25.00', 2)])
    refeita = geracao[0] != 200 and 'previa mudou' in str(geracao[1])
    if refeita:
        geracao = gerar()
    dup = banco("select count(*) from (select 1 from public.conta where is_fatura_cartao and perfil_financeiro_id = %s "
                "and cartao_competencia in ('2034-08-01', '2034-09-01') group by item_despesa_id, cartao_competencia "
                "having count(*) > 1) d", (B,))[0][0]
    tela9 = fatura_tela(c10, '2034-08-01')
    n9 = banco("select count(*) from public.lancamento_agregado where cartao_id = %s and mes_fatura = '2034-08-01'",
               (c10,))[0][0]
    registrar('9. Compra x geracao de recorrencias', compra[0] == 200 and geracao[0] == 200 and dup == 0
              and tela9['compras'] == n9 and Decimal(str(tela9['valor_executado'])) == soma(c10, '2034-08-01')
              and len(parcelas(compra[1]['compra_id'])) == 2,
              f'compra {compra[0]}; geracao {geracao[0]}{" (refeita apos previa mudou)" if refeita else ""}; '
              'faturas duplicadas 08-09/2034: 0')

    with tempfile.TemporaryDirectory(prefix='cartoes-real-') as tmp:
        pasta = Path(tmp)
        # 10. Unicidade: Flask inseriu a fatura sem commit; a compra do novo app espera e a reaproveita
        p = Flask(pasta, 'f1', acao='fatura', cartao=c10, competencia='2034-10-01', pausa='antes_do_commit')
        aguardar(pasta, ['f1_inseriu'], [p])
        tarefa, resposta = em_thread(lambda: comprar(c10, 'Espera o Flask', '2034-10-01', '70.00'))
        time.sleep(6)
        esperando = tarefa.is_alive()
        liberar(pasta, 'inseriu')
        devolvida = p.resultado()['fatura']
        tarefa.join(180)
        fs = faturas(c10, '2034-10-01')
        u1 = esperando and resposta['valor'][0] == 200 and [x[0] for x in fs] == [devolvida]             and fs[0][3] == soma(c10, '2034-10-01')
        # Flask consultou (sem fatura); o novo app cria e grava; o Flask reconhece a existente
        p2 = pasta / 'b'
        p2.mkdir()
        pf = Flask(p2, 'g1', acao='compra', pausa='antes_do_insert', dados={
            'cartao_id': c10, 'categoria_id': MORADIA, 'descricao': 'Compra Flask paralela', 'valor': '11.00',
            'data_compra': '2034-12-05', 'mes_fatura': '2034-12-01', 'total_parcelas': 1})
        aguardar(p2, ['g1_consultou'], [pf])
        st = comprar(c10, 'Compra nova paralela', '2034-12-01', '22.00')[0]
        liberar(p2, 'consultou')
        rf = pf.resultado()
        fs = faturas(c10, '2034-12-01')
        ambas = banco("select count(*) from public.lancamento_agregado where cartao_id = %s and mes_fatura = '2034-12-01' "
                      "and descricao in ('Compra Flask paralela', 'Compra nova paralela')", (c10,))[0][0]
        u2 = st == 200 and [x[0] for x in fs] == [rf['fatura']] and ambas == 2 and fs[0][3] == soma(c10, '2034-12-01')
        registrar('10. Unicidade da fatura com o Flask', u1 and u2,
                  f'novo esperou o commit do Flask: {esperando}; 1 fatura reaproveitada; Flask x novo no mesmo mes: '
                  f'1 fatura, executado {fs[0][3]}')

        # 13 (Flask). Compra parcelada criada pelo Flask: lida, comparada, editada e excluida pelo novo app
        p3 = pasta / 'c'
        p3.mkdir()
        rf = Flask(p3, 'h1', acao='compra', dados={
            'cartao_id': c10, 'categoria_id': MORADIA, 'descricao': 'Flask 3x', 'valor': '100.00',
            'data_compra': '2036-07-05', 'mes_fatura': '2036-07-01', 'total_parcelas': 3}).resultado()
    rn = ok(comprar(c10, 'Novo 3x', '2036-07-01', '100.00', 3))
    campos = ('numero_parcela, total_parcelas, valor, mes_fatura, data_compra, categoria_id, categoria_cartao_id, '
              'perfil_financeiro_id, is_recorrente, observacoes')
    flask_parc = banco(f"select {campos} from public.lancamento_agregado where descricao = 'Flask 3x' and cartao_id = %s "
                       'order by numero_parcela', (c10,))
    novo_parc = banco(f'select {campos} from public.lancamento_agregado where compra_id = %s order by numero_parcela',
                      (rn['compra_id'],))
    compras = ok(rpc('compras_da_fatura', {'p_perfil_id': B, 'p_cartao_id': c10, 'p_mes': '2036-08-01'}))
    da_flask = next(x for x in compras if x['descricao'] == 'Flask 3x')
    ed = edicao(da_flask['id'])
    s_e = editar(da_flask['id'], {'descricao': 'Flask 3x editada'})[0]
    editadas = banco("select count(*) from public.lancamento_agregado where descricao = 'Flask 3x editada'")[0][0]
    s_x, corpo_x = excluir(da_flask['id'])
    executado = [faturas(c10, m)[0][3] for m in ('2036-07-01', '2036-08-01', '2036-09-01')]
    registrar('12/13. Compatibilidade com compras do Flask', flask_parc == novo_parc and len(ed['parcelas']) == 3
              and da_flask['pode_editar'] and s_e == 200 and editadas == 3 and s_x == 200 and corpo_x['excluidas'] == 3
              and executado == [Decimal('33.34'), Decimal('33.33'), Decimal('33.33')],
              'parcelas do Flask = parcelas do novo; agrupadas pelo compra_id; editadas (3) e excluidas (3) pelo novo; '
              'faturas recalculadas (so a compra nova fica)')

    # 11. Edicoes simultaneas da mesma versao
    r = ok(comprar(c10, 'Edicao simultanea', '2035-05-01', '50.00'))
    lanc = r['lancamentos'][0]
    v = edicao(lanc)['versao']
    rs = paralelo([lambda x=x: editar(lanc, {'valor': x}, v) for x in ('60.00', '70.00')])
    registrar('14. Edicoes simultaneas', sorted(x[0] for x in rs) == [200, 400]
              and any('alterada por outra operacao' in str(x[1]) for x in rs), 'mesma versao: uma 200, outra 400 (versao)')

    # 15. Fatura paga: desvio, preservacao, bloqueio; pagamento em andamento; fechada x paga
    r = ok(comprar(c10, 'Antes do pagamento', '2035-06-01', '50.00'))
    paga = faturas(c10, '2035-06-01')[0][0]
    banco("update public.conta set status_pagamento = 'Pago', data_pagamento = '2035-07-10' where id = %s", (paga,),
          escrever=True)  # como o pagamento do Flask (status_fatura continua ABERTA)
    md5_paga = md5_fatura(paga)
    pv = previa(c10, 'Depois do pagamento', '2035-06-01', '90.00', 3)
    r2 = ok(comprar(c10, 'Depois do pagamento', '2035-06-01', '90.00', 3))
    meses = [x[2] for x in parcelas(r2['compra_id'])]
    s_ed_paga, erro_paga = editar(r['lancamentos'][0], {'descricao': 'X'})
    s_ex_paga = excluir(r['lancamentos'][0])[0]
    r3 = ok(comprar(c10, 'Parcial', '2035-10-01', '30.00', 3))
    banco("update public.conta set status_pagamento = 'Pago' where is_fatura_cartao and item_despesa_id = %s "
          "and cartao_competencia = '2035-10-01'", (c10,), escrever=True)
    ed_parcial = edicao(r3['lancamentos'][0])
    s_parcial, corpo_parcial = excluir(r3['lancamentos'][0])
    restante = parcelas(r3['compra_id'])
    registrar('11/15. Fatura paga preservada e bloqueada',
              md5_fatura(paga) == md5_paga and meses == [D(2035, 7, 1), D(2035, 8, 1), D(2035, 9, 1)]
              and all(x['redirecionada'] for x in pv['parcelas']) and fatura_tela(c10, '2035-06-01')['situacao'] == 'PAGA'
              and (s_ed_paga, s_ex_paga) == (400, 400) and 'Fatura paga' in str(erro_paga)
              and ed_parcial['abertas'] == 2 and s_parcial == 200
              and corpo_parcial == {'excluidas': 2, 'preservadas': 1} and [x[0] for x in restante] == [1],
              'compra nova desviada para 07-09/2035 (previa avisa); paga intacta; editar/excluir 400; '
              'exclusao parcial: 2 abertas removidas, 1 paga preservada')

    # Pagamento em andamento (transacao propria segurando a fatura)
    import psycopg2
    ok(comprar(c10, 'Fatura sendo paga', '2035-12-01', '10.00'))
    pagando = psycopg2.connect(URL, connect_timeout=15)
    cur = pagando.cursor()
    cur.execute("update public.conta set status_pagamento = 'Pago' where is_fatura_cartao and item_despesa_id = %s "
                "and cartao_competencia = '2035-12-01'", (c10,))
    tarefa, resposta = em_thread(lambda: comprar(c10, 'Durante o pagamento', '2035-12-01', '5.00'))
    time.sleep(6)
    esperando = tarefa.is_alive()
    pagando.commit()
    pagando.close()
    tarefa.join(180)
    st, corpo = resposta['valor']
    registrar('16. Compra durante um pagamento', esperando and st == 400 and 'paga durante o cadastro' in str(corpo)
              and faturas(c10, '2035-12-01')[0][3] == Decimal('10.00'),
              f'esperou a transacao do pagamento: {esperando}; depois recusada ({st}); fatura com 10,00')

    # 17. Fechada x paga: so status_fatura = 'FECHADA' (consolidacao do Flask), nunca inferido do vencimento.
    # FIN-CARTOES-FECHAMENTO-1 (D6): compra em fatura consolidada so com a confirmacao expressa da operacao
    # ({fatura_id, total_consolidado} que o usuario viu), com auditoria e atualizacao controlada da consolidacao.
    r = ok(comprar(c10, 'Fechada', '2036-05-01', '20.00'))
    banco("update public.conta set status_fatura = 'FECHADA', valor_consolidado = valor_executado, "
          "data_consolidacao = now() where is_fatura_cartao and item_despesa_id = %s "
          "and cartao_competencia = '2036-05-01'", (c10,), escrever=True)  # como a consolidacao do Flask
    [fechada] = faturas(c10, '2036-05-01')
    tela = fatura_tela(c10, '2036-05-01')
    s_f, erro_f = editar(r['lancamentos'][0], {'descricao': 'X'})

    def estado_fechada():
        return (md5_fatura(fechada[0]),
                banco("select count(*) from public.lancamento_agregado where cartao_id = %s and mes_fatura = '2036-05-01'",
                      (c10,))[0][0],
                banco('select count(*) from public.fatura_consolidada_inclusao where fatura_id = %s', (fechada[0],))[0][0])

    antes_f = estado_fechada()
    s_sem, erro_sem = comprar(c10, 'Na fechada', '2036-05-01', '1.00')
    erradas = [comprar(c10, 'Na fechada', '2036-05-01', '1.00', extra={'confirmar_consolidadas': conf})[0] for conf in (
        [{'fatura_id': fechada[0], 'total_consolidado': '19.00'}],        # total diferente do consolidado
        [{'fatura_id': fechada[0] + 999999, 'total_consolidado': '20.00'}],  # outra fatura
        True)]                                                              # confirmacao "global"
    sem_mudanca = estado_fechada() == antes_f
    confirmacao = [{'fatura_id': fechada[0], 'total_consolidado': '20.00'}]
    s_com, corpo_com = comprar(c10, 'Na fechada', '2036-05-01', '1.00', extra={'confirmar_consolidadas': confirmacao})
    depois_f = banco('select status_fatura, valor_consolidado, valor_executado from public.conta where id = %s',
                     (fechada[0],))[0]
    auditoria = banco('select operacao, origem, valor_incluido, total_consolidado_anterior, total_consolidado_novo, '
                      'user_id is not null from public.fatura_consolidada_inclusao where fatura_id = %s', (fechada[0],))
    s_reuso, erro_reuso = comprar(c10, 'Na fechada de novo', '2036-05-01', '1.00',
                                  extra={'confirmar_consolidadas': confirmacao})  # total ja mudou
    registrar('17. Fatura fechada: distinta de paga e inclusao so com confirmacao (D6)',
              tela['situacao'] == 'FECHADA' and s_f == 400 and 'fechada' in str(erro_f)
              and s_sem == 400 and isinstance(erro_sem, dict) and erro_sem.get('hint') == 'CONSOLIDADA'
              and erradas == [400, 400, 400] and sem_mudanca
              and s_com == 200 and [x['fatura_id'] for x in corpo_com['consolidadas']] == [fechada[0]]
              and depois_f == ('FECHADA', Decimal('21.00'), Decimal('21.00'))
              and auditoria == [('COMPRA', 'NOVO_APP', Decimal('1.00'), Decimal('20.00'), Decimal('21.00'), True)]
              and s_reuso == 400 and isinstance(erro_reuso, dict) and erro_reuso.get('hint') == 'CONSOLIDADA',
              'FECHADA (status_fatura); edicao 400; sem confirmacao 400 CONSOLIDADA; confirmacoes erradas 400 (nada '
              'mudou); com a confirmacao 200, consolidado 20,00 -> 21,00 e 1 auditoria NOVO_APP; reuso 400')

    # 17a/17b. Fechamento automatico e recorrencia rejeitada por fatura consolidada (FIN-CARTOES-RECORRENCIA-PENDENCIA-1)
    ctx = SimpleNamespace(rpc=rpc, anonimo=anonimo, banco=banco, registrar=registrar, cartao=cartao, B=B, PESSOAL=PESSOAL,
                          EMPRESA=EMPRESA, c10=c10, MORADIA=MORADIA, SAUDE=SAUDE)
    fechamento_automatico(ctx)
    recorrencia_rejeitada(ctx)

    # 18. Autorizacao: gestao, LEITOR, outro perfil, perfil inativo
    venc_ok = comprar(c10, 'X', '2034-01-01', '1.00', usuario='A')[0]  # A nao tem vinculo com o Perfil B
    checks = {
        'A compra no Perfil B': venc_ok,
        'A le compras do Perfil B': rpc('compras_da_fatura', {'p_perfil_id': B, 'p_cartao_id': c10,
                                                              'p_mes': '2034-02-01'}, 'A')[0],
        'A compra no Pessoal com cartao do Perfil B': comprar(c10, 'X', '2034-01-01', '1.00', usuario='A', perfil=PESSOAL)[0],
        'B le faturas do Pessoal': rpc('faturas_do_mes', {'p_perfil_id': PESSOAL, 'p_mes': '2026-11-01'}, 'B')[0],
        'A (LEITOR) le faturas da Empresa': rpc('faturas_do_mes', {'p_perfil_id': EMPRESA, 'p_mes': '2026-11-01'}, 'A')[0],
        'A (LEITOR) cria cartao na Empresa': rpc('criar_cartao', {'p_perfil_id': EMPRESA, 'p_dados': {
            'nome': 'X', 'dia_fechamento': 1, 'dia_vencimento': 2}, 'p_chave': str(uuid.uuid4())}, 'A')[0],
        'A edita compra do Perfil B': rpc('editar_compra', {'p_perfil_id': PESSOAL, 'p_lancamento_id': lanc,
                                                            'p_versao': 'x', 'p_dados': {}}, 'A')[0],
    }
    if INATIVO:
        checks['A cria cartao no perfil inativo'] = rpc('criar_cartao', {'p_perfil_id': INATIVO, 'p_dados': {
            'nome': 'X', 'dia_fechamento': 1, 'dia_vencimento': 2}, 'p_chave': str(uuid.uuid4())}, 'A')[0]
    esperado = {k: (200 if 'le faturas da Empresa' in k else 403) for k in checks}
    registrar('18. Autorizacao (gestor, LEITOR, outro perfil)', checks == esperado,
              '; '.join(f'{k}: {v}' for k, v in checks.items()))

    # 19. Anonimo
    funcoes = {'cartoes_do_perfil': {'p_perfil_id': B}, 'faturas_do_mes': {'p_perfil_id': B, 'p_mes': '2034-02-01'},
               'compras_da_fatura': {'p_perfil_id': B, 'p_cartao_id': c10, 'p_mes': '2034-02-01'},
               'compra_para_edicao': {'p_perfil_id': B, 'p_lancamento_id': lanc},
               'previa_compra': {'p_perfil_id': B, 'p_dados': {}},
               'criar_compra': {'p_perfil_id': B, 'p_dados': {}, 'p_chave': str(uuid.uuid4())},
               'editar_compra': {'p_perfil_id': B, 'p_lancamento_id': lanc, 'p_versao': 'x', 'p_dados': {}},
               'excluir_compra': {'p_perfil_id': B, 'p_lancamento_id': lanc, 'p_versao': 'x'},
               'criar_cartao': {'p_perfil_id': B, 'p_dados': {}, 'p_chave': str(uuid.uuid4())},
               'editar_cartao': {'p_perfil_id': B, 'p_cartao_id': c10, 'p_versao': 'x', 'p_dados': {}},
               'inativar_cartao': {'p_perfil_id': B, 'p_cartao_id': c10, 'p_versao': 'x'}}
    anon = {f: anonimo(f, c) for f, c in funcoes.items()}
    registrar('19. Acesso anonimo bloqueado', set(anon.values()) == {401}, f'11 funcoes: {sorted(set(anon.values()))}')

    # 20. Tabelas legadas e internas fora da Data API
    diretas = {t: tabela_direta(t, p, 'B') for t, p in (('lancamento_agregado', 'public'), ('config_agregador', 'public'),
                                                         ('conta', 'public'), ('operacao_cartao', 'financeiro'))}
    registrar('20. Acesso direto a tabelas bloqueado', all(st != 200 or corpo == [] for st, corpo in diretas.values())
              and all(st != 200 for t, (st, _) in diretas.items() if t != 'operacao_cartao'),
              '; '.join(f'{t}: {st}' for t, (st, _) in diretas.items()))

    # 21. Unicidade geral, registros protegidos, saldos e movimentos
    dup_f = banco("select count(*) from (select 1 from public.conta where is_fatura_cartao group by item_despesa_id, "
                  "cartao_competencia having count(*) > 1) d")[0][0]
    dup_p = banco("select count(*) from (select 1 from public.lancamento_agregado where compra_id is not null "
                  "group by compra_id, numero_parcela having count(*) > 1) d")[0][0]
    registrar('21. Sem duplicidade de faturas e parcelas', dup_f == 0 and dup_p == 0, f'faturas: {dup_f}; parcelas: {dup_p}')
    fim = protegidos()
    registrar('22. Saldos, movimentos e registros fora do Perfil B preservados', fim == inicio,
              f'movimentos: {fim[0]}; contas bancarias, contas, compras, itens e ocorrencias de recorrencia fora do '
              'Perfil B identicos')

    falhas = [n for n, okk in RESULTADOS if not okk]
    print('RESULTADO:', 'OK' if not falhas else f'FALHAS: {falhas}')
    return 1 if falhas else 0


if __name__ == '__main__':
    sys.exit(main())
