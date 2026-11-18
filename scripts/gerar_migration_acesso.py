"""Gera a migration 20270102090000 (FIN-MULTIUSUARIO-ACESSO-01) e a reversao a partir da definicao VIGENTE das funcoes.

A parte estrutural (conta da plataforma, convites, ativacao, administracao) esta em scripts/acesso_estrutura.sql. As funcoes
expostas que NAO recebem perfil (e por isso nao passam pelas funcoes centrais de acesso ao perfil) recebem, no inicio, a
exigencia de conta ativa: a definicao vigente e lida de um PostgreSQL local descartavel com as migrations anteriores
aplicadas e so essa linha e acrescentada. Nenhum dado real, conexao remota ou credencial.

    python scripts/gerar_migration_acesso.py              # grava a migration e a reversao
    python scripts/gerar_migration_acesso.py --verificar  # so compara com os arquivos versionados
"""
import argparse
import re
import sys
import tempfile
from pathlib import Path

_args = argparse.ArgumentParser(description=__doc__.splitlines()[0])
_args.add_argument('--verificar', action='store_true', help='nao grava: falha se a saida difere dos arquivos versionados')
ARGS = _args.parse_args()
RAIZ = Path(__file__).resolve().parents[1]
MIG = RAIZ / 'supabase' / 'migrations'
VERSAO = '20270102090000'
SAIDA = MIG / f'{VERSAO}_financeiro_multiusuario_acesso.sql'
REVERSAO = RAIZ / 'supabase' / 'reversao' / f'{VERSAO}_multiusuario_acesso_anterior.sql'
ANTERIORES = sorted(p for p in MIG.glob('*.sql') if p.name < VERSAO)
# Reescritas a mao em acesso_estrutura.sql (a reversao devolve o texto anterior).
NA_ESTRUTURA = ['pode_acessar_perfil', 'pode_gerir_perfil', 'gere_perfil', 'meus_perfis', 'perfis_para_configuracao', 'categorias_de_despesa',
                'situacao_catalogo_categorias', 'sou_administrador_plataforma', 'e_administrador_plataforma']
# Funcoes expostas, em plpgsql, sem perfil: recebem "perform financeiro.exigir_conta_ativa();" como primeira instrucao.
COM_EXIGENCIA = ['criar_perfil', 'criar_categoria', 'editar_categoria', 'excluir_categoria', 'definir_natureza_categoria', 'naturezas_das_categorias',
                 'criar_palavra_chave', 'remover_palavra_chave', 'criar_minha_palavra_chave', 'desligar_palavra_chave_padrao',
                 'reassociar_palavra_chave_padrao', 'remover_minha_palavra_chave', 'restaurar_palavra_chave_padrao',
                 'categorias_cartao_padrao_tela', 'manter_categoria_cartao_padrao', 'propagar_categorias_cartao_padrao',
                 'previa_reclassificacao_categorias', 'criar_tr', 'editar_tr', 'importar_tr', 'tr_faltantes', 'tr_oficial_tela']
# Guarda interna do catalogo padrao (nao exposta): quem a chama primeiro (incorporar, reclassificar...) tambem fica coberto.
INTERNAS_COM_EXIGENCIA = ['exigir_escrita_catalogo']
# Sem perfil e sem a exigencia, de proposito: lista fixa de nomes de imagens do aplicativo (nenhum dado de usuario).
SEM_EXIGENCIA = ['imagens_patrimonio']
CENTRAIS = {'pode_acessar_perfil', 'pode_gerir_perfil', 'gere_perfil', 'meus_perfis'}


def carregar():
    sys.path.insert(0, str(RAIZ))
    from tests.supabase_local import ClusterLocal, encontrar_pg_bin
    pg = encontrar_pg_bin()
    assert pg, 'binarios do PostgreSQL nao encontrados'
    with tempfile.TemporaryDirectory(prefix='cf-gerador-', ignore_cleanup_errors=True) as tmp, ClusterLocal(pg, Path(tmp)) as c:
        c.aplicar_shim()
        c.criar_tabelas_legadas()
        conn = c.conectar()
        try:
            with conn.cursor() as cur:
                for migration in ANTERIORES:
                    cur.execute(migration.read_text(encoding='utf-8'))
                cur.execute("""select p.proname, pg_get_functiondef(p.oid), p.prosrc, l.lanname, has_function_privilege('authenticated', p.oid, 'EXECUTE')
                                 from pg_proc p join pg_namespace n on n.oid = p.pronamespace join pg_language l on l.oid = p.prolang
                                where n.nspname = 'financeiro' and p.prokind = 'f' order by 1""")
                linhas = cur.fetchall()
        finally:
            conn.close()
    return [dict(nome=a, texto=b.replace('\r\n', '\n').rstrip() + ';', corpo=c_, ling=d, exposta=e) for a, b, c_, d, e in linhas]


FUNCOES = carregar()
POR_NOME = {}
for _f in FUNCOES:
    POR_NOME.setdefault(_f['nome'], []).append(_f)


def vigente(nome):
    assert len(POR_NOME.get(nome, [])) == 1, f'{nome}: {len(POR_NOME.get(nome, []))} definicoes'
    return POR_NOME[nome][0]['texto']


# Conferencia de cobertura: toda funcao exposta ou passa por uma funcao central de acesso ao perfil (direta ou indiretamente),
# ou esta numa das listas acima. Funcao nova sem perfil que nao esteja listada interrompe a geracao.
_memo = {}


def passa_pelo_perfil(nome, pilha=()):
    if nome in CENTRAIS:
        return True
    if nome in _memo:
        return _memo[nome]
    if nome in pilha:
        return False
    chamadas = lambda f: {m for m in re.findall(r'financeiro\.(\w+)\s*\(', f['corpo']) if m in POR_NOME and m != f['nome']}  # noqa: E731
    r = all(any(passa_pelo_perfil(g, pilha + (nome,)) for g in chamadas(f)) for f in POR_NOME[nome])
    _memo[nome] = r
    return r


sem_perfil = sorted({f['nome'] for f in FUNCOES if f['exposta'] and not passa_pelo_perfil(f['nome'])})
listadas = sorted(set(NA_ESTRUTURA) - CENTRAIS - {'e_administrador_plataforma'} | set(COM_EXIGENCIA) | set(SEM_EXIGENCIA))  # a ultima nao e exposta
assert sem_perfil == listadas, f'funcoes expostas sem perfil diferentes das listadas: so no banco {sorted(set(sem_perfil) - set(listadas))}; so na lista {sorted(set(listadas) - set(sem_perfil))}'

gerado = []
for nome in COM_EXIGENCIA + INTERNAS_COM_EXIGENCIA:
    f = POR_NOME[nome]
    assert len(f) == 1 and f[0]['ling'] == 'plpgsql', nome
    linhas = f[0]['texto'].split('\n')
    inicio = next(i for i, linha in enumerate(linhas) if linha.strip().lower().startswith('as $function$'))
    primeiro = next(i for i in range(inicio + 1, len(linhas)) if linhas[i].strip().lower() == 'begin')
    assert 'exigir_conta_ativa' not in f[0]['texto'], nome
    linhas.insert(primeiro + 1, '    perform financeiro.exigir_conta_ativa();  -- FIN-MULTIUSUARIO-ACESSO-01')
    gerado.append('\n'.join(linhas))

ESTRUTURA = (RAIZ / 'scripts' / 'acesso_estrutura.sql').read_text(encoding='utf-8')
texto = ESTRUTURA.rstrip('\n') + f"""

-- =====================================================================================================================
-- 6. Funcoes sem perfil ({len(COM_EXIGENCIA)}) e a guarda do catalogo padrao: definicao vigente + a exigencia de conta ativa como primeira instrucao (nenhuma outra
--    linha muda). As funcoes COM perfil ja passam pelas funcoes centrais de acesso, que exigem a conta ativa (secao 1).
-- =====================================================================================================================
""" + '\n\n'.join(gerado) + '\n'

reversao = f"""-- FIN-MULTIUSUARIO-ACESSO-01 — reversao da migration {VERSAO}.
--
-- GERADA por scripts/gerar_migration_acesso.py: nao editar a mao.
-- NAO aplicar no Supabase remoto sem autorizacao especifica. Antes: volte o frontend ao deploy anterior.
-- Recusada enquanto houver conta SUSPENSA (a regra anterior nao conhece a suspensao: a conta voltaria a ter acesso) ou
-- convite PENDENTE. O historico de convites e a auditoria de acesso sao apagados: exporte-os antes, se precisar.

do $$
begin
    if exists (select 1 from financeiro.usuario_plataforma where situacao <> 'ATIVA') then
        raise exception 'Reversao recusada: ha conta suspensa. A regra anterior devolveria o acesso a ela.';
    end if;
    if exists (select 1 from financeiro.convite where situacao = 'PENDENTE') then
        raise exception 'Reversao recusada: ha convite pendente. Revogue-o antes.';
    end if;
end
$$;

""" + '\n\n'.join(vigente(n) for n in NA_ESTRUTURA + COM_EXIGENCIA + INTERNAS_COM_EXIGENCIA) + """

drop trigger perfil_acesso_conta on financeiro.perfil_acesso;
drop function financeiro.conta_no_vinculo();
drop function financeiro.auditoria_acesso_tela(integer);
drop function financeiro.reativar_usuario(uuid);
drop function financeiro.suspender_usuario(uuid, text);
drop function financeiro.usuarios_tela();
drop function financeiro.ativar_minha_conta(jsonb);
drop function financeiro.situacao_da_minha_conta();
drop function financeiro.convites_tela();
drop function financeiro.registrar_reenvio_convite(uuid, integer);
drop function financeiro.revogar_convite(uuid);
drop function financeiro.criar_convite(jsonb);
drop function financeiro.convite_em_json(financeiro.convite);
drop function financeiro.definir_conta_plataforma(uuid, text, text, text);
drop function financeiro.exigir_administrador();
drop function financeiro.auditar_acesso(text, text, jsonb);
drop function financeiro.exigir_conta_ativa();
drop function financeiro.conta_ativa();
drop table financeiro.usuario_plataforma;
drop table financeiro.convite;
drop table financeiro.auditoria_acesso;
"""

if ARGS.verificar:
    ok = (SAIDA.exists() and SAIDA.read_text(encoding='utf-8') == texto and REVERSAO.exists() and REVERSAO.read_text(encoding='utf-8') == reversao)
    print('igual aos arquivos versionados' if ok else 'DIFERENTE dos arquivos versionados: rode o gerador sem --verificar.')
    sys.exit(0 if ok else 1)
SAIDA.write_text(texto, encoding='utf-8', newline='\n')
REVERSAO.write_text(reversao, encoding='utf-8', newline='\n')
print(f'{SAIDA.name}: {len(texto.splitlines())} linhas | {REVERSAO.name}: {len(reversao.splitlines())} linhas; '
      f'{len(NA_ESTRUTURA) + len(COM_EXIGENCIA) + len(INTERNAS_COM_EXIGENCIA)} funcoes devolvidas')
