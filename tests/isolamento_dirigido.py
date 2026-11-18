"""
Sondas DIRIGIDAS de isolamento por registro (FIN-MULTIUSUARIO-AJUSTES-FINAIS-01).

A sonda generica (tests/test_supabase_isolamento_usuarios.py) nao alcanca a regra de posse de algumas funcoes: ou falta o
registro "pai" correto (o cartao do limite, o comprovante do vinculo), ou a validacao dos dados vem antes, ou a funcao so vale
no perfil Empresa, ou o registro precisa ser de um tipo especifico (recorrencia, parcela de consorcio). Aqui cada combinacao
funcao x parametro recebe dados ficticios VALIDOS para chegar a logica relevante, e a prova e DIFERENCIAL, com o proprio
atacante, no proprio perfil dele:

    proprio     o registro equivalente do atacante          -> a funcao ENCONTRA (resposta diferente de "inexistente")
    inexistente um identificador que nao existe             -> a resposta de "nao encontrado"
    alheio      o registro equivalente do OUTRO usuario     -> tem de ser IDENTICA a de "inexistente"

Cobertura efetiva = proprio != inexistente (a logica foi alcancada) e alheio == inexistente (o registro alheio nao e lido nem
alterado, nem sequer distinguido de um que nao existe). Quando a funcao responde sem erro ao registro alheio, as tabelas do
dono sao conferidas ANTES de a transacao ser desfeita.
"""
import json
import uuid

import psycopg2

from tests import isolamento_cenario as I

INEXISTENTE = 999999991
BASE = dict(json.loads(I.DADOS))


def semear_dirigido(s):
    """Registros do tipo que as funcoes procuram, para o dono do Semeador s (alem do registro generico por tabela)."""
    ids, x = s.ids, {}
    item, conta, cartao = ids.get('public.item_despesa'), ids.get('public.conta'), s.extras.get('cartao')

    def tentar(rotulo, funcao):
        with s.conn.cursor() as cur:
            cur.execute('savepoint dirigido')
            try:
                x[rotulo] = funcao(cur)
                cur.execute('release savepoint dirigido')
            except psycopg2.Error as erro:
                cur.execute('rollback to savepoint dirigido')
                s.falhas[f'dirigido:{rotulo}'] = (erro.diag.message_primary or str(erro))[:160]

    auto = s.conn.autocommit
    s.conn.autocommit = False
    try:
        marca = I.MARCA[s.dono]
        if item:
            tentar('recorrencia', lambda cur: s.clonar('public.item_despesa', item, recorrente=True, tipo='Simples', meio_pagamento=None, origem_tipo=None,
                                                       nome=f'{marca} recorrencia'))
            if cartao:
                tentar('recorrencia_cartao', lambda cur: s.clonar('public.item_despesa', item, recorrente=True, tipo='Simples', meio_pagamento='cartao',
                                                                  cartao_id=cartao, origem_tipo=None, nome=f'{marca} recorrencia cartao'))
            if conta:
                def consorcio(cur):
                    i = s.clonar('public.item_despesa', item, tipo='Consorcio', recorrente=False, nome=f'{marca} consorcio - Parcela 1/10')
                    return s.clonar('public.conta', conta, item_despesa_id=i, financiamento_parcela_id=None, mes_referencia='2027-05-01')
                tentar('parcela_consorcio', consorcio)
        if cartao and ids.get('public.cartao_categoria_limite'):
            tentar('limite_do_cartao', lambda cur: s.clonar('public.cartao_categoria_limite', ids['public.cartao_categoria_limite'], cartao_id=cartao))
        if ids.get('public.despesa_prevista'):
            def caminho(cur):
                origem = I.BASE_ID[s.dono] + s.perfil * 1000 + 900
                s.clonar('public.despesa_prevista', ids['public.despesa_prevista'], origem_tipo='TRANSPORTE_APP', origem_id=origem,
                         metadata=json.dumps({'caminho': {'nome': f'{marca} caminho'}, 'calculo': {'valor_mensal': I.VALOR[s.dono]}}))
                return origem
            tentar('caminho_app', caminho)
        if cartao:
            def vinculado(cur):
                cur.execute("""insert into financeiro.cartao_vinculado (perfil_financeiro_id, contrato_id, nome, final, tipo)
                               values (%s, %s, %s, '4321', 'ADICIONAL') returning id""", (s.perfil, cartao, f'{marca} adicional'))
                return cur.fetchone()[0]
            tentar('cartao_vinculado', vinculado)
        if ids.get('public.ir_comprovante_vinculo'):
            tentar('vinculo_ativo', lambda cur: s.clonar('public.ir_comprovante_vinculo', ids['public.ir_comprovante_vinculo'], ativo=True))
        movimento = ids.get('public.movimento_financeiro')
        if conta and movimento:
            def pagamento_despesa(cur):
                paga = s.clonar('public.conta', conta, status_pagamento='Pago', data_pagamento='2027-03-10', financiamento_parcela_id=None,
                                mes_referencia='2027-06-01')
                x['despesa_paga'] = paga
                return s.clonar('public.movimento_financeiro', movimento, tipo='DEBITO', origem='DESPESA', conta_id=paga, fatura_id=None,
                                movimento_original_id=None)
            tentar('pagamento_da_despesa', pagamento_despesa)
            if cartao:
                def pagamento_fatura(cur):
                    paga = s.clonar('public.conta', conta, item_despesa_id=cartao, is_fatura_cartao=True, cartao_competencia='2027-04-01',
                                    status_pagamento='Pago', data_pagamento='2027-04-12', financiamento_parcela_id=None, mes_referencia='2027-04-01')
                    x['fatura_paga'] = paga
                    return s.clonar('public.movimento_financeiro', movimento, tipo='DEBITO', origem='FATURA', conta_id=paga, fatura_id=paga,
                                    movimento_original_id=None)
                tentar('pagamento_da_fatura', pagamento_fatura)
        if x.get('recorrencia') and conta:
            # conta da recorrencia, de competencia antiga: so entra na previa de interrupcao quando indicada pelo identificador
            tentar('conta_da_recorrencia', lambda cur: s.clonar('public.conta', conta, item_despesa_id=x['recorrencia'], financiamento_parcela_id=None,
                                                                mes_referencia='2026-01-01', data_vencimento='2026-01-10'))

        def particular(cur):
            # categoria de despesa PARTICULAR do dono (uma por dono, vale nos perfis dele), vinculada a categoria de cartao dele
            cur.execute('select id from public.categoria where user_id = %s and nome = %s', (I.USUARIOS[s.dono]['id'], f'{marca} particular'))
            achada = cur.fetchone()
            if achada:
                cat = achada[0]
            else:
                cur.execute('insert into public.categoria (nome, ativo, sistemica, bloquear_edicao, bloquear_exclusao, user_id) values (%s, true, false, false, false, %s) returning id', (f'{marca} particular', I.USUARIOS[s.dono]['id']))
                cat = cur.fetchone()[0]
            cc = ids.get('public.categoria_cartao')
            if cc:
                cur.execute('update public.categoria_cartao set ativo = true where id = %s', (cc,))
                cur.execute('insert into public.categoria_cartao_despesa (perfil_financeiro_id, categoria_cartao_id, categoria_id, ativo) values (%s, %s, %s, true)',
                            (s.perfil, cc, cat))
            return cat
        tentar('categoria_particular', particular)
        s.conn.commit()
    finally:
        s.conn.autocommit = auto
    s.extras.update(x)
    return s


# (funcao, parametro) -> como alcancar a regra de posse.
#   perfil: 'Pessoal' ou 'Empresa'; alvo: rotulo do registro (do dono) que vai no parametro; com: outros parametros de
#   identificador, com o registro PROPRIO do atacante; texto: parametros de texto; dados: campos de p_dados (valor ou rotulo
#   "@x" = identificador proprio do atacante).
CASOS = {
    ('abastecimento_do_lancamento', 'p_lancamento_id'): {'alvo': 'public.lancamento_agregado'},
    ('abastecimento_do_lancamento', 'p_conta_id'): {'alvo': 'public.conta'},
    ('ajustar_saldo_devedor', 'p_id'): {'alvo': 'public.financiamento', 'dados': {'saldo_devedor_real': '1000.00', 'numero_parcela': 1}},
    ('registrar_amortizacao_extra', 'p_id'): {'alvo': 'public.financiamento', 'dados': {'tipo': 'reduzir_prazo', 'valor': '100.00', 'data': '2027-03-10'}},
    ('apelidos_da_recorrencia', 'p_item_id'): {'alvo': 'recorrencia_cartao'},
    ('criar_apelido_recorrencia', 'p_item_id'): {'alvo': 'recorrencia_cartao', 'texto': {'p_apelido': 'apelido dirigido'}},
    ('atualizar_limite_cartao', 'p_limite_id'): {'alvo': 'limite_do_cartao', 'com': {'p_cartao_id': 'cartao'}, 'dados': {'limite_mensal': '100.00'}},
    ('desativar_limite_cartao', 'p_limite_id'): {'alvo': 'limite_do_cartao', 'com': {'p_cartao_id': 'cartao'}},
    ('atualizar_vinculo_documento', 'p_vinculo_id'): {'alvo': 'vinculo_ativo', 'com': {'p_comprovante_id': 'public.ir_comprovante'},
                                                     'dados': {'observacoes': 'x'}, 'so_dados': True},
    ('remover_vinculo_documento', 'p_vinculo_id'): {'alvo': 'vinculo_ativo', 'com': {'p_comprovante_id': 'public.ir_comprovante'}},
    ('conciliar_ocorrencia_recorrencia', 'p_previsto_id'): {'alvo': 'compra_no_cartao', 'com': {'p_cobranca_id': 'public.lancamento_agregado'}},
    ('conciliar_ocorrencia_recorrencia', 'p_cobranca_id'): {'alvo': 'compra_no_cartao', 'com': {'p_previsto_id': 'public.lancamento_agregado'}},
    ('definir_meio_pagamento_recorrencia', 'p_item_id'): {'alvo': 'recorrencia', 'texto': {'p_meio': 'pix'}},
    ('previa_interrupcao_recorrencia', 'p_item_id'): {'alvo': 'recorrencia'},
    ('previa_interrupcao_recorrencia', 'p_conta_id'): {'alvo': 'conta_da_recorrencia', 'com': {'p_item_id': 'recorrencia'}, 'texto': {'p_efeito': '2030-01-01'}},
    ('previa_retomada_recorrencia', 'p_item_id'): {'alvo': 'recorrencia'},
    ('editar_parcela_consorcio', 'p_conta_id'): {'alvo': 'parcela_consorcio', 'texto': {'p_escopo': 'unica'}},
    ('estornar_pagamento_despesa', 'p_movimento_id'): {'alvo': 'pagamento_da_despesa', 'com': {'p_conta_id': 'despesa_paga'}},
    ('estornar_pagamento_fatura', 'p_movimento_id'): {'alvo': 'pagamento_da_fatura', 'com': {'p_fatura_id': 'fatura_paga'}},
    ('pagar_fatura', 'p_fatura_id'): {'alvo': 'fatura', 'dados': {'conta_bancaria_id': '@public.conta_bancaria', 'valor_pago': '10.00'}},
    ('excluir_regra_km_veiculo', 'p_regra_id'): {'alvo': 'public.veiculo_regra_manutencao_km', 'com': {'p_veiculo_id': 'public.veiculo'}},
    ('excluir_regra_km_veiculo', 'p_veiculo_id'): {'alvo': 'public.veiculo', 'com': {'p_regra_id': 'public.veiculo_regra_manutencao_km'}},
    ('gerar_manutencao_km_veiculo', 'p_veiculo_id'): {'alvo': 'public.veiculo', 'dados': {'regra_id': '@public.veiculo_regra_manutencao_km'}},
    ('projecoes_mobilidade_tela', 'p_origem_id'): {'alvo': 'public.veiculo', 'texto': {'p_origem_tipo': 'VEICULO'}},
    ('editar_caminho_app', 'p_caminho_id'): {'alvo': 'caminho_app', 'dados': {'nome': 'x', 'km_mensal_estimado': 10, 'preco_medio_por_km': 2}},
    ('excluir_caminho_app', 'p_caminho_id'): {'alvo': 'caminho_app'},
    ('transporte_app_tela', 'p_id'): {'alvo': 'caminho_app'},
    ('patrimonio_transferencias_tela', 'p_id'): {'alvo': 'public.transferencia', 'texto': {'p_data_inicio': None, 'p_data_fim': None}},
    ('patrimonio_transferencias_tela', 'p_conta_id'): {'alvo': 'public.conta_patrimonio', 'texto': {'p_data_inicio': None, 'p_data_fim': None}},
    ('salvar_cartao_vinculado', 'p_cartao_vinculado_id'): {'alvo': 'cartao_vinculado', 'com': {'p_contrato_id': 'cartao'}, 'dados': {'nome': 'x', 'final': '1234'},
                                                           'so_dados': True},
    ('editar_bem_patrimonial', 'p_bem_id'): {'perfil': 'Empresa', 'alvo': 'public.bem_patrimonial', 'dados': {'observacoes': 'x'}, 'so_dados': True},
    ('excluir_bem_patrimonial', 'p_bem_id'): {'perfil': 'Empresa', 'alvo': 'public.bem_patrimonial'},
    ('patrimonio_bens_tela', 'p_bem_id'): {'perfil': 'Empresa', 'alvo': 'public.bem_patrimonial'},
    ('vincular_documento_bem', 'p_bem_id'): {'perfil': 'Empresa', 'alvo': 'public.bem_patrimonial', 'dados': {'comprovante_id': '@public.ir_comprovante'}, 'so_dados': True},
    ('patrimonio_documento_sugestao_tela', 'p_comprovante_id'): {'perfil': 'Empresa', 'alvo': 'public.ir_comprovante'},
    ('ir_documentos_empresa_tela', 'p_id'): {'perfil': 'Empresa', 'alvo': 'public.ir_comprovante', 'texto': {'p_recurso': 'metadata'}},
    ('salvar_metadata_empresarial', 'p_id'): {'perfil': 'Empresa', 'alvo': 'public.ir_comprovante', 'dados': {'observacoes': 'x'}, 'so_dados': True},
}

# Combinacoes em que o parametro NAO identifica registro de usuario, ou so filtra registros ja restritos ao proprio perfil:
# nao ha registro alheio a alcancar por ele. Cada uma com o motivo (conferido na leitura do codigo da funcao).
NAO_APLICAVEIS = {
    ('interromper_recorrencia', 'p_conta_id'): 'so filtra as contas da recorrencia ja conferida como do perfil (item_despesa_id = p_item_id); e o mesmo filtro da '
                                               'previa de interrupcao, que tem sonda dirigida; aqui a versao da recorrencia e conferida antes e impede a prova diferencial',
    ('abastecimentos_da_importacao', 'p_cartao_id'): 'so filtra abastecimentos ja restritos ao proprio perfil; a resposta parte das linhas enviadas pelo usuario',
}
# Categoria de cartao e categoria de DESPESA como parametro. O catalogo padrao e de todos; o registro "alheio" aqui e a
# categoria PARTICULAR do outro usuario, que tem de responder exatamente como uma inexistente.
CASOS[('desvincular_despesa_categoria_cartao', 'p_categoria_cartao_id')] = {'alvo': 'public.categoria_cartao', 'categoria_do_vinculo': True}
CASOS[('desvincular_despesa_categoria_cartao', 'p_categoria_id')] = {'alvo': 'categoria_particular', 'com': {'p_categoria_cartao_id': 'public.categoria_cartao'}}
CASOS[('vincular_despesa_categoria_cartao', 'p_categoria_id')] = {'alvo': 'categoria_particular', 'com': {'p_categoria_cartao_id': 'public.categoria_cartao'}}
CASOS[('resolver_categoria_cartao_tela', 'p_categoria_id')] = {'alvo': 'categoria_particular', 'com': {'p_cartao_id': 'cartao'}}


def _args(f, valores):
    nomes, tipos = (f['nomes'] or [])[:f['n']], f['tipos'] or []
    marc = ', '.join(f'{n} => %s::{t}' for n, t in zip(nomes, tipos))
    args = []
    for n, t in zip(nomes, tipos):
        if n in valores:
            args.append(valores[n])
        elif t == 'uuid':
            args.append(str(uuid.uuid4()))
        elif t in ('integer', 'bigint'):
            args.append(None)  # identificador nao usado nesta sonda: ausente
        else:
            args.append(I.ARG.get(t))
    return marc, args


def chamar(conn, usuario, f, valores, perfis_do_dono=None):
    """Como o usuario, numa transacao sempre desfeita. Devolve (codigo, mensagem, retorno, mudou): `mudou` so e medido quando a
    funcao respondeu sem erro e perfis_do_dono foi dado (as tabelas do dono, dentro da propria transacao)."""
    marc, args = _args(f, valores)
    conn.autocommit = False
    try:
        antes = I.retrato(conn, perfis_do_dono) if perfis_do_dono else None
        I.como(conn, usuario)
        with conn.cursor() as cur:
            try:
                cur.execute(f"select to_jsonb(x) from financeiro.{f['nome']}({marc}) x", args)
                retorno = json.dumps([r[0] for r in cur.fetchall()], default=str, ensure_ascii=False)
            except psycopg2.Error as e:
                return e.pgcode or '?', (e.diag.message_primary or '')[:200], '', False
            mudou = False
            if perfis_do_dono:
                cur.execute('reset role')
                mudou = I.retrato(conn, perfis_do_dono) != antes
            return 'OK', '', retorno, mudou
    finally:
        conn.rollback()
        conn.autocommit = True


def sondar(conn, f, parametro, caso, atacante, usuario_atacante, meus, dela, perfil_meu, perfis_dela, categoria):
    """Devolve dict com as tres respostas e a conclusao: EFETIVA, INCONCLUSIVA (a logica nao foi alcancada) ou FALHA."""
    rotulo = caso['alvo']
    if rotulo not in meus or rotulo not in dela:
        return {'conclusao': 'INCONCLUSIVA', 'motivo': f'registro "{rotulo}" nao semeado'}
    dados = {} if caso.get('so_dados') else dict(BASE)
    for k, v in (caso.get('dados') or {}).items():
        dados[k] = meus.get(v[1:]) if isinstance(v, str) and v.startswith('@') else v
    valores = {'p_perfil_id': perfil_meu, 'p_dados': json.dumps(dados), **(caso.get('texto') or {})}
    for p, r in (caso.get('com') or {}).items():
        if r not in meus:
            return {'conclusao': 'INCONCLUSIVA', 'motivo': f'registro "{r}" nao semeado'}
        valores[p] = meus[r]
    if caso.get('categoria_do_vinculo'):
        valores['p_categoria_id'] = categoria
    proprio = chamar(conn, usuario_atacante, f, {**valores, parametro: meus[rotulo]})
    nenhum = chamar(conn, usuario_atacante, f, {**valores, parametro: INEXISTENTE})
    alheio = chamar(conn, usuario_atacante, f, {**valores, parametro: dela[rotulo]}, perfis_dela)
    r = {'proprio': proprio[:2], 'inexistente': nenhum[:2], 'alheio': alheio[:2]}
    if alheio[3]:
        return {**r, 'conclusao': 'FALHA', 'motivo': 'tabelas do dono alteradas'}
    if alheio[:3] != nenhum[:3]:
        return {**r, 'conclusao': 'FALHA', 'motivo': 'registro alheio distinguido de inexistente'}
    if proprio[:3] == nenhum[:3]:
        return {**r, 'conclusao': 'INCONCLUSIVA', 'motivo': 'a funcao nao distinguiu nem o registro proprio (logica nao alcancada)'}
    return {**r, 'conclusao': 'EFETIVA'}
