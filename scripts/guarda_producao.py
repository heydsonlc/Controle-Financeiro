"""FIN-PUBLICACAO-SEGURA-1 — trava dos scripts de teste e de homologacao "real".

Desde o FIN-BLOCO-D-3, o projeto Supabase fzjmge... deixou de ser o banco de teste: guarda os dados reais do titular.
Os seeds de dados ficticios, os testes pela API e pela tela (E2E real), as homologacoes de migration e a limpeza do que
os testes criaram foram escritos para ele como projeto de teste e so sabem apontar para ele. Esta trava os recusa logo
no inicio, antes de ler credenciais ou conectar.

Testes reais futuros vao num projeto de teste separado, com contrato proprio, que ajusta esta trava para ele.
Somente leitura (digital_lote.py, verificar_seguranca_supabase.py) e operacao por identidade
(limpeza_ficticios_supabase.py, vincular_titular_supabase.py) nao passam por aqui.
"""
from pathlib import Path

PROJETO_PRODUCAO = 'fzjmgekasjrgvmfdkdog'


def recusar_em_producao(script):
    raise SystemExit(f'BLOQUEADO: {Path(script).name} grava dados ficticios ou testa no projeto Supabase '
                     f'{PROJETO_PRODUCAO[:6]}..., que agora e a producao (FIN-PUBLICACAO-SEGURA-1). '
                     'Use um projeto de teste separado, com contrato proprio.')
