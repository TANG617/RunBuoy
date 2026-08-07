# RunBuoy SwiftUI Performance Audit

## Summary

This is a code-backed audit of the iOS 18+ SwiftUI client. No high-impact
rendering blocker remains in the reviewed paths. Runtime CPU, hitch, and memory
metrics were not collected because there was no reported performance symptom;
the next validation step is a Release-build Instruments capture on a physical
device while progress events arrive at production frequency.

## Findings

1. High-frequency progress updates are scoped to one row
   - Risk: Updating one run could invalidate the entire task list.
   - Evidence: `RunSummaryModel` owns each row snapshot. The store reuses models
     by run ID and only replaces the active/history arrays when membership or
     order changes.
   - Resolution: Keep `runModelsByID` observation-ignored and let `RunRow` read
     only its model snapshot.
   - Validation: Use the SwiftUI Instruments cause-and-effect graph while
     updating one run at 1–5 Hz; sibling rows should not re-evaluate.

2. List identity is stable
   - Risk: Index identity or transient UUIDs would recreate rows and navigation
     state.
   - Evidence: Runs, messages, machines, feed events, and log lines use stable
     domain-derived IDs. Loading rows use a fixed enum rather than temporary
     observable objects.
   - Resolution: Preserve current ID sources and never key live collections by
     array offset.
   - Validation: Reorder and update runs while watching for row flashes or lost
     navigation state.

3. Periodic elapsed-time invalidation is isolated
   - Risk: A one-second timer could redraw the full detail screen indefinitely.
   - Evidence: `TimelineView` exists only in `RunElapsedView`, and completed
     runs render a static duration.
   - Resolution: Keep the timer leaf-scoped and active-run-only.
   - Validation: Compare SwiftUI update counts for active and completed details.

4. Liquid Glass and animation cost is bounded
   - Risk: Glass on every list row or broad animation modifiers would increase
     compositing cost and hitching.
   - Evidence: iOS 26+ custom glass is limited to the read-only action strip
     and primary controls. iOS 18–25 uses standard bordered buttons and Material.
     Task cards remain ordinary system list rows. Onboarding animation is
     value-scoped and disabled for Reduce Motion.
   - Resolution: Keep glass out of repeated task and message cells.
   - Validation: Profile scrolling with Core Animation and SwiftUI Instruments
     on an older supported iPhone.

5. Derived work stays out of `body`
   - Risk: Sorting feeds or constructing unstable data during rendering would
     repeat work on every invalidation.
   - Evidence: Network and store work runs in async methods; detail feed sorting
     and safe-log identity are prepared before row rendering.
   - Resolution: Continue moving expensive transformations to input boundaries.
   - Validation: Time Profile a long history and detail feed in Release.

## Verification

- iOS deployment target: 18.0 for App, Widget, unit-test, and UI-test targets
- Debug generic simulator build: passed with the latest SDK
- Release unsigned App + Widget archive: passed; both privacy manifests present
- Unit tests: 46 passed, 0 failed, 0 skipped
- Critical UI smoke: 2 passed, 0 failed, 0 skipped
- Read-only boundary script: passed
- `git diff --check`: passed
