"""
Testes FIN-CARTAO-NUBANK-CREDITOS-01 — a migration 20261212090000 e a reversao versionadas sao a saida exata do gerador
(scripts/gerar_migration_cartao_nubank_creditos.py), que parte do texto das migrations anteriores. Nada e gravado.
"""
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
GERADOR = RAIZ / 'scripts' / 'gerar_migration_cartao_nubank_creditos.py'


def test_migration_e_reversao_sao_a_saida_do_gerador():
    r = subprocess.run([sys.executable, str(GERADOR), str(RAIZ), '--verificar'], capture_output=True, text=True)
    assert (r.returncode, r.stdout.strip()) == (0, 'igual'), r.stdout + r.stderr


def test_verificar_acusa_diferenca(tmp_path):
    """Numa copia com a migration alterada, o modo de verificacao falha e nao grava."""
    destino = tmp_path / 'supabase'
    (destino / 'migrations').mkdir(parents=True)
    (destino / 'reversao').mkdir()
    for pasta in ('migrations', 'reversao'):
        for arquivo in (RAIZ / 'supabase' / pasta).glob('*.sql'):
            (destino / pasta / arquivo.name).write_bytes(arquivo.read_bytes())
    alvo = destino / 'migrations' / '20261212090000_financeiro_cartao_nubank_creditos.sql'
    alvo.write_bytes(alvo.read_bytes() + b'-- editado a mao\n')
    antes = alvo.read_bytes()
    r = subprocess.run([sys.executable, str(GERADOR), str(tmp_path), '--verificar'], capture_output=True, text=True)
    assert r.returncode == 1 and 'diferente: supabase' in r.stdout
    assert alvo.read_bytes() == antes
