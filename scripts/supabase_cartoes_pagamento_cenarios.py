"""
FIN-CARTOES-PAGAMENTO-REAL-1 — cenarios de pagamento e estorno de fatura (FIN-CARTOES-PAGAMENTO-1), chamados por
supabase_cartoes_pagamento_real.py.

Modulo sem acesso proprio a rede ou banco: recebe de quem chama `rpc`, `anonimo`, `banco`, o processo Flask e os
dados do perfil (Data API real e banco do Supabase de teste no script real; PostgREST e cluster locais no ensaio),
para que o ensaio local rode este mesmo codigo. So dados FICTICIOS: escreve apenas no perfil de teste (ctx.B,
atribuido ao novo aplicativo), num cartao criado aqui (compras so em 2039) e na conta ctx.conta; a conta inativa e
criada aqui com o marcador. Outros perfis so recebem tentativas negadas. Saldos e movimentos sao conferidos depois de
cada operacao (deltas: o saldo de partida da conta nao importa).
"""
import threading
import time
import uuid
from contextlib import contextmanager
from decimal import Decimal

MARCADOR = '[teste FIN-CARTOES-PAGAMENTO-REAL-1]'
D0 = Decimal('0.00')


class Cenarios:
    def __init__(self, ctx):
        self.ctx = ctx
        self.cartao = None
        self.pagos = Decimal('0.00')  # soma dos pagamentos vigentes (o que a conta deve ter perdido)

    # --- leitura e escrita ---------------------------------------------------------------------------------------
    def compra(self, mes, valor, descricao):
        c = self.ctx
        st, r = c.rpc('criar_compra', {'p_perfil_id': c.B, 'p_chave': str(uuid.uuid4()), 'p_dados': {
            'cartao_id': self.cartao, 'descricao': f'{descricao} {MARCADOR}', 'valor': valor, 'total_parcelas': 1,
            'data_compra': mes[:8] + '05', 'mes_fatura': mes, 'categoria_id': c.categoria}})
        if st != 200:
            raise SystemExit(f'compra falhou: {st} {r}')
        return self.fatura(mes)

    def fatura(self, mes):
        return self.ctx.banco('select id from public.conta where is_fatura_cartao and item_despesa_id = %s '
                              'and cartao_competencia = %s', (self.cartao, mes))[0][0]

    def pagar(self, fatura, valor, visto=None, conta=None, chave=None, usuario='B', **extra):
        c = self.ctx
        dados = {'conta_bancaria_id': conta or c.conta, 'data_pagamento': '2039-12-10', 'valor_pago': valor,
                 'valor_executado': visto or valor, **extra}
        return c.rpc('pagar_fatura', {'p_perfil_id': c.B, 'p_fatura_id': fatura, 'p_dados': dados,
                                      'p_chave': chave or str(uuid.uuid4())}, usuario)

    def estornar(self, fatura, movimento, chave=None, usuario='B', motivo='Estorno do teste real'):
        c = self.ctx
        return c.rpc('estornar_pagamento_fatura', {
            'p_perfil_id': c.B, 'p_fatura_id': fatura, 'p_movimento_id': movimento,
            'p_dados': {'motivo': motivo, 'data_estorno': '2039-12-15'}, 'p_chave': chave or str(uuid.uuid4())}, usuario)

    def dados(self, fatura, usuario='B'):
        return self.ctx.rpc('dados_pagamento_fatura', {'p_perfil_id': self.ctx.B, 'p_fatura_id': fatura}, usuario)

    def movs(self, fatura):
        return [tuple(x) for x in self.ctx.banco(
            'select tipo, valor, origem, movimento_original_id from public.movimento_financeiro '
            'where conta_id = %s or fatura_id = %s order by id', (fatura, fatura))]

    def situacao(self, fatura):
        return tuple(self.ctx.banco('select status_pagamento, valor, valor_executado, status_fatura, valor_consolidado '
                                    'from public.conta where id = %s', (fatura,))[0])

    def saldo(self, conta=None):
        """(saldo_atual gravado, saldo pelos movimentos)."""
        return tuple(self.ctx.banco(
            "select coalesce(cb.saldo_atual, 0), coalesce(cb.saldo_inicial, 0) + coalesce((select sum(case when m.tipo = "
            "'CREDITO' then m.valor else -m.valor end) from public.movimento_financeiro m where m.conta_bancaria_id = cb.id), 0) "
            'from public.conta_bancaria cb where cb.id = %s', (conta or self.ctx.conta,))[0])

    def saldo_ok(self):
        """Saldo gravado = saldo pelos movimentos = partida - pagamentos vigentes do teste."""
        atual, calculado = self.saldo()
        return atual == calculado == self.partida - self.pagos

    @staticmethod
    def hint(corpo):
        return corpo.get('hint') if isinstance(corpo, dict) else None

    @contextmanager
    def conta_presa(self):
        """Outra transacao segura a conta bancaria (FOR UPDATE): o pagamento espera e esgota o lock_timeout."""
        conn = self.ctx.conectar()
        conn.autocommit = False  # a trava precisa durar ate o rollback abaixo
        try:
            with conn.cursor() as cur:
                cur.execute('select 1 from public.conta_bancaria where id = %s for update', (self.ctx.conta,))
                yield
        finally:
            conn.rollback()
            conn.close()

    # --- cenarios --------------------------------------------------------------------------------------------------
    def executar(self):
        c, reg = self.ctx, self.ctx.registrar
        st, r = c.rpc('criar_cartao', {'p_perfil_id': c.B, 'p_chave': str(uuid.uuid4()), 'p_dados': {
            'nome': f'Cartao Pagamento {MARCADOR}', 'dia_fechamento': 3, 'dia_vencimento': 10}})
        if st != 200:
            raise SystemExit(f'cartao falhou: {st} {r}')
        self.cartao = r['cartao_id']
        self.partida = self.saldo()[1]
        if self.saldo()[0] != self.partida:
            raise SystemExit('saldo_atual da conta de teste diverge dos movimentos antes dos cenarios')

        # 1. Pagamento integral
        f1 = self.compra('2039-01-01', '100.00', 'Integral')
        st, p1 = self.pagar(f1, '100.00')
        self.pagos += Decimal('100.00') if st == 200 else D0
        reg('1. Pagamento integral', st == 200 and self.situacao(f1)[:3] == ('Pago', Decimal('100.00'), Decimal('100.00'))
            and self.movs(f1) == [('DEBITO', Decimal('100.00'), 'FATURA', None)] and self.saldo_ok(),
            f'{st}; fatura Paga 100,00; 1 debito; saldo {self.saldo()}')

        # 2. Juros justificados (sem justificativa: recusado, nada gravado)
        f2 = self.compra('2039-02-01', '200.00', 'Juros')
        st0, e0 = self.pagar(f2, '215.00', visto='200.00')
        st, p2 = self.pagar(f2, '215.00', visto='200.00', tipo_ajuste='JUROS', justificativa='Pago com atraso')
        self.pagos += Decimal('215.00') if st == 200 else D0
        reg('2. Pagamento com juros', (st0, self.hint(e0)) == (400, 'AJUSTE_OBRIGATORIO') and st == 200
            and self.situacao(f2)[:3] == ('Pago', Decimal('215.00'), Decimal('200.00'))
            and self.movs(f2) == [('DEBITO', Decimal('215.00'), 'FATURA', None)] and self.saldo_ok(),
            f'sem justificativa {st0} {self.hint(e0)}; com JUROS {st}: debito 215,00, executado 200,00')

        # 3. Desconto: quitacao integral justificada
        f3 = self.compra('2039-03-01', '300.00', 'Desconto')
        st, _ = self.pagar(f3, '290.00', visto='300.00', tipo_ajuste='DESCONTO', justificativa='Desconto do banco')
        self.pagos += Decimal('290.00') if st == 200 else D0
        _, d3 = self.dados(f3)
        reg('3. Pagamento com desconto', st == 200 and self.situacao(f3)[0] == 'Pago' and d3['pode_pagar'] is False
            and self.movs(f3) == [('DEBITO', Decimal('290.00'), 'FATURA', None)] and self.saldo_ok(),
            f'{st}; quitada com 290,00 (executado 300,00); nada pendente')

        # 4 e 5. Conta inativa (criada aqui, com o marcador) e conta de outro perfil
        f4 = self.compra('2039-04-01', '50.00', 'Contas recusadas')
        inativa = c.banco("insert into public.conta_bancaria (perfil_financeiro_id, nome, instituicao, tipo, status, "
                          "saldo_inicial, saldo_atual, cor_display, data_criacao, data_atualizacao) values "
                          "(%s, %s, 'Banco ficticio', 'Conta Corrente', 'INATIVO', 0, 0, '#3b82f6', now(), now()) returning id",
                          (c.B, f'Conta inativa {MARCADOR}'), escrever=True)[0][0]
        st_i, e_i = self.pagar(f4, '50.00', conta=inativa)
        st_o, e_o = self.pagar(f4, '50.00', conta=c.conta_outro_perfil)
        reg('4. Conta inativa', st_i == 400 and 'inativa' in str(e_i) and self.movs(f4) == [], f'{st_i}; nada gravado')
        reg('5. Conta de outro perfil', st_o == 400 and 'nao encontrada neste perfil' in str(e_o)
            and self.situacao(f4)[0] == 'Pendente' and self.movs(f4) == [] and self.saldo_ok(), f'{st_o}; nada gravado')

        # 6. Mesma solicitacao repetida; outra solicitacao para fatura paga
        chave = str(uuid.uuid4())
        st, p6 = self.pagar(f4, '50.00', chave=chave)
        st_r, r6 = self.pagar(f4, '50.00', chave=chave)
        st_n, e6 = self.pagar(f4, '50.00')
        self.pagos += Decimal('50.00') if st == 200 else D0
        reg('6. Pagamento duplicado', st == st_r == 200 and r6.get('repetida') is True
            and r6['movimento_id'] == p6['movimento_id'] and (st_n, self.hint(e6)) == (400, 'FATURA_PAGA')
            and len(self.movs(f4)) == 1 and self.saldo_ok(), f'repetida {st_r} (mesmo debito); outra {st_n} FATURA_PAGA')

        # 7. Pagamentos simultaneos (chaves diferentes)
        f7 = self.compra('2039-05-01', '70.00', 'Simultaneos')
        res = self.paralelo([lambda: self.pagar(f7, '70.00') for _ in range(3)])
        ok = [r for r in res if r[0] == 200]
        self.pagos += Decimal('70.00') * len(ok)
        reg('7. Pagamentos simultaneos', len(ok) == 1 and sorted(self.hint(r[1]) for r in res if r[0] != 200)
            == ['FATURA_PAGA', 'FATURA_PAGA'] and len(self.movs(f7)) == 1 and self.saldo_ok(),
            f'{sorted(r[0] for r in res)}; 1 debito')

        # 8. Falha no meio (conta bancaria presa por outra transacao ate o lock_timeout): nada fica; a chave nao e
        # consumida e a mesma solicitacao conclui depois.
        f8 = self.compra('2039-06-01', '80.00', 'Rollback')
        chave = str(uuid.uuid4())
        with self.conta_presa():
            st_f, _ = self.pagar(f8, '80.00', chave=chave)
        sem_nada = self.situacao(f8)[0] == 'Pendente' and self.movs(f8) == [] and self.saldo_ok()
        st_d, r8 = self.pagar(f8, '80.00', chave=chave)
        self.pagos += Decimal('80.00') if st_d == 200 else D0
        reg('8. Falha com rollback', st_f != 200 and sem_nada and st_d == 200 and r8.get('repetida') is not True
            and len(self.movs(f8)) == 1 and self.saldo_ok(),
            f'conta presa: {st_f}, nada gravado; mesma chave depois: {st_d} (1 debito)')

        # 9 e 10. Estorno e estorno repetido (fatura do cenario 1)
        chave = str(uuid.uuid4())
        st, e9 = self.estornar(f1, p1['movimento_id'], chave=chave)
        self.pagos -= Decimal('100.00') if st == 200 else D0
        st_r, r10 = self.estornar(f1, p1['movimento_id'], chave=chave)
        st_n, e10 = self.estornar(f1, p1['movimento_id'])
        reg('9. Estorno', st == 200 and self.situacao(f1)[0] == 'Pendente' and self.movs(f1) == [
            ('DEBITO', Decimal('100.00'), 'FATURA', None),
            ('CREDITO', Decimal('100.00'), 'ESTORNO_FATURA', p1['movimento_id'])] and self.saldo_ok(),
            f'{st}; credito compensatorio ligado ao debito; fatura Pendente')
        reg('10. Estorno duplicado', st_r == 200 and r10.get('repetida') is True and (st_n, self.hint(e10)) == (400, 'NAO_PAGA')
            and len(self.movs(f1)) == 2 and self.saldo_ok(), f'repetido {st_r} (mesmo credito); outro {st_n} NAO_PAGA')

        # 11. Pagar, estornar, pagar e estornar de novo (o defeito do Flask nao se repete)
        f11 = self.compra('2039-07-01', '90.00', 'Sequencia')
        _, a = self.pagar(f11, '90.00')
        self.estornar(f11, a['movimento_id'])
        st_b, b = self.pagar(f11, '95.00', visto='90.00', tipo_ajuste='JUROS', justificativa='Multa')
        st_v, ev = self.estornar(f11, a['movimento_id'])
        st_e, _ = self.estornar(f11, b['movimento_id'])
        ms = self.movs(f11)
        reg('11. Pagar, estornar, pagar e estornar', st_b == 200 and (st_v, self.hint(ev)) == (400, 'JA_ESTORNADO')
            and st_e == 200 and [(m[0], m[1], m[3]) for m in ms] == [
                ('DEBITO', Decimal('90.00'), None), ('CREDITO', Decimal('90.00'), a['movimento_id']),
                ('DEBITO', Decimal('95.00'), None), ('CREDITO', Decimal('95.00'), b['movimento_id'])]
            and self.situacao(f11)[0] == 'Pendente' and self.saldo_ok(),
            f'D/C/D/C, cada credito no seu debito; o 1o de novo {st_v} JA_ESTORNADO')

        # 12. Compra do Flask em andamento (travas de cartao e fatura) durante o pagamento: o pagamento espera, ve o
        # total novo e nao paga o antigo; pago depois com o total certo.
        f12 = self.compra('2039-08-01', '100.00', 'Concorrente')
        pasta = c.pasta('f12')
        fl = c.flask(pasta, 'fc', acao='compra', pausa='antes_do_commit', dados={
            'cartao_id': self.cartao, 'categoria_id': c.categoria, 'descricao': f'Compra Flask {MARCADOR}',
            'valor': '25.00', 'data_compra': '2039-08-06', 'mes_fatura': '2039-08-01', 'total_parcelas': 1})
        c.aguardar(pasta, ['fc_inseriu'], [fl])
        tarefa, resposta = c.em_thread(lambda: self.pagar(f12, '100.00'))
        time.sleep(3)
        esperou = tarefa.is_alive()
        c.liberar(pasta, 'inseriu')
        fl.resultado()
        tarefa.join(120)
        st_x, ex = resposta['valor']
        _, d12 = self.dados(f12)
        novo = Decimal(str(d12['fatura']['valor_executado']))
        st, _ = self.pagar(f12, f'{novo:.2f}')
        self.pagos += novo if st == 200 else D0
        reg('12. Compra concorrente ao pagamento', esperou and (st_x, self.hint(ex)) == (400, 'EXECUTADO_MUDOU')
            and novo == Decimal('125.00') and st == 200 and self.movs(f12) == [('DEBITO', Decimal('125.00'), 'FATURA', None)]
            and self.saldo_ok(), f'pagamento esperou a compra do Flask ({esperou}) e recusou o total antigo ({st_x}); '
            f'pago com {novo}')

        # 13. Fatura consolidada (como a consolidacao do Flask) paga e estornada: a consolidacao fica
        f13 = self.compra('2039-09-01', '110.00', 'Consolidada')
        c.banco("update public.conta set status_fatura = 'FECHADA', valor_consolidado = valor_executado, "
                'data_consolidacao = now() where id = %s', (f13,), escrever=True)
        consolidada = self.situacao(f13)[3:]
        st, p13 = self.pagar(f13, '110.00')
        apos_pagar = self.situacao(f13)
        st_e, _ = self.estornar(f13, p13['movimento_id'])
        apos_estorno = self.situacao(f13)
        st_c, ec = c.rpc('criar_compra', {'p_perfil_id': c.B, 'p_chave': str(uuid.uuid4()), 'p_dados': {
            'cartao_id': self.cartao, 'descricao': f'Na consolidada {MARCADOR}', 'valor': '1.00', 'total_parcelas': 1,
            'data_compra': '2039-09-06', 'mes_fatura': '2039-09-01', 'categoria_id': c.categoria}})
        reg('13. Fatura consolidada paga e estornada', consolidada == ('FECHADA', Decimal('110.00')) and st == st_e == 200
            and apos_pagar[0] == 'Pago' and apos_pagar[3:] == consolidada
            and apos_estorno[0] == 'Pendente' and apos_estorno[3:] == consolidada
            and (st_c, self.hint(ec)) == (400, 'CONSOLIDADA') and self.saldo_ok(),
            'FECHADA e total consolidado iguais depois de pagar e de estornar; compra sem confirmacao: CONSOLIDADA')

        # 14. Isolamento: outro usuario e anonimo (nada gravado)
        antes = (self.movs(f7), self.situacao(f7))
        f7_mov = self.movs(f7)
        vigente = [m for m in (self.dados(f7)[1] or {}).get('pagamentos', []) if m['vigente']]
        negados = {'dados': self.dados(f7, usuario='A')[0], 'pagar': self.pagar(f12, '1.00', usuario='A')[0],
                   'estornar': self.estornar(f7, vigente[0]['movimento_id'] if vigente else 0, usuario='A')[0]}
        anon = {f: c.anonimo(f, corpo) for f, corpo in (
            ('dados_pagamento_fatura', {'p_perfil_id': c.B, 'p_fatura_id': f7}),
            ('pagar_fatura', {'p_perfil_id': c.B, 'p_fatura_id': f7, 'p_dados': {}, 'p_chave': str(uuid.uuid4())}),
            ('estornar_pagamento_fatura', {'p_perfil_id': c.B, 'p_fatura_id': f7, 'p_movimento_id': 0, 'p_dados': {},
                                           'p_chave': str(uuid.uuid4())}))}
        internas = {f: c.rpc(f, corpo)[0] for f, corpo in (('executado_fatura', {'p_fatura_id': f7}),
                                                         ('saldo_da_conta', {'p_conta_bancaria_id': c.conta}),
                                                         ('pagamento_vigente', {'p_fatura_id': f7}))}
        reg('14. Isolamento entre usuarios', set(negados.values()) == {403} and set(anon.values()) == {401}
            and all(s != 200 for s in internas.values()) and (self.movs(f7), self.situacao(f7)) == antes and f7_mov,
            f'outro usuario {negados}; anonimo {anon}; internas {internas}')

        # 15. Saldos e movimentos: conta de teste = partida - pagamentos vigentes; cada fatura conta a mesma historia
        coerentes = []
        for f in (f1, f2, f3, f4, f7, f8, f11, f12, f13):
            ms, sit = self.movs(f), self.situacao(f)
            liquido = sum((m[1] if m[0] == 'DEBITO' else -m[1]) for m in ms)
            coerentes.append(liquido == sit[1] if sit[0] == 'Pago' else liquido == 0)
        reg('15. Saldos e movimentos', all(coerentes) and self.saldo_ok(),
            f'saldo gravado = pelos movimentos = partida - {self.pagos}: {self.saldo()}; 9 faturas coerentes: {all(coerentes)}')

    def paralelo(self, funcoes):
        barreira = threading.Barrier(len(funcoes))
        tarefas = [self.ctx.em_thread(lambda f=f: (barreira.wait(60), f())[1]) for f in funcoes]
        for t, _ in tarefas:
            t.join(240)
        return [r.get('valor') for _, r in tarefas]


def executar(ctx):
    Cenarios(ctx).executar()
