(function () {
    'use strict';

    const ASSET_BASE = '/static/img/';

    const FORMAS_PAGAMENTO = {
        pix: {
            key: 'pix',
            nome: 'Pix',
            tipo: 'pix',
            assetReal: 'logo_pix.png',
            iconeFallback: 'PX',
            classe: 'payment-method--pix',
            cor: '#00a884'
        },
        dinheiro: {
            key: 'dinheiro',
            nome: 'Dinheiro',
            tipo: 'dinheiro',
            assetReal: 'icone_dinheiro.jpg',
            iconeFallback: 'R$',
            classe: 'payment-method--dinheiro',
            cor: '#16a34a'
        },
        cartao: {
            key: 'cartao',
            nome: 'Cartao',
            tipo: 'cartao',
            assetReal: 'formaPagamento_cartao.webp',
            iconeFallback: 'CT',
            classe: 'payment-method--cartao',
            cor: '#2563eb'
        },
        boleto: {
            key: 'boleto',
            nome: 'Boleto',
            tipo: 'boleto',
            assetReal: 'icone_boleto.jpg',
            iconeFallback: 'BO',
            classe: 'payment-method--boleto',
            cor: '#f59e0b'
        },
        transferencia: {
            key: 'transferencia',
            nome: 'Transferencia',
            tipo: 'transferencia',
            assetReal: 'trasnferencia_icone.jpg',
            iconeFallback: 'TR',
            classe: 'payment-method--transferencia',
            cor: '#0f766e'
        },
        'debito-automatico': {
            key: 'debito-automatico',
            nome: 'Debito automatico',
            tipo: 'debito-automatico',
            assetReal: null,
            iconeFallback: 'DA',
            classe: 'payment-method--debito-automatico',
            cor: '#7c3aed'
        },
        default: {
            key: 'default',
            nome: 'Forma de pagamento',
            tipo: 'default',
            assetReal: null,
            iconeFallback: 'PG',
            classe: 'payment-method--default',
            cor: '#64748b'
        }
    };

    const ALIASES_BRUTOS = {
        pix: [
            'pix',
            'pagamento instantaneo',
            'pagamento instantâneo',
            'transferencia pix',
            'transferência pix'
        ],
        dinheiro: [
            'dinheiro',
            'cash',
            'especie',
            'espécie',
            'em especie',
            'em espécie'
        ],
        cartao: [
            'cartao',
            'cartão',
            'cartao de credito',
            'cartão de crédito',
            'credito',
            'crédito',
            'cartao credito',
            'cartão crédito',
            'fatura',
            'cartao de debito',
            'cartão de débito',
            'debito',
            'débito'
        ],
        boleto: [
            'boleto',
            'codigo de barras',
            'código de barras',
            'linha digitavel',
            'linha digitável',
            'guia',
            'darf',
            'dare',
            'gru'
        ],
        transferencia: [
            'transferencia',
            'transferência',
            'ted',
            'doc',
            'transferencia bancaria',
            'transferência bancária',
            'transferencia entre contas',
            'transferência entre contas'
        ],
        'debito-automatico': [
            'debito automatico',
            'débito automático',
            'debito em conta',
            'débito em conta'
        ]
    };

    function escapeHtml(value) {
        return String(value ?? '').replace(/[&<>"']/g, (char) => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;'
        }[char]));
    }

    function normalizarFormaPagamento(valor) {
        return String(valor ?? '')
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '')
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, ' ')
            .replace(/\s+/g, ' ')
            .trim();
    }

    const ALIASES = Object.entries(ALIASES_BRUTOS).reduce((acc, [key, aliases]) => {
        aliases.forEach((alias) => {
            acc[normalizarFormaPagamento(alias)] = key;
        });
        return acc;
    }, {});

    function resolverAlias(normalizado) {
        if (!normalizado) return null;
        if (ALIASES[normalizado]) return ALIASES[normalizado];

        const texto = ` ${normalizado} `;
        const aliasesOrdenados = Object.keys(ALIASES).sort((a, b) => b.length - a.length);
        const aliasEncontrado = aliasesOrdenados.find((alias) => texto.includes(` ${alias} `));
        return aliasEncontrado ? ALIASES[aliasEncontrado] : null;
    }

    function resolverAsset(assetReal) {
        return assetReal ? `${ASSET_BASE}${assetReal}` : null;
    }

    function resolverFormaPagamento(valor) {
        const normalizado = normalizarFormaPagamento(valor);
        const key = resolverAlias(normalizado);
        const base = key ? FORMAS_PAGAMENTO[key] : FORMAS_PAGAMENTO.default;
        const nomeInformado = String(valor ?? '').trim();

        return {
            key: base.key,
            nome: key ? base.nome : (nomeInformado || 'Forma de pagamento'),
            tipo: base.tipo,
            asset: resolverAsset(base.assetReal),
            iconeFallback: base.iconeFallback,
            classe: base.classe,
            cor: base.cor,
            usaAssetLocal: Boolean(base.assetReal)
        };
    }

    function resolverIconeFormaPagamento(valor) {
        return resolverFormaPagamento(valor).asset || '';
    }

    function resolverTamanho(size) {
        const valor = String(size || 'md').trim();
        if (['sm', 'md', 'lg'].includes(valor)) {
            return { classe: valor, style: '' };
        }
        if (/^\d+(\.\d+)?(px|rem|em)$/.test(valor)) {
            return { classe: 'custom', style: `--payment-size:${valor};` };
        }
        return { classe: 'md', style: '' };
    }

    function renderFormaPagamento(valor, options = {}) {
        const info = resolverFormaPagamento(valor);
        const tamanho = resolverTamanho(options.size || options.tamanho || 'md');
        const showLabel = options.showLabel ?? options.mostrarLabel ?? true;
        const className = options.className ? ` ${escapeHtml(options.className)}` : '';
        const title = escapeHtml(options.title || info.nome);
        const label = escapeHtml(info.nome);
        const fallbackClass = info.usaAssetLocal ? 'payment-method--asset' : 'payment-method--fallback';
        const style = `--payment-color:${escapeHtml(info.cor)};${tamanho.style}`;
        const imagem = info.usaAssetLocal
            ? `<img class="payment-method__img" src="${escapeHtml(info.asset)}" alt="" loading="lazy">`
            : `<span class="payment-method__fallback">${escapeHtml(info.iconeFallback)}</span>`;

        return `
            <span class="payment-method payment-method--${escapeHtml(tamanho.classe)} ${escapeHtml(info.classe)} ${fallbackClass}${className}" title="${title}" aria-label="${title}" data-payment-method="${escapeHtml(info.key)}" style="${style}">
                <span class="payment-method__icon" aria-hidden="true">${imagem}</span>
                ${showLabel ? `<span class="payment-method__label">${label}</span>` : ''}
            </span>
        `.trim();
    }

    window.FormasPagamentoUI = {
        aliases: ALIASES,
        aliasesBrutos: ALIASES_BRUTOS,
        formas: FORMAS_PAGAMENTO,
        normalizarFormaPagamento,
        resolverFormaPagamento,
        resolverIconeFormaPagamento,
        renderFormaPagamento
    };

    window.renderPaymentIcon = function renderPaymentIcon(valor, options = {}) {
        return renderFormaPagamento(valor, {
            ...options,
            showLabel: false
        });
    };
}());
