"""FIN-CATEGORIAS-RECORRENCIAS-2 — implantacao da migration 20261125090000 no Supabase de teste (fzjmge...), com dados
FICTICIOS num perfil TEMPORARIO criado pelo aplicativo. Reaproveita lote_real.py e motor_real.py.

Etapas:
  inspecionar   so leitura: as 6 funcoes remotas = o que a reversao devolve = ultima definicao local anterior; cada
                diferenca da nova definicao esta num trecho marcado; guarda do escritor preservada; objetos novos
                ausentes; dependencias presentes; nenhum comando de dados; catalogo e semanais existentes (informativo)
  aplicar       aplica SO a 20261125090000 (as locais posteriores ficam fora da pasta durante o push e voltam identicas)
  criar | api | ui | limpar [--confirmar]
Nunca grava nos perfis 1, 2, 31 e 39 nem no catalogo global. Nao imprime e-mails, senhas, chaves nem URL do banco.
"""
# FIN-PUBLICACAO-SEGURA-1: o projeto de teste virou a producao; recusa antes de ler credenciais ou conectar.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from guarda_producao import recusar_em_producao
recusar_em_producao(__file__)
import datetime as dt
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import lote_real as L  # noqa: E402
import motor_real as M  # noqa: E402

RAIZ = L.RAIZ
VERSAO = '20261125090000'
ANTERIOR = '20261124090000'
MIGRATION = RAIZ / 'supabase' / 'migrations' / f'{VERSAO}_financeiro_categorias_recorrencias.sql'
REVERSAO = RAIZ / 'supabase' / 'reversao' / f'{VERSAO}_categorias_recorrencias_anterior.sql'
PASTA = RAIZ / 'data' / 'homologacao_real' / 'cr_real'  # estado e retratos locais (data/ fora do Git)
L.PERFIL = 'Validacao Categorias Recorrencias (e2e-real)'
L.ESTADO = PASTA / 'estado.json'
MARCA = '(e2e-real)'
MARCA_MIG = 'FIN-CATEGORIAS-RECORRENCIAS-2'
SUBSTITUIDAS = ['plano_recorrencia', 'gerar_mes_interno', 'ler_dados_despesa', 'excluir_despesa', 'recorrencias_do_perfil',
                'receita_orcamento_flask']
TABELAS_NOVAS = ['financeiro.recorrencia_ocorrencia', 'financeiro.catalogo_categorias', 'financeiro.gestor_catalogo',
                 'financeiro.operacao_catalogo']
SEMANAL = f'Diarista {MARCA}'
QUINZENAL = f'Jardinagem {MARCA}'
FONTE = f'Salario base {MARCA}'
BICO = f'Bico {MARCA}'
CONTA_B = f'Conta Receitas {MARCA}'
CARTAO = f'Cartao {MARCA}'
D = dt.date


def defs(texto):
    return {m.group(1): m.group(2) for m in re.finditer(
        r'create (?:or replace )?function financeiro\.(\w+)\(.*?\)\s*returns.*?\$\$(.*?)\$\$', texto, re.S)}


def ultimas_locais():
    saida = {}
    for arq in sorted(a for a in (RAIZ / 'supabase' / 'migrations').glob('*.sql') if a.name[:14] < VERSAO):
        saida.update(defs(arq.read_text(encoding='utf-8')))
    return saida


def sem_corpos(texto):
    return re.sub(r'\$\$.*?\$\$', '$$ $$', re.sub(r'--[^\n]*', '', texto), flags=re.S)


def trechos_nao_marcados(antigo, novo):
    """Blocos de diferenca sem a marca do MVP no texto acrescentado nem nas 12 linhas anteriores (ou 3 seguintes) da nova definicao."""
    a, n = antigo.split('\n'), novo.split('\n')
    soltos = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, n, autojunk=False).get_opcodes():
        if tag == 'equal':
            continue
        vizinho = '\n'.join(n[max(0, j1 - 12):j2 + 3])  # o bloco marcado (inclui o end if que o fecha)
        if tag == 'insert' and all(x.strip() == 'end if;' for x in n[j1:j2]):
            continue  # fecha o if/else aberto por bloco marcado (conferido no diff completo)
        if MARCA_MIG not in vizinho:
            soltos.append((tag, a[i1:i2][:3], n[j1:j2][:3]))
    return soltos


def inspecionar():
    texto = MIGRATION.read_text(encoding='utf-8')
    dm, dr, locais = defs(texto), defs(REVERSAO.read_text(encoding='utf-8')), ultimas_locais()
    criadas = set(re.findall(r'^create function financeiro\.(\w+)\(', texto, re.M))
    trocadas = set(re.findall(r'^create or replace function financeiro\.(\w+)\(', texto, re.M))
    ok = True

    def item(nome, cond, det=''):
        nonlocal ok
        ok = ok and bool(cond)
        print(f"{'OK   ' if cond else 'FALHA'} | {nome} | {det}")

    item('6 funcoes substituidas (create or replace) = as previstas', trocadas == set(SUBSTITUIDAS), sorted(trocadas))
    remoto = {r['proname']: r['prosrc'].replace('\r\n', '\n') for r in M.ler(
        "select p.proname, p.prosrc from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
        "where n.nspname = 'financeiro' and p.proname = any(%s)", (sorted(trocadas | criadas),))}
    item('reversao devolve a ultima definicao local anterior (20261124 inclusive)',
         all(dr.get(n) == locais.get(n) for n in SUBSTITUIDAS), [n for n in SUBSTITUIDAS if dr.get(n) != locais.get(n)])
    item('remoto = texto que a reversao devolve (fim de linha normalizado)', all(remoto.get(n) == dr[n] for n in SUBSTITUIDAS),
         [n for n in SUBSTITUIDAS if remoto.get(n) != dr[n]])
    soltos = {n: trechos_nao_marcados(dr[n], dm[n]) for n in SUBSTITUIDAS}
    blocos = {n: sum(1 for op in difflib.SequenceMatcher(None, dr[n].split('\n'), dm[n].split('\n'), autojunk=False)
                     .get_opcodes() if op[0] != 'equal') for n in SUBSTITUIDAS}
    item('toda diferenca nova x anterior esta em trecho marcado', not any(soltos.values()),
         {n: s for n, s in soltos.items() if s} or blocos)
    guarda = {n: (dr[n].count('exigir_escrita_novo'), dm[n].count('exigir_escrita_novo')) for n in SUBSTITUIDAS}
    item('guarda do escritor unico preservada (ocorrencias anterior -> nova)', all(b >= a for a, b in guarda.values()), guarda)
    item(f'{len(criadas)} funcoes novas ausentes no remoto', not (criadas & set(remoto)), sorted(criadas & set(remoto)))
    tabelas = M.ler('select ' + ', '.join(f"to_regclass('{t}') is null \"{t}\"" for t in TABELAS_NOVAS))[0]
    item('4 tabelas novas ausentes no remoto', all(tabelas.values()), tabelas)
    existentes = {r['proname'] for r in M.ler("select p.proname from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
                                               "where n.nspname = 'financeiro'")}
    chamadas = set(re.findall(r'financeiro\.(\w+)\(', texto)) - criadas - trocadas
    item(f'{len(chamadas)} funcoes de que a migration depende presentes', not (chamadas - existentes), sorted(chamadas - existentes))
    deps = M.ler("select to_regclass('financeiro.geracao_execucao') is not null ge, to_regtype('financeiro.linha_plano') is not null lp, "
                 "to_regclass('public.categoria') is not null cat, to_regclass('public.categoria_palavra_chave') is not null pc, "
                 "to_regclass('public.receita_realizada') is not null rr")[0]
    item('tabelas e tipo usados presentes', all(deps.values()), deps)
    fora = sem_corpos(texto)
    dml = re.findall(r'^\s*(insert|update|delete|truncate|copy)\b', fora, re.M | re.I)
    item('nenhum comando de dados fora dos corpos de funcao', not dml, dml)
    soltos_ddl = sorted({m.lower() for m in re.findall(r'^\s*(drop|alter table \S+ (?:drop|alter|add))\b', fora, re.M | re.I)})
    item('nenhum drop nem alteracao de coluna', not soltos_ddl, soltos_ddl)
    ultima = M.ler('select version from supabase_migrations.schema_migrations order by 1 desc limit 1')[0]['version']
    item(f'ultima aplicada no remoto = {ANTERIOR}', ultima == ANTERIOR, ultima)
    item('perfis e escritores (informativo)', True, M.ler('select perfil_financeiro_id id, gerador from financeiro.gerador_recorrencia order by 1'))
    semanais = M.ler("select i.perfil_financeiro_id perfil, coalesce(g.gerador, 'FLASK') escritor, i.tipo_recorrencia, i.meio_pagamento, "
                     "count(*) n from public.item_despesa i left join financeiro.gerador_recorrencia g "
                     "on g.perfil_financeiro_id = i.perfil_financeiro_id where i.recorrente and i.ativo and "
                     "(i.tipo_recorrencia like 'semanal%%' or i.tipo_recorrencia = 'a_cada_2_semanas') group by 1, 2, 3, 4 order by 1")
    item('recorrencias semanais ativas existentes (informativo: passam a ser geradas so em perfil do novo aplicativo)', True, semanais)
    sistemicas = M.ler("select count(*) n from public.categoria c join financeiro.categorias_sistemicas_mobilidade() s "
                       "on s.codigo = c.codigo_sistema") if 'categorias_sistemicas_mobilidade' in existentes else 'funcao nova'
    item('catalogo: categorias e palavras-chave (informativo)', True,
         M.ler('select (select count(*) from public.categoria) categorias, (select count(*) from public.categoria_palavra_chave) palavras')[0]
         | {'sistemicas_mobilidade': sistemicas})
    print('INSPECAO', 'OK' if ok else 'COM FALHAS')
    return 0 if ok else 1


def aplicar():
    posteriores = sorted(p for p in (RAIZ / 'supabase' / 'migrations').glob('*.sql') if p.name[:14] > VERSAO)
    guarda = PASTA / 'fora_durante_o_push'
    guarda.mkdir(parents=True, exist_ok=True)
    somas = {p.name: M.md5(p) for p in posteriores}
    for p in posteriores:
        shutil.move(str(p), str(guarda / p.name))
    try:
        r = subprocess.run([sys.executable, str(RAIZ / 'scripts' / 'supabase_migrations.py'), 'aplicar', '--versoes', VERSAO],
                           capture_output=True, text=True, cwd=RAIZ, timeout=600)
        print('\n'.join(l for l in (r.stdout + r.stderr).splitlines() if 'Supabase CLI' not in l and 'recommend' not in l)[-2500:])
    finally:
        for nome in somas:
            shutil.move(str(guarda / nome), str(RAIZ / 'supabase' / 'migrations' / nome))
        print('migrations posteriores de volta, identicas:',
              {n: M.md5(RAIZ / 'supabase' / 'migrations' / n) for n in somas} == somas, sorted(somas))
    return r.returncode


def linhas_do_perfil(perfil):
    tabelas = [r['t'] for r in M.ler("""select table_schema || '.' || table_name t from information_schema.columns
        where column_name = 'perfil_financeiro_id' and table_schema in ('public', 'financeiro')
          and table_name in (select table_name from information_schema.tables where table_type = 'BASE TABLE') order by 1""")]
    saida = {}
    for t in tabelas:
        r = M.ler(f"select count(*) n, coalesce(md5(string_agg(md5(x::text), '' order by md5(x::text))), '') h from {t} x "
                  'where perfil_financeiro_id = %s', (perfil,))[0]
        if r['n']:
            saida[t] = (r['n'], r['h'])
    oc = M.ler("select count(*) n, coalesce(md5(string_agg(md5(o::text), '' order by md5(o::text))), '') h "
               'from financeiro.recorrencia_ocorrencia o join public.item_despesa i on i.id = o.item_despesa_id '
               'where i.perfil_financeiro_id = %s', (perfil,))[0]
    saida['financeiro.recorrencia_ocorrencia'] = (oc['n'], oc['h'])
    return saida


def catalogo():
    return M.ler("select (select count(*) from public.categoria) n, "
                 "(select md5(string_agg(md5(c::text), '' order by c.id)) from public.categoria c) c, "
                 "(select md5(string_agg(md5(p::text), '' order by p.id)) from public.categoria_palavra_chave p) p, "
                 "(select count(*) from financeiro.catalogo_categorias) esc, (select count(*) from financeiro.gestor_catalogo) ges, "
                 "(select count(*) from financeiro.operacao_catalogo) ops")[0]


def a_cada(primeira, dias, ate):
    saida, d = [], primeira
    while d <= ate:
        saida.append(d)
        d += dt.timedelta(days=dias)
    return saida


def api():
    origem, chave, ta, tb = L.contexto()
    perfil = json.loads(L.ESTADO.read_text(encoding='utf-8'))['perfil']
    chamar = lambda f, c, t=ta: L.rpc(origem, chave, f, c, t)  # noqa: E731
    k = lambda: str(uuid.uuid4())  # noqa: E731
    reg = L.registrar
    hint = lambda r: (r or {}).get('hint') if isinstance(r, dict) else None  # noqa: E731
    _, cats = chamar('categorias_de_despesa', {})
    categoria = cats[0]['id']
    contas = lambda item: M.ler('select id, data_vencimento, descricao, valor, status_pagamento from public.conta '  # noqa: E731
                                'where item_despesa_id = %s order by data_vencimento, id', (item,))
    mes, ate = '2026-11-01', D(2026, 12, 31)

    def gerar(mes_ref, dispensar=()):
        s, p = chamar('previa_geracao', {'p_perfil_id': perfil, 'p_mes': mes_ref})
        if s != 200:
            return s, p, None
        s2, r = chamar('gerar_mes', {'p_perfil_id': perfil, 'p_mes': mes_ref, 'p_total_previsto': p['a_gerar'],
                                     'p_dispensar': list(dispensar)})
        return s2, p, r

    def recorrencia(nome, tipo, venc):
        s, r = chamar('criar_despesa', {'p_perfil_id': perfil, 'p_chave': k(), 'p_dados': {
            'nome': nome, 'valor': '30.00', 'categoria_id': categoria, 'data_vencimento': venc, 'recorrente': True,
            'tipo_recorrencia': tipo}})
        return s, (r or {}).get('item_id') if isinstance(r, dict) else None

    # 1. Semanal (quarta) e a cada 2 semanas (segunda): uma conta por ocorrencia, descricao do Flask; repetir nao duplica.
    s1, semanal = recorrencia(SEMANAL, 'semanal_1_3', '2026-11-03')  # terca; dia 3 = quarta
    s2, quinzenal = recorrencia(QUINZENAL, 'semanal_2_1', '2026-11-02')  # segunda
    sg, previa, r = gerar(mes)
    esp_s, esp_q = a_cada(D(2026, 11, 4), 7, ate), a_cada(D(2026, 11, 2), 14, ate)
    cs, cq = contas(semanal), contas(quinzenal)
    reg('cadastro das recorrencias semanal e a cada 2 semanas', (s1, s2) == (200, 200) and semanal and quinzenal, (s1, s2))
    reg('semanal: uma conta por quarta, de 04/11 a 30/12 (9)', [c['data_vencimento'] for c in cs] == esp_s and len(esp_s) == 9,
        [str(c['data_vencimento']) for c in cs])
    reg('a cada 2 semanas: 02/11, 16/11, 30/11, 14/12, 28/12', [c['data_vencimento'] for c in cq] == esp_q,
        [str(c['data_vencimento']) for c in cq])
    reg('descricao como o Flask ("<nome> - dd/mm") e situacao Pendente',
        all(c['descricao'] == f"{n} - {c['data_vencimento']:%d/%m}" and c['status_pagamento'] == 'Pendente'
            for n, lista in ((SEMANAL, cs), (QUINZENAL, cq)) for c in lista), cs[0]['descricao'] if cs else None)
    ocorr = M.ler('select item_despesa_id, situacao, count(*) n from financeiro.recorrencia_ocorrencia where item_despesa_id in (%s, %s) '
                  'group by 1, 2 order by 1', (semanal, quinzenal))
    reg('identidade por ocorrencia registrada (GERADA)', [(o['situacao'], o['n']) for o in ocorr] == [('GERADA', 9), ('GERADA', 5)], ocorr)
    antes = (contas(semanal), contas(quinzenal))
    sg2, previa2, r2 = gerar(mes)
    reg('geracao repetida: nada novo, nada alterado', sg == 200 and previa2['a_gerar'] == 0 and (contas(semanal), contas(quinzenal)) == antes,
        (sg, previa['a_gerar'], previa2['a_gerar']))

    # 2. Excluir uma conta semanal dispensa so aquela ocorrencia; a geracao seguinte nao a recria.
    alvo = next(c for c in cs if c['data_vencimento'] == D(2026, 11, 11))
    versao = M.ler('select financeiro.versao_despesa(%s) v', (alvo['id'],))[0]['v']
    s, r = chamar('excluir_despesa', {'p_perfil_id': perfil, 'p_conta_id': alvo['id'], 'p_versao': versao})
    sit = M.ler('select situacao, conta_id from financeiro.recorrencia_ocorrencia where item_despesa_id = %s and data_ocorrencia = %s',
                (semanal, D(2026, 11, 11)))
    gerar(mes)
    gerar('2026-12-01')
    datas = [c['data_vencimento'] for c in contas(semanal)]
    reg('excluir a conta de 11/11 dispensa so essa ocorrencia e ela nao volta',
        s == 200 and (r or {}).get('competencia_dispensada') is True and sit == [{'situacao': 'DISPENSADA', 'conta_id': None}]
        and D(2026, 11, 11) not in datas and {D(2026, 11, 4), D(2026, 11, 18)} <= set(datas), (s, sit, len(datas)))

    # 2b. Conta paga nunca muda nem duplica: paga a 1a semanal; altera o valor da recorrencia; gera os meses seguintes.
    _, cb = chamar('criar_conta_bancaria', {'p_perfil_id': perfil, 'p_chave': k(), 'p_dados': {
        'nome': CONTA_B, 'instituicao': 'Banco ficticio', 'tipo': 'Conta Corrente', 'saldo_inicial': 0}})
    primeira = contas(semanal)[0]
    sp, pago = chamar('pagar_despesa', {'p_perfil_id': perfil, 'p_conta_id': primeira['id'], 'p_chave': k(), 'p_dados': {
        'conta_bancaria_id': cb['id'], 'data_pagamento': '2026-11-04', 'valor_pago': '30.00', 'valor_devido': '30.00'}})
    hash_paga = lambda: M.ler('select md5(c::text) h from public.conta c where id = %s', (primeira['id'],))[0]['h']  # noqa: E731
    paga_antes = hash_paga()
    geradas_antes = {c['id']: float(c['valor']) for c in contas(semanal)}
    se, _ = chamar('editar_recorrencia', {'p_perfil_id': perfil, 'p_item_id': semanal, 'p_versao': M.ler(
        'select financeiro.versao_recorrencia(%s) v', (semanal,))[0]['v'], 'p_dados': {'valor': '45.00'}})
    # Conta gravada "pelo Flask" no ciclo de 11/01/2027 da quinzenal, em outro dia (13/01): deve ser reconhecida.
    conn = L.conectar()
    try:
        with conn.cursor() as cur:
            a_id, _ = L.usuarios(cur)
            if L.identificar(cur, a_id)[0] != perfil:
                raise SystemExit('Perfil temporario nao confere: interrompido.')
            cur.execute("insert into public.conta (perfil_financeiro_id, item_despesa_id, mes_referencia, descricao, valor, data_vencimento, "
                        "status_pagamento, is_fatura_cartao, estouro_orcamento) values (%s, %s, '2027-01-01', %s, 30, '2027-01-13', "
                        "'Pendente', false, false) returning id", (perfil, quinzenal, QUINZENAL))
            do_flask = cur.fetchone()[0]
        conn.commit()
    finally:
        conn.close()
    sg3, previa3, _ = gerar('2027-01-01')
    depois = contas(semanal)
    ciclo = [c['data_vencimento'] for c in contas(quinzenal) if D(2027, 1, 11) <= c['data_vencimento'] < D(2027, 1, 25)]
    esperado_s = [d for d in a_cada(D(2026, 11, 4), 7, D(2027, 2, 28)) if d != D(2026, 11, 11)]
    reg('pagamento da 1a semanal com movimento', sp == 200 and (pago or {}).get('movimento_id'), (sp, (pago or {}).get('movimento_id')))
    reg('conta paga intacta depois da alteracao do valor e de nova geracao (mesmo md5)', se == 200 and hash_paga() == paga_antes
        and M.ler('select status_pagamento from public.conta where id = %s', (primeira['id'],))[0]['status_pagamento'] == 'Pago', se)
    reg('contas ja geradas mantem o valor; so as novas (fevereiro) vem com 45',
        {c['id']: float(c['valor']) for c in depois if c['id'] in geradas_antes} == geradas_antes
        and {float(c['valor']) for c in depois if c['id'] not in geradas_antes} == {45.0},
        sorted({float(c['valor']) for c in depois if c['id'] not in geradas_antes}))
    reg('semanal: todas as ocorrencias previstas ate 28/02/2027, uma por data, sem a dispensada (16)',
        sg3 == 200 and [c['data_vencimento'] for c in depois] == esperado_s and len(depois) == len(esperado_s) == 16,
        (sg3, len(depois)))
    reg('quinzenal: conta existente no ciclo (13/01) reconhecida, nada criado em 11/01, sem duplicar',
        ciclo == [D(2027, 1, 13)] and not any(x.get('item_id') == quinzenal and x.get('data_vencimento') == '2027-01-11'
                                               for x in previa3.get('itens', []) if x.get('situacao', 'A_GERAR') == 'A_GERAR'),
        (ciclo, do_flask))
    dup = M.ler('select item_despesa_id, data_vencimento, count(*) n from public.conta where perfil_financeiro_id = %s '
                'group by 1, 2 having count(*) > 1', (perfil,))
    reg('nenhuma conta duplicada (item + data) no perfil', dup == [], dup)

    # 3. Semanal no cartao: recusada, como o Flask (so mensal e anual), nada gravado.
    sc, cartao = chamar('criar_cartao', {'p_perfil_id': perfil, 'p_chave': k(), 'p_dados': {
        'nome': CARTAO, 'dia_fechamento': 25, 'dia_vencimento': 5, 'fechamento_confirmado': True, 'compra_no_fechamento': 'PROXIMO'}})
    itens_antes = M.ler('select count(*) n from public.item_despesa where perfil_financeiro_id = %s', (perfil,))[0]['n']
    s, r = chamar('criar_recorrencia_cartao', {'p_perfil_id': perfil, 'p_chave': k(), 'p_dados': {
        'nome': f'Cartao semanal {MARCA}', 'valor': '10.00', 'categoria_id': categoria, 'data_vencimento': '2026-11-06',
        'tipo_recorrencia': 'semanal_1_5', 'cartao_id': (cartao or {}).get('cartao_id')}})
    itens_depois = M.ler('select count(*) n from public.item_despesa where perfil_financeiro_id = %s', (perfil,))[0]['n']
    reg('semanal no cartao recusada (so mensal e anual), nada gravado',
        sc == 200 and s == 400 and 'mensal' in str((r or {}).get('message', '')).lower() and itens_antes == itens_depois,
        (sc, s, (r or {}).get('message'), itens_antes, itens_depois))

    # 4. Receitas: valor base cria so as previsoes que faltam; repetida nao cria nada.
    s, rec = chamar('criar_receita', {'p_perfil_id': perfil, 'p_chave': k(), 'p_dados': {
        'nome': FONTE, 'tipo': 'SALARIO_FIXO', 'valor': '5000.00', 'competencia': '2026-08-01', 'recorrente': True, 'dia_previsto': 5}})
    fonte = (rec or {}).get('item_receita_id')
    previsoes = lambda item: {str(r['mes_referencia']): float(r['valor_esperado']) for r in M.ler(  # noqa: E731
        'select mes_referencia, valor_esperado from public.receita_orcamento where item_receita_id = %s', (item,))}
    p0 = previsoes(fonte)
    vf = lambda item: M.ler('select financeiro.versao_fonte(%s) v', (item,))[0]['v']  # noqa: E731
    s1, r1 = chamar('redefinir_fonte_receita', {'p_perfil_id': perfil, 'p_item_id': fonte, 'p_versao': vf(fonte),
                                                'p_dados': {'valor_base_mensal': '6000.00', 'recorrente': True}})
    p1 = previsoes(fonte)
    novas = sorted(set(p1) - set(p0))
    s2, r2 = chamar('redefinir_fonte_receita', {'p_perfil_id': perfil, 'p_item_id': fonte, 'p_versao': vf(fonte),
                                                'p_dados': {'valor_base_mensal': '6000.00', 'recorrente': True}})
    reg('valor base: so as previsoes que faltam (6000), as gravadas nao mudam; repetida nao cria',
        (s, s1, s2) == (200, 200, 200) and novas == ['2027-08-01', '2027-09-01', '2027-10-01']
        and {m: p1[m] for m in p0} == p0 and {p1[m] for m in novas} == {6000.0} and r2.get('previsoes_criadas') == [],
        (s, s1, s2, novas, len(p0)))

    # 5. Recebimento sem previsao: credito no extrato, chave repetida nao duplica.
    _, bico =chamar('criar_receita', {'p_perfil_id': perfil, 'p_chave': k(), 'p_dados': {
        'nome': BICO, 'tipo': 'RENDA_EXTRA', 'valor': '500.00', 'competencia': '2026-10-01', 'recorrente': False}})
    dados = {'item_receita_id': bico['item_receita_id'], 'data_recebimento': '2026-11-10', 'valor_recebido': '320.00',
             'competencia': '2026-11-01', 'conta_bancaria_id': cb['id'], 'descricao': f'Bico extra {MARCA}'}
    saldo_antes = float(M.ler('select financeiro.saldo_da_conta(%s) s', (cb['id'],))[0]['s'])
    ch = k()
    sa, ra = chamar('receber_sem_previsao', {'p_perfil_id': perfil, 'p_dados': dados, 'p_chave': ch})
    sb, rb = chamar('receber_sem_previsao', {'p_perfil_id': perfil, 'p_dados': dados, 'p_chave': ch})
    real = M.ler('select id, orcamento_id from public.receita_realizada where item_receita_id = %s', (bico['item_receita_id'],))
    mov = M.ler("select tipo, valor, origem from public.movimento_financeiro where receita_realizada_id = %s", (real[0]['id'],)) if real else []
    saldo = M.ler('select financeiro.saldo_da_conta(%s) s', (cb['id'],))[0]['s']
    reg('recebimento sem previsao: 1 realizada sem previsao, 1 credito de 320, reenvio nao duplica',
        (sa, sb) == (200, 200) and (rb or {}).get('repetida') is True and len(real) == 1 and real[0]['orcamento_id'] is None
        and [(m['tipo'], float(m['valor']), m['origem']) for m in mov] == [('CREDITO', 320.0, 'RECEITA')] and float(saldo) == saldo_antes + 320,
        (sa, sb, len(real), mov, saldo))

    # 6. Catalogo global: continua com o Flask; nenhuma escrita passa e nada muda no catalogo.
    cat_antes = catalogo()
    st, situacao = chamar('situacao_catalogo_categorias', {})
    tentativas = {
        'criar_categoria': {'p_dados': {'nome': f'Nao grava {MARCA}'}, 'p_chave': k()},
        'editar_categoria': {'p_categoria_id': categoria, 'p_dados': {'nome': f'Nao grava {MARCA}'}},
        'excluir_categoria': {'p_categoria_id': categoria},
        'criar_palavra_chave': {'p_categoria_id': categoria, 'p_palavra': 'nao grava'},
    }
    recusas = {f: (lambda sr: (sr[0], hint(sr[1])))(chamar(f, corpo)) for f, corpo in tentativas.items()}
    recusas_b = {f: (lambda sr: (sr[0], hint(sr[1])))(chamar(f, corpo, tb)) for f, corpo in list(tentativas.items())[:1]}
    reg('catalogo nasce no Flask (escritor FLASK, conta sem gestao)', st == 200 and situacao == {'escritor': 'FLASK', 'gestor': False}, situacao)
    reg('catalogo: as 4 escritas recusadas com CATALOGO_FLASK (titular e leitor)',
        all(h == 'CATALOGO_FLASK' for _, h in list(recusas.values()) + list(recusas_b.values())), (recusas, recusas_b))
    reg('catalogo global identico (categorias, palavras-chave, escritor, gestores, operacoes)', catalogo() == cat_antes,
        {k2: v for k2, v in cat_antes.items() if k2 in ('n', 'esc', 'ges', 'ops')})

    # 7. Perfil passado ao Flask: as escritas novas sao recusadas (SISTEMA_FLASK) e nada muda no perfil.
    L.atribuir(perfil, 'FLASK')
    try:
        antes = linhas_do_perfil(perfil)
        conta_q = contas(quinzenal)[0]
        tentativas = {
            'redefinir_fonte_receita': {'p_perfil_id': perfil, 'p_item_id': fonte, 'p_versao': vf(fonte), 'p_dados': {'valor_base_mensal': '1.00'}},
            'receber_sem_previsao': {'p_perfil_id': perfil, 'p_chave': k(), 'p_dados': {**dados, 'data_recebimento': '2026-12-10',
                                                                                         'competencia': '2026-12-01'}},
            'criar_despesa': {'p_perfil_id': perfil, 'p_chave': k(), 'p_dados': {'nome': 'Nao grava', 'valor': '1.00', 'categoria_id': categoria,
                                                                                  'data_vencimento': '2026-11-05', 'recorrente': True,
                                                                                  'tipo_recorrencia': 'semanal_1_4'}},
            'excluir_despesa': {'p_perfil_id': perfil, 'p_conta_id': conta_q['id'],
                                'p_versao': M.ler('select financeiro.versao_despesa(%s) v', (conta_q['id'],))[0]['v']},
            'gerar_mes': {'p_perfil_id': perfil, 'p_mes': '2027-01-01', 'p_total_previsto': 0, 'p_dispensar': []},
        }
        recusadas = {f: (lambda sr: (sr[0], hint(sr[1])))(chamar(f, corpo)) for f, corpo in tentativas.items()}
        reg('perfil no Flask: as 5 escritas recusadas com SISTEMA_FLASK', all(h == 'SISTEMA_FLASK' for _, h in recusadas.values()), recusadas)
        reg('perfil no Flask: nada mudou no perfil (todas as tabelas e ocorrencias)', linhas_do_perfil(perfil) == antes)
    finally:
        L.atribuir(perfil, 'NOVO')

    # 8. Quem so le recebe 403.
    s, r = chamar('redefinir_fonte_receita', {'p_perfil_id': perfil, 'p_item_id': fonte, 'p_versao': vf(fonte),
                                              'p_dados': {'valor_base_mensal': '1.00'}}, tb)
    s2, r2 = chamar('receber_sem_previsao', {'p_perfil_id': perfil, 'p_chave': k(), 'p_dados': {**dados, 'data_recebimento': '2026-12-11',
                                                                                                 'competencia': '2026-12-01'}}, tb)
    reg('LEITOR: redefinir fonte e receber sem previsao recusados (403)', s in (401, 403) and s2 in (401, 403), (s, s2))

    # 9. Leituras alteradas: recorrencias do perfil (proximo vencimento semanal) e previsoes na tela.
    s, lista = chamar('recorrencias_do_perfil', {'p_perfil_id': perfil})
    sem = next((x for x in lista or [] if x.get('id') == semanal), {})
    reg('recorrencias_do_perfil le as semanais', s == 200 and sem.get('tipo_recorrencia') == 'semanal_1_3', (s, {k2: sem.get(k2) for k2 in
        ('tipo_recorrencia', 'proximo_vencimento')}))
    falhas = [nome for nome, ok in L.RESULTADOS if not ok]
    print(f'{len(L.RESULTADOS) - len(falhas)}/{len(L.RESULTADOS)} OK', '| falhas:', falhas or 'nenhuma')
    return 1 if falhas else 0


def complemento():
    """Refaz o cenario da conta existente no ciclo num ciclo AINDA NAO GERADO (08/03/2027 da quinzenal): na rodada
    anterior a conta de 13/01 foi inserida depois que a geracao de dezembro (janela dez-jan) ja tinha gerado 11/01."""
    origem, chave, ta, _ = L.contexto()
    perfil = json.loads(L.ESTADO.read_text(encoding='utf-8'))['perfil']
    chamar = lambda f, c, t=ta: L.rpc(origem, chave, f, c, t)  # noqa: E731
    reg = L.registrar
    itens = {r['nome']: r['id'] for r in M.ler('select id, nome from public.item_despesa where perfil_financeiro_id = %s', (perfil,))}
    semanal, quinzenal = itens[SEMANAL], itens[QUINZENAL]
    contas = lambda item: M.ler('select id, data_vencimento, valor, status_pagamento from public.conta '  # noqa: E731
                                'where item_despesa_id = %s order by data_vencimento, id', (item,))
    jan = M.ler("select o.situacao, o.conta_id, o.execucao_id from financeiro.recorrencia_ocorrencia o "
                "where o.item_despesa_id = %s and o.data_ocorrencia = '2027-01-11'", (quinzenal,))
    reg('rodada anterior: 11/01 ja era GERADA pela geracao de dezembro (a conta de 13/01 entrou depois)',
        len(jan) == 1 and jan[0]['situacao'] == 'GERADA' and jan[0]['conta_id'] < 1288, jan)
    paga = M.ler("select id, md5(c::text) h from public.conta c where item_despesa_id = %s and status_pagamento = 'Pago'", (semanal,))
    conn = L.conectar()
    try:
        with conn.cursor() as cur:
            a_id, _ = L.usuarios(cur)
            if L.identificar(cur, a_id)[0] != perfil:
                raise SystemExit('Perfil temporario nao confere: interrompido.')
            cur.execute("select count(*) from public.conta where item_despesa_id = %s and data_vencimento >= '2027-03-01'", (quinzenal,))
            if cur.fetchone()[0]:
                raise SystemExit('Ciclo de marco ja gerado: cenario invalido, interrompido.')
            cur.execute("insert into public.conta (perfil_financeiro_id, item_despesa_id, mes_referencia, descricao, valor, data_vencimento, "
                        "status_pagamento, is_fatura_cartao, estouro_orcamento) values (%s, %s, '2027-03-01', %s, 30, '2027-03-10', "
                        "'Pendente', false, false) returning id", (perfil, quinzenal, QUINZENAL))
            do_flask = cur.fetchone()[0]
        conn.commit()
    finally:
        conn.close()
    s, p = chamar('previa_geracao', {'p_perfil_id': perfil, 'p_mes': '2027-02-01'})
    a_gerar_q = sorted(x['data_vencimento'] for x in p['itens'] if x['item_id'] == quinzenal)
    s2, r = chamar('gerar_mes', {'p_perfil_id': perfil, 'p_mes': '2027-02-01', 'p_total_previsto': p['a_gerar'], 'p_dispensar': []})
    marco = [(str(c['data_vencimento']), c['id'] == do_flask) for c in contas(quinzenal) if c['data_vencimento'] >= D(2027, 3, 1)]
    reg('previa: 08/03 fora dos "a gerar" (ciclo ja tem a conta de 10/03); 22/03 a gerar',
        s == 200 and '2027-03-08' not in a_gerar_q and '2027-03-22' in a_gerar_q, a_gerar_q)
    reg('geracao: 10/03 (existente) reconhecida, 08/03 nao criada, 22/03 criada',
        s2 == 200 and marco == [('2027-03-10', True), ('2027-03-22', False)], marco)
    semana = [c['data_vencimento'] for c in contas(semanal)]
    esperado = [d for d in a_cada(D(2026, 11, 4), 7, D(2027, 3, 31)) if d != D(2026, 11, 11)]
    reg('semanal: todas as ocorrencias ate 31/03/2027, uma por data, sem a dispensada', semana == esperado, len(semana))
    reg('conta paga intacta depois de mais uma geracao (mesmo md5)',
        M.ler('select md5(c::text) h from public.conta c where id = %s', (paga[0]['id'],))[0]['h'] == paga[0]['h'] and len(paga) == 1)
    s3, p3 = chamar('previa_geracao', {'p_perfil_id': perfil, 'p_mes': '2027-02-01'})
    dup = M.ler('select item_despesa_id, data_vencimento, count(*) n from public.conta where perfil_financeiro_id = %s '
                'group by 1, 2 having count(*) > 1', (perfil,))
    reg('geracao repetida nada cria; nenhuma conta duplicada no perfil', s3 == 200 and p3['a_gerar'] == 0 and dup == [], (p3['a_gerar'], dup))
    falhas = [nome for nome, ok in L.RESULTADOS if not ok]
    print(f'{len(L.RESULTADOS) - len(falhas)}/{len(L.RESULTADOS)} OK', '| falhas:', falhas or 'nenhuma')
    return 1 if falhas else 0


SPEC = r"""
import { test, expect } from '@playwright/test';
import { trocarPerfil } from '../../tests/e2e/moldura.mjs';

const PAGINAS = ['contas.html', 'recorrencias.html', 'receitas.html', 'categorias.html', 'cartoes.html', 'contas-bancarias.html',
    'lancamentos.html', 'importar-cartao.html', 'financiamentos.html', 'patrimonio.html', 'documentos-fiscais.html',
    'dashboard.html', 'mobilidade.html', 'configuracoes.html'];

test('telas no perfil temporario (Supabase de teste real, FIN-CATEGORIAS-RECORRENCIAS-2)', async ({ page }) => {
    const erros = [];
    const paraApi = [];
    page.on('console', (m) => { if (m.type() === 'error') erros.push(`${page.url().split('/').pop()}: ${m.text()}`); });
    page.on('pageerror', (e) => erros.push(`${page.url().split('/').pop()}: ${e.message}`));
    page.on('request', (r) => { if (new URL(r.url()).pathname.startsWith('/api/')) paraApi.push(r.url()); });
    page.on('dialog', (d) => d.dismiss());
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
        if (pagina === 'recorrencias.html') {
            await expect(page.locator(':is(strong, td, span, div, h3, h4):visible', { hasText: 'Diarista (e2e-real)' }).first()).toBeVisible();
            await expect(page.locator(':is(strong, td, span, div, h3, h4):visible', { hasText: 'Jardinagem (e2e-real)' }).first()).toBeVisible();
        }
        if (pagina === 'receitas.html') await expect(page.locator(':is(strong, td, span, div, h3, h4):visible', { hasText: 'Salario base (e2e-real)' }).first()).toBeVisible();
    }
    expect(erros).toEqual([]);
    expect(paraApi).toEqual([]);
});
"""


def ui(web):
    """Telas com o dist construido a partir da arvore commitada (web = <arvore exportada>/web)."""
    sys.path.insert(0, str(Path(web) / 'tests' / 'e2e'))
    sys.path.insert(0, str(Path(web).parent))
    L.WEB = Path(web)
    L.build()
    from run_e2e import criar_handler, ler_headers
    from tests.supabase_local import porta_livre
    pasta = L.WEB / 'test-results' / 'cr_real'
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / 'playwright.real.mjs').write_text(L.CONFIG, encoding='utf-8')
    (pasta / 'cr_real.spec.mjs').write_text(SPEC, encoding='utf-8')
    dist = L.WEB / 'dist'
    porta = porta_livre()
    servidor = ThreadingHTTPServer(('127.0.0.1', porta), criar_handler(dist, None, None, ler_headers(dist)))
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    try:
        r = subprocess.run([shutil.which('npx') or 'npx', 'playwright', 'test', '-c', 'test-results/cr_real/playwright.real.mjs'],
                           cwd=L.WEB, env={**os.environ, 'CF_WEB_BASE_URL': f'http://127.0.0.1:{porta}', 'CF_PERFIL_TEMP': L.PERFIL},
                           capture_output=True, text=True, encoding='utf-8', errors='replace')
    finally:
        servidor.shutdown()
    saida = r.stdout + r.stderr
    for segredo in filter(None, (os.environ.get(x) for x in ('CF_EMAIL_A', 'CF_EMAIL_B', 'CF_SENHA_A', 'CF_SENHA_B'))):
        saida = saida.replace(segredo, '<oculto>')
    print(saida.strip()[-6000:])
    return r.returncode


def limpar(confirmar):
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
            for tabela, coluna in (('item_despesa', 'nome'), ('item_receita', 'nome'), ('conta_bancaria', 'nome')):  # cartao = item_despesa
                cur.execute(f"select count(*) from public.{tabela} where perfil_financeiro_id = %s and {coluna} not like %s",
                            (perfil, f'%{MARCA}'))
                if cur.fetchone()[0]:
                    raise SystemExit(f'{tabela} fora do teste no perfil temporario: interrompido.')
            cur.execute('select (select count(*) from financeiro.catalogo_categorias), (select count(*) from financeiro.gestor_catalogo), '
                        '(select count(*) from financeiro.operacao_catalogo)')
            if cur.fetchone() != (0, 0, 0):
                raise SystemExit('Controle do catalogo nao esta vazio: interrompido (nada do teste deveria estar la).')
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
            cur.execute('select count(*) from financeiro.recorrencia_ocorrencia o where not exists (select 1 from public.item_despesa i '
                        'where i.id = o.item_despesa_id and i.perfil_financeiro_id = %s)', (perfil,))
            ocorrencias_fora = cur.fetchone()[0]
            cur.execute('delete from financeiro.recorrencia_ocorrencia o using public.item_despesa i '
                        'where i.id = o.item_despesa_id and i.perfil_financeiro_id = %s', (perfil,))
            removidos = {'ocorrencias': cur.rowcount}
            # Ligadas ao item (sem coluna de perfil): so as dos itens do perfil temporario.
            for tabela in ('public.config_agregador', 'financeiro.recorrencia_competencia'):
                cur.execute(f'delete from {tabela} x using public.item_despesa i '
                            'where i.id = x.item_despesa_id and i.perfil_financeiro_id = %s', (perfil,))
                removidos[tabela] = cur.rowcount
            # Demais tabelas do perfil, em passadas ate esvaziar (a ordem das chaves estrangeiras resolve-se sozinha);
            # cada exclusao e limitada ao perfil temporario identificado.
            pendentes = [t for t in tabelas if t not in ('public.perfil_financeiro',)]
            for _ in range(len(pendentes) + 1):
                restam = []
                for t in pendentes:
                    cur.execute('savepoint s')
                    try:
                        cur.execute(f'delete from {t} where perfil_financeiro_id = %s', (perfil,))
                        removidos[t] = removidos.get(t, 0) + cur.rowcount
                        cur.execute(f'select count(*) from {t} where perfil_financeiro_id = %s', (perfil,))
                        if cur.fetchone()[0]:
                            restam.append(t)
                        cur.execute('release savepoint s')
                    except Exception:  # noqa: BLE001 (chave estrangeira: fica para a proxima passada)
                        cur.execute('rollback to savepoint s')
                        restam.append(t)
                if not restam:
                    break
                pendentes = restam
            else:
                raise SystemExit(f'Tabelas do perfil temporario nao esvaziaram: {restam}: nada removido.')
            cur.execute('delete from public.perfil_financeiro where id = %s and nome = %s', (perfil, L.PERFIL))
            removidos['perfil'] = cur.rowcount
            print('removidos:', {k: v for k, v in removidos.items() if v})
            restantes = {}
            for t in tabelas:
                cur.execute(f'select count(*) from {t} where perfil_financeiro_id = %s', (perfil,))
                if cur.fetchone()[0]:
                    restantes[t] = True
            cur.execute('select count(*) from financeiro.recorrencia_ocorrencia')
            if restantes or removidos['perfil'] != 1 or cur.fetchone()[0] != ocorrencias_fora:
                raise SystemExit(f'Sobraram linhas do perfil temporario ou ocorrencias alheias afetadas: {restantes}: nada removido.')
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
    if etapa == 'complemento':
        sys.exit(complemento())
    if etapa == 'ui':
        sys.exit(ui(sys.argv[2]))
    if etapa == 'limpar':
        limpar('--confirmar' in sys.argv)
