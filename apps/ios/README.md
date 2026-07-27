# RunBuoy for iOS

RunBuoy is a native read-only presentation client. Execution data flows from a
paired Machine through the RunBuoy Server to the iPhone. The app contains no
command, process, terminal, approval, or agent-response surface.

## Compatibility requirement

The accepted functional baseline is **iOS 18**. iOS 18 must support pairing,
read projections, local cache, notifications, Live Activities, Lock Screen, and
Dynamic Island where hardware supports it.

iOS 26 presentation APIs, including Liquid Glass, are optional enhancements and
must be guarded with `#available(iOS 26, *)` and complete iOS 18 fallbacks.

The current visual revision still sets the project deployment target to iOS 26
and uses iOS 26-only presentation APIs. This is a known implementation gap
against the accepted PRD and ADR 0002. Do not interpret it as a product decision
to drop iOS 18.

## Project

- `RunBuoyApp`: SwiftUI app, Read API, Keychain identity, lightweight cache,
  onboarding, QR pairing, notification registration, and ActivityKit token
  lifecycle.
- `RunBuoyWidgets`: WidgetKit Live Activity UI for the Lock Screen and Dynamic
  Island. A tap opens `runbuoy://runs/<run-id>`; there are no action controls.
- `RunBuoyTests`: protocol decoding, read-client, cache, routing, pairing, and
  token-registration contract tests.

The shared `RunBuoy` scheme builds the app and widget and runs `RunBuoyTests`.

## Current build and test

The current implementation requires Xcode 26 and an iOS 26 SDK until the
compatibility migration is completed:

```sh
xcodebuild \
  -project apps/ios/RunBuoy.xcodeproj \
  -scheme RunBuoy \
  -destination 'generic/platform=iOS Simulator' \
  CODE_SIGNING_ALLOWED=NO \
  build
```

With an iOS 26 simulator currently available:

```sh
xcodebuild \
  -project apps/ios/RunBuoy.xcodeproj \
  -scheme RunBuoy \
  -destination 'platform=iOS Simulator,name=iPhone 16' \
  CODE_SIGNING_ALLOWED=NO \
  test
```

The compatibility follow-up must:

1. restore `IPHONEOS_DEPLOYMENT_TARGET = 18.0`;
2. availability-gate Liquid Glass and all iOS 26-only APIs;
3. provide standard SwiftUI/material fallbacks;
4. build and test an iOS 18-compatible target in CI;
5. preserve the same functional behavior on iOS 18 and iOS 26.

`RUNBUOY_API_BASE_URL` in `RunBuoyApp/Info.plist` selects the HTTPS API.

## Network-tolerance UI behavior

The iOS client presents the newest known Run snapshot. It does not require every
intermediate progress or heartbeat event.

- Late older revisions are ignored and cannot move progress backward.
- Cached state remains visible when the Read API is unavailable.
- Network silence uses neutral freshness language such as `Updates may be
  delayed` or `Status currently unavailable`.
- Missing heartbeats do not imply execution failure or `LOST`.
- The default Live Activity stale horizon is 10 minutes and retains the last
  known progress.
- An explicit terminal snapshot is required to present success, failure,
  cancellation, or loss.

## Signing and Apple capabilities

Replace the sample bundle IDs with identifiers owned by the development team.
Enable Push Notifications and Live Activities for the App ID. Debug uses the
development APNs environment; Release uses production. Provisioning profiles
must contain the matching entitlements. No App Group is required by the MVP.

The implementation follows Apple ActivityKit, Activity token lifecycle, Live
Activity deep-link, and APNs registration requirements documented in
[`docs/apns-setup.md`](../../docs/apns-setup.md).

## Physical-device verification

The following cannot be validated with a generic simulator build alone:

- camera-based QR capture;
- APNs device-token issuance and delivery;
- push-to-start token issuance, rotation, and remote Live Activity start;
- per-activity update-token rotation and APNs update/end delivery;
- Lock Screen and Dynamic Island presentation on supported hardware;
- production signing and entitlement acceptance.

These paths have injectable/network mocks, JSON fixtures, previews, and unit
coverage, but final verification requires Apple Developer credentials, matching
Server APNs configuration, code signing, and a physical iPhone.
