// FIN-MVP-MOBILE-ICON-01: icones do aplicativo (PWA/iOS) a partir do icone de carteira do portal (icone-carteira-portal.svg,
// sem redesenho), sobre o fundo do portal (#0a0a0c). O SVG e desenhado pelo Chromium do Playwright, o mesmo motor que o
// exibe no portal. Substitui o gerador da marca do desktop (FIN-MVP-MOBILE-FINAL-01).
// Uso (em web/): node scripts/gerar_icones_pwa.mjs src/icones
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
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

// FIN-MVP-MOBILE-ICON-03: favicon.ico na raiz do site (aba do navegador no login e no desktop, e quem pede /favicon.ico),
// com 16, 32 e 48 px no estilo do icone-32 (cantos arredondados, transparente fora).
const FAVICON = [{ lado: 16, fracao: 0.94, raio: 3 }, { lado: 32, fracao: 0.9, raio: 7 }, { lado: 48, fracao: 0.9, raio: 10 }];

// ICO com imagens PNG dentro (aceito pelos navegadores atuais): cabecalho, uma entrada por tamanho e os PNG.
function montarIco(imagens) {
    const cabecalho = Buffer.alloc(6 + 16 * imagens.length);
    cabecalho.writeUInt16LE(0, 0);
    cabecalho.writeUInt16LE(1, 2);  // icone
    cabecalho.writeUInt16LE(imagens.length, 4);
    let deslocamento = cabecalho.length;
    imagens.forEach(({ lado, png }, i) => {
        const e = 6 + 16 * i;
        cabecalho.writeUInt8(lado >= 256 ? 0 : lado, e);
        cabecalho.writeUInt8(lado >= 256 ? 0 : lado, e + 1);
        cabecalho.writeUInt16LE(1, e + 4);  // planos
        cabecalho.writeUInt16LE(32, e + 6);  // bits por pixel
        cabecalho.writeUInt32LE(png.length, e + 8);
        cabecalho.writeUInt32LE(deslocamento, e + 12);
        deslocamento += png.length;
    });
    return Buffer.concat([cabecalho, ...imagens.map((i) => i.png)]);
}

const saida = path.resolve(process.argv[2] || path.join(AQUI, '..', 'src', 'icones'));
mkdirSync(saida, { recursive: true });
const navegador = await chromium.launch();

async function desenhar({ lado, fracao, raio = 0, transparente = false }, destino = undefined) {
    const pagina = await navegador.newPage({ viewport: { width: lado, height: lado }, deviceScaleFactor: 1 });
    const caixa = lado * fracao;
    await pagina.setContent(`<!DOCTYPE html><html><head><style>
        html, body { margin: 0; width: ${lado}px; height: ${lado}px; background: transparent; }
        .fundo { width: ${lado}px; height: ${lado}px; border-radius: ${raio}px; background: ${FUNDO};
                 display: flex; align-items: center; justify-content: center; }
        svg { width: ${caixa}px; height: ${caixa}px; display: block; }
    </style></head><body><div class="fundo">${svg}</div></body></html>`);
    const png = await pagina.screenshot({ path: destino, omitBackground: transparente });
    await pagina.close();
    return png;
}

try {
    for (const icone of ICONES) {
        await desenhar(icone, path.join(saida, icone.arquivo));
        console.log(`${icone.arquivo} ${icone.lado}x${icone.lado}`);
    }
    const imagens = [];
    for (const f of FAVICON) imagens.push({ lado: f.lado, png: await desenhar({ ...f, transparente: true }) });
    writeFileSync(path.join(saida, '..', 'favicon.ico'), montarIco(imagens));
    console.log(`favicon.ico ${FAVICON.map((f) => f.lado).join(', ')}`);
} finally {
    await navegador.close();
}
