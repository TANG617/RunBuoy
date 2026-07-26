# Repository baseline audit

Audit date: 2026-07-26 (Asia/Shanghai)

## Git baseline

- Repository: `TANG617/RunBuoy`
- Default branch: `main`
- Feature branch: `codex/runbuoy-full-mvp`
- Baseline commit: `8a8b521dd26381149d3b89d5dd19ddd5b4d18d81`
- Origin: `https://github.com/TANG617/RunBuoy.git`
- GitHub reports this repository as a fork of `sethwebster/rzr`.
- GitHub compare reported the baseline fork and upstream `main` as identical:
  zero commits ahead and zero behind.

The only pre-existing untracked content was
`.local-packages/expo-ui/android/.gradle/`. It is user-owned, is ignored by
the replacement repository, and was not deleted or committed.

## Previous implementation

The baseline was a Bun workspace containing:

- an Expo/React Native mobile app;
- SwiftTerm and PTY vendoring;
- a terminal WebView and remote keyboard/composer;
- terminal streaming over WebSocket/SSE;
- public Cloudflare/ngrok/localtunnel exposure;
- a Cloudflare worker, Clerk auth, and billing;
- remote terminal attach, control, and signal behavior.

Those capabilities conflict with RunBuoy ADR 0001. They are removed from the
feature branch rather than adapted. The MIT license and Git history remain.

## Baseline tools and tests

| Capability | Audit result |
| --- | --- |
| Python | System 3.9.6; `uv` provisioned CPython 3.12.11 |
| uv | 0.11.31 |
| tmux | 3.7b |
| Docker engine | 29.4.0 |
| Xcode | Not installed; active directory is CommandLineTools only |
| GitHub CLI | 2.96.0, authenticated with repository access |
| Existing CI | One Node job over Node 20/22/24 |
| Existing tests | `npm test` failed before execution because Bun was absent |
| License | MIT, copyright Seth Webster |

The lack of Bun did not block the rewrite because the shipped product no
longer uses the old JavaScript runtime. Xcode-specific validation must run in
GitHub Actions on macOS until full Xcode is installed locally.

## Parallel ownership

| Workstream | Owned paths |
| --- | --- |
| CLI/Worker agent | `cli`, `packages/sdk-python`, `skills/runbuoy`, `examples` |
| Server/APNs agent | `server`, `infra` |
| Native iOS agent | `apps/ios` |
| Lead/integration | protocol, root files, scripts, CI, security, documentation |

Each implementation workstream started from shared contract commit
`94fd8d679ab6b585c110cfec32a76066143c0762` in a separate Git worktree.
