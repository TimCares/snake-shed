PY=uv


# Vulnerabilities acknowledged and accepted (no fix available or not applicable)
# Add an ignore with e.g. "--ignore-vuln CVE-XXXX-XXXX "
PIP_AUDIT_IGNORE ?= --ignore-vuln PYSEC-2022-42969

PYTEST_ARGS ?=
PYTEST_COV_REPORT_ARGS ?= --cov-report=xml

.DEFAULT_GOAL := help

# =============================================================================
# Help
# =============================================================================

help:  ## Show this help message
	@echo "Makefile Commands"
	@echo "=============================="
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; $$1 != "teardown" {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@grep -E '^teardown:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "\033[31m%-20s\033[0m %s\n", $$1, $$2}'

# ============================================================================
# Setup and Installation
# ============================================================================

# `bootstrap` is the single command a fresh clone needs to be productive.
# On the very first run it also executes `scripts/bootstrap_template.py`,
# which renames the placeholder package to one derived from the directory
# name (or whatever the user types at the prompt). That script self-deletes
# afterwards — re-running `make bootstrap` later just (re)installs deps and
# pre-commit hooks, which is what you usually want.
.PHONY: bootstrap
bootstrap:  ## One-time project init (template rename, on first run) + dev environment setup
	@if [ -f scripts/bootstrap_template.py ]; then \
		$(PY) run --no-project --script scripts/bootstrap_template.py; \
	fi
	$(PY) python install $$(cat .python-version)
	$(MAKE) install-dev
	$(MAKE) pre-commit-install

.PHONY: install
install:  ## Install only production dependencies
	$(PY) sync

.PHONY: install-dev
install-dev:  ## Install production + development dependencies
	$(PY) sync --dev

.PHONY: pre-commit-install
pre-commit-install:  ## Install pre-commit hooks
	$(PY) run pre-commit install

# =============================================================================
# Code Quality
# =============================================================================

.PHONY: format-check
format-check: ## Check code formatting without changes
	$(PY) run ruff format --check .

.PHONY: format
format: ## Format code (ruff)
	$(PY) run ruff format .

.PHONY: lint-check
lint-check: ## Run linter check (ruff)
	$(PY) run ruff check .

.PHONY: lint
lint: ## Run linter and auto-fix issues
	$(PY) run ruff check --fix .

.PHONY: type-check
type-check:  ## Type check with ty
	$(PY) run ty check

.PHONY: docstring-check
docstring-check: ## Check docstring coverage
	$(PY) run interrogate -v

.PHONY: repo-check
repo-check: ## Run repository hygiene checks from pre-commit
	$(PY) run pre-commit run check-yaml --all-files
	$(PY) run pre-commit run check-toml --all-files
	$(PY) run pre-commit run check-added-large-files --all-files
	$(PY) run pre-commit run check-merge-conflict --all-files
	$(PY) run pre-commit run debug-statements --all-files

# =============================================================================
# Testing
# =============================================================================

.PHONY: test
test:  ## Run tests with pytest
	$(PY) run pytest $(PYTEST_ARGS)

.PHONY: test-cov
test-cov:  ## Run tests with coverage report
	$(PY) run pytest --cov --cov-report=term-missing $(PYTEST_COV_REPORT_ARGS) $(PYTEST_ARGS)

# ============================================================================
# Security
# ============================================================================

.PHONY: audit
audit:  ## Audit dependencies for known vulnerabilities (ignores defined in PIP_AUDIT_IGNORE)
	$(PY) run pip-audit $(PIP_AUDIT_IGNORE)

.PHONY: find-secrets
find-secrets:  ## Scan for secrets with gitleaks (uses .gitleaks.toml)
	$(PY) run pre-commit run gitleaks --all-files

.PHONY: trivy
trivy:  ## Scan for vulnerabilities with trivy (uses trivy.yaml)
	docker run --rm -v "$(PWD):/repo" -w /repo ghcr.io/aquasecurity/trivy:latest fs .

# ============================================================================
# Full check (omits trivy because of large DB used by trivy)
# ============================================================================

.PHONY: check
check: repo-check format-check lint-check type-check docstring-check test-cov audit find-secrets  ## Run the full local validation suite

# ============================================================================
# Version
# ============================================================================

.PHONY: version
version:  ## Show current version
	@$(PY) run python -c "import tomllib; print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])"

# ============================================================================
# Cleanup
# ============================================================================

.PHONY: clean clean-all teardown
clean:  ## Remove local build, test, and cache artifacts
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type f -name "*.log" -delete
	rm -rf .cache .hypothesis .nox .pytest_cache .ruff_cache .tox
	rm -rf .uv-cache .eggs build dist htmlcov sdist
	rm -f .coverage coverage.xml report.xml release.env

clean-all: clean  ## Remove cache files and virtual environment
	rm -rf .venv/

# `teardown` is the inverse of `bootstrap`'s *environment* setup only — it
# removes the venv, pre-commit hook, and pinned Python toolchain.
teardown:  ## Remove dev environment (venv, pre-commit hook, pinned Python).
	$(PY) run pre-commit uninstall
# clean-all needs to run after "pre-commit uninstall" because uv creates .venv when "pre-commit uninstall" runs
	$(MAKE) clean-all
	$(PY) python uninstall $$(cat .python-version)
