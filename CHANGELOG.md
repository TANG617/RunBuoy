# Changelog

All notable user-visible changes are documented here. The project follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and intends to use
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) for published
components.

## [Unreleased]

## [CLI 0.1.4 / iOS 1.0.4] - 2026-08-07

### Added

- iOS 18 compatibility across the app, widget, unit-test, and UI-test targets,
  with availability-gated iOS 26 visual enhancements and iOS 18 fallbacks.
- Device reset, Machine revoke/revoke-self, Workspace deletion challenge,
  CLI unpair, and batched retention lifecycle controls.
- Database-backed request limits and resource quotas with PostgreSQL
  concurrency coverage and trusted-proxy handling.
- Revisioned sync, ETag/304 support, stable history pagination, adaptive iOS
  refresh, offline cache repair, and old-Server fallback.
- Readiness checks, worker heartbeats, bounded Prometheus metrics, structured
  redacted logging, verified backup/restore, and load-smoke tooling.
- Bilingual Support, Service Status, Privacy, and Security pages with explicit
  Global and self-hosting boundaries.
- App Store submission, privacy-data-map, reviewer-note, compatibility, and
  coordinated release controls.
- Dependency update automation, CodeQL analysis, immutable Action pin checks,
  and release SBOM/source-manifest artifacts.
- An in-app Support link to the public website.

### Changed

- App and Widget privacy manifests now ship in their respective bundle roots;
  the App declares only its actual UserDefaults required-reason API use.
- Anonymous bootstrap is create-only, pairing and event ingestion are
  transactionally serialized, and retained Server deletions converge on iOS.
- Public website compatibility copy now targets iOS 18 or later.
- Tag publishing creates a GitHub Release only after the associated protected
  publish workflow succeeds.

### Security

- Request bodies are bounded before parsing, credentials and destructive
  operations are owner-scoped, and production rejects placeholder peppers.
- Production ingress trusts only the pinned Caddy address, keeps metrics off
  the public route, and restores PostgreSQL through a validated staging cutover.
- Third-party GitHub Actions are pinned to immutable commit SHAs and release
  workflows use job-scoped permissions and protected environments.

[Unreleased]: https://github.com/TANG617/RunBuoy/compare/ios-v1.0.4...HEAD
[CLI 0.1.4 / iOS 1.0.4]: https://github.com/TANG617/RunBuoy/compare/cli-v0.1.3...cli-v0.1.4
