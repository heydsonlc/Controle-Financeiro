// FIN-FIDELIDADE-DOCUMENTOS-1 — "Abrir arquivo" de comprovante/documento fiscal nas telas originais (Imposto de Renda e
// Patrimonio). No Flask o link /api/ir/comprovantes/<id>/arquivo abre o arquivo numa nova aba (send_file inline). Aqui nao
// ha servidor /api/: o link (ou window.open) e interceptado, o arquivo vem do Supabase (arquivo_comprovante_tela, so
// leitura, mesmas regras de perfil) e abre na nova aba como blob, sem sair do navegador.

import { supabase } from './cliente.js';
import { mensagemDeErro } from './adaptador-comum.js';

const ARQUIVO = /^\/api\/ir\/comprovantes\/(\d+)\/arquivo$/;

function idDoArquivo(endereco) {
    try {
        const url = new URL(endereco, window.location.href);
        if (url.origin !== window.location.origin) return null;
        const m = ARQUIVO.exec(url.pathname);
        return m ? Number(m[1]) : null;
    } catch (_erro) {
        return null;
    }
}

function blobDe(dados) {
    const binario = atob(dados.conteudo_base64 || '');
    const bytes = new Uint8Array(binario.length);
    for (let i = 0; i < binario.length; i += 1) bytes[i] = binario.charCodeAt(i);
    return new Blob([bytes], { type: dados.mime_type || 'application/octet-stream' });
}

// A aba e aberta ja no clique (sem bloqueio de pop-up) e recebe o arquivo quando ele chega.
async function abrir(perfilId, comprovanteId, abrirJanela) {
    const janela = abrirJanela('about:blank', '_blank');
    try {
        const { data, error } = await supabase.rpc('arquivo_comprovante_tela', { p_perfil_id: perfilId, p_comprovante_id: comprovanteId });
        if (error) throw error;
        const url = URL.createObjectURL(blobDe(data));
        if (janela) {
            janela.opener = null;
            janela.location.href = url;
        } else {
            window.location.href = url;
        }
        window.setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (erro) {
        if (janela) janela.close();
        window.alert(mensagemDeErro(erro));
    }
}

export function instalarAberturaDeArquivos(perfilId) {
    const abrirJanela = window.open.bind(window);
    document.addEventListener('click', (evento) => {
        const link = evento.target.closest && evento.target.closest('a[href]');
        const id = link ? idDoArquivo(link.getAttribute('href')) : null;
        if (id === null) return;
        evento.preventDefault();
        evento.stopImmediatePropagation();
        abrir(perfilId, id, abrirJanela);
    }, true);
    window.open = (endereco, ...resto) => {
        const id = idDoArquivo(String(endereco || ''));
        if (id === null) return abrirJanela(endereco, ...resto);
        abrir(perfilId, id, abrirJanela);
        return null;
    };
}

// Botoes que no Flask navegam para um relatorio gerado no servidor (window.location.href = '/api/...'): aqui informam
// que o relatorio continua no sistema atual, em vez de abrir uma pagina inexistente.
export function recusarNavegacao(seletores, mensagem) {
    document.addEventListener('click', (evento) => {
        if (!seletores.some((s) => evento.target.closest && evento.target.closest(s))) return;
        evento.preventDefault();
        evento.stopImmediatePropagation();
        window.alert(mensagem);
    }, true);
}
