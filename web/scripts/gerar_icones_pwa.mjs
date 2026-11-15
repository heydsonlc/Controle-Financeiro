// FIN-MVP-MOBILE-ICON-01: icones do aplicativo (PWA/iOS) a partir do icone de carteira do portal (icone-carteira-portal.svg,
// sem redesenho), sobre o fundo do portal (#0a0a0c). O SVG e desenhado pelo Chromium do Playwright, o mesmo motor que o
// exibe no portal. Substitui o gerador da marca do desktop (FIN-MVP-MOBILE-FINAL-01).
// Uso (em web/): node scripts/gerar_icones_pwa.mjs src/icones
import { mkdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';

const AQUI = path.dirname(fileURLToPath(import.meta.url));
const FUNDO = '#0a0a0c';
const svg = readFileSync(path.join(AQUI, 'icone-carteira-portal.svg'), 'utf8').replace(/<!--[\s\S]*?-->\s*/, '');

// fracao: lado do viewBox (64) em relacao ao icone; o desenho ocupa 56 x 50 do viewBox, centrado.
const ICONES = [
    // iOS arredonda os cantos sozinho: quadrado inteiro no fundo do portal, sem transparencia.
    { arquivo: 'apple-touch-icon.png', lado: 180, fracao: 0.72 },
    { arquivo: 'icone-192.png', lado: 192, fracao: 0.72 },
    { arquivo: 'icone-512.png', lado: 512, fracao: 0.72 },
    // "maskable": o desenho inteiro dentro da zona segura (circulo de 80%).
    { arquivo: 'icone-maskable-512.png', lado: 512, fracao: 0.62 },
    // Aba do navegador (paginas mobile): quadrado de cantos arredondados, desenho maior para ser legivel em 32 px.
    { arquivo: 'icone-32.png', lado: 32, fracao: 0.9, raio: 7, transparente: true },
];

const saida = path.resolve(process.argv[2] || path.join(AQUI, '..', 'src', 'icones'));
mkdirSync(saida, { recursive: true });
const navegador = await chromium.launch();
try {
    for (const { arquivo, lado, fracao, raio = 0, transparente = false } of ICONES) {
        const pagina = await navegador.newPage({ viewport: { width: lado, height: lado }, deviceScaleFactor: 1 });
        const caixa = lado * fracao;
        await pagina.setContent(`<!DOCTYPE html><html><head><style>
            html, body { margin: 0; width: ${lado}px; height: ${lado}px; background: transparent; }
            .fundo { width: ${lado}px; height: ${lado}px; border-radius: ${raio}px; background: ${FUNDO};
                     display: flex; align-items: center; justify-content: center; }
            svg { width: ${caixa}px; height: ${caixa}px; display: block; }
        </style></head><body><div class="fundo">${svg}</div></body></html>`);
        await pagina.screenshot({ path: path.join(saida, arquivo), omitBackground: transparente });
        await pagina.close();
        console.log(`${arquivo} ${lado}x${lado}`);
    }
} finally {
    await navegador.close();
}
