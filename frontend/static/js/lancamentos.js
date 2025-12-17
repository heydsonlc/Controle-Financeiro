/**
 * Sistema de Lançamentos - Controle Financeiro
 * Permite registrar gastos centralizadamente
 */

// Estado global da aplicação
const state = {
    lancamentos: [],
    cartoes: [],
    categorias: {}, // Mapa: cartaoId -> [categorias]
    contasBancarias: [],
    filtros: {
        mes: null,
        cartao: null,
        categoria: null
    }
};

// ===================================
// INICIALIZAÇÃO
// ===================================

document.addEventListener('DOMContentLoaded', () => {
    inicializarFiltros();
    carregarCartoes();
    carregarCategoriasGerais();
    carregarContasBancarias();
    carregarLancamentos();
    carregarReceitasPendentes(); // Carregar receitas pendentes
});

function inicializarFiltros() {
    const hoje = new Date();
    const mesAtual = `${hoje.getFullYear()}-${String(hoje.getMonth() + 1).padStart(2, '0')}`;

    document.getElementById('filtro-mes').value = mesAtual;
    document.getElementById('lancamento-data').value = hoje.toISOString().split('T')[0];
    document.getElementById('lancamento-mes-fatura').value = mesAtual;

    state.filtros.mes = mesAtual;

    // Listeners de filtros
    document.getElementById('filtro-mes').addEventListener('change', aplicarFiltros);
    document.getElementById('filtro-cartao').addEventListener('change', aplicarFiltros);
    document.getElementById('filtro-categoria').addEventListener('change', aplicarFiltros);
}

// ===================================
// CARREGAR DADOS
// ===================================

async function carregarCartoes() {
    try {
        const response = await fetch('/api/cartoes');
        const cartoes = await response.json();

        state.cartoes = cartoes;

        // Popular selects de filtro
        const selectFiltro = document.getElementById('filtro-cartao');
        const selectLancamento = document.getElementById('lancamento-cartao');

        [selectFiltro, selectLancamento].forEach(select => {
            const placeholder = select.querySelector('option[value=""]');
            select.innerHTML = '';
            if (placeholder) select.appendChild(placeholder);

            cartoes.forEach(cartao => {
                const option = document.createElement('option');
                option.value = cartao.id;
                option.textContent = cartao.nome;
                select.appendChild(option);
            });
        });

        // Carregar todas as categorias de todos os cartões para o filtro
        await carregarTodasCategorias();

    } catch (error) {
        console.error('Erro ao carregar cartões:', error);
        mostrarErro('Erro ao carregar cartões');
    }
}

async function carregarTodasCategorias() {
    try {
        const selectCategoria = document.getElementById('filtro-categoria');
        const todasCategorias = [];

        // Buscar categorias de todos os cartões
        for (const cartao of state.cartoes) {
            const response = await fetch(`/api/cartoes/${cartao.id}/itens`);
            const categorias = await response.json();

            categorias.forEach(cat => {
                // Adicionar cartão_nome para identificação
                todasCategorias.push({
                    ...cat,
                    cartao_id: cartao.id,
                    cartao_nome: cartao.nome
                });
            });
        }

        // Popular select de categoria
        selectCategoria.innerHTML = '<option value="">Todas as categorias</option>';
        todasCategorias.forEach(cat => {
            const option = document.createElement('option');
            option.value = cat.id;
            option.textContent = `${cat.nome} (${cat.cartao_nome})`;
            selectCategoria.appendChild(option);
        });

    } catch (error) {
        console.error('Erro ao carregar categorias:', error);
    }
}

async function carregarCategoriasGerais() {
    try {
        const response = await fetch('/api/categorias');
        const result = await response.json();
        const categorias = result.data || result; // Suporta tanto { data: [] } quanto []

        const selectCategoria = document.getElementById('lancamento-categoria-geral');
        selectCategoria.innerHTML = '<option value="">Selecione uma categoria...</option>';

        categorias.forEach(cat => {
            const option = document.createElement('option');
            option.value = cat.id;
            option.textContent = cat.nome;
            selectCategoria.appendChild(option);
        });
    } catch (error) {
        console.error('Erro ao carregar categorias gerais:', error);
        mostrarErro('Erro ao carregar categorias gerais');
    }
}

async function carregarContasBancarias() {
    try {
        const response = await fetch('/api/contas');
        const result = await response.json();
        const contas = result.data || result;

        state.contasBancarias = contas;

        const selectConta = document.getElementById('lancamento-conta-bancaria');
        selectConta.innerHTML = '<option value="">Selecione uma conta...</option>';

        contas.forEach(conta => {
            const option = document.createElement('option');
            option.value = conta.id;
            option.textContent = `${conta.nome} - ${conta.banco}`;
            selectConta.appendChild(option);
        });
    } catch (error) {
        console.error('Erro ao carregar contas bancárias:', error);
        mostrarErro('Erro ao carregar contas bancárias');
    }
}

async function carregarCategoriasPorCartao() {
    const cartaoId = document.getElementById('lancamento-cartao').value;
    const selectCategoriaDespesa = document.getElementById('lancamento-categoria-despesa-cartao');
    const selectItemAgregado = document.getElementById('lancamento-item-agregado');

    if (!cartaoId) {
        selectItemAgregado.disabled = true;
        selectItemAgregado.innerHTML = '<option value="">Selecione um cartão primeiro...</option>';
        return;
    }

    try {
        // 1. Carregar CATEGORIAS DE DESPESA (analíticas) - sempre disponíveis
        if (!state.categoriasDespesa) {
            const response = await fetch('/api/categorias');
            const data = await response.json();
            console.log('📊 Categorias recebidas:', data);
            // Garantir que seja um array
            state.categoriasDespesa = Array.isArray(data) ? data : (data.categorias || []);
            console.log('📊 Categorias processadas:', state.categoriasDespesa);
        }

        selectCategoriaDespesa.innerHTML = '<option value="">Selecione uma categoria...</option>';
        if (Array.isArray(state.categoriasDespesa) && state.categoriasDespesa.length > 0) {
            state.categoriasDespesa.forEach(cat => {
                // Remover filtro de ativo temporariamente para debug
                const option = document.createElement('option');
                option.value = cat.id;
                option.textContent = `${cat.nome}${cat.ativo === false ? ' (inativa)' : ''}`;
                selectCategoriaDespesa.appendChild(option);
                console.log('✅ Adicionada categoria:', cat.nome);
            });
        } else {
            console.error('❌ Nenhuma categoria encontrada!', state.categoriasDespesa);
        }

        // 2. Carregar CATEGORIAS DO CARTÃO (ItemAgregado) - opcional
        if (!state.categorias[cartaoId]) {
            const response = await fetch(`/api/cartoes/${cartaoId}/itens`);
            const categorias = await response.json();
            state.categorias[cartaoId] = categorias;
        }

        const categoriasCartao = state.categorias[cartaoId];

        selectItemAgregado.disabled = false;
        selectItemAgregado.innerHTML = '<option value="">Sem categoria (não controla limite)</option>';

        categoriasCartao.forEach(cat => {
            const option = document.createElement('option');
            option.value = cat.id;
            option.textContent = cat.nome;
            selectItemAgregado.appendChild(option);
        });

    } catch (error) {
        console.error('Erro ao carregar categorias:', error);
        mostrarErro('Erro ao carregar categorias');
    }
}

async function carregarLancamentos() {
    try {
        const lancamentos = [];

        // 1. Buscar lançamentos de cartões de crédito
        for (const cartao of state.cartoes) {
            const response = await fetch(`/api/cartoes/${cartao.id}/itens`);
            const itens = await response.json();

            for (const item of itens) {
                const respLanc = await fetch(`/api/cartoes/itens/${item.id}/lancamentos`);
                const lancsItem = await respLanc.json();

                lancsItem.forEach(lanc => {
                    lancamentos.push({
                        ...lanc,
                        tipo: 'cartao',
                        cartao_id: cartao.id,
                        cartao_nome: cartao.nome,
                        categoria_id: item.id,
                        categoria_nome: item.nome,
                        data_compra: lanc.data_compra,
                        mes_fatura: lanc.mes_fatura
                    });
                });
            }
        }

        // 2. Buscar despesas diretas (tipo Simples)
        const respDespesas = await fetch('/api/despesas/');
        const resultDespesas = await respDespesas.json();
        const despesas = resultDespesas.data || resultDespesas; // Suporta tanto { data: [] } quanto []

        despesas.forEach(desp => {
            if (desp.tipo === 'Simples' && desp.pago) {
                lancamentos.push({
                    id: desp.id,
                    tipo: 'direto',
                    descricao: desp.nome,
                    valor: desp.valor,
                    data_compra: desp.data_pagamento || desp.data_vencimento,
                    mes_fatura: desp.mes_competencia,
                    categoria_id: desp.categoria_id,
                    categoria_nome: desp.categoria?.nome || 'Sem categoria',
                    observacoes: desp.descricao,
                    numero_parcela: 1,
                    total_parcelas: 1
                });
            }
        });

        // 3. Buscar receitas pontuais (créditos/entradas)
        const respReceitas = await fetch('/api/receitas/realizadas');
        const resultReceitas = await respReceitas.json();

        if (resultReceitas.success && resultReceitas.data) {
            resultReceitas.data.forEach(rec => {
                // Apenas receitas pontuais (sem orcamento_id)
                if (!rec.orcamento_id) {
                    const conta = state.contasBancarias.find(c => c.id === rec.conta_origem_id);
                    lancamentos.push({
                        id: rec.id,
                        tipo: 'credito',
                        descricao: rec.descricao || 'Receita Pontual',
                        valor: rec.valor_recebido,
                        data_compra: rec.data_recebimento,
                        mes_fatura: rec.mes_referencia,
                        categoria_nome: conta ? conta.nome : 'Conta',
                        observacoes: rec.observacoes,
                        numero_parcela: 1,
                        total_parcelas: 1
                    });
                }
            });
        }

        state.lancamentos = lancamentos.sort((a, b) =>
            new Date(b.data_compra) - new Date(a.data_compra)
        );

        aplicarFiltros();

    } catch (error) {
        console.error('Erro ao carregar lançamentos:', error);
        mostrarErro('Erro ao carregar lançamentos');
    }
}

// ===================================
// RENDERIZAÇÃO
// ===================================

function aplicarFiltros() {
    const mesFiltro = document.getElementById('filtro-mes').value;
    const cartaoFiltro = document.getElementById('filtro-cartao').value;
    const categoriaFiltro = document.getElementById('filtro-categoria').value;

    let lancamentosFiltrados = state.lancamentos;

    // Filtrar por mês
    if (mesFiltro) {
        lancamentosFiltrados = lancamentosFiltrados.filter(l =>
            l.mes_fatura && l.mes_fatura.startsWith(mesFiltro)
        );
    }

    // Filtrar por cartão
    if (cartaoFiltro) {
        lancamentosFiltrados = lancamentosFiltrados.filter(l =>
            l.cartao_id == cartaoFiltro
        );
    }

    // Filtrar por categoria
    if (categoriaFiltro) {
        lancamentosFiltrados = lancamentosFiltrados.filter(l =>
            l.categoria_id == categoriaFiltro
        );
    }

    renderizarLancamentos(lancamentosFiltrados);
    atualizarResumoMes(lancamentosFiltrados);
}

function renderizarLancamentos(lancamentos) {
    const container = document.getElementById('lista-lancamentos');

    if (lancamentos.length === 0) {
        container.innerHTML = '<p class="empty-state">Nenhum lançamento encontrado para os filtros selecionados.</p>';
        return;
    }

    container.innerHTML = lancamentos.map(lanc => {
        const isCartao = lanc.tipo === 'cartao';
        const isCredito = lanc.tipo === 'credito';

        let tipoIcon, tipoTexto;
        if (isCartao) {
            tipoIcon = '💳';
            tipoTexto = 'Cartão';
        } else if (isCredito) {
            tipoIcon = '💰';
            tipoTexto = 'Entrada';
        } else {
            tipoIcon = '💵';
            tipoTexto = 'Direto';
        }

        return `
        <div class="lancamento-card ${isCredito ? 'lancamento-credito' : ''}">
            <div class="lancamento-row-1">
                <div class="lancamento-principal">
                    <h3 class="lancamento-nome">${lanc.descricao}</h3>
                    <span class="lancamento-data">${formatarData(lanc.data_compra)}</span>
                </div>
                <div class="lancamento-badges">
                    <span class="badge badge-tipo-${lanc.tipo}">${tipoIcon} ${tipoTexto}</span>
                    ${isCartao ? `<span class="badge badge-cartao">${lanc.cartao_nome}</span>` : ''}
                    <span class="badge badge-categoria">${lanc.categoria_nome}</span>
                </div>
                <div class="lancamento-valor ${isCredito ? 'valor-positivo' : ''}">
                    ${isCredito ? '+' : ''}R$ ${parseFloat(lanc.valor).toLocaleString('pt-BR', {minimumFractionDigits: 2})}
                </div>
            </div>
            <div class="lancamento-row-2">
                <div class="lancamento-info-extra">
                    ${isCartao ? `<span class="info-item">Fatura: ${formatarMes(lanc.mes_fatura)}</span>` : ''}
                    ${lanc.total_parcelas > 1 ? `<span class="info-item">Parcela ${lanc.numero_parcela}/${lanc.total_parcelas}</span>` : ''}
                    ${lanc.observacoes ? `<span class="info-item obs">${lanc.observacoes}</span>` : ''}
                </div>
                <div class="lancamento-actions">
                    <button class="btn-icon" onclick='editarLancamento(${JSON.stringify(lanc).replace(/'/g, "&#39;")})' title="Editar">
                        ✏️
                    </button>
                    <button class="btn-icon btn-delete" onclick="excluirLancamento(${lanc.id}, '${lanc.tipo}')" title="Excluir">
                        ×
                    </button>
                </div>
            </div>
        </div>
        `;
    }).join('');
}

function atualizarResumoMes(lancamentos) {
    const total = lancamentos.reduce((sum, lanc) => sum + parseFloat(lanc.valor), 0);
    document.getElementById('total-mes').textContent =
        `R$ ${total.toLocaleString('pt-BR', {minimumFractionDigits: 2})}`;
}

// ===================================
// MODAL E FORMULÁRIO
// ===================================

function abrirModalLancamento() {
    document.getElementById('modal-lancamento-titulo').textContent = 'Novo Lançamento';
    document.getElementById('form-lancamento').reset();
    document.getElementById('lancamento-id').value = '';

    // Resetar visibilidade dos campos
    document.getElementById('campos-cartao').style.display = 'none';
    document.getElementById('campos-direto').style.display = 'none';
    document.getElementById('campos-credito').style.display = 'none';

    const hoje = new Date();
    document.getElementById('lancamento-data').value = hoje.toISOString().split('T')[0];
    document.getElementById('lancamento-mes-fatura').value = state.filtros.mes ||
        `${hoje.getFullYear()}-${String(hoje.getMonth() + 1).padStart(2, '0')}`;

    abrirModal('modal-lancamento');
}

function alternarTipoLancamento() {
    const tipo = document.getElementById('lancamento-tipo').value;
    const camposCartao = document.getElementById('campos-cartao');
    const camposDireto = document.getElementById('campos-direto');
    const camposCredito = document.getElementById('campos-credito');
    const campoMesFatura = document.getElementById('lancamento-mes-fatura').parentElement.parentElement;
    const campoParcelas = document.getElementById('lancamento-parcelas').parentElement;

    if (tipo === 'cartao') {
        camposCartao.style.display = 'block';
        camposDireto.style.display = 'none';
        camposCredito.style.display = 'none';
        campoMesFatura.style.display = 'grid';
        campoParcelas.style.display = 'block';
    } else if (tipo === 'direto') {
        camposCartao.style.display = 'none';
        camposDireto.style.display = 'block';
        camposCredito.style.display = 'none';
        campoMesFatura.style.display = 'none';
        campoParcelas.style.display = 'none';
    } else if (tipo === 'credito') {
        camposCartao.style.display = 'none';
        camposDireto.style.display = 'none';
        camposCredito.style.display = 'block';
        campoMesFatura.style.display = 'none';
        campoParcelas.style.display = 'none';
    } else {
        camposCartao.style.display = 'none';
        camposDireto.style.display = 'none';
        camposCredito.style.display = 'none';
    }
}

async function salvarLancamento(event) {
    event.preventDefault();

    const tipo = document.getElementById('lancamento-tipo').value;

    if (tipo === 'cartao') {
        await salvarLancamentoCartao();
    } else if (tipo === 'direto') {
        await salvarLancamentoDireto();
    } else if (tipo === 'credito') {
        await salvarLancamentoCredito();
    } else {
        mostrarErro('Selecione o tipo de lançamento');
    }
}

async function salvarLancamentoCartao() {
    const categoriaId = document.getElementById('lancamento-categoria-cartao').value;

    if (!categoriaId) {
        mostrarErro('Selecione uma categoria');
        return;
    }

    const dados = {
        descricao: document.getElementById('lancamento-descricao').value,
        valor: parseFloat(document.getElementById('lancamento-valor').value),
        data_compra: document.getElementById('lancamento-data').value,
        mes_fatura: document.getElementById('lancamento-mes-fatura').value,
        numero_parcela: 1,
        total_parcelas: parseInt(document.getElementById('lancamento-parcelas').value) || 1,
        observacoes: document.getElementById('lancamento-observacoes').value
    };

    try {
        const url = `/api/cartoes/itens/${categoriaId}/lancamentos`;
        const response = await fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(dados)
        });

        if (!response.ok) throw new Error('Erro ao salvar lançamento');

        fecharModal('modal-lancamento');
        await carregarLancamentos();
        mostrarSucesso('Lançamento em cartão salvo com sucesso!');

    } catch (error) {
        console.error('Erro ao salvar lançamento:', error);
        mostrarErro('Erro ao salvar lançamento no cartão');
    }
}

async function salvarLancamentoDireto() {
    const categoriaId = document.getElementById('lancamento-categoria-geral').value;

    if (!categoriaId) {
        mostrarErro('Selecione uma categoria');
        return;
    }

    const lancamentoId = document.getElementById('lancamento-id').value;
    const isEdicao = lancamentoId && document.getElementById('lancamento-id').dataset.tipo === 'direto';

    const dataCompra = document.getElementById('lancamento-data').value;
    const dados = {
        categoria_id: parseInt(categoriaId),
        nome: document.getElementById('lancamento-descricao').value,
        tipo: 'Simples',
        descricao: document.getElementById('lancamento-observacoes').value || '',
        valor: parseFloat(document.getElementById('lancamento-valor').value),
        data_vencimento: dataCompra,
        data_pagamento: dataCompra,
        pago: true,
        recorrente: false,
        mes_competencia: dataCompra.substring(0, 7) + '-01'
    };

    try {
        const url = isEdicao ? `/api/despesas/${lancamentoId}` : '/api/despesas/';
        const method = isEdicao ? 'PUT' : 'POST';

        const response = await fetch(url, {
            method: method,
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(dados)
        });

        if (!response.ok) throw new Error('Erro ao salvar despesa');

        fecharModal('modal-lancamento');
        await carregarLancamentos();
        mostrarSucesso(isEdicao ? 'Despesa direta atualizada com sucesso!' : 'Despesa direta salva com sucesso!');

    } catch (error) {
        console.error('Erro ao salvar despesa:', error);
        mostrarErro('Erro ao salvar despesa direta');
    }
}

async function salvarLancamentoCredito() {
    const contaBancariaId = document.getElementById('lancamento-conta-bancaria').value;

    if (!contaBancariaId) {
        mostrarErro('Selecione uma conta bancária');
        return;
    }

    const dataRecebimento = document.getElementById('lancamento-data').value;
    const dados = {
        conta_bancaria_id: parseInt(contaBancariaId),
        descricao: document.getElementById('lancamento-descricao').value,
        valor_recebido: parseFloat(document.getElementById('lancamento-valor').value),
        data_recebimento: dataRecebimento,
        competencia: dataRecebimento.substring(0, 7) + '-01',
        observacoes: document.getElementById('lancamento-observacoes').value || '',
        tipo_entrada: 'RECEITA_PONTUAL'
    };

    try {
        const response = await fetch('/api/receitas/realizadas/pontual', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(dados)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Erro ao salvar entrada');
        }

        fecharModal('modal-lancamento');
        await carregarLancamentos();
        mostrarSucesso('Entrada/Crédito registrado com sucesso!');

    } catch (error) {
        console.error('Erro ao salvar entrada:', error);
        mostrarErro(error.message || 'Erro ao salvar entrada');
    }
}

function editarLancamento(lancamento) {
    // Alterar título do modal
    document.getElementById('modal-lancamento-titulo').textContent = 'Editar Lançamento';

    // Limpar formulário
    document.getElementById('form-lancamento').reset();

    // Armazenar dados do lançamento para edição
    document.getElementById('lancamento-id').value = lancamento.id;
    document.getElementById('lancamento-id').dataset.tipo = lancamento.tipo;

    // Preencher campos comuns
    document.getElementById('lancamento-descricao').value = lancamento.descricao;
    document.getElementById('lancamento-valor').value = lancamento.valor;
    document.getElementById('lancamento-data').value = lancamento.data_compra;
    document.getElementById('lancamento-observacoes').value = lancamento.observacoes || '';

    // Configurar por tipo
    if (lancamento.tipo === 'direto') {
        // Despesa direta
        document.getElementById('lancamento-tipo').value = 'direto';
        alternarTipoLancamento();

        // Aguardar um pouco para as categorias carregarem, depois selecionar
        setTimeout(() => {
            document.getElementById('lancamento-categoria-geral').value = lancamento.categoria_id;
        }, 100);

    } else if (lancamento.tipo === 'cartao') {
        // Lançamento de cartão
        document.getElementById('lancamento-tipo').value = 'cartao';
        alternarTipoLancamento();

        // Preencher campos específicos de cartão
        document.getElementById('lancamento-parcelas').value = lancamento.total_parcelas;

        if (lancamento.mes_fatura) {
            const mesFatura = lancamento.mes_fatura.substring(0, 7);
            document.getElementById('lancamento-mes-fatura').value = mesFatura;
        }

        // Aguardar um pouco, depois selecionar cartão e categoria
        setTimeout(async () => {
            document.getElementById('lancamento-cartao').value = lancamento.cartao_id;
            await carregarCategoriasPorCartao();

            setTimeout(() => {
                document.getElementById('lancamento-categoria-cartao').value = lancamento.categoria_id;
            }, 100);
        }, 100);
    }

    abrirModal('modal-lancamento');
}

async function excluirLancamento(id, tipo) {
    if (!confirm('Deseja realmente excluir este lançamento?')) return;

    try {
        let url;
        if (tipo === 'cartao') {
            url = `/api/cartoes/lancamentos/${id}`;
        } else if (tipo === 'credito') {
            url = `/api/receitas/realizadas/${id}`;
        } else {
            url = `/api/despesas/${id}`;
        }

        const response = await fetch(url, {
            method: 'DELETE'
        });

        if (!response.ok) throw new Error('Erro ao excluir');

        await carregarLancamentos();
        mostrarSucesso('Lançamento excluído com sucesso!');

    } catch (error) {
        console.error('Erro ao excluir lançamento:', error);
        mostrarErro('Erro ao excluir lançamento');
    }
}

// ===================================
// UTILITÁRIOS
// ===================================

function formatarData(data) {
    return new Date(data + 'T00:00:00').toLocaleDateString('pt-BR');
}

function formatarMes(mes) {
    const [ano, mesNum] = mes.split('-');
    const meses = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun',
                   'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];
    return `${meses[parseInt(mesNum) - 1]}/${ano}`;
}

// Converter de ISO (YYYY-MM) para formato brasileiro (MM/AAAA)
function converterISOparaMesAnoBR(mesISO) {
    if (!mesISO) return '';
    const [ano, mes] = mesISO.split('-');
    return `${mes}/${ano}`;
}

// Converter de formato brasileiro (MM/AAAA) para ISO (YYYY-MM)
function converterMesAnoBRparaISO(mesBR) {
    if (!mesBR) return '';
    const partes = mesBR.split('/');
    if (partes.length !== 2) return '';
    const [mes, ano] = partes;
    return `${ano}-${mes.padStart(2, '0')}`;
}

// Máscara para input de mês/ano (MM/AAAA)
function mascaraMesAno(input) {
    let valor = input.value.replace(/\D/g, ''); // Remove não-dígitos

    if (valor.length >= 2) {
        valor = valor.substring(0, 2) + '/' + valor.substring(2, 6);
    }

    input.value = valor;
}

function abrirModal(id) {
    document.getElementById(id).style.display = 'block';
}

function fecharModal(id) {
    document.getElementById(id).style.display = 'none';
}

function mostrarSucesso(mensagem) {
    alert(mensagem);
}

function mostrarErro(mensagem) {
    alert('Erro: ' + mensagem);
}

// ===================================
// RECEITAS PENDENTES
// ===================================

async function carregarReceitasPendentes() {
    const container = document.getElementById('lista-receitas-pendentes');
    container.innerHTML = '<p class="loading">Carregando receitas pendentes...</p>';

    try {
        // Pegar mês atual
        const hoje = new Date();
        const ano = hoje.getFullYear();
        const mes = String(hoje.getMonth() + 1).padStart(2, '0');
        const anoMes = `${ano}-${mes}-01`;

        // Buscar orçamentos do mês
        const responseOrc = await fetch(`/api/receitas/orcamento?ano=${ano}`);
        const resultOrc = await responseOrc.json();

        if (!resultOrc.success) {
            container.innerHTML = '<p class="error">Erro ao carregar orçamentos</p>';
            return;
        }

        // Filtrar orçamentos do mês atual
        const orcamentosMes = resultOrc.data.filter(orc =>
            orc.mes_referencia === anoMes
        );

        if (orcamentosMes.length === 0) {
            container.innerHTML = '<p class="empty">Nenhuma receita prevista para este mês</p>';
            return;
        }

        // Buscar receitas já realizadas do mês
        const responseReal = await fetch(`/api/receitas/realizadas?ano_mes=${anoMes}`);
        const resultReal = await responseReal.json();

        // Criar set de item_receita_ids já realizados
        const recebidos = new Set();
        if (resultReal.success && resultReal.data) {
            resultReal.data.forEach(r => recebidos.add(r.item_receita_id));
        }

        // Buscar dados das fontes de receita
        const responseFontes = await fetch('/api/receitas/itens');
        const resultFontes = await responseFontes.json();

        if (!resultFontes.success) {
            container.innerHTML = '<p class="error">Erro ao carregar fontes de receita</p>';
            return;
        }

        // Criar mapa de fontes
        const fontesMap = {};
        resultFontes.data.forEach(f => fontesMap[f.id] = f);

        // Filtrar apenas orçamentos ainda não recebidos
        const pendentes = orcamentosMes.filter(orc => !recebidos.has(orc.item_receita_id));

        if (pendentes.length === 0) {
            container.innerHTML = '<p class="empty">✓ Todas as receitas do mês foram confirmadas</p>';
            return;
        }

        // Renderizar receitas pendentes
        container.innerHTML = pendentes.map(orc => {
            const fonte = fontesMap[orc.item_receita_id];
            if (!fonte) return '';

            return `
                <div class="receita-pendente-card">
                    <div class="receita-header">
                        <h3>${fonte.nome}</h3>
                        <span class="badge badge-${fonte.tipo.toLowerCase()}">${formatarTipo(fonte.tipo)}</span>
                    </div>
                    <div class="receita-body">
                        <p class="receita-valor">
                            <span class="label">Valor Previsto:</span>
                            <span class="valor">${formatarMoeda(orc.valor_esperado)}</span>
                        </p>
                        ${fonte.dia_previsto_pagamento ? `
                            <p class="receita-dia">
                                <span class="label">Dia Previsto:</span>
                                <span>${fonte.dia_previsto_pagamento}</span>
                            </p>
                        ` : ''}
                    </div>
                    <div class="receita-actions">
                        <button class="btn btn-success" onclick="abrirModalConfirmarReceita(${orc.item_receita_id}, ${orc.id}, '${fonte.nome}', ${orc.valor_esperado})">
                            ✓ Confirmar Recebimento
                        </button>
                    </div>
                </div>
            `;
        }).join('');

    } catch (error) {
        console.error('Erro ao carregar receitas pendentes:', error);
        container.innerHTML = '<p class="error">Erro ao carregar receitas pendentes</p>';
    }
}

function abrirModalConfirmarReceita(itemReceitaId, orcamentoId, nome, valorPrevisto) {
    // Preencher campos do modal
    document.getElementById('receita-item-id').value = itemReceitaId;
    document.getElementById('receita-orcamento-id').value = orcamentoId;
    document.getElementById('receita-nome').value = nome;
    document.getElementById('receita-valor-previsto').value = formatarMoeda(valorPrevisto);

    // Preencher data atual e valor previsto por padrão
    const hoje = new Date().toISOString().split('T')[0];
    document.getElementById('receita-data-recebimento').value = hoje;
    document.getElementById('receita-valor-recebido').value = valorPrevisto;

    // Limpar observações
    document.getElementById('receita-observacoes').value = '';

    // Abrir modal
    document.getElementById('modal-confirmar-receita').style.display = 'block';
}

async function confirmarRecebimento(event) {
    event.preventDefault();

    const itemReceitaId = document.getElementById('receita-item-id').value;
    const dataRecebimento = document.getElementById('receita-data-recebimento').value;
    const valorRecebido = parseFloat(document.getElementById('receita-valor-recebido').value);
    const observacoes = document.getElementById('receita-observacoes').value;

    // Calcular competência (mês de referência)
    const data = new Date(dataRecebimento);
    const competencia = `${data.getFullYear()}-${String(data.getMonth() + 1).padStart(2, '0')}-01`;

    const dados = {
        item_receita_id: parseInt(itemReceitaId),
        data_recebimento: dataRecebimento,
        valor_recebido: valorRecebido,
        competencia: competencia,
        descricao: `Recebimento confirmado`,
        observacoes: observacoes
    };

    try {
        const response = await fetch('/api/receitas/realizadas', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        });

        const result = await response.json();

        if (result.success) {
            mostrarSucesso('Recebimento confirmado com sucesso!');
            fecharModal('modal-confirmar-receita');
            carregarReceitasPendentes(); // Recarregar lista
        } else {
            mostrarErro(result.error || 'Erro ao confirmar recebimento');
        }
    } catch (error) {
        console.error('Erro ao confirmar recebimento:', error);
        mostrarErro('Erro ao confirmar recebimento');
    }
}

function formatarTipo(tipo) {
    const tipos = {
        'SALARIO_FIXO': 'Salário',
        'GRATIFICACAO': 'Gratificação',
        'RENDA_EXTRA': 'Renda Extra',
        'ALUGUEL': 'Aluguel',
        'RENDIMENTO_FINANCEIRO': 'Rendimento',
        'OUTROS': 'Outros'
    };
    return tipos[tipo] || tipo;
}

function formatarMoeda(valor) {
    if (!valor) return 'R$ 0,00';
    return new Intl.NumberFormat('pt-BR', {
        style: 'currency',
        currency: 'BRL'
    }).format(valor);
}

// Fechar modal ao clicar fora
window.onclick = function(event) {
    if (event.target.classList.contains('modal')) {
        event.target.style.display = 'none';
    }
}
