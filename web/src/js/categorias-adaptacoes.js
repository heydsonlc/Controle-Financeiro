// FIN-CADASTROS-PADRAO-01 — apresentacao do catalogo padrao e das personalizacoes na tela original de Categorias
// (js/original/categorias.js nao muda). Script classico, depois do original: decora o que ele desenha.
//  - Categoria de despesa: selo discreto "Padrão" (do aplicativo, fixa) ou "Minha" (particular, editavel). Editar e excluir
//    de uma categoria padrao so aparecem no modo "catalogo padrao", que so existe para quem administra o catalogo.
//  - Palavras-chave: as padrao e as proprias na mesma lista; a propria tem um ponto; a padrao desligada pelo usuario fica
//    riscada e o botao a restaura. Nenhuma acao comum altera o catalogo do aplicativo.
//  - Categoria do cartao padrao: selo "Padrão"; nome e situacao protegidos (o banco recusa).
//  - Natureza gerencial (Consumo, Aporte...) no formulario: da particular, o dono; da padrao, so no modo catalogo padrao.
// Sem innerHTML: so createElement e classes (CSP).
(function () {
    'use strict';
    if (typeof estadoCategorias === 'undefined') return;

    const NATUREZAS = [['CONSUMO', 'Consumo'], ['APORTE', 'Aporte'], ['AJUSTE_TECNICO', 'Ajuste técnico'],
        ['TRANSFERENCIA_INTERNA', 'Transferência interna'], ['NAO_DEFINIDO', 'Não definido']];
    const nomeDaNatureza = (codigo) => (NATUREZAS.find(([c]) => c === codigo) || [null, 'Consumo'])[1];
    const modoPadrao = () => document.body.classList.contains('cf-modo-catalogo-padrao');
    const despesa = (id) => estadoCategorias.categoriasDespesa.find((c) => c.id === Number(id));

    function selo(texto, classe, titulo) {
        const s = document.createElement('span');
        s.className = `cf-selo-catalogo ${classe}`;
        s.textContent = texto;
        if (titulo) s.title = titulo;
        return s;
    }

    function decorarLista() {
        document.querySelectorAll('#categorias-lista [data-categoria-despesa-id]').forEach((botao) => {
            const c = despesa(botao.dataset.categoriaDespesaId);
            const alvo = botao.querySelector('.despesa-list-main strong');
            if (!c || !alvo || alvo.querySelector('.cf-selo-catalogo')) return;
            alvo.append(c.padrao ? selo('Padrão', 'padrao', 'Categoria padrão do aplicativo') : selo('Minha', 'minha', 'Categoria particular: só você a vê'));
        });
    }

    function decorarDetalhe() {
        const detalhe = document.getElementById('categoria-despesa-detalhe');
        const c = despesa(estadoCategorias.categoriaDespesaSelecionadaId);
        if (!detalhe || !c) return;
        detalhe.dataset.padrao = c.padrao ? 'sim' : 'nao';
        const titulo = detalhe.querySelector('.detail-identity h2');
        if (titulo && !titulo.querySelector('.cf-selo-catalogo')) {
            titulo.append(c.padrao ? selo('Padrão', 'padrao', 'Categoria padrão do aplicativo: nome e dados fixos')
                : selo('Minha', 'minha', 'Categoria particular: só você a vê e pode alterá-la'));
        }
        const grade = detalhe.querySelector('.despesa-data-grid');
        if (grade && !grade.querySelector('.cf-natureza')) {
            const linha = document.createElement('div');
            linha.className = 'cf-natureza';
            const rotulo = document.createElement('small');
            rotulo.textContent = 'Natureza gerencial';
            const valor = document.createElement('strong');
            valor.textContent = nomeDaNatureza(c.natureza);
            linha.append(rotulo, valor);
            grade.append(linha);
        }
        const palavras = estadoCategorias.palavrasPorCategoria.get(c.id) || [];
        detalhe.querySelectorAll('.keyword-chip [data-palavra-id]').forEach((botao) => {
            const p = palavras.find((x) => String(x.id) === botao.dataset.palavraId);
            const chip = botao.closest('.keyword-chip');
            if (!p || !chip || chip.dataset.origem) return;
            chip.dataset.origem = p.origem || 'PADRAO';
            if (p.origem === 'DESLIGADA') {
                chip.title = 'Palavra padrão desligada só para você';
                botao.textContent = '↺';
                botao.setAttribute('aria-label', `Restaurar palavra-chave ${p.palavra}`);
                botao.title = 'Restaurar';
            } else if (p.origem === 'PROPRIA') {
                chip.title = 'Palavra-chave sua';
            } else if (p.origem === 'REASSOCIADA') {
                chip.title = 'Palavra padrão que você trouxe para esta categoria';
            } else if (!modoPadrao()) {
                botao.title = 'Desligar só para mim';
                botao.setAttribute('aria-label', `Desligar para mim a palavra-chave ${p.palavra}`);
            }
        });
        const nota = detalhe.querySelector('.keywords-card .card-title-inline p');
        if (nota && !nota.dataset.cf) {
            nota.dataset.cf = '1';
            nota.textContent = modoPadrao()
                ? 'Modo catálogo padrão: o que você adicionar ou remover vale para todos os usuários que não personalizaram a palavra.'
                : 'As palavras padrão vêm do aplicativo. O que você adicionar, desligar ou restaurar vale só para a sua conta.';
        }
    }

    function decorarCartao() {
        document.querySelectorAll('#categorias-cartao-lista [data-categoria-cartao-id]').forEach((botao) => {
            const c = estadoCategorias.categoriasCartao.find((x) => x.id === Number(botao.dataset.categoriaCartaoId));
            const alvo = botao.querySelector('strong');
            if (!c || !c.padrao || !alvo || alvo.querySelector('.cf-selo-catalogo')) return;
            alvo.append(selo('Padrão', 'padrao', 'Categoria padrão do aplicativo: nome e situação fixos'));
        });
        const detalhe = document.getElementById('categoria-cartao-detalhe');
        const sel = estadoCategorias.categoriasCartao.find((x) => x.id === estadoCategorias.categoriaCartaoSelecionadaId);
        if (detalhe) detalhe.dataset.padrao = sel && sel.padrao && !estadoCategorias.criandoCategoriaCartao ? 'sim' : 'nao';
    }

    // Natureza no formulario da categoria de despesa (lida pelo adaptador ao salvar).
    function campoNatureza() {
        const form = document.getElementById('form-categoria');
        if (!form || document.getElementById('cf-natureza')) return;
        const grupo = document.createElement('div');
        grupo.className = 'form-group cf-natureza-campo';
        const rotulo = document.createElement('label');
        rotulo.htmlFor = 'cf-natureza';
        rotulo.textContent = 'Natureza gerencial';
        const select = document.createElement('select');
        select.id = 'cf-natureza';
        for (const [valor, texto] of NATUREZAS) {
            const o = document.createElement('option');
            o.value = valor;
            o.textContent = texto;
            select.append(o);
        }
        const ajuda = document.createElement('small');
        ajuda.textContent = 'Como a categoria entra no Dashboard: consumo, aportes ou outras saídas. Não altera valores nem pagamentos.';
        grupo.append(rotulo, select, ajuda);
        const ativo = document.getElementById('ativo');
        const antes = ativo ? ativo.closest('.form-group') : null;
        if (antes) antes.before(grupo); else form.append(grupo);
    }
    function ajustarFormulario() {
        campoNatureza();
        const id = Number(document.getElementById('categoria-id').value) || null;
        const c = id ? despesa(id) : null;
        document.getElementById('cf-natureza').value = (c && c.natureza) || 'CONSUMO';
        const titulo = document.getElementById('modal-titulo');
        if (titulo && !id) titulo.textContent = modoPadrao() ? 'Nova Categoria Padrão do aplicativo' : 'Nova Categoria de Despesa (particular)';
    }
    for (const nome of ['abrirModalCategoriaDespesa', 'editarCategoria']) {
        const original = window[nome];
        if (typeof original !== 'function') continue;
        window[nome] = function (...args) {
            const r = original.apply(this, args);
            Promise.resolve(r).then(ajustarFormulario);
            return r;
        };
    }

    function decorar() {
        decorarLista();
        decorarDetalhe();
        decorarCartao();
    }
    document.addEventListener('DOMContentLoaded', () => {
        const alvo = document.querySelector('.categorias-page') || document.body;
        new MutationObserver(decorar).observe(alvo, { childList: true, subtree: true });
        decorar();
    });
    // O adaptador chama depois de trocar o modo (os textos e botoes dependem dele).
    window.CF_REDESENHAR_CATEGORIAS = () => { if (typeof renderizarTelaCategorias === 'function') renderizarTelaCategorias(); };
}());
