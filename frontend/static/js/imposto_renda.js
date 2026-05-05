(function () {
    'use strict';

    const estado = {
        categoriasIr: [],
        categoriasDespesa: [],
        comprovantes: [],
        arquivosSelecionados: [],
        resumoImportacao: { enviados: 0, lidos: 0, pendentes: 0, erros: 0 },
        categoriaIrManual: false,
        contexto: { modo: 'IRPF' },
    };

    const $ = (id) => document.getElementById(id);

    document.addEventListener('DOMContentLoaded', inicializarIr);

    async function inicializarIr() {
        definirAnoPadrao();
        vincularEventos();
        await carregarContexto();
        await Promise.all([carregarCategoriasIr(), carregarCategoriasDespesa()]);
        await carregarComprovantes();
    }

    function definirAnoPadrao() {
        const ano = String(new Date().getFullYear());
        ['ir-filtro-ano', 'ir-upload-ano'].forEach((id) => {
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
        $('ir-btn-exportar')?.addEventListener('click', () => mostrarAviso('Relatorios Excel/PDF ficam para etapa futura.'));
        $('ir-filtro-ano')?.addEventListener('change', carregarComprovantes);
        $('ir-filtro-status')?.addEventListener('change', carregarComprovantes);
        $('ir-filtro-categoria')?.addEventListener('change', carregarComprovantes);
        $('ir-filtro-busca')?.addEventListener('input', debounce(carregarComprovantes, 250));
        $('ir-upload-submit')?.addEventListener('click', enviarArquivos);
        $('ir-select-files')?.addEventListener('click', () => $('ir-file-input')?.click());
        $('ir-file-input')?.addEventListener('change', (event) => selecionarArquivos(event.target.files));
        $('ir-review-close')?.addEventListener('click', fecharRevisao);
        $('ir-review-save')?.addEventListener('click', salvarRevisao);
        $('ir-review-validar')?.addEventListener('click', validarComprovante);
        $('ir-review-categoria')?.addEventListener('change', resolverCategoriaIrDaDespesa);
        $('ir-review-categoria-ir')?.addEventListener('change', () => {
            estado.categoriaIrManual = true;
            atualizarAvisoVinculo('');
        });
        $('ir-link-close')?.addEventListener('click', fecharVinculo);
        $('ir-link-cancel')?.addEventListener('click', fecharVinculo);
        $('ir-link-save')?.addEventListener('click', salvarVinculo);
        $('ir-link-tipo-entidade')?.addEventListener('change', carregarEntidadesVinculaveis);

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
        const params = new URLSearchParams();
        params.set('ano', $('ir-filtro-ano')?.value || new Date().getFullYear());
        const status = $('ir-filtro-status')?.value || 'TODOS';
        if (status && status !== 'TODOS') params.set('status', status);
        const categoriaIr = $('ir-filtro-categoria')?.value;
        if (categoriaIr) params.set('categoria_ir_id', categoriaIr);
        const busca = $('ir-filtro-busca')?.value;
        if (busca) params.set('busca', busca);

        const resposta = await fetch(`/api/ir/comprovantes?${params.toString()}`);
        const json = await resposta.json();
        estado.comprovantes = json.data || [];
        renderComprovantes();
        renderResumo(json.resumo || {});
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
            : '<p class="ir-upload-muted">Nenhum texto extraido disponivel. Se for imagem ou PDF escaneado, ficara para OCR futuro.</p>';

        return `
            <div class="ir-upload-item ir-upload-card">
                <div class="ir-upload-card-head">
                    <div>
                        <strong>${escapeHtml(arquivo.nome_arquivo || 'Comprovante')}</strong>
                        <small>${escapeHtml(resultado.mensagem || '')}${resultado.duplicado ? ' O registro existente foi carregado para revisao.' : ''}</small>
                    </div>
                    <div class="ir-upload-badges">
                        ${extraido ? '<span class="ir-mini-badge ok">Texto extraido</span>' : '<span class="ir-mini-badge">Sem texto</span>'}
                        ${renderStatus(status)}
                    </div>
                </div>
                ${notaAno}
                <div class="ir-upload-extracted">
                    ${resumo.map(([label, value]) => `<span><small>${label}</small><strong>${escapeHtml(value)}</strong></span>`).join('')}
                </div>
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
        $('ir-review-texto').textContent = item.texto_extraido || 'Texto extraido indisponivel. Documento pendente de revisao manual ou OCR futuro.';
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
        carregarComprovantes,
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
