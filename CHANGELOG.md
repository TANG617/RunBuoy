# Changelog

All notable user-visible changes are documented here. The project follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and intends to use
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) for published
components.

## [Unreleased]

### Added

- Bilingual Support, Service Status, Privacy, and Security pages with explicit
  Global and self-hosting boundaries.
- App Store submission, privacy-data-map, reviewer-note, compatibility, and
  coordinated release controls.
- Dependency update automation, CodeQL analysis, immutable Action pin checks,
  and release SBOM/source-manifest artifacts.
- An in-app Support link to the public website.

### Changed

- Public website compatibility copy now targets iOS 18 or later.
- Tag publishing creates a GitHub Release only after the associated protected
  publish workflow succeeds.

### Security

- Third-party GitHub Actions are pinned to immutable commit SHAs and release
  workflows use job-scoped permissions and protected environments.

[Unreleased]: https://github.com/TANG617/RunBuoy/compare/cli-v0.1.3...HEAD
