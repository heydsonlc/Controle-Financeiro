/**
 * Tela Categorias - Categorias de Despesa e Categorias do Cartao.
 */

const API_CATEGORIAS = '/api/categorias';
const API_CATEGORIAS_CARTAO = '/api/categorias-cartao';

const estadoCategorias = {
    categoriasDespesa: [],
    categoriasCartao: [],
    vinculosPorCartao: new Map(),
    palavrasPorCategoria: new Map(),
    abaAtiva: 'despesas',
    filtroStatus: 'ativas',
    pesquisaGeral: '',
    pesquisaCartao: '',
    pesquisaDespesa: '',
    categoriaCartaoSelecionadaId: null,
    categoriaDespesaSelecionadaId: null,
    criandoCategoriaCartao: false,
    categoriaDespesaEditandoId: null,
    categoriaDespesaAtual: null
};

function categoriaIcon(nome) {
    const icons = {
        edit: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5 19h4L19 9a2.1 2.1 0 0 0-3-3L6 16l-1 3Z"/><path d="M14 6l4 4"/></svg>',
        remove: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v5"/><path d="M14 11v5"/></svg>',
        chevron: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6"/></svg>',
        check: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12 4 4L19 6"/></svg>',
        plus: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M5 12h14"/></svg>'
    };
    return icons[nome] || '';
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

function normalizarBusca(value) {
    return String(value || '')
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .toLowerCase()
        .trim();
}

function formatarDataHora(value) {
    if (!value) return '-';
    const data = new Date(value);
    if (Number.isNaN(data.getTime())) return '-';
    return data.toLocaleString('pt-BR', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

async function fetchJson(url, options = {}) {
    const response = await fetch(url, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.success === false) {
        throw new Error(data.error || `Erro HTTP ${response.status}`);
    }
    return data;
}

document.addEventListener('DOMContentLoaded', () => {
    inicializarTelaCategorias();
});

function inicializarTelaCategorias() {
    montarSeletorIcones();
    configurarEventosGerais();
    configurarModalCategoriaDespesa();
    carregarDadosCategorias();
}

function configurarEventosGerais() {
    document.getElementById('btn-nova-categoria-despesa')?.addEventListener('click', abrirModalCategoriaDespesa);
    document.getElementById('btn-nova-categoria-cartao')?.addEventListener('click', iniciarNovaCategoriaCartao);

    document.querySelectorAll('.categorias-tab').forEach((button) => {
        button.addEventListener('click', () => trocarAba(button.dataset.tab));
    });

    document.getElementById('categorias-pesquisa')?.addEventListener('input', (event) => {
        estadoCategorias.pesquisaGeral = event.target.value;
        renderizarTelaCategorias();
    });

    document.getElementById('categorias-status')?.addEventListener('change', (event) => {
        estadoCategorias.filtroStatus = event.target.value;
        ajustarSelecaoCartao();
        renderizarTelaCategorias();
    });

    document.getElementById('busca-categoria-cartao')?.addEventListener('input', (event) => {
        estadoCategorias.pesquisaCartao = event.target.value;
        renderizarCategoriasCartao();
    });

    document.getElementById('busca-categoria-despesa')?.addEventListener('input', (event) => {
        estadoCategorias.pesquisaDespesa = event.target.value;
        ajustarSelecaoDespesa();
        renderizarCategoriasDespesa();
        renderizarDetalheCategoriaDespesa();
    });

    const listaDespesa = document.getElementById('categorias-lista');
    listaDespesa?.addEventListener('click', (event) => {
        const item = event.target.closest('[data-categoria-despesa-id]');
        if (!item) return;
        estadoCategorias.categoriaDespesaSelecionadaId = Number(item.dataset.categoriaDespesaId);
        renderizarCategoriasDespesa();
        renderizarDetalheCategoriaDespesa();
    });

    const listaCartao = document.getElementById('categorias-cartao-lista');
    listaCartao?.addEventListener('click', (event) => {
        const item = event.target.closest('[data-categoria-cartao-id]');
        if (!item) return;
        estadoCategorias.criandoCategoriaCartao = false;
        estadoCategorias.categoriaCartaoSelecionadaId = Number(item.dataset.categoriaCartaoId);
        renderizarCategoriasCartao();
        renderizarDetalheCategoriaCartao();
    });

    const detalhe = document.getElementById('categoria-cartao-detalhe');
    detalhe?.addEventListener('submit', salvarCategoriaCartao);
    detalhe?.addEventListener('click', tratarCliqueDetalheCartao);
    detalhe?.addEventListener('input', tratarInputDetalheCartao);

    const detalheDespesa = document.getElementById('categoria-despesa-detalhe');
    detalheDespesa?.addEventListener('submit', tratarSubmitDetalheDespesa);
    detalheDespesa?.addEventListener('click', tratarCliqueDetalheDespesa);
}

function configurarModalCategoriaDespesa() {
    document.getElementById('form-categoria')?.addEventListener('submit', salvarCategoria);
    document.getElementById('modal-categoria-fechar')?.addEventListener('click', fecharModal);
    document.getElementById('modal-categoria-cancelar')?.addEventListener('click', fecharModal);

    const corInput = document.getElementById('cor');
    corInput?.addEventListener('input', (event) => {
        const el = document.getElementById('cor-valor');
        if (el) el.textContent = event.target.value;
    });

    const iconeInput = document.getElementById('icone');
    iconeInput?.addEventListener('input', (event) => {
        atualizarIconeSelecionado(event.target.value.trim());
    });

    document.getElementById('icone-limpar')?.addEventListener('click', () => definirIconeCategoria(''));
    document.getElementById('logo-enviar')?.addEventListener('click', enviarLogoCategoria);
    document.getElementById('logo-remover')?.addEventListener('click', removerLogoCategoria);

    window.addEventListener('click', (event) => {
        const modal = document.getElementById('modal-categoria');
        if (event.target === modal) fecharModal();
    });
}

async function carregarDadosCategorias() {
    try {
        const [categoriasResp, categoriasCartaoResp] = await Promise.all([
            fetchJson(API_CATEGORIAS),
            fetchJson(API_CATEGORIAS_CARTAO)
        ]);

        estadoCategorias.categoriasDespesa = categoriasResp.data || [];
        estadoCategorias.categoriasCartao = categoriasCartaoResp.data || [];
        await carregarVinculosCategoriasCartao();
        await carregarPalavrasChaveCategorias();
        ajustarSelecaoDespesa();
        ajustarSelecaoCartao();
        renderizarTelaCategorias();
    } catch (error) {
        console.error('Erro ao carregar categorias:', error);
        const lista = document.getElementById('categorias-cartao-lista');
        if (lista) {
            lista.innerHTML = `<p class="empty-state">Erro ao carregar categorias: ${escapeHtml(error.message)}</p>`;
        }
        const despesas = document.getElementById('categorias-lista');
        if (despesas) {
            despesas.innerHTML = `<p class="empty-state">Erro ao carregar categorias: ${escapeHtml(error.message)}</p>`;
        }
    }
}

async function carregarVinculosCategoriasCartao() {
    const pares = await Promise.all(
        estadoCategorias.categoriasCartao.map(async (categoria) => {
            try {
                const resp = await fetchJson(`${API_CATEGORIAS_CARTAO}/${categoria.id}/despesas?ativo=true`);
                return [categoria.id, resp.data || []];
            } catch (error) {
                console.error('Erro ao carregar vinculos da categoria do cartao:', categoria.id, error);
                return [categoria.id, []];
            }
        })
    );

    estadoCategorias.vinculosPorCartao = new Map(pares);
}

async function carregarPalavrasChaveCategorias() {
    const pares = await Promise.all(
        estadoCategorias.categoriasDespesa.map(async (categoria) => {
            try {
                const resp = await fetchJson(`${API_CATEGORIAS}/${categoria.id}/palavras-chave`);
                return [categoria.id, resp.data || []];
            } catch (error) {
                console.error('Erro ao carregar palavras-chave da categoria:', categoria.id, error);
                return [categoria.id, []];
            }
        })
    );

    estadoCategorias.palavrasPorCategoria = new Map(pares);
}

function renderizarTelaCategorias() {
    renderizarResumo();
    renderizarAbas();
    renderizarCategoriasDespesa();
    renderizarDetalheCategoriaDespesa();
    renderizarCategoriasCartao();
    renderizarDetalheCategoriaCartao();
}

function renderizarResumo() {
    const categoriasCartaoAtivas = estadoCategorias.categoriasCartao.filter((categoria) => categoria.ativo);
    const idsCartaoAtivos = new Set(categoriasCartaoAtivas.map((categoria) => categoria.id));
    const idsDespesaVinculados = new Set();

    estadoCategorias.vinculosPorCartao.forEach((vinculos, categoriaCartaoId) => {
        if (!idsCartaoAtivos.has(categoriaCartaoId)) return;
        vinculos.filter((vinculo) => vinculo.ativo).forEach((vinculo) => idsDespesaVinculados.add(vinculo.categoria_id));
    });

    const categoriasDespesaAtivas = estadoCategorias.categoriasDespesa.filter((categoria) => categoria.ativo);
    const semVinculo = categoriasDespesaAtivas.filter((categoria) => !idsDespesaVinculados.has(categoria.id)).length;
    const comPalavrasChave = categoriasDespesaAtivas.filter((categoria) => obterPalavrasChaveCategoria(categoria.id).length > 0).length;

    setText('summary-cartao', categoriasCartaoAtivas.length);
    setText('summary-vinculadas', estadoCategorias.abaAtiva === 'despesas' ? comPalavrasChave : idsDespesaVinculados.size);
    setText('summary-sem-vinculo', semVinculo);

    if (estadoCategorias.abaAtiva === 'despesas') {
        setText('summary-cartao-label', 'Categorias do Cartão');
        setText('summary-cartao-desc', 'Total de categorias de cartão cadastradas no sistema.');
        setText('summary-vinculadas-label', 'Categorias com palavras-chave');
        setText('summary-vinculadas-desc', 'Categorias de despesa com regras de classificação ativas.');
        setText('summary-sem-vinculo-label', 'Categorias sem vínculo');
        setText('summary-sem-vinculo-desc', 'Categorias de despesa ainda não associadas ao cartão.');
    } else {
        setText('summary-cartao-label', 'Categorias do Cartão');
        setText('summary-cartao-desc', 'Total de categorias ativas.');
        setText('summary-vinculadas-label', 'Categorias de Despesa vinculadas');
        setText('summary-vinculadas-desc', 'Total de vinculações ativas.');
        setText('summary-sem-vinculo-label', 'Categorias sem vínculo');
        setText('summary-sem-vinculo-desc', 'Disponíveis para vinculação.');
    }
}

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function renderizarAbas() {
    document.querySelectorAll('.categorias-tab').forEach((button) => {
        const ativa = button.dataset.tab === estadoCategorias.abaAtiva;
        button.classList.toggle('active', ativa);
        button.setAttribute('aria-selected', ativa ? 'true' : 'false');
    });

    document.getElementById('panel-despesas')?.classList.toggle('hidden', estadoCategorias.abaAtiva !== 'despesas');
    document.getElementById('panel-cartao')?.classList.toggle('hidden', estadoCategorias.abaAtiva !== 'cartao');
}

function trocarAba(tab) {
    estadoCategorias.abaAtiva = tab === 'despesas' ? 'despesas' : 'cartao';
    ajustarSelecaoDespesa();
    ajustarSelecaoCartao();
    renderizarTelaCategorias();
}

function categoriasFiltradas(lista, pesquisaAdicional = '') {
    const pesquisas = [estadoCategorias.pesquisaGeral, pesquisaAdicional].map(normalizarBusca).filter(Boolean);
    return lista.filter((categoria) => {
        if (estadoCategorias.filtroStatus === 'ativas' && !categoria.ativo) return false;
        if (estadoCategorias.filtroStatus === 'inativas' && categoria.ativo) return false;
        if (!pesquisas.length) return true;
        const texto = normalizarBusca(`${categoria.nome} ${categoria.descricao || ''}`);
        return pesquisas.every((pesquisa) => texto.includes(pesquisa));
    });
}

function renderizarCategoriasDespesa() {
    const lista = document.getElementById('categorias-lista');
    if (!lista) return;

    const categorias = categoriasFiltradas(estadoCategorias.categoriasDespesa, estadoCategorias.pesquisaDespesa)
        .sort((a, b) => a.nome.localeCompare(b.nome, 'pt-BR'));
    setText('categorias-despesa-contagem', `${categorias.length} ${categorias.length === 1 ? 'categoria' : 'categorias'}`);

    if (categorias.length === 0) {
        lista.innerHTML = `
            <div class="empty-state">
                <h3>Nenhuma Categoria de Despesa encontrada</h3>
                <p>Ajuste a busca ou crie uma nova categoria de despesa.</p>
            </div>
        `;
        return;
    }

    lista.innerHTML = categorias.map((categoria) => {
        const selecionada = categoria.id === estadoCategorias.categoriaDespesaSelecionadaId;
        const categoriaCartao = obterCategoriaCartaoPorDespesa(categoria.id);
        const palavras = obterPalavrasChaveCategoria(categoria.id);

        return `
            <button class="despesa-list-item ${selecionada ? 'selected' : ''}" type="button" data-categoria-despesa-id="${categoria.id}">
                <span class="despesa-list-icon" style="color:${escapeHtml(categoria.cor || '#2563eb')}">${renderizarIconeDespesa(categoria, '22px')}</span>
                <span class="despesa-list-main">
                    <strong>${escapeHtml(categoria.nome)}</strong>
                    <small>${escapeHtml(categoria.descricao || 'Categoria de despesa')}</small>
                </span>
                <span class="despesa-list-meta">
                    <span class="status-dot ${categoria.ativo ? 'active' : ''}"></span>
                    <small>${categoria.ativo ? 'Ativa' : 'Inativa'}</small>
                    <small>${palavras.length} ${palavras.length === 1 ? 'termo' : 'termos'}</small>
                </span>
                <span class="cartao-list-chevron" aria-hidden="true">${categoriaIcon('chevron')}</span>
                ${categoriaCartao ? `<span class="sr-only">Vinculada a ${escapeHtml(categoriaCartao.nome)}</span>` : ''}
            </button>
        `;
    }).join('');
}

function renderizarDetalheCategoriaDespesa() {
    const detalhe = document.getElementById('categoria-despesa-detalhe');
    if (!detalhe) return;

    const categoria = obterCategoriaDespesaSelecionada();
    if (!categoria) {
        detalhe.innerHTML = `
            <div class="detail-empty">
                <h2>Selecione uma Categoria de Despesa</h2>
                <p>Confira dados, v&iacute;nculo operacional e palavras-chave de classifica&ccedil;&atilde;o.</p>
            </div>
        `;
        return;
    }

    const palavras = obterPalavrasChaveCategoria(categoria.id);
    const categoriaCartao = obterCategoriaCartaoPorDespesa(categoria.id);
    const exemplos = gerarExemplosReconhecidos(categoria, palavras, categoriaCartao);

    detalhe.innerHTML = `
        <div class="detail-header despesa-detail-header">
            <div class="detail-identity">
                <span class="detail-icon" style="color:${escapeHtml(categoria.cor || '#2563eb')}">${renderizarIconeDespesa(categoria, '30px')}</span>
                <div>
                    <h2>${escapeHtml(categoria.nome)}</h2>
                    <p>${escapeHtml(categoria.descricao || 'Categoria de despesa usada em despesas, relatórios e lançamentos.')}</p>
                </div>
                <span class="compact-pill ${categoria.ativo ? 'status-ativo' : 'status-inativo'}">${categoria.ativo ? 'Ativa' : 'Inativa'}</span>
            </div>
            <div class="detail-actions">
                <button class="cf-button cf-button-secondary" type="button" data-action="editar-despesa" data-categoria-id="${categoria.id}">
                    ${categoriaIcon('edit')}<span>Editar</span>
                </button>
                <button class="row-action-button danger" type="button" data-action="excluir-despesa" data-categoria-id="${categoria.id}" title="Excluir" aria-label="Excluir">${categoriaIcon('remove')}</button>
            </div>
        </div>

        <section class="detail-card despesa-data-card">
            <h3>Dados da Categoria de Despesa</h3>
            <div class="despesa-data-grid">
                <div><small>Nome</small><strong>${escapeHtml(categoria.nome)}</strong></div>
                <div><small>Cor</small><strong><span class="color-swatch" style="background:${escapeHtml(categoria.cor || '#2563eb')}"></span>${escapeHtml(categoria.cor || '#2563eb')}</strong></div>
                <div><small>&Iacute;cone</small><span class="preview-icon" style="color:${escapeHtml(categoria.cor || '#2563eb')}">${renderizarIconeDespesa(categoria, '24px')}</span></div>
                <div><small>Categoria ativa</small><strong>${categoria.ativo ? 'Sim' : 'N&atilde;o'}</strong></div>
                <div class="wide"><small>Descri&ccedil;&atilde;o</small><p>${escapeHtml(categoria.descricao || 'Sem descri&ccedil;&atilde;o cadastrada.')}</p></div>
                <div><small>Data de cria&ccedil;&atilde;o</small><strong>${formatarDataHora(categoria.criado_em)}</strong></div>
            </div>
        </section>

        <section class="detail-card operational-link-card">
            <h3>Vincula&ccedil;&atilde;o operacional</h3>
            <p>Esta categoria de despesa ser&aacute; associada &agrave;s transa&ccedil;&otilde;es da categoria do cart&atilde;o abaixo.</p>
            ${renderizarVinculoOperacional(categoriaCartao)}
        </section>

        <section class="detail-card keywords-card">
            <div class="card-title-inline">
                <div>
                    <h3>Palavras-chave de classifica&ccedil;&atilde;o</h3>
                    <p>Palavras e termos que, quando encontrados na descri&ccedil;&atilde;o da transa&ccedil;&atilde;o, sugerem esta categoria.</p>
                </div>
            </div>
            <div class="keyword-chip-list">
                ${renderizarPalavrasChave(palavras)}
            </div>
            <form class="keyword-form" id="form-palavra-chave">
                <input type="text" id="nova-palavra-chave" maxlength="120" placeholder="Adicionar nova palavra-chave...">
                <button class="cf-button cf-button-primary" type="submit">
                    <span aria-hidden="true">+</span>
                    <span>Adicionar</span>
                </button>
            </form>
        </section>

        <section class="detail-card examples-card">
            <h3>Exemplos reconhecidos</h3>
            <p>Exemplos de descri&ccedil;&otilde;es de transa&ccedil;&otilde;es que seriam classificadas para esta categoria.</p>
            ${renderizarExemplosReconhecidos(exemplos, categoria, categoriaCartao)}
        </section>
    `;
}

function renderizarVinculoOperacional(categoriaCartao) {
    if (!categoriaCartao) {
        return `
            <div class="operational-link-empty">
                <strong>Categoria ainda sem v&iacute;nculo com Categoria do Cart&atilde;o.</strong>
                <span>Use a aba Categorias do Cart&atilde;o para criar ou ajustar o v&iacute;nculo operacional.</span>
            </div>
        `;
    }

    return `
        <div class="operational-link-item">
            <span class="cartao-list-icon" style="color:${escapeHtml(categoriaCartao.cor || '#2563eb')}">${renderizarIconeCartao(categoriaCartao, '22px')}</span>
            <span>
                <strong>${escapeHtml(categoriaCartao.nome)}</strong>
                <small>${escapeHtml(categoriaCartao.descricao || 'Categoria global do cart&atilde;o')}</small>
            </span>
            <span class="compact-pill vinculo-pill">${categoriaIcon('check')} Categoria do cart&atilde;o vinculada</span>
            <span class="cartao-list-chevron" aria-hidden="true">${categoriaIcon('chevron')}</span>
        </div>
    `;
}

function renderizarPalavrasChave(palavras) {
    if (!palavras.length) {
        return '<div class="empty-inline">Nenhuma palavra-chave cadastrada. Adicione termos para melhorar a classifica&ccedil;&atilde;o autom&aacute;tica.</div>';
    }

    return palavras.map((palavra) => `
        <span class="keyword-chip">
            ${escapeHtml(palavra.palavra)}
            <button type="button" data-action="remover-palavra-chave" data-palavra-id="${palavra.id}" aria-label="Remover palavra-chave ${escapeHtml(palavra.palavra)}">&times;</button>
        </span>
    `).join('');
}

function renderizarExemplosReconhecidos(exemplos, categoria, categoriaCartao) {
    if (!exemplos.length) {
        return `
            <div class="empty-inline">
                Adicione palavras-chave para visualizar exemplos de classifica&ccedil;&atilde;o.
            </div>
        `;
    }

    return `
        <div class="examples-table">
            <div class="examples-table-header">
                <div>Descri&ccedil;&atilde;o da transa&ccedil;&atilde;o</div>
                <div>Categoria de Despesa (esperado)</div>
                <div>Categoria do Cart&atilde;o (esperado)</div>
            </div>
            ${exemplos.map((descricao) => `
                <div class="examples-table-row">
                    <div>${escapeHtml(descricao)}</div>
                    <div><span class="status-dot active"></span>${escapeHtml(categoria.nome)}</div>
                    <div>
                        ${categoriaCartao ? `<span class="chip-icon" style="color:${escapeHtml(categoriaCartao.cor || '#2563eb')}">${renderizarIconeCartao(categoriaCartao, '14px')}</span>${escapeHtml(categoriaCartao.nome)}` : '<span class="text-muted">Sem Categoria do Cart&atilde;o vinculada</span>'}
                    </div>
                </div>
            `).join('')}
        </div>
    `;
}

function gerarExemplosReconhecidos(categoria, palavras, categoriaCartao) {
    if (!palavras.length) return [];
    const termos = palavras.map((item) => item.palavra);
    const exemplos = [];

    if (termos.some((termo) => ['posto', 'shell'].includes(termo))) {
        exemplos.push('POSTO SHELL VILA MARIANA');
    }
    if (termos.some((termo) => ['ipiranga', 'abastecimento'].includes(termo))) {
        exemplos.push('IPIRANGA 0456 - ABASTECIMENTO');
    }
    if (termos.some((termo) => ['petrobras', 'gasolina'].includes(termo))) {
        exemplos.push('PETROBRAS 1234 - GASOLINA COMUM');
    }

    termos.forEach((termo) => {
        if (exemplos.length >= 3) return;
        exemplos.push(`${termo.toUpperCase()} - ${categoria.nome.toUpperCase()}`);
    });

    return [...new Set(exemplos)].slice(0, 3);
}

async function tratarSubmitDetalheDespesa(event) {
    if (event.target.id !== 'form-palavra-chave') return;
    event.preventDefault();

    const categoria = obterCategoriaDespesaSelecionada();
    const input = document.getElementById('nova-palavra-chave');
    const palavra = input?.value.trim();
    if (!categoria || !palavra) return;

    try {
        await fetchJson(`${API_CATEGORIAS}/${categoria.id}/palavras-chave`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ palavra })
        });
        if (input) input.value = '';
        await carregarPalavrasChaveCategorias();
        renderizarResumo();
        renderizarCategoriasDespesa();
        renderizarDetalheCategoriaDespesa();
    } catch (error) {
        console.error('Erro ao adicionar palavra-chave:', error);
        alert(`Erro ao adicionar palavra-chave: ${error.message}`);
    }
}

async function tratarCliqueDetalheDespesa(event) {
    const button = event.target.closest('[data-action]');
    if (!button) return;

    const categoria = obterCategoriaDespesaSelecionada();
    const action = button.dataset.action;

    if (action === 'editar-despesa' && categoria) {
        await editarCategoria(categoria.id);
    } else if (action === 'excluir-despesa' && categoria) {
        confirmarDeletar(categoria.id, categoria.nome);
    } else if (action === 'remover-palavra-chave' && categoria) {
        await removerPalavraChave(categoria.id, Number(button.dataset.palavraId));
    }
}

async function removerPalavraChave(categoriaId, palavraId) {
    try {
        await fetchJson(`${API_CATEGORIAS}/${categoriaId}/palavras-chave/${palavraId}`, {
            method: 'DELETE'
        });
        await carregarPalavrasChaveCategorias();
        renderizarResumo();
        renderizarCategoriasDespesa();
        renderizarDetalheCategoriaDespesa();
    } catch (error) {
        console.error('Erro ao remover palavra-chave:', error);
        alert(`Erro ao remover palavra-chave: ${error.message}`);
    }
}

function renderizarCategoriasCartao() {
    const lista = document.getElementById('categorias-cartao-lista');
    if (!lista) return;

    const pesquisaLocal = normalizarBusca(estadoCategorias.pesquisaCartao);
    const categorias = categoriasFiltradas(estadoCategorias.categoriasCartao)
        .filter((categoria) => !pesquisaLocal || normalizarBusca(`${categoria.nome} ${categoria.descricao || ''}`).includes(pesquisaLocal));

    if (categorias.length === 0) {
        lista.innerHTML = `
            <div class="cartao-empty">
                <h3>Nenhuma Categoria do Cart&atilde;o</h3>
                <p>Crie uma categoria global para agrupar despesas do cartao.</p>
            </div>
        `;
        return;
    }

    lista.innerHTML = categorias.map((categoria) => {
        const selecionada = !estadoCategorias.criandoCategoriaCartao && categoria.id === estadoCategorias.categoriaCartaoSelecionadaId;
        const totalVinculos = obterVinculosAtivos(categoria.id).length;
        const icone = renderizarIconeCartao(categoria, '22px');
        return `
            <button class="cartao-list-item ${selecionada ? 'selected' : ''}" type="button" data-categoria-cartao-id="${categoria.id}">
                <span class="cartao-list-icon" style="color:${escapeHtml(categoria.cor || '#2563eb')}">${icone}</span>
                <span class="cartao-list-main">
                    <strong>${escapeHtml(categoria.nome)}</strong>
                    <small>${escapeHtml(categoria.descricao || 'Categoria global do cartao')}</small>
                </span>
                <span class="cartao-list-count">
                    <strong>${totalVinculos}</strong>
                    <small>${totalVinculos === 1 ? 'vinculada' : 'vinculadas'}</small>
                </span>
                <span class="cartao-list-status ${categoria.ativo ? 'active' : 'inactive'}" aria-label="${categoria.ativo ? 'Ativa' : 'Inativa'}"></span>
                <span class="cartao-list-chevron" aria-hidden="true">${categoriaIcon('chevron')}</span>
            </button>
        `;
    }).join('');
}

function renderizarDetalheCategoriaCartao() {
    const detalhe = document.getElementById('categoria-cartao-detalhe');
    if (!detalhe) return;

    const categoria = obterCategoriaCartaoSelecionada();
    if (!categoria && !estadoCategorias.criandoCategoriaCartao) {
        detalhe.innerHTML = `
            <div class="detail-empty">
                <h2>Selecione uma Categoria do Cart&atilde;o</h2>
                <p>Crie ou escolha uma categoria global para editar seus dados e vincular Categorias de Despesa.</p>
            </div>
        `;
        return;
    }

    const emCriacao = estadoCategorias.criandoCategoriaCartao;
    const formCategoria = categoria || {
        id: '',
        nome: '',
        descricao: '',
        cor: '#2563eb',
        icone: '',
        ativo: true
    };
    const vinculos = emCriacao ? [] : obterVinculosAtivos(formCategoria.id);
    const categoriasDisponiveis = emCriacao ? [] : obterCategoriasDespesaDisponiveis();
    const icone = renderizarIconeCartao(formCategoria, '30px');
    const opcoesIcone = montarOpcoesIconeCartao(formCategoria.icone);
    const gradeIcones = montarGradeIconesCartao(formCategoria.icone);

    detalhe.innerHTML = `
        <div class="detail-header">
            <div class="detail-identity">
                <span class="detail-icon" id="cartao-detail-icon" style="color:${escapeHtml(formCategoria.cor || '#2563eb')}">${icone}</span>
                <div>
                    <h2>${escapeHtml(formCategoria.nome || 'Nova Categoria do Cart\u00e3o')}</h2>
                    <p>${escapeHtml(formCategoria.descricao || 'Categoria global usada para agrupar despesas no cart\u00e3o.')}</p>
                </div>
            </div>
            <div class="detail-actions">
                ${!emCriacao ? `
                    <span class="compact-pill ${formCategoria.ativo ? 'status-ativo' : 'status-inativo'}">${formCategoria.ativo ? 'Ativa' : 'Inativa'}</span>
                    <span class="compact-pill vinculo-pill">${vinculos.length} ${vinculos.length === 1 ? 'categoria vinculada' : 'categorias vinculadas'}</span>
                    <button class="cf-button cf-button-danger" type="button" data-action="toggle-status">
                        ${formCategoria.ativo ? 'Desativar categoria' : 'Reativar categoria'}
                    </button>
                ` : ''}
                <button class="cf-button cf-button-primary" type="submit" form="form-categoria-cartao">Salvar altera&ccedil;&otilde;es</button>
            </div>
        </div>

        <div class="detail-grid">
            <form class="detail-card" id="form-categoria-cartao">
                <input type="hidden" id="cartao-categoria-id" value="${escapeHtml(formCategoria.id)}">
                <h3>Dados da Categoria do Cart&atilde;o</h3>
                <div class="form-group light">
                    <label for="cartao-nome">Nome</label>
                    <input type="text" id="cartao-nome" required maxlength="100" value="${escapeHtml(formCategoria.nome)}" placeholder="Ex: Mobilidade">
                </div>
                <div class="form-group light">
                    <label for="cartao-descricao">Descri&ccedil;&atilde;o</label>
                    <textarea id="cartao-descricao" rows="4" placeholder="Agrupa gastos de deslocamento, veiculo e transporte">${escapeHtml(formCategoria.descricao || '')}</textarea>
                </div>
                <div class="form-row two-cols">
                    <div class="form-group light">
                        <label for="cartao-cor">Cor de exibi&ccedil;&atilde;o</label>
                        <div class="color-picker light">
                            <input type="color" id="cartao-cor" value="${escapeHtml(formCategoria.cor || '#2563eb')}">
                            <span id="cartao-cor-valor">${escapeHtml(formCategoria.cor || '#2563eb')}</span>
                        </div>
                    </div>
                    <div class="form-group light">
                        <label for="cartao-icone">&Iacute;cone</label>
                        <div class="cartao-icone-select-row">
                            <span class="cartao-icone-preview" id="cartao-icone-preview" aria-hidden="true">${icone}</span>
                            <select id="cartao-icone">${opcoesIcone}</select>
                        </div>
                        <small class="form-hint">Lista propria de icones da Categoria do Cartao.</small>
                        <div class="cartao-icone-picker-grid" id="cartao-icone-picker-grid" aria-label="Icones da Categoria do Cartao">
                            ${gradeIcones}
                        </div>
                    </div>
                </div>
                <label class="checkbox-label light">
                    <input type="checkbox" id="cartao-ativo" ${formCategoria.ativo ? 'checked' : ''}>
                    <span>Categoria ativa</span>
                </label>
            </form>

            <section class="detail-card vinculos-card">
                <div class="card-title-row">
                    <h3>Categorias de Despesa Vinculadas</h3>
                    <button class="cf-button cf-button-secondary" type="button" data-action="nova-vinculacao" ${emCriacao ? 'disabled' : ''}>
                        <span aria-hidden="true">+</span>
                        <span>Nova vincula&ccedil;&atilde;o</span>
                    </button>
                </div>
                ${renderizarBlocoVinculos(vinculos, categoriasDisponiveis, emCriacao)}
            </section>
        </div>

        <section class="classification-rule">
            <h3>Regra de classifica&ccedil;&atilde;o</h3>
            <p>Quando uma despesa lan&ccedil;ada no cart&atilde;o tiver uma destas categorias de despesa, ela ser&aacute; agrupada em <strong>${escapeHtml(formCategoria.nome || 'esta Categoria do Cart\u00e3o')}</strong>.</p>
        </section>

        <section class="detail-card vinculos-history">
            <div class="vinculos-table">
                <div class="vinculos-table-header">
                    <div>Categoria de Despesa</div>
                    <div>Status</div>
                    <div>Origem da classifica&ccedil;&atilde;o</div>
                    <div>Vinculada em</div>
                    <div></div>
                </div>
                ${renderizarHistoricoVinculos(vinculos)}
            </div>
        </section>
    `;
}

function renderizarBlocoVinculos(vinculos, disponiveis, emCriacao) {
    if (emCriacao) {
        return `
            <div class="empty-inline">
                Salve a Categoria do Cart&atilde;o antes de vincular Categorias de Despesa.
            </div>
        `;
    }

    const vinculadasHtml = vinculos.length
        ? vinculos.map((vinculo) => {
            const categoria = obterCategoriaDespesa(vinculo.categoria_id);
            return `
                <button class="linked-chip" type="button" data-action="desvincular" data-categoria-id="${vinculo.categoria_id}" title="Desvincular">
                    <span class="chip-check" aria-hidden="true">${categoriaIcon('check')}</span>
                    <span class="chip-icon" style="color:${escapeHtml(categoria?.cor || '#64748b')}">${renderizarIconeDespesa(categoria, '14px')}</span>
                    <span>${escapeHtml(categoria?.nome || vinculo.categoria_nome || 'Categoria')}</span>
                </button>
            `;
        }).join('')
        : '<div class="empty-inline">Nenhuma Categoria de Despesa vinculada.</div>';

    const disponiveisHtml = disponiveis.length
        ? disponiveis.map((categoria) => `
            <button class="available-chip" type="button" data-action="vincular" data-categoria-id="${categoria.id}">
                <span class="chip-box" aria-hidden="true"></span>
                <span class="chip-icon" style="color:${escapeHtml(categoria.cor || '#64748b')}">${renderizarIconeDespesa(categoria, '14px')}</span>
                <span>${escapeHtml(categoria.nome)}</span>
            </button>
        `).join('')
        : '<div class="empty-inline">Todas as Categorias de Despesa ativas j&aacute; est&atilde;o vinculadas.</div>';

    return `
        <div class="vinculos-section">
            <h4>Vinculadas (${vinculos.length})</h4>
            <div class="chip-list">${vinculadasHtml}</div>
        </div>
        <div class="vinculos-section">
            <h4>Dispon&iacute;veis (n&atilde;o vinculadas)</h4>
            <div class="chip-list" id="categorias-disponiveis-lista">${disponiveisHtml}</div>
        </div>
    `;
}

function renderizarHistoricoVinculos(vinculos) {
    if (!vinculos.length) {
        return `
            <div class="vinculos-empty-row">
                Nenhum v&iacute;nculo ativo para esta Categoria do Cart&atilde;o.
            </div>
        `;
    }

    return vinculos.map((vinculo) => {
        const categoria = obterCategoriaDespesa(vinculo.categoria_id);
        return `
            <div class="vinculos-table-row">
                <div class="table-category">
                    <span class="chip-icon" style="color:${escapeHtml(categoria?.cor || '#64748b')}">${renderizarIconeDespesa(categoria, '14px')}</span>
                    <span>${escapeHtml(categoria?.nome || vinculo.categoria_nome || 'Categoria')}</span>
                </div>
                <div><span class="status-dot active"></span> Vinculada</div>
                <div>Regra da categoria do cartao</div>
                <div>${formatarDataHora(vinculo.created_at)}</div>
                <div class="row-actions">
                    <button class="row-action-button danger" type="button" data-action="desvincular" data-categoria-id="${vinculo.categoria_id}" title="Desvincular" aria-label="Desvincular">${categoriaIcon('remove')}</button>
                </div>
            </div>
        `;
    }).join('');
}

function tratarInputDetalheCartao(event) {
    if (event.target.id === 'cartao-cor') {
        const valor = event.target.value;
        const label = document.getElementById('cartao-cor-valor');
        const icon = document.getElementById('cartao-detail-icon');
        if (label) label.textContent = valor;
        if (icon) icon.style.color = valor;
    }

    if (event.target.id === 'cartao-icone') {
        atualizarPreviewIconeCartao(event.target.value);
    }
}

async function tratarCliqueDetalheCartao(event) {
    const button = event.target.closest('[data-action]');
    if (!button) return;

    const action = button.dataset.action;
    if (action === 'vincular') {
        await vincularCategoriaDespesa(Number(button.dataset.categoriaId));
    } else if (action === 'desvincular') {
        await desvincularCategoriaDespesa(Number(button.dataset.categoriaId));
    } else if (action === 'toggle-status') {
        await alternarStatusCategoriaCartao();
    } else if (action === 'nova-vinculacao') {
        document.getElementById('categorias-disponiveis-lista')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    } else if (action === 'selecionar-icone-cartao') {
        selecionarIconeCartao(button.dataset.iconKey || '');
    }
}

async function salvarCategoriaCartao(event) {
    event.preventDefault();

    const id = document.getElementById('cartao-categoria-id')?.value;
    const dados = {
        nome: document.getElementById('cartao-nome')?.value.trim(),
        descricao: document.getElementById('cartao-descricao')?.value.trim(),
        cor: document.getElementById('cartao-cor')?.value || '#2563eb',
        icone: document.getElementById('cartao-icone')?.value || null,
        ativo: document.getElementById('cartao-ativo')?.checked ?? true
    };

    if (!dados.nome) {
        alert('Informe o nome da Categoria do Cartao.');
        return;
    }

    try {
        const response = await fetchJson(id ? `${API_CATEGORIAS_CARTAO}/${id}` : API_CATEGORIAS_CARTAO, {
            method: id ? 'PUT' : 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        });

        estadoCategorias.criandoCategoriaCartao = false;
        estadoCategorias.categoriaCartaoSelecionadaId = response.data.id;
        await carregarDadosCategorias();
    } catch (error) {
        console.error('Erro ao salvar Categoria do Cartao:', error);
        alert(`Erro ao salvar Categoria do Cartao: ${error.message}`);
    }
}

async function alternarStatusCategoriaCartao() {
    const categoria = obterCategoriaCartaoSelecionada();
    if (!categoria) return;

    const acao = categoria.ativo ? 'desativar' : 'reativar';
    if (!confirm(`Deseja ${acao} a Categoria do Cartao "${categoria.nome}"?`)) return;

    try {
        if (categoria.ativo) {
            await fetchJson(`${API_CATEGORIAS_CARTAO}/${categoria.id}`, { method: 'DELETE' });
        } else {
            await fetchJson(`${API_CATEGORIAS_CARTAO}/${categoria.id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ativo: true })
            });
        }
        await carregarDadosCategorias();
    } catch (error) {
        console.error('Erro ao atualizar status:', error);
        alert(`Erro ao atualizar status: ${error.message}`);
    }
}

async function vincularCategoriaDespesa(categoriaId) {
    const categoriaCartao = obterCategoriaCartaoSelecionada();
    if (!categoriaCartao) {
        alert('Salve a Categoria do Cartao antes de criar vinculos.');
        return;
    }

    try {
        await fetchJson(`${API_CATEGORIAS_CARTAO}/${categoriaCartao.id}/despesas`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ categoria_id: categoriaId, ativo: true })
        });
        await carregarDadosCategorias();
    } catch (error) {
        console.error('Erro ao vincular Categoria de Despesa:', error);
        alert(`Erro ao vincular Categoria de Despesa: ${error.message}`);
    }
}

async function desvincularCategoriaDespesa(categoriaId) {
    const categoriaCartao = obterCategoriaCartaoSelecionada();
    if (!categoriaCartao) return;

    try {
        await fetchJson(`${API_CATEGORIAS_CARTAO}/${categoriaCartao.id}/despesas/${categoriaId}`, {
            method: 'DELETE'
        });
        await carregarDadosCategorias();
    } catch (error) {
        console.error('Erro ao desvincular Categoria de Despesa:', error);
        alert(`Erro ao desvincular Categoria de Despesa: ${error.message}`);
    }
}

function iniciarNovaCategoriaCartao() {
    estadoCategorias.abaAtiva = 'cartao';
    estadoCategorias.criandoCategoriaCartao = true;
    estadoCategorias.categoriaCartaoSelecionadaId = null;
    renderizarTelaCategorias();
    document.getElementById('cartao-nome')?.focus();
}

function ajustarSelecaoCartao() {
    if (estadoCategorias.criandoCategoriaCartao) return;
    const visiveis = categoriasFiltradas(estadoCategorias.categoriasCartao);
    const selecionadaExiste = visiveis.some((categoria) => categoria.id === estadoCategorias.categoriaCartaoSelecionadaId);
    estadoCategorias.categoriaCartaoSelecionadaId = selecionadaExiste
        ? estadoCategorias.categoriaCartaoSelecionadaId
        : (visiveis[0]?.id || null);
}

function ajustarSelecaoDespesa() {
    const visiveis = categoriasFiltradas(estadoCategorias.categoriasDespesa, estadoCategorias.pesquisaDespesa)
        .sort((a, b) => a.nome.localeCompare(b.nome, 'pt-BR'));
    const selecionadaExiste = visiveis.some((categoria) => categoria.id === estadoCategorias.categoriaDespesaSelecionadaId);
    estadoCategorias.categoriaDespesaSelecionadaId = selecionadaExiste
        ? estadoCategorias.categoriaDespesaSelecionadaId
        : (visiveis[0]?.id || null);
}

function obterCategoriaCartaoSelecionada() {
    if (!estadoCategorias.categoriaCartaoSelecionadaId) return null;
    return estadoCategorias.categoriasCartao.find((categoria) => categoria.id === estadoCategorias.categoriaCartaoSelecionadaId) || null;
}

function obterCategoriaDespesaSelecionada() {
    if (!estadoCategorias.categoriaDespesaSelecionadaId) return null;
    return obterCategoriaDespesa(estadoCategorias.categoriaDespesaSelecionadaId);
}

function obterCategoriaDespesa(categoriaId) {
    return estadoCategorias.categoriasDespesa.find((categoria) => categoria.id === Number(categoriaId)) || null;
}

function obterPalavrasChaveCategoria(categoriaId) {
    return (estadoCategorias.palavrasPorCategoria.get(Number(categoriaId)) || [])
        .filter((palavra) => palavra.ativo);
}

function obterVinculosAtivos(categoriaCartaoId) {
    return (estadoCategorias.vinculosPorCartao.get(Number(categoriaCartaoId)) || [])
        .filter((vinculo) => vinculo.ativo);
}

function obterIdsDespesaVinculadosGlobal() {
    const ids = new Set();
    estadoCategorias.vinculosPorCartao.forEach((vinculos, categoriaCartaoId) => {
        const categoriaCartao = estadoCategorias.categoriasCartao.find((categoria) => categoria.id === Number(categoriaCartaoId));
        if (!categoriaCartao?.ativo) return;
        vinculos.filter((vinculo) => vinculo.ativo).forEach((vinculo) => ids.add(vinculo.categoria_id));
    });
    return ids;
}

function obterCategoriasDespesaDisponiveis() {
    const vinculadas = obterIdsDespesaVinculadosGlobal();
    return estadoCategorias.categoriasDespesa
        .filter((categoria) => categoria.ativo && !vinculadas.has(categoria.id))
        .sort((a, b) => a.nome.localeCompare(b.nome, 'pt-BR'));
}

function obterCategoriaCartaoPorDespesa(categoriaId) {
    let categoriaCartaoEncontrada = null;
    estadoCategorias.vinculosPorCartao.forEach((vinculos, categoriaCartaoId) => {
        if (categoriaCartaoEncontrada) return;
        const temVinculo = vinculos.some((vinculo) => vinculo.ativo && vinculo.categoria_id === categoriaId);
        if (temVinculo) {
            categoriaCartaoEncontrada = estadoCategorias.categoriasCartao.find((categoria) => categoria.id === Number(categoriaCartaoId)) || null;
        }
    });
    return categoriaCartaoEncontrada;
}

function renderizarIconeCartao(categoria, size) {
    if (window.CategoriaCartaoIconesUI?.renderIconeCategoriaCartao) {
        const pixels = Number.parseInt(String(size || '30px'), 10) || 30;
        return window.CategoriaCartaoIconesUI.renderIconeCategoriaCartao(categoria, {
            sizePx: pixels,
            className: 'categoria-cartao-icon--inline',
            label: categoria?.nome || 'Categoria do Cartao'
        });
    }
    if (typeof renderIcon === 'function') {
        return renderIcon(categoria?.icone || 'credit-card', { size });
    }
    return '';
}

function renderizarIconeDespesa(categoria, size) {
    if (categoria && typeof renderCategoryVisual === 'function') {
        return renderCategoryVisual(categoria, { size, alt: categoria.nome });
    }
    if (typeof renderIcon === 'function') {
        return renderIcon('tag', { size });
    }
    return '';
}

function montarOpcoesIconeCartao(iconeAtual) {
    const icones = window.CategoriaCartaoIconesUI?.listarIconesCategoriaCartao?.() || [];
    const atual = iconeAtual || '';
    const existeAtual = icones.some((icone) => icone.key === atual);
    return [
        `<option value="">Sem icone</option>`,
        ...icones.map((icone) => `<option value="${escapeHtml(icone.key)}" ${icone.key === atual ? 'selected' : ''}>${escapeHtml(icone.nome)}</option>`),
        atual && !existeAtual ? `<option value="${escapeHtml(atual)}" selected>Icone antigo indisponivel (${escapeHtml(atual)})</option>` : ''
    ].join('');
}

function montarGradeIconesCartao(iconeAtual) {
    const icones = window.CategoriaCartaoIconesUI?.listarIconesCategoriaCartao?.() || [];
    if (!icones.length) {
        return '<div class="empty-inline">Nenhum icone local de Categoria do Cartao encontrado.</div>';
    }
    return icones.map((icone) => {
        const ativo = icone.key === iconeAtual;
        const preview = window.CategoriaCartaoIconesUI.renderIconeCategoriaCartao(icone.key, {
            size: 'sm',
            className: 'categoria-cartao-icon--picker',
            label: icone.nome
        });
        return `
            <button type="button" class="cartao-icone-picker-option ${ativo ? 'active' : ''}" data-action="selecionar-icone-cartao" data-icon-key="${escapeHtml(icone.key)}" aria-pressed="${ativo ? 'true' : 'false'}" title="${escapeHtml(icone.nome)}">
                ${preview}
                <span>${escapeHtml(icone.nome)}</span>
            </button>
        `;
    }).join('');
}

function selecionarIconeCartao(key) {
    const select = document.getElementById('cartao-icone');
    if (select) {
        select.value = key || '';
    }
    atualizarPreviewIconeCartao(key || '');
}

function atualizarPreviewIconeCartao(key) {
    const categoria = {
        icone: key,
        nome: document.getElementById('cartao-nome')?.value || 'Categoria do Cartao',
        cor: document.getElementById('cartao-cor')?.value || '#2563eb'
    };
    const html = renderizarIconeCartao(categoria, '30px');
    const icon = document.getElementById('cartao-detail-icon');
    const preview = document.getElementById('cartao-icone-preview');
    if (icon) icon.innerHTML = html;
    if (preview) preview.innerHTML = html;

    document.querySelectorAll('.cartao-icone-picker-option').forEach((button) => {
        const ativo = button.dataset.iconKey === key;
        button.classList.toggle('active', ativo);
        button.setAttribute('aria-pressed', ativo ? 'true' : 'false');
    });
}

function montarSeletorIcones() {
    const grid = document.getElementById('icone-picker-grid');
    if (!grid || typeof getIconKeys !== 'function' || typeof renderIcon !== 'function') return;

    const keys = getIconKeys();
    grid.innerHTML = keys.map((key) => `
        <button type="button" class="icone-picker-option" data-icon-key="${escapeHtml(key)}" title="${escapeHtml(key)}" aria-label="Selecionar icone ${escapeHtml(key)}">
            <span class="icone-picker-option-icon" aria-hidden="true">${renderIcon(key, { size: '18px' })}</span>
            <span class="icone-picker-option-label">${escapeHtml(key)}</span>
        </button>
    `).join('');

    grid.querySelectorAll('.icone-picker-option').forEach((button) => {
        button.addEventListener('click', () => definirIconeCategoria(button.dataset.iconKey || ''));
    });
}

function definirIconeCategoria(key) {
    const iconeInput = document.getElementById('icone');
    if (iconeInput) {
        iconeInput.value = key || '';
    }
    atualizarIconeSelecionado(key || '');
}

function atualizarIconeSelecionado(key) {
    const chave = (key || '').trim();
    const preview = document.getElementById('icone-preview');
    if (preview) {
        preview.innerHTML = chave && typeof renderIcon === 'function'
            ? renderIcon(chave, { size: '22px' })
            : '';
    }

    document.querySelectorAll('.icone-picker-option').forEach((button) => {
        const ativo = button.dataset.iconKey === chave;
        button.classList.toggle('active', ativo);
        button.setAttribute('aria-pressed', ativo ? 'true' : 'false');
    });

    const limparIcone = document.getElementById('icone-limpar');
    if (limparIcone) {
        limparIcone.classList.toggle('active', !chave);
        limparIcone.setAttribute('aria-pressed', !chave ? 'true' : 'false');
    }
}

function atualizarLogoPanel(categoria) {
    const temCategoria = Boolean(categoria && categoria.id);
    const preview = document.getElementById('logo-preview');
    const input = document.getElementById('logo-upload-input');
    const enviar = document.getElementById('logo-enviar');
    const remover = document.getElementById('logo-remover');
    const status = document.getElementById('logo-upload-status');

    if (preview) {
        preview.innerHTML = categoria?.logo_url
            ? `<img src="${escapeHtml(categoria.logo_url)}" alt="" loading="lazy" onerror="this.remove()">`
            : '';
    }

    if (input) {
        input.value = '';
        input.disabled = !temCategoria;
    }

    if (enviar) enviar.disabled = !temCategoria;
    if (remover) remover.disabled = !temCategoria || !categoria?.logo_url;

    if (status) {
        if (!temCategoria) {
            status.textContent = 'Salve a categoria antes de enviar logo.';
        } else if (categoria?.logo_url) {
            status.textContent = 'Logo personalizado ativo. Ao remover, o icone do catalogo volta a aparecer.';
        } else {
            status.textContent = 'Nenhum logo personalizado. O icone do catalogo sera usado como fallback.';
        }
    }
}

async function enviarLogoCategoria() {
    if (!estadoCategorias.categoriaDespesaEditandoId) {
        alert('Salve a categoria antes de enviar logo.');
        return;
    }

    const input = document.getElementById('logo-upload-input');
    const arquivo = input?.files?.[0];
    if (!arquivo) {
        alert('Selecione um arquivo PNG, JPG ou WebP.');
        return;
    }

    const formData = new FormData();
    formData.append('file', arquivo);

    try {
        const data = await fetchJson(`${API_CATEGORIAS}/${estadoCategorias.categoriaDespesaEditandoId}/logo`, {
            method: 'POST',
            body: formData
        });

        estadoCategorias.categoriaDespesaAtual = data.data;
        atualizarLogoPanel(estadoCategorias.categoriaDespesaAtual);
        await carregarDadosCategorias();
    } catch (error) {
        console.error('Erro ao enviar logo:', error);
        alert(`Erro ao enviar logo: ${error.message}`);
    }
}

async function removerLogoCategoria() {
    if (!estadoCategorias.categoriaDespesaEditandoId) {
        alert('Salve a categoria antes de remover logo.');
        return;
    }

    try {
        const data = await fetchJson(`${API_CATEGORIAS}/${estadoCategorias.categoriaDespesaEditandoId}/logo`, {
            method: 'DELETE'
        });

        estadoCategorias.categoriaDespesaAtual = data.data;
        atualizarLogoPanel(estadoCategorias.categoriaDespesaAtual);
        await carregarDadosCategorias();
    } catch (error) {
        console.error('Erro ao remover logo:', error);
        alert(`Erro ao remover logo: ${error.message}`);
    }
}

function abrirModalCategoriaDespesa() {
    estadoCategorias.categoriaDespesaEditandoId = null;
    estadoCategorias.categoriaDespesaAtual = null;
    document.getElementById('modal-titulo').textContent = 'Nova Categoria de Despesa';
    document.getElementById('form-categoria').reset();
    document.getElementById('categoria-id').value = '';
    document.getElementById('cor').value = '#6c757d';
    document.getElementById('cor-valor').textContent = '#6c757d';
    document.getElementById('ativo').checked = true;
    const iconeEl = document.getElementById('icone');
    if (iconeEl) iconeEl.value = '';
    atualizarIconeSelecionado('');
    atualizarLogoPanel(null);
    document.getElementById('modal-categoria').classList.add('open');
}

function fecharModal() {
    document.getElementById('modal-categoria').classList.remove('open');
    estadoCategorias.categoriaDespesaEditandoId = null;
    estadoCategorias.categoriaDespesaAtual = null;
}

async function editarCategoria(id) {
    try {
        const data = await fetchJson(`${API_CATEGORIAS}/${id}`);
        const categoria = data.data;
        estadoCategorias.categoriaDespesaEditandoId = id;
        estadoCategorias.categoriaDespesaAtual = categoria;

        document.getElementById('modal-titulo').textContent = 'Editar Categoria de Despesa';
        document.getElementById('categoria-id').value = categoria.id;
        document.getElementById('nome').value = categoria.nome;
        document.getElementById('descricao').value = categoria.descricao || '';
        document.getElementById('cor').value = categoria.cor || '#6c757d';
        document.getElementById('cor-valor').textContent = categoria.cor || '#6c757d';
        document.getElementById('ativo').checked = categoria.ativo;
        const iconeEl = document.getElementById('icone');
        if (iconeEl) iconeEl.value = categoria.icone || '';
        atualizarIconeSelecionado(categoria.icone || '');
        atualizarLogoPanel(categoria);
        document.getElementById('modal-categoria').classList.add('open');
    } catch (error) {
        console.error('Erro ao carregar categoria:', error);
        alert(`Erro ao carregar categoria: ${error.message}`);
    }
}

async function salvarCategoria(event) {
    event.preventDefault();

    const id = document.getElementById('categoria-id').value;
    const dados = {
        nome: document.getElementById('nome').value.trim(),
        descricao: document.getElementById('descricao').value.trim(),
        cor: document.getElementById('cor').value,
        icone: document.getElementById('icone')?.value.trim() || null,
        ativo: document.getElementById('ativo').checked
    };

    try {
        const response = await fetchJson(id ? `${API_CATEGORIAS}/${id}` : API_CATEGORIAS, {
            method: id ? 'PUT' : 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        });

        estadoCategorias.categoriaDespesaSelecionadaId = response.data?.id || Number(id) || estadoCategorias.categoriaDespesaSelecionadaId;
        fecharModal();
        await carregarDadosCategorias();
    } catch (error) {
        console.error('Erro ao salvar categoria:', error);
        alert(`Erro ao salvar categoria: ${error.message}`);
    }
}

function confirmarDeletar(id, nome) {
    if (confirm(`Tem certeza que deseja excluir a categoria "${nome}"?`)) {
        deletarCategoria(id);
    }
}

async function deletarCategoria(id) {
    try {
        await fetchJson(`${API_CATEGORIAS}/${id}`, { method: 'DELETE' });
        if (estadoCategorias.categoriaDespesaSelecionadaId === id) {
            estadoCategorias.categoriaDespesaSelecionadaId = null;
        }
        await carregarDadosCategorias();
    } catch (error) {
        console.error('Erro ao excluir categoria:', error);
        alert(`Erro ao excluir categoria: ${error.message}`);
    }
}

window.abrirModal = abrirModalCategoriaDespesa;
window.fecharModal = fecharModal;
window.editarCategoria = editarCategoria;
window.salvarCategoria = salvarCategoria;
window.confirmarDeletar = confirmarDeletar;
window.deletarCategoria = deletarCategoria;
