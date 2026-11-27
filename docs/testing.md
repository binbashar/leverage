# Testing the Leverage CLI

What each test suite checks, how to run it, and where a new test goes. The quick commands are in the README
([Running Tests](../README.md#running-tests)).

## The suites

| Suite | Where | Checks | Doesn't check | CI job |
|---|---|---|---|---|
| Unit | `tests/test_*.py`, `tests/test_modules/` | The logic and error branches of each module. AWS is faked at the API (real boto3 clients under `botocore.stub.Stubber`), files are real, in `tmp_path` | Real tofu/terraform/aws binaries | `unit_tests` (3.11–3.15), required |
| CLI | Same files, through Click's `CliRunner` | Arguments, exit codes, messages, the order of `--layers` | That tofu accepts what the CLI passes it | `unit_tests` |
| Properties | `tests/test_properties.py` | Invariants over generated inputs ([hypothesis](https://hypothesis.readthedocs.io/)): task arguments, backend keys, the `config.tf` round trip, `build.env` loading | Specific cases: those are example tests | `unit_tests` |
| Contract | `tests/test_refarch_contract.py` | The CLI on the real layout of [le-tf-infra-aws](https://github.com/binbashar/le-tf-infra-aws): every layer passes `validate-layout`, gets the backend key `init` writes, its tfvars and its profiles | AWS | `unit_tests` on a snapshot, `contract_tests_refarch` on the ref-arch's `master` (not required) |
| Golden files | `tests/test_modules/test_project_cli.py` | What `project create` makes of the real template, verbatim: the files, the rendered ones, that they parse and pass `validate-layout` | `tofu validate` (needs providers) | `unit_tests` |
| bats | `tests/bats/` | The installed `leverage` command with real tofu and terraform, on local-backend layers: no AWS, no network | Anything a CLI test already catches | `integration_tests` (required), `integration_tests_compat` (older and latest binaries, macOS; not required) |
| Ref-arch E2E | `.github/workflows/tests-integration.yaml` | Creates a project and applies and destroys a layer of the ref-arch in AWS | — | `integration_tests_cli_refarch`, on PRs that touch the CLI |
| Mutation | `make mutation` | That the tests of `auth.py` and `tf.py` check what they run, not just run it | — | None: by hand |

Besides the tests, CI runs ruff (with its security rules), black and mypy, and fails when unit test coverage drops below
75%.

## Running them

```bash
poetry run pytest                  # unit, CLI, properties, contract (snapshot) and golden files: ~15 s
make test-unit                     # the same, with the coverage report CI checks
bats -r tests/bats                 # needs bats, tofu and terraform; see the README
make mutation                      # a few minutes; see below
```

## Where a new test goes

Put each check at the **cheapest level that catches its bug**, and only there:

1. **Unit or CLI test** for anything the CLI decides on its own: arguments, paths, messages, exit codes, what it would
   pass to tofu. Fake AWS at the API with the Stubber, not by mocking the CLI's own functions; use real files in
   `tmp_path`.
2. **A property** when the input space is large and an invariant is easy to state (parsers, key builders). Pin any
   counterexample hypothesis finds with `@example`, so it stays in the suite.
3. **bats** only for what needs the real binary: that tofu accepts the arguments, that a real run's exit code gets
   through, that each layer runs in its own directory.
4. **Contract or golden test** when the change touches the layout the CLI expects, or what `project create` generates.

Assert the exit code of every `CliRunner` call: a command that fails silently with exit code 0 is a bug. A test that
only repeats what another one already checks at the same level makes the suite slower and harder to read, not safer
(#391 removed 29 of them).

A change that touches credentials, tokens, logging or subprocesses also goes through the checklist in
[threat-model.md](threat-model.md).

## Refreshing the snapshots

Two suites run on copies of other repositories, kept in this one so the tests don't depend on the network.

**The ref-arch** (contract tests), after le-tf-infra-aws changes its layout or conventions:

```bash
git clone --depth 1 https://github.com/binbashar/le-tf-infra-aws.git /tmp/le-tf-infra-aws
LEVERAGE_REFARCH_DIR=/tmp/le-tf-infra-aws poetry run pytest tests/test_refarch_contract.py   # every layer
python tests/refarch/snapshot.py /tmp/le-tf-infra-aws                                         # refresh the snapshot
```

**The project template** (golden files), after le-tf-infra-aws-template changes, or after a change to the CLI that
is meant to change what `project create` generates:

```bash
git clone --depth 1 https://github.com/binbashar/le-tf-infra-aws-template.git /tmp/le-tf-infra-aws-template
python tests/project_template/snapshot.py /tmp/le-tf-infra-aws-template
UPDATE_GOLDEN=1 poetry run pytest tests/test_modules/test_project_cli.py
```

Review the diff of `tests/project_template/golden/` before committing it: it is what `project create` now generates.
Each snapshot records the commit it was taken from in its `SOURCE` file.

## Mutation testing

`make mutation` runs [mutmut](https://github.com/boxed/mutmut) on `auth.py` and `tf.py`, the modules that guard
credentials and the layer layout. It changes their code one small edit at a time (a *mutant*) and runs the tests that
cover each change. A mutant no test notices *survives*: it points to a line the tests run without checking.

Run it once per quarter or before a major release. `mutmut browse` shows each survivor. Most of the ones left are log
messages and *equivalent* mutants, changes that don't alter behavior (e.g. the case of an option name, which
ConfigUpdater ignores). The config is in `[tool.mutmut]` in `pyproject.toml`; the target sets `no_proxy='*'` because
on macOS looking up the system proxies crashes mutmut's forked test runs.
