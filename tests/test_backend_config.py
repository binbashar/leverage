"""Tests for backend configuration utilities."""

import pytest
from leverage._backend_config import set_backend_key, get_backend_key
from leverage._utils import ExitError


@pytest.fixture
def config_without_key(tmp_path):
    """Create a config.tf file without a backend key."""
    config_file = tmp_path / "config.tf"
    content = """# This is a comment
terraform {
  required_version = ">= 1.0"

  # Backend configuration
  backend "s3" {
    bucket = "my-terraform-state"
    region = "us-east-1"
    # More config here
  }
}

# Another comment
resource "aws_instance" "example" {
  ami = "ami-12345"
}
"""
    config_file.write_text(content)
    return config_file


@pytest.fixture
def config_with_key(tmp_path):
    """Create a config.tf file with an existing backend key."""
    config_file = tmp_path / "config.tf"
    content = """# This is a comment
terraform {
  required_version = ">= 1.0"

  # Backend configuration
  backend "s3" {
    bucket = "my-terraform-state"
    key    = "old/path/terraform.tfstate"
    region = "us-east-1"
  }
}

# Another comment
resource "aws_instance" "example" {
  ami = "ami-12345"
}
"""
    config_file.write_text(content)
    return config_file


@pytest.fixture
def config_without_backend(tmp_path):
    """Create a config.tf file without a backend block."""
    config_file = tmp_path / "config.tf"
    content = """terraform {
  required_version = ">= 1.0"
}
"""
    config_file.write_text(content)
    return config_file


def test_set_backend_key_adds_key_when_missing(config_without_key):
    """Test that set_backend_key adds a key when it doesn't exist."""
    new_key = "apps-devstg/notifications/terraform.tfstate"

    set_backend_key(config_without_key, new_key)

    # Verify the key was added
    assert get_backend_key(config_without_key) == new_key

    # Verify comments and other content are preserved
    content = config_without_key.read_text()
    assert "# This is a comment" in content
    assert "# Backend configuration" in content
    assert "# Another comment" in content
    assert 'resource "aws_instance" "example"' in content
    assert 'bucket = "my-terraform-state"' in content


def test_set_backend_key_updates_existing_key(config_with_key):
    """Test that set_backend_key updates an existing key."""
    new_key = "apps-prod/notifications/terraform.tfstate"

    # Verify old key exists
    assert get_backend_key(config_with_key) == "old/path/terraform.tfstate"

    set_backend_key(config_with_key, new_key)

    # Verify the key was updated
    assert get_backend_key(config_with_key) == new_key

    # Verify comments and other content are preserved
    content = config_with_key.read_text()
    assert "# This is a comment" in content
    assert "# Backend configuration" in content
    assert "# Another comment" in content
    assert 'resource "aws_instance" "example"' in content

    # Verify old key is not present
    assert "old/path/terraform.tfstate" not in content


def test_set_backend_key_preserves_formatting(config_without_key):
    """Test that formatting is preserved when adding a key."""
    original_content = config_without_key.read_text()
    original_lines = original_content.split("\n")

    set_backend_key(config_without_key, "test/key/terraform.tfstate")

    new_content = config_without_key.read_text()
    new_lines = new_content.split("\n")

    # When adding a key, we expect exactly one new line to be inserted
    # Count how many original lines are still present in the new content
    unchanged_lines = sum(1 for line in original_lines if line in new_lines)

    # Most lines should be unchanged (allow for the one added line)
    assert unchanged_lines / len(original_lines) > 0.8


def test_get_backend_key_returns_none_for_missing_key(config_without_key):
    """Test that get_backend_key returns None when key doesn't exist."""
    assert get_backend_key(config_without_key) is None


def test_get_backend_key_raises_for_missing_file(tmp_path):
    """Test that get_backend_key raises ExitError for non-existent file."""
    with pytest.raises(ExitError, match="Config file not found"):
        get_backend_key(tmp_path / "nonexistent.tf")


def test_set_backend_key_raises_for_missing_file(tmp_path):
    """Test that set_backend_key raises ExitError for missing file."""
    with pytest.raises(ExitError, match="Config file not found"):
        set_backend_key(tmp_path / "nonexistent.tf", "some/key")


def test_set_backend_key_raises_for_missing_backend(config_without_backend):
    """Test that set_backend_key raises ExitError when backend block is missing."""
    with pytest.raises(ExitError, match="Malformed config.tf"):
        set_backend_key(config_without_backend, "some/key")


def test_get_backend_key_raises_for_missing_backend(config_without_backend):
    """Test that get_backend_key raises ExitError when backend block is missing."""
    with pytest.raises(ExitError, match="Malformed"):
        get_backend_key(config_without_backend)


def test_set_backend_key_with_complex_formatting(tmp_path):
    """Test with various formatting styles."""
    config_file = tmp_path / "config.tf"
    content = """terraform {
  backend "s3" {
    # Comments inside backend
    bucket         = "my-bucket"  # inline comment
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "terraform-locks"
  }
}
"""
    config_file.write_text(content)

    set_backend_key(config_file, "test/terraform.tfstate")

    # Verify key was added
    assert get_backend_key(config_file) == "test/terraform.tfstate"

    # Verify other attributes and comments are preserved
    new_content = config_file.read_text()
    assert "# Comments inside backend" in new_content
    assert "# inline comment" in new_content
    assert "bucket" in new_content
    assert "dynamodb_table" in new_content
