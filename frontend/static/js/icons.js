/**
 * Catálogo interno de ícones SVG monocromáticos — ICONES-1A
 * Todos usam stroke="currentColor", fill="none" para herdar a cor do contexto.
 */

const ICONS_CATALOG = {
    'wifi':          '<path d="M5 12.5a9.5 9.5 0 0 1 14 0M8.5 16a5 5 0 0 1 7 0M12 19.5h.1"/>',
    'home':          '<path d="M4 11.5 12 5l8 6.5M6.5 10.5V20h11v-9.5M10 20v-5h4v5"/>',
    'heart':         '<path d="M12 20c-.5 0-9-5.5-9-11a5 5 0 0 1 9-3 5 5 0 0 1 9 3c0 5.5-8.5 11-9 11Z"/>',
    'cart':          '<path d="M6 2H3"/><path d="M3 2l2 13h13l2-8H6.5"/><circle cx="9" cy="19" r="1.5"/><circle cx="16" cy="19" r="1.5"/>',
    'food':          '<path d="M12 2v6M9 5c0 3 1.5 5 3 7s3-1 3-4V5M6 2v4a3 3 0 0 0 6 0V2M18 2v20"/>',
    'car':           '<path d="M5 14h14l-1.5-5.5A2 2 0 0 0 15.6 7H8.4a2 2 0 0 0-1.9 1.5L5 14Zm2 0v3M17 14v3M8 17h.1M16 17h.1"/>',
    'bus':           '<path d="M4 8h16v10H4V8Zm4 10v2M16 18v2M4 12h16M8 8v4M12 8v4M16 8v4M4 8a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2"/>',
    'fuel':          '<path d="M4 22V6a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v3l2.5 1.5v5a1.5 1.5 0 0 0 3 0V9l-1.5-1M4 12h12"/>',
    'cash':          '<rect x="3" y="6" width="18" height="12" rx="2"/><circle cx="12" cy="12" r="3"/><path d="M7 12h.1M17 12h.1"/>',
    'credit-card':   '<rect x="3" y="6" width="18" height="12" rx="2"/><path d="M3 10h18"/>',
    'qr-code':       '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><path d="M14 14h.1M18 14h3v3M14 18h3M17 21h3M14 21h.1"/>',
    'receipt':       '<path d="M4 4v16l2-1.5L8 20l2-1.5L12 20l2-1.5L16 20l2-1.5L20 20V4H4Zm3 5h10M7 12h10M7 15h6"/>',
    'bank':          '<path d="M4 10h16M6 10v8M10 10v8M14 10v8M18 10v8M4 18h16M12 4l8 4H4l8-4Z"/>',
    'briefcase':     '<rect x="3" y="8" width="18" height="13" rx="2"/><path d="M8 8V6a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 14h18"/>',
    'shield':        '<path d="M12 3 4 7v5c0 4.5 3.5 8.7 8 10 4.5-1.3 8-5.5 8-10V7l-8-4Z"/>',
    'lightning':     '<path d="M13 2 4.5 13.5H12l-1 8.5L20.5 10H13L13 2Z"/>',
    'phone':         '<path d="M5 4h4l1.5 4L9 10a13 13 0 0 0 5 5l1.5-1.5 4 1.5V20a2 2 0 0 1-2 2C8 21 3 16 3 6a2 2 0 0 1 2-2Z"/>',
    'book':          '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2Z"/>',
    'gift':          '<path d="M12 8v13M20 8H4M4 8a3 3 0 0 1 0-6c2 0 5 2 8 6 3-4 6-6 8-6a3 3 0 0 1 0 6H4Zm0 0v13h16V8"/>',
    'tool':          '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.9 6.9a2.12 2.12 0 0 1-3-3l6.9-6.9a6 6 0 0 1 7.94-7.94l-3.76 3.76Z"/>',
    'repeat':        '<path d="M17 1l4 4-4 4"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><path d="M7 23l-4-4 4-4"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/>',
    'calendar':      '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
    'tag':           '<path d="M20 7.5V4a1 1 0 0 0-1-1h-3.5a1 1 0 0 0-.7.3l-9 9a2 2 0 0 0 0 2.8l4.1 4.1a2 2 0 0 0 2.8 0l9-9a1 1 0 0 0 .3-.7ZM15 7h.1"/>',
    'education':     '<path d="M2 10l10-6 10 6-10 6-10-6Z"/><path d="M6 12.5V18c0 1 2.7 2 6 2s6-1 6-2v-5.5"/>',
    'health':        '<path d="M12 20c-.5 0-9-5.5-9-11a5 5 0 0 1 9-3 5 5 0 0 1 9 3c0 5.5-8.5 11-9 11Z"/>',
    'travel':        '<path d="M3 12h18M12 3a9 9 0 0 1 0 18M12 3a9 9 0 0 0 0 18M5 5.5A15 15 0 0 1 12 3M5 18.5A15 15 0 0 0 12 21M19 5.5A15 15 0 0 0 12 3M19 18.5A15 15 0 0 1 12 21"/>',
    'pet':           '<path d="M10 5.5a2 2 0 1 0 0-4 2 2 0 0 0 0 4ZM14 5.5a2 2 0 1 0 0-4 2 2 0 0 0 0 4ZM6 9.5a2 2 0 1 0 0-4 2 2 0 0 0 0 4ZM18 9.5a2 2 0 1 0 0-4 2 2 0 0 0 0 4ZM12 22c-3 0-6-2-6-5 0-2 1-4 4-5h4c3 1 4 3 4 5 0 3-3 5-6 5Z"/>',
    'kortex-logo':   '<path d="M5 4v16M19 4 8 12l11 8M10.5 10l7.5-6M10.5 14l7.5 6"/><path d="M5 12h3.5"/>',
    'cbmgo-logo':    '<path d="M12 3 5 6.5v5.8c0 4 2.8 7.5 7 8.7 4.2-1.2 7-4.7 7-8.7V6.5L12 3Z"/><path d="M12 7.2c2.2 2.3 3.2 4.1 3.2 5.8A3.2 3.2 0 0 1 12 16.3 3.2 3.2 0 0 1 8.8 13c0-1.3.8-2.5 1.9-3.8-.1 1 .3 1.8 1.3 2.5.7-1.2.7-2.5 0-4.5Z"/><path d="M8.8 18h6.4"/>',
    'default':       '<rect x="4" y="4" width="16" height="16" rx="3"/>'
};

const SVG_ATTRS = 'viewBox="0 0 24 24" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"';

/**
 * Retorna string SVG inline para a chave fornecida.
 * Se a chave não existir, retorna string vazia.
 * @param {string|null} key
 * @param {object} [opts]
 * @param {string} [opts.size] CSS size, ex: "16px"
 * @param {string} [opts.cssClass] classe extra
 * @returns {string}
 */
function renderIcon(key, opts = {}) {
    if (!key) return '';
    const paths = ICONS_CATALOG[key] || ICONS_CATALOG['default'];
    if (!paths) return '';
    const size = opts.size || '16px';
    const cls = opts.cssClass ? ` class="${opts.cssClass}"` : '';
    return `<svg ${SVG_ATTRS} style="width:${size};height:${size};display:inline-block;vertical-align:-0.125em;flex-shrink:0;"${cls}>${paths}</svg>`;
}

/**
 * Mapa fixo: meio_pagamento -> chave de ícone
 */
const ICONES_MEIO_PAGAMENTO = {
    'cartao':   'credit-card',
    'pix':      'qr-code',
    'dinheiro': 'cash',
    'boleto':   'receipt',
    'debito':   'bank'
};

/**
 * Renderiza ícone de meio de pagamento.
 * @param {string|null} meio
 * @param {object} [opts]
 * @returns {string}
 */
function renderPaymentIcon(meio, opts = {}) {
    if (!meio) return '';
    const key = ICONES_MEIO_PAGAMENTO[meio.toLowerCase()] || null;
    return key ? renderIcon(key, opts) : '';
}

/**
 * Renderiza ícone de categoria.
 * Aceita objeto categoria (com campo .icone) ou string de chave diretamente.
 * @param {object|string|null} categoriaOuChave
 * @param {object} [opts]
 * @returns {string}
 */
function renderCategoryIcon(categoriaOuChave, opts = {}) {
    if (!categoriaOuChave) return '';
    const key = typeof categoriaOuChave === 'string'
        ? categoriaOuChave
        : (categoriaOuChave.icone || null);
    return key ? renderIcon(key, opts) : '';
}

function escapeIconAttr(value) {
    return String(value || '').replace(/[&<>"']/g, (char) => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
    }[char]));
}

function renderCategoryVisual(categoriaOuChave, opts = {}) {
    if (!categoriaOuChave) return '';

    if (typeof categoriaOuChave === 'object' && categoriaOuChave.logo_url) {
        const size = opts.size || '16px';
        const alt = opts.alt !== undefined ? opts.alt : (categoriaOuChave.nome || '');
        const fallback = renderCategoryIcon(categoriaOuChave, opts) || renderIcon('default', opts);
        const cls = opts.cssClass ? ` ${escapeIconAttr(opts.cssClass)}` : '';
        const src = escapeIconAttr(categoriaOuChave.logo_url);

        return `<span class="category-visual category-visual-logo" style="width:${size};height:${size};display:inline-flex;align-items:center;justify-content:center;vertical-align:-0.125em;flex-shrink:0;">` +
            `<img class="category-logo${cls}" src="${src}" alt="${escapeIconAttr(alt)}" loading="lazy" style="max-width:100%;max-height:100%;object-fit:contain;border-radius:4px;display:block;" onerror="this.hidden=true;this.nextElementSibling.hidden=false;">` +
            `<span class="category-logo-fallback" hidden>${fallback}</span>` +
            `</span>`;
    }

    return renderCategoryIcon(categoriaOuChave, opts) || renderIcon('default', opts);
}

function getIconKeys() {
    return Object.keys(ICONS_CATALOG).filter(key => key !== 'default').sort();
}

if (typeof window !== 'undefined') {
    window.ICONS_CATALOG = ICONS_CATALOG;
    window.getIconKeys = getIconKeys;
    window.renderCategoryVisual = renderCategoryVisual;
}
