// FIN-FIDELIDADE-DOCUMENTOS-1 (fase 1) — adaptador da tela original de Imposto de Renda: responde as rotas /api/ir/...
// que js/original/imposto_renda.js chama (ponte-api.js), no formato do Flask. So consulta, modos IRPF e Documentos da
// Empresa (migrations 20261113090000 e 20261117090000): contexto, categorias IR, vinculos de categoria, comprovantes com
// resumo e detalhe, taxonomia, metadados e resumo empresariais e as saidas sem documento.
// FIN-DOCUMENTOS-2 (migration 20261128090000): envio de arquivo (guardado no banco, privado do perfil, com as validacoes
// do Flask e duplicidade por hash), revisao, validacao, vinculos e despesa/lancamento a partir do documento, com o
// escritor unico do perfil. O texto de PDF textual e extraido aqui (pdf.js, sem servico externo); sem ele, revisao
// manual. Ainda nao disponiveis nesta versao: OCR de imagem e categorias IR.
// FIN-REG-03: relatorios de Imposto de Renda / Documentos Fiscais e de Saidas sem documento (Excel e PDF), gerados no
// navegador (js/relatorio-fiscal.js) com as consultas ja publicadas; so leitura, sem migration.
// FIN-REG-04: pacote ZIP dos documentos da Empresa para o contador (js/zip-documentos.js), com indice e os arquivos
// originais conferidos pelo SHA-256 gravado; so leitura, sem migration, nada sai do navegador.
// FIN-MIGRACAO-LASTRO-EMPRESA-01 (migration 20261202090000): metadados empresariais (a revisao da tela original grava
// tipo, categoria, numero, orgao, datas, situacao...), saidas sem documento (vincular documento e situacao manual) e
// exclusao de documento pela lista (botao acrescentado; a tela original nao tinha), pelas funcoes do banco.
// FIN-PRE-PRODUCAO-1 (migration 20261130090000): entidades vinculaveis, vinculos ativos e resumo de lastro, e "Gerar
// financeiro" (sugestao + criacao, js/documento-financeiro.js, comum com Despesas e Lancamentos). Um documento pode ser
// vinculado a varios bens (regra do titular). Acrescimo ao Flask (que nao tinha "desvincular" na tela): o modal
// "Vincular documento" lista os vinculos ativos com "Desvincular" (o vinculo fica inativo, historico preservado).
// FIN-MOBILE-11: as regras (rotas, consultas, gravacoes, relatorios e pacote ZIP) sairam daqui SEM mudanca para
// js/documentos-servico.js, comum aos Documentos mobile; aqui ficam a moldura e o que e so da tela do desktop.

import { supabase } from './cliente.js';
import { falha } from './adaptador-comum.js';
import { instalarAberturaDeArquivos } from './arquivo-comprovante.js';
import { comprovanteCompleto, configurarDocumentos, filtrosDaLista, responderDocumentos, sugestoesDoTexto, vinculosAtivos } from './documentos-servico.js';
import { SITUACOES, TIPOS } from './leitura-fiscal.js';
import { iniciarMoldura } from './moldura.js';

let perfilId = null;

// Retorno do envio no painel "Arquivos importados" (acima da lista, que a tela original redesenha a cada envio).
function retornoDoEnvio(enviados, resultados) {
    const aviso = document.getElementById('cf-upload-retorno');
    if (!aviso) return;
    const falhas = resultados.filter((r) => !r.success);
    let texto;
    if (!falhas.length) {
        texto = enviados === 1 ? 'Documento enviado.' : `${enviados} documentos enviados.`;
    } else if (!enviados) {
        const motivos = [...new Set(falhas.map((r) => r.error))];
        texto = `Não foi possível enviar ${falhas.length === 1 ? 'o documento' : 'os documentos'}. `
            + (motivos.length === 1 ? motivos[0] : 'Veja o motivo de cada arquivo abaixo.');
    } else {
        texto = `${enviados} de ${resultados.length} documentos enviados. Os demais não foram enviados; veja o motivo abaixo.`;
    }
    aviso.textContent = texto;
    aviso.dataset.situacao = !falhas.length ? 'sucesso' : (enviados ? 'parcial' : 'erro');
    aviso.setAttribute('role', falhas.length ? 'alert' : 'status');
    aviso.hidden = false;
    // FIN-REG-08: o que a leitura automatica obteve, numa linha propria (o retorno do envio fica como era).
    const leitura = document.getElementById('cf-upload-leitura');
    if (leitura) {
        const lidos = resultados.filter((r) => r.success && r.data && r.data.comprovante && r.data.comprovante.texto_extraido && !r.data.duplicado);
        leitura.textContent = lidos.length
            ? `Texto lido automaticamente em ${lidos.length === 1 ? '1 documento' : `${lidos.length} documentos`}. Abra a revisão: os dados sugeridos aparecem lá para conferir.`
            : '';
        leitura.hidden = !lidos.length;
    }
}

// FIN-REG-08: andamento da leitura (texto do PDF ou OCR) durante o envio, no mesmo lugar do retorno.
function andamentoDaLeitura(texto) {
    const aviso = document.getElementById('cf-upload-retorno');
    if (!aviso) return;
    aviso.textContent = texto;
    aviso.dataset.situacao = 'lendo';
    aviso.setAttribute('role', 'status');
    aviso.hidden = false;
}

// A tela original marca o arquivo que falhou como "Erro de leitura"; aqui ele aparece como "Não enviado" (o motivo segue
// embaixo do nome). So o cartao de falha tem o selo como neto do cartao (no de documento gravado ele fica em
// .ir-upload-badges, e "Erro de leitura" ali e o status real do documento). Nova selecao esconde o retorno anterior.
function instalarRetornoDoEnvio() {
    const lista = document.getElementById('ir-upload-results');
    if (!lista) return;
    const aviso = document.createElement('p');
    aviso.id = 'cf-upload-retorno';
    aviso.className = 'cf-upload-retorno';
    aviso.hidden = true;
    lista.before(aviso);
    const leitura = document.createElement('p');  // FIN-REG-08
    leitura.id = 'cf-upload-leitura';
    leitura.className = 'cf-upload-leitura';
    leitura.hidden = true;
    aviso.after(leitura);
    new MutationObserver(() => {
        for (const selo of lista.querySelectorAll('.ir-upload-card > div > .ir-status.erro')) {
            if (selo.textContent !== 'Não enviado') selo.textContent = 'Não enviado';  // sem laco: so muda uma vez
        }
    }).observe(lista, { childList: true, subtree: true });
    const esconder = () => { aviso.hidden = true; };
    document.getElementById('ir-file-input')?.addEventListener('change', esconder);
    document.getElementById('ir-dropzone')?.addEventListener('drop', esconder);
}

// Acrescimo FIN-PRE-PRODUCAO-1: vinculos ativos com "Desvincular" no modal "Vincular documento" (a tela do Flask so
// criava). Desvincular passa pela mesma rota DELETE (ponte-api): o vinculo fica inativo e a lista e recarregada.
function instalarDesvinculo() {
    const modal = document.getElementById('ir-link-modal');
    const form = document.getElementById('ir-link-form');
    if (!modal || !form) return;
    const secao = document.createElement('section');
    secao.className = 'cf-vinculos-ativos';
    secao.setAttribute('aria-label', 'Vínculos ativos do documento');
    const titulo = document.createElement('h3');
    titulo.textContent = 'Vínculos ativos';
    const listaVinculos = document.createElement('ul');
    secao.append(titulo, listaVinculos);
    form.after(secao);

    async function desvincular(comprovante, vinculo) {
        if (!window.confirm('Desvincular este documento? O vínculo fica inativo e o histórico é preservado.')) return;
        const r = await (await fetch(`/api/ir/comprovantes/${comprovante}/vinculos/${vinculo}`, { method: 'DELETE' })).json();
        if (!r.success) {
            window.alert(r.error || 'Não foi possível desvincular o documento.');
            return;
        }
        await mostrar();
        document.getElementById('ir-btn-atualizar')?.click();
    }

    async function mostrar() {
        const comprovante = Number(document.getElementById('ir-link-comprovante-id')?.value);
        listaVinculos.replaceChildren();
        if (!comprovante) return;
        let vinculos = [];
        try {
            vinculos = await vinculosAtivos(comprovante);
        } catch (_erro) {
            vinculos = [];
        }
        if (!vinculos.length) {
            const vazio = document.createElement('li');
            vazio.className = 'cf-vinculos-vazio';
            vazio.textContent = 'Nenhum vínculo ativo.';
            listaVinculos.append(vazio);
            return;
        }
        for (const v of vinculos) {
            const item = document.createElement('li');
            const texto = document.createElement('span');
            texto.textContent = `${v.tipo_entidade}${v.resumo_entidade ? ` - ${v.resumo_entidade}` : ''} (${v.status_lastro})`;
            const botao = document.createElement('button');
            botao.type = 'button';
            botao.className = 'ir-secondary-btn cf-desvincular';
            botao.textContent = 'Desvincular';
            botao.addEventListener('click', () => desvincular(comprovante, v.id));
            item.append(texto, botao);
            listaVinculos.append(item);
        }
    }

    new MutationObserver(() => {
        if (modal.classList.contains('open')) mostrar();
    }).observe(modal, { attributes: true, attributeFilter: ['class'] });
}

// FIN-MIGRACAO-LASTRO-EMPRESA-01: "Excluir documento" nas acoes de cada linha da lista (a tela original nao tinha), so para
// quem gere o perfil. Usa a rota DELETE (excluir_comprovante confere perfil, escritor, vinculos e documento validado) e
// mostra o motivo da recusa; depois da exclusao a lista e os contadores sao recarregados pela propria tela.
const SVG = 'http://www.w3.org/2000/svg';

function iconeLixeira() {
    const svg = document.createElementNS(SVG, 'svg');
    const atributos = { viewBox: '0 0 24 24', 'aria-hidden': 'true', focusable: 'false', fill: 'none', stroke: 'currentColor',
                        'stroke-width': '1.8', 'stroke-linecap': 'round', 'stroke-linejoin': 'round', class: 'cf-icone-lixeira' };
    for (const [nome, valor] of Object.entries(atributos)) svg.setAttribute(nome, valor);
    for (const d of ['M4 7h16', 'M10 11v6M14 11v6', 'M6 7l1 13h10l1-13', 'M9 7V4h6v3']) {
        const caminho = document.createElementNS(SVG, 'path');
        caminho.setAttribute('d', d);
        svg.append(caminho);
    }
    return svg;
}

async function excluirDocumento(id, nome) {
    if (!window.confirm(`Excluir o documento "${nome}"?\nO arquivo e os dados dele saem do sistema. Esta ação não pode ser desfeita.`)) return false;
    const r = await (await fetch(`/api/ir/comprovantes/${id}`, { method: 'DELETE' })).json();
    if (!r.success) {
        window.alert(r.error || 'Não foi possível excluir o documento. Nada foi excluído.');
        return false;
    }
    await window.IRDoc?.carregarComprovantes?.();
    return true;
}

// Correcao autorizada (30/10/2026): "Excluir documento" tambem no rodape da revisao, onde o titular ja trabalha com o
// documento. Mesma rota e mesma confirmacao da lixeira da lista; fecha a revisao so quando a exclusao acontece.
function instalarExclusaoNaRevisao() {
    const rodape = document.querySelector('#ir-review-modal .ir-modal-footer');
    if (!rodape || rodape.querySelector('.cf-revisao-excluir')) return;
    const botao = document.createElement('button');
    botao.type = 'button';
    botao.id = 'cf-review-excluir';
    botao.className = 'ir-secondary-btn cf-revisao-excluir';
    const rotulo = document.createElement('span');
    rotulo.textContent = 'Excluir documento';
    botao.append(iconeLixeira(), rotulo);
    botao.addEventListener('click', async () => {
        const id = Number(document.getElementById('ir-review-id')?.value);
        if (!id) return;
        const nome = (document.getElementById('ir-review-file-name')?.textContent || `Documento #${id}`).trim();
        botao.disabled = true;
        try {
            if (await excluirDocumento(id, nome)) document.getElementById('ir-review-close')?.click();
        } finally {
            botao.disabled = false;
        }
    });
    rodape.prepend(botao);
}

async function instalarExclusao() {
    const corpo = document.getElementById('ir-comprovantes-tbody');
    if (!corpo) return;
    const { data: gere } = await supabase.rpc('pode_gerir_perfil', { p_perfil_id: perfilId });
    if (gere !== true) return;
    instalarExclusaoNaRevisao();

    function acrescentar() {
        for (const revisar of corpo.querySelectorAll('[data-on-click^="window.IRDoc.abrirRevisao("]')) {
            const acoes = revisar.parentElement;
            if (!acoes || acoes.querySelector('.cf-excluir-documento')) continue;  // sem laco: so acrescenta uma vez
            const id = Number(/abrirRevisao\((\d+)\)/.exec(revisar.getAttribute('data-on-click'))?.[1]);
            if (!id) continue;
            const nome = (revisar.closest('tr')?.querySelector('strong')?.textContent || `Documento #${id}`).trim();
            const botao = document.createElement('button');
            botao.type = 'button';
            botao.className = 'ir-icon-btn ir-icon-only cf-excluir-documento';
            botao.title = 'Excluir documento';
            botao.setAttribute('aria-label', 'Excluir documento');
            const rotulo = document.createElement('span');
            rotulo.className = 'sr-only';
            rotulo.textContent = 'Excluir documento';
            botao.append(iconeLixeira(), rotulo);
            botao.addEventListener('click', () => excluirDocumento(id, nome));
            acoes.append(botao);
        }
    }
    new MutationObserver(acrescentar).observe(corpo, { childList: true, subtree: true });
    acrescentar();
}

// FIN-REG-03: "Exportar", "Excel" e "PDF" do relatorio de Imposto de Renda. A tela original navega para a rota do servidor
// (window.location.href); aqui o clique gera o arquivo pela mesma rota (ponte-api) e o entrega como download, com os
// filtros da lista em tela (toda mudanca de filtro recarrega a lista). Os demais botoes ja usam fetch na tela original.
function nomeDoAnexo(resposta, padrao) {
    const m = /filename\*?=(?:UTF-8''|")?([^";]+)/i.exec(resposta.headers.get('Content-Disposition') || '');
    return m ? m[1].replace(/"/g, '') : padrao;
}

async function baixarRelatorioIr(tipo, botao) {
    const parametros = filtrosDaLista() || new URLSearchParams({ ano: String(new Date().getFullYear()) });
    const original = [...botao.childNodes];  // icone e rotulo do botao, repostos ao final
    botao.disabled = true;
    botao.replaceChildren(document.createTextNode('Gerando...'));
    try {
        const resposta = await fetch(`/api/ir/relatorios/${tipo}?${parametros.toString()}`);
        if (!resposta.ok) {
            const erro = await resposta.json().catch(() => ({}));
            throw new Error(erro.error || 'Não foi possível gerar o relatório.');
        }
        const url = URL.createObjectURL(await resposta.blob());
        const link = document.createElement('a');
        link.href = url;
        link.download = nomeDoAnexo(resposta, tipo === 'pdf' ? 'Relatorio_fiscal.pdf' : 'Relatorio_fiscal.xlsx');
        document.body.append(link);
        link.click();
        link.remove();
        window.setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (erro) {
        window.alert(erro.message || 'Não foi possível gerar o relatório.');
    } finally {
        botao.disabled = false;
        botao.replaceChildren(...original);
    }
}

function instalarRelatorioIr() {
    const BOTOES = { 'ir-btn-exportar': 'excel', 'ir-btn-excel': 'excel', 'ir-btn-pdf': 'pdf' };
    document.addEventListener('click', (evento) => {
        const botao = evento.target.closest && evento.target.closest('#ir-btn-exportar, #ir-btn-excel, #ir-btn-pdf');
        if (!botao) return;
        evento.preventDefault();
        evento.stopImmediatePropagation();  // a tela original navegaria para /api/ir/relatorios/...
        if (!botao.disabled) baixarRelatorioIr(BOTOES[botao.id], botao);
    }, true);
}

// FIN-REG-08: sugestoes da leitura automatica na revisao (tela original). Ao abrir a revisao, o texto guardado do documento
// e interpretado (NFS-e de Goiania, cupom fiscal ou generico) e a categoria e sugerida. Modelo reconhecido (NFS-e ou cupom):
// campo vazio recebe a sugestao, marcada para conferencia. Documento generico: nada e preenchido; cada sugestao aparece como
// nota com o botao "Usar" (quem abre a revisao so para outro ajuste nao grava um palpite sem ver). Campo ja preenchido (dado
// anterior ou correcao manual) NUNCA e trocado: a sugestao aparece so como nota. Valor ambiguo vira opcoes para escolher. Nada e gravado aqui: so o "Salvar revisao" grava, e "Validar" continua do
// usuario.
const CAMPOS_DA_REVISAO = [['data_documento', 'ir-review-data'], ['prestador_nome', 'ir-review-prestador'],
                           ['prestador_cpf_cnpj', 'ir-review-doc'], ['valor', 'ir-review-valor']];
const ORIGENS_DE_LEITURA = { TEXTO_PDF: 'texto do PDF', OCR_IMAGEM: 'OCR da imagem', OCR_PDF: 'OCR do PDF digitalizado' };
const reais = (v) => Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
const dataBr = (iso) => (/^\d{4}-\d{2}-\d{2}$/.test(iso || '') ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}` : iso);

function limparSugestoes(modal) {
    modal.querySelectorAll('.cf-leitura-nota, .cf-leitura-resumo, .cf-leitura-opcoes').forEach((e) => e.remove());
    modal.querySelectorAll('.cf-sugerido').forEach((e) => e.classList.remove('cf-sugerido'));
}

function nota(campo, texto, classe = 'cf-leitura-nota') {
    const n = document.createElement('small');
    n.className = classe;
    n.textContent = texto;
    campo.closest('label').append(n);
    return n;
}

// Sugestao que so entra no campo se o usuario tocar em "Usar".
function notaComUsar(campo, texto, aplicar) {
    const n = nota(campo, `${texto} `);
    const usar = document.createElement('button');
    usar.type = 'button';
    usar.className = 'cf-leitura-opcao cf-leitura-usar';
    usar.textContent = 'Usar';
    usar.addEventListener('click', () => { n.remove(); aplicar(); });
    n.append(usar);
    return n;
}

function marcarSugerido(campo) {
    campo.classList.add('cf-sugerido');
    const desmarcar = () => {
        campo.classList.remove('cf-sugerido');
        campo.closest('label')?.querySelector('.cf-leitura-nota')?.remove();
        campo.removeEventListener('input', desmarcar);
    };
    campo.addEventListener('input', desmarcar);
}

async function aplicarSugestoes(modal) {
    const id = Number(document.getElementById('ir-review-id')?.value);
    if (!id) return;
    let item;
    try {
        item = await comprovanteCompleto(id);
    } catch (_erro) {
        return;
    }
    if (!item || !item.texto_extraido || Number(document.getElementById('ir-review-id')?.value) !== id) return;
    const origem = ORIGENS_DE_LEITURA[item.origem_classificacao] ? item.origem_classificacao : 'TEXTO_PDF';
    const { leitura, categoria } = await sugestoesDoTexto(item.texto_extraido, origem);
    if (!modal.classList.contains('open') || Number(document.getElementById('ir-review-id')?.value) !== id) return;
    limparSugestoes(modal);
    const form = document.getElementById('ir-review-form');
    const resumo = document.createElement('p');
    resumo.className = 'cf-leitura-resumo';
    resumo.id = 'cf-leitura-resumo';
    const preencher = leitura.tipo === 'NFSE_GOIANIA' || leitura.tipo === 'CUPOM_FISCAL';
    const partes = [`Leitura automática (${ORIGENS_DE_LEITURA[origem]}): ${TIPOS[leitura.tipo] || 'Documento'}.`];
    partes.push(preencher ? 'Os campos marcados são sugestões: confira antes de salvar.'
        : 'Documento sem modelo reconhecido: nada foi preenchido. Use "Usar" nas sugestões que estiverem corretas.');
    if (leitura.avisos.length) partes.push(leitura.avisos.join(' '));
    resumo.textContent = partes.join(' ');
    form.before(resumo);
    for (const [chave, idCampo] of CAMPOS_DA_REVISAO) {
        const campo = document.getElementById(idCampo);
        const sugerido = leitura.campos[chave];
        if (!campo || !sugerido || sugerido.valor === null) continue;
        const exibido = chave === 'valor' ? reais(sugerido.valor) : chave === 'data_documento' ? dataBr(sugerido.valor) : sugerido.valor;
        if (!String(campo.value || '').trim() && preencher) {
            campo.value = sugerido.valor;
            marcarSugerido(campo);
            nota(campo, SITUACOES[sugerido.situacao]);
        } else if (!String(campo.value || '').trim()) {
            notaComUsar(campo, `A leitura sugere: ${exibido}.`, () => {
                campo.value = sugerido.valor;
                marcarSugerido(campo);
                const anoVazio = document.getElementById('ir-review-ano');
                if (chave === 'data_documento' && anoVazio && !String(anoVazio.value || '').trim()) {
                    anoVazio.value = sugerido.valor.slice(0, 4);
                    marcarSugerido(anoVazio);
                }
            });
        } else if (String(campo.value).trim() !== String(sugerido.valor)
                   && !(chave === 'valor' && Math.abs(Number(campo.value) - Number(sugerido.valor)) < 0.005)) {
            nota(campo, `A leitura sugere: ${exibido} (o valor atual foi mantido).`);
        }
    }
    // Ano-calendario acompanha a data sugerida, so se estiver vazio.
    const ano = document.getElementById('ir-review-ano');
    if (preencher && ano && !String(ano.value || '').trim() && leitura.campos.data_documento.valor) {
        ano.value = leitura.campos.data_documento.valor.slice(0, 4);
        marcarSugerido(ano);
    }
    // Valor ambiguo: opcoes para escolher (nenhuma e aplicada sozinha).
    const valor = document.getElementById('ir-review-valor');
    if (valor && leitura.valoresCandidatos.length && !String(valor.value || '').trim()) {
        const opcoes = document.createElement('span');
        opcoes.className = 'cf-leitura-opcoes';
        opcoes.append('Valores encontrados: ');
        for (const candidato of leitura.valoresCandidatos) {
            const b = document.createElement('button');
            b.type = 'button';
            b.className = 'cf-leitura-opcao';
            b.textContent = reais(candidato);
            b.addEventListener('click', () => { valor.value = candidato; valor.dispatchEvent(new Event('input', { bubbles: true })); });
            opcoes.append(b);
        }
        valor.closest('label').append(opcoes);
    }
    const seletor = document.getElementById('ir-review-categoria');
    if (seletor && categoria) {
        const disponivel = categoria.categoria_id && !seletor.value && [...seletor.options].some((o) => Number(o.value) === categoria.categoria_id);
        const escolher = () => {
            seletor.value = String(categoria.categoria_id);
            seletor.dispatchEvent(new Event('change', { bubbles: true }));  // a tela original resolve a Categoria IR
            marcarSugerido(seletor);
        };
        if (disponivel && preencher) {
            escolher();
            nota(seletor, categoria.aviso);
        } else if (disponivel) {
            notaComUsar(seletor, `${categoria.aviso} (${categoria.categoria_nome})`, () => { escolher(); nota(seletor, categoria.aviso); });
        } else if (!categoria.categoria_id && categoria.candidatas.length) {
            nota(seletor, categoria.aviso);
        } else if (categoria.categoria_id && seletor.value && Number(seletor.value) !== categoria.categoria_id) {
            nota(seletor, `A leitura sugere a categoria ${categoria.categoria_nome} (a atual foi mantida).`);
        }
    }
}

function instalarSugestoesDaRevisao() {
    const modal = document.getElementById('ir-review-modal');
    if (!modal) return;
    let aberto = false;
    new MutationObserver(() => {
        const agora = modal.classList.contains('open');
        if (agora && !aberto) aplicarSugestoes(modal).catch(() => {});
        if (!agora) limparSugestoes(modal);
        aberto = agora;
    }).observe(modal, { attributes: true, attributeFilter: ['class'] });
}

const contextoMoldura = await iniciarMoldura();
if (contextoMoldura && contextoMoldura.perfil) {
    perfilId = contextoMoldura.perfil.id;
    configurarDocumentos(contextoMoldura.perfil, { aoEnviar: retornoDoEnvio, aoLer: andamentoDaLeitura });
    window.CF_REGISTRAR_ADAPTADOR(responderDocumentos);
    instalarAberturaDeArquivos(perfilId);  // "Abrir arquivo" (link /api/ir/comprovantes/<id>/arquivo)
    instalarDesvinculo();
    instalarRetornoDoEnvio();
    instalarExclusao();
    instalarRelatorioIr();
    instalarSugestoesDaRevisao();  // FIN-REG-08
} else if (contextoMoldura) {
    window.CF_REGISTRAR_ADAPTADOR(async () => falha('Nenhum perfil financeiro autorizado para esta conta.', 403));
}
