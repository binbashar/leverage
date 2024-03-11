## What?
* Describe high-level what changed as a result of these commits (i.e. in plain-english, what do these changes mean?)
* Use bullet points to be concise and to the point.

## Why?
* Provide the justifications for the changes (e.g. business case). 
* Describe why these changes were made (e.g. why do these commits fix the problem?)
* Use bullet points to be concise and to the point.

## How to test this PR manually?

- *(Add the steps describing how to test your changes manually)*
- Add any new `.env` variables needed for testing:
  ```ini
  FOO_URL=http://foo.com
  ```
- Example **curl** command for testing:
    ```bash
    curl -X POST 'http://localhost:8000/api/v1/foo/' \
    --header 'Authorization: Token xxx' \
    --header 'Content-Type: application/json' \
    --data-raw '{
      "foo": "bar"
    }'
    ```
- Expected result:
    ```json
    {"success":  "ok"}
    ```

## Pre-review checklist

- [ ] Unit / integration tests are updated.
- [ ] Test manually.
- [ ] Verify that PR has clear testing instructions
- [ ] Verify that documentation is updated.
- [ ] Verify that feature branch is up-to-date with `master` (if not - rebase it).


## References
* Link to any supporting github issues or helpful documentation to add some context (e.g. stackoverflow). 
* Use `closes #123`, if this PR closes a GitHub issue `#123`

## Pre-merge checklist

- [ ] Verify that external dependencies for this commit are fulfilled (eg: new env setup is complete)
- [ ] Squash related commits together.
- [ ] Double-check the quality of [commit messages](http://chris.beams.io/posts/git-commit/).
- [ ] This PR can be deployed to production without breaking anything

## Before release

Review the checklist [here](https://binbash.atlassian.net/l/cp/BthxSQ0j)
