"""
Service para palavras-chave de classificacao de Categorias de Despesa.
"""
from datetime import datetime

try:
    from backend.models import Categoria, CategoriaPalavraChave, db
except ImportError:
    from models import Categoria, CategoriaPalavraChave, db


class CategoriaPalavraChaveService:
    @staticmethod
    def normalizar_palavra(palavra):
        return ' '.join(str(palavra or '').strip().lower().split())

    @staticmethod
    def _validar_categoria(categoria_id):
        categoria = Categoria.query.get(categoria_id)
        if not categoria:
            raise ValueError('Categoria de Despesa nao encontrada')
        return categoria

    @classmethod
    def listar(cls, categoria_id, ativo=True):
        cls._validar_categoria(categoria_id)
        query = CategoriaPalavraChave.query.filter_by(categoria_id=categoria_id)
        if ativo is not None:
            query = query.filter_by(ativo=bool(ativo))
        return query.order_by(CategoriaPalavraChave.palavra.asc()).all()

    @classmethod
    def criar(cls, categoria_id, palavra):
        cls._validar_categoria(categoria_id)
        palavra_normalizada = cls.normalizar_palavra(palavra)
        if not palavra_normalizada:
            raise ValueError('Palavra-chave e obrigatoria')

        existente = CategoriaPalavraChave.query.filter_by(
            categoria_id=categoria_id,
            palavra=palavra_normalizada,
        ).first()

        if existente and existente.ativo:
            raise ValueError('Palavra-chave ja cadastrada para esta categoria')

        if existente:
            existente.ativo = True
            existente.updated_at = datetime.utcnow()
            return existente, False

        palavra_chave = CategoriaPalavraChave(
            categoria_id=categoria_id,
            palavra=palavra_normalizada,
            ativo=True,
        )
        db.session.add(palavra_chave)
        return palavra_chave, True

    @classmethod
    def desativar(cls, categoria_id, palavra_id):
        cls._validar_categoria(categoria_id)
        palavra_chave = CategoriaPalavraChave.query.filter_by(
            id=palavra_id,
            categoria_id=categoria_id,
        ).first()
        if not palavra_chave:
            raise ValueError('Palavra-chave nao encontrada')

        palavra_chave.ativo = False
        palavra_chave.updated_at = datetime.utcnow()
        return palavra_chave
