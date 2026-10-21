"""
PERFIS-REAL-1 — dados FICTICIOS temporarios para validar perfis no Supabase real.

Usa os perfis existentes "Pessoal" e "Empresa" (nunca cria nem altera). Cria, de
forma identificavel e so para o teste:
- 2 perfis temporarios: "Perfil B" (ativo) e "Perfil inativo (A)" (inativo);
- 5 contas bancarias ficticias (instituicao com o marcador do teste), uma delas
  sem perfil para validar a regra NULL -> Pessoal do Flask;
- 4 vinculos: A -> Pessoal (TITULAR), A -> Empresa (LEITOR), A -> inativo, B -> Perfil B.
O que foi criado fica em data/perfis_real_1_teste.json (fora do Git) e e o UNICO
alvo do --remover.

Recusa: projeto da Calculadora; contas de teste com vinculos preexistentes;
contas bancarias preexistentes sem perfil (mudariam o resultado esperado).
Sem --confirmar, executa e desfaz (rollback). Nao imprime e-mails completos.

Uso:
    scripts/supabase_perfis_seed_teste.py --email-a A --email-b B [--confirmar]
    scripts/supabase_perfis_seed_teste.py --remover [--confirmar]
"""
import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

RAIZ = Path(__file__).resolve().parent.parent
ESTADO = RAIZ / 'data' / 'perfis_real_1_teste.json'
MARCADOR = 'Banco ficticio [teste PERFIS-REAL-1]'
PROJETOS_PROIBIDOS = {'dshqjhyymtpxpxuntzbz'}
PERFIS_TEMPORARIOS = [('PERFIL_B', 'Perfil B', 'PESSOAL', True), ('INATIVO_A', 'Perfil inativo (A)', 'EMPRESA', False)]
CONTAS = [('Conta Pessoal (A)', 'PESSOAL'), ('Carteira legado sem perfil', None), ('Conta Empresa (A)', 'EMPRESA'),
          ('Conta Perfil B', 'PERFIL_B'), ('Conta do perfil inativo', 'INATIVO_A')]
VINCULOS = [('A', 'PESSOAL', 'TITULAR'), ('A', 'EMPRESA', 'LEITOR'), ('A', 'INATIVO_A', 'TITULAR'), ('B', 'PERFIL_B', 'TITULAR')]


def mascarar(email):
    nome, _, dominio = email.partition('@')
    return f'{nome[:2]}***@{dominio}'


def conectar():
    import psycopg2
    from dotenv import dotenv_values
    url = dotenv_values(RAIZ / '.env.staging', encoding='utf-8-sig').get('DATABASE_URL') or ''
    usuario = urlsplit(url).username or ''
    ref = usuario.split('.', 1)[1] if usuario.startswith('postgres.') else ''
    if not ref or ref in PROJETOS_PROIBIDOS:
        raise SystemExit('Projeto invalido ou proibido no .env.staging.')
    conn = psycopg2.connect(url, connect_timeout=15)
    conn.autocommit = False
    return conn


def criar(cur, email_a, email_b):
    usuarios = {}
    for rotulo, email in (('A', email_a), ('B', email_b)):
        cur.execute('select id from auth.users where lower(email) = %s', (email.strip().lower(),))
        linha = cur.fetchone()
        if not linha:
            raise SystemExit(f'Conta {rotulo} ({mascarar(email)}) nao existe no Auth.')
        usuarios[rotulo] = str(linha[0])
    cur.execute('select count(*) from financeiro.perfil_acesso where user_id = any(%s::uuid[])', (list(usuarios.values()),))
    if cur.fetchone()[0]:
        raise SystemExit('As contas de teste ja tem vinculos: nada feito (preserva vinculos preexistentes).')
    cur.execute('select count(*) from public.conta_bancaria where perfil_financeiro_id is null')
    if cur.fetchone()[0]:
        raise SystemExit('Ha contas bancarias sem perfil preexistentes: o teste do Pessoal ficaria ambiguo.')

    perfis = {}
    for chave, nome in (('PESSOAL', 'Pessoal'), ('EMPRESA', 'Empresa')):
        cur.execute('select id from public.perfil_financeiro where nome = %s and ativo', (nome,))
        linha = cur.fetchone()
        if not linha:
            raise SystemExit(f'Perfil existente "{nome}" nao encontrado ativo.')
        perfis[chave] = linha[0]
    for chave, nome, tipo, ativo in PERFIS_TEMPORARIOS:
        cur.execute('select count(*) from public.perfil_financeiro where nome = %s', (nome,))
        if cur.fetchone()[0]:
            raise SystemExit(f'Ja existe um perfil chamado "{nome}": nada feito.')
        cur.execute("insert into public.perfil_financeiro (nome, tipo, cor, ativo, padrao, created_at, updated_at) "
                    "values (%s, %s, '#64748b', %s, false, now(), now()) returning id", (nome, tipo, ativo))
        perfis[chave] = cur.fetchone()[0]

    contas = []
    for nome, chave in CONTAS:
        cur.execute("insert into public.conta_bancaria (perfil_financeiro_id, nome, instituicao, tipo, status, cor_display, "
                    "saldo_inicial, saldo_atual, data_criacao, data_atualizacao) "
                    "values (%s, %s, %s, 'Conta Corrente', 'ATIVO', '#3b82f6', 0, 0, now(), now()) returning id",
                    (perfis[chave] if chave else None, nome, MARCADOR))
        contas.append(cur.fetchone()[0])

    vinculos = []
    for rotulo, chave, papel in VINCULOS:
        cur.execute('insert into financeiro.perfil_acesso (user_id, perfil_financeiro_id, papel) values (%s, %s, %s)',
                    (usuarios[rotulo], perfis[chave], papel))
        vinculos.append([usuarios[rotulo], perfis[chave]])

    return {'perfis_temporarios': [perfis['PERFIL_B'], perfis['INATIVO_A']], 'contas': contas,
            'vinculos': vinculos, 'id_perfil_b': perfis['PERFIL_B'],
            'ids_existentes_usados': {'Pessoal': perfis['PESSOAL'], 'Empresa': perfis['EMPRESA']}}


def remover(cur, estado):
    removidos = {'vinculos': 0, 'contas': 0, 'perfis': 0}
    for user_id, perfil_id in estado['vinculos']:
        cur.execute('delete from financeiro.perfil_acesso where user_id = %s and perfil_financeiro_id = %s', (user_id, perfil_id))
        removidos['vinculos'] += cur.rowcount
    cur.execute('delete from public.conta_bancaria where id = any(%s) and instituicao = %s', (estado['contas'], MARCADOR))
    removidos['contas'] = cur.rowcount
    nomes = [nome for _, nome, _, _ in PERFIS_TEMPORARIOS]
    cur.execute('delete from public.perfil_financeiro where id = any(%s) and nome = any(%s)', (estado['perfis_temporarios'], nomes))
    removidos['perfis'] = cur.rowcount
    return removidos


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--email-a')
    parser.add_argument('--email-b')
    parser.add_argument('--remover', action='store_true')
    parser.add_argument('--confirmar', action='store_true')
    args = parser.parse_args()

    conn = conectar()
    try:
        with conn.cursor() as cur:
            if args.remover:
                if not ESTADO.exists():
                    raise SystemExit('Sem estado de teste para remover.')
                estado = json.loads(ESTADO.read_text(encoding='utf-8'))
                resultado = remover(cur, estado)
                print('Removidos:', resultado)
            else:
                if not (args.email_a and args.email_b):
                    raise SystemExit('Informe --email-a e --email-b.')
                if ESTADO.exists():
                    raise SystemExit('Ja existe estado de teste: remova antes de criar de novo.')
                estado = criar(cur, args.email_a, args.email_b)
                print(f"Criados: 2 perfis temporarios, {len(estado['contas'])} contas ficticias, "
                      f"{len(estado['vinculos'])} vinculos | perfis existentes usados: {estado['ids_existentes_usados']}")
        if args.confirmar:
            conn.commit()
            if args.remover:
                ESTADO.unlink()
            else:
                ESTADO.parent.mkdir(parents=True, exist_ok=True)
                ESTADO.write_text(json.dumps(estado, indent=1), encoding='utf-8')
                print(f"CF_ID_PERFIL_B={estado['id_perfil_b']}")
            print('CONFIRMADO: alteracoes gravadas.')
        else:
            conn.rollback()
            print('SIMULACAO: nada foi gravado (use --confirmar).')
    finally:
        conn.close()


if __name__ == '__main__':
    sys.exit(main())
