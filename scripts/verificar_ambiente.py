"""
FIN-TRANSFERENCIA-AMBIENTE-1 — verificacao do ambiente de desenvolvimento (Windows), so leitura.

Confere ferramentas, dependencias, arquivos locais de configuracao (so os NOMES das variaveis), pastas necessarias e o
estado do Git. Com --rede, consulta tambem o Supabase de teste (so leitura: migrations aplicadas e pendentes).

Nao imprime valores de variaveis, senhas, chaves nem a URL do banco. Nao cria, altera nem apaga nada: pode ser
executado quantas vezes for preciso. Saida: 0 sem FALTA; 1 com alguma FALTA (AVISO nao reprova).

Uso (na raiz do projeto):
    venv\\Scripts\\python.exe scripts\\verificar_ambiente.py
    venv\\Scripts\\python.exe scripts\\verificar_ambiente.py --rede
"""
import argparse
import importlib.metadata as md
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

# Variaveis obrigatorias por arquivo local (fora do Git). So os nomes sao conferidos.
ARQUIVOS_ENV = {
    '.env.local': ['SECRET_KEY', 'DATABASE_URL'],
    '.env.staging': ['DATABASE_URL'],
    '.env.e2e-real': ['CF_EMAIL_A', 'CF_SENHA_A', 'CF_EMAIL_B', 'CF_SENHA_B'],
}
NODE_MINIMO = 22
RESULTADOS = []


def registrar(nivel, item, detalhe=''):
    RESULTADOS.append((nivel, item))
    print(f'{nivel:<6}| {item}' + (f' | {detalhe}' if detalhe else ''), flush=True)


def comando(*args, cwd=None):
    """Saida (stdout+stderr) de um comando, ou None se nao existir. Nunca usa shell."""
    exe = shutil.which(args[0])
    if not exe:
        return None
    try:
        r = subprocess.run([exe, *args[1:]], cwd=cwd or RAIZ, capture_output=True, text=True, timeout=120,
                           encoding='utf-8', errors='replace')
    except (OSError, subprocess.TimeoutExpired):
        return None
    return (r.stdout + r.stderr).strip()


def chaves_do_env(caminho):
    """Nomes das variaveis definidas (com valor nao vazio) num arquivo .env. Os valores nunca saem daqui."""
    nomes = set()
    for linha in Path(caminho).read_text(encoding='utf-8-sig').splitlines():
        m = re.match(r'\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$', linha)
        if m and not linha.lstrip().startswith('#') and m.group(2).strip().strip('"\''):
            nomes.add(m.group(1))
    return nomes


def requisitos_fixados(arquivo):
    """Pacotes com versao exata (==) no requirements."""
    fixados = {}
    for linha in (RAIZ / arquivo).read_text(encoding='utf-8').splitlines():
        m = re.match(r'\s*([A-Za-z0-9_.\-]+)==([^\s#]+)', linha)
        if m:
            fixados[m.group(1)] = m.group(2)
    return fixados


def verificar_python():
    esperado = (RAIZ / 'runtime.txt').read_text(encoding='utf-8').strip().replace('python-', '')
    atual = '.'.join(map(str, sys.version_info[:3]))
    registrar('OK' if atual == esperado else 'AVISO', f'Python {atual}', f'runtime.txt pede {esperado}')
    no_venv = Path(sys.prefix).resolve() == (RAIZ / 'venv').resolve()
    registrar('OK' if no_venv else 'AVISO', 'executando pelo venv do projeto', '' if no_venv else 'use venv\\Scripts\\python.exe')
    faltam, diferentes = [], []
    for pacote, versao in requisitos_fixados('requirements.txt').items():
        try:
            instalada = md.version(pacote)
        except md.PackageNotFoundError:
            faltam.append(pacote)
            continue
        if instalada != versao:
            diferentes.append(f'{pacote} {instalada} (pede {versao})')
    registrar('FALTA' if faltam else 'OK', 'pacotes do requirements.txt instalados', ', '.join(faltam))
    if diferentes:
        registrar('AVISO', 'versoes diferentes das fixadas', '; '.join(diferentes))


def verificar_node():
    versao = comando('node', '--version')
    if not versao:
        registrar('FALTA', 'Node.js', 'nao encontrado no PATH')
        return
    principal = int(re.sub(r'\D', '', versao.split('.')[0]) or 0)
    registrar('OK' if principal >= NODE_MINIMO else 'FALTA', f'Node.js {versao}', f'minimo {NODE_MINIMO}')
    registrar('OK' if comando('npm', '--version') else 'FALTA', f"npm {comando('npm', '--version') or ''}".strip())
    for pasta, pacote in (('web', '@supabase/supabase-js'), ('web', 'pdfjs-dist'), ('web', 'wrangler'), ('.', '@playwright/test')):
        declarado = json.loads((RAIZ / pasta / 'package.json').read_text(encoding='utf-8'))
        pedido = {**declarado.get('dependencies', {}), **declarado.get('devDependencies', {})}.get(pacote, '')
        instalado = RAIZ / pasta / 'node_modules' / pacote / 'package.json'
        if not instalado.exists():
            registrar('FALTA', f'{pasta}/node_modules: {pacote}', f'rodar npm ci em {pasta}')
            continue
        versao = json.loads(instalado.read_text(encoding='utf-8'))['version']
        exata = not pedido or pedido.lstrip('^~') == versao or pedido.startswith(('^', '~'))
        registrar('OK' if exata else 'AVISO', f'{pasta}/node_modules: {pacote} {versao}', f'package.json: {pedido}')
    navegadores = Path(os.environ.get('PLAYWRIGHT_BROWSERS_PATH') or Path(os.environ.get('LOCALAPPDATA', '')) / 'ms-playwright')
    chromium = sorted(navegadores.glob('chromium-*')) if navegadores.is_dir() else []
    registrar('OK' if chromium else 'FALTA', 'Chromium do Playwright', chromium[-1].name if chromium else 'rodar: npx playwright install chromium')


def verificar_bancos_locais():
    from tests.supabase_local import encontrar_pg_bin, encontrar_postgrest
    pg_bin = encontrar_pg_bin()
    if pg_bin:
        postgres = pg_bin / ('postgres.exe' if os.name == 'nt' else 'postgres')
        registrar('OK', 'PostgreSQL (initdb/pg_ctl) para os testes descartaveis', comando(str(postgres), '--version') or '')
    else:
        registrar('FALTA', 'PostgreSQL (initdb/pg_ctl)', 'instalar o PostgreSQL 18 ou definir CF_MVP_PG_BIN')
    postgrest = encontrar_postgrest()
    if postgrest:
        versao = comando(str(postgrest), '--version') or ''
        registrar('OK', 'PostgREST (POSTGREST_BIN)', versao.splitlines()[0] if versao else '')
        if pg_bin and str(pg_bin).lower() not in os.environ.get('PATH', '').lower():
            registrar('AVISO', 'bin do PostgreSQL fora do PATH', 'o PostgREST no Windows precisa da libpq.dll do PATH')
    else:
        registrar('AVISO', 'PostgREST ausente', 'E2E e testes REST sao pulados; definir POSTGREST_BIN (versao 16.5)')


def verificar_ferramentas():
    supabase = comando('supabase', '--version')
    registrar('OK' if supabase else 'FALTA', f"Supabase CLI {(supabase or '').splitlines()[0] if supabase else ''}".strip(),
              '' if supabase else 'necessaria para migrations e para a chave publica')
    vinculado = RAIZ / 'supabase' / '.temp' / 'linked-project.json'
    if vinculado.exists():
        ref = json.loads(vinculado.read_text(encoding='utf-8')).get('ref', '')
        teste = ref.startswith('fzjmge')
        registrar('OK' if teste else 'FALTA', 'projeto Supabase vinculado e o de teste', f'{ref[:6]}...' if ref else '')
    else:
        registrar('AVISO', 'projeto Supabase nao vinculado', 'supabase link --project-ref <ref-do-projeto-de-teste>')
    git = comando('git', '--version')
    registrar('OK' if git else 'FALTA', git or 'Git')
    for nome, uso in (('tesseract', 'OCR (opcional)'), ('pdftoppm', 'Poppler, OCR de PDF (opcional)')):
        registrar('OK' if shutil.which(nome) else 'AVISO', f'{nome}: {uso}', '' if shutil.which(nome) else 'ausente')


def verificar_configuracao():
    for arquivo, obrigatorias in ARQUIVOS_ENV.items():
        caminho = RAIZ / arquivo
        if not caminho.exists():
            registrar('FALTA', f'{arquivo}', 'copiar da maquina anterior por meio seguro (fora do Git)')
            continue
        ignorado = subprocess.run(['git', 'check-ignore', '-q', arquivo], cwd=RAIZ).returncode == 0
        registrar('OK' if ignorado else 'FALTA', f'{arquivo} ignorado pelo Git', '' if ignorado else 'NAO versionar este arquivo')
        faltam = [v for v in obrigatorias if v not in chaves_do_env(caminho)]
        registrar('FALTA' if faltam else 'OK', f'{arquivo}: variaveis obrigatorias definidas', ', '.join(faltam))
    data = RAIZ / 'data'
    registrar('OK' if data.is_dir() else 'FALTA', 'pasta data/', '' if data.is_dir() else 'criar vazia: a coleta do pytest precisa dela')
    banco = data / 'gastos.db'
    registrar('OK' if banco.exists() else 'AVISO', 'data/gastos.db (banco do Flask, so presenca; nao e aberto)',
              '' if banco.exists() else 'necessario so para usar o Flask com os dados locais')


def verificar_git():
    ramo = comando('git', 'branch', '--show-current') or ''
    registrar('OK' if ramo == 'main' else 'AVISO', f'branch atual: {ramo}')
    ultimo = comando('git', 'log', '-1', '--format=%h %s') or ''
    registrar('OK', 'ultimo commit', ultimo[:90])
    adiante = comando('git', 'rev-list', '--count', 'origin/main..HEAD')
    if adiante and adiante.isdigit():
        registrar('OK' if adiante == '0' else 'AVISO', f'commits locais fora do origin/main: {adiante}',
                  '' if adiante == '0' else 'enviar so com autorizacao (push)')
    rastreados = [l for l in (comando('git', 'status', '--porcelain', '--untracked-files=no') or '').splitlines() if l.strip()]
    registrar('OK' if not rastreados else 'AVISO', f'arquivos rastreados modificados: {len(rastreados)}')
    for pasta in ('supabase/migrations', 'supabase/reversao'):
        n = len(list((RAIZ / pasta).glob('*.sql')))
        registrar('OK' if n else 'FALTA', f'{pasta}: {n} arquivos .sql')


def verificar_supabase_teste():
    saida = comando(sys.executable, str(RAIZ / 'scripts' / 'supabase_migrations.py'), 'status')
    if saida is None:
        registrar('FALTA', 'consulta ao Supabase de teste', 'nao executou')
        return
    pendentes = re.search(r'Pendentes:\s*(.*)', saida)
    contagem = re.search(r'locais:\s*(\d+)\s*\|\s*aplicadas no remoto:\s*(\d+)', saida)
    if not (pendentes and contagem):
        registrar('FALTA', 'consulta ao Supabase de teste', 'sem resposta valida (conferir .env.staging e a rede)')
        return
    registrar('OK', f'Supabase de teste: {contagem.group(1)} locais, {contagem.group(2)} aplicadas', f'pendentes: {pendentes.group(1)}')


def main():
    parser = argparse.ArgumentParser(description='Verificacao do ambiente (so leitura).')
    parser.add_argument('--rede', action='store_true', help='tambem consulta o Supabase de teste (so leitura)')
    args = parser.parse_args()
    print(f'Projeto: {RAIZ.name}')
    for etapa in (verificar_python, verificar_node, verificar_bancos_locais, verificar_ferramentas, verificar_configuracao,
                  verificar_git):
        try:
            etapa()
        except Exception as exc:  # noqa: BLE001 (uma etapa com erro nao interrompe as outras)
            registrar('FALTA', etapa.__name__, f'{type(exc).__name__}')
    if args.rede:
        verificar_supabase_teste()
    faltas = [item for nivel, item in RESULTADOS if nivel == 'FALTA']
    avisos = sum(1 for nivel, _ in RESULTADOS if nivel == 'AVISO')
    print(f'\nResumo: {len(RESULTADOS) - len(faltas) - avisos} OK, {avisos} AVISO, {len(faltas)} FALTA')
    return 1 if faltas else 0


if __name__ == '__main__':
    sys.exit(main())
