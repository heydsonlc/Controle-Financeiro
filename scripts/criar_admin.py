"""
SEG-1: cria o usuario de autenticacao da aplicacao (uso local/administrativo).

A senha nunca e impressa no terminal, nunca e logada e nunca e salva em
arquivo — so existe em memoria durante a execucao e como hash no banco.

Por padrao, o script FALHA se o e-mail informado ja existir. Use --reset
para redefinir a senha de um usuario existente explicitamente.

Uso interativo (recomendado — a senha e digitada sem eco no terminal):
    venv/Scripts/python.exe scripts/criar_admin.py --email heydson@gmail.com
    venv/Scripts/python.exe scripts/criar_admin.py --email heydson@gmail.com --reset

Uso com argumento de senha (evite em maquinas compartilhadas: fica no
historico do shell e em `ps`/Gerenciador de Tarefas durante a execucao):
    venv/Scripts/python.exe scripts/criar_admin.py --email heydson@gmail.com --senha "..."

Uso via variaveis de ambiente (ex.: setup automatizado/CI local):
    ADMIN_EMAIL=heydson@gmail.com ADMIN_SENHA=... venv/Scripts/python.exe scripts/criar_admin.py

Em qualquer modo, se a senha nao vier de --senha nem de ADMIN_SENHA, o
script pede no prompt (getpass, sem eco) e pede confirmacao.
"""
import argparse
import os
import sys
import getpass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app import create_app
from backend.models import db, Usuario


def _resolver_email(args):
    email = args.email or os.environ.get('ADMIN_EMAIL', '')
    email = email.strip().lower()
    if not email:
        email = input('E-mail: ').strip().lower()
    if not email:
        print('E-mail e obrigatorio.')
        sys.exit(1)
    return email


def _resolver_senha(args):
    if args.senha:
        return args.senha
    if os.environ.get('ADMIN_SENHA'):
        return os.environ['ADMIN_SENHA']

    senha = getpass.getpass('Senha: ')
    confirmacao = getpass.getpass('Confirme a senha: ')
    if senha != confirmacao:
        print('Senhas nao conferem.')
        sys.exit(1)
    return senha


def main():
    parser = argparse.ArgumentParser(description='Cria ou redefine o usuario de autenticacao.')
    parser.add_argument('--email', help='E-mail do usuario. Tambem pode vir de ADMIN_EMAIL.')
    parser.add_argument('--senha', help='Senha em texto puro. Evite em maquinas compartilhadas; prefira o prompt.')
    parser.add_argument('--reset', action='store_true', help='Permite redefinir a senha se o e-mail ja existir.')
    args = parser.parse_args()

    email = _resolver_email(args)
    senha = _resolver_senha(args)

    if len(senha) < 8:
        print('Senha deve ter ao menos 8 caracteres.')
        sys.exit(1)

    app = create_app()
    with app.app_context():
        usuario = Usuario.query.filter_by(email=email).first()

        if usuario and not args.reset:
            print(f'Usuario {email} ja existe. Use --reset para redefinir a senha.')
            sys.exit(1)

        if usuario:
            usuario.definir_senha(senha)
            usuario.ativo = True
            acao = 'atualizado'
        else:
            usuario = Usuario(email=email, nome=email.split('@')[0])
            usuario.definir_senha(senha)
            db.session.add(usuario)
            acao = 'criado'

        db.session.commit()
        print(f'Usuario {acao}: {email}')


if __name__ == '__main__':
    main()
