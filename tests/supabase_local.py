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

    def preparar(self):
        """Shim do Supabase + migrations do repositorio + dados ficticios."""
        self.aplicar_shim()
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
        finally:
            conn.close()


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
