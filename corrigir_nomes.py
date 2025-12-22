#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from backend.app import app
from backend.models import db, ItemAgregado

def corrigir_nomes_vazios():
    with app.app_context():
        print("=" * 70)
        print("CORRIGINDO ITEMAGREADO COM NOMES VAZIOS")
        print("=" * 70)

        itens_vazios = ItemAgregado.query.filter(
            (ItemAgregado.nome == '') | (ItemAgregado.nome.is_(None))
        ).all()

        print(f"\nTotal de ItemAgregado com nome vazio: {len(itens_vazios)}")

        if not itens_vazios:
            print("\nNenhum ItemAgregado com nome vazio encontrado!")
            return

        print("\n" + "-" * 70)

        for item in itens_vazios:
            print(f"\nItemAgregado ID={item.id}")
            print(f"  Nome atual: '{item.nome}'")
            print(f"  Descricao: {item.descricao}")

            if item.descricao and item.descricao.strip():
                nome_sugerido = item.descricao.strip()[:100]
            else:
                nome_sugerido = f"Categoria {item.id}"

            item.nome = nome_sugerido
            print(f"  OK Nome atualizado para: '{item.nome}'")

        try:
            db.session.commit()
            print("\n" + "=" * 70)
            print(f"OK {len(itens_vazios)} ItemAgregado(s) atualizado(s)!")
            print("=" * 70)
        except Exception as e:
            db.session.rollback()
            print(f"\nERRO ao salvar: {e}")

if __name__ == '__main__':
    corrigir_nomes_vazios()
