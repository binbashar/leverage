import pytest

from leverage._utils import ExitError
from leverage.modules.project import validate_config


def test_validate_config_happy_path():
    assert validate_config({"project_name": "fine"})
    assert validate_config({"project_name": "fine123"})
    assert validate_config({"project_name": "123fine"})
    assert validate_config({"project_name": "hyphens-are-allowed"})


def test_validate_config_errors(muted_click_context):
    with pytest.raises(ExitError, match="Project name is not valid"):
        validate_config({"project_name": "with spaces"})

    with pytest.raises(ExitError, match="Project name is not valid"):
        validate_config({"project_name": "underscores_not_allowed"})

    with pytest.raises(ExitError, match="Project name is not valid"):
        validate_config({"project_name": "not-alph@-characters!"})

    with pytest.raises(ExitError, match="Project name is not valid"):
        validate_config({"project_name": "loooooooooooooooooooooooooooooooooooooooooooooooooooooong"})
