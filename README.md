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
8. Crea un client credenziali: `python -m app.cli.create_client "Reporting" --scope reports:read`.
9. Avvia il server di sviluppo: `uvicorn app.main:app --reload` oppure `./run.sh server`.

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
python -m app.cli.create_client "Reporting" --scope "reports:read"
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

## Comandi utili

| Comando | Descrizione |
| ------- | ----------- |
| `./run.sh init-db` | Crea le tabelle nel database |
| `./run.sh keygen` | Genera e salva una chiave Fernet |
| `./run.sh jwt-keygen` | Genera e salva un secret JWT |
| `./run.sh create-admin ...` | Crea un utente amministratore |
| `./run.sh create-client ...` | Crea un'applicazione client credential |
| `./run.sh server` | Avvia Uvicorn in modalità reload |
| `./run.sh test` | Esegue la suite di test con Pytest |

Tutti i comandi sono invocabili anche con `python -m ...` se preferisci non usare lo script shell.

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

Utilizza l'header `Authorization: Bearer <token>` nelle richieste.

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
