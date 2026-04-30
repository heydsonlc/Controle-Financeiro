function formatLocation(location) {
  if (!location || !location.url) return 'origem nao informada';

  const line = location.lineNumber !== undefined ? `:${location.lineNumber}` : '';
  const column = location.columnNumber !== undefined ? `:${location.columnNumber}` : '';
  return `${location.url}${line}${column}`;
}

function attachConsoleErrorTracking(page, routePath) {
  const events = [];

  page.on('console', (message) => {
    if (message.type() !== 'error') return;
    const location = formatLocation(message.location());
    const text = message.text();

    if (isKnownNonCriticalConsoleError(text, location)) return;

    events.push({
      route: routePath,
      type: 'console.error',
      text,
      location
    });
  });

  page.on('pageerror', (error) => {
    events.push({
      route: routePath,
      type: 'pageerror',
      text: error.message,
      location: error.stack || 'stack nao disponivel'
    });
  });

  return {
    assertNoCriticalErrors() {
      if (events.length === 0) return;

      const details = events
        .map((event) => [
          `rota: ${event.route}`,
          `tipo: ${event.type}`,
          `mensagem: ${event.text}`,
          `origem: ${event.location}`
        ].join('\n'))
        .join('\n\n---\n\n');

      throw new Error(`Erros criticos capturados no navegador:\n\n${details}`);
    }
  };
}

function isKnownNonCriticalConsoleError(text, location) {
  return (
    text.includes('Failed to load resource') &&
    text.includes('404') &&
    location.includes('/favicon.ico')
  );
}

module.exports = {
  attachConsoleErrorTracking
};
