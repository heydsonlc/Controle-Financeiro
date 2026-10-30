"""
MOBILE-CONTAS-REAL-1 — equivalencia Flask x fachada no Supabase de teste (dados FICTICIOS).

Pre-requisitos: dados de scripts/supabase_perfis_seed_teste.py e supabase_contas_seed_teste.py,
contas de teste em .env.e2e-real. O Flask (config staging) le o mesmo banco SEM mes_referencia
(sem geracao) e com a baixa de debito automatico neutralizada; a fachada e chamada por REST com o
login real das contas de teste. Nao imprime dados nem credenciais. Exit 0 = nenhuma divergencia.
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
import urllib.error
import urllib.request
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / 'scripts'))
from dotenv import dotenv_values, load_dotenv  # noqa: E402

from tests.supabase_local import CONTAS_MES_ESPERADO  # noqa: E402
from verificar_exposicao_supabase import PROJETO, chave_publica_via_cli  # noqa: E402

load_dotenv(RAIZ / '.env.e2e-real', override=False, encoding='utf-8-sig')
estado = json.loads((RAIZ / 'data' / 'contas_real_1_teste.json').read_text(encoding='utf-8'))
perfis = estado['perfis']
real = {int(k): v for k, v in estado['mapa'].items()}

FLASK = r'''
import json, sys
import backend.services.debito_automatico_service as debito
debito.executar_baixa_debito_automatico = lambda *a, **k: None
from backend.app import create_app
from backend.models import Usuario
app = create_app()
with app.app_context():
    admin = Usuario.query.order_by(Usuario.id).first().id
c = app.test_client()
with c.session_transaction() as s:
    s['_user_id'] = str(admin); s['_fresh'] = True
saida = {}
for pid in sys.argv[1:]:
    assert c.post('/api/perfis-financeiros/ativo', json={'perfil_id': int(pid)}).status_code == 200
    r = c.get('/api/despesas/')
    assert r.status_code == 200, r.data[:200]
    saida[pid] = [{k: x.get(k) for k in ('id', 'valor', 'data_vencimento', 'pago', 'is_fatura_cartao', 'mes_competencia')}
                  for x in r.get_json()['data']]
print('FLASK ' + json.dumps(saida))
'''
env = {**os.environ, **{k: v for k, v in dotenv_values(RAIZ / '.env.staging', encoding='utf-8-sig').items() if v}}
r = subprocess.run([sys.executable, '-c', FLASK, *(str(v) for v in perfis.values())], cwd=RAIZ, env=env,
                   capture_output=True, text=True, timeout=300)
if r.returncode != 0:
    print('FLASK FALHOU:', r.stderr[-1500:].replace(env.get('DATABASE_URL', '###'), '<db-url>'))
    sys.exit(1)
flask = json.loads([l for l in r.stdout.splitlines() if l.startswith('FLASK ')][-1][6:])

ORIG = f'https://{PROJETO}.supabase.co'
chave, _ = chave_publica_via_cli()


def http(caminho, corpo, token=None):
    req = urllib.request.Request(ORIG + caminho, method='POST', data=json.dumps(corpo).encode())
    req.add_header('apikey', chave)
    req.add_header('Content-Type', 'application/json')
    req.add_header('Content-Profile', 'financeiro')
    if token:
        req.add_header('Authorization', f'Bearer {token}')
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, json.loads(resp.read() or b'null')
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b'null')


tokens = {}
for rotulo in 'AB':
    req = urllib.request.Request(f'{ORIG}/auth/v1/token?grant_type=password', method='POST',
                                 data=json.dumps({'email': os.environ[f'CF_EMAIL_{rotulo}'],
                                                  'password': os.environ[f'CF_SENHA_{rotulo}']}).encode())
    req.add_header('apikey', chave)
    req.add_header('Content-Type', 'application/json')
    tokens[rotulo] = json.loads(urllib.request.urlopen(req, timeout=20).read())['access_token']
dono = {'PESSOAL': 'A', 'EMPRESA': 'A', 'PERFIL_B': 'B'}
cent = lambda v: Decimal(str(v)).quantize(Decimal('0.01'))  # noqa: E731
from tests.supabase_local import CONTAS_FICTICIAS  # noqa: E402
inverso = {real[c[0]]: c[0] for c in CONTAS_FICTICIAS}  # so ids de conta: ids repetem entre tabelas
divergencias = 0
for (chave_perfil, mes), esperado in CONTAS_MES_ESPERADO.items():
    pid = perfis[chave_perfil]
    f = {x['id']: x for x in flask[str(pid)] if x['mes_competencia'] == mes}
    st, fach = http('/rest/v1/rpc/contas_do_mes', {'p_perfil_id': pid, 'p_mes': f'{mes}-01'}, tokens[dono[chave_perfil]])
    m = {x['id']: x for x in fach}
    mesmas = set(f) == set(m)
    valores_ok = mesmas and all(cent(m[i]['valor']) == cent(f[i]['valor']) and (m[i]['situacao'] == 'PAGA') == bool(f[i]['pago'])
                                and m[i]['data_vencimento'] == f[i]['data_vencimento'] for i in f)
    zero = Decimal('0.00')
    total_f, pago_f = sum((cent(x['valor']) for x in f.values()), zero), sum((cent(x['valor']) for x in f.values() if x['pago']), zero)
    total_m, pago_m = sum((cent(x['valor']) for x in m.values()), zero), sum((cent(x['valor']) for x in m.values() if x['situacao'] == 'PAGA'), zero)
    esperados_ok = (str(total_m) == esperado['total'] and str(pago_m) == esperado['pago']
                    and {inverso[i]: str(cent(x['valor'])) for i, x in m.items()} == esperado['valores'])
    ok = st == 200 and mesmas and valores_ok and total_f == total_m and pago_f == pago_m and esperados_ok
    divergencias += 0 if ok else 1
    print(f'{chave_perfil:9} {mes} | Flask total {total_f} pago {pago_f} | fachada total {total_m} pago {pago_m} | '
          f'contas {len(m)} | esperado {esperado["total"]}/{esperado["pago"]} | {"OK" if ok else "DIVERGENCIA"}')
print('DIVERGENCIAS:', divergencias)
sys.exit(1 if divergencias else 0)
