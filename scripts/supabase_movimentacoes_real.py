"""
FIN-MOVIMENTACOES-REAL-1 — testes reais de pagamento de despesa, recebimento de receita, estornos e movimentos do mes
no Supabase de teste.

So dados FICTICIOS: toda escrita no "Perfil B" temporario (usuario B, gestor, atribuido ao novo aplicativo pelo seed
de recorrencia), em despesas e receitas criadas aqui pela API do novo aplicativo (marcador
"[teste FIN-MOVIMENTACOES-REAL-1]", 03/2040), na "Conta Perfil B" do seed e numa conta inativa criada aqui. Usuario A
(sem vinculo com o Perfil B) so recebe recusas. Data API real com login real; o banco (postgres) so cria a conta
inativa, segura a conta bancaria para o cenario de falha e confere resultados.

Cenarios em supabase_movimentacoes_cenarios.py (ensaiados localmente com o mesmo codigo).
Pre-requisitos: migration 20261101090000 aplicada; supabase_despesas_real_limpeza.py marcar; seeds perfis -> contas ->
recorrencia -> receitas -> mvp -> cartoes; .env.e2e-real. Na mesma validacao, rodar tambem
supabase_cartoes_pagamento_real.py (pagamento de cartoes preservado). Limpeza: supabase_despesas_real_limpeza.py remover
(despesas, previsoes, recebimentos, movimentos, detalhes de pagamento, chaves e a conta inativa criados aqui). Nao
imprime credenciais nem a URL do banco.
"""
# FIN-PUBLICACAO-SEGURA-1: o projeto de teste virou a producao; recusa antes de ler credenciais ou conectar.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from guarda_producao import recusar_em_producao
recusar_em_producao(__file__)
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / 'scripts'))

from supabase_fatura_concorrencia_real import (  # noqa: E402
    CATEGORIA, ORIGEM, PERFIL_B, PESSOAL, URL, banco, em_thread, rpc,
)
from supabase_movimentacoes_cenarios import executar  # noqa: E402
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
    """Registros financeiros fora do Perfil B: contas bancarias, movimentos, contas, receitas e detalhes de pagamento."""
    tabelas = ('public.conta_bancaria', 'public.movimento_financeiro', 'public.conta', 'public.receita_realizada',
               'public.receita_orcamento', 'public.item_receita', 'financeiro.pagamento_fatura')
    return tuple(banco(f"select md5(coalesce(string_agg(t::text, '|' order by id), '')) from {t} t "
                       'where perfil_financeiro_id is distinct from %s', (PERFIL_B,))[0][0] for t in tabelas)


def main():
    if banco('select financeiro.gerador_do_perfil(%s)', (PERFIL_B,))[0][0] != 'NOVO':
        raise SystemExit('O Perfil B precisa estar atribuido ao novo aplicativo (seed de recorrencia).')
    conta = banco("select id from public.conta_bancaria where nome = 'Conta Perfil B' and perfil_financeiro_id = %s",
                  (PERFIL_B,))[0][0]
    outra = banco("select id from public.conta_bancaria where nome = 'Conta Pessoal (A)' and perfil_financeiro_id = %s",
                  (PESSOAL,))[0][0]
    inicio = fora_do_perfil_b()
    executar(SimpleNamespace(rpc=rpc, anonimo=anonimo, banco=banco, conectar=conectar, registrar=registrar,
                             em_thread=em_thread, B=PERFIL_B, conta=conta, conta_outro_perfil=outra, categoria=CATEGORIA))
    registrar('20. Registros de outro perfil intactos', fora_do_perfil_b() == inicio,
              'contas bancarias, movimentos, contas, receitas e detalhes de pagamento fora do Perfil B identicos')
    falhas = [n for n, ok in RESULTADOS if not ok]
    print('RESULTADO:', 'OK' if not falhas else f'FALHAS: {falhas}')
    return 1 if falhas else 0


if __name__ == '__main__':
    sys.exit(main())
