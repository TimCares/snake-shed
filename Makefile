PY=uv

.PHONY: help
help:  ## Show this help message
	@echo "Makefile Commands"
	@echo "=============================="
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ============================================================================
# Setup and Installation
# ============================================================================

.PHONY: bootstrap
bootstrap:  ## Initial project setup (install Python, create venv, sync all deps)
	$(PY) python install $$(cat .python-version)
	$(PY) venv
	$(PY) sync --group dev

.PHONY: install
install:  ## Install only production dependencies
	$(PY) sync

.PHONY: install-dev
install-dev:  ## Install production + development dependencies
	$(PY) sync --group dev

.PHONY: pre-commit-install
pre-commit-install:  ## Install pre-commit hooks
	$(PY) run pre-commit install --hook-type commit-msg --hook-type pre-commit

# ============================================================================
# Development Workflow
# ============================================================================

.PHONY: test
test:  ## Run tests with pytest
	$(PY) run pytest

.PHONY: test-cov
test-cov:  ## Run tests with coverage report
	$(PY) run pytest --cov --cov-report=term-missing

.PHONY: lint
lint:  ## Lint code with ruff
	$(PY) run ruff check .

.PHONY: lint-fix
lint-fix:  ## Lint and auto-fix issues with ruff
	$(PY) run ruff check --fix .

.PHONY: type
type:  ## Type check with pyright
	$(PY) run pyright

.PHONY: format-check
format-check:  ## Check code formatting with ruff
	$(PY) run ruff format --check .

.PHONY: format
format:  ## Format code with ruff
	$(PY) run ruff format .

.PHONY: audit
audit:  ## Audit dependencies for known vulnerabilities
	$(PY) run pip-audit --ignore-vuln PYSEC-2022-42969 # ignore python-semantic-release vulnerability, only affects development

.PHONY: docstring-cov
docstring-cov:  ## Check docstring coverage with interrogate
	$(PY) run interrogate src/

.PHONY: check
check: format-check lint type docstring-cov test audit  ## Run all checks

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
clean:  ## Remove Python cache files
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
	find . -type f -name "*.log" -delete

clean-all: clean  ## Remove cache files and virtual environment
	rm -rf .venv/
