import Foundation

struct CachedSnapshot: Codable, Equatable, Sendable {
    let runs: [RunSnapshot]
    let machines: [MachineSnapshot]
    let messages: [RichMessage]
    let savedAt: Date
}

actor LocalCacheStore {
    private let fileURL: URL
    private let fileManager: FileManager

    init(fileURL: URL? = nil, fileManager: FileManager = .default) {
        self.fileManager = fileManager
        if let fileURL {
            self.fileURL = fileURL
        } else {
            let base = fileManager.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
            self.fileURL = base.appendingPathComponent("RunBuoy", isDirectory: true)
                .appendingPathComponent("read-cache.json", isDirectory: false)
        }
    }

    func load() throws -> CachedSnapshot? {
        guard fileManager.fileExists(atPath: fileURL.path) else { return nil }
        return try JSONDecoder.runBuoy.decode(CachedSnapshot.self, from: Data(contentsOf: fileURL))
    }

    func save(_ snapshot: CachedSnapshot) throws {
        let directory = fileURL.deletingLastPathComponent()
        try fileManager.createDirectory(at: directory, withIntermediateDirectories: true)
        let data = try JSONEncoder.runBuoy.encode(snapshot)
        try data.write(to: fileURL, options: [.atomic, .completeFileProtectionUnlessOpen])
    }

    func clear() throws {
        guard fileManager.fileExists(atPath: fileURL.path) else { return }
        try fileManager.removeItem(at: fileURL)
    }
}
