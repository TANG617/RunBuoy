import Foundation
#if os(iOS)
import ActivityKit
#endif

public struct RunActivityAttributes {
    public let runID: String
    public let title: String
    public let machineName: String
    public let schemaVersion: Int

    public init(runID: String, title: String, machineName: String, schemaVersion: Int = 1) {
        self.runID = runID
        self.title = title
        self.machineName = machineName
        self.schemaVersion = schemaVersion
    }

    public struct ContentState: Codable, Hashable {
        public let sequence: Int
        public let executionStatus: String
        public let healthStatus: String
        public let attentionStatus: String
        public let progressKind: String
        public let progress: Double?
        public let current: Double?
        public let total: Double?
        public let phase: String?
        public let message: String?
        public let createdAt: Date?
        public let startedAt: Date
        public let updatedAt: Date
        public let machineName: String?
        public let endedAt: Date?
        public let estimatedEndAt: Date?
        public let exitCode: Int?

        public init(
            sequence: Int,
            executionStatus: String,
            healthStatus: String,
            attentionStatus: String,
            progressKind: String,
            progress: Double?,
            current: Double? = nil,
            total: Double? = nil,
            phase: String?,
            message: String?,
            createdAt: Date? = nil,
            startedAt: Date,
            updatedAt: Date,
            machineName: String? = nil,
            endedAt: Date? = nil,
            estimatedEndAt: Date?,
            exitCode: Int?
        ) {
            self.sequence = sequence
            self.executionStatus = executionStatus
            self.healthStatus = healthStatus
            self.attentionStatus = attentionStatus
            self.progressKind = progressKind
            self.progress = progress
            self.current = current
            self.total = total
            self.phase = phase
            self.message = message
            self.createdAt = createdAt
            self.startedAt = startedAt
            self.updatedAt = updatedAt
            self.machineName = machineName
            self.endedAt = endedAt
            self.estimatedEndAt = estimatedEndAt
            self.exitCode = exitCode
        }

        private enum CodingKeys: String, CodingKey {
            case sequence
            case executionStatus
            case healthStatus
            case attentionStatus
            case progressKind
            case progress
            case current
            case total
            case phase
            case message
            case createdAt
            case startedAt
            case updatedAt
            case machineName
            case endedAt
            case estimatedEndAt
            case exitCode
        }

        public init(from decoder: Decoder) throws {
            let values = try decoder.container(keyedBy: CodingKeys.self)
            sequence = try values.decode(Int.self, forKey: .sequence)
            executionStatus = try values.decode(String.self, forKey: .executionStatus)
            healthStatus = try values.decode(String.self, forKey: .healthStatus)
            attentionStatus = try values.decode(String.self, forKey: .attentionStatus)
            progressKind = try values.decode(String.self, forKey: .progressKind)
            progress = try values.decodeIfPresent(Double.self, forKey: .progress)
            current = try values.decodeIfPresent(Double.self, forKey: .current)
            total = try values.decodeIfPresent(Double.self, forKey: .total)
            phase = try values.decodeIfPresent(String.self, forKey: .phase)
            message = try values.decodeIfPresent(String.self, forKey: .message)
            createdAt = try values.contains(.createdAt)
                ? Self.decodeOptionalDate(values, key: .createdAt)
                : nil
            startedAt = try Self.decodeDate(values, key: .startedAt)
            updatedAt = try Self.decodeDate(values, key: .updatedAt)
            machineName = try values.decodeIfPresent(String.self, forKey: .machineName)
            endedAt = try values.contains(.endedAt)
                ? Self.decodeOptionalDate(values, key: .endedAt)
                : nil
            estimatedEndAt = try values.contains(.estimatedEndAt)
                ? Self.decodeOptionalDate(values, key: .estimatedEndAt)
                : nil
            exitCode = try values.decodeIfPresent(Int.self, forKey: .exitCode)
        }

        public func encode(to encoder: Encoder) throws {
            var values = encoder.container(keyedBy: CodingKeys.self)
            try values.encode(sequence, forKey: .sequence)
            try values.encode(executionStatus, forKey: .executionStatus)
            try values.encode(healthStatus, forKey: .healthStatus)
            try values.encode(attentionStatus, forKey: .attentionStatus)
            try values.encode(progressKind, forKey: .progressKind)
            try values.encodeIfPresent(progress, forKey: .progress)
            try values.encodeIfPresent(current, forKey: .current)
            try values.encodeIfPresent(total, forKey: .total)
            try values.encodeIfPresent(phase, forKey: .phase)
            try values.encodeIfPresent(message, forKey: .message)
            try values.encodeIfPresent(
                createdAt.map(Self.dateFormatter.string(from:)),
                forKey: .createdAt
            )
            try values.encode(Self.dateFormatter.string(from: startedAt), forKey: .startedAt)
            try values.encode(Self.dateFormatter.string(from: updatedAt), forKey: .updatedAt)
            try values.encodeIfPresent(machineName, forKey: .machineName)
            try values.encodeIfPresent(endedAt.map(Self.dateFormatter.string(from:)), forKey: .endedAt)
            try values.encodeIfPresent(estimatedEndAt.map(Self.dateFormatter.string(from:)), forKey: .estimatedEndAt)
            try values.encodeIfPresent(exitCode, forKey: .exitCode)
        }

        private static func decodeDate(
            _ values: KeyedDecodingContainer<CodingKeys>,
            key: CodingKeys
        ) throws -> Date {
            if let string = try? values.decode(String.self, forKey: key),
               let date = dateFormatter.date(from: string) ?? fallbackDateFormatter.date(from: string) {
                return date
            }
            if let seconds = try? values.decode(Double.self, forKey: key) {
                return Date(timeIntervalSince1970: seconds)
            }
            throw DecodingError.dataCorruptedError(
                forKey: key,
                in: values,
                debugDescription: "Expected an ISO-8601 string or Unix timestamp."
            )
        }

        private static func decodeOptionalDate(
            _ values: KeyedDecodingContainer<CodingKeys>,
            key: CodingKeys
        ) throws -> Date? {
            if try values.decodeNil(forKey: key) {
                return nil
            }
            return try decodeDate(values, key: key)
        }

        private static let dateFormatter: ISO8601DateFormatter = {
            let formatter = ISO8601DateFormatter()
            formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            return formatter
        }()

        private static let fallbackDateFormatter: ISO8601DateFormatter = {
            let formatter = ISO8601DateFormatter()
            formatter.formatOptions = [.withInternetDateTime]
            return formatter
        }()
    }
}

enum RunActivityDurationText {
    static func string(
        createdAt: Date?,
        startedAt: Date,
        updatedAt: Date
    ) -> String {
        let anchor = createdAt ?? startedAt
        let totalSeconds = max(0, Int(updatedAt.timeIntervalSince(anchor)))
        let hours = totalSeconds / 3_600
        let minutes = (totalSeconds % 3_600) / 60
        let seconds = totalSeconds % 60
        if hours > 0 {
            return String(format: "%d:%02d:%02d", hours, minutes, seconds)
        }
        return String(format: "%d:%02d", minutes, seconds)
    }
}

enum RunActivityTerminalTimeText {
    static func string(
        endedAt: Date,
        currentDate: Date,
        locale: Locale = .autoupdatingCurrent
    ) -> String {
        let elapsedSeconds = max(0, currentDate.timeIntervalSince(endedAt))
        let completedMinutes = Int(elapsedSeconds / 60)
        guard completedMinutes > 0 else {
            return localizedString(forKey: "widget.just_now", locale: locale)
        }

        return String(
            format: localizedString(forKey: "widget.minutes_ago", locale: locale),
            locale: locale,
            Int64(completedMinutes)
        )
    }

    static func nextRefreshDate(endedAt: Date, currentDate: Date) -> Date {
        let elapsedSeconds = max(0, currentDate.timeIntervalSince(endedAt))
        let completedMinutes = floor(elapsedSeconds / 60)
        return endedAt.addingTimeInterval((completedMinutes + 1) * 60)
    }

    private static func localizedString(forKey key: String, locale: Locale) -> String {
        let preferredLocalizations = Bundle.preferredLocalizations(
            from: Bundle.main.localizations,
            forPreferences: [locale.identifier]
        )
        guard let localization = preferredLocalizations.first,
              let path = Bundle.main.path(
                forResource: localization,
                ofType: "lproj"
              ),
              let localizedBundle = Bundle(path: path)
        else {
            return String(localized: String.LocalizationValue(key), bundle: .main)
        }
        return localizedBundle.localizedString(forKey: key, value: key, table: nil)
    }
}

extension RunActivityAttributes.ContentState {
    var completionDate: Date {
        endedAt ?? updatedAt
    }
}

#if os(iOS)
extension RunActivityAttributes: ActivityAttributes {}
#endif
