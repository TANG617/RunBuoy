# App privacy data map

Use this map when completing App Store Connect App Privacy. It describes the
intended Global-service behavior; the release owner must compare it with the
exact app, server, SDKs, and privacy-policy revision being submitted.

RunBuoy does not use data for third-party advertising, developer advertising,
or tracking, and does not combine it with third-party data for advertising or
measurement. There are no third-party advertising or analytics SDKs in the iOS
source dependency manifest.

| Apple category / example | Collected by the Global service | Linked to the app workspace or device | Purpose | Notes |
| --- | --- | --- | --- | --- |
| Identifiers — workspace, machine, and device IDs | Yes | Yes | App functionality, security | Random service identifiers; no advertising identifier. |
| User Content — safe title, safe message, notification content | Yes | Yes | App functionality | Chosen by the machine/user; full commands and full logs stay local by default. |
| User Content — optional safe log snippet | Opt-in only | Yes | App functionality | `--share-log-tail 1..100`; sanitized, clearly labelled, maximum 24-hour retention. |
| Usage Data — Run state, phase, progress, timestamps, exit status | Yes | Yes | App functionality | Represents the observed task, not remote-control input. |
| Device Information — app/OS version, platform, architecture | Yes | Yes | Compatibility, app functionality, security | Does not include IDFA. |
| Product Interaction — notification and Live Activity preferences | Yes | Yes | App functionality | Used to decide what the selected device receives. |
| Diagnostics / delivery metadata — push attempts and audit events | Yes | Yes | App functionality, security | Retained according to the published Global retention table. |
| Push identifiers — APNs, push-to-start, and activity tokens | Yes | Yes | App functionality | Encrypted at rest and removed on device reset/revocation. |
| Camera image | No | No | On-device functionality only | Camera frames are decoded locally for a one-time pairing code and are not retained or uploaded. |
| Precise/coarse location, contacts, photos, health, financial, purchases | No | No | Not applicable | Region selection is a service endpoint choice, not device location collection. |
| Full command, arguments, cwd, environment, source, stdout/stderr, full logs | No by default | No | Not applicable | Remain on the machine; the optional bounded snippet is disclosed separately above. |

“Linked” here is deliberately conservative: records are associated with a
RunBuoy workspace/device even though RunBuoy does not require a conventional
profile name. App Store Connect’s current questions and definitions are the
authority, so the release owner must make the final selection manually.

## Permission-to-data flow

- **Camera:** requested when the user opens QR scanning; frames stay on-device.
- **Notifications:** requested during onboarding; denial does not grant any
  extra access and can be changed in Settings.
- **Live Activities:** ActivityKit tokens are registered only for delivery of
  Run state. They cannot control the machine.
- **Local storage:** the device credential is stored in Keychain. Cached Runs
  and settings remain on-device and can be cleared/reset in the app.

## Deletion and retention check

Before submission, compare the running Global configuration with
`https://www.runbuoy.cloud/privacy`. Exercise device reset and workspace
deletion in staging, including cleanup of subscriptions, token bindings,
pending delivery state, and optional snippets. Confirm active Runs and active
Live Activities are not age-deleted while active.

Self-hosted servers are controlled by their operators. The public privacy page
must continue to distinguish their policies from the Global defaults.
