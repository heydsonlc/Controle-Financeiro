(function () {
    'use strict';

    const estado = {
        categoriasIr: [],
        categoriasDespesa: [],
        comprovantes: [],
        saidasSemDocumento: [],
        paginaDocumentosEmpresa: 1,
        paginaSaidas: 1,
        resumoSaidasSemDocumento: {},
        arquivosSelecionados: [],
        resumoImportacao: { enviados: 0, lidos: 0, pendentes: 0, erros: 0 },
        categoriaIrManual: false,
        contexto: { modo: 'IRPF' },
        taxonomiaDocumental: { tipos_documentais: [], categorias_documentais: [], status_documentais: [] },
        resumoDocumentosEmpresa: {},
        tipoDocumentalAtivo: '',
        sugestaoFinanceira: null,
        sugestaoPatrimonio: null,
        cartoes: [],
        contasBancarias: [],
    };
    const ITENS_POR_PAGINA_TABELA = 5;
    const ICONES_ACAO_IMG = {
        filter: '/static/img/icone_filtro.png',
        'file-spreadsheet': '/static/img/documento_xlsx.png',
        'file-text': '/static/img/documento_pdf.png',
        'report-pdf': '/static/img/documento_relatorio.png',
        archive: '/static/img/documento_zip.webp',
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
        aplicarIconesAcoesEstaticas();
        vincularEventos();
        await carregarContexto();
        await carregarTaxonomiaDocumental();
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
        $('ir-doc-btn-zip')?.addEventListener('click', baixarPacoteDocumentosEmpresa);
        $('ir-filtros-avancados-toggle')?.addEventListener('click', alternarFiltrosAvancados);
        $('ir-filtro-ano')?.addEventListener('change', carregarComprovantes);
        $('ir-filtro-status')?.addEventListener('change', carregarComprovantes);
        $('ir-filtro-categoria')?.addEventListener('change', carregarComprovantes);
        $('ir-filtro-categoria-fiscal-avancada')?.addEventListener('change', carregarComprovantes);
        $('ir-filtro-validade')?.addEventListener('change', carregarComprovantes);
        $('ir-filtro-obrigatorio')?.addEventListener('change', carregarComprovantes);
        $('ir-filtro-tipo-documental')?.addEventListener('change', () => {
            estado.tipoDocumentalAtivo = $('ir-filtro-tipo-documental')?.value || '';
            atualizarAbaDocumentalAtiva();
            carregarComprovantes();
        });
        $('ir-filtro-categoria-documental')?.addEventListener('change', carregarComprovantes);
        $('ir-filtro-busca')?.addEventListener('input', debounce(carregarComprovantes, 250));
        document.querySelectorAll('#ir-doc-tabs button[data-tipo]').forEach((botao) => {
            botao.addEventListener('click', () => {
                estado.tipoDocumentalAtivo = botao.dataset.tipo || '';
                if ($('ir-filtro-tipo-documental')) $('ir-filtro-tipo-documental').value = estado.tipoDocumentalAtivo;
                atualizarAbaDocumentalAtiva();
                carregarComprovantes();
            });
        });
        $('ir-saidas-filtros-toggle')?.addEventListener('click', alternarFiltrosSaidas);
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
        $('ir-review-financeiro')?.addEventListener('click', abrirSugestaoFinanceira);
        $('ir-review-patrimonio')?.addEventListener('click', abrirSugestaoPatrimonio);
        $('ir-review-categoria')?.addEventListener('change', resolverCategoriaIrDaDespesa);
        $('ir-review-categoria-ir')?.addEventListener('change', () => {
            estado.categoriaIrManual = true;
            atualizarAvisoVinculo('');
        });
        $('ir-review-categoria-documental')?.addEventListener('change', sincronizarTipoPorCategoriaDocumental);
        $('ir-sugestao-close')?.addEventListener('click', fecharSugestaoFinanceira);
        $('ir-sugestao-cancel')?.addEventListener('click', fecharSugestaoFinanceira);
        $('ir-sugestao-tipo-destino')?.addEventListener('change', atualizarCamposSugestaoFinanceira);
        $('ir-sugestao-forma-pagamento')?.addEventListener('change', atualizarCamposSugestaoFinanceira);
        $('ir-sugestao-categoria')?.addEventListener('change', () => {
            atualizarCategoriaIrSugestao();
            resolverCategoriaCartaoSugestao();
        });
        $('ir-sugestao-cartao')?.addEventListener('change', resolverCategoriaCartaoSugestao);
        $('ir-sugestao-confirmar')?.addEventListener('click', confirmarSugestaoFinanceira);
        $('ir-sugestao-patrimonio-close')?.addEventListener('click', fecharSugestaoPatrimonio);
        $('ir-sugestao-patrimonio-cancel')?.addEventListener('click', fecharSugestaoPatrimonio);
        $('ir-sugestao-patrimonio-confirmar')?.addEventListener('click', confirmarSugestaoPatrimonio);
        $('ir-patrimonio-valor')?.addEventListener('input', atualizarDepreciacaoPatrimonio);
        $('ir-patrimonio-vida-util')?.addEventListener('input', atualizarDepreciacaoPatrimonio);
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
                estado.taxonomiaDocumental = json.data.taxonomia_documental || estado.taxonomiaDocumental;
                aplicarContextoVisual();
            }
        } catch (error) {
            estado.contexto = { modo: 'IRPF' };
        }
    }

    async function carregarTaxonomiaDocumental() {
        if (!modoEmpresa()) {
            estado.taxonomiaDocumental = { tipos_documentais: [], categorias_documentais: [], status_documentais: [] };
            preencherSelectsTaxonomiaDocumental();
            return;
        }
        try {
            const resposta = await fetch('/api/ir/documentos-empresa/taxonomia');
            const json = await resposta.json();
            if (json.success && json.data) {
                estado.taxonomiaDocumental = json.data;
            }
        } catch (error) {
            estado.taxonomiaDocumental = { tipos_documentais: [], categorias_documentais: [], status_documentais: [] };
        }
        preencherSelectsTaxonomiaDocumental();
    }

    function modoEmpresa() {
        return estado.contexto?.modo === 'DOCUMENTOS_FISCAIS_EMPRESA';
    }

    function aplicarContextoVisual() {
        const empresa = modoEmpresa();
        const titulo = estado.contexto?.titulo || (empresa ? 'Documentos da Empresa' : 'Imposto de Renda');
        document.body.classList.toggle('ir-doc-empresa', empresa);
        const pageTitle = document.querySelector('.page-title, .topbar-title, .app-topbar-title span, [data-page-title]');
        if (pageTitle) pageTitle.textContent = titulo;
        document.title = titulo;
        if ($('ir-btn-importar')) $('ir-btn-importar').textContent = empresa ? 'Importar documentos' : 'Importar comprovantes';
        if ($('ir-lista-titulo')) $('ir-lista-titulo').textContent = empresa ? 'Documentos da Empresa' : 'Comprovantes';
        if ($('ir-kpi-total-label')) $('ir-kpi-total-label').textContent = empresa ? 'Documentos cadastrados' : 'Comprovantes';
        if ($('ir-kpi-total-sub')) $('ir-kpi-total-sub').textContent = empresa ? 'todos os tipos' : 'documentos cadastrados';
        if ($('ir-kpi-valor-label')) $('ir-kpi-valor-label').textContent = empresa ? 'Documentos obrigatorios' : 'Valor potencialmente dedutivel';
        if ($('ir-kpi-valor-sub')) $('ir-kpi-valor-sub').textContent = empresa ? 'cadastros, licencas e certidoes' : 'sujeito a revisao';
        if ($('ir-kpi-pendentes-label')) $('ir-kpi-pendentes-label').textContent = empresa ? 'Vencendo em 30 dias' : 'Pendentes de revisao';
        if ($('ir-kpi-pendentes-sub')) $('ir-kpi-pendentes-sub').textContent = empresa ? 'acompanhar renovacoes' : 'aguardando validacao';
        if ($('ir-kpi-categorias-label')) $('ir-kpi-categorias-label').textContent = empresa ? 'Sem lastro' : 'Categorias IR usadas';
        if ($('ir-kpi-categorias-sub')) $('ir-kpi-categorias-sub').textContent = empresa ? 'pagamentos e notas sem vinculo' : 'classificacao potencial';
        aplicarIconesKpi(empresa);
        if ($('ir-pendencias-titulo')) $('ir-pendencias-titulo').textContent = empresa ? 'Pendencias de lastro' : 'Pendencias';
        if ($('ir-filtro-categoria-label')) $('ir-filtro-categoria-label').textContent = empresa ? 'Categoria fiscal' : 'Categoria IR';
        if ($('ir-filtro-categoria-wrap')) $('ir-filtro-categoria-wrap').hidden = empresa;
        if ($('ir-review-categoria-ir-label')) $('ir-review-categoria-ir-label').textContent = empresa ? 'Categoria fiscal' : 'Categoria IR';
        if ($('ir-saidas-sem-documento-panel')) $('ir-saidas-sem-documento-panel').hidden = !empresa;
        if ($('ir-review-patrimonio')) $('ir-review-patrimonio').hidden = !empresa;
        document.querySelectorAll('.ir-empresa-only').forEach((el) => { el.hidden = !empresa; });
        document.querySelectorAll('.ir-irpf-side').forEach((el) => { el.hidden = empresa; });
        atualizarStatusSelectPorContexto();
    }

    function aplicarIconesKpi(empresa) {
        const mapa = empresa
            ? [
                ['.ir-kpi-card.blue .ir-kpi-icon', 'receipt', 'Doc'],
                ['.ir-kpi-card.green .ir-kpi-icon', 'shield', '$'],
                ['.ir-kpi-card.yellow .ir-kpi-icon', 'calendar', '!'],
                ['.ir-kpi-card.purple .ir-kpi-icon', 'tag', '#'],
                ['.ir-kpi-card.orange .ir-kpi-icon', 'briefcase', '!'],
            ]
            : [
                ['.ir-kpi-card.blue .ir-kpi-icon', 'receipt', 'Doc'],
                ['.ir-kpi-card.green .ir-kpi-icon', 'cash', '$'],
                ['.ir-kpi-card.yellow .ir-kpi-icon', 'tag', '!'],
                ['.ir-kpi-card.purple .ir-kpi-icon', 'book', '#'],
            ];
        mapa.forEach(([selector, icone, fallback]) => {
            const el = document.querySelector(selector);
            if (!el) return;
            el.innerHTML = typeof window.renderIcon === 'function'
                ? window.renderIcon(icone, { size: '24px' })
                : fallback;
        });
    }

    function aplicarIconesAcoesEstaticas() {
        document.querySelectorAll('[data-ir-icon]').forEach((el) => {
            const label = el.textContent.trim() || el.getAttribute('aria-label') || el.title || 'Acao';
            const icone = renderIconeAcao(el.getAttribute('data-ir-icon'));
            el.innerHTML = `${icone}<span>${escapeHtml(label)}</span>`;
        });
    }

    function alternarFiltrosAvancados() {
        const panel = $('ir-filtros-avancados-panel');
        const trigger = $('ir-filtros-avancados-toggle');
        if (!panel || !trigger) return;
        const aberto = panel.hidden;
        panel.hidden = !aberto;
        trigger.setAttribute('aria-expanded', String(aberto));
    }

    function alternarFiltrosSaidas() {
        const panel = $('ir-saidas-filtros-panel');
        const trigger = $('ir-saidas-filtros-toggle');
        if (!panel || !trigger) return;
        const aberto = panel.hidden;
        panel.hidden = !aberto;
        trigger.setAttribute('aria-expanded', String(aberto));
    }

    function preencherSelectsTaxonomiaDocumental() {
        const tipos = estado.taxonomiaDocumental.tipos_documentais || [];
        const categorias = estado.taxonomiaDocumental.categorias_documentais || [];
        const status = estado.taxonomiaDocumental.status_documentais || [];
        const tipoOptions = '<option value="">Todos</option>' + tipos.map((item) => (
            `<option value="${escapeHtml(item.codigo)}">${escapeHtml(item.rotulo)}</option>`
        )).join('');
        const categoriaOptions = '<option value="">Todas</option>' + categorias.map((item) => (
            `<option value="${escapeHtml(item.codigo)}" data-tipo="${escapeHtml(item.tipo_documental || '')}">${escapeHtml(item.rotulo)}</option>`
        )).join('');
        const statusOptions = status.map((item) => (
            `<option value="${escapeHtml(item.codigo)}">${escapeHtml(item.rotulo)}</option>`
        )).join('');

        if ($('ir-filtro-tipo-documental')) $('ir-filtro-tipo-documental').innerHTML = tipoOptions;
        if ($('ir-filtro-categoria-documental')) $('ir-filtro-categoria-documental').innerHTML = categoriaOptions;
        if ($('ir-review-tipo-documental')) $('ir-review-tipo-documental').innerHTML = tipoOptions.replace('Todos', 'Selecione...');
        if ($('ir-review-categoria-documental')) $('ir-review-categoria-documental').innerHTML = categoriaOptions.replace('Todas', 'Selecione...');
        if ($('ir-review-status-documental')) $('ir-review-status-documental').innerHTML = statusOptions;
    }

    function atualizarStatusSelectPorContexto() {
        const select = $('ir-filtro-status');
        if (!select) return;
        const atual = select.value;
        if (modoEmpresa()) {
            const status = estado.taxonomiaDocumental.status_documentais || [];
            select.innerHTML = '<option value="TODOS">Todos</option>' + status.map((item) => (
                `<option value="${escapeHtml(item.codigo)}">${escapeHtml(item.rotulo)}</option>`
            )).join('');
            select.value = atual && Array.from(select.options).some((opcao) => opcao.value === atual) ? atual : 'TODOS';
            return;
        }
        select.innerHTML = `
            <option value="TODOS">Todos</option>
            <option value="CLASSIFICADO">Classificados</option>
            <option value="PENDENTE_REVISAO">Pendentes</option>
            <option value="VALIDADO">Validados</option>
            <option value="ERRO_LEITURA">Erro de leitura</option>
        `;
        select.value = atual && Array.from(select.options).some((opcao) => opcao.value === atual) ? atual : 'TODOS';
    }

    function atualizarAbaDocumentalAtiva() {
        document.querySelectorAll('#ir-doc-tabs button[data-tipo]').forEach((botao) => {
            botao.classList.toggle('active', (botao.dataset.tipo || '') === (estado.tipoDocumentalAtivo || ''));
        });
    }

    function sincronizarTipoPorCategoriaDocumental() {
        const categoria = $('ir-review-categoria-documental');
        const tipo = $('ir-review-tipo-documental');
        if (!categoria || !tipo) return;
        const tipoCategoria = categoria.options[categoria.selectedIndex]?.dataset?.tipo;
        if (tipoCategoria) tipo.value = tipoCategoria;
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
        const filtroAvancado = $('ir-filtro-categoria-fiscal-avancada');
        const review = $('ir-review-categoria-ir');
        if (filtro) {
            const atual = filtro.value;
            filtro.innerHTML = '<option value="">Todas</option>' + estado.categoriasIr.map((cat) => (
                `<option value="${cat.id}">${escapeHtml(cat.nome)}</option>`
            )).join('');
            filtro.value = atual;
        }
        if (filtroAvancado) {
            const atual = filtroAvancado.value;
            filtroAvancado.innerHTML = '<option value="">Todas</option>' + estado.categoriasIr.map((cat) => (
                `<option value="${cat.id}">${escapeHtml(cat.nome)}</option>`
            )).join('');
            filtroAvancado.value = atual;
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
        const vazio = estado.categoriasDespesa.length ? 'Selecione...' : 'Nenhuma categoria cadastrada';
        const options = `<option value="">${vazio}</option>` + estado.categoriasDespesa.map((cat) => (
            `<option value="${cat.id}" data-categoria-ir-id="${cat.categoria_ir_id || ''}" data-categoria-ir-nome="${escapeHtml(cat.categoria_ir_nome || '')}">${escapeHtml(cat.nome)}</option>`
        )).join('');
        if (select) select.innerHTML = options;
        if ($('ir-sugestao-categoria')) $('ir-sugestao-categoria').innerHTML = options;
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
        estado.paginaDocumentosEmpresa = 1;
        renderComprovantes();
        renderResumo(json.resumo || {});
    }

    function montarFiltrosRelatorio() {
        const params = new URLSearchParams();
        params.set('ano', $('ir-filtro-ano')?.value || new Date().getFullYear());
        const status = $('ir-filtro-status')?.value || 'TODOS';
        if (status && status !== 'TODOS') {
            params.set(modoEmpresa() ? 'status_documental' : 'status', status);
        }
        const tipoDocumental = $('ir-filtro-tipo-documental')?.value || estado.tipoDocumentalAtivo || '';
        if (modoEmpresa() && tipoDocumental) params.set('tipo_documental', tipoDocumental);
        const categoriaDocumental = $('ir-filtro-categoria-documental')?.value;
        if (modoEmpresa() && categoriaDocumental) params.set('categoria_documental', categoriaDocumental);
        const categoriaIr = modoEmpresa()
            ? $('ir-filtro-categoria-fiscal-avancada')?.value
            : $('ir-filtro-categoria')?.value;
        if (categoriaIr) params.set('categoria_ir_id', categoriaIr);
        if (modoEmpresa()) {
            const validade = $('ir-filtro-validade')?.value;
            const obrigatorio = $('ir-filtro-obrigatorio')?.value;
            if (validade) params.set('validade', validade);
            if (obrigatorio) params.set('obrigatorio', obrigatorio);
        }
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
        const textoOriginal = botao?.innerHTML;
        if (botao) {
            botao.disabled = true;
            botao.innerHTML = 'Gerando...';
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
                botao.innerHTML = textoOriginal;
            }
        }
    }

    async function baixarPacoteDocumentosEmpresa() {
        if (!modoEmpresa()) {
            mostrarAviso('Pacote de documentos empresariais disponivel apenas no perfil Empresa.');
            return;
        }
        const params = montarFiltrosRelatorio();
        const botao = $('ir-doc-btn-zip');
        const htmlOriginal = botao?.innerHTML;
        const tituloOriginal = botao?.title || '';
        if (botao) {
            botao.disabled = true;
            botao.title = 'Gerando pacote ZIP...';
            botao.setAttribute('aria-label', 'Gerando pacote ZIP para contador');
            botao.innerHTML = `${renderIconeAcao('archive')}<span>Gerando...</span>`;
        }
        try {
            const resposta = await fetch(`/api/ir/documentos-empresa/exportar-zip?${params.toString()}`);
            if (!resposta.ok) {
                let mensagem = 'Nao foi possivel gerar o pacote ZIP.';
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
            link.download = nomeArquivoResposta(resposta, 'Documentos_Empresa_Contador.zip');
            document.body.appendChild(link);
            link.click();
            link.remove();
            URL.revokeObjectURL(url);
        } catch (error) {
            mostrarAviso(error.message || 'Nao foi possivel gerar o pacote ZIP.');
        } finally {
            if (botao) {
                botao.disabled = false;
                botao.title = tituloOriginal;
                botao.setAttribute('aria-label', 'Gerar pacote ZIP para contador');
                botao.innerHTML = htmlOriginal;
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
        renderCabecalhoComprovantes();
        if (!estado.comprovantes.length) {
            const colunas = modoEmpresa() ? 7 : 10;
            tbody.innerHTML = `<tr><td colspan="${colunas}" class="ir-empty">Nenhum documento cadastrado para este ano.</td></tr>`;
            $('ir-lista-subtitulo').textContent = modoEmpresa() ? '- (0 documento(s) encontrado(s))' : '0 comprovantes encontrados';
            renderPaginacaoTabela('ir-comprovantes-pagination', 0, 1, 'irParaPaginaDocumentos');
            return;
        }

        $('ir-lista-subtitulo').textContent = modoEmpresa()
            ? `- (${estado.comprovantes.length} documento(s) encontrado(s))`
            : `${estado.comprovantes.length} comprovante(s) encontrado(s)`;
        if (modoEmpresa()) {
            estado.paginaDocumentosEmpresa = paginaValida(estado.paginaDocumentosEmpresa, estado.comprovantes.length);
            const itens = itensDaPagina(estado.comprovantes, estado.paginaDocumentosEmpresa);
            tbody.innerHTML = itens.map((item) => renderLinhaDocumentoEmpresa(item)).join('');
            renderPaginacaoTabela(
                'ir-comprovantes-pagination',
                estado.comprovantes.length,
                estado.paginaDocumentosEmpresa,
                'irParaPaginaDocumentos'
            );
            return;
        }
        renderPaginacaoTabela('ir-comprovantes-pagination', 0, 1, 'irParaPaginaDocumentos');
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
                        ${renderBotaoAcaoLinha('eye', 'Revisar', `window.IRDoc.abrirRevisao(${item.id})`)}
                        ${modoEmpresa() ? `<button type="button" class="ir-icon-btn" title="Vincular" onclick="window.IRDoc.abrirVinculo(${item.id})">Vincular</button>` : ''}
                        ${renderLinkAcaoLinha('file-text', 'Abrir arquivo', `/api/ir/comprovantes/${item.id}/arquivo`)}
                    </span>
                </td>
            </tr>
        `).join('');
    }

    function renderCabecalhoComprovantes() {
        const head = $('ir-comprovantes-head');
        if (!head) return;
        if (modoEmpresa()) {
            head.innerHTML = `
                <tr>
                    <th>Documento</th>
                    <th>Categoria</th>
                    <th>Emissao</th>
                    <th>Status</th>
                    <th>Tipo</th>
                    <th>Validade</th>
                    <th>Acoes</th>
                </tr>
            `;
            return;
        }
        head.innerHTML = `
            <tr>
                <th>Data</th>
                <th>Prestador</th>
                <th>Categoria IR</th>
                <th>Categoria de Despesa</th>
                <th>Valor</th>
                <th>Ano</th>
                <th>Natureza</th>
                <th>Lastro</th>
                <th>Status</th>
                <th>Acoes</th>
            </tr>
        `;
    }

    function renderLinhaDocumentoEmpresa(item) {
        const metadata = item.metadata_empresarial || {};
        const icone = renderIconeDocumental(item.icone_documental || metadata.icone || 'tag');
        const classeIcone = classeIconeDocumental(item.tipo_documental || metadata.tipo_documental, item.categoria_documental || metadata.categoria_documental);
        const nome = item.prestador_nome || item.arquivo?.nome_arquivo || `Documento #${item.id}`;
        return `
            <tr>
                <td>
                    <span class="ir-doc-cell">
                        <span class="ir-doc-icon ${classeIcone}">${icone}</span>
                        <strong title="${escapeHtml(nome)}">${escapeHtml(nome)}</strong>
                    </span>
                </td>
                <td>${escapeHtml(item.categoria_documental_label || metadata.categoria_documental_label || 'Sem categoria')}</td>
                <td>${formatarData(metadata.data_emissao || item.data_documento)}</td>
                <td>${renderStatusDocumental(item.status_documental || metadata.status_documental)}</td>
                <td>${escapeHtml(item.tipo_documental_label || metadata.tipo_documental_label || 'Outro')}</td>
                <td>${metadata.data_validade ? formatarData(metadata.data_validade) : 'Permanente'}</td>
                <td>
                    <span class="ir-row-actions">
                        ${renderBotaoAcaoLinha('eye', 'Revisar', `window.IRDoc.abrirRevisao(${item.id})`)}
                        ${renderBotaoAcaoLinha('link', 'Vincular', `window.IRDoc.abrirVinculo(${item.id})`)}
                        ${renderLinkAcaoLinha('file-text', 'Abrir arquivo', `/api/ir/comprovantes/${item.id}/arquivo`)}
                    </span>
                </td>
            </tr>
        `;
    }

    function itensDaPagina(lista, pagina) {
        const inicio = (pagina - 1) * ITENS_POR_PAGINA_TABELA;
        return lista.slice(inicio, inicio + ITENS_POR_PAGINA_TABELA);
    }

    function paginaValida(pagina, total) {
        const totalPaginas = Math.max(1, Math.ceil(total / ITENS_POR_PAGINA_TABELA));
        return Math.min(Math.max(Number(pagina) || 1, 1), totalPaginas);
    }

    function renderPaginacaoTabela(id, total, pagina, acao) {
        const destino = $(id);
        if (!destino) return;
        if (!total) {
            destino.hidden = true;
            destino.innerHTML = '';
            return;
        }
        const totalPaginas = Math.max(1, Math.ceil(total / ITENS_POR_PAGINA_TABELA));
        const paginaAtual = paginaValida(pagina, total);
        const inicio = ((paginaAtual - 1) * ITENS_POR_PAGINA_TABELA) + 1;
        const fim = Math.min(total, paginaAtual * ITENS_POR_PAGINA_TABELA);
        const primeiroBotao = Math.max(1, Math.min(paginaAtual - 2, Math.max(1, totalPaginas - 4)));
        const ultimoBotao = Math.min(totalPaginas, primeiroBotao + 4);
        const botoes = [];
        for (let numero = primeiroBotao; numero <= ultimoBotao; numero += 1) {
            botoes.push(`
                <button type="button" class="${numero === paginaAtual ? 'active' : ''}" onclick="window.IRDoc.${acao}(${numero})" aria-label="Ir para pagina ${numero}">${numero}</button>
            `);
        }
        destino.hidden = false;
        destino.innerHTML = `
            <span>Exibindo ${inicio} a ${fim} de ${total} registros</span>
            <div class="ir-pagination-controls">
                <button type="button" onclick="window.IRDoc.${acao}(${paginaAtual - 1})" ${paginaAtual <= 1 ? 'disabled' : ''} aria-label="Pagina anterior">${renderIconeAcao('chevron-left')}</button>
                ${botoes.join('')}
                <button type="button" onclick="window.IRDoc.${acao}(${paginaAtual + 1})" ${paginaAtual >= totalPaginas ? 'disabled' : ''} aria-label="Proxima pagina">${renderIconeAcao('chevron-right')}</button>
            </div>
        `;
    }

    function renderResumo(resumo) {
        const lastro = resumo.lastro || {};
        const documentosEmpresa = resumo.documentos_empresa || {};
        estado.resumoDocumentosEmpresa = documentosEmpresa;
        $('ir-kpi-total').textContent = String(modoEmpresa() ? (documentosEmpresa.documentos_cadastrados || 0) : (resumo.total_comprovantes || 0));
        $('ir-kpi-valor').textContent = formatarMoeda(
            modoEmpresa() ? (lastro.valor_com_lastro || 0) : (resumo.valor_potencialmente_dedutivel || 0)
        );
        if (modoEmpresa()) {
            $('ir-kpi-valor').textContent = String(documentosEmpresa.documentos_obrigatorios || 0);
        }
        $('ir-kpi-pendentes').textContent = String(
            modoEmpresa() ? (documentosEmpresa.vencendo_30_dias || 0) : (resumo.pendentes_revisao || 0)
        );
        $('ir-kpi-categorias').textContent = String(
            modoEmpresa() ? (documentosEmpresa.sem_lastro || 0) : (resumo.categorias_ir_usadas || 0)
        );
        if ($('ir-kpi-extra')) $('ir-kpi-extra').textContent = String(documentosEmpresa.aguardando_contador || 0);
        $('ir-pendencias').innerHTML = modoEmpresa()
            ? `<span>${lastro.documentos_sem_vinculo || 0} documentos sem vinculo de lastro</span>`
            : `<span>${resumo.pendentes_revisao || 0} documentos pendentes de revisao</span>`;
        const totais = resumo.totais_por_categoria_ir || [];
        const destino = $('ir-totais-categorias');
        if (!destino) return;
        if (!totais.length) {
            destino.innerHTML = '<p class="ir-empty">Nenhuma categoria consolidada.</p>';
            if (modoEmpresa()) {
                renderPainelDocumentosEmpresa(documentosEmpresa);
            }
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
        if (modoEmpresa()) {
            renderPainelDocumentosEmpresa(documentosEmpresa);
        }
    }

    function renderPainelDocumentosEmpresa(resumo) {
        const tipos = $('ir-tipos-documentos');
        if (tipos) {
            const itens = resumo.distribuicao_por_tipo || [];
            const maior = Math.max(...itens.map((item) => Number(item.quantidade) || 0), 1);
            tipos.innerHTML = itens.length ? itens.map((item, index) => {
                const quantidade = Number(item.quantidade) || 0;
                const largura = Math.max(8, Math.round((quantidade / maior) * 100));
                const cor = classeSequencial(index);
                return `
                <div class="ir-side-item ir-side-item--type">
                    <span class="ir-side-type-name">${escapeHtml(item.rotulo)}</span>
                    <strong>${quantidade}</strong>
                    <span class="ir-side-bar"><span class="${escapeHtml(cor)}" style="width:${largura}%"></span></span>
                </div>
            `;
            }).join('') : '<p class="ir-empty">Nenhum tipo consolidado.</p>';
        }
        const checklist = $('ir-checklist-empresarial');
        if (checklist) {
            const itens = resumo.checklist_empresarial || [];
            checklist.innerHTML = itens.length ? itens.map((item) => {
                const status = String(item.status || 'pendente').toLowerCase();
                const icone = status === 'ok' ? 'shield' : 'calendar';
                return `
                    <div class="ir-check-item">
                        <span class="ir-check-label"><span class="ir-check-icon ${escapeHtml(status)}">${renderIconeDocumental(icone)}</span>${escapeHtml(item.label)}</span>
                        <span class="ir-check-status ${escapeHtml(status)}">${escapeHtml(status)}</span>
                    </div>
                `;
            }).join('') : '<p class="ir-empty">Checklist ainda sem documentos.</p>';
        }
    }

    function classeSequencial(index) {
        return ['c-blue', 'c-purple', 'c-green', 'c-orange', 'c-teal', 'c-red'][index % 6];
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
            estado.paginaSaidas = 1;
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
            if (subtitulo) subtitulo.textContent = '- (Disponivel apenas no perfil Empresa)';
            renderPaginacaoTabela('ir-saidas-pagination', 0, 1, 'irParaPaginaSaidas');
            return;
        }
        if (!estado.saidasSemDocumento.length) {
            tbody.innerHTML = '<tr><td colspan="8" class="ir-empty">Nenhuma saida sem documento no periodo.</td></tr>';
            if (subtitulo) subtitulo.textContent = '- (0 saida(s) sem documento encontrada(s))';
            renderPaginacaoTabela('ir-saidas-pagination', 0, 1, 'irParaPaginaSaidas');
            return;
        }
        if (subtitulo) subtitulo.textContent = `- (${estado.saidasSemDocumento.length} saida(s) sem documento encontrada(s))`;
        estado.paginaSaidas = paginaValida(estado.paginaSaidas, estado.saidasSemDocumento.length);
        const itens = itensDaPagina(estado.saidasSemDocumento, estado.paginaSaidas);
        renderPaginacaoTabela('ir-saidas-pagination', estado.saidasSemDocumento.length, estado.paginaSaidas, 'irParaPaginaSaidas');
        tbody.innerHTML = itens.map((saida) => `
            <tr>
                <td>
                    <span class="ir-saida-cell">
                        <span class="ir-doc-icon ${escapeHtml(classeIconeSaida(saida))}">${renderIconeDocumental(iconeSaidaLastro(saida))}</span>
                        <span class="ir-saida-descricao" title="${escapeHtml(saida.descricao || 'Saida financeira')}">${escapeHtml(saida.descricao || 'Saida financeira')}</span>
                    </span>
                </td>
                <td>${escapeHtml(saida.categoria || '-')}</td>
                <td>${formatarData(saida.data)}</td>
                <td>${renderLastro(saida.status_lastro)}</td>
                <td>${escapeHtml(saida.origem || '-')}</td>
                <td>${formatarMoeda(saida.valor)}</td>
                <td>${formatarNatureza(saida.natureza_sugerida)}</td>
                <td>
                    <span class="ir-saida-actions">
                        ${renderBotaoAcaoLinha('link', 'Vincular documento', `window.IRDoc.abrirVinculoSaida('${saida.tipo_entidade}', ${saida.entidade_id})`)}
                        ${renderBotaoAcaoLinha('user', 'Aguardando contador', `window.IRDoc.abrirStatusSaida('${saida.tipo_entidade}', ${saida.entidade_id}, 'AGUARDANDO_CONTADOR')`)}
                        ${renderBotaoAcaoLinha('ban', 'Nao aplicavel', `window.IRDoc.abrirStatusSaida('${saida.tipo_entidade}', ${saida.entidade_id}, 'NAO_APLICAVEL')`)}
                        ${renderBotaoAcaoLinha('info', 'Ver origem', `window.IRDoc.verOrigemSaida('${saida.tipo_entidade}', ${saida.entidade_id})`)}
                    </span>
                </td>
            </tr>
        `).join('');
    }

    function iconeSaidaLastro(saida) {
        const status = String(saida?.status_lastro || '').toUpperCase();
        if (status === 'AGUARDANDO_CONTADOR') return 'user';
        if (status === 'NAO_APLICAVEL') return 'ban';
        const origem = String(saida?.origem || saida?.tipo_entidade || '').toUpperCase();
        if (origem.includes('LANCAMENTO') || origem.includes('MOVIMENTO')) return 'receipt';
        if (origem.includes('CONTA') || origem.includes('DESPESA')) return 'tag';
        return 'receipt';
    }

    function classeIconeSaida(saida) {
        const status = String(saida?.status_lastro || '').toUpperCase();
        if (status === 'AGUARDANDO_CONTADOR') return 'document-type--procuracao';
        if (status === 'NAO_APLICAVEL') return 'document-type--contrato';
        return 'document-type--financeiro';
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
        atualizarResumoImportacao();
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
        atualizarResumoImportacao();
    }

    function atualizarResumoImportacao() {
        const resumo = estado.resumoImportacao || {};
        const enviados = estado.arquivosSelecionados.length || resumo.enviados || 0;
        [
            ['ir-import-enviados', resumo.enviados || enviados],
            ['ir-import-lidos', resumo.lidos || 0],
            ['ir-import-pendentes', resumo.pendentes || (estado.arquivosSelecionados.length ? estado.arquivosSelecionados.length : 0)],
            ['ir-import-erros', resumo.erros || 0],
        ].forEach(([id, valor]) => {
            if ($(id)) $(id).textContent = String(valor);
        });
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
        renderBlocoCupomFiscal(item);
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
        preencherMetadataRevisao(item.metadata_empresarial || {});
        $('ir-review-observacoes').value = item.observacoes || '';
        $('ir-review-modal').classList.add('open');
        $('ir-review-modal').setAttribute('aria-hidden', 'false');
    }

    function preencherMetadataRevisao(metadata) {
        if (!modoEmpresa()) return;
        if ($('ir-review-tipo-documental')) $('ir-review-tipo-documental').value = metadata.tipo_documental || 'OUTRO';
        if ($('ir-review-categoria-documental')) $('ir-review-categoria-documental').value = metadata.categoria_documental || 'SEM_CATEGORIA';
        if ($('ir-review-numero-documento')) $('ir-review-numero-documento').value = metadata.numero_documento || '';
        if ($('ir-review-orgao-emissor')) $('ir-review-orgao-emissor').value = metadata.orgao_emissor || '';
        if ($('ir-review-data-emissao')) $('ir-review-data-emissao').value = metadata.data_emissao || $('ir-review-data')?.value || '';
        if ($('ir-review-data-validade')) $('ir-review-data-validade').value = metadata.data_validade || '';
        if ($('ir-review-status-documental')) $('ir-review-status-documental').value = metadata.status_documental || 'ATIVO';
        if ($('ir-review-responsavel-interno')) $('ir-review-responsavel-interno').value = metadata.responsavel_interno || '';
        if ($('ir-review-obrigatorio')) $('ir-review-obrigatorio').checked = Boolean(metadata.obrigatorio);
        if ($('ir-review-renovavel')) $('ir-review-renovavel').checked = Boolean(metadata.renovavel);
        if ($('ir-review-alerta-dias')) $('ir-review-alerta-dias').value = metadata.alerta_dias_antes || 30;
    }

    function renderAvisoOcrRevisao(item) {
        const alerta = $('ir-review-ocr-alert');
        if (!alerta) return;
        const resumo = obterResumoOcr(item);
        alerta.textContent = resumo.mensagem || '';
        alerta.hidden = !resumo.mensagem;
    }

    function renderBlocoCupomFiscal(item) {
        const bloco = $('ir-cupom-fiscal-bloco');
        if (!bloco) return;
        const eventos = Array.isArray(item.eventos) ? item.eventos : [];
        const evDetect = eventos.find(e => e.tipo_evento === 'CUPOM_FISCAL_DETECTADO');
        if (!evDetect) {
            bloco.hidden = true;
            return;
        }

        // Tipo detectado a partir da descricao do evento
        const descEvento = evDetect.descricao || '';
        const tipoMatch = descEvento.match(/\(([^)]+)\)/);
        const tipoBadge = $('ir-cupom-tipo-badge');
        if (tipoBadge) tipoBadge.textContent = tipoMatch ? tipoMatch[1] : 'CUPOM_FISCAL';

        function setRow(rowId, ddId, valor) {
            const row = $(rowId);
            const dd = $(ddId);
            if (!row || !dd) return;
            if (valor) {
                dd.textContent = valor;
                row.hidden = false;
            } else {
                row.hidden = true;
            }
        }

        setRow('ir-cupom-estabelecimento-row', 'ir-cupom-estabelecimento', item.prestador_nome || '');
        setRow('ir-cupom-cnpj-row', 'ir-cupom-cnpj', item.prestador_cpf_cnpj || '');
        setRow('ir-cupom-data-row', 'ir-cupom-data', item.data_documento || '');
        const valorFmt = item.valor != null ? 'R$ ' + Number(item.valor).toLocaleString('pt-BR', {minimumFractionDigits: 2}) : '';
        setRow('ir-cupom-valor-row', 'ir-cupom-valor', valorFmt);

        // Chave de acesso nas observacoes
        const obs = item.observacoes || '';
        const chaveMatch = obs.match(/Chave de acesso:\s*(\d{44})/);
        setRow('ir-cupom-chave-row', 'ir-cupom-chave', chaveMatch ? chaveMatch[1] : '');

        // Avisos do evento de extracao
        const evExtract = eventos.find(e => e.tipo_evento === 'CUPOM_FISCAL_EXTRAIDO');
        const avisosDiv = $('ir-cupom-avisos');
        if (avisosDiv) {
            const textoAvisos = evExtract && evExtract.descricao && evExtract.descricao.includes('avisos:')
                ? evExtract.descricao.replace('Extracao concluida com avisos:', '').trim()
                : '';
            if (textoAvisos) {
                avisosDiv.innerHTML = textoAvisos.split(';').map(a => `<p class="ir-cupom-aviso-item">${a.trim()}</p>`).join('');
                avisosDiv.hidden = false;
            } else {
                avisosDiv.hidden = true;
            }
        }

        bloco.hidden = false;
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
        if (modoEmpresa()) {
            const metadataOk = await salvarMetadataEmpresarial(id);
            if (!metadataOk) return;
        }
        fecharRevisao();
        await carregarComprovantes();
    }

    async function salvarMetadataEmpresarial(id) {
        const payload = {
            tipo_documental: $('ir-review-tipo-documental')?.value || 'OUTRO',
            categoria_documental: $('ir-review-categoria-documental')?.value || 'SEM_CATEGORIA',
            numero_documento: $('ir-review-numero-documento')?.value || '',
            orgao_emissor: $('ir-review-orgao-emissor')?.value || '',
            data_emissao: $('ir-review-data-emissao')?.value || $('ir-review-data')?.value || '',
            data_validade: $('ir-review-data-validade')?.value || '',
            status_documental: $('ir-review-status-documental')?.value || 'ATIVO',
            obrigatorio: Boolean($('ir-review-obrigatorio')?.checked),
            renovavel: Boolean($('ir-review-renovavel')?.checked),
            alerta_dias_antes: $('ir-review-alerta-dias')?.value || 30,
            responsavel_interno: $('ir-review-responsavel-interno')?.value || '',
            origem_documental: 'USUARIO',
        };
        const resposta = await fetch(`/api/ir/comprovantes/${id}/metadata-empresarial`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const json = await resposta.json();
        if (!json.success) {
            mostrarAviso(json.error || 'Nao foi possivel salvar os metadados empresariais.');
            return false;
        }
        return true;
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
            renderAvisoOcrRevisao(item);
            renderBlocoCupomFiscal(item);
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

    async function abrirSugestaoFinanceira() {
        const id = $('ir-review-id')?.value;
        if (!id) {
            mostrarAviso('Abra a revisao de um documento antes de gerar a sugestao financeira.');
            return;
        }
        const botao = $('ir-review-financeiro');
        const textoOriginal = botao?.textContent;
        if (botao) {
            botao.disabled = true;
            botao.textContent = 'Gerando...';
        }
        try {
            await carregarRecursosFinanceirosSugestao();
            const resposta = await fetch(`/api/ir/comprovantes/${id}/sugestao-financeira`);
            const json = await resposta.json();
            if (!json.success) {
                mostrarAviso(json.error || 'Nao foi possivel gerar a sugestao financeira.');
                return;
            }
            estado.sugestaoFinanceira = json.data;
            preencherModalSugestaoFinanceira(json.data);
            $('ir-sugestao-financeira-modal')?.classList.add('open');
            $('ir-sugestao-financeira-modal')?.setAttribute('aria-hidden', 'false');
        } finally {
            if (botao) {
                botao.disabled = false;
                botao.textContent = textoOriginal || 'Gerar sugestao financeira';
            }
        }
    }

    function fecharSugestaoFinanceira() {
        $('ir-sugestao-financeira-modal')?.classList.remove('open');
        $('ir-sugestao-financeira-modal')?.setAttribute('aria-hidden', 'true');
    }

    async function carregarRecursosFinanceirosSugestao() {
        const [cartoesResposta, contasResposta] = await Promise.all([
            fetch('/api/cartoes').catch(() => null),
            fetch('/api/contas').catch(() => null),
        ]);

        if (cartoesResposta?.ok) {
            const jsonCartoes = await cartoesResposta.json();
            estado.cartoes = Array.isArray(jsonCartoes) ? jsonCartoes : (jsonCartoes.data || []);
        }
        if (contasResposta?.ok) {
            const jsonContas = await contasResposta.json();
            estado.contasBancarias = jsonContas.data || [];
        }
    }

    function preencherModalSugestaoFinanceira(sugestao) {
        if (!sugestao) return;
        $('ir-sugestao-comprovante-id').value = sugestao.comprovante_id;
        $('ir-sugestao-tipo-destino').value = sugestao.tipo_destino_sugerido || 'DESPESA';
        $('ir-sugestao-forma-pagamento').value = sugestao.forma_pagamento || 'outros';
        $('ir-sugestao-descricao').value = sugestao.descricao || '';
        $('ir-sugestao-valor').value = sugestao.valor || '';
        $('ir-sugestao-data').value = sugestao.data || '';
        $('ir-sugestao-competencia').value = sugestao.competencia || (sugestao.data ? String(sugestao.data).slice(0, 7) : '');
        preencherSelectCategoriasDespesa();
        $('ir-sugestao-categoria').value = sugestao.categoria_id || '';
        $('ir-sugestao-observacoes').value = sugestao.observacoes || '';
        $('ir-sugestao-documento').innerHTML = `
            <strong>${escapeHtml(sugestao.documento?.nome_arquivo || 'Documento fiscal')}</strong>
            <small>${escapeHtml(sugestao.fornecedor || 'Fornecedor nao identificado')}${sugestao.cpf_cnpj ? ` - ${escapeHtml(sugestao.cpf_cnpj)}` : ''}</small>
        `;
        preencherSelectCartoesSugestao();
        preencherSelectContasSugestao();
        renderAlertasSugestao(sugestao.avisos || []);
        atualizarCategoriaIrSugestao(sugestao.categoria_ir_nome || '');
        atualizarCamposSugestaoFinanceira();
    }

    function preencherSelectCartoesSugestao() {
        const select = $('ir-sugestao-cartao');
        if (!select) return;
        const vazio = estado.cartoes.length ? 'Selecione o cartao...' : 'Nenhum cartao ativo';
        select.innerHTML = `<option value="">${vazio}</option>` + estado.cartoes.map((cartao) => (
            `<option value="${cartao.id}">${escapeHtml(cartao.nome || `Cartao #${cartao.id}`)}</option>`
        )).join('');
    }

    function preencherSelectContasSugestao() {
        const select = $('ir-sugestao-conta-bancaria');
        if (!select) return;
        const vazio = estado.contasBancarias.length ? 'Opcional para baixa financeira...' : 'Nenhuma conta bancaria ativa';
        select.innerHTML = `<option value="">${vazio}</option>` + estado.contasBancarias.map((conta) => (
            `<option value="${conta.id}">${escapeHtml(conta.nome || `Conta #${conta.id}`)}${conta.instituicao ? ` - ${escapeHtml(conta.instituicao)}` : ''}</option>`
        )).join('');
    }

    function atualizarCamposSugestaoFinanceira() {
        const tipoDestino = $('ir-sugestao-tipo-destino')?.value || 'DESPESA';
        const forma = $('ir-sugestao-forma-pagamento')?.value || 'outros';
        const usarCartao = forma === 'cartao';
        if ($('ir-sugestao-cartao-wrap')) $('ir-sugestao-cartao-wrap').hidden = !usarCartao;
        if ($('ir-sugestao-conta-wrap')) $('ir-sugestao-conta-wrap').hidden = usarCartao || tipoDestino === 'DESPESA';
        if ($('ir-sugestao-confirmar')) {
            $('ir-sugestao-confirmar').textContent = tipoDestino === 'LANCAMENTO' ? 'Criar lancamento' : 'Criar despesa';
        }
        resolverCategoriaCartaoSugestao();
    }

    function atualizarCategoriaIrSugestao(fallback = '') {
        const select = $('ir-sugestao-categoria');
        const campo = $('ir-sugestao-categoria-ir');
        const aviso = $('ir-sugestao-categoria-aviso');
        if (!select || !campo) return;
        const opcao = select.options[select.selectedIndex];
        const nomeIr = opcao?.dataset?.categoriaIrNome || fallback || '';
        campo.value = nomeIr || 'Sem vinculo configurado';
        if (aviso) {
            const mensagem = select.value && !nomeIr ? 'Categoria de Despesa ainda sem vinculo com Categoria IR/Fiscal.' : '';
            aviso.textContent = mensagem;
            aviso.hidden = !mensagem;
        }
    }

    async function resolverCategoriaCartaoSugestao() {
        const info = $('ir-sugestao-categoria-cartao-info');
        const forma = $('ir-sugestao-forma-pagamento')?.value || '';
        const cartaoId = $('ir-sugestao-cartao')?.value || '';
        const categoriaId = $('ir-sugestao-categoria')?.value || '';
        if (!info) return;
        if (forma !== 'cartao') {
            info.textContent = '';
            info.hidden = true;
            return;
        }
        if (!cartaoId || !categoriaId) {
            info.textContent = 'Categoria do Cartao sera resolvida automaticamente apos selecionar cartao e Categoria de Despesa.';
            info.hidden = false;
            return;
        }
        try {
            const params = new URLSearchParams({ cartao_id: cartaoId, categoria_id: categoriaId });
            const resposta = await fetch(`/api/categorias-cartao/resolver?${params.toString()}`);
            const json = await resposta.json();
            const resolucao = json.data || json;
            info.textContent = resolucao.aviso || 'Categoria do Cartao resolvida automaticamente.';
            info.hidden = false;
        } catch (error) {
            info.textContent = 'Nao foi possivel consultar a Categoria do Cartao automaticamente.';
            info.hidden = false;
        }
    }

    function renderAlertasSugestao(avisos) {
        const box = $('ir-sugestao-alertas');
        if (!box) return;
        const itens = (avisos || []).filter(Boolean);
        if (!itens.length) {
            box.hidden = true;
            box.innerHTML = '';
            return;
        }
        box.hidden = false;
        box.innerHTML = `<ul>${itens.map((aviso) => `<li>${escapeHtml(aviso)}</li>`).join('')}</ul>`;
    }

    async function confirmarSugestaoFinanceira() {
        const id = $('ir-sugestao-comprovante-id')?.value;
        if (!id) return;
        const botao = $('ir-sugestao-confirmar');
        const textoOriginal = botao?.textContent;
        if (botao) {
            botao.disabled = true;
            botao.textContent = 'Criando...';
        }
        const payload = {
            tipo_destino: $('ir-sugestao-tipo-destino').value,
            descricao: $('ir-sugestao-descricao').value,
            valor: $('ir-sugestao-valor').value,
            data: $('ir-sugestao-data').value,
            competencia: $('ir-sugestao-competencia').value,
            categoria_id: $('ir-sugestao-categoria').value || null,
            forma_pagamento: $('ir-sugestao-forma-pagamento').value,
            cartao_id: $('ir-sugestao-cartao').value || null,
            conta_bancaria_id: $('ir-sugestao-conta-bancaria').value || null,
            observacoes: $('ir-sugestao-observacoes').value,
        };
        try {
            const resposta = await fetch(`/api/ir/comprovantes/${id}/criar-financeiro`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const json = await resposta.json();
            if (!json.success) {
                mostrarAviso(json.error || 'Nao foi possivel criar a entidade financeira.');
                return;
            }
            const avisos = json.data?.avisos || [];
            if (avisos.length) mostrarAviso(avisos.join('\n'));
            fecharSugestaoFinanceira();
            fecharRevisao();
            await carregarComprovantes();
            await carregarSaidasSemDocumento();
        } finally {
            if (botao) {
                botao.disabled = false;
                botao.textContent = textoOriginal || 'Criar despesa';
            }
        }
    }

    async function abrirSugestaoPatrimonio() {
        const id = $('ir-review-id')?.value;
        if (!id) {
            mostrarAviso('Abra a revisao de um documento antes de sugerir um bem patrimonial.');
            return;
        }
        if (!modoEmpresa()) {
            mostrarAviso('Sugestao patrimonial disponivel apenas no perfil Empresa.');
            return;
        }
        const botao = $('ir-review-patrimonio');
        const textoOriginal = botao?.textContent;
        if (botao) {
            botao.disabled = true;
            botao.textContent = 'Gerando...';
        }
        try {
            const resposta = await fetch(`/api/patrimonio/bens/sugestao-a-partir-documento/${id}`);
            const json = await resposta.json();
            if (!json.success) {
                mostrarAviso(json.error || 'Nao foi possivel gerar a sugestao patrimonial.');
                return;
            }
            estado.sugestaoPatrimonio = json.data;
            preencherModalSugestaoPatrimonio(json.data);
            $('ir-sugestao-patrimonio-modal')?.classList.add('open');
            $('ir-sugestao-patrimonio-modal')?.setAttribute('aria-hidden', 'false');
        } finally {
            if (botao) {
                botao.disabled = false;
                botao.textContent = textoOriginal || 'Sugerir bem patrimonial';
            }
        }
    }

    function fecharSugestaoPatrimonio() {
        $('ir-sugestao-patrimonio-modal')?.classList.remove('open');
        $('ir-sugestao-patrimonio-modal')?.setAttribute('aria-hidden', 'true');
    }

    function preencherModalSugestaoPatrimonio(sugestao) {
        if (!sugestao) return;
        $('ir-patrimonio-comprovante-id').value = sugestao.comprovante_id;
        $('ir-patrimonio-imagem-arquivo').value = sugestao.imagem_arquivo || '';
        $('ir-patrimonio-nome').value = sugestao.nome || '';
        $('ir-patrimonio-categoria').value = sugestao.categoria || 'Outros';
        $('ir-patrimonio-fornecedor').value = sugestao.fornecedor || '';
        $('ir-patrimonio-documento-numero').value = sugestao.documento_numero || '';
        $('ir-patrimonio-data').value = sugestao.data_aquisicao || '';
        $('ir-patrimonio-valor').value = sugestao.valor_aquisicao || '';
        $('ir-patrimonio-vida-util').value = sugestao.vida_util_meses || '';
        $('ir-patrimonio-centro-custo').value = sugestao.centro_custo || '';
        $('ir-patrimonio-localizacao').value = sugestao.localizacao || '';
        $('ir-patrimonio-responsavel').value = sugestao.responsavel || '';
        $('ir-patrimonio-descricao').value = sugestao.descricao || '';
        $('ir-patrimonio-observacoes').value = sugestao.observacoes || '';
        $('ir-patrimonio-documento').innerHTML = `
            <strong>${escapeHtml(sugestao.documento?.arquivo?.nome_arquivo || sugestao.documento?.label || 'Documento fiscal')}</strong>
            <small>${escapeHtml(sugestao.fornecedor || 'Fornecedor nao identificado')}${sugestao.documento?.valor != null ? ` - ${formatarMoeda(sugestao.documento.valor)}` : ''}</small>
        `;
        renderAlertasPatrimonio(sugestao.avisos || []);
        atualizarDepreciacaoPatrimonio();
        const confirmar = $('ir-sugestao-patrimonio-confirmar');
        if (confirmar) {
            confirmar.disabled = Boolean(sugestao.bloqueado);
            confirmar.textContent = sugestao.bloqueado ? 'Documento ja vinculado' : 'Criar bem patrimonial';
        }
    }

    function renderAlertasPatrimonio(avisos) {
        const box = $('ir-patrimonio-alertas');
        if (!box) return;
        const itens = (avisos || []).filter(Boolean);
        if (!itens.length) {
            box.hidden = true;
            box.innerHTML = '';
            return;
        }
        box.hidden = false;
        box.innerHTML = `<ul>${itens.map((aviso) => `<li>${escapeHtml(aviso)}</li>`).join('')}</ul>`;
    }

    function atualizarDepreciacaoPatrimonio() {
        const valor = Number($('ir-patrimonio-valor')?.value || 0);
        const meses = Number($('ir-patrimonio-vida-util')?.value || 0);
        const campo = $('ir-patrimonio-depreciacao');
        if (!campo) return;
        campo.value = valor > 0 && meses > 0 ? formatarMoeda(valor / meses) : '';
    }

    async function confirmarSugestaoPatrimonio() {
        const id = $('ir-patrimonio-comprovante-id')?.value;
        if (!id) return;
        const botao = $('ir-sugestao-patrimonio-confirmar');
        const textoOriginal = botao?.textContent;
        if (botao) {
            botao.disabled = true;
            botao.textContent = 'Criando...';
        }
        const payload = {
            comprovante_id: id,
            nome: $('ir-patrimonio-nome').value,
            categoria: $('ir-patrimonio-categoria').value,
            descricao: $('ir-patrimonio-descricao').value,
            fornecedor: $('ir-patrimonio-fornecedor').value,
            documento_numero: $('ir-patrimonio-documento-numero').value,
            data_aquisicao: $('ir-patrimonio-data').value,
            valor_aquisicao: $('ir-patrimonio-valor').value,
            vida_util_meses: $('ir-patrimonio-vida-util').value,
            centro_custo: $('ir-patrimonio-centro-custo').value,
            localizacao: $('ir-patrimonio-localizacao').value,
            responsavel: $('ir-patrimonio-responsavel').value,
            imagem_arquivo: $('ir-patrimonio-imagem-arquivo').value,
            observacoes: $('ir-patrimonio-observacoes').value,
            status_documental: 'COM_LASTRO',
            natureza: 'PATRIMONIO_IMOBILIZADO',
        };
        try {
            const resposta = await fetch('/api/patrimonio/bens/criar-a-partir-documento', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const json = await resposta.json();
            if (!json.success) {
                mostrarAviso(json.error || 'Nao foi possivel criar o bem patrimonial.');
                return;
            }
            fecharSugestaoPatrimonio();
            fecharRevisao();
            await carregarComprovantes();
            await carregarSaidasSemDocumento();
            mostrarAviso('Bem patrimonial criado e vinculado ao documento fiscal.');
        } finally {
            if (botao) {
                botao.disabled = false;
                botao.textContent = textoOriginal || 'Criar bem patrimonial';
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

    function renderStatusDocumental(status) {
        const chave = String(status || 'ATIVO').toUpperCase();
        const mapa = {
            ATIVO: ['validado', 'Ativo'],
            VALIDO: ['validado', 'Valido'],
            VENCENDO: ['vencendo', 'Vencendo'],
            VENCIDO: ['erro', 'Vencido'],
            PENDENTE: ['pendente', 'Pendente'],
            EM_REVISAO: ['pendente', 'Em revisao'],
            AGUARDANDO_CONTADOR: ['contador', 'Aguardando contador'],
            SEM_LASTRO: ['sem-lastro', 'Sem lastro'],
            COM_LASTRO: ['classificado', 'Com lastro'],
            NAO_APLICAVEL: ['neutral', 'Nao aplicavel'],
            ARQUIVADO: ['neutral', 'Arquivado'],
        };
        const [classe, label] = mapa[chave] || mapa.ATIVO;
        return `<span class="ir-status ${classe}">${label}</span>`;
    }

    function classeStatusDocumental(status) {
        const chave = String(status || '').toUpperCase();
        if (['ATIVO', 'VALIDO', 'COM_LASTRO'].includes(chave)) return 'ok';
        if (chave === 'VENCENDO' || chave === 'AGUARDANDO_CONTADOR') return 'warning';
        if (chave === 'VENCIDO' || chave === 'SEM_LASTRO') return 'danger';
        return 'neutral';
    }

    function renderIconeDocumental(chave) {
        if (typeof window.renderIcon === 'function') {
            return window.renderIcon(chave || 'tag', { size: '18px' });
        }
        return '';
    }

    function renderIconeAcao(chave) {
        if (ICONES_ACAO_IMG[chave]) {
            return `
                <i class="ir-action-img-box" aria-hidden="true">
                    <img class="ir-action-img" src="${ICONES_ACAO_IMG[chave]}" alt="" aria-hidden="true" onerror="this.hidden=true; this.nextElementSibling.hidden=false">
                    <svg class="ir-action-fallback" viewBox="0 0 24 24" focusable="false" hidden><path d="M6 3h9l3 3v15H6V3Z"/><path d="M15 3v4h4"/><path d="M9 12h6M9 16h6M9 20h4"/></svg>
                </i>
            `;
        }
        if (typeof window.renderIcon === 'function') {
            return window.renderIcon(chave || 'default', { size: '15px' });
        }
        return '';
    }

    function renderBotaoAcaoLinha(icone, label, onclick) {
        return `
            <button type="button" class="ir-icon-btn ir-icon-only" title="${escapeHtml(label)}" aria-label="${escapeHtml(label)}" onclick="${escapeHtml(onclick)}">
                ${renderIconeAcao(icone)}<span class="sr-only">${escapeHtml(label)}</span>
            </button>
        `;
    }

    function renderLinkAcaoLinha(icone, label, href) {
        return `
            <a class="ir-icon-btn ir-icon-only" title="${escapeHtml(label)}" aria-label="${escapeHtml(label)}" href="${escapeHtml(href)}" target="_blank" rel="noopener">
                ${renderIconeAcao(icone)}<span class="sr-only">${escapeHtml(label)}</span>
            </a>
        `;
    }

    function classeIconeDocumental(tipo, categoria) {
        const chave = String(tipo || categoria || '').toUpperCase();
        if (['DOCUMENTO_OBRIGATORIO', 'CERTIDAO_LICENCA'].includes(chave)) return 'document-type--obrigatorio';
        if (['DOCUMENTO_SOCIETARIO'].includes(chave)) return 'document-type--societario';
        if (['PROCURACAO_REPRESENTACAO'].includes(chave)) return 'document-type--procuracao';
        if (['PAGAMENTO_REALIZADO', 'NOTA_FISCAL_RECEBIDA', 'NOTA_FISCAL_EMITIDA'].includes(chave)) return 'document-type--financeiro';
        if (['PATRIMONIO_IMOBILIZADO'].includes(chave)) return 'document-type--patrimonio';
        if (['CONTRATO_INSTRUMENTO', 'CONTABIL_FISCAL'].includes(chave)) return 'document-type--contrato';
        return 'document-type--default';
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

    function irParaPaginaDocumentos(pagina) {
        estado.paginaDocumentosEmpresa = paginaValida(pagina, estado.comprovantes.length);
        renderComprovantes();
    }

    function irParaPaginaSaidas(pagina) {
        estado.paginaSaidas = paginaValida(pagina, estado.saidasSemDocumento.length);
        renderSaidasSemDocumento();
    }

    window.IRDoc = {
        abrirRevisao,
        abrirVinculo,
        abrirVinculoSaida,
        abrirStatusSaida,
        verOrigemSaida,
        abrirSugestaoFinanceira,
        abrirSugestaoPatrimonio,
        carregarComprovantes,
        carregarSaidasSemDocumento,
        irParaPaginaDocumentos,
        irParaPaginaSaidas,
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
