/**
 * Tela Categorias - Categorias de Despesa e Categorias do Cartao.
 */

const API_CATEGORIAS = '/api/categorias';
const API_CATEGORIAS_CARTAO = '/api/categorias-cartao';

const estadoCategorias = {
    categoriasDespesa: [],
    categoriasCartao: [],
    vinculosPorCartao: new Map(),
    abaAtiva: 'cartao',
    filtroStatus: 'ativas',
    pesquisaGeral: '',
    pesquisaCartao: '',
    categoriaCartaoSelecionadaId: null,
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

function renderizarTelaCategorias() {
    renderizarResumo();
    renderizarAbas();
    renderizarCategoriasDespesa();
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

    setText('summary-cartao', categoriasCartaoAtivas.length);
    setText('summary-vinculadas', idsDespesaVinculados.size);
    setText('summary-sem-vinculo', semVinculo);
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
    renderizarTelaCategorias();
}

function categoriasFiltradas(lista) {
    const pesquisa = normalizarBusca(estadoCategorias.pesquisaGeral);
    return lista.filter((categoria) => {
        if (estadoCategorias.filtroStatus === 'ativas' && !categoria.ativo) return false;
        if (estadoCategorias.filtroStatus === 'inativas' && categoria.ativo) return false;
        if (!pesquisa) return true;
        return normalizarBusca(`${categoria.nome} ${categoria.descricao || ''}`).includes(pesquisa);
    });
}

function renderizarCategoriasDespesa() {
    const lista = document.getElementById('categorias-lista');
    if (!lista) return;

    const categorias = categoriasFiltradas(estadoCategorias.categoriasDespesa);
    if (categorias.length === 0) {
        lista.innerHTML = `
            <div class="empty-state">
                <h3>Nenhuma Categoria de Despesa encontrada</h3>
                <p>Ajuste a busca ou crie uma nova categoria de despesa.</p>
            </div>
        `;
        return;
    }

    const linhas = categorias.map((categoria) => {
        const visualHtml = typeof renderCategoryVisual === 'function'
            ? renderCategoryVisual(categoria, { size: '16px', alt: categoria.nome })
            : '';
        const iconeHtml = visualHtml
            ? `<span class="category-icon" style="color:${escapeHtml(categoria.cor || '#6c757d')}">${visualHtml}</span>`
            : `<span class="categoria-dot" style="background-color:${escapeHtml(categoria.cor || '#6c757d')}" aria-hidden="true"></span>`;
        const categoriaCartao = obterCategoriaCartaoPorDespesa(categoria.id);
        const vinculoLabel = categoriaCartao
            ? `<span class="compact-pill vinculo-pill">${escapeHtml(categoriaCartao.nome)}</span>`
            : '<span class="text-muted">Sem v&iacute;nculo</span>';

        return `
            <div class="compact-row categoria-row categorias-despesa-row">
                <div class="compact-cell col-descricao">
                    <span class="titulo">
                        ${iconeHtml}
                        <span class="categoria-nome-texto">${escapeHtml(categoria.nome)}</span>
                    </span>
                </div>
                <div class="compact-cell compact-meta">${escapeHtml(categoria.descricao || '-')}</div>
                <div class="compact-cell">${vinculoLabel}</div>
                <div class="compact-cell">
                    <span class="compact-pill status ${categoria.ativo ? 'status-ativo' : 'status-inativo'}">
                        ${categoria.ativo ? 'Ativa' : 'Inativa'}
                    </span>
                </div>
                <div class="compact-cell row-actions acoes">
                    <button class="row-action-button" type="button" onclick="editarCategoria(${categoria.id})" title="Editar" aria-label="Editar">${categoriaIcon('edit')}</button>
                    <button class="row-action-button danger" type="button" onclick="confirmarDeletar(${categoria.id}, ${escapeHtml(JSON.stringify(categoria.nome))})" title="Excluir" aria-label="Excluir">${categoriaIcon('remove')}</button>
                </div>
            </div>
        `;
    }).join('');

    lista.innerHTML = `
        <div class="compact-table categorias-despesa-table">
            <div class="compact-table-header categorias-despesa-row">
                <div>Categoria</div>
                <div>Descri&ccedil;&atilde;o</div>
                <div>Categoria do Cart&atilde;o</div>
                <div>Status</div>
                <div class="compact-actions">A&ccedil;&otilde;es</div>
            </div>
            ${linhas}
        </div>
    `;
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
        icone: 'credit-card',
        ativo: true
    };
    const vinculos = emCriacao ? [] : obterVinculosAtivos(formCategoria.id);
    const categoriasDisponiveis = emCriacao ? [] : obterCategoriasDespesaDisponiveis();
    const icone = renderizarIconeCartao(formCategoria, '30px');
    const opcoesIcone = montarOpcoesIcone(formCategoria.icone);

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
                        <select id="cartao-icone">${opcoesIcone}</select>
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
        const icon = document.getElementById('cartao-detail-icon');
        const categoria = {
            icone: event.target.value,
            cor: document.getElementById('cartao-cor')?.value || '#2563eb'
        };
        if (icon) icon.innerHTML = renderizarIconeCartao(categoria, '30px');
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

function obterCategoriaCartaoSelecionada() {
    if (!estadoCategorias.categoriaCartaoSelecionadaId) return null;
    return estadoCategorias.categoriasCartao.find((categoria) => categoria.id === estadoCategorias.categoriaCartaoSelecionadaId) || null;
}

function obterCategoriaDespesa(categoriaId) {
    return estadoCategorias.categoriasDespesa.find((categoria) => categoria.id === Number(categoriaId)) || null;
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

function montarOpcoesIcone(iconeAtual) {
    const keys = typeof getIconKeys === 'function' ? getIconKeys() : [];
    const atual = iconeAtual || 'credit-card';
    return [
        `<option value="">Sem icone</option>`,
        ...keys.map((key) => `<option value="${escapeHtml(key)}" ${key === atual ? 'selected' : ''}>${escapeHtml(key)}</option>`)
    ].join('');
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
        await fetchJson(id ? `${API_CATEGORIAS}/${id}` : API_CATEGORIAS, {
            method: id ? 'PUT' : 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        });

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
