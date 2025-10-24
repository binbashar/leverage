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

Leverage CLI is a Python-based command-line tool for managing Binbash Leverage projects. It uses a dockerized approach to encapsulate infrastructure tools.

### Core Structure
- `leverage/leverage.py` - Main CLI entry point using Click framework
- `leverage/modules/` - Command modules (aws, terraform, kubectl, etc.)
- `leverage/container.py` - Docker container management and execution
- `leverage/conf.py` - Configuration loading from build.env files
- `leverage/tasks.py` - Task system for build scripts
- `leverage/path.py` - Path utilities and git repository handling

### Key Components
- **Module System**: Commands are organized in modules under `leverage/modules/`
- **Container Integration**: Heavy use of Docker containers for tool execution
- **Configuration Management**: Hierarchical loading of build.env files
- **Task System**: Decorator-based task definition system for build scripts
- **AWS Integration**: Extensive AWS credential and service management

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
- Minimum tool versions enforced via `MINIMUM_VERSIONS`
- Docker image versioning through `__toolbox_version__`

### Configuration
- Uses `build.env` files for project configuration
- Hierarchical loading from project root to current directory
- Environment-specific overrides supported

## Docker Container Architecture for Terraform/OpenTofu

The CLI uses a containerized approach for all Terraform/OpenTofu operations to ensure consistent tool versions and isolated execution environments.

### Container Classes

#### TFContainer (`leverage/container.py:436-687`)
Primary container for Terraform/OpenTofu execution:
- **Image**: `binbash/leverage-toolbox` with user-specific permissions
- **Binaries**: `/bin/terraform` (when `terraform=True`) or `/bin/tofu` (default)
- **Mount Points**:
  - Project root → `/leverage` (guest base path)
  - AWS credentials directory → `/tmp/.aws`
  - Git config file → `/etc/gitconfig`
  - Optional: TF plugin cache directory (maintains symlinks)
  - Optional: SSH agent socket → `/ssh-agent`

#### TFautomvContainer (`leverage/container.py:689-717`)
Extends TFContainer for TFAutomv operations:
- **Binary**: `/usr/local/bin/tfautomv`
- Inherits all TFContainer mounts and configuration

### Configuration File Management

#### Environment Variables in Containers:
- `COMMON_CONFIG_FILE` → `common.tfvars`
- `ACCOUNT_CONFIG_FILE` → `account.tfvars`
- `BACKEND_CONFIG_FILE` → `backend.tfvars`
- `AWS_SHARED_CREDENTIALS_FILE` → `/tmp/.aws/credentials`
- `AWS_CONFIG_FILE` → `/tmp/.aws/config`
- `SSO_CACHE_DIR` → `/tmp/.aws/sso/cache`

#### Terraform Variable Files:
The `tf_default_args` property automatically includes:
- All `*.tfvars` files from `common/` directory
- All `*.tfvars` files from account-specific directory

### Docker Execution Points

#### Terraform/OpenTofu Commands (`leverage/modules/tf.py`)
- Container creation for `tofu` and `terraform` commands (lines 38, 56)
- Command execution via `tf.start()` for all operations
- **Supported Commands**: `init`, `plan`, `apply`, `destroy`, `output`, `version`, `shell`, `format`, `validate`, `import`, `refresh-credentials`

#### TFAutomv Commands (`leverage/modules/tfautomv.py`)
- Container creation for `tfautomv` commands (line 24)
- Command execution via `tf.start_in_layer()` (line 36)

### Container Lifecycle

1. **Image Verification**: `ensure_image()` builds local image with user permissions
2. **Container Creation**: `_create_container()` with mounted volumes and environment
3. **Authentication Setup**: SSO token validation or MFA credential handling
4. **Command Execution**: Interactive (`_start()`) or silent (`_exec()`)
5. **Cleanup**: Automatic container stop and removal

### Authentication & Credentials

#### SSO Authentication:
- Token validation before container execution
- Automatic credential refresh via `refresh_layer_credentials()`
- Browser-based authentication flow with user code

#### MFA Authentication:
- Script-based authentication via `aws-mfa-entrypoint.sh`
- Environment variable adjustments for credential paths

#### Credential Mounting:
- Host AWS credentials directory mounted to container
- Separate credential files for different authentication methods

### Backend Configuration Management

#### S3 Backend Handling:
- Automatic `backend.tfvars` parameter injection for `init` commands
- Dynamic state key generation based on layer path structure
- Backend block validation in `config.tf` files
- Support for legacy naming conventions (tf- vs terraform-)

**IMPORTANT**: As of the latest update, Leverage CLI now uses **host-based execution** instead of Docker containers:

## Host-Based Execution Architecture

The CLI has been updated to use host-based execution for improved performance and flexibility while maintaining all functionality.

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
- **Error Messages**: Provides installation URLs when binaries are not found
  - Terraform: https://developer.hashicorp.com/terraform/install
  - OpenTofu: https://opentofu.org/docs/intro/install/
- **Environment Variables**: Initialized with AWS credential file paths via `env_vars` parameter
- **No Containers**: Direct binary execution on host system

### Command Flow Architecture

#### Terraform/OpenTofu Command Flow (`leverage/modules/tf.py`)

1. **CLI Entry Points**:
   - `@click.group() tofu()` (lines 22-35) - Creates TFRunner with OpenTofu binary
   - `@click.group() terraform()` (lines 38-51) - Creates TFRunner with Terraform binary
   - Both set up credential environment variables for AWS config and credentials files

2. **Command Decoration**:
   - `@pass_runner` - Injects TFRunner instance from Click context
   - `@pass_paths` - Injects PathsHandler instance for file/directory management

3. **Supported Commands**:
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

4. **Multi-Layer Support**:
   - `--layers` option for operating on multiple layers from account directory
   - Layer validation and backend key management via `invoke_for_all_commands()`
   - Automatic backend key generation based on layer path structure

### Authentication Management

#### SSO Authentication (`leverage/modules/auth.py`)

**Token Validation** (`check_sso_token()` - lines 98-127):
- Validates SSO token existence in cache directory
- Checks token expiration against current time
- Provides clear error messages for missing or expired tokens
- Token file location: `~/.aws/sso/cache/<sso_role>`

**Credential Refresh** (`refresh_layer_credentials()` - lines 130-204):
- Parses Terraform files to discover required AWS profiles
- Uses boto3 SSO client to retrieve temporary credentials
- Updates AWS config file with credential expiration timestamps
- Writes temporary credentials to AWS credentials file
- Implements 30-minute early renewal to avoid mid-operation expiration
- Supports cross-account profile resolution

**Profile Discovery** (`get_profiles()` - lines 68-88):
- Scans `config.tf`, `locals.tf`, `runtime.tf` for profile references
- Extracts profile variables from Terraform configurations
- Reads backend profile from `backend.tfvars`

### Configuration Management

#### Automatic tfvars Discovery (`tf_default_args()` - lines 133-154):
- Discovers all `*.tfvars` files in `common/` directory
- Discovers all `*.tfvars` files in account-specific directory
- Returns as `-var-file=<path>` arguments for Terraform/OpenTofu
- Used automatically in plan, destroy, validate, and conditionally in apply

#### Backend Configuration:
- Backend config file path injected during `init` command (line 336)
- Automatic backend key generation in `invoke_for_all_commands()` (lines 291-294)
- Backend key validation in `validate_layout()` (lines 538-550)
- Support for legacy naming conventions (tf- vs terraform-, base- vs tools-)

### Execution Flow

**Standard Command Execution**:
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

**Multi-Layer Execution**:
1. User runs command with `--layers layer1,layer2` from account directory
2. `invoke_for_all_commands()` validates all layers
3. Backend keys generated/validated for each layer
4. Command executed sequentially for each layer with layer-specific working directory

### Benefits of Host-Based Execution

- **Performance**: No container startup overhead or image building
- **Flexibility**: Use any installed tool version (including custom builds)
- **IDE Integration**: Better debugging and tooling support
- **Simplicity**: Direct binary execution with standard environment variables
- **Plugin Compatibility**: Native Terraform/OpenTofu plugin caching
- **Development Speed**: Faster iteration during development

### Host Requirements

For full functionality, ensure the following binaries are installed and available in PATH:
- `terraform` or `tofu` (for Terraform/OpenTofu operations)
- `aws` CLI (for SSO authentication via boto3)

Optional binaries:
- `tfautomv` (for TFAutomv operations)