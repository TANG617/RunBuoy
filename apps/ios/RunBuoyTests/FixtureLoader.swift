import Foundation

enum FixtureLoader {
    static func data(_ name: String, extension fileExtension: String = "json") throws -> Data {
        let bundle = Bundle(for: BundleMarker.self)
        guard let url = bundle.url(forResource: name, withExtension: fileExtension) else {
            throw FixtureError.missing(name)
        }
        return try Data(contentsOf: url)
    }
}

private final class BundleMarker {}

private enum FixtureError: Error {
    case missing(String)
}
