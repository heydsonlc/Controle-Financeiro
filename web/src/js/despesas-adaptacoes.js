// FIN-FIDELIDADE-DESPESAS-1 — o minimo que a tela original de Despesas (js/original/despesas.js, sem alteracao)
// precisa para as regras do novo aplicativo. Script classico, carregado depois do original: substitui so as
// funcoes abaixo, cada uma com o motivo.
(function () {
    'use strict';

    const MES = /^\d{4}-(0[1-9]|1[0-2])$/;

    // 1. Competencia. O Flask devolvia todos os meses e a tela filtrava; o Supabase devolve o mes pedido (contas_do_mes).
    //    Trocar a competencia recarrega o mes. Ao abrir, vale o ?mes= do menu (competencia mantida na navegacao).
    document.addEventListener('DOMContentLoaded', () => {
        const filtro = document.getElementById('filtro-competencia');
        const pedido = new URLSearchParams(window.location.search).get('mes');
        if (MES.test(pedido || '')) {
            filtro.value = `${pedido.slice(5, 7)}/${pedido.slice(0, 4)}`;
            window.carregarDespesas();
        }
        filtro.addEventListener('change', () => {
            if (/^(0[1-9]|1[0-2])\/\d{4}$/.test(filtro.value)) window.carregarDespesas();
        });
        const valorPago = document.getElementById('pagar-valor-pago');
        if (valorPago) valorPago.addEventListener('input', atualizarAjuste);
    });

    // Marca o mes cuja listagem terminou de carregar (a tela pode pedir dois meses seguidos ao abrir).
    const carregarOriginal = window.carregarDespesas;
    window.carregarDespesas = async function carregarDespesas() {
        const competencia = document.getElementById('filtro-competencia').value;  // a do pedido, nao a do fim
        await carregarOriginal();
        document.getElementById('despesas-lista').dataset.competenciaCarregada = competencia;
    };

    // 3. "A partir de documento": o seletor original (despesas.js) lista os documentos do perfil (FIN-PRE-PRODUCAO-1,
    //    js/documento-financeiro.js); nada a adaptar aqui.

    // 2. Pagamento (FIN-MOVIMENTACOES-1): o pagamento da despesa e integral. "Pagar outro Valor" continua, mas a
    //    diferenca para o devido exige classificacao (juros, desconto ou ajuste de quitacao) e justificativa.
    const AJUSTES = { JUROS: 'Juros ou multa', DESCONTO: 'Desconto', AJUSTE: 'Ajuste de quitação integral' };

    function diferencaDoDevido() {
        const outro = document.querySelector('input[name="tipo-pagamento"]:checked')?.value === 'parcial';
        const previsto = Math.round(Number(document.getElementById('pagar-valor-previsto').value || 0) * 100);
        const pago = Math.round(Number(document.getElementById('pagar-valor-pago').value || 0) * 100);
        return outro && pago > 0 ? pago - previsto : 0;
    }

    function atualizarAjuste() {
        const caixa = document.getElementById('pagar-ajuste');
        const tipo = document.getElementById('pagar-ajuste-tipo');
        const diferenca = diferencaDoDevido();
        caixa.hidden = diferenca === 0;
        const opcoes = diferenca > 0 ? ['JUROS', 'AJUSTE'] : ['DESCONTO', 'AJUSTE'];
        const atual = tipo.value;
        tipo.replaceChildren(new Option('Selecione...', ''), ...opcoes.map((t) => new Option(AJUSTES[t], t)));
        if (opcoes.includes(atual)) tipo.value = atual;
    }

    const alternarOriginal = window.alternarCampoValor;
    window.alternarCampoValor = function alternarCampoValor() {
        alternarOriginal();
        atualizarAjuste();
    };

    const fecharPagarOriginal = window.fecharModalPagar;
    window.fecharModalPagar = function fecharModalPagar() {
        fecharPagarOriginal();
        document.getElementById('pagar-ajuste').hidden = true;
        document.getElementById('pagar-ajuste-justificativa').value = '';
    };

    // Copia de confirmarPagamento do original; acrescimos marcados com "Ajuste".
    window.confirmarPagamento = async function confirmarPagamento(event) {
        event.preventDefault();
        const id = document.getElementById('pagar-despesa-id').value;
        const tipoPagamento = document.querySelector('input[name="tipo-pagamento"]:checked').value;
        const dataPagamento = document.getElementById('pagar-data').value;
        const contaBancariaId = document.getElementById('pagar-conta-bancaria')?.value;
        let valorPago;
        if (tipoPagamento === 'total') {
            valorPago = null;
        } else {
            valorPago = parseFloat(document.getElementById('pagar-valor-pago').value);
            if (!valorPago || valorPago <= 0) {
                alert('Por favor, informe um valor válido');
                return;
            }
        }
        const payload = { data_pagamento: dataPagamento };
        if (!contaBancariaId) {
            alert('Selecione a conta bancária para executar o pagamento.');
            return;
        }
        payload.conta_bancaria_id = parseInt(contaBancariaId, 10);
        if (valorPago !== null) payload.valor_pago = valorPago;
        // Ajuste: diferenca classificada e justificada.
        if (diferencaDoDevido() !== 0) {
            const tipoAjuste = document.getElementById('pagar-ajuste-tipo').value;
            const justificativa = document.getElementById('pagar-ajuste-justificativa').value.trim();
            if (!tipoAjuste || !justificativa) {
                alert('Classifique a diferença e escreva a justificativa.');
                return;
            }
            payload.tipo_ajuste = tipoAjuste;
            payload.justificativa = justificativa;
        }
        const botao = document.querySelector('#form-pagar button[type="submit"]');
        if (botao) botao.disabled = true;  // Ajuste: evita duplo envio (o banco tambem protege pela chave)
        try {
            const response = await fetch(`${API_URL}/${id}/pagar`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await response.json();
            if (!data.success) {
                alert('Erro ao marcar como pago: ' + data.error);
                return;
            }
            alert(data.message || 'Despesa marcada como paga!');  // Ajuste: a mensagem informa a conta e o saldo
            window.fecharModalPagar();
            window.carregarDespesas();
        } catch (error) {
            console.error('Erro ao marcar despesa como paga:', error);
            alert('Erro ao marcar despesa como paga. Por favor, tente novamente.');
        } finally {
            if (botao) botao.disabled = false;
        }
    };

    // 4. Pagamento em lote (FIN-DESPESAS-PAGAMENTO-LOTE-01, P20). O original confirmava com confirm() e marcava cada ocorrencia
    //    como paga pela edicao (PUT /api/despesas/<id> com pago=true), que o novo aplicativo recusa de proposito: o pagamento
    //    escolhe a conta e registra o movimento. Aqui um modal com a conta de debito; o banco paga todas as pendentes pelo
    //    pagamento individual, numa so transacao, e confere de novo quantidade, valores e situacao.
    //    FIN-DESPESAS-PAGAMENTO-LOTE-02 (P21): o botao do original passa a POSICAO do agrupador na lista desenhada (ja
    //    filtrada por situacao, forma, vencimento ou busca), mas o original procurava essa posicao na lista inteira do mes;
    //    com um filtro a ordem muda e o modal abria outra recorrencia (Diarista abria Psicologa). Agora cada desenho guarda a
    //    identidade (nome e competencia) de cada posicao desenhada; o lote acha as ocorrencias por ela, confere de novo na
    //    confirmacao e envia a identidade, que o banco compara com as ocorrencias (LOTE_IDENTIDADE).
    const lote = { ocorrencias: [], identidade: null, enviando: false, pago: false };
    const desenhados = new Map();  // posicao do botao no ultimo desenho -> { nome, competencia }
    const desenharOriginal = window.renderizarDespesas;
    window.renderizarDespesas = function renderizarDespesas(lista) {
        desenhados.clear();  // o desenho troca a lista inteira: so valem as posicoes dele
        return desenharOriginal(lista);
    };
    const agrupadorOriginal = window.renderizarAgrupadorSemanal;
    window.renderizarAgrupadorSemanal = function renderizarAgrupadorSemanal(agrupador, index) {
        desenhados.set(index, { nome: agrupador.nome, competencia: agrupador.mes_competencia });
        return agrupadorOriginal(agrupador, index);
    };

    // Ocorrencias pendentes do agrupador com esta identidade, na lista inteira do mes (o banco exige todas as pendentes das
    // recorrencias na competencia, mesmo as escondidas por um filtro).
    function pendentesDoAgrupador(identidade) {
        // eslint-disable-next-line no-undef -- despesas e agruparDespesasSemanais sao do original (mesmo escopo global)
        const agrupador = agruparDespesasSemanais(despesas).find((a) => a.tipo === 'agrupador_semanal'
            && a.nome === identidade.nome && a.mes_competencia === identidade.competencia);
        return agrupador ? agrupador.ocorrencias.filter((o) => !o.pago && !o.cancelada) : null;
    }
    const idsDe = (ocorrencias) => ocorrencias.map((o) => o.id).sort((a, b) => a - b).join(',');
    const reaisBR = (v) => Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
    const $ = (id) => document.getElementById(id);

    function nomeDoMeio(meio) {
        const forma = meio && window.FormasPagamentoUI && window.FormasPagamentoUI.resolverFormaPagamento(meio);
        return (forma && forma.nome) || ({ pix: 'Pix', boleto: 'Boleto', debito: 'Débito', debito_automatico: 'Débito automático' }[meio]) || 'Não informado';
    }

    function mensagemLote(texto, tipo) {
        const el = $('pagar-lote-mensagem');
        el.textContent = texto || '';
        el.className = `pagar-lote-mensagem${tipo ? ` ${tipo}` : ''}`;
        el.hidden = !texto;
    }

    function fecharLote() {
        $('modal-pagar-lote').style.display = 'none';
        const recarregar = lote.pago;
        lote.ocorrencias = [];
        lote.identidade = null;
        lote.pago = false;
        if (recarregar) window.carregarDespesas();
    }

    async function contasDoLote(sugerida) {
        const select = $('pagar-lote-conta');
        let contas = [];
        try {
            const r = await fetch('/api/contas?status=ATIVO');
            const j = await r.json();
            contas = j.success ? (j.data || []) : [];
        } catch (erro) {
            contas = [];
        }
        const opcoes = [new Option('Selecione...', '')];
        for (const c of contas) opcoes.push(new Option(c.instituicao ? `${c.nome} (${c.instituicao})` : c.nome, String(c.id)));
        select.replaceChildren(...opcoes);
        if (sugerida && contas.some((c) => c.id === sugerida)) select.value = String(sugerida);
    }

    // FIN-RECORRENCIAS-INATIVACAO-01 (P22): exclusao de despesa recorrente.
    //    - Ao abrir a escolha, cada opcao que o banco recusaria fica visivel e desabilitada, com o motivo.
    //    - "Esta e as futuras" mostra antes o que deixa de ser exigivel e o que fica (js/interrupcao-recorrencia.js) e so
    //      entao interrompe a recorrencia (ativa ou ja inativa), com a quantidade da previa conferida no banco.
    const previaFuturas = async (id) => (await fetch(`/api/despesas/${id}/previa-futuras`)).json();

    const abrirExclusaoOriginal = window.deletarDespesaModal;
    window.deletarDespesaModal = function deletarDespesaModal() {
        abrirExclusaoOriginal();
        const id = window.despesaExcluindo;
        if (!id || window.tipoDespesaExcluindo !== 'recorrente') return;
        const botoes = [...document.querySelectorAll('#modal-tipo-exclusao [data-on-click^="confirmarTipoExclusao"]')];
        const botao = (tipo) => botoes.find((b) => b.dataset.onClick.includes(`'${tipo}'`));
        botoes.forEach((b) => { b.disabled = false; b.title = ''; });
        previaFuturas(id).then((r) => {
            if (!r.success || window.despesaExcluindo !== id) return;
            const motivo = r.data.motivo || '';
            if (!r.data.pode_excluir) {
                ['unica', 'futuras'].forEach((tipo) => { const b = botao(tipo); if (b) { b.disabled = true; b.title = motivo; } });
            } else if (!r.data.pode) {
                const b = botao('futuras');
                if (b) { b.disabled = true; b.title = motivo; }
            }
        }).catch(() => {});
    };

    const confirmarExclusaoOriginal = window.confirmarTipoExclusao;
    window.confirmarTipoExclusao = async function confirmarTipoExclusao(tipo) {
        const id = window.despesaExcluindo;
        if (tipo !== 'futuras' || window.tipoDespesaExcluindo !== 'recorrente' || !id) return confirmarExclusaoOriginal(tipo);
        window.fecharModalTipoExclusao();
        const r = await previaFuturas(id);
        if (!r.success) { alert(r.error || 'Não foi possível conferir as ocorrências futuras.'); return undefined; }
        if (!r.data.pode) { alert(`Não é possível excluir as futuras: ${r.data.motivo}`); return undefined; }
        const feito = await window.CFInterrupcao.interromper({
            titulo: 'Excluir esta e as futuras', rotulo: 'Excluir', previa: r.data, contaEscolhida: true,
            executar: async (p) => (await fetch(`/api/despesas/${id}?tipo_exclusao=futuras&esperadas=${p.quantidade}`, { method: 'DELETE' })).json(),
        });
        if (feito) {
            alert(feito.message);
            window.carregarDespesas();
        }
        return undefined;
    };

    window.pagarTodasOcorrencias = async function pagarTodasOcorrencias(index) {
        const identidade = desenhados.get(index);
        const pendentes = identidade && pendentesDoAgrupador(identidade);
        if (!pendentes) {
            alert('Erro: Agrupamento não encontrado. Atualize a lista e tente de novo.');
            return;
        }
        if (pendentes.length === 0) {
            alert('Todas as ocorrências já foram pagas!');
            return;
        }
        lote.ocorrencias = pendentes;
        lote.identidade = identidade;
        lote.pago = false;
        const total = pendentes.reduce((s, o) => s + Math.round(Number(o.valor) * 100), 0) / 100;
        $('pagar-lote-nome').textContent = identidade.nome;
        $('pagar-lote-competencia').textContent = identidade.competencia ? window.formatarCompetencia(identidade.competencia) : '';
        $('pagar-lote-meio').textContent = nomeDoMeio(pendentes[0].meio_pagamento);
        $('pagar-lote-quantidade').textContent = String(pendentes.length);
        $('pagar-lote-total').textContent = reaisBR(total);
        mensagemLote('');
        $('pagar-lote-confirmar').disabled = false;
        $('pagar-lote-confirmar').hidden = false;
        $('pagar-lote-cancelar').textContent = 'Cancelar';
        // conta sugerida: a mesma ja vinculada a todas as ocorrencias, se houver (o usuario pode trocar)
        const vinculadas = [...new Set(pendentes.map((o) => o.conta_bancaria_id).filter(Boolean))];
        await contasDoLote(vinculadas.length === 1 ? vinculadas[0] : null);
        $('modal-pagar-lote').style.display = 'block';
    };

    async function confirmarLote(event) {
        event.preventDefault();
        if (lote.enviando || lote.pago || !lote.ocorrencias.length) return;
        const conta = $('pagar-lote-conta').value;
        if (!conta) {
            mensagemLote('Selecione a conta bancária de débito.', 'erro');
            return;
        }
        // a lista pode ter sido recarregada com o modal aberto: as pendentes desta recorrencia tem de ser as que o modal mostra
        const agora = pendentesDoAgrupador(lote.identidade);
        if (!agora || idsDe(agora) !== idsDe(lote.ocorrencias)) {
            lote.pago = true;  // fechar recarrega a lista
            $('pagar-lote-confirmar').disabled = true;
            mensagemLote('Nenhuma ocorrência foi paga.\nA lista mudou desde a abertura. Feche e confira a lista atualizada antes de pagar de novo.', 'erro');
            return;
        }
        const total = lote.ocorrencias.reduce((s, o) => s + Math.round(Number(o.valor) * 100), 0);
        lote.enviando = true;
        $('pagar-lote-confirmar').disabled = true;
        mensagemLote('Pagando...');
        try {
            const r = await fetch('/api/despesas/pagar-lote', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ conta_bancaria_id: Number(conta),
                    itens: lote.ocorrencias.map((o) => ({ conta_id: o.id, valor_devido: Number(o.valor).toFixed(2) })),
                    // o que o modal mostrou: o banco recusa se as ocorrencias nao forem desta recorrencia e competencia
                    lote: { descricao: lote.identidade.nome, competencia: lote.identidade.competencia,
                        recorrencias: [...new Set(lote.ocorrencias.map((o) => o.item_despesa_id))].sort((a, b) => a - b),
                        quantidade: lote.ocorrencias.length, valor_total: (total / 100).toFixed(2) } }),
            });
            const j = await r.json().catch(() => ({}));
            if (!j.success) {
                const recarregar = ['LOTE_DESATUALIZADO', 'LOTE_IDENTIDADE', 'VALOR_MUDOU', 'DESPESA_PAGA'].includes(j.codigo);
                mensagemLote(`Nenhuma ocorrência foi paga.\n${String(j.error || 'Não foi possível pagar.').replace(/^Nenhuma ocorrência foi paga\.\s*/, '')}`
                    + (recarregar ? '\nFeche e confira a lista atualizada antes de pagar de novo.' : ''), 'erro');
                if (recarregar) lote.pago = true;  // fechar recarrega a lista
                $('pagar-lote-confirmar').disabled = recarregar;
                return;
            }
            const d = j.data;
            lote.pago = true;
            mensagemLote(`Pagamento em lote concluído\n${d.pagas} ocorrência(s) paga(s)\nValor total: ${reaisBR(d.valor_total)}\n`
                + `Conta de débito: ${d.conta_nome}\nSaldo da conta: ${reaisBR(d.saldo_conta)}`, 'ok');
            $('pagar-lote-confirmar').hidden = true;
            $('pagar-lote-cancelar').textContent = 'Fechar';
        } catch (erro) {
            // resultado desconhecido: nada e repetido sozinho; a lista mostra o que foi gravado
            lote.pago = true;
            mensagemLote('Não foi possível confirmar o resultado. Feche e confira a lista antes de tentar de novo.', 'erro');
        } finally {
            lote.enviando = false;
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        const form = $('form-pagar-lote');
        if (!form) return;
        form.addEventListener('submit', confirmarLote);
        $('pagar-lote-cancelar').addEventListener('click', fecharLote);
        $('pagar-lote-fechar').addEventListener('click', fecharLote);
    });
}());
