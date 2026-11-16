// FIN-REG-08 — leitura do arquivo no proprio navegador: texto do PDF digital (pdf.js, ja usado no aplicativo) e, quando nao
// ha texto, reconhecimento de caracteres (OCR) com o Tesseract.js 7.0.0 e o modelo de portugues, ambos hospedados no proprio
// site (vendor/tesseract-7.0.0/). Nada sai do aparelho: os caminhos do worker, do nucleo e do modelo sao todos locais (sem
// eles a biblioteca buscaria uma CDN, o que a CSP tambem bloqueia). A biblioteca so e carregada quando o OCR e pedido, e o
// worker e encerrado ao fim da leitura (memoria liberada). O modelo nao e guardado no IndexedDB (cacheMethod 'none').
// O WebAssembly do OCR depende de 'wasm-unsafe-eval' na CSP, liberado so nas paginas de documentos e nesses arquivos
// (web/scripts/build.mjs). Sem ele, ou se o OCR falhar, o documento segue para preenchimento manual.
// Tambem aqui: o preparo do arquivo antes do envio (formatos aceitos pelo banco, HEIC convertido para JPEG onde o navegador
// sabe decodificar, foto acima de 10 MB reduzida para JPEG), sempre informado e nunca no lugar do original sem aviso.

import { textoDoPdf } from './importacao-pdf.js';

const PASTA = new URL('../vendor/tesseract-7.0.0/', import.meta.url);
export const LIMITE_BYTES = 10 * 1024 * 1024;  // o limite do banco (enviar_comprovante)
const MAX_PAGINAS_OCR = 3;                      // como o Flask (OcrService.MAX_PAGINAS_OCR)
const LADO_MAXIMO_OCR = 2400;                   // foto maior e reduzida so para o OCR (o arquivo guardado e o original)
const TEMPO_MAXIMO_MS = 120000;
const TEXTO_MINIMO = 50;

const EXTENSOES = { pdf: 'application/pdf', png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', webp: 'image/webp' };
const extensao = (nome) => (/\.([A-Za-z0-9]{1,5})$/.exec(String(nome ?? '')) || [null, ''])[1].toLowerCase();

// 'pdf' | 'imagem' | 'heic' | null (formato nao aceito)
export function tipoDoArquivo(arquivo) {
    const mime = String(arquivo?.type || '').toLowerCase();
    const ext = extensao(arquivo?.name);
    if (mime === 'application/pdf' || ext === 'pdf') return 'pdf';
    if (/^image\/(heic|heif)/.test(mime) || ext === 'heic' || ext === 'heif') return 'heic';
    if (['image/png', 'image/jpeg', 'image/webp'].includes(mime) || ['png', 'jpg', 'jpeg', 'webp'].includes(ext)) return 'imagem';
    return null;
}

const tamanho = (bytes) => (bytes >= 1048576 ? `${(bytes / 1048576).toFixed(1).replace('.', ',')} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`);
export { tamanho as tamanhoLegivel };

async function decodificar(blob) {
    if (typeof createImageBitmap === 'function') return createImageBitmap(blob);
    const url = URL.createObjectURL(blob);
    try {
        const img = new Image();
        img.src = url;
        await img.decode();
        return img;
    } finally {
        URL.revokeObjectURL(url);
    }
}

function desenhar(imagem, ladoMaximo) {
    const largura = imagem.width;
    const altura = imagem.height;
    const fator = Math.min(1, ladoMaximo / Math.max(largura, altura));
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(largura * fator));
    canvas.height = Math.max(1, Math.round(altura * fator));
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(imagem, 0, 0, canvas.width, canvas.height);
    return canvas;
}

const paraBlob = (canvas, tipo, qualidade) => new Promise((ok, falha) => canvas.toBlob((b) => (b ? ok(b) : falha(new Error('Falha ao gerar a imagem.'))), tipo, qualidade));
const liberar = (canvas) => { canvas.width = 0; canvas.height = 0; };
const fechar = (imagem) => { if (imagem && typeof imagem.close === 'function') imagem.close(); };

function renomear(nome, novaExtensao) {
    const base = String(nome || 'documento').replace(/\.[^.]*$/, '') || 'documento';
    return `${base}.${novaExtensao}`;
}

// Arquivo pronto para o envio: { arquivo, original, tratamentos: [texto], erro }. O banco so aceita PDF, PNG, JPEG e WebP de
// ate 10 MB; nada aqui amplia isso.
export async function prepararArquivo(original) {
    const tipo = tipoDoArquivo(original);
    const resultado = { arquivo: original, original, tratamentos: [], erro: null };
    if (!tipo) {
        resultado.erro = 'Formato não aceito. Envie PDF, PNG, JPEG ou WebP.';
        return resultado;
    }
    if (!original.size) {
        resultado.erro = 'Arquivo vazio.';
        return resultado;
    }
    if (tipo === 'pdf') {
        if (original.size > LIMITE_BYTES) resultado.erro = `O PDF tem ${tamanho(original.size)}; o limite é 10 MB.`;
        return resultado;
    }
    let atual = original;
    if (tipo === 'heic') {
        // So converte onde o navegador decodifica HEIC (Safari); nos demais, orienta o usuario.
        let imagem;
        try {
            imagem = await decodificar(original);
        } catch (_erro) {
            resultado.erro = 'Este navegador não abre fotos HEIC. Use a câmera pelo botão Fotografar ou envie a foto em JPEG.';
            return resultado;
        }
        const canvas = desenhar(imagem, Math.max(imagem.width, imagem.height));
        fechar(imagem);
        const blob = await paraBlob(canvas, 'image/jpeg', 0.92);
        liberar(canvas);
        atual = new File([blob], renomear(original.name, 'jpg'), { type: 'image/jpeg', lastModified: original.lastModified });
        resultado.tratamentos.push(`Foto HEIC convertida para JPEG (${tamanho(atual.size)}), formato aceito pelo sistema.`);
    }
    if (atual.size > LIMITE_BYTES) {
        // Foto acima do limite: copia JPEG reduzida, informada antes do envio. O original nao e alterado.
        const imagem = await decodificar(atual);
        let lado = Math.max(imagem.width, imagem.height);
        let blob = null;
        for (let tentativa = 0; tentativa < 8 && (!blob || blob.size > LIMITE_BYTES); tentativa += 1) {
            const canvas = desenhar(imagem, lado);
            blob = await paraBlob(canvas, 'image/jpeg', tentativa < 2 ? 0.9 : 0.82);
            liberar(canvas);
            lado = Math.round(lado * 0.82);
        }
        fechar(imagem);
        if (!blob || blob.size > LIMITE_BYTES) {
            resultado.erro = 'Não foi possível reduzir a foto para o limite de 10 MB.';
            return resultado;
        }
        resultado.tratamentos.push(`A foto tinha ${tamanho(atual.size)}; será enviada uma cópia JPEG reduzida de ${tamanho(blob.size)} (limite de 10 MB).`);
        atual = new File([blob], renomear(atual.name, 'jpg'), { type: 'image/jpeg', lastModified: atual.lastModified });
    }
    resultado.arquivo = atual;
    return resultado;
}

// Miniatura da foto para a pre-visualizacao, como data: URL (JPEG reduzido). A CSP das paginas libera img-src so para
// 'self' e data: (blob: continua bloqueado), e a miniatura tambem poupa memoria no celular. null se nao der para desenhar.
export async function miniaturaDaImagem(arquivo, ladoMaximo = 1200) {
    let imagem = null;
    try {
        imagem = await decodificar(arquivo);
        const canvas = desenhar(imagem, ladoMaximo);
        try {
            return canvas.toDataURL('image/jpeg', 0.85);
        } finally {
            liberar(canvas);
        }
    } catch (_erro) {
        return null;
    } finally {
        fechar(imagem);
    }
}

// ---------------------------------------------------------------------------------------------------------------
// pdf.js (o mesmo carregamento sob demanda da tela de documentos)

let pdfjsCarregado = null;
export async function pdfjs() {
    if (!pdfjsCarregado) {
        pdfjsCarregado = await import('../vendor/pdf.min.mjs');
        pdfjsCarregado.GlobalWorkerOptions.workerSrc = new URL('../vendor/pdf.worker.min.mjs', import.meta.url).href;
    }
    return pdfjsCarregado;
}

const suficiente = (texto) => String(texto ?? '').replace(/\s+/g, '').length >= TEXTO_MINIMO;

export async function textoDoPdfDigital(bytes) {
    try {
        return (await textoDoPdf(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength), await pdfjs())).join('\n');
    } catch (_erro) {
        return '';  // sem texto (digitalizado) ou ilegivel: segue para o OCR
    }
}

async function paginasComoImagem(bytes, maximo) {
    const biblioteca = await pdfjs();
    const tarefa = biblioteca.getDocument({ data: bytes.slice(), isEvalSupported: false, disableFontFace: true, useSystemFonts: false,
        enableXfa: false, verbosity: 0 });
    const documento = await tarefa.promise;
    try {
        const canvases = [];
        for (let n = 1; n <= Math.min(documento.numPages, maximo); n += 1) {
            const pagina = await documento.getPage(n);
            const base = pagina.getViewport({ scale: 1 });
            const escala = Math.min(200 / 72, LADO_MAXIMO_OCR / Math.max(base.width, base.height));  // ~200 dpi, como o Flask
            const viewport = pagina.getViewport({ scale: escala });
            const canvas = document.createElement('canvas');
            canvas.width = Math.ceil(viewport.width);
            canvas.height = Math.ceil(viewport.height);
            const ctx = canvas.getContext('2d');
            await pagina.render({ canvas, canvasContext: ctx, viewport }).promise;
            canvases.push(canvas);
        }
        return { canvases, total: documento.numPages };
    } finally {
        await tarefa.destroy();
    }
}

// ---------------------------------------------------------------------------------------------------------------
// OCR

let biblioteca = null;
async function tesseract() {
    if (!biblioteca) biblioteca = (await import('../vendor/tesseract-7.0.0/tesseract.esm.min.js')).default;
    return biblioteca;
}

const ETAPAS = { 'loading tesseract core': 'Preparando o leitor', 'initializing tesseract': 'Preparando o leitor', 'initialized tesseract': 'Preparando o leitor',
                 'loading language traineddata': 'Carregando o modelo de português', 'initializing api': 'Preparando o leitor',
                 'recognizing text': 'Reconhecendo o texto' };

// aoProgredir(texto): andamento para a tela. Um leitor por leitura (ou por lote de arquivos); encerrar() libera a memoria.
export function criarLeitor({ aoProgredir = () => {} } = {}) {
    let worker = null;
    let cancelar = null;
    let parte = '';

    async function obterWorker() {
        if (worker) return worker;
        const { createWorker } = await tesseract();
        worker = await createWorker('por', 1, {
            workerPath: new URL('worker.min.js', PASTA).href,
            corePath: PASTA.href,
            langPath: PASTA.href.replace(/\/$/, ''),
            workerBlobURL: false,
            gzip: true,
            cacheMethod: 'none',
            logger: (m) => {
                const etapa = ETAPAS[m.status];
                if (etapa) aoProgredir(`${etapa}${parte}${m.status === 'recognizing text' ? ` ${Math.round((m.progress || 0) * 100)}%` : ''}…`);
            },
        });
        return worker;
    }

    async function ocr(fonte) {
        const w = await obterWorker();
        const r = await w.recognize(fonte);
        return r.data.text || '';
    }

    async function encerrar() {
        const w = worker;
        worker = null;
        if (w) await w.terminate().catch(() => {});
    }

    // { texto, origem: 'TEXTO_PDF' | 'OCR_IMAGEM' | 'OCR_PDF' | null, aviso }
    async function lerSemLimite(arquivo) {
        const tipo = tipoDoArquivo(arquivo);
        const bytes = new Uint8Array(await arquivo.arrayBuffer());
        if (tipo === 'pdf') {
            aoProgredir('Lendo o texto do PDF…');
            const texto = await textoDoPdfDigital(bytes);
            if (suficiente(texto)) return { texto, origem: 'TEXTO_PDF', aviso: null };
            const { canvases, total } = await paginasComoImagem(bytes, MAX_PAGINAS_OCR);
            const textos = [];
            for (let i = 0; i < canvases.length; i += 1) {
                parte = canvases.length > 1 ? ` (página ${i + 1} de ${canvases.length})` : '';
                textos.push(await ocr(canvases[i]));
                liberar(canvases[i]);
            }
            parte = '';
            return { texto: textos.join('\n'), origem: 'OCR_PDF',
                     aviso: total > MAX_PAGINAS_OCR ? `Reconhecimento limitado às ${MAX_PAGINAS_OCR} primeiras páginas.` : null };
        }
        const imagem = await decodificar(arquivo);
        const canvas = desenhar(imagem, LADO_MAXIMO_OCR);
        fechar(imagem);
        try {
            return { texto: await ocr(canvas), origem: 'OCR_IMAGEM', aviso: null };
        } finally {
            liberar(canvas);
        }
    }

    // Leitura com cancelamento e tempo maximo; o worker e encerrado ao fim (ou na falha).
    async function ler(arquivo) {
        const interrompida = new Promise((_ok, falha) => {
            cancelar = () => falha(Object.assign(new Error('Leitura cancelada.'), { cancelada: true }));
        });
        let relogio = null;
        const limite = new Promise((_ok, falha) => {
            relogio = window.setTimeout(() => falha(new Error('A leitura demorou demais neste aparelho.')), TEMPO_MAXIMO_MS);
        });
        // As promessas que perderem a corrida nao viram erro solto no console.
        interrompida.catch(() => {});
        limite.catch(() => {});
        try {
            return await Promise.race([lerSemLimite(arquivo), interrompida, limite]);
        } finally {
            window.clearTimeout(relogio);
            cancelar = null;
            await encerrar();
        }
    }

    return {
        ler,
        cancelar: () => { if (cancelar) cancelar(); },
        encerrar,
    };
}
