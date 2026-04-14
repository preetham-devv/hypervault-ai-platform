# ============================================================
# HyperVault AI Platform — Developer Makefile
#
# Prerequisites: Docker Desktop (or Docker Engine + Compose v2).
# All targets that run inside containers require the stack to
# be up first — `make dev` starts it.
#
# Quick start:
#   cp .env.local.example .env.local   # fill in your values
#   make dev                            # bring everything up
#   make test                           # run the test suite
# ============================================================

# ── Configuration ─────────────────────────────────────────────────────────────
COMPOSE         := docker compose
API_SERVICE     := api
DB_SERVICE      := db

# psql connection to the local Compose postgres (bypasses app RLS for admin use)
PSQL_SUPERUSER  := $(COMPOSE) exec $(DB_SERVICE) \
                   psql -U postgres -d hr_platform

# psql as the application user (RLS is enforced)
PSQL_APP        := $(COMPOSE) exec $(DB_SERVICE) \
                   psql -U hypervault_app -d hr_platform

.DEFAULT_GOAL   := help

# ── Help ──────────────────────────────────────────────────────────────────────
.PHONY: help
help:
	@echo ""
	@echo "HyperVault AI Platform — available targets:"
	@echo ""
	@echo "  make dev        Start all services in the foreground (hot-reload)"
	@echo "  make dev-bg     Start all services in the background (detached)"
	@echo "  make test       Run the pytest suite inside the api container"
	@echo "  make lint       Run ruff (linter) + mypy (type checker)"
	@echo "  make clean      Stop all containers and DELETE volumes (wipes DB)"
	@echo "  make stop       Stop containers without removing volumes"
	@echo "  make db-shell   Open a psql shell (superuser, RLS bypassed)"
	@echo "  make seed       Re-apply infra/seed_data.sql against the local DB"
	@echo "  make deploy     Build and push to Cloud Run via deploy_cloudrun.sh"
	@echo ""

# ── Local development ─────────────────────────────────────────────────────────

## Bring up all three services with log streaming (Ctrl-C to stop).
.PHONY: dev
dev: .env.local
	$(COMPOSE) up --build

## Same as dev but run in the background.
.PHONY: dev-bg
dev-bg: .env.local
	$(COMPOSE) up --build --detach
	@echo ""
	@echo "Services started in background:"
	@echo "  API:      http://localhost:8080"
	@echo "  Frontend: http://localhost:8501"
	@echo ""
	@echo "Follow logs:  docker compose logs -f"
	@echo "Stop:         make stop"

## Enforce .env.local exists before bringing up services.
.env.local:
	@echo ""
	@echo "ERROR: .env.local not found."
	@echo "Run:  cp .env.local.example .env.local"
	@echo "Then edit .env.local and fill in your values."
	@echo ""
	@exit 1

## Stop containers without destroying volumes.
.PHONY: stop
stop:
	$(COMPOSE) stop

# ── Testing ───────────────────────────────────────────────────────────────────

## Run the full pytest suite inside the api container.
## Pass extra arguments with ARGS=..., e.g. make test ARGS="-k test_rls -v"
.PHONY: test
test:
	$(COMPOSE) run --rm $(API_SERVICE) \
	    pytest tests/ -v --tb=short $(ARGS)

## Run tests with coverage report.
.PHONY: test-cov
test-cov:
	$(COMPOSE) run --rm $(API_SERVICE) \
	    pytest tests/ -v --tb=short \
	        --cov=src --cov-report=term-missing --cov-report=html:/app/htmlcov

# ── Linting and type checking ─────────────────────────────────────────────────

## Run ruff (fast linter) then mypy (strict type checker).
.PHONY: lint
lint:
	$(COMPOSE) run --rm $(API_SERVICE) \
	    ruff check src/ tests/
	$(COMPOSE) run --rm $(API_SERVICE) \
	    mypy src/ --ignore-missing-imports

## Auto-fix ruff lint errors where possible.
.PHONY: lint-fix
lint-fix:
	$(COMPOSE) run --rm $(API_SERVICE) \
	    ruff check src/ tests/ --fix

# ── Database ──────────────────────────────────────────────────────────────────

## Open an interactive psql shell as the postgres superuser.
## NOTE: the superuser bypasses RLS — use this for schema inspection only.
.PHONY: db-shell
db-shell:
	$(PSQL_SUPERUSER)

## Open an interactive psql shell as the application user (RLS enforced).
.PHONY: db-shell-app
db-shell-app:
	$(PSQL_APP)

## Re-apply the seed data file against the local database.
## Idempotent: uses ON CONFLICT DO NOTHING throughout seed_data.sql.
.PHONY: seed
seed:
	$(PSQL_SUPERUSER) -f /docker-entrypoint-initdb.d/02-seed.sql
	@echo "Seed data applied."

# ── Cleanup ───────────────────────────────────────────────────────────────────

## Stop containers AND remove the db_data named volume (full reset).
## WARNING: this permanently deletes your local postgres data.
.PHONY: clean
clean:
	@echo "WARNING: This will delete all local database data."
	@echo "Press Ctrl-C within 5 seconds to abort..."
	@sleep 5
	$(COMPOSE) down --volumes --remove-orphans
	@echo "All containers and volumes removed."

## Remove built images as well (forces a full rebuild on next `make dev`).
.PHONY: clean-images
clean-images: clean
	$(COMPOSE) down --rmi local

# ── Cloud Run deployment ──────────────────────────────────────────────────────

## Build the production image and deploy to Cloud Run.
## Requires GOOGLE_CLOUD_PROJECT and gcloud auth to be configured.
## Edit deploy/deploy_cloudrun.sh for Cloud Run region / service name.
.PHONY: deploy
deploy:
	@if [ -z "$$GOOGLE_CLOUD_PROJECT" ]; then \
	    echo "ERROR: GOOGLE_CLOUD_PROJECT is not set."; \
	    echo "Run: export GOOGLE_CLOUD_PROJECT=your-project-id"; \
	    exit 1; \
	fi
	chmod +x deploy/deploy_cloudrun.sh
	./deploy/deploy_cloudrun.sh
