/**
 * JavaScript para a página de Receitas
 *
 * Funcionalidades:
 * - Gerenciamento de fontes de receita
 * - Planejamento de orçamento
 * - Registro de receitas realizadas
 * - Relatórios e análises
 */

// ============================================================================
// ESTADO DA APLICAÇÃO
// ============================================================================

let estado = {
    anoAtual: new Date().getFullYear(),
    mesAtual: null,
    tipoFiltro: '',
    fontes: [],
    contasBancarias: [],
    orcamentos: [],
    realizadas: [],
    receitasMes: []
};

// ============================================================================
// INICIALIZAÇÃO
// ============================================================================

document.addEventListener('DOMContentLoaded', function() {
    inicializar();
});

function inicializar() {
    // Preencher seletor de anos (últimos 5 anos + próximos 2)
    const anoInicio = new Date().getFullYear() - 5;
    const anoFim = new Date().getFullYear() + 2;
    const selectAno = document.getElementById('filtro-ano');

    for (let ano = anoInicio; ano <= anoFim; ano++) {
        const option = document.createElement('option');
        option.value = ano;
        option.textContent = ano;
        if (ano === estado.anoAtual) {
            option.selected = true;
        }
        selectAno.appendChild(option);
    }

    // Carregar dados iniciais
    carregarContasBancarias();
    atualizarDados();
}

async function carregarContasBancarias() {
    try {
        const resp = await fetch('/api/contas?status=ATIVO');
        const json = await resp.json();
        if (!json.success) return;
        estado.contasBancarias = json.data || [];
        atualizarSelectsContasBancarias(estado.contasBancarias);
    } catch (e) {
        console.error('Erro ao carregar contas bancárias:', e);
    }
}

function atualizarSelectsContasBancarias(contas) {
    const selects = ['fonte-conta-bancaria', 'real-conta-bancaria', 'consolidar-conta-bancaria'];
    selects.forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        const atual = el.value;
        el.innerHTML = '<option value="">Selecione...</option>';
        (contas || []).forEach(c => {
            const opt = document.createElement('option');
            opt.value = c.id;
            opt.textContent = `${c.nome} (${c.instituicao})`;
            el.appendChild(opt);
        });
        if (atual) el.value = atual;
    });
}

// ============================================================================
// ATUALIZAÇÃO DE DADOS
// ============================================================================

function atualizarDados() {
    const ano = document.getElementById('filtro-ano').value;
    const mes = document.getElementById('filtro-mes').value;
    const tipo = document.getElementById('filtro-tipo').value;

    estado.anoAtual = parseInt(ano);
    estado.mesAtual = mes || null;
    estado.tipoFiltro = tipo || '';

    // Atualizar resumo
    atualizarResumo();

    // Fluxo único: recarregar fontes/contas e lista do mês
    Promise.all([carregarFontesReceita(), carregarContasBancarias()]).then(() => carregarReceitasMes());
}

async function atualizarResumo() {
    try {
        const response = await fetch(`/api/receitas/resumo-mensal?ano=${estado.anoAtual}`);
        const result = await response.json();

        if (result.success) {
            // Determinar mês a mostrar (filtro ou mês atual)
            const mesNum = estado.mesAtual ? parseInt(estado.mesAtual) : new Date().getMonth() + 1;
            const dados = result.data[mesNum];

            if (dados) {
                document.getElementById('total-previsto').textContent =
                    formatarMoeda(dados.total_previsto);
                document.getElementById('total-realizado').textContent =
                    formatarMoeda(dados.total_realizado);

                const diferenca = dados.total_realizado - dados.total_previsto;
                document.getElementById('diferenca').textContent =
                    formatarMoeda(diferenca);
                document.getElementById('diferenca').className =
                    `valor ${diferenca >= 0 ? 'positivo' : 'negativo'}`;

                const conf = dados.total_previsto > 0 ?
                    ((dados.total_realizado / dados.total_previsto) * 100).toFixed(1) : 0;
                document.getElementById('confiabilidade').textContent = `${conf}%`;
            } else {
                // Dados não disponíveis para o mês
                document.getElementById('total-previsto').textContent = formatarMoeda(0);
                document.getElementById('total-realizado').textContent = formatarMoeda(0);
                document.getElementById('diferenca').textContent = formatarMoeda(0);
                document.getElementById('confiabilidade').textContent = '0%';
            }
        }
    } catch (error) {
        console.error('Erro ao atualizar resumo:', error);
        // Mostrar valores zerados em caso de erro
        document.getElementById('total-previsto').textContent = formatarMoeda(0);
        document.getElementById('total-realizado').textContent = formatarMoeda(0);
        document.getElementById('diferenca').textContent = formatarMoeda(0);
        document.getElementById('confiabilidade').textContent = '0%';
    }
}

// ============================================================================
// FONTES DE RECEITA
// ============================================================================

async function carregarFontesReceita() {
    try {
        const url = '/api/receitas/itens';

        const response = await fetch(url);
        const result = await response.json();

        if (result.success) {
            estado.fontes = result.data;

            // Atualizar selects de fontes nos modais
            atualizarSelectsFontes(result.data);
        } else {
            console.error('Erro ao carregar fontes:', result.error);
        }
    } catch (error) {
        console.error('Erro ao carregar fontes:', error);
    }
}

function getAnoMesSelecionado() {
    const ano = estado.anoAtual;
    const mesNum = estado.mesAtual ? parseInt(estado.mesAtual, 10) : (new Date().getMonth() + 1);
    const mes = mesNum.toString().padStart(2, '0');
    return `${ano}-${mes}-01`;
}

async function carregarReceitasMes() {
    const lista = document.getElementById('mes-lista');
    if (!lista) return;
    lista.innerHTML = '<p class="loading">Carregando...</p>';

    try {
        const anoMes = getAnoMesSelecionado();

        const [resOrc, resReal] = await Promise.all([
            fetch(`/api/receitas/orcamento?ano=${estado.anoAtual}`),
            fetch(`/api/receitas/realizadas?ano_mes=${anoMes}`)
        ]);

        const [orcJson, realJson] = await Promise.all([resOrc.json(), resReal.json()]);
        if (!orcJson.success) throw new Error(orcJson.error || 'Erro ao carregar orçamento');
        if (!realJson.success) throw new Error(realJson.error || 'Erro ao carregar realizadas');

        estado.orcamentos = orcJson.data || [];
        estado.realizadas = realJson.data || [];

        estado.receitasMes = montarListaReceitasMes(estado.orcamentos, estado.realizadas, anoMes);
        renderizarReceitasMes(estado.receitasMes, anoMes);
    } catch (error) {
        console.error('Erro ao carregar receitas do mês:', error);
        lista.innerHTML = '<p class="error">Erro ao carregar receitas do mês</p>';
    }
}

function montarListaReceitasMes(orcamentos, realizadas, anoMes) {
    const orcamentosDoMes = (orcamentos || []).filter(o => (o.ano_mes || o.mes_referencia || '').slice(0, 10) === anoMes);

    const totalRealizadoPorFonte = new Map();
    const realizadasPorFonte = new Map();
    const temRealizadaPorFonte = new Set();
    (realizadas || []).forEach(r => {
        if (!r.item_receita_id) return;
        const atual = totalRealizadoPorFonte.get(r.item_receita_id) || 0;
        totalRealizadoPorFonte.set(r.item_receita_id, atual + (r.valor_recebido || 0));
        temRealizadaPorFonte.add(r.item_receita_id);

        if (!realizadasPorFonte.has(r.item_receita_id)) {
            realizadasPorFonte.set(r.item_receita_id, []);
        }
        realizadasPorFonte.get(r.item_receita_id).push(r);
    });

    const itensPlanejados = orcamentosDoMes.map(o => {
        const itemId = o.item_receita_id;
        const fonte = estado.fontes.find(f => f.id === itemId);
        const previsto = o.valor_previsto ?? o.valor_esperado ?? 0;
        const realizado = totalRealizadoPorFonte.get(itemId);
        const status = realizado != null ? 'REALIZADA' : 'PREVISTA';
        const valor = realizado != null ? realizado : previsto;
        const realizadosFonte = realizadasPorFonte.get(itemId) || [];

        return {
            kind: 'fonte',
            origem: 'orcamento',
            orcamento_id: o.id,
            item_receita_id: itemId,
            descricao: (fonte ? fonte.nome : (o.item_receita?.nome || 'Receita')),
            tipo: (fonte ? fonte.tipo : (o.item_receita?.tipo || null)),
            sub: `${formatarMesAno(anoMes)} · Receita`,
            status,
            valor,
            podeConsolidar: status === 'PREVISTA' && previsto > 0,
            realizada_id: (realizadosFonte.length === 1 ? realizadosFonte[0].id : null),
            realizadas_count: realizadosFonte.length,
            valor_previsto: previsto
        };
    }).filter(i => i.valor > 0);

    const idsPlanejados = new Set(itensPlanejados.map(i => i.item_receita_id));

    // Fallback: fontes recorrentes com valor_base_mensal (quando não há orçamento gerado para o mês)
    const fontesRecorrentes = (estado.fontes || [])
        .filter(f => f.ativo && f.recorrente && f.valor_base_mensal && !idsPlanejados.has(f.id))
        .map(f => {
            const realizado = totalRealizadoPorFonte.get(f.id);
            const status = realizado != null ? 'REALIZADA' : 'PREVISTA';
            const valor = realizado != null ? realizado : (f.valor_base_mensal || 0);
            const realizadosFonte = realizadasPorFonte.get(f.id) || [];
            return {
                kind: 'fonte',
                origem: 'fonte_base',
                item_receita_id: f.id,
                descricao: f.nome,
                tipo: f.tipo,
                sub: `${formatarMesAno(anoMes)} · Receita`,
                status,
                valor,
                podeConsolidar: status === 'PREVISTA' && (f.valor_base_mensal || 0) > 0,
                realizada_id: (realizadosFonte.length === 1 ? realizadosFonte[0].id : null),
                realizadas_count: realizadosFonte.length,
                valor_previsto: (f.valor_base_mensal || 0)
            };
        }).filter(i => i.valor > 0);

    const eventos = (realizadas || [])
        .filter(r => !r.item_receita_id || !idsPlanejados.has(r.item_receita_id))
        .map(r => {
            const fonte = r.item_receita_id ? estado.fontes.find(f => f.id === r.item_receita_id) : null;
            return {
                kind: 'evento',
                id: r.id,
                item_receita_id: r.item_receita_id,
                descricao: r.descricao || (fonte ? fonte.nome : 'Receita'),
                tipo: (fonte ? fonte.tipo : (r.item_receita?.tipo || null)),
                sub: `${formatarMesAno(anoMes)} · Receita`,
                status: 'REALIZADA',
                valor: r.valor_recebido || 0,
                podeConsolidar: false,
                realizada_id: r.id,
                realizadas_count: 1
            };
        }).filter(i => i.valor > 0);

    const lista = [...itensPlanejados, ...fontesRecorrentes, ...eventos];
    if (estado.tipoFiltro) {
        return lista.filter(i => i.tipo === estado.tipoFiltro);
    }
    return lista;
}

function renderizarReceitasMes(listaReceitas, anoMes) {
    const lista = document.getElementById('mes-lista');
    if (!lista) return;

    if (!listaReceitas || listaReceitas.length === 0) {
        lista.innerHTML = '<p class="empty">Nenhuma receita para o mês</p>';
        return;
    }

    lista.innerHTML = listaReceitas.map(r => {
        const statusClass = r.status === 'REALIZADA' ? 'status-realizada' : 'status-prevista';

        const podeEditarRealizada = r.status === 'REALIZADA' && r.realizada_id && r.realizadas_count === 1;
        const podeExcluirRealizada = r.status === 'REALIZADA' && r.realizada_id && r.realizadas_count === 1;

        const botaoEditar = (r.status === 'PREVISTA')
            ? `<button class="btn-icon" onclick="editarReceitaPrevista(${r.item_receita_id}, '${r.origem}', ${Number(r.valor_previsto ?? r.valor).toFixed(2)})" title="Editar">✏️</button>`
            : (podeEditarRealizada
                ? `<button class="btn-icon" onclick="editarRealizada(${r.realizada_id})" title="Editar">✏️</button>`
                : `<button class="btn-icon" onclick="alert('Há mais de 1 recebimento para esta receita no mês. Edite em Receitas Recebidas.')" title="Editar">✏️</button>`);

        const botaoExcluir = (r.status === 'PREVISTA')
            ? `<button class="btn-icon btn-danger" onclick="excluirReceitaPrevista(${r.item_receita_id}, '${r.origem}')" title="Excluir">X</button>`
            : (podeExcluirRealizada
                ? `<button class="btn-icon btn-danger" onclick="deletarRealizada(${r.realizada_id})" title="Excluir">X</button>`
                : `<button class="btn-icon btn-danger" onclick="alert('Há mais de 1 recebimento para esta receita no mês. Exclua em Receitas Recebidas.')" title="Excluir">X</button>`);

        const botaoConsolidar = r.podeConsolidar
            ? `<button class="btn-icon btn-consolidar-icon" onclick="consolidarReceitaMes(${r.item_receita_id}, ${Number(r.valor_previsto ?? r.valor).toFixed(2)})" title="Consolidar">✅</button>`
            : `<button class="btn-icon btn-consolidar-icon" title="Consolidar" disabled>✅</button>`;

        // Mantém sempre 3 botões no DOM (para não "pular" alinhamento). Em REALIZADA, o ✅ fica desabilitado.
        const acoes = (r.status === 'REALIZADA')
            ? `<div class="acoes">${botaoEditar}${botaoExcluir}<button class="btn-icon btn-consolidar-icon" title="Consolidar" disabled>✅</button></div>`
            : `<div class="acoes">${botaoEditar}${botaoExcluir}${botaoConsolidar}</div>`;

        return `
            <div class="linha-receita linha-receita-mes">
                <div class="col-descricao">
                    <div class="titulo">${r.descricao}</div>
                    <div class="subtitulo">${r.sub} <span class="status ${statusClass}">${r.status}</span></div>
                </div>
                <div class="col-fill"></div>
                <div class="col-valor">
                    <span class="valor">${formatarMoeda(r.valor)}</span>
                    ${acoes}
                </div>
            </div>
        `;
    }).join('');
}

async function consolidarReceitaMes(itemReceitaId, valorPrevisto) {
    const anoMes = getAnoMesSelecionado();
    const jaRealizada = (estado.realizadas || []).some(r =>
        r.item_receita_id === itemReceitaId && (r.mes_referencia || r.competencia || '').slice(0, 10) === anoMes
    );
    if (jaRealizada) {
        alert('Esta receita já está realizada neste mês.');
        return;
    }

    const fonte = estado.fontes.find(f => f.id === itemReceitaId);

    // Exigir confirmaÇõÇœo de conta bancÇ­ria (execuÇõÇœo)
    document.getElementById('consolidar-item-receita-id').value = itemReceitaId;
    document.getElementById('consolidar-valor-previsto').value = valorPrevisto;

    const select = document.getElementById('consolidar-conta-bancaria');
    if (select) {
        atualizarSelectsContasBancarias(estado.contasBancarias || []);
        select.value = fonte?.conta_bancaria_id ? String(fonte.conta_bancaria_id) : '';
    }

    document.getElementById('modal-consolidar-conta').style.display = 'block';
}

async function confirmarConsolidacaoComConta(event) {
    event.preventDefault();

    const itemReceitaId = parseInt(document.getElementById('consolidar-item-receita-id').value, 10);
    const valorPrevisto = parseFloat(document.getElementById('consolidar-valor-previsto').value);
    const contaBancariaId = document.getElementById('consolidar-conta-bancaria').value;

    if (!contaBancariaId) {
        alert('Selecione a conta bancária para consolidar.');
        return;
    }

    const fonte = estado.fontes.find(f => f.id === itemReceitaId);
    const hoje = new Date().toISOString().split('T')[0];
    const anoMes = getAnoMesSelecionado();

    try {
        const response = await fetch('/api/receitas/realizadas', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                item_receita_id: itemReceitaId,
                data_recebimento: hoje,
                valor_recebido: valorPrevisto,
                competencia: anoMes,
                descricao: fonte ? fonte.nome : 'Receita',
                observacoes: '',
                conta_bancaria_id: parseInt(contaBancariaId, 10)
            })
        });

        const result = await response.json();
        if (!result.success) {
            alert('Erro: ' + result.error);
            return;
        }

        fecharModal('modal-consolidar-conta');
        atualizarResumo();
        carregarReceitasMes();
    } catch (error) {
        console.error('Erro ao consolidar receita:', error);
        alert('Erro ao consolidar receita');
    }
}

function editarReceitaPrevista(itemReceitaId, origem, valorPrevisto) {
    const anoMes = getAnoMesSelecionado();

    if (origem === 'orcamento') {
        const modal = document.getElementById('modal-orcamento');
        const anoMesInput = (anoMes || '').slice(0, 7);
        document.getElementById('orc-fonte').value = itemReceitaId;
        document.getElementById('orc-ano-mes').value = anoMesInput;
        document.getElementById('orc-valor').value = valorPrevisto;
        modal.style.display = 'block';
        return;
    }

    // Fonte base (recorrente): editar cadastro da fonte
    abrirModalFonte(itemReceitaId);
}

async function excluirReceitaPrevista(itemReceitaId, origem) {
    const anoMes = getAnoMesSelecionado();

    if (origem === 'orcamento') {
        if (!confirm('Remover a previsão desta receita no mês selecionado?')) {
            return;
        }

        try {
            const response = await fetch('/api/receitas/orcamento', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    item_receita_id: itemReceitaId,
                    ano_mes: anoMes,
                    valor_previsto: 0,
                    periodicidade: 'MENSAL_FIXA',
                    observacoes: 'Removido pelo usuário'
                })
            });

            const result = await response.json();
            if (!result.success) {
                alert('Erro: ' + result.error);
                return;
            }

            atualizarResumo();
            carregarReceitasMes();
        } catch (error) {
            console.error('Erro ao remover previsão:', error);
            alert('Erro ao remover previsão');
        }
        return;
    }

    // Fonte base: zerar valor base mensal (impacta meses futuros)
    if (!confirm('Zerar o valor base mensal desta fonte? Isso remove a previsão para os próximos meses.')) {
        return;
    }

    const fonte = estado.fontes.find(f => f.id === itemReceitaId);
    if (!fonte) {
        alert('Fonte não encontrada.');
        return;
    }

    try {
        const response = await fetch(`/api/receitas/itens/${itemReceitaId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                nome: fonte.nome,
                tipo: fonte.tipo,
                descricao: fonte.descricao || '',
                valor_base_mensal: 0,
                dia_previsto_pagamento: fonte.dia_previsto_pagamento || null,
                recorrente: !!fonte.recorrente,
                ativo: !!fonte.ativo
            })
        });

        const result = await response.json();
        if (!result.success) {
            alert('Erro: ' + (result.error || 'Falha ao atualizar fonte'));
            return;
        }

        await carregarFontesReceita();
        atualizarResumo();
        carregarReceitasMes();
    } catch (error) {
        console.error('Erro ao zerar valor base:', error);
        alert('Erro ao zerar valor base');
    }
}

function atualizarSelectsFontes(fontes) {
    const selects = ['orc-fonte', 'real-fonte'];

    selects.forEach(selectId => {
        const select = document.getElementById(selectId);
        select.innerHTML = '<option value="">Selecione...</option>';

        fontes.filter(f => f.ativo).forEach(fonte => {
            const option = document.createElement('option');
            option.value = fonte.id;
            option.textContent = `${fonte.nome} (${formatarTipo(fonte.tipo)})`;
            select.appendChild(option);
        });
    });
}

// ============================================================================
// MODAIS
// ============================================================================

function abrirModalFonte(id = null) {
    const modal = document.getElementById('modal-fonte');
    const form = document.getElementById('form-fonte');
    form.reset();

    if (id) {
        // Modo edição - carregar dados
        const fonte = estado.fontes.find(f => f.id === id);
        if (fonte) {
            document.getElementById('fonte-id').value = fonte.id;
            document.getElementById('fonte-nome').value = fonte.nome;
            document.getElementById('fonte-tipo').value = fonte.tipo;
            document.getElementById('fonte-descricao').value = fonte.descricao || '';
            document.getElementById('fonte-valor-base').value = fonte.valor_base_mensal || '';
            document.getElementById('fonte-dia-pagamento').value = fonte.dia_previsto_pagamento || '';
            document.getElementById('fonte-conta-bancaria').value = fonte.conta_bancaria_id || '';
            document.getElementById('fonte-ativo').checked = fonte.ativo;
            document.getElementById('modal-fonte-titulo').textContent = 'Editar Fonte de Receita';
        }
    } else {
        // Modo criação
        document.getElementById('modal-fonte-titulo').textContent = 'Nova Fonte de Receita';
    }

    modal.style.display = 'block';
}

function abrirModalOrcamento() {
    const modal = document.getElementById('modal-orcamento');
    modal.style.display = 'block';
}

function editarRealizada(id) {
    const receita = estado.realizadas.find(r => r.id === id);
    if (!receita) {
        alert('Receita não encontrada.');
        return;
    }

    if (!receita.item_receita_id) {
        alert('Esta receita não possui fonte e não pode ser editada por aqui.');
        return;
    }

    const modal = document.getElementById('modal-realizada');
    const form = document.getElementById('form-realizada');
    form.reset();

    document.getElementById('realizada-id').value = receita.id;
    document.getElementById('modal-realizada-titulo').textContent = 'Editar Recebimento';

    document.getElementById('real-fonte').value = receita.item_receita_id;
    document.getElementById('real-data-recebimento').value = receita.data_recebimento;
    document.getElementById('real-valor').value = receita.valor_recebido;
    document.getElementById('real-competencia').value = (receita.competencia || receita.mes_referencia || '').slice(0, 7);
    document.getElementById('real-conta-bancaria').value = receita.conta_bancaria_id || '';
    document.getElementById('real-descricao').value = receita.descricao || '';
    document.getElementById('real-observacoes').value = receita.observacoes || '';

    modal.style.display = 'block';
}

function fecharModal(modalId) {
    document.getElementById(modalId).style.display = 'none';
}

// ============================================================================
// SALVAMENTOS
// ============================================================================

async function salvarFonte(event) {
    event.preventDefault();

    const id = document.getElementById('fonte-id').value;

    const dados = {
        nome: document.getElementById('fonte-nome').value,
        tipo: document.getElementById('fonte-tipo').value,
        descricao: document.getElementById('fonte-descricao').value,
        valor_base_mensal: document.getElementById('fonte-valor-base').value || null,
        dia_previsto_pagamento: document.getElementById('fonte-dia-pagamento').value || null,
        conta_bancaria_id: (document.getElementById('fonte-conta-bancaria').value ? parseInt(document.getElementById('fonte-conta-bancaria').value, 10) : null),
        recorrente: document.getElementById('fonte-recorrente').checked,
        ativo: document.getElementById('fonte-ativo').checked
    };

    try {
        const url = id ? `/api/receitas/itens/${id}` : '/api/receitas/itens';
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
            alert(result.message);
            fecharModal('modal-fonte');
            await carregarFontesReceita();
            atualizarResumo();
            carregarReceitasMes();
        } else {
            alert('Erro: ' + result.error);
        }
    } catch (error) {
        console.error('Erro ao salvar fonte:', error);
        alert('Erro ao salvar fonte de receita');
    }
}

async function salvarOrcamento(event) {
    event.preventDefault();

    const dados = {
        item_receita_id: parseInt(document.getElementById('orc-fonte').value),
        ano_mes: document.getElementById('orc-ano-mes').value + '-01',
        valor_previsto: parseFloat(document.getElementById('orc-valor').value),
        periodicidade: document.getElementById('orc-periodicidade').value,
        observacoes: document.getElementById('orc-observacoes').value
    };

    try {
        const response = await fetch('/api/receitas/orcamento', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(dados)
        });

        const result = await response.json();

        if (result.success) {
            alert(result.message);
            fecharModal('modal-orcamento');
            atualizarResumo();
            carregarReceitasMes();
        } else {
            alert('Erro: ' + result.error);
        }
    } catch (error) {
        console.error('Erro ao salvar orçamento:', error);
        alert('Erro ao salvar orçamento');
    }
}

async function salvarRealizada(event) {
    event.preventDefault();

    const dados = {
        item_receita_id: parseInt(document.getElementById('real-fonte').value),
        data_recebimento: document.getElementById('real-data-recebimento').value,
        valor_recebido: parseFloat(document.getElementById('real-valor').value),
        competencia: document.getElementById('real-competencia').value + '-01',
        conta_bancaria_id: (document.getElementById('real-conta-bancaria').value ? parseInt(document.getElementById('real-conta-bancaria').value, 10) : null),
        descricao: document.getElementById('real-descricao').value,
        observacoes: document.getElementById('real-observacoes').value
    };

    try {
        const id = document.getElementById('realizada-id').value;
        const url = id ? `/api/receitas/realizadas/${id}` : '/api/receitas/realizadas';
        const method = id ? 'PUT' : 'POST';

        const response = await fetch(url, {
            method,
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(dados)
        });

        const result = await response.json();

        if (result.success) {
            alert(result.message);
            fecharModal('modal-realizada');
            atualizarResumo();
            carregarReceitasMes();
        } else {
            alert('Erro: ' + result.error);
        }
    } catch (error) {
        console.error('Erro ao salvar receita:', error);
        alert('Erro ao salvar receita realizada');
    }
}

// ============================================================================
// UTILITÁRIOS
// ============================================================================

function formatarMoeda(valor) {
    return new Intl.NumberFormat('pt-BR', {
        style: 'currency',
        currency: 'BRL'
    }).format(valor || 0);
}

function formatarTipo(tipo) {
    const tipos = {
        'SALARIO_FIXO': 'Salário',
        'GRATIFICACAO': 'Gratificação',
        'RENDA_EXTRA': 'Renda Extra',
        'ALUGUEL': 'Aluguel',
        'RENDIMENTO_FINANCEIRO': 'Rendimentos',
        'OUTROS': 'Outros'
    };
    return tipos[tipo] || tipo;
}

async function deletarRealizada(id) {
    if (!confirm('Tem certeza que deseja deletar esta receita?')) {
        return;
    }

    try {
        const response = await fetch(`/api/receitas/realizadas/${id}`, {
            method: 'DELETE'
        });

        const result = await response.json();

        if (result.success) {
            alert(result.message);
            atualizarResumo();
            carregarReceitasMes();
        } else {
            alert('Erro: ' + result.error);
        }
    } catch (error) {
        console.error('Erro ao deletar receita:', error);
        alert('Erro ao deletar receita');
    }
}

function formatarMesAno(valor) {
    if (!valor) return '';
    const ano = valor.slice(0, 4);
    const mes = valor.slice(5, 7);
    return `${mes}/${ano}`;
}

// ============================================================================
// FECHAR MODAL AO CLICAR FORA
// ============================================================================

window.onclick = function(event) {
    if (event.target.classList.contains('modal')) {
        event.target.style.display = 'none';
    }
};
