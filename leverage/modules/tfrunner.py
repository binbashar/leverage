import subprocess
from pathlib import Path
from typing import Dict, Optional

from click.exceptions import Exit

from leverage._utils import ExitError
from leverage.modules.runner import Runner


class TFRunner(Runner):
    """Terraform/OpenTofu runner with appropriate installation guidance"""

    TERRAFORM_INSTALL_URL = "https://developer.hashicorp.com/terraform/install"
    OPENTOFU_INSTALL_URL = "https://opentofu.org/docs/intro/install/"

    def __init__(self, binary: str, terraform: bool = False, env_vars: Optional[Dict[str, str]] = None):
        """
        Initialize TFRunner for either Terraform or OpenTofu.

        Args:
            terraform: If True, treat the binary as Terraform. If False, as OpenTofu (default).
            env_vars: Environment variables to set for all executions
        """
        self.__terraform = terraform

        if not binary:
            binary = "tofu" if not self.__terraform else "terraform"
        if self.__terraform:
            error_message = (
                f"Terraform binary not found on system. "
                f"Please install Terraform following the instructions at: {self.TERRAFORM_INSTALL_URL}"
            )
        else:
            error_message = (
                f"OpenTofu binary not found on system. "
                f"Please install OpenTofu following the instructions at: {self.OPENTOFU_INSTALL_URL}"
            )

        super().__init__(binary=binary, error_message=error_message, env_vars=env_vars)

    def _validate_binary(self):
        super()._validate_binary()

        binary_version_stdout = subprocess.run([self.binary_path, "--version"], capture_output=True, text=True).stdout

        if self.__terraform and "Terraform" not in binary_version_stdout:
            raise ExitError(1, "The provided binary does not seem to be Terraform.")
        elif not self.__terraform and "OpenTofu" not in binary_version_stdout:
            raise ExitError(1, "The provided binary does not seem to be OpenTofu.")

    def run(
        self,
        *args: str,
        env_vars: Optional[Dict[str, str]] = None,
        working_dir: Optional[Path] = None,
        raises: bool = True,
    ):
        """
        Run the Terraform/OpenTofu binary with the given arguments.

        Args:
            *args: Command and arguments to pass (e.g., 'plan', '-out=plan.tfplan')
            env_vars: Environment variables for this specific execution
            working_dir: Working directory for command execution
            raises: If True, raise an ExitError if the command fails. If False, return the exit code.

        Returns:
            Exit code (int)
        """
        return super().run(*args, env_vars=env_vars, working_dir=working_dir, raises=raises)

    def exec(
        self,
        *args: str,
        env_vars: Optional[Dict[str, str]] = None,
        working_dir: Optional[Path] = None,
        raises: bool = False,
    ):
        """
        Execute the Terraform/OpenTofu binary in non-interactive mode (captures output).

        This is a convenience method that calls run() with interactive=False.

        Args:
            *args: Command and arguments to pass (e.g., 'plan', '-out=plan.tfplan')
            env_vars: Environment variables for this specific execution
            working_dir: Working directory for command execution
            raises: If True, raise an ExitError if the command fails. If False, return the exit code.

        Returns:
            Tuple of (exit_code, stdout, stderr)
        """
        return super().run(*args, env_vars=env_vars, working_dir=working_dir, interactive=False, raises=raises)
