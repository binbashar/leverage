from pathlib import Path
from typing import Dict, Optional

from leverage.modules.runner import Runner


class TFRunner(Runner):
    """Terraform/OpenTofu runner with appropriate installation guidance"""

    TERRAFORM_INSTALL_URL = "https://developer.hashicorp.com/terraform/install"
    OPENTOFU_INSTALL_URL = "https://opentofu.org/docs/intro/install/"

    def __init__(self, terraform: bool = False, env_vars: Optional[Dict[str, str]] = None):
        """
        Initialize TFRunner for either Terraform or OpenTofu.

        Args:
            terraform: If True, use Terraform. If False, use OpenTofu (default).
            env_vars: Environment variables to set for all executions
        """
        if terraform:
            binary = "terraform"
            error_message = (
                f"Terraform binary not found on system. "
                f"Please install Terraform following the instructions at: {self.TERRAFORM_INSTALL_URL}"
            )
        else:
            binary = "tofu"
            error_message = (
                f"OpenTofu binary not found on system. "
                f"Please install OpenTofu following the instructions at: {self.OPENTOFU_INSTALL_URL}"
            )

        super().__init__(binary=binary, error_message=error_message, env_vars=env_vars)

    def run(
        self,
        *args: str,
        env_vars: Optional[Dict[str, str]] = None,
        working_dir: Optional[Path] = None,
        interactive: bool = True,
    ):
        """
        Run the Terraform/OpenTofu binary with the given arguments.

        Args:
            *args: Command and arguments to pass (e.g., 'plan', '-out=plan.tfplan')
            env_vars: Environment variables for this specific execution
            working_dir: Working directory for command execution
            interactive: If True, run interactively. If False, capture output

        Returns:
            If interactive=True: Exit code (int)
            If interactive=False: Tuple of (exit_code, stdout, stderr)
        """
        return super().run(*args, env_vars=env_vars, working_dir=working_dir, interactive=interactive)

    def exec(self, *args: str, env_vars: Optional[Dict[str, str]] = None, working_dir: Optional[Path] = None):
        """
        Execute the Terraform/OpenTofu binary in non-interactive mode (captures output).

        This is a convenience method that calls run() with interactive=False.

        Args:
            *args: Command and arguments to pass (e.g., 'plan', '-out=plan.tfplan')
            env_vars: Environment variables for this specific execution
            working_dir: Working directory for command execution

        Returns:
            Tuple of (exit_code, stdout, stderr)
        """
        return self.run(*args, env_vars=env_vars, working_dir=working_dir, interactive=False)
