"""FIN-PATRIMONIO-2 — implantacao da migration 20261126090000 no Supabase de teste (fzjmge...), com dados FICTICIOS num
perfil TEMPORARIO criado pelo aplicativo. Reaproveita lote_real.py, motor_real.py e cr_real.py.

Etapas:
  inspecionar   so leitura: so objetos novos (nenhuma funcao existente substituida), todos ausentes no remoto; reversao
                remove exatamente o que a migration cria; dependencias presentes; nenhum comando de dados; dados de
                Patrimonio existentes (informativo)
  aplicar       aplica SO a 20261126090000
  criar | api | ui <web> | limpar [--confirmar]
Nunca grava nos perfis 1, 2, 31 e 39. Nao imprime e-mails, senhas, chaves nem URL do banco.
"""
import json
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import lote_real as L  # noqa: E402
import motor_real as M  # noqa: E402
import cr_real as C  # noqa: E402

RAIZ = L.RAIZ
VERSAO = '20261126090000'
ANTERIOR = '20261125090000'
MIGRATION = RAIZ / 'supabase' / 'migrations' / f'{VERSAO}_financeiro_patrimonio_escrita.sql'
REVERSAO = RAIZ / 'supabase' / 'reversao' / f'{VERSAO}_remover_patrimonio_escrita.sql'
PASTA = RAIZ / 'data' / 'homologacao_real' / 'pat_real'  # estado e retratos locais (data/ fora do Git)
L.PERFIL = 'Validacao Patrimonio (e2e-real)'
L.ESTADO = PASTA / 'estado.json'
MARCA = '(e2e-real)'
CAIXAS = {'a': f'Reserva {MARCA}', 'b': f'Viagem {MARCA}', 'c': f'Antiga {MARCA}'}
BENS = {'livre': f'Cadeira {MARCA}', 'doc': f'Notebook {MARCA}', 'edit': f'Notebook editado {MARCA}'}
DOCS = [(f'Loja ficticia de informatica {MARCA}', '6899.90', '2026-06-01',
         'NFS-e numero 004512 Notebook Dell Inspiron 15 i5-1135G7 garantia 12 meses', 'OCR_TESSERACT'),
        (f'Moveis ficticios ME {MARCA}', '1890.00', '2026-04-02', 'Cadeira ergonomica presidente', 'MANUAL'),
        (f'Papelaria ficticia {MARCA}', '310.40', None, None, None)]


def inspecionar():
    texto = MIGRATION.read_text(encoding='utf-8')
    rev = REVERSAO.read_text(encoding='utf-8')
    criadas = re.findall(r'^create function financeiro\.(\w+)\(', texto, re.M)
    trocadas = re.findall(r'^create or replace function', texto, re.M)
    ok = True

    def item(nome, cond, det=''):
        nonlocal ok
        ok = ok and bool(cond)
        print(f"{'OK   ' if cond else 'FALHA'} | {nome} | {det}")

    item('nenhuma funcao existente substituida (so create function)', not trocadas, len(trocadas))
    existentes = {r['proname'] for r in M.ler("select p.proname from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
                                               "where n.nspname = 'financeiro'")}
    item(f'{len(criadas)} funcoes novas ausentes no remoto', not (set(criadas) & existentes), sorted(set(criadas) & existentes))
    tab = M.ler("select to_regclass('financeiro.operacao_patrimonio') is null t")[0]['t']
    item('tabela nova (operacao_patrimonio) ausente', tab)
    removidas = set(re.findall(r'^drop function financeiro\.(\w+)\(', rev, re.M))
    item('reversao remove exatamente as funcoes criadas', removidas == set(criadas),
         {'so_na_migration': sorted(set(criadas) - removidas), 'so_na_reversao': sorted(removidas - set(criadas))})
    item('reversao remove a tabela de controle e nao toca em dados',
         'drop table financeiro.operacao_patrimonio' in rev and not re.findall(r'^\s*(insert|update|delete|truncate)\b', C.sem_corpos(rev), re.M | re.I))
    chamadas = set(re.findall(r'financeiro\.(\w+)\(', texto)) - set(criadas)
    item(f'{len(chamadas)} funcoes de que a migration depende presentes', not (chamadas - existentes), sorted(chamadas - existentes))
    usadas = sorted(set(re.findall(r'public\.(\w+)', texto)))
    faltam = [t for t in usadas if not M.ler(f"select to_regclass('public.{t}') is not null or to_regtype('public.{t}') is not null x")[0]['x']]
    item(f'{len(usadas)} tabelas de public usadas presentes', not faltam, faltam or usadas)
    fora = C.sem_corpos(texto)
    dml = re.findall(r'^\s*(insert|update|delete|truncate|copy)\b', fora, re.M | re.I)
    item('nenhum comando de dados fora dos corpos de funcao', not dml, dml)
    ddl = re.findall(r'^\s*(drop|alter table (?!financeiro\.operacao_patrimonio)\S+)', fora, re.M | re.I)
    item('nenhum drop nem alteracao de tabela existente', not ddl, ddl)
    ultima = M.ler('select version from supabase_migrations.schema_migrations order by 1 desc limit 1')[0]['version']
    item(f'ultima aplicada no remoto = {ANTERIOR}', ultima == ANTERIOR, ultima)
    item('dados de Patrimonio por perfil (informativo)', True, M.ler(
        "select p.id perfil, (select count(*) from public.conta_patrimonio c where c.perfil_financeiro_id = p.id) caixinhas, "
        "(select count(*) from public.transferencia t where t.perfil_financeiro_id = p.id) transferencias, "
        "(select count(*) from public.bem_patrimonial b where b.perfil_financeiro_id = p.id) bens from public.perfil_financeiro p order by 1"))
    print('INSPECAO', 'OK' if ok else 'COM FALHAS')
    return 0 if ok else 1


def aplicar():
    C.VERSAO = VERSAO
    C.PASTA = PASTA
    return C.aplicar()


def documentos(perfil):
    """Documentos fiscais FICTICIOS do perfil temporario (Documentos ainda nao tem cadastro no novo aplicativo)."""
    conn = L.conectar()
    try:
        with conn.cursor() as cur:
            a, _ = L.usuarios(cur)
            if L.identificar(cur, a)[0] != perfil or perfil in L.PROTEGIDOS:
                raise SystemExit('Perfil temporario nao confere: interrompido.')
            ids = []
            for prestador, valor, data, texto, origem in DOCS:
                cur.execute("insert into public.ir_comprovante (perfil_financeiro_id, ano_calendario, data_documento, prestador_nome, "
                            "valor, status, hash_arquivo, texto_extraido, origem_classificacao, created_at, updated_at) values "
                            "(%s, 2026, %s, %s, %s, 'IMPORTADO', md5(random()::text) || md5(random()::text), %s, %s, now(), now()) "
                            "returning id", (perfil, data, prestador, valor, texto, origem))
                ids.append(cur.fetchone()[0])
        conn.commit()
        return ids
    finally:
        conn.close()


def api():
    origem, chave, ta, tb = L.contexto()
    perfil = json.loads(L.ESTADO.read_text(encoding='utf-8'))['perfil']
    chamar = lambda f, c, t=ta: L.rpc(origem, chave, f, c, t)  # noqa: E731
    k = lambda: str(uuid.uuid4())  # noqa: E731
    reg = L.registrar
    hint = lambda r: (r or {}).get('hint') if isinstance(r, dict) else None  # noqa: E731
    saldos = lambda: {r['nome']: float(r['saldo_atual']) for r in M.ler(  # noqa: E731
        'select nome, saldo_atual from public.conta_patrimonio where perfil_financeiro_id = %s', (perfil,))}

    # 1. Caixinhas: criar (repetida pela chave nao duplica), editar, inativar e reativar.
    ch = k()
    sa, a = chamar('criar_caixinha', {'p_perfil_id': perfil, 'p_chave': ch, 'p_dados': {'nome': CAIXAS['a'], 'tipo': 'Reserva',
                                                                                       'saldo_inicial': 5000, 'meta': 20000, 'cor': '#123456'}})
    sa2, a2 = chamar('criar_caixinha', {'p_perfil_id': perfil, 'p_chave': ch, 'p_dados': {'nome': CAIXAS['a'], 'saldo_inicial': 5000}})
    _, b = chamar('criar_caixinha', {'p_perfil_id': perfil, 'p_chave': k(), 'p_dados': {'nome': CAIXAS['b'], 'tipo': 'Poupança', 'saldo_inicial': 800}})
    _, c = chamar('criar_caixinha', {'p_perfil_id': perfil, 'p_chave': k(), 'p_dados': {'nome': CAIXAS['c'], 'tipo': 'Investimento'}})
    a, b, c = a['conta_id'], b['conta_id'], c['conta_id']
    reg('criar caixinhas; reenvio com a mesma chave nao duplica', (sa, sa2) == (200, 200) and a2['conta_id'] == a and
        saldos() == {CAIXAS['a']: 5000, CAIXAS['b']: 800, CAIXAS['c']: 0}, saldos())
    se, _ = chamar('editar_caixinha', {'p_perfil_id': perfil, 'p_conta_id': b, 'p_dados': {'meta': 1500, 'cor': '#abcdef', 'observacoes': 'nova'}})
    sd, dup = chamar('editar_caixinha', {'p_perfil_id': perfil, 'p_conta_id': b, 'p_dados': {'nome': CAIXAS['a']}})
    si, _ = chamar('inativar_caixinha', {'p_perfil_id': perfil, 'p_conta_id': c})
    inativa = M.ler('select ativo from public.conta_patrimonio where id = %s', (c,))[0]['ativo']
    sr, _ = chamar('editar_caixinha', {'p_perfil_id': perfil, 'p_conta_id': c, 'p_dados': {'ativo': True}})
    linha_b = M.ler('select meta, cor, observacoes from public.conta_patrimonio where id = %s', (b,))[0]
    reg('editar (meta, cor, observacoes); nome repetido recusado; inativar e reativar',
        (se, si, sr) == (200, 200, 200) and sd == 400 and inativa is False and float(linha_b['meta']) == 1500 and linha_b['cor'] == '#abcdef'
        and M.ler('select ativo from public.conta_patrimonio where id = %s', (c,))[0]['ativo'] is True,
        (se, sd, (dup or {}).get('message'), si, sr))

    # 2. Transferencias: saldo travado, repeticao, saldo insuficiente, exclusao que desfaz e a que deixaria negativo.
    t = lambda o, d, v, ch=None: chamar('criar_transferencia_patrimonio', {'p_perfil_id': perfil, 'p_chave': ch or k(), 'p_dados': {  # noqa: E731
        'conta_origem_id': o, 'conta_destino_id': d, 'valor': v, 'data_transferencia': '2026-10-05', 'descricao': f'Aporte {MARCA}'}})
    ch = k()
    s1, t1 = t(a, b, 300, ch)
    s1b, t1b = t(a, b, 300, ch)
    reg('transferencia A->B 300 (reenvio nao duplica): 4700 / 1100', (s1, s1b) == (200, 200) and t1b == t1 and
        saldos() == {CAIXAS['a']: 4700, CAIXAS['b']: 1100, CAIXAS['c']: 0}, (t1, saldos()))
    s2, r2 = t(c, a, 10)
    reg('saldo insuficiente na origem recusado, nada gravado', s2 == 400 and saldos()[CAIXAS['c']] == 0, (s2, (r2 or {}).get('message')))
    _, t3 = t(b, c, 1100)
    s4, r4 = chamar('excluir_transferencia_patrimonio', {'p_perfil_id': perfil, 'p_transferencia_id': t1['transferencia_id']})
    reg('exclusao que deixaria o destino negativo recusada (SALDO_DESTINO)', s4 == 400 and hint(r4) == 'SALDO_DESTINO'
        and saldos() == {CAIXAS['a']: 4700, CAIXAS['b']: 0, CAIXAS['c']: 1100}, (s4, hint(r4), saldos()))
    s5, _ = chamar('excluir_transferencia_patrimonio', {'p_perfil_id': perfil, 'p_transferencia_id': t3['transferencia_id']})
    s6, _ = chamar('excluir_transferencia_patrimonio', {'p_perfil_id': perfil, 'p_transferencia_id': t1['transferencia_id']})
    restantes = M.ler('select count(*) n from public.transferencia where perfil_financeiro_id = %s', (perfil,))[0]['n']
    reg('excluir desfaz os saldos (volta a 5000 / 800 / 0)', (s5, s6) == (200, 200) and restantes == 0 and
        saldos() == {CAIXAS['a']: 5000, CAIXAS['b']: 800, CAIXAS['c']: 0}, saldos())
    _, t7 = t(a, b, 250)

    # 3. Bens: so na Empresa. Pessoal recusa; o perfil temporario passa a Empresa pelo proprio aplicativo.
    s, r = chamar('criar_bem_patrimonial', {'p_perfil_id': perfil, 'p_chave': k(), 'p_dados': {'nome': BENS['livre']}})
    reg('bem no perfil Pessoal recusado (SO_EMPRESA)', s == 400 and hint(r) == 'SO_EMPRESA', (s, hint(r)))
    st, _ = chamar('atualizar_perfil', {'p_perfil_id': perfil, 'p_dados': {'tipo': 'EMPRESA'}})
    docs = documentos(perfil)
    s, vinc = chamar('patrimonio_documentos_vinculaveis_tela', {'p_perfil_id': perfil, 'p_busca': None})
    reg('perfil como Empresa; 3 documentos ficticios vinculaveis', st == 200 and s == 200 and sorted(d['id'] for d in vinc) == sorted(docs),
        (st, s, len(vinc or [])))
    ch = k()
    s1, livre = chamar('criar_bem_patrimonial', {'p_perfil_id': perfil, 'p_chave': ch, 'p_dados': {
        'nome': BENS['livre'], 'categoria': 'Moveis', 'valor_aquisicao': 1200, 'vida_util_meses': 60, 'data_aquisicao': '2026-07-01'}})
    s1b, livre_b = chamar('criar_bem_patrimonial', {'p_perfil_id': perfil, 'p_chave': ch, 'p_dados': {'nome': BENS['livre']}})
    s2, com = chamar('criar_bem_patrimonial', {'p_perfil_id': perfil, 'p_chave': k(), 'p_dados': {
        'nome': BENS['doc'], 'categoria': 'Informatica', 'valor_aquisicao': 7500.555, 'vida_util_meses': 36, 'comprovante_id': docs[0]}})
    bem = M.ler('select status_documental, valor_aquisicao, depreciacao_mensal from public.bem_patrimonial where id = %s', (com['bem_id'],))[0]
    reg('criar bens (reenvio nao duplica); com documento: COM_LASTRO, valor 7500.56, depreciacao 208.35',
        (s1, s1b, s2) == (200, 200, 200) and livre_b == livre and bem['status_documental'] == 'COM_LASTRO'
        and float(bem['valor_aquisicao']) == 7500.56 and float(bem['depreciacao_mensal']) == 208.35, bem)
    s3, dup = chamar('vincular_documento_bem', {'p_perfil_id': perfil, 'p_bem_id': livre['bem_id'], 'p_dados': {'comprovante_id': docs[0]}})
    reg('documento ja vinculado a outro bem: recusado', s3 == 400 and 'ja esta vinculado' in str((dup or {}).get('message')), (s3, (dup or {}).get('message')))
    s4, de_doc = chamar('criar_bem_de_documento', {'p_perfil_id': perfil, 'p_chave': k(), 'p_dados': {'comprovante_id': docs[1]}})
    s5, _ = chamar('vincular_documento_bem', {'p_perfil_id': perfil, 'p_bem_id': com['bem_id'],
                                              'p_dados': {'comprovante_id': docs[2], 'natureza': 'outro', 'observacoes': 'troca'}})
    vinculos = M.ler("select comprovante_id, ativo from public.ir_comprovante_vinculo where tipo_entidade = 'PATRIMONIO' and entidade_id = %s "
                     'order by id', (com['bem_id'],))
    reg('bem a partir de documento; troca de documento desativa o vinculo anterior (historico)',
        (s4, s5) == (200, 200) and [(v['comprovante_id'], v['ativo']) for v in vinculos] == [(docs[0], False), (docs[2], True)],
        (s4, s5, vinculos))
    s6, _ = chamar('editar_bem_patrimonial', {'p_perfil_id': perfil, 'p_bem_id': com['bem_id'], 'p_dados': {'nome': BENS['edit']}})
    s7, r7 = chamar('excluir_bem_patrimonial', {'p_perfil_id': perfil, 'p_bem_id': com['bem_id']})
    s8, r8 = chamar('excluir_bem_patrimonial', {'p_perfil_id': perfil, 'p_bem_id': livre['bem_id']})
    reg('editar bem; com documento nao exclui (COM_DOCUMENTO); sem documento exclui',
        s6 == 200 and s7 == 400 and hint(r7) == 'COM_DOCUMENTO' and s8 == 200 and (r8 or {}).get('excluido') is True, (s6, s7, hint(r7), s8))
    s9, sug = chamar('patrimonio_documento_sugestao_tela', {'p_perfil_id': perfil, 'p_comprovante_id': docs[0]})
    reg('dados para a sugestao a partir de documento', s9 == 200 and isinstance(sug, dict), (s9, sorted(sug)[:6] if isinstance(sug, dict) else sug))

    # 4. Perfil passado ao Flask: as escritas sao recusadas (SISTEMA_FLASK) e nada muda no perfil.
    L.atribuir(perfil, 'FLASK')
    try:
        antes = C.linhas_do_perfil(perfil)
        tentativas = {
            'criar_caixinha': {'p_perfil_id': perfil, 'p_chave': k(), 'p_dados': {'nome': 'Nao grava'}},
            'editar_caixinha': {'p_perfil_id': perfil, 'p_conta_id': a, 'p_dados': {'meta': 1}},
            'inativar_caixinha': {'p_perfil_id': perfil, 'p_conta_id': a},
            'criar_transferencia_patrimonio': {'p_perfil_id': perfil, 'p_chave': k(), 'p_dados': {'conta_origem_id': a, 'conta_destino_id': b,
                                                                                                 'valor': 1, 'data_transferencia': '2026-10-06'}},
            'excluir_transferencia_patrimonio': {'p_perfil_id': perfil, 'p_transferencia_id': t7['transferencia_id']},
            'criar_bem_patrimonial': {'p_perfil_id': perfil, 'p_chave': k(), 'p_dados': {'nome': 'Nao grava'}},
            'editar_bem_patrimonial': {'p_perfil_id': perfil, 'p_bem_id': com['bem_id'], 'p_dados': {'nome': 'Nao grava'}},
            'excluir_bem_patrimonial': {'p_perfil_id': perfil, 'p_bem_id': de_doc['bem_id']},
        }
        recusadas = {f: (lambda sr: (sr[0], hint(sr[1])))(chamar(f, corpo)) for f, corpo in tentativas.items()}
        reg('perfil no Flask: as 8 escritas recusadas com SISTEMA_FLASK', all(h == 'SISTEMA_FLASK' for _, h in recusadas.values()), recusadas)
        reg('perfil no Flask: nada mudou no perfil (todas as tabelas)', C.linhas_do_perfil(perfil) == antes)
    finally:
        L.atribuir(perfil, 'NOVO')

    # 5. Quem so le recebe 403; mas le as telas.
    s, _ = chamar('criar_caixinha', {'p_perfil_id': perfil, 'p_chave': k(), 'p_dados': {'nome': 'Invasao'}}, tb)
    s2, _ = chamar('criar_transferencia_patrimonio', {'p_perfil_id': perfil, 'p_chave': k(), 'p_dados': {
        'conta_origem_id': a, 'conta_destino_id': b, 'valor': 1}}, tb)
    s3, _ = chamar('patrimonio_contas_tela', {'p_perfil_id': perfil, 'p_ativo': None}, tb)
    reg('LEITOR: escritas recusadas (403); leitura das caixinhas permitida', s in (401, 403) and s2 in (401, 403) and s3 == 200, (s, s2, s3))

    # 6. Leituras da tela depois da escrita.
    s, contas = chamar('patrimonio_contas_tela', {'p_perfil_id': perfil, 'p_ativo': None})
    s2, bens = chamar('patrimonio_bens_tela', {'p_perfil_id': perfil, 'p_filtros': {}, 'p_bem_id': None})
    reg('telas leem o que foi gravado (caixinhas e bens)', s == 200 and s2 == 200 and json.dumps(contas).count(MARCA) >= 3,
        (s, s2, saldos()))
    falhas = [nome for nome, ok in L.RESULTADOS if not ok]
    print(f'{len(L.RESULTADOS) - len(falhas)}/{len(L.RESULTADOS)} OK', '| falhas:', falhas or 'nenhuma')
    return 1 if falhas else 0


C.SPEC_PAT = C.SPEC.replace("FIN-CATEGORIAS-RECORRENCIAS-2", "FIN-PATRIMONIO-2").replace(
    """        if (pagina === 'recorrencias.html') {
            await expect(page.locator(':is(strong, td, span, div, h3, h4):visible', { hasText: 'Diarista (e2e-real)' }).first()).toBeVisible();
            await expect(page.locator(':is(strong, td, span, div, h3, h4):visible', { hasText: 'Jardinagem (e2e-real)' }).first()).toBeVisible();
        }
        if (pagina === 'receitas.html') await expect(page.locator(':is(strong, td, span, div, h3, h4):visible', { hasText: 'Salario base (e2e-real)' }).first()).toBeVisible();
""", """        if (pagina === 'patrimonio.html') {
            await expect(page.locator(':is(strong, td, span, div, h3, h4):visible', { hasText: 'Notebook editado (e2e-real)' }).first()).toBeVisible();
            await expect(page.locator(':is(strong, td, span, div, h3, h4):visible', { hasText: 'Moveis ficticios ME (e2e-real)' }).first()).toBeVisible();
        }
""")


def ui(web):
    assert 'Notebook editado (e2e-real)' in C.SPEC_PAT  # perfil Empresa: a tela e a de bens
    C.SPEC = C.SPEC_PAT
    return C.ui(web)


def limpar(confirmar):
    C.MARCA = MARCA
    estado = json.loads(L.ESTADO.read_text(encoding='utf-8'))
    conn = L.conectar()
    try:
        with conn.cursor() as cur:
            a, _ = L.usuarios(cur)
            perfil, _ = L.identificar(cur, a)
            if perfil != estado['perfil'] or perfil in L.PROTEGIDOS:
                raise SystemExit('Perfil identificado difere do estado gravado: interrompido.')
            for tabela, coluna in (('conta_patrimonio', 'nome'), ('bem_patrimonial', 'nome'), ('ir_comprovante', 'prestador_nome')):
                cur.execute(f"select count(*) from public.{tabela} where perfil_financeiro_id = %s and coalesce({coluna}, '') not like %s",
                            (perfil, f'%{MARCA}'))
                if cur.fetchone()[0]:
                    raise SystemExit(f'{tabela} fora do teste no perfil temporario: interrompido.')
    finally:
        conn.close()
    C.limpar(confirmar)


if __name__ == '__main__':
    PASTA.mkdir(parents=True, exist_ok=True)
    etapa = sys.argv[1]
    if etapa == 'inspecionar':
        sys.exit(inspecionar())
    if etapa == 'aplicar':
        sys.exit(aplicar())
    if etapa == 'criar':
        L.PASTA = PASTA
        L.criar()
    if etapa == 'api':
        sys.exit(api())
    if etapa == 'ui':
        sys.exit(ui(sys.argv[2]))
    if etapa == 'limpar':
        limpar('--confirmar' in sys.argv)
