# Coordinated rollout and rollback

Use this sequence when a change crosses Server, protocol, CLI, or iOS. The
existing component-specific commands remain in
[`deployment-and-release.md`](../developer-guide/deployment-and-release.md).

## Server-first rollout

1. Add a backward-compatible Server implementation, migrations, and OpenAPI
   contract. Keep old client behavior working.
2. Run protocol, Server, boundary, migration, retention, and supply-chain jobs.
   Record the OpenAPI digest and generated SBOM artifacts.
3. Merge through a protected pull request. Wait for the successful `main` CI
   workflow to trigger the gated `production` deployment of that exact SHA.
4. Verify `/healthz`, `/readyz`, database/migration readiness, worker progress,
   APNs configuration, and a representative old-client request. Health alone
   is not readiness or push-delivery evidence.
5. Release the CLI from a `cli-vX.Y.Z` tag only after the compatible Server is
   ready. The gated workflow publishes to PyPI, then creates the GitHub Release
   and attaches distributions and the CLI SBOM after publication succeeds.
6. Release iOS from an `ios-vX.Y.Z` tag only after physical-device TestFlight
   validation. The tag workflow creates a prerelease GitHub Release and attaches
   the iOS source/dependency manifest after TestFlight upload succeeds. App
   Review and public App Store release remain manual.
7. Keep the compatibility bridge until adoption evidence supports a separate,
   reviewed cleanup release.

Pull-request workflows have read-only permissions, receive no publishing or
production secrets, and cannot publish. PyPI, TestFlight, release, and
production credentials belong only to protected GitHub environments with
branch/tag restrictions and required reviewers.

Configure the `release` environment with required reviewers and deployment-tag
rules limited to `cli-v*` and `ios-v*`. It needs no stored secret: the release
job receives only a job-scoped `contents: write` GitHub token after the upstream
publish job and environment approval succeed.

## Rollback

- **Server:** stop the rollout or revert through a new pull request. Prefer a
  forward-compatible fix; do not blindly reverse a data migration. Keep the
  old API behavior available while clients are rolled back.
- **CLI:** stop further promotion and yank (do not delete or reuse) the bad PyPI
  version when appropriate. Publish a higher patch version; users may pin the
  last compatible version in the meantime.
- **iOS:** stop TestFlight distribution or App Store phased release. A processed
  build cannot be replaced; submit a higher build/version. Keep the Server
  compatible with both builds during review and propagation.
- **GitHub Release:** mark the affected release as prerelease and document the
  replacement. Do not move or reuse a published tag.

After rollback, verify that active Runs and Live Activities remain observable,
that destructive lifecycle ownership still holds, and that no rollback created
a Server-to-Machine control path.
