import Foundation

struct CachedSnapshot: Codable, Equatable, Sendable {
    let runs: [RunSnapshot]
    let machines: [MachineSnapshot]
    let messages: [RichMessage]
    let syncCursor: Int?
    let serverTime: Date?
    let historyRunsNextCursor: String?
    let historyRunsHasMore: Bool
    let historyMessagesNextCursor: String?
    let historyMessagesHasMore: Bool
    let savedAt: Date

    init(
        runs: [RunSnapshot],
        machines: [MachineSnapshot],
        messages: [RichMessage],
        syncCursor: Int? = nil,
        serverTime: Date? = nil,
        historyRunsNextCursor: String? = nil,
        historyRunsHasMore: Bool = false,
        historyMessagesNextCursor: String? = nil,
        historyMessagesHasMore: Bool = false,
        savedAt: Date
    ) {
        self.runs = runs
        self.machines = machines
        self.messages = messages
        self.syncCursor = syncCursor
        self.serverTime = serverTime
        self.historyRunsNextCursor = historyRunsNextCursor
        self.historyRunsHasMore = historyRunsHasMore
        self.historyMessagesNextCursor = historyMessagesNextCursor
        self.historyMessagesHasMore = historyMessagesHasMore
        self.savedAt = savedAt
    }

    private enum CodingKeys: String, CodingKey {
        case runs
        case machines
        case messages
        case syncCursor
        case serverTime
        case historyRunsNextCursor
        case historyRunsHasMore
        case historyMessagesNextCursor
        case historyMessagesHasMore
        case savedAt
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        runs = try values.decode([RunSnapshot].self, forKey: .runs)
        machines = try values.decode([MachineSnapshot].self, forKey: .machines)
        messages = try values.decode([RichMessage].self, forKey: .messages)
        syncCursor = try values.decodeIfPresent(Int.self, forKey: .syncCursor)
        serverTime = try values.decodeIfPresent(Date.self, forKey: .serverTime)
        historyRunsNextCursor = try values.decodeIfPresent(String.self, forKey: .historyRunsNextCursor)
        historyRunsHasMore = try values.decodeIfPresent(Bool.self, forKey: .historyRunsHasMore)
            ?? (historyRunsNextCursor != nil)
        historyMessagesNextCursor = try values.decodeIfPresent(
            String.self,
            forKey: .historyMessagesNextCursor
        )
        historyMessagesHasMore = try values.decodeIfPresent(
            Bool.self,
            forKey: .historyMessagesHasMore
        ) ?? (historyMessagesNextCursor != nil)
        savedAt = try values.decode(Date.self, forKey: .savedAt)
    }
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
