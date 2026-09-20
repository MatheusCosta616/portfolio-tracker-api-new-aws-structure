# QA do backend

O workflow `.github/workflows/qa.yml` executa duas camadas:

- `static-and-unit`: compila os fontes Python e roda toda a suíte `pytest` com relatório JUnit.
- `remote-smoke`: testa a API publicada sem alterar dados por padrão.

O smoke remoto verifica disponibilidade, OpenAPI, Swagger, proteção dos endpoints autenticados e rejeição de credenciais inválidas.

## Execução local

```powershell
py scripts/qa_remote.py
```

Por padrão, o alvo é `http://52.3.97.206:8000`. Para outro ambiente:

```powershell
$env:QA_BASE_URL = 'https://api.exemplo.com'
py scripts/qa_remote.py
```

O teste de dois cadastros com o mesmo nome é mutável e fica desativado por padrão. Execute apenas em um ambiente autorizado:

```powershell
$env:QA_RUN_MUTATING = 'true'
py scripts/qa_remote.py
```

## GitHub Actions

O workflow roda em push para `main`/`master`, pull requests, agendamento a cada 30 minutos e execução manual. Na execução manual é possível informar outra URL e habilitar o cenário mutável.

Configure estes secrets para o job completo de testes Django:

- `QA_SECRET_KEY`
- `QA_DB_NAME`
- `QA_DB_USER`
- `QA_DB_PASSWORD`
- `QA_DB_HOST`
- `QA_DB_PORT` (opcional, padrão `1521`)
- `QA_KEYCLOAK_SERVER_URL` (opcional)

O job remoto não precisa de secrets quando os checks não mutáveis estiverem habilitados.
