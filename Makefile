.PHONY: help build

help:
	@echo 'Available Commands:'
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf " - \033[36m%-18s\033[0m %s\n", $$1, $$2}'

setup: ## Set up requirements
	python3 -m pip install --user --upgrade setuptools wheel
	python3 -m pip install --user --upgrade twine

clean: ## Clean build files
	rm -rf ./build/
	rm -rf ./dist/

build: clean ## Build distributables
	python3 setup.py sdist bdist_wheel

check: ## Check distributables
	python3 -m twine check dist/*

push: ## Push distributables to PyPi
	python3 -m twine upload --repository testpypi dist/*

info: ## Show additional info
	@echo "virtualenv venv"
	@echo "cd venv"
	@echo "source bin/activate"
	@echo "python3 -m pip install --index-url https://test.pypi.org/simple/ --no-deps leverage"
