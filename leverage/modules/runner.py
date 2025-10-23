import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Optional, Tuple, Union
from leverage import logger


class Runner:
    """Generic command runner for executing system binaries with environment preservation"""

    def __init__(
        self, binary: Union[str, Path], error_message: Optional[str] = None, env_vars: Optional[Dict[str, str]] = None
    ):
        """
        Initialize Runner with a binary name or path.

        Args:
            binary: Name of the binary (searched in PATH) or full path to binary
            error_message: Custom error message when binary is not found
            env_vars: Environment variables to set for all executions
        """
        self.binary_input = binary
        self.binary_path = None
        self.error_message = error_message
        self.instance_env_vars = env_vars or {}

        self._validate_binary()
        self._validate_version()

    def _validate_binary(self):
        """Check if the required binary exists on the system"""
        binary_path = Path(self.binary_input)

        if binary_path.is_absolute() and binary_path.is_file():
            # Absolute path provided and file exists
            self.binary_path = binary_path.resolve().as_posix()
        else:
            # Try to find binary in PATH
            self.binary_path = shutil.which(str(self.binary_input))

        if not self.binary_path:
            if self.error_message:
                error_msg = self.error_message
            else:
                error_msg = (
                    f"Binary '{self.binary_input}' not found on system. "
                    f"Please install {self.binary_input} and ensure it's in your PATH."
                )

            logger.error(error_msg)
            raise RuntimeError(error_msg)

    def _validate_version(self):
        """
        Validate the binary version. Override in child classes for specific requirements.
        Base implementation does nothing - validation is optional.
        """
        pass

    def run(
        self,
        *args: str,
        env_vars: Optional[Dict[str, str]] = None,
        working_dir: Optional[Path] = None,
        interactive: bool = True,
    ) -> Union[int, Tuple[int, str, str]]:
        """
        Execute command with the binary.

        Args:
            *args: Command arguments to pass to the binary
            env_vars: Environment variables to set during execution (overrides instance env_vars)
            working_dir: Working directory for command execution
            interactive: If True, run interactively. If False, capture output

        Returns:
            If interactive=True: Exit code (int)
            If interactive=False: Tuple of (exit_code, stdout, stderr)
        """
        command = [self.binary_path, *args]

        # Merge environment variables: instance vars first, then run-time vars (run-time takes precedence)
        merged_env_vars = {**self.instance_env_vars}
        if env_vars:
            merged_env_vars.update(env_vars)

        # Create environment copy with additional variables
        env = os.environ.copy()
        env.update({k: str(v) for k, v in merged_env_vars.items()})

        logger.debug(f"[bold cyan]Running command:[/bold cyan] {' '.join(command)}")
        logger.debug(f"Working directory: {working_dir or Path.cwd()}")
        logger.debug(f"Additional environment variables: {merged_env_vars}")

        if interactive:
            # Interactive execution
            process = subprocess.run(command, env=env, cwd=working_dir)
            return process.returncode
        else:
            # Silent execution with output capture
            process = subprocess.run(command, env=env, cwd=working_dir, capture_output=True, text=True)
            return process.returncode, process.stdout.strip(), process.stderr.strip()

    def exec(
        self, *args: str, env_vars: Optional[Dict[str, str]] = None, working_dir: Optional[Path] = None
    ) -> Tuple[int, str, str]:
        """
        Execute command with the binary in non-interactive mode (captures output).

        This is a convenience method that calls run() with interactive=False.

        Args:
            *args: Command arguments to pass to the binary
            env_vars: Environment variables to set during execution (overrides instance env_vars)
            working_dir: Working directory for command execution

        Returns:
            Tuple of (exit_code, stdout, stderr)
        """
        return self.run(*args, env_vars=env_vars, working_dir=working_dir, interactive=False)

    def __repr__(self):
        return f"Runner(binary_input='{self.binary_input}', binary_path='{self.binary_path}')"
