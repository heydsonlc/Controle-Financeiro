(function () {
    'use strict';

    const STORAGE_CURRENT = 'help.currentArticle';
    const STORAGE_LAST = 'help.lastArticles';

    const artigos = [
        {
            id: 'primeiros-passos',
            secao: 'basico',
            icone: '↗',
            titulo: 'Primeiros passos',
            resumo: 'Como começar a usar o sistema com segurança.',
            relacionados: ['perfis-financeiros', 'categorias-despesa', 'despesas'],
            corpo: [
                ['h3', 'Comece pelo básico'],
                ['p', 'Cadastre suas contas, cartões e categorias antes de lançar despesas. Isso torna o dashboard, a importação de fatura e os relatórios mais coerentes.'],
                ['ul', ['Crie ou revise seus perfis financeiros.', 'Cadastre contas bancárias e cartões.', 'Organize Categorias de Despesa.', 'Registre despesas previstas e lançamentos realizados.', 'Use relatórios para revisar pendências.']]
            ]
        },
        {
            id: 'perfis-financeiros',
            secao: 'config',
            icone: '◎',
            titulo: 'Perfis Financeiros',
            resumo: 'Separe contextos como Pessoal e Empresa sem trocar de usuário.',
            relacionados: ['configuracoes', 'documentos-fiscais-ir', 'primeiros-passos'],
            corpo: [
                ['h3', 'Usuário e perfil financeiro são conceitos diferentes'],
                ['p', 'O mesmo usuário pode alternar entre perfis como Pessoal e Empresa sem logout. Cada perfil isola dados financeiros, relatórios e documentos dentro do contexto ativo.'],
                ['ul', ['Pessoal concentra finanças individuais e IRPF.', 'Empresa concentra documentos fiscais, lastro e gestão empresarial.', 'A troca acontece pelo seletor no topo da aplicação.']]
            ]
        },
        {
            id: 'categorias-despesa',
            secao: 'basico',
            icone: '◇',
            titulo: 'Categorias de Despesa',
            resumo: 'Classificam a natureza do gasto.',
            relacionados: ['categoria-cartao', 'importacao-fatura', 'documentos-fiscais-ir'],
            corpo: [
                ['h3', 'Natureza do gasto'],
                ['p', 'Categoria de Despesa responde o que foi comprado ou contratado: alimentação, saúde, moradia, educação, transporte e outras naturezas.'],
                ['p', 'Palavras-chave ajudam o sistema a sugerir categorias na importação de fatura e na leitura de documentos fiscais.']
            ]
        },
        {
            id: 'categoria-cartao',
            secao: 'cartoes',
            icone: '▣',
            titulo: 'Categoria do Cartão: projeção, realizado e limites',
            resumo: 'Organize fatura, limites, projeção e realizado no cartão.',
            destaque: true,
            relacionados: ['importacao-fatura', 'projecao-realizado', 'perfis-financeiros', 'lancamentos'],
            corpo: [
                ['p', 'A Categoria do Cartão é usada para organizar e controlar os gastos realizados no cartão de crédito, incluindo projeções de fatura e limites disponíveis.'],
                ['h3', 'Entenda o conceito'],
                ['p', 'Categoria de Despesa classifica a natureza do gasto. Categoria do Cartão classifica onde aquele gasto entra na fatura, limite e acompanhamento do cartão. Elas são diferentes e complementares.'],
                ['compare', [
                    ['Categoria de Despesa', 'Natureza do gasto', 'Ex.: Alimentação, Saúde, Moradia', 'Ajuda análise mensal'],
                    ['Categoria do Cartão', 'Meio/fatura do cartão', 'Ex.: Mobilidade, Supermercado, Saúde', 'Ajuda limite, projeção e realizado']
                ]],
                ['note', 'Use a Categoria do Cartão para acompanhar limites, projeções de fatura e conciliação com o realizado.'],
                ['warning', 'Lançamentos sem Categoria do Cartão podem não entrar corretamente na projeção da fatura.'],
                ['h3', 'Passo a passo'],
                ['steps', ['Cadastre os cartões.', 'Crie Categorias do Cartão.', 'Vincule Categorias de Despesa.', 'Defina limites no cartão.', 'Lance ou importe despesas.', 'Acompanhe projeção e realizado.']]
            ]
        },
        {
            id: 'projecao-realizado',
            secao: 'cartoes',
            icone: '↔',
            titulo: 'Projeção × Realizado',
            resumo: 'Diferença entre previsão e pagamento ou realização.',
            relacionados: ['categoria-cartao', 'despesas', 'lancamentos'],
            corpo: [
                ['h3', 'Previsão não é pagamento'],
                ['p', 'Projeção representa o que se espera gastar ou pagar. Realizado representa o lançamento confirmado, pagamento ou movimento efetivo.'],
                ['p', 'Essa diferença impacta dashboard, faturas, relatórios e acompanhamento mensal.']
            ]
        },
        {
            id: 'despesas',
            secao: 'gestao',
            icone: '▾',
            titulo: 'Despesas',
            resumo: 'Previsões, pendências e pagamentos do mês.',
            relacionados: ['lancamentos', 'recorrencias', 'categorias-despesa'],
            corpo: [
                ['h3', 'Despesas previstas e pagas'],
                ['p', 'Despesas previstas ajudam a planejar o mês. Ao pagar ou confirmar, elas passam a compor o realizado e podem gerar lançamentos.'],
                ['ul', ['Use status para revisar pendências.', 'Associe conta, cartão e categoria corretamente.', 'Revise diferenças entre previsto e realizado.']]
            ]
        },
        {
            id: 'lancamentos',
            secao: 'gestao',
            icone: '+',
            titulo: 'Lançamentos',
            resumo: 'Registros efetivos de entradas e saídas.',
            relacionados: ['despesas', 'receitas', 'projecao-realizado'],
            corpo: [
                ['h3', 'O que já aconteceu'],
                ['p', 'Lançamentos representam movimentos realizados. Eles podem nascer de despesas pagas, receitas confirmadas ou operações manuais.']
            ]
        },
        {
            id: 'recorrencias',
            secao: 'gestao',
            icone: '↻',
            titulo: 'Recorrências',
            resumo: 'Geração de despesas frequentes.',
            relacionados: ['despesas', 'categoria-cartao', 'configuracoes'],
            corpo: [
                ['h3', 'Despesas que se repetem'],
                ['p', 'Recorrências criam previsões periódicas para assinaturas, parcelas, serviços fixos e outros compromissos.']
            ]
        },
        {
            id: 'importacao-fatura',
            secao: 'cartoes',
            icone: '⇣',
            titulo: 'Importação de Fatura',
            resumo: 'Use palavras-chave, Categoria de Despesa e Categoria do Cartão.',
            relacionados: ['categoria-cartao', 'categorias-despesa', 'projecao-realizado'],
            corpo: [
                ['h3', 'Revisão em lote'],
                ['p', 'A importação usa palavras-chave para sugerir Categoria de Despesa. Quando houver vínculo, a Categoria do Cartão também pode ser sugerida para organizar fatura e limites.'],
                ['ul', ['Importe a fatura.', 'Revise sugestões.', 'Ajuste categorias em lote.', 'Confirme os lançamentos.']]
            ]
        },
        {
            id: 'documentos-fiscais-ir',
            secao: 'fiscal',
            icone: '▤',
            titulo: 'Documentos Fiscais / IR',
            resumo: 'IRPF no perfil pessoal e lastro fiscal no perfil empresa.',
            relacionados: ['perfis-financeiros', 'categorias-despesa', 'configuracoes'],
            corpo: [
                ['h3', 'Comportamento por perfil'],
                ['p', 'No perfil Pessoal, o módulo funciona como Imposto de Renda para organizar comprovantes potencialmente dedutíveis. No perfil Empresa, funciona como Documentos Fiscais e Lastro Empresarial.'],
                ['p', 'Relatórios Excel/PDF ajudam a preparar material para contador, mas a classificação fiscal continua sujeita a revisão.']
            ]
        },
        {
            id: 'patrimonio',
            secao: 'gestao',
            icone: '▥',
            titulo: 'Patrimônio',
            resumo: 'Caixinhas, metas e transferências.',
            relacionados: ['documentos-fiscais-ir', 'perfis-financeiros', 'lancamentos'],
            corpo: [
                ['h3', 'Organização patrimonial'],
                ['p', 'Patrimônio reúne caixinhas e controles de saldo separados das despesas do mês. Em perfis empresariais, documentos fiscais podem futuramente apoiar itens patrimoniais.']
            ]
        },
        {
            id: 'financiamentos',
            secao: 'gestao',
            icone: '▱',
            titulo: 'Financiamentos',
            resumo: 'Contratos, parcelas, amortização e extratos.',
            relacionados: ['projecao-realizado', 'patrimonio', 'documentos-fiscais-ir'],
            corpo: [
                ['h3', 'Contratos e parcelas'],
                ['p', 'Financiamentos acompanham contrato, cronograma, parcelas e amortizações sem alterar automaticamente suas regras financeiras fora dos fluxos previstos.']
            ]
        },
        {
            id: 'configuracoes',
            secao: 'config',
            icone: '⚙',
            titulo: 'Configurações',
            resumo: 'Perfis, preferências, aparência e backup futuro.',
            relacionados: ['perfis-financeiros', 'documentos-fiscais-ir', 'primeiros-passos'],
            corpo: [
                ['h3', 'Central de configuração'],
                ['p', 'A tela Configurações e Preferências concentra perfis financeiros, preferências gerais, aparência, comportamento, backup, IA e documentos fiscais.'],
                ['p', 'Algumas opções são placeholders seguros e serão ativadas em etapas futuras.']
            ]
        }
    ];

    const videos = [
        ['Entendendo a Categoria do Cartão', '02:45'],
        ['Projeção de Fatura na prática', '03:18'],
        ['Importação de Fatura com palavras-chave', '04:10'],
        ['Perfis Financeiros: Pessoal e Empresa', '03:40'],
        ['Documentos Fiscais e Lastro', '05:20']
    ];

    const faqs = [
        ['Qual a diferença entre despesa e cartão?', 'categoria-cartao'],
        ['Como ajustar o limite do cartão?', 'categoria-cartao'],
        ['O que acontece se eu trocar de perfil?', 'perfis-financeiros'],
        ['Como validar documentos fiscais?', 'documentos-fiscais-ir']
    ];

    const state = {
        artigo: null,
        busca: '',
        filtro: 'all'
    };

    const $ = (id) => document.getElementById(id);
    const byId = (id) => artigos.find((artigo) => artigo.id === id) || artigos[0];

    function escapeHtml(value) {
        return String(value ?? '').replace(/[&<>"']/g, (char) => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;'
        }[char]));
    }

    function textoArtigo(artigo) {
        return [artigo.titulo, artigo.resumo, ...artigo.corpo.flat(3)].join(' ').toLowerCase();
    }

    function artigosFiltrados() {
        const termo = state.busca.trim().toLowerCase();
        return artigos.filter((artigo) => {
            const porSecao = state.filtro === 'all' || artigo.secao === state.filtro;
            const porBusca = !termo || textoArtigo(artigo).includes(termo);
            return porSecao && porBusca;
        });
    }

    function renderNav() {
        const lista = $('help-nav-list');
        const empty = $('help-empty-results');
        const filtrados = artigosFiltrados();
        if (!lista) return;
        lista.innerHTML = filtrados.map((artigo) => `
            <button type="button" class="help-nav-item${state.artigo?.id === artigo.id ? ' active' : ''}" data-help-open="${escapeHtml(artigo.id)}">
                <span class="help-nav-icon" aria-hidden="true">${escapeHtml(artigo.icone)}</span>
                <span>${escapeHtml(artigo.titulo)}</span>
                <span aria-hidden="true">›</span>
            </button>
        `).join('');
        if (empty) empty.hidden = filtrados.length > 0;
    }

    function blocoHtml(bloco) {
        const [tipo, conteudo] = bloco;
        if (tipo === 'h3') return `<h3>${escapeHtml(conteudo)}</h3>`;
        if (tipo === 'p') return `<p>${escapeHtml(conteudo)}</p>`;
        if (tipo === 'ul') return `<ul>${conteudo.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ul>`;
        if (tipo === 'note') return `<div class="help-note"><strong>Dica</strong><br>${escapeHtml(conteudo)}</div>`;
        if (tipo === 'warning') return `<div class="help-warning"><strong>Atenção</strong><br>${escapeHtml(conteudo)}</div>`;
        if (tipo === 'steps') return `<ol class="help-step-list">${conteudo.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ol>`;
        if (tipo === 'compare') {
            return `
                <div class="help-compare">
                    <div class="help-compare-card"><strong>${escapeHtml(conteudo[0][0])}</strong>${conteudo[0].slice(1).map((item) => `<p>${escapeHtml(item)}</p>`).join('')}</div>
                    <div class="help-compare-vs">VS</div>
                    <div class="help-compare-card"><strong>${escapeHtml(conteudo[1][0])}</strong>${conteudo[1].slice(1).map((item) => `<p>${escapeHtml(item)}</p>`).join('')}</div>
                </div>
            `;
        }
        return '';
    }

    function abrirArtigo(id) {
        state.artigo = byId(id);
        localStorage.setItem(STORAGE_CURRENT, state.artigo.id);
        registrarAcesso(state.artigo);
        render();
    }

    function renderArtigo() {
        const destino = $('help-article');
        if (!destino || !state.artigo) return;
        destino.innerHTML = `
            <h2>${escapeHtml(state.artigo.titulo)}</h2>
            <p class="help-article-intro">${escapeHtml(state.artigo.resumo)}</p>
            ${state.artigo.corpo.map(blocoHtml).join('')}
        `;
    }

    function renderRelacionados() {
        const destino = $('help-related-list');
        if (!destino || !state.artigo) return;
        destino.innerHTML = state.artigo.relacionados.map((id) => {
            const artigo = byId(id);
            return `<button type="button" class="help-link-button" data-help-open="${escapeHtml(artigo.id)}">${escapeHtml(artigo.titulo)}</button>`;
        }).join('');
    }

    function renderVideos() {
        const destino = $('help-video-list');
        if (!destino) return;
        destino.innerHTML = videos.slice(0, 3).map(([titulo, duracao], index) => `
            <button type="button" class="help-video-card" data-help-video="${escapeHtml(titulo)}">
                <span class="help-video-thumb-small">▶<span class="help-video-duration">${escapeHtml(duracao)}</span></span>
                <span>${escapeHtml(titulo)}</span>
            </button>
        `).join('');
    }

    function renderFaq() {
        const destino = $('help-faq-list');
        if (!destino) return;
        destino.innerHTML = faqs.map(([pergunta, id]) => `<button type="button" class="help-faq-item" data-help-open="${escapeHtml(id)}">${escapeHtml(pergunta)} ›</button>`).join('');
    }

    function registrarAcesso(artigo) {
        const atuais = JSON.parse(localStorage.getItem(STORAGE_LAST) || '[]').filter((item) => item.id !== artigo.id);
        atuais.unshift({ id: artigo.id, titulo: artigo.titulo, quando: new Date().toISOString() });
        localStorage.setItem(STORAGE_LAST, JSON.stringify(atuais.slice(0, 4)));
    }

    function renderUltimos() {
        const destino = $('help-last-list');
        if (!destino) return;
        const acessos = JSON.parse(localStorage.getItem(STORAGE_LAST) || '[]');
        const lista = acessos.length ? acessos : [
            { id: 'importacao-fatura', titulo: 'Importação de Fatura' },
            { id: 'perfis-financeiros', titulo: 'Perfis Financeiros' }
        ];
        destino.innerHTML = lista.map((item, index) => `
            <button type="button" class="help-last-item help-link-button" data-help-open="${escapeHtml(item.id)}">
                <span>${escapeHtml(item.titulo)}</span>
                <small>${index === 0 ? 'Hoje' : 'Recente'}</small>
            </button>
        `).join('');
    }

    function abrirVideo(titulo) {
        $('help-video-title').textContent = titulo || 'Vídeo rápido';
        $('help-video-modal').classList.add('open');
        $('help-video-modal').setAttribute('aria-hidden', 'false');
    }

    function fecharVideo() {
        $('help-video-modal').classList.remove('open');
        $('help-video-modal').setAttribute('aria-hidden', 'true');
    }

    function render() {
        renderNav();
        renderArtigo();
        renderRelacionados();
        renderVideos();
        renderFaq();
        renderUltimos();
    }

    function bind() {
        document.addEventListener('click', (event) => {
            const open = event.target.closest('[data-help-open]');
            if (open) {
                abrirArtigo(open.dataset.helpOpen);
                return;
            }
            const video = event.target.closest('[data-help-video]');
            if (video) {
                abrirVideo(video.dataset.helpVideo);
                return;
            }
            if (event.target.closest('[data-help-video-all]')) {
                abrirVideo('Vídeos rápidos');
                return;
            }
            const scroll = event.target.closest('[data-help-scroll]');
            if (scroll) {
                document.getElementById(scroll.dataset.helpScroll)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        });
        $('help-search-input')?.addEventListener('input', (event) => {
            state.busca = event.target.value || '';
            renderNav();
        });
        $('help-section-filter')?.addEventListener('change', (event) => {
            state.filtro = event.target.value || 'all';
            renderNav();
        });
        $('help-video-close')?.addEventListener('click', fecharVideo);
        $('help-video-ok')?.addEventListener('click', fecharVideo);
        $('help-video-modal')?.addEventListener('click', (event) => {
            if (event.target.id === 'help-video-modal') fecharVideo();
        });
    }

    function init() {
        if (!document.querySelector('[data-help-page]')) return;
        bind();
        const inicial = localStorage.getItem(STORAGE_CURRENT) || 'categoria-cartao';
        state.artigo = byId(inicial);
        render();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
}());
