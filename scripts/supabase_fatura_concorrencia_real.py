"""
FIN-FATURA-UNICA-REAL-1 — concorrencia REAL Flask x novo aplicativo no Supabase de teste.

So dados FICTICIOS: o "Cartao B" do "Perfil B" temporario (supabase_recorrencia_seed_teste.py,
gerador NOVO). Processos Flask reais (DATABASE_URL do .env.staging) param em barreiras por
arquivo — depois de a consulta dizer "nao existe" e antes do INSERT, ou depois do INSERT e
antes do COMMIT — enquanto o novo aplicativo e chamado pela Data API com login real do
usuario B. Meses de 31 dias: o Flask nao cria fatura de dia 31 em mes de 30 (defeito
conhecido, fora deste escopo).

Pre-requisitos: seeds perfis -> contas -> recorrencia confirmados; .env.e2e-real.
Nao imprime credenciais nem a URL do banco. Remover os dados depois com os seeds (--remover).
"""
# FIN-PUBLICACAO-SEGURA-1: o projeto de teste virou a producao; recusa antes de ler credenciais ou conectar.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from guarda_producao import recusar_em_producao
recusar_em_producao(__file__)
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / 'scripts'))
from dotenv import dotenv_values, load_dotenv  # noqa: E402

from verificar_exposicao_supabase import PROJETO, PROJETOS_PROIBIDOS, chave_publica_via_cli  # noqa: E402

load_dotenv(RAIZ / '.env.e2e-real', override=False, encoding='utf-8-sig')
ENV = {**os.environ, **{k: v for k, v in dotenv_values(RAIZ / '.env.staging', encoding='utf-8-sig').items() if v}}
URL = ENV['DATABASE_URL']
if PROJETO in PROJETOS_PROIBIDOS or any(p in URL for p in PROJETOS_PROIBIDOS):
    raise SystemExit('Projeto proibido.')
ESTADO = json.loads((RAIZ / 'data' / 'recorrencia_real_1_teste.json').read_text(encoding='utf-8'))
PERFIL_B, PESSOAL = ESTADO['perfis']['PERFIL_B'], ESTADO['perfis']['PESSOAL']
CARTAO = ESTADO['itens']['452']
CATEGORIA = json.loads((RAIZ / 'data' / 'contas_real_1_teste.json').read_text(encoding='utf-8'))['mapa']['201']
ORIGEM = f'https://{PROJETO}.supabase.co'

_WORKER = r'''
import json, sys, time
from datetime import date
from pathlib import Path
cfg = json.loads(sys.argv[1])
pasta = Path(cfg['pasta'])

def esperar(etapa):
    (pasta / f"{cfg['nome']}_{etapa}").touch()
    limite = time.time() + 180
    while not (pasta / f'liberar_{etapa}').exists():
        if time.time() > limite:
            raise SystemExit('barreira expirou: ' + etapa)
        time.sleep(0.02)

from flask import session
from backend.app import create_app
from backend.models import db
from backend.services.cartao_service import CartaoService

if cfg.get('pausa') == 'antes_do_insert':
    original = CartaoService.calcular_planejado
    feito = []
    def pausado(cartao_id, competencia):
        if not feito:
            feito.append(1)
            esperar('consultou')
        return original(cartao_id, competencia)
    CartaoService.calcular_planejado = staticmethod(pausado)

app = create_app()
with app.test_request_context():
    session['perfil_financeiro_id'] = cfg['perfil']
    if cfg.get('pausa') == 'antes_do_commit':
        commit_original = db.session.commit
        feito = []
        def commit_pausado():
            if not feito:
                feito.append(1)
                esperar('inseriu')
            return commit_original()
        db.session.commit = commit_pausado
    if cfg['acao'] == 'fatura':
        fatura = CartaoService.get_or_create_fatura(cfg['cartao'], date.fromisoformat(cfg['competencia']))
        print('RESULTADO ' + json.dumps({'fatura': fatura.id}))
    else:
        dados = dict(cfg['dados'])
        dados['data_compra'] = date.fromisoformat(dados['data_compra'])
        lancamento, fatura = CartaoService.adicionar_lancamento(dados)
        print('RESULTADO ' + json.dumps({'lancamento': lancamento.id, 'fatura': fatura.id}))
'''


class Flask:
    def __init__(self, pasta, nome, **cfg):
        self.saida, self.erro = pasta / f'{nome}.out', pasta / f'{nome}.err'
        with open(self.saida, 'w') as saida, open(self.erro, 'w') as erro:
            self.processo = subprocess.Popen(
                [sys.executable, '-c', _WORKER, json.dumps({'pasta': str(pasta), 'nome': nome, 'perfil': PERFIL_B, **cfg})],
                cwd=RAIZ, env=ENV, stdout=saida, stderr=erro, stdin=subprocess.DEVNULL)

    def resultado(self):
        self.processo.wait(timeout=240)
        if self.processo.returncode != 0:
            raise SystemExit('Flask falhou: ' + self.erro.read_text(errors='replace')[-1500:].replace(URL, '<db-url>'))
        return json.loads([l for l in self.saida.read_text().splitlines() if l.startswith('RESULTADO ')][-1][10:])


def aguardar(pasta, nomes, processos, limite=180):
    fim = time.time() + limite
    while not all((pasta / n).exists() for n in nomes):
        for p in processos:
            if p.processo.poll() is not None:
                p.resultado()
        if time.time() > fim:
            raise SystemExit(f'barreira nao alcancada: {nomes}')
        time.sleep(0.05)


def liberar(pasta, etapa):
    (pasta / f'liberar_{etapa}').touch()


def banco(sql, params=(), escrever=False):
    import psycopg2
    conn = psycopg2.connect(URL, connect_timeout=15)
    try:
        if not escrever:
            conn.set_session(readonly=True)
        with conn, conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall() if cur.description else None
    finally:
        conn.close()


CHAVE, _ = chave_publica_via_cli()


def token(rotulo):
    req = urllib.request.Request(f'{ORIGEM}/auth/v1/token?grant_type=password', method='POST', data=json.dumps(
        {'email': os.environ[f'CF_EMAIL_{rotulo}'], 'password': os.environ[f'CF_SENHA_{rotulo}']}).encode())
    req.add_header('apikey', CHAVE)
    req.add_header('Content-Type', 'application/json')
    return json.loads(urllib.request.urlopen(req, timeout=30).read())['access_token']


TOKENS = {'A': token('A'), 'B': token('B')}


def rpc(funcao, corpo, usuario='B'):
    req = urllib.request.Request(f'{ORIGEM}/rest/v1/rpc/{funcao}', method='POST', data=json.dumps(corpo).encode())
    for nome, valor in (('apikey', CHAVE), ('Authorization', f'Bearer {TOKENS[usuario]}'),
                        ('Content-Type', 'application/json'), ('Content-Profile', 'financeiro')):
        req.add_header(nome, valor)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, json.loads(resp.read() or b'null')
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b'null')


def gerar(mes, perfil=PERFIL_B, usuario='B'):
    status, previa = rpc('previa_geracao', {'p_perfil_id': perfil, 'p_mes': mes}, usuario)
    if status != 200:
        return status, previa
    return rpc('gerar_mes', {'p_perfil_id': perfil, 'p_mes': mes, 'p_total_previsto': previa['a_gerar']}, usuario)


def faturas(comp):
    return [r[0] for r in banco('select id from public.conta where item_despesa_id = %s and is_fatura_cartao '
                                'and cartao_competencia = %s order by id', (CARTAO, comp))]


def compra(descricao, mes, parcelas, valor):
    return {'cartao_id': CARTAO, 'valor': valor, 'descricao': descricao, 'data_compra': mes[:8] + '05',
            'mes_fatura': mes, 'categoria_id': CATEGORIA, 'total_parcelas': parcelas}


def em_thread(funcao):
    resultado = {}
    tarefa = threading.Thread(target=lambda: resultado.setdefault('valor', funcao()))
    tarefa.start()
    return tarefa, resultado


RESULTADOS = []


def registrar(nome, ok, detalhe):
    RESULTADOS.append((nome, ok))
    print(f"{'OK ' if ok else 'FALHA'} | {nome} | {detalhe}", flush=True)


def financeiro_intocado():
    return (banco('select count(*) from public.movimento_financeiro')[0][0],
            banco("select md5(coalesce(string_agg(t::text, '|' order by id), '')) from public.conta_bancaria t")[0][0])


def main():
    # O Flask completa o avatar do perfil na primeira leitura; preenchido no perfil FICTICIO para
    # que um processo pausado nao segure a linha (Pessoal e Empresa nao sao tocados).
    banco("update public.perfil_financeiro set avatar = 'PB' where id = %s and nome = 'Perfil B' and avatar is null",
          (PERFIL_B,), escrever=True)
    inicio = financeiro_intocado()
    with tempfile.TemporaryDirectory(prefix='fatura-real-') as tmp:
        pasta = Path(tmp)

        # 1. Flask x Flask
        ps = [Flask(pasta, f'a{i}', acao='fatura', cartao=CARTAO, competencia='2027-07-01', pausa='antes_do_insert')
              for i in (1, 2)]
        aguardar(pasta, ['a1_consultou', 'a2_consultou'], ps)
        liberar(pasta, 'consultou')
        ids = {p.resultado()['fatura'] for p in ps}
        registrar('Flask x Flask', len(faturas('2027-07-01')) == 1 and ids == set(faturas('2027-07-01')),
                  f'faturas 07/2027: {len(faturas("2027-07-01"))}; ids devolvidos: {len(ids)}')

        # 2. Fatura paga + compras posteriores simultaneas (redirecionadas para a seguinte)
        paga = faturas('2027-07-01')[0]
        banco("update public.conta set status_pagamento = 'Pago', status_fatura = 'PAGA', data_pagamento = '2027-07-30' "
              "where id = %s", (paga,), escrever=True)
        md5_paga = banco('select md5(t::text) from public.conta t where id = %s', (paga,))
        pasta2 = pasta / 'paga'
        pasta2.mkdir()
        ps = [Flask(pasta2, n, acao='compra', dados=compra(f'Compra paga {n}', '2027-07-01', 1, '10.00'),
                    pausa='antes_do_insert') for n in ('x', 'y')]
        aguardar(pasta2, ['x_consultou', 'y_consultou'], ps)
        liberar(pasta2, 'consultou')
        for p in ps:
            p.resultado()
        meses = {r[0].isoformat() for r in banco("select mes_fatura from public.lancamento_agregado "
                                                  "where descricao like 'Compra paga %%'")}
        registrar('Fatura paga + compras simultaneas',
                  banco('select md5(t::text) from public.conta t where id = %s', (paga,)) == md5_paga
                  and len(faturas('2027-08-01')) == 1 and meses == {'2027-08-01'},
                  f'paga intacta; faturas 08/2027: {len(faturas("2027-08-01"))}; compras em {sorted(meses)}')

        # 3. Novo x novo
        barreira = threading.Barrier(2)
        tarefas = [em_thread(lambda: (barreira.wait(30), gerar('2027-12-01'))[1]) for _ in range(2)]
        for t, _ in tarefas:
            t.join(180)
        criadas = sorted(r['valor'][1]['criadas']['faturas'] for _, r in tarefas)
        registrar('Novo x novo', criadas == [0, 2] and len(faturas('2027-12-01')) == 1 and len(faturas('2028-01-01')) == 1,
                  f'faturas criadas por chamada: {criadas}')

        # 4. Flask consultou; novo app cria e grava primeiro
        pasta4 = pasta / 'c'
        pasta4.mkdir()
        p = Flask(pasta4, 'c1', acao='fatura', cartao=CARTAO, competencia='2028-03-01', pausa='antes_do_insert')
        aguardar(pasta4, ['c1_consultou'], [p])
        status, r = gerar('2028-03-01')
        liberar(pasta4, 'consultou')
        devolvida = p.resultado()['fatura']
        registrar('Flask consultou, novo criou', status == 200 and faturas('2028-03-01') == [devolvida],
                  f'novo criou {r["criadas"]["faturas"]} fatura(s); Flask recebeu a existente')

        # 5. Flask inseriu sem commit; novo app espera e reconhece
        pasta5 = pasta / 'd'
        pasta5.mkdir()
        p = Flask(pasta5, 'd1', acao='fatura', cartao=CARTAO, competencia='2028-05-01', pausa='antes_do_commit')
        aguardar(pasta5, ['d1_inseriu'], [p])
        tarefa, geracao = em_thread(lambda: gerar('2028-05-01'))
        time.sleep(6)  # o INSERT do novo motor fica preso no indice unico ate o commit do Flask
        esperando = tarefa.is_alive()
        liberar(pasta5, 'inseriu')
        devolvida = p.resultado()['fatura']
        tarefa.join(180)
        status, r = geracao['valor']
        registrar('Flask inseriu sem commit, novo esperou', esperando and status == 200
                  and faturas('2028-05-01') == [devolvida] and r['criadas']['faturas'] == 1,
                  f'novo ficou esperando: {esperando}; criou {r["criadas"]["faturas"]} (so 06/2028); '
                  f'existentes {r["existentes"]}')

        # 6. Compras parceladas simultaneas (2x, julho e agosto/2028)
        pasta6 = pasta / 'e'
        pasta6.mkdir()
        ps = [Flask(pasta6, n, acao='compra', dados=compra(f'Parcelada {n}', '2028-07-01', 2, '300.00'),
                    pausa='antes_do_insert') for n in ('x', 'y')]
        aguardar(pasta6, ['x_consultou', 'y_consultou'], ps)
        liberar(pasta6, 'consultou')
        for p in ps:
            p.resultado()
        parcelas = banco("select descricao, numero_parcela, valor from public.lancamento_agregado "
                         "where descricao like 'Parcelada %%' order by 1, 2")
        somas = {d: sum(v for dd, _, v in parcelas if dd == d) for d in ('Parcelada x', 'Parcelada y')}
        registrar('Compras parceladas simultaneas', len(faturas('2028-07-01')) == 1 and len(faturas('2028-08-01')) == 1
                  and len(parcelas) == 4 and all(str(v) == '300.00' for v in somas.values()),
                  f'faturas 07 e 08/2028: 1 e 1; parcelas: {len(parcelas)}; somas: {sorted(map(str, somas.values()))}')

        # 7. Geracao de recorrencias e compra simultaneas no mesmo mes
        pasta7 = pasta / 'f'
        pasta7.mkdir()
        p = Flask(pasta7, 'f1', acao='compra', dados=compra('Compra outubro', '2028-10-01', 1, '80.00'),
                  pausa='antes_do_insert')
        aguardar(pasta7, ['f1_consultou'], [p])
        status, _ = gerar('2028-10-01')
        liberar(pasta7, 'consultou')
        devolvida = p.resultado()['fatura']
        compras_out = banco("select count(*) from public.lancamento_agregado where cartao_id = %s and mes_fatura = '2028-10-01'",
                            (CARTAO,))[0][0]
        registrar('Recorrencia + compra no mesmo mes', status == 200 and faturas('2028-10-01') == [devolvida]
                  and compras_out == 1, f'1 fatura 10/2028; compras no mes: {compras_out}')

        # 8. Chamadas repetidas
        status, r = gerar('2028-10-01')
        pasta8 = pasta / 'h'
        pasta8.mkdir()
        repetida = Flask(pasta8, 'h1', acao='fatura', cartao=CARTAO, competencia='2028-10-01').resultado()['fatura']
        registrar('Chamadas repetidas', status == 200 and r['criadas']['total'] == 0 and repetida == devolvida,
                  'nova geracao criou 0; Flask devolveu a mesma fatura')

    # 9. Isolamento entre perfis e usuarios
    s1, _ = rpc('gerar_mes', {'p_perfil_id': PERFIL_B, 'p_mes': '2028-10-01', 'p_total_previsto': 0}, 'A')
    s2, _ = rpc('previa_geracao', {'p_perfil_id': PERFIL_B, 'p_mes': '2028-10-01'}, 'A')
    s3, _ = rpc('gerar_mes', {'p_perfil_id': PESSOAL, 'p_mes': '2028-10-01', 'p_total_previsto': 0}, 'B')
    s4, erro = rpc('gerar_mes', {'p_perfil_id': PESSOAL, 'p_mes': '2028-10-01', 'p_total_previsto': 0}, 'A')
    registrar('Isolamento perfis/usuarios', (s1, s2, s3, s4) == (403, 403, 403, 400) and 'sistema atual' in str(erro),
              f'A->Perfil B gerar/previa: {s1}/{s2}; B->Pessoal: {s3}; A->Pessoal (gerador Flask): {s4}')

    # 10. Sem duplicidades e sem efeito financeiro
    dup_faturas = banco("select count(*) from (select 1 from public.conta where is_fatura_cartao group by "
                        "item_despesa_id, cartao_competencia having count(*) > 1) d")[0][0]
    dup_parcelas = banco("select count(*) from (select 1 from public.lancamento_agregado where compra_id is not null "
                         "group by compra_id, numero_parcela having count(*) > 1) d")[0][0]
    registrar('Sem duplicidades', dup_faturas == 0 and dup_parcelas == 0,
              f'grupos de fatura duplicada: {dup_faturas}; parcelas duplicadas: {dup_parcelas}')
    registrar('Saldos e movimentos preservados', financeiro_intocado() == inicio,
              f'movimentos: {financeiro_intocado()[0]}; contas bancarias inalteradas')

    falhas = [n for n, ok in RESULTADOS if not ok]
    print('RESULTADO:', 'OK' if not falhas else f'FALHAS: {falhas}')
    return 1 if falhas else 0


if __name__ == '__main__':
    sys.exit(main())
