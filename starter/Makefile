# ==============================================================================
# 🤖 Rasa Always-On AI Coworker — Hackathon Starter
# ==============================================================================
GREEN   := $(shell tput -Txterm setaf 2)
YELLOW  := $(shell tput -Txterm setaf 3)
BLUE    := $(shell tput -Txterm setaf 4)
MAGENTA := $(shell tput -Txterm setaf 5)
RED     := $(shell tput -Txterm setaf 1)
RESET   := $(shell tput -Txterm sgr0)

VENV   := .venv
PYTHON := ./$(VENV)/bin/python
RASA   := $(PYTHON) -m rasa
UV     := $(shell which uv)

ifneq (,$(wildcard .env))
    include .env
    export
endif

.DEFAULT_GOAL := help

# ==============================================================================
.PHONY: help
help: ## Show this help
	@echo ''
	@echo '$(MAGENTA)🤖 Rasa AI Coworker — Hackathon Starter$(RESET)'
	@echo ''
	@echo '$(YELLOW)Setup (once):$(RESET)'
	@echo '  $(GREEN)make install$(RESET)         Create .venv and install (Rasa + voice client)'
	@echo '  $(GREEN)make verify$(RESET)          Check API keys + service connectivity'
	@echo '  $(GREEN)make train$(RESET)           Train the assistant (Level 1: flows + voice)'
	@echo '  $(GREEN)make generate-audio$(RESET)  Pre-generate the demo user voice clips'
	@echo ''
	@echo '$(YELLOW)Run — Level 1 (3 terminals):$(RESET)'
	@echo '  $(GREEN)make run-actions$(RESET)     Tab 1 — action server'
	@echo '  $(GREEN)make run-rasa$(RESET)        Tab 2 — Rasa server'
	@echo '  $(GREEN)make demo$(RESET)            Tab 3 — voice loop  (or $(GREEN)make demo-text$(RESET))'
	@echo ''
	@echo '$(YELLOW)Run — Level 2 agentic (4 terminals):$(RESET)'
	@echo '  $(GREEN)make install-agentic$(RESET) Add the MCP server dependency'
	@echo '  $(GREEN)make train-agentic$(RESET)   Train with the ops_assistant sub-agent'
	@echo '  $(GREEN)make run-mcp$(RESET)         Tab 0 — MCP tool server'
	@echo '  $(GREEN)make run-actions$(RESET)     Tab 1'
	@echo '  $(GREEN)make run-rasa-agentic$(RESET) Tab 2 — Rasa with the sub-agent'
	@echo '  $(GREEN)make demo-text$(RESET)       Tab 3'
	@echo ''
	@echo '$(YELLOW)Dev:$(RESET)'
	@echo '  $(GREEN)make inspect$(RESET)         Interactive Rasa shell'
	@echo '  $(GREEN)make test$(RESET)            Run e2e tests (stubbed actions)'
	@echo '  $(GREEN)make clean$(RESET)           Remove models, caches, audio'
	@echo ''

# ==============================================================================
.PHONY: check-uv
check-uv:
	@if [ -z "$(UV)" ]; then \
		echo "$(RED)✗ uv not found. Install from https://github.com/astral-sh/uv$(RESET)"; \
		exit 1; \
	fi

.PHONY: install
install: check-uv ## Install Rasa + voice client into .venv
	@echo "$(BLUE)Creating .venv and installing...$(RESET)"
	$(UV) venv $(VENV)
	$(UV) pip install pip setuptools
	$(UV) pip install -e ".[voice]"
	@echo "$(GREEN)✓ Installed. (Rasa Pro needs a license — see .env / hello.rasa.ai)$(RESET)"

.PHONY: install-agentic
install-agentic: check-uv ## Add the MCP server dependency for Level 2
	$(UV) pip install -e ".[voice,mcp]"
	@echo "$(GREEN)✓ Agentic deps installed.$(RESET)"

.PHONY: verify
verify: ## Pre-flight: keys + service connectivity
	$(PYTHON) scripts/verify_setup.py

.PHONY: generate-audio
generate-audio: ## Pre-generate demo user voice clips (Speechmatics TTS)
	$(PYTHON) -m voice.generate_audio

# ==============================================================================
.PHONY: train
train: ## Train Level 1 (flows + actions, no sub-agent)
	@echo "$(BLUE)Training (Level 1)...$(RESET)"
	$(RASA) train

.PHONY: train-agentic
train-agentic: ## Train Level 2 (adds the ops_assistant sub-agent + its flow)
	@echo "$(BLUE)Training (Level 2 — agentic)...$(RESET)"
	$(RASA) train --data data agentic/flows --sub-agents agentic/sub_agents

# ==============================================================================
.PHONY: run-actions
run-actions: ## Tab 1: action server
	@echo "$(MAGENTA)Action server on :5055...$(RESET)"
	RASA_SDK_LOG_LEVEL=INFO $(RASA) run actions

.PHONY: run-rasa
run-rasa: ## Tab 2: Rasa server (Level 1)
	@echo "$(MAGENTA)Rasa on :5005...$(RESET)"
	$(RASA) run --enable-api --cors "*"

.PHONY: run-rasa-agentic
run-rasa-agentic: ## Tab 2: Rasa server with the sub-agent loaded (Level 2)
	@echo "$(MAGENTA)Rasa on :5005 with sub-agents...$(RESET)"
	$(RASA) run --enable-api --cors "*" --sub-agents agentic/sub_agents

.PHONY: run-mcp
run-mcp: ## Tab 0: MCP tool server (Level 2)
	@echo "$(BLUE)MCP tool server on :8000...$(RESET)"
	$(PYTHON) agentic/servers/ops_mcp_server/server.py

.PHONY: run-heartbeat
run-heartbeat: ## Tab 0.5: Run the heartbeat monitor
	@echo "$(BLUE)Starting heartbeat monitor...$(RESET)"
	$(PYTHON) scripts/heartbeat.py

# ==============================================================================
.PHONY: demo
demo: ## Tab 3: full voice loop (run `make generate-audio` first)
	$(PYTHON) -m voice.demo

.PHONY: demo-text
demo-text: ## Tab 3: text-only loop (no audio needed)
	$(PYTHON) -m voice.demo --text

.PHONY: inspect
inspect: ## Interactive Rasa shell
	$(RASA) inspect

.PHONY: test
test: ## Run e2e tests with stubbed custom actions
	RASA_PRO_BETA_STUB_CUSTOM_ACTION=true $(RASA) test e2e tests/e2e

.PHONY: clean
clean: ## Remove models, caches, generated audio
	@echo "$(YELLOW)Cleaning...$(RESET)"
	rm -rf .rasa models results voice/audio
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	@echo "$(GREEN)✓ Clean.$(RESET)"
