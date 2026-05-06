"""
Service para palavras-chave de classificacao de Categorias de Despesa.
"""
import re
import unicodedata
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
    def normalizar_descricao_importacao(descricao):
        """Normaliza descrição para busca de palavras-chave. Não altera descrição original."""
        texto = str(descricao or '').strip().lower()
        texto = unicodedata.normalize('NFKD', texto)
        texto = ''.join(c for c in texto if not unicodedata.combining(c))
        texto = re.sub(r'[^\w\s0-9]', ' ', texto)
        texto = re.sub(r'\s+', ' ', texto)
        return texto.strip()

    @classmethod
    def classificar_por_palavras_chave(cls, descricao_normalizada):
        """
        Classifica descrição por palavras-chave cadastradas.

        Retorna dict com:
          categoria_id, categoria_nome, palavras_encontradas,
          origem, confianca, ambigua, categorias_candidatas, avisos
        """
        if not descricao_normalizada:
            return cls._resultado_sem_match()

        # Categoria de Despesa é global — sem filtro por perfil
        todas = CategoriaPalavraChave.query.filter_by(ativo=True).all()
        if not todas:
            return cls._resultado_sem_match()

        desc = cls.normalizar_descricao_importacao(descricao_normalizada)
        tokens = set(desc.split())

        # Mapeia categoria_id → {palavra_chave, ...}
        matches_por_categoria = {}
        for pk in todas:
            palavra = pk.palavra.strip()
            # suporte a palavras compostas e simples
            if ' ' in palavra:
                if palavra in desc:
                    matches_por_categoria.setdefault(pk.categoria_id, []).append(palavra)
            else:
                if palavra in tokens:
                    matches_por_categoria.setdefault(pk.categoria_id, []).append(palavra)

        if not matches_por_categoria:
            return cls._resultado_sem_match()

        categorias_candidatas = []
        for cat_id, palavras in matches_por_categoria.items():
            categoria = Categoria.query.get(cat_id)
            if categoria:
                categorias_candidatas.append({
                    'categoria_id': cat_id,
                    'categoria_nome': categoria.nome,
                    'palavras_encontradas': palavras,
                    'score': len(palavras),
                })

        categorias_candidatas.sort(key=lambda x: x['score'], reverse=True)

        if len(categorias_candidatas) == 1:
            c = categorias_candidatas[0]
            confianca = 'alta' if c['score'] >= 2 else 'alta'
            return {
                'categoria_id': c['categoria_id'],
                'categoria_nome': c['categoria_nome'],
                'palavras_encontradas': c['palavras_encontradas'],
                'origem': 'palavra_chave',
                'confianca': confianca,
                'ambigua': False,
                'categorias_candidatas': categorias_candidatas,
                'avisos': [f"Categoria sugerida por palavra-chave. Palavras encontradas: {', '.join(c['palavras_encontradas'])}."],
            }

        # Múltiplos candidatos — verificar se o melhor domina
        melhor = categorias_candidatas[0]
        segundo = categorias_candidatas[1]
        if melhor['score'] > segundo['score']:
            return {
                'categoria_id': melhor['categoria_id'],
                'categoria_nome': melhor['categoria_nome'],
                'palavras_encontradas': melhor['palavras_encontradas'],
                'origem': 'palavra_chave',
                'confianca': 'alta' if melhor['score'] >= 2 else 'media',
                'ambigua': False,
                'categorias_candidatas': categorias_candidatas,
                'avisos': [f"Categoria sugerida por palavra-chave. Palavras encontradas: {', '.join(melhor['palavras_encontradas'])}."],
            }

        # Empate: ambíguo
        palavras_ambiguas = sorted({
            palavra
            for candidata in categorias_candidatas
            for palavra in (candidata.get('palavras_encontradas') or [])
        })
        nomes = ', '.join(c['categoria_nome'] for c in categorias_candidatas[:3])
        return {
            'categoria_id': None,
            'categoria_nome': None,
            'palavras_encontradas': palavras_ambiguas,
            'origem': 'ambigua',
            'confianca': 'baixa',
            'ambigua': True,
            'categorias_candidatas': categorias_candidatas,
            'avisos': [f"Mais de uma categoria possivel. Revise antes de importar. Candidatas: {nomes}."],
        }

    @staticmethod
    def _resultado_sem_match():
        return {
            'categoria_id': None,
            'categoria_nome': None,
            'palavras_encontradas': [],
            'origem': 'sem_sugestao',
            'confianca': 'baixa',
            'ambigua': False,
            'categorias_candidatas': [],
            'avisos': ['Nenhuma palavra-chave encontrada.'],
        }

    @staticmethod
    def _validar_categoria(categoria_id):
        # Categoria de Despesa é global — sem filtro por perfil
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
