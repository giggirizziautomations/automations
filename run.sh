#!/usr/bin/env bash
set -euo pipefail

COMMAND=${1:-help}
shift || true

case "$COMMAND" in
  init-db)
    python -m app.db.init_db "$@"
    ;;
  keygen)
    python -m app.cli.keygen "$@"
    ;;
  jwt-keygen)
    python -m app.cli.jwt_keygen "$@"
    ;;
  create-admin)
    python -m app.cli.create_admin "$@"
    ;;
  create-client)
    python -m app.cli.create_client "$@"
    ;;
  aad-login)
    python -m app.cli.msal_device_login "$@"
    ;;
  aad-login-playwright)
    python -m app.cli.msal_device_playwright "$@"
    ;;
  server)
    uvicorn app.main:app --reload "$@"
    ;;
  test)
    pytest "$@"
    ;;
  *)
    cat <<USAGE
Usage: $0 <command> [args]

Commands:
  init-db         Inizializza il database SQLite
  keygen          Genera e salva una chiave Fernet
  jwt-keygen      Genera e salva un secret JWT
  create-admin    Crea un utente amministratore
  create-client   Crea un client per il grant client_credentials
  aad-login       Avvia il device code flow MSAL dal terminale
  aad-login-playwright
                  Avvia il device code flow MSAL aprendo il browser con Playwright
  server          Avvia il server di sviluppo (uvicorn --reload)
  test            Esegue la suite di test (pytest)
USAGE
    ;;
 esac
