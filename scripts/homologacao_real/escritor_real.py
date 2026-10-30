"""FIN-ESCRITOR-UNICO-FINAL-1 — implantacao da migration 20261124090000 no Supabase de teste (fzjmge...), com dados
FICTICIOS num perfil TEMPORARIO criado pelo aplicativo. Reaproveita lote_real.py e motor_real.py.

Etapas:
  inspecionar   so leitura: os 29 corpos remotos = o que a reversao devolve; nova = anterior + so a linha marcada;
                exigir_escrita_novo ausente; dependencias presentes; perfis no novo aplicativo
  aplicar       aplica SO a 20261124090000 (as locais posteriores ficam fora da pasta durante o push e voltam identicas)
  criar | api | ui | limpar [--confirmar]
Nunca grava nos perfis 1, 2, 31 e 39. Nao imprime e-mails, senhas, chaves nem URL do banco.
"""
# FIN-PUBLICACAO-SEGURA-1: o projeto de teste virou a producao; recusa antes de ler credenciais ou conectar.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from guarda_producao import recusar_em_producao
recusar_em_producao(__file__)
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
import motor_real as M  # noqa: E402

RAIZ = L.RAIZ
VERSAO = '20261124090000'
MIGRATION = RAIZ / 'supabase' / 'migrations' / f'{VERSAO}_financeiro_escritor_unico_final.sql'
REVERSAO = RAIZ / 'supabase' / 'reversao' / f'{VERSAO}_escritas_sem_escritor_anterior.sql'
PASTA = RAIZ / 'data' / 'homologacao_real' / 'escritor_real'  # estado e retratos locais (data/ fora do Git)
L.PERFIL = 'Validacao Escritor Unico (e2e-real)'
L.ESTADO = PASTA / 'estado.json'
MARCA = '(e2e-real)'
DESPESA = f'Despesa Escritor {MARCA}'
LINHA = '    perform financeiro.exigir_escrita_novo(p_perfil_id{});  -- FIN-ESCRITOR-UNICO-FINAL-1\n'


def defs(texto):
    return {m.group(1): m.group(2) for m in re.finditer(
        r'create (?:or replace )?function financeiro\.(\w+)\(.*?\)\s*returns.*?\$\$(.*?)\$\$', texto, re.S)}


def inspecionar():
    dm, dr = defs(MIGRATION.read_text(encoding='utf-8')), defs(REVERSAO.read_text(encoding='utf-8'))
    alvos = sorted(n for n in dm if n != 'exigir_escrita_novo')
    remoto = {r['proname']: r['prosrc'].replace('\r\n', '\n') for r in M.ler(
        "select p.proname, p.prosrc from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
        "where n.nspname = 'financeiro' and p.proname = any(%s)", (alvos + ['exigir_escrita_novo'],))}
    ok = True

    def item(nome, cond, det=''):
        nonlocal ok
        ok = ok and cond
        print(f"{'OK   ' if cond else 'FALHA'} | {nome} | {det}")
    item('29 funcoes substituidas, todas com o texto anterior na reversao', len(alvos) == 29 and set(alvos) <= set(dr), len(alvos))
    item('remoto = texto que a reversao devolve (fim de linha normalizado)', all(remoto.get(n) == dr[n] for n in alvos),
         [n for n in alvos if remoto.get(n) != dr[n]])
    item('nova = anterior + so a linha marcada', all(dm[n].replace(LINHA.format(''), '').replace(LINHA.format(', true'), '') == dr[n]
                                                     for n in alvos))
    item('exigir_escrita_novo ausente no remoto', 'exigir_escrita_novo' not in remoto)
    dep = M.ler("select to_regprocedure('financeiro.pode_gerir_perfil(integer)') is not null g, "
                "to_regclass('financeiro.gerador_recorrencia') is not null r, to_regclass('financeiro.perfil_acesso') is not null a")[0]
    item('dependencias presentes', all(dep.values()), dep)
    item('perfis no novo aplicativo', True, M.ler('select perfil_financeiro_id id, gerador from financeiro.gerador_recorrencia order by 1'))
    ultima = M.ler('select version from supabase_migrations.schema_migrations order by 1 desc limit 1')[0]['version']
    item('ultima aplicada no remoto = 20261123090000', ultima == '20261123090000', ultima)
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
    return saida


def api():
    origem, chave, ta, tb = L.contexto()
    perfil = json.loads(L.ESTADO.read_text(encoding='utf-8'))['perfil']
    chamar = lambda f, c, t=ta: L.rpc(origem, chave, f, c, t)  # noqa: E731
    k = lambda: str(uuid.uuid4())  # noqa: E731
    reg = L.registrar
    _, cats = chamar('categorias_de_despesa', {})
    categoria = cats[0]['id']
    dados = {'nome': DESPESA, 'valor': '42.50', 'categoria_id': categoria, 'data_vencimento': '2035-03-10'}

    # 1. Perfil no novo aplicativo: grava, e a mesma chave nao duplica.
    ch = k()
    s1, r1 = chamar('criar_despesa', {'p_perfil_id': perfil, 'p_dados': dados, 'p_chave': ch})
    s2, r2 = chamar('criar_despesa', {'p_perfil_id': perfil, 'p_dados': dados, 'p_chave': ch})
    n = M.ler('select count(*) n from public.conta where perfil_financeiro_id = %s and descricao = %s', (perfil, DESPESA))[0]['n']
    reg('perfil NOVO: cadastro grava; reenvio pela mesma chave nao duplica', (s1, s2) == (200, 200) and bool(r2.get('repetida')) and n == 1,
        (s1, s2, n))
    conta = r1['conta_id']
    _, edicao = chamar('despesa_para_edicao', {'p_perfil_id': perfil, 'p_conta_id': conta})
    versao = (edicao or {}).get('versao')

    # 2. Perfil passado ao Flask: as escritas sao recusadas (SISTEMA_FLASK) e nada muda no perfil.
    L.atribuir(perfil, 'FLASK')
    try:
        antes = linhas_do_perfil(perfil)
        tentativas = {
            'criar_despesa': {'p_perfil_id': perfil, 'p_dados': {**dados, 'nome': 'Nao grava'}, 'p_chave': k()},
            'editar_despesa': {'p_perfil_id': perfil, 'p_conta_id': conta, 'p_versao': versao, 'p_dados': {'valor': '50.00'}},
            'excluir_despesa': {'p_perfil_id': perfil, 'p_conta_id': conta, 'p_versao': versao},
            'criar_receita': {'p_perfil_id': perfil, 'p_chave': k(), 'p_dados': {'nome': 'Nao grava', 'tipo': 'RENDA_EXTRA', 'valor': '10.00',
                                                                                   'competencia': '2035-03-01', 'recorrente': False}},
            'criar_cartao': {'p_perfil_id': perfil, 'p_chave': k(), 'p_dados': {'nome': 'Nao grava', 'dia_fechamento': 1, 'dia_vencimento': 10}},
            'atualizar_perfil': {'p_perfil_id': perfil, 'p_dados': {'nome': 'Nao grava'}},
            'inativar_perfil': {'p_perfil_id': perfil},
        }
        respostas = {f: chamar(f, corpo) for f, corpo in tentativas.items()}
        recusadas = {f: (s, (r or {}).get('hint')) for f, (s, r) in respostas.items()}
        reg('perfil no Flask: as 7 escritas recusadas com SISTEMA_FLASK', all(h == 'SISTEMA_FLASK' for _, h in recusadas.values()), recusadas)
        reg('perfil no Flask: nada mudou no perfil (todas as tabelas)', linhas_do_perfil(perfil) == antes)
    finally:
        L.atribuir(perfil, 'NOVO')

    # 3. Quem so le recebe 403 (antes de qualquer informacao sobre o escritor).
    s, r = chamar('criar_despesa', {'p_perfil_id': perfil, 'p_dados': {**dados, 'nome': 'Invasao'}, 'p_chave': k()}, tb)
    reg('LEITOR: 403', s in (401, 403), (s, (r or {}).get('hint')))

    # 4. De volta ao novo aplicativo: edita; inativa e reativa o perfil (caminho do perfil inativo).
    s, r = chamar('editar_despesa', {'p_perfil_id': perfil, 'p_conta_id': conta, 'p_versao': versao, 'p_dados': {'valor': '45.00'}})
    valor = M.ler('select valor from public.conta where id = %s', (conta,))[0]['valor']
    reg('perfil NOVO: edicao grava', s == 200 and float(valor) == 45.0, (s, valor))
    si, _ = chamar('inativar_perfil', {'p_perfil_id': perfil})
    sr, _ = chamar('reativar_perfil', {'p_perfil_id': perfil})
    ativo = M.ler('select ativo from public.perfil_financeiro where id = %s', (perfil,))[0]['ativo']
    reg('inativar e reativar o proprio perfil (gestao com perfil inativo)', (si, sr) == (200, 200) and ativo is True, (si, sr, ativo))
    falhas = [nome for nome, ok in L.RESULTADOS if not ok]
    print(f'{len(L.RESULTADOS) - len(falhas)}/{len(L.RESULTADOS)} OK', '| falhas:', falhas or 'nenhuma')
    return 1 if falhas else 0


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
            cur.execute("select count(*) from public.item_despesa where perfil_financeiro_id = %s and nome <> %s", (perfil, DESPESA))
            if cur.fetchone()[0]:
                raise SystemExit('Item fora do teste no perfil temporario: interrompido.')
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
            p = [perfil]
            comandos = [
                ('contas', 'delete from public.conta where perfil_financeiro_id = %s', p),
                ('itens', 'delete from public.item_despesa where perfil_financeiro_id = %s', p),
                ('chaves', 'delete from financeiro.operacao_despesa where perfil_financeiro_id = %s', p),
                ('gerador', 'delete from financeiro.gerador_recorrencia where perfil_financeiro_id = %s', p),
                ('historico_gerador', 'delete from financeiro.gerador_recorrencia_historico where perfil_financeiro_id = %s', p),
                ('vinculos', 'delete from financeiro.perfil_acesso where perfil_financeiro_id = %s', p),
                ('perfil', 'delete from public.perfil_financeiro where id = %s and nome = %s', [perfil, L.PERFIL]),
            ]
            removidos = {}
            for rotulo, comando, params in comandos:
                cur.execute(comando, params)
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
