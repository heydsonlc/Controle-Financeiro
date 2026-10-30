"""FIN-ESCRITOR-UNICO-CONTAS-1 — validacao real do lote 20261106..20261118 no Supabase de teste (fzjmge...), so com dados
ficticios num perfil TEMPORARIO criado pelo proprio aplicativo (criar_perfil como usuario A).

Etapas (cada uma auditavel):
  build                 web/dist com a URL e a chave PUBLICA do projeto de teste; varre segredos e rotas do Flask
  criar                 A cria o perfil temporario pela Data API (gerador NOVO pelo aplicativo); acrescenta o vinculo LEITOR de B
  api                   Contas Bancarias (cadastro, ajuste, transferencia, extrato, conferencia, idempotencia), escritor unico
                        (perfil temporario trocado para FLASK e de volta), quem so le, anonimo, D2 e todas as leituras novas
  ui                    serve o dist (CSP real) e abre as telas no perfil temporario: sem erro de console/CSP, nada para /api/
  limpar [--confirmar]  remove SO o que pertence ao perfil temporario, conferindo a identidade (sem --confirmar: simulacao)
  conferir              impressao digital do banco = a de logo depois da aplicacao (lote_depois.json)

Nunca grava nos perfis 1 (Pessoal), 2 (Empresa), 31 e 39. Nao imprime e-mails, senhas, chaves nem URL do banco.
"""
# FIN-PUBLICACAO-SEGURA-1: o projeto de teste virou a producao; recusa antes de ler credenciais ou conectar.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from guarda_producao import recusar_em_producao
recusar_em_producao(__file__)
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.request
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]  # raiz do projeto (scripts/homologacao_real/..)
WEB = RAIZ / 'web'
AQUI = Path(__file__).resolve().parent
PASTA = RAIZ / 'data' / 'homologacao_real' / 'lote_real'  # estado e retratos locais (data/ fora do Git)
ESTADO = PASTA / 'estado_temporario.json'
for p in (RAIZ, RAIZ / 'scripts', WEB / 'tests' / 'e2e'):
    sys.path.insert(0, str(p))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(RAIZ / '.env.e2e-real', override=False, encoding='utf-8-sig')
PERFIL = 'Validacao Lote 1106-1118 (e2e-real)'
CONTAS = ('Conta Origem (e2e-real)', 'Conta Destino (e2e-real)', 'Conta Origem editada (e2e-real)')
FONTE = 'Salario D2 (e2e-real)'
PROTEGIDOS = {1, 2, 31, 39}
RESULTADOS = []
# Adaptadores e telas que podem citar /api/ (rotas respondidas localmente pela ponte-api.js), por nome.
ROTAS_LOCAIS = {'js/ponte-api.js', 'js/despesas-adaptador.js', 'js/recorrencias-adaptador.js', 'js/cartoes-adaptador.js',
                'js/importar-cartao-adaptador.js', 'js/contas-bancarias-adaptador.js', 'js/lancamentos-adaptador.js',
                'js/financiamentos-adaptador.js', 'js/patrimonio-adaptador.js', 'js/documentos-fiscais-adaptador.js',
                'js/dashboard-adaptador.js', 'js/mobilidade-adaptador.js', 'js/arquivo-comprovante.js',
                'js/receitas-adaptador.js', 'js/categorias-adaptador.js'}


def projeto():
    from verificar_exposicao_supabase import PROJETO
    if not PROJETO.startswith('fzjmge') or PROJETO == 'dshqjhyymtpxpxuntzbz':
        raise SystemExit('Projeto nao e o Supabase de teste: interrompido.')
    return PROJETO


def conectar():
    from supabase_migrations import _url
    import psycopg2
    url, ref = _url()
    if not ref.startswith('fzjmge'):
        raise SystemExit('Conexao nao e o Supabase de teste: interrompido.')
    conn = psycopg2.connect(url, connect_timeout=15)
    conn.autocommit = False
    return conn


def registrar(nome, ok, detalhe=''):
    RESULTADOS.append((nome, ok))
    print(f"{'OK   ' if ok else 'FALHA'} | {nome} | {detalhe}", flush=True)


def build():
    from verificar_exposicao_supabase import chave_publica_via_cli
    origem = f'https://{projeto()}.supabase.co'
    chave, tipo = chave_publica_via_cli()
    if not str(chave).startswith('sb_publishable_'):
        raise SystemExit(f'Chave nao e publicavel ({tipo}): interrompido.')
    r = subprocess.run([shutil.which('node') or 'node', 'scripts/build.mjs'], cwd=WEB, capture_output=True, text=True,
                       env={**os.environ, 'SUPABASE_URL': origem, 'SUPABASE_PUBLISHABLE_KEY': chave})
    print((r.stdout + r.stderr).replace(chave, '<chave-publica>').strip()[-400:])
    if r.returncode:
        raise SystemExit(1)
    dist = WEB / 'dist'
    problemas = []
    for arquivo in dist.rglob('*'):
        if not arquivo.is_file() or arquivo.suffix not in {'.html', '.js', '.css', '.json', ''}:
            continue
        rel = arquivo.relative_to(dist).as_posix()
        if rel.startswith('vendor/'):
            continue
        texto = arquivo.read_text(encoding='utf-8', errors='replace')
        locais = rel.startswith('js/original/') or rel in ROTAS_LOCAIS
        for padrao in (r'sb_secret_', r'service_role', r'postgres(ql)?://', r'DATABASE_URL', r'/api/',
                       r'127\.0\.0\.1', r'localhost', r'onrender\.com', r':5000'):
            if padrao == r'/api/' and locais:
                continue
            if re.search(padrao, texto):
                problemas.append(f'{rel}: {padrao}')
    for nome in ('supabase.js', 'pdf.min.mjs', 'pdf.worker.min.mjs', 'chart.umd.min.js'):
        if re.search(r'sb_secret_[A-Za-z0-9]{10,}', (dist / 'vendor' / nome).read_text(encoding='utf-8', errors='replace')):
            problemas.append(f'vendor/{nome}: chave secreta')
    paginas = sorted(p.name for p in dist.glob('*.html'))
    esperadas = sorted({p.name for p in (WEB / 'src').glob('*.html')} | {p.name for p in (WEB / 'src' / 'paginas').glob('*.html')})
    print('paginas:', len(paginas), paginas)
    print('config.js publico:', 'sb_publishable_' in (dist / 'config.js').read_text(encoding='utf-8'))
    print('problemas (segredos ou Flask):', problemas or 'nenhum')
    if problemas or paginas != esperadas:
        raise SystemExit(f'Build reprovado: interrompido. Esperadas {esperadas}')


def sessao(email, senha, chave, origem):
    corpo = json.dumps({'email': email, 'password': senha}).encode()
    req = urllib.request.Request(f'{origem}/auth/v1/token?grant_type=password', method='POST', data=corpo)
    req.add_header('apikey', chave)
    req.add_header('Content-Type', 'application/json')
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())['access_token']


def rpc(origem, chave, funcao, corpo, token=None):
    req = urllib.request.Request(f'{origem}/rest/v1/rpc/{funcao}', method='POST', data=json.dumps(corpo).encode())
    for k, v in (('apikey', chave), ('Content-Type', 'application/json'), ('Content-Profile', 'financeiro')):
        req.add_header(k, v)
    if token:
        req.add_header('Authorization', f'Bearer {token}')
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b'null')
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b'null')


def contexto():
    from verificar_exposicao_supabase import chave_publica_via_cli
    origem = f'https://{projeto()}.supabase.co'
    chave, _ = chave_publica_via_cli()
    ta = sessao(os.environ['CF_EMAIL_A'], os.environ['CF_SENHA_A'], chave, origem)
    tb = sessao(os.environ['CF_EMAIL_B'], os.environ['CF_SENHA_B'], chave, origem)
    return origem, chave, ta, tb


def usuarios(cur):
    ids = []
    for chave in ('CF_EMAIL_A', 'CF_EMAIL_B'):
        cur.execute('select id from auth.users where lower(email) = lower(%s)', (os.environ[chave],))
        ids.append(str(cur.fetchone()[0]))
    return ids


def identificar(cur, a):
    """O perfil temporario: um so com o nome do teste, criado pelo aplicativo (historico do gerador comeca com
    criar_perfil do usuario A) e fora dos protegidos. Qualquer outra coisa: interrompe."""
    cur.execute('select id from public.perfil_financeiro where nome = %s', (PERFIL,))
    linhas = cur.fetchall()
    if len(linhas) != 1:
        raise SystemExit(f'Esperado exatamente 1 perfil temporario, encontrados {len(linhas)}: interrompido.')
    perfil = linhas[0][0]
    if perfil in PROTEGIDOS:
        raise SystemExit('Perfil protegido: interrompido.')
    cur.execute('select alterado_por, gerador_novo from financeiro.gerador_recorrencia_historico '
                'where perfil_financeiro_id = %s order by id', (perfil,))
    historico = cur.fetchall()
    if not historico or historico[0] != (f'criar_perfil (usuario {a})', 'NOVO'):
        raise SystemExit('Perfil sem a criacao pelo aplicativo no historico: interrompido.')
    return perfil, historico


def criar():
    if ESTADO.exists():
        raise SystemExit('Ja existe um perfil temporario registrado: rode limpar antes.')
    origem, chave, ta, _ = contexto()
    st, r = rpc(origem, chave, 'criar_perfil', {'p_dados': {'nome': PERFIL, 'tipo': 'PESSOAL'}}, ta)
    if st != 200:
        raise SystemExit(f'criar_perfil: {st} {r}')
    conn = conectar()
    try:
        with conn.cursor() as cur:
            a, b = usuarios(cur)
            perfil, historico = identificar(cur, a)
            cur.execute('select user_id::text, papel, pode_gerir from financeiro.perfil_acesso where perfil_financeiro_id = %s', (perfil,))
            if cur.fetchall() != [(a, 'TITULAR', True)]:
                raise SystemExit('Vinculos inesperados no perfil temporario: interrompido.')
            cur.execute("insert into financeiro.perfil_acesso (user_id, perfil_financeiro_id, papel, pode_gerir) "
                        "values (%s, %s, 'LEITOR', false)", (b, perfil))
        conn.commit()
    finally:
        conn.close()
    PASTA.mkdir(parents=True, exist_ok=True)
    ESTADO.write_text(json.dumps({'perfil': perfil}, indent=1), encoding='utf-8')
    print('perfil temporario', perfil, f'"{PERFIL}"', '| historico:', historico, '| + vinculo LEITOR de B')


def atribuir(perfil, gerador):
    """Troca administrativa do gerador SO do perfil temporario (fica no historico, que a limpeza remove)."""
    conn = conectar()
    try:
        with conn.cursor() as cur:
            a, _ = usuarios(cur)
            identificar(cur, a)
            cur.execute('select financeiro.definir_gerador_recorrencia(%s, %s, %s, %s)',
                        (perfil, gerador, 'validacao lote (e2e-real)', 'escritor unico: perfil temporario'))
        conn.commit()
    finally:
        conn.close()


def leituras_do_lote():
    """RPCs de leitura liberadas no build e criadas pelo lote, com os tipos dos argumentos (pg_proc, so leitura)."""
    texto = (WEB / 'tests' / 'unit' / 'build.test.mjs').read_text(encoding='utf-8')
    bloco = texto[texto.index('const RPCS_DE_LEITURA'):]
    liberadas = set(re.findall(r"'(\w+)'", bloco[:bloco.index(']);')]))
    lote = [p for p in sorted((RAIZ / 'supabase' / 'migrations').glob('*.sql')) if '20261106' <= p.name[:8] <= '20261118']
    criadas = {m.group(1) for p in lote for m in re.finditer(r'create function financeiro\.(\w+)\(', p.read_text(encoding='utf-8'))}
    nomes = sorted(liberadas & criadas)
    conn = conectar()
    try:
        with conn.cursor() as cur:
            cur.execute("select p.proname, p.proargnames, array(select format_type(t, null) from unnest(p.proargtypes) t) "
                        "from pg_proc p join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'financeiro' "
                        "and p.proname = any(%s) and has_function_privilege('authenticated', p.oid, 'execute')", (nomes,))
            return {nome: list(zip(args or [], tipos)) for nome, args, tipos in cur.fetchall()}
    finally:
        conn.rollback()
        conn.close()


def api():
    origem, chave, ta, tb = contexto()
    perfil = json.loads(ESTADO.read_text(encoding='utf-8'))['perfil']
    chamar = lambda f, c, t=ta: rpc(origem, chave, f, c, t)  # noqa: E731

    # 1. Contas Bancarias no perfil do novo aplicativo.
    dados = {'instituicao': 'Banco ficticio', 'tipo': 'Conta Corrente', 'cor_display': '#10b981'}
    k = str(uuid.uuid4())
    st, origem_c = chamar('criar_conta_bancaria', {'p_perfil_id': perfil, 'p_dados': {**dados, 'nome': CONTAS[0], 'saldo_inicial': 1000}, 'p_chave': k})
    st2, repetida = chamar('criar_conta_bancaria', {'p_perfil_id': perfil, 'p_dados': {**dados, 'nome': CONTAS[0], 'saldo_inicial': 1000}, 'p_chave': k})
    registrar('criar conta + reenvio com a mesma chave', st == st2 == 200 and repetida.get('id') == origem_c.get('id'),
              f'{st}/{st2} id {origem_c.get("id")}')
    st, destino_c = chamar('criar_conta_bancaria', {'p_perfil_id': perfil, 'p_dados': {**dados, 'nome': CONTAS[1], 'saldo_inicial': 0}, 'p_chave': str(uuid.uuid4())})
    o, d = origem_c['id'], destino_c['id']
    st, aj = chamar('ajustar_saldo_conta', {'p_perfil_id': perfil, 'p_conta_bancaria_id': o, 'p_dados': {
        'valor_final_desejado': 1200, 'data_movimento': '2035-06-02', 'descricao': 'Ajuste (e2e-real)'}, 'p_chave': str(uuid.uuid4())})
    mov = (aj or {}).get('movimento', {}).get('id')
    registrar('ajuste pelo saldo desejado (+200)', st == 200 and mov, f'{st} saldo {(aj or {}).get("conta", {}).get("saldo_atual")}')
    st, _ = chamar('editar_ajuste_conta', {'p_perfil_id': perfil, 'p_conta_bancaria_id': o, 'p_movimento_id': mov, 'p_dados': {'valor': 150}})
    registrar('editar ajuste (150)', st == 200, st)
    k = str(uuid.uuid4())
    corpo_t = {'p_perfil_id': perfil, 'p_dados': {'conta_origem_id': o, 'conta_destino_id': d, 'valor': '250.00',
                                                  'data_movimento': '2035-06-03', 'descricao': 'Transferencia (e2e-real)'}, 'p_chave': k}
    st, t1 = chamar('transferir_entre_contas', corpo_t)
    st2, t2 = chamar('transferir_entre_contas', corpo_t)
    registrar('transferencia + reenvio (um par de movimentos)', st == st2 == 200, f'{st}/{st2}')
    listar = lambda status=None: chamar('contas_bancarias_tela', {'p_perfil_id': perfil, 'p_status': status})[1] or []  # noqa: E731
    saldos = {c['nome']: c['saldo_atual'] for c in listar()}
    registrar('saldos pelos movimentos (900 / 250)', saldos == {CONTAS[0]: 900, CONTAS[1]: 250}, saldos)
    st, ext = chamar('extrato_conta_bancaria', {'p_perfil_id': perfil, 'p_conta_bancaria_id': o, 'p_inicio': None, 'p_fim': None,
                                               'p_limite': 50, 'p_incluir_saldo': True})
    registrar('extrato da origem (ajuste e debito da transferencia)', st == 200 and sorted((m['tipo'], m['origem']) for m in ext) ==
              [('CREDITO', 'AJUSTE'), ('DEBITO', 'TRANSFERENCIA')], [(m['tipo'], m['origem'], m['valor']) for m in ext or []])
    st, conf = chamar('conferir_saldo_conta', {'p_perfil_id': perfil, 'p_conta_bancaria_id': o})
    registrar('conferencia de saldo (so leitura)', st == 200, (conf or {}).get('status') if isinstance(conf, dict) else conf)
    st, _ = chamar('excluir_ajuste_conta', {'p_perfil_id': perfil, 'p_conta_bancaria_id': o, 'p_movimento_id': mov})
    registrar('excluir ajuste', st == 200, st)
    st, ed = chamar('editar_conta_bancaria', {'p_perfil_id': perfil, 'p_conta_bancaria_id': o, 'p_versao': None,
                                              'p_dados': {'nome': CONTAS[2]}})
    registrar('editar cadastro', st == 200 and ed.get('nome') == CONTAS[2], st)

    # 2. Escritor unico: perfil temporario de volta ao Flask -> o novo aplicativo nao grava nada (nem cadastro).
    atribuir(perfil, 'FLASK')
    try:
        for funcao, corpo in (
                ('criar_conta_bancaria', {'p_perfil_id': perfil, 'p_dados': {**dados, 'nome': 'Nao grava (e2e-real)'}, 'p_chave': str(uuid.uuid4())}),
                ('editar_conta_bancaria', {'p_perfil_id': perfil, 'p_conta_bancaria_id': o, 'p_versao': None, 'p_dados': {'status': 'INATIVO'}}),
                ('ajustar_saldo_conta', {'p_perfil_id': perfil, 'p_conta_bancaria_id': o, 'p_dados': {'valor_do_ajuste': 10}, 'p_chave': str(uuid.uuid4())}),
                ('transferir_entre_contas', {**corpo_t, 'p_chave': str(uuid.uuid4())})):
            st, r = chamar(funcao, corpo)
            registrar(f'perfil no Flask: {funcao} recusado', st == 400 and (r or {}).get('hint') == 'SISTEMA_FLASK', f'{st} {(r or {}).get("hint")}')
        lista2 = listar() + (listar('INATIVO') or [])
        registrar('perfil no Flask: nada mudou', sorted((c['nome'], c['saldo_atual'], c['status']) for c in lista2) ==
                  sorted([(CONTAS[2], 900, 'ATIVO'), (CONTAS[1], 250, 'ATIVO')]), [(c['nome'], c['saldo_atual'], c['status']) for c in lista2])
    finally:
        atribuir(perfil, 'NOVO')

    # 3. Quem so le (B, LEITOR) e anonimo.
    st, _ = chamar('contas_bancarias_tela', {'p_perfil_id': perfil, 'p_status': None}, tb)
    registrar('LEITOR le as contas', st == 200, st)
    for funcao, corpo in (('criar_conta_bancaria', {'p_perfil_id': perfil, 'p_dados': {**dados, 'nome': 'Invasao'}, 'p_chave': str(uuid.uuid4())}),
                          ('ajustar_saldo_conta', {'p_perfil_id': perfil, 'p_conta_bancaria_id': o, 'p_dados': {'valor_do_ajuste': 1}, 'p_chave': str(uuid.uuid4())})):
        st, r = chamar(funcao, corpo, tb)
        registrar(f'LEITOR: {funcao} recusado', st in (401, 403) or (r or {}).get('code') == '42501', f'{st} {(r or {}).get("code")}')
    st, _ = rpc(origem, chave, 'contas_bancarias_tela', {'p_perfil_id': perfil, 'p_status': None})
    registrar('anonimo: leitura recusada', st in (401, 403), st)
    st, r = chamar('contas_bancarias_tela', {'p_perfil_id': 31, 'p_status': None}, tb)
    registrar('B nao le perfil alheio (31)', st != 200, f'{st} {(r or {}).get("code")}')

    # 4. D2: previsao 1000, recebido 950 -> previsto 1000, recebido 950, diferenca -50 (nao 1950).
    st, rec = chamar('criar_receita', {'p_perfil_id': perfil, 'p_dados': {'nome': FONTE, 'tipo': 'SALARIO_FIXO', 'valor': '1000.00',
                                                                      'competencia': '2035-06-01', 'dia_previsto': 5}, 'p_chave': str(uuid.uuid4())})
    orc = (rec or {}).get('previsoes', [None])[0]
    st2, _ = chamar('receber_receita', {'p_perfil_id': perfil, 'p_orcamento_id': orc, 'p_dados': {
        'conta_bancaria_id': d, 'data_recebimento': '2035-06-05', 'valor_recebido': '950.00', 'falta': '1000.00'}, 'p_chave': str(uuid.uuid4())})
    st3, dash = chamar('dashboard_resumo_tela', {'p_perfil_id': perfil, 'p_mes_referencia': '2035-06'})
    resumo = ((dash or {}).get('fluxo_caixa') or {}).get('resumo', {})
    registrar('D2 no Dashboard: previsto 1000, recebido 950, diferenca -50',
              (st, st2, st3) == (200, 200, 200) and (resumo.get('receitas_previstas'), resumo.get('receitas_recebidas'),
                                                     resumo.get('diferenca_receitas')) == (1000, 950, -50), (st, st2, st3, resumo))

    # 5. Todas as leituras novas do lote, no perfil temporario.
    padrao = {'integer': None, 'text': None, 'date': None, 'jsonb': {}, 'boolean': None, 'numeric': None}
    for funcao, args in sorted(leituras_do_lote().items()):
        corpo = {n: (perfil if n == 'p_perfil_id' else padrao.get(t)) for n, t in args}
        st, r = chamar(funcao, corpo)
        codigo = (r or {}).get('code') if isinstance(r, dict) else None
        ok = st == 200 or (st == 400 and codigo in ('P0001', '22023', 'P0002'))
        registrar(f'leitura {funcao}', ok, st if st == 200 else f'{st} {codigo} {(r or {}).get("message")}')

    falhas = [n for n, ok in RESULTADOS if not ok]
    print(f'\n{len(RESULTADOS) - len(falhas)}/{len(RESULTADOS)} OK', '| falhas:', falhas or 'nenhuma')
    return 1 if falhas else 0


def complemento():
    """(a) escritor unico com comparacao antes/depois da troca para FLASK; (b) leituras do perfil Empresa (tipo trocado
    pelo proprio aplicativo, atualizar_perfil, no perfil temporario)."""
    origem, chave, ta, _ = contexto()
    perfil = json.loads(ESTADO.read_text(encoding='utf-8'))['perfil']
    chamar = lambda f, c, t=ta: rpc(origem, chave, f, c, t)  # noqa: E731
    listar = lambda status=None: sorted(json.dumps(c, sort_keys=True) for c in (chamar('contas_bancarias_tela', {'p_perfil_id': perfil, 'p_status': status})[1] or []))  # noqa: E731
    contas = [json.loads(c) for c in listar()]
    o = next(c['id'] for c in contas if c['nome'] == CONTAS[2])
    d = next(c['id'] for c in contas if c['nome'] == CONTAS[1])
    antes = (listar(), listar('INATIVO'))
    atribuir(perfil, 'FLASK')
    try:
        for funcao, corpo in (
                ('criar_conta_bancaria', {'p_perfil_id': perfil, 'p_dados': {'nome': 'Nao grava (e2e-real)', 'instituicao': 'X', 'tipo': 'Conta Corrente'}, 'p_chave': str(uuid.uuid4())}),
                ('editar_conta_bancaria', {'p_perfil_id': perfil, 'p_conta_bancaria_id': o, 'p_versao': None, 'p_dados': {'status': 'INATIVO'}}),
                ('ajustar_saldo_conta', {'p_perfil_id': perfil, 'p_conta_bancaria_id': o, 'p_dados': {'valor_do_ajuste': 10}, 'p_chave': str(uuid.uuid4())}),
                ('transferir_entre_contas', {'p_perfil_id': perfil, 'p_dados': {'conta_origem_id': o, 'conta_destino_id': d, 'valor': '1.00'}, 'p_chave': str(uuid.uuid4())})):
            st, r = chamar(funcao, corpo)
            registrar(f'perfil no Flask: {funcao} recusado', st == 400 and (r or {}).get('hint') == 'SISTEMA_FLASK', f'{st} {(r or {}).get("hint")}')
        registrar('perfil no Flask: contas, saldos e situacao identicos antes/depois', (listar(), listar('INATIVO')) == antes,
                  [(c['nome'], c['saldo_atual'], c['status']) for c in contas])
    finally:
        atribuir(perfil, 'NOVO')
    st, r = chamar('atualizar_perfil', {'p_perfil_id': perfil, 'p_dados': {'tipo': 'EMPRESA'}})
    registrar('perfil temporario como Empresa (atualizar_perfil)', st == 200, st)
    for funcao, corpo in (('ir_documentos_empresa_tela', {'p_perfil_id': perfil, 'p_recurso': 'taxonomia', 'p_filtros': {}, 'p_id': None}),
                          ('ir_documentos_empresa_tela', {'p_perfil_id': perfil, 'p_recurso': 'resumo', 'p_filtros': {}, 'p_id': None}),
                          ('ir_documentos_empresa_tela', {'p_perfil_id': perfil, 'p_recurso': None, 'p_filtros': {}, 'p_id': None}),
                          ('lastro_saidas_tela', {'p_perfil_id': perfil, 'p_filtros': {}, 'p_resumo': None}),
                          ('lastro_saidas_tela', {'p_perfil_id': perfil, 'p_filtros': {}, 'p_resumo': True})):
        st, r = chamar(funcao, corpo)
        registrar(f"leitura Empresa {funcao} ({corpo.get('p_recurso') or corpo.get('p_resumo')})", st == 200, st if st == 200 else r)
    falhas = [n for n, ok in RESULTADOS if not ok]
    print(f'{len(RESULTADOS) - len(falhas)}/{len(RESULTADOS)} OK', '| falhas:', falhas or 'nenhuma')
    return 1 if falhas else 0


SPEC = r"""
import { test, expect } from '@playwright/test';
import { trocarPerfil } from '../../tests/e2e/moldura.mjs';

const PAGINAS = ['contas-bancarias.html', 'lancamentos.html', 'financiamentos.html', 'patrimonio.html', 'documentos-fiscais.html',
    'dashboard.html', 'mobilidade.html', 'recorrencias.html', 'contas.html', 'cartoes.html', 'importar-cartao.html', 'receitas.html'];

test('telas do lote no perfil temporario (Supabase de teste real)', async ({ page }) => {
    const erros = [];
    const paraApi = [];
    page.on('console', (m) => { if (m.type() === 'error') erros.push(`${page.url().split('/').pop()}: ${m.text()}`); });
    page.on('pageerror', (e) => erros.push(`${page.url().split('/').pop()}: ${e.message}`));
    page.on('request', (r) => { if (new URL(r.url()).pathname.startsWith('/api/')) paraApi.push(r.url()); });
    await page.goto('/index.html');
    await page.fill('#email', process.env.CF_EMAIL_A);
    await page.fill('#senha', process.env.CF_SENHA_A);
    await page.click('#login-enviar');
    await page.waitForURL('**/contas.html');
    await page.waitForLoadState('networkidle');
    await trocarPerfil(page, process.env.CF_PERFIL_TEMP);
    await page.waitForLoadState('networkidle');
    for (const pagina of PAGINAS) {
        await page.goto('/' + pagina);
        await page.waitForLoadState('networkidle');
        await page.waitForTimeout(1500);
        await page.waitForLoadState('networkidle');
        await expect(page.locator('#perfil-financeiro-name')).toHaveText(process.env.CF_PERFIL_TEMP);
    }
    await page.goto('/contas-bancarias.html');
    await expect(page.locator('#contas-lista .conta-row', { hasText: 'Conta Origem editada (e2e-real)' })).toBeVisible();
    expect(erros).toEqual([]);
    expect(paraApi).toEqual([]);
});
"""

CONFIG = """
import { defineConfig, devices } from '@playwright/test';
export default defineConfig({
    testDir: '.', timeout: 120 * 1000, expect: { timeout: 20 * 1000 }, workers: 1, retries: 0, reporter: [['list']],
    outputDir: './saida', use: { baseURL: process.env.CF_WEB_BASE_URL, trace: 'retain-on-failure' },
    projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
"""


def ui():
    from run_e2e import criar_handler, ler_headers
    from tests.supabase_local import porta_livre
    pasta = WEB / 'test-results' / 'lote_real'
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / 'playwright.real.mjs').write_text(CONFIG, encoding='utf-8')
    (pasta / 'lote_real.spec.mjs').write_text(SPEC, encoding='utf-8')
    dist = WEB / 'dist'
    porta = porta_livre()
    servidor = ThreadingHTTPServer(('127.0.0.1', porta), criar_handler(dist, None, None, ler_headers(dist)))
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    try:
        r = subprocess.run([shutil.which('npx') or 'npx', 'playwright', 'test', '-c', 'test-results/lote_real/playwright.real.mjs'],
                           cwd=WEB, env={**os.environ, 'CF_WEB_BASE_URL': f'http://127.0.0.1:{porta}', 'CF_PERFIL_TEMP': PERFIL},
                           capture_output=True, text=True, encoding='utf-8', errors='replace')
    finally:
        servidor.shutdown()
    saida = r.stdout + r.stderr
    for segredo in filter(None, (os.environ.get(k) for k in ('CF_EMAIL_A', 'CF_EMAIL_B', 'CF_SENHA_A', 'CF_SENHA_B'))):
        saida = saida.replace(segredo, '<oculto>')
    print(saida.strip()[-6000:])
    return r.returncode


def limpar(confirmar):
    estado = json.loads(ESTADO.read_text(encoding='utf-8'))
    conn = conectar()
    try:
        with conn.cursor() as cur:
            a, b = usuarios(cur)
            perfil, _ = identificar(cur, a)
            if perfil != estado['perfil']:
                raise SystemExit('Perfil identificado difere do estado gravado: interrompido.')
            cur.execute('select user_id::text, papel from financeiro.perfil_acesso where perfil_financeiro_id = %s', (perfil,))
            if sorted(cur.fetchall()) != sorted([(a, 'TITULAR'), (b, 'LEITOR')]):
                raise SystemExit('Vinculos do perfil temporario nao sao so os do teste: interrompido.')
            cur.execute('select id, nome from public.conta_bancaria where perfil_financeiro_id = %s', (perfil,))
            contas = cur.fetchall()
            if any(nome not in CONTAS for _, nome in contas):
                raise SystemExit(f'Conta bancaria fora do teste no perfil temporario: interrompido.')
            conta_ids = [i for i, _ in contas]
            cur.execute('select count(*) from public.movimento_financeiro where conta_bancaria_id = any(%s) '
                        'and perfil_financeiro_id is distinct from %s', (conta_ids, perfil))
            if cur.fetchone()[0]:
                raise SystemExit('Movimento de outro perfil nas contas de teste: interrompido.')
            cur.execute('select count(*) from public.item_receita where perfil_financeiro_id = %s and nome <> %s', (perfil, FONTE))
            if cur.fetchone()[0]:
                raise SystemExit('Fonte de receita fora do teste: interrompido.')
            cur.execute("""select table_schema || '.' || table_name from information_schema.columns
                            where column_name = 'perfil_financeiro_id' and table_schema in ('public', 'financeiro')
                              and table_name in (select table_name from information_schema.tables where table_type = 'BASE TABLE')""")
            tabelas = sorted(r[0] for r in cur.fetchall())
            contagem = {}
            for t in tabelas:
                cur.execute(f'select count(*) from {t} where perfil_financeiro_id = %s', (perfil,))
                n = cur.fetchone()[0]
                if n:
                    contagem[t] = n
            print('linhas do perfil temporario por tabela:', contagem)
            comandos = [
                ('movimentos', 'delete from public.movimento_financeiro where perfil_financeiro_id = %s and conta_bancaria_id = any(%s)',
                 [perfil, conta_ids]),
                ('recebimentos', 'delete from public.receita_realizada where perfil_financeiro_id = %s', [perfil]),
                ('previsoes', 'delete from public.receita_orcamento where perfil_financeiro_id = %s', [perfil]),
                ('fontes', 'delete from public.item_receita where perfil_financeiro_id = %s and nome = %s', [perfil, FONTE]),
                ('chaves', 'delete from financeiro.operacao_despesa where perfil_financeiro_id = %s', [perfil]),
                ('chaves_receita', 'delete from financeiro.operacao_receita where perfil_financeiro_id = %s', [perfil]),
                ('contas_bancarias', 'delete from public.conta_bancaria where perfil_financeiro_id = %s and id = any(%s)', [perfil, conta_ids]),
                ('gerador', 'delete from financeiro.gerador_recorrencia where perfil_financeiro_id = %s', [perfil]),
                ('historico_gerador', 'delete from financeiro.gerador_recorrencia_historico where perfil_financeiro_id = %s', [perfil]),
                ('vinculos', 'delete from financeiro.perfil_acesso where perfil_financeiro_id = %s', [perfil]),
                ('perfil', 'delete from public.perfil_financeiro where id = %s and nome = %s', [perfil, PERFIL]),
            ]
            removidos = {}
            for rotulo, sql, params in comandos:
                cur.execute(sql, params)
                removidos[rotulo] = cur.rowcount
            print('removidos:', {k: v for k, v in removidos.items() if v})
            restantes = {}
            for t in tabelas:
                cur.execute(f'select count(*) from {t} where perfil_financeiro_id = %s', (perfil,))
                if cur.fetchone()[0]:
                    restantes[t] = True
            if restantes:
                raise SystemExit(f'Sobraram linhas do perfil temporario: {restantes}: nada removido.')
        if confirmar:
            conn.commit()
            ESTADO.unlink()
            print('CONFIRMADO: perfil temporario e o que era dele removidos.')
        else:
            conn.rollback()
            print('SIMULACAO: nada foi gravado (use --confirmar).')
    finally:
        conn.close()


def conferir():
    r = subprocess.run([sys.executable, str(AQUI / 'digital_lote.py'), str(PASTA / 'final.json')], capture_output=True, text=True)
    print(r.stdout.strip(), r.stderr.strip()[-500:])
    antes = json.loads((AQUI / 'lote_depois.json').read_text(encoding='utf-8'))
    final = json.loads((PASTA / 'final.json').read_text(encoding='utf-8'))
    dif = sorted(k for k in set(antes['tabelas']) | set(final['tabelas']) if antes['tabelas'].get(k) != final['tabelas'].get(k))
    print('tabelas diferentes do retrato pos-aplicacao:', dif or 'nenhuma')
    print('funcoes iguais:', antes['funcoes'] == final['funcoes'], '| migrations iguais:', antes['migrations'] == final['migrations'])
    return 1 if dif or antes['funcoes'] != final['funcoes'] else 0


if __name__ == '__main__':
    etapa = sys.argv[1]
    if etapa == 'build':
        build()
    elif etapa == 'criar':
        criar()
    elif etapa == 'api':
        sys.exit(api())
    elif etapa == 'complemento':
        sys.exit(complemento())
    elif etapa == 'ui':
        sys.exit(ui())
    elif etapa == 'limpar':
        limpar('--confirmar' in sys.argv)
    elif etapa == 'conferir':
        sys.exit(conferir())
