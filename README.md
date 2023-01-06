<a href="https://github.com/binbashar">
    <img src="https://raw.githubusercontent.com/binbashar/le-ref-architecture-doc/master/docs/assets/images/logos/binbash-leverage-banner.png" width="1032" align="left" alt="Binbash"/>
</a>
<br clear="left"/>

# Leverage CLI
Leverage CLI is the tool used to manage and interact with any Leverage project.

It transparently handles the most complex and error prone tasks that arise from working with a state-of-the-art infrastructure definition like our Leverage Reference Architecture. Leverage CLI uses a dockerized approach to encapsulate the tools needed to perform such tasks and to free the user from having to deal with the configuration and management of said tools.
Provides the means to interact with your Leverage project and allows you to define custom tasks to run.


## Documentation
For installation instructions and all documentation regarding Leverage CLI, please refer to [this page](https://leverage.binbash.com.ar/how-it-works/leverage-cli/).

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
A Docker image suitable for running all tests can be crafted by running `make build-image`. After crafting the image all tests can be executed.

To run all tests, run `make tests`. Alternatively `make test-unit` or `make test-int` for unit or integration tests respectively.

## Release Process
* On every PR, a Github Action workflow is triggered to create/update a release draft.
* The version number is determined by the labels of those PRs (major, minor, fix).
* The release draft has to be manually published. This allows for any number of PR (features, fixes) to make the cut.
* Once a release is published, another workflow is triggered to create and push the package to PyPi.

## Release Candidate Process
* There is an Action called "Test Build Package and Push".
* This Action can be called manually on any branch specifying the version to release to test.
    * The version is a Release Candidate following the Semver: e.g. if the next release is 1.2.3, the test version should be 1.2.3-rc.1
* The package will be published to [Test PyPi](https://test.pypi.org/project/leverage/).

## Contributors/Contributing
* Leverage CLI was initially based on Pynt: https://github.com/rags/pynt


## License
Leverage CLI is licensed under [MIT license](http://opensource.org/licenses/MIT)[BinBash Inc](https://github.com/binbashar)
