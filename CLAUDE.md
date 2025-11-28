# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Setup
- `poetry install --with=dev --with=main` - Install all dependencies including dev tools
- `poetry shell` - Activate virtual environment for development

### Testing
- `poetry run pytest` - Run unit tests
- `poetry run pytest --verbose --cov=./ --cov-report=xml` - Run unit tests with coverage
- `make test-unit` - Run unit tests in Docker (with coverage)
- `make test-unit-no-cov` - Run unit tests in Docker (no coverage)
- `make test-int` - Run integration tests using bats in Docker
- `make tests` - Run full test suite (unit + integration)

### Code Quality
- `poetry run black .` - Format code with Black (line length: 120)
- `poetry run pylint leverage/` - Run linting
- `poetry run pre-commit install` - Install pre-commit hooks
- `poetry run pre-commit run --all-files` - Run pre-commit checks manually

### Build and Distribution
- `make build` - Build distributables (cleans first)
- `make check` - Check distributables with twine
- `poetry build` - Build package using Poetry
- `make clean` - Clean build artifacts

### Docker
- `make build-image` - Build Docker testing image
- All test commands can run in Docker using the testing image

## Architecture

Leverage CLI is a Python-based command-line tool for managing Binbash Leverage projects. It uses host-based execution to run infrastructure tools directly on the system.

### Core Structure
- `leverage/leverage.py` - Main CLI entry point using Click framework
- `leverage/modules/` - Command modules (aws, terraform, kubectl, etc.)
- `leverage/modules/runner.py` - Generic binary runner base class
- `leverage/modules/tfrunner.py` - Terraform/OpenTofu-specific runner
- `leverage/conf.py` - Configuration loading from build.env files
- `leverage/tasks.py` - Task system for build scripts
- `leverage/path.py` - Path utilities and git repository handling

### Key Components
- **Module System**: Commands are organized in modules under `leverage/modules/`
- **Host-Based Execution**: Direct execution of system binaries (terraform, tofu, kubectl, etc.)
- **Runner Architecture**: Generic Runner class with specialized subclasses (TFRunner)
- **Configuration Management**: Hierarchical loading of build.env files
- **Task System**: Decorator-based task definition system for build scripts
- **AWS Integration**: Extensive AWS credential and service management via SSO/MFA

### Command Structure
The CLI follows this pattern:
```
leverage [global-options] <module> <subcommand> [args]
```

Key modules include:
- `project` - Project initialization and management
- `terraform`/`tf`/`tofu` - Terraform/OpenTofu operations
- `aws` - AWS service interactions
- `credentials` - Credential management
- `kubectl`/`kc` - Kubernetes operations
- `run` - Custom task execution
- `shell` - Interactive shell access

### Version Management
- Supports Python 3.9-3.13
- Version defined in `leverage/__init__.py`
- Binary version validation on initialization (for TFRunner)

### Configuration
- Uses `build.env` files for project configuration
- Hierarchical loading from project root to current directory
- Environment-specific overrides supported

## Execution Architecture

The CLI executes infrastructure tools directly on the host system using the Runner architecture.

### Core Runner Classes

#### Runner (`leverage/modules/runner.py`)
Generic command runner base class:
- **Purpose**: Provides common execution functionality for all binary runners
- **Binary Discovery**: Searches for binaries in PATH or accepts absolute paths
- **Environment Management**: Merges instance-level and run-time environment variables
- **Execution Modes**:
  - `run()` - Interactive execution (returns exit code) or silent (returns exit code, stdout, stderr)
  - `exec()` - Convenience method for non-interactive execution with output capture
- **Working Directory**: Supports execution in any specified directory
- **Validation**: Automatic binary existence validation on initialization

#### TFRunner (`leverage/modules/tfrunner.py`)
Terraform/OpenTofu-specific runner extending Runner:
- **Binaries**: Uses system-installed `terraform` or `tofu` binaries
- **Configuration**: Accepts `terraform=True` for Terraform, defaults to OpenTofu
- **Binary Validation**: Validates binary type by checking `--version` output
  - Ensures `tofu` binary is actually OpenTofu (not Terraform)
  - Ensures `terraform` binary is actually Terraform (not OpenTofu)
- **Error Messages**: Provides installation URLs when binaries are not found
  - Terraform: https://developer.hashicorp.com/terraform/install
  - OpenTofu: https://opentofu.org/docs/intro/install/
- **Environment Variables**: Initialized with AWS credential file paths via `env_vars` parameter

### Command Modules

#### Terraform/OpenTofu Commands (`leverage/modules/tf.py`)

**CLI Entry Points**:
- `tofu` - Creates TFRunner with OpenTofu binary (`tofu`)
- `terraform` - Creates TFRunner with Terraform binary (`terraform`)
- Both set up credential environment variables for AWS config and credentials files

**Command Decorators**:
- `@pass_runner` - Injects TFRunner instance from Click context
- `@pass_paths` - Injects PathsHandler instance for file/directory management

**Supported Commands**:
- `init` - Layer initialization with backend configuration injection
- `plan` - Execution plan generation with auto-discovered tfvars
- `apply` - Infrastructure changes with conditional tfvars injection
- `destroy` - Infrastructure destruction
- `output` - Output variable display
- `version` - Binary version display
- `format` - Code formatting (recursive by default)
- `force-unlock` - State file lock removal
- `validate` - Configuration validation
- `validate-layout` - Leverage convention validation
- `import` - Resource import
- `refresh-credentials` - AWS credential refresh

**Multi-Layer Support**:
- `--layers` option for operating on multiple layers from account directory
- Layer validation and backend key management via `invoke_for_all_commands()`
- Automatic backend key generation based on layer path structure

#### Kubectl Commands (`leverage/modules/kubectl.py`)

Uses generic Runner class to execute `kubectl` binary:
- **Binary**: System-installed `kubectl`
- **Configuration**: Sets KUBECONFIG environment variable to project-specific path
- **AWS Integration**: Configures kubectl contexts for EKS clusters
- **Commands**:
  - `configure` - Add EKS cluster from current layer to kubectl config
  - `discover` - Scan for cluster metadata files and configure selected cluster
- All other kubectl commands pass through to the binary

#### TFAutomv Commands (`leverage/modules/tfautomv.py`)

Uses generic Runner class to execute `tfautomv` binary:
- **Binary**: System-installed `tfautomv`
- **Configuration**: Passes terraform binary path via `--terraform-bin` flag
- **Integration**: Uses same tfvars discovery as Terraform/OpenTofu commands

### Authentication Management (`leverage/modules/auth.py`)

#### SSO Authentication

**Token Validation** (`check_sso_token()`):
- Validates SSO token existence in cache directory (`~/.aws/sso/cache/<sso_role>`)
- Checks token expiration against current time
- Provides clear error messages for missing or expired tokens

**Credential Refresh** (`refresh_layer_credentials()`):
- Parses Terraform files to discover required AWS profiles
- Uses boto3 SSO client to retrieve temporary credentials
- Updates AWS config file with credential expiration timestamps
- Writes temporary credentials to AWS credentials file
- Implements 30-minute early renewal to avoid mid-operation expiration
- Supports cross-account profile resolution

**Profile Discovery** (`get_profiles()`):
- Scans `config.tf`, `locals.tf`, `runtime.tf` for profile references
- Extracts profile variables from Terraform configurations
- Reads backend profile from `backend.tfvars`

### Configuration Management

#### Automatic tfvars Discovery (`tf_default_args()`):
- Discovers all `*.tfvars` files in `common/` directory
- Discovers all `*.tfvars` files in account-specific directory
- Returns as `-var-file=<path>` arguments for Terraform/OpenTofu
- Used automatically in plan, destroy, validate, and conditionally in apply

#### Backend Configuration:
- Backend config file path injected during `init` command
- Automatic backend key generation in `invoke_for_all_commands()`
- Backend key validation in `validate_layout()`
- Support for legacy naming conventions (tf- vs terraform-, base- vs tools-)

### Execution Flow

#### Standard Command Execution
1. User runs `leverage tofu|terraform <command> [args]`
2. Click creates TFRunner instance with credential environment variables
3. Command function decorated with `@pass_runner` and `@pass_paths`
4. Authentication check via `check_sso_token(paths)`
5. Credential refresh via `refresh_layer_credentials(paths)`
6. TFRunner.run() executes binary with:
   - Merged environment variables (instance + runtime)
   - Specified working directory
   - Auto-discovered tfvars (for applicable commands)
   - User-provided arguments
7. Exit code returned to CLI

#### Multi-Layer Execution
1. User runs command with `--layers layer1,layer2` from account directory
2. `invoke_for_all_commands()` validates all layers
3. Backend keys generated/validated for each layer
4. Command executed sequentially for each layer with layer-specific working directory

### System Requirements

For full functionality, ensure the following binaries are installed and available in PATH:

**Required**:
- `terraform` or `tofu` - For Terraform/OpenTofu operations
- `aws` - AWS CLI for SSO authentication (via boto3)
- Python 3.9-3.13

**Optional**:
- `kubectl` - For Kubernetes operations
- `tfautomv` - For TFAutomv operations

### Benefits of Current Architecture

- **Performance**: Direct binary execution without overhead
- **Flexibility**: Use any installed tool version (including custom builds)
- **IDE Integration**: Better debugging and tooling support
- **Simplicity**: Standard environment variables and execution
- **Plugin Compatibility**: Native Terraform/OpenTofu plugin caching
- **Development Speed**: Faster iteration during development