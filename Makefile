.PHONY: help build

help:
	@echo 'Available Commands:'
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf " - \033[36m%-18s\033[0m %s\n", $$1, $$2}'


deps: ## Install Leverage dependencies
	python3 -m pip install -r dev-requirements.txt

build-image: ## Build docker image
	docker build . -t leverage-testing

test-unit: ## Run unit tests
	docker run --rm --mount type=bind,src=$(shell pwd),dst=/leverage -t leverage-testing -c "pytest --verbose"

test-int: ## Run integration tests
	docker run --rm --mount type=bind,src=$(shell pwd),dst=/leverage -t leverage-testing bats -r tests/bats

tests: test-unit test-int## Run full set of tests

setup: ## Set up requirements
	python3 -m pip install --user --upgrade setuptools wheel twine gitpython

clean: ## Clean build files
	rm -rf ./build/
	rm -rf ./dist/

build: clean ## Build distributables
	python3 setup.py sdist bdist_wheel

check: ## Check distributables
	python3 -m twine check dist/*

push: ## Push distributables to PyPi
	python3 -m twine upload --repository-url https://upload.pypi.org/legacy/ dist/*

info: ## Show additional info
	@echo "virtualenv venv"
	@echo "cd venv"
	@echo "source bin/activate"
	@echo "python3 -m pip install --index-url https://test.pypi.org/simple/ --no-deps leverage"
