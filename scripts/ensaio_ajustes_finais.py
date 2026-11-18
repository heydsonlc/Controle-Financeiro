"""FIN-MULTIUSUARIO-AJUSTES-FINAIS-01 — ensaio encadeado das TRES migrations (com os ajustes finais incorporados) numa copia
fiel da producao, em PostgreSQL DESCARTAVEL local.

    python scripts/ensaio_ajustes_finais.py --saida <pasta privada> --pessoais <arquivo.json> [--backup-id ID]

Roda os ensaios das tres etapas (seguranca, cadastros padrao, acesso), que ja medem migration, carga e reversao de cada uma,
e, sobre o estado final, confere a acao "Alterar categoria" da palavra-chave (que faz parte das migrations 20270101090000 e
20270102090000): um usuario ficticio altera a categoria de uma palavra-chave padrao; nada muda para o titular (telas e
sugestoes identicas); so a tabela de ajustes do usuario muda; repetir nao duplica; restaurar devolve a regra padrao.
O relatorio vai SO para a pasta privada indicada. Nada e impresso alem do resumo.
"""
import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / 'scripts'))

import psycopg2  # noqa: E402

import ensaio_cadastros_padrao as E2  # noqa: E402
import ensaio_multiusuario_acesso as E3  # noqa: E402
import ensaio_multiusuario_seguranca as E1  # noqa: E402

consulta, diferencas, chamar = E1.consulta, E1.diferencas, E3.chamar


def etapa_ajustes(x):
    conferir, rel, titular, perfis, outro, perfil_outro = x['conferir'], x['rel'], x['titular'], x['perfis'], x['outro'], x['perfil_do_outro']
    conn, cur = x['abrir']()

    def retrato():
        r = E2.retrato(cur)
        conn.rollback()
        return r

    def sugestoes():
        r = E2.sugestoes(cur, perfis)
        conn.rollback()
        return r

    base = {'leituras': E2.leituras(conn, titular, perfis), 'sugestoes': sugestoes()}

    rel['ajustes'] = {'leituras_do_titular': len(base['leituras']), 'descricoes_com_sugestao_medida': len(base['sugestoes'])}

    # ------------------------------------------------------------ 2. um usuario ficticio altera a categoria de palavras-chave
    padrao = consulta(cur, """select p.id, p.categoria_id, lower(btrim(p.palavra)) palavra from public.categoria_palavra_chave p
                               where p.ativo and not exists (select 1 from financeiro.palavra_chave_usuario u where u.palavra = lower(btrim(p.palavra)))
                               order by p.id limit 1""")[0]
    destino = consulta(cur, """select c.id from public.categoria c where c.user_id is null and coalesce(c.ativo, true) and c.id <> %s
                                and not exists (select 1 from public.categoria_palavra_chave p where p.categoria_id = c.id and p.ativo and lower(btrim(p.palavra)) = %s)
                                order by c.id limit 1""", (padrao['categoria_id'], padrao['palavra']))[0]['id']
    conn.rollback()
    antes = retrato()
    n_ajustes = consulta(cur, 'select count(*) n from financeiro.palavra_chave_usuario')[0]['n']
    conn.rollback()
    r = chamar(conn, cur, outro, 'select financeiro.alterar_categoria_da_palavra_chave(%s, %s) j', (padrao['id'], destino))
    conferir('ajustes/alterar: o usuario leva a palavra padrao para outra categoria (so para ele)', r[0] == 'OK' and r[1]['origem'] == 'REASSOCIADA', r[0])
    # (a tabela de ajustes de palavras-chave fica fora do retrato: e estrutura do multiusuario, conferida pela contagem)
    conferir('ajustes/alterar: so a tabela de ajustes do usuario muda (nenhuma compra, despesa ou saldo)',
             diferencas(antes, retrato()) == [] and consulta(cur, 'select count(*) n from financeiro.palavra_chave_usuario')[0]['n'] == n_ajustes + 1,
             diferencas(antes, retrato()))
    conn.rollback()
    conferir('ajustes/alterar: leituras de tela do titular identicas', diferencas(base['leituras'], E2.leituras(conn, titular, perfis)) == [])
    conferir('ajustes/alterar: sugestoes de categoria do titular identicas', sugestoes() == base['sugestoes'])
    s = consulta(cur, 'select financeiro.sugestao_categoria_importacao(%s, %s, %s, null) j', (perfil_outro, padrao['palavra'], padrao['palavra']))[0]['j']
    conn.rollback()
    conferir('ajustes/alterar: para o usuario, a sugestao passa a ser a categoria escolhida', (s or {}).get('categoria_id') == destino, (s or {}).get('categoria_id'))
    r2 = chamar(conn, cur, outro, 'select financeiro.alterar_categoria_da_palavra_chave(%s, %s) j', (padrao['id'], destino))
    conferir('ajustes/alterar: repetir nao duplica', r2[0] == 'OK' and r2[1]['alterada'] is False
             and consulta(cur, 'select count(*) n from financeiro.palavra_chave_usuario where palavra = %s', (padrao['palavra'],))[0]['n'] == 1)
    conn.rollback()
    r3 = chamar(conn, cur, titular, 'select financeiro.alterar_categoria_da_palavra_chave(%s, %s) j', (r[1]['id'] if r[0] == 'OK' else -1, padrao['categoria_id']))
    conferir('ajustes/alterar: o titular nao alcanca o ajuste do outro usuario', r3[0] == 'P0001' and r3[1] == 'NAO_ENCONTRADA', r3)
    r4 = chamar(conn, cur, outro, 'select financeiro.alterar_categoria_da_palavra_chave(%s, %s) j', (padrao['id'], padrao['categoria_id']))
    conferir('ajustes/alterar: voltar a categoria padrao restaura (banco identico ao de antes)', r4[0] == 'OK' and r4[1].get('restaurada') is True
             and diferencas(antes, retrato()) == []
             and consulta(cur, 'select count(*) n from financeiro.palavra_chave_usuario')[0]['n'] == n_ajustes, r4[0])
    conn.rollback()

    conferir('ajustes/alterar: depois de restaurar, leituras e sugestoes do titular identicas',
             diferencas(base['leituras'], E2.leituras(conn, titular, perfis)) == [] and sugestoes() == base['sugestoes'])
    conn.close()


def continuar(x):
    E3.etapa_acesso(x)
    etapa_ajustes(x)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--saida', required=True, help='pasta privada do relatorio (fora do repositorio)')
    ap.add_argument('--pessoais', required=True, help='JSON com a lista de palavras-chave pessoais (a mesma dos ensaios anteriores)')
    ap.add_argument('--backup-id')
    a = ap.parse_args(argv)
    saida = Path(a.saida).resolve()
    if RAIZ in saida.parents or saida == RAIZ:
        raise SystemExit('A pasta do relatorio tem de ficar FORA do repositorio.')
    rel = E2.ensaiar(saida, json.loads(Path(a.pessoais).read_text(encoding='utf-8')), a.backup_id, depois=continuar)
    proprias = [v for v in rel['verificacoes'] if v['verificacao'].startswith('ajustes/')]
    for v in proprias:
        print(('ok    ' if v['resultado'] == 'ok' else 'FALHA ') + v['verificacao'] + (f" [{v['detalhe']}]" if v['resultado'] != 'ok' and v['detalhe'] else ''))
    print(f"backup {rel['backup_id']} | {len(rel['verificacoes'])} verificacoes ({len(proprias)} desta etapa) | {len(rel['falhas'])} falha(s)")
    return 1 if rel['falhas'] else 0


if __name__ == '__main__':
    sys.exit(main())
