import XCTest
@testable import RunBuoyApp

final class CacheStoreTests: XCTestCase {
    func testCacheRoundTripAndClear() async throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("runbuoy-cache-test-\(UUID().uuidString)", isDirectory: true)
        let fileURL = directory.appendingPathComponent("cache.json")
        let cache = LocalCacheStore(fileURL: fileURL)
        let expected = CachedSnapshot(
            runs: [PreviewFixtures.activeRun],
            machines: [PreviewFixtures.machine],
            messages: [PreviewFixtures.message],
            savedAt: PreviewFixtures.baseDate
        )

        try await cache.save(expected)
        let loaded = try await cache.load()
        XCTAssertEqual(loaded, expected)
        try await cache.clear()
        let cleared = try await cache.load()
        XCTAssertNil(cleared)
    }
}
