"""
FIN-PUBLICACAO-PREVIEW-2 — dados FICTICIOS de demonstracao para a previa publicada (Cloudflare Pages) no Supabase de
teste. Nenhum dado pessoal: nao le o gastos.db; nomes com o marcador "(demonstracao)".

Cria um perfil ficticio "Demonstracao (ficticio)" vinculado SOMENTE a conta de avaliacao (CF_EMAIL_A do
.env.e2e-real, a mesma liberada no Cloudflare Access), atribuido ao novo aplicativo (para pagar e receber),
2 contas bancarias e 4 categorias de demonstracao. Depois, com login real dessa conta na Data API, cria pelas
operacoes do proprio aplicativo: 1 cartao com compras, despesas comuns, receitas previstas, 2 pagamentos e 2
recebimentos (os movimentos e saldos saem dessas operacoes). Nada fora do perfil de demonstracao e tocado.

O que foi criado fica em data/demo_preview_2.json (fora do Git) e e o unico alvo do --remover.
Recusa: projeto da Calculadora; perfil de demonstracao ja existente; estado anterior presente.

Uso:
    scripts/supabase_demo_preview_seed.py                       # so mostra o plano (nada e gravado)
    scripts/supabase_demo_preview_seed.py --confirmar           # cria
    scripts/supabase_demo_preview_seed.py --remover [--confirmar]
Nao imprime e-mails completos, senhas, tokens nem a URL do banco.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / 'scripts'))
from dotenv import load_dotenv  # noqa: E402

from supabase_perfis_seed_teste import conectar, mascarar  # noqa: E402
from verificar_exposicao_supabase import PROJETO, PROJETOS_PROIBIDOS, chave_publica_via_cli  # noqa: E402

ESTADO = RAIZ / 'data' / 'demo_preview_2.json'
PERFIL = 'Demonstracao (ficticio)'
SUFIXO = ' (demonstracao)'
CONTAS = [('Conta corrente' + SUFIXO, 'Banco Demo', 'Conta Corrente', 5000), ('Poupanca' + SUFIXO, 'Banco Demo', 'Poupanca', 1500)]
CATEGORIAS = [('Moradia' + SUFIXO, '#2563eb'), ('Alimentacao' + SUFIXO, '#16a34a'), ('Saude' + SUFIXO, '#dc2626'),
              ('Lazer' + SUFIXO, '#9333ea')]


class Api:
    """Data API real com login real da conta de avaliacao (como o navegador)."""

    def __init__(self, email, senha):
        self.origem = f'https://{PROJETO}.supabase.co'
        self.chave, _ = chave_publica_via_cli()
        corpo = self._chamar('/auth/v1/token?grant_type=password', {'email': email, 'password': senha}, autenticado=False)
        self.token = corpo['access_token']

    def _chamar(self, caminho, corpo, autenticado=True):
        req = urllib.request.Request(self.origem + caminho, method='POST', data=json.dumps(corpo).encode())
        req.add_header('apikey', self.chave)
        req.add_header('Content-Type', 'application/json')
        if autenticado:
            req.add_header('Authorization', f'Bearer {self.token}')
            req.add_header('Content-Profile', 'financeiro')
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read() or b'null')
        except urllib.error.HTTPError as exc:
            raise SystemExit(f'Falha em {caminho.split("?")[0]}: {exc.code} {exc.read()[:300]!r}')

    def rpc(self, funcao, corpo):
        return self._chamar(f'/rest/v1/rpc/{funcao}', corpo)


def criar(email, senha):
    conn = conectar()
    try:
        with conn.cursor() as cur:
            cur.execute('select id from auth.users where lower(email) = %s', (email.strip().lower(),))
            linha = cur.fetchone()
            if not linha:
                raise SystemExit(f'Conta de avaliacao ({mascarar(email)}) nao existe no Auth.')
            usuario = str(linha[0])
            cur.execute('select count(*) from public.perfil_financeiro where nome = %s', (PERFIL,))
            if cur.fetchone()[0]:
                raise SystemExit(f'Ja existe o perfil "{PERFIL}": nada feito.')
            cur.execute("insert into public.perfil_financeiro (nome, tipo, cor, avatar, ativo, padrao, created_at, updated_at) "
                        "values (%s, 'PESSOAL', '#0ea5e9', 'DE', true, false, now(), now()) returning id", (PERFIL,))
            perfil = cur.fetchone()[0]
            cur.execute("insert into financeiro.perfil_acesso (user_id, perfil_financeiro_id, papel, pode_gerir) "
                        "values (%s, %s, 'TITULAR', true)", (usuario, perfil))
            cur.execute("select financeiro.definir_gerador_recorrencia(%s, 'NOVO', 'FIN-PUBLICACAO-PREVIEW-2', "
                        "'Perfil ficticio de demonstracao')", (perfil,))
            contas = []
            for nome, instituicao, tipo, saldo in CONTAS:
                cur.execute("insert into public.conta_bancaria (perfil_financeiro_id, nome, instituicao, tipo, status, cor_display, "
                            "saldo_inicial, saldo_atual, data_criacao, data_atualizacao) "
                            "values (%s, %s, %s, %s, 'ATIVO', '#3b82f6', %s, %s, now(), now()) returning id",
                            (perfil, nome, instituicao, tipo, saldo, saldo))
                contas.append(cur.fetchone()[0])
            categorias = []
            for nome, cor in CATEGORIAS:
                cur.execute('insert into public.categoria (nome, cor, ativo, sistemica, bloquear_edicao, bloquear_exclusao) '
                            'values (%s, %s, true, false, false, false) returning id', (nome, cor))
                categorias.append(cur.fetchone()[0])
        conn.commit()
    finally:
        conn.close()
    estado = {'perfil': perfil, 'usuario': usuario, 'contas': contas, 'categorias': categorias}
    ESTADO.write_text(json.dumps(estado, indent=1), encoding='utf-8')  # antes das operacoes: o --remover sempre acha

    api = Api(email, senha)
    moradia, alimentacao, saude, lazer = categorias
    corrente, poupanca = contas

    def chave():
        return str(uuid.uuid4())

    cartao = api.rpc('criar_cartao', {'p_perfil_id': perfil, 'p_chave': chave(), 'p_dados': {
        'nome': 'Cartao' + SUFIXO, 'dia_fechamento': 3, 'dia_vencimento': 10, 'limite_credito': '3000.00',
        'fechamento_confirmado': True}})['cartao_id']
    for descricao, valor, data, mes, parcelas, cat in (
            ('Supermercado', '412.35', '2026-09-28', '2026-10-01', 1, alimentacao),
            ('Farmacia', '89.90', '2026-10-01', '2026-10-01', 1, saude),
            ('Restaurante', '156.00', '2026-10-08', '2026-11-01', 1, lazer),
            ('Geladeira nova', '2400.00', '2026-10-12', '2026-11-01', 6, moradia),
            ('Cinema', '64.00', '2026-10-18', '2026-11-01', 1, lazer)):
        api.rpc('criar_compra', {'p_perfil_id': perfil, 'p_chave': chave(), 'p_dados': {
            'cartao_id': cartao, 'descricao': descricao + SUFIXO, 'valor': valor, 'total_parcelas': parcelas,
            'data_compra': data, 'mes_fatura': mes, 'categoria_id': cat}})
    despesas = {}
    for nome, valor, venc, cat in (('Aluguel', '1800.00', '2026-10-05', moradia), ('Condominio', '420.00', '2026-10-10', moradia),
                                   ('Energia', '238.47', '2026-10-15', moradia), ('Internet', '119.90', '2026-10-20', moradia),
                                   ('Plano de saude', '640.00', '2026-10-25', saude), ('Academia', '99.00', '2026-10-28', lazer)):
        despesas[nome] = api.rpc('criar_despesa', {'p_perfil_id': perfil, 'p_chave': chave(), 'p_dados': {
            'nome': nome + SUFIXO, 'valor': valor, 'categoria_id': cat, 'data_vencimento': venc, 'competencia': '2026-10-01',
            'descricao': '', 'debito_automatico': False}})['conta_id']
    receitas = {}
    for nome, tipo, valor, data in (('Salario', 'SALARIO_FIXO', '7500.00', '2026-10-05'),
                                    ('Aluguel recebido', 'ALUGUEL', '1200.00', '2026-10-10'),
                                    ('Freela', 'RENDA_EXTRA', '900.00', '2026-10-22'),
                                    ('Rendimento', 'RENDIMENTO_FINANCEIRO', '48.30', '2026-10-30')):
        receitas[nome] = api.rpc('criar_receita', {'p_perfil_id': perfil, 'p_chave': chave(), 'p_dados': {
            'nome': nome + SUFIXO, 'tipo': tipo, 'valor': valor, 'competencia': '2026-10-01',
            'data_prevista': data}})['previsoes'][0]
    pagos = [api.rpc('pagar_despesa', {'p_perfil_id': perfil, 'p_conta_id': despesas[n], 'p_chave': chave(), 'p_dados': {
        'conta_bancaria_id': corrente, 'data_pagamento': d, 'valor_pago': v, 'valor_devido': v}})
        for n, v, d in (('Aluguel', '1800.00', '2026-10-05'), ('Condominio', '420.00', '2026-10-10'))]
    recebidos = [api.rpc('receber_receita', {'p_perfil_id': perfil, 'p_orcamento_id': receitas[n], 'p_chave': chave(), 'p_dados': {
        'conta_bancaria_id': c, 'data_recebimento': d, 'valor_recebido': v, 'falta': f}})
        for n, v, f, d, c in (('Salario', '7500.00', '7500.00', '2026-10-05', corrente),
                              ('Aluguel recebido', '600.00', '1200.00', '2026-10-11', poupanca))]
    estado.update({'cartao': cartao, 'despesas': despesas, 'receitas': receitas,
                   'movimentos': [x['movimento_id'] for x in pagos + recebidos]})
    ESTADO.write_text(json.dumps(estado, indent=1), encoding='utf-8')
    return estado


def remover(confirmar):
    estado = json.loads(ESTADO.read_text(encoding='utf-8'))
    perfil = estado['perfil']
    conn = conectar()
    try:
        with conn.cursor() as cur:
            cur.execute('select nome from public.perfil_financeiro where id = %s', (perfil,))
            linha = cur.fetchone()
            if not linha or linha[0] != PERFIL:
                raise SystemExit('O perfil do estado nao e o perfil de demonstracao: nada removido.')
            cur.execute('select id from public.item_despesa where perfil_financeiro_id = %s', (perfil,))
            itens = [r[0] for r in cur.fetchall()]
            comandos = [
                ('movimentos', 'delete from public.movimento_financeiro where conta_bancaria_id = any(%s)', [estado['contas']]),
                ('recebimentos', 'delete from public.receita_realizada where perfil_financeiro_id = %s', [perfil]),
                ('previsoes', 'delete from public.receita_orcamento where perfil_financeiro_id = %s', [perfil]),
                ('fontes', 'delete from public.item_receita where perfil_financeiro_id = %s', [perfil]),
                ('identidades', 'delete from financeiro.recorrencia_competencia where item_despesa_id = any(%s)', [itens]),
                ('compras', 'delete from public.lancamento_agregado where cartao_id = any(%s) or perfil_financeiro_id = %s',
                 [itens, perfil]),
                ('contas', 'delete from public.conta where perfil_financeiro_id = %s or item_despesa_id = any(%s)', [perfil, itens]),
                ('configs_cartao', 'delete from public.config_agregador where item_despesa_id = any(%s)', [itens]),
                ('itens', 'delete from public.item_despesa where id = any(%s)', [itens]),
                ('chaves', 'delete from financeiro.operacao_despesa where perfil_financeiro_id = %s', [perfil]),
                ('chaves_receita', 'delete from financeiro.operacao_receita where perfil_financeiro_id = %s', [perfil]),
                ('chaves_cartao', 'delete from financeiro.operacao_cartao where perfil_financeiro_id = %s', [perfil]),
                ('execucoes', 'delete from financeiro.geracao_execucao where perfil_financeiro_id = %s', [perfil]),
                ('gerador', 'delete from financeiro.gerador_recorrencia where perfil_financeiro_id = %s', [perfil]),
                ('historico_gerador', 'delete from financeiro.gerador_recorrencia_historico where perfil_financeiro_id = %s',
                 [perfil]),
                ('vinculos', 'delete from financeiro.perfil_acesso where perfil_financeiro_id = %s', [perfil]),
                ('contas_bancarias', 'delete from public.conta_bancaria where id = any(%s) and nome like %s',
                 [estado['contas'], '%' + SUFIXO]),
                ('categorias', 'delete from public.categoria where id = any(%s) and nome like %s',
                 [estado['categorias'], '%' + SUFIXO]),
                ('perfil', 'delete from public.perfil_financeiro where id = %s and nome = %s', [perfil, PERFIL]),
            ]
            removidos = {}
            for rotulo, sql, params in comandos:
                cur.execute(sql, params)
                removidos[rotulo] = cur.rowcount
            print('Removidos:', removidos)
        if confirmar:
            conn.commit()
            ESTADO.unlink()
            print('CONFIRMADO: dados de demonstracao removidos.')
        else:
            conn.rollback()
            print('SIMULACAO: nada foi gravado (use --confirmar).')
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--remover', action='store_true')
    parser.add_argument('--confirmar', action='store_true')
    args = parser.parse_args()
    if PROJETO in PROJETOS_PROIBIDOS:
        raise SystemExit('Projeto proibido.')
    if args.remover:
        return remover(args.confirmar)
    if ESTADO.exists():
        raise SystemExit('Ja existe estado de demonstracao: remova antes de criar de novo.')
    load_dotenv(RAIZ / '.env.e2e-real', override=False, encoding='utf-8-sig')
    email, senha = os.environ.get('CF_EMAIL_A'), os.environ.get('CF_SENHA_A')
    if not email or not senha:
        raise SystemExit('CF_EMAIL_A/CF_SENHA_A ausentes no .env.e2e-real.')
    if not args.confirmar:
        print(f'PLANO (nada gravado): perfil "{PERFIL}" so para {mascarar(email)}, 2 contas, 4 categorias, 1 cartao com 5 '
              'compras, 6 despesas, 4 receitas, 2 pagamentos e 2 recebimentos. Use --confirmar.')
        return 0
    estado = criar(email, senha)
    print(f'CRIADO: perfil {estado["perfil"]} ("{PERFIL}") so para {mascarar(email)}; contas {estado["contas"]}; '
          f'cartao {estado["cartao"]}; {len(estado["despesas"])} despesas; {len(estado["receitas"])} receitas; '
          f'{len(estado["movimentos"])} movimentos de pagamento/recebimento. Estado: data/demo_preview_2.json')
    return 0


if __name__ == '__main__':
    sys.exit(main())
