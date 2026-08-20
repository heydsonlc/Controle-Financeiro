"""
Helpers compartilhados de teste.

SEG-1: testes que usam create_app() real (nao um app isolado por blueprint)
passam a exigir sessao autenticada, porque o gate de autenticacao global
vive em create_app()/app.py. autenticar_cliente_teste() cria um usuario de
teste descartavel (banco em memoria, nunca persiste) e faz login via
POST /login, devolvendo o mesmo client ja autenticado.
"""
from backend.models import Usuario, db

EMAIL_TESTE = 'teste-suite@local.invalido'
SENHA_TESTE = 'senha-teste-suite-123'


def autenticar_cliente_teste(client, app):
    """Cria um usuario de teste e autentica `client` via POST /login."""
    with app.app_context():
        if not Usuario.query.filter_by(email=EMAIL_TESTE).first():
            usuario = Usuario(email=EMAIL_TESTE, nome='Suite de Testes', ativo=True)
            usuario.definir_senha(SENHA_TESTE)
            db.session.add(usuario)
            db.session.commit()

    client.post('/login', data={'email': EMAIL_TESTE, 'senha': SENHA_TESTE})
    return client
