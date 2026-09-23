.DEFAULT_GOAL := help
ENV ?= dev
TF_DIR := infra/terraform/envs/$(ENV)

.PHONY: help install lint format test cov run-local local-db build tf-fmt tf-validate tf-init tf-plan tf-apply tf-bootstrap smoke rollback clean

help: ## Show targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Create venv and install all dependencies
	uv sync

lint: ## Ruff lint + format check + mypy
	uv run ruff check src tests scripts
	uv run ruff format --check src tests scripts
	uv run mypy

format: ## Auto-format
	uv run ruff format src tests scripts
	uv run ruff check --fix src tests scripts

test: ## Unit + integration tests (moto)
	uv run pytest

cov: ## Tests with coverage report
	uv run pytest --cov=projects_api --cov-report=term-missing

local-db: ## Start DynamoDB Local and create the table
	docker compose up -d dynamodb
	AWS_ACCESS_KEY_ID=local AWS_SECRET_ACCESS_KEY=local uv run python scripts/create_local_table.py

run-local: ## Run the API locally against DynamoDB Local (see docs: X-Api-Key-Id header = identity)
	ENV=local TABLE_NAME=projects-local DYNAMODB_ENDPOINT=http://localhost:8000 \
	AWS_ACCESS_KEY_ID=local AWS_SECRET_ACCESS_KEY=local \
	uv run uvicorn projects_api.main:app --reload --port 8080

build: ## Build build/lambda.zip (python3.12, arm64)
	scripts/build_lambda.sh

tf-fmt: ## terraform fmt check
	terraform fmt -check -recursive infra/terraform

tf-validate: ## terraform validate (no backend, no credentials)
	cd infra/terraform/bootstrap && terraform init -backend=false -input=false >/dev/null && terraform validate
	cd $(TF_DIR) && terraform init -backend=false -input=false >/dev/null && terraform validate

tf-bootstrap: ## One-off: create state bucket and lock table (STATE_BUCKET required)
	cd infra/terraform/bootstrap && terraform init -input=false && terraform apply -var="state_bucket_name=$(STATE_BUCKET)"

tf-init: ## terraform init with S3 backend (copy backend.example.hcl to backend.hcl first)
	cd $(TF_DIR) && terraform init -input=false -backend-config=backend.hcl

tf-plan: build ## terraform plan for ENV
	cd $(TF_DIR) && terraform plan -input=false -var-file=$(ENV).tfvars -out=tfplan

tf-apply: ## terraform apply the saved plan for ENV
	cd $(TF_DIR) && terraform apply -input=false tfplan

smoke: ## Smoke test the deployed ENV
	ENV=$(ENV) tests/smoke/smoke.sh

rollback: ## Repoint the live Lambda alias to an earlier version (ARGS="--version N --yes --dry-run")
	ENV=$(ENV) scripts/rollback.sh --env $(ENV) $(ARGS)

clean: ## Remove build artefacts
	rm -rf build .pytest_cache .ruff_cache .mypy_cache .coverage
