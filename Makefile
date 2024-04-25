.PHONY: help build
LEVERAGE_TESTING_IMAGE := binbash/leverage-cli-testing
LEVERAGE_TESTING_TAG   := 2.5.0
LEVERAGE_IMAGE_TAG     := 1.2.7-0.0.5
PYPROJECT_FILE := pyproject.toml
INIT_FILE := leverage/__init__.py
RELEASE_VERSION ?= $(shell curl -sL "https://test.pypi.org/pypi/leverage/json" | jq -r ".releases | keys | sort | .[-1]" | awk 'BEGIN{FS="."; OFS="."} {print $$1,$$2,$$3+1}' )rc.1
PLACEHOLDER := 0.0.0

help:
	@echo 'Available Commands:'
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf " - \033[36m%-18s\033[0m %s\n", $$1, $$2}'

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

bump-test-version: ## Bump version based on TestPyPI or provided input
	@echo "[INFO] Get current version from __init__.py"
	$(eval CURRENT_VERSION=$(shell awk '/__version__/ {print $$3}' $(INIT_FILE) | tr -d '"' | tr -d "'"))
	@echo "[INFO] Current version: $(CURRENT_VERSION)"
	@echo "[INFO] Get latest version from TestPypi."
	$(eval LATEST_VERSION=$(shell curl -sL "https://test.pypi.org/pypi/leverage/json" | jq -r ".releases | keys | sort | .[-1]"))
	@echo "[INFO] Latest version: $(LATEST_VERSION)"
	$(eval RELEASE_VERSION=$(shell echo $(LATEST_VERSION) | awk 'BEGIN{FS="."; OFS="."} {print $$1,$$2,$$3+1}')rc.1)
	@echo "[INFO] Checking Release Version (template 9.9.9-rc9)..."
	@echo $(RELEASE_VERSION) | awk '/[0-9]+\.[0-9]+\.[0-9]+-(rc|alpha|beta)[0-9]+/ {print "[INFO] Version ok"}' || (echo "[ERROR] Version is wrong" && exit 1)
	@echo "[INFO] Bump version to $(RELEASE_VERSION)"
	@sed -i '' 's/__version__ = "$(CURRENT_VERSION)"/__version__ = "$(RELEASE_VERSION)"/' $(INIT_FILE)
	@sed -i '' 's/version = "$(CURRENT_VERSION)"/version = "$(RELEASE_VERSION)"/' $(PYPROJECT_FILE)

bump-version-ci: ## Fetch latest tag, update versions in __init__.py and pyproject.toml
	@echo "[INFO] Get latest tag"
	$(eval RELEASE_VERSION=$(shell git fetch --all --tags && git tag --sort=version:refname | tail -1 | sed 's/v//'))
	@echo $(RELEASE_VERSION)

	@echo "[INFO] Write version to __init__.py"
	@sed -i '' 's/$(PLACEHOLDER)/$(RELEASE_VERSION)/' $(INIT_FILE)

	@echo "[INFO] Update version in pyproject.toml"
	@sed -i '' 's/version = ".*"/version = "$(RELEASE_VERSION)"/' $(PYPROJECT_FILE)
