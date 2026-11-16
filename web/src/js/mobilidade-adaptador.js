// FIN-FIDELIDADE-PATRIMONIO-1 (Mobilidade, fase 1) — adaptador da tela original de Mobilidade: responde as rotas
// /api/... que js/original/veiculos.js chama (ponte-api.js), no formato do Flask. Consulta (migration 20261115090000):
// veiculos, projecoes ja geradas, uso, regras e estimativas de manutencao por km, financiamento do veiculo, modalidade
// ativa, assinaturas, caminhos de transporte por app e categorias.
// FIN-MOBILIDADE-2 (migration 20261127090000): escrita pelas funcoes do banco, com o escritor unico do perfil (perfil
// ainda no Flask e recusado sem gravar): veiculos (criar, editar, converter, excluir com seguranca, gerar projecoes),
// regras e manutencao por km, financiamento projetivo do veiculo, previa e ativacao de modalidade (cenario ativo no
// banco, por perfil), assinaturas, caminhos de transporte por app e confirmar/adiar/ignorar despesas previstas.
// FIN-MVP-MOB-02 (migration 20261220090000): lista de Projecoes do veiculo (itens com tipo, valor e periodicidade):
// consulta, criar e editar, ativar ou desativar e excluir sem historico. As ocorrencias continuam em despesa_prevista.
// Categorias sistemicas MOB_* nunca sao criadas aqui. O arquivo global /api/veiculos/cenario-ativo do Flask nao e
// reproduzido (a tela le a modalidade ativa do banco).
// FIN-MOBILE-12: as regras (rotas, consultas e gravacoes) sairam daqui SEM mudanca para js/mobilidade-servico.js, comum a
// Mobilidade mobile; aqui fica a moldura.

import { falha } from './adaptador-comum.js';
import { configurarMobilidade, responderMobilidade } from './mobilidade-servico.js';
import { iniciarMoldura } from './moldura.js';

const contexto = await iniciarMoldura();
if (contexto && contexto.perfil) {
    configurarMobilidade(contexto.perfil.id);
    window.CF_REGISTRAR_ADAPTADOR(responderMobilidade);
} else if (contexto) {
    window.CF_REGISTRAR_ADAPTADOR(async () => falha('Nenhum perfil financeiro autorizado para esta conta.', 403));
}
