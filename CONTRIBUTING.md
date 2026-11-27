# Contributing

When contributing to this repository, please first discuss the change you wish to make via issue
with the owners of this repository before making a change.

Please note we have a code of conduct, please follow it in all your interactions with the project.

## Pull Request Process

1. Start the PR title with a prefix: `Fix |`, `Feature |`, `Enhancement |`, `Docs |` or `Chore |`. It sets the PR's
   labels and the version bump of the next release; see "Release Process" in the README. Don't change version numbers
   by hand: the release draft computes the next one.
2. Add or update tests for the change, at the cheapest level that catches its bug. [docs/testing.md](docs/testing.md)
   explains each suite and where a new test goes.
3. The required checks have to pass: `lint` (black, ruff), `unit_tests` on every supported Python version (with mypy
   and the coverage floor) and `integration_tests` (bats).
4. A change that touches credentials, tokens, logging or the processes the CLI runs goes through the checklist in
   [docs/threat-model.md](docs/threat-model.md).
5. Update the README when the change affects how the CLI is installed, configured or developed, and the
   [user documentation](https://github.com/binbashar/le-ref-architecture-doc) when it changes a command's behavior.
6. The PR can be merged once a maintainer approves it.


### Collaborate on fixes for security vulnerabilities in private forks

Working in the open means that it is impossible to hide things. And yet, sometimes you will want
to work on some changes in the code in private, for example when fixing a security vulnerability.

Working on a fix in the open might allow attackers to reverse engineer the bug and attack our users.
Since GitHub provides a mechanism to easily create a private fork of our repo, please use this
private forks to collaborate on a security fix.

### Publish maintainer advisories for security fixes

Fixing a security vulnerability is no small feat and we should tell our users about it.
We will do it in a way that will make it easy for you to learn about it and patch

Since GitHub provides an easy way to publish a security advisory, this will
be incorporated and you could add it into your security scanning tools, the ones you
depend on to keep your applications secure.

## Read More

[Leverage Open Source Modules management](https://leverage.binbash.com.ar/how-it-works/infra-as-code-library/infra-as-code-library-forks/)
