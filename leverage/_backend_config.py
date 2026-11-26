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
            "Malformed config.tf: File must contain a terraform block with an S3 backend. "
            "Expected structure:\n"
            "terraform {\n"
            '  backend "s3" {\n'
            "    # configuration\n"
            "  }\n"
            "}",
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

    The searches run on a copy of the content with its comments blanked out, so a commented
    `backend "s3" {` or `key = "..."` is never taken for the active one. Positions match the original.

    Args:
        content: The original file content
        key: The new key value
        key_exists: Whether the key attribute already exists

    Returns:
        Modified content with the key set
    """
    searchable = _blank_comments(content)
    backend = re.search(r'backend\s+"s3"\s*\{', searchable)
    if backend is None:
        return content
    body_start = backend.end()

    if key_exists:
        # Update the existing key, only inside the backend block: other attributes ending in `key`
        # (`sse_customer_key`) or a `key` in another block (`locals`) must stay as they are
        body_end = _find_closing_brace(searchable, body_start)
        # Only the backend's own `key`, not one nested in a value such as `assume_role = { tags = { key = ... } }`
        top_level = _blank_nested_blocks(searchable, body_start, body_end)
        current = re.compile(r'(?<![\w-])key\s*=\s*"[^"]*"').search(top_level, body_start, body_end)
        if current is None:
            return content
        assignment = content[current.start() : current.end()]
        value_start = current.start() + assignment.index('"')
        return f'{content[:value_start]}"{key}"{content[current.end():]}'

    # Add the key right after the opening brace, with the indentation of the line that follows
    next_line = re.match(r"[^\n]*\n([ \t]*)", content[body_start:])
    indent = next_line.group(1) if next_line else "    "
    return f'{content[:body_start]}\n{indent}key = "{key}"{content[body_start:]}'


def _blank_comments(content: str) -> str:
    """Return the content with every comment (`#`, `//`, `/* */`) replaced by spaces, keeping newlines and length."""
    chars = list(content)
    index = 0
    while index < len(content):
        if content[index] == '"':
            # Skip the string, honoring escaped quotes
            index += 1
            while index < len(content) and content[index] != '"':
                index += 2 if content[index] == "\\" else 1
            index += 1
            continue
        if content[index] == "#" or content.startswith("//", index):
            end = content.find("\n", index)
            end = len(content) if end == -1 else end
        elif content.startswith("/*", index):
            end = content.find("*/", index + 2)
            end = len(content) if end == -1 else end + 2
        else:
            index += 1
            continue
        for position in range(index, end):
            if chars[position] != "\n":
                chars[position] = " "
        index = end
    return "".join(chars)


def _blank_nested_blocks(content: str, start: int, end: int) -> str:
    """Return the content with whatever sits inside `{}` nested in `[start, end)` replaced by spaces, keeping
    newlines and length. Expects content without comments (see `_blank_comments`)."""
    chars = list(content)
    depth = 0
    index = start
    while index < end:
        char = content[index]
        string_start = index
        if char == '"':
            # Skip the string, honoring escaped quotes
            index += 1
            while index < end and content[index] != '"':
                index += 2 if content[index] == "\\" else 1
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        if depth > 0 or char == "}":
            for position in range(string_start, min(index + 1, end)):
                if chars[position] != "\n":
                    chars[position] = " "
        index += 1
    return "".join(chars)


def _find_closing_brace(content: str, start: int) -> int:
    """Return the index of the `}` that closes the block whose body starts at `start`, skipping strings.

    Expects content without comments (see `_blank_comments`)."""
    depth = 1
    index = start
    while index < len(content):
        char = content[index]
        if char == '"':
            # Skip the string, honoring escaped quotes
            index += 1
            while index < len(content) and content[index] != '"':
                index += 2 if content[index] == "\\" else 1
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return len(content)


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
                "Malformed [bold]config.tf[/bold] file. Missing backend block.\n"
                "In some cases you may want to skip this check by using the --skip-validation flag, "
                "e.g. the first time you initialize a tf-backend layer.",
            )

    except lark.exceptions.UnexpectedInput as error:
        raise ExitError(
            1,
            f"Possible invalid expression in [bold]config.tf[/bold] near line {error.line}, column {error.column}\n"
            f"{error.get_context(config_content)}",
        )
    except ExitError:
        # Let our own, more specific errors (e.g. missing backend block) through untouched
        raise
    except Exception:
        raise ExitError(1, "Malformed [bold]config.tf[/bold] file. Unable to parse.")
