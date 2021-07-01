.PHONY: help build

help:
	@echo 'Available Commands:'
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf " - \033[36m%-18s\033[0m %s\n", $$1, $$2}'

build-image: ## Build docker image
	docker build . -t leverage-testing

test-unit: ## Run unit tests and create a coverage report
	docker run --rm --mount type=bind,src=$(shell pwd),dst=/leverage -t leverage-testing -c "pytest --verbose"

test-unit-no-cov: ## Run unit tests with no coverage report
	docker run --rm --mount type=bind,src=$(shell pwd),dst=/leverage -t leverage-testing -c "pytest --verbose --no-cov"

test-int: ## Run integration tests
	docker run --rm --mount type=bind,src=$(shell pwd),dst=/leverage -t leverage-testing bats -r tests/bats

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

install-command: ## Command for installing leverage as a local package for development in a leverage ref arch project
	@echo 'python3 -m pip3 install pipenv && pipenv install -e $(shell pwd)'