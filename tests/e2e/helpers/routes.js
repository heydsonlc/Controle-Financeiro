const smokeRoutes = [
  { path: '/', label: 'Dashboard' },
  { path: '/configuracoes', label: 'Configuracoes' },
  { path: '/despesas', label: 'Despesas' },
  { path: '/cartoes', label: 'Cartoes' },
  { path: '/receitas', label: 'Receitas' },
  { path: '/lancamentos', label: 'Lancamentos' },
  { path: '/financiamentos', label: 'Financiamentos' },
  { path: '/contas-bancarias', label: 'Contas Bancarias' },
  { path: '/patrimonio', label: 'Patrimonio' },
  { path: '/categorias', label: 'Categorias' },
  { path: '/veiculos', label: 'Veiculos' },
  { path: '/preferencias', label: 'Preferencias' },
  { path: '/ajuda', label: 'Ajuda e Manual' },
  { path: '/importar-cartao', label: 'Importar Cartao' }
];

const diagnosticRoutes = [
  {
    path: '/financiamentos/seguro',
    label: 'Seguro Habitacional',
    reason: 'Pendente conhecida: template usa base.html ainda inexistente ate UX-1B.'
  },
  {
    path: '/indexadores',
    label: 'Indexadores',
    reason: 'Rota existe, mas fica fora do smoke principal ate validacao visual/asset dedicada.'
  }
];

module.exports = {
  smokeRoutes,
  diagnosticRoutes
};
