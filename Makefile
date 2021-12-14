.PHONY: help build
LEVERAGE_TESTING_IMAGE := binbash/leverage-cli-testing
LEVERAGE_TESTING_TAG   := 2.0.0

help:
	@echo 'Available Commands:'
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf " - \033[36m%-18s\033[0m %s\n", $$1, $$2}'

test-unit: ## Run unit tests and create a coverage report
	docker run --rm --privileged --mount type=bind,src=$(shell pwd),dst=/leverage -t ${LEVERAGE_TESTING_IMAGE}:${LEVERAGE_TESTING_TAG} pytest --verbose

test-unit-no-cov: ## Run unit tests with no coverage report
	docker run --rm --privileged --mount type=bind,src=$(shell pwd),dst=/leverage -t ${LEVERAGE_TESTING_IMAGE}:${LEVERAGE_TESTING_TAG} pytest --verbose --no-cov

test-int: ## Run integration tests
	docker run --rm --privileged --mount type=bind,src=$(shell pwd),dst=/leverage -t ${LEVERAGE_TESTING_IMAGE}:${LEVERAGE_TESTING_TAG} bash -c "pip3 install -e . > /dev/null && bats --verbose-run --show-output-of-passing-tests -p -r tests/bats"

tests: test-unit-no-cov test-int ## Run full set of tests

setup: ## Set up requirements
	python3 -m pip3 install --user --upgrade pipenv && pipenv install --dev

clean: ## Clean build files
	rm -rf ./build/
	rm -rf ./dist/

build: clean ## Build distributables
	pipenv run python setup.py sdist bdist_wheel

check: ## Check distributables
	pipenv run twine check dist/*

push: ## Push distributables to PyPi
	pipenv run twine upload --repository-url https://upload.pypi.org/legacy/ dist/*

push-test: ## Push distributables to Pypi test
	pipenv run twine upload --repository testpypi dist/*
