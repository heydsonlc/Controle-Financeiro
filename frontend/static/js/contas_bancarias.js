/**
 * JavaScript para o módulo de Contas Bancárias
 */

const API_BASE = 'http://localhost:5000/api/contas';

let contaAtual = null;
let contaParaInativar = null;
let contaExtratoId = null;
let extratoMovimentos = [];

// Carregar contas ao iniciar a página
document.addEventListener('DOMContentLoaded', () => {
    carregarContas();
});

/**
 * Carrega todas as contas bancárias
 */
async function carregarContas() {
    try {
        const status = document.getElementById('filtro-status').value;
        const url = status ? `${API_BASE}?status=${status}` : `${API_BASE}?status=ATIVO`;

        const response = await fetch(url);
        const result = await response.json();

        if (result.success) {
            exibirContas(result.data);
            atualizarResumo(result.data);
        } else {
            mostrarErro('Erro ao carregar contas: ' + result.error);
        }
    } catch (error) {
        console.error('Erro ao carregar contas:', error);
        mostrarErro('Erro ao conectar com o servidor');
    }
}

/**
 * Exibe as contas na grade
 */
function exibirContas(contas) {
    const lista = document.getElementById('contas-lista');

    if (!contas || contas.length === 0) {
        lista.innerHTML = '<p class="empty-state">Nenhuma conta encontrada. Cadastre sua primeira conta!</p>';
        return;
    }

    lista.innerHTML = contas.map(conta => criarLinhaConta(conta)).join('');
}

/**
 * Cria o HTML de uma linha (lista)
 */
function criarLinhaConta(conta) {
    const saldoClass = conta.saldo_atual < 0 ? 'negativo' : '';
    const statusText = conta.status === 'INATIVO' ? 'INATIVA' : 'ATIVA';
    const statusClass = conta.status === 'INATIVO' ? 'status-inativo' : 'status-ativo';

    const instituicao = conta.instituicao || '';
    const tipo = conta.tipo || '';
    const subtitulo = [instituicao, tipo].filter(Boolean).join(' · ');

    const btnExtrato = `<button class="btn-icon" onclick="abrirExtrato(${conta.id})" title="Extrato" ${conta.status !== 'ATIVO' ? 'disabled' : ''}>📄</button>`;
    const btnEditar = `<button class="btn-icon" onclick="editarConta(${conta.id})" title="Editar">✏️</button>`;
    const btnFinal = (conta.status === 'ATIVO')
        ? `<button class="btn-icon btn-danger" onclick="abrirModalInativar(${conta.id})" title="Inativar">❌</button>`
        : `<button class="btn-icon" onclick="ativarConta(${conta.id})" title="Ativar">🔁</button>`;

    return `
        <div class="conta-row ${conta.status === 'INATIVO' ? 'inativa' : ''}">
            <div class="col-descricao">
                <div class="titulo">
                    <span class="conta-dot" style="background-color: ${conta.cor_display || '#6e6e73'}" aria-hidden="true"></span>
                    <span class="conta-nome-texto">${conta.nome}</span>
                </div>
                <div class="subtitulo">
                    ${subtitulo}
                    <span class="status ${statusClass}">${statusText}</span>
                </div>
            </div>

            <div class="col-fill"></div>

            <div class="col-direita">
                <div class="saldo ${saldoClass}">${formatarMoedaDisplay(conta.saldo_atual)}</div>
                <div class="acoes">
                    ${btnExtrato}
                    ${btnEditar}
                    ${btnFinal}
                </div>
            </div>
        </div>
    `;
}

/**
 * Cria o HTML de um card de conta
 */
function criarCardContaLegacy(conta) {
    const saldoClass = conta.saldo_atual < 0 ? 'negativo' : '';
    const statusClass = conta.status === 'INATIVO' ? 'inativo' : '';
    const statusText = conta.status === 'INATIVO' ? 'INATIVA' : 'ATIVA';

    return `
        <div class="conta-card" style="--cor-conta: ${conta.cor_display}">
            <div class="conta-header">
                <div class="conta-info">
                    <h3>${conta.nome}</h3>
                    <div class="instituicao">${conta.instituicao}</div>
                    <div class="tipo">${conta.tipo}</div>
                </div>
                <span class="conta-badge ${statusClass}">${statusText}</span>
            </div>

            ${conta.agencia || conta.numero_conta ? `
                <div class="conta-dados">
                    ${conta.agencia ? `
                        <div class="dado">
                            <span class="dado-label">Agência</span>
                            <span class="dado-valor">${conta.agencia}</span>
                        </div>
                    ` : ''}
                    ${conta.numero_conta ? `
                        <div class="dado">
                            <span class="dado-label">Conta</span>
                            <span class="dado-valor">${conta.numero_conta}${conta.digito_conta ? '-' + conta.digito_conta : ''}</span>
                        </div>
                    ` : ''}
                </div>
            ` : ''}

            <div class="conta-saldo">
                <div class="conta-saldo-label">Saldo Atual</div>
                <div class="conta-saldo-valor ${saldoClass}">
                    ${formatarMoedaDisplay(conta.saldo_atual)}
                </div>
            </div>

            <div class="conta-actions">
                ${conta.status === 'ATIVO' ? `
                    <button class="btn-extrato" onclick="abrirExtrato(${conta.id})">
                        📄 Extrato
                    </button>
                    <button class="btn-ajustar" onclick="abrirAjusteSaldo(${conta.id})">
                        ⚖ Ajustar
                    </button>
                ` : ''}
                <button class="btn-editar" onclick="editarConta(${conta.id})">
                    ✏️ Editar
                </button>
                ${conta.status === 'ATIVO' ? `
                    <button class="btn-inativar" onclick="abrirModalInativar(${conta.id})">
                        🚫 Inativar
                    </button>
                ` : `
                    <button class="btn-ativar" onclick="ativarConta(${conta.id})">
                        ✓ Ativar
                    </button>
                `}
            </div>
        </div>
    `;
}

/**
 * Atualiza os cards de resumo
 */
function atualizarResumo(contas) {
    const contasAtivas = contas.filter(c => c.status === 'ATIVO');
    const totalSaldo = contasAtivas.reduce((sum, c) => sum + c.saldo_atual, 0);
    const maiorSaldo = contasAtivas.length > 0 ?
        Math.max(...contasAtivas.map(c => c.saldo_atual)) : 0;

    document.getElementById('total-saldo').textContent = formatarMoedaDisplay(totalSaldo);
    document.getElementById('total-contas').textContent = contasAtivas.length;
    document.getElementById('maior-saldo').textContent = formatarMoedaDisplay(maiorSaldo);
}

/**
 * Abre modal para nova conta
 */
function abrirModalNovaConta() {
    contaAtual = null;
    document.getElementById('modal-titulo').textContent = 'Nova Conta Bancária';
    document.getElementById('btn-deletar-modal').style.display = 'none';
    document.getElementById('form-conta').reset();
    document.getElementById('conta-id').value = '';
    document.getElementById('conta-cor').value = '#3b82f6';
    abrirModal('modal-conta');
}

/**
 * Edita uma conta existente
 */
async function editarConta(id) {
    try {
        const response = await fetch(`${API_BASE}/${id}`);
        const result = await response.json();

        if (result.success) {
            contaAtual = result.data;
            preencherFormulario(result.data);
            document.getElementById('modal-titulo').textContent = 'Editar Conta Bancária';
            document.getElementById('btn-deletar-modal').style.display = 'block';
            abrirModal('modal-conta');
        } else {
            mostrarErro('Erro ao carregar conta: ' + result.error);
        }
    } catch (error) {
        console.error('Erro ao carregar conta:', error);
        mostrarErro('Erro ao conectar com o servidor');
    }
}

/**
 * Preenche o formulário com os dados da conta
 */
function preencherFormulario(conta) {
    document.getElementById('conta-id').value = conta.id;
    document.getElementById('conta-nome').value = conta.nome;
    document.getElementById('conta-instituicao').value = conta.instituicao;
    document.getElementById('conta-tipo').value = conta.tipo;
    document.getElementById('conta-agencia').value = conta.agencia || '';
    document.getElementById('conta-numero').value = conta.numero_conta || '';
    document.getElementById('conta-digito').value = conta.digito_conta || '';
    document.getElementById('conta-saldo-inicial').value = formatarMoedaDisplay(conta.saldo_inicial);
    document.getElementById('conta-cor').value = conta.cor_display || '#3b82f6';
}

/**
 * Salva a conta (criar ou atualizar)
 */
async function salvarConta(event) {
    event.preventDefault();

    const id = document.getElementById('conta-id').value;
    const dados = {
        nome: document.getElementById('conta-nome').value,
        instituicao: document.getElementById('conta-instituicao').value,
        tipo: document.getElementById('conta-tipo').value,
        agencia: document.getElementById('conta-agencia').value || null,
        numero_conta: document.getElementById('conta-numero').value || null,
        digito_conta: document.getElementById('conta-digito').value || null,
        saldo_inicial: parseMoeda(document.getElementById('conta-saldo-inicial').value),
        cor_display: document.getElementById('conta-cor').value
    };

    try {
        const url = id ? `${API_BASE}/${id}` : API_BASE;
        const method = id ? 'PUT' : 'POST';

        const response = await fetch(url, {
            method: method,
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(dados)
        });

        const result = await response.json();

        if (result.success) {
            mostrarSucesso(result.message);
            fecharModal('modal-conta');
            carregarContas();
        } else {
            mostrarErro('Erro ao salvar conta: ' + result.error);
        }
    } catch (error) {
        console.error('Erro ao salvar conta:', error);
        mostrarErro('Erro ao conectar com o servidor');
    }
}

/**
 * Abre modal de confirmação para inativar
 */
function abrirModalInativar(id) {
    contaParaInativar = id;
    abrirModal('modal-confirmar');
}

/**
 * Inativar conta via modal de edição
 */
function inativarContaModal() {
    const id = document.getElementById('conta-id').value;
    if (id) {
        abrirModalInativar(id);
        fecharModal('modal-conta');
    }
}

/**
 * Confirma a inativação da conta
 */
async function confirmarInativacao() {
    if (!contaParaInativar) return;

    try {
        const response = await fetch(`${API_BASE}/${contaParaInativar}`, {
            method: 'DELETE'
        });

        const result = await response.json();

        if (result.success) {
            mostrarSucesso('Conta inativada com sucesso');
            fecharModal('modal-confirmar');
            contaParaInativar = null;
            carregarContas();
        } else {
            mostrarErro('Erro ao inativar conta: ' + result.error);
        }
    } catch (error) {
        console.error('Erro ao inativar conta:', error);
        mostrarErro('Erro ao conectar com o servidor');
    }
}

/**
 * Ativar uma conta inativa
 */
async function ativarConta(id) {
    try {
        const response = await fetch(`${API_BASE}/${id}/ativar`, {
            method: 'PUT'
        });

        const result = await response.json();

        if (result.success) {
            mostrarSucesso('Conta reativada com sucesso');
            carregarContas();
        } else {
            mostrarErro('Erro ao ativar conta: ' + result.error);
        }
    } catch (error) {
        console.error('Erro ao ativar conta:', error);
        mostrarErro('Erro ao conectar com o servidor');
    }
}

/**
 * Abre um modal
 */
function abrirModal(modalId) {
    document.getElementById(modalId).style.display = 'block';
}

/**
 * Fecha um modal
 */
function fecharModal(modalId) {
    document.getElementById(modalId).style.display = 'none';
}

// ============================================================================
// EXTRATO / AJUSTE DE SALDO
// ============================================================================

async function abrirExtrato(contaId) {
    contaExtratoId = contaId;
    document.getElementById('extrato-lista').innerHTML = '<p class="loading">Carregando extrato...</p>';
    abrirModal('modal-extrato');

    try {
        const [respConta, respMov] = await Promise.all([
            fetch(`${API_BASE}/${contaId}`),
            fetch(`${API_BASE}/${contaId}/movimentos?incluir_saldo=1&limit=200`)
        ]);
        const [jsonConta, jsonMov] = await Promise.all([respConta.json(), respMov.json()]);

        if (!jsonConta.success) throw new Error(jsonConta.error || 'Erro ao carregar conta');
        if (!jsonMov.success) throw new Error(jsonMov.error || 'Erro ao carregar extrato');

        const conta = jsonConta.data;
        extratoMovimentos = jsonMov.data || [];

        document.getElementById('extrato-titulo').textContent = `Extrato — ${conta.nome}`;
        document.getElementById('extrato-saldo').textContent = formatarMoedaDisplay(conta.saldo_atual);
        renderizarExtrato(extratoMovimentos);
    } catch (e) {
        console.error(e);
        document.getElementById('extrato-lista').innerHTML = `<p class="empty-state">Erro ao carregar extrato</p>`;
    }
}

function renderizarExtrato(movimentos) {
    const lista = document.getElementById('extrato-lista');
    if (!movimentos || movimentos.length === 0) {
        lista.innerHTML = '<p class="empty-state">Nenhum movimento encontrado</p>';
        return;
    }

    lista.innerHTML = movimentos.map(m => {
        const tipoClass = m.tipo === 'DEBITO' ? 'debito' : 'credito';
        const sinal = m.tipo === 'DEBITO' ? '-' : '+';
        const tag = (m.origem === 'AJUSTE') ? 'AJUSTE' : (m.origem || '');
        const meta = `${formatarDataBR(m.data_movimento)}${tag ? ' · ' + tag : ''}`;
        const saldoApos = (m.saldo_apos_movimento != null) ? formatarMoedaDisplay(m.saldo_apos_movimento) : null;

        const acoes = (m.ajustavel)
            ? `<div class="acoes">
                    <button onclick="editarAjuste(${m.id})">✏️</button>
                    <button onclick="excluirAjuste(${m.id})">🗑️</button>
               </div>`
            : '';

        return `
            <div class="movimento">
                <div class="mov-desc">
                    <div class="titulo">${m.descricao}</div>
                    <div class="meta">${meta}</div>
                </div>
                <div class="mov-valor">
                    <div class="valor ${tipoClass}">${sinal} ${formatarMoedaDisplay(m.valor)}</div>
                    ${saldoApos ? `<div class="saldo-apos">Saldo: ${saldoApos}</div>` : ''}
                    ${acoes}
                </div>
            </div>
        `;
    }).join('');
}

function abrirAjusteSaldo(contaId) {
    contaExtratoId = contaId;
    abrirModalAjusteSaldo();
}

function abrirModalAjusteSaldo() {
    const hoje = new Date().toISOString().split('T')[0];
    document.getElementById('ajuste-conta-id').value = contaExtratoId || '';
    document.getElementById('ajuste-movimento-id').value = '';
    document.getElementById('ajuste-titulo').textContent = 'Ajustar Saldo';
    document.getElementById('ajuste-modo-saldo-final').style.display = 'block';
    document.getElementById('ajuste-modo-editar').style.display = 'none';
    document.getElementById('ajuste-data').value = hoje;
    document.getElementById('ajuste-descricao').value = '';
    document.getElementById('ajuste-novo-saldo').value = '';
    document.getElementById('ajuste-valor').value = '';
    document.getElementById('ajuste-tipo').value = 'CREDITO';

    // saldo atual exibido
    const saldoAtualTexto = document.getElementById('extrato-saldo')?.textContent || 'R$ 0,00';
    document.getElementById('ajuste-saldo-atual').value = saldoAtualTexto;

    abrirModal('modal-ajuste');
}

function editarAjuste(movId) {
    const mov = (extratoMovimentos || []).find(m => m.id === movId);
    if (!mov) return;

    contaExtratoId = mov.conta_bancaria_id;
    document.getElementById('ajuste-conta-id').value = contaExtratoId;
    document.getElementById('ajuste-movimento-id').value = mov.id;
    document.getElementById('ajuste-titulo').textContent = 'Editar Ajuste';
    document.getElementById('ajuste-modo-saldo-final').style.display = 'none';
    document.getElementById('ajuste-modo-editar').style.display = 'block';

    document.getElementById('ajuste-saldo-atual').value = document.getElementById('extrato-saldo')?.textContent || 'R$ 0,00';
    document.getElementById('ajuste-data').value = mov.data_movimento;
    document.getElementById('ajuste-descricao').value = mov.descricao || '';
    document.getElementById('ajuste-tipo').value = mov.tipo;
    document.getElementById('ajuste-valor').value = formatarMoedaDisplay(mov.valor);

    abrirModal('modal-ajuste');
}

async function excluirAjuste(movId) {
    if (!contaExtratoId) return;
    if (!confirm('Excluir este ajuste?')) return;

    try {
        const resp = await fetch(`${API_BASE}/${contaExtratoId}/movimentos/${movId}`, { method: 'DELETE' });
        const json = await resp.json();
        if (!json.success) throw new Error(json.error || 'Erro ao excluir ajuste');
        await abrirExtrato(contaExtratoId);
    } catch (e) {
        console.error(e);
        mostrarErro('Erro ao excluir ajuste: ' + e.message);
    }
}

async function salvarAjusteSaldo(event) {
    event.preventDefault();
    const contaId = parseInt(document.getElementById('ajuste-conta-id').value, 10);
    const movId = document.getElementById('ajuste-movimento-id').value;
    const dataMov = document.getElementById('ajuste-data').value;
    const descricao = document.getElementById('ajuste-descricao').value || '';

    try {
        if (!contaId) throw new Error('Conta inválida');

        if (movId) {
            const payload = {
                tipo: document.getElementById('ajuste-tipo').value,
                valor: parseMoeda(document.getElementById('ajuste-valor').value),
                descricao,
                data_movimento: dataMov
            };
            const resp = await fetch(`${API_BASE}/${contaId}/movimentos/${movId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const json = await resp.json();
            if (!json.success) throw new Error(json.error || 'Erro ao editar ajuste');
        } else {
            const payload = {
                valor_final_desejado: parseMoeda(document.getElementById('ajuste-novo-saldo').value),
                descricao,
                data_movimento: dataMov
            };
            const resp = await fetch(`${API_BASE}/${contaId}/ajuste-saldo`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const json = await resp.json();
            if (!json.success) throw new Error(json.error || 'Erro ao criar ajuste');
        }

        fecharModal('modal-ajuste');
        await abrirExtrato(contaId);
        await carregarContas();
    } catch (e) {
        console.error(e);
        mostrarErro('Erro ao salvar ajuste: ' + e.message);
    }
}

function formatarDataBR(valor) {
    if (!valor) return '';
    const [ano, mes, dia] = valor.slice(0, 10).split('-');
    return `${dia}/${mes}/${ano}`;
}

/**
 * Formata valor monetário para exibição
 */
function formatarMoedaDisplay(valor) {
    return new Intl.NumberFormat('pt-BR', {
        style: 'currency',
        currency: 'BRL'
    }).format(valor);
}

/**
 * Formata input de moeda
 */
function formatarMoeda(input) {
    let valor = input.value.replace(/\D/g, '');
    valor = (parseInt(valor) / 100).toFixed(2);
    input.value = 'R$ ' + valor.replace('.', ',').replace(/(\d)(?=(\d{3})+\,)/g, '$1.');
}

/**
 * Converte string de moeda para número
 */
function parseMoeda(valor) {
    if (!valor) return 0;
    return parseFloat(valor.replace('R$', '').replace(/\./g, '').replace(',', '.').trim());
}

/**
 * Mostra mensagem de sucesso
 */
function mostrarSucesso(mensagem) {
    alert(mensagem);
}

/**
 * Mostra mensagem de erro
 */
function mostrarErro(mensagem) {
    alert(mensagem);
}

// Fechar modal ao clicar fora
window.onclick = function (event) {
    const modals = document.getElementsByClassName('modal');
    for (let modal of modals) {
        if (event.target == modal) {
            modal.style.display = 'none';
        }
    }
}
