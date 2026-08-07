# Server, CLI, iOS, and protocol compatibility

RunBuoy clients communicate over versioned `/v1` HTTP endpoints defined by
`packages/protocol/openapi.yaml`. Additive fields and endpoints may ship within
the v1 line; clients must ignore response fields they do not understand.

| Release train | Server API | CLI | iOS app | Local manifest/event schema | Status |
| --- | --- | --- | --- | --- | --- |
| Current 0.1 / 1.0 train | `/v1` | `0.1.x` | `1.0.x`, iOS 18+ | manifest v2; event v1 | Release candidate; validate exact versions before marking supported |

This table records compatibility, not public availability. Replace the release
candidate row with exact minimum and maximum tested versions when a release is
cut. Never infer compatibility solely from a successful build.

## Compatibility rules

1. Server changes must accept the currently published CLI and iOS requests
   before the Server is deployed.
2. New response fields are optional during a mixed-version rollout. Existing
   fields keep their meaning for the full supported v1 window.
3. A client must not require a new endpoint until that endpoint is deployed and
   its readiness and ownership tests pass in the Global environment.
4. Authentication scope changes, destructive lifecycle operations, and
   retention changes require cross-version integration tests; they are not
   treated as cosmetic additions.
5. A breaking wire change requires a new API/schema version or a compatibility
   bridge. Do not silently repurpose a v1 field.
6. The read-only boundary is invariant across every version: Server and iPhone
   routes cannot start, cancel, retry, signal, approve, or send input to a
   machine process.

Record the tested Server commit SHA, CLI version, iOS marketing/build version,
OpenAPI digest, and test date in each release’s GitHub Release notes.
