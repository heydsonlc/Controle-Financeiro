"""FIN-FINANCIAMENTOS-MOTOR-1 — implantacao da migration 20261123090000 no Supabase de teste (fzjmge...), com dados
FICTICIOS num perfil TEMPORARIO criado pelo aplicativo. Reaproveita lote_real.py (sessao, rpc, perfil temporario).

Etapas:
  inspecionar   so leitura: duplicidades dos indices unicos, objetos a criar ausentes, dependencias presentes, colunas iguais
                ao cluster local, dono das funcoes (BYPASSRLS), saldo_devedor_pelas_parcelas remoto = o que a reversao devolve
  aplicar       aplica SO a 20261123090000 (as migrations locais posteriores ficam fora da pasta durante o push e voltam
                identicas, conferidas por md5)
  api           validacao no perfil temporario (financiamento SAC/TR ficticio, historicas, protecao, amortizacao, escritor)
  limpar [--confirmar]   remove so o que pertence ao perfil temporario, conferindo a identidade
Nunca grava nos perfis 1, 2, 31 e 39. Nao imprime e-mails, senhas, chaves nem URL do banco.
"""
# FIN-PUBLICACAO-SEGURA-1: o projeto de teste virou a producao; recusa antes de ler credenciais ou conectar.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from guarda_producao import recusar_em_producao
recusar_em_producao(__file__)
import hashlib
import json
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import lote_real as L  # noqa: E402

RAIZ = L.RAIZ
MIGRATION = RAIZ / 'supabase' / 'migrations' / '20261123090000_financeiro_financiamentos_motor.sql'
REVERSAO = RAIZ / 'supabase' / 'reversao' / '20261123090000_remover_motor_financiamentos.sql'
PASTA = RAIZ / 'data' / 'homologacao_real' / 'motor_real'  # estado e retratos locais (data/ fora do Git)
L.PERFIL = 'Validacao Motor Financiamentos (e2e-real)'
L.ESTADO = PASTA / 'estado.json'
MARCA = '(e2e-real)'


def ler(sql_texto, params=()):
    import psycopg2.extras
    conn = L.conectar()
    conn.set_session(readonly=True)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql_texto, params)
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def objetos_da_migration():
    t = MIGRATION.read_text(encoding='utf-8')
    criadas = set(re.findall(r'^create (?:or replace )?function financeiro\.(\w+)\(', t, re.M))
    chamadas = set(re.findall(r'financeiro\.(\w+)\(', t)) - criadas
    tabelas = set(re.findall(r'\b(public|financeiro)\.(\w+)\b', t))
    tabelas = {f'{e}.{n}' for e, n in tabelas if n not in criadas and n not in chamadas and n != 'parcela_historica'}
    return criadas, chamadas, tabelas


def colunas_locais(tabelas):
    sys.path.insert(0, str(RAIZ))
    from tests.supabase_local import ClusterLocal, encontrar_pg_bin  # noqa: E402
    import tempfile
    import psycopg2
    with tempfile.TemporaryDirectory(prefix='cfm-cl-') as tmp, ClusterLocal(encontrar_pg_bin(), Path(tmp)) as c:
        c.preparar(contas=False)
        conn = c.conectar()
        with conn.cursor() as cur:
            cur.execute("select table_schema || '.' || table_name, column_name, data_type from information_schema.columns "
                        "where table_schema || '.' || table_name = any(%s) order by 1, 2", (sorted(tabelas),))
            saida = cur.fetchall()
        conn.close()
        return saida


def inspecionar():
    criadas, chamadas, tabelas = objetos_da_migration()
    ok = True

    def item(nome, condicao, detalhe=''):
        nonlocal ok
        ok = ok and condicao
        print(f"{'OK   ' if condicao else 'FALHA'} | {nome} | {detalhe}")

    dup1 = ler('select financiamento_id, numero_parcela, count(*) n from public.financiamento_parcela '
               'group by 1, 2 having count(*) > 1')
    dup2 = ler('select financiamento_parcela_id, count(*) n from public.conta where financiamento_parcela_id is not null '
               'group by 1 having count(*) > 1')
    totais = ler('select (select count(*) from public.financiamento) contratos, (select count(*) from public.financiamento_parcela) parcelas, '
                 '(select count(*) from public.conta where financiamento_parcela_id is not null) despesas')[0]
    item('sem numero de parcela duplicado por contrato', dup1 == [], dup1 or totais)
    item('sem despesa duplicada por parcela', dup2 == [], dup2)
    existentes = {r['proname'] for r in ler("select p.proname from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
                                             "where n.nspname = 'financeiro'")}
    novas = criadas - {'saldo_devedor_pelas_parcelas'}
    item(f'{len(novas)} funcoes novas ausentes no remoto', not (novas & existentes), sorted(novas & existentes))
    item('saldo_devedor_pelas_parcelas existe (sera substituida)', 'saldo_devedor_pelas_parcelas' in existentes)
    faltam = sorted(chamadas - existentes)
    item(f'{len(chamadas)} funcoes de que a migration depende presentes', not faltam, faltam)
    objetos = ler("select to_regclass('financeiro.parcela_historica') t, to_regclass('public.financiamento_parcela_numero_unico') i1, "
                  "to_regclass('public.conta_financiamento_parcela_unica') i2")[0]
    item('tabela e indices novos ausentes', all(v is None for v in objetos.values()), objetos)
    remoto = ler("select table_schema || '.' || table_name t, column_name, data_type from information_schema.columns "
                 "where table_schema || '.' || table_name = any(%s) order by 1, 2", (sorted(tabelas),))
    remoto = [(r['t'], r['column_name'], r['data_type']) for r in remoto]
    local = colunas_locais(tabelas)
    ausentes_remoto = sorted(set(local) - set(remoto))
    item(f'colunas das {len(tabelas)} tabelas usadas iguais ao cluster local', not ausentes_remoto,
         ausentes_remoto[:10] or f'{len(remoto)} colunas; extras no remoto: {len(set(remoto) - set(local))}')
    donos = ler("select distinct r.rolname, r.rolsuper, r.rolbypassrls from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
                "join pg_roles r on r.oid = p.proowner where n.nspname = 'financeiro' and p.prosecdef")
    item('dono das funcoes SECURITY DEFINER passa pelo RLS forcado (BYPASSRLS ou superusuario)',
         all(d['rolbypassrls'] or d['rolsuper'] for d in donos), donos)
    tabela_dono = ler("select r.rolname from pg_class c join pg_roles r on r.oid = c.relowner "
                      "where c.oid = 'public.financiamento_parcela'::regclass")
    item('dono de public.financiamento_parcela', True, tabela_dono)
    corpo = ler("select prosrc from pg_proc where oid = 'financeiro.saldo_devedor_pelas_parcelas(integer)'::regprocedure")[0]['prosrc']
    rev = REVERSAO.read_text(encoding='utf-8')
    m = re.search(r'function financeiro\.saldo_devedor_pelas_parcelas\(.*?\$\$(.*?)\$\$', rev, re.S)
    item('saldo_devedor_pelas_parcelas remoto = o que a reversao devolve (fim de linha normalizado: o remoto guarda CRLF)',
         bool(m) and m.group(1) == corpo.replace('\r\n', '\n'))
    tr = ler('select min(competencia) primeira, max(competencia) ultima, count(*) n from public.indice_tr_mensal')[0]
    item('TR disponivel no remoto', tr['n'] > 0, tr)
    pend = ler('select version from supabase_migrations.schema_migrations order by 1 desc limit 1')
    item('ultima aplicada no remoto = 20261122090000', pend and pend[0]['version'] == '20261122090000', pend)
    print('INSPECAO', 'OK' if ok else 'COM FALHAS')
    return 0 if ok else 1


def md5(p):
    return hashlib.md5(p.read_bytes()).hexdigest()


def aplicar():
    posteriores = sorted(p for p in (RAIZ / 'supabase' / 'migrations').glob('*.sql') if p.name[:14] > '20261123090000')
    guarda = PASTA / 'fora_durante_o_push'
    guarda.mkdir(parents=True, exist_ok=True)
    somas = {p.name: md5(p) for p in posteriores}
    for p in posteriores:
        shutil.move(str(p), str(guarda / p.name))
    try:
        r = subprocess.run([sys.executable, str(RAIZ / 'scripts' / 'supabase_migrations.py'), 'aplicar', '--versoes', '20261123090000'],
                           capture_output=True, text=True, cwd=RAIZ, timeout=600)
        print('\n'.join(l for l in (r.stdout + r.stderr).splitlines() if 'Supabase CLI' not in l and 'recommend' not in l)[-2500:])
    finally:
        for nome in somas:
            shutil.move(str(guarda / nome), str(RAIZ / 'supabase' / 'migrations' / nome))
        voltaram = {nome: md5(RAIZ / 'supabase' / 'migrations' / nome) for nome in somas}
        print('migrations posteriores de volta, identicas:', voltaram == somas, sorted(somas))
    return r.returncode


NOME = f'Financiamento Validacao SAC-TR {MARCA}'
CONTA = f'Conta Financiamento {MARCA}'
CONTRATO = {
    'nome': NOME, 'produto': 'SFH', 'sistema_amortizacao': 'SAC', 'indexador_saldo': 'TR', 'valor_financiado': 300000,
    'prazo_total_meses': 23, 'taxa_juros_nominal_anual': 9.38, 'data_contrato': '2024-05-20',
    'data_primeira_parcela': '2024-06-05', 'seguro_modo': 'fixo', 'taxa_administracao_fixa': 25,
    'vigencias_seguro': [{'competencia_inicio': '2024-06', 'valor_mensal': 120.10},
                         {'competencia_inicio': '2025-03', 'valor_mensal': 131.45}],
}


def historico(fid):
    """Parcelas 1-6 (historicas) e as despesas delas, linha a linha (md5), e os movimentos dessas parcelas."""
    return {
        'parcelas': ler('select numero_parcela, md5(p::text) h from public.financiamento_parcela p '
                        'where financiamento_id = %s and numero_parcela <= 6 order by 1', (fid,)),
        'despesas': ler('select p.numero_parcela, md5(c::text) h from public.conta c join public.financiamento_parcela p '
                        'on p.id = c.financiamento_parcela_id where p.financiamento_id = %s and p.numero_parcela <= 6 order by 1', (fid,)),
        'movimentos': ler('select count(*) n from public.movimento_financeiro m join public.financiamento_parcela p '
                          'on p.id = m.financiamento_parcela_id where p.financiamento_id = %s and p.numero_parcela <= 6', (fid,))[0]['n'],
        'registro': ler('select md5(string_agg(h::text, \'|\' order by parcela_id)) h, count(*) n from financeiro.parcela_historica h '
                        'where financiamento_id = %s', (fid,))[0],
    }


def protecao_com_privilegio_real(fid, perfil):
    """Como o dono das tabelas e das funcoes SECURITY DEFINER (postgres, sem superusuario, com BYPASSRLS): UPDATE, DELETE e
    TRUNCATE do registro e INSERT incoerente sao recusados. Tudo numa transacao desfeita no fim."""
    import psycopg2
    conn = L.conectar()
    resultados = {}
    try:
        with conn.cursor() as cur:
            cur.execute('select current_user, (select rolsuper from pg_roles where rolname = current_user), '
                        '(select rolbypassrls from pg_roles where rolname = current_user)')
            resultados['papel'] = cur.fetchone()
            cur.execute("select id from public.financiamento_parcela where financiamento_id = %s and numero_parcela = 12", (fid,))
            pendente = cur.fetchone()[0]
            for nome, comando, params in (
                    ('update', 'update financeiro.parcela_historica set conta_id = null where financiamento_id = %s', (fid,)),
                    ('delete', 'delete from financeiro.parcela_historica where financiamento_id = %s', (fid,)),
                    ('truncate', 'truncate financeiro.parcela_historica', ()),
                    ('insert_incoerente', 'insert into financeiro.parcela_historica (parcela_id, financiamento_id, perfil_financeiro_id, '
                                          "registrado_por) values (%s, %s, %s, '00000000-0000-0000-0000-000000000000')",
                     (pendente, fid, perfil))):
                cur.execute('savepoint t')
                try:
                    cur.execute(comando, params)
                    resultados[nome] = 'ACEITO'
                except psycopg2.Error as e:
                    resultados[nome] = (e.diag.message_hint or e.pgerror.split('\n')[0])
                cur.execute('rollback to savepoint t')
    finally:
        conn.rollback()
        conn.close()
    return resultados


def api():
    origem, chave, ta, tb = L.contexto()
    perfil = json.loads(L.ESTADO.read_text(encoding='utf-8'))['perfil']
    chamar = lambda f, c, t=ta: L.rpc(origem, chave, f, c, t)  # noqa: E731
    k = lambda: str(uuid.uuid4())  # noqa: E731
    registrar = L.registrar
    contratos_fora = ler('select count(*) n, coalesce(md5(string_agg(md5(f::text), \'\' order by f.id)), \'\') h '
                         'from public.financiamento f where perfil_financeiro_id <> %s', (perfil,))[0]

    # 1. Cadastro SAC/TR e reenvio com a mesma chave.
    ch = k()
    s1, r1 = chamar('criar_financiamento', {'p_perfil_id': perfil, 'p_dados': CONTRATO, 'p_chave': ch})
    s2, r2 = chamar('criar_financiamento', {'p_perfil_id': perfil, 'p_dados': CONTRATO, 'p_chave': ch})
    fid = (r1 or {}).get('data', {}).get('id')
    n = ler('select count(*) p, (select count(*) from public.conta c join public.financiamento_parcela q on q.id = c.financiamento_parcela_id '
            'where q.financiamento_id = %s) d, (select count(*) from public.financiamento where nome = %s) f '
            'from public.financiamento_parcela where financiamento_id = %s', (fid, NOME, fid))[0]
    registrar('cadastro SAC/TR + reenvio pela mesma chave (um contrato, 23 parcelas, 23 despesas)',
              (s1, s2) == (200, 200) and bool(r2.get('repetida')) and (n['f'], n['p'], n['d']) == (1, 23, 23), (s1, s2, n))

    # 2. Parcelas historicas 1-6: pagas, sem movimento; saldo = saldo da 6a.
    st, r = chamar('registrar_parcelas_historicas', {'p_perfil_id': perfil, 'p_id': fid, 'p_dados': {'ate_parcela': 6}, 'p_chave': k()})
    h0 = historico(fid)
    saldo6 = ler('select saldo_devedor_apos_pagamento s from public.financiamento_parcela where financiamento_id = %s and numero_parcela = 6',
                 (fid,))[0]['s']
    atual = ler('select saldo_devedor_atual s from public.financiamento where id = %s', (fid,))[0]['s']
    registrar('6 historicas registradas, sem movimento, saldo = o da 6a', st == 200 and r.get('registradas') == 6
              and h0['movimentos'] == 0 and h0['registro']['n'] == 6 and atual == saldo6, (st, r.get('registradas'), atual, saldo6))
    pagas = ler("select count(*) n from public.financiamento_parcela p join public.conta c on c.financiamento_parcela_id = p.id "
                "where p.financiamento_id = %s and p.numero_parcela <= 6 and p.status = 'pago' and c.status_pagamento = 'Pago'", (fid,))[0]['n']
    registrar('parcelas e despesas historicas quitadas', pagas == 6, pagas)

    # 3. Protecao sob os privilegios reais do banco (dono das funcoes SECURITY DEFINER).
    p = protecao_com_privilegio_real(fid, perfil)
    registrar('UPDATE/DELETE/TRUNCATE do registro recusados ao dono das tabelas (postgres, BYPASSRLS)',
              p['update'] == p['delete'] == p['truncate'] == 'HISTORICO_PERMANENTE' and p['papel'][1] is False, p)
    registrar('registro incoerente (parcela pendente) recusado', p['insert_incoerente'] == 'HISTORICO_INCOERENTE', p['insert_incoerente'])
    req_status = acesso_direto(origem, chave, ta)
    registrar('navegador nao le nem escreve a tabela do registro', req_status in (401, 403, 404), req_status)

    # 4. Re-registro e regeneracao nao mexem no historico.
    st, r = chamar('registrar_parcelas_historicas', {'p_perfil_id': perfil, 'p_id': fid, 'p_dados': {'ate_parcela': 6}, 'p_chave': k()})
    sg, rg = chamar('regenerar_parcelas_financiamento', {'p_perfil_id': perfil, 'p_id': fid})
    registrar('re-registro registra 0; regeneracao recusada (COM_EXECUCAO); historico identico',
              st == 200 and r.get('registradas') == 0 and rg.get('hint') == 'COM_EXECUCAO' and historico(fid) == h0, (r.get('registradas'), sg, rg.get('hint')))

    # 5. Paga a 7 em Despesas; amortiza (reduzir parcela) e depois reduz prazo: historico e a 7 intactos, saldo continuo.
    _, banco = chamar('criar_conta_bancaria', {'p_perfil_id': perfil, 'p_dados': {
        'nome': CONTA, 'instituicao': 'Banco ficticio', 'tipo': 'Conta Corrente', 'saldo_inicial': 100000}, 'p_chave': k()})
    d7 = ler('select c.id, c.valor from public.conta c join public.financiamento_parcela p on p.id = c.financiamento_parcela_id '
             'where p.financiamento_id = %s and p.numero_parcela = 7', (fid,))[0]
    sp, pg = chamar('pagar_despesa', {'p_perfil_id': perfil, 'p_conta_id': d7['id'], 'p_chave': k(), 'p_dados': {
        'conta_bancaria_id': banco['id'], 'data_pagamento': '2024-12-05', 'valor_pago': str(d7['valor']), 'valor_devido': str(d7['valor'])}})
    linha7 = lambda: ler('select md5(p::text) h from public.financiamento_parcela p where financiamento_id = %s and numero_parcela = 7', (fid,))  # noqa: E731
    p7 = linha7()
    saldo7 = ler('select saldo_devedor_apos_pagamento s from public.financiamento_parcela where financiamento_id = %s and numero_parcela = 7',
                 (fid,))[0]['s']
    registrar('parcela 7 paga em Despesas (movimento)', sp == 200 and bool(pg.get('movimento_id')), sp)
    sa, ra = chamar('registrar_amortizacao_extra', {'p_perfil_id': perfil, 'p_id': fid, 'p_chave': k(),
                                                     'p_dados': {'data': '2024-12-20', 'valor': 50000, 'tipo': 'reduzir_parcela'}})
    atual = ler('select saldo_devedor_atual s from public.financiamento where id = %s', (fid,))[0]['s']
    registrar('amortizacao (reduzir parcela): saldo = saldo da 7a - 50.000; historico e a 7 intactos',
              sa == 200 and atual == saldo7 - 50000 and historico(fid) == h0 and linha7() == p7, (sa, atual, saldo7))
    sb, rb = chamar('registrar_amortizacao_extra', {'p_perfil_id': perfil, 'p_id': fid, 'p_chave': k(),
                                                     'p_dados': {'data': '2025-01-03', 'valor': 20000, 'tipo': 'reduzir_prazo'}})
    amort = ler('select count(*) n, sum(valor) v from public.financiamento_amortizacao_extra where financiamento_id = %s', (fid,))[0]
    atual = ler('select saldo_devedor_atual s, (select financeiro.saldo_devedor_pelas_parcelas(%s)) c from public.financiamento where id = %s',
                (fid, fid))[0]
    registrar('reduzir prazo: as duas amortizacoes ficam; saldo continuo (= pela cadeia); historico e a 7 intactos',
              sb == 200 and amort['n'] == 2 and atual['s'] == saldo7 - 70000 and atual['s'] == atual['c']
              and historico(fid) == h0 and linha7() == p7, (sb, rb.get('hint') if isinstance(rb, dict) else rb, amort, atual))
    sx, rx = chamar('registrar_amortizacao_extra', {'p_perfil_id': perfil, 'p_id': fid, 'p_chave': k(),
                                                     'p_dados': {'data': '2024-12-25', 'valor': 1000, 'tipo': 'reduzir_parcela'}})
    registrar('amortizacao anterior a uma ja registrada: recusada', rx.get('hint') == 'AMORTIZACAO_POSTERIOR', (sx, rx.get('hint')))

    # 6. Simulacao de quitacao nao grava.
    antes = ler('select md5(string_agg(md5(p::text), \'\' order by p.id)) h from public.financiamento_parcela p where financiamento_id = %s', (fid,))
    sq, rq = chamar('simular_quitacao', {'p_perfil_id': perfil, 'p_id': fid, 'p_dados': {'data_quitacao': '2025-02-10'}})
    registrar('simulacao de quitacao sem gravar', sq == 200 and antes == ler(
        'select md5(string_agg(md5(p::text), \'\' order by p.id)) h from public.financiamento_parcela p where financiamento_id = %s', (fid,)),
        sq)

    # 7. Escritor unico e quem so le.
    L.atribuir(perfil, 'FLASK')
    try:
        s, r = chamar('registrar_amortizacao_extra', {'p_perfil_id': perfil, 'p_id': fid, 'p_chave': k(),
                                                      'p_dados': {'data': '2025-03-10', 'valor': 100, 'tipo': 'reduzir_parcela'}})
        registrar('perfil no Flask: amortizacao recusada (SISTEMA_FLASK)', r.get('hint') == 'SISTEMA_FLASK', (s, r.get('hint')))
        s, r = chamar('criar_financiamento', {'p_perfil_id': perfil, 'p_dados': {**CONTRATO, 'nome': 'Nao grava'}, 'p_chave': k()})
        registrar('perfil no Flask: cadastro recusado (SISTEMA_FLASK)', r.get('hint') == 'SISTEMA_FLASK', (s, r.get('hint')))
    finally:
        L.atribuir(perfil, 'NOVO')
    s, _ = chamar('registrar_amortizacao_extra', {'p_perfil_id': perfil, 'p_id': fid, 'p_chave': k(),
                                                  'p_dados': {'data': '2025-03-10', 'valor': 100, 'tipo': 'reduzir_parcela'}}, tb)
    registrar('LEITOR nao amortiza', s in (401, 403), s)

    # 8. Exclusao com execucao: recusada; historico intacto. Contratos fora do perfil temporario: intactos.
    se, re_ = chamar('excluir_financiamento', {'p_perfil_id': perfil, 'p_id': fid})
    registrar('exclusao com execucao recusada (COM_EXECUCAO)', re_.get('hint') == 'COM_EXECUCAO' and historico(fid) == h0, (se, re_.get('hint')))
    depois_fora = ler('select count(*) n, coalesce(md5(string_agg(md5(f::text), \'\' order by f.id)), \'\') h '
                      'from public.financiamento f where perfil_financeiro_id <> %s', (perfil,))[0]
    registrar('nenhum contrato fora do perfil temporario tocado', depois_fora == contratos_fora, depois_fora)
    falhas = [nome for nome, ok in L.RESULTADOS if not ok]
    print(f'{len(L.RESULTADOS) - len(falhas)}/{len(L.RESULTADOS)} OK', '| falhas:', falhas or 'nenhuma')
    return 1 if falhas else 0


def acesso_direto(origem, chave, token):
    import urllib.error
    import urllib.request
    req = urllib.request.Request(f'{origem}/rest/v1/parcela_historica?select=*', method='GET')
    for k, v in (('apikey', chave), ('Authorization', f'Bearer {token}'), ('Accept-Profile', 'financeiro')):
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status
    except urllib.error.HTTPError as exc:
        return exc.code


def limpar(confirmar):
    """Remove so o que pertence ao perfil temporario. O registro historico e permanente (gatilho): para apagar as linhas
    FICTICIAS do perfil temporario, o gatilho de linha e desligado SO dentro desta transacao, a exclusao e limitada ao
    perfil, e o gatilho e religado antes do commit (conferido)."""
    estado = json.loads(L.ESTADO.read_text(encoding='utf-8'))
    conn = L.conectar()
    try:
        with conn.cursor() as cur:
            a, b = L.usuarios(cur)
            perfil, _ = L.identificar(cur, a)
            if perfil != estado['perfil'] or perfil in L.PROTEGIDOS:
                raise SystemExit('Perfil identificado difere do estado gravado: interrompido.')
            cur.execute('select user_id::text, papel from financeiro.perfil_acesso where perfil_financeiro_id = %s', (perfil,))
            if sorted(cur.fetchall()) != sorted([(a, 'TITULAR'), (b, 'LEITOR')]):
                raise SystemExit('Vinculos do perfil temporario nao sao so os do teste: interrompido.')
            for tabela, condicao in (('financiamento', f"nome <> '{NOME}'"), ('conta_bancaria', f"nome <> '{CONTA}'")):
                cur.execute(f'select count(*) from public.{tabela} where perfil_financeiro_id = %s and {condicao}', (perfil,))
                if cur.fetchone()[0]:
                    raise SystemExit(f'{tabela} fora do teste no perfil temporario: interrompido.')
            cur.execute("""select table_schema || '.' || table_name from information_schema.columns
                            where column_name = 'perfil_financeiro_id' and table_schema in ('public', 'financeiro')
                              and table_name in (select table_name from information_schema.tables where table_type = 'BASE TABLE')""")
            tabelas = sorted(r[0] for r in cur.fetchall())
            contagem = {}
            for t in tabelas:
                cur.execute(f'select count(*) from {t} where perfil_financeiro_id = %s', (perfil,))
                if (n := cur.fetchone()[0]):
                    contagem[t] = n
            print('linhas do perfil temporario por tabela:', contagem)
            cur.execute('select count(*) from financeiro.parcela_historica where perfil_financeiro_id <> %s', (perfil,))
            fora = cur.fetchone()[0]
            p = [perfil]
            cur.execute('alter table financeiro.parcela_historica disable trigger parcela_historica_protegida')
            comandos = [
                ('registro_historico', 'delete from financeiro.parcela_historica where perfil_financeiro_id = %s', p),
                ('pagamentos', 'delete from financeiro.pagamento_fatura where perfil_financeiro_id = %s', p),
                ('movimentos', 'delete from public.movimento_financeiro where perfil_financeiro_id = %s', p),
                ('amortizacoes', 'delete from public.financiamento_amortizacao_extra where perfil_financeiro_id = %s', p),
                ('ajustes', 'delete from public.financiamento_ajuste_saldo where perfil_financeiro_id = %s', p),
                ('vigencias', 'delete from public.financiamento_seguro_vigencia where perfil_financeiro_id = %s', p),
                ('faixas', 'delete from public.financiamento_seguro_faixa_mip where perfil_financeiro_id = %s', p),
                ('vinculo_parcela_despesa', 'update public.financiamento_parcela set conta_id = null where perfil_financeiro_id = %s', p),
                ('contas', 'delete from public.conta where perfil_financeiro_id = %s', p),
                ('parcelas', 'delete from public.financiamento_parcela where perfil_financeiro_id = %s', p),
                ('contratos', 'delete from public.financiamento where perfil_financeiro_id = %s', p),
                ('itens', 'delete from public.item_despesa where perfil_financeiro_id = %s', p),
                ('chaves', 'delete from financeiro.operacao_despesa where perfil_financeiro_id = %s', p),
                ('contas_bancarias', 'delete from public.conta_bancaria where perfil_financeiro_id = %s', p),
                ('gerador', 'delete from financeiro.gerador_recorrencia where perfil_financeiro_id = %s', p),
                ('historico_gerador', 'delete from financeiro.gerador_recorrencia_historico where perfil_financeiro_id = %s', p),
                ('vinculos', 'delete from financeiro.perfil_acesso where perfil_financeiro_id = %s', p),
                ('perfil', 'delete from public.perfil_financeiro where id = %s and nome = %s', [perfil, L.PERFIL]),
            ]
            removidos = {}
            for rotulo, comando, params in comandos:
                cur.execute(comando, params)
                removidos[rotulo] = cur.rowcount
            cur.execute('alter table financeiro.parcela_historica enable trigger parcela_historica_protegida')
            cur.execute("select tgenabled from pg_trigger where tgrelid = 'financeiro.parcela_historica'::regclass "
                        "and tgname in ('parcela_historica_protegida', 'parcela_historica_sem_truncate') order by tgname")
            gatilhos = [r[0] for r in cur.fetchall()]
            cur.execute('select count(*) from financeiro.parcela_historica where perfil_financeiro_id <> %s', (perfil,))
            if cur.fetchone()[0] != fora or gatilhos != ['O', 'O']:
                raise SystemExit('Registro de outro perfil afetado ou gatilho desligado: nada removido.')
            print('removidos:', {k: v for k, v in removidos.items() if v}, '| gatilhos religados:', gatilhos)
            restantes = {}
            for t in tabelas:
                cur.execute(f'select count(*) from {t} where perfil_financeiro_id = %s', (perfil,))
                if cur.fetchone()[0]:
                    restantes[t] = True
            if restantes:
                raise SystemExit(f'Sobraram linhas do perfil temporario: {restantes}: nada removido.')
        if confirmar:
            conn.commit()
            L.ESTADO.unlink()
            print('CONFIRMADO: perfil temporario e o que era dele removidos.')
        else:
            conn.rollback()
            print('SIMULACAO: nada foi gravado (use --confirmar).')
    finally:
        conn.close()


if __name__ == '__main__':
    PASTA.mkdir(parents=True, exist_ok=True)
    etapa = sys.argv[1]
    if etapa == 'inspecionar':
        sys.exit(inspecionar())
    if etapa == 'aplicar':
        sys.exit(aplicar())
    if etapa == 'criar':
        L.PASTA = PASTA
        L.criar()
    if etapa == 'api':
        sys.exit(api())
    if etapa == 'limpar':
        limpar('--confirmar' in sys.argv)
