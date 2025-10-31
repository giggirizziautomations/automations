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
python -m app.cli.create_client "Reporting" --client-id reporting-service --scope "reports:read"
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
| `./run.sh create-client --client-id <id> --scope ...` | Crea un'applicazione client credential |
| `./run.sh create-client <id> --scope ...` | Variante con `client_id` posizionale |
| `./run.sh server` | Avvia Uvicorn in modalità reload |
| `./run.sh test` | Esegue la suite di test con Pytest |
| `python -m app.cli.open_webpage <url> <user>` | Apre una pagina web in un browser visibile |

Tutti i comandi sono invocabili anche con `python -m ...` se preferisci non usare lo script shell.

### Apertura di pagine web

Il comando `python -m app.cli.open_webpage <url> <user>` (o la relativa API `/browser/open`) avvia
un browser Chromium con interfaccia grafica, raggiunge l'indirizzo richiesto e attende il completamento
del caricamento (stato `networkidle`) prima di restituire il controllo. Il browser rimane aperto dopo la
navigazione così da consentire eventuali interazioni manuali con la pagina già caricata.

## Toolkit di scraping assistito

Il progetto include un toolkit che permette di trasformare istruzioni in linguaggio naturale
in azioni strutturate pronte per l'esecuzione da parte di un motore di scraping. L'obiettivo
è assistere utenti senza esperienza tecnica nella definizione dei passaggi necessari a
interagire con pagine web e raccogliere i dati desiderati.

### Generazione intelligente delle azioni

Ogni azione viene ricavata partendo da due elementi forniti dall'utente:

1. **Istruzione in linguaggio naturale**, ad esempio "Clicca il pulsante di login" oppure
   "Attendi 2.5 secondi prima di continuare".
2. **Frammento HTML** relativo all'elemento con cui bisogna interagire.

Il motore inferisce automaticamente il tipo di azione (`click`, `fill`, `select`, `wait` o
`custom`), costruisce un selettore CSS affidabile e arricchisce l'output con metadati utili,
come l'etichetta dell'elemento, un valore suggerito, l'anteprima HTML e un indice di
confidenza. Per i campi di tipo password viene anche segnalato che il dato atteso è
sensibile.

## Reference API per router

Ogni router FastAPI viene esposto con un prefisso dedicato e raggruppato tramite tag OpenAPI.
Tutti gli endpoint richiedono autenticazione bearer token a meno che non sia indicato diversamente.

### Autenticazione (`/auth`)

| Metodo | Percorso | Descrizione | Note |
| ------ | -------- | ----------- | ---- |
| `POST` | `/auth/token` | Genera un access token usando credenziali e-mail/password. | Accetta payload JSON o form-url-encoded. |
| `GET` | `/auth/token` | Genera un access token usando client id e secret registrati. | Richiede query `client_id` e `client_secret`. |

### Browser (`/browser`)

| Metodo | Percorso | Descrizione | Note |
| ------ | -------- | ----------- | ---- |
| `POST` | `/browser/open` | Avvia un browser Chromium visibile e apre la pagina richiesta, mantenendo la sessione aperta. | Sostituisce eventuali sessioni Playwright attive dello stesso utente. |

### Profilo utente (`/me`)

| Metodo | Percorso | Descrizione | Note |
| ------ | -------- | ----------- | ---- |
| `GET` | `/me` | Restituisce i dati dell'utente autenticato. | |
| `PATCH` | `/me` | Aggiorna nome, cognome, e-mail o password dell'utente corrente. | Non consente la modifica dei campi amministrativi. |

### Gestione utenti (`/users`)

| Metodo | Percorso | Descrizione | Note |
| ------ | -------- | ----------- | ---- |
| `POST` | `/users` | Crea un nuovo utente. | Richiede ruolo amministratore. |
| `GET` | `/users` | Elenca gli utenti con supporto a paginazione (`skip`, `limit`). | Richiede ruolo amministratore. |
| `GET` | `/users/{user_id}` | Recupera un utente per identificativo. | Richiede ruolo amministratore. |
| `PATCH` | `/users` | Aggiorna i dati del proprio account (utente autenticato). | Impedisce di modificare scope o privilegi amministrativi. |
| `DELETE` | `/users/{user_id}` | Elimina un utente. | Richiede ruolo amministratore. |

### Report protetti (`/reports`)

| Metodo | Percorso | Descrizione | Note |
| ------ | -------- | ----------- | ---- |
| `GET` | `/reports` | Restituisce un elenco di report dimostrativi. | Richiede lo scope `reports:read`. |

### Toolkit di scraping (`/scraping`)

Tutti gli endpoint sono protetti da autenticazione bearer token. Le routine sono associate
all'utente che le crea e non sono accessibili da altri account.

| Metodo | Percorso | Descrizione |
| ------ | -------- | ----------- |
| `POST` | `/scraping/routines` | Crea una routine con URL, modalità browser, azioni iniziali ed eventuali credenziali. |
| `POST` | `/scraping/actions/preview` | Genera un'anteprima di un'azione a partire da istruzione e frammento HTML. |
| `POST` | `/scraping/routines/{routine_id}/actions` | Appende una nuova azione ad una routine esistente. |
| `PATCH` | `/scraping/routines/{routine_id}/actions/{action_index}` | Sostituisce un'azione esistente con una nuova versione generata da linguaggio naturale. |
| `POST` | `/scraping/routines/{routine_id}/execute` | Riesegue le azioni memorizzate aprendo il browser se necessario e navigando all'URL della routine prima dell'esecuzione. |

### Struttura delle azioni

L'endpoint di anteprima e quelli di mutazione restituiscono sempre un oggetto con la
seguente forma:

```json
{
  "type": "click",
  "selector": "#login-btn",
  "description": "Click the login button",
  "target_tag": "button",
  "input_text": null,
  "metadata": {
    "attributes": {"id": "login-btn"},
    "html_preview": "<button id='login-btn'>Sign in</button>",
    "raw_instruction": "Click the login button",
    "confidence": 0.95,
    "label": null,
    "text": "Sign in",
    "suggested_value": null,
    "delay_seconds": null
  }
}
```

- `selector` è costruito automaticamente privilegiando `id`, `data-*` o `name` per
  massimizzare l'affidabilità.
- `confidence` rappresenta una stima (0.35–0.95) della solidità del selettore.
- `delay_seconds` è valorizzato per le azioni di tipo `wait` quando l'istruzione include
  una durata (supportate millisecondi, secondi e minuti).
- `suggested_value` viene popolato quando il markup include placeholder o valori di default
  utili per campi di input o select.

### Persistenza e isolamento

Le routine vengono salvate nella tabella `scraping_routines` con il riferimento all'autore.
Ogni record memorizza le azioni in formato JSON, l'URL target, la modalità browser (`headless`
o `headed`) ed eventuali credenziali da usare durante la sessione. Le password vengono
cifrate con Fernet e recuperate in chiaro solo per l'utente proprietario della routine.

## Esportatore Power BI con azioni di scraping

L'integrazione Power BI fornisce una pipeline completa per scaricare report e registrare
lo storico delle esportazioni. A partire da questa versione è possibile allegare alla
configurazione le stesse azioni strutturate generate dal toolkit di scraping così da
preparare la pagina (login, navigazione, filtri, ecc.) prima di avviare il download del
report.

### Configurazione del servizio

1. Autenticati con un utente dotato dello scope `bi` oppure con un amministratore.
2. Esegui una richiesta `PUT /power-bi/config` fornendo l'URL del report, le opzioni di
   merge ed eventualmente le credenziali.
3. Usa il campo `scraping_actions` per elencare le azioni da rieseguire ad ogni export.

Esempio completo:

```bash
curl -X PUT \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
        "report_url": "https://app.powerbi.com/groups/me/reports/12345",
        "export_format": "csv",
        "merge_strategy": "append",
        "username": "bi.user@example.com",
        "password": "Sup3rSecret",
        "scraping_actions": [
          {
            "type": "click",
            "selector": "#login-button",
            "description": "Apre il form di autenticazione",
            "target_tag": "button",
            "metadata": {"confidence": 0.92}
          },
          {
            "type": "fill",
            "selector": "input[name=\"email\"]",
            "description": "Inserisce l'email aziendale",
            "input_text": "bi.user@example.com"
          }
        ]
      }' \
  http://localhost:8000/power-bi/config
```

Le azioni supportano gli stessi campi descritti nel paragrafo "Struttura delle azioni" e
possono essere generate tramite gli endpoint `/scraping/actions/preview` e
`/scraping/routines/.../actions`. È possibile omettere `password` nelle richieste successive
per mantenere il valore precedentemente cifrato nel database.

### Esecuzione di un'esportazione

Una volta configurato il servizio, invia una richiesta `POST /power-bi/run` specificando
il VIN o un identificativo equivalente e, opzionalmente, i parametri da passare al report:

```bash
curl -X POST \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
        "vin": "1A4AABBC5KD501999",
        "parameters": {"region": "eu"},
        "notes": "Report mensile"
      }' \
  http://localhost:8000/power-bi/run
```

La risposta include lo stato dell'export e, all'interno della chiave `payload`, una copia
degli step elencati in `scraping_actions` così da poter verificare quali interazioni verranno
eseguite prima del download. Tutte le esecuzioni vengono storicizzate e possono essere
consultate tramite gli endpoint amministrativi (`GET /power-bi/admin/exports` e
`GET /power-bi/admin/exports/by-vin/{vin}`).

### Esempio di workflow

1. **Creazione**

   ```bash
   curl -X POST \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
           "url": "https://example.com/login",
           "mode": "headless"
         }' \
     http://localhost:8000/scraping/routines
   ```

2. **Anteprima azione**

   ```bash
   curl -X POST \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
           "instruction": "Fill the email field with \"demo@example.com\"",
           "html_snippet": "<input id=\"email\" name=\"email\" placeholder=\"Email\" />"
         }' \
     http://localhost:8000/scraping/actions/preview
   ```

3. **Append**

   ```bash
   curl -X POST \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
           "instruction": "Fill the email field with \"demo@example.com\"",
           "html_snippet": "<input id=\"email\" name=\"email\" placeholder=\"Email\" />"
         }' \
     http://localhost:8000/scraping/routines/1/actions
   ```

4. **Patch**

   ```bash
   curl -X PATCH \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
           "instruction": "Wait for 2 seconds after clicking",
           "html_snippet": "<div data-testid=\"loader\"></div>"
         }' \
     http://localhost:8000/scraping/routines/1/actions/0
   ```

> ℹ️ **Suggerimento:** includi nel frammento HTML tutti gli attributi utili (id, data-* e
> name) per aiutare il generatore a proporre selettori precisi e ottenere un indice di
> confidenza elevato.

> ℹ️ **Nuova istruzione:** per i client `client_credentials` fornisci sempre un `client_id` esplicito.
> Il comando mostrerà il `client_secret` una sola volta: salvalo in modo sicuro perché
> non potrà essere recuperato dal database in chiaro.

## Gestione del servizio

Per ambienti permanenti puoi registrare l'applicazione come servizio `systemd` così da
gestirla con i classici comandi `systemctl`.

1. Installa le dipendenze nel percorso definitivo (es. `/opt/automations`) e crea il file
   `/etc/systemd/system/automations.service` con i permessi di root:

   ```ini
   [Unit]
   Description=Automations API
   After=network.target

   [Service]
   Type=simple
   WorkingDirectory=/opt/automations
   EnvironmentFile=/opt/automations/.env
   ExecStart=/opt/automations/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
   Restart=on-failure

   [Install]
   WantedBy=multi-user.target
   ```

   Adatta i percorsi a seconda della tua installazione (virtualenv, porta di ascolto, ecc.).

2. Ricarica la configurazione e avvia il servizio:

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now automations.service
   ```

3. Monitora lo stato e i log con:

   ```bash
   systemctl status automations.service
   journalctl -u automations.service -f
   ```

Quando è registrato come servizio puoi riavviare, fermare o aggiornare l'applicazione con i
classici comandi `systemctl restart|stop automations.service` e gestire i segreti tramite il file
`EnvironmentFile` o tramite variabili definite direttamente nell'unità.

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

```text
.
├── app
│   ├── cli
│   │   ├── create_admin.py
│   │   ├── create_client.py
│   │   ├── jwt_keygen.py
│   │   ├── keygen.py
│   │   ├── open_webpage.py
│   │   └── utils.py
│   ├── core
│   │   ├── auth.py
│   │   ├── browser.py
│   │   ├── config.py
│   │   ├── logging.py
│   │   └── security.py
│   ├── db
│   │   ├── base.py
│   │   ├── init_db.py
│   │   └── models.py
│   ├── routers
│   │   ├── auth.py
│   │   ├── browser.py
│   │   ├── me.py
│   │   ├── reports.py
│   │   └── users.py
│   ├── schemas
│   │   ├── auth.py
│   │   ├── browser.py
│   │   ├── client.py
│   │   └── user.py
│   ├── setup
│   │   └── client_credentials.py
│   └── main.py
├── tests
│   ├── conftest.py
│   ├── test_auth_client.py
│   ├── test_auth_password.py
│   ├── test_cli_admin.py
│   ├── test_security.py
│   ├── test_setup_client_credentials.py
│   └── test_users_self_service.py
├── requirements.txt
├── requirements-dev.txt
├── run.sh
├── pyproject.toml
└── README.md
```
