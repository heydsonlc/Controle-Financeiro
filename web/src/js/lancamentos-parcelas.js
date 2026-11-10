// FIN-MVP-LANCAMENTOS-03 (P14) — previa das parcelas no Novo Lancamento (js/original/lancamentos.js fica igual ao Flask).
// Compra no cartao com 2 ou mais parcelas: tabela compacta (parcela, competencia da fatura e valor, com o total) logo abaixo
// de Parcelas e Mes da fatura. Os numeros vem de previa_compra, que planeja pelo mesmo plano_compra que criar_compra grava:
// nenhuma formula aqui (centavos, fatura paga que manda para a proxima, virada de ano). Nada e gravado ao mudar os campos.
// Script classico, depois de lancamentos.js; a consulta passa pelo adaptador (GET /api/lancamentos/previa-parcelas).
(function () {
    'use strict';
    const $ = (id) => document.getElementById(id);
    const CAMPOS = ['lancamento-tipo', 'lancamento-cartao', 'lancamento-valor', 'lancamento-data', 'lancamento-parcelas', 'lancamento-mes-fatura',
        'lancamento-categoria-despesa-cartao'];
    const estado = { temporizador: null, pedido: 0 };
    const moeda = (v) => Number(v || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
    const mesAno = (iso) => `${String(iso).slice(5, 7)}/${String(iso).slice(0, 4)}`;

    function caixa() {
        let c = $('lancamento-previa-parcelas');
        if (!c) {
            const linha = $('lancamento-parcelas')?.closest('.form-row');
            if (!linha) return null;
            c = document.createElement('div');
            c.id = 'lancamento-previa-parcelas';
            c.className = 'lanc-previa-parcelas';
            c.setAttribute('aria-live', 'polite');
            c.hidden = true;
            (linha.nextElementSibling?.classList.contains('lanc-fatura-sugestao-linha') ? linha.nextElementSibling : linha).after(c);
        }
        return c;
    }

    // So compra nova no cartao, com valor, cartao, data, mes da fatura e 2 ou mais parcelas.
    function dados() {
        if ($('lancamento-tipo')?.value !== 'cartao' || $('lancamento-id')?.value) return null;
        const parcelas = Number.parseInt($('lancamento-parcelas')?.value, 10);
        const valor = Number($('lancamento-valor')?.value);
        const cartao = $('lancamento-cartao')?.value;
        const data = $('lancamento-data')?.value;
        const mes = $('lancamento-mes-fatura')?.value;
        if (!(parcelas >= 2) || !(valor > 0) || !cartao || !/^\d{4}-\d{2}-\d{2}$/.test(data || '') || !/^\d{4}-\d{2}$/.test(mes || '')) return null;
        return { cartao_id: cartao, valor: valor.toFixed(2), total_parcelas: String(parcelas), data_compra: data, mes_fatura: `${mes}-01`,
            descricao: $('lancamento-descricao')?.value || '', categoria_id: $('lancamento-categoria-despesa-cartao')?.value || '' };
    }

    function celula(tag, texto, classe) {
        const e = document.createElement(tag);
        e.textContent = texto;
        if (classe) e.className = classe;
        return e;
    }

    function desenhar(c, p) {
        const tabela = document.createElement('table');
        tabela.className = 'lanc-previa-tabela';
        const cab = tabela.createTHead().insertRow();
        cab.append(celula('th', 'Parcela'), celula('th', 'Competência'), celula('th', 'Valor', 'direita'));
        const corpo = tabela.createTBody();
        p.parcelas.forEach((x) => {
            const tr = corpo.insertRow();
            const comp = celula('td', mesAno(x.mes_fatura));
            if (x.redirecionada) {
                comp.textContent += ' *';
                comp.title = `Fatura de ${mesAno(x.mes_fatura_sugerido || x.mes_fatura)} paga: a parcela vai para a próxima aberta`;
            }
            tr.append(celula('td', `${x.numero}/${x.total}`), comp, celula('td', moeda(x.valor), 'direita'));
        });
        const total = tabela.createTFoot().insertRow();
        total.append(celula('td', 'Total'), celula('td', ''), celula('td', moeda(p.soma), 'direita'));
        const rolagem = document.createElement('div');
        rolagem.className = 'lanc-previa-rolagem';
        rolagem.appendChild(tabela);
        const titulo = celula('div', 'Prévia das parcelas', 'lanc-previa-titulo');
        c.replaceChildren(titulo, rolagem);
        const notas = [];
        if (p.parcelas.some((x) => x.redirecionada)) notas.push('* fatura paga: a parcela vai para a próxima aberta.');
        if ((p.consolidadas || []).length) notas.push(`Fatura consolidada: ${p.consolidadas.map((f) => mesAno(f.competencia)).join(', ')} (pedirá confirmação ao salvar).`);
        if (notas.length) c.appendChild(celula('div', notas.join(' '), 'lanc-previa-nota'));
    }

    async function atualizar() {
        const c = caixa();
        if (!c) return;
        const d = dados();
        const pedido = ++estado.pedido;
        if (!d) {
            c.hidden = true;
            c.replaceChildren();
            return;
        }
        c.hidden = false;
        try {
            const r = await (await fetch(`/api/lancamentos/previa-parcelas?${new URLSearchParams(d)}`)).json();
            if (pedido !== estado.pedido) return;  // os campos mudaram durante a consulta
            if (!r.success) {
                c.replaceChildren(celula('div', r.error || 'Não foi possível calcular as parcelas.', 'lanc-previa-nota erro'));
                return;
            }
            desenhar(c, r.data);
        } catch (e) {
            if (pedido === estado.pedido) c.replaceChildren(celula('div', 'Não foi possível calcular as parcelas.', 'lanc-previa-nota erro'));
        }
    }

    function agendar() {
        clearTimeout(estado.temporizador);
        estado.temporizador = setTimeout(atualizar, 250);
    }
    window.atualizarPreviaParcelas = agendar;

    function iniciar() {
        CAMPOS.forEach((id) => {
            $(id)?.addEventListener('input', agendar);
            $(id)?.addEventListener('change', agendar);
        });
    }
    // A moldura pode carregar este script com o documento ja pronto (como js/lancamentos-abastecimento.js).
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
    else iniciar();
    // O mes da fatura tambem muda pela sugestao do fechamento e ao abrir o formulario (sem evento de campo).
    ['renderizarSugestaoFatura', 'abrirModalLancamento', 'cancelarLancamentoInline', 'alternarTipoLancamento'].forEach((nome) => {
        const original = window[nome];
        if (typeof original !== 'function') return;
        window[nome] = function (...args) {
            const r = original.apply(this, args);
            agendar();
            return r;
        };
    });
})();
