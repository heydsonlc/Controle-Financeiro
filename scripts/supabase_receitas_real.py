"""
FIN-RECEITAS-DATA-REAL-1 — testes reais de receitas previstas (com data prevista) no Supabase de teste.

So dados FICTICIOS: escritas no "Perfil B" temporario (usuario B, gestor); leituras e tentativas
negadas no Pessoal/Empresa (usuario A: gestor do Pessoal, LEITOR da Empresa). As operacoes passam
pela Data API real com login real; o banco (postgres) so prepara um recebimento ficticio e confere
resultados. Regra central conferida: previsao nunca vira recebimento, movimento ou saldo.

Pre-requisitos: supabase_despesas_real_limpeza.py marcar; seeds perfis -> receitas; .env.e2e-real.
Nao imprime credenciais nem a URL do banco.
"""
import json
import os
import sys
import threading
import urllib.error
import urllib.request
import uuid
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / 'scripts'))
from dotenv import dotenv_values, load_dotenv  # noqa: E402

from verificar_exposicao_supabase import PROJETO, PROJETOS_PROIBIDOS, chave_publica_via_cli  # noqa: E402

load_dotenv(RAIZ / '.env.e2e-real', override=False, encoding='utf-8-sig')
URL = dotenv_values(RAIZ / '.env.staging', encoding='utf-8-sig')['DATABASE_URL']
if PROJETO in PROJETOS_PROIBIDOS or any(p in URL for p in PROJETOS_PROIBIDOS):
    raise SystemExit('Projeto proibido.')
ORIGEM = f'https://{PROJETO}.supabase.co'
PERFIS = json.loads((RAIZ / 'data' / 'perfis_real_1_teste.json').read_text(encoding='utf-8'))
B, PESSOAL, EMPRESA = PERFIS['id_perfil_b'], PERFIS['ids_existentes_usados']['Pessoal'], PERFIS['ids_existentes_usados']['Empresa']
CHAVE, _ = chave_publica_via_cli()


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


def token(rotulo):
    req = urllib.request.Request(f'{ORIGEM}/auth/v1/token?grant_type=password', method='POST', data=json.dumps(
        {'email': os.environ[f'CF_EMAIL_{rotulo}'], 'password': os.environ[f'CF_SENHA_{rotulo}']}).encode())
    req.add_header('apikey', CHAVE)
    req.add_header('Content-Type', 'application/json')
    return json.loads(urllib.request.urlopen(req, timeout=30).read())['access_token']


TOKENS = {'A': token('A'), 'B': token('B'), None: None}


def rpc(funcao, corpo, usuario='B'):
    req = urllib.request.Request(f'{ORIGEM}/rest/v1/rpc/{funcao}', method='POST', data=json.dumps(corpo).encode())
    for nome, valor in (('apikey', CHAVE), ('Content-Type', 'application/json'), ('Content-Profile', 'financeiro')):
        req.add_header(nome, valor)
    if TOKENS[usuario]:
        req.add_header('Authorization', f'Bearer {TOKENS[usuario]}')
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, json.loads(resp.read() or b'null')
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b'null')


def ok(resposta):
    status, corpo = resposta
    if status != 200:
        raise SystemExit(f'chamada falhou: {status} {corpo}')
    return corpo


def criar(dados, perfil=B, usuario='B', chave=None):
    return rpc('criar_receita', {'p_perfil_id': perfil, 'p_dados': dados, 'p_chave': chave or str(uuid.uuid4())}, usuario)


def edicao(orc, perfil=B, usuario='B'):
    return rpc('receita_para_edicao', {'p_perfil_id': perfil, 'p_orcamento_id': orc}, usuario)


def editar(orc, dados, versao=None, perfil=B, usuario='B'):
    versao = versao or ok(edicao(orc))['versao']
    return rpc('editar_receita', {'p_perfil_id': perfil, 'p_orcamento_id': orc, 'p_versao': versao, 'p_dados': dados}, usuario)


def mes(competencia, perfil=B, usuario='B'):
    return {x['nome']: x for x in ok(rpc('receitas_do_mes', {'p_perfil_id': perfil, 'p_mes': competencia}, usuario))}


def dinheiro():
    return (banco("select md5(coalesce(string_agg(t::text, '|' order by id), '')) from public.conta_bancaria t")[0][0],
            banco("select md5(coalesce(string_agg(t::text, '|' order by id), '')) from public.movimento_financeiro t")[0][0],
            banco("select md5(coalesce(string_agg(t::text, '|' order by id), '')) from public.receita_realizada t")[0][0])


RESULTADOS = []


def registrar(numero, nome, passou, detalhe):
    RESULTADOS.append((numero, nome, passou))
    print(f"{'OK ' if passou else 'FALHA'} | {numero:>2} {nome} | {detalhe}", flush=True)


SALARIO = {'nome': 'Salario real', 'tipo': 'SALARIO_FIXO', 'valor': '5000.00'}


def main():
    inicio = dinheiro()

    # 1-3. Competencia x data prevista
    for numero, nome, comp, data, outro in ((1, 'Out/nov', '2030-10-01', '2030-11-05', '2030-11-01'),
                                            (2, 'Dez/jan', '2030-12-01', '2031-01-05', '2031-01-01'),
                                            (3, 'Mesmo mes', '2031-03-01', '2031-03-20', None)):
        ok(criar({**SALARIO, 'nome': f'Salario {nome}', 'competencia': comp, 'data_prevista': data}))
        linha = mes(comp)[f'Salario {nome}']
        fora = outro is None or f'Salario {nome}' not in mes(outro)
        registrar(numero, f'Competencia x data prevista ({nome})', (linha['data_prevista'], linha['data_prevista_explicita'],
                  linha['situacao']) == (data, True, 'PREVISTA') and fora, f'competencia {comp[:7]}, prevista {data}')

    # 4. Registros antigos (seed sem data): regra do dia da fonte
    antigo = mes('2026-11-01', PESSOAL, 'A')
    registrar(4, 'Registros antigos sem data', (antigo['Freelas']['data_prevista'], antigo['Freelas']['data_prevista_explicita'],
              antigo['Salário (A)']['situacao']) == ('2026-11-20', False, 'PARCIAL'), 'Freelas 20/11 pelo dia da fonte; Salario parcial')

    # 5, 6. Recorrente com regra de data, virada de ano, dia 31 e bissexto
    rec = ok(criar({**SALARIO, 'nome': 'Recorrente real', 'competencia': '2031-12-01', 'data_prevista': '2032-01-31',
                    'recorrente': True}))
    datas = dict(banco('select mes_referencia::text, data_prevista::text from public.receita_orcamento '
                       'where item_receita_id = %s', (rec['item_receita_id'],)))
    registrar(5, 'Recorrente 12 competencias', len(datas) == 12 and datas['2031-12-01'] == '2032-01-31'
              and datas['2032-02-01'] == '2032-03-31', 'dez->31/01, jan->29/02, fev->31/03 (sem deriva)')
    registrar(6, 'Fevereiro bissexto', datas['2032-01-01'] == '2032-02-29', f"competencia 01/2032 prevista {datas['2032-01-01']}")

    # 7. Editar a fonte preserva datas explicitas
    antes = sorted(datas.items())
    e = ok(edicao(rec['previsoes'][0]))
    ok(rpc('editar_fonte_receita', {'p_perfil_id': B, 'p_item_id': rec['item_receita_id'], 'p_versao': e['versao_fonte'],
                                    'p_dados': {'dia_previsto': 10}}))
    depois = sorted(banco('select mes_referencia::text, data_prevista::text from public.receita_orcamento '
                          'where item_receita_id = %s', (rec['item_receita_id'],)))
    registrar(7, 'Datas explicitas preservadas apos editar a fonte', depois == antes, '12 datas identicas')

    # 8. Concorrencia: edicoes da mesma versao e cadastros com a mesma chave
    unica = ok(criar({**SALARIO, 'nome': 'Concorrencia real', 'competencia': '2030-10-01', 'data_prevista': '2030-11-05'}))
    versao = ok(edicao(unica['previsoes'][0]))['versao']
    barreira = threading.Barrier(2)
    respostas = []

    def editar_paralelo(data):
        barreira.wait(30)
        respostas.append(editar(unica['previsoes'][0], {'data_prevista': data}, versao))

    tarefas = [threading.Thread(target=editar_paralelo, args=(d,)) for d in ('2030-11-06', '2030-11-07')]
    for t in tarefas:
        t.start()
    for t in tarefas:
        t.join(120)
    chave = str(uuid.uuid4())
    barreira3 = threading.Barrier(3)
    criados = []

    def criar_paralelo():
        barreira3.wait(30)
        criados.append(criar({**SALARIO, 'nome': 'Paralela real', 'competencia': '2030-10-01'}, chave=chave))

    tarefas = [threading.Thread(target=criar_paralelo) for _ in range(3)]
    for t in tarefas:
        t.start()
    for t in tarefas:
        t.join(120)
    qtd = banco("select count(*) from public.item_receita where nome = 'Paralela real'")[0][0]
    registrar(8, 'Cadastro e edicao concorrentes', sorted(s for s, _ in respostas) == [200, 400] and qtd == 1
              and all(s == 200 for s, _ in criados), f'edicoes paralelas {sorted(s for s, _ in respostas)}; mesma chave x3 -> {qtd}')

    # 9. Receita ja recebida: bloqueada (recebimento ficticio preparado pelo banco)
    recebida = ok(criar({**SALARIO, 'nome': 'Recebida real', 'competencia': '2030-10-01', 'data_prevista': '2030-11-05'}))
    banco("insert into public.receita_realizada (perfil_financeiro_id, item_receita_id, data_recebimento, valor_recebido, "
          "mes_referencia, criado_em, atualizado_em) values (%s, %s, '2030-11-05', 5000, '2030-10-01', now(), now())",
          (B, recebida['item_receita_id']), escrever=True)
    e = ok(edicao(recebida['previsoes'][0]))
    s1, _ = editar(recebida['previsoes'][0], {'data_prevista': '2030-11-10'}, e['versao'])
    s2, _ = rpc('excluir_receita', {'p_perfil_id': B, 'p_orcamento_id': recebida['previsoes'][0], 'p_versao': e['versao']})
    registrar(9, 'Receita ja recebida bloqueada', (s1, s2, e['pode_editar']) == (400, 400, False)
              and mes('2030-10-01')['Recebida real']['situacao'] == 'RECEBIDA', e['bloqueio'])

    # 10. Nenhum movimento ou saldo alterado (o unico recebimento novo e o preparado no item 9)
    fim = dinheiro()
    registrar(10, 'Sem movimentacao bancaria', fim[0] == inicio[0] and fim[1] == inicio[1],
              'contas bancarias e movimentos identicos; recebimentos: so o ficticio do item 9')

    # 11. Autorizacao por perfil
    s_leitor, _ = criar(SALARIO | {'competencia': '2030-10-01'}, EMPRESA, 'A')
    s_outro, _ = criar(SALARIO | {'competencia': '2030-10-01'}, B, 'A')
    s_ler, _ = rpc('receitas_do_mes', {'p_perfil_id': PESSOAL, 'p_mes': '2026-11-01'}, 'B')
    s_anon, _ = rpc('receitas_do_mes', {'p_perfil_id': B, 'p_mes': '2026-11-01'}, None)
    empresa = mes('2026-11-01', EMPRESA, 'A')
    registrar(11, 'Autorizacao por perfil', (s_leitor, s_outro, s_ler, s_anon) == (403, 403, 403, 401)
              and set(empresa) == {'Consultoria'}, 'LEITOR/outro perfil/leitura alheia: 403; anonimo: 401; isolamento ok')

    # Totais pela competencia (nao pela data prevista)
    outubro = mes('2030-10-01')
    previsto = sum(Decimal(str(x['valor_previsto'])) for x in outubro.values() if x['origem'] == 'PREVISAO')
    registrar(12, 'Totais pela competencia', previsto == Decimal('20000.00') and 'Salario Out/nov' not in mes('2030-11-01'),
              f'previsto em 10/2030: {previsto} (4 previsoes de R$ 5.000; nenhuma em 11/2030)')

    falhas = [f'{n} {nome}' for n, nome, passou in RESULTADOS if not passou]
    print('RESULTADO:', 'OK' if not falhas else f'FALHAS: {falhas}')
    return 1 if falhas else 0


if __name__ == '__main__':
    sys.exit(main())
