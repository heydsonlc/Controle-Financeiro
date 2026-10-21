"""
FIN-DESPESAS-REAL-1 — testes reais do cadastro/edicao de despesas no Supabase de teste.

So dados FICTICIOS: escritas no "Perfil B" temporario (usuario B, gestor, novo gerador);
leitura e tentativas negadas no Pessoal/Empresa (usuario A: gestor do Pessoal, LEITOR da
Empresa) sem gravar nada neles. As operacoes passam pela Data API real com login real;
o banco (postgres) so prepara estados ficticios (conta paga, movimento, item de consorcio)
e confere resultados. Tambem reproduz, como EVIDENCIA (sem corrigir), a corrida do
pagamento do Flask com uma edicao simultanea (pendencia do FIN-PAGAMENTOS-1).

Pre-requisitos: supabase_despesas_real_limpeza.py marcar; seeds perfis -> contas ->
recorrencia; .env.e2e-real. Depois: limpeza (remover) e removedores dos seeds.
Nao imprime credenciais nem a URL do banco.
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import date
from decimal import Decimal
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
ORIGEM = f'https://{PROJETO}.supabase.co'
CONTAS = json.loads((RAIZ / 'data' / 'contas_real_1_teste.json').read_text(encoding='utf-8'))
REC = json.loads((RAIZ / 'data' / 'recorrencia_real_1_teste.json').read_text(encoding='utf-8'))
PERFIS = json.loads((RAIZ / 'data' / 'perfis_real_1_teste.json').read_text(encoding='utf-8'))
B, PESSOAL, EMPRESA = REC['perfis']['PERFIL_B'], REC['perfis']['PESSOAL'], REC['perfis']['EMPRESA']
MORADIA, SAUDE = CONTAS['mapa']['201'], CONTAS['mapa']['202']
CONTA_EMPRESA_SEED = CONTAS['mapa']['507']  # "Contador 11/2026" (Empresa)
CONTA_PESSOAL_SEED = CONTAS['mapa']['503']  # "Plano de saude" (Pessoal)
CARTAO_B = REC['itens']['452']
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
    return rpc('criar_despesa', {'p_perfil_id': perfil, 'p_dados': dados, 'p_chave': chave or str(uuid.uuid4())}, usuario)


def edicao(conta, perfil=B, usuario='B'):
    return rpc('despesa_para_edicao', {'p_perfil_id': perfil, 'p_conta_id': conta}, usuario)


def editar(conta, dados, versao=None, perfil=B, usuario='B'):
    versao = versao or ok(edicao(conta))['versao']
    return rpc('editar_despesa', {'p_perfil_id': perfil, 'p_conta_id': conta, 'p_versao': versao, 'p_dados': dados}, usuario)


def excluir(conta, versao=None, perfil=B, usuario='B'):
    versao = versao or ok(edicao(conta))['versao']
    return rpc('excluir_despesa', {'p_perfil_id': perfil, 'p_conta_id': conta, 'p_versao': versao}, usuario)


def gerar(mes, perfil=B, usuario='B'):
    previa = ok(rpc('previa_geracao', {'p_perfil_id': perfil, 'p_mes': mes}, usuario))
    return ok(rpc('gerar_mes', {'p_perfil_id': perfil, 'p_mes': mes, 'p_total_previsto': previa['a_gerar']}, usuario)), previa


def contas_mes(mes, perfil=B, usuario='B'):
    return ok(rpc('contas_do_mes', {'p_perfil_id': perfil, 'p_mes': mes}, usuario))


def conta_de(item, competencia):
    linhas = banco('select id from public.conta where item_despesa_id = %s and mes_referencia = %s', (item, competencia))
    return linhas[0][0] if linhas else None


def linha_conta(conta_id):
    return banco('select valor, data_vencimento, mes_referencia, status_pagamento, debito_automatico, conta_bancaria_id, '
                 'descricao from public.conta where id = %s', (conta_id,))


def financeiro():
    return (banco("select md5(coalesce(string_agg(t::text, '|' order by id), '')) from public.conta_bancaria t")[0][0],
            banco('select count(*) from public.movimento_financeiro')[0][0])


def contas_bancarias():
    return {nome: i for i, nome in banco('select id, nome from public.conta_bancaria where id = any(%s)', (PERFIS['contas'],))}


RESULTADOS = []

# Pagamento real do Flask, pausado depois de ler a conta e antes de gravar o movimento.
_PAGAMENTO = r'''
import json, sys, time
from pathlib import Path
cfg = json.loads(sys.argv[1])
pasta = Path(cfg['pasta'])
from backend.app import create_app
from backend.models import Usuario
from backend.services.conta_bancaria_service import ContaBancariaService
original = ContaBancariaService.criar_movimento
def pausado(*a, **k):
    (pasta / 'leu').touch()
    limite = time.time() + 120
    while not (pasta / 'liberar').exists():
        if time.time() > limite:
            raise SystemExit('barreira expirou')
        time.sleep(0.02)
    return original(*a, **k)
ContaBancariaService.criar_movimento = staticmethod(pausado)
app = create_app()
with app.app_context():
    admin = Usuario.query.order_by(Usuario.id).first().id
c = app.test_client()
with c.session_transaction() as s:
    s['_user_id'] = str(admin); s['_fresh'] = True; s['perfil_financeiro_id'] = cfg['perfil']
r = c.post('/api/despesas/%s/pagar' % cfg['conta'], json={'conta_bancaria_id': cfg['conta_bancaria']})
print('RESULTADO ' + json.dumps({'status': r.status_code}))
'''


def corrida_pagamento(conta_bancaria):
    """EVIDENCIA (sem correcao): o Flask le a conta sem trava; uma edicao entre a leitura e a
    gravacao do pagamento faz o movimento usar o valor antigo. Pendencia do FIN-PAGAMENTOS-1."""
    alvo = ok(criar({**AVULSA, 'nome': 'Corrida pagamento'}))
    with tempfile.TemporaryDirectory(prefix='corrida-') as tmp:
        pasta = Path(tmp)
        saida, erro = pasta / 'out.txt', pasta / 'err.txt'
        with open(saida, 'w') as fo, open(erro, 'w') as fe:
            processo = subprocess.Popen([sys.executable, '-c', _PAGAMENTO, json.dumps(
                {'pasta': str(pasta), 'perfil': B, 'conta': alvo['conta_id'], 'conta_bancaria': conta_bancaria})],
                cwd=RAIZ, env=ENV, stdout=fo, stderr=fe, stdin=subprocess.DEVNULL)
        limite = time.time() + 180
        while not (pasta / 'leu').exists():
            if processo.poll() is not None or time.time() > limite:
                raise SystemExit('Flask nao chegou a barreira: ' + erro.read_text(errors='replace')[-800:].replace(URL, '<db-url>'))
            time.sleep(0.05)
        edicao_status, _ = editar(alvo['conta_id'], {'valor': '500.00'})  # o Flask ja leu 350,40
        (pasta / 'liberar').touch()
        processo.wait(timeout=180)
        pagamento = json.loads([l for l in saida.read_text().splitlines() if l.startswith('RESULTADO ')][-1][10:])
    conta = banco('select valor, status_pagamento from public.conta where id = %s', (alvo['conta_id'],))[0]
    movimento = banco('select valor from public.movimento_financeiro where conta_id = %s', (alvo['conta_id'],))
    reproduzida = edicao_status == 200 and pagamento['status'] == 200 and conta == (Decimal('500.00'), 'Pago') \
        and movimento == [(Decimal('350.40'),)]
    print(f"EVIDENCIA | corrida pagamento Flask x edicao | edicao: {edicao_status}; pagamento Flask: {pagamento['status']}; "
          f"conta: R$ {conta[0]} {conta[1]}; movimento: R$ {movimento[0][0] if movimento else None} | "
          f"{'REPRODUZIDA (pendencia confirmada)' if reproduzida else 'nao reproduzida'}", flush=True)


def registrar(numero, nome, passou, detalhe):
    RESULTADOS.append((numero, nome, passou))
    print(f"{'OK ' if passou else 'FALHA'} | {numero:>2} {nome} | {detalhe}", flush=True)


AVULSA = {'nome': 'Conserto real', 'valor': '350.40', 'categoria_id': MORADIA, 'data_vencimento': '2030-07-05'}


def main():
    bancarias = contas_bancarias()
    conta_b, conta_emp = bancarias['Conta Perfil B'], bancarias['Conta Empresa (A)']
    inicio = financeiro()

    # 1, 4. Avulsa com competencia diferente do vencimento
    r = ok(criar({**AVULSA, 'competencia': '2030-06-01', 'descricao': 'Teste real'}))
    junho = [c['id'] for c in contas_mes('2030-06-01')]
    julho = [c['id'] for c in contas_mes('2030-07-01')]
    registrar(1, 'Avulsa', linha_conta(r['conta_id'])[0][:4] == (Decimal('350.40'), date(2030, 7, 5), date(2030, 6, 1),
              'Pendente'), 'pendente, R$ 350,40')
    registrar(4, 'Competencia diferente do vencimento', r['conta_id'] in junho and r['conta_id'] not in julho,
              'vence 05/07/2030, aparece em 06/2030')
    avulsa = r

    # 2, 3, 22. Recorrencias mensal e anual geradas pelo FIN-RECORRENCIA-1
    mensal = ok(criar({**AVULSA, 'nome': 'Condominio real', 'valor': '900.00', 'data_vencimento': '2030-01-31',
                       'recorrente': True, 'tipo_recorrencia': 'mensal'}))
    anual = ok(criar({**AVULSA, 'nome': 'Seguro real', 'valor': '1200.00', 'data_vencimento': '2030-01-15',
                      'recorrente': True, 'tipo_recorrencia': 'anual'}))
    sem_conta = mensal['conta_id'] is None and anual['conta_id'] is None
    resultado, previa = gerar('2030-02-01')
    datas = [str(d[0]) for d in banco('select data_vencimento from public.conta where item_despesa_id = %s order by 1',
                                      (mensal['item_id'],))]
    anuais = banco('select data_vencimento from public.conta where item_despesa_id = %s', (anual['item_id'],))
    registrar(2, 'Recorrencia mensal', sem_conta and datas == ['2030-01-31', '2030-02-28', '2030-03-31'],
              f'cadastro sem conta; geradas pelo FIN-RECORRENCIA-1: {datas}')
    registrar(3, 'Recorrencia anual', [str(a[0]) for a in anuais] == ['2030-01-15'], 'so 15/01/2030 na janela')

    # 5, 6. Categoria e conta bancaria; debito automatico na avulsa
    s1, e1 = criar({**AVULSA, 'categoria_id': 999999999})
    s2, e2 = criar({**AVULSA, 'debito_automatico': True, 'conta_bancaria_id': conta_emp})
    s3, e3 = criar({**AVULSA, 'debito_automatico': True})
    registrar(5, 'Categoria e conta bancaria', (s1, s2, s3) == (400, 400, 400),
              'categoria inexistente, conta da Empresa e debito sem conta: 400')
    deb = ok(criar({**AVULSA, 'nome': 'Debito real', 'debito_automatico': True, 'conta_bancaria_id': conta_b}))
    registrar(6, 'Debito automatico em avulsa', linha_conta(deb['conta_id'])[0][4:6] == (True, conta_b),
              'debito e conta bancaria do Perfil B gravados')

    # 7. Edicao de conta pendente (inclui troca de competencia) e 15 (versao desatualizada)
    versao = ok(edicao(avulsa['conta_id']))['versao']
    ok(editar(avulsa['conta_id'], {'valor': '410.00', 'data_vencimento': '2030-07-12', 'competencia': '2030-08-01'}, versao))
    status_velha, erro_velha = editar(avulsa['conta_id'], {'valor': '1.00'}, versao)
    linha = linha_conta(avulsa['conta_id'])[0]
    registrar(7, 'Edicao de conta pendente', (linha[0], str(linha[1]), str(linha[2])) == (Decimal('410.00'), '2030-07-12', '2030-08-01')
              and avulsa['conta_id'] in [c['id'] for c in contas_mes('2030-08-01')], 'valor, vencimento e competencia')

    # 15. Edicoes concorrentes da mesma versao
    versao = ok(edicao(avulsa['conta_id']))['versao']
    barreira = threading.Barrier(2)
    respostas = []

    def concorrente(valor):
        barreira.wait(30)
        respostas.append(editar(avulsa['conta_id'], {'valor': valor}, versao))

    tarefas = [threading.Thread(target=concorrente, args=(v,)) for v in ('420.00', '430.00')]
    for t in tarefas:
        t.start()
    for t in tarefas:
        t.join(120)
    codigos = sorted(s for s, _ in respostas)
    registrar(15, 'Edicoes concorrentes/desatualizadas', codigos == [200, 400] and status_velha == 400
              and 'alterada por outra operacao' in str(erro_velha),
              f'mesma versao em paralelo: {codigos}; versao velha: {status_velha}')

    # 8. Edicao de recorrencia (vale para as proximas; existentes nao mudam)
    existentes = banco("select md5(string_agg(t::text, '|' order by id)) from public.conta t where item_despesa_id = %s",
                       (mensal['item_id'],))
    conta_fev = conta_de(mensal['item_id'], '2030-02-01')
    ok(rpc('editar_recorrencia', {'p_perfil_id': B, 'p_item_id': mensal['item_id'],
                                  'p_versao': ok(edicao(conta_fev))['versao_recorrencia'],
                                  'p_dados': {'valor': '950.00', 'categoria_id': SAUDE}}))
    gerar('2030-04-01')
    abril = banco("select valor from public.conta where item_despesa_id = %s and mes_referencia = '2030-04-01'",
                  (mensal['item_id'],))
    registrar(8, 'Edicao de recorrencia', banco("select md5(string_agg(t::text, '|' order by id)) from public.conta t "
                                                "where item_despesa_id = %s and mes_referencia <= '2030-03-01'",
                                                (mensal['item_id'],)) == existentes and abril == [(Decimal('950.00'),)],
              'jan-mar intactas; abril gerado com R$ 950,00')

    # 11. Dispensa ao excluir conta recorrente
    conta_mar = conta_de(mensal['item_id'], '2030-03-01')
    excl = ok(excluir(conta_mar))
    gerar('2030-03-01')
    gerar('2030-05-01')
    dispensada = banco("select situacao, motivo from financeiro.recorrencia_competencia where item_despesa_id = %s "
                       "and competencia = '2030-03-01'", (mensal['item_id'],))
    registrar(11, 'Dispensa de competencia recorrente', excl['competencia_dispensada'] and
              conta_de(mensal['item_id'], '2030-03-01') is None and dispensada == [('DISPENSADA', 'Conta excluida pelo usuario')],
              'marco/2030 excluida, dispensada e nao recriada em duas geracoes')

    # 9. Inativacao
    ok(rpc('inativar_recorrencia', {'p_perfil_id': B, 'p_item_id': anual['item_id'],
                                    'p_versao': ok(edicao(conta_de(anual['item_id'], '2030-01-01')))['versao_recorrencia']}))
    previa_futura = ok(rpc('previa_geracao', {'p_perfil_id': B, 'p_mes': '2031-01-01'}))
    registrar(9, 'Inativacao de recorrencia', anual['item_id'] not in {i['item_id'] for i in previa_futura['itens']}
              and conta_de(anual['item_id'], '2030-01-01') is not None, '2031 nao e oferecido; 2030 mantido')

    # 10. Exclusao segura de avulsa
    x = ok(criar({**AVULSA, 'nome': 'Para excluir'}))
    resultado = ok(excluir(x['conta_id']))
    registrar(10, 'Exclusao segura', resultado['item_excluido'] and not banco('select 1 from public.item_despesa where id = %s',
                                                                              (x['item_id'],)), 'conta e item removidos')

    # 12. Conta paga; 13. conta com movimento
    paga = ok(criar({**AVULSA, 'nome': 'Paga real'}))
    banco("update public.conta set status_pagamento = 'Pago', data_pagamento = '2030-07-05' where id = %s",
          (paga['conta_id'],), escrever=True)
    e_paga = ok(edicao(paga['conta_id']))
    s_ed, _ = editar(paga['conta_id'], {'valor': '1.00'}, e_paga['versao'])
    s_ex, _ = excluir(paga['conta_id'], e_paga['versao'])
    registrar(12, 'Bloqueio de conta paga', (s_ed, s_ex, e_paga['pode_editar']) == (400, 400, False)
              and linha_conta(paga['conta_id'])[0][0] == Decimal('350.40'), e_paga['bloqueio'])
    mov = ok(criar({**AVULSA, 'nome': 'Com movimento'}))
    banco("insert into public.movimento_financeiro (conta_bancaria_id, tipo, valor, descricao, data_movimento, conta_id, origem) "
          "values (%s, 'DEBITO', 350.40, 'Movimento de teste', '2030-07-05', %s, 'DESPESA')", (conta_b, mov['conta_id']),
          escrever=True)
    e_mov = ok(edicao(mov['conta_id']))
    s_mov, _ = excluir(mov['conta_id'], e_mov['versao'])
    registrar(13, 'Bloqueio de exclusao com movimento', s_mov == 400 and linha_conta(mov['conta_id']) != [], e_mov['bloqueio'])

    # 14. Faturas e outros modulos
    fatura = banco('select id from public.conta where item_despesa_id = %s and is_fatura_cartao limit 1', (CARTAO_B,))[0][0]
    s_fat, _ = edicao(fatura)
    item_cons = banco("insert into public.item_despesa (nome, tipo, perfil_financeiro_id, categoria_id, ativo, recorrente) "
                      "values ('Consorcio real', 'Consorcio', %s, %s, true, false) returning id", (B, MORADIA), escrever=True)[0][0]
    conta_cons = banco("insert into public.conta (item_despesa_id, perfil_financeiro_id, mes_referencia, descricao, valor, "
                       "data_vencimento, status_pagamento, numero_parcela, total_parcelas, is_fatura_cartao) values "
                       "(%s, %s, '2030-07-01', 'Parcela consorcio', 100, '2030-07-10', 'Pendente', 3, 60, false) returning id",
                       (item_cons, B), escrever=True)[0][0]
    e_cons = ok(edicao(conta_cons))
    s_cons, _ = excluir(conta_cons, e_cons['versao'])
    registrar(14, 'Faturas e outros modulos', s_fat == 403 and s_cons == 400 and not e_cons['pode_editar'],
              f'fatura: {s_fat}; consorcio: {e_cons["bloqueio"]}')

    # 16. Idempotencia (repeticao e concorrencia com a mesma chave)
    chave = str(uuid.uuid4())
    primeira, segunda = ok(criar({**AVULSA, 'nome': 'Idempotente'}, chave=chave)), ok(criar({**AVULSA, 'nome': 'Idempotente'}, chave=chave))
    chave2 = str(uuid.uuid4())
    barreira = threading.Barrier(3)
    paralelas = []

    def mesma_chave():
        barreira.wait(30)
        paralelas.append(criar({**AVULSA, 'nome': 'Idempotente paralelo'}, chave=chave2))

    tarefas = [threading.Thread(target=mesma_chave) for _ in range(3)]
    for t in tarefas:
        t.start()
    for t in tarefas:
        t.join(120)
    qtd = banco("select count(*) from public.item_despesa where nome = 'Idempotente paralelo'")[0][0]
    registrar(16, 'Idempotencia de cadastro', segunda.get('repetida') and segunda['item_id'] == primeira['item_id']
              and qtd == 1 and all(s == 200 for s, _ in paralelas), f'repeticao devolve o mesmo; 3 simultaneas -> {qtd} item')

    # 17-20. Autorizacao
    registrar(17, 'Usuario com gestao', True, 'todas as escritas acima feitas pelo usuario B (gestor do Perfil B)')
    e_emp = ok(edicao(CONTA_EMPRESA_SEED, EMPRESA, 'A'))
    s_c, _ = criar(AVULSA, EMPRESA, 'A')
    s_e, _ = excluir(CONTA_EMPRESA_SEED, e_emp['versao'], EMPRESA, 'A')
    registrar(18, 'Usuario somente leitura', (e_emp['pode_gerir'], e_emp['pode_editar'], s_c, s_e) == (False, False, 403, 403),
              'A (LEITOR da Empresa) ve, mas criar/excluir: 403')
    s1, _ = criar(AVULSA, B, 'A')
    s2, _ = edicao(avulsa['conta_id'], B, 'A')
    s3, _ = edicao(CONTA_PESSOAL_SEED, B, 'B')
    s4, _ = rpc('editar_despesa', {'p_perfil_id': B, 'p_conta_id': CONTA_PESSOAL_SEED, 'p_versao': 'x', 'p_dados': {}})
    s5, _ = criar(AVULSA, PESSOAL, 'B')
    registrar(19, 'Usuario de outro perfil', (s1, s2, s3, s4, s5) == (403, 403, 403, 403, 403),
              'A no Perfil B, B com conta do Pessoal e B no Pessoal: 403')
    anonimos = [rpc(f, c, None)[0] for f, c in (
        ('criar_despesa', {'p_perfil_id': B, 'p_dados': AVULSA, 'p_chave': str(uuid.uuid4())}),
        ('despesa_para_edicao', {'p_perfil_id': B, 'p_conta_id': avulsa['conta_id']}),
        ('categorias_de_despesa', {}))]
    registrar(20, 'Acesso anonimo', all(s == 401 for s in anonimos), f'{anonimos}')

    # 22. Gerador do Flask (T1) e fatura unica
    banco("select financeiro.definir_gerador_recorrencia(%s, 'FLASK', 'FIN-DESPESAS-REAL-1 (teste)', 'cenario T1 temporario')",
          (B,), escrever=True)
    conta_abr = conta_de(mensal['item_id'], '2030-04-01')
    s_t1, e_t1 = excluir(conta_abr)
    s_cal, _ = rpc('editar_recorrencia', {'p_perfil_id': B, 'p_item_id': mensal['item_id'],
                                          'p_versao': ok(edicao(conta_abr))['versao_recorrencia'],
                                          'p_dados': {'data_vencimento': '2030-01-20'}})
    banco("select financeiro.definir_gerador_recorrencia(%s, 'NOVO', 'FIN-DESPESAS-REAL-1 (teste)', 'fim do cenario T1')",
          (B,), escrever=True)
    dup = banco('select count(*) from (select 1 from public.conta where is_fatura_cartao group by item_despesa_id, '
                'cartao_competencia having count(*) > 1) d')[0][0]
    registrar(22, 'Compatibilidade FIN-RECORRENCIA/T1/FATURA-UNICA', (s_t1, s_cal, dup) == (400, 400, 0)
              and 'Flask a recriaria' in str(e_t1), 'gerador Flask: exclusao/calendario 400; 0 faturas duplicadas')

    # 21. Saldos e movimentos (o unico movimento novo e o inserido de proposito no item 13)
    fim = financeiro()
    registrar(21, 'Preservacao de saldos e movimentos', fim == (inicio[0], inicio[1] + 1),
              'contas bancarias identicas; movimentos: so o de teste do item 13')

    corrida_pagamento(conta_b)

    falhas = [f'{n} {nome}' for n, nome, passou in RESULTADOS if not passou]
    print('RESULTADO:', 'OK' if not falhas else f'FALHAS: {falhas}')
    return 1 if falhas else 0


if __name__ == '__main__':
    sys.exit(main())
