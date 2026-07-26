# RunBuoy for iOS

RunBuoy is a native iOS 18+ read-only presentation client. Execution data flows
from a paired machine through the RunBuoy server to the iPhone. The app contains
no command, process, terminal, approval, or agent-response surface.

## Project

- `RunBuoyApp`: SwiftUI app, read API, Keychain identity, lightweight cache,
  onboarding, QR pairing, notification registration, and ActivityKit token
  lifecycle.
- `RunBuoyWidgets`: WidgetKit Live Activity UI for the Lock Screen and Dynamic
  Island. A tap opens `runbuoy://runs/<run-id>`; there are no action controls.
- `RunBuoyTests`: protocol decoding, read-client, cache, routing, pairing, and
  token-registration contract tests.

The shared `RunBuoy` scheme builds the app and widget and runs `RunBuoyTests`.

## Build and test

Xcode 16 or newer with the iOS 18 SDK is required:

```sh
xcodebuild \
  -project apps/ios/RunBuoy.xcodeproj \
  -scheme RunBuoy \
  -destination 'generic/platform=iOS Simulator' \
  CODE_SIGNING_ALLOWED=NO \
  build
```

With an iOS 18 simulator available:

```sh
xcodebuild \
  -project apps/ios/RunBuoy.xcodeproj \
  -scheme RunBuoy \
  -destination 'platform=iOS Simulator,name=iPhone 16' \
  CODE_SIGNING_ALLOWED=NO \
  test
```

`RUNBUOY_API_BASE_URL` in `RunBuoyApp/Info.plist` selects the HTTPS API.

## Signing and Apple capabilities

Replace the sample bundle IDs and app-group identifier with identifiers owned
by the development team. Enable Push Notifications, the app group, and Live
Activities for the App ID. Debug uses the development APNs environment;
Release uses production. Provisioning profiles must contain the matching
entitlements.

The implementation follows Apple’s current documentation for
[ActivityKit](https://developer.apple.com/documentation/activitykit/),
[Activity token updates](https://developer.apple.com/documentation/activitykit/activity),
[Live Activity deep links](https://developer.apple.com/documentation/widgetkit/linking-to-specific-app-scenes-from-your-widget-or-live-activity),
and [APNs registration](https://developer.apple.com/documentation/usernotifications/registering-your-app-with-apns).

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
