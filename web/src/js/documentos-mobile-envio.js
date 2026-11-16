// FIN-REG-08 — inclusao de documento pelo celular (Documentos mobile), em etapas no painel inferior:
//   1. Fotografar (camera do aparelho, pelo seletor de arquivos do navegador) ou Selecionar arquivo;
//   2. Pre-visualizacao: imagem ou PDF, nome, formato, tamanho e o tratamento aplicado (HEIC convertido, foto reduzida para o
//      limite de 10 MB); Cancelar, Substituir ou Continuar. Nada e enviado so por abrir a camera;
//   3. Leitura no aparelho (texto do PDF ou OCR), com andamento e Cancelar;
//   4. Conferencia: os campos reconhecidos, cada um dizendo se foi identificado, se precisa de conferencia ou se nao foi
//      reconhecido; valor ambiguo vira opcoes; categoria sugerida (ou nenhuma); tudo editavel;
//   5. Confirmar e enviar: arquivo, texto lido e dados conferidos numa so gravacao (enviar_comprovante). O documento fica
//      pendente: validar continua sendo do usuario. Nenhuma despesa, compra ou pagamento e criado.
// Falha na leitura nao impede o envio (os campos ficam para preencher). Sem innerHTML (CSP).

import { el } from './comum.js';
import { enviarConferido, novoLeitor, responderDocumentos, sugestoesDoTexto } from './documentos-servico.js';
import { SITUACOES, TIPOS } from './leitura-fiscal.js';
import { miniaturaDaImagem, prepararArquivo, tamanhoLegivel, tipoDoArquivo } from './leitura-ocr.js';
import { moeda } from './mobile-formulario.js';
import { abrirFolha, botao, campo, entrada, fecharFolha, folhaAberta, mensagem, mostrarAviso, mostrarMensagem, quandoFechar, seletor, texto } from './mobile-ui.js';

const ORIGENS = { TEXTO_PDF: 'texto do PDF', OCR_IMAGEM: 'reconhecimento da imagem (OCR)', OCR_PDF: 'reconhecimento do PDF (OCR)' };
const FORMATOS = { 'application/pdf': 'PDF', 'image/jpeg': 'JPEG', 'image/png': 'PNG', 'image/webp': 'WebP' };

// opcoes: { perfil, ano: () => 'AAAA', aoEnviado(comprovanteId) }
export function criarEnvio(opcoes) {
    const fotografar = document.getElementById('mob-foto');
    const selecionar = document.getElementById('mob-arquivo');
    let estado = null;  // { preparado, imagem (data: URL da miniatura), leitor, leitura, categoria }
    let categorias = null;

    function limpar() {
        if (estado?.leitor) estado.leitor.cancelar();
        estado = null;
    }

    function acoes(...botoes) {
        const caixa = el('div', 'mob-acoes');
        caixa.append(...botoes);
        return caixa;
    }

    function botaoCom(id, rotulo, classe, aoClicar) {
        const b = botao(rotulo, classe);
        b.id = id;
        b.addEventListener('click', aoClicar);
        return b;
    }

    // ---- 1. escolha
    function abrir() {
        limpar();
        abrirFolha('Incluir documento',
            texto('Fotografe o comprovante ou escolha um arquivo (PDF, JPEG, PNG ou WebP, até 10 MB). Antes de enviar você confere os dados lidos.', 'discreto'),
            acoes(botaoCom('mob-envio-fotografar', 'Fotografar', '', () => fotografar.click()),
                  botaoCom('mob-envio-selecionar', 'Selecionar arquivo', 'primario', () => selecionar.click())));
        quandoFechar(limpar);
    }

    async function recebido(entradaArquivo) {
        const arquivo = entradaArquivo.files && entradaArquivo.files[0];
        entradaArquivo.value = '';  // a mesma foto pode ser escolhida de novo
        if (!arquivo) return;
        limpar();
        abrirFolha('Incluir documento', texto('Preparando o arquivo…', 'discreto'));
        quandoFechar(limpar);
        const preparado = await prepararArquivo(arquivo).catch(() => ({ arquivo, original: arquivo, tratamentos: [], erro: 'Não foi possível abrir este arquivo.' }));
        const imagem = !preparado.erro && tipoDoArquivo(preparado.arquivo) === 'imagem' ? await miniaturaDaImagem(preparado.arquivo) : null;
        if (!folhaAberta()) return;  // o painel foi fechado durante o preparo
        estado = { preparado, imagem, leitor: null, leitura: null, categoria: null };
        previa();
    }

    // ---- 2. pre-visualizacao
    function miniatura(pequena = false) {
        const { arquivo } = estado.preparado;
        const caixa = el('div', `mob-envio-previa${pequena ? ' pequena' : ''}`);
        caixa.id = pequena ? 'mob-envio-miniatura' : 'mob-envio-previa';
        if (estado.imagem) {
            const img = el('img');
            img.src = estado.imagem;
            img.alt = 'Pré-visualização do documento';
            caixa.append(img);
        } else {
            caixa.append(el('span', 'mob-envio-tipo', tipoDoArquivo(arquivo) === 'pdf' ? 'PDF' : 'IMG'));
        }
        const dados = el('span', 'mob-envio-dados');
        dados.append(el('strong', null, arquivo.name), el('span', null, `${FORMATOS[arquivo.type] || 'Arquivo'} · ${tamanhoLegivel(arquivo.size)}`));
        caixa.append(dados);
        return caixa;
    }

    function previa() {
        const { preparado } = estado;
        const m = mensagem();
        const partes = [];
        if (preparado.erro) {
            mostrarMensagem(m, preparado.erro, 'erro');
            partes.push(m, acoes(botaoCom('mob-envio-cancelar', 'Cancelar', '', fecharFolha), botaoCom('mob-envio-substituir', 'Escolher outro', 'primario', abrir)));
            abrirFolha('Incluir documento', ...partes);
            quandoFechar(limpar);
            return;
        }
        partes.push(miniatura(), ...preparado.tratamentos.map((t) => texto(t, 'discreto')));
        partes.push(acoes(botaoCom('mob-envio-cancelar', 'Cancelar', '', fecharFolha), botaoCom('mob-envio-substituir', 'Substituir', '', abrir),
                          botaoCom('mob-envio-continuar', 'Continuar', 'primario', ler)));
        abrirFolha('Incluir documento', ...partes);
        quandoFechar(limpar);
    }

    // ---- 3. leitura no aparelho
    async function ler() {
        const andamento = texto('Lendo o documento…', 'discreto');
        andamento.id = 'mob-envio-andamento';
        andamento.setAttribute('role', 'status');
        const cancelar = botaoCom('mob-envio-cancelar-leitura', 'Cancelar leitura', '', () => estado?.leitor?.cancelar());
        abrirFolha('Lendo o documento', miniatura(true), andamento, acoes(cancelar));
        quandoFechar(limpar);
        estado.leitor = novoLeitor((t) => { andamento.textContent = t; });
        let lido = null;
        let falhou = null;
        try {
            lido = await estado.leitor.ler(estado.preparado.arquivo);
        } catch (erro) {
            if (erro && erro.cancelada) {
                if (!estado) return;  // cancelado porque o painel foi fechado
                estado.leitor = null;
                previa();
                return;
            }
            falhou = erro && erro.message ? erro.message : 'A leitura não foi concluída.';
        }
        if (!estado) return;  // o painel foi fechado durante a leitura
        estado.leitor = null;
        const resultado = await sugestoesDoTexto(lido ? lido.texto : '', lido ? lido.origem : 'OCR_IMAGEM');
        estado.leitura = lido ? resultado.leitura : null;
        estado.categoria = resultado.categoria;
        if (falhou) estado.falha = `${falhou} Preencha os dados manualmente.`;
        await conferencia();
    }

    // ---- 4. conferencia
    async function listaDeCategorias() {
        if (!categorias) {
            const r = await responderDocumentos({ metodo: 'GET', caminho: '/api/ir/categorias-despesa-disponiveis', parametros: new URLSearchParams(), corpo: null });
            categorias = r.corpo && r.corpo.success ? r.corpo.data || [] : [];
        }
        return categorias;
    }

    function situacao(campoDoForm, s) {
        const n = el('small', `mob-envio-situacao ${s || 'nao_reconhecido'}`, SITUACOES[s || 'nao_reconhecido']);
        campoDoForm.append(n);
        return n;
    }

    async function conferencia() {
        const leitura = estado.leitura;
        const vazio = { valor: null, situacao: 'nao_reconhecido' };
        const c = (chave) => (leitura ? leitura.campos[chave] : vazio);
        const lista = await listaDeCategorias();
        if (!estado) return;
        const empresa = opcoes.perfil.tipo === 'EMPRESA';
        const data = entrada('date', c('data_documento').valor || '');
        const prestador = entrada('text', c('prestador_nome').valor || '', { maxlength: '255', autocomplete: 'off' });
        const documento = entrada('text', c('prestador_cpf_cnpj').valor || '', { maxlength: '20', autocomplete: 'off', inputmode: 'numeric' });
        const valor = entrada('number', c('valor').valor || '', { step: '0.01', min: '0', inputmode: 'decimal', placeholder: '0,00' });
        const ano = entrada('number', (c('data_documento').valor || '').slice(0, 4) || opcoes.ano(), { step: '1', min: '2000', max: '2100', inputmode: 'numeric' });
        const categoria = seletor([['', 'Sem categoria'], ...lista.map((x) => [x.id, x.nome])], estado.categoria && estado.categoria.categoria_id ? estado.categoria.categoria_id : '');
        const observacoes = el('textarea');
        observacoes.rows = 2;
        observacoes.maxLength = 1000;
        for (const [controle, id] of [[data, 'mob-envio-data'], [prestador, 'mob-envio-prestador'], [documento, 'mob-envio-documento'], [valor, 'mob-envio-valor'],
            [ano, 'mob-envio-ano'], [categoria, 'mob-envio-categoria'], [observacoes, 'mob-envio-observacoes']]) controle.id = id;
        data.addEventListener('change', () => { if (/^\d{4}-/.test(data.value)) ano.value = data.value.slice(0, 4); });
        const cData = campo('Data do documento', data);
        const cPrestador = campo(empresa ? 'Fornecedor / emissor' : 'Prestador', prestador);
        const cDocumento = campo('CPF/CNPJ', documento);
        const cValor = campo('Valor', valor);
        const cCategoria = campo(empresa ? 'Categoria (define a categoria fiscal)' : 'Categoria (define a Categoria IR)', categoria);
        situacao(cData, c('data_documento').situacao);
        situacao(cPrestador, c('prestador_nome').situacao);
        situacao(cDocumento, c('prestador_cpf_cnpj').situacao);
        situacao(cValor, c('valor').situacao);
        if (leitura && leitura.valoresCandidatos.length) {
            // Valor ambiguo: nenhuma opcao e aplicada sozinha.
            const escolha = el('span', 'mob-envio-opcoes');
            escolha.id = 'mob-envio-opcoes';
            escolha.append(el('span', null, 'Valores encontrados:'));
            for (const v of leitura.valoresCandidatos) {
                const b = botao(moeda(v), 'mob-envio-opcao');
                b.dataset.valor = v;
                b.addEventListener('click', () => { valor.value = v; });
                escolha.append(b);
            }
            cValor.append(escolha);
        }
        const notaCategoria = el('small', 'mob-envio-situacao', estado.categoria ? estado.categoria.aviso : 'Sem sugestão segura de categoria.');
        notaCategoria.id = 'mob-envio-categoria-nota';
        cCategoria.append(notaCategoria);
        const form = el('form', 'mob-form mob-envio-form');
        form.noValidate = true;
        const m = mensagem();
        const resumo = el('p', 'mob-envio-resumo');
        resumo.id = 'mob-envio-resumo';
        resumo.textContent = leitura
            ? `${TIPOS[leitura.tipo] || 'Documento'} · lido por ${ORIGENS[leitura.origem]}. Confira antes de enviar.`
            : (estado.falha || 'Não foi possível ler o documento. Preencha os dados.');
        const avisos = leitura ? leitura.avisos.map((a) => texto(a, 'discreto mob-envio-aviso')) : [];
        const enviar = botao('Confirmar e enviar', 'primario');
        enviar.type = 'submit';
        enviar.id = 'mob-envio-confirmar';
        form.append(miniatura(true), resumo, ...avisos, cData, cPrestador, cDocumento, cValor, campo('Ano-calendário', ano), cCategoria,
            campo('Observações', observacoes), m,
            acoes(botaoCom('mob-envio-cancelar', 'Cancelar', '', fecharFolha), botaoCom('mob-envio-substituir', 'Substituir', '', abrir), enviar));
        form.addEventListener('submit', async (evento) => {
            evento.preventDefault();
            if (enviar.disabled) return;
            if (valor.value && !(Number(valor.value) > 0)) { mostrarMensagem(m, 'Informe um valor maior que zero, ou deixe em branco.', 'erro'); return; }
            if (!/^\d{4}$/.test(String(ano.value))) { mostrarMensagem(m, 'Informe o ano-calendário.', 'erro'); return; }
            enviar.disabled = true;
            enviar.textContent = 'Enviando…';
            try {
                const revisao = { data_documento: data.value || null, prestador_nome: prestador.value, prestador_cpf_cnpj: documento.value,
                                  valor: valor.value || null, ano_calendario: ano.value, categoria_id: categoria.value || null };
                if (observacoes.value.trim()) revisao.observacoes = observacoes.value.trim();
                const r = await enviarConferido({ arquivo: estado.preparado.arquivo, ano: ano.value, leitura, revisao });
                concluido(r);
            } catch (erro) {
                const motivo = erro && erro.code === '42501' ? 'Esta conta não pode gravar documentos neste perfil. Nada foi gravado.'
                    : (erro && erro.message) || 'Não foi possível enviar. Nada foi gravado.';
                mostrarMensagem(m, motivo, 'erro');
                enviar.disabled = false;
                enviar.textContent = 'Confirmar e enviar';
            }
        });
        abrirFolha('Conferir documento', form);
        quandoFechar(limpar);
    }

    // ---- 5. resultado
    function concluido(r) {
        const id = r.comprovante_id;
        limpar();
        // A lista e recarregada ao sair do painel por qualquer caminho (Fechar, X ou fundo); "Abrir documento" abre o detalhe.
        let abrirDetalhe = false;
        const ver = botaoCom('mob-envio-abrir', 'Abrir documento', 'primario', () => { abrirDetalhe = true; fecharFolha(); });
        const fechar = botaoCom('mob-envio-fechar', 'Fechar', '', fecharFolha);
        abrirFolha(r.duplicado ? 'Documento já enviado' : 'Documento enviado',
            texto(r.duplicado ? 'Este arquivo já tinha sido enviado. O documento existente foi mantido, sem nenhuma alteração.'
                : 'Documento guardado com os dados conferidos. Ele fica pendente até você validar.'),
            acoes(fechar, ver));
        quandoFechar(() => { Promise.resolve(opcoes.aoEnviado(id, abrirDetalhe)).catch(() => {}); });
        mostrarAviso(r.duplicado ? 'Arquivo já enviado antes: nada foi alterado.' : 'Documento enviado.');
    }

    fotografar.addEventListener('change', () => recebido(fotografar));
    selecionar.addEventListener('change', () => recebido(selecionar));
    return { abrir };
}
