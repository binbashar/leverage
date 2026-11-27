# Leverage CLI threat model

What the CLI protects, where it can leak, and what keeps it from leaking. Review it when a change touches
credentials, tokens, logging, the processes the CLI runs, or what it downloads.

Last reviewed: 2026-11-27 (#346).

## What there is to protect

| Asset | Where | Who writes it | Worth to an attacker |
|---|---|---|---|
| SSO access token | `~/.aws/<project>/sso/cache/token` | `leverage aws sso login` | **Highest.** Until it expires (8 h by default) it gets credentials for every account and role the user has |
| Temporary role credentials | `~/.aws/<project>/credentials` | SSO and MFA credential refresh | Access to one account with one role, until they expire |
| MFA cached credentials | `~/.aws/<project>/cache/<profile>` | MFA credential refresh | Same as above |
| Static IAM keys (MFA mode) | `~/.aws/<project>/credentials` | `leverage credentials configure`, through the AWS CLI | Long-lived access, until rotated |
| AWS config | `~/.aws/<project>/config` | `leverage aws configure sso`, AWS CLI | Not a secret: account IDs, role names, SSO start URL. Useful for reconnaissance |

## Where it can leak, and what stops it

| # | Threat | Status |
|---|---|---|
| T1 | **Another user on the same machine reads the token or credentials** (shared hosts, bastions, CI runners, macOS `staff` group) | **Mitigated.** The files above are created `0600` and their directories `0700`, as the AWS CLI does (`leverage/_utils.py`: `make_private_dir`, `make_private_file`). Files written by older versions are tightened the next time the CLI writes them. `config` is left as the AWS CLI writes it |
| T2 | **Secrets printed in a traceback** to the terminal or CI logs | **Mitigated.** Logged tracebacks never show local variables (`tracebacks_show_locals=False` in `leverage/logger.py`); they did before, and the credential code's locals hold the token and the keys |
| T3 | **Secrets in debug logs** (`--verbose`) | **Holds today, by rule.** The runner logs the command and the extra environment variables it sets: only file paths (`AWS_CONFIG_FILE`, `AWS_SHARED_CREDENTIALS_FILE`, `KUBECONFIG`). **Never pass a secret through `env_vars` or as a command argument**; tofu/terraform/aws read credentials from those files |
| T4 | **Child processes get more than they need** | **Accepted.** They inherit the user's whole environment plus those paths: they are the user's own tools, run on the user's behalf |
| T5 | **A malicious or compromised project repository** | **Out of scope, by design.** The CLI trusts the project the way `make` trusts a Makefile: `leverage run` executes `build.py`, `TF_BINARY` in `build.env` picks the binary that gets the credentials, and the `.tf` files choose providers and modules. Review changes to `build.py` and `build.env` like code |
| T6 | **A compromised project template** | **Partly mitigated.** `leverage project init` clones `le-tf-infra-aws-template` from `master`, unpinned, over HTTPS. A change there reaches every new project. Protected by that repo's branch protection; pinning a release tag would close it |
| T7 | **Stolen SSO token** | **Limited by its lifetime.** `leverage aws sso logout` revokes it with AWS and deletes it and the credentials, even when the token is already invalid (#352) |
| T8 | **A vulnerable dependency** | Dependabot alerts and weekly updates, CodeQL (#358) |
| T9 | **Insecure code patterns** (shell injection, unsafe YAML or pickle, temp files, hardcoded secrets) | ruff's `S` rules (bandit) in the required `lint` check. Each accepted finding in `leverage/` has a `noqa: S...` with its reason |
| T10 | **Static AWS keys in CI** | The ref-arch integration test uses them; moving it to OIDC is #337 |

## Checklist for changes

- A new file holding a secret: create it with `write_private_file`/`make_private_file`, in a directory made with `make_private_dir`, and test its mode.
- A new log line: no tokens, keys, passwords or `Credentials` dicts, not even at debug level.
- A new subprocess: a list of arguments, never `shell=True`; secrets through files, not arguments or env vars.
- A new download (git clone, HTTP): from where, pinned or not, and over HTTPS.
