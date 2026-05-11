const API_RECEITAS = '/api/receitas';
const API_CONTAS = '/api/contas';

const TIPOS_RECEITA = {
    SALARIO_FIXO: { label: 'Salário Fixo', color: '#2563eb', bg: '#dbeafe' },
    GRATIFICACAO: { label: 'Gratificação', color: '#16a34a', bg: '#dcfce7' },
    RENDA_EXTRA: { label: 'Renda Extra', color: '#7c3aed', bg: '#ede9fe' },
    ALUGUEL: { label: 'Aluguel', color: '#7c3aed', bg: '#ede9fe' },
    RENDIMENTO_FINANCEIRO: { label: 'Rendimento', color: '#14b8a6', bg: '#ccfbf1' },
    OUTROS: { label: 'Outros', color: '#f97316', bg: '#ffedd5' },
    PONTUAL: { label: 'Pontual', color: '#64748b', bg: '#f1f5f9' },
};

const CORES_DONUT = ['#2563eb', '#22c55e', '#7c3aed', '#14b8a6', '#f97316', '#ef4444'];

let estado = {
    anoAtual: new Date().getFullYear(),
    mesAtual: '',
    tipoFiltro: '',
    busca: '',
    fontes: [],
    contasBancarias: [],
    orcamentos: [],
    realizadas: [],
    receitasMes: [],
    receitasFiltradas: [],
    fonteAtual: null,
};

document.addEventListener('DOMContentLoaded', () => {
    inicializarReceitas();
});

function inicializarReceitas() {
    inicializarAno();
    registrarEventosReceitas();
    atualizarDados();
}

function inicializarAno() {
    const selectAno = document.getElementById('filtro-ano');
    if (!selectAno) return;

    const anoAtual = new Date().getFullYear();
    selectAno.innerHTML = '';

    for (let ano = anoAtual - 3; ano <= anoAtual + 2; ano += 1) {
        const option = document.createElement('option');
        option.value = String(ano);
        option.textContent = String(ano);
        option.selected = ano === anoAtual;
        selectAno.appendChild(option);
    }

    estado.anoAtual = anoAtual;
}

function registrarEventosReceitas() {
    ['filtro-ano', 'filtro-mes', 'filtro-tipo'].forEach((id) => {
        const campo = document.getElementById(id);
        if (campo) campo.addEventListener('change', atualizarDados);
    });

    const busca = document.getElementById('receitas-busca');
    if (busca) {
        busca.addEventListener('input', () => {
            estado.busca = busca.value.trim();
            aplicarFiltrosLocais();
        });
    }

    [
        'fonte-nome',
        'fonte-tipo',
        'fonte-descricao',
        'fonte-valor-base',
        'fonte-recorrente',
        'fonte-dia-pagamento',
        'fonte-conta-bancaria',
        'fonte-observacoes',
        'fonte-ativo',
    ].forEach((id) => {
        const campo = document.getElementById(id);
        if (!campo) return;
        const evento = campo.type === 'checkbox' || campo.tagName === 'SELECT' ? 'change' : 'input';
        campo.addEventListener(evento, atualizarPreviewFonte);
    });

    ['fonte-descricao', 'fonte-observacoes'].forEach((id) => {
        const campo = document.getElementById(id);
        if (!campo) return;
        campo.addEventListener('input', () => atualizarContadorCampo(id));
    });

    ['fonte-valor-base', 'real-valor', 'orc-valor'].forEach((id) => {
        const campo = document.getElementById(id);
        if (!campo) return;
        campo.addEventListener('blur', () => {
            const valor = parseMoeda(campo.value);
            campo.value = valor ? formatarNumeroInput(valor) : '';
            atualizarPreviewFonte();
        });
    });

    document.querySelectorAll('.receitas-modal').forEach((modal) => {
        modal.addEventListener('click', (event) => {
            if (event.target === modal) fecharModal(modal.id);
        });
    });
}

async function atualizarDados() {
    const ano = document.getElementById('filtro-ano')?.value;
    const mes = document.getElementById('filtro-mes')?.value;
    const tipo = document.getElementById('filtro-tipo')?.value;
    const busca = document.getElementById('receitas-busca')?.value;

    estado.anoAtual = parseInt(ano || new Date().getFullYear(), 10);
    estado.mesAtual = mes || '';
    estado.tipoFiltro = tipo || '';
    estado.busca = (busca || '').trim();

    renderizarCarregando();

    try {
        await Promise.all([carregarContasBancarias(), carregarFontesReceita()]);
        await carregarReceitasMes();
    } catch (error) {
        console.error('Erro ao atualizar receitas:', error);
        mostrarToast('Não foi possível carregar as receitas.', 'error');
        renderizarErroLista();
    }
}

function renderizarCarregando() {
    const lista = document.getElementById('mes-lista');
    if (lista) lista.innerHTML = '<div class="receitas-loading">Carregando receitas e pendências...</div>';

    const fontes = document.getElementById('fontes-resumo');
    if (fontes) fontes.innerHTML = '<div class="receitas-loading small">Carregando fontes...</div>';

    const proximos = document.getElementById('proximos-recebimentos');
    if (proximos) proximos.innerHTML = '<div class="receitas-loading small">Carregando recebimentos pendentes...</div>';
}

async function carregarContasBancarias() {
    const response = await fetch(`${API_CONTAS}?status=ATIVO`);
    const result = await response.json();

    if (!result.success) throw new Error(result.error || 'Erro ao carregar contas bancárias');

    estado.contasBancarias = result.data || [];
    atualizarSelectsContasBancarias();
}

async function carregarFontesReceita() {
    const response = await fetch(`${API_RECEITAS}/itens`);
    const result = await response.json();

    if (!result.success) throw new Error(result.error || 'Erro ao carregar fontes de receita');

    estado.fontes = result.data || [];
    atualizarSelectsFontes();
}

async function carregarReceitasMes() {
    const anoMes = getAnoMesSelecionado();
    const inicioPendencias = `${estado.anoAtual}-01-01`;

    const [orcamentosResponse, realizadasResponse] = await Promise.all([
        fetch(`${API_RECEITAS}/orcamento?ano=${estado.anoAtual}`),
        fetch(`${API_RECEITAS}/realizadas?ano_mes_inicio=${inicioPendencias}&ano_mes_fim=${anoMes}`),
    ]);

    const [orcamentosResult, realizadasResult] = await Promise.all([
        orcamentosResponse.json(),
        realizadasResponse.json(),
    ]);

    if (!orcamentosResult.success) throw new Error(orcamentosResult.error || 'Erro ao carregar previsões');
    if (!realizadasResult.success) throw new Error(realizadasResult.error || 'Erro ao carregar receitas realizadas');

    estado.orcamentos = orcamentosResult.data || [];
    estado.realizadas = realizadasResult.data || [];
    estado.receitasMes = montarReceitasMes(estado.orcamentos, estado.realizadas, anoMes);

    aplicarFiltrosLocais();
}

function montarReceitasMes(orcamentos, realizadas, anoMes) {
    const realizadasEfetivas = (realizadas || []).filter((receita) => !receitaPendenteConfirmacao(receita));
    const realizadasPendentes = (realizadas || []).filter(receitaPendenteConfirmacao);
    const realizadasSelecionadas = realizadasEfetivas.filter((receita) => normalizarDataMes(receita.competencia || receita.mes_referencia) === anoMes);
    const realizadasPorFonteCompetencia = new Map();

    realizadasEfetivas.forEach((receita) => {
        if (!receita.item_receita_id) return;
        const competencia = normalizarDataMes(receita.competencia || receita.mes_referencia);
        const chave = chaveReceita(receita.item_receita_id, competencia);
        if (!realizadasPorFonteCompetencia.has(chave)) realizadasPorFonteCompetencia.set(chave, []);
        realizadasPorFonteCompetencia.get(chave).push(receita);
    });

    const idsPlanejadosNoMesSelecionado = new Set();
    const chavesPlanejadas = new Set();
    const lista = [];

    (orcamentos || [])
        .filter((orcamento) => normalizarDataMes(orcamento.ano_mes || orcamento.mes_referencia) <= anoMes)
        .forEach((orcamento) => {
        const itemId = orcamento.item_receita_id;
        const competencia = normalizarDataMes(orcamento.ano_mes || orcamento.mes_referencia);
        const chave = chaveReceita(itemId, competencia);

        const fonte = buscarFonte(itemId);
        const realizadasFonte = realizadasPorFonteCompetencia.get(chave) || [];
        const valorPrevisto = Number(orcamento.valor_previsto ?? orcamento.valor_esperado ?? 0);
        const valorRealizado = soma(realizadasFonte, 'valor_recebido');
        const status = obterStatusReceita(valorPrevisto, valorRealizado);

        if (competencia === anoMes) idsPlanejadosNoMesSelecionado.add(itemId);
        if (competencia !== anoMes && status === 'REALIZADA') return;

        chavesPlanejadas.add(chave);
        lista.push({
            uid: `orc-${orcamento.id || itemId}`,
            origem: 'orcamento',
            orcamento_id: orcamento.id,
            item_receita_id: itemId,
            fonte,
            nome: fonte?.nome || orcamento.item_receita?.nome || 'Receita',
            descricao: fonte?.descricao || orcamento.observacoes || '',
            competencia,
            tipo: fonte?.tipo || orcamento.item_receita?.tipo || 'OUTROS',
            status,
            conta: obterContaLinha(fonte, realizadasFonte[0]),
            valor_previsto: valorPrevisto,
            valor_realizado: valorRealizado,
            diferenca: valorRealizado - valorPrevisto,
            realizada_id: realizadasFonte.length === 1 ? realizadasFonte[0].id : null,
            realizadas_count: realizadasFonte.length,
            dia_previsto_pagamento: fonte?.dia_previsto_pagamento || null,
        });
    });

    realizadasPendentes
        .filter((receita) => normalizarDataMes(receita.competencia || receita.mes_referencia) <= anoMes)
        .filter((receita) => {
            const competencia = normalizarDataMes(receita.competencia || receita.mes_referencia);
            return !receita.item_receita_id || !chavesPlanejadas.has(chaveReceita(receita.item_receita_id, competencia));
        })
        .forEach((receita) => {
            lista.push(montarLinhaReceitaPendenteConfirmacao(receita, buscarFonte(receita.item_receita_id), anoMes));
        });

    const realizadasSelecionadasPorFonte = new Map();
    realizadasSelecionadas.forEach((receita) => {
        if (!receita.item_receita_id) return;
        if (!realizadasSelecionadasPorFonte.has(receita.item_receita_id)) realizadasSelecionadasPorFonte.set(receita.item_receita_id, []);
        realizadasSelecionadasPorFonte.get(receita.item_receita_id).push(receita);
    });

    (estado.fontes || [])
        .filter((fonte) => fonte.ativo && fonte.recorrente && !idsPlanejadosNoMesSelecionado.has(fonte.id))
        .filter((fonte) => Number(fonte.valor_base_mensal || 0) > 0 || realizadasSelecionadasPorFonte.has(fonte.id))
        .forEach((fonte) => {
            const realizadasFonte = realizadasSelecionadasPorFonte.get(fonte.id) || [];
            const valorPrevisto = Number(fonte.valor_base_mensal || 0);
            const valorRealizado = soma(realizadasFonte, 'valor_recebido');
            const status = obterStatusReceita(valorPrevisto, valorRealizado);

            lista.push({
                uid: `fonte-${fonte.id}`,
                origem: 'fonte_base',
                item_receita_id: fonte.id,
                fonte,
                nome: fonte.nome,
                descricao: fonte.descricao || '',
                competencia: anoMes,
                tipo: fonte.tipo || 'OUTROS',
                status,
                conta: obterContaLinha(fonte, realizadasFonte[0]),
                valor_previsto: valorPrevisto,
                valor_realizado: valorRealizado,
                diferenca: valorRealizado - valorPrevisto,
                realizada_id: realizadasFonte.length === 1 ? realizadasFonte[0].id : null,
                realizadas_count: realizadasFonte.length,
                dia_previsto_pagamento: fonte.dia_previsto_pagamento || null,
            });
        });

    realizadasSelecionadas
        .filter((receita) => receita.item_receita_id && !idsPlanejadosNoMesSelecionado.has(receita.item_receita_id))
        .filter((receita) => !(buscarFonte(receita.item_receita_id)?.recorrente))
        .forEach((receita) => {
            const fonte = buscarFonte(receita.item_receita_id);
            lista.push(montarLinhaRealizadaPontual(receita, fonte, anoMes));
        });

    realizadasSelecionadas.filter((receita) => !receita.item_receita_id).forEach((receita) => {
        lista.push(montarLinhaRealizadaPontual(receita, null, anoMes));
    });

    return lista.sort((a, b) => {
        const statusOrder = { PREVISTA: 0, PARCIAL: 1, REALIZADA: 2, CANCELADA: 3 };
        return (statusOrder[a.status] ?? 9) - (statusOrder[b.status] ?? 9)
            || a.competencia.localeCompare(b.competencia)
            || a.nome.localeCompare(b.nome);
    });
}

function montarLinhaReceitaPendenteConfirmacao(receita, fonte, anoMes) {
    const valorPrevisto = Number(receita.valor_recebido || 0);
    const competencia = normalizarDataMes(receita.competencia || receita.mes_referencia) || anoMes;
    return {
        uid: `pend-real-${receita.id}`,
        origem: 'realizada_pendente',
        id: receita.id,
        item_receita_id: receita.item_receita_id,
        fonte,
        nome: receita.descricao || fonte?.nome || 'Receita prevista',
        descricao: fonte?.descricao || receita.observacoes || '',
        competencia,
        tipo: fonte?.tipo || receita.item_receita?.tipo || 'OUTROS',
        status: 'PREVISTA',
        conta: obterContaLinha(fonte, null),
        valor_previsto: valorPrevisto,
        valor_realizado: 0,
        diferenca: -valorPrevisto,
        realizada_id: receita.id,
        realizadas_count: 0,
        dia_previsto_pagamento: Number(String(receita.data_recebimento || '').slice(8, 10)) || fonte?.dia_previsto_pagamento || null,
    };
}

function montarLinhaRealizadaPontual(receita, fonte, anoMes) {
    const valorRealizado = Number(receita.valor_recebido || 0);
    return {
        uid: `real-${receita.id}`,
        origem: 'realizada',
        id: receita.id,
        item_receita_id: receita.item_receita_id,
        fonte,
        nome: receita.descricao || fonte?.nome || 'Receita pontual',
        descricao: fonte?.descricao || receita.observacoes || '',
        competencia: normalizarDataMes(receita.competencia || receita.mes_referencia) || anoMes,
        tipo: fonte?.tipo || receita.item_receita?.tipo || 'PONTUAL',
        status: 'REALIZADA',
        conta: obterContaLinha(fonte, receita),
        valor_previsto: 0,
        valor_realizado: valorRealizado,
        diferenca: valorRealizado,
        realizada_id: receita.id,
        realizadas_count: 1,
        dia_previsto_pagamento: null,
    };
}

function aplicarFiltrosLocais() {
    const termo = normalizarTexto(estado.busca);
    const tipoFiltro = estado.tipoFiltro;

    estado.receitasFiltradas = (estado.receitasMes || []).filter((receita) => {
        const tipoOk = !tipoFiltro || receita.tipo === tipoFiltro;
        const texto = normalizarTexto([
            receita.nome,
            receita.descricao,
            formatarTipo(receita.tipo),
            receita.conta?.nome,
            receita.conta?.instituicao,
        ].filter(Boolean).join(' '));

        return tipoOk && (!termo || texto.includes(termo));
    });

    renderizarReceitasMes();
    renderizarKpis();
    renderizarFontesResumo();
    renderizarProximosRecebimentos();
}

function renderizarReceitasMes() {
    const container = document.getElementById('mes-lista');
    const footer = document.getElementById('receitas-total-encontradas');
    if (!container) return;

    const receitas = estado.receitasFiltradas || [];

    if (footer) {
        footer.textContent = `${receitas.length} ${receitas.length === 1 ? 'receita encontrada' : 'receitas encontradas'}`;
    }

    if (!receitas.length) {
        container.innerHTML = `
            <div class="receitas-empty-state">
                <h3>Nenhuma receita encontrada para o período.</h3>
                <p>Cadastre uma fonte de receita para iniciar a previsão.</p>
            </div>
        `;
        return;
    }

    container.innerHTML = receitas.map((receita) => {
        const tipoInfo = getTipoInfo(receita.tipo);
        const contaTexto = receita.conta
            ? `<strong>${escapeHtml(receita.conta.nome)}</strong><small>${escapeHtml(formatarAgenciaConta(receita.conta))}</small>`
            : '<strong>Sem conta padrão</strong><small>Defina na fonte ou ao realizar</small>';

        return `
            <article class="receita-row" data-receita="${escapeHtml(receita.uid)}">
                <div class="receita-source">
                    <strong>${escapeHtml(receita.nome)}</strong>
                    <small>${escapeHtml(receita.descricao || 'Fonte de receita')}</small>
                </div>
                <div class="receita-meta">
                    <strong>${escapeHtml(formatarCompetencia(receita.competencia))}</strong>
                    <small>${escapeHtml(nomeMes(receita.competencia))}</small>
                </div>
                <div>
                    <span class="receita-type-badge" style="--tipo-color:${tipoInfo.color};--tipo-bg:${tipoInfo.bg}">
                        ${escapeHtml(tipoInfo.label)}
                    </span>
                </div>
                <div>
                    <span class="receita-status-badge ${statusClasse(receita.status)}">${escapeHtml(formatarStatus(receita.status))}</span>
                </div>
                <div class="receita-account">${contaTexto}</div>
                <div class="receita-value">${formatarMoeda(receita.valor_previsto)}</div>
                <div class="receita-value green">${formatarMoeda(receita.valor_realizado)}</div>
                <div class="receita-value ${receita.diferenca < 0 ? 'red' : 'green'}">${formatarMoeda(receita.diferenca)}</div>
                <div class="receita-actions">
                    <button type="button" class="receitas-action-btn" onclick="visualizarReceita('${escapeAttribute(receita.uid)}')" title="Visualizar" aria-label="Visualizar">${iconReceitas('eye')}</button>
                    <button type="button" class="receitas-action-btn" onclick="editarReceitaLinha('${escapeAttribute(receita.uid)}')" title="Editar" aria-label="Editar">${iconReceitas('edit')}</button>
                    <button type="button" class="receitas-action-btn success" onclick="realizarReceitaLinha('${escapeAttribute(receita.uid)}')" title="Confirmar/realizar" aria-label="Confirmar/realizar" ${receita.status === 'REALIZADA' ? 'disabled' : ''}>${iconReceitas('check')}</button>
                    <button type="button" class="receitas-action-btn danger" onclick="cancelarReceitaLinha('${escapeAttribute(receita.uid)}')" title="Cancelar/ignorar" aria-label="Cancelar/ignorar">${iconReceitas('x')}</button>
                    <button type="button" class="receitas-action-btn" onclick="mostrarToast('Mais ações serão detalhadas em evolução futura.', 'info')" title="Mais ações" aria-label="Mais ações">${iconReceitas('more')}</button>
                </div>
            </article>
        `;
    }).join('');
}

function renderizarKpis() {
    const receitas = estado.receitasFiltradas || [];
    const previsto = soma(receitas, 'valor_previsto');
    const realizado = soma(receitas, 'valor_realizado');
    const diferenca = realizado - previsto;
    const confiabilidade = previsto > 0 ? (realizado / previsto) * 100 : 0;

    setText('total-previsto', formatarMoeda(previsto));
    setText('total-realizado', formatarMoeda(realizado));
    setText('diferenca', formatarMoeda(diferenca));
    setText('confiabilidade', `${formatarPercentual(confiabilidade)}`);

    setText('previsto-indicador', `${receitas.length} ${receitas.length === 1 ? 'receita no período' : 'receitas no período'}`);
    setText('realizado-indicador', `${formatarPercentual(confiabilidade)} realizado`);
    setText('diferenca-indicador', diferenca >= 0 ? 'Realizado acima do previsto' : 'Abaixo do previsto');
    setText('confiabilidade-indicador', 'Meta: ≥ 80%');

    const diferencaEl = document.getElementById('diferenca');
    if (diferencaEl) diferencaEl.classList.toggle('negative', diferenca < 0);
}

function renderizarFontesResumo() {
    const container = document.getElementById('fontes-resumo');
    if (!container) return;

    const fontesAtivas = (estado.fontes || []).filter((fonte) => fonte.ativo);
    if (!fontesAtivas.length) {
        container.innerHTML = `
            <div class="receitas-empty-state small">
                <h3>Sem fontes cadastradas</h3>
                <p>Cadastre uma fonte para acompanhar previsões.</p>
            </div>
        `;
        return;
    }

    const grupos = Array.from(fontesAtivas.reduce((mapa, fonte) => {
        const tipo = fonte.tipo || 'OUTROS';
        const item = mapa.get(tipo) || { tipo, total: 0, count: 0 };
        item.total += Number(fonte.valor_base_mensal || 0);
        item.count += 1;
        mapa.set(tipo, item);
        return mapa;
    }, new Map()).values()).sort((a, b) => b.count - a.count);

    const totalFontes = fontesAtivas.length || 1;
    let cursor = 0;
    const stops = grupos.map((grupo, index) => {
        const percent = (grupo.count / totalFontes) * 100;
        const inicio = cursor;
        cursor += percent;
        return `${CORES_DONUT[index % CORES_DONUT.length]} ${inicio}% ${cursor}%`;
    }).join(', ');

    container.innerHTML = `
        <div class="receitas-fontes-layout">
            <div class="receitas-donut" style="--donut-stops:${escapeAttribute(stops)}">
                <div class="receitas-donut-center">
                    <strong>${fontesAtivas.length}</strong>
                    <span>Fontes</span>
                </div>
            </div>
            <div class="receitas-fontes-list">
                ${grupos.map((grupo, index) => {
                    const tipoInfo = getTipoInfo(grupo.tipo);
                    const percent = Math.round((grupo.count / totalFontes) * 100);
                    const cor = CORES_DONUT[index % CORES_DONUT.length];
                    return `
                        <div class="receitas-fonte-item">
                            <div class="receitas-fonte-line">
                                <span class="receitas-fonte-name"><i class="receitas-color-dot" style="--item-color:${cor}"></i>${escapeHtml(tipoInfo.label)}</span>
                                <strong class="receitas-fonte-percent">${percent}%</strong>
                            </div>
                            <div class="receitas-fonte-bar"><div style="--bar-value:${percent}%;--item-color:${cor}"></div></div>
                        </div>
                    `;
                }).join('')}
            </div>
        </div>
    `;
}

function renderizarProximosRecebimentos() {
    const container = document.getElementById('proximos-recebimentos');
    if (!container) return;

    const anoMes = getAnoMesSelecionado();
    const proximos = (estado.receitasMes || [])
        .filter((receita) => ['PREVISTA', 'PARCIAL'].includes(receita.status))
        .map((receita) => ({
            ...receita,
            dataPrevista: montarDataPrevista(receita.competencia || anoMes, receita.dia_previsto_pagamento),
        }))
        .sort((a, b) => a.dataPrevista.localeCompare(b.dataPrevista))
        .slice(0, 4);

    if (!proximos.length) {
        container.innerHTML = `
            <div class="receitas-empty-state small">
                <h3>Nenhum recebimento pendente.</h3>
                <p>As previsões aparecerão quando houver fontes ativas.</p>
            </div>
        `;
        return;
    }

    container.innerHTML = proximos.map((receita) => `
        <div class="receitas-proximo-item">
            <div class="receitas-proximo-line">
                <strong>${escapeHtml(receita.nome)}</strong>
                <span class="receitas-proximo-value">${formatarMoeda(receita.valor_previsto - receita.valor_realizado)}</span>
            </div>
            <small>Vencimento: ${escapeHtml(formatarDataBR(receita.dataPrevista))}</small>
            <span class="receita-status-badge ${statusClasse(receita.status)}">${escapeHtml(formatarStatus(receita.status))}</span>
        </div>
    `).join('');
}

function visualizarReceita(uid) {
    const receita = buscarReceitaLinha(uid);
    if (!receita) return;

    setText('detalhe-receita-titulo', receita.nome);
    setText('detalhe-receita-subtitulo', `${formatarTipo(receita.tipo)} · ${formatarCompetencia(receita.competencia)}`);

    const conteudo = document.getElementById('detalhe-receita-conteudo');
    if (conteudo) {
        conteudo.innerHTML = `
            <div class="receitas-detail-grid">
                <div class="receitas-detail-item"><span>Status</span><strong>${escapeHtml(formatarStatus(receita.status))}</strong></div>
                <div class="receitas-detail-item"><span>Conta bancária</span><strong>${escapeHtml(receita.conta?.nome || 'Sem conta padrão')}</strong></div>
                <div class="receitas-detail-item"><span>Valor previsto</span><strong>${formatarMoeda(receita.valor_previsto)}</strong></div>
                <div class="receitas-detail-item"><span>Valor realizado</span><strong>${formatarMoeda(receita.valor_realizado)}</strong></div>
                <div class="receitas-detail-item"><span>Diferença</span><strong>${formatarMoeda(receita.diferenca)}</strong></div>
                <div class="receitas-detail-item"><span>Descrição</span><strong>${escapeHtml(receita.descricao || 'Sem descrição')}</strong></div>
            </div>
        `;
    }

    abrirModal('modal-detalhe-receita');
}

function editarReceitaLinha(uid) {
    const receita = buscarReceitaLinha(uid);
    if (!receita) return;

    if (receita.item_receita_id) {
        abrirModalFonte(receita.item_receita_id);
        return;
    }

    if (receita.realizada_id) {
        editarRealizada(receita.realizada_id);
    }
}

function realizarReceitaLinha(uid) {
    const receita = buscarReceitaLinha(uid);
    if (!receita || receita.status === 'REALIZADA') return;

    if (receita.item_receita_id || receita.realizada_id) {
        consolidarReceitaMes(receita.item_receita_id, Math.max(receita.valor_previsto - receita.valor_realizado, 0), uid);
    }
}

function cancelarReceitaLinha(uid) {
    const receita = buscarReceitaLinha(uid);
    if (!receita) return;

    if (receita.status === 'REALIZADA' && receita.realizada_id) {
        deletarRealizada(receita.realizada_id);
        return;
    }

    if (receita.item_receita_id) {
        excluirReceitaPrevista(receita.item_receita_id, receita.origem, receita.competencia, receita.realizada_id);
    }
}

function abrirModalFonte(id = null) {
    const form = document.getElementById('form-fonte');
    if (!form) return;

    form.reset();
    estado.fonteAtual = null;
    setValue('fonte-id', '');
    setValue('fonte-descricao', '');
    setValue('fonte-observacoes', '');
    setChecked('fonte-recorrente', true);
    setChecked('fonte-ativo', true);
    setText('modal-fonte-titulo', 'Nova Fonte de Receita');
    setText('modal-fonte-subtitulo', 'Crie uma nova fonte de receita para organizar e prever seus recebimentos.');

    const btnInativar = document.getElementById('btn-inativar-fonte');
    if (btnInativar) btnInativar.style.display = 'none';

    if (id) {
        const fonte = buscarFonte(Number(id));
        if (fonte) {
            estado.fonteAtual = fonte;
            setValue('fonte-id', fonte.id);
            setValue('fonte-nome', fonte.nome);
            setValue('fonte-tipo', fonte.tipo);
            setValue('fonte-descricao', fonte.descricao || '');
            setValue('fonte-valor-base', formatarNumeroInput(Number(fonte.valor_base_mensal || 0)));
            setChecked('fonte-recorrente', !!fonte.recorrente);
            setValue('fonte-dia-pagamento', fonte.dia_previsto_pagamento || '');
            setValue('fonte-conta-bancaria', fonte.conta_bancaria_id || '');
            setChecked('fonte-ativo', !!fonte.ativo);
            setText('modal-fonte-titulo', 'Editar Fonte de Receita');
            setText('modal-fonte-subtitulo', 'Atualize os dados da fonte sem alterar regras financeiras.');
            if (btnInativar) btnInativar.style.display = 'inline-flex';
        }
    }

    atualizarContadorCampo('fonte-descricao');
    atualizarContadorCampo('fonte-observacoes');
    atualizarPreviewFonte();
    abrirModal('modal-fonte');
}

async function salvarFonte(event) {
    event.preventDefault();

    const id = document.getElementById('fonte-id')?.value;
    const recorrente = document.getElementById('fonte-recorrente')?.checked ?? true;
    const contaId = document.getElementById('fonte-conta-bancaria')?.value;

    const dados = {
        nome: document.getElementById('fonte-nome')?.value.trim(),
        tipo: document.getElementById('fonte-tipo')?.value,
        descricao: document.getElementById('fonte-descricao')?.value.trim() || '',
        valor_base_mensal: parseMoeda(document.getElementById('fonte-valor-base')?.value),
        dia_previsto_pagamento: recorrente ? parseInt(document.getElementById('fonte-dia-pagamento')?.value || '0', 10) || null : null,
        conta_bancaria_id: contaId ? parseInt(contaId, 10) : null,
        recorrente,
        ativo: document.getElementById('fonte-ativo')?.checked ?? true,
    };

    if (!dados.nome || !dados.tipo) {
        mostrarToast('Informe nome e tipo da fonte.', 'error');
        return;
    }

    try {
        const response = await fetch(id ? `${API_RECEITAS}/itens/${id}` : `${API_RECEITAS}/itens`, {
            method: id ? 'PUT' : 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados),
        });

        const result = await response.json();
        if (!result.success) {
            mostrarToast(result.error || 'Erro ao salvar fonte.', 'error');
            return;
        }

        fecharModal('modal-fonte');
        mostrarToast(result.message || 'Fonte salva com sucesso.', 'success');
        await atualizarDados();
    } catch (error) {
        console.error('Erro ao salvar fonte:', error);
        mostrarToast('Erro ao salvar fonte de receita.', 'error');
    }
}

async function inativarFonteAtual() {
    const id = document.getElementById('fonte-id')?.value;
    if (!id || !confirm('Inativar esta fonte de receita?')) return;

    try {
        const response = await fetch(`${API_RECEITAS}/itens/${id}`, { method: 'DELETE' });
        const result = await response.json();

        if (!result.success) {
            mostrarToast(result.error || 'Erro ao inativar fonte.', 'error');
            return;
        }

        fecharModal('modal-fonte');
        mostrarToast(result.message || 'Fonte inativada com sucesso.', 'success');
        await atualizarDados();
    } catch (error) {
        console.error('Erro ao inativar fonte:', error);
        mostrarToast('Erro ao inativar fonte de receita.', 'error');
    }
}

function atualizarPreviewFonte() {
    const nome = document.getElementById('fonte-nome')?.value.trim() || 'Nome da Fonte';
    const tipo = document.getElementById('fonte-tipo')?.value || '';
    const valor = parseMoeda(document.getElementById('fonte-valor-base')?.value);
    const recorrente = document.getElementById('fonte-recorrente')?.checked ?? true;
    const dia = document.getElementById('fonte-dia-pagamento')?.value;
    const contaId = document.getElementById('fonte-conta-bancaria')?.value;
    const ativo = document.getElementById('fonte-ativo')?.checked ?? true;
    const tipoInfo = getTipoInfo(tipo);
    const conta = estado.contasBancarias.find((item) => String(item.id) === String(contaId));

    setText('preview-fonte-nome', nome);
    setText('preview-fonte-tipo', tipo ? tipoInfo.label.toUpperCase() : 'TIPO');
    setText('preview-fonte-valor', formatarMoeda(valor));
    setText('preview-fonte-recorrencia', recorrente ? 'Mensal' : 'Não recorrente');
    setText('preview-fonte-dia', recorrente && dia ? `Dia ${dia}` : '—');
    setText('preview-fonte-conta', conta ? conta.nome : '—');
    setText('preview-fonte-status', ativo ? 'Ativa' : 'Inativa');

    const badgeTipo = document.getElementById('preview-fonte-tipo');
    if (badgeTipo) {
        badgeTipo.style.setProperty('--tipo-color', tipoInfo.color);
        badgeTipo.style.setProperty('--tipo-bg', tipoInfo.bg);
    }

    const status = document.getElementById('preview-fonte-status');
    if (status) {
        status.classList.toggle('active', ativo);
        status.classList.toggle('inactive', !ativo);
    }

    const diaCampo = document.getElementById('fonte-dia-pagamento');
    if (diaCampo) diaCampo.disabled = !recorrente;
}

function abrirModalOrcamento() {
    setValue('orc-ano-mes', getAnoMesSelecionado().slice(0, 7));
    abrirModal('modal-orcamento');
}

async function salvarOrcamento(event) {
    event.preventDefault();

    const dados = {
        item_receita_id: parseInt(document.getElementById('orc-fonte')?.value || '0', 10),
        ano_mes: `${document.getElementById('orc-ano-mes')?.value}-01`,
        valor_previsto: parseMoeda(document.getElementById('orc-valor')?.value),
        periodicidade: document.getElementById('orc-periodicidade')?.value || 'MENSAL_FIXA',
        observacoes: document.getElementById('orc-observacoes')?.value || '',
    };

    if (!dados.item_receita_id || !dados.ano_mes || dados.valor_previsto < 0) {
        mostrarToast('Preencha os dados da previsão.', 'error');
        return;
    }

    try {
        const response = await fetch(`${API_RECEITAS}/orcamento`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados),
        });
        const result = await response.json();

        if (!result.success) {
            mostrarToast(result.error || 'Erro ao salvar previsão.', 'error');
            return;
        }

        fecharModal('modal-orcamento');
        mostrarToast(result.message || 'Previsão salva.', 'success');
        await atualizarDados();
    } catch (error) {
        console.error('Erro ao salvar previsão:', error);
        mostrarToast('Erro ao salvar previsão.', 'error');
    }
}

function editarRealizada(id) {
    const receita = estado.realizadas.find((item) => item.id === Number(id));
    if (!receita) {
        mostrarToast('Receita realizada não encontrada.', 'error');
        return;
    }

    setValue('realizada-id', receita.id);
    setText('modal-realizada-titulo', 'Editar Recebimento');
    setValue('real-fonte', receita.item_receita_id || '');
    setValue('real-data-recebimento', normalizarDataDia(receita.data_recebimento));
    setValue('real-valor', formatarNumeroInput(Number(receita.valor_recebido || 0)));
    setValue('real-competencia', normalizarDataMes(receita.competencia || receita.mes_referencia).slice(0, 7));
    setValue('real-conta-bancaria', receita.conta_bancaria_id || '');
    setValue('real-descricao', receita.descricao || '');
    setValue('real-observacoes', receita.observacoes || '');

    abrirModal('modal-realizada');
}

async function salvarRealizada(event) {
    event.preventDefault();

    const id = document.getElementById('realizada-id')?.value;
    const contaId = document.getElementById('real-conta-bancaria')?.value;
    const dados = {
        item_receita_id: parseInt(document.getElementById('real-fonte')?.value || '0', 10),
        data_recebimento: document.getElementById('real-data-recebimento')?.value,
        valor_recebido: parseMoeda(document.getElementById('real-valor')?.value),
        competencia: `${document.getElementById('real-competencia')?.value}-01`,
        conta_bancaria_id: contaId ? parseInt(contaId, 10) : null,
        descricao: document.getElementById('real-descricao')?.value.trim() || '',
        observacoes: document.getElementById('real-observacoes')?.value.trim() || '',
    };

    if (!dados.item_receita_id || !dados.data_recebimento || !dados.valor_recebido) {
        mostrarToast('Preencha fonte, data e valor recebido.', 'error');
        return;
    }

    try {
        const response = await fetch(id ? `${API_RECEITAS}/realizadas/${id}` : `${API_RECEITAS}/realizadas`, {
            method: id ? 'PUT' : 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados),
        });

        const result = await response.json();
        if (!result.success) {
            mostrarToast(result.error || 'Erro ao salvar recebimento.', 'error');
            return;
        }

        fecharModal('modal-realizada');
        mostrarToast(result.message || 'Recebimento salvo.', 'success');
        await atualizarDados();
    } catch (error) {
        console.error('Erro ao salvar recebimento:', error);
        mostrarToast('Erro ao salvar recebimento.', 'error');
    }
}

async function deletarRealizada(id) {
    if (!confirm('Remover esta receita realizada?')) return;

    try {
        const response = await fetch(`${API_RECEITAS}/realizadas/${id}`, { method: 'DELETE' });
        const result = await response.json();

        if (!result.success) {
            mostrarToast(result.error || 'Erro ao remover receita.', 'error');
            return;
        }

        mostrarToast(result.message || 'Receita removida.', 'success');
        await atualizarDados();
    } catch (error) {
        console.error('Erro ao remover receita realizada:', error);
        mostrarToast('Erro ao remover receita.', 'error');
    }
}

function consolidarReceitaMes(itemReceitaId, valorPrevisto, uid = null) {
    const fonte = buscarFonte(Number(itemReceitaId));
    const linha = uid ? buscarReceitaLinha(uid) : null;

    setValue('consolidar-item-receita-id', itemReceitaId);
    setValue('consolidar-valor-previsto', valorPrevisto);
    setValue('consolidar-receita-uid', uid || '');
    setValue('consolidar-realizada-id', linha?.origem === 'realizada_pendente' ? linha.realizada_id : '');
    setValue('consolidar-competencia', linha?.competencia || getAnoMesSelecionado());
    atualizarSelectsContasBancarias();
    setValue('consolidar-conta-bancaria', fonte?.conta_bancaria_id || linha?.conta?.id || '');

    abrirModal('modal-consolidar-conta');
}

async function confirmarConsolidacaoComConta(event) {
    event.preventDefault();

    const itemReceitaId = parseInt(document.getElementById('consolidar-item-receita-id')?.value || '0', 10);
    const valorPrevisto = parseMoeda(document.getElementById('consolidar-valor-previsto')?.value);
    const contaId = document.getElementById('consolidar-conta-bancaria')?.value;
    const realizadaId = document.getElementById('consolidar-realizada-id')?.value;
    const uid = document.getElementById('consolidar-receita-uid')?.value;
    const competencia = document.getElementById('consolidar-competencia')?.value || getAnoMesSelecionado();
    const linha = uid ? buscarReceitaLinha(uid) : null;
    const fonte = buscarFonte(itemReceitaId);
    const hoje = new Date().toISOString().slice(0, 10);

    if ((!itemReceitaId && !realizadaId) || !contaId || !valorPrevisto) {
        mostrarToast('Selecione a conta bancária para consolidar.', 'error');
        return;
    }

    try {
        const payload = {
            item_receita_id: itemReceitaId || undefined,
            data_recebimento: hoje,
            valor_recebido: valorPrevisto,
            competencia,
            conta_bancaria_id: parseInt(contaId, 10),
            descricao: linha?.nome || fonte?.nome || 'Receita',
        };
        if (!realizadaId) {
            payload.observacoes = 'Consolidado pelo gerenciamento de receitas';
        }
        const response = await fetch(realizadaId ? `${API_RECEITAS}/realizadas/${realizadaId}` : `${API_RECEITAS}/realizadas`, {
            method: realizadaId ? 'PUT' : 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });

        const result = await response.json();
        if (!result.success) {
            mostrarToast(result.error || 'Erro ao consolidar receita.', 'error');
            return;
        }

        fecharModal('modal-consolidar-conta');
        mostrarToast(result.message || 'Receita consolidada.', 'success');
        await atualizarDados();
    } catch (error) {
        console.error('Erro ao consolidar receita:', error);
        mostrarToast('Erro ao consolidar receita.', 'error');
    }
}

function editarReceitaPrevista(itemReceitaId, origem, valorPrevisto, competencia = null) {
    if (origem === 'orcamento') {
        setValue('orc-fonte', itemReceitaId);
        setValue('orc-ano-mes', (competencia || getAnoMesSelecionado()).slice(0, 7));
        setValue('orc-valor', formatarNumeroInput(Number(valorPrevisto || 0)));
        setValue('orc-periodicidade', 'MENSAL_FIXA');
        abrirModal('modal-orcamento');
        return;
    }

    abrirModalFonte(itemReceitaId);
}

async function excluirReceitaPrevista(itemReceitaId, origem, competencia = null, realizadaId = null) {
    const fonte = buscarFonte(Number(itemReceitaId));

    if (origem === 'orcamento') {
        if (!confirm('Remover a previsão desta receita na competência selecionada?')) return;

        await salvarPrevisaoZerada(itemReceitaId, 'Removido pelo usuário', competencia);
        return;
    }

    if (origem === 'realizada_pendente' && realizadaId) {
        if (!confirm('Remover esta receita prevista pendente de confirmação?')) return;
        await deletarRealizada(realizadaId);
        return;
    }

    if (!fonte || !confirm('Inativar a previsão recorrente desta fonte?')) return;
    abrirModalFonte(itemReceitaId);
}

async function salvarPrevisaoZerada(itemReceitaId, observacoes, competencia = null) {
    try {
        const response = await fetch(`${API_RECEITAS}/orcamento`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                item_receita_id: itemReceitaId,
                ano_mes: competencia || getAnoMesSelecionado(),
                valor_previsto: 0,
                periodicidade: 'MENSAL_FIXA',
                observacoes,
            }),
        });

        const result = await response.json();
        if (!result.success) {
            mostrarToast(result.error || 'Erro ao remover previsão.', 'error');
            return;
        }

        mostrarToast('Previsão removida.', 'success');
        await atualizarDados();
    } catch (error) {
        console.error('Erro ao remover previsão:', error);
        mostrarToast('Erro ao remover previsão.', 'error');
    }
}

function atualizarSelectsFontes() {
    ['orc-fonte', 'real-fonte'].forEach((id) => {
        const select = document.getElementById(id);
        if (!select) return;

        const atual = select.value;
        select.innerHTML = '<option value="">Selecione...</option>';
        (estado.fontes || []).filter((fonte) => fonte.ativo).forEach((fonte) => {
            const option = document.createElement('option');
            option.value = fonte.id;
            option.textContent = `${fonte.nome} (${formatarTipo(fonte.tipo)})`;
            select.appendChild(option);
        });
        if (atual) select.value = atual;
    });
}

function atualizarSelectsContasBancarias() {
    ['fonte-conta-bancaria', 'real-conta-bancaria', 'consolidar-conta-bancaria'].forEach((id) => {
        const select = document.getElementById(id);
        if (!select) return;

        const atual = select.value;
        select.innerHTML = '<option value="">Selecione...</option>';

        (estado.contasBancarias || []).forEach((conta) => {
            const option = document.createElement('option');
            option.value = conta.id;
            option.textContent = `${conta.nome} (${conta.instituicao || 'Instituição'})`;
            select.appendChild(option);
        });

        if (atual) select.value = atual;
    });
}

function mostrarFiltrosAvancados() {
    mostrarToast('Use Ano, Mês, Tipo e Busca para refinar a visão.', 'info');
}

function exportarReceitas() {
    mostrarToast('Exportação avançada ficará para uma próxima evolução.', 'info');
}

function mostrarMenuReceitas() {
    mostrarToast('Mais ações ficarão agrupadas aqui em evolução futura.', 'info');
}

function mostrarProximosRecebimentos() {
    const busca = document.getElementById('receitas-busca');
    if (busca) busca.value = '';
    estado.busca = '';
    aplicarFiltrosLocais();
    mostrarToast('Mostrando recebimentos pendentes do período selecionado.', 'info');
}

function abrirModal(id) {
    const modal = document.getElementById(id);
    if (!modal) return;
    modal.style.display = 'flex';
    modal.setAttribute('aria-hidden', 'false');
}

function fecharModal(id) {
    const modal = document.getElementById(id);
    if (!modal) return;
    modal.style.display = 'none';
    modal.setAttribute('aria-hidden', 'true');
}

function buscarReceitaLinha(uid) {
    return (estado.receitasMes || []).find((receita) => receita.uid === uid);
}

function buscarFonte(id) {
    return (estado.fontes || []).find((fonte) => Number(fonte.id) === Number(id));
}

function chaveReceita(itemReceitaId, competencia) {
    return `${itemReceitaId || 'sem-fonte'}|${normalizarDataMes(competencia)}`;
}

function receitaPendenteConfirmacao(receita) {
    const observacoes = String(receita?.observacoes || '');
    return /\bconsorcio_id=\d+\b/.test(observacoes) && !receita?.conta_bancaria_id;
}

function obterContaLinha(fonte, realizada) {
    const contaId = realizada?.conta_bancaria_id || fonte?.conta_bancaria_id;
    if (!contaId) return null;
    return (estado.contasBancarias || []).find((conta) => Number(conta.id) === Number(contaId)) || {
        id: contaId,
        nome: realizada?.conta_bancaria?.nome || fonte?.conta_bancaria?.nome || 'Conta bancária',
        instituicao: realizada?.conta_bancaria?.instituicao || fonte?.conta_bancaria?.instituicao || '',
    };
}

function obterStatusReceita(previsto, realizado) {
    if (realizado > 0 && (previsto <= 0 || realizado >= previsto)) return 'REALIZADA';
    if (realizado > 0) return 'PARCIAL';
    return 'PREVISTA';
}

function statusClasse(status) {
    const mapa = {
        REALIZADA: 'realizada',
        PREVISTA: 'prevista',
        PARCIAL: 'parcial',
        CANCELADA: 'cancelada',
        INATIVA: 'cancelada',
    };
    return mapa[status] || 'prevista';
}

function formatarStatus(status) {
    const mapa = {
        REALIZADA: 'Realizada',
        PREVISTA: 'Prevista',
        PARCIAL: 'Parcial',
        CANCELADA: 'Cancelada',
        INATIVA: 'Inativa',
    };
    return mapa[status] || status || 'Prevista';
}

function getTipoInfo(tipo) {
    return TIPOS_RECEITA[tipo] || TIPOS_RECEITA.OUTROS;
}

function formatarTipo(tipo) {
    return getTipoInfo(tipo).label;
}

function formatarMoeda(valor) {
    return new Intl.NumberFormat('pt-BR', {
        style: 'currency',
        currency: 'BRL',
    }).format(Number(valor || 0));
}

function formatarPercentual(valor) {
    return `${Number(valor || 0).toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`;
}

function parseMoeda(valor) {
    if (typeof valor === 'number') return valor;
    if (!valor) return 0;

    const texto = String(valor).replace(/[^\d,.-]/g, '').trim();
    if (!texto) return 0;

    const normalizado = texto.includes(',')
        ? texto.replace(/\./g, '').replace(',', '.')
        : texto;

    return Number.parseFloat(normalizado) || 0;
}

function formatarNumeroInput(valor) {
    return Number(valor || 0).toLocaleString('pt-BR', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    });
}

function formatarCompetencia(data) {
    const normalizada = normalizarDataMes(data);
    if (!normalizada) return '—';
    return `${normalizada.slice(5, 7)}/${normalizada.slice(0, 4)}`;
}

function nomeMes(data) {
    const normalizada = normalizarDataMes(data);
    if (!normalizada) return '';

    const nomes = [
        'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
        'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
    ];

    return `${nomes[Number(normalizada.slice(5, 7)) - 1]}/${normalizada.slice(0, 4)}`;
}

function getAnoMesSelecionado() {
    const ano = estado.anoAtual || new Date().getFullYear();
    const mes = estado.mesAtual || String(new Date().getMonth() + 1).padStart(2, '0');
    return `${ano}-${String(mes).padStart(2, '0')}-01`;
}

function normalizarDataMes(data) {
    if (!data) return '';
    return `${String(data).slice(0, 7)}-01`;
}

function normalizarDataDia(data) {
    if (!data) return '';
    return String(data).slice(0, 10);
}

function montarDataPrevista(anoMes, dia) {
    const ano = Number(anoMes.slice(0, 4));
    const mes = Number(anoMes.slice(5, 7));
    const ultimoDia = new Date(ano, mes, 0).getDate();
    const diaSeguro = Math.min(Math.max(Number(dia || 1), 1), ultimoDia);
    return `${anoMes.slice(0, 8)}${String(diaSeguro).padStart(2, '0')}`;
}

function formatarDataBR(data) {
    if (!data) return '—';
    const [ano, mes, dia] = String(data).slice(0, 10).split('-');
    return `${dia}/${mes}/${ano}`;
}

function formatarAgenciaConta(conta) {
    if (!conta) return 'Sem conta padrão';

    const agencia = conta.agencia ? `Ag. ${conta.agencia}` : '';
    const numero = conta.numero_conta ? `C/C ${conta.numero_conta}${conta.digito_conta ? `-${conta.digito_conta}` : ''}` : '';
    const partes = [conta.instituicao, agencia, numero].filter(Boolean);
    return partes.length ? partes.join(' · ') : 'Conta bancária';
}

function soma(lista, campo) {
    return (lista || []).reduce((total, item) => total + Number(item[campo] || 0), 0);
}

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function setValue(id, value) {
    const el = document.getElementById(id);
    if (el) el.value = value ?? '';
}

function setChecked(id, value) {
    const el = document.getElementById(id);
    if (el) el.checked = !!value;
}

function atualizarContadorCampo(id) {
    const campo = document.getElementById(id);
    const contador = document.getElementById(`${id}-count`);
    if (!campo || !contador) return;
    contador.textContent = `${campo.value.length}/${campo.maxLength || 200}`;
}

function renderizarErroLista() {
    const lista = document.getElementById('mes-lista');
    if (!lista) return;
    lista.innerHTML = `
        <div class="receitas-empty-state">
            <h3>Não foi possível carregar as receitas.</h3>
            <p>Tente atualizar a página ou revisar os filtros.</p>
        </div>
    `;
}

function mostrarToast(mensagem, tipo = 'info') {
    const existente = document.querySelector('.receitas-toast');
    if (existente) existente.remove();

    const toast = document.createElement('div');
    toast.className = 'receitas-toast';
    toast.textContent = mensagem;

    const cores = {
        success: ['#ecfdf5', '#047857'],
        error: ['#fef2f2', '#b91c1c'],
        info: ['#eff6ff', '#1d4ed8'],
    };
    const [background, color] = cores[tipo] || cores.info;
    toast.style.background = background;
    toast.style.color = color;

    document.body.appendChild(toast);
    window.setTimeout(() => toast.remove(), 3200);
}

function normalizarTexto(texto) {
    return String(texto || '')
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .toLowerCase();
}

function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function escapeAttribute(value) {
    return escapeHtml(value).replace(/`/g, '&#096;');
}

function iconReceitas(name) {
    const icons = {
        eye: '<path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6-10-6-10-6Z"/><circle cx="12" cy="12" r="2.8"/>',
        edit: '<path d="M5 19h4L19 9a2.1 2.1 0 0 0-3-3L6 16l-1 3Z"/><path d="M14 6l4 4"/>',
        check: '<path d="M5 12.5l4 4L19 7"/>',
        x: '<path d="M6 6l12 12M18 6 6 18"/>',
        more: '<circle cx="12" cy="5" r="1.3"/><circle cx="12" cy="12" r="1.3"/><circle cx="12" cy="19" r="1.3"/>',
    };

    return `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false" style="width:1em;height:1em;display:inline-block;vertical-align:-0.15em;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round;">${icons[name] || icons.more}</svg>`;
}
