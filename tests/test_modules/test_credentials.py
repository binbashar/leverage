from unittest import mock
from unittest.mock import Mock

from leverage.modules.credentials import _load_configs_for_credentials


@mock.patch(
    "leverage.modules.credentials._load_project_yaml",
    Mock(
        return_value={
            "short_name": "test",
            "region": "us-test-1",
            "organization": {
                "accounts": [
                    {"name": "acc2"},
                ]
            },
        }
    ),
)
@mock.patch(
    "leverage.modules.credentials.AWSCLI",
    Mock(
        env_conf={
            "PROJECT": "test",
            "MFA_ENABLED": "true",
        },
        paths=Mock(
            common_conf={
                "project_long": "test-prjt",
                "region_secondary": "us-test-2",
                "accounts": {
                    "acc1": {
                        "email": "test@test.com",
                        "id": "123456",
                    }
                },
            },
        ),
    ),
)
def test_load_configs_for_credentials(with_click_context):
    assert _load_configs_for_credentials() == {
        "mfa_enabled": "true",
        "organization": {
            "accounts": [
                {
                    "email": "test@test.com",
                    "id": "123456",
                    "name": "acc1",
                },
                {
                    "name": "acc2",
                },
            ]
        },
        "primary_region": "us-test-1",
        "project_name": "test-prjt",
        "secondary_region": "us-test-2",
        "short_name": "test",
    }
