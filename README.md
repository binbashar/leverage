<a href="https://github.com/binbashar">
    <img src="https://raw.githubusercontent.com/binbashar/le-ref-architecture-doc/master/docs/assets/images/logos/binbash-leverage-banner.png" width="1032" align="left" alt="Binbash"/>
</a>
<br clear="left"/>

# Leverage CLI
Leverage CLI is the tool used to manage and interact with any Leverage project.

It transparently handles the most complex and error prone tasks that arise from working with a state-of-the-art infrastructure definition like our Leverage Reference Architecture. Leverage CLI uses a dockerized approach to encapsulate the tools needed to perform such tasks and to free the user from having to deal with the configuration and management of said tools.
Provides the means to interact with your Leverage project and allows you to define custom tasks to run.

Reviewing and implementing the [Binbash Leverage Landing Zone for AWS](https://leverage.binbash.co/try-leverage/) would be a very good place to start!

## Documentation
For installation instructions and all documentation regarding Leverage CLI, please refer to [this page](https://leverage.binbash.co/user-guide/leverage-cli/installation/).

### Note for migration from previous versions

If you come from Leverage CLI version <1.8.0 and want to install Leverage CLI version >= 1.8.0 keep into account the following.

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
TERRAFORM_IMAGE_TAG=1.2.7-0.1.0
```

So, if you have created a project with version <1.8.0 and want to use it with version >=1.8.0 you should:

- remove TERRAFORM_IMAGE_NAME line
- update TERRAFORM_IMAGE_TAG from this form '9.9.9' to this one '9.9.9-9.9.9'. 

For the second item you can check the version [here](https://hub.docker.com/r/binbash/leverage-toolbox/tags).


## Setting up development environment

### How to contribute to this repository

- The `master` branch should always be in a deployable state.
- [We are not following GitFlow](https://www.endoflineblog.com/gitflow-considered-harmful), there is no `dev` branch.
- All work is done in short lived feature branches that are merged to `master` once they have been tested and approved.
- Commit history is kept linear.

In order to keep our commit history linear and easy to navigate, we're following a few simple rules:

- Only [fast-forward merges](http://ariya.ofilabs.com/2013/09/fast-forward-git-merge.html) are allowed. Github's repo
  has already been set up for this so only `Rebase and Merge` button is available for all PRs. Alternatively you can
  merge PRs from command line:
  ```bash
  git fetch origin                   # fetch latest changes from Github
  git rebase -i origin/master        # rebase your branch on top of master and squash multiple commits 
  git push -f origin <my_branch>     # update the remote branch on Github 
  git push origin <my_branch>:master # push your branch as master. This will succeed only if your branch 
                                     # is rebased on top of master and if the PR has been approved. 
                                     # It also merges the PR and deletes the feature branch on Github.
  ```

- Before merge ensure commits are [squashed](http://gitready.com/advanced/2009/02/10/squashing-commits-with-rebase.html):
    1. Each commit should be well-tested product increment
    2. PR should usually have only one commit
    3. Multiple commits per PR are acceptable in rare cases when each commit is a complete work unit.

- [Write meaningful commit messages](https://chris.beams.io/posts/git-commit/), prefix it with ticket number in square brackets

### Python versions and virtual environment management

Install Python 3.8.18 & setup virtual environment. We recommend to use [pyenv](https://github.com/pyenv/pyenv) and
[pyenv-virtualenv](https://github.com/pyenv/pyenv-virtualenv)

```bash
pyenv install 3.8.18
pyenv local 3.8.18
pyenv virtualenv 3.8.2 leverage_cli_venv
pyenv local leverage_cli_venv
```

The new virtual environment will be automatically used when you change into the project's directory.

### Install dependencies with pipenv

Install [pipenv](https://pipenv.pypa.io/en/latest/#install-pipenv-today) if you don't have it already:

```bash
pip install pipenv
```

First, you should create a virtual environment and install all the required dependencies by running:
```bash
pipenv install --dev
```

Now all the changes to the project will be immediately reflected on the command.

### Pre-commit hooks

In order to run black automatically on every commit, you should install [pre-commit](https://pre-commit.com/#installation) first:

And then install the hooks:
```bash
pre-commit install
```

## Running Tests
To run unit tests, pytest is the tool of choice, and the required dependencies are available in the corresponding `dev-requirements.txt`.

Integration tests are implemented using [bats](https://github.com/bats-core/bats-core/). Bear in mind that bats tests are meant to be run in a throwaway environment since they perform filesystem manipulations and installation and removal of packages, and the cleanup may not be completely thorough. As such, is highly recommended to run these tests using de docker image.

### Manually
Unit tests:
```bash
pip3 install -r dev-requirements.txt
python3 -m pytest
```
Integration tests:
```bash
bats -r tests/bats
```
### Using docker image

#### Build the base image for all tests

A Docker image suitable for running all tests can be crafted by running:

```bash
make build-image
``` 

*Note*: this is a pre-requisite for running tests with `make`

#### Run all tests

```bash
make tests
```

#### Run only unit tests

```bash
make test-unit
```

#### Run only integration tests

```bash
make test-int 
```

## Release Process
* On every PR, a Github Action workflow is triggered to create/update a release draft.
* The version number is determined by the labels of those PRs (major, minor, fix).
* The release draft has to be manually published. This allows for any number of PR (features, fixes) to make the cut.
* Once a release is published, another workflow is triggered to create and push the package to PyPi.

## Release Candidate Process
* There is an Action called "Test Build Package and Push".
* This Action can be called manually on any branch specifying the version to release to test.
    * The version is a Release Candidate following the Semver: e.g. if the next release is 1.2.3, the test version should be 1.2.3-rc.1
* The package will be published to [PyPi](https://pypi.org/project/leverage/).

## Contributors/Contributing
* Leverage CLI was initially based on Pynt: https://github.com/rags/pynt


## License
Leverage CLI is licensed under [MIT license](http://opensource.org/licenses/MIT)[BinBash Inc](https://github.com/binbashar)
