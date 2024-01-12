from leverage._utils import key_finder


def test_key_finder_real_scenario():
    data = {
        "provider": [
            {
                "aws": {"region": "${var.region}", "profile": "${var.profile}"},
            },
        ],
        "terraform": [
            {
                "required_version": ">= 1.2.7",
                "required_providers": [{"aws": "~> 4.10", "sops": {"source": "carlpett/sops", "version": "~> 0.7"}}],
                "backend": [{"s3": {"key": "apps-devstg/notifications/terraform.tfstate"}}],
            }
        ],
        "data": [
            {
                "terraform_remote_state": {
                    "keys": {
                        "backend": "s3",
                        "config": {
                            "region": "${var.region}",
                            "profile": "${var.profile}",
                            "bucket": "${var.bucket}",
                            "key": "${var.environment}/security-keys/terraform.tfstate",
                        },
                    }
                }
            },
            {
                "sops_file": {"secrets": {"source_file": "secrets.enc.yaml"}},
            },
        ],
    }
    found = key_finder(data, "profile")

    assert found == ["${var.profile}", "${var.profile}"]


def test_key_finder_simple_scenario():
    data = {
        "test1": {
            "a": {"profile": "1a"},
            "b": {"profile": "1b"},
        },
        "test2": {"profile": "2"},
        "test3": {"profile": "3"},
    }
    found = key_finder(data, "profile")

    assert found == ["1a", "1b", "2", "3"]
