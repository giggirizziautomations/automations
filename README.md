# Automations API

Stack FastAPI pronto per ambienti di produzione, progettato per crescere in ecosistemi a microservizi.

## Requisiti

- Python 3.11+
- SQLite (incluso con Python)
- Ambiente virtuale consigliato

## Setup rapido

1. Clona il repository e crea un virtualenv.
2. Installa le dipendenze: `pip install -e .[dev]` (oppure `pip install -e .` per runtime).
   - In alternativa puoi usare `pip install -r requirements.txt` o `pip install -r requirements-dev.txt`.
3. Copia l'ambiente di esempio: `cp .env.example .env` e compila i valori richiesti.
4. Inizializza il database: `python -m app.db.init_db` oppure `./run.sh init-db`.
5. Genera una chiave Fernet: `python -m app.cli.keygen` (verrà aggiunta automaticamente al tuo `.env`).
6. Genera un secret JWT: `python -m app.cli.jwt_keygen` (verrà aggiunto automaticamente al tuo `.env`, insieme ad eventuali aggiornamenti di `JWT_SECRET`).
7. Crea un amministratore: `python -m app.cli.create_admin Nome Cognome email@example.com --password ****`.
8. Crea un client credenziali: `python -m app.cli.create_client "Reporting" --client-id reporting-service --scope reports:read`.
   - In alternativa puoi passare il `client_id` come secondo argomento posizionale: `python -m app.cli.create_client "Reporting" reporting-service`.
9. Esegui un login MSAL di prova usando gli endpoint `/powerbi/device-login` e `/powerbi/device-login/complete` con un token utente oppure, in alternativa, dal terminale con `./run.sh aad-login`.
   - L'endpoint di avvio restituisce il codice dispositivo e le istruzioni fornite da Microsoft Entra; quello di completamento conclude il flusso e restituisce il token MSAL.
   - Entrambi riutilizzano il `PUBLIC_CLIENT_ID` configurato sul profilo dell'utente autenticato e l'`aad_tenant_id` salvato sul database.
9. Esegui un login MSAL di prova usando l'endpoint `/powerbi/device-login` con un token utente o, in alternativa, dal terminale con `./run.sh aad-login`.
   - L'endpoint riutilizza il `PUBLIC_CLIENT_ID` configurato sul profilo dell'utente autenticato e l'`aad_tenant_id` salvato sul database.
   - Il comando CLI continua a funzionare per scenari manuali o offline e salva i token nella cache configurata.
10. Avvia il server di sviluppo: `uvicorn app.main:app --reload` oppure `./run.sh server`.

### Sequenza comandi da tastiera

Ecco una sequenza di comandi terminale che ripercorre l'intero setup (sostituisci i valori segnaposto dove necessario):

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
cp .env.example .env
python -m app.db.init_db
python -m app.cli.keygen
python -m app.cli.jwt_keygen
python -m app.cli.create_admin "Nome" "Cognome" admin@example.com --password "Password123" --scopes "*"
python -m app.cli.create_client "Reporting" --client-id reporting-service --scope "reports:read"
./run.sh aad-login
uvicorn app.main:app --reload
```

Su Windows PowerShell, sostituisci `source .venv/bin/activate` con `.venv\\Scripts\\Activate.ps1` e usa `setx`/`$Env:` per impostare le variabili di ambiente.

Le variabili di ambiente principali possono essere caricate tramite `.env` grazie a `python-dotenv`.

## Variabili di ambiente

| Nome | Descrizione | Default |
| ---- | ----------- | ------- |
| `DATABASE_URL` | Connessione al database | `sqlite:///./app.db` |
| `FERNET_KEY` | Chiave per cifrare password e client secret | _obbligatoria_ |
| `JWT_SECRET` | Secret per firmare i JWT HS256 | _obbligatorio_ |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Durata access token in minuti | `15` |
| `LOG_LEVEL` | Livello di log dell'applicazione | `INFO` |
| `TENANT_ID` | GUID del tenant Microsoft Entra ID usato come default per i nuovi utenti | _obbligatorio per popolare i profili_ |
| `PUBLIC_CLIENT_ID` | Client ID pubblico multi-tenant fornito da Microsoft per il device code flow | `04f0c124-f2bc-4f59-9a70-39b0f486b5ab` |
| `SCOPES` | Elenco di scope MSAL separati da spazio (es. Dataverse + OpenID) | `https://yourorg.crm.dynamics.com/user_impersonation offline_access openid profile` |
| `MSAL_OPEN_BROWSER` | Se `true`, apre automaticamente il browser locale con il codice dispositivo | `true` |
| `TOKEN_CACHE_PATH` | Percorso sul filesystem dove salvare la cache MSAL serializzata | `./data/aad_user_token_cache.json` |

Le variabili storiche `MSAL_CLIENT_ID`, `MSAL_AUTHORITY`, `MSAL_SCOPES` e `MSAL_TOKEN_CACHE_PATH` sono ancora supportate come fallback per
retrocompatibilità e verranno sovrascritte automaticamente dai nuovi valori quando presenti.

Ogni nuovo utente creato tramite CLI o API eredita automaticamente questi parametri MSAL.
I campi `aad_tenant_id`, `aad_public_client_id` e `aad_token_cache_path` vengono salvati sul record
utente per facilitare audit e troubleshooting, e possono essere sovrascritti passando valori espliciti
alle API di creazione.

## Comandi utili

| Comando | Descrizione |
| ------- | ----------- |
| `./run.sh init-db` | Crea le tabelle nel database |
| `./run.sh keygen` | Genera e salva una chiave Fernet |
| `./run.sh jwt-keygen` | Genera e salva un secret JWT |
| `./run.sh create-admin ...` | Crea un utente amministratore |
| `./run.sh create-client --client-id <id> --scope ...` | Crea un'applicazione client credential |
| `./run.sh create-client <id> --scope ...` | Variante con `client_id` posizionale |
| `./run.sh aad-login` | Avvia il device code flow MSAL usando il `PUBLIC_CLIENT_ID` |
| `./run.sh server` | Avvia Uvicorn in modalità reload |
| `./run.sh test` | Esegue la suite di test con Pytest |

Tutti i comandi sono invocabili anche con `python -m ...` se preferisci non usare lo script shell.

> ℹ️ **Nuova istruzione:** per i client `client_credentials` fornisci sempre un `client_id` esplicito.
> Il comando mostrerà il `client_secret` una sola volta: salvalo in modo sicuro perché
> non potrà essere recuperato dal database in chiaro.

## Flussi di autenticazione

### Password grant (utente)

```bash
curl -X POST \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d 'grant_type=password&email=admin@example.com&password=Password123' \
  http://localhost:8000/auth/token
```

Risposta:

```json
{
  "access_token": "<JWT>",
  "token_type": "bearer",
  "expires_in": 900,
  "scope": "*"
}
```

### Client credentials grant

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"grant_type":"client_credentials","client_id":"<id>","client_secret":"<secret>"}' \
  http://localhost:8000/auth/token
```

## Esempi di API protette

- `GET /users` richiede token admin.
- `GET /reports` richiede lo scope `reports:read`.
- `GET /me` restituisce il profilo corrente.
- `POST /powerbi/device-login` avvia il flusso device code MSAL e restituisce il codice dispositivo.
- `POST /powerbi/device-login/complete` conclude il flusso device code MSAL e restituisce il token ottenuto.

Utilizza l'header `Authorization: Bearer <token>` nelle richieste.

## Integrazione Power BI

Per ottenere un token tramite device code flow MSAL (con supporto MFA):

```bash
# 1) Avvio del flusso: ottieni il codice dispositivo
curl -X POST \
  -H "Authorization: Bearer <JWT utente>" \
  http://localhost:8000/powerbi/device-login

# Risposta (estratto)
{
  "flow_id": "<identificativo>",
  "user_code": "CODE-123",
  "verification_uri": "https://microsoft.com/devicelogin",
  "message": "Per completare l'accesso visita ..."
}

# 2) Completa l'autenticazione da browser seguendo le istruzioni restituite (supporta MFA)

# 3) Recupera il token MSAL una volta completato l'accesso
curl -X POST \
  -H "Authorization: Bearer <JWT utente>" \
  -H "Content-Type: application/json" \
  -d '{"flow_id":"<identificativo>"}' \
  http://localhost:8000/powerbi/device-login/complete
```

Gli endpoint recuperano il tenant (`aad_tenant_id`) e il client MSAL (`aad_public_client_id`) dal profilo dell'utente associato al token
e mantengono lo stato del flusso fino alla scadenza. Assicurati che gli utenti abbiano un `aad_tenant_id` valorizzato (viene popolato
automaticamente usando `TENANT_ID` durante la creazione) e, se vuoi persistere i token fra esecuzioni, configura `aad_token_cache_path`
o il relativo default in `TOKEN_CACHE_PATH`. In alternativa agli endpoint HTTP puoi avviare il flusso direttamente da terminale con
curl -X POST \
  -H "Authorization: Bearer <JWT utente>" \
  http://localhost:8000/powerbi/device-login
```

L'endpoint recupera il tenant (`aad_tenant_id`) e il client MSAL (`aad_public_client_id`) dal profilo dell'utente associato al token
e avvia il device code flow aprendo il browser con il codice precompilato. Al termine restituisce il token MSAL, che può essere
riutilizzato per chiamare le API di Power BI. Assicurati che gli utenti abbiano un `aad_tenant_id` valorizzato (viene popolato
automaticamente usando `TENANT_ID` durante la creazione) e, se vuoi persistere i token fra esecuzioni, configura `aad_token_cache_path`
o il relativo default in `TOKEN_CACHE_PATH`. In alternativa all'endpoint HTTP puoi avviare il flusso direttamente da terminale con
`./run.sh aad-login`.

## Logging e osservabilità

- Log strutturato: `timestamp | livello | request-id | logger | messaggio`.
- Middleware `X-Request-ID` per tracciare le richieste.
- Progettato per integrazione futura con sistemi di rate limiting o tracing distribuito.

## Sicurezza

- Password utenti e client secret vengono cifrati con Fernet e sono reversibili per integrazioni legacy.
- I JWT sono firmati HS256 con secret configurabile.
- Gli scope sono normalizzati e memorizzati come stringhe space-separated.
- Assicurati di ruotare periodicamente chiavi Fernet e secret JWT.

## Testing

Esegui l'intera suite:

```bash
./run.sh test
```

La suite copre:

- Roundtrip di cifratura Fernet
- Creazione di amministratori via CLI
- Login password grant
- Login client credentials

## Struttura del progetto

La struttura completa è riportata in fondo alla risposta del bot (albero dei file).
