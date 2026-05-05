/**
 * Icones proprios para Categoria do Cartao.
 * Usa somente assets locais adicionados em frontend/static/img.
 */
(function () {
    const BASE_PATH = '/static/img/';

    const ICONES = [
        {
            key: 'mobilidade',
            nome: 'Mobilidade',
            asset: `${BASE_PATH}categoria_cartão_mobilidade.png`,
            aliases: ['mobilidade', 'transporte', 'veiculo', 'veiculo proprio', 'uber', 'taxi']
        },
        {
            key: 'supermercado',
            nome: 'Supermercado',
            asset: `${BASE_PATH}categoria_cartão_supermercado.png`,
            aliases: ['supermercado', 'mercado', 'alimentacao', 'alimentacao mercado', 'compras mercado']
        },
        {
            key: 'saude',
            nome: 'Saude',
            asset: `${BASE_PATH}categoria_cartão_saude.png`,
            aliases: ['saude', 'saude bem estar', 'medico', 'hospital', 'clinica']
        },
        {
            key: 'farmacia',
            nome: 'Farmacia',
            asset: `${BASE_PATH}categoria_cartão_farmácia.png`,
            aliases: ['farmacia', 'remedio', 'medicamento', 'drogaria']
        },
        {
            key: 'educacao',
            nome: 'Educacao',
            asset: `${BASE_PATH}categoria_cartao_educacao.jpg`,
            aliases: ['educacao', 'estudo', 'curso', 'faculdade', 'escola']
        },
        {
            key: 'inteligencia-artificial',
            nome: 'Inteligencia artificial',
            asset: `${BASE_PATH}categoria_cartão_inteligenciaArtificial.png`,
            aliases: ['inteligencia artificial', 'ia', 'ai', 'software ia', 'assinatura ia']
        },
        {
            key: 'padaria',
            nome: 'Padaria',
            asset: `${BASE_PATH}categoria_cartão_padaria.png`,
            aliases: ['padaria', 'panificadora', 'cafe', 'cafeteria']
        },
        {
            key: 'verdurao',
            nome: 'Verdurao',
            asset: `${BASE_PATH}categoria_cartão_verdurao.png`,
            aliases: ['verdurao', 'hortifruti', 'hortifruti feira', 'feira', 'sacolao']
        },
        {
            key: 'saude-2',
            nome: 'Saude alternativa',
            asset: `${BASE_PATH}categoria_cartao_saude2.jpg`,
            aliases: ['saude alternativa', 'bem estar', 'terapia']
        }
    ];

    const FALLBACK = {
        key: 'categoria-cartao-default',
        nome: 'Categoria do Cartao',
        asset: null,
        aliases: []
    };

    function escapeAttr(value) {
        return String(value ?? '').replace(/[&<>"']/g, (char) => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;'
        }[char]));
    }

    function normalizarIconeCategoriaCartao(valor) {
        return String(valor || '')
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '')
            .toLowerCase()
            .replace(/[_/\\|.,;:()[\]{}]+/g, ' ')
            .replace(/[^a-z0-9 -]+/g, '')
            .replace(/\s+/g, ' ')
            .trim();
    }

    function listarIconesCategoriaCartao() {
        return ICONES.map((icone) => ({
            key: icone.key,
            nome: icone.nome,
            asset: icone.asset,
            categoriaVisual: 'categoria-cartao'
        }));
    }

    function resolverPorTexto(valor) {
        const normalizado = normalizarIconeCategoriaCartao(valor);
        if (!normalizado) return { ...FALLBACK, usaAssetLocal: false };

        const encontrado = ICONES.find((icone) => {
            if (normalizarIconeCategoriaCartao(icone.key) === normalizado) return true;
            if (normalizarIconeCategoriaCartao(icone.nome) === normalizado) return true;
            return icone.aliases.some((alias) => normalizarIconeCategoriaCartao(alias) === normalizado);
        }) || ICONES.find((icone) => {
            const alvos = [icone.key, icone.nome, ...icone.aliases].map(normalizarIconeCategoriaCartao);
            return alvos.some((alvo) => alvo && normalizado.includes(alvo));
        });

        return encontrado
            ? { ...encontrado, usaAssetLocal: true }
            : { ...FALLBACK, usaAssetLocal: false };
    }

    function resolverIconeCategoriaCartao(iconeOuNome) {
        if (typeof iconeOuNome === 'object' && iconeOuNome !== null) {
            const porIcone = resolverPorTexto(iconeOuNome.icone);
            if (porIcone.usaAssetLocal) return porIcone;
            return resolverPorTexto(iconeOuNome.nome);
        }
        return resolverPorTexto(iconeOuNome);
    }

    function renderFallback(sizePx, classeExtra, label) {
        const svg = typeof renderIcon === 'function'
            ? renderIcon('credit-card', { size: `${Math.max(14, Math.round(sizePx * 0.56))}px` })
            : '<span aria-hidden="true">CC</span>';
        return `<span class="categoria-cartao-icon categoria-cartao-icon--fallback ${classeExtra}" title="${escapeAttr(label)}" aria-label="${escapeAttr(label)}" style="width:${sizePx}px;height:${sizePx}px">${svg}</span>`;
    }

    function renderIconeCategoriaCartao(categoria, options = {}) {
        const resolvido = resolverIconeCategoriaCartao(categoria);
        const sizeMap = { sm: 28, md: 36, lg: 48 };
        const sizePx = Number(options.sizePx) || sizeMap[options.size || 'md'] || 36;
        const classeExtra = options.className ? escapeAttr(options.className) : '';
        const label = options.label || resolvido.nome || 'Categoria do Cartao';

        if (!resolvido.asset) {
            return renderFallback(sizePx, classeExtra, label);
        }

        const fallback = renderFallback(sizePx, classeExtra, label);
        const img = `<img class="categoria-cartao-icon__img" src="${escapeAttr(resolvido.asset)}" alt="" loading="lazy" onerror="this.hidden=true;this.nextElementSibling.hidden=false;">`;
        return `<span class="categoria-cartao-icon ${classeExtra}" title="${escapeAttr(label)}" aria-label="${escapeAttr(label)}" style="width:${sizePx}px;height:${sizePx}px">${img}<span class="categoria-cartao-icon__fallback" hidden>${fallback}</span></span>`;
    }

    window.CategoriaCartaoIconesUI = {
        normalizarIconeCategoriaCartao,
        listarIconesCategoriaCartao,
        resolverIconeCategoriaCartao,
        renderIconeCategoriaCartao
    };
})();
