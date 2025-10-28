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
| `python -m app.cli.scrape_site <site> <user_id>` | Avvia una sessione di scraping configurata nel database |

Tutti i comandi sono invocabili anche con `python -m ...` se preferisci non usare lo script shell.

### Apertura di pagine web

Il comando `python -m app.cli.open_webpage <url> <user>` (o la relativa API `/browser/open`) avvia
un browser Chromium con interfaccia grafica, raggiunge l'indirizzo richiesto e attende il completamento
del caricamento (stato `networkidle`) prima di restituire il controllo. Il browser rimane aperto dopo la
navigazione così da consentire eventuali interazioni manuali con la pagina già caricata.

### Scraping configurabile

Il comando `python -m app.cli.scrape_site <site_name> <user_id>` riutilizza le configurazioni salvate
nella tabella `scraping_targets` per avviare una sessione di scraping in Playwright. Ogni record contiene:

- `user_id`: collegamento all'utente che ha definito l'operazione;
- `site_name`: identificativo mnemonico dell'operazione;
- `url`: indirizzo da aprire nel browser;
- `recipe`: nome della ricetta da utilizzare (`default` o `save_screenshot` di default);
- `parameters`: JSON opzionale con impostazioni aggiuntive (es. `{ "settle_ms": 2000 }`).
- `password`: password opzionale per lo scraping; se omessa viene riutilizzata quella dell'utente proprietario.

Puoi creare queste configurazioni anche tramite API autenticata con un amministratore:

```http
POST /scraping-targets
Authorization: Bearer <token>
Content-Type: application/json

{
  "user_id": 1,
  "site_name": "my-site",
  "url": "https://example.com/login",
  "recipe": "default",
  "parameters": {"settle_ms": 1500},
  "notes": "Login di esempio",
  "password": "PasswordDaUsare"
}
```

La password viene cifrata automaticamente con la chiave Fernet. Se il campo è vuoto o assente, lo script di scraping decodificherà e userà la password dell'utente proprietario. Quando una password specifica è presente nel record, questa viene decifrata e resa disponibile alle ricette durante l'esecuzione (ad esempio nel parametro `password`).

Per avviare la sessione in modalità non headless oppure salvare il report su file:

```bash
python -m app.cli.scrape_site my-site 1 --no-headless --output report.json
```

Se desideri lanciare lo scraping per conto di un altro operatore (ad esempio un analista o un membro
del team di supporto) specifica `--invoked-by` per attribuire correttamente l'esecuzione:

```bash
python -m app.cli.scrape_site my-site 1 --invoked-by "support@example.com"
```

Il report JSON risultante include sia il proprietario della configurazione (`user`) sia l'operatore che
ha avviato la sessione (`run_by`), così puoi tracciare chi ha effettuato l'esecuzione.

Le istruzioni di scraping sono raccolte in `app/scraping/recipes.py` e sono suddivise in **azioni**
atomiche. Il dizionario `SCRAPING_ACTIONS` elenca tutte le operazioni disponibili indicando per
ognuna una breve descrizione, i campi obbligatori e quelli opzionali. Per costruire la tua routine
aggiungi al campo `parameters` del record nel database una lista `actions` composta da dizionari con
la forma `{"action": "nome", ...}`:

```json
{
  "settle_ms": 1500,
  "actions": [
    { "action": "wait", "seconds": 1.5 },
    { "action": "click", "selector": "button.login" },
    { "action": "wait_for_element", "selector": "#username" },
    { "action": "fill", "selector": "#username", "text": "demo" },
    { "action": "fill", "selector": "#password", "text": "demo" },
    { "action": "click", "selector": "button[type=submit]" },
    { "action": "wait_for_element", "selector": "#result", "state": "visible" },
    { "action": "get_text", "selector": "#result", "store_as": "result_text" }
  ]
}
```

Tra le azioni già disponibili trovi `wait`, `wait_for_element`, `click`, `fill`, `hover`, `scroll_to`,
`get_text`, `get_attribute`, `save_html` e `screenshot`. Ogni azione accetta parametri autoesplicativi
(es. `selector`, `seconds`, `store_as`, `path`). Puoi visionare la lista completa e i relativi campi
direttamente nel file `app/scraping/recipes.py` oppure da una shell Python:

```python
from pprint import pprint
from app.scraping.recipes import SCRAPING_ACTIONS

pprint({name: {
    "description": details["description"],
    "required": details["required_fields"],
    "optional": tuple(details["optional_fields"].keys()),
} for name, details in SCRAPING_ACTIONS.items()})
```

Le ricette predefinite (`default`, `save_screenshot`) eseguono nell'ordine le azioni indicate, quindi
puoi aggiungere nuove ricette o personalizzare quelle esistenti aggiornando il campo `recipe` del
relativo record nel database.

### Generazione guidata delle azioni

Se desideri generare automaticamente la struttura JSON partendo dal codice HTML dell'elemento da
interagire, puoi utilizzare i nuovi helper disponibili in `app.scraping.helpers`.

1. **Estrai lo snippet HTML di interesse** (ad esempio ispezionando la pagina con gli strumenti del
   browser) e apri una shell Python nel progetto:

   ```bash
   python
   ```

2. **Genera gli step** tramite `build_action_step` o il documento completo con
   `build_actions_document`:

   ```python
   >>> from app.scraping.helpers import build_action_step, build_actions_document
   >>> html = '<button id="submit-login" class="btn">Login</button>'
   >>> build_action_step(html, "click")
   {'action': 'click', 'selector': '#submit-login'}
   >>> build_actions_document(html, "click", settle_ms=500)
   {'actions': [{'action': 'click', 'selector': '#submit-login'}], 'settle_ms': 500}
   ```

   Il generatore analizza il primo elemento presente nello snippet e costruisce un selettore CSS
   stabile utilizzando `id`, `class`, attributi `name` o `data-*`. Le azioni riconosciute includono:

   - `wait`: crea automaticamente un'azione `wait_for_element` se è possibile dedurre un selettore,
     altrimenti ripiega su un semplice `wait` di 1000ms;
   - `click`: produce un'azione `click` con il selettore più specifico disponibile;
   - `input text` (oltre ai sinonimi `fill`, `type`): crea un'azione `fill` valorizzando `value` con il
     campo esplicito passato alla funzione oppure con `placeholder`/`value`/`aria-label` trovati
     nell'HTML.

3. **Componi più step** concatenando l'output di `build_action_step` in un array. Un semplice script
   può aiutarti a evitare copia/incolla manuali:

   ```python
   from app.scraping.helpers import build_action_step

   snippets = [
       ("<input name='email' placeholder='Email'>", "input text"),
       ("<input name='password' type='password'>", "input text"),
       ("<button type='submit' class='btn primary'>Accedi</button>", "click"),
   ]

   actions = [build_action_step(html, action) for html, action in snippets]
   document = {"settle_ms": 800, "actions": actions}
   ```

4. **Invia il documento alle API di scraping**. L'endpoint `PUT /scraping-targets/{id}/actions`
   sostituisce il blocco JSON associato a un target esistente. Esempio con `httpie` (dove `actions`
   rappresenta l'array di step e `parameters` contiene i restanti campi del documento):

   ```bash
   http PUT :8000/scraping-targets/42/actions \
     Authorization:'Bearer <token admin>' \
     actions:='[{"action": "click", "selector": "#submit-login"}]' \
     parameters:='{"settle_ms": 800}'
   ```

   oppure con `curl` combinando il documento generato con `jq` o salvandolo su file:

   ```bash
   python - <<'PY'
   import json
   from app.scraping.helpers import build_actions_document

   html = '<button id="submit-login" class="btn">Login</button>'
   document = build_actions_document(html, "click", settle_ms=500)
   payload = {
       "actions": document["actions"],
       "parameters": {k: v for k, v in document.items() if k != "actions"},
   }
   print(json.dumps(payload))
   PY > actions.json

   curl -X PUT \
     -H "Authorization: Bearer <token admin>" \
     -H "Content-Type: application/json" \
     --data @actions.json \
     http://localhost:8000/scraping-targets/42/actions
   ```

   Il corpo accetta sia la chiave `actions` (obbligatoria) sia un oggetto `parameters` opzionale che
   verrà fuso con i parametri esistenti. In assenza di `parameters` l'endpoint mantiene quelli già
   salvati nel database.

5. **Anteprima rapida tramite API**. Gli endpoint `POST /scraping-targets/actions/preview` e
   `POST /scraping-targets/{id}/actions/from-html` accettano ora il campo `action` al posto del
   precedente `suggestion`. I client esistenti continuano a funzionare grazie all'alias automatico,
   ma il nuovo nome rende esplicito che il valore deve indicare direttamente il tipo di azione da
   generare (es. `click`, `wait`, `input text`). Entrambi gli endpoint normalizzano inoltre gli
   snippet HTML che contengono doppi apici non escapati, così puoi inviare direttamente il codice
   copiato dagli strumenti del browser senza doverlo manipolare manualmente. È sufficiente inviare
   un corpo JSON o `application/x-www-form-urlencoded`, come nell'esempio:

   ```bash
   curl -X POST \
     -H "Authorization: Bearer <token admin>" \
     -H "Content-Type: application/json" \
     -d '{"html": "<div data-bind="text: session.tileDisplayName">demo</div>", "action": "click"}' \
     http://localhost:8000/scraping-targets/actions/preview
   ```

   L'API si occupa di escapare i caratteri necessari e restituirà il documento di azione completo.

Puoi combinare più azioni generando differenti step e assemblarli in un'unica struttura JSON da
salvare nel campo `parameters` della configurazione.

### Aggiornamento via API delle azioni di scraping

Oltre al classico `POST /scraping-targets`, l'API espone ora un endpoint dedicato alla gestione del
JSON delle azioni associate a un target esistente:

```http
PUT /scraping-targets/{id}/actions
Authorization: Bearer <token admin>
Content-Type: application/json

{
  "actions": [
    {"action": "click", "selector": "#submit-login"},
    {"action": "fill", "selector": "input[name=email]", "value": "demo@example.com"}
  ],
  "parameters": {
    "settle_ms": 750
  }
}
```

Il corpo della richiesta accetta una lista di step (con la chiave obbligatoria `action`) e un oggetto
`parameters` opzionale usato per unire ulteriori impostazioni (ad esempio `settle_ms`). L'array di
azioni viene sostituito integralmente nel record e la risposta restituisce la rappresentazione
aggiornata del target, così da avere conferma immediata delle modifiche applicate.

Quando uno step `fill` non specifica esplicitamente il testo da inserire, l'esecuzione prova a
ricavare email e password dal database: il sistema usa le credenziali dell'utente che ha avviato
lo scraping (se presenti), altrimenti ricade su quelle associate al target.

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
│   │   └── utils.py
│   ├── core
│   │   ├── auth.py
│   │   ├── config.py
│   │   ├── logging.py
│   │   └── security.py
│   ├── db
│   │   ├── base.py
│   │   ├── init_db.py
│   │   └── models.py
│   ├── routers
│   │   ├── auth.py
│   │   ├── me.py
│   │   ├── reports.py
│   │   └── users.py
│   ├── schemas
│   │   ├── auth.py
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
