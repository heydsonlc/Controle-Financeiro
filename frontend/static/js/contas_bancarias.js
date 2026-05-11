const API_BASE = '/api/contas';

const estadoContas = {
    contas: [],
    filtradas: [],
    contaAtual: null,
    contaParaInativar: null,
    contaExtratoId: null,
    extratoMovimentos: []
};

const CORES_CONTA = ['#3b82f6', '#22c55e', '#14b8a6', '#7c3aed', '#f97316', '#ef4444', '#6b7280'];

document.addEventListener('DOMContentLoaded', () => {
    configurarEventos();
    carregarContas();
});

function configurarEventos() {
    const busca = document.getElementById('contas-busca');
    if (busca) {
        busca.addEventListener('input', aplicarFiltrosLocais);
    }

    ['conta-nome', 'conta-instituicao', 'conta-tipo', 'conta-agencia', 'conta-numero', 'conta-digito', 'conta-saldo-inicial'].forEach((id) => {
        const campo = document.getElementById(id);
        if (campo) {
            campo.addEventListener('input', atualizarPreviaConta);
        }
    });

    ['conta-saldo-inicial', 'transfer-valor', 'ajuste-novo-saldo', 'ajuste-valor'].forEach((id) => {
        const campo = document.getElementById(id);
        if (campo) {
            campo.addEventListener('blur', () => formatarCampoMoeda(campo));
        }
    });

    document.querySelectorAll('#conta-cor-paleta [data-color]').forEach((botao) => {
        botao.addEventListener('click', () => selecionarCorConta(botao.dataset.color));
    });
}

async function carregarContas() {
    const lista = document.getElementById('contas-lista');
    if (lista) lista.innerHTML = '<div class="contas-loading">Carregando contas...</div>';

    try {
        const status = document.getElementById('filtro-status')?.value || 'TODAS';
        estadoContas.contas = await buscarContas(status);
        aplicarFiltrosLocais();
    } catch (error) {
        console.error('Erro ao carregar contas:', error);
        if (lista) {
            lista.innerHTML = `<div class="contas-empty-state"><h3>Erro ao carregar contas.</h3><p>${escapeHtml(error.message)}</p></div>`;
        }
    }
}

async function buscarContas(status) {
    if (status === 'TODAS') {
        const [ativas, inativas] = await Promise.all([
            fetchJSON(`${API_BASE}?status=ATIVO`),
            fetchJSON(`${API_BASE}?status=INATIVO`)
        ]);
        return [...ativas.data, ...inativas.data];
    }

    const resultado = await fetchJSON(`${API_BASE}?status=${encodeURIComponent(status)}`);
    return resultado.data || [];
}

async function fetchJSON(url, options = {}) {
    const response = await fetch(url, options);
    const result = await response.json();
    if (!result.success) {
        throw new Error(result.error || result.message || 'Erro na operação');
    }
    return result;
}

function aplicarFiltrosLocais() {
    const termo = normalizarBusca(document.getElementById('contas-busca')?.value || '');

    estadoContas.filtradas = estadoContas.contas.filter((conta) => {
        if (!termo) return true;
        const alvo = [
            conta.nome,
            conta.instituicao,
            conta.tipo,
            conta.agencia,
            conta.numero_conta,
            conta.digito_conta
        ].map(normalizarBusca).join(' ');
        return alvo.includes(termo);
    });

    renderizarContas(estadoContas.filtradas);
    atualizarResumo(estadoContas.contas);
}

function renderizarContas(contas) {
    const lista = document.getElementById('contas-lista');
    const total = document.getElementById('contas-total-encontradas');

    if (total) {
        total.textContent = `${contas.length} ${contas.length === 1 ? 'conta encontrada' : 'contas encontradas'}`;
    }

    if (!lista) return;

    if (!contas.length) {
        const statusAtual = document.getElementById('filtro-status')?.value || 'TODAS';
        const termoBusca = document.getElementById('contas-busca')?.value?.trim();
        const possuiFiltroAtivo = statusAtual !== 'TODAS' || Boolean(termoBusca);
        const possuiCadastroForaDoFiltro = possuiFiltroAtivo || estadoContas.contas.length > 0;
        lista.innerHTML = `
            <div class="contas-empty-state">
                <h3>${possuiCadastroForaDoFiltro ? 'Nenhuma conta encontrada.' : 'Nenhuma conta bancária cadastrada.'}</h3>
                <p>${possuiCadastroForaDoFiltro ? 'Ajuste a busca ou os filtros para localizar a conta.' : 'Cadastre uma conta para acompanhar saldos e movimentações.'}</p>
                <button type="button" class="contas-primary-btn" onclick="abrirModalNovaConta()">Nova conta</button>
            </div>
        `;
        return;
    }

    const maiorSaldoAbsoluto = Math.max(...contas.map((conta) => Math.abs(Number(conta.saldo_atual || 0))), 1);

    lista.innerHTML = contas.map((conta) => criarLinhaConta(conta, maiorSaldoAbsoluto)).join('');
}

function criarLinhaConta(conta, maiorSaldoAbsoluto) {
    const cor = conta.cor_display || '#3b82f6';
    const saldo = Number(conta.saldo_atual || 0);
    const saldoPercentual = Math.min((Math.abs(saldo) / maiorSaldoAbsoluto) * 100, 100);
    const statusInativo = conta.status === 'INATIVO';
    const agenciaConta = formatarAgenciaConta(conta);

    return `
        <article class="conta-row ${statusInativo ? 'is-inactive' : ''}" style="--conta-cor:${escapeHtml(cor)}; --saldo-percentual:${saldoPercentual.toFixed(2)}%">
            <div class="conta-main">
                <span class="conta-bank-icon">${renderizarInstituicaoConta(conta.instituicao, { tamanho: 'lg' })}</span>
                <div class="conta-title">
                    <h3>${escapeHtml(conta.nome)}</h3>
                    <p>${escapeHtml(conta.instituicao || '-')}</p>
                    <span class="conta-status ${statusInativo ? 'inativa' : ''}">${statusInativo ? 'INATIVA' : 'ATIVA'}</span>
                </div>
            </div>

            <div class="conta-details">
                <div class="conta-detail">
                    ${renderizarInstituicaoConta(conta.instituicao, { tamanho: 'sm' })}
                    <div><span>Instituição</span><strong>${escapeHtml(conta.instituicao || '-')}</strong></div>
                </div>
                <div class="conta-detail">
                    ${contasIcon('card')}
                    <div><span>Tipo de conta</span><strong>${escapeHtml(conta.tipo || '-')}</strong></div>
                </div>
                <div class="conta-detail">
                    <span class="conta-color-dot" aria-hidden="true"></span>
                    <div><span>Agência / Conta</span><strong>${agenciaConta}</strong></div>
                </div>
            </div>

            <div class="conta-balance">
                <strong class="${saldo < 0 ? 'negative' : ''}">${formatarMoedaDisplay(saldo)}</strong>
                <small>Saldo disponível</small>
                <div class="conta-mini-bar" aria-hidden="true"><div></div></div>
            </div>

            <div class="conta-actions">
                <button type="button" class="contas-action-btn" onclick="visualizarConta(${conta.id})" title="Visualizar" aria-label="Visualizar">${contasIcon('eye')}</button>
                <button type="button" class="contas-action-btn" onclick="editarConta(${conta.id})" title="Editar" aria-label="Editar">${contasIcon('edit')}</button>
                <button type="button" class="contas-action-btn" onclick="abrirTransferencia(${conta.id})" title="Transferir" aria-label="Transferir" ${statusInativo ? 'disabled' : ''}>${contasIcon('transfer')}</button>
                <button type="button" class="contas-action-btn" onclick="abrirExtrato(${conta.id})" title="Extrato" aria-label="Extrato" ${statusInativo ? 'disabled' : ''}>${contasIcon('file')}</button>
                <button type="button" class="contas-action-btn" onclick="abrirAjusteSaldoDireto(${conta.id})" title="Ajustar saldo" aria-label="Ajustar saldo" ${statusInativo ? 'disabled' : ''}>${contasIcon('adjust')}</button>
                <button type="button" class="contas-action-btn" onclick="conferirSaldo(${conta.id})" title="Conferir saldo" aria-label="Conferir saldo">${contasIcon('check')}</button>
                ${statusInativo
                    ? `<button type="button" class="contas-action-btn" onclick="ativarConta(${conta.id})" title="Ativar" aria-label="Ativar">${contasIcon('restore')}</button>`
                    : `<button type="button" class="contas-action-btn danger" onclick="abrirModalInativar(${conta.id})" title="Inativar" aria-label="Inativar">${contasIcon('ban')}</button>`}
            </div>
        </article>
    `;
}

function atualizarResumo(contas) {
    const contasAtivas = contas.filter((conta) => conta.status === 'ATIVO');
    const totalSaldo = contasAtivas.reduce((sum, conta) => sum + Number(conta.saldo_atual || 0), 0);
    const totalContas = contas.length;
    const maiorConta = contasAtivas.reduce((maior, conta) => {
        if (!maior || Number(conta.saldo_atual || 0) > Number(maior.saldo_atual || 0)) return conta;
        return maior;
    }, null);
    const maiorSaldo = maiorConta ? Number(maiorConta.saldo_atual || 0) : 0;
    const percentualAtivas = totalContas > 0 ? (contasAtivas.length / totalContas) * 100 : 0;

    setText('saldo-total', formatarMoedaDisplay(totalSaldo));
    setText('saldo-total-percentual', totalSaldo !== 0 ? '100% do saldo disponível' : '0% do saldo disponível');
    setWidth('saldo-total-barra', totalSaldo !== 0 ? 100 : 0);
    setText('contas-ativas', String(contasAtivas.length));
    setText('contas-ativas-texto', `${contasAtivas.length} de ${totalContas} contas`);
    setWidth('contas-ativas-barra', percentualAtivas);
    setText('maior-saldo', formatarMoedaDisplay(maiorSaldo));
    setText('maior-saldo-conta', maiorConta ? maiorConta.nome : 'Nenhuma conta');
    setText('saldo-conciliado', formatarMoedaDisplay(totalSaldo));
    setText('saldo-conciliado-texto', totalSaldo !== 0 ? '100% conciliado' : 'Sem conciliação registrada');
    setWidth('saldo-conciliado-barra', totalSaldo !== 0 ? 100 : 0);
}

function abrirModalNovaConta() {
    estadoContas.contaAtual = null;
    document.getElementById('form-conta')?.reset();
    setValue('conta-id', '');
    setText('modal-titulo', 'Nova Conta Bancária');
    setText('modal-subtitulo', 'Cadastre uma nova conta para organizar e acompanhar seus saldos.');
    selecionarCorConta('#3b82f6');
    const btnInativar = document.getElementById('btn-inativar-modal');
    if (btnInativar) btnInativar.style.display = 'none';
    atualizarPreviaConta();
    abrirModal('modal-conta');
}

async function editarConta(id) {
    try {
        const result = await fetchJSON(`${API_BASE}/${id}`);
        estadoContas.contaAtual = result.data;
        preencherFormulario(result.data);
        setText('modal-titulo', 'Editar Conta Bancária');
        setText('modal-subtitulo', 'Atualize os dados cadastrais e visuais da conta.');
        const btnInativar = document.getElementById('btn-inativar-modal');
        if (btnInativar) btnInativar.style.display = result.data.status === 'ATIVO' ? 'inline-flex' : 'none';
        abrirModal('modal-conta');
    } catch (error) {
        mostrarToast(error.message, 'erro');
    }
}

function preencherFormulario(conta) {
    setValue('conta-id', conta.id);
    setValue('conta-nome', conta.nome || '');
    setSelectValuePreservingOption('conta-instituicao', conta.instituicao || '');
    setSelectValuePreservingOption('conta-tipo', conta.tipo || '');
    setValue('conta-agencia', conta.agencia || '');
    setValue('conta-numero', conta.numero_conta || '');
    setValue('conta-digito', conta.digito_conta || '');
    setValue('conta-saldo-inicial', formatarMoedaDisplay(conta.saldo_inicial || 0));
    selecionarCorConta(conta.cor_display || '#3b82f6');
    atualizarPreviaConta();
}

async function salvarConta(event) {
    event.preventDefault();

    const id = document.getElementById('conta-id')?.value;
    const payload = {
        nome: document.getElementById('conta-nome')?.value?.trim(),
        instituicao: document.getElementById('conta-instituicao')?.value,
        tipo: document.getElementById('conta-tipo')?.value,
        agencia: valorOuNull(document.getElementById('conta-agencia')?.value),
        numero_conta: valorOuNull(document.getElementById('conta-numero')?.value),
        digito_conta: valorOuNull(document.getElementById('conta-digito')?.value),
        saldo_inicial: parseMoeda(document.getElementById('conta-saldo-inicial')?.value),
        cor_display: document.getElementById('conta-cor')?.value || '#3b82f6'
    };

    try {
        const result = await fetchJSON(id ? `${API_BASE}/${id}` : API_BASE, {
            method: id ? 'PUT' : 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        fecharModal('modal-conta');
        mostrarToast(result.message || 'Conta salva com sucesso.');
        await carregarContas();
    } catch (error) {
        mostrarToast(error.message, 'erro');
    }
}

async function visualizarConta(id) {
    try {
        const [contaResult, movimentosResult] = await Promise.all([
            fetchJSON(`${API_BASE}/${id}`),
            fetchJSON(`${API_BASE}/${id}/movimentos?incluir_saldo=1&limit=5`)
        ]);
        const conta = contaResult.data;
        setText('detalhe-titulo', conta.nome);
        setText('detalhe-subtitulo', `${conta.instituicao || '-'} - ${conta.tipo || '-'}`);
        renderizarDetalheConta(conta, movimentosResult.data || []);
        abrirModal('modal-detalhe');
    } catch (error) {
        mostrarToast(error.message, 'erro');
    }
}

function renderizarDetalheConta(conta, movimentos) {
    const container = document.getElementById('detalhe-conteudo');
    if (!container) return;

    container.innerHTML = `
        <div class="contas-detail-grid">
            <div class="contas-detail-item"><span>Instituição</span><strong class="contas-institution-value">${renderizarInstituicaoConta(conta.instituicao, { tamanho: 'sm' })}${escapeHtml(conta.instituicao || '-')}</strong></div>
            <div class="contas-detail-item"><span>Tipo de conta</span><strong>${escapeHtml(conta.tipo || '-')}</strong></div>
            <div class="contas-detail-item"><span>Agência / Conta</span><strong>${formatarAgenciaConta(conta)}</strong></div>
            <div class="contas-detail-item"><span>Saldo atual</span><strong>${formatarMoedaDisplay(conta.saldo_atual || 0)}</strong></div>
            <div class="contas-detail-item"><span>Status</span><strong>${escapeHtml(conta.status || '-')}</strong></div>
            <div class="contas-detail-item"><span>Cor</span><strong>${escapeHtml(conta.cor_display || '-')}</strong></div>
        </div>
        <div class="contas-extrato-lista">
            ${movimentos.length ? movimentos.map(criarMovimentoHTML).join('') : '<div class="contas-empty-state"><p>Nenhuma movimentação encontrada.</p></div>'}
        </div>
        <div class="contas-modal-footer">
            <button type="button" class="contas-secondary-btn" onclick="abrirExtrato(${conta.id})">Abrir extrato</button>
            <button type="button" class="contas-primary-btn" onclick="abrirTransferencia(${conta.id})">Transferir</button>
        </div>
    `;
}

function abrirModalInativar(id) {
    estadoContas.contaParaInativar = id;
    abrirModal('modal-confirmar');
}

function inativarContaModal() {
    const id = document.getElementById('conta-id')?.value;
    if (!id) return;
    fecharModal('modal-conta');
    abrirModalInativar(Number(id));
}

async function confirmarInativacao() {
    if (!estadoContas.contaParaInativar) return;

    try {
        const result = await fetchJSON(`${API_BASE}/${estadoContas.contaParaInativar}`, { method: 'DELETE' });
        fecharModal('modal-confirmar');
        estadoContas.contaParaInativar = null;
        mostrarToast(result.message || 'Conta inativada com sucesso.');
        await carregarContas();
    } catch (error) {
        mostrarToast(error.message, 'erro');
    }
}

async function ativarConta(id) {
    try {
        const result = await fetchJSON(`${API_BASE}/${id}/ativar`, { method: 'PUT' });
        mostrarToast(result.message || 'Conta reativada com sucesso.');
        await carregarContas();
    } catch (error) {
        mostrarToast(error.message, 'erro');
    }
}

function abrirTransferencia(id) {
    const origem = estadoContas.contas.find((conta) => Number(conta.id) === Number(id));
    if (!origem) return;

    const destinos = estadoContas.contas.filter((conta) => conta.status === 'ATIVO' && Number(conta.id) !== Number(id));
    if (!destinos.length) {
        mostrarToast('Cadastre outra conta ativa para transferir.');
        return;
    }

    setValue('transfer-origem-id', origem.id);
    setValue('transfer-origem-nome', origem.nome);
    setValue('transfer-valor', '');
    setValue('transfer-descricao', 'Transferência entre contas');
    setValue('transfer-data', new Date().toISOString().slice(0, 10));

    const destinoSelect = document.getElementById('transfer-destino-id');
    if (destinoSelect) {
        destinoSelect.innerHTML = destinos.map((conta) => `<option value="${conta.id}">${escapeHtml(conta.nome)} - ${escapeHtml(conta.instituicao || '')}</option>`).join('');
    }

    abrirModal('modal-transferencia');
}

async function salvarTransferencia(event) {
    event.preventDefault();

    const payload = {
        conta_origem_id: Number(document.getElementById('transfer-origem-id')?.value),
        conta_destino_id: Number(document.getElementById('transfer-destino-id')?.value),
        valor: parseMoeda(document.getElementById('transfer-valor')?.value),
        data_movimento: document.getElementById('transfer-data')?.value,
        descricao: document.getElementById('transfer-descricao')?.value || 'Transferência'
    };

    try {
        const result = await fetchJSON(`${API_BASE}/transferir`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        fecharModal('modal-transferencia');
        mostrarToast(result.message || 'Transferência realizada.');
        await carregarContas();
    } catch (error) {
        mostrarToast(error.message, 'erro');
    }
}

async function abrirExtrato(contaId) {
    estadoContas.contaExtratoId = contaId;
    const lista = document.getElementById('extrato-lista');
    if (lista) lista.innerHTML = '<div class="contas-loading">Carregando extrato...</div>';
    abrirModal('modal-extrato');

    try {
        const [contaResult, movimentosResult] = await Promise.all([
            fetchJSON(`${API_BASE}/${contaId}`),
            fetchJSON(`${API_BASE}/${contaId}/movimentos?incluir_saldo=1&limit=200`)
        ]);
        estadoContas.extratoMovimentos = movimentosResult.data || [];
        setText('extrato-titulo', `Extrato - ${contaResult.data.nome}`);
        setText('extrato-saldo', formatarMoedaDisplay(contaResult.data.saldo_atual || 0));
        renderizarExtrato(estadoContas.extratoMovimentos);
    } catch (error) {
        if (lista) lista.innerHTML = `<div class="contas-empty-state"><p>${escapeHtml(error.message)}</p></div>`;
    }
}

function renderizarExtrato(movimentos) {
    const lista = document.getElementById('extrato-lista');
    if (!lista) return;

    if (!movimentos.length) {
        lista.innerHTML = '<div class="contas-empty-state"><p>Nenhuma movimentação encontrada.</p></div>';
        return;
    }

    lista.innerHTML = movimentos.map(criarMovimentoHTML).join('');
}

function criarMovimentoHTML(movimento) {
    const debito = movimento.tipo === 'DEBITO';
    const sinal = debito ? '-' : '+';
    const saldoApos = movimento.saldo_apos_movimento != null ? formatarMoedaDisplay(movimento.saldo_apos_movimento) : null;

    return `
        <article class="contas-movimento">
            <div>
                <h4>${escapeHtml(movimento.descricao || 'Movimento')}</h4>
                <p>${formatarDataBR(movimento.data_movimento)}${movimento.origem ? ` - ${escapeHtml(movimento.origem)}` : ''}</p>
            </div>
            <div class="contas-movimento-value">
                <strong class="${debito ? 'debito' : ''}">${sinal} ${formatarMoedaDisplay(movimento.valor || 0)}</strong>
                ${saldoApos ? `<small>Saldo: ${saldoApos}</small>` : ''}
                ${movimento.ajustavel ? `
                    <div class="contas-movimento-actions">
                        <button type="button" class="contas-action-btn" onclick="editarAjuste(${movimento.id})" title="Editar ajuste">${contasIcon('edit')}</button>
                        <button type="button" class="contas-action-btn danger" onclick="excluirAjuste(${movimento.id})" title="Excluir ajuste">${contasIcon('trash')}</button>
                    </div>
                ` : ''}
            </div>
        </article>
    `;
}

async function conferirSaldo(contaId) {
    const modal = document.getElementById('modal-conferencia-saldo');
    if (!modal) {
        mostrarToast('Modal de conferência não encontrado.', 'erro');
        return;
    }
    const corpo = document.getElementById('conferencia-corpo');
    if (corpo) corpo.innerHTML = '<p class="contas-loading">Verificando saldo...</p>';
    abrirModal('modal-conferencia-saldo');

    try {
        const resp = await fetch(`/api/contas/${contaId}/conferir-saldo`);
        const json = await resp.json();
        if (!json.success) throw new Error(json.error || 'Erro ao conferir saldo');
        const d = json.data;
        const consistente = d.consistente;
        const statusCls = consistente ? 'conferencia-ok' : 'conferencia-erro';
        const statusTxt = consistente ? 'Consistente' : 'Divergente';
        if (corpo) corpo.innerHTML = `
            <table class="conferencia-tabela">
                <tr><th>Saldo inicial</th><td>${formatarMoedaDisplay(d.saldo_inicial)}</td></tr>
                <tr><th>Créditos</th><td>${formatarMoedaDisplay(d.total_creditos)}</td></tr>
                <tr><th>Débitos</th><td>${formatarMoedaDisplay(d.total_debitos)}</td></tr>
                <tr><th>Saldo calculado</th><td>${formatarMoedaDisplay(d.saldo_calculado)}</td></tr>
                <tr><th>Saldo registrado</th><td>${formatarMoedaDisplay(d.saldo_atual)}</td></tr>
                <tr><th>Divergência</th><td>${formatarMoedaDisplay(d.divergencia)}</td></tr>
                <tr><th>Movimentos</th><td>${d.quantidade_movimentos}</td></tr>
            </table>
            <p class="conferencia-status ${statusCls}">Status: ${statusTxt}</p>
            ${!consistente ? '<p class="conferencia-aviso">Este diagnóstico não altera o saldo. Use ajuste de saldo apenas após conferir o extrato.</p>' : ''}
        `;
    } catch (err) {
        if (corpo) corpo.innerHTML = `<p class="contas-error">${err.message}</p>`;
    }
}

function abrirAjusteSaldoDireto(contaId) {
    const conta = (estadoContas.contas || []).find((c) => c.id === contaId);
    if (!conta) return;
    estadoContas.contaExtratoId = contaId;

    setValue('ajuste-conta-id', contaId);
    setValue('ajuste-movimento-id', '');
    setText('ajuste-titulo', 'Ajustar Saldo');
    document.getElementById('ajuste-modo-saldo-final')?.removeAttribute('hidden');
    document.getElementById('ajuste-modo-editar')?.setAttribute('hidden', 'hidden');
    setValue('ajuste-saldo-atual', formatarMoedaDisplay(conta.saldo_atual || 0));
    setValue('ajuste-novo-saldo', '');
    setValue('ajuste-valor', '');
    setValue('ajuste-tipo', 'CREDITO');
    setValue('ajuste-data', new Date().toISOString().slice(0, 10));
    setValue('ajuste-descricao', '');
    abrirModal('modal-ajuste');
}

function abrirModalAjusteSaldo() {
    if (!estadoContas.contaExtratoId) {
        mostrarToast('Abra o extrato de uma conta para ajustar o saldo.', 'erro');
        return;
    }

    setValue('ajuste-conta-id', estadoContas.contaExtratoId);
    setValue('ajuste-movimento-id', '');
    setText('ajuste-titulo', 'Ajustar Saldo');
    document.getElementById('ajuste-modo-saldo-final')?.removeAttribute('hidden');
    document.getElementById('ajuste-modo-editar')?.setAttribute('hidden', 'hidden');
    setValue('ajuste-saldo-atual', document.getElementById('extrato-saldo')?.textContent || 'R$ 0,00');
    setValue('ajuste-novo-saldo', '');
    setValue('ajuste-valor', '');
    setValue('ajuste-tipo', 'CREDITO');
    setValue('ajuste-data', new Date().toISOString().slice(0, 10));
    setValue('ajuste-descricao', '');
    abrirModal('modal-ajuste');
}

function editarAjuste(movId) {
    const movimento = estadoContas.extratoMovimentos.find((item) => Number(item.id) === Number(movId));
    if (!movimento) return;

    setValue('ajuste-conta-id', movimento.conta_bancaria_id);
    setValue('ajuste-movimento-id', movimento.id);
    setText('ajuste-titulo', 'Editar Ajuste');
    document.getElementById('ajuste-modo-saldo-final')?.setAttribute('hidden', 'hidden');
    document.getElementById('ajuste-modo-editar')?.removeAttribute('hidden');
    setValue('ajuste-saldo-atual', document.getElementById('extrato-saldo')?.textContent || 'R$ 0,00');
    setValue('ajuste-tipo', movimento.tipo);
    setValue('ajuste-valor', formatarMoedaDisplay(movimento.valor || 0));
    setValue('ajuste-data', movimento.data_movimento);
    setValue('ajuste-descricao', movimento.descricao || '');
    abrirModal('modal-ajuste');
}

async function excluirAjuste(movId) {
    if (!estadoContas.contaExtratoId) return;
    if (!window.confirm('Excluir este ajuste?')) return;

    try {
        await fetchJSON(`${API_BASE}/${estadoContas.contaExtratoId}/movimentos/${movId}`, { method: 'DELETE' });
        await abrirExtrato(estadoContas.contaExtratoId);
        await carregarContas();
    } catch (error) {
        mostrarToast(error.message, 'erro');
    }
}

async function salvarAjusteSaldo(event) {
    event.preventDefault();

    const contaId = Number(document.getElementById('ajuste-conta-id')?.value);
    const movId = document.getElementById('ajuste-movimento-id')?.value;
    const descricao = document.getElementById('ajuste-descricao')?.value || '';
    const dataMovimento = document.getElementById('ajuste-data')?.value;

    try {
        if (movId) {
            await fetchJSON(`${API_BASE}/${contaId}/movimentos/${movId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    tipo: document.getElementById('ajuste-tipo')?.value,
                    valor: parseMoeda(document.getElementById('ajuste-valor')?.value),
                    descricao,
                    data_movimento: dataMovimento
                })
            });
        } else {
            await fetchJSON(`${API_BASE}/${contaId}/ajuste-saldo`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    valor_final_desejado: parseMoeda(document.getElementById('ajuste-novo-saldo')?.value),
                    descricao,
                    data_movimento: dataMovimento
                })
            });
        }

        fecharModal('modal-ajuste');
        await abrirExtrato(contaId);
        await carregarContas();
    } catch (error) {
        mostrarToast(error.message, 'erro');
    }
}

function selecionarCorConta(cor) {
    const corNormalizada = /^#[0-9a-fA-F]{6}$/.test(cor || '') ? cor : '#3b82f6';
    setValue('conta-cor', corNormalizada);
    document.querySelectorAll('#conta-cor-paleta [data-color]').forEach((botao) => {
        botao.classList.toggle('active', botao.dataset.color === corNormalizada);
    });
    atualizarPreviaConta();
}

function atualizarPreviaConta() {
    const nome = document.getElementById('conta-nome')?.value || 'Nome da Conta';
    const tipo = document.getElementById('conta-tipo')?.value || 'Tipo de Conta';
    const instituicao = document.getElementById('conta-instituicao')?.value || '-';
    const agencia = document.getElementById('conta-agencia')?.value || '-';
    const numero = document.getElementById('conta-numero')?.value || '-';
    const digito = document.getElementById('conta-digito')?.value;
    const saldo = parseMoeda(document.getElementById('conta-saldo-inicial')?.value);
    const cor = document.getElementById('conta-cor')?.value || '#3b82f6';

    setText('preview-nome', nome);
    setText('preview-tipo', tipo);
    setText('preview-instituicao', instituicao);
    setText('preview-agencia-conta', `${agencia} / ${numero}${digito ? '-' + digito : ''}`);
    setText('preview-saldo', formatarMoedaDisplay(saldo));

    const previewInstituicao = document.getElementById('preview-instituicao-logo');
    if (previewInstituicao) {
        previewInstituicao.innerHTML = renderizarInstituicaoConta(instituicao, { tamanho: 'xl' });
    }

    ['preview-cor-icon', 'preview-cor-dot'].forEach((id) => {
        const el = document.getElementById(id);
        if (el) el.style.setProperty('--conta-cor', cor);
    });
}

function abrirModal(modalId) {
    const modal = document.getElementById(modalId);
    if (!modal) return;
    modal.classList.add('is-open');
    modal.setAttribute('aria-hidden', 'false');
}

function fecharModal(modalId) {
    const modal = document.getElementById(modalId);
    if (!modal) return;
    modal.classList.remove('is-open');
    modal.setAttribute('aria-hidden', 'true');
}

function contasIcon(name) {
    const icons = {
        bank: '<path d="m3 10 9-6 9 6"/><path d="M5 10h14M6 10v8M10 10v8M14 10v8M18 10v8M4 18h16M3 21h18"/>',
        card: '<path d="M4 7h16v10H4V7Zm0 3h16M8 15h3"/>',
        eye: '<path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z"/><path d="M12 9a3 3 0 1 1 0 6 3 3 0 0 1 0-6Z"/>',
        edit: '<path d="M5 19h4L19 9a2.1 2.1 0 0 0-3-3L6 16l-1 3Z"/><path d="M14 6l4 4"/>',
        transfer: '<path d="M16 3l5 5-5 5"/><path d="M21 8H7"/><path d="M8 21l-5-5 5-5"/><path d="M3 16h14"/>',
        file: '<path d="M7 4h7l4 4v12H7V4Z"/><path d="M14 4v4h4"/><path d="M9 13h6M9 17h6"/>',
        ban: '<path d="M6 6l12 12"/><path d="M20 12a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z"/>',
        restore: '<path d="M20 12a8 8 0 1 1-2.3-5.7"/><path d="M20 5v6h-6"/>',
        trash: '<path d="M4 7h16"/><path d="M10 11v6M14 11v6"/><path d="M6 7l1 13h10l1-13"/><path d="M9 7V4h6v3"/>',
        adjust: '<path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/><circle cx="12" cy="12" r="3"/>',
        check: '<path d="M9 12l2 2 4-4"/><path d="M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"/>'
    };
    return `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">${icons[name] || icons.bank}</svg>`;
}

function formatarAgenciaConta(conta) {
    const agencia = conta.agencia || '-';
    const numero = conta.numero_conta || '-';
    const digito = conta.digito_conta ? `-${conta.digito_conta}` : '';
    return `${escapeHtml(agencia)} / ${escapeHtml(numero)}${escapeHtml(digito)}`;
}

function renderizarInstituicaoConta(instituicao, options = {}) {
    if (window.InstituicoesUI?.renderLogo) {
        return window.InstituicoesUI.renderLogo(instituicao, {
            tipo: 'banco',
            tamanho: options.tamanho || 'md',
            mostrarLabel: Boolean(options.mostrarLabel)
        });
    }

    const nome = String(instituicao || 'Banco').trim();
    const partes = nome.split(/\s+/).filter(Boolean);
    const iniciais = partes.length > 1
        ? `${partes[0][0] || ''}${partes[1][0] || ''}`
        : nome.slice(0, 2);
    return `<span class="institution-logo institution-logo--${escapeHtml(options.tamanho || 'md')} institution-logo--default"><span class="institution-logo__mark"><span class="institution-logo__initials">${escapeHtml(iniciais.toUpperCase())}</span></span></span>`;
}

function formatarMoedaDisplay(valor) {
    return Number(valor || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}

function formatarCampoMoeda(campo) {
    const valor = parseMoeda(campo.value);
    campo.value = valor ? formatarMoedaDisplay(valor) : '';
    atualizarPreviaConta();
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

function formatarDataBR(valor) {
    if (!valor) return '';
    const iso = String(valor).slice(0, 10);
    const [ano, mes, dia] = iso.split('-');
    if (!ano || !mes || !dia) return valor;
    return `${dia}/${mes}/${ano}`;
}

function setText(id, texto) {
    const el = document.getElementById(id);
    if (el) el.textContent = texto;
}

function setValue(id, valor) {
    const el = document.getElementById(id);
    if (el) el.value = valor ?? '';
}

function setSelectValuePreservingOption(id, valor) {
    const el = document.getElementById(id);
    if (!el) return;

    const value = valor ?? '';
    if (value && !Array.from(el.options).some((option) => option.value === value)) {
        const option = new Option(value, value);
        el.add(option);
    }

    el.value = value;
}

function setWidth(id, percentual) {
    const el = document.getElementById(id);
    if (el) el.style.width = `${Math.max(0, Math.min(Number(percentual) || 0, 100))}%`;
}

function valorOuNull(valor) {
    const texto = String(valor || '').trim();
    return texto || null;
}

function normalizarBusca(valor) {
    return String(valor || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
}

function escapeHtml(valor) {
    return String(valor ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function mostrarToast(mensagem, tipo = 'info') {
    let toast = document.getElementById('contas-toast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'contas-toast';
        toast.className = 'contas-toast';
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
    toast._timer = setTimeout(() => toast.remove(), 4200);
}

window.addEventListener('click', (event) => {
    document.querySelectorAll('.contas-modal.is-open').forEach((modal) => {
        if (event.target === modal) {
            fecharModal(modal.id);
        }
    });
});
