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


    // ---------------------------------------------------------------------------------------------------------------
    // FIN-MULTIUSUARIO-AJUSTES-FINAIS-01 — "Alterar categoria" da palavra-chave.
    // O usuario seleciona a palavra (clique no texto dela); abaixo da lista aparecem as acoes daquela palavra, em botoes
    // pequenos com icone e texto. "Alterar categoria" abre um modal simples com as categorias que ele pode usar. A mudanca
    // vale so para a conta dele: a palavra padrao vira uma personalizacao (o catalogo do aplicativo nao muda) e pode ser
    // restaurada; a palavra propria so muda de categoria.
    // ---------------------------------------------------------------------------------------------------------------
    let palavraSelecionada = null;  // { categoriaId, id }
    const somenteLeitura = () => document.body.classList.contains('cf-somente-leitura');
    const DESCRICAO = {
        PADRAO: 'palavra padrão do aplicativo',
        PROPRIA: 'palavra sua',
        REASSOCIADA: 'palavra padrão que você trouxe para esta categoria',
        DESLIGADA: 'palavra padrão desligada só para você',
        MOVIDA: 'palavra padrão que você levou para outra categoria',
    };

    function botaoDeAcao(icone, texto, classe, aoClicar) {
        const b = document.createElement('button');
        b.type = 'button';
        b.className = `cf-acao-palavra ${classe}`.trim();
        const i = document.createElement('span');
        i.setAttribute('aria-hidden', 'true');
        i.textContent = icone;
        const t = document.createElement('span');
        t.textContent = texto;
        b.append(i, t);
        b.addEventListener('click', aoClicar);
        return b;
    }

    function barraDeAcoes(detalhe, c, palavras) {
        const cartao = detalhe.querySelector('.keywords-card');
        const lista = cartao && cartao.querySelector('.keyword-chip-list');
        if (!lista) return;
        const p = palavraSelecionada && palavraSelecionada.categoriaId === c.id ? palavras.find((x) => x.id === palavraSelecionada.id) : null;
        const assinatura = p && !modoPadrao() && !somenteLeitura() ? `${c.id}:${p.id}:${p.origem}` : '';
        const atual = cartao.querySelector('#cf-acoes-palavra');
        if ((atual ? atual.dataset.assinatura : '') === assinatura) return;  // ja esta certa (o observador chama varias vezes)
        if (atual) atual.remove();
        if (!assinatura) return;
        const barra = document.createElement('div');
        barra.id = 'cf-acoes-palavra';
        barra.className = 'cf-acoes-palavra';
        barra.dataset.assinatura = assinatura;
        barra.setAttribute('role', 'group');
        barra.setAttribute('aria-label', `Ações da palavra-chave ${p.palavra}`);
        const rotulo = document.createElement('span');
        rotulo.className = 'cf-acoes-palavra-rotulo';
        const nome = document.createElement('strong');
        nome.textContent = p.palavra;
        const tipo = document.createElement('small');
        const outra = p.origem === 'MOVIDA' ? despesa(p.categoria_destino_id) : (p.origem === 'REASSOCIADA' ? despesa(p.categoria_padrao_id) : null);
        tipo.textContent = (DESCRICAO[p.origem] || DESCRICAO.PADRAO)
            + (outra ? (p.origem === 'MOVIDA' ? `: ${outra.nome}` : ` (padrão: ${outra.nome})`) : '');
        rotulo.append(nome, tipo);
        barra.append(rotulo);
        const botaoDoChip = [...lista.querySelectorAll('[data-palavra-id]')].find((b) => b.dataset.palavraId === String(p.id));
        const peloChip = () => { if (botaoDoChip) botaoDoChip.click(); };
        if (p.origem !== 'DESLIGADA' && p.origem !== 'MOVIDA') {
            barra.append(botaoDeAcao('⇄', 'Alterar categoria', 'principal', () => abrirModalPalavra(c, p)));
        }
        if (p.origem === 'PADRAO' || !p.origem) barra.append(botaoDeAcao('⊘', 'Desativar para mim', '', peloChip));
        else if (p.origem === 'PROPRIA') barra.append(botaoDeAcao('×', 'Remover', 'perigo', peloChip));
        else barra.append(botaoDeAcao('↺', 'Restaurar padrão', '', peloChip));
        lista.after(barra);
    }

    function prepararChips(detalhe, c, palavras) {
        detalhe.querySelectorAll('.keyword-chip').forEach((chip) => {
            const botao = chip.querySelector('[data-palavra-id]');
            if (!botao) return;
            const id = Number(botao.dataset.palavraId);
            chip.dataset.selecionada = palavraSelecionada && palavraSelecionada.categoriaId === c.id && palavraSelecionada.id === id ? 'sim' : 'nao';
            if (chip.dataset.cfSelecao) return;
            chip.dataset.cfSelecao = '1';
            if (modoPadrao() || somenteLeitura()) return;
            chip.tabIndex = 0;
            chip.setAttribute('role', 'button');
            const selecionar = (evento) => {
                if (evento.target.closest('button')) return;  // o botao proprio do chip segue como era
                if (evento.type === 'keydown' && evento.key !== 'Enter' && evento.key !== ' ') return;
                evento.preventDefault();
                const mesma = palavraSelecionada && palavraSelecionada.categoriaId === c.id && palavraSelecionada.id === id;
                palavraSelecionada = mesma ? null : { categoriaId: c.id, id };
                prepararChips(detalhe, c, palavras);
                barraDeAcoes(detalhe, c, palavras);
            };
            chip.addEventListener('click', selecionar);
            chip.addEventListener('keydown', selecionar);
        });
    }

    function elemento(tag, classe, texto) {
        const e = document.createElement(tag);
        if (classe) e.className = classe;
        if (texto !== undefined) e.textContent = texto;
        return e;
    }

    function modalPalavra() {
        let modal = document.getElementById('cf-modal-palavra');
        if (modal) return modal;
        modal = elemento('div', 'modal modal-sm');
        modal.id = 'cf-modal-palavra';
        const conteudo = elemento('div', 'modal-content');
        const cabeca = elemento('div', 'modal-header');
        const titulo = elemento('h2', '', 'Alterar categoria da palavra-chave');
        titulo.id = 'cf-modal-palavra-titulo';
        const fechar = elemento('button', 'modal-close', '×');
        fechar.type = 'button';
        fechar.setAttribute('aria-label', 'Fechar');
        cabeca.append(titulo, fechar);
        const form = elemento('form');
        form.id = 'cf-form-palavra';
        form.noValidate = true;  // a mensagem e a da tela (em portugues, no proprio modal)
        const texto = elemento('p', 'cf-modal-palavra-texto');
        texto.id = 'cf-modal-palavra-texto';
        const grupo = elemento('div', 'form-group');
        const rotulo = elemento('label', '', 'Nova categoria');
        rotulo.htmlFor = 'cf-palavra-destino';
        const select = elemento('select');
        select.id = 'cf-palavra-destino';
        grupo.append(rotulo, select);
        const nota = elemento('small', 'cf-modal-palavra-nota', 'Vale só para a sua conta. Despesas e compras já classificadas não mudam.');
        const erro = elemento('div', 'cf-modal-palavra-erro');
        erro.id = 'cf-modal-palavra-erro';
        erro.setAttribute('role', 'alert');
        erro.hidden = true;
        const acoes = elemento('div', 'form-actions');
        const cancelar = elemento('button', 'cf-button cf-button-secondary', 'Cancelar');
        cancelar.type = 'button';
        cancelar.id = 'cf-modal-palavra-cancelar';
        const confirmar = elemento('button', 'cf-button cf-button-primary', 'Confirmar');
        confirmar.type = 'submit';
        confirmar.id = 'cf-modal-palavra-confirmar';
        acoes.append(cancelar, confirmar);
        form.append(texto, grupo, nota, erro, acoes);
        conteudo.append(cabeca, form);
        modal.append(conteudo);
        modal.setAttribute('role', 'dialog');
        modal.setAttribute('aria-modal', 'true');
        modal.setAttribute('aria-labelledby', 'cf-modal-palavra-titulo');
        document.body.append(modal);
        const fecharModal = () => modal.classList.remove('open');
        fechar.addEventListener('click', fecharModal);
        cancelar.addEventListener('click', fecharModal);
        modal.addEventListener('click', (evento) => { if (evento.target === modal) fecharModal(); });
        document.addEventListener('keydown', (evento) => { if (evento.key === 'Escape') fecharModal(); });
        form.addEventListener('submit', confirmarAlteracao);
        return modal;
    }

    function abrirModalPalavra(c, p) {
        const modal = modalPalavra();
        modal.dataset.categoriaId = String(c.id);
        modal.dataset.palavraId = String(p.id);
        document.getElementById('cf-modal-palavra-texto').textContent = `“${p.palavra}” hoje sugere a categoria ${c.nome}.`;
        const select = document.getElementById('cf-palavra-destino');
        select.replaceChildren();
        const vazio = elemento('option', '', 'Selecione a categoria');
        vazio.value = '';
        select.append(vazio);
        // so as categorias que o usuario pode usar: ativas, padrao ou dele (as de outro usuario nem chegam a tela)
        [...estadoCategorias.categoriasDespesa].filter((x) => x.ativo !== false && x.id !== c.id)
            .sort((a, b) => String(a.nome).localeCompare(String(b.nome), 'pt-BR'))
            .forEach((x) => {
                const o = elemento('option', '', x.nome + (x.padrao === false ? ' (minha)' : '')
                    + (p.origem === 'REASSOCIADA' && x.id === p.categoria_padrao_id ? ' — categoria padrão (restaura)' : ''));
                o.value = String(x.id);
                select.append(o);
            });
        document.getElementById('cf-modal-palavra-erro').hidden = true;
        modal.classList.add('open');
        select.focus();
    }

    async function confirmarAlteracao(evento) {
        evento.preventDefault();
        const modal = document.getElementById('cf-modal-palavra');
        const erro = document.getElementById('cf-modal-palavra-erro');
        const destino = Number(document.getElementById('cf-palavra-destino').value);
        erro.hidden = true;
        if (!destino) {
            erro.textContent = 'Selecione a nova categoria.';
            erro.hidden = false;
            return;
        }
        const confirmar = document.getElementById('cf-modal-palavra-confirmar');
        confirmar.disabled = true;
        try {
            const resposta = await fetchJson(`${API_CATEGORIAS}/${modal.dataset.categoriaId}/palavras-chave/${modal.dataset.palavraId}/categoria`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ categoria_id: destino }),
            });
            modal.classList.remove('open');
            await carregarPalavrasChaveCategorias();
            // a tela vai para a categoria de destino, com a palavra ja selecionada: o usuario ve onde ela ficou
            estadoCategorias.categoriaDespesaSelecionadaId = destino;
            palavraSelecionada = resposta && resposta.data && resposta.data.id ? { categoriaId: destino, id: resposta.data.id } : null;
            renderizarTelaCategorias();
        } catch (falha) {
            erro.textContent = falha.message || 'Não foi possível alterar a categoria. Nada foi gravado.';
            erro.hidden = false;
        } finally {
            confirmar.disabled = false;
        }
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
                const origem = despesa(p.categoria_padrao_id);
                chip.title = `Palavra padrão que você trouxe para esta categoria${origem ? ` (padrão: ${origem.nome})` : ''}`;
                botao.textContent = '↺';
                botao.setAttribute('aria-label', `Restaurar a categoria padrão da palavra-chave ${p.palavra}`);
                botao.title = 'Restaurar a categoria padrão';
            } else if (p.origem === 'MOVIDA') {
                const destino = despesa(p.categoria_destino_id);
                chip.title = `Palavra padrão que você levou para ${destino ? destino.nome : 'outra categoria'}`;
                botao.textContent = '↺';
                botao.setAttribute('aria-label', `Restaurar a categoria padrão da palavra-chave ${p.palavra}`);
                botao.title = 'Restaurar a categoria padrão';
            } else if (!modoPadrao()) {
                botao.title = 'Desligar só para mim';
                botao.setAttribute('aria-label', `Desligar para mim a palavra-chave ${p.palavra}`);
            }
        });
        prepararChips(detalhe, c, palavras);
        barraDeAcoes(detalhe, c, palavras);
        const nota = detalhe.querySelector('.keywords-card .card-title-inline p');
        if (nota && !nota.dataset.cf) {
            nota.dataset.cf = '1';
            nota.textContent = modoPadrao()
                ? 'Modo catálogo padrão: o que você adicionar ou remover vale para todos os usuários que não personalizaram a palavra.'
                : 'As palavras padrão vêm do aplicativo. Clique numa palavra para ver as ações. O que você adicionar, alterar, desligar ou restaurar vale só para a sua conta.';
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
