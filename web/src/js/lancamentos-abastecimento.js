// FIN-MOB-ABAST-LANCAMENTOS-01 — dados do abastecimento no formulario de Novo Lancamento (js/original/lancamentos.js fica
// igual ao Flask). Com a Categoria de Despesa Combustivel (o banco informa o id pelo codigo MOB_COMBUSTIVEL, nunca pelo
// nome), o bloco aparece; com outra categoria ele so se esconde, sem perder o que foi preenchido. Valor, data, cartao e
// descricao sao os do lancamento: os litros sao valor / preco por litro. Validacoes de hodometro, combustivel e cartao
// ficam no banco (as mesmas da Mobilidade); o adaptador le os dados por dadosAbastecimentoDoFormulario() e grava a despesa e
// o abastecimento numa so operacao.
// Script classico, depois de lancamentos.js e lancamentos-adaptacoes.js, antes do DOMContentLoaded.
(function () {
    'use strict';
    const $ = (id) => document.getElementById(id);
    const COMBUSTIVEIS = { flex: ['gasolina', 'etanol'], gasolina: ['gasolina'], etanol: ['etanol'], diesel: ['diesel'], gnv: ['gnv'] };
    const ROTULOS = { gasolina: 'Gasolina', etanol: 'Etanol', diesel: 'Diesel', gnv: 'GNV', outro: 'Outro' };
    const SITUACOES = { SIMULADO: 'simulado', FORA_DE_USO: 'fora de uso' };
    const estado = { formulario: null, carga: null, vinculado: null, cartao: null, categoriaDaDespesa: null };

    // litros = valor total / preco por litro; sem arredondar (a tela mostra tres casas).
    function calcularLitros(valor, preco) {
        const v = Number(valor);
        const p = Number(preco);
        return v > 0 && p > 0 ? v / p : null;
    }
    const formatarLitros = (litros) => (litros === null ? '—'
        : `${litros.toLocaleString('pt-BR', { minimumFractionDigits: 3, maximumFractionDigits: 3 })} L`);
    window.calcularLitrosAbastecimento = calcularLitros;
    window.formatarLitrosAbastecimento = formatarLitros;

    function opcao(valor, texto) {
        const o = document.createElement('option');
        o.value = valor;
        o.textContent = texto;
        return o;
    }

    function trocarOpcoes(select, opcoes) {
        const atual = select.value;
        select.replaceChildren(...opcoes);
        if ([...select.options].some((o) => o.value === atual)) select.value = atual;
    }

    const data = (iso) => (iso ? String(iso).slice(0, 10).split('-').reverse().join('/') : '');
    const reais = (v) => Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
    const km = (v) => `${Number(v).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} km`;

    function aviso(texto) {
        const el = $('abast-aviso');
        if (el) el.textContent = texto || '';
    }

    function preencherVeiculos(veiculos) {
        const select = $('abast-veiculo');
        trocarOpcoes(select, [opcao('', 'Só a despesa (sem abastecimento)'), ...veiculos.map((v) => {
            const o = opcao(String(v.id), SITUACOES[v.situacao_uso] ? `${v.nome} (${SITUACOES[v.situacao_uso]})` : v.nome);
            o.dataset.combustivel = v.combustivel || '';
            if (v.ultimo_hodometro !== null && v.ultimo_hodometro !== undefined) o.dataset.ultimoHodometro = String(v.ultimo_hodometro);
            return o;
        })]);
        atualizarVeiculo();
    }

    function formulario() {
        if (!estado.carga) {
            estado.carga = fetch('/api/lancamentos/abastecimento/formulario')
                .then((r) => (r.ok ? r.json() : null))
                .then((j) => {
                    estado.formulario = (j && j.data) || null;
                    if (estado.formulario) preencherVeiculos(estado.formulario.veiculos || []);
                    return estado.formulario;
                })
                .catch(() => null);
        }
        return estado.carga;
    }

    function categoriaSelecionada() {
        const tipo = $('lancamento-tipo').value;
        if (tipo === 'cartao') return $('lancamento-categoria-despesa-cartao').value;
        if (tipo === 'direto') return $('lancamento-categoria-geral').value;
        return '';
    }

    function ehCombustivel() {
        const f = estado.formulario;
        return Boolean(f && f.categoria_combustivel_id && String(f.categoria_combustivel_id) === String(categoriaSelecionada()));
    }

    function atualizarVeiculo() {
        const escolhido = $('abast-veiculo').selectedOptions[0];
        const tipo = (escolhido && escolhido.dataset.combustivel) || '';
        const lista = COMBUSTIVEIS[tipo] || (escolhido && escolhido.value ? ['outro'] : []);
        trocarOpcoes($('abast-combustivel'), lista.map((c) => opcao(c, ROTULOS[c] || c)));
        const ultimo = escolhido && escolhido.dataset.ultimoHodometro;
        $('abast-hodometro').placeholder = ultimo ? `último: ${km(ultimo)}` : '';
        atualizarHabilitados();
    }

    function atualizarLitros() {
        const valor = $('abast-existente').value ? null : calcularLitros($('lancamento-valor').value, $('abast-preco').value);
        $('abast-litros').textContent = formatarLitros(valor);
    }

    function atualizarHabilitados() {
        const existente = Boolean($('abast-existente').value);
        const semVeiculo = !$('abast-veiculo').value;
        $('abast-veiculo').disabled = existente;
        for (const id of ['abast-combustivel', 'abast-hodometro', 'abast-preco', 'abast-cartao-fisico']) {
            $(id).disabled = existente || semVeiculo;
        }
        atualizarLitros();
    }

    async function atualizarCartaoFisico() {
        const grupo = $('abast-cartao-fisico-grupo');
        const cartao = $('lancamento-tipo').value === 'cartao' ? $('lancamento-cartao').value : '';
        if (!cartao) {
            grupo.hidden = true;
            return;
        }
        if (estado.cartao !== cartao) {
            estado.cartao = cartao;
            let lista = [];
            try {
                const r = await fetch(`/api/cartoes/${encodeURIComponent(cartao)}/vinculados`);
                lista = r.ok ? ((await r.json()).data || []) : [];
            } catch (erro) {
                lista = [];
            }
            if (estado.cartao !== cartao) return;
            const ativos = lista.filter((c) => c.situacao === 'ATIVO' || (estado.vinculado && estado.vinculado.cartao_vinculado_id === c.id));
            trocarOpcoes($('abast-cartao-fisico'), [opcao('', 'Não identificado'),
                ...ativos.map((c) => opcao(String(c.id), `${c.nome} •••• ${c.final}`))]);
            grupo.hidden = ativos.length === 0;
        }
    }

    async function atualizarVisibilidade() {
        await formulario();
        const ativo = ehCombustivel();
        $('bloco-abastecimento').hidden = !ativo;
        if (ativo) {
            await atualizarCartaoFisico();
            atualizarHabilitados();
        }
    }

    function limpar() {
        estado.vinculado = null;
        estado.categoriaDaDespesa = null;
        for (const id of ['abast-veiculo', 'abast-hodometro', 'abast-preco']) $(id).value = '';
        trocarOpcoes($('abast-existente'), []);
        $('abast-existente-grupo').hidden = true;
        $('abast-cartao-fisico').value = '';
        aviso('');
        atualizarVeiculo();
        $('bloco-abastecimento').hidden = true;
    }

    // Edicao: o abastecimento ja vinculado volta preenchido; sem ele, os registros de Mobilidade que podem ser esta despesa.
    async function carregarDaDespesa(lancamento) {
        limpar();
        if (!lancamento || !['cartao', 'direto'].includes(lancamento.tipo)) return;
        await formulario();
        const chave = lancamento.tipo === 'cartao' ? 'lancamento_id' : 'conta_id';
        let leitura = null;
        try {
            const r = await fetch(`/api/lancamentos/abastecimento?${chave}=${encodeURIComponent(lancamento.id)}`);
            leitura = r.ok ? (await r.json()).data : null;
        } catch (erro) {
            leitura = null;
        }
        if (!leitura || String($('lancamento-id').value) !== String(lancamento.id)) return;
        estado.categoriaDaDespesa = lancamento.tipo === 'cartao' ? leitura.categoria_id : null;
        const a = leitura.abastecimento;
        if (a) {
            estado.vinculado = a;
            $('abast-veiculo').value = String(a.veiculo_id);
            atualizarVeiculo();
            $('abast-combustivel').value = a.combustivel;
            $('abast-hodometro').value = a.hodometro_km;
            $('abast-preco').value = a.preco_litro;
            aviso(`Abastecimento vinculado: ${a.veiculo_nome || 'veículo'}, ${data(a.data_abastecimento)}. Alterações ficam no histórico do veículo.`);
        } else if ((leitura.candidatos || []).length) {
            trocarOpcoes($('abast-existente'), [opcao('', 'Registrar novo'), ...leitura.candidatos.map((c) => opcao(String(c.id),
                `${data(c.data_abastecimento)} · ${c.veiculo_nome} · ${km(c.hodometro_km)} · ${reais(c.valor_total)}`))]);
            $('abast-existente-grupo').hidden = false;
        }
        // a tela original escolhe a categoria e o cartao depois de um intervalo: confere de novo em seguida
        await atualizarVisibilidade();
        setTimeout(completarEAtualizar, 400);
        setTimeout(completarEAtualizar, 900);
    }

    // A lista de compras nao traz a categoria e a edicao original a deixa vazia: o banco a informa (so preenche campo vazio).
    function completarEAtualizar() {
        const select = $('lancamento-categoria-despesa-cartao');
        const categoria = estado.categoriaDaDespesa ? String(estado.categoriaDaDespesa) : '';
        if (categoria && !select.value && $('lancamento-tipo').value === 'cartao' && [...select.options].some((o) => o.value === categoria)) {
            select.value = categoria;
        }
        return atualizarVisibilidade();
    }

    // Para o adaptador: {ativo} sem a categoria Combustivel; {ativo, dados: null} so a despesa; {ativo, erro}; {ativo, dados}.
    window.dadosAbastecimentoDoFormulario = function () {
        const vinculado = estado.vinculado ? estado.vinculado.id : null;
        if (!ehCombustivel()) return { ativo: false, vinculado };
        const existente = $('abast-existente').value;
        if (existente) return { ativo: true, vinculado, dados: { id: Number(existente) } };
        const veiculo = $('abast-veiculo').value;
        if (!veiculo) return { ativo: true, vinculado, dados: null };
        const hodometro = $('abast-hodometro').value;
        const preco = $('abast-preco').value;
        if (hodometro === '' || preco === '' || !$('abast-combustivel').value) {
            return { ativo: true, vinculado, erro: 'Informe o combustível, o hodômetro e o preço por litro do abastecimento, ou escolha "Só a despesa".' };
        }
        const dados = { veiculo_id: Number(veiculo), combustivel: $('abast-combustivel').value, hodometro_km: Number(hodometro),
            preco_litro: Number(preco) };
        if (!$('abast-cartao-fisico-grupo').hidden && $('abast-cartao-fisico').value) dados.cartao_vinculado_id = Number($('abast-cartao-fisico').value);
        if (vinculado) dados.id = vinculado;
        return { ativo: true, vinculado, dados };
    };

    function embrulhar(nome, depois) {
        const original = window[nome];
        if (typeof original !== 'function') return;
        window[nome] = function (...args) {
            const r = original.apply(this, args);
            depois(...args);
            return r;
        };
    }

    function iniciar() {
        if (!$('bloco-abastecimento')) return;
        for (const id of ['lancamento-tipo', 'lancamento-categoria-despesa-cartao', 'lancamento-categoria-geral']) {
            $(id).addEventListener('change', atualizarVisibilidade);
        }
        $('lancamento-cartao').addEventListener('change', () => { estado.cartao = null; atualizarVisibilidade(); });
        $('abast-veiculo').addEventListener('change', atualizarVeiculo);
        $('abast-existente').addEventListener('change', atualizarHabilitados);
        for (const id of ['lancamento-valor', 'abast-preco']) $(id).addEventListener('input', atualizarLitros);
        formulario();
    }

    embrulhar('editarLancamento', carregarDaDespesa);
    for (const nome of ['abrirModalLancamento', 'cancelarLancamentoInline', 'finalizarLancamentoInline']) embrulhar(nome, limpar);
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
    else iniciar();
}());
