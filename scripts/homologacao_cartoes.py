"""FIN-FIDELIDADE-CARTOES-2 — perfil FICTICIO de homologacao de Cartoes, so no Supabase de TESTE.

Uso (venv do projeto; credenciais da conta de avaliacao em .env.e2e-real, banco em .env.staging):
    venv\\Scripts\\python.exe scripts\\homologacao_cartoes.py criar
    venv\\Scripts\\python.exe scripts\\homologacao_cartoes.py recorrencia       (R2: acrescenta a recorrencia no cartao, se faltar)
    venv\\Scripts\\python.exe scripts\\homologacao_cartoes.py conferir          (so leitura: previsto / realizado / pago)
    venv\\Scripts\\python.exe scripts\\homologacao_cartoes.py remover [--confirmar]

Protecoes:
- so roda no projeto de TESTE (ref "fzjmge..."): qualquer outro projeto (producao, Calculadora) interrompe;
- o perfil e criado pelo proprio aplicativo (criar_perfil, como a conta de avaliacao) e os dados pelas funcoes do
  aplicativo; so o que nao tem funcao (conta bancaria, Categorias do Cartao do perfil e o mapa delas, consolidacao da
  fatura como a do Flask) vai por SQL, sempre com perfil_financeiro_id do perfil de homologacao;
- a remocao e por identidade: o perfil pelo nome e pelos vinculos (so a conta de avaliacao, TITULAR), e cada tabela so
  pelo perfil (ou pelos itens dele); Categorias do Cartao e conta bancaria tambem pelo nome; sem --confirmar e simulacao;
- os perfis 1 (Pessoal), 2 (Empresa) e 31 (demonstracao) e as categorias globais sao conferidos por impressao digital:
  se mudarem, nada e gravado.
Nao imprime e-mails, senhas, chaves nem URL do banco. Nenhum numero, validade ou CVV de cartao.
"""
# FIN-PUBLICACAO-SEGURA-1: o projeto de teste virou a producao; recusa antes de ler credenciais ou conectar.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from guarda_producao import recusar_em_producao
recusar_em_producao(__file__)
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / 'scripts'))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(RAIZ / '.env.e2e-real', override=False, encoding='utf-8-sig')

PREFIXO_TESTE = 'fzjmge'  # projeto Supabase de teste; nada roda fora dele
PROTEGIDOS = (1, 2, 31)
PERFIL = 'Homologacao Cartoes (ficticio)'
M = '(homologacao)'
CONTA = f'Conta Corrente {M}'
CATEGORIAS_CARTAO = [  # nome, categoria de despesa (global, ja existente), limite no Cartao Azul
    (f'Mercado {M}', 'Alimentacao (demonstracao)', '800.00'),
    (f'Combustivel {M}', 'Combustível', '600.00'),
    (f'Lazer {M}', 'Lazer (demonstracao)', '300.00'),
    (f'Casa {M}', 'Moradia (demonstracao)', '180.00'),
]
AZUL, VERDE = f'Cartao Azul {M}', f'Cartao Verde {M}'
COMPRAS = [  # cartao, descricao, valor, parcelas, data, mes da fatura, categoria de despesa
    (AZUL, f'Supermercado {M}', '320.00', 1, '2026-08-20', '2026-09-01', 'Alimentacao (demonstracao)'),
    (AZUL, f'Posto {M}', '250.00', 1, '2026-08-25', '2026-09-01', 'Combustível'),
    (AZUL, f'Supermercado {M}', '450.00', 1, '2026-09-28', '2026-10-01', 'Alimentacao (demonstracao)'),
    (AZUL, f'Posto Centro {M}', '380.00', 1, '2026-09-27', '2026-10-01', 'Combustível'),
    (AZUL, f'Posto Rodovia {M}', '240.00', 1, '2026-10-01', '2026-10-01', 'Combustível'),
    (AZUL, f'Cinema {M}', '90.00', 1, '2026-09-30', '2026-10-01', 'Lazer (demonstracao)'),
    (AZUL, f'Farmacia {M}', '60.00', 1, '2026-09-29', '2026-10-01', 'Saude (demonstracao)'),
    (AZUL, f'Notebook {M}', '1500.00', 10, '2026-09-26', '2026-10-01', 'Moradia (demonstracao)'),
    (AZUL, f'Assinatura streaming {M}', '39.90', 1, '2026-10-20', '2026-11-01', 'Lazer (demonstracao)'),
    (VERDE, f'Restaurante {M}', '85.00', 1, '2026-09-10', '2026-10-01', 'Lazer (demonstracao)'),
    (VERDE, f'Padaria {M}', '32.50', 1, '2026-09-12', '2026-10-01', 'Alimentacao (demonstracao)'),
]
RECORRENCIA = {'nome': f'Musica mensal {M}', 'valor': '21.90', 'data_vencimento': '2026-11-12', 'tipo_recorrencia': 'mensal',
               'descricao': 'Recorrencia no cartao (R2)'}


def conectar():
    import psycopg2
    from supabase_migrations import _url
    url, ref = _url()
    if not ref.startswith(PREFIXO_TESTE):
        raise SystemExit('Banco nao e o Supabase de teste: interrompido.')
    conn = psycopg2.connect(url, connect_timeout=15)
    conn.autocommit = False
    return conn


def sessao():
    from verificar_exposicao_supabase import PROJETO, chave_publica_via_cli
    if not PROJETO.startswith(PREFIXO_TESTE):
        raise SystemExit('Projeto nao e o Supabase de teste: interrompido.')
    origem = f'https://{PROJETO}.supabase.co'
    chave, _ = chave_publica_via_cli()
    corpo = json.dumps({'email': os.environ['CF_EMAIL_A'], 'password': os.environ['CF_SENHA_A']}).encode()
    req = urllib.request.Request(f'{origem}/auth/v1/token?grant_type=password', method='POST', data=corpo)
    req.add_header('apikey', chave)
    req.add_header('Content-Type', 'application/json')
    with urllib.request.urlopen(req, timeout=30) as r:
        return origem, chave, json.loads(r.read())['access_token']


def chamar(ctx, funcao, corpo):
    origem, chave, token = ctx
    req = urllib.request.Request(f'{origem}/rest/v1/rpc/{funcao}', method='POST', data=json.dumps(corpo).encode())
    for k, v in (('apikey', chave), ('Content-Type', 'application/json'), ('Content-Profile', 'financeiro'),
                 ('Authorization', f'Bearer {token}')):
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read() or b'null')
    except urllib.error.HTTPError as exc:
        raise SystemExit(f'{funcao}: {exc.code} {exc.read()[:300]!r}')


def conta_avaliacao(cur):
    cur.execute('select id from auth.users where lower(email) = lower(%s)', (os.environ['CF_EMAIL_A'],))
    return str(cur.fetchone()[0])


def retrato_protegido(cur):
    """md5 das linhas dos perfis protegidos em toda tabela com perfil_financeiro_id, e das categorias globais."""
    cur.execute("""select table_schema || '.' || table_name from information_schema.columns
                    where column_name = 'perfil_financeiro_id' and table_schema in ('public', 'financeiro')
                      and table_name in (select table_name from information_schema.tables where table_type = 'BASE TABLE')
                    order by 1""")
    partes = []
    for (t,) in cur.fetchall():
        cur.execute(f"select coalesce(md5(string_agg(x::text, '|' order by x::text)), '') from {t} x "
                    'where perfil_financeiro_id = any(%s)', (list(PROTEGIDOS),))
        partes.append(f'{t}:{cur.fetchone()[0]}')
    cur.execute("select md5(string_agg(c::text, '|' order by c.id)) from public.categoria c")
    partes.append(f'categoria:{cur.fetchone()[0]}')
    return hashlib.md5('\n'.join(partes).encode()).hexdigest()


def perfil_de_homologacao(cur):
    """O perfil pelo nome, so com a conta de avaliacao como TITULAR. Qualquer outra coisa interrompe."""
    cur.execute('select id from public.perfil_financeiro where nome = %s', (PERFIL,))
    linhas = cur.fetchall()
    if len(linhas) != 1:
        raise SystemExit(f'Esperado 1 perfil "{PERFIL}", encontrados {len(linhas)}: interrompido.')
    perfil = linhas[0][0]
    if perfil in PROTEGIDOS:
        raise SystemExit('Perfil protegido: interrompido.')
    cur.execute('select user_id::text, papel from financeiro.perfil_acesso where perfil_financeiro_id = %s', (perfil,))
    if cur.fetchall() != [(conta_avaliacao(cur), 'TITULAR')]:
        raise SystemExit('Vinculos inesperados no perfil de homologacao: interrompido.')
    return perfil


def ids_do_perfil(cur, perfil):
    cur.execute('select id, nome from public.item_despesa where perfil_financeiro_id = %s', (perfil,))
    itens = cur.fetchall()
    cartoes = {n: i for i, n in itens if n in (AZUL, VERDE)}
    return cartoes, [i for i, _ in itens]


def criar_recorrencia(ctx, cur, perfil, cartoes):
    cur.execute('select count(*) from public.item_despesa where perfil_financeiro_id = %s and nome = %s', (perfil, RECORRENCIA['nome']))
    if cur.fetchone()[0]:
        print('recorrencia no cartao ja existe')
        return
    cur.execute("select id from public.categoria where nome = 'Lazer (demonstracao)'")
    categoria = cur.fetchone()[0]
    r = chamar(ctx, 'criar_recorrencia_cartao', {'p_perfil_id': perfil, 'p_chave': str(uuid.uuid4()),
                                                  'p_dados': {**RECORRENCIA, 'categoria_id': categoria, 'cartao_id': cartoes[AZUL]}})
    print('recorrencia no cartao criada:', r['item_id'])


def criar():
    conn = conectar()
    with conn.cursor() as cur:
        cur.execute('select count(*) from public.perfil_financeiro where nome = %s', (PERFIL,))
        if cur.fetchone()[0]:
            raise SystemExit('Perfil de homologacao ja existe: interrompido.')
        antes = retrato_protegido(cur)
        cur.execute('select id, nome from public.categoria where coalesce(ativo, true)')
        categorias = {n: i for i, n in cur.fetchall()}
    conn.rollback()
    ctx = sessao()
    perfil = chamar(ctx, 'criar_perfil', {'p_dados': {'nome': PERFIL, 'tipo': 'PESSOAL', 'cor': '#0f766e'}})['id']
    with conn.cursor() as cur:
        perfil_de_homologacao(cur)
        cur.execute('select gerador from financeiro.gerador_recorrencia where perfil_financeiro_id = %s', (perfil,))
        if cur.fetchone()[0] != 'NOVO':
            raise SystemExit('Perfil criado fora do gerador NOVO: interrompido.')
        cur.execute("insert into public.conta_bancaria (perfil_financeiro_id, nome, instituicao, tipo, status, cor_display, "
                    "saldo_inicial, saldo_atual) values (%s, %s, 'Banco ficticio (homologacao)', 'Conta Corrente', 'ATIVO', "
                    "'#2563eb', 10000, 10000) returning id", (perfil, CONTA))
        conta = cur.fetchone()[0]
        categorias_cartao = {}
        for nome, despesa, _ in CATEGORIAS_CARTAO:
            cur.execute("insert into public.categoria_cartao (perfil_financeiro_id, nome, ativo, cor) values (%s, %s, true, '#0ea5e9') "
                        'returning id', (perfil, nome))
            categorias_cartao[nome] = cur.fetchone()[0]
            cur.execute('insert into public.categoria_cartao_despesa (perfil_financeiro_id, categoria_cartao_id, categoria_id, ativo) '
                        'values (%s, %s, %s, true)', (perfil, categorias_cartao[nome], categorias[despesa]))
    conn.commit()

    cartoes = {}
    for nome, fechamento, vencimento, limite, confirmado in ((AZUL, 3, 12, '5000.00', True), (VERDE, 25, 5, '2500.00', False)):
        cartoes[nome] = chamar(ctx, 'criar_cartao', {'p_perfil_id': perfil, 'p_chave': str(uuid.uuid4()), 'p_dados': {
            'nome': nome, 'descricao': 'Banco ficticio (homologacao)', 'dia_fechamento': fechamento, 'dia_vencimento': vencimento,
            'limite_credito': limite, 'fechamento_confirmado': confirmado, 'tem_codigo': True}})['cartao_id']
    for nome, _, limite in CATEGORIAS_CARTAO:
        chamar(ctx, 'vincular_limite_cartao', {'p_perfil_id': perfil, 'p_cartao_id': cartoes[AZUL],
                                               'p_dados': {'categoria_cartao_id': categorias_cartao[nome], 'limite_mensal': limite}})
    for cartao, descricao, valor, parcelas, data, mes, despesa in COMPRAS:
        chamar(ctx, 'criar_compra', {'p_perfil_id': perfil, 'p_chave': str(uuid.uuid4()), 'p_dados': {
            'cartao_id': cartoes[cartao], 'descricao': descricao, 'valor': valor, 'total_parcelas': parcelas,
            'data_compra': data, 'mes_fatura': mes, 'categoria_id': categorias[despesa]}})
    # Fatura 09/2026 do Azul paga (pagamento integral, pela conta de homologacao).
    fatura = next(x for x in chamar(ctx, 'faturas_do_mes', {'p_perfil_id': perfil, 'p_mes': '2026-09-01'}) if x['cartao_id'] == cartoes[AZUL])
    executado = f"{float(chamar(ctx, 'dados_pagamento_fatura', {'p_perfil_id': perfil, 'p_fatura_id': fatura['fatura_id']})['fatura']['valor_executado']):.2f}"
    chamar(ctx, 'pagar_fatura', {'p_perfil_id': perfil, 'p_fatura_id': fatura['fatura_id'], 'p_chave': str(uuid.uuid4()), 'p_dados': {
        'conta_bancaria_id': conta, 'data_pagamento': '2026-09-12', 'valor_pago': executado, 'valor_executado': executado}})
    # Fatura 10/2026 do Verde consolidada, como a rota de consolidacao do Flask (sem funcao no novo aplicativo).
    verde = next(x for x in chamar(ctx, 'faturas_do_mes', {'p_perfil_id': perfil, 'p_mes': '2026-10-01'}) if x['cartao_id'] == cartoes[VERDE])
    with conn.cursor() as cur:
        cur.execute("update public.conta set status_fatura = 'FECHADA', valor_consolidado = valor_executado, data_consolidacao = now() "
                    "where id = %s and perfil_financeiro_id = %s and is_fatura_cartao and status_fatura = 'ABERTA'", (verde['fatura_id'], perfil))
        if cur.rowcount != 1:
            raise SystemExit('Consolidacao inesperada: interrompido.')
        cur.execute("select count(*) from pg_proc where proname = 'criar_recorrencia_cartao'")
        if cur.fetchone()[0]:
            criar_recorrencia(ctx, cur, perfil, cartoes)
        intactos = retrato_protegido(cur) == antes
    conn.commit()
    conn.close()
    print('perfil de homologacao', perfil, '| cartoes', cartoes, '| conta', conta, '| perfis protegidos intactos:', intactos)


def recorrencia():
    conn = conectar()
    with conn.cursor() as cur:
        perfil = perfil_de_homologacao(cur)
        cartoes, _ = ids_do_perfil(cur, perfil)
        criar_recorrencia(sessao(), cur, perfil, cartoes)
    conn.rollback()
    conn.close()


def conferir():
    conn = conectar()
    with conn.cursor() as cur:
        perfil = perfil_de_homologacao(cur)
        cartoes, itens = ids_do_perfil(cur, perfil)
        cur.execute('select count(*) from public.config_agregador where item_despesa_id = any(%s) '
                    'and (numero_cartao is not null or codigo_seguranca is not null or data_validade is not null)', (itens,))
        sensiveis = cur.fetchone()[0]
    conn.rollback()
    conn.close()
    ctx = sessao()
    for mes in ('2026-09-01', '2026-10-01', '2026-11-01'):
        for c in chamar(ctx, 'contas_do_mes', {'p_perfil_id': perfil, 'p_mes': mes}):
            print(f"  {mes[:7]} {c['nome']}: exibido {c['valor']} | previsto {c['valor_previsto']} | realizado {c['valor_executado']} "
                  f"| {c['situacao']}")
    recs = [r for r in chamar(ctx, 'recorrencias_do_perfil', {'p_perfil_id': perfil}) if r['meio_pagamento'] == 'cartao']
    print('  recorrencias no cartao:', [(r['nome'], r['valor'], r['cartao_nome'], r['ativo']) for r in recs])
    print('  dados sensiveis de cartao guardados:', sensiveis)


def remover(confirmar):
    conn = conectar()
    try:
        with conn.cursor() as cur:
            perfil = perfil_de_homologacao(cur)
            antes = retrato_protegido(cur)
            _, itens = ids_do_perfil(cur, perfil)
            nomes_cc = [n for n, _, _ in CATEGORIAS_CARTAO]
            cur.execute('select nome from public.categoria_cartao where perfil_financeiro_id = %s', (perfil,))
            if any(n not in nomes_cc for (n,) in cur.fetchall()):
                raise SystemExit('Categoria do Cartao fora do roteiro no perfil: interrompido.')
            cur.execute('select nome from public.conta_bancaria where perfil_financeiro_id = %s', (perfil,))
            if any(n != CONTA for (n,) in cur.fetchall()):
                raise SystemExit('Conta bancaria fora do roteiro no perfil: interrompido.')
            comandos = [
                ('limites', 'delete from public.cartao_categoria_limite where perfil_financeiro_id = %s and cartao_id = any(%s)', [perfil, itens]),
                ('mapas', 'delete from public.categoria_cartao_despesa where perfil_financeiro_id = %s', [perfil]),
                ('pagamentos_fatura', 'delete from financeiro.pagamento_fatura where perfil_financeiro_id = %s', [perfil]),
                ('movimentos', 'delete from public.movimento_financeiro where perfil_financeiro_id = %s', [perfil]),
                ('identidades', 'delete from financeiro.recorrencia_competencia where item_despesa_id = any(%s)', [itens]),
                ('rejeicoes', 'delete from public.recorrencia_rejeicao where perfil_financeiro_id = %s', [perfil]),
                ('inclusoes', 'delete from public.fatura_consolidada_inclusao where perfil_financeiro_id = %s', [perfil]),
                ('compras', 'delete from public.lancamento_agregado where perfil_financeiro_id = %s or cartao_id = any(%s)', [perfil, itens]),
                ('contas', 'delete from public.conta where perfil_financeiro_id = %s or item_despesa_id = any(%s)', [perfil, itens]),
                ('configs_cartao', 'delete from public.config_agregador where item_despesa_id = any(%s)', [itens]),
                ('itens', 'delete from public.item_despesa where id = any(%s) and perfil_financeiro_id = %s', [itens, perfil]),
                ('chaves', 'delete from financeiro.operacao_despesa where perfil_financeiro_id = %s', [perfil]),
                ('chaves_cartao', 'delete from financeiro.operacao_cartao where perfil_financeiro_id = %s', [perfil]),
                ('execucoes', 'delete from financeiro.geracao_execucao where perfil_financeiro_id = %s', [perfil]),
                ('gerador', 'delete from financeiro.gerador_recorrencia where perfil_financeiro_id = %s', [perfil]),
                ('historico_gerador', 'delete from financeiro.gerador_recorrencia_historico where perfil_financeiro_id = %s', [perfil]),
                ('vinculos', 'delete from financeiro.perfil_acesso where perfil_financeiro_id = %s', [perfil]),
                ('conta_bancaria', 'delete from public.conta_bancaria where perfil_financeiro_id = %s and nome = %s', [perfil, CONTA]),
                ('categorias_cartao', 'delete from public.categoria_cartao where perfil_financeiro_id = %s and nome = any(%s)', [perfil, nomes_cc]),
                ('perfil', 'delete from public.perfil_financeiro where id = %s and nome = %s', [perfil, PERFIL]),
            ]
            removidos = {}
            for rotulo, sql, params in comandos:
                cur.execute(sql, params)
                removidos[rotulo] = cur.rowcount
            print('removidos:', {k: v for k, v in removidos.items() if v})
            cur.execute("""select table_schema || '.' || table_name from information_schema.columns
                            where column_name = 'perfil_financeiro_id' and table_schema in ('public', 'financeiro')
                              and table_name in (select table_name from information_schema.tables where table_type = 'BASE TABLE')""")
            for (t,) in cur.fetchall():
                cur.execute(f'select count(*) from {t} where perfil_financeiro_id = %s', (perfil,))
                if cur.fetchone()[0]:
                    raise SystemExit(f'Sobraram linhas do perfil em {t}: nada removido.')
            if retrato_protegido(cur) != antes:
                raise SystemExit('Retrato dos perfis protegidos mudou: nada removido.')
        if confirmar:
            conn.commit()
            print('CONFIRMADO: perfil de homologacao removido.')
        else:
            conn.rollback()
            print('SIMULACAO: nada foi gravado (use --confirmar).')
    finally:
        conn.close()


if __name__ == '__main__':
    etapas = {'criar': criar, 'recorrencia': recorrencia, 'conferir': conferir}
    etapa = sys.argv[1] if len(sys.argv) > 1 else ''
    if etapa == 'remover':
        remover('--confirmar' in sys.argv)
    elif etapa in etapas:
        etapas[etapa]()
    else:
        raise SystemExit(__doc__)
