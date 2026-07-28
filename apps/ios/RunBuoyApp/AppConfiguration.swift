import Foundation

struct AppConfiguration: Sendable {
    static let serverAddressDefaultsKey = "runbuoy.server-address"

    let apiBaseURL: URL

    static var live: AppConfiguration {
        let address = UserDefaults.standard.string(forKey: serverAddressDefaultsKey)
        return AppConfiguration(
            apiBaseURL: resolvedAPIBaseURL(
                serverAddress: address,
                defaultBaseURL: bundledAPIBaseURL
            ) ?? bundledAPIBaseURL
        )
    }

    static var bundledAPIBaseURL: URL {
        let configured = Bundle.main.object(forInfoDictionaryKey: "RUNBUOY_API_BASE_URL") as? String
        let fallback = URL(string: "https://api.example.runbuoy.dev")!
        guard let configured,
              let url = URL(string: configured),
              url.host != nil
        else {
            return fallback
        }
        return url
    }

    static var defaultServerAddress: String {
        displayAddress(for: bundledAPIBaseURL)
    }

    static func resolvedAPIBaseURL(
        serverAddress: String?,
        defaultBaseURL: URL
    ) -> URL? {
        let value = serverAddress?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard !value.isEmpty else {
            return defaultBaseURL
        }

        let hasScheme = value.contains("://")
        let candidate = hasScheme
            ? value
            : "\(defaultBaseURL.scheme ?? "https")://\(value)"
        guard var components = URLComponents(string: candidate),
              let scheme = components.scheme?.lowercased(),
              ["http", "https"].contains(scheme),
              let host = components.host,
              !host.isEmpty,
              components.user == nil,
              components.password == nil,
              components.query == nil,
              components.fragment == nil,
              components.path.isEmpty || components.path == "/"
        else {
            return nil
        }

        if !hasScheme,
           isIPv4Address(host),
           bundledHostUsesSSLIP(defaultBaseURL) {
            components.host = "\(host.replacingOccurrences(of: ".", with: "-")).sslip.io"
        }
        components.path = ""
        return components.url
    }

    static func displayAddress(for url: URL) -> String {
        guard let host = url.host else { return url.absoluteString }
        let displayHost: String
        if let address = ipv4Address(fromSSLIPHost: host) {
            displayHost = address
        } else if host.contains(":") {
            displayHost = "[\(host)]"
        } else {
            displayHost = host
        }
        if let port = url.port {
            return "\(displayHost):\(port)"
        }
        return displayHost
    }

    private static func bundledHostUsesSSLIP(_ url: URL) -> Bool {
        url.host?.lowercased().hasSuffix(".sslip.io") == true
    }

    private static func ipv4Address(fromSSLIPHost host: String) -> String? {
        let suffix = ".sslip.io"
        let lowercasedHost = host.lowercased()
        guard lowercasedHost.hasSuffix(suffix) else { return nil }
        let address = String(lowercasedHost.dropLast(suffix.count))
            .replacingOccurrences(of: "-", with: ".")
        return isIPv4Address(address) ? address : nil
    }

    private static func isIPv4Address(_ value: String) -> Bool {
        let octets = value.split(separator: ".", omittingEmptySubsequences: false)
        guard octets.count == 4 else { return false }
        return octets.allSatisfy { octet in
            guard !octet.isEmpty,
                  octet.count <= 3,
                  let number = Int(octet)
            else {
                return false
            }
            return 0...255 ~= number
        }
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
