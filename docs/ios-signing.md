# iOS signing

The checked-in Xcode project targets iOS 18 and builds without signing in CI:

```bash
xcodebuild \
  -project apps/ios/RunBuoy.xcodeproj \
  -scheme RunBuoy \
  -destination 'generic/platform=iOS Simulator' \
  CODE_SIGNING_ALLOWED=NO \
  build
```

## Identifiers and capabilities

- App sample bundle ID: `dev.runbuoy.app`
- Widget sample bundle ID: `dev.runbuoy.app.widgets`
- URL scheme: `runbuoy`
- App capabilities: Push Notifications and Live Activities
- Widget capabilities: Live Activity widget extension
- `NSSupportsLiveActivities` is enabled.

Change sample IDs consistently in build settings, entitlements, the APNs
topic, and Server configuration. Select your Team in both targets. Use an App
Group only if the project entitlements actually declare and consume one; do
not add a capability speculatively.

Debug builds normally use APNs sandbox. TestFlight and App Store builds use
production APNs. Keep `.p8`, provisioning profiles, Team IDs, and real bundle
configuration out of source control and inject Server secrets at deployment.

Before TestFlight, verify notification denial, token rotation, offline cache,
deep links, Dynamic Type, VoiceOver, Reduce Motion, English/Chinese strings,
and each Live Activity presentation on a supported physical device.
