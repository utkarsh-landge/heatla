# HEATLA. `make all` rebuilds every table, figure and model from scratch.
PY := .venv/bin/python
PIP := .venv/bin/pip

.PHONY: all setup mock real fetch test figures dashboard deploy clean distclean

all: setup mock test

setup: .venv/.installed

.venv/.installed: requirements.txt pyproject.toml
	python3.12 -m venv .venv 2>/dev/null || python3 -m venv .venv
	$(PIP) install -q --upgrade pip
	$(PIP) install -q -r requirements.txt
	$(PIP) install -q -e . --no-deps
	@touch $@

# Full pipeline on the synthetic county. Runs anywhere, no credentials.
mock: setup
	$(PY) -m heatla.run_all --data-mode mock

# Same pipeline against real data in data/raw (see data/README.md).
real: setup
	$(PY) -m heatla.run_all --data-mode real

# Download every public source that needs no credentials.
fetch: setup
	$(PY) -m heatla.fetch_real

test: setup
	$(PY) -m pytest tests -q

# Quick pass used by CI: small K grid, one radius, fewer random draws.
ci: setup
	$(PY) -m heatla.run_all --data-mode mock --quick
	$(PY) -m pytest tests -q

dashboard:
	cd dashboard && npm install && npm run build

dashboard-dev:
	cd dashboard && npm install && npm run dev

deploy: dashboard
	cd dashboard && npx vercel --prod

clean:
	rm -rf reports/figures/* reports/tables/* data/processed/* \
	       dashboard/public/data/* reports/run_manifest.json

distclean: clean
	rm -rf .venv data/raw/* dashboard/node_modules dashboard/dist
