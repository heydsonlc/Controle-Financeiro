(function () {
    'use strict';

    const ASSET_BASE = '/static/assets/instituicoes/';
    const DEFAULT_ASSETS = {
        banco: 'default-bank.svg',
        cartao: 'default-card.svg',
        default: 'default-bank.svg'
    };

    const INSTITUICOES = {
        'caixa': {
            key: 'caixa',
            nome: 'Caixa Economica Federal',
            tipo: 'banco',
            iniciais: 'CEF',
            cor: '#2563eb',
            assetReal: 'caixa.png'
        },
        'banco-do-brasil': {
            key: 'banco-do-brasil',
            nome: 'Banco do Brasil',
            tipo: 'banco',
            iniciais: 'BB',
            cor: '#f59e0b'
        },
        'itau': {
            key: 'itau',
            nome: 'Itau',
            tipo: 'banco',
            iniciais: 'IT',
            cor: '#f97316'
        },
        'santander': {
            key: 'santander',
            nome: 'Santander',
            tipo: 'banco',
            iniciais: 'ST',
            cor: '#ef4444'
        },
        'nubank': {
            key: 'nubank',
            nome: 'Nubank',
            tipo: 'banco',
            iniciais: 'NU',
            cor: '#7c3aed',
            assetReal: 'nubank.png'
        },
        'nubank-empresa': {
            key: 'nubank-empresa',
            nome: 'Nubank Empresa',
            tipo: 'banco',
            iniciais: 'NU',
            cor: '#7c3aed',
            assetReal: 'nubank-empresa.png'
        },
        'inter': {
            key: 'inter',
            nome: 'Banco Inter',
            tipo: 'banco',
            iniciais: 'BI',
            cor: '#f97316',
            assetReal: 'inter.png'
        },
        'bradesco': {
            key: 'bradesco',
            nome: 'Bradesco',
            tipo: 'banco',
            iniciais: 'BR',
            cor: '#dc2626'
        },
        'c6-bank': {
            key: 'c6-bank',
            nome: 'C6 Bank',
            tipo: 'banco',
            iniciais: 'C6',
            cor: '#111827'
        },
        'mercado-pago': {
            key: 'mercado-pago',
            nome: 'Mercado Pago',
            tipo: 'carteira',
            iniciais: 'MP',
            cor: '#0ea5e9'
        },
        'picpay': {
            key: 'picpay',
            nome: 'PicPay',
            tipo: 'carteira',
            iniciais: 'PP',
            cor: '#16a34a'
        },
        'pagbank': {
            key: 'pagbank',
            nome: 'PagBank',
            tipo: 'banco',
            iniciais: 'PB',
            cor: '#f59e0b'
        },
        'neon': {
            key: 'neon',
            nome: 'Neon',
            tipo: 'banco',
            iniciais: 'NE',
            cor: '#06b6d4'
        },
        'next': {
            key: 'next',
            nome: 'Next',
            tipo: 'banco',
            iniciais: 'NX',
            cor: '#22c55e'
        },
        'visa': {
            key: 'visa',
            nome: 'Visa',
            tipo: 'cartao',
            iniciais: 'VI',
            cor: '#1d4ed8',
            assetReal: 'visa.png'
        },
        'mastercard': {
            key: 'mastercard',
            nome: 'Mastercard',
            tipo: 'cartao',
            iniciais: 'MC',
            cor: '#dc2626',
            assetReal: 'mastercard.png'
        }
    };

    const ALIASES = {
        'caixa': 'caixa',
        'cef': 'caixa',
        'caixa economica': 'caixa',
        'caixa economica federal': 'caixa',
        'banco do brasil': 'banco-do-brasil',
        'bb': 'banco-do-brasil',
        'itau': 'itau',
        'santander': 'santander',
        'nubank': 'nubank',
        'nu': 'nubank',
        'nu bank': 'nubank',
        'nubank empresa': 'nubank-empresa',
        'inter': 'inter',
        'banco inter': 'inter',
        'bradesco': 'bradesco',
        'c6': 'c6-bank',
        'c6 bank': 'c6-bank',
        'mercado pago': 'mercado-pago',
        'mercadopago': 'mercado-pago',
        'picpay': 'picpay',
        'pic pay': 'picpay',
        'pagbank': 'pagbank',
        'pag bank': 'pagbank',
        'neon': 'neon',
        'next': 'next',
        'visa': 'visa',
        'mastercard': 'mastercard',
        'master card': 'mastercard',
        'martercard': 'mastercard'
    };

    function resolverAlias(normalizado) {
        if (ALIASES[normalizado]) {
            return ALIASES[normalizado];
        }

        const texto = ` ${normalizado} `;
        const aliasesOrdenados = Object.keys(ALIASES).sort((a, b) => b.length - a.length);
        const aliasEncontrado = aliasesOrdenados.find((alias) => texto.includes(` ${alias} `));
        return aliasEncontrado ? ALIASES[aliasEncontrado] : null;
    }

    function escapeHtml(value) {
        return String(value ?? '').replace(/[&<>"']/g, (char) => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;'
        }[char]));
    }

    function normalizarInstituicao(nome) {
        return String(nome || '')
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '')
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, ' ')
            .replace(/\s+/g, ' ')
            .trim();
    }

    function gerarIniciais(nome) {
        const partes = normalizarInstituicao(nome).split(' ').filter(Boolean);
        if (!partes.length) return '?';
        if (partes.length === 1) return partes[0].slice(0, 2).toUpperCase();
        return `${partes[0][0]}${partes[1][0]}`.toUpperCase();
    }

    function resolverAsset(tipo, assetReal) {
        if (assetReal) {
            return `${ASSET_BASE}${assetReal}`;
        }
        const asset = DEFAULT_ASSETS[tipo] || DEFAULT_ASSETS.default;
        return `${ASSET_BASE}${asset}`;
    }

    function resolverInstituicao(nome, tipo) {
        const normalizado = normalizarInstituicao(nome);
        const key = resolverAlias(normalizado);
        const base = key ? INSTITUICOES[key] : null;
        const tipoResolvido = tipo || base?.tipo || 'banco';

        if (base) {
            return {
                ...base,
                tipo: tipoResolvido,
                classe: `institution-logo--${base.key}`,
                asset: resolverAsset(tipoResolvido, base.assetReal),
                usaAssetReal: Boolean(base.assetReal)
            };
        }

        return {
            key: 'default',
            nome: String(nome || '').trim() || 'Instituicao nao informada',
            tipo: tipoResolvido,
            classe: 'institution-logo--default',
            iniciais: gerarIniciais(nome),
            asset: resolverAsset(tipoResolvido),
            cor: '#64748b',
            usaAssetReal: false
        };
    }

    function resolverLogoInstituicao(nome, tipo) {
        return resolverInstituicao(nome, tipo).asset;
    }

    function renderInstituicaoLogo(nome, options = {}) {
        const tipo = options.tipo || 'banco';
        const tamanho = options.tamanho || options.size || 'md';
        const mostrarLabel = Boolean(options.mostrarLabel);
        const info = resolverInstituicao(nome, tipo);
        const label = info.nome || 'Instituicao financeira';
        const cssColor = escapeHtml(info.cor || '#64748b');
        const realClass = info.usaAssetReal ? 'institution-logo--real' : 'institution-logo--fallback';

        return `
            <span class="institution-logo institution-logo--${escapeHtml(tamanho)} ${escapeHtml(info.classe)} ${realClass}" title="${escapeHtml(label)}" aria-label="${escapeHtml(label)}" data-institution-key="${escapeHtml(info.key)}" style="--institution-color:${cssColor}">
                <span class="institution-logo__mark" aria-hidden="true">
                    <img class="institution-logo__icon" src="${escapeHtml(info.asset)}" alt="" loading="lazy">
                    ${info.usaAssetReal ? '' : `<span class="institution-logo__initials">${escapeHtml(info.iniciais)}</span>`}
                </span>
                ${mostrarLabel ? `<span class="institution-logo__label">${escapeHtml(label)}</span>` : ''}
            </span>
        `.trim();
    }

    window.InstituicoesUI = {
        aliases: ALIASES,
        instituicoes: INSTITUICOES,
        normalizarInstituicao,
        resolverInstituicao,
        resolverLogoInstituicao,
        renderLogo: renderInstituicaoLogo,
        renderInstituicaoLogo
    };
}());
