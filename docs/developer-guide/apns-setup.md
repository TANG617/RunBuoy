# APNs and Live Activity setup

RunBuoy defaults to deterministic mock delivery. Production delivery requires
an Apple Developer account, a physical device, signing, and an APNs provider
key; none of those secrets belong in this repository.

## Apple configuration

1. Register the app ID (the sample project uses `dev.runbuoy.app`; replace it
   for your team).
2. Enable Push Notifications and Live Activities for the app ID and
   provisioning profile.
3. Create an APNs `.p8` provider key and record its Key ID and Team ID.
4. Configure the App and Widget targets with the same signing team and the
   documented bundle IDs.
5. Install on a physical iOS 26+ device and grant notifications.

Apple requires apps to register with APNs and forward the latest device token
to their provider. Device tokens may change and must not be treated as stable
or cached forever. RunBuoy also observes `pushToStartTokenUpdates`, each
Activity's `pushTokenUpdates`, and current Activities during reconciliation.

Official references:

- [Registering your app with APNs](https://developer.apple.com/documentation/usernotifications/registering-your-app-with-apns)
- [Starting and updating Live Activities with ActivityKit push notifications](https://developer.apple.com/documentation/activitykit/starting-and-updating-live-activities-with-activitykit-push-notifications)
- [Sending notification requests to APNs](https://developer.apple.com/documentation/usernotifications/sending-notification-requests-to-apns)
- [Handling APNs responses](https://developer.apple.com/documentation/usernotifications/handling-notification-responses-from-apns)
- [`NSSupportsLiveActivities`](https://developer.apple.com/documentation/bundleresources/information-property-list/nssupportsliveactivities)

## Server environment

Use a secret manager in production:

```dotenv
APNS_MODE=production
APNS_ENVIRONMENT=development
APNS_TEAM_ID=YOUR_TEAM_ID
APNS_KEY_ID=YOUR_KEY_ID
APNS_BUNDLE_ID=dev.runbuoy.app
APNS_PRIVATE_KEY_PATH=/run/secrets/AuthKey_KEYID.p8
TOKEN_ENCRYPTION_KEY=base64-encoded-32-byte-key
```

Use `APNS_ENVIRONMENT=production` only for distribution-signed builds.
Provider connections use HTTP/2 and TLS. Token authentication uses ES256;
provider JWTs are cached below Apple's one-hour refresh ceiling. Normal alert
topics use the app bundle ID. Live Activity requests use push type
`liveactivity` and topic `<bundle-id>.push-type.liveactivity`.

ActivityKit payloads use epoch-second `timestamp`, `event` set to `start`,
`update`, or `end`, and a `content-state` matching
`RunActivityAttributes.ContentState`. Start payloads also contain an alert,
`attributes-type`, and `attributes`. End payloads contain the final content
state. Ordinary progress uses priority 5; terminal and attention transitions
use 10. Active updates carry a stale date 60 seconds after the latest
confirmed Machine event. End payloads omit the stale date, carry final state,
and use ActivityKit's default dismissal behavior. APNs expiration is bounded
by event semantics: starts remain useful for five minutes, updates until their
stale date, and terminal updates for four hours. A per-activity collapse ID
allows APNs to retain the newest useful snapshot while a device is offline.

The app also reconciles locally whenever a foreground API refresh completes.
It applies only a newer Run sequence, ends terminal activities, and reports the
ActivityKit sequence and lifecycle state to the server. Active and stale
bindings remain eligible for push delivery; a lagging sequence causes the
server to enqueue the current full snapshot. Pending remote starts that never
materialize are released after `LIVE_ACTIVITY_PENDING_TTL_SECONDS`.

APNs `410 Unregistered` invalidates the target. Permanent 4xx errors are not
retried; transient failures use bounded exponential backoff.

## Mock mode

```dotenv
APNS_MODE=mock
```

Mock mode records headers, exact JSON payloads, and deterministic HTTP 200
results in the `push_attempts` database table. It requires no Apple
credentials and is the only APNs mode used in CI.

## Physical-device verification

1. Clear old tokens in the test database.
2. Launch the signed app and confirm normal, push-to-start, and update tokens
   are registered without appearing in logs.
3. Pair the CLI.
4. Run `runbuoy run --live-activity immediate -- sleep 8`.
5. Confirm an immediate start and an end on completion; also verify that a
   normal automatic Run still observes the five-second policy.
6. Rotate/reinstall and confirm replacement tokens take effect.
7. Use Apple's Push Notification Console for payload troubleshooting.

This repository's automated results do not imply that production APNs or a
physical iPhone has been verified.
