"""
FIN-CARTOES-FECHAMENTO-REAL-1 — cenarios de fechamento automatico e de recorrencia rejeitada por fatura consolidada
(FIN-CARTOES-RECORRENCIA-PENDENCIA-1), chamados por supabase_cartoes_real.py depois do cenario 17 (D6).

Modulo sem acesso proprio a rede ou banco: recebe `rpc`, `anonimo` e `banco` de quem chama (Data API real e banco do
Supabase de teste no script real; PostgREST e cluster locais no ensaio), para que o ensaio local rode este mesmo codigo.
So dados FICTICIOS: escreve apenas no "Perfil B" temporario (cartoes recebidos/criados aqui, meses 2036-06 a 2037-01);
Pessoal e Empresa so recebem tentativas negadas. A recorrencia criada aqui e removida pela limpeza dos testes reais
(item acima da marca; a ocorrencia vai junto).
"""
import uuid
from datetime import date
from decimal import Decimal

D = date
NOME_RECORRENCIA = 'Recorrente Real [teste FIN-CARTOES-REAL-1]'


def _comprar(ctx, cartao_id, descricao, data_compra, valor, mes=None):
    dados = {'cartao_id': cartao_id, 'descricao': descricao, 'valor': valor, 'total_parcelas': 1,
             'data_compra': data_compra, 'categoria_id': ctx.MORADIA}
    if mes:
        dados['mes_fatura'] = mes
    return ctx.rpc('criar_compra', {'p_perfil_id': ctx.B, 'p_dados': dados, 'p_chave': str(uuid.uuid4())})


def _meses_da_compra(ctx, resposta):
    status, corpo = resposta
    if status != 200:
        return None
    return [tuple(x) for x in ctx.banco('select mes_fatura, mes_fatura_sugerido from public.lancamento_agregado '
                                        'where compra_id = %s order by numero_parcela', (corpo['compra_id'],))]


def fechamento_automatico(ctx):
    """17a. A competencia sugerida segue o fechamento confirmado do cartao; sem mes informado, ela decide."""
    cf = ctx.cartao('Cartao Real Fechamento', 10, 3, fechamento_confirmado=True)
    cn = ctx.cartao('Cartao Real Sem Fechamento', 10, 3)

    def sugerir(cartao_id, data_compra, usuario='B'):
        return ctx.rpc('sugerir_competencia', {'p_perfil_id': ctx.B, 'p_cartao_id': cartao_id,
                                               'p_data_compra': data_compra}, usuario)

    # Fecha dia 3 e vence dia 10; regra padrao PROXIMO (compra no dia do fechamento vai para o ciclo seguinte).
    esperado = {'2036-06-02': '2036-06-01', '2036-06-03': '2036-07-01', '2036-06-04': '2036-07-01',
                '2036-12-20': '2037-01-01'}
    sugeridas = {d: (lambda r: r[1].get('competencia') if r[0] == 200 else r[0])(sugerir(cf, d)) for d in esperado}
    s_nc, nc = sugerir(cn, '2036-06-02')
    pelo_fechamento = _meses_da_compra(ctx, _comprar(ctx, cf, 'Pelo fechamento', '2036-06-04', '10.00'))
    informado = _meses_da_compra(ctx, _comprar(ctx, cf, 'Mes informado', '2036-06-04', '10.00', mes='2036-06-01'))
    s_sem, e_sem = _comprar(ctx, cn, 'Sem fechamento confirmado', '2036-06-04', '10.00')
    s_outro = sugerir(cf, '2036-06-02', usuario='A')[0]  # A sem vinculo com o Perfil B
    ctx.registrar(
        '17a. Fechamento automatico (competencia sugerida)',
        sugeridas == esperado and s_nc == 200 and nc.get('competencia') is None
        and nc.get('situacao') == 'NAO_CONFIRMADO'
        and pelo_fechamento == [(D(2036, 7, 1), D(2036, 7, 1))] and informado == [(D(2036, 6, 1), D(2036, 7, 1))]
        and s_sem == 400 and isinstance(e_sem, dict) and e_sem.get('hint') == 'SEM_SUGESTAO' and s_outro == 403,
        f'sugestoes {sugeridas}; nao confirmado: {nc.get("situacao") if isinstance(nc, dict) else s_nc}; sem mes -> '
        f'{pelo_fechamento}; mes informado (usuario decide, sugestao auditada) -> {informado}; sem fechamento e sem mes '
        f'{s_sem}; A no Perfil B {s_outro}')


def recorrencia_rejeitada(ctx):
    """17b. Recorrencia no cartao com a fatura de destino consolidada: nada e lancado (D6, D5), a ocorrencia persiste
    (uma por recorrencia + competencia), novas tentativas so contam e a dispensa do aviso e auditavel e idempotente."""
    B, c10 = ctx.B, ctx.c10

    def consolidar(mes):
        st, corpo = _comprar(ctx, c10, f'Consolidada {mes[:7]}', mes[:8] + '05', '30.00', mes=mes)
        if st != 200:
            raise SystemExit(f'compra para consolidar falhou: {st} {corpo}')
        return ctx.banco("update public.conta set status_fatura = 'FECHADA', valor_consolidado = valor_executado, "
                         'data_consolidacao = now() where is_fatura_cartao and item_despesa_id = %s '
                         'and cartao_competencia = %s returning id', (c10, mes), escrever=True)[0][0]  # como o Flask

    outubro, novembro = consolidar('2036-10-01'), consolidar('2036-11-01')
    rec = ctx.banco("insert into public.item_despesa (nome, tipo, perfil_financeiro_id, categoria_id, ativo, recorrente, "
                    "tipo_recorrencia, data_vencimento, valor, meio_pagamento, cartao_id, criado_em) "
                    "values (%s, 'Simples', %s, %s, true, true, 'mensal', '2036-10-05', 12.34, 'cartao', %s, now()) "
                    'returning id', (NOME_RECORRENCIA, B, ctx.SAUDE, c10), escrever=True)[0][0]
    # SAUDE: uma unica categoria do cartao ativa com limite no c10 (cenario 3), entao o plano so rejeita pelo destino.

    def gerar(mes):
        st, pv = ctx.rpc('previa_geracao', {'p_perfil_id': B, 'p_mes': mes})
        if st != 200:
            return st, pv
        return ctx.rpc('gerar_mes', {'p_perfil_id': B, 'p_mes': mes, 'p_total_previsto': pv['a_gerar']})

    def ocorrencia(comp):
        return [tuple(x) for x in ctx.banco(
            'select perfil_financeiro_id, cartao_id, fatura_id, valor, situacao, origem, tentativas, '
            'aviso_dispensado_em is not null, aviso_dispensado_user_id is not null from public.recorrencia_rejeicao '
            'where item_despesa_id = %s and competencia = %s', (rec, comp))]

    def financeiro():
        """Faturas consolidadas, compras e identidades da recorrencia e a propria recorrencia."""
        return (ctx.banco("select md5(string_agg(t::text, '|' order by id)) from public.conta t where id in (%s, %s)",
                          (outubro, novembro))[0][0],
                ctx.banco('select count(*) from public.lancamento_agregado where item_despesa_id = %s', (rec,))[0][0],
                ctx.banco('select md5(t::text) from public.item_despesa t where id = %s', (rec,))[0][0],
                ctx.banco('select count(*) from financeiro.recorrencia_competencia where item_despesa_id = %s',
                          (rec,))[0][0])

    def dispensar(comp, usuario='B', perfil=None):
        return ctx.rpc('dispensar_aviso_recorrencia', {'p_perfil_id': perfil or B, 'p_item_id': rec,
                                                       'p_competencia': comp}, usuario)

    def avisos(incluir=False, comp='2036-10-01'):
        st, corpo = ctx.rpc('recorrencias_rejeitadas', {'p_perfil_id': B, 'p_incluir_dispensadas': incluir})
        return st, [x for x in corpo if x['item_id'] == rec and x['competencia'] == comp] if st == 200 else corpo

    antes = financeiro()
    # 11/2036 antes de qualquer geracao: o banco confere o plano e registra a ocorrencia antes de dispensar o aviso.
    # (A geracao de 10/2036 cobre tambem os meses seguintes do horizonte, entao este passo vem primeiro.)
    s_nov, d_nov = dispensar('2036-11-01')
    o_nov = ocorrencia('2036-11-01')
    g1 = gerar('2036-10-01')[0]
    o1 = ocorrencia('2036-10-01')
    g2 = gerar('2036-10-01')[0]  # nova tentativa: so conta, sem duplicar
    o2 = ocorrencia('2036-10-01')
    s_av, aviso = avisos()
    negados = {
        'A lista avisos do Perfil B': ctx.rpc('recorrencias_rejeitadas', {'p_perfil_id': B}, 'A')[0],
        'A dispensa no Perfil B': dispensar('2036-10-01', usuario='A')[0],
        'A dispensa pelo Pessoal (recorrencia do Perfil B)': dispensar('2036-10-01', usuario='A', perfil=ctx.PESSOAL)[0],
        'A (LEITOR) dispensa na Empresa': dispensar('2036-10-01', usuario='A', perfil=ctx.EMPRESA)[0],
        'B lista avisos do Pessoal': ctx.rpc('recorrencias_rejeitadas', {'p_perfil_id': ctx.PESSOAL})[0],
    }
    anon = {f: ctx.anonimo(f, c) for f, c in (
        ('recorrencias_rejeitadas', {'p_perfil_id': B}),
        ('dispensar_aviso_recorrencia', {'p_perfil_id': B, 'p_item_id': rec, 'p_competencia': '2036-10-01'}))}
    intacta = ocorrencia('2036-10-01') == o2  # tentativas negadas nao dispensam nem registram nada
    s_d1, d1 = dispensar('2036-10-01')
    s_d2, d2 = dispensar('2036-10-01')  # idempotente
    s_at, ativos = avisos()
    s_hi, historico = avisos(incluir=True)
    g3 = gerar('2036-10-01')[0]  # depois da dispensa: conta a tentativa e mantem a dispensa
    o3 = ocorrencia('2036-10-01')
    o_nov_fim = ocorrencia('2036-11-01')
    s_dez, e_dez = dispensar('2036-12-01')  # dezembro nao tem fatura consolidada: nada a dispensar
    depois = financeiro()

    base = (B, c10, outubro, Decimal('12.34'), 'PENDENTE', 'NOVO_APP')
    checks = {
        'geracoes 200': (g1, g2, g3) == (200, 200, 200),
        'ocorrencia registrada': o1 == [base + (1, False, False)],
        'nova tentativa so conta': o2 == [base + (2, False, False)],
        'aviso na lista': s_av == 200 and [(x['competencia'], x['fatura_id'], x['tentativas']) for x in aviso]
        == [('2036-10-01', outubro, 2)],
        'isolamento 403': set(negados.values()) == {403},
        'anonimo 401': set(anon.values()) == {401},
        'negados nao mudam nada': intacta,
        'dispensa auditada': s_d1 == 200 and d1.get('ja_dispensado') is False,
        'dispensa idempotente': s_d2 == 200 and d2.get('ja_dispensado') is True
        and d2.get('aviso_dispensado_em') == d1.get('aviso_dispensado_em') and d2.get('id') == d1.get('id'),
        'fora dos avisos ativos': s_at == 200 and ativos == [],
        'no historico': s_hi == 200 and [(x['competencia'], x['aviso_dispensado_em'] is not None) for x in historico]
        == [('2036-10-01', True)],
        'dispensa mantida apos nova tentativa': o3 == [base + (3, True, True)],
        'dispensa antes da geracao': s_nov == 200 and d_nov.get('ja_dispensado') is False
        and o_nov == [(B, c10, novembro, Decimal('12.34'), 'PENDENTE', 'NOVO_APP', 1, True, True)]
        and len(o_nov_fim) == 1 and o_nov_fim[0][6] > 1 and o_nov_fim[0][7],  # geracoes depois so contam
        'sem rejeicao 400': s_dez == 400 and 'Nao ha aviso' in str(e_dez),
        'nada financeiro mudou': depois == antes and depois[1] == 0,
    }
    falhas = [k for k, v in checks.items() if not v]
    ctx.registrar(
        '17b. Recorrencia rejeitada por fatura consolidada: ocorrencia, aviso e dispensa', not falhas,
        (f'FALHAS: {falhas}; ' if falhas else '')
        + f'geracoes {g1}/{g2}/{g3}; tentativas {[o[0][6] if o else None for o in (o1, o2, o3)]}; negados '
        f'{sorted(set(negados.values()))}; anonimo {sorted(set(anon.values()))}; dispensa {s_d1}/{s_d2} '
        f'(ja_dispensado {d1.get("ja_dispensado") if isinstance(d1, dict) else d1}/'
        f'{d2.get("ja_dispensado") if isinstance(d2, dict) else d2}); 11/2036 dispensada antes da geracao {s_nov}; '
        f'12/2036 {s_dez}; faturas consolidadas, compras e recorrencia inalteradas: {depois == antes}')
