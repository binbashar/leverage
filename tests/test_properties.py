"""
Property-based tests (hypothesis) for the parsers and generators where most of the CLI's own logic lives.

Each test states a rule that must hold for any input, and hypothesis searches for an input that breaks it.
"""

import re
import string
import tempfile
from pathlib import Path
from unittest import mock

from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

from leverage._backend_config import get_backend_key, set_backend_key
from leverage._parsing import DuplicateKeywordArgumentError, InvalidArgumentOrderError, parse_task_args
from leverage.conf import load
from leverage.modules.tf import REGION, _layer_backend_key, _make_layer_backend_key

# Building blocks shared by the tests -----------------------------------------------------------------------------

# A directory name as found in a project: account, layer or layer group
DIR_NAME = st.text(alphabet=string.ascii_lowercase + string.digits + "-_", min_size=1, max_size=20).filter(
    lambda name: name not in (".", "..")
)
# Layer directory names, built from chunks so the legacy prefixes and region-like words the backend key logic looks
# for show up anywhere in the name, not only at its start
LAYER_DIR = st.builds(
    lambda chunks, name: "".join(chunks) + name,
    st.lists(st.one_of(st.sampled_from(["base-", "tools-", "tf-", "terraform-", "global", "us-east-1-"]), DIR_NAME)),
    DIR_NAME,
).filter(lambda name: not re.fullmatch(REGION, name))
REGION_DIRS = ["us-east-1", "us-west-2", "eu-central-1", "sa-east-1", "global"]
REGION_DIR = st.sampled_from(REGION_DIRS)
# The path of a layer below the account directory: an optional region directory, then 1 to 3 levels
LAYER_PATH = st.builds(
    lambda region, parts: ([region] if region else []) + parts,
    st.one_of(st.none(), REGION_DIR),
    st.lists(LAYER_DIR, min_size=1, max_size=3),
)
# An S3 backend key, e.g. "apps-devstg/notifications/terraform.tfstate"
BACKEND_KEY = st.builds(
    lambda parts: "/".join(parts) + "/terraform.tfstate", st.lists(DIR_NAME, min_size=1, max_size=4)
)

# parse_task_args ---------------------------------------------------------------------------------------------------

# Task arguments as typed by the user: anything but the separators, without surrounding spaces
TASK_ARG = (
    st.text(
        alphabet=st.characters(blacklist_characters=",=", blacklist_categories=("Cs", "Cc")), min_size=1, max_size=15
    )
    .map(str.strip)
    .filter(bool)
)


@given(args=st.lists(TASK_ARG, max_size=4), kwargs=st.dictionaries(TASK_ARG, TASK_ARG, max_size=4))
def test_parse_task_args_round_trips(args, kwargs):
    """Joining args and kwargs the way the user types them and parsing the result gives them back."""
    arguments = ",".join([*args, *(f"{key}={value}" for key, value in kwargs.items())])

    parsed_args, parsed_kwargs = parse_task_args(arguments if arguments else None)

    if arguments:
        assert (parsed_args, parsed_kwargs) == (args, kwargs)
    else:
        assert (parsed_args, parsed_kwargs) == ([], {})


@given(arguments=st.text(max_size=30))
def test_parse_task_args_only_raises_its_own_errors(arguments):
    """Any input either parses or fails with an error the `run` command turns into a message."""
    try:
        parse_task_args(arguments)
    except (InvalidArgumentOrderError, DuplicateKeywordArgumentError):
        pass


@given(key=TASK_ARG, value=st.lists(TASK_ARG, min_size=2, max_size=3).map("=".join))
@example(key="url", value="https://example.com/?a=b")  # crashed with ValueError
def test_parse_task_args_keeps_equal_signs_in_values(key, value):
    """Only the first `=` separates the keyword: a value such as a URL query or base64 text keeps the others."""
    assert parse_task_args(f"{key}={value}") == ([], {key: value})


def _drop_legacy_prefix(name):
    """Expected naming: a single legacy prefix, `base-` or `tools-`, is dropped from the start of the name."""
    for prefix in ("base-", "tools-"):
        if name.startswith(prefix):
            return name[len(prefix) :]
    return name


# _make_layer_backend_key --------------------------------------------------------------------------------------------


@given(account=DIR_NAME, layer_path=LAYER_PATH)
@example(account="apps-devstg", layer_path=["global-accelerator"])  # was taken for a region directory
def test_layer_backend_keys_shape(account, layer_path):
    """Every accepted key belongs to the account, ends in the state file and is listed once."""
    account_dir = Path("/project") / account

    keys = _make_layer_backend_key(account_dir.joinpath(*layer_path), account_dir, account)

    assert keys
    assert len(keys) == len(set(keys))
    for key in keys:
        assert key.startswith(f"{account}/")
        assert key.endswith("/terraform.tfstate")


@given(account=DIR_NAME, layer_path=LAYER_PATH)
def test_layer_backend_keys_include_a_disaster_recovery_variant(account, layer_path):
    """The `-dr` variant goes on the first directory that is not a region directory."""
    account_dir = Path("/project") / account

    keys = _make_layer_backend_key(account_dir.joinpath(*layer_path), account_dir, account)

    parts = [_drop_legacy_prefix(part) for part in layer_path]
    first_layer_dir = 1 if layer_path[0] in REGION_DIRS else 0
    parts[first_layer_dir] += "-dr"
    assert "/".join([account, *parts, "terraform.tfstate"]) in keys


@given(account=DIR_NAME, layer_path=LAYER_PATH)
@example(account="apps-devstg", layer_path=["base-network-base-x"])  # both `base-` were dropped
def test_layer_backend_keys_only_drop_the_leading_prefix(account, layer_path):
    """One `base-` or `tools-` prefix is dropped from the start of a directory name, never from its middle."""
    account_dir = Path("/project") / account

    keys = _make_layer_backend_key(account_dir.joinpath(*layer_path), account_dir, account)

    expected = "/".join([account, *(_drop_legacy_prefix(part) for part in layer_path), "terraform.tfstate"])
    assert expected in keys


@given(account=DIR_NAME, layer_path=LAYER_PATH)
@example(account="apps-devstg", layer_path=["base-tools-x"])  # init dropped both prefixes
def test_init_backend_key_passes_validate_layout(account, layer_path):
    """The key `init` writes on a layer without one is among the keys validate-layout accepts."""
    root_dir = Path("/project")
    account_dir = root_dir / account
    layer = account_dir.joinpath(*layer_path)

    assert _layer_backend_key(layer, root_dir) in _make_layer_backend_key(layer, account_dir, account)


# set_backend_key / get_backend_key ----------------------------------------------------------------------------------

CONFIG_TF = """\
provider "aws" {{
  region  = var.region
  profile = var.profile
}}

terraform {{
  required_version = "~> 1.6"

  backend "s3" {{
{key_line}    sse_customer_key = "{other_key}"
    encrypt          = true
  }}
}}

locals {{
  key = "{other_key}"
}}
"""


def _write_config(directory, key, other_key):
    config_file = Path(directory) / "config.tf"
    key_line = f'    key = "{key}"\n' if key is not None else ""
    config_file.write_text(CONFIG_TF.format(key_line=key_line, other_key=other_key))
    return config_file


@settings(max_examples=50, deadline=None)
@given(old_key=st.one_of(st.none(), BACKEND_KEY), new_key=BACKEND_KEY, other_key=BACKEND_KEY)
def test_set_backend_key_round_trips(old_key, new_key, other_key):
    """After setting a key, reading it back gives the same key, whether there was one before or not."""
    with tempfile.TemporaryDirectory() as directory:
        config_file = _write_config(directory, old_key, other_key)

        set_backend_key(config_file, new_key)

        assert get_backend_key(config_file) == new_key


@settings(max_examples=50, deadline=None)
@given(old_key=st.one_of(st.none(), BACKEND_KEY), new_key=BACKEND_KEY, other_key=BACKEND_KEY)
def test_set_backend_key_only_changes_the_backend_key(old_key, new_key, other_key):
    """Setting the key leaves the rest of the file as it was, including other attributes named `*key`."""
    with tempfile.TemporaryDirectory() as directory:
        config_file = _write_config(directory, old_key, other_key)

        set_backend_key(config_file, new_key)

        assert config_file.read_text() == CONFIG_TF.format(key_line=f'    key = "{new_key}"\n', other_key=other_key)


# conf.load ----------------------------------------------------------------------------------------------------------

ENV_KEY = st.from_regex(r"[A-Z][A-Z0-9_]{0,10}", fullmatch=True)
# Values as used in build.env files: names, paths, versions, flags
ENV_VALUE = st.text(alphabet=string.ascii_letters + string.digits + "-_./:@", min_size=1, max_size=20)


# click_context returns a factory, so sharing it across the examples of one test is safe
@settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(levels=st.lists(st.dictionaries(ENV_KEY, ENV_VALUE, max_size=5), min_size=1, max_size=3))
def test_load_gives_the_deepest_value(levels, click_context):
    """With build.env files from the root down to the current directory, each variable takes the deepest value."""
    with tempfile.TemporaryDirectory() as root, click_context():
        directory = Path(root)
        for depth, variables in enumerate(levels):
            if depth:
                directory = directory / f"level{depth}"
                directory.mkdir()
            (directory / "build.env").write_text("".join(f"{key}={value}\n" for key, value in variables.items()))

        with (
            mock.patch("leverage.conf.get_root_path", return_value=root),
            mock.patch("leverage.conf.get_working_path", return_value=directory.as_posix()),
        ):
            loaded = load()

    expected = {}
    for variables in levels:
        expected.update(variables)
    assert loaded == expected
