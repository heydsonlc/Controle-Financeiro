"""
FIN-CARTOES-PAGAMENTO-REAL-1 — testes reais de pagamento e estorno de fatura no Supabase de teste.

So dados FICTICIOS: toda escrita no "Perfil B" temporario (usuario B, gestor, atribuido ao novo aplicativo pelo seed
de recorrencia), num cartao criado aqui (compras so em 2039), na "Conta Perfil B" do seed e numa conta inativa criada
aqui (marcador "[teste FIN-CARTOES-PAGAMENTO-REAL-1]"). Usuario A (sem vinculo com o Perfil B) so recebe recusas. Data
API real com login real; o banco (postgres) so consolida uma fatura como o Flask, segura a conta bancaria para o
cenario de rollback e confere resultados; um processo Flask real faz a compra concorrente.

Cenarios em supabase_cartoes_pagamento_cenarios.py (ensaiados localmente com o mesmo codigo).
Pre-requisitos: migration 20261031090000 aplicada; supabase_despesas_real_limpeza.py marcar; seeds perfis -> contas ->
recorrencia -> cartoes; .env.e2e-real. Na mesma validacao, rodar tambem supabase_cartoes_real.py (cenario 10 do
FIN-CARTOES-FECHAMENTO-REAL-1, roteiro corrigido). Limpeza: supabase_despesas_real_limpeza.py remover (cartao, compras,
faturas, movimentos, detalhes dos pagamentos, chaves e a conta inativa criados aqui). Nao imprime credenciais nem a URL
do banco.
"""
# FIN-PUBLICACAO-SEGURA-1: o projeto de teste virou a producao; recusa antes de ler credenciais ou conectar.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from guarda_producao import recusar_em_producao
recusar_em_producao(__file__)
import json
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / 'scripts'))

from supabase_fatura_concorrencia_real import (  # noqa: E402
    CATEGORIA, ORIGEM, PERFIL_B, PESSOAL, URL, Flask, aguardar, banco, em_thread, liberar, rpc,
)
from supabase_cartoes_pagamento_cenarios import executar  # noqa: E402
from verificar_exposicao_supabase import chave_publica_via_cli  # noqa: E402

CHAVE, _ = chave_publica_via_cli()
RESULTADOS = []


def registrar(nome, ok, detalhe):
    RESULTADOS.append((nome, ok))
    print(f"{'OK ' if ok else 'FALHA'} | {nome} | {detalhe}", flush=True)


def anonimo(funcao, corpo):
    req = urllib.request.Request(f'{ORIGEM}/rest/v1/rpc/{funcao}', method='POST', data=json.dumps(corpo).encode())
    for nome, valor in (('apikey', CHAVE), ('Content-Type', 'application/json'), ('Content-Profile', 'financeiro')):
        req.add_header(nome, valor)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


def conectar():
    import psycopg2
    return psycopg2.connect(URL, connect_timeout=15)


def fora_do_perfil_b():
    """Registros financeiros fora do Perfil B (contas bancarias, movimentos, contas e detalhes de pagamento)."""
    def md5(sql):
        return banco(sql, (PERFIL_B,))[0][0]
    return (md5("select md5(coalesce(string_agg(t::text, '|' order by id), '')) from public.conta_bancaria t "
                'where perfil_financeiro_id is distinct from %s'),
            md5("select md5(coalesce(string_agg(t::text, '|' order by id), '')) from public.movimento_financeiro t "
                'where perfil_financeiro_id is distinct from %s'),
            md5("select md5(coalesce(string_agg(t::text, '|' order by id), '')) from public.conta t "
                'where perfil_financeiro_id is distinct from %s'),
            md5("select md5(coalesce(string_agg(t::text, '|' order by id), '')) from financeiro.pagamento_fatura t "
                'where perfil_financeiro_id is distinct from %s'))


def main():
    if banco("select financeiro.gerador_do_perfil(%s)", (PERFIL_B,))[0][0] != 'NOVO':
        raise SystemExit('O Perfil B precisa estar atribuido ao novo aplicativo (seed de recorrencia).')
    conta = banco("select id from public.conta_bancaria where nome = 'Conta Perfil B' and perfil_financeiro_id = %s",
                  (PERFIL_B,))[0][0]
    outra = banco("select id from public.conta_bancaria where nome = 'Conta Pessoal (A)' and perfil_financeiro_id = %s",
                  (PESSOAL,))[0][0]
    inicio = fora_do_perfil_b()
    with tempfile.TemporaryDirectory(prefix='pagamento-real-') as tmp:
        def pasta(nome):
            p = Path(tmp) / nome
            p.mkdir()
            return p
        executar(SimpleNamespace(rpc=rpc, anonimo=anonimo, banco=banco, conectar=conectar, registrar=registrar,
                                 flask=Flask, aguardar=aguardar, liberar=liberar, em_thread=em_thread, pasta=pasta,
                                 B=PERFIL_B, conta=conta, conta_outro_perfil=outra, categoria=CATEGORIA))
    registrar('16. Registros fora do Perfil B preservados', fora_do_perfil_b() == inicio,
              'contas bancarias, movimentos, contas e detalhes de pagamento fora do Perfil B identicos')
    falhas = [n for n, ok in RESULTADOS if not ok]
    print('RESULTADO:', 'OK' if not falhas else f'FALHAS: {falhas}')
    return 1 if falhas else 0


if __name__ == '__main__':
    sys.exit(main())
