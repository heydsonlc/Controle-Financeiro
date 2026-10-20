// Cliente Supabase unico da aplicacao. A configuracao vem de config.js, gerado no
// build SOMENTE com a URL do projeto e a chave publicavel (nunca uma chave privilegiada).

const config = window.CF_CONFIG || {};

if (!config.supabaseUrl || !config.supabasePublishableKey) {
    throw new Error('Configuracao do Supabase ausente (config.js).');
}

export const supabase = window.supabase.createClient(config.supabaseUrl, config.supabasePublishableKey, {
    auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: false,
        // Chave propria: nunca reaproveitar a sessao de outro sistema Kortex.
        storageKey: 'cf-financeiro-auth',
    },
    db: { schema: 'financeiro' },
});
