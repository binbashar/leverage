from pathlib import Path
from unittest.mock import patch

import click
import pytest

from leverage import conf
from leverage import leverage
from leverage import path as lepath
from leverage._internals import State
from leverage.path import PathsHandler
from leverage.modules.tf import _make_layer_backend_key, _validate_layout, has_a_plan_file


@pytest.mark.parametrize(
    "args",
    [
        ([]),
        (["-migrate-state"]),
        (["-r1", "-r2"]),
    ],
)
def test_init_arguments(leverage_project, leverage_runner, args):
    """
    Test that the arguments for the init command are prepared correctly.
    """
    with leverage_runner(leverage_project) as runner:
        with patch("leverage.modules.tfrunner.TFRunner.run", return_value=0) as mocked_run:
            runner.invoke(leverage, ["tf", "init", *args])

    called_args = list(mocked_run.call_args_list[0][0])

    # Check that init was called
    assert called_args[0] == "init"

    # The layer tfvars are injected before the user arguments. They are discovered by globbing
    # the config directories, so their order depends on the filesystem and cannot be asserted.
    assert {arg for arg in called_args if arg.startswith("-var-file=")} == {
        f"-var-file={(leverage_project / 'config' / 'common.tfvars').as_posix()}",
        f"-var-file={(leverage_project / 'account' / 'config' / 'account.tfvars').as_posix()}",
        f"-var-file={(leverage_project / 'account' / 'config' / 'backend.tfvars').as_posix()}",
    }

    # Check that the user arguments are preserved and backend-config is appended last
    backend_config_arg = f"-backend-config={leverage_project / 'account' / 'config' / 'backend.tfvars'}"
    remaining_args = [arg for arg in called_args[1:] if not arg.startswith("-var-file=")]

    assert remaining_args == [*args, backend_config_arg]


def test_validate_layout_checks_the_given_layer_not_cwd(leverage_project, monkeypatch):
    """
    Regression test: `_validate_layout` must validate the *layer* it was given, not `paths.cwd`.
    Otherwise `leverage tf init --layers a,b` run from an account-level "layers-group" directory
    (e.g. account/us-east-1) always fails with "This command can only run at layer level.",
    since cwd itself - the layers-group - has no .tf files of its own, only its layer
    subdirectories do.
    """
    layers_group = leverage_project / "account" / "us-east-1"
    layer = layers_group / "security-base"

    monkeypatch.setattr(Path, "cwd", lambda: layers_group)
    monkeypatch.setattr(lepath, "get_working_path", lambda: layers_group)
    monkeypatch.setattr(lepath, "get_root_path", lambda: leverage_project)
    monkeypatch.setattr(conf, "get_root_path", lambda: leverage_project)
    monkeypatch.setattr(conf, "get_working_path", lambda: layers_group)

    state = State()
    state.verbosity = False
    state.config = conf.load()
    state.paths = PathsHandler(state.config)

    with click.Context(command=click.Command("leverage"), obj=state):
        # Must not raise ExitError("This command can only run at layer level."), which it would
        # if check_for_layer_location() fell back to checking cwd (the layers-group) instead.
        _validate_layout(layer)


@pytest.mark.parametrize(
    "args, expected_output",
    [
        # No arguments, there's no plan file
        ([], False),
        # One argument that doesn't begin with '-', it is a plan file
        (["plan_file"], True),
        # A single flag/mode, no plan file
        (["-no-color"], False),
        # A single argument that has -key=value form, no plan file
        (["-val='NAME=value'"], False),
        # One key value argument, no plan file
        (["-target", "aws_iam_role.example_role"], False),
        # One flag before a plan file
        (["-compact-warnings", "plan_file"], True),
        # One -key=value argument before a plan file
        (["-lock=false", "plan_file"], True),
        # One key value argument before a plan file
        (["-lock-timeout", "5s", "plan_file"], True),
        # Some other options
        (["-no-color", "-auto-approve"], False),
        (["-destroy", "-target", "aws_iam_role.example.role"], False),
        (["-target=aws_iam_role.example_role", "-destroy"], False),
    ],
)
def test_apply_arguments_have_plan_file(args, expected_output):
    assert has_a_plan_file(tuple(args)) == expected_output


# ###########################################################################
# EXIT CODE PROPAGATION
# ###########################################################################
# The CLI must exit with the same code as the underlying binary, so it can be relied upon in
# scripts and CI pipelines (e.g. `plan -detailed-exitcode` returns 2 when there are changes).


@pytest.mark.parametrize("binary_exit_code", [0, 1, 2])
@pytest.mark.parametrize(
    "command",
    [
        ["init"],
        ["plan"],
        ["plan", "-detailed-exitcode"],
        ["apply", "-auto-approve"],
        ["output"],
        ["destroy", "-auto-approve"],
        ["version"],
        ["format"],
        ["force-unlock", "LOCK_ID"],
        ["validate"],
        ["import", "aws_s3_bucket.example", "example-id"],
    ],
)
@pytest.mark.parametrize("group", ["tofu", "terraform"])
def test_exit_code_is_propagated(leverage_project, leverage_runner, group, command, binary_exit_code):
    with leverage_runner(leverage_project) as runner:
        with patch("leverage.modules.tfrunner.TFRunner.run", return_value=binary_exit_code) as mocked_run:
            result = runner.invoke(leverage, [group, *command])

    mocked_run.assert_called_once()
    assert result.exit_code == binary_exit_code, result.output


# Only init validates the layout by default; the mock project layers are not meant to pass it
_LAYERS_ARGS = {
    command: ["--layers", "security-base,base-tf-backend", *(["--skip-validation"] if command == "init" else [])]
    for command in ("init", "plan", "apply", "output", "destroy")
}


@pytest.mark.parametrize("command", _LAYERS_ARGS)
def test_layers_stop_at_the_first_failing_layer(leverage_project, leverage_runner, command):
    layers_group = leverage_project / "account" / "us-east-1"

    with leverage_runner(leverage_project, working_directory=layers_group) as runner:
        with patch("leverage.modules.tfrunner.TFRunner.run", side_effect=[1, 0]) as mocked_run:
            result = runner.invoke(leverage, ["tofu", command, *_LAYERS_ARGS[command]])

    assert result.exit_code == 1, result.output
    # The second layer is never reached
    mocked_run.assert_called_once()
    assert mocked_run.call_args.kwargs["working_dir"] == layers_group / "security-base"


@pytest.mark.parametrize("command", _LAYERS_ARGS)
def test_layers_run_all_layers_when_none_fails(leverage_project, leverage_runner, command):
    layers_group = leverage_project / "account" / "us-east-1"

    with leverage_runner(leverage_project, working_directory=layers_group) as runner:
        with patch("leverage.modules.tfrunner.TFRunner.run", return_value=0) as mocked_run:
            result = runner.invoke(leverage, ["tofu", command, *_LAYERS_ARGS[command]])

    assert result.exit_code == 0, result.output
    assert [call.kwargs["working_dir"] for call in mocked_run.call_args_list] == [
        layers_group / "security-base",
        layers_group / "base-tf-backend",
    ]


def _output(result):
    """The command output with its whitespace collapsed: rich wraps long log lines."""
    return " ".join(result.output.split())


# ###########################################################################
# --layers ERRORS
# ###########################################################################
@pytest.mark.parametrize(
    "location, layers, message",
    [
        # Inside a layer, --layers is not allowed
        ("account/us-east-1/security-base", "security-base", "Can not set --layers inside a layer."),
        # In a layers-group (or account) directory, --layers is required
        ("account/us-east-1", "", "--layers has to be set."),
        ("account", "", "--layers has to be set."),
        # Outside an account
        (".", "", "This command has to be run inside a layer or account directory."),
        # A layer that does not exist
        ("account/us-east-1", "security-base,missing", "does not exist or is not a directory"),
    ],
)
def test_layers_errors(leverage_project, leverage_runner, location, layers, message):
    args = ["tofu", "plan", *(["--layers", layers] if layers else [])]

    with leverage_runner(leverage_project, working_directory=leverage_project / location) as runner:
        with patch("leverage.modules.tfrunner.TFRunner.run", return_value=0) as mocked_run:
            result = runner.invoke(leverage, args)

    assert result.exit_code == 1, result.output
    assert message in _output(result)
    # Every layer is checked before running anything
    mocked_run.assert_not_called()


# ###########################################################################
# BACKEND KEY
# ###########################################################################
_CONFIG_TF_WITHOUT_KEY = 'terraform {\n  backend "s3" {\n    region = "us-east-1"\n  }\n}\n'


@pytest.mark.parametrize(
    "location, layers",
    [
        # From the layer itself
        ("account/us-east-1/security-base", []),
        # From the layers-group, with --layers
        ("account/us-east-1", ["--layers", "security-base,base-tf-backend"]),
    ],
)
def test_init_sets_the_backend_key_of_each_layer(leverage_project, leverage_runner, location, layers):
    layers_group = leverage_project / "account" / "us-east-1"
    for layer in ("security-base", "base-tf-backend"):
        (layers_group / layer / "config.tf").write_text(_CONFIG_TF_WITHOUT_KEY)

    with leverage_runner(leverage_project, working_directory=leverage_project / location) as runner:
        with patch("leverage.modules.tfrunner.TFRunner.run", return_value=0):
            result = runner.invoke(leverage, ["tofu", "init", *layers])

    assert result.exit_code == 0, result.output
    assert (
        'key = "account/us-east-1/security-base/terraform.tfstate"'
        in (layers_group / "security-base" / "config.tf").read_text()
    )
    if layers:
        # The base- prefix is dropped from the key
        assert (
            'key = "account/us-east-1/tf-backend/terraform.tfstate"'
            in (layers_group / "base-tf-backend" / "config.tf").read_text()
        )


@pytest.mark.parametrize(
    "layer, expected",
    [
        # Region directory: the key may or may not include it, and may carry the DR suffix
        (
            "us-east-1/security-base",
            [
                "acc/security-base/terraform.tfstate",
                "acc/security-base-dr/terraform.tfstate",
                "acc/us-east-1/security-base/terraform.tfstate",
                "acc/us-east-1/security-base-dr/terraform.tfstate",
            ],
        ),
        # base- and tools- prefixes are dropped; tf- and terraform- are interchangeable
        (
            "us-east-1/base-tf-backend",
            [
                "acc/tf-backend/terraform.tfstate",
                "acc/tf-backend-dr/terraform.tfstate",
                "acc/terraform-backend/terraform.tfstate",
                "acc/terraform-backend-dr/terraform.tfstate",
                "acc/us-east-1/tf-backend/terraform.tfstate",
                "acc/us-east-1/tf-backend-dr/terraform.tfstate",
                "acc/us-east-1/terraform-backend/terraform.tfstate",
                "acc/us-east-1/terraform-backend-dr/terraform.tfstate",
            ],
        ),
        (
            "global/tools-vpn-server",
            [
                "acc/vpn-server/terraform.tfstate",
                "acc/vpn-server-dr/terraform.tfstate",
                "acc/global/vpn-server/terraform.tfstate",
                "acc/global/vpn-server-dr/terraform.tfstate",
            ],
        ),
        (
            "apps/terraform-state",
            [
                "acc/apps/terraform-state/terraform.tfstate",
                "acc/apps-dr/terraform-state/terraform.tfstate",
                "acc/apps/tf-state/terraform.tfstate",
                "acc/apps-dr/tf-state/terraform.tfstate",
            ],
        ),
        # No region directory: the DR suffix goes on the first directory
        (
            "apps/backend",
            [
                "acc/apps/backend/terraform.tfstate",
                "acc/apps-dr/backend/terraform.tfstate",
            ],
        ),
    ],
)
def test_make_layer_backend_key(tmp_path, layer, expected):
    account_dir = tmp_path / "acc"
    assert sorted(_make_layer_backend_key(account_dir / layer, account_dir, "acc")) == sorted(expected)


# ###########################################################################
# validate-layout
# ###########################################################################
def _validate_layout_in(leverage_project, leverage_runner, layer="account/us-east-1/security-base"):
    with leverage_runner(leverage_project, working_directory=leverage_project / layer) as runner:
        return runner.invoke(leverage, ["tofu", "validate-layout"])


def test_validate_layout_ok(leverage_project, leverage_runner):
    result = _validate_layout_in(leverage_project, leverage_runner)

    assert result.exit_code == 0, result.output
    assert "FAILED" not in result.output


def test_validate_layout_without_environment(leverage_project, leverage_runner):
    (leverage_project / "account" / "config" / "account.tfvars").write_text('sso_role = "test-sso-role"\n')

    result = _validate_layout_in(leverage_project, leverage_runner)

    assert result.exit_code == 1, result.output
    assert "FAILED" in result.output


def test_validate_layout_wrong_backend_key(leverage_project, leverage_runner):
    config_tf = leverage_project / "account" / "us-east-1" / "security-base" / "config.tf"
    config_tf.write_text(config_tf.read_text().replace("security-base/", "other-layer/"))

    result = _validate_layout_in(leverage_project, leverage_runner)

    assert result.exit_code == 1, result.output
    assert "Expected one of: account/security-base/terraform.tfstate;" in _output(result)
    assert "FAILED" in result.output


def test_validate_layout_wrong_backend_tfvars(leverage_project, leverage_runner):
    (leverage_project / "account" / "config" / "backend.tfvars").write_text('bucket = "other-bucket"\n')

    result = _validate_layout_in(leverage_project, leverage_runner)

    assert result.exit_code == 1, result.output
    # profile, bucket and dynamodb_table
    assert result.output.count("FAILED") == 3


def test_validate_layout_warns_when_the_account_directory_does_not_match(leverage_project, leverage_runner):
    (leverage_project / "account" / "config" / "account.tfvars").write_text(
        'environment = "apps-devstg"\nsso_role = "test-sso-role"\n'
    )

    result = _validate_layout_in(leverage_project, leverage_runner)

    assert "Account directory name does not match environment name" in _output(result)


def test_init_stops_on_an_invalid_layout(leverage_project, leverage_runner):
    (leverage_project / "account" / "config" / "backend.tfvars").write_text('bucket = "other-bucket"\n')

    with leverage_runner(leverage_project) as runner:
        with patch("leverage.modules.tfrunner.TFRunner.run", return_value=0) as mocked_run:
            result = runner.invoke(leverage, ["tofu", "init"])

    assert result.exit_code == 1, result.output
    assert "Layer configuration doesn't seem to be valid" in _output(result)
    mocked_run.assert_not_called()
