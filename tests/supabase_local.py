"""
CF-SUPABASE-REFACTOR-1 — ambiente isolado para testar a nova arquitetura sem Docker.

Sobe um cluster PostgreSQL DESCARTAVEL (initdb em diretorio temporario, so em
127.0.0.1, porta livre) com os binarios locais do PostgreSQL, aplica o shim dos
objetos do Supabase (roles, auth.uid()) e as migrations de `supabase/migrations`.
Opcionalmente sobe o PostgREST (mesma camada REST do Supabase) apontando para ele.

Nunca conecta ao banco local de desenvolvimento nem ao Supabase remoto.
Usuarios e dados sao ficticios.
"""
import base64
import glob
import hashlib
import hmac
import json
import os
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUPABASE_DIR = ROOT / 'supabase'

USUARIO_A = {'id': str(uuid.UUID('aaaaaaaa-0000-4000-8000-00000000000a')), 'email': 'usuario.a@teste.local'}
USUARIO_B = {'id': str(uuid.UUID('bbbbbbbb-0000-4000-8000-00000000000b')), 'email': 'usuario.b@teste.local'}
CATEGORIAS_A = ['Moradia (A)', 'Transporte (A)', 'Lazer (A)']
CATEGORIAS_B = ['Saude (B)', 'Educacao (B)']


def encontrar_pg_bin():
    """Diretorio com initdb/pg_ctl: CF_MVP_PG_BIN, PATH ou instalacao padrao do Windows."""
    configurado = os.getenv('CF_MVP_PG_BIN')
    candidatos = [configurado] if configurado else []
    no_path = shutil.which('initdb')
    if no_path:
        candidatos.append(str(Path(no_path).parent))
    candidatos += sorted(glob.glob(r'C:\Program Files\PostgreSQL\*\bin'), reverse=True)
    for candidato in candidatos:
        if candidato and (Path(candidato) / _exe('initdb')).exists() and (Path(candidato) / _exe('pg_ctl')).exists():
            return Path(candidato)
    return None


def encontrar_postgrest():
    caminho = os.getenv('POSTGREST_BIN') or shutil.which('postgrest')
    return Path(caminho) if caminho and Path(caminho).exists() else None


def _exe(nome):
    return f'{nome}.exe' if os.name == 'nt' else nome


def porta_livre():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class ClusterLocal:
    """Cluster PostgreSQL descartavel. Use como context manager."""

    def __init__(self, pg_bin, diretorio):
        self.pg_bin = Path(pg_bin)
        self.diretorio = Path(diretorio)
        self.dados = self.diretorio / 'pgdata'
        self.porta = porta_livre()

    def __enter__(self):
        subprocess.run(
            [str(self.pg_bin / _exe('initdb')), '-D', str(self.dados), '-U', 'postgres',
             '-A', 'trust', '-E', 'UTF8', '--no-locale'],
            check=True, capture_output=True,
        )
        # Sem pipes: no Windows o postgres herda os handles de stdout/stderr do
        # pg_ctl, e capture_output faria o subprocess.run esperar para sempre.
        with open(self.diretorio / 'pg_ctl.log', 'wb') as saida:
            resultado = subprocess.run(
                [str(self.pg_bin / _exe('pg_ctl')), '-D', str(self.dados), '-l', str(self.diretorio / 'pg.log'),
                 '-o', f'-p {self.porta} -h 127.0.0.1', '-w', '-t', '60', 'start'],
                stdin=subprocess.DEVNULL, stdout=saida, stderr=subprocess.STDOUT, timeout=90,
            )
        if resultado.returncode != 0:
            log = (self.diretorio / 'pg.log')
            raise RuntimeError('pg_ctl start falhou: ' + (log.read_text(errors='replace')[-800:] if log.exists() else ''))
        return self

    def __exit__(self, *exc):
        subprocess.run(
            [str(self.pg_bin / _exe('pg_ctl')), '-D', str(self.dados), '-m', 'immediate', '-w', 'stop'],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60,
        )

    def dsn(self, usuario='postgres'):
        return f'postgresql://{usuario}@127.0.0.1:{self.porta}/postgres'

    def conectar(self, usuario='postgres'):
        import psycopg2
        conn = psycopg2.connect(self.dsn(usuario))
        conn.autocommit = True
        return conn

    def aplicar_shim(self):
        conn = self.conectar()
        try:
            with conn.cursor() as cur:
                cur.execute((SUPABASE_DIR / 'tests' / 'local_supabase_shim.sql').read_text(encoding='utf-8'))
        finally:
            conn.close()

    def criar_papel_estilo_supabase(self, nome='supa_postgres'):
        """Papel que imita o `postgres` do Supabase: sem superuser, com BYPASSRLS e
        com os default privileges da plataforma (ALL para anon/authenticated no public)."""
        conn = self.conectar()
        try:
            with conn.cursor() as cur:
                cur.execute(f'create role {nome} login nosuperuser bypassrls')
                cur.execute(f'grant usage, create on schema public to {nome}')
                for tipo in ('tables', 'sequences', 'functions'):
                    cur.execute(f'alter default privileges for role {nome} in schema public '
                                f'grant all on {tipo} to anon, authenticated, service_role')
        finally:
            conn.close()
        return nome

    def criar_tabelas_legadas(self):
        """Tabelas do Flask (models) + protecao SEC-SUPABASE-PUBLIC-1, como no staging."""
        import importlib.util

        from sqlalchemy import create_engine

        from backend.models import db
        engine = create_engine(self.dsn())
        try:
            db.metadata.create_all(bind=engine)
            caminho = next((ROOT / 'migrations' / 'versions').glob('c4f7a2d91b3e_*.py'))
            spec = importlib.util.spec_from_file_location('migration_sec_public_local', caminho)
            migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration)
            with engine.begin() as conn:
                migration.aplicar_protecao(conn)
        finally:
            engine.dispose()

    def preparar(self, contas=True):
        """Shim do Supabase + tabelas do Flask protegidas + migrations de supabase/ + dados ficticios.

        contas=False: sem as contas do MOBILE-CONTAS-1 (cenarios proprios, ex.: FIN-RECORRENCIA-1)."""
        self.aplicar_shim()
        self.criar_tabelas_legadas()
        conn = self.conectar()
        try:
            with conn.cursor() as cur:
                for migration in sorted((SUPABASE_DIR / 'migrations').glob('*.sql')):
                    cur.execute(migration.read_text(encoding='utf-8'))
                for usuario in (USUARIO_A, USUARIO_B):
                    cur.execute('insert into auth.users (id, email) values (%s, %s)', (usuario['id'], usuario['email']))
                for usuario, nomes in ((USUARIO_A, CATEGORIAS_A), (USUARIO_B, CATEGORIAS_B)):
                    for nome in nomes:
                        cur.execute(
                            'insert into financeiro.categorias (user_id, nome, descricao) values (%s, %s, %s)',
                            (usuario['id'], nome, 'Dado ficticio de teste'),
                        )
                semear_perfis(cur)
                if contas:
                    semear_contas(cur)
        finally:
            conn.close()


# PERFIS-1: perfis, vinculos e contas bancarias FICTICIOS (ids fixos para os testes).
PERFIS = {
    'PESSOAL': {'id': 101, 'nome': 'Pessoal', 'tipo': 'PESSOAL', 'padrao': True, 'ativo': True},
    'EMPRESA': {'id': 102, 'nome': 'Empresa', 'tipo': 'EMPRESA', 'padrao': False, 'ativo': True},
    'PERFIL_B': {'id': 103, 'nome': 'Perfil B', 'tipo': 'PESSOAL', 'padrao': False, 'ativo': True},
    'INATIVO_A': {'id': 104, 'nome': 'Perfil inativo (A)', 'tipo': 'EMPRESA', 'padrao': False, 'ativo': False},
}
VINCULOS = [  # (usuario, perfil, papel, pode_gerir) — nada e vinculado automaticamente
    (USUARIO_A, 'PESSOAL', 'TITULAR', True),
    (USUARIO_A, 'EMPRESA', 'LEITOR', False),
    (USUARIO_A, 'INATIVO_A', 'TITULAR', True),
    (USUARIO_B, 'PERFIL_B', 'TITULAR', True),
]
CONTAS = [  # (nome, perfil ou None = legado do "Pessoal")
    ('Conta Pessoal (A)', 'PESSOAL'),
    ('Carteira legado sem perfil', None),
    ('Conta Empresa (A)', 'EMPRESA'),
    ('Conta Perfil B', 'PERFIL_B'),
    ('Conta do perfil inativo', 'INATIVO_A'),
]
CONTAS_ESPERADAS = {
    'PESSOAL': ['Carteira legado sem perfil', 'Conta Pessoal (A)'],
    'EMPRESA': ['Conta Empresa (A)'],
    'PERFIL_B': ['Conta Perfil B'],
}


def semear_perfis(cur):
    for perfil in PERFIS.values():
        cur.execute(
            'insert into public.perfil_financeiro (id, nome, tipo, cor, ativo, padrao) values (%s, %s, %s, %s, %s, %s)',
            (perfil['id'], perfil['nome'], perfil['tipo'], '#2563eb', perfil['ativo'], perfil['padrao']),
        )
    for usuario, chave, papel, pode_gerir in VINCULOS:
        cur.execute('insert into financeiro.perfil_acesso (user_id, perfil_financeiro_id, papel, pode_gerir) '
                    'values (%s, %s, %s, %s)', (usuario['id'], PERFIS[chave]['id'], papel, pode_gerir))
    for nome, chave in CONTAS:
        cur.execute(
            "insert into public.conta_bancaria (perfil_financeiro_id, nome, instituicao, tipo, status, cor_display) "
            "values (%s, %s, 'Banco ficticio', 'Conta Corrente', 'ATIVO', '#3b82f6')",
            (PERFIS[chave]['id'] if chave else None, nome),
        )


def assinar_jwt(claims, segredo):
    """JWT HS256 no formato usado pelo Supabase Auth (sem dependencia externa)."""
    def b64(dados):
        return base64.urlsafe_b64encode(dados).rstrip(b'=').decode()

    cabecalho = b64(json.dumps({'alg': 'HS256', 'typ': 'JWT'}, separators=(',', ':')).encode())
    corpo = b64(json.dumps(claims, separators=(',', ':')).encode())
    assinatura = hmac.new(segredo.encode(), f'{cabecalho}.{corpo}'.encode(), hashlib.sha256).digest()
    return f'{cabecalho}.{corpo}.{b64(assinatura)}'


def claims_usuario(usuario, segundos=3600):
    agora = int(time.time())
    return {'sub': usuario['id'], 'email': usuario['email'], 'role': 'authenticated',
            'aud': 'authenticated', 'iat': agora, 'exp': agora + segundos}


class PostgrestLocal:
    """PostgREST apontando para o cluster descartavel, expondo public e financeiro."""

    def __init__(self, binario, cluster, segredo_jwt, diretorio, schemas='public,financeiro'):
        # Todos os schemas expostos precisam existir: se faltar um, o PostgREST nao
        # carrega o cache de schema e fica em 503 indefinidamente.
        self.schemas = schemas
        self.binario = Path(binario)
        self.cluster = cluster
        self.segredo_jwt = segredo_jwt
        self.porta = porta_livre()
        self.porta_admin = porta_livre()
        self.log = Path(diretorio) / 'postgrest.log'
        self.processo = None

    @property
    def url(self):
        return f'http://127.0.0.1:{self.porta}'

    def __enter__(self):
        env = dict(os.environ)
        env.update({
            'PGRST_DB_URI': self.cluster.dsn('authenticator'),
            'PGRST_DB_SCHEMAS': self.schemas,
            'PGRST_DB_ANON_ROLE': 'anon',
            'PGRST_JWT_SECRET': self.segredo_jwt,
            'PGRST_JWT_AUD': 'authenticated',
            'PGRST_SERVER_HOST': '127.0.0.1',
            'PGRST_SERVER_PORT': str(self.porta),
            'PGRST_ADMIN_SERVER_PORT': str(self.porta_admin),
            'PGRST_DB_CHANNEL_ENABLED': 'false',
        })
        self._log = open(self.log, 'wb')
        self.processo = subprocess.Popen([str(self.binario)], env=env, stdout=self._log, stderr=subprocess.STDOUT)
        try:
            self._aguardar_pronto()
        except BaseException:
            # Nunca deixar processo orfao se a subida falhar.
            self.__exit__(None, None, None)
            raise
        return self

    def _aguardar_pronto(self):
        """/ready do servidor admin: 200 so quando conexao e cache de schema estao prontos."""
        limite = time.time() + 30
        ultimo_erro = None
        while time.time() < limite:
            if self.processo.poll() is not None:
                raise RuntimeError(f'PostgREST encerrou: {self.log.read_text(errors="replace")[-800:]}')
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{self.porta_admin}/ready', timeout=2) as resp:
                    if resp.status == 200:
                        return
            except OSError as exc:
                ultimo_erro = exc
            time.sleep(0.2)
        raise RuntimeError(f'PostgREST nao ficou pronto em 30 s (ultimo erro: {ultimo_erro!r})')

    def __exit__(self, *exc):
        if self.processo and self.processo.poll() is None:
            self.processo.terminate()
            try:
                self.processo.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.processo.kill()
        self._log.close()


# MOBILE-CONTAS-1: contas do mes FICTICIAS, declaradas uma unica vez e usadas tanto
# no cluster local (ids fixos) quanto no Supabase de teste (ids gerados pelo banco,
# scripts/supabase_contas_seed_teste.py). Os ids abaixo sao LOGICOS; os valores
# esperados (calculados a mao) estao em CONTAS_MES_ESPERADO.
# Perfil: 'PESSOAL', 'EMPRESA', 'PERFIL_B' ou None (legado sem perfil -> Pessoal).
CATEGORIAS_CONTAS = [(201, 'Moradia', '#2563eb'), (202, 'Saude', '#16a34a'), (203, 'Cartoes', '#9333ea')]
CATEGORIAS_CARTAO = [(301, 'Mercado'), (302, 'Restaurantes'), (303, 'Combustivel')]
ITENS_DESPESA = [  # id, nome, tipo, perfil, categoria, recorrente, data_vencimento
    (401, 'Aluguel', 'Simples', 'PESSOAL', 201, True, '2026-01-10'),
    (402, 'Internet', 'Simples', None, 201, False, '2026-01-20'),
    (403, 'Plano de saude', 'Simples', 'PESSOAL', 202, False, '2026-01-15'),
    (404, 'Cartao Azul', 'Agregador', 'PESSOAL', 203, False, None),
    (405, 'Cartao Verde', 'Agregador', None, 203, False, None),
    (406, 'Contador', 'Simples', 'EMPRESA', 201, False, '2026-11-10'),
    (407, 'Cartao Empresa', 'Agregador', 'EMPRESA', 203, False, None),
    (408, 'Aluguel B', 'Simples', 'PERFIL_B', 201, False, '2026-11-08'),
]
CONTAS_FICTICIAS = [  # id, item, perfil, mes_ref, venc, valor, status, data_pag, parcela, total, debito, fatura, competencia
    (501, 401, 'PESSOAL', '2026-11-01', '2026-12-05', '2000.00', 'Pendente', None, None, None, False, False, None),
    (502, 402, None, '2026-11-01', '2026-11-20', '150.50', 'Pago', '2026-11-19', None, None, False, False, None),
    (503, 403, 'PESSOAL', '2026-11-01', '2026-11-15', '800.00', 'Pendente', None, 3, 12, True, False, None),
    (504, 401, 'PESSOAL', '2026-01-01', '2026-01-10', '1900.00', 'Pendente', None, None, None, False, False, None),
    (505, 403, 'PESSOAL', '2026-01-01', '2026-01-15', '780.00', 'Atrasado', None, None, None, False, False, None),
    (506, 402, None, '2026-01-01', '2026-01-20', '150.50', 'Pago', '2026-01-25', None, None, False, False, None),
    (507, 406, 'EMPRESA', '2026-11-01', '2026-11-10', '1200.00', 'Pendente', None, None, None, False, False, None),
    (508, 408, 'PERFIL_B', '2026-11-01', '2026-11-08', '999.99', 'Pendente', None, None, None, False, False, None),
    (509, 404, 'PESSOAL', '2026-11-01', '2026-12-10', '0.00', 'Pendente', None, None, None, False, True, '2026-11-01'),
    (510, 405, None, '2026-11-01', '2026-11-25', '1.00', 'Pago', '2026-11-24', None, None, False, True, '2026-11-01'),
    (511, 407, 'EMPRESA', '2026-11-01', '2026-12-01', '0.00', 'Pendente', None, None, None, False, True, '2026-11-01'),
    (512, 404, 'PESSOAL', '2026-01-01', '2026-02-10', '0.00', 'Pago', '2026-02-09', None, None, False, True, '2026-01-01'),
]
LANCAMENTOS_FICTICIOS = [  # id, cartao, perfil, categoria_cartao, descricao, valor, mes_fatura, parcela, total
    (601, 404, 'PESSOAL', 301, 'Supermercado X', '300.00', '2026-11-01', 1, 1),
    (602, 404, 'PESSOAL', 301, 'Supermercado Y', '150.00', '2026-11-01', 1, 1),
    (603, 404, 'PESSOAL', 302, 'Restaurante Z', '420.00', '2026-11-01', 1, 1),
    (604, 404, 'PESSOAL', 303, 'Posto', '100.00', '2026-11-01', 1, 1),
    (605, 404, 'PESSOAL', None, 'Compra parcelada', '200.00', '2026-11-01', 2, 3),
    (606, 404, None, 301, 'Farmacia (legado)', '50.00', '2026-11-01', 1, 1),
    (607, 404, 'PESSOAL', 301, 'Supermercado dezembro', '999.00', '2026-12-01', 1, 1),
    (608, 405, None, 302, 'Livraria', '80.00', '2026-11-01', 1, 1),
    (609, 405, None, None, 'Cinema', '40.00', '2026-11-01', 1, 1),
    (610, 407, 'EMPRESA', None, 'Papelaria', '250.00', '2026-11-01', 1, 1),
    (611, 404, 'PESSOAL', 301, 'Mercado janeiro', '500.00', '2026-01-01', 1, 1),
]
LIMITES_FICTICIOS = [  # id, cartao, categoria_cartao, limite, ativo
    (701, 404, 301, '600.00', True),   # gasto 500 -> complemento 100
    (702, 404, 302, '300.00', True),   # gasto 420 -> complemento 0
    (703, 404, 303, '500.00', False),  # inativo: ignorado
    (704, 405, 301, '200.00', True),   # fatura paga: o previsto nao vale
]


def semear_contas(cur, perfis_ids=None, sufixo_nomes='', ids_fixos=True):
    """Insere os dados ficticios e devolve {id_logico: id_no_banco}.

    perfis_ids: {'PESSOAL': id, 'EMPRESA': id, 'PERFIL_B': id} (padrao: ids do cluster local).
    sufixo_nomes: marcador nos nomes de categorias (unicos no banco), para identificacao.
    ids_fixos=False: deixa o banco gerar os ids (projeto remoto).
    """
    perfis_ids = perfis_ids or {chave: perfil['id'] for chave, perfil in PERFIS.items()}
    mapa = {}

    def perfil(chave):
        return perfis_ids[chave] if chave else None

    def inserir(tabela, id_logico, colunas, valores):
        if ids_fixos:
            colunas, valores = ['id', *colunas], [id_logico, *valores]
        marcadores = ', '.join(['%s'] * len(colunas))
        cur.execute(f'insert into public.{tabela} ({", ".join(colunas)}) values ({marcadores}) returning id', valores)
        mapa[id_logico] = cur.fetchone()[0]

    if ids_fixos:
        cur.execute('update public.perfil_financeiro set avatar = upper(left(nome, 2))')  # evita o Flask completar o avatar
    for cid, nome, cor in CATEGORIAS_CONTAS:
        inserir('categoria', cid, ['nome', 'cor', 'ativo', 'sistemica', 'bloquear_edicao', 'bloquear_exclusao'],
                [nome + sufixo_nomes, cor, True, False, False, False])
    for cid, nome in CATEGORIAS_CARTAO:
        inserir('categoria_cartao', cid, ['nome', 'ativo'], [nome + sufixo_nomes, True])
    for iid, nome, tipo, chave, cat, rec, venc in ITENS_DESPESA:
        inserir('item_despesa', iid, ['nome', 'tipo', 'perfil_financeiro_id', 'categoria_id', 'ativo', 'recorrente',
                                      'tipo_recorrencia', 'data_vencimento'],
                [nome, tipo, perfil(chave), mapa[cat], True, rec, 'mensal', venc])
    nomes_item = {i[0]: i[1] for i in ITENS_DESPESA}
    for (cid, item, chave, mes, venc, valor, status, pag, parc, tot, deb, fatura, comp) in CONTAS_FICTICIAS:
        if fatura:
            descricao = f'Fatura {nomes_item[item]} - {comp[5:7]}/{comp[:4]}'
        else:
            descricao = f'{nomes_item[item]} {mes[5:7]}/{mes[:4]}'
        inserir('conta', cid, ['item_despesa_id', 'perfil_financeiro_id', 'mes_referencia', 'descricao', 'valor',
                               'data_vencimento', 'status_pagamento', 'data_pagamento', 'numero_parcela', 'total_parcelas',
                               'debito_automatico', 'is_fatura_cartao', 'cartao_competencia', 'valor_planejado',
                               'valor_executado'],
                [mapa[item], perfil(chave), mes, descricao, valor, venc, status, pag, parc, tot, deb, fatura, comp,
                 valor if fatura else None, valor if fatura else None])
    for lid, cartao, chave, catc, desc, valor, mes, parc, tot in LANCAMENTOS_FICTICIOS:
        inserir('lancamento_agregado', lid, ['cartao_id', 'perfil_financeiro_id', 'categoria_id', 'categoria_cartao_id',
                                             'descricao', 'valor', 'data_compra', 'mes_fatura', 'numero_parcela',
                                             'total_parcelas'],
                [mapa[cartao], perfil(chave), mapa[203], mapa[catc] if catc else None, desc, valor, mes[:8] + '05', mes,
                 parc, tot])
    for lim_id, cartao, catc, limite, ativo in LIMITES_FICTICIOS:
        inserir('cartao_categoria_limite', lim_id, ['cartao_id', 'categoria_cartao_id', 'limite_mensal', 'ativo'],
                [mapa[cartao], mapa[catc], limite, ativo])
    return mapa


CONTAS_MES_ESPERADO = {
    # (perfil, mes): ids na ordem da tela (vencimento crescente), total, pago, valor exibido de cada conta
    ('PESSOAL', '2026-11'): {'despesas': [503, 502, 501], 'faturas': [510, 509], 'total': '4390.50', 'pago': '270.50',
                             'valores': {501: '2000.00', 502: '150.50', 503: '800.00', 509: '1320.00', 510: '120.00'}},
    ('PESSOAL', '2026-01'): {'despesas': [504, 505, 506], 'faturas': [512], 'total': '3330.50', 'pago': '650.50',
                             'valores': {504: '1900.00', 505: '780.00', 506: '150.50', 512: '500.00'}},
    ('EMPRESA', '2026-11'): {'despesas': [507], 'faturas': [511], 'total': '1450.00', 'pago': '0.00',
                             'valores': {507: '1200.00', 511: '250.00'}},
    ('PERFIL_B', '2026-11'): {'despesas': [508], 'faturas': [], 'total': '999.99', 'pago': '0.00',
                              'valores': {508: '999.99'}},
    ('PESSOAL', '2026-06'): {'despesas': [], 'faturas': [], 'total': '0.00', 'pago': '0.00', 'valores': {}},
}


# FIN-RECORRENCIA-1: cenario FICTICIO de geracao (ids logicos fixos, cluster local).
# Competencia de referencia: 2027-03 (gera ate 2027-04). Valores esperados nos testes.
CATEGORIAS_RECORRENCIA = [(951, 'Moradia R', '#2563eb'), (952, 'Assinaturas R', '#9333ea')]
CATEGORIAS_CARTAO_RECORRENCIA = [(961, 'Streaming CC', 'PESSOAL'), (962, 'Outros CC', 'PESSOAL'), (963, 'Legado CC', None)]
CARTOES_RECORRENCIA = [  # id, nome, perfil, dia_vencimento (None = sem config_agregador)
    (910, 'Cartao Teste', 'PESSOAL', 31),
    (911, 'Cartao Sem Config', 'PESSOAL', None),
    (930, 'Cartao B', 'PERFIL_B', 10),
]
LIMITES_RECORRENCIA = [  # id, cartao, categoria_cartao, limite, ativo, perfil
    (981, 910, 961, '500.00', True, 'PESSOAL'),
    (982, 910, 962, '300.00', False, 'PESSOAL'),   # inativo: fora do planejado
    (983, 910, 963, '200.00', True, None),         # perfil NULL: o Flask so soma limites do perfil
]
RECORRENCIAS = [  # id, nome, perfil, categoria, tipo_recorrencia, ancora, valor, meio, cartao, ativo, descricao
    (901, 'Aluguel 31', 'PESSOAL', 951, 'mensal', '2027-01-31', '1500.00', 'boleto', None, True, None),
    (902, 'Escola', 'PESSOAL', 951, 'mensal', '2026-12-10', '800.00', 'debito_automatico', None, True, 'Mensalidade escolar'),
    (903, 'IPVA', 'PESSOAL', 951, 'anual', '2026-03-15', '1200.00', 'boleto', None, True, None),
    (904, 'Academia', 'PESSOAL', 951, 'mensal', '2027-01-05', '100.00', 'pix', None, False, None),
    (906, 'Streaming', 'PESSOAL', 952, 'mensal', '2027-01-31', '39.90', 'cartao', 910, True, None),
    (907, 'Bissexto', 'PESSOAL', 951, 'mensal', '2028-01-31', '10.00', 'boleto', None, True, None),
    (908, 'Feira semanal', 'PESSOAL', 951, 'semanal', '2027-01-04', '50.00', 'pix', None, True, None),
    (909, 'Legado sem perfil', None, 951, 'mensal', '2027-02-12', '60.00', 'boleto', None, True, None),
    (920, 'Valido B', 'PERFIL_B', 951, 'mensal', '2027-03-05', '70.00', 'boleto', None, True, None),
    (921, 'Sem valor B', 'PERFIL_B', 951, 'mensal', '2027-03-01', None, 'boleto', None, True, None),
    (922, 'Cartao sem categoria B', 'PERFIL_B', None, 'mensal', '2027-03-02', '20.00', 'cartao', 930, True, None),
    (940, 'Aluguel sala', 'EMPRESA', 951, 'mensal', '2027-03-10', '300.00', 'boleto', None, True, None),
]
# Registros ja gravados "pelo Flask" antes do novo motor.
CONTAS_PREEXISTENTES = [  # id, item, perfil, mes_ref, venc, valor, status, data_pag, debito
    (960, 902, 'PESSOAL', '2027-01-01', '2027-01-10', '800.00', 'Pendente', None, True),
    (961, 902, 'PESSOAL', '2027-02-01', '2027-02-15', '800.00', 'Pago', '2027-02-15', True),  # vencimento editado
]
LANCAMENTOS_PREEXISTENTES = [  # id, item, cartao, perfil, categoria, cat_cartao, data_compra, mes_fatura (sem compra_id: legado)
    (970, 906, 910, 'PESSOAL', 952, 961, '2027-01-31', '2027-01-01'),
]


def semear_recorrencias(cur):
    """Cenario do FIN-RECORRENCIA-1 (exige semear_perfis; sem semear_contas)."""
    def perfil(chave):
        return PERFIS[chave]['id'] if chave else None

    cur.execute("select id from public.conta_bancaria where nome = 'Conta Pessoal (A)'")
    conta_bancaria = cur.fetchone()[0]
    for cid, nome, cor in CATEGORIAS_RECORRENCIA:
        cur.execute('insert into public.categoria (id, nome, cor, ativo, sistemica, bloquear_edicao, bloquear_exclusao) '
                    'values (%s, %s, %s, true, false, false, false)', (cid, nome, cor))
    for cid, nome, chave in CATEGORIAS_CARTAO_RECORRENCIA:
        cur.execute('insert into public.categoria_cartao (id, nome, ativo, perfil_financeiro_id) values (%s, %s, true, %s)',
                    (cid, nome, perfil(chave)))
    cur.execute('insert into public.categoria_cartao_despesa (categoria_cartao_id, categoria_id, ativo, perfil_financeiro_id) '
                'values (961, 952, true, %s)', (perfil('PESSOAL'),))
    for iid, nome, chave, dia in CARTOES_RECORRENCIA:
        cur.execute("insert into public.item_despesa (id, nome, tipo, perfil_financeiro_id, categoria_id, ativo, recorrente) "
                    "values (%s, %s, 'Agregador', %s, 951, true, false)", (iid, nome, perfil(chave)))
        if dia:
            cur.execute('insert into public.config_agregador (item_despesa_id, dia_fechamento, dia_vencimento) '
                        'values (%s, 25, %s)', (iid, dia))
    for lid, cartao, catc, limite, ativo, chave in LIMITES_RECORRENCIA:
        cur.execute('insert into public.cartao_categoria_limite (id, cartao_id, categoria_cartao_id, limite_mensal, ativo, '
                    'perfil_financeiro_id) values (%s, %s, %s, %s, %s, %s)', (lid, cartao, catc, limite, ativo, perfil(chave)))
    for iid, nome, chave, cat, tipo, ancora, valor, meio, cartao, ativo, descricao in RECORRENCIAS:
        cur.execute("insert into public.item_despesa (id, nome, tipo, perfil_financeiro_id, categoria_id, ativo, recorrente, "
                    "tipo_recorrencia, data_vencimento, valor, meio_pagamento, cartao_id, conta_bancaria_id, descricao) "
                    "values (%s, %s, 'Simples', %s, %s, %s, true, %s, %s, %s, %s, %s, %s, %s)",
                    (iid, nome, perfil(chave), cat, ativo, tipo, ancora, valor, meio, cartao,
                     conta_bancaria if meio == 'debito_automatico' else None, descricao))
    for cid, item, chave, mes, venc, valor, status, pag, debito in CONTAS_PREEXISTENTES:
        cur.execute("insert into public.conta (id, item_despesa_id, perfil_financeiro_id, mes_referencia, descricao, valor, "
                    "data_vencimento, status_pagamento, data_pagamento, debito_automatico, conta_bancaria_id, observacoes, "
                    "is_fatura_cartao, estouro_orcamento, status_fatura) "
                    "values (%s, %s, %s, %s, 'Escola', %s, %s, %s, %s, %s, %s, 'Mensalidade escolar', false, false, 'ABERTA')",
                    (cid, item, perfil(chave), mes, valor, venc, status, pag, debito, conta_bancaria))
    for lid, item, cartao, chave, cat, catc, compra, mes in LANCAMENTOS_PREEXISTENTES:
        cur.execute("insert into public.lancamento_agregado (id, item_despesa_id, cartao_id, perfil_financeiro_id, categoria_id, "
                    "categoria_cartao_id, descricao, valor, data_compra, mes_fatura, numero_parcela, total_parcelas, "
                    "observacoes, is_recorrente, is_importado) "
                    "values (%s, %s, %s, %s, %s, %s, 'Streaming', 39.90, %s, %s, 1, 1, '', true, false)",
                    (lid, item, cartao, perfil(chave), cat, catc, compra, mes))


# FIN-RECORRENCIA-1 (E2E): recorrencia e cartao do "Perfil B" e recorrencia da Empresa
# (A e so LEITOR). Datas em 2027, longe dos meses usados pelos outros cenarios E2E.
RECORRENCIAS_E2E = [  # id, nome, perfil, ancora, valor
    (451, 'Mensalidade B', 'PERFIL_B', '2027-01-31', '120.00'),
    (453, 'Aluguel sala', 'EMPRESA', '2027-05-15', '900.00'),
    (454, 'Seguro 2028', 'PESSOAL', '2028-01-10', '10.00'),  # Pessoal segue no gerador Flask (T1)
]
# FIN-RECORRENCIA-T1: so o Perfil B e atribuido ao novo motor; os demais ficam no padrao (Flask).
GERADOR_NOVO_E2E = ['PERFIL_B']
CARTAO_E2E = (452, 'Cartao B', 'PERFIL_B', 31)


def semear_recorrencia_e2e(cur, categoria_id=201):
    for iid, nome, chave, ancora, valor in RECORRENCIAS_E2E:
        cur.execute("insert into public.item_despesa (id, nome, tipo, perfil_financeiro_id, categoria_id, ativo, recorrente, "
                    "tipo_recorrencia, data_vencimento, valor, meio_pagamento) "
                    "values (%s, %s, 'Simples', %s, %s, true, true, 'mensal', %s, %s, 'boleto')",
                    (iid, nome, PERFIS[chave]['id'], categoria_id, ancora, valor))
    iid, nome, chave, dia = CARTAO_E2E
    cur.execute("insert into public.item_despesa (id, nome, tipo, perfil_financeiro_id, categoria_id, ativo, recorrente) "
                "values (%s, %s, 'Agregador', %s, %s, true, false)", (iid, nome, PERFIS[chave]['id'], categoria_id))
    cur.execute('insert into public.config_agregador (item_despesa_id, dia_fechamento, dia_vencimento) values (%s, 25, %s)',
                (iid, dia))
    for chave in GERADOR_NOVO_E2E:
        cur.execute("select financeiro.definir_gerador_recorrencia(%s, 'NOVO', 'administrador de teste', 'cenario E2E')",
                    (PERFIS[chave]['id'],))


# FIN-CARTOES-RECORRENCIA-PENDENCIA-1 (E2E): compra recorrente FICTICIA no Cartao B do "Perfil B" (novo motor), a
# partir de 2033 (nenhum outro cenario usa esses meses; antes da ancora ela nao entra no plano).
PENDENCIA_E2E = (456, 'Streaming B', 'PERFIL_B', '2033-01-10', '25.00')


def semear_pendencia_e2e(cur, categoria_id=201):
    iid, nome, chave, ancora, valor = PENDENCIA_E2E
    cur.execute("insert into public.item_despesa (id, nome, tipo, perfil_financeiro_id, categoria_id, ativo, recorrente, "
                "tipo_recorrencia, data_vencimento, valor, meio_pagamento, cartao_id) "
                "values (%s, %s, 'Simples', %s, %s, true, true, 'mensal', %s, %s, 'cartao', %s)",
                (iid, nome, PERFIS[chave]['id'], categoria_id, ancora, valor, CARTAO_E2E[0]))


# FIN-RECEITAS-1 (E2E): receitas FICTICIAS de 11/2026 (previsoes; um recebimento parcial com movimento).
RECEITAS_E2E = [  # nome, tipo, perfil, recorrente, valor_base, dia, valor previsto 11/2026
    ('Salário (A)', 'SALARIO_FIXO', 'PESSOAL', True, '5000.00', 5, '5000.00'),
    ('Freelas', 'RENDA_EXTRA', 'PESSOAL', False, None, 20, '800.00'),
    ('Consultoria', 'RENDA_EXTRA', 'EMPRESA', False, None, 10, '3000.00'),
    ('Freela B', 'RENDA_EXTRA', 'PERFIL_B', False, None, 12, '700.00'),
]


def semear_receitas_e2e(cur):
    cur.execute("select id from public.conta_bancaria where nome = 'Conta Pessoal (A)'")
    conta = cur.fetchone()[0]
    for nome, tipo, chave, recorrente, base, dia, previsto in RECEITAS_E2E:
        perfil = PERFIS[chave]['id']
        cur.execute('insert into public.item_receita (perfil_financeiro_id, nome, tipo, descricao, ativo, valor_base_mensal, '
                    "dia_previsto_pagamento, recorrente) values (%s, %s, %s, '', true, %s, %s, %s) returning id",
                    (perfil, nome, tipo, base, dia, recorrente))
        item = cur.fetchone()[0]
        cur.execute("insert into public.receita_orcamento (perfil_financeiro_id, item_receita_id, mes_referencia, valor_esperado, "
                    "periodicidade) values (%s, %s, '2026-11-01', %s, %s)",
                    (perfil, item, previsto, 'MENSAL_FIXA' if recorrente else 'UNICA'))
        if nome == 'Salário (A)':  # recebimento parcial ja registrado (com movimento), como o Flask faz
            cur.execute("insert into public.receita_realizada (perfil_financeiro_id, item_receita_id, data_recebimento, "
                        "valor_recebido, mes_referencia, conta_bancaria_id) values (%s, %s, '2026-11-05', 2000, "
                        "'2026-11-01', %s) returning id", (perfil, item, conta))
            realizada = cur.fetchone()[0]
            cur.execute("insert into public.movimento_financeiro (conta_bancaria_id, tipo, valor, descricao, data_movimento, "
                        "receita_realizada_id, origem) values (%s, 'CREDITO', 2000, 'Recebimento', '2026-11-05', %s, 'RECEITA')",
                        (conta, realizada))


# FIN-CARTOES-1 (E2E): cartao FICTICIO INATIVO do "Perfil B" (cadastro: final do numero). Um cartao ativo
# entraria na geracao de faturas dos outros cenarios; cartoes.spec.mjs cria o seu e o inativa no fim.
CARTAO_INATIVO_E2E = (455, 'Cartao Antigo', 'PERFIL_B', 25, 10)  # id, nome, perfil, fechamento, vencimento
CATEGORIAS_CARTAO_E2E_B = [(340, 'Mercado B'), (341, 'Viagem B')]


def semear_cartoes_e2e(cur, categoria_id=203):
    iid, nome, chave, fechamento, vencimento = CARTAO_INATIVO_E2E
    cur.execute("insert into public.item_despesa (id, nome, tipo, perfil_financeiro_id, categoria_id, ativo, recorrente) "
                "values (%s, %s, 'Agregador', %s, %s, false, false)", (iid, nome, PERFIS[chave]['id'], categoria_id))
    cur.execute('insert into public.config_agregador (item_despesa_id, dia_fechamento, dia_vencimento, numero_cartao) '
                "values (%s, %s, %s, '5555 6666 7777 8888')", (iid, fechamento, vencimento))
    # FIN-FIDELIDADE-CARTOES-1: Categorias do Cartao do Perfil B (tela original de Cartoes); "Mercado B" classifica as
    # compras da categoria de despesa Moradia (201) quando vinculada ao cartao.
    for cid, nome_cc in CATEGORIAS_CARTAO_E2E_B:
        cur.execute('insert into public.categoria_cartao (id, nome, ativo, perfil_financeiro_id, cor, icone) '
                    "values (%s, %s, true, %s, '#16a34a', 'shopping-cart')", (cid, nome_cc, PERFIS['PERFIL_B']['id']))
    cur.execute('insert into public.categoria_cartao_despesa (categoria_cartao_id, categoria_id, ativo, perfil_financeiro_id) '
                'values (%s, 201, true, %s)', (CATEGORIAS_CARTAO_E2E_B[0][0], PERFIS['PERFIL_B']['id']))
    # Importar Cartao: palavras-chave de categoria (globais, como no Flask) para a sugestao das linhas do arquivo.
    cur.execute("insert into public.categoria_palavra_chave (categoria_id, palavra, ativo) values (201, 'padaria', true), "
                "(202, 'farmacia', true)")


# FIN-FIDELIDADE-CONTRATOS-1 (E2E, so leitura): financiamento FICTICIO do "Perfil B" com 3 parcelas (1 paga).
FINANCIAMENTO_E2E_B = 'Financiamento E2E (ficticio)'


def semear_financiamento_e2e(cur):
    perfil = PERFIS['PERFIL_B']['id']
    cur.execute("insert into public.financiamento (perfil_financeiro_id, nome, produto, sistema_amortizacao, valor_financiado, "
                "prazo_total_meses, prazo_remanescente_meses, taxa_juros_nominal_anual, taxa_juros_mensal, data_contrato, "
                "data_primeira_parcela, seguro_tipo, valor_seguro_mensal, ativo) values (%s, %s, 'Imovel ficticio', 'SAC', "
                "3000, 3, 2, 12, 0.009489, '2033-01-10', '2033-02-10', 'fixo', 10, true) returning id",
                (perfil, FINANCIAMENTO_E2E_B))
    financiamento = cur.fetchone()[0]
    for numero, status, saldo in ((1, 'pago', 2000), (2, 'pendente', 1000), (3, 'pendente', 0)):
        cur.execute("insert into public.financiamento_parcela (perfil_financeiro_id, financiamento_id, numero_parcela, "
                    "data_vencimento, valor_amortizacao, valor_juros, valor_seguro, valor_taxa_adm, valor_subsidio, "
                    "valor_fgts_utilizado, valor_juros_mora, valor_multa, valor_atualizacao_monetaria, valor_iof_complementar, "
                    "valor_previsto_total, valor_pago, dif_apurada, saldo_devedor_apos_pagamento, status) "
                    "values (%s, %s, %s, %s, 1000, %s, 10, 0, 0, 0, 0, 0, 0, 0, %s, %s, 0, %s, %s)",
                    (perfil, financiamento, numero, f'2033-0{numero + 1}-10', 28.47 / numero, 1010 + 28.47 / numero,
                     1038.47 if status == 'pago' else 0, saldo, status))
    # FIN-CONTRATOS-2 (contratos_pagamento.spec.mjs): como o Flask cria (1 parcela = 1 despesa do item 'Financiamento'),
    # as despesas das parcelas, ligadas por financiamento_parcela_id; a da parcela 1 ja paga.
    cur.execute("insert into public.item_despesa (perfil_financeiro_id, nome, tipo, ativo, recorrente, categoria_id) "
                "values (%s, %s, 'Financiamento', true, false, 201) returning id", (perfil, FINANCIAMENTO_E2E_B))
    item = cur.fetchone()[0]
    cur.execute('update public.financiamento set item_despesa_id = %s where id = %s', (item, financiamento))
    cur.execute('select id, numero_parcela, valor_previsto_total, data_vencimento, status from public.financiamento_parcela '
                'where financiamento_id = %s order by numero_parcela', (financiamento,))
    for pid, numero, valor, vencimento, status in cur.fetchall():
        cur.execute("insert into public.conta (perfil_financeiro_id, item_despesa_id, mes_referencia, descricao, valor, "
                    "data_vencimento, status_pagamento, debito_automatico, is_fatura_cartao, estouro_orcamento, status_fatura, "
                    "financiamento_parcela_id) values (%s, %s, date_trunc('month', %s::date), %s, %s, %s, %s, false, false, false, "
                    "'ABERTA', %s) returning id",
                    (perfil, item, vencimento, f'{FINANCIAMENTO_E2E_B} - parcela {numero}/3', valor, vencimento,
                     'Pago' if status == 'pago' else 'Pendente', pid))
        cur.execute('update public.financiamento_parcela set conta_id = %s where id = %s', (cur.fetchone()[0], pid))
    # FIN-FINANCIAMENTOS-MOTOR-1 (financiamentos_motor.spec.mjs): TR ficticia de 2034-2035 para o motor SAC/TR.
    cur.execute("insert into public.indice_tr_mensal (ano, mes, competencia, valor_decimal, fonte) "
                "select extract(year from d)::int, extract(month from d)::int, to_char(d, 'YYYY-MM'), 0.0010, 'E2E' "
                "from generate_series('2034-01-01'::date, '2035-12-01'::date, interval '1 month') d on conflict do nothing")



# FIN-FIDELIDADE-PATRIMONIO-1 (patrimonio_tela.spec.mjs): caixinhas e transferencia FICTICIAS do Perfil B e bens
# FICTICIOS do perfil Empresa (o usuario A e LEITOR nele). So leitura na tela.
PATRIMONIO_E2E_B = ('Reserva E2E (ficticia)', 'Viagem E2E (ficticia)')
BENS_E2E_EMPRESA = ('Notebook E2E (ficticio)', 'Cadeira E2E (ficticia)')


def semear_patrimonio_e2e(cur):
    perfil = PERFIS['PERFIL_B']['id']
    ids = []
    for nome, saldo in zip(PATRIMONIO_E2E_B, (1500, 300)):
        cur.execute("insert into public.conta_patrimonio (perfil_financeiro_id, nome, tipo, saldo_inicial, saldo_atual, meta, cor, "
                    "ativo, criado_em) values (%s, %s, 'Reserva', %s, %s, 5000, '#28a745', true, now()) returning id",
                    (perfil, nome, saldo, saldo))
        ids.append(cur.fetchone()[0])
    cur.execute("insert into public.transferencia (perfil_financeiro_id, conta_origem_id, conta_destino_id, valor, "
                "data_transferencia, descricao, criado_em) values (%s, %s, %s, 200, '2033-01-15', 'Transferencia E2E (ficticia)', now())",
                (perfil, ids[0], ids[1]))
    for nome, valor, status_doc, imagem in ((BENS_E2E_EMPRESA[0], 4200, 'PENDENTE', 'Patrimonio_notebook.jpg'),
                                            (BENS_E2E_EMPRESA[1], 900, 'NAO_APLICAVEL', None)):
        cur.execute("insert into public.bem_patrimonial (perfil_financeiro_id, nome, categoria, valor_aquisicao, data_aquisicao, "
                    "status, status_documental, imagem_arquivo, created_at, updated_at) "
                    "values (%s, %s, 'Equipamentos', %s, '2033-02-01', 'ATIVO', %s, %s, now(), now())",
                    (PERFIS['EMPRESA']['id'], nome, valor, status_doc, imagem))


# FIN-FIDELIDADE-DOCUMENTOS-1 (documentos_fiscais_tela.spec.mjs): categoria IR e comprovantes FICTICIOS do Perfil B.
# As categorias IR iniciais o Flask cria na leitura; o novo aplicativo so le, entao o cluster local recebe uma.
COMPROVANTES_E2E_B = ('Clinica E2E (ficticia)', 'Escola E2E (ficticia)')
DOCUMENTO_EMPRESA_E2E = 'Junta Comercial E2E (ficticia)'
ARQUIVO_E2E_B = 'Recibo E2E (ficticio) - conteudo de teste'.encode()


def semear_documentos_fiscais_e2e(cur):
    perfil = PERFIS['PERFIL_B']['id']
    cur.execute("insert into public.ir_categoria (nome, descricao, dedutivel, ativo, ordem, tipo_contexto, natureza, created_at, "
                "updated_at) values ('Saude E2E (ficticia)', 'Categoria ficticia', true, true, 10, 'PESSOAL', 'DEDUCAO_IRPF', now(), now()) "
                "returning id")
    categoria_ir = cur.fetchone()[0]
    for n, (nome, valor, status) in enumerate(zip(COMPROVANTES_E2E_B, (450.3, 980), ('PENDENTE_REVISAO', 'VALIDADO')), start=1):
        cur.execute("insert into public.ir_comprovante (perfil_financeiro_id, ano_calendario, data_documento, prestador_nome, valor, "
                    "categoria_ir_id, dedutivel, status, hash_arquivo, created_at, updated_at) "
                    "values (%s, extract(year from current_date)::int, current_date - %s, %s, %s, %s, true, %s, %s, now(), now()) "
                    "returning id", (perfil, n, nome, valor, categoria_ir, status, f'{n:064d}'))
        if n == 1:  # "Abrir arquivo" (documentos_fiscais_tela.spec.mjs): texto ficticio, aberto como blob numa nova aba
            cur.execute("insert into public.ir_comprovante_arquivo (comprovante_id, nome_arquivo, mime_type, tamanho_bytes, "
                        "hash_arquivo, conteudo, created_at) values (%s, 'recibo-ficticio.txt', 'text/plain', %s, %s, %s, now())",
                        (cur.fetchone()[0], len(ARQUIVO_E2E_B), 'c' * 64, ARQUIVO_E2E_B))
    # Documentos da Empresa: um documento FICTICIO do perfil Empresa com metadados empresariais (usuario A e LEITOR nele).
    cur.execute("insert into public.ir_comprovante (perfil_financeiro_id, ano_calendario, data_documento, prestador_nome, valor, "
                "status, hash_arquivo, created_at, updated_at) values (%s, extract(year from current_date)::int, current_date, "
                "%s, 0, 'VALIDADO', %s, now(), now()) returning id", (PERFIS['EMPRESA']['id'], DOCUMENTO_EMPRESA_E2E, 'e' * 64))
    documento = cur.fetchone()[0]
    cur.execute("insert into public.documento_empresarial_metadata (comprovante_id, perfil_financeiro_id, tipo_documental, "
                "categoria_documental, data_validade, status_documental, obrigatorio, renovavel, created_at, updated_at) values "
                "(%s, %s, 'DOCUMENTO_SOCIETARIO', 'CONTRATO_SOCIAL', null, 'ATIVO', true, false, now(), now())",
                (documento, PERFIS['EMPRESA']['id']))


# FIN-FIDELIDADE-PATRIMONIO-1 (mobilidade_tela.spec.mjs): veiculo, projecoes, regra de manutencao, assinatura e caminho
# de transporte por app FICTICIOS do Perfil B. So leitura na tela.
VEICULO_E2E_B = 'Carro E2E (ficticio)'
CAMINHO_APP_E2E_B = 'App E2E (ficticio)'


def semear_mobilidade_e2e(cur):
    perfil = PERFIS['PERFIL_B']['id']
    # FIN-MOBILIDADE-2: as categorias sistemicas MOB_* como o Flask as cria (o novo aplicativo so as procura).
    from backend.services.categoria_default import CATEGORIAS_SISTEMICAS_MOBILIDADE
    for codigo, d in CATEGORIAS_SISTEMICAS_MOBILIDADE.items():
        cur.execute("insert into public.categoria (nome, descricao, cor, icone, ativo, sistemica, codigo_sistema, modulo_origem, "
                    "bloquear_edicao, bloquear_exclusao) values (%s, %s, %s, %s, true, true, %s, 'mobilidade', true, true)",
                    (d['nome'], d.get('descricao'), d.get('cor'), d.get('icone'), codigo))
    cur.execute("select id from public.categoria order by id limit 1")
    categoria = cur.fetchone()[0]
    cur.execute("insert into public.veiculo (perfil_financeiro_id, nome, tipo, combustivel, autonomia_km_l, status, data_inicio, "
                "combustivel_valor_mensal, preco_medio_combustivel, ipva_mes, ipva_valor, km_estimado_acumulado, criado_em, "
                "atualizado_em) values (%s, %s, 'Carro', 'Gasolina', 12, 'ATIVO', current_date, 480, 6, 3, 1200, 5000, now(), now()) "
                "returning id", (perfil, VEICULO_E2E_B))
    veiculo = cur.fetchone()[0]
    for meses, evento, valor in ((0, 'COMBUSTIVEL', 480), (1, 'COMBUSTIVEL', 480), (2, 'IPVA', 1200)):
        cur.execute("insert into public.despesa_prevista (perfil_financeiro_id, origem_tipo, origem_id, categoria_id, data_prevista, "
                    "data_original_prevista, data_atual_prevista, valor_previsto, status, metadata, criado_em, atualizado_em) "
                    "select %s, 'VEICULO', %s, %s, d, d, d, %s, 'PREVISTA', %s, now(), now() "
                    "from (select (date_trunc('month', current_date) + make_interval(months => %s))::date d) x",
                    (perfil, veiculo, categoria, valor, json.dumps({'tipo_evento': evento}), meses))
    cur.execute("insert into public.veiculo_regra_manutencao_km (perfil_financeiro_id, veiculo_id, tipo_evento, intervalo_km, "
                "custo_estimado, categoria_id, ativo, criado_em, atualizado_em) values (%s, %s, 'TROCA_OLEO', 10000, 300, %s, true, "
                "now(), now())", (perfil, veiculo, categoria))
    cur.execute("insert into public.mobilidade_assinatura (perfil_financeiro_id, nome, valor_mensal, status, created_at, updated_at) "
                "values (%s, 'Assinatura E2E (ficticia)', 1300, 'ATIVO', now(), now())", (perfil,))
    cur.execute("insert into public.despesa_prevista (perfil_financeiro_id, origem_tipo, origem_id, categoria_id, data_prevista, "
                "data_original_prevista, data_atual_prevista, valor_previsto, status, metadata, criado_em, atualizado_em) "
                "select %s, 'TRANSPORTE_APP', 1, %s, d, d, d, 750, 'PREVISTA', %s, now(), now() "
                "from (select date_trunc('month', current_date)::date d) x",
                (perfil, categoria, json.dumps({'tipo_evento': 'TRANSPORTE_APP', 'caminho': {
                    'nome': CAMINHO_APP_E2E_B, 'km_mensal_estimado': 300, 'preco_medio_por_km': 2.5},
                    'calculo': {'valor_mensal': 750}})))
