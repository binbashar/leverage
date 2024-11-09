<a href="https://github.com/binbashar">
    <img src="https://raw.githubusercontent.com/binbashar/le-ref-architecture-doc/master/docs/assets/images/logos/binbash-leverage-banner.png" width="1032" align="left" alt="Binbash"/>
</a>
<br clear="left"/>

# Leverage CLI

Leverage CLI is the tool used to manage and interact with any Leverage project.

It transparently handles the most complex and error prone tasks that arise from working with a state-of-the-art
infrastructure definition like our Leverage Reference Architecture. Leverage CLI uses a dockerized approach to
encapsulate the tools needed to perform such tasks and to free the user from having to deal with the configuration and
management of said tools.
Provides the means to interact with your Leverage project and allows you to define custom tasks to run.

Reviewing and implementing the [Binbash Leverage Landing Zone for AWS](https://leverage.binbash.co/try-leverage/) would
be a very good place to start!

## Documentation

For installation instructions and all documentation regarding Leverage CLI, please refer
to [this page](https://leverage.binbash.co/user-guide/leverage-cli/installation/).

### Note for migration from previous versions

If you come from Leverage CLI version <1.8.0 and want to install Leverage CLI version >= 1.8.0 keep into account the
following.

The `build.env` file format has changed. As an example, this is the old format:

```
# Project settings
PROJECT=bb

# General
MFA_ENABLED=false

# Terraform
TERRAFORM_IMAGE_NAME=binbash/terraform-awscli-slim
TERRAFORM_IMAGE_TAG=1.1.9
```

New version example:

```
# Project settings
PROJECT=bb

# General
MFA_ENABLED=false

# Terraform
TERRAFORM_IMAGE_TAG=1.5.0-0.2.0
```

So, if you have created a project with version <1.8.0 and want to use it with version >=1.8.0 you should:

- remove TERRAFORM_IMAGE_NAME line
- update TERRAFORM_IMAGE_TAG from this form '9.9.9' to this one '9.9.9-9.9.9'.

For the second item you can check the version [here](https://hub.docker.com/r/binbash/leverage-toolbox/tags).

## System requirements

### Supported python versions

Leverage CLI explicitly supports the following Python versions:

- Python 3.9.x
- Python 3.10.x
- Python 3.11.x
- Python 3.12.x

These versions are not only supported but are also the only versions used in our CI/CD pipelines to ensure compatibility
and performance. This rigorous testing helps prevent compatibility issues and ensures that the Leverage CLI performs as
expected under these versions.

Please ensure that your development and deployment environments are set up with one of these supported versions. Our
GitHub Actions and other CI workflows are specifically configured to test against these Python versions, which
reinforces our commitment to maintaining a reliable and stable toolset.

### Installing multiple python versions with pyenv

If you need to install one of the supported Python versions and would like to manage multiple
Python environments, `pyenv` is a highly recommended tool. Here’s how you can use `pyenv` to install and manage Python
versions:

1. Installing Pyenv:

```bash
curl https://pyenv.run | bash
```

2. Add Pyenv to your shell to automate the setup process (if using bash, otherwise you can find details on how to set it
   up [here](https://github.com/pyenv/pyenv#set-up-your-shell-environment-for-pyenv)):

```bash
echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.bashrc
echo 'export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.bashrc
echo 'eval "$(pyenv init --path)"' >> ~/.bashrc
echo 'eval "$(pyenv virtualenv-init -)"' >> ~/.bashrc
exec "$SHELL"
```

3. Installing python versions:

Once pyenv is installed, you can install any supported Python version by following these steps:

```bash
pyenv install 3.9.7
pyenv install 3.10.1
pyenv install 3.11.8
pyenv install 3.12.7
```

4. Create a virtual environment for the leverage project:

Create a virtual environment for your project using Python 3.9.7:

```bash
pyenv virtualenv 3.9.7 leverage_py_39_venv
```

5. Set your virtual environment to be used in the project:

To set this virtual environment as the local environment for your project, navigate to your project directory and run:

```bash
cd <path_to_leverage_project_root>
pyenv local leverage_py_39_venv
```

This setup commands `pyenv` to use `leverage_py_39_venv` as the local Python version for your project directory,
ensuring that all Python operations within this directory use this isolated environment.

## Setting up development environment

Before you begin, ensure you are running one of the supported Python versions.

We now use Poetry for dependency management. Setup your development environment as follows:

1. Install Poetry:

```bash
curl -sSL https://install.python-poetry.org | POETRY_VERSION=1.8.2 python -
```

2. Clone the repository and navigate into it:

```bash
git clone https://github.com/binbashar/leverage.git
cd leverage
```

3. Install dependencies using Poetry:

```bash
poetry install --with=dev --with=main
```

4. To activate the virtual environment and start using the CLI in dev mode, use:

```bash
poetry shell
```

## Pre-commit hooks

In order to run black automatically on every commit, you should install `pre-commit` first:

https://pre-commit.com/#installation

And then the hooks:

```
poetry run pre-commit install
```

## Running Tests

To run unit tests, pytest is the tool of choice, and the required dependencies are available in the
corresponding `dev-requirements.txt`.

Integration tests are implemented using [bats](https://github.com/bats-core/bats-core/). Bear in mind that bats tests
are meant to be run in a throwaway environment since they perform filesystem manipulations and installation and removal
of packages, and the cleanup may not be completely thorough. As such, is highly recommended to run these tests using the
docker image.

### Manually

1. Unit tests:

```bash
poetry run pytest
```

2. Integration tests:

Install dependencies (MacOS):

```bash
brew install bats-core
brew tap bats-core/bats-core
brew install bats-support
brew install bats-assert
```

```bash
bats -r tests/bats
```

### Using docker image

A Docker image suitable for running all tests can be crafted by running `make build-image`. After crafting the image all
tests can be executed.

To run all tests, run `make tests`. Alternatively `make test-unit` or `make test-int` for unit or integration tests
respectively.

## Release Process

* On every PR, a Github Action workflow is triggered to create/update a release draft.
* The version number is determined by the labels of those PRs (major, minor, fix).
* The release draft has to be manually published. This allows for any number of PR (features, fixes) to make the cut.
* Once a release is published, another workflow is triggered to create and push the package to PyPi.

## Release Candidate Process

* There is an Action called "Test Build Package and Push".
* This Action can be called manually on any branch specifying the version to release to test.
    * The version is a Release Candidate following the Semver: e.g. if the next release is 1.2.3, the test version
      should be 1.2.3rc.1
* The package will be published to [PyPi](https://pypi.org/project/leverage/).

## Contributors/Contributing

* Leverage CLI was initially based on Pynt: https://github.com/rags/pynt

## License

Leverage CLI is licensed
under [MIT license](http://opensource.org/licenses/MIT)[BinBash Inc](https://github.com/binbashar)
