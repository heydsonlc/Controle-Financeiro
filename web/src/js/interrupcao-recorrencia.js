// FIN-RECORRENCIAS-INATIVACAO-01 (P22) — modal compacto da interrupcao e da retomada de uma recorrencia, comum a
// Recorrencias (Inativar / Reativar) e a Despesas ("Excluir esta e as futuras"). Mostra, antes de confirmar, o que
// deixa de ser exigivel (quantidade, valor, competencias) e o que fica protegido (pago, com movimento, vencido, cobranca
// real); a confirmacao leva a versao e a quantidade da previa (o banco recusa se algo mudou).
// Script classico. CSP: o HTML e montado por createElement e os botoes recebem addEventListener (sem atributo de evento).
(function () {
    'use strict';

    const moeda = (v) => Number(v || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
    const mesAno = (iso) => (iso ? `${String(iso).slice(5, 7)}/${String(iso).slice(0, 4)}` : '—');
    const dataBr = (iso) => (iso ? `${String(iso).slice(8, 10)}/${String(iso).slice(5, 7)}/${String(iso).slice(0, 4)}` : '—');

    function el(tag, classe, texto) {
        const e = document.createElement(tag);
        if (classe) e.className = classe;
        if (texto !== undefined && texto !== null) e.textContent = texto;
        return e;
    }

    function tabela(colunas, linhas) {
        const t = el('table', 'cf-int-tabela');
        const cab = t.createTHead().insertRow();
        colunas.forEach(([rotulo, classe]) => cab.appendChild(el('th', classe || '', rotulo)));
        const corpo = t.createTBody();
        linhas.forEach((valores) => {
            const tr = corpo.insertRow();
            valores.forEach((v, i) => tr.appendChild(el('td', colunas[i][1] || '', v)));
        });
        const caixa = el('div', 'cf-int-rolagem');
        caixa.appendChild(t);
        return caixa;
    }

    // Moldura do modal; resolve com o valor de aoConfirmar (ou null ao cancelar).
    function moldura(titulo) {
        const fundo = el('div', 'cf-int-fundo');
        fundo.setAttribute('role', 'dialog');
        fundo.setAttribute('aria-modal', 'true');
        const caixa = el('div', 'cf-int-caixa');
        const topo = el('div', 'cf-int-topo');
        topo.appendChild(el('h3', '', titulo));
        const fechar = el('button', 'cf-int-fechar', '×');
        fechar.type = 'button';
        fechar.setAttribute('aria-label', 'Fechar');
        topo.appendChild(fechar);
        const corpo = el('div', 'cf-int-corpo');
        const aviso = el('div', 'cf-int-aviso');
        aviso.hidden = true;
        const rodape = el('div', 'cf-int-rodape');
        const cancelar = el('button', 'cf-int-botao secundario', 'Cancelar');
        cancelar.type = 'button';
        const confirmar = el('button', 'cf-int-botao', 'Confirmar');
        confirmar.type = 'button';
        rodape.append(cancelar, confirmar);
        caixa.append(topo, corpo, aviso, rodape);
        fundo.appendChild(caixa);
        document.body.appendChild(fundo);
        return { fundo, corpo, aviso, cancelar, confirmar, fechar };
    }

    function erroDe(r) {
        return (r && (r.error || r.message)) || 'Não foi possível concluir. Tente de novo.';
    }

    // opcoes: { titulo, rotulo, buscar(efeito) -> {success,data} | previa (ja buscada), executar(previa) -> {success,...},
    //           incluirAtual (oferece incluir a competencia atual) }
    function interromper(opcoes) {
        return new Promise((resolver) => {
            const m = moldura(opcoes.titulo || 'Inativar recorrência');
            let previa = null;
            let efeito = null;

            const fim = (valor) => { m.fundo.remove(); resolver(valor); };
            m.cancelar.addEventListener('click', () => fim(null));
            m.fechar.addEventListener('click', () => fim(null));

            function desenhar() {
                m.corpo.replaceChildren();
                const p = previa;
                const linha = (rotulo, valor) => {
                    const d = el('div', 'cf-int-linha');
                    d.append(el('span', '', rotulo), el('strong', '', valor));
                    return d;
                };
                m.corpo.append(linha('Recorrência', p.nome), linha('Data de efeito', `a partir de ${mesAno(p.efeito)}`));
                if (opcoes.incluirAtual && p.competencia_atual && p.efeito_padrao !== p.competencia_atual) {
                    const rot = el('label', 'cf-int-opcao');
                    const caixa = document.createElement('input');
                    caixa.type = 'checkbox';
                    caixa.checked = p.efeito === p.competencia_atual;
                    caixa.addEventListener('change', () => carregar(caixa.checked ? p.competencia_atual : null));
                    rot.append(caixa, el('span', '', `Incluir a competência atual (${mesAno(p.competencia_atual)}); as vencidas ficam`));
                    m.corpo.appendChild(rot);
                }
                m.corpo.appendChild(el('p', 'cf-int-resumo',
                    `${p.quantidade} ocorrência(s) deixam de ser exigíveis: ${moeda(p.total)}`));
                if (p.afetadas.length) {
                    m.corpo.appendChild(tabela([['Competência'], ['Vencimento'], ['Valor', 'direita']],
                        p.afetadas.map((a) => [mesAno(a.competencia), dataBr(a.data_vencimento), moeda(a.valor)])));
                }
                if (p.preservadas.length) {
                    m.corpo.appendChild(el('p', 'cf-int-subtitulo', `Permanecem (protegidas): ${p.preservadas.length} — ${moeda(p.total_preservado)}`));
                    m.corpo.appendChild(tabela([['Competência'], ['Valor', 'direita'], ['Motivo']],
                        p.preservadas.map((a) => [mesAno(a.competencia), moeda(a.valor), a.motivo])));
                }
                m.aviso.hidden = true;
                m.confirmar.textContent = opcoes.rotulo || (p.ativo ? 'Inativar' : 'Cancelar ocorrências');
                m.confirmar.className = 'cf-int-botao perigo';
                if (!p.pode_interromper) {
                    m.aviso.textContent = p.motivo || 'Esta recorrência não pode ser alterada aqui.';
                    m.aviso.hidden = false;
                }
                m.confirmar.disabled = !p.pode_interromper || (!p.ativo && !p.quantidade && !opcoes.contaEscolhida);
            }

            async function carregar(novoEfeito) {
                m.confirmar.disabled = true;
                try {
                    const r = typeof opcoes.buscar === 'function' ? await opcoes.buscar(novoEfeito) : { success: true, data: opcoes.previa };
                    if (!r || !r.success) throw new Error(erroDe(r));
                    previa = r.data;
                    efeito = previa.efeito;
                    desenhar();
                } catch (e) {
                    m.aviso.textContent = e.message;
                    m.aviso.hidden = false;
                }
            }

            m.confirmar.addEventListener('click', async () => {
                if (!previa) return;
                m.confirmar.disabled = true;
                m.cancelar.disabled = true;
                try {
                    const r = await opcoes.executar({ ...previa, efeito });
                    if (!r || !r.success) throw new Error(erroDe(r));
                    fim(r);
                } catch (e) {
                    m.aviso.textContent = e.message;
                    m.aviso.hidden = false;
                    m.cancelar.disabled = false;
                    m.confirmar.disabled = false;
                }
            });
            carregar(null);
        });
    }

    // opcoes: { buscar(retomada 'YYYY-MM-01' | null) -> {success,data}, executar(previa, restaurar) -> {success,...} }
    function retomar(opcoes) {
        return new Promise((resolver) => {
            const m = moldura('Reativar recorrência');
            let previa = null;
            let restaurar = false;

            const fim = (valor) => { m.fundo.remove(); resolver(valor); };
            m.cancelar.addEventListener('click', () => fim(null));
            m.fechar.addEventListener('click', () => fim(null));

            function desenhar() {
                const p = previa;
                m.corpo.replaceChildren();
                const linha = el('div', 'cf-int-linha');
                linha.append(el('span', '', 'Recorrência'), el('strong', '', p.nome));
                const rotMes = el('label', 'cf-int-linha');
                const campo = document.createElement('input');
                campo.type = 'month';
                campo.className = 'cf-int-mes';
                campo.value = String(p.retomada).slice(0, 7);
                campo.addEventListener('change', () => { if (/^\d{4}-\d{2}$/.test(campo.value)) carregar(`${campo.value}-01`); });
                rotMes.append(el('span', '', 'Retomar a partir de'), campo);
                m.corpo.append(linha, rotMes);
                m.corpo.appendChild(el('p', 'cf-int-resumo', p.quantidade_lacunas
                    ? `${p.quantidade_lacunas} ocorrência(s) do período inativo não serão geradas: ${p.lacunas.map((l) => mesAno(l.competencia)).filter((v, i, a) => a.indexOf(v) === i).join(', ')}`
                    : 'Nenhuma ocorrência do período inativo ficaria para trás.'));
                if (p.quantidade_restauraveis) {
                    const rot = el('label', 'cf-int-opcao');
                    const caixa = document.createElement('input');
                    caixa.type = 'checkbox';
                    caixa.checked = restaurar;
                    caixa.addEventListener('change', () => { restaurar = caixa.checked; });
                    rot.append(caixa, el('span', '', `Restaurar as ${p.quantidade_restauraveis} ocorrência(s) canceladas pela inativação `
                        + `(${p.restauraveis.map((r) => mesAno(r.competencia)).join(', ')}; cerca de ${moeda(p.total_restauravel)})`));
                    m.corpo.appendChild(rot);
                }
                if (p.dispensadas_mantidas) {
                    m.corpo.appendChild(el('p', 'cf-int-subtitulo', `${p.dispensadas_mantidas} ocorrência(s) excluída(s) uma a uma continuam excluídas.`));
                }
                m.confirmar.textContent = 'Reativar';
                m.confirmar.className = 'cf-int-botao primario';
                m.aviso.hidden = true;
                if (!p.pode_retomar) {
                    m.aviso.textContent = p.motivo || 'Esta recorrência não pode ser alterada aqui.';
                    m.aviso.hidden = false;
                }
                m.confirmar.disabled = !p.pode_retomar;
            }

            async function carregar(retomada) {
                m.confirmar.disabled = true;
                try {
                    const r = await opcoes.buscar(retomada);
                    if (!r || !r.success) throw new Error(erroDe(r));
                    previa = r.data;
                    desenhar();
                } catch (e) {
                    m.aviso.textContent = e.message;
                    m.aviso.hidden = false;
                }
            }

            m.confirmar.addEventListener('click', async () => {
                if (!previa) return;
                m.confirmar.disabled = true;
                m.cancelar.disabled = true;
                try {
                    const r = await opcoes.executar(previa, restaurar);
                    if (!r || !r.success) throw new Error(erroDe(r));
                    fim(r);
                } catch (e) {
                    m.aviso.textContent = e.message;
                    m.aviso.hidden = false;
                    m.cancelar.disabled = false;
                    m.confirmar.disabled = false;
                }
            });
            carregar(null);
        });
    }

    window.CFInterrupcao = { interromper, retomar };
})();
