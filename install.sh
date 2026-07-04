#!/bin/bash
set -euo pipefail

REPO_URL="${DESPAMIZER_REPO_URL:-https://github.com/iam-sayco/despamizer.git}"
INSTALL_DIR="${DESPAMIZER_INSTALL_DIR:-$HOME/despamizer}"
SKIP_START="${DESPAMIZER_INSTALL_SKIP_START:-false}"

log() {
    echo "[despamizer-install] $*"
}

fail() {
    echo "[despamizer-install] ERROR: $*" >&2
    exit 1
}

require_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        fail "$2"
    fi
}

require_command git "Git is required. Install Git before running Despamizer."
require_command docker "Docker is required. Install Docker before running Despamizer."

if ! docker compose version >/dev/null 2>&1; then
    fail "Docker Compose is required. Install the Docker Compose plugin before running Despamizer."
fi

if [ ! -f docker-compose.yml ] || [ ! -f config.example.yaml ]; then
    if [ ! -d "$INSTALL_DIR" ]; then
        log "Cloning $REPO_URL into $INSTALL_DIR"
        git clone "$REPO_URL" "$INSTALL_DIR"
    else
        log "Using existing install directory: $INSTALL_DIR"
    fi
    cd "$INSTALL_DIR"
fi

[ -f docker-compose.yml ] || fail "docker-compose.yml not found. Run this script inside the repo or set DESPAMIZER_INSTALL_DIR."
[ -f config.example.yaml ] || fail "config.example.yaml not found."
[ -f .env.default ] || fail ".env.default not found."

if [ ! -f config.yaml ]; then
    cp config.example.yaml config.yaml
    log "Created config.yaml from config.example.yaml"
else
    log "Keeping existing config.yaml"
fi

if [ ! -f .env ]; then
    cp .env.default .env
    log "Created .env from .env.default"
else
    log "Keeping existing .env"
fi

if grep -Eq 'imap\.example\.com|password:[[:space:]]*change-me' config.yaml; then
    log "Bootstrap complete: $(pwd)"
    log "Edit config.yaml with real mailbox credentials, then run: ./install.sh"
    exit 0
fi

if [ "$SKIP_START" = "true" ]; then
    log "Start skipped because DESPAMIZER_INSTALL_SKIP_START=true"
    exit 0
fi

log "Starting Docker Compose stack"
docker compose up -d --build
