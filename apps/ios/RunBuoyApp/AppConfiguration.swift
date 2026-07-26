import Foundation

struct AppConfiguration: Sendable {
    let apiBaseURL: URL

    static var live: AppConfiguration {
        let configured = Bundle.main.object(forInfoDictionaryKey: "RUNBUOY_API_BASE_URL") as? String
        let fallback = "https://api.example.runbuoy.dev"
        return AppConfiguration(apiBaseURL: URL(string: configured ?? fallback) ?? URL(string: fallback)!)
    }
}

extension JSONDecoder {
    static var runBuoy: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            if let string = try? container.decode(String.self),
               let date = ISO8601DateFormatter.runBuoy.date(from: string)
                    ?? ISO8601DateFormatter.runBuoyWithoutFraction.date(from: string) {
                return date
            }
            if let seconds = try? container.decode(Double.self) {
                return Date(timeIntervalSince1970: seconds)
            }
            throw DecodingError.dataCorruptedError(
                in: container,
                debugDescription: "Expected an ISO-8601 string or Unix timestamp."
            )
        }
        return decoder
    }
}

extension JSONEncoder {
    static var runBuoy: JSONEncoder {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .custom { date, encoder in
            var container = encoder.singleValueContainer()
            try container.encode(ISO8601DateFormatter.runBuoy.string(from: date))
        }
        encoder.outputFormatting = [.sortedKeys]
        return encoder
    }
}

extension ISO8601DateFormatter {
    static let runBuoy: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()

    static let runBuoyWithoutFraction: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()
}
