<a href="https://github.com/binbashar">
    <img src="https://raw.githubusercontent.com/binbashar/le-ref-architecture-doc/master/docs/assets/images/logos/binbash-leverage-banner.png" width="1032" align="left" alt="Binbash"/>
</a>
<br clear="left"/>

# Leverage CLI

Leverage CLI is the tool used to manage and interact with any Leverage project.

It transparently handles the most complex and error-prone tasks that arise from working with a state-of-the-art infrastructure definition like our Leverage Reference Architecture. It understands the structure of the Leverage Reference Architecture and assists the user in their day-to-day operation.

Leverage CLI orchestrates a set of tools used to operate in a Leverage project. Usually this means OpenTofu/Terraform, but also aws-cli, kubectl and more. 

Reviewing and implementing the [Binbash Leverage Landing Zone for AWS](https://leverage.binbash.co/try-leverage/) would
be a very good place to start!

## Documentation

For installation instructions and all documentation regarding Leverage CLI, please refer
to [this page](https://leverage.binbash.co/user-guide/leverage-cli/installation/).

A proposal for ordering layer applies and running them from CI is in
[docs/ordered-apply.md](docs/ordered-apply.md).

### Note for migration from previous versions

If you come from Leverage CLI version <3.0.0 and want to use Leverage CLI version >= 3.0.0 keep into account the
following.

Leverage CLI no longer runs tools inside a Docker container; it executes the OpenTofu/Terraform binaries installed on
your host. Because of this, the `TERRAFORM_IMAGE_NAME`/`TF_IMAGE_NAME` and `TERRAFORM_IMAGE_TAG`/`TF_IMAGE_TAG`
parameters in the `build.env` file no longer exist. In their place, the optional `TF_BINARY` parameter specifies the path
to the OpenTofu/Terraform binary to use. As an example, this is the old format:

```
# Project settings
PROJECT=bb

# General
MFA_ENABLED=false

# Terraform
TF_IMAGE_TAG=1.5.0-0.2.0
```

New version example:

```
# Project settings
PROJECT=bb

# General
MFA_ENABLED=false

# OpenTofu/Terraform binary
TF_BINARY=/usr/local/bin/tofu
```

So, if you have created a project with version <3.0.0 and want to use it with version >=3.0.0 you should:

- remove the `TERRAFORM_IMAGE_NAME`/`TF_IMAGE_NAME` and `TERRAFORM_IMAGE_TAG`/`TF_IMAGE_TAG` lines
- install [OpenTofu](https://opentofu.org/docs/intro/install/) or [Terraform](https://developer.hashicorp.com/terraform/install)
  on your host
- optionally, set `TF_BINARY` to the path of the binary. This is useful when you have multiple versions of
  OpenTofu/Terraform installed, or when the binary lives in an unconventional location. It can be an absolute path, a path starting with `~`, or a path
  relative to the project root. If not set, the `tofu` or `terraform` binary is looked up in your `PATH`. Keep in mind
  the binary must match the command you use: `leverage tofu` expects OpenTofu and `leverage terraform` expects Terraform.

## System requirements

### Supported python versions

Leverage CLI explicitly supports the following Python versions:

- Python 3.9.x
- Python 3.10.x
- Python 3.11.x
- Python 3.12.x
- Python 3.13.x

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
pyenv install 3.13.6
```

4. Create a virtual environment for the leverage project:

Create a virtual environment for your project using Python 3.13.x:

```bash
pyenv virtualenv 3.13.6 leverage_py_313_venv
```

5. Set your virtual environment to be used in the project:

To set this virtual environment as the local environment for your project, navigate to your project directory and run:

```bash
cd <path_to_leverage_project_root>
pyenv local leverage_py_313_venv
```

This setup commands `pyenv` to use `leverage_py_313_venv` as the local Python version for your project directory,
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

Integration tests are implemented using [bats](https://github.com/bats-core/bats-core/). They drive the installed
`leverage` command, and work on temporary directories of their own, so they can be run directly on your machine.

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

The cli runs the infrastructure binaries directly, so `terraform` and `tofu` need to be installed as well. See
[System requirements](#system-requirements).

```bash
bats -r tests/bats
```

If `bats-support` and `bats-assert` are not installed in a location bats searches by default, point `BATS_LIB_PATH` at
the directory holding them:

```bash
BATS_LIB_PATH=/opt/homebrew/lib bats -r tests/bats
```

Alternatively, `make tests` runs both suites, and `make test-unit` or `make test-int` runs one of them.

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
