import pytest

from leverage._utils import ExitError
from leverage.modules.project import validate_config


@pytest.mark.parametrize(
    "project_name,short_name",
    [
        # different valid project names
        ("fine", "ok"),
        ("fine123", "ok"),
        ("123fine", "ok"),
        ("hyphens-are-allowed", "ok"),
        # different valid short project names
        ("fine", "foo"),
        ("fine", "123"),
        ("fine", "max3"),
    ],
)
def test_validate_config_happy_path(project_name, short_name):
    assert validate_config({"project_name": project_name, "short_name": short_name})


@pytest.mark.parametrize(
    "invalid_name",
    [
        "with spaces",
        "underscores_not_allowed",
        "not-alph@-characters!",
        "loooooooooooooooooooooooooooooooooooooooooooooooooooooong",
    ],
)
def test_validate_config_project_name_errors(muted_click_context, invalid_name):
    with pytest.raises(ExitError, match="Project name is not valid"):
        validate_config({"project_name": invalid_name, "short_name": "ok"})


@pytest.mark.parametrize(
    "invalid_name",
    [
        "longerthan4",
        "1",
        "@-!#",
        "",
    ],
)
def test_validate_config_short_project_name_errors(muted_click_context, invalid_name):
    with pytest.raises(ExitError, match="Project short name is not valid"):
        validate_config({"project_name": "test", "short_name": invalid_name})
