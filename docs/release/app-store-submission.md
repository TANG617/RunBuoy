# App Store submission checklist

This is the release-owner checklist for the RunBuoy iPhone app. It does not
authorize a release and does not claim that App Store Connect configuration is
complete.

## Binary and platform

- [ ] **Manual — blocking:** confirm `IPHONEOS_DEPLOYMENT_TARGET = 18.0` for the
  app, widget, test, and UI-test targets in the exact release commit. Run the
  unsigned iOS 18 simulator lane and the latest-iOS lane. Do not submit a build
  whose binary still requires iOS 26.
- [ ] Confirm the archive contains `dev.runbuoy.app` and its Live Activity
  widget extension, and that version/build values match App Store Connect.
- [ ] Confirm `RUNBUOY_API_BASE_URL` points at the intended HTTPS service and
  the Global service is ready before releasing the client.
- [ ] On a physical iPhone running iOS 18, exercise first launch, Dynamic Type,
  VoiceOver, Reduce Motion, dark mode, offline cache, and English and Simplified
  Chinese localization.

## Product behavior and permissions

- [ ] Pair with `runbuoy device pair`, start a safe demo Run, and verify that
  state, progress, terminal status, and safe messages reach the phone.
- [ ] Verify the phone remains read-only: there is no start, cancel, retry,
  shell, approval, terminal-input, or Server-to-Machine control route.
- [ ] Deny notifications and verify the app remains usable; then grant them and
  verify an APNs notification opens the expected Run.
- [ ] Verify Live Activity start, update, terminal end, stale/lost behavior, and
  the disabled-system-setting state on a physical device.
- [ ] Deny Camera permission and verify the error and recovery path. Grant it
  and verify that the camera is used only to decode a one-time pairing QR code;
  no image is retained or uploaded.
- [ ] Verify stop-receiving, device reset, machine unpair, and workspace
  deletion. Confirm destructive actions cannot affect a process on the machine.
- [ ] Verify the in-app Website, Privacy, Support, and self-hosting links.

## Listing and policy metadata

- [ ] **Manual — App Store Connect:** set minimum OS to iOS 18.0 and ensure the
  compatibility text, subtitle, description, age rating, and review notes do
  not claim iOS 26-only behavior.
- [ ] **Manual — App Store Connect:** set Privacy Policy URL to
  `https://www.runbuoy.cloud/privacy` and Support URL to
  `https://www.runbuoy.cloud/support`; open both public URLs from a logged-out
  browser before submission.
- [ ] **Manual — App Store Connect:** answer App Privacy from
  [the data map](app-privacy-data-map.md) against the release binary and Global
  server configuration. The document is a review aid, not an automatic answer.
- [ ] **Manual — App Review Information:** enter a verified contact name, phone,
  and email in App Store Connect. No verified public support email is stored in
  this repository; do not invent one for the listing or review form.
- [ ] Paste and complete the [reviewer notes](reviewer-notes.md), replacing every
  placeholder and testing the steps from a clean device.

## Encryption declaration

- [ ] Confirm the release binary still uses Apple platform cryptography and
  HTTPS only, with no custom or non-exempt cryptographic implementation.
- [ ] Confirm `ITSAppUsesNonExemptEncryption` remains `false` only if the prior
  statement is true. Reassess after any networking, cryptography, VPN, or secure
  storage dependency change.
- [ ] **Manual — App Store Connect:** answer export-compliance questions for the
  submitted binary. Retain the answer/evidence with the release record; a plist
  value does not replace the legal review.

## Screenshots and review evidence

- [ ] **Manual:** capture current App Store-required iPhone sizes from the exact
  release build, with status bars and sample data free of identifiers, tokens,
  hostnames, paths, commands, logs, or customer information.
- [ ] Include the active Runs list, Run detail/progress, notification or Live
  Activity presentation, pairing explanation, and privacy/read-only boundary.
- [ ] Check English and Simplified Chinese artwork for matching features and
  iOS 18 wording. Do not reuse an old screenshot when the UI or permission copy
  changed.
- [ ] Keep internal verification captures under
  `apps/ios/VerificationScreenshots/` separate from App Store assets unless a
  release owner has inspected and approved each image.

## Submission gate

- [ ] CI is green at the tagged commit, the Server-first rollout has passed
  readiness and smoke checks, and the TestFlight build has passed physical
  device testing.
- [ ] The changelog, compatibility matrix, privacy page, support page, and
  reviewer notes describe the exact release.
- [ ] **Manual:** select the intended build and submit it for review. The
  TestFlight workflow does not perform App Review submission or public release.
