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

    def preparar(self):
        """Shim do Supabase + tabelas do Flask protegidas + migrations de supabase/ + dados ficticios."""
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
VINCULOS = [  # (usuario, perfil, papel) — nada e vinculado automaticamente
    (USUARIO_A, 'PESSOAL', 'TITULAR'),
    (USUARIO_A, 'EMPRESA', 'LEITOR'),
    (USUARIO_A, 'INATIVO_A', 'TITULAR'),
    (USUARIO_B, 'PERFIL_B', 'TITULAR'),
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
    for usuario, chave, papel in VINCULOS:
        cur.execute('insert into financeiro.perfil_acesso (user_id, perfil_financeiro_id, papel) values (%s, %s, %s)',
                    (usuario['id'], PERFIS[chave]['id'], papel))
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


# MOBILE-CONTAS-1: contas do mes FICTICIAS (ids fixos). Valores esperados calculados a mao
# em CONTAS_MES_ESPERADO; os testes de equivalencia comparam tambem com o Flask.
def semear_contas(cur):
    p = {chave: perfil['id'] for chave, perfil in PERFIS.items()}
    cur.execute('update public.perfil_financeiro set avatar = upper(left(nome, 2))')  # evita o Flask completar o avatar
    for cid, nome, cor in ((201, 'Moradia', '#2563eb'), (202, 'Saude', '#16a34a'), (203, 'Cartoes', '#9333ea')):
        cur.execute('insert into public.categoria (id, nome, cor, ativo, sistemica, bloquear_edicao, bloquear_exclusao) '
                    'values (%s, %s, %s, true, false, false, false)', (cid, nome, cor))
    for cid, nome in ((301, 'Mercado'), (302, 'Restaurantes'), (303, 'Combustivel')):
        cur.execute('insert into public.categoria_cartao (id, nome, ativo) values (%s, %s, true)', (cid, nome))
    itens = [  # id, nome, tipo, perfil, categoria, recorrente, data_vencimento
        (401, 'Aluguel', 'Simples', p['PESSOAL'], 201, True, '2026-01-10'),
        (402, 'Internet', 'Simples', None, 201, False, '2026-01-20'),
        (403, 'Plano de saude', 'Simples', p['PESSOAL'], 202, False, '2026-01-15'),
        (404, 'Cartao Azul', 'Agregador', p['PESSOAL'], 203, False, None),
        (405, 'Cartao Verde', 'Agregador', None, 203, False, None),
        (406, 'Contador', 'Simples', p['EMPRESA'], 201, False, '2026-11-10'),
        (407, 'Cartao Empresa', 'Agregador', p['EMPRESA'], 203, False, None),
        (408, 'Aluguel B', 'Simples', p['PERFIL_B'], 201, False, '2026-11-08'),
    ]
    for iid, nome, tipo, perfil, cat, rec, venc in itens:
        cur.execute('insert into public.item_despesa (id, nome, tipo, perfil_financeiro_id, categoria_id, ativo, recorrente, '
                    "tipo_recorrencia, data_vencimento) values (%s, %s, %s, %s, %s, true, %s, 'mensal', %s)",
                    (iid, nome, tipo, perfil, cat, rec, venc))
    contas = [  # id, item, perfil, mes_ref, venc, valor, status, data_pag, parcela, total, debito, fatura, competencia
        (501, 401, p['PESSOAL'], '2026-11-01', '2026-12-05', '2000.00', 'Pendente', None, None, None, False, False, None),
        (502, 402, None, '2026-11-01', '2026-11-20', '150.50', 'Pago', '2026-11-19', None, None, False, False, None),
        (503, 403, p['PESSOAL'], '2026-11-01', '2026-11-15', '800.00', 'Pendente', None, 3, 12, True, False, None),
        (504, 401, p['PESSOAL'], '2026-01-01', '2026-01-10', '1900.00', 'Pendente', None, None, None, False, False, None),
        (505, 403, p['PESSOAL'], '2026-01-01', '2026-01-15', '780.00', 'Atrasado', None, None, None, False, False, None),
        (506, 402, None, '2026-01-01', '2026-01-20', '150.50', 'Pago', '2026-01-25', None, None, False, False, None),
        (507, 406, p['EMPRESA'], '2026-11-01', '2026-11-10', '1200.00', 'Pendente', None, None, None, False, False, None),
        (508, 408, p['PERFIL_B'], '2026-11-01', '2026-11-08', '999.99', 'Pendente', None, None, None, False, False, None),
        (509, 404, p['PESSOAL'], '2026-11-01', '2026-12-10', '0.00', 'Pendente', None, None, None, False, True, '2026-11-01'),
        (510, 405, None, '2026-11-01', '2026-11-25', '1.00', 'Pago', '2026-11-24', None, None, False, True, '2026-11-01'),
        (511, 407, p['EMPRESA'], '2026-11-01', '2026-12-01', '0.00', 'Pendente', None, None, None, False, True, '2026-11-01'),
        (512, 404, p['PESSOAL'], '2026-01-01', '2026-02-10', '0.00', 'Pago', '2026-02-09', None, None, False, True, '2026-01-01'),
    ]
    nomes_item = {i[0]: i[1] for i in itens}
    for (cid, item, perfil, mes, venc, valor, status, pag, parc, tot, deb, fatura, comp) in contas:
        if fatura:
            descricao = f'Fatura {nomes_item[item]} - {comp[5:7]}/{comp[:4]}'
        else:
            descricao = f'{nomes_item[item]} {mes[5:7]}/{mes[:4]}'
        cur.execute('insert into public.conta (id, item_despesa_id, perfil_financeiro_id, mes_referencia, descricao, valor, '
                    'data_vencimento, status_pagamento, data_pagamento, numero_parcela, total_parcelas, debito_automatico, '
                    'is_fatura_cartao, cartao_competencia, valor_planejado, valor_executado) '
                    'values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    (cid, item, perfil, mes, descricao, valor, venc, status, pag, parc, tot, deb, fatura, comp,
                     valor if fatura else None, valor if fatura else None))
    lancamentos = [  # id, cartao, perfil, categoria_cartao, descricao, valor, mes_fatura, parcela, total
        (601, 404, p['PESSOAL'], 301, 'Supermercado X', '300.00', '2026-11-01', 1, 1),
        (602, 404, p['PESSOAL'], 301, 'Supermercado Y', '150.00', '2026-11-01', 1, 1),
        (603, 404, p['PESSOAL'], 302, 'Restaurante Z', '420.00', '2026-11-01', 1, 1),
        (604, 404, p['PESSOAL'], 303, 'Posto', '100.00', '2026-11-01', 1, 1),
        (605, 404, p['PESSOAL'], None, 'Compra parcelada', '200.00', '2026-11-01', 2, 3),
        (606, 404, None, 301, 'Farmacia (legado)', '50.00', '2026-11-01', 1, 1),
        (607, 404, p['PESSOAL'], 301, 'Supermercado dezembro', '999.00', '2026-12-01', 1, 1),
        (608, 405, None, 302, 'Livraria', '80.00', '2026-11-01', 1, 1),
        (609, 405, None, None, 'Cinema', '40.00', '2026-11-01', 1, 1),
        (610, 407, p['EMPRESA'], None, 'Papelaria', '250.00', '2026-11-01', 1, 1),
        (611, 404, p['PESSOAL'], 301, 'Mercado janeiro', '500.00', '2026-01-01', 1, 1),
    ]
    for lid, cartao, perfil, catc, desc, valor, mes, parc, tot in lancamentos:
        cur.execute('insert into public.lancamento_agregado (id, cartao_id, perfil_financeiro_id, categoria_id, '
                    'categoria_cartao_id, descricao, valor, data_compra, mes_fatura, numero_parcela, total_parcelas) '
                    'values (%s,%s,%s,203,%s,%s,%s,%s,%s,%s,%s)',
                    (lid, cartao, perfil, catc, desc, valor, mes[:8] + '05', mes, parc, tot))
    limites = [  # cartao, categoria_cartao, limite, ativo
        (404, 301, '600.00', True),   # gasto 500 -> complemento 100
        (404, 302, '300.00', True),   # gasto 420 -> complemento 0
        (404, 303, '500.00', False),  # inativo: ignorado
        (405, 301, '200.00', True),   # fatura paga: o previsto nao vale
    ]
    for cartao, catc, limite, ativo in limites:
        cur.execute('insert into public.cartao_categoria_limite (cartao_id, categoria_cartao_id, limite_mensal, ativo) '
                    'values (%s, %s, %s, %s)', (cartao, catc, limite, ativo))


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
