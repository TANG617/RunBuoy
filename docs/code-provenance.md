# Code provenance

## Repository history

`TANG617/RunBuoy` is a GitHub fork of
[`sethwebster/rzr`](https://github.com/sethwebster/rzr). The RunBuoy rewrite
started at upstream commit
`8a8b521dd26381149d3b89d5dd19ddd5b4d18d81`. The original MIT license and Git
history are retained.

## RunBuoy implementation

The Python CLI/Worker, FastAPI Server, protocol schemas, security checks,
native SwiftUI/ActivityKit app, documentation, fixtures, and CI in this
feature branch are newly authored for RunBuoy. No rzr source file is copied
into the new implementation.

The previous rzr terminal server, Cloudflare worker, Expo/React Native app,
SwiftTerm vendoring, remote keyboard, WebSocket/SSE streaming, tunnel,
billing, and public terminal URL implementation are deleted from the branch
because they violate ADR 0001.

## Retained third-party material

- The top-level MIT license text and copyright notice from rzr remain.
- Git history remains intact and identifies every previous upstream file.

If future work copies an implementation from the upstream history or another
project, update this file with repository URL, exact commit, source and
destination file paths, license, and modifications before merging.
