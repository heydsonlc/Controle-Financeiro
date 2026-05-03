const API_BASE = '/api/financiamentos';

const estadoFinanciamentos = {
    lista: [],
    filtrados: [],
    atual: null,
    abaAtual: 'parcelas',
    modoTabela: false
};

document.addEventListener('DOMContentLoaded', () => {
    atualizarTituloGlobal('Financiamentos');
    configurarEventosFormulario();
    configurarEventosSimulacao();
    preencherDatasPadrao();
    carregarFinanciamentos();
});

function configurarEventosFormulario() {
    ['fin-valor', 'fin-entrada', 'fin-saldo-inicial', 'fin-prazo', 'fin-taxa', 'fin-seguro', 'fin-taxa-adm', 'fin-data-primeira'].forEach((id) => {
        const campo = document.getElementById(id);
        if (campo) {
            campo.addEventListener('input', () => {
                if (id === 'fin-valor' || id === 'fin-entrada') {
                    atualizarSaldoInicial();
                }
                atualizarResumoSimulacao();
            });
            if (['fin-valor', 'fin-entrada', 'fin-saldo-inicial', 'fin-seguro', 'fin-taxa-adm'].includes(id)) {
                campo.addEventListener('blur', () => formatarCampoMoeda(campo));
            }
        }
    });

    const dataPrimeira = document.getElementById('fin-data-primeira');
    const diaVencimento = document.getElementById('fin-dia-vencimento');
    if (dataPrimeira && diaVencimento) {
        dataPrimeira.addEventListener('change', () => {
            const partes = dataPrimeira.value.split('-');
            if (partes.length === 3) {
                diaVencimento.value = String(Number(partes[2]));
            }
            atualizarResumoSimulacao();
        });
    }

    const observacoes = document.getElementById('fin-observacoes');
    const contador = document.getElementById('fin-observacoes-count');
    if (observacoes && contador) {
        observacoes.addEventListener('input', () => {
            contador.textContent = observacoes.value.length;
        });
    }
}

function configurarEventosSimulacao() {
    const valor = document.getElementById('sim-amort-valor');
    if (valor) {
        valor.addEventListener('input', simularAmortizacaoDetalhe);
        valor.addEventListener('blur', () => {
            formatarCampoMoeda(valor);
            simularAmortizacaoDetalhe();
        });
    }

    document.querySelectorAll('input[name="sim-estrategia"]').forEach((radio) => {
        radio.addEventListener('change', () => {
            document.querySelectorAll('.fin-strategy').forEach((item) => item.classList.remove('active'));
            radio.closest('.fin-strategy')?.classList.add('active');
            simularAmortizacaoDetalhe();
        });
    });
}

function preencherDatasPadrao() {
    const hoje = new Date();
    const hojeIso = toISODate(hoje);
    const proximoMes = new Date(hoje.getFullYear(), hoje.getMonth() + 1, 1);

    const dataContrato = document.getElementById('fin-data-contrato');
    const dataPrimeira = document.getElementById('fin-data-primeira');
    const pagarData = document.getElementById('pagar-data');
    const amortData = document.getElementById('amort-data');

    if (dataContrato && !dataContrato.value) dataContrato.value = hojeIso;
    if (dataPrimeira && !dataPrimeira.value) dataPrimeira.value = toISODate(proximoMes);
    if (pagarData) pagarData.value = hojeIso;
    if (amortData) amortData.value = hojeIso;

    const diaVencimento = document.getElementById('fin-dia-vencimento');
    if (diaVencimento && dataPrimeira?.value) {
        diaVencimento.value = String(Number(dataPrimeira.value.split('-')[2]));
    }
}

async function carregarFinanciamentos() {
    const lista = document.getElementById('financiamentos-lista');
    if (lista) {
        lista.innerHTML = '<div class="fin-loading-state">Carregando financiamentos...</div>';
    }

    try {
        const status = document.getElementById('filtro-status')?.value || 'ativos';
        const sistemaFiltro = document.getElementById('filtro-sistema')?.value || 'todos';
        const ativoParam = status === 'todos' ? '' : `?ativo=${status === 'ativos' ? 'true' : 'false'}`;
        const response = await fetch(`${API_BASE}${ativoParam}`);
        const resultado = await response.json();

        if (!resultado.success) {
            throw new Error(resultado.error || 'Erro ao carregar financiamentos');
        }

        estadoFinanciamentos.lista = Array.isArray(resultado.data) ? resultado.data : [];
        estadoFinanciamentos.filtrados = estadoFinanciamentos.lista.filter((financiamento) => {
            if (sistemaFiltro === 'todos') return true;
            return sistemaVisual(financiamento) === sistemaFiltro || financiamento.sistema_amortizacao === sistemaFiltro;
        });

        renderizarFinanciamentos(estadoFinanciamentos.filtrados);
        atualizarResumo(estadoFinanciamentos.filtrados);
    } catch (error) {
        console.error('Erro ao carregar financiamentos:', error);
        if (lista) {
            lista.innerHTML = `<div class="fin-empty-state"><h3>Não foi possível carregar os financiamentos.</h3><p>${escapeHtml(error.message)}</p></div>`;
        }
    }
}

function renderizarFinanciamentos(financiamentos) {
    const container = document.getElementById('financiamentos-lista');
    const count = document.getElementById('contratos-count');
    const footer = document.getElementById('financiamentos-pagination');

    if (count) count.textContent = String(financiamentos.length);
    if (footer) footer.textContent = `Mostrando ${financiamentos.length} de ${financiamentos.length} contratos`;
    if (!container) return;

    if (!financiamentos.length) {
        container.innerHTML = `
            <div class="fin-empty-state">
                <h3>Nenhum financiamento cadastrado.</h3>
                <p>Crie um contrato para acompanhar parcelas, saldo devedor e amortizações.</p>
                <button type="button" class="fin-primary-btn" onclick="abrirTelaNovoFinanciamento()">Novo financiamento</button>
            </div>
        `;
        return;
    }

    container.innerHTML = financiamentos.map((financiamento, index) => {
        const totalParcelas = Number(financiamento.total_parcelas || financiamento.prazo_total_meses || 0);
        const pagas = Number(financiamento.parcelas_pagas || 0);
        const progresso = totalParcelas > 0 ? Math.min((pagas / totalParcelas) * 100, 100) : 0;
        const sistema = sistemaVisual(financiamento);
        const subtitulo = tipoVisual(financiamento);
        const iconClass = index % 2 === 0 ? '' : 'green';

        return `
            <article class="fin-contract-row">
                <span class="fin-contract-icon ${iconClass}" aria-hidden="true">${iconeCasa()}</span>
                <div class="fin-contract-main">
                    <h3>${escapeHtml(financiamento.nome || 'Financiamento')}</h3>
                    <span class="fin-soft-badge">${escapeHtml(sistema)}</span>
                    <p>${escapeHtml(subtitulo)}</p>
                </div>
                <div class="fin-contract-metrics">
                    <div class="fin-contract-metric">
                        <span>Valor financiado</span>
                        <strong>${formatarMoedaDisplay(financiamento.valor_financiado)}</strong>
                    </div>
                    <div class="fin-contract-metric">
                        <span>Saldo devedor atual</span>
                        <strong>${formatarMoedaDisplay(financiamento.saldo_devedor_atual)}</strong>
                    </div>
                    <div class="fin-contract-metric">
                        <span>Parcelas</span>
                        <strong>${pagas} / ${totalParcelas}</strong>
                    </div>
                    <div class="fin-contract-metric">
                        <span>Taxa anual</span>
                        <strong>${formatarPercentualDisplay(financiamento.taxa_juros_nominal_anual)}</strong>
                    </div>
                    <div class="fin-progress-wrap">
                        <div class="fin-progress-track"><div class="fin-progress-fill" style="width: ${progresso.toFixed(2)}%"></div></div>
                        <small>${progresso.toFixed(2).replace('.', ',')}% das parcelas pagas</small>
                    </div>
                </div>
                <div class="fin-contract-actions">
                    <button type="button" class="fin-action-btn" onclick="verDetalhes(${financiamento.id})">Visualizar</button>
                    <button type="button" class="fin-action-btn green" onclick="abrirModalAmortizacao(${financiamento.id})">Amortizar</button>
                    <button type="button" class="fin-action-btn blue" onclick="abrirExtratoFinanciamento(${financiamento.id})">Extrato</button>
                    <button type="button" class="fin-action-btn" onclick="editarFinanciamento(${financiamento.id})">Editar</button>
                    <button type="button" class="fin-action-btn red" onclick="abrirQuitacao(${financiamento.id})">Quitar</button>
                </div>
                <button type="button" class="fin-row-menu" onclick="verDetalhes(${financiamento.id})" aria-label="Mais ações">⋮</button>
            </article>
        `;
    }).join('');
}

function atualizarResumo(financiamentos) {
    const totalFinanciado = financiamentos.reduce((total, item) => total + Number(item.valor_financiado || 0), 0);
    const saldoDevedor = financiamentos.reduce((total, item) => total + Number(item.saldo_devedor_atual || 0), 0);
    const totalParcelas = financiamentos.reduce((total, item) => total + Number(item.total_parcelas || item.prazo_total_meses || 0), 0);
    const parcelasPagas = financiamentos.reduce((total, item) => total + Number(item.parcelas_pagas || 0), 0);
    const contratosAtivos = financiamentos.filter((item) => item.ativo !== false).length;
    const percentualPagas = totalParcelas > 0 ? (parcelasPagas / totalParcelas) * 100 : 0;

    setText('total-financiado', formatarMoedaDisplay(totalFinanciado));
    setText('saldo-devedor', formatarMoedaDisplay(saldoDevedor));
    setText('parcelas-pagas', `${parcelasPagas} / ${totalParcelas}`);
    setText('parcelas-pagas-sub', `${percentualPagas.toFixed(2).replace('.', ',')}% do total de parcelas`);
    setText('contratos-ativos', String(contratosAtivos));
}

function abrirTelaNovoFinanciamento() {
    limparFormulario();
    setText('form-title', 'Novo financiamento');
    setText('form-breadcrumb-current', 'Novo financiamento');
    atualizarTituloGlobal('Novo financiamento');
    mostrarView('form');
    atualizarResumoSimulacao();
}

function abrirModalNovoFinanciamento() {
    abrirTelaNovoFinanciamento();
}

function cancelarFormulario() {
    mostrarView('list');
}

function voltarLista() {
    estadoFinanciamentos.atual = null;
    atualizarTituloGlobal('Financiamentos');
    mostrarView('list');
    carregarFinanciamentos();
}

function mostrarView(view) {
    if (view === 'list') {
        atualizarTituloGlobal('Financiamentos');
    }
    document.querySelectorAll('.fin-view').forEach((item) => item.classList.remove('is-active'));
    const alvo = document.getElementById(`fin-${view}-view`);
    if (alvo) alvo.classList.add('is-active');
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function limparFormulario() {
    document.getElementById('form-financiamento')?.reset();
    setValue('fin-id', '');
    selecionarSistema('SAC');
    preencherDatasPadrao();
    setValue('fin-valor', '');
    setValue('fin-entrada', '');
    setValue('fin-saldo-inicial', '');
    setValue('fin-seguro', '');
    setValue('fin-taxa-adm', '');
    setText('fin-observacoes-count', '0');
}

function selecionarSistema(sistema) {
    setValue('fin-sistema', sistema);
    document.querySelectorAll('.fin-segmented [data-sistema]').forEach((botao) => {
        botao.classList.toggle('active', botao.dataset.sistema === sistema);
    });
    setText('sim-sistema', sistema);
    atualizarResumoSimulacao();
}

function atualizarSaldoInicial() {
    const valor = parseMoeda(document.getElementById('fin-valor')?.value);
    const entrada = parseMoeda(document.getElementById('fin-entrada')?.value);
    const saldo = Math.max(valor - entrada, 0);
    const campoSaldo = document.getElementById('fin-saldo-inicial');
    if (campoSaldo && (document.activeElement?.id === 'fin-valor' || document.activeElement?.id === 'fin-entrada')) {
        campoSaldo.value = saldo > 0 ? formatarMoedaSemSimbolo(saldo) : '';
    }
}

function atualizarResumoSimulacao() {
    const saldo = parseMoeda(document.getElementById('fin-saldo-inicial')?.value);
    const prazo = Number(document.getElementById('fin-prazo')?.value || 0);
    const taxaAnual = parseNumero(document.getElementById('fin-taxa')?.value);
    const seguro = parseMoeda(document.getElementById('fin-seguro')?.value);
    const taxaAdm = parseMoeda(document.getElementById('fin-taxa-adm')?.value);
    const sistema = document.getElementById('fin-sistema')?.value || 'SAC';
    const dataPrimeira = document.getElementById('fin-data-primeira')?.value;

    const taxaMensal = calcularTaxaMensal(taxaAnual);
    let parcela = 0;

    if (saldo > 0 && prazo > 0) {
        if (sistema === 'PRICE') {
            parcela = taxaMensal > 0
                ? saldo * (taxaMensal * Math.pow(1 + taxaMensal, prazo)) / (Math.pow(1 + taxaMensal, prazo) - 1)
                : saldo / prazo;
        } else {
            parcela = (saldo / prazo) + (saldo * taxaMensal);
        }
        parcela += seguro + taxaAdm;
    }

    setText('sim-parcela', formatarMoedaDisplay(parcela));
    setText('sim-custo-total', formatarMoedaDisplay(parcela * prazo));
    setText('sim-primeira', dataPrimeira ? formatarDataBR(dataPrimeira) : '--');
    setText('sim-sistema', sistema);
    setText('sim-prazo', `${prazo || 0} meses`);
}

async function salvarFinanciamento(event) {
    event.preventDefault();

    try {
        const id = document.getElementById('fin-id')?.value;
        const dados = coletarDadosFormulario(Boolean(id));
        const response = await fetch(id ? `${API_BASE}/${id}` : API_BASE, {
            method: id ? 'PUT' : 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        });
        const resultado = await response.json();

        if (!resultado.success) {
            throw new Error(resultado.error || resultado.message || 'Erro ao salvar financiamento');
        }

        mostrarToast(id ? 'Financiamento atualizado com sucesso.' : 'Financiamento salvo com sucesso.');
        mostrarView('list');
        await carregarFinanciamentos();
    } catch (error) {
        mostrarToast(error.message, 'erro');
    }
}

function coletarDadosFormulario(editando) {
    const sistemaVisualSelecionado = document.getElementById('fin-sistema')?.value || 'SAC';
    const produto = document.getElementById('fin-produto')?.value || 'Habitacional';
    const saldoInicial = parseMoeda(document.getElementById('fin-saldo-inicial')?.value);
    const seguro = parseMoeda(document.getElementById('fin-seguro')?.value);
    const dataPrimeira = document.getElementById('fin-data-primeira')?.value;
    const nome = document.getElementById('fin-nome')?.value?.trim();

    if (!nome) throw new Error('Informe o nome do financiamento.');
    if (saldoInicial <= 0) throw new Error('Informe um saldo inicial maior que zero.');
    if (!editando && seguro <= 0) throw new Error('Informe seguro habitacional mensal maior que zero.');

    const dados = {
        nome,
        produto: sistemaVisualSelecionado === 'SFH' ? 'SFH' : produto,
        sistema_amortizacao: sistemaVisualSelecionado === 'SFH' ? 'SAC' : sistemaVisualSelecionado,
        valor_financiado: saldoInicial,
        prazo_total_meses: Number(document.getElementById('fin-prazo')?.value || 0),
        taxa_juros_nominal_anual: parseNumero(document.getElementById('fin-taxa')?.value),
        indexador_saldo: document.getElementById('fin-indexador')?.value || null,
        data_contrato: document.getElementById('fin-data-contrato')?.value,
        data_primeira_parcela: dataPrimeira,
        seguro_tipo: 'fixo',
        valor_seguro_mensal: seguro,
        taxa_administracao_fixa: parseMoeda(document.getElementById('fin-taxa-adm')?.value),
        ativo: document.getElementById('fin-status')?.value !== 'inativo'
    };

    if (!dados.prazo_total_meses || dados.prazo_total_meses <= 0) throw new Error('Informe prazo em meses maior que zero.');
    if (dados.taxa_juros_nominal_anual < 0) throw new Error('A taxa de juros não pode ser negativa.');
    if (!dados.data_contrato) throw new Error('Informe a data de contratação.');
    if (!dados.data_primeira_parcela) throw new Error('Informe a data da 1ª parcela.');

    if (!editando) {
        dados.vigencias_seguro = [{
            competencia_inicio: dataPrimeira,
            valor_mensal: seguro,
            observacoes: document.getElementById('fin-observacoes')?.value || null
        }];
    }

    return dados;
}

async function verDetalhes(id) {
    try {
        const response = await fetch(`${API_BASE}/${id}`);
        const resultado = await response.json();

        if (!resultado.success) {
            throw new Error(resultado.error || 'Erro ao carregar detalhe do financiamento');
        }

        estadoFinanciamentos.atual = resultado.data;
        estadoFinanciamentos.abaAtual = 'parcelas';
        renderizarDetalhes(resultado.data);
        mostrarView('detail');
    } catch (error) {
        mostrarToast(error.message, 'erro');
    }
}

function renderizarDetalhes(financiamento) {
    const parcelas = Array.isArray(financiamento.parcelas) ? financiamento.parcelas : [];
    const pagas = parcelas.filter((parcela) => String(parcela.status).toLowerCase() === 'pago').length;
    const total = parcelas.length || Number(financiamento.total_parcelas || financiamento.prazo_total_meses || 0);
    const percentual = total > 0 ? (pagas / total) * 100 : 0;
    const proxima = parcelas.find((parcela) => String(parcela.status).toLowerCase() !== 'pago') || parcelas[0];
    const sistema = sistemaVisual(financiamento);

    setText('detalhe-breadcrumb', financiamento.nome || 'Financiamento');
    setText('detalhe-nome', financiamento.nome || 'Financiamento');
    atualizarTituloGlobal(financiamento.nome || 'Financiamento');
    setText('detalhe-sistema', sistema);
    setText('detalhe-status', financiamento.ativo === false ? 'INATIVO' : 'ATIVO');
    document.getElementById('detalhe-status')?.classList.toggle('warning', financiamento.ativo === false);
    document.getElementById('detalhe-status')?.classList.toggle('success', financiamento.ativo !== false);
    setText('detalhe-subtitulo', `${escapeText(financiamento.nome || 'Contrato')} - ${tipoVisual(financiamento)}`);
    setText('detalhe-valor-financiado', formatarMoedaDisplay(financiamento.valor_financiado));
    setText('detalhe-saldo-devedor', formatarMoedaDisplay(financiamento.saldo_devedor_atual));
    setText('detalhe-data-base', financiamento.data_base ? `Atualizado em ${formatarDataBR(financiamento.data_base)}` : 'Atualizado');
    setText('detalhe-parcelas-pagas', `${pagas} / ${total}`);
    setText('detalhe-parcelas-sub', `${percentual.toFixed(2).replace('.', ',')}% do total de parcelas`);
    setText('detalhe-proxima-data', proxima ? formatarDataBR(proxima.data_vencimento) : '--');
    setText('detalhe-proxima-valor', proxima ? formatarMoedaDisplay(proxima.valor_previsto_total) : 'R$ 0,00');
    setText('sim-quitacao-valor', formatarMoedaDisplay(financiamento.saldo_devedor_atual));
    setText('sim-quitacao-data', `Data base: ${financiamento.data_base ? formatarDataBR(financiamento.data_base) : formatarDataBR(toISODate(new Date()))}`);

    renderizarTabelaParcelas(parcelas);
    selecionarAba('parcelas');
    simularAmortizacaoDetalhe();
}

function renderizarTabelaParcelas(parcelas) {
    const tbody = document.getElementById('detalhe-parcelas-body');
    if (!tbody) return;

    const pagina = parcelas.slice(0, 10);
    tbody.innerHTML = pagina.map((parcela) => {
        const pago = String(parcela.status).toLowerCase() === 'pago';
        return `
            <tr>
                <td>${parcela.numero_parcela || '-'}</td>
                <td>${formatarDataBR(parcela.data_vencimento)}</td>
                <td>${formatarMoedaDisplay(parcela.valor_amortizacao)}</td>
                <td>${formatarMoedaDisplay(parcela.valor_juros)}</td>
                <td>${formatarMoedaDisplay(parcela.valor_seguro)}</td>
                <td>${formatarMoedaDisplay(parcela.valor_taxa_adm)}</td>
                <td><strong>${formatarMoedaDisplay(parcela.valor_previsto_total)}</strong></td>
                <td>${formatarMoedaDisplay(parcela.saldo_devedor_apos_pagamento)}</td>
                <td><span class="fin-pill ${pago ? 'paid' : 'pending'}">${pago ? 'PAGO' : 'PENDENTE'}</span></td>
                <td>
                    ${pago
                        ? '<button type="button" class="fin-table-menu-btn" title="Parcela paga">...</button>'
                        : `<button type="button" class="fin-table-menu-btn" onclick="abrirModalPagamento(${parcela.id})" title="Registrar pagamento">⋮</button>`}
                </td>
            </tr>
        `;
    }).join('');

    setText('detalhe-parcelas-footer', `Mostrando 1 a ${pagina.length} de ${parcelas.length} parcelas`);
}

function selecionarAba(aba) {
    estadoFinanciamentos.abaAtual = aba;
    document.querySelectorAll('.fin-tabs [data-tab]').forEach((botao) => {
        botao.classList.toggle('active', botao.dataset.tab === aba);
    });

    const financiamento = estadoFinanciamentos.atual;
    if (!financiamento) return;

    const title = document.getElementById('detalhe-tab-title');
    const content = document.getElementById('detalhe-tab-content');
    const footer = document.getElementById('detalhe-parcelas-footer');
    if (!title || !content) return;

    if (aba === 'parcelas') {
        title.textContent = `Cronograma de Parcelas (${(financiamento.parcelas || []).length} parcelas)`;
        content.innerHTML = `
            <div class="fin-table-wrap">
                <table class="fin-schedule-table">
                    <thead>
                        <tr>
                            <th>Nº</th>
                            <th>Vencimento</th>
                            <th>Amortização</th>
                            <th>Juros</th>
                            <th>Seguro</th>
                            <th>Taxa adm</th>
                            <th>Total</th>
                            <th>Saldo após</th>
                            <th>Status</th>
                            <th>Ações</th>
                        </tr>
                    </thead>
                    <tbody id="detalhe-parcelas-body"></tbody>
                </table>
            </div>
        `;
        renderizarTabelaParcelas(financiamento.parcelas || []);
        return;
    }

    const htmlPorAba = {
        resumo: renderizarAbaResumo(financiamento),
        extrato: renderizarAbaExtrato(financiamento),
        amortizacao: renderizarAbaAmortizacao(financiamento),
        quitacao: renderizarAbaQuitacao(financiamento),
        documentos: renderizarAbaDocumentos(),
        dados: renderizarAbaDados(financiamento)
    };

    const titulos = {
        resumo: 'Resumo operacional',
        extrato: 'Extrato e histórico',
        amortizacao: 'Amortização',
        quitacao: 'Quitação',
        documentos: 'Documentos',
        dados: 'Dados do contrato'
    };

    title.textContent = titulos[aba] || 'Detalhe';
    content.innerHTML = htmlPorAba[aba] || renderizarAbaResumo(financiamento);
    if (footer) footer.textContent = `${titulos[aba] || 'Detalhe'} do financiamento`;
}

function selecionarAbaDetalheOuAvisar(aba) {
    if (estadoFinanciamentos.atual) {
        selecionarAba(aba);
        mostrarView('detail');
        return;
    }
    mostrarToast('Salve ou selecione um financiamento para abrir a simulação detalhada.');
}

function renderizarAbaResumo(financiamento) {
    const parcelas = financiamento.parcelas || [];
    const proxima = parcelas.find((parcela) => String(parcela.status).toLowerCase() !== 'pago');
    return `
        <div class="fin-info-grid">
            <div class="fin-info-item"><span>Sistema</span><strong>${escapeHtml(sistemaVisual(financiamento))}</strong></div>
            <div class="fin-info-item"><span>Produto</span><strong>${escapeHtml(tipoVisual(financiamento))}</strong></div>
            <div class="fin-info-item"><span>Prazo total</span><strong>${financiamento.prazo_total_meses || 0} meses</strong></div>
            <div class="fin-info-item"><span>Taxa anual</span><strong>${formatarPercentualDisplay(financiamento.taxa_juros_nominal_anual)}</strong></div>
            <div class="fin-info-item"><span>Seguro mensal</span><strong>${formatarMoedaDisplay(financiamento.valor_seguro_mensal)}</strong></div>
            <div class="fin-info-item"><span>Próxima parcela</span><strong>${proxima ? formatarMoedaDisplay(proxima.valor_previsto_total) : 'Sem parcela pendente'}</strong></div>
        </div>
    `;
}

function renderizarAbaExtrato(financiamento) {
    const eventos = (financiamento.parcelas || [])
        .filter((parcela) => String(parcela.status).toLowerCase() === 'pago')
        .slice(0, 12);

    if (!eventos.length) {
        return '<div class="fin-tab-empty"><h3>Nenhum lançamento no extrato.</h3><p>Pagamentos, amortizações e quitações aparecerão aqui conforme forem registrados.</p></div>';
    }

    return `
        <div class="fin-demo-content">
            <div class="fin-demo-row header"><span>Evento</span><span>Data</span><span>Amortização</span><span>Juros</span><span>Total</span></div>
            ${eventos.map((parcela) => `
                <div class="fin-demo-row">
                    <span>Parcela ${parcela.numero_parcela} paga</span>
                    <span>${formatarDataBR(parcela.data_vencimento)}</span>
                    <span>${formatarMoedaDisplay(parcela.valor_amortizacao)}</span>
                    <span>${formatarMoedaDisplay(parcela.valor_juros)}</span>
                    <span><strong>${formatarMoedaDisplay(parcela.valor_pago || parcela.valor_previsto_total)}</strong></span>
                </div>
            `).join('')}
        </div>
    `;
}

function renderizarAbaAmortizacao(financiamento) {
    return `
        <div class="fin-info-grid">
            <div class="fin-info-item"><span>Saldo atual</span><strong>${formatarMoedaDisplay(financiamento.saldo_devedor_atual)}</strong></div>
            <div class="fin-info-item"><span>Regime pós-amortização</span><strong>${escapeHtml(financiamento.regime_pos_amortizacao || 'Sem amortização registrada')}</strong></div>
            <div class="fin-info-item"><span>Ação disponível</span><strong>Simular ou registrar amortização</strong></div>
        </div>
        <div class="fin-tab-empty">
            <button type="button" class="fin-primary-btn" onclick="abrirModalAmortizacao()">Registrar amortização</button>
        </div>
    `;
}

function renderizarAbaQuitacao(financiamento) {
    return `
        <div class="fin-info-grid">
            <div class="fin-info-item"><span>Valor para quitação</span><strong>${formatarMoedaDisplay(financiamento.saldo_devedor_atual)}</strong></div>
            <div class="fin-info-item"><span>Data base</span><strong>${financiamento.data_base ? formatarDataBR(financiamento.data_base) : formatarDataBR(toISODate(new Date()))}</strong></div>
            <div class="fin-info-item"><span>Status</span><strong>Simulação operacional</strong></div>
        </div>
        <div class="fin-tab-empty">
            <p>A emissão real de boleto de quitação depende de integração bancária. O valor exibido usa o saldo devedor atual do contrato.</p>
        </div>
    `;
}

function renderizarAbaDocumentos() {
    return '<div class="fin-tab-empty"><h3>Nenhum documento anexado.</h3><p>Contratos, boletos e comprovantes poderão ser organizados aqui em evolução futura.</p></div>';
}

function renderizarAbaDados(financiamento) {
    return `
        <div class="fin-info-grid">
            <div class="fin-info-item"><span>Nome</span><strong>${escapeHtml(financiamento.nome || '-')}</strong></div>
            <div class="fin-info-item"><span>Produto</span><strong>${escapeHtml(financiamento.produto || '-')}</strong></div>
            <div class="fin-info-item"><span>Sistema do motor</span><strong>${escapeHtml(financiamento.sistema_amortizacao || '-')}</strong></div>
            <div class="fin-info-item"><span>Data do contrato</span><strong>${formatarDataBR(financiamento.data_contrato)}</strong></div>
            <div class="fin-info-item"><span>1ª parcela</span><strong>${formatarDataBR(financiamento.data_primeira_parcela)}</strong></div>
            <div class="fin-info-item"><span>Indexador</span><strong>${escapeHtml(financiamento.indexador_saldo || 'Não informado')}</strong></div>
        </div>
        <div class="fin-tab-empty">
            <button type="button" class="fin-secondary-btn" onclick="abrirSeguroHabitacional()">Gerenciar seguro habitacional</button>
        </div>
    `;
}

async function editarFinanciamento(id) {
    try {
        const response = await fetch(`${API_BASE}/${id}`);
        const resultado = await response.json();
        if (!resultado.success) throw new Error(resultado.error || 'Erro ao carregar financiamento');

        const financiamento = resultado.data;
        setValue('fin-id', financiamento.id);
        setValue('fin-nome', financiamento.nome || '');
        setValue('fin-produto', financiamento.produto || 'Habitacional');
        selecionarSistema(sistemaVisual(financiamento));
        setValue('fin-finalidade', tipoVisual(financiamento) === 'Imóvel' ? 'Aquisição de imóvel' : 'Outro');
        setValue('fin-status', financiamento.ativo === false ? 'inativo' : 'ativo');
        setValue('fin-valor', formatarMoedaSemSimbolo(financiamento.valor_financiado));
        setValue('fin-entrada', '0,00');
        setValue('fin-saldo-inicial', formatarMoedaSemSimbolo(financiamento.valor_financiado));
        setValue('fin-prazo', financiamento.prazo_total_meses || '');
        setValue('fin-taxa', formatarNumeroBR(financiamento.taxa_juros_nominal_anual));
        setValue('fin-data-contrato', normalizarISODate(financiamento.data_contrato));
        setValue('fin-seguro', formatarMoedaSemSimbolo(financiamento.valor_seguro_mensal));
        setValue('fin-taxa-adm', formatarMoedaSemSimbolo(financiamento.taxa_administracao_fixa));
        setValue('fin-indexador', financiamento.indexador_saldo || '');
        setValue('fin-data-primeira', normalizarISODate(financiamento.data_primeira_parcela));
        setValue('fin-dia-vencimento', normalizarISODate(financiamento.data_primeira_parcela)?.split('-')[2]?.replace(/^0/, '') || '');
        setText('form-title', 'Editar financiamento');
        setText('form-breadcrumb-current', 'Editar financiamento');
        atualizarTituloGlobal('Editar financiamento');
        atualizarResumoSimulacao();
        mostrarView('form');
    } catch (error) {
        mostrarToast(error.message, 'erro');
    }
}

function editarFinanciamentoAtual() {
    if (!estadoFinanciamentos.atual) return;
    editarFinanciamento(estadoFinanciamentos.atual.id);
}

async function abrirQuitacao(id) {
    await verDetalhes(id);
    selecionarAba('quitacao');
}

async function abrirExtratoFinanciamento(id) {
    await verDetalhes(id);
    selecionarAba('extrato');
}

function abrirModalPagamentoProxima() {
    const financiamento = estadoFinanciamentos.atual;
    const proxima = financiamento?.parcelas?.find((parcela) => String(parcela.status).toLowerCase() !== 'pago');
    if (!proxima) {
        mostrarToast('Não há parcela pendente para pagamento.');
        return;
    }
    abrirModalPagamento(proxima.id);
}

function abrirModalPagamento(parcelaId) {
    const financiamento = estadoFinanciamentos.atual;
    const parcela = financiamento?.parcelas?.find((item) => Number(item.id) === Number(parcelaId));
    if (!parcela) {
        mostrarToast('Parcela não encontrada.', 'erro');
        return;
    }

    setValue('pagar-parcela-id', parcela.id);
    setValue('pagar-data', toISODate(new Date()));
    setValue('pagar-valor', formatarMoedaSemSimbolo(parcela.valor_previsto_total));
    const info = document.getElementById('pagar-info');
    if (info) {
        info.innerHTML = `<strong>Parcela ${parcela.numero_parcela}</strong><br>Vencimento: ${formatarDataBR(parcela.data_vencimento)}<br>Total previsto: ${formatarMoedaDisplay(parcela.valor_previsto_total)}`;
    }
    abrirModal('modal-pagar');
}

async function salvarPagamento(event) {
    event.preventDefault();

    try {
        const parcelaId = document.getElementById('pagar-parcela-id')?.value;
        const payload = {
            data_pagamento: document.getElementById('pagar-data')?.value,
            valor_pago: parseMoeda(document.getElementById('pagar-valor')?.value)
        };
        const response = await fetch(`${API_BASE}/parcelas/${parcelaId}/pagar`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const resultado = await response.json();

        if (!resultado.success) {
            throw new Error(resultado.error || 'Erro ao registrar pagamento');
        }

        fecharModal('modal-pagar');
        mostrarToast('Pagamento registrado com sucesso.');
        if (estadoFinanciamentos.atual) {
            await verDetalhes(estadoFinanciamentos.atual.id);
        }
    } catch (error) {
        mostrarToast(error.message, 'erro');
    }
}

function abrirModalAmortizacao(id = null) {
    const financiamentoId = id || estadoFinanciamentos.atual?.id;
    if (!financiamentoId) {
        mostrarToast('Selecione um financiamento para amortizar.');
        return;
    }

    setValue('amort-financiamento-id', financiamentoId);
    setValue('amort-data', toISODate(new Date()));
    setValue('amort-valor', '10.000,00');
    setValue('amort-tipo', 'reduzir_prazo');
    setValue('amort-obs', '');
    const info = document.getElementById('info-amortizacao');
    if (info) {
        info.innerHTML = 'A amortização será registrada pelo motor financeiro existente, preservando o histórico do contrato.';
    }
    abrirModal('modal-amortizacao');
}

async function salvarAmortizacao(event) {
    event.preventDefault();

    try {
        const financiamentoId = document.getElementById('amort-financiamento-id')?.value;
        const payload = {
            data: document.getElementById('amort-data')?.value,
            valor: parseMoeda(document.getElementById('amort-valor')?.value),
            tipo: document.getElementById('amort-tipo')?.value,
            observacoes: document.getElementById('amort-obs')?.value || null
        };
        const response = await fetch(`${API_BASE}/${financiamentoId}/amortizacao-extra`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const resultado = await response.json();

        if (!resultado.success) {
            throw new Error(resultado.error || 'Erro ao registrar amortização');
        }

        fecharModal('modal-amortizacao');
        mostrarToast('Amortização registrada com sucesso.');
        if (estadoFinanciamentos.atual?.id) {
            await verDetalhes(estadoFinanciamentos.atual.id);
        } else {
            await carregarFinanciamentos();
        }
    } catch (error) {
        mostrarToast(error.message, 'erro');
    }
}

function simularAmortizacaoDetalhe() {
    const financiamento = estadoFinanciamentos.atual;
    if (!financiamento) return;

    const valorExtra = parseMoeda(document.getElementById('sim-amort-valor')?.value);
    const estrategia = document.querySelector('input[name="sim-estrategia"]:checked')?.value || 'reduzir_prazo';
    const saldo = Number(financiamento.saldo_devedor_atual || 0);
    const parcelas = financiamento.parcelas || [];
    const pendentes = parcelas.filter((parcela) => String(parcela.status).toLowerCase() !== 'pago');
    const amortizacaoMedia = media(pendentes.map((parcela) => Number(parcela.valor_amortizacao || 0))) || (saldo / Math.max(pendentes.length, 1));
    const taxaMensal = calcularTaxaMensal(Number(financiamento.taxa_juros_nominal_anual || 0));

    let reducaoPrazo = 0;
    let economia = 0;

    if (valorExtra > 0 && saldo > 0) {
        if (estrategia === 'reduzir_prazo') {
            reducaoPrazo = Math.max(1, Math.min(Math.floor(valorExtra / Math.max(amortizacaoMedia, 1)), pendentes.length));
            economia = valorExtra * taxaMensal * Math.max(reducaoPrazo, 1) * 0.65;
        } else {
            reducaoPrazo = 0;
            economia = valorExtra * taxaMensal * Math.max(pendentes.length, 1) * 0.25;
        }
    }

    const novaQuitacao = pendentes.length
        ? adicionarMeses(pendentes[pendentes.length - 1].data_vencimento, -reducaoPrazo)
        : '--';

    setText('sim-amort-prazo', reducaoPrazo ? `- ${reducaoPrazo} meses` : 'Sem redução estimada');
    setText('sim-amort-data', novaQuitacao);
    setText('sim-amort-economia', formatarMoedaDisplay(economia));
}

async function abrirDemonstrativo() {
    if (!estadoFinanciamentos.atual) {
        mostrarToast('Selecione um financiamento para gerar extrato.');
        return;
    }

    const anoSelect = document.getElementById('demo-ano');
    if (anoSelect && !anoSelect.options.length) {
        const anoAtual = new Date().getFullYear();
        for (let ano = anoAtual - 2; ano <= anoAtual + 2; ano += 1) {
            const option = document.createElement('option');
            option.value = String(ano);
            option.textContent = String(ano);
            if (ano === anoAtual) option.selected = true;
            anoSelect.appendChild(option);
        }
    }

    setText('demo-titulo', `Extrato - ${estadoFinanciamentos.atual.nome}`);
    abrirModal('modal-demonstrativo');
    await carregarDemonstrativo();
}

async function carregarDemonstrativo() {
    const financiamento = estadoFinanciamentos.atual;
    const container = document.getElementById('demonstrativo-conteudo');
    const ano = document.getElementById('demo-ano')?.value || new Date().getFullYear();
    if (!financiamento || !container) return;

    container.innerHTML = '<div class="fin-loading-state">Carregando extrato...</div>';

    try {
        const response = await fetch(`${API_BASE}/${financiamento.id}/demonstrativo-anual?ano=${ano}`);
        const resultado = await response.json();
        if (!resultado.success) throw new Error(resultado.error || 'Erro ao carregar demonstrativo');

        const dados = resultado.data || {};
        const resumoMensal = dados.resumo_mensal || {};
        const linhas = Object.entries(resumoMensal).map(([mes, valores]) => ({
            mes: Number(mes),
            ...valores
        })).sort((a, b) => a.mes - b.mes);

        if (!linhas.length) {
            container.innerHTML = '<div class="fin-tab-empty">Nenhum evento encontrado para o período.</div>';
            return;
        }

        container.innerHTML = `
            <div class="fin-demo-row header"><span>Mês</span><span>Amortização</span><span>Juros</span><span>Seguro</span><span>Total previsto</span></div>
            ${linhas.map((linha) => `
                <div class="fin-demo-row">
                    <span>${nomeMes(linha.mes)}</span>
                    <span>${formatarMoedaDisplay(linha.amortizacao)}</span>
                    <span>${formatarMoedaDisplay(linha.juros)}</span>
                    <span>${formatarMoedaDisplay(linha.seguro)}</span>
                    <span><strong>${formatarMoedaDisplay(linha.total_previsto)}</strong></span>
                </div>
            `).join('')}
        `;
    } catch (error) {
        container.innerHTML = `<div class="fin-tab-empty">${escapeHtml(error.message)}</div>`;
    }
}

function abrirSeguroHabitacional() {
    window.location.href = '/financiamentos/seguro';
}

function alternarModoTabela() {
    estadoFinanciamentos.modoTabela = !estadoFinanciamentos.modoTabela;
    mostrarToast(estadoFinanciamentos.modoTabela ? 'Visualização em tabela será detalhada em evolução futura.' : 'Visualização em cards restaurada.');
}

function abrirMenuMaisAcoes() {
    mostrarToast('Use as ações rápidas no painel lateral.');
}

function focarFiltroParcelas() {
    mostrarToast('Filtros de parcelas serão detalhados em evolução futura.');
}

function registrarPendenciaQuitacao() {
    mostrarToast('Geração real de boleto de quitação depende de integração bancária.');
}

async function tentarExcluirFinanciamento(id) {
    const confirmar = window.confirm('Deseja excluir este financiamento? Esta ação só é permitida se não houver histórico.');
    if (!confirmar) return;

    try {
        const response = await fetch(`${API_BASE}/${id}`, { method: 'DELETE' });
        const resultado = await response.json();
        if (!resultado.success) throw new Error(resultado.error || resultado.message || 'Erro ao excluir financiamento');
        mostrarToast('Financiamento excluído com sucesso.');
        carregarFinanciamentos();
    } catch (error) {
        mostrarToast(error.message, 'erro');
    }
}

function abrirModal(id) {
    const modal = document.getElementById(id);
    if (!modal) return;
    modal.classList.add('is-open');
    modal.setAttribute('aria-hidden', 'false');
}

function fecharModal(id) {
    const modal = document.getElementById(id);
    if (!modal) return;
    modal.classList.remove('is-open');
    modal.setAttribute('aria-hidden', 'true');
}

function setText(id, texto) {
    const el = document.getElementById(id);
    if (el) el.textContent = texto;
}

function setValue(id, valor) {
    const el = document.getElementById(id);
    if (el) el.value = valor ?? '';
}

function atualizarTituloGlobal(titulo) {
    const el = document.querySelector('.app-topbar-title span');
    if (el) el.textContent = titulo;
}

function sistemaVisual(financiamento) {
    const produto = String(financiamento?.produto || '').toUpperCase();
    if (produto.includes('SFH')) return 'SFH';
    return financiamento?.sistema_amortizacao || document.getElementById('fin-sistema')?.value || 'SAC';
}

function tipoVisual(financiamento) {
    const produto = String(financiamento?.produto || '').trim();
    if (!produto || produto.toUpperCase() === 'SFH' || produto.toLowerCase() === 'habitacional') return 'Imóvel';
    return produto;
}

function formatarMoedaDisplay(valor) {
    const numero = Number(valor || 0);
    return numero.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}

function formatarMoedaSemSimbolo(valor) {
    const numero = Number(valor || 0);
    return numero.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatarNumeroBR(valor) {
    const numero = Number(valor || 0);
    return numero.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatarPercentualDisplay(valor) {
    const numero = Number(valor || 0);
    return `${numero.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;
}

function parseMoeda(valor) {
    if (typeof valor === 'number') return valor;
    if (!valor) return 0;
    const normalizado = String(valor)
        .replace(/[^\d,.-]/g, '')
        .replace(/\./g, '')
        .replace(',', '.');
    const numero = Number(normalizado);
    return Number.isFinite(numero) ? numero : 0;
}

function parseNumero(valor) {
    if (typeof valor === 'number') return valor;
    if (!valor) return 0;
    const numero = Number(String(valor).replace(/[^\d,.-]/g, '').replace(/\./g, '').replace(',', '.'));
    return Number.isFinite(numero) ? numero : 0;
}

function formatarCampoMoeda(campo) {
    if (!campo) return;
    const valor = parseMoeda(campo.value);
    campo.value = valor ? formatarMoedaSemSimbolo(valor) : '';
}

function calcularTaxaMensal(taxaAnual) {
    const taxa = Number(taxaAnual || 0) / 100;
    if (taxa <= 0) return 0;
    return Math.pow(1 + taxa, 1 / 12) - 1;
}

function media(valores) {
    const validos = valores.filter((valor) => Number.isFinite(valor) && valor > 0);
    if (!validos.length) return 0;
    return validos.reduce((total, valor) => total + valor, 0) / validos.length;
}

function formatarDataBR(valor) {
    const iso = normalizarISODate(valor);
    if (!iso) return '--';
    const [ano, mes, dia] = iso.split('-');
    return `${dia}/${mes}/${ano}`;
}

function normalizarISODate(valor) {
    if (!valor) return '';
    if (valor instanceof Date) return toISODate(valor);
    return String(valor).slice(0, 10);
}

function toISODate(data) {
    const ano = data.getFullYear();
    const mes = String(data.getMonth() + 1).padStart(2, '0');
    const dia = String(data.getDate()).padStart(2, '0');
    return `${ano}-${mes}-${dia}`;
}

function adicionarMeses(dataISO, meses) {
    const iso = normalizarISODate(dataISO);
    if (!iso) return '--';
    const [ano, mes, dia] = iso.split('-').map(Number);
    const data = new Date(ano, mes - 1, dia);
    data.setMonth(data.getMonth() + meses);
    return formatarDataBR(toISODate(data));
}

function nomeMes(mes) {
    const nomes = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'];
    return nomes[Number(mes) - 1] || `Mês ${mes}`;
}

function escapeHtml(valor) {
    return escapeText(valor)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function escapeText(valor) {
    return String(valor ?? '');
}

function mostrarToast(mensagem, tipo = 'info') {
    let toast = document.getElementById('fin-toast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'fin-toast';
        toast.style.position = 'fixed';
        toast.style.right = '24px';
        toast.style.bottom = '24px';
        toast.style.zIndex = '1400';
        toast.style.padding = '12px 16px';
        toast.style.borderRadius = '6px';
        toast.style.boxShadow = '0 14px 34px rgba(15, 23, 42, 0.18)';
        toast.style.fontWeight = '700';
        document.body.appendChild(toast);
    }

    toast.textContent = mensagem;
    toast.style.background = tipo === 'erro' ? '#fee2e2' : '#eff6ff';
    toast.style.color = tipo === 'erro' ? '#991b1b' : '#1d4ed8';
    clearTimeout(toast._timer);
    toast._timer = setTimeout(() => {
        toast.remove();
    }, 4200);
}

function iconeCasa() {
    return '<svg viewBox="0 0 24 24"><path d="m3 11 9-8 9 8"/><path d="M5 10v10h14V10"/><path d="M9 20v-6h6v6"/></svg>';
}
