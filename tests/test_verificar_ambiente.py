"""
FIN-TRANSFERENCIA-AMBIENTE-1 — scripts/verificar_ambiente.py: so le, e nunca imprime valores de configuracao.
"""
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / 'scripts'))
import verificar_ambiente as V  # noqa: E402

SENSIVEIS = ('SENHA', 'SECRET', 'KEY', 'PASSWORD', 'TOKEN', 'EMAIL', 'DATABASE_URL', 'PGPASS')


def test_chaves_do_env_devolve_so_nomes_com_valor(tmp_path):
    arquivo = tmp_path / '.env.teste'
    arquivo.write_text('﻿# comentario=1\nSECRET_KEY=valor-secreto-123\nVAZIA=\nexport CF_EMAIL_A="x@y"\nDATABASE_URL = abc\n',
                       encoding='utf-8')
    assert V.chaves_do_env(arquivo) == {'SECRET_KEY', 'CF_EMAIL_A', 'DATABASE_URL'}


def test_requisitos_fixados_le_o_requirements():
    fixados = V.requisitos_fixados('requirements.txt')
    assert fixados['Flask'] == '3.0.0' and 'psycopg2-binary' in fixados


def test_saida_nao_contem_valores_dos_arquivos_locais():
    valores = set()
    for arquivo in V.ARQUIVOS_ENV:
        caminho = RAIZ / arquivo
        if caminho.exists():
            for linha in caminho.read_text(encoding='utf-8-sig').splitlines():
                if '=' in linha and not linha.lstrip().startswith('#'):
                    nome, valor = linha.split('=', 1)
                    valor = valor.strip().strip('"\'')
                    # So valores sensiveis: APP_ENV=staging, por exemplo, coincide com o nome do arquivo .env.staging.
                    if len(valor) >= 6 and any(p in nome.upper() for p in SENSIVEIS):
                        valores.add(valor)
    if not valores:
        pytest.skip('sem arquivos .env locais nesta maquina')
    r = subprocess.run([sys.executable, str(RAIZ / 'scripts' / 'verificar_ambiente.py')], cwd=RAIZ, capture_output=True,
                       text=True, encoding='utf-8', errors='replace', timeout=300)
    saida = r.stdout + r.stderr
    assert 'Resumo:' in saida
    assert not [v for v in valores if v in saida]


# FIN-MIGRACAO-P0P1-01: o .env.e2e-real foi apagado de proposito (projeto Supabase em producao). Ausente = estado normal.
def _configuracao_em(raiz, monkeypatch):
    monkeypatch.setattr(V, 'RAIZ', raiz)
    monkeypatch.setattr(V, 'RESULTADOS', [])
    monkeypatch.setattr(V, 'ARQUIVOS_ENV', {'.env.e2e-real': V.ARQUIVOS_ENV['.env.e2e-real']})
    V.verificar_configuracao()
    return [(nivel, item) for nivel, item in V.RESULTADOS if '.env.e2e-real' in item]


def test_env_e2e_real_ausente_e_ok(tmp_path, monkeypatch):
    linhas = _configuracao_em(tmp_path, monkeypatch)
    assert linhas == [('OK', '.env.e2e-real ausente: NAO_CONFIGURADO_INTENCIONALMENTE')]


def test_env_e2e_real_presente_gera_aviso(tmp_path, monkeypatch):
    (tmp_path / '.env.e2e-real').write_text('CF_EMAIL_A=ficticio\n', encoding='utf-8')  # valor ficticio, so no tmp
    linhas = _configuracao_em(tmp_path, monkeypatch)
    assert ('AVISO', '.env.e2e-real presente') in linhas
    assert not any(nivel == 'OK' and 'ausente' in item for nivel, item in linhas)
