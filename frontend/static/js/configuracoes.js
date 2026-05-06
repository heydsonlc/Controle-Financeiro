(function () {
    'use strict';

    const API_PERFIS = '/api/perfis-financeiros';
    const API_PREFERENCIAS = '/api/preferencias';
    const API_BACKUP = '/api/backup';
    const API_OCR = '/api/ocr';
    const state = {
        perfis: [],
        ativo: null,
        selecionado: null,
        preferencias: {},
        backup: {
            status: null,
            historico: [],
            testesRestauracao: [],
            carregado: false
        },
        ocr: {
            status: null,
            carregado: false
        },
        secao: 'perfis-financeiros'
    };

    const $ = (id) => document.getElementById(id);

    const ajuda = {
        'perfis-financeiros': {
            titulo: 'Como funciona o contexto financeiro',
            itens: [
                ['Perfis independentes', 'Cada perfil possui dados, configurações e relatórios separados.'],
                ['Troca rápida', 'Alterne entre perfis pelo seletor no topo sem sair da aplicação.'],
                ['Personalização total', 'Defina preferências e comportamentos específicos para cada perfil.'],
                ['Dica', 'Crie perfis para separar suas finanças pessoais das da empresa.']
            ]
        },
        'preferencias-gerais': {
            titulo: 'Preferências globais',
            itens: [
                ['Dados preservados', 'A tela usa os mesmos campos e a mesma API de Preferências já existente.'],
                ['Escopo atual', 'Estas preferências continuam globais até uma etapa específica de preferências por perfil.']
            ]
        },
        aparencia: {
            titulo: 'Aparência',
            itens: [
                ['Tema e cor', 'As opções visuais existentes foram consolidadas nesta central.'],
                ['Evolução futura', 'Densidade visual e estilos avançados podem ser adicionados depois.']
            ]
        },
        comportamento: {
            titulo: 'Comportamento',
            itens: [
                ['Ações sensíveis', 'Confirmações e avisos continuam controlados como preferências globais.'],
                ['Sem regras novas', 'Nenhuma regra financeira foi alterada nesta tela.']
            ]
        },
        backup: {
            titulo: 'Backup',
            itens: [
                ['Ferramentas PostgreSQL', 'Configure pg_dump e pg_restore quando eles não estiverem no PATH do Windows.'],
                ['Restauração segura', 'Restore continua exigindo confirmação textual forte antes de executar.']
            ]
        },
        'ia-automacao': {
            titulo: 'IA e Automação',
            itens: [
                ['Classificação', 'Preferências existentes para automação continuam disponíveis.'],
                ['Sem IA nova', 'Esta etapa não adiciona integração externa nem modelos novos.']
            ]
        },
        'documentos-fiscais': {
            titulo: 'Documentos fiscais por perfil',
            itens: [
                ['Pessoal', 'O perfil pessoal usa Imposto de Renda e comprovantes potencialmente dedutíveis.'],
                ['Empresa', 'O perfil empresa usa Documentos Fiscais e Lastro Empresarial.'],
                ['Revisão fiscal', 'Classificações seguem informativas e sujeitas à validação contábil.']
            ]
        }
    };

    function escapeHtml(value) {
        return String(value ?? '').replace(/[&<>"']/g, (char) => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;'
        }[char]));
    }

    function iniciais(perfil) {
        if (perfil?.avatar) return String(perfil.avatar).slice(0, 3).toUpperCase();
        const partes = String(perfil?.nome || 'PF').trim().split(/\s+/).filter(Boolean);
        if (!partes.length) return 'PF';
        if (partes.length === 1) return partes[0].slice(0, 2).toUpperCase();
        return `${partes[0][0]}${partes[1][0]}`.toUpperCase();
    }

    function tipoLabel(tipo) {
        const value = String(tipo || '').toUpperCase();
        if (value === 'PESSOAL') return 'Pessoal';
        if (value === 'EMPRESA') return 'Empresa';
        return 'Outro';
    }

    function mostrarMensagem(message, tipo = 'info') {
        const alert = $('config-profile-alert');
        if (!alert) return;
        alert.textContent = message || '';
        alert.dataset.tipo = tipo;
        alert.hidden = !message;
    }

    function mostrarBackupMensagem(message, tipo = 'info') {
        const alert = $('backup-alert');
        if (!alert) return;
        alert.textContent = message || '';
        alert.dataset.tipo = tipo;
        alert.hidden = !message;
    }

    function mostrarOcrMensagem(message, tipo = 'info') {
        const alert = $('ocr-alert');
        if (!alert) return;
        alert.textContent = message || '';
        alert.dataset.tipo = tipo;
        alert.hidden = !message;
    }

    function formatarDataHora(valor) {
        if (!valor) return '-';
        const data = new Date(valor);
        if (Number.isNaN(data.getTime())) return String(valor);
        return data.toLocaleString('pt-BR', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    }

    function statusLabel(status) {
        const valor = String(status || '').toLowerCase();
        if (valor === 'concluido') return 'Concluído';
        if (valor === 'erro') return 'Erro';
        return valor || '-';
    }

    function tipoBackupLabel(tipo) {
        const valor = String(tipo || '').toLowerCase();
        if (valor === 'manual') return 'Manual';
        if (valor === 'automatico') return 'Automático';
        return valor || '-';
    }

    async function requestJson(url, options = {}) {
        const response = await fetch(url, {
            headers: {
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                ...(options.headers || {})
            },
            ...options
        });
        const data = await response.json();
        if (!response.ok || data?.success === false) {
            throw new Error(data.error || data.message || 'Falha na operação');
        }
        return data;
    }

    async function carregarBackup() {
        if (!$('config-section-backup')) return;
        try {
            const [status, historico, testesRestauracao] = await Promise.all([
                requestJson(`${API_BACKUP}/status`),
                requestJson(`${API_BACKUP}/historico`),
                requestJson(`${API_BACKUP}/testes-restauracao`)
            ]);
            state.backup.status = status;
            state.backup.historico = historico.data || [];
            state.backup.testesRestauracao = testesRestauracao.data || [];
            state.backup.carregado = true;
            renderBackup();
        } catch (error) {
            mostrarBackupMensagem(error.message);
            renderBackup();
        }
    }

    async function carregarOcr() {
        if (!$('config-section-ia-automacao')) return;
        try {
            state.ocr.status = await requestJson(`${API_OCR}/status`);
            state.ocr.carregado = true;
            renderOcr();
        } catch (error) {
            mostrarOcrMensagem(error.message, 'error');
            renderOcr();
        }
    }

    function renderOcr() {
        const status = state.ocr.status || {};
        const config = status.configuracao || {};
        preencherCampoFerramenta('ocr-tesseract-path', config.tesseract_path);
        preencherCampoFerramenta('ocr-poppler-path', config.poppler_path);
        renderOcrBadge('ocr-status-tesseract', status.tesseract?.disponivel, status.tesseract?.disponivel ? 'Disponivel' : 'Nao encontrado', status.tesseract?.mensagem);
        renderOcrBadge('ocr-status-por', status.tesseract?.por_disponivel, status.tesseract?.por_disponivel ? 'Disponivel' : 'Ausente', status.tesseract?.mensagem);
        renderOcrBadge('ocr-status-poppler', status.poppler?.disponivel, status.poppler?.disponivel ? 'Disponivel' : 'Nao encontrado', status.poppler?.mensagem);
        renderOcrBadge('ocr-status-images', status.pronto_para_imagens, status.pronto_para_imagens ? 'Preparado' : 'Indisponivel');
        renderOcrBadge('ocr-status-pdf', status.pronto_para_pdf_escaneado, status.pronto_para_pdf_escaneado ? 'Preparado' : 'Indisponivel');
        const detalhe = $('ocr-status-tesseract-detail');
        if (detalhe) detalhe.textContent = status.tesseract?.versao || '-';
        const recomendacao = $('ocr-recommendation');
        if (recomendacao) recomendacao.textContent = (status.recomendacoes || ['OCR ainda nao processa documentos nesta etapa.']).join(' ');
        if (status.tesseract?.disponivel && !status.tesseract?.por_disponivel) {
            mostrarOcrMensagem('Tesseract encontrado, mas o idioma portugues nao esta instalado. O OCR pode funcionar, mas tera menor precisao em documentos brasileiros.', 'error');
        } else if (status.poppler && !status.poppler.disponivel) {
            mostrarOcrMensagem('Poppler nao encontrado. OCR em imagens podera ser preparado futuramente, mas PDF escaneado exigira conversao de paginas.', 'error');
        } else if (status.tesseract || status.poppler) {
            mostrarOcrMensagem('Ferramentas OCR configuradas.', 'success');
        }
    }

    function renderOcrBadge(id, ok, label, title = '') {
        const badge = $(id);
        if (!badge) return;
        badge.className = 'config-backup-status';
        badge.classList.add(ok ? 'disponivel' : 'nao-encontrado');
        badge.textContent = label || (ok ? 'Disponivel' : 'Nao encontrado');
        badge.title = title || '';
    }

    function renderBackup() {
        renderBackupAgendamento();
        renderBackupFerramentas();
        renderBackupHistorico();
        renderBackupTestesRestauracao();
        if (state.secao === 'backup') {
            renderBackupPainel();
        }
    }

    function renderBackupAgendamento() {
        const agendamento = state.backup.status?.agendamento || {};
        const ativo = $('backup-schedule-active');
        const frequencia = $('backup-schedule-frequency');
        const horario = $('backup-schedule-time');
        const retencao = $('backup-schedule-retention');
        const proximo = $('backup-schedule-next');
        const nota = $('backup-schedule-note');
        if (ativo) ativo.checked = Boolean(agendamento.ativo);
        if (frequencia && agendamento.frequencia) frequencia.value = agendamento.frequencia;
        if (horario && agendamento.horario) horario.value = agendamento.horario;
        if (retencao && agendamento.retencao_dias) retencao.value = agendamento.retencao_dias;
        if (proximo) proximo.textContent = agendamento.proximo_backup_estimado || '-';
        if (nota) nota.textContent = agendamento.mensagem || 'Configuração visual preparada. Agendamento automático será ativado em etapa futura.';
    }

    function renderBackupFerramentas() {
        const ferramentas = state.backup.status?.ferramentas || {};
        const config = ferramentas.configuracao || {};
        preencherCampoFerramenta('backup-pg-dump-path', config.pg_dump_path);
        preencherCampoFerramenta('backup-pg-restore-path', config.pg_restore_path);
        preencherCampoFerramenta('backup-psql-path', config.psql_path);
        renderBackupFerramentaBadge('backup-tool-pg-dump-status', ferramentas.ferramentas?.pg_dump, true);
        renderBackupFerramentaBadge('backup-tool-pg-restore-status', ferramentas.ferramentas?.pg_restore, true);
        renderBackupFerramentaBadge('backup-tool-psql-status', ferramentas.ferramentas?.psql, false);
        const ultima = $('backup-tools-last-validation');
        if (ultima) ultima.textContent = formatarDataHora(ferramentas.ultima_validacao || config.ultima_validacao);
    }

    function preencherCampoFerramenta(id, valor) {
        const campo = $(id);
        if (!campo || document.activeElement === campo) return;
        campo.value = valor || '';
    }

    function renderBackupFerramentaBadge(id, info, obrigatorio) {
        const badge = $(id);
        if (!badge) return;
        const disponivel = Boolean(info?.disponivel);
        badge.className = 'config-backup-status';
        if (disponivel) {
            badge.classList.add('disponivel');
            badge.textContent = info?.origem === 'configurado' ? 'Configurado' : 'Disponível';
            badge.title = [info?.caminho, info?.versao].filter(Boolean).join(' | ');
            return;
        }
        if (!obrigatorio) {
            badge.classList.add('opcional');
            badge.textContent = 'Opcional';
            badge.title = info?.mensagem || '';
            return;
        }
        badge.classList.add('nao-encontrado');
        badge.textContent = 'Não encontrado';
        badge.title = info?.mensagem || '';
    }

    function renderBackupHistorico() {
        const tbody = $('backup-history-body');
        const seletor = $('backup-restore-file');
        const seletorTeste = $('backup-test-restore-file');
        if (!tbody) return;

        if (!state.backup.historico.length) {
            tbody.innerHTML = '<tr><td colspan="5">Nenhum backup registrado ainda.</td></tr>';
        } else {
            tbody.innerHTML = state.backup.historico.slice(0, 8).map((item) => {
                const podeBaixar = item.arquivo && item.status === 'concluido';
                return `
                    <tr>
                        <td>${escapeHtml(formatarDataHora(item.created_at))}</td>
                        <td>${escapeHtml(tipoBackupLabel(item.tipo))}</td>
                        <td><span class="config-backup-status ${escapeHtml(item.status)}">${escapeHtml(statusLabel(item.status))}</span></td>
                        <td>${escapeHtml(item.tamanho_formatado || '-')}</td>
                        <td>
                            ${podeBaixar ? `<button type="button" class="config-table-link" data-backup-download="${escapeHtml(item.arquivo)}">Baixar</button>` : '<span class="config-muted">-</span>'}
                        </td>
                    </tr>
                `;
            }).join('');
        }

        if (seletor) {
            const selecionaveis = state.backup.historico.filter((item) => item.arquivo && item.status === 'concluido');
            seletor.innerHTML = '<option value="">Selecione um backup</option>' + selecionaveis.map((item) => (
                `<option value="${escapeHtml(item.arquivo)}">${escapeHtml(item.arquivo)} · ${escapeHtml(item.tamanho_formatado || '')}</option>`
            )).join('');
        }
    }

    function renderBackupTestesRestauracao() {
        const seletorTeste = $('backup-test-restore-file');
        if (seletorTeste) {
            const selecionaveis = state.backup.historico.filter((item) => item.arquivo && item.status === 'concluido');
            seletorTeste.innerHTML = '<option value="">Selecione um backup</option>' + selecionaveis.map((item) => (
                `<option value="${escapeHtml(item.arquivo)}">${escapeHtml(item.arquivo)} - ${escapeHtml(item.tamanho_formatado || '')}</option>`
            )).join('');
        }

        const tbody = $('backup-restore-test-history-body');
        if (!tbody) return;
        const historico = state.backup.testesRestauracao || [];
        if (!historico.length) {
            tbody.innerHTML = '<tr><td colspan="5">Nenhum teste de restauracao registrado.</td></tr>';
            return;
        }

        tbody.innerHTML = historico.slice(0, 8).map((item) => `
            <tr>
                <td>${escapeHtml(formatarDataHora(item.data_hora))}</td>
                <td>${escapeHtml(item.backup_arquivo || '-')}</td>
                <td><span class="config-backup-status ${escapeHtml(item.status)}">${escapeHtml(statusLabel(item.status))}</span></td>
                <td>${escapeHtml(formatarDuracao(item.duracao_segundos))}</td>
                <td>${item.removido_apos_teste ? 'Sim' : 'Nao'}</td>
            </tr>
        `).join('');
    }

    function formatarDuracao(valor) {
        const segundos = Number(valor || 0);
        if (!Number.isFinite(segundos) || segundos <= 0) return '-';
        if (segundos < 60) return `${segundos.toFixed(1).replace('.', ',')}s`;
        const minutos = Math.floor(segundos / 60);
        const resto = Math.round(segundos % 60);
        return `${minutos}min ${resto}s`;
    }

    function renderBackupTesteResultado(resultado) {
        const alvo = $('backup-test-restore-result');
        if (!alvo) return;
        if (!resultado) {
            alvo.hidden = true;
            alvo.innerHTML = '';
            return;
        }
        const validacoes = resultado.validacoes || [];
        alvo.hidden = false;
        alvo.dataset.status = resultado.status || 'erro';
        alvo.innerHTML = `
            <strong>${escapeHtml(resultado.mensagem || 'Teste de restauracao processado.')}</strong>
            <span>Banco descartavel: ${escapeHtml(resultado.database_teste || '-')} ${resultado.removido_apos_teste ? '- removido ao final' : '- mantido para inspecao'}</span>
            ${validacoes.length ? `
                <ul>
                    ${validacoes.slice(0, 8).map((item) => `
                        <li class="${item.ok ? 'ok' : 'warn'}">${escapeHtml(item.item || 'validacao')}: ${escapeHtml(item.mensagem || (item.ok ? 'OK' : 'Atencao'))}</li>
                    `).join('')}
                </ul>
            ` : ''}
        `;
    }

    function renderBackupPainel() {
        const title = $('config-help-title');
        const content = $('config-help-content');
        const status = state.backup.status || {};
        const ferramentas = status.ferramentas?.ferramentas || {};
        if (title) title.textContent = 'Status do backup';
        if (!content) return;
        const checklist = status.checklist || [];
        content.innerHTML = `
            <div class="config-backup-side">
                <div class="config-backup-side-status ${escapeHtml(status.status || 'atencao')}">
                    <strong>${status.status === 'ok' ? 'Tudo certo' : 'Atenção necessária'}</strong>
                    <span>${status.ultimo_backup ? 'Histórico local encontrado.' : 'Nenhum backup concluído registrado.'}</span>
                </div>
                <section>
                    <h3>Checklist rápido</h3>
                    <div class="config-backup-side-list">
                        ${checklist.map((item) => `
                            <span class="${item.ok ? 'ok' : 'warn'}">
                                <i aria-hidden="true">${item.ok ? '✓' : '!'}</i>
                                ${escapeHtml(item.label)}
                            </span>
                        `).join('')}
                    </div>
                </section>
                <section>
                    <h3>Informações rápidas</h3>
                    <dl class="config-backup-info">
                        <dt>Último backup</dt>
                        <dd>${escapeHtml(formatarDataHora(status.ultimo_backup?.created_at))}</dd>
                        <dt>Engine do banco</dt>
                        <dd>${escapeHtml(status.engine || 'PostgreSQL')}</dd>
                        <dt>pg_dump</dt>
                        <dd>${ferramentas.pg_dump?.disponivel ? 'Disponível' : 'Não encontrado'}</dd>
                        <dt>pg_restore</dt>
                        <dd>${ferramentas.pg_restore?.disponivel ? 'Disponível' : 'Não encontrado'}</dd>
                        <dt>Última validação</dt>
                        <dd>${escapeHtml(formatarDataHora(status.ferramentas?.ultima_validacao))}</dd>
                        <dt>Retenção configurada</dt>
                        <dd>${escapeHtml(status.retencao_dias || 30)} dias</dd>
                        <dt>Tamanho médio</dt>
                        <dd>${escapeHtml(status.tamanho_medio_formatado || '0 B')}</dd>
                    </dl>
                </section>
                <section class="config-backup-recommendation">
                    <strong>Recomendação</strong>
                    <span>${escapeHtml(status.recomendacao || 'Exporte configurações após alterações importantes.')}</span>
                    <button type="button" class="config-secondary-action" id="backup-side-export">Exportar configurações</button>
                </section>
            </div>
        `;
        $('backup-side-export')?.addEventListener('click', exportarConfiguracoes);
    }

    async function executarBackup() {
        const botao = $('backup-run');
        mostrarBackupMensagem('Executando backup local do PostgreSQL...', 'info');
        if (botao) {
            botao.disabled = true;
            botao.textContent = 'Executando...';
        }
        try {
            const resposta = await requestJson(`${API_BACKUP}/executar`, { method: 'POST', body: '{}' });
            mostrarBackupMensagem(resposta.message || 'Backup concluído.', 'success');
        } catch (error) {
            mostrarBackupMensagem(error.message, 'error');
        } finally {
            if (botao) {
                botao.disabled = false;
                botao.textContent = 'Executar backup';
            }
            await carregarBackup();
        }
    }

    async function salvarAgendamentoBackup() {
        const payload = {
            ativo: obterCheckbox('backup-schedule-active'),
            frequencia: obterCampo('backup-schedule-frequency') || 'diaria',
            horario: obterCampo('backup-schedule-time') || '02:00',
            retencao_dias: parseInt(obterCampo('backup-schedule-retention'), 10) || 30
        };
        try {
            const resposta = await requestJson(`${API_BACKUP}/agendamento`, {
                method: 'POST',
                body: JSON.stringify(payload)
            });
            state.backup.status = state.backup.status || {};
            state.backup.status.agendamento = resposta.data;
            mostrarBackupMensagem(resposta.message || 'Agendamento salvo.', 'success');
            renderBackup();
        } catch (error) {
            mostrarBackupMensagem(error.message);
        }
    }

    async function validarFerramentasBackup() {
        try {
            const resposta = await requestJson(`${API_BACKUP}/ferramentas/status`);
            state.backup.status = state.backup.status || {};
            state.backup.status.ferramentas = resposta;
            renderBackup();
            mostrarBackupMensagem(resposta.disponivel ? 'Ferramentas PostgreSQL disponíveis.' : 'Ferramentas PostgreSQL incompletas. Configure os caminhos.', resposta.disponivel ? 'success' : 'error');
        } catch (error) {
            mostrarBackupMensagem(error.message, 'error');
        }
    }

    async function autodetectarFerramentasBackup() {
        try {
            const resposta = await requestJson(`${API_BACKUP}/ferramentas/autodetectar`, {
                method: 'POST',
                body: '{}'
            });
            state.backup.status = state.backup.status || {};
            state.backup.status.ferramentas = resposta;
            renderBackup();
            mostrarBackupMensagem(resposta.mensagem || 'Autodetecção concluída.', resposta.disponivel ? 'success' : 'error');
        } catch (error) {
            mostrarBackupMensagem(error.message, 'error');
        }
    }

    async function salvarFerramentasBackup() {
        const payload = {
            pg_dump_path: obterCampo('backup-pg-dump-path').trim(),
            pg_restore_path: obterCampo('backup-pg-restore-path').trim(),
            psql_path: obterCampo('backup-psql-path').trim()
        };
        try {
            const resposta = await requestJson(`${API_BACKUP}/ferramentas/configurar`, {
                method: 'POST',
                body: JSON.stringify(payload)
            });
            state.backup.status = state.backup.status || {};
            state.backup.status.ferramentas = resposta;
            renderBackup();
            mostrarBackupMensagem(resposta.disponivel ? 'Caminhos salvos e validados.' : 'Caminhos salvos, mas alguma ferramenta não foi validada.', resposta.disponivel ? 'success' : 'error');
        } catch (error) {
            mostrarBackupMensagem(error.message, 'error');
        }
    }

    async function validarFerramentasOcr() {
        try {
            state.ocr.status = await requestJson(`${API_OCR}/validar`, {
                method: 'POST',
                body: '{}'
            });
            state.ocr.carregado = true;
            renderOcr();
            mostrarOcrMensagem(state.ocr.status.pronto_para_imagens ? 'Ferramentas OCR validadas.' : 'Ferramentas OCR incompletas.', state.ocr.status.pronto_para_imagens ? 'success' : 'error');
        } catch (error) {
            mostrarOcrMensagem(error.message, 'error');
        }
    }

    async function autodetectarFerramentasOcr() {
        try {
            state.ocr.status = await requestJson(`${API_OCR}/autodetectar`, {
                method: 'POST',
                body: '{}'
            });
            state.ocr.carregado = true;
            renderOcr();
            mostrarOcrMensagem(state.ocr.status.mensagem || 'Autodeteccao OCR concluida.', state.ocr.status.pronto_para_imagens ? 'success' : 'error');
        } catch (error) {
            mostrarOcrMensagem(error.message, 'error');
        }
    }

    async function salvarFerramentasOcr() {
        const payload = {
            tesseract_path: obterCampo('ocr-tesseract-path').trim(),
            poppler_path: obterCampo('ocr-poppler-path').trim()
        };
        try {
            state.ocr.status = await requestJson(`${API_OCR}/configurar`, {
                method: 'POST',
                body: JSON.stringify(payload)
            });
            state.ocr.carregado = true;
            renderOcr();
            mostrarOcrMensagem(state.ocr.status.message || 'Caminhos OCR salvos.', state.ocr.status.pronto_para_imagens ? 'success' : 'error');
        } catch (error) {
            mostrarOcrMensagem(error.message, 'error');
        }
    }

    function exportarConfiguracoes() {
        window.location.href = `${API_BACKUP}/configuracoes/exportar`;
    }

    function abrirImportacaoConfiguracoes() {
        $('backup-import-file')?.click();
    }

    async function importarConfiguracoes(event) {
        const arquivo = event.target.files?.[0];
        if (!arquivo) return;
        try {
            const texto = await arquivo.text();
            const payload = JSON.parse(texto);
            const resposta = await requestJson(`${API_BACKUP}/configuracoes/importar`, {
                method: 'POST',
                body: JSON.stringify(payload)
            });
            mostrarBackupMensagem(resposta.message || 'Arquivo validado.', 'success');
        } catch (error) {
            mostrarBackupMensagem(error.message || 'Arquivo inválido.');
        } finally {
            event.target.value = '';
        }
    }

    async function restaurarBackup() {
        const arquivo = obterCampo('backup-restore-file');
        const confirmacao = obterCampo('backup-restore-confirmation').trim();
        if (!arquivo) {
            mostrarBackupMensagem('Selecione um backup para restaurar.');
            return;
        }
        if (confirmacao !== 'CONFIRMO RESTAURACAO') {
            mostrarBackupMensagem('Digite CONFIRMO RESTAURACAO para liberar a restauração.');
            return;
        }
        const autorizado = window.confirm('Esta ação substituirá os dados atuais do banco. Confirma a restauração?');
        if (!autorizado) return;

        try {
            const resposta = await requestJson(`${API_BACKUP}/restaurar`, {
                method: 'POST',
                body: JSON.stringify({ arquivo, confirmacao })
            });
            mostrarBackupMensagem(resposta.message || 'Restauração concluída.', 'success');
        } catch (error) {
            mostrarBackupMensagem(error.message, 'error');
        }
    }

    async function testarRestauracaoBackup() {
        const arquivo = obterCampo('backup-test-restore-file');
        const confirmacao = obterCampo('backup-test-restore-confirmation').trim();
        const manterBanco = obterCheckbox('backup-test-restore-keep');
        const botao = $('backup-test-restore-start');
        renderBackupTesteResultado(null);
        if (!arquivo) {
            mostrarBackupMensagem('Selecione um backup para testar.');
            return;
        }
        if (confirmacao !== 'TESTAR RESTAURACAO') {
            mostrarBackupMensagem('Digite TESTAR RESTAURACAO para liberar o teste de restauracao.');
            return;
        }

        mostrarBackupMensagem('Executando teste de restauracao em banco descartavel...', 'info');
        if (botao) {
            botao.disabled = true;
            botao.textContent = 'Testando...';
        }
        try {
            const resposta = await requestJson(`${API_BACKUP}/testar-restauracao`, {
                method: 'POST',
                body: JSON.stringify({
                    arquivo,
                    confirmacao,
                    manter_banco: manterBanco
                })
            });
            renderBackupTesteResultado(resposta.data);
            mostrarBackupMensagem(resposta.message || 'Teste de restauracao concluido.', 'success');
            await carregarBackup();
        } catch (error) {
            const data = error.data || null;
            if (data) renderBackupTesteResultado(data);
            mostrarBackupMensagem(error.message, 'error');
            await carregarBackup();
        } finally {
            if (botao) {
                botao.disabled = false;
                botao.textContent = 'Testar restauracao';
            }
        }
    }

    async function carregarPerfis() {
        const data = await requestJson(`${API_PERFIS}/config`);
        state.perfis = data.perfis || [];
        state.ativo = data.perfil_ativo || null;
        if (!state.selecionado || !state.perfis.some((perfil) => Number(perfil.id) === Number(state.selecionado.id))) {
            state.selecionado = state.perfis.find((perfil) => Number(perfil.id) === Number(state.ativo?.id)) || state.perfis[0] || null;
        } else {
            state.selecionado = state.perfis.find((perfil) => Number(perfil.id) === Number(state.selecionado.id));
        }
        renderPerfis();
        preencherFormularioPerfil(state.selecionado);
    }

    async function carregarPreferencias() {
        const data = await requestJson(API_PREFERENCIAS);
        state.preferencias = data.data || {};
        preencherPreferencias(state.preferencias);
    }

    function renderPerfis() {
        const destino = $('config-profiles-list');
        if (!destino) return;
        if (!state.perfis.length) {
            destino.innerHTML = '<div class="config-empty-state">Nenhum perfil financeiro cadastrado. Crie um perfil para começar a organizar seus dados por contexto.</div>';
            return;
        }

        const cards = state.perfis.map((perfil) => {
            const selecionado = Number(state.selecionado?.id) === Number(perfil.id);
            const emUso = Number(state.ativo?.id) === Number(perfil.id);
            const statusClasse = perfil.ativo ? (emUso ? 'active' : 'available') : 'inactive';
            const statusLabel = perfil.ativo ? (emUso ? 'Ativo' : 'Disponível') : 'Inativo';
            return `
                <button type="button" class="config-profile-card${selecionado ? ' active' : ''}" data-profile-id="${escapeHtml(perfil.id)}">
                    <span class="config-profile-avatar" style="--profile-color:${escapeHtml(perfil.cor || '#2563eb')}">${escapeHtml(iniciais(perfil))}</span>
                    <span class="config-profile-main">
                        <strong>${escapeHtml(perfil.nome)}</strong>
                        <small>${escapeHtml(tipoLabel(perfil.tipo))}${perfil.documento ? ` · ${escapeHtml(perfil.documento)}` : ''}</small>
                        <span class="config-profile-badges">
                            <span class="config-profile-badge ${statusClasse}">${statusLabel}</span>
                            ${perfil.padrao ? '<span class="config-profile-badge default">Padrão</span>' : ''}
                            ${emUso ? '<span class="config-profile-badge current">Perfil em uso</span>' : ''}
                        </span>
                    </span>
                    <span aria-hidden="true">›</span>
                </button>
            `;
        });

        cards.push(`
            <button type="button" class="config-profile-new-card" id="config-profile-card-new">
                <span class="config-profile-plus" aria-hidden="true">+</span>
                <span class="config-profile-main">
                    <strong>Novo perfil</strong>
                    <small>Crie um novo perfil financeiro</small>
                </span>
            </button>
        `);
        destino.innerHTML = cards.join('');
    }

    function preencherFormularioPerfil(perfil) {
        $('config-profile-id').value = perfil?.id || '';
        $('config-profile-nome').value = perfil?.nome || '';
        $('config-profile-tipo').value = perfil?.tipo || 'PESSOAL';
        $('config-profile-avatar').value = perfil?.avatar || '';
        $('config-profile-documento').value = perfil?.documento || '';
        $('config-profile-cor').value = perfil?.cor || '#2563eb';
        $('config-profile-ativo').checked = perfil ? Boolean(perfil.ativo) : true;
        $('config-profile-padrao').checked = perfil ? Boolean(perfil.padrao) : false;
        atualizarChecksConceituais();
    }

    function novoPerfil() {
        state.selecionado = null;
        renderPerfis();
        preencherFormularioPerfil(null);
        mostrarMensagem('Novo perfil em edição. Preencha os dados e salve para criar.', 'info');
        $('config-profile-nome')?.focus();
    }

    function payloadPerfilBase() {
        return {
            nome: $('config-profile-nome').value.trim(),
            tipo: $('config-profile-tipo').value,
            documento: $('config-profile-documento').value.trim(),
            cor: $('config-profile-cor').value || '#2563eb',
            avatar: $('config-profile-avatar').value.trim()
        };
    }

    async function salvarPerfil() {
        mostrarMensagem('');
        const id = $('config-profile-id').value;
        const desejaAtivo = $('config-profile-ativo').checked;
        const desejaPadrao = $('config-profile-padrao').checked;
        const perfilAntes = id ? state.perfis.find((perfil) => Number(perfil.id) === Number(id)) : null;

        try {
            let perfilSalvo;
            if (id) {
                const payload = payloadPerfilBase();
                const resposta = await requestJson(`${API_PERFIS}/${id}`, {
                    method: 'PUT',
                    body: JSON.stringify(payload)
                });
                perfilSalvo = resposta.perfil;

                if (perfilAntes?.ativo && !desejaAtivo) {
                    await requestJson(`${API_PERFIS}/${id}/inativar`, { method: 'POST' });
                } else if (!perfilAntes?.ativo && desejaAtivo) {
                    await requestJson(`${API_PERFIS}/${id}/reativar`, { method: 'POST' });
                }
            } else {
                const resposta = await requestJson(API_PERFIS, {
                    method: 'POST',
                    body: JSON.stringify({ ...payloadPerfilBase(), ativo: desejaAtivo, padrao: desejaPadrao })
                });
                perfilSalvo = resposta.perfil;
            }

            if (desejaPadrao && desejaAtivo && perfilSalvo?.id) {
                await requestJson(`${API_PERFIS}/${perfilSalvo.id}/padrao`, { method: 'POST' });
            }

            state.selecionado = perfilSalvo;
            await carregarPerfis();
            atualizarTopbar();
            mostrarMensagem('Configurações do perfil salvas.', 'success');
        } catch (error) {
            mostrarMensagem(error.message);
        }
    }

    async function definirPerfilAtivo(perfil) {
        if (!perfil || !perfil.ativo) return;
        try {
            await requestJson(`${API_PERFIS}/ativo`, {
                method: 'POST',
                body: JSON.stringify({ perfil_id: perfil.id })
            });
            state.ativo = perfil;
            state.selecionado = perfil;
            await carregarPerfis();
            atualizarTopbar();
            mostrarMensagem(`Perfil em uso alterado para ${perfil.nome}.`, 'success');
        } catch (error) {
            mostrarMensagem(error.message);
        }
    }

    function atualizarTopbar() {
        if (window.ContextoFinanceiroUI?.init) {
            window.ContextoFinanceiroUI.init();
        }
    }

    function atualizarChecksConceituais() {
        const tipo = String($('config-profile-tipo')?.value || '').toUpperCase();
        const ativo = $('config-profile-ativo')?.checked;
        const irpf = $('config-profile-irpf');
        const docs = $('config-profile-docs');
        const topbar = $('config-profile-topbar');
        const switcher = $('config-profile-switch');
        if (irpf) irpf.checked = tipo !== 'EMPRESA';
        if (docs) docs.checked = tipo === 'EMPRESA';
        if (topbar) topbar.checked = Boolean(ativo);
        if (switcher) switcher.checked = Boolean(ativo);
    }

    function preencherPreferencias(prefs) {
        setCampo('nome_usuario', prefs.nome_usuario);
        setCampo('renda_principal', prefs.renda_principal);
        setCampo('mes_inicio_planejamento', prefs.mes_inicio_planejamento || 1);
        setCampo('dia_fechamento_mes', prefs.dia_fechamento_mes || 1);
        setCheckbox('ajustar_competencia_automatico', prefs.ajustar_competencia_automatico);
        setCheckbox('exibir_aviso_despesa_vencida', prefs.exibir_aviso_despesa_vencida);
        setCheckbox('solicitar_confirmacao_exclusao', prefs.solicitar_confirmacao_exclusao);
        setCheckbox('vincular_pagamento_cartao_auto', prefs.vincular_pagamento_cartao_auto);
        setRadio('tema_sistema', prefs.tema_sistema || 'claro');
        setCampo('cor_principal', prefs.cor_principal || '#3b82f6');
        const preview = $('cor_preview');
        if (preview) preview.textContent = prefs.cor_principal || '#3b82f6';
        setCheckbox('mostrar_icones_coloridos', prefs.mostrar_icones_coloridos);
        setCheckbox('abreviar_valores', prefs.abreviar_valores);
        setCheckbox('modo_inteligente_ativo', prefs.modo_inteligente_ativo);
        setCheckbox('sugestoes_economia', prefs.sugestoes_economia);
        setCheckbox('classificacao_automatica', prefs.classificacao_automatica);
        setCheckbox('correcao_categorias', prefs.correcao_categorias);
    }

    async function salvarPreferencias(escopo) {
        const dados = {};
        if (escopo === 'gerais') {
            dados.nome_usuario = obterCampo('nome_usuario');
            dados.renda_principal = parseFloat(obterCampo('renda_principal')) || 0;
            dados.mes_inicio_planejamento = parseInt(obterCampo('mes_inicio_planejamento'), 10) || 1;
            dados.dia_fechamento_mes = parseInt(obterCampo('dia_fechamento_mes'), 10) || 1;
        }
        if (escopo === 'aparencia') {
            dados.tema_sistema = obterRadio('tema_sistema') || 'claro';
            dados.cor_principal = obterCampo('cor_principal') || '#3b82f6';
            dados.mostrar_icones_coloridos = obterCheckbox('mostrar_icones_coloridos');
            dados.abreviar_valores = obterCheckbox('abreviar_valores');
        }
        if (escopo === 'comportamento') {
            dados.ajustar_competencia_automatico = obterCheckbox('ajustar_competencia_automatico');
            dados.exibir_aviso_despesa_vencida = obterCheckbox('exibir_aviso_despesa_vencida');
            dados.solicitar_confirmacao_exclusao = obterCheckbox('solicitar_confirmacao_exclusao');
            dados.vincular_pagamento_cartao_auto = obterCheckbox('vincular_pagamento_cartao_auto');
        }
        if (escopo === 'ia') {
            dados.modo_inteligente_ativo = obterCheckbox('modo_inteligente_ativo');
            dados.sugestoes_economia = obterCheckbox('sugestoes_economia');
            dados.classificacao_automatica = obterCheckbox('classificacao_automatica');
            dados.correcao_categorias = obterCheckbox('correcao_categorias');
        }

        try {
            await requestJson(API_PREFERENCIAS, {
                method: 'PUT',
                body: JSON.stringify(dados)
            });
            await carregarPreferencias();
            mostrarMensagem('Preferências salvas.', 'success');
        } catch (error) {
            mostrarMensagem(error.message);
        }
    }

    function trocarSecao(secao) {
        state.secao = secao || 'perfis-financeiros';
        document.querySelectorAll('[data-config-section]').forEach((panel) => {
            panel.classList.toggle('active', panel.dataset.configSection === state.secao);
        });
        document.querySelectorAll('[data-config-section-target]').forEach((link) => {
            link.classList.toggle('active', link.dataset.configSectionTarget === state.secao);
        });
        renderAjuda();
        if (state.secao === 'backup') {
            if (!state.backup.carregado) {
                carregarBackup();
            } else {
                renderBackupPainel();
            }
        }
        if (state.secao === 'ia-automacao' && !state.ocr.carregado) {
            carregarOcr();
        }
        if (window.location.hash !== `#${state.secao}`) {
            history.replaceState(null, '', `#${state.secao}`);
        }
    }

    function renderAjuda() {
        const data = ajuda[state.secao] || ajuda['perfis-financeiros'];
        const title = $('config-help-title');
        const content = $('config-help-content');
        if (title) title.textContent = data.titulo;
        if (!content) return;
        content.innerHTML = `
            <div class="config-help-list">
                ${data.itens.map((item, index) => `
                    <div class="config-help-item">
                        <span class="config-help-marker" aria-hidden="true">${index + 1}</span>
                        <span>
                            <strong>${escapeHtml(item[0])}</strong>
                            <span>${escapeHtml(item[1])}</span>
                        </span>
                    </div>
                `).join('')}
            </div>
        `;
    }

    function setCampo(id, valor) {
        const campo = $(id);
        if (campo && valor !== null && valor !== undefined) campo.value = valor;
    }

    function setCheckbox(id, valor) {
        const campo = $(id);
        if (campo) campo.checked = Boolean(valor);
    }

    function setRadio(name, valor) {
        const campo = document.querySelector(`input[name="${name}"][value="${valor}"]`);
        if (campo) campo.checked = true;
    }

    function obterCampo(id) {
        return $(id)?.value || '';
    }

    function obterCheckbox(id) {
        return Boolean($(id)?.checked);
    }

    function obterRadio(name) {
        return document.querySelector(`input[name="${name}"]:checked`)?.value || '';
    }

    function bind() {
        document.querySelectorAll('[data-config-section-target]').forEach((button) => {
            button.addEventListener('click', () => trocarSecao(button.dataset.configSectionTarget));
        });

        document.querySelectorAll('[data-config-placeholder]').forEach((button) => {
            const texto = String(button.dataset.configPlaceholder || '');
            if (texto.includes('Exportar')) {
                button.removeAttribute('data-config-placeholder');
                button.addEventListener('click', exportarConfiguracoes);
            }
            if (texto.includes('Importar')) {
                button.removeAttribute('data-config-placeholder');
                button.addEventListener('click', abrirImportacaoConfiguracoes);
            }
        });

        document.querySelectorAll('[data-config-placeholder]').forEach((button) => {
            button.addEventListener('click', () => mostrarMensagem(`${button.dataset.configPlaceholder} será disponibilizado em etapa futura.`, 'info'));
        });

        $('backup-export-config')?.addEventListener('click', exportarConfiguracoes);
        $('backup-import-config')?.addEventListener('click', abrirImportacaoConfiguracoes);
        $('backup-import-file')?.addEventListener('change', importarConfiguracoes);
        $('backup-run')?.addEventListener('click', executarBackup);
        $('backup-tools-autodetect')?.addEventListener('click', autodetectarFerramentasBackup);
        $('backup-tools-validate')?.addEventListener('click', validarFerramentasBackup);
        $('backup-tools-save')?.addEventListener('click', salvarFerramentasBackup);
        $('ocr-tools-autodetect')?.addEventListener('click', autodetectarFerramentasOcr);
        $('ocr-tools-validate')?.addEventListener('click', validarFerramentasOcr);
        $('ocr-tools-save')?.addEventListener('click', salvarFerramentasOcr);
        $('backup-schedule-save')?.addEventListener('click', salvarAgendamentoBackup);
        $('backup-restore-start')?.addEventListener('click', restaurarBackup);
        $('backup-test-restore-start')?.addEventListener('click', testarRestauracaoBackup);
        $('backup-history-body')?.addEventListener('click', (event) => {
            const botao = event.target.closest('[data-backup-download]');
            if (!botao) return;
            window.location.href = `${API_BACKUP}/download/${encodeURIComponent(botao.dataset.backupDownload)}`;
        });

        $('config-profiles-list')?.addEventListener('click', (event) => {
            const newCard = event.target.closest('#config-profile-card-new');
            if (newCard) {
                novoPerfil();
                return;
            }
            const card = event.target.closest('[data-profile-id]');
            if (!card) return;
            const perfil = state.perfis.find((item) => Number(item.id) === Number(card.dataset.profileId));
            state.selecionado = perfil;
            renderPerfis();
            preencherFormularioPerfil(perfil);
            mostrarMensagem('');
        });

        $('config-profile-new')?.addEventListener('click', novoPerfil);
        $('config-profile-cancel')?.addEventListener('click', () => {
            state.selecionado = state.perfis.find((perfil) => Number(perfil.id) === Number(state.ativo?.id)) || state.perfis[0] || null;
            renderPerfis();
            preencherFormularioPerfil(state.selecionado);
            mostrarMensagem('');
        });
        $('config-profile-save')?.addEventListener('click', salvarPerfil);
        $('config-profile-use')?.addEventListener('click', () => definirPerfilAtivo(state.selecionado));
        $('config-profile-manage')?.addEventListener('click', () => mostrarMensagem('Use os cards e o formulário para gerenciar perfis nesta central.', 'info'));
        $('config-profile-tipo')?.addEventListener('change', atualizarChecksConceituais);
        $('config-profile-ativo')?.addEventListener('change', atualizarChecksConceituais);
        $('config-preferences-save')?.addEventListener('click', () => salvarPreferencias('gerais'));

        document.querySelectorAll('[data-preferences-save]').forEach((button) => {
            button.addEventListener('click', () => salvarPreferencias(button.dataset.preferencesSave));
        });

        $('cor_principal')?.addEventListener('input', (event) => {
            const preview = $('cor_preview');
            if (preview) preview.textContent = event.target.value;
        });
    }

    async function init() {
        if (!document.querySelector('[data-config-page]')) return;
        bind();
        const secaoInicial = window.location.hash ? window.location.hash.slice(1) : 'perfis-financeiros';
        trocarSecao(document.querySelector(`[data-config-section="${secaoInicial}"]`) ? secaoInicial : 'perfis-financeiros');
        try {
            await Promise.all([carregarPerfis(), carregarPreferencias()]);
        } catch (error) {
            mostrarMensagem(error.message);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
}());
