"""
TESTES-IMPACTO-1 — selecao de testes pelo impacto das alteracoes (docs/TESTES_IMPACTO_1.md).

Le as alteracoes do Git (ou uma lista de arquivos) e descobre:
- o que mudou: funcoes, metodos, classes e constantes Python (pelas linhas alteradas), funcoes SQL das
  migrations do Supabase, modulos JS, telas e arquivos de apoio dos testes;
- quem depende disso: funcoes do backend que referenciam o que mudou (por nome, ate --profundidade niveis),
  rotas HTTP dessas funcoes, funcoes SQL que chamam as alteradas, telas e specs do novo aplicativo;
- quais testes cobrem: testes que importam ou citam o modulo, um simbolo, uma rota, uma funcao SQL ou o
  arquivo alterado (inclusive os que leem o frontend como texto), mais a matriz curada abaixo, que cobre o
  que a analise estatica nao enxerga (protecoes financeiras e invariantes globais do esquema).

Mostra a lista e o motivo de cada teste ANTES de executar qualquer coisa. Sem --executar, nao roda nada.
Na duvida, amplia: arquivo alterado sem teste encontrado e arquivo central sao avisados, nunca ignorados.
Testes remotos (scripts/*_real.py, run_e2e_real.py) so sao listados, nunca executados.
Sem dependencias novas: biblioteca padrao + pytest e npm ja usados no projeto.

Uso (da raiz do repositorio, Windows):
    venv\\Scripts\\python.exe scripts\\testes_impacto.py                     # alteracoes locais x HEAD
    venv\\Scripts\\python.exe scripts\\testes_impacto.py --base origin/main  # tudo o que o ramo mudou
    venv\\Scripts\\python.exe scripts\\testes_impacto.py --arquivos backend/services/cartao_service.py
    venv\\Scripts\\python.exe scripts\\testes_impacto.py --executar          # roda e mede (pytest, web unit, E2E)
    venv\\Scripts\\python.exe scripts\\testes_impacto.py --executar --sem-e2e
O E2E local precisa de POSTGREST_BIN e dos binarios do PostgreSQL (como web/tests/e2e/run_e2e.py).
"""
import argparse
import ast
import fnmatch
import re
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Matriz curada (o que a analise estatica nao enxerga). Atualizar junto com docs/TESTES_IMPACTO_1.md.
# ---------------------------------------------------------------------------
PROTECOES_CARTAO = ['tests/test_fatura_integridade.py', 'tests/test_pagamento_trava.py',
                    'tests/test_supabase_fatura_unica.py', 'tests/test_fatura_unica_flask.py']
INVARIANTES_ESQUEMA = ['tests/test_sec_supabase_public.py', 'tests/test_supabase_mvp_rls.py']

# (padroes do arquivo alterado, regex no conteudo do arquivo ou None, testes, motivo)
REGRAS = [
    (['backend/services/cartao_service.py', 'backend/routes/cartoes.py', 'backend/services/trava_financeira.py',
      'backend/services/importacao_cartao*.py', 'backend/routes/despesas.py', 'backend/routes/recorrencias.py',
      'backend/routes/contas_bancarias.py'],
     None, PROTECOES_CARTAO, 'protecoes financeiras de cartao e fatura (fatura paga, pagamento, travas, unicidade)'),
    (['supabase/migrations/*.sql'], r'lancamento_agregado|is_fatura_cartao|movimento_financeiro',
     PROTECOES_CARTAO, 'migration mexe em compras, faturas ou movimentos: protecoes financeiras'),
    (['supabase/migrations/*.sql'], None, INVARIANTES_ESQUEMA,
     'invariantes globais do esquema (RLS, privilegios, exposicao a Data API)'),
    (['migrations/versions/*.py'], None, ['tests/test_alembic_*.py'], 'cadeia de migrations Alembic'),
]

# Regra permanente: NA DUVIDA SOBRE IMPACTO FINANCEIRO, AMPLIAR. Se o trecho alterado (linhas novas ou removidas)
# de codigo cita pagamento, estorno, conciliacao, consolidacao, saldo, baixa ou movimentacao, entram todas as
# protecoes financeiras e, se o novo aplicativo pode ser afetado, os E2E que mostram faturas, pagamentos e saldos.
AREAS_FINANCEIRAS = re.compile(r'pagament|pagar|\bpag[oa]s?\b|estorn|concilia|consolid|saldo|baixa|movimenta|movimento_'
                               r'|transferenc', re.I)
CODIGO = ['backend/*.py', 'supabase/migrations/*.sql', 'migrations/versions/*.py', 'web/src/*', 'frontend/static/js/*']
PROTECOES_FINANCEIRAS = PROTECOES_CARTAO + [
    'tests/test_pagamento_*.py', 'tests/test_estorno_*.py', 'tests/test_movimento_original_estorno.py',
    'tests/test_baixa_despesa_transacional.py', 'tests/test_core_saldo_*.py', 'tests/test_debito_automatico_baixa_status.py',
    'tests/test_meio_pagamento_debito_automatico.py']
E2E_FINANCEIROS = ['web/tests/e2e/contas.spec.mjs', 'web/tests/e2e/despesas.spec.mjs', 'web/tests/e2e/recorrencia.spec.mjs',
                   'web/tests/e2e/cartoes.spec.mjs', 'web/tests/e2e/fechamento.spec.mjs']

# Alterar estes arquivos pode afetar o projeto inteiro: avisar e avaliar o nivel 3 (suite completa).
CENTRAIS = ['backend/app.py', 'backend/config.py', 'backend/__init__.py', 'backend/models.py', 'tests/conftest.py',
            'pytest.ini', 'requirements*.txt', 'web/package.json', 'web/package-lock.json']
# Apoio dos testes com banco descartavel: todos os testes que sobem o cluster dependem dele.
APOIO_CLUSTER = ['tests/supabase_local.py']
# Infraestrutura do E2E: todos os specs dependem dela.
INFRA_E2E = ['web/tests/e2e/run_e2e.py', 'web/playwright.config.mjs', 'web/scripts/build.mjs', 'tests/supabase_local.py']
# Acessam recursos remotos: so listados (executar apenas com autorizacao).
REMOTOS = ['scripts/*_real.py', 'scripts/supabase_*.py', 'web/tests/e2e/run_e2e_real.py']
IGNORADOS = ['*.md', '*.png', '*.jpg', '*.webp', '*.svg', '*.pdf', '*.zip', '*.txt']

NOMES_GENERICOS = {'to_dict', 'get', 'query', 'validar', 'listar', 'criar', 'atualizar', 'excluir', 'main', 'run'}


def casa(caminho, padroes):
    return any(fnmatch.fnmatch(caminho, p) for p in padroes)


def git(*args):
    r = subprocess.run(['git', *args], cwd=RAIZ, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.returncode != 0:
        raise SystemExit(f'git {" ".join(args)} falhou: {r.stderr.strip()}')
    return r.stdout


AVISOS_ANALISE = []


def ler(caminho):
    try:  # utf-8-sig: varios modulos do backend comecam com BOM
        return (RAIZ / caminho).read_text(encoding='utf-8-sig', errors='replace')
    except OSError:
        return ''


# ---------------------------------------------------------------------------
# O que mudou
# ---------------------------------------------------------------------------

def alteracoes(base, arquivos):
    """{arquivo: linhas novas alteradas (set) ou None = arquivo inteiro (novo ou sem diff de linhas)}."""
    if arquivos:
        return {Path(a).as_posix(): None for a in arquivos}
    resultado = {}
    for caminho in git('diff', '--name-only', base).splitlines():
        resultado[caminho] = set()
    for caminho in git('ls-files', '--others', '--exclude-standard').splitlines():
        resultado[caminho] = None
    for caminho in [c for c, v in resultado.items() if v is not None]:
        linhas = set()
        diff = git('diff', '-U0', base, '--', caminho)
        for m in re.finditer(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@', diff, re.M):
            inicio, qtd = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
            linhas.update(range(inicio, inicio + max(qtd, 1)))
        REMOVIDO[caminho] = '\n'.join(x[1:] for x in diff.splitlines() if x.startswith('-') and not x.startswith('---'))
        resultado[caminho] = linhas or None
    return resultado


REMOVIDO = {}  # arquivo -> linhas removidas pelo diff (entram na regra financeira)


def trecho_alterado(arquivo, linhas):
    """Texto das linhas novas alteradas e das removidas (arquivo inteiro se novo ou sem diff de linhas)."""
    texto = ler(arquivo)
    if linhas is None:
        return texto
    todas = texto.splitlines()
    return '\n'.join(todas[n - 1] for n in sorted(linhas) if 0 < n <= len(todas)) + '\n' + REMOVIDO.get(arquivo, '')


def simbolos_python(caminho, linhas):
    """Funcoes, metodos, classes e nomes de nivel de modulo tocados pelas linhas alteradas."""
    try:
        arvore = ast.parse(ler(caminho))
    except SyntaxError as exc:
        AVISOS_ANALISE.append(f'{caminho}: analise de simbolos falhou ({exc.msg}); selecao ampliada ao modulo inteiro')
        return {'<modulo>'}
    tocado = (lambda n: True) if linhas is None else \
        (lambda n: any(n.lineno <= x <= (n.end_lineno or n.lineno) for x in linhas))
    nomes = set()
    for no in arvore.body:
        if not tocado(no):
            continue
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
            nomes.add(no.name)
        elif isinstance(no, ast.ClassDef):
            metodos = [m for m in no.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]
            nomes.update(m.name for m in metodos if tocado(m))
            # A classe inteira so conta se mudou fora dos metodos (cabecalho, colunas, atributos publicos) ou e
            # nova: mudar um metodo nao afeta quem usa os outros. Atributo privado (_cache) entra pelo proprio nome.
            cabecalho = ast.ClassDef(name=no.name, bases=[], keywords=[], body=[], decorator_list=[],
                                     lineno=no.lineno, end_lineno=no.body[0].lineno - 1 if no.body else no.lineno)
            corpo = [m for m in no.body if m not in metodos and (linhas is None or tocado(m))]
            privados = [_alvo_privado(m) for m in corpo]
            if linhas is None or tocado(cabecalho) or not all(privados):
                nomes.add(no.name)
            else:
                nomes.update(privados)  # vazio se so metodos mudaram
        elif isinstance(no, (ast.Assign, ast.AnnAssign)):
            alvos = no.targets if isinstance(no, ast.Assign) else [no.target]
            nomes.update(a.id for a in alvos if isinstance(a, ast.Name))
        else:
            nomes.add('<modulo>')  # import, configuracao: quem importa o modulo depende
    return nomes


def _alvo_privado(no):
    """Nome do atributo privado (_x) atribuido por `no`, ou None."""
    alvos = no.targets if isinstance(no, ast.Assign) else [no.target] if isinstance(no, ast.AnnAssign) else []
    nomes = [a.id for a in alvos if isinstance(a, ast.Name)]
    return nomes[0] if len(nomes) == 1 and len(alvos) == 1 and nomes[0].startswith('_') else None


def padrao_rota(url):
    """Regex do caminho inteiro da rota: parametros (<int:id>) casam um segmento qualquer, inclusive {id} de
    f-string; o caminho tem de terminar ali (aspas, ?, espaco) — '/x/<id>/pagar' nao casa '/x/' nem '/x/{id}'."""
    corpo = r'[^/\s]+'.join(re.escape(p) for p in re.split(r'<[^>]+>', url))
    if corpo.endswith('/'):
        corpo = corpo[:-1] + '/?'
    return corpo + r"""(?=['"?\s#)]|$)"""


RE_FUNCAO_SQL = re.compile(r'create\s+(?:or\s+replace\s+)?function\s+(?:(\w+)\.)?(\w+)\s*\(', re.I)


def blocos_sql():
    """[(funcao, corpo)] de todas as migrations do Supabase (a definicao mais recente vence na ordem)."""
    blocos = []
    for arquivo in sorted((RAIZ / 'supabase' / 'migrations').glob('*.sql')):
        texto = arquivo.read_text(encoding='utf-8', errors='replace')
        marcas = list(RE_FUNCAO_SQL.finditer(texto))
        for i, m in enumerate(marcas):
            fim = marcas[i + 1].start() if i + 1 < len(marcas) else len(texto)
            blocos.append((m.group(2).lower(), texto[m.end():fim]))
    return blocos


# ---------------------------------------------------------------------------
# Quem depende
# ---------------------------------------------------------------------------

class IndiceBackend:
    """Referencias por nome entre funcoes do backend e as rotas HTTP de cada funcao."""

    def __init__(self):
        self.refs = defaultdict(set)   # nome referenciado -> {(modulo, funcao)}
        self.rotas = defaultdict(set)  # (modulo, funcao) -> {url}
        self.defs = defaultdict(int)   # nome de funcao -> em quantos modulos e definido
        prefixos = self._prefixos_app()
        for arquivo in sorted((RAIZ / 'backend').rglob('*.py')):
            modulo = arquivo.relative_to(RAIZ).as_posix()
            try:
                arvore = ast.parse(arquivo.read_text(encoding='utf-8-sig', errors='replace'))
            except SyntaxError as exc:
                AVISOS_ANALISE.append(f'{modulo}: fora do indice de dependencias ({exc.msg})')
                continue
            bps = self._blueprints(arvore, prefixos)
            definidos = set()
            for no in ast.walk(arvore):
                if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    definidos.add(no.name)
                    for filho in ast.walk(no):
                        nome = filho.id if isinstance(filho, ast.Name) else \
                            filho.attr if isinstance(filho, ast.Attribute) else None
                        if nome and nome != no.name:
                            self.refs[nome].add((modulo, no.name))
                    for dec in no.decorator_list:
                        if (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)
                                and dec.func.attr == 'route' and dec.args and isinstance(dec.args[0], ast.Constant)):
                            bp = dec.func.value.id if isinstance(dec.func.value, ast.Name) else ''
                            self.rotas[(modulo, no.name)].add(bps.get(bp, '') + str(dec.args[0].value))
            for nome in definidos:
                self.defs[nome] += 1
            for no in arvore.body:  # referencias de nivel de modulo
                if not isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    for filho in ast.walk(no):
                        if isinstance(filho, (ast.Name, ast.Attribute)):
                            self.refs[filho.id if isinstance(filho, ast.Name) else filho.attr].add((modulo, '<modulo>'))

    @staticmethod
    def _prefixos_app():
        prefixos = {}
        for m in re.finditer(r"register_blueprint\((\w+)\s*,\s*url_prefix=['\"]([^'\"]+)", ler('backend/app.py')):
            prefixos[m.group(1)] = m.group(2)
        return prefixos

    @staticmethod
    def _blueprints(arvore, prefixos):
        bps = {}
        for no in arvore.body:
            if (isinstance(no, ast.Assign) and isinstance(no.value, ast.Call)
                    and getattr(no.value.func, 'id', '') == 'Blueprint'):
                nome = no.targets[0].id if isinstance(no.targets[0], ast.Name) else ''
                prefixo = next((k.value.value for k in no.value.keywords
                                if k.arg == 'url_prefix' and isinstance(k.value, ast.Constant)), '')
                bps[nome] = prefixos.get(nome, prefixo)
        return bps

    def generico(self, nome):
        return nome in NOMES_GENERICOS or nome.startswith('__') or self.defs.get(nome, 0) >= 3 or len(nome) < 5


def dependentes_python(indice, modulo, simbolos, profundidade):
    """{(modulo, funcao): nivel} das funcoes que dependem dos simbolos alterados (ate `profundidade`)."""
    vistos, fronteira = {}, [s for s in simbolos if s != '<modulo>' and not indice.generico(s)]
    for nivel in range(1, profundidade + 1):
        proxima = []
        for nome in fronteira:
            for mod, func in indice.refs.get(nome, ()):
                chave = (mod, func)
                if chave in vistos or (mod == modulo and func in simbolos):
                    continue
                vistos[chave] = nivel
                if func != '<modulo>' and not indice.generico(func):
                    proxima.append(func)
        fronteira = proxima
    return vistos


def dependentes_sql(funcoes, profundidade):
    """Funcoes SQL que chamam as alteradas (financeiro.x(...)), ate `profundidade` niveis."""
    blocos = blocos_sql()
    vistos, fronteira = {}, set(funcoes)
    for nivel in range(1, profundidade + 1):
        proxima = set()
        for nome, corpo in blocos:
            if nome not in funcoes and nome not in vistos and any(
                    re.search(rf'\bfinanceiro\.{re.escape(f)}\s*\(', corpo) for f in fronteira):
                vistos[nome] = nivel
                proxima.add(nome)
        fronteira = proxima
    return vistos


def modulos_js_dependentes(modulos):
    """Fecho dos modulos de web/src/js que importam (direta ou indiretamente) os alterados."""
    fonte = {p.name: p.read_text(encoding='utf-8', errors='replace') for p in (RAIZ / 'web/src/js').glob('*.js')}
    fecho, mudou = set(modulos), True
    while mudou:
        mudou = False
        for nome, texto in fonte.items():
            if nome not in fecho and any(f"'./{m}'" in texto or f'"./{m}"' in texto for m in fecho):
                fecho.add(nome)
                mudou = True
    return fecho, fonte


# ---------------------------------------------------------------------------
# Selecao
# ---------------------------------------------------------------------------

def paginas_web():
    """Paginas do novo aplicativo: as soltas em web/src e as da moldura (web/src/paginas/<pagina>.html vira <pagina>.html
    no build, com os scripts e estilos declarados no comentario <!-- moldura {...} -->)."""
    return sorted((RAIZ / 'web/src').glob('*.html')) + sorted((RAIZ / 'web/src/paginas').glob('*.html'))


def selecionar(mudancas, profundidade):
    testes_py = sorted(p.relative_to(RAIZ).as_posix() for p in (RAIZ / 'tests').glob('test_*.py'))
    texto_teste = {t: ler(t) for t in testes_py}
    especs = sorted(p.relative_to(RAIZ).as_posix() for p in (RAIZ / 'web/tests/e2e').glob('*.spec.mjs'))
    texto_spec = {s: ler(s) for s in especs}
    sel_py, sel_e2e = defaultdict(list), defaultdict(list)
    unit_web, avisos, remotos, sem_cobertura = [], [], [], []
    indice = IndiceBackend()
    cluster = [t for t, tx in texto_teste.items()
               if re.search(r'supabase_local|from tests\.test_supabase_recorrencia import|ClusterLocal', tx)]

    def citar(destino, textos, padrao, motivo):
        achou = False
        for alvo, tx in textos.items():
            if re.search(padrao, tx):
                destino[alvo].append(motivo)
                achou = True
        return achou

    sql_alteradas = set()
    sql_por_dados = set()  # funcoes SQL que leem tabela alterada (E2E por dados, nao por nome)
    js_alterados = set()
    for arquivo, linhas in sorted(mudancas.items()):
        if casa(arquivo, REMOTOS):
            remotos.append(arquivo)  # nunca executado; os testes locais que o usam entram
            nome = Path(arquivo).name
            citar(sel_py, texto_teste, re.escape(nome), f'cita {nome} (script remoto; o teste roda local)')
            continue
        if casa(arquivo, CENTRAIS):
            avisos.append(f'{arquivo}: arquivo central — avaliar nivel 3 (suite completa)')
        coberto = False
        base = Path(arquivo).name
        # 1. Testes que citam o arquivo pelo caminho ou nome (inclui os que leem o frontend como texto)
        if (not casa(arquivo, IGNORADOS) or arquivo.startswith('docs/')) and not arquivo.startswith('tests/'):
            coberto |= citar(sel_py, texto_teste, re.escape(base) if '.' in base else rf'\b{re.escape(base)}\b',
                             f'cita {base}')
        # 2. Teste alterado: roda ele mesmo; simbolos dele importados por outros testes
        if arquivo.startswith('tests/') and arquivo in texto_teste:
            sel_py[arquivo].append('teste alterado')
            coberto = True
            for s in simbolos_python(arquivo, linhas) - {'<modulo>'}:
                modulo = arquivo[:-3].replace('/', '.')
                citar(sel_py, {t: tx for t, tx in texto_teste.items() if t != arquivo},
                      rf'from {re.escape(modulo)} import [^\n]*\b{re.escape(s)}\b|{re.escape(modulo)}\.{re.escape(s)}\b',
                      f'importa {s} de {base}')
        if casa(arquivo, APOIO_CLUSTER):
            for t in cluster:
                sel_py[t].append(f'usa o cluster descartavel de {base}')
            coberto = True
        # 3. Python do backend: simbolos alterados, dependentes e rotas
        if arquivo.startswith('backend/') and arquivo.endswith('.py'):
            simbolos = simbolos_python(arquivo, linhas)
            modulo = arquivo[:-3].replace('/', '.')
            pacote, _, nome_mod = modulo.rpartition('.')
            if linhas is None or '<modulo>' in simbolos:  # modulo novo ou codigo de nivel de modulo alterado
                coberto |= citar(sel_py, texto_teste,
                                 rf'\b{re.escape(modulo)}\b|from\s+{re.escape(pacote)}\s+import\s+[^\n]*\b{nome_mod}\b',
                                 f'importa {modulo} (nivel de modulo alterado)')
            for s in sorted(simbolos - {'<modulo>'}):
                if not indice.generico(s):
                    coberto |= citar(sel_py, texto_teste, rf'\b{re.escape(s)}\b', f'usa {s} (alterado em {base})')
            urls = set()
            for (mod, func), urls_func in indice.rotas.items():
                if mod == arquivo and func in simbolos:
                    urls |= urls_func
            dependentes = dependentes_python(indice, arquivo, simbolos, profundidade)
            for (mod, func), nivel in sorted(dependentes.items(), key=lambda x: x[1]):
                urls |= indice.rotas.get((mod, func), set())
                if func != '<modulo>' and not indice.generico(func):
                    citar(sel_py, texto_teste, rf'\b{re.escape(func)}\b',
                          f'usa {func} ({Path(mod).name}), que depende de {base} [nivel {nivel}]')
            for url in sorted(u for u in urls if len(u.split('<')[0].rstrip('/')) >= 8):
                coberto |= citar(sel_py, texto_teste, padrao_rota(url),
                                 f'chama a rota {url} (alterada ou dependente de {base})')
        # 4. Migrations do Supabase: funcoes alteradas, chamadoras e telas que as usam
        if arquivo.startswith('supabase/migrations/') and arquivo.endswith('.sql'):
            texto = ler(arquivo)
            alteradas = {m.group(2).lower() for m in RE_FUNCAO_SQL.finditer(texto)}
            tabelas = set(re.findall(r'(?:alter|create)\s+table\s+(?:if\s+not\s+exists\s+)?(?:public\.)?(\w+)', texto, re.I))
            chamadoras = dependentes_sql(alteradas, profundidade)
            sql_alteradas |= alteradas | set(chamadoras)
            for nome in sorted(alteradas | set(chamadoras)):
                origem = 'alterada' if nome in alteradas else f'chama funcao alterada [nivel {chamadoras[nome]}]'
                coberto |= citar(sel_py, texto_teste, rf'\b{nome}\b', f'usa financeiro.{nome} ({origem})')
            for tabela in sorted(tabelas):
                citar(sel_py, {t: texto_teste[t] for t in cluster}, rf'\b{tabela}\b', f'usa a tabela {tabela} (alterada)')
            leitoras = {nome for nome, corpo in blocos_sql()
                        if any(re.search(rf'\b(?:public|financeiro)\.{re.escape(t)}\b', corpo) for t in tabelas)}
            sql_por_dados |= leitoras | set(dependentes_sql(leitoras, profundidade))
        # 5. Alembic
        if arquivo.startswith('migrations/versions/'):
            revisao = Path(arquivo).stem.split('_')[0]
            coberto |= citar(sel_py, texto_teste, re.escape(revisao), f'cita a revisao {revisao}')
        # 6. Novo aplicativo (web/)
        if arquivo.startswith('web/'):
            unit_web.append(arquivo)
            if arquivo.startswith('web/src/js/'):
                js_alterados.add(base)
            elif arquivo.startswith('web/src/') and arquivo.endswith('.html'):
                citar(sel_e2e, texto_spec, re.escape(base), f'abre {base} (alterada)')
            elif arquivo.startswith('web/src/css/'):
                for spec in especs:
                    sel_e2e[spec].append(f'{base} e usada por todas as telas')
            elif arquivo in especs:
                sel_e2e[arquivo].append('spec alterado')
            coberto = True
        # 6b. Arquivos do Flask que o novo aplicativo reaproveita (FIN-MIGRACAO-FIDELIDADE): JS e CSS copiados pelo build
        # (js/original/, css/shared/) e templates de onde as paginas da moldura foram geradas.
        reaproveitado = {'frontend/static/js/': f'js/original/{base}', 'frontend/static/css/': f'css/shared/{base}',
                         'frontend/templates/': f'frontend/templates/{base}'}
        for prefixo, marca in reaproveitado.items():
            if arquivo.startswith(prefixo):
                for pagina in paginas_web():
                    if marca in pagina.read_text(encoding='utf-8', errors='replace'):
                        citar(sel_e2e, texto_spec, re.escape(pagina.name), f'abre {pagina.name} (usa {marca} do Flask)')
                        coberto = True
        if casa(arquivo, INFRA_E2E):
            for spec in especs:
                sel_e2e[spec].append(f'infraestrutura do E2E alterada ({base})')
            coberto = True
        # 7. Regra financeira permanente: na duvida sobre impacto financeiro, ampliar
        if casa(arquivo, CODIGO):
            achado = AREAS_FINANCEIRAS.search(trecho_alterado(arquivo, linhas))
            if achado:
                motivo = f"regra financeira: trecho alterado de {base} cita '{achado.group(0)}' (na duvida, ampliar)"
                for padrao in PROTECOES_FINANCEIRAS:
                    for t in testes_py:
                        if fnmatch.fnmatch(t, padrao):
                            sel_py[t].append(motivo)
                if arquivo.startswith(('supabase/', 'web/src/')):  # o novo aplicativo pode ser afetado
                    for spec in E2E_FINANCEIROS:
                        if spec in texto_spec:
                            sel_e2e[spec].append(motivo)
                coberto = True
        # 8. Matriz curada
        for padroes, conteudo, testes, motivo in REGRAS:
            if casa(arquivo, padroes) and (conteudo is None or re.search(conteudo, ler(arquivo))):
                for padrao in testes:
                    for t in testes_py:
                        if fnmatch.fnmatch(t, padrao):
                            sel_py[t].append(f'matriz: {motivo}')
                            coberto = True
        if not coberto and not casa(arquivo, IGNORADOS):
            sem_cobertura.append(arquivo)

    # Telas do novo aplicativo afetadas: JS alterado, JS que chama RPC alterada ou RPC que le tabela alterada
    # (dados: a tela de Contas mostra faturas de cartao sem importar o JS de cartoes), e quem importa esses JS.
    if js_alterados or sql_alteradas or sql_por_dados:
        _, fonte = modulos_js_dependentes(set())
        raizes = {m: 'alterado' for m in js_alterados}
        for nome, texto in fonte.items():
            rpcs = set(re.findall(r"""\.rpc\(\s*['"](\w+)['"]""", texto))
            if rpcs & sql_alteradas:
                raizes.setdefault(nome, 'chama RPC alterada: ' + ', '.join(sorted(rpcs & sql_alteradas)[:3]))
            elif rpcs & sql_por_dados:
                raizes.setdefault(nome, 'chama RPC que le tabela alterada: ' + ', '.join(sorted(rpcs & sql_por_dados)[:3]))
        alcance = {r: modulos_js_dependentes({r})[0] for r in raizes}
        # Todo spec espera cair em contas.html depois do login (waitForURL): isso nao e testar a tela.
        navegacao = {s: re.sub(r'waitForURL\([^)]*\)', '', tx) for s, tx in texto_spec.items()}
        for pagina in paginas_web():
            html = pagina.read_text(encoding='utf-8', errors='replace')
            motivos = [f'{r} ({raizes[r]})' for r in sorted(raizes) if any(f'js/{m}' in html for m in alcance[r])]
            if motivos:
                citar(sel_e2e, navegacao, re.escape(pagina.name), f'abre {pagina.name} — ' + '; '.join(motivos[:2]))
    avisos.extend(dict.fromkeys(AVISOS_ANALISE))
    return {'py': dict(sel_py), 'e2e': dict(sel_e2e), 'unit_web': unit_web, 'avisos': avisos, 'remotos': remotos,
            'sem_cobertura': sem_cobertura, 'total_py': len(testes_py), 'total_e2e': len(especs)}


def mostrar(sel):
    print(f"\n=== Python (pytest): {len(sel['py'])} de {sel['total_py']} arquivos de teste")
    for t, motivos in sorted(sel['py'].items()):
        unicos = list(dict.fromkeys(motivos))
        print(f'  {t}\n      - ' + '\n      - '.join(unicos[:4]) + (f'\n      - (+{len(unicos) - 4} motivos)' if len(unicos) > 4 else ''))
    print(f"\n=== Web unit: {'todos (rapidos)' if sel['unit_web'] else 'nenhum'}")
    print(f"=== Web E2E: {len(sel['e2e'])} de {sel['total_e2e']} specs")
    for s, motivos in sorted(sel['e2e'].items()):
        print(f'  {s}: ' + '; '.join(list(dict.fromkeys(motivos))[:2]))
    for titulo, chave in (('Remotos (NAO executados; so com autorizacao)', 'remotos'),
                          ('Sem teste encontrado (revisar manualmente ou ampliar)', 'sem_cobertura'),
                          ('Avisos', 'avisos')):
        if sel[chave]:
            print(f'\n=== {titulo}:\n  ' + '\n  '.join(sel[chave]))


# ---------------------------------------------------------------------------
# Execucao e medicao
# ---------------------------------------------------------------------------

def executar(sel, saida, sem_e2e):
    saida.mkdir(parents=True, exist_ok=True)
    etapas = []
    if sel['py']:
        xml = saida / 'pytest.xml'
        inicio = time.perf_counter()
        r = subprocess.run([sys.executable, '-m', 'pytest', *sorted(sel['py']), '-p', 'no:cacheprovider', '-rfEs',
                            '--durations=15', f'--junitxml={xml}'], cwd=RAIZ)
        etapas.append(('pytest', time.perf_counter() - inicio, r.returncode))
        resumo_junit(xml)
    if sel['unit_web']:
        npm = shutil.which('npm') or 'npm'
        inicio = time.perf_counter()
        r = subprocess.run([npm, 'run', 'test:unit'], cwd=RAIZ / 'web')
        etapas.append(('web unit', time.perf_counter() - inicio, r.returncode))
    if sel['e2e'] and not sem_e2e:
        inicio = time.perf_counter()
        r = subprocess.run([sys.executable, 'web/tests/e2e/run_e2e.py', *[Path(s).name for s in sorted(sel['e2e'])]],
                           cwd=RAIZ)
        etapas.append(('web E2E', time.perf_counter() - inicio, r.returncode))
    print('\n=== Duracao por etapa (relogio)')
    for nome, segundos, codigo in etapas:
        print(f'  {nome:<9} {segundos / 60:6.1f} min  saida={codigo}')
    print(f'  {"total":<9} {sum(e[1] for e in etapas) / 60:6.1f} min')
    return max((e[2] for e in etapas), default=0)


def resumo_junit(xml):
    if not xml.exists():
        return
    por_arquivo = defaultdict(lambda: [0, 0.0, 0, 0, 0])  # testes, segundos, falhas, erros, pulados
    for caso in ET.parse(xml).getroot().iter('testcase'):
        arquivo = caso.get('classname', '').split('.')
        nome = '/'.join(arquivo[:2]) + '.py' if len(arquivo) >= 2 else caso.get('classname', '?')
        dados = por_arquivo[nome]
        dados[0] += 1
        dados[1] += float(caso.get('time') or 0)
        dados[2] += caso.find('failure') is not None
        dados[3] += caso.find('error') is not None
        dados[4] += caso.find('skipped') is not None
    print('\n=== Tempo por arquivo (soma dos testes, inclui preparacao das fixtures)')
    print(f'  {"arquivo":<52} {"testes":>6} {"min":>6} {"falhas":>6} {"erros":>5} {"pulados":>7}')
    for nome, (n, s, f, e, p) in sorted(por_arquivo.items(), key=lambda x: -x[1][1]):
        print(f'  {nome:<52} {n:>6} {s / 60:>6.1f} {f:>6} {e:>5} {p:>7}')
    total = [sum(x[i] for x in por_arquivo.values()) for i in range(5)]
    print(f'  {"TOTAL":<52} {total[0]:>6} {total[1] / 60:>6.1f} {total[2]:>6} {total[3]:>5} {total[4]:>7}')


def main():
    parser = argparse.ArgumentParser(description='Selecao de testes por impacto (TESTES-IMPACTO-1).')
    parser.add_argument('--base', default='HEAD', help='revisao de comparacao (padrao: HEAD = alteracoes locais)')
    parser.add_argument('--arquivos', nargs='+', help='analisar estes arquivos em vez do diff do Git')
    parser.add_argument('--profundidade', type=int, default=2, help='niveis de dependentes (padrao 2)')
    parser.add_argument('--executar', action='store_true', help='executa e mede a selecao')
    parser.add_argument('--sem-e2e', action='store_true', help='nao executa o E2E web')
    parser.add_argument('--excluir', nargs='+', default=[],
                        help='testes ja validados NESTA MESMA versao dos arquivos (registrar a evidencia no relatorio)')
    parser.add_argument('--saida', default=str(Path(tempfile.gettempdir()) / 'testes_impacto'),
                        help='pasta do relatorio JUnit (padrao: pasta temporaria do sistema)')
    args = parser.parse_args()
    mudancas = alteracoes(args.base, args.arquivos)
    print(f'Alteracoes analisadas ({len(mudancas)}): base {args.base if not args.arquivos else "--arquivos"}')
    for arquivo in sorted(mudancas):
        print(f'  {arquivo}')
    sel = selecionar(mudancas, args.profundidade)
    mostrar(sel)
    excluidos = [Path(x).as_posix() for x in args.excluir]
    if excluidos:
        print('\n=== Reaproveitados (validados na mesma versao; nao executados agora):')
        for teste in excluidos:
            print(f"  {teste}{'' if teste in sel['py'] or teste in sel['e2e'] else '  (nao estava na selecao)'}")
            sel['py'].pop(teste, None)
            sel['e2e'].pop(teste, None)
        print(f"  restam {len(sel['py'])} arquivos Python e {len(sel['e2e'])} specs E2E")
    if args.executar:
        sys.exit(executar(sel, Path(args.saida), args.sem_e2e))


if __name__ == '__main__':
    main()
