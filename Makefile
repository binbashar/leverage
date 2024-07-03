.PHONY: help build
LEVERAGE_TESTING_IMAGE := binbash/leverage-cli-testing
LEVERAGE_TESTING_TAG   := 2.5.0
LEVERAGE_IMAGE_TAG     := 1.2.7-0.0.5
PYPROJECT_FILE := pyproject.toml
INIT_FILE := leverage/__init__.py
PLACEHOLDER := 0.0.0

# Detect OS
UNAME_S := $(shell uname -s)

# Default tools
SED := sed
SORT := sort

ifeq ($(UNAME_S),Darwin)
    # Ensuring commands are compatible and errors are handled gracefully
    SED := $(shell if command -v gsed >/dev/null 2>&1; then echo 'gsed'; else echo 'sed'; fi)
    SORT := $(shell if command -v gsort >/dev/null 2>&1; then echo 'gsort'; else echo 'sort'; fi)
endif

RELEASE_VERSION ?= $(shell curl -sL "https://pypi.org/pypi/leverage/json" | jq -r ".releases | keys[]" | $(SORT) -V | tail -n 1 | awk 'BEGIN{FS="[.-]"} {if ($$4 ~ /^rc[0-9]+$$/) {rc=substr($$4,3)+1} else {rc=0}; print $$1"."$$2"."$$3"-rc"rc}')

help:
	@echo 'Available Commands:'
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | $(SORT) | awk 'BEGIN {FS = ":.*?## "}; {printf " - \033[36m%-18s\033[0m %s\n", $$1, $$2}'

build-image: ## Build docker image for testing
	docker build . -t ${LEVERAGE_TESTING_IMAGE}:${LEVERAGE_TESTING_TAG}

test-unit: ## Run unit tests and create a coverage report
	docker run --rm --privileged --mount type=bind,src=$(shell pwd),dst=/leverage -t ${LEVERAGE_TESTING_IMAGE}:${LEVERAGE_TESTING_TAG} pytest --verbose --cov=./ --cov-report=xml

test-unit-no-cov: ## Run unit tests with no coverage report
	docker run --rm --privileged --mount type=bind,src=$(shell pwd),dst=/leverage -t ${LEVERAGE_TESTING_IMAGE}:${LEVERAGE_TESTING_TAG} pytest --verbose --no-cov

test-int: ## Run integration tests
	docker run --rm --privileged --mount type=bind,src=$(shell pwd),dst=/leverage --env LEVERAGE_IMAGE_TAG=${LEVERAGE_IMAGE_TAG} -t ${LEVERAGE_TESTING_IMAGE}:${LEVERAGE_TESTING_TAG} bash -c "bats --verbose-run --show-output-of-passing-tests --print-output-on-failure -T -t -p -r tests/bats"

tests: test-unit-no-cov test-int ## Run full set of tests

setup: ## Set up requirements
	poetry install --with=dev --with=main

clean: ## Clean build files
	rm -rf ./build/
	rm -rf ./dist/

build: clean ## Build distributables
	poetry build

check: ## Check distributables
	poetry run twine check dist/*

push: ## Push distributables to PyPi
	poetry run twine upload --repository-url https://upload.pypi.org/legacy/ dist/*

push-ci: ## Push distributables to PyPi (to be used in CI)
	poetry run twine upload --non-interactive --repository-url https://upload.pypi.org/legacy/ dist/*

push-test: ## Push distributables to Pypi test
	poetry run twine upload --repository testpypi dist/*

bump-test-version: ## Bump version based on PyPI latest release or provided input
	@echo "[INFO] Get current version from leverage/__init__.py"
	$(eval CURRENT_VERSION=$(shell awk '/__version__/ {print $$3}' $(INIT_FILE) | tr -d '"' | tr -d "'"))
	@echo "[INFO] Current version from project files: $(CURRENT_VERSION)"

	@echo "[INFO] Fetching the latest version from PyPI."
	$(eval LATEST_VERSION=$(shell curl -sL "https://pypi.org/pypi/leverage/json" | jq -r ".releases | keys[]" | $(SORT) -V | tail -n 1))
	@echo "[INFO] Latest version fetched from PyPI: $(LATEST_VERSION)"

	# Get the latest RC version from PyPI if it exists
	$(eval LATEST_RC_VERSION=$(shell curl -sL "https://pypi.org/pypi/leverage/json" | jq -r ".releases | keys[]" | grep "$(LATEST_VERSION)-rc" | $(SORT) -V | tail -n 1))

ifeq ($(strip $(RELEASE_VERSION)),)
	@echo "[INFO] RELEASE_VERSION not provided. Generating new RC version."
	$(eval BASE_VERSION=$(shell echo $(LATEST_VERSION) | awk 'BEGIN{FS="-"} {print $$1}'))
	$(eval RC_VERSION=$(shell echo $(LATEST_RC_VERSION) | awk 'BEGIN{FS="-rc"} {if (NF > 1) {print $$2} else {print "0"}}'))
	$(eval NEXT_RC_VERSION=$(shell echo $(RC_VERSION) | awk '{print $$1+1}'))
	$(eval RELEASE_VERSION=$(BASE_VERSION)-rc$(NEXT_RC_VERSION))
	@echo "[INFO] Current version from PyPI: $(LATEST_VERSION)"
	@echo "[INFO] Creating new RC version: $(RELEASE_VERSION)"
else
	@echo "[INFO] RELEASE_VERSION provided as argument: $(RELEASE_VERSION)"
	@echo "[INFO] Checking if provided RELEASE_VERSION is valid..."
	$(eval PROVIDED_BASE_VERSION=$(shell echo $(RELEASE_VERSION) | awk 'BEGIN{FS="-"} {print $$1}'))
	$(eval PROVIDED_RC_VERSION=$(shell echo $(RELEASE_VERSION) | awk 'BEGIN{FS="-rc"} {if (NF > 1) {print $$2} else {print "0"}}'))
	@echo "[INFO] Current base version from PyPI: $(LATEST_VERSION)"
	@echo "[INFO] Provided base version: $(PROVIDED_BASE_VERSION)"
	@echo "[INFO] Provided RC version: $(PROVIDED_RC_VERSION)"
	@echo "[INFO] Latest RC version from PyPI: $(LATEST_RC_VERSION)"
	@if [ -z "$(LATEST_RC_VERSION)" ]; then \
		if [ "$(PROVIDED_RC_VERSION)" != "0" ]; then \
			echo "[ERROR] Provided RC version is invalid as there are no existing RC versions in PyPI. Exiting..."; \
			exit 1; \
		else \
			echo "[INFO] Provided RC version is valid."; \
		fi \
	else \
		if [ "$(PROVIDED_RC_VERSION)" -le "$(shell echo $(LATEST_RC_VERSION) | sed 's/.*-rc//')" ]; then \
			echo "[INFO] Provided RC version is valid."; \
		else \
			echo "[ERROR] Provided RC version is invalid as it does not follow the latest RC version from PyPI. Exiting..."; \
			exit 1; \
		fi \
	fi
endif

	@echo "[INFO] Testing version syntax patterns..."
	@echo $(RELEASE_VERSION) | awk '/^[0-9]+\.[0-9]+\.[0-9]+-rc[0-9]+$$/ {print "[INFO] Version ok"}' || (echo "[ERROR] Invalid format for RELEASE_VERSION. Expected format: ^[0-9]+\.[0-9]+\.[0-9]+-rc[0-9]+$$" && exit 1)

	@echo "[INFO] Bumping RC version to $(RELEASE_VERSION)"
	@$(SED) -i 's/__version__ = "$(CURRENT_VERSION)"/__version__ = "$(RELEASE_VERSION)"/' $(INIT_FILE)
	@$(SED) -i 's/version = "$(CURRENT_VERSION)"/version = "$(RELEASE_VERSION)"/' $(PYPROJECT_FILE)

bump-version-ci: ## Fetch latest tag, update versions in __init__.py and pyproject.toml
	@echo "[INFO] Get latest tag"
	$(eval RELEASE_VERSION=$(shell git fetch --all --tags && git tag --sort=version:refname | tail -n 1 | sed 's/v//'))
	@echo $(RELEASE_VERSION)

	@echo "[INFO] Write version to __init__.py"
	@$(SED) -i 's/$(PLACEHOLDER)/$(RELEASE_VERSION)/' $(INIT_FILE)

	@echo "[INFO] Update version in pyproject.toml"
	@$(SED) -i 's/version = ".*"/version = "$(RELEASE_VERSION)"/' $(PYPROJECT_FILE)
