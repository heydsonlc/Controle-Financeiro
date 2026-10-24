"""
FIN-MOVIMENTACOES-REAL-1 — cenarios de pagamento de despesa, recebimento de receita, estornos e movimentos do mes
(FIN-MOVIMENTACOES-1), chamados por supabase_movimentacoes_real.py.

Modulo sem acesso proprio a rede ou banco: recebe de quem chama `rpc`, `anonimo`, `banco`, `conectar` e os dados do
perfil (Data API real e banco do Supabase de teste no script real; PostgREST e cluster locais no ensaio), para que o
ensaio local rode este mesmo codigo. So dados FICTICIOS: despesas e receitas criadas aqui pela API do novo aplicativo
(nomes com o marcador, competencia e datas em 03/2040), na conta ctx.conta do perfil de teste ctx.B (atribuido ao
novo aplicativo) e numa conta inativa criada aqui com o marcador. Outros perfis so recebem tentativas negadas.
Saldo conferido depois de cada operacao (por diferenca: o saldo de partida da conta nao importa).
"""
import threading
import uuid
from contextlib import contextmanager
from decimal import Decimal

MARCADOR = '[teste FIN-MOVIMENTACOES-REAL-1]'
MES = '2040-03-01'
Z = Decimal('0.00')


class Cenarios:
    def __init__(self, ctx):
        self.ctx = ctx
        self.delta = Decimal('0.00')  # variacao esperada do saldo da conta de teste

    # --- apoio ---------------------------------------------------------------------------------------------------
    def despesa(self, nome, valor):
        c = self.ctx
        st, r = c.rpc('criar_despesa', {'p_perfil_id': c.B, 'p_chave': str(uuid.uuid4()), 'p_dados': {
            'nome': f'{nome} {MARCADOR}', 'valor': valor, 'categoria_id': c.categoria, 'data_vencimento': '2040-03-10',
            'competencia': MES, 'descricao': '', 'debito_automatico': False}})
        if st != 200:
            raise SystemExit(f'despesa falhou: {st} {r}')
        return r['conta_id']

    def previsao(self, nome, valor):
        c = self.ctx
        st, r = c.rpc('criar_receita', {'p_perfil_id': c.B, 'p_chave': str(uuid.uuid4()), 'p_dados': {
            'nome': f'{nome} {MARCADOR}', 'tipo': 'RENDA_EXTRA', 'valor': valor, 'competencia': MES,
            'data_prevista': '2040-03-15'}})
        if st != 200:
            raise SystemExit(f'receita falhou: {st} {r}')
        return r['previsoes'][0]

    def pagar(self, conta_id, valor, devido=None, conta=None, chave=None, usuario='B', **extra):
        c = self.ctx
        return c.rpc('pagar_despesa', {'p_perfil_id': c.B, 'p_conta_id': conta_id, 'p_chave': chave or str(uuid.uuid4()),
                                       'p_dados': {'conta_bancaria_id': conta or c.conta, 'data_pagamento': '2040-03-12',
                                                   'valor_pago': valor, 'valor_devido': devido or valor, **extra}}, usuario)

    def estornar_despesa(self, conta_id, movimento, chave=None):
        c = self.ctx
        return c.rpc('estornar_pagamento_despesa', {
            'p_perfil_id': c.B, 'p_conta_id': conta_id, 'p_movimento_id': movimento, 'p_chave': chave or str(uuid.uuid4()),
            'p_dados': {'motivo': 'Estorno do teste real', 'data_estorno': '2040-03-14'}})

    def receber(self, orc, valor, falta, conta=None, chave=None, usuario='B', **extra):
        c = self.ctx
        return c.rpc('receber_receita', {'p_perfil_id': c.B, 'p_orcamento_id': orc, 'p_chave': chave or str(uuid.uuid4()),
                                         'p_dados': {'conta_bancaria_id': conta or c.conta, 'data_recebimento': '2040-03-15',
                                                     'valor_recebido': valor, 'falta': falta, **extra}}, usuario)

    def estornar_recebimento(self, realizada, chave=None):
        c = self.ctx
        return c.rpc('estornar_recebimento', {'p_perfil_id': c.B, 'p_realizada_id': realizada,
                                              'p_chave': chave or str(uuid.uuid4()),
                                              'p_dados': {'motivo': 'Estorno do teste real', 'data_estorno': '2040-03-20'}})

    def movs_despesa(self, conta_id):
        return [tuple(x) for x in self.ctx.banco('select tipo, valor, origem, movimento_original_id from '
                                                 'public.movimento_financeiro where conta_id = %s order by id', (conta_id,))]

    def movs_receita(self, orc):
        return [tuple(x) for x in self.ctx.banco(
            'select m.tipo, m.valor, m.origem, m.movimento_original_id from public.movimento_financeiro m '
            'join public.receita_realizada r on r.id = m.receita_realizada_id where r.orcamento_id = %s order by m.id', (orc,))]

    def realizadas(self, orc):
        return self.ctx.banco('select count(*) from public.receita_realizada where orcamento_id = %s', (orc,))[0][0]

    def despesa_estado(self, conta_id):
        return tuple(self.ctx.banco('select status_pagamento, valor from public.conta where id = %s', (conta_id,))[0])

    def situacao_receita(self, orc):
        st, linhas = self.ctx.rpc('receitas_do_mes', {'p_perfil_id': self.ctx.B, 'p_mes': MES})
        return next((l['situacao'] for l in linhas if l['origem'] == 'PREVISAO' and l['id'] == orc), None) if st == 200 else st

    def saldo(self):
        return tuple(self.ctx.banco(
            "select coalesce(cb.saldo_atual, 0), coalesce(cb.saldo_inicial, 0) + coalesce((select sum(case when m.tipo = "
            "'CREDITO' then m.valor else -m.valor end) from public.movimento_financeiro m where m.conta_bancaria_id = cb.id), 0) "
            'from public.conta_bancaria cb where cb.id = %s', (self.ctx.conta,))[0])

    def saldo_ok(self):
        atual, calculado = self.saldo()
        return atual == calculado == self.partida + self.delta

    @staticmethod
    def hint(corpo):
        return corpo.get('hint') if isinstance(corpo, dict) else None

    def paralelo(self, funcoes):
        barreira = threading.Barrier(len(funcoes))
        tarefas = [self.ctx.em_thread(lambda f=f: (barreira.wait(60), f())[1]) for f in funcoes]
        for t, _ in tarefas:
            t.join(240)
        return [r.get('valor') for _, r in tarefas]

    @contextmanager
    def conta_presa(self):
        """Outra transacao segura a conta bancaria (FOR UPDATE): a operacao espera e esgota o lock_timeout."""
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
        self.partida = self.saldo()[1]
        if self.saldo()[0] != self.partida:
            raise SystemExit('saldo_atual da conta de teste diverge dos movimentos antes dos cenarios')
        inativa = c.banco("insert into public.conta_bancaria (perfil_financeiro_id, nome, instituicao, tipo, status, "
                          "saldo_inicial, saldo_atual, cor_display, data_criacao, data_atualizacao) values "
                          "(%s, %s, 'Banco ficticio', 'Conta Corrente', 'INATIVO', 0, 0, '#3b82f6', now(), now()) returning id",
                          (c.B, f'Conta inativa {MARCADOR}'), escrever=True)[0][0]

        # 1. Pagamento integral
        d1 = self.despesa('Aluguel', '800.00')
        st, p1 = self.pagar(d1, '800.00')
        self.delta -= Decimal('800.00') if st == 200 else Z
        reg('1. Pagamento integral de despesa', st == 200 and self.despesa_estado(d1) == ('Pago', Decimal('800.00'))
            and self.movs_despesa(d1) == [('DEBITO', Decimal('800.00'), 'DESPESA', None)] and self.saldo_ok(),
            f'{st}; despesa Paga; 1 debito; saldo {self.saldo()}')

        # 2. Diferenca justificada (sem classificacao: recusado, nada gravado)
        d2 = self.despesa('Energia', '200.00')
        st0, e0 = self.pagar(d2, '210.00', devido='200.00')
        st, _ = self.pagar(d2, '210.00', devido='200.00', tipo_ajuste='JUROS', justificativa='Multa por atraso')
        self.delta -= Decimal('210.00') if st == 200 else Z
        devido = c.banco('select valor_executado from financeiro.pagamento_fatura where fatura_id = %s', (d2,))
        reg('2. Pagamento com diferenca justificada', (st0, self.hint(e0)) == (400, 'AJUSTE_OBRIGATORIO') and st == 200
            and self.despesa_estado(d2) == ('Pago', Decimal('210.00')) and devido == [(Decimal('200.00'),)] and self.saldo_ok(),
            f'sem classificacao {st0}; com JUROS {st}: debito 210,00, devido original 200,00 registrado')

        # 3 e 4. Conta inativa e de outro perfil (despesa e receita)
        d3 = self.despesa('Internet', '100.00')
        o3 = self.previsao('Consultoria', '500.00')
        recusas = [self.pagar(d3, '100.00', conta=inativa), self.pagar(d3, '100.00', conta=c.conta_outro_perfil),
                   self.receber(o3, '500.00', '500.00', conta=inativa), self.receber(o3, '500.00', '500.00', conta=c.conta_outro_perfil)]
        reg('3. Conta bancaria inativa', recusas[0][0] == recusas[2][0] == 400 and 'inativa' in str(recusas[0][1])
            and 'inativa' in str(recusas[2][1]), 'despesa 400 e receita 400; nada gravado')
        reg('4. Conta de outro perfil', recusas[1][0] == recusas[3][0] == 400 and 'nao encontrada neste perfil' in str(recusas[1][1])
            and self.movs_despesa(d3) == [] and self.realizadas(o3) == 0 and self.saldo_ok(), 'despesa 400 e receita 400; nada gravado')

        # 5 e 6. Pagamento duplicado e simultaneo
        chave = str(uuid.uuid4())
        st, a = self.pagar(d3, '100.00', chave=chave)
        st_r, b = self.pagar(d3, '100.00', chave=chave)
        st_n, en = self.pagar(d3, '100.00')
        self.delta -= Decimal('100.00') if st == 200 else Z
        reg('5. Pagamento duplicado', st == st_r == 200 and b.get('repetida') is True and b['movimento_id'] == a['movimento_id']
            and (st_n, self.hint(en)) == (400, 'DESPESA_PAGA') and len(self.movs_despesa(d3)) == 1 and self.saldo_ok(),
            f'mesma chave {st_r} (mesmo debito); outra {st_n} DESPESA_PAGA')
        d6 = self.despesa('Agua', '60.00')
        res = self.paralelo([lambda: self.pagar(d6, '60.00') for _ in range(3)])
        ok = [r for r in res if r[0] == 200]
        self.delta -= Decimal('60.00') * len(ok)
        reg('6. Pagamentos simultaneos', len(ok) == 1 and sorted(self.hint(r[1]) for r in res if r[0] != 200)
            == ['DESPESA_PAGA', 'DESPESA_PAGA'] and len(self.movs_despesa(d6)) == 1 and self.saldo_ok(),
            f'{sorted(r[0] for r in res)}; 1 debito')

        # 7 e 8. Estorno; segundo pagamento e segundo estorno (cada estorno no seu debito; volta ao devido)
        st_e, _ = self.estornar_despesa(d2, self.movs_ids(d2)[0])
        self.delta += Decimal('210.00') if st_e == 200 else Z
        estado7 = self.despesa_estado(d2)
        st_p, p2 = self.pagar(d2, '200.00')
        st_x, ex = self.estornar_despesa(d2, self.movs_ids(d2)[0])  # o 1o de novo
        st_e2, _ = self.estornar_despesa(d2, p2['movimento_id'])
        ids = self.movs_ids(d2)
        reg('7. Estorno de despesa', st_e == 200 and estado7 == ('Pendente', Decimal('200.00')) and self.movs_despesa(d2)[1]
            == ('CREDITO', Decimal('210.00'), 'ESTORNO_DESPESA', ids[0]), 'credito ligado ao debito; volta a Pendente com 200,00')
        reg('8. Segundo pagamento e segundo estorno', st_p == st_e2 == 200 and (st_x, self.hint(ex)) == (400, 'JA_ESTORNADO')
            and [(m[0], m[3]) for m in self.movs_despesa(d2)] == [('DEBITO', None), ('CREDITO', ids[0]), ('DEBITO', None),
                                                                 ('CREDITO', ids[2])]
            and self.despesa_estado(d2)[0] == 'Pendente' and self.saldo_ok(), f'D/C/D/C; o 1o de novo {st_x} JA_ESTORNADO')

        # 9. Recebimento integral
        o9 = self.previsao('Salario', '3000.00')
        st, r9 = self.receber(o9, '3000.00', '3000.00')
        self.delta += Decimal('3000.00') if st == 200 else Z
        reg('9. Recebimento integral', st == 200 and self.situacao_receita(o9) == 'RECEBIDA'
            and self.movs_receita(o9) == [('CREDITO', Decimal('3000.00'), 'RECEITA', None)] and self.saldo_ok(),
            f'{st}; Recebida; 1 credito')

        # 10, 11 e 12. Parcial, complemento ate o integral, acima do previsto com justificativa
        st_a, _ = self.receber(o3, '200.00', '500.00')
        sit_a = self.situacao_receita(o3)
        st_b, _ = self.receber(o3, '300.00', '300.00')
        sit_b = self.situacao_receita(o3)
        st_c0, ec = self.receber(o3, '50.00', '0.00')
        st_c, _ = self.receber(o3, '50.00', '0.00', justificativa='Reajuste pago junto')
        self.delta += sum((Decimal(v) for v, s in (('200.00', st_a), ('300.00', st_b), ('50.00', st_c)) if s == 200), Z)
        acima = c.banco("select count(*) from public.receita_realizada where orcamento_id = %s and observacoes like '[ACIMA%%'",
                        (o3,))[0][0]
        reg('10. Recebimento parcial', st_a == 200 and sit_a == 'PARCIAL', '200 de 500: Parcial, sem justificativa')
        reg('11. Complemento ate o integral', st_b == 200 and sit_b == 'RECEBIDA', 'mais 300: Recebida')
        reg('12. Recebimento acima do previsto', (st_c0, self.hint(ec)) == (400, 'JUSTIFICATIVA_OBRIGATORIA') and st_c == 200
            and acima == 1 and len(self.movs_receita(o3)) == 3 and self.saldo_ok(),
            f'sem justificativa {st_c0}; com justificativa {st_c} (registrada no recebimento)')

        # 13 e 14. Recebimento duplicado e simultaneo
        o13 = self.previsao('Aluguel recebido', '1200.00')
        chave = str(uuid.uuid4())
        st, a = self.receber(o13, '1200.00', '1200.00', chave=chave)
        st_r, b = self.receber(o13, '1200.00', '1200.00', chave=chave)
        st_n, en = self.receber(o13, '1200.00', '1200.00')
        self.delta += Decimal('1200.00') if st == 200 else Z
        reg('13. Recebimento duplicado', st == st_r == 200 and b.get('repetida') is True
            and b['receita_realizada_id'] == a['receita_realizada_id'] and (st_n, self.hint(en)) == (400, 'VALOR_MUDOU')
            and self.realizadas(o13) == 1 and self.saldo_ok(), f'mesma chave {st_r} (mesmo recebimento); outra {st_n} VALOR_MUDOU')
        o14 = self.previsao('Freela', '400.00')
        res = self.paralelo([lambda: self.receber(o14, '400.00', '400.00') for _ in range(3)])
        ok = [r for r in res if r[0] == 200]
        self.delta += Decimal('400.00') * len(ok)
        reg('14. Recebimentos simultaneos', len(ok) == 1 and sorted(self.hint(r[1]) for r in res if r[0] != 200)
            == ['VALOR_MUDOU', 'VALOR_MUDOU'] and self.realizadas(o14) == 1 and self.saldo_ok(),
            f'{sorted(r[0] for r in res)}; 1 recebimento')

        # 15 e 16. Estorno; segundo recebimento e segundo estorno
        st_e, e15 = self.estornar_recebimento(r9['receita_realizada_id'])
        self.delta -= Decimal('3000.00') if st_e == 200 else Z
        sit15 = self.situacao_receita(o9)
        st_x, ex = self.estornar_recebimento(r9['receita_realizada_id'])
        st_2, r16 = self.receber(o9, '3000.00', '3000.00')
        st_e2, _ = self.estornar_recebimento(r16['receita_realizada_id']) if st_2 == 200 else (st_2, None)
        ms = self.movs_receita(o9)
        reg('15. Estorno de recebimento', st_e == 200 and sit15 == 'PREVISTA' and (st_x, self.hint(ex)) == (400, 'JA_ESTORNADO')
            and ms[1] == ('DEBITO', Decimal('3000.00'), 'ESTORNO_RECEITA', e15['movimento_original_id']),
            'debito ligado ao credito; previsao volta a Prevista; repetido JA_ESTORNADO')
        reg('16. Segundo recebimento e segundo estorno', st_2 == st_e2 == 200 and [(m[0], m[2]) for m in ms] == [
            ('CREDITO', 'RECEITA'), ('DEBITO', 'ESTORNO_RECEITA'), ('CREDITO', 'RECEITA'), ('DEBITO', 'ESTORNO_RECEITA')]
            and ms[3][3] == r16['movimento_id'] and self.situacao_receita(o9) == 'PREVISTA' and self.saldo_ok(),
            'C/D/C/D, cada debito no seu credito')

        # 18. Falha no meio (conta presa ate o lock_timeout): nada fica; a chave nao e consumida
        d18, o18 = self.despesa('Seguro', '90.00'), self.previsao('Bonus', '150.00')
        kd, kr = str(uuid.uuid4()), str(uuid.uuid4())
        with self.conta_presa():
            st_fd, _ = self.pagar(d18, '90.00', chave=kd)
            st_fr, _ = self.receber(o18, '150.00', '150.00', chave=kr)
        sem_nada = self.movs_despesa(d18) == [] and self.despesa_estado(d18)[0] == 'Pendente' and self.realizadas(o18) == 0
        st_d, rd = self.pagar(d18, '90.00', chave=kd)
        st_r, rr = self.receber(o18, '150.00', '150.00', chave=kr)
        self.delta += (Decimal('150.00') if st_r == 200 else Z) - (Decimal('90.00') if st_d == 200 else Z)
        reg('18. Falha intermediaria sem operacao parcial', st_fd != 200 and st_fr != 200 and sem_nada and st_d == st_r == 200
            and rd.get('repetida') is not True and rr.get('repetida') is not True and self.realizadas(o18) == 1
            and self.saldo_ok(), f'conta presa: despesa {st_fd}, receita {st_fr}; nada gravado (nem o recebimento); '
            f'mesmas chaves depois: {st_d}/{st_r}')

        # 19. Sem permissao: outro usuario e anonimo (nada gravado)
        antes = (self.movs_despesa(d6), self.realizadas(o14), self.saldo())
        negados = {f: c.rpc(f, a, 'A')[0] for f, a in (
            ('dados_pagamento_despesa', {'p_perfil_id': c.B, 'p_conta_id': d6}),
            ('dados_recebimento_receita', {'p_perfil_id': c.B, 'p_orcamento_id': o14}),
            ('movimentos_do_mes', {'p_perfil_id': c.B, 'p_mes': MES}))}
        negados['pagar_despesa'] = self.pagar(d6, '60.00', usuario='A')[0]
        negados['receber_receita'] = self.receber(o14, '1.00', '0.00', usuario='A')[0]
        anon = {f: c.anonimo(f, a) for f, a in (
            ('pagar_despesa', {'p_perfil_id': c.B, 'p_conta_id': d6, 'p_dados': {}, 'p_chave': str(uuid.uuid4())}),
            ('receber_receita', {'p_perfil_id': c.B, 'p_orcamento_id': o14, 'p_dados': {}, 'p_chave': str(uuid.uuid4())}),
            ('movimentos_do_mes', {'p_perfil_id': c.B, 'p_mes': MES}))}
        internas = {f: c.rpc(f, a)[0] for f, a in (('recebido_da_previsao', {'p_orcamento_id': o14}),
                                                 ('debito_vigente', {'p_conta_id': d6, 'p_origem': 'DESPESA'}),
                                                 ('travar_conta_bancaria', {'p_perfil_id': c.B, 'p_conta_bancaria_id': c.conta}))}
        reg('19. Usuario sem permissao', set(negados.values()) == {403} and set(anon.values()) == {401}
            and all(s != 200 for s in internas.values()) and (self.movs_despesa(d6), self.realizadas(o14), self.saldo()) == antes,
            f'outro usuario {negados}; anonimo {anon}; internas {internas}')

        # 17 e 22. Saldo = movimentos; extrato do mes mostra cada operacao com a origem e o item
        st, ext = c.rpc('movimentos_do_mes', {'p_perfil_id': c.B, 'p_mes': MES})
        meus = [m for m in (ext or {}).get('movimentos', []) if m['conta_bancaria_id'] == c.conta
                and MARCADOR in (m.get('referencia') or '')]
        origens = sorted({m['origem'] for m in meus})
        estornos_ok = all(m['estorno_de'] is not None for m in meus if m['origem'].startswith('ESTORNO_'))
        liquido = sum((Decimal(str(m['valor'])) if m['tipo'] == 'CREDITO' else -Decimal(str(m['valor']))) for m in meus)
        conta_tela = next((x for x in (ext or {}).get('contas', []) if x['id'] == c.conta), {})
        reg('17. Saldo corresponde aos movimentos', self.saldo_ok() and Decimal(str(conta_tela.get('saldo'))) == self.saldo()[1]
            and liquido == self.delta, f'saldo gravado = movimentos = partida {self.delta:+}: {self.saldo()}')
        reg('22. Historico e extrato', st == 200 and origens == ['DESPESA', 'ESTORNO_DESPESA', 'ESTORNO_RECEITA', 'RECEITA']
            and estornos_ok and len(meus) == 18, f'{len(meus)} movimentos do teste no extrato de 03/2040; origens {origens}; '
            'estornos ligados ao original')

    def movs_ids(self, conta_id):
        return [x[0] for x in self.ctx.banco('select id from public.movimento_financeiro where conta_id = %s order by id',
                                             (conta_id,))]


def executar(ctx):
    Cenarios(ctx).executar()
