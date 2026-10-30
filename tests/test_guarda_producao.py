"""FIN-PUBLICACAO-SEGURA-1 — os scripts de teste e de homologacao "real" recusam a producao antes de qualquer outra coisa.

Cada script roda num processo sem credenciais e sem rede configurada: a trava tem de interromper antes de ler o
.env, montar o build ou conectar, com a mensagem BLOQUEADO e codigo de saida diferente de zero."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
TRAVADOS = [
    'scripts/homologacao_cartoes.py', 'scripts/supabase_cartoes_pagamento_real.py', 'scripts/supabase_cartoes_real.py',
    'scripts/supabase_contas_equivalencia_real.py', 'scripts/supabase_despesas_real.py',
    'scripts/supabase_fatura_concorrencia_real.py', 'scripts/supabase_fatura_integridade_real.py',
    'scripts/supabase_movimentacoes_real.py', 'scripts/supabase_receitas_real.py', 'scripts/supabase_cartoes_seed_teste.py',
    'scripts/supabase_contas_seed_teste.py', 'scripts/supabase_demo_preview_seed.py', 'scripts/supabase_mvp_seed_teste.py',
    'scripts/supabase_perfis_seed_teste.py', 'scripts/supabase_receitas_seed_teste.py',
    'scripts/supabase_recorrencia_seed_teste.py', 'scripts/supabase_despesas_real_limpeza.py',
    'scripts/homologacao_real/cr_real.py', 'scripts/homologacao_real/escritor_real.py',
    'scripts/homologacao_real/lote_real.py', 'scripts/homologacao_real/motor_real.py', 'scripts/homologacao_real/pat_real.py',
    'web/tests/e2e/run_e2e_real.py',
]


@pytest.mark.parametrize('script', TRAVADOS)
def test_script_real_recusa_a_producao(script, tmp_path):
    env = {k: v for k, v in os.environ.items() if k in ('SYSTEMROOT', 'PATH', 'TEMP', 'TMP')}
    # Diretorio de trabalho vazio: sem .env.staging nem .env.e2e-real ao alcance de caminhos relativos.
    r = subprocess.run([sys.executable, str(RAIZ / script), '--help'], cwd=tmp_path, env=env,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode != 0
    assert 'BLOQUEADO' in r.stderr and Path(script).name in r.stderr
    assert r.stdout == ''


def test_trava_esta_antes_de_qualquer_import():
    for script in TRAVADOS:
        texto = (RAIZ / script).read_text(encoding='utf-8')
        trava = texto.index('recusar_em_producao(__file__)')
        depois_da_doc = texto.index('# FIN-PUBLICACAO-SEGURA-1')
        antes = texto[:depois_da_doc]
        assert 'import ' not in antes.split('"""')[-1], script  # nada importado antes da trava
        assert trava > depois_da_doc
