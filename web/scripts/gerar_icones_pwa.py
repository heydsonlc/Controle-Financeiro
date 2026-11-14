"""FIN-MVP-MOBILE-FINAL-01: icones do aplicativo (PWA/iOS) a partir da marca do desktop (app-brand-mark: quadrado preto
#1d1d1f com o simbolo de livro-caixa em branco, viewBox 24: contorno 4..20 com raio 3,5 e tres linhas), sobre fundo
branco. Desenhado em 8x e reduzido (antisserrilhado). Uso (Pillow do venv): python -I web/scripts/gerar_icones_pwa.py web/src/icones"""
import os
import sys

from PIL import Image, ImageDraw

PRETO = (29, 29, 31, 255)
BRANCO = (255, 255, 255, 255)
ESCALA = 8


def desenhar(tamanho, fracao_tile):
    s = tamanho * ESCALA
    img = Image.new('RGBA', (s, s), BRANCO)
    d = ImageDraw.Draw(img)
    tile = s * fracao_tile
    x0 = (s - tile) / 2
    d.rounded_rectangle([x0, x0, x0 + tile, x0 + tile], radius=tile * 10 / 36, fill=PRETO)
    # O mesmo simbolo da marca, maior que no menu do desktop (20/36 do quadrado), para ser legivel na tela de inicio.
    svg = tile * 0.84
    u = svg / 24  # uma unidade do viewBox
    ox = x0 + (tile - svg) / 2
    traco = max(1, round(1.9 * u))

    def p(x, y):
        return (ox + x * u, ox + y * u)

    d.rounded_rectangle([*p(4, 4), *p(20, 20)], radius=3.5 * u, outline=BRANCO, width=traco)
    for (xa, ya, xb, yb) in ((8, 15.5, 16, 15.5), (8, 11.5, 16, 11.5), (8, 7.5, 12, 7.5)):
        d.line([p(xa, ya), p(xb, yb)], fill=BRANCO, width=traco)
        for (cx, cy) in (p(xa, ya), p(xb, yb)):  # pontas arredondadas (stroke-linecap: round)
            d.ellipse([cx - traco / 2, cy - traco / 2, cx + traco / 2, cy + traco / 2], fill=BRANCO)
    return img.resize((tamanho, tamanho), Image.LANCZOS).convert('RGB')


def main(saida):
    os.makedirs(saida, exist_ok=True)
    # iOS arredonda os cantos sozinho: icone quadrado, sem transparencia.
    desenhar(180, 0.66).save(os.path.join(saida, 'apple-touch-icon.png'), optimize=True)
    desenhar(192, 0.66).save(os.path.join(saida, 'icone-192.png'), optimize=True)
    desenhar(512, 0.66).save(os.path.join(saida, 'icone-512.png'), optimize=True)
    # "maskable": o simbolo dentro da zona segura (circulo de 80%).
    desenhar(512, 0.54).save(os.path.join(saida, 'icone-maskable-512.png'), optimize=True)
    desenhar(32, 0.86).save(os.path.join(saida, 'icone-32.png'), optimize=True)


if __name__ == '__main__':
    main(sys.argv[1])
