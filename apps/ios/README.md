# RunBuoy for iOS

RunBuoy is a native iOS 26+ read-only presentation client. Execution data flows
from a paired machine through the RunBuoy server to the iPhone. The app contains
no command, process, terminal, approval, or agent-response surface.

## Project

- `RunBuoyApp`: SwiftUI app, read API, Keychain identity, lightweight cache,
  onboarding, QR pairing, notification registration, and ActivityKit token
  lifecycle. Successful foreground reads reconcile newer Run sequences into
  existing Live Activities locally and end terminal Runs without waiting for a
  second APNs delivery.
- `RunBuoyWidgets`: WidgetKit Live Activity UI for the Lock Screen and Dynamic
  Island. Its elapsed value advances only with Machine-confirmed events and
  becomes stale after 60 seconds without an update. A tap opens
  `runbuoy://runs/<run-id>`; there are no action controls.
- `RunBuoyTests`: protocol decoding, read-client, cache, routing, pairing, and
  token-registration contract tests.

The shared `RunBuoy` scheme builds the app and widget and runs `RunBuoyTests`.

## Build and test

Xcode 26 or newer with the iOS 26 SDK is required:

```sh
xcodebuild \
  -project apps/ios/RunBuoy.xcodeproj \
  -scheme RunBuoy \
  -destination 'generic/platform=iOS Simulator' \
  CODE_SIGNING_ALLOWED=NO \
  build
```

With an iOS 26 simulator available:

```sh
xcodebuild \
  -project apps/ios/RunBuoy.xcodeproj \
  -scheme RunBuoy \
  -destination 'platform=iOS Simulator,name=iPhone 16' \
  CODE_SIGNING_ALLOWED=NO \
  test
```

The shared `RunBuoy.xctestplan` runs both `RunBuoyTests` and
`RunBuoyUITests`. Run either layer independently with:

```sh
xcodebuild \
  -project apps/ios/RunBuoy.xcodeproj \
  -scheme RunBuoy \
  -destination 'platform=iOS Simulator,name=iPhone 17,OS=latest' \
  -only-testing:RunBuoyUITests \
  -resultBundlePath /tmp/RunBuoyUITests.xcresult \
  CODE_SIGNING_ALLOWED=NO \
  test
```

UI tests launch the Debug app with deterministic Preview fixtures. Supported
scenarios are `loaded`, `empty`, `offline`, and `failed`; the test-only launch
arguments are parsed by `UITestConfiguration.swift`. Every UI test attaches a
final screenshot that Xcode retains when the test fails.

The `RUNBUOY_API_BASE_URL` build setting selects the HTTPS API and is expanded
into `RunBuoyApp/Info.plist`. Override the setting per build environment when
the checked-in deployment is not the desired server.

## Signing and Apple capabilities

Replace the sample bundle IDs with identifiers owned by the development team.
Enable Push Notifications and Live Activities for the App ID. The app opts
into frequent Live Activity updates for the 15-second heartbeat cadence.
Debug uses the development APNs environment; Release uses production.
Provisioning profiles must contain the matching entitlements. No App Group is
required by the MVP.

The implementation follows Apple’s current documentation for
[ActivityKit](https://developer.apple.com/documentation/activitykit/),
[Activity token updates](https://developer.apple.com/documentation/activitykit/activity),
[Live Activity deep links](https://developer.apple.com/documentation/widgetkit/linking-to-specific-app-scenes-from-your-widget-or-live-activity),
and [APNs registration](https://developer.apple.com/documentation/usernotifications/registering-your-app-with-apns).
ActivityKit token and activity-sync registrations retry with exponential
backoff and are re-sent when the app returns to the foreground. The current
`frequentPushesEnabled` setting is included in reconciliation so the server can
reduce ordinary progress cadence when the user disables frequent updates.

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
server APNs configuration, code signing, and a physical iPhone.
