from subprocess import CalledProcessError
from unittest.mock import patch, MagicMock

import pytest

from leverage.path import get_root_path, NotARepositoryError


class TestGetRootPath:
    @pytest.fixture(autouse=True)
    def setup_method(self):
        """Setup common test resources and mock patches."""
        self.mock_run_patcher = patch("leverage.path.run")
        self.mock_run = self.mock_run_patcher.start()
        yield
        self.mock_run_patcher.stop()

    def test_in_valid_git_repository(self):
        """Test get_root_path returns the correct path in a valid Git repository."""
        self.mock_run.return_value = MagicMock(stdout="path/to/repo\n")
        assert get_root_path() == "path/to/repo"

    def test_outside_of_git_repository(self):
        """Test get_root_path raises NotARepositoryError when outside a Git repository."""
        self.mock_run.side_effect = CalledProcessError(
            returncode=1, cmd=["git", "rev-parse", "--show-toplevel"], stderr="fatal: not a git repository"
        )
        with pytest.raises(NotARepositoryError):
            get_root_path()

    def test_with_git_not_installed(self):
        """Test get_root_path raises NotARepositoryError if git is not installed (FileNotFoundError)."""
        self.mock_run.side_effect = FileNotFoundError()
        with pytest.raises(NotARepositoryError):
            get_root_path()

    def test_in_a_git_submodule(self):
        """
        Test get_root_path correctly identifies the root of the main Git repository when called from within a submodule.
        """
        # Assuming submodules will have a different path structure
        self.mock_run.return_value = MagicMock(stdout="path/to/main/repo\n")
        assert get_root_path() == "path/to/main/repo"

    def test_in_newly_initialized_git_repo_without_commits(self):
        """Test get_root_path in a new Git repo that has no commits yet."""
        # In practice, this should succeed as the command works in empty repos as well
        self.mock_run.return_value = MagicMock(stdout="path/to/new/repo\n")
        assert get_root_path() == "path/to/new/repo"

    def test_with_permissions_issue_on_git_directory(self):
        """Test get_root_path behavior when there's a permissions issue on the .git directory."""
        self.mock_run.side_effect = PermissionError()
        with pytest.raises(PermissionError):
            get_root_path()

    def test_with_large_output_from_git_rev_parse(self):
        """Test get_root_path correctly handles and processes large outputs from the git rev-parse command."""
        # Simulating a large output scenario
        large_path = "path/to/repo" * 1000 + "\n"
        self.mock_run.return_value = MagicMock(stdout=large_path)
        assert get_root_path() == large_path.strip()

    def test_in_git_repo_with_unusual_characters_in_path(self):
        """Test get_root_path handles paths with spaces, special, or non-ASCII characters."""
        unusual_path = "path/to/🚀 project with spaces\n"
        self.mock_run.return_value = MagicMock(stdout=unusual_path)
        assert get_root_path() == unusual_path.strip()
