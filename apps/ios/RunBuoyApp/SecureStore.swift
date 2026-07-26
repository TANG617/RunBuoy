import Foundation
import Security

protocol DeviceIdentityStoring: Sendable {
    func load() throws -> DeviceIdentity?
    func save(_ identity: DeviceIdentity) throws
    func remove() throws
}

struct KeychainDeviceIdentityStore: DeviceIdentityStoring {
    private let service: String
    private let account = "device-identity"

    init(service: String = "dev.runbuoy.app") {
        self.service = service
    }

    func load() throws -> DeviceIdentity? {
        var query = baseQuery
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne

        var result: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        if status == errSecItemNotFound {
            return nil
        }
        guard status == errSecSuccess, let data = result as? Data else {
            throw SecureStoreError.unexpectedStatus(status)
        }
        return try JSONDecoder().decode(DeviceIdentity.self, from: data)
    }

    func save(_ identity: DeviceIdentity) throws {
        let data = try JSONEncoder().encode(identity)
        let update = [kSecValueData as String: data]
        let status = SecItemUpdate(baseQuery as CFDictionary, update as CFDictionary)
        if status == errSecItemNotFound {
            var query = baseQuery
            query[kSecValueData as String] = data
            query[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            let addStatus = SecItemAdd(query as CFDictionary, nil)
            guard addStatus == errSecSuccess else {
                throw SecureStoreError.unexpectedStatus(addStatus)
            }
        } else if status != errSecSuccess {
            throw SecureStoreError.unexpectedStatus(status)
        }
    }

    func remove() throws {
        let status = SecItemDelete(baseQuery as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else {
            throw SecureStoreError.unexpectedStatus(status)
        }
    }

    private var baseQuery: [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account
        ]
    }
}

enum SecureStoreError: Error {
    case unexpectedStatus(OSStatus)
}
