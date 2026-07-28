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

## GitHub Actions to TestFlight

The `Publish iOS to TestFlight` workflow archives and signs both the app and
widget extension, exports an IPA, and submits it to TestFlight. It finishes
after Apple accepts the upload; App Store Connect then processes the build
asynchronously. It can be started manually or by pushing a tag such as
`ios-v1.0.0`.

The workflow uses the GitHub environment named `testflight`. Keep all signing
credentials in that environment, not in repository files.

### 1. Confirm Apple identifiers

In Certificates, Identifiers & Profiles, verify that this team owns both
explicit identifiers:

- `dev.runbuoy.app`
- `dev.runbuoy.app.widgets`

The app identifier must have Push Notifications enabled. The Team ID in the
Xcode project and `apps/ios/ExportOptions-TestFlight.plist` is
`PRTA2MGMQH`. If any identifier or the Team ID changes, update the Xcode
project, export options, and `.github/workflows/testflight.yml` together.

Create the `dev.runbuoy.app` app record in App Store Connect before the first
upload.

### 2. Create the distribution certificate and profiles

On a trusted Mac, create or select an Apple Distribution certificate whose
private key is present in Keychain Access. Export the certificate and private
key from **My Certificates** as a password-protected `.p12`.

Create one `App Store Connect` provisioning profile for each bundle ID. Both
profiles must use the same active Apple Distribution certificate. Keep only
the intended active profile for each ID when possible so CI profile selection
is unambiguous.

Encode the `.p12` for GitHub:

```bash
base64 -i /absolute/path/to/RunBuoy-distribution.p12 | pbcopy
```

The command copies the Base64 value; it does not modify the certificate.

### 3. Create an App Store Connect team API key

In App Store Connect, open **Users and Access → Integrations → App Store
Connect API** and create a **team** key with the `App Manager` role. Record its
Issuer ID and Key ID, then download the `.p8` private key. Apple only allows
the private key to be downloaded once.

Use a team key rather than an individual key because individual keys cannot
access provisioning endpoints.

### 4. Configure the GitHub environment

In the repository, open **Settings → Environments → New environment** and
create `testflight`. Restrict deployment branches/tags and add a required
reviewer if appropriate.

Add these environment secrets:

- `APPSTORE_API_KEY_ID`: the App Store Connect Key ID
- `APPSTORE_ISSUER_ID`: the App Store Connect Issuer ID
- `APPSTORE_API_PRIVATE_KEY`: the complete raw contents of the `.p8` file,
  including the BEGIN/END lines
- `APPSTORE_CERTIFICATES_FILE_BASE64`: the value copied by the Base64 command
- `APPSTORE_CERTIFICATES_PASSWORD`: the `.p12` export password

Do not Base64-encode `APPSTORE_API_PRIVATE_KEY`; the Apple actions expect the
raw `.p8` contents.

### 5. Run the first release

Open **Actions → Publish iOS to TestFlight → Run workflow**. Leave the version
blank to use `MARKETING_VERSION` from the Xcode project. Leave the build number
blank to use the workflow run number.

If App Store Connect already contains that build number for the same version,
run the workflow again with an explicitly higher numeric build number.

After the first manual release succeeds, a release can also be started with:

```bash
git tag ios-v1.0.1
git push origin ios-v1.0.1
```

The tag suffix becomes `CFBundleShortVersionString`; the workflow run number
becomes `CFBundleVersion`.

The current iOS app uses Apple's Keychain and HTTPS APIs but no custom
cryptography, so `RunBuoyApp/Info.plist` declares that it does not use
non-exempt encryption. Reassess `ITSAppUsesNonExemptEncryption` before adding
custom encryption.
