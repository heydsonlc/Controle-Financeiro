(function () {
    'use strict';

    const estado = {
        categoriasIr: [],
        categoriasDespesa: [],
        comprovantes: [],
        arquivosSelecionados: [],
        resumoImportacao: { enviados: 0, lidos: 0, pendentes: 0, erros: 0 },
    };

    const $ = (id) => document.getElementById(id);

    document.addEventListener('DOMContentLoaded', inicializarIr);

    async function inicializarIr() {
        definirAnoPadrao();
        vincularEventos();
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

    async function carregarCategoriasIr() {
        const resposta = await fetch('/api/ir/categorias');
        const json = await resposta.json();
        estado.categoriasIr = json.data || [];
        preencherSelectCategoriasIr();
    }

    async function carregarCategoriasDespesa() {
        try {
            const resposta = await fetch('/api/categorias');
            const json = await resposta.json();
            estado.categoriasDespesa = json.data || [];
        } catch (error) {
            estado.categoriasDespesa = [];
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
            review.innerHTML = '<option value="">Selecione...</option>' + estado.categoriasIr.map((cat) => (
                `<option value="${cat.id}">${escapeHtml(cat.nome)}</option>`
            )).join('');
        }
    }

    function preencherSelectCategoriasDespesa() {
        const select = $('ir-review-categoria');
        if (!select) return;
        select.innerHTML = '<option value="">Selecione...</option>' + estado.categoriasDespesa.map((cat) => (
            `<option value="${cat.id}">${escapeHtml(cat.nome)}</option>`
        )).join('');
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
            tbody.innerHTML = '<tr><td colspan="8" class="ir-empty">Nenhum comprovante cadastrado para este ano.</td></tr>';
            $('ir-lista-subtitulo').textContent = '0 comprovantes encontrados';
            return;
        }

        $('ir-lista-subtitulo').textContent = `${estado.comprovantes.length} comprovante(s) encontrado(s)`;
        tbody.innerHTML = estado.comprovantes.map((item) => `
            <tr>
                <td>${formatarData(item.data_documento)}</td>
                <td>${escapeHtml(item.prestador_nome || item.arquivo?.nome_arquivo || 'Sem prestador')}</td>
                <td>${escapeHtml(item.categoria_ir_nome || '-')}</td>
                <td>${escapeHtml(item.categoria_nome || '-')}</td>
                <td>${formatarMoeda(item.valor)}</td>
                <td>${item.ano_calendario || '-'}</td>
                <td>${renderStatus(item.status)}</td>
                <td>
                    <span class="ir-row-actions">
                        <button type="button" class="ir-icon-btn" title="Revisar" onclick="window.IRDoc.abrirRevisao(${item.id})">Ver</button>
                        <a class="ir-icon-btn" title="Abrir arquivo" href="/api/ir/comprovantes/${item.id}/arquivo" target="_blank" rel="noopener">PDF</a>
                    </span>
                </td>
            </tr>
        `).join('');
    }

    function renderResumo(resumo) {
        $('ir-kpi-total').textContent = String(resumo.total_comprovantes || 0);
        $('ir-kpi-valor').textContent = formatarMoeda(resumo.valor_potencialmente_dedutivel || 0);
        $('ir-kpi-pendentes').textContent = String(resumo.pendentes_revisao || 0);
        $('ir-kpi-categorias').textContent = String(resumo.categorias_ir_usadas || 0);
        $('ir-pendencias').innerHTML = `<span>${resumo.pendentes_revisao || 0} documentos pendentes de revisao</span>`;

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
        destino.innerHTML = resultados.map((resultado) => {
            if (!resultado.success) {
                resumo.erros += 1;
                return `<div class="ir-upload-item"><strong>${escapeHtml(resultado.arquivo || 'Arquivo')}</strong><span>${escapeHtml(resultado.error)}</span><span>${renderStatus('ERRO_LEITURA')}</span></div>`;
            }
            const comprovante = resultado.data?.comprovante || {};
            const status = comprovante.status || (resultado.data?.duplicado ? 'IMPORTADO' : 'PENDENTE_REVISAO');
            if (status === 'CLASSIFICADO' || status === 'VALIDADO') resumo.lidos += 1;
            if (status === 'PENDENTE_REVISAO' || status === 'IMPORTADO') resumo.pendentes += 1;
            if (status === 'ERRO_LEITURA') resumo.erros += 1;
            return `<div class="ir-upload-item"><strong>${escapeHtml(comprovante.arquivo?.nome_arquivo || 'Comprovante')}</strong><span>${escapeHtml(resultado.data?.mensagem || '')}</span><span>${renderStatus(status)}</span></div>`;
        }).join('');
        estado.resumoImportacao = resumo;
        $('ir-import-enviados').textContent = resumo.enviados;
        $('ir-import-lidos').textContent = resumo.lidos;
        $('ir-import-pendentes').textContent = resumo.pendentes;
        $('ir-import-erros').textContent = resumo.erros;
    }

    async function abrirRevisao(id) {
        const resposta = await fetch(`/api/ir/comprovantes/${id}`);
        const json = await resposta.json();
        if (!json.success) {
            mostrarAviso(json.error || 'Nao foi possivel abrir o comprovante.');
            return;
        }
        const item = json.data;
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
        $('ir-review-observacoes').value = item.observacoes || '';
        $('ir-review-modal').classList.add('open');
        $('ir-review-modal').setAttribute('aria-hidden', 'false');
    }

    function fecharRevisao() {
        $('ir-review-modal').classList.remove('open');
        $('ir-review-modal').setAttribute('aria-hidden', 'true');
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
        carregarComprovantes,
    };
}());
