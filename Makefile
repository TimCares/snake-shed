PY=uv
PIP_AUDIT_ARGS ?= --ignore-vuln PYSEC-2022-42969
PYTEST_ARGS ?=
PYTEST_COV_REPORT_ARGS ?= --cov-report=xml

.DEFAULT_GOAL := help

# =============================================================================
# Help
# =============================================================================

help:  ## Show this help message
	@echo "Makefile Commands"
	@echo "=============================="
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ============================================================================
# Setup and Installation
# ============================================================================

.PHONY: bootstrap
bootstrap: install-dev pre-commit-install ## Full project setup (deps + pre-commit hooks)
	$(PY) python install $$(cat .python-version)

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
type-check:  ## Type check with pyright
	$(PY) run pyright

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
# Misc
# ============================================================================

.PHONY: audit
audit:  ## Audit dependencies for known vulnerabilities
	$(PY) run pip-audit $(PIP_AUDIT_ARGS)

.PHONY: secrets-check
secrets-check: ## Scan the repository for secrets
	$(PY) run pre-commit run gitleaks --all-files

# ============================================================================
# Full check
# ============================================================================

.PHONY: check
check: repo-check format-check lint-check type-check docstring-check test-cov audit secrets-check  ## Run the full local validation suite

# ============================================================================
# Version
# ============================================================================

.PHONY: version
version:  ## Show current version
	@$(PY) run python -c "import tomllib; print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])"

# ============================================================================
# Cleanup
# ============================================================================

.PHONY: clean clean-all
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
