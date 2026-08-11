# Configurable variables
PROJECT_ID ?= $(shell gcloud config get-value project 2>/dev/null)
LOCATION ?= us-central1
STAGING_BUCKET ?= 
SERVICE_NAME ?= code-review-agent
IMAGE_TAG ?= gcr.io/$(PROJECT_ID)/$(SERVICE_NAME):latest

.PHONY: help install test eval dev deploy-agent-engine deploy-cloud-run

help: ## Show this help message
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install project dependencies locally
	pip install -e .[dev]

test: ## Run local pytest test suite
	python3 -m pytest tests/ -v

eval: ## Execute the automated evaluation/regression suite
	PYTHONPATH=src python3 tests/run_eval_suite.py

dev: ## Start the ADK web server locally for interactive UI testing
	python3 -m google.adk.cli.cli web --session_service_uri=sqlite:///agent_sessions.db --port=8000 src/code_review_agent

deploy-agent-engine: ## Deploy the agent to Vertex AI Agent Engine (Reasoning Engine)
	@if [ -z "$(PROJECT_ID)" ] || [ -z "$(STAGING_BUCKET)" ]; then \
		echo "Error: PROJECT_ID and STAGING_BUCKET variables must be set."; \
		exit 1; \
	fi
	@echo "🧠 Deploying agent to Vertex AI Reasoning Engine..."
	python3 deployment/deploy_agent_engine.py --project $(PROJECT_ID) --location $(LOCATION) --bucket $(STAGING_BUCKET)

deploy-cloud-run: ## Deploy the agent as a containerized service to Cloud Run
	@if [ -z "$(PROJECT_ID)" ]; then \
		echo "Error: PROJECT_ID variable must be set."; \
		exit 1; \
	fi
	@echo "📦 Building container image..."
	gcloud builds submit --tag $(IMAGE_TAG) .
	@echo "🚀 Deploying to Cloud Run via Terraform..."
	cd deployment/terraform && \
		terraform init && \
		terraform apply -var="project_id=$(PROJECT_ID)" -var="image_url=$(IMAGE_TAG)" -var="service_name=$(SERVICE_NAME)" -var="region=$(LOCATION)" -auto-approve
