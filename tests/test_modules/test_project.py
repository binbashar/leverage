import pytest

from leverage._utils import ExitError
from leverage.modules.project import validate_config


def test_validate_config_happy_path():
    assert validate_config({"project_name": "fine"})
    assert validate_config({"project_name": "fine_with_underscores"})


def test_validate_config_errors(muted_click_context):
    with pytest.raises(ExitError, match="Project name is not valid"):
        validate_config({"project_name": "with spaces"})

    with pytest.raises(ExitError, match="Project name is not valid"):
        validate_config({"project_name": "with-hyphen"})
