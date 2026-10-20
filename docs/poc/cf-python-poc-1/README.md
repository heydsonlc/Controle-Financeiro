# CF-PYTHON-POC-1 — prova de conceito isolada

Fontes da prova de conceito descrita em `docs/CF_PYTHON_POC_1.md`. **Nunca publicada**: executada só localmente com `pywrangler dev` (workerd local). Sem credenciais e sem banco real.

Para reproduzir (fora do repositório, numa pasta descartável):

1. Copiar esta pasta e, dentro dela, extrair `backend/` e `frontend/templates/` do commit desejado: `git archive HEAD backend frontend/templates | tar -x -C src`.
2. `uvx --from workers-py pywrangler sync` (resolve para CPython 3.14 / Pyodide).
3. `uvx --from workers-py pywrangler dev --port 8799 --ip 127.0.0.1`.
4. Chamar as rotas `/deps`, `/pdf`, `/xlsx`, `/runtime`, `/db-driver`, `/kdf` e `/app-real`.

Observações:
- `compatibility_date` é `2026-09-10` porque é a data mais recente aceita pelo `workerd` baixado localmente.
- Atrás de antivírus com inspeção TLS: `UV_SYSTEM_CERTS=1` e `NODE_OPTIONS=--use-system-ca`.
- `src/worker.py` usa um hash scrypt gerado no CPython para uma **senha fictícia** (`senha-poc-123456`). Não é credencial real.
