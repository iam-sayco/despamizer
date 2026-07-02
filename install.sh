#!/bin/bash
set -euo pipefail

if ! command -v docker >/dev/null 2>&1; then
    echo "ERROR: Docker is required. Install Docker before running Despamizer." >&2
    exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
    echo "ERROR: Docker Compose is required. Install the Docker Compose plugin before running Despamizer." >&2
    exit 1
fi

if [ ! -f config.yaml ]; then
    echo "ERROR: config.yaml is missing. Create it from config.example.yaml first." >&2
    exit 1
fi

if [ ! -f .env.default ]; then
    echo "ERROR: .env.default is missing. Runtime defaults are required." >&2
    exit 1
fi

docker compose up -d --build
