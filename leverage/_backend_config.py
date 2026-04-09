"""Utilities for modifying Terraform backend configuration."""

import re
from pathlib import Path
from typing import Union, Optional

import hcl2
import lark

from leverage._utils import ExitError


def set_backend_key(config_file_path: Union[str, Path], key: str) -> None:
    """
    Set or update the backend key in a Terraform config.tf file.

    This function modifies the Terraform backend configuration to set the S3 state key.
    It preserves all comments, formatting, and other HCL code in the file by using
    string manipulation to surgically modify only the key attribute.

    Args:
        config_file_path: Path to the config.tf file
        key: The backend key value to set (e.g., "apps-devstg/notifications/terraform.tfstate")

    Raises:
        ExitError: If the file cannot be found, cannot be parsed, or does not contain a
        terraform block with an S3 backend
    """
    config_file_path = Path(config_file_path)

    # Validate file exists
    if not config_file_path.exists():
        raise ExitError(1, f"Config file not found: {config_file_path}")

    # Read the file content
    content = config_file_path.read_text()

    # Parse the config file to validate structure
    try:
        config_tf = hcl2.loads(content)
    except Exception as e:
        raise ExitError(1, f"Failed to parse config.tf: {e}")

    # Validate that the file contains a terraform backend block with S3
    if not (
        "terraform" in config_tf
        and config_tf["terraform"]
        and isinstance(config_tf["terraform"], list)
        and "backend" in config_tf["terraform"][0]
        and config_tf["terraform"][0]["backend"]
        and isinstance(config_tf["terraform"][0]["backend"], list)
        and "s3" in config_tf["terraform"][0]["backend"][0]
    ):
        raise ExitError(
            1,
            f"Malformed config.tf: File must contain a terraform block with an S3 backend. "
            f"Expected structure:\n"
            f"terraform {{\n"
            f'  backend "s3" {{\n'
            f"    # configuration\n"
            f"  }}\n"
            f"}}",
        )

    # Check if key already exists
    backend_config = config_tf["terraform"][0]["backend"][0]["s3"]
    key_exists = "key" in backend_config

    # Modify the file content
    modified_content = _modify_backend_key(content, key, key_exists)

    # Write back to file
    config_file_path.write_text(modified_content)


def _modify_backend_key(content: str, key: str, key_exists: bool) -> str:
    """
    Modify the backend key in the HCL content.

    Args:
        content: The original file content
        key: The new key value
        key_exists: Whether the key attribute already exists

    Returns:
        Modified content with the key set
    """
    # Pattern to find the backend "s3" block
    # This matches: backend "s3" { ... }
    backend_pattern = r'(backend\s+"s3"\s*\{)'

    if key_exists:
        # Update existing key
        # Match: key = "anything" or key = "anything" with various whitespace/quotes
        key_pattern = r'(\s*key\s*=\s*)"[^"]*"'
        replacement = r'\1"' + key + '"'

        modified = re.sub(key_pattern, replacement, content)

        return modified
    else:
        # Add new key attribute
        # Find the backend "s3" block and add the key after the opening brace
        def add_key(match):
            # Get the matched backend opening
            backend_opening = match.group(1)

            # Find the indentation by looking at the next line
            remaining = content[match.end() :]
            next_line_match = re.search(r"\n(\s*)", remaining)
            if next_line_match:
                indent = next_line_match.group(1)
            else:
                indent = "    "  # Default to 4 spaces

            # Add the key attribute with proper indentation
            return f'{backend_opening}\n{indent}key = "{key}"'

        modified = re.sub(backend_pattern, add_key, content, count=1)

        return modified


def get_backend_key(config_file: Union[str, Path]) -> Optional[str]:
    """
    Get the current backend key from a Terraform config.tf file.

    Args:
        config_file: Path to the config.tf file

    Returns:
        The backend key if it exists, None otherwise

    Example:
        >>> get_backend_key("/path/to/config.tf")
        'apps-devstg/layer/terraform.tfstate'
    """
    config_file = Path(config_file)

    if not config_file.exists():
        raise ExitError(1, f"Config file not found: {config_file}")

    try:
        config_content = config_file.read_text()
        config_tf = hcl2.loads(config_content)

        if (
            "terraform" in config_tf
            and config_tf["terraform"]
            and isinstance(config_tf["terraform"], list)
            and "backend" in config_tf["terraform"][0]
            and config_tf["terraform"][0]["backend"]
            and isinstance(config_tf["terraform"][0]["backend"], list)
            and "s3" in config_tf["terraform"][0]["backend"][0]
        ):
            return config_tf["terraform"][0]["backend"][0]["s3"].get("key")
        else:
            raise ExitError(
                1,
                f"Malformed [bold]config.tf[/bold] file. Missing backend block.\n"
                f"In some cases you may want to skip this check by using the --skip-validation flag, "
                f"e.g. the first time you initialize a tf-backend layer.",
            )

    except lark.exceptions.UnexpectedInput as error:
        raise ExitError(
            1,
            f"Possible invalid expression in [bold]config.tf[/bold] near line {error.line}, column {error.column}\n"
            f"{error.get_context(config_content)}",
        )
    except Exception:
        raise ExitError(1, f"Malformed [bold]config.tf[/bold] file. Unable to parse.")
