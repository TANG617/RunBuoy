# RunBuoy deployment and release guide

This guide describes how repository changes reach the production Server,
TestFlight, and PyPI. The three delivery paths use different GitHub Actions
triggers:

| Git operation | Server | iOS | CLI / PyPI |
| --- | --- | --- | --- |
| `git pull` | No deployment | No release | No release |
| Push a feature branch | Run CI only | Run CI only | Run CI only |
| Merge or push to `main` | Deploy after CI succeeds | No release | No release |
| Push an `ios-vX.Y.Z` tag | No deployment | Upload to TestFlight | No release |
| Push a `cli-vX.Y.Z` tag | No deployment | No release | Publish to PyPI after approval |
| Manually run the TestFlight workflow | No deployment | Upload the selected ref to TestFlight | No release |

`git pull` only synchronizes a local checkout. Do not SSH to the production
Server and run `git pull` as part of a normal release; the Server workflow
deploys the exact commit SHA that passed CI.

## Release safety rules

1. Develop on a feature branch and merge through a pull request.
2. Do not publish from a dirty working tree.
3. Do not create release tags until the intended code is on `origin/main` and
   the CI run for that commit is green.
4. Point release tags explicitly at `origin/main`, rather than relying on the
   currently checked-out branch.
5. Push only the intended tag. Do not use `git push --tags`.
6. Deploy backward-compatible Server and protocol changes before releasing
   clients that depend on them.

The tag workflows do not independently wait for the `main` CI workflow.
Following the third and fourth rules is therefore the human release gate.

## Normal development flow

Commit only the intended files on the current feature branch:

```bash
git status
git add <paths>
git diff --cached
git commit -m "Describe the change"
git push -u origin HEAD
```

Open a pull request targeting `main`, wait for every required CI job to pass,
and merge it. A feature-branch push or a pull-request CI run never deploys the
production Server.

After the merge, update a clean local `main` when needed:

```bash
git fetch origin --prune --tags
git switch main
git pull --ff-only origin main
```

If the current working tree contains uncommitted work, commit it on its feature
branch before switching branches. Alternatively, use a separate clean worktree
for release operations.

## Server production deployment

Workflow: [`.github/workflows/deploy-server.yml`](../.github/workflows/deploy-server.yml)

The Server deploy is automatic:

```text
push to main
  -> CI
  -> all CI jobs succeed
  -> Deploy server
  -> SSH to production + production-cn in parallel
  -> deploy <tested-commit-sha> on each region
```

The deploy workflow accepts only a successful `push` CI run on `main`. A
successful pull-request run is not sufficient. Global and Mainland China use
separate concurrency groups, deployments, databases, credentials, and public
region health checks. A failure in one region does not cancel the other job.

### Required GitHub environment

Create GitHub environments named `production` and `production-cn`, restrict
both to the `main` branch, and configure the following values independently in
each environment:

Environment variables:

- `PROD_HOST`
- `PROD_PORT`
- `PROD_USER`

Environment secrets:

- `PROD_SSH_KEY`
- `PROD_KNOWN_HOSTS`

The target host must install `infra/runbuoy-ci-command` and
`infra/deploy-runbuoy` under `/usr/local/sbin`, and restrict the CI public key
to the former with an `authorized_keys` forced command. It accepts one commit
SHA, verifies that it belongs to `origin/main`, checks out exactly that
revision, applies migrations, starts or updates the API and worker, and exits
unsuccessfully if health checks fail.

### Deploy

The recommended Server release action is simply to merge the green pull
request into `main`. No Server tag is required.

Monitor the runs in GitHub Actions or with GitHub CLI:

```bash
gh run list --workflow ci.yml --limit 3
gh run list --workflow deploy-server.yml --limit 3
```

Verify production after the deployment:

```bash
curl --fail --silent --show-error https://api.runbuoy.cloud/healthz
curl --fail --silent --show-error https://api-cn.runbuoy.cloud/healthz
```

Expected response:

```json
{"status":"ok","region":"global"}
{"status":"ok","region":"cn"}
```

The two installations are intentionally isolated. Do not copy PostgreSQL data,
device credentials, or pairing sessions between them. The same Apple APNs
signing `.p8` key may be mounted on both Workers, while each deployment keeps
independent database, credential-pepper, and token-encryption secrets.

### Backups

Install `infra/backup-runbuoy` as `/usr/local/sbin/backup-runbuoy` and the two
`runbuoy-backup.*` units in `/etc/systemd/system`. The daily timer writes a
custom-format PostgreSQL dump, a root-only archive of `/etc/runbuoy`, and
SHA-256 checksums under `/var/backups/runbuoy`. Backups default to 14-day local
retention. Periodically copy encrypted backups off-host and perform a private
restore test; a local backup alone does not protect against loss of the server.

Also verify a representative API operation and check the production API,
worker, migration, and APNs delivery logs when the release changes those
paths.

### Roll back

Prefer a forward fix or a Git revert committed through a pull request:

```bash
git switch -c revert/<short-description> origin/main
git revert <bad-commit-sha>
git push -u origin HEAD
```

Merge the revert after CI succeeds. The resulting `main` push automatically
deploys the revert commit. Database migrations require special care: do not
blindly downgrade a production database if the migration has already modified
data. Restore compatibility with a forward migration when possible.

## iOS release to TestFlight

Workflow: [`.github/workflows/testflight.yml`](../.github/workflows/testflight.yml)

The workflow signs the app and widget, archives and exports an IPA, uploads it
to App Store Connect, and waits for TestFlight processing. It does **not**
submit the build for App Review or automatically publish it on the App Store.

### Required GitHub environment

Create a GitHub environment named `testflight` and configure:

- `APPSTORE_API_KEY_ID`
- `APPSTORE_ISSUER_ID`
- `APPSTORE_API_PRIVATE_KEY`
- `APPSTORE_CERTIFICATES_FILE_BASE64`
- `APPSTORE_CERTIFICATES_PASSWORD`

The raw `.p8` contents, including their begin and end lines, belong in
`APPSTORE_API_PRIVATE_KEY`. Do not Base64-encode that value. The distribution
certificate and private key must be exported as a password-protected `.p12`;
its Base64 representation belongs in
`APPSTORE_CERTIFICATES_FILE_BASE64`.

The Apple team, app bundle ID, widget bundle ID, App Store Connect record,
capabilities, distribution certificate, and provisioning profiles must match
the values in the workflow and Xcode project. See
[`docs/ios-signing.md`](ios-signing.md) for the complete setup.

Restrict this environment to `main` and `ios-v*` tags. A required reviewer is
recommended.

### Manual TestFlight build

Manual dispatch is useful for an initial release or an internal candidate:

```bash
gh workflow run testflight.yml \
  --ref main \
  -f marketing_version=1.0.1
```

Omit `marketing_version` to use the Xcode project value. Omit `build_number`
to use the workflow run number. If App Store Connect already contains the
same build number for that marketing version, supply a higher numeric value:

```bash
RUNBUOY_BUILD_NUMBER=1000  # Replace with a value higher than the existing build.
gh workflow run testflight.yml \
  --ref main \
  -f marketing_version=1.0.1 \
  -f build_number="$RUNBUOY_BUILD_NUMBER"
```

The same action is available under **Actions -> Publish iOS to TestFlight ->
Run workflow**.

### Tagged TestFlight release

Fetch current remote state and inspect the exact commit to release:

```bash
git fetch origin --prune --tags
git log -1 --oneline origin/main
```

After confirming that this commit's CI run is green, create an annotated tag
that points explicitly to it:

```bash
git tag -a ios-v1.0.1 origin/main -m "RunBuoy iOS 1.0.1"
git push origin refs/tags/ios-v1.0.1
```

The `ios-v` suffix becomes `CFBundleShortVersionString`. The workflow run
number becomes `CFBundleVersion` unless a manual build number was supplied.

After upload:

1. Wait for App Store Connect processing to complete.
2. Test installation, pairing, notifications, and Live Activities on a
   physical iPhone.
3. Assign the build to the intended TestFlight groups.
4. For a public App Store release, complete the listing and privacy metadata,
   select the build, and submit it for App Review.

A TestFlight or App Store build cannot be replaced in place. Release a new,
higher build number for a fix.

## CLI release to PyPI

Workflow: [`.github/workflows/publish-cli.yml`](../.github/workflows/publish-cli.yml)

The CLI version has a single source of truth:
`cli/src/runbuoy/__init__.py`. A tag such as `cli-v0.1.2` must exactly match:

```python
__version__ = "0.1.2"
```

PyPI files are immutable. Never reuse a version that PyPI has already
accepted.

### Required publishing configuration

The workflow uses PyPI Trusted Publishing, not a long-lived API token. The
publisher identity must match:

```text
PyPI project: runbuoy
GitHub owner: TANG617
GitHub repository: RunBuoy
Workflow filename: publish-cli.yml
GitHub environment: pypi
```

The GitHub environment named `pypi` should require deployment approval. Do not
add a PyPI password or `PYPI_API_TOKEN` to the repository.

### Prepare and validate a release

1. Update `__version__` using semantic versioning.
2. Update the changelog or user-facing release notes.
3. Validate the package locally.
4. Merge the release changes to `main` and wait for green CI.

Local validation:

```bash
cd cli
uv sync --all-groups --frozen
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
uv build --clear --no-sources
uvx --from twine twine check dist/*
cd ..
```

### Publish

Fetch the remote state and verify the version contained in `origin/main`:

```bash
git fetch origin --prune --tags
git show origin/main:cli/src/runbuoy/__init__.py | grep __version__
git log -1 --oneline origin/main
```

For version `0.1.2`, publish the exact `origin/main` commit with:

```bash
git tag -a cli-v0.1.2 origin/main -m "RunBuoy CLI 0.1.2"
git push origin refs/tags/cli-v0.1.2
```

The workflow verifies the tag/version match, runs tests, builds and validates
the wheel and source distribution, installs the wheel for a smoke test, and
then waits for approval of the `pypi` environment. Review the build job before
approving publication.

Monitor the workflow:

```bash
gh run list --workflow publish-cli.yml --limit 3
```

Verify public metadata:

```bash
curl --fail --silent --show-error \
  https://pypi.org/pypi/runbuoy/json |
  jq '.info | {name, version, requires_python, project_url}'
```

Verify installation from the public index:

```bash
uv tool upgrade runbuoy
runbuoy doctor --json
```

See [`docs/cli-distribution.md`](cli-distribution.md) for packaging details,
isolated installation checks, Trusted Publishing setup, and yanking a bad
release.

## Coordinated Server, CLI, and iOS release

When one change spans the protocol, Server, CLI, and iOS, use this order:

1. Commit the complete change on a feature branch and push it.
2. Fix every CI failure.
3. Merge the pull request to `main`.
4. Wait for the automatic Server deployment and verify production.
5. Tag the tested `origin/main` commit with `cli-vX.Y.Z`.
6. Approve the PyPI deployment and verify installation.
7. Tag the tested `origin/main` commit with `ios-vX.Y.Z`.
8. Verify the TestFlight build on a physical device.
9. Submit the iOS build for App Review when it is ready for public release.

For a breaking protocol change, use a two-phase rollout: first deploy a Server
that accepts both old and new clients, then release the clients, and only
remove old compatibility in a later Server release.

## Common mistakes

- Running `git pull` locally and expecting a deployment.
- Pushing a feature branch and expecting production Server changes.
- Tagging the currently checked-out feature branch instead of `origin/main`.
- Tagging uncommitted work; Git tags contain commits only.
- Publishing while the `main` CI run is still failing.
- Using `git push --tags` and triggering unintended releases.
- Reusing a PyPI version or an App Store build number.
- Assuming a TestFlight upload is a public App Store release.
- Manually running `git pull` on the production host and bypassing the tested
  commit SHA.
