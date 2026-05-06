(function () {
    'use strict';

    const estado = {
        categoriasIr: [],
        categoriasDespesa: [],
        comprovantes: [],
        saidasSemDocumento: [],
        resumoSaidasSemDocumento: {},
        arquivosSelecionados: [],
        resumoImportacao: { enviados: 0, lidos: 0, pendentes: 0, erros: 0 },
        categoriaIrManual: false,
        contexto: { modo: 'IRPF' },
    };

    const $ = (id) => document.getElementById(id);
    const NATUREZAS_LASTRO = [
        ['DESPESA_OPERACIONAL', 'Despesa operacional'],
        ['PATRIMONIO_IMOBILIZADO', 'Patrimonio / Imobilizado'],
        ['SOFTWARE_ASSINATURA', 'Software / Assinatura'],
        ['IMPOSTO_TAXA', 'Imposto / taxa'],
        ['PRO_LABORE', 'Pro-labore'],
        ['DISTRIBUICAO_LUCROS', 'Distribuicao de lucros'],
        ['REEMBOLSO', 'Reembolso'],
        ['EMPRESTIMO', 'Emprestimo'],
        ['ADIANTAMENTO', 'Adiantamento'],
        ['OUTRO', 'Outro'],
    ];

    document.addEventListener('DOMContentLoaded', inicializarIr);

    async function inicializarIr() {
        definirAnoPadrao();
        vincularEventos();
        await carregarContexto();
        await Promise.all([carregarCategoriasIr(), carregarCategoriasDespesa()]);
        preencherSelectsNaturezaLastro();
        await carregarComprovantes();
        await carregarSaidasSemDocumento();
    }

    function definirAnoPadrao() {
        const ano = String(new Date().getFullYear());
        ['ir-filtro-ano', 'ir-upload-ano', 'ir-saidas-filtro-ano'].forEach((id) => {
            const campo = $(id);
            if (campo && Array.from(campo.options).some((opcao) => opcao.value === ano)) {
                campo.value = ano;
            }
        });
    }

    function vincularEventos() {
        $('ir-btn-atualizar')?.addEventListener('click', carregarComprovantes);
        $('ir-btn-importar')?.addEventListener('click', () => alternarView('import'));
        $('ir-btn-voltar')?.addEventListener('click', () => alternarView('main'));
        $('ir-btn-exportar')?.addEventListener('click', () => baixarRelatorio('excel'));
        $('ir-btn-excel')?.addEventListener('click', () => baixarRelatorio('excel'));
        $('ir-btn-pdf')?.addEventListener('click', () => baixarRelatorio('pdf'));
        $('ir-filtro-ano')?.addEventListener('change', carregarComprovantes);
        $('ir-filtro-status')?.addEventListener('change', carregarComprovantes);
        $('ir-filtro-categoria')?.addEventListener('change', carregarComprovantes);
        $('ir-filtro-busca')?.addEventListener('input', debounce(carregarComprovantes, 250));
        $('ir-saidas-btn-atualizar')?.addEventListener('click', carregarSaidasSemDocumento);
        $('ir-saidas-btn-excel')?.addEventListener('click', () => baixarRelatorioSaidasSemDocumento('excel'));
        $('ir-saidas-btn-pdf')?.addEventListener('click', () => baixarRelatorioSaidasSemDocumento('pdf'));
        $('ir-saidas-filtro-ano')?.addEventListener('change', carregarSaidasSemDocumento);
        $('ir-saidas-filtro-mes')?.addEventListener('change', carregarSaidasSemDocumento);
        $('ir-saidas-filtro-origem')?.addEventListener('change', carregarSaidasSemDocumento);
        $('ir-saidas-filtro-status')?.addEventListener('change', carregarSaidasSemDocumento);
        $('ir-saidas-filtro-natureza')?.addEventListener('change', carregarSaidasSemDocumento);
        $('ir-saidas-filtro-valor')?.addEventListener('input', debounce(carregarSaidasSemDocumento, 250));
        $('ir-saidas-filtro-busca')?.addEventListener('input', debounce(carregarSaidasSemDocumento, 250));
        $('ir-upload-submit')?.addEventListener('click', enviarArquivos);
        $('ir-select-files')?.addEventListener('click', () => $('ir-file-input')?.click());
        $('ir-file-input')?.addEventListener('change', (event) => selecionarArquivos(event.target.files));
        $('ir-review-close')?.addEventListener('click', fecharRevisao);
        $('ir-review-save')?.addEventListener('click', salvarRevisao);
        $('ir-review-validar')?.addEventListener('click', validarComprovante);
        $('ir-review-ocr-reprocess')?.addEventListener('click', reprocessarOcr);
        $('ir-review-categoria')?.addEventListener('change', resolverCategoriaIrDaDespesa);
        $('ir-review-categoria-ir')?.addEventListener('change', () => {
            estado.categoriaIrManual = true;
            atualizarAvisoVinculo('');
        });
        $('ir-link-close')?.addEventListener('click', fecharVinculo);
        $('ir-link-cancel')?.addEventListener('click', fecharVinculo);
        $('ir-link-save')?.addEventListener('click', salvarVinculo);
        $('ir-link-tipo-entidade')?.addEventListener('change', carregarEntidadesVinculaveis);
        $('ir-saida-link-close')?.addEventListener('click', fecharVinculoSaida);
        $('ir-saida-link-cancel')?.addEventListener('click', fecharVinculoSaida);
        $('ir-saida-link-save')?.addEventListener('click', salvarVinculoSaida);
        $('ir-saida-status-close')?.addEventListener('click', fecharStatusSaida);
        $('ir-saida-status-cancel')?.addEventListener('click', fecharStatusSaida);
        $('ir-saida-status-save')?.addEventListener('click', salvarStatusSaida);

        const dropzone = $('ir-dropzone');
        if (dropzone) {
            ['dragenter', 'dragover'].forEach((evento) => {
                dropzone.addEventListener(evento, (ev) => {
                    ev.preventDefault();
                    dropzone.classList.add('dragover');
                });
            });
            ['dragleave', 'drop'].forEach((evento) => {
                dropzone.addEventListener(evento, (ev) => {
                    ev.preventDefault();
                    dropzone.classList.remove('dragover');
                });
            });
            dropzone.addEventListener('drop', (ev) => selecionarArquivos(ev.dataTransfer.files));
        }
    }

    function alternarView(view) {
        $('ir-main-view')?.classList.toggle('active', view === 'main');
        $('ir-import-view')?.classList.toggle('active', view === 'import');
    }

    async function carregarContexto() {
        try {
            const resposta = await fetch('/api/ir/contexto');
            const json = await resposta.json();
            if (json.success && json.data) {
                estado.contexto = json.data;
                aplicarContextoVisual();
            }
        } catch (error) {
            estado.contexto = { modo: 'IRPF' };
        }
    }

    function modoEmpresa() {
        return estado.contexto?.modo === 'DOCUMENTOS_FISCAIS_EMPRESA';
    }

    function aplicarContextoVisual() {
        const empresa = modoEmpresa();
        const titulo = estado.contexto?.titulo || (empresa ? 'Documentos Fiscais e Lastro' : 'Imposto de Renda');
        const pageTitle = document.querySelector('.page-title, .topbar-title, [data-page-title]');
        if (pageTitle) pageTitle.textContent = titulo;
        document.title = titulo;
        if ($('ir-btn-importar')) $('ir-btn-importar').textContent = empresa ? 'Importar documentos' : 'Importar comprovantes';
        if ($('ir-lista-titulo')) $('ir-lista-titulo').textContent = empresa ? 'Documentos fiscais' : 'Comprovantes';
        if ($('ir-kpi-total-label')) $('ir-kpi-total-label').textContent = empresa ? 'Documentos fiscais' : 'Comprovantes';
        if ($('ir-kpi-total-sub')) $('ir-kpi-total-sub').textContent = empresa ? 'documentos cadastrados' : 'documentos cadastrados';
        if ($('ir-kpi-valor-label')) $('ir-kpi-valor-label').textContent = empresa ? 'Valor documentado' : 'Valor potencialmente dedutivel';
        if ($('ir-kpi-valor-sub')) $('ir-kpi-valor-sub').textContent = empresa ? 'com documento importado' : 'sujeito a revisao';
        if ($('ir-kpi-pendentes-label')) $('ir-kpi-pendentes-label').textContent = empresa ? 'Sem lastro' : 'Pendentes de revisao';
        if ($('ir-kpi-pendentes-sub')) $('ir-kpi-pendentes-sub').textContent = empresa ? 'sem vinculo financeiro' : 'aguardando validacao';
        if ($('ir-kpi-categorias-label')) $('ir-kpi-categorias-label').textContent = empresa ? 'Aguardando contador' : 'Categorias IR usadas';
        if ($('ir-kpi-categorias-sub')) $('ir-kpi-categorias-sub').textContent = empresa ? 'classificacao contabil' : 'classificacao potencial';
        if ($('ir-pendencias-titulo')) $('ir-pendencias-titulo').textContent = empresa ? 'Pendencias de lastro' : 'Pendencias';
        if ($('ir-filtro-categoria-label')) $('ir-filtro-categoria-label').textContent = empresa ? 'Categoria fiscal' : 'Categoria IR';
        if ($('ir-review-categoria-ir-label')) $('ir-review-categoria-ir-label').textContent = empresa ? 'Categoria fiscal' : 'Categoria IR';
        if ($('ir-lastro-panel')) $('ir-lastro-panel').hidden = !empresa;
        if ($('ir-saidas-sem-documento-panel')) $('ir-saidas-sem-documento-panel').hidden = !empresa;
    }

    async function carregarCategoriasIr() {
        const resposta = await fetch('/api/ir/categorias');
        const json = await resposta.json();
        estado.categoriasIr = json.data || [];
        preencherSelectCategoriasIr();
    }

    async function carregarCategoriasDespesa() {
        try {
            const resposta = await fetch('/api/ir/categorias-despesa-disponiveis');
            const json = await resposta.json();
            estado.categoriasDespesa = json.data || [];
        } catch (error) {
            estado.categoriasDespesa = [];
            mostrarAviso('Nao foi possivel carregar Categorias de Despesa para revisao.');
        }
        preencherSelectCategoriasDespesa();
    }

    function preencherSelectCategoriasIr() {
        const filtro = $('ir-filtro-categoria');
        const review = $('ir-review-categoria-ir');
        if (filtro) {
            const atual = filtro.value;
            filtro.innerHTML = '<option value="">Todas</option>' + estado.categoriasIr.map((cat) => (
                `<option value="${cat.id}">${escapeHtml(cat.nome)}</option>`
            )).join('');
            filtro.value = atual;
        }
        if (review) {
            const vazio = estado.categoriasIr.length ? 'Selecione...' : 'Nenhuma Categoria IR cadastrada';
            review.innerHTML = `<option value="">${vazio}</option>` + estado.categoriasIr.map((cat) => (
                `<option value="${cat.id}">${escapeHtml(cat.nome)}</option>`
            )).join('');
        }
    }

    function preencherSelectCategoriasDespesa() {
        const select = $('ir-review-categoria');
        if (!select) return;
        const vazio = estado.categoriasDespesa.length ? 'Selecione...' : 'Nenhuma categoria cadastrada';
        select.innerHTML = `<option value="">${vazio}</option>` + estado.categoriasDespesa.map((cat) => (
            `<option value="${cat.id}" data-categoria-ir-id="${cat.categoria_ir_id || ''}">${escapeHtml(cat.nome)}</option>`
        )).join('');
    }

    function resolverCategoriaIrDaDespesa() {
        const selectCategoria = $('ir-review-categoria');
        const selectIr = $('ir-review-categoria-ir');
        if (!selectCategoria || !selectIr || estado.categoriaIrManual) return;

        const categoriaId = Number(selectCategoria.value || 0);
        if (!categoriaId) {
            atualizarAvisoVinculo('');
            return;
        }

        const categoria = estado.categoriasDespesa.find((item) => Number(item.id) === categoriaId);
        if (categoria?.categoria_ir_id) {
            selectIr.value = String(categoria.categoria_ir_id);
            atualizarAvisoVinculo('');
            return;
        }

        selectIr.value = '';
        atualizarAvisoVinculo('Categoria de Despesa ainda sem vinculo com Categoria IR.');
    }

    function atualizarAvisoVinculo(mensagem) {
        const aviso = $('ir-review-categoria-aviso');
        if (!aviso) return;
        aviso.textContent = mensagem || '';
        aviso.hidden = !mensagem;
    }

    async function carregarComprovantes() {
        const params = montarFiltrosRelatorio();
        const resposta = await fetch(`/api/ir/comprovantes?${params.toString()}`);
        const json = await resposta.json();
        estado.comprovantes = json.data || [];
        renderComprovantes();
        renderResumo(json.resumo || {});
    }

    function montarFiltrosRelatorio() {
        const params = new URLSearchParams();
        params.set('ano', $('ir-filtro-ano')?.value || new Date().getFullYear());
        const status = $('ir-filtro-status')?.value || 'TODOS';
        if (status && status !== 'TODOS') params.set('status', status);
        const categoriaIr = $('ir-filtro-categoria')?.value;
        if (categoriaIr) params.set('categoria_ir_id', categoriaIr);
        const busca = $('ir-filtro-busca')?.value;
        if (busca) params.set('busca', busca);
        return params;
    }

    function baixarRelatorio(tipo) {
        const params = montarFiltrosRelatorio();
        const endpoint = tipo === 'pdf' ? 'pdf' : 'excel';
        const botao = tipo === 'pdf' ? $('ir-btn-pdf') : $('ir-btn-excel');
        const textoOriginal = botao?.innerHTML;
        if (botao) {
            botao.disabled = true;
            botao.innerHTML = 'Gerando...';
        }
        window.location.href = `/api/ir/relatorios/${endpoint}?${params.toString()}`;
        window.setTimeout(() => {
            if (botao) {
                botao.disabled = false;
                botao.innerHTML = textoOriginal;
            }
        }, 1200);
    }

    async function baixarRelatorioSaidasSemDocumento(tipo) {
        if (!modoEmpresa()) {
            mostrarAviso('Relatorio de lastro empresarial disponivel apenas no perfil Empresa.');
            return;
        }
        const params = montarFiltrosSaidas();
        const endpoint = tipo === 'pdf' ? 'relatorio-pdf' : 'relatorio-excel';
        const botao = tipo === 'pdf' ? $('ir-saidas-btn-pdf') : $('ir-saidas-btn-excel');
        const textoOriginal = botao?.textContent;
        if (botao) {
            botao.disabled = true;
            botao.textContent = 'Gerando...';
        }
        try {
            const resposta = await fetch(`/api/ir/lastro/saidas-sem-documento/${endpoint}?${params.toString()}`);
            if (!resposta.ok) {
                let mensagem = 'Nao foi possivel gerar o relatorio.';
                try {
                    const erro = await resposta.json();
                    mensagem = erro.error || mensagem;
                } catch (error) {
                    mensagem = resposta.statusText || mensagem;
                }
                throw new Error(mensagem);
            }
            const blob = await resposta.blob();
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = nomeArquivoResposta(resposta, tipo === 'pdf' ? 'Saidas_sem_documento.pdf' : 'Saidas_sem_documento.xlsx');
            document.body.appendChild(link);
            link.click();
            link.remove();
            URL.revokeObjectURL(url);
        } catch (error) {
            mostrarAviso(error.message || 'Nao foi possivel gerar o relatorio.');
        } finally {
            if (botao) {
                botao.disabled = false;
                botao.textContent = textoOriginal;
            }
        }
    }

    function nomeArquivoResposta(resposta, fallback) {
        const header = resposta.headers.get('Content-Disposition') || '';
        const match = header.match(/filename\*?=(?:UTF-8''|")?([^";]+)/i);
        if (!match) return fallback;
        try {
            return decodeURIComponent(match[1].replace(/"/g, ''));
        } catch (error) {
            return match[1].replace(/"/g, '') || fallback;
        }
    }

    function renderComprovantes() {
        const tbody = $('ir-comprovantes-tbody');
        if (!tbody) return;
        if (!estado.comprovantes.length) {
            tbody.innerHTML = '<tr><td colspan="10" class="ir-empty">Nenhum comprovante cadastrado para este ano.</td></tr>';
            $('ir-lista-subtitulo').textContent = modoEmpresa() ? '0 documentos encontrados' : '0 comprovantes encontrados';
            return;
        }

        $('ir-lista-subtitulo').textContent = modoEmpresa()
            ? `${estado.comprovantes.length} documento(s) encontrado(s)`
            : `${estado.comprovantes.length} comprovante(s) encontrado(s)`;
        tbody.innerHTML = estado.comprovantes.map((item) => `
            <tr>
                <td>${formatarData(item.data_documento)}</td>
                <td>${escapeHtml(item.prestador_nome || item.arquivo?.nome_arquivo || 'Sem prestador')}</td>
                <td>${escapeHtml(item.categoria_ir_nome || '-')}</td>
                <td>${escapeHtml(item.categoria_nome || '-')}</td>
                <td>${formatarMoeda(item.valor)}</td>
                <td>${item.ano_calendario || '-'}</td>
                <td>${formatarNatureza(item.natureza_fiscal)}</td>
                <td>${renderLastro(item.status_lastro)}</td>
                <td>${renderStatus(item.status)}</td>
                <td>
                    <span class="ir-row-actions">
                        <button type="button" class="ir-icon-btn" title="Revisar" onclick="window.IRDoc.abrirRevisao(${item.id})">Ver</button>
                        ${modoEmpresa() ? `<button type="button" class="ir-icon-btn" title="Vincular" onclick="window.IRDoc.abrirVinculo(${item.id})">Vincular</button>` : ''}
                        <a class="ir-icon-btn" title="Abrir arquivo" href="/api/ir/comprovantes/${item.id}/arquivo" target="_blank" rel="noopener">PDF</a>
                    </span>
                </td>
            </tr>
        `).join('');
    }

    function renderResumo(resumo) {
        const lastro = resumo.lastro || {};
        $('ir-kpi-total').textContent = String(resumo.total_comprovantes || 0);
        $('ir-kpi-valor').textContent = formatarMoeda(
            modoEmpresa() ? (lastro.valor_com_lastro || 0) : (resumo.valor_potencialmente_dedutivel || 0)
        );
        $('ir-kpi-pendentes').textContent = String(
            modoEmpresa() ? (lastro.documentos_sem_vinculo || 0) : (resumo.pendentes_revisao || 0)
        );
        $('ir-kpi-categorias').textContent = String(
            modoEmpresa() ? (lastro.documentos_aguardando_contador || 0) : (resumo.categorias_ir_usadas || 0)
        );
        $('ir-pendencias').innerHTML = modoEmpresa()
            ? `<span>${lastro.documentos_sem_vinculo || 0} documentos sem vinculo de lastro</span>`
            : `<span>${resumo.pendentes_revisao || 0} documentos pendentes de revisao</span>`;
        if ($('ir-lastro-resumo')) {
            $('ir-lastro-resumo').innerHTML = `
                <span>${lastro.documentos_vinculados || 0} documentos vinculados</span>
                <span>${lastro.documentos_sem_vinculo || 0} sem vinculo</span>
                <span>${formatarMoeda(lastro.valor_sem_lastro || 0)} sem lastro</span>
            `;
        }

        const totais = resumo.totais_por_categoria_ir || [];
        const destino = $('ir-totais-categorias');
        if (!destino) return;
        if (!totais.length) {
            destino.innerHTML = '<p class="ir-empty">Nenhuma categoria consolidada.</p>';
            return;
        }
        const maior = Math.max(...totais.map((item) => Number(item.valor) || 0), 1);
        destino.innerHTML = totais.map((item) => {
            const percentual = Math.min(100, Math.round(((Number(item.valor) || 0) / maior) * 100));
            return `
                <div class="ir-total-line">
                    <span>${escapeHtml(item.categoria_ir_nome)}</span>
                    <strong>${formatarMoeda(item.valor)}</strong>
                    <div class="ir-total-bar"><span style="width:${percentual}%"></span></div>
                </div>
            `;
        }).join('');
    }

    function preencherSelectsNaturezaLastro() {
        const options = NATUREZAS_LASTRO.map(([valor, label]) => (
            `<option value="${valor}">${escapeHtml(label)}</option>`
        )).join('');
        ['ir-saida-link-natureza', 'ir-saida-status-natureza'].forEach((id) => {
            const select = $(id);
            if (select) select.innerHTML = options;
        });
    }

    function montarFiltrosSaidas() {
        const params = new URLSearchParams();
        params.set('ano', $('ir-saidas-filtro-ano')?.value || $('ir-filtro-ano')?.value || new Date().getFullYear());
        const mes = $('ir-saidas-filtro-mes')?.value;
        if (mes) params.set('mes', mes);
        const origem = $('ir-saidas-filtro-origem')?.value;
        if (origem) params.set('origem', origem);
        const status = $('ir-saidas-filtro-status')?.value;
        if (status) params.set('status', status);
        const natureza = $('ir-saidas-filtro-natureza')?.value;
        if (natureza) params.set('natureza', natureza);
        const valorMinimo = $('ir-saidas-filtro-valor')?.value;
        if (valorMinimo) params.set('valor_minimo', valorMinimo);
        const busca = $('ir-saidas-filtro-busca')?.value;
        if (busca) params.set('busca', busca);
        return params;
    }

    async function carregarSaidasSemDocumento() {
        if (!modoEmpresa()) {
            estado.saidasSemDocumento = [];
            estado.resumoSaidasSemDocumento = {};
            renderSaidasSemDocumento();
            renderResumoSaidasSemDocumento({});
            return;
        }
        const params = montarFiltrosSaidas();
        try {
            const [listaResp, resumoResp] = await Promise.all([
                fetch(`/api/ir/lastro/saidas-sem-documento?${params.toString()}`),
                fetch(`/api/ir/lastro/saidas-sem-documento/resumo?${params.toString()}`),
            ]);
            const listaJson = await listaResp.json();
            const resumoJson = await resumoResp.json();
            if (!listaJson.success) throw new Error(listaJson.error || 'Erro ao carregar saidas sem documento.');
            if (!resumoJson.success) throw new Error(resumoJson.error || 'Erro ao carregar resumo de lastro.');
            estado.saidasSemDocumento = listaJson.data || [];
            estado.resumoSaidasSemDocumento = resumoJson.data || {};
            renderResumoSaidasSemDocumento(estado.resumoSaidasSemDocumento);
            renderSaidasSemDocumento();
        } catch (error) {
            estado.saidasSemDocumento = [];
            renderSaidasSemDocumento();
            mostrarAviso(error.message || 'Nao foi possivel carregar saidas sem documento.');
        }
    }

    function renderResumoSaidasSemDocumento(resumo) {
        if ($('ir-saidas-kpi-quantidade')) $('ir-saidas-kpi-quantidade').textContent = String(resumo.quantidade_sem_documento || 0);
        if ($('ir-saidas-kpi-valor')) $('ir-saidas-kpi-valor').textContent = formatarMoeda(resumo.valor_sem_documento || 0);
        if ($('ir-saidas-kpi-contador')) $('ir-saidas-kpi-contador').textContent = String(resumo.aguardando_contador || 0);
        if ($('ir-saidas-kpi-na')) $('ir-saidas-kpi-na').textContent = String(resumo.nao_aplicavel || 0);
    }

    function renderSaidasSemDocumento() {
        const tbody = $('ir-saidas-tbody');
        const subtitulo = $('ir-saidas-subtitulo');
        if (!tbody) return;
        if (!modoEmpresa()) {
            tbody.innerHTML = '<tr><td colspan="8" class="ir-empty">Disponivel apenas no perfil Empresa.</td></tr>';
            if (subtitulo) subtitulo.textContent = 'Disponivel apenas no perfil Empresa';
            return;
        }
        if (!estado.saidasSemDocumento.length) {
            tbody.innerHTML = '<tr><td colspan="8" class="ir-empty">Nenhuma saida sem documento no periodo.</td></tr>';
            if (subtitulo) subtitulo.textContent = '0 saidas sem documento encontradas';
            return;
        }
        if (subtitulo) subtitulo.textContent = `${estado.saidasSemDocumento.length} saida(s) sem documento encontrada(s)`;
        tbody.innerHTML = estado.saidasSemDocumento.map((saida) => `
            <tr>
                <td>${formatarData(saida.data)}</td>
                <td>${escapeHtml(saida.origem || '-')}</td>
                <td>
                    <span class="ir-saida-descricao">
                        <strong>${escapeHtml(saida.descricao || 'Saida financeira')}</strong>
                        <small>${escapeHtml(saida.tipo_entidade)} #${escapeHtml(saida.entidade_id)}</small>
                    </span>
                </td>
                <td>${escapeHtml(saida.categoria || '-')}</td>
                <td>${formatarMoeda(saida.valor)}</td>
                <td>${formatarNatureza(saida.natureza_sugerida)}</td>
                <td>${renderLastro(saida.status_lastro)}</td>
                <td>
                    <span class="ir-saida-actions">
                        <button type="button" class="ir-icon-btn" title="Vincular documento" onclick="window.IRDoc.abrirVinculoSaida('${saida.tipo_entidade}', ${saida.entidade_id})">Vincular</button>
                        <button type="button" class="ir-icon-btn" title="Aguardando contador" onclick="window.IRDoc.abrirStatusSaida('${saida.tipo_entidade}', ${saida.entidade_id}, 'AGUARDANDO_CONTADOR')">Contador</button>
                        <button type="button" class="ir-icon-btn" title="Nao aplicavel" onclick="window.IRDoc.abrirStatusSaida('${saida.tipo_entidade}', ${saida.entidade_id}, 'NAO_APLICAVEL')">N/A</button>
                        <button type="button" class="ir-icon-btn" title="Ver origem" onclick="window.IRDoc.verOrigemSaida('${saida.tipo_entidade}', ${saida.entidade_id})">Origem</button>
                    </span>
                </td>
            </tr>
        `).join('');
    }

    function buscarSaida(tipoEntidade, entidadeId) {
        return estado.saidasSemDocumento.find((saida) => (
            saida.tipo_entidade === tipoEntidade && Number(saida.entidade_id) === Number(entidadeId)
        ));
    }

    function renderResumoSaidaModal(saida) {
        if (!saida) return '';
        return `
            <span><small>Saida</small><strong>${escapeHtml(saida.descricao || '-')}</strong></span>
            <span><small>Valor</small><strong>${formatarMoeda(saida.valor)}</strong></span>
            <span><small>Data</small><strong>${formatarData(saida.data)}</strong></span>
            <span><small>Origem</small><strong>${escapeHtml(saida.origem || '-')}</strong></span>
            <span><small>Categoria</small><strong>${escapeHtml(saida.categoria || '-')}</strong></span>
            <span><small>Status</small><strong>${escapeHtml(saida.status_lastro || 'SEM_DOCUMENTO')}</strong></span>
        `;
    }

    async function abrirVinculoSaida(tipoEntidade, entidadeId) {
        const saida = buscarSaida(tipoEntidade, entidadeId);
        if (!saida) return;
        $('ir-saida-link-tipo-entidade').value = tipoEntidade;
        $('ir-saida-link-entidade-id').value = entidadeId;
        $('ir-saida-link-resumo').innerHTML = renderResumoSaidaModal(saida);
        $('ir-saida-link-natureza').value = saida.natureza_sugerida || 'DESPESA_OPERACIONAL';
        $('ir-saida-link-status').value = 'VALIDADO';
        $('ir-saida-link-tipo-vinculo').value = 'NOTA_FISCAL';
        $('ir-saida-link-observacoes').value = saida.observacoes || '';
        await carregarComprovantesParaVinculoSaida();
        $('ir-saida-link-modal').classList.add('open');
        $('ir-saida-link-modal').setAttribute('aria-hidden', 'false');
    }

    function fecharVinculoSaida() {
        $('ir-saida-link-modal')?.classList.remove('open');
        $('ir-saida-link-modal')?.setAttribute('aria-hidden', 'true');
    }

    async function carregarComprovantesParaVinculoSaida() {
        const select = $('ir-saida-link-comprovante');
        if (!select) return;
        const ano = $('ir-saidas-filtro-ano')?.value || $('ir-filtro-ano')?.value || new Date().getFullYear();
        const resposta = await fetch(`/api/ir/comprovantes?ano=${encodeURIComponent(ano)}`);
        const json = await resposta.json();
        const documentos = json.data || [];
        const vazio = documentos.length ? 'Selecione...' : 'Nenhum documento fiscal encontrado no ano';
        select.innerHTML = `<option value="">${vazio}</option>` + documentos.map((item) => {
            const label = [
                item.prestador_nome || item.arquivo?.nome_arquivo || `Documento #${item.id}`,
                item.valor != null ? formatarMoeda(item.valor) : null,
                formatarData(item.data_documento),
            ].filter(Boolean).join(' - ');
            return `<option value="${item.id}">${escapeHtml(label)}</option>`;
        }).join('');
    }

    async function salvarVinculoSaida() {
        const comprovanteId = $('ir-saida-link-comprovante')?.value;
        if (!comprovanteId) {
            mostrarAviso('Selecione um documento fiscal existente.');
            return;
        }
        const payload = {
            tipo_entidade: $('ir-saida-link-tipo-entidade').value,
            entidade_id: $('ir-saida-link-entidade-id').value,
            comprovante_id: comprovanteId,
            tipo_vinculo: $('ir-saida-link-tipo-vinculo').value,
            natureza: $('ir-saida-link-natureza').value,
            status_lastro: $('ir-saida-link-status').value,
            observacoes: $('ir-saida-link-observacoes').value,
        };
        const resposta = await fetch('/api/ir/lastro/saidas-sem-documento/vincular', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const json = await resposta.json();
        if (!json.success) {
            mostrarAviso(json.error || 'Nao foi possivel vincular o documento fiscal.');
            return;
        }
        fecharVinculoSaida();
        await Promise.all([carregarComprovantes(), carregarSaidasSemDocumento()]);
    }

    function abrirStatusSaida(tipoEntidade, entidadeId, status) {
        const saida = buscarSaida(tipoEntidade, entidadeId);
        if (!saida) return;
        $('ir-saida-status-tipo-entidade').value = tipoEntidade;
        $('ir-saida-status-entidade-id').value = entidadeId;
        $('ir-saida-status-resumo').innerHTML = renderResumoSaidaModal(saida);
        $('ir-saida-status-valor').value = status || saida.status_lastro || 'AGUARDANDO_CONTADOR';
        $('ir-saida-status-natureza').value = saida.natureza_sugerida || 'DESPESA_OPERACIONAL';
        $('ir-saida-status-observacoes').value = saida.observacoes || '';
        $('ir-saida-status-modal').classList.add('open');
        $('ir-saida-status-modal').setAttribute('aria-hidden', 'false');
    }

    function fecharStatusSaida() {
        $('ir-saida-status-modal')?.classList.remove('open');
        $('ir-saida-status-modal')?.setAttribute('aria-hidden', 'true');
    }

    async function salvarStatusSaida() {
        const payload = {
            tipo_entidade: $('ir-saida-status-tipo-entidade').value,
            entidade_id: $('ir-saida-status-entidade-id').value,
            status_lastro: $('ir-saida-status-valor').value,
            natureza: $('ir-saida-status-natureza').value,
            observacoes: $('ir-saida-status-observacoes').value,
        };
        const resposta = await fetch('/api/ir/lastro/saidas-sem-documento/status', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const json = await resposta.json();
        if (!json.success) {
            mostrarAviso(json.error || 'Nao foi possivel salvar o status de lastro.');
            return;
        }
        fecharStatusSaida();
        await carregarSaidasSemDocumento();
    }

    function verOrigemSaida(tipoEntidade, entidadeId) {
        const saida = buscarSaida(tipoEntidade, entidadeId);
        if (!saida) return;
        mostrarAviso(`${saida.origem || 'Origem'} #${saida.entidade_id}\n${saida.descricao || ''}\n${formatarMoeda(saida.valor)} em ${formatarData(saida.data)}`);
    }

    function selecionarArquivos(fileList) {
        estado.arquivosSelecionados = Array.from(fileList || []);
        $('ir-upload-count').textContent = `${estado.arquivosSelecionados.length} arquivo(s) selecionado(s)`;
        renderArquivosSelecionados();
    }

    function renderArquivosSelecionados() {
        const destino = $('ir-upload-results');
        if (!destino) return;
        if (!estado.arquivosSelecionados.length) {
            destino.innerHTML = '<p class="ir-empty">Selecione arquivos para iniciar a importacao.</p>';
            return;
        }
        destino.innerHTML = estado.arquivosSelecionados.map((arquivo) => `
            <div class="ir-upload-item">
                <strong>${escapeHtml(arquivo.name)}</strong>
                <span>${escapeHtml(arquivo.type || 'tipo desconhecido')}</span>
                <span>${formatarTamanho(arquivo.size)}</span>
            </div>
        `).join('');
    }

    async function enviarArquivos() {
        if (!estado.arquivosSelecionados.length) {
            mostrarAviso('Selecione ao menos um comprovante.');
            return;
        }

        const form = new FormData();
        form.append('ano_calendario', $('ir-upload-ano')?.value || new Date().getFullYear());
        estado.arquivosSelecionados.forEach((arquivo) => form.append('arquivos', arquivo, arquivo.name));

        const resposta = await fetch('/api/ir/comprovantes/upload', { method: 'POST', body: form });
        const json = await resposta.json();
        renderResultadoUpload(json.data || []);
        await carregarComprovantes();
    }

    function renderResultadoUpload(resultados) {
        const destino = $('ir-upload-results');
        const resumo = { enviados: resultados.length, lidos: 0, pendentes: 0, erros: 0 };
        const anoUpload = $('ir-upload-ano')?.value || '';
        destino.innerHTML = resultados.map((resultado) => {
            if (!resultado.success) {
                resumo.erros += 1;
                return `
                    <div class="ir-upload-item ir-upload-card">
                        <div>
                            <strong>${escapeHtml(resultado.arquivo || 'Arquivo')}</strong>
                            <small>${escapeHtml(resultado.error)}</small>
                        </div>
                        <div>${renderStatus('ERRO_LEITURA')}</div>
                    </div>
                `;
            }
            const comprovante = resultado.data?.comprovante || {};
            const status = comprovante.status || (resultado.data?.duplicado ? 'IMPORTADO' : 'PENDENTE_REVISAO');
            if (status === 'CLASSIFICADO' || status === 'VALIDADO') resumo.lidos += 1;
            if (status === 'PENDENTE_REVISAO' || status === 'IMPORTADO') resumo.pendentes += 1;
            if (status === 'ERRO_LEITURA') resumo.erros += 1;
            return renderUploadComprovante(comprovante, resultado.data || {}, status, anoUpload);
        }).join('');
        estado.resumoImportacao = resumo;
        $('ir-import-enviados').textContent = resumo.enviados;
        $('ir-import-lidos').textContent = resumo.lidos;
        $('ir-import-pendentes').textContent = resumo.pendentes;
        $('ir-import-erros').textContent = resumo.erros;
    }

    function renderUploadComprovante(comprovante, resultado, status, anoUpload) {
        const arquivo = comprovante.arquivo || {};
        const extraido = Boolean(comprovante.texto_extraido);
        const resumoOcr = obterResumoOcr(comprovante);
        const anoDocumento = comprovante.ano_calendario ? String(comprovante.ano_calendario) : '';
        const anoDiferente = anoDocumento && anoUpload && anoDocumento !== anoUpload;
        const resumo = [
            ['Data', formatarData(comprovante.data_documento)],
            ['Ano', comprovante.ano_calendario || '-'],
            ['Prestador', comprovante.prestador_nome || '-'],
            ['CPF/CNPJ', comprovante.prestador_cpf_cnpj || '-'],
            ['Valor', comprovante.valor != null ? formatarMoeda(comprovante.valor) : '-'],
            ['Categoria despesa', comprovante.categoria_nome || '-'],
            ['Categoria IR', comprovante.categoria_ir_nome || '-'],
        ];
        const notaAno = anoDiferente
            ? `<div class="ir-upload-warning">O documento foi identificado como ano-calendario ${escapeHtml(anoDocumento)}. Ele nao aparece no filtro ${escapeHtml(anoUpload)}.</div>`
            : '';
        const trecho = comprovante.texto_extraido
            ? `<details class="ir-upload-text"><summary>Ver texto extraido</summary><pre>${escapeHtml(comprovante.texto_extraido.slice(0, 1400))}</pre></details>`
            : '<p class="ir-upload-muted">Nenhum texto extraido disponivel. Revise manualmente ou reprocesse OCR depois de configurar as ferramentas locais.</p>';
        const avisoOcr = resumoOcr.mensagem
            ? `<div class="ir-ocr-alert">${escapeHtml(resumoOcr.mensagem)}</div>`
            : '';

        return `
            <div class="ir-upload-item ir-upload-card">
                <div class="ir-upload-card-head">
                    <div>
                        <strong>${escapeHtml(arquivo.nome_arquivo || 'Comprovante')}</strong>
                        <small>${escapeHtml(resultado.mensagem || '')}${resultado.duplicado ? ' O registro existente foi carregado para revisao.' : ''}</small>
                    </div>
                    <div class="ir-upload-badges">
                        ${extraido ? '<span class="ir-mini-badge ok">Texto extraido</span>' : '<span class="ir-mini-badge">Sem texto</span>'}
                        ${resumoOcr.usouOcr ? '<span class="ir-mini-badge ok">OCR local</span>' : ''}
                        ${renderStatus(status)}
                    </div>
                </div>
                ${notaAno}
                <div class="ir-upload-extracted">
                    ${resumo.map(([label, value]) => `<span><small>${label}</small><strong>${escapeHtml(value)}</strong></span>`).join('')}
                </div>
                ${avisoOcr}
                ${trecho}
                <div class="ir-upload-actions">
                    <button type="button" class="ir-secondary-btn" onclick="window.IRDoc.abrirRevisao(${comprovante.id})">Revisar dados</button>
                    <a class="ir-secondary-btn ir-link-button" href="/api/ir/comprovantes/${comprovante.id}/arquivo" target="_blank" rel="noopener">Abrir arquivo</a>
                    ${anoDiferente ? `<button type="button" class="ir-secondary-btn" onclick="window.IRDoc.verAno(${comprovante.ano_calendario})">Ver no ano ${escapeHtml(anoDocumento)}</button>` : ''}
                </div>
            </div>
        `;
    }

    async function abrirRevisao(id) {
        const resposta = await fetch(`/api/ir/comprovantes/${id}`);
        const json = await resposta.json();
        if (!json.success) {
            mostrarAviso(json.error || 'Nao foi possivel abrir o comprovante.');
            return;
        }
        const item = json.data;
        estado.categoriaIrManual = false;
        atualizarAvisoVinculo('');
        $('ir-review-id').value = item.id;
        $('ir-review-file-name').textContent = item.arquivo?.nome_arquivo || 'Comprovante';
        $('ir-review-file-link').href = `/api/ir/comprovantes/${item.id}/arquivo`;
        $('ir-review-texto').textContent = item.texto_extraido || 'Texto extraido indisponivel. Documento pendente de revisao manual ou OCR local.';
        renderAvisoOcrRevisao(item);
        $('ir-review-data').value = item.data_documento || '';
        $('ir-review-prestador').value = item.prestador_nome || '';
        $('ir-review-doc').value = item.prestador_cpf_cnpj || '';
        $('ir-review-valor').value = item.valor != null ? item.valor : '';
        $('ir-review-ano').value = item.ano_calendario || '';
        $('ir-review-categoria').value = item.categoria_id || '';
        $('ir-review-categoria-ir').value = item.categoria_ir_id || '';
        if (!item.categoria_ir_id) {
            resolverCategoriaIrDaDespesa();
        }
        $('ir-review-observacoes').value = item.observacoes || '';
        $('ir-review-modal').classList.add('open');
        $('ir-review-modal').setAttribute('aria-hidden', 'false');
    }

    function renderAvisoOcrRevisao(item) {
        const alerta = $('ir-review-ocr-alert');
        if (!alerta) return;
        const resumo = obterResumoOcr(item);
        alerta.textContent = resumo.mensagem || '';
        alerta.hidden = !resumo.mensagem;
    }

    function fecharRevisao() {
        $('ir-review-modal').classList.remove('open');
        $('ir-review-modal').setAttribute('aria-hidden', 'true');
    }

    async function abrirVinculo(id) {
        if (!modoEmpresa()) return;
        $('ir-link-comprovante-id').value = id;
        $('ir-link-observacoes').value = '';
        $('ir-link-status').value = 'PENDENTE';
        $('ir-link-natureza').value = 'DESPESA_OPERACIONAL';
        $('ir-link-tipo-entidade').value = 'DESPESA_PREVISTA';
        await carregarEntidadesVinculaveis();
        $('ir-link-modal').classList.add('open');
        $('ir-link-modal').setAttribute('aria-hidden', 'false');
    }

    function fecharVinculo() {
        $('ir-link-modal')?.classList.remove('open');
        $('ir-link-modal')?.setAttribute('aria-hidden', 'true');
    }

    async function carregarEntidadesVinculaveis() {
        const tipo = $('ir-link-tipo-entidade')?.value || 'OUTRO';
        const select = $('ir-link-entidade');
        if (!select) return;
        if (tipo === 'OUTRO') {
            select.innerHTML = '<option value="">Sem entidade especifica</option>';
            select.disabled = true;
            return;
        }
        select.disabled = false;
        const resposta = await fetch(`/api/ir/entidades-vinculaveis?tipo=${encodeURIComponent(tipo)}`);
        const json = await resposta.json();
        const entidades = json.data || [];
        const vazio = entidades.length ? 'Selecione...' : 'Nenhuma entidade encontrada no perfil ativo';
        select.innerHTML = `<option value="">${vazio}</option>` + entidades.map((item) => (
            `<option value="${item.id}">${escapeHtml(item.label)}${item.valor != null ? ` - ${formatarMoeda(item.valor)}` : ''}</option>`
        )).join('');
    }

    async function salvarVinculo() {
        const id = $('ir-link-comprovante-id').value;
        const payload = {
            tipo_entidade: $('ir-link-tipo-entidade').value,
            entidade_id: $('ir-link-entidade').value || null,
            natureza: $('ir-link-natureza').value,
            status_lastro: $('ir-link-status').value,
            tipo_vinculo: 'COMPROVANTE',
            observacoes: $('ir-link-observacoes').value,
        };
        const resposta = await fetch(`/api/ir/comprovantes/${id}/vinculos`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const json = await resposta.json();
        if (!json.success) {
            mostrarAviso(json.error || 'Nao foi possivel vincular o documento.');
            return;
        }
        fecharVinculo();
        await carregarComprovantes();
        await carregarSaidasSemDocumento();
    }

    async function salvarRevisao() {
        const id = $('ir-review-id').value;
        const payload = {
            data_documento: $('ir-review-data').value,
            prestador_nome: $('ir-review-prestador').value,
            prestador_cpf_cnpj: $('ir-review-doc').value,
            valor: $('ir-review-valor').value,
            ano_calendario: $('ir-review-ano').value,
            categoria_id: $('ir-review-categoria').value || null,
            categoria_ir_id: $('ir-review-categoria-ir').value || null,
            observacoes: $('ir-review-observacoes').value,
        };
        const resposta = await fetch(`/api/ir/comprovantes/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const json = await resposta.json();
        if (!json.success) {
            mostrarAviso(json.error || 'Nao foi possivel salvar a revisao.');
            return;
        }
        fecharRevisao();
        await carregarComprovantes();
    }

    async function validarComprovante() {
        const id = $('ir-review-id').value;
        await salvarRevisao();
        const resposta = await fetch(`/api/ir/comprovantes/${id}/validar`, { method: 'POST' });
        const json = await resposta.json();
        if (!json.success) {
            mostrarAviso(json.error || 'Nao foi possivel validar o comprovante.');
            return;
        }
        fecharRevisao();
        await carregarComprovantes();
    }

    async function reprocessarOcr() {
        const id = $('ir-review-id').value;
        if (!id) return;
        const botao = $('ir-review-ocr-reprocess');
        const textoOriginal = botao?.textContent;
        if (botao) {
            botao.disabled = true;
            botao.textContent = 'Processando...';
        }
        try {
            const resposta = await fetch(`/api/ir/comprovantes/${id}/reprocessar-ocr`, { method: 'POST' });
            const json = await resposta.json();
            if (!json.success) {
                mostrarAviso(json.error || 'Nao foi possivel reprocessar OCR.');
                return;
            }
            const item = json.data;
            $('ir-review-texto').textContent = item.texto_extraido || 'Texto extraido indisponivel. Documento pendente de revisao manual ou OCR local.';
            $('ir-review-data').value = item.data_documento || '';
            $('ir-review-prestador').value = item.prestador_nome || '';
            $('ir-review-doc').value = item.prestador_cpf_cnpj || '';
            $('ir-review-valor').value = item.valor != null ? item.valor : '';
            $('ir-review-ano').value = item.ano_calendario || '';
            $('ir-review-categoria').value = item.categoria_id || '';
            $('ir-review-categoria-ir').value = item.categoria_ir_id || '';
            $('ir-review-observacoes').value = item.observacoes || '';
            renderAvisoOcrRevisao(item);
            await carregarComprovantes();
        } finally {
            if (botao) {
                botao.disabled = false;
                botao.textContent = textoOriginal || 'Reprocessar OCR';
            }
        }
    }

    function renderStatus(status) {
        const chave = String(status || 'IMPORTADO').toUpperCase();
        const mapa = {
            VALIDADO: ['validado', 'Validado'],
            CLASSIFICADO: ['classificado', 'Classificado'],
            PENDENTE_REVISAO: ['pendente', 'Pendente'],
            ERRO_LEITURA: ['erro', 'Erro de leitura'],
            IMPORTADO: ['importado', 'Importado'],
            LIDO: ['classificado', 'Lido'],
            NAO_DEDUTIVEL: ['pendente', 'Nao dedutivel'],
            IGNORADO: ['importado', 'Ignorado'],
        };
        const [classe, label] = mapa[chave] || mapa.IMPORTADO;
        return `<span class="ir-status ${classe}">${label}</span>`;
    }

    function renderLastro(status) {
        const chave = String(status || 'SEM_DOCUMENTO').toUpperCase();
        const mapa = {
            COM_DOCUMENTO: ['classificado', 'Com documento'],
            VALIDADO: ['validado', 'Validado'],
            SEM_DOCUMENTO: ['pendente', 'Sem vinculo'],
            PENDENTE: ['pendente', 'Pendente'],
            DIVERGENTE: ['erro', 'Divergente'],
            NAO_APLICAVEL: ['importado', 'Nao aplicavel'],
            AGUARDANDO_CONTADOR: ['pendente', 'Aguardando contador'],
        };
        const [classe, label] = mapa[chave] || mapa.SEM_DOCUMENTO;
        return `<span class="ir-status ${classe}">${label}</span>`;
    }

    function obterResumoOcr(item) {
        const eventos = item?.eventos || [];
        const usouOcr = eventos.some((evento) => ['OCR_EXECUTADO', 'TEXTO_EXTRAIDO_OCR', 'OCR_LIMITADO'].includes(String(evento.tipo_evento || '').toUpperCase()));
        const falhou = eventos.some((evento) => String(evento.tipo_evento || '').toUpperCase() === 'OCR_FALHOU');
        const limitado = eventos.some((evento) => String(evento.tipo_evento || '').toUpperCase() === 'OCR_LIMITADO')
            || /3 primeiras paginas/i.test(item?.observacoes || '');
        if (usouOcr) {
            const partes = ['Texto extraido por OCR local. Revise os dados antes de validar.'];
            if (limitado) partes.push('OCR limitado as 3 primeiras paginas do documento.');
            return { usouOcr: true, mensagem: partes.join(' ') };
        }
        if (falhou) {
            return { usouOcr: false, mensagem: 'OCR local nao retornou texto suficiente. Revise manualmente ou verifique as ferramentas em Configuracoes > IA e Automacao.' };
        }
        return { usouOcr: false, mensagem: '' };
    }

    function formatarNatureza(valor) {
        const mapa = {
            DESPESA_OPERACIONAL: 'Despesa operacional',
            PATRIMONIO_IMOBILIZADO: 'Patrimonio',
            SOFTWARE_ASSINATURA: 'Software',
            IMPOSTO_TAXA: 'Imposto/taxa',
            PRO_LABORE: 'Pro-labore',
            DISTRIBUICAO_LUCROS: 'Distribuicao',
            REEMBOLSO: 'Reembolso',
            EMPRESTIMO: 'Emprestimo',
            ADIANTAMENTO: 'Adiantamento',
            OUTRO: 'Outro',
        };
        return escapeHtml(mapa[String(valor || '').toUpperCase()] || '-');
    }

    function formatarMoeda(valor) {
        return Number(valor || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
    }

    function formatarData(valor) {
        if (!valor) return '-';
        const [ano, mes, dia] = String(valor).split('-');
        return `${dia}/${mes}/${ano}`;
    }

    function formatarTamanho(bytes) {
        if (!bytes) return '0 KB';
        if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    }

    function escapeHtml(valor) {
        return String(valor ?? '').replace(/[&<>"']/g, (char) => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#039;',
        }[char]));
    }

    function mostrarAviso(mensagem) {
        window.alert(mensagem);
    }

    function debounce(fn, wait) {
        let timer;
        return function (...args) {
            clearTimeout(timer);
            timer = setTimeout(() => fn.apply(this, args), wait);
        };
    }

    window.IRDoc = {
        abrirRevisao,
        abrirVinculo,
        abrirVinculoSaida,
        abrirStatusSaida,
        verOrigemSaida,
        carregarComprovantes,
        carregarSaidasSemDocumento,
        reprocessarOcr,
        verAno(ano) {
            if ($('ir-filtro-ano')) {
                const valor = String(ano);
                const select = $('ir-filtro-ano');
                if (!Array.from(select.options).some((opcao) => opcao.value === valor)) {
                    select.add(new Option(valor, valor));
                }
                select.value = valor;
            }
            alternarView('main');
            carregarComprovantes();
        },
    };
}());
