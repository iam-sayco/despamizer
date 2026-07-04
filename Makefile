MAILBOX ?=

.PHONY: help
help:
	@echo "Despamizer commands:"
	@echo "  make install              Bootstrap local files and start the stack"
	@echo "  make run                  Pull, build, and recreate the Docker Compose stack"
	@echo "  make probe MAILBOX=name   List IMAP folders for a configured mailbox"
	@echo "  make run-once             Run one worker cycle using current .env"
	@echo "  make dry-run              Run one forced dry-run worker cycle"
	@echo "  make logs                 Follow despamizer logs"
	@echo "  make restart              Restart the despamizer worker container"
	@echo "  make stop                 Stop and remove the Docker Compose stack"
	@echo "  make rebuild              Rebuild images after dependency or Dockerfile changes"
	@echo "  make lint                 Run Ruff in Docker"
	@echo "  make test                 Run tests in Docker"
	@echo "  make check                Run lint and tests in Docker"
	@echo "  make lock                 Refresh poetry.lock in Docker"

.PHONY: install
install:
	./install.sh

.PHONY: run
run:
	docker compose pull --ignore-pull-failures
	docker compose up -d --build --force-recreate

.PHONY: probe
probe:
	@test -n "$(MAILBOX)" || (echo "Usage: make probe MAILBOX=personal" >&2; exit 1)
	docker compose run --rm --no-deps despamizer poetry run python -m despamizer folders "$(MAILBOX)"

.PHONY: run-once
run-once:
	docker compose run --rm despamizer poetry run python -m despamizer --vvv once

.PHONY: dry-run
dry-run:
	docker compose run --rm despamizer poetry run python -m despamizer --vvv --run-dry once

.PHONY: logs
logs:
	docker compose logs -f despamizer

.PHONY: restart
restart:
	docker compose restart despamizer

.PHONY: stop
stop:
	docker compose down

.PHONY: rebuild
rebuild:
	docker compose up -d --build

.PHONY: lint
lint:
	docker compose --profile dev run --rm --no-deps despamizer-dev poetry run ruff check .

.PHONY: test
test:
	docker compose --profile dev run --rm --no-deps despamizer-dev poetry run pytest

.PHONY: check
check:
	docker compose --profile dev run --rm --no-deps despamizer-dev sh -lc 'poetry run ruff check . && poetry run pytest'

.PHONY: lock
lock:
	docker compose --profile dev run --rm --no-deps despamizer-dev poetry lock
