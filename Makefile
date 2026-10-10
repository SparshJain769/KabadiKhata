export PYTHONPATH := src

# Settings and keys live in .env (copied from .env.example on first run)
ifneq (,$(wildcard .env))
include .env
export
endif

.PHONY: install test api seed demo tamper sam-invoke up down reindex bot console smoke

install: .env
	uv sync --extra dev --extra product --extra product

.env:
	cp .env.example .env
	@echo "Created .env from .env.example (MOCK_LLM=1: no API key needed). Add keys there for the real LLM."

test:
	MOCK_LLM=1 uv run pytest -q

api:
	uv run uvicorn api.app:app --port 3000 --reload

# The bot talks to the real API here (its own default is the mock)
bot:
	KK_USE_MOCK=0 uv run python -m bot.telegram_bot

console:
	KK_USE_MOCK=0 uv run streamlit run console/app.py --server.headless true --server.port 8501

# WhatsApp (Twilio sandbox) webhook. Talks to the real API; expose it with ngrok
# and set the sandbox webhook to https://<ngrok>/whatsapp (see docs/whatsapp_runbook.md).
whatsapp:
	KK_USE_MOCK=0 uv run uvicorn bot.whatsapp_webhook:app --port 8080 --reload

# Rebuilds data/kk.db from data/synth/world.json (P1 generates it)
seed:
	uv run python -m ledger.seed

# OpenSearch for the read-only search copy. Optional: everything else works without it.
up:
	docker compose up -d --wait

down:
	docker compose down

reindex:
	uv run python -m search.reindex

# Seeds, then starts every process in the Procfile in one terminal.
# The leading "-" on up: no Docker means no search copy, not a failed demo.
demo: install
	-$(MAKE) up
	$(MAKE) seed
	uv run honcho start

# Checks every endpoint and the 4 spine beats against a running `make demo`.
# Smoke decides a flag and adds a test kabadiwala, so it re-seeds afterwards to keep the demo pristine.
smoke:
	uv run python scripts/smoke.py; status=$$?; $(MAKE) -s seed > /dev/null; exit $$status

# Video backup for the tamper demo: make tamper COLLECTOR=kw-raju SEQ=0 KG=40
tamper:
	uv run python -m ledger.tamper $(COLLECTOR) $(SEQ) $(KG)

# The "Built on AWS" clip: build the API as an arm64 Lambda and invoke it with a collection event
sam-invoke:
	sam build --use-container
	sam local invoke KabadiKhataApi --event events/collection.json
	sam local invoke KabadiKhataApi --event events/brand-reads-receipts.json
