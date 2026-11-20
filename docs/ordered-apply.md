# Ordered apply for a Leverage repo

Proposal. How any Leverage reference-architecture repo orders its layers
and how a push to the default branch applies only the layers whose plan
has a diff. The account names, profile names, and role ARNs below are
the slots a repo fills in. Nothing here depends on one organization's
accounts.

## Layout the design expects

A Leverage repo is one Git repository and many OpenTofu roots.

```
<repo>/
  config/common.tfvars          # project, region, sso_enabled, account ids
  config/ci-roles.json          # profile name → role ARN, used only by --ci
  <account>/
    config/account.tfvars       # environment = "<environment>"
    config/backend.tfvars       # profile, bucket, region, dynamodb_table
    <region-or-global>/
      <layer>/                  # one OpenTofu root
        config.tf               # backend "s3" { key = "..." }
        *.tf
```

An account is a directory at the repo root that contains
`config/account.tfvars`. Account directory names are whatever that repo
uses (`management`, `security`, `shared`, and its workload accounts).
The graph discovers them. It does not ship a fixed list.

`config/common.tfvars` holds the project short name (`project`), the
primary region, and `sso_enabled`. Each account's `account.tfvars` holds
`environment`. Some repos set `environment` to the directory name with
hyphens removed. The graph uses the string in the file, not a guess.

A layer is a directory under an account whose `.tf` files contain
`backend "s3" { key = "..." }`. That key is the layer's identity. It
often differs from the directory path: a directory
`<account>/<region>/base-network` may store state at
`<account>/network/terraform.tfstate`. The state bucket and the DynamoDB
lock table are named in `<account>/config/backend.tfvars` and live in
that account.

`backend.tfvars` also names the AWS profile OpenTofu uses for the state
of that account. Other profiles appear as `profile = "..."` on providers
and remote-state data sources inside the layer. A single profile name
can both read another account's state and create resources in that
account. The design keeps those names and points them at roles. It does
not invent a second profile for the same hop.

Skip `modules/`, `.terraform/`, a `TMP_FILES/` scratch directory, and any
directory whose name starts with a dot. Those are not layers.

OpenTofu in CI is pinned to the version the repo already plans with. A
newer binary on a laptop accepts syntax CI rejects.

## What depends on what

One layer depends on another only when it reads that layer's state.
The reads that count are:

- `data "terraform_remote_state"` with a `key`
- a module argument `key = ".../terraform.tfstate"`, including keys
  passed through a shared module and keys inside a `for_each` map in
  `locals.tf`

OpenTofu already orders resources inside one layer. That does not apply
any other layer.

A read of the layer's own backend key is not a dependency.
`${var.environment}` in a key is replaced with the `environment` value
from that account's `account.tfvars`. A key that still contains `${...}`
after that replacement, or that matches no layer, is a warning and is
not an edge. A warning names the reading layer and the key. The walk
still runs. The missing state is a problem for that layer's plan, which
then stops the walk on exit code 1.

These are not edges, even when the resources are related:

- an IAM role ARN typed in by hand
- a DNS name written as a string
- `depends_on` between resources in the same layer
- Python task order in the repo's `build.py`
- a report that only prints the remote-state keys of the current layer

## How the order is built

1. Find every account directory, then every layer under it, using the
   rules above. Strip `#` comments, `//` comments, and `/* */` blocks
   that sit outside strings before searching for keys.
2. Collect every `key = "...terraform.tfstate"` in the layer. Drop the
   layer's own backend key. Resolve `${var.environment}`.
3. Match each remaining key to the layer that owns it. An edge means
   the owner is applied before the reader. A key owned by two layers is
   a graph error. Construction stops, and nothing is planned or applied.
   Those two roots would write the same state file.
4. Find the strongly connected sets. Walk forward (reader after owner)
   and record the finish order. Then walk the reverse edges, starting
   from vertices in decreasing finish time: reverse the finish list,
   and collect a set from each vertex not yet placed. A set of one
   layer is a real precedence. A set of more than one layer is a cycle:
   those layers read each other.
5. Order the sets with a queue. A set is ready when every set it depends
   on is already emitted. When several sets are ready, sort them with
   the tie-break below. Do not reverse the result.

Tie-break, used only when the graph does not decide. Each repo writes
this once, next to the graph, as two ordered lists:

1. Account directory names, earliest first. A typical reference layout
   is the management account, then the security account, then the shared
   account, then workload accounts.
2. Path kinds inside an account: a backend layer, then an identities or
   organizations layer, then a network or security-baseline layer, then
   everything else by directory path.

A real remote-state edge always beats the tie-break.

Cycles show up where two layers read each other. VPC peering and a DNS
association that each side records are the usual cases. Both states
already exist, and either side can be updated, so there is no safe total
order. The edges stay. Members are listed in tie-break order and marked
as a cycle. Layers that only read the mesh stay outside it, so a network
layer still precedes the cluster that reads it.

A first-time bring-up of a cyclic mesh is two passes done by a person.
Create the resources that do not read each other. Apply the peering or
association after both sides exist.

## What the CLI can already do

`leverage tf init`, `plan`, `apply`, `output`, and `destroy` accept
`--layers`, a comma-separated list of paths relative to the current
directory. The list is visited in the order given. The command does not
discover layers and does not sort them.

The flag is accepted in two places:

- an account directory
- a directory under an account that contains no `.tf` files (a
  layers-group). A DNS directory whose zones are child layers is one.

The flag is rejected inside a layer and at the repository root. One list
cannot name a layer in another account.

`validate` has no `--layers` flag. After `init`, `tofu validate` in each
layer directory is the check, on the CI OpenTofu version.

Extra arguments are forwarded to every layer in the list, with that
layer as the working directory. `-out=tfplan` writes a separate `tfplan`
in each layer. The matching apply is the same list plus the plan file
name. When the last argument is a plan file, the CLI does not prepend
`-var-file`. A plan file does not prompt.

Human commands do not pass `-auto-approve`. Each apply still asks for
confirmation.

```bash
cd <account>/<layers-group>
leverage tf init --layers layer-a,layer-b
leverage tf plan -input=false -out=tfplan --layers layer-a,layer-b
leverage tf apply --layers layer-a,layer-b tfplan
```

On a laptop, `sso_enabled = true`. Running `init`, `plan`, or `apply`
from inside a layer checks the SSO token and refreshes short-lived keys
into `~/.aws/<project>/`. The process is pointed at that directory's
`config` and `credentials` files. From an account directory that refresh
is skipped, but OpenTofu still reads the same files. Profile names in
the `.tf` files are filled from the SSO session: a profile
`<project>-<account-name>-<role>` is minted from the SSO profile
`<project>-sso-<account-name>`. There is no SSO token on a CI
runner, so the same command fails there until `--ci` exists.

`plan -detailed-exitcode` exits 0 when nothing changed, 2 when the plan
has changes, and 1 on a real error. The CLI today treats every non-zero
exit as failure. The ordered walker does not. For a single layer, exit
2 applies the saved plan and the walk continues. Any other non-zero
exit stops the walk. For a cycle, any exit 2 stops the walk before that
cycle is applied.

Layers in one `--layers` invocation run one after another, in one
process. Independent layers are not applied at the same time. Each layer
still runs its own `tofu`.

## Two new commands

### Sort one account

```bash
cd <account>
leverage tf apply -input=false --order --layers <layer-a>,<layer-b>
```

`--order` sorts that set with the subgraph, then the existing `--layers`
loop runs. Paths stay relative to the account. A cycle inside the set is
printed and the apply stops. `--allow-cycle` means the operator will
apply that mesh by hand, in the two-pass order above, and the command
may continue with the layers after the cycle. `--layers` without
`--order` still visits the list in the given order.

### Walk the whole repo

`leverage tf apply-ordered` runs from the repository root. It loads the
full graph and walks every component.

Consecutive layers in the same account become one `--layers` run. A
change of account starts a new run. A cycle is its own group and is not
merged with the layers before or after it.

For a single layer, when the walk reaches it:

1. `tofu init` with that account's `backend.tfvars`, `config/common.tfvars`,
   and `<account>/config/account.tfvars`.
2. `tofu plan -input=false -no-color -lock-timeout=120s -detailed-exitcode -out=<temp file>`.
3. Exit 0: delete the file and continue.
4. Exit 2: `tofu apply -input=false -no-color -lock-timeout=120s <that file>`, then delete the file.
5. Any other exit: stop. Nothing after this layer is planned or applied.

For a cycle, plan every member. If any plan exits 2, stop before
applying those layers and before anything after them. If every plan
exits 0, skip the cycle and continue.

Plans are made when the layer is reached, not all at once at the start.
A layer applied earlier in the same walk is already in state when a
later layer plans. The walk does not add extra prerequisites: they have
already been planned, and applied when they had a diff.

Selectors:

| Invocation | What it walks |
| --- | --- |
| No layer arguments | Every layer in the repo. |
| One or more layer paths | Only those layers, using edges among them. |
| Those paths plus `--with-deps` | Those layers plus every layer they read, transitively. |
| `--account <directory>` | Layers in that account. Layers they read in other accounts are assumed already applied and are printed as comments. |
| `--plan` | Plan only. Print the diff. Do not apply. |
| `--list` | One repo-relative path per line, no commands. |

`--with-deps` is for a first apply of a new layer, when the layers it
reads may not exist yet. If it reads a member of a cycle, the whole
cycle is included and stays marked.

Human use of `apply-ordered` still confirms each apply. `--ci` is what
applies a saved plan file with no prompt.

## `--ci` for any CI

`--ci` is a flag on `leverage tf`. It is how a job runs the commands
above without an SSO token. Leverage does not know which CI product
started the job.

```bash
leverage tf apply-ordered --ci
```

The CI's job is to prove who is running. It does that with an OIDC JWT
whose issuer and subject AWS can check. Leverage only needs a way to
read that JWT, then it calls `AssumeRoleWithWebIdentity` for the role of
the account it is about to touch.

Set `LEVERAGE_CI_TOKEN_COMMAND` to a program that prints a JWT to stdout
and exits 0. Leverage runs it once per exchange. The program requests
the audience that AWS expects for that issuer, usually
`sts.amazonaws.com`. A file path in `LEVERAGE_CI_TOKEN_FILE` is the same
contract when the CI writes the JWT to disk instead of requiring a
command.

AWS returns `AccessKeyId`, `SecretAccessKey`, and `SessionToken`. Every
AWS API call is signed with those three values. They exist only in the
runner's memory for the role session. They are not an IAM user key, and
they are not stored as a CI secret.

`credential_process` caches those three values until shortly before the
role session ends. It runs the token command only when it needs a new
exchange. Each account and each provider profile is a separate
exchange, and that exchange needs a JWT that is still valid. A longer
role session does not extend the JWT. A CI that can mint a JWT at any
moment during the job can refresh mid-walk. A CI that mints one JWT
when the job starts can finish only if that JWT is still valid for
every exchange. The token command must succeed on every call. A JWT
that is already expired fails the refresh.

Calling `sts:AssumeRole` with credentials that are already temporary is
role chaining. AWS caps that second hop at one hour, even when the role
allows a longer session. With a token command, `--ci` does not chain.
Each account, and each provider profile, is its own
`AssumeRoleWithWebIdentity`.

When `LEVERAGE_CI_TOKEN_COMMAND` and `LEVERAGE_CI_TOKEN_FILE` are both
unset, `--ci` uses the AWS credentials already in the environment. That
is the fallback for a CI that exchanged OIDC itself, or for a runner
role. Per-account hops are then `sts:AssumeRole` from those credentials,
refreshed before the one-hour cap. Prefer the token command when the CI
can supply a JWT.

`--ci` does not prompt. It fails when there is no token command, no
token file, and no ambient AWS credentials. A laptop session keeps using
`leverage aws sso login`.

### What each CI supplies

Leverage stays the same. Each CI adds three things: a token program, a
trust policy on the apply roles, and a pipeline that runs only on the
default branch.

| CI | How the token program gets a JWT | Where the subject comes from |
| --- | --- | --- |
| GitHub Actions | `POST` to `ACTIONS_ID_TOKEN_REQUEST_URL` with `ACTIONS_ID_TOKEN_REQUEST_TOKEN`. The job needs `id-token: write`. A new JWT can be requested for the whole job. | Decode `sub` from a token of the apply job. A branch job is often `repo:<org>/<repo>:ref:refs/heads/<branch>`. A job that names an environment uses `environment:` instead. Repositories can also require an immutable id in the subject. |
| GitLab CI | An `id_tokens:` entry on the job, audience `sts.amazonaws.com`. GitLab puts the JWT in an environment variable at job start. | Decode `sub` from a token of the apply job. The default is often `project_path:<group>/<repo>:ref_type:branch:ref:<branch>`. The project can change that claim. |
| Buildkite, CircleCI, Bitbucket Pipelines, Azure DevOps | Each product's documented OIDC token for the job. Most issue it once at the start. | That product's documented repository or job claim for the apply job, copied from a real token. |
| Anything else | A program that prints a JWT, or ambient AWS credentials. | The CI's documented repository or job claim. The issuer is not the subject. |

The trust policy uses the exact `sub` from a token minted for the apply
job. The examples above are common shapes, not a format to generate.
The issuer URL is a separate setting: it is registered once per AWS
account as an IAM OIDC provider. GitHub's issuer is
`token.actions.githubusercontent.com`. GitLab's is the GitLab host. A
second CI is a second provider and a second statement on the same apply
role, or a separate role and a separate `config/ci-roles.json` selected
by the pipeline.

A review pipeline (pull request, merge request) must not satisfy the
subject. The apply pipeline's definition is the one on the default
branch. A change to the pipeline is applied by a person until it has
been merged.

### The role map

`config/ci-roles.json` maps every profile name that layer files and
`backend.tfvars` use to a role ARN in the account that profile
represents. Leverage discovers the names by reading `profile` in every
`.tf` file in the layer, including `provider.tf` and any other name,
and in `backend.tfvars`. A discovered name missing from the map fails
the command. Role ARNs are not secrets. The file is committed.

```json
{
  "<project>-<account>-<purpose>": "arn:aws:iam::<account-id>:role/<role-name>"
}
```

`--ci` writes `~/.aws/<project>/config`. Each profile is a
`credential_process` that reads a JWT from the token command or token
file and assumes the role in the map. The backend profile in
`backend.tfvars` is one of those names, so init uses it directly.

The same profile name is used for remote state and for a provider that
writes in another account. Both hops receive the role in the map, which
for an apply walk is that account's apply role.

### The roles

Each account has one apply role that the map points at. The role can
create and change the resources that account's layers manage, including
IAM roles when a layer creates them, and it can read and write that
account's state bucket and lock table. A repo that wants a narrower
policy lists the actions layer by layer and attaches that policy
instead. The walk itself does not change.

Trust, on each apply role, allows one OIDC issuer and one subject. The
issuer is an IAM OIDC provider in that account. The subject is that
CI's claim for "this repo, default branch," from the table above. The
audience condition is `sts.amazonaws.com` unless that CI uses another
audience and the token program requests it.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::<account-id>:oidc-provider/<issuer-host>"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "<issuer>:aud": "sts.amazonaws.com",
          "<issuer>:sub": "<exact-sub-from-the-apply-job-token>"
        }
      }
    }
  ]
}
```

A review pipeline cannot assume these roles. The pipeline definition
that runs is the one already on the default branch.

## The pipeline

Trigger: a merge to the default branch that changes a `.tf` file, a
`.tfvars` file, `config/ci-roles.json`, or the pipeline itself.

The job runs only when a CI variable `APPLY_ON_MERGE` equals `true`.
The variable is the one the CI exposes to the default branch and hides
from review pipelines. One lock, so a second merge waits instead of
starting another walk. The timeout is long enough for a full serial
walk of the repo. The job can request an OIDC token.

Steps:

1. Check out the commit that was merged.
2. Install the pinned OpenTofu version.
3. Export `LEVERAGE_CI_TOKEN_COMMAND` (or `LEVERAGE_CI_TOKEN_FILE`).
4. Run `leverage tf apply-ordered --ci`.

No hub role is assumed before that command. Leverage performs every
OIDC exchange.

Merging this pipeline changes nothing in AWS until both of the following
are true.

1. A person, with SSO, applies the layers that create the apply roles
   and their trust policies. Those layers are the identity layer in
   each account. Graph order applies them management-account first when
   that account's layer is a prerequisite, and in either order when they
   do not read each other. The trust names the OIDC provider, which
   already exists, so the first apply does not name a role that has not
   been created yet.
2. Someone sets `APPLY_ON_MERGE` to `true`.

To stop a walk that has not started, set `APPLY_ON_MERGE` to any other
value. A walk already running keeps its role sessions until they expire
or someone removes the trust. Cancelling the job stops the process on
the runner.

## Review plans

A review pipeline still plans each changed layer with a read-only role
in that account. Those roles can read state and cannot change
infrastructure. The plan job fails the check when OpenTofu exits
non-zero. That job is separate from the ordered apply. It can later take
`--ci` with the plan-role ARNs in a second map. The apply walk does not
run on a review pipeline.

## Stops to add on the same walk

Two stops, both before `tofu apply` of a saved plan:

- The plan deletes or replaces a resource. The walk stops unless the
  commit message or a workflow input contains an explicit allow. The
  plan output lists the addresses.
- The plan on the default branch does not match the plan the review
  pipeline already showed. The walk stops on that layer. Someone re-runs
  that plan and reviews it before the next merge.

## Boundaries

- Independent layers are not applied in parallel.
- A cycle is not split into a bootstrap order by the CLI.
- `validate` does not gain `--layers` in this design.
- How narrow the apply role is belongs to the repo's identity layer.
  The walker only assumes the role the map names.
- Apply does not run from a review pipeline.
- A profile that writes in another account is the same profile that
  reads that account's state, so the apply walk gives that profile the
  apply role.
