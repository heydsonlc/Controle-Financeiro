"""
TESTES-IMPACTO-1 — o seletor de testes por impacto (scripts/testes_impacto.py).

So analise estatica sobre o repositorio (nenhum teste e executado, nenhum banco e aberto).
"""
import importlib.util
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent


@pytest.fixture(scope='module')
def ti():
    spec = importlib.util.spec_from_file_location('testes_impacto', RAIZ / 'scripts' / 'testes_impacto.py')
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


FONTE = '''﻿"""Modulo com BOM, como varios do backend."""
import os

LIMITE = 10


class Servico:
    ATRIBUTO = 1
    _cache = {}

    def metodo_alterado(self):
        return 1

    def metodo_intacto(self):
        return 2


def funcao_solta():
    return os.sep
'''


def test_simbolos_pelas_linhas_alteradas(ti, tmp_path):
    arquivo = tmp_path / 'modulo.py'
    arquivo.write_text(FONTE, encoding='utf-8')
    linha = {texto.strip(): n for n, texto in enumerate(FONTE.splitlines(), start=1)}
    assert ti.simbolos_python(arquivo, {linha['return 1']}) == {'metodo_alterado'}  # metodo: a classe nao arrasta
    assert ti.simbolos_python(arquivo, {linha['ATRIBUTO = 1']}) == {'Servico'}       # corpo da classe: arrasta
    assert ti.simbolos_python(arquivo, {linha['_cache = {}']}) == {'_cache'}         # atributo privado: nao arrasta
    assert ti.simbolos_python(arquivo, {linha['LIMITE = 10']}) == {'LIMITE'}
    assert ti.simbolos_python(arquivo, {linha['import os']}) == {'<modulo>'}         # importadores dependem
    assert ti.simbolos_python(arquivo, None) == {'LIMITE', 'Servico', 'metodo_alterado', 'metodo_intacto',
                                                'funcao_solta', '<modulo>'}          # arquivo novo: tudo


@pytest.mark.parametrize('rota, codigo, casa', [
    ('/api/despesas/<int:id>/pagar', "c.post(f'/api/despesas/{d.id}/pagar')", True),
    ('/api/despesas/<int:id>/pagar', "c.post(f'/api/despesas/{d[\"id\"]}/pagar', json={})", True),
    ('/api/despesas/', "c.post(f'/api/despesas/{d.id}/pagar')", False),  # a raiz nao casa outra rota do blueprint
    ('/api/despesas/', "c.get('/api/despesas/?mes=2026-01')", True),
    ('/api/despesas/', "c.get('/api/despesas')", True),
    ('/api/despesas/', "c.get('/api/despesas/recorrentes')", False),
    ('/api/cartoes/<int:cartao_id>/lancamentos', "f'/api/cartoes/{c}/lancamentos'", True),
])
def test_rota_casa_o_caminho_inteiro(ti, rota, codigo, casa):
    import re
    assert bool(re.search(ti.padrao_rota(rota), codigo)) is casa


def test_funcoes_sql_chamadoras(ti):
    chamadoras = ti.dependentes_sql({'plano_compra'}, 1)
    assert {'previa_compra', 'criar_compra'} <= set(chamadoras)  # usam financeiro.plano_compra(...)
    assert 'pode_gerir_perfil' not in chamadoras


def test_selecao_backend_sql_e_remotos(ti):
    sel = ti.selecionar({'backend/services/cartao_service.py': {0}, 'frontend/static/js/lancamentos.js': None,
                         'supabase/migrations/20261030090000_financeiro_cartoes_fechamento.sql': None,
                         'scripts/supabase_cartoes_real.py': None}, 2)
    py = sel['py']
    for teste in ti.PROTECOES_CARTAO + ti.INVARIANTES_ESQUEMA:  # matriz curada
        assert teste in py, teste
    assert 'tests/test_supabase_cartoes.py' in py               # usa funcoes SQL alteradas
    assert 'tests/test_payment_assets.py' in py                 # le lancamentos.js como texto
    assert 'tests/test_ir_ocr.py' not in py                     # sem relacao
    assert sel['remotos'] == ['scripts/supabase_cartoes_real.py']  # listado, nunca executado
    sel = ti.selecionar({'scripts/supabase_conferencia_migration.py': None}, 2)
    assert sel['remotos'] == ['scripts/supabase_conferencia_migration.py']
    assert 'tests/test_cartoes_fechamento.py' in sel['py']  # usa o script localmente


def test_selecao_web_por_importacao_e_tela(ti):
    sel = ti.selecionar({'web/src/js/fechamento.js': None}, 2)
    e2e = set(sel['e2e'])
    # fechamento.js e importado por compra-cartao.js e lancamentos-adaptador.js, carregados pelas paginas da moldura
    # (web/src/paginas/cartoes.html e lancamentos.html); cartoes.spec/fechamento.spec sairam no FIN-FIDELIDADE-CARTOES-1.
    assert {'web/tests/e2e/cartoes_tela.spec.mjs', 'web/tests/e2e/lancamentos_tela.spec.mjs'} <= e2e
    assert 'web/tests/e2e/receitas.spec.mjs' not in e2e
    assert sel['unit_web'] == ['web/src/js/fechamento.js']
    sel = ti.selecionar({'web/tests/e2e/run_e2e.py': {1}}, 2)
    assert len(sel['e2e']) == sel['total_e2e']  # infraestrutura: todos os specs


def test_e2e_por_dados_da_tabela_alterada(ti):
    # A migration altera lancamento_agregado e config_agregador: a tela de Contas mostra faturas de cartao
    # (contas_do_mes le essas tabelas) sem importar o JS de cartoes.
    sel = ti.selecionar({'supabase/migrations/20261030090000_financeiro_cartoes_fechamento.sql': None}, 2)
    e2e = {s.rsplit('/', 1)[-1] for s in sel['e2e']}
    assert {'contas.spec.mjs', 'despesas.spec.mjs', 'recorrencia.spec.mjs', 'cartoes_tela.spec.mjs'} <= e2e
    # so esperar cair em contas.html depois do login nao e testar a tela (perfis.spec abre contas.html?mes=... de fato:
    # entra desde que a pagina da moldura web/src/paginas/contas.html passou a ser lida)
    assert 'acesso.spec.mjs' not in e2e
    assert 'perfis.spec.mjs' in e2e


def test_regra_financeira_amplia_na_duvida(ti):
    servico = 'backend/services/cartao_service.py'
    linhas = (RAIZ / servico).read_text(encoding='utf-8-sig').splitlines()
    pagar = next(n for n, texto in enumerate(linhas, start=1) if 'def pagar_fatura' in texto)
    neutra = next(n for n, texto in enumerate(linhas, start=1) if 'def dia_contratual' in texto)
    sel = ti.selecionar({servico: {pagar}}, 2)
    for teste in ('tests/test_pagamento_trava.py', 'tests/test_estorno_fatura.py', 'tests/test_core_saldo_despesas.py',
                  'tests/test_movimento_original_estorno.py', 'tests/test_baixa_despesa_transacional.py'):
        assert any(m.startswith('regra financeira') for m in sel['py'].get(teste, [])), teste
    assert sel['e2e'] == {}  # so o Flask mudou: o novo aplicativo nao e afetado
    sel = ti.selecionar({servico: {neutra}}, 2)
    assert not any(m.startswith('regra financeira') for motivos in sel['py'].values() for m in motivos)


def test_arquivo_do_flask_reaproveitado_seleciona_a_tela_que_o_usa(ti):
    # FIN-MIGRACAO-FIDELIDADE: o build copia o JS do Flask para js/original/ e a pagina da moldura o declara.
    e2e = set(ti.selecionar({'frontend/static/js/patrimonio.js': None}, 2)['e2e'])
    assert 'web/tests/e2e/patrimonio_tela.spec.mjs' in e2e
    assert 'web/tests/e2e/receitas.spec.mjs' not in e2e
    e2e = set(ti.selecionar({'frontend/templates/veiculos.html': None}, 2)['e2e'])
    assert 'web/tests/e2e/mobilidade_tela.spec.mjs' in e2e
